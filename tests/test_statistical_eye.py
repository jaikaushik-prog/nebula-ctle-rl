"""Unit + cross-validation tests for the semi-analytic BER engine."""
import numpy as np
import pytest

from statistical_eye import (StatisticalEye, isi_pmf, qfunc, optimize_ctle,
                             PAM4_LEVELS)
from link_sim import LinkConfig, run_link
from dataclasses import replace


class TestISIPMF:
    def test_sums_to_one(self):
        grid, pmf = isi_pmf(np.array([0.1, -0.05, 0.02]))
        assert pmf.sum() == pytest.approx(1.0, abs=1e-9)

    def test_single_tap_four_points(self):
        """One tap h: ISI takes values {±h, ±3h}, each with p=1/4."""
        h = 0.1
        grid, pmf = isi_pmf(np.array([h]))
        nz = pmf > 1e-12
        vals = np.sort(grid[nz])
        assert len(vals) == 4
        assert np.allclose(vals, [-3 * h, -h, h, 3 * h], atol=1e-3)
        assert np.allclose(pmf[nz], 0.25, atol=1e-9)

    def test_empty_taps_is_delta(self):
        grid, pmf = isi_pmf(np.array([]))
        assert pmf.max() == pytest.approx(1.0)
        assert abs(grid[np.argmax(pmf)]) < 1e-9

    def test_variance_matches_theory(self):
        """Var[ISI] = E[a²]·Σh² = 5·Σh² for equiprobable PAM-4."""
        taps = np.array([0.12, -0.07, 0.03, 0.02])
        grid, pmf = isi_pmf(taps)
        var = float(np.sum(pmf * grid ** 2))
        assert var == pytest.approx(5.0 * np.sum(taps ** 2), rel=1e-3)


class TestClosedForm:
    def test_ideal_channel_matches_closed_form(self):
        """
        A near-lossless channel with wide TX bandwidth and 0 dB CTLE has
        (almost) no ISI, so the engine must reproduce BER = (3/4)·Q(1/σ)
        using its own slicer sigma.
        """
        cfg = LinkConfig(channel_cm=0.05, noise_db=24.0, tx_bw_rel=4.0,
                         ctle_peaking_db=0.0, tx_rj_rms_ui=0.0,
                         aperture_rj_fs=0.0)
        eye = StatisticalEye.from_link_config(cfg)
        eye.rj_ui = 0.0
        ber, comb = eye.ber_at_phase(0.0)
        sigma = eye._slicer_sigma(eye._design_ffe())
        ber_cf = 0.75 * float(qfunc(1.0 / sigma))
        assert ber == pytest.approx(ber_cf, rel=0.3)

    def test_monotonic_in_snr(self):
        bers = []
        for snr in (20.0, 24.0, 28.0):
            cfg = LinkConfig(channel_cm=3.0, noise_db=snr)
            r = StatisticalEye.from_link_config(cfg).analyse(n_phase=15)
            bers.append(r.ber)
        assert bers[0] > bers[1] > bers[2]

    def test_dfe_helps(self):
        cfg = LinkConfig(channel_cm=5.0, noise_db=26.0)
        with_dfe = StatisticalEye.from_link_config(cfg)
        no_dfe = StatisticalEye.from_link_config(replace(cfg, dfe_taps=0))
        b1, _ = with_dfe.ber_at_phase(0.0)
        b0, _ = no_dfe.ber_at_phase(0.0)
        assert b1 < b0


class TestCrossValidation:
    """
    The heart of Phase 2: the two independent engines must agree where the
    time-domain engine can actually measure (BER 1e-2 .. 1e-4). Perfect
    agreement is not expected — the statistical model is a reference
    receiver (ideal DFE, MMSE-designed FFE, Gaussianized quantization) —
    but they must land within an order of magnitude.
    """

    @pytest.mark.parametrize("snr_db", [20.0, 24.0])
    def test_engines_agree_within_order_of_magnitude(self, snr_db):
        cfg = LinkConfig(channel_cm=3.0, noise_db=snr_db,
                         n_symbols=20_000, training_len=6_000)
        td = run_link(cfg, verbose=False)
        st = StatisticalEye.from_link_config(cfg).analyse(n_phase=15)
        assert td['cdr_locked']
        assert td['ber'] > 0, "need measurable BER for the comparison"
        ratio = st.ber / td['ber']
        assert 0.1 < ratio < 10.0, \
            f"stat {st.ber:.2e} vs td {td['ber']:.2e} (ratio {ratio:.2f})"


class TestOptimizer:
    def test_finds_nonzero_peaking_for_lossy_channel(self):
        """
        The unconstrained slicer optimum at 6 cm is 0 dB CTLE (a long FFE
        equalizes with less noise boost than analog peaking) — but 0 dB is
        CDR-INFEASIBLE: the BB PD's crossings are pattern-smeared and the
        time-domain engine shows 100x worse BER there. The optimizer must
        exclude it and pick a nonzero feasible peaking.
        """
        cfg = LinkConfig(channel_cm=6.0, noise_db=28.0)
        out = optimize_ctle(cfg, peaking_grid=np.array([0.0, 4.0, 8.0, 12.0]))
        sweep = {r['peaking_db']: r for r in out['sweep']}
        assert not sweep[0.0]['cdr_feasible']
        assert out['best']['peaking_db'] > 0.0
        assert out['best']['cdr_feasible']

    def test_short_channel_all_feasible(self):
        cfg = LinkConfig(channel_cm=2.0, noise_db=28.0)
        out = optimize_ctle(cfg, peaking_grid=np.array([0.0, 3.0, 6.0]))
        assert out['any_feasible']

    def test_crossing_jitter_grows_with_loss(self):
        from statistical_eye import StatisticalEye
        cj = []
        for L in (2.0, 6.0, 10.0):
            cfg = LinkConfig(channel_cm=L, noise_db=28.0, ctle_peaking_db=6.0)
            cj.append(StatisticalEye.from_link_config(cfg).crossing_jitter_ui())
        assert cj[0] < cj[1] < cj[2]
