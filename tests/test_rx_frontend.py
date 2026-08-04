"""Unit tests: CTLE transfer function, noise enhancement, CDR lock/tracking."""
import numpy as np
import pytest

from rx_frontend import (CTLE, CDRSampler, SamplerConfig, agc_scale,
                         estimate_delay)
from pam4_chain import tx_waveform, PAM4_LEVELS


class TestCTLE:
    @pytest.mark.parametrize("pk", [3.0, 6.0, 9.0, 12.0, 15.0])
    def test_peaking_calibrated(self, pk):
        c = CTLE.from_peaking(pk, f_pole1=28e9, f_pole2=56e9)
        assert c.peaking_db() == pytest.approx(pk, abs=0.1)

    def test_dc_gain(self):
        # Poles are required arguments (they used to default to the 112G
        # 28/56 GHz pair, which silently mis-built any non-112G CTLE).
        c = CTLE.from_peaking(9.0, f_pole1=28e9, f_pole2=56e9)
        assert abs(c.freq_response(np.array([1e3]))[0]) == pytest.approx(
            1.0, rel=1e-3)

    def test_noise_enhancement_is_modeled(self):
        """
        White noise through the CTLE must come out with MORE power (the
        peaking region amplifies it). This is the property the old baud-rate
        FIR + post-CTLE noise injection completely missed.
        """
        rng = np.random.default_rng(0)
        f_s = 8 * 56e9
        noise = rng.normal(0, 1.0, 200_000)
        c = CTLE.from_peaking(12.0, f_pole1=28e9, f_pole2=56e9)
        out = c.apply(noise, f_s)
        assert np.var(out) > 1.3 * np.var(noise)

    def test_zero_peaking_is_flat_lowpass(self):
        c = CTLE.from_peaking(0.0, f_pole1=28e9, f_pole2=56e9)
        assert c.peaking_db() < 0.2

    def test_poles_are_required_not_defaulted(self):
        """CLAUDEwa.md §12's named trap: `from_peaking(6.0)` used to work and
        silently place a 5 Gbps CTLE's poles at 28/56 GHz."""
        with pytest.raises(TypeError):
            CTLE.from_peaking(6.0)


class TestAGC:
    def test_scales_to_pam4_rms(self):
        rng = np.random.default_rng(1)
        syms = rng.choice(PAM4_LEVELS, 20_000)
        wave = 0.05 * np.repeat(syms, 8)          # heavily attenuated
        s = agc_scale(wave)
        assert np.sqrt(np.mean((s * wave) ** 2)) == pytest.approx(
            np.sqrt(5.0), rel=0.02)


class TestCDRSampler:
    def _run(self, ppm=0.0, phase_off_ui=0.25, sj_amp=0.0, sj_freq=0.0,
             n_sym=30_000, quantize=False):
        rng = np.random.default_rng(2)
        osr, fbaud = 8, 56e9
        syms = rng.choice(PAM4_LEVELS, n_sym + 200)
        wave = tx_waveform(syms, osr=osr, fbaud=fbaud, tx_bw_hz=0.75 * fbaud,
                           sj_amp_ui=sj_amp, sj_freq_hz=sj_freq, rng=rng)
        cfg = SamplerConfig(osr=osr, fbaud=fbaud, ppm_offset=ppm,
                            aperture_rj_fs=0.0, ti_timing_rms_ps=0.0,
                            ti_gain_rms_db=0.0, ti_offset_rms=0.0,
                            quantize=quantize)
        res = CDRSampler(cfg, rng).process(
            wave, t0=osr * (1.0 - phase_off_ui), n_symbols=n_sym)
        return syms, res

    def test_locks_with_static_phase_offset(self):
        syms, res = self._run(phase_off_ui=0.3)
        assert res.locked

    def test_locks_and_tracks_100ppm(self):
        syms, res = self._run(ppm=100.0)
        assert res.locked
        # frequency word must move toward the offset magnitude (1e-4 UI/UI)
        assert abs(res.freq_ui[-1]) > 2e-5

    def test_recovers_symbols_through_mild_channel(self):
        """
        Representative use: channel-dispersed + CTLE-equalized waveform.
        (On a raw ZOH waveform the MM S-curve is flat and the phase wanders —
        that is a property of the MM criterion, not a code bug; see the
        CDRSampler docstring.)
        """
        from rx_frontend import _slice_pam4
        from channel import Channel
        rng = np.random.default_rng(2)
        osr, fbaud, n_sym = 8, 56e9, 30_000
        f_s = osr * fbaud
        syms = rng.choice(PAM4_LEVELS, n_sym + 400)
        wave = tx_waveform(syms, osr=osr, fbaud=fbaud, tx_bw_hz=0.75 * fbaud,
                           rng=rng)
        ch = Channel.from_loss_model(length_cm=2.0)     # ~6 dB @ Nyquist
        rx = ch.apply(wave, f_s)
        ctle = CTLE.from_peaking(4.0, f_pole1=fbaud / 2, f_pole2=fbaud)
        rx = ctle.apply(rx, f_s)
        # Gain calibration from the pulse-response cursor (RMS AGC is fooled
        # by CTLE edge overshoot and compresses the sampled levels)
        pulse = np.zeros(400)
        pulse[100] = 1.0
        pr = ctle.apply(ch.apply(tx_waveform(pulse, osr, fbaud,
                                             tx_bw_hz=0.75 * fbaud, rng=rng),
                                 f_s), f_s)
        cur = int(np.argmax(np.abs(pr)))
        rx /= pr[cur]
        t0 = float(cur - 100 * osr)
        cfg = SamplerConfig(osr=osr, fbaud=fbaud, aperture_rj_fs=0.0,
                            ti_timing_rms_ps=0.0, ti_gain_rms_db=0.0,
                            ti_offset_rms=0.0, quantize=False)
        res = CDRSampler(cfg, rng).process(rx, t0=t0 + 0.5, n_symbols=n_sym)
        assert res.locked
        d = estimate_delay(res.samples, syms)
        start = 10_000
        dec = np.array([_slice_pam4(v) for v in res.samples[start + d:]])
        ref = syms[start:start + len(dec)]
        ser = np.mean(dec != ref)
        assert ser < 5e-3

    def test_tracks_low_freq_sj(self):
        """0.15 UI of 5 MHz SJ is far inside the loop BW: must stay locked."""
        syms, res = self._run(sj_amp=0.15, sj_freq=5e6)
        assert res.locked


class TestDelayEstimator:
    def test_finds_known_lag(self):
        rng = np.random.default_rng(3)
        syms = rng.choice(PAM4_LEVELS, 8000)
        lag = 37
        stream = np.concatenate([rng.normal(0, 0.1, lag),
                                 syms + rng.normal(0, 0.1, len(syms))])
        assert estimate_delay(stream, syms, max_lag=100) == lag
