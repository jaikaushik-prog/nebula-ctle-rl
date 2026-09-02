"""Gates for the real attenuator x CTLE-bank PVT/channel sweep."""

from __future__ import annotations

import ast
import gzip
import json
import math
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest

import nebula.rl.reward_v1 as R
from nebula.common.types import Corner
from nebula.device import attenuator as AT
from nebula.experiments import exp_joint_bank as J
from nebula.experiments.adaptive_screen import _attenuation_run_args
from nebula.experiments.exp_bank_sweep import REQUEST_ROWS, SPECS


def _row(**overrides) -> J.JointRow:
    margins = {name: 1.0 for name in SPECS
               if name not in REQUEST_ROWS and not name.startswith("S8_")}
    values = dict(
        setting=J.setting_id(5, 35), atten_code=5, bank_code=35,
        i_rs=4, i_cs=3, corner="tt/1.00/27C", ok=True, reason=None,
        peaking_db=9.0, f_peak_oct=math.log2(1.9e9 / 2.5e9),
        margins=margins, eye_h_v=0.3, eye_w_ui=0.7, power_w=5e-3,
        hd3_nyq_dbc=-40.0,
        links={"3.0": {"ok": True, "eye_h_v": 0.3,
                       "eye_w_ui": 0.7}},
    )
    values.update(overrides)
    return J.JointRow(**values)


@pytest.mark.parametrize("atten,bank", [(0, 0), (0, 63), (5, 35), (7, 63)])
def test_joint_setting_number_round_trips(atten, bank):
    assert J.split_setting(J.setting_id(atten, bank)) == (atten, bank)


def test_g140_swing_range_scales_with_the_real_attenuation():
    assert _attenuation_run_args(None) == {"vid_max": 0.8,
                                           "atten_code": None}
    args = _attenuation_run_args(7)
    assert args["atten_code"] == 7
    assert args["vid_max"] == pytest.approx(0.8 / AT.attenuation(7))

    candidate_x = 10.0 ** (7.0 / 20.0)
    custom = _attenuation_run_args(7, atten_max_x=candidate_x)
    assert custom == {
        "vid_max": pytest.approx(
            0.8 / AT.attenuation(7, atten_max_x=candidate_x)),
        "atten_code": 7,
        "atten_max_x": candidate_x,
    }


def test_channel_rescore_replaces_both_eye_rows_and_request_rows():
    margins = J.margins_at(_row(), 3.0, 1.9e9, 9.0)
    assert margins["S8_eye_h"] == pytest.approx(0.2)
    assert margins["S8_eye_w"] == pytest.approx(0.3)
    assert all(name in margins for name in SPECS)
    assert J.is_compliant(_row(), 3.0, 1.9e9, 9.0)


def test_an_unscorable_channel_cannot_be_called_compliant():
    row = _row(links={"3.0": {"ok": False, "reason": "compression"}})
    assert J.margins_at(row, 3.0, 1.9e9, 9.0) is None
    assert not J.is_compliant(row, 3.0, 1.9e9, 9.0)


def test_compression_reason_is_compacted_without_losing_the_numbers():
    compact = J._compact_link({
        "ok": False, "eye_h_v": None, "eye_w_ui": None,
        "reason": "output swing 1234.5 mVpp exceeds the linear limit 987.6 mVpp (x)",
    })
    assert compact == {"ok": False, "reason": "compression",
                       "demand_mvpp": 1234.5, "limit_mvpp": 987.6}


def test_fresh_sweep_refuses_to_overwrite_a_journal(tmp_path):
    path = tmp_path / "rows.jsonl"
    path.write_text("already here\n", encoding="utf-8")
    with pytest.raises(FileExistsError, match="use --resume"):
        J.sweep([0.5] * 7, corners=[Corner("tt", 1.0, 27.0)],
                atten_codes=[0], log_path=path)


def test_resume_rejects_a_truncated_or_invalid_row(tmp_path):
    path = tmp_path / "rows.jsonl"
    path.write_text('{"setting":', encoding="utf-8")
    with pytest.raises(ValueError, match="invalid journal row"):
        J.sweep([0.5] * 7, corners=[Corner("tt", 1.0, 27.0)],
                atten_codes=[0], log_path=path, resume=True)


def test_sweep_journals_every_member_and_resume_runs_nothing(monkeypatch,
                                                              tmp_path):
    calls = []

    def fake(task):
        bank_code, st, atten_code, corner = task
        calls.append((bank_code, atten_code, corner.process))
        return _row(setting=J.setting_id(atten_code, bank_code),
                    atten_code=atten_code, bank_code=bank_code,
                    i_rs=st.i_rs, i_cs=st.i_cs,
                    corner=J._corner_label(corner))

    monkeypatch.setattr(J, "_measure", fake)
    path = tmp_path / "rows.jsonl"
    corner = Corner("tt", 1.0, 27.0)
    rows = J.sweep([0.5] * 7, corners=[corner], atten_codes=[0],
                   log_path=path)
    assert len(rows) == J.N_BANK_CODES == len(calls)
    assert len(path.read_text(encoding="utf-8").splitlines()) == len(rows)
    calls.clear()
    resumed = J.sweep([0.5] * 7, corners=[corner], atten_codes=[0],
                      log_path=path, resume=True)
    assert len(resumed) == len(rows)
    assert calls == []


def test_custom_range_is_part_of_every_physical_task():
    corner = Corner("tt", 1.0, 27.0)
    tasks = J._tasks([0.5] * 7, [corner], [0, 7], atten_max_x=2.3)
    assert len(tasks) == 2 * J.N_BANK_CODES
    assert all(task[4] == pytest.approx(2.3) for task in tasks)


def test_custom_range_reaches_measurement_and_records_control_fields(monkeypatch):
    captured = {}
    point = SimpleNamespace(
        ok=True,
        links_by_loss={loss: {"ok": True, "eye_h_v": 0.3,
                              "eye_w_ui": 0.7} for loss in J.LOSSES_DB},
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
    row = J._measure((0, st, 7, Corner("tt", 1.0, 27.0), 2.3))
    assert captured["atten_max_x"] == pytest.approx(2.3)
    assert row.g_dc_db == pytest.approx(-11.0)
    assert row.noise_mvrms == pytest.approx(0.7)


def test_duplicate_journal_keys_are_rejected(tmp_path):
    path = tmp_path / "rows.jsonl"
    line = json.dumps(asdict(_row()))
    path.write_text(line + "\n" + line + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        J._load_rows(path)


def test_completed_journal_can_be_a_byte_preserving_gzip(tmp_path):
    path = tmp_path / "rows.jsonl.gz"
    expected = _row()
    with gzip.open(path, "wt", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(asdict(expected)) + "\n")

    assert J._load_rows(path) == [expected]


def test_diagnosis_separates_request_miss_from_compression_headroom():
    target_hz, target_db = 1.9e9, 9.0
    compressed = _row(
        setting=J.setting_id(7, 35), atten_code=7,
        links={"3.0": {"ok": False, "reason": "compression",
                       "demand_mvpp": 110.0, "limit_mvpp": 100.0}},
    )
    shape_miss = _row(
        setting=J.setting_id(7, 36), atten_code=7, bank_code=36,
        peaking_db=6.0,
        links={"3.0": {"ok": True, "eye_h_v": 0.3,
                       "eye_w_ui": 0.7}},
    )

    out = J.diagnose([compressed, shape_miss], loss_db=3.0,
                     requests=[(target_db, target_hz)])

    assert out["n_unserved_corner_requests"] == 1
    assert out["best_scorable_single_violation_histogram"] == {
        "S3_peaking_match": 1}
    assert out["n_with_shape_compliant_compressed_candidate"] == 1
    assert out["n_min_extra_candidate_at_max_attenuator"] == 1
    row = out["unserved"][0]
    assert row["best_scorable_violations"] == ["S3_peaking_match"]
    assert row["shape_compliant_compressed_candidates"] == 1
    assert row["least_extra_attenuation_db"] == pytest.approx(
        20.0 * math.log10(1.1))


def test_resumed_run_labels_segment_cost_instead_of_total_cost(monkeypatch,
                                                                 tmp_path):
    """A resumed timer must not masquerade as the cost of the whole table."""
    from nebula.experiments import exp_tuning_bank as T

    old = [
        _row(setting=0, atten_code=0, bank_code=0, i_rs=0, i_cs=0),
        _row(setting=1, atten_code=0, bank_code=1, i_rs=0, i_cs=1),
    ]
    new = _row(setting=2, atten_code=0, bank_code=2, i_rs=0, i_cs=2)
    log = tmp_path / "rows.jsonl"
    log.write_text("".join(json.dumps(asdict(row)) + "\n" for row in old),
                   encoding="utf-8")
    monkeypatch.setattr(J, "RUN_LOG", log)
    monkeypatch.setattr(J, "RESULTS", tmp_path / "results.json")
    monkeypatch.setattr(T, "_base_from_artifacts", lambda: [0.5] * 7)
    monkeypatch.setattr(
        J, "sweep",
        lambda base_u, workers, resume: old + [new],
    )
    monkeypatch.setattr(J, "analyse", lambda rows: {"membership_ok": True})

    out = J.run(workers=3, resume=True)

    assert out["resumed"] is True
    assert out["rows_before_segment"] == 2
    assert out["spice_invocations_this_segment"] == 1
    assert out["wall_clock_scope"] == "resume segment only"


def test_console_print_literals_are_ascii():
    path = Path(J.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for call in (n for n in ast.walk(tree) if isinstance(n, ast.Call)):
        if not isinstance(call.func, ast.Name) or call.func.id != "print":
            continue
        for constant in (n for arg in call.args for n in ast.walk(arg)
                         if isinstance(n, ast.Constant)
                         and isinstance(n.value, str)):
            assert constant.value.isascii(), repr(constant.value)
