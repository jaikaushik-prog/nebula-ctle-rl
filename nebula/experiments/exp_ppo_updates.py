"""
experiments/exp_ppo_updates.py -- session 22g. **How many gradient updates does
PPO actually get, and does giving it more help?**

THE MEASUREMENT THAT PROMPTED THIS
-----------------------------------
The G3 sweep ranked PPO last of five methods on P1 (`BASELINES.md` §12,
median 8.91063 against uniform random's 8.95319). The obvious reading -- and the
one this session first wrote down -- was **exploration collapse**. It is wrong,
and the instrumented run says so:

    entropy per update   9.942 -> 9.952 -> 9.956      RISES
    final log_std        ~0.005 in every dimension    UNCHANGED from init

Nothing collapses. What the same run measured instead:

    simulations spent    235 for 150 environment steps   = 1.57 sims/step
    policy updates       3   (rollout_steps = 64)

**A third of the budget goes on episode RESETS**, because `CtleSizingEnv.reset`
simulates a fresh start point and an invalid evaluation ends the episode
immediately -- 38 episodes in 150 steps, many of length 1. So the sweep's
150-simulation budget buys PPO roughly **96 environment steps**, and at
`rollout_steps = 64` that is **ONE policy update**.

"PPO came last" therefore means "PPO performed one gradient update". It is not
stuck; it has barely started.

WHAT THIS FILE VARIES, AND WHAT IT HOLDS FIXED
-----------------------------------------------
**One knob: `rollout_steps`.** Everything else is the sweep's -- same
`Objective`, same `_ObjectiveEnv`, same `method_ppo`, same seed rule
(`baselines.run_seed`), same box, same specs, same 150-simulation budget, same
interpolated objective. The `rollout_steps = 64` arm is the CONTROL and must
reproduce the sweep's PPO numbers exactly; if it does not, nothing else here
transfers and the run is void.

**No reward, spec, box or tolerance is touched.** `rollout_steps` is a PPO
hyperparameter, which `PLAN.md` §4 assigns as work to be done rather than as a
human decision -- unlike the two follow-on candidates (stop simulating on
reset; stop ending the episode at first feasibility), which change the
environment contract and are B's.

USAGE
    python -m nebula.experiments.exp_ppo_updates --run
    python -m nebula.experiments.exp_ppo_updates --analyse
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from nebula.experiments.baselines import (
    BUDGET_SIMS,
    BudgetExhausted,
    Objective,
    PROBLEMS,
    bootstrap_median,
    method_ppo,
    run_seed,
)
from nebula.rl import reward_v1 as R

HERE = Path(__file__).resolve().parent
LOG_PATH: Path = HERE / "ppo_updates_run.jsonl"

#: The arms. `64` is `PPOConfig.rollout_steps`'s default and therefore the
#: sweep's own configuration -- it is the CONTROL, not an arm.
ROLLOUT_STEPS: tuple[int, ...] = (64, 32, 16, 8)

#: Replicates per arm. **10, because that is what the sweep gave PPO**
#: (`baselines.REPLICATES["ppo"]`), and the control arm has to be comparable
#: seed for seed rather than merely in distribution.
REPLICATES: int = 10

#: Environment steps a 150-simulation budget buys, measured: 235 simulations
#: for 150 steps in the instrumented run, so 150 / 1.567. Used only to predict
#: the update count; the runs report the actual figure.
SIMS_PER_STEP: float = 235.0 / 150.0


def provenance() -> dict:
    def _git(*a: str) -> Optional[str]:
        try:
            return subprocess.run(["git", *a], cwd=str(HERE), capture_output=True,
                                  text=True, timeout=20).stdout.strip() or None
        except Exception:                                   # noqa: BLE001
            return None
    head = _git("rev-parse", "HEAD")
    return {"commit": head, "commit_short": head[:7] if head else None,
            "dirty": bool(_git("status", "--porcelain"))}


def expected_updates(rollout_steps: int, budget: int = BUDGET_SIMS) -> int:
    """How many policy updates a budget buys, from the MEASURED sims-per-step.

    Reported beside every arm so "more updates helped" is checkable against the
    number of updates rather than against the knob that was turned.
    """
    return int(budget / SIMS_PER_STEP) // int(rollout_steps)


def run_one(rollout_steps: int, replicate: int,
            budget_sims: int = BUDGET_SIMS) -> dict:
    """One PPO run at one `rollout_steps`. **Identical to the sweep otherwise.**

    The seed comes from `baselines.run_seed("P1", "ppo", replicate)` -- the
    sweep's own rule -- so the control arm is the same run, seed for seed.
    """
    seed = run_seed("P1", "ppo", replicate)
    rng = np.random.default_rng(seed)
    obj = Objective(PROBLEMS["P1"], budget_sims=budget_sims, prescreen=False,
                    ac_peak_interp=True)
    t0 = time.perf_counter()
    try:
        method_ppo(obj, rng, rollout_steps=rollout_steps)
    except BudgetExhausted:
        pass
    wall = time.perf_counter() - t0
    s = obj.summary()
    sim = [t for t in obj.trials if t.n_sims > 0]
    return {
        "kind": "run", "rollout_steps": int(rollout_steps),
        "replicate": int(replicate), "seed": seed,
        "budget_sims": budget_sims,
        "n_sims": obj.n_sims, "n_proposals": len(obj.trials),
        "n_simulated": len(sim),
        "best_reward": s["best_reward"],
        "n_feasible": s["n_feasible"],
        "sims_to_first_feasible": s["sims_to_first_feasible"],
        "invalid_rate": s["invalid_rate"],
        "invalid_reasons": s["invalid_reasons"],
        "n_interp_refused": obj.n_interp_refused,
        "wall_s": round(wall, 2),
        "sec_per_sim": (wall / obj.n_sims if obj.n_sims else None),
    }


def run(arms: Sequence[int] = ROLLOUT_STEPS, replicates: int = REPLICATES,
        out_path: Path = LOG_PATH) -> Path:
    """Every arm x every replicate, INTERLEAVED and shuffled (7g).

    Shuffled over individual jobs rather than over arms, so no arm is
    systematically early: G71 is this project's own gotcha about the first
    configuration paying the cold cache whichever one it is.
    """
    jobs = [(rs, rep) for rs in arms for rep in range(replicates)]
    np.random.default_rng(20260819).shuffle(jobs)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    with out_path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "schema_version": 1, "kind": "header",
            "experiment": "PPO rollout_steps -- how many updates does the "
                          "budget buy, and does giving it more help",
            "arms": list(arms), "replicates": replicates,
            "control_arm": 64,
            "budget_sims": BUDGET_SIMS,
            "sims_per_step_measured": SIMS_PER_STEP,
            "expected_updates": {str(rs): expected_updates(rs) for rs in arms},
            "held_fixed": "Objective, _ObjectiveEnv, method_ppo, run_seed, the "
                          "box, V1_SPECS, the tolerances, ac_peak_interp=True, "
                          "budget 150. Only rollout_steps varies.",
            "job_order": [f"{rs}/{rep}" for rs, rep in jobs],
            "written_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            **provenance(),
        }) + "\n")
        for i, (rs, rep) in enumerate(jobs, start=1):
            r = run_one(rs, rep)
            fh.write(json.dumps(r) + "\n")
            fh.flush()
            print(f"  [{i:>3}/{len(jobs)}] rollout={rs:<3} rep {rep:>2}  "
                  f"best {r['best_reward']:.5f}  sims {r['n_sims']}  "
                  f"{r['wall_s']:.1f} s", flush=True)
    print(f"\n-> {out_path}  ({time.perf_counter() - t0:.1f} s)")
    return out_path


# ─────────────────────────────────────────────────────────────────────────────
# The INSTRUMENTED arm -- did the policy move AT ALL?
#
# `--run` answers "does the final number improve" (it does, by +0.0106, and not
# separably). It does NOT answer the question the owner asked: **is the policy
# still sitting on its initialisation?** One seed at `rollout_steps = 64` said
# yes -- entropy 9.942/9.952/9.956 against 9.9326 for an untrained 7-dimensional
# Gaussian -- and one seed is not a measurement.
#
# So: both arms, ten seeds, logging what `--run` did not:
#
#   * entropy at every update
#   * the final `log_std`, per dimension
#   * **the distance between the trained policy's mean action and the UNTRAINED
#     one's, on the same observation.** Entropy only measures the SPREAD; a
#     policy can keep its spread and still have moved its mean a long way. This
#     is the direct test and `--run` had no equivalent.
#   * the anytime curve, so "does it still flatten" is answerable
#
# **`total_steps` is capped rather than the budget**, because `BudgetExhausted`
# propagates out through `train()` and takes the stats and the policy with it.
# 90 steps costs ~141 simulations at the measured 1.567 sims/step, just under
# the sweep's 150. **The `best_reward` from this mode is therefore NOT the
# comparable number** -- `--run` has that -- and `n_sims` is reported on every
# row so the shortfall is visible rather than assumed.
# ─────────────────────────────────────────────────────────────────────────────

#: Environment steps for the instrumented arm. See the note above.
INSTRUMENTED_STEPS: int = 90

#: Differential entropy of the UNTRAINED policy: a 7-dimensional Gaussian at
#: `log_std_init = 0.0`, i.e. `(d/2)*ln(2*pi*e)`. **The reference every measured
#: entropy is read against**, so "the policy did not move" is a comparison
#: rather than an impression.
def untrained_entropy(act_dim: int = 7, log_std: float = 0.0) -> float:
    import math
    return 0.5 * act_dim * math.log(2 * math.pi * math.e * math.exp(2 * log_std))


def run_instrumented(rollout_steps: int, replicate: int,
                     total_steps: int = INSTRUMENTED_STEPS,
                     budget_sims: int = BUDGET_SIMS) -> dict:
    """One PPO run with the policy itself instrumented."""
    import dataclasses

    import torch

    from nebula.experiments.baselines import _ObjectiveEnv
    from nebula.rl.env import EnvConfig
    from nebula.rl.ppo import ActorCritic, PPOConfig, train

    seed = run_seed("P1", "ppo", replicate)
    rng = np.random.default_rng(seed)
    obj = Objective(PROBLEMS["P1"], budget_sims=budget_sims, prescreen=False,
                    ac_peak_interp=True)
    pt = obj.problem.points[0]
    env_seed = int(rng.integers(1 << 31))
    cfg = EnvConfig(seed=env_seed, cl_f=pt.cl_f, corner=pt.corner,
                    temp_c=pt.temp_c, vdd_scale=pt.vdd_scale, specs=obj.specs,
                    target_f_peak_hz=obj.target_f_peak_hz,
                    target_peaking_db=obj.target_peaking_db,
                    ac_peak_interp=True)
    env = _ObjectiveEnv(obj, cfg)
    pcfg = dataclasses.replace(
        PPOConfig(seed=env_seed, total_steps=total_steps),
        rollout_steps=int(rollout_steps))

    row: dict = {"kind": "instrumented", "rollout_steps": int(rollout_steps),
                 "replicate": int(replicate), "seed": seed,
                 "total_steps": total_steps}
    t0 = time.perf_counter()
    policy = stats = None
    try:
        policy, stats = train(env, pcfg)
    except BudgetExhausted:
        row["budget_exhausted_before_return"] = True
    row["wall_s"] = round(time.perf_counter() - t0, 2)

    s = obj.summary()
    sim = [t for t in obj.trials if t.n_sims > 0]
    rew = [float(t.reward) for t in sim]
    row.update({
        "n_sims": obj.n_sims, "n_simulated": len(sim),
        "sims_per_step": (obj.n_sims / total_steps if total_steps else None),
        "best_reward_NOT_COMPARABLE": s["best_reward"],
        "n_feasible": s["n_feasible"],
        # the anytime curve, so "does it still flatten" has an answer
        "curve": [max(rew[:k]) for k in range(1, len(rew) + 1)],
    })
    if stats is not None:
        row.update({
            "n_updates": len(stats.entropy),
            "entropy": [float(e) for e in stats.entropy],
            "episode_lengths": list(stats.episode_length),
        })
    if policy is not None:
        ls = [float(x) for x in policy.log_std.detach()]
        row["final_log_std"] = ls
        row["untrained_entropy"] = untrained_entropy(len(ls))
        # ---- THE DIRECT TEST: did the MEAN move? ----
        # Rebuild the initialisation exactly as `train` does -- same
        # `torch.manual_seed(cfg.seed)`, same constructor arguments -- and
        # compare the two mean actions on ONE fixed observation.
        torch.manual_seed(pcfg.seed)
        init = ActorCritic(env.observation_dim, env.action_dim, pcfg.hidden,
                           pcfg.log_std_init)
        probe = torch.as_tensor(env.reset()[0], dtype=torch.float32).unsqueeze(0)
        with torch.no_grad():
            m_trained = policy.distribution(probe).mean.squeeze(0)
            m_init = init.distribution(probe).mean.squeeze(0)
        row["mean_action_trained"] = [round(float(x), 6) for x in m_trained]
        row["mean_action_untrained"] = [round(float(x), 6) for x in m_init]
        row["mean_action_l2_move"] = float(torch.linalg.norm(m_trained - m_init))
        row["init_reproduced"] = bool(
            torch.allclose(init.log_std, torch.zeros_like(init.log_std)))
    return row


def run_instrumented_all(arms: Sequence[int] = (64, 8),
                         replicates: int = REPLICATES,
                         out_path: Optional[Path] = None) -> Path:
    out_path = out_path or (HERE / "ppo_instrumented_run.jsonl")
    jobs = [(rs, rep) for rs in arms for rep in range(replicates)]
    np.random.default_rng(20260820).shuffle(jobs)
    t0 = time.perf_counter()
    with out_path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "schema_version": 1, "kind": "header",
            "experiment": "did the PPO policy move at all?",
            "arms": list(arms), "replicates": replicates,
            "total_steps": INSTRUMENTED_STEPS,
            "untrained_entropy_7d": untrained_entropy(7),
            "note": "best_reward is NOT comparable to --run: this mode caps "
                    "total_steps so train() returns with its stats instead of "
                    "BudgetExhausted carrying them away.",
            "written_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            **provenance(),
        }) + "\n")
        for i, (rs, rep) in enumerate(jobs, start=1):
            r = run_instrumented(rs, rep)
            fh.write(json.dumps(r) + "\n")
            fh.flush()
            print(f"  [{i:>2}/{len(jobs)}] rollout={rs:<3} rep {rep:>2}  "
                  f"updates {r.get('n_updates')}  "
                  f"entropy_last {r.get('entropy', [float('nan')])[-1]:.4f}  "
                  f"mean_move {r.get('mean_action_l2_move', float('nan')):.5f}  "
                  f"sims {r['n_sims']}", flush=True)
    print(f"\n-> {out_path}  ({time.perf_counter() - t0:.1f} s)")
    return out_path


def analyse_instrumented(path: Optional[Path] = None) -> dict:
    path = path or (HERE / "ppo_instrumented_run.jsonl")
    rows = [json.loads(L) for L in path.open(encoding="utf-8")]
    header, runs = rows[0], [r for r in rows[1:] if r.get("kind") == "instrumented"]
    H0 = header["untrained_entropy_7d"]
    out = {"kind": "instrumented", "untrained_entropy": H0, "arms": []}
    for rs in header["arms"]:
        g = [r for r in runs if r["rollout_steps"] == rs and "entropy" in r]
        last_H = [r["entropy"][-1] for r in g]
        move = [r["mean_action_l2_move"] for r in g]
        ls = [float(np.mean(np.abs(r["final_log_std"]))) for r in g]
        # does the curve still flatten? gain over the LAST THIRD of the run.
        tail = []
        for r in g:
            c = r["curve"]
            if len(c) > 30:
                tail.append(c[-1] - c[int(len(c) * 2 / 3)])
        out["arms"].append({
            "rollout_steps": rs, "n": len(g),
            "updates": int(np.median([r["n_updates"] for r in g])),
            "entropy_last_median": float(np.median(last_H)),
            "entropy_minus_untrained": float(np.median(last_H)) - H0,
            "mean_abs_log_std": float(np.median(ls)),
            "mean_action_l2_move_median": float(np.median(move)),
            "mean_action_l2_move_max": float(np.max(move)),
            "curve_gain_over_last_third_median": (float(np.median(tail))
                                                  if tail else None),
            "n_sims_median": float(np.median([r["n_sims"] for r in g])),
            "sims_per_step_median": float(np.median([r["sims_per_step"]
                                                     for r in g])),
        })
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Analysis.
# ─────────────────────────────────────────────────────────────────────────────


def analyse(path: Path = LOG_PATH, sweep_median: Optional[float] = None) -> dict:
    rows = [json.loads(L) for L in path.open(encoding="utf-8")]
    header, runs = rows[0], [r for r in rows[1:] if r.get("kind") == "run"]
    out = {"kind": "analysis", "header": {k: header.get(k) for k in
                                          ("commit_short", "dirty", "arms",
                                           "replicates", "budget_sims")},
           "arms": []}
    for rs in header["arms"]:
        g = [r for r in runs if r["rollout_steps"] == rs]
        best = [r["best_reward"] for r in g]
        med, lo, hi = bootstrap_median(best, alpha=0.05,
                                       rng=np.random.default_rng(7))
        out["arms"].append({
            "rollout_steps": rs,
            "expected_updates": expected_updates(rs),
            "n": len(g),
            "median_best": med, "ci": [lo, hi],
            "min_best": min(best), "max_best": max(best),
            "mean_sims": float(np.mean([r["n_sims"] for r in g])),
            "mean_invalid_rate": float(np.mean([r["invalid_rate"] for r in g])),
            "n_feasible_total": int(sum(r["n_feasible"] for r in g)),
            "sec_per_sim": float(np.mean([r["sec_per_sim"] for r in g])),
            "n_interp_refused": int(sum(r["n_interp_refused"] for r in g)),
        })
    out["arms"].sort(key=lambda a: -a["median_best"])

    ctrl = next(a for a in out["arms"] if a["rollout_steps"] == header["control_arm"])
    out["control"] = {
        "rollout_steps": ctrl["rollout_steps"],
        "median_best": ctrl["median_best"],
        "sweep_median": sweep_median,
        "reproduces": (sweep_median is None
                       or abs(ctrl["median_best"] - sweep_median) < 1e-9),
    }
    # Separability against the control, by the same CI-overlap rule the
    # benchmark uses (7h). Nothing here is ranked without it.
    out["vs_control"] = []
    for a in out["arms"]:
        if a["rollout_steps"] == ctrl["rollout_steps"]:
            continue
        sep = not (a["ci"][0] <= ctrl["ci"][1] and ctrl["ci"][0] <= a["ci"][1])
        out["vs_control"].append({
            "rollout_steps": a["rollout_steps"],
            "delta_median": a["median_best"] - ctrl["median_best"],
            "separable_from_control": bool(sep),
        })
    return out


def print_report(a: dict) -> None:
    print("=" * 78)
    print("PPO rollout_steps -- does giving the policy more updates help?")
    print("=" * 78)
    c = a["control"]
    print(f"  CONTROL rollout_steps={c['rollout_steps']}  median {c['median_best']:.6f}"
          f"   sweep {c['sweep_median']}   reproduces: {c['reproduces']}")
    print()
    print(f"  {'rollout':>8}{'updates':>9}{'n':>4}{'median':>11}{'95% CI':>24}"
          f"{'s/sim':>8}")
    print("  " + "-" * 64)
    for g in a["arms"]:
        print(f"  {g['rollout_steps']:>8}{g['expected_updates']:>9}{g['n']:>4}"
              f"{g['median_best']:>11.5f}"
              f"   [{g['ci'][0]:>8.5f},{g['ci'][1]:>9.5f}]{g['sec_per_sim']:>8.2f}")
    print()
    for v in a["vs_control"]:
        mark = "SEPARABLE" if v["separable_from_control"] else "not separable"
        print(f"    rollout={v['rollout_steps']:<3} vs control: "
              f"{v['delta_median']:+.5f}   {mark}")
    print()
    print("  Separability is 7h's CI-overlap rule. An arm whose interval")
    print("  overlaps the control's is NOT reported as better than it.")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--instrument", action="store_true",
                    help="both arms, ten seeds, logging entropy, log_std, the "
                         "distance the policy MEAN moved from its "
                         "initialisation, and the anytime curve")
    ap.add_argument("--analyse", action="store_true")
    ap.add_argument("--replicates", type=int, default=REPLICATES)
    ap.add_argument("--sweep-median", type=float, default=8.910625533,
                    help="the sweep's PPO median, for the control check")
    a = ap.parse_args(argv)
    if a.run:
        run(replicates=a.replicates)
    if a.instrument:
        run_instrumented_all(replicates=a.replicates)
        print(json.dumps(analyse_instrumented(), indent=2))
    if a.analyse or a.run:
        print_report(analyse(sweep_median=a.sweep_median))
    if not (a.run or a.analyse or a.instrument):
        ap.print_help()
    return 0


if __name__ == "__main__":                                  # pragma: no cover
    sys.exit(main())
