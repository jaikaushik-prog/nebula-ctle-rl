"""
experiments/exp_budget_ladder.py — **does PPO learn if you give it more
simulations, or is the gradient simply pointing the wrong way?**

THE QUESTION
------------
`PREDICTIONS.md` entries 12 and 13 left PPO with two live explanations and no
way to choose between them:

  (a) **starved.** 150 simulations buys ~96 environment steps and, at
      `rollout_steps = 64`, **ONE** policy update. A method that gets one
      gradient step has not been tested.
  (b) **misdirected.** Entry 13 measured that the policy DOES move -- the mean
      action travels 0.167 -> 0.389 as the update count goes 2 -> 12 -- while
      the design does not improve. That is an *uninformative* gradient, and
      more of it buys more travel in a direction that is not up.

**Only the budget distinguishes them.** Under (a) the curve should bend upward
once the update count reaches double digits; under (b) it should not, however
long you run.

WHY THIS IS ONE LONG RUN AND NOT A LADDER OF SHORT ONES
--------------------------------------------------------
The obvious design is separate runs at 200, 250, 300, 350... **and it would be
pure waste here.** Nothing in PPO's configuration depends on the budget:
`method_ppo` fixes `steps = 100_000` precisely so that the SIMULATION budget is
what stops the run, `PPOConfig.lr` is a constant, and there is no schedule
annealed against a horizon. The seed comes from `run_seed(problem, method,
replicate)`, which does not see the budget either.

**So for a given seed the trajectory is identical up to wherever it stops.** A
run at 2400 simulations *contains* the run at 150, 300, 600 and 1200, exactly.
And `anytime_curve` already records the best-so-far after every single
simulation, so the whole ladder is read off one curve for free.

That claim is not assumed. `--verify-prefix` checks the first 150 entries of
every curve here against the corresponding run in the published grid sweep and
requires them equal at rel = 0.

WHY THERE IS A CONTROL, AND WHY IT IS THE POINT
------------------------------------------------
**PPO compared only against itself will trend upward whether or not it is
learning**, because more simulations is more lottery tickets and every method
improves with budget -- uniform random most obviously of all. A rising PPO
curve on its own says nothing.

The quantity that answers the question is the **gap to uniform random as a
function of budget**:

    learning       ->  the gap shrinks and eventually flips sign
    not learning   ->  the gap is flat, or widens

`cmaes` rides along as the strong classical reference: it answers the third
question, which is whether ANY method is still improving at 2400 or whether the
problem is simply solved by then. If uniform saturates, the finding is not "RL
lost" but **"there was nothing left to win at this budget"**, and the response
is to make the problem harder rather than the policy better.

WHAT IS DELIBERATELY NOT HERE
-------------------------------
* **No pre-screened arms.** The screen changes how many *proposals* a
  simulation buys, which is a different axis from the one under test, and it
  would double a 2-hour run for nothing.
* **No warm-up and no timing control.** The metric is score against
  simulations; wall clock is not reported, so 7g's control would cost ~29 % of
  the run to protect a number this file does not quote.
* **P1 only.** `CtleSizingEnv` takes one corner and one load, so PPO cannot run
  the robust rungs at all (see `baselines.method_ppo`).

USAGE
    python -m nebula.experiments.exp_budget_ladder --budget      # no SPICE
    python -m nebula.experiments.exp_budget_ladder --run         # ~2 h
    python -m nebula.experiments.exp_budget_ladder --analyse
    python -m nebula.experiments.exp_budget_ladder --verify-prefix
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from nebula.experiments import baselines as B

HERE = Path(__file__).resolve().parent

#: The top of the ladder. 16x the published 150, chosen against the measured
#: noise rather than against a round number: PPO's seed spread at 150 is
#: ~0.12 wide (`BASELINES.md` §13's CI), and entry 12 measured that an 11x
#: increase in UPDATES moved the score by 0.0106 -- six times smaller. A ladder
#: whose rungs are 50 simulations apart cannot resolve anything at that ratio,
#: so the rungs multiply instead of adding.
LADDER_BUDGET: int = 2400

#: Where the curve is read. Powers of two off the published budget, so every
#: rung is a doubling and the x-axis is log-spaced by construction.
READOUTS: tuple[int, ...] = (150, 300, 600, 1200, 2400)

#: The arms. `ppo` is the subject, `uniform` is the control that makes the
#: trend interpretable, `cmaes` says whether anything is still improving.
#: Seed counts match `baselines.REPLICATES` exactly -- changing them would make
#: this a comparison of sample sizes.
ARMS: tuple[str, ...] = ("ppo", "uniform", "cmaes")

LOG_PATH = HERE / "budget_ladder_run.jsonl"
OUT_PATH = HERE / "budget_ladder_results.json"

#: The published 150-simulation sweep, for `--verify-prefix`.
REFERENCE_LOG = HERE / "baselines_run_interp_grid.jsonl.gz"


#: Entry 12's measurement, not an estimate made here: a third of PPO's budget
#: goes on episode resets, so one environment step costs this many simulations.
SIMS_PER_ENV_STEP: float = 1.57


def _ppo_rollout_default() -> int:
    """`PPOConfig`'s own value. **Imported, never restated** (rule 9).

    Lazy because `rl.ppo` pulls in torch, which `baselines.method_ppo` also
    imports lazily. If torch is missing this RAISES rather than substituting a
    remembered 64 -- an update count is a number in a report.
    """
    from nebula.rl.ppo import PPOConfig

    return int(PPOConfig(seed=0).rollout_steps)


def allocation(budget: int = LADDER_BUDGET) -> tuple[B.Allocation, ...]:
    """P1, no pre-screen, three arms at the ladder budget."""
    return tuple(B.Allocation("P1", m, False, B.REPLICATES[m], int(budget))
                 for m in ARMS)


def budget_report(budget: int = LADDER_BUDGET) -> dict:
    """The cost, computed. No SPICE."""
    alloc = allocation(budget)
    sims = sum(a.sims for a in alloc)
    est = sims * B.SEC_PER_SIM_AT_8
    return {
        "budget_sims_per_run": int(budget),
        "arms": {a.method: a.replicates for a in alloc},
        "n_runs": sum(a.replicates for a in alloc),
        "total_sims": sims,
        "hours_optimistic": est / 3600.0,
        "hours_pessimistic": sims * B.SEC_PER_SIM_AT_8_LATTICE / 3600.0,
        "readouts": list(READOUTS),
        "control_and_warmup": False,
        "note": ("no warm-up and no timing control: the metric is score "
                 "against SIMULATIONS and no wall-clock number is quoted, so "
                 "7g's control would cost ~29 % of the run to protect nothing "
                 "this file reports."),
        # What the budget buys PPO, which is the mechanism under test. 1.57
        # simulations per environment step and 1/3 of the budget going to
        # episode resets are entry 12's measurements, not estimates made here.
        "ppo_rollout_steps": _ppo_rollout_default(),
        "ppo_updates_at_readout": {
            str(n): int(max(1, (n / SIMS_PER_ENV_STEP)
                            // _ppo_rollout_default()))
            for n in READOUTS
        },
    }


def run(budget: int = LADDER_BUDGET, workers: int = B.WORKERS) -> dict:
    """The run. Reuses `baselines.sweep` so every 7f fairness rule holds."""
    return B.sweep(allocation(budget), log_path=LOG_PATH, out_path=OUT_PATH,
                   workers=workers, control=False, ac_peak_interp=True)


# ─────────────────────────────────────────────────────────────────────────────
# Read-out
# ─────────────────────────────────────────────────────────────────────────────


def _curves(results: dict) -> dict[str, list[list[float]]]:
    out: dict[str, list[list[float]]] = {}
    for r in results["runs"]:
        if r.get("role", "measured") != "measured":
            continue
        out.setdefault(r["method"], []).append(r["curve"])
    return out


def ladder(results: dict, readouts: Sequence[int] = READOUTS) -> dict:
    """Median best-so-far per arm at each rung, with intervals and the gap.

    The gap to `uniform` is the number the experiment exists to produce. It is
    reported as a difference of medians with a bootstrap interval, and the
    seeds are NOT paired across arms -- different methods draw different
    numbers of seeds by design, so a paired statistic would be a fiction.
    """
    cur = _curves(results)
    rows: dict[str, dict] = {}
    for method, cs in cur.items():
        arr = np.asarray(cs, dtype=float)
        per_readout = {}
        for n in readouts:
            if n > arr.shape[1]:
                continue
            col = arr[:, n - 1]
            col = np.where(np.isfinite(col), col, np.nan)
            med, lo, hi = B.bootstrap_median(
                [v for v in col if np.isfinite(v)],
                rng=np.random.default_rng(B.group_seed(f"{method}@{n}")))
            # is it still moving? the gain over the final third of THIS rung
            third = max(1, n // 3)
            gain = np.nanmedian(arr[:, n - 1] - arr[:, n - third - 1])
            per_readout[str(n)] = {
                "median": float(med), "ci": [float(lo), float(hi)],
                "n_seeds": int(arr.shape[0]),
                "gain_over_final_third": float(gain),
            }
        rows[method] = per_readout

    # ── the saturation-robust read-out, and the headline ────────────────────
    #
    # **The raw gap is a trap at large budgets.** The reward has an asymptote
    # near +9.0, so as the budget grows EVERY method compresses toward it and
    # the difference between any two shrinks -- which would look exactly like
    # "PPO is catching up" and would be an artifact of the ceiling, not of
    # learning. G74's ceiling was removed at `dec 50`; the reward is still
    # bounded above.
    #
    # So the primary metric is stated in the control's own units: **how many
    # UNIFORM RANDOM simulations buy the score this method reached in n?**
    #
    #     ratio < 1   the method is worth less than random guessing
    #     ratio = 1   it is random guessing
    #     ratio > 1   it is buying something
    #
    # Computed on the published 150-simulation sweep this reads PPO **0.720x**
    # (150 policy simulations are worth 108 random ones), grid 0.540x, LHS
    # 0.960x and CMA-ES above 1.0 (uniform never catches it inside 150). If
    # PPO is merely STARVED, this ratio must climb through 1.0 as the budget
    # grows. If the gradient is misdirected, it will not.
    equiv: dict[str, dict[str, dict]] = {}
    if "uniform" in cur:
        u = np.asarray(cur["uniform"], float)
        umed = np.nanmedian(np.where(np.isfinite(u), u, np.nan), axis=0)
        for method, cs in cur.items():
            arr = np.asarray(cs, float)
            mmed = np.nanmedian(np.where(np.isfinite(arr), arr, np.nan), axis=0)
            per = {}
            for n in readouts:
                if n > mmed.size:
                    continue
                target = float(mmed[n - 1])
                if not math.isfinite(target):
                    continue
                reached = np.flatnonzero(umed >= target)
                if reached.size == 0:
                    # CENSORED, and reported as censored rather than as the
                    # budget: uniform never got there inside its own run.
                    per[str(n)] = {"target": target, "uniform_sims": None,
                                   "ratio": None, "censored": True,
                                   "censored_at": int(umed.size)}
                else:
                    k = int(reached[0]) + 1
                    per[str(n)] = {"target": target, "uniform_sims": k,
                                   "ratio": k / float(n), "censored": False}
            equiv[method] = per

    gaps = {}
    if "ppo" in cur and "uniform" in cur:
        p = np.asarray(cur["ppo"], float)
        u = np.asarray(cur["uniform"], float)
        for n in readouts:
            if n > min(p.shape[1], u.shape[1]):
                continue
            gp = float(np.nanmedian(p[:, n - 1]))
            gu = float(np.nanmedian(u[:, n - 1]))
            ci_p = rows["ppo"][str(n)]["ci"]
            ci_u = rows["uniform"][str(n)]["ci"]
            gaps[str(n)] = {
                "ppo_minus_uniform": gp - gu,
                "separable": B.separable(tuple(ci_p), tuple(ci_u)),
            }
    return {"per_arm": rows, "ppo_vs_uniform": gaps,
            "random_equivalent_budget": equiv, "readouts": list(readouts)}


def verify_prefix(results: dict, reference: Path = REFERENCE_LOG,
                  n: int = 150) -> dict:
    """**The design claim, checked rather than argued.**

    If a long run really contains the short ones, every curve here must agree
    with the published 150-simulation sweep over its first `n` entries, at
    rel = 0. If it does not, the budget IS a configuration for some method and
    the ladder must be run rung by rung after all.
    """
    ref: dict[tuple[str, int], list[float]] = {}
    opener = gzip.open if reference.suffix == ".gz" else open
    with opener(reference, "rt", encoding="utf-8") as f:
        trials: dict[tuple[str, int], list] = {}
        for line in f:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("event") != "trial" or row.get("role") != "measured":
                continue
            if row.get("prescreen") or row.get("problem") != "P1":
                continue
            if row["method"] not in ARMS:
                continue
            trials.setdefault((row["method"], row["replicate"]), []).append(row)
    for key, rows in trials.items():
        rows.sort(key=lambda r: r["index"])
        ts = [B.Trial(**{k: v for k, v in r.items()
                         if k in B.Trial.__dataclass_fields__}) for r in rows]
        # **Build at the reference run's OWN budget, then slice.**
        # `anytime_curve(trials, budget)` clamps `cum_sims` to `budget`
        # (`lo = min(cum_sims, budget)`), so handing it a short budget with a
        # long trial list folds EVERY later trial's best into the last cell.
        # Calling it with n = 30 on a 150-simulation run reported 34 of 40
        # curves as mismatched, with a worst difference of 9.18 -- a
        # disagreement manufactured entirely by the instrument. Same family as
        # the session 22g probe that spent the budget it was measuring.
        full = max((int(t.cum_sims) for t in ts), default=n)
        ref[key] = [float(v) for v in B.anytime_curve(ts, max(full, n))]

    checked = mismatched = 0
    worst = 0.0
    misses: list[str] = []
    for r in results["runs"]:
        if r.get("role", "measured") != "measured":
            continue
        key = (r["method"], r["replicate"])
        if key not in ref:
            continue
        m = min(n, len(ref[key]), len(r["curve"]))
        a = np.asarray(ref[key][:m], float)
        b = np.asarray(r["curve"][:m], float)
        checked += 1
        both = np.isfinite(a) & np.isfinite(b)
        d = float(np.max(np.abs(a[both] - b[both]))) if both.any() else 0.0
        if d > 0.0 or (np.isfinite(a) != np.isfinite(b)).any():
            mismatched += 1
            misses.append(f"{key[0]}/{key[1]} max|d| = {d:.3e}")
        worst = max(worst, d)
    return {"n_checked": checked, "n_mismatched": mismatched,
            "worst_abs_diff": worst, "examples": misses[:10],
            "reference": str(reference), "prefix": n,
            "verdict": ("the long run CONTAINS the short ones"
                        if checked and not mismatched
                        else "PREFIXES DISAGREE -- the ladder cannot be read "
                             "off one curve")}


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────


def print_budget(b: dict) -> None:
    print("\n" + "=" * 78)
    print("BUDGET LADDER -- cost, computed")
    print("=" * 78)
    print(f"  budget per run   {b['budget_sims_per_run']} simulations")
    print("  arms             " + ", ".join(f"{k} x{v}"
                                            for k, v in b["arms"].items()))
    print(f"  runs             {b['n_runs']}")
    print(f"  simulations      {b['total_sims']:,}")
    print(f"  estimate         {b['hours_optimistic']:.2f} h "
          f"- {b['hours_pessimistic']:.2f} h")
    print(f"  read out at      {b['readouts']}")
    print("  PPO policy updates bought at each rung (rollout_steps = 64):")
    for k, v in b["ppo_updates_at_readout"].items():
        print(f"     {k:>6} sims -> ~{v} updates")
    print()
    print("  " + b["note"].replace(". ", ".\n  "))
    print()


def print_ladder(a: dict) -> None:
    print("\n" + "=" * 78)
    print("THE LADDER -- median best-so-far against simulations spent")
    print("=" * 78)
    hdr = "  " + "arm".ljust(10) + "".join(f"{n:>18}" for n in a["readouts"])
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for m, per in a["per_arm"].items():
        cells = []
        for n in a["readouts"]:
            d = per.get(str(n))
            cells.append("--".rjust(18) if d is None
                         else f"{d['median']:.4f}".rjust(18))
        print("  " + m.ljust(10) + "".join(cells))
    print()
    print("  STILL IMPROVING? median gain over the final third of each rung")
    for m, per in a["per_arm"].items():
        cells = []
        for n in a["readouts"]:
            d = per.get(str(n))
            cells.append("--".rjust(18) if d is None
                         else f"{d['gain_over_final_third']:+.4f}".rjust(18))
        print("  " + m.ljust(10) + "".join(cells))
    print()
    print("  RANDOM-EQUIVALENT BUDGET -- how many UNIFORM simulations buy")
    print("  what this arm reached in n. <1 means worse than guessing.")
    hdr2 = "  " + "arm".ljust(10) + "".join(f"{n:>18}" for n in a["readouts"])
    print(hdr2)
    print("  " + "-" * (len(hdr2) - 2))
    for m, per in a.get("random_equivalent_budget", {}).items():
        cells = []
        for n in a["readouts"]:
            d = per.get(str(n))
            if d is None:
                cells.append("--".rjust(18))
            elif d["censored"]:
                cells.append(f">{d['censored_at'] / n:.2f}x".rjust(18))
            else:
                cells.append(f"{d['ratio']:.3f}x".rjust(18))
        print("  " + m.ljust(10) + "".join(cells))
    print()
    print("  THE RAW GAP: PPO minus UNIFORM RANDOM at each budget")
    print("    read with care -- the reward saturates near +9.0, so this")
    print("    shrinks with budget whether or not anything is learned")
    print("    negative = RL is behind random search")
    for n in a["readouts"]:
        g = a["ppo_vs_uniform"].get(str(n))
        if g is None:
            continue
        tag = "separable" if g["separable"] else "NOT separable"
        print(f"     {n:>6} sims   {g['ppo_minus_uniform']:+.4f}   ({tag})")
    print()


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--budget", action="store_true", help="cost only, no SPICE")
    ap.add_argument("--run", action="store_true", help="the ~2 h run")
    ap.add_argument("--analyse", action="store_true",
                    help="read the ladder off the saved curves")
    ap.add_argument("--verify-prefix", action="store_true",
                    help="check the long run contains the published short ones")
    ap.add_argument("--ladder-budget", type=int, default=LADDER_BUDGET)
    ap.add_argument("--workers", type=int, default=B.WORKERS)
    args = ap.parse_args(argv)

    if not any((args.budget, args.run, args.analyse, args.verify_prefix)):
        ap.error("choose a stage; see the module docstring")

    out: dict = {}
    if args.budget:
        b = budget_report(args.ladder_budget)
        print_budget(b)
        out["budget"] = b
    if args.run:
        res = run(args.ladder_budget, workers=args.workers)
        a = ladder(res)
        print_ladder(a)
        out["ladder"] = a
    if (args.analyse or args.verify_prefix) and not args.run:
        if not OUT_PATH.exists():
            print(f"no results at {OUT_PATH}; run --run first")
            return 1
        res = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        if args.analyse:
            a = ladder(res)
            print_ladder(a)
            out["ladder"] = a
        if args.verify_prefix:
            v = verify_prefix(res)
            print("\n  PREFIX CHECK against " + Path(v["reference"]).name)
            print(f"    curves checked   {v['n_checked']}")
            print(f"    mismatched       {v['n_mismatched']}")
            print(f"    worst |diff|     {v['worst_abs_diff']:.3e}")
            for e in v["examples"]:
                print(f"      {e}")
            print(f"    -> {v['verdict']}\n")
            out["prefix_check"] = v
    if out:
        p = HERE / "budget_ladder_summary.json"
        p.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
        print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
