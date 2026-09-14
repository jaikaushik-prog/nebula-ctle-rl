"""Final-report contracts: no simulator or training calls."""
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_final_report_is_separate_twelve_page_artifact():
    from nebula.report import final_submission as report
    assert report.PDF.name == 'Nebula_Final_Submission_12p_20260915.pdf'
    assert len(report.PAGE_TITLES) == 12
    assert report.PDF != report.DETAILED_PDF


def test_manifest_rejects_changed_evidence(tmp_path):
    from nebula.report.final_submission import source_record, verify_sources
    path = tmp_path / 'evidence.bin'
    path.write_bytes(b'original frozen bytes')
    record = source_record(path, root=tmp_path)
    path.write_bytes(b'changed frozen bytes')
    with pytest.raises(ValueError, match='changed'):
        verify_sources([record], root=tmp_path)


def test_final_pdf_claims_and_blank_owner_fields():
    import fitz
    from nebula.report.final_submission import PDF, MANIFEST, verify_sources
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    verify_sources(manifest['sources'])
    doc = fitz.open(PDF)
    assert len(doc) == 12
    assert len(doc.get_toc()) == 12
    text = ' '.join(' '.join(p.get_text().split()) for p in doc)
    for phrase in ('The source-degenerated CTLE', 'Reference current made physical',
                   'Physical attenuation and peaking', 'From transistor response to eye',
                   'What the 1-tap DFE contributes', 'not routed', 'held-clock',
                   'not an end-to-end', 'local random', '-54.92', 'S1-S9'):
        assert phrase in text
    widgets = list(doc[0].widgets())
    assert len(widgets) == 11
    assert all(not w.field_value for w in widgets)
    assert not any('Jai Kaushik' in p.get_text() for p in doc)


def test_receipt_counts_reconcile_without_claiming_rl_discovery():
    from nebula.report.final_submission import load_receipt_evidence
    receipt = load_receipt_evidence()
    assert receipt['conditions'] == 315
    assert receipt['policy_visits'] == 2406
    assert receipt['rl_selected'] + receipt['centered'] + receipt['recovered'] == 315
    assert receipt['fallback_example']['selected'] not in receipt['fallback_example']['visits']


def test_report_rejects_content_inside_footer():
    from nebula.report.final_submission import FinalReport
    report = FinalReport.__new__(FinalReport)
    report.n = 7
    report.y = 47
    with pytest.raises(ValueError, match='overlaps the footer'):
        report.end()
