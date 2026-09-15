"""
experiments/exp_unscorable.py — **task 4d's instrument: WHY is the eye
unmeasurable, corner by corner?** (`PROGRESS.md` §6 row 4d, entry 53's closing
paragraph)

    python -m nebula.experiments.exp_unscorable            # requests 3 and 5
    python -m nebula.experiments.exp_unscorable --all      # all four of entry 53
    python -m nebula.experiments.exp_unscorable --report   # re-print the artifact

WHY THIS EXISTS
----------------
Entry 53 established the shape of the remaining coverage gap and then could not
look inside it:

    "The binding constraint on coverage is not the search, the ranking or the
     library. It is that the eye cannot be computed at the corners where the
     stage compresses."

Request 3 is **one corner** from taking mandated coverage 8 -> 9 of 16, and
every failing point in that run carried a POSITIVE worst margin -- so no spec is
violated; the eye simply refuses to be scored. Whether that refusal is
**physical** (the circuit genuinely cannot swing that far) or **modelling**
(the check is conservative at a boundary) decides whether there is a coverage
point sitting on the table.

**The artifacts on disk cannot answer it.** `exp_g4_verify.FullPointResult`
carries a `reason` string for every point that fails to evaluate, and
`exp_coverage._rescore` drops it on the floor:

    out.append({... "failed": ["UNSCORABLE"] ...})    # reason discarded

So `deep_verify_results.json` records `n_unscorable = 46` and not one word about
why. This file re-runs the same verifier and **keeps the reason**.

THERE ARE TWO UNSCORABLE PATHS AND THEY ARE NOT THE SAME FAILURE
------------------------------------------------------------------
**The first version of this file checked the wrong flag and reported the
opposite of the truth**, so the distinction is written down rather than
remembered. `_rescore` emits two different verdicts:

    ok = False                     -> "UNSCORABLE"        the POINT never
                                                          evaluated: ngspice,
                                                          geometry, the fit
    ok = True, S8 rows missing     -> "EYE_UNMEASURABLE"  the point evaluated
                                                          FINE and the LINK
                                                          refused -- this is
                                                          the compression case

Filtering on `ok` alone sees only the first and declares the second clean: it
scored request 5 at "45 of 45 evaluable" when 8 of its corners carry no eye.
Same shape as G115 -- a set built by testing the convenient flag loses members
without saying so. **Blocked-ness here is `not ok` OR an S8 row in
`unmeasured_specs`**, and the two are counted separately in every output.

WHAT IT MEASURES, AND THE ONE NUMBER THAT DECIDES
--------------------------------------------------
`link/calibration.check_compression` refuses when the pulse response's peak
excursion exceeds the stage's measured linear limit, and its message carries
both numbers. The ratio of the two is the whole question:

    ratio ~ 1.0    the design is AT the boundary -- a refusal that a more
                   careful instrument might not have to make
    ratio >> 1.0   the design is being asked for swing it cannot produce.
                   Physical. Nothing to recover.

For scale, measured over the 573 compression refusals already recorded in
`hybrid_topk_scan_k40.json`: median ratio **1.89x**, and only **5.2 %** sit
within 1.05x. The population answer is already "physical". This file asks the
same question of the **four specific designs entry 53 verified**, because a
population median says nothing about the single corner request 3 is missing.

WHAT IS NOT DONE HERE
----------------------
**Nothing is tuned and nothing is loosened.** `check_compression`,
`compression_margin`, the tolerances, the screen, `V6_SPECS`, the box and
`reward_v1.py` are untouched -- this file only calls `verify_full` and reads
what it already returns. Standing rule 7: wrap, do not replace.

**No coverage or compliance claim comes out of this file.** It runs at ONE load
(the design load), so it produces the mandated 45-corner column only, and it is
a diagnosis of designs already verified in entry 53 -- not a new verification of
anything.

COST
-----
45 decks per design at the design load: **90 decks** by default (requests 3 and
5, the two entry 53 identified as movable), 180 with `--all`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Optional, Sequence

HERE = Path(__file__).resolve().parent

DEEP_VERIFY = HERE / "deep_verify_results.json"
RESULTS = HERE / "unscorable_diagnosis.json"

#: Entry 53's two movable requests -- the only ones whose outcome can move the
#: 8-of-16 headline. Requests 6 and 10 are its control pair and are already
#: 45/45, so they are diagnosed only under `--all`.
MOVABLE: tuple[int, ...] = (3, 5)

#: `check_compression`'s message, which is the one place both numbers appear.
_COMPRESSION = re.compile(
    r"output swing ([0-9.]+) mVpp exceeds the linear limit ([0-9.]+) mVpp "
    r"\(vout_swing_v=([0-9.]+) mVpp")

#: At or below this the refusal is a boundary call rather than a verdict. Chosen
#: to match `check_compression`'s own `margin` semantics (a 5 % band), and
#: registered here so it cannot be moved after seeing the answer.
NEAR_MISS_RATIO: float = 1.05


def classify(reason: Optional[str]) -> dict:
    """One point's refusal, parsed into numbers where the message carries them.

    Every branch is named. A reason this does not recognise comes back as
    `kind="other"` **with its text**, never silently bucketed -- an unparsed
    string that reads as a known category is how a diagnosis invents a finding.
    """
    if not reason:
        return {"kind": "none", "reason": reason}
    m = _COMPRESSION.search(reason)
    if m:
        req, lim, swing = (float(m.group(1)), float(m.group(2)),
                           float(m.group(3)))
        return {"kind": "compression", "required_pp_mv": req,
                "limit_pp_mv": lim, "vout_swing_pp_mv": swing,
                "ratio": req / lim, "near_miss": (req / lim) <= NEAR_MISS_RATIO,
                "reason": reason}
    low = reason.lower()
    for kind, needle in (("unrealisable_geometry", "unrealisable geometry"),
                         ("no_swing_sweep", "vout_swing_v is missing"),
                         ("fit_failed", "pole-zero fit"),
                         ("ngspice", "ngspice")):
        if needle in low:
            return {"kind": kind, "reason": reason}
    return {"kind": "other", "reason": reason}


def load_designs(all_four: bool) -> list[dict]:
    """The designs to diagnose, read from entry 53's artifact.

    Raises if the artifact is absent -- standing rule 4: a missing artifact
    raises, it never gets a placeholder.
    """
    if not DEEP_VERIFY.exists():
        raise FileNotFoundError(
            f"{DEEP_VERIFY} does not exist. Run exp_deep_verify first; this "
            f"file diagnoses ITS designs and invents none of its own.")
    rows = json.loads(DEEP_VERIFY.read_text(encoding="utf-8"))["rows"]
    if all_four:
        return list(rows)
    keep = [r for r in rows if int(r["index"]) in MOVABLE]
    if len(keep) != len(MOVABLE):
        raise ValueError(
            f"expected the movable requests {MOVABLE} in {DEEP_VERIFY.name}, "
            f"found {[r['index'] for r in rows]}")
    return keep


def diagnose_one(row: dict) -> dict:
    """45 mandated corners at the DESIGN load, reasons kept.

    Calls `verify_full` with a single load so the run is the mandated 45-corner
    grid (D8) and cannot be misread as the 135-point robustness sweep.
    """
    from nebula.experiments.exp_g4_verify import Candidate, verify_full
    from nebula.experiments.s9_yield import PROMOTION_LOADS

    design_load = sorted(PROMOTION_LOADS)[len(PROMOTION_LOADS) // 2]
    cand = Candidate(design_id=row["design_id"], u=tuple(row["u"]),
                     role="unscorable-diagnosis",
                     source=f"entry53/req{row['index']}@rank{row['rank']}",
                     claimed_reward=float(row["screen_reward"]),
                     claimed_worst_point=None)
    out = verify_full(cand, loads=[float(design_load)], ac_peak_interp=True)
    pts = out.get("points") or []
    if len(pts) != 45:
        raise ValueError(
            f"expected 45 mandated corners at one load, got {len(pts)} -- the "
            f"grid is not what this diagnosis says it is")

    from nebula.rl.reward_v1 import S8_SPECS

    points = []
    for p in pts:
        unmeasured = list(p.get("unmeasured_specs") or [])
        eye_blocked = bool(set(unmeasured) & set(S8_SPECS))
        rec = {"corner": p["corner"], "vdd_scale": p["vdd_scale"],
               "temp_c": p["temp_c"], "ok": bool(p["ok"]),
               "eye_blocked": eye_blocked,
               "blocked": (not p["ok"]) or eye_blocked,
               "unmeasured_specs": unmeasured,
               # Recorded whether or not the point is blocked: the whole
               # question is how the blocked ones differ from the clear ones,
               # and a field present only on failures cannot answer that.
               "drive_overdrive_x": p.get("drive_overdrive_x"),
               "linear_in_nyq_pp_v": p.get("linear_in_nyq_pp_v"),
               "drive_pp_v": p.get("drive_pp_v"),
               "vout_swing_v": p.get("vout_swing_v"),
               "eye_h_v": p.get("eye_h_v")}
        if rec["blocked"]:
            rec.update(classify(p.get("reason")))
        points.append(rec)

    bad = [p for p in points if p["blocked"]]
    comp = [p for p in bad if p.get("kind") == "compression"]
    ratios = sorted(p["ratio"] for p in comp)
    ov = sorted(p["drive_overdrive_x"] for p in bad
                if p.get("drive_overdrive_x") is not None)
    return {
        "index": row["index"], "rank": row["rank"],
        "design_id": row["design_id"],
        "peaking_db": row["peaking_db"], "f_peak_hz": row["f_peak_hz"],
        "n_points": len(points), "n_ok": sum(1 for p in points if p["ok"]),
        "n_blocked": len(bad),
        "n_point_failed": sum(1 for p in points if not p["ok"]),
        "n_eye_blocked": sum(1 for p in points if p["eye_blocked"]),
        "kinds": {k: sum(1 for p in bad if p.get("kind") == k)
                  for k in sorted({p.get("kind") for p in bad})},
        "n_near_miss": sum(1 for p in comp if p["near_miss"]),
        "ratio_min": (ratios[0] if ratios else None),
        "ratio_median": (ratios[len(ratios) // 2] if ratios else None),
        "ratio_max": (ratios[-1] if ratios else None),
        "overdrive_min": (ov[0] if ov else None),
        "overdrive_max": (ov[-1] if ov else None),
        "points": points,
    }


def analyse(rows: list[dict]) -> dict:
    """The verdict this file exists to produce, stated as a branch.

    `physical` and `boundary` are counted separately per design AND in
    aggregate, because request 3 -- one corner from compliance -- is a single
    point whose answer an aggregate would bury.
    """
    comp = [p for r in rows for p in r["points"]
            if p["blocked"] and p.get("kind") == "compression"]
    near = [p for p in comp if p["near_miss"]]
    return {
        "n_designs": len(rows),
        "n_points": sum(r["n_points"] for r in rows),
        "n_blocked": sum(r["n_blocked"] for r in rows),
        "n_point_failed": sum(r["n_point_failed"] for r in rows),
        "n_eye_blocked": sum(r["n_eye_blocked"] for r in rows),
        "n_compression": len(comp),
        "n_near_miss": len(near),
        "near_miss_ratio_threshold": NEAR_MISS_RATIO,
        "per_request": {str(r["index"]): {"n_blocked": r["n_blocked"],
                                          "n_near_miss": r["n_near_miss"],
                                          "ratio_min": r["ratio_min"]}
                        for r in rows},
        # The branch, stated before the numbers are read.
        "verdict": ("boundary: at least one refusal sits within "
                    f"{NEAR_MISS_RATIO}x of the limit"
                    if near else
                    "physical: every refusal asks for swing the stage cannot "
                    "produce"),
    }


def _report(d: dict) -> None:
    a = d["analysis"]
    print()
    print("UNSCORABLE DIAGNOSIS -- task 4d. 45 mandated corners, design load.")
    print(f"  designs {a['n_designs']}   points {a['n_points']}   "
          f"blocked {a['n_blocked']}  "
          f"(point failed {a['n_point_failed']}, eye blocked "
          f"{a['n_eye_blocked']})")
    print()
    print("  req  rank  blocked/45  point-failed  eye-blocked  kinds")
    for r in d["rows"]:
        kinds = ", ".join(f"{k}={v}" for k, v in r["kinds"].items()) or "-"
        print(f"  {r['index']:>3}  {r['rank']:>4}  {r['n_blocked']:>7}/45  "
              f"{r['n_point_failed']:>12}  {r['n_eye_blocked']:>11}  {kinds}")
    print()
    print("  compression refusals: required / linear limit")
    for r in d["rows"]:
        if r["ratio_min"] is None:
            print(f"  req {r['index']:>3}   none")
            continue
        print(f"  req {r['index']:>3}   min {r['ratio_min']:.3f}x   "
              f"med {r['ratio_median']:.3f}x   max {r['ratio_max']:.3f}x   "
              f"near-miss {r['n_near_miss']}   "
              f"drive overdrive {r['overdrive_min']:.2f}x-"
              f"{r['overdrive_max']:.2f}x")
    print()
    print(f"  VERDICT  {a['verdict']}")
    print(f"  wall clock {d['wall_clock_s']:.1f} s, {d['n_decks']} decks")
    print()


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true",
                    help="diagnose all four entry-53 designs, not just the "
                         "two movable ones")
    ap.add_argument("--report", action="store_true",
                    help="re-print the existing artifact, run nothing")
    args = ap.parse_args(argv)

    if args.report:
        if not RESULTS.exists():
            print(f"no artifact at {RESULTS}", file=sys.stderr)
            return 1
        _report(json.loads(RESULTS.read_text(encoding="utf-8")))
        return 0

    designs = load_designs(args.all)
    t0 = time.time()
    rows = [diagnose_one(r) for r in designs]
    out = {"task": "4d -- why is the eye unmeasurable",
           "source": DEEP_VERIFY.name,
           "grid": "45 mandated corners at the design load (D8)",
           "rows": rows, "analysis": analyse(rows),
           "n_decks": sum(r["n_points"] for r in rows),
           "wall_clock_s": time.time() - t0}
    RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    _report(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
