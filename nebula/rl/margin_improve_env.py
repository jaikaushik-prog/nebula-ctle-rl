"""Entry 88's masked, scale-free margin-improvement environment.

This is separate from Entry 87 so the published absolute-lock reward remains
reproducible.  PVT, channel, compliance and quality are training-only hidden
truth; observations contain only the request, code and measured eye history.
No method invokes SPICE.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np

from nebula.common.types import SPEC_F_PEAK_HZ_RANGE, SPEC_PEAKING_DB_RANGE
from nebula.experiments import exp_joint_bank as J
from nebula.rl.margin_adapt_env import (
    A_ATTEN_DOWN, A_ATTEN_UP, A_CS_DOWN, A_CS_UP, A_LOCK, A_RS_DOWN,
    A_RS_UP, HISTORY_FIELDS, MAX_TRIALS, N_ACTIONS, N_OBS, MarginBankTable,
)


@dataclass
class ImproveEpisode:
    corner: str
    loss_db: float
    target_peaking_db: float
    target_f_peak_hz: float
    start_setting: int
    current_setting: int
    settings_tried: list[int] = field(default_factory=list)
    measurements: list[tuple[bool, float, float]] = field(default_factory=list)
    n_trials: int = 0
    ret: float = 0.0
    start_quality: float = 0.0
    current_quality: float = 0.0
    locked_setting: Optional[int] = None
    locked_compliant: Optional[bool] = None
    quality: float = 0.0

    @property
    def identity(self) -> tuple[str, float, float, float]:
        return (self.corner, self.loss_db, self.target_peaking_db,
                self.target_f_peak_hz)


class MarginImproveEnv:
    """Eight-measurement local adaptation with D18's exact reward and masks."""

    observation_dim = N_OBS
    action_dim = N_ACTIONS

    def __init__(self, table: MarginBankTable, identities: Sequence[tuple],
                 start_by_request: dict[tuple[float, float], int],
                 max_trials: int = MAX_TRIALS, seed: int = 0):
        self.t = table
        self.identities = [
            (str(c), float(loss), float(pk), float(freq))
            for c, loss, pk, freq in identities]
        if not self.identities:
            raise ValueError("empty identity set")
        self.start_by_request = {
            (float(pk), float(freq)): int(setting)
            for (pk, freq), setting in start_by_request.items()}
        self.max_trials = int(max_trials)
        if not 2 <= self.max_trials <= MAX_TRIALS:
            raise ValueError(f"max_trials must be in 2..{MAX_TRIALS}")
        self.rng = np.random.default_rng(seed)
        self.ep: Optional[ImproveEpisode] = None

    def reset(self, corner: Optional[str] = None,
              loss_db: Optional[float] = None,
              request: Optional[tuple[float, float]] = None) -> np.ndarray:
        if corner is None or loss_db is None or request is None:
            corner, loss_db, pk, freq = self.identities[
                int(self.rng.integers(len(self.identities)))]
        else:
            pk, freq = map(float, request)
        req = (float(pk), float(freq))
        start = self.start_by_request[req]
        self.ep = ImproveEpisode(
            corner=str(corner), loss_db=float(loss_db),
            target_peaking_db=req[0], target_f_peak_hz=req[1],
            start_setting=start, current_setting=start)
        self._measure(start)
        q = self._quality(start)
        self.ep.start_quality = q
        self.ep.current_quality = q
        return self._obs()

    def action_mask(self) -> np.ndarray:
        if self.ep is None:
            raise RuntimeError("reset() first")
        if self.ep.locked_setting is not None:
            return np.zeros(N_ACTIONS, dtype=np.bool_)
        atten, bank = J.split_setting(self.ep.current_setting)
        rs, cs = divmod(bank, 8)
        return np.asarray([
            atten > 0, atten < 7, rs > 0, rs < 7, cs > 0, cs < 7,
            self.ep.n_trials >= 2,
        ], dtype=np.bool_)

    def step(self, action: int):
        if self.ep is None:
            raise RuntimeError("reset() first")
        action = int(action)
        if not 0 <= action < N_ACTIONS:
            raise ValueError(f"action {action} outside 0..{N_ACTIONS - 1}")
        if not self.action_mask()[action]:
            raise ValueError(f"masked action {action} is not available")
        if action == A_LOCK:
            return self._lock(truncated=False, move_reward=0.0)

        old_q = self.ep.current_quality
        setting = self.moved_setting(self.ep.current_setting, action)
        if setting == self.ep.current_setting:
            raise AssertionError("an available move must change the setting")
        self.ep.current_setting = setting
        self._measure(setting)
        new_q = self._quality(setting)
        self.ep.current_quality = new_q
        move_reward = new_q - old_q
        self.ep.ret += move_reward
        if self.ep.n_trials >= self.max_trials:
            return self._lock(truncated=True, move_reward=move_reward,
                              move_already_added=True)
        return self._obs(), float(move_reward), False, False, {}

    def _quality(self, setting: int) -> float:
        ep = self.ep
        return self.t.quality(
            setting, ep.corner, ep.loss_db, ep.target_peaking_db,
            ep.target_f_peak_hz)

    def _measure(self, setting: int) -> None:
        ep = self.ep
        ep.settings_tried.append(int(setting))
        ep.measurements.append(self.t.observe(setting, ep.corner, ep.loss_db))
        ep.n_trials += 1

    def _lock(self, truncated: bool, move_reward: float,
              move_already_added: bool = False):
        ep = self.ep
        good = self.t.compliant(
            ep.current_setting, ep.corner, ep.loss_db,
            ep.target_peaking_db, ep.target_f_peak_hz)
        terminal = 0.0 if good else -1.0 - ep.current_quality
        ep.ret += terminal
        ep.locked_setting = ep.current_setting
        ep.locked_compliant = bool(good)
        ep.quality = ep.current_quality if good else 0.0
        reward = terminal + (move_reward if move_already_added else 0.0)
        return self._obs(), float(reward), True, bool(truncated), {
            "locked": ep.current_setting, "compliant": bool(good),
            "quality": float(ep.quality),
            "quality_improvement": float(ep.quality - ep.start_quality),
        }

    @staticmethod
    def moved_setting(setting: int, action: int) -> int:
        atten, bank = J.split_setting(setting)
        rs, cs = divmod(bank, 8)
        if action == A_ATTEN_DOWN:
            atten = max(0, atten - 1)
        elif action == A_ATTEN_UP:
            atten = min(7, atten + 1)
        elif action == A_RS_DOWN:
            rs = max(0, rs - 1)
        elif action == A_RS_UP:
            rs = min(7, rs + 1)
        elif action == A_CS_DOWN:
            cs = max(0, cs - 1)
        elif action == A_CS_UP:
            cs = min(7, cs + 1)
        else:
            raise ValueError(f"action {action} is not a move")
        return J.setting_id(atten, rs * 8 + cs)

    def _obs(self) -> np.ndarray:
        ep = self.ep
        out = np.zeros(N_OBS, dtype=np.float32)
        pk_lo, pk_hi = SPEC_PEAKING_DB_RANGE
        f_lo, f_hi = SPEC_F_PEAK_HZ_RANGE
        out[0] = (ep.target_peaking_db - pk_lo) / (pk_hi - pk_lo)
        out[1] = math.log2(ep.target_f_peak_hz / f_lo) / math.log2(f_hi / f_lo)
        out[2] = ep.n_trials / self.max_trials
        atten, bank = J.split_setting(ep.current_setting)
        rs, cs = divmod(bank, 8)
        out[3:6] = (atten / 7.0, rs / 7.0, cs / 7.0)
        for slot, (setting, measurement) in enumerate(
                zip(ep.settings_tried, ep.measurements)):
            if slot >= MAX_TRIALS:
                break
            i = 6 + slot * HISTORY_FIELDS
            a, b = J.split_setting(setting)
            r, c = divmod(b, 8)
            ok, eye_h, eye_w = measurement
            out[i:i + HISTORY_FIELDS] = (
                1.0, a / 7.0, r / 7.0, c / 7.0, float(ok),
                float(eye_h), float(eye_w))
        return out


__all__ = (
    "A_ATTEN_DOWN", "A_ATTEN_UP", "A_RS_DOWN", "A_RS_UP", "A_CS_DOWN",
    "A_CS_UP", "A_LOCK", "N_ACTIONS", "MAX_TRIALS", "N_OBS",
    "MarginBankTable", "ImproveEpisode", "MarginImproveEnv")
