"""Gates for entry 76's before/after PFET library-cost instrument."""

from pathlib import Path

import pytest

from nebula.experiments import lib_cost


def _section(corner: str = "tt") -> str:
    root = "C:/Users/DELL/sky130A/libs.ref/sky130_fd_pr/spice"
    return (
        ".lib tt_typical\n"
        f'.include "{root}/sky130_fd_pr__nfet_01v8__{corner}.pm3.spice"\n'
        f'.include "{root}/sky130_fd_pr__nfet_01v8__mismatch.corner.spice"\n'
        ".endl tt_typical\n"
    )


def test_candidate_adds_pfet_corner_for_corner_after_each_nfet_include():
    got = lib_cost._with_pfet_includes(_section("ss"))
    lines = got.splitlines()
    nfet_corner = next(i for i, s in enumerate(lines) if "nfet_01v8__ss.pm3" in s)
    nfet_mismatch = next(i for i, s in enumerate(lines) if "nfet_01v8__mismatch" in s)
    assert "pfet_01v8__ss.pm3" in lines[nfet_corner + 1]
    assert "pfet_01v8__mismatch" in lines[nfet_mismatch + 1]
    assert got.count("pfet_01v8__ss.pm3") == 1
    assert got.count("pfet_01v8__mismatch") == 1


def test_candidate_gate_fails_loudly_if_an_expected_nfet_site_is_missing():
    broken = _section().replace(
        '.include "C:/Users/DELL/sky130A/libs.ref/sky130_fd_pr/spice/'
        'sky130_fd_pr__nfet_01v8__mismatch.corner.spice"\n',
        "",
    )
    with pytest.raises(ValueError, match="one corner and one mismatch"):
        lib_cost._with_pfet_includes(broken)


def test_pfet_decision_requires_both_absolute_and_relative_limits():
    assert lib_cost._pfet_cost_decision(0.200, 0.209)["immaterial"]
    assert not lib_cost._pfet_cost_decision(0.200, 0.211)["immaterial"]
    assert not lib_cost._pfet_cost_decision(0.050, 0.059)["immaterial"]


def test_pfet_measurement_arms_are_exactly_the_registered_pair():
    assert lib_cost.PFET_ARMS == ("current_section", "pfet_section")


def test_staged_section_carries_every_relative_include(tmp_path: Path):
    source_root = tmp_path / "source"
    source_sections = source_root / "sections"
    source_sections.mkdir(parents=True)
    (source_root / "leaf.spice").write_text(".param kept=1\n", encoding="ascii")
    (source_root / "trim.spice").write_text(
        '.include "leaf.spice"\n', encoding="ascii")
    source = source_sections / "sky130_ctle__tt.lib.spice"
    source.write_text(
        '.lib tt\n.include "../trim.spice"\n.endl tt\n', encoding="ascii")
    destination = tmp_path / "candidate" / "sections"

    lib_cost._stage_section_tree(source, destination, source.read_text())

    assert (destination / source.name).exists()
    assert (destination.parent / "trim.spice").exists()
    assert (destination.parent / "leaf.spice").read_text(encoding="ascii") == (
        ".param kept=1\n")
