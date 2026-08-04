"""
visualization.py — Plotting utilities for SerDes and optical link simulation.

Functions:
  - plot_eye_diagram         (PAM-4 with phosphor persistence)
  - plot_constellation       (QAM / PAM-4)
  - plot_ber_curve           (vs SNR, simulation + theory)
  - plot_equalizer_convergence
  - plot_jitter_histogram    (with Q-function extrapolation)
  - plot_channel_response    (IL + group delay)
  - plot_dfe_taps            (tap weight evolution)
  - plot_bathtub_curve
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from typing import Optional, Tuple, List


# ─────────────────────────────────────────────────────────────────────────────
# Matplotlib style defaults
# ─────────────────────────────────────────────────────────────────────────────

def set_style():
    plt.rcParams.update({
        'figure.dpi':        150,
        'figure.facecolor':  'black',
        'axes.facecolor':    '#0a0a0a',
        'axes.edgecolor':    '#404040',
        'axes.labelcolor':   '#cccccc',
        'axes.grid':         True,
        'grid.color':        '#222222',
        'grid.linestyle':    '--',
        'grid.linewidth':    0.5,
        'xtick.color':       '#aaaaaa',
        'ytick.color':       '#aaaaaa',
        'text.color':        '#cccccc',
        'lines.linewidth':   1.5,
        'font.family':       'monospace',
        'font.size':         9,
        'legend.facecolor':  '#111111',
        'legend.edgecolor':  '#333333',
    })


# ─────────────────────────────────────────────────────────────────────────────
# Eye diagram with phosphor persistence
# ─────────────────────────────────────────────────────────────────────────────

def plot_eye_diagram(rx_samples: np.ndarray,
                     fbaud: float,
                     osr: int = 8,
                     n_ui: int = 2,
                     noise_db: float = 25.0,
                     title: str = "PAM-4 Eye Diagram",
                     cmap: str = 'hot',
                     ax: Optional[plt.Axes] = None,
                     show: bool = True) -> plt.Axes:
    """
    Plot PAM-4 eye diagram with 2D histogram (phosphor persistence effect).

    rx_samples : received signal at osr × baud rate
    fbaud      : baud rate [Hz]
    osr        : oversampling ratio
    n_ui       : number of UI to display (typically 2)
    """
    set_style()
    if ax is None:
        fig, ax = plt.subplots(figsize=(6, 4))

    ui_samples = osr
    fold_len   = n_ui * ui_samples
    N_folds    = len(rx_samples) // fold_len
    if N_folds < 10:
        print("[WARNING] Too few UI folds for eye diagram. Increase n_symbols.")
        return ax

    # Fold the waveform
    data = rx_samples[:N_folds * fold_len].reshape(N_folds, fold_len)
    t_axis = np.linspace(-n_ui/2, n_ui/2, fold_len)

    # 2D histogram (phosphor)
    v_min = np.percentile(data, 0.5)
    v_max = np.percentile(data, 99.5)
    H, xedges, yedges = np.histogram2d(
        np.tile(t_axis, N_folds),
        data.ravel(),
        bins=[150, 200],
        range=[[t_axis[0], t_axis[-1]], [v_min, v_max]]
    )
    # Log scale for phosphor effect
    H_log = np.log1p(H.T)
    ax.pcolormesh(xedges, yedges, H_log, cmap=cmap, shading='auto')
    ax.set_xlabel("Time [UI]")
    ax.set_ylabel("Amplitude [a.u.]")
    ax.set_title(title)
    ax.axvline(0, color='cyan', linestyle='--', linewidth=0.8, alpha=0.6)
    ax.axhline(0, color='#444', linestyle='-', linewidth=0.5)
    # Draw PAM-4 threshold lines
    for th in [-2, 0, 2]:
        ax.axhline(th, color='yellow', linestyle=':', linewidth=0.6, alpha=0.5)
    if show:
        plt.tight_layout()
        plt.show()
    return ax


# ─────────────────────────────────────────────────────────────────────────────
# Constellation diagram
# ─────────────────────────────────────────────────────────────────────────────

def plot_constellation(signal_iq: np.ndarray,
                       title: str = "Constellation",
                       max_points: int = 5000,
                       ax: Optional[plt.Axes] = None,
                       show: bool = True) -> plt.Axes:
    """Plot IQ constellation with density colouring."""
    set_style()
    if ax is None:
        fig, ax = plt.subplots(figsize=(5, 5))

    pts = min(max_points, len(signal_iq))
    x = np.real(signal_iq[:pts])
    y = np.imag(signal_iq[:pts])

    lim = np.percentile(np.abs(signal_iq[:pts]), 99) * 1.2
    H, xe, ye = np.histogram2d(x, y, bins=100,
                                range=[[-lim, lim], [-lim, lim]])
    ax.pcolormesh(xe, ye, np.log1p(H.T), cmap='inferno', shading='auto')
    ax.set_xlabel("I")
    ax.set_ylabel("Q")
    ax.set_title(title)
    ax.set_aspect('equal')
    ax.axhline(0, color='#333', lw=0.5)
    ax.axvline(0, color='#333', lw=0.5)
    if show:
        plt.tight_layout()
        plt.show()
    return ax


# ─────────────────────────────────────────────────────────────────────────────
# BER vs SNR curves
# ─────────────────────────────────────────────────────────────────────────────

def plot_ber_curve(snr_db: np.ndarray,
                   ber_sim: Optional[np.ndarray] = None,
                   ber_theory: Optional[np.ndarray] = None,
                   labels: Optional[List[str]] = None,
                   title: str = "BER vs SNR",
                   ax: Optional[plt.Axes] = None,
                   show: bool = True) -> plt.Axes:
    """
    Plot BER curves (simulation and/or theory) on log-scale Y axis.
    """
    set_style()
    if ax is None:
        fig, ax = plt.subplots(figsize=(7, 5))

    colours = ['#00ff88', '#ff6644', '#44aaff', '#ffcc00', '#cc44ff']
    c_idx = 0

    if ber_theory is not None:
        label = (labels[0] if labels else "Theory (PAM-4, AWGN)")
        ax.semilogy(snr_db, ber_theory, '--',
                    color=colours[c_idx], label=label, linewidth=1.5)
        c_idx += 1

    if ber_sim is not None:
        if isinstance(ber_sim, np.ndarray) and ber_sim.ndim == 1:
            ber_sim = [ber_sim]
        for i, b in enumerate(ber_sim):
            label = (labels[i + (1 if ber_theory is not None else 0)]
                     if labels and i + 1 < len(labels) else f"Simulation {i+1}")
            valid = b > 0
            ax.semilogy(snr_db[valid], b[valid], 'o-',
                        color=colours[c_idx % len(colours)],
                        label=label, markersize=4)
            c_idx += 1

    # Reference lines
    for ref_ber, label in [(1e-3, 'KR4 FEC threshold'),
                            (2e-2, 'KP4 FEC threshold'),
                            (1e-12, 'Target post-FEC')]:
        ax.axhline(ref_ber, color='#555', linestyle=':', linewidth=0.8)
        ax.text(snr_db[0] + 0.5, ref_ber * 1.5, label,
                fontsize=7, color='#888')

    ax.set_xlabel("SNR [dB]")
    ax.set_ylabel("Bit Error Rate")
    ax.set_title(title)
    ax.set_ylim([1e-15, 1.0])
    ax.legend(loc='upper right')
    if show:
        plt.tight_layout()
        plt.show()
    return ax


# ─────────────────────────────────────────────────────────────────────────────
# Equalizer convergence
# ─────────────────────────────────────────────────────────────────────────────

def plot_equalizer_convergence(ber_trace: np.ndarray,
                                mse_trace: Optional[np.ndarray] = None,
                                tap_history: Optional[np.ndarray] = None,
                                title: str = "Equalizer Convergence",
                                fbaud: float = 56e9,
                                show: bool = True):
    """
    Multi-panel convergence plot: BER trace, MSE trace, tap evolution.
    """
    set_style()
    n_panels = 1 + (mse_trace is not None) + (tap_history is not None)
    fig, axes = plt.subplots(n_panels, 1, figsize=(8, 3*n_panels), sharex=False)
    if n_panels == 1:
        axes = [axes]

    n = np.arange(len(ber_trace))
    idx = 0

    # BER trace
    axes[idx].semilogy(n, np.maximum(ber_trace, 1e-12), color='#00ff88')
    axes[idx].axhline(2e-2, color='red', linestyle='--', linewidth=0.8,
                       label='KP4 threshold')
    axes[idx].set_ylabel("BER")
    axes[idx].set_title(title)
    axes[idx].legend()
    idx += 1

    # MSE trace
    if mse_trace is not None:
        axes[idx].semilogy(np.arange(len(mse_trace)),
                           np.maximum(mse_trace, 1e-12), color='#ff8844')
        axes[idx].set_ylabel("MSE")
        idx += 1

    # Tap weight evolution
    if tap_history is not None:
        # tap_history: (n_snapshots, n_taps)
        for k in range(tap_history.shape[1]):
            axes[idx].plot(tap_history[:, k], linewidth=0.8, alpha=0.7)
        axes[idx].set_ylabel("Tap weights")
        axes[idx].set_xlabel("Adaptation iteration")

    plt.tight_layout()
    if show:
        plt.show()
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Jitter histogram with Q-function bathtub extrapolation
# ─────────────────────────────────────────────────────────────────────────────

def plot_jitter_histogram(phase_errors: np.ndarray,
                           title: str = "CDR Phase / Jitter Histogram",
                           fbaud: float = 56e9,
                           ax: Optional[plt.Axes] = None,
                           show: bool = True) -> plt.Axes:
    """
    Plot jitter histogram with Gaussian fit and key metrics.
    """
    from scipy.stats import norm
    set_style()
    if ax is None:
        fig, ax = plt.subplots(figsize=(7, 4))

    # Histogram
    counts, bins, _ = ax.hist(phase_errors, bins=100, density=True,
                               color='#0088ff', alpha=0.7, label='Measured')
    # Gaussian fit
    mu, sigma = norm.fit(phase_errors)
    x_fit = np.linspace(bins[0], bins[-1], 300)
    ax.plot(x_fit, norm.pdf(x_fit, mu, sigma), 'r--',
            linewidth=1.5, label=f'Gaussian fit σ={sigma*1e12:.2f} ps')

    # Metrics
    pk_pk = np.ptp(phase_errors)
    ax.axvline(mu + 6*sigma, color='yellow', linestyle=':', linewidth=0.8,
               label=f'±6σ = {12*sigma*1e12:.1f} ps pk-pk (BER~1e-9)')

    ax.set_xlabel("Phase error [s]")
    ax.set_ylabel("Probability density")
    ax.set_title(f"{title}\nRJ rms = {sigma*1e12:.2f} ps, pk-pk = {pk_pk*1e12:.1f} ps")
    ax.legend()
    if show:
        plt.tight_layout()
        plt.show()
    return ax


# ─────────────────────────────────────────────────────────────────────────────
# Channel frequency response
# ─────────────────────────────────────────────────────────────────────────────

def plot_channel_response(freq: np.ndarray, H: np.ndarray,
                           fbaud: float = 56e9,
                           title: str = "Channel Transfer Function",
                           show: bool = True):
    """Plot insertion loss and group delay of channel H(f)."""
    set_style()
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 6), sharex=True)

    IL = 20 * np.log10(np.abs(H) + 1e-15)
    phase = np.unwrap(np.angle(H))
    gd_ns = -np.gradient(phase, freq) / (2 * np.pi) * 1e9

    ax1.plot(freq/1e9, IL, color='#00ff88', linewidth=1.5)
    ax1.axvline(fbaud/2e9, color='red', linestyle='--', linewidth=0.8,
                label=f'Nyquist = {fbaud/2e9:.0f} GHz')
    ax1.set_ylabel("Insertion Loss [dB]")
    ax1.set_title(title)
    ax1.legend()

    ax2.plot(freq/1e9, gd_ns, color='#ff8844', linewidth=1.5)
    ax2.set_ylabel("Group Delay [ns]")
    ax2.set_xlabel("Frequency [GHz]")

    # Annotate loss at Nyquist
    il_nyq = np.interp(fbaud/2, freq, IL)
    ax1.annotate(f'IL @ Nyquist = {il_nyq:.1f} dB',
                 xy=(fbaud/2e9, il_nyq),
                 xytext=(fbaud/2e9 * 0.5, il_nyq + 3),
                 color='#ffcc00', fontsize=8,
                 arrowprops=dict(arrowstyle='->', color='#ffcc00'))

    plt.tight_layout()
    if show:
        plt.show()
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Bathtub curve (horizontal)
# ─────────────────────────────────────────────────────────────────────────────

def plot_bathtub(t_ui: np.ndarray, ber_hor: np.ndarray,
                 title: str = "Bathtub Curve",
                 show: bool = True) -> plt.Axes:
    """Plot horizontal bathtub curve with eye opening at target BER."""
    set_style()
    fig, ax = plt.subplots(figsize=(7, 4))
    valid = ber_hor > 0
    ax.semilogy(t_ui[valid], ber_hor[valid], color='#00aaff', linewidth=2)
    # Mark eye opening at KP4 threshold
    for target_ber, label, color in [(2e-2, 'KP4 (2×10⁻²)', 'red'),
                                      (1e-3, 'KR4 (1×10⁻³)', 'orange')]:
        # Find crossings
        above = ber_hor > target_ber
        crossings = np.where(np.diff(above.astype(int)))[0]
        if len(crossings) >= 2:
            t_left  = t_ui[crossings[0]]
            t_right = t_ui[crossings[-1]]
            eye_ui  = t_right - t_left
            ax.axhline(target_ber, color=color, linestyle='--', linewidth=0.8)
            ax.annotate(f'{label}\nEye = {eye_ui:.3f} UI',
                        xy=((t_left+t_right)/2, target_ber),
                        color=color, fontsize=8, ha='center')

    ax.set_xlabel("Sampling Phase [UI]")
    ax.set_ylabel("BER")
    ax.set_title(title)
    ax.set_xlim([-1, 1])
    plt.tight_layout()
    if show:
        plt.show()
    return ax


# ─────────────────────────────────────────────────────────────────────────────
# DFE tap waterfall
# ─────────────────────────────────────────────────────────────────────────────

def plot_tap_evolution(tap_history: np.ndarray,
                       label: str = "DFE",
                       show: bool = True):
    """
    Plot tap weight evolution over adaptation time.
    tap_history: (n_snapshots, n_taps) array
    """
    set_style()
    fig, ax = plt.subplots(figsize=(8, 4))
    cmap = plt.cm.rainbow
    n_taps = tap_history.shape[1]
    for k in range(n_taps):
        color = cmap(k / n_taps)
        ax.plot(tap_history[:, k], linewidth=1.2, color=color,
                label=f'Tap {k}' if n_taps <= 8 else None, alpha=0.8)
    ax.set_xlabel("Adaptation snapshot")
    ax.set_ylabel("Tap weight")
    ax.set_title(f"{label} Tap Weight Evolution")
    if n_taps <= 8:
        ax.legend(loc='upper right', fontsize=7)
    plt.tight_layout()
    if show:
        plt.show()
    return fig


if __name__ == "__main__":
    np.random.seed(3)
    # Quick demo: eye diagram from synthetic PAM-4 signal
    N = 50_000
    from pam4_chain import PAM4_LEVELS
    symbols = np.random.choice(PAM4_LEVELS, N)
    # Simple 3-tap channel
    h = np.array([0.1, 1.0, 0.25])
    rx = np.convolve(np.repeat(symbols, 8), h, mode='same')
    rx += np.random.normal(0, 0.12, len(rx))

    ax = plot_eye_diagram(rx, fbaud=56e9, osr=8,
                          title="PAM-4 Eye (3-tap ISI + noise)", show=False)
    plt.savefig('/tmp/eye_demo.png', dpi=120, bbox_inches='tight')
    print("Eye diagram saved to /tmp/eye_demo.png")

    # BER curve
    from channel import ber_from_snr_pam4
    snr = np.linspace(10, 25, 20)
    ber_th = ber_from_snr_pam4(snr)
    ax2 = plot_ber_curve(snr, ber_theory=ber_th,
                         title="PAM-4 Theoretical BER", show=False)
    plt.savefig('/tmp/ber_demo.png', dpi=120, bbox_inches='tight')
    print("BER curve saved to /tmp/ber_demo.png")
    print("visualization.py: self-test PASSED")
