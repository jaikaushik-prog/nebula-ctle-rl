"""
experiments/exp_dfe_ablation.py -- **is the ideal 1-tap DFE load-bearing?**

WHY THIS EXISTS
----------------
The competition spec names the receiver as *"1-Stage CTLE w/ source
degeneration (variable Rs, Cs) + 1-Tap DFE"* and measures the eye rows -- **>
0.4 UI and > 100 mV** -- *after* the DFE. This project models that DFE as an
**ideal tap cancelling the first post-cursor exactly**, flagged
`NON_SILICON_PARAMS` and never sized at transistor level.

A judge is entitled to ask what that assumption is worth. **Sizing a DFE would
not answer it; this does**, by re-deriving the eye of the SHIPPED design at the
same 135 verification points under four tap policies -- ideal, deleted, 20 %
misadapted, 4-bit quantised -- from the same pulse response, at the cost of one
device run per point and no second definition of an eye.

Pre-registered as `PREDICTIONS.md` entry 39.

THE CONTROL IS THE LICENCE
----------------------------
The `ideal` policy must reproduce **the committed per-point `eye_h_v` and
`eye_w_ui` in `joint_verify_full_results.json`**. If it does not, this
experiment is measuring its own arithmetic rather than the DFE, and no other
number in it may be read. That is Q1, and `_verdict` refuses to interpret the
rest when it fails.

    python -m nebula.experiments.exp_dfe_ablation --run
    python -m nebula.experiments.exp_dfe_ablation --analyse
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "dfe_ablation_results.json"
JOINT = HERE / "joint_verify_full_results.json"
SEARCH = HERE / "joint_search_results.json"

#: The spec floors these eyes are judged against, from the competition table.
EYE_H_FLOOR_V: float = 0.100
EYE_W_FLOOR_UI: float = 0.400

#: Entry 39's thresholds.
Q1_MAX_ABS_DIFF_V: float = 1e-9
Q4_MAX_MEDIAN_LOSS_FRAC: float = 0.25


def shipped_design() -> tuple:
    """The joint winner, read from the artifact rather than pasted in."""
    from nebula.rl.contract import design_id, sizing_from_u

    d = json.loads(SEARCH.read_text(encoding="utf-8"))
    u = np.asarray(d["best"]["u"], dtype=float)
    did = design_id(sizing_from_u(u))
    committed = json.loads(JOINT.read_text(encoding="utf-8"))["results"][0]
    if did != committed["design_id"]:
        raise RuntimeError(
            f"the search's best design ({did}) is not the one the compliance "
            f"artifact verified ({committed['design_id']}). Entry 39 ablates "
            f"THE SHIPPED DESIGN; ablating a different one would be a "
            f"different experiment wearing this one's name.")
    return u, committed


def _points_from_artifact(committed: dict) -> list:
    """The exact 135 (corner, vdd, temp, load) points the verification used."""
    return [{"corner": p["corner"], "vdd_scale": float(p["vdd_scale"]),
             "temp_c": float(p["temp_c"]), "cl_f": float(p["cl_f"]),
             "eye_h_v": p.get("eye_h_v"), "eye_w_ui": p.get("eye_w_ui")}
            for p in committed["points"]]


def _design_load_f(points: list) -> float:
    """The DESIGN load: the middle of the three the grid sweeps.

    The 45 mandated corners are this load's subset. Taken as the median of the
    distinct loads rather than a pasted constant, so a change to the grid
    cannot leave this experiment quoting the wrong 45.
    """
    loads = sorted({round(p["cl_f"], 20) for p in points})
    if len(loads) != 3:
        raise RuntimeError(f"expected 3 loads in the grid, got {len(loads)}")
    return float(loads[1])


def ablate_point(u, corner: str, vdd_scale: float, temp_c: float,
                 cl_f: float) -> Optional[dict]:
    """One device run; four eyes. Returns None when the point is unscorable."""
    import nebula.link.dfe_ablation as A
    from nebula.device.sky130_runner import run_point
    from nebula.link.bridge import device_result_from_point, evaluate_link
    from nebula.link.channel import DEFAULT_OSR
    from nebula.link.config import LinkConfig
    from nebula.link.cursors import pulse_response
    from nebula.rl.contract import sizing_from_u

    # **Mirrors `adaptive_screen.evaluate_at_points` call for call** -- the load
    # goes into `sizing_from_u`, VDD into `build_point`, temperature into
    # `run_point`, and the link config carries `FUNNEL_LOSS_DB`. Approximating
    # any one of them would produce an eye that is close to the committed one
    # and not equal to it, and Q1 would fail for the wrong reason.
    from nebula.experiments.exp_g2_closed_loop import FUNNEL_LOSS_DB
    from nebula.rl.evaluator import build_point

    cfg = LinkConfig(channel_loss_db_at_nyquist=FUNNEL_LOSS_DB)
    drive_pk = 0.5 * float(cfg.v_in_diff_pp_v)
    sizing = sizing_from_u(np.asarray(u, dtype=float), cl_f=float(cl_f))
    point, _ = build_point(sizing, corner=corner, vdd_scale=float(vdd_scale))
    pt = run_point(point, corner, temp_c=float(temp_c), swing=True,
                   ac_sweep=True, hd3=True, ac_peak_interp=True,
                   hd3_vin_pk_v=drive_pk, hd3_tone_hz=cfg.nyquist_hz)
    dev = device_result_from_point(pt)
    detail: list = []
    lr = evaluate_link(dev, cfg, detail=detail)
    if not lr.ok or not detail:
        return None

    ctle = detail[0].ctle
    pr = pulse_response(cfg.channel, cfg.tx, ctle)
    cursor = int(np.argmax(pr))
    eyes = A.all_policies(pr, DEFAULT_OSR, cursor)
    return {"corner": corner, "vdd_scale": vdd_scale, "temp_c": temp_c,
            "cl_f": cl_f,
            "bridge_eye_h_v": float(lr.eye_h_v),
            "bridge_eye_w_ui": float(lr.eye_w_ui),
            "dfe_tap": float(lr.dfe_tap),
            "policies": {p: {"eye_h_v": e.eye_h_v, "eye_w_ui": e.eye_w_ui,
                             "h0_v": e.h0_v, "h1_v": e.h1_v,
                             "leftover_v": e.leftover_v}
                         for p, e in eyes.items()}}


def run(limit: Optional[int] = None) -> dict:
    from nebula.experiments.runlock import hold, stamp
    import nebula.link.dfe_ablation as A

    u, committed = shipped_design()
    points = _points_from_artifact(committed)
    if limit:
        points = points[:int(limit)]
    design_load = _design_load_f(points)

    out: dict = {"task": "is the ideal 1-tap DFE load-bearing?", **stamp(),
                 "design_id": committed["design_id"], "u": [float(x) for x in u],
                 "n_points": len(points), "design_load_f": design_load,
                 "eye_h_floor_v": EYE_H_FLOOR_V,
                 "eye_w_floor_ui": EYE_W_FLOOR_UI,
                 "misadapt_eps": A.MISADAPT_EPS, "quant_bits": A.QUANT_BITS,
                 "rows": []}

    with hold("dfe_ablation", meta={"n_points": len(points)}):
        t0 = time.time()
        for i, p in enumerate(points, start=1):
            row = ablate_point(u, p["corner"], p["vdd_scale"], p["temp_c"],
                               p["cl_f"])
            if row is None:
                out["rows"].append({**{k: p[k] for k in
                                       ("corner", "vdd_scale", "temp_c", "cl_f")},
                                    "unscorable": True})
                print(f"  [{i:3d}/{len(points)}] UNSCORABLE", flush=True)
                continue
            row["committed_eye_h_v"] = p["eye_h_v"]
            row["committed_eye_w_ui"] = p["eye_w_ui"]
            out["rows"].append(row)
            if i % 15 == 0 or i == len(points):
                pol = row["policies"]
                print(f"  [{i:3d}/{len(points)}] ideal {pol['ideal']['eye_h_v']*1e3:6.1f} mV"
                      f"  none {pol['none']['eye_h_v']*1e3:6.1f} mV"
                      f"  tap {row['dfe_tap']:+.3f}", flush=True)
        out["wall_s"] = time.time() - t0

    out["verdict"] = _verdict(out)
    RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def _mandated(rows: list, design_load: float) -> list:
    return [r for r in rows if not r.get("unscorable")
            and abs(r["cl_f"] - design_load) < 1e-18]


def _verdict(d: dict) -> dict:
    """Entry 39's decision rule, applied mechanically."""
    rows = [r for r in d["rows"] if not r.get("unscorable")]
    man = _mandated(rows, d["design_load_f"])

    # Q1: the ideal policy must reproduce the COMMITTED eye.
    diffs = [abs(r["policies"]["ideal"]["eye_h_v"] - r["committed_eye_h_v"])
             for r in rows if r.get("committed_eye_h_v") is not None]
    wdiffs = [abs(r["policies"]["ideal"]["eye_w_ui"] - r["committed_eye_w_ui"])
              for r in rows if r.get("committed_eye_w_ui") is not None]
    q1 = bool(diffs) and max(diffs) <= Q1_MAX_ABS_DIFF_V and \
        bool(wdiffs) and max(wdiffs) <= Q1_MAX_ABS_DIFF_V

    def _passes(rs, policy, key, floor):
        return all(r["policies"][policy][key] > floor for r in rs)

    q2 = bool(man) and _passes(man, "none", "eye_h_v", EYE_H_FLOOR_V)
    q3 = bool(man) and _passes(man, "none", "eye_w_ui", EYE_W_FLOOR_UI)
    losses = [1.0 - (r["policies"]["none"]["eye_h_v"] /
                     r["policies"]["ideal"]["eye_h_v"])
              for r in rows if r["policies"]["ideal"]["eye_h_v"] > 0]
    q4 = bool(losses) and float(np.median(losses)) <= Q4_MAX_MEDIAN_LOSS_FRAC
    q5 = bool(man) and _passes(man, "quantised", "eye_h_v", EYE_H_FLOOR_V) \
        and _passes(man, "quantised", "eye_w_ui", EYE_W_FLOOR_UI)

    if not q1:
        call = ("Q1 MISSED -- the `ideal` policy does NOT reproduce the "
                "committed verification. This experiment is measuring its own "
                "arithmetic, not the DFE. Nothing else here may be read.")
    elif q2 and q3:
        call = ("Q2 and Q3 HIT: **the CTLE meets BOTH eye rows at all 45 "
                "mandated corners with the 1-tap DFE REMOVED ENTIRELY.** The "
                "ideal-DFE model is a bounded assumption, not a crutch, and "
                "that sentence belongs in the report with the numbers "
                "attached. Transistor-level DFE sizing stays OUT of scope.")
    elif q2:
        call = ("Q2 hit, Q3 missed: the VERTICAL eye survives deleting the "
                "DFE; the WIDTH does not. Report exactly that and quote the "
                "width both ways. A width that needs the tap argues for "
                "modelling the tap honestly, not for building one.")
    else:
        call = ("Q2 MISSED -- **the ideal-DFE assumption IS load-bearing.** The "
                "report must say so plainly and quote the eye rows with the "
                "assumption attached. Whether to size or derate is the "
                "OWNER's decision. DO NOT adjust the tap model to recover the "
                "number.")
    if not q5:
        call += (" Q5 MISSED: a 4-bit tap is NOT indistinguishable from an "
                 "ideal one -- the eye numbers assume a finer tap, and the "
                 "report must say so.")

    return {"Q1_control_reproduced": bool(q1), "Q2_height_survives": bool(q2),
            "Q3_width_survives": bool(q3), "Q4_loss_small": bool(q4),
            "Q5_quantised_ok": bool(q5),
            "max_ideal_vs_committed_v": (max(diffs) if diffs else None),
            "median_height_loss_frac": (float(np.median(losses)) if losses
                                        else None),
            "n_mandated": len(man), "call": call}


def _report(d: dict) -> None:
    v = d["verdict"]
    rows = [r for r in d["rows"] if not r.get("unscorable")]
    man = _mandated(rows, d["design_load_f"])
    print()
    print("=" * 78)
    print(f"DFE ABLATION -- design {d['design_id']}, {len(rows)} scorable of "
          f"{d['n_points']} points ({len(man)} mandated), {d['wall_s']/60:.1f} min")
    print(f"  floors: eye_h > {d['eye_h_floor_v']*1e3:.0f} mV, "
          f"eye_w > {d['eye_w_floor_ui']} UI")
    print("=" * 78)
    print(f"  {'policy':12s} {'min eye_h mV':>13s} {'min eye_w UI':>13s} "
          f"{'mandated pass':>14s}")
    for p in ("ideal", "none", "misadapted", "quantised"):
        hs = [r["policies"][p]["eye_h_v"] for r in man]
        ws = [r["policies"][p]["eye_w_ui"] for r in man]
        ok = sum(1 for h, w in zip(hs, ws)
                 if h > d["eye_h_floor_v"] and w > d["eye_w_floor_ui"])
        print(f"  {p:12s} {min(hs)*1e3:13.1f} {min(ws):13.4f} "
              f"{ok:>10d}/{len(man)}")
    print()
    print(f"  tap cancels: median {np.median([r['dfe_tap'] for r in rows]):+.4f} "
          f"of the cursor")
    print(f"  Q1 control: max |ideal - committed| = "
          f"{v['max_ideal_vs_committed_v']:.3e} V")
    print(f"  median eye-height loss from deleting the DFE: "
          f"{100*v['median_height_loss_frac']:.1f} %")
    print()
    for k in ("Q1_control_reproduced", "Q2_height_survives",
              "Q3_width_survives", "Q4_loss_small", "Q5_quantised_ok"):
        print(f"  {'HIT ' if v[k] else 'MISS'}  {k}")
    print()
    print(f"  {v['call']}")
    print()
    print("  A re-derivation of the eye under different DFE assumptions from")
    print("  the SAME simulations. No measured spec changes; no DFE is designed.")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--analyse", action="store_true")
    ap.add_argument("--limit", type=int, default=None,
                    help="smoke only: ablate the first N points")
    a = ap.parse_args(argv)
    if a.run:
        _report(run(limit=a.limit))
    elif a.analyse:
        if not RESULTS.exists():
            raise SystemExit(f"{RESULTS.name} missing: run --run first")
        _report(json.loads(RESULTS.read_text(encoding="utf-8")))
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":                                  # pragma: no cover
    raise SystemExit(main())
