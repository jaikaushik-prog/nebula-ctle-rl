"""
experiments/exp_invert_screen.py — **entry 58: does an on-target-by-
construction proposal survive the corner screen?**

    python -m nebula.experiments.exp_invert_screen --run
    python -m nebula.experiments.exp_invert_screen --report

WHAT THIS MEASURES
-------------------
`invert_response` solves `(rs, cs, rl)` in closed form so that
`predict_response` lands exactly on a requested `(peaking, f_peak)`. This file
asks the only question that matters about that: **do the resulting designs pass
the live 4-corner screen**, against the library proposer's measured **6 of 16**
(entry 32 at k=5, entry 40 delivered).

Scored through `evaluate_at_points` on `AdaptiveScreen(EDGE4_MANDATED).points`
with `V6_SPECS` -- the same call, screen and spec set entry 32 used -- so `A` is
on the same axis as the number it is compared to. **320 decks.**

THE RANKING IS THE ANALYTIC PROXY, ON PURPOSE
-----------------------------------------------
Candidates are ranked by `i_bias * (1 + gm*rs/2) / gm`, the headroom the
degeneration algebra implies. Entry 37's measured swing surrogate is **Phase
2**, and mixing it in here would make the two impossible to attribute. If the
proxy is the weak link, Phase 2 is the experiment that says so.

WHAT IT REFUSES TO PRODUCE
---------------------------
**No coverage number** (entry 58 Q5). The screen is 4 corners; compliance is
45, and entry 53 measured that the screen's filter quality degrades with depth
(83 % -> 50 %). Accepted candidates must be verified separately before any
coverage claim, and this file writes no verification.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "topk_scan_analytic.json"

#: Entry 32's measured optimum and `design.AUTO_K`. **Not swept here.**
K: int = 5

#: The (w, l, i_bias, rs) grid the feasibility map used. Registered in entry 58;
#: a later run on a finer grid is a different experiment, not this one.
N_W, N_L, N_I, N_RS = 5, 5, 8, 40

#: Box edges the candidates must satisfy to be expressible as a `u` vector.
BOX = {"rs": (50.0, 1000.0), "cs": (1e-13, 1e-11), "rl": (50.0, 800.0)}


def _in_box(sol) -> bool:
    return (BOX["rs"][0] <= sol.rs <= BOX["rs"][1]
            and BOX["cs"][0] <= sol.cs <= BOX["cs"][1]
            and BOX["rl"][0] <= sol.rl <= BOX["rl"][1])


def analytic_candidates(f_peak_hz: float, peaking_db: float,
                        k: int = K) -> list[list[float]]:
    """The top `k` analytic solutions for one request, as `u` vectors.

    Ranked by the analytic headroom proxy. Every candidate is on-target in the
    model by construction, so the ranking spends its only degree of freedom on
    the constraint that actually binds.
    """
    from nebula.experiments.invert_response import invert
    from nebula.experiments.prescreen import predict_gm
    from nebula.experiments.s9_yield import PROMOTION_LOADS
    from nebula.rl.contract import u_from_params

    cl = sorted(PROMOTION_LOADS)[len(PROMOTION_LOADS) // 2]
    ws = np.geomspace(2e-5, 1e-4, N_W)
    ls = np.geomspace(1.5e-7, 1e-6, N_L)
    ibs = np.geomspace(0.5e-3, 8e-3, N_I)
    rss = np.geomspace(BOX["rs"][0], BOX["rs"][1], N_RS)

    found: list[tuple[float, dict]] = []
    for w in ws:
        for l in ls:
            for ib in ibs:
                bias = {"w_in": float(w), "l_in": float(l), "nf_in": 4.0,
                        "i_bias": float(ib), "vcm_in": 1.35}
                gm, gmbs = predict_gm(bias)
                if gm <= 0.0:
                    continue
                for rs in rss:
                    sol = invert(float(peaking_db), float(f_peak_hz), bias, cl,
                                 rs=float(rs))
                    if sol is None or not _in_box(sol):
                        continue
                    proxy = float(ib) * (1.0 + gm * sol.rs / 2.0) / gm
                    found.append((proxy, {**bias, "rs": sol.rs, "cs": sol.cs,
                                          "rl": sol.rl}))
    found.sort(key=lambda t: -t[0])

    out: list[list[float]] = []
    for _, params in found:
        try:
            u = u_from_params(params)
        except Exception:                                       # noqa: BLE001
            continue
        uu = [float(x) for x in np.asarray(u).ravel()]
        if any(not (0.0 - 1e-9 <= x <= 1.0 + 1e-9) for x in uu):
            continue
        out.append([min(1.0, max(0.0, x)) for x in uu])
        if len(out) >= int(k):
            break
    return out


def library_rank1(f_peak_hz: float, peaking_db: float) -> Optional[list[float]]:
    """The library's rank-1 candidate for the same request, for entry 58 Q4."""
    from nebula.experiments.exp_hybrid import library_candidates_k

    try:
        cands = list(library_candidates_k(float(f_peak_hz), float(peaking_db), 1))
    except Exception:                                           # noqa: BLE001
        return None
    return [float(x) for x in np.asarray(cands[0]).ravel()] if cands else None


def run(k: int = K) -> dict:
    from nebula.experiments import exp_coverage as C
    from nebula.experiments.adaptive_screen import EDGE4_MANDATED, AdaptiveScreen
    from nebula.experiments.exp_hybrid import evaluate_at_points
    from nebula.experiments.runlock import hold, stamp
    from nebula.rl import reward_v1 as R

    screen = AdaptiveScreen(EDGE4_MANDATED)
    requests = [(pk, f) for pk in C.PEAKING_REQUESTS for f in C.FREQ_REQUESTS]

    with hold("invert_screen", meta={"k": int(k)}):
        t0 = time.time()
        rows: list[dict] = []
        n_decks = 0
        for i, (pk, f) in enumerate(requests):
            cands = analytic_candidates(float(f), float(pk), int(k))
            lib1 = library_rank1(float(f), float(pk))
            cand_rows: list[dict] = []
            accepted_rank: Optional[int] = None
            for rank, u in enumerate(cands, start=1):
                try:
                    ev = evaluate_at_points(
                        np.asarray(u, dtype=float), screen.points,
                        target_f_peak_hz=float(f),
                        target_peaking_db=float(pk), specs=R.V6_SPECS)
                except Exception as exc:                        # noqa: BLE001
                    cand_rows.append({"rank": rank, "u": u, "ok": False,
                                      "error": repr(exc)})
                    continue
                n_decks += len(screen.points)
                feasible = bool(getattr(ev, "feasible", False))
                dist = (float(np.max(np.abs(np.asarray(u) - np.asarray(lib1))))
                        if lib1 is not None else None)
                cand_rows.append({
                    "rank": rank, "u": u, "ok": True, "feasible": feasible,
                    "reward": float(getattr(ev, "reward", float("nan"))),
                    "reason": getattr(ev, "reason", None),
                    "worst_spec": getattr(ev, "worst_spec", None),
                    "linf_to_library_rank1": dist})
                if feasible and accepted_rank is None:
                    accepted_rank = rank
                    break
            rows.append({"index": i, "peaking_db": float(pk),
                         "f_peak_hz": float(f),
                         "n_candidates": len(cands),
                         "accepted_rank": accepted_rank,
                         "candidates": cand_rows})
            print(f"[{i + 1}/16] {pk:5.1f} dB @ {f / 1e9:.3f} GHz  "
                  f"cands {len(cands)}  accepted_rank {accepted_rank}",
                  flush=True)

        out = {"task": "entry 58: analytic inversion as a proposer",
               "k": int(k), "n_decks": n_decks, **stamp(),
               "wall_clock_s": time.time() - t0, "requests": rows}
        out["analysis"] = analyse(out)
        RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
        return out


def analyse(d: dict) -> dict:
    """Score entry 58's questions. Thresholds are the registered ones."""
    rows = d["requests"]
    a = sum(1 for r in rows if r["accepted_rank"] is not None)
    rejected = [c for r in rows for c in r["candidates"]
                if c.get("ok") and not c.get("feasible")]
    n_rej = len(rejected)

    def _frac(needle: str) -> float:
        if not n_rej:
            return 0.0
        return sum(1 for c in rejected
                   if needle in str(c.get("reason") or "")) / n_rej

    swing = _frac("exceeds the linear limit")
    shape = sum(1 for c in rejected
                if str(c.get("worst_spec") or "").startswith("S3_")
                and "match" in str(c.get("worst_spec"))) / n_rej if n_rej else 0.0
    dists = [c["linf_to_library_rank1"] for r in rows for c in r["candidates"]
             if c.get("linf_to_library_rank1") is not None]
    return {
        "A": a, "library_baseline": 6, "n_rejected": n_rej,
        "frac_swing": swing, "frac_shape_match": shape,
        "min_linf_to_library": (min(dists) if dists else None),
        "Q1_at_least_library": a >= 6,
        "Q2_swing_dominates": swing > 0.5,
        "Q3_shape_survives": shape < 0.25,
        "Q4_not_the_library": (min(dists) > 0.05) if dists else None,
    }


def _report(d: dict) -> None:
    a = d["analysis"]
    print()
    print("ENTRY 58 -- analytic inversion as a proposer")
    print(f"  k={d['k']}  decks {d['n_decks']}  "
          f"wall {d.get('wall_clock_s', 0.0):.1f} s")
    print()
    print("  req  target                 cands  accepted_rank")
    for r in d["requests"]:
        print(f"  {r['index']:3}  {r['peaking_db']:5.1f} dB @ "
              f"{r['f_peak_hz'] / 1e9:.3f} GHz  {r['n_candidates']:5}  "
              f"{r['accepted_rank']}")
    print()
    print(f"  A = {a['A']} of 16   (library baseline {a['library_baseline']})")
    print(f"  rejections: {a['n_rejected']}   swing {a['frac_swing']:.1%}   "
          f"shape-match {a['frac_shape_match']:.1%}")
    print(f"  min L-inf to library rank 1: {a['min_linf_to_library']}")
    for q in ("Q1_at_least_library", "Q2_swing_dominates", "Q3_shape_survives",
              "Q4_not_the_library"):
        print(f"    {q:22} {a[q]}")
    print()
    print("  NO COVERAGE NUMBER (Q5): 4 corners, not 45.")
    print()


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("-k", type=int, default=K)
    args = ap.parse_args(argv)
    if args.run:
        _report(run(k=args.k))
        return 0
    if args.report:
        if not RESULTS.exists():
            print(f"no artifact at {RESULTS}")
            return 1
        _report(json.loads(RESULTS.read_text(encoding="utf-8")))
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
