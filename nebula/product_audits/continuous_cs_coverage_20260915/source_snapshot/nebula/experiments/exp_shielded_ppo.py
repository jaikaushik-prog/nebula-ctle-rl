"""Train one Entry 89 oracle-warm-started masked-PPO seed.

Training uses only the fully exposed DEVELOPMENT table.  The command refuses
to run if any fresh midpoint journal exists.  FINAL evaluation is added only
after all five durable policy artifacts are frozen.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import torch

from nebula.experiments import exp_joint_bank as J
from nebula.experiments import exp_margin_improve_controls as BASE
from nebula.experiments import exp_shielded_controls as CONTROLS
from nebula.rl.discrete_ppo import state_dict_sha256
from nebula.rl.margin_adapt_env import MarginBankTable
from nebula.rl.margin_improve_env import MarginImproveEnv
from nebula.rl.masked_discrete_ppo import (
    DiscretePPOConfig, MaskedActorCritic, train,
)
from nebula.rl.oracle_imitation import oracle_samples
from nebula.rl.oracle_warmstart import BCConfig, pretrain_actor

HERE = Path(__file__).resolve().parent
SOURCE_NAME = "joint_bank_73_run.jsonl.gz"
CONTROLS_NAME = "shielded_controls_results.json"
MIDPOINT_NAME = "joint_bank_midpoint_run.jsonl.gz"
DEVELOPMENT_RESULTS_NAME = "shielded_policy_development_results.json"
MANIFEST_NAME = "shielded_policy_manifest.json"
DEVELOPMENT_RESULTS = HERE / DEVELOPMENT_RESULTS_NAME
SOURCE_SHA256 = BASE.SOURCE_SHA256
CONTROLS_SHA256 = "82F868B94A6D80C790C104ABF7383DC2257E919DC8E2441D9509D44AC066FF45"

TRAIN_SEEDS = tuple(range(2026090500, 2026090505))
DEPLOYMENT_SEED = 2026090500
BC_EPOCHS = 50
BC_BATCH_SIZE = 256
BC_LR = 3e-4
TOTAL_STEPS = 200_000
FINAL_STATUS = "NOT_GENERATED_NOT_SCORED"


def source_path() -> Path:
    return HERE / SOURCE_NAME


def controls_path() -> Path:
    return HERE / CONTROLS_NAME


def midpoint_path() -> Path:
    return HERE / MIDPOINT_NAME


def bc_path(seed: int) -> Path:
    return HERE / f"shielded_bc_{int(seed)}.pth"


def policy_path(seed: int) -> Path:
    return HERE / f"shielded_policy_{int(seed)}.pth"


def training_path(seed: int) -> Path:
    return HERE / f"shielded_train_{int(seed)}.json"


def development_results_path() -> Path:
    return HERE / DEVELOPMENT_RESULTS_NAME


def policy_manifest_path() -> Path:
    return HERE / MANIFEST_NAME


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _load_controls() -> dict:
    path = controls_path()
    digest = _sha256(path)
    if digest != CONTROLS_SHA256:
        raise ValueError(f"controls hash mismatch: {digest}")
    out = json.loads(path.read_text(encoding="utf-8"))
    if out.get("final_status") != FINAL_STATUS:
        raise ValueError("controls did not preserve nonexistent FINAL")
    return out


def _finite_ppo(stats: dict) -> bool:
    names = ("policy_loss", "value_loss", "entropy", "update_seconds")
    return all(math.isfinite(float(value)) for name in names
               for value in stats[name])


def training_health(row: dict, seed: int) -> bool:
    """Validate the complete registered BC plus PPO contract for one seed."""
    try:
        bc_cfg = dict(row["bc_config"])
        ppo_cfg = dict(row["ppo_config"])
        expected_bc = asdict(BCConfig(
            seed=int(seed), epochs=BC_EPOCHS,
            batch_size=BC_BATCH_SIZE, lr=BC_LR))
        expected_ppo = asdict(DiscretePPOConfig(
            seed=int(seed), total_steps=TOTAL_STEPS))
        if isinstance(ppo_cfg.get("hidden"), list):
            ppo_cfg["hidden"] = tuple(ppo_cfg["hidden"])
        losses = [float(value) for value in row["bc_stats"]["loss"]]
        return bool(
            int(row["seed"]) == int(seed)
            and row["source_decoded_sha256"] == SOURCE_SHA256
            and row["controls_sha256"] == CONTROLS_SHA256
            and row["development_status"] == "EXPOSED_TRAINING_ONLY"
            and row["final_status"] == FINAL_STATUS
            and bc_cfg == expected_bc
            and ppo_cfg == expected_ppo
            and int(row["bc_stats"]["epochs_completed"]) == BC_EPOCHS
            and len(losses) == BC_EPOCHS
            and all(math.isfinite(value) for value in losses)
            and int(row["steps_completed"]) == TOTAL_STEPS
            and bool(row["bc_changed_actor"])
            and bool(row["bc_preserved_value"])
            and bool(row["ppo_started_from_bc"])
            and bool(row["ppo_changed_weights"])
            and bool(row["finite"])
            and int(row["simulations_run"]) == 0)
    except (KeyError, TypeError, ValueError):
        return False


def _validate_payload(payload: dict, seed: int, kind: str) -> None:
    expected = {
        "seed": int(seed), "kind": kind,
        "observation_dim": 62, "action_dim": 7,
        "source_decoded_sha256": SOURCE_SHA256,
        "controls_sha256": CONTROLS_SHA256,
    }
    for name, value in expected.items():
        if payload.get(name) != value:
            raise ValueError(f"seed {seed} {kind} {name} mismatch")
    if tuple(payload.get("hidden", ())) != (64, 64):
        raise ValueError(f"seed {seed} {kind} hidden sizes mismatch")


def validate_training_artifacts() -> tuple[list[dict], dict[int, MaskedActorCritic]]:
    """Load and cross-check all fifteen durable artifacts before any scoring."""
    rows = []
    nets = {}
    file_hashes = []
    bc_weights = []
    final_weights = []
    for seed in TRAIN_SEEDS:
        paths = (bc_path(seed), policy_path(seed), training_path(seed))
        missing = [path.name for path in paths if not path.exists()]
        if missing:
            raise FileNotFoundError(f"missing seed {seed} artifacts: {missing}")
        summary = json.loads(training_path(seed).read_text(encoding="utf-8"))
        if not training_health(summary, seed):
            raise ValueError(f"seed {seed} training health mismatch")
        bc = torch.load(bc_path(seed), map_location="cpu", weights_only=False)
        policy = torch.load(
            policy_path(seed), map_location="cpu", weights_only=False)
        _validate_payload(bc, seed, "entry89_bc")
        _validate_payload(policy, seed, "entry89_bc_plus_ppo")
        bc_hash = state_dict_sha256(bc["state_dict"])
        final_hash = state_dict_sha256(policy["state_dict"])
        if bc_hash != summary["bc_weights_sha256"]:
            raise ValueError(f"seed {seed} BC state hash mismatch")
        if final_hash != summary["final_weights_sha256"]:
            raise ValueError(f"seed {seed} final state hash mismatch")
        net = MaskedActorCritic(62, 7, (64, 64))
        net.load_state_dict(policy["state_dict"])
        net.eval()
        artifact = {
            "seed": int(seed),
            "bc_file": bc_path(seed).name,
            "bc_sha256": _sha256(bc_path(seed)),
            "policy_file": policy_path(seed).name,
            "policy_sha256": _sha256(policy_path(seed)),
            "training_file": training_path(seed).name,
            "training_sha256": _sha256(training_path(seed)),
            "random_weights_sha256": summary["random_weights_sha256"],
            "bc_weights_sha256": bc_hash,
            "final_weights_sha256": final_hash,
            "bc_support_accuracy": float(
                summary["bc_stats"]["support_accuracy"]),
            "bc_epochs": int(summary["bc_stats"]["epochs_completed"]),
            "ppo_steps": int(summary["steps_completed"]),
            "finite": bool(summary["finite"]),
        }
        rows.append(artifact)
        nets[int(seed)] = net
        file_hashes.extend((artifact["bc_sha256"], artifact["policy_sha256"],
                            artifact["training_sha256"]))
        bc_weights.append(bc_hash)
        final_weights.append(final_hash)
    if len(set(file_hashes)) != 15:
        raise ValueError("the fifteen training artifact hashes are not distinct")
    if len(set(bc_weights)) != 5 or len(set(final_weights)) != 5:
        raise ValueError("BC or final policy weights are not distinct across seeds")
    return rows, nets


def development_checks(training_ok: bool, fixed: dict,
                       shielded: Sequence[dict]) -> dict:
    """Exposed diagnostics; D4/D5 do not select or alter frozen policies."""
    rows = list(shielded)
    base_compliance = float(fixed["compliance_rate"])
    return {
        "D3_training": bool(training_ok),
        "D4_safety": bool(len(rows) == len(TRAIN_SEEDS) and all(
            float(row["compliance_rate"]) >= base_compliance
            and bool(row.get("retained_all_compliant_starts", True))
            for row in rows)),
        "D5_quality": bool(len(rows) == len(TRAIN_SEEDS) and sum(
            float(row["quality_delta"]) >= 0.02 for row in rows) >= 4),
    }


def train_seed(seed: int) -> dict:
    seed = int(seed)
    if seed not in TRAIN_SEEDS:
        raise ValueError(f"unregistered seed {seed}")
    if midpoint_path().exists():
        raise RuntimeError("midpoint data exists before all policies froze")
    artifacts = (bc_path(seed), policy_path(seed), training_path(seed))
    if any(path.exists() for path in artifacts):
        raise FileExistsError(f"refusing to overwrite seed {seed} artifact")
    controls = _load_controls()
    decoded = J._decoded_sha256(source_path())
    if decoded != SOURCE_SHA256:
        raise ValueError(f"source hash mismatch: {decoded}")
    table = MarginBankTable.from_path(source_path())
    identities = CONTROLS.development_identities()
    starts = BASE.select_start_settings(table, identities)
    samples = oracle_samples(table, identities, starts, radius=7)

    torch.manual_seed(seed)
    net = MaskedActorCritic(62, 7, (64, 64))
    random_weights = state_dict_sha256(net.state_dict())
    bc_cfg = BCConfig(
        seed=seed, epochs=BC_EPOCHS, batch_size=BC_BATCH_SIZE, lr=BC_LR)
    bc_stats = pretrain_actor(net, samples, bc_cfg)
    bc_state = {name: value.detach().cpu().clone()
                for name, value in net.state_dict().items()}
    bc_weights = state_dict_sha256(bc_state)

    env = MarginImproveEnv(table, identities, starts, seed=seed)
    ppo_cfg = DiscretePPOConfig(seed=seed, total_steps=TOTAL_STEPS)
    net, ppo_stats = train(env, ppo_cfg, initial_net=net)
    ppo_dict = asdict(ppo_stats)
    final_weights = state_dict_sha256(net.state_dict())
    out = {
        "task": "entry 89 oracle-warm-started masked PPO training",
        "seed": seed,
        "source_decoded_sha256": decoded,
        "controls_sha256": CONTROLS_SHA256,
        "development_status": "EXPOSED_TRAINING_ONLY",
        "final_status": FINAL_STATUS,
        "n_development_identities": len(identities),
        "n_oracle_samples": len(samples),
        "bc_config": asdict(bc_cfg), "bc_stats": asdict(bc_stats),
        "ppo_config": asdict(ppo_cfg), "ppo_stats": ppo_dict,
        "steps_completed": ppo_stats.steps_completed,
        "random_weights_sha256": random_weights,
        "bc_weights_sha256": bc_weights,
        "final_weights_sha256": final_weights,
        "bc_changed_actor": (
            bc_stats.initial_actor_sha256 != bc_stats.final_actor_sha256),
        "bc_preserved_value": (
            bc_stats.initial_value_sha256 == bc_stats.final_value_sha256),
        "ppo_started_from_bc": ppo_stats.initial_weights_sha256 == bc_weights,
        "ppo_changed_weights": final_weights != bc_weights,
        "finite": bool(_finite_ppo(ppo_dict)
                       and all(math.isfinite(x) for x in bc_stats.loss)),
        "simulations_run": 0,
    }
    torch.save({
        "seed": seed, "kind": "entry89_bc",
        "observation_dim": 62, "action_dim": 7, "hidden": (64, 64),
        "state_dict": bc_state, "source_decoded_sha256": decoded,
        "controls_sha256": CONTROLS_SHA256,
    }, bc_path(seed))
    torch.save({
        "seed": seed, "kind": "entry89_bc_plus_ppo",
        "observation_dim": 62, "action_dim": 7, "hidden": (64, 64),
        "state_dict": net.state_dict(), "source_decoded_sha256": decoded,
        "controls_sha256": CONTROLS_SHA256,
    }, policy_path(seed))
    training_path(seed).write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def _retained_all_compliant_starts(fixed: dict, shielded: dict) -> bool:
    before = fixed["per_identity"]
    after = shielded["per_identity"]
    if len(before) != len(after):
        return False
    return all(not bool(a["compliant"]) or bool(b["compliant"])
               for a, b in zip(before, after))


def evaluate_development() -> dict:
    """Score all frozen policies on exposed DEVELOPMENT only, with no SPICE."""
    result = development_results_path()
    if result.exists():
        raise FileExistsError(f"refusing to overwrite {result.name}")
    if policy_manifest_path().exists():
        raise RuntimeError("policy manifest exists before DEVELOPMENT scoring")
    if midpoint_path().exists():
        raise RuntimeError("fresh midpoint data exists before policy freeze")
    artifacts, nets = validate_training_artifacts()
    decoded = J._decoded_sha256(source_path())
    if decoded != SOURCE_SHA256:
        raise ValueError(f"source hash mismatch: {decoded}")
    controls = _load_controls()
    table = MarginBankTable.from_path(source_path())
    identities = CONTROLS.development_identities()
    starts = BASE.select_start_settings(table, identities)
    fixed = BASE.score_fixed(table, identities, starts)
    raw = []
    shielded = []
    by_seed = {row["seed"]: row for row in artifacts}
    for seed in TRAIN_SEEDS:
        before, after = CONTROLS.score_policy_pair(
            table, identities, starts, nets[seed], seed)
        before["arm"] = f"entry89_unshielded_{seed}"
        after["arm"] = f"entry89_shielded_{seed}"
        before["quality_delta"] = float(
            before["mean_quality"] - fixed["mean_quality"])
        after["quality_delta"] = float(
            after["mean_quality"] - fixed["mean_quality"])
        after["retained_all_compliant_starts"] = (
            _retained_all_compliant_starts(fixed, after))
        for row in (before, after):
            row.update({
                "policy_sha256": by_seed[seed]["policy_sha256"],
                "training_sha256": by_seed[seed]["training_sha256"],
                "steps_completed": by_seed[seed]["ppo_steps"],
                "bc_epochs": by_seed[seed]["bc_epochs"],
                "finite": by_seed[seed]["finite"],
            })
        raw.append(before)
        shielded.append(after)
    checks = development_checks(True, fixed, shielded)
    integrity = {
        "source_hash": decoded == SOURCE_SHA256,
        "controls_hash": _sha256(controls_path()) == CONTROLS_SHA256,
        "identity_membership": len(identities) == len(set(identities)) == 5040,
        "five_training_artifact_sets": len(artifacts) == 5,
        "final_untouched": not midpoint_path().exists(),
    }
    out = {
        "task": "entry 89 frozen-policy exposed DEVELOPMENT evaluation",
        "source_decoded_sha256": decoded,
        "controls_sha256": _sha256(controls_path()),
        "development_status": "EXPOSED_DIAGNOSTIC_ONLY",
        "final_status": FINAL_STATUS,
        "training_seeds": list(TRAIN_SEEDS),
        "deployment_seed": DEPLOYMENT_SEED,
        "n_development_identities": len(identities),
        "training_artifacts": artifacts,
        "fixed": fixed,
        "entry88_unshielded": controls["entry88_unshielded"],
        "entry88_shielded": controls["entry88_shielded"],
        "oracle_teacher": controls["teacher"],
        "entry89_unshielded": raw,
        "entry89_shielded": shielded,
        "integrity": integrity,
        "integrity_passed": all(integrity.values()),
        "diagnostic_checks": checks,
        "diagnostics_passed": all(checks.values()),
        "simulations_run": 0,
    }
    result.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def freeze_policies() -> dict:
    """Write the immutable five-policy hash manifest after DEVELOPMENT scoring."""
    result_path = development_results_path()
    manifest_path = policy_manifest_path()
    if not result_path.exists():
        raise FileNotFoundError("DEVELOPMENT result is required before policy freeze")
    if manifest_path.exists():
        raise FileExistsError(f"refusing to overwrite {manifest_path.name}")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if result.get("final_status") != FINAL_STATUS:
        raise ValueError("DEVELOPMENT result FINAL status is not untouched")
    if result.get("training_seeds") != list(TRAIN_SEEDS):
        raise ValueError("DEVELOPMENT result seed membership mismatch")
    if not bool(result.get("integrity_passed")):
        raise ValueError("DEVELOPMENT result integrity did not pass")
    artifacts, _ = validate_training_artifacts()
    expected = result.get("training_artifacts")
    if expected is not None and artifacts != expected:
        raise ValueError("training artifacts changed after DEVELOPMENT scoring")
    manifest = {
        "task": "entry 89 immutable five-policy freeze before fresh data",
        "status": "FIVE_POLICIES_FROZEN",
        "source_decoded_sha256": SOURCE_SHA256,
        "controls_sha256": CONTROLS_SHA256,
        "development_results_file": result_path.name,
        "development_results_sha256": _sha256(result_path),
        "development_status": result["development_status"],
        "development_diagnostic_checks": result["diagnostic_checks"],
        "development_diagnostics_passed": result["diagnostics_passed"],
        "final_status": FINAL_STATUS,
        "deployment_seed": DEPLOYMENT_SEED,
        "training_seeds": list(TRAIN_SEEDS),
        "policies": artifacts,
    }
    manifest_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


def report_development(out: dict) -> None:
    print("=" * 78)
    print("ENTRY 89 EXPOSED DEVELOPMENT POLICY DIAGNOSTIC")
    print("=" * 78)
    fixed = out["fixed"]
    print(f"  fixed: compliance {fixed['compliance_rate']:.4f}, "
          f"q {fixed['mean_quality']:.4f}")
    for raw, shielded in zip(out["entry89_unshielded"],
                             out["entry89_shielded"]):
        print(f"  seed {raw['seed']}: raw compliance "
              f"{raw['compliance_rate']:.4f}, q {raw['mean_quality']:.4f}; "
              f"shielded compliance {shielded['compliance_rate']:.4f}, "
              f"q {shielded['mean_quality']:.4f}, delta "
              f"{shielded['quality_delta']:+.4f}, trials "
              f"{shielded['mean_trials']:.3f}")
    for name, passed in out["diagnostic_checks"].items():
        print(f"  {name}: {'PASS' if passed else 'FAIL'}")
    print(f"  DEVELOPMENT ONLY: "
          f"{'PASS' if out['diagnostics_passed'] else 'FAIL'}")
    print(f"  FINAL: {out['final_status']}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--train-seed", type=int)
    mode.add_argument("--evaluate-development", action="store_true")
    mode.add_argument("--freeze", action="store_true")
    mode.add_argument("--analyse-development", action="store_true")
    args = parser.parse_args(argv)
    if args.train_seed is not None:
        out = train_seed(args.train_seed)
        print(f"seed {out['seed']} complete: BC {out['bc_config']['epochs']} "
              f"epochs, PPO {out['steps_completed']} steps, "
              f"accuracy {out['bc_stats']['support_accuracy']:.4f}, "
              f"finite={out['finite']}")
    elif args.evaluate_development:
        report_development(evaluate_development())
    elif args.freeze:
        out = freeze_policies()
        print(f"frozen {len(out['policies'])} policies; FINAL remains "
              f"{out['final_status']}")
    else:
        result = development_results_path()
        if not result.exists():
            raise SystemExit(f"missing {result.name}; evaluate DEVELOPMENT first")
        report_development(json.loads(result.read_text(encoding="utf-8")))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
