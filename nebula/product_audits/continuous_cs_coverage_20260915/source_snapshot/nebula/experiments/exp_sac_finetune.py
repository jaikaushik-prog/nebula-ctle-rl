"""
experiments/exp_sac_finetune.py — **does SAC survive the SPICE transfer that
erased PPO? Three levers held, one variable changed.**

THE FAILURE THIS IS DESIGNED AGAINST
--------------------------------------
G114 is the sharpest negative this project has. A PPO policy trained for
200 000 analytic steps -- `log_std -3.022 .. -0.719`, sigma 0.199 -- was
fine-tuned for 3 000 SPICE steps and came back at **`log_std -0.097 .. +0.063`,
sigma 0.988: its initialisation.** Feasibility 1/16 -> 0/16, and episodes got
*shorter*. **3 000 steps erased 200 000.**

G114 names three uncontrolled changes and its own instruction is *"change them
one at a time and measure"*. This file holds all three:

    optimiser         sac.train(agent=...) keeps the agent AND its three
                      optimisers; `lr_finetune` LOWERS the rate rather than
                      resetting it (G114 lever 1)
    reward scale      the SPICE env is scored on V6A_SPECS -- the SAME five
                      rows the analytic env scores, NOT V6D. The confound is
                      REMOVED, not measured (lever 2)
    episode dynamics  RevertOnInvalidEnv(revert_on_invalid=True,
                      keep_going_on_success=True) makes the SPICE env behave
                      exactly as the analytic one does (lever 3)

**So exactly one thing changes between the two legs: the design equations are
replaced by ngspice.** Pre-registered as `PREDICTIONS.md` entry 35.

WHY SCORING SPICE ON V6A IS A CHOICE AND NOT A SHORTCUT
---------------------------------------------------------
`V6A_SPECS` is five rows -- both frequency rows, both peaking rows, and the
Nyquist boost -- because those are what `prescreen.predict_response` can
predict. Scoring the SPICE leg on the same five means the critic's value
function means the same thing on both sides of the transfer.

**It also means this experiment measures nothing about noise, power, saturation,
area, HD3 or the eye**, and therefore nothing about compliance. That is stated
here and in the report rather than left for a reader to discover: the number
that discharges D9's condition is `exp_hybrid`'s **accept rate against 6 of
16**, scored on the full set, and it is stage 3.

WHAT IS MEASURED, BEFORE AND AFTER
------------------------------------
The same 16 held-out targets are run **on real SPICE** before and after the
fine-tune leg, so "did the transfer help or hurt" is a paired measurement
rather than an assumption. `log_std` and `alpha` are recorded at both points --
they are the instrument that caught G114, and the only reason it was caught.

    python -m nebula.experiments.exp_sac_finetune --run
    python -m nebula.experiments.exp_sac_finetune --analyse
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "sac_finetune_results.json"
RUN_LOG = HERE / "sac_finetune_run.jsonl"
CKPT_ANALYTIC = HERE / "sac_policy_analytic.pt"
CKPT_FINETUNED = HERE / "sac_policy_finetuned.pt"

#: Analytic steps. Entry 34 measured the return curve PLATEAUING by the third
#: quarter of a 50 000-step run (+20.3, +35.6, +32.3, +34.3 by quarter), so
#: more would mostly buy time.
ANALYTIC_STEPS: int = 50_000

#: SPICE steps for the correction. 1 500 x 4 decks = 6 000 decks, ~31 min at
#: the measured 1.26 s/step. Half of PPO's 3 000 because the question is
#: whether the policy SURVIVES the transfer, not whether more steps help.
FINETUNE_STEPS: int = 1_500

#: **The one hyper-parameter that is not a library default, and it is here
#: because G114 lever 1 says so.** SAC's `lr` is 3e-4; a converged policy taking
#: initial-scale updates is what let 3 000 steps undo 200 000. A tenth is the
#: conventional fine-tune ratio, stated rather than tuned.
FINETUNE_LR: float = 3e-5

N_TRAIN_TARGETS: int = 64
N_TEST_TARGETS: int = 16
SEED: int = 23_0826

#: Entry 35's thresholds.
Q1_LOG_STD_MAX: float = -1.0
Q2_ALPHA_MAX: float = 0.30
Q3_MAX_DROP: float = 5.0
Q4_MAX_RATIO_GROWTH: float = 2.0


def _log(fh, **kw) -> None:
    fh.write(json.dumps(kw) + "\n")
    fh.flush()


def _spice_env(targets, seed: int):
    """The SPICE corner env, made to behave like the analytic one.

    Two wrappers, and both are `NEXT_AGENT_SAC.md` rule 7's "wrap, do not
    replace": `SpecConditionedCornerEnv` resamples the target per episode,
    `RevertOnInvalidEnv` holds G114 lever 3. `rl/env.py` is untouched.
    """
    from nebula.experiments.exp_corner_rl import SpecConditionedCornerEnv, _screen
    from nebula.rl.analytic_env import V6A_SPECS
    from nebula.rl.episode_dynamics import RevertOnInvalidEnv

    base = SpecConditionedCornerEnv(_screen(), targets, seed=seed,
                                    specs=V6A_SPECS)
    return RevertOnInvalidEnv(base, revert_on_invalid=True,
                              keep_going_on_success=True)


def evaluate_on_spice(agent, targets, seed: int, label: str) -> dict:
    """Run the policy on real SPICE over held-out targets, deterministically.

    The policy is asked for its ANSWER, not an exploration draw, so actions are
    the distribution mean. Cost is recorded because the whole deliverable is a
    ratio of simulation counts.
    """
    from nebula.experiments.exp_corner_rl import _budget_calls

    rets, lens, sims = [], [], 0
    t0 = time.time()
    for i, t in enumerate(targets):
        env = _spice_env([t], seed=seed + i)
        obs, _ = env.reset()
        base = _budget_calls(env.env.env if hasattr(env, "env") else env)
        total, n, done = 0.0, 0, False
        while not done:
            a = agent.actor.act(obs, deterministic=True)
            obs, r, term, trunc, _ = env.step(a)
            total += float(r)
            n += 1
            done = bool(term or trunc)
        sims += _budget_calls(env.env.env if hasattr(env, "env") else env) - base
        rets.append(total)
        lens.append(n)
    return {"label": label, "n": len(rets),
            "mean_return": float(np.mean(rets)),
            "median_return": float(np.median(rets)),
            "var_return": float(np.var(rets)),
            "mean_episode_length": float(np.mean(lens)),
            "n_sims": int(sims), "seconds": time.time() - t0,
            "returns": [float(x) for x in rets]}


def run(analytic_steps: int = ANALYTIC_STEPS,
        finetune_steps: int = FINETUNE_STEPS, seed: int = SEED) -> dict:
    import torch

    from nebula.experiments.runlock import hold, stamp
    from nebula.rl.analytic_env import V6A_SPECS, AnalyticCtleEnv
    from nebula.rl.sac import SACConfig
    from nebula.rl.sac import train as sac_train
    from nebula.rl.spec_dist import interpolation_split

    with hold("sac_finetune", meta={"analytic": analytic_steps,
                                    "finetune": finetune_steps}):
        t_all = time.time()
        split = interpolation_split(n_train=N_TRAIN_TARGETS,
                                    n_test=N_TEST_TARGETS, seed=seed)
        out: dict = {"task": "does SAC survive the SPICE transfer?", **stamp(),
                     "analytic_steps": analytic_steps,
                     "finetune_steps": finetune_steps,
                     "finetune_lr": FINETUNE_LR,
                     "scored_on": list(V6A_SPECS), "seed": seed}

        with RUN_LOG.open("w", encoding="utf-8") as fh:
            _log(fh, event="start", **{k: v for k, v in out.items()
                                       if not isinstance(v, dict)})

            # ---- leg A: analytic --------------------------------------------
            env_a = AnalyticCtleEnv(split.train, seed=seed)
            print(f"leg A: {analytic_steps:,} analytic steps, ZERO SPICE",
                  flush=True)
            t0 = time.time()
            agent, stats_a = sac_train(
                env_a, SACConfig(seed=seed, total_steps=analytic_steps))
            ga = stats_a.gate_report()
            out["analytic"] = {**ga, "seconds": time.time() - t0,
                               "q_loss_last": float(stats_a.q_loss[-1])
                               if stats_a.q_loss else None}
            torch.save({"state_dict": agent.state_dict()
                        if hasattr(agent, "state_dict") else None,
                        "stage": "analytic", "steps": analytic_steps,
                        "seed": seed, "spice_calls": 0}, CKPT_ANALYTIC)
            print(f"  log_std {ga['log_std_last']:+.4f}  alpha "
                  f"{ga['alpha_last']:.4f}  ({out['analytic']['seconds']/60:.1f} min)",
                  flush=True)
            _log(fh, event="leg_a_done", **out["analytic"])

            # ---- measure BEFORE, on real SPICE ------------------------------
            print("measuring on SPICE, BEFORE fine-tune...", flush=True)
            before = evaluate_on_spice(agent, split.test, seed, "analytic_only")
            out["before"] = before
            _log(fh, event="eval_before",
                 **{k: v for k, v in before.items() if k != "returns"})
            print(f"  mean return {before['mean_return']:+.3f}  "
                  f"{before['n_sims']} decks  ({before['seconds']/60:.1f} min)",
                  flush=True)

            # ---- leg B: SPICE fine-tune, SAME agent, SAME reward -----------
            env_b = _spice_env(split.train, seed=seed)
            print(f"leg B: {finetune_steps:,} SPICE steps, lr {FINETUNE_LR}, "
                  f"agent+optimiser KEPT, reward IDENTICAL", flush=True)
            t0 = time.time()
            agent, stats_b = sac_train(
                env_b, SACConfig(seed=seed, total_steps=finetune_steps,
                                 lr_finetune=FINETUNE_LR),
                agent=agent)
            gb = stats_b.gate_report()
            out["finetune"] = {**gb, "seconds": time.time() - t0,
                               "q_loss_last": float(stats_b.q_loss[-1])
                               if stats_b.q_loss else None}
            torch.save({"state_dict": agent.state_dict()
                        if hasattr(agent, "state_dict") else None,
                        "stage": "finetuned", "steps": finetune_steps,
                        "seed": seed,
                        "spice_calls": finetune_steps * 4}, CKPT_FINETUNED)
            print(f"  log_std {gb['log_std_last']:+.4f}  alpha "
                  f"{gb['alpha_last']:.4f}  ({out['finetune']['seconds']/60:.1f} min)",
                  flush=True)
            _log(fh, event="leg_b_done", **out["finetune"])

            # ---- measure AFTER, same targets, same way ----------------------
            print("measuring on SPICE, AFTER fine-tune...", flush=True)
            after = evaluate_on_spice(agent, split.test, seed, "finetuned")
            out["after"] = after
            _log(fh, event="eval_after",
                 **{k: v for k, v in after.items() if k != "returns"})
            print(f"  mean return {after['mean_return']:+.3f}  "
                  f"{after['n_sims']} decks  ({after['seconds']/60:.1f} min)",
                  flush=True)

        out["wall_s"] = time.time() - t_all
        out["verdict"] = _verdict(out)
        RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
        return out


def _verdict(d: dict) -> dict:
    """Entry 35's decision rule, applied mechanically."""
    ft, be, af = d["finetune"], d["before"], d["after"]
    an = d["analytic"]

    q1 = ft["log_std_last"] <= Q1_LOG_STD_MAX
    q2 = ft["alpha_last"] <= Q2_ALPHA_MAX
    q3 = af["mean_return"] >= be["mean_return"] - Q3_MAX_DROP

    # Q4: the NORMALISED critic test entry 34's outcome said to register first.
    def _ratio(q, var):
        return None if (q is None or not var) else q / var
    r0 = _ratio(an.get("q_loss_last"), max(be["var_return"], 1e-9))
    r1 = _ratio(ft.get("q_loss_last"), max(af["var_return"], 1e-9))
    q4 = (r0 is not None and r1 is not None and r0 > 0
          and (r1 / r0) <= Q4_MAX_RATIO_GROWTH)
    q5 = 80 * 60 <= d["wall_s"] <= 120 * 60

    if q1 and q3:
        call = ("PASS: the transfer works and G114 is SOLVED, not merely "
                "avoided. Proceed to stage 3 -- SAC as exp_hybrid's proposer, "
                "measured on ACCEPT RATE against the non-RL baseline of 6 of "
                "16 (entry 32). That is what D9's condition requires.")
    elif q1:
        call = ("Q1 hit, Q3 missed: the policy SURVIVES but does not transfer "
                "usefully. Report it. DO NOT start tuning -- the next lever is "
                "more SPICE steps, which is the owner's budget decision.")
    else:
        call = ("Q1 MISSED: fine-tuning erased SAC as it erased PPO, with all "
                "three of G114's levers held. That is a strong negative -- the "
                "sim-to-real gap is not an optimiser-state artifact. Report it, "
                "and use the ANALYTIC-ONLY policy as the stage-3 proposer.")
    return {"Q1_policy_survived": bool(q1), "Q2_alpha_stayed_low": bool(q2),
            "Q3_return_held": bool(q3), "Q4_critic_normalised": bool(q4),
            "Q5_time_in_band": bool(q5),
            "q_ratio_before": r0, "q_ratio_after": r1, "call": call}


def _report(d: dict) -> None:
    v, an, ft = d["verdict"], d["analytic"], d["finetune"]
    be, af = d["before"], d["after"]
    print()
    print("=" * 78)
    print(f"SAC SPICE TRANSFER — {d['analytic_steps']:,} analytic + "
          f"{d['finetune_steps']:,} SPICE steps, {d['wall_s']/60:.1f} min")
    print(f"  scored on {len(d['scored_on'])} rows (V6A) on BOTH legs — "
          f"the reward scale is held FIXED (G114 lever 2)")
    print("=" * 78)
    print(f"  log_std   analytic {an['log_std_last']:+.4f}  ->  "
          f"after fine-tune {ft['log_std_last']:+.4f}"
          f"      (PPO went to -0.097..+0.063, its init)")
    print(f"  alpha     analytic {an['alpha_last']:.4f}  ->  "
          f"after fine-tune {ft['alpha_last']:.4f}")
    print()
    print(f"  SPICE mean return   BEFORE {be['mean_return']:+8.3f}   "
          f"AFTER {af['mean_return']:+8.3f}   "
          f"delta {af['mean_return']-be['mean_return']:+8.3f}")
    print(f"  SPICE decks         BEFORE {be['n_sims']:5d}   "
          f"AFTER {af['n_sims']:5d}")
    print(f"  episode length      BEFORE {be['mean_episode_length']:.2f}   "
          f"AFTER {af['mean_episode_length']:.2f}")
    print()
    for k in ("Q1_policy_survived", "Q2_alpha_stayed_low", "Q3_return_held",
              "Q4_critic_normalised", "Q5_time_in_band"):
        print(f"  {'HIT ' if v[k] else 'MISS'}  {k}")
    print()
    print(f"  {v['call']}")
    print()
    print("  Scored on 5 of 13 rows. This measures NO compliance and NO")
    print("  coverage. D9's condition is discharged by accept rate, stage 3.")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--analyse", action="store_true")
    ap.add_argument("--analytic-steps", type=int, default=ANALYTIC_STEPS)
    ap.add_argument("--finetune-steps", type=int, default=FINETUNE_STEPS)
    ap.add_argument("--seed", type=int, default=SEED)
    a = ap.parse_args(argv)
    if a.run:
        _report(run(analytic_steps=a.analytic_steps,
                    finetune_steps=a.finetune_steps, seed=a.seed))
    elif a.analyse:
        if not RESULTS.exists():
            raise SystemExit(f"{RESULTS.name} missing: run --run first")
        _report(json.loads(RESULTS.read_text(encoding="utf-8")))
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":                                  # pragma: no cover
    raise SystemExit(main())
