"""Generated physical CTLE to transistor DFE integration."""
import hashlib
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "nebula/product_demo/submission_runs_20260915_v2/4608cf1c525f4e59b2d5226059b0ce5d"


def inputs():
    design = json.loads((RUN / "design.json").read_text(encoding="utf-8"))
    deck = (RUN / "design.cir").read_bytes().decode("ascii")
    return design, deck


def test_connected_deck_uses_selected_ctle_and_real_dfe():
    from nebula.generated_receiver import build_deck

    design, selected = inputs()
    deck = build_deck(design, selected)
    assert deck.count(".lib ") == 1
    assert deck.count(".control") == 1
    assert "W=57.97671772296124" in deck
    assert "RS=257.7458646418858" in deck
    assert "Xdfe_sump" in deck and "Xdfe_dacp" in deck
    assert "Xdf_mtrack" in deck and "Xdf_strack" in deck and "Xdfe_bleed0" in deck
    assert "wrdata trace.txt" in deck and "wrdata terminals.txt" in deck
    assert "ideal DFE" not in deck and "behavioral cancellation" not in deck


def test_deck_identity_mismatch_is_refused():
    from nebula.generated_receiver import build_deck

    design, selected = inputs()
    with pytest.raises(ValueError, match="deck hash"):
        build_deck(design, selected + "\n* changed\n")


def test_only_accepted_physical_design_is_exported():
    from nebula.generated_receiver import build_deck

    design, selected = inputs()
    design["method"] = "rl-hybrid"
    with pytest.raises(ValueError, match="accepted physical"):
        build_deck(design, selected)


def test_export_records_structural_scope_without_claiming_verification(tmp_path):
    from nebula.generated_receiver import export

    design, selected = inputs()
    out = tmp_path / "receiver"
    result = export(design, selected, out)
    path = out / "receiver.cir"
    assert path.is_file()
    assert result["structurally_integrated"] is True
    assert result["nominal_transistor_verified"] is False
    assert result["full_receiver_verified"] is False
    assert result["receiver_deck_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()



def test_nominal_instrument_failure_is_retained_without_retry(tmp_path, monkeypatch):
    from nebula import generated_receiver as G
    calls=[]
    def fail(deck, folder):
        calls.append(deck)
        raise ValueError("missing terminal trace")
    monkeypatch.setattr(G.spice_capture, "invoke", fail)
    design, selected=inputs()
    out=tmp_path/"nominal"
    result=G.verify_nominal(design, selected, out)
    assert len(calls)==1
    assert result["nominal_transistor_verified"] is False
    assert result["signal_gate_pass"] is False
    assert result["instrument_ok"] is False
    assert result["full_receiver_verified"] is False
    assert "missing terminal trace" in result["fail_reason"]
    assert json.loads((out/"result.json").read_text())==result


def test_nominal_hash_failure_never_launches_spice(tmp_path, monkeypatch):
    from nebula import generated_receiver as G
    monkeypatch.setattr(G.spice_capture, "invoke", lambda *args: pytest.fail("unexpected simulation"))
    design, selected=inputs()
    result=G.verify_nominal(design,selected+"\n* changed",tmp_path/"invalid")
    assert result["instrument_ok"] is False
    assert result["nominal_transistor_verified"] is False
    assert "deck hash" in result["fail_reason"]
