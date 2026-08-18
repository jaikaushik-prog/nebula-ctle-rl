"""
Tests for `experiments/exp_difficulty.py` — task 0's difficulty measurement.

**None of these runs ngspice.** The device layer is stubbed through
`monkeypatch`, exactly as `test_baselines.py` does and for the same reason:
these tests are about the ACCOUNTING and the DECISION RULE, not about circuits.

Four of them are gates in CLAUDEwa.md §8 rule 10's sense — they exist to fail
if a rule is quietly relaxed, and each was checked by deliberately breaking its
input and watching it go red (PLAN.md §7 rule 3):

  * `test_the_restart_loop_matches_method_lhs_exactly` — the claim that this
    experiment changes NOTHING about the problem definition. Break the block
    size in `lhs_stream` and it goes red.
  * `test_censored_restarts_are_never_substituted` — a censored waiting time
    stays `None`; the budget is not written in its place.
  * `test_the_decision_rule_is_the_pre_registered_one` — the verdict is read
    off the medians by the rule in `PREDICTIONS.md` entry 7.
  * `test_a_screened_out_proposal_costs_zero_simulations_and_one_proposal` —
    G65's cost definition, on the arm that could hide a cost.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pytest

from nebula.experiments import baselines as B
from nebula.experiments import exp_difficulty as D
from nebula.experiments import prescreen as PS
from nebula.rl import reward_v1 as R
from nebula.common.types import SPEC_F_PEAK_HZ_RANGE
from nebula.rl.contract import N_ACTIONS, f_peak_octaves
from nebula.rl.evaluator import Verdict


# ─────────────────────────────────────────────────────────────────────────────
# The same stub `test_baselines.py` uses. One definition of "a fake device"
# would be better still, but importing a test module from a test module is
# worse; this is copied deliberately and says so.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class _StubResult:
    verdict: Verdict
    reason: Optional[str]
    meas: Optional[dict]
    headroom: Optional[dict]
    design_id: str = "stub"
    geometry_tag: str = "stub"
    n_spice: int = 1
    seconds: float = 0.0
    #: `EvalResult` has always had this; the stub went without it until
    #: `Objective` started reading `raw['peak_interp_status']` (session 22e).
    #: Named here rather than defended against with `getattr` in the production
    #: path -- a double that silently lacks a field the real object has fails
    #: wherever the caller happens to touch it, not at the seam it stands in for.
    raw: dict = field(default_factory=dict)

    @property
    def valid(self) -> bool:
        return self.verdict is Verdict.VALID


#: The `f_peak_oct` a design scoring EXACTLY the AC-grid ceiling reports.
#: **Derived, not typed in:** the target's own octave coordinate plus
#: `nearest_grid_offset_octaves`, so if the grid or the target ever moves this
#: follows rather than silently pinning a stale number (rule 9).
_CEILING_F_PEAK_OCT: float = (
    f_peak_octaves(math.sqrt(SPEC_F_PEAK_HZ_RANGE[0] * SPEC_F_PEAK_HZ_RANGE[1]))
    + B.nearest_grid_offset_octaves(
        math.sqrt(SPEC_F_PEAK_HZ_RANGE[0] * SPEC_F_PEAK_HZ_RANGE[1])))


def _good_meas(f_peak_oct: float = _CEILING_F_PEAK_OCT) -> dict:
    """A design that meets every V1 spec. `f_peak_oct` is the tuning knob.

    At the default it scores the ceiling: `S3_f_peak` binds at the nearest
    lattice point and every other margin/tol is >= 0.95.
    """
    return {"g_dc_db": 5.0, "peaking_db": 7.5, "f_peak_oct": f_peak_oct,
            "nyq_boost_db": 6.0, "inoise_vrms": 2e-4, "power_w": 5e-3,
            "pair_margin_v": 0.26, "tail_margin_v": 0.33}


def _stub(monkeypatch, pattern):
    calls = {"n": 0}

    def _fake_evaluate(sizing, budget, corner="tt", temp_c=27.0,
                       vdd_scale=1.0, keep_raw_text=False,
                       ac_peak_interp=False):
        # The stub tracks the REAL signature by name rather than swallowing
        # `**kw`: a keyword the harness starts passing and the stub silently
        # absorbs is a threading bug that no test can see. `ac_peak_interp`
        # is recorded so a test can assert `Objective` passes it through.
        calls["n"] += 1
        calls["ac_peak_interp"] = bool(ac_peak_interp)
        r = pattern(calls["n"])
        budget.charge(r.n_spice, 0.0)
        return r

    monkeypatch.setattr(B, "evaluate", _fake_evaluate)
    return calls


@pytest.fixture
def stub_at_ceiling(monkeypatch):
    """Every evaluation lands exactly on the nearest AC grid point."""
    return _stub(monkeypatch,
                 lambda n: _StubResult(Verdict.VALID, None, _good_meas(), {}))


@pytest.fixture
def stub_never_feasible(monkeypatch):
    """Every evaluation is invalid, and still costs one simulation (G65)."""
    return _stub(monkeypatch,
                 lambda n: _StubResult(Verdict.INVALID,
                                       "the reported peak IS the sweep edge: "
                                       "f_pk 1.9e10", None, None))


# ─────────────────────────────────────────────────────────────────────────────
# THE GATE: this experiment must not change the problem definition.
# ─────────────────────────────────────────────────────────────────────────────


def test_the_restart_loop_matches_method_lhs_exactly(stub_at_ceiling):
    """`lhs_stream` proposes what `baselines.method_lhs` proposes, draw for draw.

    The whole argument of task 0 is that it measures the EXISTING problem with
    the EXISTING sampler. If the block size, the continuation rule or the
    generator's consumption order drifted, this experiment would be measuring a
    different search and would say nothing about the sweep.

    **Proven able to fail:** changing `lhs_stream`'s block size to `n + 1`
    turns this red on the first block boundary.
    """
    budget = 37
    seen: list[np.ndarray] = []

    def record(tr):
        seen.append(np.asarray(tr.u, dtype=float))

    ref = B.Objective(B.PROBLEMS["P1"], budget_sims=budget, on_trial=record)
    with pytest.raises(B.BudgetExhausted):
        B.method_lhs(ref, np.random.default_rng(4242))
    reference = list(seen)

    seen.clear()
    obj = D.Objective(B.PROBLEMS["P1"], budget_sims=budget, on_trial=record)
    rng = np.random.default_rng(4242)
    try:
        for row in D.lhs_stream(obj, rng):
            obj.check_budget()
            obj.evaluate(row)
    except B.BudgetExhausted:
        pass

    assert len(seen) == len(reference) > budget - 2
    for a, b in zip(seen, reference):
        np.testing.assert_array_equal(a, b)


def test_the_arms_differ_only_by_the_prescreen_flag(stub_at_ceiling,
                                                    monkeypatch):
    """Same box, same evaluator, same target, same problem rung on both arms."""
    monkeypatch.setattr(PS, "screen",
                        lambda p, **kw: PS.ScreenVerdict(True, None, None))
    a = D.run_restart("unscreened", 0, budget_sims=3, stop_at_ceiling=False)
    b = D.run_restart("screened", 0, budget_sims=3, stop_at_ceiling=False)
    assert a["reward_ceiling"] == b["reward_ceiling"]
    # An accept-everything screen must cost the screened arm nothing.
    assert b["n_screened_out"] == 0
    assert a["n_sims"] == b["n_sims"]


# ─────────────────────────────────────────────────────────────────────────────
# THE GATE: cost accounting (G65 — every ngspice invocation counted).
# ─────────────────────────────────────────────────────────────────────────────


def test_a_screened_out_proposal_costs_zero_simulations_and_one_proposal(
        stub_at_ceiling, monkeypatch):
    """The screened arm's saving is real, and its proposal count records it.

    A screen that rejects everything must spend no simulations — and must not
    thereby look like an arm that "solved the problem in zero simulations". The
    run comes back CENSORED on every metric, with the proposals it spent
    visible beside the zero.

    **Proven able to fail:** returning `n_sims=1` from the screened branch of
    `Objective.evaluate` turns the first assertion red.
    """
    monkeypatch.setattr(PS, "screen",
                        lambda p, **kw: PS.ScreenVerdict(False, "no", None))
    r = D.run_restart("screened", 0, budget_sims=5, max_proposals=50)
    assert r["n_sims"] == 0 and stub_at_ceiling["n"] == 0
    assert r["n_screened_out"] == r["n_proposals"] > 0
    assert r["censored_ceiling"] and r["censored_s3"] and r["censored_feasible"]
    assert r["sims_to_ceiling"] is None


def test_a_screen_that_rejects_everything_terminates_and_says_so(
        stub_at_ceiling, monkeypatch):
    """A simulation budget alone does not terminate a screened arm.

    Found by this test suite hanging: a screened rejection costs zero
    simulations by design, so `n_sims` never advances and the loop runs
    forever at full CPU, reporting nothing. The proposal cap is the second
    termination condition and hitting it is RECORDED, so it cannot be read as
    "the arm searched properly and found nothing".

    **Proven able to fail:** removing the `len(obj.trials) >= cap` break makes
    this test hang rather than go red, which is exactly why the flag is logged
    — a silent non-termination is worse than a loud one.
    """
    monkeypatch.setattr(PS, "screen",
                        lambda p, **kw: PS.ScreenVerdict(False, "no", None))
    r = D.run_restart("screened", 0, budget_sims=5, max_proposals=40)
    assert r["proposal_cap_hit"] is True
    assert r["n_proposals"] == 40 and r["n_sims"] == 0
    p = D.run_pool("screened", pool_sims=5, max_proposals=40)
    assert p["proposal_cap_hit"] is True and p["n_simulated"] == 0
    # The default cap is generous against the MEASURED screen (61.7 % free
    # rejection, ~2.6 proposals per simulation), so it cannot bind by accident.
    assert D.PROPOSAL_CAP_FACTOR >= 10
    assert D.run_restart("unscreened", 0, budget_sims=3)["proposal_cap_hit"] is False


def test_an_invalid_design_still_costs_its_simulation(stub_never_feasible):
    r = D.run_restart("unscreened", 0, budget_sims=6)
    assert r["n_sims"] >= 6 and stub_never_feasible["n"] >= 6
    assert r["censored_ceiling"] and r["invalid_rate"] == pytest.approx(1.0)


# ─────────────────────────────────────────────────────────────────────────────
# THE GATE: censored data is never substituted (BASELINES.md §3 / 7c).
# ─────────────────────────────────────────────────────────────────────────────


def test_censored_restarts_are_never_substituted():
    """Three numbers and never one, and the budget is not one of them.

    **Proven able to fail:** substituting `budget_sims` for a `None` in
    `censored_summary` makes `n_censored` 0 and drags the median to 200.
    """
    runs = [{"sims_to_ceiling": 10}, {"sims_to_ceiling": 20},
            {"sims_to_ceiling": None}, {"sims_to_ceiling": None}]
    c = D.censored_summary(runs, "sims_to_ceiling")
    assert c["n_runs"] == 4 and c["n_reached"] == 2 and c["n_censored"] == 2
    assert c["reached_fraction"] == 0.5
    assert c["median_conditional"] == pytest.approx(15.0)
    assert c["values"] == [10, 20]
    # The budget never appears, in any field.
    assert 600 not in c["values"]


def test_a_fully_censored_metric_has_no_median():
    c = D.censored_summary([{"k": None}] * 5, "k")
    assert c["n_reached"] == 0 and c["median_conditional"] is None
    assert c["ci90_lo"] is None and c["ci90_hi"] is None


def test_the_ci_is_a_ninety_percent_band_not_the_helpers_default_ninety_five():
    """The brief asks for 90 %; `bootstrap_median` defaults to 95 %.

    **Proven able to fail:** dropping the `alpha=alpha` argument in
    `censored_summary` makes the band the helper's 95 % and this goes red,
    because a 95 % band is strictly wider than a 90 % one on the same draws.
    """
    raw = list(range(1, 41))
    c90 = D.censored_summary([{"k": v} for v in raw], "k", alpha=0.10, seed=0)
    _, lo95, hi95 = B.bootstrap_median(raw, alpha=0.05,
                                       rng=np.random.default_rng(0))
    assert c90["ci90_hi"] - c90["ci90_lo"] < hi95 - lo95


# ─────────────────────────────────────────────────────────────────────────────
# THE GATE: the decision rule is the pre-registered one.
# ─────────────────────────────────────────────────────────────────────────────


def test_the_decision_rule_is_the_pre_registered_one():
    """`< 50` -> thesis holds; `> 500` in every arm -> it does not; else stop.

    **Proven able to fail:** moving `DECISION_LO` to 5 flips the first case to
    `in_between`.
    """
    assert D.DECISION_LO == 50 and D.DECISION_HI == 500
    assert D.decide({"unscreened": 8.0, "screened": 3.0})["verdict"] == "thesis_holds"
    # One arm below the line is enough — the brief says "in either arm".
    assert D.decide({"unscreened": 900.0, "screened": 12.0})["verdict"] == "thesis_holds"
    assert D.decide({"unscreened": 900.0, "screened": 700.0})["verdict"] == "thesis_fails"
    assert D.decide({"unscreened": 120.0, "screened": 60.0})["verdict"] == "in_between"
    # A censored arm is NOT evidence for the thesis: it cannot be < 50.
    assert D.decide({"unscreened": 900.0, "screened": None})["verdict"] == "in_between"
    assert D.decide({"unscreened": None, "screened": None})["verdict"] == "undecided"


# ─────────────────────────────────────────────────────────────────────────────
# The two predicates, which are where a spec test could get reimplemented.
# ─────────────────────────────────────────────────────────────────────────────


def _trial(reward: float, margins, n_sims: int = 1) -> B.Trial:
    return B.Trial(index=0, u=[0.5] * N_ACTIONS, design_id="d", geometry_tag="g",
                   params={}, reward=reward, feasible=reward > 0,
                   verdict="valid", invalid_reason=None, worst_point=None,
                   worst_spec=None, n_sims=n_sims, seconds=0.0, cum_sims=n_sims,
                   cum_seconds=0.0, screened_out=False, screen_reason=None,
                   meas=None, margins=margins, predicted=None)


def test_meets_s3_reads_reward_v1s_own_margins_and_does_not_retest():
    assert D.S3_SPECS == R.V0_SPECS
    ok = {"S3_peaking": 0.1, "S3_f_peak": 0.0, "S3_nyq_boost": 3.0,
          "S5_noise": 1.0, "S6_power": 1.0}
    assert D.meets_s3(_trial(1.0, ok))
    bad = dict(ok, S3_f_peak=-1e-9)
    assert not D.meets_s3(_trial(1.0, bad))
    # No margins at all -- screened out or invalid -- is NOT an S3 pass.
    assert not D.meets_s3(_trial(-7.0, None))
    assert not D.meets_s3(_trial(-7.0, {}))


def test_at_ceiling_accepts_the_measured_value_and_rejects_a_hair_below():
    """G74: derived 8.950669295, measured 8.950670. Both must count.

    **Proven able to fail:** setting `CEILING_TOL = 0` rejects nothing here but
    would reject the measured 8.950670 in the other direction on a machine
    whose float arithmetic lands below; setting it to 1e-3 makes the
    hair-below case pass, which is the failure that matters.
    """
    c = D.reward_ceiling(math.sqrt(1.25e9 * 2.5e9))
    assert c == pytest.approx(8.950669, abs=1e-6)
    assert D.at_ceiling(_trial(8.950670, {}), c)
    assert D.at_ceiling(_trial(c, {}), c)
    assert not D.at_ceiling(_trial(c - 1e-3, {}), c)
    # A trial that cost no simulation cannot be at the ceiling, whatever it scored.
    assert not D.at_ceiling(_trial(c, {}, n_sims=0), c)


# ─────────────────────────────────────────────────────────────────────────────
# Seeds, provenance, and the analysis round-trip.
# ─────────────────────────────────────────────────────────────────────────────


def test_seed_protocol_is_a_stated_rule_and_collides_with_nothing():
    seen = set()
    for arm in D.ARM_OFFSET:
        for kind in D.KIND_OFFSET:
            for rep in range(200):
                s = D.run_seed(arm, kind, rep)
                assert s not in seen, f"seed collision at {arm}/{kind}/{rep}"
                seen.add(s)
    with pytest.raises(KeyError):
        D.run_seed("nope", "restart", 0)
    with pytest.raises(KeyError):
        D.run_seed("screened", "nope", 0)
    # ...and disjoint from the benchmark's own streams, so the two experiments
    # never share a random sequence by accident.
    other = {B.run_seed(p, m, r) for p in B.PROBLEM_OFFSET
             for m in B.METHOD_OFFSET for r in range(200)}
    assert not (seen & other)


def test_the_restart_count_meets_the_briefs_floor_of_twenty():
    assert D.RESTARTS >= 20


def test_analyse_round_trips_through_the_log(tmp_path, stub_at_ceiling,
                                             monkeypatch):
    """`--analyse` must rebuild the whole analysis from the streamed log.

    Session 18's pilot was killed one job from the end and every row survived
    because the log streams. That property is worth a test, not a paragraph.
    """
    monkeypatch.setattr(PS, "screen",
                        lambda p, **kw: PS.ScreenVerdict(True, None, None))
    log = tmp_path / "d.jsonl"
    out = D.run(restarts=2, budget_sims=3, pool_sims=4, arms=("unscreened",),
                log_path=log)
    again = D.analyse(D.load(log))
    assert again["decision"] == out["decision"]
    assert set(again["per_arm"]) == {"unscreened"}
    e = again["per_arm"]["unscreened"]
    assert e["n_restarts"] == 2
    assert e["pool"]["n_simulated"] > 0
    # The stub scores the ceiling on every design, so every restart reaches it
    # in one simulation and the pool's ties are all the same design.
    assert e["sims_to_ceiling"]["median_conditional"] == pytest.approx(1.0)
    assert e["pool"]["n_distinct_at_ceiling"] == 1


def test_the_log_header_pins_the_evaluator_and_the_seed_rule(tmp_path,
                                                             stub_at_ceiling,
                                                             monkeypatch):
    monkeypatch.setattr(PS, "screen",
                        lambda p, **kw: PS.ScreenVerdict(True, None, None))
    log = tmp_path / "d.jsonl"
    D.run(restarts=1, budget_sims=2, pool_sims=2, arms=("unscreened",),
          log_path=log)
    import json
    head = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    assert head["kind"] == "header"
    assert head["base_seed"] == D.BASE_SEED
    assert "seed_rule" in head and "box" in head and "library" in head
    assert head["specs"] == list(R.V1_SPECS)


# ─────────────────────────────────────────────────────────────────────────────
# G89 — does the pre-screen discard CEILING-capable designs?
# ─────────────────────────────────────────────────────────────────────────────


def test_the_ceiling_ratio_is_measured_per_PROPOSAL_not_per_simulation():
    """The statistic must be on the axis a screen can actually bias.

    A screen only REMOVES proposals, so absent bias both arms must show the
    same ceiling rate PER PROPOSAL. The per-SIMULATION rate cannot answer the
    question, because raising that one is what the screen is for — reading it
    instead would "confirm" the screen is helping in exactly the case where it
    is throwing good designs away.

    **Proven able to fail:** switching `ceiling_rate_ratio` to `n_sims` makes
    the ratio 1.78 (the screen looks purely beneficial) instead of 0.535, and
    the ordering assertion below goes red.
    """
    pools = [
        {"arm": "unscreened", "n_at_ceiling": 9, "n_proposals": 2000,
         "n_sims": 2000},
        {"arm": "screened", "n_at_ceiling": 16, "n_proposals": 6645,
         "n_sims": 2000},
    ]
    rr = D.ceiling_rate_ratio(pools)
    assert rr["rate_unscreened"] == pytest.approx(0.0045)
    assert rr["rate_screened"] == pytest.approx(16 / 6645)
    assert rr["ratio"] == pytest.approx(0.535, abs=1e-3)
    assert rr["ratio"] < 1.0, "per-simulation would give 1.78 and hide the bias"
    assert rr["implied_false_rejection"] == pytest.approx(0.465, abs=1e-3)


def test_the_ratio_reports_whether_its_interval_excludes_one():
    """A CI spanning 1.0 is NOT a finding, and the code has to say so.

    This is the whole reason G89 is recorded as a suspicion. The flag is what
    stops the point estimate being quoted on its own.
    """
    wide = D.ceiling_rate_ratio([
        {"arm": "unscreened", "n_at_ceiling": 9, "n_proposals": 2000},
        {"arm": "screened", "n_at_ceiling": 16, "n_proposals": 6645}])
    assert wide["excludes_one"] is False
    lo, hi = wide["ci95"]
    assert lo < 1.0 < hi

    # Same rates, ~6x the events: the interval must tighten and exclude 1.
    tight = D.ceiling_rate_ratio([
        {"arm": "unscreened", "n_at_ceiling": 54, "n_proposals": 12000},
        {"arm": "screened", "n_at_ceiling": 96, "n_proposals": 39870}])
    assert tight["ratio"] == pytest.approx(wide["ratio"], abs=1e-6)
    assert tight["excludes_one"] is True
    assert tight["ci95"][1] < 1.0


def test_a_zero_event_count_is_undefined_rather_than_zero():
    """`log(0)` is not a rate ratio, and 0.0 would read as total rejection."""
    rr = D.ceiling_rate_ratio([
        {"arm": "unscreened", "n_at_ceiling": 5, "n_proposals": 1000},
        {"arm": "screened", "n_at_ceiling": 0, "n_proposals": 3000}])
    assert rr["ratio"] is None and "undefined" in rr["note"]


def test_more_pools_uses_a_fresh_seed_so_counts_may_be_added(stub_at_ceiling,
                                                             monkeypatch):
    """Replicate 1 must not redraw replicate 0's sample.

    Pooling counts by addition is only valid across INDEPENDENT samples; if the
    seed did not move, the second pool would be the first one again and the
    interval would tighten around a number that never gained evidence.
    """
    monkeypatch.setattr(PS, "screen",
                        lambda p, **kw: PS.ScreenVerdict(True, None, None))
    a = D.run_pool("unscreened", pool_sims=3, replicate=0)
    b = D.run_pool("unscreened", pool_sims=3, replicate=1)
    assert a["seed"] != b["seed"]
    assert a["replicate"] == 0 and b["replicate"] == 1
    assert D.run_seed("unscreened", "pool", 1) == b["seed"]
