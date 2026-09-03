"""Fail-capable gates for Entry 87's 512-code margin-adaptation episode."""

from __future__ import annotations

import math

import numpy as np
import pytest

from nebula.experiments import exp_joint_bank as J
from nebula.rl.margin_adapt_env import (
    A_ATTEN_DOWN,
    A_ATTEN_UP,
    A_CS_DOWN,
    A_CS_UP,
    A_LOCK,
    A_RS_DOWN,
    A_RS_UP,
    HISTORY_FIELDS,
    MAX_TRIALS,
    N_ACTIONS,
    N_OBS,
    MarginAdaptEnv,
    MarginBankTable,
)

REQ = (9.0, 1.9e9)
CORNER = "tt/1.00/27C"
LOSS = 7.5


def _row(setting: int, compliant: bool = False, eye_h: float = 0.2,
         eye_w: float = 0.6, link_ok: bool = True) -> J.JointRow:
    a, bank = J.split_setting(setting)
    margins = {
        "S3_peaking": 1.0,
        "S3_nyq_boost": 1.0,
        "S5_noise": 1.0,
        "S6_power": 1.0,
        "saturation": 1.0,
        "tail_saturation": 1.0,
        "S8_eye_h": 1.0,
        "S8_eye_w": 1.0,
        "S7_area": 1.0,
        "S4_hd3_nyq": 1.0,
    }
    return J.JointRow(
        setting=setting, atten_code=a, bank_code=bank,
        i_rs=bank // 8, i_cs=bank % 8, corner=CORNER, ok=True,
        peaking_db=9.0 if compliant else 30.0,
        f_peak_oct=math.log2(1.9e9 / 2.5e9), margins=margins,
        links={str(LOSS): ({"ok": True, "eye_h_v": eye_h,
                            "eye_w_ui": eye_w} if link_ok else
                           {"ok": False, "reason": "compression"})},
    )


def _table(rows=None) -> MarginBankTable:
    return MarginBankTable(rows or [
        _row(0, compliant=True, eye_h=0.1, eye_w=0.4),
        _row(1, compliant=True, eye_h=0.2, eye_w=0.6),
        _row(64, compliant=False, eye_h=0.3, eye_w=0.7),
    ], losses=[LOSS])


def _env(table=None, start=0, max_trials=MAX_TRIALS) -> MarginAdaptEnv:
    return MarginAdaptEnv(
        table or _table(), [(CORNER, LOSS, REQ[0], REQ[1])],
        {REQ: start}, max_trials=max_trials, seed=7)


def test_registered_shapes_and_actions():
    assert N_ACTIONS == 7
    assert {A_ATTEN_DOWN, A_ATTEN_UP, A_RS_DOWN, A_RS_UP,
            A_CS_DOWN, A_CS_UP, A_LOCK} == set(range(7))
    assert N_OBS == 6 + MAX_TRIALS * HISTORY_FIELDS
    env = _env()
    assert env.observation_dim == N_OBS
    assert env.action_dim == N_ACTIONS
    assert env.reset(corner=CORNER, loss_db=LOSS, request=REQ).shape == (N_OBS,)


def test_observation_does_not_leak_compliance_or_hidden_identity():
    # Same receiver-visible eye, different non-eye compliance truth.
    seen = []
    for good in (True, False):
        table = _table([_row(0, compliant=good, eye_h=0.2, eye_w=0.6)])
        env = _env(table)
        seen.append(env.reset(corner=CORNER, loss_db=LOSS, request=REQ))
    assert np.array_equal(seen[0], seen[1])
    # There is no corner/loss-sized one-hot tail hidden in the shape.
    assert seen[0].shape == (N_OBS,)


def test_reset_measures_the_train_selected_start_and_costs_one_trial():
    env = _env(start=1)
    env.reset(corner=CORNER, loss_db=LOSS, request=REQ)
    assert env.ep.settings_tried == [1]
    assert env.ep.n_trials == 1
    assert env.ep.ret == pytest.approx(-1.0)


def test_six_moves_change_exactly_one_physical_code_axis():
    start = J.setting_id(3, 3 * 8 + 3)
    expected = {
        A_ATTEN_DOWN: J.setting_id(2, 3 * 8 + 3),
        A_ATTEN_UP: J.setting_id(4, 3 * 8 + 3),
        A_RS_DOWN: J.setting_id(3, 2 * 8 + 3),
        A_RS_UP: J.setting_id(3, 4 * 8 + 3),
        A_CS_DOWN: J.setting_id(3, 3 * 8 + 2),
        A_CS_UP: J.setting_id(3, 3 * 8 + 4),
    }
    rows = [_row(s, compliant=True) for s in {start, *expected.values()}]
    for action, target in expected.items():
        env = _env(_table(rows), start=start)
        env.reset(corner=CORNER, loss_db=LOSS, request=REQ)
        env.step(action)
        assert env.ep.current_setting == target


def test_boundary_move_remeasures_the_same_code_and_costs_a_trial():
    env = _env(start=0)
    env.reset(corner=CORNER, loss_db=LOSS, request=REQ)
    _, reward, term, trunc, _ = env.step(A_ATTEN_DOWN)
    assert not term and not trunc
    assert reward == pytest.approx(-1.0)
    assert env.ep.settings_tried == [0, 0]
    assert env.ep.n_trials == 2


def test_lock_reward_is_exact_quality_scaled_or_false_lock_penalty():
    env = _env(start=0)
    env.reset(corner=CORNER, loss_db=LOSS, request=REQ)
    _, reward, term, _, info = env.step(A_LOCK)
    # area 0.04 / oracle area 0.12 = 1/3
    assert term and info["compliant"]
    assert info["quality"] == pytest.approx(1.0 / 3.0)
    assert reward == pytest.approx(20.0 / 3.0)

    env = _env(start=64)
    env.reset(corner=CORNER, loss_db=LOSS, request=REQ)
    _, reward, term, _, info = env.step(A_LOCK)
    assert term and not info["compliant"]
    assert info["quality"] == 0.0
    assert reward == pytest.approx(-60.0)


def test_eighth_measurement_auto_locks_the_last_code():
    env = _env(start=0, max_trials=3)
    env.reset(corner=CORNER, loss_db=LOSS, request=REQ)
    env.step(A_CS_UP)
    _, reward, term, trunc, info = env.step(A_CS_DOWN)
    assert term and trunc and env.ep.n_trials == 3
    assert info["locked"] == 0
    assert reward == pytest.approx(-1.0 + 20.0 / 3.0)
