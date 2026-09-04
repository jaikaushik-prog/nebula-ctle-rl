"""Entry 96 gates for the split-capacitor / floating-resistor bank."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from nebula.device.split_tuning_bank import (
    C_ERROR_LIMIT_F,
    C_SWITCH_WIDTHS_UM,
    G_ERROR_LIMIT_S,
    R_SWITCH_WIDTHS_UM,
    BankRow,
    assess,
    bank_targets,
    build_deck,
    parse_admittance,
)


def test_binary_targets_preserve_endpoints_and_registered_branches():
    t = bank_targets()
    assert t.rs_values_ohm[0] == pytest.approx(70.17347204196405)
    assert t.rs_values_ohm[-1] == pytest.approx(683.8419860404529)
    assert t.cs_values_f[0] == pytest.approx(1.6846486662527978e-12)
    assert t.cs_values_f[-1] == pytest.approx(10e-12)
    assert t.r_branch_total_ohm == pytest.approx(
        (547.3850421801883, 273.69252109009415, 136.84626054504707))
    assert t.c_branch_per_side_f == pytest.approx(
        (2.3758146667849147e-12, 4.7516293335698295e-12,
         9.503258667139659e-12))
    assert R_SWITCH_WIDTHS_UM == (80.0, 160.0, 320.0)
    assert C_SWITCH_WIDTHS_UM == (160.0, 320.0, 640.0)


def test_registered_half_step_limits_are_derived_not_rounded_guesses():
    t = bank_targets()
    assert G_ERROR_LIMIT_S == pytest.approx(0.5 * t.g_step_s)
    assert C_ERROR_LIMIT_F == pytest.approx(0.5 * t.c_step_f)
    assert G_ERROR_LIMIT_S * 1e3 == pytest.approx(0.913434, abs=1e-6)
    assert C_ERROR_LIMIT_F * 1e12 == pytest.approx(0.593954, abs=1e-6)


def test_deck_contains_real_controls_split_caps_and_all_switches():
    text = build_deck(7, 0)  # every switch OFF
    assert "Xctrl_r cp cn 0 sky130_fd_pr__res_high_po" in text
    assert "Xctrl_c cp cn sky130_fd_pr__cap_mim_m3_1" in text
    assert "Xbank_cfixp sp 0" in text and "Xbank_cfixn sn 0" in text
    assert text.count("sky130_fd_pr__nfet_01v8") == 9
    assert "W=640 L=0.15 nf=16" in text
    # OFF means gate at zero, but the transistor remains in the deck.
    assert "Xbank_cswp2" in text and " 0 0 0 sky130_fd_pr__nfet_01v8" in text
    assert "ac lin 3 1.25e+09 2.5e+09" in text


def test_deck_turns_only_requested_binary_bits_on():
    text = build_deck(5, 3)
    # R logical 5 -> conductance mask 2: only resistor bit 1 on.
    assert "Xbank_rsw0" in text and " rmid0 0 sn 0 " in text
    assert "Xbank_rsw1" in text and " rmid1 vdd sn 0 " in text
    assert "Xbank_rsw2" in text and " rmid2 0 sn 0 " in text
    # C code 3 -> bits 0 and 1 on, bit 2 off, on both sides.
    assert "Xbank_cswp0" in text and " cmidp0 vdd 0 0 " in text
    assert "Xbank_cswp1" in text and " cmidp1 vdd 0 0 " in text
    assert "Xbank_cswp2" in text and " cmidp2 0 0 0 " in text


def test_admittance_parser_uses_differential_source_currents():
    f = np.linspace(1.25e9, 2.5e9, 3)
    y_sw = 1 / 200 + 1j * 2 * math.pi * f * 3e-12
    y_ctrl = 1 / 210 + 1j * 2 * math.pi * f * 2.9e-12
    # i(Vp)=-Y and i(Vn)=+Y for a unit differential voltage.
    cols = []
    for current in (-y_sw, y_sw, -y_ctrl, y_ctrl):
        cols.extend((f, current.real, current.imag))
    raw = np.column_stack(cols)
    got = parse_admittance(raw)
    assert got["switched"][0] == pytest.approx(y_sw[0])
    assert got["switched"][1] == pytest.approx(y_sw[-1])
    assert got["control"][1] == pytest.approx(y_ctrl[-1])
    with pytest.raises(ValueError, match="shape"):
        parse_admittance(raw[:, :-1])


def _rows(g_error=0.0, c_error=0.0, reverse_r=False):
    t = bank_targets()
    rows = []
    for rcode in range(8):
        for ccode in range(8):
            g = 1.0 / t.rs_values_ohm[rcode]
            if reverse_r:
                g = 1.0 / t.rs_values_ohm[7 - rcode]
            c = t.cs_values_f[ccode]
            rows.append(BankRow(
                r_code=rcode, c_code=ccode,
                switched_g_s=(g + g_error, g + g_error),
                switched_c_f=(c + c_error, c + c_error),
                control_g_s=(g, g), control_c_f=(c, c)))
    return rows


def test_assessment_passes_only_complete_ordered_half_step_accurate_bank():
    result = assess(_rows(g_error=0.9 * G_ERROR_LIMIT_S,
                          c_error=0.9 * C_ERROR_LIMIT_F))
    assert all(result[f"S{i}"] for i in range(1, 7))
    assert result["overall"]
    assert not assess(_rows(g_error=1.1 * G_ERROR_LIMIT_S))["S4"]
    assert not assess(_rows(c_error=1.1 * C_ERROR_LIMIT_F))["S5"]
    assert not assess(_rows(reverse_r=True))["S2"]
    assert not assess(_rows()[:-1])["S1"]


def test_stage_one_source_is_isolated_from_ctle_link_reward_and_final():
    source = (Path(__file__).parents[1] / "device" /
              "split_tuning_bank.py").read_text(encoding="utf-8").lower()
    for forbidden in ("sky130_runner.run_point", "nebula.link",
                      "reward_v1", "hybrid_designer", "entry89_final"):
        assert forbidden not in source


def test_result_writer_refuses_overwrite(tmp_path):
    from nebula.experiments.exp_split_tuning_bank import write_result

    path = tmp_path / "result.json"
    write_result(path, {"ok": True})
    with pytest.raises(FileExistsError):
        write_result(path, {"ok": False})
