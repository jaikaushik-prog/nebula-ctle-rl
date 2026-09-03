"""Fail-capable gates for Entry 88's improvement-reward episode."""

from __future__ import annotations

import math

import numpy as np
import pytest

from nebula.experiments import exp_joint_bank as J
from nebula.rl.margin_improve_env import (
    A_ATTEN_DOWN,
    A_ATTEN_UP,
    A_CS_DOWN,
    A_CS_UP,
    A_LOCK,
    A_RS_DOWN,
    A_RS_UP,
    MAX_TRIALS,
    MarginImproveEnv,
)
from nebula.rl.margin_adapt_env import MarginBankTable

REQ = (9.0, 1.9e9)
CORNER = "tt/1.00/27C"
LOSS = 7.5


def _row(setting: int, compliant: bool, area: float,
         visible_area: float | None = None) -> J.JointRow:
    a, bank = J.split_setting(setting)
    margins = {name: 1.0 for name in (
        "S3_peaking", "S3_nyq_boost", "S5_noise", "S6_power",
        "saturation", "tail_saturation", "S8_eye_h", "S8_eye_w",
        "S7_area", "S4_hd3_nyq")}
    seen = area if visible_area is None else visible_area
    return J.JointRow(
        setting=setting, atten_code=a, bank_code=bank, i_rs=bank // 8,
        i_cs=bank % 8, corner=CORNER, ok=True,
        peaking_db=9.0 if compliant else 30.0,
        f_peak_oct=math.log2(1.9e9 / 2.5e9), margins=margins,
        links={str(LOSS): {"ok": True, "eye_h_v": seen,
                           "eye_w_ui": 1.0}})


def _table() -> MarginBankTable:
    return MarginBankTable([
        _row(0, True, 0.25),
        _row(1, True, 1.00),
        _row(8, True, 0.50),
        _row(64, False, 0.0, visible_area=1.20),
        _row(72, True, 0.75),
    ], losses=[LOSS])


def _env(start: int = 0, max_trials: int = MAX_TRIALS) -> MarginImproveEnv:
    return MarginImproveEnv(
        _table(), [(CORNER, LOSS, REQ[0], REQ[1])], {REQ: start},
        max_trials=max_trials, seed=7)


def test_initial_mask_blocks_boundaries_and_immediate_lock():
    env = _env(start=0)
    obs = env.reset(corner=CORNER, loss_db=LOSS, request=REQ)
    mask = env.action_mask()
    assert obs.shape == (env.observation_dim,)
    assert mask.dtype == np.bool_ and mask.shape == (env.action_dim,)
    assert not mask[A_ATTEN_DOWN] and mask[A_ATTEN_UP]
    assert not mask[A_RS_DOWN] and mask[A_RS_UP]
    assert not mask[A_CS_DOWN] and mask[A_CS_UP]
    assert not mask[A_LOCK]


def test_one_real_move_enables_lock_and_invalid_action_cannot_measure():
    env = _env(start=0)
    env.reset(corner=CORNER, loss_db=LOSS, request=REQ)
    with pytest.raises(ValueError, match="masked action"):
        env.step(A_ATTEN_DOWN)
    assert env.ep.n_trials == 1
    env.step(A_CS_UP)
    assert env.ep.settings_tried == [0, 1]
    assert env.action_mask()[A_LOCK]


def test_compliant_return_telescopes_to_quality_improvement():
    env = _env(start=0)
    env.reset(corner=CORNER, loss_db=LOSS, request=REQ)
    _, move_reward, term, _, _ = env.step(A_CS_UP)
    assert not term and move_reward == pytest.approx(0.75)
    _, lock_reward, term, _, info = env.step(A_LOCK)
    assert term and info["compliant"] and lock_reward == 0.0
    assert env.ep.ret == pytest.approx(1.0 - 0.25)


def test_false_lock_return_is_minus_one_minus_start_quality():
    env = _env(start=0)
    env.reset(corner=CORNER, loss_db=LOSS, request=REQ)
    _, move_reward, _, _, _ = env.step(A_ATTEN_UP)
    assert move_reward == pytest.approx(-0.25)
    _, lock_reward, term, _, info = env.step(A_LOCK)
    assert term and not info["compliant"]
    assert lock_reward == pytest.approx(-1.0)
    assert env.ep.ret == pytest.approx(-1.25)


def test_last_measurement_auto_locks_with_the_same_terminal_rule():
    env = _env(start=0, max_trials=2)
    env.reset(corner=CORNER, loss_db=LOSS, request=REQ)
    _, reward, term, trunc, info = env.step(A_CS_UP)
    assert term and trunc and info["compliant"]
    assert reward == pytest.approx(0.75)
    assert env.ep.ret == pytest.approx(0.75)


def test_observation_does_not_reveal_quality_or_compliance():
    rows = [
        _row(0, True, 0.25, visible_area=0.4),
        _row(1, True, 1.0),
    ]
    good = MarginImproveEnv(
        MarginBankTable(rows, losses=[LOSS]),
        [(CORNER, LOSS, *REQ)], {REQ: 0}, seed=1)
    rows[0] = _row(0, False, 0.0, visible_area=0.4)
    hidden_bad = MarginImproveEnv(
        MarginBankTable(rows, losses=[LOSS]),
        [(CORNER, LOSS, *REQ)], {REQ: 0}, seed=1)
    one = good.reset(corner=CORNER, loss_db=LOSS, request=REQ)
    two = hidden_bad.reset(corner=CORNER, loss_db=LOSS, request=REQ)
    assert np.array_equal(one, two)


def test_six_moves_each_change_one_axis():
    start = J.setting_id(3, 3 * 8 + 3)
    expected = {
        A_ATTEN_DOWN: J.setting_id(2, 3 * 8 + 3),
        A_ATTEN_UP: J.setting_id(4, 3 * 8 + 3),
        A_RS_DOWN: J.setting_id(3, 2 * 8 + 3),
        A_RS_UP: J.setting_id(3, 4 * 8 + 3),
        A_CS_DOWN: J.setting_id(3, 3 * 8 + 2),
        A_CS_UP: J.setting_id(3, 3 * 8 + 4),
    }
    for action, target in expected.items():
        assert MarginImproveEnv.moved_setting(start, action) == target
