"""Entry 96 split-capacitor / floating-resistor binary bank probe.

Stage one treats the proposed bank as a two-terminal differential block.  It
does not instantiate the CTLE or touch the frozen policy.  Every switched deck
contains a separately drawn real-passive R||C control so selector error is
measured against silicon geometry, not against an ideal equation.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Sequence

import numpy as np

from nebula.device.crosscheck import scan_for_silent_failures
from nebula.device.ngspice_runner import ngspice_path
from nebula.device.passives import capacitor_geometry, resistor_geometry
from nebula.device.sky130_runner import (
    NFET_01V8,
    SPICE_DIR,
    _m_suffix,
    lib_for_device,
)

HERE = Path(__file__).resolve().parent
EXPERIMENTS = HERE.parent / "experiments"
ENTRY81_PATH = EXPERIMENTS / "joint_bank_results.json"
ENTRY95_PATH = EXPERIMENTS / "tuning_switch_results.json"
ENTRY81_SHA256 = "72B3C88551E0F2B8D4F0A25AB8D760CFDED3FFD36911AF1A51A534497E11AE9D"
ENTRY95_SHA256 = "E99F7CD8BAD788DF2F36CD4E3585E66110D30108D7AEBCB520498E7B6F339883"

R_SWITCH_WIDTHS_UM: tuple[float, ...] = (80.0, 160.0, 320.0)
C_SWITCH_WIDTHS_UM: tuple[float, ...] = (160.0, 320.0, 640.0)
FREQS_HZ: tuple[float, ...] = (1.25e9, 2.5e9)
SOURCE_V: float = 0.50
VDD_V: float = 1.8
TEMP_C: float = 27.0
L_UM: float = 0.15


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


@dataclass(frozen=True)
class BankTargets:
    rs_values_ohm: tuple[float, ...]
    cs_values_f: tuple[float, ...]
    r_branch_total_ohm: tuple[float, ...]
    r_branch_drawn_ohm: tuple[float, ...]
    r_nominal_ron_ohm: tuple[float, ...]
    c_branch_per_side_f: tuple[float, ...]
    c_fixed_per_side_f: float
    g_step_s: float
    c_step_f: float


@lru_cache(maxsize=1)
def bank_targets() -> BankTargets:
    """Derive endpoints and switch compensation from hash-gated evidence."""
    if _sha256(ENTRY81_PATH) != ENTRY81_SHA256:
        raise ValueError("Entry 81 base artifact hash mismatch")
    if _sha256(ENTRY95_PATH) != ENTRY95_SHA256:
        raise ValueError("Entry 95 switch artifact hash mismatch")

    from nebula.experiments import exp_joint_bank as J
    from nebula.experiments.exp_tuning_bank import bank
    from nebula.rl.contract import sizing_from_u

    source = json.loads(ENTRY81_PATH.read_text(encoding="utf-8"))
    old = bank(source["base_u"], n_rs=J.N_RS, n_cs=J.N_CS,
               rs_span=J.RS_SPAN, cs_span=J.CS_SPAN)
    rs_old, cs_old = {}, {}
    for setting in old:
        params = sizing_from_u(setting.u).params
        rs_old.setdefault(setting.i_rs, float(params["rs"]))
        cs_old.setdefault(setting.i_cs, float(params["cs"]))
    if sorted(rs_old) != list(range(8)) or sorted(cs_old) != list(range(8)):
        raise ValueError("Entry 81 bank does not have an 8x8 code grid")
    r_min, r_max = rs_old[0], rs_old[7]
    c_min, c_max = cs_old[0], cs_old[7]
    g_step = (1.0 / r_min - 1.0 / r_max) / 7.0
    c_step = (c_max - c_min) / 7.0
    rs_values = tuple(1.0 / (1.0 / r_max + (7 - code) * g_step)
                      for code in range(8))
    cs_values = tuple(c_min + code * c_step for code in range(8))
    r_total = tuple(1.0 / (g_step * (2 ** bit)) for bit in range(3))

    switch = json.loads(ENTRY95_PATH.read_text(encoding="ascii"))
    lookup = {(float(row["width_um"]), str(row["corner"]),
               float(row["source_v"])): float(row["ron_ohm"])
              for row in switch["rows"]}
    ron = tuple(lookup[(w, "tt/1.00/27C", SOURCE_V)]
                for w in R_SWITCH_WIDTHS_UM)
    drawn = tuple(total - r_on for total, r_on in zip(r_total, ron))
    if not all(value > 0.0 for value in drawn):
        raise ValueError("switch Ron exceeds an Entry 96 resistor branch")
    return BankTargets(
        rs_values_ohm=rs_values, cs_values_f=cs_values,
        r_branch_total_ohm=r_total, r_branch_drawn_ohm=drawn,
        r_nominal_ron_ohm=ron,
        c_branch_per_side_f=tuple(2.0 * c_step * (2 ** bit)
                                  for bit in range(3)),
        c_fixed_per_side_f=2.0 * c_min,
        g_step_s=g_step, c_step_f=c_step)


# Fixed after bank_targets()'s exact endpoint derivation; literals are Entry 96
# registration values and tests prove they match the derived quantities.
G_ERROR_LIMIT_S: float = 0.0009134338015678002
C_ERROR_LIMIT_F: float = 0.5939536666962287e-12


def _res_line(name: str, a: str, b: str, target_ohm: float) -> str:
    geo = resistor_geometry(target_ohm)
    return (f"{name} {a} {b} 0 {geo.subckt} w={geo.w_um:g} l={geo.l_um:g}"
            f"{_m_suffix(geo.m)}")


def _cap_line(name: str, a: str, b: str, target_f: float) -> str:
    geo = capacitor_geometry(target_f)
    return (f"{name} {a} {b} {geo.subckt} w={geo.w_um:g} l={geo.l_um:g}"
            f"{_m_suffix(geo.m)}")


def build_deck(r_code: int, c_code: int) -> str:
    """One code plus its real-passive control, including every OFF device."""
    if not 0 <= int(r_code) < 8 or not 0 <= int(c_code) < 8:
        raise ValueError("R and C codes must each be in 0..7")
    r_code, c_code = int(r_code), int(c_code)
    t = bank_targets()
    lib = lib_for_device(NFET_01V8, real_passives=True, section="tt")
    lines = [
        f"* Entry 96 split bank R{r_code} C{c_code} -- generated",
        f'.lib "{lib.as_posix()}" tt',
        f".temp {TEMP_C:g}",
        f"Vdd vdd 0 {VDD_V:g}",
        f"Vsp sp 0 dc {SOURCE_V:g} ac 0.5",
        f"Vsn sn 0 dc {SOURCE_V:g} ac -0.5",
        f"Vcp cp 0 dc {SOURCE_V:g} ac 0.5",
        f"Vcn cn 0 dc {SOURCE_V:g} ac -0.5",
        "* Same-deck separately drawn R || C control.",
        _res_line("Xctrl_r", "cp", "cn", t.rs_values_ohm[r_code]),
        _cap_line("Xctrl_c", "cp", "cn", t.cs_values_f[c_code]),
        "* Floating binary resistor bank: fixed Rmax plus 3 conductance bits.",
        _res_line("Xbank_rfix", "sp", "sn", t.rs_values_ohm[7]),
    ]
    r_mask = 7 - r_code
    for bit, (target, width) in enumerate(zip(
            t.r_branch_drawn_ohm, R_SWITCH_WIDTHS_UM)):
        gate = "vdd" if r_mask & (1 << bit) else "0"
        nf = int(round(width / 40.0))
        lines += [
            _res_line(f"Xbank_rb{bit}", "sp", f"rmid{bit}", target),
            f"Xbank_rsw{bit} rmid{bit} {gate} sn 0 {NFET_01V8} "
            f"W={width:g} L={L_UM:g} nf={nf}",
        ]
    lines += [
        "* Split-C bank: 2C per side is differential-equivalent to C across.",
        _cap_line("Xbank_cfixp", "sp", "0", t.c_fixed_per_side_f),
        _cap_line("Xbank_cfixn", "sn", "0", t.c_fixed_per_side_f),
    ]
    for bit, (target, width) in enumerate(zip(
            t.c_branch_per_side_f, C_SWITCH_WIDTHS_UM)):
        gate = "vdd" if c_code & (1 << bit) else "0"
        nf = int(round(width / 40.0))
        for side, node in (("p", "sp"), ("n", "sn")):
            lines += [
                _cap_line(f"Xbank_cb{side}{bit}", node,
                          f"cmid{side}{bit}", target),
                f"Xbank_csw{side}{bit} cmid{side}{bit} {gate} 0 0 {NFET_01V8} "
                f"W={width:g} L={L_UM:g} nf={nf}",
            ]
    lines += [
        ".control",
        "set noaskquit",
        "set filetype=ascii",
        f"ac lin 3 {FREQS_HZ[0]:g} {FREQS_HZ[1]:g}",
        "wrdata admittance.txt i(Vsp) i(Vsn) i(Vcp) i(Vcn)",
        "quit",
        ".endc",
        ".end",
    ]
    return "\n".join(lines) + "\n"


def parse_admittance(raw: np.ndarray) -> dict[str, tuple[complex, complex]]:
    """Parse four complex source currents and project differential admittance."""
    arr = np.atleast_2d(np.asarray(raw, dtype=float))
    if arr.shape != (3, 12):
        raise ValueError(f"admittance.txt has shape {arr.shape}, expected (3, 12)")
    expected_f = np.linspace(FREQS_HZ[0], FREQS_HZ[1], 3)
    for base in (0, 3, 6, 9):
        if not np.allclose(arr[:, base], expected_f, rtol=1e-12, atol=1.0):
            raise ValueError(f"admittance frequency axis mismatch at column {base}")
    currents = [arr[:, base + 1] + 1j * arr[:, base + 2]
                for base in (0, 3, 6, 9)]
    y_sw = -0.5 * (currents[0] - currents[1])
    y_ctrl = -0.5 * (currents[2] - currents[3])
    return {"switched": (complex(y_sw[0]), complex(y_sw[-1])),
            "control": (complex(y_ctrl[0]), complex(y_ctrl[-1]))}


@dataclass(frozen=True)
class BankRow:
    r_code: int
    c_code: int
    switched_g_s: tuple[float, float]
    switched_c_f: tuple[float, float]
    control_g_s: tuple[float, float]
    control_c_f: tuple[float, float]

    def to_dict(self) -> dict:
        return asdict(self)


def run_code(r_code: int, c_code: int, timeout_s: float = 120.0) -> BankRow:
    text = build_deck(r_code, c_code)
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        shutil.copy(SPICE_DIR / ".spiceinit", tmp / ".spiceinit")
        (tmp / "bank.cir").write_text(text, encoding="ascii", newline="\n")
        try:
            proc = subprocess.run(
                [str(ngspice_path()), "-b", "bank.cir"], cwd=str(tmp),
                capture_output=True, text=True, timeout=float(timeout_s))
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"R{r_code}C{c_code} timeout") from exc
        out = proc.stdout + "\n" + proc.stderr
        offenders = scan_for_silent_failures(out)
        if offenders:
            raise RuntimeError(f"R{r_code}C{c_code} silent failure: "
                               f"{offenders[0][:240]}")
        path = tmp / "admittance.txt"
        if not path.exists() or path.stat().st_size == 0:
            raise RuntimeError(f"R{r_code}C{c_code} wrote no admittance.txt; "
                               f"tail: {out[-800:]}")
        adm = parse_admittance(np.loadtxt(path))

    def values(which: str) -> tuple[tuple[float, float], tuple[float, float]]:
        y = adm[which]
        g = tuple(float(value.real) for value in y)
        c = tuple(float(value.imag) / (2.0 * math.pi * f)
                  for value, f in zip(y, FREQS_HZ))
        if not all(math.isfinite(x) and x > 0 for x in (*g, *c)):
            raise RuntimeError(f"R{r_code}C{c_code} {which} non-positive: {g}, {c}")
        return g, c

    sw_g, sw_c = values("switched")
    ctrl_g, ctrl_c = values("control")
    return BankRow(r_code=int(r_code), c_code=int(c_code),
                   switched_g_s=sw_g, switched_c_f=sw_c,
                   control_g_s=ctrl_g, control_c_f=ctrl_c)


def assess(rows: Sequence[BankRow]) -> dict:
    rows = list(rows)
    keys = [(r.r_code, r.c_code) for r in rows]
    finite = all(
        len(values) == len(FREQS_HZ)
        and all(math.isfinite(x) and x > 0.0 for x in values)
        for row in rows for values in
        (row.switched_g_s, row.switched_c_f,
         row.control_g_s, row.control_c_f))
    s1 = (len(rows) == 64 and len(set(keys)) == 64
          and set(keys) == {(r, c) for r in range(8) for c in range(8)}
          and finite)
    by_key = {(r.r_code, r.c_code): r for r in rows}
    s2 = s1
    s3 = s1
    if s1:
        for ccode in range(8):
            for fi in range(2):
                g = [by_key[(rcode, ccode)].switched_g_s[fi]
                     for rcode in range(8)]
                if not all(a > b for a, b in zip(g, g[1:])):
                    s2 = False
        for rcode in range(8):
            for fi in range(2):
                c = [by_key[(rcode, ccode)].switched_c_f[fi]
                     for ccode in range(8)]
                if not all(a < b for a, b in zip(c, c[1:])):
                    s3 = False
    max_g_error = max((abs(a - b) for row in rows
                       for a, b in zip(row.switched_g_s, row.control_g_s)),
                      default=math.inf)
    max_c_error = max((abs(a - b) for row in rows
                       for a, b in zip(row.switched_c_f, row.control_c_f)),
                      default=math.inf)
    s4 = bool(s1 and max_g_error <= G_ERROR_LIMIT_S)
    s5 = bool(s1 and max_c_error <= C_ERROR_LIMIT_F)
    s6 = True
    return {
        "S1": s1, "S2": s2, "S3": s3, "S4": s4, "S5": s5, "S6": s6,
        "overall": bool(s1 and s2 and s3 and s4 and s5 and s6),
        "max_g_error_s": max_g_error,
        "g_error_limit_s": G_ERROR_LIMIT_S,
        "max_c_error_f": max_c_error,
        "c_error_limit_f": C_ERROR_LIMIT_F,
    }


def run_bank(workers: int = 8) -> tuple[list[BankRow], dict]:
    import concurrent.futures

    codes = [(r, c) for r in range(8) for c in range(8)]
    t0 = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=int(workers)) as ex:
        rows = list(ex.map(lambda rc: run_code(*rc), codes))
    result = assess(rows)
    result["wall_clock_s"] = time.perf_counter() - t0
    return rows, result


__all__ = (
    "ENTRY81_SHA256", "ENTRY95_SHA256", "R_SWITCH_WIDTHS_UM",
    "C_SWITCH_WIDTHS_UM", "FREQS_HZ", "G_ERROR_LIMIT_S",
    "C_ERROR_LIMIT_F", "BankTargets", "BankRow", "bank_targets",
    "build_deck", "parse_admittance", "run_code", "assess", "run_bank",
)
