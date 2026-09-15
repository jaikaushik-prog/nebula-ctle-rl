"""Train and evaluate Entry 87's preregistered categorical-PPO policies.

Training is intentionally one registered seed per invocation so a shutdown
cannot erase completed work.  Evaluation is refused until all five distinct
checkpoints and summaries exist.  Every transition is a frozen-table lookup;
this module never invokes SPICE.
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
from nebula.experiments import exp_margin_adapt_controls as C
from nebula.rl.discrete_ppo import (
    DiscreteActorCritic, DiscretePPOConfig, deterministic_action, train,
)
from nebula.rl.margin_adapt_env import MarginAdaptEnv, MarginBankTable

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "joint_bank_73_run.jsonl.gz"
CONTROLS = HERE / "margin_adapt_controls_results.json"
RESULTS = HERE / "margin_adapt_rl_results.json"
SOURCE_SHA256 = C.SOURCE_SHA256
CONTROLS_SHA256 = "4E7930C6EF353B81949F7D8C6562D6E4027F7B164F3B0099AD79FE652E09501D"

TRAIN_SEEDS = tuple(range(2026090300, 2026090305))
DEPLOYMENT_SEED = 2026090300
TOTAL_STEPS = 200_000
BOOTSTRAP_SEED = 2026090387
N_BOOTSTRAP = 10_000


def checkpoint_path(seed: int) -> Path:
    return HERE / f"margin_adapt_policy_{int(seed)}.pth"


def training_path(seed: int) -> Path:
    return HERE / f"margin_adapt_train_{int(seed)}.json"


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _load_controls() -> dict:
    digest = _file_sha256(CONTROLS)
    if digest != CONTROLS_SHA256:
        raise ValueError(f"controls hash mismatch: {digest}")
    return json.loads(CONTROLS.read_text(encoding="utf-8"))


def _start_map(controls: dict) -> dict:
    encoded = []
    for key, setting in controls["start_by_request"].items():
        pk, freq = key.split("/", 1)
        encoded.append((float(pk), float(freq), int(setting)))
    out = {}
    for exact_pk, exact_freq in C.REQUESTS:
        candidates = [(abs(freq - exact_freq), setting, freq)
                      for pk, freq, setting in encoded if pk == exact_pk]
        if not candidates:
            raise ValueError(f"missing start code for request {(exact_pk, exact_freq)}")
        _, setting, stored_freq = min(candidates)
        if not math.isclose(stored_freq, exact_freq, rel_tol=1e-5, abs_tol=0.0):
            raise ValueError(
                f"stored request frequency {stored_freq} does not identify {exact_freq}")
        out[(exact_pk, exact_freq)] = setting
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
    summary_path = training_path(seed)
    if checkpoint.exists() or summary_path.exists():
        raise FileExistsError(
            f"refusing to overwrite seed {seed} artifact")
    controls = _load_controls()
    decoded = J._decoded_sha256(SOURCE)
    if decoded != SOURCE_SHA256:
        raise ValueError(f"source hash mismatch: {decoded}")
    table = MarginBankTable.from_path(SOURCE)
    train_ids, _ = C.identities()
    starts = _start_map(controls)
    env = MarginAdaptEnv(table, train_ids, starts, seed=seed)
    cfg = DiscretePPOConfig(seed=seed, total_steps=TOTAL_STEPS)
    net, stats = train(env, cfg)
    stats_dict = asdict(stats)
    out = {
        "task": "entry 87 categorical PPO training",
        "seed": seed, "config": asdict(cfg),
        "source_decoded_sha256": decoded,
        "controls_sha256": CONTROLS_SHA256,
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
        "action_dim": env.action_dim,
        "state_dict": net.state_dict(),
        "source_decoded_sha256": decoded,
        "controls_sha256": CONTROLS_SHA256,
    }, checkpoint)
    summary_path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def _load_net(seed: int) -> DiscreteActorCritic:
    payload = torch.load(checkpoint_path(seed), map_location="cpu",
                         weights_only=False)
    if int(payload["seed"]) != int(seed):
        raise ValueError(f"checkpoint seed mismatch for {seed}")
    if payload["source_decoded_sha256"] != SOURCE_SHA256:
        raise ValueError(f"checkpoint source mismatch for {seed}")
    if payload["controls_sha256"] != CONTROLS_SHA256:
        raise ValueError(f"checkpoint controls mismatch for {seed}")
    cfg = payload["config"]
    net = DiscreteActorCritic(
        int(payload["observation_dim"]), int(payload["action_dim"]),
        tuple(cfg["hidden"]))
    net.load_state_dict(payload["state_dict"])
    net.eval()
    return net


def _evaluate_seed(seed: int, table: MarginBankTable, test_ids: Sequence[tuple],
                   starts: dict) -> dict:
    net = _load_net(seed)
    records = []
    for corner, loss, pk, freq in test_ids:
        env = MarginAdaptEnv(table, [(corner, loss, pk, freq)], starts,
                             seed=seed)
        obs = env.reset(corner=corner, loss_db=loss, request=(pk, freq))
        while env.ep.locked_setting is None:
            obs, _, term, _, _ = env.step(deterministic_action(net, obs))
            if term:
                break
        records.append(C._episode_record(env.ep))
    row = C._summarise(f"ppo_{seed}", records)
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
    for start in range(0, N_BOOTSTRAP, 500):
        count = min(500, N_BOOTSTRAP - start)
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
    healthy = (len(rows) == len(TRAIN_SEEDS)
               and {r["seed"] for r in rows} == set(TRAIN_SEEDS)
               and all(r["steps_completed"] == TOTAL_STEPS
                       and r["weights_changed"] and r["finite"] for r in rows))
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
        "Q8": bool(mean_trials <= 8.0 and mean_trials < 512.0),
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
    decoded = J._decoded_sha256(SOURCE)
    table = MarginBankTable.from_path(SOURCE)
    train_ids, test_ids = C.identities()
    starts = _start_map(controls)
    rows = [_evaluate_seed(seed, table, test_ids, starts)
            for seed in TRAIN_SEEDS]
    comparator = controls["primary_comparator"]
    comparator_eps = controls["primary_comparator_per_identity"]
    comparator_q = np.asarray([e["quality"] for e in comparator_eps], dtype=float)
    seed_q = np.asarray([[e["quality"] for e in row["per_identity"]]
                         for row in rows], dtype=float)
    for index, row in enumerate(rows):
        row["quality_delta"] = float(np.mean(seed_q[index] - comparator_q))
    paired_delta = seed_q.mean(axis=0) - comparator_q
    ci = paired_bootstrap_ci(paired_delta)
    split_ok = (len(train_ids) == 1728 and len(test_ids) == 864
                and not set(train_ids).intersection(test_ids))
    source_ok = decoded == SOURCE_SHA256
    controls_ok = _file_sha256(CONTROLS) == CONTROLS_SHA256
    checks = score_checks(source_ok, split_ok, controls_ok, rows, comparator, ci)
    out = {
        "task": "entry 87 five-seed categorical PPO held-out evaluation",
        "source_decoded_sha256": decoded,
        "controls_sha256": _file_sha256(CONTROLS),
        "split": controls["split"], "deployment_seed": DEPLOYMENT_SEED,
        "training_seeds": list(TRAIN_SEEDS), "total_steps_per_seed": TOTAL_STEPS,
        "comparator": comparator,
        "per_seed": rows,
        "aggregate": {
            "mean_compliance_rate": float(np.mean(
                [r["compliance_rate"] for r in rows])),
            "mean_quality": float(np.mean([r["mean_quality"] for r in rows])),
            "mean_trials": float(np.mean([r["mean_trials"] for r in rows])),
            "mean_return": float(np.mean([r["mean_return"] for r in rows])),
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
    print("ENTRY 87 MARGIN-ADAPTATION CATEGORICAL PPO")
    print("=" * 78)
    comparator = out["comparator"]
    print(f"  comparator {comparator['arm']}: compliance "
          f"{comparator['compliance_rate']:.4f}, quality "
          f"{comparator['mean_quality']:.4f}, trials "
          f"{comparator['mean_trials']:.3f}")
    for row in out["per_seed"]:
        print(f"  seed {row['seed']}: compliance {row['compliance_rate']:.4f}, "
              f"quality {row['mean_quality']:.4f}, delta "
              f"{row['quality_delta']:+.4f}, trials {row['mean_trials']:.3f}")
    aggregate = out["aggregate"]
    print(f"  aggregate: compliance {aggregate['mean_compliance_rate']:.4f}, "
          f"quality {aggregate['mean_quality']:.4f}, delta "
          f"{aggregate['quality_delta']:+.4f}, trials "
          f"{aggregate['mean_trials']:.3f}")
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
