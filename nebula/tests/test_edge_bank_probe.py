"""Fail-capable gates for Entry 90's focused physical edge-bank probe."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from nebula.experiments import exp_edge_bank_probe as P
from nebula.experiments import exp_joint_bank as J


def _row(setting: int, corner: str = "tt/1.00/27C", ok: bool = True,
         links=None) -> J.JointRow:
    return J.JointRow(
        setting=setting, atten_code=7, bank_code=-1, i_rs=-1, i_cs=-1,
        corner=corner, ok=ok, reason=(None if ok else "ngspice failure"),
        peaking_db=11.0, f_peak_oct=-0.5, margins={},
        links=(links if links is not None else {"3.0": {"ok": True}}))


def _coverage(n_pass: int = 315, old_pass: int = 315,
              new_only: int = 0) -> dict:
    return {
        P.request_key(request): {
            "n_pass": n_pass, "n_old_pass": old_pass,
            "n_new_only": new_only, "per_loss": {},
            "candidate_usage": ({"edge-0": new_only} if new_only else {}),
        }
        for request in P.REQUESTS
    }


def test_registered_candidate_grid_has_exact_membership_and_values():
    base_u = P.load_base_u()
    candidates = P.build_candidates(base_u)
    assert len(candidates) == 30
    assert len({candidate.setting for candidate in candidates}) == 30
    assert sum(candidate.group == "low-edge" for candidate in candidates) == 6
    assert sum(candidate.group == "high-edge" for candidate in candidates) == 24
    assert {candidate.atten_code for candidate in candidates
            if candidate.group == "high-edge"} == set(range(8))
    assert {candidate.atten_code for candidate in candidates
            if candidate.group == "low-edge"} == {7}
    assert P.PROBE_TOP_DB == pytest.approx(8.3)
    assert P.PROBE_MAX_X == pytest.approx(10.0 ** (8.3 / 20.0))
    assert P.extra_cs_f(base_u) * 1e12 == pytest.approx(1.294863, rel=2e-6)
    assert P.mid_rs_ohm(base_u) == pytest.approx(581.2038, rel=2e-6)


def test_coverage_uses_union_and_attributes_new_only_conditions(monkeypatch):
    source = [_row(1)]
    probe = [_row(P.FIRST_PROBE_SETTING)]

    def compliant(row, loss, freq, peaking):
        del loss, freq
        if (peaking, row.setting) == (12.0, P.FIRST_PROBE_SETTING):
            return True
        return peaking != 12.0 and row.setting == 1

    monkeypatch.setattr(J, "is_compliant", compliant)
    out = P.coverage(
        source, probe, requests=((12.0, 1.25e9), (3.0, 1.25e9)),
        losses=(3.0,), corners=("tt/1.00/27C",))
    assert out[P.request_key((12.0, 1.25e9))]["n_old_pass"] == 0
    assert out[P.request_key((12.0, 1.25e9))]["n_pass"] == 1
    assert out[P.request_key((12.0, 1.25e9))]["n_new_only"] == 1
    assert out[P.request_key((3.0, 1.25e9))]["n_old_pass"] == 1


def test_score_accepts_all_registered_gates():
    cov = _coverage()
    cov[P.request_key(P.LOW_EDGE_REQUEST)].update(
        n_old_pass=308, n_new_only=7, candidate_usage={"edge-0": 7})
    cov[P.request_key(P.HIGH_EDGE_REQUEST)].update(
        n_old_pass=112, n_new_only=203, candidate_usage={"edge-1": 203})
    out = P.score(
        membership_ok=True, hard_device_failures=0, coverage_by_request=cov,
        source_hash_ok=True, isolation_ok=True)
    assert out["checks"] == {f"Q{i}": True for i in range(1, 8)}
    assert out["passed"]
    assert out["recommend_production_redesign"]


def test_low_high_control_and_isolation_gates_fail_independently():
    cov = _coverage()
    cov[P.request_key(P.LOW_EDGE_REQUEST)]["n_pass"] = 314
    cov[P.request_key(P.HIGH_EDGE_REQUEST)].update(
        n_old_pass=112, n_new_only=203, candidate_usage={"edge-1": 203})
    cov[P.request_key(P.CONTROL_REQUESTS[0])]["n_pass"] = 314
    out = P.score(
        membership_ok=True, hard_device_failures=0, coverage_by_request=cov,
        source_hash_ok=False, isolation_ok=False)
    assert not out["checks"]["Q3"]
    assert out["checks"]["Q4"]
    assert not out["checks"]["Q5"]
    assert out["checks"]["Q6"]
    assert not out["checks"]["Q7"]
    assert not out["passed"]


def test_membership_checks_every_candidate_corner_and_link_key():
    candidates = (
        P.ProbeCandidate(P.FIRST_PROBE_SETTING, "a", "low-edge", 7,
                         (0.5,) * 7),
        P.ProbeCandidate(P.FIRST_PROBE_SETTING + 1, "b", "high-edge", 0,
                         (0.5,) * 7),
    )
    rows = [
        _row(candidate.setting, corner,
             links={str(loss): {"ok": True} for loss in (3.0, 4.5)})
        for candidate in candidates for corner in ("c0", "c1")
    ]
    assert P.membership_ok(
        rows, candidates, corners=("c0", "c1"), losses=(3.0, 4.5))
    rows[0].links.pop("4.5")
    assert not P.membership_ok(
        rows, candidates, corners=("c0", "c1"), losses=(3.0, 4.5))


def test_run_refuses_to_overwrite_result(monkeypatch, tmp_path):
    result = tmp_path / "result.json"
    result.write_text("keep", encoding="utf-8")
    monkeypatch.setattr(P, "RESULTS", result)
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        P.run()


def test_probe_source_never_reaches_entry89_final():
    source = Path(P.__file__).read_text(encoding="utf-8")
    assert "exp_shielded_final" not in source
    assert "shielded_policy_final_results" not in source
    assert "MIDPOINT" not in source


def test_console_print_literals_are_ascii():
    tree = ast.parse(Path(P.__file__).read_text(encoding="utf-8"))
    for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
        if not isinstance(call.func, ast.Name) or call.func.id != "print":
            continue
        for value in (node for arg in call.args for node in ast.walk(arg)
                      if isinstance(node, ast.Constant)
                      and isinstance(node.value, str)):
            assert value.value.isascii(), repr(value.value)
