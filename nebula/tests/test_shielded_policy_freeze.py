"""Fail-capable gates for Entry 89 DEVELOPMENT scoring and policy freeze."""

from __future__ import annotations

import json
from dataclasses import asdict

import pytest

from nebula.experiments import exp_shielded_ppo as P


def _healthy(seed: int) -> dict:
    return {
        "seed": seed,
        "source_decoded_sha256": P.SOURCE_SHA256,
        "controls_sha256": P.CONTROLS_SHA256,
        "development_status": "EXPOSED_TRAINING_ONLY",
        "final_status": P.FINAL_STATUS,
        "bc_config": asdict(P.BCConfig(
            seed=seed, epochs=P.BC_EPOCHS,
            batch_size=P.BC_BATCH_SIZE, lr=P.BC_LR)),
        "bc_stats": {"epochs_completed": P.BC_EPOCHS,
                     "loss": [0.5] * P.BC_EPOCHS},
        "ppo_config": asdict(P.DiscretePPOConfig(
            seed=seed, total_steps=P.TOTAL_STEPS)),
        "steps_completed": P.TOTAL_STEPS,
        "bc_changed_actor": True,
        "bc_preserved_value": True,
        "ppo_started_from_bc": True,
        "ppo_changed_weights": True,
        "finite": True,
        "simulations_run": 0,
    }


def test_result_and_manifest_paths_follow_redirected_base(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "HERE", tmp_path)
    assert P.development_results_path() == (
        tmp_path / "shielded_policy_development_results.json")
    assert P.policy_manifest_path() == tmp_path / "shielded_policy_manifest.json"


def test_training_health_requires_the_exact_registered_run():
    row = _healthy(P.TRAIN_SEEDS[0])
    assert P.training_health(row, P.TRAIN_SEEDS[0])
    row["steps_completed"] -= 1
    assert not P.training_health(row, P.TRAIN_SEEDS[0])
    row = _healthy(P.TRAIN_SEEDS[0])
    row["bc_stats"]["loss"][0] = float("nan")
    assert not P.training_health(row, P.TRAIN_SEEDS[0])


def test_development_checks_require_all_five_safe_and_four_useful():
    fixed = {"compliance_rate": 0.98, "mean_quality": 0.70}
    rows = [{"compliance_rate": 0.98, "quality_delta": 0.04}
            for _ in P.TRAIN_SEEDS]
    checks = P.development_checks(True, fixed, rows)
    assert all(checks.values())
    rows[0]["compliance_rate"] = 0.97
    assert not P.development_checks(True, fixed, rows)["D4_safety"]
    rows = [{"compliance_rate": 0.98, "quality_delta": 0.01}
            for _ in P.TRAIN_SEEDS]
    assert not P.development_checks(True, fixed, rows)["D5_quality"]
    assert not P.development_checks(False, fixed, rows)["D3_training"]


def test_freeze_refuses_before_development_result_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "HERE", tmp_path)
    with pytest.raises(FileNotFoundError, match="DEVELOPMENT result"):
        P.freeze_policies()


def test_freeze_refuses_bad_integrity_or_final_scored_development_result(
        tmp_path, monkeypatch):
    monkeypatch.setattr(P, "HERE", tmp_path)
    result = {
        "integrity_passed": False,
        "final_status": P.FINAL_STATUS,
        "training_seeds": list(P.TRAIN_SEEDS),
    }
    P.development_results_path().write_text(json.dumps(result), encoding="utf-8")
    with pytest.raises(ValueError, match="integrity"):
        P.freeze_policies()
    result["integrity_passed"] = True
    result["final_status"] = "EVALUATED"
    P.development_results_path().write_text(json.dumps(result), encoding="utf-8")
    with pytest.raises(ValueError, match="FINAL status"):
        P.freeze_policies()
