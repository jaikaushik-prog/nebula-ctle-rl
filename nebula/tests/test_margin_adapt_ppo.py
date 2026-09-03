"""Provenance and scoring gates for Entry 87's five-seed PPO run."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from nebula.experiments import exp_margin_adapt_ppo as P


def test_registered_seeds_budget_and_deployment_seed_are_fixed():
    assert P.TRAIN_SEEDS == tuple(range(2026090300, 2026090305))
    assert P.DEPLOYMENT_SEED == 2026090300
    assert P.TOTAL_STEPS == 200_000
    assert P.BOOTSTRAP_SEED == 2026090387
    assert P.N_BOOTSTRAP == 10_000


def test_checkpoint_and_summary_paths_are_distinct_and_nonhistorical():
    checkpoints = [P.checkpoint_path(seed) for seed in P.TRAIN_SEEDS]
    summaries = [P.training_path(seed) for seed in P.TRAIN_SEEDS]
    assert len(set(checkpoints)) == len(P.TRAIN_SEEDS)
    assert len(set(summaries)) == len(P.TRAIN_SEEDS)
    assert all(path.suffix == ".pth" for path in checkpoints)
    assert P.RESULTS.name == "margin_adapt_rl_results.json"
    assert P.RESULTS not in checkpoints and P.RESULTS not in summaries


def test_paired_bootstrap_is_deterministic_and_detects_positive_delta():
    delta = np.linspace(0.01, 0.05, 864)
    one = P.paired_bootstrap_ci(delta)
    two = P.paired_bootstrap_ci(delta)
    assert one == two
    assert one[0] > 0.0 and one[1] > one[0]


def test_score_gates_use_registered_comparator_floors_and_all_five_seeds():
    comparator = {"compliance_rate": 0.9931, "mean_quality": 0.6796,
                  "mean_trials": 1.0}
    per_seed = []
    for seed in P.TRAIN_SEEDS:
        per_seed.append({
            "seed": seed, "steps_completed": P.TOTAL_STEPS,
            "weights_changed": True, "finite": True,
            "compliance_rate": 0.99, "mean_quality": 0.71,
            "mean_trials": 2.0, "quality_delta": 0.0304,
        })
    checks = P.score_checks(
        source_ok=True, split_ok=True, controls_ok=True,
        per_seed=per_seed, comparator=comparator,
        bootstrap_ci=(0.02, 0.04))
    assert all(checks.values())

    per_seed[0]["compliance_rate"] = 0.97
    checks = P.score_checks(True, True, True, per_seed, comparator,
                            (0.02, 0.04))
    assert not checks["Q5"]


def test_train_seed_refuses_unregistered_seed_and_existing_artifacts(tmp_path,
                                                                    monkeypatch):
    with pytest.raises(ValueError, match="unregistered"):
        P.train_seed(1)
    monkeypatch.setattr(P, "HERE", tmp_path)
    P.checkpoint_path(P.TRAIN_SEEDS[0]).write_bytes(b"keep")
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        P.train_seed(P.TRAIN_SEEDS[0])
