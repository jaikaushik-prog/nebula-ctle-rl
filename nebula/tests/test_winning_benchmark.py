import pytest

from nebula.experiments import exp_winning_benchmark as W


ID = ["tt/1.00/27C", 7.5, 9.0, 1.9e9]


def row(seed, policy_q, oracle_q, visits=8, unique=6):
    return {
        "seed": seed, "identity": ID, "policy_selected": 1,
        "oracle_selected": 2, "policy_compliant": policy_q > 0,
        "oracle_compliant": oracle_q > 0, "policy_quality": policy_q,
        "oracle_quality": oracle_q, "quality_regret": oracle_q-policy_q,
        "within_0p01": oracle_q-policy_q <= .01,
        "within_0p05": oracle_q-policy_q <= .05,
        "policy_visits": visits, "policy_unique_visits": unique,
        "exhaustive_visits": 512,
    }


def test_summary_reports_regret_and_candidate_reduction():
    result = W.summarise([row(1, .9, 1.), row(2, .96, 1., visits=4, unique=4)])
    assert result["mean_regret_oracle_solvable"] == pytest.approx(.07)
    assert result["fraction_within_0p05"] == .5
    assert result["candidate_visit_reduction"] == pytest.approx(512/6)
    assert result["unique_candidate_reduction"] == pytest.approx(512/5)


def test_compare_rejects_quality_above_exhaustive_oracle():
    policy = {"seed": 1, "identity": ID, "selected": 1,
              "compliant": True, "quality": 1.1, "n_visits": 2,
              "n_unique": 2}
    oracle = {"identity": ID, "selected": 2, "compliant": True,
              "quality": 1., "n_visits": 512}
    with pytest.raises(ValueError, match="exceeds"):
        W.compare_row(policy, oracle)


def test_compare_keeps_unserved_oracle_distinct():
    policy = {"seed": 1, "identity": ID, "selected": 1,
              "compliant": False, "quality": 0., "n_visits": 2,
              "n_unique": 2}
    oracle = {"identity": ID, "selected": 2, "compliant": False,
              "quality": 0., "n_visits": 512}
    result = W.compare_row(policy, oracle)
    assert not result["oracle_compliant"]
    assert not result["within_0p05"]


def test_existing_output_is_never_overwritten(monkeypatch, tmp_path):
    monkeypatch.setattr(W, "frozen_plan", lambda: "hash")
    with pytest.raises(FileExistsError):
        W.run(tmp_path)


def test_uncommitted_protocol_is_rejected(monkeypatch, tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("changed")
    monkeypatch.setattr(W, "PLAN", plan)
    monkeypatch.setattr(W.subprocess, "check_output", lambda *a, **k: b"frozen")
    with pytest.raises(ValueError, match="committed"):
        W.frozen_plan()
