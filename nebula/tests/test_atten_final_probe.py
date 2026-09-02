"""Fail-capable gates for entry 85's one-point 7.3 dB diagnostic."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from nebula.experiments import exp_atten_final_probe as P


def _source(reason: str = "compression") -> dict:
    return {
        "source": "atten_range_probe_results.json",
        "source_sha256": P.ROOT_SOURCE_SHA256,
        "probe_top_db": 7.0,
        "rows": [{
            "kind": "cs_probe", "corner": P.CORNER_LABEL,
            "bank_code": P.BANK_CODE, "atten_code": P.ATTEN_CODE,
            "request_id": P.REQUEST_ID, "device_ok": True,
            "g_dc_db": -10.708719157811116,
            "links": {
                "3.0": {"ok": False, "reason": reason,
                        "demand_mvpp": 754.0, "limit_mvpp": 731.5},
                "12.0": {"ok": True},
            },
            "requests": [{
                "request_id": P.REQUEST_ID, "scorable": False,
                "compliant": False, "violations": ["unscorable"],
            }],
        }],
    }


def _row(g_dc_db: float = -11.008719157811116,
         compliant: bool = True, long_ok: bool = True,
         noise_mvrms: float = 0.8) -> dict:
    return {
        "kind": "final_probe", "corner": P.CORNER_LABEL,
        "bank_code": P.BANK_CODE, "atten_code": P.ATTEN_CODE,
        "request_id": P.REQUEST_ID, "device_ok": True,
        "old_g_dc_db": -10.708719157811116, "g_dc_db": g_dc_db,
        "noise_mvrms": noise_mvrms,
        "links": {"3.0": {"ok": compliant},
                  "12.0": {"ok": long_ok}},
        "requests": [{
            "request_id": P.REQUEST_ID, "scorable": compliant,
            "compliant": compliant,
            "violations": ([] if compliant else ["unscorable"]),
        }],
    }


def test_source_selects_only_the_registered_compression_row():
    task = P.task_from_source(_source())
    assert (task.corner_label, task.request_id, task.bank_code,
            task.atten_code) == (
                P.CORNER_LABEL, P.REQUEST_ID, P.BANK_CODE, P.ATTEN_CODE)
    assert task.old_g_dc_db == pytest.approx(-10.708719157811116)


def test_source_rejects_a_different_failure_mechanism():
    with pytest.raises(ValueError, match="compression"):
        P.task_from_source(_source(reason="fit_residual"))


def test_analysis_scores_all_six_registered_gates():
    out = P.analyse([_row()], wall_clock_s=1.0)
    assert out["dc_gain_reduction_db"] == pytest.approx(0.3)
    assert out["checks"] == {f"Q{i}": True for i in range(1, 7)}
    assert out["passed"]


def test_gain_movement_and_closure_fail_independently():
    out = P.analyse([_row(g_dc_db=-10.8, compliant=False)],
                    wall_clock_s=1.0)
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
