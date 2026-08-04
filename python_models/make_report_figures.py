"""
make_report_figures.py — Report-quality figures from link_sim sweep results.

Reads the CSVs in results/ (produced by link_sim.py sweep modes) and renders:
    fig1_eyes.png         eye diagrams vs channel length (the eyes closing)
    fig2_ber_vs_snr.png   BER waterfall vs SNR, with no-ISI theory reference
    fig3_ber_vs_loss.png  BER vs channel loss, with CDR lock-loss marked
    fig4_jtol.png         jitter tolerance vs SJ frequency

Regenerate the CSVs first if needed:
    python link_sim.py --mode sweep_snr  --n_symbols 30000 --channel_cm 3
    python link_sim.py --mode sweep_loss --n_symbols 25000 --snr_db 28
    python link_sim.py --mode jtol --channel_cm 3 --snr_db 26
"""

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

from channel import Channel
from pam4_chain import PAM4Transmitter, tx_waveform
from rx_frontend import CTLE

RES = Path("results")

# ── Palette (light mode) ─────────────────────────────────────────────────────
SURFACE   = "#fcfcfb"
INK       = "#0b0b0b"
INK_2     = "#52514e"
MUTED     = "#898781"
GRID      = "#e1e0d9"
BASELINE  = "#c3c2b7"
BLUE      = "#2a78d6"     # series 1 — simulation
CRITICAL  = "#d03b3b"     # status — lock lost (icon+label, never color alone)

plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans", "sans-serif"],
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "axes.edgecolor": BASELINE, "axes.linewidth": 1.0,
    "axes.labelcolor": INK_2, "axes.titlecolor": INK,
    "axes.titlesize": 11, "axes.labelsize": 10,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "xtick.labelsize": 9, "ytick.labelsize": 9,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False,
    "legend.frameon": False, "legend.fontsize": 9,
})


def _eye_panel(ax, length_cm: float, snr_db: float = 28.0,
               ctle_db: float = 6.0, n_sym: int = 4000, osr: int = 8):
    """Render one eye diagram at the CTLE output for a given trace length."""
    fbaud, f_s = 56e9, 8 * 56e9
    rng = np.random.default_rng(5)
    tx = PAM4Transmitter(prbs_order=15)
    syms, _ = tx.generate(2 * n_sym)
    wave = tx_waveform(syms, osr, fbaud, tx_bw_hz=0.75 * fbaud, rng=rng)
    ch = Channel.from_loss_model(length_cm=length_cm)
    rx = ch.apply(wave, f_s)
    p = np.mean(rx ** 2)
    rx += rng.normal(0, np.sqrt(p * osr / 10 ** (snr_db / 10)), len(rx))
    ctle = CTLE.from_peaking(ctle_db, f_pole1=fbaud / 2, f_pole2=fbaud)
    rx = ctle.apply(rx, f_s)
    # gain-calibrate via pulse cursor so levels land at ±1/±3
    pulse = np.zeros(400)
    pulse[200] = 1.0
    pr = ctle.apply(ch.apply(
        tx_waveform(pulse, osr, fbaud, tx_bw_hz=0.75 * fbaud, rng=rng), f_s),
        f_s)
    rx /= pr[np.argmax(np.abs(pr))]

    fold = 2 * osr
    seg = rx[100 * osr:]
    n_tr = len(seg) // fold
    eye = seg[:n_tr * fold].reshape(n_tr, fold)
    t = np.linspace(0, 2, fold)
    ax.plot(t, eye.T, color=BLUE, alpha=0.035, lw=0.6)
    il = -ch.nloss_at_nyquist(fbaud)
    ax.set_title(f"{length_cm:.0f} cm  ({il:.0f} dB loss)")
    ax.set_xlabel("time [UI]")
    ax.set_ylim(-4.6, 4.6)
    ax.grid(False)


def fig_eyes():
    fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.4), sharey=True)
    for ax, L in zip(axes, [2.0, 6.0, 10.0]):
        _eye_panel(ax, L)
    axes[0].set_ylabel("amplitude [symbol units]")
    fig.suptitle("Received eye vs channel length — 56 Gbaud PAM-4, "
                 "after 6 dB CTLE", color=INK, fontsize=12, y=1.02)
    fig.text(0.5, -0.04,
             "Three open 'eyes' = recoverable signal. Longer trace -> more "
             "high-frequency loss -> the eyes close.",
             ha="center", color=INK_2, fontsize=9)
    fig.tight_layout()
    fig.savefig(RES / "fig1_eyes.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def fig_ber_snr():
    df = pd.read_csv(RES / "sweep_snr.csv")
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    ax.set_yscale("log")
    # theory reference (no ISI, ideal receiver)
    ax.plot(df.snr_db, df.ber_theory_no_isi, ls="--", color=MUTED, lw=1.6,
            label="theory (ideal RX, no ISI)")
    # simulation: measured points; zero-error points plotted at their
    # 95 % Wilson upper bound as open markers
    meas = df[df.ber > 0]
    zero = df[df.ber == 0]
    ax.plot(meas.snr_db, meas.ber, color=BLUE, lw=2.0, marker="o",
            ms=6, label="simulation (full RX)")
    if len(zero):
        ax.plot(zero.snr_db, zero.ber_ub95, ls="none", marker="v", ms=8,
                mfc="none", mec=BLUE, mew=1.8)
        for _, r in zero.iterrows():
            ax.annotate("0 errors\n(95% bound)", (r.snr_db, r.ber_ub95),
                        textcoords="offset points", xytext=(8, -2),
                        fontsize=8.5, color=INK_2)
    ax.annotate("implementation penalty:\nresidual ISI + CTLE noise boost\n"
                "+ 6-bit ADC + jitter + TI mismatch",
                xy=(21, 2e-3), fontsize=8.5, color=INK_2, ha="center")
    ax.set_xlabel("SNR at channel output [dB]")
    ax.set_ylabel("bit error rate")
    ax.set_title("BER waterfall — 3 cm channel (9 dB), closed CDR loop")
    ax.set_ylim(1e-7, 0.5)
    ax.legend(loc="lower left")
    fig.tight_layout()
    fig.savefig(RES / "fig2_ber_vs_snr.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def fig_ber_loss():
    df = pd.read_csv(RES / "sweep_loss.csv")
    df["il"] = -df.il_nyq_db
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    ax.set_yscale("log")
    locked = df[df.cdr_locked]
    lost = df[~df.cdr_locked]
    l_meas = locked[locked.ber > 0]
    l_zero = locked[locked.ber == 0]
    ax.plot(locked.il, np.where(locked.ber > 0, locked.ber, locked.ber_ub95),
            color=BLUE, lw=2.0, ls="-", zorder=1)
    ax.plot(l_meas.il, l_meas.ber, ls="none", marker="o", ms=6, color=BLUE,
            label="CDR locked")
    if len(l_zero):
        ax.plot(l_zero.il, l_zero.ber_ub95, ls="none", marker="v", ms=8,
                mfc="none", mec=BLUE, mew=1.8)
        ax.annotate("0 errors (95% bound)",
                    (l_zero.il.iloc[0], l_zero.ber_ub95.iloc[0]),
                    textcoords="offset points", xytext=(8, -3),
                    fontsize=8.5, color=INK_2)
    if len(lost):
        ax.plot(lost.il, lost.ber, ls="none", marker="X", ms=9,
                color=CRITICAL, label="CDR lock LOST")
        ax.annotate("timing loop cannot lock:\neye closed before EQ -> needs\n"
                    "stronger CTLE / more RX EQ",
                    xy=(lost.il.iloc[0], lost.ber.iloc[0]),
                    textcoords="offset points", xytext=(-160, -30),
                    fontsize=8.5, color=INK_2)
    ax.axhline(2.4e-4, color=MUTED, ls=":", lw=1.4)
    ax.annotate("KP4 FEC limit (2.4e-4)", xy=(6.2, 2.4e-4),
                textcoords="offset points", xytext=(0, 5),
                fontsize=8.5, color=INK_2)
    ax.set_xlabel("channel loss at Nyquist [dB]")
    ax.set_ylabel("bit error rate")
    ax.set_title("BER vs channel loss — SNR 28 dB, CTLE fixed at 6 dB")
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(RES / "fig3_ber_vs_loss.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def fig_jtol():
    df = pd.read_csv(RES / "jtol.csv")
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.set_xscale("log")
    f_mhz = df.sj_freq_hz / 1e6
    ax.plot(f_mhz, df.jtol_ui, color=BLUE, lw=2.0, marker="o", ms=6,
            drawstyle="steps-post")
    ax.annotate("slow jitter: CDR tracks it\n(tolerates a full UI)",
                xy=(0.45, 1.0), textcoords="offset points", xytext=(0, -28),
                fontsize=8.5, color=INK_2)
    ax.annotate("fast jitter: beyond the loop bandwidth,\nonly the raw eye "
                "margin is left",
                xy=(30, 0.1), textcoords="offset points", xytext=(-10, 14),
                fontsize=8.5, color=INK_2)
    ax.axvspan(1.0, 3.16, color=GRID, alpha=0.5, zorder=0)
    ax.annotate("loop bandwidth\ncorner", xy=(1.7, 0.55), fontsize=8.5,
                color=MUTED, ha="center")
    ax.set_xlabel("sinusoidal jitter frequency [MHz]")
    ax.set_ylabel("tolerated jitter amplitude [UI]")
    ax.set_title("Jitter tolerance — closed CDR loop, BER limit 1e-3")
    ax.set_ylim(0, 1.12)
    fig.tight_layout()
    fig.savefig(RES / "fig4_jtol.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def fig_crossval():
    """Statistical engine vs time-domain measurements vs no-ISI theory."""
    from statistical_eye import StatisticalEye
    from link_sim import LinkConfig
    from channel import ber_from_snr_pam4
    df = pd.read_csv(RES / "sweep_snr.csv")
    snr_grid = np.arange(14.0, 30.5, 1.0)
    stat = []
    for snr in snr_grid:
        cfg = LinkConfig(channel_cm=3.0, noise_db=float(snr))
        stat.append(StatisticalEye.from_link_config(cfg)
                    .analyse(n_phase=15).ber)
    fig, ax = plt.subplots(figsize=(7.4, 4.8))
    ax.set_yscale("log")
    ax.plot(snr_grid, ber_from_snr_pam4(snr_grid), ls="--", color=MUTED,
            lw=1.6, label="theory (ideal RX, no ISI)")
    ax.plot(snr_grid, stat, color="#008300", lw=2.0,
            label="statistical engine (semi-analytic)")
    meas = df[df.ber > 0]
    ax.plot(meas.snr_db, meas.ber, ls="none", marker="o", ms=7, color=BLUE,
            label="time-domain engine (counted errors)")
    zero = df[df.ber == 0]
    if len(zero):
        ax.plot(zero.snr_db, zero.ber_ub95, ls="none", marker="v", ms=8,
                mfc="none", mec=BLUE, mew=1.8)
    ax.annotate("time-domain floor:\ncan't count below ~1e-5",
                xy=(27.5, 3e-6), fontsize=8.5, color=INK_2, ha="center")
    ax.annotate("statistical engine\nextrapolates cleanly",
                xy=(29.3, 1e-8), fontsize=8.5, color="#006300", ha="center")
    ax.set_xlabel("SNR at channel output [dB]")
    ax.set_ylabel("bit error rate")
    ax.set_title("Cross-validation — two independent engines, one link "
                 "(3 cm, 6 dB CTLE)")
    ax.set_ylim(1e-12, 0.5)
    ax.legend(loc="lower left")
    fig.tight_layout()
    fig.savefig(RES / "fig5_crossval.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def fig_bathtub():
    """Deep statistical bathtub at a high-SNR operating point."""
    from statistical_eye import StatisticalEye
    from link_sim import LinkConfig
    cfg = LinkConfig(channel_cm=3.0, noise_db=32.0)
    res = StatisticalEye.from_link_config(cfg).analyse(
        phase_span_ui=0.5, n_phase=81)
    fig, ax = plt.subplots(figsize=(7.4, 4.4))
    ax.set_yscale("log")
    ax.plot(res.phase_ui, np.maximum(res.ber_vs_phase, 1e-30),
            color=BLUE, lw=2.0)
    for tgt, ls in [(1e-6, ":"), (1e-12, "--")]:
        w = res.eye_width_ui.get(tgt, 0.0)
        ax.axhline(tgt, color=MUTED, ls=ls, lw=1.2)
        ax.annotate(f"BER {tgt:.0e}: eye width {w:.2f} UI",
                    xy=(-0.48, tgt), textcoords="offset points",
                    xytext=(0, 4), fontsize=8.5, color=INK_2)
    ax.set_xlabel("sampling phase offset from cursor [UI]")
    ax.set_ylabel("bit error rate")
    ax.set_title("Statistical bathtub — 3 cm @ SNR 32 dB "
                 "(unreachable by error counting)")
    ax.set_ylim(1e-16, 1.0)
    fig.tight_layout()
    fig.savefig(RES / "fig6_bathtub.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def fig_ctle_opt():
    """CTLE optimization landscape: slicer BER + CDR feasibility, stacked."""
    path = RES / "ctle_optimization.csv"
    if not path.exists():
        print("  (skip fig7 — run link_sim.py --mode optimize first)")
        return
    df = pd.read_csv(path)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.4, 6.2), sharex=True)
    ok = df[df.cdr_feasible]
    bad = df[~df.cdr_feasible]
    ax1.set_yscale("log")
    ax1.plot(df.peaking_db, df.ber, color=BASELINE, lw=1.2, zorder=1)
    ax1.plot(ok.peaking_db, ok.ber, ls="none", marker="o", ms=7, color=BLUE,
             label="CDR-feasible")
    ax1.plot(bad.peaking_db, bad.ber, ls="none", marker="X", ms=9,
             color=CRITICAL, label="CDR-infeasible")
    best = ok.loc[ok.ber.idxmin()]
    ax1.annotate("optimum", xy=(best.peaking_db, best.ber),
                 textcoords="offset points", xytext=(10, 8),
                 fontsize=9, color=INK)
    ax1.set_ylabel("slicer BER (statistical)")
    ax1.set_title("CTLE optimization — slicer margin vs timing health "
                  "(6 cm channel)")
    ax1.legend(loc="lower right")
    ax2.plot(df.peaking_db, df.cdr_crossing_jitter_ui, color=BLUE, lw=2.0,
             marker="o", ms=6)
    ax2.axhline(0.6, color=CRITICAL, ls="--", lw=1.4)
    ax2.annotate("lock boundary (0.6 UI)", xy=(9.5, 0.6),
                 textcoords="offset points", xytext=(0, 6),
                 fontsize=8.5, color=CRITICAL)
    ax2.set_xlabel("CTLE peaking [dB]")
    ax2.set_ylabel("crossing jitter [UI]")
    fig.tight_layout()
    fig.savefig(RES / "fig7_ctle_opt.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def fig_arch_compare():
    """
    CTLE-peaking sweep at a fixed 6 cm channel: the discriminating view.
    (A loss sweep at 6 dB CTLE shows the two architectures tying — with
    adequate peaking the raw eye is Alexander-friendly, and the deep-loss
    failures are eye margin/clipping, not timing. The difference appears at
    LOW peaking, where the raw crossings smear but the equalized eye is fine.)
    """
    from link_sim import LinkConfig, run_link
    from dataclasses import replace
    path = RES / "arch_compare_pk.csv"
    if path.exists():
        df = pd.read_csv(path)
    else:
        rows = []
        base = LinkConfig(channel_cm=6.0, noise_db=28.0,
                          n_symbols=20_000, training_len=6_000)
        for arch in ("alexander", "mm_postffe"):
            for pk in (0.0, 1.0, 2.0, 3.0, 4.0, 6.0, 8.0):
                r = run_link(replace(base, ctle_peaking_db=pk, cdr_arch=arch),
                             verbose=False)
                r["ctle_db"] = pk
                rows.append(r)
                print(f"  {arch} pk={pk}: BER={r['ber']:.2e} "
                      f"jit={r['cdr_jitter_mui']:.0f} mUI")
        df = pd.DataFrame(rows)
        df.to_csv(path, index=False)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.4, 6.4), sharex=True)
    styles = {"alexander": (BLUE, "o", "Alexander PD (raw eye)"),
              "mm_postffe": ("#008300", "s", "MM PD behind timing FFE")}
    ax1.set_yscale("log")
    for arch, (col, mk, lbl) in styles.items():
        d = df[df.cdr_arch == arch].sort_values("ctle_db")
        ber_plot = np.where(d.ber > 0, d.ber, d.ber_ub95)
        ax1.plot(d.ctle_db, ber_plot, color=col, lw=2.0, marker=mk, ms=7,
                 label=lbl)
        ax2.plot(d.ctle_db, d.cdr_jitter_mui, color=col, lw=2.0, marker=mk,
                 ms=7)
    ax1.axhline(2.4e-4, color=MUTED, ls=":", lw=1.4)
    ax1.annotate("KP4 FEC limit", xy=(6.2, 2.4e-4),
                 textcoords="offset points", xytext=(0, 5),
                 fontsize=8.5, color=INK_2)
    ax1.annotate("0 dB: BER clipping-limited\n(both architectures — the\n"
                 "CTLE's irreplaceable job is\nADC dynamic range)",
                 xy=(0.35, 4.5e-3), fontsize=8.5, color=INK_2)
    ax2.annotate("timing decoupled from AFE tuning", xy=(3.2, 15),
                 fontsize=8.5, color="#006300")
    ax1.set_ylabel("bit error rate")
    ax1.set_title("CDR architecture vs CTLE peaking — 6 cm channel, "
                  "SNR 28 dB")
    ax1.legend(loc="upper right")
    ax2.set_xlabel("CTLE peaking [dB]")
    ax2.set_ylabel("CDR rms jitter [mUI]")
    fig.tight_layout()
    fig.savefig(RES / "fig8_arch_compare.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    RES.mkdir(exist_ok=True)
    fig_eyes()
    print("fig1_eyes.png")
    fig_ber_snr()
    print("fig2_ber_vs_snr.png")
    fig_ber_loss()
    print("fig3_ber_vs_loss.png")
    fig_jtol()
    print("fig4_jtol.png")
    fig_crossval()
    print("fig5_crossval.png")
    fig_bathtub()
    print("fig6_bathtub.png")
    fig_ctle_opt()
    print("fig7_ctle_opt.png")
    fig_arch_compare()
    print("fig8_arch_compare.png")
    print("All figures written to results/")
