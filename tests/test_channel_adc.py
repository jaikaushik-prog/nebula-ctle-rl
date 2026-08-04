"""Unit tests: channel loss model, PAM-4 BER theory, ADC quantisation."""
import numpy as np
import pytest

from channel import Channel, ber_from_snr_pam4
from adc_model import ideal_quantize, sqnr_ideal, compute_sinad_enob
from pam4_chain import pam4_slicer, PAM4_LEVELS


class TestChannelLossModel:
    def test_il_matches_analytic(self):
        """|H| at any frequency must follow the skin+dielectric loss formula."""
        alpha_s, alpha_d, L = 0.30, 0.05, 30.0
        ch = Channel.from_loss_model(alpha_skin=alpha_s, alpha_diel=alpha_d,
                                     length_cm=L)
        for f_ghz in (5.0, 14.0, 28.0):
            il_expected = -(alpha_s * np.sqrt(f_ghz) + alpha_d * f_ghz) * L
            il_model = 20 * np.log10(
                np.interp(f_ghz * 1e9, ch.freq, np.abs(ch.H)))
            assert il_model == pytest.approx(il_expected, abs=0.1)

    def test_nyquist_loss_helper(self):
        ch = Channel.from_loss_model(length_cm=30.0)
        il = ch.nloss_at_nyquist(fbaud=56e9)
        # 28 GHz: -(0.3*sqrt(28) + 0.05*28)*30 = -89.6 dB
        assert il == pytest.approx(-89.6, abs=0.5)

    def test_pulse_response_causal_peak(self):
        ch = Channel.from_loss_model(length_cm=10.0)
        pr = ch.pulse_response(fbaud=56e9, osr=8)
        assert len(pr) > 0
        assert np.max(np.abs(pr)) > 0


class TestPAM4Theory:
    def test_ber_matches_montecarlo(self):
        """
        Corrected closed form BER = (3/8)·erfc(sqrt(SNR/10)) must match a
        brute-force Gray-coded slicer simulation. (The pre-audit formula was
        2x too high — erfc used where Q was meant.)
        """
        rng = np.random.default_rng(7)
        snr_db = 16.0
        n = 400_000
        syms = rng.choice(PAM4_LEVELS, n)
        sigma = np.sqrt(np.mean(PAM4_LEVELS**2) / 10**(snr_db / 10))
        r = syms + rng.normal(0, sigma, n)
        d = pam4_slicer(r)
        # Symbol errors -> bit errors: Gray => 1 bit per symbol error (approx),
        # count actual bit errors through the Gray map
        from pam4_chain import gray_decode
        bits_tx = gray_decode(syms)
        bits_rx = gray_decode(d)
        ber_sim = np.mean(bits_tx != bits_rx)
        ber_theory = float(ber_from_snr_pam4(snr_db))
        assert ber_sim == pytest.approx(ber_theory, rel=0.15)

    def test_ber_monotonic_in_snr(self):
        b = ber_from_snr_pam4(np.array([10.0, 15.0, 20.0, 25.0]))
        assert np.all(np.diff(b) < 0)


class TestADC:
    def test_ideal_sqnr(self):
        """Full-scale sine through an ideal N-bit quantiser: SQNR ≈ 6.02N+1.76."""
        n_bits, n_samples, f_s = 6, 16384, 56e9
        # Coherent sampling: choose bin-centred frequency to avoid leakage
        f_in = 1013 / n_samples * f_s
        t = np.arange(n_samples) / f_s
        x = 0.99 * np.sin(2 * np.pi * f_in * t)
        xq, _ = ideal_quantize(x, n_bits, v_ref=1.0)
        sinad, enob = compute_sinad_enob(xq, x, f_in, f_s, window=True)
        assert sinad == pytest.approx(sqnr_ideal(n_bits), abs=1.5)

    def test_quantizer_is_monotonic(self):
        x = np.linspace(-1, 1, 10_000)
        _, codes = ideal_quantize(x, 6, v_ref=1.0)
        assert np.all(np.diff(codes) >= 0)

    def test_quantizer_clips_at_rails(self):
        x = np.array([-5.0, 5.0])
        _, codes = ideal_quantize(x, 6, v_ref=1.0)
        assert codes[0] == 0 and codes[1] == 63
