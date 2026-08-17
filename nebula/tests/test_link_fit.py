"""
The pole-zero fit: CLAUDEwa.md §5.3(b), the second of the two things most
likely to be silently wrong.

WHAT THESE PIN
--------------
1. **Exactness.** Given a response that IS one-zero/two-pole, the fit returns
   the generating parameters — not "close", to machine precision. A fitter
   that cannot do that on noiseless data has no business on measured data.
2. **The 0.5 dB gate discriminates.** It rejects a shape the model cannot
   represent AND accepts one it can. A gate that always fires is
   indistinguishable from a deleted gate (G73); one that never fires is worse.
3. **Pole ORDER is enforced.** `(f_p1, f_p2)` and `(f_p2, f_p1)` describe the
   same response, so the optimiser may return either — but §6 gives them
   different meanings and downstream code reads them by that meaning.
4. **A rejected fit cannot be used by accident.** Reading `.response()` or
   `.small_signal` off one raises rather than returning plausible poles.
5. **Bad INPUT raises; a bad CIRCUIT is rejected.** Same distinction
   `run_point` draws.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from nebula.common import design_equations as deq
from nebula.common.types import FIT_RESIDUAL_REJECT_DB
from nebula.link.fit import (
    FIT_F_HI_HZ,
    FIT_F_LO_HZ,
    CtleFit,
    FitError,
    fit_ctle,
    fit_from_point,
    initial_guess_from_design_equations,
)

F_GRID = np.logspace(6, 11, 251)          # the .ac dec 50 1meg 100g grid


def _synthetic_db(g_dc, fz, fp1, fp2, f=F_GRID):
    s = 1j * np.asarray(f, dtype=float)
    h = g_dc * (1 + s / fz) / ((1 + s / fp1) * (1 + s / fp2))
    return 20.0 * np.log10(np.abs(h))


# ─────────────────────────────────────────────────────────────────────────────
# 1. Exactness on a response the model can represent.
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("g_dc,fz,fp1,fp2", [
    (1.9, 0.6e9, 2.4e9, 9.0e9),
    (0.5, 1.2e9, 8.0e9, 3.0e9),           # poles given in the "wrong" order
    (3.2, 0.15e9, 0.9e9, 22.0e9),
    (1.0, 2.0e9, 2.05e9, 40.0e9),         # a nearly-cancelling pair
])
def test_the_fit_recovers_the_generating_parameters_exactly(g_dc, fz, fp1, fp2):
    r = fit_ctle(F_GRID, _synthetic_db(g_dc, fz, fp1, fp2))
    assert r.ok, r.fail_reason
    lo, hi = sorted((fp1, fp2))
    assert r.g_dc == pytest.approx(g_dc, rel=1e-6)
    assert r.f_zero_hz == pytest.approx(fz, rel=1e-6)
    assert r.f_pole1_hz == pytest.approx(lo, rel=1e-6)
    assert r.f_pole2_hz == pytest.approx(hi, rel=1e-6)
    assert r.residual_db < 1e-9, "noiseless data must fit to machine precision"


def test_poles_come_back_ordered_because_section_6_gives_them_meanings():
    """§6: `f_p1 = k/(Rs*Cs)` is the degeneration pole, `f_p2 = 1/(RL*CL)` the
    load pole. `SmallSignal.degeneration_factor` is literally `f_p1/f_z`, so a
    swapped pair silently reports the wrong degeneration factor."""
    r = fit_ctle(F_GRID, _synthetic_db(1.0, 1.0e9, 30.0e9, 3.0e9))
    assert r.ok, r.fail_reason
    assert r.f_pole1_hz < r.f_pole2_hz
    assert r.f_pole1_hz == pytest.approx(3.0e9, rel=1e-6)


def test_small_signal_is_the_repos_own_type_and_degeneration_factor_follows():
    r = fit_ctle(F_GRID, _synthetic_db(2.0, 1.0e9, 4.0e9, 20.0e9))
    ss = r.small_signal
    assert isinstance(ss, deq.SmallSignal)
    assert ss.degeneration_factor == pytest.approx(4.0, rel=1e-6)
    # `peaking_db` on SmallSignal is the ASYMPTOTE by that type's definition.
    assert ss.peaking_db == pytest.approx(20 * math.log10(4.0), rel=1e-6)


def test_realised_peaking_is_below_the_asymptote_as_task8_measured():
    """`task8_symbolic.py`: `20*log10(k)` over-predicts the realised peak by a
    median +1.199 dB across 1311 designs. The fit must expose both and they
    must differ in that direction."""
    r = fit_ctle(F_GRID, _synthetic_db(1.0, 0.5e9, 4.0e9, 8.0e9))
    realised, f_peak = r.realised_peaking_db()
    assert realised < r.small_signal.peaking_db
    assert 0.5e9 < f_peak < 8.0e9


# ─────────────────────────────────────────────────────────────────────────────
# 2. The gate. It must fire, and it must NOT always fire.
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("q,expect_res_db", [(2.0, 3.0), (5.0, 4.0), (12.0, 4.5)])
def test_a_resonance_is_REJECTED_because_1z2p_cannot_make_a_sharp_peak(q, expect_res_db):
    """The gate firing. Measured residuals 3.17 / 4.25 / 4.88 dB at Q = 2/5/12,
    against a 0.5 dB budget."""
    f = F_GRID
    f0 = 2.5e9
    h = ((1 + 1j * f / 0.6e9)
         / ((1 + 1j * f / 9e9) * (1 - (f / f0) ** 2 + 1j * f / (q * f0))))
    r = fit_ctle(f, 20 * np.log10(np.abs(h)))
    assert not r.ok
    assert "residual" in (r.fail_reason or "")
    assert r.residual_db > expect_res_db


def test_a_mild_extra_pole_is_ACCEPTED_so_the_gate_is_not_always_on():
    """G73: a gate whose condition is unreachable is a deleted gate. A third
    pole well above the band is a real circuit and must pass — measured
    residual 0.224 dB against the 0.5 dB budget."""
    f = F_GRID
    s = 1j * f
    h = 1.9 * (1 + s / 0.6e9) / ((1 + s / 2.4e9) * (1 + s / 9e9) * (1 + s / 15e9))
    r = fit_ctle(f, 20 * np.log10(np.abs(h)))
    assert r.ok, r.fail_reason
    assert 0.0 < r.residual_db < FIT_RESIDUAL_REJECT_DB


def test_the_gate_threshold_is_the_contracts_and_is_not_redeclared():
    """§5.3(b)'s 0.5 dB lives in `common/types.FIT_RESIDUAL_REJECT_DB` and the
    fitter defaults to it — a second copy is rule 9's failure."""
    import inspect
    from nebula.link import fit as F
    sig = inspect.signature(F.fit_ctle)
    assert sig.parameters["reject_above_db"].default is FIT_RESIDUAL_REJECT_DB
    assert FIT_RESIDUAL_REJECT_DB == pytest.approx(0.5)


def test_a_borderline_fit_is_rejected_on_the_stated_side_of_the_gate():
    """Break it deliberately: tighten the gate below a known-good residual and
    watch the same data go red."""
    data = _synthetic_db(1.9, 0.6e9, 2.4e9, 9.0e9)
    f = F_GRID
    s = 1j * f
    h = 1.9 * (1 + s / 0.6e9) / ((1 + s / 2.4e9) * (1 + s / 9e9) * (1 + s / 15e9))
    data = 20 * np.log10(np.abs(h))

    loose = fit_ctle(f, data, reject_above_db=0.5)
    tight = fit_ctle(f, data, reject_above_db=0.05)
    assert loose.ok and not tight.ok
    # same numbers, different verdict — the gate is the only difference
    assert loose.residual_db == pytest.approx(tight.residual_db)
    assert loose.f_zero_hz == pytest.approx(tight.f_zero_hz)


# ─────────────────────────────────────────────────────────────────────────────
# 3. A rejected fit cannot be used by accident.
# ─────────────────────────────────────────────────────────────────────────────


def test_a_rejected_fit_refuses_to_hand_over_poles_or_a_response():
    f = F_GRID
    f0 = 2.5e9
    h = (1 + 1j * f / 0.6e9) / (1 - (f / f0) ** 2 + 1j * f / (8.0 * f0))
    r = fit_ctle(f, 20 * np.log10(np.abs(h)))
    assert not r.ok
    with pytest.raises(FitError):
        _ = r.small_signal
    with pytest.raises(FitError):
        r.response(np.array([1e9]))
    # ... but it still SAYS what it converged on, which is what a rejection
    # makes you want to know.
    assert r.f_zero_hz is not None and r.residual_db > 0


def test_max_residual_is_reported_beside_the_rms():
    """An RMS of 0.4 dB with a 3 dB spike at the peak is a bad fit that passes
    the RMS gate. Both numbers are reported so that is visible."""
    r = fit_ctle(F_GRID, _synthetic_db(1.9, 0.6e9, 2.4e9, 9.0e9))
    assert r.max_residual_db >= r.residual_db


# ─────────────────────────────────────────────────────────────────────────────
# 4. Bad input RAISES; a bad circuit is REJECTED.
# ─────────────────────────────────────────────────────────────────────────────


def test_non_finite_samples_raise_rather_than_being_fitted():
    """G54's shape: a NaN that reaches an optimiser is fitted as though it were
    data, and the result is finite and plausible."""
    m = _synthetic_db(1.0, 1e9, 4e9, 20e9).copy()
    m[100] = np.nan
    with pytest.raises(FitError, match="non-finite"):
        fit_ctle(F_GRID, m)


def test_mismatched_or_empty_input_raises():
    with pytest.raises(FitError):
        fit_ctle([], [])
    with pytest.raises(FitError):
        fit_ctle(F_GRID, F_GRID[:-1])


def test_too_few_in_band_points_raises_rather_than_fitting_four_params_to_three():
    f = np.array([1e6, 2e6, 3e6, 4e6])         # all below FIT_F_LO_HZ
    with pytest.raises(FitError, match="cannot be fitted"):
        fit_ctle(f, np.zeros_like(f))


def test_a_point_without_an_ac_curve_raises_with_the_reason():
    class _Bare:
        ac_freq_hz = None
        ac_mag_db = None
        g_dc_db = 1.0
    with pytest.raises(FitError, match="ac_sweep=True"):
        fit_from_point(_Bare())


# ─────────────────────────────────────────────────────────────────────────────
# 5. Band, guess, and the independent cross-check.
# ─────────────────────────────────────────────────────────────────────────────


def test_the_fitted_band_is_stated_and_excludes_the_meas_dead_zone():
    """The band is a decision with a reason, not a silent trim: below 10 MHz
    the model is flat, and above 20 GHz `meas ac MAX` does not look (G44)."""
    r = fit_ctle(F_GRID, _synthetic_db(1.0, 1e9, 4e9, 20e9))
    assert r.f_lo_hz >= FIT_F_LO_HZ
    assert r.f_hi_hz <= FIT_F_HI_HZ
    assert r.n_points > 8


def test_the_initial_guess_gets_the_dc_plateau_and_the_ordering_right():
    """What the guess actually guarantees — no more.

    An earlier version of this test asserted `f_z` to within 60 %, and it was
    WRONG about the guess rather than about the code: the docstring claimed
    "the peak sits between f_z and f_p1", which fails whenever `f_p2` pulls the
    maximum above `f_p1`. At (1.9, 0.6, 2.4, 9.0) GHz the true peak is at
    4.52 GHz and the guess returns f_z = 2.56 GHz against a true 0.6 GHz.

    The guess only has to land in the right basin. The test below is the
    evidence that it does.
    """
    g_dc, fz, fp1, fp2 = 1.9, 0.6e9, 2.4e9, 9.0e9
    band = (F_GRID >= FIT_F_LO_HZ) & (F_GRID <= FIT_F_HI_HZ)
    p0 = initial_guess_from_design_equations(
        F_GRID[band], _synthetic_db(g_dc, fz, fp1, fp2)[band])
    assert 10 ** p0[0] == pytest.approx(g_dc, rel=0.15)   # the DC plateau IS read
    assert p0[1] < p0[2] < p0[3]                          # z below p1 below p2
    assert np.all(np.isfinite(p0))


@pytest.mark.parametrize("g_dc,fz,fp1,fp2", [
    (1.9, 0.6e9, 2.4e9, 9.0e9),
    (0.5, 1.2e9, 3.0e9, 8.0e9),
])
def test_the_fit_converges_from_deliberately_bad_starts(g_dc, fz, fp1, fp2):
    """THE BASIN, probed rather than assumed.

    A four-parameter fit that only ever starts from one place cannot tell a
    unique minimum from a lucky one. Starts spanning two decades either side
    of the truth must all land on the same parameters.
    """
    data = _synthetic_db(g_dc, fz, fp1, fp2)
    ref = fit_ctle(F_GRID, data)
    assert ref.ok, ref.fail_reason

    for shift in (-2.0, -1.0, +1.0, +2.0):
        start = np.array([math.log10(g_dc) + 0.5 * shift,
                          math.log10(fz) + shift,
                          math.log10(fp1) + shift,
                          math.log10(fp2) + shift])
        r = fit_ctle(F_GRID, data, p0=start)
        assert r.ok, (shift, r.fail_reason)
        assert r.f_zero_hz == pytest.approx(ref.f_zero_hz, rel=1e-6), shift
        assert r.f_pole1_hz == pytest.approx(ref.f_pole1_hz, rel=1e-6), shift
        assert r.f_pole2_hz == pytest.approx(ref.f_pole2_hz, rel=1e-6), shift
        assert r.g_dc == pytest.approx(ref.g_dc, rel=1e-6), shift


def test_g_dc_disagreement_is_none_unless_an_independent_value_is_given():
    """The fit never READS the measured value — that is what makes agreement
    evidence rather than construction."""
    m = _synthetic_db(2.0, 1e9, 4e9, 20e9)
    assert fit_ctle(F_GRID, m).g_dc_disagreement_db is None
    r = fit_ctle(F_GRID, m, measured_g_dc_db=20 * math.log10(2.0))
    assert r.g_dc_disagreement_db == pytest.approx(0.0, abs=1e-6)


def test_response_is_hermitian_so_the_pulse_stays_real():
    """`cursors.pulse_response` multiplies on a SIGNED frequency axis and takes
    the real part; a non-Hermitian response would leak an imaginary part into
    the time domain. Same convention as `MatchedCtle.response`."""
    r = fit_ctle(F_GRID, _synthetic_db(1.5, 1e9, 4e9, 20e9))
    f = np.array([-3e9, -1e9, 1e9, 3e9])
    h = r.response(f)
    assert h[0] == pytest.approx(np.conj(h[3]))
    assert h[1] == pytest.approx(np.conj(h[2]))


def test_fit_and_matched_ctle_share_one_response_convention():
    """Rule 9: two ways of arriving at a CTLE, one interface. Build a
    `MatchedCtle`, read its poles back through the fitter's response form, and
    require the same complex numbers."""
    from nebula.link.cursors import matched_ctle

    mc = matched_ctle(target_boost_db=6.0)
    fitted = CtleFit(
        ok=True, fail_reason=None, g_dc=mc.ss.g_dc,
        f_zero_hz=mc.ss.f_zero_hz, f_pole1_hz=mc.ss.f_pole1_hz,
        f_pole2_hz=mc.ss.f_pole2_hz, residual_db=0.0, max_residual_db=0.0,
        n_points=0, f_lo_hz=0.0, f_hi_hz=0.0)
    f = np.array([-5e9, -1e9, 0.0, 1e9, 5e9])
    np.testing.assert_allclose(fitted.response(f), mc.response(f), rtol=1e-12)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Against real silicon.
# ─────────────────────────────────────────────────────────────────────────────


def _have_sim() -> bool:
    import shutil
    from nebula.device.ngspice_runner import _DEFAULT_NGSPICE
    from nebula.device.sky130_runner import CTLE_LIB
    ng = _DEFAULT_NGSPICE.exists() or shutil.which("ngspice_con") is not None
    return ng and CTLE_LIB.exists()


needs_sim = pytest.mark.skipif(not _have_sim(), reason="ngspice or SKY130 absent")


@needs_sim
@pytest.mark.parametrize("rs,cs,rl,w,l,i_bias,vcm", [
    (319.0, 1.90e-12, 565.0, 89.3, 0.399, 3.25e-3, 1.407),   # design 432
    (200.0, 1.60e-12, 400.0, 40.0, 0.150, 3.00e-3, 1.250),   # the 9c reference
    (700.0, 0.80e-12, 300.0, 60.0, 0.250, 4.00e-3, 1.350),   # high peaking
])
def test_real_sky130_responses_fit_inside_the_gate(rs, cs, rl, w, l, i_bias, vcm):
    """The whole point: does a real drawn-passive CTLE fit a 1z/2p model?

    Measured 2026-08-17, TT/27, drawn passives and a real mirror tail:
    residuals 0.227 / 0.008 / 0.028 dB against the 0.5 dB gate, and the fitted
    DC gain agrees with the INDEPENDENT `meas ac g_dc` to 0.03 dB.

    Design 432 is the worst of the three at 45 % of the residual budget, and
    that is worth knowing rather than averaging away: it is the drawn-passive
    design whose `res_po` bottom plate loads the output node hardest (G66), so
    the response departs from a pure 1z/2p shape most where the parasitics
    matter most.
    """
    from nebula.device.passives import to_geometry
    from nebula.device.sky130_runner import SizingPoint, run_point

    geo = to_geometry(rs, cs, rl)
    p = SizingPoint(w=w, l=l, nf=4, rs=rs, cs=cs, rl=rl, cl=32.63e-15,
                    i_tail_per_side_a=i_bias / 2.0, vcm=vcm, passives=geo)
    r = run_point(p, "tt", swing=False, ac_sweep=True)
    assert r.ok, r.fail_reason

    fit = fit_from_point(r)
    assert fit.ok, fit.fail_reason
    assert fit.residual_db < FIT_RESIDUAL_REJECT_DB

    # The §5.3(b) cross-check: the fit never reads this number.
    assert abs(fit.g_dc_disagreement_db) < 0.10

    # And the fitted model's own peak agrees with `meas ac MAX` on the circuit.
    peaking, f_peak = fit.realised_peaking_db()
    assert peaking == pytest.approx(r.peaking_db, abs=0.35)
    assert f_peak == pytest.approx(r.f_pk_hz, rel=0.10)


@needs_sim
def test_the_fit_is_deterministic_on_one_measured_curve():
    """Two fits of the same data must agree exactly — an optimiser seeded from
    anything run-dependent would make every downstream eye number irreproducible."""
    from nebula.device.passives import to_geometry
    from nebula.device.sky130_runner import SizingPoint, run_point

    geo = to_geometry(319.0, 1.90e-12, 565.0)
    p = SizingPoint(w=89.3, l=0.399, nf=4, rs=319.0, cs=1.90e-12, rl=565.0,
                    cl=32.63e-15, i_tail_per_side_a=3.25e-3 / 2, vcm=1.407,
                    passives=geo)
    r = run_point(p, "tt", swing=False, ac_sweep=True)
    assert r.ok, r.fail_reason
    a, b = fit_from_point(r), fit_from_point(r)
    for name in ("g_dc", "f_zero_hz", "f_pole1_hz", "f_pole2_hz", "residual_db"):
        assert getattr(a, name) == getattr(b, name), name
