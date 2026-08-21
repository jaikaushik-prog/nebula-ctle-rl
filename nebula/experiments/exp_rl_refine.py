"""
experiments/exp_rl_refine.py — **does the policy add anything ON TOP of
retrieval?**

WHY THE PREVIOUS COMPARISON DID NOT ANSWER THIS
-------------------------------------------------
Entries 25 and 26 put these two side by side:

    library    pick the best of ~74 500 ALREADY-SIMULATED designs
    policy     start from a UNIFORM RANDOM design and make 8 edits

and the policy lost 1 to 9. **Those are not the same problem.** The lookup was
handed a very large head start; the policy was asked to beat it from nothing.
That comparison measures the difficulty gap at least as much as it measures
either method.

The question the deliverable actually raises -- and the one the owner's brief
described, with RL as the proposal/refinement layer rather than a from-scratch
designer -- is the one this file asks:

    step 1   library retrieves a start point       0 SPICE
    step 2   policy makes <= 8 refining edits     ~32 SPICE
                                                   ----
                                                   ~32 SPICE per request

**The bar is the library's own measured result: 9 of 16 feasible at 4.0 SPICE
calls per request.** Anything the policy does is measured against the thing it
started from, which is the only comparison that isolates its contribution.

TWO CHANGES, AND BOTH ARE IN THE WRAPPER
------------------------------------------
1. **The start point is the library's design**, not uniform random.
2. **`max_step` 0.15 -> 0.04.** At 0.15 an 8-step episode travels up to 1.2 box
   widths: that is a SEARCH stride and it can leave a good neighbourhood on the
   first move. 0.04 x 8 = 0.32 box widths, a refinement stride.

`MAX_STEP` is a published constant in `rl/contract.py` and rule 7 forbids
editing that without a human decision, so **the override lives here**, in the
`EnvConfig` this file constructs. `rl/contract.py` is untouched and every other
caller still gets 0.15.

WHICH POLICY, AND WHY NOT THE OTHER ONE
-----------------------------------------
`rl_policy_pretrained.pt` -- 200 000 analytic steps, zero SPICE. **NOT**
`rl_policy_finetuned.pt`: G114 measured that fine-tuning returned `log_std`
from -3.022..-0.719 to -0.097..+0.063, i.e. to its initialisation, taking
feasibility from 1/16 to 0/16 with it. Using the fine-tuned policy here would
be measuring the erasure rather than the refinement.

WHAT IS REPORTED
-----------------
Per request: the library's reward, the policy's reward after refining it, and
the DELTA -- because "did it help" is a paired comparison on the same starting
point, not two independent samples. Reporting only the totals would hide a
policy that fixes four requests and breaks four others.

    python -m nebula.experiments.exp_rl_refine --run
    python -m nebula.experiments.exp_rl_refine --analyse
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

import nebula.rl.reward_v1 as R

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "rl_refine_results.json"
RUN_LOG = HERE / "rl_refine_run.jsonl"
POLICY = HERE / "rl_policy_pretrained.pt"

#: Refinement stride, overriding `contract.MAX_STEP`'s 0.15 **here only**.
#: 0.04 x 8 steps = 0.32 box widths of reach. See the module docstring.
REFINE_MAX_STEP: float = 0.04

#: The bar, measured in entry 25. Quoted so the comparison cannot drift.
LIBRARY_BASELINE: dict = {"n_feasible": 9, "n": 16, "median_reward": 10.0476,
                          "mean_sims": 4.0}

SEED: int = 23_0821


@dataclass
class RefineResult:
    """One request: what the library gave, what the policy did to it."""

    peaking_db: float
    f_peak_hz: float
    lib_reward: float
    lib_feasible: bool
    lib_sims: int
    pol_reward: float
    pol_feasible: bool
    pol_sims: int
    delta: float
    n_steps: int
    improved: bool
    broke_it: bool
    lib_u: Optional[list] = None
    pol_u: Optional[list] = None
    worst_spec: Optional[str] = None


def _load_policy(obs_dim: int, act_dim: int, seed: int):
    import torch

    from nebula.rl.ppo import ActorCritic, PPOConfig

    if not POLICY.exists():
        raise FileNotFoundError(
            f"{POLICY.name} is missing. This experiment refines with a TRAINED "
            f"policy; running it with a fresh network would measure random "
            f"perturbation of the library's answer, which is a different and "
            f"far less interesting question.")
    c = torch.load(POLICY, weights_only=False)
    if int(c.get("obs_dim", -1)) != obs_dim or int(c.get("act_dim", -1)) != act_dim:
        raise ValueError(
            f"{POLICY.name} has obs/act ({c.get('obs_dim')}, "
            f"{c.get('act_dim')}), env has ({obs_dim}, {act_dim})")
    cfg = PPOConfig(seed=seed)
    net = ActorCritic(obs_dim, act_dim, cfg.hidden, cfg.log_std_init)
    net.load_state_dict(c["state_dict"])
    return net, c


def refine_one(net, target, seed: int) -> RefineResult:
    """Library start -> policy refinement -> paired comparison. **One request.**

    Both endpoints are scored through `exp_corner_rl._score`, the same shared
    evaluator every arm in entry 25 used, so this result sits on the same axis
    as the bar it is measured against.
    """
    import torch

    from nebula.design import solve_library
    from nebula.experiments.exp_corner_rl import (
        SpecConditionedCornerEnv, _budget_calls, _score, _screen,
    )
    from nebula.rl.spec_dist import SpecTarget

    points = _screen()

    # -- what the library gives, scored ------------------------------------
    lib = solve_library(SpecTarget(peaking_db=target.peaking_db,
                                   f_peak_hz=target.f_peak_hz))
    lib_ev = _score(lib["u"], target)

    # -- the policy refines it ---------------------------------------------
    env = SpecConditionedCornerEnv(points, [target], seed=seed)
    # **The stride override, here and nowhere else** (rule 7).
    env.env.cfg.max_step = REFINE_MAX_STEP
    env.env.base.cfg.max_step = REFINE_MAX_STEP

    # Seeded at the library's design: `reset(u0=...)` MEASURES the start point
    # rather than assuming it is valid, and raises if it is not -- which is the
    # correct behaviour, because refining an unbuildable start is meaningless.
    try:
        obs, _ = env.reset(np.asarray(lib["u"], dtype=float))
    except Exception as exc:                                    # noqa: BLE001
        return RefineResult(
            peaking_db=target.peaking_db, f_peak_hz=target.f_peak_hz,
            lib_reward=float(lib_ev.reward), lib_feasible=bool(lib_ev.feasible),
            lib_sims=int(lib_ev.n_sims), pol_reward=float(lib_ev.reward),
            pol_feasible=bool(lib_ev.feasible), pol_sims=int(lib_ev.n_sims),
            delta=0.0, n_steps=0, improved=False, broke_it=False,
            lib_u=[float(x) for x in lib["u"]],
            worst_spec=f"start not refinable: {exc}"[:120])

    base = _budget_calls(env.env)
    best_u = np.array(env.env._u, dtype=float)
    # **The starting design is a CANDIDATE, not just a starting point.**
    #
    # This was `-np.inf`, so only step rewards competed and the first edit won
    # by default: **the policy was structurally incapable of returning "I
    # looked, and the design I was given was best."** A refiner that cannot
    # decline to edit is not a refiner; it is forced to change something.
    #
    # Measured cost of that defect (entry 27): the policy BROKE 3 of the
    # library's 9 working designs -- +10.3282 -> -0.3970, +10.0944 -> -0.3569,
    # +10.0009 -> -0.0841 -- and declining was the correct move in all three.
    #
    # `lib_ev.reward` is the same design scored through the same evaluator, so
    # this is a like-for-like comparison rather than two scales meeting.
    best_r = float(lib_ev.reward)
    n_steps = 0
    done = False
    while not done:
        with torch.no_grad():
            o = torch.as_tensor(obs, dtype=torch.float32).unsqueeze(0)
            a = net.distribution(o).mean.squeeze(0).numpy()
        obs, r, term, trunc, _ = env.step(a)
        n_steps += 1
        if r > best_r:
            best_r, best_u = r, np.array(env.env._u, dtype=float)
        done = bool(term or trunc)
    used = _budget_calls(env.env) - base

    pol_ev = _score(best_u, target)
    delta = float(pol_ev.reward) - float(lib_ev.reward)
    return RefineResult(
        peaking_db=target.peaking_db, f_peak_hz=target.f_peak_hz,
        lib_reward=float(lib_ev.reward), lib_feasible=bool(lib_ev.feasible),
        lib_sims=int(lib_ev.n_sims), pol_reward=float(pol_ev.reward),
        pol_feasible=bool(pol_ev.feasible),
        pol_sims=int(used + pol_ev.n_sims + lib_ev.n_sims),
        delta=delta, n_steps=n_steps,
        improved=bool(pol_ev.feasible and not lib_ev.feasible),
        # **The outcome that must not be hidden**: the policy was handed a
        # working design and returned a broken one.
        broke_it=bool(lib_ev.feasible and not pol_ev.feasible),
        lib_u=[float(x) for x in lib["u"]],
        pol_u=[float(x) for x in best_u], worst_spec=pol_ev.worst_spec)


def run(seed: int = SEED, n_test: int = 16) -> dict:
    from nebula.experiments.exp_corner_rl import _screen
    from nebula.experiments.runlock import hold, stamp
    from nebula.rl.spec_dist import interpolation_split

    with hold("rl_refine"):
        t0 = time.time()
        split = interpolation_split(n_train=64, n_test=n_test, seed=seed)
        points = _screen()
        net, ck = _load_policy(7 + 8 + 2 + 1, 7, seed)
        print(f"refining with {POLICY.name}: {ck['steps']:,} analytic steps, "
              f"{ck['spice_calls']} SPICE calls, max_step={REFINE_MAX_STEP}",
              flush=True)

        rows: list[RefineResult] = []
        with RUN_LOG.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps({"event": "start", "seed": seed,
                                 "max_step": REFINE_MAX_STEP,
                                 "policy": POLICY.name,
                                 "bar": LIBRARY_BASELINE,
                                 "screen": [p.label for p in points],
                                 **stamp()}) + "\n")
            for i, t in enumerate(split.test):
                r = refine_one(net, t, seed=seed + i)
                rows.append(r)
                fh.write(json.dumps(asdict(r)) + "\n")
                fh.flush()
                tag = ("IMPROVED" if r.improved else
                       "BROKE IT" if r.broke_it else "        ")
                print(f"[{i + 1}/{len(split.test)}] {t.peaking_db:5.2f} dB @ "
                      f"{t.f_peak_hz / 1e9:.3f} GHz   lib {r.lib_reward:+9.4f} "
                      f"-> pol {r.pol_reward:+9.4f}  ({r.delta:+8.4f}) {tag}  "
                      f"{r.pol_sims:3d} sims", flush=True)

        out = {
            "task": "does the policy improve the library's retrieved design?",
            **stamp(),
            "policy": POLICY.name, "policy_steps": ck["steps"],
            "max_step": REFINE_MAX_STEP, "bar": LIBRARY_BASELINE,
            "n": len(rows),
            "lib_feasible": sum(1 for r in rows if r.lib_feasible),
            "pol_feasible": sum(1 for r in rows if r.pol_feasible),
            "n_improved": sum(1 for r in rows if r.improved),
            "n_broke": sum(1 for r in rows if r.broke_it),
            "lib_median": float(np.median([r.lib_reward for r in rows])),
            "pol_median": float(np.median([r.pol_reward for r in rows])),
            "median_delta": float(np.median([r.delta for r in rows])),
            "mean_pol_sims": float(np.mean([r.pol_sims for r in rows])),
            "wall_clock_s": time.time() - t0,
            "results": [asdict(r) for r in rows],
        }
        RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
        return out


def _report(d: dict) -> None:
    print()
    print("=" * 78)
    print(f"RL ON TOP OF RETRIEVAL — {d['n']} held-out requests, "
          f"{d['wall_clock_s'] / 60:.1f} min")
    print("=" * 78)
    print(f"  library start   {d['lib_feasible']:2d}/{d['n']} feasible   "
          f"median {d['lib_median']:+9.4f}   {d['bar']['mean_sims']:.1f} sims/req")
    print(f"  after refining  {d['pol_feasible']:2d}/{d['n']} feasible   "
          f"median {d['pol_median']:+9.4f}   {d['mean_pol_sims']:.1f} sims/req")
    print()
    print(f"  requests the policy FIXED  : {d['n_improved']}")
    print(f"  requests the policy BROKE  : {d['n_broke']}")
    print(f"  median paired delta        : {d['median_delta']:+.4f}")
    print()
    # The decision rule from PREDICTIONS entry 27, applied mechanically so the
    # verdict cannot drift in the writing.
    bar = d["bar"]["n_feasible"]
    if d["pol_feasible"] > bar:
        print(f"  Q1 HIT: {d['pol_feasible']} > {bar}. Retrieval finds the "
              f"neighbourhood, RL refines it -- report WITH the cost.")
    elif d["pol_feasible"] >= bar - 1:
        print(f"  Q1 miss, Q2 hit: {d['pol_feasible']} vs the library's {bar}. "
              f"RL neither helps nor harms on top of retrieval.")
        print("  The contribution claim STAYS DROPPED.")
    else:
        print(f"  Q1 and Q2 both miss: {d['pol_feasible']} vs {bar}. **RL "
              f"actively degrades a retrieved design.** Report it as the "
              f"strongest negative available, with the degradation quantified.")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--analyse", action="store_true")
    ap.add_argument("--seed", type=int, default=SEED)
    a = ap.parse_args(argv)
    if a.run:
        _report(run(seed=a.seed))
    elif a.analyse:
        if not RESULTS.exists():
            raise SystemExit(f"{RESULTS.name} missing: run --run first")
        _report(json.loads(RESULTS.read_text(encoding="utf-8")))
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":                                  # pragma: no cover
    raise SystemExit(main())
