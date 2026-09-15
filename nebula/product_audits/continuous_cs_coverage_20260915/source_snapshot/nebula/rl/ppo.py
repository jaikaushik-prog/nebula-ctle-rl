"""
rl/ppo.py — a minimal PPO. Written to be READ, not to be fast.

WHY IT IS WRITTEN HERE AND NOT IMPORTED
----------------------------------------
`stable_baselines3` and `gymnasium` are **not installed** in this environment
(checked 2026-08-07; `torch` 2.9.1+cpu is). CLAUDEwa.md §4.2 says to port the
plumbing from `ams_rl_ppo` rather than treat it as a source of truth, and the
plumbing is 150 lines. A missing package must not block a smoke run whose
entire purpose is to find integration bugs in three layers below this one.

**NOTHING HERE IS TUNED.** §6 is explicit: *"Do not tune hyperparameters. Do
not chase reward."* The values below are the PPO paper's defaults (Schulman et
al. 2017) and SB3's defaults where the two differ, written down so that a
later change is visible as a change:

    clip_eps      0.2      PPO paper
    gamma         0.99     PPO paper
    gae_lambda    0.95     PPO paper
    lr            3e-4     SB3 default
    epochs        10       PPO paper
    minibatches   4        SB3 default (n_steps / batch_size = 64 / 16)
    vf_coef       0.5      PPO paper
    ent_coef      0.0      SB3 default
    max_grad_norm 0.5      SB3 default
    hidden        (64, 64) SB3 default MlpPolicy

If the reward curve is flat, that is the expected outcome at 500 steps and it
is reported as such. It is NOT a reason to touch any number above.

THE ONE NON-DEFAULT CHOICE, AND IT IS NOT A TUNING KNOB
-------------------------------------------------------
The policy's mean head is `tanh`-squashed, so actions are in [-1, 1] before
the env scales them by `MAX_STEP`. The alternative — an unbounded Gaussian
that the env clips — makes the log-probability of every clipped action wrong,
which biases the gradient in exactly the region the policy spends its early
training in. This is a correctness fix, not a performance one.

SEEDING
-------
HANDOFF G3: never `np.random.seed()`. The seed arrives through `PPOConfig` and
is threaded into `torch.manual_seed` and the env's own
`numpy.random.default_rng`. One seed, one place, stated in the run header.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

import numpy as np
import torch
import torch.nn as nn


@dataclass
class PPOConfig:
    """Every hyperparameter, with its origin. See the module docstring."""

    seed: int
    total_steps: int = 500
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
    hidden: tuple = (64, 64)
    #: Initial policy standard deviation, in the tanh-squashed action space.
    #: SB3's `log_std_init` default is 0.0 (std = 1.0), which with a tanh mean
    #: makes the first rollouts almost uniform over [-1, 1]. Kept.
    log_std_init: float = 0.0


class ActorCritic(nn.Module):
    """Two-headed MLP. Separate trunks, as in SB3's default MlpPolicy."""

    def __init__(self, obs_dim: int, act_dim: int, hidden: Sequence[int],
                 log_std_init: float):
        super().__init__()

        def _trunk(out_dim: int) -> nn.Sequential:
            layers: list = []
            last = obs_dim
            for h in hidden:
                layers += [nn.Linear(last, h), nn.Tanh()]
                last = h
            layers += [nn.Linear(last, out_dim)]
            return nn.Sequential(*layers)

        self.pi = _trunk(act_dim)
        self.vf = _trunk(1)
        self.log_std = nn.Parameter(torch.full((act_dim,), float(log_std_init)))

    def distribution(self, obs: torch.Tensor) -> torch.distributions.Normal:
        # tanh on the MEAN, not on the sample: the sample stays Gaussian so the
        # log-probability is exact, while the mean cannot run away to a region
        # the env would clip. See the module docstring.
        mean = torch.tanh(self.pi(obs))
        return torch.distributions.Normal(mean, self.log_std.exp())

    def value(self, obs: torch.Tensor) -> torch.Tensor:
        return self.vf(obs).squeeze(-1)


@dataclass
class RolloutStats:
    """What a run reports. Enough to plot the §6g curve and nothing more."""

    step: list = field(default_factory=list)
    episode_return: list = field(default_factory=list)
    episode_length: list = field(default_factory=list)
    episode_end_step: list = field(default_factory=list)
    policy_loss: list = field(default_factory=list)
    value_loss: list = field(default_factory=list)
    entropy: list = field(default_factory=list)
    update_seconds: list = field(default_factory=list)
    env_seconds: float = 0.0
    policy_seconds: float = 0.0


def train(
    env,
    cfg: PPOConfig,
    on_episode: Optional[Callable[[int, float, int], None]] = None,
) -> tuple[ActorCritic, RolloutStats]:
    """Run `cfg.total_steps` environment steps of PPO. Returns (policy, stats).

    `total_steps` counts ENVIRONMENT steps, i.e. SPICE-evaluated edits — not
    gradient steps and not episodes. That is the unit §6a specifies ("500 PPO
    steps") and the unit §6i's cost accounting divides by.
    """
    import time

    torch.manual_seed(cfg.seed)
    obs_dim, act_dim = env.observation_dim, env.action_dim
    net = ActorCritic(obs_dim, act_dim, cfg.hidden, cfg.log_std_init)
    opt = torch.optim.Adam(net.parameters(), lr=cfg.lr)
    stats = RolloutStats()

    t_env = time.perf_counter()
    obs, _ = env.reset()
    stats.env_seconds += time.perf_counter() - t_env

    ep_return, ep_len, n_done = 0.0, 0, 0
    steps_done = 0

    while steps_done < cfg.total_steps:
        n = min(cfg.rollout_steps, cfg.total_steps - steps_done)
        buf_obs = np.zeros((n, obs_dim), dtype=np.float32)
        buf_act = np.zeros((n, act_dim), dtype=np.float32)
        buf_logp = np.zeros(n, dtype=np.float32)
        buf_val = np.zeros(n, dtype=np.float32)
        buf_rew = np.zeros(n, dtype=np.float32)
        # `terminated` and `truncated` are kept SEPARATE all the way through.
        # A truncated episode is bootstrapped through; a terminated one is not.
        # Conflating them credits an invalid circuit (§6d terminates on one)
        # with the value of whatever the policy would have done next.
        buf_term = np.zeros(n, dtype=np.float32)
        buf_trunc = np.zeros(n, dtype=np.float32)
        buf_last_val = np.zeros(n, dtype=np.float32)

        for i in range(n):
            t0 = time.perf_counter()
            with torch.no_grad():
                o = torch.as_tensor(obs, dtype=torch.float32).unsqueeze(0)
                dist = net.distribution(o)
                a = dist.sample()
                buf_logp[i] = dist.log_prob(a).sum(-1).item()
                buf_val[i] = net.value(o).item()
            stats.policy_seconds += time.perf_counter() - t0

            act = a.squeeze(0).numpy()
            buf_obs[i], buf_act[i] = obs, act

            t0 = time.perf_counter()
            obs2, rew, terminated, truncated, _ = env.step(act)
            stats.env_seconds += time.perf_counter() - t0

            buf_rew[i] = rew
            buf_term[i], buf_trunc[i] = float(terminated), float(truncated)
            ep_return += float(rew)
            ep_len += 1

            if truncated:
                # Bootstrap value of the state the horizon cut off.
                t0 = time.perf_counter()
                with torch.no_grad():
                    buf_last_val[i] = net.value(
                        torch.as_tensor(obs2, dtype=torch.float32).unsqueeze(0)).item()
                stats.policy_seconds += time.perf_counter() - t0

            if terminated or truncated:
                stats.episode_return.append(ep_return)
                stats.episode_length.append(ep_len)
                stats.episode_end_step.append(steps_done + i + 1)
                if on_episode is not None:
                    on_episode(n_done, ep_return, ep_len)
                n_done += 1
                ep_return, ep_len = 0.0, 0
                t0 = time.perf_counter()
                obs2, _ = env.reset()
                stats.env_seconds += time.perf_counter() - t0
            obs = obs2

        steps_done += n

        # ---- GAE(lambda) -----------------------------------------------------
        t0 = time.perf_counter()
        with torch.no_grad():
            last_v = net.value(
                torch.as_tensor(obs, dtype=torch.float32).unsqueeze(0)).item()
        adv = np.zeros(n, dtype=np.float32)
        gae = 0.0
        for t in reversed(range(n)):
            done = buf_term[t] or buf_trunc[t]
            if buf_trunc[t]:
                next_v = buf_last_val[t]      # bootstrap through a cut horizon
            elif buf_term[t]:
                next_v = 0.0                  # never bootstrap through a failure
            else:
                next_v = buf_val[t + 1] if t + 1 < n else last_v
            delta = buf_rew[t] + cfg.gamma * next_v - buf_val[t]
            gae = delta + cfg.gamma * cfg.gae_lambda * (0.0 if done else gae)
            adv[t] = gae
        ret = adv + buf_val

        # ---- the clipped surrogate ------------------------------------------
        t_obs = torch.as_tensor(buf_obs)
        t_act = torch.as_tensor(buf_act)
        t_logp = torch.as_tensor(buf_logp)
        t_adv = torch.as_tensor(adv)
        t_ret = torch.as_tensor(ret)
        if t_adv.numel() > 1:
            t_adv = (t_adv - t_adv.mean()) / (t_adv.std() + 1e-8)

        mb = max(1, n // cfg.n_minibatches)
        idx = np.arange(n)
        rng = np.random.default_rng(cfg.seed + steps_done)
        pl = vl = ent = 0.0
        n_mb = 0
        for _ in range(cfg.epochs):
            rng.shuffle(idx)
            for s in range(0, n, mb):
                j = idx[s:s + mb]
                if len(j) == 0:
                    continue
                dist = net.distribution(t_obs[j])
                logp = dist.log_prob(t_act[j]).sum(-1)
                ratio = (logp - t_logp[j]).exp()
                a1 = ratio * t_adv[j]
                a2 = torch.clamp(ratio, 1 - cfg.clip_eps, 1 + cfg.clip_eps) * t_adv[j]
                loss_pi = -torch.min(a1, a2).mean()
                loss_v = ((net.value(t_obs[j]) - t_ret[j]) ** 2).mean()
                entropy = dist.entropy().sum(-1).mean()
                loss = loss_pi + cfg.vf_coef * loss_v - cfg.ent_coef * entropy
                opt.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(net.parameters(), cfg.max_grad_norm)
                opt.step()
                pl += loss_pi.item(); vl += loss_v.item(); ent += entropy.item()
                n_mb += 1
        stats.step.append(steps_done)
        stats.policy_loss.append(pl / max(n_mb, 1))
        stats.value_loss.append(vl / max(n_mb, 1))
        stats.entropy.append(ent / max(n_mb, 1))
        stats.update_seconds.append(time.perf_counter() - t0)
        stats.policy_seconds += time.perf_counter() - t0

    return net, stats


__all__: Sequence[str] = ("PPOConfig", "ActorCritic", "RolloutStats", "train")
