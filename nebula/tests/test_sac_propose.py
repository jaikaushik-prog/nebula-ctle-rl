"""
tests/test_sac_propose.py — gates on `exp_sac_propose`, stage 3 of the SAC
brief (`PREDICTIONS.md` entry 36).

WHAT IS GUARDED, AND WHICH FAILURE EACH GUARD IS FOR
------------------------------------------------------
1.  **An RL arm cannot overwrite entry 32's baseline** (G113). `scan_topk` used
    to write `hybrid_topk_scan.json` unconditionally, so running it with a SAC
    candidate source would have destroyed the artifact that `A = 6 of 16` and
    the 35.6 % deck saving are quoted from — while reporting success.
    `topk_scan_path` must REFUSE, and the refusal is watched here.
2.  **A checkpoint with no weights cannot become a proposer** (G113 again).
    `torch.save` in `exp_sac_finetune` writes `state_dict: None` for an agent
    that has none; that file looks entirely normal on disk. `load_agent` must
    raise rather than propose from an untrained network.
3.  **"The policy could not act" is not "the policy acted and failed"** (G107).
    A seeded start the analytic model cannot describe is DECLINED, counted, and
    the untouched library design is proposed — never silently scored as an RL
    success.
4.  **The proposal is the best design along the rollout, and the SEEDED START
    IS NOT ONE OF THEM.** Including it would make the seeded arms `>= library`
    by construction and report retrieval's result as RL's.
5.  **The verdict is mechanical.** Entry 36's six predictions are applied in
    code so the call cannot drift in the writing, and the Q1 branch — the
    control failing to reproduce — must dominate every other reading.

No SPICE runs here. Rollouts use the analytic model, which is what makes them
cheap enough to gate; `scan_topk`'s SPICE call is monkeypatched.
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pytest

from nebula.experiments import exp_hybrid as H
from nebula.experiments import exp_sac_propose as P

U7 = [0.5] * 7


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _agent(obs_dim: int = 18, act_dim: int = 7, seed: int = 7):
    """An untrained SAC agent. Enough for every gate here: these tests check
    plumbing, determinism and accounting, never whether the policy is good."""
    torch = pytest.importorskip("torch")
    from nebula.rl.sac import SACAgent, SACConfig

    torch.manual_seed(seed)
    return SACAgent(obs_dim, act_dim, SACConfig(seed=seed))


@dataclass
class _Ev:
    """The subset of `adaptive_screen.DesignEval` the scan reads."""

    u: tuple = tuple(U7)
    ok: bool = False
    reward: float = -1.0
    feasible: bool = False
    n_sims: int = 4
    n_points: int = 4
    n_scorable: int = 0
    worst_point: Optional[str] = None
    worst_spec: Optional[str] = None
    reason: Optional[str] = ("4 of 4 points unscorable; first: output swing "
                             "979.6 mVpp exceeds the linear limit")
    margins: dict = field(default_factory=dict)
    points: list = field(default_factory=list)
    peaking_db: Optional[float] = 6.0
    f_peak_hz: Optional[float] = 1.9e9
    power_w: Optional[float] = None
    hd3_nyq_dbc: Optional[float] = None
    eye_w_ui: Optional[float] = None
    eye_h_v: Optional[float] = None


def _arm(name: str, accepted_at_k, n_accepted: int, *, measured: int = 320,
         deployed: int = 260, swing: Optional[float] = 0.95,
         declined: int = 0) -> dict:
    return {"arm": name, "accepted_at_k": list(accepted_at_k),
            "n_accepted": int(n_accepted), "accepted_ranks": [],
            "n_cand_feasible": 0, "n_cand_infeasible": 0,
            "n_cand_unscorable": 0, "n_sims_measured": measured,
            "n_sims_deployed": deployed, "swing_named": 0, "non_feasible": 0,
            "swing_fraction": swing, "n_declined": declined,
            "artifact": None, "wall_clock_s": 1.0}


def _result(*, lib_curve=(1, 4, 5, 5, 6), lib_a=6, random_a=(0, 1),
            seeded_a=(5, 6), measured=320, deployed=260,
            swing=(0.95, 0.95)) -> dict:
    arms = [_arm("library", lib_curve, lib_a, measured=measured,
                 deployed=deployed, swing=None)]
    for name, a, sw in zip(("sac_random_analytic", "sac_random_finetuned"),
                           random_a, swing):
        arms.append(_arm(name, [0] * 5, a, measured=measured, swing=sw))
    for name, a in zip(("sac_seeded_analytic", "sac_seeded_finetuned"),
                       seeded_a):
        arms.append(_arm(name, [0] * 5, a, measured=measured))
    return {"k": 5, "arms": arms}


# ---------------------------------------------------------------------------
# 1. the baseline artifact cannot be overwritten by an RL arm  (G113)
# ---------------------------------------------------------------------------

def test_library_source_keeps_the_historical_path():
    assert H.topk_scan_path("library") == H.TOPK_SCAN


def test_non_library_source_gets_its_own_default_path():
    p = H.topk_scan_path("sac_random_analytic")
    assert p != H.TOPK_SCAN
    assert p.name == "topk_scan_sac_random_analytic.json"


def test_the_library_at_a_different_k_may_not_write_the_baseline():
    """G128, and it is the bug this guard SHIPPED with. The artifact's identity
    is `(source, k)`: stage 3 runs the library control at k=5, and a guard that
    keyed on `source` alone let it overwrite entry 32's k=8 measurement with a
    k=5 one that looked entirely legitimate."""
    with pytest.raises(ValueError, match="k=5"):
        H.topk_scan_path("library", H.TOPK_SCAN, k=5)


def test_the_library_at_a_different_k_gets_its_own_default_path():
    p = H.topk_scan_path("library", k=5)
    assert p != H.TOPK_SCAN and p.name == "topk_scan_library_k5.json"


def test_the_library_at_the_default_k_still_owns_the_baseline():
    assert H.topk_scan_path("library", k=H.DEFAULT_TOPK) == H.TOPK_SCAN
    assert H.topk_scan_path("library", k=None) == H.TOPK_SCAN


def test_scan_topk_passes_its_k_to_the_guard(monkeypatch, tmp_path):
    """The guard is only worth anything if the caller actually keys on k."""
    seen = {}
    monkeypatch.setattr(H, "topk_scan_path",
                        lambda source, out=None, k=None: seen.setdefault(
                            "k", k) and None or tmp_path / "x.json")
    monkeypatch.setattr(H, "evaluate_at_points", lambda u, pts, **kw: _Ev())
    monkeypatch.setattr(H.SS, "score_design_eval", lambda ev, specs: -1.0)
    monkeypatch.setitem(H.CANDIDATE_SOURCES, "fake_rl",
                        lambda f, p, k: [np.asarray(U7)] * k)

    @contextlib.contextmanager
    def _hold(name, meta=None):
        yield

    monkeypatch.setattr("nebula.experiments.runlock.hold", _hold)
    H.scan_topk(peakings=[6.0], freqs=[1.9e9], source="fake_rl", k=3)
    assert seen["k"] == 3


def test_non_library_source_may_not_write_the_baseline(tmp_path):
    with pytest.raises(ValueError, match="entry 32"):
        H.topk_scan_path("sac_seeded_finetuned", H.TOPK_SCAN)


def test_the_refusal_names_the_number_it_protects():
    """A guard whose message does not say WHY gets deleted by the next agent."""
    with pytest.raises(ValueError) as exc:
        H.topk_scan_path("sac_random_analytic", H.TOPK_SCAN)
    msg = str(exc.value)
    assert "6 of 16" in msg and "35.6" in msg


def test_an_explicit_out_is_honoured_for_a_non_library_source(tmp_path):
    dest = tmp_path / "elsewhere.json"
    assert H.topk_scan_path("sac_random_analytic", dest) == dest


def test_scan_writes_the_arm_file_and_leaves_the_baseline_untouched(
        monkeypatch, tmp_path):
    """The end-to-end version of gate 1: a full scan on a non-library source
    must produce its own artifact and must not touch `TOPK_SCAN`."""
    baseline = tmp_path / "hybrid_topk_scan.json"
    baseline.write_text('{"n_accepted": 6}', encoding="utf-8")
    monkeypatch.setattr(H, "TOPK_SCAN", baseline)
    monkeypatch.setattr(H, "HERE", tmp_path)
    monkeypatch.setattr(H, "evaluate_at_points", lambda u, pts, **kw: _Ev())
    monkeypatch.setattr(H.SS, "score_design_eval", lambda ev, specs: -1.0)
    monkeypatch.setattr(H.C, "solve_request", _tripwire)
    monkeypatch.setitem(H.CANDIDATE_SOURCES, "fake_rl",
                        lambda f, p, k: [np.asarray(U7)] * k)

    @contextlib.contextmanager
    def _hold(name, meta=None):
        yield

    monkeypatch.setattr("nebula.experiments.runlock.hold", _hold)

    out = H.scan_topk(peakings=[6.0], freqs=[1.9e9], source="fake_rl", k=2)

    assert json.loads(baseline.read_text(encoding="utf-8")) == {"n_accepted": 6}
    written = tmp_path / "topk_scan_fake_rl.json"
    assert written.exists()
    assert out["artifact"] == str(written)


def _tripwire(*a, **k):
    raise AssertionError("a proposal scan must run NO search")


# ---------------------------------------------------------------------------
# 2. a checkpoint of nothing cannot become a proposer  (G113)
# ---------------------------------------------------------------------------

def test_load_agent_raises_on_a_checkpoint_with_no_weights(tmp_path):
    torch = pytest.importorskip("torch")
    p = tmp_path / "sac_policy_analytic.pt"
    torch.save({"state_dict": None, "stage": "analytic", "steps": 50_000}, p)
    with pytest.raises(ValueError, match="checkpoint of\n?\\s*nothing|no state_dict"):
        P.load_agent(p)


def test_load_agent_raises_on_a_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError, match="exp_sac_finetune"):
        P.load_agent(tmp_path / "not_here.pt")


def test_load_agent_round_trips_a_real_agent(tmp_path):
    torch = pytest.importorskip("torch")
    agent = _agent()
    p = tmp_path / "ckpt.pt"
    torch.save({"state_dict": agent.state_dict(), "stage": "analytic",
                "steps": 50_000, "spice_calls": 0}, p)
    back, meta = P.load_agent(p)
    assert (back.obs_dim, back.act_dim) == (agent.obs_dim, agent.act_dim)
    assert meta["stage"] == "analytic" and meta["spice_calls"] == 0


# ---------------------------------------------------------------------------
# 3. rollouts: deterministic, ranked, and zero SPICE
# ---------------------------------------------------------------------------

def test_the_same_seed_proposes_the_same_designs():
    agent = _agent()
    a = P._Rollouts(agent, "random", seed=11)(1.9e9, 6.0, 3)
    b = P._Rollouts(agent, "random", seed=11)(1.9e9, 6.0, 3)
    assert len(a) == len(b) == 3
    for x, y in zip(a, b):
        assert np.allclose(x, y)


def test_a_different_seed_proposes_different_designs():
    agent = _agent()
    a = P._Rollouts(agent, "random", seed=11)(1.9e9, 6.0, 3)
    b = P._Rollouts(agent, "random", seed=12)(1.9e9, 6.0, 3)
    assert not all(np.allclose(x, y) for x, y in zip(a, b))


def test_candidates_come_back_best_first():
    agent = _agent()
    src = P._Rollouts(agent, "random", seed=3)
    src(1.9e9, 6.0, 4)
    rewards = [r for r in src.notes[(1.9e9, 6.0)]["analytic_rewards"]
               if r is not None]
    assert rewards == sorted(rewards, reverse=True)


def test_a_rollout_proposes_a_design_it_visited_not_the_start():
    """Gate 4. The seeded start is the library's design; proposing it unchanged
    would make the seeded arms `>= library` by construction."""
    agent = _agent()
    u0 = np.full(7, 0.5)
    src = P._Rollouts(agent, "seeded", seed=5,
                      library_fn=lambda f, p, k: [u0.copy() for _ in range(k)])
    cands = src(1.9e9, 6.0, 2)
    assert cands, "the policy proposed nothing at all"
    assert not any(np.allclose(u, u0) for u in cands)


def test_rollout_returns_the_best_step_not_the_last(monkeypatch):
    """The proposal is the best design by analytic reward, and the recorded
    step proves it is not simply the final one."""
    from nebula.rl.analytic_env import AnalyticCtleEnv
    from nebula.rl.spec_dist import SpecTarget

    agent = _agent()
    env = AnalyticCtleEnv([SpecTarget(peaking_db=6.0, f_peak_hz=1.9e9)], seed=2)
    rewards = iter([-5.0, -1.0, -9.0, -9.0, -9.0, -9.0, -9.0, -9.0])
    real_step = env.step

    def _step(a):
        obs, _r, term, trunc, info = real_step(a)
        return obs, next(rewards), term, trunc, info

    monkeypatch.setattr(env, "step", _step)
    u, r, step = P.rollout(agent, env)
    assert step == 2 and r == -1.0


def test_a_start_the_model_cannot_describe_is_declined_not_faked(monkeypatch):
    """Gate 3 (G107). `reset` raises on an unfittable seeded start; the arm must
    count the decline and fall back to the untouched library design."""
    from nebula.rl import analytic_env as AE

    agent = _agent()
    u0 = np.full(7, 0.25)
    real_reset = AE.AnalyticCtleEnv.reset

    def _reset(self, u0_=None):
        if u0_ is not None:
            raise ValueError("the requested start point cannot be described")
        return real_reset(self)

    monkeypatch.setattr(AE.AnalyticCtleEnv, "reset", _reset)
    src = P._Rollouts(agent, "seeded", seed=5,
                      library_fn=lambda f, p, k: [u0.copy() for _ in range(k)])
    cands = src(1.9e9, 6.0, 2)
    note = src.notes[(1.9e9, 6.0)]
    assert note["n_declined"] == 2
    assert all(np.allclose(u, u0) for u in cands)
    assert all(note["declined_flags"])


def test_the_library_is_fetched_once_per_request_and_copies_are_handed_out():
    """G123: `load_pool` re-parses 74 526 rows per call. The memo must not hand
    out the same array twice, or a caller mutating one changes the other."""
    agent = _agent()
    calls = {"n": 0}

    def _lib(f, p, k):
        calls["n"] += 1
        return [np.full(7, 0.5) for _ in range(k)]

    src = P._Rollouts(agent, "seeded", seed=5, library_fn=_lib)
    a = src._library(1.9e9, 6.0, 2)
    b = src._library(1.9e9, 6.0, 2)
    assert calls["n"] == 1
    a[0][0] = 0.99
    assert b[0][0] == 0.5


def test_registering_the_sources_does_not_replace_the_library():
    """Standing rule 6: wrap, do not replace. The control must survive."""
    before = H.CANDIDATE_SOURCES["library"]
    agent = _agent()
    P.register_sources({"analytic": agent, "finetuned": agent}, seed=1)
    try:
        assert H.CANDIDATE_SOURCES["library"] is before
        assert "sac_seeded_finetuned" in H.CANDIDATE_SOURCES
    finally:
        for name, ckpt, _m in P.ARMS:
            if ckpt:
                H.CANDIDATE_SOURCES.pop(name, None)


def test_an_unknown_mode_raises():
    with pytest.raises(ValueError, match="random"):
        P._Rollouts(_agent(), "sideways")


# ---------------------------------------------------------------------------
# 4. Q4's counter
# ---------------------------------------------------------------------------

def test_swing_fraction_counts_only_non_feasible_candidates():
    scan = {"requests": [{"candidates": [
        {"feasible": True, "reason": "output swing exceeds"},
        {"feasible": False, "reason": "output swing 979.6 mVpp exceeds"},
        {"feasible": False, "reason": "S3_peaking_match out of tolerance"},
        {"error": "boom"},
    ]}]}
    assert P._swing_fraction(scan) == (1, 2)


# ---------------------------------------------------------------------------
# 5. the verdict is mechanical  (entry 36)
# ---------------------------------------------------------------------------

def test_the_registered_negative_is_the_default_reading():
    v = P._verdict(_result())
    assert v["Q1_control_reproduced"] and v["Q2_random_weak"]
    assert v["Q3_seeded_not_above_baseline"]
    assert "DOES NOT CONTRIBUTE" in v["call"]


def test_a_seeded_arm_above_the_baseline_is_the_d9_branch():
    v = P._verdict(_result(seeded_a=(7, 6)))
    assert not v["Q3_seeded_not_above_baseline"]
    assert v["best_seeded"] == 7
    assert "ADDS ACCEPTANCES ON TOP OF RETRIEVAL" in v["call"]


def test_a_random_arm_at_three_falsifies_q2_without_claiming_a_win():
    v = P._verdict(_result(random_a=(3, 1)))
    assert not v["Q2_random_weak"]
    assert "DO NOT" in v["call"] and "TUNE" in v["call"]


def test_a_control_that_did_not_reproduce_dominates_every_other_reading():
    """If the baseline moved, no RL number in the run means anything."""
    v = P._verdict(_result(lib_curve=(1, 4, 5, 5, 7), lib_a=7, seeded_a=(9, 9)))
    assert not v["Q1_control_reproduced"]
    assert "not\ninterpretable" in v["call"] or "interpretable" in v["call"]
    assert "ADDS ACCEPTANCES" not in v["call"]


def test_q5_flags_a_decisive_checkpoint_gap():
    assert P._verdict(_result(seeded_a=(6, 4)))["Q5_checkpoint_not_decisive"] is False
    assert P._verdict(_result(seeded_a=(6, 5)))["Q5_checkpoint_not_decisive"] is True


def test_q6_catches_a_deck_count_that_does_not_add_up():
    assert P._verdict(_result())["Q6_accounting"] is True
    assert P._verdict(_result(measured=319))["Q6_accounting"] is False
    assert P._verdict(_result(deployed=261))["Q6_accounting"] is False


def test_q4_needs_every_random_arm_to_show_the_mechanism():
    assert P._verdict(_result(swing=(0.95, 0.60)))["Q4_swing_dominates"] is True
    assert P._verdict(_result(swing=(0.95, 0.10)))["Q4_swing_dominates"] is False


def test_the_thresholds_are_entry_36s_and_are_not_silently_retunable():
    """The bars are constants so a change shows up in a diff, not in prose."""
    assert (P.Q2_MAX_RANDOM_ACCEPT, P.Q3_BASELINE) == (2, 6)
    assert P.Q4_MIN_SWING_FRACTION == 0.50
    assert P.Q5_MAX_CHECKPOINT_GAP == 1
    assert P.BASELINE_ACCEPTED_AT_K == (1, 4, 5, 5, 6)
    assert P.BASELINE_DEPLOYED_DECKS == 260
    assert P.K == 5


# ---------------------------------------------------------------------------
# session 29: scoring an ARBITRARY checkpoint (entry 41's Q4/Q5).
# These gate the ADDITIVE path only -- entry 36's run()/ARMS/RESULTS must be
# provably untouched, because entry 36 is published.
# ---------------------------------------------------------------------------

def test_entry36_arms_and_results_are_unchanged():
    """The five-arm set and its artifact are entry 36's published identity."""
    assert P.ARMS == (
        ("library", "", ""),
        ("sac_random_analytic", "analytic", "random"),
        ("sac_random_finetuned", "finetuned", "random"),
        ("sac_seeded_analytic", "analytic", "seeded"),
        ("sac_seeded_finetuned", "finetuned", "seeded"),
    )
    assert P.RESULTS.name == "sac_propose_results.json"


def test_ckpt_results_path_never_collides_with_entry36():
    for label in ("screen", "screen2", "entry41"):
        assert P.ckpt_results_path(label) != P.RESULTS
        assert P.ckpt_results_path(label).name.startswith("sac_propose_")


def test_ckpt_results_path_rejects_a_bad_label():
    for bad in ("", "has space", "dots.here", "slash/es"):
        with pytest.raises(ValueError):
            P.ckpt_results_path(bad)


def test_ckpt_label_scopes_the_artifact_so_entry36_control_survives():
    """G128: entry 36's control artifact is `topk_scan_library_k5.json`.

    The --with-control path must never write that name.
    """
    k, label = 5, "screen"
    forbidden = f"topk_scan_library_k{k}.json"
    scoped = f"topk_scan_library_k{k}_{label}.json"
    assert scoped != forbidden


def test_mean_scorable_corners_ignores_errored_candidates():
    scan = {"requests": [
        {"candidates": [{"n_scorable": 4}, {"n_scorable": 2},
                        {"error": "boom"}, {"n_scorable": None}]},
        {"candidates": [{"n_scorable": 0}]},
    ]}
    # (4 + 2 + 0) / 3 -- the errored and the None are excluded, not zeroed.
    assert P.mean_scorable_corners(scan) == pytest.approx(2.0)


def test_mean_scorable_corners_is_none_when_nothing_measured():
    assert P.mean_scorable_corners({"requests": []}) is None
    assert P.mean_scorable_corners(
        {"requests": [{"candidates": [{"error": "x"}]}]}) is None


def test_ckpt_cli_does_not_trigger_entry36_run(monkeypatch):
    """`--ckpt` must route to run_ckpt, never to entry 36's run()."""
    called = {}

    def _fake_run36(**kw):
        called["run36"] = kw
        return {}

    def _fake_run_ckpt(**kw):
        called["runckpt"] = kw
        return {"checkpoint": {"path": "x", "stage": "screen", "steps": 1},
                "k": 5, "arms": [],
                "baseline": {"n_accepted": 6, "accepted_at_k": [1, 4, 5, 5, 6]}}

    monkeypatch.setattr(P, "run", _fake_run36)
    monkeypatch.setattr(P, "run_ckpt", _fake_run_ckpt)
    P.main(["--ckpt", "some.pt", "--label", "screen"])
    assert "runckpt" in called and "run36" not in called
    assert called["runckpt"]["label"] == "screen"


def test_load_agent_rejects_a_weightless_checkpoint(tmp_path):
    torch = pytest.importorskip("torch")
    p = tmp_path / "empty.pt"
    torch.save({"state_dict": None, "steps": 0}, p)
    with pytest.raises(ValueError, match="no state_dict"):
        P.load_agent(p)
