"""Unit tests: MMSE init, FFE/DFE convergence, MLSE trellis correctness."""
import numpy as np
import pytest

from equalizers import (FFE, FFEDFEReceiver, MLSE, mmse_init_ffe,
                        hard_slicer_pam4, PAM4_LEVELS)


class TestMMSEInit:
    def test_identity_channel_gives_delta(self):
        """For h = [1], the MMSE FFE is (nearly) a unit impulse."""
        w = mmse_init_ffe(np.array([1.0]), n_ffe=11, snr_db=30)
        peak = np.argmax(np.abs(w))
        assert np.abs(w[peak]) == pytest.approx(1.0, abs=0.05)
        off_peak = np.delete(w, peak)
        assert np.max(np.abs(off_peak)) < 0.1

    def test_reduces_isi(self):
        """FFE from MMSE init must reduce peak ISI on a lossy channel."""
        h = np.array([0.1, 1.0, 0.45, 0.2, 0.1])
        w = mmse_init_ffe(h, n_ffe=15, snr_db=25)
        combined = np.convolve(h, w)
        cur = np.argmax(np.abs(combined))
        isi_before = (np.sum(np.abs(h)) - np.max(np.abs(h))) / np.max(np.abs(h))
        isi_after = (np.sum(np.abs(combined)) - np.abs(combined[cur])) \
                    / np.abs(combined[cur])
        assert isi_after < isi_before


class TestFFEDFEReceiver:
    def test_converges_on_isi_channel(self):
        rng = np.random.default_rng(42)
        N = 20_000
        h = np.array([0.05, 1.0, 0.30, 0.08, 0.02])
        cursor = int(np.argmax(np.abs(h)))
        tx = rng.choice(PAM4_LEVELS, N)
        r = np.convolve(tx, h)[:N] + rng.normal(0, 0.1, N)
        rx = FFEDFEReceiver(n_ffe_pre=3, n_ffe_post=12, n_dfe=4)
        rx.ffe.init_from_channel(h, snr_db=20)
        decisions, info = rx.process(r, ref_syms=tx, training_len=4000,
                                     sys_delay=cursor)
        n_eval = len(decisions) - 4000
        ser = np.mean(decisions[4000:] != tx[4000:4000 + n_eval])
        assert ser < 1e-3

    def test_decisions_indexed_by_symbol(self):
        """decisions[k] must be the decision for TX symbol k (alignment)."""
        rng = np.random.default_rng(3)
        N = 6000
        tx = rng.choice(PAM4_LEVELS, N)
        r = tx + rng.normal(0, 0.05, N)   # ideal channel, tiny noise
        rx = FFEDFEReceiver(n_ffe_pre=2, n_ffe_post=4, n_dfe=2)
        decisions, info = rx.process(r, ref_syms=tx, training_len=1000,
                                     sys_delay=0)
        ser = np.mean(decisions[1000:] != tx[1000:len(decisions)])
        assert ser < 1e-3


class TestMLSE:
    def test_perfect_detection_no_noise(self):
        """With zero noise and exact channel knowledge, MLSE must be exact."""
        rng = np.random.default_rng(5)
        h = np.array([1.0, 0.5, 0.2])
        tx = rng.choice(PAM4_LEVELS, 500)
        r = np.convolve(tx, h)[:500]
        mlse = MLSE(h)
        d = mlse.detect(r)
        # allow the last L-1 symbols to be off (no trellis termination)
        assert np.array_equal(d[:-3], tx[:-3])

    def test_beats_slicer_under_isi(self):
        rng = np.random.default_rng(6)
        h = np.array([1.0, 0.6])
        tx = rng.choice(PAM4_LEVELS, 3000)
        r = np.convolve(tx, h)[:3000] + rng.normal(0, 0.15, 3000)
        ser_slicer = np.mean(hard_slicer_pam4(r) != tx)
        ser_mlse = np.mean(MLSE(h).detect(r)[:-2] != tx[:-2])
        assert ser_mlse < ser_slicer / 2
