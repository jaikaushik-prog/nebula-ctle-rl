"""
experiments/robust_geometry.py — WHERE do the corner-robust designs live?

WHAT THIS ANSWERS
-----------------
`S9_YIELD.md` §4 cross-tabulated 1890 designs and found that **100 of the 255
that pass every spec at TT/27 C fail at a corner**. It reported the count. It
did not report where those 100 sit.

The hypothesis under test, from G46:

    Corner robustness requires the nominal peak to be centred enough in S3's
    1.25-2.5 GHz window that neither corner mechanism can push it out. FF
    raises gm and drives f_peak UP through the 2.5 GHz top edge; SS lowers gm
    and drives peaking DOWN toward 0 dB. The two failure modes therefore sit on
    OPPOSITE sides of the process axis, and a design survives only if it starts
    far enough from both window edges. Corner-robust designs should be interior
    in the box; corner-fragile ones should cluster near its edges.

The deliverable is `nebula/ROBUST_GEOMETRY.md`, and the number worth having is
the **f_peak margin in octaves** — a warm-start prior and a reward-shaping term
that costs nothing to compute analytically.

WHY THIS RE-SIMULATES A POPULATION SESSION 10D ALREADY SIMULATED
----------------------------------------------------------------
It should not have to. Session 10d's 20 205-run, 47-minute sweep wrote
`s9_yield_results.json` next to the script, and `.gitignore` line 67 lists that
filename under "run artifacts -- regenerable". It was never committed and it is
no longer on disk, so the only surviving record of that run is the prose in
`S9_YIELD.md`. See HANDOFF G49.

Two consequences, both deliberate:

1. The population is **reproduced exactly** rather than approximated:
   `sample_box(PROPOSED_BOX, 2000, 20260804)` -> pin `cl` -> drop the designs
   `headroom_ok_1v8` rejects at the nominal rail. Latin-hypercube sampling is
   seeded, so the 1890 designs are the same 1890 designs. The published counts
   are then a REPRODUCTION CHECK, asserted rather than assumed: 255 pass at
   TT/1.00/27 C, 155 pass all three screen corners, 100 are corner-fragile. If
   this run disagrees with `S9_YIELD.md`, one of the two is wrong and the
   analysis must not proceed.
2. The collected per-design table is written as **CSV and committed**, so the
   analysis, the statistics and the figures can be regenerated with no
   simulator at all. That is the fix for the loss described above.

Cost: 1890 designs x 4 corners = 7560 runs, ~13 min at G48's ~100 ms per
(design, corner) with 8-11 workers. Everything after collection is free.

USAGE
    python -m nebula.experiments.robust_geometry --collect   # ~13 min, ngspice
    python -m nebula.experiments.robust_geometry             # analyse + figures
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from nebula.common.design_equations import predict
from nebula.common.types import (
    SPEC_F_PEAK_HZ_RANGE,
    SPEC_PEAKING_DB_RANGE,
    Corner,
)
from nebula.experiments.s3_yield import (
    PROPOSED_BOX,
    headroom_ok_1v8,
    pin_param,
    sample_box,
    wilson_ci,
)
from nebula.experiments.s9_yield import (
    CL_FIXED_F,
    NOMINAL_VDD,
    SCREEN_CORNERS,
    evaluate_at_corner,
    run_tasks,
)

HERE = Path(__file__).resolve().parent
DATA_CSV = HERE / "robust_geometry_data.csv"
FIG_DIR = HERE.parent / "figures"

#: The nominal corner. NOT one of `SCREEN_CORNERS` — that is what makes
#: "does any design fail nominal yet pass the corners?" a real question
#: (S9_YIELD.md §4) rather than a tautology.
NOMINAL_CORNER = Corner(process="tt", vdd_scale=1.00, temp_c=27.0)

#: What session 10d published for this exact population. Asserted, not trusted.
EXPECTED = {"n_designs": 1890, "n_tt_pass": 255, "n_robust": 155, "n_fragile": 100}

#: The nine sampled parameters, minus `cl` (pinned, so it is a constant and
#: has no distribution to compare). `nf_in` is kept even though G38 measured it
#: near-dead and non-monotonic — an axis that measurement says does nothing is
#: exactly the axis a "robust designs are interior" claim must not be allowed
#: to score a free hit on.
BOX_PARAMS: tuple[str, ...] = (
    "rs", "cs", "rl", "i_bias", "w_in", "l_in", "vcm_in", "nf_in",
)

#: The seven the task asks to be plotted, in the order it asks for them.
PLOT_PARAMS: tuple[str, ...] = ("rs", "cs", "rl", "i_bias", "w_in", "l_in", "vcm_in")

#: The coordinates that actually set S3, derived from the TT operating point.
DERIVED: tuple[str, ...] = ("f_z", "f_p2", "k", "f_peak_nom", "peaking_nom")

#: Units and display scaling for the report tables. (scale, unit, log_axis)
DISPLAY: dict[str, tuple[float, str, bool]] = {
    "rs": (1.0, "ohm", True),
    "cs": (1e15, "fF", True),
    "rl": (1.0, "ohm", True),
    "i_bias": (1e3, "mA", True),
    "w_in": (1e6, "um", False),
    "l_in": (1e6, "um", True),
    "vcm_in": (1.0, "V", False),
    "nf_in": (1.0, "-", False),
    "f_z": (1e-9, "GHz", True),
    "f_p1": (1e-9, "GHz", True),
    "f_p2": (1e-9, "GHz", True),
    "k": (1.0, "-", True),
    "f_peak_nom": (1e-9, "GHz", True),
    "peaking_nom": (1.0, "dB", False),
    "nyq_boost_nom": (1.0, "dB", False),
    "gm_over_id": (1.0, "1/V", False),
    "f_peak_margin_oct": (1.0, "oct", False),
    "peaking_margin_db": (1.0, "dB", False),
    "box_interiority": (1.0, "-", False),
    "box_interiority_mean": (1.0, "-", False),
}


# ─────────────────────────────────────────────────────────────────────────────
# Statistics. Every function here is pure and simulator-free, which is what the
# tests exercise: this is where a wrong answer would be invisible, because a
# p-value looks equally plausible whichever way it comes out.
# ─────────────────────────────────────────────────────────────────────────────


def median(xs: Sequence[float]) -> float:
    """Sample median. Even n averages the two middle values."""
    s = sorted(xs)
    n = len(s)
    if n == 0:
        raise ValueError("median of an empty sample")
    m = n // 2
    return s[m] if n % 2 else 0.5 * (s[m - 1] + s[m])


def _average_ranks(xs: Sequence[float]) -> list[float]:
    """Ranks 1..n, with TIED VALUES SHARING THEIR AVERAGE RANK.

    The tie handling is not a detail. `nf_in` takes eight distinct integer
    values across 255 designs, so its ranking is almost entirely ties; ranking
    ties arbitrarily inflates U's apparent precision and would report a
    significant difference where there is none.
    """
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0          # ranks are 1-based
        for t in range(i, j + 1):
            ranks[order[t]] = avg
        i = j + 1
    return ranks


def _norm_sf(z: float) -> float:
    """Upper tail of the standard normal, via erfc. No scipy dependency."""
    return 0.5 * math.erfc(z / math.sqrt(2.0))


@dataclass(frozen=True)
class MannWhitney:
    u: float                 # U for the FIRST sample
    p_two_sided: float
    z: float
    #: Common-language effect size: P(a random draw from A exceeds one from B),
    #: ties counted as half. Reported alongside p because with n ~ 255 a tiny
    #: difference can be significant and still be useless as a design rule.
    prob_a_greater: float
    #: Rank-biserial correlation, 2*prob - 1, in [-1, +1].
    rank_biserial: float


def mann_whitney_u(a: Sequence[float], b: Sequence[float]) -> MannWhitney:
    """Two-sided Mann-Whitney U, normal approximation with tie correction.

    Chosen over a t-test because nothing here is Gaussian: `rs`, `cs`, `rl`,
    `i_bias` and `l_in` are sampled LOG-uniformly, and `f_peak` spans decades.
    A rank test asks the question the hypothesis actually poses — "are the
    robust designs drawn from a different distribution?" — without assuming a
    shape for either.

    The normal approximation is used with a continuity correction; at
    n1 = 155, n2 = 100 it agrees with the exact test to well under the third
    decimal, and `test_robust_geometry.py` holds it to `scipy.stats.
    mannwhitneyu` rather than to a hand-copied number.
    """
    n1, n2 = len(a), len(b)
    if n1 == 0 or n2 == 0:
        raise ValueError("both samples must be non-empty")
    pooled = list(a) + list(b)
    ranks = _average_ranks(pooled)
    r1 = sum(ranks[:n1])
    u1 = r1 - n1 * (n1 + 1) / 2.0
    mu = n1 * n2 / 2.0

    # Tie correction to the variance of U.
    counts: dict[float, int] = {}
    for v in pooled:
        counts[v] = counts.get(v, 0) + 1
    n = n1 + n2
    tie_term = sum(t ** 3 - t for t in counts.values())
    var = n1 * n2 / 12.0 * ((n + 1) - tie_term / (n * (n - 1.0)))

    if var <= 0.0:                      # every value identical: no evidence
        return MannWhitney(u1, 1.0, 0.0, 0.5, 0.0)
    z = (abs(u1 - mu) - 0.5) / math.sqrt(var)
    z = max(z, 0.0)
    p = min(1.0, 2.0 * _norm_sf(z))
    prob = u1 / (n1 * n2)
    signed_z = math.copysign(z, u1 - mu)
    return MannWhitney(u1, p, signed_z, prob, 2.0 * prob - 1.0)


def benjamini_hochberg(pvals: Sequence[float]) -> list[float]:
    """BH-adjusted p-values (q-values), same order as the input.

    Twelve variables are tested against one grouping, so at alpha = 0.05 the
    expected number of spurious hits under a true null is 0.6 — enough that an
    uncorrected table would invite exactly the "which of these is real?"
    question it exists to answer. BH controls the false discovery rate and is
    the right correction for a screen, where the cost of one false positive is
    a paragraph, not a design.
    """
    m = len(pvals)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvals[i])
    out = [0.0] * m
    prev = 1.0
    for rank, i in enumerate(reversed(order), start=1):
        k = m - rank + 1                       # 1-based rank of this p-value
        prev = min(prev, pvals[i] * m / k)
        out[i] = min(1.0, prev)
    return out


def window_margin_octaves(f_hz: float, lo_hz: float, hi_hz: float) -> float:
    """Distance from `f_hz` to the NEARER edge of [lo, hi], in octaves.

    Positive inside the window, negative outside, zero on an edge. Octaves
    rather than Hz or per cent because every mechanism that moves this peak —
    gm with process and temperature, the RL*CL pole, the Rs*Cs zero — is
    multiplicative, so a fixed number of hertz means something different at
    1.3 GHz than at 2.4 GHz while a fixed number of octaves does not.

    S3's window is 1.25-2.5 GHz, i.e. EXACTLY ONE OCTAVE WIDE, so this margin
    saturates at **0.5 octaves** at the geometric centre 1.7678 GHz. That 0.5
    is the ceiling every number in the write-up is measured against.
    """
    if f_hz <= 0.0 or lo_hz <= 0.0 or hi_hz <= 0.0:
        raise ValueError("frequencies must be positive")
    if hi_hz <= lo_hz:
        raise ValueError("window must have hi > lo")
    return min(math.log2(f_hz / lo_hz), math.log2(hi_hz / f_hz))


def normalised_position(value: float, name: str, box=PROPOSED_BOX) -> float:
    """Where `value` sits in its bound, on [0, 1].

    Uses the SAME log/linear mapping `sample_box` samples with, so a uniform
    draw maps back to a uniform position. Reading a log-sampled parameter on a
    linear scale would pile every sample against the low edge and manufacture
    the very "fragile designs are near the edge" pattern this file is testing.
    """
    lo, hi, log, _ = box[name]
    if log:
        return (math.log(value) - math.log(lo)) / (math.log(hi) - math.log(lo))
    return (value - lo) / (hi - lo)


def box_interiority(params: dict[str, float],
                    names: Sequence[str] = PLOT_PARAMS,
                    box=PROPOSED_BOX) -> float:
    """Distance to the NEAREST face of the box, in normalised units, [0, 0.5].

    0 means the design sits on a bound; 0.5 means it is dead centre in every
    dimension at once. This is the direct operationalisation of "the robust
    designs are interior in the box": a min over dimensions, because a design
    pinned against any single bound is on the boundary regardless of how
    central it is in the others.

    **`nf_in` is excluded, and would otherwise destroy the statistic.** It is
    sampled continuously and then ROUNDED to an integer in 1..8, so every
    design that lands on nf = 1 or nf = 8 has a normalised position of exactly
    0 or 1 and a min-interiority of exactly 0. That is roughly a seventh of the
    population at each end, pinned to the floor of this metric by a rounding
    rule rather than by anything about the design. `nf_in` still gets its own
    row in the comparison table — G38 measured it near-dead, and an axis that
    does nothing is precisely the one a "robust designs are interior" claim
    must not be allowed to score a free hit on.
    """
    return min(min(u, 1.0 - u) for u in
               (normalised_position(float(params[n]), n, box) for n in names))


def box_interiority_mean(params: dict[str, float],
                         names: Sequence[str] = PLOT_PARAMS,
                         box=PROPOSED_BOX) -> float:
    """Mean distance to a face over the dimensions, [0, 0.5].

    Reported beside the min because the two ask different questions: the min
    asks "is this design pinned against ANY bound", the mean asks "is it
    central ON AVERAGE". A hypothesis about interiority that holds for one and
    not the other is a weaker hypothesis than it looks, and saying which is
    cheaper than arguing about it.
    """
    us = [normalised_position(float(params[n]), n, box) for n in names]
    return sum(min(u, 1.0 - u) for u in us) / len(us)


# ─────────────────────────────────────────────────────────────────────────────
# Records.
# ─────────────────────────────────────────────────────────────────────────────

#: Measured TT scalars carried into the CSV. Everything else is derived.
MEASURED_COLS: tuple[str, ...] = (
    "peaking_db", "f_pk_hz", "nyquist_boost_db", "g_dc_db", "g_nyq_db",
    "g_pk_db", "g_top_db", "vn_in_vrms", "gm", "gmbs", "gds", "vth",
    "vds", "vdsat", "id_a", "v_src_dc", "v_out_dc", "power_w",
)


@dataclass
class DesignRecord:
    """One design: its coordinates, its nominal measurement, its verdicts."""
    idx: int                                   # index into the feasible list
    params: dict[str, float]
    tt_ok: bool
    tt_pass: bool
    tt_first_fail: Optional[str]
    measured: dict[str, Optional[float]]
    #: One entry per screen corner, in `SCREEN_CORNERS` order.
    corner_pass: tuple[bool, ...]
    corner_first_fail: tuple[Optional[str], ...]

    @property
    def robust(self) -> bool:
        """Passes TT and all three screen corners. S9_YIELD.md's 155."""
        return self.tt_pass and all(self.corner_pass)

    @property
    def fragile(self) -> bool:
        """Passes TT, fails at least one screen corner. S9_YIELD.md's 100."""
        return self.tt_pass and not all(self.corner_pass)

    def derived(self) -> dict[str, float]:
        """The coordinates that actually set S3, at the nominal operating point.

        Pole/zero/degeneration come from `common/design_equations.predict()` --
        the ONE definition of §6 in this repo (rule 9), fed the SIMULATED gm and
        gmbs so the body-effect term G27 is about is present. `f_peak_nom` and
        `peaking_nom` are MEASURED, not predicted: 10b already recorded that the
        analytic peak location fails badly here (a probed sample with
        f_p2 = 55.3 GHz peaks at 9.55 GHz), so predicting them would analyse the
        model instead of the circuit.
        """
        p = self.params
        m = self.measured
        ss = predict(gm=float(m["gm"]), rs=float(p["rs"]), cs=float(p["cs"]),
                     rl=float(p["rl"]), cl=float(p["cl"]),
                     gmbs=float(m["gmbs"]))
        return {
            "f_z": ss.f_zero_hz,
            "f_p1": ss.f_pole1_hz,
            "f_p2": ss.f_pole2_hz,
            "k": ss.degeneration_factor,
            "f_peak_nom": float(m["f_pk_hz"]),
            "peaking_nom": float(m["peaking_db"]),
            "nyq_boost_nom": float(m["nyquist_boost_db"]),
            "gm_over_id": float(m["gm"]) / float(m["id_a"]),
            "f_peak_margin_oct": window_margin_octaves(
                float(m["f_pk_hz"]), *SPEC_F_PEAK_HZ_RANGE),
            # S3's OTHER two-sided axis, folded the same way. Peaking is in dB
            # already, i.e. a log unit, so the additive distance to the nearer
            # edge is the right analogue of the octave margin.
            "peaking_margin_db": min(
                float(m["peaking_db"]) - SPEC_PEAKING_DB_RANGE[0],
                SPEC_PEAKING_DB_RANGE[1] - float(m["peaking_db"])),
            "box_interiority": box_interiority(p),
            "box_interiority_mean": box_interiority_mean(p),
        }

    def coord(self, name: str) -> float:
        """One coordinate by name, box parameter or derived alike."""
        if name in self.params:
            return float(self.params[name])
        return self.derived()[name]


# ─────────────────────────────────────────────────────────────────────────────
# Collection (the only part that needs a simulator).
# ─────────────────────────────────────────────────────────────────────────────


def population(n: int = 2000, seed: int = 20260804) -> list[dict[str, float]]:
    """The exact 1890 designs of `S9_YIELD.md`, reproduced from the seed.

    Same three steps in the same order as `s9_yield.main`: Latin-hypercube
    sample the proposed box, pin `cl`, then drop what the analytic headroom
    check rejects at the NOMINAL rail (corner headroom is re-checked per corner
    inside `evaluate_at_corner`, so losing headroom at 0.95 VDD stays a corner
    failure rather than being screened out up front).
    """
    params = pin_param(sample_box(PROPOSED_BOX, n, seed), "cl", CL_FIXED_F)
    return [p for p in params if headroom_ok_1v8(p, NOMINAL_VDD) is None]


def collect(designs: Sequence[dict[str, float]], workers: int = 11
            ) -> list[DesignRecord]:
    """Evaluate every design at TT and at the three screen corners.

    Calls `s9_yield.evaluate_at_corner` unmodified, so the pass/fail label here
    is produced by the same code that produced `S9_YIELD.md`'s counts — which
    is what makes the reproduction check below meaningful rather than circular.
    """
    corners = (NOMINAL_CORNER,) + tuple(SCREEN_CORNERS)
    tasks = [(p, c.process, c.vdd_scale, c.temp_c)
             for p in designs for c in corners]
    t0 = time.perf_counter()
    flat = run_tasks(tasks, workers=workers)
    dt = time.perf_counter() - t0
    print(f"  {len(tasks)} runs in {dt:.1f} s "
          f"({dt / len(tasks) * 1000:.1f} ms/run)")

    nc = len(corners)
    out: list[DesignRecord] = []
    for i, p in enumerate(designs):
        rs = flat[i * nc:(i + 1) * nc]
        tt = rs[0]
        out.append(DesignRecord(
            idx=i, params=dict(p),
            tt_ok=tt.ok, tt_pass=bool(tt.all_specs_met),
            tt_first_fail=tt.first_fail,
            measured=dict(tt.measured or {}),
            corner_pass=tuple(bool(r.all_specs_met) for r in rs[1:]),
            corner_first_fail=tuple(r.first_fail for r in rs[1:]),
        ))
    return out


def _csv_fields() -> list[str]:
    return (["idx"] + list(PROPOSED_BOX) + ["tt_ok", "tt_pass", "tt_first_fail"]
            + list(MEASURED_COLS)
            + [f"c{j}_pass" for j in range(len(SCREEN_CORNERS))]
            + [f"c{j}_first_fail" for j in range(len(SCREEN_CORNERS))])


def save_csv(records: Sequence[DesignRecord], path: Path = DATA_CSV) -> None:
    """Write the collected table. TRACKED IN GIT, unlike `s9_yield_results.json`
    — see the module docstring and G49. It is the input to every number in
    `ROBUST_GEOMETRY.md`, so losing it would cost another 13 minutes of SPICE
    and, more importantly, would make the write-up uncheckable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="ascii") as fh:
        w = csv.DictWriter(fh, fieldnames=_csv_fields())
        w.writeheader()
        for r in records:
            row: dict[str, object] = {"idx": r.idx}
            row.update({k: repr(float(v)) for k, v in r.params.items()})
            row["tt_ok"] = int(r.tt_ok)
            row["tt_pass"] = int(r.tt_pass)
            row["tt_first_fail"] = r.tt_first_fail or ""
            for c in MEASURED_COLS:
                v = r.measured.get(c)
                row[c] = "" if v is None else repr(float(v))
            for j, ok in enumerate(r.corner_pass):
                row[f"c{j}_pass"] = int(ok)
            for j, ff in enumerate(r.corner_first_fail):
                row[f"c{j}_first_fail"] = ff or ""
            w.writerow(row)


def load_csv(path: Path = DATA_CSV) -> list[DesignRecord]:
    """Read the collected table back. No simulator involved."""
    out: list[DesignRecord] = []
    with path.open(newline="", encoding="ascii") as fh:
        for row in csv.DictReader(fh):
            nc = len(SCREEN_CORNERS)
            out.append(DesignRecord(
                idx=int(row["idx"]),
                params={k: float(row[k]) for k in PROPOSED_BOX},
                tt_ok=bool(int(row["tt_ok"])),
                tt_pass=bool(int(row["tt_pass"])),
                tt_first_fail=row["tt_first_fail"] or None,
                measured={c: (float(row[c]) if row[c] else None)
                          for c in MEASURED_COLS},
                corner_pass=tuple(bool(int(row[f"c{j}_pass"]))
                                  for j in range(nc)),
                corner_first_fail=tuple(row[f"c{j}_first_fail"] or None
                                        for j in range(nc)),
            ))
    return out


def check_reproduction(records: Sequence[DesignRecord]) -> list[str]:
    """Compare the regenerated counts against what session 10d published.

    Returns a list of discrepancies, empty if everything matches. This is a
    GATE, not a print: if the population does not reproduce, the split into
    robust and fragile is a split of some other experiment's designs and every
    statistic downstream is about the wrong thing (CLAUDEwa §8 rule 10).
    """
    got = {
        "n_designs": len(records),
        "n_tt_pass": sum(1 for r in records if r.tt_pass),
        "n_robust": sum(1 for r in records if r.robust),
        "n_fragile": sum(1 for r in records if r.fragile),
    }
    return [f"{k}: expected {EXPECTED[k]}, got {got[k]}"
            for k in EXPECTED if got[k] != EXPECTED[k]]


# ─────────────────────────────────────────────────────────────────────────────
# Analysis.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Comparison:
    name: str
    median_robust: float
    median_fragile: float
    p: float
    q: float                # BH-adjusted
    prob_robust_greater: float
    unit: str


def compare_groups(robust: Sequence[DesignRecord],
                   fragile: Sequence[DesignRecord],
                   names: Sequence[str]) -> list[Comparison]:
    """Median-vs-median plus a Mann-Whitney U test on every named coordinate."""
    raw: list[tuple[str, float, float, float, float]] = []
    for name in names:
        a = [r.coord(name) for r in robust]
        b = [r.coord(name) for r in fragile]
        mw = mann_whitney_u(a, b)
        raw.append((name, median(a), median(b), mw.p_two_sided,
                    mw.prob_a_greater))
    qs = benjamini_hochberg([r[3] for r in raw])
    out = []
    for (name, ma, mb, p, prob), q in zip(raw, qs):
        scale, unit, _ = DISPLAY.get(name, (1.0, "", False))
        out.append(Comparison(name, ma * scale, mb * scale, p, q, prob, unit))
    return out


@dataclass(frozen=True)
class MarginBin:
    lo: float
    hi: float
    n: int
    n_robust: int
    rate: float
    ci: tuple[float, float]


def margin_table(records: Sequence[DesignRecord],
                 edges: Sequence[float],
                 coord: str = "f_peak_margin_oct") -> list[MarginBin]:
    """P(corner-robust | margin in bin), over the TT winners, with Wilson CIs."""
    winners = [r for r in records if r.tt_pass]
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        rows = [r for r in winners if lo <= r.coord(coord) < hi]
        k = sum(1 for r in rows if r.robust)
        n = len(rows)
        out.append(MarginBin(lo, hi, n, k, (k / n if n else float("nan")),
                             wilson_ci(k, n) if n else (float("nan"),) * 2))
    return out


def threshold_table(records: Sequence[DesignRecord],
                    thresholds: Sequence[float],
                    coord: str = "f_peak_margin_oct") -> list[MarginBin]:
    """P(corner-robust | margin >= t), the form a warm-start prior needs.

    A prior does not ask "which bin is this design in", it asks "if I only ever
    propose designs with at least this much margin, what fraction survives the
    corners, and how much of the space do I give up to get it?" `n` is that
    second number: the count retained at each threshold.
    """
    winners = [r for r in records if r.tt_pass]
    out = []
    for t in thresholds:
        rows = [r for r in winners if r.coord(coord) >= t]
        k = sum(1 for r in rows if r.robust)
        n = len(rows)
        out.append(MarginBin(t, float("inf"), n, k,
                             (k / n if n else float("nan")),
                             wilson_ci(k, n) if n else (float("nan"),) * 2))
    return out


#: Points per decade in the netlist's `ac dec 50` sweep. `meas ac ... MAX`
#: returns a GRID POINT, so f_peak — and therefore the margin — is quantised.
AC_POINTS_PER_DECADE: int = 50


def margin_quantum_octaves(points_per_decade: int = AC_POINTS_PER_DECADE
                           ) -> float:
    """The smallest resolvable step in `f_peak_margin_oct`, in octaves.

    `meas ac g_pk MAX vd_db FROM=... TO=...` reports the largest SAMPLE, not an
    interpolated maximum, so f_peak can only ever land on the `ac dec 50` grid.
    One grid step is 10^(1/50) in frequency = log2(10)/50 octaves = 0.0664.

    Consequence, and it must be stated wherever the margin is quoted: S3's
    window is one octave wide, so it contains only about **15 distinct
    f_peak values**, and any margin threshold quoted to finer than ~0.07
    octaves is quoting the sweep grid rather than the circuit. It is why the
    threshold table has repeated rows (t = 0.100 and t = 0.125 select the same
    designs) and why the margin histogram has empty bins.
    """
    return math.log2(10.0) / points_per_decade


def failure_edge_split(fragile: Sequence[DesignRecord]) -> dict[str, int]:
    """Which window edge each fragile design was sitting near, and where it died.

    G46's mechanism, made checkable: a fragile design whose nominal peak sits
    ABOVE the window's geometric centre should be killed by the FAST corner
    (higher gm pushes f_peak up through 2.5 GHz), and one sitting BELOW it by a
    SLOW corner (lower gm drops the peaking toward 0 dB). Counting the four
    combinations turns "the two edges are on opposite sides of the process
    axis" from a story into a 2x2 table.
    """
    centre = math.sqrt(SPEC_F_PEAK_HZ_RANGE[0] * SPEC_F_PEAK_HZ_RANGE[1])
    fast_idx = [j for j, c in enumerate(SCREEN_CORNERS) if c.process == "ff"]
    out = {"high_fast": 0, "high_slow": 0, "low_fast": 0, "low_slow": 0}
    for r in fragile:
        high = r.coord("f_peak_nom") > centre
        died_fast = any(not r.corner_pass[j] for j in fast_idx)
        died_slow = any(not ok for j, ok in enumerate(r.corner_pass)
                        if j not in fast_idx)
        if died_fast:
            out["high_fast" if high else "low_fast"] += 1
        if died_slow:
            out["high_slow" if high else "low_slow"] += 1
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Figures. Two series only (robust / fragile), so identity is carried by colour
# AND marker shape AND the legend -- never by colour alone.
# ─────────────────────────────────────────────────────────────────────────────

C_ROBUST = "#0072B2"      # Okabe-Ito blue
C_FRAGILE = "#D55E00"     # Okabe-Ito vermillion
C_INK = "#1a1a1a"
C_MUTED = "#8a8a8a"

#: Text drawn on top of markers needs a surface behind it or the markers read
#: as part of the glyphs.
_LABEL_BBOX = dict(facecolor="white", alpha=0.72, edgecolor="none", pad=1.5)


def _style():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "figure.facecolor": "white", "axes.facecolor": "white",
        "axes.edgecolor": C_MUTED, "axes.labelcolor": C_INK,
        "axes.labelsize": 8, "axes.titlesize": 9,
        "xtick.color": C_MUTED, "ytick.color": C_MUTED,
        "xtick.labelsize": 7, "ytick.labelsize": 7,
        "grid.color": "#e6e6e6", "grid.linewidth": 0.6,
        "legend.frameon": False, "legend.fontsize": 8,
        "font.size": 8, "savefig.dpi": 160, "savefig.bbox": "tight",
    })
    return plt


def _scatter(ax, xs_r, ys_r, xs_f, ys_f):
    ax.scatter(xs_f, ys_f, s=13, c=C_FRAGILE, marker="x", linewidths=0.9,
               alpha=0.85, label="corner-fragile", zorder=3)
    ax.scatter(xs_r, ys_r, s=11, facecolors="none", edgecolors=C_ROBUST,
               marker="o", linewidths=0.8, alpha=0.85,
               label="corner-robust", zorder=4)


def _tidy(ax, logx=False, logy=False):
    """Recessive frame, and NO MINOR TICK LABELS on log axes.

    matplotlib labels log minor ticks by default whenever a decade is not
    fully spanned, which on a 5x5 grid of narrow panels prints "2 3 4 6 10 20"
    on top of itself and on top of the major labels. It is the single thing
    that made the first render of these matrices unreadable.
    """
    from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(True, linewidth=0.4, alpha=0.6)
    for on, axis in ((logx, ax.xaxis), (logy, ax.yaxis)):
        if not on:
            continue
        (ax.set_xscale if axis is ax.xaxis else ax.set_yscale)("log")
        # 1-2-5 per decade as MAJOR ticks. The default log locator puts majors
        # only on whole decades, which leaves an axis spanning e.g. k = 1.5-7
        # with no labelled tick at all, and labels every minor tick when a
        # decade is not fully spanned -- printing "2 3 4 6 10 20" on top of
        # itself. Both were visible in the first render of these matrices.
        axis.set_major_locator(LogLocator(base=10.0, subs=(1.0, 2.0, 5.0),
                                          numticks=12))
        axis.set_major_formatter(FuncFormatter(_compact))
        axis.set_minor_formatter(NullFormatter())


def _compact(v, _pos=None) -> str:
    """Short decimal label: 0.15, 2, 50, 1e3 — never 2 x 10^0."""
    if v <= 0:
        return ""
    if v >= 1000:
        return f"{v / 1000:.3g}k"      # 1k / 2k / 10k: "1000" and "2000" side
    if v >= 10:                        # by side on a narrow panel collide
        return f"{v:.0f}"
    if v >= 1:
        return f"{v:.3g}"
    return f"{v:.3g}"


def _limits(vals, log: bool, pad: float = 0.06) -> tuple[float, float]:
    """Shared limits for one variable, so every panel in a row or column of the
    matrix is on the SAME scale. Without this each panel autoscales to its own
    data and the grid stops being comparable across rows, which is the entire
    point of a scatter matrix."""
    lo, hi = min(vals), max(vals)
    if log and lo > 0:
        span = math.log10(hi) - math.log10(lo)
        return (10 ** (math.log10(lo) - pad * span),
                10 ** (math.log10(hi) + pad * span))
    span = hi - lo or 1.0
    return lo - pad * span, hi + pad * span


def _hist_bins(lo: float, hi: float, log: bool, n: int = 18):
    if log and lo > 0:
        a, b = math.log10(lo), math.log10(hi)
        return [10 ** (a + t * (b - a) / n) for t in range(n + 1)]
    return [lo + t * (hi - lo) / n for t in range(n + 1)]


def _axis_label(name: str) -> str:
    scale, unit, _ = DISPLAY.get(name, (1.0, "", False))
    return f"{name} ({unit})" if unit and unit != "-" else name


def _vals(rows, name):
    scale = DISPLAY.get(name, (1.0, "", False))[0]
    return [r.coord(name) * scale for r in rows]


def fig_pairs(records, names, path: Path, title: str, subtitle: str = ""):
    """Lower-triangle pairwise scatter matrix, robust vs fragile.

    Every panel in a column shares one x scale and every panel in a row shares
    one y scale, set explicitly from the pooled data rather than by autoscale,
    so the grid is actually comparable panel to panel.
    """
    plt = _style()
    robust = [r for r in records if r.robust]
    fragile = [r for r in records if r.fragile]
    d = len(names)
    logs = {n: DISPLAY.get(n, (1, "", False))[2] for n in names}
    lims = {n: _limits(_vals(robust, n) + _vals(fragile, n), logs[n])
            for n in names}

    fig, axes = plt.subplots(d, d, figsize=(1.62 * d, 1.62 * d))
    for i in range(d):
        for j in range(d):
            ax = axes[i][j]
            if j > i:
                ax.axis("off")
                continue
            yname, xname = names[i], names[j]
            if i == j:
                # Diagonal: the two marginals as OUTLINES, not overlapping
                # fills -- two translucent fills blend into a third colour
                # that reads as a third category.
                bins = _hist_bins(*lims[xname], logs[xname])
                ax.hist(_vals(robust, xname), bins=bins, histtype="step",
                        color=C_ROBUST, linewidth=1.3)
                ax.hist(_vals(fragile, xname), bins=bins, histtype="step",
                        color=C_FRAGILE, linewidth=1.3, linestyle=(0, (3, 2)))
                ax.set_yticks([])
                _tidy(ax, logx=logs[xname])
            else:
                _scatter(ax, _vals(robust, xname), _vals(robust, yname),
                         _vals(fragile, xname), _vals(fragile, yname))
                _tidy(ax, logx=logs[xname], logy=logs[yname])
                ax.set_ylim(*lims[yname])
            ax.set_xlim(*lims[xname])
            if i == d - 1:
                ax.set_xlabel(_axis_label(xname))
            else:
                ax.set_xticklabels([])
                ax.tick_params(axis="x", length=0)
            if j == 0 and i != 0:
                ax.set_ylabel(_axis_label(yname))
            elif i != j:
                ax.set_yticklabels([])
                ax.tick_params(axis="y", length=0)
    h = [plt.Line2D([], [], color=C_ROBUST, marker="o", markerfacecolor="none",
                    linestyle="none", label=f"corner-robust (n={len(robust)})"),
         plt.Line2D([], [], color=C_FRAGILE, marker="x", linestyle="none",
                    label=f"corner-fragile (n={len(fragile)})")]
    fig.legend(handles=h, loc="upper right", bbox_to_anchor=(0.99, 0.935))
    fig.suptitle(title, x=0.015, y=0.995, ha="left", va="top", fontsize=12,
                 color=C_INK)
    if subtitle:
        fig.text(0.015, 0.966, subtitle, ha="left", va="top", fontsize=8.5,
                 color="#555555")
    fig.tight_layout(rect=(0, 0, 1, 0.925))
    fig.savefig(path)
    plt.close(fig)
    return path


def fig_s3_plane(records, path: Path):
    """The one figure this experiment exists to produce.

    Every one of these 255 designs passes S3 at TT, so every marker sits inside
    the box that is drawn. The question the figure answers is which of them
    SURVIVE, and the answer is legible as position: the fragile ones line the
    window's frequency edges.
    """
    plt = _style()
    robust = [r for r in records if r.robust]
    fragile = [r for r in records if r.fragile]
    f_lo, f_hi = (f / 1e9 for f in SPEC_F_PEAK_HZ_RANGE)
    p_lo, p_hi = SPEC_PEAKING_DB_RANGE
    centre = math.sqrt(f_lo * f_hi)

    from matplotlib.ticker import NullFormatter
    band = 0.1                       # octaves: the "near an edge" strip
    fig, ax = plt.subplots(figsize=(8.0, 5.0))
    top = p_hi + 1.4                 # headroom for the legend

    ax.add_patch(plt.Rectangle((f_lo, p_lo), f_hi - f_lo, p_hi - p_lo,
                               facecolor="#f4f4f4", edgecolor=C_MUTED,
                               linewidth=0.8, zorder=1))
    for x0, x1 in ((f_lo, f_lo * 2 ** band), (f_hi / 2 ** band, f_hi)):
        ax.add_patch(plt.Rectangle((x0, p_lo), x1 - x0, p_hi - p_lo,
                                   facecolor=C_FRAGILE, alpha=0.10,
                                   edgecolor="none", zorder=2))
    ax.axvline(centre, color=C_MUTED, linewidth=0.8, linestyle=(0, (4, 3)),
               zorder=3)
    _scatter(ax, _vals(robust, "f_peak_nom"), _vals(robust, "peaking_nom"),
             _vals(fragile, "f_peak_nom"), _vals(fragile, "peaking_nom"))

    ax.set_xscale("log")
    ax.set_xlim(f_lo * 0.985, f_hi * 1.015)
    ax.set_ylim(p_lo - 0.5, top)
    ax.set_xticks([1.25, 1.5, 1.77, 2.0, 2.5])
    ax.set_xticklabels(["1.25\n(edge)", "1.5", "1.77\n(centre)", "2.0",
                        "2.5\n(edge)"])
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.set_yticks([3, 4, 6, 8, 10, 12])
    ax.set_xlabel("nominal peak frequency (GHz, log axis). The S3 window is "
                  "exactly one octave wide.")
    ax.set_ylabel("nominal peaking (dB)")
    fig.suptitle("Every design here passes S3 at TT/27 C. Only the blue ones "
                 "survive three corners.",
                 x=0.02, y=0.985, ha="left", va="top", fontsize=12,
                 color=C_INK)
    fig.text(0.02, 0.925,
             "The survivors are not at a different frequency -- they are at a "
             "less EXTREME one.\nShaded strips: within 0.1 octave of a window "
             "edge.",
             ha="left", va="top", fontsize=8.5, color="#555555")

    # Labels sit INSIDE their own strip, rotated. No arrows: every arrow long
    # enough to reach a strip from clear space had to cross the data to do it.
    ax.text(math.sqrt(f_lo * f_lo * 2 ** band), (p_lo + p_hi) / 2,
            "SS lowers gm: f_peak falls out through this edge",
            rotation=90, ha="center", va="center", fontsize=8,
            color="#8c3d00", zorder=5, bbox=_LABEL_BBOX)
    ax.text(math.sqrt(f_hi * f_hi / 2 ** band), (p_lo + p_hi) / 2,
            "FF raises gm: f_peak rises out through this edge",
            rotation=90, ha="center", va="center", fontsize=8,
            color="#8c3d00", zorder=5, bbox=_LABEL_BBOX)
    _tidy(ax)
    ax.legend(loc="upper left", ncols=1)
    fig.subplots_adjust(top=0.855, left=0.085, right=0.985, bottom=0.145)
    fig.savefig(path, bbox_inches=None)
    plt.close(fig)
    return path


def fig_margin(records, path: Path, bins: Sequence[MarginBin],
               thresh: Sequence[MarginBin]):
    """Margin distribution, and what margin buys — the reward-shaping number."""
    plt = _style()
    robust = [r for r in records if r.robust]
    fragile = [r for r in records if r.fragile]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.6, 3.7))

    # Dodged bars, not overlapping translucent fills: two alpha fills blend
    # into a third colour that reads as a third category.
    nb = 10
    step = 0.5 / nb
    lo_edges = [t * step for t in range(nb)]
    cr = [sum(1 for r in robust if e <= r.coord("f_peak_margin_oct") < e + step)
          for e in lo_edges]
    cf = [sum(1 for r in fragile if e <= r.coord("f_peak_margin_oct") < e + step)
          for e in lo_edges]
    w = step * 0.42
    ax1.bar([e + step / 2 - w / 2 - 0.001 for e in lo_edges], cr, width=w,
            color=C_ROBUST, label=f"corner-robust (n={len(robust)})")
    ax1.bar([e + step / 2 + w / 2 + 0.001 for e in lo_edges], cf, width=w,
            color=C_FRAGILE, label=f"corner-fragile (n={len(fragile)})")
    ax1.set_xlabel("nominal f_peak margin to the nearer window edge (octaves)")
    ax1.set_ylabel("designs")
    ax1.set_xlim(-0.02, 0.52)
    ax1.set_title("Where the two groups sit in the window", loc="left")
    ax1.legend(loc="upper right")

    xs = [b.lo for b in thresh]
    ys = [b.rate * 100 for b in thresh]
    lo = [b.ci[0] * 100 for b in thresh]
    hi = [b.ci[1] * 100 for b in thresh]
    ax2.fill_between(xs, lo, hi, color=C_ROBUST, alpha=0.16, linewidth=0)
    ax2.plot(xs, ys, color=C_ROBUST, linewidth=2.0, marker="o", markersize=4)
    base = 100.0 * sum(1 for r in records if r.robust) / max(
        1, sum(1 for r in records if r.tt_pass))
    ax2.axhline(base, color=C_MUTED, linewidth=1.0, linestyle=(0, (4, 3)))
    ax2.text(0.30, base - 4.5, f"no filter: {base:.1f}%", fontsize=8,
             color=C_MUTED, ha="right")
    ax2.set_xlabel("keep only designs with margin >= t (octaves)")
    ax2.set_ylabel("% corner-robust")
    ax2.set_ylim(0, 104)
    ax2.set_xlim(-0.005, 0.305)
    ax2.set_title("What margin buys (Wilson 95% band)", loc="left")
    for ax in (ax1, ax2):
        _tidy(ax)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


# ─────────────────────────────────────────────────────────────────────────────
# Report.
# ─────────────────────────────────────────────────────────────────────────────


def _fmt_p(p: float) -> str:
    return "<1e-12" if p < 1e-12 else f"{p:.2e}" if p < 1e-3 else f"{p:.4f}"


def report(records: Sequence[DesignRecord]) -> str:
    robust = [r for r in records if r.robust]
    fragile = [r for r in records if r.fragile]
    L: list[str] = []
    A = L.append
    A("=" * 78)
    A("WHERE DO THE CORNER-ROBUST DESIGNS LIVE?")
    A("=" * 78)
    A(f"  designs        {len(records)}")
    A(f"  TT winners     {sum(1 for r in records if r.tt_pass)}")
    A(f"  corner-robust  {len(robust)}   (TT + all 3 screen corners)")
    A(f"  corner-fragile {len(fragile)}   (TT, fails >= 1 screen corner)")
    problems = check_reproduction(records)
    A(f"  reproduction   {'OK -- matches S9_YIELD.md' if not problems else 'MISMATCH'}")
    for p in problems:
        A(f"    *** {p}")
    A("")

    names = list(PLOT_PARAMS) + ["nf_in"] + list(DERIVED) + [
        "nyq_boost_nom", "gm_over_id", "f_peak_margin_oct",
        "peaking_margin_db", "box_interiority", "box_interiority_mean"]
    cmps = compare_groups(robust, fragile, names)
    A("  --- group medians and Mann-Whitney U (BH-adjusted across the table) ---")
    A(f"      {'coordinate':20} {'robust':>12} {'fragile':>12} {'P(R>F)':>8} "
      f"{'p':>10} {'q':>10}")
    for c in cmps:
        star = " *" if c.q < 0.05 else ""
        A(f"      {c.name + ' (' + c.unit + ')':20} {c.median_robust:12.4g} "
          f"{c.median_fragile:12.4g} {c.prob_robust_greater:8.3f} "
          f"{_fmt_p(c.p):>10} {_fmt_p(c.q):>10}{star}")
    A("      (* q < 0.05.  P(R>F) is the common-language effect size: the")
    A("       chance a random robust design exceeds a random fragile one.)")
    A("")

    edges = [0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.5001]
    A("  --- P(corner-robust | f_peak margin in bin), TT winners only ---")
    A(f"      {'margin (oct)':16} {'n':>5} {'robust':>7} {'rate':>8}   95% CI")
    for b in margin_table(records, edges):
        if b.n == 0:
            continue
        A(f"      {b.lo:5.2f} - {b.hi if b.hi < 1 else 0.5:5.2f}    "
          f"{b.n:5d} {b.n_robust:7d} {b.rate * 100:7.1f}%   "
          f"[{b.ci[0] * 100:5.1f}, {b.ci[1] * 100:5.1f}]")
    A("")

    q = margin_quantum_octaves()
    distinct = len({round(r.coord("f_peak_nom"), 3)
                    for r in records if r.tt_pass})
    A(f"  --- resolution: f_peak is quantised onto the ac dec "
      f"{AC_POINTS_PER_DECADE} grid ---")
    A(f"      one grid step = {q:.4f} octaves; the 1-octave S3 window holds "
      f"{distinct} distinct f_peak values.")
    A("      Margin thresholds finer than that quote the sweep grid, not the "
      "circuit.")
    A("")

    ths = [0.0, 0.05, 0.10, 0.125, 0.15, 0.175, 0.20, 0.25, 0.30]
    trows = threshold_table(records, ths)
    A("  --- P(corner-robust | margin >= t): the warm-start prior ---")
    A(f"      {'t (oct)':>8} {'kept':>6} {'robust':>7} {'rate':>8}   95% CI")
    for b in trows:
        if b.n == 0:
            continue
        A(f"      {b.lo:8.3f} {b.n:6d} {b.n_robust:7d} {b.rate * 100:7.1f}%   "
          f"[{b.ci[0] * 100:5.1f}, {b.ci[1] * 100:5.1f}]")
    A("")

    A("  --- BOTH S3 axes are two-sided. Joint prior: require margin on each ---")
    A(f"      {'f_peak >= (oct)':>16} {'peaking >= (dB)':>16} {'kept':>6} "
      f"{'robust':>7} {'rate':>8}   95% CI")
    for t_f, t_p in ((0.0, 0.0), (0.0, 0.5), (0.0, 1.0),
                     (0.133, 0.0), (0.133, 0.5), (0.133, 1.0),
                     (0.2, 1.0), (0.2, 1.5)):
        rows = [r for r in records if r.tt_pass
                and r.coord("f_peak_margin_oct") >= t_f
                and r.coord("peaking_margin_db") >= t_p]
        k = sum(1 for r in rows if r.robust)
        if not rows:
            continue
        lo, hi = wilson_ci(k, len(rows))
        A(f"      {t_f:16.3f} {t_p:16.2f} {len(rows):6d} {k:7d} "
          f"{k / len(rows) * 100:7.1f}%   [{lo * 100:5.1f}, {hi * 100:5.1f}]")
    A("")

    split = failure_edge_split(fragile)
    A("  --- G46's mechanism as a 2x2: where the fragile design sat, and which")
    A("      corner killed it (a design can appear in both columns) ---")
    A(f"      {'nominal f_peak':22} {'died at FF':>12} {'died at SS':>12}")
    A(f"      {'above 1.77 GHz centre':22} {split['high_fast']:12d} "
      f"{split['high_slow']:12d}")
    A(f"      {'below 1.77 GHz centre':22} {split['low_fast']:12d} "
      f"{split['low_slow']:12d}")
    A("")

    from collections import Counter
    A("  --- what the fragile designs fail on, per screen corner ---")
    for j, c in enumerate(SCREEN_CORNERS):
        cnt = Counter(r.corner_first_fail[j] for r in fragile
                      if not r.corner_pass[j])
        tot = sum(cnt.values())
        items = ", ".join(f"{k} {v}" for k, v in cnt.most_common())
        A(f"      {str(c):22} {tot:4d} failures   {items}")
    A("=" * 78)
    return "\n".join(L)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--collect", action="store_true",
                    help="re-run ngspice and rewrite the CSV (~13 min)")
    ap.add_argument("--workers", type=int, default=11)
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20260804)
    ap.add_argument("--data", type=Path, default=DATA_CSV)
    ap.add_argument("--figures", type=Path, default=FIG_DIR)
    ap.add_argument("--no-figures", action="store_true")
    args = ap.parse_args(argv)

    if args.collect or not args.data.exists():
        if not args.collect:
            print(f"no {args.data.name}; collecting (this needs ngspice)")
        designs = population(args.n, args.seed)
        print(f"  {args.n} sampled -> {len(designs)} feasible at nominal 1.8 V")
        records = collect(designs, workers=args.workers)
        save_csv(records, args.data)
        print(f"  wrote {args.data}")
    else:
        records = load_csv(args.data)
        print(f"loaded {len(records)} designs from {args.data.name} "
              f"(no simulator used)")

    problems = check_reproduction(records)
    print()
    print(report(records))

    if problems:
        print("\n*** POPULATION DOES NOT REPRODUCE S9_YIELD.md -- "
              "the split above is not the published one. Stopping.")
        return 1

    if not args.no_figures:
        args.figures.mkdir(parents=True, exist_ok=True)
        edges = [0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.5001]
        ths = [t / 200.0 for t in range(0, 61, 2)]
        paths = [
            fig_s3_plane(records, args.figures / "robust_s3_plane.png"),
            fig_margin(records, args.figures / "robust_margin.png",
                       margin_table(records, edges),
                       threshold_table(records, ths)),
            fig_pairs(records, PLOT_PARAMS,
                      args.figures / "robust_box_pairs.png",
                      "Box coordinates: corner-robust vs corner-fragile",
                      "The two groups are indistinguishable in every sampled "
                      "dimension. No box coordinate survives correction "
                      "(all q > 0.12)."),
            fig_pairs(records, DERIVED,
                      args.figures / "robust_derived_pairs.png",
                      "Derived coordinates: corner-robust vs corner-fragile",
                      "Also indistinguishable -- including f_peak itself. The "
                      "separation is in DISTANCE TO THE WINDOW EDGE, which no "
                      "panel here plots."),
        ]
        for p in paths:
            print(f"  wrote {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
