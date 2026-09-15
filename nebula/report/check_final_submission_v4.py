"""Read-only v4 evidence and PDF structure check; emits only its new review JSON."""
import json
from pathlib import Path
from nebula.report.final_submission_v4 import PDF,MANIFEST,REVIEW,ROOT,sha,verify_sources

def check():
    import fitz
    from pypdf import PdfReader
    manifest=json.loads(MANIFEST.read_text(encoding='utf-8'))
    assert sha(PDF)==manifest['report_sha256']
    verify_sources(manifest['sources'])
    assert sha(PDF.with_name('Nebula_Final_Submission_12p_20260915_v3.pdf'))=='35011417c6c27aece63ef91194bc9f04ecc9fb14fdc91c248102c909c274988f'
    reader=PdfReader(PDF);fields=reader.get_fields()
    assert len(reader.pages)==12 and len(fields)==11
    assert all(f.get('/V','')=='' for f in fields.values())
    widgets=[a.get_object() for p in reader.pages for a in p.get('/Annots',[]) if a.get_object().get('/Subtype')=='/Widget']
    assert len(widgets)==11 and all(w.get('/V','')=='' for w in widgets)
    with fitz.open(PDF) as doc:
        assert len(doc)==len(doc.get_toc())==12
        texts=[' '.join(p.get_text().split()) for p in doc]
        for p in doc:
            for block in p.get_text('dict')['blocks']:
                for line in block.get('lines',[]):
                    for s in line['spans']:
                        x0,y0,x1,y1=s['bbox'];assert x0>=0 and y0>=0 and x1<=p.rect.width+.5 and y1<=p.rect.height+.5
        for needle,page in [('S3 / Failed',2),('0.548',4),('oracle regret',4),('setting 352',5),('fixed physical CTLE',5),('296.981',8),('no RL speed advantage',10),('--run-root',11),('Three evidence branches',12)]:
            assert needle in texts[page-1],(page,needle)
    assert len(manifest['figures'])==12
    assert [x['number'] for x in manifest['figures']]==list(range(1,13))
    assert '4608cf1c525f4e59b2d5226059b0ce5d/design_schematic.png' in manifest['figures'][3]['asset']
    return dict(status='PASS',page_count=12,blank_identity_fields=11,figures=12,
        report_sha256=sha(PDF),sources_checked=len(manifest['sources']),simulations_launched=0,
        visual_review='All 12 page PNGs reviewed separately by the assistant; source/structure checks do not substitute for that review.')

if __name__=='__main__':
    result=check();REVIEW.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,indent=2))
