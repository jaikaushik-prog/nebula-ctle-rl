"""
experiments/exp_corner_rl.py — **the RL experiment this project has deferred
four times, on the problem it was always supposed to be run on.**

WHY THE PUBLISHED NULL DOES NOT SETTLE THE QUESTION
-----------------------------------------------------
`BASELINES.md` measures PPO as statistically indistinguishable from uniform
random search at every budget from 150 to 2400 simulations, while CMA-ES is
separably better at every one. That is a real measurement and it is not
retracted here.

**It was measured on a problem that was degenerate in two ways, and one of them
was a bug fixed earlier in this same session:**

1. **The spec manifold was one-dimensional.** `reward_v1.margins` accepted
   `target_peaking_db` and discarded it, so "give me 4 dB" and "give me 11 dB"
   were literally the same question -- one design scored **8.999984 against
   targets of 3, 5, 7.5, 10 and 12 dB, identically** (`SPEC_CONDITIONED.md`
   §0). **On a 1-D manifold a lookup table IS the optimal policy**, which is
   exactly what session 22j measured when 50 random designs answered 100 % of
   held-out targets. A policy cannot beat a lookup at a problem with nothing to
   generalise across. `V5_SPECS` and `S3_peaking_match` make the manifold
   genuinely 2-D.
2. **The policy was never shown a corner.** Every published RL run is P1 --
   one corner, one load, nominal. `rl/corner_env.py` was built for precisely
   this and has never been run.

THE CLAIM BEING TESTED, STATED SO IT CANNOT BE MOVED AFTERWARDS
----------------------------------------------------------------
**NOT "RL beats CMA-ES on one request."** On a 7-D continuous box with a
well-behaved objective, a classical optimiser should win a single query, and
claiming otherwise is a retraction waiting to happen. This file does not test
that and the report must not claim it.

The claim is **amortised**, and it is what the competition slide actually asks
about (*"fewer search spaces (lowest design time)"*):

    per-request cost, after training:
        CMA-ES        ~200 design evaluations, EVERY request, forever
        library       0 simulations -- but blind to corners by construction
        POLICY        1 forward pass + a verification, on a request it has
                      never seen

**The library is the honest competitor, not random search**, and the asymmetry
that gives the policy a niche is structural rather than hopeful: **the pool is
P1-only by construction**, so no amount of re-scoring can tell it what happens
at `sf`/1.05/0 C. A corner-aware policy can. If the policy cannot beat a
corner-blind lookup on corner-scored rewards, the RL contribution claim should
be dropped, and this file is written so that outcome is publishable.

WHAT IS WRAPPED RATHER THAN MODIFIED
--------------------------------------
Rule 7 forbids editing `rl/env.py` and `rl/contract.py` without a human
decision. `CornerCtleEnv` is the precedent and this file follows it: the
spec-conditioned behaviour is a WRAPPER that resamples the target between
episodes. `EnvConfig` is a mutable dataclass and the target already reaches the
observation through `contract.build_observation`, so nothing in the contract
changes -- the target block simply stops being constant, which is what
`CLAUDEwa.md` §7's second contribution always described.

    python -m nebula.experiments.exp_corner_rl --run
    python -m nebula.experiments.exp_corner_rl --analyse
"""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

import nebula.rl.reward_v1 as R
from nebula.rl.spec_dist import SpecTarget, interpolation_split

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "corner_rl_results.json"
RUN_LOG = HERE / "corner_rl_run.jsonl"
POLICY_CKPT = HERE / "corner_rl_policy.pt"

#: Environment steps of PPO. Each is one SPICE-evaluated edit at every screen
#: point, so the SPICE cost is `TRAIN_STEPS * len(points)`.
TRAIN_STEPS: int = 1200

#: Held-out targets the policy has never seen. Interpolation split: test points
#: lie INSIDE the training convex hull, which is the easier and the honest
#: first question. Extrapolation is a separate, harder experiment.
N_TRAIN_TARGETS: int = 64
N_TEST_TARGETS: int = 16

#: Per-request budget for the CMA-ES arm, in design evaluations. Matched to
#: `exp_coverage.BUDGET_DESIGN_EVALS` so the two experiments' cost statements
#: are in the same unit.
CMAES_BUDGET: int = 200

SEED: int = 23_0821


# ─────────────────────────────────────────────────────────────────────────────
# The wrapper: a corner-aware env whose TARGET changes between episodes.
# ─────────────────────────────────────────────────────────────────────────────


class SpecConditionedCornerEnv:
    """`CornerCtleEnv` with a fresh spec target each episode. **A wrapper.**

    Everything about the MDP is the base env's. The one added behaviour is that
    `reset()` draws a target from `targets` and writes it into the config the
    observation is built from, so the policy sees *which spec it is being asked
    for* rather than a constant.

    **`rl/env.py` and `rl/contract.py` are untouched** (rule 7). The target
    block already exists in `contract.build_observation` -- `N_TARGET = 2`, two
    channels, one of which could never change any reward until `V5_SPECS`
    existed. This makes it vary; it does not make it new.
    """

    def __init__(self, points, targets: Sequence[SpecTarget], seed: int,
                 specs: Sequence[str] = R.V6D_SPECS, budget=None):
        from nebula.rl.corner_env import CornerCtleEnv

        if not targets:
            raise ValueError("a spec-conditioned env needs targets to sample")
        self.targets = list(targets)
        self.rng = np.random.default_rng(seed)
        self.env = CornerCtleEnv.from_points(_env_points(points), seed=seed,
                                             budget=budget,
                                             specs=tuple(specs))
        self.observation_dim = self.env.observation_dim
        self.action_dim = self.env.action_dim
        #: Which target each episode was asked for. The report's x-axis.
        self.episode_targets: list = []

    def _set_target(self, t: SpecTarget) -> None:
        for cfg in (self.env.cfg, self.env.base.cfg):
            cfg.target_peaking_db = float(t.peaking_db)
            cfg.target_f_peak_hz = float(t.f_peak_hz)

    def reset(self, u0=None):
        t = self.targets[int(self.rng.integers(len(self.targets)))]
        self._set_target(t)
        self.episode_targets.append((t.peaking_db, t.f_peak_hz))
        return self.env.reset(u0)

    def step(self, action):
        return self.env.step(action)

    def __getattr__(self, name):
        return getattr(self.env, name)


# ─────────────────────────────────────────────────────────────────────────────
# The three arms. One evaluator, one reward, one screen.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ArmResult:
    """One method's answer to one held-out request."""

    arm: str
    peaking_db: float
    f_peak_hz: float
    reward: float
    feasible: bool
    n_sims: int
    wall_s: float
    u: Optional[list] = None
    worst_point: Optional[str] = None
    worst_spec: Optional[str] = None
    reason: Optional[str] = None


def _budget_calls(env) -> int:
    """SPICE calls charged to an env's budget. **THE reader (rule 9).**

    `SpiceBudget` exposes `calls`; this file asked for `n_calls` in three
    places. Two of them were guarded by `hasattr(..., "budget")` -- which is
    True -- so they raised, and the third was an f-string that printed
    `None SPICE calls` for the whole training run without failing. **A wrong
    attribute name that FORMATS cleanly is worse than one that crashes**, and
    both shapes were in this file at once. One reader now, and it raises rather
    than defaulting: a missing budget means the cost accounting is broken, and
    a run whose cost cannot be stated is not reportable.
    """
    b = getattr(env, "budget", None)
    if b is None:
        raise AttributeError(
            "env has no budget: the SPICE cost of this arm cannot be stated, "
            "and an arm with no cost cannot appear in a benchmark table")
    return int(b.calls)


def _screen():
    """The search screen. One definition, shared by every arm (rule 9)."""
    from nebula.experiments.adaptive_screen import EDGE4_MANDATED

    return list(EDGE4_MANDATED)


def _env_points(points):
    """`ScreenPoint` -> `baselines.EvalPoint`, which is what the env wants.

    `CornerCtleEnv` documents `EvalPoint` as the intended record type and
    checks `points[0]` against its own `EnvConfig`; `ScreenPoint.corner` is a
    `Corner` DATACLASS while `EnvConfig.corner` is a process STRING, so handing
    the screen straight over fails that check. Converting here keeps one
    definition of the screen and one of the env contract, rather than a second
    screen that could drift from the first (rule 9 / G32).
    """
    from nebula.experiments.baselines import EvalPoint

    return [EvalPoint(label=p.label, corner=p.corner.process,
                      vdd_scale=float(p.corner.vdd_scale),
                      temp_c=float(p.corner.temp_c), cl_f=float(p.cl_f))
            for p in points]


def _score(u, t: SpecTarget) -> tuple:
    """**THE shared evaluator. Every arm goes through it (`BASELINES.md` §7d).**

    Scores `V6D_SPECS` -- the nine device-measurable rows -- and NOT the full
    `V6_SPECS`, and the reason is a measurement rather than a convenience.

    Scored on `V6_SPECS`, the first run of this experiment returned **-16.0000,
    the invalid floor, for every arm on every request**: the eye is computed
    from a pole-zero fit that is rejected whenever the stage is driven past its
    linear range, and G103 established that peaking and drive handling are one
    knob, so a double-digit peaking request guarantees compression. Measured on
    the library's answer to 10.25 dB @ 1.410 GHz: output swing **675.6 mVpp
    against a 193.9 mVpp linear limit**, at all four corners.

    That is a true and important property **of the circuit**, and reporting it
    as the benchmark's headline would have been reporting it as a property of
    the SEARCH -- four arms pinned at the floor with no gradient between them,
    which measures nothing about which one searches better.

    So the comparison runs on the rows every arm and the RL env can all score,
    and **eye computability is reported as its own number** rather than folded
    into the reward. Two clean measurements instead of one degenerate one.
    """
    from nebula.experiments.adaptive_screen import evaluate_at_points

    ev = evaluate_at_points(u, _screen(), target_f_peak_hz=t.f_peak_hz,
                            target_peaking_db=t.peaking_db, specs=R.V6D_SPECS)
    return ev


def _eye_points(ev) -> int:
    """How many screen points had a COMPUTABLE eye. Reported, never scored."""
    return sum(1 for p in getattr(ev, "points", ()) if p.ok and p.eye_h_v is not None)


def arm_policy(net, t: SpecTarget, points, seed: int) -> ArmResult:
    """**The trained policy, on a request it has never seen.**

    One episode, deterministic (the distribution mean, not a sample): the
    policy is being asked for its answer, not for an exploration draw. Its
    simulation cost is the episode's, and the episode is the same length every
    other arm's single evaluation would be multiplied by.
    """
    import torch

    t0 = time.time()
    env = SpecConditionedCornerEnv(points, [t], seed=seed)
    obs, _ = env.reset()
    best_u, best_r = None, -math.inf
    done = False
    n_sims = _budget_calls(env.env)
    while not done:
        with torch.no_grad():
            o = torch.as_tensor(obs, dtype=torch.float32).unsqueeze(0)
            a = net.distribution(o).mean.squeeze(0).numpy()
        obs, r, term, trunc, info = env.step(a)
        if r > best_r:
            best_r, best_u = r, np.array(env.env._u, dtype=float)
        done = bool(term or trunc)
    used = _budget_calls(env.env) - n_sims
    ev = _score(best_u, t)
    return ArmResult("policy", t.peaking_db, t.f_peak_hz, float(ev.reward),
                     bool(ev.feasible), int(used + ev.n_sims),
                     time.time() - t0, list(map(float, best_u)),
                     ev.worst_point, ev.worst_spec, ev.reason,
                     n_eye_ok=_eye_points(ev))


def arm_library(t: SpecTarget, seed: int = 0) -> ArmResult:
    """**The lookup, and it is the arm to beat.** Zero search simulations.

    Blind to corners by construction: the pool is P1-only, so its choice is
    made on a nominal score and then PAYS for the corner evaluation like
    everyone else. That is the asymmetry the whole RL claim rests on, and it is
    measured here rather than asserted.
    """
    from nebula.design import solve_library

    t0 = time.time()
    lib = solve_library(SpecTarget(peaking_db=t.peaking_db,
                                   f_peak_hz=t.f_peak_hz))
    ev = _score(lib["u"], t)
    return ArmResult("library", t.peaking_db, t.f_peak_hz, float(ev.reward),
                     bool(ev.feasible), int(ev.n_sims), time.time() - t0,
                     [float(x) for x in lib["u"]], ev.worst_point,
                     ev.worst_spec, ev.reason, n_eye_ok=_eye_points(ev))


def arm_cmaes(t: SpecTarget, budget: int = CMAES_BUDGET,
              seed: int = 0) -> ArmResult:
    """Fresh CMA-ES per request. The strong per-query baseline."""
    from nebula.experiments.baselines import BudgetExhausted, CmaConfig, method_cmaes

    t0 = time.time()

    class _Obj:
        def __init__(self):
            self.used = 0
            self.n_sims = 0
            self.best = None

        def check_budget(self):
            if self.used >= budget:
                raise BudgetExhausted(f"{self.used}/{budget}")

        def evaluate(self, u):
            self.check_budget()
            self.used += 1
            ev = _score(u, t)
            self.n_sims += ev.n_sims
            if self.best is None or ev.reward > self.best.reward:
                self.best = ev
            return ev

    obj = _Obj()
    try:
        method_cmaes(obj, np.random.default_rng(seed), CmaConfig(sigma0=0.3))
    except BudgetExhausted:
        pass
    b = obj.best
    return ArmResult("cmaes", t.peaking_db, t.f_peak_hz,
                     float(b.reward if b else -1e3), bool(b and b.feasible),
                     obj.n_sims, time.time() - t0,
                     (list(map(float, b.u)) if b else None),
                     (b.worst_point if b else None),
                     (b.worst_spec if b else None), (b.reason if b else None),
                     n_eye_ok=(_eye_points(b) if b else 0))


def arm_random(t: SpecTarget, budget: int = CMAES_BUDGET,
               seed: int = 0) -> ArmResult:
    """Uniform random, same budget as CMA-ES. The control."""
    from nebula.rl.contract import N_ACTIONS

    t0 = time.time()
    rng = np.random.default_rng(seed)
    best, n_sims = None, 0
    for _ in range(budget):
        ev = _score(rng.uniform(0.0, 1.0, N_ACTIONS), t)
        n_sims += ev.n_sims
        if best is None or ev.reward > best.reward:
            best = ev
    return ArmResult("random", t.peaking_db, t.f_peak_hz,
                     float(best.reward if best else -1e3),
                     bool(best and best.feasible), n_sims, time.time() - t0,
                     (list(map(float, best.u)) if best else None),
                     (best.worst_point if best else None),
                     (best.worst_spec if best else None), None,
                     n_eye_ok=(_eye_points(best) if best else 0))


# ─────────────────────────────────────────────────────────────────────────────


def run(train_steps: int = TRAIN_STEPS, n_test: int = N_TEST_TARGETS,
        cmaes_budget: int = CMAES_BUDGET, seed: int = SEED,
        arms: Sequence[str] = ("policy", "library", "cmaes", "random"),
        reuse_checkpoint: bool = True) -> dict:
    import torch

    from nebula.rl.ppo import PPOConfig, train

    t0 = time.time()
    split = interpolation_split(n_train=N_TRAIN_TARGETS, n_test=n_test,
                                seed=seed)
    points = _screen()
    print(f"training on {len(split.train)} targets, testing on "
          f"{len(split.test)} held out, {len(points)} screen points",
          flush=True)

    # ---- train -------------------------------------------------------------
    env = SpecConditionedCornerEnv(points, split.train, seed=seed)
    t_train = time.time()
    # **Reuse a checkpoint when its provenance matches**, so a crash in the
    # arms below does not cost the 19.3 minutes of training again. Matching is
    # on the things that would make the policy a DIFFERENT policy -- step
    # count, seed, and both dimensions -- and a mismatch retrains rather than
    # loading something that merely fits in memory.
    from nebula.rl.ppo import ActorCritic

    ck = None
    if reuse_checkpoint and POLICY_CKPT.exists():
        c = torch.load(POLICY_CKPT, weights_only=False)
        same = (int(c.get("train_steps", -1)) == int(train_steps)
                and int(c.get("seed", -1)) == int(seed)
                and int(c.get("obs_dim", -1)) == int(env.observation_dim)
                and int(c.get("act_dim", -1)) == int(env.action_dim))
        if same:
            ck = c
        else:
            print(f"  checkpoint present but provenance differs; retraining",
                  flush=True)
    if ck is not None:
        net = ActorCritic(env.observation_dim, env.action_dim,
                          PPOConfig(seed=seed).hidden,
                          PPOConfig(seed=seed).log_std_init)
        net.load_state_dict(ck["state_dict"])
        stats = None
        train_s = 0.0
        train_sims_ck = ck.get("train_sims")
        print(f"  LOADED policy from {POLICY_CKPT.name} "
              f"({train_steps} steps, seed {seed}) -- training skipped",
              flush=True)
    else:
        net, stats = train(env, PPOConfig(seed=seed, total_steps=train_steps))
        train_s = time.time() - t_train
        train_sims_ck = None
    # **Checkpoint immediately.** The first run of this file trained for
    # 19.3 minutes and then died in the evaluation loop on a typo, losing the
    # policy. Training is the expensive, non-reproducible-in-a-hurry part; the
    # arms after it are cheap to re-run.
    import torch

    if ck is None:
        torch.save({"state_dict": net.state_dict(),
                    "train_steps": train_steps, "seed": seed,
                    "obs_dim": env.observation_dim,
                    "act_dim": env.action_dim,
                    "train_sims": _budget_calls(env.env),
                    "train_targets": [(t.peaking_db, t.f_peak_hz)
                                      for t in split.train]},
                   POLICY_CKPT)
        print(f"  checkpointed policy -> {POLICY_CKPT.name}", flush=True)
    # **The checkpoint carries its own training cost.** Reading the live env's
    # budget after loading a checkpoint would report ~0 SPICE calls for a
    # policy that cost thousands -- the break-even arithmetic below divides by
    # this number, so a zero here would print an infinitely good result.
    train_sims = (train_sims_ck if ck is not None else _budget_calls(env.env))
    if train_sims is None:
        raise ValueError(
            "the checkpoint does not record its training SPICE cost, so the "
            "break-even number cannot be computed. Delete it and retrain "
            "rather than publishing a ratio with an unknown denominator.")
    print(f"  trained: {train_steps} env steps, {train_sims} SPICE calls, "
          f"{train_s / 60:.1f} min", flush=True)

    # ---- evaluate on held-out requests -------------------------------------
    rows: list[ArmResult] = []
    with RUN_LOG.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({"event": "start", "train_steps": train_steps,
                             "n_train": len(split.train),
                             "n_test": len(split.test),
                             "train_sims": train_sims,
                             "train_seconds": train_s,
                             "spec_set": list(R.V6_SPECS),
                             "screen": [p.label for p in points]}) + "\n")
        for i, t in enumerate(split.test):
            print(f"[{i + 1}/{len(split.test)}] held-out request "
                  f"{t.peaking_db:.2f} dB @ {t.f_peak_hz / 1e9:.3f} GHz",
                  flush=True)
            for arm in arms:
                if arm == "policy":
                    r = arm_policy(net, t, points, seed=seed + i)
                elif arm == "library":
                    r = arm_library(t)
                elif arm == "cmaes":
                    r = arm_cmaes(t, cmaes_budget, seed=seed + i)
                else:
                    r = arm_random(t, cmaes_budget, seed=seed + i)
                rows.append(r)
                fh.write(json.dumps(asdict(r)) + "\n")
                fh.flush()
                print(f"      {arm:8s} reward {r.reward:+9.4f}  "
                      f"{'FEASIBLE' if r.feasible else '        '}  "
                      f"{r.n_sims:5d} sims  {r.wall_s:6.1f} s", flush=True)

    out = {
        "task": "corner-aware, spec-conditioned RL vs library, CMA-ES, random",
        "spec_set": list(R.V6_SPECS),
        "screen": [p.label for p in points],
        "train_steps": train_steps, "train_sims": train_sims,
        "train_seconds": train_s,
        "n_train_targets": len(split.train), "n_test_targets": len(split.test),
        "cmaes_budget_design_evals": cmaes_budget,
        "results": [asdict(r) for r in rows],
        "summary": _summarise(rows),
        "wall_clock_s": time.time() - t0,
    }
    RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def _summarise(rows: Sequence) -> dict:
    by: dict = {}
    for r in rows:
        d = r if isinstance(r, dict) else asdict(r)
        by.setdefault(d["arm"], []).append(d)
    out = {}
    for arm, rs in by.items():
        rew = [x["reward"] for x in rs]
        out[arm] = {
            "n": len(rs),
            "n_feasible": sum(1 for x in rs if x["feasible"]),
            "median_reward": float(np.median(rew)),
            "mean_sims": float(np.mean([x["n_sims"] for x in rs])),
            "total_sims": int(sum(x["n_sims"] for x in rs)),
            "mean_wall_s": float(np.mean([x["wall_s"] for x in rs])),
            "n_with_computable_eye": sum(1 for x in rs
                                         if x.get("n_eye_ok", 0) > 0),
            "n_with_eye_at_every_point": sum(
                1 for x in rs if x.get("n_eye_ok", 0) >= 4),
        }
    return out


def _report(d: dict) -> None:
    s = d["summary"]
    print()
    print("=" * 78)
    print(f"CORNER-AWARE RL — {d['n_test_targets']} held-out requests, "
          f"{d['wall_clock_s'] / 60:.1f} min total")
    print(f"  training: {d['train_steps']} env steps, {d['train_sims']} SPICE "
          f"calls, {d['train_seconds'] / 60:.1f} min  (paid ONCE)")
    print("=" * 78)
    print(f"  {'arm':10s} {'feasible':>10s} {'median rwd':>12s} "
          f"{'sims/req':>10s} {'total sims':>11s} {'s/req':>8s}")
    for arm in ("policy", "library", "cmaes", "random"):
        if arm not in s:
            continue
        a = s[arm]
        print(f"  {arm:10s} {a['n_feasible']:>4d}/{a['n']:<5d} "
              f"{a['median_reward']:>12.4f} {a['mean_sims']:>10.1f} "
              f"{a['total_sims']:>11d} {a['mean_wall_s']:>8.1f}")
    print()
    print("  READ THIS TABLE AMORTISED. Training is paid once; 'sims/req' is")
    print("  what each additional request costs. The per-query winner and the")
    print("  amortised winner are DIFFERENT questions and both are reported.")
    if "policy" in s and "cmaes" in s:
        pol, cma = s["policy"], s["cmaes"]
        if pol["mean_sims"] > 0:
            n_break = (d["train_sims"] or 0) / max(
                cma["mean_sims"] - pol["mean_sims"], 1e-9)
            if n_break > 0:
                print(f"  Break-even against CMA-ES: **{n_break:.0f} requests** "
                      f"(training {d['train_sims']} sims / saving "
                      f"{cma['mean_sims'] - pol['mean_sims']:.1f} sims per "
                      f"request)")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--analyse", action="store_true")
    ap.add_argument("--train-steps", type=int, default=TRAIN_STEPS)
    ap.add_argument("--n-test", type=int, default=N_TEST_TARGETS)
    ap.add_argument("--budget", type=int, default=CMAES_BUDGET)
    a = ap.parse_args(argv)
    if a.run:
        _report(run(train_steps=a.train_steps, n_test=a.n_test,
                    cmaes_budget=a.budget))
    elif a.analyse:
        if not RESULTS.exists():
            raise SystemExit(f"{RESULTS.name} missing: run --run first")
        _report(json.loads(RESULTS.read_text(encoding="utf-8")))
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":                                  # pragma: no cover
    raise SystemExit(main())
