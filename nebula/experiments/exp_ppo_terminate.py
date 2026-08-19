"""
experiments/exp_ppo_terminate.py — **PPO is trained on a different objective
from the one it is scored on. This removes the mismatch and measures what it
was worth.**

THE DEFECT, IN TWO LINES
-------------------------
`rl/env.py`:

    terminated = bool(rb.feasible)     # early success

`rl/reward_v1.py`, feasible branch:

    reward = B + min_i(margin_i / tol_i)      # how far PAST the band you get

**The episode ends the instant every spec is met, and the metric rewards
exactly what happens after that.** The policy is never once in a state where it
could learn to improve a design that already works -- that region is terminal.

MEASURED ON THE PUBLISHED SWEEP, NOT INFERRED
-----------------------------------------------
Ten unscreened PPO runs at 150 simulations: a median of **11.5 feasible
designs**. Each of those ended its episode, and `CtleSizingEnv.reset` then drew
a fresh **uniform-random** start. So the run is

    random start -> short walk -> hits feasibility -> STOP -> random restart

about twelve times in 150 simulations. **Random restarts plus a short walk that
stops at "good enough" is structurally a random search** -- which is precisely
what `BASELINES.md` §14 measured PPO to be, at every budget from 150 to 2400.

`CONTINUE_HERE.md` §5 item 3 flagged this as an open decision. Nobody tested it.

WHAT THIS CHANGES, AND WHAT IT DOES NOT
-----------------------------------------
`method_ppo(terminate_on_feasible=False)` suppresses termination **only on a
valid, feasible evaluation**. An invalid measurement still ends the episode --
there is no observation to continue from (§6d) -- and the horizon still
truncates. Nothing else moves: same `PPOConfig`, same box, same evaluator, same
reward, same seeds. The flag defaults to the published behaviour, so no
existing number changes.

THE MECHANISM CHECK COMES BEFORE THE OUTCOME
----------------------------------------------
`steps_from_feasible` counts environment steps taken FROM a state that already
met every spec. In the control it is **near zero but not exactly zero** -- a
`reset()` can land on a feasible design and the first step out of it precedes
any termination -- so the claim is *"the control cannot accumulate
feasible-state experience"*, not *"the counter is zero"*. A 60-simulation smoke
run measured one such step in the control against three in the treatment.

If the treatment does not raise it well above the control, the flag did not do
what it claims and the outcome is meaningless -- so that number is reported
first, and an outcome without it is not read.

USAGE
    python -m nebula.experiments.exp_ppo_terminate --budget   # cost, no SPICE
    python -m nebula.experiments.exp_ppo_terminate --run      # ~25 min
    python -m nebula.experiments.exp_ppo_terminate --analyse
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from nebula.experiments import baselines as B

HERE = Path(__file__).resolve().parent
OUT_PATH = HERE / "ppo_terminate_results.json"

#: Both budgets matter and they answer different questions. **150** is where G3
#: is scored and where PPO loses to uniform by 0.0426. **600** is where
#: `BASELINES.md` §14 measured PPO to have closed the gap to random search --
#: so if the mismatch is the binding defect, its removal should show at BOTH,
#: and if it only shows at 600 the effect is about experience rather than about
#: the objective.
BUDGETS: tuple[int, ...] = (150, 600)

#: Matches `baselines.REPLICATES["ppo"]` exactly. Changing it would make this a
#: comparison of sample sizes.
N_SEEDS: int = 10


@dataclass
class Run:
    budget: int
    terminate_on_feasible: bool
    replicate: int
    seed: int
    best_reward: float
    n_sims: int
    n_feasible: int
    curve: list
    diagnostics: dict
    wall_s: float


def _job(args) -> dict:
    budget, terminate, rep = args
    try:                                                    # pragma: no cover
        import torch

        torch.set_num_threads(1)
    except Exception:                                       # pragma: no cover
        pass
    # **The published seed protocol, unchanged.** So the control arm at 150 is
    # a bit-for-bit re-run of the sweep's PPO arm and reproducing its median is
    # a free correctness check on this whole harness.
    seed = B.run_seed("P1", "ppo", rep)
    rng = np.random.default_rng(seed)
    obj = B.Objective(B.PROBLEMS["P1"], budget, ac_peak_interp=True)
    t0 = time.perf_counter()
    try:
        B.method_ppo(obj, rng, terminate_on_feasible=terminate)
    except B.BudgetExhausted:
        pass
    # read from the OBJECTIVE, not from the return value: the budget raises
    # from inside PPO's rollout, so a normally-completing run never returns.
    diag: dict = dict(obj.method_diagnostics)
    wall = time.perf_counter() - t0
    s = obj.summary()
    return asdict(Run(
        budget=budget, terminate_on_feasible=terminate, replicate=rep,
        seed=seed, best_reward=float(s["best_reward"]),
        n_sims=int(s["n_sims"]), n_feasible=int(s["n_feasible"]),
        curve=[float(v) for v in B.anytime_curve(obj.trials, budget)],
        diagnostics=diag, wall_s=wall))


def budget_report() -> dict:
    total = sum(2 * N_SEEDS * b for b in BUDGETS)
    return {"budgets": list(BUDGETS), "arms": 2, "seeds_per_arm": N_SEEDS,
            "n_runs": len(BUDGETS) * 2 * N_SEEDS, "total_sims": total,
            "hours_optimistic": total * B.SEC_PER_SIM_AT_8 / 3600.0,
            "hours_pessimistic": total * B.SEC_PER_SIM_AT_8_LATTICE / 3600.0}


def run(workers: int = B.WORKERS) -> dict:
    from concurrent.futures import ProcessPoolExecutor, as_completed

    jobs = [(b, t, r) for b in BUDGETS for t in (True, False)
            for r in range(N_SEEDS)]
    rows: list[dict] = []
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_job, j): j for j in jobs}
        for i, fut in enumerate(as_completed(futs), start=1):
            r = fut.result()
            rows.append(r)
            print(f"  [{i:>3}/{len(jobs)}] budget {r['budget']:>4}  "
                  f"terminate={str(r['terminate_on_feasible']):<5} "
                  f"rep {r['replicate']:>2}  best {r['best_reward']:.4f}  "
                  f"feasible-steps "
                  f"{r['diagnostics'].get('steps_from_feasible', 0):>3}  "
                  f"{r['wall_s']:.0f} s", flush=True)
    out = {"task": "PPO trained on the objective it is scored on",
           "budgets": list(BUDGETS), "n_seeds": N_SEEDS,
           "wall_s": time.perf_counter() - t0,
           "provenance": B.provenance(), "runs": rows}
    out["analysis"] = analyse(out)
    OUT_PATH.write_text(json.dumps(out, indent=1, default=str),
                        encoding="utf-8")
    print(f"wrote {OUT_PATH}")
    return out


def analyse(res: dict) -> dict:
    rows = res["runs"]
    out: dict = {"per_budget": {}}
    for b in sorted({r["budget"] for r in rows}):
        arms = {}
        for t in (True, False):
            sel = [r for r in rows if r["budget"] == b
                   and r["terminate_on_feasible"] is t]
            if not sel:
                continue
            best = [r["best_reward"] for r in sel]
            med, lo, hi = B.bootstrap_median(
                best, rng=np.random.default_rng(
                    B.group_seed(f"terminate={t}@{b}")))
            curves = np.asarray([r["curve"] for r in sel], dtype=float)
            third = max(1, b // 3)
            gain = float(np.nanmedian(curves[:, -1] - curves[:, -third - 1]))
            steps = [r["diagnostics"].get("steps_from_feasible", 0)
                     for r in sel]
            frac = [r["diagnostics"].get("fraction_of_steps_from_feasible", 0.0)
                    for r in sel]
            arms[str(t)] = {
                "n": len(sel), "median_best": float(med),
                "ci": [float(lo), float(hi)],
                "gain_over_final_third": gain,
                "median_steps_from_feasible": float(np.median(steps)),
                "median_fraction_from_feasible": float(np.median(frac)),
                "median_episodes": float(np.median(
                    [r["diagnostics"].get("n_episodes", 0) for r in sel])),
                "median_n_feasible": float(np.median(
                    [r["n_feasible"] for r in sel])),
            }
        if "True" in arms and "False" in arms:
            arms["delta"] = arms["False"]["median_best"] - arms["True"]["median_best"]
            arms["separable"] = B.separable(tuple(arms["True"]["ci"]),
                                            tuple(arms["False"]["ci"]))
        out["per_budget"][str(b)] = arms
    return out


def print_report(res: dict) -> None:
    a = res["analysis"]["per_budget"]
    print("\n" + "=" * 76)
    print("PPO TRAINED ON THE OBJECTIVE IT IS SCORED ON")
    print("=" * 76)
    print("  MECHANISM CHECK FIRST -- steps taken FROM a feasible state.")
    print("  The control is NEAR zero (a reset can land feasible); if the")
    print("  treatment is not well above it, the flag did nothing and the")
    print("  outcome is void.")
    print(f"  {'budget':>7} {'arm':<22} {'steps':>8} {'fraction':>10} "
          f"{'episodes':>9}")
    for b, arms in a.items():
        for t, label in (("True", "terminate (control)"),
                         ("False", "keep going (fix)")):
            d = arms.get(t)
            if d:
                print(f"  {b:>7} {label:<22} "
                      f"{d['median_steps_from_feasible']:>8.0f} "
                      f"{d['median_fraction_from_feasible']:>10.3f} "
                      f"{d['median_episodes']:>9.0f}")
    print()
    print("  OUTCOME -- median best reward")
    print(f"  {'budget':>7} {'control':>10} {'fixed':>10} {'delta':>9}  "
          f"separable?")
    for b, arms in a.items():
        if "delta" not in arms:
            continue
        print(f"  {b:>7} {arms['True']['median_best']:>10.4f} "
              f"{arms['False']['median_best']:>10.4f} "
              f"{arms['delta']:>+9.4f}  "
              f"{'YES' if arms['separable'] else 'not separable'}")
    print()
    print("  STILL CLIMBING? median gain over the final third")
    for b, arms in a.items():
        if "delta" not in arms:
            continue
        print(f"  {b:>7} control {arms['True']['gain_over_final_third']:+.4f}"
              f"    fixed {arms['False']['gain_over_final_third']:+.4f}")
    print()
    print("  Comparators from BASELINES.md sec 14, same seeds and objective:")
    print("      150 sims   uniform 8.9532   cmaes 8.9736   ppo 8.9106")
    print("      600 sims   uniform 8.9860   cmaes 8.9993   ppo 8.9844")
    print()


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--budget", action="store_true", help="cost only, no SPICE")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--analyse", action="store_true")
    ap.add_argument("--workers", type=int, default=B.WORKERS)
    args = ap.parse_args(argv)
    if not any((args.budget, args.run, args.analyse)):
        ap.error("choose a stage")

    if args.budget:
        b = budget_report()
        print(f"\n  {b['n_runs']} runs, {b['total_sims']:,} simulations, "
              f"{b['hours_optimistic']:.2f}-{b['hours_pessimistic']:.2f} h\n")
    if args.run:
        print_report(run(workers=args.workers))
    elif args.analyse:
        if not OUT_PATH.exists():
            print(f"no results at {OUT_PATH}; run --run first")
            return 1
        res = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        res["analysis"] = analyse(res)
        print_report(res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
