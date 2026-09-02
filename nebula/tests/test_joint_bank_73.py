"""Fail-capable gates for entry 86's full 7.3 dB bank verification."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from nebula.experiments import exp_joint_bank as J
from nebula.experiments import exp_joint_bank_73 as P


def _analysis(coverage=(16, 15, 16, 16, 16, 16, 16),
              scorable_3db=7520, all_channel=720) -> dict:
    per_loss = []
    for loss, served in zip(J.LOSSES_DB, coverage):
        per_loss.append({
            "loss_db": loss,
            "n_scorable": scorable_3db if loss == 3.0 else 8000,
            "n_solvable_corner_requests": 720,
            "n_requests_served_all_corners": served,
        })
    return {
        "n_rows": P.EXPECTED_ROWS,
        "n_expected": P.EXPECTED_ROWS,
        "membership_ok": True,
        "n_corners": 45,
        "n_requests": 16,
        "per_loss": per_loss,
        "channel_adaptation": {
            "n_corner_requests_solvable_on_every_channel": all_channel,
            "n_needing_different_setting_for_compliance": 0,
            "n_whose_best_eye_setting_moves": 600,
            "best_setting_attenuator_histogram": {"7": 1},
        },
    }


def _control(**overrides) -> J.JointRow:
    values = dict(
        setting=J.setting_id(P.ATTEN_CODE, P.BANK_CODE),
        atten_code=P.ATTEN_CODE, bank_code=P.BANK_CODE,
        i_rs=6, i_cs=2, corner=P.CORNER_LABEL, ok=True,
        peaking_db=P.ENTRY85_PEAKING_DB,
        f_peak_oct=P.ENTRY85_F_PEAK_OCT,
        g_dc_db=P.ENTRY85_G_DC_DB, noise_mvrms=0.74,
        margins={}, links={"3.0": {"ok": True}, "12.0": {"ok": True}},
    )
    values.update(overrides)
    return J.JointRow(**values)


def _corner_counts() -> dict[str, int]:
    return {f"corner-{index}": 1 for index in range(45)}


def test_registered_geometry_and_artifacts_are_distinct():
    assert P.PROBE_TOP_DB == pytest.approx(7.3)
    assert P.PROBE_MAX_X == pytest.approx(2.31739464996848)
    assert P.EXPECTED_ROWS == 8 * 64 * 45 == 23040
    assert P.RUN_LOG != J.RUN_LOG
    assert P.RESULTS != J.RESULTS


def test_committed_sources_match_the_registered_hashes():
    entry85, baseline_rows, base_u, hashes = P._load_sources()
    assert entry85["summary"]["passed"]
    assert len(baseline_rows) == P.EXPECTED_ROWS
    assert len(base_u) == 7
    assert hashes["entry85_sha256"] == P.ENTRY85_SHA256
    assert hashes["baseline_decoded_sha256"] == P.BASELINE_DECODED_SHA256


def test_score_accepts_all_registered_gates():
    out = P.score(_analysis(), _analysis((11, 15, 16, 16, 16, 16, 16),
                                         scorable_3db=7519,
                                         all_channel=704),
                  [_control()], _corner_counts(), wall_clock_s=60.0)
    assert out["checks"] == {f"Q{i}": True for i in range(1, 8)}
    assert out["recommend_adoption"]


def test_short_coverage_and_long_regression_fail_independently():
    out = P.score(_analysis((15, 14, 16, 16, 16, 16, 16)),
                  _analysis((11, 15, 16, 16, 16, 16, 16),
                            scorable_3db=7519, all_channel=704),
                  [_control()], _corner_counts(), wall_clock_s=60.0)
    assert not out["checks"]["Q3"]
    assert not out["checks"]["Q4"]
    assert not out["recommend_adoption"]


def test_entry85_control_rejects_a_wrong_physical_range_fingerprint():
    out = P.score(_analysis(), _analysis((11, 15, 16, 16, 16, 16, 16),
                                         scorable_3db=7519,
                                         all_channel=704),
                  [_control(g_dc_db=P.ENTRY85_G_DC_DB + 0.1)],
                  _corner_counts(), wall_clock_s=60.0)
    assert not out["checks"]["Q2"]


def test_run_refuses_to_overwrite_result(monkeypatch, tmp_path):
    result = tmp_path / "result.json"
    result.write_text("keep", encoding="utf-8")
    monkeypatch.setattr(P, "RESULTS", result)
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        P.run()


def test_console_print_literals_are_ascii():
    tree = ast.parse(Path(P.__file__).read_text(encoding="utf-8"))
    for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
        if not isinstance(call.func, ast.Name) or call.func.id != "print":
            continue
        for value in (node for arg in call.args for node in ast.walk(arg)
                      if isinstance(node, ast.Constant)
                      and isinstance(node.value, str)):
            assert value.value.isascii(), repr(value.value)
