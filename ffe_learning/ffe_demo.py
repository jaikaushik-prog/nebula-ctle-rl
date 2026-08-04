"""
FFE learning demo (Part A visualization).

Goal: SEE what an FFE does, four ways at once, matching the professor's
"Part 11 FFE" note (fig on page 12):

  (top-left)  Channel pulse response      -> the ISI problem (cursor + tails)
  (top-right) Frequency response          -> channel droops, FFE boosts, sum flat
  (bot-left)  Eye diagram WITHOUT FFE      -> closed by ISI
  (bot-right) Eye diagram WITH FFE         -> reopened

This is a self-contained teaching script (numpy + scipy + matplotlib only).
It does NOT touch the validated python_models/ code. Symbols are simple NRZ
(+/-1) so the picture is as clean as possible. Zero-forcing tap design is a
preview of Part A / Step 2.

Run:  python ffe_demo.py     (writes ffe_demo.png next to this file)
"""

import numpy as np
from scipy.signal import butter, lfilter
import matplotlib
matplotlib.use("Agg")           # write a PNG, no display needed
import matplotlib.pyplot as plt

# ----------------------------------------------------------------------
# 0. Setup
# ----------------------------------------------------------------------
SPS   = 32          # samples per symbol (oversampling of the waveform)
NSYM  = 4000        # number of symbols to simulate
FBAUD = 1.0         # normalized symbol rate (1 symbol per UI)
rng   = np.random.default_rng(0)

# ----------------------------------------------------------------------
# 1. Channel = a lossy low-pass filter (this is what CREATES the ISI)
#    A real PCB/package trace rolls off at high frequency; a Butterworth
#    low-pass is a clean stand-in. Cutoff below Nyquist => real ISI.
# ----------------------------------------------------------------------
fc_over_fbaud = 0.40                       # channel -3 dB point, in units of fbaud
Wn = fc_over_fbaud / (SPS / 2.0)           # normalized to the sample-rate Nyquist
b_ch, a_ch = butter(N=4, Wn=Wn, btype="low")  # moderate roll-off -> clear ISI

def channel(x):
    return lfilter(b_ch, a_ch, x)

# ----------------------------------------------------------------------
# 2. Measure the SYMBOL-SPACED pulse response p[k]
#    Send one isolated symbol, look at the far end, sample once per UI.
#    p[cursor] is the main sample; the rest are pre/post-cursor ISI.
# ----------------------------------------------------------------------
def symbol_pulse_response(n_taps_span=9):
    imp = np.zeros(NSYM)
    imp[NSYM // 2] = 1.0
    wf  = channel(np.repeat(imp, SPS))     # ZOH one symbol, push through channel
    peak = int(np.argmax(wf))              # cursor sampling instant
    ks = np.arange(-(n_taps_span // 2), n_taps_span // 2 + 1)
    p = np.array([wf[peak + k * SPS] for k in ks])
    return p, ks, peak % SPS               # p, its indices, sub-UI sampling phase

p, p_idx, samp_phase = symbol_pulse_response()
cursor_i = int(np.argmax(p))
print("Symbol-spaced pulse response p[k]:")
for k, v in zip(p_idx, p):
    tag = " <- cursor" if (k == p_idx[cursor_i]) else (" (pre)" if k < 0 else " (post)")
    print("  k=%+d : %+.4f%s" % (k, v, tag))

# ----------------------------------------------------------------------
# 3. Design a ZERO-FORCING FFE from the pulse response  (preview of Step 2)
#    Pick N taps, force the equalized pulse to be [.. 0 0 1 0 0 ..]:
#    solve a small Toeplitz system  A @ w = target.
# ----------------------------------------------------------------------
def design_zf_ffe(p, n_taps=7, n_pre=3):
    # Build A so that (A @ w)[i] = equalized pulse at symbol i, for n_taps points.
    A = np.zeros((n_taps, n_taps))
    pc = int(np.argmax(p))                 # cursor index inside p
    for i in range(n_taps):                # i = output symbol index
        for j in range(n_taps):            # j = tap index
            pk = pc + (i - n_pre) - (j - n_pre)
            if 0 <= pk < len(p):
                A[i, j] = p[pk]
    target = np.zeros(n_taps)
    target[n_pre] = 1.0                    # force cursor = 1, neighbors = 0
    w = np.linalg.solve(A, target)
    return w, n_pre

N_TAPS, N_PRE = 7, 3
w, n_pre = design_zf_ffe(p, N_TAPS, N_PRE)
print("\nZero-forcing FFE taps (n_taps=%d, n_pre=%d):" % (N_TAPS, n_pre))
print("  " + "  ".join("%+.3f" % t for t in w))
print("  main tap = %+.3f, sum|other taps| = %.3f" %
      (w[n_pre], np.sum(np.abs(w[np.arange(N_TAPS) != n_pre]))))

# Apply the (symbol-spaced) FFE to an oversampled waveform:
# place taps SPS samples apart, then convolve.
def apply_ffe(wf, w):
    kernel = np.zeros((len(w) - 1) * SPS + 1)
    kernel[np.arange(len(w)) * SPS] = w
    return np.convolve(wf, kernel, mode="full")

# ----------------------------------------------------------------------
# 4. Run a real symbol stream through channel, with and without FFE
# ----------------------------------------------------------------------
sym    = rng.choice([-1.0, 1.0], size=NSYM)
tx     = np.repeat(sym, SPS)               # NRZ waveform
rx     = channel(tx)                       # after channel  (ISI -> eye closes)
rx_eq  = apply_ffe(rx, w)                  # after FFE       (ISI cancelled)

# sampling phase for each (so the eye opening sits centered)
_, _, ph_rx  = symbol_pulse_response()
ph_eq = (ph_rx + n_pre * SPS) % SPS        # FFE adds n_pre UI of delay

def eye_segments(wf, phase, n_eye=400, start_sym=200):
    """Fold the waveform into 2-UI windows for an eye diagram."""
    segs = []
    base = start_sym * SPS + phase
    for i in range(n_eye):
        s = base + i * SPS - SPS // 2
        if s + 2 * SPS < len(wf):
            segs.append(wf[s:s + 2 * SPS])
    return np.array(segs)

eye_rx = eye_segments(rx,    ph_rx)
eye_eq = eye_segments(rx_eq, ph_eq)

# ----------------------------------------------------------------------
# 5. Frequency responses:  channel, FFE, and the two combined
# ----------------------------------------------------------------------
f = np.linspace(0, 1.5 * FBAUD, 800)       # in units of fbaud (Nyquist = 0.5)
# channel magnitude from its impulse response
imp = np.zeros(2048); imp[0] = 1.0
h_ch = channel(imp)
w_rad = 2 * np.pi * f / SPS                 # digital freq per sample
H_ch = np.array([np.sum(h_ch * np.exp(-1j * wr * np.arange(len(h_ch)))) for wr in w_rad])
# FFE magnitude:  H(f) = sum_k w[k] exp(-j 2pi f k Tb)
H_ffe = np.array([np.sum(w * np.exp(-1j * 2 * np.pi * fi * np.arange(len(w)))) for fi in f])
H_tot = H_ch * H_ffe

def db(x):
    return 20 * np.log10(np.abs(x) + 1e-12)

# ----------------------------------------------------------------------
# 6. Plot everything
# ----------------------------------------------------------------------
fig, ax = plt.subplots(2, 2, figsize=(13, 9))
fig.suptitle("How an FFE works  (channel makes ISI  ->  FFE cancels it)", fontsize=14, weight="bold")

# (0,0) pulse response
mk = ax[0, 0].stem(p_idx, p, basefmt=" ")
ax[0, 0].axhline(0, color="k", lw=0.6)
ax[0, 0].set_title("1. Channel pulse response  p[k]  (the ISI)")
ax[0, 0].set_xlabel("symbol offset k (UI)"); ax[0, 0].set_ylabel("amplitude")
ax[0, 0].annotate("cursor", (p_idx[cursor_i], p[cursor_i]),
                  textcoords="offset points", xytext=(6, -2))
ax[0, 0].grid(alpha=0.3)

# (0,1) frequency response
ax[0, 1].plot(f, db(H_ch),  label="channel (low-pass, droops)", color="tab:blue")
ax[0, 1].plot(f, db(H_ffe), label="FFE (boosts highs)",         color="tab:green")
ax[0, 1].plot(f, db(H_tot), label="combined (flatter)",         color="tab:purple", lw=2)
ax[0, 1].set_ylim(-30, 15)
ax[0, 1].axvline(0.5, color="red", ls="--", lw=1)
ax[0, 1].text(0.52, 11, "Nyquist", color="red", fontsize=9)
ax[0, 1].set_title("2. Frequency response")
ax[0, 1].set_xlabel("frequency (x fbaud)"); ax[0, 1].set_ylabel("magnitude (dB)")
ax[0, 1].legend(fontsize=8); ax[0, 1].grid(alpha=0.3)

# (1,0) eye without FFE
t_eye = (np.arange(2 * SPS) / SPS) - 0.5
for seg in eye_rx:
    ax[1, 0].plot(t_eye, seg, color="tab:red", alpha=0.05, lw=0.6)
ax[1, 0].set_title("3. Eye WITHOUT FFE  (closed by ISI)")
ax[1, 0].set_xlabel("time (UI)"); ax[1, 0].set_ylabel("amplitude")
ax[1, 0].grid(alpha=0.3)

# (1,1) eye with FFE
for seg in eye_eq:
    ax[1, 1].plot(t_eye, seg, color="tab:green", alpha=0.05, lw=0.6)
ax[1, 1].set_title("4. Eye WITH FFE  (reopened)")
ax[1, 1].set_xlabel("time (UI)"); ax[1, 1].set_ylabel("amplitude")
ax[1, 1].grid(alpha=0.3)

plt.tight_layout(rect=[0, 0, 1, 0.97])
out = __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0] + "/ffe_demo.png"
plt.savefig(out, dpi=110)
print("\nSaved figure -> ffe_demo.png")
