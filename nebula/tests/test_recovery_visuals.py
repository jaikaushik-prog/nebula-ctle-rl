"""Recovery-layout adapter tests; all eye science stays in canonical code."""
import hashlib
import json
from pathlib import Path
import shutil

import pytest
from nebula.web import recovery_visuals as R

ROOT = Path(__file__).resolve().parents[2]
SAVED = ROOT / "nebula/product_demo/submission_runs_20260915_v2/94b55321c7f245df8093284b402c8a40"
CANDIDATE = "candidate_02_setting_352"


@pytest.fixture
def saved_copy(tmp_path):
    out = tmp_path / "copied_run"
    out.mkdir()
    for name in ("design.json", "design.cir", "workflow_receipt.json"):
        shutil.copyfile(SAVED/name, out/name)
    source = SAVED/"physical_recovery"/CANDIDATE
    dest = out/"physical_recovery"/CANDIDATE
    for name in ("design.cir", "evidence_sha256.json", "tt_1.00_27/ac_noise/ac.txt"):
        path = dest/name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source/name, path)
    return out


def test_saved_352_uses_unchanged_canonical_eye(saved_copy):
    eye = R.selected_eye(saved_copy)
    assert eye["eye_h_v"]*1000 == pytest.approx(337.518717, abs=0.00001)
    assert eye["eye_w_ui"] == .859375
    assert eye["kind"] == "worst-case-isi-envelope"
    assert eye["waveform"]["samples_per_ui"] == 64


@pytest.mark.parametrize("name", ["design.cir", "tt_1.00_27/ac_noise/ac.txt"])
def test_wrong_deck_or_tampered_ac_rejected(saved_copy, name):
    path=saved_copy/"physical_recovery"/CANDIDATE/name
    path.write_bytes(path.read_bytes()+b"\n* modified\n")
    with pytest.raises(ValueError, match="hash|deck"):
        R.selected_eye(saved_copy)


def test_tampered_selected_design_rejected(saved_copy):
    path=saved_copy/"design.json"
    path.write_bytes(path.read_bytes()+b" ")
    with pytest.raises(ValueError, match="design.json"):
        R.selected_eye(saved_copy)


def test_tampered_visible_export_rejected(saved_copy):
    (saved_copy/"design.cir").write_text("wrong circuit")
    with pytest.raises(ValueError, match="design.cir|deck"):
        R.selected_eye(saved_copy)


def test_missing_local_candidate_never_follows_original_absolute_path(saved_copy):
    local=saved_copy/"physical_recovery"/CANDIDATE
    local.rename(local.with_name("removed_candidate"))
    # The receipt's original absolute coverage path still exists. It must not be read.
    with pytest.raises((ValueError,FileNotFoundError), match="candidate"):
        R.selected_eye(saved_copy)


def test_candidate_identity_cannot_be_redirected(saved_copy):
    path=saved_copy/"workflow_receipt.json"
    receipt=json.loads(path.read_text())
    receipt["attempts"][-1]["directory"]="../../other_candidate"
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="candidate"):
        R.selected_eye(saved_copy)


def test_last_attempt_must_match_selected_setting(saved_copy):
    path=saved_copy/"workflow_receipt.json"
    receipt=json.loads(path.read_text())
    receipt["attempts"][-1]["setting"]=481
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="setting|candidate"):
        R.selected_eye(saved_copy)


def test_legacy_layout_delegates_without_recovery_requirements(tmp_path,monkeypatch):
    (tmp_path/"physical_evidence").mkdir()
    sentinel={"legacy":"unchanged"}
    calls=[]
    monkeypatch.setattr(R.canonical,"selected_eye",lambda p:(calls.append(p) or sentinel))
    assert R.selected_eye(tmp_path) is sentinel
    assert calls==[tmp_path]

