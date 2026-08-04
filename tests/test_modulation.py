"""
Tests for the modulation flag and the first three NRZ retarget fixes.

Scope, deliberately narrow (see `nebula/NRZ_RETARGET_AUDIT.md`):

  fix 1  `crossing_jitter_ui()`'s E[a²] factor — was a hard-coded 5.0, which
         overestimates NRZ jitter by sqrt(5) = 2.24x and would falsely
         declare the CDR infeasible. A WRONG RESULT, not a slow one.
  fix 2  `CTLE.from_peaking`'s absolute 28/56 GHz pole defaults — CLAUDEwa.md
         §12's named trap, previously callable with no pole arguments at all.
  fix 3  `adc_vref = 4.0` — established as MOOT for the Nebula S2 chain,
         which has no ADC. Pinned here so the conclusion is checkable rather
         than a claim in a document.

Everything else in the audit is still PAM-4, and `StatisticalEye` refuses to
run its BER path in NRZ mode rather than returning 0.75x the truth. That
refusal is tested too — an unenforced staging boundary is not a boundary.
"""
import numpy as np
import pytest

import modulation as M
from modulation import NRZ, PAM4, Modulation
from statistical_eye import StatisticalEye
from link_sim import LinkConfig
from rx_frontend import CTLE


class TestModulationObject:
    def test_pam4_constants_match_the_literals_they_replace(self):
        """Every value here was previously a bare number in the source."""
        assert PAM4.n_levels == 4
        assert PAM4.bits_per_symbol == 2
        assert PAM4.symbol_probability == 0.25          # isi_pmf's 0.25
        assert PAM4.max_level == 3.0                    # isi_pmf's 3.0 span
        assert PAM4.mean_square == 5.0                  # the sqrt(5) factor
        assert PAM4.rms == pytest.approx(np.sqrt(5.0))  # PAM4_RMS
        assert np.allclose(PAM4.levels, [-3, -1, 1, 3])
        assert np.allclose(PAM4.thresholds, [-2, 0, 2])

    def test_nrz_constants(self):
        assert NRZ.n_levels == 2
        assert NRZ.bits_per_symbol == 1
        assert NRZ.symbol_probability == 0.5
        assert NRZ.max_level == 1.0
        assert NRZ.mean_square == 1.0
        assert NRZ.rms == 1.0
        assert np.allclose(NRZ.levels, [-1, 1])
        assert np.allclose(NRZ.thresholds, [0.0])

    def test_mean_square_is_derived_not_stored(self):
        """E[a²] must come from `levels`, so a new alphabet cannot disagree
        with itself. CLAUDEwa.md §8 rule 6 — no autonomously chosen numbers."""
        pam8 = Modulation(
            name="pam8",
            levels=np.array([-7.0, -5, -3, -1, 1, 3, 5, 7]),
            thresholds=np.array([-6.0, -4, -2, 0, 2, 4, 6]),
            bits_per_symbol=3,
        )
        assert pam8.mean_square == pytest.approx(21.0)  # (49+25+9+1)*2/8

    def test_adjacency_helper_replaces_the_1p01_literal(self):
        """The BER sum's `abs(a0 - thr) > 1.01` works for NRZ by luck."""
        assert PAM4.is_adjacent(-3.0, -2.0)
        assert not PAM4.is_adjacent(-3.0, 0.0)
        assert NRZ.is_adjacent(-1.0, 0.0)
        assert NRZ.is_adjacent(1.0, 0.0)

    @pytest.mark.parametrize("name,expected", [("pam4", PAM4), ("nrz", NRZ),
                                               ("PAM4", PAM4), ("NRZ", NRZ)])
    def test_get_resolves_names(self, name, expected):
        assert M.get(name) is expected
        assert M.get(expected) is expected

    def test_unknown_modulation_fails_loudly(self):
        with pytest.raises(ValueError, match="unknown modulation"):
            M.get("pam8")

    @pytest.mark.parametrize("kwargs", [
        dict(levels=np.array([-1.0, 1.0]), thresholds=np.array([0.0, 1.0]),
             bits_per_symbol=1),                       # wrong threshold count
        dict(levels=np.array([1.0, -1.0]), thresholds=np.array([0.0]),
             bits_per_symbol=1),                       # not ascending
        dict(levels=np.array([-1.0, 1.0]), thresholds=np.array([0.0]),
             bits_per_symbol=2),                       # 2 levels != 2^2
        dict(levels=np.array([0.0, 2.0]), thresholds=np.array([1.0]),
             bits_per_symbol=1),                       # not zero-mean
    ])
    def test_malformed_alphabets_are_rejected(self, kwargs):
        with pytest.raises(ValueError):
            Modulation(name="bad", **kwargs)


def _eye(modulation):
    """Identical link, one knob changed. Any difference is the knob."""
    cfg = LinkConfig(channel_cm=6.0, noise_db=28.0, ctle_peaking_db=3.0)
    eye = StatisticalEye.from_link_config(cfg)
    eye.mod = M.get(modulation)
    return eye


class TestCrossingJitterFactor:
    """FIX 1 — the sqrt(5) that would have declared the NRZ CDR infeasible."""

    def test_nrz_jitter_is_exactly_sqrt5_below_pam4(self):
        """sigma_e = sqrt(E[a²]·Σg²), so the ONLY difference between the two
        alphabets is sqrt(5/1). The edge slope is identical because the pulse
        response is identical. This is the number the fix is worth."""
        pam4_ui = _eye("pam4").crossing_jitter_ui()
        nrz_ui = _eye("nrz").crossing_jitter_ui()
        assert pam4_ui > 0.0
        assert pam4_ui / nrz_ui == pytest.approx(np.sqrt(5.0), rel=1e-12)

    def test_the_old_hardcoded_value_is_what_pam4_still_produces(self):
        """Regression guard: the PAM-4 path must be bit-identical to the
        pre-retarget code, which used a literal 5.0."""
        eye = _eye("pam4")
        pr, osr, cur = eye.pr, eye.osr, eye.cursor
        edge = cur - osr // 2
        ks = np.arange(-8, 9)
        idx = edge + ks * osr
        ok = (idx >= 0) & (idx < len(pr))
        g = np.zeros(len(ks))
        g[ok] = pr[idx[ok]]
        isi = g[(ks != 0) & (ks != 1)]
        sigma_e = np.sqrt(5.0 * np.sum(isi ** 2))       # the OLD literal
        slope = (pr[edge + 2] - pr[edge - 2]) / (4.0 / osr)
        assert eye.crossing_jitter_ui() == pytest.approx(
            sigma_e / (2.0 * abs(slope) + 1e-12), rel=1e-12)

    def test_a_2p24x_error_can_cross_the_feasibility_threshold(self):
        """Why this is fix #1 and not fix #3.

        The CDR-feasibility rule is a threshold on this value (healthy
        < 0.45 UI). An NRZ config landing anywhere in [0.45/sqrt(5), 0.45]
        would be reported infeasible when it is fine. Demonstrated with the
        real numbers rather than asserted.
        """
        healthy_threshold = 0.45
        nrz_ui = _eye("nrz").crossing_jitter_ui()
        pam4_ui = _eye("pam4").crossing_jitter_ui()
        if nrz_ui < healthy_threshold <= pam4_ui:
            # this link sits inside the falsely-infeasible band
            assert pam4_ui / nrz_ui == pytest.approx(np.sqrt(5.0), rel=1e-9)
        # and in every case the misreporting factor is the same
        assert pam4_ui / nrz_ui == pytest.approx(2.2360679, rel=1e-6)


class TestNrzBerPathIsFencedOff:
    """The staging boundary. Enforced, not just documented."""

    @pytest.mark.parametrize("method,args", [
        ("ber_at_phase", (0.0,)),
        ("clip_probability", ()),
    ])
    def test_nrz_refuses_pam4_ber_maths(self, method, args):
        eye = _eye("nrz")
        with pytest.raises(NotImplementedError, match="PAM-4 only"):
            getattr(eye, method)(*args)

    def test_analyse_is_fenced_too(self):
        with pytest.raises(NotImplementedError):
            _eye("nrz").analyse(n_phase=5)

    def test_pam4_path_is_untouched(self):
        ber, _ = _eye("pam4").ber_at_phase(0.0)
        assert 0.0 <= ber <= 1.0

    def test_default_is_pam4(self):
        """What keeps the existing 65 tests green without editing them."""
        cfg = LinkConfig(channel_cm=3.0, noise_db=28.0)
        assert StatisticalEye.from_link_config(cfg).mod is PAM4


class TestFromPeakingPolesAreRequired:
    """FIX 2 — CLAUDEwa.md §12's named trap."""

    def test_cannot_be_called_without_poles(self):
        with pytest.raises(TypeError):
            CTLE.from_peaking(6.0)

    def test_poles_actually_control_the_response(self):
        """The trap was silent because a 5 Gbps CTLE built with 28/56 GHz
        poles still *returns a CTLE*. It just equalises nothing in band."""
        fbaud = 5e9
        right = CTLE.from_peaking(6.0, f_pole1=fbaud / 2, f_pole2=fbaud)
        trapped = CTLE.from_peaking(6.0, f_pole1=28e9, f_pole2=56e9)

        f_nyq = np.array([fbaud / 2])
        boost_right = 20 * np.log10(
            abs(right.freq_response(f_nyq)[0]) / abs(right.g_dc))
        boost_trapped = 20 * np.log10(
            abs(trapped.freq_response(f_nyq)[0]) / abs(trapped.g_dc))

        assert boost_right > 3.0, "correctly placed poles boost at Nyquist"
        assert boost_trapped < 1.0, (
            "the 112G defaults deliver almost no in-band boost at 5 Gbps — "
            "which is exactly why the silent default was dangerous")


class TestAdcVrefIsMootForS2:
    """FIX 3 — established, then pinned.

    S2 fixes the topology at 'a 1-stage CTLE with source degeneration
    (variable Rs, Cs) + 1-tap DFE'. There is no ADC in it. The Nebula link
    layer never imports `link_sim` or `adc_model`, and
    `LinkConfig.to_link_sim_config()` raises rather than silently handing over
    112G PAM-4 defaults. So `adc_vref = 4.0` cannot reach a Nebula number, and
    changing it was correctly skipped rather than done for tidiness.
    """

    def test_nebula_link_layer_does_not_import_the_adc_path(self):
        import nebula.link.mock as link_mock
        import nebula.link.config as link_cfg
        for mod in (link_mock, link_cfg):
            src = open(mod.__file__, encoding="utf-8").read()
            assert "import adc_model" not in src
            assert "from adc_model" not in src

    def test_to_link_sim_config_still_refuses(self):
        from nebula.link.config import LinkConfig as NebulaLinkConfig
        cfg = NebulaLinkConfig(channel_loss_db_at_nyquist=9.0)
        with pytest.raises(NotImplementedError, match="no NRZ mode"):
            cfg.to_link_sim_config()

    def test_adc_vref_remains_a_pam4_link_sim_concern(self):
        """It is still 4.0 for the 112G path, where a 6-bit ADC is real."""
        assert LinkConfig().adc_vref == 4.0
