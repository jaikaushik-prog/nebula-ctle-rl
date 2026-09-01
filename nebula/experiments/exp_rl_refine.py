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
    python -m nebula.experiments.exp_rl_refine --run --n 128     # entry 46

THE SAMPLE SIZE, AND WHY IT IS THE ONLY THING ENTRY 46 CHANGES
----------------------------------------------------------------
The n=16 run returned 2 improved, 0 broken -- and the exact two-sided sign test
on that is **p = 0.50**, which `NEXT_AGENT_SAC.md` correctly refuses to quote as
a win. But with zero regressions the sign test cannot reach p < 0.05 until
**six** improvements exist, and sixteen requests cannot produce six at the
observed 12.5 % rate except by luck. **The experiment could not detect its own
effect.** `--n` fixes exactly that and nothing else: same checkpoint, same
`REFINE_MAX_STEP`, same reward, same screen, same target law, `n_train` still
64 so every test target stays unseen.

The control is free. `sample_targets` draws sequentially from one
`default_rng`, so the draw is prefix-stable and **the first 16 rows of any
larger run ARE the n=16 experiment, re-run** -- scored automatically by
`control_block` against the committed artifact. If they do not reproduce,
nothing downstream of them may be read.
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

#: The sample size entry 28 ran at, and the one `RESULTS` holds. A run at any
#: other `n` writes its own artifact so this one cannot be overwritten -- it
#: backs a published number (`NEXT_AGENT_SAC.md` §39) and an experiment that
#: silently replaces its own control is not a control.
N_TEST_DEFAULT: int = 16


def results_path(n_test: int) -> Path:
    """Where a run at this sample size writes. `n=16` keeps the historic name."""
    if int(n_test) == N_TEST_DEFAULT:
        return RESULTS
    return HERE / f"rl_refine_results_n{int(n_test)}.json"


def run_log_path(n_test: int) -> Path:
    """Per-`n` JSONL, for the same reason `results_path` is per-`n`."""
    if int(n_test) == N_TEST_DEFAULT:
        return RUN_LOG
    return HERE / f"rl_refine_run_n{int(n_test)}.jsonl"

#: Refinement stride, overriding `contract.MAX_STEP`'s 0.15 **here only**.
#: 0.04 x 8 steps = 0.32 box widths of reach. See the module docstring.
REFINE_MAX_STEP: float = 0.04

#: The bar, measured in entry 25. Quoted so the comparison cannot drift.
LIBRARY_BASELINE: dict = {"n_feasible": 9, "n": 16, "median_reward": 10.0476,
                          "mean_sims": 4.0}

SEED: int = 23_0821


def sign_test_p(n_improved: int, n_broke: int) -> float:
    """Exact two-sided sign test on the PAIRED outcomes. **Ties are dropped.**

    The question "does refining help" is paired -- every request is scored
    against the design the policy started from -- so the statistic is the
    number of positive differences among the requests that moved at all.
    Requests where the policy declined to edit, or edited to no effect, carry
    no information about direction and are excluded; that is what a sign test
    is, and it is why `n` here is `n_improved + n_broke` and not the number of
    requests.

    **This is the number entry 28's 11-of-16 was missing.** At 2 improved and
    0 broken it returns 0.5: with zero regressions the test cannot reach 0.05
    until six improvements exist, so sixteen requests could not have detected a
    12.5 % effect however real it was.
    """
    k, m = int(n_improved), int(n_improved) + int(n_broke)
    if m == 0:
        return 1.0
    from math import comb
    # Two-sided exact binomial at p=0.5: sum the tail at least as extreme as k
    # on BOTH sides. Symmetric, so double the smaller tail and clip at 1.
    lo = min(k, m - k)
    tail = sum(comb(m, i) for i in range(lo + 1)) / (2.0 ** m)
    return float(min(1.0, 2.0 * tail))


def wilson_ci(k: int, n: int, z: float = 1.959963984540054) -> tuple:
    """95 % Wilson score interval for a rate. Used, never re-derived.

    Wilson rather than normal-approximation because the counts here are small
    and the rates are near zero, where the normal interval goes negative and
    stops meaning anything.
    """
    if n <= 0:
        return (0.0, 0.0)
    p = k / n
    d = 1.0 + z * z / n
    c = p + z * z / (2.0 * n)
    h = z * ((p * (1.0 - p) / n + z * z / (4.0 * n * n)) ** 0.5)
    return (float(max(0.0, (c - h) / d)), float(min(1.0, (c + h) / d)))


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


def control_block(rows: Sequence) -> Optional[dict]:
    """Entry 46's Q1: do the first 16 rows reproduce entry 28?

    `sample_targets` draws sequentially from one `default_rng`, so the target
    draw is PREFIX-STABLE: `interpolation_split(64, 128).test[:16]` is exactly
    `interpolation_split(64, 16).test`. The first sixteen rows of a larger run
    are therefore entry 28's experiment re-run, at no extra cost, and this
    function scores them against the committed artifact.

    Returns `None` when there is no n=16 artifact to compare against, or when
    the run is itself the n=16 run.
    """
    if len(rows) <= N_TEST_DEFAULT or not RESULTS.exists():
        return None
    ref = json.loads(RESULTS.read_text(encoding="utf-8"))
    head = list(rows)[:N_TEST_DEFAULT]
    got = {"n_improved": sum(1 for r in head if r.improved),
           "n_broke": sum(1 for r in head if r.broke_it),
           "lib_feasible": sum(1 for r in head if r.lib_feasible),
           "pol_feasible": sum(1 for r in head if r.pol_feasible)}
    want = {k: int(ref[k]) for k in got}
    return {"reference": RESULTS.name, "expected": want, "observed": got,
            "reproduced": got == want,
            "differs_on": sorted(k for k in got if got[k] != want[k])}


def run(seed: int = SEED, n_test: int = N_TEST_DEFAULT) -> dict:
    from nebula.experiments.exp_corner_rl import _screen
    from nebula.experiments.runlock import hold, stamp
    from nebula.rl.spec_dist import interpolation_split

    with hold("rl_refine"):
        t0 = time.time()
        # n_train STAYS 64: `rl_policy_pretrained.pt` trained on `all_t[:64]`
        # at this same seed (`exp_rl_pretrain.N_TRAIN_TARGETS`), so holding it
        # fixed is what keeps every test target unseen as `n_test` grows.
        split = interpolation_split(n_train=64, n_test=n_test, seed=seed)
        points = _screen()
        net, ck = _load_policy(7 + 8 + 2 + 1, 7, seed)
        print(f"refining with {POLICY.name}: {ck['steps']:,} analytic steps, "
              f"{ck['spice_calls']} SPICE calls, max_step={REFINE_MAX_STEP}",
              flush=True)

        rows: list[RefineResult] = []
        with run_log_path(n_test).open("w", encoding="utf-8") as fh:
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
        n_imp, n_brk = out["n_improved"], out["n_broke"]
        out["stats"] = {
            "sign_test_p": sign_test_p(n_imp, n_brk),
            "sign_test_n": n_imp + n_brk,
            "improve_rate": n_imp / len(rows),
            "improve_rate_ci95": list(wilson_ci(n_imp, len(rows))),
            "broke_rate": n_brk / len(rows),
            "broke_rate_ci95": list(wilson_ci(n_brk, len(rows))),
            "basis": ("exact two-sided sign test on the PAIRED outcomes; ties "
                      "(the policy declined, or edited to no effect) are "
                      "dropped, so sign_test_n is improved+broke, not n"),
        }
        out["control_first16"] = control_block(rows)
        results_path(n_test).write_text(json.dumps(out, indent=1),
                                        encoding="utf-8")
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

    # ── statistics ────────────────────────────────────────────────────────
    # Recomputed rather than read, so an artifact written before `stats`
    # existed still reports correctly and the two can never disagree.
    n = d["n"]
    n_imp, n_brk = d["n_improved"], d["n_broke"]
    p = sign_test_p(n_imp, n_brk)
    lo, hi = wilson_ci(n_imp, n)
    print(f"  improvement rate           : {n_imp}/{n} = {n_imp / n:6.2%}"
          f"   95% CI [{lo:.2%}, {hi:.2%}]")
    print(f"  exact two-sided sign test  : p = {p:.4f}   "
          f"(on {n_imp + n_brk} requests that moved)")

    ctrl = d.get("control_first16")
    if ctrl:
        tag = "REPRODUCED" if ctrl["reproduced"] else "DIFFERS"
        print(f"  control, first 16 rows     : {tag} vs {ctrl['reference']}"
              + ("" if ctrl["reproduced"]
                 else f"  -- differs on {', '.join(ctrl['differs_on'])}"))
    print()

    # The decision rule from PREDICTIONS entry 46, applied mechanically so the
    # verdict cannot drift in the writing. Entry 28's fixed bar of 9 is only
    # meaningful at n=16; the paired comparison is what scales.
    if ctrl and not ctrl["reproduced"]:
        print("  Q1 MISSED -- the control did not reproduce. READ NOTHING "
              "ELSE until that is explained (entry 46's decision rule).")
        return
    if n_imp >= n_brk and p < 0.05:
        print(f"  Q2 and Q3 HIT: {n_imp} improved, {n_brk} broken, p = {p:.4f}."
              f"  **RL measurably improves a retrieved design.** Report WITH "
              f"the cost ({d['mean_pol_sims']:.1f} sims/request) and the words "
              f"'on top of retrieval' -- it is not a claim that RL beats it.")
    elif n_imp > n_brk:
        print(f"  Q2 direction holds, Q3 MISSED: {n_imp} improved, {n_brk} "
              f"broken, p = {p:.4f}. The effect points the right way and is "
              f"NOT powered. Report the paired rates and the CI; claim nothing.")
    else:
        print(f"  Q4 MISSED: {n_imp} improved, {n_brk} broken. **Refining a "
              f"retrieved design does not help and may hurt.** Report it as "
              f"the strongest negative available, with the rate quantified.")
    if n < 64:
        print(f"  NOTE: n = {n}. With zero regressions the sign test cannot "
              f"reach p < 0.05 below six improvements (entry 46).")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--analyse", action="store_true")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--n", type=int, default=N_TEST_DEFAULT,
                    help=f"held-out requests to refine (default "
                         f"{N_TEST_DEFAULT}). The ONLY knob entry 46 moves: "
                         f"n=16 could not reach p<0.05 at the observed effect "
                         f"size. Runs at n != {N_TEST_DEFAULT} write their own "
                         f"artifact so the n={N_TEST_DEFAULT} control survives.")
    a = ap.parse_args(argv)
    if a.n < 1:
        raise SystemExit(f"--n must be >= 1, got {a.n}")
    if a.run:
        _report(run(seed=a.seed, n_test=a.n))
    elif a.analyse:
        path = results_path(a.n)
        if not path.exists():
            raise SystemExit(f"{path.name} missing: run --run --n {a.n} first")
        _report(json.loads(path.read_text(encoding="utf-8")))
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":                                  # pragma: no cover
    raise SystemExit(main())
