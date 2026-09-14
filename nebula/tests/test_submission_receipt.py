"""Pure saved-record receipt checks: no simulator, policy or network."""
import copy
import json
from pathlib import Path
import pytest
from nebula.experiments import build_submission_receipt as R

ROOT = Path(__file__).resolve().parents[2]

@pytest.fixture
def saved():
    return json.loads((ROOT / R.SOURCE).read_text(encoding="utf-8"))

def test_saved_receipt_preserves_cost_and_recovery(saved):
    receipt = R.receipt_model(saved)
    assert receipt["counts"]["billed_visits"] == 2406
    assert receipt["counts"]["fixed_start_visits"] == 315
    assert receipt["counts"]["bank_selected"] == 234
    assert receipt["counts"]["safety_recoveries"] == 49
    trace = receipt["recovery_example"]
    assert trace["policy_trace"]["settings_tried"] == [360,296,232,168,104,168,232]
    assert trace["selected_setting"] == 496
    assert 496 not in trace["policy_trace"]["settings_tried"]
    assert receipt["timing"]["end_to_end_wall_s"] is None
    assert receipt["timing"]["original_recorded_wall_s"] == saved["wall_s"]
    assert receipt["spice"]["receipt_generation_new_calls"] == 0
    assert receipt["spice"]["original_run"]["export"] == 1

def test_missing_elapsed_time_is_not_fabricated(saved):
    del saved["wall_s"]
    del saved["export_wall_s"]
    timing = R.receipt_model(saved)["timing"]
    assert timing["original_recorded_wall_s"] is None
    assert timing["recorded_export_wall_s"] is None

@pytest.mark.parametrize("damage", ["duplicate", "counts", "trace", "action", "selection"])
def test_receipt_refuses_inconsistent_evidence(saved, damage):
    row = saved["verification"]["per_condition"][0]
    if damage == "duplicate":
        saved["verification"]["per_condition"][1] = copy.deepcopy(row)
    elif damage == "counts":
        saved["search"]["rl_proposals"] += 1
    elif damage == "trace":
        row["policy_trace"]["measurements"].pop()
    elif damage == "action":
        row["policy_trace"]["actions"][0] = "cs_up"
    else:
        row["source"] = "rl-shield"
    with pytest.raises(ValueError):
        R.receipt_model(saved)

def test_source_hash_gate_refuses_changed_bytes(tmp_path):
    path = tmp_path / "source.json"
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash"):
        R.checked_bytes(path, R.SOURCE_SHA256)
