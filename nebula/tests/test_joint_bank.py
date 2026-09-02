"""Gates for the real attenuator x CTLE-bank PVT/channel sweep."""

from __future__ import annotations

import ast
import json
import math
from dataclasses import asdict
from pathlib import Path

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


def test_duplicate_journal_keys_are_rejected(tmp_path):
    path = tmp_path / "rows.jsonl"
    line = json.dumps(asdict(_row()))
    path.write_text(line + "\n" + line + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        J._load_rows(path)


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
