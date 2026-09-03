"""Entry 87 control accounting and controls-first provenance gates."""

from __future__ import annotations

import ast
import math
from pathlib import Path

import pytest

from nebula.experiments import exp_joint_bank as J
from nebula.experiments import exp_margin_adapt_controls as C
from nebula.rl.margin_adapt_env import MarginBankTable

REQ = (9.0, 1.9e9)
TRAIN = "tt/1.00/27C"
TEST = "sf/1.00/27C"
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


def _table(test_good: int = 1) -> MarginBankTable:
    rows = []
    for corner, good in ((TRAIN, 0), (TEST, test_good)):
        for setting in (0, 1, 64):
            rows.append(_row(setting, corner, setting == good,
                             area=0.1 + setting / 1000.0))
    return MarginBankTable(rows, losses=[LOSS])


def test_artifact_paths_cannot_clobber_historical_controls():
    assert C.RESULTS.name == "margin_adapt_controls_results.json"
    assert C.RESULTS.name != "adapt_controls_multiseed_results.json"


def test_split_is_exact_and_disjoint():
    train, test = C.identities(C.REQUESTS)
    assert len(train) == 1728
    assert len(test) == 864
    assert not set(train).intersection(test)


def test_request_start_map_uses_train_only():
    train_ids = [(TRAIN, LOSS, REQ[0], REQ[1])]
    assert C.select_start_settings(_table(test_good=1), train_ids)[REQ] == 0
    assert C.select_start_settings(_table(test_good=64), train_ids)[REQ] == 0


def test_fixed_control_locks_the_registered_start_in_one_trial():
    table = _table()
    ids = [(TEST, LOSS, REQ[0], REQ[1])]
    out = C.score_arm(table, C.arm_fixed, ids, {REQ: 1})
    assert out["n_episodes"] == 1
    assert out["mean_trials"] == pytest.approx(1.0)
    assert out["compliance_rate"] == pytest.approx(1.0)


def test_random_control_changes_with_seed_and_episode_identity():
    one = C.random_action_trace(17, (TEST, LOSS, REQ[0], REQ[1]))
    assert one == C.random_action_trace(17, (TEST, LOSS, REQ[0], REQ[1]))
    assert one != C.random_action_trace(18, (TEST, LOSS, REQ[0], REQ[1]))
    assert one != C.random_action_trace(17, (TEST, 4.5, REQ[0], REQ[1]))


def test_primary_comparator_obeys_registered_safety_then_quality_rule():
    rows = [
        {"arm": "fixed", "compliance_rate": 0.95,
         "mean_quality": 0.60, "mean_trials": 1.0},
        {"arm": "hillclimb", "compliance_rate": 0.94,
         "mean_quality": 0.70, "mean_trials": 7.0},
        {"arm": "random_mean", "compliance_rate": 0.80,
         "mean_quality": 0.90, "mean_trials": 5.0},
    ]
    assert C.primary_comparator(rows)["arm"] == "hillclimb"


def test_console_literals_are_ascii_for_windows():
    path = Path(C.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for call in (n for n in ast.walk(tree) if isinstance(n, ast.Call)):
        if isinstance(call.func, ast.Name) and call.func.id == "print":
            for const in (n for arg in call.args for n in ast.walk(arg)
                          if isinstance(n, ast.Constant)
                          and isinstance(n.value, str)):
                assert const.value.isascii(), repr(const.value)
