"""Entry 88 split, controls and controls-first provenance gates."""

from __future__ import annotations

import ast
import math
from pathlib import Path

import pytest

from nebula.experiments import exp_joint_bank as J
from nebula.experiments import exp_margin_improve_controls as C
from nebula.rl.margin_adapt_env import MarginBankTable

REQ = (9.0, 1.9e9)
TRAIN_A = "tt/1.00/27C"
TRAIN_B = "sf/1.00/27C"
LOSS = 7.5


def _row(setting: int, corner: str, compliant: bool, area: float) -> J.JointRow:
    a, bank = J.split_setting(setting)
    margins = {name: 1.0 for name in (
        "S3_peaking", "S3_nyq_boost", "S5_noise", "S6_power",
        "saturation", "tail_saturation", "S8_eye_h", "S8_eye_w",
        "S7_area", "S4_hd3_nyq")}
    return J.JointRow(
        setting=setting, atten_code=a, bank_code=bank, i_rs=bank // 8,
        i_cs=bank % 8, corner=corner, ok=True,
        peaking_db=9.0 if compliant else 30.0,
        f_peak_oct=math.log2(1.9e9 / 2.5e9), margins=margins,
        links={str(LOSS): {"ok": True, "eye_h_v": area,
                           "eye_w_ui": 1.0}})


def _table() -> MarginBankTable:
    rows = []
    for corner in (TRAIN_A, TRAIN_B):
        rows.extend([
            _row(0, corner, True, 0.2),
            _row(1, corner, True, 1.0),
            _row(8, corner, True, 0.6),
            _row(64, corner, False, 1.2),
        ])
    return MarginBankTable(rows, losses=[LOSS])


def test_artifact_path_is_new_and_cannot_clobber_entry87():
    assert C.RESULTS.name == "margin_improve_controls_results.json"
    assert C.RESULTS.name != "margin_adapt_controls_results.json"


def test_split_is_exact_disjoint_and_complete():
    train, final = C.identities(C.REQUESTS)
    assert len(train) == 2592
    assert len(final) == 2448
    assert not set(train).intersection(final)
    assert len(set(train).union(final)) == 5040


def test_start_selection_uses_only_supplied_train_identities():
    table = _table()
    only_a = [(TRAIN_A, LOSS, *REQ)]
    assert C.select_start_settings(table, only_a)[REQ] == 1


def test_manhattan_distance_uses_atten_rs_cs_axes():
    zero = J.setting_id(0, 0)
    target = J.setting_id(2, 3 * 8 + 1)
    assert C.setting_distance(zero, target) == 6
    assert C.setting_distance(target, zero) == 6


def test_reachable_oracle_respects_seven_move_radius():
    table = _table()
    ids = [(TRAIN_A, LOSS, *REQ)]
    result = C.score_reachable_oracle(table, ids, {REQ: 0}, radius=1)
    assert result["mean_quality"] == pytest.approx(1.0)
    assert result["per_identity"][0]["locked_setting"] == 1
    assert result["per_identity"][0]["move_distance"] == 1


def test_fixed_control_is_direct_one_measurement_comparator():
    result = C.score_fixed(_table(), [(TRAIN_A, LOSS, *REQ)], {REQ: 1})
    assert result["compliance_rate"] == 1.0
    assert result["mean_quality"] == 1.0
    assert result["mean_trials"] == 1.0
    assert result["code_change_rate"] == 0.0


def test_random_trace_is_stable_and_identity_specific():
    identity = (TRAIN_A, LOSS, *REQ)
    assert C.random_uniforms(7, identity) == C.random_uniforms(7, identity)
    assert C.random_uniforms(7, identity) != C.random_uniforms(8, identity)
    assert C.random_uniforms(7, identity) != C.random_uniforms(
        7, (TRAIN_B, LOSS, *REQ))


def test_random_summary_averages_seed_compliance_and_code_change():
    rows = [_row(setting, TRAIN_A, setting in (0, 1),
                 0.2 + setting / 1000.0) for setting in range(512)]
    table = MarginBankTable(rows, losses=[LOSS])
    result = C.score_random(table, [(TRAIN_A, LOSS, *REQ)], {REQ: 0})
    per_seed = result["per_seed"]
    assert result["compliance_rate"] == pytest.approx(
        sum(row["compliance_rate"] for row in per_seed) / len(per_seed))
    assert result["n_compliant"] == pytest.approx(result["compliance_rate"])
    assert result["n_false_locks"] == pytest.approx(
        1.0 - result["compliance_rate"])
    assert result["code_change_rate"] == pytest.approx(
        sum(row["code_change_rate"] for row in per_seed) / len(per_seed))


def test_console_literals_are_ascii_for_windows():
    tree = ast.parse(Path(C.__file__).read_text(encoding="utf-8"))
    for call in (n for n in ast.walk(tree) if isinstance(n, ast.Call)):
        if isinstance(call.func, ast.Name) and call.func.id == "print":
            for const in (n for arg in call.args for n in ast.walk(arg)
                          if isinstance(n, ast.Constant)
                          and isinstance(n.value, str)):
                assert const.value.isascii(), repr(const.value)
