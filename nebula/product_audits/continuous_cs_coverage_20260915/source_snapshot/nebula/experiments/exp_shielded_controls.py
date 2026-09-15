"""Entry 89 exposed-DEVELOPMENT controls for the structural safety shield.

This diagnostic replays the five frozen Entry 88 policies on the now-exposed
5,040 identities.  It runs no SPICE and cannot support a fresh result claim.
The midpoint FINAL source must not exist when this artifact is produced.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

import numpy as np

from nebula.experiments import exp_joint_bank as J
from nebula.experiments import exp_margin_improve_controls as BASE
from nebula.experiments import exp_margin_improve_ppo as PPO
from nebula.rl.margin_adapt_env import MarginBankTable
from nebula.rl.margin_improve_env import MarginImproveEnv
from nebula.rl.masked_discrete_ppo import deterministic_action
from nebula.rl.oracle_imitation import reachable_teacher, setting_distance
from nebula.rl.safety_shield import (
    ShieldSelection, select_best_compliant_visited,
)

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "joint_bank_73_run.jsonl.gz"
RESULTS = HERE / "shielded_controls_results.json"
MIDPOINT_JOURNAL = HERE / "joint_bank_midpoint_run.jsonl.gz"
SOURCE_SHA256 = BASE.SOURCE_SHA256
FINAL_STATUS = "NOT_GENERATED_NOT_SCORED"
SIMULATIONS_RUN = 0


def development_identities() -> list[tuple]:
    train, final = BASE.identities(BASE.REQUESTS)
    rows = sorted(set(train).union(final))
    if len(rows) != 5040:
        raise AssertionError(f"expected 5040 DEVELOPMENT identities, got {len(rows)}")
    return rows


def shielded_record(ep, selected: ShieldSelection) -> dict:
    improvement = float(selected.quality - ep.start_quality)
    ret = improvement if selected.compliant else -1.0 - ep.start_quality
    return {
        "corner": ep.corner, "loss_db": ep.loss_db,
        "target_peaking_db": ep.target_peaking_db,
        "target_f_peak_hz": ep.target_f_peak_hz,
        "start_setting": ep.start_setting,
        "policy_locked_setting": ep.locked_setting,
        "locked_setting": selected.setting,
        "compliant": bool(selected.compliant),
        "start_quality": float(ep.start_quality),
        "quality": float(selected.quality),
        "quality_improvement": improvement,
        "n_trials": int(len(ep.settings_tried)),
        "return": float(ret),
        "move_distance": setting_distance(ep.start_setting, selected.setting),
        "shield_intervened": bool(selected.intervened),
        "shield_failure": bool(selected.shield_failure),
        "n_verifier_calls": int(selected.n_verifier_calls),
    }


def summarise_shielded(name: str, episodes: Sequence[dict]) -> dict:
    rows = list(episodes)
    out = BASE._summarise(name, rows)
    out.update({
        "n_shield_interventions": int(sum(
            bool(row["shield_intervened"]) for row in rows)),
        "n_shield_failures": int(sum(
            bool(row["shield_failure"]) for row in rows)),
        "mean_verifier_calls": float(np.mean([
            row["n_verifier_calls"] for row in rows])),
    })
    return out


def score_policy_pair(table: MarginBankTable, identities: Sequence[tuple],
                      starts: dict, net, seed: int) -> tuple[dict, dict]:
    raw_records = []
    shielded_records = []
    for corner, loss, peaking, frequency in identities:
        identity = (corner, loss, peaking, frequency)
        env = MarginImproveEnv(table, [identity], starts, seed=seed)
        obs = env.reset(corner=corner, loss_db=loss,
                        request=(peaking, frequency))
        while env.ep.locked_setting is None:
            action = deterministic_action(net, obs, env.action_mask())
            obs, _, terminated, _, _ = env.step(action)
            if terminated:
                break
        raw_records.append(BASE._episode_record(env.ep))
        selected = select_best_compliant_visited(
            table, identity, env.ep.settings_tried)
        shielded_records.append(shielded_record(env.ep, selected))
    raw = BASE._summarise(f"entry88_raw_{seed}", raw_records)
    shielded = summarise_shielded(
        f"entry88_shielded_{seed}", shielded_records)
    raw["seed"] = shielded["seed"] = int(seed)
    raw["quality_delta"] = float(raw["mean_quality"])
    shielded["quality_delta"] = float(shielded["mean_quality"])
    return raw, shielded


def development_checks(fixed: dict, shielded: Sequence[dict]) -> dict:
    rows = list(shielded)
    base_compliance = float(fixed["compliance_rate"])
    base_quality = float(fixed["mean_quality"])
    return {
        "D1_safety": bool(len(rows) == 5 and all(
            float(row["compliance_rate"]) >= base_compliance for row in rows)),
        "D2_quality": bool(len(rows) == 5 and sum(
            float(row.get("quality_delta",
                          float(row["mean_quality"]) - base_quality)) >= 0.02
            for row in rows) >= 4),
    }


def _teacher_summary(table: MarginBankTable, identities: Sequence[tuple],
                     starts: dict) -> dict:
    distances = []
    qualities = []
    for identity in identities:
        request = (float(identity[2]), float(identity[3]))
        start = int(starts[request])
        target = reachable_teacher(table, identity, start, radius=7)
        distances.append(setting_distance(start, target))
        qualities.append(table.quality(target, *identity))
    return {
        "n_identities": len(distances),
        "mean_distance": float(np.mean(distances)),
        "fraction_positive_distance": float(np.mean(np.asarray(distances) > 0)),
        "mean_quality": float(np.mean(qualities)),
    }


def run() -> dict:
    if RESULTS.exists():
        raise FileExistsError(f"refusing to overwrite {RESULTS.name}")
    if MIDPOINT_JOURNAL.exists():
        raise RuntimeError("fresh midpoint journal exists before policy freeze")
    decoded = J._decoded_sha256(SOURCE)
    if decoded != SOURCE_SHA256:
        raise ValueError(f"source hash mismatch: {decoded}")
    controls = PPO._load_controls()
    nets = {seed: PPO._load_net(seed, controls) for seed in PPO.TRAIN_SEEDS}
    table = MarginBankTable.from_path(SOURCE)
    identities = development_identities()
    starts = BASE.select_start_settings(table, identities)
    fixed = BASE.score_fixed(table, identities, starts)
    raw = []
    shielded = []
    for seed in PPO.TRAIN_SEEDS:
        before, after = score_policy_pair(
            table, identities, starts, nets[seed], seed)
        before["quality_delta"] = (
            before["mean_quality"] - fixed["mean_quality"])
        after["quality_delta"] = (
            after["mean_quality"] - fixed["mean_quality"])
        raw.append(before)
        shielded.append(after)
    checks = development_checks(fixed, shielded)
    out = {
        "task": "entry 89 exposed DEVELOPMENT shield controls",
        "source_decoded_sha256": decoded,
        "development_status": "EXPOSED_DIAGNOSTIC_ONLY",
        "final_status": FINAL_STATUS,
        "n_development_identities": len(identities),
        "losses_db": list(J.LOSSES_DB),
        "requests": [list(row) for row in BASE.REQUESTS],
        "fixed": fixed,
        "entry88_unshielded": raw,
        "entry88_shielded": shielded,
        "teacher": _teacher_summary(table, identities, starts),
        "checks": checks, "passed": all(checks.values()),
        "simulations_run": SIMULATIONS_RUN,
    }
    RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def report(out: dict) -> None:
    fixed = out["fixed"]
    print("=" * 78)
    print("ENTRY 89 EXPOSED DEVELOPMENT SHIELD CONTROLS")
    print("=" * 78)
    print(f"  fixed: compliance {fixed['compliance_rate']:.4f}, "
          f"q {fixed['mean_quality']:.4f}")
    for row in out["entry88_shielded"]:
        print(f"  seed {row['seed']}: compliance {row['compliance_rate']:.4f}, "
              f"q {row['mean_quality']:.4f}, delta "
              f"{row['quality_delta']:+.4f}, interventions "
              f"{row['n_shield_interventions']}")
    for name, passed in out["checks"].items():
        print(f"  {name}: {'PASS' if passed else 'FAIL'}")
    print(f"  DEVELOPMENT ONLY: {'PASS' if out['passed'] else 'FAIL'}")
    print(f"  FINAL: {out['final_status']}")


def main() -> int:
    report(run())
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
