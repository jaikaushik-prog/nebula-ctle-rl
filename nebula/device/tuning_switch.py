"""Real SKY130 selector probe for the source-degeneration R/C bank.

The old bank used separately regenerated passive geometries.  This module
qualifies the missing NMOS selector at the voltage it actually sees, including
its ON impedance and its OFF loading.  It deliberately does not alter the
production CTLE or the frozen RL policy; Entry 95's isolated gates decide
whether a topology is allowed to reach that stage.
"""

from __future__ import annotations

import math
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

from nebula.common.types import all_corners
from nebula.device.crosscheck import scan_for_silent_failures
from nebula.device.ngspice_runner import ngspice_path
from nebula.device.sky130_runner import (
    NFET_01V8,
    SPICE_DIR,
    lib_for_device,
)

WIDTHS_UM: tuple[float, ...] = (40.0, 80.0, 160.0, 320.0, 640.0)
BIASES_V: tuple[float, ...] = (0.44, 0.50, 0.55)
FREQS_HZ: tuple[float, ...] = (1.25e9, 2.5e9)
L_UM: float = 0.15
FINGER_W_UM: float = 40.0

# Entry 95's pre-registered, half-code-step limits.
ONE_HOT_RON_MAX_OHM: float = 2.02
ONE_HOT_COFF_MAX_F: float = 36.22e-15
BINARY_RON_MAX_OHM: float = 5.06
BINARY_COFF_MAX_F: float = 198.0e-15


def finger_count(width_um: float) -> int:
    """Number of 40 um fingers, rejecting an unregistered/model-bin width."""
    ratio = float(width_um) / FINGER_W_UM
    nf = int(round(ratio))
    if nf < 1 or not math.isclose(ratio, nf, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("switch width must be a positive multiple of 40 um")
    return nf


def corner_label(process: str, vdd_scale: float, temp_c: float) -> str:
    return f"{process}/{float(vdd_scale):.2f}/{float(temp_c):g}C"


def _tag(width_um: float, source_v: float) -> str:
    return f"w{int(round(width_um))}_v{int(round(source_v * 1000)):03d}"


def build_deck(process: str, vdd_v: float, temp_c: float,
               widths_um: Sequence[float] = WIDTHS_UM,
               biases_v: Sequence[float] = BIASES_V) -> tuple[str, tuple[str, ...]]:
    """Build one corner deck containing every registered W/source-bias pair."""
    lib = lib_for_device(NFET_01V8, section=process)
    names = tuple(_tag(w, v) for v in biases_v for w in widths_um)
    lines = [
        "* Entry 95 physical tuning-switch probe -- generated",
        f'.lib "{lib.as_posix()}" {process}',
        f".temp {float(temp_c):g}",
        f"Vgate_on gate_on 0 {float(vdd_v):g}",
        "Vdelta delta 0 0 ac 1",
    ]
    for source_v in biases_v:
        for width_um in widths_um:
            name = _tag(width_um, source_v)
            nf = finger_count(width_um)
            lines += [
                f"Vsrc_{name} s_{name} 0 {float(source_v):g}",
                f"Eon_{name} don_{name} s_{name} delta 0 1",
                f"Xon_{name} don_{name} gate_on s_{name} 0 {NFET_01V8} "
                f"W={float(width_um):g} L={L_UM:g} nf={nf}",
                f"Eoff_{name} doff_{name} s_{name} delta 0 1",
                f"Xoff_{name} doff_{name} 0 s_{name} 0 {NFET_01V8} "
                f"W={float(width_um):g} L={L_UM:g} nf={nf}",
            ]
    on_vecs = " ".join(f"i(Eon_{name})" for name in names)
    off_vecs = " ".join(f"i(Eoff_{name})" for name in names)
    lines += [
        ".control",
        "set noaskquit",
        "set filetype=ascii",
        "dc Vdelta 0 0.05 0.001",
        f"wrdata ron.txt {on_vecs}",
        # G164: this ngspice build returns N-1 rows for `ac lin N`.
        # `lin 3` is therefore the two registered endpoints, not a midpoint.
        f"ac lin 3 {FREQS_HZ[0]:g} {FREQS_HZ[1]:g}",
        f"wrdata zon.txt {on_vecs}",
        f"wrdata coff.txt {off_vecs}",
        "quit",
        ".endc",
        ".end",
    ]
    return "\n".join(lines) + "\n", names


def parse_dc_table(raw: np.ndarray, names: Sequence[str]) -> dict[str, float]:
    """Parse real `wrdata`: one `(sweep-x, current)` pair per vector."""
    arr = np.atleast_2d(np.asarray(raw, dtype=float))
    if arr.shape != (51, 2 * len(names)):
        raise ValueError(f"ron.txt has shape {arr.shape}, expected "
                         f"(51, {2 * len(names)})")
    x = arr[:, 0]
    for i in range(len(names)):
        if not np.allclose(arr[:, 2 * i], x, rtol=0.0, atol=1e-15):
            raise ValueError(f"ron.txt x-axis mismatch for {names[i]}")
    fit = (x > 0.005) & (x < 0.045)
    out: dict[str, float] = {}
    for i, name in enumerate(names):
        current = arr[:, 2 * i + 1]
        slope = float(np.polyfit(current[fit], x[fit], 1)[0])
        out[name] = abs(slope)
    return out


def parse_ac_table(raw: np.ndarray,
                   names: Sequence[str]) -> dict[str, tuple[complex, ...]]:
    """Parse complex `wrdata`: one `(frequency, real, imag)` triple/vector."""
    arr = np.atleast_2d(np.asarray(raw, dtype=float))
    expected = (len(FREQS_HZ), 3 * len(names))
    if arr.shape != expected:
        raise ValueError(f"AC table has shape {arr.shape}, expected {expected}")
    f = arr[:, 0]
    if not np.allclose(f, FREQS_HZ, rtol=1e-12, atol=1.0):
        raise ValueError(f"AC frequency axis {tuple(f)} != {FREQS_HZ}")
    out: dict[str, tuple[complex, ...]] = {}
    for i, name in enumerate(names):
        base = 3 * i
        if not np.allclose(arr[:, base], f, rtol=0.0, atol=1.0):
            raise ValueError(f"AC x-axis mismatch for {name}")
        out[name] = tuple(complex(re, im) for re, im in
                          zip(arr[:, base + 1], arr[:, base + 2]))
    return out


@dataclass(frozen=True)
class SwitchRow:
    corner: str
    process: str
    vdd_scale: float
    temp_c: float
    vdd_v: float
    source_v: float
    width_um: float
    nf: int
    ron_ohm: float
    on_z_ohm: tuple[float, float]
    off_cap_f: tuple[float, float]

    def to_dict(self) -> dict:
        return asdict(self)


def measure_corner(process: str, vdd_scale: float, temp_c: float,
                   timeout_s: float = 120.0) -> list[SwitchRow]:
    """Measure all 15 W/bias combinations in one real-PDK invocation."""
    vdd_v = 1.8 * float(vdd_scale)
    text, names = build_deck(process, vdd_v, temp_c)
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        shutil.copy(SPICE_DIR / ".spiceinit", tmp / ".spiceinit")
        (tmp / "switch.cir").write_text(text, encoding="ascii", newline="\n")
        try:
            proc = subprocess.run(
                [str(ngspice_path()), "-b", "switch.cir"], cwd=str(tmp),
                capture_output=True, text=True, timeout=float(timeout_s))
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"switch probe timeout >{timeout_s}s") from exc
        out = proc.stdout + "\n" + proc.stderr
        offenders = scan_for_silent_failures(out)
        if offenders:
            raise RuntimeError(f"ngspice silent failure: {offenders[0][:240]}")
        paths = [tmp / name for name in ("ron.txt", "zon.txt", "coff.txt")]
        missing = [p.name for p in paths if not p.exists() or p.stat().st_size == 0]
        if missing:
            raise RuntimeError(f"ngspice did not write {missing}; tail: {out[-800:]}")
        dc = parse_dc_table(np.loadtxt(paths[0]), names)
        on = parse_ac_table(np.loadtxt(paths[1]), names)
        off = parse_ac_table(np.loadtxt(paths[2]), names)

    rows: list[SwitchRow] = []
    label = corner_label(process, vdd_scale, temp_c)
    for source_v in BIASES_V:
        for width_um in WIDTHS_UM:
            name = _tag(width_um, source_v)
            on_z = tuple(abs(1.0 / i) for i in on[name])
            off_c = tuple(abs(i.imag) / (2.0 * math.pi * f)
                          for i, f in zip(off[name], FREQS_HZ))
            values = (dc[name], *on_z, *off_c)
            if not all(math.isfinite(x) and x > 0.0 for x in values):
                raise RuntimeError(f"non-positive/non-finite switch result "
                                   f"at {label}/{name}: {values}")
            rows.append(SwitchRow(
                corner=label, process=process, vdd_scale=float(vdd_scale),
                temp_c=float(temp_c), vdd_v=vdd_v, source_v=source_v,
                width_um=width_um, nf=finger_count(width_um),
                ron_ohm=dc[name], on_z_ohm=on_z, off_cap_f=off_c))
    return rows


def _expected_keys() -> set[tuple[str, float, float]]:
    return {(corner_label(c.process, c.vdd_scale, c.temp_c), v, w)
            for c in all_corners() for v in BIASES_V for w in WIDTHS_UM}


def assess(rows: Sequence[SwitchRow]) -> dict:
    """Apply Entry 95 P1--P5 without changing thresholds after exposure."""
    keys = [(r.corner, float(r.source_v), float(r.width_um)) for r in rows]
    finite = all(
        r.nf == finger_count(r.width_um)
        and len(r.on_z_ohm) == len(FREQS_HZ)
        and len(r.off_cap_f) == len(FREQS_HZ)
        and all(math.isfinite(x) and x > 0.0
                for x in (r.ron_ohm, *r.on_z_ohm, *r.off_cap_f))
        for r in rows)
    p1 = (len(rows) == 675 and len(set(keys)) == 675
          and set(keys) == _expected_keys() and finite)

    p2 = p1
    if p2:
        by_key = {(r.corner, r.source_v, r.width_um): r for r in rows}
        for corner in {r.corner for r in rows}:
            for bias in BIASES_V:
                ordered = [by_key[(corner, bias, w)] for w in WIDTHS_UM]
                ron = [r.ron_ohm for r in ordered]
                if not all(a > b for a, b in zip(ron, ron[1:])):
                    p2 = False
                for fi in range(len(FREQS_HZ)):
                    cap = [r.off_cap_f[fi] for r in ordered]
                    if not all(a < b for a, b in zip(cap, cap[1:])):
                        p2 = False

    summaries = []
    for width in WIDTHS_UM:
        subset = [r for r in rows if r.width_um == width]
        summaries.append({
            "width_um": width,
            "nf": finger_count(width),
            "worst_ron_ohm": (max((r.ron_ohm for r in subset), default=None)),
            "worst_on_z_ohm": (max((z for r in subset for z in r.on_z_ohm),
                                    default=None)),
            "worst_off_cap_f": (max((c for r in subset for c in r.off_cap_f),
                                     default=None)),
        })

    def topology(name: str, ron_limit: float, cap_limit: float) -> dict:
        passing = [s for s in summaries
                   if p1 and p2 and s["worst_ron_ohm"] <= ron_limit
                   and s["worst_off_cap_f"] <= cap_limit]
        return {"name": name, "ron_limit_ohm": ron_limit,
                "off_cap_limit_f": cap_limit,
                "selected_width_um": (None if not passing else
                                      min(s["width_um"] for s in passing))}

    one_hot = topology("exact-one-hot", ONE_HOT_RON_MAX_OHM,
                       ONE_HOT_COFF_MAX_F)
    binary = topology("three-switch-binary", BINARY_RON_MAX_OHM,
                      BINARY_COFF_MAX_F)
    return {
        "P1_integrity": p1,
        "P2_scaling": p2,
        "P3_one_hot": one_hot["selected_width_um"] is not None,
        "P4_binary": binary["selected_width_um"] is not None,
        "one_hot": one_hot,
        "binary": binary,
        "width_summary": summaries,
    }


def run_probe(workers: int = 8) -> tuple[list[SwitchRow], dict]:
    """Run all 45 registered corners, parallel-safe via temporary decks."""
    import concurrent.futures

    corners = list(all_corners())
    t0 = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=int(workers)) as ex:
        chunks = list(ex.map(
            lambda c: measure_corner(c.process, c.vdd_scale, c.temp_c), corners))
    rows = [row for chunk in chunks for row in chunk]
    result = assess(rows)
    result["wall_clock_s"] = time.perf_counter() - t0
    return rows, result


__all__ = (
    "WIDTHS_UM", "BIASES_V", "FREQS_HZ", "L_UM", "SwitchRow",
    "finger_count", "corner_label", "build_deck", "parse_dc_table",
    "parse_ac_table", "measure_corner", "assess", "run_probe",
)
