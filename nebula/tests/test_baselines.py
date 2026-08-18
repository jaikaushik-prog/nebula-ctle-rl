"""
Tests for `experiments/baselines.py` — task 7's benchmark harness.

**None of these runs ngspice.** The device layer is replaced by a stub through
`monkeypatch`, which is the only way to test the FAIRNESS rules — that every
simulation is counted, that a budget stops every method, that the pre-screen
spends nothing on a rejected design — without spending an hour per test run.
The stub is deliberately crude: none of these tests is about circuits.

Three of them are gates in CLAUDEwa.md §8 rule 10's sense, i.e. they exist to
fail if a rule is quietly relaxed:

  * `test_every_simulation_is_counted_including_invalid_ones` (7f rule 1)
  * `test_censored_table_never_substitutes_the_budget`        (7c)
  * `test_reward_ceiling_matches_the_ac_grid`                 (the finding that
    the primary metric saturates on P1, pinned so it cannot be forgotten)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pytest

from nebula.common.types import SPEC_F_PEAK_HZ_RANGE
from nebula.experiments import baselines as B
from nebula.experiments import prescreen as PS
from nebula.rl import reward_v1 as R
from nebula.rl.contract import N_ACTIONS
from nebula.rl.evaluator import Verdict


# ─────────────────────────────────────────────────────────────────────────────
# A stubbed device layer. Deterministic, cheap, and physically meaningless.
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

    @property
    def valid(self) -> bool:
        return self.verdict is Verdict.VALID


def _good_meas(f_peak_oct: float = -0.5247) -> dict:
    return {"g_dc_db": 5.0, "peaking_db": 7.5, "f_peak_oct": f_peak_oct,
            "nyq_boost_db": 6.0, "inoise_vrms": 2e-4, "power_w": 5e-3,
            "pair_margin_v": 0.26, "tail_margin_v": 0.33}


def _stub_factory(pattern):
    """`pattern(u, corner) -> _StubResult`, plus a call counter."""
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
        r = pattern(sizing, corner, calls["n"])
        budget.charge(r.n_spice, 0.0)
        return r

    return _fake_evaluate, calls


@pytest.fixture
def stub_valid(monkeypatch):
    """Every evaluation is a valid, feasible design at the reward ceiling."""
    fake, calls = _stub_factory(
        lambda s, c, n: _StubResult(Verdict.VALID, None, _good_meas(), {}))
    monkeypatch.setattr(B, "evaluate", fake)
    return calls


@pytest.fixture
def stub_invalid(monkeypatch):
    """Every evaluation is invalid, and still costs one simulation."""
    fake, calls = _stub_factory(
        lambda s, c, n: _StubResult(Verdict.INVALID,
                                    "the reported peak IS the sweep edge: "
                                    "f_pk 1.9e10", None, None))
    monkeypatch.setattr(B, "evaluate", fake)
    return calls


# ─────────────────────────────────────────────────────────────────────────────
# 7b — the ladder.
# ─────────────────────────────────────────────────────────────────────────────


def test_the_ladder_has_the_rungs_7b_asks_for():
    assert B.PROBLEMS["P1"].sims_per_design == 1
    assert B.PROBLEMS["P2"].sims_per_design == 3
    assert B.PROBLEMS["P3"].sims_per_design == 6
    # P1 is nominal; P2 and P3 are the SCREEN corners, not invented ones.
    assert B.PROBLEMS["P1"].points[0].corner == "tt"
    assert {p.corner for p in B.PROBLEMS["P2"].points} == {"ss", "ff"}


def test_p3_spans_both_ends_of_the_derived_load_range():
    loads = sorted({p.cl_f for p in B.PROBLEMS["P3"].points})
    from nebula.experiments.cl_range import committed_cl_range

    c = committed_cl_range()
    assert loads == pytest.approx([c.cl_lo_f, c.cl_hi_f])
    assert B.PROBLEMS["P1"].points[0].cl_f == pytest.approx(c.cl_mid_f)


def test_p4_is_a_declared_seam_not_a_silent_omission():
    assert "P4" not in B.PROBLEMS
    assert "NOT RUN" in B.TUNABLE_SEAM and "G63" in B.TUNABLE_SEAM


# ─────────────────────────────────────────────────────────────────────────────
# 7f — fairness, enforced in code.
# ─────────────────────────────────────────────────────────────────────────────


def test_every_simulation_is_counted_including_invalid_ones(stub_invalid):
    """7f rule 1. An optimiser that wanders into the invalid region pays."""
    obj = B.Objective(B.PROBLEMS["P1"], budget_sims=9)
    with pytest.raises(B.BudgetExhausted):
        B.method_uniform(obj, np.random.default_rng(0))
    assert obj.n_sims == 9
    assert stub_invalid["n"] == 9
    assert obj.invalid_rate == 1.0


def test_the_budget_stops_every_method(stub_valid):
    for name in ("uniform", "lhs", "cmaes", "gp_bo"):
        obj = B.Objective(B.PROBLEMS["P1"], budget_sims=12)
        with pytest.raises(B.BudgetExhausted):
            B.METHODS[name](obj, np.random.default_rng(1))
        assert obj.n_sims == 12, f"{name} overran its budget"


def test_the_interp_flag_is_threaded_to_the_evaluator_and_defaults_OFF(stub_valid):
    """`Objective(ac_peak_interp=...)` must reach `evaluate`, and default False.

    Both halves matter and only one of them is obvious. If the default flipped
    to True, every baseline in `BASELINES.md` would start paying for a curve
    dump — provably inert, but the point of the default is that the deck stays
    byte-identical to the one those numbers came from. If the flag failed to
    thread, the interpolated arm would silently score the LATTICE peak and
    report "the ceiling did not move", which is the wrong answer arrived at
    quietly.
    """
    obj = B.Objective(B.PROBLEMS["P1"], budget_sims=4)
    assert obj.ac_peak_interp is False
    obj.evaluate([0.5] * B.N_ACTIONS)
    assert stub_valid["ac_peak_interp"] is False

    obj = B.Objective(B.PROBLEMS["P1"], budget_sims=4, ac_peak_interp=True)
    obj.evaluate([0.5] * B.N_ACTIONS)
    assert stub_valid["ac_peak_interp"] is True


def test_worst_case_over_points_is_the_score(monkeypatch):
    """The score must be the MINIMUM over the problem's evaluation points."""
    def pattern(s, corner, n):
        # ss is a worse corner: f_peak further from target.
        oct_ = -0.5247 if corner != "ss" else -0.9897
        return _StubResult(Verdict.VALID, None, _good_meas(oct_), {})

    fake, _ = _stub_factory(pattern)
    monkeypatch.setattr(B, "evaluate", fake)
    obj = B.Objective(B.PROBLEMS["P2"], budget_sims=100)
    t = obj.evaluate(np.full(N_ACTIONS, 0.5))
    solo = B.Objective(B.PROBLEMS["P1"], budget_sims=100)
    assert t.reward < solo.evaluate(np.full(N_ACTIONS, 0.5)).reward


def test_the_floor_short_circuit_is_exact(monkeypatch):
    """Stopping at the invalid floor must not change the answer, only the cost.

    It is exact because `invalid_reward` is the global minimum of the four
    bands, so no later point can lower the result. If that ever stops being
    true this test fails and the short-circuit has to go.
    """
    def pattern(s, corner, n):
        if corner == "ss":
            return _StubResult(Verdict.INVALID, "ngspice: boom", None, None)
        return _StubResult(Verdict.VALID, None, _good_meas(), {})

    fake, calls = _stub_factory(pattern)
    monkeypatch.setattr(B, "evaluate", fake)
    obj = B.Objective(B.PROBLEMS["P3"], budget_sims=100)
    t = obj.evaluate(np.full(N_ACTIONS, 0.5))
    assert t.reward == obj.floor
    assert t.n_sims < B.PROBLEMS["P3"].sims_per_design, (
        "the short-circuit did not fire"
    )
    assert obj.floor <= min(R.invalid_reward(len(R.V1_SPECS)),
                            R.headroom_band_top(len(R.V1_SPECS)) - 1.0), (
        "the floor is no longer the global minimum, so the short-circuit is "
        "no longer exact"
    )


def test_prescreened_rejection_costs_zero_simulations(stub_valid, monkeypatch):
    monkeypatch.setattr(PS, "screen",
                        lambda p, **kw: PS.ScreenVerdict(False, "no", None))
    obj = B.Objective(B.PROBLEMS["P1"], budget_sims=5, prescreen=True)
    for _ in range(20):
        obj.evaluate(np.full(N_ACTIONS, 0.5))
    assert obj.n_sims == 0 and stub_valid["n"] == 0
    assert obj.n_screened_out == 20
    # ...and a screened-out trial never appears on the anytime curve.
    assert obj.simulated == []


def test_seed_protocol_is_a_stated_rule_and_collides_with_nothing():
    seen = set()
    for p in B.PROBLEM_OFFSET:
        for m in B.METHOD_OFFSET:
            for rep in range(20):
                s = B.run_seed(p, m, rep)
                assert s not in seen, f"seed collision at {p}/{m}/{rep}"
                seen.add(s)
    with pytest.raises(KeyError):
        B.run_seed("P9", "uniform", 0)


def test_workers_is_eight_because_eleven_is_slower():
    assert B.WORKERS == 8
    # This benchmark's OWN measurement (33 runs, 1992 sims), not session 17's
    # 2.98x on isolated evaluations -- the two are different task mixes and
    # BASELINES.md quotes both because the difference is the finding.
    assert B.SPEEDUP_AT_8 == pytest.approx(1.80, abs=0.02)
    assert B.SPEEDUP_AT_8_SESSION_17 == pytest.approx(2.98, abs=0.01)
    assert B.SEC_PER_SIM_AT_8 > B.SEC_PER_SIM_AT_8_SESSION_17, (
        "the benchmark's own rate must be the SLOWER one; sizing to the "
        "faster one plans a 12-hour run that takes 15"
    )


def test_p3_lost_two_methods_and_says_which():
    """The second cut, after the pilot re-measured the throughput."""
    alloc = B.default_allocation()
    p3 = {a.method for a in alloc if a.problem == "P3"}
    assert p3 == set(B.P3_METHODS) == {"uniform", "cmaes"}
    p1 = {a.method for a in alloc if a.problem == "P1"}
    assert p1 == set(B.REPLICATES), "P1 keeps every method"


def test_provenance_pins_the_evaluator_and_the_box():
    p = B.provenance()
    assert set(p) >= {"commit", "box", "specs", "tolerances", "library",
                      "prescreen", "workers"}
    assert [d["name"] for d in p["box"]] == list(
        __import__("nebula.rl.contract", fromlist=["x"]).ACTION_NAMES)
    assert "params.py" in p["box_source"]


def test_ppo_refuses_a_multi_point_problem(stub_valid):
    obj = B.Objective(B.PROBLEMS["P3"], budget_sims=5)
    with pytest.raises(ValueError, match="P1 only"):
        B.method_ppo(obj, np.random.default_rng(0))


# ─────────────────────────────────────────────────────────────────────────────
# 7a — the arithmetic.
# ─────────────────────────────────────────────────────────────────────────────


def test_budget_report_adds_up():
    b = B.budget_report()
    assert b["total_sims"] == sum(
        blk["replicates"] * blk["budget_sims"] for blk in b["blocks"])
    assert b["hours_pessimistic"] == pytest.approx(
        b["total_sims"] * B.SEC_PER_SIM_AT_8 / 3600.0)
    assert b["hours_optimistic"] < b["hours_pessimistic"]


def test_the_allocation_fits_an_overnight_run_and_the_full_design_does_not():
    b = B.budget_report()
    # 7a asks for "roughly 12 hours"; 12.5 is where "roughly" stops. The
    # allocation lands at 12.0 h and the warm-up plus control add ~0.15 h on
    # top, which is why the bound is not exactly 12.
    assert b["hours_pessimistic"] <= 12.5, (
        "7a: the allocation must fit a single overnight run of roughly 12 h"
    )
    assert b["fully_crossed_hours_at_8"] > 12.0, (
        "if the fully crossed design fits, nothing needed cutting and the "
        "allocation should be the full one"
    )


def test_the_cut_fell_on_problems_and_screen_arms_not_on_seeds():
    """7a: cut seeds or problems, never the per-run budget -- and 7h puts
    seeds last. This pins WHICH cut was made."""
    alloc = B.default_allocation()
    assert {a.budget_sims for a in alloc} == {B.BUDGET_SIMS}
    for a in alloc:
        assert a.replicates == B.REPLICATES[a.method], (
            "a seed count was cut; 7h says cut a problem rung instead"
        )
    problems = {a.problem for a in alloc}
    assert problems == {"P1", "P3"} and "P2" not in problems


# ─────────────────────────────────────────────────────────────────────────────
# The reward ceiling — the AC grid caps the primary metric.
# ─────────────────────────────────────────────────────────────────────────────


def test_reward_ceiling_matches_the_ac_grid():
    """Pinned against the value four independent pilot runs measured.

    Different designs, same reward to six decimals, because `meas ac MAX` can
    only report a frequency on the `ac dec 50 1meg 100g` lattice and
    `S3_f_peak` is the binding row. 8.950669 is derived here; 8.950670 was
    measured.
    """
    target = math.sqrt(SPEC_F_PEAK_HZ_RANGE[0] * SPEC_F_PEAK_HZ_RANGE[1])
    assert B.AC_GRID_OCTAVES == pytest.approx(0.066439, abs=1e-6)
    assert B.nearest_grid_offset_octaves(target) == pytest.approx(0.024665,
                                                                  abs=1e-5)
    assert B.reward_ceiling(target) == pytest.approx(8.950670, abs=1e-5)


def test_ac_grid_constants_match_the_netlist_the_runner_writes():
    """Two definitions of one thing is the failure this repo keeps hitting."""
    from pathlib import Path

    src = Path(B.__file__).parents[1] / "device" / "sky130_runner.py"
    text = src.read_text(encoding="utf-8", errors="replace")
    assert "ac dec 50 1meg 100g" in text, (
        "the AC sweep template changed; AC_GRID_START_HZ / AC_GRID_PER_DECADE "
        "and therefore the reward ceiling are now wrong"
    )
    assert B.AC_GRID_PER_DECADE == 50
    assert B.AC_GRID_START_HZ == 1e6


def test_sims_to_ceiling_is_censored_not_defaulted():
    ceil = 8.95067
    trials = [B.Trial(index=0, u=[], design_id=None, geometry_tag=None,
                      params={}, reward=1.0, feasible=True, verdict="valid",
                      invalid_reason=None, worst_point=None, worst_spec=None,
                      n_sims=1, seconds=0.0, cum_sims=1, cum_seconds=0.0,
                      screened_out=False, screen_reason=None, meas=None,
                      margins=None, predicted=None)]
    assert B.sims_to_ceiling(trials, ceil) is None
    trials.append(B.Trial(index=1, u=[], design_id=None, geometry_tag=None,
                          params={}, reward=ceil, feasible=True,
                          verdict="valid", invalid_reason=None,
                          worst_point=None, worst_spec=None, n_sims=1,
                          seconds=0.0, cum_sims=2, cum_seconds=0.0,
                          screened_out=False, screen_reason=None, meas=None,
                          margins=None, predicted=None))
    assert B.sims_to_ceiling(trials, ceil) == 2


# ─────────────────────────────────────────────────────────────────────────────
# 7c / 7h — metrics and statistics.
# ─────────────────────────────────────────────────────────────────────────────


def test_anytime_curve_is_monotone_and_steps_at_the_simulation_count():
    trials = []
    for i, (r, n) in enumerate([(-3.0, 2), (5.0, 3), (1.0, 1)]):
        cum = sum(t.n_sims for t in trials) + n
        trials.append(B.Trial(index=i, u=[], design_id=None, geometry_tag=None,
                              params={}, reward=r, feasible=False,
                              verdict="valid", invalid_reason=None,
                              worst_point=None, worst_spec=None, n_sims=n,
                              seconds=0.0, cum_sims=cum, cum_seconds=0.0,
                              screened_out=False, screen_reason=None,
                              meas=None, margins=None, predicted=None))
    c = B.anytime_curve(trials, 10)
    assert np.all(np.diff(c[np.isfinite(c)]) >= 0)
    assert c[0] == -np.inf and c[1] == -3.0        # first result lands at 2
    assert c[4] == 5.0 and c[-1] == 5.0


def test_censored_table_never_substitutes_the_budget():
    """7c, stated as a prohibition and therefore tested as one."""
    runs = [{"sims_to_first_feasible": None} for _ in range(10)]
    t = B.censored_table(runs)
    assert t["n_found"] == 0 and t["frac_found"] == 0.0
    assert t["median_conditional"] is None, (
        "a censored median must be None, never the budget and never infinity"
    )
    runs[0]["sims_to_first_feasible"] = 7
    runs[1]["sims_to_first_feasible"] = 9
    t = B.censored_table(runs)
    assert t["n_found"] == 2 and t["frac_found"] == pytest.approx(0.2)
    assert t["median_conditional"] == pytest.approx(8.0)
    assert t["censored_seeds"] == 8
    assert "CONDITIONAL" in t["conditional_on"].upper()


def test_bootstrap_median_brackets_the_median():
    rng = np.random.default_rng(3)
    x = rng.normal(5.0, 1.0, 40)
    m, lo, hi = B.bootstrap_median(x, n_boot=2000, rng=rng)
    assert lo <= m <= hi
    assert m == pytest.approx(float(np.median(x)))


def test_separable_is_an_interval_test():
    assert B.separable((0.0, 1.0), (2.0, 3.0))
    assert not B.separable((0.0, 2.0), (1.0, 3.0))
    assert not B.separable((0.0, 1.0), (1.0, 2.0))          # touching


def test_mann_whitney_reports_an_effect_size_beside_the_p_value():
    r = B.mann_whitney([1, 2, 3, 4, 5], [10, 11, 12, 13, 14])
    assert r["p"] is not None and r["effect"] is not None
    assert r["effect"] == pytest.approx(0.0)      # a is entirely below b
    assert B.mann_whitney([1], [2])["p"] is None  # too few, and says so


def test_analysis_reports_multiple_comparisons_and_a_guarded_ranking():
    runs = []
    for method, base in (("uniform", 1.0), ("cmaes", 5.0)):
        for rep in range(4):
            runs.append({"problem": "P1", "method": method, "replicate": rep,
                         "seed": rep, "prescreen": False,
                         "curve": [base, base + rep * 0.01],
                         "sims_to_first_feasible": 3 + rep,
                         "sims_to_ceiling": None,
                         "reward_ceiling": 8.95,
                         "invalid_rate": 0.1, "wall_s": 1.0,
                         "model_seconds": 0.0, "sec_per_sim": 1.0,
                         "n_screened_out": 0})
    a = B.analyse(runs)
    assert "Bonferroni" in a["multiple_comparisons"]
    assert "not separable" in a["multiple_comparisons"]
    rows = a["ranking"]["P1"]
    assert rows[0]["group"] == "P1/cmaes"
    assert rows[0]["separable_from_next"] is True


# ─────────────────────────────────────────────────────────────────────────────
# 7d — the designer row.
# ─────────────────────────────────────────────────────────────────────────────


def test_designer_baseline_is_traceable_to_the_session_log():
    from pathlib import Path

    d = B.DESIGNER_BASELINE
    # Whitespace-normalised: HANDOFF.md is hard-wrapped, so the quote spans a
    # line break. Normalising is not weakening the gate -- the words still have
    # to be there, in that order.
    handoff = " ".join((Path(B.__file__).parents[2] / "HANDOFF.md").read_text(
        encoding="utf-8", errors="replace").split())
    assert d["sims_quoted"] in handoff, (
        "the designer baseline must quote the session log verbatim, not a "
        "number an agent recalled (CLAUDEwa.md §8 rule 1)"
    )
    assert d["comparable_rung"] is None
    assert "LOWER bound" in d["caveat"] and "UPPER bound" in d["caveat"]


# ─────────────────────────────────────────────────────────────────────────────
# 7g — the timing control.
# ─────────────────────────────────────────────────────────────────────────────


def test_the_job_order_is_interleaved_not_blocked():
    alloc = B.default_allocation()
    jobs = B.jobs_for(alloc, seed=B.BASE_SEED)
    assert len(jobs) == sum(a.replicates for a in alloc)
    # A blocked order would put every replicate of a config consecutively.
    configs = [j.config for j in jobs]
    runs_of_same = sum(1 for i in range(1, len(configs))
                       if configs[i] == configs[i - 1])
    assert runs_of_same < len(configs) // 3, "the job order looks blocked"


def test_control_limits_are_session_17s_own():
    assert B.CONTROL_RATIO_LIMIT == (0.8, 1.25)
