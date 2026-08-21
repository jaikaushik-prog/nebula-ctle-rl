"""
experiments/exp_rl_pretrain.py — **pre-train the policy where practice is free,
then correct it where the truth is.**

THE MEASUREMENT THIS EXISTS TO ACT ON
---------------------------------------
Session 23 trained a corner-aware policy on SPICE for 1200 environment steps
and it learned nothing. **The evidence is not the score, it is the parameter
that tracks learning:** PPO's `log_std` starts at 0.0 and shrinks as a policy
becomes confident. After training it read **-0.05 to +0.053** -- unmoved. Sigma
~1.0 is also as wide as the whole `tanh`-bounded action, so what the policy
chose was drowned out by its own sampling.

1200 steps is roughly **1 % of one training run**, and the reason is arithmetic
rather than anything about PPO:

    one SPICE step = 4 decks = 1.26 s   ->   120 000 steps = 42 hours

`rl/analytic_env.py` runs the same MDP off the design equations, and the
speed-up is large but **NOT as large as first claimed, and the correction
matters**:

    env stepping ALONE                   0.47 ms/step   <- what was first measured
    env + PPO's own compute             11    ms/step   <- what a run actually costs
    SPICE env + PPO                   1 260    ms/step

The first number was measured by stepping the environment in a loop with no
policy attached. **PPO's forward passes, GAE and gradient updates cost ~23x
more than the analytic environment does**, so removing the simulator does not
buy 2 600x; it buys **~114x**. Corrected before it reached a report:

      120 000 steps    SPICE  42 h      analytic  ~22 min
    1 000 000 steps    SPICE 350 h      analytic  ~3.1 h

Still decisive, and now honest. **A speed-up measured on a component rather
than on the whole pipeline is the shape of an over-claim** -- the same family
as G105 (measuring the instrument instead of the thing).

THE THREE STAGES, AND WHY THE MIDDLE ONE IS NOT OPTIONAL
----------------------------------------------------------
    1. PRE-TRAIN   analytic env, ~1e6 steps, ~8 min, ZERO SPICE
    2. FINE-TUNE   the real corner env on SPICE, a few thousand steps
    3. MEASURE     16 held-out requests, on SPICE, against the same arms

**Stage 2 is the whole risk.** The design equations are a simplification:
measured against SPICE, f_peak median error **4.93 %** and peaking MAE
**0.284 dB** with essentially no bias -- but **p99 f_peak error is 1.078
octaves**, a factor of two. A policy that trains only on stage 1 gets very good
at an approximation and can pick up habits that do not survive contact with the
simulator, confidently, in exactly the region where the equations break down.

**So stage 2 is not a formality and its effect must be MEASURED, not assumed.**
This file evaluates the policy on real SPICE **before and after** fine-tuning
and reports both. If fine-tuning does not close the gap, that is the finding
and it gets published; it is not a reason to quote the pre-trained number.

WHAT IS LOGGED, AND WHY THESE FIELDS
--------------------------------------
Everything, to `rl_pretrain_run.jsonl`, because the last four RL runs each
ended with a question the logs could not answer:

* **`log_std` per update** -- the diagnostic that found the original defect. If
  it is still flat after a million steps, the problem is not the budget and
  this whole approach is falsified. **That is the first thing to look at.**
* **episode length** -- the SPICE env ends episodes on an unbuildable design
  and the policy was getting 1-3 of its 8 moves. The analytic env reverts
  instead; this records whether that actually holds at scale.
* **reverted-edit rate** -- how often the policy proposes something
  unrealisable. A rate that falls over training IS learning; one that does not
  says the policy never learned where the box ends.
* **SPICE calls, separately per stage** -- the headline claim is a ratio of
  simulation counts, and stage 1 must be able to prove it spent zero.

    python -m nebula.experiments.exp_rl_pretrain --pretrain
    python -m nebula.experiments.exp_rl_pretrain --finetune
    python -m nebula.experiments.exp_rl_pretrain --all
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "rl_pretrain_results.json"
RUN_LOG = HERE / "rl_pretrain_run.jsonl"
PRETRAINED = HERE / "rl_policy_pretrained.pt"
FINETUNED = HERE / "rl_policy_finetuned.pt"

#: Analytic steps. **200 000, not the 1 000 000 first written**, and the
#: reason is the corrected cost above: at 11 ms/step (env + PPO, not env alone)
#: a million steps is ~3.1 h rather than ~8 min. 200 000 costs ~37 min and is
#: still **167x** the 1200 steps that learned nothing. The smoke test settles
#: that this is enough to be in the right regime: at **20 000** steps `log_std`
#: had already moved 0.000 -> -0.462..+0.137 (sigma 0.792), where 1200 SPICE
#: steps left it at -0.05..+0.053 (sigma ~1.000, flat).
PRETRAIN_STEPS: int = 200_000

#: SPICE steps for the correction. 3000 steps x 4 decks = 12 000 decks, ~63 min
#: at the measured 1.26 s/step. Sized so the correction is affordable in one
#: sitting rather than to hit a target.
FINETUNE_STEPS: int = 3_000

N_TRAIN_TARGETS: int = 64
N_TEST_TARGETS: int = 16
SEED: int = 23_0821


def _log(fh, **kw) -> None:
    fh.write(json.dumps(kw) + "\n")
    fh.flush()


def _policy_diagnostics(net) -> dict:
    """**The fields that answer "is it learning?" rather than "is it good?".**

    `log_std` first: it is the parameter that moved zero on the run that
    failed, and if it is flat again after a million steps then budget was not
    the blocker and this approach is falsified.
    """
    import torch

    with torch.no_grad():
        ls = net.log_std.detach().cpu().numpy()
    return {
        "log_std_mean": float(np.mean(ls)),
        "log_std_min": float(np.min(ls)),
        "log_std_max": float(np.max(ls)),
        "sigma_mean": float(np.mean(np.exp(ls))),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — analytic pre-training. ZERO SPICE.
# ─────────────────────────────────────────────────────────────────────────────


def pretrain(steps: int = PRETRAIN_STEPS, seed: int = SEED) -> dict:
    import torch

    from nebula.rl.analytic_env import V6A_SPECS, AnalyticCtleEnv
    from nebula.rl.ppo import PPOConfig, train
    from nebula.rl.spec_dist import interpolation_split

    split = interpolation_split(n_train=N_TRAIN_TARGETS,
                                n_test=N_TEST_TARGETS, seed=seed)
    env = AnalyticCtleEnv(split.train, seed=seed)
    print(f"pre-training: {steps:,} analytic steps on {len(split.train)} "
          f"targets, ZERO SPICE", flush=True)

    t0 = time.time()
    with RUN_LOG.open("a", encoding="utf-8") as fh:
        _log(fh, event="pretrain_start", steps=steps, seed=seed,
             specs=list(V6A_SPECS), n_train=len(split.train))

        seen = {"n": 0}

        def on_episode(ep: int, ret: float, length: int) -> None:
            seen["n"] += 1
            # Sampled rather than logged every episode: a million steps is
            # ~125 000 episodes and a line each would be a 30 MB log nobody
            # reads. Every 250th keeps the curve and the file legible.
            if seen["n"] % 250:
                return
            _log(fh, event="pretrain_episode", episode=ep, ret=float(ret),
                 length=int(length), n_evals=env.n_evals,
                 n_reverted=env.n_reverted,
                 revert_rate=(env.n_reverted / max(env.n_evals, 1)))

        net, stats = train(env, PPOConfig(seed=seed, total_steps=steps),
                           on_episode=on_episode)
        dt = time.time() - t0
        diag = _policy_diagnostics(net)
        _log(fh, event="pretrain_done", seconds=dt, **diag,
             n_evals=env.n_evals, n_reverted=env.n_reverted,
             mean_episode_length=(float(np.mean(stats.episode_length))
                                  if stats.episode_length else None))

    torch.save({"state_dict": net.state_dict(), "stage": "pretrained",
                "steps": steps, "seed": seed,
                "obs_dim": env.observation_dim, "act_dim": env.action_dim,
                # **Zero, and recorded as zero.** The headline claim is a ratio
                # of simulation counts; a stage that spent none must be able to
                # prove it rather than be assumed to have.
                "spice_calls": 0,
                "analytic_evals": env.n_evals}, PRETRAINED)

    print(f"  {steps:,} steps in {dt / 60:.1f} min, 0 SPICE calls", flush=True)
    print(f"  log_std {diag['log_std_min']:+.3f} .. {diag['log_std_max']:+.3f} "
          f"(started 0.000)  sigma {diag['sigma_mean']:.3f}", flush=True)
    print(f"  reverted edits {env.n_reverted:,} of {env.n_evals:,} "
          f"({100 * env.n_reverted / max(env.n_evals, 1):.1f} %)", flush=True)
    if abs(diag["log_std_mean"]) < 0.05:
        print("  *** log_std is STILL FLAT. Budget was not the blocker and "
              "this approach is falsified -- report it, do not re-tune. ***",
              flush=True)
    return {"steps": steps, "seconds": dt, "spice_calls": 0, **diag}


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — fine-tune on SPICE, and MEASURE whether it helped.
# ─────────────────────────────────────────────────────────────────────────────


def _budget(env) -> int:
    from nebula.experiments.exp_corner_rl import _budget_calls

    return _budget_calls(env.env)


def _load(path: Path, obs_dim: int, act_dim: int, seed: int):
    """Load a checkpoint, refusing one whose shape or cost is unrecorded."""
    import torch

    from nebula.rl.ppo import ActorCritic, PPOConfig

    if not path.exists():
        raise FileNotFoundError(
            f"{path.name} is missing: fine-tuning has nothing to correct. Run "
            f"--pretrain first rather than starting from a fresh network, "
            f"which would measure something else entirely.")
    c = torch.load(path, weights_only=False)
    if int(c.get("obs_dim", -1)) != obs_dim or int(c.get("act_dim", -1)) != act_dim:
        raise ValueError(
            f"{path.name} was trained on obs/act ({c.get('obs_dim')}, "
            f"{c.get('act_dim')}) and this env is ({obs_dim}, {act_dim}). "
            f"Loading it would silently measure a different problem.")
    if c.get("spice_calls") is None:
        raise ValueError(
            f"{path.name} does not record its SPICE cost. The headline claim "
            f"is a ratio of simulation counts and this is its denominator; a "
            f"missing value must raise, never default to zero.")
    cfg = PPOConfig(seed=seed)
    net = ActorCritic(obs_dim, act_dim, cfg.hidden, cfg.log_std_init)
    net.load_state_dict(c["state_dict"])
    return net, c


def evaluate_on_spice(net, targets, seed: int, label: str) -> dict:
    """Run the policy on real SPICE over held-out targets. **The honest test.**

    The design equations are unbiased typically and off by a full octave at the
    p99, so a policy trained on them can be confidently wrong exactly where
    they break down. This is the measurement that says whether that happened,
    and it runs BEFORE and AFTER stage 2 so the correction has a number rather
    than an assumption.
    """
    from nebula.experiments.exp_corner_rl import _screen, arm_policy

    rows = []
    t0 = time.time()
    for i, t in enumerate(targets):
        r = arm_policy(net, t, _screen(), seed=seed + i)
        rows.append({"peaking_db": t.peaking_db, "f_peak_hz": t.f_peak_hz,
                     "reward": r.reward, "feasible": r.feasible,
                     "n_sims": r.n_sims, "n_eye_ok": r.n_eye_ok})
    rew = [r["reward"] for r in rows]
    return {"label": label, "n": len(rows),
            "n_feasible": sum(1 for r in rows if r["feasible"]),
            "median_reward": float(np.median(rew)),
            "mean_reward": float(np.mean(rew)),
            "total_sims": int(sum(r["n_sims"] for r in rows)),
            "mean_sims": float(np.mean([r["n_sims"] for r in rows])),
            "seconds": time.time() - t0, "rows": rows}


def finetune(steps: int = FINETUNE_STEPS, seed: int = SEED) -> dict:
    import torch

    from nebula.experiments.exp_corner_rl import SpecConditionedCornerEnv, _screen
    from nebula.rl.ppo import PPOConfig, train
    from nebula.rl.spec_dist import interpolation_split

    split = interpolation_split(n_train=N_TRAIN_TARGETS,
                                n_test=N_TEST_TARGETS, seed=seed)
    points = _screen()
    env = SpecConditionedCornerEnv(points, split.train, seed=seed)
    net, ck = _load(PRETRAINED, env.observation_dim, env.action_dim, seed)

    print(f"fine-tuning: {steps:,} SPICE steps on {len(points)} screen points",
          flush=True)
    print(f"  loaded {PRETRAINED.name}: {ck['steps']:,} analytic steps, "
          f"{ck['spice_calls']} SPICE calls", flush=True)

    with RUN_LOG.open("a", encoding="utf-8") as fh:
        before = evaluate_on_spice(net, split.test, seed, "pretrained_only")
        _log(fh, event="eval_before_finetune",
             **{k: v for k, v in before.items() if k != "rows"})
        print(f"  BEFORE fine-tune, on SPICE: median {before['median_reward']:+.4f}, "
              f"{before['n_feasible']}/{before['n']} feasible, "
              f"{before['mean_sims']:.1f} sims/request", flush=True)

        t0 = time.time()
        net, stats = train(env, PPOConfig(seed=seed, total_steps=steps))
        dt = time.time() - t0
        spice = int(ck["spice_calls"]) + _budget(env)
        diag = _policy_diagnostics(net)
        _log(fh, event="finetune_done", seconds=dt, spice_calls=spice, **diag)

        torch.save({"state_dict": net.state_dict(), "stage": "finetuned",
                    "steps": steps, "seed": seed,
                    "obs_dim": env.observation_dim,
                    "act_dim": env.action_dim, "spice_calls": spice,
                    "pretrain_steps": ck["steps"]}, FINETUNED)

        after = evaluate_on_spice(net, split.test, seed, "finetuned")
        _log(fh, event="eval_after_finetune",
             **{k: v for k, v in after.items() if k != "rows"})
        print(f"  AFTER  fine-tune, on SPICE: median {after['median_reward']:+.4f}, "
              f"{after['n_feasible']}/{after['n']} feasible, "
              f"{after['mean_sims']:.1f} sims/request", flush=True)

    delta = after["median_reward"] - before["median_reward"]
    print(f"  fine-tuning moved the median by {delta:+.4f} "
          f"({'helped' if delta > 0 else 'did NOT help'})", flush=True)
    if delta <= 0:
        print("  *** Fine-tuning did not close the sim-to-real gap. That is "
              "the finding; report it. Do NOT quote the pre-trained number as "
              "if it were a SPICE result. ***", flush=True)
    return {"finetune_steps": steps, "seconds": dt, "spice_calls": spice,
            "before": before, "after": after, "median_delta": delta, **diag}


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pretrain", action="store_true")
    ap.add_argument("--finetune", action="store_true")
    ap.add_argument("--all", action="store_true",
                    help="pretrain, then fine-tune, then measure both on SPICE")
    ap.add_argument("--steps", type=int, default=PRETRAIN_STEPS)
    ap.add_argument("--finetune-steps", type=int, default=FINETUNE_STEPS)
    ap.add_argument("--seed", type=int, default=SEED)
    a = ap.parse_args(argv)
    if a.pretrain or a.finetune or a.all:
        from nebula.experiments.runlock import hold

        out: dict = {}
        with hold("rl_pretrain", meta={"steps": a.steps}):
            if a.pretrain or a.all:
                out["pretrain"] = pretrain(steps=a.steps, seed=a.seed)
            if a.finetune or a.all:
                out["finetune"] = finetune(steps=a.finetune_steps, seed=a.seed)
        RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":                                  # pragma: no cover
    raise SystemExit(main())
