"""
experiments/lib_cost.py — what the parameter-deck trim actually bought.

    python -m nebula.experiments.lib_cost                 # 50 designs, ~4 min
    python -m nebula.experiments.lib_cost --designs 100
    python -m nebula.experiments.lib_cost --json out.json
    python -m nebula.experiments.lib_cost --pfet-cost     # entry 76, ~30 s

THE QUESTION
------------
Session 17 measured that **99.7 % of a training run is the simulator**
(1585.8 s of environment against a 3.5 s PPO update), and that a real-passives
evaluation costs **2.07 s against ~0.33 s** on the nfet-only library. Every
experiment in this project is bought at that rate. `device/pdk_trim.py` removes
8,823 of the 8,909 `.param` definitions the R/C corner decks carry. This
measures what that is worth, on real designs, through the real `run_point`
path — not on a synthetic probe.

THREE ARMS, AND THE THIRD IS NOT AN APPLES-TO-APPLES COMPARISON
---------------------------------------------------------------
  * `extended_untrimmed` — drawn SKY130 passives, the extended library with
    the trim undone by `pdk_trim.untrimmed_library_text()`. The "before".
  * `extended_trimmed`   — the same netlist, the current library. The "after".
  * `nfet_only`          — **ideal R/C elements** and the nfet-only trim. It is
    a DIFFERENT NETLIST, not a different library for the same circuit, because
    the nfet-only library has no resistor or capacitor model cards at all. It
    is measured anyway because ~0.33 s is the number every throughput estimate
    in this repo is anchored to, and the honest comparison is "how close does
    the trim get to the floor", not "does it beat the floor".

THE PROTOCOL, WHICH IS G71'S AND IS NOT OPTIONAL
------------------------------------------------
G71: *a benchmark whose passes run in a fixed order MEASURES THE ORDER*, and it
nearly published a wrong conclusion. Three defences, all on:

  * **a discarded warm-up pass**, because the first configuration always pays
    the OS file cache warming on the PDK include tree, whichever one it is;
  * **randomised arm order, re-drawn per design** — stronger than G71's
    once-per-sweep shuffle, because it also averages out drift over the run
    rather than only stopping the penalty landing on one arm;
  * **a control**: the first arm is re-run at the end over the same designs and
    the two medians compared. A ratio outside [0.8, 1.25] means the run
    measured its own order and **the numbers are void, not adjusted** (G71).

G70: one SPICE experiment at a time. This runs single-process on purpose —
per-evaluation cost is the quantity, and anything else simulating alongside it
makes the extended library 4.8x slower and the number meaningless.

WHAT THIS DOES *NOT* LICENCE
-----------------------------
G75: a speed-up measured on isolated evaluations **does not transfer** to a
workload whose workers also compute — session 17's 2.98x at 8 workers became
1.80x on the benchmark's own task mix. So the ratio here is the ratio for
`SEC_PER_SIM_TRAJECTORY`, and `baselines.SEC_PER_SIM_AT_8` must be re-measured
by re-running `--pilot`, not by dividing this number by anything.

CORRECTNESS FIRST
-----------------
Every arm's parsed measurement vector is compared across arms on the designs
they share. A speed-up that changed a number is not a speed-up; the run says so
and returns a non-zero exit code.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from nebula.device import pdk_trim, sky130_runner
from nebula.device.passives import to_geometry
from nebula.device.sky130_runner import SizingPoint, run_point
from nebula.device.tail import TailDevice, min_nf_for_width

HERE = Path(__file__).resolve().parent

#: The arms. Each differs from its neighbour in ONE thing, which is the only
#: reason the differences between them mean anything:
#:
#:   untrimmed_mono   PDK parameter decks + 25-section file   <- session 18 state
#:   trimmed_mono     trimmed decks       + 25-section file   <- the deck trim alone
#:   trimmed_split    trimmed decks       + 1-section file    <- today
#:   extended_ideal   IDEAL R/C netlist   + 1-section file    <- drawn-device cost
#:   nfet_only        IDEAL R/C netlist   + nfet-only library <- the floor
#:
#: so
#:     untrimmed_mono - trimmed_mono   = what trimming the parameter decks bought
#:     trimmed_mono   - trimmed_split  = what splitting the sections bought
#:     trimmed_split  - extended_ideal = what DRAWING the passives costs
#:     extended_ideal - nfet_only      = what the extra model cards cost
#:
#: The last two arms are what turned a disappointing 1.55x into an answer: they
#: showed the residual is neither the circuit nor the model cards, which is
#: what sent the search to the section count.
ARMS: "tuple[str, ...]" = ("extended_untrimmed_mono", "extended_trimmed_mono",
                           "extended_trimmed_split", "extended_ideal",
                           "nfet_only")

#: Entry 76's deliberately narrow comparison. Both arms use the same drawn
#: passive netlist and one-section library; only PFET model availability moves.
PFET_ARMS: "tuple[str, str]" = ("current_section", "pfet_section")
PFET_ABS_LIMIT_S: float = 0.010
PFET_REL_LIMIT: float = 1.05

#: Arms that run the IDEAL R/C netlist rather than drawn SKY130 devices. They
#: are a different circuit, so they are excluded from the equivalence check by
#: construction rather than by remembering to.
_IDEAL_NETLIST_ARMS: "frozenset[str]" = frozenset({"nfet_only", "extended_ideal"})

#: Arms that must NOT take the one-section fast path. `lib_for_device` prefers
#: a one-section file whenever one exists, which would silently turn the
#: "before" arms into "after" arms — the measurement reporting the improvement
#: it was built to test. `_run_arm` points `pdk_trim.SECTION_DIR` at an empty
#: directory for these, so the real fallback branch runs.
_MONOLITHIC_ARMS: "frozenset[str]" = frozenset(
    {"extended_untrimmed_mono", "extended_trimmed_mono"})

#: Fields compared across arms. The AC measurements the reward reads, plus the
#: `.op` primitives the cross-check reads. `runtime_s` is deliberately absent.
COMPARED: "tuple[str, ...]" = (
    "g_dc_db", "g_pk_db", "f_pk_hz", "g_nyq_db", "gm", "gmbs", "vth", "id_a",
    "v_out_dc", "i_supply_a", "vn_in_vrms",
)

#: Session 17's own constants for the designs, so this measures the cost of the
#: workload the project actually runs rather than an invented one.
NF_IN_FIXED: int = 4
CL_CONTEXT_F: float = 150e-15
TAIL_MIRROR_RATIO: float = 4.0


@dataclass
class ArmResult:
    name: str
    seconds: "list[float]" = field(default_factory=list)
    values: "dict[int, dict]" = field(default_factory=dict)
    failures: "list[str]" = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.seconds)

    @property
    def median_s(self) -> float:
        return statistics.median(self.seconds) if self.seconds else math.nan

    @property
    def mean_s(self) -> float:
        return statistics.fmean(self.seconds) if self.seconds else math.nan

    def quantile(self, q: float) -> float:
        if not self.seconds:
            return math.nan
        s = sorted(self.seconds)
        return s[min(len(s) - 1, int(q * len(s)))]


def _designs(n: int, seed: int) -> "list[dict]":
    """`n` realisable box samples, with the tail and geometry rl_smoke uses."""
    from nebula.experiments.s3_yield import PROPOSED_BOX, sample_box

    out: "list[dict]" = []
    draw, attempts = 0, 0
    while len(out) < n and attempts < 20:
        attempts += 1
        rows = sample_box(PROPOSED_BOX, 2 * n, seed + draw)
        draw += 1
        for p in rows:
            if len(out) >= n:
                break
            p = dict(p, nf_in=float(NF_IN_FIXED), cl=CL_CONTEXT_F)
            try:
                geo = to_geometry(p["rs"], p["cs"], p["rl"])
            except ValueError:
                continue                     # unrealisable geometry; free skip
            i_side = float(p["i_bias"]) / 2.0
            w_t = i_side * _tail_w_per_amp()
            tail = TailDevice(w_tail=w_t, l_tail=_tail_l(),
                              nf_tail=min_nf_for_width(w_t, TAIL_MIRROR_RATIO),
                              mirror_ratio=TAIL_MIRROR_RATIO)
            out.append({"params": p, "geo": geo, "tail": tail})
    if len(out) < n:
        raise RuntimeError(f"only {len(out)} of {n} designs were realisable")
    return out


def _tail_w_per_amp() -> float:
    from nebula.experiments import rl_smoke
    return rl_smoke._tail_rule_j()


def _tail_l() -> float:
    from nebula.experiments import rl_smoke
    return rl_smoke._tail_rule_l()


def _evaluate(arm: str, design: dict, corner: str = "tt") -> "tuple[float, dict, Optional[str]]":
    """One evaluation. Returns (seconds, compared values, failure reason)."""
    p, geo, tail = design["params"], design["geo"], design["tail"]
    passives = None if arm in _IDEAL_NETLIST_ARMS else geo
    pt = SizingPoint.from_params(p, vdd=1.8, tail=tail, passives=passives)
    t0 = time.perf_counter()
    r = run_point(pt, corner=corner, swing=False)
    dt = time.perf_counter() - t0
    if not r.ok:
        return dt, {}, r.fail_reason
    return dt, {k: getattr(r, k, None) for k in COMPARED}, None


def _with_library(**libs: Path):
    """Point `sky130_runner`'s library constants somewhere else, temporarily.

    The measurement needs one netlist run against two libraries, and one
    library run against two netlists, and `lib_for_device` reads module
    constants for both. Swapping them here — in the harness, explicitly, and
    restored in `__exit__` even on failure — keeps `sky130_runner` free of a
    measurement hook and guarantees the arms differ in exactly the swapped
    constant and in nothing else.

    `CTLE_LIB` selects the library used when `passives` is a drawn geometry;
    `TRIMMED_LIB` selects it when `passives is None`. `extended_ideal` needs
    the second, which is why this takes keywords rather than one path.
    """
    class _Swap:
        def __enter__(self):
            self.old = {k: getattr(sky130_runner, k) for k in libs}
            for k, v in libs.items():
                setattr(sky130_runner, k, v)
            return libs

        def __exit__(self, *exc):
            for k, v in self.old.items():
                setattr(sky130_runner, k, v)
            return False
    return _Swap()


def _with_pfet_includes(section_text: str) -> str:
    """Return one current CTLE section with matching PFET includes added.

    This builds entry 76's candidate in a temporary directory, before the
    production library is edited.  The two asserted insertion counts are the
    gate: measuring a half-built candidate would understate its parse cost.
    """
    lines = section_text.splitlines(keepends=True)
    out: "list[str]" = []
    n_corner = n_mismatch = 0
    for line in lines:
        out.append(line)
        if "sky130_fd_pr__nfet_01v8__mismatch.corner.spice" in line:
            out.append(line.replace("nfet_01v8__mismatch",
                                    "pfet_01v8__mismatch"))
            n_mismatch += 1
        elif "sky130_fd_pr__nfet_01v8__" in line and ".pm3.spice" in line:
            out.append(line.replace("nfet_01v8__", "pfet_01v8__"))
            n_corner += 1
    if (n_corner, n_mismatch) != (1, 1):
        raise ValueError(
            "a split CTLE section must contain one corner and one mismatch "
            f"NFET include; found corner={n_corner}, mismatch={n_mismatch}")
    return "".join(out)


def _pfet_cost_decision(current_s: float, pfet_s: float) -> dict:
    """Apply entry 76's pre-registered absolute AND relative cost limits."""
    added = pfet_s - current_s
    ratio = pfet_s / current_s if current_s else math.inf
    return {
        "current_median_s": current_s,
        "pfet_median_s": pfet_s,
        "added_median_s": added,
        "ratio": ratio,
        "absolute_limit_s": PFET_ABS_LIMIT_S,
        "relative_limit": PFET_REL_LIMIT,
        "immaterial": added <= PFET_ABS_LIMIT_S and ratio <= PFET_REL_LIMIT,
    }


def _stage_section_tree(source: Path, destination_dir: Path, text: str) -> None:
    """Stage one split library plus every relative include it references."""
    seen: "set[Path]" = set()

    def stage(src: Path, dst: Path, body: "str | None" = None) -> None:
        src = src.resolve()
        if src in seen:
            return
        seen.add(src)
        if body is None:
            if not src.is_file():
                raise FileNotFoundError(
                    f"relative include missing while staging: {src}")
            body = src.read_text(encoding="ascii")
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(body, encoding="ascii", newline="\n")
        for raw in re.findall(r'^\.include\s+"([^"]+)"', body,
                              flags=re.MULTILINE | re.IGNORECASE):
            inc = Path(raw)
            if inc.is_absolute():
                continue
            stage(src.parent / inc, dst.parent / inc)

    stage(source, destination_dir / source.name, text)


def _no_section_libraries(empty_dir: Path):
    """Point `pdk_trim.SECTION_DIR` at an empty directory for the duration.

    `lib_for_device` takes the one-section fast path whenever the file exists,
    so a "before" arm that only swapped `CTLE_LIB` would still have been served
    the split library and would have measured the improvement as the baseline.
    That is a silent failure of exactly the shape this repo keeps hitting, and
    it was live for one run before being caught.
    """
    class _Swap:
        def __enter__(self):
            self.old = pdk_trim.SECTION_DIR
            pdk_trim.SECTION_DIR = empty_dir
            return empty_dir

        def __exit__(self, *exc):
            pdk_trim.SECTION_DIR = self.old
            return False
    return _Swap()


def measure(n_designs: int = 50, seed: int = 20260808, corner: str = "tt",
            arms: "Sequence[str]" = ARMS, warmup: int = 3) -> dict:
    """Run the comparison. Single process, warmed up, shuffled, controlled."""
    import tempfile

    designs = _designs(n_designs, seed)
    rng = random.Random(seed)

    with tempfile.TemporaryDirectory() as td:
        untrimmed = Path(td) / "untrimmed_ctle.lib.spice"
        untrimmed.write_text(pdk_trim.untrimmed_library_text(),
                             encoding="ascii", newline="\n")

        empty = Path(td) / "no_sections"
        empty.mkdir()

        def _run_arm(arm: str, design: dict):
            if arm in _MONOLITHIC_ARMS:
                # Hide the one-section files so `lib_for_device` falls back to
                # the 25-section library, and swap in the untrimmed decks for
                # the arm that wants them.
                lib = untrimmed if arm == "extended_untrimmed_mono" else \
                    sky130_runner.CTLE_LIB
                with _no_section_libraries(empty), _with_library(CTLE_LIB=lib):
                    return _evaluate(arm, design, corner)
            if arm == "extended_ideal":
                # Ideal R/C netlist, so `lib_for_device` reads TRIMMED_LIB —
                # point that at the one-section extended library so the only
                # difference from `extended_trimmed_split` is the netlist.
                with _with_library(
                        TRIMMED_LIB=pdk_trim.section_library_path(corner)):
                    return _evaluate(arm, design, corner)
            return _evaluate(arm, design, corner)

        # THE WARM-UP, DISCARDED (G71). Without it the arm that happens to go
        # first pays the OS file cache on the PDK include tree and reports a
        # penalty that looks like a property of the arm.
        warm = {}
        for arm in arms:
            ts = [_run_arm(arm, designs[i % len(designs)])[0]
                  for i in range(warmup)]
            warm[arm] = statistics.median(ts)

        results = {a: ArmResult(a) for a in arms}
        for idx, design in enumerate(designs):
            order = list(arms)
            rng.shuffle(order)              # re-drawn per design, not per sweep
            for arm in order:
                dt, vals, fail = _run_arm(arm, design)
                results[arm].seconds.append(dt)
                if fail:
                    results[arm].failures.append(f"design {idx}: {fail}")
                else:
                    results[arm].values[idx] = vals

        # THE CONTROL (G71): the first arm again, at the end, same designs.
        control_arm = arms[0]
        control = [_run_arm(control_arm, d)[0] for d in designs]

    ctrl_med = statistics.median(control)
    first_med = results[control_arm].median_s
    ratio = first_med / ctrl_med if ctrl_med else math.nan
    contaminated = not (0.8 <= ratio <= 1.25)

    return {
        "n_designs": n_designs, "seed": seed, "corner": corner,
        "arms": list(arms), "warmup_median_s": warm,
        "rows": {a: {"n": r.n, "median_s": r.median_s, "mean_s": r.mean_s,
                     "p10_s": r.quantile(0.10), "p90_s": r.quantile(0.90),
                     "n_failed": len(r.failures),
                     "failures": r.failures[:5]}
                 for a, r in results.items()},
        "control": {"arm": control_arm, "median_s": ctrl_med,
                    "first_pass_median_s": first_med,
                    "ratio_to_first_pass": ratio,
                    "contaminated": contaminated},
        "equivalence": _equivalence(results),
        "speedup": _speedups(results),
        "decomposition": _decompose(results),
    }


def measure_pfet_cost(n_designs: int = 50, seed: int = 20260808,
                      corner: str = "tt", warmup: int = 3) -> dict:
    """Measure PFET model availability before changing the production trim."""
    import tempfile

    designs = _designs(n_designs, seed)
    rng = random.Random(seed)
    t_wall = time.perf_counter()
    source = pdk_trim.section_library_path(corner)
    if not source.exists():
        raise FileNotFoundError(f"missing current split library {source}")

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        dirs = {arm: root / arm / "sections" for arm in PFET_ARMS}
        current_text = source.read_text(encoding="ascii")
        _stage_section_tree(source, dirs["current_section"], current_text)
        _stage_section_tree(source, dirs["pfet_section"],
                            _with_pfet_includes(current_text))

        def _run_arm(arm: str, design: dict):
            with _no_section_libraries(dirs[arm]):
                return _evaluate(arm, design, corner)

        warm = {}
        for arm in PFET_ARMS:
            warm[arm] = statistics.median(
                _run_arm(arm, designs[i % len(designs)])[0]
                for i in range(warmup))

        results = {a: ArmResult(a) for a in PFET_ARMS}
        for idx, design in enumerate(designs):
            order = list(PFET_ARMS)
            rng.shuffle(order)
            for arm in order:
                dt, vals, fail = _run_arm(arm, design)
                results[arm].seconds.append(dt)
                if fail:
                    results[arm].failures.append(f"design {idx}: {fail}")
                else:
                    results[arm].values[idx] = vals

        control = [_run_arm(PFET_ARMS[0], d)[0] for d in designs]

    first = results[PFET_ARMS[0]].median_s
    ctrl = statistics.median(control)
    control_ratio = first / ctrl if ctrl else math.nan
    rows = {
        a: {"n": r.n, "median_s": r.median_s, "mean_s": r.mean_s,
            "p10_s": r.quantile(0.10), "p90_s": r.quantile(0.90),
            "n_failed": len(r.failures), "failures": r.failures[:5]}
        for a, r in results.items()
    }
    return {
        "task": "entry 76: parse cost of PFET support in one CTLE section",
        "n_designs": n_designs, "seed": seed, "corner": corner,
        "arms": list(PFET_ARMS), "warmup_median_s": warm, "rows": rows,
        "control": {
            "arm": PFET_ARMS[0], "median_s": ctrl,
            "first_pass_median_s": first,
            "ratio_to_first_pass": control_ratio,
            "contaminated": not (0.8 <= control_ratio <= 1.25),
        },
        "equivalence": _equivalence_pair(
            results, PFET_ARMS[0], PFET_ARMS[1]),
        "decision": _pfet_cost_decision(
            rows[PFET_ARMS[0]]["median_s"], rows[PFET_ARMS[1]]["median_s"]),
        "wall_clock_s": time.perf_counter() - t_wall,
    }


def _decompose(results: "dict[str, ArmResult]") -> "Optional[dict]":
    """Split an evaluation's cost into its four additive terms.

    Each term is a difference of medians between two arms that differ in
    exactly one thing, which is the only reason the subtraction means
    anything. Returns None unless every arm ran.
    """
    need = ARMS
    if any(a not in results or not results[a].seconds for a in need):
        return None
    med = {a: results[a].median_s for a in need}
    floor = med["nfet_only"]
    overhead = med["extended_untrimmed_mono"] - floor
    terms = {
        "model_cards_s": med["extended_ideal"] - floor,
        "drawing_passives_s": med["extended_trimmed_split"] - med["extended_ideal"],
        "section_count_s": med["extended_trimmed_mono"] - med["extended_trimmed_split"],
        "parameter_decks_s": med["extended_untrimmed_mono"] - med["extended_trimmed_mono"],
    }
    out = {"medians": med, "floor_s": floor, "overhead_s": overhead, **terms}
    for k, v in terms.items():
        out[k.replace("_s", "_share")] = v / overhead if overhead else math.nan
    return out


def _speedups(results: "dict[str, ArmResult]") -> dict:
    base = results.get("extended_untrimmed_mono")
    if base is None or not base.seconds:
        return {}
    return {a: base.median_s / r.median_s
            for a, r in results.items() if r.seconds}


def _equivalence(results: "dict[str, ArmResult]") -> dict:
    """Did the trim change a number? Untrimmed against trimmed, exactly.

    `nfet_only` is excluded — it is a different netlist (ideal R/C), so it
    SHOULD disagree, and folding it in would make a real regression look like
    an expected one.
    """
    return _equivalence_pair(results, "extended_untrimmed_mono",
                             "extended_trimmed_split")


def _equivalence_pair(results: "dict[str, ArmResult]", first: str,
                      second: str) -> dict:
    """Exact comparison for two arms that must produce the same circuit."""
    a = results.get(first)
    b = results.get(second)
    if a is None or b is None:
        return {"checked": 0, "note": "both extended arms are needed"}
    shared = sorted(set(a.values) & set(b.values))
    diffs = []
    for idx in shared:
        for k in COMPARED:
            x, y = a.values[idx].get(k), b.values[idx].get(k)
            if x is None and y is None:
                continue
            if x != y:                       # exact; rel=0, abs=0
                diffs.append({"design": idx, "field": k,
                              "untrimmed": x, "trimmed": y})
    return {"checked": len(shared), "fields": len(COMPARED),
            "n_diff": len(diffs), "diffs": diffs[:10],
            "identical": not diffs and len(shared) > 0}


def report(res: dict) -> str:
    L: "list[str]" = []
    L.append("=" * 78)
    L.append("LIBRARY COST -- what the R/C parameter-deck trim bought")
    L.append("=" * 78)
    L.append(f"  {res['n_designs']} designs, corner {res['corner']}, "
             f"single process, seed {res['seed']}")
    L.append("  arm order re-shuffled per design; warm-up discarded; "
             "control re-run last (G71)")
    L.append("")
    L.append(f"  {'arm':<20} {'median s':>10} {'mean s':>9} {'p10':>8} "
             f"{'p90':>8} {'fail':>5}")
    L.append("  " + "-" * 64)
    for a in res["arms"]:
        r = res["rows"][a]
        L.append(f"  {a:<20} {r['median_s']:>10.3f} {r['mean_s']:>9.3f} "
                 f"{r['p10_s']:>8.3f} {r['p90_s']:>8.3f} {r['n_failed']:>5}")
    L.append("  " + "-" * 64)
    L.append("")
    sp = res.get("speedup", {})
    if "extended_trimmed_split" in sp:
        L.append(f"  SPEED-UP, end to end: {sp['extended_trimmed_split']:.2f}x "
                 f"(session 18's state -> today, same netlist, same numbers)")
    if "extended_trimmed_mono" in sp:
        L.append(f"    of which the parameter-deck trim alone: "
                 f"{sp['extended_trimmed_mono']:.2f}x")
    L.append("")
    d = res.get("decomposition")
    if d:
        L.append("  WHERE AN EVALUATION'S TIME GOES -- median seconds, additive:")
        L.append(f"    {d['floor_s']:>7.3f}  floor: ideal R/C netlist on the "
                 f"nfet-only library")
        L.append(f"   +{d['model_cards_s']:>7.3f}  the passive model cards "
                 f"({100 * d['model_cards_share']:.0f}% of the overhead)")
        L.append(f"   +{d['drawing_passives_s']:>7.3f}  DRAWING the passives: "
                 f"subckts, parasitics, nodes "
                 f"({100 * d['drawing_passives_share']:.0f}%)")
        L.append(f"   ={d['medians']['extended_trimmed_split']:>7.3f}  a real "
                 f"evaluation TODAY")
        L.append(f"   +{d['section_count_s']:>7.3f}  the 24 sections the run "
                 f"does not use ({100 * d['section_count_share']:.0f}%) "
                 f"-- FIXED by the split")
        L.append(f"   +{d['parameter_decks_s']:>7.3f}  the R/C parameter decks "
                 f"({100 * d['parameter_decks_share']:.0f}%) "
                 f"-- FIXED by the trim")
        L.append(f"   ={d['medians']['extended_untrimmed_mono']:>7.3f}  what an "
                 f"evaluation cost before this session")
        L.append("")
        big = max(("the section count", d["section_count_share"]),
                  ("the parameter decks", d["parameter_decks_share"]),
                  ("the passive model cards", d["model_cards_share"]),
                  ("drawing the passives", d["drawing_passives_share"]),
                  key=lambda kv: kv[1])
        L.append(f"  The dominant term was {big[0]} at "
                 f"{100 * big[1]:.0f}% of the overhead.")
    L.append("")
    c = res["control"]
    verdict = ("CONTAMINATED -- the run measured its own ORDER (G71). "
               "The wall-clock numbers above are VOID; re-run, do not adjust."
               if c["contaminated"] else "clean")
    L.append(f"  CONTROL: {c['arm']} re-run last -> {c['median_s']:.3f} s "
             f"against its first pass at {c['first_pass_median_s']:.3f} s")
    L.append(f"           ratio {c['ratio_to_first_pass']:.2f}x -> {verdict}")
    L.append("")
    e = res["equivalence"]
    if e.get("identical"):
        L.append(f"  EQUIVALENCE: {e['checked']} designs x {e['fields']} "
                 f"fields, ALL IDENTICAL (rel=0, abs=0).")
    else:
        L.append(f"  EQUIVALENCE FAILED: {e.get('n_diff')} differing value(s) "
                 f"over {e.get('checked')} designs. The trim is NOT free.")
        for d in e.get("diffs", []):
            L.append(f"    design {d['design']:>3} {d['field']:<12} "
                     f"untrimmed={d['untrimmed']!r} trimmed={d['trimmed']!r}")
    L.append("")
    L.append("  G75: this is a SINGLE-PROCESS ratio. It does not transfer to a")
    L.append("  parallel workload whose workers also compute -- re-measure")
    L.append("  baselines.SEC_PER_SIM_AT_8 with `--pilot`, do not divide.")
    L.append("")
    return "\n".join(L)


def main(argv: "Optional[Sequence[str]]" = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--designs", type=int, default=50)
    ap.add_argument("--seed", type=int, default=20260808)
    ap.add_argument("--corner", type=str, default="tt")
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--pfet-cost", action="store_true",
                    help="entry 76: compare current and PFET-capable sections")
    args = ap.parse_args(argv)

    if args.designs < 50:
        print(f"WARNING: {args.designs} designs is below the 50 the step asks "
              f"for; the median will be noisy.", file=sys.stderr)

    if args.pfet_cost:
        res = measure_pfet_cost(n_designs=args.designs, seed=args.seed,
                                corner=args.corner)
        print(json.dumps(res, indent=2, default=str))
        output = args.json or HERE / "pfet_lib_cost_results.json"
    else:
        res = measure(n_designs=args.designs, seed=args.seed, corner=args.corner)
        print(report(res))
        output = args.json or HERE / "lib_cost_results.json"
    output.write_text(json.dumps(res, indent=2, default=str), encoding="ascii")
    print(f"  wrote {output.as_posix()}")

    if res["control"]["contaminated"]:
        print("  EXIT 1: the timing control disagreed.", file=sys.stderr)
        return 1
    if not res["equivalence"].get("identical"):
        print("  EXIT 1: the trim changed a measured value.", file=sys.stderr)
        return 1
    if args.pfet_cost and any(r["n_failed"] for r in res["rows"].values()):
        print("  EXIT 1: at least one PFET-cost arm failed.", file=sys.stderr)
        return 1
    return 0


__all__: Sequence[str] = ("ARMS", "PFET_ARMS", "COMPARED", "ArmResult",
                          "measure", "measure_pfet_cost", "report", "main")

if __name__ == "__main__":                                  # pragma: no cover
    sys.exit(main())
