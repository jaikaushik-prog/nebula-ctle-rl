"""Provenance and scoring gates for Entry 88's five masked-PPO runs."""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest

from nebula.experiments import exp_margin_improve_ppo as P


def test_registered_seeds_budget_and_bootstrap_are_fixed():
    assert P.TRAIN_SEEDS == tuple(range(2026090400, 2026090405))
    assert P.DEPLOYMENT_SEED == 2026090400
    assert P.TOTAL_STEPS == 200_000
    assert P.BOOTSTRAP_SEED == 2026090488
    assert P.N_BOOTSTRAP == 10_000


def test_artifact_paths_are_distinct_and_do_not_clobber_entry87():
    checkpoints = [P.checkpoint_path(seed) for seed in P.TRAIN_SEEDS]
    summaries = [P.training_path(seed) for seed in P.TRAIN_SEEDS]
    assert len(set(checkpoints)) == len(P.TRAIN_SEEDS)
    assert len(set(summaries)) == len(P.TRAIN_SEEDS)
    assert all(path.name.startswith("margin_improve_policy_")
               for path in checkpoints)
    assert all(path.name.startswith("margin_improve_train_")
               for path in summaries)
    assert P.RESULTS.name == "margin_improve_rl_results.json"


def test_structured_control_start_map_keeps_exact_request_values():
    rows = [{"target_peaking_db": pk, "target_f_peak_hz": freq,
             "setting": index}
            for index, (pk, freq) in enumerate(P.C.REQUESTS)]
    restored = P._start_map({"start_by_request": rows})
    assert set(restored) == set(P.C.REQUESTS)
    assert all(restored[request] == index
               for index, request in enumerate(P.C.REQUESTS))


def test_paired_bootstrap_is_deterministic_and_positive():
    delta = np.linspace(0.01, 0.05, 2448)
    assert P.paired_bootstrap_ci(delta) == P.paired_bootstrap_ci(delta)
    assert P.paired_bootstrap_ci(delta)[0] > 0.0


def _passing_rows():
    return [{
        "seed": seed, "steps_completed": P.TOTAL_STEPS,
        "weights_changed": True, "finite": True,
        "checkpoint_sha256": f"checkpoint-{seed}",
        "training_summary": f"summary-{seed}.json",
        "compliance_rate": 0.99, "mean_quality": 0.74,
        "mean_trials": 4.0, "quality_delta": 0.04,
        "mean_return": 0.04, "n_false_locks": 1,
        "code_change_rate": 0.5,
    } for seed in P.TRAIN_SEEDS]


def test_score_gates_keep_safety_quality_and_all_five_seed_requirements():
    comparator = {"compliance_rate": 0.995, "mean_quality": 0.70,
                  "mean_trials": 1.0}
    rows = _passing_rows()
    checks = P.score_checks(True, True, True, rows, comparator, (0.02, 0.06))
    assert all(checks.values())
    rows[0]["compliance_rate"] = 0.98
    assert not P.score_checks(
        True, True, True, rows, comparator, (0.02, 0.06))["Q5"]
    rows = _passing_rows()
    rows[0]["quality_delta"] = -0.01
    rows[1]["quality_delta"] = -0.01
    assert not P.score_checks(
        True, True, True, rows, comparator, (0.02, 0.06))["Q7"]


def test_train_refuses_unregistered_seed_and_existing_artifact(tmp_path,
                                                               monkeypatch):
    with pytest.raises(ValueError, match="unregistered"):
        P.train_seed(1)
    monkeypatch.setattr(P, "HERE", tmp_path)
    P.checkpoint_path(P.TRAIN_SEEDS[0]).write_bytes(b"keep")
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        P.train_seed(P.TRAIN_SEEDS[0])


def test_final_evaluation_refuses_to_open_without_all_training_artifacts(
        tmp_path, monkeypatch):
    monkeypatch.setattr(P, "HERE", tmp_path)
    with pytest.raises(FileNotFoundError, match="missing training artifacts"):
        P.evaluate()


def test_all_checkpoints_validate_before_final_scoring(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "HERE", tmp_path)
    for seed in P.TRAIN_SEEDS:
        P.checkpoint_path(seed).write_bytes(b"checkpoint")
        P.training_path(seed).write_text("{}", encoding="utf-8")
    monkeypatch.setattr(P, "_load_controls", lambda: {"split": {}})
    scored = []

    def reject(seed, controls):
        if seed == P.TRAIN_SEEDS[2]:
            raise ValueError("bad checkpoint")
        return object()

    monkeypatch.setattr(P, "_load_net", reject)
    monkeypatch.setattr(P.C, "score_fixed",
                        lambda *args, **kwargs: scored.append(True))
    with pytest.raises(ValueError, match="bad checkpoint"):
        P.evaluate()
    assert not scored


def test_console_literals_are_ascii_for_windows():
    tree = ast.parse(Path(P.__file__).read_text(encoding="utf-8"))
    for call in (n for n in ast.walk(tree) if isinstance(n, ast.Call)):
        if isinstance(call.func, ast.Name) and call.func.id == "print":
            for const in (n for arg in call.args for n in ast.walk(arg)
                          if isinstance(n, ast.Constant)
                          and isinstance(n.value, str)):
                assert const.value.isascii(), repr(const.value)
