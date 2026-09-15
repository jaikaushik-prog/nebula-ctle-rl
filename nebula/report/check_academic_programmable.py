"""Read-only artifact checks followed by a separate closeout provenance record."""
from pathlib import Path
import hashlib,json,re,zipfile
from datetime import datetime,timezone
from docx import Document
from pypdf import PdfReader
from lxml import etree

ROOT=Path(__file__).resolve().parents[2]
REPORT=ROOT/'output/docx/Nebula_Academic_Final_Report_20260915_v2.docx'
SOURCE=ROOT/'output/docx/Nebula_Academic_Final_Report_20260915.docx'
RENDER=ROOT/'tmp/academic-closeout/programmable-report-verified'
EXPECTED='d40cc1cf297fe317b1ac7e9c414a54c7ec777d0d555d62965ba94a9e7b4ed17f'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    assert sha(REPORT)==EXPECTED,'Report changed since final visual review'
    source_at_build='f8233b46f1a701779961ce00a3730762977959609859a294b38757cb0bd746e2'
    source_resaved=sha(SOURCE)!=source_at_build
    # Preserve and disclose a later external save; never rewrite it or its prior hash.
    # Narrative diff was inspected and contains only the planned receiver additions.
    current=Document(REPORT);old=Document(SOURCE)
    assert [[c.text for c in r.cells] for r in current.tables[0].rows]==[[c.text for c in r.cells] for r in old.tables[0].rows]
    with zipfile.ZipFile(REPORT) as z:
        xml=etree.fromstring(z.read('word/document.xml'))
        equations=xml.xpath('count(//m:oMath)',namespaces={'m':'http://schemas.openxmlformats.org/officeDocument/2006/math'})
        assert equations==3
    figures=[int(re.match(r'Figure (\d+)\.',p.text)[1]) for p in current.paragraphs if re.match(r'Figure (\d+)\.',p.text)]
    assert figures==list(range(1,13)) and len(current.inline_shapes)==12
    reader=PdfReader(RENDER/(REPORT.stem+'.pdf'));assert len(reader.pages)==12
    assert 'Programmable receiver extension' in reader.pages[7].extract_text()
    assert 'References and evidence records' in reader.pages[11].extract_text()
    images=[RENDER/f'page-{i}.png' for i in range(1,13)];assert all(p.is_file() for p in images)
    text=' '.join([p.text for p in current.paragraphs]+[c.text for t in current.tables for r in t.rows for c in r.cells])
    assert len(text.split())==3905
    names=['nebula/programmable_receiver.py','nebula/programmable_option.py','nebula/recovery_workflow.py',
      'nebula/web/recovery_server.py','nebula/web/static/index.html','nebula/web/static/styles.css',
      'nebula/web/static/programmable_option.js','nebula/web/static/judge_evidence.js',
      'nebula/report/academic_programmable_update.py','nebula/report/check_academic_programmable.py',
      'nebula/report/programmable_receiver_visuals.py','nebula/experiments/review_programmable_receiver.py',
      'nebula/PROGRAMMABLE_RECEIVER_RESULTS_20260915.md','nebula/PROGRAMMABLE_RECEIVER_PRESENTATION_NOTE_20260915.md',
      'nebula/product_audits/entry160_programmable_receiver_review_20260915/review.json',
      'tmp/academic-closeout/programmable-ui.json','tmp/academic-closeout/programmable-download.json','tmp/academic-closeout/programmable-retry.json']
    record=dict(created_utc=datetime.now(timezone.utc).isoformat(),status='PASS_WITH_SOURCE_RESAVE' if source_resaved else 'PASS',report_sha256=EXPECTED,
      page_count=12,word_count=3905,figures=12,native_equations=3,member_fields_preserved=True,
      final_visual_review='All 12 pages inspected at original PNG size; pages 1-8 pixel-identical after final pagination-only edit, pages 9-12 reinspected.',
      source_sha256_at_build=source_at_build,original_report_current_sha256=sha(SOURCE),source_resaved_after_build=source_resaved,
      source_resave_note='Original DOCX later saved at 13:24 UTC; left untouched. Current narrative diff contains only planned receiver additions and identity fields match. New report remains pinned to its visually reviewed hash.',sources={n:sha(ROOT/n) for n in names},
      page_sha256={p.name:sha(p) for p in images},focused_tests=dict(before=16,after=26,after_seconds=3.25),
      ui_viewports=['1440x1000','1280x900'],actual_download_checked=True,temporary_failure_retry_checked=True,
      simulations_launched_by_closeout=0,historical_task_simulator_calls=8,core_gate_or_old_evidence_changed=False)
    out=ROOT/'output/docx/Nebula_Programmable_Closeout_20260915_sources.json';out.write_text(json.dumps(record,indent=2),encoding='utf-8')
    print(json.dumps({k:record[k] for k in ['status','page_count','word_count','figures','native_equations','report_sha256','member_fields_preserved']},indent=2))

if __name__=='__main__':main()
