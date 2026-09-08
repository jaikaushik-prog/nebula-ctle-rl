"""Report metrics must preserve the evidence/deployment boundary."""
import json

import pytest

from nebula.report import competition_2026 as R


def test_report_evidence_has_fixed_candidate_not_deployed():
    old, new, requests, final, product, summary = R.evidence()
    assert len(old) == len(new) == 45
    assert product["search"]["setting"] == 425
    assert summary["adopted"] is False
    assert summary["fixed"]["full_product_compliance"] is False
    assert sum(x["model_pass"] for row in old for x in row["links"]) == 301
    assert sum(x["model_pass"] for row in new for x in row["links"]) == 315
    assert sum(r["n_compliant"] == 315 for r in requests) == 8
    assert final["n_final_identities"] == 2430


def test_report_cannot_silently_label_adopted_candidate_as_unadopted(monkeypatch):
    original = R.read_json

    def changed(path):
        d = original(path)
        if path == R.A101 / "summary.json":
            d["adopted"] = True
        return d

    monkeypatch.setattr(R, "read_json", changed)
    with pytest.raises(AssertionError):
        R.evidence()


def test_report_rejects_fixed_circuit_identity_drift(monkeypatch):
    original = R.read_rows

    def changed(path):
        rows = original(path)
        if path == R.A101 / "fixed_pvt.jsonl":
            rows[-1]["circuit_signature"] = "different-circuit"
        return rows

    monkeypatch.setattr(R, "read_rows", changed)
    with pytest.raises(AssertionError):
        R.evidence()


def test_report_jsonl_reader_skips_empty_lines(tmp_path):
    path = tmp_path / "rows.jsonl"
    path.write_text(json.dumps({"ok": True})+"\n\n", encoding="utf-8")
    assert R.read_rows(path) == [{"ok": True}]
