"""Gates for `experiments/exp_rl_diagnose.py` -- entry 42.

**NO SPICE ANYWHERE IN THIS FILE.** Every expensive path is patched with
something that RAISES, not something that counts (G122): a counter still lets
the real call through if the wrong name was patched, and this module's
`run_arm_a`/`run_arm_b` would each start a multi-thousand-deck sweep.

The gates are grouped by what they protect:

* the pre-registered CONSTANTS, so a post-hoc edit to a threshold is a red test
  rather than an invisible diff (G110);
* the two STATISTICS entry 42 scores on, whose definitions were fixed before
  the run;
* `_no_revert_step`, arm A4's only difference from `ScreenEnv`, driven against
  a fake env so the behaviour is checked without a simulator;
* `transect_endpoints`, which must RAISE rather than quietly return a shorter
  transect set (G115: a silently filtered contract is a contract violation);
* the artifact path, which must not collide with any other experiment's
  (G113/G128).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

import nebula.experiments.exp_rl_diagnose as D


# ---------------------------------------------------------------------------
# the pre-registered constants
# ---------------------------------------------------------------------------

def test_the_preregistered_thresholds_are_entry_42s():
    """Entry 42 fixed all five. A later edit must show up here, not in a diff
    nobody reads (G110)."""
    assert D.Q4_INFORMATIVE_DELTA == 0.05
    assert D.Q4_MEDIAN_MAX == 0.5
    assert (D.Q1_REVERTS_LO, D.Q1_REVERTS_HI) == (36, 60)
    assert D.Q3_MEDIAN_F_PEAK_HZ == 4.0e9
    assert D.ENTRY41_Q3_REVERTS == (16, 0, 16, 0, 16, 0, 0, 0)
    assert D.ENTRY41_Q3_DECKS == 636
    assert D.HORIZON == 16 and D.N_INTERIOR == 9


def test_q1_band_is_plus_minus_25_percent_of_entry_41s_48_reverts():
    """The band in the entry is '+-25 % of 48'. 36 and 60 are that, and the
    test states the arithmetic so the two cannot drift apart."""
    assert D.Q1_REVERTS_LO == round(48 * 0.75)
    assert D.Q1_REVERTS_HI == round(48 * 1.25)
    assert sum(D.ENTRY41_Q3_REVERTS) == 48


def test_the_four_arms_are_the_four_entry_42_registered():
    names = [a[0] for a in D.ARMS_A]
    assert names == ["det", "sto", "best4", "norevert"]
    by = {a[0]: a[1:] for a in D.ARMS_A}
    assert by["det"] == ("det", True, 1)          # entry 41's Q3, reproduced
    assert by["sto"] == ("sto", True, 1)          # hypothesis 1's remedy
    assert by["best4"] == ("sto", True, 4)        # best-of-N
    assert by["norevert"] == ("det", False, 1)    # the revert removed


def test_arm_a_changes_deployment_only_and_never_the_reward_or_specs():
    """The arms differ in action sampling, restart count and the revert rule.
    None of them may reach a tolerance, a spec set or a screen point."""
    src = Path(D.__file__).read_text(encoding="utf-8")
    for forbidden in ("TOL[", "V6_SPECS =", "EDGE4_MANDATED =",
                      "invalid_reward =", "reward_v1.TOL"):
        assert forbidden not in src, f"{forbidden!r} would redefine a contract"
    # V6_SPECS and EDGE4_MANDATED may be READ; arm B scores through them.
    assert "specs=R.V6_SPECS" in src
    assert "EDGE4_MANDATED" in src


# ---------------------------------------------------------------------------
# Q4's statistic
# ---------------------------------------------------------------------------

def test_informative_fraction_counts_intervals_not_points():
    """9 points give 8 intervals. A statistic over points would report 9/9."""
    assert D.informative_fraction([0.0, 1.0, 2.0]) == 1.0
    assert D.informative_fraction([0.0, 0.0, 0.0]) == 0.0
    assert D.informative_fraction([0.0, 0.0, 1.0]) == 0.5


def test_informative_fraction_uses_a_strict_threshold():
    """Exactly `delta` is NOT informative; the entry says 'more than 0.05'."""
    assert D.informative_fraction([0.0, 0.05]) == 0.0
    assert D.informative_fraction([0.0, 0.0500001]) == 1.0


def test_informative_fraction_treats_an_unscorable_endpoint_as_uninformative():
    """The docstring's reason: under the revert that step is undone, so the
    -16 floor is a number the dynamics throw away. A naive implementation that
    substituted the floor would report this interval as informative."""
    assert D.informative_fraction([-2.0, None, -2.0]) == 0.0
    assert D.informative_fraction([-2.0, None, 14.0]) == 0.0


def test_informative_fraction_is_none_for_a_degenerate_transect():
    assert D.informative_fraction([]) is None
    assert D.informative_fraction([1.0]) is None


def test_a_flat_plateau_and_a_ramp_are_distinguishable():
    """G125: the gate's DATA must separate the correct rule from a broken one.
    A transect that is flat then jumps scores 1/8, not 0 and not 1."""
    flat_then_jump = [-2.0] * 8 + [14.0]
    assert D.informative_fraction(flat_then_jump) == pytest.approx(1 / 8)
    ramp = list(np.linspace(-2.0, 14.0, 9))
    assert D.informative_fraction(ramp) == 1.0


# ---------------------------------------------------------------------------
# Q3's statistic
# ---------------------------------------------------------------------------

def _v(step, scorable, f, feasible=False, reward=0.0):
    return {"step": step, "scorable": scorable, "f_peak_hz": f,
            "feasible": feasible, "reward": reward, "u": [0.5] * 7}


def test_delivered_f_peak_is_the_LAST_scorable_reading():
    vis = [_v(0, True, 2.0e9), _v(1, True, 5.0e9), _v(2, False, None)]
    assert D.delivered_f_peak_hz(vis) == 5.0e9


def test_delivered_f_peak_is_none_when_nothing_was_measurable():
    """A design that could not be measured has no peak frequency. Defaulting
    one would invent a number (standing rule 1)."""
    assert D.delivered_f_peak_hz([_v(0, False, None), _v(1, False, None)]) is None


def test_delivered_f_peak_ignores_a_scorable_row_with_no_peak():
    assert D.delivered_f_peak_hz([_v(0, True, 3.0e9), _v(1, True, None)]) == 3.0e9


def test_best_feasible_picks_the_highest_reward_feasible_design():
    vis = [_v(0, True, 2e9, feasible=True, reward=14.1),
           _v(1, True, 2e9, feasible=True, reward=14.4),
           _v(2, True, 2e9, feasible=False, reward=99.0)]
    assert D.best_feasible(vis)["reward"] == 14.4
    assert D.best_feasible([_v(0, True, 2e9)]) is None


# ---------------------------------------------------------------------------
# arm A4 -- the no-revert step
# ---------------------------------------------------------------------------

class _Ev:
    def __init__(self, ok, reward, feasible=False):
        self.ok, self.reward, self.feasible = ok, reward, feasible
        self.reason = None if ok else "unscorable"
        self.n_sims = 4
        self.worst_spec = "S3_f_peak_match"
        self.f_peak_hz = 2.0e9 if ok else None
        self.peaking_db = 8.0 if ok else None


class _FakeEnv:
    """The minimum `_no_revert_step` touches. No SPICE, no ngspice, no PDK."""

    def __init__(self, evs):
        self._evs, self._i = list(evs), 0
        self._u = np.full(7, 0.5)
        self._step, self.horizon, self.max_step = 0, 3, 0.05
        self._last = _Ev(True, -2.0)
        self.n_kept_unscorable = 0
        self.obs_calls = []

    def _evaluate(self, u):
        ev = self._evs[min(self._i, len(self._evs) - 1)]
        self._i += 1
        return ev

    def _obs(self, ev):
        self.obs_calls.append(ev)
        return np.zeros(18)


def test_no_revert_step_KEEPS_the_edit_when_the_design_is_unscorable():
    """**Arm A4's entire content.** `ScreenEnv.step` restores `u` here; this
    must not, or the walk can never leave the region it started in."""
    env = _FakeEnv([_Ev(False, -16.0)])
    before = env._u.copy()
    D._no_revert_step(env, np.ones(7))
    assert not np.allclose(env._u, before)
    assert env._u == pytest.approx(before + 0.05)
    assert env.n_kept_unscorable == 1


def test_screen_env_itself_still_reverts_so_the_control_is_a_real_control():
    """A1 must be entry 41's deployment. If the parent stopped reverting, A1
    and A4 would measure the same thing and Q5 would pass vacuously."""
    from nebula.rl.screen_env import ScreenEnv

    src = Path(ScreenEnv.__module__.replace(".", "/") + ".py")
    text = (Path(__file__).resolve().parents[1] / "rl" / "screen_env.py"
            ).read_text(encoding="utf-8")
    assert "self._u = u_before" in text, "ScreenEnv no longer reverts"
    assert D._NoRevertScreenEnv.step is not ScreenEnv.step
    assert issubclass(D._NoRevertScreenEnv, ScreenEnv)


def test_no_revert_step_reports_the_last_TRUE_observation_and_the_floor_reward():
    """Keeping the edit must not mean inventing a measurement. The observation
    stays the last real one and the reward stays the graded invalid floor."""
    env = _FakeEnv([_Ev(False, -16.0)])
    true_last = env._last
    obs, reward, term, trunc, info = D._no_revert_step(env, np.ones(7))
    assert reward == -16.0
    assert env.obs_calls[-1] is true_last
    assert info["kept_unscorable"] is True and info["reverted"] is False
    assert term is False


def test_no_revert_step_does_not_terminate_early_on_success():
    """G100: an episode that ends on the condition the metric rewards
    exceeding is two objectives, not one."""
    env = _FakeEnv([_Ev(True, 14.2, feasible=True)])
    _obs, reward, term, trunc, info = D._no_revert_step(env, np.zeros(7))
    assert reward == 14.2 and info["feasible"] is True
    assert term is False and trunc is False


def test_no_revert_step_truncates_at_the_horizon():
    env = _FakeEnv([_Ev(True, -2.0)])
    for t in range(1, 4):
        *_, trunc, _info = D._no_revert_step(env, np.zeros(7))
    assert trunc is True


def test_no_revert_step_clips_u_into_the_box():
    env = _FakeEnv([_Ev(True, -2.0)])
    env._u = np.full(7, 0.99)
    D._no_revert_step(env, np.ones(7))
    assert np.all(env._u <= 1.0) and np.all(env._u >= 0.0)


def test_no_revert_step_rejects_a_malformed_action():
    env = _FakeEnv([_Ev(True, -2.0)])
    with pytest.raises(ValueError):
        D._no_revert_step(env, np.ones(3))
    with pytest.raises(ValueError):
        D._no_revert_step(env, np.full(7, np.nan))


def test_make_env_returns_the_no_revert_subclass_only_when_asked(monkeypatch):
    """`make_env` must not silently hand arm A1 the A4 environment."""
    built = {}

    class _Stub:
        def __init__(self, targets, seed, horizon):
            built["cls"] = type(self).__name__

    monkeypatch.setattr(D, "ScreenEnv", _Stub)
    monkeypatch.setattr(D, "_NoRevertScreenEnv", type("_NR", (_Stub,), {}))
    D.make_env(object(), 1, revert=True)
    assert built["cls"] == "_Stub"
    D.make_env(object(), 1, revert=False)
    assert built["cls"] == "_NR"


def test_rollout_once_rejects_an_unknown_mode():
    with pytest.raises(ValueError):
        D.rollout_once(None, None, 1, "greedy", True)


# ---------------------------------------------------------------------------
# arm B -- the endpoints
# ---------------------------------------------------------------------------

def _scan(idx_to_cands):
    return {"requests": [{"index": i, "peaking_db": 8.0,
                          "f_peak_hz": 1.921e9, "candidates": c}
                         for i, c in idx_to_cands.items()]}


def _cand(u, reward, feasible=False, f=2.0e9):
    return {"u": list(u), "reward": reward, "feasible": feasible,
            "f_peak_hz_got": f, "rank": 1}


def test_transect_endpoints_pairs_the_best_of_each_end():
    lib = _scan({2: [_cand([0.1] * 7, 14.26, True), _cand([0.2] * 7, 14.35, True),
                     _cand([0.3] * 7, -2.0)]})
    sac = _scan({2: [_cand([0.9] * 7, -3.5), _cand([0.8] * 7, -2.1)]})
    got = D.transect_endpoints(lib, sac)
    assert len(got) == 1
    assert got[0]["u_lib"] == [0.2] * 7 and got[0]["reward_lib"] == 14.35
    assert got[0]["u_sac"] == [0.8] * 7 and got[0]["reward_sac"] == -2.1


def test_transect_endpoints_skips_requests_the_library_did_not_solve():
    lib = _scan({2: [_cand([0.1] * 7, 14.2, True)],
                 3: [_cand([0.4] * 7, -2.0)]})
    sac = _scan({2: [_cand([0.9] * 7, -3.0)], 3: [_cand([0.9] * 7, -3.0)]})
    assert [t["index"] for t in D.transect_endpoints(lib, sac)] == [2]


def test_transect_endpoints_RAISES_on_a_missing_counterpart():
    """G115: `[x for x in CONTRACT if available]` is a silent contract
    violation. A shorter transect set would report a weaker barrier than was
    measured, and nothing in the artifact would say so."""
    lib = _scan({2: [_cand([0.1] * 7, 14.2, True)]})
    with pytest.raises(ValueError, match="absent from the SAC scan"):
        D.transect_endpoints(lib, _scan({7: [_cand([0.9] * 7, -3.0)]}))


def test_transect_endpoints_RAISES_when_the_sac_scan_scored_nothing():
    lib = _scan({2: [_cand([0.1] * 7, 14.2, True)]})
    sac = {"requests": [{"index": 2, "peaking_db": 8.0, "f_peak_hz": 1.921e9,
                         "candidates": [{"error": "boom"}]}]}
    with pytest.raises(ValueError, match="no scored SAC candidate"):
        D.transect_endpoints(lib, sac)


def test_transect_endpoints_RAISES_when_nothing_can_be_paired():
    with pytest.raises(ValueError, match="nothing to transect"):
        D.transect_endpoints(_scan({2: [_cand([0.1] * 7, -2.0)]}),
                             _scan({2: [_cand([0.9] * 7, -3.0)]}))


def test_the_real_committed_scans_yield_the_six_transects_entry_42_registered():
    """Entry 42 says 'the 6 requests where the library found a screen-feasible
    design'. If either artifact moves, this reddens instead of the run
    measuring a different experiment."""
    if not (D.LIB_SCAN.exists() and D.SAC_SCAN.exists()):
        pytest.skip("scan artifacts not present in this checkout")
    pairs = D.transect_endpoints(
        json.loads(D.LIB_SCAN.read_text(encoding="utf-8")),
        json.loads(D.SAC_SCAN.read_text(encoding="utf-8")))
    assert [p["index"] for p in pairs] == [2, 4, 7, 9, 11, 14]
    assert all(p["reward_lib"] > 14.0 for p in pairs)
    assert all(p["reward_sac"] < 0.0 for p in pairs)
    # the disclosed observation: every SAC endpoint is at the sweep edge
    assert all(p["f_peak_sac_hz"] > 19.0e9 for p in pairs)


def test_arm_b_deck_cost_is_the_registered_216():
    if not (D.LIB_SCAN.exists() and D.SAC_SCAN.exists()):
        pytest.skip("scan artifacts not present in this checkout")
    pairs = D.transect_endpoints(
        json.loads(D.LIB_SCAN.read_text(encoding="utf-8")),
        json.loads(D.SAC_SCAN.read_text(encoding="utf-8")))
    assert len(pairs) * D.N_INTERIOR * 4 == 216


def test_run_arm_b_never_scores_an_endpoint(monkeypatch):
    """The endpoints are already measured in the two committed scans;
    re-measuring them would spend 48 decks to reproduce numbers on disk."""
    seen = []

    def _fake(u, points, target_f_peak_hz, target_peaking_db, specs):
        seen.append(np.asarray(u, dtype=float).copy())
        return _DesignEvalStub()

    import nebula.experiments.adaptive_screen as A
    monkeypatch.setattr(A, "evaluate_at_points", _fake)
    pair = {"index": 2, "peaking_db": 8.0, "f_peak_hz": 1.921e9,
            "u_sac": [0.0] * 7, "u_lib": [1.0] * 7,
            "reward_sac": -2.0, "reward_lib": 14.2,
            "f_peak_sac_hz": 19.95e9, "f_peak_lib_hz": 2.0e9}
    out = D.run_arm_b([pair], n_interior=9)
    assert len(seen) == 9
    assert not any(np.allclose(u, 0.0) for u in seen)
    assert not any(np.allclose(u, 1.0) for u in seen)
    assert out["transects"][0]["u_distance"] == pytest.approx(np.sqrt(7))


class _DesignEvalStub:
    ok, reward, feasible, n_scorable, n_sims = True, -2.0, False, 4, 4
    worst_spec, f_peak_hz, peaking_db, reason = "S3_f_peak_match", 2e9, 8.0, None


# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------

def _arm(name, **kw):
    base = {"arm": name, "n_feasible_designs": 0, "total_reverted": 48,
            "total_kept_unscorable": 0,
            "n_compliant": 0, "compliant_indices": [],
            "median_delivered_f_peak_hz": 19.95e9, "n_delivered": 8,
            "reverts_per_request": list(D.ENTRY41_Q3_REVERTS),
            "total_decks": D.ENTRY41_Q3_DECKS, "requests": []}
    base.update(kw)
    return base


def _doc(**over):
    d = {"arms_a": [_arm("det"), _arm("sto"), _arm("best4"), _arm("norevert")],
         "arm_b": {"median_informative_fraction": 0.25, "total_unscorable": 10,
                   "total_interior_points": 54, "total_feasible": 0}}
    d.update(over)
    return d


def test_score_reads_all_five_and_the_all_pass_case_scores_five():
    s = D.score(_doc())
    assert s["n_scored"] == 5 and s["n_pass"] == 5


def test_q1_fails_when_a_single_feasible_design_appears():
    d = _doc()
    d["arms_a"][1]["n_feasible_designs"] = 1
    assert D.score(d)["Q1"]["pass"] is False


def test_q1_fails_outside_the_revert_band():
    for n, ok in ((35, False), (36, True), (60, True), (61, False)):
        d = _doc()
        d["arms_a"][1]["total_reverted"] = n
        assert D.score(d)["Q1"]["pass"] is ok, n


def test_q2_headline_and_secondary_are_scored_separately():
    d = _doc()
    d["arms_a"][2]["n_feasible_designs"] = 3
    s = D.score(d)
    assert s["Q2"]["pass"] is True            # still 0 compliant
    assert s["Q2"]["secondary_pass"] is True  # but it found feasible designs
    d["arms_a"][2]["n_compliant"] = 1
    assert D.score(d)["Q2"]["pass"] is False


def test_q3_is_strict_above_4_ghz():
    for f, ok in ((3.9e9, False), (4.0e9, False), (4.1e9, True)):
        d = _doc()
        d["arms_a"][3]["median_delivered_f_peak_hz"] = f
        assert D.score(d)["Q3"]["pass"] is ok, f


def test_q3_is_a_miss_when_nothing_was_measurable():
    d = _doc()
    d["arms_a"][3]["median_delivered_f_peak_hz"] = None
    assert D.score(d)["Q3"]["pass"] is False


def test_q4_is_at_most_one_half():
    for fr, ok in ((0.5, True), (0.501, False), (0.0, True)):
        d = _doc()
        d["arm_b"]["median_informative_fraction"] = fr
        assert D.score(d)["Q4"]["pass"] is ok, fr


def test_q5_fails_on_any_per_request_revert_difference():
    d = _doc()
    d["arms_a"][0]["reverts_per_request"] = [16, 0, 16, 0, 0, 16, 0, 0]
    assert D.score(d)["Q5"]["pass"] is False


def test_q5_fails_on_a_deck_count_difference():
    d = _doc()
    d["arms_a"][0]["total_decks"] = 640
    assert D.score(d)["Q5"]["pass"] is False


def test_score_omits_a_question_whose_arm_did_not_run():
    s = D.score({"arms_a": [], "arm_b": None})
    assert s["n_scored"] == 0 and s["n_pass"] == 0


# ---------------------------------------------------------------------------
# artifacts and the CLI
# ---------------------------------------------------------------------------

def test_the_results_path_collides_with_no_other_experiment(tmp_path):
    """G113/G128: a completed run must not be able to overwrite a completed
    run, and identity is the whole filename, not half of it."""
    assert D.RESULTS.name == "rl_diagnose_results.json"
    others = {p.name for p in D.HERE.glob("*.json")} - {D.RESULTS.name}
    assert D.RESULTS.name not in others
    for owned in ("hybrid_topk_scan.json", "topk_scan_library_k5.json",
                  "sac_q3_results.json", "sac_propose_results.json",
                  "coverage_results_AFTER_unclip_fix.json"):
        assert D.RESULTS.name != owned


def test_arm_b_reads_the_two_scans_and_writes_neither():
    src = Path(D.__file__).read_text(encoding="utf-8")
    assert "LIB_SCAN.read_text" in src and "SAC_SCAN.read_text" in src
    assert "LIB_SCAN.write" not in src and "SAC_SCAN.write" not in src
    # Every write_text in the module is RESULTS'; there are three (the arm-B
    # checkpoint, the per-arm checkpoint, and none other), and no other path
    # is ever written.
    assert src.count("write_text") == src.count("RESULTS.write_text")


def test_cli_rejects_an_unknown_arm_without_running_anything(monkeypatch):
    """G129: the guard must be reachable without calling the expensive entry
    point. If `main` ran first and validated second, this test would spend
    thousands of decks."""
    def _boom(*a, **kw):
        raise AssertionError("run() must not be called for an invalid --arm")

    monkeypatch.setattr(D, "run", _boom)
    with pytest.raises(SystemExit):
        D.main(["--run", "--arm", "z"])


def test_cli_without_run_or_analyse_does_nothing_expensive(monkeypatch):
    monkeypatch.setattr(D, "run", lambda *a, **kw: (_ for _ in ()).throw(
        AssertionError("run() called without --run")))
    assert D.main([]) == 0


def test_run_takes_the_lock_before_it_loads_anything(monkeypatch):
    """G113: a run that starts alongside another inflates both wall clocks and
    can overwrite the survivor's artifact. The lock is the refusal."""
    # slice to `run()`'s own body: the call sites, not the definitions.
    whole = Path(D.__file__).read_text(encoding="utf-8")
    body = whole[whole.index("def run(ckpt: Path = CKPT"):]
    body = body[:body.index("def _report(")]
    i_hold = body.index('with hold("rl_diagnose"')
    for after in ("load_agent(Path(ckpt))", "run_arm_a(", "run_arm_b(",
                  "RESULTS.write_text"):
        assert after in body, f"{after} is not called by run() at all"
        assert body.index(after) > i_hold, f"{after} runs outside the lock"


def test_report_renders_a_complete_document_without_raising(capsys):
    """G112: a format error in the cheap reporting phase must not be found
    after 4 500 decks have been spent. `_report` is exercised on the same
    synthetic document the scorer is."""
    d = _doc()
    for a in d["arms_a"]:
        a["requests"] = [{"n_scorable_evals": 10, "n_evals": 17}]
    d["arm_b"]["transects"] = [{}] * 6
    d["arm_b"]["n_interior"] = 9
    d["arm_b"]["total_decks"] = 216
    d["score"] = D.score(d)
    D._report(d)
    out = capsys.readouterr().out
    assert "ENTRY 42" in out and "SCORE 5 of 5" in out
    assert "ARM B" in out and "norevert" in out


def test_report_survives_a_run_with_only_arm_b(capsys):
    d = {"arms_a": [], "arm_b": {"median_informative_fraction": 0.1,
                                 "total_unscorable": 3,
                                 "total_interior_points": 54,
                                 "total_feasible": 0, "n_interior": 9,
                                 "total_decks": 216, "transects": [{}] * 6}}
    d["score"] = D.score(d)
    D._report(d)
    assert "ARM B" in capsys.readouterr().out


def test_report_has_no_non_ascii(capsys):
    """Windows cp1252 console: a non-ASCII glyph in print() is a crash at the
    end of an hour-long run (CLAUDE.md rule 7)."""
    d = _doc()
    for a in d["arms_a"]:
        a["requests"] = [{"n_scorable_evals": 10, "n_evals": 17}]
    d["arm_b"].update({"transects": [{}] * 6, "n_interior": 9,
                       "total_decks": 216})
    d["score"] = D.score(d)
    D._report(d)
    capsys.readouterr().out.encode("cp1252")


def test_arm_b_is_checkpointed_before_arm_a_spends_anything():
    """G112 lever 3: make the expensive phase's predecessor durable. Arm B's
    216 decks are written to the artifact before arm A's ~4 500 begin."""
    whole = Path(D.__file__).read_text(encoding="utf-8")
    body = whole[whole.index("def run(ckpt: Path = CKPT"):]
    body = body[:body.index("def _report(")]
    assert body.index('if "b" in arms:') < body.index('if "a" in arms:')
    assert body.index("RESULTS.write_text") < body.index("run_arm_a(")
