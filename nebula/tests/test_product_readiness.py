"""Fail-capable gates for area/scope and fixed-circuit readiness auditing."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from nebula.report import product_scope as S
from nebula.experiments import exp_product_readiness as A


DEMO = Path("nebula/product_demo/rl_hybrid_9db_1p9ghz")


def deck():
    return (DEMO / "design.cir").read_text(encoding="utf-8")


def test_area_counts_off_switches_and_parallel_resistors_without_nf_double_count():
    result = S.area_inventory(deck())
    by = {r["name"]: r for r in result["components"]}
    assert by["xatt_swp0"]["geometry_um2"] == pytest.approx(40 * .15)
    assert by["xatt_swp2"]["geometry_um2"] == pytest.approx(160 * .15)
    assert by["xatt_rp2"]["geometry_um2"] == pytest.approx(5.73 * 4.97 * 2)
    assert sum(r["kind"] == "mos_gate" for r in by.values()) == 11
    assert result["passive_body_plate_mm2"] > result["legacy_passive_area_mm2"]
    assert result["full_area_mm2"] is None
    assert result["s7_status"] == "NOT_VERIFIED"
    assert result["layout_overhead_mm2"] is None
    assert by["cbyp"]["value"] == pytest.approx(1e-11)
    assert by["cbyp"]["geometry_um2"] is None
    assert by["iref"]["kind"] == "unimplemented_bias_source"
    assert by["clp"]["kind"] == "external_load_assumption"


@pytest.mark.parametrize("change", [
    lambda d: d.replace("w=32.94", "w={UNKNOWN}"),
    lambda d: d.replace("w=32.94", "w=-1"),
    lambda d: d.replace("Xcs   s1 s2 sky130_fd_pr__cap_mim_m3_1", "Xcs s1 s2 mystery_model"),
])
def test_area_refuses_unknown_or_invalid_physical_geometry(change):
    with pytest.raises(ValueError):
        S.area_inventory(change(deck()))


def test_area_inventory_records_unknown_top_level_elements_not_silent_zero():
    result = S.area_inventory(deck().replace(".control", "Rextra outp 0 123\n.control"))
    row = next(r for r in result["components"] if r["name"] == "rextra")
    assert row["geometry_um2"] is None
    assert row["kind"] == "unimplemented_element"


def test_fixed_signature_allows_only_pvt_and_measurement_changes():
    original = deck()
    variant = original.replace(".temp 27.0", ".temp 125.0").replace("VDD=1.8", "VDD=1.71")
    variant = variant.replace("Vid   vid 0 dc 0 ac 1", "Vid vid 0 dc 0 ac 1 sin(0 .2 100meg)")
    assert S.circuit_signature(original) == S.circuit_signature(variant)
    for changed in (original.replace("w=32.94", "w=33.94"),
                    original.replace("att_p0 vdd cm vdd", "att_p0 0 cm vdd")):
        assert S.circuit_signature(original) != S.circuit_signature(changed)


def test_dfe_control_rejects_changed_height_and_nan():
    ideal = SimpleNamespace(eye_h_v=.3, eye_w_ui=.7)
    assert A.control_matches(ideal, .3, .7)
    assert not A.control_matches(ideal, .301, .7)
    assert not A.control_matches(ideal, float("nan"), .7)


def test_incomplete_fixed_grid_cannot_pass():
    with pytest.raises(ValueError, match="membership"):
        A.summarise_fixed([], losses=[7.5], representative_loss=7.5)


def fixed_fixture():
    from nebula.common.types import all_corners
    return [{"corner": A._label(c), "setting": 425, "circuit_signature": "fixed",
             "ok": True, "links": [{"loss_db": 7.5, "model_pass": True,
             "control_pass": True, "failed_specs": [], "unmeasured_specs": [],
             "policies": {name: {"eye_h_v": .3, "eye_w_ui": .7}
                          for name in ("ideal", "none", "misadapted", "quantised")}}]}
            for c in all_corners()]


def test_full_fixed_summary_keeps_area_scope_and_fails_control_or_eye_mutations():
    rows = fixed_fixture()
    summary = A.summarise_fixed(rows, [7.5], 7.5)
    assert summary["n_model_pass"] == 45
    assert summary["dfe_policies"]["none"]["all_eyes_pass"]
    assert not summary["full_product_compliance"]
    rows[0]["links"][0]["policies"]["none"]["eye_h_v"] = .05
    assert not A.summarise_fixed(rows, [7.5], 7.5)["dfe_policies"]["none"]["all_eyes_pass"]
    rows[0]["links"][0]["control_pass"] = False
    summary = A.summarise_fixed(rows, [7.5], 7.5)
    assert not summary["dfe_control_all_pass"]
    assert summary["dfe_policies"]["ideal"]["n_valid_control"] == 44
    assert not summary["dfe_policies"]["ideal"]["all_eyes_pass"]


def test_fixed_summary_rejects_setting_changes_and_missing_channels():
    rows = fixed_fixture()
    rows[0]["setting"] = 426
    with pytest.raises(ValueError, match="changed"):
        A.summarise_fixed(rows, [7.5], 7.5)
    rows[0]["setting"] = 425
    rows[0]["links"] = []
    with pytest.raises(ValueError, match="membership"):
        A.summarise_fixed(rows, [7.5], 7.5)


def test_request_audit_includes_full_range_edges_without_tuning():
    assert len(A.REQUESTS) == 12
    assert (3.0, 1.25e9) in A.REQUESTS
    assert (12.0, 2.5e9) in A.REQUESTS
    assert (9.0, 1.9e9) in A.REQUESTS


def test_model_success_does_not_certify_full_product_or_area():
    from nebula.web.server import present_design
    shown = present_design("x", {"method": "rl-hybrid", "nominal": {
        "ok": True, "meas": {"area_mm2": .002}},
        "request_match": {"request_met": True},
        "verification": {"all_points_pass": True}}, source="live-run")
    assert shown["status_label"] == "MODEL PASS"
    assert shown["implementation_scope"]["full_product_compliance"] is False
    area = next(r for r in shown["specs"] if r["key"] == "area_mm2")
    assert area["label"] == "Partial passive area"
    assert area["status"] is None
    assert area["status_label"] == "Partial only"
    assert "adaptive" in shown["implementation_scope"]["verification_note"].lower()
