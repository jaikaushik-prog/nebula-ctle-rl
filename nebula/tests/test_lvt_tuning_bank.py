"""Entry 97 gates for the safe LVT capacitor-selector screen."""

from __future__ import annotations

from pathlib import Path

import pytest

from nebula.device.lvt_tuning_bank import (
    BASE_C_WIDTHS_UM,
    C_ERROR_LIMIT_F,
    G_ERROR_LIMIT_S,
    LVT_NFET,
    WIDTH_SCALES,
    LvtBankRow,
    assess,
    build_scale_deck,
)


def test_registered_device_scales_and_limits_are_frozen():
    assert LVT_NFET == "sky130_fd_pr__nfet_01v8_lvt"
    assert WIDTH_SCALES == (1, 2, 4, 8, 16, 32)
    assert BASE_C_WIDTHS_UM == (160.0, 320.0, 640.0)
    assert G_ERROR_LIMIT_S == pytest.approx(0.0009134338015678002)
    assert C_ERROR_LIMIT_F == pytest.approx(0.5939536666962287e-12)


def test_scale_deck_contains_all_codes_real_controls_and_safe_lvt_switches():
    text = build_scale_deck(32)
    assert "sky130.lib.spice" in text
    assert text.count("* bank R") == 64
    assert text.count("* Same-deck separately drawn R || C control.") == 64
    assert text.count("sky130_fd_pr__nfet_01v8_lvt W=") == 64 * 6
    assert text.count("sky130_fd_pr__nfet_01v8 W=") == 64 * 3
    assert "sky130_fd_pr__nfet_01v8_lvt W=20480 L=0.15 nf=512" in text
    assert "Vdd vdd 0 1.8" in text
    assert "1.81" not in text and "boost" not in text.lower()
    assert text.count("wrdata adm_r") == 64


def test_scale_deck_keeps_off_devices_and_rejects_unregistered_scale():
    text = build_scale_deck(1)
    # R7/C0 has all six LVT capacitor selectors present and OFF at gate zero.
    block = text.split("* bank R7 C0", 1)[1].split("* bank R7 C1", 1)[0]
    assert block.count("sky130_fd_pr__nfet_01v8_lvt") == 6
    assert "Xb_r7_c0_cswp2" in block and " 0 0 0 sky130_fd_pr__nfet_01v8_lvt" in block
    with pytest.raises(ValueError, match="registered"):
        build_scale_deck(3)


def _rows(g_errors=None, c_errors=None):
    from nebula.device.split_tuning_bank import bank_targets

    g_errors = g_errors or {s: 0.5 * G_ERROR_LIMIT_S for s in WIDTH_SCALES}
    c_errors = c_errors or {s: 0.5 * C_ERROR_LIMIT_F for s in WIDTH_SCALES}
    t = bank_targets()
    rows = []
    for scale in WIDTH_SCALES:
        for rcode in range(8):
            for ccode in range(8):
                g = 1.0 / t.rs_values_ohm[rcode]
                c = t.cs_values_f[ccode]
                rows.append(LvtBankRow(
                    scale=scale, r_code=rcode, c_code=ccode,
                    switched_g_s=(g + g_errors[scale],) * 2,
                    switched_c_f=(c + c_errors[scale],) * 2,
                    control_g_s=(g,) * 2, control_c_f=(c,) * 2,
                ))
    return rows


def test_assessment_selects_smallest_simultaneous_pass():
    g = {1: 2 * G_ERROR_LIMIT_S, 2: 1.1 * G_ERROR_LIMIT_S,
         4: 0.9 * G_ERROR_LIMIT_S, 8: 0.8 * G_ERROR_LIMIT_S,
         16: 0.7 * G_ERROR_LIMIT_S, 32: 0.6 * G_ERROR_LIMIT_S}
    result = assess(_rows(g_errors=g))
    assert result["L1_integrity"] and result["L2_ordering"]
    assert result["L3_any_loss_pass"] and result["L4_any_cap_pass"]
    assert result["L5_selection"] and result["selected_scale"] == 4
    assert result["L6_isolation_safety"] and result["overall"]


def test_assessment_rejects_disjoint_loss_and_capacitance_passes():
    g = {s: (2 if s <= 4 else 0.5) * G_ERROR_LIMIT_S
         for s in WIDTH_SCALES}
    c = {s: (0.5 if s <= 4 else 2) * C_ERROR_LIMIT_F
         for s in WIDTH_SCALES}
    result = assess(_rows(g_errors=g, c_errors=c))
    assert result["L3_any_loss_pass"]
    assert result["L4_any_cap_pass"]
    assert not result["L5_selection"]
    assert result["selected_scale"] is None
    assert not result["overall"]
    assert not assess(_rows()[:-1])["L1_integrity"]


def test_stage_a_source_is_isolated_from_ctle_link_reward_and_final():
    source = (Path(__file__).parents[1] / "device" /
              "lvt_tuning_bank.py").read_text(encoding="utf-8").lower()
    for forbidden in ("sky130_runner.run_point", "nebula.link",
                      "reward_v1", "hybrid_designer", "entry89_final",
                      "vdd_boost", "gate_boost"):
        assert forbidden not in source


def test_result_writer_refuses_overwrite(tmp_path):
    from nebula.experiments.exp_lvt_tuning_bank import write_result

    path = tmp_path / "result.json"
    write_result(path, {"ok": True})
    with pytest.raises(FileExistsError):
        write_result(path, {"ok": False})
