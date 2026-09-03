"""DEVELOPMENT-only oracle trajectories for Entry 89 actor pretraining."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from nebula.experiments import exp_joint_bank as J
from nebula.rl.margin_adapt_env import MarginBankTable
from nebula.rl.margin_improve_env import (
    A_LOCK, N_ACTIONS, MarginImproveEnv,
)


@dataclass(frozen=True)
class OracleSample:
    observation: np.ndarray
    mask: np.ndarray
    target_probs: np.ndarray


def _coords(setting: int) -> tuple[int, int, int]:
    atten, bank = J.split_setting(int(setting))
    rs, cs = divmod(bank, 8)
    return atten, rs, cs


def setting_distance(left: int, right: int) -> int:
    return int(sum(abs(a - b) for a, b in zip(_coords(left), _coords(right))))


def reachable_teacher(table: MarginBankTable,
                      identity: tuple[str, float, float, float],
                      start: int, radius: int = 7) -> int:
    """Best compliant visible-eye setting in the registered move radius."""
    corner, loss, peaking, frequency = identity
    candidates = [
        setting for setting in table.settings
        if setting_distance(start, setting) <= int(radius)
        and table.compliant(setting, corner, loss, peaking, frequency)]
    if not candidates:
        raise ValueError(f"no compliant teacher within radius for {identity}")
    return max(candidates, key=lambda setting: (
        table.eye_area(setting, corner, loss), -int(setting)))


def reducing_actions(current: int, target: int,
                     mask: np.ndarray) -> tuple[tuple[int, ...], np.ndarray]:
    """Valid move actions that reduce Manhattan distance, with soft labels."""
    available = np.asarray(mask, dtype=np.bool_)
    if available.shape != (N_ACTIONS,):
        raise ValueError(f"mask shape {available.shape} != {(N_ACTIONS,)}")
    before = setting_distance(current, target)
    actions = tuple(
        action for action in range(A_LOCK)
        if available[action]
        and setting_distance(
            MarginImproveEnv.moved_setting(current, action), target) < before)
    if before and not actions:
        raise ValueError("no available action reduces teacher distance")
    probs = np.zeros(N_ACTIONS, dtype=np.float32)
    if actions:
        probs[list(actions)] = 1.0 / len(actions)
    return actions, probs


def oracle_samples(table: MarginBankTable, identities: Sequence[tuple],
                   start_by_request: dict[tuple[float, float], int],
                   radius: int = 7) -> list[OracleSample]:
    """Build deterministic shortest-path actor samples from exposed data."""
    samples: list[OracleSample] = []
    for raw in identities:
        corner, loss, peaking, frequency = (
            str(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))
        identity = (corner, loss, peaking, frequency)
        start = int(start_by_request[(peaking, frequency)])
        target = reachable_teacher(table, identity, start, radius=radius)
        if target == start:
            continue
        env = MarginImproveEnv(
            table, [identity], start_by_request, seed=0)
        obs = env.reset(corner=corner, loss_db=loss,
                        request=(peaking, frequency))
        while env.ep.current_setting != target:
            mask = env.action_mask()
            actions, probs = reducing_actions(
                env.ep.current_setting, target, mask)
            samples.append(OracleSample(
                observation=np.asarray(obs, dtype=np.float32).copy(),
                mask=np.asarray(mask, dtype=np.bool_).copy(),
                target_probs=probs.copy()))
            obs, _, terminated, _, _ = env.step(min(actions))
            if terminated:
                break
        if env.ep.locked_setting is None:
            mask = env.action_mask()
            if not mask[A_LOCK]:
                raise AssertionError("teacher reached target before LOCK enabled")
            probs = np.zeros(N_ACTIONS, dtype=np.float32)
            probs[A_LOCK] = 1.0
            samples.append(OracleSample(
                observation=np.asarray(obs, dtype=np.float32).copy(),
                mask=np.asarray(mask, dtype=np.bool_).copy(),
                target_probs=probs))
    return samples


__all__ = (
    "OracleSample", "setting_distance", "reachable_teacher",
    "reducing_actions", "oracle_samples")
