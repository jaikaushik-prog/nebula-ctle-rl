"""
experiments/exp_pool_size.py — **how big does the library actually have to be?**

    python -m nebula.experiments.exp_pool_size
    python -m nebula.experiments.exp_pool_size --report     # re-print from the artifact

**ZERO SIMULATIONS.** Pure re-analysis of `spec_pool` rows already on disk.

WHY THIS EXISTS
----------------
Every cost claim this project publishes — entry 32's **35.6 %**, entry 40's
**25 % fewer simulations** and **1 284 decks per compliant design against
1 960** — prices the *query* and charges **nothing** for the library the query
reads. `spec_pool.py` states the one-off cost: **~128 000 simulations**
(31 879 + 96 000 trials -> 74 526 de-duplicated designs).

Those simulations were spent running the baselines and budget-ladder
benchmarks, for other reasons; the library was free at the margin. That is true
and it is **not the question a judge asks.** The question is *"what would this
cost me to stand up on my topology?"*, and the answer is the break-even:

    measured: hybrid 642.1 decks/request, plain search 857.4 -> saving 215.3

    pool charged      300 sims  ->  break-even at    1.4 requests
    pool charged    1 000 sims  ->  break-even at    4.6 requests
    pool charged   10 000 sims  ->  break-even at   46.4 requests
    pool charged   74 526 sims  ->  break-even at  346.1 requests

**The claim is excellent at 1 000 and indefensible at 74 526.** Nothing in this
repository said which. This file measures it.

THE TRAP THIS FILE IS DESIGNED AROUND (PREDICTIONS.md entry 51)
----------------------------------------------------------------
The obvious experiment — subsample the pool to `N`, re-rank, take the top 5,
count how many requests still get a corner-feasible candidate — **cannot be run
at zero simulations**, and would produce a garbage curve if attempted.

Only **128 of 74 526** designs carry a corner-screen label
(`hybrid_topk_scan.json`). Subsampling to `N = 1000` retains a *specific*
labelled design with probability `1000/74526 = 1.3 %`. A declining
coverage-vs-`N` curve would therefore be measuring **label survival**, not
design quality — and it would read as a real finding.

**So this file measures MATCH QUALITY, which needs no labels at all.** `dev` is
the max-normalised deviation on the two requested axes and is the exact
criterion `exp_coverage.library_candidates` ranks on. It is computable for every
pool row for free.

THE INFERENCE CHAIN, WITH ITS WEAK LINK NAMED
-----------------------------------------------
    top-5 `dev` at pool size N matches top-5 `dev` at 74 526
      -> the proposer sees candidates of the same match quality
      -> **[WEAK LINK]** corner feasibility is a function of match quality
      -> coverage holds at N

**The weak link is false in general and this file does not pretend otherwise.**
`PROGRESS.md` §5h measured exactly that: no nominal channel separates the 1
accepted design from the 14 unscorable ones. So a flat curve is **necessary,
not sufficient**: below `N*` the proposer provably degrades; above `N*` it
provably sees equivalent-match candidates and coverage is *unresolved here*.

**`N*` IS A LOWER BOUND ON THE POOL SIZE AND MUST BE REPORTED IN THOSE WORDS.**
`Q4` measures the weak link directly on the 16 requests we have labels for.

WHAT IS NOT TOUCHED
--------------------
`exp_coverage.library_candidates`, `exp_hybrid`, the tolerances, `reward_v1.py`,
`V6_SPECS`, the box and the screen are **not modified**. The ranking criterion
is re-implemented here and **Q5 is the test that the re-implementation and the
shipped function agree exactly** — if it fails, nothing else in the artifact may
be read.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from nebula.rl import reward_v1 as R

HERE = Path(__file__).resolve().parent

#: The labelled scan. Supplies the request grid AND the corner-screen outcomes,
#: so the requests cannot drift from the run that produced the labels.
SCAN = HERE / "hybrid_topk_scan.json"

RESULTS = HERE / "pool_size_results.json"

#: Pool sizes swept, log-spaced. The last entry is the full pool and is the
#: control: at that size the "subsample" is the whole thing.
N_GRID: tuple[int, ...] = (50, 100, 300, 1000, 3000, 10_000, 30_000, 74_526)

#: Random subsamples per (request, N). 200 is enough for a stable median and
#: costs seconds; nothing here is a simulation.
N_SUBSAMPLES: int = 200

#: Depth the delivered tool reads the library to (`design.AUTO_K`), and the
#: depth entry 32 measured as the optimum.
K: int = 5

#: Q1/Q3's "same match quality" band, in units of tolerance. Registered in
#: entry 51 before any subsample was drawn.
FLAT_BAND: float = 0.05

#: Q2's "degraded" threshold, in units of tolerance. Also registered.
DEGRADED_BAND: float = 0.25

SEED: int = 20260901


def dev_all(pool_pk: np.ndarray, pool_fo: np.ndarray,
            peaking_db: float, f_peak_hz: float) -> np.ndarray:
    """`dev` for every pool row against one request.

    **This is `exp_coverage.library_candidates`' criterion, re-implemented.**
    It is not imported because that function also takes `k` and returns `u`
    vectors, and this file needs the full vector to subsample. Q5 asserts the
    two agree exactly; a mismatch invalidates the whole artifact.
    """
    tgt_oct = math.log2(float(f_peak_hz) / 2.5e9)
    return np.maximum(
        np.abs(pool_fo - tgt_oct) / R.TOL["S3_f_peak_match"],
        np.abs(pool_pk - float(peaking_db)) / R.TOL["S3_peaking_match"])


def _load_pool() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    from nebula.experiments import spec_pool as SP

    pool = SP.load_pool()
    pk = np.array([m["peaking_db"] for m in pool.meas], dtype=float)
    fo = np.array([m["f_peak_oct"] for m in pool.meas], dtype=float)
    u = np.asarray(pool.u, dtype=float)
    return pk, fo, u


def q5_control(pk: np.ndarray, fo: np.ndarray, u: np.ndarray,
               requests: list[dict]) -> dict:
    """**The sanity check that gates every other number in this file.**

    Re-ranks the FULL pool with `dev_all` and compares the top-`K` `u` vectors
    against `exp_coverage.library_candidates(k=K)` — the shipped function the
    delivered tool calls. Registered as Q5 at confidence 0.95.
    """
    from nebula.experiments import exp_coverage as C

    worst = 0.0
    n_ok = 0
    for req in requests:
        mine_idx = np.argsort(dev_all(pk, fo, req["peaking_db"],
                                      req["f_peak_hz"]), kind="stable")[:K]
        mine = u[mine_idx]
        theirs = C.library_candidates(float(req["f_peak_hz"]),
                                      float(req["peaking_db"]), k=K)
        if len(theirs) != len(mine):
            worst = float("inf")
            continue
        d = max(float(np.abs(np.asarray(a) - b).max())
                for a, b in zip(theirs, mine))
        worst = max(worst, d)
        n_ok += int(d < 1e-12)
    return {"n_requests_exact": n_ok, "n_requests": len(requests),
            "worst_abs_diff": worst, "passed": n_ok == len(requests)}


def sweep(pk: np.ndarray, fo: np.ndarray, requests: list[dict],
          n_grid: Sequence[int] = N_GRID,
          n_subsamples: int = N_SUBSAMPLES, seed: int = SEED) -> list[dict]:
    """Top-`K` `dev` against pool size, per request.

    The full-pool row is computed once and exactly (no subsampling); every
    smaller `N` is `n_subsamples` random draws and reports the median across
    draws of the median of the top-`K` `dev`.
    """
    n_pool = pk.size
    rng = np.random.default_rng(seed)
    out: list[dict] = []
    for req in requests:
        dv = dev_all(pk, fo, req["peaking_db"], req["f_peak_hz"])
        full_top = np.sort(dv)[:K]
        full_med = float(np.median(full_top))
        rows = []
        for n in n_grid:
            if n >= n_pool:
                rows.append({"n": int(n_pool), "median_dev": full_med,
                             "p90_dev": full_med, "is_full_pool": True,
                             "excess": 0.0})
                continue
            meds = np.empty(n_subsamples, dtype=float)
            for s in range(n_subsamples):
                pick = rng.choice(n_pool, size=int(n), replace=False)
                meds[s] = np.median(np.sort(dv[pick])[:K])
            out_med = float(np.median(meds))
            rows.append({"n": int(n), "median_dev": out_med,
                         "p90_dev": float(np.quantile(meds, 0.90)),
                         "is_full_pool": False,
                         "excess": out_med - full_med})
        out.append({"index": req["index"], "peaking_db": req["peaking_db"],
                    "f_peak_hz": req["f_peak_hz"],
                    "accepted_rank": req["accepted_rank"],
                    "full_pool_median_dev": full_med, "by_n": rows})
    return out


def analyse(per_request: list[dict]) -> dict:
    """Score Q1-Q4 from the sweep. **The thresholds are entry 51's, not tuned.**"""
    n_req = len(per_request)
    by_n: dict[int, dict] = {}
    for n in N_GRID:
        n_flat = sum(1 for r in per_request
                     for row in r["by_n"]
                     if row["n"] == n and row["excess"] <= FLAT_BAND)
        n_degraded = sum(1 for r in per_request
                         for row in r["by_n"]
                         if row["n"] == n and row["excess"] > DEGRADED_BAND)
        by_n[int(n)] = {"n_flat": n_flat, "n_degraded": n_degraded,
                        "n_requests": n_req}

    # Q3: the smallest N on the grid that is flat on >= 14 of 16.
    n_star: Optional[int] = None
    for n in N_GRID:
        if by_n[int(n)]["n_flat"] >= 14:
            n_star = int(n)
            break

    # Q4: do the SOLVED requests have lower full-pool dev than the unsolved?
    solved = [r["full_pool_median_dev"] for r in per_request
              if r["accepted_rank"] is not None]
    unsolved = [r["full_pool_median_dev"] for r in per_request
                if r["accepted_rank"] is None]
    p_mw = _mannwhitney_p(np.array(solved), np.array(unsolved))

    saving = 857.375 - 642.0625        # entry 40's measured decks per request
    return {
        "by_n": by_n,
        "n_star": n_star,
        "q1_flat_at_3000": by_n[3000]["n_flat"],
        "q2_degraded_at_50": by_n[50]["n_degraded"],
        "q4": {"n_solved": len(solved), "n_unsolved": len(unsolved),
               "median_dev_solved": float(np.median(solved)) if solved else None,
               "median_dev_unsolved": (float(np.median(unsolved))
                                       if unsolved else None),
               "mannwhitney_p": p_mw},
        "break_even_requests": (None if n_star is None
                                else round(n_star / saving, 2)),
        "decks_saved_per_request": saving,
    }


def _mannwhitney_p(a: np.ndarray, b: np.ndarray) -> Optional[float]:
    """Two-sided Mann-Whitney U, normal approximation with tie correction.

    Written out rather than imported: `scipy` is not a dependency of this
    project and adding one for a single p-value would be a new install on
    every machine that clones the repo.
    """
    if a.size == 0 or b.size == 0:
        return None
    both = np.concatenate([a, b])
    order = np.argsort(both, kind="stable")
    ranks = np.empty(both.size, dtype=float)
    ranks[order] = np.arange(1, both.size + 1, dtype=float)
    # average ranks within ties
    srt = both[order]
    i = 0
    while i < srt.size:
        j = i
        while j + 1 < srt.size and srt[j + 1] == srt[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = ranks[order[i:j + 1]].mean()
        i = j + 1
    n1, n2 = a.size, b.size
    u1 = ranks[:n1].sum() - n1 * (n1 + 1) / 2.0
    mu = n1 * n2 / 2.0
    _, counts = np.unique(both, return_counts=True)
    tie = float((counts ** 3 - counts).sum())
    n = n1 + n2
    var = n1 * n2 / 12.0 * ((n + 1) - tie / (n * (n - 1)))
    if var <= 0:
        return 1.0
    z = (abs(u1 - mu) - 0.5) / math.sqrt(var)
    return float(math.erfc(z / math.sqrt(2.0)))


def _requests_from_scan() -> list[dict]:
    if not SCAN.exists():
        raise FileNotFoundError(
            f"{SCAN} missing. It supplies both the request grid and the "
            f"corner-screen labels; this experiment does not invent either.")
    d = json.loads(SCAN.read_text(encoding="utf-8"))
    return [{"index": r["index"], "peaking_db": float(r["peaking_db"]),
             "f_peak_hz": float(r["f_peak_hz"]),
             "accepted_rank": r["accepted_rank"]} for r in d["requests"]]


def _header() -> None:
    print("=" * 74)
    print("POOL SIZE vs MATCH QUALITY  --  ZERO SIMULATIONS")
    print("=" * 74)
    print("ASSUMPTIONS, printed every run (CLAUDEwa.md rule):")
    print("  1. `dev` is the SHIPPED ranking criterion, re-implemented here.")
    print("     Q5 asserts it reproduces exp_coverage.library_candidates")
    print("     EXACTLY. If Q5 fails, no other number here may be read.")
    print("  2. This measures MATCH QUALITY, not corner feasibility. Only")
    print("     128 of 74 526 designs carry a corner label, so a direct")
    print("     coverage-vs-N curve would measure LABEL SURVIVAL instead.")
    print("  3. N* is therefore a LOWER BOUND on the pool size: below it the")
    print("     proposer provably degrades; above it coverage is UNRESOLVED.")
    print("  4. Pool rows are NOMINAL (tt/1.00/27C). PROGRESS.md 5h measured")
    print("     that nominal channels do not separate corner outcomes. Q4")
    print("     tests that weak link directly on the 16 labelled requests.")
    print("=" * 74)


def report(d: dict) -> None:
    a = d["analysis"]
    print()
    print(f"pool {d['n_pool']:,} designs   k={d['k']}   "
          f"{d['n_subsamples']} subsamples per (request, N)")
    print()
    q5 = d["q5_control"]
    verdict = "PASS" if q5["passed"] else "*** FAIL ***"
    print(f"Q5 control  reproduces shipped ranking on "
          f"{q5['n_requests_exact']} of {q5['n_requests']} requests   {verdict}")
    if not q5["passed"]:
        print("    STOP. The re-implementation is not the shipped criterion.")
        return
    print()
    print(f"    {'N':>8}  {'flat (<=0.05)':>14}  {'degraded (>0.25)':>17}")
    for n in N_GRID:
        r = a["by_n"][int(n)] if int(n) in a["by_n"] else a["by_n"][str(n)]
        print(f"    {n:>8,}  {r['n_flat']:>10} / {r['n_requests']:<2}"
              f"  {r['n_degraded']:>13} / {r['n_requests']:<2}")
    print()
    print(f"  Q1  flat at N=3000 on {a['q1_flat_at_3000']} of 16"
          f"   (registered: >= 14)")
    print(f"  Q2  degraded at N=50 on {a['q2_degraded_at_50']} of 16"
          f"   (registered: >= 8)")
    print(f"  Q3  N* = {a['n_star']}"
          f"   (registered: <= 1000)")
    q4 = a["q4"]
    print(f"  Q4  solved med dev {q4['median_dev_solved']:.4f} vs unsolved "
          f"{q4['median_dev_unsolved']:.4f}, p = {q4['mannwhitney_p']:.4f}"
          f"   (registered: p >= 0.05)")
    print()
    if a["n_star"] is not None:
        print(f"  BREAK-EVEN at N* = {a['n_star']:,} designs: "
              f"{a['break_even_requests']} spec requests")
    print(f"  BREAK-EVEN at the full pool (74 526): "
          f"{74526 / a['decks_saved_per_request']:.1f} spec requests")
    print()
    print("  N* IS A LOWER BOUND. Above it this experiment does not resolve")
    print("  coverage; it resolves that the proposer sees candidates of")
    print("  equivalent match quality. Report it in those words.")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m nebula.experiments.exp_pool_size",
                                 description=__doc__)
    ap.add_argument("--report", action="store_true",
                    help="re-print from the committed artifact, no computation")
    ap.add_argument("--subsamples", type=int, default=N_SUBSAMPLES)
    args = ap.parse_args(argv)

    if args.report:
        if not RESULTS.exists():
            print(f"error: {RESULTS} missing; run without --report first",
                  file=sys.stderr)
            return 2
        report(json.loads(RESULTS.read_text(encoding="utf-8")))
        return 0

    _header()
    t0 = time.time()
    requests = _requests_from_scan()
    pk, fo, u = _load_pool()
    print(f"pool loaded: {pk.size:,} designs, {len(requests)} requests")

    q5 = q5_control(pk, fo, u, requests)
    if not q5["passed"]:
        print(f"Q5 CONTROL FAILED: worst abs diff {q5['worst_abs_diff']}",
              file=sys.stderr)
        print("The re-implemented criterion is not the shipped one. "
              "Refusing to write an artifact.", file=sys.stderr)
        return 1

    per_request = sweep(pk, fo, requests, n_subsamples=int(args.subsamples))
    out = {
        "task": "pool size vs match quality (PREDICTIONS.md entry 51)",
        "is_zero_simulation": True,
        "n_pool": int(pk.size),
        "k": K,
        "n_subsamples": int(args.subsamples),
        "n_grid": list(N_GRID),
        "flat_band": FLAT_BAND,
        "degraded_band": DEGRADED_BAND,
        "seed": SEED,
        "source_scan": SCAN.name,
        "q5_control": q5,
        "per_request": per_request,
        "analysis": analyse(per_request),
        "wall_clock_s": time.time() - t0,
    }
    RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    report(out)
    print(f"\nwrote {RESULTS.name}  ({out['wall_clock_s']:.1f} s, "
          f"0 simulations)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
