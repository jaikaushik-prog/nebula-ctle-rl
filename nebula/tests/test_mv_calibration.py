"""
The millivolt calibration test. CLAUDEwa.md §5.3(a).

    "This is the highest-risk silent bug in the project — a wrong scale factor
     produces plausible-looking numbers that are meaningless. Write a
     dedicated test with a hand-computed expected value."

Every expected value below is computed by hand in the comment above it. No
value here is produced by calling the code under test with different
arguments, because that only proves the code is self-consistent — which a
factor-of-two error also is.

The arithmetic, once, in full
-----------------------------
    |H(f_nyquist)| = 4.0 V/V     (NOT g_dc — see convention C3)
    v_in_diff_pp   = 100 mV
    vout_swing_v   = 600 mV      (compression limit)

    output swing  = 4.0 * 100 mV = 400 mV pp
    400 mV < 600 mV, so the small-signal model is still valid (C4)

    NRZ symbols are +/-1, so a fully open eye is 2.0 normalised units and
    spans the whole 400 mV:

        1.0 normalised unit = 200 mV
        2.0 normalised (ideal eye) = 400 mV
        0.5 normalised = 100 mV  <- exactly the S8 threshold
"""

from __future__ import annotations

import math

import pytest

from nebula.common import design_equations as deq
from nebula.link.calibration import (
    NRZ_IDEAL_EYE_NORM,
    check_compression,
    normalized_to_volts,
    output_swing_pp_v,
    volts_to_normalized,
)

G_NYQ = 4.0
V_IN_PP = 0.100
V_SWING = 0.600


class TestOutputSwing:
    def test_hand_computed(self):
        # 4.0 * 100 mV = 400 mV.
        assert output_swing_pp_v(G_NYQ, V_IN_PP) == pytest.approx(0.400)

    def test_unity_gain_hand_computed(self):
        # 1.0 * 100 mV = 100 mV. Guards the trivial case where a stray factor
        # of two would otherwise hide behind a plausible gain.
        assert output_swing_pp_v(1.0, V_IN_PP) == pytest.approx(0.100)

    def test_does_not_clamp(self):
        # 10.0 * 100 mV = 1000 mV. Even though that exceeds any sane
        # compression limit, this function returns the LINEAR prediction.
        # Clamping here is the bug this whole redesign removed: see C4.
        assert output_swing_pp_v(10.0, V_IN_PP) == pytest.approx(1.000)

    def test_rejects_gain_in_db(self):
        with pytest.raises(ValueError, match="linear/dB mix-up"):
            output_swing_pp_v(2000.0, V_IN_PP)

    @pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), float("inf")])
    def test_rejects_nonsense_inputs(self, bad):
        with pytest.raises(ValueError):
            output_swing_pp_v(bad, V_IN_PP)
        with pytest.raises(ValueError):
            output_swing_pp_v(G_NYQ, bad)


class TestGainIsPeakedNotDC:
    """Convention C3. Using g_dc understates the eye by exactly the peaking."""

    def test_nyquist_gain_exceeds_dc_gain_for_a_real_ctle(self):
        # gm=10 mS, Rs=400, Cs=1 pF, RL=250, CL=100 fF.
        ss = deq.predict(gm=10e-3, rs=400.0, cs=1e-12, rl=250.0, cl=100e-15)
        assert deq.gain_linear(2.5e9, ss) > ss.g_dc

    def test_the_ratio_is_the_boost_in_db(self):
        ss = deq.predict(gm=10e-3, rs=400.0, cs=1e-12, rl=250.0, cl=100e-15)
        boost_db = deq.transfer_db(2.5e9, ss) - 20 * math.log10(ss.g_dc)
        ratio = deq.gain_linear(2.5e9, ss) / ss.g_dc
        assert 20 * math.log10(ratio) == pytest.approx(boost_db)

    def test_using_dc_gain_would_understate_the_swing(self):
        # The concrete size of the bug that was fixed: with ~9 dB of boost at
        # Nyquist, a DC-gain calculation reports well under half the swing.
        ss = deq.predict(gm=10e-3, rs=400.0, cs=1e-12, rl=250.0, cl=100e-15)
        peaked = output_swing_pp_v(deq.gain_linear(2.5e9, ss), V_IN_PP)
        dc_only = output_swing_pp_v(ss.g_dc, V_IN_PP)
        assert peaked > dc_only * 2.0

    def test_gain_linear_and_transfer_db_agree(self):
        ss = deq.predict(gm=10e-3, rs=400.0, cs=1e-12, rl=250.0, cl=100e-15)
        for f in (1e6, 1e9, 2.5e9, 1e10):
            assert (20 * math.log10(deq.gain_linear(f, ss))
                    == pytest.approx(deq.transfer_db(f, ss)))


class TestCompressionIsAValidityCheckNotAClamp:
    """Convention C4."""

    def test_within_the_linear_range_returns_none(self):
        # 400 mV predicted vs a 600 mV limit: valid.
        assert check_compression(0.400, V_SWING) is None

    def test_exactly_at_the_limit_is_still_valid(self):
        assert check_compression(0.600, V_SWING) is None

    def test_beyond_the_limit_returns_a_specific_reason(self):
        reason = check_compression(1.000, V_SWING)
        assert reason is not None
        assert "1000.0 mVpp" in reason and "600.0 mVpp" in reason
        # The reason has to explain WHY this invalidates the result, not just
        # state the inequality — it is what lands in the experiment log.
        assert "no longer describes" in reason

    def test_the_reason_connects_compression_to_hd3(self):
        # Compression and collapsing HD3 are the same physical condition;
        # saying so in the log is what stops someone "fixing" it by widening
        # the limit.
        assert ".disto" in check_compression(1.000, V_SWING)

    def test_margin_can_tighten_the_check(self):
        # 500 mV against a 600 mV limit is fine at margin=1.0...
        assert check_compression(0.500, V_SWING) is None
        # ...and a violation if you demand 20% linear headroom (limit 480 mV).
        assert check_compression(0.500, V_SWING, margin=0.8) is not None

    def test_margin_cannot_loosen_the_check(self):
        # The one direction that would let a compressed design pass.
        with pytest.raises(ValueError, match="only make the check stricter"):
            check_compression(1.000, V_SWING, margin=1.5)

    def test_there_is_no_clamped_return_path(self):
        # A regression guard in the most literal form: the function returns a
        # reason or None, never a voltage. If someone reintroduces clamping it
        # will have to change this signature, which is the point.
        assert check_compression(1.000, V_SWING) != 0.600
        assert isinstance(check_compression(1.000, V_SWING), str)
        assert check_compression(0.400, V_SWING) is None


class TestNormalizedToVolts:
    """The factor of two. This is the test §5.3(a) asks for."""

    def test_ideal_eye_equals_the_full_peak_to_peak_swing(self):
        # 2.0 normalised == the full 400 mV pp swing.
        assert normalized_to_volts(NRZ_IDEAL_EYE_NORM, 0.400) == pytest.approx(0.400)

    def test_one_normalised_unit_is_half_the_swing(self):
        # 1.0 normalised (one symbol level) == 200 mV.
        assert normalized_to_volts(1.0, 0.400) == pytest.approx(0.200)

    def test_the_s8_threshold_in_normalised_units(self):
        # S8 wants > 100 mV. At a 400 mV pp swing that is 0.5 normalised.
        assert normalized_to_volts(0.5, 0.400) == pytest.approx(0.100)

    def test_a_closed_eye_is_zero_volts(self):
        assert normalized_to_volts(0.0, 0.400) == 0.0

    def test_end_to_end_hand_computed(self):
        # The full chain from the module docstring: |H(f_ny)|=4, v_in=100 mV pp,
        # swing limit 600 mV, eye 70% open (1.4 normalised).
        #   v_out_pp = 400 mV;  valid;  1.4 * 400/2 = 280 mV
        v_out_pp = output_swing_pp_v(G_NYQ, V_IN_PP)
        assert check_compression(v_out_pp, V_SWING) is None
        assert normalized_to_volts(1.4, v_out_pp) == pytest.approx(0.280)

    def test_end_to_end_compressed_produces_no_eye_at_all(self):
        # |H(f_ny)|=10 -> 1000 mV predicted against a 600 mV limit. Under the
        # old clamping behaviour this returned a confident 420 mV eye. It must
        # now produce no number.
        v_out_pp = output_swing_pp_v(10.0, V_IN_PP)
        assert v_out_pp == pytest.approx(1.000)
        assert check_compression(v_out_pp, V_SWING) is not None

    def test_rejects_an_eye_wider_than_the_symbol_spacing(self):
        with pytest.raises(ValueError, match="units bug"):
            normalized_to_volts(2.5, 0.400)

    def test_rejects_a_negative_eye(self):
        with pytest.raises(ValueError, match="negative"):
            normalized_to_volts(-0.1, 0.400)


class TestRoundTrip:
    def test_volts_to_normalized_is_the_exact_inverse(self):
        for amp in (0.0, 0.25, 1.0, 1.4, NRZ_IDEAL_EYE_NORM):
            v = normalized_to_volts(amp, 0.400)
            assert volts_to_normalized(v, 0.400) == pytest.approx(amp)

    def test_s8_spec_line_maps_into_normalised_units(self):
        # 100 mV at a 400 mV pp swing is 0.5 normalised — hand-computed.
        assert volts_to_normalized(0.100, 0.400) == pytest.approx(0.5)
        # ...and at a 250 mV pp swing it is 0.8, i.e. a much harder spec.
        # This is the whole reason the swing has to be carried through.
        assert volts_to_normalized(0.100, 0.250) == pytest.approx(0.8)


class TestScaleFactorGuards:
    """Tests that would fail under the three most likely wrong scale factors."""

    @pytest.mark.parametrize("amp,expected_v", [(2.0, 0.400), (1.0, 0.200), (0.5, 0.100)])
    def test_against_hand_table(self, amp, expected_v):
        assert normalized_to_volts(amp, 0.400) == pytest.approx(expected_v)

    def test_is_not_off_by_two(self):
        # A missing /2 would give 2.0 -> 800 mV; a spurious /2 would give
        # 2.0 -> 200 mV. Both are excluded by the assertion above, and this
        # states it explicitly so the intent survives a refactor.
        v = normalized_to_volts(NRZ_IDEAL_EYE_NORM, 0.400)
        assert not math.isclose(v, 0.800)
        assert not math.isclose(v, 0.200)
        assert math.isclose(v, 0.400)

    def test_ideal_eye_constant_is_two_not_one(self):
        # NRZ +/-1 spans 2.0. If someone "simplifies" this to 1.0 to mean
        # "full scale", every eye height doubles.
        assert NRZ_IDEAL_EYE_NORM == 2.0
