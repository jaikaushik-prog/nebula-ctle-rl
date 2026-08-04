"""
optical_dsp.py — DSP algorithms for optical communication receivers.

Covers:
  - Chromatic dispersion (CD) compensation (frequency-domain equaliser)
  - Polarisation mode dispersion (PMD) compensation (2×2 MIMO)
  - Laser phase noise model and Viterbi-Viterbi carrier phase recovery
  - Frequency offset estimation and correction
  - Coherent receiver front-end model (90° hybrid + balanced PD)
  - IM-DD DSP chain
  - Constant modulus algorithm (CMA) for blind equalisation
"""

import numpy as np
from typing import Tuple, Optional
from scipy import signal as sp_signal


# ─────────────────────────────────────────────────────────────────────────────
# Physical constants
# ─────────────────────────────────────────────────────────────────────────────

C_M_S       = 2.998e8    # speed of light [m/s]
LAMBDA_1550 = 1550e-9    # wavelength [m]
LAMBDA_1310 = 1310e-9
D_SMF28     = 17.0       # CD coefficient SMF-28 @ 1550 nm [ps/nm/km]


# ─────────────────────────────────────────────────────────────────────────────
# Chromatic dispersion compensation
# ─────────────────────────────────────────────────────────────────────────────

def cd_transfer_function(freq: np.ndarray, D: float, L_km: float,
                          wavelength_m: float = LAMBDA_1550) -> np.ndarray:
    """
    Chromatic dispersion transfer function H_CD(f).

    H_CD(f) = exp(j · π · λ² · D · L · f² / c)

    D          : dispersion coefficient [ps/nm/km]
    L_km       : fibre length [km]
    wavelength_m: carrier wavelength [m]

    Returns complex transfer function (phase only, |H|=1).
    """
    D_si = D * 1e-6        # convert ps/nm/km → s/m²
    L_m  = L_km * 1e3
    beta2 = -wavelength_m**2 * D_si / (2 * np.pi * C_M_S)   # [s²/m]
    phi = -np.pi * beta2 * L_m * (2 * np.pi * freq)**2
    return np.exp(1j * phi)


def cd_compensate_freq_domain(signal_iq: np.ndarray,
                               f_s: float,
                               D: float,
                               L_km: float,
                               wavelength_m: float = LAMBDA_1550,
                               block_size: int = 1024,
                               overlap: int = 128) -> np.ndarray:
    """
    Overlap-save frequency-domain CD equaliser.

    signal_iq : complex baseband signal (I + jQ)
    f_s       : sample rate [Hz]
    D         : residual dispersion [ps/nm/km]
    L_km      : equivalent fibre length [km]
    block_size: FFT block length
    overlap   : overlap length (must cover CD impulse response length)

    Returns CD-compensated complex signal.
    """
    N = len(signal_iq)
    out = np.zeros(N, dtype=complex)
    # Pre-compute H_CD for this block size
    freq = np.fft.fftfreq(block_size, d=1.0/f_s)
    H_inv = np.conj(cd_transfer_function(freq, D, L_km, wavelength_m))

    step = block_size - overlap
    for start in range(0, N, step):
        end = min(start + block_size, N)
        block = signal_iq[start:end]
        if len(block) < block_size:
            block = np.pad(block, (0, block_size - len(block)))
        B = np.fft.fft(block)
        B_eq = B * H_inv
        b_eq = np.fft.ifft(B_eq)
        # Save non-overlapping output
        out_start = start + overlap
        out_end   = min(out_start + step, N)
        b_start   = overlap
        b_end     = b_start + (out_end - out_start)
        out[out_start:out_end] = b_eq[b_start:b_end]

    return out


def cd_tap_count(D: float, L_km: float, fbaud: float,
                  wavelength_m: float = LAMBDA_1550) -> int:
    """
    Estimate number of time-domain taps required to compensate CD.
    Based on CD-induced pulse spreading: Δτ = D·L·Δλ where Δλ ≈ λ²·fbaud/c.
    """
    D_si = D * 1e-6
    L_m  = L_km * 1e3
    delta_tau = abs(D_si * L_m * wavelength_m**2 * fbaud / C_M_S)
    n_taps = int(np.ceil(delta_tau * fbaud)) + 1
    return n_taps


# ─────────────────────────────────────────────────────────────────────────────
# Laser phase noise model
# ─────────────────────────────────────────────────────────────────────────────

def laser_phase_noise(n_samples: int, linewidth_hz: float,
                       f_s: float) -> np.ndarray:
    """
    Generate laser phase noise trajectory (Wiener process / Brownian motion).

    Phase noise variance per sample: σ²_Δφ = 2π · Δν / f_s
    where Δν is the laser linewidth (half FWHM of Lorentzian spectrum).

    Returns phase noise array [radians].
    """
    sigma_phi = np.sqrt(2 * np.pi * linewidth_hz / f_s)
    phase_increments = np.random.normal(0, sigma_phi, n_samples)
    return np.cumsum(phase_increments)


def apply_phase_noise(signal_iq: np.ndarray, linewidth_hz: float,
                       f_s: float) -> np.ndarray:
    """Apply combined TX + LO laser phase noise to coherent signal."""
    phase = laser_phase_noise(len(signal_iq), linewidth_hz * 2, f_s)  # ×2 for TX+LO
    return signal_iq * np.exp(1j * phase)


# ─────────────────────────────────────────────────────────────────────────────
# Frequency offset estimation and correction
# ─────────────────────────────────────────────────────────────────────────────

def estimate_frequency_offset(signal_iq: np.ndarray,
                                f_s: float,
                                modulation: str = 'QPSK') -> float:
    """
    Frequency offset estimator using 4th-power method (for QPSK/16-QAM).

    Raises signal to Mth power to remove modulation, then finds peak frequency.
    Returns estimated frequency offset [Hz].
    """
    M = 4 if 'QAM' in modulation or modulation == 'QPSK' else 2
    z = signal_iq ** M
    Z = np.fft.fft(z)
    freqs = np.fft.fftfreq(len(z), d=1.0/f_s)
    fo_idx = np.argmax(np.abs(Z))
    return freqs[fo_idx] / M


def correct_frequency_offset(signal_iq: np.ndarray,
                               f_s: float, freq_offset_hz: float) -> np.ndarray:
    """Multiply by complex exponential to remove frequency offset."""
    t = np.arange(len(signal_iq)) / f_s
    return signal_iq * np.exp(-1j * 2 * np.pi * freq_offset_hz * t)


# ─────────────────────────────────────────────────────────────────────────────
# Carrier phase recovery: Viterbi-Viterbi (QPSK / 16-QAM)
# ─────────────────────────────────────────────────────────────────────────────

def viterbi_viterbi_phase_recovery(signal_iq: np.ndarray,
                                    window: int = 32,
                                    modulation_order: int = 4) -> np.ndarray:
    """
    Viterbi-Viterbi (V-V) carrier phase estimator.

    Raises signal to Mth power, estimates phase in a sliding window,
    then divides by M to recover the carrier phase.

    modulation_order : M (4 for QPSK, 4 for 16-QAM with partitioning)
    window           : averaging window length (longer → less noise, more latency)

    Returns phase-corrected signal.
    """
    M = modulation_order
    z = signal_iq ** M
    N = len(signal_iq)
    phase_est = np.zeros(N)

    # Sliding window average
    for n in range(N):
        start = max(0, n - window//2)
        stop  = min(N, n + window//2)
        avg   = np.mean(z[start:stop])
        phase_est[n] = np.angle(avg) / M

    # Phase unwrapping to handle cycle slips
    phase_unwrapped = np.unwrap(phase_est * M) / M
    return signal_iq * np.exp(-1j * phase_unwrapped)


# ─────────────────────────────────────────────────────────────────────────────
# 2×2 MIMO butterfly equaliser for PMD compensation
# ─────────────────────────────────────────────────────────────────────────────

class MIMOButterfly:
    """
    2×2 MIMO FIR butterfly equaliser for polarisation demultiplexing and PMD.

    Structure (Jones matrix equaliser):
        [Hxx  Hxy] * [Ex]   = [Ex_out]
        [Hyx  Hyy]   [Ey]     [Ey_out]

    Adaptation: Constant Modulus Algorithm (CMA) for blind start-up,
                then LMS for tracking (can switch after convergence).

    n_taps : length of each 1D FIR filter (complex-valued)
    """
    def __init__(self, n_taps: int = 13,
                 mu_cma: float = 1e-4, mu_lms: float = 5e-5,
                 r_cma: float = 1.0):
        self.n_taps = n_taps
        self.mu_cma = mu_cma
        self.mu_lms = mu_lms
        self.r_cma  = r_cma   # CMA radius (= RMS signal amplitude)
        # Initialise butterfly coefficients: identity start
        self.Hxx = np.zeros(n_taps, dtype=complex); self.Hxx[n_taps//2] = 1.0
        self.Hxy = np.zeros(n_taps, dtype=complex)
        self.Hyx = np.zeros(n_taps, dtype=complex)
        self.Hyy = np.zeros(n_taps, dtype=complex); self.Hyy[n_taps//2] = 1.0

    def process_cma(self, ex: np.ndarray, ey: np.ndarray
                    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Process X and Y polarisation streams with CMA adaptation.
        Returns (ex_out, ey_out).
        """
        N = len(ex)
        ex_out = np.zeros(N, dtype=complex)
        ey_out = np.zeros(N, dtype=complex)
        bx = np.zeros(self.n_taps, dtype=complex)
        by = np.zeros(self.n_taps, dtype=complex)

        for n in range(N):
            bx = np.roll(bx, 1); bx[0] = ex[n]
            by = np.roll(by, 1); by[0] = ey[n]

            # Butterfly outputs
            ox = np.dot(self.Hxx, bx) + np.dot(self.Hxy, by)
            oy = np.dot(self.Hyx, bx) + np.dot(self.Hyy, by)
            ex_out[n] = ox
            ey_out[n] = oy

            # CMA error: drives |output|² → r_cma²
            ex_cma = ox * (self.r_cma**2 - np.abs(ox)**2)
            ey_cma = oy * (self.r_cma**2 - np.abs(oy)**2)

            # Gradient update (Wirtinger derivative)
            self.Hxx += self.mu_cma * ex_cma * np.conj(bx)
            self.Hxy += self.mu_cma * ex_cma * np.conj(by)
            self.Hyx += self.mu_cma * ey_cma * np.conj(bx)
            self.Hyy += self.mu_cma * ey_cma * np.conj(by)

        return ex_out, ey_out

    def jones_matrix(self) -> np.ndarray:
        """Return 2×2 Jones matrix evaluated at f=0 (DC)."""
        return np.array([[self.Hxx[self.n_taps//2], self.Hxy[self.n_taps//2]],
                         [self.Hyx[self.n_taps//2], self.Hyy[self.n_taps//2]]])


# ─────────────────────────────────────────────────────────────────────────────
# Coherent receiver front-end model
# ─────────────────────────────────────────────────────────────────────────────

def coherent_90deg_hybrid(E_sig: np.ndarray, E_lo: np.ndarray
                           ) -> Tuple[np.ndarray, np.ndarray,
                                      np.ndarray, np.ndarray]:
    """
    Ideal 90° optical hybrid: mixes signal with LO to produce I/Q.

    Outputs:
        I+ = (E_sig + E_lo) / √2
        I- = (E_sig - E_lo) / √2
        Q+ = (E_sig + j·E_lo) / √2
        Q- = (E_sig - j·E_lo) / √2

    Balanced detection: I = |I+|² - |I-|², Q = |Q+|² - |Q-|²
    """
    sqrt2 = np.sqrt(2)
    Ip = (E_sig + E_lo)       / sqrt2
    Im = (E_sig - E_lo)       / sqrt2
    Qp = (E_sig + 1j * E_lo)  / sqrt2
    Qm = (E_sig - 1j * E_lo)  / sqrt2
    return Ip, Im, Qp, Qm


def balanced_detection(Ip, Im, Qp, Qm, responsivity: float = 0.8
                        ) -> Tuple[np.ndarray, np.ndarray]:
    """
    Balanced photodetection → I and Q photocurrents.
    responsivity : PD responsivity [A/W]
    """
    I = responsivity * (np.abs(Ip)**2 - np.abs(Im)**2)
    Q = responsivity * (np.abs(Qp)**2 - np.abs(Qm)**2)
    return I, Q


# ─────────────────────────────────────────────────────────────────────────────
# Complete coherent DSP chain
# ─────────────────────────────────────────────────────────────────────────────

class CoherentDSP:
    """
    Complete coherent optical DSP pipeline:
        1. CD compensation (frequency domain)
        2. PMD equalisation (CMA 2×2 MIMO)
        3. Frequency offset estimation and correction
        4. Carrier phase recovery (Viterbi-Viterbi)
        5. Symbol decision

    Supports dual-polarisation QPSK and 16-QAM.
    """
    def __init__(self,
                 f_s: float = 64e9,
                 fbaud: float = 32e9,
                 D_ps_nm_km: float = 17.0,
                 L_km: float = 80.0,
                 linewidth_hz: float = 100e3,
                 n_mimo_taps: int = 13,
                 vv_window: int = 32):
        self.f_s         = f_s
        self.fbaud       = fbaud
        self.D           = D_ps_nm_km
        self.L_km        = L_km
        self.linewidth   = linewidth_hz
        self.mimo        = MIMOButterfly(n_taps=n_mimo_taps)
        self.vv_window   = vv_window
        # CD tap count estimate
        n_cd = cd_tap_count(D_ps_nm_km, L_km, fbaud)
        print(f"[CoherentDSP] CD requires ~{n_cd} taps | "
              f"Using FFT block size 1024 overlap 128")

    def process(self, rx_x: np.ndarray, rx_y: np.ndarray,
                apply_cd: bool = True,
                apply_pmd: bool = True,
                apply_phase: bool = True
                ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Process dual-polarisation received signal.

        rx_x, rx_y : complex baseband X and Y polarisation samples
        Returns (eq_x, eq_y) equalised, phase-recovered complex signals.
        """
        # 1. CD compensation
        if apply_cd:
            rx_x = cd_compensate_freq_domain(rx_x, self.f_s, self.D, self.L_km)
            rx_y = cd_compensate_freq_domain(rx_y, self.f_s, self.D, self.L_km)

        # 2. PMD equalisation (CMA)
        if apply_pmd:
            rx_x, rx_y = self.mimo.process_cma(rx_x, rx_y)

        # 3. Frequency offset correction
        fo = estimate_frequency_offset(rx_x, self.f_s)
        rx_x = correct_frequency_offset(rx_x, self.f_s, fo)
        rx_y = correct_frequency_offset(rx_y, self.f_s, fo)

        # 4. Carrier phase recovery
        if apply_phase:
            rx_x = viterbi_viterbi_phase_recovery(rx_x, window=self.vv_window)
            rx_y = viterbi_viterbi_phase_recovery(rx_y, window=self.vv_window)

        return rx_x, rx_y


# ─────────────────────────────────────────────────────────────────────────────
# IM-DD optical link model (for short-reach, silicon photonics)
# ─────────────────────────────────────────────────────────────────────────────

class IMDDLink:
    """
    IM-DD optical link: laser → modulator → fibre → PD → TIA.

    Includes:
    - Laser relative intensity noise (RIN)
    - Extinction ratio penalty
    - Shot noise
    - Thermal noise (TIA)
    - Optional CD (for longer reach)
    """
    def __init__(self,
                 er_db: float = 6.0,           # extinction ratio [dB]
                 rin_db_hz: float = -155.0,     # RIN [dB/Hz]
                 p_avg_dbm: float = -3.0,       # avg optical power [dBm]
                 responsivity: float = 0.8,     # PD responsivity [A/W]
                 tia_noise_a_rthz: float = 15e-12,  # TIA noise [A/√Hz]
                 bw_pd_hz: float = 35e9,        # PD bandwidth [Hz]
                 bw_tia_hz: float = 35e9,       # TIA bandwidth [Hz]
                 D_ps_nm_km: float = 0.0,       # CD for optional reach
                 L_km: float = 0.0):
        self.er_lin         = 10 ** (er_db / 10.0)
        self.rin_lin        = 10 ** (rin_db_hz / 10.0)
        self.p_avg          = 1e-3 * 10 ** (p_avg_dbm / 10.0)   # W
        self.responsivity   = responsivity
        self.tia_noise      = tia_noise_a_rthz
        self.bw_pd          = bw_pd_hz
        self.bw_tia         = bw_tia_hz
        self.D              = D_ps_nm_km
        self.L_km           = L_km

    def transmit(self, symbols: np.ndarray, f_s: float) -> np.ndarray:
        """
        Convert normalised symbols (∈ {-3,-1,+1,+3}) to optical intensity.
        Returns photocurrent [A].
        """
        # Map PAM-4 to optical power levels (with extinction ratio)
        # Min power: p_0 = p_avg * 2/(1 + er_lin) × 1; Max: p_avg * 2*er_lin/(1+er_lin)
        p0 = 2 * self.p_avg / (1 + self.er_lin)      # min power (level -3)
        p3 = 2 * self.p_avg * self.er_lin / (1 + self.er_lin)  # max power
        # Map symbols ∈ {-3,-1,1,3} → power levels linearly
        p = p0 + (symbols + 3.0) / 6.0 * (p3 - p0)

        # RIN noise
        rin_noise = np.sqrt(self.rin_lin * self.bw_pd) * p
        p_noisy = p + rin_noise * np.random.normal(0, 1, len(p))
        p_noisy = np.maximum(p_noisy, 0)

        # Photodetection: photocurrent
        I_pd = self.responsivity * p_noisy

        # Shot noise: σ² = 2q·I·BW  [A²]
        q = 1.602e-19
        shot_rms = np.sqrt(2 * q * np.abs(I_pd) * self.bw_pd)
        I_pd += shot_rms * np.random.normal(0, 1, len(I_pd))

        # TIA thermal noise
        tia_rms = self.tia_noise * np.sqrt(self.bw_tia)
        I_pd += np.random.normal(0, tia_rms, len(I_pd))

        return I_pd

    def snr_db(self, fbaud: float) -> float:
        """Estimate link SNR at baud-rate (simplified, linear regime)."""
        i_signal = self.responsivity * self.p_avg  # average photocurrent
        # Signal power: PAM-4 level spread
        p0 = 2 * self.p_avg / (1 + self.er_lin)
        p3 = 2 * self.p_avg * self.er_lin / (1 + self.er_lin)
        p_eye = (p3 - p0) / 3.0 / 2.0   # half eye opening amplitude
        I_eye = self.responsivity * p_eye
        # Noise RMS
        q = 1.602e-19
        shot_rms = np.sqrt(2 * q * self.responsivity * self.p_avg * fbaud)
        rin_rms  = np.sqrt(self.rin_lin * fbaud) * self.responsivity * self.p_avg
        tia_rms  = self.tia_noise * np.sqrt(fbaud)
        noise_total = np.sqrt(shot_rms**2 + rin_rms**2 + tia_rms**2)
        return 20 * np.log10(I_eye / (noise_total + 1e-30))


if __name__ == "__main__":
    np.random.seed(5)
    # Test CD compensation
    f_s = 64e9
    N = 4096
    t = np.arange(N) / f_s
    sig = np.exp(1j * 2 * np.pi * 2e9 * t)  # test tone at 2 GHz
    # Apply CD
    freq = np.fft.fftfreq(N, d=1.0/f_s)
    H_cd = cd_transfer_function(freq, D=17.0, L_km=80.0)
    sig_cd = np.fft.ifft(np.fft.fft(sig) * H_cd)
    # Compensate
    sig_comp = cd_compensate_freq_domain(sig_cd, f_s, D=17.0, L_km=80.0)
    phase_err = np.std(np.angle(sig_comp[128:] * np.conj(sig[128:])))
    print(f"CD comp phase residual (rms): {np.degrees(phase_err):.2f}°")

    # Test IM-DD link SNR
    link = IMDDLink(er_db=6.0, p_avg_dbm=-3.0)
    snr = link.snr_db(fbaud=56e9)
    print(f"IM-DD link SNR at 56 Gbaud: {snr:.1f} dB")

    # Test coherent DSP pipeline
    dsp = CoherentDSP(f_s=64e9, fbaud=32e9, D_ps_nm_km=17.0, L_km=80.0)
    N_coh = 8192
    tx_x = np.exp(1j * np.random.choice([0, np.pi/2, np.pi, 3*np.pi/2], N_coh))
    tx_y = np.exp(1j * np.random.choice([0, np.pi/2, np.pi, 3*np.pi/2], N_coh))
    # Add phase noise
    tx_x_pn = apply_phase_noise(tx_x, linewidth_hz=500e3, f_s=64e9)
    tx_y_pn = apply_phase_noise(tx_y, linewidth_hz=500e3, f_s=64e9)
    rx_x, rx_y = dsp.process(tx_x_pn, tx_y_pn)
    print(f"Coherent DSP: output signal rms = {np.std(np.abs(rx_x)):.3f}")
    print("optical_dsp.py: self-test PASSED")
