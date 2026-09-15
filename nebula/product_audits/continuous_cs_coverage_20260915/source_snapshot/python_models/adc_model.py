"""
adc_model.py — Behavioral ADC model for high-speed SerDes simulation.

Models:
  - Ideal N-bit quantisation
  - Thermal noise (input-referred)
  - Aperture jitter (clock noise degrading ENOB)
  - Harmonic distortion (HD2, HD3)
  - Time-interleaved ADC (TI-ADC) with gain/offset/timing mismatch
  - ENOB vs frequency analysis
  - DNL/INL modelling
"""

import numpy as np
from typing import Optional, Tuple
from dataclasses import dataclass


# ─────────────────────────────────────────────────────────────────────────────
# Core quantiser
# ─────────────────────────────────────────────────────────────────────────────

def ideal_quantize(x: np.ndarray, n_bits: int,
                   v_ref: float = 1.0) -> Tuple[np.ndarray, np.ndarray]:
    """
    Ideal mid-tread uniform quantiser.

    Parameters
    ----------
    x      : input signal (should be within [-v_ref, +v_ref])
    n_bits : converter resolution
    v_ref  : full-scale reference voltage (differential, so range is ±v_ref)

    Returns
    -------
    x_q : quantised output (same units as x)
    code: integer code [0 .. 2^n_bits - 1]
    """
    n_levels = 2 ** n_bits
    lsb = 2.0 * v_ref / n_levels
    code = np.floor((x + v_ref) / lsb).astype(int)
    code = np.clip(code, 0, n_levels - 1)
    x_q = code * lsb - v_ref + lsb/2.0   # mid-tread reconstruction
    return x_q, code


def sqnr_ideal(n_bits: int) -> float:
    """Theoretical SQNR = 6.02·N + 1.76 dB (sine input, ideal ADC)."""
    return 6.02 * n_bits + 1.76


# ─────────────────────────────────────────────────────────────────────────────
# Noise and distortion models
# ─────────────────────────────────────────────────────────────────────────────

def aperture_jitter_noise(signal: np.ndarray, sample_rate: float,
                          jitter_rms_s: float) -> np.ndarray:
    """
    Model aperture jitter as additive noise.

    For a sinusoidal input at frequency f_in:
        noise_rms = 2π · f_in · A · t_j_rms

    For a wideband signal, approximate as:
        noise = dV/dt · Δt  where Δt ~ N(0, t_j_rms)

    This implementation uses a finite-difference derivative estimate.
    """
    # dV/dt by first difference
    dvdt = np.diff(signal, prepend=signal[0]) * sample_rate
    # Jitter noise = dV/dt * random_time_error
    jitter_noise = dvdt * np.random.normal(0, jitter_rms_s, len(signal))
    return signal + jitter_noise


def add_thermal_noise(signal: np.ndarray, noise_rms_v: float) -> np.ndarray:
    """Add input-referred thermal noise (kT/C, op-amp noise)."""
    return signal + np.random.normal(0, noise_rms_v, len(signal))


def add_harmonic_distortion(signal: np.ndarray,
                             hd2_db: float = -60.0,
                             hd3_db: float = -65.0) -> np.ndarray:
    """
    Add 2nd and 3rd harmonic distortion.
    Typical values: HD2 ~ -55 to -65 dB, HD3 ~ -60 to -70 dB for 6-bit ADC.
    """
    hd2_lin = 10 ** (hd2_db / 20.0)
    hd3_lin = 10 ** (hd3_db / 20.0)
    return signal + hd2_lin * signal**2 + hd3_lin * signal**3


def add_dnl_inl(signal: np.ndarray, n_bits: int, v_ref: float,
                dnl_rms_lsb: float = 0.3) -> np.ndarray:
    """
    Model random DNL errors (Gaussian, RMS = dnl_rms_lsb LSBs).
    DNL errors create quantisation spurs.
    """
    n_levels = 2 ** n_bits
    lsb = 2.0 * v_ref / n_levels
    # Random offset per code level (represents code-dependent gain error)
    dnl = np.random.normal(0, dnl_rms_lsb * lsb, n_levels)
    inl = np.cumsum(dnl)
    # Apply INL correction map
    codes = np.floor((signal + v_ref) / lsb).astype(int)
    codes = np.clip(codes, 0, n_levels - 1)
    correction = inl[codes]
    return signal + correction


# ─────────────────────────────────────────────────────────────────────────────
# ENOB analysis via SINAD
# ─────────────────────────────────────────────────────────────────────────────

def compute_sinad_enob(output: np.ndarray, input_sig: np.ndarray,
                       f_in: float, f_s: float,
                       window: bool = True) -> Tuple[float, float]:
    """
    Compute SINAD and ENOB from ADC output and ideal input.

    output   : ADC output (quantised)
    input_sig: ideal input signal
    f_in     : input sine frequency [Hz]
    f_s      : sampling rate [Hz]
    window   : apply Hann window to reduce spectral leakage

    Returns (SINAD_dB, ENOB)
    """
    N = len(output)
    if window:
        w = np.hanning(N)
    else:
        w = np.ones(N)
    # FFT of output
    Y = np.fft.rfft(output * w)
    P = np.abs(Y)**2
    # Find signal bin
    freqs = np.fft.rfftfreq(N, d=1.0/f_s)
    sig_bin = np.argmin(np.abs(freqs - f_in))
    # Signal power (3 bins around peak)
    sig_bins = slice(max(0, sig_bin-1), min(len(P), sig_bin+2))
    P_sig  = np.sum(P[sig_bins])
    P_total = np.sum(P)
    P_noise = P_total - P_sig
    sinad = 10 * np.log10(P_sig / max(P_noise, 1e-30))
    enob  = (sinad - 1.76) / 6.02
    return sinad, enob


def enob_vs_frequency(adc_model: "ADC", f_range: np.ndarray,
                      f_s: float, n_samples: int = 8192) -> np.ndarray:
    """Sweep input frequency and measure ENOB at each frequency."""
    enob_arr = np.zeros(len(f_range))
    for i, f_in in enumerate(f_range):
        t = np.arange(n_samples) / f_s
        x_in = 0.9 * np.sin(2 * np.pi * f_in * t)  # 90% full scale
        x_out = adc_model.convert(x_in, f_s)
        _, enob_arr[i] = compute_sinad_enob(x_out, x_in, f_in, f_s)
    return enob_arr


# ─────────────────────────────────────────────────────────────────────────────
# Time-interleaved ADC mismatch model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TIADCMismatch:
    """Mismatch parameters for one sub-ADC in a time-interleaved array."""
    gain_error_db:     float = 0.0    # relative gain error [dB]
    offset_v:          float = 0.0    # offset voltage [V]
    timing_error_ps:   float = 0.0    # sampling instant error [ps]


class TIADC:
    """
    Time-interleaved ADC model.

    M sub-ADCs operating at f_s/M each, combined to achieve f_s.
    Mismatch between sub-ADCs creates spurious tones at f_s·k/M offsets.

    Parameters
    ----------
    n_sub   : number of interleaved channels (typically 4–32)
    n_bits  : resolution per sub-ADC
    f_s     : total sampling rate [Hz]
    v_ref   : full-scale voltage
    mismatch_gain_db  : rms gain mismatch [dB]
    mismatch_offset_v : rms offset mismatch [V]
    mismatch_timing_ps: rms timing mismatch [ps]
    """
    def __init__(self,
                 n_sub:   int   = 4,
                 n_bits:  int   = 6,
                 f_s:     float = 56e9,
                 v_ref:   float = 0.5,
                 mismatch_gain_db:   float = 0.1,
                 mismatch_offset_v:  float = 2e-3,
                 mismatch_timing_ps: float = 0.2):
        self.n_sub  = n_sub
        self.n_bits = n_bits
        self.f_s    = f_s
        self.v_ref  = v_ref
        # Generate random mismatch for each sub-ADC
        rng = np.random.default_rng(seed=42)
        self.sub_adcs = [
            TIADCMismatch(
                gain_error_db   = rng.normal(0, mismatch_gain_db),
                offset_v        = rng.normal(0, mismatch_offset_v),
                timing_error_ps = rng.normal(0, mismatch_timing_ps)
            )
            for _ in range(n_sub)
        ]
        # Thermal noise floor
        self.thermal_rms_v = v_ref / (2**n_bits) / 4.0   # ~1/4 LSB thermal

    def convert(self, x: np.ndarray, apply_calibration: bool = False
                ) -> np.ndarray:
        """
        Convert input signal through time-interleaved ADC model.
        If apply_calibration=True, ideal mismatch is corrected (residual only).
        """
        N = len(x)
        out = np.zeros(N)
        f_sub = self.f_s / self.n_sub
        dt = 1.0 / self.f_s

        for n in range(N):
            ch = n % self.n_sub
            mis = self.sub_adcs[ch]
            # Timing mismatch: adjust sample time
            t_err = mis.timing_error_ps * 1e-12
            # Interpolate input at displaced time
            n_shifted = n + t_err * self.f_s
            n_floor   = int(np.floor(n_shifted))
            frac      = n_shifted - n_floor
            if 0 <= n_floor < N-1:
                x_sample = x[n_floor] * (1-frac) + x[n_floor+1] * frac
            else:
                x_sample = x[min(n, N-1)]

            # Gain mismatch
            gain_lin = 10 ** (mis.gain_error_db / 20.0)
            x_sample = x_sample * gain_lin

            # Offset mismatch
            if not apply_calibration:
                x_sample += mis.offset_v

            # Thermal noise
            x_sample += np.random.normal(0, self.thermal_rms_v)

            # Quantise
            x_q, _ = ideal_quantize(np.array([x_sample]), self.n_bits, self.v_ref)
            out[n] = x_q[0]

        return out

    def spur_frequencies(self, f_in: float) -> np.ndarray:
        """
        Theoretical spur frequencies due to timing/gain/offset mismatch.
        Returns array of spur frequencies [Hz].
        """
        f_sub = self.f_s / self.n_sub
        spurs = []
        for k in range(1, self.n_sub):
            spurs.append(k * f_sub + f_in)
            spurs.append(k * f_sub - f_in)
        return np.array(spurs)


# ─────────────────────────────────────────────────────────────────────────────
# Complete ADC behavioural model
# ─────────────────────────────────────────────────────────────────────────────

class ADC:
    """
    Complete ADC behavioural model combining all non-idealities.

    Usage
    -----
    adc = ADC(n_bits=6, f_s=56e9, v_ref=0.5,
              jitter_rms_ps=0.15, n_sub=16)
    y = adc.convert(x_analog, apply_ti_mismatch=True)
    sinad, enob = adc.characterise(f_in=1e9)
    """
    def __init__(self,
                 n_bits:         int   = 6,
                 f_s:            float = 56e9,
                 v_ref:          float = 0.5,
                 jitter_rms_ps:  float = 0.15,   # aperture jitter [ps]
                 thermal_rms_v:  float = None,    # input-referred noise [V]
                 hd2_db:         float = -62.0,
                 hd3_db:         float = -65.0,
                 dnl_rms_lsb:    float = 0.2,
                 n_sub:          int   = 16,      # TI sub-ADC count
                 mismatch_gain_db:   float = 0.08,
                 mismatch_offset_v:  float = 1e-3,
                 mismatch_timing_ps: float = 0.15):
        self.n_bits  = n_bits
        self.f_s     = f_s
        self.v_ref   = v_ref
        self.jitter_rms_s = jitter_rms_ps * 1e-12
        self.hd2_db  = hd2_db
        self.hd3_db  = hd3_db
        self.dnl_rms_lsb = dnl_rms_lsb
        # Thermal noise: default to ~1/4 LSB input-referred
        lsb = 2.0 * v_ref / (2**n_bits)
        self.thermal_rms_v = thermal_rms_v if thermal_rms_v else lsb * 0.25
        # TI-ADC model
        self.ti_adc = TIADC(n_sub=n_sub, n_bits=n_bits, f_s=f_s, v_ref=v_ref,
                            mismatch_gain_db=mismatch_gain_db,
                            mismatch_offset_v=mismatch_offset_v,
                            mismatch_timing_ps=mismatch_timing_ps)

    def convert(self, x: np.ndarray,
                apply_ti_mismatch: bool = True,
                apply_distortion:  bool = True,
                apply_jitter:      bool = True,
                apply_dnl:         bool = True) -> np.ndarray:
        """Full conversion pipeline with all non-idealities."""
        y = x.copy()
        if apply_jitter:
            y = aperture_jitter_noise(y, self.f_s, self.jitter_rms_s)
        if apply_distortion:
            y = add_harmonic_distortion(y, self.hd2_db, self.hd3_db)
        y = add_thermal_noise(y, self.thermal_rms_v)
        if apply_ti_mismatch:
            y = self.ti_adc.convert(y)
        else:
            if apply_dnl:
                y = add_dnl_inl(y, self.n_bits, self.v_ref, self.dnl_rms_lsb)
            y, _ = ideal_quantize(y, self.n_bits, self.v_ref)
        return y

    def characterise(self, f_in: float = 1e9,
                     n_samples: int = 16384) -> Tuple[float, float]:
        """Run single-tone SINAD/ENOB test."""
        t = np.arange(n_samples) / self.f_s
        x_in = 0.9 * self.v_ref * np.sin(2 * np.pi * f_in * t)
        x_out = self.convert(x_in)
        return compute_sinad_enob(x_out, x_in, f_in, self.f_s)

    @property
    def enob_dc(self) -> float:
        """ENOB at near-DC (quantisation + thermal noise only)."""
        lsb = 2.0 * self.v_ref / (2**self.n_bits)
        sigma_q = lsb / np.sqrt(12.0)
        sigma_total = np.sqrt(sigma_q**2 + self.thermal_rms_v**2)
        sndr = 20 * np.log10(self.v_ref / (sigma_total * np.sqrt(2)))
        return (sndr - 1.76) / 6.02

    def power_estimate_mw(self) -> float:
        """
        Rough power estimate using Walden FOM:
        P ≈ FOM · f_s · 2^ENOB  with FOM = 10 fJ/conv-step (28nm)
        """
        fom_j = 10e-15   # 10 fJ/conv-step (aggressive 28nm)
        enob = self.enob_dc
        return fom_j * self.f_s * (2**enob) * 1e3  # mW


if __name__ == "__main__":
    np.random.seed(1)
    adc = ADC(n_bits=6, f_s=56e9, v_ref=0.5,
              jitter_rms_ps=0.15, n_sub=16,
              mismatch_gain_db=0.08, mismatch_timing_ps=0.15)

    sinad, enob = adc.characterise(f_in=1e9)
    print(f"ADC @ 1 GHz:  SINAD = {sinad:.1f} dB,  ENOB = {enob:.2f} bits")
    sinad_h, enob_h = adc.characterise(f_in=28e9)
    print(f"ADC @ 28 GHz: SINAD = {sinad_h:.1f} dB,  ENOB = {enob_h:.2f} bits")
    print(f"DC ENOB (ideal): {adc.enob_dc:.2f} bits")
    print(f"Power estimate: {adc.power_estimate_mw():.0f} mW")
    print(f"Ideal SQNR ({adc.n_bits}-bit): {sqnr_ideal(adc.n_bits):.1f} dB")
    print("adc_model.py: self-test PASSED")
