"""
rx_frontend.py — Analog front-end + timing recovery for the oversampled RX.

Implements the receiver path between the channel output and the DSP:

    channel out ──(+noise, injected BEFORE the CTLE)──▶ CTLE ──▶ AGC ──▶
        ──▶ CDR-driven sampler (MM TED + PI loop, fractional interpolation,
             aperture jitter, TI mismatch, ADC quantisation) ──▶ baud samples

Design notes
------------
* The CTLE is a real 1-zero / 2-pole transfer function applied in the
  frequency domain on the oversampled waveform. Because the noise is added
  at the channel output (i.e. at the CTLE input), CTLE noise enhancement —
  the central CTLE design tradeoff — is captured, unlike the earlier
  baud-rate 3-tap FIR "CTLE" which shaped signal but never saw noise.
* The sampler closes the timing loop: a Mueller-Müller phase detector on the
  sliced baud samples drives a PI loop filter which moves the fractional
  sampling instant on the oversampled grid (Catmull-Rom interpolation).
  Frequency offset (ppm) between TX and RX is supported and absorbed by the
  loop integrator, so JTOL and lock behaviour are now simulatable.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Optional, Tuple

from adc_model import ideal_quantize


# ─────────────────────────────────────────────────────────────────────────────
# CTLE — continuous-time linear equalizer (1 zero, 2 poles)
# ─────────────────────────────────────────────────────────────────────────────

class CTLE:
    """
    H(s) = g_dc · (1 + s/ωz) / ((1 + s/ωp1)(1 + s/ωp2))

    With fp2 ≫ fp1 the mid-band peaking is ≈ 20·log10(fp1/fz) dB above DC.
    `from_peaking` places the zero for a requested peaking value, which is
    how a real CTLE's digital peaking-control code is abstracted.
    """

    def __init__(self, f_zero: float, f_pole1: float, f_pole2: float,
                 g_dc: float = 1.0):
        self.fz, self.fp1, self.fp2, self.g_dc = f_zero, f_pole1, f_pole2, g_dc

    @classmethod
    def from_peaking(cls, peaking_db: float,
                     f_pole1: float,
                     f_pole2: float,
                     g_dc: float = 1.0) -> "CTLE":
        """
        Place the zero to realise `peaking_db` of boost.

        The asymptotic rule fz = fp1/10^(pk/20) only holds for fp2 ≫ fp1;
        with realistic pole spacing (fp2 ≈ 2·fp1) the second pole erodes the
        boost, so the zero is calibrated numerically (a few fixed-point
        iterations on the realised peaking).

        **`f_pole1` and `f_pole2` are REQUIRED, on purpose.** They used to
        default to 28e9 / 56e9 — the poles of a 112G PAM-4 part in 28 nm,
        expressed as ABSOLUTE frequencies. That made `CTLE.from_peaking(6.0)`
        a callable, plausible-looking, completely silent way to build a 5 Gbps
        equaliser with its poles at 28 and 56 GHz: eleven times above the
        band, so the response is flat where the data lives and the requested
        peaking is delivered nowhere useful. CLAUDEwa.md §12 names this trap
        specifically; `nebula/NRZ_RETARGET_AUDIT.md` item F2 calls it "the
        trap in its purest form".

        There is no correct default, because the right poles depend on the
        baud rate — so there is now no default. Pass them relative to your
        own `fbaud` (e.g. `f_pole1=fbaud/2, f_pole2=fbaud`), or, in the Nebula
        link layer, from the fitted device poles and never from this
        constructor's convenience.
        """
        if peaking_db <= 0.0:
            return cls(f_pole1 * 1e3, f_pole1, f_pole2, g_dc)  # zero disabled
        f_zero = f_pole1 / 10 ** (peaking_db / 20.0)
        c = cls(f_zero, f_pole1, f_pole2, g_dc)
        for _ in range(8):
            err_db = c.peaking_db() - peaking_db
            if abs(err_db) < 0.05:
                break
            c.fz *= 10 ** (err_db / 20.0)
        return c

    def freq_response(self, f: np.ndarray) -> np.ndarray:
        s = 2j * np.pi * np.asarray(f, dtype=float)
        wz, wp1, wp2 = (2 * np.pi * self.fz, 2 * np.pi * self.fp1,
                        2 * np.pi * self.fp2)
        return self.g_dc * (1 + s / wz) / ((1 + s / wp1) * (1 + s / wp2))

    def peaking_db(self) -> float:
        """Numerical peaking: max gain over DC gain, in dB."""
        f = np.logspace(8, np.log10(self.fp2 * 4), 2000)
        h = np.abs(self.freq_response(f))
        return 20 * np.log10(np.max(h) / np.abs(self.g_dc))

    def apply(self, x: np.ndarray, f_s: float) -> np.ndarray:
        """Filter waveform sampled at f_s (frequency-domain, zero-padded)."""
        x = np.asarray(x, dtype=float)
        n_fft = int(2 ** np.ceil(np.log2(len(x) + 4096)))
        f = np.fft.rfftfreq(n_fft, d=1.0 / f_s)
        Y = np.fft.rfft(x, n=n_fft) * self.freq_response(f)
        return np.fft.irfft(Y, n=n_fft)[:len(x)]


# ─────────────────────────────────────────────────────────────────────────────
# AGC
# ─────────────────────────────────────────────────────────────────────────────

PAM4_RMS = np.sqrt(5.0)   # rms of equiprobable {±1, ±3}


def agc_scale(x: np.ndarray, skip: int = 0) -> float:
    """
    Gain that maps the waveform to PAM-4 "symbol units" (levels ≈ ±1, ±3)
    by matching the waveform rms to the ideal PAM-4 rms. Simple single-shot
    AGC; a decision-directed AGC loop belongs to Phase 3.
    """
    rms = np.sqrt(np.mean(x[skip:] ** 2))
    return PAM4_RMS / max(rms, 1e-15)


# ─────────────────────────────────────────────────────────────────────────────
# CDR-driven sampler
# ─────────────────────────────────────────────────────────────────────────────

def _catmull_rom(wave: np.ndarray, t: float) -> float:
    """4-tap Catmull-Rom interpolation of `wave` at fractional index t."""
    i = int(np.floor(t))
    u = t - i
    if i < 1 or i > len(wave) - 3:
        return wave[int(np.clip(round(t), 0, len(wave) - 1))]
    x0, x1, x2, x3 = wave[i - 1], wave[i], wave[i + 1], wave[i + 2]
    return 0.5 * (2 * x1 + (-x0 + x2) * u
                  + (2 * x0 - 5 * x1 + 4 * x2 - x3) * u * u
                  + (-x0 + 3 * x1 - 3 * x2 + x3) * u * u * u)


def _slice_pam4(y: float) -> float:
    if y > 2.0:
        return 3.0
    if y > 0.0:
        return 1.0
    if y > -2.0:
        return -1.0
    return -3.0


@dataclass
class SamplerConfig:
    """Sampling + ADC non-ideality configuration (symbol-unit domain)."""
    osr:             int   = 8
    fbaud:           float = 56e9
    pd_mode:         str   = 'alexander'   # 'alexander' | 'mm_postffe'
    # BB loop stability note: updates are pattern-gated (~1 in 4 symbols) but
    # the integrator feeds the phase EVERY symbol, so the effective integral
    # gain is ~4·ki. Keep 4·ki/kp ≤ ~2 % or the loop limit-cycles
    # (ki = 1e-4 with kp = 4e-3 was verified unstable).
    kp:              float = 4e-3     # proportional gain [UI/step]
    ki:              float = 2e-5     # integral gain
    n_acq:           int   = 2000     # P-only symbols before integrator enable
    integ_clamp_ui:  float = 1e-3     # |freq word| clamp [UI/UI] (=1000 ppm)
    ppm_offset:      float = 0.0      # RX clock frequency offset [ppm]
    aperture_rj_fs:  float = 150.0    # sampling-clock RJ [fs rms]
    adc_bits:        int   = 6
    adc_vref:        float = 4.0      # full scale in symbol units (±3 + margin)
    n_sub:           int   = 16       # TI sub-ADC count
    ti_timing_rms_ps: float = 0.15
    ti_gain_rms_db:   float = 0.08
    ti_offset_rms:    float = 0.02    # symbol units
    quantize:        bool  = True


@dataclass
class SamplerResult:
    samples:    np.ndarray   # baud-rate ADC output [symbol units]
    phase_ui:   np.ndarray   # CDR phase trace [UI]
    freq_ui:    np.ndarray   # loop integrator (frequency word) trace
    rms_jitter_ui: float     # rms of phase after acquisition
    locked:     bool


class CDRSampler:
    """
    Baud-rate sampler with a closed Mueller-Müller timing loop.

    Phase detector: pattern-gated PAM-4 Alexander (bang-bang) PD.
    A T/2 mid-sample is interpolated between consecutive data samples; on
    symmetric transitions (d[k−1] = −d[k], i.e. ±1↔∓1 and ±3↔∓3, whose
    zero crossings align at the eye centre) the late/early indicator is
        e_late = sign(m) · sign(d[k] − d[k−1])
    which regulates the mid-sample onto the crossing and hence the data
    sample onto the eye centre. This matches the bang-bang architecture in
    rtl/bb_cdr_ber.sv.

    PI loop filter:
        integ += ki·e ;  phase += kp·e + integ    [phase in UI]

    Why not Mueller-Müller here: sign-MM regulates h(−1) = h(+1), whose
    equilibrium on a well-equalized (low-ISI) pulse sits near the eye EDGE,
    not the centre — verified in simulation (phase settled −0.48 UI off
    cursor, SER 0.44). MM belongs behind the FFE with a programmable h(+1)
    target (production ADC-DSP practice); that lands in Phase 3.

    The sampling instant of RX symbol k on the oversampled grid is
        t[k] = t0 + k·osr·(1 + ppm·1e-6) − phase[k]·osr (+ jitter + TI skew)
    so a TX/RX frequency offset appears exactly as in hardware and must be
    absorbed by the loop integrator.
    """

    def __init__(self, cfg: SamplerConfig,
                 rng: Optional[np.random.Generator] = None,
                 w_pd: Optional[np.ndarray] = None):
        """
        w_pd : frozen timing-path FFE taps (required for pd_mode='mm_postffe').
               In silicon this is a dedicated few-tap FFE feeding only the
               phase detector; freezing it avoids the FFE↔CDR tap-rotation
               degeneracy of a fully joint loop (that co-adaptation study is
               the next Phase 3 step).
        """
        self.cfg = cfg
        self.rng = rng if rng is not None else np.random.default_rng()
        c = cfg
        if c.pd_mode == 'mm_postffe' and w_pd is None:
            raise ValueError("pd_mode='mm_postffe' requires timing-FFE taps w_pd")
        self.w_pd = None if w_pd is None else np.asarray(w_pd, dtype=float)
        self.ti_timing = self.rng.normal(0, c.ti_timing_rms_ps * 1e-12, c.n_sub)
        self.ti_gain = 10 ** (self.rng.normal(0, c.ti_gain_rms_db, c.n_sub) / 20)
        self.ti_offset = self.rng.normal(0, c.ti_offset_rms, c.n_sub)

    def process(self, wave: np.ndarray, t0: float,
                n_symbols: int) -> SamplerResult:
        c = self.cfg
        f_s = c.osr * c.fbaud
        period = c.osr * (1.0 + c.ppm_offset * 1e-6)   # RX-view samples/UI
        aperture_samp = c.aperture_rj_fs * 1e-15 * f_s

        samples = np.zeros(n_symbols)
        phase_tr = np.zeros(n_symbols)
        freq_tr = np.zeros(n_symbols)

        phase = 0.0      # UI
        integ = 0.0
        d_prev = 0.0
        t_prev = None
        t_nom = float(t0)
        # post-FFE MM PD state
        if self.w_pd is not None:
            buf_pd = np.zeros(len(self.w_pd))
            y_pd_prev, d_pd_prev = 0.0, 0.0

        for k in range(n_symbols):
            sub = k % c.n_sub
            t_k = (t_nom - phase * c.osr
                   + self.ti_timing[sub] * f_s
                   + (self.rng.normal(0.0, aperture_samp)
                      if aperture_samp > 0 else 0.0))
            if t_k >= len(wave) - 3:
                samples = samples[:k]
                phase_tr = phase_tr[:k]
                freq_tr = freq_tr[:k]
                n_symbols = k
                break

            y = _catmull_rom(wave, t_k)
            # TI mismatch + quantisation at the sampling instant
            y = y * self.ti_gain[sub] + self.ti_offset[sub]
            if c.quantize:
                y = ideal_quantize(np.array([y]), c.adc_bits, c.adc_vref)[0][0]
            samples[k] = y

            d = _slice_pam4(y)
            e = 0.0
            if c.pd_mode == 'mm_postffe':
                # Mueller-Müller PD on the EQUALIZED sample stream: a frozen
                # timing-path FFE opens the eye first, so the MM equilibrium
                # h_eq(−1) = h_eq(+1) sits near the equalized-eye centre even
                # on channels whose raw crossings are pattern-smeared (the
                # regime where the Alexander PD loses lock). Gated on
                # outer-level pairs for detector gain, as in production.
                buf_pd[1:] = buf_pd[:-1]
                buf_pd[0] = y
                y_pd = float(np.dot(self.w_pd, buf_pd))
                d_pd = _slice_pam4(y_pd)
                if abs(d_pd) == 3.0 and abs(d_pd_prev) == 3.0:
                    # E[y_k·d_{k−1} − y_{k−1}·d_k] ∝ h(+1) − h(−1), which is
                    # POSITIVE when sampling early. This loop's convention is
                    # e > 0 ⇒ retard the sampling instant (phase up = earlier
                    # t_k), so the raw MM product must be negated — verified
                    # empirically: the unnegated form locks ~0.5 UI off-centre
                    # (BER 0.12 at an operating point that should be error-free).
                    e = float(np.sign(y_pd_prev * d_pd - y_pd * d_pd_prev))
                y_pd_prev, d_pd_prev = y_pd, d_pd
            else:
                # Alexander PD on symmetric transitions: mid-sample between
                # the previous and current sampling instants tells early/late.
                if d_prev == -d and d != 0.0 and t_prev is not None:
                    m = _catmull_rom(wave, 0.5 * (t_k + t_prev))
                    e = float(np.sign(m) * np.sign(d - d_prev))

            if e != 0.0:
                # Gear shift: phase-acquire P-only first, then enable the
                # integrator. Enabling it during the initial one-sided
                # transient winds it up, causes cycle slips and frequency
                # runaway (observed, not hypothetical).
                if k >= c.n_acq:
                    integ = float(np.clip(
                        integ + c.ki * e,
                        -c.integ_clamp_ui, c.integ_clamp_ui))
                phase += c.kp * e + integ
            else:
                phase += integ      # frequency feed-forward continues

            d_prev = d
            t_prev = t_k
            phase_tr[k] = phase
            freq_tr[k] = integ
            t_nom += period

        skip = min(n_symbols // 3, 10_000)
        if n_symbols - skip > 10:
            n_tail = len(phase_tr) - skip
            slope, _ = np.polyfit(np.arange(n_tail), phase_tr[skip:], 1)
            detrended = phase_tr[skip:] - np.polyval(
                np.polyfit(np.arange(n_tail), phase_tr[skip:], 1),
                np.arange(n_tail))
            rms_j = float(np.std(detrended))
            # Lock requires BOTH low detrended jitter AND that any phase slope
            # is explained by the frequency word (ppm tracking). A drifting
            # unlocked loop has slope carried by the proportional path, which
            # a pure detrended-rms metric cannot see (verified failure mode).
            residual_slope = abs(slope - float(np.mean(freq_tr[skip:])))
            locked = (rms_j < 0.1) and (residual_slope < 5e-5)
        else:
            rms_j, locked = 1.0, False
        return SamplerResult(samples=samples, phase_ui=phase_tr,
                             freq_ui=freq_tr, rms_jitter_ui=rms_j,
                             locked=locked)


# ─────────────────────────────────────────────────────────────────────────────
# Symbol-delay estimation (for reference alignment)
# ─────────────────────────────────────────────────────────────────────────────

def estimate_delay(samples: np.ndarray, ref_syms: np.ndarray,
                   max_lag: int = 400, n_use: int = 4000,
                   min_lag: int = -8) -> int:
    """
    Integer symbol delay between the sampled stream and the TX reference,
    via cross-correlation over `n_use` symbols. Result d means
    samples[k + d] carries symbol k — pass it as `sys_delay` to the
    equalizer and as the alignment for BER counting.

    Negative lags are scanned too (min_lag): the CDR can slip whole UIs
    during acquisition, leaving the sampled stream EARLY relative to the
    reference. Skips the first `n_skip` symbols so the CDR acquisition
    transient does not pollute the correlation.
    """
    n_skip = 4096
    n = min(n_use, len(samples) - max_lag - n_skip, len(ref_syms) - n_skip)
    if n <= 0:
        n_skip = 0
        n = min(n_use, len(samples) - max_lag, len(ref_syms))
    if n <= 0:
        return 0
    ref = ref_syms[n_skip:n_skip + n] - np.mean(ref_syms[n_skip:n_skip + n])
    best_lag, best_val = 0, -np.inf
    for lag in range(min_lag, max_lag):
        i0 = n_skip + lag
        if i0 < 0 or i0 + n > len(samples):
            continue
        seg = samples[i0:i0 + n] - np.mean(samples[i0:i0 + n])
        v = float(np.dot(seg, ref))
        if v > best_val:
            best_val, best_lag = v, lag
    return best_lag


if __name__ == "__main__":
    # Self-test: CTLE peaking accuracy + CDR lock on a clean PAM-4 waveform
    rng = np.random.default_rng(0)

    ctle = CTLE.from_peaking(9.0, f_pole1=28e9, f_pole2=56e9)
    pk = ctle.peaking_db()
    print(f"CTLE requested 9.0 dB peaking, realised {pk:.2f} dB")
    assert abs(pk - 9.0) < 1.5

    # CDR: ideal PAM-4 ZOH waveform with 100 ppm offset and 0.25 UI static phase
    from pam4_chain import tx_waveform, PAM4_LEVELS
    osr, fbaud, n_sym = 8, 56e9, 30_000
    syms = rng.choice(PAM4_LEVELS, n_sym + 200)
    wave = tx_waveform(syms, osr=osr, fbaud=fbaud, tx_bw_hz=0.75 * fbaud,
                       rng=rng)
    cfg = SamplerConfig(osr=osr, fbaud=fbaud, ppm_offset=100.0,
                        aperture_rj_fs=0.0, ti_timing_rms_ps=0.0,
                        ti_gain_rms_db=0.0, ti_offset_rms=0.0, quantize=False)
    smp = CDRSampler(cfg, rng)
    res = smp.process(wave, t0=osr * 0.75, n_symbols=n_sym)  # 0.25 UI early
    print(f"CDR: rms jitter {res.rms_jitter_ui*1e3:.2f} mUI, "
          f"locked={res.locked}, "
          f"final freq word {res.freq_ui[-1]*1e6:.1f} uUI/UI "
          f"(expect ~100 ppm magnitude, sign per loop convention)")
    d = estimate_delay(res.samples, syms)
    print(f"Estimated delay: {d} symbols")
    assert res.locked, "CDR failed to lock"
    print("rx_frontend.py: self-test PASSED")
