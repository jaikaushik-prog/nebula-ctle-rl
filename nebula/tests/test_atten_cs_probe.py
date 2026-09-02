"""Fail-capable gates for entry 84's three adjacent-Cs measurements."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from nebula.experiments import exp_atten_cs_probe as P


def _source(violations=None) -> dict:
    return {
        "base_u": [0.5] * 7,
        "rows": [{
            "kind": "critical", "corner": "sf/0.95/0C",
            "bank_code": 41, "atten_code": 7,
            "f_peak_hz": 2.05e9,
            "links": {"3.0": {"ok": True}, "12.0": {"ok": True}},
            "requests": [{
                "request_id": 13, "scorable": True, "compliant": False,
                "violations": (["S3_f_peak_match"] if violations is None
                               else violations),
            }],
        }],
    }


def _row(new_f=1.95e9, compliant=True, long_ok=True,
         noise_mvrms=0.8) -> dict:
    return {
        "corner": "sf/0.95/0C", "old_bank_code": 41,
        "bank_code": 42, "atten_code": 7,
        "request_id": 13, "device_ok": True,
        "old_f_peak_hz": 2.05e9, "f_peak_hz": new_f,
        "noise_mvrms": noise_mvrms,
        "links": {"3.0": {"ok": True}, "12.0": {"ok": long_ok}},
        "requests": [{"request_id": 13, "scorable": True,
                      "compliant": compliant,
                      "violations": ([] if compliant else ["S3_f_peak_match"])}],
    }


def test_tasks_move_only_from_c1_to_the_adjacent_c2_code():
    tasks = P.tasks_from_source(_source())
    assert len(tasks) == 1
    task = tasks[0]
    assert (task.corner_label, task.old_bank_code, task.new_bank_code) == (
        "sf/0.95/0C", 41, 42)
    assert (task.i_rs, task.old_i_cs, task.new_i_cs) == (5, 1, 2)
    assert task.request_id == 13


def test_task_selection_rejects_a_non_frequency_failure():
    with pytest.raises(ValueError, match="only S3_f_peak_match"):
        P.tasks_from_source(_source(["S8_eye_h"]))


def test_analysis_scores_all_six_registered_gates():
    out = P.analyse([_row()], expected_rows=1, wall_clock_s=2.0)
    assert out["frequency_lowered"] == 1
    assert out["requests_recovered"] == 1
    assert out["checks"] == {f"Q{i}": True for i in range(1, 7)}
    assert out["passed"]


def test_wrong_frequency_direction_and_request_miss_fail_separately():
    out = P.analyse([_row(new_f=2.06e9, compliant=False)],
                    expected_rows=1, wall_clock_s=2.0)
    assert not out["checks"]["Q2"]
    assert not out["checks"]["Q3"]
    assert not out["passed"]


def test_probe_refuses_to_overwrite_its_artifact(monkeypatch, tmp_path):
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
