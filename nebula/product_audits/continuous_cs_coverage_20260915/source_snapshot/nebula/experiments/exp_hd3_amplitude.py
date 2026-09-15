"""
experiments/exp_hd3_amplitude.py — **S4 has no amplitude in it, the deck picked
one, and the one it picked is not the one the circuit sees.**

THE GAP
-------
`CLAUDEwa.md` §3 states S4 as *"HD3 < -30 dB @ 100 MHz differential input"*.
It names a FREQUENCY and no AMPLITUDE. HD3 on a differential pair goes roughly
as the square of the input drive, so an unstated amplitude makes the number
meaningless — and `sky130_runner.HD3_VIN_DIFF_PK_V` quietly supplies one:
**0.1 V differential peak, i.e. 200 mVpp**, inherited from the G0 prototype.

The link drives this input at **534.7 mVpp** (`LinkConfig.v_in_diff_pp_v`:
PCIe Gen2's 800 mVpp minimum TX swing, less the mandated -3.5 dB de-emphasis,
through a channel with 0 dB loss at DC by construction). **So S4 was verified
at 2.7x below the drive**, and the report quoted 17-19 dB of margin without
ever stating the condition.

THE SECOND GAP, WHICH IS LARGER AND WAS NOT IN THE BRIEF
---------------------------------------------------------
S4's 100 MHz is also the wrong FREQUENCY, and the reason is structural rather
than a matter of taste.

The delivered design's CTLE zero sits at **114.97 MHz** (fitted from the `.ac`
sweep; the design equation `1/(2*pi*Rs*Cs)` gives 114.81 MHz, agreeing to
0.14 %). **S4's tone is at 0.87x the zero** — below it, where `Cs` is still
open and the full `Rs` degeneration is intact. That is the most linear the
stage ever is. By Nyquist the degeneration is shorted out, which is the whole
mechanism of the peaking, and the pair is running un-degenerated.

So this file sweeps HD3 over **amplitude AND frequency**, and the two axes
turn out to cost about the same.

WHY THIS IS AN EXPERIMENT MODULE AND NOT A FIGURE
--------------------------------------------------
`report/figures.py` opens with *"No number in this file is typed by hand. Each
figure loads the JSON a real run wrote."* A first version of this sweep lived
inside `fig_hd3_amplitude` and simulated on demand, caching to a JSON beside
the figures — which makes the figure module a RUN PRODUCER and puts a
simulation behind a plotting call. The run belongs here; the figure loads what
this writes.

    python -m nebula.experiments.exp_hd3_amplitude --run
    python -m nebula.experiments.exp_hd3_amplitude --analyse
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
RESULTS = HERE / "hd3_amplitude_results.json"

#: Differential input amplitudes, mVpp. Spans small-signal to well past the
#: drive so the -30 dBc crossing is bracketed rather than extrapolated to.
AMPLITUDES_MVPP: tuple[int, ...] = (50, 100, 200, 300, 400, 500, 600, 800,
                                    1000, 1200)

#: Tones, Hz. **Each one is a spec landmark, not a round number.**
TONES: tuple[tuple[float, str], ...] = (
    (100e6, "S4's stated tone"),
    (1.25e9, "S3 window, low edge"),
    (2.5e9, "Nyquist - where the data is"),
)


def _delivered_point():
    """The delivered design, read from the run log. Nothing transcribed."""
    import numpy as _np

    from nebula.experiments.cl_range import committed_cl_range
    from nebula.experiments.exp_g4_verify import candidates
    from nebula.rl.contract import sizing_from_u
    from nebula.rl.evaluator import build_point

    win = [c for c in candidates(n_control=0) if c.role == "robust"][0]
    sz = sizing_from_u(_np.asarray(win.u), cl_f=committed_cl_range().cl_mid_f)
    pt, _ = build_point(sz, corner="tt", vdd_scale=1.0)
    return win, pt


def crossing_mvpp(rows: Sequence[dict], limit_dbc: float = -30.0) -> Optional[float]:
    """Input amplitude at which HD3 crosses `limit_dbc`, by log-linear
    interpolation between the bracketing samples.

    `None` when the sweep does not bracket the crossing — which must stay
    `None` rather than becoming an extrapolation off the end of the data.
    """
    v = np.array([r["vin_pp_mv"] for r in rows], dtype=float)
    h = np.array([r["hd3_dbc"] for r in rows], dtype=float)
    o = np.argsort(v)
    v, h = v[o], h[o]
    above = np.flatnonzero(h >= limit_dbc)
    if above.size == 0 or above[0] == 0:
        return None
    i = int(above[0])
    # HD3 in dBc against log(amplitude) is close to a straight line for a
    # cubic nonlinearity (20*log10 of a square law); interpolate there.
    x0, x1 = math.log10(v[i - 1]), math.log10(v[i])
    y0, y1 = h[i - 1], h[i]
    if y1 == y0:
        return float(v[i])
    return float(10.0 ** (x0 + (limit_dbc - y0) * (x1 - x0) / (y1 - y0)))


def run(amplitudes: Sequence[int] = AMPLITUDES_MVPP,
        tones: Sequence[tuple] = TONES) -> dict:
    from nebula.device.sky130_runner import (HD3_TONE_HZ, HD3_VIN_DIFF_PK_V,
                                             run_point)
    from nebula.link.bridge import device_result_from_point
    from nebula.link.config import LinkConfig, PCIE_GEN2_TX_DIFF_PP_MIN_V
    from nebula.experiments.exp_g2_closed_loop import FUNNEL_LOSS_DB

    t0 = time.time()
    win, pt0 = _delivered_point()

    # The pole-zero fit, so the frequency finding has its mechanism attached.
    ref = run_point(pt0, "tt", temp_c=27.0, swing=True, ac_sweep=True, hd3=True)
    if not ref.ok:
        raise RuntimeError(f"reference point failed: {ref.fail_reason}")
    dev = device_result_from_point(ref)

    cfg = LinkConfig(channel_loss_db_at_nyquist=FUNNEL_LOSS_DB)
    drive_mvpp = 1e3 * float(cfg.v_in_diff_pp_v)

    sweeps = []
    for tone_hz, tone_label in tones:
        rows = []
        for pp in amplitudes:
            pt = run_point(pt0, "tt", temp_c=27.0, swing=False, hd3=True,
                           hd3_vin_pk_v=pp / 2e3, hd3_tone_hz=tone_hz)
            if pt.hd3_dbc is None:
                continue
            rows.append({"vin_pp_mv": int(pp), "hd3_dbc": float(pt.hd3_dbc)})
        sweeps.append({
            "tone_hz": float(tone_hz), "tone_label": tone_label,
            "rows": rows,
            "crossing_mvpp": crossing_mvpp(rows),
            "hd3_at_deck_amplitude_dbc": next(
                (r["hd3_dbc"] for r in rows
                 if r["vin_pp_mv"] == int(round(2e3 * HD3_VIN_DIFF_PK_V))), None),
        })

    out = {
        "design_id": win.design_id,
        "corner": "tt/1.00/27C",
        # ── the conditions S4 was actually verified at ──────────────────────
        "deck_tone_hz": float(HD3_TONE_HZ),
        "deck_vin_diff_pk_v": float(HD3_VIN_DIFF_PK_V),
        "deck_vin_pp_mv": 2e3 * float(HD3_VIN_DIFF_PK_V),
        "deck_amplitude_provenance": (
            "sky130_runner.HD3_VIN_DIFF_PK_V, inherited from the G0 prototype. "
            "S4 as written in CLAUDEwa.md sec 3 names a frequency and NO "
            "amplitude, so this is a choice the deck made, not a spec."),
        # ── the conditions the link actually imposes ────────────────────────
        "tx_swing_pp_mv": 1e3 * float(PCIE_GEN2_TX_DIFF_PP_MIN_V),
        "drive_pp_mv": drive_mvpp,
        "drive_provenance": (
            "LinkConfig.v_in_diff_pp_v -- PCIe Gen2 minimum TX swing less the "
            "mandated -3.5 dB de-emphasis, through a channel with 0 dB loss at "
            "DC. POST-CHANNEL, not the raw TX swing."),
        "drive_over_deck_x": drive_mvpp / (2e3 * float(HD3_VIN_DIFF_PK_V)),
        # ── the mechanism ───────────────────────────────────────────────────
        "f_zero_hz": float(dev.f_zero_hz),
        "f_pole1_hz": float(dev.f_pole1_hz),
        "f_pole2_hz": float(dev.f_pole2_hz),
        "fit_residual_db": float(dev.fit_residual_db),
        "deck_tone_over_f_zero": float(HD3_TONE_HZ) / float(dev.f_zero_hz),
        "sweeps": sweeps,
        "n_simulations": sum(len(s["rows"]) for s in sweeps) + 1,
        "wall_clock_s": time.time() - t0,
    }
    RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def _report(d: dict) -> None:
    print(f"design {d['design_id']} at {d['corner']}, "
          f"{d['n_simulations']} simulations")
    print(f"\n  S4 as VERIFIED : {d['deck_vin_pp_mv']:.0f} mVpp at "
          f"{d['deck_tone_hz']/1e6:.0f} MHz")
    print(f"  the link DRIVES: {d['drive_pp_mv']:.0f} mVpp "
          f"({d['drive_over_deck_x']:.2f}x the deck amplitude), "
          f"data at {2.5:.1f} GHz")
    print(f"\n  CTLE zero at {d['f_zero_hz']/1e6:.2f} MHz "
          f"(fit residual {d['fit_residual_db']:.3f} dB) -- S4's tone is "
          f"{d['deck_tone_over_f_zero']:.2f}x the zero,")
    print(f"  i.e. BELOW it, where Cs is still open and the full Rs "
          f"degeneration is intact.")
    print(f"\n  {'amp mVpp':>9s}" + "".join(
        f"{s['tone_hz']/1e9:>11.3f} GHz" for s in d["sweeps"]))
    amps = sorted({r["vin_pp_mv"] for s in d["sweeps"] for r in s["rows"]})
    for a in amps:
        line = f"  {a:9d}"
        for s in d["sweeps"]:
            v = next((r["hd3_dbc"] for r in s["rows"] if r["vin_pp_mv"] == a), None)
            line += f"{v:14.2f}" if v is not None else f"{'-':>14s}"
        mark = ""
        if a == int(round(d["deck_vin_pp_mv"])):
            mark = "   <- S4 verified here"
        print(line + mark)
    print(f"\n  -30 dBc crossing:")
    for s in d["sweeps"]:
        c = s["crossing_mvpp"]
        print(f"    {s['tone_hz']/1e9:7.3f} GHz  "
              + (f"{c:7.0f} mVpp  ({c/d['drive_pp_mv']:.2f}x the drive)"
                 if c else "  not bracketed by the sweep")
              + f"   [{s['tone_label']}]")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--analyse", action="store_true")
    a = ap.parse_args(argv)
    if a.analyse:
        _report(json.loads(RESULTS.read_text(encoding="utf-8")))
        return 0
    if not a.run:
        ap.print_help()
        return 2
    _report(run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
