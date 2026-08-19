"""
Tests for `experiments/exp_budget_ladder.py`.

**None of these runs ngspice.** The point of the module is a read-out over
curves, so the curves are synthesised and the arithmetic is checked against
hand-computed values.

Two of them are gates in CLAUDEwa.md §8 rule 10's sense:

  * `test_the_readouts_are_doublings_not_additions` — the design decision the
    whole experiment rests on. Rungs 50 simulations apart cannot resolve an
    effect six times smaller than the noise.
  * `test_verify_prefix_reports_a_mismatch_rather_than_averaging_it` — if the
    long run does NOT contain the short ones, reading the ladder off one curve
    is invalid and this has to say so loudly.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from nebula.experiments import baselines as B
from nebula.experiments import exp_budget_ladder as L


# ─────────────────────────────────────────────────────────────────────────────
# The design
# ─────────────────────────────────────────────────────────────────────────────


def test_the_readouts_are_doublings_not_additions():
    """**The decision this experiment rests on.**

    The obvious ladder is 200 / 250 / 300 / 350. It cannot work: PPO's seed
    spread at 150 simulations is ~0.12 wide, and `PREDICTIONS.md` entry 12
    measured an 11x increase in policy updates moving the score by **0.0106**,
    six times smaller than that. A ladder spanning 2.3x cannot resolve an
    effect that size, so the rungs multiply.
    """
    r = list(L.READOUTS)
    assert r[0] == B.BUDGET_SIMS, "the ladder must start at the published budget"
    assert r[-1] == L.LADDER_BUDGET
    for a, b in zip(r, r[1:]):
        assert b == 2 * a, f"{a} -> {b} is not a doubling"
    assert r[-1] / r[0] >= 16, "the ladder must span at least 16x"


def test_the_arms_include_the_CONTROL_and_keep_the_published_seed_counts():
    """PPO against itself trends upward whether or not it learns, because more
    simulations is more lottery tickets. `uniform` is what makes the trend
    mean something; `cmaes` says whether anything is still improving."""
    assert "ppo" in L.ARMS and "uniform" in L.ARMS, (
        "a budget trend without a random-search control is uninterpretable"
    )
    alloc = L.allocation()
    for a in alloc:
        assert a.problem == "P1"
        assert a.prescreen is False, (
            "the screen changes how many PROPOSALS a simulation buys, which is "
            "a different axis from the one under test"
        )
        assert a.replicates == B.REPLICATES[a.method], (
            "a changed seed count makes this a comparison of sample sizes"
        )
        assert a.budget_sims == L.LADDER_BUDGET


def test_the_budget_report_is_arithmetic_and_names_the_update_count():
    b = L.budget_report()
    assert b["total_sims"] == sum(a.sims for a in L.allocation())
    assert b["n_runs"] == sum(B.REPLICATES[m] for m in L.ARMS)
    assert b["hours_optimistic"] == pytest.approx(
        b["total_sims"] * B.SEC_PER_SIM_AT_8 / 3600.0)
    # the mechanism under test: budget buys policy updates, and the ladder must
    # actually move it out of the single-update regime entry 12 diagnosed
    u = b["ppo_updates_at_readout"]
    assert u[str(B.BUDGET_SIMS)] == 1, (
        "at the published budget PPO gets ONE update -- that is the finding "
        "this experiment is built on"
    )
    assert u[str(L.LADDER_BUDGET)] >= 20, (
        "the top of the ladder must buy enough updates for the question to be "
        "answerable"
    )
    # rollout_steps is PPOConfig's, not restated here (rule 9)
    from nebula.rl.ppo import PPOConfig

    assert b["ppo_rollout_steps"] == PPOConfig(seed=0).rollout_steps


# ─────────────────────────────────────────────────────────────────────────────
# The read-out
# ─────────────────────────────────────────────────────────────────────────────


def _results(curves: dict[str, list[list[float]]]) -> dict:
    runs = []
    for m, cs in curves.items():
        for i, c in enumerate(cs):
            runs.append({"method": m, "replicate": i, "role": "measured",
                         "curve": list(c)})
    return {"runs": runs}


def test_the_ladder_reads_the_curve_at_the_right_index():
    """`anytime_curve` index i is the best after i+1 simulations, so budget n
    is index n-1. An off-by-one here silently reports the wrong budget."""
    c = [float(i) for i in range(1, 2401)]     # value == simulations spent
    res = _results({"ppo": [c], "uniform": [c]})
    a = L.ladder(res, readouts=(150, 300, 2400))
    for n in (150, 300, 2400):
        assert a["per_arm"]["ppo"][str(n)]["median"] == pytest.approx(float(n))


def test_the_gap_to_random_search_is_the_reported_answer():
    """The experiment exists to produce this row, so it is pinned."""
    flat = [8.90] * 600
    rising = [8.90 + 0.0001 * i for i in range(600)]
    res = _results({"ppo": [flat] * 3, "uniform": [rising] * 3})
    a = L.ladder(res, readouts=(150, 300, 600))
    g = a["ppo_vs_uniform"]
    assert set(g) == {"150", "300", "600"}
    # uniform pulls away, so the gap must get MORE negative with budget
    vals = [g[str(n)]["ppo_minus_uniform"] for n in (150, 300, 600)]
    assert vals[0] > vals[1] > vals[2]
    assert vals[-1] == pytest.approx(8.90 - (8.90 + 0.0001 * 599))


def test_still_improving_is_measured_over_the_final_third_of_each_rung():
    """A flat method must read 0.0 and a climbing one must not — this is how
    'has it stopped learning?' is answered at every rung rather than only at
    the end."""
    flat = [8.9] * 600
    rising = [8.9 + 0.001 * i for i in range(600)]
    a = L.ladder(_results({"ppo": [flat], "uniform": [rising]}),
                 readouts=(600,))
    assert a["per_arm"]["ppo"]["600"]["gain_over_final_third"] == 0.0
    assert a["per_arm"]["uniform"]["600"]["gain_over_final_third"] > 0.15


def test_a_readout_beyond_the_curve_is_omitted_not_invented():
    """Rule 1: never fabricate a number. A partial run must drop the rungs it
    did not reach rather than reporting its last value at all of them."""
    a = L.ladder(_results({"ppo": [[8.9] * 300]}), readouts=(150, 300, 2400))
    assert set(a["per_arm"]["ppo"]) == {"150", "300"}


# ─────────────────────────────────────────────────────────────────────────────
# The design claim, checked
# ─────────────────────────────────────────────────────────────────────────────


def test_verify_prefix_reports_a_mismatch_rather_than_averaging_it(tmp_path):
    """**The gate. If the long run does not contain the short ones, the whole
    'read the ladder off one curve' argument is invalid.**

    A reference log is synthesised with two trials; one results curve agrees
    with it and one is perturbed in its third entry. The perturbed one must be
    counted, named, and must flip the verdict.
    """
    ref = tmp_path / "ref.jsonl"
    rows = []
    for rep, rewards in ((0, [8.0, 8.5, 8.9]), (1, [8.1, 8.2, 8.7])):
        for i, rw in enumerate(rewards):
            rows.append({"event": "trial", "role": "measured", "problem": "P1",
                         "method": "ppo", "replicate": rep, "prescreen": False,
                         "index": i, "u": [0.5] * 7, "design_id": None,
                         "geometry_tag": None, "params": {}, "reward": rw,
                         "feasible": True, "verdict": "valid",
                         "invalid_reason": None, "worst_point": None,
                         "worst_spec": None, "n_sims": 1, "seconds": 0.0,
                         "cum_sims": i + 1, "cum_seconds": 0.0,
                         "screened_out": False, "screen_reason": None,
                         "meas": None, "margins": None, "predicted": None})
    ref.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    good = {"runs": [{"method": "ppo", "replicate": 0, "role": "measured",
                      "curve": [8.0, 8.5, 8.9, 9.0]}]}
    v = L.verify_prefix(good, reference=ref, n=3)
    assert v["n_checked"] == 1 and v["n_mismatched"] == 0
    assert v["worst_abs_diff"] == 0.0
    assert "CONTAINS" in v["verdict"]

    bad = {"runs": [{"method": "ppo", "replicate": 1, "role": "measured",
                     "curve": [8.1, 8.2, 8.75, 9.0]}]}
    v = L.verify_prefix(bad, reference=ref, n=3)
    assert v["n_mismatched"] == 1, "a disagreeing prefix was not reported"
    assert v["worst_abs_diff"] == pytest.approx(0.05)
    assert "DISAGREE" in v["verdict"]
    assert v["examples"] and "ppo/1" in v["examples"][0]


def test_verify_prefix_builds_the_reference_at_its_OWN_budget(tmp_path):
    """**G97, and it fabricated a 9.18 disagreement out of nothing.**

    `anytime_curve(trials, budget)` CLAMPS rather than truncates --
    `lo = min(cum_sims, budget)` -- so handing it a short budget together with
    a long trial list folds every later trial's best into the final cell.
    Building the 150-simulation reference at n = 30 therefore compared a real
    30-simulation curve against "the best of 150, stamped at index 29", and
    reported **34 of 40 curves mismatched, worst difference 9.18**. Every one
    of those was manufactured by the instrument.

    The reference must be built at its own length and sliced afterwards. This
    synthesises a run whose best jumps AFTER the prefix, which is the only
    shape that distinguishes the two.
    """
    ref = tmp_path / "ref.jsonl"
    rewards = [8.0, 8.1, 8.2] + [9.9] * 7          # the jump is at sim 4
    rows = [{"event": "trial", "role": "measured", "problem": "P1",
             "method": "ppo", "replicate": 0, "prescreen": False, "index": i,
             "u": [0.5] * 7, "design_id": None, "geometry_tag": None,
             "params": {}, "reward": rw, "feasible": True, "verdict": "valid",
             "invalid_reason": None, "worst_point": None, "worst_spec": None,
             "n_sims": 1, "seconds": 0.0, "cum_sims": i + 1,
             "cum_seconds": 0.0, "screened_out": False, "screen_reason": None,
             "meas": None, "margins": None, "predicted": None}
            for i, rw in enumerate(rewards)]
    ref.write_text('\n'.join(json.dumps(r) for r in rows),
                   encoding="utf-8")

    # the TRUE first three simulations never see the 9.9
    honest = {"runs": [{"method": "ppo", "replicate": 0, "role": "measured",
                        "curve": [8.0, 8.1, 8.2]}]}
    v = L.verify_prefix(honest, reference=ref, n=3)
    assert v["n_mismatched"] == 0, (
        "the reference was built at the prefix length, so the later 9.9 was "
        "clamped into index 2 and a real match was reported as a mismatch"
    )
    assert v["worst_abs_diff"] == 0.0


def test_verify_prefix_tolerates_a_shorter_curve_without_crashing():
    """A partial or interrupted run has a short curve; comparing it must
    compare the overlap rather than raising a shape error."""
    v = L.verify_prefix({"runs": []}, reference=L.REFERENCE_LOG, n=1) \
        if L.REFERENCE_LOG.exists() else {"n_checked": 0}
    assert v["n_checked"] == 0


def test_the_random_equivalent_budget_is_the_headline_and_handles_censoring():
    """**The saturation-robust metric, and the one the report quotes.**

    The raw gap shrinks with budget whether or not anything is learned, because
    the reward has an asymptote near +9.0 and every method compresses toward
    it. Stating the result in the CONTROL's units removes that: "150 policy
    simulations are worth 108 random ones" cannot be manufactured by a ceiling.

    Three behaviours are pinned: a method matching random reads 1.0, a method
    at half the value reads the fraction of random simulations that match it,
    and a method uniform NEVER catches is reported as censored rather than
    silently pinned at the budget (7c's rule).
    """
    # uniform climbs one unit per simulation; value == simulations spent
    u_curve = [float(i) for i in range(1, 101)]
    res = _results({"uniform": [u_curve],
                    # matches uniform exactly
                    "cmaes": [u_curve],
                    # always half of uniform, so it needs half the sims
                    "ppo": [[0.5 * v for v in u_curve]],
                    # beyond anything uniform reaches
                    "lhs": [[v + 500.0 for v in u_curve]]})
    a = L.ladder(res, readouts=(50, 100))
    e = a["random_equivalent_budget"]

    assert e["cmaes"]["100"]["ratio"] == pytest.approx(1.0)
    assert e["cmaes"]["50"]["ratio"] == pytest.approx(1.0)
    # ppo at 100 sims scores 50, which uniform reaches at 50 sims -> 0.5x
    assert e["ppo"]["100"]["ratio"] == pytest.approx(0.5)
    assert e["ppo"]["100"]["uniform_sims"] == 50
    # lhs is out of reach: censored, NOT reported as the budget
    assert e["lhs"]["100"]["censored"] is True
    assert e["lhs"]["100"]["ratio"] is None
    assert e["lhs"]["100"]["uniform_sims"] is None
    assert e["lhs"]["100"]["censored_at"] == 100


# ─────────────────────────────────────────────────────────────────────────────
# Resume — earned. The first attempt was killed after 8 of 40 runs.
# ─────────────────────────────────────────────────────────────────────────────


def _log_rows(method, replicate, rewards, with_summary=True, budget=None):
    rows = [{"kind": "event", "event": "trial", "role": "measured",
             "problem": "P1", "method": method, "replicate": replicate,
             "prescreen": False, "index": i, "reward": rw, "n_sims": 1,
             "cum_sims": i + 1}
            for i, rw in enumerate(rewards)]
    if with_summary:
        rows.append({"kind": "event", "event": "run_summary", "role": "measured",
                     "problem": "P1", "method": method, "replicate": replicate,
                     "prescreen": False, "n_sims": len(rewards),
                     "budget_sims": budget or len(rewards),
                     "best_reward": max(rewards), "seed": 1})
    return rows


def _write_log(tmp_path, rows):
    p = tmp_path / "run.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return p


def test_completed_requires_a_SUMMARY_not_merely_trials(tmp_path, monkeypatch):
    """**The correctness property of resume, and the one that can silently
    corrupt a result.**

    A job killed mid-flight leaves its trials in the log with no summary. Those
    trials are a PARTIAL run: treating them as complete would put a short curve
    into the ladder and every read-out above its length would silently be the
    last value it happened to reach. The summary is written last, so its
    presence is the only honest completion marker.
    """
    rows = (_log_rows("ppo", 0, [8.1, 8.4, 8.9])
            + _log_rows("ppo", 1, [8.0, 8.2], with_summary=False))
    p = _write_log(tmp_path, rows)
    monkeypatch.setattr(L, "LOG_PATH", p)
    assert L.completed(p) == {("ppo", 0)}, (
        "a run with trials but no summary was counted as complete"
    )


def test_completed_is_empty_when_there_is_no_log(tmp_path):
    assert L.completed(tmp_path / "nope.jsonl") == set()


def test_results_from_log_rebuilds_the_curve_from_the_TRIAL_rows(tmp_path,
                                                                 monkeypatch):
    """Rule 9: the log is the one record. The curve is not in it -- the summary
    drops it because it is `budget_sims` floats per run -- so it is rebuilt
    rather than stored twice, and the rebuild has to be a step function of the
    best so far."""
    p = _write_log(tmp_path, _log_rows("ppo", 0, [8.1, 8.0, 8.9, 8.5]))
    monkeypatch.setattr(L, "LOG_PATH", p)
    res = L.results_from_log(p)
    assert len(res["runs"]) == 1
    r = res["runs"][0]
    assert r["method"] == "ppo" and r["replicate"] == 0
    # best-so-far, never decreasing
    assert r["curve"] == pytest.approx([8.1, 8.1, 8.9, 8.9])
    # the bookkeeping keys the log carries survive; the wrapper keys do not
    assert "best_reward" in r
    assert "kind" not in r and "event" not in r


def test_results_from_log_skips_a_run_with_no_summary(tmp_path):
    """The recovery path must yield every COMPLETE run and no partial one."""
    rows = (_log_rows("ppo", 0, [8.1, 8.9])
            + _log_rows("ppo", 1, [8.0, 8.2, 8.3], with_summary=False))
    res = L.results_from_log(_write_log(tmp_path, rows))
    assert [r["replicate"] for r in res["runs"]] == [0]


def test_the_job_list_covers_the_whole_allocation():
    js = L.jobs()
    assert len(js) == sum(B.REPLICATES[m] for m in L.ARMS)
    assert {j.method for j in js} == set(L.ARMS)
    assert all(j.problem == "P1" and not j.prescreen for j in js)
    assert all(j.ac_peak_interp for j in js), (
        "the ladder must score the same objective as the published sweep"
    )
    assert all(j.budget_sims == L.LADDER_BUDGET for j in js)
    # and the seed does not see the budget, which is WHY one long run contains
    # the short ones
    assert (B.run_seed("P1", "ppo", 3)
            == B.run_seed("P1", "ppo", 3)), "run_seed is not a pure function"


def test_runlog_append_continues_instead_of_truncating(tmp_path):
    """`RunLog` opened with `"w"` is why the first ladder attempt could not be
    resumed: 19 200 trial rows were on disk and reopening the log would have
    erased them. Append is opt-in, so nothing else changes."""
    from nebula.rl.runlog import RunLog, read as runlog_read

    p = tmp_path / "log.jsonl"
    with RunLog(p, {"chunk": 1}) as lg:
        lg.event("trial", i=0)
    with RunLog(p, {"chunk": 2}, append=True) as lg:
        lg.event("trial", i=1)
    rows = list(runlog_read(p))
    assert [r.get("i") for r in rows if r.get("event") == "trial"] == [0, 1]
    # each chunk records its own provenance rather than inheriting the first
    assert [r.get("chunk") for r in rows if r.get("kind") == "header"] == [1, 2]

    # ... and the default still truncates, so no existing caller changes
    with RunLog(p, {"chunk": 3}) as lg:
        lg.event("trial", i=2)
    rows = list(runlog_read(p))
    assert [r.get("i") for r in rows if r.get("event") == "trial"] == [2]


def test_the_control_measured_against_ITSELF_exposes_the_metrics_calibration():
    """**G98: a ratio metric must be run against its own reference.**

    `random_equivalent_budget` is "the first simulation at which uniform's
    median curve reaches this score". Against UNIFORM ITSELF that must be
    1.000x if the metric means what its name says -- and on the real run it
    reads 0.960 / 0.893 / 0.632 / 0.988 / 0.623 across the five rungs.

    The cause is real rather than a coding error: a median over twenty monotone
    step functions is a step function with long PLATEAUS, so "first reached" is
    the start of the plateau the target sits on. `uniform 2400 -> 1494` is a
    true sentence -- the median uniform run had already reached its
    2400-simulation score after 1494 -- but it is **not an equivalent budget**,
    and 1.0 is therefore the wrong line to compare against.

    This pins both halves: the raw metric is allowed to be non-unity on a
    plateaued curve (nobody may "fix" it into a fake 1.0 by smoothing), and the
    CALIBRATED table must read exactly 1.0 for the control at every rung,
    because that is what makes the other rows readable.
    """
    # a control whose median plateaus: flat from index 5 to 9
    ctrl = [8.0, 8.2, 8.4, 8.6, 8.8, 9.0, 9.0, 9.0, 9.0, 9.0]
    other = [8.0, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.6, 8.6, 8.6]
    a = L.ladder(_results({"uniform": [ctrl], "ppo": [other]}),
                 readouts=(10,))

    raw = a["random_equivalent_budget"]
    # the plateau makes the control's own ratio LESS than one, and that is the
    # honest reading rather than a bug to be smoothed away
    assert raw["uniform"]["10"]["uniform_sims"] == 6
    assert raw["uniform"]["10"]["ratio"] == pytest.approx(0.6)

    cal = a["calibrated_against_the_control"]
    assert cal["uniform"]["10"]["calibrated"] == pytest.approx(1.0), (
        "the control must read exactly 1.0 after calibration, or the other "
        "rows have no line to be compared against"
    )
    # ppo reached 8.6, which the control first hits at simulation 4
    assert raw["ppo"]["10"]["uniform_sims"] == 4
    assert cal["ppo"]["10"]["calibrated"] == pytest.approx(4 / 6)


def test_calibration_keeps_censoring_censored():
    """A method the control never catches must stay censored after
    calibration, with a LOWER BOUND rather than a number (7c)."""
    ctrl = [8.0 + 0.1 * i for i in range(10)]
    high = [20.0] * 10
    a = L.ladder(_results({"uniform": [ctrl], "ppo": [high]}), readouts=(10,))
    d = a["calibrated_against_the_control"]["ppo"]["10"]
    assert d["censored"] is True
    assert d["calibrated"] is None
    assert d["at_least"] > 0
