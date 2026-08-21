"""test_search_score.py — gates on the unclipped SEARCH ranking (`search_score`).

**None of these runs ngspice.** The transform is pure arithmetic over
`reward_v1.shortfalls`, which is the point: the defect it fixes was found, and is
pinned here, without a single simulation.

The file is organised around the three properties `search_score`'s docstring
claims, because a claim in a docstring that no test can fail is decoration:

1. order-identical to the clipped reward wherever the clip never bites;
2. strictly monotone past the clip -- the gradient the plateau removed;
3. band-safe, so the search can never prefer an INVALID design to a measurable
   one (G107).

Plus a regression that pins the ORIGINAL DEFECT rather than only the fix: the
clipped reward really does tie a 10.303 GHz peak with a legal 2.500 GHz one. If
someone later "fixes" `reward_v1` upstream, that test fails and tells them this
wrapper has become redundant, instead of leaving two corrections stacked.
"""

from __future__ import annotations

import math

import pytest

import nebula.rl.reward_v1 as R
from nebula.experiments import search_score as SS

N6 = len(R.V6_SPECS)


# ─────────────────────────────────────────────────────────────────────────────
# Property 1 — the near-feasible region is untouched.
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("v", [0.0, 1e-12, 0.031, 0.25, 0.5, 0.75, 0.999, 1.0])
def test_row_penalty_is_bit_identical_to_the_clip_below_one_tolerance(v):
    """**Exact**, not approximate: `log1p(0.0)` is `0.0`.

    This is the safety property. Every one of the eight requests the sweep
    already solves lives in this region, so the fix provably cannot disturb them.
    """
    assert SS.row_penalty(v) == min(v, 1.0)


def test_search_spec_reward_is_a_positive_rescaling_of_the_clipped_sum_below_one():
    """Below one tolerance the two scores differ by ONE constant factor.

    A single positive constant cannot reorder anything, which is the whole
    argument that this fix is safe on the requests that already work -- so it is
    asserted rather than reasoned about.
    """
    rows = dict(zip(R.V6_SPECS, [0.4, 0.9, 0.0, 0.15, 0.6] + [0.0] * (N6 - 5)))
    clipped = -sum(min(v, 1.0) for v in rows.values())
    assert SS.search_spec_reward(rows) == pytest.approx(
        clipped / SS.SEARCH_ROW_CAP, rel=0, abs=1e-15)


def test_ordering_below_one_tolerance_matches_the_clipped_reward_exactly():
    """Order-identity over a grid of shortfall vectors, not one example."""
    import itertools

    cases = []
    for combo in itertools.product([0.0, 0.2, 0.55, 0.8, 1.0], repeat=3):
        rows = dict(zip(R.V6_SPECS, list(combo) + [0.0] * (N6 - 3)))
        cases.append((-sum(min(v, 1.0) for v in rows.values()),
                      SS.search_spec_reward(rows)))
    for (c_a, s_a), (c_b, s_b) in itertools.combinations(cases, 2):
        # Same strict ordering, and same ties.
        assert (c_a < c_b) == (s_a < s_b)
        assert (c_a == c_b) == (s_a == s_b)


# ─────────────────────────────────────────────────────────────────────────────
# Property 2 — the gradient the plateau removed.
# ─────────────────────────────────────────────────────────────────────────────


def test_row_penalty_is_strictly_increasing_past_the_clip():
    vs = [1.0, 1.5, 2.0, 2.833, 5.0, 9.643, 10.296, 12.833, 20.0]
    ps = [SS.row_penalty(v) for v in vs]
    assert all(b > a for a, b in zip(ps, ps[1:])), ps


def test_the_original_defect_is_real_and_the_fix_separates_it():
    """**The regression this module exists for**, in the units of the artifact.

    A 1.387 GHz request with `TOL["S3_f_peak_match"] = 0.30` octaves. A delivered
    peak at 10.303 GHz is 2.893 octaves off; a legal one at 2.500 GHz is 0.850
    off. `coverage_results_AFTER_seeding_fix.json` recorded four such runaways at
    `screen_reward` = exactly -2.0000.
    """
    tol = R.TOL["S3_f_peak_match"]
    tgt = 1.387e9
    v_legal = abs(math.log2(2.500e9 / tgt)) / tol
    v_runaway = abs(math.log2(10.303e9 / tgt)) / tol

    # Both are past one tolerance, so the CLIP TIES THEM. Pinning the defect.
    assert v_legal > 1.0 and v_runaway > 1.0
    assert min(v_legal, 1.0) == min(v_runaway, 1.0) == 1.0

    # Unclipped, the legal peak is strictly preferred. That is the gradient.
    assert SS.row_penalty(v_legal) < SS.row_penalty(v_runaway)


def test_two_runaways_at_different_distances_tie_clipped_and_separate_unclipped():
    """**The artifact's finding, reproduced end to end with both S3 rows live.**

    `coverage_results_AFTER_seeding_fix.json` recorded four out-of-window
    requests at `screen_reward` of **exactly -2.0000** across delivered errors of
    1.901, 2.386, 2.715 and 2.893 octaves. -2.0 is an integer because it is
    simply *two fully-saturated rows* -- `S3_f_peak_band` and `S3_f_peak_match` --
    and carries nothing about how far out the peak actually is.

    The band row is built from `reward_v1`'s own `_F_LO_OCT`/`_F_HI_OCT` rather
    than from a window rebuilt here, which is the thing rule 9 forbids and which
    a first draft of this test got wrong.
    """
    def rows(hz):
        f_oct = math.log2(hz / 2.5e9)
        d = dict.fromkeys(R.V6_SPECS, 0.0)
        d["S3_f_peak_match"] = (abs(math.log2(hz / 1.387e9))
                                / R.TOL["S3_f_peak_match"])
        band = min(f_oct - R._F_LO_OCT, R._F_HI_OCT - f_oct)
        d["S3_f_peak_band"] = max(0.0, -band / R.TOL["S3_f_peak_band"])
        return d

    near, far = rows(10.303e9), rows(11.800e9)
    clipped = lambda d: -sum(min(v, 1.0) for v in d.values())  # noqa: E731

    # Both rows saturated on both designs -> the exact integer the artifact holds.
    assert clipped(near) == clipped(far) == -2.0
    # Unclipped, the nearer runaway is strictly preferred. That is the gradient.
    assert SS.search_spec_reward(near) > SS.search_spec_reward(far)


def test_two_in_band_designs_off_target_also_tie_clipped():
    """The same plateau one row down, and this is the one that stalls a request.

    A peak at 2.500 GHz and one at 1.962 GHz are both INSIDE the window (band row
    met) and both miss a 1.387 GHz request by more than 0.30 octaves, so both
    score exactly -1.0 -- while being 0.35 octaves apart in truth.
    """
    def rows(hz):
        f_oct = math.log2(hz / 2.5e9)
        d = dict.fromkeys(R.V6_SPECS, 0.0)
        d["S3_f_peak_match"] = (abs(math.log2(hz / 1.387e9))
                                / R.TOL["S3_f_peak_match"])
        band = min(f_oct - R._F_LO_OCT, R._F_HI_OCT - f_oct)
        d["S3_f_peak_band"] = max(0.0, -band / R.TOL["S3_f_peak_band"])
        assert d["S3_f_peak_band"] == 0.0, f"{hz/1e9:.3f} GHz is out of band"
        return d

    hi, lo = rows(2.500e9), rows(1.962e9)
    clipped = lambda d: -sum(min(v, 1.0) for v in d.values())  # noqa: E731

    assert clipped(hi) == clipped(lo) == -1.0
    assert SS.search_spec_reward(lo) > SS.search_spec_reward(hi)


# ─────────────────────────────────────────────────────────────────────────────
# Property 3 — band safety. G107: "cannot be scored" is not "fails".
# ─────────────────────────────────────────────────────────────────────────────


def test_infeasible_scores_stay_inside_reward_v1s_infeasible_band():
    """`[-N, 0]`, so strictly above `headroom_band_top(N)` and `invalid_reward(N)`.

    **This is why the division by `ROW_CAP` exists.** An uncapped sum would send
    a badly infeasible design below the invalid floor and the search would start
    preferring unbuildable designs -- G107 committed on purpose.
    """
    worst = dict.fromkeys(R.V6_SPECS, 1e6)          # every row absurdly violated
    s = SS.search_spec_reward(worst)
    assert -N6 <= s <= 0.0
    assert s > R.headroom_band_top(N6)
    assert s > R.invalid_reward(N6)


def test_the_cap_is_inert_on_anything_this_box_can_produce():
    """The cap bounds the band; it must not be doing any ranking work.

    It saturates at ~21 tolerances = 6.33 octaves of frequency error. The widest
    miss ever observed in this project is 3.09 octaves.
    """
    v_cap = math.exp((SS.SEARCH_ROW_CAP - 1.0) / SS.SEARCH_TAIL_W) + 1.0
    assert v_cap * R.TOL["S3_f_peak_match"] > 2.0 * 3.09
    assert SS.row_penalty(3.09 / R.TOL["S3_f_peak_match"]) < SS.SEARCH_ROW_CAP


@pytest.mark.parametrize("bad", [-1e-9, -1.0, float("nan"), float("inf")])
def test_row_penalty_raises_on_a_shortfall_that_cannot_be_one(bad):
    """A shortfall is `max(0, ...)` and finite. Anything else is a caller bug.

    Raising beats absorbing: the repo's second named failure mode is a wrong
    value that formats cleanly (G112).
    """
    with pytest.raises(ValueError):
        SS.row_penalty(bad)


def test_search_spec_reward_raises_on_an_empty_spec_set():
    with pytest.raises(ValueError):
        SS.search_spec_reward({})


# ─────────────────────────────────────────────────────────────────────────────
# The band pass-throughs, on real `RewardBreakdown`s.
# ─────────────────────────────────────────────────────────────────────────────


def _rb(**kw):
    base = dict(reward=0.0, feasible=False, valid=True, headroom_only=False,
                spec_reward=0.0, cost_penalty=0.0, margins={}, shortfalls={},
                worst_spec=None, n_violated=0)
    base.update(kw)
    return R.RewardBreakdown(**base)


def test_feasible_headroom_and_invalid_pass_through_untouched():
    """Only the infeasible band moves. The ordering BETWEEN bands is reward_v1's."""
    feas = _rb(reward=R.feasible_bonus(N6) + 0.3, feasible=True)
    head = _rb(reward=R.headroom_band_top(N6) - 0.5, valid=False,
               headroom_only=True)
    inval = _rb(reward=R.invalid_reward(N6), valid=False, n_violated=N6)
    for rb in (feas, head, inval):
        assert SS.score_breakdown(rb) == rb.reward


def test_an_infeasible_breakdown_moves_and_keeps_its_cost_penalty():
    s = dict.fromkeys(R.V6_SPECS, 0.0)
    s["S3_f_peak_match"] = 9.643
    rb = _rb(reward=-1.0 - 0.25, spec_reward=-1.0, cost_penalty=0.25,
             shortfalls=s, n_violated=1)
    got = SS.score_breakdown(rb)
    assert got != rb.reward
    assert got == pytest.approx(SS.search_spec_reward(s) - 0.25)


# ─────────────────────────────────────────────────────────────────────────────
# `score_margins` — the G101/G106 shape: a set that loses members silently.
# ─────────────────────────────────────────────────────────────────────────────


def test_score_margins_returns_none_when_a_spec_row_is_missing():
    """**Never rank on a partial spec set.**

    A score computed from 9 of 13 rows is systematically higher than one computed
    from all 13, so mixing them builds an objective that rewards NOT BEING
    MEASURED -- the defect `PROGRESS.md` §6 records the spread probe hitting.
    """
    full = {k: -1.0 for k in R.V6_SPECS}
    assert SS.score_margins(full, R.V6_SPECS) is not None
    partial = dict(full)
    partial.pop("S5_noise")
    assert SS.score_margins(partial, R.V6_SPECS) is None


def test_score_margins_returns_none_when_every_row_is_met():
    """A feasible point needs `feasible_bonus`, which a shortfall sum cannot give.

    Returning `None` sends the caller to the real reward rather than inventing a
    number in the wrong band.
    """
    met = {k: +1.0 for k in R.V6_SPECS}
    assert SS.score_margins(met, R.V6_SPECS) is None


# ─────────────────────────────────────────────────────────────────────────────
# `score_design_eval` — worst point by the UNCLIPPED score.
# ─────────────────────────────────────────────────────────────────────────────


class _Pt:
    def __init__(self, label, ok=True, reward=0.0, feasible=False, margins=None):
        self.label, self.ok, self.reward = label, ok, reward
        self.feasible, self.margins = feasible, (margins or {})


class _Ev:
    def __init__(self, ok=True, reward=0.0, points=(), margins=None):
        self.ok, self.reward = ok, reward
        self.points, self.margins = list(points), (margins or {})


def _margins_for(f_oct_miss, other_miss=0.0):
    """Margins where `S3_f_peak_match` misses by `f_oct_miss` tolerances."""
    m = {k: +1.0 for k in R.V6_SPECS}
    m["S3_f_peak_match"] = -f_oct_miss * R.TOL["S3_f_peak_match"]
    if other_miss:
        m["S5_noise"] = -other_miss * R.TOL["S5_noise"]
    return m


def test_an_unscorable_design_passes_through_as_the_floor():
    """G107. Re-ranking the graded invalid band would kill the search or fake a pass.

    **The eval must carry real margins for this to gate anything**, and it does in
    production: `evaluate_at_points`'s unscorable branch sets
    `margins=(worst.margins if worst else {})`, so a design whose eye failed to
    compute at one corner still arrives here with a complete margin set from the
    corners that DID score. A first draft of this test passed an eval with empty
    margins and therefore passed for the wrong reason -- it went green with the
    `ok` guard deleted.

    Without the guard this design would be re-ranked into the infeasible band
    (about -0.2) instead of the invalid floor (-15.5), and the search would then
    prefer an UNBUILDABLE design to every measurable one.
    """
    good = _Pt("scored", reward=-0.8, margins=_margins_for(1.2))
    dead = _Pt("dead", ok=False, reward=0.0)
    ev = _Ev(ok=False, reward=R.invalid_reward(N6) + 0.5,
             points=[good, dead], margins=good.margins)

    assert SS.score_design_eval(ev, R.V6_SPECS) == ev.reward
    # And that floor is genuinely below what the infeasible path would have given.
    assert ev.reward < SS.search_spec_reward(
        R.shortfalls(good.margins, R.V6_SPECS))
    assert ev.reward < R.headroom_band_top(N6)


def test_the_worst_point_is_re_selected_by_the_unclipped_score():
    """**This is a second defect fixed by the same change.**

    `DesignEval` picked its worst point with `pr.reward < worst.reward` -- the
    clipped number. With two points both fully saturated the choice was whichever
    tied first, i.e. arbitrary. Here point B is far worse in truth but both read
    -1.0 clipped, so the design's rank score must come from B.
    """
    a = _Pt("A", reward=-1.0, margins=_margins_for(2.833))
    b = _Pt("B", reward=-1.0, margins=_margins_for(9.643))
    assert a.reward == b.reward                       # the clipped tie
    ev = _Ev(reward=-1.0, points=[a, b], margins=a.margins)
    got = SS.score_design_eval(ev, R.V6_SPECS)
    assert got == pytest.approx(
        SS.search_spec_reward(R.shortfalls(b.margins, R.V6_SPECS)))
    assert got < SS.search_spec_reward(R.shortfalls(a.margins, R.V6_SPECS))


def test_a_feasible_point_never_drags_the_design_score_up():
    """min over points: one compliant corner cannot hide a failing one."""
    good = _Pt("good", reward=R.feasible_bonus(N6) + 0.2, feasible=True)
    bad = _Pt("bad", reward=-1.0, margins=_margins_for(9.643))
    ev = _Ev(reward=-1.0, points=[good, bad], margins=bad.margins)
    assert SS.score_design_eval(ev, R.V6_SPECS) < 0.0


def test_falls_back_to_the_verdict_when_no_point_detail_survives():
    ev = _Ev(ok=True, reward=-2.0, points=[], margins={})
    assert SS.score_design_eval(ev, R.V6_SPECS) == -2.0


def test_skips_points_that_were_not_scorable():
    bad = _Pt("dead", ok=False, reward=-99.0)
    live = _Pt("live", reward=-1.0, margins=_margins_for(2.833))
    ev = _Ev(reward=-1.0, points=[bad, live], margins=live.margins)
    got = SS.score_design_eval(ev, R.V6_SPECS)
    assert got == pytest.approx(
        SS.search_spec_reward(R.shortfalls(live.margins, R.V6_SPECS)))
    assert got > -99.0


# ─────────────────────────────────────────────────────────────────────────────
# `RankView` — one field, deliberately.
# ─────────────────────────────────────────────────────────────────────────────


def test_rankview_carries_the_scalar_and_refuses_everything_else():
    """A shim that proxied `feasible` would let a caller read the SEARCH's
    opinion where they meant the VERDICT. Failing loudly is the requirement."""
    rv = SS.RankView(reward=-0.5)
    assert rv.reward == -0.5
    for attr in ("feasible", "margins", "u", "ok", "worst_spec"):
        assert not hasattr(rv, attr), attr


def test_method_cmaes_reads_only_the_attribute_rankview_provides():
    """Pins the coupling this design depends on, in `baselines.py`'s own source.

    If someone makes `method_cmaes` read `.feasible` or `.u`, `RankView` starts
    raising `AttributeError` mid-search. This test fails first and says why.
    """
    import inspect

    from nebula.experiments import baselines as B

    src = inspect.getsource(B.method_cmaes)
    assert "obj.evaluate(X[i]).reward" in src, (
        "method_cmaes no longer reads .reward from the objective's return value; "
        "search_score.RankView must be revisited")
    for attr in (".feasible", ".margins", ".worst_spec"):
        assert f"obj.evaluate(X[i]){attr}" not in src


# ─────────────────────────────────────────────────────────────────────────────
# The seam into the coverage sweep.
# ─────────────────────────────────────────────────────────────────────────────


def test_objective_ranks_on_the_unclipped_score_and_reports_the_clipped_one():
    """**No SPICE**: `evaluate_at_points` is monkeypatched with two fixed designs.

    The design that is better on the clipped score must LOSE, because it is worse
    once the clip is removed. And `best` must still be the real `DesignEval`, so
    `screen_reward` continues to report `reward_v1`'s verdict.
    """
    from nebula.experiments import exp_coverage as C

    a = _Pt("p", reward=-1.0, margins=_margins_for(9.643))       # runaway
    b = _Pt("p", reward=-1.0, margins=_margins_for(2.833, other_miss=0.10))
    evs = [_Ev(reward=-1.0, points=[a], margins=a.margins),
           _Ev(reward=-1.10, points=[b], margins=b.margins)]
    for e in evs:
        e.u, e.n_sims, e.feasible = (0.5,) * 7, 4, False
        e.worst_point = e.worst_spec = None
        e.peaking_db = e.f_peak_hz = e.reason = None

    calls = iter(evs)
    orig = C.evaluate_at_points
    try:
        C.evaluate_at_points = lambda *a, **k: next(calls)
        obj = C._Objective(_Screen(), 1.387e9, 8.0, 10, None)
        obj.evaluate([0.5] * 7)
        obj.evaluate([0.5] * 7)
    finally:
        C.evaluate_at_points = orig

    # The runaway reads BETTER clipped (-1.00 vs -1.10) and must still lose.
    assert evs[0].reward > evs[1].reward
    assert obj.best is evs[1]
    assert obj.best.reward == -1.10          # the verdict, unchanged
    assert obj.best_score < 0.0
    assert obj.best_score != obj.best.reward


def test_objective_with_rank_unclipped_false_reproduces_the_old_behaviour():
    """The switch is real, so the two regimes are comparable by measurement."""
    from nebula.experiments import exp_coverage as C

    a = _Pt("p", reward=-1.0, margins=_margins_for(9.643))
    b = _Pt("p", reward=-1.0, margins=_margins_for(2.833, other_miss=0.10))
    evs = [_Ev(reward=-1.0, points=[a], margins=a.margins),
           _Ev(reward=-1.10, points=[b], margins=b.margins)]
    for e in evs:
        e.u, e.n_sims, e.feasible = (0.5,) * 7, 4, False
        e.worst_point = e.worst_spec = None
        e.peaking_db = e.f_peak_hz = e.reason = None

    calls = iter(evs)
    orig = C.evaluate_at_points
    try:
        C.evaluate_at_points = lambda *a, **k: next(calls)
        obj = C._Objective(_Screen(), 1.387e9, 8.0, 10, None,
                           rank_unclipped=False)
        obj.evaluate([0.5] * 7)
        obj.evaluate([0.5] * 7)
    finally:
        C.evaluate_at_points = orig

    assert obj.best is evs[0]                # the clipped winner, as before
    assert obj.best_score == -1.0


class _Screen:
    points = ("edge0", "edge1", "edge2", "edge3")
