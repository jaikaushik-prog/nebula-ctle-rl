"""D11 gates: PFET-only library plumbing and the measured PMOS switch."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from nebula.device import attenuator as A
from nebula.device import pdk_trim as PT
from nebula.device import sky130_runner as SR
from nebula.experiments import exp_atten_verify as VERIFY


def test_pfet_variant_is_derived_corner_for_corner_without_mutating_the_base():
    before = PT.CTLE_LIB.read_text(encoding="ascii")
    derived = PT.pfet_library_text()
    assert PT.CTLE_LIB.read_text(encoding="ascii") == before
    assert derived.count("pfet_01v8__mismatch.corner.spice") == 25
    for corner in ("tt", "ss", "ff", "sf", "fs"):
        assert derived.count(f"pfet_01v8__{corner}.pm3.spice") == 5
        nf = (f'sky130_fd_pr__nfet_01v8__{corner}.pm3.spice"')
        pf = (f'sky130_fd_pr__pfet_01v8__{corner}.pm3.spice"')
        lines = derived.splitlines()
        for i, line in enumerate(lines):
            if nf in line:
                assert pf in lines[i + 1]


def test_pfet_derivation_gate_fails_if_a_source_site_is_missing():
    broken = PT.CTLE_LIB.read_text(encoding="ascii").replace(
        "sky130_fd_pr__nfet_01v8__mismatch.corner.spice",
        "missing_mismatch.spice",
        1,
    )
    with pytest.raises(PT.PdkTrimError, match="25 corner and 25 mismatch"):
        PT.pfet_library_text(broken)


def test_every_pfet_section_is_generated_and_contains_only_its_section():
    build = PT.build()
    assert len(build.sections[PT.PFET_STEM]) == 25
    for section in build.sections[PT.PFET_STEM]:
        name = f"sections/{PT.PFET_STEM}__{section}.lib.spice"
        text = build.files[name]
        assert len(re.findall(r"^\.lib\s+", text, flags=re.MULTILINE)) == 1
        assert "sky130_fd_pr__pfet_01v8" in text


def test_runner_selects_pfet_variant_only_when_explicitly_requested():
    ordinary = SR.lib_for_device(
        SR.NFET_01V8, real_passives=True, section="tt")
    switched = SR.lib_for_device(
        SR.NFET_01V8, real_passives=True, section="tt", include_pfet=True)
    assert ordinary == PT.section_library_path("tt", "sky130_ctle")
    assert switched == PT.section_library_path("tt", PT.PFET_STEM)
    assert ordinary != switched


def test_switch_constant_is_the_entry_75_measurement_at_40_um():
    artifact = Path(A.__file__).resolve().parents[1] / "experiments" / (
        "pmos_switch_results.json")
    measured = json.loads(artifact.read_text(encoding="utf-8"))
    ron_w = measured["pmos_ron_times_width_ohm_um"]["mean"]
    assert A.SWITCH_RON_W_OHM_UM == pytest.approx(ron_w, rel=0, abs=0)
    assert A.SWITCH_RON_OHM == pytest.approx(ron_w / 40.0, rel=0, abs=0)


def test_drawn_legs_remove_binary_weighted_pmos_ron():
    unit_total = 1.0 / A.G0_S
    for bit in range(A.N_BITS):
        expected = (unit_total - A.SWITCH_RON_OHM) / (2 ** bit)
        assert A.leg_resistance_ohm(bit) == pytest.approx(expected)


@pytest.mark.parametrize("code", range(A.N_CODES))
def test_pmos_switches_have_binary_width_fingers_polarity_and_bulk(code: int):
    text = A.attenuator_block(code)
    for bit in range(A.N_BITS):
        line = next(s for s in text.splitlines()
                    if s.startswith(f"Xatt_swp{bit} "))
        fields = line.split()
        assert fields[2] == ("0" if code & (1 << bit) else "vdd")
        assert fields[4] == "vdd"
        assert fields[5] == "sky130_fd_pr__pfet_01v8"
        assert f"W={40 * (2 ** bit):g}" in line
        assert f"nf={2 ** bit}" in line


def _verify_rows():
    rows = []
    for code in [None] + list(range(A.N_CODES)):
        rows.append({
            "code": code,
            "device_ok": True,
            "atten_realised_db": 0.0 if code is None else float(code),
            "short_ok": code is not None and code >= 5,
            "long_ok": True,
            "short_limit_mvpp": 1110.0 if code is None or code < 5 else None,
        })
    return rows


def test_switched_reproduction_gate_accepts_the_registered_result_shape():
    rows = _verify_rows()
    got = VERIFY._reproduction(rows, {"rows": _verify_rows()})
    assert got["passed"], got


@pytest.mark.parametrize("damage", ["missing", "limit", "attenuation"])
def test_switched_reproduction_gate_can_fail(damage: str):
    rows, ref = _verify_rows(), {"rows": _verify_rows()}
    if damage == "missing":
        rows = [r for r in rows if r["code"] != 4]
    elif damage == "limit":
        rows[0]["short_limit_mvpp"] = 1000.0
    else:
        rows[3]["atten_realised_db"] += 0.3
    assert not VERIFY._reproduction(rows, ref)["passed"]
