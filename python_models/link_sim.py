"""
link_sim.py — Top-level 112G/224G PAM-4 link simulation harness (waveform engine).

Chain (all on an oversampled waveform, OSR samples/UI):

  PRBS -> scramble -> Gray -> TX-FFE -> ZOH + TX bandwidth + TX jitter (RJ/SJ)
      -> channel H(f) -> + AWGN (at the CTLE INPUT, so noise enhancement is real)
      -> CTLE (1 zero / 2 poles) -> gain calibration
      -> CDR-driven sampler (Alexander BB PD + PI loop, ppm offset, aperture RJ,
         TI mismatch, ADC quantisation)
      -> joint FFE+DFE (single-pass LMS, supervised -> decision-directed)
      -> bit BER with Wilson confidence bound

Modes:
    python link_sim.py                        # single run, default config
    python link_sim.py --mode sweep_snr       # BER vs SNR + theory overlay
    python link_sim.py --mode sweep_loss      # BER vs channel length
    python link_sim.py --mode monte_carlo     # seed-varied MC (noise, jitter,
                                              #   TI mismatch all re-drawn)
    python link_sim.py --mode jtol            # SJ jitter-tolerance sweep

Reproducibility: every run derives ALL randomness from LinkConfig.seed via a
numpy Generator. (The pre-audit version hard-seeded the global RNG inside
run_link, which silently made every Monte-Carlo run identical.)
"""

import numpy as np
import pandas as pd
import argparse
import json
from pathlib import Path
from dataclasses import dataclass, asdict, replace
from typing import Optional, List, Dict

from channel import Channel, ber_from_snr_pam4
from pam4_chain import (PAM4Transmitter, tx_waveform, gray_decode,
                        ber_wilson_upper)
from equalizers import FFEDFEReceiver
from rx_frontend import CTLE, CDRSampler, SamplerConfig, estimate_delay


# ─────────────────────────────────────────────────────────────────────────────
# Link configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class LinkConfig:
    """Complete link specification for the 112G PAM-4 reference receiver."""
    # ── Simulation ─────────────────────
    seed:            int   = 1
    n_symbols:       int   = 50_000
    osr:             int   = 8          # samples per UI

    # ── TX ─────────────────────────────
    fbaud:           float = 56e9
    prbs_order:      int   = 31
    ffe_taps_tx:     Optional[List] = None    # TX pre-emphasis taps
    tx_bw_rel:       float = 0.75       # TX driver BW as fraction of fbaud
    tx_rj_rms_ui:    float = 0.005      # TX random jitter [UI rms]
    sj_amp_ui:       float = 0.0        # sinusoidal jitter (JTOL) [UI]
    sj_freq_hz:      float = 0.0

    # ── Channel ────────────────────────
    channel_model:   str   = 'loss'     # 'loss' | 'sparam' | 'optical_imdd'
    sparam_file:     str   = ''
    channel_cm:      float = 5.0        # trace length [cm]
    alpha_skin:      float = 0.30       # dB/cm/sqrt(GHz)
    alpha_diel:      float = 0.05       # dB/cm/GHz
    noise_db:        float = 26.0       # SNR at channel output, measured in
                                        # the symbol Nyquist band [0, fbaud/2]

    # ── CTLE ───────────────────────────
    ctle_peaking_db: float = 6.0
    ctle_fp1_rel:    float = 0.5        # first pole / fbaud
    ctle_fp2_rel:    float = 1.0        # second pole / fbaud

    # ── Sampler / ADC / CDR ────────────
    adc_bits:        int   = 6
    adc_vref:        float = 4.0        # full scale in symbol units
    aperture_rj_fs:  float = 150.0
    n_sub:           int   = 16
    ti_timing_rms_ps: float = 0.15
    ti_gain_rms_db:   float = 0.08
    ti_offset_rms:    float = 0.02
    cdr_kp:          float = 4e-3
    cdr_ki:          float = 2e-5
    ppm_offset:      float = 50.0       # TX/RX frequency offset [ppm]
    cdr_arch:        str   = 'alexander'  # 'alexander' | 'mm_postffe'
                                        # mm_postffe: MM PD behind a frozen
                                        # MMSE timing-FFE (production ADC-DSP
                                        # arrangement; works on channels whose
                                        # raw crossings are pattern-smeared)

    # ── DSP ────────────────────────────
    ffe_pre:         int   = 3
    ffe_post:        int   = 17
    dfe_taps:        int   = 5
    mu_ffe:          float = 5e-4
    mu_dfe:          float = 2e-4
    ss_lms:          bool  = True
    training_len:    int   = 8_000

    def __post_init__(self):
        if self.ffe_taps_tx is None:
            self.ffe_taps_tx = [-0.05, 0.9, -0.05]


def _build_channel(cfg: LinkConfig) -> Channel:
    if cfg.channel_model == 'sparam' and cfg.sparam_file:
        return Channel.from_sparam(cfg.sparam_file)
    if cfg.channel_model == 'optical_imdd':
        return Channel.optical_imdd(bw_laser=30e9, bw_pd=35e9)
    return Channel.from_loss_model(alpha_skin=cfg.alpha_skin,
                                   alpha_diel=cfg.alpha_diel,
                                   length_cm=cfg.channel_cm)


# ─────────────────────────────────────────────────────────────────────────────
# Single link simulation run
# ─────────────────────────────────────────────────────────────────────────────

def run_link(cfg: LinkConfig, plot: bool = False,
             verbose: bool = True) -> Dict:
    """Run one complete waveform-level link simulation. Returns metric dict."""
    rng = np.random.default_rng(cfg.seed)
    f_s = cfg.osr * cfg.fbaud
    tx_bw = cfg.tx_bw_rel * cfg.fbaud

    # ── Channel + CTLE objects ───────────────────────────────────────────────
    ch = _build_channel(cfg)
    il_nyq = ch.nloss_at_nyquist(cfg.fbaud)
    ctle = CTLE.from_peaking(cfg.ctle_peaking_db,
                             f_pole1=cfg.ctle_fp1_rel * cfg.fbaud,
                             f_pole2=cfg.ctle_fp2_rel * cfg.fbaud)

    # ── Calibration pulse through the identical (noiseless) path ────────────
    n_cal = 512
    pulse_syms = np.zeros(n_cal)
    pulse_syms[n_cal // 2] = 1.0
    pr = ctle.apply(
        ch.apply(tx_waveform(pulse_syms, cfg.osr, cfg.fbaud, tx_bw_hz=tx_bw,
                             rng=rng), f_s), f_s)
    cursor = int(np.argmax(np.abs(pr)))
    gain_cal = 1.0 / pr[cursor]
    t0 = float(cursor - (n_cal // 2) * cfg.osr)
    # Baud-spaced combined pulse taps for the FFE MMSE warm start
    n_pre_t, n_post_t = 4, 20
    idx = cursor + np.arange(-n_pre_t, n_post_t + 1) * cfg.osr
    idx = idx[(idx >= 0) & (idx < len(pr))]
    h_baud = pr[idx] * gain_cal

    # ── TX ───────────────────────────────────────────────────────────────────
    tx = PAM4Transmitter(prbs_order=cfg.prbs_order,
                         ffe_taps=np.array(cfg.ffe_taps_tx))
    n_margin = 300
    syms_tx, bits_line = tx.generate(2 * (cfg.n_symbols + n_margin))
    ref_syms = tx.reference_symbols
    wave = tx_waveform(syms_tx, cfg.osr, cfg.fbaud, tx_bw_hz=tx_bw,
                       rj_rms_ui=cfg.tx_rj_rms_ui,
                       sj_amp_ui=cfg.sj_amp_ui, sj_freq_hz=cfg.sj_freq_hz,
                       rng=rng)

    # ── Channel + noise (injected BEFORE the CTLE) ───────────────────────────
    rx_ch = ch.apply(wave, f_s)
    # cfg.noise_db is the SNR in the symbol Nyquist band [0, fbaud/2].
    # The simulation runs at f_s = osr·fbaud with white noise, so the total
    # simulated noise power is osr× the in-band power.
    p_sig = float(np.mean(rx_ch ** 2))
    sigma = np.sqrt(p_sig * cfg.osr / 10 ** (cfg.noise_db / 10.0))
    rx_ch = rx_ch + rng.normal(0.0, sigma, len(rx_ch))

    # ── CTLE + gain calibration ──────────────────────────────────────────────
    rx_eq = ctle.apply(rx_ch, f_s) * gain_cal
    # ADC overload diagnostic: fraction of the waveform beyond full scale.
    # With cursor-normalised gain, ISI raises the peak-to-nominal ratio on
    # lossy channels; at 6 cm / 0 dB CTLE ~17 % of samples clip and the
    # post-EQ BER floor is set by clipping, not noise (measured 2026-07-18).
    clip_frac = float(np.mean(np.abs(rx_eq[cfg.osr * 200:]) > cfg.adc_vref))

    # ── CDR-driven sampler (closed timing loop) ──────────────────────────────
    scfg = SamplerConfig(osr=cfg.osr, fbaud=cfg.fbaud,
                         pd_mode=cfg.cdr_arch,
                         kp=cfg.cdr_kp, ki=cfg.cdr_ki,
                         ppm_offset=cfg.ppm_offset,
                         aperture_rj_fs=cfg.aperture_rj_fs,
                         adc_bits=cfg.adc_bits, adc_vref=cfg.adc_vref,
                         n_sub=cfg.n_sub,
                         ti_timing_rms_ps=cfg.ti_timing_rms_ps,
                         ti_gain_rms_db=cfg.ti_gain_rms_db,
                         ti_offset_rms=cfg.ti_offset_rms,
                         quantize=True)
    w_pd = None
    if cfg.cdr_arch == 'mm_postffe':
        from equalizers import mmse_init_ffe
        # Timing-path FFE: same MMSE design as the data path's warm start,
        # but FROZEN — it only feeds the phase detector.
        w_pd = mmse_init_ffe(h_baud, cfg.ffe_pre + 1 + cfg.ffe_post,
                             snr_db=cfg.noise_db, n_pre=cfg.ffe_pre)
    sampler = CDRSampler(scfg, rng, w_pd=w_pd)
    res = sampler.process(rx_eq, t0=t0, n_symbols=cfg.n_symbols)

    # ── Reference alignment + FFE/DFE ────────────────────────────────────────
    delay = estimate_delay(res.samples, ref_syms)
    rx_dsp = FFEDFEReceiver(n_ffe_pre=cfg.ffe_pre, n_ffe_post=cfg.ffe_post,
                            n_dfe=cfg.dfe_taps, mu_ffe=cfg.mu_ffe,
                            mu_dfe=cfg.mu_dfe, ss_lms=cfg.ss_lms)
    rx_dsp.ffe.init_from_channel(h_baud, snr_db=cfg.noise_db)
    # Bring-up sequencing (as in silicon): CDR acquires first, THEN the DSP
    # adapts. Training on pre-lock samples destroys the MMSE warm start.
    adapt_start = scfg.n_acq + 500
    decisions, info = rx_dsp.process(res.samples, ref_syms=ref_syms,
                                     training_len=cfg.training_len,
                                     sys_delay=delay,
                                     adapt_start=adapt_start)

    # ── BER over the post-training window, with confidence bound ────────────
    k0 = cfg.training_len
    n_dec = len(decisions) - k0
    rx_bits = gray_decode(decisions[k0:])
    tx_bits = bits_line[2 * k0: 2 * k0 + len(rx_bits)]
    n_bits = min(len(rx_bits), len(tx_bits))
    n_err = int(np.sum(rx_bits[:n_bits] != tx_bits[:n_bits]))
    ber = n_err / max(n_bits, 1)
    ber_ub = ber_wilson_upper(n_err, n_bits)

    if verbose:
        print(f"[Channel] IL @ Nyquist = {il_nyq:.1f} dB "
              f"({cfg.channel_cm:.0f} cm)")
        print(f"[CTLE]    {cfg.ctle_peaking_db:.1f} dB peaking "
              f"(realised {ctle.peaking_db():.2f} dB)")
        print(f"[CDR]     arch={cfg.cdr_arch}  locked={res.locked}  "
              f"rms jitter={res.rms_jitter_ui*1e3:.1f} mUI  "
              f"freq word={res.freq_ui[-1]*1e6:+.0f} ppm-equivalent")
        print(f"[ADC]     clip fraction = {clip_frac*100:.2f}% of samples "
              f"beyond +/-{cfg.adc_vref:.1f}")
        print(f"[Align]   symbol delay = {delay}")
        print(f"[DSP]     FFE({cfg.ffe_pre}+1+{cfg.ffe_post}) "
              f"+ DFE({cfg.dfe_taps}), training {cfg.training_len} symbols")
        print(f"[BER]     {n_err} errors / {n_bits} bits -> "
              f"BER = {ber:.3e}  (95% upper bound {ber_ub:.3e})")

    # ── Power budget — PLACEHOLDER numbers, not simulation outputs ──────────
    p_total_mw = _power_budget_placeholder(cfg, verbose=verbose)

    if plot:
        _plot_run(cfg, ch, rx_eq, res, info)

    return dict(
        fbaud_gbaud=cfg.fbaud / 1e9, channel_cm=cfg.channel_cm,
        il_nyq_db=il_nyq, snr_db=cfg.noise_db,
        cdr_arch=cfg.cdr_arch,
        cdr_locked=bool(res.locked),
        cdr_jitter_mui=res.rms_jitter_ui * 1e3,
        adc_clip_frac=clip_frac,
        n_errors=n_err, n_bits=n_bits,
        ber=ber, ber_ub95=ber_ub,
        power_mw_placeholder=p_total_mw,
        seed=cfg.seed,
    )


def _power_budget_placeholder(cfg: LinkConfig, verbose: bool) -> float:
    """
    Literature-based placeholder budget (28 nm class). These are NOT
    simulated quantities — do not report them next to measured metrics
    without this caveat.
    """
    p = dict(adc=120.0, ffe=0.8 * (cfg.ffe_pre + 1 + cfg.ffe_post),
             dfe=2.5 * cfg.dfe_taps, cdr=12.0, ctle=20.0, fec=100.0)
    total = sum(p.values())
    if verbose:
        pj = total / (cfg.fbaud * 2e-9)
        print(f"[Power]   ~{total:.0f} mW ({pj:.1f} pJ/bit) -- "
              f"PLACEHOLDER budget, not simulated")
    return total


def _plot_run(cfg, ch, rx_eq, res, info):
    """Diagnostic plots for a single run."""
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(2, 2, figsize=(11, 7))
    # Eye at sampler input
    osr = cfg.osr
    n_ui = 2
    seg = rx_eq[20_000 * osr // 8: 20_000 * osr // 8 + 2000 * osr]
    folds = len(seg) // (n_ui * osr)
    eye = seg[:folds * n_ui * osr].reshape(folds, n_ui * osr)
    t_ax = np.linspace(0, n_ui, n_ui * osr)
    ax[0, 0].plot(t_ax, eye.T, color='steelblue', alpha=0.05, lw=0.5)
    ax[0, 0].set_title('Eye @ CTLE output (pre-ADC)')
    ax[0, 0].set_xlabel('UI')
    # CDR phase
    ax[0, 1].plot(res.phase_ui)
    ax[0, 1].set_title(f'CDR phase [UI] (rms {res.rms_jitter_ui*1e3:.1f} mUI)')
    # Channel + CTLE response
    f = np.linspace(1e8, cfg.fbaud, 500)
    ax[1, 0].plot(f / 1e9,
                  20 * np.log10(np.abs(np.interp(f, ch.freq, np.abs(ch.H)))),
                  label='channel')
    ax[1, 0].axvline(cfg.fbaud / 2e9, ls='--', color='gray')
    ax[1, 0].set_title('Channel |H(f)| [dB]')
    ax[1, 0].set_xlabel('GHz')
    # Slicer error trace
    ax[1, 1].plot(np.abs(info['error']), lw=0.3)
    ax[1, 1].set_title('|slicer error| per symbol')
    plt.tight_layout()
    out = Path('results')
    out.mkdir(exist_ok=True)
    fig.savefig(out / 'link_run.png', dpi=130)
    print(f"[Plot]    saved to {out / 'link_run.png'}")
    plt.show()


# ─────────────────────────────────────────────────────────────────────────────
# Sweeps
# ─────────────────────────────────────────────────────────────────────────────

def sweep_snr(base: LinkConfig, snr_range=None) -> pd.DataFrame:
    if snr_range is None:
        snr_range = np.arange(14, 29, 2.0)
    rows = []
    for snr in snr_range:
        r = run_link(replace(base, noise_db=float(snr)), verbose=False)
        r['ber_theory_no_isi'] = float(ber_from_snr_pam4(snr))
        rows.append(r)
        print(f"  SNR={snr:.0f} dB -> BER={r['ber']:.2e} "
              f"(<={r['ber_ub95']:.1e})  theory(no ISI)={r['ber_theory_no_isi']:.1e}")
    return pd.DataFrame(rows)


def sweep_channel_loss(base: LinkConfig, lengths_cm=None) -> pd.DataFrame:
    if lengths_cm is None:
        lengths_cm = [2, 4, 6, 8, 10, 12]
    rows = []
    for L in lengths_cm:
        r = run_link(replace(base, channel_cm=float(L)), verbose=False)
        rows.append(r)
        print(f"  L={L} cm -> IL={r['il_nyq_db']:.1f} dB -> BER={r['ber']:.2e} "
              f"locked={r['cdr_locked']}")
    return pd.DataFrame(rows)


def monte_carlo(base: LinkConfig, n_runs: int = 50) -> pd.DataFrame:
    """
    Seed-varied Monte Carlo: every run redraws noise, TX jitter, aperture
    jitter and TI mismatch through its own Generator seed.
    """
    rows = []
    for run in range(n_runs):
        r = run_link(replace(base, seed=1000 + run), verbose=False)
        r['run'] = run
        rows.append(r)
        if (run + 1) % 10 == 0:
            df = pd.DataFrame(rows)
            print(f"  MC {run+1}/{n_runs}: BER mean={df.ber.mean():.2e} "
                  f"max={df.ber.max():.2e} lock rate={df.cdr_locked.mean():.2f}")
    df = pd.DataFrame(rows)
    print(f"\nMC summary: BER mean={df.ber.mean():.2e} std={df.ber.std():.2e} "
          f"worst={df.ber.max():.2e} lock rate={df.cdr_locked.mean()*100:.0f}%")
    return df


def jtol_sweep(base: LinkConfig,
               freqs_hz=None,
               ber_limit: float = 1e-3,
               amp_grid=None) -> pd.DataFrame:
    """
    Jitter tolerance: for each SJ frequency, find the largest SJ amplitude
    the closed-loop link tolerates (BER ≤ ber_limit and CDR locked).
    Expected shape: high tolerance well inside the CDR loop bandwidth,
    dropping to a flat floor above it.
    """
    if freqs_hz is None:
        freqs_hz = np.logspace(5.5, 8.5, 7)   # ~300 kHz … 300 MHz
    if amp_grid is None:
        amp_grid = [0.05, 0.1, 0.2, 0.4, 0.7, 1.0]
    short = replace(base, n_symbols=20_000, training_len=5_000)
    rows = []
    for fj in freqs_hz:
        tol = 0.0
        for amp in amp_grid:
            r = run_link(replace(short, sj_amp_ui=amp, sj_freq_hz=float(fj)),
                         verbose=False)
            if r['cdr_locked'] and r['ber'] <= ber_limit:
                tol = amp
            else:
                break
        rows.append(dict(sj_freq_hz=fj, jtol_ui=tol))
        print(f"  f_SJ={fj/1e6:8.2f} MHz -> JTOL={tol:.2f} UI")
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='112G/224G PAM-4 waveform-level link simulator')
    parser.add_argument('--mode', default='single',
                        choices=['single', 'sweep_snr', 'sweep_loss',
                                 'monte_carlo', 'jtol',
                                 'statistical', 'optimize'])
    parser.add_argument('--fbaud', type=float, default=56e9)
    parser.add_argument('--channel_cm', type=float, default=5.0)
    parser.add_argument('--snr_db', type=float, default=26.0)
    parser.add_argument('--ctle_db', type=float, default=6.0)
    parser.add_argument('--n_symbols', type=int, default=50_000)
    parser.add_argument('--n_runs', type=int, default=50)
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--cdr_arch', default='alexander',
                        choices=['alexander', 'mm_postffe'])
    parser.add_argument('--plot', action='store_true')
    parser.add_argument('--out_csv', type=str, default='')
    args = parser.parse_args()

    cfg = LinkConfig(fbaud=args.fbaud, channel_cm=args.channel_cm,
                     noise_db=args.snr_db, ctle_peaking_db=args.ctle_db,
                     n_symbols=args.n_symbols, seed=args.seed,
                     cdr_arch=args.cdr_arch)
    out_dir = Path('results')
    out_dir.mkdir(exist_ok=True)

    if args.mode == 'single':
        result = run_link(cfg, plot=args.plot, verbose=True)
        print("\n[Summary]", json.dumps(result, indent=2))
        return

    if args.mode == 'statistical':
        from statistical_eye import StatisticalEye
        eye = StatisticalEye.from_link_config(cfg)
        res = eye.analyse()
        cj = eye.crossing_jitter_ui()
        print(f"[Statistical] {cfg.channel_cm:.0f} cm @ SNR {cfg.noise_db:.0f} dB, "
              f"CTLE {cfg.ctle_peaking_db:.1f} dB")
        print(f"  BER (semi-analytic)     = {res.ber:.3e}")
        print(f"  best sampling phase     = {res.best_phase_ui:+.3f} UI")
        print(f"  slicer noise sigma      = {res.sigma_slicer:.4f}")
        print(f"  eye width @ BER 1e-6    = {res.eye_width_ui[1e-6]:.3f} UI")
        print(f"  eye width @ BER 1e-12   = {res.eye_width_ui[1e-12]:.3f} UI")
        print(f"  CDR crossing jitter     = {cj:.3f} UI "
              f"({'feasible' if cj < 0.6 else 'INFEASIBLE - CDR will not lock'})")
        df = pd.DataFrame(dict(phase_ui=res.phase_ui, ber=res.ber_vs_phase))
        out = args.out_csv or str(out_dir / 'statistical_bathtub.csv')
        df.to_csv(out, index=False)
        print(f"Bathtub saved to {out}")
        return

    if args.mode == 'optimize':
        from statistical_eye import optimize_ctle
        print(f"=== CTLE optimization ({cfg.channel_cm:.0f} cm, "
              f"SNR {cfg.noise_db:.0f} dB) ===")
        outp = optimize_ctle(cfg)
        for r in outp['sweep']:
            tag = '' if r['cdr_feasible'] else '  << CDR-infeasible'
            print(f"  pk={r['peaking_db']:5.1f} dB: BER={r['ber']:.2e}  "
                  f"crossing jitter={r['cdr_crossing_jitter_ui']:.2f} UI{tag}")
        b = outp['best']
        print(f"\n  OPTIMUM: {b['peaking_db']:.1f} dB peaking -> "
              f"BER {b['ber']:.2e} @ phase {b['best_phase_ui']:+.2f} UI")
        df = pd.DataFrame(outp['sweep'])
        out = args.out_csv or str(out_dir / 'ctle_optimization.csv')
        df.to_csv(out, index=False)
        print(f"Sweep saved to {out}")
        return

    runners = dict(sweep_snr=lambda: sweep_snr(cfg),
                   sweep_loss=lambda: sweep_channel_loss(cfg),
                   monte_carlo=lambda: monte_carlo(cfg, n_runs=args.n_runs),
                   jtol=lambda: jtol_sweep(cfg))
    print(f"=== {args.mode} ===")
    df = runners[args.mode]()
    out = args.out_csv or str(out_dir / f'{args.mode}.csv')
    df.to_csv(out, index=False)
    print(f"Results saved to {out}")


if __name__ == '__main__':
    main()
