"""Entry 115A: exhaustive-oracle regret for frozen PPO trajectories.

This is a cached, exposed-data diagnostic. It never trains or runs SPICE.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import subprocess
import time
from pathlib import Path

import numpy as np

from nebula.experiments import exp_post_review_attribution as A
from nebula.experiments import exp_shielded_final as F
from nebula.rl.safety_shield import select_best_compliant_visited

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "nebula/WINNING_SPRINT_PLAN.md"
SOURCE = ROOT / "nebula/product_audits/entry113_attribution_20260907"
NEAR_REGRET = 0.05
TIGHT_REGRET = 0.01
MEAN_REGRET_GATE = 0.05
NEAR_FRACTION_GATE = 0.90
VISIT_REDUCTION_GATE = 20.0


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def frozen_plan() -> str:
    committed = subprocess.check_output(
        ["git", "show", "HEAD:nebula/WINNING_SPRINT_PLAN.md"], cwd=ROOT)
    if committed.replace(b"\r\n", b"\n") != PLAN.read_bytes().replace(b"\r\n", b"\n"):
        raise ValueError("protocol must be committed unchanged before measurement")
    return hashlib.sha256(committed).hexdigest()


def verify_source() -> dict:
    manifest = json.loads((SOURCE / "sha256.json").read_text(encoding="utf-8"))
    for name, expected in manifest.items():
        path = (SOURCE / name).resolve()
        if not path.is_relative_to(SOURCE.resolve()):
            raise ValueError("source manifest escapes its evidence directory")
        if not path.is_file() or sha(path) != expected:
            raise ValueError(f"source hash mismatch: {name}")
    return manifest


def load_ppo_rows() -> tuple[list[dict], dict]:
    manifest = verify_source()
    rows = []
    with gzip.open(SOURCE / "episodes.jsonl.gz", "rt", encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            if row["arm"] == "ppo" and row["budget"] == 8:
                rows.append(row)
    seeds = sorted({int(row["seed"]) for row in rows})
    if seeds != list(A.P.TRAIN_SEEDS):
        raise ValueError("PPO seed membership mismatch")
    if len(rows) != 5 * 2430:
        raise ValueError("expected five complete 2,430-identity PPO evaluations")
    keys = [(row["seed"], *row["identity"]) for row in rows]
    if len(keys) != len(set(tuple(key) for key in keys)):
        raise ValueError("duplicate PPO identity")
    return rows, manifest


def oracle_row(table, identity: tuple, settings: list[int]) -> dict:
    selected = select_best_compliant_visited(table, identity, settings)
    return {
        "identity": list(identity),
        "selected": int(selected.setting),
        "compliant": bool(selected.compliant),
        "quality": float(selected.quality),
        "n_visits": len(settings),
    }


def compare_row(policy: dict, oracle: dict) -> dict:
    if policy["identity"] != oracle["identity"]:
        raise ValueError("policy/oracle identity mismatch")
    oq = float(oracle["quality"])
    pq = float(policy["quality"])
    regret = oq - pq
    if regret < -1e-12:
        raise ValueError("policy quality exceeds exhaustive oracle")
    return {
        "seed": int(policy["seed"]),
        "identity": list(policy["identity"]),
        "policy_selected": int(policy["selected"]),
        "oracle_selected": int(oracle["selected"]),
        "policy_compliant": bool(policy["compliant"]),
        "oracle_compliant": bool(oracle["compliant"]),
        "policy_quality": pq,
        "oracle_quality": oq,
        "quality_regret": max(0.0, regret),
        "within_0p01": bool(oracle["compliant"] and regret <= TIGHT_REGRET + 1e-12),
        "within_0p05": bool(oracle["compliant"] and regret <= NEAR_REGRET + 1e-12),
        "policy_visits": int(policy["n_visits"]),
        "policy_unique_visits": int(policy["n_unique"]),
        "exhaustive_visits": int(oracle["n_visits"]),
    }


def summarise(rows: list[dict]) -> dict:
    solvable = [row for row in rows if row["oracle_compliant"]]
    if not solvable:
        raise ValueError("oracle found no solvable identities")
    regrets = np.asarray([row["quality_regret"] for row in solvable])
    visits = np.asarray([row["policy_visits"] for row in rows], dtype=float)
    unique = np.asarray([row["policy_unique_visits"] for row in rows], dtype=float)
    return {
        "n_rows": len(rows),
        "n_oracle_solvable": len(solvable),
        "policy_compliance": float(np.mean([row["policy_compliant"] for row in rows])),
        "oracle_compliance": float(np.mean([row["oracle_compliant"] for row in rows])),
        "policy_quality": float(np.mean([row["policy_quality"] for row in rows])),
        "oracle_quality": float(np.mean([row["oracle_quality"] for row in rows])),
        "mean_regret_oracle_solvable": float(regrets.mean()),
        "median_regret_oracle_solvable": float(np.median(regrets)),
        "p90_regret_oracle_solvable": float(np.percentile(regrets, 90)),
        "fraction_within_0p01": float(np.mean([row["within_0p01"] for row in solvable])),
        "fraction_within_0p05": float(np.mean([row["within_0p05"] for row in solvable])),
        "mean_policy_visits": float(visits.mean()),
        "mean_policy_unique_visits": float(unique.mean()),
        "candidate_visit_reduction": float(512.0 / visits.mean()),
        "unique_candidate_reduction": float(512.0 / unique.mean()),
    }


def run(out: Path) -> dict:
    out = Path(out)
    protocol_hash = frozen_plan()
    out.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    policy_rows, source_manifest = load_ppo_rows()
    table, _, facts = F._load_midpoint_table()
    settings = [int(value) for value in table.settings]
    if settings != list(range(512)):
        raise ValueError("exhaustive setting membership is not exactly 0..511")

    identities = sorted({tuple(row["identity"]) for row in policy_rows})
    if len(identities) != 2430:
        raise ValueError("identity membership mismatch")
    oracle = {}
    oracle_started = time.perf_counter()
    for identity in identities:
        oracle[identity] = oracle_row(table, identity, settings)
    oracle_wall = time.perf_counter() - oracle_started

    comparisons = []
    policy_score_started = time.perf_counter()
    for row in policy_rows:
        identity = tuple(row["identity"])
        # Re-score the visited prefix so policy and exhaustive timing use the
        # same selection implementation. The saved selection is an integrity gate.
        selected = select_best_compliant_visited(table, identity, row["visits"])
        if (selected.setting != row["selected"] or
                selected.compliant != bool(row["compliant"]) or
                abs(selected.quality - float(row["quality"])) > 1e-12):
            raise ValueError("saved PPO selection does not reproduce")
        comparisons.append(compare_row(row, oracle[identity]))
    policy_score_wall = time.perf_counter() - policy_score_started

    aggregate = summarise(comparisons)
    solvable = [row for row in comparisons if row["oracle_compliant"]]
    aggregate["mean_regret_ci95"] = A.grouped_interval(
        [row["identity"] for row in solvable],
        [row["quality_regret"] for row in solvable], seed=20260908115)
    aggregate["within_0p05_ci95"] = A.grouped_interval(
        [row["identity"] for row in solvable],
        [float(row["within_0p05"]) for row in solvable], seed=20260908116)
    aggregate["near_optimality_gate"] = bool(
        aggregate["mean_regret_oracle_solvable"] <= MEAN_REGRET_GATE and
        aggregate["fraction_within_0p05"] >= NEAR_FRACTION_GATE)
    aggregate["visit_reduction_gate"] = bool(
        aggregate["candidate_visit_reduction"] >= VISIT_REDUCTION_GATE)

    with gzip.open(out / "per_identity.jsonl.gz", "wt", encoding="utf-8") as fh:
        for row in comparisons:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")
    result = {
        "status": "ENTRY115_EXPOSED_CACHED_BENCHMARK",
        "protocol_sha256": protocol_hash,
        "source_sha256": source_manifest,
        "source_facts": facts,
        "simulations_run": 0,
        "training_steps": 0,
        "n_settings": len(settings),
        "n_identities": len(identities),
        "n_policy_seeds": 5,
        "aggregate": aggregate,
        "cached_timing": {
            "oracle_all_identities_s": oracle_wall,
            "policy_all_seed_identities_s": policy_score_wall,
            "scope": "Python table scoring only; excludes policy inference and is not SPICE speedup",
        },
        "claim_boundary": "Exposed midpoint library-policy evidence; not the physical-bias circuit or a new held-out set",
        "wall_s": time.perf_counter() - started,
    }
    (out / "summary.json").write_text(
        json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    payloads = [path for path in out.iterdir() if path.is_file()]
    (out / "sha256.json").write_text(
        json.dumps({path.name: sha(path) for path in payloads}, indent=2),
        encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    result = run(parser.parse_args().out)
    print(json.dumps(result["aggregate"], indent=2))
