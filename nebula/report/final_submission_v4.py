"""Separate 12-page revision from verified recovery and frozen hardware evidence."""
from __future__ import annotations
import json
from pathlib import Path
from nebula.report.submission_story import source_record, verify_sources, sha
from nebula.report.competition_2026 import ROOT, OUT, FINAL
from nebula.report.competition_submission import PHYS, WIN_BENCH, WIN_RECOVERY, POST_DIRS
from nebula.web.hardware_checkpoint import NOMINAL_ROOT, PVT_ROOT, NOMINAL_SUMMARY, PVT_SUMMARY, NOMINAL_NETLIST
PDF=OUT/'Nebula_Final_Submission_12p_20260915_v4.pdf'
MANIFEST=PDF.with_name(PDF.stem+'_sources.json')
REVIEW=PDF.with_name(PDF.stem+'_review.json')
RAW_PROOF=OUT/'Nebula_Final_Submission_12p_20260915_raw_verification.json'
DETAILED_PDF=OUT/'Nebula_Submission_Report_20260914.pdf'
ASSETS=ROOT/'nebula/report/final_submission_assets'
V3_ASSETS=ROOT/'nebula/report/final_submission_v3_assets'
SCRATCH=ROOT/'tmp/final-submission-report-v4'
V4_ASSETS=ROOT/'nebula/report/final_submission_v4_assets'
RECEIPT_SOURCE=ROOT/'nebula/product_demo/rl_hybrid_9db_1p9ghz/design.json'
CAMPAIGN=ROOT/'nebula/product_audits/submission_recovery_20260915'
CAMPAIGN_REVIEW=CAMPAIGN/'final_review.json'
RECOVERY_OUTPUT=CAMPAIGN/'coverage_012_6db_2p1ghz_rl_r0/output'
RECOVERY_ROWS=RECOVERY_OUTPUT/'physical_recovery/candidate_02_setting_352/fixed_pvt.jsonl'
ANOMALY_ROOT=CAMPAIGN/'benchmark_005_9db_1p9ghz_classical_r0/output/physical_recovery/candidate_01_setting_490'
HARDENING=ROOT/'nebula/SUBMISSION_RECOVERY_HARDENING_20260915.json'
SAVED_COPY=ROOT/'nebula/product_demo/submission_runs_20260915_v2/94b55321c7f245df8093284b402c8a40'
PAGE_TITLES=('NEBULA','Requirements and evidence coverage','From specification to circuit',
 'What the learned policy does','The circuit and its physical bias','Physical attenuation and peaking',
 'From transistor response to eye','The generated transistor receiver','Independent reference: PVT scope',
 'Recovery and complete workflow cost','The designer workflow','Conclusions and evidence guide')
PRESERVED={
 'Nebula_Submission_Report_20260914.pdf':'169845fac6690d16630a18d70d7118b0936b66ce9bca277aed7380ae2025c15f',
 'Nebula_Competition_Report_Academic.pdf':'a573db02335879e0a6a0b3feb2c9eeea2172c2f3f4b4e4699dfc8123c8f90670',
 'Nebula_Competition_Report.pdf':'3cd67ffc933b8f369d601a72f16e39295542780777ca5bccc797135278faf43b'}
NAVY='#0b2342'; TEAL='#008aa1'; MUTED='#52677b'


# Final campaign review is independently hash-checked before every build.
REVISION_READY = True
REVISION_PAGES = (1, 2, 3, 8, 9, 10, 11, 12)
FROZEN_V1 = {'Nebula_Final_Submission_12p_20260915.pdf': '764d6f510168430d7386e2b5189f8fe19c6d1c0bef223818d0932bef85364446', 'Nebula_Final_Submission_12p_20260915_raw_verification.json': 'fef30241f591cfae617facddb2312bc5ffc42c17840b4d0b1c0e3b2decee51d8', 'Nebula_Final_Submission_12p_20260915_review.json': '6bcd64891d553d70576bdddbe7f448f36297e4bc5a89e4df14245d598a2a0c75', 'Nebula_Final_Submission_12p_20260915_sources.json': '776c871fc1086fccc82dd66625f94d2abadebbaeafb13aa58be6094bfad65c18'}


FROZEN_V2 = {'Nebula_Final_Submission_12p_20260915_v2.pdf': 'd82c7ba8d00827e36293dc12b15570a9246143ebb35fce87d5e7161aea5658a9', 'Nebula_Final_Submission_12p_20260915_v2_review.json': '4c149107bd6794d2b60bf2675537e11f44813dfd1218ede138a4caf22d7f0460', 'Nebula_Final_Submission_12p_20260915_v2_sources.json': '6299aac6ed582130c5ab3e1cee0b8de4ab8190b8955109b28915cdae6386447c'}


def verify_frozen_baseline(directory=OUT):
    """Fail if any completed v1 deliverable has been overwritten."""
    for name, expected in (FROZEN_V1 | FROZEN_V2).items():
        if sha(Path(directory)/name) != expected:
            raise ValueError(f'Frozen v1 artifact changed: {name}')


def require_completed_revision():
    if not REVISION_READY:
        raise ValueError('V3 is not publishable: frozen campaign metrics are not yet integrated')


def validate_campaign_review(directory=CAMPAIGN, review_path=CAMPAIGN_REVIEW):
    """Bind independent review to the exact campaign files before publication."""
    proof=json.loads(Path(review_path).read_text(encoding='utf-8'))
    if proof.get('status')!='PASS' or proof.get('source_freeze')!='PASS':
        raise ValueError('Campaign has not passed the independent final review')
    for key,name in [('summary_sha256','summary.json'),('workflows_sha256','workflows.jsonl'),('protocol_sha256','protocol.json')]:
        if proof.get(key)!=sha(Path(directory)/name):
            raise ValueError(f'Campaign proof does not match {name}')
    if (proof.get('checked_workflows'),proof.get('expected_coverage'),proof.get('expected_benchmark'))!=(37,13,24):
        raise ValueError('Campaign final-review membership is incomplete')
    return proof


def load_campaign_evidence():
    """Use only the completed campaign, after the independent deep-check proof."""
    validate_campaign_review()
    hardening=json.loads(HARDENING.read_text(encoding='utf-8'))
    old=hardening['historical_campaign']
    if sha(ROOT/old['checked_original_snapshot'])!=old['frozen_physical_design_sha256'] or old['measurement_artifacts_edited'] or old['campaign_reexecuted']:
        raise ValueError('Post-campaign hardening is not separated from historical evidence')
    if sha(ROOT/'nebula/physical_design.py')!=hardening['source_changes'][0]['after_sha256']:
        raise ValueError('Current physical implementation differs from the hardening record')
    summary=json.loads((CAMPAIGN/'summary.json').read_text(encoding='utf-8'))
    rows=[json.loads(line) for line in (CAMPAIGN/'workflows.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    coverage=[r for r in rows if r['purpose']=='coverage']
    benchmark=[r for r in rows if r['purpose']=='benchmark']
    if len(rows)!=37 or len(coverage)!=13 or len(benchmark)!=24 or summary.get('unknown_call_workflows')!=0:
        raise ValueError('Campaign is incomplete or has unknown simulator accounting')
    if summary.get('coverage_complete') is not True or summary.get('benchmark_complete') is not True or summary.get('stop_reason')!='schedule_complete':
        raise ValueError('Campaign completion flags do not establish a finished schedule')
    if any(r.get('outcome')=='unrun' for r in summary['readiness_matrix']):
        raise ValueError('Campaign still contains unrun workflows')
    selected=next(r for r in coverage if r['target_id']=='6db_2p1ghz')
    if not selected['delivered_success'] or [(a['setting'],a['n_pass']) for a in selected['attempts']]!=[(288,314),(352,315)]:
        raise ValueError('The registered recovery demonstration changed')
    design=json.loads((RECOVERY_OUTPUT/'design.json').read_text(encoding='utf-8'))
    fixed=[json.loads(line) for line in RECOVERY_ROWS.read_text(encoding='utf-8').splitlines() if line.strip()]
    links=[link for row in fixed for link in row['links']]
    if len(fixed)!=45 or len(links)!=315 or not all(link['model_pass'] for link in links):
        raise ValueError('Recovered fixed-circuit coverage is incomplete')
    return dict(summary=summary,rows=rows,coverage=coverage,benchmark=benchmark,selected=selected,design=design,
        min_eye_h_v=min(link['bridge_eye_h_v'] for link in links),
        min_eye_w_ui=min(link['bridge_eye_w_ui'] for link in links),
        coverage_calls=sum(r['spice_calls'] for r in coverage),
        coverage_parent_s=sum(r['parent_wall_s'] for r in coverage),
        benchmark_calls={arm:sum(r['spice_calls'] for r in benchmark if r['selection_mode']==arm) for arm in ('rl','classical')})


CS_ROOT=ROOT/'nebula/product_audits/continuous_cs_coverage_20260915'
CS_REVIEW=ROOT/'nebula/CONTINUOUS_CS_COVERAGE_REVIEW_20260915.json'
GEN_ROOT=ROOT/'nebula/product_audits/generated_receiver_6db_2p1ghz_20260915'
LIVE_ROOT=ROOT/'nebula/product_demo/submission_runs_20260915_v2/4608cf1c525f4e59b2d5226059b0ce5d'

def load_revision_evidence():
    read=lambda path: json.loads(path.read_text(encoding='utf-8'))
    cs=read(CS_ROOT/'summary.json');proof=read(CS_REVIEW)
    if proof['status']!='PASS' or proof['manifest_verified_files']!=2105:
        raise ValueError('Continuous-Cs independent review incomplete')
    for key,name in [('summary_sha256','summary.json'),('manifest_sha256','evidence_sha256.json')]:
        if proof[key]!=sha(CS_ROOT/name):raise ValueError('Continuous-Cs proof hash changed')
    if not cs['registered_candidates_completed'] or not cs['source_fingerprints_unchanged'] or cs['charged_invocations']!=411:
        raise ValueError('Continuous-Cs campaign did not complete unchanged')
    if [(r['cs_factor'],r['n_pass'],r['n_points']) for r in cs['candidates']]!=[(1.01,308,315),(1.02,315,315),(1.03,315,315)]:
        raise ValueError('Continuous-Cs candidate membership or outcomes changed')
    for row in cs['candidates']:
        folder=CS_ROOT/row['candidate_id']
        if sha(folder/'result.json')!=row['result_sha256'] or sha(folder/'evidence_sha256.json')!=row['manifest_sha256']:
            raise ValueError('Continuous-Cs result or original manifest changed')
    generated=read(GEN_ROOT/'result.json');review=read(GEN_ROOT/'independent_review.json')
    if review['status']!='PASS' or len(review['checks'])!=17 or not all(review['checks'].values()):
        raise ValueError('Generated receiver independent review failed')
    for name,digest in review['evidence_sha256'].items():
        path=(GEN_ROOT/name).resolve()
        if not path.is_relative_to(GEN_ROOT.resolve()) or sha(path)!=digest:
            raise ValueError('Generated receiver raw evidence changed')
    if generated['correct_bits']!=64 or generated['scored_bits']!=64 or not generated['signal_gate_pass'] or generated['full_receiver_verified']:
        raise ValueError('Generated receiver scope differs from nominal-only evidence')
    if generated['whole_circuit_voltage_audit']['documented_ranges_ok'] is not False:
        raise ValueError('Signed transistor model-domain limitation must remain explicit')
    live=read(LIVE_ROOT/'workflow_receipt.json')
    if not live['delivered_success'] or live['spice_calls']!=274 or round(live['wall_s'],6)!=164.766106:
        raise ValueError('Live recovery receipt changed')
    if [(r['setting'],r['n_pass'],r['accepted']) for r in live['attempts']]!=[(288,314,False),(352,315,True)]:
        raise ValueError('Live recovery attempt sequence changed')
    for name,digest in live['artifact_sha256'].items():
        path=(LIVE_ROOT/name).resolve()
        if not path.is_relative_to(LIVE_ROOT.resolve()) or sha(path)!=digest:raise ValueError('Live recovery output hash changed')
    return dict(cs=cs,generated=generated,live=live,live_design=read(LIVE_ROOT/'design.json'))


def generate_revision_figure(evidence):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    a=evidence['generated']['aperture'];x=np.asarray(a['offsets_ui'])
    fig,ax=plt.subplots(figsize=(8,2.6),layout='constrained')
    ax.plot(x,np.asarray(a['positive_min_v'])*1000,color=TEAL,label='Minimum positive-bit voltage',lw=1.8)
    ax.plot(x,np.asarray(a['negative_max_v'])*1000,color=NAVY,label='Maximum negative-bit voltage',lw=1.8)
    interval=a['positive_eye_interval'];ax.axvspan(interval['left_ui'],interval['right_ui'],color=TEAL,alpha=.08)
    ax.axhline(0,color='#9eacb8',lw=.7);ax.axvline(a['sample_anchor_ui'],color='#b56824',ls='--',lw=1)
    ax.set(xlabel='Offset from registered clock edge (UI)',ylabel='DFE summer voltage (mV)',xlim=(-.5,.5))
    ax.legend(fontsize=8,loc='upper left');ax.grid(alpha=.16)
    for spine in ('top','right'):ax.spines[spine].set_visible(False)
    V3_ASSETS.mkdir(exist_ok=True);fig.savefig(V3_ASSETS/'generated_aperture.png',dpi=180);plt.close(fig)


def load_receipt_evidence():
    p=json.loads(RECEIPT_SOURCE.read_text(encoding='utf-8'))
    s,v=p['search'],p['verification']; rows=v['per_condition']
    assert len(rows)==v['n_points']==v['n_pass']==315
    assert all(r['compliant'] for r in rows)
    visits=sum(len(r['policy_trace']['settings_tried']) for r in rows)
    assert visits==s['rl_proposals']==s['shield_verifier_calls']
    refined=sum(r['selection_reason']=='target-refinement' for r in rows)
    recovered=sum(r['source']=='bank-fallback' and r['selection_reason']!='target-refinement' for r in rows)
    selected=sum(r['source']=='rl-shield' for r in rows)
    assert refined==s['target_refinements'] and recovered==s['safety_fallbacks']
    assert selected+refined+recovered==len(rows)
    example=next(r for r in rows if r['corner']=='fs/0.95/125C' and r['channel_loss_db']==3)
    return dict(conditions=len(rows),policy_visits=visits,rl_selected=selected,centered=refined,
        recovered=recovered,table_checks=s['table_rows_checked'],setting=s['setting'],
        wall_s=p['wall_s'],export_wall_s=p['export_wall_s'],simulations=p['simulations'],
        fallback_example=dict(visits=example['policy_trace']['settings_tried'],selected=example['setting'],reason=example['selection_reason']))


class FinalReport:
    """Measured flow and fixed total pages; overflow is an explicit failure."""
    def __init__(self):
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        for name,file in [('Body','arial.ttf'),('Bold','arialbd.ttf'),('Italic','ariali.ttf')]:
            if name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(name,str(Path('C:/Windows/Fonts')/file)))
        pdfmetrics.registerFontFamily('Body',normal='Body',bold='Bold',italic='Italic',boldItalic='Bold')
        OUT.mkdir(parents=True,exist_ok=True)
        self.c=canvas.Canvas(str(PDF),pagesize=A4,pageCompression=1)
        self.c.setTitle('Nebula - Final Submission: RL-assisted analog circuit design');self.c.setAuthor('')
        self.w,self.h=A4;self.x=42;self.width=self.w-84;self.n=0;self.figures=[];self.bottoms=[];self.y=0
    def color(self,v):
        from reportlab.lib.colors import HexColor
        return HexColor(v)
    def new(self,section,subtitle):
        if self.n:self.end()
        self.n+=1;title=PAGE_TITLES[self.n-1];c=self.c
        c.bookmarkPage(f'p{self.n}');c.addOutlineEntry(title,f'p{self.n}',level=0,closed=False)
        c.setFillColor(self.color(TEAL));c.rect(self.x,self.h-34,28,3,fill=1,stroke=0)
        c.setFont('Bold',8);c.drawString(self.x+37,self.h-34,section.upper())
        c.setFillColor(self.color(NAVY));c.setFont('Bold',28 if self.n==1 else 23)
        c.drawString(self.x,self.h-75,title);self.y=self.h-89
        self.para(subtitle,size=11,color=MUTED,gap=16)
    def para(self,text,size=10.7,gap=9,color=NAVY):
        from reportlab.platypus import Paragraph
        from reportlab.lib.styles import ParagraphStyle
        p=Paragraph(text,ParagraphStyle('body',fontName='Body',fontSize=size,leading=size*1.36,textColor=self.color(color)))
        _,height=p.wrap(self.width,1000);p.drawOn(self.c,self.x,self.y-height);self.y-=height+gap
    def heading(self,text):self.para(text,size=13,gap=7,color=TEAL)
    def table(self,headings,rows,widths=None,size=9.5):
        from reportlab.platypus import Table,TableStyle,Paragraph
        from reportlab.lib.styles import ParagraphStyle
        size *= {2:1.05,3:1.045,4:1.10,9:1.045,10:1.025,12:1.10}.get(self.n,1)
        padding={2:9,3:5,4:11,9:10,10:7,12:4}.get(self.n,7)
        widths=widths or [self.width/len(headings)]*len(headings)
        def p(s,bold=False):
            return Paragraph(str(s),ParagraphStyle('cell',fontName='Bold' if bold else 'Body',fontSize=size if not bold else size-.2,leading=size*1.32,textColor=self.color('#ffffff' if bold else NAVY)))
        t=Table([[p(s,True) for s in headings]]+[[p(s) for s in row] for row in rows],colWidths=widths,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),self.color(NAVY)),('ROWBACKGROUNDS',(0,1),(-1,-1),[self.color('#f0f5f8'),self.color('#ffffff')]),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),padding),('BOTTOMPADDING',(0,0),(-1,-1),padding),('LINEBELOW',(0,-1),(-1,-1),.5,self.color('#c9d6e0'))]))
        _,height=t.wrap(self.width,1000);t.drawOn(self.c,self.x,self.y-height);self.y-=height+12
    def figure(self,name,caption,height):
        from reportlab.lib.utils import ImageReader
        path=(V4_ASSETS if name in ('desktop','learning') else V3_ASSETS if name=='generated_aperture' else ASSETS)/(name+'.png')
        if name=='selected_ctle':path=LIVE_ROOT/'design_schematic.png'
        if not path.is_file():raise FileNotFoundError(f'Required verified report image is missing: {path}')
        im=ImageReader(str(path));iw,ih=im.getSize();scale=min(self.width/iw,height/ih);dw,dh=iw*scale,ih*scale
        self.c.drawImage(im,self.x+(self.width-dw)/2,self.y-dh,width=dw,height=dh,mask='auto');self.y-=dh+5
        number=len(self.figures)+1;self.para(f'<b>Figure {number}.</b> '+caption,size=8.6,gap=10,color=MUTED)
        self.figures.append(dict(number=number,page=self.n,asset=path.relative_to(ROOT).as_posix(),caption=caption))
    def note(self,label,text):self.para('<b>'+label+'</b> '+text,size=10.1,gap=9,color=MUTED)
    def owner_fields(self):
        c=self.c
        for label,name in [('Team','team'),('College','college')]:
            c.setFont('Bold',9);c.setFillColor(self.color(MUTED));c.drawString(self.x,self.y-12,label)
            c.acroForm.textfield(name=name,tooltip=label,x=self.x+53,y=self.y-20,width=self.width-53,height=20,borderStyle='underlined',borderWidth=.5,borderColor=self.color('#a3b8c7'),fillColor=self.color('#ffffff'),textColor=self.color(NAVY),fontSize=10,forceBorder=True,value='');self.y-=35
        cols=[('Member name',190),('Contact number',126),('Email ID',self.width-316)];x=self.x
        for label,width in cols:c.setFont('Bold',8.5);c.drawString(x,self.y-11,label);x+=width
        self.y-=19
        for row in range(3):
            x=self.x
            for col,(_,width) in enumerate(cols):
                c.acroForm.textfield(name=f'member_{row+1}_{col}',tooltip=f'Member {row+1} '+cols[col][0],x=x,y=self.y-22,width=width-8,height=22,borderStyle='underlined',borderWidth=.5,borderColor=self.color('#a3b8c7'),fillColor=self.color('#ffffff'),textColor=self.color(NAVY),fontSize=9,forceBorder=True,value='');x+=width
            self.y-=35
        self.y-=6
    def end(self):
        if self.y < 48:
            raise ValueError(f'Page {self.n} content overlaps the footer: {self.y:.1f} pt remaining')
        self.bottoms.append(round(self.h-self.y,2));c=self.c;c.setStrokeColor(self.color('#d0dde5'));c.setLineWidth(.5);c.line(self.x,35,self.w-self.x,35)
        c.setFillColor(self.color(MUTED));c.setFont('Body',8);c.drawString(self.x,23,'NEBULA  |  Final submission  |  15 September 2026');c.drawRightString(self.w-self.x,23,f'{self.n:02d} / 12');c.showPage()
    def save(self):self.end();assert self.n==12;self.c.save()


def load_final_evidence():
    """Check original manifests, exact compressed bytes and all non-trace files.

    The frozen archive index binds raw digests to exact gzip bytes. Rebuilding
    a PDF need not decompress every multi-gigabyte PVT trace: the original raw
    equivalence check remains recorded in the preserved report, while this
    loader verifies that every stored archive and its pinned index is unchanged.
    The nominal plotted trace is separately read by the existing eye loader.
    """
    import hashlib
    from nebula.report.competition_submission import load_evidence
    from nebula.web.hardware_checkpoint import build_hardware_checkpoint
    from nebula.web.hardware_visuals import devices
    detailed=json.loads(DETAILED_PDF.with_name(DETAILED_PDF.stem+'_sources.json').read_text(encoding='utf-8'))
    source_map={x['path']:x for x in detailed['sources']}
    checks=[]
    for folder in (NOMINAL_ROOT,PVT_ROOT):
        index_path=folder/'trace_archives.json';manifest_path=folder/'evidence_sha256.json'
        verify_sources([source_map[index_path.relative_to(ROOT).as_posix()],source_map[manifest_path.relative_to(ROOT).as_posix()]])
        original=json.loads(manifest_path.read_text());index=json.loads(index_path.read_text())
        assert sha(manifest_path)==index['original_manifest_sha256']
        traced=set()
        for row in index['archives']:
            raw=(folder/row['raw']).resolve();compressed=(folder/row['gzip']).resolve()
            assert raw.is_relative_to(folder.resolve()) and compressed.is_relative_to(folder.resolve())
            assert row['raw'] not in traced and row['gzip']==row['raw']+'.gz'
            assert original[row['raw']]==row['raw_sha256']
            assert compressed.stat().st_size==row['gzip_bytes']
            with compressed.open('rb') as stream: actual=hashlib.file_digest(stream,'sha256').hexdigest()
            assert actual==row['gzip_sha256']
            traced.add(row['raw'])
        assert traced=={k for k in original if Path(k).name in ('trace.txt','terminals.txt')}
        for key,digest in original.items():
            if key not in traced:
                path=(folder/key).resolve();assert path.is_relative_to(folder.resolve())
                assert sha(path)==digest
        checks.append(dict(verified_files=len(original),verified_archives=len(traced),manifest_sha256=sha(manifest_path),scope='Exact compressed archives and non-trace files; raw equivalence inherited from pinned original index, not re-decompressed.'))
    rows=devices();assert len(rows)==73
    return dict(hardware=build_hardware_checkpoint(),legacy=load_evidence(),device_count=73,devices=rows,archive_checks=checks)


def build(e=None, regenerate_assets=False):
    verify_frozen_baseline()
    if sha(OUT/'Nebula_Final_Submission_12p_20260915_v3.pdf') != '35011417c6c27aece63ef91194bc9f04ecc9fb14fdc91c248102c909c274988f':
        raise ValueError('Preserved v3 PDF changed')
    require_completed_revision()
    from nebula.report.submission_control_plot import plot_saved_controls
    plot_saved_controls(V4_ASSETS/'learning.png')
    if regenerate_assets:
        raise ValueError('V3 reuses immutable v1 figures; generate new revision assets separately')
    for filename,digest in PRESERVED.items():
        if sha(OUT/filename)!=digest:raise ValueError(f'Preserved report changed: {filename}')
    if e is None:e=load_final_evidence()
    rc=load_receipt_evidence()
    campaign=load_campaign_evidence()
    revision=load_revision_evidence()
    h=e['hardware'];n=h['nominal'];p=h['pvt'];agg=e['legacy']['final']['aggregate'];bench=e['legacy']['winning']['benchmark']['aggregate'];r=FinalReport()
    r.new('Final report / PCIe Gen2 equalizer','RL-assisted automated analog circuit design with SKY130 and ngspice')
    r.para('<b>Specifications in. A circuit, measured specifications and an auditable decision out.</b>',size=15,gap=12)
    r.para('Nebula turns target specifications into a measured physical CTLE through learned candidate search, deterministic recovery and fresh transistor verification. The 512-setting bank supports search; the accepted exported circuit is the result. That selected CTLE can now be connected to a transistor one-tap DFE, with structural and measured claims kept separate.')
    r.figure('architecture','One design flow: search proposes candidates, fresh verification accepts one circuit, and its exact artifacts preserve the decision trail.',110)
    r.table(['AUTOMATED RECOVERY','MEASURED PROGRESS','REVIEWABLE OUTPUT'],[['288 rejected; 352 accepted;<br/>315/315 CTLE model conditions','Physical grid evidence: 4/12;<br/>generated DFE: 64/64 nominal','Exact CTLE + structural receiver<br/>decks, traces and source hashes']],size=9.2)
    r.para('The generated 6 dB / 2.1 GHz receiver scores 64/64 nominal decisions with a 296.981 mV eye, 0.720 UI aperture and 9.2636 mW VDD draw. Signed attenuator PMOS model-domain findings keep full receiver verification false. A separate 9 dB / 1.9 GHz reference provides earlier nominal analog and 45-point link-PVT evidence. [E1-E2,E14]',size=10,gap=11)
    r.owner_fields()
    r.note('Contribution.', 'A learned proposal stage, automatic physical recovery and independently reviewed transistor evidence make the engineering decisions inspectable. This report includes all front matter and references within 12 pages.')

    r.new('01 / Problem and deliverables','The requested outcome is an automated design flow whose circuit claims survive verification.')
    r.para('At 5 Gbps, one unit interval is 200 ps and Nyquist is 2.5 GHz. Channel loss spreads each symbol into its neighbors. The prescribed equalizer combines one source-degenerated CTLE stage with variable Rs/Cs and one DFE tap. The official deliverable is an RL-based Python framework: target specifications in, seamless SPICE integration, final schematic and resulting specifications out. LLM-based interaction is a bonus. [E7]',size=10.3)
    r.table(['SPEC / STATUS','REQUIRED TARGET','CIRCUIT OWNERSHIP / EVIDENCE'],[
     ['S1 / Verified pass','5 Gbps NRZ; 2.5 GHz Nyquist','200 ps UI and nominal NRZ transistor waveform. Not full PCIe protocol signoff.'],
     ['S2 / Partial evidence','One-stage CTLE, variable Rs/Cs + 1-tap DFE','Selected 352: fixed Rs/Cs; transistor DFE nominal. Variable controls belong to the separate 9 dB reference.'],
     ['S3 / Failed','On-demand 3-12 dB;<br/>1.25-2.5 GHz','Only 4/12 combined grid targets. Selected 352: 6.6147 dB / 2.1595 GHz. Full range not delivered.'],
     ['S4 / Partial evidence','HD3 below -30 dBc;<br/>100 MHz input','Selected CTLE nominal -84.5045 dBc. Separate receiver reference about -54.92 dBc. Selected receiver HD3 open.'],
     ['S5 / Partial evidence','Below 1.5 mVrms;<br/>10 MHz-5 GHz','Selected CTLE maximum 0.680353 mVrms. Separate reference held-clock 0.654051 mVrms; periodic receiver noise open.'],
     ['S6 / Partial evidence','Below 15 mW','Selected CTLE maximum 9.80212 mW; selected receiver nominal 9.2636 mW. External generators excluded.'],
     ['S7 / Partial evidence','Below 0.05 mm2;<br/>130 nm PDK','Selected geometry subtotal 0.00734015 mm2; independent reference 0.014715766 mm2. No routed layout.'],
     ['S8 / Partial evidence','Above 100 mV AND<br/>0.4 UI','Selected ideal-DFE minima: 178.288 mV / 0.796875 UI. Selected transistor nominal: 296.981 mV / 0.675 UI above 100 mV.'],
     ['S9 / Partial evidence','5 processes x 3 VDD x<br/>3 temperatures','Selected CTLE + ideal DFE: 45 x 7 conditions. Selected transistor receiver nominal only; full simultaneous S3-S8 open.'],
    ],[104,124,r.width-228],size=8.5)
    r.table(['JUDGING CRITERION','WHERE THE SUBMISSION PROVIDES EVIDENCE'],[
     ['Deliverable coverage','Framework/input/output: pp.3,10-11; circuit/specifications: pp.5-9; source guide: p.12.'],
     ['Innovation','Learned candidate search, automatic recovery, continuous-Cs refinement and guarded LLM interaction: pp.3-4,10-11.'],
     ['Thought process','Retained failed attempts, unchanged gates, nominal receiver review and signed-domain limits: pp.3,6,8-10.'],
    ],[116,r.width-116],size=8.9)

    r.new('02 / Architecture','The learned bank is a candidate-search stage in one physical design workflow.')
    r.figure('architecture','The 512-setting bank guides candidate search. Fresh transistor measurements, not cached scores or LLM wording, determine physical acceptance.',116)
    r.table(['EVIDENCE','WHAT IS VERIFIED','WHAT IS NOT TRANSFERRED'],[
      ['Accepted physical CTLE','One fixed circuit over 45 corners x seven constructed losses; ideal behavioral DFE scoring.','The 315-condition gate is not transistor DFE or full receiver verification.'],
      ['Generated transistor receiver','Selected 6 dB / 2.1 GHz CTLE plus physical DFE; one nominal finite-pattern test.','Nominal signal pass does not clear signed PMOS limits or establish PVT.'],
      ['Independent 9 dB reference','Separate 73-device configurable receiver, nominal analog and 45-point transistor link PVT.','Its measurements do not replace evidence for a new generated circuit.'],
    ],[104,207,r.width-311],size=9.2)
    r.heading('Physical target evidence: 3/12 to 4/12 grid requests')
    grid={(x['peaking_db'],x['f_peak_hz']):x for x in campaign['coverage']}
    labels={'accepted':'Pass','exhausted':'Physical fail','no_eligible':'No candidate'}
    r.table(['BOOST','1.25 GHz','1.90 GHz','2.50 GHz'],[
        [f'{boost:g} dB']+[('New Cs pass' if boost==6 and freq==2.5 else labels[grid[boost,freq*1e9]['status']]) for freq in (1.25,1.9,2.5)]
        for boost in (3.,6.,9.,12.)],[71,147,147,r.width-365],size=9)
    r.table(['6 dB / 2.5 GHz REFINEMENT','Cs x1.01','Cs x1.02','Cs x1.03'],[
       ['Unchanged 315-condition gate','308/315','315/315','315/315']], [205,102,102,r.width-409],size=8.8)
    r.note('Coverage accounting.', 'The historical grid remains 3/12. Adding this separately registered Cs pilot gives 4/12 tested grid requests, or 5/13 including the exposed 6 dB / 2.1 GHz recovery diagnostic; the whole grid was not rerun. The three-factor pilot charged 411 calls in 281.4683 s before final closeout, with 2,105 files checked and fingerprints unchanged. [E11,E13]')
    r.note('Automatic next step.', 'For exactly 6 dB / 2.5 GHz, production proposes Cs x1.02 in both selection modes, then runs a fresh unchanged 137-call gate. A prior pass never substitutes for new acceptance. Full-range tuning, mismatch and layout remain unverified. [E13]')

    r.new('03 / RL formulation','The learned contribution is a bounded search trajectory through characterized circuits.')
    r.table(['PART OF THE MDP','IMPLEMENTED DEFINITION'],[
     ['Observation','62 fields: requested boost/log frequency, trial fraction, current A/R/C codes and measured eye history. PVT, channel loss, compliance, quality and oracle are hidden.'],
     ['Actions / horizon','A, R or C one index up/down, or LOCK; boundary masks; at most eight measurements, including the fixed start and repeats. Bank = 8 x 8 x 8 = 512 settings.'],
     ['Quality / reward','q is compliant eye area normalized to the best compliant bank eye area for that identity, clipped to [0,1]. Infeasible candidates have q=0. Reward tracks quality change and penalizes a bad final lock.'],
     ['Training / acceptance','Imitation initialization then PPO; five frozen seeds. Deployment seed is preselected. The shield retains compliant visits; production adds classical fallback and centering.'],
    ],[103,r.width-103],size=9.3)
    r.figure('learning','Saved controls only. Left: post-review exposed diagnostics with the same eight-visit cap; the fixed arm uses one visit. Right: frozen FINAL raw policy versus shield. These are separate evaluation records, not a new held-out experiment. [E3-E4]',188)
    r.para(f'The frozen FINAL evaluation contains 2,430 non-overlapping request/loss/PVT identities, not independent transistor geometries. Mean q rises from 0.5619 to {agg["mean_quality"]:.4f}: gain {agg["quality_delta"]:.4f}, paired 95% interval [{agg["paired_quality_delta_ci95"][0]:.4f}, {agg["paired_quality_delta_ci95"][1]:.4f}]. Shielded compliance is {agg["mean_compliance_rate"]*100:.2f}%; raw policy q is 0.5481 with 64.44% compliance. The shield is essential. [E3]')
    r.note('Interpretation.', 'Within-bank mean oracle regret is 0.2831; only 20.91% of seed/identity outcomes lie within 0.05 of the oracle. Near-optimality is not established. Cached visit savings are not end-to-end RL speedup. No unrestricted MOS search or on-chip omniscient verifier is claimed.')
    r.new('04 / Final physical output','Only setting 352 is the final fixed physical CTLE for the selected 6 dB / 2.1 GHz request.')
    r.figure('selected_ctle','Exact generated setting-352 drawing, matched to the delivered design.cir. All 13 MOS devices, physical poly/MIM passives and shared net labels belong to this selected circuit. The transistor DFE is a separate nominal check (p.8). [E11,E14]',330)
    r.table(['SELECTED 352 / A5 R4 C0','FIXED PHYSICAL VALUES'],[
      ['Input pair / degeneration','W = 57.9767 um; L = 0.391149 um; nf = 4. Rs = 257.7459 ohm; Cs = 1.684649 pF.'],
      ['Load / operating point','RL = 254.6330 ohm; CL = 0.0326281 pF; input common mode = 1.501023 V. Nominal VDD power = 6.96579 mW.'],
    ],[150,r.width-150],size=9.3)
    r.para('The input pair converts differential voltage to current; resistive loads convert it back to voltage. Rs degenerates the low-frequency gain, while Cs bypasses that feedback at higher frequency. Separate tail devices preserve the two source nodes. The physical reference uses real transistors, a resistor and MIM bypass rather than an ideal tail supply.',size=10.3)
    r.note('First-order reasoning.', 'fz = 1/(2 pi Rs Cs), k = 1 + (gm + gmb) Rs/2, A_dc approximately gm RL/k. Rs is the full inter-source resistance; body effect matters. SPICE includes finite output resistance and parasitics. Fixed values are not programmable hardware. [E7,E11]')

    r.new('05 / Circuit narrative','Input excursion, relative peaking and absolute voltage gain answer different engineering questions.')
    r.figure('submission_attenuator','One leg of the earlier differential input attenuator [E6]; the other is identical. Three PMOS-switched shunts have real ON resistance and OFF parasitics.',139)
    r.para('The attenuator controls voltage presented to the active pair. This matters most on low-loss channels, where the minimum required CTLE boost can otherwise overdrive the stage. Peaking is a ratio to DC gain: about 9 dB of boost does not mean 9 dB of absolute gain. The input attenuator is not the source of CTLE peaking.')
    r.figure('submission_ac','Absolute voltage gain and the 45-corner envelope of the earlier fixed CTLE [E6]. These curves do not establish analog PVT for the later integrated receiver.',168)
    r.heading('From separate geometries to physical variable Rs/Cs')
    r.table(['DESIGN STEP','FINDING / CONSEQUENCE'],[
     ['Original 512-setting bank','Attenuator switches are netlisted. Rs/Cs codes select separately drawn passives; a code table alone is not a physical switch matrix.'],
     ['Series-switch studies','ON loss and OFF capacitance could not satisfy both registered limits at one width. Larger width did not solve the complete network.'],
     ['Independent reference','A fixed poly Rs path parallels a resistor/NMOS path; two N500 varactors provide variable Cs. Filtered control feeds and bypass are physical.'],
     ['Loaded calibration','At nominal VDD, R=1.26 V and C=0.333 V recover the 1.9 GHz identity after DFE loading. Signed Rs-switch Vds findings remain disclosed.'],
    ],[121,r.width-121],size=9.2)

    r.new('06 / Circuit narrative','A voltage-calibrated device-to-link bridge makes receiver quality affordable to inspect during search.')
    r.para('Saved transistor AC is fitted to a one-zero/two-pole CTLE model with a fit-validity gate, then combined with transmitter shaping and a constructed minimum-phase channel. The pulse response preserves voltage scale. Cursor samples separate desired signal from intersymbol interference without a full transistor transient for every candidate.')
    r.figure('submission_eyes','Earlier fixed physical CTLE: modeled ideal-DFE eye ranges across 45 corners at each of seven constructed losses, totaling 315 conditions. Heights and widths are cursor metrics. [E6]',165)
    r.heading('What the 1-tap DFE contributes')
    r.para('For pulse cursors h0 and h1, the normalized ideal tap is b1=h1/h0. Previous-bit feedback subtracts h1; remaining pre- and post-cursors limit the eye. Ideal height is twice the difference between the main cursor and remaining absolute ISI sum, clipped at zero. Hardware additionally needs decision memory, timing and a physical summer.')
    r.figure('submission_dfe','Saved behavioral comparison [E6]. This CTLE already meets eye targets without cancellation; ideal feedback chiefly increases width margin. Four model policies are not four transistor DAC implementations.',155)
    r.note('Measurement boundary.', 'The model uses 0.8 V differential peak-to-peak TX, -3.5 dB de-emphasis, 64 samples/UI and 3-12 dB constructed losses. Eyes are noiseless ISI openings, not BER contours. Inferred phase, ideal decisions and omitted jitter limit the result; measured reflections and decision-error propagation are absent.')

    r.new('07 / Generated hardware','The accepted setting-352 CTLE is now connected to a physical one-tap feedback path.')
    g=revision['generated']
    r.figure('receiver','Receiver topology: CTLE, CML summer, master/slave memory and current DAC. The generated 45-MOS circuit uses the selected fixed CTLE; the older 73-device reference separately adds variable controls. [E14,E1]',110)
    r.para('The exact accepted 6 dB / 2.1 GHz CTLE is retained, then connected to established transistor decision memory, a summer, feedback DAC and four bleed devices. There is no ideal decision source in this receiver deck. External clocks and tap controls remain verification apparatus.',size=10.3)
    r.figure('generated_aperture','Recorded nominal transistor aperture: minimum positive-bit and maximum negative-bit summer voltages across 64 scored bits. Shading marks the positive opening; the scan ends at +0.5 UI. This finite pattern is not a BER contour. [E14]',150)
    r.table(['NOMINAL MEASUREMENT','RESULT','EXACT SCOPE'],[
      ['Decisions / sampled eye',f"64/64 / {g['sampled_eye_height_v']*1000:.3f} mV",'TT / 1.8 V / 27 C; constructed 7.5 dB channel.'],
      ['Positive aperture / VDD',f"{g['aperture']['eye_width_ui']:.3f} UI / {g['ctle_plus_dfe_vdd_power_w']*1000:.4f} mW",'Phase 1 UI; code 2; fixed geometry; external source power excluded.'],
      ['Independent readback','17/17 integrity checks','Raw traces reproduce the nominal signal gate; no simulation rerun for review.'],
    ],[136,128,r.width-264],size=9)
    r.note('Retained electrical limit.', 'The added DFE signed checks and whole-circuit voltage envelope pass, but six attenuator PMOS devices violate documented signed model ranges. Therefore full receiver verification remains false. Nominal bit/eye success does not establish analog/link PVT, noise/HD3, BER or reliability signoff. [E14]')
    r.note('Why the design changed.', 'Earlier held-bit failures motivated stronger memory drive; floating inactive DAC tails motivated physical bleeders. The independent variable-Rs/Cs reference required loaded calibration. Its 850/690/650 ns standalone retuning still fails the original 500 ns target; DFE-active retuning remains open. [E1-E2]')

    r.new('08 / Independent reference','Separate 9 dB / 1.9 GHz, 73-device receiver: these results do not belong to the generated setting-352 circuit.')
    r.figure('pvt','All 45 fixed-control link points, grouped by MOS process; each group includes three supplies and three temperatures. Dashed lines are the eye-height and VDD-power limits. [E2]',202)
    r.table(['MEASUREMENT','RESULT','EXACT SCOPE'],[
     ['Nominal peaking / peak',f'{n["boost_db"]["min"]:.3f}-{n["boost_db"]["max"]:.3f} dB<br/>{n["peak_frequency_hz"]["min"]/1e9:.3f}-{n["peak_frequency_hz"]["max"]/1e9:.3f} GHz','Loaded held-clock states; .5 dB / 100 MHz internal request tolerances.'],
     ['Input-referred noise',f'{n["input_noise_vrms"]["min"]*1000:.5f}-{n["input_noise_vrms"]["max"]*1000:.5f} mVrms','10 MHz-5 GHz; two nominal negative-branch held-clock states, not periodic noise.'],
     ['Clocked HD3','-54.9201 to -54.9137 dBc','100 MHz, 100 mV differential peak; four time-step/tolerance settings, CTLE output.'],
     ['Link PVT','45/45; 64/64 bits each','TT/SS/FF/SF/FS; 1.71/1.80/1.89 V; 0/27/125 C; constructed 7.5 dB channel.'],
     ['Minimum eye / width',f'{p["minimum_eye_height_v"]*1000:.3f} mV / {p["minimum_positive_width_ui"]:.3f} UI',f'Positive opening width; width above 100 mV is {p["minimum_width_above_100mv_ui"]:.3f} UI. Distinct definitions.'],
     ['Maximum VDD / geometry',f'{p["maximum_vdd_power_w"]*1000:.4f} mW<br/>0.014715766 mm2','External clock/control/common-mode sources excluded; geometry subtotal is not routed area.'],
    ],[111,136,r.width-247],size=9.1)
    r.note('Scope of the result.', 'These are nominal analog checks plus sampled link PVT, not simultaneous all-specification PVT. Signed bilateral Rs-switch Vds findings persist at all 45 points. Omitted poly-resistor voltage dependence, passive corners, mismatch, periodic noise, full clock/control power and layout remain open.')
    r.note('Deadline pilot.', 'A separately registered two-corner analog pilot reproduced the nominal checks; FS / 1.71 V / 125 C failed the required latch initialization. It adds no valid analog-PVT coverage. [E10]')
    r.new('09 / Automation and search cost','A complete fresh physical workflow retains its rejected attempt, recovered circuit and actual cost.')
    recovered=revision['live'];meas=revision['live_design']['nominal']['meas']
    r.para('For the exposed request <b>6 dB at 2.1 GHz</b>, the framework parses the request, runs the frozen proposer, forms the fixed eligible set and verifies candidates without a human choosing the replacement. Setting 288 failed; the next ascending eligible setting, 352, passed and was exported. The recovery is classical selection after the learned proposal, not a new policy-discovered geometry. [E11]')
    r.table(['ACTUAL ATTEMPT','FRESH ACCEPTANCE','COST / DECISION'],[
        [f"Setting {a['setting']}",f"{a['n_pass']}/{a['n_points']} model conditions",f"{a['spice_calls']} calls; "+('accept and export' if a['accepted'] else 'retain failure, continue')]
        for a in recovered['attempts']],[130,159,r.width-289],size=9.5)
    r.para(f"The completed output measures {meas['peaking_db']:.4f} dB at {meas['_f_peak_ghz']:.4f} GHz. The separately recorded live workflow took <b>{recovered['wall_s']:.6f} s and {recovered['spice_calls']} charged invocations</b>, including the rejected candidate, parsing, selection, verification, CTLE export, drawing, files and checks. Receipt serialization is excluded; this run is outside the timing benchmark and predates structural receiver export. Request limits remain +/-1.5 dB and +/-0.3 octave.",size=10.3)
    r.heading('Matched complete-workflow comparison')
    arms=campaign['summary']['arms']
    r.table(['ARM','DELIVERED / ATTEMPTED','ALL WORKFLOW COST'],[
        [label,f"{arms[arm]['delivered_successes']}/{arms[arm]['attempted_workflows']}",f"{arms[arm]['wall_s']:.3f} s; {campaign['benchmark_calls'][arm]:,} charged calls"]
        for arm,label in [('rl','RL proposal + recovery'),('classical','Classical + recovery')]],
        [151,163,r.width-314],size=9.5)
    paired=campaign['summary'];ratio=paired['median_classical_over_rl_ratio']
    ratio_text='No paired delivered-time ratio is available.' if ratio is None else f"Median classical/RL elapsed ratio: {ratio:.3f}; classical is faster in this conditional median. This sample shows no RL speed advantage."
    r.note('Paired result.',f"{paired['both_success_pairs']}/{paired['matched_pairs']} target/repetition pairs delivered in both arms. {ratio_text} Ratios condition on both successes; failed and empty-domain workflows remain in the all-workflow cost above.")
    r.para('One classical 9 dB run suffered a Windows access-denied call-ledger write before a simulator launch. Its non-delivery is an infrastructure failure, not an electrical rejection or evidence of RL superiority. Calls above are charged ledger entries; one was charged although its simulator never launched. Four registered targets, three repetitions and two arms use fresh Python processes, counterbalanced order, the same bank, registry proposals, eight-candidate cap, physical gate and exports. Filesystem caches are not cleared. Both arms remeasure registry choices; 12 dB / 2.5 GHz has no cached candidate. The multi-candidate nonregistry case is 6 dB / 2.1 GHz. Three repeats are descriptive. [E12]',size=10.1)
    r.note('Historical context.',f"The earlier bank receipt used {rc['policy_visits']:,} visits and {rc['centered']+rc['recovered']} bank-selected outcomes/315 adaptive conditions. Its 5.894 s partial timer and 91.8x cached-visit comparison are different scopes; the old near-optimality gate failed. [E5,E8]")

    r.new('10 / Product and demonstration','The application shows the selected CTLE, its recovery record and separately scoped receiver evidence.')
    r.figure('desktop','Reviewed 1440x1000 workbench: saved setting 352, actual 288-to-352 recovery trace, selected CTLE and modeled DFE labels. The normal workbench opens accepted saved run 4608cf1c, replaying its original 164.766106 s receipt without launching new work. No special judge mode is required. [E9,E11]',224)
    r.table(['WORKFLOW','WHAT THE REVIEWER CAN INSPECT'],[
        ['Selected CTLE / recovery','Target -> rejected 288 (314/315) -> accepted 352 (315/315) -> exact artifacts. Main design.cir contains physical CTLE, attenuation, bias and fixed Rs/Cs.'],
        ['Modeled DFE / new receiver','The 315-condition eye gate uses ideal behavioral DFE outside design.cir. A read-only card links the matching selected-CTLE nominal transistor check by exact deck hash. Structural exports for other runs do not inherit this verification.'],
        ['Independent reference','Open the explicitly separate 9 dB / 1.9 GHz transistor evidence. Its calibration and PVT results do not follow a changed target.'],
        ['Run files / audit','An evidence index separates selected CTLE, matching nominal receiver and independent reference, with measurement scope, direct downloads and full SHA-256 hashes.'],
    ],[115,r.width-115],size=9.1)
    r.heading('Optional language assistance, deterministic authority')
    r.para('A guarded wrapper optionally parses requests and explains measured results. The LLM cannot select circuits, change acceptance or invent measurements. Controls are unchecked and visibly disabled without provider SDK/credentials; the live provider is unavailable here. Deterministic fallback remains usable: <b>six dB near 2.1 GHz</b> parses as <b>6 dB / 2.1 GHz</b>, with source and notes displayed. [E9]',size=10.2)
    r.para('Saved-run launch: <b>py -3.13 -m nebula.web.recovery_server --run-root nebula/product_demo/submission_runs_20260915_v2 --no-browser</b>. Open <b>http://127.0.0.1:8766</b>. The default now uses this saved root too; selecting a replay launches no SPICE. Read-only preflight: <b>py -3.13 -m nebula.submission_preflight</b>.',size=9.7)

    r.new('11 / Conclusions and reproducibility','Automated recovery turns a measured failed candidate into a delivered circuit, with every attempt accounted for.')
    r.para('Nebula combines learned candidate search, deterministic physical recovery and exact circuit output. Recovery delivers the exposed 6 dB / 2.1 GHz target; continuous-Cs measurements add 6 dB / 2.5 GHz evidence, moving the tested grid from 3/12 to 4/12. The generated transistor DFE demonstrates one nominal signal gate; verification scope stays attached to each circuit.',size=10.3)
    r.note('Remaining work.', 'Full target-range coverage, signed PMOS model-domain closure, generated-receiver analog/link PVT, DFE-active retuning, integrated clock/control drivers, noise/HD3 and extracted layout remain open. The live LLM provider is unavailable. No RL runtime advantage or full receiver signoff is claimed.')
    r.heading('Three evidence branches; no transfer of verification')
    r.table(['CIRCUIT / RECORD','MEASUREMENT OWNERSHIP / DIRECT ACCESS'],[
      ['Selected setting 352<br/>E11 / pp.2,3,5,10,11','Run files: design.cir, drawing, design.json and receipt. 45 PVT x seven constructed losses; eyes use ideal behavioral DFE. Rs/Cs fixed. Accepted run 4608cf1c; 288 rejection retained.'],
      ['Selected CTLE + transistor DFE<br/>E14 / pp.1,2,3,8','Run files: separate receiver deck, results, trace and terminals. Exact CTLE deck hash binding. Nominal TT/1.8 V/27 C, 7.5 dB constructed channel, clock phase 1 UI, tap code 2. Six signed PMOS violations; full verification false.'],
      ['Independent 9 dB / 1.9 GHz<br/>E1-E2 / pp.2,6,9','Reference panel: exact deck and 45-point transistor link record. Rs/Cs controls fixed at 0.7/0.185 VDD. Nominal HD3 uses 100 MHz, 100 mV differential peak; held-clock noise is not periodic receiver noise.'],
    ],[153,r.width-153],size=9)
    r.para('<b>Exact paths and hashes.</b> The <link href="http://127.0.0.1:8766/#evidence">Run files evidence index</link> provides direct artifact links and full SHA-256 values for all three branches. The companion v4 source manifest binds every report source, the selected drawing and current UI. Historical measurements and workflow receipts were not edited.',size=9.8)
    r.table(['ADDITIONAL EVIDENCE','SOURCE RELATIVE TO REPOSITORY ROOT'],[
      ['E3-E5: RL and oracle controls','nebula/experiments/shielded_policy_final_results.json; nebula/product_audits/entry113_attribution_20260907/summary.json; entry115_exhaustive_benchmark_20260908/summary.json (same product_audits parent).'],
      ['E11-E13: recovery / coverage','nebula/product_audits/submission_recovery_20260915/workflows.jsonl; continuous_cs_coverage_20260915/summary.json (same parent). Failed cases remain in their original records.'],
      ['E6-E10: historical scope','Earlier fixed CTLE, specification contract, historical adaptive-bank receipt and invalid analog-PVT pilot remain bound in the companion source manifest. None supplies missing selected-receiver signoff.'],
    ],[153,r.width-153],size=8.6)
    r.para('<b>Read-only preflight:</b> py -3.13 -m nebula.submission_preflight. Checks the accepted output, recorded hashes, matching nominal evidence and direct PDK paths; no simulator launch or deck rewrite. Absolute model paths and legacy newline-bound manifests limit clean-clone portability; this is not transitive PDK certification.',size=9.1)
    r.para('<b>Methods.</b> <link href="https://skywater-pdk.readthedocs.io/en/main/">SKY130 official documentation</link>; <link href="https://ngspice.sourceforge.io/docs.html">ngspice documentation</link>; Schulman et al., <link href="https://arxiv.org/abs/1707.06347">Proximal Policy Optimization Algorithms</link> (2017). Build: py -3.13 -m nebula.report.final_submission_v4. The 12-page report and source manifest are separate v4 outputs; earlier editions are preserved. Identity fields and the owner-recorded video remain submission actions.',size=8.8,gap=0)
    r.save()
    sources=[ROOT/'nebula/product_audits/submission_analog_pvt_20260914/second_attempt/summary.json',DETAILED_PDF.with_name(DETAILED_PDF.stem+'_sources.json'),Path(__file__),ROOT/'nebula/report/check_final_submission_v3.py',ROOT/'nebula/report/submission_story.py',ROOT/'nebula/report/competition_submission.py',NOMINAL_SUMMARY,PVT_SUMMARY,NOMINAL_NETLIST,FINAL,RECEIPT_SOURCE,PHYS/'summary.json',PHYS/'evidence_sha256.json',WIN_BENCH/'summary.json',WIN_BENCH/'sha256.json',WIN_RECOVERY/'summary.json',WIN_RECOVERY/'sha256.json',ROOT/'nebula/POST_REVIEW_RESULTS.md',ROOT/'nebula/DFE_CALIBRATED_RESULTS.md',ROOT/'CLAUDEwa.md',ROOT/'nebula/rl/hybrid_designer.py',ROOT/'nebula/web/static/app.js',ROOT/'nebula/web/static/design_plots.js',ROOT/'nebula/web/design_visuals.py',ROOT/'nebula/web/hardware_checkpoint.py',ROOT/'nebula/web/hardware_visuals.py',ROOT/'nebula/experiments/evidence_archive.py',ROOT/'nebula/AUTOMATION_RECEIPT_20260914.md',ROOT/'nebula/results/submission_receipt_20260914/receipt.json']
    sources += [folder/'summary.json' for folder in POST_DIRS.values()]
    sources += [folder/name for folder in (NOMINAL_ROOT,PVT_ROOT) for name in ('evidence_sha256.json','trace_archives.json')]
    sources += [CAMPAIGN/name for name in ('protocol.json','summary.json','workflows.jsonl','final_review.json')]
    sources += [RECOVERY_OUTPUT/name for name in ('design.json','design.cir','workflow_receipt.json')]
    sources += [RECOVERY_ROWS,ROOT/'nebula/physical_recovery.py',ROOT/'nebula/recovery_workflow.py',ROOT/'nebula/web/recovery_server.py',ROOT/'nebula/web/recovery_visuals.py',ROOT/'nebula/physical_design.py']
    sources += [ANOMALY_ROOT/'result.json',ANOMALY_ROOT/'fixed_pvt.jsonl',HARDENING,SAVED_COPY/'preservation.json',SAVED_COPY/'design.json']
    hardening=json.loads(HARDENING.read_text(encoding='utf-8'))
    sources.append(ROOT/hardening['historical_campaign']['checked_original_snapshot'])
    sources += sorted(V3_ASSETS.glob('*.png'))
    sources += sorted(V4_ASSETS.glob('*.png'))
    sources += [LIVE_ROOT/'design_schematic.png', ROOT/'nebula/submission_evidence.py', ROOT/'nebula/submission_preflight.py', ROOT/'nebula/report/submission_control_plot.py', ROOT/'nebula/report/check_final_submission_v4.py', ROOT/'nebula/web/static/judge_evidence.js', ROOT/'nebula/web/static/index.html', ROOT/'nebula/web/static/styles.css']
    sources += [OUT/name for name in (FROZEN_V1 | FROZEN_V2)]
    sources += [CS_REVIEW,CS_ROOT/'summary.json',CS_ROOT/'evidence_sha256.json',GEN_ROOT/'independent_review.json']
    sources += [CS_ROOT/row['candidate_id']/name for row in revision['cs']['candidates'] for name in ('result.json','evidence_sha256.json')]
    sources += [GEN_ROOT/name for name in json.loads((GEN_ROOT/'independent_review.json').read_text())['evidence_sha256']]
    sources += [LIVE_ROOT/name for name in ('workflow_receipt.json','design.json','design.cir')]
    sources += [ROOT/'nebula'/name for name in ('GENERATED_RECEIVER_RESULTS_20260915.md','generated_receiver.py','TARGET_COVERAGE_CS_RESULTS_20260915.md','CONTINUOUS_CS_RECOVERY_INTEGRATION_20260915.md','web/optional_llm.py','llm/spec_parse.py','web/static/language_assistant.js','web/static/recovery_trace.js')]
    sources += [V3_ASSETS/'desktop_provenance.json']
    sources += sorted(ASSETS.glob('*.png'))
    if RAW_PROOF.exists():sources.append(RAW_PROOF)
    manifest=dict(report=PDF.name,page_count=12,report_sha256=sha(PDF),page_titles=PAGE_TITLES,preserved_reports=PRESERVED,frozen_v1_artifacts=FROZEN_V1,content_bottoms_pt=r.bottoms,figures=r.figures,hardware_archive_checks=e['archive_checks'],receipt=rc,campaign_summary=campaign['summary'],revision_evidence=revision,frozen_v2_artifacts=FROZEN_V2,campaign_review=source_record(CAMPAIGN_REVIEW),cover_fields='11 intentionally blank AcroForm fields',source_claim_map={'E1':[1,2,5,6,7,8,9],'E2':[1,2,8,9],'E3':[3,4],'E4':[4,10],'E5':[10],'E6':[3,5,6,7],'E7':[1,2,5],'E8':[10],'E9':[11],'E10':[9],'E11':[3,10,11],'E12':[10],'E13':[2,3,12],'E14':[1,2,3,8,12]},sources=[source_record(path) for path in sources],scope='Saved evidence only; no new simulation or training.')
    verify_sources(manifest['sources']);MANIFEST.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(f'Created {PDF.name}: 12 total pages; previous reports preserved.')
    return PDF

if __name__=='__main__':build()
