"""
Tests for the transmitter (`link/tx.py`) and the cursor extraction
(`link/cursors.py`) — the "is a 1-tap DFE enough?" measurement.

The repo's standing rule is that a hand-checkable value beats a regression
baseline, so the load-bearing tests here are three closed forms:

1. **A lossless channel reproduces the TX pulse exactly.** `h0 = c0*A`,
   `h1 = c1*A`, everything else zero, residual zero. Every stage of the
   convolution, the normalisation and the volts is in that one comparison.
2. **The UI-spaced cursors sum to the transmitter's long-run level.** The
   channel is transparent at DC (`A*sqrt(0) + B*0 = 0`), so a run of identical
   bits must arrive at exactly the de-emphasised level. This holds to 7 figures
   for every family member and is the end-to-end check that the deleted DC-loss
   constant's replacement is right.
3. **The CTLE's peak location is closed form**, and a peak exists iff
   `1/fz^2 > 1/fp1^2 + 1/fp2^2` — session 9c's measured "f_z must sit below
   f_p2 or there is no peak at all", in exact form.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from nebula.common import design_equations as deq
from nebula.common.types import NYQUIST_HZ, SPEC_EYE_H_MIN_V
from nebula.link.channel import (
    BALANCED,
    DIELECTRIC_DOMINATED,
    SKIN_DOMINATED,
    ChannelModel,
    channel_family,
)
from nebula.link.config import (
    PCIE_GEN2_DE_EMPHASIS_DB,
    PCIE_GEN2_DE_EMPHASIS_OPTION_DB,
    PCIE_GEN2_TX_DIFF_PP_MIN_V,
)
from nebula.link.cursors import (
    DEFAULT_F_POLE2_HZ,
    REPORTED_TAPS,
    extract_cursors,
    eye_estimate,
    matched_ctle,
    peak_frequency_hz,
    pulse_response,
)
from nebula.link.tx import (
    DE_EMPHASIS_SETTINGS_DB,
    NO_DE_EMPHASIS_DB,
    PCIE_GEN2_TX,
    TxDeEmphasis,
)


# ─────────────────────────────────────────────────────────────────────────────
# The transmitter
# ─────────────────────────────────────────────────────────────────────────────


class TestTxDeEmphasis:
    def test_the_taps_by_hand(self):
        # d = 10**(-3.5/20) = 0.668344
        # c0 = (1 + d)/2 = 0.834172      c1 = -(1 - d)/2 = -0.165828
        tx = TxDeEmphasis(PCIE_GEN2_DE_EMPHASIS_DB)
        assert tx.level_ratio == pytest.approx(0.6683439, rel=1e-6)
        assert tx.c0 == pytest.approx(0.8341720, rel=1e-6)
        assert tx.c1 == pytest.approx(-0.1658280, rel=1e-6)

    def test_the_option_taps_by_hand(self):
        # d = 10**(-6/20) = 0.501187 -> c0 = 0.750594, c1 = -0.249406
        tx = TxDeEmphasis(PCIE_GEN2_DE_EMPHASIS_OPTION_DB)
        assert tx.c0 == pytest.approx(0.7505936, rel=1e-6)
        assert tx.c1 == pytest.approx(-0.2494064, rel=1e-6)

    @pytest.mark.parametrize("db", DE_EMPHASIS_SETTINGS_DB)
    def test_the_transition_bit_always_reaches_full_swing(self, db):
        # THE normalisation. PCIe measures V_TX-DIFF-PP on the transition bit,
        # so c0 + |c1| must be 1 or the launched swing is not what the spec
        # says it is.
        tx = TxDeEmphasis(db)
        assert tx.c0 - tx.c1 == pytest.approx(1.0, abs=1e-15)
        assert tx.gain_at_nyquist == pytest.approx(1.0, abs=1e-15)

    @pytest.mark.parametrize("db", DE_EMPHASIS_SETTINGS_DB)
    def test_the_tilt_is_exactly_the_de_emphasis(self, db):
        # Not approximately: |H_tx| is d at DC and 1 at Nyquist by construction.
        assert TxDeEmphasis(db).tilt_db == pytest.approx(-db, abs=1e-12)

    @pytest.mark.parametrize("db", DE_EMPHASIS_SETTINGS_DB)
    def test_the_fir_response_matches_the_dc_and_nyquist_endpoints(self, db):
        tx = TxDeEmphasis(db)
        assert abs(tx.response(0.0)) == pytest.approx(tx.gain_at_dc, abs=1e-12)
        assert abs(tx.response(NYQUIST_HZ)) == pytest.approx(1.0, abs=1e-12)

    def test_no_de_emphasis_is_a_pass_through(self):
        tx = TxDeEmphasis(NO_DE_EMPHASIS_DB)
        assert tx.c1 == 0.0 and tx.c0 == 1.0
        assert tx.tilt_db == 0.0
        assert tx.long_run_diff_pp_v == pytest.approx(PCIE_GEN2_TX_DIFF_PP_MIN_V)

    def test_the_long_run_level_drops_by_the_de_emphasis(self):
        tx = TxDeEmphasis(PCIE_GEN2_DE_EMPHASIS_DB)
        assert tx.long_run_diff_pp_v == pytest.approx(0.8 * 0.6683439, rel=1e-6)
        assert tx.long_run_level_v == pytest.approx(tx.long_run_diff_pp_v / 2.0)

    def test_the_pulse_is_two_ui_of_the_two_taps(self):
        tx = TxDeEmphasis(PCIE_GEN2_DE_EMPHASIS_DB)
        p = tx.pulse(64)
        assert p.size == 128
        assert np.allclose(p[:64], tx.c0 * tx.symbol_amplitude_v)
        assert np.allclose(p[64:], tx.c1 * tx.symbol_amplitude_v)

    def test_the_swing_anchor_is_referenced_not_redeclared(self):
        # CLAUDEwa.md §8 rule 9. G32 was two netlists describing "the same"
        # point with different model cards.
        assert TxDeEmphasis().swing_diff_pp_v is PCIE_GEN2_TX_DIFF_PP_MIN_V
        assert TxDeEmphasis().de_emphasis_db is PCIE_GEN2_DE_EMPHASIS_DB

    def test_pre_emphasis_is_rejected(self):
        with pytest.raises(ValueError, match="de_emphasis_db must be <= 0"):
            TxDeEmphasis(+3.5)

    def test_the_burden_subtraction(self):
        tx = TxDeEmphasis(PCIE_GEN2_DE_EMPHASIS_DB)
        assert tx.burden_db(12.0) == pytest.approx(8.5)
        assert tx.burden_db(3.0) == pytest.approx(-0.5)   # already over-equalised
        with pytest.raises(ValueError, match="non-negative dB loss"):
            tx.burden_db(-1.0)


# ─────────────────────────────────────────────────────────────────────────────
# The closed-form CTLE
# ─────────────────────────────────────────────────────────────────────────────


class TestPeakLocationClosedForm:
    @pytest.mark.parametrize("fz_ghz", [0.1, 0.3, 0.8, 1.5])
    def test_the_closed_form_agrees_with_a_dense_numeric_search(self, fz_ghz):
        ss = deq.SmallSignal(g_dc=1.0, f_zero_hz=fz_ghz * 1e9,
                             f_pole1_hz=4.0 * fz_ghz * 1e9,
                             f_pole2_hz=DEFAULT_F_POLE2_HZ, peaking_db=12.0)
        analytic = peak_frequency_hz(ss)
        _, numeric = deq.realised_peaking_db(ss, n_points=400000)
        assert analytic == pytest.approx(numeric, rel=2e-4)

    def test_a_peak_exists_exactly_when_the_inequality_holds(self):
        # 1/fz^2 > 1/fp1^2 + 1/fp2^2. Session 9c's "f_z must sit BELOW f_p2 or
        # there is no peak at all", stated exactly rather than as a rule of
        # thumb, and checked on both sides of the boundary.
        fp2 = 8.0e9
        for k in (1.2, 2.0, 6.0):
            for fz in (0.2e9, 1.0e9, 4.0e9, 12.0e9):
                ss = deq.SmallSignal(g_dc=1.0, f_zero_hz=fz, f_pole1_hz=k * fz,
                                     f_pole2_hz=fp2, peaking_db=0.0)
                predicted = (1.0 / fz ** 2) > (1.0 / (k * fz) ** 2 + 1.0 / fp2 ** 2)
                assert (peak_frequency_hz(ss) is not None) is predicted

    def test_no_peak_returns_none_rather_than_a_sweep_edge(self):
        # G44's failure mode one level up: a monotone response must not report
        # the top of a search range as a peak.
        ss = deq.SmallSignal(g_dc=1.0, f_zero_hz=20e9, f_pole1_hz=22e9,
                             f_pole2_hz=1e9, peaking_db=0.0)
        assert peak_frequency_hz(ss) is None


class TestMatchedCtle:
    @pytest.mark.parametrize("boost", [3.0, 4.5, 6.0, 8.5, 10.0, 12.0])
    def test_it_delivers_exactly_the_requested_boost_at_the_requested_place(self, boost):
        c = matched_ctle(boost)
        assert c.realised_peaking_db == pytest.approx(boost, abs=1e-9)
        assert c.realised_f_peak_hz == pytest.approx(NYQUIST_HZ, rel=1e-9)

    @pytest.mark.parametrize("boost", [3.0, 8.5, 12.0])
    def test_both_s3_readings_coincide_by_construction(self, boost):
        # CLAUDEwa.md §3: peak-to-DC (a) and boost at Nyquist (b) are different
        # numbers with possibly opposite signs. Pinning the peak AT Nyquist
        # makes them the same, which removes the ambiguity from every number
        # derived through this CTLE.
        c = matched_ctle(boost)
        nyq_boost = deq.transfer_db(NYQUIST_HZ, c.ss) - 20.0 * math.log10(c.ss.g_dc)
        assert nyq_boost == pytest.approx(c.realised_peaking_db, abs=1e-9)

    def test_the_gain_convention_is_shape_only(self):
        assert matched_ctle(6.0).ss.g_dc == 1.0

    def test_the_zero_sits_below_both_poles(self):
        c = matched_ctle(8.5)
        assert c.ss.f_zero_hz < c.ss.f_pole1_hz < c.ss.f_pole2_hz

    def test_more_boost_needs_more_degeneration(self):
        k = [matched_ctle(b).ss.f_pole1_hz / matched_ctle(b).ss.f_zero_hz
             for b in (3.0, 6.0, 9.0, 12.0)]
        assert all(k[i] < k[i + 1] for i in range(len(k) - 1))

    def test_every_boost_is_reachable_and_what_pays_for_it_is_dc_gain(self):
        # MEASURED, and recorded because the expectation going in was the
        # opposite. With the peak PINNED at Nyquist and the DC gain left free,
        # the two-condition solve succeeds at every boost from 0.5 to 60 dB and
        # every second pole from 0.1 to 100 GHz: nothing in the small-signal
        # algebra forbids a large boost, it just pushes the zero down.
        #
        # What pays for it is the degeneration factor k = f_p1/f_z, and in a
        # real device A_dc = gm*RL/k — so the price of boost is DC GAIN, and
        # the binding constraint is the device's, not the topology's.
        # `matched_ctle`'s "no 1-zero/2-pole CTLE supplies ..." branch is
        # therefore a guard that nothing in this project's range trips.
        for f_p2 in (0.1e9, 1e9, 8.6e9, 100e9):
            for boost in (0.5, 3.0, 8.5, 12.0, 25.0, 60.0):
                c = matched_ctle(boost, f_pole2_hz=f_p2)
                assert c.realised_peaking_db == pytest.approx(boost, abs=1e-9)
                assert c.ss.f_pole1_hz / c.ss.f_zero_hz > 1.0

    def test_a_non_positive_boost_is_rejected(self):
        with pytest.raises(ValueError, match="target_boost_db must be positive"):
            matched_ctle(0.0)

    def test_the_default_second_pole_comes_from_measured_numbers(self):
        # rl = 565 ohm (design 432, the S9 survivor) and cl_mid = 32.63 fF
        # (CL_RANGE.md). Derived, not chosen.
        assert DEFAULT_F_POLE2_HZ == pytest.approx(
            1.0 / (2 * math.pi * 565.0 * 32.63e-15), rel=1e-12)
        assert 8.0e9 < DEFAULT_F_POLE2_HZ < 9.0e9

    def test_s3_membership_is_reported_not_assumed(self):
        assert matched_ctle(6.0).meets_s3_peaking
        assert not matched_ctle(2.0).meets_s3_peaking     # below S3's 3 dB floor


# ─────────────────────────────────────────────────────────────────────────────
# Cursor extraction — the hand-computed references
# ─────────────────────────────────────────────────────────────────────────────


class TestCursorHandComputedReferences:
    def test_a_lossless_channel_reproduces_the_tx_pulse_exactly(self):
        # THE reference case. |H| = 1 everywhere, so the minimum-phase
        # reconstruction is a unit impulse and the pulse response IS the TX
        # pulse. Everything downstream — convolution, phase search, volts —
        # is pinned by this one comparison.
        tx = PCIE_GEN2_TX
        cs = extract_cursors(ChannelModel(0.0), tx)
        assert cs.h0_v == pytest.approx(tx.c0 * tx.symbol_amplitude_v, rel=1e-12)
        assert cs.taps[1] == pytest.approx(tx.c1 * tx.symbol_amplitude_v, rel=1e-12)
        assert cs.dfe_tap == pytest.approx(tx.c1 / tx.c0, rel=1e-12)
        for k in (-2, -1, 2, 3, 4):
            assert abs(cs.taps[k]) < 1e-15
        assert cs.residual_fraction < 1e-12
        assert cs.eye_h_v == pytest.approx(2.0 * tx.c0 * tx.symbol_amplitude_v, rel=1e-12)

    @pytest.mark.parametrize("ch", channel_family(), ids=str)
    def test_the_cursors_sum_to_the_transmitters_long_run_level(self, ch):
        # The channel is transparent at DC, so a long run of identical bits
        # must arrive at exactly the de-emphasised level and nothing else. This
        # is the physical statement that replaced the deleted DC-loss constant,
        # checked end to end through the whole convolution.
        cs = extract_cursors(ch, PCIE_GEN2_TX)
        assert len(cs.taps) == cs.n_ui_scanned            # whole buffer, once
        assert sum(cs.taps.values()) == pytest.approx(
            PCIE_GEN2_TX.long_run_level_v, rel=1e-6)

    def test_the_lossless_case_also_holds_without_de_emphasis(self):
        tx = TxDeEmphasis(NO_DE_EMPHASIS_DB)
        cs = extract_cursors(ChannelModel(0.0), tx)
        assert cs.h0_v == pytest.approx(tx.symbol_amplitude_v, rel=1e-12)
        assert abs(cs.taps[1]) < 1e-15
        assert cs.dfe_tap == pytest.approx(0.0, abs=1e-12)


class TestCursorExtraction:
    def test_the_sampling_phase_maximises_h0(self):
        # The phase search is argmax of the pulse response, because the sample
        # grid IS the oversampled grid. Checked directly against every other
        # available phase.
        ch = ChannelModel(9.0, BALANCED)
        pr = pulse_response(ch, PCIE_GEN2_TX)
        cs = extract_cursors(ch, PCIE_GEN2_TX)
        osr = cs.osr
        best = max(pr[phi::osr].max() for phi in range(osr))
        assert cs.h0_v == pytest.approx(best, rel=1e-15)

    @pytest.mark.parametrize("ch", channel_family(), ids=str)
    def test_the_reported_window_is_populated_and_normalised(self, ch):
        cs = extract_cursors(ch, PCIE_GEN2_TX)
        row = cs.reported_row()
        assert set(row) == set(REPORTED_TAPS)
        assert row[0] == pytest.approx(1.0)
        assert all(math.isfinite(v) for v in row.values())

    @pytest.mark.parametrize("ch", channel_family(), ids=str)
    def test_the_dfe_tap_is_the_first_postcursor(self, ch):
        cs = extract_cursors(ch, PCIE_GEN2_TX)
        assert cs.dfe_tap == pytest.approx(cs.normalised(1))

    @pytest.mark.parametrize("ch", channel_family(), ids=str)
    def test_the_residual_excludes_h0_and_h1_and_nothing_else(self, ch):
        # A 1-tap DFE cancels exactly one post-cursor. The definition of
        # "residual" is the whole finding, so it is pinned rather than trusted.
        cs = extract_cursors(ch, PCIE_GEN2_TX)
        expect = sum(abs(v) for k, v in cs.taps.items()
                     if k not in (0, 1) and -1e9 < k < 1e9)
        assert cs.residual_abs_v == pytest.approx(expect, rel=1e-12)
        assert cs.residual_abs_v == pytest.approx(
            cs.precursor_abs_v + cs.postcursor_residual_abs_v, rel=1e-12)

    def test_more_loss_means_more_residual_isi(self):
        r = [extract_cursors(ChannelModel(il, BALANCED), PCIE_GEN2_TX).residual_fraction
             for il in (3.0, 6.0, 9.0, 12.0)]
        assert all(r[i] < r[i + 1] for i in range(len(r) - 1))

    def test_the_split_ratio_changes_the_residual_at_a_fixed_headline_loss(self):
        # 5c: a scalar cannot represent a channel. Same 12 dB at Nyquist; the
        # skin-dominated member leaves materially more ISI a 1-tap DFE cannot
        # reach, because sqrt(f) leaves a long slowly-decaying tail.
        skin = extract_cursors(ChannelModel(12.0, SKIN_DOMINATED), PCIE_GEN2_TX)
        diel = extract_cursors(ChannelModel(12.0, DIELECTRIC_DOMINATED), PCIE_GEN2_TX)
        assert skin.residual_fraction > 1.3 * diel.residual_fraction

    def test_de_emphasis_shrinks_the_first_postcursor(self):
        # That is what a post-cursor pre-canceller does, and it is why the DFE
        # tap it leaves behind is smaller.
        ch = ChannelModel(12.0, BALANCED)
        off = extract_cursors(ch, TxDeEmphasis(NO_DE_EMPHASIS_DB)).dfe_tap
        on = extract_cursors(ch, TxDeEmphasis(PCIE_GEN2_DE_EMPHASIS_DB)).dfe_tap
        deep = extract_cursors(ch, TxDeEmphasis(PCIE_GEN2_DE_EMPHASIS_OPTION_DB)).dfe_tap
        assert off > on > deep

    def test_an_inverted_pulse_is_refused_rather_than_silently_flipped(self, monkeypatch):
        # A sign flip anywhere upstream would give a plausible-looking cursor
        # set with every tap negated, which is the exact shape of bug this
        # project keeps finding. The guard fires on the pulse response itself,
        # so it is exercised by feeding one in.
        import nebula.link.cursors as cur

        monkeypatch.setattr(cur, "pulse_response",
                            lambda *a, **k: -np.abs(np.linspace(1.0, 0.0, 32768)))
        with pytest.raises(ValueError, match="non-positive maximum"):
            cur.extract_cursors(ChannelModel(6.0), PCIE_GEN2_TX)

    def test_reflections_land_where_a_1_tap_dfe_cannot_reach_them(self):
        ch = ChannelModel(9.0, BALANCED)
        base = extract_cursors(ch, PCIE_GEN2_TX)
        with_r = extract_cursors(ch.with_reflections(), PCIE_GEN2_TX)
        assert with_r.residual_fraction > base.residual_fraction
        # The echoes sit at 2 and 5 UI, so h2 moves and h1 essentially does not.
        assert abs(with_r.normalised(2)) > abs(base.normalised(2))


class TestCtleInFront:
    @pytest.mark.parametrize("il", [6.0, 9.0, 12.0])
    def test_a_matched_ctle_reduces_the_residual_isi(self, il):
        ch = ChannelModel(il, BALANCED)
        burden = PCIE_GEN2_TX.burden_db(il)
        bare = extract_cursors(ch, PCIE_GEN2_TX)
        eq = extract_cursors(ch, PCIE_GEN2_TX, ctle=matched_ctle(burden))
        assert eq.residual_fraction < bare.residual_fraction

    def test_the_ctle_is_applied_on_a_signed_frequency_axis(self):
        # A Hermitian response is what keeps the time-domain result real. A
        # folded (non-negative) axis would give a complex impulse response and
        # a silently wrong cursor set.
        ch = ChannelModel(9.0, BALANCED)
        pr = pulse_response(ch, PCIE_GEN2_TX, ctle=matched_ctle(5.5))
        assert np.all(np.isfinite(pr))
        assert pr.dtype == float


class TestEyeEstimate:
    @pytest.mark.parametrize("ch", channel_family(), ids=str)
    def test_an_open_eye_reports_the_gain_s8_would_need(self, ch):
        est = eye_estimate(extract_cursors(ch, PCIE_GEN2_TX))
        if est.eye_open:
            assert est.eye_h_v_at_unity_dc_gain > 0.0
            assert est.required_dc_gain == pytest.approx(
                SPEC_EYE_H_MIN_V / est.eye_h_v_at_unity_dc_gain)
        else:
            assert est.required_dc_gain == math.inf

    def test_a_closed_eye_cannot_be_reopened_by_gain(self):
        # The point of reporting the residual as a RATIO: gain scales signal
        # and ISI identically, so `residual >= 1` is a verdict about the
        # topology and not about the device.
        from nebula.link.cursors import CursorSet

        closed = CursorSet(taps={0: 1.0, 1: 0.2, 2: 1.5}, h0_v=1.0, dfe_tap=0.2,
                           precursor_abs_v=0.0, postcursor_residual_abs_v=1.5,
                           residual_abs_v=1.5, osr=64, cursor_index=0,
                           n_ui_scanned=3)
        assert not closed.eye_open
        assert closed.eye_h_v == 0.0
        assert eye_estimate(closed).required_dc_gain == math.inf
