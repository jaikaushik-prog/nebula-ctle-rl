"""Fail-capable gates for the local evidence-grounded web interface."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from nebula.web.server import WORKER_LIMIT, NebulaWebApp, present_design


DEMO = Path("nebula/product_demo/rl_hybrid_9db_1p9ghz")


def _design(*, request_met=True, verified=True):
    return {
        "request": {"peaking_db": 9.0, "f_peak_hz": 1.9e9,
                    "f_peak_ghz": 1.9},
        "method": "rl-hybrid",
        "search": {"programmable_hardware": {
            "attenuator": {"switch_status": "netlisted-and-measured"},
            "rs_bank": {"switch_status": "not-netlisted"},
            "cs_bank": {"switch_status": "not-netlisted"},
        }},
        "nominal": {"ok": True, "verdict": "ok", "design_id": "abc",
                    "meas": {"peaking_db": 8.9, "_f_peak_ghz": 1.88,
                             "nyq_boost_db": 6.0, "_noise_mv": 0.4,
                             "_power_mw": 6.0, "hd3_nyq_dbc": -44.0,
                             "area_mm2": 0.002, "eye_h_v": 0.3,
                             "eye_w_ui": 0.8},
                    "params": {"rs": 350.0, "cs": 2e-12}},
        "request_match": {"request_met": request_met},
        "verification": {"all_points_pass": verified, "n_points": 1,
                         "n_pass": int(verified),
                         "n_failed": int(not verified),
                         "per_condition": [{"channel_loss_db": 7.5,
                                            "corner": "tt/1.00/27C",
                                            "compliant": verified,
                                            "eye_area": 0.24}]},
    }


def test_presentation_keeps_missing_values_null_and_reports_hardware_boundary():
    shown = present_design("x", _design(), source="live-run")
    assert shown["status"] == "pass"
    assert shown["hardware"]["programmable_selector_complete"] is False
    assert shown["hardware"]["incomplete_items"] == [
        "Rs selector switches", "Cs selector switches"]
    assert next(row for row in shown["specs"]
                if row["label"] == "Input noise")["measured"] == 0.4
    # No invented fallback when a field is absent.
    assert shown["nominal"]["reward"] is None


@pytest.mark.parametrize("request_met,verified,fragment", [
    (False, True, "requested target"),
    (True, False, "1 of 1"),
])
def test_failures_are_explained_not_hidden(request_met, verified, fragment):
    shown = present_design(
        "x", _design(request_met=request_met, verified=verified),
        source="live-run")
    assert shown["status"] == "fail"
    assert fragment in " ".join(shown["failure_reasons"])


def test_judge_mode_is_the_real_preverified_artifact_not_a_ui_fixture(tmp_path):
    app = NebulaWebApp(run_root=tmp_path, demo_dir=DEMO)
    try:
        shown = app.demo()
        raw = json.loads((DEMO / "design.json").read_text(encoding="utf-8"))
        assert shown["cached"] is True
        assert shown["source"] == "preverified-demo"
        assert shown["verification"]["n_points"] == raw["verification"]["n_points"] == 315
        assert len(shown["verification"]["conditions"]) == 315
        assert shown["hardware"]["programmable_selector_complete"] is False
    finally:
        app.close()


def test_evidence_bundle_contains_real_files_at_zip_root(tmp_path):
    app = NebulaWebApp(run_root=tmp_path, demo_dir=DEMO)
    try:
        app.demo()
        payload = app.evidence_zip("judge-demo")
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = set(zf.namelist())
        assert {"design.json", "design.cir", "design_schematic.png"} <= names
        assert all("/" not in name and "\\" not in name for name in names)
    finally:
        app.close()


def test_completed_designs_are_available_to_a_fresh_browser_view(tmp_path):
    app = NebulaWebApp(run_root=tmp_path, demo_dir=DEMO)
    try:
        demo = app.demo()
        assert app.get_design("judge-demo") == demo
        assert app.get_design("does-not-exist") is None
        assert app.design_list()[0]["id"] == "judge-demo"
    finally:
        app.close()


def test_channel_upload_rejects_ambiguous_or_empty_input_before_a_worker_runs(tmp_path):
    app = NebulaWebApp(run_root=tmp_path, demo_dir=DEMO)
    try:
        with pytest.raises(ValueError, match="Touchstone"):
            app.start_channel("notes.txt", b"data", (1, 3))
        with pytest.raises(ValueError, match="empty"):
            app.start_channel("board.s4p", b"", (1, 3))
        assert not app.jobs
    finally:
        app.close()


def test_interface_has_no_algorithm_benchmark_leaderboard():
    static = Path("nebula/web/static")
    text = "\n".join(path.read_text(encoding="utf-8").lower()
                       for path in static.glob("*.*") if path.is_file())
    for forbidden in ("cma-es", "cmaes", "random search", "grid search",
                      "benchmark leaderboard"):
        assert forbidden not in text


def test_single_worker_is_an_explicit_responsiveness_guard(tmp_path):
    app = NebulaWebApp(run_root=tmp_path, demo_dir=DEMO)
    try:
        assert WORKER_LIMIT == 1
        assert app.executor._max_workers == WORKER_LIMIT
    finally:
        app.close()
