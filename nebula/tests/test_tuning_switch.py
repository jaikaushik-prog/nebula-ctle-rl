"""Entry 95 gates for the real source-degeneration selector transistor."""

from __future__ import annotations

import math

import numpy as np
import pytest

from nebula.common.types import all_corners
from nebula.device.tuning_switch import (
    BIASES_V,
    FREQS_HZ,
    WIDTHS_UM,
    SwitchRow,
    assess,
    build_deck,
    corner_label,
    finger_count,
    parse_ac_table,
    parse_dc_table,
)


def test_registered_probe_axes_are_frozen():
    assert WIDTHS_UM == (40.0, 80.0, 160.0, 320.0, 640.0)
    assert BIASES_V == (0.44, 0.50, 0.55)
    assert FREQS_HZ == (1.25e9, 2.5e9)
    assert len(WIDTHS_UM) * len(BIASES_V) * 45 == 675


def test_fingers_keep_every_device_at_40_um_per_finger():
    assert [finger_count(w) for w in WIDTHS_UM] == [1, 2, 4, 8, 16]
    with pytest.raises(ValueError):
        finger_count(60.0)


def test_deck_uses_real_bias_body_and_both_switch_states():
    text, names = build_deck("tt", 1.8, 27.0)
    assert len(names) == len(WIDTHS_UM) * len(BIASES_V)
    assert '.lib "' in text and '" tt' in text
    assert "Vgate_on gate_on 0 1.8" in text
    assert "sky130_fd_pr__nfet_01v8 W=640 L=0.15 nf=16" in text
    assert "Xon_" in text and "Xoff_" in text
    # Fourth MOS terminal is ground: the real p-substrate connection.
    assert " gate_on " in text and " 0 sky130_fd_pr__nfet_01v8" in text
    assert "dc Vdelta 0 0.05 0.001" in text
    # `lin 2` emitted one row; `lin 3` gives low/mid/high and we use endpoints.
    assert "ac lin 3 1.25e+09 2.5e+09" in text
    assert "wrdata ron.txt" in text
    assert "wrdata zon.txt" in text
    assert "wrdata coff.txt" in text


def test_dc_parser_fits_dv_di_and_checks_every_x_axis():
    x = np.linspace(0.0, 0.05, 51)
    # wrdata real format is (x, y) for each requested vector.
    raw = np.column_stack((x, -x / 10.0, x, -x / 20.0))
    got = parse_dc_table(raw, ("a", "b"))
    assert got["a"] == pytest.approx(10.0)
    assert got["b"] == pytest.approx(20.0)
    broken = raw.copy()
    broken[:, 2] += 1.0
    with pytest.raises(ValueError, match="x-axis"):
        parse_dc_table(broken, ("a", "b"))


def test_ac_parser_reads_x_real_imag_triples_not_magnitude_columns():
    f = np.linspace(FREQS_HZ[0], FREQS_HZ[1], 3)
    # Two vectors; current a = j*w*20 fF, b = 1/(5+j/(w*1pF)).
    ia = 1j * 2.0 * math.pi * f * 20e-15
    zb = 5.0 - 1j / (2.0 * math.pi * f * 1e-12)
    ib = 1.0 / zb
    raw = np.column_stack((f, ia.real, ia.imag,
                           f, ib.real, ib.imag))
    got = parse_ac_table(raw, ("a", "b"))
    assert got["a"][0] == pytest.approx(ia[0])
    assert got["b"][1] == pytest.approx(ib[-1])
    with pytest.raises(ValueError, match="shape"):
        parse_ac_table(raw[:, :-1], ("a", "b"))


def _rows(ron_by_w, coff_by_w):
    out = []
    for corner in all_corners():
        for bias in BIASES_V:
            for width in WIDTHS_UM:
                ron = ron_by_w[width]
                coff = coff_by_w[width]
                out.append(SwitchRow(
                    corner=corner_label(corner.process, corner.vdd_scale,
                                        corner.temp_c),
                    process=corner.process, vdd_scale=corner.vdd_scale,
                    temp_c=corner.temp_c, vdd_v=1.8 * corner.vdd_scale,
                    source_v=bias, width_um=width,
                    nf=finger_count(width), ron_ohm=ron,
                    on_z_ohm=(ron, ron), off_cap_f=(coff, coff)))
    return out


def test_assessment_chooses_smallest_measured_passing_width():
    rows = _rows(
        {40.0: 20.0, 80.0: 10.0, 160.0: 5.0, 320.0: 1.9, 640.0: 0.9},
        {40.0: 10e-15, 80.0: 20e-15, 160.0: 40e-15,
         320.0: 100e-15, 640.0: 210e-15})
    result = assess(rows)
    assert result["P1_integrity"]
    assert result["P2_scaling"]
    assert result["one_hot"]["selected_width_um"] is None
    assert result["binary"]["selected_width_um"] == 160.0
    assert not result["P3_one_hot"]
    assert result["P4_binary"]


def test_assessment_rejects_nonmonotonic_or_incomplete_evidence():
    rows = _rows(
        {40.0: 20.0, 80.0: 21.0, 160.0: 5.0, 320.0: 2.0, 640.0: 1.0},
        {40.0: 10e-15, 80.0: 20e-15, 160.0: 40e-15,
         320.0: 80e-15, 640.0: 160e-15})
    assert not assess(rows)["P2_scaling"]
    assert not assess(rows[:-1])["P1_integrity"]


def test_result_writer_refuses_to_overwrite_evidence(tmp_path):
    from nebula.experiments.exp_tuning_switch import write_result

    path = tmp_path / "result.json"
    write_result(path, {"ok": True})
    with pytest.raises(FileExistsError):
        write_result(path, {"ok": False})


def test_result_payload_recomputes_the_assessment(monkeypatch):
    from nebula.experiments import exp_tuning_switch as E

    rows = _rows(
        {40.0: 20.0, 80.0: 10.0, 160.0: 5.0, 320.0: 1.9, 640.0: 0.9},
        {40.0: 10e-15, 80.0: 20e-15, 160.0: 40e-15,
         320.0: 100e-15, 640.0: 210e-15})
    assessment = assess(rows)
    monkeypatch.setattr(E, "_git_head", lambda: "a" * 40)
    payload = E.result_payload(rows, assessment)
    assert payload["n_rows"] == 675
    assert len(payload["rows_sha256"]) == 64
    assert payload["preregistration_commit"] == "a" * 40
    broken = dict(assessment, P1_integrity=False)
    with pytest.raises(ValueError, match="P1_integrity"):
        E.result_payload(rows, broken)
