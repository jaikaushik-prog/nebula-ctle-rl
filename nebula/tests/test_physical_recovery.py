import json

import pytest

from nebula import physical_design as D
from nebula.experiments import exp_physical_recovery as R


class Table:
    settings = (1, 2, 3)
    corners = ("tt", "ss")

    def compliant_settings(self, corner, loss, *request):
        return (1, 2) if corner == "tt" else (2, 3)


def test_forced_setting_must_belong_to_fixed_intersection():
    result = D.select_fixed_setting(Table(), (3.0, 1.9e9), 1, (3.0,),
                                    forced_setting=2)
    assert result == (2, [2], 6)
    with pytest.raises(ValueError, match="historically eligible|fixed|eligible"):
        D.select_fixed_setting(Table(), (3.0, 1.9e9), 1, (3.0,),
                               forced_setting=1)


def test_recovery_attempts_all_ten_even_after_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "frozen_plan", lambda: "orium")
    monkeypatch.setattr(R, "verify_source", lambda: ("source", {}))
    calls = []

    def fake_run(peaking, frequency, *, evidence_dir, forced_setting):
        calls.append((peaking, frequency, forced_setting))
        evidence_dir.mkdir()
        passed = forced_setting in (401, 481)
        return {
            "verified": passed,
            "simulations": {"total": 137},
            "verification": {"n_pass": 315 if passed else 314, "n_points": 315},
            "physical_evidence": {
                "circuit_signature": f"signature-{forced_setting}",
                "deck_sha256": f"deck-{forced_setting}",
            },
        }

    monkeypatch.setattr(D, "run", fake_run)
    monkeypatch.setattr(D, "is_verified", lambda result: result["verified"])
    result = R.run(tmp_path / "out")
    assert len(calls) == 10
    assert result["all_candidates_attempted"]
    assert result["n_targets_recovered"] == 2
    assert result["spice_calls"] == 1370
    assert result["targets"][0]["first_passing_setting"] == 401
    assert result["targets"][1]["first_passing_setting"] == 481
    assert json.loads((tmp_path / "out/summary.json").read_text())["n_candidates"] == 10


def test_recovery_refuses_existing_output(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "frozen_plan", lambda: "protocol")
    monkeypatch.setattr(R, "verify_source", lambda: ("source", {}))
    with pytest.raises(FileExistsError):
        R.run(tmp_path)


def test_recovery_runs_all_candidates_and_records_first_pass(tmp_path, monkeypatch):
    calls = []

    def fake_run(peaking, frequency, *, evidence_dir, forced_setting):
        evidence_dir.mkdir()
        calls.append((peaking, frequency, forced_setting))
        passed = forced_setting in (337, 346)
        return {
            "passed": passed,
            "simulations": {"total": 137},
            "verification": {"n_pass": 315 if passed else 314, "n_points": 315},
            "physical_evidence": {
                "circuit_signature": f"sig-{forced_setting}",
                "deck_sha256": f"deck-{forced_setting}",
            },
        }

    monkeypatch.setattr(R, "frozen_plan", lambda: "protocol")
    monkeypatch.setattr(R, "verify_source", lambda: ("coverage", {}))
    monkeypatch.setattr(R.D, "run", fake_run)
    monkeypatch.setattr(R.D, "is_verified", lambda result: result["passed"])

    result = R.run(tmp_path / "evidence")

    assert len(calls) == 10
    assert result["all_candidates_attempted"]
    assert result["n_targets_recovered"] == 2
    assert [target["first_passing_setting"] for target in result["targets"]] == [337, 346]
    assert result["spice_calls"] == 1370
    assert json.loads((tmp_path / "evidence/summary.json").read_text())["n_candidates"] == 10
    assert "summary.json" in json.loads((tmp_path / "evidence/sha256.json").read_text())