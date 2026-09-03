"""Fail-capable gates for Entry 89's exposed DEVELOPMENT controls."""

from __future__ import annotations

import math

import pytest

from nebula.experiments import exp_joint_bank as J
from nebula.experiments import exp_shielded_controls as C
from nebula.rl.margin_adapt_env import MarginBankTable
from nebula.rl.margin_improve_env import MarginImproveEnv
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
        _row(0, True, 0.4), _row(1, True, 0.8),
        _row(64, False, 1.2),
    ], losses=[LOSS])


def test_development_is_the_exact_exposed_5040_identity_union():
    ids = C.development_identities()
    assert len(ids) == len(set(ids)) == 5040
    assert {row[1] for row in ids} == set(J.LOSSES_DB)
    assert {row[2:] for row in ids} == set(C.BASE.REQUESTS)


def test_control_artifact_is_distinct_and_final_is_not_scored():
    assert C.RESULTS.name == "shielded_controls_results.json"
    assert C.FINAL_STATUS == "NOT_GENERATED_NOT_SCORED"
    assert C.SIMULATIONS_RUN == 0


def test_shielded_record_uses_actual_visits_and_bills_each_verdict():
    table = _table()
    env = MarginImproveEnv(table, [IDENTITY], {REQ: 0}, seed=1)
    env.reset(corner=CORNER, loss_db=LOSS, request=REQ)
    env.ep.settings_tried.extend([1, 64])
    selection = select_best_compliant_visited(
        table, IDENTITY, env.ep.settings_tried)
    row = C.shielded_record(env.ep, selection)
    assert row["locked_setting"] == 1
    assert row["compliant"]
    assert row["n_trials"] == row["n_verifier_calls"] == 3
    assert row["quality"] == pytest.approx(1.0)
    assert row["shield_intervened"]


def test_shield_summary_cannot_hide_interventions_or_failures():
    episodes = [{
        "corner": CORNER, "loss_db": LOSS, "target_peaking_db": REQ[0],
        "target_f_peak_hz": REQ[1], "start_setting": 0,
        "locked_setting": 0, "compliant": True, "start_quality": 0.5,
        "quality": 0.5, "quality_improvement": 0.0, "n_trials": 2,
        "return": 0.0, "move_distance": 0, "shield_intervened": True,
        "shield_failure": False, "n_verifier_calls": 2,
    }, {
        "corner": CORNER, "loss_db": LOSS, "target_peaking_db": REQ[0],
        "target_f_peak_hz": REQ[1], "start_setting": 0,
        "locked_setting": 0, "compliant": False, "start_quality": 0.0,
        "quality": 0.0, "quality_improvement": 0.0, "n_trials": 3,
        "return": -1.0, "move_distance": 0, "shield_intervened": False,
        "shield_failure": True, "n_verifier_calls": 3,
    }]
    out = C.summarise_shielded("test", episodes)
    assert out["n_shield_interventions"] == 1
    assert out["n_shield_failures"] == 1
    assert out["mean_verifier_calls"] == pytest.approx(2.5)


def test_development_checks_require_structural_safety_and_quality():
    fixed = {"compliance_rate": 0.98, "mean_quality": 0.70}
    rows = [{"compliance_rate": 0.98, "mean_quality": 0.74,
             "quality_delta": 0.04} for _ in range(5)]
    assert all(C.development_checks(fixed, rows).values())
    rows[0]["compliance_rate"] = 0.97
    assert not C.development_checks(fixed, rows)["D1_safety"]
    rows = [{"compliance_rate": 0.98, "mean_quality": 0.71,
             "quality_delta": 0.01} for _ in range(5)]
    assert not C.development_checks(fixed, rows)["D2_quality"]
