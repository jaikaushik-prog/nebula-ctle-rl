"""
pam4_chain.py — PAM-4 TX signal chain
PRBS generator, Gray coding, PAM-4 encoding, scrambler, TX FFE/pre-emphasis.
"""

import numpy as np
from typing import Optional, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# PRBS Generator
# ─────────────────────────────────────────────────────────────────────────────

PRBS_POLYNOMIALS = {
    7:  [7, 6],
    9:  [9, 5],
    11: [11, 9],
    13: [13, 12, 11, 8],
    15: [15, 14],
    23: [23, 18],
    31: [31, 28],
    58: [58, 39],  # IEEE 802.3ck
}

class PRBSGenerator:
    """
    Linear feedback shift register PRBS generator.
    Matches IEEE 802.3 specifications for SerDes PRBS patterns.
    """
    def __init__(self, order: int = 31, seed: int = 1):
        assert order in PRBS_POLYNOMIALS, f"Unsupported PRBS order {order}"
        self.order = order
        self.taps = PRBS_POLYNOMIALS[order]
        self.state = seed & ((1 << order) - 1)
        if self.state == 0:
            self.state = 1

    def next_bit(self) -> int:
        fb = 0
        for tap in self.taps:
            fb ^= (self.state >> (tap - 1)) & 1
        self.state = ((self.state << 1) | fb) & ((1 << self.order) - 1)
        return fb

    def generate(self, n_bits: int) -> np.ndarray:
        return np.array([self.next_bit() for _ in range(n_bits)], dtype=np.int8)

    def generate_fast(self, n_bits: int) -> np.ndarray:
        """Vectorised generation — ~30× faster than loop for long sequences."""
        bits = np.zeros(n_bits, dtype=np.int8)
        state = np.zeros(self.order, dtype=np.int8)
        # Initialise state from self.state integer
        for i in range(self.order):
            state[i] = (self.state >> i) & 1
        tap_indices = [t - 1 for t in self.taps]
        for n in range(n_bits):
            fb = int(np.bitwise_xor.reduce(state[tap_indices]))
            bits[n] = fb
            state = np.roll(state, 1)
            state[0] = fb
        return bits


# ─────────────────────────────────────────────────────────────────────────────
# Scrambler / Descrambler (self-synchronising, x^58 + x^39 + 1, IEEE 802.3ck)
# ─────────────────────────────────────────────────────────────────────────────

class Scrambler:
    """
    Self-synchronising scrambler.
    Polynomial: x^58 + x^39 + 1  (IEEE 802.3ck, 100GBASE-KR4)
    """
    def __init__(self, poly: Tuple[int,...] = (58, 39), seed: int = 0x1):
        self.poly = poly  # (58, 39) → taps at bit 58 and 39
        self.state = seed & ((1 << poly[0]) - 1)
        self._mask = (1 << poly[0]) - 1

    def _scramble_bit(self, b_in: int) -> int:
        fb = ((self.state >> (self.poly[0] - 1)) ^
              (self.state >> (self.poly[1] - 1))) & 1
        b_out = b_in ^ fb
        # Multiplicative (self-synchronising) scrambler: the OUTPUT bit is
        # shifted into the register. An earlier revision shifted in the input
        # (plaintext) bit, which broke the scramble→descramble roundtrip and
        # the self-synchronisation property.
        self.state = ((self.state << 1) | b_out) & self._mask
        return b_out

    def scramble(self, bits: np.ndarray) -> np.ndarray:
        return np.array([self._scramble_bit(int(b)) for b in bits], dtype=np.int8)

    def descramble(self, bits: np.ndarray) -> np.ndarray:
        """For self-synchronising scrambler, descrambling uses the same XOR."""
        out = np.zeros_like(bits)
        for i, b in enumerate(bits):
            fb = ((self.state >> (self.poly[0] - 1)) ^
                  (self.state >> (self.poly[1] - 1))) & 1
            self.state = ((self.state << 1) | int(b)) & self._mask
            out[i] = int(b) ^ fb
        return out


# ─────────────────────────────────────────────────────────────────────────────
# Gray coding
# ─────────────────────────────────────────────────────────────────────────────

# IEEE 802.3 Gray map: 2-bit dibits → PAM-4 levels {-3,-1,+1,+3}
# Dibit:   00   01   11   10
# Level:   -3   -1   +3   +1   (IEEE standard Gray map)
_GRAY_ENC = {(0,0): -3, (0,1): -1, (1,1): +1, (1,0): +3}
_GRAY_DEC = {v: k for k, v in _GRAY_ENC.items()}

def gray_encode(bits: np.ndarray) -> np.ndarray:
    """
    Convert bit stream to PAM-4 symbol stream using Gray coding.
    Input:  bit array of length 2N  (MSB, LSB pairs)
    Output: symbol array of length N with values in {-3,-1,+1,+3}
    """
    assert len(bits) % 2 == 0, "Bit count must be even for PAM-4"
    bits = bits.reshape(-1, 2)
    symbols = np.array([_GRAY_ENC[(int(b[0]), int(b[1]))] for b in bits])
    return symbols

def gray_decode(symbols: np.ndarray) -> np.ndarray:
    """
    Convert PAM-4 symbol stream back to bit stream.
    Input:  symbol array with values in {-3,-1,+1,+3}
    Output: bit array of length 2N
    """
    bits = []
    for s in symbols:
        s_clipped = int(np.clip(np.round(s), -3, 3))
        # Find nearest valid level
        nearest = min(_GRAY_DEC.keys(), key=lambda x: abs(x - s_clipped))
        bits.extend(_GRAY_DEC[nearest])
    return np.array(bits, dtype=np.int8)


# ─────────────────────────────────────────────────────────────────────────────
# TX FFE (pre-emphasis)
# ─────────────────────────────────────────────────────────────────────────────

class TxFFE:
    """
    Transmitter FIR pre-emphasis filter.
    Operates under a power constraint: sum(|c_k|) ≤ 1 (normalised swing).

    Parameters
    ----------
    taps : array-like
        FIR tap coefficients. tap[0] = pre-cursor, tap[1] = main cursor,
        tap[2]... = post-cursor. Will be normalised to unit peak swing.
    normalise : bool
        If True, normalise so that max output magnitude = 1.
    """
    def __init__(self, taps: Optional[np.ndarray] = None, normalise: bool = True):
        if taps is None:
            taps = np.array([0.0, 1.0, 0.0])   # pass-through
        self.taps = np.asarray(taps, dtype=float)
        if normalise:
            peak = np.max(np.abs(np.convolve(self.taps,
                          np.ones(1))))  # worst-case amplitude
            if peak > 0:
                self.taps /= peak

    def apply(self, symbols: np.ndarray) -> np.ndarray:
        """Apply TX FFE to symbol stream. Returns filtered symbol stream."""
        return np.convolve(symbols.astype(float), self.taps, mode='same')

    def frequency_response(self, fbaud: float,
                           n_pts: int = 512) -> Tuple[np.ndarray, np.ndarray]:
        """Return (freq, |H(f)|_dB) of the TX FFE."""
        freq = np.fft.rfftfreq(n_pts, d=1.0/fbaud)
        H = np.fft.rfft(self.taps, n=n_pts)
        return freq, 20 * np.log10(np.abs(H) + 1e-15)


# ─────────────────────────────────────────────────────────────────────────────
# Full TX chain
# ─────────────────────────────────────────────────────────────────────────────

class PAM4Transmitter:
    """
    Complete PAM-4 transmitter: PRBS → scramble → Gray encode → TX FFE.

    Example
    -------
    tx = PAM4Transmitter(prbs_order=31, ffe_taps=[-0.1, 0.8, -0.1])
    symbols = tx.generate(n_bits=100_000)
    """
    def __init__(self,
                 prbs_order: int = 31,
                 ffe_taps: Optional[np.ndarray] = None,
                 scramble: bool = True,
                 seed: int = 1):
        self.prbs = PRBSGenerator(order=prbs_order, seed=seed)
        self.scrambler = Scrambler() if scramble else None
        self.ffe = TxFFE(taps=ffe_taps)
        self._raw_bits = None
        self._line_bits = None
        self._ref_symbols = None

    def generate(self, n_bits: int) -> Tuple[np.ndarray, np.ndarray]:
        """
        Returns
        -------
        symbols : ndarray, shape (n_bits//2,)   PAM-4 symbols after TX FFE
        bits    : ndarray, shape (n_bits,)      LINE bits — the (scrambled) bits
                  that Gray-map onto the transmitted symbols. Use these as the
                  BER / LMS-training reference; they are coherent with `symbols`.

        Notes
        -----
        Earlier revisions returned the raw pre-scrambler PRBS bits here, which
        do NOT correspond to the transmitted symbols when scrambling is on —
        any training or BER count against them is invalid. Raw PRBS bits remain
        available via `.raw_bits` (descramble RX bits before comparing).
        """
        bits = self.prbs.generate_fast(n_bits)
        self._raw_bits = bits.copy()
        if self.scrambler:
            bits_line = self.scrambler.scramble(bits)
        else:
            bits_line = bits
        self._line_bits = bits_line.copy()
        symbols_raw = gray_encode(bits_line)
        self._ref_symbols = symbols_raw.astype(float)
        symbols_ffe = self.ffe.apply(symbols_raw)
        return symbols_ffe, bits_line

    @property
    def raw_bits(self) -> Optional[np.ndarray]:
        """Pre-scrambler PRBS bits."""
        return self._raw_bits

    @property
    def reference_bits(self) -> Optional[np.ndarray]:
        """Line bits coherent with the transmitted symbols (post-scrambler)."""
        return self._line_bits

    @property
    def reference_symbols(self) -> Optional[np.ndarray]:
        """Transmitted PAM-4 symbols before TX FFE (ideal levels ±1, ±3)."""
        return self._ref_symbols


# ─────────────────────────────────────────────────────────────────────────────
# Oversampled TX waveform with jitter injection
# ─────────────────────────────────────────────────────────────────────────────

def tx_waveform(symbols: np.ndarray,
                osr: int,
                fbaud: float,
                tx_bw_hz: Optional[float] = None,
                rj_rms_ui: float = 0.0,
                sj_amp_ui: float = 0.0,
                sj_freq_hz: float = 0.0,
                rng: Optional[np.random.Generator] = None) -> np.ndarray:
    """
    Build an oversampled analog TX waveform from a symbol stream.

    Chain: ZOH upsample → single-pole TX bandwidth shaping → jitter injection
    by phase-warped resampling  x_j(t) = x(t − Δ(t)).

    Parameters
    ----------
    symbols   : baud-rate symbol stream (post TX-FFE)
    osr       : samples per UI (≥ 8 recommended)
    fbaud     : symbol rate [Hz]
    tx_bw_hz  : TX driver 3-dB bandwidth (None = ideal edges).
                Rule of thumb: 0.35/t_rise; ~0.75·fbaud is a realistic driver.
    rj_rms_ui : random jitter, rms, in UI (white, per-symbol, interpolated)
    sj_amp_ui : sinusoidal jitter amplitude [UI] (for JTOL testing)
    sj_freq_hz: sinusoidal jitter frequency [Hz]
    rng       : numpy Generator (REQUIRED for reproducible RJ; falls back to
                a fresh default_rng if omitted)

    Returns
    -------
    waveform at f_s = osr·fbaud, length len(symbols)·osr
    """
    if rng is None:
        rng = np.random.default_rng()
    x = np.repeat(np.asarray(symbols, dtype=float), osr)
    f_s = osr * fbaud

    # TX bandwidth: single real pole, bilinear-transform discretisation
    if tx_bw_hz is not None:
        from scipy.signal import lfilter, bilinear
        b, a = bilinear([1.0], [1.0 / (2 * np.pi * tx_bw_hz), 1.0], fs=f_s)
        x = lfilter(b, a, x)

    # Jitter: Δ(t) in samples, built per-symbol and interpolated to the
    # oversampled grid, then applied as a time warp
    if rj_rms_ui > 0.0 or (sj_amp_ui > 0.0 and sj_freq_hz > 0.0):
        n_sym = len(symbols)
        t_sym = np.arange(n_sym) / fbaud
        delta_ui = np.zeros(n_sym)
        if rj_rms_ui > 0.0:
            delta_ui += rng.normal(0.0, rj_rms_ui, n_sym)
        if sj_amp_ui > 0.0 and sj_freq_hz > 0.0:
            delta_ui += sj_amp_ui * np.sin(2 * np.pi * sj_freq_hz * t_sym)
        # Interpolate jitter to the sample grid and warp the time base
        n = np.arange(len(x))
        delta_samp = np.interp(n / osr, np.arange(n_sym), delta_ui) * osr
        x = np.interp(n - delta_samp, n, x)

    return x


# ─────────────────────────────────────────────────────────────────────────────
# PAM-4 slicer and BER counter
# ─────────────────────────────────────────────────────────────────────────────

PAM4_LEVELS = np.array([-3.0, -1.0, 1.0, 3.0])

def pam4_slicer(x: np.ndarray,
                thresholds: Optional[np.ndarray] = None) -> np.ndarray:
    """
    Hard PAM-4 slicer. Thresholds default to {-2, 0, +2}.
    Returns decided symbols in {-3,-1,+1,+3}.
    """
    if thresholds is None:
        thresholds = np.array([-2.0, 0.0, 2.0])
    decisions = np.full(len(x), -3.0)
    decisions[x >  thresholds[0]] = -1.0
    decisions[x >  thresholds[1]] =  1.0
    decisions[x >  thresholds[2]] =  3.0
    return decisions

def count_ber(tx_bits: np.ndarray, rx_symbols: np.ndarray,
              descramble: bool = False,
              scrambler: Optional[Scrambler] = None) -> Tuple[float, int, int]:
    """
    Compare TX line bits to RX decoded symbols.
    `tx_bits` must be the LINE bits (post-scrambler) coherent with the
    transmitted symbols — i.e. what `PAM4Transmitter.generate` returns.
    Returns (BER, n_errors, n_bits).
    """
    rx_bits = gray_decode(rx_symbols)
    n = min(len(tx_bits), len(rx_bits))
    errors = int(np.sum(tx_bits[:n] != rx_bits[:n]))
    ber = errors / max(n, 1)
    return ber, errors, n


def ber_wilson_upper(n_errors: int, n_bits: int, z: float = 1.96) -> float:
    """
    Wilson-score upper confidence bound on BER.

    With zero observed errors this still returns a meaningful bound
    (~ z²/n for large n), unlike the naive estimate 0/n. Use it whenever
    reporting a measured BER so "0 errors in 40k bits" reads as
    "BER < 1e-4 @ 95%" rather than "BER = 0".

    z = 1.96 → 95 % one-sided-ish bound; z = 3.0 → ~99.9 %.
    """
    if n_bits <= 0:
        return 1.0
    p = n_errors / n_bits
    z2 = z * z
    denom = 1.0 + z2 / n_bits
    centre = p + z2 / (2.0 * n_bits)
    half = z * np.sqrt(p * (1.0 - p) / n_bits + z2 / (4.0 * n_bits**2))
    return min(1.0, (centre + half) / denom)


if __name__ == "__main__":
    tx = PAM4Transmitter(prbs_order=31, ffe_taps=[-0.05, 0.9, -0.05])
    syms, bits = tx.generate(n_bits=10_000)
    print(f"TX: generated {len(syms)} PAM-4 symbols from {len(bits)} bits")
    print(f"Symbol levels present: {np.unique(np.round(syms))}")
    # Check gray encode/decode round-trip
    test_bits = np.random.randint(0, 2, 1000).astype(np.int8)
    syms_enc = gray_encode(test_bits)
    bits_dec = gray_decode(syms_enc)
    assert np.array_equal(test_bits, bits_dec), "Gray encode/decode mismatch!"
    print("Gray coding round-trip: PASS")
    print("pam4_chain.py: self-test PASSED")
