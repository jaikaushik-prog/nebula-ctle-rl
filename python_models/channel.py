"""
channel.py — High-speed wireline/optical channel modeling
Supports S-parameter import, impulse response extraction, ISI analysis,
jitter/noise injection, and optical channel modeling.

Usage:
    ch = Channel.from_sparam('board.s4p', port_pair=(1,2))
    pulse = ch.pulse_response(fbaud=56e9)
    eye  = ch.eye_diagram(bits, fbaud=56e9, osr=8)
"""

import numpy as np
from scipy import signal, interpolate
import matplotlib.pyplot as plt
from dataclasses import dataclass, field
from typing import Optional, Tuple
import warnings

try:
    import skrf
    SKRF_AVAILABLE = True
except ImportError:
    SKRF_AVAILABLE = False
    warnings.warn("scikit-rf not installed; S-parameter import disabled.")


# ─────────────────────────────────────────────────────────────────────────────
# S-parameter channel model
# ─────────────────────────────────────────────────────────────────────────────

class Channel:
    """
    Encapsulates a linear time-invariant channel for high-speed link simulation.

    Attributes
    ----------
    freq : ndarray   frequency vector [Hz]
    H    : ndarray   complex channel transfer function H(f)
    h    : ndarray   impulse response (time domain)
    dt   : float     time step of impulse response [s]
    """

    def __init__(self, freq: np.ndarray, H: np.ndarray, z0: float = 100.0):
        self.freq = freq
        self.H = H                          # H[f], complex
        self.z0 = z0
        # Build two-sided spectrum for IFFT
        f_max = freq[-1]
        N = len(freq)
        self.dt = 1.0 / (2 * f_max)
        # DC + positive freqs + mirror negative freqs
        H_full = np.concatenate([H, np.conj(H[-2:0:-1])])
        self.h = np.real(np.fft.ifft(H_full))
        self.h /= np.max(np.abs(self.h))    # normalise cursor to unity

    # ── Constructors ──────────────────────────────────────────────────────────

    @classmethod
    def from_sparam(cls, filename: str, port_pair: Tuple[int,int] = (1,2),
                    z0: float = 100.0) -> "Channel":
        """Load channel from Touchstone file (.s2p / .s4p / .sNp)."""
        if not SKRF_AVAILABLE:
            raise RuntimeError("scikit-rf required: pip install scikit-rf")
        nw = skrf.Network(filename)
        # Extract S21 (or specified port pair)
        p_out, p_in = port_pair[0]-1, port_pair[1]-1
        H = nw.s[:, p_out, p_in]
        freq = nw.f
        return cls(freq, H, z0=z0)

    @classmethod
    def from_loss_model(cls, f_max: float = 60e9, N: int = 4096,
                        alpha_skin: float = 0.30, alpha_diel: float = 0.05,
                        length_cm: float = 30.0) -> "Channel":
        """
        Analytical PCB trace model.

        alpha_skin : loss coefficient [dB / cm / sqrt(GHz)]  (FR4 typical: 0.3)
        alpha_diel : loss coefficient [dB / cm / GHz]        (FR4 typical: 0.05)
        length_cm  : trace length [cm]
        """
        freq = np.linspace(1e6, f_max, N)
        f_GHz = freq / 1e9
        IL_dB = -(alpha_skin * np.sqrt(f_GHz) + alpha_diel * f_GHz) * length_cm
        IL_lin = 10 ** (IL_dB / 20.0)
        # Simple linear phase (constant group delay)
        tau = length_cm * 1e-2 / (0.6 * 3e8)
        phase = -2 * np.pi * freq * tau
        H = IL_lin * np.exp(1j * phase)
        return cls(freq, H)

    @classmethod
    def optical_imdd(cls, f_max: float = 60e9, N: int = 4096,
                     bw_laser: float = 30e9, bw_pd: float = 35e9,
                     cd_ps_nm: float = 0.0) -> "Channel":
        """
        IM-DD optical channel: laser bandwidth + photodiode bandwidth + CD.
        cd_ps_nm : chromatic dispersion [ps/nm] (for ~2km OM4: ~10 ps/nm @ 850nm)
        """
        freq = np.linspace(1e6, f_max, N)
        # Gaussian bandwidth model for laser and PD
        H_laser = np.exp(-0.5 * (freq / bw_laser)**2)
        H_pd    = np.exp(-0.5 * (freq / bw_pd)**2)
        # Chromatic dispersion (group delay spread ∝ Δλ·D·L)
        lambda_nm = 1310.0  # nm
        c_nm_ps = 3e8 * 1e9 / 1e12   # speed of light in nm/ps
        tau_cd = cd_ps_nm * freq / (c_nm_ps / lambda_nm**2) * 1e-12
        H_cd = np.exp(-1j * np.pi * lambda_nm**2 * cd_ps_nm * 1e-3 * (freq**2) / c_nm_ps)
        H = H_laser * H_pd * H_cd
        return cls(freq, H)

    # ── Analysis methods ──────────────────────────────────────────────────────

    def insertion_loss_db(self) -> Tuple[np.ndarray, np.ndarray]:
        """Return (freq, IL_dB)."""
        return self.freq, 20 * np.log10(np.abs(self.H) + 1e-15)

    def group_delay_ns(self) -> Tuple[np.ndarray, np.ndarray]:
        """Estimate group delay from phase derivative."""
        phase = np.unwrap(np.angle(self.H))
        gd = -np.gradient(phase, self.freq) / (2 * np.pi) * 1e9  # ns
        return self.freq, gd

    def pulse_response(self, fbaud: float, osr: int = 8) -> np.ndarray:
        """
        Compute baud-rate pulse response.
        A rectangular TX pulse (1 UI wide) convolved with channel impulse response.
        Returns the pulse response sampled at osr samples/symbol.
        """
        Tsym = 1.0 / fbaud
        dt_sim = Tsym / osr
        t_max = 100 * Tsym         # 100-symbol window
        t = np.arange(0, t_max, dt_sim)
        N_t = len(t)

        # Frequency axis for this dt_sim
        freq_sim = np.fft.rfftfreq(N_t, d=dt_sim)
        # Interpolate channel to simulation frequency grid
        H_re = np.interp(freq_sim, self.freq, np.real(self.H), right=0.0)
        H_im = np.interp(freq_sim, self.freq, np.imag(self.H), right=0.0)
        H_sim = H_re + 1j * H_im
        # TX pulse: rectangular, 1 UI
        n_ui = osr
        pulse_time = np.zeros(N_t)
        pulse_time[:n_ui] = 1.0
        # Convolve via FFT
        PULSE_F = np.fft.rfft(pulse_time)
        PR_F = PULSE_F * H_sim
        pr = np.real(np.fft.irfft(PR_F, n=N_t))
        # Trim to 30 UI centred on cursor
        cursor_idx = np.argmax(np.abs(pr))
        n_pre, n_post = 5 * osr, 25 * osr
        start = max(0, cursor_idx - n_pre)
        stop  = min(N_t, cursor_idx + n_post)
        return pr[start:stop]

    def apply(self, x: np.ndarray, f_s: float) -> np.ndarray:
        """
        Filter an arbitrary waveform sampled at f_s through H(f).

        Full linear convolution semantics: the output is zero-padded by the
        channel memory before the FFT so no circular wrap-around occurs, then
        trimmed back to len(x). The channel's bulk delay is preserved — do NOT
        assume x[n] and y[n] are cursor-aligned; measure the delay (e.g. by
        cross-correlation against the known TX sequence) before slicing.

        Beyond the highest measured/modelled frequency, H is taken as 0
        (band-limited extrapolation), which is conservative for loss channels.
        """
        x = np.asarray(x, dtype=float)
        n_pad = int(min(len(x), 64 * 1024))          # ≥ channel memory
        n_fft = int(2 ** np.ceil(np.log2(len(x) + n_pad)))
        freq_sim = np.fft.rfftfreq(n_fft, d=1.0 / f_s)
        H_re = np.interp(freq_sim, self.freq, np.real(self.H), right=0.0)
        H_im = np.interp(freq_sim, self.freq, np.imag(self.H), right=0.0)
        Y = np.fft.rfft(x, n=n_fft) * (H_re + 1j * H_im)
        y = np.fft.irfft(Y, n=n_fft)
        return y[:len(x)]

    def isi_taps(self, fbaud: float, osr: int = 64) -> np.ndarray:
        """Return baud-rate sampled ISI taps from the pulse response."""
        pr = self.pulse_response(fbaud, osr=osr)
        # Sample at baud rate
        return pr[::osr]

    def nloss_at_nyquist(self, fbaud: float) -> float:
        """Return channel loss [dB] at Nyquist frequency (fbaud/2)."""
        f_nyq = fbaud / 2.0
        IL = 20 * np.log10(np.abs(np.interp(f_nyq, self.freq, np.abs(self.H))) + 1e-15)
        return IL

    # ── Noise and jitter injection ─────────────────────────────────────────────

    @staticmethod
    def add_awgn(signal: np.ndarray, snr_db: float) -> np.ndarray:
        """Add AWGN to achieve target SNR (signal power / noise power)."""
        sig_power = np.mean(signal**2)
        snr_lin = 10 ** (snr_db / 10.0)
        noise_power = sig_power / snr_lin
        return signal + np.random.normal(0, np.sqrt(noise_power), signal.shape)

    @staticmethod
    def add_rj(samples: np.ndarray, rj_rms_ui: float, fbaud: float,
               osr: int = 1) -> np.ndarray:
        """
        Add random jitter by resampling with time-displaced sampling instants.
        rj_rms_ui : RJ rms value in unit intervals
        osr       : oversampling ratio (1 = baud-rate sampling)
        """
        Tsym = 1.0 / fbaud
        dt = Tsym / osr
        jitter_s = np.random.normal(0, rj_rms_ui * Tsym, len(samples))
        t = np.arange(len(samples)) * dt
        t_jittered = t + jitter_s
        # Resample via interpolation
        interp_fn = interpolate.interp1d(t, samples, kind='linear',
                                          bounds_error=False, fill_value='extrapolate')
        return interp_fn(t_jittered)

    @staticmethod
    def add_dj_isi(samples: np.ndarray, h_isi: np.ndarray,
                   dj_scale: float = 0.05) -> np.ndarray:
        """Add deterministic jitter via ISI from a secondary channel tap."""
        isi = np.convolve(samples, h_isi * dj_scale, mode='same')
        return samples + isi

    # ── Crosstalk ──────────────────────────────────────────────────────────────

    @staticmethod
    def add_fext(victim: np.ndarray, aggressor: np.ndarray,
                 fext_level_db: float) -> np.ndarray:
        """Add FEXT noise: aggressor signal scaled by FEXT coupling."""
        scale = 10 ** (fext_level_db / 20.0)
        n = min(len(victim), len(aggressor))
        result = victim.copy()
        result[:n] += aggressor[:n] * scale
        return result

    # ── Eye diagram ───────────────────────────────────────────────────────────

    def eye_diagram(self, symbols: np.ndarray, fbaud: float,
                    osr: int = 8, n_symbols: int = 5000,
                    noise_db: float = 25.0) -> Tuple[np.ndarray, np.ndarray]:
        """
        Generate eye diagram data (time folds, voltage samples).
        Returns (t_fold, v_fold) arrays for plotting.
        """
        pr = self.pulse_response(fbaud, osr=osr)
        # Convolve symbol stream with pulse response
        N = min(len(symbols), n_symbols)
        sym = symbols[:N].astype(float)
        rx = np.convolve(sym, pr, mode='same')
        rx = self.add_awgn(rx, noise_db)
        # Fold into 2 UI window
        ui_samples = osr
        fold_len = 2 * ui_samples
        n_folds = len(rx) // fold_len
        v_fold = rx[:n_folds * fold_len].reshape(n_folds, fold_len)
        t_fold = np.tile(np.linspace(-1, 1, fold_len), (n_folds, 1))
        return t_fold.ravel(), v_fold.ravel()


# ─────────────────────────────────────────────────────────────────────────────
# Bathtub curve and BER estimation
# ─────────────────────────────────────────────────────────────────────────────

def bathtub_curve(t_fold: np.ndarray, v_fold: np.ndarray,
                  threshold: float = 0.0,
                  n_bins: int = 200) -> Tuple[np.ndarray, np.ndarray]:
    """
    Estimate horizontal bathtub curve at a given voltage threshold.
    Returns (time_axis, BER_estimate) for the horizontal bathtub.
    """
    from scipy.special import erfc
    t_axis = np.linspace(-1, 1, n_bins)
    ber = np.zeros(n_bins)
    for i, t0 in enumerate(t_axis):
        mask = np.abs(t_fold - t0) < (1.0 / n_bins)
        if mask.sum() < 10:
            ber[i] = np.nan
            continue
        v_at_t = v_fold[mask]
        # BER estimate: fraction of samples on wrong side of threshold
        # (simplified — real bathtub needs Q-function extrapolation)
        ber_raw = np.mean(v_at_t < threshold) if np.mean(v_at_t) > threshold \
                  else np.mean(v_at_t > threshold)
        ber[i] = max(ber_raw, 1e-15)
    return t_axis, ber


def ber_from_snr_pam4(snr_db: np.ndarray) -> np.ndarray:
    """
    Theoretical Gray-coded PAM-4 BER over AWGN (no ISI, ideal thresholds).

    Levels {±1, ±3}: mean symbol power = 5, half eye height = 1, so the
    per-boundary error probability is Q(sqrt(SNR/5)) with SNR = 5/sigma^2.
    Inner levels see two boundaries, outer levels one:
        SER = (3/2) * Q( sqrt(SNR/5) )
    Gray coding makes almost every symbol error a single bit error:
        BER = SER/2 = (3/4) * Q( sqrt(SNR/5) ) = (3/8) * erfc( sqrt(SNR/10) )
    """
    from scipy.special import erfc
    snr_lin = 10 ** (np.asarray(snr_db, dtype=float) / 10.0)
    return (3.0/8.0) * erfc(np.sqrt(snr_lin / 10.0))


if __name__ == "__main__":
    # Quick self-test
    ch = Channel.from_loss_model(alpha_skin=0.30, alpha_diel=0.05, length_cm=30)
    freq, IL = ch.insertion_loss_db()
    print(f"IL at 28 GHz: {np.interp(28e9, freq, IL):.1f} dB")
    pr = ch.pulse_response(fbaud=56e9, osr=8)
    taps = ch.isi_taps(fbaud=56e9)
    print(f"Pulse response length: {len(pr)} samples | ISI taps: {len(taps)}")
    print(f"Cursor tap index: {np.argmax(np.abs(taps))}")
    print("channel.py: self-test PASSED")
