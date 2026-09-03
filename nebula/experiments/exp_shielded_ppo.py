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
DEVELOPMENT_RESULTS = HERE / "shielded_policy_development_results.json"
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


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-seed", type=int, required=True)
    args = parser.parse_args(argv)
    out = train_seed(args.train_seed)
    print(f"seed {out['seed']} complete: BC {out['bc_config']['epochs']} "
          f"epochs, PPO {out['steps_completed']} steps, "
          f"accuracy {out['bc_stats']['support_accuracy']:.4f}, "
          f"finite={out['finite']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
