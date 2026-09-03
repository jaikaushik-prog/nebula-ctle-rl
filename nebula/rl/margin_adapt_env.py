"""Entry 87's frozen-table, hidden-state margin-adaptation environment.

This is intentionally separate from :mod:`nebula.rl.adapt_env`, whose 64-code
binary-compliance result is already published.  Here the fabricated circuit has
8 attenuator x 8 Rs x 8 Cs settings.  The policy sees only the request and the
ordered eye measurements it could obtain during receiver calibration; PVT,
channel loss, compliance and non-eye spec rows remain reward-only ground truth.
No method in this module invokes SPICE.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np

from nebula.common.types import SPEC_F_PEAK_HZ_RANGE, SPEC_PEAKING_DB_RANGE
from nebula.experiments import exp_joint_bank as J

A_ATTEN_DOWN = 0
A_ATTEN_UP = 1
A_RS_DOWN = 2
A_RS_UP = 3
A_CS_DOWN = 4
A_CS_UP = 5
A_LOCK = 6
N_ACTIONS = 7

MAX_TRIALS = 8
HISTORY_FIELDS = 7  # present, a, Rs, Cs, link-valid, eye H, eye W
N_OBS = 6 + MAX_TRIALS * HISTORY_FIELDS


@dataclass(frozen=True)
class MarginAdaptReward:
    """Human-approved D17 weights; do not tune after seeing a result."""

    trial_cost: float = 1.0
    false_lock: float = 60.0
    compliant_scale: float = 20.0


@dataclass
class MarginEpisode:
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
    locked_setting: Optional[int] = None
    locked_compliant: Optional[bool] = None
    quality: float = 0.0

    @property
    def identity(self) -> tuple[str, float, float, float]:
        return (self.corner, self.loss_db, self.target_peaking_db,
                self.target_f_peak_hz)


class MarginBankTable:
    """The immutable 512-code Entry 86 table, indexed without simulation."""

    def __init__(self, rows: Sequence[J.JointRow],
                 losses: Optional[Sequence[float]] = None):
        self.by = {(int(r.setting), str(r.corner)): r for r in rows}
        if not self.by:
            raise ValueError("empty margin-adaptation table")
        if len(self.by) != len(rows):
            raise ValueError("duplicate setting/corner rows")
        self.settings = sorted({int(r.setting) for r in rows})
        self.corners = sorted({str(r.corner) for r in rows})
        self.losses = tuple(float(x) for x in (
            losses if losses is not None else J.LOSSES_DB))
        self._good: dict[tuple, tuple[int, ...]] = {}
        self._oracle_area: dict[tuple, float] = {}

    @classmethod
    def from_path(cls, path) -> "MarginBankTable":
        return cls(J._load_rows(path))

    def row(self, setting: int, corner: str) -> J.JointRow:
        return self.by[(int(setting), str(corner))]

    def observe(self, setting: int, corner: str,
                loss_db: float) -> tuple[bool, float, float]:
        row = self.row(setting, corner)
        link = (row.links or {}).get(str(float(loss_db)), {})
        if not row.ok or not link.get("ok"):
            return False, 0.0, 0.0
        return True, float(link["eye_h_v"]), float(link["eye_w_ui"])

    def compliant(self, setting: int, corner: str, loss_db: float,
                  target_peaking_db: float,
                  target_f_peak_hz: float) -> bool:
        return J.is_compliant(
            self.row(setting, corner), float(loss_db),
            float(target_f_peak_hz), float(target_peaking_db))

    def compliant_settings(self, corner: str, loss_db: float,
                           target_peaking_db: float,
                           target_f_peak_hz: float) -> tuple[int, ...]:
        key = (str(corner), float(loss_db), float(target_peaking_db),
               float(target_f_peak_hz))
        if key not in self._good:
            self._good[key] = tuple(
                setting for setting in self.settings
                if self.compliant(setting, *key))
        return self._good[key]

    def eye_area(self, setting: int, corner: str, loss_db: float) -> float:
        ok, h, w = self.observe(setting, corner, loss_db)
        return h * w if ok else 0.0

    def oracle_area(self, corner: str, loss_db: float,
                    target_peaking_db: float,
                    target_f_peak_hz: float) -> float:
        key = (str(corner), float(loss_db), float(target_peaking_db),
               float(target_f_peak_hz))
        if key not in self._oracle_area:
            good = self.compliant_settings(*key)
            self._oracle_area[key] = max(
                (self.eye_area(s, key[0], key[1]) for s in good), default=0.0)
        return self._oracle_area[key]

    def quality(self, setting: int, corner: str, loss_db: float,
                target_peaking_db: float,
                target_f_peak_hz: float) -> float:
        if not self.compliant(setting, corner, loss_db, target_peaking_db,
                              target_f_peak_hz):
            return 0.0
        ceiling = self.oracle_area(corner, loss_db, target_peaking_db,
                                   target_f_peak_hz)
        if ceiling <= 0.0:
            return 0.0
        return float(np.clip(self.eye_area(setting, corner, loss_db) / ceiling,
                             0.0, 1.0))


class MarginAdaptEnv:
    """Gym-shaped Entry 87 episode with seven discrete local actions."""

    observation_dim = N_OBS
    action_dim = N_ACTIONS

    def __init__(self, table: MarginBankTable, identities: Sequence[tuple],
                 start_by_request: dict[tuple[float, float], int],
                 reward: MarginAdaptReward = MarginAdaptReward(),
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
        self.R = reward
        self.max_trials = int(max_trials)
        if not 1 <= self.max_trials <= MAX_TRIALS:
            raise ValueError(f"max_trials must be in 1..{MAX_TRIALS}")
        self.rng = np.random.default_rng(seed)
        self.ep: Optional[MarginEpisode] = None

    def reset(self, corner: Optional[str] = None,
              loss_db: Optional[float] = None,
              request: Optional[tuple[float, float]] = None) -> np.ndarray:
        if corner is None or loss_db is None or request is None:
            identity = self.identities[int(self.rng.integers(len(self.identities)))]
            corner, loss_db, pk, freq = identity
        else:
            pk, freq = map(float, request)
        req = (float(pk), float(freq))
        start = self.start_by_request[req]
        self.ep = MarginEpisode(
            corner=str(corner), loss_db=float(loss_db),
            target_peaking_db=req[0], target_f_peak_hz=req[1],
            start_setting=start, current_setting=start,
            ret=-self.R.trial_cost)
        self._measure(start)
        return self._obs()

    def step(self, action: int):
        if self.ep is None:
            raise RuntimeError("reset() first")
        action = int(action)
        if not 0 <= action < N_ACTIONS:
            raise ValueError(f"action {action} outside 0..{N_ACTIONS - 1}")
        if action == A_LOCK:
            return self._lock(truncated=False, step_cost=0.0)
        setting = self._moved_setting(self.ep.current_setting, action)
        self.ep.current_setting = setting
        self._measure(setting)
        self.ep.ret -= self.R.trial_cost
        if self.ep.n_trials >= self.max_trials:
            return self._lock(truncated=True, step_cost=-self.R.trial_cost)
        return self._obs(), -self.R.trial_cost, False, False, {}

    def _measure(self, setting: int) -> None:
        ep = self.ep
        ep.settings_tried.append(int(setting))
        ep.measurements.append(self.t.observe(setting, ep.corner, ep.loss_db))
        ep.n_trials += 1

    def _lock(self, truncated: bool, step_cost: float):
        ep = self.ep
        setting = ep.current_setting
        good = self.t.compliant(
            setting, ep.corner, ep.loss_db, ep.target_peaking_db,
            ep.target_f_peak_hz)
        q = self.t.quality(
            setting, ep.corner, ep.loss_db, ep.target_peaking_db,
            ep.target_f_peak_hz) if good else 0.0
        terminal = self.R.compliant_scale * q if good else -self.R.false_lock
        ep.locked_setting = setting
        ep.locked_compliant = bool(good)
        ep.quality = float(q)
        ep.ret += terminal
        return self._obs(), step_cost + terminal, True, bool(truncated), {
            "locked": setting, "compliant": bool(good), "quality": float(q)}

    @staticmethod
    def _moved_setting(setting: int, action: int) -> int:
        atten, bank_code = J.split_setting(setting)
        rs, cs = divmod(bank_code, 8)
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
    "A_CS_UP", "A_LOCK", "N_ACTIONS", "MAX_TRIALS", "HISTORY_FIELDS",
    "N_OBS", "MarginAdaptReward", "MarginEpisode", "MarginBankTable",
    "MarginAdaptEnv")
