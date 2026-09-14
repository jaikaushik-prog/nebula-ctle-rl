"""Source, structural and Poppler rendering checks for the final report."""
import json
import re
import shutil
import subprocess
from nebula.report.final_submission import PDF,MANIFEST,REVIEW,SCRATCH,ROOT,OUT,PRESERVED,RAW_PROOF,NOMINAL_ROOT,PVT_ROOT,sha,verify_sources


def main():
    import fitz
    from pypdf import PdfReader
    manifest=json.loads(MANIFEST.read_text(encoding='utf-8'))
    assert sha(PDF)==manifest['report_sha256']
    raw_proof=json.loads(RAW_PROOF.read_text(encoding='utf-8'))
    assert raw_proof['status']=='PASS'
    assert raw_proof['nominal']['manifest_sha256']==sha(NOMINAL_ROOT/'evidence_sha256.json')
    assert raw_proof['pvt']['manifest_sha256']==sha(PVT_ROOT/'evidence_sha256.json')
    verify_sources(raw_proof['sources'])
    assert raw_proof['nominal']['verified_files']==137 and raw_proof['nominal']['verified_archives']==10
    assert raw_proof['pvt']['verified_files']==362 and raw_proof['pvt']['verified_archives']==90
    assert any(x['path']==RAW_PROOF.relative_to(ROOT).as_posix() for x in manifest['sources'])
    verify_sources(manifest['sources'])
    for name,digest in PRESERVED.items():assert sha(OUT/name)==digest
    doc=fitz.open(PDF)
    assert len(doc)==manifest['page_count']==12
    assert len(doc.get_toc())==12
    pages=SCRATCH/'pages';pages.mkdir(parents=True,exist_ok=True)
    poppler=shutil.which('pdftoppm') or str(ROOT/'tmp/pdfs/poppler-runtime/Library/bin/pdftoppm.exe')
    subprocess.run([poppler,'-r','120','-png',str(PDF),str(pages/'page')],check=True,capture_output=True)
    problems=[];stats=[];texts=[]
    for i,page in enumerate(doc,1):
        text=page.get_text();texts.append(text)
        assert len(text)>500,(i,'too little text')
        for block in page.get_text('dict')['blocks']:
            for line in block.get('lines',[]):
                for span in line['spans']:
                    x0,y0,x1,y1=span['bbox']
                    if x0<0 or y0<0 or x1>page.rect.width+.5 or y1>page.rect.height+.5:
                        problems.append(dict(page=i,text=span['text'],bbox=span['bbox']))
        stats.append(dict(page=i,characters=len(text),content_bottom_pt=manifest['content_bottoms_pt'][i-1],render_sha256=sha(pages/f'page-{i:02d}.png')))
    text='\n'.join(texts)
    figures=[int(n) for n in re.findall(r'Figure\s+(\d+)\.',text)]
    assert figures==list(range(1,len(manifest['figures'])+1))
    assert not problems,problems
    assert '\ufffd' not in text and not re.search(r'\d\?\d|mm\?|\?C',text)
    assert '-54.92' in text and '-30' in text
    fields=PdfReader(PDF).get_fields();assert fields and len(fields)==11
    assert all(f.get('/V','')=='' for f in fields.values())
    annotations=PdfReader(PDF).pages[0]['/Annots']
    assert len(annotations)==11
    assert all('/AP' in a.get_object() and '/N' in a.get_object()['/AP'] for a in annotations)
    widgets=list(doc[0].widgets());assert len(widgets)==11 and all(not w.field_value for w in widgets)
    review=dict(report_sha256=sha(PDF),page_count=12,source_hash_checks='PASS',raw_archive_proof='PASS (Entry143 inherited completed verification; Entry144 verified in this report closeout)',previous_reports='PASS',text_bounds='PASS',outline='PASS',figure_sequence=figures,blank_acroform_fields='PASS (11)',renderer='Poppler pdftoppm 120 dpi',pages=stats,visual_review='PENDING')
    REVIEW.write_text(json.dumps(review,indent=2)+'\n',encoding='utf-8')
    print('PASS: 12 pages, source hashes, prior PDFs, text bounds, outline, figures and blank AcroForm. Visual review pending.')

if __name__=='__main__':main()
