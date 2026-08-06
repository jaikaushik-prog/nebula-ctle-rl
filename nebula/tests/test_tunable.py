"""
Tests for the tunable sweep — `run_tunable_sweep` and `experiments/tunable.py`.

THE ONE THAT MATTERS IS `test_alter_on_rs_cs_is_bit_identical_to_fresh_parse`.
G35 measured `alter` to be **silently wrong** for subckt-wrapped device
geometry: it writes the `w` instance parameter, leaves every geometry-derived
parasitic at its old value, and returns plausible numbers up to 24 % off with
no error. It recorded that ideal R/C/I elements are fine. The tunable sweep
leans on that 67 times per process, so "recorded" is not good enough — this
file holds it to **rel=0, abs=0** against fresh-parse ground truth. If that
test goes red, every number the tunable experiment produces is fiction.

Everything else here runs without a simulator.
"""

from __future__ import annotations

import shutil

import pytest

from nebula.common.types import Corner
from nebula.device.sky130_runner import (
    _CONTROL_SINGLE,
    _NETLIST,
    _TOPOLOGY,
    SizingPoint,
    Sky130Point,
    TunableSetting,
    run_point,
    run_tunable_sweep,
)
from nebula.device.tail import TailDevice
from nebula.experiments.s3_yield import PROPOSED_BOX
from nebula.experiments.tunable import (
    N_CS,
    N_RS,
    S13_FIXED_ALL,
    S13_FIXED_ANY_LOAD,
    S13_POPULATION,
    PointResult,
    adaptation_class,
    dac_spec,
    own_setting_index,
    required_settings,
    tuning_grid,
)


def _has_sim() -> bool:
    from nebula.device.sky130_runner import TRIMMED_LIB
    try:
        from nebula.device.ngspice_runner import ngspice_path
        return TRIMMED_LIB.exists() and shutil.which(str(ngspice_path())) is not None
    except Exception:
        return False


needs_ngspice = pytest.mark.skipif(not _has_sim(),
                                   reason="ngspice or the SKY130 PDK is absent")

TAIL = TailDevice(w_tail=180.8, l_tail=0.5, nf_tail=8)
BASE = dict(w=100.0, l=0.399, nf=8, rl=565.0, cl=78.04e-15,
            i_tail_per_side_a=1.626e-3, vcm=1.4069, tail=TAIL)


# ─────────────────────────────────────────────────────────────────────────────
# The netlist split. G32: two netlists describing "the same" circuit drifted by
# one model parameter and silently explained away a discrepancy for a week.
# ─────────────────────────────────────────────────────────────────────────────


def test_the_topology_control_split_reassembles_the_original_netlist():
    """`_TOPOLOGY` + `_CONTROL_SINGLE` must BE `_NETLIST`. The split exists so
    the tunable sweep can put a different control block on the SAME circuit;
    if the two halves drift, there are two topologies again."""
    assert _TOPOLOGY + _CONTROL_SINGLE == _NETLIST


def test_the_topology_carries_no_analysis_and_the_control_no_devices():
    """Each half must contain only its own kind, or the split is cosmetic."""
    assert ".control" not in _TOPOLOGY and "meas ac" not in _TOPOLOGY
    assert "XM1" in _TOPOLOGY and "{tail_source}" in _TOPOLOGY
    assert ".control" in _CONTROL_SINGLE and "XM1   outp" not in _CONTROL_SINGLE


# ─────────────────────────────────────────────────────────────────────────────
# The grid.
# ─────────────────────────────────────────────────────────────────────────────


def test_grid_is_geometric_on_both_axes_and_spans_the_box():
    g = tuning_grid()
    rs = sorted({s.rs for s in g})
    cs = sorted({s.cs for s in g})
    assert len(rs) == N_RS and len(cs) == N_CS
    assert rs[0] == pytest.approx(PROPOSED_BOX["rs"][0])
    assert rs[-1] == pytest.approx(PROPOSED_BOX["rs"][1])
    assert cs[0] == pytest.approx(PROPOSED_BOX["cs"][0])
    assert cs[-1] == pytest.approx(PROPOSED_BOX["cs"][1])
    for axis in (rs, cs):
        ratios = [b / a for a, b in zip(axis, axis[1:])]
        assert all(r == pytest.approx(ratios[0]) for r in ratios)


def test_the_design_s_own_setting_is_appended_last():
    """G52: the grid must CONTAIN the point the earlier verdict was made at, or
    the two measure different things and can disagree while both look fine.
    `own_setting_index` depends on it being last."""
    g = tuning_grid(include=[(317.0, 1.9e-12)])
    assert len(g) == N_RS * N_CS + 1
    own = g[own_setting_index(g)]
    assert own.rs == 317.0 and own.cs == 1.9e-12


def test_grid_rejects_a_degenerate_axis():
    with pytest.raises(ValueError):
        tuning_grid(n_rs=1)


def test_the_session_13_gate_constants_are_the_published_ones():
    """If these drift from S9_YIELD §9, the consistency gate silently stops
    checking what it claims to check."""
    assert S13_POPULATION == (2000, 20260804)
    assert (S13_FIXED_ALL, S13_FIXED_ANY_LOAD) == (1, 146)


# ─────────────────────────────────────────────────────────────────────────────
# Adaptation class — the "does it need foreknowledge of the corner?" question.
# ─────────────────────────────────────────────────────────────────────────────


def _pt(cl, met):
    n = len(met)
    return PointResult(tag="t", cl_f=cl, corner="c", met=list(met),
                       first_fail=[None] * n, violated=[()] * n,
                       peaking_db=[None] * n, f_pk_hz=[None] * n,
                       vn_in_vrms=[None] * n)


LOADS = (13.6e-15, 78.0e-15)


def test_one_setting_everywhere_is_class_none():
    pts = [_pt(13.6e-15, [1, 1, 0]), _pt(13.6e-15, [0, 1, 0]),
           _pt(78.0e-15, [0, 1, 1])]
    assert adaptation_class(pts, LOADS) == "none"


def test_one_setting_per_load_is_class_load():
    """Setting 0 covers both cl_lo points, setting 2 covers both cl_hi points,
    and nothing covers all four. A part that adapts to its own load suffices."""
    pts = [_pt(13.6e-15, [1, 0, 0]), _pt(13.6e-15, [1, 1, 0]),
           _pt(78.0e-15, [0, 0, 1]), _pt(78.0e-15, [0, 1, 1])]
    assert adaptation_class(pts, LOADS) == "load"


def test_needing_a_different_setting_per_corner_is_class_load_plus_corner():
    """Within cl_lo, the two corners need different settings. Legitimate only
    for a part that adapts in the field -- never as a design-time trim."""
    pts = [_pt(13.6e-15, [1, 0]), _pt(13.6e-15, [0, 1]),
           _pt(78.0e-15, [1, 1])]
    assert adaptation_class(pts, LOADS) == "load+corner"


def test_a_point_with_no_working_setting_is_class_none_works():
    assert adaptation_class([_pt(13.6e-15, [1, 1]), _pt(78.0e-15, [0, 0])],
                            LOADS) == "none_works"
    assert adaptation_class([], LOADS) == "none_works"


# ─────────────────────────────────────────────────────────────────────────────
# The DAC specification.
# ─────────────────────────────────────────────────────────────────────────────


def test_required_settings_covers_every_point():
    settings = [TunableSetting(100, 1e-12), TunableSetting(500, 2e-12),
                TunableSetting(900, 4e-12)]
    pts = [_pt(13.6e-15, [1, 0, 0]), _pt(78.0e-15, [0, 0, 1])]
    r = required_settings(pts, settings, LOADS)
    assert r["n_settings_upper_bound"] == 2
    assert r["rs_range"] == [100, 900]
    assert r["rs_ratio"] == pytest.approx(9.0)


def test_required_settings_is_empty_when_a_point_is_uncoverable():
    settings = [TunableSetting(100, 1e-12), TunableSetting(500, 2e-12)]
    pts = [_pt(13.6e-15, [1, 0]), _pt(78.0e-15, [0, 0])]
    assert required_settings(pts, settings, LOADS) == {}


def test_greedy_cover_prefers_the_setting_that_covers_most():
    """One setting covering all three points must beat two that cover two and
    one -- otherwise the reported DAC size is inflated."""
    settings = [TunableSetting(100, 1e-12), TunableSetting(500, 2e-12),
                TunableSetting(900, 4e-12)]
    pts = [_pt(13.6e-15, [1, 1, 0]), _pt(13.6e-15, [0, 1, 0]),
           _pt(78.0e-15, [0, 1, 1])]
    assert required_settings(pts, settings, LOADS)["n_settings_upper_bound"] == 1


def test_dac_spec_aggregates_span_and_bit_count():
    spec = dac_spec([
        {"rs_range": [100, 400], "cs_range": [1e-12, 2e-12],
         "n_settings_upper_bound": 2},
        {"rs_range": [200, 900], "cs_range": [5e-13, 4e-12],
         "n_settings_upper_bound": 5},
    ])
    assert spec["rs_span_ohm"] == [100, 900]
    assert spec["cs_span_f"] == [5e-13, 4e-12]
    assert spec["n_settings_max"] == 5
    assert spec["bits_for_max"] == 3          # ceil(log2(5))


def test_dac_spec_is_empty_without_input():
    assert dac_spec([]) == {}


# ─────────────────────────────────────────────────────────────────────────────
# The sweep runner. One needs a simulator; the failure paths do not.
# ─────────────────────────────────────────────────────────────────────────────


def test_an_empty_setting_list_returns_nothing_rather_than_running():
    assert run_tunable_sweep(SizingPoint(rs=300, cs=2e-12, **BASE), []) == []


def test_an_unknown_corner_fails_every_setting_not_just_the_first():
    """Partial results are the danger: a caller handed 3 of 67 back would score
    a design on a grid it never ran."""
    sets = [TunableSetting(100, 1e-12)] * 3
    res = run_tunable_sweep(SizingPoint(rs=300, cs=2e-12, **BASE), sets,
                            corner="zz")
    assert len(res) == 3 and not any(r.ok for r in res)
    assert all("unknown corner" in (r.fail_reason or "") for r in res)


@needs_ngspice
def test_alter_on_rs_cs_is_bit_identical_to_fresh_parse():
    """THE TEST THIS WHOLE PATH RESTS ON.

    G35 proved `alter` silently wrong for device geometry and said it is fine
    for ideal R/C/I. This holds that to rel=0, abs=0 -- not approx -- on every
    quantity the experiment reads, across three corners, reaching each target
    from a DIFFERENT starting setting so the alter genuinely has to move.
    """
    targets = [TunableSetting(800.0, 400e-15), TunableSetting(120.0, 8e-12),
               TunableSetting(50.0, 100e-15)]
    for process, temp in (("tt", 27.0), ("ss", 125.0), ("ff", 0.0)):
        swept = run_tunable_sweep(
            SizingPoint(rs=318.58, cs=1.9e-12, **BASE), targets,
            corner=process, temp_c=temp)
        for st, got in zip(targets, swept):
            fresh = run_point(SizingPoint(rs=st.rs, cs=st.cs, **BASE),
                              corner=process, temp_c=temp, swing=False)
            assert fresh.ok and got.ok, (fresh.fail_reason, got.fail_reason)
            for name in ("g_dc_db", "g_nyq_db", "g_pk_db", "g_top_db",
                         "f_pk_hz", "vn_in_vrms", "gm", "vds", "vdsat",
                         "v_src_dc", "vds_tail", "vdsat_tail"):
                a, b = getattr(fresh, name), getattr(got, name)
                assert a == b, (f"{process}/{temp} {st.tag()} {name}: "
                                f"fresh {a!r} != altered {b!r}")


@needs_ngspice
def test_the_sweep_returns_settings_in_the_order_given():
    """The parser splits output into blocks and pairs the Nth with the Nth
    setting. If that ordering were wrong every result would be attributed to
    the wrong setting, and nothing would look broken."""
    sets = [TunableSetting(1000.0, 100e-15), TunableSetting(50.0, 10e-12),
            TunableSetting(300.0, 1e-12)]
    res = run_tunable_sweep(SizingPoint(rs=300, cs=2e-12, **BASE), sets)
    assert all(r.ok for r in res)
    for st, r in zip(sets, res):
        assert r.point is not None
        assert r.point.rs == st.rs and r.point.cs == st.cs
    # ...and they are genuinely different circuits, so a constant-output bug
    # would be caught too.
    assert len({round(r.g_pk_db, 6) for r in res}) == 3
