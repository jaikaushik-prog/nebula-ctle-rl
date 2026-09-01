"""
tests/test_pool_size.py — gates on `exp_pool_size`, the library-size measurement
(`PREDICTIONS.md` entry 51).

WHY EACH GUARD EXISTS
----------------------
1.  **The re-implemented ranking must BE the shipped one.** `dev_all` duplicates
    `exp_coverage.library_candidates`' criterion so the vector can be
    subsampled. Two definitions of one thing is this repo's third named failure
    mode (G32), and here it would silently change every number in the artifact.
    `q5_control` is the run-time check; these are the unit-time ones.
2.  **`_mannwhitney_p` is hand-rolled** because `scipy` is not a dependency of
    this project. A hand-rolled statistic with no test is a number nobody can
    trust, and Q4 -- the finding that `dev` does not separate solved from
    unsolved requests -- rests entirely on it.
3.  **The registered thresholds must not drift.** `FLAT_BAND` and
    `DEGRADED_BAND` were fixed in entry 51 *before* the run and both Q1 and Q3
    missed against them. Retuning them afterwards would convert a recorded miss
    into a hit, which is the exact move the pre-registration exists to prevent.
4.  **It must not simulate.** The entry's whole claim is that it is a zero-
    simulation re-analysis; an accidental import of the device layer would make
    that false while every printed number stayed the same.
5.  **`analyse` must not invent a knee.** `n_star` is the smallest grid size
    meeting the registered bar; if no size meets it, it must be `None` rather
    than the largest one tried.

No pool and no artifacts are needed: the ranking tests build a tiny synthetic
pool whose answer is known by construction.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from nebula.experiments import exp_pool_size as PS
from nebula.rl import reward_v1 as R


# ── 1. the criterion is the shipped one ──────────────────────────────────────


def test_dev_all_is_the_documented_formula():
    """`max(|df|/TOL_f, |dpk|/TOL_pk)` -- computed by hand on one row."""
    pk = np.array([7.0])
    fo = np.array([math.log2(2.0e9 / 2.5e9)])
    got = PS.dev_all(pk, fo, peaking_db=6.0, f_peak_hz=2.0e9)
    # frequency is exact, so the peaking axis must bind: 1 dB of its tolerance
    assert got[0] == pytest.approx(1.0 / R.TOL["S3_peaking_match"])


def test_dev_all_takes_the_MAX_not_the_sum_of_the_two_axes():
    """A max and a sum agree when one axis is zero; they must not be confused.

    Ranking on the sum would trade a frequency miss against a peaking hit,
    which is a different proposer from the one every published number used.
    """
    pk = np.array([6.0])
    fo = np.array([math.log2(2.0e9 / 2.5e9) + 0.10])
    d = float(PS.dev_all(pk, fo, peaking_db=6.0, f_peak_hz=2.0e9)[0])
    assert d == pytest.approx(0.10 / R.TOL["S3_f_peak_match"])


def test_dev_all_ranks_a_synthetic_pool_the_way_the_shipped_one_would():
    """Four designs at known distances must sort in the order built.

    Each row's `dev` is written out beside it, because the interesting
    orderings are the ones where the two axes disagree and an eyeballed
    fixture gets them wrong.
    """
    tgt_pk, tgt_hz = 8.0, 1.8e9
    tgt_oct = math.log2(tgt_hz / 2.5e9)
    tp, tf = R.TOL["S3_peaking_match"], R.TOL["S3_f_peak_match"]
    pk = np.array([8.0, 8.0, 9.0, 11.0])          # dpk = 0, 0, 1.0, 3.0
    fo = np.array([tgt_oct, tgt_oct + 0.05 * tf,  # dfo = 0, .05tf, 0, 3tf
                   tgt_oct, tgt_oct + 3.0 * tf])
    got = PS.dev_all(pk, fo, tgt_pk, tgt_hz)
    assert got == pytest.approx([0.0, 0.05, 1.0 / tp, 3.0])
    assert list(np.argsort(got, kind="stable")) == [0, 1, 2, 3]


def test_dev_is_zero_only_for_an_exact_match_on_both_axes():
    tgt_oct = math.log2(1.8e9 / 2.5e9)
    d = PS.dev_all(np.array([8.0]), np.array([tgt_oct]), 8.0, 1.8e9)
    assert float(d[0]) == pytest.approx(0.0, abs=1e-15)


# ── 2. the hand-rolled statistic ─────────────────────────────────────────────


def test_mannwhitney_identical_samples_is_not_significant():
    a = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    assert PS._mannwhitney_p(a, a.copy()) > 0.9


def test_mannwhitney_separated_samples_is_significant():
    a = np.arange(1.0, 11.0)
    b = np.arange(101.0, 111.0)
    assert PS._mannwhitney_p(a, b) < 0.01


def test_mannwhitney_is_symmetric_in_its_arguments():
    """Two-sided: swapping the groups cannot change the p-value."""
    a = np.array([1.0, 4.0, 9.0, 16.0, 25.0])
    b = np.array([2.0, 3.0, 10.0, 11.0])
    assert PS._mannwhitney_p(a, b) == pytest.approx(PS._mannwhitney_p(b, a))


def test_mannwhitney_handles_ties_without_dividing_by_zero():
    """All-tied input is the degenerate case; it must return 1.0, not NaN."""
    a = np.ones(5)
    b = np.ones(5)
    p = PS._mannwhitney_p(a, b)
    assert p is not None and math.isfinite(p) and p == pytest.approx(1.0)


def test_mannwhitney_returns_None_on_an_empty_group():
    assert PS._mannwhitney_p(np.array([]), np.array([1.0, 2.0])) is None


# ── 3. the registered thresholds have not drifted ────────────────────────────


def test_the_registered_bands_are_still_entry_51s_values():
    """**Entry 51 fixed these BEFORE the run and Q1/Q3 missed against them.**

    Loosening either would turn a recorded miss into a hit. If a future entry
    wants different bands it registers them and changes this test in the same
    commit, deliberately.
    """
    assert PS.FLAT_BAND == 0.05
    assert PS.DEGRADED_BAND == 0.25
    assert PS.K == 5


def test_the_pool_size_grid_spans_three_orders_and_ends_at_the_full_pool():
    assert PS.N_GRID[0] == 50
    assert PS.N_GRID[-1] == 74_526
    assert list(PS.N_GRID) == sorted(PS.N_GRID)


# ── 4. it does not simulate ──────────────────────────────────────────────────


def test_the_module_never_reaches_the_device_layer():
    """**The zero-simulation claim, checked on the source rather than trusted.**

    `is_zero_simulation: true` is stamped on the artifact; nothing enforced it.
    """
    import inspect

    src = inspect.getsource(PS)
    for banned in ("sky130_runner", "run_point", "ngspice", "evaluate_at_points"):
        assert banned not in src, f"{banned} reachable from a zero-sim module"


# ── 5. `analyse` reports absence rather than inventing a knee ────────────────


def _fake(n_requests: int, excess_by_n: dict) -> list:
    return [{"index": i, "peaking_db": 6.0, "f_peak_hz": 1.8e9,
             "accepted_rank": (1 if i < 6 else None),
             "full_pool_median_dev": 0.02,
             "by_n": [{"n": n, "median_dev": 0.02 + e, "p90_dev": 0.02 + e,
                       "is_full_pool": n == 74_526, "excess": e}
                      for n, e in excess_by_n.items()]}
            for i in range(n_requests)]


def test_n_star_is_None_when_no_grid_size_meets_the_registered_bar():
    """A knee that does not exist must read as `None`, never as the biggest N."""
    per_req = _fake(16, {n: 1.0 for n in PS.N_GRID})
    assert PS.analyse(per_req)["n_star"] is None


def test_n_star_is_the_SMALLEST_grid_size_that_qualifies():
    excess = {n: (0.01 if n >= 3000 else 1.0) for n in PS.N_GRID}
    a = PS.analyse(_fake(16, excess))
    assert a["n_star"] == 3000


def test_break_even_is_the_pool_size_over_the_measured_deck_saving():
    excess = {n: (0.01 if n >= 3000 else 1.0) for n in PS.N_GRID}
    a = PS.analyse(_fake(16, excess))
    assert a["break_even_requests"] == pytest.approx(
        3000 / a["decks_saved_per_request"], rel=1e-3)


def test_break_even_is_None_when_there_is_no_knee():
    """No knee means no intercept to quote -- not an intercept of zero."""
    a = PS.analyse(_fake(16, {n: 1.0 for n in PS.N_GRID}))
    assert a["break_even_requests"] is None


def test_the_deck_saving_is_entry_40s_measured_pair():
    """857.4 - 642.1, from `hybrid_results.json` and the plain coverage sweep."""
    a = PS.analyse(_fake(16, {n: 0.0 for n in PS.N_GRID}))
    assert a["decks_saved_per_request"] == pytest.approx(215.3125, abs=1e-3)


def test_q4_partitions_on_accepted_rank_not_on_position():
    a = PS.analyse(_fake(16, {n: 0.0 for n in PS.N_GRID}))["q4"]
    assert a["n_solved"] == 6 and a["n_unsolved"] == 10
