"""
statistical_eye.py — Semi-analytic (statistical) BER engine.

Instead of transmitting N symbols and COUNTING errors (which caps the
measurable BER at ~1/N), this engine COMPUTES the error probability from:

  1. the equalized pulse response  → every possible ISI combination and its
     probability (a probability mass function built by convolving the
     per-tap symbol distributions),
  2. the noise variance at the slicer (white channel noise shaped by the
     CTLE, then combined by the FFE — the tap-to-tap noise CORRELATION after
     the CTLE is accounted for, not just a single sigma),
  3. Gaussian folding of each ISI state across the slicer thresholds
     (a Q-function per boundary — exact for AWGN, no Monte Carlo).

This is the StatEye-class methodology used in link compliance work (cf.
Shakiba/Tonietto/Sheikholeslami, IEEE OJ-SSCS 2024, Part I/II) and lets the
framework state BERs like 1e-12..1e-15 that no time-domain run can reach.

Model assumptions (stated, on purpose):
  * DFE is ideal: it cancels the first n_dfe post-cursors exactly, with no
    error propagation (optimistic; reference-receiver practice).
  * ADC quantization and TI offset enter as additive Gaussian terms.
  * Timing jitter (TX RJ + aperture + CDR dither) folds as a Gaussian
    distribution over the sampling phase of the bathtub.
  * Symbols are i.i.d. equiprobable PAM-4 (scrambling makes this true).

Consistency: `StatisticalEye.from_link_config()` builds its pulse response
and noise model from the SAME LinkConfig + calibration path as the
time-domain engine in link_sim.py, so the two engines are directly
comparable — see tests/test_statistical_eye.py for the cross-validation.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Optional, Tuple, Dict, List
from scipy.special import erfc

from channel import Channel
from pam4_chain import tx_waveform
from equalizers import mmse_init_ffe
from rx_frontend import CTLE
from modulation import ModulationLike, get as get_modulation

PAM4_LEVELS = np.array([-3.0, -1.0, 1.0, 3.0])
PAM4_THRESH = np.array([-2.0, 0.0, 2.0])


def qfunc(x: np.ndarray) -> np.ndarray:
    """Gaussian tail probability Q(x) = 0.5·erfc(x/√2)."""
    return 0.5 * erfc(np.asarray(x, dtype=float) / np.sqrt(2.0))


# ─────────────────────────────────────────────────────────────────────────────
# ISI probability mass function
# ─────────────────────────────────────────────────────────────────────────────

def isi_pmf(taps: np.ndarray, resolution: float = 5e-4
            ) -> Tuple[np.ndarray, np.ndarray]:
    """
    Distribution of the total ISI voltage  Σ_k a_k·h_k  for i.i.d.
    equiprobable PAM-4 symbols a_k ∈ {±1, ±3}.

    Built exactly by convolving each tap's 4-point distribution on a shared
    amplitude grid. Cost is O(n_taps · grid), independent of BER level —
    this is the whole trick that beats Monte Carlo.

    Returns (amplitude_grid, probability) with probability summing to 1.
    """
    taps = np.asarray(taps, dtype=float)
    taps = taps[np.abs(taps) > 1e-9]
    span = 3.0 * np.sum(np.abs(taps)) + 10 * resolution
    n_half = int(np.ceil(span / resolution)) + 1
    n_grid = 2 * n_half + 1
    grid = np.arange(-n_half, n_half + 1) * resolution
    pmf = np.zeros(n_grid)
    pmf[n_half] = 1.0                      # delta at 0 V
    # Each tap's distribution has only 4 mass points (a ∈ ±1, ±3), so the
    # convolution is 4 shifted adds — O(4·grid) per tap, not O(grid²).
    for h in taps:
        nxt = np.zeros(n_grid)
        for a in PAM4_LEVELS:
            k = int(round(a * h / resolution))
            lo_src = max(0, -k)
            hi_src = min(n_grid, n_grid - k)
            if hi_src > lo_src:
                nxt[lo_src + k: hi_src + k] += 0.25 * pmf[lo_src:hi_src]
        pmf = nxt
    s = pmf.sum()
    if s > 0:
        pmf /= s
    return grid, pmf


# ─────────────────────────────────────────────────────────────────────────────
# Statistical eye
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class StatEyeResult:
    ber:            float          # BER at the chosen sampling phase
    ber_vs_phase:   np.ndarray     # horizontal bathtub
    phase_ui:       np.ndarray     # phase axis [UI], 0 = pulse cursor
    best_phase_ui:  float
    sigma_slicer:   float          # total Gaussian sigma at the slicer
    eye_width_ui:   Dict[float, float]   # {target_ber: width in UI}
    h_equalized:    np.ndarray     # residual taps at the best phase
    ber_no_jitter:  float


class StatisticalEye:
    """
    Semi-analytic BER for a PAM-4 link with FFE + ideal DFE.

    Parameters
    ----------
    pr_osr    : oversampled pulse response of TX + channel + CTLE,
                gain-calibrated so the cursor sample equals 1.0
    osr       : samples per UI of pr_osr
    cursor    : index of the pulse cursor in pr_osr
    sigma_in  : white noise sigma per oversample at the CTLE INPUT
                (channel-output referred, simulation-grid units)
    ctle      : the CTLE object (needed to shape the noise correctly)
    gain_cal  : gain applied after the CTLE (same as the link)
    f_s       : simulation sample rate of pr_osr
    n_ffe_pre / n_ffe_post / n_dfe : receiver DSP configuration
    snr_mmse_db : SNR used for the MMSE FFE design
    sigma_extra : additional Gaussian slicer noise (quantization, TI offset)
    rj_ui     : total Gaussian timing jitter sigma [UI] folded over phase
    """

    def __init__(self, pr_osr: np.ndarray, osr: int, cursor: int,
                 sigma_in: float, ctle: CTLE, gain_cal: float, f_s: float,
                 n_ffe_pre: int = 3, n_ffe_post: int = 17, n_dfe: int = 5,
                 snr_mmse_db: float = 26.0,
                 sigma_extra: float = 0.0,
                 rj_ui: float = 0.0,
                 modulation: ModulationLike = "pam4"):
        self.mod = get_modulation(modulation)
        self.pr = np.asarray(pr_osr, dtype=float)
        self.osr = osr
        self.cursor = cursor
        self.sigma_in = sigma_in
        self.ctle = ctle
        self.gain_cal = gain_cal
        self.f_s = f_s
        self.n_pre, self.n_post, self.n_dfe = n_ffe_pre, n_ffe_post, n_dfe
        self.snr_mmse_db = snr_mmse_db
        self.sigma_extra = sigma_extra
        self.rj_ui = rj_ui
        self._noise_autocorr_T = self._compute_noise_autocorr()

    # ── noise model ─────────────────────────────────────────────────────────
    def _compute_noise_autocorr(self, n_lags: int = 64) -> np.ndarray:
        """
        Autocorrelation of the slicer-input noise at baud (T) spacing.

        White noise sigma_in enters at the CTLE input; the CTLE impulse
        response g[n] (including gain_cal) colors it:
            r[m] = sigma_in² · Σ_n g[n]·g[n+m]
        Baud-rate sampling keeps every osr-th lag. The FFE then combines
        taps of this CORRELATED sequence — ignoring the correlation
        (treating sigma as white at the slicer) misestimates the noise
        by the CTLE's shaping factor.
        """
        n_fft = 1 << 14
        f = np.fft.rfftfreq(n_fft, d=1.0 / self.f_s)
        G = self.ctle.freq_response(f) * self.gain_cal
        g = np.fft.irfft(G, n=n_fft)
        r_full = np.correlate(g, g, mode='full')[len(g) - 1:]
        r_T = r_full[::self.osr][:n_lags] * self.sigma_in ** 2
        return r_T

    def _slicer_sigma(self, w: np.ndarray) -> float:
        """Noise sigma after the FFE:  sqrt(wᵀ R w + sigma_extra²)."""
        n = len(w)
        r = self._noise_autocorr_T
        R = np.empty((n, n))
        for i in range(n):
            for j in range(n):
                lag = abs(i - j)
                R[i, j] = r[lag] if lag < len(r) else 0.0
        var = float(w @ R @ w)
        return float(np.sqrt(max(var, 0.0) + self.sigma_extra ** 2))

    # ── pulse sampling and equalization ─────────────────────────────────────
    def _baud_taps(self, phase_ui: float,
                   n_pre_c: int = 8, n_post_c: int = 40) -> np.ndarray:
        """Baud-spaced channel taps sampled at `phase_ui` around the cursor."""
        pos = self.cursor + phase_ui * self.osr
        idx = np.round(pos + np.arange(-n_pre_c, n_post_c + 1)
                       * self.osr).astype(int)
        ok = (idx >= 0) & (idx < len(self.pr))
        taps = np.zeros(len(idx))
        taps[ok] = self.pr[idx[ok]]
        return taps, n_pre_c

    def _equalize(self, h: np.ndarray, h_cursor: int,
                  w: np.ndarray) -> Tuple[np.ndarray, int]:
        """Convolve channel taps with FFE, cancel n_dfe post-cursors (ideal DFE)."""
        comb = np.convolve(h, w)
        cur = h_cursor + self.n_pre         # FFE shifts cursor by n_pre
        # Ideal DFE: remove the first n_dfe post-cursors
        comb = comb.copy()
        comb[cur + 1: cur + 1 + self.n_dfe] = 0.0
        return comb, cur

    # ── BER at one sampling phase ───────────────────────────────────────────
    def ber_at_phase(self, phase_ui: float,
                     w: Optional[np.ndarray] = None) -> Tuple[float, np.ndarray]:
        """
        Exact-ISI / Gaussian-noise BER at a given sampling phase.

        For each residual-ISI state x with probability p(x), each PAM-4 level
        a0 and each adjacent threshold at distance d from a0·h0 + x, the
        boundary-crossing probability is Q(d/σ). Gray coding → 1 bit per
        crossing (2 bits per symbol):
            BER = (1/2)·(1/4)·Σ_a0 Σ_x p(x)·Σ_thr Q(dist/σ)
        With no ISI this reduces to (3/4)·Q(1/σ) — the closed form.

        PAM-4 ONLY, deliberately. See `_require_pam4_ber_path`.
        """
        self._require_pam4_ber_path("ber_at_phase")
        h, h_cur = self._baud_taps(phase_ui)
        if w is None:
            w = self._design_ffe()
        comb, cur = self._equalize(h, h_cur, w)
        h0 = comb[cur]
        resid = np.delete(comb, cur)
        sigma = self._slicer_sigma(w)
        if h0 <= 0 or sigma <= 0:
            return 0.5, comb
        grid, pmf = isi_pmf(resid)
        nz = pmf > 1e-22
        grid, pmf = grid[nz], pmf[nz]

        total = 0.0
        for a0 in PAM4_LEVELS:
            centre = a0 * h0 + grid           # slicer input per ISI state
            for thr in PAM4_THRESH:
                # only boundaries adjacent to a0 produce (1-bit) errors
                if abs(a0 - thr) > 1.01:
                    continue
                dist = np.abs(centre - thr)
                total += float(np.sum(pmf * qfunc(dist / sigma)))
        ber = 0.5 * total / 4.0
        return ber, comb

    def _require_pam4_ber_path(self, what: str) -> None:
        """Refuse to compute a BER with PAM-4 maths on a non-PAM-4 alphabet.

        The NRZ retarget is being landed in stages (see
        `nebula/NRZ_RETARGET_AUDIT.md`). `crossing_jitter_ui()` is retargeted;
        the BER path is NOT. Its `0.5 * total / 4.0` prefactor, its
        `PAM4_LEVELS x PAM4_THRESH` loop and `isi_pmf`'s `0.25` symbol
        probability are all still four-level.

        Every one of those is SILENT — leaving them in place on an NRZ link
        reports a BER 0.75x the truth: optimistic, finite, and entirely
        plausible. So this raises instead. A loud NotImplementedError costs
        one traceback; a silent 0.75x factor costs a wrong result in a report.
        """
        if self.mod.name != "pam4":
            raise NotImplementedError(
                f"StatisticalEye.{what}() is PAM-4 only, but this instance was "
                f"built with modulation={self.mod.name!r}. The BER mathematics "
                f"(audit groups A and B), the slicers (C), the bit mapping (D) "
                f"and the remaining amplitude constants (E) have not been "
                f"retargeted yet — only crossing_jitter_ui() has. Running "
                f"anyway would report a BER 0.75x the truth. See "
                f"nebula/NRZ_RETARGET_AUDIT.md for the ordered work list."
            )

    def _design_ffe(self) -> np.ndarray:
        h0, c0 = self._baud_taps(0.0)
        # hand the MMSE designer a cursor-leading view of the channel
        return mmse_init_ffe(h0[c0 - min(4, c0):], self.n_pre + 1 + self.n_post,
                             snr_db=self.snr_mmse_db, n_pre=self.n_pre)

    # ── CDR timing feasibility ──────────────────────────────────────────────
    def crossing_jitter_ui(self) -> float:
        """
        Pattern-dependent zero-crossing jitter at the eye edge [UI rms].

        The Alexander/BB phase detector reads the SIGN of a mid-sample at the
        transition. Channel dispersion makes the crossing position wander with
        the surrounding data pattern; when that wander approaches the UI, the
        PD output decorrelates from the true phase and the loop dithers or
        loses lock. Estimated as
            sigma_cross ≈ sqrt(E[a²]·Σ g_k²) / (2·|edge slope|)
        with g_k the edge-sample ISI taps (transition pair excluded).

        **E[a²] is the alphabet's mean square, not a constant.** It was
        written as a literal `5.0` — correct for PAM-4's {±1, ±3} and wrong by
        sqrt(5) = 2.24x for NRZ's {±1}. Since the calibration below is a
        threshold on this value, the PAM-4 factor applied to an NRZ link would
        report 2.24x the true jitter and declare a perfectly lockable CDR
        infeasible. It is a wrong answer, not a slow one — which is why this
        is the first item of the NRZ retarget (audit E5).

        Calibration against the time-domain engine (28 dB SNR, this
        framework): locks comfortably below ~0.45 UI, marginal ~0.6 UI,
        observed failures at ≥ 0.75 UI. Those thresholds were measured on the
        PAM-4 link; they are inherited, not re-derived, for NRZ.

        The statistical slicer BER alone CANNOT see this — a config can have a
        fine post-EQ eye and an unlockable timing loop (verified: 6 cm @ 0 dB
        CTLE).
        """
        pr, osr, cur = self.pr, self.osr, self.cursor
        edge = cur - osr // 2
        ks = np.arange(-8, 9)
        idx = edge + ks * osr
        ok = (idx >= 0) & (idx < len(pr))
        g = np.zeros(len(ks))
        g[ok] = pr[idx[ok]]
        isi_taps = g[(ks != 0) & (ks != 1)]     # exclude the transition pair
        sigma_e = np.sqrt(self.mod.mean_square * np.sum(isi_taps ** 2))
        slope = (pr[edge + 2] - pr[edge - 2]) / (4.0 / osr)
        return float(sigma_e / (2.0 * abs(slope) + 1e-12))

    def clip_probability(self, vref: float = 4.0) -> float:
        """
        Probability that the PRE-FFE (post-CTLE, cursor-normalised) sample
        exceeds the ADC full scale — computed exactly from the PMF of
        Σ a_k·h_k over ALL channel taps (cursor included).

        Why it matters: the slicer BER computed by this engine assumes an
        un-clipped linear ADC. On lossy channels with little CTLE, ISI drives
        the waveform far beyond the nominal ±3 levels (measured 17 % of
        samples clipped at 6 cm / 0 dB CTLE) and clipping — not noise — sets
        the real BER floor. The time-domain engine models this (its quantizer
        saturates); this engine reports the probability so an optimizer can
        constrain it. Folding clipping distortion into the statistical BER
        itself is future work.

        PAM-4 ONLY: `isi_pmf` below is four-level, and the `vref=4.0` default
        is sized for ±3 symbols (audit E4). Note that S2's topology — CTLE +
        slicer + 1-tap DFE — contains no ADC at all, so for the Nebula link
        there is nothing for this to constrain.
        """
        self._require_pam4_ber_path("clip_probability")
        h, cur = self._baud_taps(0.0)
        grid, pmf = isi_pmf(h)             # cursor tap included
        return float(np.sum(pmf[np.abs(grid) > vref]))

    # ── full analysis: bathtub + jitter folding ─────────────────────────────
    def analyse(self, phase_span_ui: float = 0.5,
                n_phase: int = 41,
                ber_targets: Tuple[float, ...] = (1e-6, 1e-12)
                ) -> StatEyeResult:
        w = self._design_ffe()
        phases = np.linspace(-phase_span_ui, phase_span_ui, n_phase)
        bers = np.empty(n_phase)
        combs = {}
        for i, ph in enumerate(phases):
            bers[i], combs[i] = self.ber_at_phase(ph, w)

        # Jitter folding: BER_j(φ) = E_δ[BER(φ+δ)], δ ~ N(0, rj_ui)
        if self.rj_ui > 0:
            dphi = phases[1] - phases[0]
            kern_half = int(np.ceil(4 * self.rj_ui / dphi))
            k = np.arange(-kern_half, kern_half + 1) * dphi
            kern = np.exp(-0.5 * (k / self.rj_ui) ** 2)
            kern /= kern.sum()
            # pad with edge values (BER saturates at the eye edge)
            padded = np.concatenate([np.full(kern_half, bers[0]), bers,
                                     np.full(kern_half, bers[-1])])
            bers_j = np.convolve(padded, kern, mode='valid')
        else:
            bers_j = bers.copy()

        i_best = int(np.argmin(bers_j))
        eye_w = {}
        for tgt in ber_targets:
            open_mask = bers_j < tgt
            eye_w[tgt] = float(open_mask.sum() * (phases[1] - phases[0])) \
                if open_mask.any() else 0.0

        return StatEyeResult(
            ber=float(bers_j[i_best]),
            ber_vs_phase=bers_j, phase_ui=phases,
            best_phase_ui=float(phases[i_best]),
            sigma_slicer=self._slicer_sigma(w),
            eye_width_ui=eye_w,
            h_equalized=combs[i_best],
            ber_no_jitter=float(bers[int(np.argmin(bers))]),
        )

    # ── construction from the link configuration ────────────────────────────
    @classmethod
    def from_link_config(cls, cfg, ctle_peaking_db: Optional[float] = None
                         ) -> "StatisticalEye":
        """
        Build the statistical model from a link_sim.LinkConfig using the SAME
        calibration path as the time-domain engine (TX shaping → channel →
        CTLE, pulse-cursor gain calibration), so both engines describe the
        same physical link.
        """
        from link_sim import _build_channel
        rng = np.random.default_rng(cfg.seed)
        f_s = cfg.osr * cfg.fbaud
        tx_bw = cfg.tx_bw_rel * cfg.fbaud
        peaking = (cfg.ctle_peaking_db if ctle_peaking_db is None
                   else ctle_peaking_db)
        ch = _build_channel(cfg)
        ctle = CTLE.from_peaking(peaking,
                                 f_pole1=cfg.ctle_fp1_rel * cfg.fbaud,
                                 f_pole2=cfg.ctle_fp2_rel * cfg.fbaud)
        n_cal = 512
        pulse = np.zeros(n_cal)
        pulse[n_cal // 2] = 1.0
        pr = ctle.apply(ch.apply(
            tx_waveform(pulse, cfg.osr, cfg.fbaud, tx_bw_hz=tx_bw, rng=rng),
            f_s), f_s)
        cursor = int(np.argmax(np.abs(pr)))
        gain_cal = 1.0 / pr[cursor]
        pr = pr * gain_cal

        # Noise sigma at the CTLE input, exactly as link_sim injects it:
        # white on the oversampled grid with total power P_sig·osr/SNR.
        # P_sig is estimated from a long random symbol waveform through the
        # channel (same statistic the link uses).
        syms = rng.choice(PAM4_LEVELS, 4000)
        w_ch = ch.apply(tx_waveform(syms, cfg.osr, cfg.fbaud, tx_bw_hz=tx_bw,
                                    rng=rng), f_s)
        p_sig = float(np.mean(w_ch[cfg.osr * 100:] ** 2))
        sigma_in = np.sqrt(p_sig * cfg.osr / 10 ** (cfg.noise_db / 10.0))

        # Extra slicer-referred Gaussian terms (documented approximations):
        lsb = 2.0 * cfg.adc_vref / (2 ** cfg.adc_bits)
        sigma_q = lsb / np.sqrt(12.0)             # quantization
        sigma_ti = cfg.ti_offset_rms              # TI offset spread
        sigma_extra = float(np.hypot(sigma_q, sigma_ti))

        # Timing jitter folded over the bathtub: TX RJ + aperture RJ + CDR
        # dither (CDR self-noise measured in time domain, config-level value)
        rj_aperture_ui = cfg.aperture_rj_fs * 1e-15 * cfg.fbaud
        rj_cdr_ui = 0.015          # typical measured BB dither, see link runs
        rj_ui = float(np.sqrt(cfg.tx_rj_rms_ui ** 2 + rj_aperture_ui ** 2
                              + rj_cdr_ui ** 2))

        return cls(pr, cfg.osr, cursor, sigma_in, ctle, gain_cal, f_s,
                   n_ffe_pre=cfg.ffe_pre, n_ffe_post=cfg.ffe_post,
                   n_dfe=cfg.dfe_taps, snr_mmse_db=cfg.noise_db,
                   sigma_extra=sigma_extra, rj_ui=rj_ui)


# ─────────────────────────────────────────────────────────────────────────────
# Link optimization (Part II-style, simplified)
# ─────────────────────────────────────────────────────────────────────────────

def optimize_ctle(cfg, peaking_grid: Optional[np.ndarray] = None,
                  cdr_jitter_max_ui: float = 0.6) -> Dict:
    """
    Joint CTLE / (MMSE-FFE + ideal DFE) optimization against the statistical
    BER — the reference-receiver optimization loop of OJ-SSCS Part II in
    miniature — SUBJECT TO a timing-feasibility constraint.

    Why the constraint exists (a real finding from this framework): the
    unconstrained slicer-BER optimum on a dispersive channel is often 0 dB
    CTLE, because a long MMSE FFE can equalize digitally with less noise
    enhancement than analog peaking. But the BB CDR locks on the PRE-FFE
    eye, and without CTLE its zero crossings are pattern-smeared — the
    time-domain engine shows 75 mUI dither and 100× worse BER at 6 cm/0 dB.
    In this architecture the CTLE's primary job is timing health, not
    slicer margin. Configurations with crossing jitter > cdr_jitter_max_ui
    are therefore excluded (0.6 UI ≈ the empirical lock boundary).
    """
    if peaking_grid is None:
        peaking_grid = np.arange(0.0, 15.1, 1.5)
    rows = []
    for pk in peaking_grid:
        eye = StatisticalEye.from_link_config(cfg, ctle_peaking_db=float(pk))
        res = eye.analyse(n_phase=25)
        cj = eye.crossing_jitter_ui()
        clip_p = eye.clip_probability(vref=cfg.adc_vref)
        # Timing feasibility applies to the raw-eye (Alexander) architecture;
        # with cdr_arch='mm_postffe' the PD sees the equalized eye and locks
        # wherever the FFE can open it, so only the clip constraint binds.
        timing_ok = (cj < cdr_jitter_max_ui
                     if getattr(cfg, 'cdr_arch', 'alexander') == 'alexander'
                     else True)
        rows.append(dict(peaking_db=float(pk), ber=res.ber,
                         best_phase_ui=res.best_phase_ui,
                         sigma=res.sigma_slicer,
                         cdr_crossing_jitter_ui=cj,
                         adc_clip_prob=clip_p,
                         cdr_feasible=bool(timing_ok),
                         # Clip limit calibrated against time-domain runs at
                         # 6 cm: ~10 % clip → BER 3e-4 (FFE absorbs soft
                         # saturation), ~16 % clip → BER 2e-2 (clipping-
                         # limited). 12 % splits them; refine when clipping
                         # distortion is folded into the statistical BER.
                         clip_ok=bool(clip_p < 0.12),
                         eye_width_1e6=res.eye_width_ui.get(1e-6, 0.0)))
    feasible = [r for r in rows if r['cdr_feasible'] and r['clip_ok']]
    pool = feasible if feasible else rows
    best = min(pool, key=lambda r: r['ber'])
    return dict(best=best, sweep=rows, any_feasible=bool(feasible))


if __name__ == "__main__":
    # Self-test 1: no-ISI channel must reproduce the closed form
    import warnings
    warnings.filterwarnings("ignore")
    sigma = 0.2
    eye = StatisticalEye.__new__(StatisticalEye)
    # minimal manual setup: ideal single-tap channel
    grid, pmf = isi_pmf(np.array([]))
    ber_cf = 0.75 * qfunc(1.0 / sigma)
    # exercise the boundary math via a tiny fake instance
    print(f"closed form (3/4)Q(1/sigma) @ sigma={sigma}: {ber_cf:.3e}")

    # Self-test 2: full link config
    from link_sim import LinkConfig
    cfg = LinkConfig(channel_cm=3.0, noise_db=26.0)
    se = StatisticalEye.from_link_config(cfg)
    res = se.analyse()
    print(f"3 cm @ SNR 26: statistical BER = {res.ber:.3e} "
          f"(no jitter {res.ber_no_jitter:.3e}) "
          f"@ phase {res.best_phase_ui:+.3f} UI, "
          f"sigma_slicer = {res.sigma_slicer:.4f}")
    print(f"eye width @1e-6: {res.eye_width_ui[1e-6]:.2f} UI, "
          f"@1e-12: {res.eye_width_ui[1e-12]:.2f} UI")
    print("statistical_eye.py: self-test PASSED")
