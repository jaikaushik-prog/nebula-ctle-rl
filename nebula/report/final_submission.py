"""Separate 12-page final submission; saved evidence only, no simulations."""
from __future__ import annotations
import json
from pathlib import Path
from shutil import copyfile
from nebula.report.submission_story import source_record, verify_sources, sha
from nebula.report.competition_2026 import ROOT, OUT, FINAL
from nebula.report.competition_submission import PHYS, WIN_BENCH, WIN_RECOVERY, POST_DIRS
from nebula.web.hardware_checkpoint import NOMINAL_ROOT, PVT_ROOT, NOMINAL_SUMMARY, PVT_SUMMARY, NOMINAL_NETLIST
PDF=OUT/'Nebula_Final_Submission_12p_20260915.pdf'
MANIFEST=PDF.with_name(PDF.stem+'_sources.json')
REVIEW=PDF.with_name(PDF.stem+'_review.json')
RAW_PROOF=PDF.with_name(PDF.stem+'_raw_verification.json')
DETAILED_PDF=OUT/'Nebula_Submission_Report_20260914.pdf'
ASSETS=ROOT/'nebula/report/final_submission_assets'
SCRATCH=ROOT/'tmp/final-submission-report'
RECEIPT_SOURCE=ROOT/'nebula/product_demo/rl_hybrid_9db_1p9ghz/design.json'
PAGE_TITLES=('NEBULA','Requirements and evidence coverage','From specification to circuit',
 'What the learned policy does','The circuit and its physical bias','Physical attenuation and peaking',
 'From transistor response to eye','The integrated transistor receiver','Measured results and PVT scope',
 'An inspectable automation receipt','The designer workflow','Conclusions and evidence guide')
PRESERVED={
 'Nebula_Submission_Report_20260914.pdf':'169845fac6690d16630a18d70d7118b0936b66ce9bca277aed7380ae2025c15f',
 'Nebula_Competition_Report_Academic.pdf':'a573db02335879e0a6a0b3feb2c9eeea2172c2f3f4b4e4699dfc8123c8f90670',
 'Nebula_Competition_Report.pdf':'3cd67ffc933b8f369d601a72f16e39295542780777ca5bccc797135278faf43b'}
NAVY='#0b2342'; TEAL='#008aa1'; MUTED='#52677b'


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


def make_assets(e):
    import nebula.report.competition_submission as legacy
    import nebula.report.submission_story as story
    ASSETS.mkdir(parents=True,exist_ok=True)
    old=legacy.SCRATCH;legacy.SCRATCH=ASSETS/'legacy'
    try:
        legacy.make_figures(e['legacy'])
        for name in ('submission_core','submission_bias','submission_attenuator','submission_ac','submission_eyes','submission_dfe'):
            copyfile(legacy.SCRATCH/(name+'.png'),ASSETS/(name+'.png'))
    finally: legacy.SCRATCH=old
    old=story.SCRATCH;story.SCRATCH=ASSETS
    try: story.make_story_figures(e)
    finally: story.SCRATCH=old
    if not (ASSETS/'desktop.png').exists():
        fresh=ROOT/'tmp/final-submission-lead/browser/report-explorer.png'
        if not fresh.exists():fresh=ROOT/'nebula/report/assets/submission_20260914/receiver_desktop.png'
        copyfile(fresh,ASSETS/'desktop.png')


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
        padding={2:9,3:11,4:11,9:10,10:11,12:6}.get(self.n,7)
        widths=widths or [self.width/len(headings)]*len(headings)
        def p(s,bold=False):
            return Paragraph(str(s),ParagraphStyle('cell',fontName='Bold' if bold else 'Body',fontSize=size if not bold else size-.2,leading=size*1.32,textColor=self.color('#ffffff' if bold else NAVY)))
        t=Table([[p(s,True) for s in headings]]+[[p(s) for s in row] for row in rows],colWidths=widths,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),self.color(NAVY)),('ROWBACKGROUNDS',(0,1),(-1,-1),[self.color('#f0f5f8'),self.color('#ffffff')]),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),padding),('BOTTOMPADDING',(0,0),(-1,-1),padding),('LINEBELOW',(0,-1),(-1,-1),.5,self.color('#c9d6e0'))]))
        _,height=t.wrap(self.width,1000);t.drawOn(self.c,self.x,self.y-height);self.y-=height+12
    def figure(self,name,caption,height):
        from reportlab.lib.utils import ImageReader
        path=ASSETS/(name+'.png');im=ImageReader(str(path));iw,ih=im.getSize();scale=min(self.width/iw,height/ih);dw,dh=iw*scale,ih*scale
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


def build(e=None, regenerate_assets=True):
    for filename,digest in PRESERVED.items():
        if sha(OUT/filename)!=digest:raise ValueError(f'Preserved report changed: {filename}')
    if e is None:e=load_final_evidence()
    rc=load_receipt_evidence()
    if regenerate_assets:make_assets(e)
    h=e['hardware'];n=h['nominal'];p=h['pvt'];agg=e['legacy']['final']['aggregate'];bench=e['legacy']['winning']['benchmark']['aggregate'];r=FinalReport()
    r.new('Final report / PCIe Gen2 equalizer','RL-assisted automated analog circuit design with SKY130 and ngspice')
    r.para('<b>Specifications in. A circuit, measured specifications and an auditable decision out.</b>',size=15,gap=12)
    r.para('Nebula connects a trained policy, deterministic verification, transistor simulation and circuit export in a Python design framework. The policy explores a characterized 512-setting library; safety recovery and target centering make its role inspectable. A separate physical development implements voltage-configurable source degeneration and a transistor one-tap DFE.')
    r.figure('receiver','Calibrated transistor checkpoint. The feedback path is physical; clock and control generators remain external.',110)
    r.table(['AUTOMATED FRAMEWORK','CALIBRATED HARDWARE','REVIEWABLE OUTPUT'],[['Target input, policy proposals,<br/>verification and exact export','45/45 sampled link PVT;<br/>one fixed calibration','Circuit drawings, raw traces,<br/>specifications and source hashes']],size=9.2)
    r.para(f'Independent nominal measurements give {n["boost_db"]["min"]:.3f}-{n["boost_db"]["max"]:.3f} dB peaking near 1.9 GHz, {n["input_noise_vrms"]["max"]*1000:.5f} mVrms held-state noise and approximately -54.92 dBc clocked HD3. The minimum sampled link-PVT eye is {p["minimum_eye_height_v"]*1000:.3f} mV. These are simulation results at declared test conditions, not complete receiver signoff. [E1-E2]',size=10,gap=11)
    r.owner_fields()
    r.note('Contribution.', 'An integrated design workflow, measured policy comparisons and a physical receiver checkpoint make the result inspectable. This report includes all front matter and references within 12 pages.')

    r.new('01 / Problem and deliverables','The requested outcome is an automated design flow whose circuit claims survive verification.')
    r.para('At 5 Gbps, one unit interval is 200 ps and Nyquist is 2.5 GHz. Channel loss spreads each symbol into its neighbors. The prescribed equalizer combines one source-degenerated CTLE stage with variable Rs/Cs and one DFE tap. The official deliverable is an RL-based Python framework: target specifications in, seamless SPICE integration, final schematic and resulting specifications out. LLM-based interaction is a bonus. [E7]',size=10.3)
    r.table(['SPECIFICATION','REQUIRED TARGET','EVIDENCE / ASSESSMENT'],[
     ['S1 / Signaling','5 Gbps NRZ, PCIe Gen2','Simulated 200 ps UI; full PCIe protocol compliance is not assessed.'],
     ['S2 / Topology','CTLE, variable Rs/Cs,<br/>one-tap DFE','Implemented in the separate calibrated transistor deck.'],
     ['S3 / Response','3-12 dB; peak 1.25-2.5 GHz','Loaded nominal 8.744-8.747 dB at 1.903-1.906 GHz. Full target rectangle incomplete.'],
     ['S4 / Linearity','HD3 below -30 dBc,<br/>100 MHz input','Nominal clocked model HD3 about -54.92 dBc; 100 mV differential peak.'],
     ['S5 / Noise','Below 1.5 mVrms,<br/>10 MHz-5 GHz','Nominal held-clock noise at most 0.65405 mVrms; periodic noise unverified.'],
     ['S6 / Power','Below 15 mW','Maximum link-PVT VDD draw 12.5241 mW; external generators excluded.'],
     ['S7 / Area','Below 0.05 mm2, 130 nm','0.014715766 mm2 geometry subtotal; not routed layout area.'],
     ['S8 / Eye','Above 100 mV / 0.4 UI','45-point minima: 113.244 mV, 0.635 UI positive opening; 0.560 UI above 100 mV.'],
     ['S9 / PVT','5 process x 3 supplies x<br/>3 temperatures','Fixed-control link PVT: 45/45. Simultaneous S3-S8 analog PVT incomplete.'],
    ],[87,140,r.width-227],size=8.9)
    r.table(['JUDGING CRITERION','WHERE THE SUBMISSION PROVIDES EVIDENCE'],[
     ['Deliverable coverage','Framework/input/output: pp.3,10-11; circuit/specifications: pp.5-9; source guide: p.12.'],
     ['Innovation','Learned search with explicit verification/recovery, device-to-eye bridge and inspectable provenance: pp.3-4,7,10.'],
     ['Thought process','Measured failure mechanisms, physical redesign and independent re-verification: pp.6,8-9.'],
    ],[116,r.width-116],size=8.9)

    r.new('02 / Architecture','A common target contract links user input, learned proposals, verification and output artifacts.')
    r.figure('architecture','Cached bank scoring and fresh physical acceptance are separate execution paths. The verifier controls acceptance; the policy proposes candidates.',160)
    r.heading('Three evidence layers, three different meanings')
    r.table(['LAYER','WHAT RUNS / WHAT IS EXPORTED','WHAT ITS PASS MEANS'],[
     ['Frozen adaptive bank','Policy A/R/C moves; best compliant visit; classical recovery and centering; representative deck plus code map.','Codes may differ across PVT/channel conditions. One representative deck is not the whole map.'],
     ['Fixed physical CTLE','Eligible fixed setting, physical bias/MIM and exact captured transistor deck. Saved 3, 6 and 9 dB targets at 1.9 GHz.','One fixed CTLE across 315 modeled conditions. Its DFE remains ideal behavioral cancellation.'],
     ['Integrated checkpoint','73-device configurable CTLE, CML summer, clocked memory and feedback DAC; separate nominal and link-PVT decks.','One loaded 9 dB / 1.9 GHz calibration, independently checked. It was not autonomously discovered by PPO.'],
    ],[92,219,r.width-311],size=9.5)
    r.heading('Acceptance is a measured engineering decision')
    r.para('The device runner checks operating points, output completeness, model warnings, units and numerical consistency. It reads primitives instead of treating an exit code as proof. The link stage preserves absolute voltage and rejects invalid fits or compression. Each result keeps its request, circuit identity, measured outcomes and exact artifact paths together.')
    r.note('Automatic operation.', 'For a supported request, proposal, selection, verification and export require no manual candidate choice. Topology development, allowed ranges and the later receiver calibration were engineering decisions made before the run. [E1-E3,E6]')

    r.new('03 / RL formulation','The learned contribution is a bounded search trajectory through characterized circuits.')
    r.table(['PART OF THE MDP','IMPLEMENTED DEFINITION'],[
     ['Observation','62 fields: requested boost/log frequency, trial fraction, current A/R/C codes and measured eye history. PVT, channel loss, compliance, quality and oracle are hidden.'],
     ['Actions / horizon','A, R or C one index up/down, or LOCK; boundary masks; at most eight measurements, including the fixed start and repeats. Bank = 8 x 8 x 8 = 512 settings.'],
     ['Quality / reward','q is compliant eye area normalized to the best compliant bank eye area for that identity, clipped to [0,1]. Infeasible candidates have q=0. Reward tracks quality change and penalizes a bad final lock.'],
     ['Training / acceptance','Imitation initialization then PPO; five frozen seeds. Deployment seed is preselected. The shield retains compliant visits; production adds classical fallback and centering.'],
    ],[103,r.width-103],size=9.3)
    r.figure('learning','Exposed matched controls, eight-visit cap. PPO plus shield improves mean quality; local random exploration achieves higher compliance. All arms retain the fixed start. [E4]',193)
    r.para(f'The frozen FINAL evaluation contains 2,430 non-overlapping request/loss/PVT identities, not independent transistor geometries. Mean q rises from 0.5619 to {agg["mean_quality"]:.4f}: gain {agg["quality_delta"]:.4f}, paired 95% interval [{agg["paired_quality_delta_ci95"][0]:.4f}, {agg["paired_quality_delta_ci95"][1]:.4f}]. Shielded compliance is {agg["mean_compliance_rate"]*100:.2f}%; raw policy compliance is only 64.44%. The shield is essential. [E3]')
    r.note('Interpretation.', 'The study supports learned quality search within a characterized bank. It does not establish universal superiority, unrestricted MOS sizing or an on-chip controller with access to all verifier measurements.')
    r.new('04 / Circuit narrative','The physical export explains the CTLE core; the later receiver adds loaded voltage controls.')
    r.heading('The source-degenerated CTLE')
    r.figure('submission_core','Earlier verified fixed physical export [E6]. Rs/Cs here are drawn fixed values; shared net labels connect the attenuator and bias. NMOS bulks connect to ground.',216)
    r.para('The input pair converts differential voltage into current; poly loads convert current back to voltage. At low frequency Rs provides local feedback and reduces gain. Cs bypasses that degeneration as frequency rises; output loading then limits the high-frequency response. Two tail devices preserve separate source nodes.')
    r.note('First-order reasoning.', 'fz = 1/(2 pi Rs Cs), k = 1 + (gm + gmb) Rs/2, and A_dc is approximately gm RL/k. Rs is the full inter-source resistance. Body effect is included; finite output resistance and parasitics require the measured SPICE response. [E7]')
    r.heading('Reference current made physical')
    r.figure('submission_bias','Physical PMOS reference/feed, poly bias resistor, diode-connected NMOS and MIM bypass [E6]. PMOS bulks connect to VDD. The bypass is a fixed capacitor.',143)
    r.para('VDD supplies a resistor-and-transistor reference; the diode-connected NMOS sets the shared tail-gate bias. A roughly 10 pF physical MIM bypass suppresses signal-frequency bias movement. This supply-dependent reference exposes mirror error, noise, power and area that ideal current sources conceal. It is not a precision bandgap.',size=10.3)

    r.new('05 / Circuit narrative','Input excursion, relative peaking and absolute voltage gain answer different engineering questions.')
    r.figure('submission_attenuator','One leg of the earlier differential input attenuator [E6]; the other is identical. Three PMOS-switched shunts have real ON resistance and OFF parasitics.',139)
    r.para('The attenuator controls voltage presented to the active pair. This matters most on low-loss channels, where the minimum required CTLE boost can otherwise overdrive the stage. Peaking is a ratio to DC gain: about 9 dB of boost does not mean 9 dB of absolute gain. The input attenuator is not the source of CTLE peaking.')
    r.figure('submission_ac','Absolute voltage gain and the 45-corner envelope of the earlier fixed CTLE [E6]. These curves do not establish analog PVT for the later integrated receiver.',168)
    r.heading('From separate geometries to physical variable Rs/Cs')
    r.table(['DESIGN STEP','FINDING / CONSEQUENCE'],[
     ['Original 512-setting bank','Attenuator switches are netlisted. Rs/Cs codes select separately drawn passives; a code table alone is not a physical switch matrix.'],
     ['Series-switch studies','ON loss and OFF capacitance could not satisfy both registered limits at one width. Larger width did not solve the complete network.'],
     ['Configurable receiver','A fixed poly Rs path parallels a resistor/NMOS path; two N500 varactors provide variable Cs. Filtered control feeds and bypass are physical.'],
     ['Loaded calibration','At nominal VDD, R=1.26 V and C=0.333 V recover the 1.9 GHz identity after DFE loading. Signed Rs-switch Vds findings remain disclosed.'],
    ],[121,r.width-121],size=9.2)

    r.new('06 / Circuit narrative','A voltage-calibrated device-to-link bridge makes receiver quality affordable to inspect during search.')
    r.para('Saved transistor AC is fitted to a one-zero/two-pole CTLE model with a fit-validity gate, then combined with transmitter shaping and a constructed minimum-phase channel. The pulse response preserves voltage scale. Cursor samples separate desired signal from intersymbol interference without a full transistor transient for every candidate.')
    r.figure('submission_eyes','Earlier fixed physical CTLE: modeled ideal-DFE eye ranges across 45 corners at each of seven constructed losses, totaling 315 conditions. Heights and widths are cursor metrics. [E6]',165)
    r.heading('What the 1-tap DFE contributes')
    r.para('For pulse cursors h0 and h1, the normalized ideal tap is b1=h1/h0. Previous-bit feedback subtracts h1; remaining pre- and post-cursors limit the eye. Ideal height is twice the difference between the main cursor and remaining absolute ISI sum, clipped at zero. Hardware additionally needs decision memory, timing and a physical summer.')
    r.figure('submission_dfe','Saved behavioral comparison [E6]. This CTLE already meets eye targets without cancellation; ideal feedback chiefly increases width margin. Four model policies are not four transistor DAC implementations.',155)
    r.note('Measurement boundary.', 'The model uses 0.8 V differential peak-to-peak TX, -3.5 dB de-emphasis, 64 samples/UI and 3-12 dB constructed losses. Eyes are noiseless ISI openings, not BER contours. Inferred phase, ideal decisions and omitted jitter limit the result; measured reflections and decision-error propagation are absent.')

    r.new('07 / Hardware development','A physical one-tap feedback path is a separate result from an ideal behavioral eye score.')
    r.figure('receiver','73-device integrated checkpoint: configurable CTLE, CML summer, master/slave memory and current DAC. Physical bleeders prevent floating inactive DAC tails. [E1]',116)
    r.figure('eye','Saved transistor DFE-summer waveform overlay at nominal conditions [E1]. The finite, noiseless test scores 64 bits after settling on one constructed 7.5 dB channel.',173)
    r.heading('What failed, and what changed')
    r.table(['OBSERVATION','ENGINEERING RESPONSE / RETAINED LIMIT'],[
     ['Raw latch bits resolved; held ones failed','Storage and drive were tested separately. Wider CML memory later passed standalone PVT before feedback integration.'],
     ['64/64 decoded; an inactive tail had reverse Vds','Added real discharge transistors. Logic did not waive the electrical gate; code zero became minimum current, not feedback off.'],
     ['Standalone controls shifted near 1.75 GHz when loaded','Measured 65 loaded OP/AC points; selected .70/.185 VDD. Independent new analog/link checks followed; old passes were not transferred.'],
     ['Runtime settling exceeded 500 ns','Longer standalone observation measured 850/690/650 ns. The original internal 500 ns criterion remains failed; DFE-active retuning is unverified.'],
    ],[150,r.width-150],size=9.1)
    r.note('Thought process.', 'Every stronger test changed either the circuit, acceptance logic or claim. Frozen failed attempts remain available so progress can be checked rather than inferred from the final diagram.')

    r.new('08 / Verification','One fixed geometry, control fractions, tap code and clock phase at every declared link-PVT point.')
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
    r.new('09 / Automation and search cost','A saved production run exposes the policy, verifier and classical recovery as separate contributors.')
    r.para('The receipt reconstructs the existing 9 dB / 1.9 GHz adaptive-bank run; it does not rerun optimization. Its representative exported CTLE is setting 425. The 315 accepted conditions form an adaptive code map, distinct from the fixed 3 dB physical demo and the separate transistor receiver. [E8]')
    r.table(['RECORDED STAGE','MEASURED ACCOUNTING'],[
     ['Policy and verifier',f'{rc["policy_visits"]:,} visits/checks, including 315 fixed starts and repeats. {rc["rl_selected"]} outcomes retained by the RL-visit shield.'],
     ['Classical selection',f'{rc["centered"]} target-centering outcomes + {rc["recovered"]} safety recoveries = {rc["centered"]+rc["recovered"]} bank-selected outcomes; {rc["table_checks"]:,} table rows checked.'],
     ['Search / export cost',f'Zero new search/verification SPICE calls; one representative export call. Recorded design-plus-deck timer {rc["wall_s"]:.3f} s; export component {rc["export_wall_s"]:.3f} s. Drawing/writing excluded.'],
    ],[122,r.width-122],size=9.5)
    visits=' > '.join(str(x) for x in rc['fallback_example']['visits'])
    r.note('An actual safety-recovery trace.',f'FS / .95 VDD / 125 C at 3 dB channel loss: {visits}. No compliant visited candidate was retained; the bank supplied setting {rc["fallback_example"]["selected"]}. This final code is not an actor visit.')
    r.heading('Search effort is not elapsed design time')
    r.table(['COMPARISON','RESULT / INTERPRETATION'],[
     ['Policy vs cached exhaustive oracle',f'{bench["mean_policy_visits"]:.3f} versus 512 visits on average; {bench["candidate_visit_reduction"]:.1f}x fewer candidate visits. This is not an end-to-end SPICE or wall-clock speedup. [E5]'],
     ['Near-optimality',f'Mean oracle regret {bench["mean_regret_oracle_solvable"]:.5f}; {bench["fraction_within_0p05"]*100:.2f}% within 0.05 of oracle quality. Registered near-optimality gate fails.'],
     ['PPO attribution','At cap eight, PPO quality exceeds imitation by 0.039957, but local random compliance is higher. The all-classical-controls no-loss condition is not met. [E4]'],
    ],[143,r.width-143],size=9.4)
    r.para('The historical bank, midpoint and five PPO stages sum to 6.711 recorded hours. This excludes imitation, teacher construction, earlier sizing/training and other audits; original bank retries were not fully billed. It is not total project duration. No matched end-to-end MOS/R/C/L sweep establishes a final-physical speedup. [E4]')
    r.note('Competitive contribution.', 'Bounded learned search, explicit recovery and traceable output reduce opaque manual decisions. The evidence supports that integrated workflow without treating cached visits as seconds saved.')

    r.new('10 / Product and demonstration','The desktop workbench organizes inspection around one selected completed result.')
    r.figure('desktop','Design Explorer from the local application. A shared circuit canvas and adjacent inspector connect the selected circuit to response, specifications, sizing and its run record. [E9]',260)
    r.table(['DEMO STEP','WHAT THE REVIEWER CAN INSPECT'],[
     ['Design Explorer','Open the saved 3 dB / 1.9 GHz physical result: measured 3.910115 dB / 2.131144 GHz; modeled eye 341.791199 mV / 0.859375 UI. Start with CTLE and tails.'],
     ['Design PVT','315/315 model conditions = 45 PVT corners x seven losses. This physical export uses one fixed setting; each displayed heatmap is one 45-point loss slice.'],
     ['Compare circuits','CTLE-only, CTLE + ideal DFE and separate margin-envelope views. Waveforms come from saved AC; recorded dimensions remain cursor-based metrics.'],
     ['Separate transistor checkpoint','Expand the labeled 9 dB / 1.9 GHz evidence: actual DFE, nominal analog results and 45-point finite-pattern transistor link PVT.'],
     ['Channel / Run files','Profile an uploaded Touchstone file without inheriting bank verification. Inspect exact exported decks, specifications, drawings and evidence.'],
    ],[111,r.width-111],size=9.3)
    r.para('The saved 3 dB request uses production tolerances of 1.5 dB and 0.3 octave; its response is accepted within those tolerances, not exactly equal to the target. Editing the next request never relabels the completed result. A replayed demonstration is identified as saved evidence, not newly finished live optimization.')
    r.note('Deliverable closure.', 'Framework, circuit outputs, measurements and evidence are ready to inspect. The demo route above connects the report evidence to the actual workflow. Complete tuning coverage, extracted silicon area, all-specification PVT and provider-backed LLM fine-tuning remain further work.')

    r.new('11 / Conclusions and reproducibility','A working, inspectable design framework with an independently measured physical receiver checkpoint.')
    r.para('Nebula addresses the brief with target input, learned proposals, deterministic acceptance, open-source SPICE integration and circuit/specification output. The hardware extension demonstrates calibrated variable Rs/Cs and a transistor one-tap DFE at one loaded target. It strengthens implementation evidence while preserving the distinction between learned bank search and engineer-developed circuitry.')
    r.note('Next engineering steps.', 'Close analog PVT and loaded target coverage; resolve model-domain and passive-model limits; add DFE-active retuning, clock/control generation and extracted layout. Compare future automation against strong classical methods with matched complete timing and simulator budgets.')
    r.heading('Source-to-claim guide')
    r.table(['KEY / PAGES','SOURCE ARTIFACT (RELATIVE TO REPOSITORY)'],[
     ['E1 / 1,2,5-9','nebula/DFE_CALIBRATED_RESULTS.md; nebula/product_audits/entry143_dfe_calibrated_verification_20260910/ - nominal checks, exact transistor deck and waveform.'],
     ['E2 / 1,2,8,9','nebula/product_audits/entry144_dfe_calibrated_pvt_20260910/ - fixed-control link PVT, all 45 decks, summary and lossless raw archive.'],
     ['E3 / 3,4','nebula/experiments/shielded_policy_final_results.json; nebula/rl/hybrid_designer.py - frozen final study and actual production logic.'],
     ['E4 / 4,10','nebula/POST_REVIEW_RESULTS.md; nebula/product_audits/entry113_attribution_20260907/ - matched controls, failures and cost ledger.'],
     ['E5 / 10','nebula/product_audits/entry115_exhaustive_benchmark_20260908/ - cached oracle and failed near-optimality gate.'],
     ['E6 / 3,5-7','nebula/product_demo/physical_bias_9db_1p9ghz_20260906/; nebula/product_audits/entry115_physical_recovery_20260908/ - fixed CTLE and recovered 3/6 dB targets.'],
     ['E7 / 1,2,5','CLAUDEwa.md - deliverables, S1-S9, circuit conventions. Pre-existing SerDes infrastructure is declared; reported results are Nebula NRZ only.'],
     ['E8 / 10','nebula/product_demo/rl_hybrid_9db_1p9ghz/design.json; nebula/AUTOMATION_RECEIPT_20260914.md - actual policy traces, selection and partial timing.'],
     ['E9 / 11','nebula/web/; nebula/report/final_submission_assets/desktop.png - five-tab implementation and captured workbench.'],
     ['E10 / 9','nebula/product_audits/submission_analog_pvt_20260914/second_attempt/summary.json - registered two-corner analog pilot; stress initialization failed.'],
    ],[72,r.width-72],size=8.2)
    r.para('<b>Methods and tools.</b> [R1] <link href="https://skywater-pdk.readthedocs.io/en/main/">SkyWater SKY130 official documentation</link>. [R2] <link href="https://ngspice.sourceforge.io/docs.html">ngspice manual and documentation</link>. [R3] Schulman et al., <i>Proximal Policy Optimization Algorithms</i>, 2017, <link href="https://arxiv.org/abs/1707.06347">arXiv:1707.06347</link>. Measurements are E1-E10, not values borrowed from these references.',size=8.6,gap=7)
    r.para('Build: <b>py -3.13 -m nebula.report.final_submission</b>; check: <b>py -3.13 -m nebula.report.check_final_submission</b>. Companion sources/review JSON files record hashes and page checks. Three earlier PDFs are preserved. Local evidence validates; nine legacy JSON newline mismatches remain a documented clean-clone rebuild limitation (HANDOFF G197).',size=8.6,gap=0)
    r.save()
    sources=[ROOT/'nebula/product_audits/submission_analog_pvt_20260914/second_attempt/summary.json',DETAILED_PDF.with_name(DETAILED_PDF.stem+'_sources.json'),Path(__file__),ROOT/'nebula/report/check_final_submission.py',ROOT/'nebula/report/submission_story.py',ROOT/'nebula/report/competition_submission.py',NOMINAL_SUMMARY,PVT_SUMMARY,NOMINAL_NETLIST,FINAL,RECEIPT_SOURCE,PHYS/'summary.json',PHYS/'evidence_sha256.json',WIN_BENCH/'summary.json',WIN_BENCH/'sha256.json',WIN_RECOVERY/'summary.json',WIN_RECOVERY/'sha256.json',ROOT/'nebula/POST_REVIEW_RESULTS.md',ROOT/'nebula/DFE_CALIBRATED_RESULTS.md',ROOT/'CLAUDEwa.md',ROOT/'nebula/rl/hybrid_designer.py',ROOT/'nebula/web/static/app.js',ROOT/'nebula/web/static/design_plots.js',ROOT/'nebula/web/design_visuals.py',ROOT/'nebula/web/hardware_checkpoint.py',ROOT/'nebula/web/hardware_visuals.py',ROOT/'nebula/experiments/evidence_archive.py',ROOT/'nebula/AUTOMATION_RECEIPT_20260914.md',ROOT/'nebula/results/submission_receipt_20260914/receipt.json']
    sources += [folder/'summary.json' for folder in POST_DIRS.values()]
    sources += [folder/name for folder in (NOMINAL_ROOT,PVT_ROOT) for name in ('evidence_sha256.json','trace_archives.json')]
    sources += sorted(ASSETS.glob('*.png'))
    if RAW_PROOF.exists():sources.append(RAW_PROOF)
    manifest=dict(report=PDF.name,page_count=12,report_sha256=sha(PDF),page_titles=PAGE_TITLES,preserved_reports=PRESERVED,content_bottoms_pt=r.bottoms,figures=r.figures,hardware_archive_checks=e['archive_checks'],receipt=rc,cover_fields='11 intentionally blank AcroForm fields',source_claim_map={'E1':[1,2,5,6,7,8,9],'E2':[1,2,8,9],'E3':[3,4],'E4':[4,10],'E5':[10],'E6':[3,5,6,7],'E7':[1,2,5],'E8':[10],'E9':[11],'E10':[9]},sources=[source_record(path) for path in sources],scope='Saved evidence only; no new simulation or training.')
    verify_sources(manifest['sources']);MANIFEST.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(f'Created {PDF.name}: 12 total pages; previous reports preserved.')
    return PDF

if __name__=='__main__':build()
