"""Fail-capable gates for entry 83's focused 7 dB diagnostic."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from nebula.experiments import exp_atten_range_probe as P


def _diagnosis() -> dict:
    return {
        "source": "joint_bank_run.jsonl.gz",
        "source_decoded_sha256": "ABC123",
        "n_unserved_corner_requests": 3,
        "unserved": [
            {"corner": "sf/0.95/0C", "request_id": 8,
             "target_peaking_db": 8.0, "target_f_peak_hz": 1.4e9,
             "least_extra_setting": 483, "least_extra_atten_code": 7},
            {"corner": "sf/0.95/0C", "request_id": 12,
             "target_peaking_db": 10.0, "target_f_peak_hz": 1.4e9,
             "least_extra_setting": 491, "least_extra_atten_code": 7},
            {"corner": "sf/0.95/0C", "request_id": 13,
             "target_peaking_db": 10.0, "target_f_peak_hz": 1.6e9,
             "least_extra_setting": 491, "least_extra_atten_code": 7},
        ],
    }


def _critical(bank_code: int, request_ids: list[int], recovered=True,
              long_ok=True) -> dict:
    return {
        "kind": "critical", "corner": "sf/0.95/0C",
        "bank_code": bank_code, "atten_code": 7, "device_ok": True,
        "noise_mvrms": 0.8,
        "links": {"3.0": {"ok": True}, "12.0": {"ok": long_ok}},
        "requests": [
            {"request_id": i, "scorable": True, "compliant": recovered,
             "violations": ([] if recovered else ["S8_eye_h"])}
            for i in request_ids
        ],
    }


def _control(code: int, g_dc_db: float, noise_mvrms: float = 0.8) -> dict:
    return {
        "kind": "control", "corner": "tt/1.00/27C", "bank_code": 35,
        "atten_code": code, "device_ok": True, "g_dc_db": g_dc_db,
        "noise_mvrms": noise_mvrms,
        "links": {"3.0": {"ok": True}, "12.0": {"ok": True}},
        "requests": [],
    }


def test_diagnosis_collapses_requests_to_unique_physical_points():
    tasks = P.critical_tasks(_diagnosis())
    assert [(t.corner_label, t.setting, t.request_ids) for t in tasks] == [
        ("sf/0.95/0C", 483, (8,)),
        ("sf/0.95/0C", 491, (12, 13)),
    ]
    assert all(t.atten_code == 7 for t in tasks)


def test_request_ids_may_repeat_at_different_corners():
    diagnosis = _diagnosis()
    diagnosis["unserved"].append({
        "corner": "ff/0.95/0C", "request_id": 12,
        "target_peaking_db": 10.0, "target_f_peak_hz": 1.4e9,
        "least_extra_setting": 490, "least_extra_atten_code": 7,
    })
    tasks = P.critical_tasks(diagnosis)
    assert len(tasks) == 3
    assert sum(len(task.request_ids) for task in tasks) == 4


def test_analysis_scores_every_registered_gate():
    rows = [
        _critical(35, [8]), _critical(43, [12, 13]),
        _control(0, -1.0), _control(7, -8.0),
    ]
    out = P.analyse(rows, expected_critical=2, expected_requests=3,
                    wall_clock_s=12.0)
    assert out["membership_ok"]
    assert out["realised_top_attenuation_db"] == pytest.approx(7.0)
    assert out["n_recovered_requests"] == 3
    assert out["n_long_channel_scorable"] == 2
    assert out["checks"] == {f"Q{i}": True for i in range(1, 7)}
    assert out["passed"]


def test_one_failed_request_or_long_channel_fails_the_probe():
    rows = [
        _critical(35, [8], recovered=False),
        _critical(43, [12, 13], long_ok=False),
        _control(0, -1.0), _control(7, -8.0),
    ]
    out = P.analyse(rows, expected_critical=2, expected_requests=3,
                    wall_clock_s=12.0)
    assert not out["checks"]["Q4"]
    assert not out["checks"]["Q5"]
    assert not out["passed"]


def test_probe_refuses_to_overwrite_its_result(monkeypatch, tmp_path):
    result = tmp_path / "probe.json"
    result.write_text("preserve me", encoding="utf-8")
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
