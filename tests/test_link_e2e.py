"""End-to-end regression: full waveform link (TX→channel→CTLE→CDR→FFE/DFE→BER)."""
import numpy as np
import pytest

from link_sim import LinkConfig, run_link
from dataclasses import replace


BASE = LinkConfig(channel_cm=3.0, noise_db=26.0,
                  n_symbols=15_000, training_len=5_000)


class TestEndToEnd:
    def test_nominal_link_closes(self):
        """3 cm / ~9 dB channel at 26 dB SNR: lock + BER below 1e-3."""
        r = run_link(BASE, verbose=False)
        assert r['cdr_locked']
        assert r['ber'] < 1e-3
        assert r['n_bits'] > 15_000

    def test_monte_carlo_seeds_differ(self):
        """Different seeds MUST give different error patterns (the pre-audit
        harness hard-seeded the global RNG and made every MC run identical)."""
        r1 = run_link(replace(BASE, seed=11, noise_db=22.0), verbose=False)
        r2 = run_link(replace(BASE, seed=22, noise_db=22.0), verbose=False)
        assert r1['n_errors'] != r2['n_errors'] or r1['ber'] != r2['ber']

    def test_same_seed_reproducible(self):
        r1 = run_link(replace(BASE, seed=7), verbose=False)
        r2 = run_link(replace(BASE, seed=7), verbose=False)
        assert r1['n_errors'] == r2['n_errors']

    def test_tracks_low_freq_sj(self):
        """0.4 UI of 1 MHz SJ is inside the CDR loop BW: link must survive."""
        r = run_link(replace(BASE, sj_amp_ui=0.4, sj_freq_hz=1e6),
                     verbose=False)
        assert r['cdr_locked']
        assert r['ber'] < 1e-3

    def test_ber_degrades_with_snr(self):
        lo = run_link(replace(BASE, noise_db=18.0), verbose=False)
        hi = run_link(replace(BASE, noise_db=26.0), verbose=False)
        assert lo['ber'] > hi['ber']

    def test_ppm_offset_tracked(self):
        """100 ppm TX/RX offset must be absorbed by the loop integrator."""
        r = run_link(replace(BASE, ppm_offset=100.0), verbose=False)
        assert r['cdr_locked']
        assert r['ber'] < 1e-3


class TestMMPostFFEArchitecture:
    """
    Phase 3a: MM phase detector behind a frozen timing-path FFE. Its whole
    point is locking on channels whose RAW zero crossings are pattern-smeared
    (where the Alexander PD fails) — these tests pin that claim.
    """

    def test_locks_where_alexander_cannot_6cm_0db(self):
        """6 cm @ 0 dB CTLE: crossing jitter 0.75 UI, Alexander-infeasible.
        The post-FFE MM PD must lock (residual BER is clipping-limited)."""
        cfg = replace(BASE, channel_cm=6.0, ctle_peaking_db=0.0,
                      noise_db=28.0, cdr_arch='mm_postffe',
                      n_symbols=20_000, training_len=6_000)
        r = run_link(cfg, verbose=False)
        assert r['cdr_locked']
        assert r['cdr_jitter_mui'] < 50

    def test_locks_where_alexander_lost_10cm(self):
        """10 cm @ 6 dB: Alexander lost lock entirely. MM-postFFE must lock
        (the link may still fail on eye margin — that is honest)."""
        cfg = replace(BASE, channel_cm=10.0, ctle_peaking_db=6.0,
                      noise_db=28.0, cdr_arch='mm_postffe',
                      n_symbols=20_000, training_len=6_000)
        r = run_link(cfg, verbose=False)
        assert r['cdr_locked']

    def test_parity_on_short_channel(self):
        """On an easy channel both architectures must deliver low BER."""
        alex = run_link(replace(BASE, cdr_arch='alexander'), verbose=False)
        mm = run_link(replace(BASE, cdr_arch='mm_postffe'), verbose=False)
        assert mm['cdr_locked'] and alex['cdr_locked']
        assert mm['ber'] < 1e-3 and alex['ber'] < 1e-3

    def test_mm_tracks_ppm(self):
        cfg = replace(BASE, cdr_arch='mm_postffe', ppm_offset=100.0)
        r = run_link(cfg, verbose=False)
        assert r['cdr_locked']
        assert r['ber'] < 1e-3

    def test_clip_fraction_reported(self):
        r = run_link(replace(BASE, cdr_arch='mm_postffe'), verbose=False)
        assert 0.0 <= r['adc_clip_frac'] < 0.05   # short channel: low clip
