"""
experiments/exp_rerank_cost.py — **entry 49: does a learned ranker cut the
SIMULATION BILL? Zero simulations, because the counterfactual is arithmetic.**

    python -m nebula.experiments.exp_rerank_cost --run

WHAT IS BEING ASKED, AND WHY IT IS NOT ENTRY 44 AGAIN
------------------------------------------------------
Entry 44 asked whether corner-robustness is *predictable* (yes -- pooled
out-of-fold AUC **0.891**) and whether a ranker reaches **rank <= 2** (no). It
never computed the quantity the competition actually scores: **how many
candidates you must screen before one passes.**

`hybrid_topk_scan.json` holds 16 requests x 8 candidates, **every one already
screened and labelled**. So reordering them and recounting "how far down did we
have to go" is **pure arithmetic over labels already paid for**. Nothing is
re-simulated; the counterfactual is exact rather than estimated.

THE CEILING, WHICH IS WHY THE HEADLINE MUST BE STATED CAREFULLY
----------------------------------------------------------------
    accepted ranks  [1, 2, 2, 2, 3, 5]      unaccepted 10 of 16
    k=5 today:  65 candidates screened for 6 of 16 coverage

**Reordering at fixed k is worth at most 13.8 %**, because the 10 requests with
no feasible candidate pay the full `k` and no ordering can help them. A larger
saving requires **shrinking `k`**, which is only honest if acceptances actually
land near the top -- and **four of the six are already at rank <= 2**, so the
whole experiment turns on the two at ranks **3 and 5**.

LEAVE-ONE-REQUEST-OUT, OR IT IS LEAKAGE
-----------------------------------------
The labelled pool covers the same 16 requests the metric is measured on, so a
model that has seen request `i` cannot be allowed to rank request `i`'s
candidates. `exp_rerank.features` / `make_model` are reused unchanged (rule 9);
only the fold loop and the cost arithmetic are new.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from nebula.experiments.exp_rerank import (
    SEED, auc, features, load_screened, make_model, scan_candidates,
)

HERE = Path(__file__).resolve().parent
SCAN = HERE / "hybrid_topk_scan.json"
RESULTS = HERE / "rerank_cost_results.json"

#: What ships today (entry 32's measured optimum).
K_DEPLOYED: int = 5

#: The shrunken depth entry 49 Q3 asks whether the ranker unlocks.
K_TARGET: int = 2


def _group(peaking_db: float, f_peak_hz: float) -> str:
    """The request identity used for the folds. Same form as `exp_rerank`."""
    return f"{peaking_db:.3f}@{f_peak_hz:.0f}"


def deployed_cost(labels: Sequence[bool], k: int) -> int:
    """Candidates screened before stopping. **The competition's own metric.**

    A deployed proposer screens candidates in order and **stops at the first
    one that passes** -- so it pays the rank of the acceptance, or the full `k`
    when nothing in the first `k` passes. This is exactly `exp_hybrid`'s
    short-circuit, counted rather than re-implemented.
    """
    for i, ok in enumerate(labels[:k], start=1):
        if ok:
            return i
    return k


def run(seed: int = SEED) -> dict:
    t0 = time.time()
    pool = load_screened()["rows"]
    cands = scan_candidates(SCAN)
    if not cands:
        raise SystemExit(f"{SCAN.name} has no scored candidates")

    by_req: dict[int, list] = {}
    for c in cands:
        by_req.setdefault(c["index"], []).append(c)
    for cs in by_req.values():
        cs.sort(key=lambda c: c["rank"])        # the order that ships today

    Xp = features([r["u"] for r in pool],
                  np.array([r["target_peaking_db"] for r in pool]),
                  np.array([r["target_f_peak_hz"] for r in pool]))
    yp = np.array([r["feasible"] for r in pool], dtype=int)
    gp = np.array([_group(r["target_peaking_db"], r["target_f_peak_hz"])
                   for r in pool])

    rows, oof_s, oof_y = [], [], []
    for idx in sorted(by_req):
        cs = by_req[idx]
        g = _group(cs[0]["target_peaking_db"], cs[0]["target_f_peak_hz"])
        tr = gp != g                            # LEAVE THIS REQUEST OUT
        if yp[tr].min() == yp[tr].max():        # pragma: no cover
            continue
        m = make_model(seed)
        m.fit(Xp[tr], yp[tr])
        Xc = features([c["u"] for c in cs],
                      np.array([c["target_peaking_db"] for c in cs]),
                      np.array([c["target_f_peak_hz"] for c in cs]))
        s = m.predict_proba(Xc)[:, 1]
        order = np.argsort(-s)

        before = [bool(c["feasible"]) for c in cs]
        after = [bool(cs[i]["feasible"]) for i in order]
        pos_b = [i + 1 for i, f in enumerate(before) if f]
        pos_a = [i + 1 for i, f in enumerate(after) if f]
        rows.append({
            "index": idx, "n_candidates": len(cs),
            "n_feasible": sum(before),
            "best_before": min(pos_b) if pos_b else None,
            "best_after": min(pos_a) if pos_a else None,
            "cost_before_k5": deployed_cost(before, K_DEPLOYED),
            "cost_after_k5": deployed_cost(after, K_DEPLOYED),
            "cost_before_k2": deployed_cost(before, K_TARGET),
            "cost_after_k2": deployed_cost(after, K_TARGET),
            "solved_before_k5": any(before[:K_DEPLOYED]),
            "solved_after_k5": any(after[:K_DEPLOYED]),
            "solved_after_k2": any(after[:K_TARGET]),
        })
        oof_s.extend(s.tolist())
        oof_y.extend([int(c["feasible"]) for c in cs])

    out = _summarise(rows, oof_y, oof_s)
    out.update({"task": "entry 49: does reranking cut the simulation bill?",
                "simulations_run": 0, "seed": seed,
                "n_pool": len(pool), "n_pool_feasible": int(yp.sum()),
                "k_deployed": K_DEPLOYED, "k_target": K_TARGET,
                "wall_s": time.time() - t0, "rows": rows})
    RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def _summarise(rows, oof_y, oof_s) -> dict:
    n = len(rows)
    cb = sum(r["cost_before_k5"] for r in rows)
    ca = sum(r["cost_after_k5"] for r in rows)
    ca2 = sum(r["cost_after_k2"] for r in rows)
    cov_b = sum(1 for r in rows if r["solved_before_k5"])
    cov_a = sum(1 for r in rows if r["solved_after_k5"])
    cov_a2 = sum(1 for r in rows if r["solved_after_k2"])

    withf = [r for r in rows if r["n_feasible"]]
    nof = [r for r in rows if not r["n_feasible"]]
    easy = [r for r in withf if r["best_before"] is not None
            and r["best_before"] <= K_TARGET]
    hard = [r for r in withf if r["best_before"] is not None
            and r["best_before"] > K_TARGET]

    # The perfect-ranker ceiling, recomputed here so the headline can never be
    # quoted without it.
    ceiling = sum(1 if r["n_feasible"] else K_DEPLOYED for r in rows)

    return {
        "n_requests": n,
        "Q1_auc": {"pooled_oof_auc": auc(np.array(oof_y), np.array(oof_s)),
                   "n": len(oof_y), "n_pos": int(sum(oof_y))},
        "Q2_cost": {
            "before_k5": cb, "after_k5": ca,
            "saving_pct": 100.0 * (cb - ca) / cb if cb else 0.0,
            "coverage_before": cov_b, "coverage_after": cov_a,
            "ceiling_k5": ceiling,
            "ceiling_saving_pct": 100.0 * (cb - ceiling) / cb if cb else 0.0,
            "hit": ca < cb and cov_a >= cov_b},
        "Q3_shrink_k": {
            "after_k2_cost": ca2, "after_k2_coverage": cov_a2,
            "n_hard_moved": sum(1 for r in hard
                                if r["best_after"] is not None
                                and r["best_after"] <= K_TARGET),
            "n_hard": len(hard),
            "saving_pct_vs_today": 100.0 * (cb - ca2) / cb if cb else 0.0,
            "hit": cov_a2 >= cov_b},
        "Q4_no_scramble": {
            "n_easy": len(easy),
            "n_easy_worsened": sum(1 for r in easy
                                   if r["best_after"] is not None
                                   and r["best_after"] > r["best_before"]),
            "hit": all(r["best_after"] is not None
                       and r["best_after"] <= r["best_before"] for r in easy)},
        "Q5_sanity": {
            "n_no_feasible": len(nof),
            "all_cost_k_before_and_after": all(
                r["cost_before_k5"] == K_DEPLOYED
                and r["cost_after_k5"] == K_DEPLOYED for r in nof),
            "hit": all(r["cost_before_k5"] == K_DEPLOYED
                       and r["cost_after_k5"] == K_DEPLOYED for r in nof)},
    }


def _report(d: dict) -> None:
    q2, q3, q4, q5 = (d["Q2_cost"], d["Q3_shrink_k"], d["Q4_no_scramble"],
                      d["Q5_sanity"])
    print()
    print("=" * 78)
    print(f"ENTRY 49 — RERANKING THE LIBRARY, {d['n_requests']} requests, "
          f"{d['simulations_run']} simulations")
    print("=" * 78)
    a = d["Q1_auc"]
    print(f"  Q1 AUC     : pooled out-of-fold {a['pooled_oof_auc']:.4f} "
          f"on {a['n']} candidates ({a['n_pos']} feasible)   "
          f"{'HIT ' if (a['pooled_oof_auc'] or 0) >= 0.70 else 'MISS'}")
    print()
    print(f"  candidates screened, k={d['k_deployed']}:")
    print(f"    today (search_score order)  {q2['before_k5']:>3}   "
          f"coverage {q2['coverage_before']}/{d['n_requests']}")
    print(f"    reranked                    {q2['after_k5']:>3}   "
          f"coverage {q2['coverage_after']}/{d['n_requests']}"
          f"   {q2['saving_pct']:+.1f}%")
    print(f"    perfect-ranker CEILING      {q2['ceiling_k5']:>3}   "
          f"({q2['ceiling_saving_pct']:.1f}% -- the most reordering can buy)")
    print(f"  Q2 PRIMARY : {'HIT ' if q2['hit'] else 'MISS'}")
    print()
    print(f"  Q3 shrink k to {d['k_target']}: {q3['after_k2_cost']} candidates, "
          f"coverage {q3['after_k2_coverage']}/{d['n_requests']}"
          f"   ({q3['saving_pct_vs_today']:+.1f}% vs today)")
    print(f"               hard cases moved to rank<={d['k_target']}: "
          f"{q3['n_hard_moved']}/{q3['n_hard']}   "
          f"{'HIT ' if q3['hit'] else 'MISS'}")
    print(f"  Q4 scramble: {q4['n_easy_worsened']}/{q4['n_easy']} easy "
          f"acceptances worsened   {'HIT ' if q4['hit'] else 'MISS'}")
    print(f"  Q5 sanity  : {q5['n_no_feasible']} no-feasible requests cost k "
          f"both ways   {'HIT ' if q5['hit'] else 'MISS'}")
    print()
    if not q5["hit"]:
        print("  Q5 MISSED -- the metric is computed wrong. Fix it and rerun;")
        print("  read nothing else.")
    elif q3["hit"]:
        print(f"  Q3 HIT: k can drop to {d['k_target']} at unchanged coverage --")
        print(f"  {q3['saving_pct_vs_today']:.1f}% fewer simulations. RE-CHECK against")
        print("  the raw labels before writing this anywhere.")
    elif q2["hit"]:
        print("  Q2 HIT: reranking cuts the bill at matched coverage. Report it")
        print(f"  WITH the {q2['ceiling_saving_pct']:.1f}% ceiling, so nobody reads it as the 60%.")
    else:
        print("  Q2 MISSED: the library's own search_score ordering is already")
        print("  close to optimal on this set. The ranker line closes -- with a")
        print("  NUMBER rather than an AUC, which entry 44 could not manage.")
    print("=" * 78)


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
