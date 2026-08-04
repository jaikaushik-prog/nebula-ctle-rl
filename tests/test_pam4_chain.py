"""Unit tests: PRBS, Gray coding, scrambler, TX reference coherence, BER stats."""
import numpy as np
import pytest

from pam4_chain import (PRBSGenerator, Scrambler, gray_encode, gray_decode,
                        PAM4Transmitter, pam4_slicer, count_ber,
                        ber_wilson_upper, PAM4_LEVELS)


class TestPRBS:
    def test_prbs7_period(self):
        """A maximal-length LFSR of order 7 must repeat with period 2^7 - 1."""
        gen = PRBSGenerator(order=7, seed=1)
        seq = gen.generate(3 * 127)
        assert np.array_equal(seq[:127], seq[127:254])
        assert np.array_equal(seq[:127], seq[254:381])

    def test_prbs7_balance(self):
        """One period of PRBS7 contains 64 ones and 63 zeros."""
        gen = PRBSGenerator(order=7, seed=1)
        seq = gen.generate(127)
        assert int(seq.sum()) == 64

    def test_generate_fast_matches_generate(self):
        a = PRBSGenerator(order=15, seed=0x1234).generate(2000)
        b = PRBSGenerator(order=15, seed=0x1234).generate_fast(2000)
        assert np.array_equal(a, b)

    def test_zero_seed_recovers(self):
        """All-zero LFSR state is a lock-up state and must be avoided."""
        gen = PRBSGenerator(order=7, seed=0)
        seq = gen.generate(254)
        assert seq.sum() > 0


class TestGray:
    def test_roundtrip(self):
        rng = np.random.default_rng(0)
        bits = rng.integers(0, 2, 2000).astype(np.int8)
        assert np.array_equal(gray_decode(gray_encode(bits)), bits)

    def test_adjacent_levels_differ_by_one_bit(self):
        """Gray property: neighbouring PAM-4 levels differ in exactly 1 bit."""
        levels = np.array([-3.0, -1.0, 1.0, 3.0])
        dibits = [gray_decode(np.array([l])) for l in levels]
        for a, b in zip(dibits[:-1], dibits[1:]):
            assert int(np.sum(a != b)) == 1


class TestScrambler:
    def test_roundtrip(self):
        rng = np.random.default_rng(1)
        bits = rng.integers(0, 2, 500).astype(np.int8)
        tx = Scrambler(seed=0x1)
        rx = Scrambler(seed=0x1)
        assert np.array_equal(rx.descramble(tx.scramble(bits)), bits)

    def test_self_synchronising(self):
        """Descrambler with a WRONG seed must still recover after 58 bits."""
        rng = np.random.default_rng(2)
        bits = rng.integers(0, 2, 300).astype(np.int8)
        scrambled = Scrambler(seed=0x1).scramble(bits)
        out = Scrambler(seed=0xDEADBEEF).descramble(scrambled)
        assert np.array_equal(out[58:], bits[58:])


class TestTransmitterCoherence:
    """The returned bits MUST Gray-map onto the transmitted symbols."""

    def test_line_bits_match_symbols(self):
        tx = PAM4Transmitter(prbs_order=15, scramble=True, ffe_taps=[0, 1, 0])
        syms, bits_line = tx.generate(4000)
        assert np.array_equal(gray_encode(bits_line).astype(float),
                              tx.reference_symbols)

    def test_scrambled_line_bits_differ_from_raw(self):
        tx = PAM4Transmitter(prbs_order=15, scramble=True)
        _, bits_line = tx.generate(4000)
        assert not np.array_equal(bits_line, tx.raw_bits)

    def test_ideal_loopback_ber_zero(self):
        """Slicing the (FFE-bypassed) TX symbols must give BER = 0."""
        tx = PAM4Transmitter(prbs_order=15, scramble=True, ffe_taps=[0, 1, 0])
        syms, bits_line = tx.generate(4000)
        decisions = pam4_slicer(3.0 * syms / np.max(np.abs(syms)))
        ber, errors, n = count_ber(bits_line, decisions)
        assert errors == 0


class TestBERStats:
    def test_wilson_zero_errors_nonzero_bound(self):
        ub = ber_wilson_upper(0, 100_000)
        assert 0 < ub < 1e-4

    def test_wilson_bound_above_point_estimate(self):
        assert ber_wilson_upper(10, 10_000) > 10 / 10_000

    def test_wilson_tightens_with_n(self):
        assert ber_wilson_upper(0, 1_000_000) < ber_wilson_upper(0, 10_000)
