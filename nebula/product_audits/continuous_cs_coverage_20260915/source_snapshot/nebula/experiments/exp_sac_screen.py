"""
experiments/exp_sac_screen.py -- **SAC trained on the acceptance criterion
itself. 25 000 SPICE steps.**

WHY THIS RUN EXISTS
--------------------
Five experiments have measured RL losing here, and every one of them was shaped
by a decision to make training CHEAP:

    entry 34/35  trained on an ANALYTIC model      -> a sim-to-real gap to survive
    entry 36     the analytic model predicts 5 of  -> blind to the quantity that
                 13 spec rows                         rejected 95 % of designs
    entry 38     fixed that blindness              -> failures moved to rows the
                                                      policy WAS trained on...
                                                      because it is trained at
                                                      NOMINAL and scored at CORNERS

**This run removes the last mismatch by paying for it.** `ScreenEnv` scores
through `evaluate_at_points(EDGE4_MANDATED, V6_SPECS)` -- the same function,
corners and spec rows that decide acceptance -- so the training signal IS the
metric. 4 SPICE decks per step, ~7.2 s/step measured. 25 000 steps is
**100 000 decks and roughly 50 hours**, and the owner has authorised it.

WHAT ELSE THE EVIDENCE PUT IN
-------------------------------
* **Warm starts from library designs** (entry 36: the policy destroyed five of
  the six designs retrieval found -- those states are where it must learn
  restraint), **filtered by entry 37's swing surrogate** so episodes begin in
  the measurable region rather than on the four-level invalid staircase. The
  smoke's first warm start was already feasible at all four corners.
* **`MAX_STEP = 0.05`**, because repairing a working design needs fine control.
* **Entry 40's finding that the 4-corner screen is a good filter for 45-corner
  compliance** -- 5 of 6 accepted proposals passed 45/45 -- which is what makes
  the screen reward worth maximising in the first place.

WHAT WAS DELIBERATELY NOT DONE
--------------------------------
**The replay buffer is NOT seeded from the pool**, though `replay.seed_from_pool`
exists and would supply thousands of real transitions for free. The pool carries
no eye, area or HD3 measurement, so it cannot score 4 of `V6_SPECS`' 13 rows;
seeded transitions would describe a **different reward** from the env's. That is
G114's second lever, and `replay.py`'s own docstring says it "does not raise --
it gives the critic two incompatible descriptions of the same state, which is
how the PPO policy was erased." Rejected on purpose, recorded here.

RESUMABILITY
-------------
50 hours is long enough that a crash must not cost the run. Training is chunked;
the agent (with its three optimisers) and a progress row are written after every
chunk. `--resume` continues from the checkpoint. **The replay buffer is not
persisted** -- a resumed run rebuilds it, which is a real cost and is reported
rather than hidden.

    python -m nebula.experiments.exp_sac_screen --run
    python -m nebula.experiments.exp_sac_screen --run --resume
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

HERE = Path(__file__).resolve().parent
CKPT = HERE / "sac_policy_screen.pt"
PROGRESS = HERE / "sac_screen_progress.jsonl"
RESULTS = HERE / "sac_screen_results.json"

TOTAL_STEPS: int = 25_000
CHUNK: int = 500            # ~1 hour per chunk at the measured 7.2 s/step
SEED: int = 23_0826
N_TRAIN_TARGETS: int = 64
LEARNING_STARTS: int = 100


def _gate(stats) -> dict:
    try:
        return stats.gate_report()
    except Exception as exc:                                    # noqa: BLE001
        # `gate_report` RAISES when a chunk made no updates -- that guard is
        # right (entry 35 §5) and must not be weakened; it is reported instead.
        return {"gate_error": repr(exc)}


def run(total_steps: int = TOTAL_STEPS, chunk: int = CHUNK, seed: int = SEED,
        resume: bool = False) -> dict:
    import torch

    from nebula.experiments.runlock import hold, stamp
    from nebula.rl.sac import ReplayBuffer, SACAgent, SACConfig
    from nebula.rl.sac import train as sac_train
    from nebula.rl.screen_env import MAX_STEP, ScreenEnv
    from nebula.rl.spec_dist import interpolation_split
    import nebula.rl.reward_v1 as R

    split = interpolation_split(n_train=N_TRAIN_TARGETS, n_test=16, seed=seed)
    env = ScreenEnv(split.train, seed=seed)

    agent = None
    done_steps = 0
    if resume and CKPT.exists():
        ck = torch.load(CKPT, map_location="cpu", weights_only=False)
        sd = ck.get("state_dict")
        if sd:
            agent = SACAgent(int(sd["obs_dim"]), int(sd["act_dim"]),
                             SACConfig(seed=seed))
            agent.load_state_dict(sd)
            done_steps = int(ck.get("steps", 0))
            print(f"resumed from {done_steps:,} steps "
                  f"(replay buffer NOT restored -- it rebuilds)", flush=True)

    buffer = ReplayBuffer(SACConfig(seed=seed).buffer_capacity,
                          env.observation_dim, env.action_dim)

    with hold("sac_screen", meta={"total_steps": total_steps,
                                  "resumed_at": done_steps}):
        t0 = time.time()
        out: dict = {"task": "SAC trained on the acceptance criterion itself",
                     **stamp(), "total_steps": total_steps, "chunk": chunk,
                     "seed": seed, "max_step": MAX_STEP,
                     "specs": list(R.V6_SPECS),
                     "screen": [p.label for p in env.points],
                     "buffer_seeded_from_pool": False,
                     "buffer_seeding_note":
                         "the pool cannot score 4 of V6_SPECS' 13 rows, so "
                         "seeded transitions would carry a different reward "
                         "(G114 lever 2)",
                     "chunks": []}

        mode = "a" if resume else "w"
        with PROGRESS.open(mode, encoding="utf-8") as fh:
            while done_steps < total_steps:
                n = min(chunk, total_steps - done_steps)
                cfg = SACConfig(
                    seed=seed + done_steps, total_steps=n,
                    # **Only the FIRST chunk warms up.** A continuation that
                    # re-ran `learning_starts` would inject 100 uniform-random
                    # actions every chunk -- 5 000 wasted SPICE steps over this
                    # run, and a periodic kick to a converged policy.
                    learning_starts=(LEARNING_STARTS if done_steps == 0 else 0))
                agent, stats = sac_train(env, cfg, buffer=buffer, agent=agent)
                done_steps += n
                rep = env.report()
                row = {"steps": done_steps, "elapsed_min": (time.time() - t0) / 60,
                       **_gate(stats), **{k: rep[k] for k in
                                          ("n_decks", "n_reverted", "n_unscorable",
                                           "n_feasible_steps", "n_warm_starts",
                                           "n_starts_filtered")},
                       "buffer": len(buffer) if hasattr(buffer, "__len__") else None}
                out["chunks"].append(row)
                fh.write(json.dumps(row) + "\n")
                fh.flush()
                torch.save({"state_dict": agent.state_dict(), "stage": "screen",
                            "steps": done_steps, "seed": seed,
                            "spice_calls": rep["n_decks"]}, CKPT)
                print(f"  [{done_steps:,}/{total_steps:,}] "
                      f"log_std {row.get('log_std_last', float('nan')):+.4f}  "
                      f"alpha {row.get('alpha_last', float('nan')):.4f}  "
                      f"feasible steps {rep['n_feasible_steps']}  "
                      f"decks {rep['n_decks']:,}  "
                      f"({row['elapsed_min']:.0f} min)", flush=True)

        out["wall_s"] = time.time() - t0
        out["env_report"] = env.report()
        RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
        return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--steps", type=int, default=TOTAL_STEPS)
    ap.add_argument("--chunk", type=int, default=CHUNK)
    ap.add_argument("--seed", type=int, default=SEED)
    a = ap.parse_args(argv)
    if not a.run:
        ap.print_help()
        return 0
    d = run(total_steps=a.steps, chunk=a.chunk, seed=a.seed, resume=a.resume)
    last = d["chunks"][-1] if d["chunks"] else {}
    print()
    print(f"DONE  {d['total_steps']:,} steps, "
          f"{d['env_report']['n_decks']:,} decks, {d['wall_s']/3600:.1f} h")
    print(f"  log_std {last.get('log_std_last')}  alpha {last.get('alpha_last')}")
    print(f"  feasible steps {d['env_report']['n_feasible_steps']:,} of "
          f"{d['env_report']['n_evals']:,} evaluations")
    print("  Nothing here is an accept rate. Evaluate with exp_sac_screen_eval.")
    return 0


if __name__ == "__main__":                                  # pragma: no cover
    raise SystemExit(main())
