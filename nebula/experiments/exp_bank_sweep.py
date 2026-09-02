"""
experiments/exp_bank_sweep.py — **one fixed part, one 6-bit code: how much of
the 16-request grid does the bank serve at the 45 mandated corners?**

    python -m nebula.experiments.exp_bank_sweep --run
    python -m nebula.experiments.exp_bank_sweep --analyse

WHY THIS FILE, AND WHY IT COSTS NOTHING EXTRA
----------------------------------------------
Entry 70 measured the 8x8 bank's *reachable* range at TT: peaking 1.78-13.05 dB,
`f_peak` 1.109-3.387 GHz, 100 % of S3's window, and the code -> response map
**monotone on every row and column**. That is what the knob reaches, not what it
complies with. This file asks the compliance question, and it asks it for the
whole request grid at once.

**The trick is that a measurement does not know what it was aiming at.** Of the
13 rows in `V6_SPECS`, exactly **three** depend on the request --
`S3_f_peak_band`, `S3_f_peak_match`, `S3_peaking_match` -- and all three are
computable from two numbers the measurement already carries, `peaking_db` and
`f_peak_oct`. So 64 codes x 45 corners is **2 880 SPICE decks once**, and every
one of the 16 requests is then a **free re-score** of those same decks.

`reward_v1.request_rows` is the one definition of that arithmetic, shared with
`margins()` and `exp_coverage._rescore`. **G115 is what the second copy cost**:
`_rescore` silently dropped two of the three rows and a design peaking at
10.818 GHz -- 4.3x outside S3's window -- verified at 45 of 45 corners.

WHAT THIS IS, AND PRECISELY WHAT IT IS NOT
--------------------------------------------
It is **45 mandated PVT corners at the design load, scored on `V6_SPECS` (13
rows) through `adaptive_screen.evaluate_at_points`** -- the same evaluator, and
the same 13 rows, that `design.py --method auto` screens on.

It is **NOT** `exp_g4_verify.verify_full`, and the difference must travel with
any number from here:

* **one load, not three.** The 45 mandated PVT corners are the competition's own
  requirement (D8); the 135-point load grid is this project's extra axis and is
  not swept here.
* **`S4_hd3_nyq`, not `S4_hd3`.** `V6_SPECS` carries HD3 at the *operating
  point* -- 2.5 GHz at the amplitude the link actually delivers -- which is this
  project's harder self-imposed row. `V6V_SPECS`, which the 135-point checklist
  scores, carries S4's literal 100 MHz row instead. **This sweep is therefore
  STRICTER than the delivered path's verification on that row**, not laxer.
* it is a different function from the one that produced the 14-of-16 headline,
  so a number from here may not be added to that one.

THE STALE-ROW TRAP, CLOSED BY CONSTRUCTION
--------------------------------------------
`evaluate_at_points` must be handed *some* target, and it writes the three
request rows into its margins using it. Those values are **wrong for every
other request**. Rather than trusting each re-score to overwrite all three,
`_strip_request_rows` **deletes them at sweep time**, so a stale value cannot
survive into an artifact and be re-scored against silently. A missing row raises
in `rescore_margins`; a stale row would not have. `test_bank_sweep.py` breaks
the strip and watches it go red.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

import nebula.rl.reward_v1 as R
from nebula.common.types import Corner, all_corners
from nebula.experiments.adaptive_screen import CL_MID_F, ScreenPoint, evaluate_at_points
from nebula.experiments.exp_coverage import FREQ_REQUESTS, PEAKING_REQUESTS
from nebula.experiments.exp_tuning_bank import bank
from nebula.rl.contract import design_id, sizing_from_u

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "bank_sweep_results.json"
RUN_LOG = HERE / "bank_sweep_run.jsonl"

#: The geometry entry 70 measured and pre-registered. **Not re-rolled here**:
#: retuning a geometry on the run that measures it is what G110 forbids.
N_RS: int = 8
N_CS: int = 8
RS_SPAN: float = 0.38
CS_SPAN: float = 0.20

#: What every point is scored against. `V6_SPECS` is what `design.py --method
#: auto` screens on, so the number here is comparable with the delivered path's
#: -- see the module docstring for the three ways it is not identical.
SPECS: tuple[str, ...] = R.V6_SPECS

#: The three rows `request_rows` owns. Deleted from every stored margin dict so
#: a value computed against the sweep's placeholder target can never be
#: re-scored against a different request by accident.
REQUEST_ROWS: tuple[str, ...] = ("S3_f_peak_band", "S3_f_peak_match",
                                 "S3_peaking_match")

#: The target handed to `evaluate_at_points`. Any legal value works -- every row
#: it touches is stripped -- but it is named rather than left as a magic number.
PLACEHOLDER_TARGET_HZ: float = 1.9e9
PLACEHOLDER_TARGET_DB: float = 7.5


@dataclass
class SweepRow:
    """One (code, corner) measurement, stored so it can be re-scored freely."""

    i_rs: int
    i_cs: int
    code: int
    corner: str
    ok: bool
    reason: Optional[str] = None
    peaking_db: Optional[float] = None
    f_peak_oct: Optional[float] = None
    #: Every row EXCEPT the three in `REQUEST_ROWS`.
    margins: dict = None
    #: What a real receiver can actually observe. The adaptation policy of row
    #: 4ac may look at these; it may NOT look at `corner`.
    eye_h_v: Optional[float] = None
    eye_w_ui: Optional[float] = None
    power_w: Optional[float] = None
    hd3_nyq_dbc: Optional[float] = None


def _strip_request_rows(margins: dict) -> dict:
    """Drop the three request-dependent rows. **The stale-row gate.**"""
    return {k: float(v) for k, v in (margins or {}).items()
            if k not in REQUEST_ROWS}


def rescore_margins(row: SweepRow, target_f_peak_hz: float,
                    target_peaking_db: float) -> dict:
    """The stored margins plus this request's three rows. Zero SPICE.

    Raises if a request row survived the strip, because that would mean a value
    measured against a different target was about to be scored as if it were
    this one's.
    """
    if not row.ok:
        raise ValueError(f"{row.corner} code {row.code} is unscorable")
    m = dict(row.margins or {})
    stale = [k for k in REQUEST_ROWS if k in m]
    if stale:
        raise KeyError(
            f"{stale} survived _strip_request_rows and would have been scored "
            f"against the wrong target. This is the G115 shape.")
    m.update(R.request_rows(float(row.f_peak_oct), float(row.peaking_db),
                            float(target_f_peak_hz), float(target_peaking_db)))
    missing = [k for k in SPECS if k not in m]
    if missing:
        raise KeyError(f"cannot score {missing}; refusing to report a "
                       f"{len(SPECS) - len(missing)}-row result as {len(SPECS)}")
    return m


def is_compliant(row: SweepRow, target_f_peak_hz: float,
                 target_peaking_db: float) -> bool:
    """Every one of `SPECS`' 13 rows satisfied at this point."""
    if not row.ok:
        return False
    m = rescore_margins(row, target_f_peak_hz, target_peaking_db)
    return all(v == 0.0 for v in R.shortfalls(m, SPECS).values())


def coverage(rows: Sequence[SweepRow], target_f_peak_hz: float,
             target_peaking_db: float) -> dict:
    """For ONE request: is there a code at every mandated corner?"""
    by_corner: dict = {}
    for r in rows:
        by_corner.setdefault(r.corner, []).append(r)
    served, unserved, codes_used, per_corner = 0, [], {}, {}
    for corner, rs in sorted(by_corner.items()):
        good = [r for r in rs
                if is_compliant(r, target_f_peak_hz, target_peaking_db)]
        per_corner[corner] = len(good)
        if good:
            served += 1
            # The code a policy would have to FIND. Recorded per corner because
            # a corner served by exactly one code has no tuning margin left.
            codes_used[corner] = sorted(r.code for r in good)
        else:
            unserved.append(corner)
    return {
        "target_peaking_db": float(target_peaking_db),
        "target_f_peak_hz": float(target_f_peak_hz),
        "n_corners": len(by_corner), "n_served": served,
        "all_corners_served": served == len(by_corner),
        "unserved": unserved,
        "n_codes_per_corner": per_corner,
        "codes_per_corner": codes_used,
        "n_distinct_codes": len({c for cs in codes_used.values() for c in cs}),
        "corners_with_one_code": sorted(k for k, v in per_corner.items()
                                        if v == 1),
    }


def sweep(base_u: Sequence[float], corners: Optional[Sequence[Corner]] = None,
          cl_f: float = CL_MID_F, log: bool = True) -> list:
    """**The only expensive thing here.** 64 codes x 45 corners of real SPICE."""
    settings = bank(base_u, n_rs=N_RS, n_cs=N_CS, rs_span=RS_SPAN,
                    cs_span=CS_SPAN)
    corners = list(corners if corners is not None else all_corners())
    rows: list[SweepRow] = []
    n_sims = 0
    fh = RUN_LOG.open("w", encoding="utf-8") if log else None
    try:
        for n, st in enumerate(settings):
            for c in corners:
                pts = [ScreenPoint(c, cl_f, "bank sweep")]
                ev = evaluate_at_points(
                    st.u, pts, target_f_peak_hz=PLACEHOLDER_TARGET_HZ,
                    target_peaking_db=PLACEHOLDER_TARGET_DB, specs=SPECS)
                n_sims += ev.n_sims
                p = ev.points[0] if ev.points else None
                label = f"{c.process}/{c.vdd_scale:.2f}/{c.temp_c:g}C"
                row = SweepRow(
                    i_rs=st.i_rs, i_cs=st.i_cs, code=n, corner=label,
                    ok=bool(p and p.ok),
                    reason=(None if (p and p.ok) else
                            (p.reason if p else "no point")),
                    peaking_db=(p.peaking_db if p and p.ok else None),
                    f_peak_oct=(p.f_peak_oct if p and p.ok else None),
                    margins=(_strip_request_rows(p.margins) if p and p.ok
                             else {}),
                    eye_h_v=(p.eye_h_v if p and p.ok else None),
                    eye_w_ui=(p.eye_w_ui if p and p.ok else None),
                    power_w=(p.power_w if p and p.ok else None),
                    hd3_nyq_dbc=(p.hd3_nyq_dbc if p and p.ok else None))
                rows.append(row)
                if fh:
                    fh.write(json.dumps(asdict(row)) + "\n")
            print(f"  [{n + 1}/{len(settings)}] code {n} "
                  f"(R{st.i_rs}C{st.i_cs}): {n_sims} decks", flush=True)
    finally:
        if fh:
            fh.close()
    return rows


def run(base_u: Optional[Sequence[float]] = None) -> dict:
    from nebula.experiments.exp_tuning_bank import _base_from_artifacts
    if base_u is None:
        base_u = _base_from_artifacts()
    t0 = time.time()
    did = design_id(sizing_from_u(np.asarray(base_u)))
    print(f"base {did}: {N_RS}x{N_CS} codes over {len(all_corners())} corners",
          flush=True)
    rows = sweep(base_u)
    n_ok = sum(1 for r in rows if r.ok)
    requests = [(pk, f) for pk in PEAKING_REQUESTS for f in FREQ_REQUESTS]
    per_request = [coverage(rows, f, pk) for pk, f in requests]
    n_full = sum(1 for c in per_request if c["all_corners_served"])
    out = {
        "task": "one fixed part + a 6-bit code, over the 16-request grid",
        "base_design_id": did, "base_u": [float(x) for x in base_u],
        "geometry": {"n_rs": N_RS, "n_cs": N_CS, "rs_span": RS_SPAN,
                     "cs_span": CS_SPAN, "n_codes": N_RS * N_CS},
        "spec_set": list(SPECS), "n_spec_rows": len(SPECS),
        "n_rows": len(rows), "n_scorable": n_ok,
        "n_requests": len(requests),
        "n_requests_fully_served": n_full,
        "per_request": per_request,
        "wall_clock_s": time.time() - t0,
        "scope": ("45 mandated PVT corners at the DESIGN LOAD, scored on "
                  "V6_SPECS via adaptive_screen.evaluate_at_points. NOT "
                  "exp_g4_verify.verify_full, NOT the 135-point load grid, and "
                  "S4 is the operating-point row S4_hd3_nyq, which is STRICTER "
                  "than the 100 MHz row the 135-point checklist scores."),
    }
    RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def _report(d: dict) -> None:
    print()
    print("=" * 78)
    print(f"BANK SWEEP - base {d['base_design_id']}, "
          f"{d['geometry']['n_codes']} codes x 45 corners, "
          f"{d['n_rows']} points, {d['wall_clock_s'] / 60:.1f} min")
    print("=" * 78)
    print(f"  scorable {d['n_scorable']}/{d['n_rows']}   "
          f"spec set {d['n_spec_rows']} rows")
    print()
    print("  request              corners served   codes   1-code corners")
    for c in d["per_request"]:
        flag = "  <- ALL 45" if c["all_corners_served"] else ""
        print(f"   {c['target_peaking_db']:5.1f} dB @ "
              f"{c['target_f_peak_hz'] / 1e9:.3f} GHz   "
              f"{c['n_served']:2d}/{c['n_corners']:2d}        "
              f"{c['n_distinct_codes']:3d}     "
              f"{len(c['corners_with_one_code']):3d}{flag}")
    print()
    print(f"  REQUESTS SERVED AT ALL 45 MANDATED CORNERS: "
          f"{d['n_requests_fully_served']} of {d['n_requests']}")


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
