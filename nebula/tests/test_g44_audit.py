"""Gates for `experiments/exp_g44_audit.py`.

**NO SPICE ANYWHERE.** `gate_one_point` is the only function that simulates and
it is never called here; the functions that decide WHAT gets simulated, and
how the verdict is aggregated, are tested directly (G129).

The central property this file protects is that the audit **imports** the gate
rather than restating it (CLAUDEwa.md section 8 rule 9). An audit that
re-derived `peak_is_sweep_edge` would be a third definition of validity in a
repository that already has two, which is the defect it exists to measure.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import nebula.experiments.exp_g44_audit as A


# ---------------------------------------------------------------------------
# the gate is imported, never restated
# ---------------------------------------------------------------------------

def test_the_audit_imports_validate_and_does_not_reimplement_it():
    src = Path(A.__file__).read_text(encoding="utf-8")
    assert "from nebula.rl.evaluator import Verdict, build_point, validate" in src
    assert "from nebula.rl.evaluator import F_PEAK_HZ_LIMITS" in src
    # no local copy of either half of the G44 rule. The module docstring may
    # QUOTE the limits when explaining the defect; the CODE may not restate
    # them, so the check is on everything after the docstring.
    code = src[src.index('"""', src.index('"""') + 3) + 3:]
    assert "g_pk_db - pt.g_top_db <=" not in code
    assert "PEAK_MARGIN_DB" not in code
    assert "1.8e10" not in code, "the limit must come from evaluator, not a literal"
    assert "1e7" not in code


def test_the_scan_artifact_list_is_enumerated_not_globbed():
    """G101: a set defined by what it matches grows silently. A new scan must
    be added deliberately, so the audit's scope is always readable."""
    src = Path(A.__file__).read_text(encoding="utf-8")
    assert "glob" not in src
    assert len(A.SCAN_ARTIFACTS) == 10
    assert "hybrid_topk_scan.json" in A.SCAN_ARTIFACTS
    assert "topk_scan_library_k5.json" in A.SCAN_ARTIFACTS


def test_the_audit_writes_only_its_own_artifact():
    src = Path(A.__file__).read_text(encoding="utf-8")
    assert A.RESULTS.name == "g44_audit_results.json"
    assert src.count("write_text") == src.count("RESULTS.write_text") == 1
    for owned in A.SCAN_ARTIFACTS:
        assert A.RESULTS.name != owned


# ---------------------------------------------------------------------------
# pass 1
# ---------------------------------------------------------------------------

def _scan_file(tmp_path, name, cands, k=5):
    p = tmp_path / name
    p.write_text(json.dumps({"k": k, "n_accepted": sum(
        1 for c in cands if c.get("feasible")), "requests": [
            {"index": 2, "peaking_db": 8.0, "f_peak_hz": 1.921e9,
             "candidates": cands}]}), encoding="utf-8")
    return p


def _c(f, feasible=False, rank=1, u=None):
    return {"u": u or [0.5] * 7, "rank": rank, "reward": -2.0,
            "feasible": feasible, "f_peak_hz_got": f}


def test_scan_audit_counts_candidates_outside_the_limits(tmp_path):
    p = _scan_file(tmp_path, "topk_scan_x.json",
                   [_c(19.95e9), _c(2.0e9), _c(2.1e9, feasible=True)])
    out = A.scan_audit([p])
    a = out["artifacts"][0]
    assert a["n_candidates"] == 3
    assert a["n_outside_limits"] == 1
    assert a["n_accepted"] == 1
    assert a["n_accepted_outside_limits"] == 0


def test_scan_audit_FLAGS_an_accepted_candidate_at_the_sweep_edge(tmp_path):
    """The one outcome that would move a published baseline. It must be named
    per design, not only counted."""
    p = _scan_file(tmp_path, "topk_scan_x.json", [_c(19.95e9, feasible=True)])
    out = A.scan_audit([p])
    a = out["artifacts"][0]
    assert a["n_accepted_outside_limits"] == 1
    assert a["accepted_outside"][0]["f_peak_hz"] == 19.95e9
    assert a["accepted_outside"][0]["u"] == [0.5] * 7
    assert out["total_accepted_outside_limits"] == 1


def test_scan_audit_uses_the_evaluators_own_limits():
    from nebula.rl.evaluator import F_PEAK_HZ_LIMITS
    out = A.scan_audit([])
    assert tuple(out["limits_hz"]) == tuple(F_PEAK_HZ_LIMITS)


def test_scan_audit_records_a_missing_artifact_rather_than_skipping_it(tmp_path):
    out = A.scan_audit([tmp_path / "not_here.json"])
    assert out["artifacts"][0]["missing"] is True


def test_scan_audit_declares_itself_a_lower_bound():
    """The artifact cannot answer `peak_is_sweep_edge`. Saying so in the
    artifact is the difference between a bound and an overclaim."""
    assert "LOWER BOUND" in A.scan_audit([])["note"]


def test_scan_audit_ignores_errored_candidates(tmp_path):
    p = _scan_file(tmp_path, "topk_scan_x.json", [{"error": "boom"}, _c(2e9)])
    assert A.scan_audit([p])["artifacts"][0]["n_candidates"] == 1


# ---------------------------------------------------------------------------
# which designs get re-simulated
# ---------------------------------------------------------------------------

def test_accepted_designs_takes_only_feasible_candidates(tmp_path):
    p = _scan_file(tmp_path, "topk_scan_x.json",
                   [_c(2e9, u=[0.1] * 7), _c(2e9, feasible=True, u=[0.2] * 7)])
    got = A.accepted_designs([p])
    assert len(got) == 1 and got[0]["u"] == [0.2] * 7


def test_accepted_designs_dedups_on_u_not_on_design_id(tmp_path):
    """G124: bit-identical sizing gets different `design_id`s across artifact
    boundaries, so an id-keyed dedup would re-simulate the same design twice
    and an id-keyed JOIN would come back empty and read as a finding."""
    a = _scan_file(tmp_path, "topk_scan_a.json",
                   [_c(2e9, feasible=True, u=[0.3] * 7)])
    b = _scan_file(tmp_path, "topk_scan_b.json",
                   [_c(2e9, feasible=True, u=[0.3] * 7)])
    got = A.accepted_designs([a, b])
    assert len(got) == 1
    assert {s["artifact"] for s in got[0]["sources"]} == {
        "topk_scan_a.json", "topk_scan_b.json"}


def test_accepted_designs_keeps_two_genuinely_different_sizings(tmp_path):
    p = _scan_file(tmp_path, "topk_scan_x.json",
                   [_c(2e9, feasible=True, u=[0.3] * 7),
                    _c(2e9, feasible=True, u=[0.4] * 7)])
    assert len(A.accepted_designs([p])) == 2


def test_accepted_designs_carries_the_request_it_was_accepted_for(tmp_path):
    p = _scan_file(tmp_path, "topk_scan_x.json", [_c(2e9, feasible=True)])
    got = A.accepted_designs([p])[0]
    assert got["request_index"] == 2 and got["peaking_db"] == 8.0


def test_the_real_scans_yield_the_twelve_accepted_designs_this_audit_covers():
    """If a scan artifact moves, the audit's scope moves with it and this
    reddens rather than the run silently measuring a different population."""
    paths = [A.HERE / n for n in A.SCAN_ARTIFACTS]
    if not all(p.exists() for p in paths):
        pytest.skip("scan artifacts not present in this checkout")
    got = A.accepted_designs(paths)
    assert len(got) == 12
    lib = [g for g in got
           if any(s["artifact"] == "hybrid_topk_scan.json" for s in g["sources"])]
    assert len(lib) == 7, "entry 32's baseline is 7 feasible candidates"


# ---------------------------------------------------------------------------
# the mandated grid
# ---------------------------------------------------------------------------

def test_mandated_45_is_45_points_at_one_load():
    pts = A.mandated_45()
    assert len(pts) == 45
    assert len({p.cl_f for p in pts}) == 1
    assert len({(p.corner.process, p.corner.vdd_scale, p.corner.temp_c)
                for p in pts}) == 45


def test_mandated_45_uses_the_screens_design_load(monkeypatch):
    from nebula.experiments.adaptive_screen import EDGE4_MANDATED
    assert A.mandated_45()[0].cl_f == EDGE4_MANDATED[0].cl_f


def test_mandated_45_RAISES_if_the_screen_spans_loads(monkeypatch):
    """G109: the mandated grid is 45 corners at the design load. If
    `EDGE4_MANDATED` ever gained a load axis, silently picking its first
    member's load would merge compliance with characterisation."""
    import nebula.experiments.adaptive_screen as S

    two = (S.EDGE4_MANDATED[0],
           S.ScreenPoint(S.EDGE4_MANDATED[1].corner,
                         S.EDGE4_MANDATED[1].cl_f * 2.0, "sabotage"))
    monkeypatch.setattr(S, "EDGE4_MANDATED", two)
    with pytest.raises(ValueError, match="single load"):
        A.mandated_45()


# ---------------------------------------------------------------------------
# reading a published compliance design
# ---------------------------------------------------------------------------

def test_compliance_design_u_reads_both_artifact_shapes(tmp_path):
    listed = tmp_path / "listed.json"
    listed.write_text(json.dumps({"results": [{"design_id": "aa", "u": [0.1] * 7}]}))
    flat = tmp_path / "flat.json"
    flat.write_text(json.dumps({"design_id": "bb", "u": [0.2] * 7}))
    import nebula.experiments.exp_g44_audit as M
    old = M.HERE
    try:
        M.HERE = tmp_path
        assert M.compliance_design_u("listed.json", "aa") == [0.1] * 7
        assert M.compliance_design_u("flat.json", "bb") == [0.2] * 7
    finally:
        M.HERE = old


def test_compliance_design_u_RAISES_on_a_record_with_no_u(tmp_path):
    """Measured: `joint_verify_full_results.json` names the joint winner and
    does not record its `u`. Returning None there would silently drop the very
    compliance claim the audit exists to check (G115)."""
    p = tmp_path / "x.json"
    p.write_text(json.dumps({"results": [{"design_id": "aa"}]}))
    import nebula.experiments.exp_g44_audit as M
    old = M.HERE
    try:
        M.HERE = tmp_path
        with pytest.raises(ValueError, match="carries no `u`"):
            M.compliance_design_u("x.json", "aa")
        with pytest.raises(ValueError, match="no record with design_id"):
            M.compliance_design_u("x.json", "zz")
    finally:
        M.HERE = old


def test_both_published_compliance_designs_are_reconstructible():
    for artifact, design_id, _what in A.COMPLIANCE_DESIGNS:
        if not (A.HERE / artifact).exists():
            pytest.skip(f"{artifact} not present")
        u = A.compliance_design_u(artifact, design_id)
        assert len(u) == 7 and all(0.0 <= x <= 1.0 for x in u)


# ---------------------------------------------------------------------------
# the verdict aggregation
# ---------------------------------------------------------------------------

def test_gate_design_rejects_when_ANY_point_is_invalid(monkeypatch):
    """The screen's own rule is worst-of-points; validity must be too, or a
    design invalid at one corner would be audited as clean."""
    seq = [{"point": "a", "sim_ok": True, "invalid": False,
            "peak_is_sweep_edge": False},
           {"point": "b", "sim_ok": True, "invalid": True,
            "peak_is_sweep_edge": True}]
    it = iter(seq)
    monkeypatch.setattr(A, "gate_one_point", lambda u, sp: next(it))
    g = A.gate_design([0.5] * 7, [object(), object()])
    assert g["gate_rejects"] is True
    assert g["n_invalid"] == 1 and g["n_sweep_edge"] == 1 and g["n_points"] == 2


def test_gate_design_passes_a_clean_design(monkeypatch):
    monkeypatch.setattr(A, "gate_one_point", lambda u, sp: {
        "point": "a", "sim_ok": True, "invalid": False,
        "peak_is_sweep_edge": False})
    g = A.gate_design([0.5] * 7, [object()] * 4)
    assert g["gate_rejects"] is False and g["n_invalid"] == 0
    assert g["n_sims"] == 4


def test_gate_design_counts_a_failed_simulation_separately(monkeypatch):
    """A deck that did not run is not a design that failed the gate (G107)."""
    monkeypatch.setattr(A, "gate_one_point", lambda u, sp: {
        "point": "a", "sim_ok": False, "fail_reason": "no convergence",
        "verdict": None})
    g = A.gate_design([0.5] * 7, [object()])
    assert g["n_sim_failed"] == 1 and g["n_invalid"] == 0
    assert g["gate_rejects"] is False


def test_scan_only_spends_no_spice(monkeypatch):
    """G122/G129: `--scan` must be unable to simulate. If it could, the
    'zero SPICE' claim in the module docstring would be false."""
    def _boom(*a, **kw):
        raise AssertionError("--scan must not simulate")

    monkeypatch.setattr(A, "gate_one_point", _boom)
    monkeypatch.setattr(A, "gate_design", _boom)
    out = A.run(scan_only=True)
    assert "scan" in out and "accepted" not in out


def test_mandated_45_RAISES_when_the_corner_grid_is_not_45(monkeypatch):
    """G117: the first version of this round left the `len(corners) != 45`
    guard GREEN under sabotage, because `all_corners()` really does return 45
    and no test could tell the guard from its absence. A gate whose data
    cannot separate the correct rule from the broken one is not a gate.
    """
    import nebula.common.types as T

    real = T.all_corners()
    monkeypatch.setattr(T, "all_corners", lambda: real[:44])
    with pytest.raises(ValueError, match="not the 45"):
        A.mandated_45()
