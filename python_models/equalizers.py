"""
equalizers.py — DSP equalizer library for high-speed PAM-4 receivers.

Implements:
  - FFE  (feed-forward equalizer, FIR)
  - DFE  (decision-feedback equalizer)
  - LMS  adaptation (floating-point and sign-sign)
  - MMSE tap initialisation (via channel inversion)
  - MLSE (Viterbi, for short channel memories)
  - Fractionally-spaced FFE (T/2-spaced)
  - Fixed-point simulation support

All equalizers follow a common interface:
    eq.process(r) → (decisions, errors, tap_history)
"""

import numpy as np
from typing import Optional, Tuple, List
from dataclasses import dataclass, field


# ─────────────────────────────────────────────────────────────────────────────
# Shared utilities
# ─────────────────────────────────────────────────────────────────────────────

PAM4_LEVELS = np.array([-3.0, -1.0, 1.0, 3.0])
PAM4_THRESH = np.array([-2.0, 0.0, 2.0])

def hard_slicer_pam4(x: np.ndarray,
                     thresh: np.ndarray = PAM4_THRESH) -> np.ndarray:
    d = np.full(len(x), -3.0)
    d[x > thresh[0]] = -1.0
    d[x > thresh[1]] =  1.0
    d[x > thresh[2]] =  3.0
    return d

def quantize_fixed(x: np.ndarray, n_bits: int, x_max: float) -> np.ndarray:
    """Uniform mid-tread quantiser (signed)."""
    lsb = 2 * x_max / (2**n_bits)
    return np.clip(np.round(x / lsb) * lsb, -x_max, x_max - lsb)


# ─────────────────────────────────────────────────────────────────────────────
# MMSE tap initialisation from channel impulse response
# ─────────────────────────────────────────────────────────────────────────────

def mmse_init_ffe(h_ch: np.ndarray, n_ffe: int,
                  snr_db: float = 20.0,
                  n_pre: Optional[int] = None) -> np.ndarray:
    """
    Compute MMSE FFE tap vector from channel impulse response.
    Uses frequency-domain Wiener filter:  W = H* / (|H|² + 1/SNR).

    h_ch   : channel impulse response (baud-rate sampled)
    n_ffe  : number of FFE taps
    snr_db : operating SNR [dB]
    n_pre  : tap index where the FFE expects its main cursor
             (default n_ffe//2). MUST match the consuming FFE's pre-cursor
             count: an earlier revision always centred the peak at n_ffe//2,
             which put the warm-start cursor 7 taps away from FFE(3+1+17)'s
             convention, misaligning the training reference by 7 symbols and
             costing thousands of symbols of re-convergence.

    The Wiener gain is preserved (no re-normalisation) so the equalized
    levels land on the PAM-4 targets immediately.
    """
    if n_pre is None:
        n_pre = n_ffe // 2
    snr_lin = 10 ** (snr_db / 10.0)
    N = max(256, 4 * max(len(h_ch), n_ffe))
    H = np.fft.fft(h_ch, n=N)
    W_mmse = np.conj(H) / (np.abs(H)**2 + 1.0/snr_lin)
    w_time = np.real(np.fft.ifft(W_mmse))
    # Full cyclic peak search: inverting a channel whose cursor is delayed by
    # k taps puts the Wiener peak at index −k (mod N), i.e. near the END of
    # the array — a [:N//2] search window misses it.
    peak = int(np.argmax(np.abs(w_time)))
    # Cyclic extraction so a peak anywhere still yields the pre-cursor taps
    idx = (peak - n_pre + np.arange(n_ffe)) % N
    return w_time[idx]


# ─────────────────────────────────────────────────────────────────────────────
# FFE — Feed-Forward Equalizer (T-spaced)
# ─────────────────────────────────────────────────────────────────────────────

class FFE:
    """
    Baud-rate (T-spaced) FFE with LMS adaptation.

    Parameters
    ----------
    n_pre   : pre-cursor tap count
    n_post  : post-cursor tap count
    mu      : LMS step size
    ss_lms  : if True, use sign-sign LMS (hardware-friendly)
    fix_pt  : if set, quantise taps to (n_bits, x_max)
    """
    def __init__(self, n_pre: int = 3, n_post: int = 17,
                 mu: float = 1e-3, ss_lms: bool = False,
                 fix_pt: Optional[Tuple[int,float]] = None):
        self.n_pre  = n_pre
        self.n_post = n_post
        self.n_taps = n_pre + 1 + n_post
        self.mu     = mu
        self.ss_lms = ss_lms
        self.fix_pt = fix_pt
        # Initialise: main cursor = 1, all others = 0
        self.w = np.zeros(self.n_taps)
        self.w[n_pre] = 1.0
        self._tap_history: List[np.ndarray] = []

    def init_from_channel(self, h_ch: np.ndarray, snr_db: float = 20.0):
        """Warm-start taps from MMSE solution (cursor at this FFE's n_pre)."""
        self.w = mmse_init_ffe(h_ch, self.n_taps, snr_db, n_pre=self.n_pre)

    def process(self, r: np.ndarray,
                ref: Optional[np.ndarray] = None,
                adapt: bool = True,
                log_every: int = 1000) -> Tuple[np.ndarray, np.ndarray]:
        """
        Process received sample stream.

        r    : received samples (baud-rate)
        ref  : reference symbols for supervised LMS (None = use slicer decisions)
        adapt: enable adaptation

        Returns (y_out, errors)
        """
        N = len(r)
        y = np.zeros(N)
        e = np.zeros(N)
        buf = np.zeros(self.n_taps)   # delay line

        for n in range(N):
            # Shift input into tap delay line (in-place, newest at index 0)
            buf[1:] = buf[:-1]
            buf[0] = r[n]
            # FFE output
            y[n] = np.dot(self.w, buf)
            # Decision
            d = hard_slicer_pam4(np.array([y[n]]))[0]
            # Error — y[n] has main cursor at tap n_pre, so it equalises the
            # symbol carried by r[n - n_pre]; the reference must be delayed
            # by n_pre or the LMS trains against the wrong symbol.
            n_sym = n - self.n_pre
            target = ref[n_sym] if (ref is not None and 0 <= n_sym < len(ref)) else d
            e[n] = y[n] - target
            # LMS update
            if adapt:
                if self.ss_lms:
                    self.w -= self.mu * np.sign(e[n]) * np.sign(buf)
                else:
                    self.w -= self.mu * e[n] * buf
                # Optional fixed-point quantisation of taps
                if self.fix_pt:
                    self.w = quantize_fixed(self.w, *self.fix_pt)
            # Periodic tap snapshot
            if n % log_every == 0:
                self._tap_history.append(self.w.copy())

        return y, e

    @property
    def tap_history(self) -> np.ndarray:
        return np.array(self._tap_history)


# ─────────────────────────────────────────────────────────────────────────────
# DFE — Decision-Feedback Equalizer
# ─────────────────────────────────────────────────────────────────────────────

class DFE:
    """
    DFE with speculative first-tap option and LMS adaptation.

    In hardware the DFE feedback loop must close within 1 UI.
    The `speculative` flag models the look-ahead (unrolled) DFE
    by using the correct (noise-free) previous decision for the
    first tap — an optimistic but architecturally valid model.
    """
    def __init__(self, n_taps: int = 5,
                 mu_fb: float = 5e-4, ss_lms: bool = True,
                 speculative: bool = True,
                 fix_pt: Optional[Tuple[int,float]] = None):
        self.n_taps     = n_taps
        self.mu_fb      = mu_fb
        self.ss_lms     = ss_lms
        self.speculative = speculative
        self.fix_pt     = fix_pt
        self.f = np.zeros(n_taps)   # feedback tap weights

    def process_with_ffe(self, ffe_out: np.ndarray,
                         adapt: bool = True,
                         ref: Optional[np.ndarray] = None
                         ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Apply DFE to FFE output stream.

        Returns (decisions, errors)
        """
        N = len(ffe_out)
        d_hat = np.zeros(N)
        e     = np.zeros(N)
        db    = np.zeros(self.n_taps)   # decision buffer

        for n in range(N):
            # Subtract DFE feedback
            slicer_in = ffe_out[n] - np.dot(self.f, db)
            # Hard decision
            d = hard_slicer_pam4(np.array([slicer_in]))[0]
            d_hat[n] = d
            # Error: use reference if provided, else use decision
            target = ref[n] if (ref is not None and n < len(ref)) else d
            e[n] = slicer_in - target
            # Update DFE taps
            if adapt:
                if self.ss_lms:
                    self.f += self.mu_fb * np.sign(e[n]) * np.sign(db)
                else:
                    self.f += self.mu_fb * e[n] * db
                if self.fix_pt:
                    self.f = quantize_fixed(self.f, *self.fix_pt)
            # Shift decision buffer
            db = np.roll(db, 1)
            db[0] = d if not self.speculative else target

        return d_hat, e


# ─────────────────────────────────────────────────────────────────────────────
# Combined FFE + DFE receiver
# ─────────────────────────────────────────────────────────────────────────────

class FFEDFEReceiver:
    """
    Complete linear + DFE receiver with joint LMS adaptation.

    Typical usage
    -------------
    rx = FFEDFEReceiver(n_ffe_pre=3, n_ffe_post=17, n_dfe=5)
    rx.ffe.init_from_channel(channel_taps, snr_db=18)
    decisions, ber_trace = rx.process(received_samples, tx_bits)
    """
    def __init__(self,
                 n_ffe_pre:  int   = 3,
                 n_ffe_post: int   = 17,
                 n_dfe:      int   = 5,
                 mu_ffe:     float = 5e-4,
                 mu_dfe:     float = 2e-4,
                 ss_lms:     bool  = True,
                 adc_bits:   int   = 6,
                 adc_vmax:   float = 1.0):
        self.ffe = FFE(n_pre=n_ffe_pre, n_post=n_ffe_post,
                       mu=mu_ffe, ss_lms=ss_lms)
        self.dfe = DFE(n_taps=n_dfe, mu_fb=mu_dfe, ss_lms=ss_lms)
        self.adc_bits = adc_bits
        self.adc_vmax = adc_vmax

    def quantize_adc(self, r: np.ndarray) -> np.ndarray:
        """Simulate ADC quantisation (only if the input is not already digital)."""
        return quantize_fixed(r, self.adc_bits, self.adc_vmax)

    def process(self, r: np.ndarray,
                ref_syms: Optional[np.ndarray] = None,
                training_len: int = 5000,
                adapt: bool = True,
                sys_delay: int = 0,
                quantize: bool = False,
                adapt_start: int = 0
                ) -> Tuple[np.ndarray, dict]:
        """
        Full receiver processing: single-pass joint FFE+DFE with shared-error
        LMS. The supervised→decision-directed switch happens inline at
        `training_len`, so equalizer delay lines are never reset mid-stream
        (earlier revisions ran two passes with fresh buffers, corrupting the
        symbols around the switch and mis-training the second pass).

        Parameters
        ----------
        r           : baud-rate ADC samples. Alignment convention:
                      r[n + sys_delay] carries symbol n at its cursor.
        ref_syms    : transmitted PAM-4 symbols (±1, ±3) for supervised LMS
        training_len: symbols of supervised adaptation before going
                      decision-directed
        sys_delay   : channel/front-end delay in symbols (cursor position of
                      symbol 0 in `r`). FFE pre-cursor delay handled internally.
        quantize    : re-quantize input (leave False when an ADC model already
                      produced `r` — double quantization is not physical)
        adapt_start : first symbol index at which LMS may adapt. Set past the
                      CDR acquisition window: sign-sign LMS moves every tap by
                      ±µ per symbol REGARDLESS of error size, so training on
                      pre-lock garbage samples walks the MMSE warm start away
                      (observed: mean |e| ≈ 3.7 during acquisition and a
                      wrecked equalizer afterwards). Hardware sequences DSP
                      adaptation after CDR lock for exactly this reason.

        Returns
        -------
        decisions : ndarray indexed by SYMBOL (decisions[k] = decision for
                    TX symbol k), length N - total_delay
        info      : dict with 'error' (per-symbol slicer error), 'slicer_in',
                    'ffe_taps', 'dfe_taps', 'total_delay'
        """
        r_in = self.quantize_adc(r) if quantize else np.asarray(r, dtype=float)
        N = len(r_in)
        total_delay = sys_delay + self.ffe.n_pre   # input index → symbol index
        n_out = max(0, N - total_delay)

        decisions = np.zeros(n_out)
        err_out   = np.zeros(n_out)
        slicer_in_out = np.zeros(n_out)

        w   = self.ffe.w
        f   = self.dfe.f
        buf = np.zeros(self.ffe.n_taps)          # FFE delay line
        db  = np.zeros(self.dfe.n_taps)          # DFE decision buffer

        mu_ffe, mu_dfe = self.ffe.mu, self.dfe.mu_fb
        ss = self.ffe.ss_lms

        for m in range(N):
            buf[1:] = buf[:-1]
            buf[0] = r_in[m]
            k = m - total_delay                  # symbol index of this decision
            if k < 0:
                continue                          # pipeline fill
            y = np.dot(w, buf)
            slicer_in = y - np.dot(f, db)
            d = hard_slicer_pam4(np.array([slicer_in]))[0]

            supervised = (ref_syms is not None and k < training_len
                          and k < len(ref_syms))
            target = ref_syms[k] if supervised else d
            e = slicer_in - target

            if adapt and k >= adapt_start:
                if ss:
                    w -= mu_ffe * np.sign(e) * np.sign(buf)
                    f += mu_dfe * np.sign(e) * np.sign(db)
                else:
                    w -= mu_ffe * e * buf
                    f += mu_dfe * e * db
                if self.ffe.fix_pt:
                    w = self.ffe.w = quantize_fixed(w, *self.ffe.fix_pt)
                if self.dfe.fix_pt:
                    f = self.dfe.f = quantize_fixed(f, *self.dfe.fix_pt)
            if k % 1000 == 0:
                self.ffe._tap_history.append(w.copy())

            # DFE feedback: use the true symbol during supervised training
            # (models error-free speculation), decisions afterwards
            fb = target if (supervised and self.dfe.speculative) else d
            db[1:] = db[:-1]
            db[0] = fb

            decisions[k] = d
            err_out[k] = e
            slicer_in_out[k] = slicer_in

        info = dict(error=err_out, slicer_in=slicer_in_out,
                    ffe_taps=w.copy(), dfe_taps=f.copy(),
                    total_delay=total_delay)
        return decisions, info


# ─────────────────────────────────────────────────────────────────────────────
# Fractionally-spaced FFE (T/2-spaced)
# ─────────────────────────────────────────────────────────────────────────────

class FractionalFFE:
    """
    T/2-spaced (2× oversampled) FFE.
    Provides timing-insensitive equalization and implicit timing recovery.
    Downsamples to baud-rate at output.

    n_taps : number of T/2-spaced taps
    phase  : initial sampling phase offset (0 or 1) for T-rate output
    """
    def __init__(self, n_taps: int = 32, mu: float = 5e-4, phase: int = 0):
        self.n_taps = n_taps
        self.mu     = mu
        self.phase  = phase  # 0 or 1
        self.w      = np.zeros(n_taps)
        self.w[n_taps//2] = 1.0

    def process(self, r_2x: np.ndarray, adapt: bool = True
                ) -> Tuple[np.ndarray, np.ndarray]:
        """
        r_2x : received samples at 2× baud rate
        Returns (decisions, errors) at baud rate
        """
        N = len(r_2x) // 2
        decisions = np.zeros(N)
        errors    = np.zeros(N)
        buf = np.zeros(self.n_taps)

        for n in range(N):
            # Two T/2 samples per symbol
            for sub in range(2):
                idx = 2*n + sub
                buf = np.roll(buf, 1)
                buf[0] = r_2x[idx]

            # Output at selected phase
            y = np.dot(self.w, buf)
            d = hard_slicer_pam4(np.array([y]))[0]
            e = y - d
            decisions[n] = d
            errors[n]    = e
            if adapt:
                self.w -= self.mu * e * buf

        return decisions, errors


# ─────────────────────────────────────────────────────────────────────────────
# MLSE — Maximum Likelihood Sequence Estimation (Viterbi)
# ─────────────────────────────────────────────────────────────────────────────

class MLSE:
    """
    Viterbi MLSE for short PAM-4 channels.

    h_ch      : channel impulse response (baud-rate, length L)
    n_levels  : number of PAM levels (4 for PAM-4)

    State count = n_levels^(L-1).  Practical limit: L ≤ 4 (256 states for PAM-4).
    For longer channels, use MLSE after DFE pre-equalisation.
    """
    def __init__(self, h_ch: np.ndarray, n_levels: int = 4):
        self.h = np.asarray(h_ch[:5])   # max 5 taps (64 states for PAM-4)
        self.L = len(self.h)
        self.M = n_levels
        self.levels = PAM4_LEVELS if n_levels == 4 else np.linspace(-1,1,n_levels)
        self.n_states = self.M ** (self.L - 1)
        self._build_trellis()

    def _build_trellis(self):
        """
        Pre-compute trellis: (state, input) → (next_state, output).

        State encoding: base-M integer over the (L-1) most recent past symbols
        with the MOST RECENT symbol in the LEAST significant digit:
            s = idx(s[n-1]) + idx(s[n-2])·M + … + idx(s[n-L+1])·M^(L-2)
        The decode and the state-update below must use the same convention —
        an earlier revision mixed the two (newest=MSB on decode, newest=LSB on
        update), which silently produced a garbage trellis (SER ≈ 0.7).
        """
        L, M = self.L, self.M
        lev = self.levels
        self.transitions = {}   # (state, sym_idx) → (next_state, channel_output)
        for s in range(self.n_states):
            # past[j] = s[n-1-j]
            past = [lev[(s // M**j) % M] for j in range(L - 1)]
            for sym_i, sym in enumerate(lev):
                seq = [sym] + past   # s[n], s[n-1], …, s[n-L+1]
                ch_out = sum(self.h[k] * seq[k] for k in range(L))
                # next state's past = [s[n], s[n-1], …, s[n-L+2]]
                next_s = sym_i + (s % M**(L - 2)) * M if L >= 2 else 0
                self.transitions[(s, sym_i)] = (next_s, ch_out)

    def detect(self, r: np.ndarray) -> np.ndarray:
        """
        Run Viterbi algorithm on received sequence r.
        Returns detected symbol sequence.
        """
        N = len(r)
        INF = 1e18
        # path_metric[state] = cumulative squared error
        # All-zero init: unknown starting state (don't force state 0)
        pm  = np.zeros(self.n_states)
        # traceback[n][state] = (prev_state, sym_idx)
        tb = []

        for n in range(N):
            new_pm = np.full(self.n_states, INF)
            tb_n   = [None] * self.n_states
            for s in range(self.n_states):
                if pm[s] >= INF:
                    continue
                for sym_i in range(self.M):
                    ns, y_hat = self.transitions[(s, sym_i)]
                    branch = (r[n] - y_hat) ** 2
                    cand   = pm[s] + branch
                    if cand < new_pm[ns]:
                        new_pm[ns] = cand
                        tb_n[ns]   = (s, sym_i)
            pm = new_pm
            tb.append(tb_n)

        # Traceback from best final state
        decisions = np.zeros(N, dtype=int)
        s = int(np.argmin(pm))
        for n in range(N-1, -1, -1):
            if tb[n][s] is None:
                break
            prev_s, sym_i = tb[n][s]
            decisions[n] = sym_i
            s = prev_s

        return self.levels[decisions]


# ─────────────────────────────────────────────────────────────────────────────
# Adaptive threshold optimiser (for mismatched PAM-4 levels)
# ─────────────────────────────────────────────────────────────────────────────

class AdaptiveThreshold:
    """
    Tracks PAM-4 slicer thresholds by estimating conditional means of each level.
    Handles transmitter level mismatch, nonlinearity, and gain errors.
    """
    def __init__(self, mu: float = 1e-4):
        self.mu = mu
        self.level_est = PAM4_LEVELS.copy().astype(float)  # running level estimates
        self.counts = np.ones(4)

    def update(self, y: float, d: float):
        """Update level estimates using decision d."""
        idx = np.argmin(np.abs(PAM4_LEVELS - d))
        self.level_est[idx] += self.mu * (y - self.level_est[idx])
        self.counts[idx] += 1

    @property
    def thresholds(self) -> np.ndarray:
        lvl = np.sort(self.level_est)
        return np.array([(lvl[0]+lvl[1])/2,
                         (lvl[1]+lvl[2])/2,
                         (lvl[2]+lvl[3])/2])


if __name__ == "__main__":
    rng = np.random.default_rng(42)
    # Generate test signal: causal channel with 5-tap ISI, cursor at index 1
    N = 20_000
    h_ch = np.array([0.05, 1.0, 0.30, 0.08, 0.02])
    cursor = int(np.argmax(np.abs(h_ch)))
    tx_syms = rng.choice(PAM4_LEVELS, N)
    rx_raw  = np.convolve(tx_syms, h_ch)[:N]      # causal: r[n+cursor] ~ tx[n]
    rx_noisy = rx_raw + rng.normal(0, 0.1, N)

    # FFE + DFE — reference is the actual transmitted symbol sequence
    rx = FFEDFEReceiver(n_ffe_pre=3, n_ffe_post=20, n_dfe=5)
    rx.ffe.init_from_channel(h_ch, snr_db=20)
    decisions, info = rx.process(rx_noisy, ref_syms=tx_syms,
                                 training_len=4000, sys_delay=cursor)
    n_eval = len(decisions) - 4000
    ser = np.mean(decisions[4000:] != tx_syms[4000:4000+len(decisions)-4000])
    print(f"FFE+DFE receiver: post-training SER = {ser:.3e} "
          f"({n_eval} symbols)")
    assert ser < 1e-2, "FFE+DFE failed to converge on mild ISI channel"

    # MLSE — trellis models r[n] = h[0]·s[n] + h[1]·s[n-1] + …, which matches
    # the causal convolution above, so d_mlse[n] estimates tx[n] directly
    mlse = MLSE(h_ch[:4])
    d_mlse = mlse.detect(rx_noisy[:2000])
    err_mlse = np.mean(d_mlse[:2000] != tx_syms[:2000])
    print(f"MLSE symbol error rate: {err_mlse:.3e}")
    print("equalizers.py: self-test PASSED")
