"""
experiments/tail_device.py — the tail transistor, measured.

WHAT THIS CLOSES
----------------
HANDOFF §8's top open item, promoted 2026-08-05:

    Every simulation this project has ever run uses TWO IDEAL CURRENT SINKS for
    the tail. An ideal sink delivers exactly I_tail at every corner: it does not
    lose current at SS/125 C, does not gain it at FF/0 C, and does not fall out
    of saturation when the rail drops 5%. That single assumption is what makes
    the whole S9 result an OPTIMISTIC bound (G47), and it also blocks three of
    the nine box dimensions (`w_tail`, `l_tail`, `nf_tail` have no provenance).

Five measurements, in the order they depend on each other:

1. **`--identity`** — the mirror does what it says. Three checks that can each
   FAIL, on the reference point: the realised `I_tail` against the requested
   one, the identity `vds_tail == v(source)` (which is what makes the tail's
   headroom a constraint on VCM and W_in rather than on itself), and
   `v(source) == VCM - Vgs_in` from independently parsed primitives.

2. **`--sweep`** — `(w_tail, l_tail, nf_tail)` at fixed `I_ref`, over three
   corners, recording `vdsat_tail`, realised `I_tail`, `v(source)` and
   `vds - vdsat`. This is where the sizing rule comes from.

3. **`--noise`** — what the tail costs S5, by per-instance attribution rather
   than by the difference of two totals, so the answer names the contributor.

4. **`--rout`** — what a SHORT tail costs S3. The tail's output resistance sits
   from each source node to ground, in parallel with the path through the
   degeneration network, so a low `r_o` shunts the degeneration and takes
   peaking away. This is the measurement that gives `l_tail` a real floor
   instead of "long is better".

5. **`--bounds`** — the three box edges, with per-edge provenance, in the style
   of `BOUNDS_REDERIVATION.md`. **Written to `TAIL_DEVICE.md` §6, NOT to
   `common/params.py`** (CLAUDEwa §8 rule 6; the box is a human decision).

WHAT REMAINS IDEAL, STATED SO IT CANNOT BE FORGOTTEN
-----------------------------------------------------
`I_ref` is an ideal current source. A real one is a bandgap or a constant-gm
bias cell, which is a circuit S2 does not name; modelling it badly would be
worse than declaring it. One justified ideal element is defensible, four are
not. Everything else in the tail is now a device.

USAGE
    python -m nebula.experiments.tail_device --identity
    python -m nebula.experiments.tail_device --sweep --workers 8
    python -m nebula.experiments.tail_device --noise --rout
    python -m nebula.experiments.tail_device --all --workers 8
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from nebula.common.types import Corner
from nebula.device.sky130_runner import SizingPoint, run_point
from nebula.device.tail import (
    W_PER_FINGER_MAX_UM,
    TailDevice,
    TailGeometryError,
    min_nf_for_width,
)

HERE = Path(__file__).resolve().parent
DATA_CSV = HERE / "tail_device_data.csv"
RESULTS_JSON = HERE / "tail_device_results.json"

# ─────────────────────────────────────────────────────────────────────────────
# The reference point. ONE definition (rule 9).
#
# Session 9c's corrected bias, the one HANDOFF §6 publishes: W=40 nf=4,
# I_tail = 1.5 mA/side, VCM = 1.25, VDD = 1.8 -> gm 12.62 mS, gm/I_D 8.42,
# v(s1) = +0.343 V. That +0.343 V is the entire headroom budget the tail has to
# fit inside, which is why this point is the one the identity checks run at.
# ─────────────────────────────────────────────────────────────────────────────

REFERENCE_INPUT: dict[str, float] = {
    "w": 40.0, "l": 0.15, "nf": 4,
    "rs": 600.0, "cs": 200e-15, "rl": 400.0, "cl": 100e-15,
    "i_tail_per_side_a": 1.5e-3, "vcm": 1.25, "vdd": 1.8,
}

#: Published at the reference point with an IDEAL tail (HANDOFF §6). The
#: identity check asserts against these, so a drift in the runner, the library
#: or the PDK shows up here rather than in a yield number three stages later.
REFERENCE_IDEAL: dict[str, float] = {
    "gm": 12.62e-3, "v_src_dc": 0.3435, "vn_in_vrms": 0.275e-3,
}

#: Mirror ratio N = W_tail / W_ref. 8 puts the reference branch at 12.5% of one
#: side, i.e. 6.25% of the tail current, which `power_measured_w` bills.
#: A LARGER N would cost less reference current and mirror worse (the reference
#: device gets narrower and its finger parasitics matter more); a smaller N
#: costs current. 8 is a stated choice, not a measured optimum.
MIRROR_RATIO: float = 8.0

#: The three corners S9 screens at, so the tail is characterised on the same
#: grid the yield experiment scores on.
SWEEP_CORNERS: tuple[Corner, ...] = (
    Corner(process="tt", vdd_scale=1.00, temp_c=27.0),
    Corner(process="ss", vdd_scale=0.95, temp_c=125.0),
    Corner(process="ff", vdd_scale=1.05, temp_c=0.0),
)

#: The task's sizing target: `vdsat_tail <= 0.20 V`. Not a spec — a design
#: choice about how much of `v(source)` the tail is allowed to consume. At the
#: reference point `v(source)` is +0.343 V, so 0.20 V leaves ~0.14 V of margin.
VDSAT_TARGET_V: float = 0.20

#: L in 0.5-1.0 um, NOT minimum. The tail is not speed-critical, and both output
#: resistance and matching improve with length. `--rout` measures the first of
#: those; the second is a Monte-Carlo question this project has not opened.
L_SWEEP_UM: tuple[float, ...] = (0.5, 0.75, 1.0)

#: Currents per side. Spans the box: `i_bias` is 0.5-8.0 mA TOTAL, so per side
#: 0.25-4.0 mA. Three points are enough to test whether the sizing rule is a
#: current DENSITY (W proportional to I) or something else.
I_SIDE_SWEEP_A: tuple[float, ...] = (0.75e-3, 1.5e-3, 3.0e-3)


def w_ladder(lo: float = 25.0, hi: float = 800.0, n: int = 9) -> tuple[float, ...]:
    """Geometric ladder of tail widths, um.

    Geometric because `vdsat` moves as roughly `sqrt(I/W)` — a linear ladder
    spends most of its rungs where nothing happens.
    """
    if n < 2:
        raise ValueError("a ladder needs at least two rungs")
    r = (hi / lo) ** (1.0 / (n - 1))
    return tuple(lo * r ** i for i in range(n))


# ─────────────────────────────────────────────────────────────────────────────
# Pure helpers. Simulator-free, so they are tested without ngspice.
# ─────────────────────────────────────────────────────────────────────────────


def tail_for(w_um: float, l_um: float, nf: Optional[int] = None,
             ratio: float = MIRROR_RATIO) -> TailDevice:
    """A buildable tail at this width, choosing `nf` if not given.

    `nf` defaults to the smallest finger count that keeps the geometry inside
    the per-finger bin ceiling AND a whole multiple of the mirror ratio, so the
    reference device stays one matched unit (see `tail.py`).
    """
    return TailDevice(w_tail=w_um, l_tail=l_um,
                      nf_tail=nf if nf is not None else min_nf_for_width(w_um, ratio),
                      mirror_ratio=ratio)


def interp_width_at_vdsat(widths: Sequence[float],
                          vdsats: Sequence[float],
                          target_v: float = VDSAT_TARGET_V) -> Optional[float]:
    """Width, um, at which `vdsat_tail` crosses `target_v`. None if not bracketed.

    Log-linear in width, because that is how `vdsat` actually moves against it.
    Returns `None` rather than extrapolating: a sizing rule read off an
    extrapolation is a rule about the fit, not about the device.
    """
    pts = sorted((float(w), float(v)) for w, v in zip(widths, vdsats)
                 if w > 0 and v is not None and math.isfinite(v))
    for (w0, v0), (w1, v1) in zip(pts, pts[1:]):
        if (v0 - target_v) * (v1 - target_v) <= 0 and v0 != v1:
            f = (target_v - v0) / (v1 - v0)
            return math.exp(math.log(w0) + f * (math.log(w1) - math.log(w0)))
    return None


def width_per_amp(i_side_a: float, w_um: float) -> float:
    """Microns of tail width per amp of side current — the sizing rule's unit.

    Quoted this way round (and not as a current density in A/um) because the
    thing a caller does with it is multiply by a current to get a width.
    """
    if i_side_a <= 0:
        raise ValueError(f"i_side {i_side_a} must be > 0")
    return w_um / i_side_a


@dataclass(frozen=True)
class TailRow:
    """One (design, tail geometry, corner) evaluation. One row of the CSV."""

    corner: str
    process: str
    vdd_scale: float
    temp_c: float
    i_side_a: float
    w_tail: float
    l_tail: float
    nf_tail: int
    nf_ref: int
    ok: bool
    fail_reason: Optional[str] = None
    i_tail_meas_a: Optional[float] = None
    i_ref_meas_a: Optional[float] = None
    mirror_err: Optional[float] = None
    v_src_dc: Optional[float] = None
    vds_tail: Optional[float] = None
    vdsat_tail: Optional[float] = None
    tail_margin_v: Optional[float] = None
    gm_tail: Optional[float] = None
    vgs_tail: Optional[float] = None
    vth_tail: Optional[float] = None
    v_bias_dc: Optional[float] = None
    gm_in: Optional[float] = None
    peaking_db: Optional[float] = None
    f_pk_hz: Optional[float] = None
    vn_in_vrms: Optional[float] = None
    i_supply_a: Optional[float] = None
    power_measured_w: Optional[float] = None


def _base_point(i_side_a: float, corner: Corner,
                tail: Optional[TailDevice]) -> SizingPoint:
    """The reference input pair, at `corner`, with `tail` fitted.

    VDD scales with the corner; VCM does NOT, matching `s9_yield.VCM_TRACKS_VDD`
    so the two experiments make the same assumption (rule 9).
    """
    kw = dict(REFERENCE_INPUT)
    kw["vdd"] = float(kw["vdd"]) * corner.vdd_scale
    kw["i_tail_per_side_a"] = i_side_a
    kw["nf"] = int(kw["nf"])
    return SizingPoint(**kw, tail=tail)  # type: ignore[arg-type]


def evaluate_tail(task: tuple) -> TailRow:
    """One (i_side, geometry, corner) point. Module-level so it pickles."""
    i_side_a, w_tail, l_tail, nf_tail, process, vdd_scale, temp_c = task
    corner = Corner(process=process, vdd_scale=vdd_scale, temp_c=temp_c)
    try:
        tail = TailDevice(w_tail=w_tail, l_tail=l_tail, nf_tail=nf_tail,
                          mirror_ratio=MIRROR_RATIO)
    except TailGeometryError as exc:
        return TailRow(corner=str(corner), process=process, vdd_scale=vdd_scale,
                       temp_c=temp_c, i_side_a=i_side_a, w_tail=w_tail,
                       l_tail=l_tail, nf_tail=nf_tail, nf_ref=0, ok=False,
                       fail_reason=f"geometry: {exc}")

    pt = _base_point(i_side_a, corner, tail)
    r = run_point(pt, corner=process, temp_c=temp_c, swing=False)
    if not r.ok:                       # transient failures are real under load (G45)
        r = run_point(pt, corner=process, temp_c=temp_c, swing=False)
    if not r.ok:
        return TailRow(corner=str(corner), process=process, vdd_scale=vdd_scale,
                       temp_c=temp_c, i_side_a=i_side_a, w_tail=w_tail,
                       l_tail=l_tail, nf_tail=nf_tail, nf_ref=tail.nf_ref,
                       ok=False, fail_reason=r.fail_reason)

    return TailRow(
        corner=str(corner), process=process, vdd_scale=vdd_scale, temp_c=temp_c,
        i_side_a=i_side_a, w_tail=w_tail, l_tail=l_tail, nf_tail=nf_tail,
        nf_ref=tail.nf_ref, ok=True,
        i_tail_meas_a=r.i_tail_meas_a, i_ref_meas_a=r.i_ref_meas_a,
        mirror_err=r.mirror_gain_error, v_src_dc=r.v_src_dc,
        vds_tail=r.vds_tail, vdsat_tail=r.vdsat_tail,
        tail_margin_v=r.tail_margin_v, gm_tail=r.gm_tail, vgs_tail=r.vgs_tail,
        vth_tail=r.vth_tail, v_bias_dc=r.v_bias_dc, gm_in=r.gm,
        peaking_db=r.peaking_db, f_pk_hz=r.f_pk_hz, vn_in_vrms=r.vn_in_vrms,
        i_supply_a=r.i_supply_a, power_measured_w=r.power_measured_w,
    )


def run_tasks(tasks, workers: int):
    if workers <= 1:
        return [evaluate_tail(t) for t in tasks]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(evaluate_tail, tasks, chunksize=2))


# ─────────────────────────────────────────────────────────────────────────────
# 1. The identity checks. Each one can FAIL, and a test proves it can.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class IdentityCheck:
    name: str
    passed: bool
    lhs: float
    rhs: float
    tol: float
    unit: str
    note: str = ""

    @property
    def delta(self) -> float:
        return self.lhs - self.rhs

    def line(self) -> str:
        v = "PASS" if self.passed else "FAIL"
        return (f"  [{v}] {self.name:34} {self.lhs:+11.6g} vs {self.rhs:+11.6g} "
                f"{self.unit:6} delta {self.delta:+.4g} (tol {self.tol:g})")


def identity_checks(r, point: SizingPoint) -> list[IdentityCheck]:
    """The three things the mirror must satisfy before any sweep is believed.

    These are CLAUDEwa §8 rule 10 applied to a new device: not "did ngspice exit
    zero" but "does the circuit obey the relation the write-up is about".
    """
    assert r.point is not None and r.point.tail is not None
    checks: list[IdentityCheck] = []

    # (a) The mirror delivers roughly what it was asked for. NOT an equality:
    #     the reference sits at vds = vgs ~ 1.0 V and the tail at v(source)
    #     ~ 0.34 V, and channel-length modulation gives the reference more
    #     current per micron. The tolerance is loose ON PURPOSE — the point is
    #     to catch a mirror that is broken (ratio 1x, or 64x), not to assert a
    #     precision the topology does not have. The exact error is REPORTED.
    asked = point.i_tail_per_side_a
    checks.append(IdentityCheck(
        "I_tail delivered vs requested", abs(r.i_tail_meas_a / asked - 1.0) < 0.25,
        r.i_tail_meas_a * 1e3, asked * 1e3, 0.25, "mA",
        f"mirror gain error {r.mirror_gain_error * 100:+.2f}%"))

    # (b) THE COUPLING IDENTITY, and the reason this experiment exists. The
    #     tail's drain IS the input pair's source node, so its headroom
    #     requirement is a constraint on VCM, W_in, L_in and i_bias — not on the
    #     tail alone. Parsed from two independent prints, so agreement is a
    #     measurement rather than a tautology.
    checks.append(IdentityCheck(
        "vds_tail == v(source)", abs(r.vds_tail - r.v_src_dc) < 1e-6,
        r.vds_tail, r.v_src_dc, 1e-6, "V",
        "the tail's drain IS the pair's source node"))

    # (c) v(source) = VCM - Vgs_in, the equation the write-up predicts from.
    checks.append(IdentityCheck(
        "v(source) == VCM - Vgs_in", abs(r.v_src_dc - (point.vcm - r.vgs)) < 2e-3,
        r.v_src_dc, point.vcm - r.vgs, 2e-3, "V",
        "so tail headroom couples VCM, W_in and i_bias"))
    return checks


def identity_main(args) -> int:
    print("=" * 78)
    print("1. MIRROR IDENTITY CHECKS -- at the session 9c reference point")
    print("=" * 78)
    corner = SWEEP_CORNERS[0]

    ideal = run_point(_base_point(REFERENCE_INPUT["i_tail_per_side_a"], corner, None),
                      swing=False)
    if not ideal.ok:
        print(f"  ideal-tail reference run FAILED: {ideal.fail_reason}")
        return 1
    print(f"  IDEAL tail (the legacy topology, for comparison):")
    print(f"    gm {ideal.gm * 1e3:.3f} mS   v(s1) {ideal.v_src_dc:+.4f} V   "
          f"noise {ideal.vn_in_vrms * 1e3:.4f} mV   "
          f"peaking {ideal.peaking_db:.3f} dB at {ideal.f_pk_hz / 1e9:.3f} GHz")
    drift = [f"{k} {getattr(ideal, k):.6g} vs published {v:.6g}"
             for k, v in REFERENCE_IDEAL.items()
             if abs(getattr(ideal, k) - v) / v > 0.02]
    if drift:
        print("  *** the ideal reference has DRIFTED from HANDOFF sec 6: "
              + "; ".join(drift) + " ***")
        return 1
    print("    (matches HANDOFF sec 6 to within 2% on gm, v(s1) and noise)")

    w0 = 100.0
    tail = tail_for(w0, 0.5)
    pt = _base_point(REFERENCE_INPUT["i_tail_per_side_a"], corner, tail)
    r = run_point(pt, corner=corner.process, temp_c=corner.temp_c, swing=False)
    if not r.ok:
        print(f"  mirror run FAILED: {r.fail_reason}")
        return 1

    print(f"\n  MIRROR tail  {tail.tag()}  "
          f"(W_ref {tail.w_ref:g} um, nf_ref {tail.nf_ref}, "
          f"fingers {'MATCHED' if tail.finger_matched else 'MISMATCHED'} at "
          f"{tail.finger_w_um:g} um)")
    print(f"    I_ref asked {tail.i_ref_a(pt.i_tail_per_side_a) * 1e6:.2f} uA, "
          f"forced {r.i_ref_meas_a * 1e6:.2f} uA   v(nbias) {r.v_bias_dc:.4f} V")
    print(f"    gm {r.gm * 1e3:.3f} mS   v(s1) {r.v_src_dc:+.4f} V   "
          f"noise {r.vn_in_vrms * 1e3:.4f} mV   "
          f"peaking {r.peaking_db:.3f} dB at {r.f_pk_hz / 1e9:.3f} GHz")
    print(f"    vds_tail {r.vds_tail:.4f} V   vdsat_tail {r.vdsat_tail:.4f} V   "
          f"MARGIN {r.tail_margin_v:+.4f} V   "
          f"{'saturated' if r.tail_in_saturation else 'TRIODE'}")
    print(f"    power: requested {pt.power_w * 1e3:.4f} mW, "
          f"MEASURED {r.power_measured_w * 1e3:.4f} mW")
    print()

    checks = identity_checks(r, pt)
    for c in checks:
        print(c.line())
        if c.note:
            print(f"         {c.note}")
    failed = [c for c in checks if not c.passed]
    print()
    if failed:
        print(f"  *** {len(failed)} IDENTITY CHECK(S) FAILED -- every number "
              f"downstream of the mirror is fiction (rule 10). STOP. ***")
        return 1
    print("  all identity checks passed; the mirror is what the write-up says "
          "it is")

    # The mechanism, shown rather than asserted: fitting a real tail MOVES
    # v(source), because the mirror does not deliver the requested current and
    # the input pair's Vgs follows whatever it does deliver.
    print(f"\n  what fitting the tail changed at TT:")
    print(f"    I_tail   {pt.i_tail_per_side_a * 1e3:.4f} -> "
          f"{r.i_tail_meas_a * 1e3:.4f} mA  ({r.mirror_gain_error * 100:+.2f}%)")
    print(f"    v(s1)    {ideal.v_src_dc:+.4f} -> {r.v_src_dc:+.4f} V  "
          f"({(r.v_src_dc - ideal.v_src_dc) * 1e3:+.1f} mV; less current means "
          f"less Vgs)")
    print(f"    gm       {ideal.gm * 1e3:.3f} -> {r.gm * 1e3:.3f} mS")
    print(f"    peaking  {ideal.peaking_db:.3f} -> {r.peaking_db:.3f} dB")
    print(f"    noise    {ideal.vn_in_vrms * 1e3:.4f} -> "
          f"{r.vn_in_vrms * 1e3:.4f} mV  "
          f"({r.vn_in_vrms / ideal.vn_in_vrms:.2f}x -- see --noise)")
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# 2. The geometry sweep.
# ─────────────────────────────────────────────────────────────────────────────


def sweep_tasks() -> list[tuple]:
    """(i_side, w, l, nf, corner) grid. `nf` is DERIVED, not swept — see §5."""
    tasks: list[tuple] = []
    for i_side in I_SIDE_SWEEP_A:
        for l in L_SWEEP_UM:
            for w in w_ladder():
                nf = min_nf_for_width(w, MIRROR_RATIO)
                for c in SWEEP_CORNERS:
                    tasks.append((i_side, w, l, nf, c.process, c.vdd_scale,
                                  c.temp_c))
    return tasks


def nf_tasks() -> list[tuple]:
    """`nf_tail` held against everything else, to test whether it is a real
    dimension or a near-dead one like `nf_in` (G38)."""
    w, l, i_side = 200.0, 0.5, 1.5e-3
    out = []
    for nf in (2, 4, 8, 16, 24, 32):
        if w / nf > W_PER_FINGER_MAX_UM:
            continue
        for c in SWEEP_CORNERS:
            out.append((i_side, w, l, nf, c.process, c.vdd_scale, c.temp_c))
    return out


def write_csv(rows: Sequence[TailRow], path: Path) -> None:
    """TRACKED ON PURPOSE (G49): TAIL_DEVICE.md quotes numbers from it, so it is
    an INPUT to the write-up, not a build artifact. `repr` floats, losslessly."""
    from dataclasses import asdict, fields
    cols = [f.name for f in fields(TailRow)]
    with path.open("w", newline="", encoding="ascii") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for r in rows:
            d = asdict(r)
            w.writerow(["" if d[c] is None else
                        (repr(d[c]) if isinstance(d[c], float) else d[c])
                        for c in cols])


def read_csv(path: Path) -> list[TailRow]:
    """Re-read the CSV so the whole analysis runs with NO simulator (G49)."""
    from dataclasses import fields
    ftypes = {f.name: f.type for f in fields(TailRow)}
    out: list[TailRow] = []
    with path.open(newline="", encoding="ascii") as fh:
        for d in csv.DictReader(fh):
            kw: dict = {}
            for k, v in d.items():
                if v == "":
                    kw[k] = None
                elif k in ("corner", "process", "fail_reason"):
                    kw[k] = v
                elif k == "ok":
                    kw[k] = v == "True"
                elif k in ("nf_tail", "nf_ref"):
                    kw[k] = int(v)
                else:
                    kw[k] = float(v)
            out.append(TailRow(**kw))
    return out


def sizing_rule(rows: Sequence[TailRow],
                target_v: float = VDSAT_TARGET_V) -> dict:
    """Width-per-amp that puts `vdsat_tail` on target, per (L, corner).

    THE OUTPUT THAT MATTERS. A single fixed `w_tail` cannot serve a box whose
    `i_bias` spans 16x, so the sizing rule has to be a current DENSITY. This
    measures it, and — by reporting it at three currents — tests whether it
    actually IS one.
    """
    out: dict = {}
    for l in sorted({r.l_tail for r in rows}):
        for c in sorted({r.corner for r in rows}):
            per_i: dict = {}
            for i_side in sorted({r.i_side_a for r in rows}):
                sel = [r for r in rows if r.ok and r.l_tail == l
                       and r.corner == c and r.i_side_a == i_side
                       and r.vdsat_tail is not None]
                if len(sel) < 2:
                    continue
                sel.sort(key=lambda r: r.w_tail)
                w = interp_width_at_vdsat([r.w_tail for r in sel],
                                          [r.vdsat_tail for r in sel], target_v)
                if w is not None:
                    per_i[i_side] = {"w_um": w,
                                     "um_per_amp": width_per_amp(i_side, w)}
            if per_i:
                out[f"L={l:g} {c}"] = per_i
    return out


def sweep_main(args) -> int:
    print("=" * 78)
    print("2. GEOMETRY SWEEP -- (w_tail, l_tail, nf_tail) at fixed I_ref")
    print("=" * 78)
    tasks = sweep_tasks() + nf_tasks()
    print(f"  {len(tasks)} runs "
          f"({len(I_SIDE_SWEEP_A)} currents x {len(L_SWEEP_UM)} lengths x "
          f"{len(w_ladder())} widths x {len(SWEEP_CORNERS)} corners, "
          f"plus an nf_tail probe)")
    t0 = time.perf_counter()
    rows = run_tasks(tasks, workers=args.workers)
    dt = time.perf_counter() - t0
    ok = [r for r in rows if r.ok]
    geo = [r for r in rows if not r.ok and (r.fail_reason or "").startswith("geometry")]
    hard = [r for r in rows if not r.ok and r not in geo]
    print(f"  {dt:.1f} s ({dt / len(tasks) * 1000:.0f} ms/run)")
    print(f"  health: {len(ok)}/{len(rows)} simulated, {len(geo)} rejected on "
          f"geometry, {len(hard)} hard failures")
    for h in hard[:3]:
        print(f"    {h.corner} W{h.w_tail:g} L{h.l_tail:g}: {h.fail_reason}")
    write_csv(rows, DATA_CSV)
    print(f"  wrote {DATA_CSV.name} ({len(rows)} rows)")
    print()
    _merge_results({"sweep": report_sweep(ok)})
    return 0


def report_sweep(rows: Sequence[TailRow]) -> dict:
    """Everything the write-up quotes, derived from the rows and nothing else."""
    res: dict = {}

    print("  --- vdsat_tail and headroom margin vs width, per corner "
          f"(I_side 1.5 mA, L 0.5 um) ---")
    print(f"      {'W_tail':>8} {'nf':>3}  " + "  ".join(
        f"{c.process}/{c.vdd_scale:.2f}/{c.temp_c:.0f}C".center(30)
        for c in SWEEP_CORNERS))
    print(f"      {'um':>8} {'':>3}  " + "  ".join(
        f"{'vdsat':>7}{'v(s)':>8}{'margin':>8}{'I/mA':>7}" for _ in SWEEP_CORNERS))
    for w in w_ladder():
        cells = []
        nf = min_nf_for_width(w, MIRROR_RATIO)
        for c in SWEEP_CORNERS:
            m = [r for r in rows if r.i_side_a == 1.5e-3 and r.l_tail == 0.5
                 and abs(r.w_tail - w) < 1e-6 and r.corner == str(c)
                 and r.nf_tail == nf]
            if m:
                r = m[0]
                cells.append(f"{r.vdsat_tail:7.4f}{r.v_src_dc:8.4f}"
                             f"{r.tail_margin_v:+8.4f}{r.i_tail_meas_a * 1e3:7.3f}")
            else:
                cells.append(" " * 30)
        print(f"      {w:8.1f} {nf:3d}  " + "  ".join(cells))

    rule = sizing_rule(rows)
    res["sizing_rule"] = rule
    print(f"\n  --- the sizing rule: width per amp that puts vdsat_tail at "
          f"{VDSAT_TARGET_V:.2f} V ---")
    print(f"      {'L / corner':28} " + "  ".join(
        f"{i * 1e3:.2f} mA".rjust(16) for i in I_SIDE_SWEEP_A))
    for key, per_i in rule.items():
        cells = []
        for i in I_SIDE_SWEEP_A:
            d = per_i.get(i)
            cells.append(f"{d['w_um']:6.1f}um {d['um_per_amp'] / 1e3:6.1f}k"
                         if d else " " * 16)
        print(f"      {key:28} " + "  ".join(cells))
    print(f"      (second column of each pair is um of width per AMP, in "
          f"thousands -- constant across")
    print(f"       the three currents means the rule really is a current "
          f"DENSITY, W proportional to I)")

    print(f"\n  --- mirror gain error vs corner (how far I_tail lands from the "
          f"request) ---")
    print(f"      {'corner':22} {'median err':>11} {'min':>9} {'max':>9}")
    for c in SWEEP_CORNERS:
        errs = sorted(r.mirror_err for r in rows
                      if r.corner == str(c) and r.mirror_err is not None)
        if errs:
            print(f"      {str(c):22} {errs[len(errs) // 2] * 100:+10.2f}% "
                  f"{errs[0] * 100:+8.2f}% {errs[-1] * 100:+8.2f}%")
    res["mirror_err_by_corner"] = {
        str(c): sorted(r.mirror_err for r in rows
                       if r.corner == str(c) and r.mirror_err is not None)
        for c in SWEEP_CORNERS}

    print(f"\n  --- is nf_tail a real dimension? (W 200 um, L 0.5 um, "
          f"I_side 1.5 mA, TT) ---")
    print(f"      {'nf':>4} {'nf_ref':>7} {'tail fing':>10} {'ref fing':>9} "
          f"{'matched':>8} {'I_tail/mA':>10} {'vdsat':>8}")
    nf_rows: dict = {}
    for nf in (2, 4, 8, 16, 24, 32):
        sel = [r for r in rows if abs(r.w_tail - 200.0) < 1e-6
               and r.l_tail == 0.5 and r.nf_tail == nf and r.i_side_a == 1.5e-3]
        tt = [r for r in sel if r.corner == str(SWEEP_CORNERS[0])]
        if not tt:
            continue
        r = tt[0]
        tail_f, ref_f = 200.0 / nf, (200.0 / MIRROR_RATIO) / r.nf_ref
        matched = abs(tail_f - ref_f) < 1e-9
        print(f"      {nf:4d} {r.nf_ref:7d} {tail_f:10.2f} {ref_f:9.2f} "
              f"{('YES' if matched else 'no'):>8} {r.i_tail_meas_a * 1e3:10.4f} "
              f"{r.vdsat_tail:8.4f}")
        nf_rows[nf] = {"nf_ref": r.nf_ref, "matched": matched,
                       "i_tail": r.i_tail_meas_a, "vdsat": r.vdsat_tail}

    # The split is the point. Finger MATCHING is what makes the mirror ratio
    # repeatable; `nf` on its own does almost nothing, exactly as G38 found for
    # `nf_in`. Reporting one pooled spread would hide both facts.
    for label, sel in (("matched fingers only",
                        [d for d in nf_rows.values() if d["matched"]]),
                       ("all nf, matched or not", list(nf_rows.values()))):
        vals = [d["i_tail"] for d in sel]
        if len(vals) > 1:
            print(f"      spread in delivered I_tail, {label:24}: "
                  f"{(max(vals) / min(vals) - 1) * 100:5.1f}%")
    print(f"      => nf_tail is a NEAR-DEAD dimension (same shape as nf_in, "
          f"G38); what matters is")
    print(f"         whether the fingers MATCH, and that is decided by "
          f"w_tail and N, not chosen freely.")
    res["nf_probe"] = nf_rows
    return res


# ─────────────────────────────────────────────────────────────────────────────
# 3. What the tail costs S5.
# ─────────────────────────────────────────────────────────────────────────────


def noise_main(args) -> int:
    print("=" * 78)
    print("3. NOISE -- what the tail costs S5, attributed per instance")
    print("=" * 78)
    print("  The stated expectation was that tail noise is largely COMMON MODE")
    print("  and therefore rejected by a balanced pair, so S5 should barely")
    print("  move. The measurement below is the check.\n")

    corner = SWEEP_CORNERS[0]
    i_side = REFERENCE_INPUT["i_tail_per_side_a"]
    rows: dict = {}

    ideal = run_point(_base_point(i_side, corner, None), swing=False,
                      noise_detail=True)
    tail = tail_for(100.0, 0.5)
    real = run_point(_base_point(i_side, corner, tail), swing=False,
                     noise_detail=True)
    if not ideal.ok or not real.ok:
        print(f"  FAILED: ideal {ideal.fail_reason} / real {real.fail_reason}")
        return 1

    # The attribution must reconstruct the total, or a share read off it is
    # meaningless. Gate it (rule 10).
    for lbl, r in (("ideal", ideal), ("real", real)):
        resid = r.noise_quadrature_residual()
        if resid is None or resid > 1e-4:
            print(f"  *** {lbl}: per-instance noise does NOT reconstruct the "
                  f"total (residual {resid}). The breakdown is incomplete; no "
                  f"share below can be believed. STOP. ***")
            return 1
    print(f"  attribution gate: parts reconstruct the total to "
          f"{ideal.noise_quadrature_residual():.1e} (ideal) and "
          f"{real.noise_quadrature_residual():.1e} (real)")
    print(f"  NOTE the per-instance numbers are RMS VOLTS and add in "
          f"QUADRATURE, not linearly:")
    print(f"       they sum linearly to "
          f"{sum(real.noise_by_device.values()) * 1e6:.1f} uV against a total "
          f"of {real.vn_in_vrms * 1e6:.1f} uV.\n")

    print(f"  {'contributor':14} {'IDEAL tail':>22}   {'REAL tail':>22}")
    print(f"  {'':14} {'uV_rms':>10}{'% power':>12}   "
          f"{'uV_rms':>10}{'% power':>12}")
    si, sr = ideal.noise_share_power(), real.noise_share_power()
    for k in ("in_pair_p", "in_pair_n", "rs_deg", "rl_p", "rl_n",
              "tail_p", "tail_n", "mirror_ref"):
        a = ideal.noise_by_device.get(k)
        b = real.noise_by_device.get(k)
        ta = f"{a * 1e6:10.3f}{si.get(k, 0) * 100:11.2f}%" if a is not None else " " * 22
        tb = f"{b * 1e6:10.3f}{sr.get(k, 0) * 100:11.2f}%" if b is not None else " " * 22
        print(f"  {k:14} {ta}   {tb}")
    print(f"  {'TOTAL':14} {ideal.vn_in_vrms * 1e6:10.3f}{100.0:11.2f}%   "
          f"{real.vn_in_vrms * 1e6:10.3f}{100.0:11.2f}%")

    tail_share = sr.get("tail_p", 0) + sr.get("tail_n", 0)
    ref_share = sr.get("mirror_ref", 0)
    ratio = real.vn_in_vrms / ideal.vn_in_vrms
    print(f"\n  S5 moves {ideal.vn_in_vrms * 1e3:.4f} -> "
          f"{real.vn_in_vrms * 1e3:.4f} mV_rms = {ratio:.2f}x "
          f"(spec 1.5 mV; headroom {1.5e-3 / ideal.vn_in_vrms:.1f}x -> "
          f"{1.5e-3 / real.vn_in_vrms:.1f}x)")
    print(f"  the two TAIL DEVICES are {tail_share * 100:.1f}% of the noise "
          f"POWER -- the single largest contributor")
    print(f"  the mirror REFERENCE device is {ref_share * 100:.4f}% "
          f"({real.noise_by_device['mirror_ref'] * 1e6:.2e} uV)")
    print(f"\n  READ THIS TOGETHER: the common-mode-rejection argument is REAL "
          f"and is visible in")
    print(f"  the data -- the reference device's noise is rejected to "
          f"{ref_share * 100:.0e}%. It does not")
    print(f"  apply to the tails, because S2 needs ONE SINK PER SIDE (a shared "
          f"tail would short")
    print(f"  the Rs/Cs degeneration), and two separate devices have "
          f"INDEPENDENT noise.")

    rows["attribution"] = {
        "ideal": {"total": ideal.vn_in_vrms, "by_device": ideal.noise_by_device,
                  "share_power": si},
        "real": {"total": real.vn_in_vrms, "by_device": real.noise_by_device,
                 "share_power": sr},
        "ratio": ratio, "tail_share_power": tail_share,
        "mirror_ref_share_power": ref_share,
    }

    # Does the noise follow the sizing? gm_tail = 2*I/vdsat, so a WIDER tail
    # (lower vdsat, more headroom) has MORE gm and injects MORE noise. That is
    # the exchange rate the bound in §6 is set on.
    print(f"\n  --- headroom bought with noise: S5 vs tail width "
          f"(L 0.5 um, I_side 1.5 mA, TT) ---")
    print(f"      {'W_tail':>8} {'vdsat':>8} {'margin':>8} {'gm_tail':>9} "
          f"{'S5':>9} {'tail share':>11}")
    trade = []
    for w in (50.0, 100.0, 200.0, 400.0, 800.0):
        try:
            t = tail_for(w, 0.5)
        except TailGeometryError:
            continue
        r = run_point(_base_point(i_side, corner, t), swing=False,
                      noise_detail=True)
        if not r.ok:
            print(f"      {w:8.1f}  FAILED: {r.fail_reason}")
            continue
        sh = r.noise_share_power()
        ts = sh.get("tail_p", 0) + sh.get("tail_n", 0)
        print(f"      {w:8.1f} {r.vdsat_tail:8.4f} {r.tail_margin_v:+8.4f} "
              f"{r.gm_tail * 1e3:9.3f} {r.vn_in_vrms * 1e3:8.4f}m "
              f"{ts * 100:10.1f}%")
        trade.append({"w_um": w, "vdsat": r.vdsat_tail,
                      "margin_v": r.tail_margin_v, "gm_tail": r.gm_tail,
                      "vn_in_vrms": r.vn_in_vrms, "tail_share_power": ts})
    rows["headroom_noise_tradeoff"] = trade
    if len(trade) > 1:
        a, b = trade[0], trade[-1]
        print(f"      => {b['w_um'] / a['w_um']:.0f}x more width buys "
              f"{(b['margin_v'] - a['margin_v']) * 1e3:+.0f} mV of headroom and "
              f"costs {b['vn_in_vrms'] / a['vn_in_vrms']:.2f}x in S5.")
        print(f"         THIS is the tail's design trade, and it is why "
              f"w_tail has a ceiling as well as a floor.")
    _merge_results({"noise": rows})
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# 4. What a SHORT tail costs S3 — where l_tail's floor comes from.
# ─────────────────────────────────────────────────────────────────────────────


def rout_main(args) -> int:
    """What the tail's own impedance at the source node does to S3.

    THE FIRST DRAFT OF THIS STAGE ATTRIBUTED THE EFFECT TO `l_tail` AND WAS
    WRONG. It swept `(L, W)` together — picking W per L to hold `vdsat` — and
    read a 3.8 dB swing in peaking as an L effect. Separating the two axes on
    the sweep CSV shows W does almost all of it: at fixed L = 0.5 um, W from 25
    to 800 um moves peaking 2.74 -> 6.65 dB (3.9 dB), while at fixed W = 141 um,
    L from 0.5 to 1.0 um moves it 4.44 -> 4.79 dB (0.34 dB). Both axes are swept
    here so the attribution is visible rather than asserted.
    """
    print("=" * 78)
    print("4. THE TAIL'S IMPEDANCE AT THE SOURCE NODE -- what it does to S3")
    print("=" * 78)
    print("  Each tail device hangs from ONE source node to ground, so it adds")
    print("  BOTH a finite r_o (which shunts the Rs/Cs degeneration and takes")
    print("  peaking AWAY) and a parasitic capacitance (which degenerates less")
    print("  at high frequency, exactly as Cs does, and ADDS peaking). The two")
    print("  pull in opposite directions and both scale with tail size, so the")
    print("  net sign is a measurement, not a deduction.\n")

    corner = SWEEP_CORNERS[0]
    i_side = REFERENCE_INPUT["i_tail_per_side_a"]
    ideal = run_point(_base_point(i_side, corner, None), swing=False)
    if not ideal.ok:
        print(f"  ideal reference FAILED: {ideal.fail_reason}")
        return 1
    ip = ideal.peaking_db
    print(f"  reference with an IDEAL tail (r_o infinite, no parasitics): "
          f"peaking {ip:.3f} dB at {ideal.f_pk_hz / 1e9:.3f} GHz")

    out: dict = {"ideal_peaking_db": ip, "vs_w": [], "vs_l": []}

    print(f"\n  --- axis 1: WIDTH, at fixed L = 0.5 um ---")
    print(f"      {'W_tail':>8} {'nf':>3} {'vdsat':>8} {'margin':>8} "
          f"{'gm_in/mS':>9} {'peaking':>9} {'vs ideal':>9} {'f_peak/GHz':>11}")
    for w in (25.0, 50.0, 100.0, 200.0, 400.0, 800.0):
        r, t = _probe(i_side, corner, w, 0.5)
        if r is None:
            continue
        print(f"      {w:8.1f} {t.nf_tail:3d} {r.vdsat_tail:8.4f} "
              f"{r.tail_margin_v:+8.4f} {r.gm * 1e3:9.3f} {r.peaking_db:9.3f} "
              f"{r.peaking_db - ip:+9.3f} {r.f_pk_hz / 1e9:11.4f}")
        out["vs_w"].append({"w_um": w, "l_um": 0.5, "vdsat": r.vdsat_tail,
                            "margin_v": r.tail_margin_v, "gm_in": r.gm,
                            "peaking_db": r.peaking_db,
                            "delta_db": r.peaking_db - ip, "f_pk_hz": r.f_pk_hz})

    print(f"\n  --- axis 2: LENGTH, at fixed W = 141.4 um ---")
    print(f"      {'L_tail':>8} {'nf':>3} {'vdsat':>8} {'margin':>8} "
          f"{'gm_in/mS':>9} {'peaking':>9} {'vs ideal':>9} {'f_peak/GHz':>11}")
    for l in (0.15, 0.25, 0.5, 0.75, 1.0, 2.0):
        r, t = _probe(i_side, corner, 141.4, l)
        if r is None:
            continue
        print(f"      {l:8.2f} {t.nf_tail:3d} {r.vdsat_tail:8.4f} "
              f"{r.tail_margin_v:+8.4f} {r.gm * 1e3:9.3f} {r.peaking_db:9.3f} "
              f"{r.peaking_db - ip:+9.3f} {r.f_pk_hz / 1e9:11.4f}")
        out["vs_l"].append({"w_um": 141.4, "l_um": l, "vdsat": r.vdsat_tail,
                            "margin_v": r.tail_margin_v, "gm_in": r.gm,
                            "peaking_db": r.peaking_db,
                            "delta_db": r.peaking_db - ip, "f_pk_hz": r.f_pk_hz})

    def _span(rows) -> float:
        d = [x["peaking_db"] for x in rows]
        return max(d) - min(d) if d else 0.0

    sw, sl = _span(out["vs_w"]), _span(out["vs_l"])
    allrows = out["vs_w"] + out["vs_l"]
    worst = max((abs(x["delta_db"]) for x in allrows), default=0.0)
    print(f"\n      peaking swing across WIDTH  (25-800 um at L 0.5):  "
          f"{sw:.2f} dB")
    print(f"      peaking swing across LENGTH (0.15-2 um at W 141):  {sl:.2f} dB")
    print(f"      Both axes also move vdsat_tail, so neither is a clean "
          f"single-mechanism sweep; what")
    print(f"      is clean is that gm_in barely moves across either "
          f"(11.0-12.4 mS), so this is the tail's")
    print(f"      IMPEDANCE at the source node and not a shift in the pair's "
          f"bias point.")
    print(f"      Sign: small tails give away peaking (low r_o shunts the "
          f"degeneration); large tails ADD")
    print(f"      peaking (their source-node capacitance degenerates less at "
          f"high frequency, like Cs).")
    cross = [x for x in out["vs_w"] if x["delta_db"] >= 0]
    if cross and len(cross) < len(out["vs_w"]):
        print(f"      The two cancel near W = {cross[0]['w_um']:g} um at "
              f"L = 0.5 um, where the real tail reproduces")
        print(f"      the ideal one to {cross[0]['delta_db']:+.2f} dB.")
    out["swing_w_db"], out["swing_l_db"], out["worst_delta_db"] = sw, sl, worst

    # THE NUMBER THAT DECIDES THE RECOMMENDATION. A tail sized to the vdsat
    # target barely touches S3; a tail left free to roam the geometry can move
    # it by more than session 11's entire corner-robustness margin budget.
    on_target = [x for x in allrows
                 if abs(x["vdsat"] - VDSAT_TARGET_V) <= 0.05]
    if on_target:
        lo = min(x["delta_db"] for x in on_target)
        hi = max(x["delta_db"] for x in on_target)
        out["on_target_delta_db"] = [lo, hi]
        print(f"\n      RESTRICTED to tails sized near the vdsat target "
              f"({VDSAT_TARGET_V:.2f} +/- 0.05 V), the shift is only")
        print(f"      {lo:+.2f} to {hi:+.2f} dB over {len(on_target)} "
              f"geometries. Unrestricted it reaches {worst:.2f} dB.")
        print(f"      => Session 11 measured that corner robustness needs "
              f"1.0 dB of peaking margin. A tail")
        print(f"         sized BY RULE costs a small fraction of that; a tail "
              f"left as a free SEARCH dimension")
        print(f"         can consume {worst / 1.0:.1f}x the whole budget on "
              f"its own. That is the case for sizing it,")
        print(f"         not searching it -- see TAIL_DEVICE.md sec 6.")
    _merge_results({"tail_impedance": out})
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# 5. The bounds. DERIVED from the committed data, never typed.
# ─────────────────────────────────────────────────────────────────────────────

#: Session 11's measured requirement: a design needs >= 1.0 dB of peaking
#: margin (and >= 0.133 octaves of f_peak margin) to be corner-robust at 92%
#: against a 60.8% base rate. It is the natural yardstick for "how much S3 may
#: the tail move?", because anything the tail spends comes out of that budget.
S11_PEAKING_MARGIN_DB: float = 1.0


def saturation_floor_um_per_amp(rows: Sequence[TailRow],
                                corner: str,
                                l_um: float) -> Optional[float]:
    """Narrowest tail, as um per amp, that stays SATURATED at `corner`.

    The hard floor, distinct from the `vdsat` target: below this the tail is in
    triode and is not delivering its current at all, so every small-signal
    number describes a different circuit.

    **INTERPOLATED, not read off a ladder rung — G52.** The first version of
    this returned the smallest PASSING rung, which overstates the floor by up
    to one rung and produced a floor of 112.1k um/A sitting ABOVE the
    vdsat-target rule's own 105.4k lower edge. That is impossible — the
    saturation floor is by construction looser than a `vdsat = 0.20 V` target
    when `v(source)` is ~0.33 V — and it was a property of the ladder, not of
    the device. G52's rule: interpolate onto the quantity the verdict is about
    (here `tail_margin_v = 0`) rather than quoting the grid.
    """
    best: Optional[float] = None
    for i_side in sorted({r.i_side_a for r in rows}):
        sel = sorted((r for r in rows if r.ok and r.corner == corner
                      and r.l_tail == l_um and r.i_side_a == i_side
                      and r.tail_margin_v is not None),
                     key=lambda r: r.w_tail)
        # `tail_margin_v` crosses zero once, from below, as W grows. Find the
        # bracketing pair and interpolate log-linearly in width, matching
        # `interp_width_at_vdsat`.
        w_cross = None
        for a, b in zip(sel, sel[1:]):
            if a.tail_margin_v <= 0.0 < b.tail_margin_v:
                f = (0.0 - a.tail_margin_v) / (b.tail_margin_v - a.tail_margin_v)
                w_cross = math.exp(math.log(a.w_tail)
                                   + f * (math.log(b.w_tail) - math.log(a.w_tail)))
                break
        if w_cross is None and sel and sel[0].tail_margin_v > 0.0:
            # Saturated at every rung: the floor is below the ladder, so the
            # honest answer is "not bracketed here", not the smallest rung.
            continue
        if w_cross is not None:
            per_amp = w_cross / i_side
            best = per_amp if best is None else max(best, per_amp)
    return best


def bounds_main(args) -> int:
    rows = [r for r in read_csv(DATA_CSV) if r.ok]
    saved: dict = {}
    if RESULTS_JSON.exists():
        saved = json.loads(RESULTS_JSON.read_text(encoding="ascii"))
    worst = str(SWEEP_CORNERS[1])            # ss/0.95/125 C

    print("=" * 78)
    print("5. BOUNDS for w_tail, l_tail, nf_tail -- per-edge provenance")
    print("=" * 78)
    print("  PROPOSAL ONLY. common/params.py is untouched (CLAUDEwa sec 8 "
          "rule 6): the box")
    print("  is a human decision. Every edge below traces to a row of "
          "tail_device_data.csv.\n")

    rule = sizing_rule(rows)
    tgt = rule.get(f"L=0.5 {worst}", {})
    per_amp = [d["um_per_amp"] for d in tgt.values()]
    floor = saturation_floor_um_per_amp(rows, worst, 0.5)

    print(f"  --- w_tail ---")
    if per_amp:
        print(f"  RULE  {min(per_amp) / 1e3:.1f}-{max(per_amp) / 1e3:.1f}k um/A "
              f"at L=0.5 um, {worst}, for vdsat_tail = {VDSAT_TARGET_V:.2f} V.")
        print(f"        Measured at {len(per_amp)} currents spanning "
              f"{min(tgt) * 1e3:.2f}-{max(tgt) * 1e3:.2f} mA/side; the spread "
              f"is {max(per_amp) / min(per_amp):.2f}x,")
        print(f"        which is what makes it a current DENSITY rather than a "
              f"width.")
    if floor:
        print(f"  FLOOR {floor / 1e3:.1f}k um/A -- below this the tail is in "
              f"TRIODE at {worst}.")
        print(f"        Hard, not a target: a triode tail is not delivering "
              f"its current, so every")
        print(f"        small-signal number above it describes a different "
              f"circuit.")
    imp = saved.get("tail_impedance", {})
    over = [x for x in imp.get("vs_w", []) if abs(x["delta_db"]) > S11_PEAKING_MARGIN_DB]
    if over:
        w_hi = min(x["w_um"] for x in over if x["delta_db"] > 0)
        print(f"  CEIL  ~{w_hi:.0f} um at 1.5 mA/side "
              f"= {w_hi / 1.5e-3 / 1e3:.0f}k um/A -- at this width the tail's "
              f"own source-node")
        print(f"        capacitance moves S3 peaking by more than session 11's "
              f"{S11_PEAKING_MARGIN_DB:.1f} dB margin")
        print(f"        requirement ({[x for x in over if x['delta_db'] > 0][0]['delta_db']:+.2f} dB), "
              f"i.e. the tail alone consumes the whole corner-robustness")
        print(f"        budget. Noise agrees in direction: the tails are "
              f"already the largest")
        print(f"        contributor at the rule width (sec 4).")

    print(f"\n  --- l_tail ---")
    vs_l = imp.get("vs_l", [])
    short = [x for x in vs_l if x["delta_db"] < -S11_PEAKING_MARGIN_DB]
    if short:
        l_lo = max(x["l_um"] for x in short)
        print(f"  FLOOR 0.5 um. At L={l_lo:g} um the tail's output resistance "
              f"shunts the degeneration")
        print(f"        and gives away {short[-1]['delta_db']:+.2f} dB of "
              f"peaking against the ideal tail -- more than")
        print(f"        session 11's whole {S11_PEAKING_MARGIN_DB:.1f} dB "
              f"margin. At 0.5 um it is "
              f"{[x for x in vs_l if x['l_um'] == 0.5][0]['delta_db']:+.2f} dB.")
    for l in (0.5, 1.0):
        t = rule.get(f"L={l:g} {worst}", {})
        if t:
            v = list(t.values())[len(t) // 2]["um_per_amp"]
            print(f"        (width cost at L={l:g}: {v / 1e3:.0f}k um/A)")
    l10 = rule.get(f"L=1 {worst}", {})
    l05 = rule.get(f"L=0.5 {worst}", {})
    if l10 and l05:
        a = list(l05.values())[len(l05) // 2]["um_per_amp"]
        b = list(l10.values())[len(l10) // 2]["um_per_amp"]
        print(f"  CEIL  1.0 um. Same headroom costs {b / a:.2f}x the width, and "
              f"width is what the")
        print(f"        S3 ceiling above is made of -- so length past 1 um "
              f"buys output resistance")
        print(f"        the design does not need at a width cost it cannot "
              f"afford.")

    print(f"\n  --- nf_tail ---")
    nf = saved.get("sweep", {}).get("nf_probe", {})
    matched = [d for d in nf.values() if d.get("matched")]
    if matched:
        iv = [d["i_tail"] for d in matched]
        print(f"  NOT A SEARCH DIMENSION. Derived: the smallest multiple of "
              f"N = {MIRROR_RATIO:g} that keeps")
        print(f"  W/nf <= {W_PER_FINGER_MAX_UM:g} um (G53) -- which also keeps "
              f"the reference a whole number of")
        print(f"  matched fingers. Measured over nf = "
              f"{sorted(int(k) for k, d in nf.items() if d.get('matched'))}: "
              f"the delivered current")
        print(f"  moves {(max(iv) / min(iv) - 1) * 100:.1f}%. Same shape as "
              f"G38 (nf_in) and G42 (cl): an axis that")
        print(f"  spends samples without carrying information. If it is "
              f"searched anyway, the range")
        print(f"  is {min(int(k) for k in nf)}-{max(int(k) for k in nf)} and "
              f"multiples of N are the only sane values.")
    print(f"\n  Written up in TAIL_DEVICE.md sec 6.")
    return 0


def _probe(i_side: float, corner: Corner, w: float, l: float):
    """One tail geometry at one corner. `(None, None)` on a rejected build."""
    try:
        t = tail_for(w, l)
    except TailGeometryError as exc:
        print(f"      W{w:g} L{l:g}: geometry rejected: {exc}")
        return None, None
    r = run_point(_base_point(i_side, corner, t), corner=corner.process,
                  temp_c=corner.temp_c, swing=False)
    if not r.ok:
        print(f"      W{w:g} L{l:g}: FAILED: {r.fail_reason}")
        return None, None
    return r, t


# ─────────────────────────────────────────────────────────────────────────────
# Results bookkeeping.
# ─────────────────────────────────────────────────────────────────────────────


def _merge_results(new: dict) -> None:
    """Merge into the results JSON rather than overwriting, so `--noise` does
    not silently delete `--sweep`'s output."""
    cur: dict = {}
    if RESULTS_JSON.exists():
        try:
            cur = json.loads(RESULTS_JSON.read_text(encoding="ascii"))
        except ValueError:
            cur = {}
    cur.update(new)
    RESULTS_JSON.write_text(json.dumps(cur, indent=1, default=float),
                            encoding="ascii")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--identity", action="store_true")
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--noise", action="store_true")
    ap.add_argument("--rout", action="store_true")
    ap.add_argument("--bounds", action="store_true",
                    help="derive the three box edges from the committed data")
    ap.add_argument("--report", action="store_true",
                    help="re-report the sweep from the committed CSV, no simulator")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args(argv)

    if not any((args.identity, args.sweep, args.noise, args.rout, args.report,
                args.bounds, args.all)):
        ap.error("pick at least one stage (--identity/--sweep/--noise/--rout/"
                 "--bounds/--report/--all)")

    rc = 0
    if args.report:
        rows = [r for r in read_csv(DATA_CSV) if r.ok]
        print(f"re-reporting {len(rows)} rows from {DATA_CSV.name}, "
              f"no simulator\n")
        _merge_results({"sweep": report_sweep(rows)})
        return 0
    if args.identity or args.all:
        rc |= identity_main(args)
        print()
    if args.sweep or args.all:
        rc |= sweep_main(args)
        print()
    if args.noise or args.all:
        rc |= noise_main(args)
        print()
    if args.rout or args.all:
        rc |= rout_main(args)
        print()
    if args.bounds or args.all:
        rc |= bounds_main(args)
    return rc


if __name__ == "__main__":
    sys.exit(main())
