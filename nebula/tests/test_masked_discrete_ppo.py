"""Algorithm gates for Entry 88's masked categorical PPO."""

from __future__ import annotations

import numpy as np
import torch

from nebula.rl.masked_discrete_ppo import (
    DiscretePPOConfig,
    MaskedActorCritic,
    deterministic_action,
    state_dict_sha256,
    train,
)


class _TinyMaskedEnv:
    observation_dim = 2
    action_dim = 3

    def __init__(self):
        self.n = 0
        self.actions = []

    def reset(self):
        self.n = 0
        return np.asarray([1.0, 0.0], dtype=np.float32)

    def action_mask(self):
        return np.asarray([self.n == 0, self.n == 1, False], dtype=np.bool_)

    def step(self, action):
        assert self.action_mask()[int(action)]
        self.actions.append(int(action))
        self.n += 1
        done = self.n >= 2
        return np.asarray([1.0, self.n / 2], dtype=np.float32), \
            1.0, done, False, {}


def _cfg(**kw):
    values = dict(seed=19, total_steps=128, rollout_steps=32, epochs=2,
                  n_minibatches=4, hidden=(16, 16))
    values.update(kw)
    return DiscretePPOConfig(**values)


def test_distribution_assigns_zero_probability_to_masked_actions():
    net = MaskedActorCritic(2, 3, (8,))
    obs = torch.zeros(2, 2)
    mask = torch.tensor([[True, False, True], [False, True, False]])
    dist = net.distribution(obs, mask)
    assert torch.equal(dist.probs == 0.0, ~mask)
    assert torch.allclose(dist.probs.sum(-1), torch.ones(2))


def test_deterministic_action_is_masked_argmax():
    net = MaskedActorCritic(2, 3, (8,))
    with torch.no_grad():
        for parameter in net.parameters():
            parameter.zero_()
        net.pi[-1].bias[:] = torch.tensor([10.0, 2.0, 1.0])
    action = deterministic_action(
        net, np.zeros(2, dtype=np.float32),
        np.asarray([False, True, True]))
    assert action == 1 and isinstance(action, int)


def test_empty_or_wrong_shape_mask_fails_loudly():
    net = MaskedActorCritic(2, 3, (8,))
    obs = torch.zeros(1, 2)
    for mask in (torch.zeros(1, 3, dtype=torch.bool),
                 torch.ones(1, 2, dtype=torch.bool)):
        try:
            net.distribution(obs, mask)
        except ValueError:
            pass
        else:  # pragma: no cover - explicit fail-capable branch
            raise AssertionError("invalid action mask was accepted")


def test_training_uses_only_available_actions_and_is_reproducible():
    initial = MaskedActorCritic(2, 3, (16, 16))
    torch.manual_seed(19)
    initial = MaskedActorCritic(2, 3, (16, 16))
    before = state_dict_sha256(initial.state_dict())
    env1 = _TinyMaskedEnv()
    env2 = _TinyMaskedEnv()
    net1, stats1 = train(env1, _cfg())
    net2, stats2 = train(env2, _cfg())
    assert stats1.steps_completed == stats2.steps_completed == 128
    assert before != state_dict_sha256(net1.state_dict())
    assert state_dict_sha256(net1.state_dict()) == state_dict_sha256(
        net2.state_dict())
    assert env1.actions == env2.actions
    assert set(env1.actions) == {0, 1}
    assert np.isfinite(stats1.policy_loss).all()
    assert np.isfinite(stats1.value_loss).all()


def test_optimizer_defaults_remain_entry87_values():
    cfg = DiscretePPOConfig(seed=2026090400, total_steps=200_000)
    assert cfg.rollout_steps == 64 and cfg.epochs == 10
    assert cfg.n_minibatches == 4 and cfg.lr == 3e-4
    assert cfg.gamma == 0.99 and cfg.gae_lambda == 0.95
    assert cfg.clip_eps == 0.2 and cfg.vf_coef == 0.5
    assert cfg.ent_coef == 0.0 and cfg.max_grad_norm == 0.5
    assert cfg.hidden == (64, 64)
