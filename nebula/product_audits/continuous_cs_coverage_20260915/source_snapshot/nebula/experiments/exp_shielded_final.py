"""Entry 89's one-time fresh FINAL evaluation.

All policies and the complete midpoint SPICE journal must match their frozen
hash manifests before the first final identity is scored.  Evaluation is a
lookup over that real-ngspice journal and refuses to overwrite its result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from nebula.common.types import (
    SPEC_F_PEAK_HZ_RANGE, SPEC_PEAKING_DB_RANGE, all_corners,
)
from nebula.experiments import exp_joint_bank as J
from nebula.experiments import exp_joint_bank_midpoint as MIDPOINT
from nebula.experiments import exp_margin_improve_controls as BASE
from nebula.experiments import exp_margin_improve_ppo as ENTRY88
from nebula.experiments import exp_shielded_controls as SHIELD
from nebula.experiments import exp_shielded_ppo as ENTRY89
from nebula.rl.margin_adapt_env import MarginBankTable
from nebula.rl.margin_improve_env import MarginImproveEnv

HERE = Path(__file__).resolve().parent
RESULTS_NAME = "shielded_policy_final_results.json"
MIDPOINT_METADATA_NAME = "joint_bank_midpoint_metadata.json"

TRAIN_SEEDS = ENTRY89.TRAIN_SEEDS
DEPLOYMENT_SEED = ENTRY89.DEPLOYMENT_SEED
ENTRY88_DEPLOYMENT_SEED = ENTRY88.DEPLOYMENT_SEED
BOOTSTRAP_SEED = 2026090589
N_BOOTSTRAP = 10_000

DEVELOPMENT_IDENTITIES_SHA256 = (
    "7425BEDBC540CBCE61997128CBCE6D206FEEA79666A4E8C805EDAA6812C6A34E")
FINAL_IDENTITIES_SHA256 = (
    "1E7A44582FF52B7EB08710AC2C5BB6740E1A243F837439B074F43551F4F02BD9")
DEVELOPMENT_RESULTS_SHA256 = (
    "9D462EE4F3FE97AFEF1FD372817A0672487A33AD3C46A794DCE3AB390C9EFFBF")
POLICY_MANIFEST_SHA256 = (
    "3E910DECEFD7CAAA5D401655E77C310F8BE4A645DD48538EEE4E1531199734DB")
MIDPOINT_METADATA_SHA256 = (
    "1C5C9527A1A982BD8C82373F98CE3AFDFD021C1AC542D04CF4FAB9D0C2612D65")
MIDPOINT_GZIP_SHA256 = (
    "AE57F93E9636DC135C9E3B86DD37B9B59BE14C3A5DA511EAC4202101E529E9C4")
MIDPOINT_DECODED_SHA256 = (
    "99B6BF526EE610CF39EBC921A2B8BEA2EA482A610354056569B2A176AA1169E2")
ENTRY88_POLICY_SHA256 = (
    "18BC302DF496AE46DAAA1E20BA5775A052CB3245F2635E5BCDA56DE721BA12AA")
ENTRY88_TRAINING_SHA256 = (
    "EE14AF125F034AA73419A5101161B23F5614E6FE8F129A8D3BCDC4356B85FEB8")

ACTOR_OBSERVATION_FIELDS = (
    "target_peaking", "target_log_frequency", "trial_fraction",
    "attenuator_code", "rs_code", "cs_code", "measured_eye_history",
)
ACTOR_HIDDEN_FIELDS = (
    "pvt", "channel_loss", "compliance", "quality", "oracle",
)
SCOPE_STATEMENT = (
    "This is a simulator-backed design-time safety shield, not a receiver-only "
    "calibration loop and not silicon validation. It evaluates fresh link and "
    "request views of the same transistor geometries and PVT lattice."
)

R1_PROVENANCE_FIELDS = (
    "development_hash", "development_membership", "policy_manifest_hash",
    "training_artifacts_match_manifest", "policies_frozen",
    "midpoint_metadata_hash", "midpoint_status", "midpoint_hashes",
    "midpoint_membership", "freeze_precedes_midpoint_provenance",
    "final_membership", "development_final_overlap_zero",
    "result_absent_before_scoring",
)


def results_path() -> Path:
    return HERE / RESULTS_NAME


def metadata_path() -> Path:
    return HERE / MIDPOINT_METADATA_NAME


def midpoint_path() -> Path:
    return HERE / MIDPOINT.GZIP_NAME


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def final_identities() -> list[tuple]:
    """Return the exact 45 x 6 x 9 registered FINAL identities."""
    return [
        (J._corner_label(corner), float(loss), float(peaking), float(frequency))
        for corner in all_corners()
        for loss in MIDPOINT.MIDPOINT_LOSSES_DB
        for peaking, frequency in MIDPOINT.FINAL_REQUESTS
    ]


def _request_distance(one: tuple[float, float],
                      two: tuple[float, float]) -> float:
    pk_lo, pk_hi = SPEC_PEAKING_DB_RANGE
    f_lo, f_hi = SPEC_F_PEAK_HZ_RANGE
    one_pk = (float(one[0]) - pk_lo) / (pk_hi - pk_lo)
    two_pk = (float(two[0]) - pk_lo) / (pk_hi - pk_lo)
    denom = math.log2(f_hi / f_lo)
    one_f = math.log2(float(one[1]) / f_lo) / denom
    two_f = math.log2(float(two[1]) / f_lo) / denom
    return float((one_pk - two_pk) ** 2 + (one_f - two_f) ** 2)


def nearest_development_request(
        target: tuple[float, float],
        development_requests: Sequence[tuple] = BASE.REQUESTS,
        ) -> tuple[float, float]:
    """Nearest normalized request; tuple order breaks exact distance ties."""
    choices = tuple(sorted((float(pk), float(freq))
                           for pk, freq in development_requests))
    if not choices:
        raise ValueError("empty DEVELOPMENT request set")
    target = (float(target[0]), float(target[1]))
    # The registered 0.500-octave request is mathematically equidistant from
    # 0.38 and 0.62. Binary floating point perturbs that tie by ~1e-17, so
    # quantise only the comparison key before applying the required tuple tie.
    return min(choices, key=lambda row: (
        round(_request_distance(target, row), 15), row))


def map_final_starts(development_starts: dict) -> tuple[dict, list[dict]]:
    """Map FINAL requests to frozen DEVELOPMENT starts without FINAL data."""
    source = {(float(pk), float(freq)): int(setting)
              for (pk, freq), setting in development_starts.items()}
    if set(source) != set(BASE.REQUESTS):
        raise ValueError("DEVELOPMENT start map request membership mismatch")
    starts = {}
    provenance = []
    for target in MIDPOINT.FINAL_REQUESTS:
        target = (float(target[0]), float(target[1]))
        nearest = nearest_development_request(target)
        starts[target] = source[nearest]
        provenance.append({
            "target_peaking_db": target[0],
            "target_f_peak_hz": target[1],
            "development_peaking_db": nearest[0],
            "development_f_peak_hz": nearest[1],
            "normalized_squared_distance": _request_distance(target, nearest),
            "setting": source[nearest],
        })
    return starts, provenance


def _load_development_starts() -> tuple[dict, dict]:
    path = ENTRY89.development_results_path()
    if _sha256(path) != DEVELOPMENT_RESULTS_SHA256:
        raise ValueError("DEVELOPMENT result hash mismatch")
    result = json.loads(path.read_text(encoding="utf-8"))
    if (result.get("development_status") != "EXPOSED_DIAGNOSTIC_ONLY"
            or result.get("final_status") != ENTRY89.FINAL_STATUS
            or int(result.get("n_development_identities", -1)) != 5040):
        raise ValueError("DEVELOPMENT result status or membership mismatch")
    starts = {}
    for row in result["fixed"]["per_identity"]:
        request = (float(row["target_peaking_db"]),
                   float(row["target_f_peak_hz"]))
        setting = int(row["start_setting"])
        previous = starts.setdefault(request, setting)
        if previous != setting:
            raise ValueError("DEVELOPMENT start changes within one request")
    if set(starts) != set(BASE.REQUESTS):
        raise ValueError("DEVELOPMENT result start membership mismatch")
    return starts, result


def _load_midpoint_table() -> tuple[MarginBankTable, dict, dict]:
    meta_file = metadata_path()
    gzip_file = midpoint_path()
    if _sha256(meta_file) != MIDPOINT_METADATA_SHA256:
        raise ValueError("midpoint metadata hash mismatch")
    metadata = json.loads(meta_file.read_text(encoding="utf-8"))
    if metadata.get("status") != "GENERATED_NOT_SCORED":
        raise ValueError("midpoint data is not sealed before FINAL scoring")
    if _sha256(gzip_file) != MIDPOINT_GZIP_SHA256:
        raise ValueError("midpoint gzip hash mismatch")
    decoded = J._decoded_sha256(gzip_file)
    if decoded != MIDPOINT_DECODED_SHA256:
        raise ValueError("midpoint decoded hash mismatch")
    rows = J._load_rows(gzip_file)
    expected_corners = {J._corner_label(corner) for corner in all_corners()}
    pairs = {(int(row.setting), str(row.corner)) for row in rows}
    midpoint_membership = bool(
        len(rows) == MIDPOINT.EXPECTED_ROWS
        and len(pairs) == MIDPOINT.EXPECTED_ROWS
        and {int(row.setting) for row in rows} == set(range(512))
        and {str(row.corner) for row in rows} == expected_corners
        and all(not row.ok or set(row.links or {}) == {
            str(value) for value in MIDPOINT.MIDPOINT_LOSSES_DB}
                for row in rows))
    if not midpoint_membership:
        raise ValueError("midpoint setting/corner/link membership mismatch")
    table = MarginBankTable(rows, losses=MIDPOINT.MIDPOINT_LOSSES_DB)
    facts = {
        "decoded": decoded,
        "midpoint_membership": midpoint_membership,
        "n_rows": len(rows),
        "n_settings": len(table.settings),
        "n_corners": len(table.corners),
    }
    return table, metadata, facts


def paired_bootstrap_ci(delta: Sequence[float]) -> tuple[float, float]:
    values = np.asarray(delta, dtype=float)
    if values.ndim != 1 or not len(values):
        raise ValueError("paired bootstrap needs a non-empty vector")
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    means = np.empty(N_BOOTSTRAP, dtype=float)
    for start in range(0, N_BOOTSTRAP, 250):
        count = min(250, N_BOOTSTRAP - start)
        indices = rng.integers(0, len(values), size=(count, len(values)))
        means[start:start + count] = values[indices].mean(axis=1)
    low, high = np.percentile(means, [2.5, 97.5])
    return float(low), float(high)


def _make_reportable(row: dict, *, shielded: bool = False) -> dict:
    """Attach the identical required accounting fields to every arm."""
    episodes = row["per_identity"]
    for episode in episodes:
        episode.setdefault("n_verifier_calls", int(episode["n_trials"]))
        episode.setdefault("shield_intervened", False)
        episode.setdefault("shield_failure", False)
    row.setdefault("n_shield_interventions", int(sum(
        bool(ep["shield_intervened"]) for ep in episodes)))
    row.setdefault("n_shield_failures", int(sum(
        bool(ep["shield_failure"]) for ep in episodes)))
    row["n_shield_fallbacks"] = int(row["n_shield_failures"])
    row["mean_verifier_calls"] = float(np.mean([
        ep["n_verifier_calls"] for ep in episodes]))
    row["shielded"] = bool(shielded)
    return row


def _score_hidden_oracle(table: MarginBankTable, identities: Sequence[tuple],
                         starts: dict, radius: Optional[int], name: str) -> dict:
    rows = []
    for identity in identities:
        corner, loss, peaking, frequency = identity
        request = (float(peaking), float(frequency))
        start = int(starts[request])
        candidates = list(table.compliant_settings(*identity))
        if radius is not None:
            candidates = [setting for setting in candidates
                          if BASE.setting_distance(start, setting) <= radius]
        setting = (max(candidates,
                       key=lambda value: (table.quality(value, *identity),
                                          -int(value)))
                   if candidates else start)
        distance = BASE.setting_distance(start, setting)
        trials = 1 if radius is None else distance + 1
        rows.append(BASE._direct_record(
            table, identity, start, setting, trials, distance))
    return _make_reportable(BASE._summarise(name, rows))


def _reporting_ok(fixed: dict, controls: dict) -> bool:
    required = {
        "compliance_rate", "mean_quality", "quality_delta", "mean_trials",
        "n_false_locks", "n_shield_fallbacks", "code_change_rate",
        "mean_verifier_calls", "per_identity",
    }
    expected = (
        [fixed, controls.get("entry88_deployment_shielded", {})]
        + list(controls.get("entry89_unshielded", []))
        + list(controls.get("entry89_shielded", []))
        + [controls.get("global_hidden_oracle", {}),
           controls.get("reachable_hidden_oracle", {})]
    )
    attribution = controls.get("entry89_attribution", [])
    attribution_ok = bool(
        len(attribution) == len(TRAIN_SEEDS)
        and {row.get("seed") for row in attribution} == set(TRAIN_SEEDS)
        and all({"shield_minus_unshielded_quality",
                 "shield_minus_unshielded_compliance"}.issubset(row)
                for row in attribution))
    return bool(all(required.issubset(row) for row in expected)
                and len(controls.get("entry89_unshielded", [])) == 5
                and len(controls.get("entry89_shielded", [])) == 5
                and attribution_ok)


def score_gates(*, provenance: dict, observation_ok: bool,
                imitation_ok: bool, training_ok: bool,
                development_safety_ok: bool, fixed: dict,
                primary: Sequence[dict], controls: dict,
                bootstrap_ci: tuple[float, float],
                scope_statement: str) -> dict:
    rows = list(primary)
    deploy = next((row for row in rows
                   if row.get("seed") == DEPLOYMENT_SEED), None)
    fixed_compliance = float(fixed["compliance_rate"])
    fixed_quality = float(fixed["mean_quality"])
    mean_compliance = float(np.mean([
        row["compliance_rate"] for row in rows])) if rows else float("nan")
    mean_quality = float(np.mean([
        row["mean_quality"] for row in rows])) if rows else float("nan")
    mean_trials = float(np.mean([
        row["mean_trials"] for row in rows])) if rows else float("nan")
    verifier_exact = bool(rows and all(
        abs(float(row["mean_verifier_calls"]) -
            float(row["mean_trials"])) <= 1e-12
        and all(int(ep["n_verifier_calls"]) == int(ep["n_trials"])
                for ep in row["per_identity"])
        for row in rows))
    safety = bool(
        len(rows) == len(TRAIN_SEEDS)
        and development_safety_ok
        and all(bool(row["retained_all_compliant_starts"])
                for row in rows)
        and mean_compliance >= fixed_compliance
        and deploy is not None
        and float(deploy["compliance_rate"]) >= fixed_compliance)
    quality_delta = mean_quality - fixed_quality
    scope = scope_statement.lower()
    return {
        "R1_provenance": bool(all(bool(provenance.get(name))
                                  for name in R1_PROVENANCE_FIELDS)),
        "R2_observation": bool(observation_ok),
        "R3_imitation": bool(imitation_ok),
        "R4_training": bool(training_ok),
        "R5_structural_safety": safety,
        "R6_quality": bool(quality_delta >= 0.0200
                           and float(bootstrap_ci[0]) > 0.0),
        "R7_reproducibility": bool(
            len(rows) == len(TRAIN_SEEDS)
            and sum(float(row["quality_delta"]) > 0.0 for row in rows) >= 4
            and deploy is not None
            and float(deploy["quality_delta"]) > 0.0),
        "R8_cost": bool(mean_trials <= 8.0 and mean_trials < 512.0
                        and verifier_exact),
        "R9_attribution_reporting": _reporting_ok(fixed, controls),
        "R10_scope": bool("simulator-backed" in scope
                          and "not a receiver-only" in scope
                          and "not silicon" in scope),
    }


def evaluate() -> dict:
    """Validate every freeze, then expose and write FINAL exactly once."""
    result_file = results_path()
    if result_file.exists():
        raise FileExistsError(f"refusing to overwrite {result_file.name}")

    manifest_file = ENTRY89.policy_manifest_path()
    manifest = MIDPOINT.validate_policy_freeze()
    artifacts, entry89_nets = ENTRY89.validate_training_artifacts()
    if artifacts != manifest.get("policies"):
        raise ValueError("training artifacts differ from frozen manifest")
    development_starts, development_result = _load_development_starts()
    table, metadata, table_facts = _load_midpoint_table()
    final_ids = final_identities()
    development_ids = SHIELD.development_identities()
    final_starts, start_provenance = map_final_starts(development_starts)

    old_controls = ENTRY88._load_controls()
    if (_sha256(ENTRY88.checkpoint_path(ENTRY88_DEPLOYMENT_SEED)) !=
            ENTRY88_POLICY_SHA256):
        raise ValueError("Entry 88 deployment checkpoint hash mismatch")
    if (_sha256(ENTRY88.training_path(ENTRY88_DEPLOYMENT_SEED)) !=
            ENTRY88_TRAINING_SHA256):
        raise ValueError("Entry 88 deployment training hash mismatch")
    entry88_net = ENTRY88._load_net(ENTRY88_DEPLOYMENT_SEED, old_controls)

    metadata_manifest_ok = bool(
        metadata.get("policy_manifest_sha256") == POLICY_MANIFEST_SHA256
        and metadata.get("policy_manifest") == manifest)
    provenance = {
        "development_hash": (
            _sha256(ENTRY89.development_results_path()) ==
            DEVELOPMENT_RESULTS_SHA256),
        "development_membership": bool(
            len(development_ids) == len(set(development_ids)) == 5040
            and BASE.identities_sha256(development_ids) ==
            DEVELOPMENT_IDENTITIES_SHA256),
        "policy_manifest_hash": (
            _sha256(manifest_file) == POLICY_MANIFEST_SHA256),
        "training_artifacts_match_manifest": artifacts == manifest["policies"],
        "policies_frozen": manifest.get("status") == "FIVE_POLICIES_FROZEN",
        "midpoint_metadata_hash": (
            _sha256(metadata_path()) == MIDPOINT_METADATA_SHA256),
        "midpoint_status": bool(
            metadata.get("status") == "GENERATED_NOT_SCORED"
            and int(metadata.get("n_rows", -1)) == MIDPOINT.EXPECTED_ROWS
            and int(metadata.get("expected_rows", -1)) == MIDPOINT.EXPECTED_ROWS
            and int(metadata.get("n_final_identities_defined", -1)) == 2430
            and metadata.get("losses_db") == list(MIDPOINT.MIDPOINT_LOSSES_DB)
            and metadata.get("final_requests_defined_not_scored") == [
                [float(pk), float(freq)]
                for pk, freq in MIDPOINT.FINAL_REQUESTS]),
        "midpoint_hashes": bool(
            _sha256(midpoint_path()) == MIDPOINT_GZIP_SHA256
            and table_facts["decoded"] == MIDPOINT_DECODED_SHA256),
        "midpoint_membership": table_facts["midpoint_membership"],
        "freeze_precedes_midpoint_provenance": metadata_manifest_ok,
        "final_membership": bool(
            len(final_ids) == len(set(final_ids)) == 2430
            and BASE.identities_sha256(final_ids) == FINAL_IDENTITIES_SHA256),
        "development_final_overlap_zero": not bool(
            set(development_ids).intersection(final_ids)),
        "result_absent_before_scoring": True,
    }
    if not all(provenance.values()):
        failed = [name for name, value in provenance.items() if not value]
        raise ValueError(f"FINAL provenance failed before scoring: {failed}")

    # The one and only fresh FINAL exposure begins here. Everything above is
    # artifact, membership and hash validation or policy loading.
    fixed = _make_reportable(BASE.score_fixed(table, final_ids, final_starts))
    fixed["arm"] = "fixed_nearest_development_request"
    fixed["quality_delta"] = 0.0

    _, entry88_shielded = SHIELD.score_policy_pair(
        table, final_ids, final_starts, entry88_net, ENTRY88_DEPLOYMENT_SEED)
    entry88_shielded = _make_reportable(entry88_shielded, shielded=True)
    entry88_shielded["arm"] = "entry88_deployment_shielded"
    entry88_shielded["quality_delta"] = float(
        entry88_shielded["mean_quality"] - fixed["mean_quality"])

    raw_rows = []
    shielded_rows = []
    attributions = []
    by_seed = {row["seed"]: row for row in artifacts}
    for seed in TRAIN_SEEDS:
        raw, shielded = SHIELD.score_policy_pair(
            table, final_ids, final_starts, entry89_nets[seed], seed)
        raw = _make_reportable(raw)
        shielded = _make_reportable(shielded, shielded=True)
        raw["arm"] = f"entry89_unshielded_{seed}"
        shielded["arm"] = f"entry89_shielded_{seed}"
        for row in (raw, shielded):
            row["quality_delta"] = float(
                row["mean_quality"] - fixed["mean_quality"])
            row["policy_sha256"] = by_seed[seed]["policy_sha256"]
            row["steps_completed"] = by_seed[seed]["ppo_steps"]
            row["bc_epochs"] = by_seed[seed]["bc_epochs"]
        shielded["retained_all_compliant_starts"] = (
            ENTRY89._retained_all_compliant_starts(fixed, shielded))
        raw_rows.append(raw)
        shielded_rows.append(shielded)
        attributions.append({
            "seed": int(seed),
            "shield_minus_unshielded_quality": float(
                shielded["mean_quality"] - raw["mean_quality"]),
            "shield_minus_unshielded_compliance": float(
                shielded["compliance_rate"] - raw["compliance_rate"]),
            "n_shield_interventions": shielded["n_shield_interventions"],
            "n_shield_fallbacks": shielded["n_shield_fallbacks"],
        })

    global_oracle = _score_hidden_oracle(
        table, final_ids, final_starts, None, "global_hidden_oracle")
    reachable_oracle = _score_hidden_oracle(
        table, final_ids, final_starts, 7, "reachable_hidden_oracle")
    for row in (entry88_shielded, global_oracle, reachable_oracle):
        row["quality_delta"] = float(
            row["mean_quality"] - fixed["mean_quality"])

    fixed_q = np.asarray([
        row["quality"] for row in fixed["per_identity"]], dtype=float)
    primary_q = np.asarray([[
        row["quality"] for row in summary["per_identity"]]
        for summary in shielded_rows], dtype=float)
    paired_delta = primary_q.mean(axis=0) - fixed_q
    confidence_interval = paired_bootstrap_ci(paired_delta)

    controls = {
        "entry88_deployment_shielded": entry88_shielded,
        "entry89_unshielded": raw_rows,
        "entry89_shielded": shielded_rows,
        "entry89_attribution": attributions,
        "global_hidden_oracle": global_oracle,
        "reachable_hidden_oracle": reachable_oracle,
    }
    observation_ok = bool(
        MarginImproveEnv.observation_dim == 62
        and set(ACTOR_OBSERVATION_FIELDS).isdisjoint(ACTOR_HIDDEN_FIELDS))
    imitation_ok = bool(
        manifest.get("development_status") == "EXPOSED_DIAGNOSTIC_ONLY"
        and all(row["bc_epochs"] == ENTRY89.BC_EPOCHS
                and row["bc_support_accuracy"] > 1.0 / 7.0
                for row in artifacts))
    training_ok = bool(
        len(artifacts) == len(TRAIN_SEEDS)
        and {row["seed"] for row in artifacts} == set(TRAIN_SEEDS)
        and all(row["ppo_steps"] == ENTRY89.TOTAL_STEPS and row["finite"]
                for row in artifacts))
    development_safety_ok = bool(
        manifest.get("development_diagnostic_checks", {}).get("D4_safety")
        and manifest.get("development_diagnostics_passed")
        and development_result.get("diagnostic_checks", {}).get("D4_safety"))
    gates = score_gates(
        provenance=provenance, observation_ok=observation_ok,
        imitation_ok=imitation_ok, training_ok=training_ok,
        development_safety_ok=development_safety_ok, fixed=fixed,
        primary=shielded_rows, controls=controls,
        bootstrap_ci=confidence_interval, scope_statement=SCOPE_STATEMENT)
    aggregate = {
        "mean_compliance_rate": float(np.mean([
            row["compliance_rate"] for row in shielded_rows])),
        "mean_quality": float(np.mean([
            row["mean_quality"] for row in shielded_rows])),
        "quality_delta": float(np.mean(paired_delta)),
        "paired_quality_delta_ci95": list(confidence_interval),
        "mean_trials": float(np.mean([
            row["mean_trials"] for row in shielded_rows])),
        "mean_verifier_calls": float(np.mean([
            row["mean_verifier_calls"] for row in shielded_rows])),
        "mean_code_change_rate": float(np.mean([
            row["code_change_rate"] for row in shielded_rows])),
        "total_false_locks": int(sum(
            row["n_false_locks"] for row in shielded_rows)),
        "total_shield_interventions": int(sum(
            row["n_shield_interventions"] for row in shielded_rows)),
        "total_shield_fallbacks": int(sum(
            row["n_shield_fallbacks"] for row in shielded_rows)),
        "positive_seeds": int(sum(
            row["quality_delta"] > 0.0 for row in shielded_rows)),
        "bootstrap_seed": BOOTSTRAP_SEED,
        "bootstrap_resamples": N_BOOTSTRAP,
    }
    out = {
        "task": "entry 89 one-time fresh midpoint FINAL evaluation",
        "final_status": "EVALUATED_ONCE_AFTER_FROZEN_POLICIES_AND_DATA",
        "scope": SCOPE_STATEMENT,
        "policy_freeze_commit": "a84082e",
        "midpoint_evidence_commit": "51a1146",
        "development_identities_sha256": DEVELOPMENT_IDENTITIES_SHA256,
        "final_identities_sha256": FINAL_IDENTITIES_SHA256,
        "n_final_identities": len(final_ids),
        "training_seeds": list(TRAIN_SEEDS),
        "deployment_seed": DEPLOYMENT_SEED,
        "start_selection": start_provenance,
        "provenance": provenance,
        "observation": {
            "visible_fields": list(ACTOR_OBSERVATION_FIELDS),
            "hidden_fields": list(ACTOR_HIDDEN_FIELDS),
        },
        "fixed": fixed,
        "controls": controls,
        "aggregate": aggregate,
        "gates": gates,
        "passed": all(gates.values()),
        "simulations_run_during_final": 0,
    }
    result_file.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def report(out: dict) -> None:
    fixed = out["fixed"]
    print("=" * 78)
    print("ENTRY 89 ONE-TIME FRESH MIDPOINT FINAL")
    print("=" * 78)
    print(f"  fixed: compliance {fixed['compliance_rate']:.4f}, "
          f"q {fixed['mean_quality']:.4f}, trials {fixed['mean_trials']:.3f}")
    for row in out["controls"]["entry89_shielded"]:
        print(f"  seed {row['seed']}: compliance {row['compliance_rate']:.4f}, "
              f"q {row['mean_quality']:.4f}, delta "
              f"{row['quality_delta']:+.4f}, trials {row['mean_trials']:.3f}, "
              f"fallbacks {row['n_shield_fallbacks']}")
    aggregate = out["aggregate"]
    print(f"  aggregate: compliance {aggregate['mean_compliance_rate']:.4f}, "
          f"q {aggregate['mean_quality']:.4f}, delta "
          f"{aggregate['quality_delta']:+.4f}, trials "
          f"{aggregate['mean_trials']:.3f}")
    print(f"  paired 95% CI: {aggregate['paired_quality_delta_ci95']}")
    for name, passed in out["gates"].items():
        print(f"  {name}: {'PASS' if passed else 'FAIL'}")
    print(f"  OVERALL: {'PASS' if out['passed'] else 'FAIL'}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--evaluate", action="store_true")
    mode.add_argument("--analyse", action="store_true")
    args = parser.parse_args(argv)
    if args.evaluate:
        out = evaluate()
    else:
        path = results_path()
        if not path.exists():
            raise SystemExit(f"missing {path.name}; FINAL has not run")
        out = json.loads(path.read_text(encoding="utf-8"))
    report(out)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
