"""
Interface tests for the link layer.

    def evaluate_link(dev: DeviceResult, cfg: LinkConfig) -> LinkResult

The two things this boundary must never do:

  * treat a failed DeviceResult as zeros — that hands the RL loop a finite
    reward for a design that does not simulate;
  * report eye height in anything other than volts (§5.3a — the dedicated
    arithmetic lives in test_mv_calibration.py).
"""

from __future__ import annotations

import inspect
import math

import numpy as np
import pytest

from nebula.common.types import (
    Corner,
    DeviceResult,
    LinkResult,
    TT_NOMINAL,
    SPEC_EYE_H_MIN_V,
)
from nebula.device import mock as device_mock
from nebula.link import mock as link_mock
from nebula.link.config import LinkConfig
from nebula.link.interface import (
    LinkEvaluator,
    propagate_device_failure,
    safe_evaluate_link,
)


@pytest.fixture
def dev(ref_params) -> DeviceResult:
    d = device_mock.evaluate(ref_params, TT_NOMINAL)
    assert d.ok, d.fail_reason
    return d


def boost_at_nyquist_db(dev: DeviceResult) -> float:
    """The CTLE's boost over DC at 2.5 GHz, from its poles.

    The equalisation tests below are written RELATIVE to this rather than
    against fixed dB numbers. A CTLE is only "under-equalising" with respect
    to a particular channel loss, so a test that hard-codes "8 dB is a lossy
    channel" silently changes meaning the moment the reference sizing moves.
    """
    from nebula.common import design_equations as deq

    ss = deq.SmallSignal(
        g_dc=dev.g_dc, f_zero_hz=dev.f_zero_hz, f_pole1_hz=dev.f_pole1_hz,
        f_pole2_hz=dev.f_pole2_hz, peaking_db=dev.peaking_db,
    )
    import math as _math

    return deq.transfer_db(2.5e9, ss) - 20.0 * _math.log10(dev.g_dc)


def cfg_with_tilt(dev: DeviceResult, tilt_offset_db: float, **kw) -> LinkConfig:
    """A LinkConfig whose CTLE BURDEN is the device's boost + `tilt_offset_db`.

    The equalisation tests are written against the burden, not absolute loss,
    because the burden is what the CTLE actually undoes. `tilt_offset_db=0` is
    a perfectly matched channel; positive is under-equalised, negative is over.

    `tx_de_emphasis_db` defaults to 0 HERE and nowhere else in the codebase.
    These tests isolate the CTLE against the channel, and PCIe Gen2's mandated
    -3.5 dB would otherwise shift every requested burden by 3.5 dB and clamp
    against `il >= 0` at the over-equalised end. The de-emphasis subtraction
    itself is tested directly in `TestTransmitterIsPartOfTheLink`.
    """
    kw.setdefault("tx_de_emphasis_db", 0.0)
    burden = max(boost_at_nyquist_db(dev) + tilt_offset_db, 0.0)
    return LinkConfig(channel_loss_db_at_nyquist=burden, **kw)


class TestProtocolConformance:
    def test_mock_satisfies_the_protocol(self):
        assert isinstance(link_mock.MockLink(), LinkEvaluator)

    def test_signature_matches_5_1(self):
        sig = inspect.signature(link_mock.evaluate_link)
        assert list(sig.parameters) == ["dev", "cfg"]


class TestLinkConfig:
    def test_channel_loss_is_required_because_it_is_the_swept_axis(self):
        # Not in the §3 spec table. Rather than default it, every config states
        # which point of the sweep it is, and results are reported as a curve.
        with pytest.raises(TypeError):
            LinkConfig()  # type: ignore[call-arg]

    def test_input_amplitude_is_derived_not_configured(self):
        # A second free constant would let a loss sweep leave the input
        # amplitude unchanged, which is not a thing that happens to a link.
        import dataclasses

        assert "v_in_diff_pp_v" not in {f.name for f in dataclasses.fields(LinkConfig)}
        assert isinstance(LinkConfig.v_in_diff_pp_v, property)

    def test_low_frequency_amplitude_hand_computed(self):
        # v_in_diff_pp_v is the LONG-RUN level: the transmitter's DE-EMPHASISED
        # level, attenuated by the channel at DC. The channel contributes
        # exactly 0 dB there (A*sqrt(0) + B*0), so with de-emphasis switched
        # off the long-run level IS the TX swing...
        flat = LinkConfig(channel_loss_db_at_nyquist=12.0, tx_de_emphasis_db=0.0)
        assert flat.tx_swing_diff_pp_v == pytest.approx(0.8)
        assert flat.v_in_diff_pp_v == pytest.approx(0.8)
        # ...and at exactly -6.0206 dB of de-emphasis it is halved, by hand.
        half = LinkConfig(channel_loss_db_at_nyquist=12.0,
                          tx_de_emphasis_db=-20 * math.log10(2.0))
        assert half.v_in_diff_pp_v == pytest.approx(0.4)

    def test_nyquist_amplitude_hand_computed(self):
        # The Nyquist content is attenuated by the FULL channel loss and NOT
        # by the de-emphasis: the 2-tap FIR has unity gain at Nyquist by
        # construction, because the transition bit carries full swing.
        # 0.8 V, 12.04 dB -> factor of exactly 4 -> 0.2 V.
        cfg = LinkConfig(channel_loss_db_at_nyquist=40 * math.log10(2.0))
        assert cfg.v_in_nyquist_pp_v == pytest.approx(0.2)
        assert cfg.tx.gain_at_nyquist == pytest.approx(1.0)

    def test_the_dc_loss_is_now_derived_and_is_exactly_zero(self):
        # THE RETIRED CONSTANT. The invented 1.0 dB DC-loss placeholder had
        # no provenance
        # and decided every compression verdict this project published. It is
        # deleted, not re-valued: a lossy transmission line's insertion loss at
        # DC is A*sqrt(0) + B*0 = 0, so the model answers the question the
        # constant was standing in for.
        for il in (0.0, 3.0, 12.0):
            for r in (0.0, 0.5, 1.0):
                cfg = LinkConfig(channel_loss_db_at_nyquist=il,
                                 channel_skin_fraction=r)
                assert cfg.channel_loss_db_at_dc == 0.0
                assert cfg.channel_tilt_db == pytest.approx(il)

    def test_tilt_is_what_the_ctle_equalises_and_the_tx_supplies_some_of_it(self):
        cfg = LinkConfig(channel_loss_db_at_nyquist=9.0)
        assert cfg.channel_tilt_db == pytest.approx(9.0)
        assert cfg.tx_tilt_db == pytest.approx(3.5)
        assert cfg.equalisation_burden_db == pytest.approx(5.5)

    def test_a_lossless_channel_passes_the_tx_swing_through_unchanged(self):
        cfg = LinkConfig(channel_loss_db_at_nyquist=0.0, tx_de_emphasis_db=0.0)
        assert cfg.v_in_diff_pp_v == pytest.approx(cfg.tx_swing_diff_pp_v)
        assert cfg.v_in_nyquist_pp_v == pytest.approx(cfg.tx_swing_diff_pp_v)
        assert cfg.channel_tilt_db == 0.0

    def test_more_loss_shrinks_the_nyquist_content_not_the_dc_level(self):
        lo = LinkConfig(channel_loss_db_at_nyquist=3.0)
        hi = LinkConfig(channel_loss_db_at_nyquist=12.0)
        # The channel is transparent at DC, so the long-run level is unchanged...
        assert hi.v_in_diff_pp_v == pytest.approx(lo.v_in_diff_pp_v)
        # ...and it is the Nyquist content that the extra loss eats.
        assert hi.v_in_nyquist_pp_v < lo.v_in_nyquist_pp_v
        assert hi.channel_tilt_db > lo.channel_tilt_db

    def test_a_high_pass_channel_cannot_be_constructed_at_all(self):
        # The old guard compared two configured loss numbers and rejected the
        # inverted pair. It is gone because the question can no longer be
        # asked: A*sqrt(f) + B*f with A, B >= 0 is monotone by construction.
        # The surviving failure mode is an out-of-range split.
        for il in (0.0, 3.0, 12.0):
            cfg = LinkConfig(channel_loss_db_at_nyquist=il)
            assert cfg.channel.passivity_report().passes
        with pytest.raises(ValueError, match="skin_fraction"):
            LinkConfig(channel_loss_db_at_nyquist=8.0, channel_skin_fraction=1.5)

    def test_tx_anchor_is_the_pcie_gen2_minimum(self):
        from nebula.link.config import PCIE_GEN2_TX_DIFF_PP_MIN_V

        # 0.8 Vpp differential, the minimum V_TX-DIFF-PP at 5.0 GT/s.
        # Secondary source only — see the provenance note in link/config.py.
        # Budgeting a receiver equaliser against the MINIMUM transmit swing is
        # the conservative choice; a typical value would make every eye number
        # optimistic by an unstated margin.
        assert PCIE_GEN2_TX_DIFF_PP_MIN_V == 0.8
        assert LinkConfig(channel_loss_db_at_nyquist=8.0).tx_swing_diff_pp_v == 0.8

    def test_the_loss_sweep_axis_exists_and_spans_s3(self):
        from nebula.link.config import DEFAULT_LOSS_SWEEP_DB, sweep_channel_loss
        from nebula.common.types import SPEC_PEAKING_DB_RANGE

        lo, hi = SPEC_PEAKING_DB_RANGE
        assert min(DEFAULT_LOSS_SWEEP_DB) == lo and max(DEFAULT_LOSS_SWEEP_DB) == hi
        cfgs = sweep_channel_loss()
        assert len(cfgs) == len(DEFAULT_LOSS_SWEEP_DB)
        assert [c.channel_loss_db_at_nyquist for c in cfgs] == list(DEFAULT_LOSS_SWEEP_DB)

    def test_compression_margin_cannot_be_loosened(self):
        with pytest.raises(ValueError, match="only make the validity check stricter"):
            LinkConfig(channel_loss_db_at_nyquist=8.0, compression_margin=1.2)

    def test_baud_rate_is_5g_not_56g(self):
        # CLAUDEwa.md §12: 112G defaults leaking into a 5 Gbps link.
        cfg = LinkConfig(channel_loss_db_at_nyquist=8.0)
        assert cfg.fbaud_hz == 5.0e9
        assert cfg.nyquist_hz == 2.5e9

    def test_dfe_is_fixed_at_one_tap_by_s2(self):
        with pytest.raises(ValueError, match="1-tap DFE"):
            LinkConfig(channel_loss_db_at_nyquist=8.0, n_dfe_taps=5)

    def test_insertion_loss_must_be_positive_dB(self):
        with pytest.raises(ValueError, match="insertion LOSS"):
            LinkConfig(channel_loss_db_at_nyquist=-8.0)

    def test_link_sim_conversion_refuses_until_the_nrz_retarget_lands(self):
        cfg = LinkConfig(channel_loss_db_at_nyquist=8.0)
        with pytest.raises(NotImplementedError, match="no NRZ mode yet"):
            cfg.to_link_sim_config()


class TestTransmitterIsPartOfTheLink:
    """PCIe Gen1/Gen2 specify TX de-emphasis and no receiver equaliser at all.

    So the CTLE is equalising a channel plus a partially pre-equalised
    transmitter, and leaving the transmitter out overstates its job by exactly
    the de-emphasis.
    """

    def test_the_default_is_the_gen2_mandate(self):
        from nebula.link.config import PCIE_GEN2_DE_EMPHASIS_DB

        assert PCIE_GEN2_DE_EMPHASIS_DB == -3.5
        assert LinkConfig(channel_loss_db_at_nyquist=8.0).tx_de_emphasis_db == -3.5

    @pytest.mark.parametrize("de_emph, expected", [(0.0, 0.0), (-3.5, 3.5), (-6.0, 6.0)])
    def test_the_tx_supplies_exactly_its_de_emphasis_as_tilt(self, de_emph, expected):
        cfg = LinkConfig(channel_loss_db_at_nyquist=12.0, tx_de_emphasis_db=de_emph)
        assert cfg.tx_tilt_db == pytest.approx(expected)
        assert cfg.equalisation_burden_db == pytest.approx(12.0 - expected)

    def test_the_burden_can_go_negative_and_that_is_a_real_answer(self):
        # At the bottom of the family the mandated de-emphasis already
        # over-equalises, so S3's 3 dB FLOOR is more boost than the link needs.
        cfg = LinkConfig(channel_loss_db_at_nyquist=3.0)
        assert cfg.equalisation_burden_db == pytest.approx(-0.5)

    def test_pre_emphasis_is_rejected(self):
        with pytest.raises(ValueError, match="de_emphasis_db must be <= 0"):
            LinkConfig(channel_loss_db_at_nyquist=8.0, tx_de_emphasis_db=+3.5)


class TestHappyPath:
    def test_returns_a_populated_link_result(self, dev, link_cfg):
        r = link_mock.evaluate_link(dev, link_cfg)
        assert r.ok, r.fail_reason
        for name in ("eye_h_v", "eye_w_ui", "ber", "dfe_tap"):
            v = getattr(r, name)
            assert v is not None and math.isfinite(v), name

    def test_eye_height_is_in_volts_not_normalised(self, dev, link_cfg):
        # The eye cannot exceed the actual output swing, which is the PEAKED
        # gain times the input amplitude (convention C3). A normalised value
        # (order 1-2) would blow straight through that bound.
        from nebula.common import design_equations as deq

        ss = deq.SmallSignal(
            g_dc=dev.g_dc, f_zero_hz=dev.f_zero_hz, f_pole1_hz=dev.f_pole1_hz,
            f_pole2_hz=dev.f_pole2_hz, peaking_db=dev.peaking_db,
        )
        v_out_pp = deq.gain_linear(link_cfg.nyquist_hz, ss) * link_cfg.v_in_diff_pp_v
        r = link_mock.evaluate_link(dev, link_cfg)
        assert r.ok
        assert 0.0 <= r.eye_h_v <= v_out_pp + 1e-12

    def test_the_swing_uses_the_peaked_gain_not_the_dc_gain(self, dev, link_cfg):
        # The bug this replaced: sizing the eye off g_dc understates it by
        # exactly the S3 peaking the circuit exists to provide.
        r = link_mock.evaluate_link(dev, link_cfg)
        assert r.ok
        dc_bound = dev.g_dc * link_cfg.v_in_diff_pp_v
        assert r.eye_h_v > dc_bound, (
            "eye fits inside the DC-gain bound, so the peaked response is "
            "probably not being used"
        )

    def test_eye_height_is_in_the_millivolt_range_that_s8_talks_about(self, dev, link_cfg):
        r = link_mock.evaluate_link(dev, link_cfg)
        assert r.ok
        # Not an assertion that the design passes S8 — an assertion that the
        # number is on the same scale as S8, i.e. tens to hundreds of mV.
        assert 1e-3 < r.eye_h_v < 1.0
        assert r.eye_h_mv == pytest.approx(r.eye_h_v * 1e3)

    def test_eye_width_is_in_ui(self, dev, link_cfg):
        r = link_mock.evaluate_link(dev, link_cfg)
        assert 0.0 <= r.eye_w_ui <= 1.0

    def test_ber_is_a_probability(self, dev, link_cfg):
        r = link_mock.evaluate_link(dev, link_cfg)
        assert 0.0 <= r.ber <= 1.0

    def test_bathtub_is_returned(self, dev, link_cfg):
        r = link_mock.evaluate_link(dev, link_cfg)
        assert isinstance(r.bathtub, np.ndarray)
        assert r.bathtub.size > 1
        assert np.all(r.bathtub >= 0.0) and np.all(r.bathtub <= 0.5)

    def test_s8_thresholds_are_comparable_without_conversion(self, dev, link_cfg):
        # The point of carrying volts through: this comparison is direct.
        r = link_mock.evaluate_link(dev, link_cfg)
        met = r.eye_h_v >= SPEC_EYE_H_MIN_V
        assert isinstance(met, (bool, np.bool_))


class TestDeviceFailurePropagation:
    def test_failed_device_gives_a_failed_link(self, link_cfg):
        d = DeviceResult.failed("ngspice: timestep too small")
        r = link_mock.evaluate_link(d, link_cfg)
        assert r.ok is False
        assert "timestep too small" in r.fail_reason

    def test_failed_link_carries_no_numbers(self, link_cfg):
        d = DeviceResult.failed("no convergence")
        r = link_mock.evaluate_link(d, link_cfg)
        assert r.eye_h_v is None and r.ber is None and r.eye_w_ui is None

    def test_propagate_helper_returns_none_for_a_good_device(self, dev):
        assert propagate_device_failure(dev) is None

    def test_propagate_helper_returns_a_failure_for_a_bad_device(self):
        out = propagate_device_failure(DeviceResult.failed("boom"))
        assert isinstance(out, LinkResult) and out.ok is False


class TestSafeEvaluateLink:
    def test_converts_an_exception_into_ok_false(self, dev, link_cfg):
        def exploding(d, c):
            raise ValueError("pole-zero fit produced a negative frequency")

        r = safe_evaluate_link(exploding, dev, link_cfg)
        assert r.ok is False
        assert "negative frequency" in r.fail_reason

    def test_catches_a_wrong_return_type(self, dev, link_cfg):
        r = safe_evaluate_link(lambda d, c: 0.5, dev, link_cfg)  # type: ignore[arg-type]
        assert r.ok is False and "expected LinkResult" in r.fail_reason


class TestBridgeBehaviour:
    """The device->link bridge is CLAUDEwa.md §5's "intellectually distinctive
    part". These pin the qualitative behaviour it must have."""

    def test_the_bridge_reads_the_poles_not_the_raw_ac_array(self, dev, link_cfg):
        # Blanking the diagnostic AC arrays must not change the answer: the
        # bridge is defined on (g_dc, f_zero, f_pole1, f_pole2).
        baseline = link_mock.evaluate_link(dev, link_cfg)
        dev.ac_mag_db = np.zeros_like(dev.ac_mag_db)
        after = link_mock.evaluate_link(dev, link_cfg)
        assert after.eye_h_v == pytest.approx(baseline.eye_h_v)

    def test_the_matched_channel_gives_the_biggest_eye(self, dev):
        # The CTLE opens the eye when its boost equals the channel TILT, and
        # closes it on either side. Both halves matter: without the right-hand
        # side the reward function is free to ask for infinite peaking.
        matched = link_mock.evaluate_link(dev, cfg_with_tilt(dev, 0.0))
        under = link_mock.evaluate_link(dev, cfg_with_tilt(dev, +6.0))
        over = link_mock.evaluate_link(dev, cfg_with_tilt(dev, -6.0))
        assert matched.eye_h_v > under.eye_h_v
        assert matched.eye_h_v > over.eye_h_v

    def test_a_lossier_channel_closes_the_eye(self, dev):
        # Both sides under-equalised, so the comparison isolates channel loss.
        easy = cfg_with_tilt(dev, +2.0)
        hard = cfg_with_tilt(dev, +10.0)
        assert (link_mock.evaluate_link(dev, hard).eye_h_v
                < link_mock.evaluate_link(dev, easy).eye_h_v)

    def test_the_dfe_tap_tracks_the_first_postcursor(self, dev):
        light = cfg_with_tilt(dev, +2.0)
        heavy = cfg_with_tilt(dev, +10.0)
        assert (link_mock.evaluate_link(dev, heavy).dfe_tap
                > link_mock.evaluate_link(dev, light).dfe_tap)

    def test_an_over_equalised_link_needs_no_dfe(self, dev):
        # Over-equalisation spills into the precursor, which the 1-tap DFE
        # cannot touch — so the tap goes to zero and the eye still closes.
        r = link_mock.evaluate_link(dev, cfg_with_tilt(dev, -8.0))
        assert r.ok and r.dfe_tap == 0.0

    def test_noisier_device_gives_worse_ber(self, dev, link_cfg):
        # Swept rather than a single 4x step, because the mock's noise floor is
        # optimistic enough (HANDOFF G16) that BER underflows to exactly 0.0
        # over a wide range — 4x more noise on a Q of ~450 is still Q of ~110.
        # Pinning the monotonicity across decades documents that limitation
        # instead of hiding behind a comparison of two zeros.
        base = dev.vn_in_vrms
        bers = []
        for mult in (1.0, 10.0, 100.0, 300.0, 1000.0):
            dev.vn_in_vrms = base * mult
            r = link_mock.evaluate_link(dev, link_cfg)
            assert r.ok, r.fail_reason
            bers.append(r.ber)

        assert bers == sorted(bers), f"BER must be non-decreasing in noise: {bers}"
        assert bers[-1] > 0.0, "the noisiest case must produce a representable BER"
        assert bers[-1] > bers[0], "1000x the noise must be strictly worse"

    def test_bigger_input_amplitude_gives_a_bigger_eye_in_volts(self, dev):
        small = LinkConfig(channel_loss_db_at_nyquist=8.0, tx_swing_diff_pp_v=0.4)
        big = LinkConfig(channel_loss_db_at_nyquist=8.0, tx_swing_diff_pp_v=0.9)
        assert (link_mock.evaluate_link(dev, big).eye_h_v
                > link_mock.evaluate_link(dev, small).eye_h_v)

    def test_compression_fails_the_evaluation_rather_than_clamping(self, dev, link_cfg):
        # Convention C4. A compressed stage means the AC/pole-zero model
        # behind every number in the DeviceResult has stopped describing the
        # circuit — so there is no eye to report. Clamping would let the policy
        # colonise the compressed region and score every proposal in it as
        # though it cleanly delivered the compression limit.
        dev.vout_swing_v = 0.001
        r = link_mock.evaluate_link(dev, link_cfg)
        assert r.ok is False
        assert "compressing" in r.fail_reason or "exceeds the linear limit" in r.fail_reason
        assert r.eye_h_v is None

    def test_a_tighter_compression_margin_fails_earlier(self, dev):
        loose = LinkConfig(channel_loss_db_at_nyquist=8.0, compression_margin=1.0)
        r_loose = link_mock.evaluate_link(dev, loose)
        assert r_loose.ok

        # Demand more linear headroom than the stage actually has.
        needed = r_loose.eye_h_v / dev.vout_swing_v
        strict = LinkConfig(channel_loss_db_at_nyquist=8.0,
                            compression_margin=min(needed * 0.5, 0.99))
        assert link_mock.evaluate_link(dev, strict).ok is False

    def test_jitter_narrows_the_eye(self, dev):
        clean = LinkConfig(channel_loss_db_at_nyquist=8.0,
                           rj_ui_rms=0.0)
        jittery = LinkConfig(channel_loss_db_at_nyquist=8.0,
                             rj_ui_rms=0.02)
        assert (link_mock.evaluate_link(dev, jittery).eye_w_ui
                < link_mock.evaluate_link(dev, clean).eye_w_ui)


class TestNeverRaises:
    @pytest.mark.parametrize(
        "field,value",
        [
            ("g_dc", 1e-30),
            ("f_zero_hz", 1e-3),
            ("f_pole2_hz", 1e-3),
            ("vout_swing_v", 1e-30),
            ("vn_in_vrms", 1e3),
            ("peaking_db", 1e6),
        ],
    )
    def test_pathological_device_results_do_not_raise(self, dev, link_cfg, field, value):
        setattr(dev, field, value)
        r = link_mock.evaluate_link(dev, link_cfg)
        assert isinstance(r, LinkResult)
        if not r.ok:
            assert r.fail_reason

    def test_every_corner_evaluates(self, ref_params, link_cfg):
        from nebula.common.types import all_corners

        for c in all_corners():
            d = device_mock.evaluate(ref_params, c)
            r = link_mock.evaluate_link(d, link_cfg)
            assert isinstance(r, LinkResult)
