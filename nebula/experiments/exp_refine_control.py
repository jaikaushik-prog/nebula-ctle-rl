"""
experiments/exp_refine_control.py — **entry 47: the matched-budget control.
Does 30 decks of RL refinement beat 30 decks spent any other way?**

    python -m nebula.experiments.exp_refine_control --run
    python -m nebula.experiments.exp_refine_control --analyse

WHY ENTRY 46 COULD NOT ANSWER THIS
------------------------------------
Entry 46 compared *refining* against *doing nothing*, and entry 28's fix lets
the policy **decline**. A method that may decline wins that comparison **by
construction**: it cannot do worse than the design it was handed. So the
measured 5 crossings and 0 regressions are consistent with a good policy and
equally consistent with **"movement plus a best-of-visited selector"**, which
needs no policy at all.

This file runs the comparison with a null anybody disbelieves.

THE THREE ARMS, FROM THE SAME START
------------------------------------
    A   the RL refiner, exactly as entry 46 ran it
    B   RANDOM perturbation -- the same env, horizon, stride and selector,
        with actions drawn uniformly instead of from the policy
    C   deeper retrieval -- library ranks 2, 3, 4... on the same screen

**B is the arm that matters.** It is `exp_rl_refine.refine_one` with one
argument changed, so it differs from A in exactly one thing: where the action
comes from. Rule 9 -- the control is the same loop, not a copy of it.

THE POPULATION, AND WHY IT IS 58 AND NOT 128
----------------------------------------------
`improved` requires `not lib_ev.feasible`. In entry 46's n=128 run the library
was **already feasible on 70 requests**, which can never be counted as improved
by construction. Measuring a rate over all 128 was **entry 46's defect 1**.
This file uses the **58 eligible** requests, read out of
`rl_refine_run_n128.jsonl` at **zero simulation cost** -- eligibility is
deterministic given the same split, library and screen.

THE PRIMARY METRIC IS THE PAIRED DELTA, AND THAT IS ARITHMETIC
----------------------------------------------------------------
McNemar's exact test on crossings, with arm B crossing 0:

    A = 5, B = 0  ->  discordant 5  ->  p = 0.0625   CANNOT reach 0.05
    p < 0.05 needs A >= 6 crossings with B at 0.

So the crossing test is **underpowered by construction at n = 58** -- the same
defect entry 46's Q3 had. The primary is therefore the **paired score delta**,
where arm A moved 30 of 58 and there is real signal. Entry 47's **Q4 registers
the crossing null in advance** rather than discovering it afterwards.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from nebula.experiments.exp_rl_refine import (
    REFINE_MAX_STEP, SEED, refine_one, sign_test_p, wilson_ci,
)

HERE = Path(__file__).resolve().parent

#: Entry 46's run log. Read for the eligible set; never written.
ELIGIBLE_SOURCE = HERE / "rl_refine_run_n128.jsonl"

RESULTS = HERE / "refine_control_results.json"
RUN_LOG = HERE / "refine_control_run.jsonl"

#: Entry 46's arm-A numbers on the eligible subset, quoted so Q1 cannot drift.
ARM_A_BASELINE: dict = {"n": 58, "crossings": 5, "moved_up": 30,
                        "moved_down": 2, "declined": 26, "mean_decks": 30.2}


def eligible(source: Path = ELIGIBLE_SOURCE) -> list[dict]:
    """The 58 requests where a crossing is POSSIBLE. **Zero simulations.**

    Row `j` of the log is test target `j` of `interpolation_split(64, 128)`,
    because the log is written in order -- and entry 46 seeded each request
    `SEED + j`. Both facts are needed for arm A to reproduce exactly, so the
    index is carried rather than re-derived from the target values.
    """
    rows = [json.loads(l) for l in
            source.read_text(encoding="utf-8").splitlines()[1:]]
    return [{"index": j, "peaking_db": r["peaking_db"],
             "f_peak_hz": r["f_peak_hz"], "seed": SEED + j,
             "entry46_delta": r["delta"], "entry46_improved": r["improved"],
             "entry46_decks": r["pol_sims"]}
            for j, r in enumerate(rows) if not r["lib_feasible"]]


def random_actor(obs, rng):
    """Arm B. Uniform in the tanh-bounded action box, same shape as the policy's.

    **Not Gaussian noise around the policy** -- that would be a perturbed
    policy, not a control. This is the action the env would get if nothing had
    ever been trained, which is what the comparison is about.
    """
    from nebula.rl.contract import N_ACTIONS

    return rng.uniform(-1.0, 1.0, size=N_ACTIONS)


def retrieval_deeper(target, budget_decks: int, seed: int) -> dict:
    """Arm C. Spend the same decks reading the library DEEPER instead.

    Ranks 2, 3, 4... scored on the same screen, stopping when the budget is
    spent. Rank 1 is the start every arm shares, so it is the incumbent here
    exactly as it is the `best_r` seed in `refine_one` -- the selector is the
    same in all three arms, which is the point.
    """
    from nebula.experiments.exp_corner_rl import _score
    from nebula.experiments.exp_hybrid import library_candidates_k
    from nebula.rl.spec_dist import SpecTarget

    t = SpecTarget(peaking_db=target["peaking_db"],
                   f_peak_hz=target["f_peak_hz"])
    # One extra rank beyond what the budget can plausibly buy, then truncated
    # by decks below -- asking for fewer would cap the arm before its budget.
    cands = library_candidates_k(t.f_peak_hz, t.peaking_db, 12)

    start = _score(cands[0], t) if cands else None
    if start is None:
        return {"ok": False, "reason": "library returned no candidate",
                "decks": 0, "crossed": False, "delta": 0.0, "n_scored": 0}

    best_r = float(start.reward)
    best_feasible = bool(start.feasible)
    decks = int(start.n_sims)
    n_scored = 0
    for u in cands[1:]:
        if decks >= budget_decks:
            break
        ev = _score(u, t)
        decks += int(ev.n_sims)
        n_scored += 1
        if float(ev.reward) > best_r:
            best_r, best_feasible = float(ev.reward), bool(ev.feasible)
    return {"ok": True, "decks": decks, "n_scored": n_scored,
            "start_feasible": bool(start.feasible),
            "crossed": bool(best_feasible and not start.feasible),
            "delta": float(best_r - float(start.reward)),
            "reward": best_r}


def _mcnemar_p(only_a: int, only_b: int) -> float:
    """Exact two-sided McNemar on discordant pairs. **The paired crossing test.**

    Identical arithmetic to `sign_test_p`, applied to the pairs where the two
    arms disagree -- which is what makes it the paired test rather than two
    independent proportions. Reused rather than re-derived (rule 9).
    """
    return sign_test_p(only_a, only_b)


def run(n: Optional[int] = None, seed: int = SEED) -> dict:
    """All three arms over the eligible set. Arm A first, so B and C can match
    the budget it actually spent on each request."""
    import torch                                            # noqa: F401

    from nebula.experiments.exp_rl_refine import _load_policy
    from nebula.experiments.runlock import hold, stamp
    from nebula.rl.spec_dist import SpecTarget

    with hold("refine_control"):
        t0 = time.time()
        targets = eligible()
        if n is not None:
            targets = targets[:int(n)]
        net, ck = _load_policy(7 + 8 + 2 + 1, 7, seed)
        print(f"entry 47: {len(targets)} eligible requests, 3 arms, "
              f"policy {ck['steps']:,} analytic steps, "
              f"max_step={REFINE_MAX_STEP}", flush=True)

        rows: list[dict] = []
        with RUN_LOG.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps({"event": "start", "seed": seed,
                                 "n_eligible": len(targets),
                                 "baseline": ARM_A_BASELINE,
                                 "max_step": REFINE_MAX_STEP,
                                 **stamp()}) + "\n")
            for k, t in enumerate(targets):
                tgt = SpecTarget(peaking_db=t["peaking_db"],
                                 f_peak_hz=t["f_peak_hz"])
                # ARM A -- same seed as entry 46, so Q1 can reproduce it.
                a = refine_one(net, tgt, seed=t["seed"])
                # ARM B -- the same loop, one argument different.
                b = refine_one(net, tgt, seed=t["seed"], actor=random_actor)
                # ARM C -- matched to what A actually spent here.
                c = retrieval_deeper(t, budget_decks=int(a.pol_sims),
                                     seed=t["seed"])
                row = {
                    "index": t["index"],
                    "peaking_db": t["peaking_db"], "f_peak_hz": t["f_peak_hz"],
                    "A_delta": a.delta, "A_crossed": a.improved,
                    "A_decks": a.pol_sims, "A_steps": a.n_steps,
                    "B_delta": b.delta, "B_crossed": b.improved,
                    "B_decks": b.pol_sims, "B_steps": b.n_steps,
                    "C_delta": c["delta"], "C_crossed": c["crossed"],
                    "C_decks": c["decks"], "C_scored": c["n_scored"],
                    "entry46_delta": t["entry46_delta"],
                    "entry46_improved": t["entry46_improved"],
                    "A_reproduces_entry46": bool(
                        a.improved == t["entry46_improved"]
                        and abs(a.delta - t["entry46_delta"]) < 1e-9),
                }
                rows.append(row)
                fh.write(json.dumps(row) + "\n")
                fh.flush()
                print(f"[{k + 1}/{len(targets)}] {t['peaking_db']:5.2f} dB @ "
                      f"{t['f_peak_hz'] / 1e9:.3f} GHz   "
                      f"A {a.delta:+8.4f}{'*' if a.improved else ' '} "
                      f"B {b.delta:+8.4f}{'*' if b.improved else ' '} "
                      f"C {c['delta']:+8.4f}{'*' if c['crossed'] else ' '}   "
                      f"decks {a.pol_sims}/{b.pol_sims}/{c['decks']}",
                      flush=True)

        out = _summarise(rows)
        out.update({"task": "entry 47: matched-budget control",
                    **stamp(), "seed": seed, "policy": ck["steps"],
                    "max_step": REFINE_MAX_STEP,
                    "baseline": ARM_A_BASELINE,
                    "wall_clock_s": time.time() - t0, "rows": rows})
        RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
        return out


def _summarise(rows: Sequence[dict]) -> dict:
    n = len(rows)
    out: dict = {"n": n}
    for arm in ("A", "B", "C"):
        cr = sum(1 for r in rows if r[f"{arm}_crossed"])
        up = sum(1 for r in rows if r[f"{arm}_delta"] > 1e-9)
        dn = sum(1 for r in rows if r[f"{arm}_delta"] < -1e-9)
        lo, hi = wilson_ci(cr, n) if n else (0.0, 0.0)
        out[arm] = {"crossings": cr, "cross_rate": cr / n if n else 0.0,
                    "cross_ci95": [lo, hi], "moved_up": up, "moved_down": dn,
                    "declined": n - up - dn,
                    "mean_decks": float(np.mean([r[f"{arm}_decks"]
                                                 for r in rows])) if n else 0.0,
                    "median_delta": float(np.median([r[f"{arm}_delta"]
                                                     for r in rows])) if n else 0.0}

    # Q2 -- the PRIMARY. Paired, on the per-request difference.
    diff = np.array([r["A_delta"] - r["B_delta"] for r in rows], dtype=float)
    nz = diff[np.abs(diff) > 1e-12]
    try:
        from scipy.stats import wilcoxon

        p_w = float(wilcoxon(nz).pvalue) if nz.size else 1.0
    except Exception as exc:                                    # noqa: BLE001
        p_w = float("nan")
        out["wilcoxon_error"] = repr(exc)
    out["Q2_primary"] = {
        "test": "Wilcoxon signed-rank on per-request (A_delta - B_delta)",
        "n_nonzero_pairs": int(nz.size), "p": p_w,
        "median_diff": float(np.median(diff)) if n else 0.0,
        "a_better": int(np.sum(diff > 1e-12)),
        "b_better": int(np.sum(diff < -1e-12))}

    # Q3/Q4 -- crossings, paired.
    only_a = sum(1 for r in rows if r["A_crossed"] and not r["B_crossed"])
    only_b = sum(1 for r in rows if r["B_crossed"] and not r["A_crossed"])
    out["Q4_mcnemar"] = {"only_A": only_a, "only_B": only_b,
                         "p": _mcnemar_p(only_a, only_b),
                         "note": ("registered in advance as an expected NULL: "
                                  "with only_B = 0 this needs only_A >= 6 to "
                                  "reach 0.05, and entry 46 measured 5")}
    # **Q1 is scored PER ROW, not on aggregate counts.**
    #
    # Matching three totals against `ARM_A_BASELINE` is both weaker and wrong
    # on a truncated run: two rows can never sum to the full set's 5 crossings,
    # so `--n 2` would always report a control failure and refuse to print
    # anything. Row-level identity is the stronger claim anyway -- it says each
    # request produced the same delta and the same crossing, not merely that
    # the totals happened to agree. The aggregate comparison is kept as a
    # SECOND check, applied only when the whole eligible set has been run.
    n_repro = sum(1 for r in rows if r["A_reproduces_entry46"])
    complete = n == ARM_A_BASELINE["n"]
    out["Q1_control"] = {
        "n_reproduced": n_repro, "n": n,
        "reproduced": n_repro == n,
        "complete_run": complete,
        "crossings_now": out["A"]["crossings"],
        "crossings_entry46": ARM_A_BASELINE["crossings"],
        "aggregate_matches": (
            out["A"]["crossings"] == ARM_A_BASELINE["crossings"]
            and out["A"]["moved_up"] == ARM_A_BASELINE["moved_up"]
            and out["A"]["moved_down"] == ARM_A_BASELINE["moved_down"])
        if complete else None}
    return out


def _report(d: dict) -> None:
    n = d["n"]
    print()
    print("=" * 78)
    print(f"ENTRY 47 — MATCHED-BUDGET CONTROL, {n} eligible requests, "
          f"{d.get('wall_clock_s', 0) / 60:.1f} min")
    print("=" * 78)
    print(f"  {'arm':<26}{'crossed':>9}{'up':>6}{'down':>6}{'decl':>6}"
          f"{'decks':>8}")
    print("  " + "-" * 68)
    for arm, name in (("A", "A  RL refiner"), ("B", "B  random, same budget"),
                      ("C", "C  deeper retrieval")):
        a = d[arm]
        print(f"  {name:<26}{a['crossings']:>6} /{n:<2}{a['moved_up']:>6}"
              f"{a['moved_down']:>6}{a['declined']:>6}{a['mean_decks']:>8.1f}")
    q1 = d["Q1_control"]
    print()
    print(f"  Q1 control : arm A {'REPRODUCES' if q1['reproduced'] else 'DIFFERS from'}"
          f" entry 46 row for row -- {q1['n_reproduced']}/{q1['n']} identical")
    if q1.get("complete_run"):
        print(f"               aggregate {q1['crossings_now']} vs "
              f"{q1['crossings_entry46']} crossings: "
              f"{'matches' if q1['aggregate_matches'] else 'DIFFERS'}")
    else:
        print(f"               (truncated run -- the {d['n']}-row subset cannot "
              f"reproduce the full set's totals, so only row identity is scored)")
    q2 = d["Q2_primary"]
    print(f"  Q2 PRIMARY : Wilcoxon on (A-B) deltas  p = {q2['p']:.4f}"
          f"   A better on {q2['a_better']}, B better on {q2['b_better']}")
    q4 = d["Q4_mcnemar"]
    print(f"  Q4 crossing: McNemar exact  p = {q4['p']:.4f}"
          f"   (only A {q4['only_A']}, only B {q4['only_B']})")
    print()
    if not q1["reproduced"]:
        print("  Q1 MISSED -- the control did not reproduce. READ NOTHING ELSE.")
        return
    if q2["p"] < 0.05 and q2["a_better"] > q2["b_better"]:
        print("  Q2 HIT: RL refinement beats a MATCHED BUDGET of random movement")
        print("  from the same start. That is a real RL contribution -- report it")
        print(f"  with the cost ({d['A']['mean_decks']:.1f} decks/request) and the")
        print("  words 'on top of retrieval'.")
    elif d["A"]["crossings"] > d["B"]["crossings"]:
        print("  Q2 MISSED, Q3 direction holds. Underpowered; report both rates")
        print("  and the CI, and claim nothing.")
    else:
        print("  Q2 AND Q3 BOTH MISSED: what entry 46 measured was the SELECTOR,")
        print("  not the policy. This is the strongest negative available and it")
        print("  closes the RL line more decisively than entry 46 did.")
    if d["A"]["crossings"] <= d["C"]["crossings"]:
        print(f"  Q5 holds: deeper retrieval crosses {d['C']['crossings']} vs "
              f"the refiner's {d['A']['crossings']}.")
    else:
        print(f"  Q5 MISSED: the refiner ({d['A']['crossings']}) beat deeper "
              f"retrieval ({d['C']['crossings']}). Re-check the wiring.")
    print("=" * 78)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--analyse", action="store_true")
    ap.add_argument("--n", type=int, default=None,
                    help="truncate the eligible set (smoke tests only)")
    ap.add_argument("--seed", type=int, default=SEED)
    a = ap.parse_args(argv)
    if a.run:
        _report(run(n=a.n, seed=a.seed))
    elif a.analyse:
        if not RESULTS.exists():
            raise SystemExit(f"{RESULTS.name} missing: run --run first")
        _report(json.loads(RESULTS.read_text(encoding="utf-8")))
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":                                  # pragma: no cover
    raise SystemExit(main())
