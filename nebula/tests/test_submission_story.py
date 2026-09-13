"""Evidence and preservation boundaries for the independent submission report."""
import hashlib
import json

import pytest


def test_report_preserves_both_previous_editions():
    from nebula.report.submission_story import PREVIOUS, OUT, PDF
    assert PDF.name == "Nebula_Submission_Report_20260914.pdf"
    for name, digest in PREVIOUS.items():
        assert hashlib.sha256((OUT / name).read_bytes()).hexdigest() == digest


def test_report_uses_pinned_hardware_and_separate_policy_evidence():
    from nebula.report.submission_story import load_story_evidence
    e = load_story_evidence()
    assert e["hardware"]["pvt"]["n_pass"] == 45
    assert e["hardware"]["nominal"]["correct_bits"] == 64
    assert e["legacy"]["conditions"] == 315
    assert e["legacy"]["winning"]["benchmark"]["aggregate"]["near_optimality_gate"] is False
    assert e["device_count"] == 73
    assert [item["verified_files"] for item in e["archive_checks"]] == [137, 362]
    assert [item["verified_archives"] for item in e["archive_checks"]] == [10, 90]


def test_report_manifest_rejects_changed_input(tmp_path):
    from nebula.report.submission_story import verify_sources
    path = tmp_path / "source.json"
    path.write_text("{}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    records = [{"path": path.name, "sha256": digest}]
    verify_sources(records, tmp_path)
    path.write_text('{"changed":true}')
    with pytest.raises(ValueError, match="source changed"):
        verify_sources(records, tmp_path)


def test_new_pdf_has_required_story_and_preserves_honest_boundaries():
    import fitz
    from nebula.report.submission_story import PDF, MANIFEST, verify_sources
    assert PDF.is_file(), "Build the new report before submission checks"
    manifest = json.loads(MANIFEST.read_text())
    assert hashlib.sha256(PDF.read_bytes()).hexdigest() == manifest["report_sha256"]
    verify_sources(manifest["sources"])
    with fitz.open(PDF) as doc:
        assert len(doc) == manifest["page_count"] == 25
        assert len(doc.get_toc()) == 25
        assert all(742 <= y <= 779 for y in manifest["content_bottoms_pt"])
        text = " ".join("\n".join(page.get_text() for page in doc).split())
    for phrase in ("Abstract", "Deliverables", "Architecture", "Decisions",
                   "The source-degenerated CTLE", "Reference current made physical",
                   "Physical attenuation and peaking", "From transistor response to eye",
                   "What the 1-tap DFE contributes",
                   "45/45", "64/64", "91.8x", "near-optimality",
                   "finite", "noiseless", "analog PVT", "not routed",
                   "zero human intervention", "Jai Kaushik", "Rishabh Agarwal", "Avi Mehta"):
        assert phrase in text, phrase


def test_report_source_hash_accepts_only_git_line_ending_changes(tmp_path):
    from nebula.report.submission_story import source_record, verify_sources
    path = tmp_path / "source.py"
    path.write_bytes(b"value = 1\n")
    record = source_record(path, tmp_path)
    assert record["hash_mode"] == "lf-text"
    path.write_bytes(b"value = 1\r\n")
    verify_sources([record], tmp_path)
    path.write_bytes(b"value = 2\r\n")
    with pytest.raises(ValueError, match="source changed"):
        verify_sources([record], tmp_path)
    frozen = tmp_path / "nebula/product_audits/result.json"
    frozen.parent.mkdir(parents=True)
    frozen.write_bytes(b"{}\n")
    record = source_record(frozen, tmp_path)
    assert record["hash_mode"] == "raw"
    frozen.write_bytes(b"{}\r\n")
    with pytest.raises(ValueError, match="source changed"):
        verify_sources([record], tmp_path)
