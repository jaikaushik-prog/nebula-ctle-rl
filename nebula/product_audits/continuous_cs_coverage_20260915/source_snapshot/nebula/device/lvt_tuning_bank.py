"""Entry 97 safe-LVT capacitor-selector feasibility screen.

This stage is deliberately isolated from the CTLE and RL layers.  Six frozen
width scales of the official SKY130 1.8 V LVT NFET are measured on Entry 96's
two-terminal split bank.  Each ngspice invocation batches all 64 codes so the
full PDK library is parsed once per scale rather than once per row.
"""

from __future__ import annotations

import hashlib
import math
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

from nebula.device.crosscheck import scan_for_silent_failures
from nebula.device.ngspice_runner import ngspice_path
from nebula.device.sky130_runner import NFET_01V8, SPICE_DIR, lib_for_device
from nebula.device.split_tuning_bank import (
    C_ERROR_LIMIT_F,
    C_SWITCH_WIDTHS_UM,
    FREQS_HZ,
    G_ERROR_LIMIT_S,
    L_UM,
    R_SWITCH_WIDTHS_UM,
    SOURCE_V,
    TEMP_C,
    VDD_V,
    BankRow,
    _cap_line,
    _res_line,
    assess as assess_one_scale,
    bank_targets,
    parse_admittance,
)

HERE = Path(__file__).resolve().parent
ENTRY96_PATH = HERE.parent / "experiments" / "split_tuning_bank_results.json"
ENTRY96_SHA256 = "70E73F1A8798AF957BDF36D5275D64218F76A78CF75D451A3354928F327D5582"

LVT_NFET: str = "sky130_fd_pr__nfet_01v8_lvt"
WIDTH_SCALES: tuple[int, ...] = (1, 2, 4, 8, 16, 32)
BASE_C_WIDTHS_UM: tuple[float, ...] = C_SWITCH_WIDTHS_UM
FINGER_W_UM: float = 40.0


def _evidence_check() -> None:
    got = hashlib.sha256(ENTRY96_PATH.read_bytes()).hexdigest().upper()
    if got != ENTRY96_SHA256:
        raise ValueError("Entry 96 result artifact hash mismatch")


def _finger_count(width_um: float) -> int:
    ratio = float(width_um) / FINGER_W_UM
    count = int(round(ratio))
    if count < 1 or not math.isclose(ratio, count, abs_tol=1e-12):
        raise ValueError("LVT width must be a positive multiple of 40 um")
    return count


def _registered_scale(scale: int) -> int:
    value = int(scale)
    if value != scale or value not in WIDTH_SCALES:
        raise ValueError(f"scale must be one of the registered {WIDTH_SCALES}")
    return value


def build_scale_deck(scale: int) -> str:
    """One TT deck containing all 64 codes at one registered LVT scale."""
    scale = _registered_scale(scale)
    _evidence_check()
    targets = bank_targets()
    lib = lib_for_device(LVT_NFET, real_passives=True, section="tt")
    lines = [
        f"* Entry 97 safe LVT bank scale {scale} -- generated",
        f'.lib "{lib.as_posix()}" tt',
        f".temp {TEMP_C:g}",
        f"Vdd vdd 0 {VDD_V:g}",
    ]
    writes: list[str] = []
    for r_code in range(8):
        for c_code in range(8):
            tag = f"r{r_code}_c{c_code}"
            sp, sn, cp, cn = (f"sp_{tag}", f"sn_{tag}",
                              f"cp_{tag}", f"cn_{tag}")
            lines += [
                f"* bank R{r_code} C{c_code}",
                f"Vsp_{tag} {sp} 0 dc {SOURCE_V:g} ac 0.5",
                f"Vsn_{tag} {sn} 0 dc {SOURCE_V:g} ac -0.5",
                f"Vcp_{tag} {cp} 0 dc {SOURCE_V:g} ac 0.5",
                f"Vcn_{tag} {cn} 0 dc {SOURCE_V:g} ac -0.5",
                "* Same-deck separately drawn R || C control.",
                _res_line(f"Xb_{tag}_ctrlr", cp, cn,
                          targets.rs_values_ohm[r_code]),
                _cap_line(f"Xb_{tag}_ctrlc", cp, cn,
                          targets.cs_values_f[c_code]),
                "* Floating resistor bank; Entry 96 topology unchanged.",
                _res_line(f"Xb_{tag}_rfix", sp, sn,
                          targets.rs_values_ohm[7]),
            ]
            r_mask = 7 - r_code
            for bit, (resistance, width) in enumerate(zip(
                    targets.r_branch_drawn_ohm, R_SWITCH_WIDTHS_UM)):
                gate = "vdd" if r_mask & (1 << bit) else "0"
                mid = f"rmid_{tag}_{bit}"
                lines += [
                    _res_line(f"Xb_{tag}_rb{bit}", sp, mid, resistance),
                    f"Xb_{tag}_rsw{bit} {mid} {gate} {sn} 0 {NFET_01V8} "
                    f"W={width:g} L={L_UM:g} nf={_finger_count(width)}",
                ]
            lines += [
                "* Split capacitor; only its selector family/scale changes.",
                _cap_line(f"Xb_{tag}_cfixp", sp, "0",
                          targets.c_fixed_per_side_f),
                _cap_line(f"Xb_{tag}_cfixn", sn, "0",
                          targets.c_fixed_per_side_f),
            ]
            for bit, (capacitance, base_width) in enumerate(zip(
                    targets.c_branch_per_side_f, BASE_C_WIDTHS_UM)):
                gate = "vdd" if c_code & (1 << bit) else "0"
                width = base_width * scale
                for side, node in (("p", sp), ("n", sn)):
                    mid = f"cmid{side}_{tag}_{bit}"
                    lines += [
                        _cap_line(f"Xb_{tag}_cb{side}{bit}", node, mid,
                                  capacitance),
                        f"Xb_{tag}_csw{side}{bit} {mid} {gate} 0 0 "
                        f"{LVT_NFET} W={width:g} L={L_UM:g} "
                        f"nf={_finger_count(width)}",
                    ]
            writes.append(
                f"wrdata adm_{tag}.txt i(Vsp_{tag}) i(Vsn_{tag}) "
                f"i(Vcp_{tag}) i(Vcn_{tag})")
    lines += [
        ".control",
        "set noaskquit",
        "set filetype=ascii",
        f"ac lin 3 {FREQS_HZ[0]:g} {FREQS_HZ[1]:g}",
        *writes,
        "quit",
        ".endc",
        ".end",
    ]
    return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class LvtBankRow:
    scale: int
    r_code: int
    c_code: int
    switched_g_s: tuple[float, float]
    switched_c_f: tuple[float, float]
    control_g_s: tuple[float, float]
    control_c_f: tuple[float, float]

    def to_dict(self) -> dict:
        return asdict(self)

    def as_bank_row(self) -> BankRow:
        return BankRow(
            r_code=self.r_code, c_code=self.c_code,
            switched_g_s=self.switched_g_s,
            switched_c_f=self.switched_c_f,
            control_g_s=self.control_g_s,
            control_c_f=self.control_c_f,
        )


def _row_from_admittance(scale: int, r_code: int, c_code: int,
                         raw: np.ndarray) -> LvtBankRow:
    adm = parse_admittance(raw)

    def values(which: str) -> tuple[tuple[float, float], tuple[float, float]]:
        y = adm[which]
        g = tuple(float(value.real) for value in y)
        c = tuple(float(value.imag) / (2.0 * math.pi * frequency)
                  for value, frequency in zip(y, FREQS_HZ))
        if not all(math.isfinite(x) and x > 0.0 for x in (*g, *c)):
            raise RuntimeError(
                f"scale {scale} R{r_code}C{c_code} {which} invalid: {g}, {c}")
        return g, c

    sw_g, sw_c = values("switched")
    ctrl_g, ctrl_c = values("control")
    return LvtBankRow(
        scale=scale, r_code=r_code, c_code=c_code,
        switched_g_s=sw_g, switched_c_f=sw_c,
        control_g_s=ctrl_g, control_c_f=ctrl_c,
    )


def run_scale(scale: int, timeout_s: float = 240.0) -> list[LvtBankRow]:
    """Run one scale's batched 64-code real-PDK deck."""
    scale = _registered_scale(scale)
    text = build_scale_deck(scale)
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        shutil.copy(SPICE_DIR / ".spiceinit", tmp / ".spiceinit")
        (tmp / "lvt_bank.cir").write_text(text, encoding="ascii", newline="\n")
        try:
            proc = subprocess.run(
                [str(ngspice_path()), "-b", "lvt_bank.cir"], cwd=str(tmp),
                capture_output=True, text=True, timeout=float(timeout_s))
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"LVT scale {scale} timeout >{timeout_s}s") from exc
        out = proc.stdout + "\n" + proc.stderr
        offenders = scan_for_silent_failures(out)
        if offenders:
            raise RuntimeError(f"LVT scale {scale} silent failure: "
                               f"{offenders[0][:240]}")
        rows: list[LvtBankRow] = []
        for r_code in range(8):
            for c_code in range(8):
                path = tmp / f"adm_r{r_code}_c{c_code}.txt"
                if not path.exists() or path.stat().st_size == 0:
                    raise RuntimeError(
                        f"LVT scale {scale} R{r_code}C{c_code} wrote no data; "
                        f"tail: {out[-800:]}")
                rows.append(_row_from_admittance(
                    scale, r_code, c_code, np.loadtxt(path)))
    return rows


def assess(rows: Sequence[LvtBankRow]) -> dict:
    """Apply the frozen Entry 97 L1-L6 gates without fitting a new width."""
    rows = list(rows)
    keys = [(row.scale, row.r_code, row.c_code) for row in rows]
    expected = {(scale, r, c) for scale in WIDTH_SCALES
                for r in range(8) for c in range(8)}
    finite = all(
        len(values) == len(FREQS_HZ)
        and all(math.isfinite(x) and x > 0.0 for x in values)
        for row in rows for values in
        (row.switched_g_s, row.switched_c_f,
         row.control_g_s, row.control_c_f))
    l1 = (len(rows) == 384 and len(set(keys)) == 384
          and set(keys) == expected and finite)

    summaries: list[dict] = []
    if l1:
        for scale in WIDTH_SCALES:
            base_rows = [row.as_bank_row() for row in rows if row.scale == scale]
            one = assess_one_scale(base_rows)
            summaries.append({
                "scale": scale,
                "widths_um": [width * scale for width in BASE_C_WIDTHS_UM],
                "ordered": bool(one["S2"] and one["S3"]),
                "max_g_error_s": float(one["max_g_error_s"]),
                "loss_pass": bool(one["S4"]),
                "max_c_error_f": float(one["max_c_error_f"]),
                "cap_pass": bool(one["S5"]),
            })
    l2 = bool(l1 and all(item["ordered"] for item in summaries))
    l3 = bool(l1 and any(item["loss_pass"] for item in summaries))
    l4 = bool(l1 and any(item["cap_pass"] for item in summaries))
    passing = [item for item in summaries
               if item["ordered"] and item["loss_pass"] and item["cap_pass"]]
    selected = None if not passing else min(item["scale"] for item in passing)
    l5 = selected is not None
    l6 = True
    return {
        "L1_integrity": l1,
        "L2_ordering": l2,
        "L3_any_loss_pass": l3,
        "L4_any_cap_pass": l4,
        "L5_selection": l5,
        "L6_isolation_safety": l6,
        "overall": bool(l1 and l2 and l5 and l6),
        "selected_scale": selected,
        "g_error_limit_s": G_ERROR_LIMIT_S,
        "c_error_limit_f": C_ERROR_LIMIT_F,
        "scale_summary": summaries,
    }


def run_screen(workers: int = 6) -> tuple[list[LvtBankRow], dict]:
    """Run all six frozen scale decks and score the complete 384-row set."""
    import concurrent.futures

    t0 = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=int(workers)) as ex:
        chunks = list(ex.map(run_scale, WIDTH_SCALES))
    rows = [row for chunk in chunks for row in chunk]
    result = assess(rows)
    result["wall_clock_s"] = time.perf_counter() - t0
    return rows, result


__all__ = (
    "ENTRY96_SHA256", "LVT_NFET", "WIDTH_SCALES", "BASE_C_WIDTHS_UM",
    "G_ERROR_LIMIT_S", "C_ERROR_LIMIT_F", "LvtBankRow",
    "build_scale_deck", "run_scale", "assess", "run_screen",
)
