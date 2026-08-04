"""
Tests for the §6 design equations, and the §6 cross-check gate.

    "at least one full extraction must be checked by hand against these. If
     A_dc from the wrapper disagrees with gm*RL/(1+gm*Rs/2), something
     upstream is broken and every downstream number is fiction. Do not
     proceed past that discrepancy."                     — CLAUDEwa.md §6

Every expected value here is computed by hand in the comment above it.
"""

from __future__ import annotations

import math

import pytest

from nebula.common import design_equations as deq

# A round operating point, chosen so the arithmetic is checkable by eye.
GM = 10e-3        # 10 mS
RS = 400.0        # ohms, full source-to-source
CS = 400e-15      # F
RL = 250.0        # ohms
CL = 100e-15      # F

# k = 1 + gm*Rs/2 = 1 + 0.010*400/2 = 1 + 2.0 = 3.0
K = 3.0


@pytest.fixture
def ss() -> deq.SmallSignal:
    return deq.predict(gm=GM, rs=RS, cs=CS, rl=RL, cl=CL)


class TestDesignEquations:
    def test_zero_frequency_hand_computed(self, ss):
        # w_z = 1/(Rs*Cs) = 1/(400 * 400e-15) = 6.25e9 rad/s
        # f_z = 6.25e9 / 2pi = 994.72 MHz
        assert ss.f_zero_hz == pytest.approx(6.25e9 / (2 * math.pi))
        assert ss.f_zero_hz == pytest.approx(994.7e6, rel=1e-3)

    def test_first_pole_is_k_times_the_zero(self, ss):
        # w_p1 = (1 + gm*Rs/2)/(Rs*Cs) = 3.0 * w_z
        assert ss.f_pole1_hz == pytest.approx(K * ss.f_zero_hz)
        assert ss.degeneration_factor == pytest.approx(K)

    def test_second_pole_hand_computed(self, ss):
        # w_p2 = 1/(RL*CL) = 1/(250 * 100e-15) = 4.0e10 rad/s
        # f_p2 = 4.0e10 / 2pi = 6.366 GHz
        assert ss.f_pole2_hz == pytest.approx(4.0e10 / (2 * math.pi))
        assert ss.f_pole2_hz == pytest.approx(6.366e9, rel=1e-3)

    def test_dc_gain_hand_computed(self, ss):
        # A_dc = gm*RL / k = 0.010 * 250 / 3.0 = 2.5/3 = 0.8333
        assert ss.g_dc == pytest.approx(2.5 / 3.0)

    def test_asymptotic_peaking_hand_computed(self, ss):
        # 20*log10(3.0) = 9.542 dB
        assert ss.peaking_db == pytest.approx(20 * math.log10(3.0))
        assert ss.peaking_db == pytest.approx(9.542, abs=1e-3)

    def test_the_factor_of_two_in_the_degeneration_term(self):
        # Rs is the FULL source-to-source resistance, so the half circuit sees
        # Rs/2. Dropping the /2 would make k = 5.0 here instead of 3.0 and put
        # every gain and peaking number 4.4 dB out.
        s = deq.predict(gm=GM, rs=RS, cs=CS, rl=RL, cl=CL)
        assert s.degeneration_factor == pytest.approx(3.0)
        assert s.degeneration_factor != pytest.approx(5.0)

    @pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), float("inf")])
    def test_rejects_nonphysical_values(self, bad):
        with pytest.raises(ValueError):
            deq.predict(gm=bad, rs=RS, cs=CS, rl=RL, cl=CL)
        with pytest.raises(ValueError):
            deq.predict(gm=GM, rs=bad, cs=CS, rl=RL, cl=CL)


class TestTransferFunction:
    def test_dc_gain_matches_at_low_frequency(self, ss):
        db = deq.transfer_db(1e3, ss)
        assert db == pytest.approx(20 * math.log10(ss.g_dc), abs=1e-6)

    def test_response_peaks_between_the_zero_and_the_second_pole(self, ss):
        peak_db, f_peak = deq.realised_peaking_db(ss)
        assert ss.f_zero_hz < f_peak < ss.f_pole2_hz * 3

    def test_realised_peaking_is_below_the_asymptote(self, ss):
        # The second pole erodes the boost. This is the same effect
        # rx_frontend.CTLE.from_peaking calibrates for, and S3 is written
        # against the realised number.
        peak_db, _ = deq.realised_peaking_db(ss)
        assert 0.0 < peak_db < ss.peaking_db

    def test_widely_spaced_poles_approach_the_asymptote(self):
        # With f_p2 >> f_p1 the realised peaking converges on 20*log10(k).
        s = deq.predict(gm=GM, rs=RS, cs=CS, rl=RL, cl=CL / 1000.0)
        peak_db, _ = deq.realised_peaking_db(s)
        assert peak_db == pytest.approx(s.peaking_db, abs=0.1)

    def test_more_degeneration_gives_more_peaking(self):
        low = deq.predict(gm=GM, rs=200.0, cs=CS, rl=RL, cl=CL)
        high = deq.predict(gm=GM, rs=800.0, cs=CS, rl=RL, cl=CL)
        assert (deq.realised_peaking_db(high)[0] > deq.realised_peaking_db(low)[0])


class TestCrossCheckGate:
    """The §6 hard gate. This is what stops a broken extraction reaching the
    link layer and producing a plausible, wrong eye contour."""

    def test_a_matching_extraction_passes(self, ss):
        agrees, delta = deq.cross_check_extraction(ss.g_dc, GM, RS, RL)
        assert agrees and delta == pytest.approx(0.0, abs=1e-9)

    def test_a_six_db_discrepancy_fails(self, ss):
        # Exactly the symptom of a dropped factor of two somewhere upstream.
        agrees, delta = deq.cross_check_extraction(ss.g_dc * 2.0, GM, RS, RL)
        assert not agrees
        assert delta == pytest.approx(6.02, abs=0.01)

    def test_a_small_discrepancy_is_tolerated(self, ss):
        # r_o, body effect and the second pole's DC contribution are all
        # neglected by the analytic form; half a dB is agreement.
        agrees, delta = deq.cross_check_extraction(ss.g_dc * 1.06, GM, RS, RL)
        assert agrees and delta < 1.0

    def test_the_default_tolerance_is_one_db(self, ss):
        assert deq.cross_check_extraction(ss.g_dc * 10 ** (0.9 / 20), GM, RS, RL)[0]
        assert not deq.cross_check_extraction(ss.g_dc * 10 ** (1.1 / 20), GM, RS, RL)[0]

    def test_a_nonpositive_extracted_gain_fails_rather_than_raising(self):
        agrees, delta = deq.cross_check_extraction(0.0, GM, RS, RL)
        assert not agrees and math.isinf(delta)


class TestMockDeviceObeysTheDesignEquations:
    """The mock is synthetic, but if it did not satisfy §6 it would be useless
    as a development target — the reward function would be tuned against
    physics that ngspice does not share."""

    def test_mock_gain_matches_the_analytic_form(self, ref_params):
        from nebula.common.types import TT_NOMINAL
        from nebula.device import mock as device_mock

        d = device_mock.evaluate(ref_params, TT_NOMINAL)
        assert d.ok, d.fail_reason

        # Recover k from the extracted pole/zero ratio, then check A_dc.
        k = d.f_pole1_hz / d.f_zero_hz
        gm = 2.0 * (k - 1.0) / ref_params["rs"]
        agrees, delta = deq.cross_check_extraction(
            d.g_dc, gm=gm, rs=ref_params["rs"], rl=ref_params["rl"]
        )
        assert agrees, f"mock disagrees with §6 by {delta:.3f} dB"


class TestBodyEffectCorrection:
    """Measured 2026-08-03 on the G1 hand-design point (ngspice, generic BSIM4).

    §6 as written assumes the bulk is tied to the source. In a bulk process it
    is not, and the resulting error is LARGER than §6's own 1 dB gate — so the
    equation as transcribed fails its own acceptance test on a correct circuit.
    """

    # G1 point: gm = 10.973 mS, gmbs = 3.583 mS, Rs = 800, RL = 120.
    GM, GMBS, RS_G1, RL_G1 = 10.973e-3, 3.583e-3, 800.0, 120.0
    SIM_G_DC_DB = -14.57      # ngspice, differential, 1 MHz

    def test_gmbs_defaults_to_zero_so_section_6_is_reproduced_verbatim(self):
        a = deq.predict(gm=self.GM, rs=self.RS_G1, cs=1e-12,
                        rl=self.RL_G1, cl=1e-12)
        b = deq.predict(gm=self.GM, rs=self.RS_G1, cs=1e-12,
                        rl=self.RL_G1, cl=1e-12, gmbs=0.0)
        assert a.g_dc == pytest.approx(b.g_dc)

    def test_section_6_as_written_fails_its_own_gate_on_the_g1_point(self):
        agrees, delta = deq.cross_check_extraction(
            10 ** (self.SIM_G_DC_DB / 20), self.GM, self.RS_G1, self.RL_G1)
        assert not agrees
        assert delta == pytest.approx(2.33, abs=0.05)

    def test_including_gmbs_makes_it_agree(self):
        agrees, delta = deq.cross_check_extraction(
            10 ** (self.SIM_G_DC_DB / 20), self.GM, self.RS_G1, self.RL_G1,
            gmbs=self.GMBS)
        assert agrees
        assert delta == pytest.approx(0.28, abs=0.05)

    def test_body_effect_lowers_gain_and_raises_the_degeneration_factor(self):
        no_body = deq.predict(gm=self.GM, rs=self.RS_G1, cs=1e-12,
                              rl=self.RL_G1, cl=1e-12)
        body = deq.predict(gm=self.GM, rs=self.RS_G1, cs=1e-12,
                           rl=self.RL_G1, cl=1e-12, gmbs=self.GMBS)
        assert body.g_dc < no_body.g_dc
        assert body.degeneration_factor > no_body.degeneration_factor
        assert body.peaking_db > no_body.peaking_db

    def test_negative_gmbs_is_rejected(self):
        with pytest.raises(ValueError, match="gmbs"):
            deq.predict(gm=self.GM, rs=self.RS_G1, cs=1e-12,
                        rl=self.RL_G1, cl=1e-12, gmbs=-1e-3)
