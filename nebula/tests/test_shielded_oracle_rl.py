"""Fail-capable layer gates for Entry 89's shield and oracle teacher."""

from __future__ import annotations

import math

import numpy as np
import pytest

from nebula.experiments import exp_joint_bank as J
from nebula.rl.margin_adapt_env import MarginBankTable
from nebula.rl.margin_improve_env import A_ATTEN_UP, A_LOCK, A_RS_UP
from nebula.rl.oracle_imitation import (
    OracleSample, oracle_samples, reachable_teacher, reducing_actions,
)
from nebula.rl.safety_shield import select_best_compliant_visited

REQ = (9.0, 1.9e9)
CORNER = "tt/1.00/27C"
LOSS = 7.5
IDENTITY = (CORNER, LOSS, *REQ)


def _row(setting: int, compliant: bool, area: float) -> J.JointRow:
    atten, bank = J.split_setting(setting)
    margins = {name: 1.0 for name in (
        "S3_peaking", "S3_nyq_boost", "S5_noise", "S6_power",
        "saturation", "tail_saturation", "S8_eye_h", "S8_eye_w",
        "S7_area", "S4_hd3_nyq")}
    return J.JointRow(
        setting=setting, atten_code=atten, bank_code=bank,
        i_rs=bank // 8, i_cs=bank % 8, corner=CORNER, ok=True,
        peaking_db=9.0 if compliant else 30.0,
        f_peak_oct=math.log2(1.9e9 / 2.5e9), margins=margins,
        links={str(LOSS): {"ok": True, "eye_h_v": area,
                           "eye_w_ui": 1.0}})


def _table() -> MarginBankTable:
    return MarginBankTable([
        _row(0, True, 0.40),
        _row(1, True, 0.70),
        _row(8, True, 0.60),
        _row(64, False, 1.20),
        _row(72, True, 1.00),
    ], losses=[LOSS])


def test_shield_keeps_a_compliant_start_when_policy_ends_unsafe():
    out = select_best_compliant_visited(_table(), IDENTITY, [0, 64])
    assert out.setting == 0
    assert out.compliant and out.intervened
    assert out.n_verifier_calls == 2


def test_shield_selects_largest_visible_eye_among_compliant_visited():
    out = select_best_compliant_visited(_table(), IDENTITY, [0, 1, 72, 64])
    assert out.setting == 72
    assert out.compliant and out.eye_area == pytest.approx(1.0)
    assert out.first_visit == 2 and out.n_verifier_calls == 4


def test_shield_falls_back_to_start_if_nothing_visited_is_compliant():
    table = MarginBankTable([_row(64, False, 1.2)], losses=[LOSS])
    out = select_best_compliant_visited(table, IDENTITY, [64])
    assert out.setting == 64
    assert not out.compliant and out.shield_failure


def test_reachable_teacher_uses_best_compliant_eye_and_lower_id_tie():
    table = _table()
    assert reachable_teacher(table, IDENTITY, start=0, radius=1) == 1
    assert reachable_teacher(table, IDENTITY, start=0, radius=2) == 72


def test_reducing_action_target_is_uniform_and_respects_mask():
    mask = np.ones(7, dtype=np.bool_)
    actions, probs = reducing_actions(0, 72, mask)
    assert actions == (A_ATTEN_UP, A_RS_UP)
    assert probs.shape == (7,)
    assert probs[A_ATTEN_UP] == pytest.approx(0.5)
    assert probs[A_RS_UP] == pytest.approx(0.5)
    assert probs[A_LOCK] == 0.0
    mask[A_ATTEN_UP] = False
    actions, probs = reducing_actions(0, 72, mask)
    assert actions == (A_RS_UP,)
    assert probs[A_RS_UP] == 1.0


def test_oracle_samples_follow_shortest_path_and_end_in_lock():
    samples = oracle_samples(_table(), [IDENTITY], {REQ: 0}, radius=2)
    assert len(samples) == 3
    assert samples[0].target_probs[A_ATTEN_UP] == pytest.approx(0.5)
    assert samples[0].target_probs[A_RS_UP] == pytest.approx(0.5)
    assert np.argmax(samples[-1].target_probs) == A_LOCK
    assert samples[-1].mask[A_LOCK]
    assert all(sample.observation.shape == (62,) for sample in samples)


def test_actor_sample_interface_contains_no_hidden_identity_or_verdict():
    assert set(OracleSample.__dataclass_fields__) == {
        "observation", "mask", "target_probs"}


def test_zero_distance_teacher_emits_no_initially_masked_lock_sample():
    table = MarginBankTable([_row(0, True, 1.0)], losses=[LOSS])
    assert oracle_samples(table, [IDENTITY], {REQ: 0}, radius=7) == []
