"""
experiments/exp_gain_axis.py — **the AGC gate: does a switched LOAD rescue the
short channel, or is a separate VGA stage really needed?**

    python -m nebula.experiments.exp_gain_axis --run

WHY A LOAD BANK RATHER THAN A NEW STAGE
-----------------------------------------
Entry 72 measured the stage saturating on every channel shorter than ~9 dB, at
**every** bank code including the lowest-boost one (1.43x over the linear
limit). The conclusion recorded there was that the missing knob is **gain**, not
equalisation, and a real receiver solves that with a VGA/AGC.

A VGA is a new topology block: new devices, new netlist, and every number in
this repository re-verified. Before paying that, there is a much cheaper thing
to try, and the design equations say it should work:

    peaking   ~ 20 log10(1 + (gm + gmbs) Rs / 2)      <- RL does NOT appear
    DC gain   ~ gm RL / (1 + (gm + gmbs) Rs / 2)      <- proportional to RL
    output    ~ I_d * RL                               <- proportional to RL
    pole      = 1 / (2 pi RL CL)                       <- inversely proportional

**`rl` is already an axis of the box** (50-800 ohm, base 254.63 ohm), and the
bank already switches passives. So gain control may be a **third bank axis** —
a switched load resistor — rather than a new stage. That is also how coarse RX
gain is done in real parts.

WHAT THIS FILE MEASURES, AND WHAT IT DELIBERATELY DOES NOT
------------------------------------------------------------
It is a **gate**, not the bank. One corner (TT), one load, three boost codes,
and the `rl` axis swept downward from the base design. The question is binary:

    at 3 dB of channel loss, is there ANY rl setting at which the link
    becomes scorable again?

If yes, the AGC is a third bank axis and the next step is a 3-axis sweep. If no,
the gain knob does not rescue the short channel either and a separate VGA stage
is a real topology decision for the owner.

**Nothing here is a compliance claim.** It is TT-only and it is not the
delivered path, which is untouched: this is the parallel experiment the owner
authorised, and it changes no committed number.

THE TWO NUMBERS IN A REJECTION
--------------------------------
`bridge.py` rejects with *"output swing 1480.0 mVpp exceeds the linear limit
1035.5 mVpp"*. Those are **demand** and **capability**, and they are not
independent of `rl`:

* demand falls with `rl`, because the stage's gain does;
* capability is the measured linear range from the `.dc` sweep, which also
  moves with `rl` through the output operating point.

So the ratio is measured at every step rather than assumed to improve, and the
**flip point** — the largest `rl` at which the link becomes scorable — is the
result.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

import nebula.rl.reward_v1 as R
from nebula.common.types import Corner
from nebula.experiments.adaptive_screen import CL_MID_F, ScreenPoint, evaluate_at_points
from nebula.rl.contract import ACTION_NAMES, ACTION_SPACE, sizing_from_u

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "gain_axis_results.json"

I_RS = ACTION_NAMES.index("rs")
I_CS = ACTION_NAMES.index("cs")
I_RL = ACTION_NAMES.index("rl")

TT = Corner(process="tt", vdd_scale=1.0, temp_c=27.0)

#: The channel entry 72 found impossible, and the one every number in the repo
#: was measured on. Both, so the gate cannot rescue one by breaking the other.
LOSS_SHORT_DB: float = 3.0
LOSS_LONG_DB: float = 12.0

#: Entry 70's geometry, so a code here means the same thing it does there.
N_RS, N_CS, RS_SPAN, CS_SPAN = 8, 8, 0.38, 0.20

#: Low, middle and high boost at mid frequency. Three, not sixty-four: this is
#: a gate and the boost axis is the one the over-drive scaled with (1.43x at R0,
#: 1.86x at R7).
PROBE_CODES: tuple[tuple[int, int], ...] = ((0, 3), (4, 3), (7, 3))

#: `rl` swept DOWNWARD from the base. Entry 72 measured the over-drive at
#: 1.43-1.86x, so a 30-50 % gain cut is the range of interest; -0.45 in
#: normalised box units reaches well past it on a log-scaled axis.
RL_STEPS: int = 10
RL_DROP: float = 0.45

_SWING = re.compile(r"output swing ([\d.]+) mVpp exceeds the linear limit "
                    r"([\d.]+)")


def _base() -> list:
    from nebula.experiments.exp_tuning_bank import _base_from_artifacts
    return _base_from_artifacts()


def _code_u(base_u: Sequence[float], i_rs: int, i_cs: int) -> np.ndarray:
    """The entry-70 bank code, as a sizing. `rl` untouched here."""
    from nebula.experiments.exp_tuning_bank import bank
    for st in bank(base_u, n_rs=N_RS, n_cs=N_CS, rs_span=RS_SPAN,
                   cs_span=CS_SPAN):
        if (st.i_rs, st.i_cs) == (i_rs, i_cs):
            return np.asarray(st.u, dtype=float)
    raise KeyError(f"no bank code R{i_rs}C{i_cs}")


def probe(base_u: Sequence[float]) -> list:
    rl_dim = ACTION_SPACE[I_RL]
    rows = []
    for i_rs, i_cs in PROBE_CODES:
        u0 = _code_u(base_u, i_rs, i_cs)
        for k in range(RL_STEPS):
            frac = k / (RL_STEPS - 1)
            u = u0.copy()
            u[I_RL] = float(np.clip(u0[I_RL] - RL_DROP * frac, 0.0, 1.0))
            ev = evaluate_at_points(
                tuple(u), [ScreenPoint(TT, CL_MID_F, "gain-axis gate")],
                target_f_peak_hz=1.9e9, target_peaking_db=7.5,
                specs=R.V6_SPECS,
                link_losses_db=[LOSS_SHORT_DB, LOSS_LONG_DB])
            p = ev.points[0] if ev.points else None
            row = {
                "i_rs": i_rs, "i_cs": i_cs, "step": k,
                "u_rl": float(u[I_RL]),
                "rl_ohm": float(rl_dim.to_physical(u[I_RL])),
                "rl_frac_of_base": float(
                    rl_dim.to_physical(u[I_RL]) / rl_dim.to_physical(u0[I_RL])),
                "device_ok": bool(p and p.ok),
                "peaking_db": (p.peaking_db if p and p.ok else None),
                "f_peak_ghz": ((2.5 * 2.0 ** p.f_peak_oct) if p and p.ok
                               else None),
            }
            for name, L in (("short", LOSS_SHORT_DB), ("long", LOSS_LONG_DB)):
                e = ((p.links_by_loss or {}).get(float(L)) if p and p.ok
                     else None) or {}
                row[f"{name}_ok"] = bool(e.get("ok"))
                row[f"{name}_eye_h_v"] = e.get("eye_h_v")
                m = _SWING.search(e.get("reason") or "")
                row[f"{name}_demand_mvpp"] = float(m.group(1)) if m else None
                row[f"{name}_limit_mvpp"] = float(m.group(2)) if m else None
            rows.append(row)
            print(f"  R{i_rs}C{i_cs} step {k}: rl {row['rl_ohm']:6.1f} ohm "
                  f"({row['rl_frac_of_base']:.2f}x)  short_ok={row['short_ok']}"
                  f"  long_ok={row['long_ok']}  pk="
                  f"{(row['peaking_db'] or float('nan')):.2f} dB", flush=True)
    return rows


def analyse(rows: Sequence[dict]) -> dict:
    out = {}
    for i_rs, i_cs in PROBE_CODES:
        rs = [r for r in rows if (r["i_rs"], r["i_cs"]) == (i_rs, i_cs)]
        good = [r for r in rs if r["short_ok"]]
        # The FLIP POINT: the largest rl (least gain reduction) that works.
        flip = max(good, key=lambda r: r["rl_ohm"]) if good else None
        pk = [r["peaking_db"] for r in rs if r["peaking_db"] is not None]
        fp = [r["f_peak_ghz"] for r in rs if r["f_peak_ghz"] is not None]
        out[f"R{i_rs}C{i_cs}"] = {
            "rescued": bool(good),
            "flip_rl_ohm": (flip["rl_ohm"] if flip else None),
            "flip_frac_of_base": (flip["flip_frac"] if flip and
                                  "flip_frac" in flip
                                  else (flip["rl_frac_of_base"] if flip
                                        else None)),
            "n_short_ok": len(good),
            "still_long_ok_at_flip": (flip["long_ok"] if flip else None),
            "peaking_span_db": (max(pk) - min(pk)) if pk else None,
            "f_peak_span_ghz": ([min(fp), max(fp)] if fp else None),
        }
    resc = [v for v in out.values() if v["rescued"]]
    return {
        "per_code": out,
        "n_rescued": len(resc),
        "n_codes": len(PROBE_CODES),
        "max_peaking_span_db": max(
            (v["peaking_span_db"] or 0.0) for v in out.values()),
    }


def run() -> dict:
    t0 = time.time()
    base_u = _base()
    print(f"gain-axis gate: {len(PROBE_CODES)} codes x {RL_STEPS} rl steps "
          f"at TT, channels {LOSS_SHORT_DB} and {LOSS_LONG_DB} dB", flush=True)
    rows = probe(base_u)
    out = {
        "task": "does a switched LOAD rescue the short channel entry 72 broke on?",
        "base_u": [float(x) for x in base_u],
        "corner": "tt/1.00/27C", "loss_short_db": LOSS_SHORT_DB,
        "loss_long_db": LOSS_LONG_DB,
        "probe_codes": [list(c) for c in PROBE_CODES],
        "rl_steps": RL_STEPS, "rl_drop_box": RL_DROP,
        "rows": rows, "analysis": analyse(rows),
        "wall_clock_s": time.time() - t0,
        "scope": ("TT only, one load, three codes. A GATE, not a compliance "
                  "claim. The delivered path is untouched."),
    }
    RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def _report(d: dict) -> None:
    a = d["analysis"]
    print()
    print("=" * 78)
    print(f"GAIN-AXIS GATE - {len(d['rows'])} points, "
          f"{d['wall_clock_s'] / 60:.1f} min")
    print("=" * 78)
    print(f"  code    rescued at 3 dB?   flip rl      x base   long still ok")
    for k, v in a["per_code"].items():
        print(f"   {k:<6}  {str(v['rescued']):<16} "
              f"{(v['flip_rl_ohm'] or 0):6.1f} ohm  "
              f"{(v['flip_frac_of_base'] or 0):5.2f}x   "
              f"{v['still_long_ok_at_flip']}")
    print()
    print(f"  codes rescued: {a['n_rescued']} of {a['n_codes']}")
    print(f"  largest peaking drift across the rl sweep: "
          f"{a['max_peaking_span_db']:.2f} dB  (axes separable if small)")


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
