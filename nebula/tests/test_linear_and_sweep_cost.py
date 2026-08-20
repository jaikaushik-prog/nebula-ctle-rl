"""
Tests for session 22q's three experiment modules — the linear-range front, the
HD3 amplitude/frequency sweep, and the full-sweep cost extrapolation.

**None of these runs ngspice.** What is under test is the arithmetic and the
filtering, not the circuit — and in two cases the thing under test is
specifically a filter that was MISSING in the first version and whose absence
produced a confident wrong answer:

  * `Probe.in_s3_window` — binning by peaking alone admitted a design peaking
    at 19.95 GHz, whose Nyquist de-rate is ~1, which then defined the "front".
    Filtering on peaking does not select CTLEs, it selects wideband
    attenuators.
  * `exp_sweep_cost`'s interpolated-peak gradient — reading `f_peak` off the
    `dec 50` lattice made four of seven axes return a gradient of exactly one
    lattice step, inflating the final simulation count by 1 296x.

Both are gates in `CLAUDEwa.md` §8 rule 10's sense and both were watched go
red before being restored.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from nebula.experiments import exp_hd3_amplitude as H
from nebula.experiments import exp_linear_pareto as LP
from nebula.experiments import exp_sweep_cost as SC


def _probe(peaking=9.0, f_peak=1.9e9, boost=8.0, lin_dc=0.52, ok=True,
           real_peak=True, lower=False):
    return LP.Probe(
        u=tuple([0.5] * 7), ok=ok, arm="test", peaking_db=peaking,
        nyq_boost_db=boost, f_peak_hz=f_peak, g_dc_db=-3.4, power_w=2.2e-3,
        linear_in_dc_pp_v=lin_dc,
        linear_in_nyq_pp_v=lin_dc / (10.0 ** (boost / 20.0)),
        limit_is_lower_bound=lower, has_real_peak=real_peak)


# ─────────────────────────────────────────────────────────────────────────────
# The S3 filter — the gate whose absence invalidated the first run.
# ─────────────────────────────────────────────────────────────────────────────


def test_a_20ghz_peak_is_NOT_in_the_s3_window():
    """**The exact design that defined the bogus front.** 10 dB of peaking at
    19.95 GHz: inside S3's amplitude band, nowhere near its frequency window,
    and flat by 2.5 GHz so its de-rate is ~1."""
    assert not _probe(peaking=10.09, f_peak=19.95e9, boost=0.2).in_s3_window
    assert _probe(peaking=10.09, f_peak=1.9e9, boost=8.0).in_s3_window


def test_s3_window_needs_all_of_band_frequency_and_boost():
    assert _probe().in_s3_window
    assert not _probe(peaking=2.5).in_s3_window           # under S3's floor
    assert not _probe(peaking=12.5).in_s3_window          # over its ceiling
    assert not _probe(f_peak=1.0e9).in_s3_window          # below the window
    assert not _probe(f_peak=3.0e9).in_s3_window          # above it
    assert not _probe(boost=-0.5).in_s3_window            # worse than a wire
    assert not _probe(real_peak=False).in_s3_window       # G44 sweep edge
    assert not _probe(ok=False).in_s3_window


def test_front_defaults_to_s3_only_and_the_contrast_is_available():
    """The default must exclude the attenuators; `s3_only=False` is a contrast
    a caller can ask for, never the default."""
    good = _probe(peaking=9.2, f_peak=1.9e9, boost=8.0, lin_dc=0.52)
    fake = _probe(peaking=9.2, f_peak=19.9e9, boost=0.2, lin_dc=1.50)
    edges = (9.0, 9.5)

    f_s3 = LP.front([good, fake], "linear_in_nyq_pp_v", edges=edges)
    f_all = LP.front([good, fake], "linear_in_nyq_pp_v", edges=edges,
                     s3_only=False)
    assert f_s3[0]["n"] == 1
    assert f_s3[0]["best"] == pytest.approx(good.linear_in_nyq_pp_v)
    assert f_all[0]["n"] == 2
    assert f_all[0]["best"] == pytest.approx(fake.linear_in_nyq_pp_v)
    # and the artefact is the LARGER of the two, which is why it wins
    assert f_all[0]["best"] > f_s3[0]["best"]


def test_a_lower_bound_is_never_reported_as_the_front():
    """A design whose sweep never compressed has a bound, not a limit. It is
    counted, and excluded from the max."""
    bound = _probe(lin_dc=1.60, lower=True)
    hard = _probe(lin_dc=0.52, lower=False)
    r = LP.front([bound, hard], "linear_in_nyq_pp_v", edges=(8.5, 9.5))[0]
    assert r["n"] == 2
    assert r["n_with_a_hard_limit"] == 1
    assert r["n_lower_bound_only"] == 1
    assert r["best"] == pytest.approx(hard.linear_in_nyq_pp_v)


def test_crossing_returns_none_when_no_bin_reaches_the_drive():
    """`None` is a RESULT here, not a missing number."""
    rows = [{"peaking_lo_db": 3.0, "peaking_hi_db": 4.0, "best": 0.20, "n": 5}]
    assert LP.crossing(rows, drive_v=0.535) is None
    rows.append({"peaking_lo_db": 4.0, "peaking_hi_db": 5.0, "best": 0.60,
                 "n": 5})
    got = LP.crossing(rows, drive_v=0.535)
    assert got is not None and got["peaking_hi_db"] == 5.0


# ─────────────────────────────────────────────────────────────────────────────
# HD3 crossing interpolation.
# ─────────────────────────────────────────────────────────────────────────────


def test_hd3_crossing_is_bracketed_never_extrapolated():
    """A sweep that never reaches the limit returns None rather than running
    the fit off the end of the data."""
    rows = [{"vin_pp_mv": v, "hd3_dbc": h}
            for v, h in ((50, -72.0), (100, -60.0), (200, -48.0))]
    assert H.crossing_mvpp(rows, -30.0) is None


def test_hd3_crossing_interpolates_in_log_amplitude():
    """HD3 in dBc against log(amplitude) is near-linear for a cubic
    nonlinearity, so the interpolation is done there.

    **More negative is better**, so -30.23 dBc at 500 mVpp is still INSIDE
    S4 and the crossing lies between 500 and 600, not below 500. (These are
    the delivered design's own measured 100 MHz samples, and the run reports
    505 mVpp.) A sign slip here would put the crossing on the wrong side of
    the drive and invert the finding.
    """
    rows = [{"vin_pp_mv": v, "hd3_dbc": h}
            for v, h in ((400, -34.90), (500, -30.23), (600, -26.15))]
    c = H.crossing_mvpp(rows, -30.0)
    assert 500.0 < c < 520.0

    x0, x1 = math.log10(500), math.log10(600)
    want = 10 ** (x0 + (-30.0 + 30.23) * (x1 - x0) / (-26.15 + 30.23))
    assert c == pytest.approx(want)


# ─────────────────────────────────────────────────────────────────────────────
# The sweep-cost arithmetic.
# ─────────────────────────────────────────────────────────────────────────────


def test_peak_resolution_is_derived_from_dec_50_not_transcribed():
    """G74's 0.0664386 octaves. Derived so it cannot drift from `dec 50`."""
    assert SC.PEAK_RESOLUTION_OCT == pytest.approx(0.0664386, abs=1e-6)
    assert SC.PEAK_RESOLUTION_OCT == pytest.approx(
        math.log2(10.0 ** (1.0 / SC.AC_DEC)))


def test_sweep_cost_is_the_product_of_the_levels():
    c = SC.sweep_cost([2, 5, 9, 9, 50, 42, 2], sec_per_sim=0.09773)
    assert c["n_simulations"] == 2 * 5 * 9 * 9 * 50 * 42 * 2
    assert c["wall_clock_s"] == pytest.approx(
        c["n_simulations"] * 0.09773)
    assert c["wall_clock_hours"] == pytest.approx(c["wall_clock_s"] / 3600.0)
    assert c["is_extrapolation"] is True


def test_one_more_level_on_one_axis_is_a_multiplicative_change():
    """Why the level count may not be a round number picked by hand: at d = 7
    the answer is a product, so each axis scales the whole result."""
    a = SC.sweep_cost([8] * 7, 0.1)["n_simulations"]
    b = SC.sweep_cost([6] * 7, 0.1)["n_simulations"]
    assert a / b == pytest.approx((8 / 6) ** 7, rel=1e-9)
    assert a / b > 7.0


def test_an_inert_axis_gets_two_levels_not_one():
    """A factorial cannot have fewer than two levels on an axis; an axis
    measured as inert for f_peak must still be swept at its two edges."""
    lv = max(2, 1 + int(math.ceil(0.0 / SC.PEAK_RESOLUTION_OCT)))
    assert lv == 2
    # and an axis at exactly one resolution step gets exactly two
    lv1 = max(2, 1 + int(math.ceil(SC.PEAK_RESOLUTION_OCT
                                   / SC.PEAK_RESOLUTION_OCT)))
    assert lv1 == 2


def test_the_committed_result_matches_its_own_level_arithmetic():
    """The artifact on disk must be internally consistent: the reported
    simulation count is the product of the reported levels, and the levels are
    what the reported sensitivities imply. Catches a stale artifact."""
    import json
    from pathlib import Path

    p = Path(SC.RESULTS)
    if not p.exists():
        pytest.skip("sweep_cost_results.json not built in this checkout")
    d = json.loads(p.read_text(encoding="utf-8"))
    n = 1
    for l in d["levels"]:
        n *= l
    assert d["full_factorial_at_8_workers"]["n_simulations"] == n
    for s in d["sensitivity"]:
        want = max(2, 1 + int(math.ceil(s["median_oct"]
                                        / d["resolution_oct"])))
        assert s["levels"] == want, s["name"]


def test_no_axis_reports_a_gradient_of_exactly_one_lattice_step():
    """**THE REGRESSION GATE for the defect that inflated this by 1 296x.**

    Reading `f_peak` off the `dec 50` lattice made four axes return
    |d log2 f / du| = 0.664386 exactly -- ten steps of 0.0664386 over a 0.1
    finite difference, i.e. the smallest change the lattice can express. A
    gradient pinned to an exact multiple of the quantum, with zero spread
    across six independent reference designs, is the quantum and not a
    derivative.
    """
    import json
    from pathlib import Path

    p = Path(SC.RESULTS)
    if not p.exists():
        pytest.skip("sweep_cost_results.json not built in this checkout")
    d = json.loads(p.read_text(encoding="utf-8"))
    step = d["fd_step_u"]
    quantum = d["resolution_oct"] / step
    for s in d["sensitivity"]:
        if s["median_oct"] == 0.0:
            continue
        ratio = s["median_oct"] / quantum
        pinned = abs(ratio - round(ratio)) < 1e-6
        flat = (s["max_oct"] - s["min_oct"]) < 1e-9
        assert not (pinned and flat), (
            f"{s['name']}: gradient {s['median_oct']} is exactly "
            f"{round(ratio)} lattice quanta with zero spread across "
            f"{s['n_usable']} probes -- that is the quantisation, not a "
            f"derivative. Read the peak from f_pk_interp_hz.")
