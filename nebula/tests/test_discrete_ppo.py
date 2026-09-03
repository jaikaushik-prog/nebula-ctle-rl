"""Algorithm gates for Entry 87's categorical PPO."""

from __future__ import annotations

import numpy as np
import torch

from nebula.rl.discrete_ppo import (
    DiscreteActorCritic,
    DiscretePPOConfig,
    deterministic_action,
    state_dict_sha256,
    train,
)


class _TinyEnv:
    observation_dim = 2
    action_dim = 3

    def __init__(self):
        self.n = 0

    def reset(self):
        self.n = 0
        return np.asarray([1.0, 0.0], dtype=np.float32)

    def step(self, action):
        self.n += 1
        reward = 1.0 if int(action) == 2 else -1.0
        done = self.n >= 2
        return np.asarray([1.0, self.n / 2], dtype=np.float32), \
            reward, done, False, {}


def _cfg(**kw):
    base = dict(seed=17, total_steps=128, rollout_steps=32, epochs=2,
                n_minibatches=4, hidden=(16, 16))
    base.update(kw)
    return DiscretePPOConfig(**base)


def test_actor_is_categorical_and_has_separate_value_trunk():
    net = DiscreteActorCritic(2, 3, (8, 8))
    obs = torch.zeros(4, 2)
    dist = net.distribution(obs)
    assert isinstance(dist, torch.distributions.Categorical)
    assert dist.probs.shape == (4, 3)
    assert torch.allclose(dist.probs.sum(-1), torch.ones(4))
    assert net.pi is not net.vf


def test_deterministic_action_is_argmax_and_an_integer():
    net = DiscreteActorCritic(2, 3, (8,))
    with torch.no_grad():
        for p in net.parameters():
            p.zero_()
        net.pi[-1].bias[:] = torch.tensor([-1.0, 2.0, 0.0])
    action = deterministic_action(net, np.zeros(2, dtype=np.float32))
    assert action == 1 and isinstance(action, int)


def test_training_runs_exact_steps_changes_weights_and_is_reproducible():
    torch.manual_seed(17)
    initial = DiscreteActorCritic(2, 3, (16, 16))
    before = state_dict_sha256(initial.state_dict())
    net1, stats1 = train(_TinyEnv(), _cfg())
    net2, stats2 = train(_TinyEnv(), _cfg())
    assert stats1.steps_completed == 128
    assert stats1.steps_completed == stats2.steps_completed
    assert before != state_dict_sha256(net1.state_dict())
    assert state_dict_sha256(net1.state_dict()) == state_dict_sha256(
        net2.state_dict())
    assert np.isfinite(stats1.policy_loss).all()
    assert np.isfinite(stats1.value_loss).all()


def test_registered_defaults_match_entry87():
    cfg = DiscretePPOConfig(seed=2026090300, total_steps=200_000)
    assert cfg.rollout_steps == 64
    assert cfg.epochs == 10
    assert cfg.n_minibatches == 4
    assert cfg.lr == 3e-4
    assert cfg.gamma == 0.99 and cfg.gae_lambda == 0.95
    assert cfg.clip_eps == 0.2 and cfg.vf_coef == 0.5
    assert cfg.ent_coef == 0.0 and cfg.max_grad_norm == 0.5
    assert cfg.hidden == (64, 64)

