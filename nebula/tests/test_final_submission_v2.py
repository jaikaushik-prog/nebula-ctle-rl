"""Isolation and fail-closed publication boundaries for the v2 report."""
import hashlib

import pytest

from nebula.report import final_submission_v2 as report


def test_v2_has_separate_outputs_and_preserves_v1():
    assert report.PDF.name == 'Nebula_Final_Submission_12p_20260915_v2.pdf'
    assert len(report.PAGE_TITLES) == 12
    assert report.REVISION_PAGES == (3, 10, 11, 12)
    assert report.PDF.name not in report.FROZEN_V1
    report.verify_frozen_baseline()


def test_v2_refuses_unfinished_revision_before_writing(monkeypatch, tmp_path):
    output = tmp_path / 'must_not_exist.pdf'
    monkeypatch.setattr(report, 'PDF', output)
    monkeypatch.setattr(report, 'REVISION_READY', False)
    with pytest.raises(ValueError, match='not publishable'):
        report.build()
    assert not output.exists()


def test_v2_rejects_changed_frozen_artifact(monkeypatch, tmp_path):
    artifact = tmp_path / 'frozen.pdf'
    artifact.write_bytes(b'original frozen artifact')
    expected = hashlib.sha256(artifact.read_bytes()).hexdigest()
    monkeypatch.setattr(report, 'FROZEN_V1', {artifact.name: expected})
    report.verify_frozen_baseline(tmp_path)
    artifact.write_bytes(b'overwritten')
    with pytest.raises(ValueError, match='Frozen v1 artifact changed'):
        report.verify_frozen_baseline(tmp_path)


def test_v2_cannot_regenerate_frozen_figures(monkeypatch, tmp_path):
    output = tmp_path / 'must_not_exist.pdf'
    monkeypatch.setattr(report, 'PDF', output)
    monkeypatch.setattr(report, 'REVISION_READY', True)
    with pytest.raises(ValueError, match='immutable v1 figures'):
        report.build(regenerate_assets=True)
    assert not output.exists()


def test_v2_review_rejects_changed_campaign_summary(tmp_path):
    import json
    for name in ('summary.json', 'workflows.jsonl', 'protocol.json'):
        (tmp_path/name).write_text('{}\n', encoding='utf-8')
    proof = dict(status='PASS', source_freeze='PASS', checked_workflows=37,
                 expected_coverage=13, expected_benchmark=24)
    for key,name in [('summary_sha256','summary.json'), ('workflows_sha256','workflows.jsonl'), ('protocol_sha256','protocol.json')]:
        proof[key] = report.sha(tmp_path/name)
    review = tmp_path/'final_review.json'
    review.write_text(json.dumps(proof), encoding='utf-8')
    report.validate_campaign_review(tmp_path, review)
    (tmp_path/'summary.json').write_text('{"changed": true}', encoding='utf-8')
    with pytest.raises(ValueError, match='does not match summary.json'):
        report.validate_campaign_review(tmp_path, review)


def test_v2_pdf_retains_narratives_and_honest_campaign_scope():
    import json
    import fitz
    manifest=json.loads(report.MANIFEST.read_text(encoding='utf-8'))
    report.verify_sources(manifest['sources'])
    with fitz.open(report.PDF) as doc:
        assert len(doc)==len(doc.get_toc())==12
        assert len(list(doc[0].widgets()))==11
        assert all(not w.field_value for w in doc[0].widgets())
        text=' '.join(' '.join(p.get_text().split()) for p in doc)
    for claim in ('The source-degenerated CTLE', 'Reference current made physical',
                  'Physical attenuation and peaking', 'From transistor response to eye',
                  'What the 1-tap DFE contributes', 'infrastructure failure',
                  'no RL speed advantage', 'charged calls', '0.939', '166.085', '8766'):
        assert claim in text
