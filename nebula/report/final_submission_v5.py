"""Narrow v5 overlay: saved bounded tuning evidence; preserve earlier editions."""
import json
from pathlib import Path
import shutil
from nebula.report import final_submission_v4 as R
from nebula.deadline_evidence import diagnostics

PDF=R.OUT/'Nebula_Final_Submission_12p_20260915_v5.pdf'
MANIFEST=PDF.with_name(PDF.stem+'_sources.json')
REVIEW=PDF.with_name(PDF.stem+'_review.json')
ASSETS=R.ROOT/'nebula/report/final_submission_v5_assets'
V4_SHA='5619ae9f015f8e9d53c96300c79c3af854354e9409a5fded9323a8b41e053384'

class RevisedReport(R.FinalReport):
    def para(self,text,*args,**kwargs):
        text=text.replace('companion v4 source manifest','companion v5 source manifest')
        text=text.replace('nebula.report.final_submission_v4','nebula.report.final_submission_v5')
        text=text.replace('separate v4 outputs','separate v5 outputs')
        return super().para(text,*args,**kwargs)
    def figure(self,name,caption,height):
        if name=='pvt':height=150
        return super().figure(name,caption,height)
    def note(self,label,text):
        if label=='Deadline pilot.':
            label='Bounded programmable tuning.'
            text=('Two new calls measured 31 OP/AC snapshots per held-clock state on this independent reference. '
                'Both baseline checks pass. Five of 12 targets match in BOTH states within the existing .5 dB / 100 MHz tolerances; '
                'the standalone saved table matched 10/12. No 3 dB target matches the loaded sample. This is nominal AC only, '
                'not new end-to-end coverage, PVT or signed-model signoff. Setting 352 and 4/12 coverage are unchanged. [E15] '
                'The earlier FS / 1.71 V / 125 C analog pilot failed latch initialization; no valid analog-PVT coverage was added. [E10]')
        if label=='Retained electrical limit.':
            text=('The added DFE signed checks and whole-circuit voltage envelope pass, but six attenuator PMOS devices violate '
                'signed model ranges. All six Vds intervals cross zero; two off devices also have +0.299 V Vgs. Swapping terminal '
                'labels cannot close this gap. Full receiver verification remains false: analog/link PVT, noise/HD3, BER and reliability remain open. [E14,E16]')
        return super().note(label,text)
    def table(self,headings,rows,*args,**kwargs):
        if headings==['ADDITIONAL EVIDENCE','SOURCE RELATIVE TO REPOSITORY ROOT']:
            rows=[*rows[:2],['E6-E10 / E15-E16: scoped diagnostics',
                'Historical scopes remain in the manifest. New: nebula/DEADLINE_ENGINEERING_RESULTS_20260915.md; deadline_evidence.py recomputes saved tuning, RL cost/regret and PMOS findings with no simulation.']]
        return super().table(headings,rows,*args,**kwargs)

def build():
    if R.sha(R.PDF)!=V4_SHA:raise ValueError('Preserved v4 PDF changed')
    data=diagnostics()
    ASSETS.mkdir(exist_ok=True)
    for name in ('desktop.png','learning.png'):
        if not (ASSETS/name).exists():shutil.copyfile(R.V4_ASSETS/name,ASSETS/name)
    old={name:getattr(R,name) for name in ('PDF','MANIFEST','REVIEW','V4_ASSETS','FinalReport')}
    try:
        R.PDF=PDF;R.MANIFEST=MANIFEST;R.REVIEW=REVIEW;R.V4_ASSETS=ASSETS;R.FinalReport=RevisedReport
        R.build()
        manifest=json.loads(MANIFEST.read_text())
        sources=[Path(__file__),R.ROOT/'nebula/deadline_evidence.py',R.ROOT/'nebula/DEADLINE_ENGINEERING_RESULTS_20260915.md',
            R.ROOT/'nebula/web/static/engineering_diagnostics.js',R.ROOT/'nebula/experiments/review_loaded_tuning_bound.py']
        folder=R.ROOT/'nebula/product_audits/entry158_loaded_tuning_20260915'
        sources += [folder/name for name in ('summary.json','config.json','evidence_sha256.json')]
        manifest['sources'] += [R.source_record(p) for p in sources]
        manifest['source_claim_map'].update(E15=[9,12],E16=[8,12])
        manifest['deadline_diagnostics']=data
        manifest['preserved_v4_sha256']=V4_SHA
        manifest['scope']='Report reads saved evidence only. E15 records two separately approved nominal OP/AC calls; no report-build simulation or training.'
        R.verify_sources(manifest['sources']);MANIFEST.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    finally:
        for name,value in old.items():setattr(R,name,value)
    return PDF

if __name__=='__main__':build()
