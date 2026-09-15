"""
experiments/exp_bypass_recover.py — **entry 54: request 3's last corner is a
known ngspice singularity (G54), not physics. Does clearing it reach 9 of 16?**

    python -m nebula.experiments.exp_bypass_recover
    python -m nebula.experiments.exp_bypass_recover --report

WHY THIS EXISTS
----------------
`exp_unscorable.py` (task 4d) separated two failures the artifacts had merged:

    request 5   8 corners  "EYE_UNMEASURABLE"  compression, ALL at VDD-5 %
    request 3   1 corner   "UNSCORABLE"        ngspice: inoise_total = -nan(ind)

Request 3 is **one corner** from mandated coverage 8 -> 9 of 16, and that corner
is **G54**: the mirror's reference-device noise is rejected to machine zero by
symmetry, ngspice's integrated-noise log-slope integration evaluates `log(0)`,
returns `-nan(ind)`, and **exits 0**. G54 also records the remedy and that the
remedy is answer-neutral -- 1p/10p/100p/1n give `inoise_total` identical to
every printed digit wherever they all compute.

THE CONTROL OUTRANKS THE HEADLINE
-----------------------------------
Raising a circuit element until a number appears is indistinguishable from
buying the result, unless the invariance is **measured on this design** rather
than cited. So Q1 re-runs all 45 mandated corners at both bypass values and
compares `vn_in_vrms`, `g_dc_db` and the interpolated `f_pk` **digit for
digit**. If any corner disagrees, the run stops and reports nothing else:
entry 54's decision rule says no coverage number from this entry is then
admissible.

WHAT IS CHANGED, AND WHAT IS NOT
----------------------------------
**One field, on one instance, through a wrapper.** `TailDevice.c_bypass_f` is a
per-instance field; `_raised_bypass` patches `exp_g4_verify.build_point` for the
duration of a call and restores it in a `finally`. **`C_BYPASS_F`'s default of
10 pF is NOT changed** -- every published number was measured against it --
and no protected file is touched (rule 7). `check_compression`, the tolerances,
the screen, `V6_SPECS`, the box and `reward_v1.py` are untouched.

**`RAISED_BYPASS_F` = 30 pF is the smallest of the three values measured to
clear this corner, not a swept one.** Declared input 2 of entry 54 measured
30 p / 100 p / 1 n as bit-identical; picking the smallest keeps the added
capacitor -- and the S7 area it is not yet billed for -- as small as the
mechanism allows.

WHY `noise_detail` IS OFF
--------------------------
`run_point(noise_detail=True)` produces a DIFFERENT failure at raised bypass
(`vector inoise_total_rlp ... zero length`). That is an artifact of the detail
flag, not of the bypass. The production path passes `noise_detail=False` and so
does this file; entry 54 declared input 3 records it because the obvious
diagnostic flag hits it.

COST
-----
Q1's invariance pass is 45 decks per bypass value at the design load. Q3 and Q5
re-verify through `exp_deep_verify.verify_one`, which is `verify_request` and
therefore **135 decks per design** (3 loads) -- the same instrument entry 53
used, so the 45-corner column is comparable to its 44/45 and 37/45 without
adjustment. **360 decks total.**
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Sequence

HERE = Path(__file__).resolve().parent

DEEP_VERIFY = HERE / "deep_verify_results.json"
RESULTS = HERE / "bypass_recover_results.json"

#: The request whose single blocking corner this entry is about.
TARGET_REQUEST: int = 3
#: The registered expected null (entry 54 Q5): link-layer compression, so a
#: device-side bypass cannot touch it.
NULL_REQUEST: int = 5

#: Smallest bypass measured to clear the singularity on this design. NOT swept.
RAISED_BYPASS_F: float = 30e-12

#: The corner entry 53 lost. Named so a run that clears a DIFFERENT corner
#: cannot be read as having cleared this one.
BLOCKING_CORNER: tuple[str, float, float] = ("tt", 1.00, 0.0)

#: Q1 compares these three, exactly as registered.
INVARIANT_FIELDS: tuple[str, ...] = ("vn_in_vrms", "g_dc_db", "f_pk_interp_hz")


@contextmanager
def _raised_bypass(c_bypass_f: float):
    """Patch `exp_g4_verify.build_point` to raise the tail's bypass.

    Wrapping rather than editing: `build_point`'s own docstring says its
    defaults are the published configuration and must stay that way, and
    `C_BYPASS_F` is a default every published number was measured against.
    Restored in a `finally` so a raised bypass cannot leak into a later call in
    the same process -- which would silently contaminate the control.
    """
    import nebula.experiments.exp_g4_verify as V

    real = V.build_point

    def wrapped(sizing, **kw):
        point, geo = real(sizing, **kw)
        if point.tail is None:
            raise ValueError(
                "build_point returned a point with no tail, so there is no "
                "bypass to raise -- this wrapper would be a silent no-op")
        return (dataclasses.replace(
            point, tail=dataclasses.replace(point.tail,
                                            c_bypass_f=float(c_bypass_f))),
                geo)

    V.build_point = wrapped
    try:
        yield
    finally:
        V.build_point = real


def _row(index: int) -> dict:
    if not DEEP_VERIFY.exists():
        raise FileNotFoundError(
            f"{DEEP_VERIFY} does not exist. This entry diagnoses ITS designs "
            f"and invents none of its own.")
    rows = json.loads(DEEP_VERIFY.read_text(encoding="utf-8"))["rows"]
    hit = [r for r in rows if int(r["index"]) == index]
    if not hit:
        raise ValueError(f"request {index} is not in {DEEP_VERIFY.name}")
    return hit[0]


def invariance_pass(row: dict, c_bypass_f: Optional[float]) -> list[dict]:
    """All 45 mandated corners at the design load, raw device numbers.

    `c_bypass_f=None` is the baseline: the point is used exactly as
    `build_point` returns it, so the baseline arm shares every line of code
    with the production path.
    """
    from nebula.common.types import all_corners
    from nebula.device.sky130_runner import run_point
    from nebula.experiments.s9_yield import PROMOTION_LOADS
    from nebula.rl.contract import sizing_from_u
    from nebula.rl.evaluator import build_point

    cl = sorted(PROMOTION_LOADS)[len(PROMOTION_LOADS) // 2]
    sizing = sizing_from_u(row["u"], cl_f=float(cl))
    out = []
    for c in all_corners():
        point, _ = build_point(sizing, corner=c.process,
                               vdd_scale=c.vdd_scale)
        if c_bypass_f is not None:
            point = dataclasses.replace(
                point, tail=dataclasses.replace(point.tail,
                                                c_bypass_f=float(c_bypass_f)))
        pt = run_point(point, c.process, temp_c=c.temp_c, swing=True,
                       ac_sweep=True, hd3=True, ac_peak_interp=True)
        rec = {"corner": c.process, "vdd_scale": c.vdd_scale,
               "temp_c": c.temp_c, "ok": bool(pt.ok),
               "fail_reason": pt.fail_reason}
        for f in INVARIANT_FIELDS:
            rec[f] = getattr(pt, f, None)
        out.append(rec)
    return out


def compare(base: Sequence[dict], raised: Sequence[dict]) -> dict:
    """Q1. Every corner that computed at 10 pF must be identical at 30 pF.

    Compared with `==` on the parsed floats, not with a tolerance: the claim
    being tested is *bit-identical*, and a tolerance would be the place a real
    drift could hide.
    """
    if len(base) != len(raised):
        raise ValueError(f"grid mismatch: {len(base)} vs {len(raised)}")
    diffs, recovered, lost = [], [], []
    for b, r in zip(base, raised):
        key = (b["corner"], b["vdd_scale"], b["temp_c"])
        if key != (r["corner"], r["vdd_scale"], r["temp_c"]):
            raise ValueError(f"corner order differs: {key} vs "
                             f"{(r['corner'], r['vdd_scale'], r['temp_c'])}")
        if not b["ok"] and r["ok"]:
            recovered.append({"corner": key, "reason_at_10pF": b["fail_reason"],
                              **{f: r[f] for f in INVARIANT_FIELDS}})
            continue
        if b["ok"] and not r["ok"]:
            lost.append({"corner": key, "reason_at_30pF": r["fail_reason"]})
            continue
        if not b["ok"]:
            continue
        bad = {f: (b[f], r[f]) for f in INVARIANT_FIELDS if b[f] != r[f]}
        if bad:
            diffs.append({"corner": key, "fields": bad})
    n_both = sum(1 for b, r in zip(base, raised) if b["ok"] and r["ok"])
    return {"n_corners": len(base), "n_ok_baseline": sum(1 for b in base if b["ok"]),
            "n_ok_raised": sum(1 for r in raised if r["ok"]),
            "n_compared": n_both, "n_differing": len(diffs),
            "differing": diffs, "recovered": recovered, "lost": lost,
            "identical": not diffs and not lost}


def rescore(row: dict, c_bypass_f: float) -> dict:
    """Q3/Q5. The same verifier entry 53 used, under the raised bypass."""
    from nebula.experiments.exp_deep_verify import verify_one

    with _raised_bypass(c_bypass_f):
        return verify_one(row)


def analyse(d: dict) -> dict:
    """Score entry 54's six questions. Thresholds are the registered ones."""
    inv = d["invariance"]
    tgt, null = d["target"], d["null"]
    rec_corners = [tuple(r["corner"]) for r in inv["recovered"]]
    blocking = list(BLOCKING_CORNER)

    q1 = inv["identical"]
    q2 = [list(c) for c in rec_corners] == [blocking] or blocking in [
        list(c) for c in rec_corners]
    q3 = tgt["after"]["n_pvt45_pass"] == 45
    # Q4: the recovered corner's noise against its own tt/1.00 family.
    fam = [r["vn_in_vrms"] for r in d["raised_points"]
           if r["corner"] == "tt" and r["vdd_scale"] == 1.00
           and r["ok"] and r["vn_in_vrms"] is not None
           and r["temp_c"] != BLOCKING_CORNER[2]]
    got = next((r["vn_in_vrms"] for r in d["raised_points"]
                if (r["corner"], r["vdd_scale"], r["temp_c"])
                == BLOCKING_CORNER and r["ok"]), None)
    q4 = bool(fam) and got is not None and min(fam) <= got <= max(fam)
    q5 = null["after"]["n_pvt45_pass"] == null["before"]["n_pvt45_pass"]
    q6 = d["n_nan_blocked_baseline"] <= 2

    coverage = d["entry40_coverage"] + (1 if q3 else 0)
    return {
        "Q1_invariance": q1, "Q2_corner_computes": q2,
        "Q3_coverage_9": q3, "Q4_not_an_outlier": q4,
        "Q5_null_holds": q5, "Q6_bounded_nuisance": q6,
        "n_hit": sum([q1, q2, q3, q4, q5, q6]),
        "vn_family_tt_1p00": {"min": (min(fam) if fam else None),
                              "max": (max(fam) if fam else None),
                              "recovered": got},
        "coverage_before": d["entry40_coverage"],
        "coverage_after": coverage,
        "admissible": q1,
    }


def _report(d: dict) -> None:
    a, inv = d["analysis"], d["invariance"]
    print()
    print("BYPASS RECOVERY -- entry 54. G54's singularity at request 3's last corner.")
    print(f"  bypass  {d['baseline_bypass_f'] * 1e12:.0f} pF -> "
          f"{d['raised_bypass_f'] * 1e12:.0f} pF   decks {d['n_decks']}")
    print()
    print("  Q1 CONTROL -- invariance over the 45 mandated corners")
    print(f"    computed at both      {inv['n_compared']}")
    print(f"    differing in any of   {', '.join(INVARIANT_FIELDS)}: "
          f"{inv['n_differing']}")
    print(f"    recovered             {len(inv['recovered'])}   "
          f"lost {len(inv['lost'])}")
    for r in inv["recovered"]:
        print(f"      {r['corner']}  was: {str(r['reason_at_10pF'])[:60]}")
    print()
    print("  coverage arms (45 mandated corners, via verify_request)")
    for name, k in (("request 3 (target)", "target"), ("request 5 (null)", "null")):
        r = d[k]
        # On the Q1-failure path these arms are deliberately NOT run, so there
        # is nothing to print. Saying so beats printing a number that does not
        # exist -- which is what the first version of this line did.
        if not r.get("before") or not r.get("after"):
            print(f"    {name:<20} not run ({r.get('skipped', 'no result')})")
            continue
        print(f"    {name:<20} {r['before']['n_pvt45_pass']}/45 -> "
              f"{r['after']['n_pvt45_pass']}/45")
    print()
    for q in ("Q1_invariance", "Q2_corner_computes", "Q3_coverage_9",
              "Q4_not_an_outlier", "Q5_null_holds", "Q6_bounded_nuisance"):
        if q in a:
            print(f"    {q:<22} {'HIT' if a[q] else 'MISS'}")
    print(f"    scored {a['n_hit']} of 6")
    print()
    if not a["admissible"]:
        print("  Q1 MISSED -- the knob is buying the answer. NO COVERAGE "
              "NUMBER FROM THIS RUN IS ADMISSIBLE.")
    else:
        print(f"  MANDATED COVERAGE  {a['coverage_before']} -> "
              f"{a['coverage_after']} of 16")
    print(f"  wall clock {d['wall_clock_s']:.1f} s")
    print()


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", action="store_true",
                    help="re-print the existing artifact, run nothing")
    args = ap.parse_args(argv)

    if args.report:
        if not RESULTS.exists():
            print(f"no artifact at {RESULTS}", file=sys.stderr)
            return 1
        _report(json.loads(RESULTS.read_text(encoding="utf-8")))
        return 0

    tgt_row, null_row = _row(TARGET_REQUEST), _row(NULL_REQUEST)
    t0 = time.time()

    base_pts = invariance_pass(tgt_row, None)
    raised_pts = invariance_pass(tgt_row, RAISED_BYPASS_F)
    inv = compare(base_pts, raised_pts)

    out = {
        "entry": 54,
        "baseline_bypass_f": 1e-11, "raised_bypass_f": RAISED_BYPASS_F,
        "entry40_coverage": 8,
        "invariance": inv,
        "baseline_points": base_pts, "raised_points": raised_pts,
        "n_nan_blocked_baseline": sum(
            1 for p in base_pts
            if not p["ok"] and "nan" in str(p["fail_reason"]).lower()),
    }

    # **Q1 gates the rest, in code and not only in prose.** Entry 54's decision
    # rule says a failed control makes every later number inadmissible; running
    # them anyway would put those numbers on disk where they can be quoted.
    if not inv["identical"]:
        out["target"] = out["null"] = {"before": None, "after": None,
                                       "skipped": "Q1 failed"}
        out["analysis"] = {"Q1_invariance": False, "admissible": False,
                           "n_hit": 0, "coverage_before": 8,
                           "coverage_after": 8}
        out["n_decks"] = 90
        out["wall_clock_s"] = time.time() - t0
        RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
        _report(out)
        return 1

    out["target"] = {"before": {"n_pvt45_pass": tgt_row["n_pvt45_pass"]},
                     "after": rescore(tgt_row, RAISED_BYPASS_F)}
    out["null"] = {"before": {"n_pvt45_pass": null_row["n_pvt45_pass"]},
                   "after": rescore(null_row, RAISED_BYPASS_F)}
    out["n_decks"] = 90 + 135 + 135
    out["analysis"] = analyse(out)
    out["wall_clock_s"] = time.time() - t0
    RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    _report(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
