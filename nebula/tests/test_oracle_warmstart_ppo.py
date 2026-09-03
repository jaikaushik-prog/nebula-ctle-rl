"""Fail-capable gates for Entry 89 BC-warm-started masked PPO."""

from __future__ import annotations

import numpy as np
import pytest
import torch

from nebula.experiments import exp_shielded_ppo as P
from nebula.rl.discrete_ppo import DiscretePPOConfig, state_dict_sha256
from nebula.rl.masked_discrete_ppo import MaskedActorCritic, train
from nebula.rl.oracle_imitation import OracleSample
from nebula.rl.oracle_warmstart import BCConfig, pretrain_actor


def _samples() -> list[OracleSample]:
    rows = []
    for index in range(16):
        obs = np.asarray([index / 15.0, 1.0 - index / 15.0],
                         dtype=np.float32)
        mask = np.asarray([True, True, False], dtype=np.bool_)
        target = np.asarray([1.0, 0.0, 0.0] if index < 8 else
                            [0.0, 1.0, 0.0], dtype=np.float32)
        rows.append(OracleSample(obs, mask, target))
    return rows


def test_registered_training_contract_is_exact():
    assert P.TRAIN_SEEDS == tuple(range(2026090500, 2026090505))
    assert P.DEPLOYMENT_SEED == 2026090500
    assert P.BC_EPOCHS == 50 and P.BC_BATCH_SIZE == 256
    assert P.TOTAL_STEPS == 200_000
    assert P.FINAL_STATUS == "NOT_GENERATED_NOT_SCORED"


def test_bc_changes_only_actor_and_records_finite_epoch_losses():
    torch.manual_seed(4)
    net = MaskedActorCritic(2, 3, (8,))
    actor_before = state_dict_sha256(net.pi.state_dict())
    value_before = state_dict_sha256(net.vf.state_dict())
    stats = pretrain_actor(
        net, _samples(), BCConfig(seed=9, epochs=4, batch_size=8))
    assert stats.initial_actor_sha256 == actor_before
    assert stats.final_actor_sha256 != actor_before
    assert state_dict_sha256(net.vf.state_dict()) == value_before
    assert len(stats.loss) == 4
    assert all(np.isfinite(stats.loss))
    assert 0.0 <= stats.support_accuracy <= 1.0


def test_bc_rejects_targets_on_masked_actions():
    bad = _samples()
    bad[0] = OracleSample(
        bad[0].observation, bad[0].mask,
        np.asarray([0.0, 0.0, 1.0], dtype=np.float32))
    with pytest.raises(ValueError, match="masked action"):
        pretrain_actor(MaskedActorCritic(2, 3, (8,)), bad,
                       BCConfig(seed=1, epochs=1, batch_size=8))


class _TinyEnv:
    observation_dim = 2
    action_dim = 2

    def __init__(self):
        self.obs = np.zeros(2, dtype=np.float32)

    def reset(self):
        return self.obs.copy()

    def action_mask(self):
        return np.ones(2, dtype=np.bool_)

    def step(self, action):
        return self.obs.copy(), float(action), True, False, {}


def test_masked_ppo_can_start_from_supplied_bc_network():
    net = MaskedActorCritic(2, 2, (4,))
    before = state_dict_sha256(net.state_dict())
    cfg = DiscretePPOConfig(
        seed=3, total_steps=8, rollout_steps=4, epochs=1,
        n_minibatches=2, hidden=(4,))
    trained, stats = train(_TinyEnv(), cfg, initial_net=net)
    assert trained is net
    assert stats.initial_weights_sha256 == before
    assert stats.final_weights_sha256 != before


def test_artifact_paths_are_distinct_and_result_is_not_entry88():
    bc = [P.bc_path(seed) for seed in P.TRAIN_SEEDS]
    final = [P.policy_path(seed) for seed in P.TRAIN_SEEDS]
    summary = [P.training_path(seed) for seed in P.TRAIN_SEEDS]
    assert len(set(bc + final + summary)) == 15
    assert P.DEVELOPMENT_RESULTS.name == "shielded_policy_development_results.json"
    assert P.DEVELOPMENT_RESULTS.name != "margin_improve_rl_results.json"


def test_training_refuses_unregistered_seed_or_premature_midpoint_data(
        tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="unregistered"):
        P.train_seed(1)
    monkeypatch.setattr(P, "HERE", tmp_path)
    P.midpoint_path().write_bytes(b"premature")
    with pytest.raises(RuntimeError, match="midpoint"):
        P.train_seed(P.TRAIN_SEEDS[0])
