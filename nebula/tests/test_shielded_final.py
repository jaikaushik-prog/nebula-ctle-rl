"""Fail-capable gates for Entry 89's one-time fresh FINAL evaluator."""

from __future__ import annotations

import math

import pytest

from nebula.experiments import exp_joint_bank_midpoint as M
from nebula.experiments import exp_margin_improve_controls as BASE
from nebula.experiments import exp_shielded_controls as DEVELOPMENT
from nebula.experiments import exp_shielded_final as F


def _summary(seed: int | None = None, *, compliance: float = 0.90,
             quality: float = 0.74, trials: float = 5.0,
             retained: bool = True) -> dict:
    row = {
        "compliance_rate": compliance,
        "mean_quality": quality,
        "quality_delta": quality - 0.70,
        "mean_trials": trials,
        "n_false_locks": 0,
        "n_shield_fallbacks": 0,
        "code_change_rate": 0.5,
        "mean_verifier_calls": trials,
        "retained_all_compliant_starts": retained,
        "per_identity": [
            {"n_trials": int(trials), "n_verifier_calls": int(trials)}],
    }
    if seed is not None:
        row["seed"] = seed
    return row


def test_final_identity_membership_hash_and_zero_overlap_are_exact():
    final_ids = F.final_identities()
    development_ids = DEVELOPMENT.development_identities()
    assert len(final_ids) == len(set(final_ids)) == 2430
    assert BASE.identities_sha256(final_ids) == F.FINAL_IDENTITIES_SHA256
    assert BASE.identities_sha256(development_ids) == \
        F.DEVELOPMENT_IDENTITIES_SHA256
    assert not set(final_ids).intersection(development_ids)
    assert {row[1] for row in final_ids} == set(M.MIDPOINT_LOSSES_DB)
    assert {row[2:] for row in final_ids} == set(M.FINAL_REQUESTS)


def test_nearest_development_request_uses_normalized_log_frequency_and_tuple_ties():
    expected_pk = {5.0: 4.0, 7.0: 6.0, 9.0: 8.0}
    expected_exponent = {0.265: 0.15, 0.5: 0.38, 0.735: 0.62}
    for final_pk, old_pk in expected_pk.items():
        for final_exp, old_exp in expected_exponent.items():
            target = (final_pk, 1.25e9 * 2.0 ** final_exp)
            got = F.nearest_development_request(target)
            assert got[0] == old_pk
            assert math.log2(got[1] / 1.25e9) == pytest.approx(old_exp)


def test_final_start_map_uses_only_the_nearest_development_lookup():
    development_starts = {
        request: index for index, request in enumerate(BASE.REQUESTS)}
    starts, provenance = F.map_final_starts(development_starts)
    assert set(starts) == set(M.FINAL_REQUESTS)
    assert len(provenance) == len(M.FINAL_REQUESTS)
    for row in provenance:
        final_request = (row["target_peaking_db"], row["target_f_peak_hz"])
        source_request = (row["development_peaking_db"],
                          row["development_f_peak_hz"])
        assert source_request == F.nearest_development_request(final_request)
        assert starts[final_request] == development_starts[source_request]


def test_registered_gates_pass_only_with_safety_quality_cost_and_reporting():
    fixed = _summary(quality=0.70, trials=1.0)
    primary = [_summary(seed) for seed in F.TRAIN_SEEDS]
    controls = {
        "entry88_deployment_shielded": _summary(F.ENTRY88_DEPLOYMENT_SEED),
        "entry89_unshielded": [_summary(seed) for seed in F.TRAIN_SEEDS],
        "entry89_shielded": primary,
        "global_hidden_oracle": _summary(quality=1.0, trials=1.0),
        "reachable_hidden_oracle": _summary(quality=0.95, trials=6.0),
        "entry89_attribution": [{
            "seed": seed,
            "shield_minus_unshielded_quality": 0.0,
            "shield_minus_unshielded_compliance": 0.0,
        } for seed in F.TRAIN_SEEDS],
    }
    provenance = {name: True for name in F.R1_PROVENANCE_FIELDS}
    gates = F.score_gates(
        provenance=provenance, observation_ok=True, imitation_ok=True,
        training_ok=True, development_safety_ok=True, fixed=fixed,
        primary=primary, controls=controls, bootstrap_ci=(0.02, 0.06),
        scope_statement=F.SCOPE_STATEMENT)
    assert all(gates.values())

    unsafe = [dict(row) for row in primary]
    unsafe[0]["compliance_rate"] = fixed["compliance_rate"] - 0.001
    gates = F.score_gates(
        provenance=provenance, observation_ok=True, imitation_ok=True,
        training_ok=True, development_safety_ok=True, fixed=fixed,
        primary=unsafe, controls={**controls, "entry89_shielded": unsafe},
        bootstrap_ci=(0.02, 0.06), scope_statement=F.SCOPE_STATEMENT)
    assert not gates["R5_structural_safety"]

    weak = [_summary(seed, quality=0.71) for seed in F.TRAIN_SEEDS]
    gates = F.score_gates(
        provenance=provenance, observation_ok=True, imitation_ok=True,
        training_ok=True, development_safety_ok=True, fixed=fixed,
        primary=weak, controls={**controls, "entry89_shielded": weak},
        bootstrap_ci=(0.001, 0.03), scope_statement=F.SCOPE_STATEMENT)
    assert not gates["R6_quality"]

    expensive = [_summary(seed, trials=9.0) for seed in F.TRAIN_SEEDS]
    gates = F.score_gates(
        provenance=provenance, observation_ok=True, imitation_ok=True,
        training_ok=True, development_safety_ok=True, fixed=fixed,
        primary=expensive,
        controls={**controls, "entry89_shielded": expensive},
        bootstrap_ci=(0.02, 0.06), scope_statement=F.SCOPE_STATEMENT)
    assert not gates["R8_cost"]

    incomplete = dict(controls)
    incomplete.pop("entry89_attribution")
    gates = F.score_gates(
        provenance=provenance, observation_ok=True, imitation_ok=True,
        training_ok=True, development_safety_ok=True, fixed=fixed,
        primary=primary, controls=incomplete, bootstrap_ci=(0.02, 0.06),
        scope_statement=F.SCOPE_STATEMENT)
    assert not gates["R9_attribution_reporting"]


def test_frozen_input_artifacts_validate_without_scoring_final():
    table, metadata, facts = F._load_midpoint_table()
    starts, development = F._load_development_starts()
    assert facts == {
        "decoded": F.MIDPOINT_DECODED_SHA256,
        "midpoint_membership": True,
        "n_rows": 23040,
        "n_settings": 512,
        "n_corners": 45,
    }
    assert metadata["status"] == "GENERATED_NOT_SCORED"
    assert development["final_status"] == "NOT_GENERATED_NOT_SCORED"
    assert set(starts) == set(BASE.REQUESTS)


def test_final_evaluator_refuses_to_overwrite_a_result(monkeypatch, tmp_path):
    monkeypatch.setattr(F, "HERE", tmp_path)
    F.results_path().write_text("sealed", encoding="ascii")
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        F.evaluate()
