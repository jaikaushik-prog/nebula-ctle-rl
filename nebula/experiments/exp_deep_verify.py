"""
experiments/exp_deep_verify.py — **stage 2 of entry 52: do the DEEP retrieved
proposals hold up at the 45 mandated corners?** (`PREDICTIONS.md` entry 53)

    python -m nebula.experiments.exp_deep_verify
    python -m nebula.experiments.exp_deep_verify --report

WHY THIS EXISTS
----------------
Entry 52 read the library to rank 40 and found `A` goes **6 -> 10 of 16**: four
requests get a corner-screen-feasible starting design that the k=8 scan never
saw, at ranks 17, 17, 19 and 26. **Screen acceptance is not compliance.** The
screen is 4 corners; the competition mandates 45. This file closes that gap by
running the same verifier `exp_coverage` uses.

THE COVERAGE UPSIDE IS BOUNDED AT +2, AND THE BOUND WAS COMPUTED FIRST
------------------------------------------------------------------------
Cross-referencing the four newly accepted requests against `hybrid_results.json`
(entry 40) **before** running anything:

    request  3   entry 40 search got 11/45, worst -0.5559   <- a real spec failure
    request  5   entry 40 search got 44/45, worst +14.5035  <- missing corner is an
                                                               UNMEASURABLE eye (G120)
    request  6   entry 40 search got 45/45                  <- already covered
    request 10   entry 40 search got 45/45                  <- already covered

So only requests **3** and **5** can move the headline from 8 of 16. Requests 6
and 10 are the **control**: they are already solvable, so a proposal that passes
the 4-corner screen and then fails 45 corners on one of them would indict the
screen rather than the request (entry 53 Q3).

WHAT IS COUNTED, AND WHAT IS NOT
----------------------------------
`verify_request` runs the full **135 points** and splits the mandated 45 out of
them, so this costs **135 decks per design, not 45**. Both columns are reported:
the 45 is **compliance**, the 135 is **robustness characterisation**, and they
are never merged (`exp_coverage.verify_request`'s own docstring, D8).

**The verification decks are NOT added to any amortisation number.** Entry 40
keeps three cost lines — proposal, search, verification — precisely so this one
cannot be quietly folded into a saving claim.

NOTHING IS TUNED
-----------------
The candidates are read from `hybrid_topk_scan_k40.json` exactly as scanned;
`verify_request`, the tolerances, the screen, `V6_SPECS`, the box and
`reward_v1.py` are untouched.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional, Sequence

HERE = Path(__file__).resolve().parent

SCAN_K40 = HERE / "hybrid_topk_scan_k40.json"
SCAN_K8 = HERE / "hybrid_topk_scan.json"
HYBRID = HERE / "hybrid_results.json"
RESULTS = HERE / "deep_verify_results.json"

#: Ranks at or below this were already scanned by entry 32, so an acceptance
#: there is not "new". Entry 52's `accepted_at_k[7]` is the 6 it starts from.
SHALLOW_K: int = 8


def newly_accepted(scan: dict, shallow_k: int = SHALLOW_K) -> list[dict]:
    """Requests whose FIRST feasible candidate sits below `shallow_k`.

    Returns the candidate itself, so the verified design is provably the one
    the scan accepted rather than a re-derived lookup (G124: `design_id` does
    not join across artifact boundaries; the `u` vector is the identity here).
    """
    out = []
    for r in scan["requests"]:
        first = next((c for c in sorted(r["candidates"], key=lambda c: c["rank"])
                      if c["feasible"]), None)
        if first is not None and first["rank"] > shallow_k:
            out.append({"index": r["index"], "peaking_db": r["peaking_db"],
                        "f_peak_hz": r["f_peak_hz"], "rank": first["rank"],
                        "u": first["u"], "design_id": first["design_id"],
                        "screen_reward": first["reward"]})
    return out


def entry40_baseline() -> dict:
    """Per-request 45-corner outcome from entry 40, for the +2 bound."""
    h = json.loads(HYBRID.read_text(encoding="utf-8"))
    return {r["index"]: {"n_pvt45_pass": r["request"]["n_pvt45_pass"],
                         "n_pvt45_total": r["request"]["n_pvt45_total"],
                         "pvt45_worst": r["request"]["pvt45_worst"],
                         "which_path": r["which_path"]}
            for r in h["requests"]}


def verify_one(cand: dict) -> dict:
    """One design, 135 points, through `exp_coverage`'s own verifier."""
    from nebula.experiments.exp_coverage import RequestResult, verify_request
    from nebula.experiments.adaptive_screen import EDGE4_MANDATED, AdaptiveScreen

    res = RequestResult(peaking_db=float(cand["peaking_db"]),
                        f_peak_hz=float(cand["f_peak_hz"]),
                        solved_on_screen=True,
                        design_id=cand["design_id"], u=list(cand["u"]),
                        screen_reward=float(cand["screen_reward"]))
    verify_request(res, None, AdaptiveScreen(EDGE4_MANDATED))
    return {"index": cand["index"], "rank": cand["rank"],
            "peaking_db": cand["peaking_db"], "f_peak_hz": cand["f_peak_hz"],
            "design_id": cand["design_id"], "u": cand["u"],
            "screen_reward": cand["screen_reward"],
            "verified": res.verified,
            "n_pvt45_pass": res.n_pvt45_pass, "n_pvt45_total": res.n_pvt45_total,
            "pvt45_worst": res.pvt45_worst,
            "n_full135_pass": res.n_full135_pass,
            "full135_worst": res.full135_worst,
            "n_unscorable": res.n_unscorable,
            "failing_rows": list(res.failing_rows)}


def analyse(rows: list[dict], base: dict) -> dict:
    """Score entry 53. Thresholds are the registered ones."""
    movable = [r for r in rows
               if base.get(r["index"], {}).get("n_pvt45_pass", 45) < 45]
    control = [r for r in rows
               if base.get(r["index"], {}).get("n_pvt45_pass", 0) == 45]
    passed = {r["index"] for r in rows
              if r["n_pvt45_pass"] == r["n_pvt45_total"]}
    gained = sorted(r["index"] for r in movable if r["index"] in passed)
    base_cov = sum(1 for v in base.values() if v["n_pvt45_pass"] == 45)
    return {
        "entry40_coverage": base_cov,
        "movable_requests": sorted(r["index"] for r in movable),
        "control_requests": sorted(r["index"] for r in control),
        "gained": gained,
        "new_coverage": base_cov + len(gained),
        "control_all_pass": all(r["index"] in passed for r in control),
        "n_verify_decks": sum(r["n_pvt45_total"] or 0 for r in rows) * 3,
    }


def _report(d: dict) -> None:
    a = d["analysis"]
    print()
    print(f"{'req':>4} {'rank':>5} {'request':>18} {'45 corners':>12} "
          f"{'worst':>10} {'135':>8}  entry40")
    for r in d["rows"]:
        b = d["entry40"].get(str(r["index"]), d["entry40"].get(r["index"], {}))
        tag = f"{b.get('n_pvt45_pass','?')}/45 via {b.get('which_path','?')}"
        w = r["pvt45_worst"]
        print(f"{r['index']:>4} {r['rank']:>5} "
              f"{r['peaking_db']:>6.1f} dB @ {r['f_peak_hz'] / 1e9:.3f} GHz "
              f"{r['n_pvt45_pass']:>4}/{r['n_pvt45_total']:<3} "
              f"{(w if w is not None else float('nan')):>10.4f} "
              f"{r['n_full135_pass']:>4}/135  {tag}")
    print()
    print(f"  entry 40 coverage      {a['entry40_coverage']} of 16")
    print(f"  movable requests       {a['movable_requests']}")
    print(f"  control (already 45/45) {a['control_requests']}   "
          f"all pass: {a['control_all_pass']}")
    print(f"  GAINED                 {a['gained']}")
    print(f"  NEW COVERAGE           {a['new_coverage']} of 16")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m nebula.experiments.exp_deep_verify",
        description=__doc__)
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args(argv)

    if args.report:
        if not RESULTS.exists():
            print(f"error: {RESULTS} missing", file=sys.stderr)
            return 2
        _report(json.loads(RESULTS.read_text(encoding="utf-8")))
        return 0

    if not SCAN_K40.exists():
        print(f"error: {SCAN_K40} missing; run the k=40 scan first",
              file=sys.stderr)
        return 2

    print("=" * 74)
    print("STAGE 2 -- do the DEEP proposals hold at the MANDATED 45 corners?")
    print("=" * 74)
    print("ASSUMPTIONS, printed every run:")
    print("  1. Coverage upside is bounded at +2, computed BEFORE this run:")
    print("     requests 6 and 10 were already 45/45 via the entry 40 search,")
    print("     so only requests 3 and 5 can move the headline.")
    print("  2. verify_request runs 135 points and splits the mandated 45 out")
    print("     of them, so this costs 135 decks per design, not 45.")
    print("  3. Verification decks are NEVER added to an amortisation number.")
    print("=" * 74)

    t0 = time.time()
    scan = json.loads(SCAN_K40.read_text(encoding="utf-8"))
    cands = newly_accepted(scan)
    base = entry40_baseline()
    print(f"newly accepted below rank {SHALLOW_K}: "
          f"{[(c['index'], c['rank']) for c in cands]}")

    rows = []
    for c in cands:
        print(f"  verifying request {c['index']} (rank {c['rank']}) ...",
              flush=True)
        rows.append(verify_one(c))
        r = rows[-1]
        print(f"    {r['n_pvt45_pass']}/{r['n_pvt45_total']} mandated, "
              f"{r['n_full135_pass']}/135, worst {r['pvt45_worst']}")

    out = {"task": "stage 2: 45-corner verification of deep proposals "
                   "(PREDICTIONS.md entry 53)",
           "source_scan": SCAN_K40.name, "shallow_k": SHALLOW_K,
           "rows": rows, "entry40": base,
           "analysis": analyse(rows, base),
           "wall_clock_s": time.time() - t0}
    RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    _report(out)
    print(f"\nwrote {RESULTS.name}  ({out['wall_clock_s']:.1f} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
