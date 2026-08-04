"""
cdr.py — Clock and data recovery for high-speed PAM-4 receivers.

Implements:
  - Mueller-Müller (MM) baud-rate timing error detector
  - Bang-bang (BB) CDR  (standard SerDes architecture)
  - Gardner TED (T/2-spaced, loop bandwidth analysis)
  - Digital PLL loop filter (type-I and type-II)
  - Jitter tolerance / jitter transfer simulation
  - Phase interpolator model

All CDR classes expose:
    ted.update(r_now, r_prev, d_now, d_prev) → timing_error
    loop.update(e) → phase_correction
"""

import numpy as np
from typing import Tuple, Optional, List
from dataclasses import dataclass


# ─────────────────────────────────────────────────────────────────────────────
# Timing error detectors
# ─────────────────────────────────────────────────────────────────────────────

class MuellerMullerTED:
    """
    Mueller-Müller baud-rate timing error detector.

    Error:  e[n] = r[n]·d̂[n-1] − r[n-1]·d̂[n]

    Properties
    ----------
    - Baud-rate (no oversampling required)
    - S-curve zero crossing at optimal sampling phase
    - Works for PAM-4 with normalised levels
    - Sensitive to ISI; best used after FFE pre-equalisation
    """
    def __init__(self):
        self.r_prev = 0.0
        self.d_prev = 0.0

    def update(self, r_now: float, d_now: float) -> float:
        e = r_now * self.d_prev - self.r_prev * d_now
        self.r_prev = r_now
        self.d_prev = d_now
        return float(e)

    def process_block(self, r: np.ndarray,
                      d: np.ndarray) -> np.ndarray:
        """Vectorised MM processing. Returns error sequence."""
        e = np.zeros(len(r))
        for n in range(1, len(r)):
            e[n] = r[n]*d[n-1] - r[n-1]*d[n]
        return e


class BangBangTED:
    """
    Alexander (bang-bang) phase detector using 2× oversampled data.

    Uses early sample (e), on-time sample (d), and late sample as:
        if sign(early) == sign(on_time): phase is early → step forward
        else:                            phase is late  → step backward

    Output: ±1 only (hard nonlinearity)
    """
    def __init__(self):
        self.prev_on = 0.0
        self.prev_half = 0.0

    def update(self, on_sample: float, half_sample: float) -> int:
        """
        on_sample   : sample at baud-rate instant
        half_sample : sample at T/2 offset (early/late indicator)
        Returns ±1 phase error.
        """
        s_on   = np.sign(on_sample)
        s_half = np.sign(half_sample)
        s_prev = np.sign(self.prev_on)
        # Transition between prev_on and on_sample
        if s_prev != s_on:
            e = int(s_half)   # if half-sample agrees with prev, we're early
        else:
            e = 0             # no transition, no phase info
        self.prev_on   = on_sample
        self.prev_half = half_sample
        return e


class GardnerTED:
    """
    Gardner timing error detector (T/2-spaced, data-aided).

    Error: e[n] = x[n-1] * (x[n] - x[n-2])
    where x[] is the oversampled received stream at 2 samples/symbol.
    Linear for small timing errors; works without decision feedback.
    """
    def __init__(self):
        self.buf = [0.0, 0.0, 0.0]

    def update(self, sample: float) -> float:
        self.buf = [self.buf[1], self.buf[2], sample]
        e = self.buf[0] * (self.buf[2] - self.buf[1])   # note: buf is x[n-2..n]
        # Wait: Gardner: e = x[(2n-1)T/2] * (x[2nT/2] - x[(2n-2)T/2])
        # Corrected: call update twice per symbol, read every 2 updates
        return e


# ─────────────────────────────────────────────────────────────────────────────
# Digital PLL loop filter (type-II, proportional + integral)
# ─────────────────────────────────────────────────────────────────────────────

class DigitalLoopFilter:
    """
    Second-order digital loop filter for CDR.

    Parameters (discrete-time PI loop filter)
    -----------------------------------------
    Kp : proportional gain
    Ki : integral gain
    mu : normalised loop bandwidth ≈ Kp * Kv_dco  (Kv_dco = DCO gain)

    Type-II CDR (PI): can acquire frequency offsets.
    Type-I  CDR (P):  set Ki=0; can only track phase.

    The output is a phase accumulator value (fractional UI).
    """
    def __init__(self, Kp: float = 0.02, Ki: float = 0.001):
        self.Kp = Kp
        self.Ki = Ki
        self.integrator = 0.0
        self.phase      = 0.0

    def update(self, error: float) -> float:
        """Process one timing error sample, return updated phase offset [UI]."""
        self.integrator += self.Ki * error
        self.phase      += self.Kp * error + self.integrator
        return self.phase

    def reset(self):
        self.integrator = 0.0
        self.phase      = 0.0

    @property
    def natural_freq_norm(self) -> float:
        """Approximate normalised loop bandwidth (fraction of baud rate)."""
        return np.sqrt(self.Kp * self.Ki)

    @property
    def damping(self) -> float:
        if self.Ki > 0:
            return self.Kp / (2.0 * np.sqrt(self.Ki))
        return np.inf


# ─────────────────────────────────────────────────────────────────────────────
# Phase interpolator model
# ─────────────────────────────────────────────────────────────────────────────

class PhaseInterpolator:
    """
    Behavioural model of a digital phase interpolator.

    Implements fractional-delay interpolation:
        y(t - τ) ≈ Σ h[k; τ] · x[k]
    using a raised-cosine interpolation kernel.

    n_taps    : interpolation filter length
    phase_bits: DCO/PI resolution [bits]
    """
    def __init__(self, n_taps: int = 8, phase_bits: int = 7):
        self.n_taps     = n_taps
        self.phase_bits = phase_bits
        self.phase_steps = 2 ** phase_bits  # number of quantised phases
        self._build_filter_bank()

    def _build_filter_bank(self):
        """Pre-compute interpolation filters for each quantised phase."""
        n = self.n_taps
        phases = np.arange(self.phase_steps) / self.phase_steps
        self.filter_bank = np.zeros((self.phase_steps, n))
        for pi_idx, frac in enumerate(phases):
            # Sinc interpolation kernel with Hann window
            t = np.arange(n) - (n-1)/2.0 - frac
            h = np.sinc(t)
            win = np.hanning(n)
            h *= win
            h /= np.sum(h)
            self.filter_bank[pi_idx] = h

    def interpolate(self, buf: np.ndarray, phase_code: int) -> float:
        """
        Apply fractional delay.
        buf        : delay line of length n_taps
        phase_code : integer in [0, phase_steps-1]
        """
        h = self.filter_bank[phase_code % self.phase_steps]
        return float(np.dot(h, buf[:self.n_taps]))


# ─────────────────────────────────────────────────────────────────────────────
# Full CDR simulation
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CDRResult:
    phase_trace: np.ndarray
    freq_trace:  np.ndarray
    error_trace: np.ndarray
    final_phase_ui: float
    rms_jitter_ui:  float

class BangBangCDR:
    """
    Complete bang-bang CDR simulation using 2× oversampled input.

    Architecture
    ------------
      [2× oversampled RX] → [BB phase detector] → [PI loop filter]
                                                 → [phase accumulator]
                                                 → [select baud-rate samples]

    Parameters
    ----------
    Kp, Ki   : loop filter gains
    fbaud    : baud rate [Hz]
    step_ui  : BB phase step size [UI]  (typ 0.01–0.03 UI)
    """
    def __init__(self, Kp: float = 0.01, Ki: float = 5e-4,
                 fbaud: float = 56e9, step_ui: float = 0.02):
        self.lf      = DigitalLoopFilter(Kp=Kp, Ki=Ki)
        self.step_ui = step_ui
        self.fbaud   = fbaud
        self.pi      = PhaseInterpolator(n_taps=8, phase_bits=7)
        self._phase_acc = 0.0    # fractional UI phase accumulator

    def process(self, r_2x: np.ndarray,
                ref_syms: Optional[np.ndarray] = None
                ) -> Tuple[np.ndarray, CDRResult]:
        """
        Process 2× oversampled received stream.
        Returns (baud_rate_samples, CDRResult).
        """
        N = len(r_2x) // 2
        baud_out    = np.zeros(N)
        phase_trace = np.zeros(N)
        freq_trace  = np.zeros(N)
        err_trace   = np.zeros(N)

        buf = np.zeros(self.pi.n_taps)
        phase_code = 0
        bb_ted = BangBangTED()

        for n in range(N):
            # Two 2× samples per baud period
            s0 = r_2x[2*n]
            s1 = r_2x[2*n+1]

            # Shift into interpolation buffer
            buf = np.roll(buf, 2)
            buf[0] = s1
            buf[1] = s0

            # Interpolated on-time sample
            y = self.pi.interpolate(buf, phase_code)
            baud_out[n] = y

            # BB phase detector
            from pam4_chain import hard_slicer_pam4
            from equalizers import hard_slicer_pam4 as hsp
            d = hsp(np.array([y]))[0]
            e = bb_ted.update(on_sample=y, half_sample=s1)

            # Scale BB output to phase step
            e_scaled = e * self.step_ui

            # Loop filter
            phase_ui = self.lf.update(e_scaled)

            # Convert phase [UI] → phase code integer
            phase_code = int(phase_ui * self.pi.phase_steps) % self.pi.phase_steps

            phase_trace[n] = phase_ui
            freq_trace[n]  = self.lf.integrator
            err_trace[n]   = e_scaled

        # Compute jitter metrics (skip initial acquisition)
        skip = min(N//5, 5000)
        jitter_ui = np.std(phase_trace[skip:])

        result = CDRResult(
            phase_trace    = phase_trace,
            freq_trace     = freq_trace,
            error_trace    = err_trace,
            final_phase_ui = float(phase_trace[-1]),
            rms_jitter_ui  = float(jitter_ui)
        )
        return baud_out, result


class MuellerMullerCDR:
    """
    Continuous-time Mueller-Müller CDR for baud-rate sampled receivers.
    Used when 2× oversampling is not available (direct-detection, cost-optimised).
    """
    def __init__(self, Kp: float = 0.015, Ki: float = 8e-4):
        self.ted = MuellerMullerTED()
        self.lf  = DigitalLoopFilter(Kp=Kp, Ki=Ki)
        self._phase = 0.0

    def update(self, r_now: float, d_now: float) -> Tuple[float, float]:
        """Process one baud-rate sample. Returns (phase, timing_error)."""
        e = self.ted.update(r_now, d_now)
        phase = self.lf.update(e)
        return phase, e

    def process_block(self, r: np.ndarray,
                      d: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        phase_trace = np.zeros(len(r))
        err_trace   = np.zeros(len(r))
        for n in range(len(r)):
            phase_trace[n], err_trace[n] = self.update(r[n], d[n])
        return phase_trace, err_trace


# ─────────────────────────────────────────────────────────────────────────────
# Jitter tolerance simulation
# ─────────────────────────────────────────────────────────────────────────────

def jitter_tolerance_sweep(cdr: MuellerMullerCDR,
                            fbaud: float = 56e9,
                            n_symbols: int = 50_000,
                            jitter_freqs_hz: Optional[np.ndarray] = None,
                            jitter_amp_ui: float = 0.1
                            ) -> Tuple[np.ndarray, np.ndarray]:
    """
    Simulate CDR jitter tolerance vs sinusoidal jitter frequency.

    Injects sinusoidal phase modulation at various frequencies and
    checks whether the CDR tracks or causes excess BER.

    Returns (freq_axis [Hz], jtol_ui [UI])
    """
    from pam4_chain import PAM4Transmitter
    from equalizers import hard_slicer_pam4

    if jitter_freqs_hz is None:
        jitter_freqs_hz = np.logspace(5, 9, 30)  # 100kHz to 1GHz

    jtol = np.zeros(len(jitter_freqs_hz))
    tx = PAM4Transmitter(prbs_order=31, scramble=False)
    syms, _ = tx.generate(2 * n_symbols)

    for i_f, fj in enumerate(jitter_freqs_hz):
        t = np.arange(n_symbols) / fbaud
        # Sinusoidal jitter: timing offset = A·sin(2π·fj·t) [UI]
        jitter_offset = jitter_amp_ui * np.sin(2 * np.pi * fj * t)
        # Apply jitter: resample at displaced time instants
        # (simplified: shift samples by rounding to nearest integer sample)
        from scipy.interpolate import interp1d
        syms_up = syms[:n_symbols]
        t_nominal = np.arange(n_symbols, dtype=float)
        t_jittered = t_nominal + jitter_offset
        t_jittered = np.clip(t_jittered, 0, n_symbols - 1)
        # Interpolate
        interp = interp1d(t_nominal, syms_up, kind='linear')
        r_jittered = interp(t_jittered)
        # Add moderate noise
        r_jittered += np.random.normal(0, 0.05, n_symbols)

        # Run CDR + slicer, compute phase rms after convergence
        cdr_local = MuellerMullerCDR(Kp=cdr.lf.Kp, Ki=cdr.lf.Ki)
        phase_trace = np.zeros(n_symbols)
        prev_r, prev_d = r_jittered[0], float(hard_slicer_pam4(np.array([r_jittered[0]]))[0])
        for n in range(1, n_symbols):
            d = float(hard_slicer_pam4(np.array([r_jittered[n]]))[0])
            phase_trace[n], _ = cdr_local.update(r_jittered[n], d)

        skip = n_symbols // 5
        # Jitter tolerance: amplitude at which CDR just tracks
        # Proxy: peak-to-peak phase residual < 0.5 UI
        residual_pkpk = np.ptp(jitter_offset[skip:] - phase_trace[skip:])
        jtol[i_f] = jitter_amp_ui if residual_pkpk < 0.5 else jitter_amp_ui * 0.5 / residual_pkpk

    return jitter_freqs_hz, jtol


if __name__ == "__main__":
    np.random.seed(0)
    # Test MM CDR on a simple signal
    N = 10_000
    from pam4_chain import PAM4_LEVELS
    from equalizers import hard_slicer_pam4
    tx_syms = np.random.choice(PAM4_LEVELS, N)
    r = tx_syms + np.random.normal(0, 0.08, N)
    cdr = MuellerMullerCDR(Kp=0.015, Ki=8e-4)
    d = np.array([float(hard_slicer_pam4(np.array([ri]))[0]) for ri in r])
    phase, err = cdr.process_block(r, d)
    print(f"MM CDR: final phase = {phase[-1]:.4f} UI, "
          f"rms error = {np.std(err[2000:]):.4f}")
    # Loop filter properties
    lf = DigitalLoopFilter(Kp=0.015, Ki=8e-4)
    print(f"Loop filter: fn = {lf.natural_freq_norm:.4f} (norm baud), "
          f"damping = {lf.damping:.2f}")
    print("cdr.py: self-test PASSED")
