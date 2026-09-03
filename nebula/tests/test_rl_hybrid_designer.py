"""Product-boundary tests for the frozen RL proposer and safety fallback.

These tests deliberately use a tiny in-memory bank.  They prove the control
flow without treating the 4.3 MB pre-characterisation journal as a unit-test
fixture and without invoking ngspice.
"""

from __future__ import annotations

import math

import numpy as np

from nebula.experiments import exp_joint_bank as J
from nebula.rl.margin_adapt_env import MarginBankTable
from nebula.rl.margin_improve_env import A_LOCK, A_RS_UP, MarginImproveEnv

REQ = (9.0, 1.9e9)
LOSS = 7.5
CORNERS = ("tt/1.00/27C", "ss/0.95/125C")


def _row(setting: int, corner: str, compliant: bool, area: float) -> J.JointRow:
    atten, bank = J.split_setting(setting)
    margins = {name: 1.0 for name in (
        "S3_peaking", "S3_nyq_boost", "S5_noise", "S6_power",
        "saturation", "tail_saturation", "S8_eye_h", "S8_eye_w",
        "S7_area", "S4_hd3_nyq")}
    return J.JointRow(
        setting=setting, atten_code=atten, bank_code=bank,
        i_rs=bank // 8, i_cs=bank % 8, corner=corner, ok=True,
        peaking_db=9.0 if compliant else 30.0,
        f_peak_oct=math.log2(REQ[1] / 2.5e9), margins=margins,
        links={str(LOSS): {"ok": True, "eye_h_v": area,
                           "eye_w_ui": 1.0}}, g_dc_db=-4.0,
        noise_mvrms=0.3, power_w=0.003, hd3_nyq_dbc=-40.0)


def _table() -> MarginBankTable:
    # 0 passes TT only; 8 passes both; 16 is the highest-eye safe fallback.
    status = {
        (0, CORNERS[0]): (True, 0.4), (0, CORNERS[1]): (False, 0.4),
        (8, CORNERS[0]): (True, 0.5), (8, CORNERS[1]): (True, 0.5),
        (16, CORNERS[0]): (True, 0.8), (16, CORNERS[1]): (True, 0.8),
    }
    return MarginBankTable([
        _row(setting, corner, *status[(setting, corner)])
        for setting in (0, 8, 16) for corner in CORNERS
    ], losses=[LOSS])


def test_product_observation_exactly_matches_the_trained_actor_contract():
    """Inference must not silently feed the frozen policy a new observation."""
    from nebula.rl.hybrid_designer import build_observation

    table = _table()
    env = MarginImproveEnv(table, [(CORNERS[0], LOSS, *REQ)], {REQ: 0})
    expected = env.reset(corner=CORNERS[0], loss_db=LOSS, request=REQ)
    actual = build_observation(
        REQ, current_setting=0, settings_tried=[0],
        measurements=[table.observe(0, CORNERS[0], LOSS)])
    np.testing.assert_array_equal(actual, expected)


def test_policy_trace_has_the_registered_eight_measurement_hard_limit():
    from nebula.rl.hybrid_designer import trace_policy

    def choose(_net, _obs, mask):
        return A_RS_UP if mask[A_RS_UP] else A_LOCK

    trace = trace_policy(
        object(), lambda setting: (True, 0.4, 0.5),
        REQ, start_setting=0, choose_action=choose)
    assert 1 <= len(trace.settings_tried) <= 8
    assert trace.locked_setting == trace.settings_tried[-1]


def test_shield_uses_rl_when_it_found_a_safe_setting():
    from nebula.rl.hybrid_designer import select_with_bank_fallback

    selected = select_with_bank_fallback(
        _table(), (CORNERS[0], LOSS, *REQ), [0, 8])
    assert selected.setting == 8
    assert selected.source == "rl-shield"
    assert selected.compliant
    assert selected.bank_rows_checked == 0


def test_shield_falls_back_to_the_measured_bank_when_rl_found_none():
    from nebula.rl.hybrid_designer import select_with_bank_fallback

    selected = select_with_bank_fallback(
        _table(), (CORNERS[1], LOSS, *REQ), [0])
    assert selected.setting == 16
    assert selected.source == "bank-fallback"
    assert selected.compliant
    assert selected.bank_rows_checked == 3


def test_production_inference_does_not_read_hidden_reward_or_final_data():
    """The actor may see requests/codes/eyes only, exactly as evaluated."""
    import inspect
    import nebula.rl.hybrid_designer as H

    source = inspect.getsource(H)
    assert "MarginImproveEnv" not in source
    assert "exp_shielded_final" not in source
    assert ".quality(" not in source
    assert ".oracle" not in source
