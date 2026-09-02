"""
experiments/exp_adapt_controls.py — **the controls the RL policy has to beat,
built and measured BEFORE any policy exists.**

    python -m nebula.experiments.exp_adapt_controls --run

WHY THE CONTROLS COME FIRST
-----------------------------
Entry 47 established the rule this file obeys: *a learned arm measured against
no matched control is unfalsifiable.* The project has been here before -- the
SAC proposer looked like a contribution until it was scored against a
zero-simulation library lookup and came back 1 of 16 against 6 (entry 36).

So the controls are written, run and committed **before** the policy, and the
bar the policy must clear is a number that already exists.

THE ARMS
---------
Every arm is driven through the **same** `AdaptEnv` with the **same**
`AdaptReward`, so trials, compliance and return are accounted identically and no
comparison can be confounded by the scoring.

* **`oracle`** -- locks a compliant code if one exists, in one trial. It cheats:
  it reads ground truth. **Not an arm, a ceiling.** It answers "was this corner
  solvable at all", which is the only fair denominator.
* **`exhaustive`** -- tries every code, then locks the one with the largest
  observed eye. This is the honest brute force: 64 trials, and it still only
  ever *observes* the eye, so it can lock a big-eye code that fails HD3.
* **`hillclimb`** -- **the matched control.** Coordinate ascent on the observed
  eye: start at the centre code, probe +-1 on the boost axis, move while the eye
  improves, then the same on the frequency axis. It is what an engineer actually
  builds, it uses only what a receiver can see, and entry 70 measured the
  response map monotone on every row and column, so the ascent is well posed.
* **`fixed`** -- the single code that is compliant at the most TRAIN corners,
  chosen offline and then frozen. **This is the no-tuning baseline**: if it
  scores as well as the others, the bank is decoration.
* **`random`** -- codes drawn without replacement until the budget runs out.
  The floor, and the arm PPO was statistically indistinguishable from when this
  project last measured a learner (`BASELINES.md`).

THE SPLIT, AND WHY IT IS BY PROCESS
-------------------------------------
Corners are split **by process**: `tt`/`ss`/`ff` train (27 corners), `sf`/`fs`
test (18). Not at random.

A policy evaluated on the corners it trained on is measuring memorisation, and
this project has already established what memorisation is worth here -- a
zero-simulation lookup serves 32 of 32 held-out targets, so a learner that only
memorises will look excellent and mean nothing. The mixed corners are the
honest held-out set: a real part meets silicon its designer never simulated, and
`sf`/`fs` are the two the 4-corner screen was extended to cover precisely
because they behave differently (decision D1).

**`fixed` chooses its code on TRAIN corners only.** So does any policy. The
`oracle` and `exhaustive` arms are corner-agnostic by construction.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Callable, Optional, Sequence

import numpy as np

from nebula.experiments.exp_coverage import FREQ_REQUESTS, PEAKING_REQUESTS
from nebula.rl.adapt_env import (
    LOCK,
    N_CODES,
    OBS_PER_CODE,
    AdaptEnv,
    AdaptReward,
    BankTable,
    Episode,
)

HERE = Path(__file__).resolve().parent
RUN_LOG = HERE / "bank_sweep_run.jsonl"
RESULTS = HERE / "adapt_controls_results.json"

#: Held-out processes. See the module docstring: this is a split by PROCESS, so
#: the test corners are ones no arm was tuned on.
TRAIN_PROCESSES: tuple[str, ...] = ("tt", "ss", "ff")
TEST_PROCESSES: tuple[str, ...] = ("sf", "fs")

#: Trial budget for the budgeted arms. 8 of 64 codes is ~12 % of the bank and
#: the same horizon `rl/env.py` uses, so the policy inherits a familiar one.
BUDGET: int = 8

#: The centre of the 8x8 grid, where a hill-climb starts. Code = i_rs*8 + i_cs.
CENTRE_RS, CENTRE_CS = 3, 3


def _process(corner: str) -> str:
    return corner.split("/")[0]


def _eye_of(obs: np.ndarray, code: int) -> Optional[float]:
    """The eye this arm OBSERVED at `code`, or None if it never tried it."""
    i = 3 + int(code) * OBS_PER_CODE
    return float(obs[i + 1]) if obs[i] > 0.5 else None


# ── the arms ────────────────────────────────────────────────────────────────


def arm_oracle(env: AdaptEnv) -> Episode:
    """Ceiling, not an arm: locks a compliant code when one exists."""
    ep = env.ep
    good = env.t.solvable(ep.corner, ep.target_f_peak_hz, ep.target_peaking_db)
    env.step(good[0] if good else 0)
    env.step(LOCK)
    return env.ep


def arm_exhaustive(env: AdaptEnv) -> Episode:
    """Try everything, lock the biggest observed eye. 64 trials."""
    best, best_eye = None, -1.0
    for c in range(N_CODES):
        obs, _, term, _, _ = env.step(c)
        if term:
            return env.ep
        e = _eye_of(obs, c)
        if e is not None and e > best_eye:
            best, best_eye = c, e
    if best is not None:
        env.step(best)
        env.step(LOCK)
    return env.ep


def arm_hillclimb(env: AdaptEnv) -> Episode:
    """**The matched control.** Coordinate ascent on the observed eye.

    Entry 70 measured the response map monotone and separable on every row and
    column, so ascending one axis at a time is well posed. What it cannot see is
    everything that is not the eye -- which is the gap a learned policy has to
    exploit if it is going to be worth anything.
    """
    rs, cs = CENTRE_RS, CENTRE_CS
    obs, _, term, _, _ = env.step(rs * 8 + cs)
    if term:
        return env.ep
    cur = _eye_of(obs, rs * 8 + cs) or -1.0
    for axis in (0, 1):
        improving = True
        while improving:
            improving = False
            for d in (+1, -1):
                nr = rs + d if axis == 0 else rs
                nc = cs if axis == 0 else cs + d
                if not (0 <= nr < 8 and 0 <= nc < 8):
                    continue
                code = nr * 8 + nc
                if _eye_of(obs, code) is not None:
                    continue
                obs, _, term, _, _ = env.step(code)
                if term:
                    return env.ep
                e = _eye_of(obs, code) or -1.0
                if e > cur:
                    rs, cs, cur, improving = nr, nc, e, True
                    break
    env.step(rs * 8 + cs)
    env.step(LOCK)
    return env.ep


def _fixed_code(table: BankTable, corners: Sequence[str],
                requests: Sequence[tuple]) -> int:
    """The code compliant at the most (TRAIN corner, request) pairs."""
    score = np.zeros(N_CODES, dtype=int)
    for c in corners:
        for pk, f in requests:
            for code in range(N_CODES):
                if table.compliant(code, c, f, pk):
                    score[code] += 1
    return int(np.argmax(score))


def make_arm_fixed(code: int) -> Callable:
    def arm(env: AdaptEnv) -> Episode:
        env.step(code)
        env.step(LOCK)
        return env.ep
    arm.__name__ = f"fixed_{code}"
    return arm


def make_arm_random(seed: int) -> Callable:
    def arm(env: AdaptEnv) -> Episode:
        rng = np.random.default_rng(seed + env.ep.n_trials)
        order = rng.permutation(N_CODES)[:BUDGET]
        best, best_eye = None, -1.0
        for c in order:
            obs, _, term, _, _ = env.step(int(c))
            if term:
                return env.ep
            e = _eye_of(obs, int(c))
            if e is not None and e > best_eye:
                best, best_eye = int(c), e
        if best is not None:
            env.step(best)
            env.step(LOCK)
        return env.ep
    arm.__name__ = "random"
    return arm


# ── scoring ─────────────────────────────────────────────────────────────────


def score_arm(table: BankTable, arm: Callable, corners: Sequence[str],
              requests: Sequence[tuple], reward: AdaptReward,
              max_trials: int) -> dict:
    eps: list[Episode] = []
    for c in corners:
        for pk, f in requests:
            env = AdaptEnv(table, [(pk, f)], reward=reward,
                           max_trials=max_trials, seed=0)
            env.reset(corner=c, request=(pk, f))
            eps.append(arm(env))
    solvable = [e for e in eps if e.solvable]
    ok = [e for e in eps if e.locked_compliant]
    return {
        "arm": getattr(arm, "__name__", str(arm)),
        "n_episodes": len(eps),
        "n_solvable": len(solvable),
        "n_compliant_locks": len(ok),
        # The only fair denominator: an arm cannot be blamed where the bank has
        # no compliant code at all.
        "compliance_rate_of_solvable": (len(ok) / len(solvable)
                                        if solvable else None),
        "mean_trials": float(np.mean([e.n_trials for e in eps])),
        "mean_trials_on_solvable": (float(np.mean([e.n_trials
                                                   for e in solvable]))
                                    if solvable else None),
        "mean_return": float(np.mean([e.ret for e in eps])),
        "n_false_locks": sum(1 for e in eps
                             if e.locked_compliant is False and e.solvable),
    }


def run() -> dict:
    t0 = time.time()
    table = BankTable.from_jsonl(RUN_LOG)
    requests = [(pk, f) for pk in PEAKING_REQUESTS for f in FREQ_REQUESTS]
    train = [c for c in table.corners if _process(c) in TRAIN_PROCESSES]
    test = [c for c in table.corners if _process(c) in TEST_PROCESSES]
    if not train or not test:
        raise ValueError(f"empty split: {len(train)} train, {len(test)} test")
    reward = AdaptReward()
    fixed = _fixed_code(table, train, requests)
    print(f"train {len(train)} corners, test {len(test)}; "
          f"fixed arm uses code {fixed} (chosen on TRAIN only)", flush=True)

    arms = [arm_oracle, arm_exhaustive, arm_hillclimb, make_arm_fixed(fixed),
            make_arm_random(20260902)]
    rows = []
    for arm in arms:
        budget = N_CODES + 2 if arm is arm_exhaustive else BUDGET
        r = score_arm(table, arm, test, requests, reward, budget)
        r["budget"] = budget
        rows.append(r)
        print(f"  {r['arm']:<12} compliant {r['n_compliant_locks']:3d}/"
              f"{r['n_solvable']:3d} solvable   trials {r['mean_trials']:5.2f}"
              f"   return {r['mean_return']:7.2f}", flush=True)

    out = {
        "task": "adaptation controls, measured BEFORE any policy exists",
        "source": RUN_LOG.name,
        "split": {"by": "process", "train_processes": list(TRAIN_PROCESSES),
                  "test_processes": list(TEST_PROCESSES),
                  "n_train_corners": len(train), "n_test_corners": len(test)},
        "reward": reward.__dict__, "budget": BUDGET,
        "fixed_code_chosen_on_train": fixed,
        "n_requests": len(requests), "arms": rows,
        "wall_clock_s": time.time() - t0,
        "simulations_run_by_this_file": 0,
    }
    RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def _report(d: dict) -> None:
    print()
    print("=" * 78)
    print(f"ADAPTATION CONTROLS — {d['split']['n_test_corners']} held-out "
          f"corners x {d['n_requests']} requests, 0 simulations")
    print("=" * 78)
    print(f"  split by process: train {d['split']['train_processes']} -> "
          f"test {d['split']['test_processes']}")
    print(f"  reward {d['reward']}")
    print()
    print("  arm            budget  compliant/solvable   trials   return")
    for r in d["arms"]:
        rate = r["compliance_rate_of_solvable"]
        print(f"   {r['arm']:<13} {r['budget']:4d}   "
              f"{r['n_compliant_locks']:3d}/{r['n_solvable']:3d} "
              f"({0.0 if rate is None else 100 * rate:5.1f} %)  "
              f"{r['mean_trials']:6.2f}  {r['mean_return']:7.2f}")
    print()
    print("  THE BAR THE POLICY MUST CLEAR is the hillclimb row, on BOTH")
    print("  compliance and trials. Beating only `random` or only `fixed`")
    print("  is not a contribution (entry 47).")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--analyse", action="store_true")
    a = ap.parse_args(argv)
    if a.run:
        _report(run())
    elif a.analyse:
        if not RESULTS.exists():
            raise SystemExit(f"{RESULTS.name} missing: run --run first")
        _report(json.loads(RESULTS.read_text(encoding="utf-8")))
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":                                  # pragma: no cover
    raise SystemExit(main())
