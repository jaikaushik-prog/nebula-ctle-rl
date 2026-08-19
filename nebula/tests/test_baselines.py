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
import re
from dataclasses import dataclass, field
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
    #: `EvalResult` has carried this since the interface froze, and the stub
    #: went without it until `Objective` started reading
    #: `raw['peak_interp_status']` (session 22e). A test double missing a field
    #: the real object has does not fail at the seam it is standing in for --
    #: it fails wherever the caller happens to touch it, which is why the stub
    #: now names the field rather than being defended against with `getattr`.
    raw: dict = field(default_factory=dict)

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
    """Derived from `METHODS`, not from a list, so a method added without a
    budget test cannot slip through. `ppo` is excluded here because it needs
    the torch env; `test_ppo_refuses_a_multi_point_problem` covers its seam."""
    names = [m for m in B.METHODS if m != "ppo"]
    assert "grid" in names, "the grid arm must be covered by this gate"
    for name in names:
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


def test_no_two_default_artifact_paths_collide():
    """**G95: the sweep silently overwrote the pre-screen's results file.**

    `--prescreen` writes 1890 samples of calibration -- the 61.69 % free
    rejection, the 2.600x yield lift, the 0.394 % false rejection that
    `BASELINES.md` §5 and half this project quote -- and `sweep()` defaulted its
    own output to the same name. The first real sweep replaced 4 KB of
    calibration with 63 MB of run summaries, and nothing said so: both writers
    succeeded, both printed "wrote ...", and the loss was only visible as a
    deletion in `git status`.

    Recovering it needed `git checkout HEAD~1 --`. Had the sweep run twice
    before anyone looked, it would have been gone.

    This asserts the defaults are distinct by NAME rather than checking the
    files on disk, so it fails in CI on a fresh clone.
    """
    import inspect

    src = inspect.getsource(B.sweep) + inspect.getsource(B.main)
    defaults = re.findall(r'HERE / f?"([A-Za-z0-9_{}.]+\.json)"', src)
    assert defaults, "no default artifact paths found -- has the pattern moved?"
    # `{suffix}`-templated names are distinct from the literal ones by
    # construction; strip them to their stem and compare the rest.
    literal = [d for d in defaults if "{" not in d]
    assert len(literal) == len(set(literal)), (
        f"two writers share a default artifact path: {literal}")
    # ... and specifically: the CALL, not the comment above it. Grepping the
    # whole source matches the paragraph explaining the bug, which would make
    # this test permanently red for documenting itself.
    save_line = [L for L in inspect.getsource(B.sweep).splitlines()
                 if "_save(" in L]
    assert len(save_line) == 1, save_line
    assert "baselines_results.json" not in save_line[0], (
        "sweep() must not default to the pre-screen's artifact name (G95)")


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


def test_the_rate_the_budget_is_sized_to_is_the_sweeps_own_end_to_end_timing():
    """**Replaces an assertion that had gone false, and says why.**

    Until 2026-08-19 this file asserted `SEC_PER_SIM_AT_8 >
    SEC_PER_SIM_AT_8_SESSION_17` -- "the benchmark's own rate must be the
    SLOWER one" -- which was the right rule while both numbers were PREDICTIONS
    of a run that had not happened. The run has now happened, twice, and timed
    itself end to end: 2528.06 s / 25 869 sims and 2869.64 s / 25 866 sims. A
    measured rate does not have to be pessimistic; it has to be measured.

    What the rule becomes: the constant the allocation is sized to must be one
    of the two SWEEP timings, the pessimistic bracket must be the slower of
    them, and the superseded constants must still be present so a reader can
    see a 17x revision rather than only its result.
    """
    assert B.SEC_PER_SIM_AT_8 == pytest.approx(2528.055 / 25869, rel=1e-3), (
        "sized to the interpolated sweep's own elapsed time"
    )
    assert B.SEC_PER_SIM_AT_8_LATTICE == pytest.approx(2869.637 / 25866,
                                                       rel=1e-3)
    assert B.SEC_PER_SIM_AT_8_LATTICE > B.SEC_PER_SIM_AT_8, (
        "the pessimistic bracket must be the slower measurement"
    )
    # the history is kept, not overwritten
    assert B.SEC_PER_SIM_AT_8_PILOT == pytest.approx(1.698)
    assert B.SEC_PER_SIM_AT_8_PILOT / B.SEC_PER_SIM_AT_8 > 15.0
    b = B.budget_report()
    assert b["hours_optimistic"] == pytest.approx(
        b["total_sims"] * B.SEC_PER_SIM_AT_8 / 3600.0)
    assert b["hours_pessimistic"] == pytest.approx(
        b["total_sims"] * B.SEC_PER_SIM_AT_8_LATTICE / 3600.0)


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
        b["total_sims"] * B.SEC_PER_SIM_AT_8_LATTICE / 3600.0)
    assert b["hours_optimistic"] < b["hours_pessimistic"]


def test_the_allocation_fits_and_the_cut_is_no_longer_a_cost_argument():
    """**This test asserted the opposite until 2026-08-19, and the change is
    the finding rather than a relaxation.**

    It used to require `fully_crossed_hours_at_8 > 12.0`, on the reasoning
    that "if the fully crossed design fits, nothing needed cutting". At the
    measured 0.098 s/sim the fully crossed design DOES fit -- 81 000 sims is
    ~2.2 h -- so that reasoning now points at a decision rather than at a
    constraint, and the decision is the owner's (CONTINUE_HERE.md sec 5).

    What survives is the part that was never about hours: 7a's rule that the
    cut falls on problems and screen arms, never on the per-run budget and
    never on the seed counts. `test_the_cut_fell_on_problems_and_screen_arms_
    not_on_seeds` is that rule and it is untouched.
    """
    b = B.budget_report()
    assert b["hours_pessimistic"] <= 12.5, (
        "7a: the allocation must fit a single overnight run"
    )
    assert b["fully_crossed_hours_at_8"] < 4.0, (
        "the fully crossed design now fits; if this goes red the rate moved "
        "and default_allocation()'s docstring has to be re-argued"
    )
    # ... and the allocation is still NOT the fully crossed design, so the
    # docstring's claim that cuts remain is checkable rather than asserted.
    assert b["total_sims"] < b["fully_crossed_sims"]


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


# ─────────────────────────────────────────────────────────────────────────────
# The GRID arm — G3's criterion names grid search and this file had none until
# 2026-08-19. These pin the arithmetic, the point pattern, and the two ways the
# method can silently stop being grid search.
# ─────────────────────────────────────────────────────────────────────────────


def test_grid_levels_is_the_budget_arithmetic_and_it_is_the_finding():
    """150 simulations in 7 dimensions buys 2.06 levels per axis.

    This is the number the whole grid row exists to report, so it is pinned
    exactly rather than approximately: L = 2 costs 128 points and fits inside
    150; L = 3 costs 2 187 and is 14.6x the budget. No arrangement of a
    150-simulation budget makes grid search finer than two levels per axis at
    d = 7, and that is what the competition's "sweeping all MOS, R, C, L
    parameter space" costs.
    """
    assert B.grid_levels(B.BUDGET_SIMS, N_ACTIONS) == 2
    assert 2 ** N_ACTIONS == 128 <= B.BUDGET_SIMS
    assert 3 ** N_ACTIONS == 2187 > B.BUDGET_SIMS
    # the boundaries, exactly
    assert B.grid_levels(128, N_ACTIONS) == 2
    assert B.grid_levels(127, N_ACTIONS) == 1
    assert B.grid_levels(2186, N_ACTIONS) == 2
    assert B.grid_levels(2187, N_ACTIONS) == 3
    # monotone in the budget, and never zero
    prev = 0
    for n in (1, 2, 50, 128, 500, 2187, 20000):
        L = B.grid_levels(n, N_ACTIONS)
        assert L >= max(1, prev)
        prev = L
    for bad in (0, -1):
        with pytest.raises(ValueError):
            B.grid_levels(bad, N_ACTIONS)
    with pytest.raises(ValueError):
        B.grid_levels(150, 0)


def test_grid_is_not_on_P3_and_the_reason_is_arithmetic_not_taste():
    """P3 buys 25 designs; the smallest factorial in 7 dimensions is 128."""
    assert "grid" not in B.P3_METHODS
    designs = B.BUDGET_SIMS // B.PROBLEMS["P3"].sims_per_design
    assert designs == 25
    assert B.grid_levels(designs, N_ACTIONS) == 1, (
        "if this ever returns >= 2, a grid arm on P3 becomes a search rather "
        "than a single point and P3_METHODS should be re-argued"
    )


def test_every_method_has_a_seed_offset(stub_valid):
    """`run_seed` raises `KeyError` on an unknown method, so a method added to
    `METHODS` without an offset fails at RUN time, inside a worker process,
    after the sweep has already started. Catch it here instead."""
    assert set(B.METHOD_OFFSET) >= set(B.METHODS)
    assert len(set(B.METHOD_OFFSET.values())) == len(B.METHOD_OFFSET)


def _grid_us(budget, seed=0, obj=None):
    obj = obj or B.Objective(B.PROBLEMS["P1"], budget_sims=budget)
    with pytest.raises(B.BudgetExhausted):
        B.method_grid(obj, np.random.default_rng(seed))
    return obj, [t.u for t in obj.trials]


def test_grid_is_a_CENTRED_factorial_not_the_128_box_corners(stub_valid):
    """An endpoint-inclusive 2-level grid in 7 dimensions is exactly the box
    corners -- every parameter at its extreme, simultaneously. That is a straw
    man, and it would also be a different measurement: `sizing_from_u` maps
    u = 0 and u = 1 to the ends of every range. The centred convention is
    `_lhs`'s, so the two model-free methods differ in point pattern alone."""
    obj, us = _grid_us(128)
    assert len(us) == 128
    assert {round(x, 12) for u in us for x in u} == {0.25, 0.75}
    assert len({tuple(u) for u in us}) == 128, "the factorial is complete"


def test_grid_refines_past_its_first_factorial_when_budget_remains(stub_valid):
    obj, us = _grid_us(150)
    levels = [B.grid_level_of(u) for u in us]
    assert levels.count(2) == 128
    assert levels.count(3) == 22, "the leftover 22 go into the finer grid"
    assert None not in levels


def test_grid_visits_distinct_points_and_its_dedupe_CANNOT_FIRE_here(stub_valid):
    """**G73, stated instead of assumed: this guard is unreachable at 150.**

    `method_grid` carries a `seen` set across levels so a refinement never
    re-simulates a point the coarse pass already has. The first draft of this
    test asserted "no duplicates" after 400 simulations, went green, and was
    VACUOUS -- centred lattices nest only when `M / L` is an ODD integer, so
    L = 2's points are absent from L = 3, L = 4 and L = 5 and first reappear at
    L = 6, which this loop reaches only after 96 824 designs.

    So this test asserts two different things and keeps them apart: that the
    points really are distinct at a reachable budget, and that the DEDUPE is
    not what makes them distinct. The second half is the part G73 is about --
    "a gate whose condition is unreachable is indistinguishable from a deleted
    gate" -- and it is why `method_grid`'s docstring says the same thing.
    """
    obj, us = _grid_us(400)
    keys = [tuple(round(x, 12) for x in u) for u in us]
    assert len(keys) == len(set(keys)), "grid re-evaluated a point"

    # the nesting rule, checked on the lattices themselves
    rng = np.random.default_rng(0)

    def _pts(L):
        return {round(x, 12) for x in B._factorial(L, 1, rng).ravel()}

    assert _pts(2) <= _pts(6), "L=2 must nest inside L=6 (6/2 = 3, odd)"
    for L in (3, 4, 5):
        assert not (_pts(2) <= _pts(L)), f"L=2 must NOT nest inside L={L}"

    # ... therefore the first level at which `seen` could fire is 6, and
    # reaching it costs this many designs:
    cost = sum(L ** N_ACTIONS for L in (2, 3, 4, 5))
    assert cost == 96_824
    assert cost > 100 * B.BUDGET_SIMS, (
        "if the budget ever grows past the coarse levels, the dedupe becomes "
        "reachable and this test should start asserting that it fires"
    )


def test_grid_level_of_recovers_the_lattice_from_u_alone():
    """The run log stores `u` and nothing about the grid, so a write-up that
    claims "the screened arm reached the three-level grid" has to be able to
    check it against the artifact."""
    assert B.grid_level_of([0.5] * N_ACTIONS) == 1
    assert B.grid_level_of([0.25] * N_ACTIONS) == 2
    assert B.grid_level_of([1 / 6] * N_ACTIONS) == 3
    # nesting: 0.25 is on BOTH the 2-level and the 6-level lattice, and the
    # smallest is the one the enumeration reached.
    assert B.grid_level_of([0.25, 0.75, 0.25, 0.75, 0.25, 0.75, 0.25]) == 2
    # a point on no lattice -- i.e. every row any other method logs
    assert B.grid_level_of([0.31] * N_ACTIONS) is None
    assert B.grid_level_of(np.random.default_rng(0).uniform(size=N_ACTIONS)) is None


def test_the_screen_buys_the_grid_RESOLUTION_not_only_throughput(monkeypatch,
                                                                 stub_valid):
    """**The claim in `method_grid`'s docstring, measured rather than asserted.**

    For every other method the pre-screen buys throughput: a rejected proposal
    costs no simulation, so more proposals fit in the budget. For the grid it
    buys step size -- the screened arm can finish the coarse factorial cheaply
    and spend its simulations inside the FINER one, which the unscreened arm
    cannot reach at all. This is the only mechanism in the benchmark that can
    change a grid's resolution, and if it stops being true the docstring is
    wrong.
    """
    n = {"i": 0}

    def _screen(params, target_f_peak_hz=None):
        n["i"] += 1
        return PS.ScreenVerdict(n["i"] % 3 == 0, "stub", None)

    monkeypatch.setattr(B.PS, "screen", _screen)

    plain, _ = _grid_us(150)
    scr = B.Objective(B.PROBLEMS["P1"], budget_sims=150, prescreen=True)
    scr, _ = _grid_us(150, obj=scr)

    def _fine(o):
        return sum(1 for t in o.trials
                   if t.n_sims > 0 and (B.grid_level_of(t.u) or 0) >= 3)

    assert scr.n_screened_out > 0, "the stub screen never fired"
    assert _fine(plain) == 22
    assert _fine(scr) > _fine(plain), (
        f"the screen bought no resolution: {_fine(scr)} simulated points on "
        f"the 3-level grid against {_fine(plain)} unscreened"
    )


def test_grid_raises_rather_than_enumerating_forever(monkeypatch):
    """CLAUDEwa sec 8 rule 10: a condition that cannot be handled must fail
    loudly. If nothing costs a simulation the budget never exhausts, and every
    method in this file spins -- `method_uniform` silently and forever. The
    grid is finite per level, so it is the one that can name the condition,
    and it must."""
    fake, calls = _stub_factory(
        lambda s, c, i: _StubResult(Verdict.VALID, None, _good_meas(), {},
                                    n_spice=0))
    monkeypatch.setattr(B, "evaluate", fake)
    monkeypatch.setattr(B, "GRID_MAX_LEVELS", 2)
    obj = B.Objective(B.PROBLEMS["P1"], budget_sims=150)
    with pytest.raises(RuntimeError, match="without spending"):
        B.method_grid(obj, np.random.default_rng(0))
    assert obj.n_sims == 0


def test_a_groups_bootstrap_stream_is_a_function_of_its_NAME(monkeypatch):
    """**G96: a group's interval must not depend on which other arms ran.**

    `analyse` used to build ONE generator and consume it across
    `groups.items()`, whose order is the order the process pool finished.
    Adding a `grid` arm reproduced all twelve medians at **0.00e+00** and still
    moved the separable-pair count from **20 to 22 of 45**.

    **This asserts on the STREAM, not on the interval, and that is
    deliberate.** A percentile bootstrap endpoint is an order statistic of the
    sample, so across 10 000 resamples it is *stable*: two different streams
    land on the same endpoint most of the time and only a group sitting near a
    boundary flips. That stability is why the defect survived three sessions --
    and it is also why an interval-equality version of this test passed with
    the bug restored, which the first draft did. The property that actually has
    to hold is that **the draws a group sees are a function of its name and of
    nothing else.**

    `analyse` iterates `sorted(groups.items())`, so adding `P1/grid` prepends
    its calls and leaves `P1/lhs` and `P1/uniform` seeing exactly the draws
    they saw before. With a shared generator they would all shift.
    """
    drawn: list[int] = []

    def _spy(x, n_boot=10_000, alpha=0.05, rng=None):
        if rng is not None:
            drawn.append(int(rng.integers(0, 10 ** 9)))
        return (float(np.median(x)), float(np.min(x)), float(np.max(x)))

    monkeypatch.setattr(B, "bootstrap_median", _spy)

    def _row(method, rep):
        return {"problem": "P1", "method": method, "prescreen": False,
                "replicate": rep, "seed": rep, "curve": [8.0, 8.4, 8.9],
                "sims_to_first_feasible": 2, "sims_to_ceiling": None,
                "censored": False, "reward_ceiling": 8.95, "invalid_rate": 0.0,
                "wall_s": 1.0, "model_seconds": 0.0, "sec_per_sim": 0.1,
                "n_screened_out": 0, "n_sims": 3}

    base = ([_row("uniform", i) for i in range(5)]
            + [_row("lhs", i) for i in range(5)])
    extra = [_row("grid", i) for i in range(5)]

    drawn.clear()
    B.analyse(base)
    without = list(drawn)

    drawn.clear()
    B.analyse(extra + base)
    with_grid = list(drawn)

    assert without, "the spy recorded nothing -- has bootstrap_median moved?"
    assert len(with_grid) > len(without)
    assert with_grid[-len(without):] == without, (
        "adding an unrelated arm changed the bootstrap stream the SHARED "
        "groups see; the generator is not seeded per group (G96)"
    )
    # ... and the seed is a pure function of the name, stable across processes
    assert B.group_seed("P1/uniform") == B.group_seed("P1/uniform")
    assert B.group_seed("P1/uniform") != B.group_seed("P1/grid")


def test_analyse_survives_a_log_with_a_single_group():
    """The recovery path's whole purpose is a PARTIAL log, and the first
    finished arm is one group -- which used to divide by zero pairs."""
    runs = [{"problem": "P1", "method": "uniform", "prescreen": False,
             "replicate": i, "seed": i, "curve": [8.0, 8.5, 8.9],
             "sims_to_first_feasible": 2, "sims_to_ceiling": None,
             "censored": False, "reward_ceiling": 8.95, "invalid_rate": 0.0,
             "wall_s": 1.0, "model_seconds": 0.0, "sec_per_sim": 0.1,
             "n_screened_out": 0, "n_sims": 3} for i in range(3)]
    a = B.analyse(runs)
    assert "no pairs to correct" in a["multiple_comparisons"]
    assert set(a["groups"]) == {"P1/uniform"}
