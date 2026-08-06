"""
Tests for `experiments/robust_geometry.py`.

ALL SIMULATOR-FREE. Every test here exercises arithmetic — ranks, p-values,
octaves, normalised box positions, and the robust/fragile split — because that
is where a wrong answer would be invisible. A p-value looks equally plausible
whichever way it comes out, and a margin in octaves cannot be sanity-checked by
eye. The two things that could not be caught by review are held to independent
references: the Mann-Whitney implementation to `scipy.stats.mannwhitneyu`, and
the octave margin to values computed by hand in the test.
"""

from __future__ import annotations

import math

import pytest

from nebula.common.types import SPEC_F_PEAK_HZ_RANGE, SPEC_PEAKING_DB_RANGE
from nebula.experiments.robust_geometry import (
    BOX_PARAMS,
    DesignRecord,
    EXPECTED,
    MEASURED_COLS,
    PLOT_PARAMS,
    _average_ranks,
    benjamini_hochberg,
    box_interiority,
    box_interiority_mean,
    check_reproduction,
    compare_groups,
    failure_edge_split,
    load_csv,
    mann_whitney_u,
    margin_quantum_octaves,
    margin_table,
    median,
    normalised_position,
    population,
    save_csv,
    threshold_table,
    window_margin_octaves,
)
from nebula.experiments.s3_yield import PROPOSED_BOX
from nebula.experiments.s9_yield import CL_LEGACY_PIN_F, SCREEN_CORNERS

# ─────────────────────────────────────────────────────────────────────────────
# median
# ─────────────────────────────────────────────────────────────────────────────


def test_median_odd_and_even():
    assert median([3.0, 1.0, 2.0]) == 2.0
    assert median([4.0, 1.0, 3.0, 2.0]) == 2.5


def test_median_of_empty_raises_rather_than_returning_nan():
    # A silent nan would propagate into a report table looking like a number.
    with pytest.raises(ValueError):
        median([])


# ─────────────────────────────────────────────────────────────────────────────
# ranks and Mann-Whitney U
# ─────────────────────────────────────────────────────────────────────────────


def test_ranks_are_one_based_and_ordered():
    assert _average_ranks([10.0, 30.0, 20.0]) == [1.0, 3.0, 2.0]


def test_tied_values_share_their_average_rank():
    # Ranks 2 and 3 are tied -> both get 2.5. Ranking them arbitrarily would
    # overstate the precision of U on a discrete axis like nf_in.
    assert _average_ranks([1.0, 5.0, 5.0, 9.0]) == [1.0, 2.5, 2.5, 4.0]


def test_all_ties_give_no_evidence_rather_than_a_divide_by_zero():
    mw = mann_whitney_u([2.0] * 5, [2.0] * 7)
    assert mw.p_two_sided == 1.0
    assert mw.rank_biserial == 0.0


def test_u_statistic_matches_the_textbook_definition():
    # U1 counts (a > b) pairs. a=[3,4] vs b=[1,2]: all 4 pairs -> U1 = 4.
    assert mann_whitney_u([3.0, 4.0], [1.0, 2.0]).u == 4.0
    assert mann_whitney_u([1.0, 2.0], [3.0, 4.0]).u == 0.0


def test_prob_a_greater_is_u_normalised_and_symmetric():
    mw = mann_whitney_u([3.0, 4.0], [1.0, 2.0])
    assert mw.prob_a_greater == 1.0
    assert mw.rank_biserial == 1.0
    back = mann_whitney_u([1.0, 2.0], [3.0, 4.0])
    assert back.prob_a_greater == 0.0


def test_empty_sample_raises():
    with pytest.raises(ValueError):
        mann_whitney_u([], [1.0, 2.0])


@pytest.mark.parametrize("a,b", [
    ([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0], [2.5, 3.5, 4.5, 9.0, 11.0]),
    ([0.1, 0.2, 0.2, 0.3, 0.9, 1.4, 1.4, 1.4], [0.2, 0.3, 1.4, 2.0, 2.0]),
    ([float(i % 8) for i in range(60)], [float(i % 5) for i in range(40)]),
])
def test_mann_whitney_agrees_with_scipy(a, b):
    """The load-bearing check: our U and p against an independent implementation.

    `scipy.stats.mannwhitneyu` with `method="asymptotic"` uses the same normal
    approximation with the same tie correction and continuity correction, so
    agreement should be to floating-point noise, not merely to two decimals.
    Cases deliberately include heavy ties, which is where a hand-rolled rank
    routine goes wrong.
    """
    scipy_stats = pytest.importorskip("scipy.stats")
    ref = scipy_stats.mannwhitneyu(a, b, alternative="two-sided",
                                   method="asymptotic", use_continuity=True)
    mine = mann_whitney_u(a, b)
    assert mine.u == pytest.approx(ref.statistic)
    assert mine.p_two_sided == pytest.approx(ref.pvalue, rel=1e-9)


def test_a_real_shift_is_detected_and_a_null_is_not():
    lo = [float(i) for i in range(60)]
    hi = [float(i) + 40.0 for i in range(60)]
    assert mann_whitney_u(hi, lo).p_two_sided < 1e-10
    same = [float(i) for i in range(60)]
    assert mann_whitney_u(same, list(reversed(same))).p_two_sided == 1.0


# ─────────────────────────────────────────────────────────────────────────────
# multiple-comparison correction
# ─────────────────────────────────────────────────────────────────────────────


def test_bh_leaves_a_single_pvalue_alone():
    assert benjamini_hochberg([0.03]) == pytest.approx([0.03])


def test_bh_matches_a_hand_computed_case():
    # p = .01 .02 .03 .04 (m=4). raw q = p*m/rank = .04 .04 .04 .04
    assert benjamini_hochberg([0.01, 0.02, 0.03, 0.04]) == pytest.approx(
        [0.04, 0.04, 0.04, 0.04])


def test_bh_is_monotone_and_capped_at_one():
    q = benjamini_hochberg([0.5, 0.9, 0.99, 0.001])
    assert all(0.0 <= v <= 1.0 for v in q)
    assert q[3] < q[0] <= q[1] <= q[2]


def test_bh_preserves_input_order():
    q = benjamini_hochberg([0.9, 0.001, 0.5])
    assert q[1] == min(q)


def test_bh_of_empty_is_empty():
    assert benjamini_hochberg([]) == []


# ─────────────────────────────────────────────────────────────────────────────
# the octave margin
# ─────────────────────────────────────────────────────────────────────────────


def test_s3_window_is_exactly_one_octave_so_the_margin_ceiling_is_half():
    lo, hi = SPEC_F_PEAK_HZ_RANGE
    assert hi == pytest.approx(2.0 * lo)
    centre = math.sqrt(lo * hi)
    assert window_margin_octaves(centre, lo, hi) == pytest.approx(0.5)


def test_margin_is_zero_on_each_edge_and_negative_outside():
    lo, hi = SPEC_F_PEAK_HZ_RANGE
    assert window_margin_octaves(lo, lo, hi) == pytest.approx(0.0)
    assert window_margin_octaves(hi, lo, hi) == pytest.approx(0.0)
    assert window_margin_octaves(lo / 2, lo, hi) == pytest.approx(-1.0)
    assert window_margin_octaves(4 * lo, lo, hi) == pytest.approx(-1.0)


def test_margin_is_multiplicative_not_additive():
    """The reason for octaves rather than hertz.

    1.4 GHz sits 150 MHz above the low edge; 2.23 GHz sits ~270 MHz below the
    high edge. In hertz those are very different distances; in octaves they are
    the same distance, and it is the octave one that predicts what a corner
    does, because every mechanism that moves this peak is multiplicative.
    """
    lo, hi = SPEC_F_PEAK_HZ_RANGE
    f_low_side = lo * 2 ** 0.17
    f_high_side = hi / 2 ** 0.17
    assert window_margin_octaves(f_low_side, lo, hi) == pytest.approx(0.17)
    assert window_margin_octaves(f_high_side, lo, hi) == pytest.approx(0.17)
    assert (f_low_side - lo) != pytest.approx(hi - f_high_side)


def test_the_margin_resolution_is_the_ac_sweep_grid_not_the_circuit():
    """`meas ac MAX` returns a grid SAMPLE, so f_peak is quantised at
    log2(10)/50 = 0.0664 octaves and the one-octave S3 window holds only ~15
    distinct values. Any threshold quoted finer than this is quoting the sweep
    setup. The committed data must show exactly that."""
    q = margin_quantum_octaves(50)
    assert q == pytest.approx(math.log2(10.0) / 50)
    assert q == pytest.approx(0.06644, abs=1e-5)
    winners = [r for r in load_csv() if r.tt_pass]
    distinct = {round(r.coord("f_peak_nom"), 3) for r in winners}
    assert len(distinct) == 15
    assert 1.0 / q == pytest.approx(len(distinct), abs=1.0)


def test_margin_rejects_impossible_windows_and_frequencies():
    with pytest.raises(ValueError):
        window_margin_octaves(0.0, 1.25e9, 2.5e9)
    with pytest.raises(ValueError):
        window_margin_octaves(2e9, 2.5e9, 1.25e9)


# ─────────────────────────────────────────────────────────────────────────────
# normalised box position and interiority
# ─────────────────────────────────────────────────────────────────────────────


def test_normalised_position_hits_zero_and_one_at_the_bounds():
    for name, (lo, hi, _log, _p) in PROPOSED_BOX.items():
        assert normalised_position(lo, name) == pytest.approx(0.0)
        assert normalised_position(hi, name) == pytest.approx(1.0)


def test_a_log_sampled_axis_is_read_on_a_log_scale():
    """The trap this avoids: reading `rs` (50-1000, log-sampled) linearly puts
    its GEOMETRIC centre at u = 0.18, i.e. apparently near the low edge, and
    would manufacture the 'fragile designs sit near an edge' pattern the whole
    experiment is testing for."""
    lo, hi, log, _ = PROPOSED_BOX["rs"]
    assert log
    geometric_centre = math.sqrt(lo * hi)
    assert normalised_position(geometric_centre, "rs") == pytest.approx(0.5)
    linear_reading = (geometric_centre - lo) / (hi - lo)
    assert linear_reading < 0.2


def test_interiority_is_zero_on_a_face_and_half_at_dead_centre():
    on_face = {n: PROPOSED_BOX[n][0] for n in PROPOSED_BOX}
    assert box_interiority(on_face) == pytest.approx(0.0)
    centre = {}
    for n, (lo, hi, log, _p) in PROPOSED_BOX.items():
        centre[n] = math.sqrt(lo * hi) if log else 0.5 * (lo + hi)
    assert box_interiority(centre) == pytest.approx(0.5)
    assert box_interiority_mean(centre) == pytest.approx(0.5)


def test_interiority_is_the_min_and_one_pinned_axis_is_enough_to_zero_it():
    centre = {n: (math.sqrt(lo * hi) if log else 0.5 * (lo + hi))
              for n, (lo, hi, log, _p) in PROPOSED_BOX.items()}
    pinned = dict(centre, rs=PROPOSED_BOX["rs"][1])
    assert box_interiority(pinned) == pytest.approx(0.0)
    # ...but the mean barely moves, which is exactly why both are reported.
    assert box_interiority_mean(pinned) > 0.4


def test_nf_in_is_excluded_from_interiority_because_rounding_pins_it():
    """`nf_in` is sampled continuously then rounded to 1..8, so nf = 1 forces a
    normalised position of exactly 0. Including it would give a min-interiority
    of 0 to roughly a seventh of the population for a reason that has nothing
    to do with the design."""
    assert "nf_in" in BOX_PARAMS
    assert "nf_in" not in PLOT_PARAMS
    centre = {n: (math.sqrt(lo * hi) if log else 0.5 * (lo + hi))
              for n, (lo, hi, log, _p) in PROPOSED_BOX.items()}
    centre["nf_in"] = 1.0
    assert box_interiority(centre) == pytest.approx(0.5)           # excluded
    assert box_interiority(centre, names=BOX_PARAMS) == pytest.approx(0.0)


# ─────────────────────────────────────────────────────────────────────────────
# the record: the split, and the derived coordinates
# ─────────────────────────────────────────────────────────────────────────────


def _rec(idx=0, tt_pass=True, corner_pass=(True, True, True), f_pk=1.77e9,
         peaking=6.0, **overrides):
    params = {n: (math.sqrt(lo * hi) if log else 0.5 * (lo + hi))
              for n, (lo, hi, log, _p) in PROPOSED_BOX.items()}
    params["cl"] = CL_LEGACY_PIN_F
    params.update({k: v for k, v in overrides.items() if k in params})
    measured = {c: 0.0 for c in MEASURED_COLS}
    measured.update({"gm": 12.0e-3, "gmbs": 4.5e-3, "id_a": 1.5e-3,
                     "f_pk_hz": f_pk, "peaking_db": peaking,
                     "nyquist_boost_db": 2.0})
    return DesignRecord(idx=idx, params=params, tt_ok=True, tt_pass=tt_pass,
                        tt_first_fail=None if tt_pass else "S3_f_peak",
                        measured=measured,
                        corner_pass=tuple(corner_pass),
                        corner_first_fail=tuple(
                            None if ok else "S3_f_peak" for ok in corner_pass))


def test_robust_requires_tt_and_every_screen_corner():
    assert _rec().robust
    assert not _rec(corner_pass=(True, True, False)).robust
    assert not _rec(tt_pass=False).robust


def test_fragile_is_tt_pass_and_at_least_one_corner_fail():
    assert _rec(corner_pass=(True, False, True)).fragile
    assert not _rec().fragile
    # A design that fails TT is in NEITHER group -- the two groups partition
    # the TT winners, not the population.
    r = _rec(tt_pass=False, corner_pass=(False, False, False))
    assert not r.robust and not r.fragile


def test_derived_uses_the_shared_section6_equations_with_the_body_effect():
    """Rule 9: the pole/zero/k come from `design_equations.predict`, and the
    SIMULATED gmbs is passed. Dropping it (§6 verbatim) would change k by the
    gmbs/gm ratio, which G27 measured at 0.33-0.40 on real devices."""
    r = _rec()
    k = r.derived()["k"]
    gm, gmbs, rs = 12.0e-3, 4.5e-3, r.params["rs"]
    assert k == pytest.approx(1.0 + (gm + gmbs) * rs / 2.0)
    assert k != pytest.approx(1.0 + gm * rs / 2.0)


def test_derived_f_peak_is_the_measured_one_not_the_predicted_one():
    """10b's failed prediction: a probed sample with f_p2 = 55.3 GHz peaked at
    9.55 GHz, so the analytic peak location is not usable here. `f_peak_nom`
    must be the simulator's number."""
    r = _rec(f_pk=1.3e9)
    d = r.derived()
    assert d["f_peak_nom"] == 1.3e9
    assert d["f_peak_nom"] != pytest.approx(d["f_p2"])


def test_peaking_margin_folds_the_other_two_sided_s3_axis():
    """S3 has TWO windows, not one. Peaking is bounded 3-12 dB, so the same
    folding applies: a design at 3.1 dB and one at 11.9 dB are both one step
    from failing, and a raw comparison of peaking cannot see that."""
    lo, hi = SPEC_PEAKING_DB_RANGE
    assert _rec(peaking=lo + 0.4).derived()["peaking_margin_db"] == pytest.approx(0.4)
    assert _rec(peaking=hi - 0.4).derived()["peaking_margin_db"] == pytest.approx(0.4)
    mid = 0.5 * (lo + hi)
    assert _rec(peaking=mid).derived()["peaking_margin_db"] == pytest.approx(
        (hi - lo) / 2)


def test_the_two_folded_margins_are_what_separate_the_real_groups():
    """The headline, pinned against the committed dataset: neither raw S3
    coordinate separates the groups, and both folded margins do. If a future
    change to the peak detector or the spec constants breaks that, this goes
    red rather than the write-up quietly becoming wrong."""
    recs = load_csv()
    robust = [r for r in recs if r.robust]
    fragile = [r for r in recs if r.fragile]
    raw = compare_groups(robust, fragile, ["f_peak_nom", "peaking_nom"])
    folded = compare_groups(robust, fragile,
                            ["f_peak_margin_oct", "peaking_margin_db"])
    assert all(c.q > 0.05 for c in raw)          # raw: no separation at all
    assert all(c.q < 1e-6 for c in folded)       # folded: overwhelming
    assert all(c.median_robust > c.median_fragile for c in folded)


def test_derived_margin_matches_the_standalone_function():
    r = _rec(f_pk=1.4e9)
    assert r.derived()["f_peak_margin_oct"] == pytest.approx(
        window_margin_octaves(1.4e9, *SPEC_F_PEAK_HZ_RANGE))


def test_coord_reaches_both_box_and_derived_names():
    r = _rec()
    assert r.coord("rs") == r.params["rs"]
    assert r.coord("f_peak_nom") == r.measured["f_pk_hz"]


# ─────────────────────────────────────────────────────────────────────────────
# the reproduction gate
# ─────────────────────────────────────────────────────────────────────────────


def test_reproduction_gate_passes_only_on_the_published_counts():
    recs = ([_rec(idx=i) for i in range(EXPECTED["n_robust"])]
            + [_rec(idx=i, corner_pass=(True, True, False))
               for i in range(EXPECTED["n_fragile"])]
            + [_rec(idx=i, tt_pass=False, corner_pass=(False, False, False))
               for i in range(EXPECTED["n_designs"] - EXPECTED["n_tt_pass"])])
    assert check_reproduction(recs) == []


def test_reproduction_gate_can_fail():
    """A gate that cannot go red is not a gate (CLAUDEwa §8 rule 10)."""
    problems = check_reproduction([_rec()])
    assert problems
    assert any("n_designs" in p for p in problems)


def test_the_population_reproduces_without_a_simulator():
    """Sampling is seeded, so the 1890 designs are regenerable for free — which
    is what makes the whole 'the raw results were lost' recovery possible."""
    designs = population()
    assert len(designs) == EXPECTED["n_designs"]
    assert all(d["cl"] == CL_LEGACY_PIN_F for d in designs)
    assert population() == designs                    # deterministic


# ─────────────────────────────────────────────────────────────────────────────
# analysis tables
# ─────────────────────────────────────────────────────────────────────────────


def test_compare_groups_reports_medians_in_display_units():
    robust = [_rec(rs=200.0), _rec(rs=200.0), _rec(rs=200.0)]
    fragile = [_rec(rs=800.0, corner_pass=(False, True, True))] * 3
    c = compare_groups(robust, fragile, ["rs"])[0]
    assert c.median_robust == pytest.approx(200.0)
    assert c.median_fragile == pytest.approx(800.0)
    assert c.prob_robust_greater == 0.0        # robust are entirely below


def test_compare_groups_adds_a_q_column_that_is_never_below_p():
    robust = [_rec(idx=i, rs=100.0 + i) for i in range(20)]
    fragile = [_rec(idx=i, rs=500.0 + i, corner_pass=(False, True, True))
               for i in range(20)]
    cs = compare_groups(robust, fragile, ["rs", "cs", "rl"])
    assert all(c.q >= c.p - 1e-12 for c in cs)


def test_margin_table_bins_only_tt_winners_and_counts_robust_within_the_bin():
    recs = [_rec(f_pk=1.30e9, corner_pass=(False, True, True)),   # margin .056
            _rec(f_pk=1.77e9),                                     # margin .500
            _rec(f_pk=1.77e9, tt_pass=False)]                      # excluded
    rows = margin_table(recs, [0.0, 0.1, 0.6])
    assert [r.n for r in rows] == [1, 1]
    assert [r.n_robust for r in rows] == [0, 1]


def test_threshold_table_is_cumulative_and_shrinks_the_kept_set():
    recs = [_rec(f_pk=1.30e9, corner_pass=(False, True, True)),
            _rec(f_pk=1.60e9),
            _rec(f_pk=1.77e9)]
    rows = threshold_table(recs, [0.0, 0.2, 0.45])
    assert [r.n for r in rows] == [3, 2, 1]
    assert rows[0].rate == pytest.approx(2 / 3)
    assert rows[-1].rate == pytest.approx(1.0)


def test_failure_edge_split_puts_a_high_peak_killed_by_ff_in_the_right_cell():
    ff_j = [j for j, c in enumerate(SCREEN_CORNERS) if c.process == "ff"][0]
    cp = [True, True, True]
    cp[ff_j] = False
    high = _rec(f_pk=2.4e9, corner_pass=tuple(cp))
    split = failure_edge_split([high])
    assert split["high_fast"] == 1
    assert split["low_fast"] == 0 and split["high_slow"] == 0


def test_failure_edge_split_puts_a_low_peak_killed_by_ss_in_the_right_cell():
    ss_js = [j for j, c in enumerate(SCREEN_CORNERS) if c.process == "ss"]
    cp = [True, True, True]
    cp[ss_js[0]] = False
    low = _rec(f_pk=1.3e9, corner_pass=tuple(cp))
    assert failure_edge_split([low])["low_slow"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# the CSV, which is the committed artifact the write-up is checkable against
# ─────────────────────────────────────────────────────────────────────────────


def test_csv_roundtrips_every_field_exactly(tmp_path):
    """`repr(float)` is used rather than a format string so the CSV is a
    LOSSLESS record. A rounded CSV would quietly move medians in the last
    reported digit and there would be no way to tell."""
    recs = [_rec(idx=3, f_pk=1.234567890123e9, rs=137.913572468),
            _rec(idx=9, corner_pass=(True, False, True), tt_pass=True)]
    p = tmp_path / "d.csv"
    save_csv(recs, p)
    back = load_csv(p)
    assert len(back) == 2
    for a, b in zip(recs, back):
        assert a.idx == b.idx
        assert a.params == b.params
        assert a.tt_pass == b.tt_pass
        assert a.corner_pass == b.corner_pass
        assert a.measured["f_pk_hz"] == b.measured["f_pk_hz"]
        assert a.robust == b.robust and a.fragile == b.fragile


def test_the_committed_dataset_is_present_and_reproduces_the_published_counts():
    """The dataset is tracked in git precisely so this test can exist without a
    simulator. If it is ever regenerated and the counts move, this goes red."""
    recs = load_csv()
    assert check_reproduction(recs) == []


def test_the_committed_dataset_matches_the_seeded_population_design_for_design():
    """Guards against the dataset being from a different box, seed or `cl` pin —
    the failure mode that would make every statistic in the write-up describe
    some other experiment's designs."""
    recs = load_csv()
    designs = population()
    assert len(recs) == len(designs)
    for r, d in zip(recs, designs):
        for name in PROPOSED_BOX:
            assert r.params[name] == pytest.approx(d[name], rel=1e-12)
