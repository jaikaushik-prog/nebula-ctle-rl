"""Fail-capable gates for Entry 89's fresh midpoint-bank generator."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from nebula.common.types import Corner
from nebula.experiments import exp_joint_bank as J
from nebula.experiments import exp_joint_bank_midpoint as M


def test_midpoint_losses_requests_and_final_count_are_exact():
    assert M.MIDPOINT_LOSSES_DB == (3.75, 5.25, 6.75, 8.25, 9.75, 11.25)
    assert M.FINAL_PEAKING_DB == (5.0, 7.0, 9.0)
    assert M.FINAL_FREQ_EXPONENTS == (0.265, 0.5, 0.735)
    assert len(M.FINAL_REQUESTS) == 9
    assert M.N_FINAL_IDENTITIES == 2430
    assert not set(M.MIDPOINT_LOSSES_DB).intersection(J.LOSSES_DB)


def test_custom_losses_reach_link_evaluation_and_row_keys(monkeypatch):
    captured = {}
    point = SimpleNamespace(
        ok=True,
        links_by_loss={loss: {"ok": True, "eye_h_v": 0.3,
                              "eye_w_ui": 0.7}
                       for loss in M.MIDPOINT_LOSSES_DB},
        peaking_db=9.0, f_peak_oct=-0.4,
        margins={name: 1.0 for name in J.SPECS
                 if name not in J.REQUEST_ROWS},
        eye_h_v=0.3, eye_w_ui=0.7, power_w=5e-3,
        hd3_nyq_dbc=-40.0, g_dc_db=-11.0, noise_vrms=0.7e-3,
    )

    def fake_evaluate(*args, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(points=[point], reason=None)

    monkeypatch.setattr(J, "evaluate_at_points", fake_evaluate)
    st = SimpleNamespace(u=(0.5,) * 7, i_rs=0, i_cs=0)
    row = J._measure((
        0, st, 7, Corner("tt", 1.0, 27.0), 2.3,
        M.MIDPOINT_LOSSES_DB))
    assert tuple(captured["link_losses_db"]) == M.MIDPOINT_LOSSES_DB
    assert set(row.links) == {str(value) for value in M.MIDPOINT_LOSSES_DB}


def test_generator_refuses_without_committed_policy_manifest(
        tmp_path, monkeypatch):
    monkeypatch.setattr(M, "HERE", tmp_path)
    with pytest.raises(FileNotFoundError, match="policy freeze manifest"):
        M.validate_policy_freeze()


def test_generator_metadata_cannot_claim_final_scoring():
    assert M.METADATA_NAME == "joint_bank_midpoint_metadata.json"
    assert M.FINAL_STATUS == "GENERATED_NOT_SCORED"
    assert M.EXPECTED_ROWS == 23040
