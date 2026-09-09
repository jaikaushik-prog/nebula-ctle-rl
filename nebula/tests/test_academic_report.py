"""Regression checks for the preserved and academic competition reports."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pypdf import PdfReader

from nebula.report.competition_2026 import OUT


ARCHIVE = OUT / "archive_before_academic_restructure_20260909"
BASELINE_PDF = OUT / "Nebula_Competition_Report.pdf"
ACADEMIC_PDF = OUT / "Nebula_Competition_Report_Academic.pdf"
ACADEMIC_MANIFEST = OUT / "Nebula_Competition_Report_Academic_sources.json"
ACADEMIC_REVIEW = OUT / "Nebula_Competition_Report_Academic_review.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_previous_report_is_preserved_byte_for_byte():
    recorded = json.loads((ARCHIVE / "archive_sha256.json").read_text(encoding="utf-8"))
    for name, expected_hash in recorded.items():
        assert sha256(ARCHIVE / name) == expected_hash

    archived_pdf = ARCHIVE / "Nebula_Competition_Report.pdf"
    expected = "3cd67ffc933b8f369d601a72f16e39295542780777ca5bccc797135278faf43b"
    assert recorded[archived_pdf.name] == expected
    assert sha256(BASELINE_PDF) == expected


def test_academic_report_has_expected_structure_and_evidence_headlines():
    manifest = json.loads(ACADEMIC_MANIFEST.read_text(encoding="utf-8"))
    review = json.loads(ACADEMIC_REVIEW.read_text(encoding="utf-8"))
    reader = PdfReader(ACADEMIC_PDF)
    assert manifest["page_count"] == 22
    assert len(reader.pages) == len(reader.outline) == 22
    assert sha256(ACADEMIC_PDF) == manifest["report_sha256"]
    assert review["report_sha256"] == manifest["report_sha256"]
    assert review["visual_review"].startswith("PASS")
    assert sha256(ACADEMIC_PDF) != sha256(BASELINE_PDF)

    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    required = (
        "Abstract and project objectives",
        "Contents and evidence map",
        "CHAPTER 1 / PROBLEM AND OBJECTIVES",
        "CHAPTER 4 / REINFORCEMENT LEARNING",
        "CHAPTER 6 / CONCLUSIONS",
        "45/45",
        "315/315",
        "91.8x",
        "Jai Kaushik",
        "Rishabh Agarwal",
        "Avi Mehta",
        "Final circuit at a glance",
        "What the automated run produces",
        "Three evidence layers",
    )
    assert all(value in text for value in required)
    assert "Future work and development priorities" in (
        reader.pages[-1].extract_text() or ""
    )
