"""Actor-only oracle imitation for Entry 89's masked PPO warm start."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np
import torch

from nebula.rl.discrete_ppo import state_dict_sha256
from nebula.rl.masked_discrete_ppo import MaskedActorCritic
from nebula.rl.oracle_imitation import OracleSample


@dataclass(frozen=True)
class BCConfig:
    seed: int
    epochs: int = 50
    batch_size: int = 256
    lr: float = 3e-4


@dataclass
class BCStats:
    n_samples: int = 0
    epochs_completed: int = 0
    initial_actor_sha256: str = ""
    final_actor_sha256: str = ""
    initial_value_sha256: str = ""
    final_value_sha256: str = ""
    loss: list[float] = field(default_factory=list)
    support_accuracy: float = 0.0


def _arrays(samples: Sequence[OracleSample]):
    rows = list(samples)
    if not rows:
        raise ValueError("oracle imitation needs at least one sample")
    obs = np.asarray([row.observation for row in rows], dtype=np.float32)
    masks = np.asarray([row.mask for row in rows], dtype=np.bool_)
    targets = np.asarray([row.target_probs for row in rows], dtype=np.float32)
    if obs.ndim != 2 or masks.shape != targets.shape:
        raise ValueError("inconsistent oracle sample shapes")
    if masks.shape[0] != obs.shape[0]:
        raise ValueError("sample counts do not match")
    if not np.allclose(targets.sum(axis=1), 1.0):
        raise ValueError("each oracle target must sum to one")
    if np.any(targets < 0.0):
        raise ValueError("oracle target probabilities must be nonnegative")
    if np.any(targets[~masks] > 0.0):
        raise ValueError("oracle target assigns probability to a masked action")
    return obs, masks, targets


def pretrain_actor(net: MaskedActorCritic, samples: Sequence[OracleSample],
                   cfg: BCConfig) -> BCStats:
    if cfg.epochs <= 0 or cfg.batch_size <= 0 or cfg.lr <= 0.0:
        raise ValueError("BC epochs, batch size and learning rate must be positive")
    obs, masks, targets = _arrays(samples)
    if obs.shape[1] != net.pi[0].in_features:
        raise ValueError("BC observation width does not match actor")
    if targets.shape[1] != net.pi[-1].out_features:
        raise ValueError("BC action width does not match actor")
    torch.manual_seed(int(cfg.seed))
    t_obs = torch.as_tensor(obs, dtype=torch.float32)
    t_masks = torch.as_tensor(masks, dtype=torch.bool)
    t_targets = torch.as_tensor(targets, dtype=torch.float32)
    optimiser = torch.optim.Adam(net.pi.parameters(), lr=float(cfg.lr))
    stats = BCStats(
        n_samples=len(obs),
        initial_actor_sha256=state_dict_sha256(net.pi.state_dict()),
        initial_value_sha256=state_dict_sha256(net.vf.state_dict()))
    for _ in range(int(cfg.epochs)):
        permutation = torch.randperm(len(obs))
        total = 0.0
        batches = 0
        for start in range(0, len(obs), int(cfg.batch_size)):
            index = permutation[start:start + int(cfg.batch_size)]
            logits = net.pi(t_obs[index]).masked_fill(
                ~t_masks[index], -1e9)
            log_probs = torch.log_softmax(logits, dim=-1)
            loss = -(t_targets[index] * log_probs).sum(dim=-1).mean()
            optimiser.zero_grad()
            loss.backward()
            optimiser.step()
            value = float(loss.item())
            if not math.isfinite(value):
                raise FloatingPointError("non-finite BC loss")
            total += value
            batches += 1
        stats.loss.append(total / batches)
        stats.epochs_completed += 1
    with torch.no_grad():
        logits = net.pi(t_obs).masked_fill(~t_masks, -torch.inf)
        chosen = torch.argmax(logits, dim=-1)
        supported = t_targets.gather(1, chosen.unsqueeze(1)).squeeze(1) > 0.0
        stats.support_accuracy = float(supported.float().mean().item())
    stats.final_actor_sha256 = state_dict_sha256(net.pi.state_dict())
    stats.final_value_sha256 = state_dict_sha256(net.vf.state_dict())
    return stats


__all__ = ("BCConfig", "BCStats", "pretrain_actor")
