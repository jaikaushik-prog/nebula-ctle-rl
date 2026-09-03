"""Minimal categorical PPO for Entry 87's seven-action controller.

The historical :mod:`nebula.rl.ppo` has a Gaussian continuous actor and remains
unchanged for reproducibility.  This module changes only the distribution;
its optimisation defaults are the same preregistered PPO-paper values.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np
import torch
import torch.nn as nn


@dataclass(frozen=True)
class DiscretePPOConfig:
    seed: int
    total_steps: int = 200_000
    rollout_steps: int = 64
    epochs: int = 10
    n_minibatches: int = 4
    lr: float = 3e-4
    gamma: float = 0.99
    gae_lambda: float = 0.95
    clip_eps: float = 0.2
    vf_coef: float = 0.5
    ent_coef: float = 0.0
    max_grad_norm: float = 0.5
    hidden: tuple[int, ...] = (64, 64)


class DiscreteActorCritic(nn.Module):
    """Separate categorical-policy and scalar-value tanh trunks."""

    def __init__(self, obs_dim: int, act_dim: int, hidden: Sequence[int]):
        super().__init__()

        def trunk(out_dim: int) -> nn.Sequential:
            layers: list[nn.Module] = []
            previous = int(obs_dim)
            for width in hidden:
                layers.extend((nn.Linear(previous, int(width)), nn.Tanh()))
                previous = int(width)
            layers.append(nn.Linear(previous, int(out_dim)))
            return nn.Sequential(*layers)

        self.pi = trunk(act_dim)
        self.vf = trunk(1)

    def distribution(self, obs: torch.Tensor) -> torch.distributions.Categorical:
        return torch.distributions.Categorical(logits=self.pi(obs))

    def value(self, obs: torch.Tensor) -> torch.Tensor:
        return self.vf(obs).squeeze(-1)


@dataclass
class DiscretePPOStats:
    steps_completed: int = 0
    episode_return: list[float] = field(default_factory=list)
    episode_length: list[int] = field(default_factory=list)
    policy_loss: list[float] = field(default_factory=list)
    value_loss: list[float] = field(default_factory=list)
    entropy: list[float] = field(default_factory=list)
    update_seconds: list[float] = field(default_factory=list)
    wall_clock_s: float = 0.0
    initial_weights_sha256: str = ""
    final_weights_sha256: str = ""


def state_dict_sha256(state_dict: dict) -> str:
    """Stable tensor-content hash, independent of torch serialization."""
    digest = hashlib.sha256()
    for name in sorted(state_dict):
        value = state_dict[name].detach().cpu().contiguous()
        digest.update(name.encode("utf-8"))
        digest.update(str(value.dtype).encode("ascii"))
        digest.update(str(tuple(value.shape)).encode("ascii"))
        digest.update(value.numpy().tobytes())
    return digest.hexdigest().upper()


def deterministic_action(net: DiscreteActorCritic, obs: np.ndarray) -> int:
    with torch.no_grad():
        tensor = torch.as_tensor(obs, dtype=torch.float32).unsqueeze(0)
        return int(torch.argmax(net.pi(tensor), dim=-1).item())


def train(env, cfg: DiscretePPOConfig) -> tuple[DiscreteActorCritic,
                                                DiscretePPOStats]:
    if cfg.total_steps <= 0 or cfg.rollout_steps <= 0:
        raise ValueError("step counts must be positive")
    if cfg.total_steps % cfg.rollout_steps:
        raise ValueError("total_steps must be divisible by rollout_steps")
    if cfg.rollout_steps % cfg.n_minibatches:
        raise ValueError("rollout_steps must be divisible by n_minibatches")

    torch.manual_seed(int(cfg.seed))
    net = DiscreteActorCritic(env.observation_dim, env.action_dim, cfg.hidden)
    optimiser = torch.optim.Adam(net.parameters(), lr=cfg.lr)
    stats = DiscretePPOStats(
        initial_weights_sha256=state_dict_sha256(net.state_dict()))
    started = time.perf_counter()
    obs = env.reset()
    episode_return = 0.0
    episode_length = 0

    while stats.steps_completed < cfg.total_steps:
        observations = []
        actions = []
        rewards = []
        dones = []
        values = []
        log_probs = []

        for _ in range(cfg.rollout_steps):
            tensor = torch.as_tensor(obs, dtype=torch.float32).unsqueeze(0)
            with torch.no_grad():
                dist = net.distribution(tensor)
                action = dist.sample()
                value = net.value(tensor)
                log_prob = dist.log_prob(action)
            next_obs, reward, terminated, truncated, _ = env.step(
                int(action.item()))
            done = bool(terminated or truncated)
            observations.append(np.asarray(obs, dtype=np.float32))
            actions.append(int(action.item()))
            rewards.append(float(reward))
            dones.append(done)
            values.append(float(value.item()))
            log_probs.append(float(log_prob.item()))
            stats.steps_completed += 1
            episode_return += float(reward)
            episode_length += 1
            obs = next_obs
            if done:
                stats.episode_return.append(episode_return)
                stats.episode_length.append(episode_length)
                episode_return = 0.0
                episode_length = 0
                obs = env.reset()

        with torch.no_grad():
            last_value = float(net.value(torch.as_tensor(
                obs, dtype=torch.float32).unsqueeze(0)).item())
        advantages = np.zeros(cfg.rollout_steps, dtype=np.float32)
        gae = 0.0
        for index in reversed(range(cfg.rollout_steps)):
            nonterminal = 0.0 if dones[index] else 1.0
            next_value = (last_value if index == cfg.rollout_steps - 1
                          else values[index + 1])
            delta = (rewards[index] + cfg.gamma * next_value * nonterminal
                     - values[index])
            gae = delta + cfg.gamma * cfg.gae_lambda * nonterminal * gae
            advantages[index] = gae
        returns = advantages + np.asarray(values, dtype=np.float32)

        t_obs = torch.as_tensor(np.asarray(observations), dtype=torch.float32)
        t_actions = torch.as_tensor(actions, dtype=torch.int64)
        t_old_logp = torch.as_tensor(log_probs, dtype=torch.float32)
        t_returns = torch.as_tensor(returns, dtype=torch.float32)
        t_adv = torch.as_tensor(advantages, dtype=torch.float32)
        t_adv = (t_adv - t_adv.mean()) / (t_adv.std(unbiased=False) + 1e-8)

        update_started = time.perf_counter()
        policy_total = value_total = entropy_total = 0.0
        batches = 0
        batch_size = cfg.rollout_steps // cfg.n_minibatches
        for _ in range(cfg.epochs):
            permutation = torch.randperm(cfg.rollout_steps)
            for start in range(0, cfg.rollout_steps, batch_size):
                index = permutation[start:start + batch_size]
                dist = net.distribution(t_obs[index])
                new_logp = dist.log_prob(t_actions[index])
                ratio = torch.exp(new_logp - t_old_logp[index])
                unclipped = ratio * t_adv[index]
                clipped = torch.clamp(
                    ratio, 1.0 - cfg.clip_eps, 1.0 + cfg.clip_eps) * t_adv[index]
                policy_loss = -torch.min(unclipped, clipped).mean()
                value_loss = ((net.value(t_obs[index]) - t_returns[index]) ** 2).mean()
                entropy = dist.entropy().mean()
                loss = (policy_loss + cfg.vf_coef * value_loss
                        - cfg.ent_coef * entropy)
                optimiser.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(net.parameters(), cfg.max_grad_norm)
                optimiser.step()
                policy_total += float(policy_loss.item())
                value_total += float(value_loss.item())
                entropy_total += float(entropy.item())
                batches += 1
        stats.policy_loss.append(policy_total / batches)
        stats.value_loss.append(value_total / batches)
        stats.entropy.append(entropy_total / batches)
        stats.update_seconds.append(time.perf_counter() - update_started)

    stats.wall_clock_s = time.perf_counter() - started
    stats.final_weights_sha256 = state_dict_sha256(net.state_dict())
    return net, stats


__all__ = (
    "DiscretePPOConfig", "DiscreteActorCritic", "DiscretePPOStats",
    "state_dict_sha256", "deterministic_action", "train")
