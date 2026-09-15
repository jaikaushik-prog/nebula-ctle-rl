"""
experiments/exp_sac_gate.py — **does SAC learn at all? One gate, zero SPICE.**

WHAT THIS IS, AND THE MUCH LARGER THING IT IS NOT
---------------------------------------------------
`rl/sac.py` is committed, has 55 passing tests, and **has never been run.**
`NEXT_AGENT_SAC.md` §4 stage 1 puts exactly one gate in front of anything
expensive:

    "log_std (or SAC's entropy coefficient) must move. If it does not, stop --
     the problem is not the algorithm, and say so."

This file is that gate. It runs on `rl/analytic_env.py` (**zero SPICE calls**)
and asks only whether the learner's own parameters move.

**It measures no coverage, compares against nothing, and produces no number
that belongs in the report.** The 35.6 % bar from entry 32 is not addressed
here and cannot be; that needs `exp_hybrid` with a SAC proposer, which is
stage 3. Pre-registered as `PREDICTIONS.md` entry 34.

WHY THE ENTROPY COEFFICIENT AND NOT THE SCORE
-----------------------------------------------
PPO's failure on this problem was **invisible in the reward** and obvious in
one parameter. After 1200 SPICE steps its `log_std` read **-0.05 .. +0.053** --
sigma ~1.000, its initialisation, i.e. the network had not trained -- while the
score was negative both before and after and distinguished nothing. After
200 000 analytic steps the same parameter read **-3.022 .. -0.719** (sigma
0.199).

SAC's `alpha` is the same instrument. Automatic entropy tuning has a direct
gradient toward the target entropy (`-dim(A) = -7`) and **does not depend on
the reward being learnable**, so a flat `alpha` after a large step budget means
no signal is reaching the policy at all -- a stronger and earlier diagnosis than
any reward curve.

WHAT IS LOGGED, AND WHY EACH
------------------------------
* **`alpha` and `log_std_mean`, first and last** -- the gate itself (Q1, Q2).
* **`q_loss`** -- the critic's stability (Q3). A maximin reward with an invalid
  floor at `-(N+3)` has a wide value range, and `analytic_env` reverts a bad
  edit rather than terminating, so the critic sees repeated identical states.
  Divergence here is diagnosable, not mysterious.
* **episode length** -- an ENV property (Q4). Logged so an env regression shows
  up as an env regression instead of being blamed on the learner.
* **wall clock and steps/second** -- Q5 recorded an expectation that SAC is
  SLOWER per step than PPO (one gradient step per env step against batched
  updates; (256, 256) against (64, 64)). Measured rather than discovered.

    python -m nebula.experiments.exp_sac_gate --run
    python -m nebula.experiments.exp_sac_gate --analyse
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "sac_gate_results.json"
RUN_LOG = HERE / "sac_gate_run.jsonl"

#: Analytic steps. 50 000 is ~42x the 1200 SPICE steps that left PPO's
#: `log_std` at its initialisation, and small enough that the gate is a
#: quarter-hour rather than an afternoon. It is a GATE budget, not a training
#: budget: if `alpha` has not moved in 50 000 steps it will not move in 500 000.
GATE_STEPS: int = 50_000

N_TRAIN_TARGETS: int = 64
N_TEST_TARGETS: int = 16
SEED: int = 23_0826

#: Q1's threshold, from entry 34. A factor rather than an absolute, because
#: `alpha`'s initial value is a config choice and the question is whether the
#: tuner MOVED it, not where it landed.
ALPHA_MOVE_FACTOR: float = 2.0

#: Q2's threshold, from entry 34.
LOG_STD_MOVE_MIN: float = 0.1


def run(steps: int = GATE_STEPS, seed: int = SEED) -> dict:
    from nebula.experiments.runlock import hold, stamp
    from nebula.rl.analytic_env import V6A_SPECS, AnalyticCtleEnv
    from nebula.rl.sac import SACConfig
    from nebula.rl.sac import train as sac_train
    from nebula.rl.spec_dist import interpolation_split

    with hold("sac_gate", meta={"steps": steps}):
        split = interpolation_split(n_train=N_TRAIN_TARGETS,
                                    n_test=N_TEST_TARGETS, seed=seed)
        env = AnalyticCtleEnv(split.train, seed=seed)
        print(f"SAC gate: {steps:,} analytic steps on {len(split.train)} "
              f"targets, ZERO SPICE", flush=True)

        t0 = time.time()
        with RUN_LOG.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps({"event": "start", "steps": steps,
                                 "seed": seed, "specs": list(V6A_SPECS),
                                 **stamp()}) + "\n")

            seen = {"n": 0}

            def on_episode(ep: int, ret: float, length: int) -> None:
                seen["n"] += 1
                # Sampled: 50 000 steps is ~6 250 episodes and a line each is
                # noise. Every 50th keeps the curve legible.
                if seen["n"] % 50:
                    return
                fh.write(json.dumps({"event": "episode", "episode": ep,
                                     "ret": float(ret),
                                     "length": int(length)}) + "\n")
                fh.flush()

            agent, stats = sac_train(env, SACConfig(seed=seed,
                                                    total_steps=steps),
                                     on_episode=on_episode)
            dt = time.time() - t0

        # `SACStats.gate_report()` is the module's own reporter -- used rather than
        # re-derived here, so the gate reads the same numbers `sac.py` reports
        # (rule 9: one definition).
        summ = stats.gate_report()
        ep_len = (float(np.mean(stats.episode_length))
                  if stats.episode_length else None)
        q = [float(x) for x in stats.q_loss if np.isfinite(x)]

        out = {
            "task": "SAC stage-1 gate: does the learner move at all?",
            **stamp(),
            "steps": steps, "seed": seed, "spice_calls": 0,
            "wall_s": dt, "steps_per_s": steps / max(dt, 1e-9),
            "mean_episode_length": ep_len,
            "horizon": env.horizon,
            "n_evals": env.n_evals, "n_reverted": env.n_reverted,
            "q_loss_first_decile": (float(np.percentile(q[:max(len(q)//10, 1)],
                                                        50)) if q else None),
            "q_loss_last": (q[-1] if q else None),
            "q_loss_finite": bool(q) and all(np.isfinite(q)),
            **summ,
        }
        out["verdict"] = _verdict(out)
        RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
        return out


def _verdict(d: dict) -> dict:
    """Entry 34's decision rule, applied mechanically.

    Written as code so the verdict cannot drift in the writing -- the same
    discipline `exp_rl_refine._report` uses.
    """
    a0, a1 = d.get("alpha_first"), d.get("alpha_last")
    l0, l1 = d.get("log_std_first"), d.get("log_std_last")
    q_ok = bool(d.get("q_loss_finite"))
    qd, ql = d.get("q_loss_first_decile"), d.get("q_loss_last")

    q1 = (a0 is not None and a1 is not None and a0 > 0
          and (max(a1, a0) / min(a1, a0)) >= ALPHA_MOVE_FACTOR)
    q2 = (l0 is not None and l1 is not None
          and abs(l1 - l0) >= LOG_STD_MOVE_MIN)
    q3 = q_ok and (qd is not None and ql is not None and ql <= qd)
    q4 = (d.get("mean_episode_length") is not None
          and d["mean_episode_length"] >= 7.5)
    q5 = d.get("wall_s", 1e9) <= 15 * 60

    if q1 and q2:
        call = ("PASS: the learner moves. Stage 1 may proceed to a measured "
                "comparison against entry 32's 35.6 % bar.")
    else:
        call = ("STOP THE SAC TRACK. Entry 34's own branch: 'the problem is "
                "not the algorithm, and say so.' Report as a measured negative "
                "beside PPO's; the RL contribution claim stays dropped.")
    return {"Q1_alpha_moved": q1, "Q2_log_std_moved": q2,
            "Q3_critic_stable": q3, "Q4_full_horizon": q4,
            "Q5_under_15min": q5, "call": call}


def _report(d: dict) -> None:
    v = d["verdict"]
    print()
    print("=" * 78)
    print(f"SAC STAGE-1 GATE — {d['steps']:,} analytic steps, "
          f"{d['spice_calls']} SPICE calls, {d['wall_s'] / 60:.1f} min "
          f"({d['steps_per_s']:.0f} steps/s)")
    print("=" * 78)
    print(f"  alpha         {d.get('alpha_first')} -> {d.get('alpha_last')}")
    print(f"  log_std_mean  {d.get('log_std_first')} -> {d.get('log_std_last')}")
    print(f"  q_loss        first-decile {d.get('q_loss_first_decile')}  "
          f"last {d.get('q_loss_last')}  finite={d.get('q_loss_finite')}")
    print(f"  episodes      mean length {d.get('mean_episode_length')} "
          f"of horizon {d.get('horizon')}   reverted {d.get('n_reverted')} "
          f"of {d.get('n_evals')} evals")
    print()
    for k in ("Q1_alpha_moved", "Q2_log_std_moved", "Q3_critic_stable",
              "Q4_full_horizon", "Q5_under_15min"):
        print(f"  {'HIT ' if v[k] else 'MISS'}  {k}")
    print()
    print(f"  {v['call']}")
    print()
    print("  This gate measures NO coverage and compares against NOTHING.")
    print("  No number here belongs in the report.")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--analyse", action="store_true")
    ap.add_argument("--steps", type=int, default=GATE_STEPS)
    ap.add_argument("--seed", type=int, default=SEED)
    a = ap.parse_args(argv)
    if a.run:
        _report(run(steps=a.steps, seed=a.seed))
    elif a.analyse:
        if not RESULTS.exists():
            raise SystemExit(f"{RESULTS.name} missing: run --run first")
        _report(json.loads(RESULTS.read_text(encoding="utf-8")))
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":                                  # pragma: no cover
    raise SystemExit(main())
