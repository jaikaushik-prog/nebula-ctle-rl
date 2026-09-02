"""
experiments/exp_atten_verify.py — **does the sized attenuator actually clear the
compression entry 72 found? One code at a time, with the G140 correction applied.**

    python -m nebula.experiments.exp_atten_verify --run

WHAT IT MEASURES
-----------------
For every attenuator code, at TT and the design load: the realised attenuation
(as the drop in `g_dc_db`), the compression demand and capability at the
shortest channel, and whether the link becomes scorable at **3 dB** without
losing **12 dB**.

TWO THINGS THIS FILE EXISTS TO GET RIGHT, BOTH OF WHICH BIT ONCE
------------------------------------------------------------------
**1. `vid_max` is scaled by `1 / A` (G140).** `run_point`'s sweep range is
fixed. Attenuate the input and the pair never reaches its own limit inside that
sweep, so the reported "linear limit" collapses in proportion and the ratio
looks constant at ~1.13 whatever you do — which reads as *"input attenuation
cannot work"* and is an artefact of the instrument. Scaled, the limit comes back
constant at ~1110 mVpp, which is what the physics says: the output linear range
belongs to the output node and input attenuation does not touch it.

**2. The switches are REAL PMOS devices** (`switched=True`). Entry 75 measured
the device at the actual 1.5 V common mode and found `Ron*W = 4086.8 ohm.um`.
The three switches are binary-weighted with their resistor legs, so each leg
keeps the designed 1:2:4 conductance ratio. This run must reproduce the earlier
ideal-switch control before the variable block is trusted.

WHAT IT CORRECTS
-----------------
Entry 74 concluded *"5.94 dB is not enough, the requirement is at least
~9.5 dB"*. **That was wrong.** It came from an ad-hoc fixed divider that asked
for 153.1 ohm — a value needing `m = 2` — and emitted it without the
multiplier, realising 306.2 ohm and therefore 3.47 dB where 5.93 dB was
designed. The bank's own legs are all `m = 1` and always realised their design
values; `test_attenuator.py` now gates the multiplier so the same slip cannot
recur.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import time
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from nebula.device import attenuator as AT
from nebula.device import sky130_runner as SR
from nebula.experiments.adaptive_screen import CL_MID_F
from nebula.experiments.exp_tuning_bank import bank
from nebula.link.bridge import device_result_from_point, evaluate_link
from nebula.link.config import LinkConfig
from nebula.rl.contract import sizing_from_u
from nebula.rl.evaluator import build_point

HERE = Path(__file__).resolve().parent
SWITCHLESS_REFERENCE = HERE / "atten_verify_results.json"
RESULTS = HERE / "atten_verify_switched_results.json"

LOSS_SHORT_DB: float = 3.0
LOSS_LONG_DB: float = 12.0
PROBE_CODE: tuple = (4, 3)          # mid boost, mid frequency, from entry 70
N_RS, N_CS, RS_SPAN, CS_SPAN = 8, 8, 0.38, 0.20

_SWING = re.compile(r"output swing ([\d.]+) mVpp exceeds the linear limit "
                    r"([\d.]+)")


def _probe_sizing(base_u: Sequence[float]):
    st = next(s for s in bank(base_u, n_rs=N_RS, n_cs=N_CS, rs_span=RS_SPAN,
                              cs_span=CS_SPAN)
              if (s.i_rs, s.i_cs) == PROBE_CODE)
    return sizing_from_u(np.asarray(st.u), cl_f=CL_MID_F)


def _reproduction(rows: list[dict], reference: dict) -> dict:
    """Fail-capable gate for entry 77's switched-vs-switchless comparison."""
    expected = {None, *range(AT.N_CODES)}
    codes = [r.get("code") for r in rows]
    membership_ok = len(codes) == len(expected) and set(codes) == expected
    all_device_ok = membership_ok and all(r.get("device_ok") for r in rows)
    good = [r for r in rows if r.get("short_ok") and r.get("long_ok")
            and r.get("code") is not None]
    first = min((int(r["code"]) for r in good), default=None)
    long_all_ok = all_device_ok and all(r.get("long_ok") for r in rows)
    limits = [float(r["short_limit_mvpp"]) for r in rows
              if r.get("short_limit_mvpp") is not None]
    limit_min = min(limits) if limits else None
    limit_max = max(limits) if limits else None
    limit_ok = bool(limits and limit_min >= 1105.0 and limit_max <= 1115.0
                    and limit_max - limit_min <= 5.0)

    ref_by = {r.get("code"): r for r in reference.get("rows", [])}
    deltas = []
    if set(ref_by) == expected and membership_ok:
        for row in rows:
            old = ref_by[row["code"]]
            if row.get("device_ok") and old.get("device_ok"):
                deltas.append(abs(float(row["atten_realised_db"])
                                  - float(old["atten_realised_db"])))
    max_delta = max(deltas) if len(deltas) == len(expected) else None
    attenuation_ok = max_delta is not None and max_delta <= 0.25
    passed = bool(all_device_ok and first == 5 and long_all_ok and limit_ok
                  and attenuation_ok)
    return {
        "passed": passed,
        "membership_ok": membership_ok,
        "all_device_ok": all_device_ok,
        "first_clearing_code": first,
        "long_channel_all_ok": long_all_ok,
        "limit_mvpp_min": limit_min,
        "limit_mvpp_max": limit_max,
        "limit_spread_mvpp": (limit_max - limit_min if limits else None),
        "max_abs_attenuation_delta_db": max_delta,
        "limits": {
            "first_clearing_code": 5,
            "limit_window_mvpp": [1105.0, 1115.0],
            "limit_spread_max_mvpp": 5.0,
            "attenuation_delta_max_db": 0.25,
        },
    }


def run(base_u: Optional[Sequence[float]] = None) -> dict:
    from nebula.experiments.exp_tuning_bank import _base_from_artifacts
    if base_u is None:
        base_u = _base_from_artifacts()
    if not SWITCHLESS_REFERENCE.exists():
        raise FileNotFoundError(
            f"switchless reference missing: {SWITCHLESS_REFERENCE}")
    reference = json.loads(SWITCHLESS_REFERENCE.read_text(encoding="utf-8"))
    t0 = time.time()
    pt_spec, _ = build_point(_probe_sizing(base_u), corner="tt", vdd_scale=1.0)
    real_fields = AT.netlist_fields          # captured BEFORE patching
    rows, g0 = [], None
    try:
        for code in [None] + list(range(AT.N_CODES)):
            a = 1.0 if code is None else AT.attenuation(code)
            fields = (real_fields(None) if code is None
                      else real_fields(code, switched=True))
            SR._attenuator.netlist_fields = (lambda f=fields: (lambda c: f))()
            # **G140**: the sweep must still reach the pair's own limit.
            p = SR.run_point(pt_spec, "tt", temp_c=27.0, swing=True,
                             vid_max=0.8 / a, ac_sweep=True, hd3=True,
                             ac_peak_interp=True, atten_code=code)
            if not p.ok:
                rows.append({"code": code, "device_ok": False,
                             "reason": p.fail_reason})
                continue
            dev = device_result_from_point(p)
            if g0 is None:
                g0 = float(dev.g_dc_db)
            row = {"code": code, "device_ok": True,
                   "atten_design_db": (0.0 if code is None
                                       else AT.attenuation_db(code)),
                   "atten_realised_db": g0 - float(dev.g_dc_db),
                   "vid_max_v": 0.8 / a,
                   "noise_mvrms": float(dev.vn_in_vrms or 0.0) * 1e3}
            for name, L in (("short", LOSS_SHORT_DB), ("long", LOSS_LONG_DB)):
                lr = evaluate_link(dev, LinkConfig(channel_loss_db_at_nyquist=L))
                row[f"{name}_ok"] = bool(lr.ok)
                m = _SWING.search(lr.fail_reason or "")
                row[f"{name}_demand_mvpp"] = float(m.group(1)) if m else None
                row[f"{name}_limit_mvpp"] = float(m.group(2)) if m else None
            rows.append(row)
            print(f"  code {str(code):>4}: design "
                  f"{row['atten_design_db']:5.2f} dB  realised "
                  f"{row['atten_realised_db']:5.2f} dB  short_ok="
                  f"{row['short_ok']}  long_ok={row['long_ok']}", flush=True)
    finally:
        SR._attenuator.netlist_fields = real_fields

    good = [r for r in rows if r.get("short_ok") and r.get("long_ok")
            and r.get("code") is not None]
    first = min(good, key=lambda r: r["code"]) if good else None
    lims = [r["short_limit_mvpp"] for r in rows if r.get("short_limit_mvpp")]
    out = {
        "task": "does the sized attenuator clear the compression? (G140 applied)",
        "base_u": [float(x) for x in base_u], "probe_code": list(PROBE_CODE),
        "switched": True,
        "switched_note": ("real binary-weighted pfet_01v8 switches: entry 75 "
                          "measured Ron*W = 4086.8 ohm.um at VCM = 1.5 V; "
                          "gate low is on and bulk is tied to VDD."),
        "rows": rows,
        "first_clearing_code": (first["code"] if first else None),
        "first_clearing_atten_db": (first["atten_design_db"] if first else None),
        "limit_mvpp_min": (min(lims) if lims else None),
        "limit_mvpp_max": (max(lims) if lims else None),
        "noise_mvrms_unattenuated": next(
            (r["noise_mvrms"] for r in rows if r.get("code") is None), None),
        "noise_mvrms_top_code": next(
            (r["noise_mvrms"] for r in rows
             if r.get("code") == AT.N_CODES - 1), None),
        "wall_clock_s": time.time() - t0,
        "scope": "TT only, one load, one bank code. NOT a coverage number.",
    }
    out["switchless_reference"] = SWITCHLESS_REFERENCE.name
    out["reproduction"] = _reproduction(rows, reference)
    RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def _report(d: dict) -> None:
    print()
    print("=" * 78)
    print(f"ATTENUATOR VERIFY - {len(d['rows'])} points, "
          f"{d['wall_clock_s'] / 60:.1f} min   (real PMOS switches)")
    print("=" * 78)
    print("  code  design  realised   demand    limit  ratio   3dB  12dB   noise")
    for r in d["rows"]:
        if not r.get("device_ok"):
            print(f"   {str(r['code']):>4}  device FAIL"); continue
        dem, lim = r["short_demand_mvpp"], r["short_limit_mvpp"]
        ratio = (dem / lim) if dem and lim else float("nan")
        print(f"   {str(r['code']):>4} {r['atten_design_db']:6.2f} "
              f"{r['atten_realised_db']:9.2f} "
              f"{(dem if dem else float('nan')):8.1f} "
              f"{(lim if lim else float('nan')):8.1f} {ratio:6.2f} "
              f"{str(r['short_ok']):>5} {str(r['long_ok']):>5} "
              f"{r['noise_mvrms']:7.4f}")
    print()
    print(f"  FIRST CODE CLEARING 3 dB (and holding 12 dB): "
          f"{d['first_clearing_code']} at {d['first_clearing_atten_db']:.2f} dB")
    print(f"  limit across every code: {d['limit_mvpp_min']:.1f} - "
          f"{d['limit_mvpp_max']:.1f} mVpp  <- constant, so input attenuation")
    print(f"     scales DEMAND alone (entry 73's mechanism, by its converse)")
    print(f"  noise {d['noise_mvrms_unattenuated']:.4f} -> "
          f"{d['noise_mvrms_top_code']:.4f} mVrms at the top code, "
          f"against S5's 1.5 mVrms")
    rep = d.get("reproduction", {})
    print(f"  SWITCHLESS REPRODUCTION GATE: "
          f"{'PASS' if rep.get('passed') else 'FAIL'}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--analyse", action="store_true")
    a = ap.parse_args(argv)
    if a.run:
        result = run()
        _report(result)
        if not result["reproduction"]["passed"]:
            print("  EXIT 1: switched table did not reproduce the switchless "
                  "reference.")
            return 1
    elif a.analyse:
        if not RESULTS.exists():
            raise SystemExit(f"{RESULTS.name} missing: run --run first")
        _report(json.loads(RESULTS.read_text(encoding="utf-8")))
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":                                  # pragma: no cover
    raise SystemExit(main())
