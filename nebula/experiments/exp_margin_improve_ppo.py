"""Train and evaluate Entry 88's preregistered masked-PPO policies.

Each command trains one durable seed.  FINAL TEST cannot be scored until all
five checkpoints and summaries exist and validate.  Every transition is a
frozen-table lookup and this module never invokes SPICE.
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
from nebula.experiments import exp_margin_improve_controls as C
from nebula.rl.margin_adapt_env import MarginBankTable
from nebula.rl.margin_improve_env import MarginImproveEnv
from nebula.rl.masked_discrete_ppo import (
    DiscretePPOConfig, MaskedActorCritic, deterministic_action, train,
)

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "joint_bank_73_run.jsonl.gz"
CONTROLS = HERE / "margin_improve_controls_results.json"
RESULTS = HERE / "margin_improve_rl_results.json"
SOURCE_SHA256 = C.SOURCE_SHA256
CONTROLS_SHA256 = "7EE4650145E1603E1A90282A0F9B69C33E8070C8A4E52AF73156F3B8AC1497B6"

TRAIN_SEEDS = tuple(range(2026090400, 2026090405))
DEPLOYMENT_SEED = 2026090400
TOTAL_STEPS = 200_000
BOOTSTRAP_SEED = 2026090488
N_BOOTSTRAP = 10_000


def checkpoint_path(seed: int) -> Path:
    return HERE / f"margin_improve_policy_{int(seed)}.pth"


def training_path(seed: int) -> Path:
    return HERE / f"margin_improve_train_{int(seed)}.json"


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _load_controls() -> dict:
    digest = _file_sha256(CONTROLS)
    if digest != CONTROLS_SHA256:
        raise ValueError(f"controls hash mismatch: {digest}")
    controls = json.loads(CONTROLS.read_text(encoding="utf-8"))
    if controls["split"]["final_test_status"] != "DEFINED_NOT_SCORED":
        raise ValueError("controls artifact did not preserve unopened FINAL TEST")
    return controls


def _start_map(controls: dict) -> dict:
    rows = controls["start_by_request"]
    out = {(float(row["target_peaking_db"]),
            float(row["target_f_peak_hz"])): int(row["setting"])
           for row in rows}
    if len(out) != len(rows) or set(out) != set(C.REQUESTS):
        raise ValueError("controls start map does not match exact requests")
    return out


def _finite_stats(stats: dict) -> bool:
    fields = ("policy_loss", "value_loss", "entropy", "update_seconds")
    return all(math.isfinite(float(value)) for name in fields
               for value in stats[name])


def train_seed(seed: int) -> dict:
    seed = int(seed)
    if seed not in TRAIN_SEEDS:
        raise ValueError(f"unregistered seed {seed}")
    checkpoint = checkpoint_path(seed)
    summary = training_path(seed)
    if checkpoint.exists() or summary.exists():
        raise FileExistsError(f"refusing to overwrite seed {seed} artifact")
    controls = _load_controls()
    decoded = J._decoded_sha256(SOURCE)
    if decoded != SOURCE_SHA256:
        raise ValueError(f"source hash mismatch: {decoded}")
    table = MarginBankTable.from_path(SOURCE)
    train_ids, final_ids = C.identities()
    if C.identities_sha256(train_ids) != controls["split"][
            "train_identities_sha256"]:
        raise ValueError("TRAIN identity hash mismatch")
    starts = _start_map(controls)
    env = MarginImproveEnv(table, train_ids, starts, seed=seed)
    cfg = DiscretePPOConfig(seed=seed, total_steps=TOTAL_STEPS)
    net, stats = train(env, cfg)
    stats_dict = asdict(stats)
    out = {
        "task": "entry 88 masked categorical PPO training",
        "seed": seed, "config": asdict(cfg),
        "source_decoded_sha256": decoded,
        "controls_sha256": CONTROLS_SHA256,
        "train_identities_sha256": C.identities_sha256(train_ids),
        "final_test_identities_sha256": C.identities_sha256(final_ids),
        "final_test_status": "NOT_EVALUATED_DURING_TRAINING",
        "steps_completed": stats.steps_completed,
        "initial_weights_sha256": stats.initial_weights_sha256,
        "final_weights_sha256": stats.final_weights_sha256,
        "weights_changed": (stats.initial_weights_sha256 !=
                            stats.final_weights_sha256),
        "finite": _finite_stats(stats_dict),
        "stats": stats_dict, "simulations_run": 0,
    }
    torch.save({
        "seed": seed, "config": asdict(cfg),
        "observation_dim": env.observation_dim,
        "action_dim": env.action_dim, "state_dict": net.state_dict(),
        "source_decoded_sha256": decoded,
        "controls_sha256": CONTROLS_SHA256,
        "train_identities_sha256": C.identities_sha256(train_ids),
        "final_test_identities_sha256": C.identities_sha256(final_ids),
    }, checkpoint)
    summary.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def _load_net(seed: int, controls: dict) -> MaskedActorCritic:
    payload = torch.load(checkpoint_path(seed), map_location="cpu",
                         weights_only=False)
    expected = {
        "seed": int(seed), "source_decoded_sha256": SOURCE_SHA256,
        "controls_sha256": CONTROLS_SHA256,
        "train_identities_sha256": controls["split"]["train_identities_sha256"],
        "final_test_identities_sha256": controls["split"][
            "final_test_identities_sha256"],
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise ValueError(f"checkpoint {key} mismatch for seed {seed}")
    cfg = payload["config"]
    net = MaskedActorCritic(
        int(payload["observation_dim"]), int(payload["action_dim"]),
        tuple(cfg["hidden"]))
    net.load_state_dict(payload["state_dict"])
    net.eval()
    return net


def _evaluate_seed(seed: int, net: MaskedActorCritic,
                   table: MarginBankTable, final_ids: Sequence[tuple],
                   starts: dict) -> dict:
    records = []
    for corner, loss, pk, freq in final_ids:
        env = MarginImproveEnv(table, [(corner, loss, pk, freq)], starts,
                               seed=seed)
        obs = env.reset(corner=corner, loss_db=loss, request=(pk, freq))
        while env.ep.locked_setting is None:
            action = deterministic_action(net, obs, env.action_mask())
            obs, _, term, _, _ = env.step(action)
            if term:
                break
        records.append(C._episode_record(env.ep))
    row = C._summarise(f"masked_ppo_{seed}", records)
    training = json.loads(training_path(seed).read_text(encoding="utf-8"))
    row.update({
        "seed": seed, "steps_completed": training["steps_completed"],
        "weights_changed": training["weights_changed"],
        "finite": training["finite"],
        "checkpoint": checkpoint_path(seed).name,
        "checkpoint_sha256": _file_sha256(checkpoint_path(seed)),
        "training_summary": training_path(seed).name,
        "training_summary_sha256": _file_sha256(training_path(seed)),
    })
    return row


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
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(lo), float(hi)


def score_checks(source_ok: bool, split_ok: bool, controls_ok: bool,
                 per_seed: Sequence[dict], comparator: dict,
                 bootstrap_ci: tuple[float, float],
                 environment_ok: bool = True) -> dict:
    rows = list(per_seed)
    deploy = next((r for r in rows if r["seed"] == DEPLOYMENT_SEED), None)
    required = {
        "mean_return", "n_false_locks", "code_change_rate",
        "compliance_rate", "mean_quality", "mean_trials",
    }
    healthy = (len(rows) == len(TRAIN_SEEDS)
               and {r["seed"] for r in rows} == set(TRAIN_SEEDS)
               and len({r["checkpoint_sha256"] for r in rows}) == len(rows)
               and all(r["steps_completed"] == TOTAL_STEPS
                       and r["weights_changed"] and r["finite"] for r in rows))
    reporting = all(required.issubset(row) for row in rows)
    mean_compliance = float(np.mean([r["compliance_rate"] for r in rows]))
    mean_quality = float(np.mean([r["mean_quality"] for r in rows]))
    mean_trials = float(np.mean([r["mean_trials"] for r in rows]))
    safety_floor = float(comparator["compliance_rate"]) - 0.01
    quality_delta = mean_quality - float(comparator["mean_quality"])
    return {
        "Q1": bool(source_ok and split_ok),
        "Q2": bool(environment_ok),
        "Q3": bool(controls_ok),
        "Q4": bool(healthy),
        "Q5": bool(mean_compliance >= safety_floor and deploy is not None
                   and deploy["compliance_rate"] >= safety_floor),
        "Q6": bool(quality_delta >= 0.02 and bootstrap_ci[0] > 0.0),
        "Q7": bool(sum(r["quality_delta"] > 0.0 for r in rows) >= 4
                   and deploy is not None and deploy["quality_delta"] > 0.0),
        "Q8": bool(reporting and mean_trials <= 8.0 and mean_trials < 512.0),
    }


def evaluate() -> dict:
    if RESULTS.exists():
        raise FileExistsError(f"refusing to overwrite {RESULTS.name}")
    missing = [path.name for seed in TRAIN_SEEDS
               for path in (checkpoint_path(seed), training_path(seed))
               if not path.exists()]
    if missing:
        raise FileNotFoundError(f"missing training artifacts: {missing}")

    controls = _load_controls()
    nets = {seed: _load_net(seed, controls) for seed in TRAIN_SEEDS}
    decoded = J._decoded_sha256(SOURCE)
    table = MarginBankTable.from_path(SOURCE)
    train_ids, final_ids = C.identities()
    starts = _start_map(controls)
    split_ok = (
        len(train_ids) == 2592 and len(final_ids) == 2448
        and not set(train_ids).intersection(final_ids)
        and len(set(train_ids).union(final_ids)) == 5040
        and C.identities_sha256(train_ids) == controls["split"][
            "train_identities_sha256"]
        and C.identities_sha256(final_ids) == controls["split"][
            "final_test_identities_sha256"])

    # This block is the single registered FINAL TEST exposure.  All policies
    # were loaded above before any final identity was scored.
    fixed = C.score_fixed(table, final_ids, starts)
    hill = C.score_arm(table, C.arm_hillclimb, final_ids, starts)
    random = C.score_random(table, final_ids, starts)
    exhaustive = C.score_exhaustive_visible(table, final_ids, starts)
    oracle = C.score_global_oracle(table, final_ids, starts)
    reachable = C.score_reachable_oracle(table, final_ids, starts)
    rows = [_evaluate_seed(seed, nets[seed], table, final_ids, starts)
            for seed in TRAIN_SEEDS]

    comparator_q = np.asarray(
        [e["quality"] for e in fixed["per_identity"]], dtype=float)
    seed_q = np.asarray([[e["quality"] for e in row["per_identity"]]
                         for row in rows], dtype=float)
    for index, row in enumerate(rows):
        row["quality_delta"] = float(np.mean(seed_q[index] - comparator_q))
    paired_delta = seed_q.mean(axis=0) - comparator_q
    ci = paired_bootstrap_ci(paired_delta)
    source_ok = decoded == SOURCE_SHA256
    controls_ok = (_file_sha256(CONTROLS) == CONTROLS_SHA256
                   and controls["split"]["final_test_status"] ==
                   "DEFINED_NOT_SCORED")
    checks = score_checks(source_ok, split_ok, controls_ok, rows, fixed, ci)
    final_controls = {
        "practical": [fixed, hill, random],
        "exhaustive_visible_eye": exhaustive,
        "global_hidden_oracle": oracle,
        "reachable_hidden_oracle": reachable,
    }
    out = {
        "task": "entry 88 five-seed masked PPO final evaluation",
        "source_decoded_sha256": decoded,
        "controls_sha256": _file_sha256(CONTROLS),
        "split": {**controls["split"],
                  "final_test_status": "EVALUATED_ONCE_AFTER_FIVE_POLICIES"},
        "deployment_seed": DEPLOYMENT_SEED,
        "training_seeds": list(TRAIN_SEEDS),
        "total_steps_per_seed": TOTAL_STEPS,
        "comparator": fixed, "final_controls": final_controls,
        "per_seed": rows,
        "aggregate": {
            "mean_compliance_rate": float(np.mean(
                [r["compliance_rate"] for r in rows])),
            "mean_quality": float(np.mean([r["mean_quality"] for r in rows])),
            "mean_trials": float(np.mean([r["mean_trials"] for r in rows])),
            "mean_return": float(np.mean([r["mean_return"] for r in rows])),
            "mean_code_change_rate": float(np.mean(
                [r["code_change_rate"] for r in rows])),
            "quality_delta": float(np.mean(paired_delta)),
            "paired_quality_delta_ci95": list(ci),
            "bootstrap_seed": BOOTSTRAP_SEED,
            "bootstrap_resamples": N_BOOTSTRAP,
        },
        "checks": checks, "passed": all(checks.values()),
        "simulations_run": 0,
    }
    RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def report(out: dict) -> None:
    print("=" * 78)
    print("ENTRY 88 IMPROVEMENT-REWARD MASKED PPO")
    print("=" * 78)
    comparator = out["comparator"]
    print(f"  comparator fixed: compliance {comparator['compliance_rate']:.4f}, "
          f"quality {comparator['mean_quality']:.4f}, trials "
          f"{comparator['mean_trials']:.3f}")
    for row in out["per_seed"]:
        print(f"  seed {row['seed']}: compliance {row['compliance_rate']:.4f}, "
              f"quality {row['mean_quality']:.4f}, delta "
              f"{row['quality_delta']:+.4f}, trials {row['mean_trials']:.3f}, "
              f"changed {row['code_change_rate']:.4f}")
    aggregate = out["aggregate"]
    print(f"  aggregate: compliance {aggregate['mean_compliance_rate']:.4f}, "
          f"quality {aggregate['mean_quality']:.4f}, delta "
          f"{aggregate['quality_delta']:+.4f}, trials "
          f"{aggregate['mean_trials']:.3f}, changed "
          f"{aggregate['mean_code_change_rate']:.4f}")
    print(f"  paired 95% CI: {aggregate['paired_quality_delta_ci95']}")
    for name, passed in out["checks"].items():
        print(f"  {name}: {'PASS' if passed else 'FAIL'}")
    print(f"  OVERALL: {'PASS' if out['passed'] else 'FAIL'}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--train-seed", type=int)
    mode.add_argument("--evaluate", action="store_true")
    mode.add_argument("--analyse", action="store_true")
    args = parser.parse_args(argv)
    if args.train_seed is not None:
        out = train_seed(args.train_seed)
        print(f"seed {out['seed']} complete: {out['steps_completed']} steps, "
              f"changed={out['weights_changed']}, finite={out['finite']}, "
              f"{out['stats']['wall_clock_s']:.2f} s")
    elif args.evaluate:
        report(evaluate())
    else:
        if not RESULTS.exists():
            raise SystemExit(f"missing {RESULTS.name}; train and evaluate first")
        report(json.loads(RESULTS.read_text(encoding="utf-8")))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
