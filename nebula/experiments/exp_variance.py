"""experiments/exp_variance.py — run-to-run CONSISTENCY of each search method.

WHY THIS EXISTS
---------------
Proposal 002 (Vikas Vijay, "AI-Driven Automation of Analog Circuit Sizing — A
Designer's Perspective") lists four adoption criteria a sizing tool must meet.
Three are business arguments we cannot act on. The fourth is **consistency**:

    "Adoption follows several silicon revisions of predictable results.
     Unpredictable output sends designers back to manual methods."

`CONTINUE_HERE.md` section 5 records that whether our variance-across-repeats is
measurable at all was an OPEN question. It is measurable, it needs **zero new
simulations**, and this module answers it from `baselines_run_interp.jsonl.gz`.

It is also the axis proposal 001's paper claims as its own contribution: fRL-AD's
headline against AutoCkt is **variance reduction, not a better mean** (001 brief
section 4). So this measures our arms on the metric that literature competes on.

WHAT IT MEASURES
----------------
Spread of `best_reward` across replicates of the same (problem, method,
prescreen, budget) cell. Every replicate differs only in seed, so the spread IS
the run-to-run consistency a designer would experience.

TWO FILTERS THAT ARE NOT OPTIONAL
---------------------------------
1. **`role == "measured"`.** The sweep also logs `warmup` and `control` rows;
   `BASELINES.md` section 7g excludes warmup from timing, and G71 records that the
   first configuration pays the cold cache. Mixing them in is a timing error
   leaking into a quality metric.
2. **One problem at a time.** P1 saturates near a reward ceiling of ~8.95; P3 is
   mostly infeasible and its rewards run negative. Pooling them makes `uniform`'s
   standard deviation read **4.6186 instead of 0.1110** -- a 42x inflation that
   looks like a finding. This was hit while writing this module; the grouping key
   carries `problem` for that reason.

Reproduce:

    python -m nebula.experiments.exp_variance --run
"""

from __future__ import annotations

import argparse
import gzip
import json
import random
import statistics as st
from collections import defaultdict
from pathlib import Path
from typing import Optional, Sequence

HERE = Path(__file__).resolve().parent
LOG = HERE / "baselines_run_interp.jsonl.gz"
#: The budget ladder, a SEPARATE sweep at a larger budget (VARIANCE.md section 4).
LADDER_LOG = HERE / "budget_ladder_run.jsonl.gz"

#: Artifacts are named per (log, problem). A single fixed filename let a P3 run
#: silently overwrite the P1 result the moment `--problem` was used -- the same
#: clobbering `runlock.py` was written to stop (G113).
def results_path(problem: str, log: Path) -> Path:
    tag = "ladder" if log == LADDER_LOG else "baselines"
    return HERE / f"variance_results_{tag}_{problem}.json"

#: Bootstrap resamples for the SD-ratio interval. Fixed so the number is stable.
N_BOOT: int = 20_000
BOOT_SEED: int = 7

#: Arms compared head to head. Each is (label_a, label_b) as (method, prescreen).
PAIRS: tuple = (
    (("uniform", False), ("cmaes", False)),
    (("uniform", False), ("gp_bo", False)),
    (("ppo", False), ("cmaes", False)),
    (("ppo", True), ("cmaes", True)),
    (("ppo", True), ("uniform", True)),
)


def load_summaries(path: Optional[Path] = None, problem: str = "P1",
                   role: str = "measured") -> list[dict]:
    """Per-replicate `run_summary` rows for ONE problem and ONE role.

    Both filters are load-bearing -- see the module docstring. Passing
    `problem=None` is deliberately NOT supported.
    """
    if not problem:
        raise ValueError("problem must be given; pooling problems inflates the "
                         "spread by ~42x (see module docstring)")
    path = LOG if path is None else path
    out: list[dict] = []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            d = json.loads(line)
            if (d.get("event") == "run_summary"
                    and d.get("role") == role
                    and d.get("problem") == problem):
                out.append(d)
    return out


def group(rows: Sequence[dict]) -> dict:
    """(method, prescreen) -> list of best_reward, one per replicate."""
    g: dict = defaultdict(list)
    for r in rows:
        g[(r["method"], bool(r["prescreen"]))].append(float(r["best_reward"]))
    return dict(g)


def sd_ratio_ci(a: Sequence[float], b: Sequence[float],
                n_boot: int = N_BOOT, seed: int = BOOT_SEED) -> tuple:
    """Percentile bootstrap 95 % interval for sd(a)/sd(b).

    A ratio interval containing 1.0 means the two arms are NOT distinguishable
    on consistency, and that is reported as such rather than rounded away.
    """
    rng = random.Random(seed)
    rs: list[float] = []
    for _ in range(n_boot):
        aa = [rng.choice(a) for _ in a]
        bb = [rng.choice(b) for _ in b]
        try:
            s = st.stdev(bb)
        except st.StatisticsError:
            continue
        if s > 0:
            rs.append(st.stdev(aa) / s)
    if not rs:
        return (float("nan"), float("nan"))
    rs.sort()
    return (rs[int(0.025 * len(rs))], rs[int(0.975 * len(rs))])


def analyse(problem: str = "P1", log: Optional[Path] = None) -> dict:
    log = LOG if log is None else log
    rows = load_summaries(path=log, problem=problem)
    g = group(rows)
    budgets = sorted({r["budget_sims"] for r in rows})

    arms = {}
    for (m, scr), vals in sorted(g.items()):
        if len(vals) < 2:
            continue
        mean = st.mean(vals)
        sd = st.stdev(vals)
        arms[f"{m}{'+screen' if scr else ''}"] = {
            "method": m, "prescreen": scr, "n": len(vals),
            "mean": mean, "sd": sd,
            "cv_pct": abs(sd / mean) * 100.0 if mean else None,
            "min": min(vals), "max": max(vals),
        }

    comparisons = []
    for A, B in PAIRS:
        if A not in g or B not in g:
            continue
        a, b = g[A], g[B]
        sa, sb = st.stdev(a), st.stdev(b)
        lo, hi = sd_ratio_ci(a, b)
        comparisons.append({
            "a": f"{A[0]}{'+screen' if A[1] else ''}",
            "b": f"{B[0]}{'+screen' if B[1] else ''}",
            "sd_a": sa, "sd_b": sb, "ratio": sa / sb,
            "ci95": [lo, hi],
            # The honest read: an interval spanning 1.0 is "not distinguishable".
            "distinguishable": bool(lo > 1.0 or hi < 1.0),
        })

    screen_effect = {}
    for m in sorted({k[0] for k in g}):
        if (m, False) in g and (m, True) in g and len(g[(m, False)]) > 1:
            off, on = st.stdev(g[(m, False)]), st.stdev(g[(m, True)])
            screen_effect[m] = {"sd_off": off, "sd_on": on,
                                "tighter_x": off / on if on else None}

    return {"task": "run-to-run consistency (proposal 002 criterion 4)",
            "source_log": log.name, "problem": problem, "role": "measured",
            "budgets": budgets, "n_boot": N_BOOT, "boot_seed": BOOT_SEED,
            "arms": arms, "comparisons": comparisons,
            "screen_effect_on_spread": screen_effect}


def _print(d: dict) -> None:
    print(f"Run-to-run consistency -- {d['problem']}, budget(s) {d['budgets']}, "
          f"role={d['role']}")
    print(f"source: {d['source_log']}")
    print()
    print(f"{'arm':16} {'n':>3} {'mean':>9} {'sd':>8} {'CV%':>6} "
          f"{'min':>9} {'max':>9}")
    for name, a in sorted(d["arms"].items(), key=lambda kv: kv[1]["sd"]):
        print(f"{name:16} {a['n']:3d} {a['mean']:9.4f} {a['sd']:8.4f} "
              f"{a['cv_pct']:6.1f} {a['min']:9.4f} {a['max']:9.4f}")
    print()
    print("Head to head (spread ratio, 95 % bootstrap CI):")
    for c in d["comparisons"]:
        verdict = "" if c["distinguishable"] else "   <- NOT distinguishable"
        print(f"  {c['a']:14} sd {c['sd_a']:.4f}  vs {c['b']:14} sd "
              f"{c['sd_b']:.4f}   {c['ratio']:6.2f}x  "
              f"[{c['ci95'][0]:.2f}, {c['ci95'][1]:.2f}]{verdict}")
    print()
    print("Pre-screen effect on spread:")
    for m, s in sorted(d["screen_effect_on_spread"].items(),
                       key=lambda kv: -(kv[1]["tighter_x"] or 0)):
        print(f"  {m:8} {s['sd_off']:.4f} -> {s['sd_on']:.4f}   "
              f"{s['tighter_x']:6.2f}x tighter")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--problem", default="P1")
    ap.add_argument("--ladder", action="store_true",
                    help="read the budget-ladder sweep (larger budget) instead")
    a = ap.parse_args(argv)
    if not a.run:
        ap.print_help()
        return 0
    log = LADDER_LOG if a.ladder else LOG
    d = analyse(problem=a.problem, log=log)
    _print(d)
    out = results_path(a.problem, log)
    out.write_text(json.dumps(d, indent=1), encoding="utf-8")
    print(f"\nwrote {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
