"""Gates for the honest programmable-hardware architecture output."""

from __future__ import annotations

import inspect

import pytest


def test_hardware_manifest_separates_measured_switches_from_unbuilt_ones():
    from nebula.rl.hybrid_designer import programmable_hardware_manifest

    manifest = programmable_hardware_manifest([0.5] * 7)
    assert manifest["total_logical_settings"] == 512
    assert len(manifest["attenuator"]["codes"]) == 8
    assert len(manifest["rs_bank"]["codes"]) == 8
    assert len(manifest["cs_bank"]["codes"]) == 8
    assert manifest["attenuator"]["switch_status"] == "netlisted-and-measured"
    assert manifest["rs_bank"]["switch_status"] == "not-netlisted"
    assert manifest["cs_bank"]["switch_status"] == "not-netlisted"


def test_manifest_code_order_matches_the_512_setting_encoding():
    from nebula.rl.hybrid_designer import programmable_hardware_manifest

    manifest = programmable_hardware_manifest([0.5] * 7)
    assert [row["code"] for row in manifest["attenuator"]["codes"]] == list(
        range(8))
    assert [row["code"] for row in manifest["rs_bank"]["codes"]] == list(
        range(8))
    assert [row["code"] for row in manifest["cs_bank"]["codes"]] == list(
        range(8))
    assert manifest["setting_encoding"] == "setting = A*64 + R*8 + C"


def _design() -> dict:
    from nebula.rl.hybrid_designer import programmable_hardware_manifest

    return {
        "method": "rl-hybrid",
        "request": {"peaking_db": 9.0, "f_peak_hz": 1.9e9},
        "search": {
            "atten_code": 1, "bank_code": 40,
            "programmable_hardware": programmable_hardware_manifest(
                [0.5] * 7),
        },
        "verification": {"n_points": 315, "n_pass": 315},
    }


def test_architecture_drawing_states_the_unverified_rs_cs_boundary(tmp_path):
    from nebula.report.programmable_architecture import (
        architecture_model, draw_programmable_architecture,
    )

    model = architecture_model(_design())
    assert model["selected"] == {"atten_code": 1, "rs_code": 5,
                                  "cs_code": 0}
    assert model["rs_cs_switches_verified"] is False
    out = draw_programmable_architecture(
        _design(), tmp_path / "programmable_architecture.png")
    assert out.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert len(out.read_bytes()) > 10_000


def test_architecture_refuses_a_manifest_that_claims_unmeasured_switches():
    from nebula.report.programmable_architecture import architecture_model

    design = _design()
    design["search"]["programmable_hardware"]["rs_bank"][
        "switch_status"] = "netlisted-and-measured"
    with pytest.raises(ValueError, match="Rs|rs|switch"):
        architecture_model(design)


def test_product_writer_emits_the_programmable_architecture():
    import nebula.design as design

    source = inspect.getsource(design.write_outputs)
    assert "draw_programmable_architecture" in source
    assert "programmable_architecture.png" in source
