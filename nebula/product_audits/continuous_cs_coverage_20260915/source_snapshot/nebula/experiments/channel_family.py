"""
experiments/channel_family.py — the channel family, its gates, the cursor
table, and the compression verdict that the deleted DC-loss constant used to
decide.

    python -m nebula.experiments.channel_family                # no simulator
    python -m nebula.experiments.channel_family --compression  # + ngspice
    python -m nebula.experiments.channel_family --report       # from the CSV

Stages
------
`--gates`        causality and passivity, REPORTED per family member (5b/5f).
`--cursors`      the headline table: h_-2..h_4 normalised to h0, residual ISI
                 after an ideal 1-tap DFE, and the vertical eye — channel-only
                 and channel+CTLE, at each of the three de-emphasis settings
                 (5d/5e).
`--reflections`  how much the stated two-echo probe moves the cursor set (5h).
`--compression`  re-runs the matched-boost compression analysis against the new
                 channel + transmitter, on ngspice, and replaces the "1.22x at
                 3 dB" reading (5g). **This is the only stage that needs a
                 simulator.**

Everything except `--compression` is pure numpy and runs in a few seconds, so
the default is all three of the others.

THE CONSISTENCY GATE, AND IT IS NOT DECORATION
-----------------------------------------------
`--compression` reproduces the published reference device before it analyses
anything: `w=40 nf=4 l=0.15 I=1.5 mA/side VCM=1.25 RL=400`, which must give
gm = 12.62 mS, gm/I_D = 8.42, v(source) = +0.343 V, A_dc = 5.05 dB and a 1 dB
compression swing of 1427 mVpp (HANDOFF §6, `BOUNDS_REDERIVATION.md` §1). If
those do not reproduce, the run ABORTS rather than reporting a comparison
against a different device than the one whose verdict it is replacing. Same
shape as G52.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from nebula.common import design_equations as deq
from nebula.common.types import (
    NYQUIST_HZ,
    SPEC_EYE_H_MIN_V,
    SPEC_F_PEAK_HZ_RANGE,
    SPEC_PEAKING_DB_RANGE,
)
from nebula.link.channel import (
    CAUSALITY_ENERGY_THRESHOLD,
    DEFAULT_N_FFT,
    DEFAULT_OSR,
    FAMILY_IL_DB,
    FAMILY_SKIN_FRACTIONS,
    FR4_MICROSTRIP,
    STATED_REFLECTION_PROBE,
    ChannelModel,
    channel_family,
)
from nebula.link.cursors import (
    DEFAULT_F_POLE2_HZ,
    REPORTED_TAPS,
    MatchedCtle,
    extract_cursors,
    eye_estimate,
    matched_ctle,
    pulse_response,
)
from nebula.link.tx import DE_EMPHASIS_SETTINGS_DB, TxDeEmphasis

HERE = Path(__file__).resolve().parent
DATA_CSV = HERE / "channel_family_data.csv"
RESULTS_JSON = HERE / "channel_family_results.json"

# ─────────────────────────────────────────────────────────────────────────────
# The published reference device, and the numbers it must reproduce.
# ─────────────────────────────────────────────────────────────────────────────

REFERENCE_DEVICE = dict(w=40.0, l=0.15, nf=4, rl=400.0, cl=100e-15,
                        i_tail_per_side_a=1.5e-3, vcm=1.25, vdd=1.8)

#: (name, expected, absolute tolerance). Every one is a PUBLISHED number.
REFERENCE_CHECKS = (
    ("gm_mS", 12.62, 0.05),
    ("gm_over_id", 8.42, 0.05),
    ("v_src_dc_V", 0.343, 0.005),
    ("g_dc_dB", 5.05, 0.05),
    ("swing_1db_mVpp", 1427.0, 3.0),
)

#: The (rs, cs) grid the compression sweep visits. Contains the four rs and two
#: cs values `BOUNDS_REDERIVATION.md` §2's own table reports, so its rows are
#: findable in this one.
RS_GRID = (100.0, 150.0, 200.0, 250.0, 300.0, 400.0, 500.0, 600.0, 800.0,
           1000.0, 1500.0)
CS_GRID = (0.2e-12, 0.4e-12, 0.8e-12, 1.6e-12, 3.2e-12, 6.4e-12)

#: Reference point inside that grid used for the reproduction gate. Session 9c
#: published "Rs=200, Cs=1.6p, RL=400, CL=100f -> 4.63 dB at 1.95 GHz".
GATE_SETTING = (200.0, 1.6e-12)


# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — the gates, reported per member
# ─────────────────────────────────────────────────────────────────────────────


def run_gates(verbose: bool = True) -> list[dict]:
    rows = []
    for ch in channel_family():
        caus = ch.causality_report()
        pas = ch.passivity_report()
        el = ch.equivalent_length(FR4_MICROSTRIP)
        rows.append(dict(
            il_db=ch.il_db_at_nyquist, skin_fraction=ch.skin_fraction,
            split=ch.split_name,
            a_db_per_sqrt_ghz=ch.a_db_per_sqrt_ghz, b_db_per_ghz=ch.b_db_per_ghz,
            il_at_nyquist_check_db=float(ch.il_db(NYQUIST_HZ)),
            il_error_db=float(ch.il_db(NYQUIST_HZ)) - ch.il_db_at_nyquist,
            il_at_dc_db=ch.il_db_at_dc,
            pre_t0_energy=caus.pre_energy_fraction,
            pre_t0_energy_db=caus.pre_energy_db,
            causal=caus.passes,
            max_magnitude=pas.max_magnitude,
            worst_monotonicity=pas.worst_monotonicity_violation,
            passive=pas.passes,
            len_total_inch=el.from_total_inch,
            len_skin_m=el.from_skin_m, len_diel_m=el.from_dielectric_m,
            length_self_consistent=el.self_consistent,
        ))
    if verbose:
        print("\n=== 1. GATES (5b, 5f) — reported per member, not just asserted ===")
        print(f"  osr = {DEFAULT_OSR} samples/UI, n_fft = {DEFAULT_N_FFT} "
              f"({DEFAULT_N_FFT // DEFAULT_OSR} UI), "
              f"causality threshold = {CAUSALITY_ENERGY_THRESHOLD:.0e}")
        print(f"  stackup for lengths: {FR4_MICROSTRIP.name}, "
              f"natural skin fraction at 2.5 GHz = "
              f"{FR4_MICROSTRIP.natural_skin_fraction(NYQUIST_HZ):.3f}")
        print()
        print("   IL   split                 A        B   IL err     pre-t<0    max|H|"
              "   len(in)  self-consistent")
        for r in rows:
            print(f"  {r['il_db']:4.1f}  {r['split']:<20s} "
                  f"{r['a_db_per_sqrt_ghz']:5.2f} {r['b_db_per_ghz']:8.4f} "
                  f"{r['il_error_db']:+8.1e}  {r['pre_t0_energy']:9.2e} "
                  f"{r['max_magnitude']:8.4f} {r['len_total_inch']:8.2f}"
                  f"   {'yes' if r['length_self_consistent'] else 'no'}")
        bad = [r for r in rows if not (r["causal"] and r["passive"])]
        print(f"\n  causal AND passive: {len(rows) - len(bad)}/{len(rows)}"
              + (f"   FAILURES: {bad}" if bad else ""))
        worst = max(rows, key=lambda r: r["pre_t0_energy"])
        print(f"  worst pre-t<0 energy: {worst['pre_t0_energy']:.2e} "
              f"({worst['pre_t0_energy_db']:.1f} dB) at IL {worst['il_db']} dB, "
              f"{worst['split']}")
        # The control: the same magnitude with zero phase, which is what a
        # magnitude-only channel model gives you.
        ctrl = ChannelModel(12.0, 0.8)
        from nebula.link.channel import causality_of
        z = causality_of(ctrl.zero_phase_impulse_response(), DEFAULT_OSR)
        print(f"  CONTROL — same channel, magnitude only, zero phase: "
              f"{z.pre_energy_fraction:.3f} of the energy at t < 0 "
              f"({z.pre_energy_db:+.1f} dB). That is the error this gate exists "
              f"to catch, and it raises nothing on its own.")
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — the cursor table
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class CursorRow:
    il_db: float
    skin_fraction: float
    split: str
    de_emphasis_db: float
    ctle: str                 # "none" or "matched"
    ctle_boost_db: float      # nan when no CTLE
    burden_db: float
    h0_mv: float
    dfe_tap: float
    precursor_frac: float
    postcursor_tail_frac: float
    residual_frac: float
    eye_open: bool
    eye_h_mv: float
    required_dc_gain: float
    taps: dict


def _row(ch: ChannelModel, tx: TxDeEmphasis, ctle: Optional[MatchedCtle],
         label: str) -> CursorRow:
    cs = extract_cursors(ch, tx, ctle=ctle)
    est = eye_estimate(cs)
    return CursorRow(
        il_db=ch.il_db_at_nyquist, skin_fraction=ch.skin_fraction,
        split=ch.split_name, de_emphasis_db=tx.de_emphasis_db, ctle=label,
        ctle_boost_db=(ctle.target_boost_db if ctle else float("nan")),
        burden_db=tx.burden_db(ch.il_db_at_nyquist),
        h0_mv=cs.h0_v * 1e3, dfe_tap=cs.dfe_tap,
        precursor_frac=cs.precursor_abs_v / cs.h0_v,
        postcursor_tail_frac=cs.postcursor_residual_abs_v / cs.h0_v,
        residual_frac=cs.residual_fraction, eye_open=cs.eye_open,
        eye_h_mv=cs.eye_h_v * 1e3, required_dc_gain=est.required_dc_gain,
        taps={k: cs.normalised(k) for k in REPORTED_TAPS},
    )


def run_cursors(verbose: bool = True) -> list[CursorRow]:
    """The headline table: every family member, every de-emphasis setting,
    with and without a matched CTLE in front."""
    rows: list[CursorRow] = []
    for ch in channel_family():
        for de in DE_EMPHASIS_SETTINGS_DB:
            tx = TxDeEmphasis(de)
            rows.append(_row(ch, tx, None, "none"))
            burden = tx.burden_db(ch.il_db_at_nyquist)
            if burden > 0.0:
                rows.append(_row(ch, tx, matched_ctle(burden), "matched"))
    if verbose:
        _print_cursor_tables(rows)
    return rows


def _print_cursor_tables(rows: list[CursorRow]) -> None:
    print("\n=== 2. CURSORS AND RESIDUAL ISI (5e) — THE HEADLINE TABLE ===")
    print(f"  UI = 200 ps; {DEFAULT_OSR} samples/UI internally; sampling phase "
          f"chosen to maximise h0.")
    print(f"  residual = (sum|h_k|, k<0) + (sum|h_k|, k>=2), over the whole "
          f"{DEFAULT_N_FFT // DEFAULT_OSR} UI buffer, / h0.")
    print("  An ideal 1-tap DFE cancels h1 exactly and nothing else.")
    print("  residual >= 1.00 => EYE CLOSED, and no amount of gain reopens it.")
    print("  CTLE is normalised to UNITY DC GAIN: shape only, no raw gain.")

    for de in DE_EMPHASIS_SETTINGS_DB:
        tag = "no de-emphasis" if de == 0.0 else f"{de:+.1f} dB de-emphasis"
        print(f"\n  --- TX {tag} " + "-" * 40)
        print("   IL  split         eq   CTLE     h-2     h-1      h1      h2"
              "      h3      h4   resid    eye     open")
        for r in rows:
            if r.de_emphasis_db != de:
                continue
            t = r.taps
            print(f"  {r.il_db:4.1f} {r.split[:5]:<5s} {r.burden_db:+6.1f} "
                  f"{r.ctle:>7s} {t[-2]:+7.4f} {t[-1]:+7.4f} {t[1]:+7.4f} "
                  f"{t[2]:+7.4f} {t[3]:+7.4f} {t[4]:+7.4f} {r.residual_frac:7.4f} "
                  f"{r.eye_h_mv:7.1f} {'Y' if r.eye_open else 'N':>4s}")

    # --- the decisive answer ------------------------------------------------
    print("\n  --- IS A 1-TAP DFE ENOUGH? ---")
    closed = [r for r in rows if not r.eye_open]
    if closed:
        first = min(closed, key=lambda r: r.il_db)
        print(f"  EYE CLOSES somewhere: first at IL {first.il_db} dB, "
              f"{first.split}, {first.ctle} CTLE, "
              f"de-emphasis {first.de_emphasis_db:+.1f} dB")
    else:
        worst = max(rows, key=lambda r: r.residual_frac)
        print(f"  The eye is OPEN at every point of the family, in every "
              f"configuration. Worst residual {worst.residual_frac:.4f} at "
              f"IL {worst.il_db} dB, {worst.split}, {worst.ctle} CTLE, "
              f"de-emphasis {worst.de_emphasis_db:+.1f} dB.")
        print(f"  So a 1-tap DFE is SUFFICIENT to keep the eye open across "
              f"3-12 dB. What it is not sufficient for is S8's 100 mV floor "
              f"without gain — see the required-DC-gain column below.")

    print("\n  --- S8 (100 mV vertical): DC gain the CTLE must then supply ---")
    print("   IL  split          burden  boost   eye@unity  needs A_dc  = dB")
    for r in rows:
        if r.de_emphasis_db != DE_EMPHASIS_SETTINGS_DB[1] or r.ctle != "matched":
            continue
        g = r.required_dc_gain
        print(f"  {r.il_db:4.1f} {r.split:<20s} {r.burden_db:+6.1f} "
              f"{r.ctle_boost_db:6.2f} {r.eye_h_mv:10.1f} {g:11.3f} "
              f"{20 * math.log10(g) if math.isfinite(g) else float('inf'):6.2f}")

    print("\n  --- 5d: what the mandated de-emphasis is worth ---")
    for de in DE_EMPHASIS_SETTINGS_DB:
        tx = TxDeEmphasis(de)
        print(f"  de-emphasis {de:+5.1f} dB -> TX supplies {tx.tilt_db:.3f} dB "
              f"of tilt, exactly; CTLE burden over the family = "
              f"{tx.burden_db(min(FAMILY_IL_DB)):+.1f} .. "
              f"{tx.burden_db(max(FAMILY_IL_DB)):+.1f} dB")
    lo, hi = SPEC_PEAKING_DB_RANGE
    tx = TxDeEmphasis(DE_EMPHASIS_SETTINGS_DB[1])
    below = [il for il in FAMILY_IL_DB if tx.burden_db(il) < lo]
    print(f"  S3's tunable range is {lo}-{hi} dB. With the Gen2 mandate the "
          f"burden never exceeds {tx.burden_db(max(FAMILY_IL_DB)):.1f} dB, so "
          f"the TOP {hi - tx.burden_db(max(FAMILY_IL_DB)):.1f} dB of S3 is "
          f"never called for on this family;")
    print(f"  and at IL in {below} dB the burden is BELOW S3's {lo} dB floor, "
          f"i.e. the CTLE's minimum setting over-equalises.")


# ─────────────────────────────────────────────────────────────────────────────
# Stage 3 — reflections (5h)
# ─────────────────────────────────────────────────────────────────────────────


def run_reflections(verbose: bool = True) -> list[dict]:
    rows = []
    tx = TxDeEmphasis(DE_EMPHASIS_SETTINGS_DB[1])
    for ch in channel_family():
        base = extract_cursors(ch, tx)
        refl = extract_cursors(ch.with_reflections(), tx)
        rows.append(dict(
            il_db=ch.il_db_at_nyquist, split=ch.split_name,
            residual_smooth=base.residual_fraction,
            residual_with_reflections=refl.residual_fraction,
            delta=refl.residual_fraction - base.residual_fraction,
            h2_smooth=base.normalised(2), h2_reflections=refl.normalised(2),
            eye_smooth_mv=base.eye_h_v * 1e3, eye_reflections_mv=refl.eye_h_v * 1e3,
        ))
    if verbose:
        print("\n=== 3. REFLECTIONS (5h) — the declared omission, measured ===")
        print("  A smooth A*sqrt(f) + B*f form has NO impedance discontinuities.")
        print("  Real channels have connectors and vias, and reflections are the")
        print("  ISI a DFE handles worst: they arrive many UI out, where a 1-tap")
        print("  DFE cannot reach, and they do not decay monotonically.")
        print("  STATED probe, not measured: "
              + ", ".join(f"rho={r.rho} at {r.delay_ui:g} UI"
                          for r in STATED_REFLECTION_PROBE))
        print("\n   IL  split                 smooth   +refl    delta      h2 ->"
              "      h2     eye ->    eye")
        for r in rows:
            print(f"  {r['il_db']:4.1f} {r['split']:<20s} "
                  f"{r['residual_smooth']:7.4f} {r['residual_with_reflections']:7.4f} "
                  f"{r['delta']:+8.4f} {r['h2_smooth']:+8.4f} "
                  f"{r['h2_reflections']:+8.4f} {r['eye_smooth_mv']:8.1f} "
                  f"{r['eye_reflections_mv']:8.1f}")
        d = [r["delta"] for r in rows]
        print(f"\n  residual delta: {min(d):+.4f} .. {max(d):+.4f} "
              f"(median {float(np.median(d)):+.4f})")
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Stage 4 — the compression re-run (5g). NEEDS NGSPICE.
# ─────────────────────────────────────────────────────────────────────────────


#: §5.3b: a pole-zero model that misses the measured response by more than
#: this is garbage and must be rejected rather than passed downstream.
FIT_REJECT_PEAKING_DB: float = 0.5

#: How far the model's peak frequency may sit from the measured one. Session 11
#: measured `meas ac MAX` as quantised at 0.0664 octaves (4.7%) on an
#: `ac dec 50` grid, so anything at or below ~10% is the sweep setup rather
#: than the model.
FIT_REJECT_F_PEAK_RATIO: float = 0.15


def calibrated_ctle_model(rs: float, cs: float, rl: float, cl: float,
                          g_dc_linear: float, nyquist_boost_db: float
                          ) -> deq.SmallSignal:
    """A 1-zero/2-pole model tied to the MEASURED response, not predicted from §6.

    WHY THIS IS NOT `deq.predict(...)`. Measured on this very sweep, the §6
    equations over-predict the Nyquist boost by **+0.79 to +1.57 dB**, growing
    with `rs` — they neglect `r_o`, so the degeneration factor `k` comes out too
    large. Convention C below integrates the whole pulse response through this
    model, so a 1.5 dB error in the boost is a 1.5 dB error in the output swing
    it demands, and the compression verdict would inherit it.

    Two of the three time constants are set by PASSIVES and are exact:

        f_z  = 1 / (2*pi*Rs*Cs)          f_p2 = 1 / (2*pi*RL*CL)

    so only the degeneration factor `k = f_p1/f_z` is fitted, from ONE measured
    number (the boost at Nyquist), and `g_dc` is taken from the measurement
    directly. The peaking and the peak frequency are then **independent**
    checks — the caller gates on them.
    """
    from scipy.optimize import brentq

    f_z = 1.0 / (2.0 * math.pi * rs * cs)
    f_p2 = 1.0 / (2.0 * math.pi * rl * cl)

    def boost(k: float) -> float:
        probe = deq.SmallSignal(g_dc=1.0, f_zero_hz=f_z, f_pole1_hz=k * f_z,
                                f_pole2_hz=f_p2, peaking_db=0.0)
        return deq.transfer_db(NYQUIST_HZ, probe)

    k = brentq(lambda k: boost(k) - nyquist_boost_db, 1.0 + 1e-9, 1e4, xtol=1e-12)
    return deq.SmallSignal(g_dc=g_dc_linear, f_zero_hz=f_z, f_pole1_hz=k * f_z,
                           f_pole2_hz=f_p2, peaking_db=20.0 * math.log10(k))


def _peak_distortion_output_pp_v(ch: ChannelModel, tx: TxDeEmphasis,
                                 ss: deq.SmallSignal) -> float:
    """The output swing the stage ACTUALLY has to produce, differential Vpp.

    Peak-distortion analysis: the worst data pattern puts every UI-spaced
    sample of the pulse response on the same side, so the largest excursion at
    sampling phase `t` is `sum_k |pr(t + k*T)|`, and the peak-to-peak swing is
    twice its maximum over `t`.

    This supersedes BOTH earlier conventions. Session 9c used "Nyquist content
    in, Nyquist gain out"; `calibration.py` C3 used "long-run level in, peak
    gain out". Each is a proxy for a worst-case pattern; with a real pulse
    response the worst-case pattern can simply be computed.
    """
    ctle = MatchedCtle(ss=ss, target_boost_db=1.0, f_peak_hz=NYQUIST_HZ,
                       f_pole2_hz=ss.f_pole2_hz, realised_peaking_db=0.0,
                       realised_f_peak_hz=NYQUIST_HZ)
    pr = pulse_response(ch, tx, ctle=ctle)
    osr = DEFAULT_OSR
    folded = np.abs(pr).reshape(-1, osr).sum(axis=0)
    return 2.0 * float(folded.max())


def run_compression(verbose: bool = True) -> dict:
    from nebula.device.sky130_runner import SizingPoint, run_point

    print("\n=== 4. COMPRESSION, RE-RUN AGAINST THE DERIVED CHANNEL (5g) ===")
    print("  Replaces BOUNDS_REDERIVATION.md §2's matched-boost table, whose")
    print("  own blockquote says a made-up constant decided the verdict.")

    # --- the reproduction gate ------------------------------------------
    rs0, cs0 = GATE_SETTING
    gate_pt = SizingPoint(rs=rs0, cs=cs0, **REFERENCE_DEVICE)
    g = run_point(gate_pt, "tt")
    if not g.ok:
        raise RuntimeError(f"reference device did not simulate: {g.fail_reason}")
    sw = g.swing()
    measured = dict(gm_mS=g.gm * 1e3, gm_over_id=g.gm_over_id,
                    v_src_dc_V=g.v_src_dc, g_dc_dB=g.g_dc_db,
                    swing_1db_mVpp=(sw.linear_pp_v * 1e3
                                    if sw.linear_pp_v is not None else float("nan")))
    print("\n  reproduction gate (published reference device):")
    failures = []
    for name, expect, tol in REFERENCE_CHECKS:
        got = measured[name]
        ok = math.isfinite(got) and abs(got - expect) <= tol
        print(f"    {name:<16s} expected {expect:9.3f}  measured {got:9.3f}  "
              f"{'ok' if ok else 'MISMATCH'}")
        if not ok:
            failures.append(name)
    if failures:
        raise RuntimeError(
            f"the reference device does NOT reproduce its published numbers "
            f"({failures}). Aborting rather than replacing a verdict with a "
            f"comparison against a different device."
        )

    # --- sweep (rs, cs) --------------------------------------------------
    t0 = time.perf_counter()
    settings = []
    for rs in RS_GRID:
        for cs in CS_GRID:
            pt = SizingPoint(rs=rs, cs=cs, **REFERENCE_DEVICE)
            r = run_point(pt, "tt")
            if not r.ok:
                continue
            lo_pk, hi_pk = SPEC_PEAKING_DB_RANGE
            lo_f, hi_f = SPEC_F_PEAK_HZ_RANGE
            meets = (r.has_interior_peak
                     and lo_pk <= r.peaking_db <= hi_pk
                     and lo_f <= r.f_pk_hz <= hi_f)
            if not meets:
                continue
            swing = r.swing().linear_pp_v
            if swing is None:
                continue
            # §6 as written, kept as an INFORMATIONAL number: it neglects r_o
            # and is measurably optimistic here, which is why it is not what
            # convention C runs on.
            _, s6_delta = deq.cross_check_extraction(
                r.g_dc_linear, gm=r.gm, rs=rs, rl=REFERENCE_DEVICE["rl"],
                gmbs=r.gmbs)
            predicted = deq.predict(gm=r.gm, rs=rs, cs=cs,
                                    rl=REFERENCE_DEVICE["rl"],
                                    cl=REFERENCE_DEVICE["cl"], gmbs=r.gmbs)
            pred_boost = (deq.transfer_db(NYQUIST_HZ, predicted)
                          - 20.0 * math.log10(predicted.g_dc))

            # The model the pulse response actually runs through: tied to the
            # measurement, with the peaking and peak frequency left as
            # independent checks.
            ss = calibrated_ctle_model(rs, cs, REFERENCE_DEVICE["rl"],
                                       REFERENCE_DEVICE["cl"], r.g_dc_linear,
                                       r.nyquist_boost_db)
            fit_pk, fit_fpk = deq.realised_peaking_db(ss, 40000)
            d_peaking = fit_pk - r.peaking_db
            d_fpk = fit_fpk / r.f_pk_hz - 1.0
            if (abs(d_peaking) > FIT_REJECT_PEAKING_DB
                    or abs(d_fpk) > FIT_REJECT_F_PEAK_RATIO):
                raise RuntimeError(
                    f"calibrated CTLE model rejected at rs={rs} cs={cs * 1e12:g}p: "
                    f"peaking off by {d_peaking:+.3f} dB (limit "
                    f"{FIT_REJECT_PEAKING_DB}), f_peak off by {d_fpk:+.1%} "
                    f"(limit {FIT_REJECT_F_PEAK_RATIO:.0%}). §5.3b: a bad fit is "
                    f"a failed evaluation, not a result to pass downstream."
                )
            settings.append(dict(rs=rs, cs=cs, peaking_db=r.peaking_db,
                                 nyquist_boost_db=r.nyquist_boost_db,
                                 f_pk_ghz=r.f_pk_hz / 1e9,
                                 g_dc_lin=r.g_dc_linear,
                                 g_nyq_lin=r.g_nyq_linear,
                                 g_pk_lin=10.0 ** (r.g_pk_db / 20.0),
                                 swing_1db_mVpp=swing * 1e3,
                                 s6_delta_db=s6_delta,
                                 s6_boost_error_db=pred_boost - r.nyquist_boost_db,
                                 fit_peaking_error_db=d_peaking,
                                 fit_f_peak_error=d_fpk,
                                 ss=ss))
    runtime = time.perf_counter() - t0
    n_runs = len(RS_GRID) * len(CS_GRID)
    print(f"\n  swept {n_runs} (rs, cs) settings in {runtime:.1f} s; "
          f"{len(settings)} meet S3 (peaking {SPEC_PEAKING_DB_RANGE[0]}-"
          f"{SPEC_PEAKING_DB_RANGE[1]} dB, interior peak in "
          f"{SPEC_F_PEAK_HZ_RANGE[0] / 1e9:g}-{SPEC_F_PEAK_HZ_RANGE[1] / 1e9:g} GHz)")
    if not settings:
        raise RuntimeError("no setting meets S3 — the sweep grid is wrong")
    e6 = [s["s6_boost_error_db"] for s in settings]
    ef = [s["fit_peaking_error_db"] for s in settings]
    ep = [s["fit_f_peak_error"] for s in settings]
    print(f"  §6 AS WRITTEN over-predicts the Nyquist boost by "
          f"{min(e6):+.2f} .. {max(e6):+.2f} dB (it neglects r_o), so it is NOT "
          f"what convention C runs on.")
    print(f"  CALIBRATED model (k fitted to the measured boost; f_z and f_p2 "
          f"exact from the passives): independent residuals — peaking "
          f"{min(ef):+.3f} .. {max(ef):+.3f} dB against a {FIT_REJECT_PEAKING_DB} dB "
          f"reject limit, f_peak {min(ep):+.1%} .. {max(ep):+.1%} "
          f"(session 11 measured `meas ac MAX` as quantised at 4.7%).")

    # --- the matched-boost verdict, three conventions ---------------------
    tx = TxDeEmphasis(DE_EMPHASIS_SETTINGS_DB[1])
    rows = []
    for il in FAMILY_IL_DB:
        burden = tx.burden_db(il)
        target = min(max(burden, SPEC_PEAKING_DB_RANGE[0]), SPEC_PEAKING_DB_RANGE[1])
        chosen = min(settings, key=lambda s: abs(s["nyquist_boost_db"] - target))
        ch = ChannelModel(il)
        cfg_nyq_pp = tx.swing_diff_pp_v * 10.0 ** (-il / 20.0)
        need_a = cfg_nyq_pp * chosen["g_nyq_lin"]
        need_b = tx.long_run_diff_pp_v * chosen["g_pk_lin"]
        need_c = _peak_distortion_output_pp_v(ch, tx, chosen["ss"])
        have = chosen["swing_1db_mVpp"] / 1e3
        rows.append(dict(
            il_db=il, burden_db=burden, target_db=target,
            rs=chosen["rs"], cs=chosen["cs"],
            peaking_db=chosen["peaking_db"],
            nyquist_boost_db=chosen["nyquist_boost_db"],
            f_pk_ghz=chosen["f_pk_ghz"],
            need_nyquist_mVpp=need_a * 1e3,
            need_longrun_mVpp=need_b * 1e3,
            need_peakdist_mVpp=need_c * 1e3,
            have_mVpp=have * 1e3,
            ratio_nyquist=need_a / have,
            ratio_longrun=need_b / have,
            ratio_peakdist=need_c / have,
        ))

    if verbose:
        print("\n  MATCHED BOOST — each loss point uses the S3-meeting setting")
        print("  whose Nyquist boost is closest to the CTLE's BURDEN")
        print("  (= channel IL - 3.5 dB of mandated TX de-emphasis).")
        print("\n   IL  burden  chosen setting        boost   f_pk    have"
              "   need(A)  need(B)  need(C)   A     B     C")
        for r in rows:
            print(f"  {r['il_db']:4.1f} {r['burden_db']:+6.1f}  "
                  f"rs{r['rs']:<6.0f} cs{r['cs'] * 1e12:<5.2f}p "
                  f"{r['nyquist_boost_db']:6.2f} {r['f_pk_ghz']:6.3f} "
                  f"{r['have_mVpp']:7.0f} {r['need_nyquist_mVpp']:8.0f} "
                  f"{r['need_longrun_mVpp']:8.0f} {r['need_peakdist_mVpp']:8.0f} "
                  f"{r['ratio_nyquist']:5.2f} {r['ratio_longrun']:5.2f} "
                  f"{r['ratio_peakdist']:5.2f}")
        print("\n    A = session 9c/9d's convention: Nyquist content in, Nyquist gain out")
        print("    B = calibration.py C3: long-run level in, PEAK gain out")
        print("    C = peak distortion through the ACTUAL pulse response — the")
        print("        worst-case pattern, computed rather than proxied. USE C.")
        for key, label in (("ratio_nyquist", "A"), ("ratio_longrun", "B"),
                           ("ratio_peakdist", "C")):
            n = sum(1 for r in rows if r[key] > 1.0)
            print(f"    convention {label}: {n}/{len(rows)} loss points compress")
    return dict(settings=[{k: v for k, v in s.items() if k != "ss"}
                          for s in settings],
                matched=rows, reference_measured=measured,
                n_runs=n_runs, runtime_s=runtime)


# ─────────────────────────────────────────────────────────────────────────────
# Persistence + main
# ─────────────────────────────────────────────────────────────────────────────


def write_outputs(gates, cursors, reflections, compression) -> None:
    fieldnames = ["il_db", "skin_fraction", "split", "de_emphasis_db", "ctle",
                  "ctle_boost_db", "burden_db", "h0_mv", "dfe_tap",
                  "precursor_frac", "postcursor_tail_frac", "residual_frac",
                  "eye_open", "eye_h_mv", "required_dc_gain"] + \
                 [f"h{k}" for k in REPORTED_TAPS]
    with DATA_CSV.open("w", newline="", encoding="ascii") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for r in cursors:
            d = {k: v for k, v in asdict(r).items() if k != "taps"}
            d.update({f"h{k}": repr(r.taps[k]) for k in REPORTED_TAPS})
            w.writerow(d)
    payload = dict(
        osr=DEFAULT_OSR, n_fft=DEFAULT_N_FFT,
        causality_threshold=CAUSALITY_ENERGY_THRESHOLD,
        family_il_db=list(FAMILY_IL_DB),
        family_skin_fractions=list(FAMILY_SKIN_FRACTIONS),
        ctle_f_pole2_hz=DEFAULT_F_POLE2_HZ,
        gates=gates, reflections=reflections,
        compression=compression,
    )
    RESULTS_JSON.write_text(json.dumps(payload, indent=2, default=str),
                            encoding="ascii")
    print(f"\nwrote {DATA_CSV.name} ({len(cursors)} rows) and {RESULTS_JSON.name}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gates", action="store_true")
    ap.add_argument("--cursors", action="store_true")
    ap.add_argument("--reflections", action="store_true")
    ap.add_argument("--compression", action="store_true",
                    help="the ngspice re-run of the compression verdict")
    ap.add_argument("--report", action="store_true",
                    help="print from the committed CSV/JSON, no computation")
    args = ap.parse_args(argv)

    if args.report:
        if not RESULTS_JSON.exists():
            print(f"no {RESULTS_JSON.name} — run without --report first")
            return 1
        print(RESULTS_JSON.read_text(encoding="ascii"))
        return 0

    any_stage = args.gates or args.cursors or args.reflections or args.compression
    do_gates = args.gates or not any_stage
    do_cursors = args.cursors or not any_stage
    do_refl = args.reflections or not any_stage

    print("=" * 78)
    print("CHANNEL FAMILY — derived from S3, not invented")
    print("  IL at 2.5 GHz:", ", ".join(f"{x:g}" for x in FAMILY_IL_DB), "dB")
    print("  skin fractions:", ", ".join(f"{x:g}" for x in FAMILY_SKIN_FRACTIONS))
    print("  TX: PCIe Gen2 mandated de-emphasis, settings",
          ", ".join(f"{x:+g}" for x in DE_EMPHASIS_SETTINGS_DB), "dB")
    print("  CTLE second pole: %.3f GHz (rl 565 x cl_mid 32.63 fF, measured)"
          % (DEFAULT_F_POLE2_HZ / 1e9))
    print("=" * 78)

    gates = run_gates() if do_gates else []
    cursors = run_cursors() if do_cursors else []
    reflections = run_reflections() if do_refl else []
    compression = run_compression() if args.compression else None

    if cursors:
        write_outputs(gates, cursors, reflections, compression)
    return 0


if __name__ == "__main__":
    sys.exit(main())
