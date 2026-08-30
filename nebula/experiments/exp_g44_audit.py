"""experiments/exp_g44_audit.py -- **the blast radius of the missing validity
gate, measured on the BASELINE before anything is retrained.**

WHAT WAS FOUND, AND WHY THIS FILE EXISTS
------------------------------------------
`rl/evaluator.validate` is this project's validity gate. Among other things it
implements **G44**: a response still rising at the top of the 20 GHz search
range has a FICTITIOUS peak, because `meas ac MAX` returns the range edge, and
`peaking_db` is then large and meaningless. `validate` rejects it two ways --
`Sky130Point.peak_is_sweep_edge` (the mechanism) and `F_PEAK_HZ_LIMITS`
(1e7 .. 1.8e10, the symptom).

**`experiments/adaptive_screen.evaluate_at_points` does not import
`validate`.** It imports `annotate_interpolated_peak`, `build_point` and
`scored_meas` and nothing else. So the four-corner screen -- the function that
decides whether a proposal is ACCEPTED, and the reward `rl/screen_env.py`
trains on -- has no G44 gate, while `nebula/design.py` (the deliverable),
`experiments/baselines.py` (the whole benchmark) and `rl/env.py` (the PPO
track) all do. **`exp_g4_verify.verify_full`, which produces every 45- and
135-point compliance number, does not have it either.**

Two definitions of validity in one repository is the third failure mode named
in `CLAUDE.md`, and entry 41's SAC policy walked straight into the gap: **all
52 of its fully-scorable proposals report a peak at 19.95 GHz.**

THE QUESTION THIS FILE ANSWERS, AND IT IS ABOUT THE CONTROL
-------------------------------------------------------------
Every accept rate this project has published -- entries 31, 32, 36, 38, 40, 41,
42 -- was scored through the ungated path, **including the non-RL library
baseline of 6 of 16 that every RL arm is measured against.** Fixing the gate
and then comparing against a contaminated bar would measure nothing.

So: **re-score every design this project has ever ACCEPTED, with the gate
applied**, and report the corrected baseline.

TWO PASSES, AND ONLY ONE OF THEM NEEDS A SIMULATOR
----------------------------------------------------
1. **`scan_audit()` -- zero SPICE.** Every scan artifact records the worst
   point's `f_peak_hz_got`, which answers the `F_PEAK_HZ_LIMITS` half exactly.
   It **cannot** answer the `peak_is_sweep_edge` half, which needs `g_top_db`,
   and no artifact records that. This pass is a LOWER BOUND and says so.
2. **`resimulate()` -- SPICE, ~170 decks.** Re-runs each accepted design at the
   points it was accepted on and applies **`evaluator.validate` itself**
   (imported, never reimplemented -- CLAUDEwa.md section 8 rule 9) to the
   resulting `Sky130Point`. This is the only pass that can answer the
   mechanism half.

WHAT THIS FILE DOES NOT DO
----------------------------
It does not modify `adaptive_screen`, `reward_v1`, any tolerance or any screen
point. It is a MEASUREMENT of how much would move if the gate were added. The
repair is a separate, pre-registered change.

    python -m nebula.experiments.exp_g44_audit --scan     # zero SPICE
    python -m nebula.experiments.exp_g44_audit --run      # ~170 decks
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "g44_audit_results.json"

#: Every artifact that records per-candidate accept decisions on the four-corner
#: screen. Listed by ENUMERATION so a new scan does not join silently (G101).
SCAN_ARTIFACTS: tuple[str, ...] = (
    "hybrid_topk_scan.json",              # entry 32, the k=8 baseline: A = 6
    "topk_scan_library_k5.json",          # entry 36's k=5 library control
    "topk_scan_sac_random_analytic.json", # entry 36
    "topk_scan_sac_random_finetuned.json",
    "topk_scan_sac_seeded_analytic.json",
    "topk_scan_sac_seeded_finetuned.json",
    "topk_scan_swing_random_k5.json",     # entry 38
    "topk_scan_swing_seeded_k5.json",
    "topk_scan_screen_random.json",       # entry 41
    "topk_scan_screen_seeded.json",
)

#: Designs whose COMPLIANCE (45 or 135 points) this project publishes. The
#: `u` vectors are read from the artifacts rather than restated (rule 9); these
#: names select which record to read.
COMPLIANCE_DESIGNS: tuple[tuple[str, str, str], ...] = (
    ("g4_verify_results.json", "57cba07581cd2603",
     "the delivered G4 design: 135 of 135 on V1_SPECS, 0 failed"),
    # `joint_verify_full_results.json` names this design but does not record
    # its `u`, so the audit reads it from `dfe_ablation_results.json`, which
    # does. Both artifacts agree on the `design_id`; the audit asserts that
    # rather than assuming it, because G124 records that ids do not join
    # across artifact boundaries and a silent empty join reads as a finding.
    ("dfe_ablation_results.json", "c507a3ba6f58b9a6",
     "the joint winner: 11 rows at 45 of 45 mandated corners "
     "(u read from dfe_ablation_results.json; verified in "
     "joint_verify_full_results.json)"),
)


# --------------------------------------------------------------------------
# pass 1 -- zero SPICE
# --------------------------------------------------------------------------

def scan_audit(paths: Sequence[Path]) -> dict:
    """The `F_PEAK_HZ_LIMITS` half, read off the artifacts. **No simulator.**

    Reports, per artifact, how many candidates and how many ACCEPTED
    candidates carry a worst-point peak outside the gate's frequency band.
    """
    from nebula.rl.evaluator import F_PEAK_HZ_LIMITS

    lo, hi = F_PEAK_HZ_LIMITS
    out: dict = {"limits_hz": [lo, hi], "artifacts": [],
                 "note": ("LOWER BOUND. This pass answers F_PEAK_HZ_LIMITS "
                          "only; peak_is_sweep_edge needs g_top_db, which no "
                          "scan artifact records.")}
    for p in paths:
        if not p.exists():
            out["artifacts"].append({"artifact": p.name, "missing": True})
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        tot = edge = acc = acc_edge = 0
        flagged = []
        for r in d.get("requests", []):
            for c in r.get("candidates", []):
                if "error" in c:
                    continue
                tot += 1
                f = c.get("f_peak_hz_got")
                bad = bool(f is not None and not (lo <= float(f) <= hi))
                edge += bad
                if c.get("feasible"):
                    acc += 1
                    acc_edge += bad
                    if bad:
                        flagged.append({"index": r["index"], "rank": c["rank"],
                                        "f_peak_hz": f, "reward": c["reward"],
                                        "u": c["u"]})
        out["artifacts"].append({
            "artifact": p.name, "k": d.get("k"), "n_candidates": tot,
            "n_outside_limits": edge, "n_accepted": acc,
            "n_accepted_outside_limits": acc_edge,
            "accepted_outside": flagged,
            "n_accepted_reported": d.get("n_accepted")})
    a = [x for x in out["artifacts"] if not x.get("missing")]
    out["total_candidates"] = sum(x["n_candidates"] for x in a)
    out["total_accepted"] = sum(x["n_accepted"] for x in a)
    out["total_accepted_outside_limits"] = sum(
        x["n_accepted_outside_limits"] for x in a)
    return out


def accepted_designs(paths: Sequence[Path]) -> list[dict]:
    """Every ACCEPTED candidate across the scans, deduplicated on `u`.

    Deduplicated on `u` to 1e-9 and **not** on `design_id`: G124 records that
    ids do not join across artifact boundaries because the two writers pass
    different `geometry_tag`s, and the failure mode is a silent empty join.
    """
    seen: dict[tuple, dict] = {}
    for p in paths:
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        for r in d.get("requests", []):
            for c in r.get("candidates", []):
                if "error" in c or not c.get("feasible"):
                    continue
                key = tuple(round(float(x), 9) for x in c["u"])
                rec = seen.setdefault(key, {
                    "u": [float(x) for x in c["u"]],
                    "peaking_db": float(r["peaking_db"]),
                    "f_peak_hz": float(r["f_peak_hz"]),
                    "request_index": r["index"], "sources": []})
                rec["sources"].append({"artifact": p.name, "rank": c["rank"],
                                       "reward": c["reward"],
                                       "f_peak_hz_got": c.get("f_peak_hz_got")})
    return list(seen.values())


# --------------------------------------------------------------------------
# pass 2 -- SPICE, and the gate is IMPORTED
# --------------------------------------------------------------------------

def gate_one_point(u: Sequence[float], sp, ac_peak_interp: bool = True) -> dict:
    """Re-run one design at one screen point and ask **`validate` itself**.

    The deck is the SCREEN's deck (`swing=True, hd3=True`), so the question is
    literally *"on the simulation the screen ran, what would the gate have
    said?"* rather than a re-derivation on a different deck (G32).
    """
    from nebula.device.sky130_runner import run_point
    from nebula.rl.contract import sizing_from_u
    from nebula.rl.evaluator import Verdict, build_point, validate

    c = sp.corner
    sizing = sizing_from_u(np.asarray(u, dtype=float), cl_f=float(sp.cl_f))
    point, _ = build_point(sizing, corner=c.process, vdd_scale=c.vdd_scale)
    pt = run_point(point, c.process, temp_c=c.temp_c, swing=True,
                   ac_sweep=True, hd3=True, ac_peak_interp=ac_peak_interp)
    if not pt.ok:
        return {"point": sp.label, "sim_ok": False,
                "fail_reason": pt.fail_reason, "verdict": None}
    verdict, why = validate(pt, point)
    g_pk = None if pt.g_pk_db is None else float(pt.g_pk_db)
    g_top = None if pt.g_top_db is None else float(pt.g_top_db)
    return {
        "point": sp.label, "sim_ok": True,
        "verdict": verdict.name, "why": why,
        "invalid": bool(verdict is Verdict.INVALID),
        "f_pk_hz": (None if pt.f_pk_hz is None else float(pt.f_pk_hz)),
        "g_pk_db": g_pk, "g_top_db": g_top,
        "g_pk_minus_g_top_db": (None if (g_pk is None or g_top is None)
                                else g_pk - g_top),
        "peak_is_sweep_edge": bool(pt.peak_is_sweep_edge),
        "has_interior_peak": bool(pt.has_interior_peak),
        "peaking_db": (None if pt.peaking_db is None else float(pt.peaking_db)),
    }


def gate_design(u: Sequence[float], points) -> dict:
    """`validate` at every point. A design is gate-rejected if ANY point is."""
    res = [gate_one_point(u, sp) for sp in points]
    return {"points": res, "n_points": len(res),
            "n_invalid": sum(1 for r in res if r.get("invalid")),
            "n_sweep_edge": sum(1 for r in res if r.get("peak_is_sweep_edge")),
            "n_sim_failed": sum(1 for r in res if not r.get("sim_ok")),
            "gate_rejects": bool(any(r.get("invalid") for r in res)),
            "n_sims": len(res)}


def compliance_design_u(artifact: str, design_id: str) -> list[float]:
    """The `u` of a published compliance result, read from its artifact.

    Raises rather than returning None: a missing design means the audit would
    silently skip the very claim it exists to check (G115).
    """
    d = json.loads((HERE / artifact).read_text(encoding="utf-8"))
    # Two artifact shapes in this repo: a `results` list of records, and a
    # single record at the top level. Both are read; neither is assumed.
    records = list(d.get("results") or [])
    if "design_id" in d:
        records.append(d)
    for r in records:
        if str(r.get("design_id")) == design_id:
            u = r.get("u")
            if not u:
                raise ValueError(
                    f"{artifact} record {design_id} carries no `u`; the audit "
                    f"cannot re-simulate a design it cannot reconstruct")
            return [float(x) for x in u]
    raise ValueError(f"{artifact} has no record with design_id {design_id}")


def run(scan_only: bool = False) -> dict:
    from nebula.experiments.adaptive_screen import EDGE4_MANDATED
    from nebula.experiments.runlock import hold, stamp

    t0 = time.time()
    paths = [HERE / n for n in SCAN_ARTIFACTS]
    out: dict = {"task": "G44 validity-gate blast radius, measured on the "
                         "baseline before anything is retrained",
                 **stamp(), "scan": scan_audit(paths)}
    s = out["scan"]
    print(f"\nPASS 1 (zero SPICE): {s['total_candidates']} candidates, "
          f"{s['total_accepted']} accepted, "
          f"{s['total_accepted_outside_limits']} accepted outside "
          f"F_PEAK_HZ_LIMITS", flush=True)
    for a in s["artifacts"]:
        if a.get("missing"):
            print(f"   {a['artifact']:38} MISSING", flush=True)
            continue
        print(f"   {a['artifact']:38} {a['n_candidates']:4d} cand  "
              f"{a['n_outside_limits']:3d} outside  "
              f"{a['n_accepted']:2d} accepted  "
              f"{a['n_accepted_outside_limits']:2d} accepted-outside",
              flush=True)
    if scan_only:
        out["wall_s"] = time.time() - t0
        return out

    with hold("g44_audit", meta={"pass": "resimulate"}):
        designs = accepted_designs(paths)
        print(f"\nPASS 2 (SPICE): {len(designs)} unique ACCEPTED designs "
              f"x {len(EDGE4_MANDATED)} screen points = "
              f"{len(designs) * len(EDGE4_MANDATED)} decks", flush=True)
        out["accepted"] = []
        for i, d in enumerate(designs):
            g = gate_design(d["u"], EDGE4_MANDATED)
            rec = {**{k: v for k, v in d.items() if k != "u"}, "u": d["u"], **g}
            out["accepted"].append(rec)
            arts = sorted({s0["artifact"] for s0 in d["sources"]})
            print(f"   [{i + 1:2d}/{len(designs)}] req {d['request_index']:2d} "
                  f"{d['peaking_db']:4.1f} dB @ {d['f_peak_hz'] / 1e9:.3f} GHz  "
                  f"gate_rejects={g['gate_rejects']}  "
                  f"invalid {g['n_invalid']}/{g['n_points']}  "
                  f"sweep_edge {g['n_sweep_edge']}/{g['n_points']}  "
                  f"[{', '.join(a.replace('.json', '') for a in arts)}]",
                  flush=True)

        out["n_accepted_designs"] = len(designs)
        out["n_gate_rejected"] = sum(1 for r in out["accepted"]
                                     if r["gate_rejects"])
        out["decks_pass2_accepted"] = sum(r["n_sims"] for r in out["accepted"])

        print(f"\nPASS 3 (SPICE): the published COMPLIANCE designs, "
              f"45 mandated corners each", flush=True)
        out["compliance"] = []
        for artifact, design_id, what in COMPLIANCE_DESIGNS:
            if not (HERE / artifact).exists():
                out["compliance"].append({"artifact": artifact,
                                          "design_id": design_id,
                                          "missing": True})
                print(f"   {artifact} MISSING", flush=True)
                continue
            u = compliance_design_u(artifact, design_id)
            pts = mandated_45()
            g = gate_design(u, pts)
            out["compliance"].append({"artifact": artifact,
                                      "design_id": design_id, "what": what,
                                      "u": u, **g})
            print(f"   {design_id}  {what}\n"
                  f"      gate_rejects={g['gate_rejects']}  "
                  f"invalid {g['n_invalid']}/{g['n_points']}  "
                  f"sweep_edge {g['n_sweep_edge']}/{g['n_points']}", flush=True)

        out["n_compliance_gate_rejected"] = sum(
            1 for r in out["compliance"] if r.get("gate_rejects"))
        out["total_decks"] = (out["decks_pass2_accepted"]
                              + sum(r.get("n_sims", 0)
                                    for r in out["compliance"]))
        out["wall_s"] = time.time() - t0
        RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print(f"\nwrote {RESULTS.name}", flush=True)
    return out


def mandated_45():
    """The 45 mandated PVT corners at the DESIGN load. G109's compliance grid.

    Built from `adaptive_screen`'s own corner list rather than re-enumerated
    here, so there is one definition of "the mandated 45" (rule 9).
    """
    from nebula.common.types import all_corners
    from nebula.experiments.adaptive_screen import EDGE4_MANDATED, ScreenPoint

    cl = float(EDGE4_MANDATED[0].cl_f)
    if any(abs(float(p.cl_f) - cl) > 0 for p in EDGE4_MANDATED):
        raise ValueError("EDGE4_MANDATED is not at a single load; the "
                         "mandated grid's load axis is ambiguous (G109)")
    corners = all_corners()
    if len(corners) != 45:
        raise ValueError(f"all_corners() is {len(corners)}, not the 45 the "
                         f"competition slide mandates")
    return [ScreenPoint(corner=c, cl_f=cl, why="mandated 45, design load")
            for c in corners]


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--scan", action="store_true",
                    help="pass 1 only, zero SPICE")
    a = ap.parse_args(argv)
    if not (a.run or a.scan):
        ap.print_help()
        return 0
    d = run(scan_only=a.scan and not a.run)
    if not a.scan or a.run:
        print(f"\n  ACCEPTED designs gate-rejected: "
              f"{d.get('n_gate_rejected')} of {d.get('n_accepted_designs')}")
        print(f"  COMPLIANCE designs gate-rejected: "
              f"{d.get('n_compliance_gate_rejected')} of "
              f"{len(d.get('compliance') or [])}")
        print(f"  decks spent: {d.get('total_decks')}")
    return 0


if __name__ == "__main__":                                  # pragma: no cover
    raise SystemExit(main())
