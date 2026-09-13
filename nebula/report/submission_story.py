"""Independent 14 September submission edition; saved evidence only.

Build: py -3.13 -m nebula.report.submission_story
The two earlier report editions are immutable comparison copies.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from nebula.report.competition_2026 import Report, ROOT, OUT, FINAL, read_json
from nebula.report.competition_submission import (
    TEAM_MEMBERS, INSTITUTION, load_evidence, POST_DIRS,
    WIN_BENCH, WIN_RECOVERY, PHYS,
)
from nebula.web.hardware_checkpoint import (
    build_hardware_checkpoint, NOMINAL_ROOT, PVT_ROOT, NOMINAL_SUMMARY,
    PVT_SUMMARY, NOMINAL_NETLIST,
)
from nebula.web.hardware_visuals import devices, eye_data, POINT
from nebula.experiments.evidence_archive import verify as verify_archive

PDF = OUT / "Nebula_Submission_Report_20260914.pdf"
MANIFEST = PDF.with_name(PDF.stem + "_sources.json")
REVIEW = PDF.with_name(PDF.stem + "_review.json")
SCRATCH = ROOT / "tmp/pdfs/submission_story"
_PAGE_SCALES = {}
_PAGE_SPACING = {}
PREVIOUS = {
    "Nebula_Competition_Report_Academic.pdf": "a573db02335879e0a6a0b3feb2c9eeea2172c2f3f4b4e4699dfc8123c8f90670",
    "Nebula_Competition_Report.pdf": "3cd67ffc933b8f369d601a72f16e39295542780777ca5bccc797135278faf43b",
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_record(path, root=ROOT):
    """Normalize Git text line endings; retain exact frozen artifact bytes."""
    path, root = Path(path), Path(root)
    relative = path.relative_to(root)
    raw = path.read_bytes()
    frozen = relative.parts[:2] in (("nebula", "product_audits"), ("nebula", "product_demo"))
    text = path.suffix.lower() in {".py", ".js", ".css", ".html", ".md", ".json"}
    mode = "lf-text" if text and not frozen else "raw"
    data = raw.replace(b"\r\n", b"\n") if mode == "lf-text" else raw
    return {"path": relative.as_posix(), "sha256": hashlib.sha256(data).hexdigest(),
            "hash_mode": mode, "raw_sha256_at_build": hashlib.sha256(raw).hexdigest()}


def verify_sources(records, root=ROOT):
    root = Path(root).resolve()
    for record in records:
        path = (root / record["path"]).resolve()
        mode = record.get("hash_mode", "raw")
        if not path.is_relative_to(root) or not path.is_file() or mode not in {"raw", "lf-text"}:
            raise ValueError(f"Report source changed: {record['path']}")
        data = path.read_bytes()
        if mode == "lf-text":
            data = data.replace(b"\r\n", b"\n")
        if hashlib.sha256(data).hexdigest() != record["sha256"]:
            raise ValueError(f"Report source changed: {record['path']}")


def load_story_evidence():
    for name, digest in PREVIOUS.items():
        if sha(OUT / name) != digest:
            raise ValueError(f"Preserved report changed: {name}")
    h = build_hardware_checkpoint()
    # Preserve raw-evidence integrity, not just the headline summaries.
    archive_checks=[]
    for folder,digest in (
        (NOMINAL_ROOT,"59a7deec832a1d744ad7175bd1eeed7fb0d21b376e1d03c15acb24e1888c99c7"),
        (PVT_ROOT,"c5213fb228fc450b882b2ce7b4be7219adc6f352d63315b5195af32a4e63afe1"),
    ):
        result=verify_archive(folder)
        if result["manifest_sha256"]!=digest:
            raise ValueError("Pinned hardware archive manifest changed")
        archive_checks.append(result)
    legacy = load_evidence()
    rows = devices()
    if len(rows) != 73 or h["pvt"]["n_pass"] != 45:
        raise ValueError("Hardware scope changed; editorial review required")
    return {"hardware": h, "legacy": legacy, "device_count": len(rows), "devices": rows,
            "archive_checks": archive_checks}


def make_story_figures(e):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.patches import FancyBboxPatch
    SCRATCH.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "text.color": "#102e4e", "axes.labelcolor": "#102e4e"})
    navy, teal, blue, amber = "#102e4e", "#008a94", "#2469a0", "#a15c24"

    def save(fig, name):
        fig.savefig(SCRATCH / f"{name}.png", dpi=190, bbox_inches="tight", facecolor="white")
        plt.close(fig)

    def block(ax, x, y, w, label, color=navy):
        ax.add_patch(FancyBboxPatch((x, y), w, .8, boxstyle="round,pad=.04,rounding_size=.08",
                                  facecolor="#f1f7fa", edgecolor=color, lw=1.3))
        ax.text(x+w/2, y+.4, label, ha="center", va="center", fontsize=11, color=color)

    fig, ax = plt.subplots(figsize=(9.2, 3.3))
    ax.set(xlim=(-.2, 10.4), ylim=(-.1, 3.3)); ax.axis("off")
    for x, label in [(0,"Target\nspecifications"),(2.65,"Policy\nproposal"),(5.3,"Deterministic\nverification"),(7.95,"Circuit + specs\n+ evidence")]:
        block(ax,x,2.15,2,label)
    for x in (2.02,4.67,7.32):
        ax.annotate("",xy=(x+.6,2.55),xytext=(x,2.55),arrowprops={"arrowstyle":"->","color":teal,"lw":1.6})
    block(ax,1.25,.45,3.4,"Characterized SKY130 bank\nscoped candidate scoring",blue)
    block(ax,5.6,.45,3.4,"ngspice + fixed-circuit PVT\nphysical export acceptance",teal)
    ax.annotate("",xy=(3.65,2.1),xytext=(3.2,1.3),arrowprops={"arrowstyle":"->","color":blue})
    ax.annotate("",xy=(6.3,2.1),xytext=(7.3,1.3),arrowprops={"arrowstyle":"->","color":teal})
    save(fig,"architecture")

    fig, ax = plt.subplots(figsize=(9.2, 3.0))
    ax.set(xlim=(-.2,10.4),ylim=(-.2,3)); ax.axis("off")
    for x,w,label in [(0,1.7,"Input\nattenuator"),(2.3,1.7,"CTLE\nRs / Cs"),(4.6,1.7,"CML\nsummer"),(6.9,3.1,"Master / slave\ndecision memory")]:
        block(ax,x,1.8,w,label)
    for x, end in [(1.75,2.25),(4.05,4.55),(6.35,6.85)]:
        ax.annotate("",xy=(end,2.2),xytext=(x,2.2),arrowprops={"arrowstyle":"->","color":teal,"lw":1.6})
    block(ax,6.9,.2,3.1,"1-tap current DAC\nwith physical bleeders",teal)
    ax.annotate("",xy=(8.45,1.04),xytext=(8.45,1.75),arrowprops={"arrowstyle":"->","color":teal})
    ax.plot([6.85,5.45,5.45],[.6,.6,1.75],color=teal,lw=1.5)
    ax.text(3,.55,"VDD-derived bias; external clock and controls",ha="center",fontsize=10)
    save(fig,"receiver")

    offsets, waves, aperture = eye_data()
    fig, ax = plt.subplots(figsize=(8.8,4.1),layout="constrained")
    ax.plot(offsets,waves.T*1000,color=teal,alpha=.25,lw=.8)
    ax.axhline(0,color="#8295a4",lw=.7)
    ax.axvspan(-.05,-.005,color=amber,alpha=.2)
    ax.set(xlim=(-1,1),ylim=(-370,370),xlabel="Time relative to clock edge (UI)",ylabel="DFE summer differential output (mV)")
    ax.grid(alpha=.17)
    save(fig,"eye")

    rows=e["hardware"]["pvt"]["corners"]
    fig, axes=plt.subplots(2,1,figsize=(8.8,4.8),sharex=True,layout="constrained")
    groups=["tt","ss","ff","sf","fs"]
    ordered=[r for group in groups for r in rows if r["process"]==group]
    assert len(ordered)==45
    for ax,key,scale,label,limit in [
        (axes[0],"sampled_eye_height_v",1000,"Sampled eye (mV)",100),
        (axes[1],"vdd_power_w",1000,"VDD power (mW)",15)]:
        ax.scatter(range(45),[r[key]*scale for r in ordered],s=29,color=teal)
        ax.axhline(limit,color=amber,ls="--",lw=1)
        ax.set_ylabel(label); ax.grid(axis="y",alpha=.17)
        for pos in (8.5,17.5,26.5,35.5): ax.axvline(pos,color="#ced9e1",lw=.8)
    axes[0].set_ylim(bottom=70); axes[1].set_ylim(0,16.5)
    axes[1].set_xticks([4,13,22,31,40],[x.upper() for x in groups])
    axes[1].set_xlabel("Nine supply / temperature combinations per transistor corner")
    save(fig,"pvt")

    controls=e["legacy"]["supplemental"]["attribution"]["results"]
    arms=["fixed","hill","random_local","bc","ppo"]
    names=["Fixed start","Hill climb","Local random","Imitation","PPO + shield"]
    fig,axes=plt.subplots(1,2,figsize=(9.2,3.4),layout="constrained")
    for ax,key,label,scale in [(axes[0],"quality","Mean quality score",1),(axes[1],"compliant","Model compliance (%)",100)]:
        vals=[np.mean([r[key] for r in controls if r["arm"]==arm and r["budget"]==8])*scale for arm in arms]
        bars=ax.barh(names,vals,color=["#8b9aa8",blue,blue,blue,teal],height=.6)
        ax.invert_yaxis(); ax.set_xlabel(label); ax.set_xlim(0,1.05 if scale==1 else 105)
        ax.bar_label(bars,labels=[f"{v:.3f}" if scale==1 else f"{v:.2f}" for v in vals],padding=4,fontsize=10)
        ax.grid(axis="x",alpha=.13)
    save(fig,"learning")


class StoryReport(Report):
    def __init__(self,path):
        super().__init__(path)
        self.style.fontSize=10.7; self.style.leading=16.05
        self.c.setTitle("Nebula | From specifications to inspectable circuit evidence")
        self.c.setAuthor("; ".join(name for name,_ in TEAM_MEMBERS))
        self.c.setSubject("Independent submission report | 14 September 2026")
        self.content_bottoms=[]; self.figures=[]; self.paragraph_counts=[]

    def new(self, tag, title, subtitle=None):
        self.scale = _PAGE_SCALES.get(self.n + 1, 1.0)
        super().new(tag, title, None)
        self.paragraph_count = 0
        if subtitle:
            self.para(subtitle, size=10.5, color="#617287", gap=18)

    def check(self, height):
        # Layout passes measure before the final renderer checks page bounds.
        if height < 0:
            raise ValueError("Negative layout height")

    def para(self, text, size=None, color=None, gap=11, x=None, width=None):
        self.paragraph_count += 1
        super().para(text, (size or self.style.fontSize)*self.scale,
                     color, gap*self.scale + _PAGE_SPACING.get(self.n, 0), x, width)

    def heading(self, text):
        self.text(text, self.left, self.y+13*self.scale, 13*self.scale, "Strong")
        self.y += 25*self.scale

    def table(self, headers, rows, widths=None, size=9):
        from html import escape
        from reportlab.platypus import Table, TableStyle, Paragraph
        from reportlab.lib.styles import ParagraphStyle
        size *= self.scale
        style=ParagraphStyle("cell",parent=self.style,fontSize=size,leading=size*1.42)
        head=ParagraphStyle("head",parent=style,fontName="Strong",textColor="white")
        cells=[[Paragraph(escape(str(t)),head) for t in headers]]
        cells += [[Paragraph(str(t),style) for t in row] for row in rows]
        tab=Table(cells,colWidths=widths or [self.width/len(headers)]*len(headers))
        padding=8+_PAGE_SPACING.get(self.n,0)/2
        tab.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),"#162d49"),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),["#f0f5f9","#ffffff"]),
            ("VALIGN",(0,0),(-1,-1),"TOP"),
            ("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8),
            ("TOPPADDING",(0,0),(-1,-1),padding),("BOTTOMPADDING",(0,0),(-1,-1),padding),
            ("LINEBELOW",(0,-1),(-1,-1),.5,"#d9e3ec")]))
        _,height=tab.wrap(self.width,700)
        tab.drawOn(self.c,self.left,self.h-self.y-height)
        self.y += height+16
        self.paragraph_count += len(cells)

    def finish_page(self):
        self.content_bottoms.append(round(self.y,2))
        self.paragraph_counts.append(self.paragraph_count)
        self.c.setStrokeColor("#d9e3ec"); self.c.line(46,41,self.w-46,41)
        self.text("14 SEPTEMBER 2026  |  SUBMISSION EDITION",46,self.h-26,8,color="#617287")
        self.text(f"{self.n:02d}",self.w-61,self.h-26,9,"Strong","#1764b0")
        self.c.showPage()

    def figure(self,name,caption,max_h=250):
        from PIL import Image
        path=SCRATCH/f"{name}.png"
        with Image.open(path) as im: iw,ih=im.size
        w=self.width; h=w*ih/iw
        max_h *= self.scale
        if h>max_h: w,h=w*max_h/h,max_h
        self.check(h)
        self.c.drawImage(str(path),self.left+(self.width-w)/2,self.h-self.y-h,w,h,mask="auto")
        self.y+=h+9
        self.figures.append({"number":len(self.figures)+1,"name":name,"page":self.n})
        self.para(f"<b>Figure {len(self.figures)}.</b> {caption}",size=9.3,color="#53677b",gap=16)

    def close_note(self,title,copy):
        self.heading(title); self.para(copy)


def build(e=None):
    if e is None:
        e=load_story_evidence(); make_story_figures(e)
    h=e["hardware"]; n=h["nominal"]; p=h["pvt"]
    agg=e["legacy"]["final"]["aggregate"]
    bench=e["legacy"]["winning"]["benchmark"]["aggregate"]
    r=StoryReport(PDF)
    r.new("Competition submission / 14 September 2026","NEBULA","RL-assisted automated analog circuit design for a PCIe Gen2 equalizer")
    r.para("From specifications to<br/><b>inspectable circuit evidence</b>",size=23,gap=18)
    r.para("A Python design framework and calibrated SKY130 transistor receiver, developed for the Astera Labs Nebula challenge.",size=12)
    r.figure("receiver","Implemented receiver architecture. The physical checkpoint combines voltage-configurable source degeneration with a transistor 1-tap DFE; arrows show signal and feedback flow.",190)
    r.table(["AUTOMATION","TRANSISTOR HARDWARE","REVIEWABLE OUTPUT"],[
        ["Target-driven search,<br/>verification and export","45/45 sampled Link PVT<br/>points at one calibration","Circuit drawings, exact decks,<br/>specifications and raw evidence"]],size=9.8)
    r.para("<b>Jai Kaushik | Rishabh Agarwal | Avi Mehta</b><br/>"+INSTITUTION,size=11)
    r.para("Final submission: 15 September 2026<br/>Companion to the narrated desktop demonstration",size=10,color="#53677b")
    r.para("Scope: simulator-backed engineering evidence. Complete target coverage, all-specification PVT and extracted-layout signoff remain open.",size=9.7)

    r.new("Front matter","Abstract","What we built, what the evidence supports, and why it matters.")
    r.para("Analog equalizer design is a coupled search problem: improving frequency response can change noise, distortion, power and the eye opening seen by the receiver. A useful automated tool must therefore do more than suggest component values. It must determine whether the requested response is achievable, verify the resulting circuit and expose enough evidence for an engineer to trust the decision.")
    r.para("Nebula connects structured target input, an RL-assisted candidate search, SKY130/ngspice measurements, link evaluation and circuit export in a Python framework. The learned policy navigates a characterized 512-setting library. A deterministic verifier controls acceptance, retains useful visited candidates and records unsuccessful requests. The desktop frontend makes the circuit, measurements and evidence accessible without hiding the distinction between saved results and fresh computation.")
    r.para("The hardware work extends beyond the earlier behavioral DFE score. A calibrated transistor implementation now includes the CTLE, voltage-configurable Rs/Cs, a CML summer, master/slave decision memory and a feedback-current DAC. At a 9 dB / 1.9 GHz request, independent nominal checks measure 8.744-8.747 dB boost, 1.903-1.906 GHz peak frequency, 0.6541 mVrms input noise and approximately -54.92 dBc HD3. The same control fractions, tap code and phase recover all 64 scored bits at each of 45 sampled Link PVT points on a constructed 7.5 dB channel. [E1-E2]")
    r.para(f"The frozen policy study reports a {agg['quality_delta']:.4f} mean quality improvement over its fixed start. An exhaustive cached-library comparison finds {bench['candidate_visit_reduction']:.1f}x fewer candidate visits, but its near-optimality gate fails. These are library-search results; they do not establish an end-to-end SPICE speedup or demonstrate that PPO discovered the later transistor receiver. [E3-E5]")
    r.close_note("Contribution and boundary","The contribution is an integrated and inspectable design workflow backed by increasingly physical evidence. The current result demonstrates a calibrated receiver checkpoint and useful search behavior; it does not yet satisfy the full tunable specification rectangle or every specification at every PVT point.")

    r.new("Front matter","Contents and reading route","Use the video for the workflow; use this report to examine the decisions and evidence.")
    r.table(["CHAPTER","WHAT IT ANSWERS","PAGES"],[
        ["1 / Problem and deliverables","What was asked, and what did we deliver?","4-5"],
        ["2 / Architecture and learning","How does the automated flow work, and what does RL add?","6-8"],
        ["3 / Circuit implementation","How are equalization, tuning and feedback physically realized?","9-16"],
        ["4 / Verification and results","What was measured, under which conditions?","17-19"],
        ["5 / Decisions and product","What failed, what changed, and how can it be reviewed?","20-22"],
        ["6 / Assessment and conclusions","Which requirements are supported and what remains?","23-24"],
        ["References and evidence index","Where are the original methods and exact artifacts?","25"]],[120,330,53],size=10)
    r.heading("Three evidence layers")
    r.para("<b>Frozen library-policy experiment.</b> RL selects A/R/C codes in a SPICE-characterized bank; link scoring uses a behavioral cursor-based DFE. The held-out request/loss views share the characterized transistor geometries and PVT lattice.")
    r.para("<b>Physical CTLE export.</b> Automated request handling can deliver a fixed transistor CTLE with a physical bias reference and bypass. Verified 3, 6 and 9 dB targets at 1.9 GHz each retain a 315-case model record. The associated DFE metric remains behavioral.")
    r.para("<b>Calibrated transistor receiver.</b> The latest Rs/Cs and DFE implementation has its own exact deck, nominal analog checks and 45-point link experiment. Its single calibrated target is not automatically inherited by other generated requests.")
    r.para("Evidence labels [E1]-[E7] identify project artifacts listed on page 25. [R1]-[R3] identify external method/tool references. The companion source manifest records exact hashes. No unannounced scoring rubric is assumed.",size=10)

    r.new("Chapter 1 / Problem and objectives","The problem behind the brief","A fast proposal matters only when the circuit still meets the receiver requirements.")
    r.para("The competition asks for an RL-based Python framework that accepts circuit specifications, integrates with a SPICE simulator and returns the final schematic and resulting specifications. It calls for substantially less design time than sweeping the full MOS/R/C/L parameter space, near-optimal solutions and zero human intervention. A language-based interaction wrapper is an additional opportunity, not a substitute for the engineering flow. [E7]")
    r.heading("1.1 The electrical problem")
    r.para("The specified use case is 5.0 Gbps NRZ, giving a 200 ps unit interval and a 2.5 GHz Nyquist frequency. Channel loss smears symbols into neighboring decisions. A source-degenerated CTLE shapes the analog response to recover high-frequency content, while a 1-tap DFE subtracts the contribution of the previous decided bit. The topology is prescribed: one CTLE stage with variable Rs/Cs followed by one feedback tap.")
    r.table(["REQUIREMENT GROUP","TARGET"],[
        ["Response (S3)","3-12 dB peaking; peak in 1.25-2.5 GHz; tunable to the requested point"],
        ["Analog cost (S4-S7)","HD3 below -30 dBc at 100 MHz; noise below 1.5 mVrms over 10 MHz-5 GHz; power below 15 mW; area below 0.05 mm2"],
        ["Receiver robustness (S8-S9)","Eye above 100 mV and 0.4 UI; TT/SS/FF/SF/FS, VDD +/-5%, temperatures from 0 to 125 deg C"]],[140,363],size=10)
    r.heading("1.2 Our acceptance philosophy")
    r.para("Peak magnitude, peak location and gain at Nyquist are different measurements. A large peak at the wrong frequency is not enough. The project contract tracks these definitions separately and applies PVT to S3-S8 together. A nominal pass, a finite eye trace or a geometry estimate cannot establish complete receiver compliance.")
    r.para("We therefore separate candidate discovery from acceptance. The policy can explore; the measurement and verification code decides whether a result is deliverable. This choice connects the machine-learning objective to the actual problem rather than treating reward alone as proof.")

    r.new("Chapter 1 / Deliverables","Deliverables and reviewer route","Concrete artifacts make each part of the brief inspectable.")
    r.table(["ASKED FOR","DELIVERED IMPLEMENTATION","HOW TO REVIEW"],[
        ["Python framework; target specs in","CLI and desktop request input share structured target validation; supported paths are explicitly labeled.","Enter peaking and frequency; inspect the parsed request."],
        ["RL-based design flow","Frozen policy, characterized bank, local A/R/C actions and deterministic safety shield.","Chapter 2; policy/control results [E3-E5]."],
        ["SPICE integration","ngspice 41 subprocess runner with SKY130 primitives, output parsing and numerical checks.","Open exact decks, logs and measurement files [E1-E2, E6]."],
        ["Final schematic and resulting specs","Generated CTLE export plus a separately verified configurable transistor receiver checkpoint.","Circuit inspector, full device sheet, spec table and evidence downloads."],
        ["Fewer searches / lower design time","Measured cached candidate-visit reduction; offline characterization and training costs retained.","Page 8 and cost accounting on page 22."],
        ["Near-optimal / automatic operation","Automatic proposal-to-acceptance workflow within characterized paths; near-optimality and full-domain coverage remain unproven.","Read the failed oracle gate and scope matrix, not only headline results."],
        ["Bonus: human interaction","Plain-language request intake with deterministic bounds and confirmation of extracted values.","Use Read this request; a local demonstration does not prove an LLM-backed tuning conversation."]],[102,261,140],size=9.5)
    r.close_note("What is automated, and what required engineering","Once a supported request is submitted, candidate handling, verification and export can run without manual selection. Engineers still chose the topology, developed the bank and calibrated the newer integrated receiver. That distinction is central to assessing the requested zero human intervention objective honestly.")

    r.new("Chapter 2 / Automated framework","Architecture: proposal to evidence","A common request contract connects the user interface to circuit verification.")
    r.figure("architecture","Software architecture. Cached bank scoring and fresh physical acceptance are distinct execution paths with a shared evidence-oriented interface.",210)
    r.heading("2.1 Request and orchestration")
    r.para("The frontend converts a human request into numerical peaking and peak-frequency targets. The Python layer validates units and bounds, chooses the requested design path and runs a protected worker. The interface reports progress and remains usable while the worker runs. A result carries its request, method, circuit identity, verification outcomes and artifact list.")
    r.heading("2.2 Two paths with explicit responsibilities")
    r.para("Adaptive-bank mode combines policy proposals and a visited-candidate shield with a deterministic measured-bank fallback and centering lookup. These classical checks are billed separately. Physical-export mode establishes a fixed eligible setting, emits physical bias and passive devices, and verifies the CTLE. The registry reuses exact accepted targets only after integrity checks; it does not authorize interpolation between targets.")
    r.heading("2.3 Verification is part of the product")
    r.para("The runner parses measurements and simulator diagnostics rather than relying on an exit code. Source hashes connect visible numbers to the files that produced them. Missing artifacts, changed pinned hardware sources and unsuccessful requests remain visible failures or unavailable states. The Receiver tab uses a separate adapter for the latest transistor checkpoint, preventing older policy results from being relabeled as integrated hardware.")

    r.new("Chapter 2 / Learning method","Learning a useful search behavior","The demonstrated policy moves through a characterized circuit bank.")
    r.heading("2.4 Search space and observations")
    r.para("The bank contains 8 attenuation choices x 8 Rs choices x 8 Cs choices: 512 settings across 45 PVT points. This reduced space lets the policy learn from simulator-backed data without paying for a fresh transistor simulation at every policy step. The deployed experiment is discrete code selection; it is not unrestricted continuous sizing of every MOS dimension.")
    r.para("The policy observes the requested peaking and log frequency, the trial fraction, current A/R/C codes and measured eye history. PVT identity, channel loss, compliance labels, quality and oracle answers are hidden from the observation. It can move one code up or down, or lock. Masks disallow out-of-range moves; the experiment caps the trajectory at eight measurements. [E3]")
    r.heading("2.5 Reward, training and acceptance")
    r.para("Quality is the candidate's eye area divided by the best compliant bank eye area for that identity, clipped to 0-1; noncompliant candidates score zero. The improvement environment rewards quality changes and penalizes an invalid final lock. Imitation initializes search, then PPO refines the policy. PPO uses a constrained policy-update objective [R3]; matched controls establish what its training adds.")
    r.para("The design-time safety shield retains the best compliant visited setting, including the fixed start. If no visited setting is compliant, it preserves a failed outcome. This is an engineering acceptance layer with access to verifier truth; it is not a claim that an on-chip receiver can infer all those quantities from the policy observation.")
    r.heading("2.6 Evaluation discipline")
    r.para("Five training seeds were frozen before the final midpoint views were scored. The final set contains 2,430 request/loss/PVT identities; development and final identity membership do not overlap. They still share circuit geometries and the PVT library, so the result measures generalization to new views of that library. Subsequent classical-control and exhaustive-oracle analyses are explicitly exposed-data diagnostics.")
    r.para("The chosen deployment seed remains fixed. Mean results across five seeds describe the experiment and must not be presented as the operational cost of that one deployed policy.",size=10)

    # Remaining chapters are authored below; no earlier report text is mutated.
    return finish_story(r,e)


def finish_story(r,e):
    h=e["hardware"]; n=h["nominal"]; p=h["pvt"]
    agg=e["legacy"]["final"]["aggregate"]
    bench=e["legacy"]["winning"]["benchmark"]["aggregate"]
    r.new("Chapter 2 / Evaluation","What the policy adds","Quality improves, search visits fall, and the comparison retains its unfavorable outcomes.")
    r.figure("learning","Matched controls at an eight-visit cap. PPO plus the shield achieves higher mean quality; local random exploration achieves higher compliance. This is the exposed follow-up comparison, not a new held-out experiment. [E4]",210)
    r.para(f"On the frozen final identities, mean quality rises from 0.5619 at the fixed start to {agg['mean_quality']:.4f}. The paired gain is {agg['quality_delta']:.4f}, with a 95% interval of {agg['paired_quality_delta_ci95'][0]:.4f}-{agg['paired_quality_delta_ci95'][1]:.4f}. All five seeds improve quality. Shielded compliance is {agg['mean_compliance_rate']*100:.2f}%; this still leaves unsuccessful identities. [E3]")
    r.para(f"The exhaustive cached oracle examines 512 settings per identity. The policy uses {bench['mean_policy_visits']:.3f} visits on average, giving {bench['candidate_visit_reduction']:.1f}x fewer candidate visits. This measures table-search effort. Offline characterization, training, policy inference and fresh physical verification are not included in that ratio. [E5]")
    r.heading("The near-optimality claim does not pass")
    r.para(f"Mean regret against the solvable-library oracle is {bench['mean_regret_oracle_solvable']:.5f}; only {bench['fraction_within_0p05']*100:.2f}% of outcomes fall within 0.05 of its quality. The near-optimality gate is therefore false. The study supports a useful low-visit search strategy, not a globally near-optimal analog-design solution.")
    r.para("PPO improves quality over imitation but uses more actual visits; local random rescues more noncompliant starts. The production tool adds classical bank fallback and centering checks beyond this frozen policy experiment. Its complete search cost can therefore exceed the policy-visit count. The 91.8x ratio is not a cost bound for a generated product run.",size=10)

    r.new("Chapter 3 / Circuit implementation","The analog front end","The implementation must preserve the intended response after real loading is added.")
    r.heading("3.1 A CTLE designed around its job")
    r.para("The differential input pair converts voltage into current; poly load resistors convert that current back to differential output voltage. Source degeneration reduces low-frequency gain. As the degeneration capacitance becomes effective at higher frequency, it reduces that feedback and produces relative peaking. Rs, Cs, transistor transconductance and the output load therefore interact; a requested peak cannot be assigned by changing a label.")
    r.para("The input attenuator is a differential resistor-plus-PMOS shunt network ahead of the CTLE. It manages the input excursion presented to the active stage. Each code enables a defined combination of three weighted branches; code A7 enables all three in the calibrated receiver. Disabled switches remain physical devices with parasitics. This is distinct from the Rs/Cs controls inside the source-degeneration network.")
    r.heading("3.2 Physical bias and bypass")
    r.para("A PMOS reference/feed pair, high-poly resistor and diode-connected NMOS derive the tail bias from VDD. A MIM capacitor bypasses the bias node at signal frequencies. Replacing an ideal source with this network makes loading and supply dependence visible. It is a supply-dependent reference, not a precision bandgap or a complete bias-management subsystem.")
    r.table(["FUNCTION","EXACT-DECK IDENTITIES","DESIGN IMPLICATION"],[
        ["Input conditioning","Xatt_sp / Xatt_sn; Xatt_sw*","A code controls shunt paths before the CTLE."],
        ["Differential amplification","XM1 / XM2; Xrlp / Xrln","Actual loads and following-stage capacitance affect the response."],
        ["Tail current and reference","XMT1 / XMT2; Xbpref / Xbpfeed / XMR / Xcbyp","Bias generation and bypass consume area and influence PVT behavior."]],[100,190,213],size=10)
    r.para("Names above are checked against the pinned 73-instance decoding deck [E1]. The frontend's full named-net sheet includes every SKY130 instance and its terminal labels. Simplified circuit guides serve explanation; the exact deck remains the electrical source of truth.",size=10)

    add_analog_detail(r,e)

    r.new("Chapter 3 / Physical tuning","From fixed values to voltage controls","Selectable values in software are only part of a tunable circuit.")
    r.heading("3.3 Implementing variable Rs and Cs")
    r.para("Earlier generated CTLEs export fixed Rs/Cs values. The newer hardware implements a fixed high-poly Rs branch in parallel with a resistor-plus-NMOS branch whose conductance changes with gate voltage. Two N500 SKY130 varactors provide bias-dependent capacitance. Filtered control feeds and bypass devices are included, so the controls have physical loading and dynamics.")
    by_name={row[0]:row for row in e["devices"]}
    r.table(["INSTANCE","TERMINALS FROM THE MEASURED DECK","ROLE"],[
        [key," / ".join(by_name[key][1]),role] for key,role in [
            ("Xrc_rmax","Fixed degeneration branch"),
            ("Xrc_branch","Series branch resistor"),
            ("Xrc_switch","Voltage-controlled NMOS branch"),
            ("Xrc_var_s1","First bias-controlled varactor"),
            ("Xrc_var_s2","Second bias-controlled varactor")]], [110,225,168],size=10)
    r.heading("3.4 Calibrating the loaded receiver")
    r.para("Adding the transistor DFE changes the load seen by the CTLE. The previous control setting therefore could not inherit the standalone target match. A bounded 65-point loaded OP/AC calibration selected R = 0.70 VDD and C = 0.185 VDD: 1.260 V and 0.333 V at 1.8 V supply. Geometry was held fixed. Independent verification then measured the response again. [E1]")
    r.para("The calibrated response is 8.744-8.747 dB at 1.903-1.906 GHz. It satisfies the unchanged internal +/-0.5 dB / +/-100 MHz target tolerances around 9 dB / 1.9 GHz. The reported boost is the measured value, not exactly 9 dB.")
    r.close_note("What tuning is demonstrated","The circuit contains electrical Rs/Cs controls, and the saved receiver result holds their supply fractions fixed across PVT. This single loaded calibration does not demonstrate arbitrary target coverage or DFE-active runtime tuning. Standalone tuning experiments remain separate evidence.")

    add_link_detail(r,e)

    r.new("Chapter 3 / Transistor DFE","Closing the feedback path","The previous decided bit must return as a correctly timed physical correction.")
    r.figure("receiver","Transistor DFE integration. The CTLE drives a CML summer; master/slave memory stores the decision; the current DAC returns the correction to the summer. Clock and control generators remain external. [E1]",190)
    r.heading("3.5 Why the behavioral score was insufficient")
    r.para("A cursor-based DFE score can estimate how much one previous symbol could be cancelled. It does not implement the sampler, memory, feedback current, loading or timing needed to produce that cancellation. The hardware checkpoint therefore uses a transistor summer and clocked CML master/slave memory rather than transferring a behavioral eye result to a circuit claim.")
    r.heading("3.6 Making the implementation measurable")
    r.para("The held decision nodes df_q / df_qb steer Xdfe_dacp / Xdfe_dacn into sum_p / sum_n. Four weighted feedback branches set the tap strength. Physical bleeders stabilize the off-branch behavior. The calibrated experiment uses tap code 2 and phase 1 UI, retained unchanged at every PVT point. The full deck contains 73 SKY130 instances across the receiver.")
    r.para("The output is checked using the actual differential summer waveform and stored decision trace. A valid run must include the full time interval, finite signals, the expected controls and a correctly scored pattern. A simulator exit status alone is not enough. This measurement discipline was necessary because earlier numerical aborts could otherwise look like successful batch runs.")
    r.para("The result is a functioning calibrated transistor feedback path in simulation. Clock recovery, on-chip control generation, periodic receiver-noise analysis and extracted interconnect are beyond this checkpoint.",size=10)

    r.new("Chapter 4 / Nominal verification","Independent nominal measurements","Calibration selected controls; separate runs tested the resulting circuit.")
    r.para("Entry 143 performs independent nominal checks at TT / 1.8 V / 27 deg C after the loaded calibration. Static held-clock checks measure AC response and input-referred noise. Clocked tone runs measure CTLE-output HD3. A fresh link run measures decoding and the eye at the transistor summer. These tests answer different questions and are reported separately. [E1]")
    r.table(["MEASUREMENT","RECORDED RESULT","TEST DEFINITION"],[
        ["Boost / peak",f"{n['boost_db']['min']:.3f}-{n['boost_db']['max']:.3f} dB<br/>{n['peak_frequency_hz']['min']/1e9:.3f}-{n['peak_frequency_hz']['max']/1e9:.3f} GHz","Nominal held-state AC; target 9 dB / 1.9 GHz"],
        ["Input noise",f"{n['input_noise_vrms']['max']*1e3:.5f} mVrms maximum","10 MHz-5 GHz; two negative-branch held-clock states"],
        ["HD3",f"{n['hd3_dbc']['min']:.4f} to {n['hd3_dbc']['max']:.4f} dBc","Clocked; 100 MHz tone; 100 mV differential peak input"],
        ["Decoding",f"{n['correct_bits']}/{n['scored_bits']} scored bits correct","Finite noiseless pattern; constructed 7.5 dB channel"],
        ["Summer eye",f"{n['sampled_eye_height_v']*1e3:.3f} mV; {n['width_above_100mv_ui']:.3f} UI above 100 mV","Positive opening 0.705 UI; finite waveform aperture"],
        ["VDD power",f"{n['vdd_power_w']*1e3:.5f} mW","CTLE + transistor DFE during decoding; external apparatus excluded"]],[100,180,223],size=10)
    r.heading("4.1 Numerical and measurement cross-checks")
    r.para("Four tone-run numerical settings and all harmonic windows agree on the HD3 result. Noise is checked against its spectrum integral; ngspice's integrated noise value is already RMS volts and must not be square-rooted again. These checks address plausible-looking unit and numerical errors rather than only checking that a file exists.")
    r.para("Held-clock noise is not periodic noise of the active receiver. HD3 is a nominal result for the simulated device/passive models. Neither number establishes analog PVT or omitted passive voltage-dependent distortion.",size=10)

    r.new("Chapter 4 / Link experiment","A recovered eye across sampled PVT","The same control fractions, tap code and phase are used at all 45 points.")
    r.figure("pvt","All 45 measured link points, grouped by transistor corner. Dashed limits mark 100 mV sampled eye and 15 mW VDD power. The plotted values come directly from the pinned PVT summary. [E2]",290)
    r.para("The grid combines TT, SS, FF, SF and FS with 1.71, 1.80 and 1.89 V, and 0, 27 and 125 deg C. Every point uses the same constructed 7.5 dB channel and scores the same 64-bit pattern after warm-up. There is no corner-by-corner retuning. All 45 points recover 64/64 scored bits.")
    r.para(f"The smallest sampled eye is {p['minimum_eye_height_v']*1e3:.3f} mV at FS / 0.95 VDD / 125 deg C. Minimum positive opening is {p['minimum_positive_width_ui']:.3f} UI, and the minimum width above 100 mV is {p['minimum_width_above_100mv_ui']:.3f} UI. Maximum VDD power is {p['maximum_vdd_power_w']*1e3:.4f} mW. External positive clock power is reported separately, reaching {p['maximum_external_clock_positive_power_w']*1e3:.6f} mW.")
    r.close_note("Interpretation","This supports sampled link robustness at the calibrated setting. It is a finite, noiseless simulation result on one constructed channel; it is not a BER estimate, continuous-temperature guarantee or simultaneous S3-S8 analog PVT signoff.")

    r.new("Chapter 4 / Waveform and scope","What the eye proves","An inspectable waveform is stronger evidence than a pass badge, within its stated test.")
    r.figure("eye","Nominal summer eye reconstructed from the pinned transient waveform. The shaded region is the scored sample window. No noise or additional bits are synthesized for this figure. [E1]",245)
    r.para("The sampled voltage separation and the time aperture both exceed the declared eye thresholds for this experiment. Folding the saved signal also exposes the finite pattern and clock relationship behind the numbers. A low measured error count over 64 scored bits cannot support a low-BER claim; no such extrapolation is made.")
    r.heading("4.2 Power, area and model boundaries")
    r.para("The known geometry subtotal is 0.014715766 mm2, below the 0.05 mm2 numerical limit, but it is not routed layout area. Routing, well spacing, contacts, pads and physical verification can change the final footprint. VDD power includes the drawn CTLE and DFE; external clocks, control voltages and common-mode generation prevent a full receiver-power claim.")
    r.para("The strict new-DFE voltage checks and whole-circuit magnitude/body and varactor envelopes pass. Separately retained signed bilateral Rs-switch Vds findings occur at all 45 points; they are not silently converted into a reliability pass. Typical passives, absent mismatch/tolerance analysis and ignored generic-poly nonlinear coefficients remain model boundaries. [E1-E2, E4]")
    return finish_product_chapters(r,e)



def add_analog_detail(r,e):
    r.new("Chapter 3 / Circuit detail", "The source-degenerated CTLE",
          "The fixed physical export explains the core; the later receiver adds voltage-controlled degeneration.")
    r.figure("submission_core", "Source-degenerated CTLE from the earlier verified physical export [E6]. Equal net names connect the attenuator and bias diagrams. Rs and Cs shown here are fixed drawn elements, not the later voltage-control network.",300)
    r.table(["DEVICE / ELEMENT", "FIXED-EXPORT VALUE"], [
        ["M1 / M2", "Total W = 57.9767 um; L = 0.39115 um; four fingers"],
        ["MT1 / MT2", "W = 201.656 um; L = 0.5 um; eight fingers"],
        ["Each load / external CL", "254.633 ohm / 32.628 fF per output"],
        ["Rs / Cs between sources", "356.818 ohm / 2.85155 pF"]], [175,328],size=9.8)
    r.para("At low frequency, Rs reduces effective transconductance and therefore gain. At higher frequency, Cs bypasses the degeneration so the response rises before output capacitance and device poles impose roll-off. The input attenuator controls signal excursion; it is not the source of CTLE peaking.")
    r.para("The first-order zero is approximately fz = 1/(2 pi Rs Cs), while the degeneration pole is shifted by k = 1 + (gm + gmb)Rs/2. These equations explain design direction. The measured peak comes from SPICE because parasitics and the following stage change the actual response.")

    r.new("Chapter 3 / Bias detail", "Reference current made physical",
          "A transistor-and-resistor reference replaces an ideal current source and exposes its real costs.")
    r.figure("submission_bias", "PMOS reference/feed mirror, poly bias resistor, diode-connected NMOS reference and MIM bypass in the fixed physical export [E6]. PMOS bulks connect to VDD and the NMOS bulk to ground.",280)
    r.table(["IMPLEMENTATION", "GEOMETRY / PURPOSE"], [
        ["MPref / MPfeed", "W/L = 25.2069/0.5 um; supply-dependent PMOS reference"],
        ["MR and tail mirror", "MR W/L = 25.2069/0.5 um; each tail has eight times the width"],
        ["Rbias", "Poly W/L = 1/5.34 um; nominal 2.072 kohm"],
        ["Cbyp", "MIM 70.545 x 70.545 um; approximately 10 pF"]], [166,337],size=9.8)
    r.para("Reference geometry sets a design intention; the transistors and resistor determine the operating current. The diode-connected PMOS establishes p_bias, the feed device supplies the NMOS reference, and nbias drives the two CTLE tails. The bypass capacitor keeps this node relatively quiet at signal frequencies.")
    r.para("Supply power is measured as -VDD x I(VDD), so reference consumption and mirror error are included. The circuit is a compact supply-dependent bias, not a precision bandgap. Its value is removing an ideal-source assumption and making PVT behavior measurable. The newer integrated receiver retains physical bias and counts its loading and geometry [E1].")

    r.new("Chapter 3 / Input conditioning", "Physical attenuation and peaking",
          "Signal scaling, relative boost and absolute voltage gain answer different engineering questions.")
    r.figure("submission_attenuator", "Positive input leg of the fixed physical CTLE export [E6]; the negative leg is identical. Three real PMOS-switched shunts connect inp to cm. A7 holds all three gates at zero volts. Width labels are total microns, with L = 0.15 um.",205)
    r.para("Each differential leg uses a 150 ohm series target and three weighted shunt branches. Their switches have resistance and capacitance, including when a branch is disabled. A7 enables all three branches in the calibrated receiver. The attenuation code controls input excursion; the Rs/Cs network controls degeneration.")
    r.figure("submission_ac", "Earlier fixed-export AC magnitude with its 45-corner envelope [E6]. This is absolute voltage gain. These curves belong to the earlier CTLE experiment and do not establish all-PVT analog response for the later integrated receiver.",240)
    r.para("Peaking is the maximum AC gain relative to low-frequency gain. A circuit can therefore have about 9 dB of peaking while its absolute peak gain stays near 0 dB. Channel insertion loss is a separate quantity. Preserving absolute amplitude is essential when the next calculation asks whether an eye exceeds 100 mV.")


def add_link_detail(r,e):
    fixed=e["legacy"]["summary"]["fixed"]
    r.new("Chapter 3 / Device-to-link bridge", "From transistor response to eye",
          "The earlier model connects measured transistor response to a receiver metric at manageable search cost.")
    r.para("The bridge fits a one-zero/two-pole response to the measured CTLE magnitude, checks fit quality and measured output swing, and composes it with the transmitter and channel. It preserves absolute voltage scale. Pulse cursors then describe desired signal and intersymbol interference, avoiding a transistor transient for every candidate and bit pattern.")
    r.figure("submission_eyes", "Minimum-to-maximum modeled eye across 45 PVT points at each constructed channel loss, using ideal behavioral 1-tap cancellation [E6]. This earlier 315-condition model dataset is separate from the newer 45-point transistor link experiment.",245)
    r.table(["LINK CONDITION", "DECLARED MODEL SETTING"], [
        ["Transmitter", "0.8 V differential peak-to-peak; -3.5 dB de-emphasis"],
        ["Channels", "Constructed minimum-phase skin/dielectric-loss family; 3-12 dB at Nyquist in 1.5 dB steps"],
        ["Sampling / eye", "64 samples/UI; height at pulse cursor; contiguous positive-opening width"],
        ["Circuit", "One fixed geometry and code across all conditions; no channel-specific resizing"]], [145,358],size=9.6)
    r.para("These are noiseless cursor-based ISI openings, not BER contours. Noise is not subtracted; phase is inferred from the magnitude fit. Random jitter, clock recovery and decision-error propagation are absent. The later transistor experiment is a stronger implementation check, while its finite noiseless pattern also has a clearly stated boundary.")

    r.new("Chapter 3 / Decision feedback", "What the 1-tap DFE contributes",
          "The behavioral comparison explains cancellation; the next section shows how it became a physical feedback path.")
    r.figure("submission_dfe", "Nominal 7.5 dB-channel cursors and worst modeled width under four DFE policies across the earlier 315 conditions [E6]. These are saved model comparisons, not measurements of four transistor implementations.",235)
    r.para("The normalized tap is b1 = h1/h0. The previous decision cancels the first post-cursor; the remaining pre- and post-cursors limit the opening. Under ideal cancellation, eye height is 2(h0 - the sum of the remaining absolute cursor amplitudes), clipped at zero.")
    pol=fixed["dfe_policies"]
    r.table(["TAP POLICY", "MIN HEIGHT", "MIN WIDTH"], [
        [label,f"{pol[key]['min_eye_h_v']*1000:.2f} mV",f"{pol[key]['min_eye_w_ui']:.4f} UI"]
        for key,label in [("ideal","Ideal first-post-cursor cancellation"),("misadapted","20% of first post-cursor remains"),("quantised","Tap step 1/16; clipped to +/-0.5"),("none","No cancellation")]], [259,122,122],size=9.6)
    r.para("All four policies meet the eye thresholds for this circuit and channel family. The clearest benefit is additional width margin; the CTLE already supports the height target. The quantized model is not a claim of a realized four-bit DAC.")
    r.para("At the nominal 7.5 dB channel, h0 = 184.99 mV and h1 = -43.43 mV give b1 = -0.2348. The ideal-tap opening is 255.81 mV and 0.8125 UI. Turning that arithmetic into hardware requires a summer, timed decision memory and feedback current. Those elements are now present in the separate calibrated transistor checkpoint, replacing the older report's then-current failed-prototype status [E1-E2].")


def finish_product_chapters(r,e):
    r.new("Chapter 5 / Engineering decisions","Decisions shaped by failure","The difficult work was making an attractive result survive a more physical test.")
    r.heading("5.1 An apparently successful simulation")
    r.para("ngspice can emit warnings or incomplete results while returning exit code zero. Early toolchain work also exposed unit-scaling and duplicated-model hazards. The response was to make the exact deck authoritative, retain logs, check warning fingerprints, validate trace length and independently derive measurements. This converted silent failures into actionable engineering outcomes.")
    r.heading("5.2 A passing score without the required hardware")
    r.para("Behavioral equalization established a useful link-search model, but did not supply the transistor decision path or real Rs/Cs controls. Physical bias, switch and varactor networks and a CML feedback chain were therefore added as separately measured stages. The old results remained valid within their original scopes; they were not rebranded as evidence for newly added devices.")
    r.heading("5.3 Integration changed the response")
    r.para("Loading from the DFE shifted the CTLE response away from the intended target. A bounded OP/AC calibration selected new external control fractions while keeping geometry fixed. Separate nominal and PVT runs then checked that setting. This is why the final report identifies calibration, nominal verification and corner verification as three different steps. [E1-E2]")
    r.heading("5.4 Search efficiency did not imply optimality")
    r.para("A favorable mean quality gain and fewer search visits initially left open the question of how much performance was missed. The exhaustive oracle exposed substantial regret, while local random exploration achieved better compliance under the matched budget. Those results changed the competitive claim: useful RL-assisted search is demonstrated; global near-optimality and universal superiority are not. [E3-E5]")
    r.close_note("The engineering lesson","Each stronger check changed either the circuit, the acceptance logic or the claim. Keeping failed runs and older scopes intact makes that progression auditable and gives the next iteration a precise starting point.")

    r.new("Chapter 5 / Desktop product","A product an engineer can inspect","The interface organizes the evidence around the questions a reviewer will ask.")
    screenshot=ROOT/"nebula/report/assets/submission_20260914/receiver_desktop.png"
    if not screenshot.is_file():
        raise ValueError("Capture the reviewed desktop receiver before building the submission report")
    from shutil import copyfile
    copyfile(screenshot,SCRATCH/"desktop.png")
    r.figure("desktop","The desktop Receiver view, captured from the local application. A signal-path overview leads to a readable circuit inspector and scoped measurements. The exact device sheet is available separately.",230)
    r.heading("5.5 Progressive inspection")
    r.para("The Receiver view opens on the calibrated hardware checkpoint. A reader first sees the implemented signal path, then selects a block to understand its connections. The recovered eye and measurements share one evidence region. The full device sheet and source files are available on demand rather than competing with the main explanation.")
    r.para("Design Explorer handles numerical targets and generated-run results. Its circuit blocks expand one at a time, preserving readable labels. Selected A/R/C codes and fixed-export values stay attached to the chosen run. The DFE reference is explicitly identified as a separate transistor implementation, while the run's original cursor-based score remains visible in its verification scope.")
    r.heading("5.6 A demo that does not borrow a pass")
    r.para("Changing the target away from 9 dB / 1.9 GHz hides the calibrated receiver's eye and measurement claims for that request. Returning through judge mode restores the saved target. Design PVT, comparison and run-file views refer to the selected generated design. The interface distinguishes saved evidence from a new verification job; the accompanying narration follows the same distinction.")

    r.new("Chapter 5 / Reproducibility","From a result to its source","A reviewable submission includes enough information to challenge its own conclusions.")
    r.heading("5.7 Reproducing the evidence chain")
    r.para("Each hardware claim is tied to pinned summaries, an exact nominal deck and retained raw measurements. The 45-point Link PVT manifest lists 362 files. The report builder checks saved evidence hashes before drawing charts; it performs no training or fresh circuit campaign. The companion report source manifest connects this PDF to its inputs and the code used to create it.")
    r.para("To review the receiver, open its exact deck, then compare the nominal result with the held-state AC/noise and clocked tone records. For PVT, inspect a nominal point and the minimum-eye corner, checking that control fractions, tap code, phase and geometry remain unchanged. Use the actual SPICE options inside each deck: the shared dispatch folder labels are not authoritative solver settings for every analysis type.")
    r.heading("5.8 Account for the cost that preceded the fast result")
    r.table(["RECORDED WORK","TIME / EFFORT","INTERPRETATION"],[
        ["Bank, midpoint data and five PPO training stages","6.711 hours summed recorded stages","Partial historical cost subtotal; excludes earlier sizing, imitation and other audits."],
        ["Loaded calibration (Entry 142)","65 OP/AC pairs; 33.445 s","A bounded circuit calibration, not policy search."],
        ["Independent nominal checks (Entry 143)","7 checks; 331.018 s","Separate from choosing the controls."],
        ["Fixed-control Link PVT (Entry 144)","45 calls; 1,921.963 s","Includes 2.955 s preflight; one constructed channel."]],[166,132,205],size=9.7)
    r.para("Recorded stage times are not an independently measured sequential project duration. The 91.8x result is a cached candidate-visit reduction; no matched end-to-end sweep of all MOS/R/C/L parameters has established that ratio as a wall-clock or SPICE speedup. [E4-E5]")
    r.para("Launch the desktop demonstration from the repository root with <b>py -3.13 -m nebula.web</b>. The separate narration guide lists screen actions, the saved-evidence route and exact phrases for presenting these boundaries.",size=10)

    r.new("Chapter 6 / Submission assessment","Evidence against S1-S9","This matrix applies the published specification, not an invented judging score.")
    r.table(["SPECIFICATION","CURRENT EVIDENCE","ASSESSMENT"],[
        ["S1 / 5 Gbps NRZ","200 ps UI, transistor decoding experiment, constructed channel.","Demonstrated in simulation; not full PCIe protocol compliance."],
        ["S2 / CTLE + variable Rs/Cs + 1-tap DFE","Drawn physical controls, summer, decision memory and current DAC.","Topology implemented in the calibrated deck."],
        ["S3 / 3-12 dB; 1.25-2.5 GHz","Loaded nominal 8.744-8.747 dB at 1.903-1.906 GHz. Earlier fixed exports cover 3/6/9 dB at 1.9 GHz.","Single loaded calibration; full target rectangle and all-PVT response unverified."],
        ["S4 / HD3 below -30 dBc","About -54.92 dBc at 100 MHz, 100 mV differential peak.","Nominal clocked check passes; analog PVT and omitted passive nonlinearity open."],
        ["S5 / Noise below 1.5 mVrms","Maximum 0.65405 mVrms over 10 MHz-5 GHz.","Nominal held-clock model passes; periodic and analog PVT noise open."],
        ["S6 / Power below 15 mW","Maximum drawn-receiver VDD power 12.5241 mW in Link PVT.","Pass within measured boundary; external generation excluded."],
        ["S7 / Area below 0.05 mm2","Known geometry subtotal 0.014715766 mm2.","Not routed area; layout signoff unverified."],
        ["S8 / Eye above 100 mV and 0.4 UI","Minimum sampled eye 113.244 mV; minimum width above 100 mV 0.560 UI.","45/45 sampled link points pass; finite noiseless pattern, not BER."],
        ["S9 / All specs across PVT","Five transistor corners x three supplies x three temperatures, fixed controls.","Link PVT demonstrated; simultaneous S3-S8 signoff incomplete."]],[111,228,164],size=9.2)
    r.para("The earlier 315-case CTLE/model records and the newer 45-point transistor-receiver experiment are separate evidence sets. Their counts cannot be combined into an expanded hardware validation campaign.",size=10)

    r.new("Chapter 6 / Conclusions","What the submission establishes","A working automation product, a measured hardware checkpoint, and a precise next step.")
    r.heading("6.1 Delivered contribution")
    r.para("Nebula turns a target request into an inspectable circuit-design workflow: structured input, learned candidate proposals, deterministic checks, simulator integration, circuit exports and reviewable evidence. Its strongest product contribution is that these parts work together and distinguish an accepted result from an unsupported request. The user can inspect the engineering outcome rather than accepting a model's assertion.")
    r.para("The transistor work closes an important implementation gap. A voltage-configurable CTLE with physical bias and a transistor 1-tap DFE now meets the nominal calibrated target tolerances and passes 45/45 sampled Link PVT points using fixed controls. Independent analog checks and exact raw files support that claim. The later receiver is an engineering development built alongside the automation framework, not evidence of autonomous PPO discovery.")
    r.heading("6.2 Competitive strengths supported by evidence")
    r.para("The submission combines an open-source process and simulator, an implemented receiver topology, measurable policy comparisons and an evidence-driven interface. It addresses the central deliverable directly: specifications in, a circuit and resulting specifications out. The report and video together show both the user workflow and the implementation beneath it.")
    r.heading("6.3 Prioritized completion roadmap")
    r.para("<b>First, close the electrical coverage.</b> Measure loaded response, noise and distortion across the required PVT grid; extend the target map and verify DFE-active control settling. A single well-supported calibration is the starting point, not the end of tunability.")
    r.para("<b>Next, close implementation realism.</b> Resolve the signed Rs-switch model-domain findings, passive nonlinearity, mismatch and tolerances. Add clock/control generation, layout, DRC/LVS and extracted verification before claiming final area, full receiver power or reliability.")
    r.para("<b>Then, strengthen the automation claim.</b> Extend the policy's design variables where circuit evidence supports them, improve feasibility recovery, and compare against strong classical optimizers with equal physical SPICE-call and wall-clock budgets. Preserve the frozen results as the baseline for those tests.")

    r.new("References / Evidence index","Methods and source artifacts","External methods are cited separately from project measurements.")
    r.para('<b>[R1]</b> SkyWater SKY130 PDK documentation. Device families, model interfaces and process documentation. <link href="https://skywater-pdk.readthedocs.io/en/main/" color="#1764b0">Official documentation</link>.<br/><b>[R2]</b> ngspice project. User manual and simulator documentation. <link href="https://ngspice.sourceforge.io/docs.html" color="#1764b0">Official documentation index</link>.<br/><b>[R3]</b> J. Schulman et al., <i>Proximal Policy Optimization Algorithms</i>, 2017, arXiv:1707.06347. <link href="https://arxiv.org/abs/1707.06347" color="#1764b0">Original paper</link>.',size=10)
    r.heading("Project evidence (paths relative to the repository)")
    r.table(["KEY","ARTIFACT / PURPOSE"],[
        ["E1","nebula/DFE_CALIBRATED_RESULTS.md; product_audits/entry143_dfe_calibrated_verification_20260910/ - exact deck, independent nominal checks and waveform."],
        ["E2","nebula/product_audits/entry144_dfe_calibrated_pvt_20260910/ - fixed-control 45-point Link PVT, raw files and integrity manifest."],
        ["E3","nebula/experiments/shielded_policy_final_results.json - frozen final identities, seeds, observation contract and policy outcomes."],
        ["E4","nebula/POST_REVIEW_RESULTS.md; product_audits/entry113_attribution_20260907/ and entry113_models_20260907/ - matched controls, model audit and historical cost accounting."],
        ["E5","nebula/product_audits/entry115_exhaustive_benchmark_20260908/ - cached exhaustive oracle, visit reduction and failed near-optimality gate."],
        ["E6","nebula/product_demo/physical_bias_9db_1p9ghz_20260906/; product_audits/entry115_physical_recovery_20260908/ - earlier physical CTLE exports and recovered 3/6 dB targets."],
        ["E7","CLAUDEwa.md - repository transcription of the challenge deliverables and S1-S9 contract; nebula/web/ - implemented desktop and API paths."]],[35,468],size=9.4)
    r.para("Directory fragments beginning product_audits/ are under nebula/. Each cited result keeps its original scope. The companion *_sources.json records SHA-256 input/output hashes; *_review.json records rendering and document checks. Both earlier report PDFs are preserved unchanged for comparison.",size=9.6)
    r.save()
    sources=[Path(__file__),ROOT/"nebula/report/competition_2026.py",ROOT/"nebula/report/competition_submission.py",
             ROOT/"nebula/report/check_submission_story.py",FINAL,NOMINAL_SUMMARY,PVT_SUMMARY,NOMINAL_NETLIST,
             POINT/"trace.txt.gz",ROOT/"nebula/DFE_CALIBRATED_RESULTS.md",ROOT/"nebula/POST_REVIEW_RESULTS.md",
             ROOT/"CLAUDEwa.md",ROOT/"nebula/web/hardware_checkpoint.py",ROOT/"nebula/web/hardware_visuals.py",
             ROOT/"nebula/web/static/app.js",ROOT/"nebula/web/static/circuit_views.js",ROOT/"nebula/web/static/styles.css",
             ROOT/"nebula/web/static/index.html",ROOT/"nebula/rl/margin_improve_env.py",ROOT/"nebula/rl/margin_adapt_env.py",ROOT/"nebula/rl/safety_shield.py",ROOT/"nebula/rl/hybrid_designer.py",
             PHYS/"summary.json",PHYS/"evidence_sha256.json",WIN_BENCH/"summary.json",WIN_BENCH/"sha256.json",
             WIN_RECOVERY/"summary.json",WIN_RECOVERY/"sha256.json",screenshot]
    sources += [folder/"summary.json" for folder in POST_DIRS.values()]
    sources += [folder/name for folder in (NOMINAL_ROOT,PVT_ROOT)
                for name in ("evidence_sha256.json","trace_archives.json")]
    sources += [ROOT/"nebula/experiments/evidence_archive.py"]
    manifest={"report":PDF.name,"page_count":r.n,"report_sha256":sha(PDF),
              "edition":"Independent submission story / 2026-09-14","previous_reports_preserved":PREVIOUS,
              "content_bottoms_pt":r.content_bottoms,"figures":r.figures,
              "hardware_archive_checks":e["archive_checks"],
              "page_font_scales":dict(_PAGE_SCALES),
              "paragraph_counts":r.paragraph_counts,"page_spacing_adjustment_pt":dict(_PAGE_SPACING),
              "sources":[source_record(path) for path in sources],
              "scope":"Latest calibrated receiver and frozen policy evidence are separate; no new simulation or training."}
    verify_sources(manifest["sources"])
    MANIFEST.write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    print(f"Created {PDF.name}: {r.n} pages; both previous PDFs preserved.")
    return PDF


def build_balanced():
    """Fill each page with readable content and figures, preserving normal margins."""
    from shutil import copyfile
    import nebula.report.competition_submission as legacy
    e=load_story_evidence()
    make_story_figures(e)
    # Only generate reusable figures; never rebuild either preserved report.
    original_scratch=legacy.SCRATCH
    legacy.SCRATCH=SCRATCH / "legacy_figures"
    try:
        legacy.make_figures(e["legacy"])
        for name in ("submission_core", "submission_bias", "submission_attenuator",
                     "submission_ac", "submission_eyes", "submission_dfe"):
            copyfile(legacy.SCRATCH / f"{name}.png", SCRATCH / f"{name}.png")
    finally:
        legacy.SCRATCH=original_scratch
    _PAGE_SCALES.clear(); _PAGE_SPACING.clear()
    # Typography handles large gaps first. Small remaining differences are
    # distributed between paragraphs, without stretching any glyph or diagram.
    for attempt in range(5):
        build(e)
        manifest=json.loads(MANIFEST.read_text())
        bottoms=manifest["content_bottoms_pt"]
        counts=manifest["paragraph_counts"]
        corrections=[(760-y)/count for y,count in zip(bottoms,counts)]
        if all(-3 <= extra <= 5 for extra in corrections):
            _PAGE_SPACING.update(enumerate(corrections,1))
            build(e)
            final=json.loads(MANIFEST.read_text())
            assert all(759.9 <= y <= 760.1 for y in final["content_bottoms_pt"])
            print("Balanced layout: every page ends at the same normal bottom margin.")
            return PDF
        for page,(bottom,extra) in enumerate(zip(bottoms,corrections),1):
            if not -3 <= extra <= 5:
                old=_PAGE_SCALES.get(page,1.0)
                _PAGE_SCALES[page]=old*((760-116)/max(bottom-116,1))**0.48
    raise ValueError(f"Layout did not converge: {bottoms}")


if __name__=="__main__":
    build_balanced()
