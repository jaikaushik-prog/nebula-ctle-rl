"""Evidence identities and scope boundaries for the separate v3 report."""
import json
from pathlib import Path
import pytest
from nebula.report import final_submission_v3 as R


def test_v3_keeps_v2_and_blank_identity_fields():
    from pypdf import PdfReader
    R.verify_frozen_baseline()
    assert R.PDF.name=='Nebula_Final_Submission_12p_20260915_v3.pdf'
    reader=PdfReader(R.PDF)
    assert len(reader.pages)==12 and len(reader.get_fields())==11
    assert all(x.get('/V','')=='' for x in reader.get_fields().values())


def test_v3_measured_evidence_keeps_three_scope_boundaries():
    e=R.load_revision_evidence()
    assert [x['n_pass'] for x in e['cs']['candidates']]==[308,315,315]
    assert e['cs']['charged_invocations']==411
    assert e['generated']['correct_bits']==64
    assert e['generated']['whole_circuit_voltage_audit']['documented_ranges_ok'] is False
    assert e['generated']['full_receiver_verified'] is False
    assert e['live']['spice_calls']==274


def test_v3_manifest_binds_new_evidence_and_exact_screenshot():
    m=json.loads(R.MANIFEST.read_text(encoding='utf-8'))
    assert m['report_sha256']==R.sha(R.PDF)
    assert m['revision_evidence']==R.load_revision_evidence()
    for path in [R.CS_REVIEW,R.GEN_ROOT/'result.json',R.GEN_ROOT/'trace.txt',R.LIVE_ROOT/'workflow_receipt.json']:
        assert any(row['path']==path.relative_to(R.ROOT).as_posix() and row['sha256']==R.sha(path) for row in m['sources'])
    provenance=json.loads((R.V3_ASSETS/'desktop_provenance.json').read_text())
    assert provenance['sha256']==R.sha(R.V3_ASSETS/'desktop.png')


def test_v3_retains_circuit_narratives_and_current_claims():
    import fitz
    with fitz.open(R.PDF) as doc:
        assert len(doc)==len(doc.get_toc())==12
        text=' '.join(' '.join(p.get_text().split()) for p in doc)
    for claim in ['The source-degenerated CTLE','Reference current made physical','Physical attenuation and peaking',
       'What the 1-tap DFE contributes','164.766106','296.981','0.720','9.2636','281.4683','4/12','5/13',
       'no RL speed advantage','receiver/receiver.cir','live provider is unavailable','six dB near 2.1 GHz']:
        assert claim in text,claim


def test_v3_refuses_modified_generated_raw_evidence(monkeypatch,tmp_path):
    original=R.sha
    monkeypatch.setattr(R,'sha',lambda p:'tampered' if Path(p)==R.GEN_ROOT/'trace.txt' else original(p))
    with pytest.raises(ValueError,match='raw evidence changed'):
        R.load_revision_evidence()
