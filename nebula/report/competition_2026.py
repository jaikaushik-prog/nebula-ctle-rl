"""Fresh, evidence-derived competition report; no SPICE or model mutation.

Run from the repository root: py -3.13 -m nebula.report.competition_2026
Requires reportlab, matplotlib and Pillow. PDF QA additionally uses PyMuPDF.
All report narrative and plots are new; earlier report builders are not read.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/pdf"
SCRATCH = ROOT / "tmp/pdfs/competition_2026"
A100 = ROOT / "nebula/product_audits/entry100_20260906"
A101 = ROOT / "nebula/product_audits/entry101_fixed490_20260906"
FINAL = ROOT / "nebula/experiments/shielded_policy_final_results.json"
PRODUCT = ROOT / "nebula/product_demo/rl_hybrid_9db_1p9ghz/design.json"


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_rows(path):
    return [json.loads(s) for s in Path(path).read_text(encoding="utf-8").splitlines() if s.strip()]


def evidence():
    a, b = read_rows(A100 / "fixed_pvt.jsonl"), read_rows(A101 / "fixed_pvt.jsonl")
    requests = read_rows(A100 / "request_accuracy.jsonl")
    final, product = read_json(FINAL), read_json(PRODUCT)
    summary = read_json(A101 / "summary.json")
    assert len(a) == len(b) == 45 and len(requests) == 12
    assert len({r["corner"] for r in b}) == 45
    assert len({r["circuit_signature"] for r in b}) == 1
    assert all(r["setting"] == 490 and r["ok"] for r in b)
    assert sum(x["model_pass"] for r in b for x in r["links"]) == 315
    assert summary["fixed"]["full_product_compliance"] is False
    assert summary["adopted"] is False and product["search"]["setting"] == 425
    return a, b, requests, final, product, summary


def figures(a, b, requests, final):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.colors import LinearSegmentedColormap
    from nebula.report.schematic import draw_schematic

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.labelcolor": "#25354b", "text.color": "#16263c",
                         "xtick.color": "#526479", "ytick.color": "#526479",
                         "axes.edgecolor": "#c4d0db", "figure.facecolor": "white"})
    blue, teal, amber = "#1764b0", "#008575", "#bd6627"

    def save(fig, name):
        fig.savefig(SCRATCH / f"{name}.png", dpi=210, bbox_inches="tight", facecolor="white")
        plt.close(fig)

    matrix = np.array([r["n_compliant"] for r in requests]).reshape(4, 3)
    fig, ax = plt.subplots(figsize=(8, 3.8))
    cm = LinearSegmentedColormap.from_list("coverage", ["#fbe6d3", "#edf5f3", "#58b7a5"])
    ax.imshow(matrix / 315, cmap=cm, vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(3), ["1.25 GHz", "1.90 GHz", "2.50 GHz"])
    ax.set_yticks(range(4), ["3 dB", "6 dB", "9 dB", "12 dB"])
    ax.set_xlabel("Requested peak frequency", labelpad=12)
    ax.set_ylabel("Requested peaking", labelpad=12)
    for i in range(4):
        for j in range(3):
            n = matrix[i, j]
            ax.text(j, i, f"{n}/315\n" + ("FULL GRID" if n == 315 else f"{315-n} unsupported"),
                    ha="center", va="center", fontsize=11, linespacing=1.6)
    for sp in ax.spines.values():
        sp.set_visible(False)
    save(fig, "coverage")

    corners = sorted(r["corner"] for r in b)
    by_a, by_b = {r["corner"]: r for r in a}, {r["corner"]: r for r in b}
    fig, axes = plt.subplots(2, 1, figsize=(8.5, 5.3), sharex=True, layout="constrained")
    for rows, col, label in [(by_a, amber, "425 - current export"), (by_b, blue, "490 - fixed candidate")]:
        axes[0].plot([rows[c]["meas"]["peaking_db"] for c in corners], "o-", ms=3, lw=1, color=col, label=label)
        axes[1].plot([2.5 * 2 ** rows[c]["meas"]["f_peak_oct"] for c in corners], "o-", ms=3, lw=1, color=col)
    axes[0].axhline(7.5, color="#af3838", ls="--", lw=1)
    axes[0].text(1, 7.56, "9 dB request: lower acceptance edge = 7.5 dB", fontsize=8, color="#af3838")
    axes[0].axhline(9, color="#a8b5c3", ls=":", lw=1)
    axes[0].set_ylabel("Peaking (dB)")
    axes[0].legend(loc="upper left", fontsize=8, ncol=2)
    axes[0].set_ylim(7.1, 10.3)
    axes[1].axhline(1.9, color="#a8b5c3", ls=":", lw=1)
    axes[1].axhline(1.9 / 2 ** .3, color="#af3838", ls="--", lw=1)
    axes[1].set_ylabel("Peak frequency (GHz)")
    axes[1].set_xlabel("Process group; each contains all 3 supplies x 3 temperatures")
    axes[1].set_xticks([4, 13, 22, 31, 40], ["FF", "FS", "SF", "SS", "TT"])
    for ax in axes:
        ax.grid(axis="y", alpha=.18)
        for pos in [8.5, 17.5, 26.5, 35.5]:
            ax.axvline(pos, color="#c4d0db", lw=.7)
    save(fig, "pvt")

    fig, axes = plt.subplots(1, 3, figsize=(9, 3.1), layout="constrained")
    groups = ["tt", "ss", "ff", "sf", "fs"]
    for ax, key, scale, title, limit in [
        (axes[0], "inoise_vrms", 1000, "Input noise (mVrms)", 1.5),
        (axes[1], "power_w", 1000, "CTLE power (mW)", 15),
        (axes[2], "hd3_100mhz_dbc", 1, "HD3 at 100 MHz (dBc)", -30)]:
        for i, group in enumerate(groups):
            vals = [(r[key] if key in r else r["meas"][key]) * scale for r in b if r["corner"].split('/')[0] == group]
            ax.scatter(np.linspace(i-.13, i+.13, len(vals)), vals, s=19, color=blue, alpha=.75)
        ax.axhline(limit, color=amber, ls="--", lw=1)
        ax.set_xticks(range(5), [g.upper() for g in groups], fontsize=8)
        ax.set_title(title, fontsize=10, pad=12)
        ax.grid(axis="y", alpha=.15)
    axes[0].set_ylim(0, 1.65)
    axes[1].set_ylim(0, 16.5)
    axes[2].set_ylim(-95, -23)
    save(fig, "electrical")

    pol = read_json(A101 / "summary.json")["fixed"]["dfe_policies"]
    names = ["ideal", "misadapted", "quantised", "none"]
    labels = ["Ideal 1-tap", "20% residual", "Quantised tap", "No DFE"]
    fig, axes = plt.subplots(1, 2, figsize=(8.5, 3.6), layout="constrained")
    for ax, key, scale, threshold, label in [(axes[0], "min_eye_h_v", 1000, 100, "Minimum height (mV)"),
                                            (axes[1], "min_eye_w_ui", 1, .4, "Minimum width (UI)")]:
        vals = [pol[n][key] * scale for n in names]
        bars = ax.barh(labels, vals, color=[blue, teal, "#63a9c9", "#8393a8"], height=.58)
        ax.axvline(threshold, ls="--", color=amber, lw=1)
        ax.set_xlabel(label)
        ax.invert_yaxis()
        ax.set_xlim(0, max(vals)*1.23)
        ax.bar_label(bars, labels=[f"{v:.3f}" for v in vals], padding=4, fontsize=9)
        ax.grid(axis="x", alpha=.15)
    save(fig, "dfe")

    fig, ax = plt.subplots(figsize=(8, 3.1), layout="constrained")
    for loss in sorted(x["loss_db"] for x in b[0]["links"]):
        vals = [x["policies"]["ideal"]["eye_h_v"]*1000 for r in b for x in r["links"] if x["loss_db"] == loss]
        ax.plot([loss, loss], [min(vals), max(vals)], color=blue, lw=3)
        ax.scatter([loss, loss], [min(vals), max(vals)], color=blue, s=22)
    ax.axhline(100, ls="--", lw=1, color=amber)
    ax.set_xlabel("Constructed channel insertion loss at 2.5 GHz (dB)")
    ax.set_ylabel("Ideal-DFE eye height (mV)")
    ax.set_xticks([3, 4.5, 6, 7.5, 9, 10.5, 12])
    ax.text(3, 106, "100 mV requirement", color=amber, fontsize=8)
    ax.grid(axis="y", alpha=.15)
    save(fig, "channel_eyes")

    fig, axes = plt.subplots(1, 2, figsize=(8.5, 3.3), layout="constrained")
    seeds = final["controls"]["entry89_shielded"]
    axes[0].bar(range(5), [s["quality_delta"] for s in seeds], color=blue, width=.56)
    axes[0].axhline(0, color="#a8b5c3", lw=.8)
    axes[0].set_xticks(range(5), [str(s["seed"])[-2:] for s in seeds])
    axes[0].set_xlabel("Training seed suffix (20260905xx)")
    axes[0].set_ylabel("Quality gain over fixed start")
    axes[0].set_ylim(0, .20)
    x = np.arange(3)
    raw = final["controls"]["entry89_unshielded"]
    vals = [final["fixed"]["compliance_rate"], np.mean([s["compliance_rate"] for s in raw]), final["aggregate"]["mean_compliance_rate"]]
    bars = axes[1].bar(x, [100*v for v in vals], color=["#8393a8", amber, teal], width=.56)
    axes[1].bar_label(bars, labels=[f"{v:.2%}" for v in vals], padding=4, fontsize=9)
    axes[1].set_xticks(x, ["Fixed\nstart", "Policy\nalone", "Policy +\nshield"])
    axes[1].set_ylabel("Model compliance (%)")
    axes[1].set_ylim(0, 100)
    for ax in axes:
        ax.grid(axis="y", alpha=.15)
    save(fig, "rl")

    area = read_json(A101 / "area_inventory.json")
    fig, ax = plt.subplots(figsize=(8, 2.5), layout="constrained")
    vals = [area["passive_body_plate_mm2"], area["mos_gate_area_mm2"]]
    ax.barh([0], [vals[0]], color=blue, label="Passive bodies / plates", height=.5)
    ax.barh([0], [vals[1]], left=vals[0], color=teal, label="MOS gate rectangles", height=.5)
    ax.set_yticks([0], ["Known geometry\nsubtotal only"])
    ax.set_xlabel("Area (mm2); this is NOT the full laid-out area")
    ax.set_xlim(0, .0033)
    ax.legend(loc="upper center", bbox_to_anchor=(.5, 1.4), ncol=2, frameon=False)
    ax.text(sum(vals)+.00004, 0, f"{sum(vals):.6f}", va="center", fontsize=9)
    ax.grid(axis="x", alpha=.15)
    save(fig, "area")

    draw_schematic((A101 / "design.cir").read_text(encoding="utf-8"), SCRATCH / "schematic.png",
                   title="Setting 490 | source-degenerated CTLE core",
                   subtitle="Audited candidate, not deployed; real input attenuator is outside this core view")


class Report:
    def __init__(self, path):
        from reportlab.pdfgen.canvas import Canvas
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.lib.styles import ParagraphStyle
        fonts = Path("C:/Windows/Fonts")
        for name, file in [("Body", "segoeui.ttf"), ("Strong", "segoeuib.ttf"), ("Light", "segoeuil.ttf")]:
            pdfmetrics.registerFont(TTFont(name, str(fonts / file)))
        pdfmetrics.registerFontFamily("Body", normal="Body", bold="Strong", italic="Body", boldItalic="Strong")
        self.c = Canvas(str(path), pagesize=A4, pageCompression=1)
        self.c.setTitle("Nebula | RL-assisted equalizer design - Competition Technical Report")
        self.c.setAuthor("Nebula Project Team")
        self.c.setSubject("5 Gbps NRZ SKY130 CTLE: product, reinforcement learning, verification and hardware scope")
        self.w, self.h = A4
        self.left, self.width, self.y, self.n = 46, A4[0]-92, 0, 0
        self.style = ParagraphStyle("body", fontName="Body", fontSize=10.1, leading=15.2,
                                    textColor="#293b50", spaceAfter=0)
        self.pages = []

    def text(self, text, x, y, size=10, font="Body", color="#16263c"):
        self.c.setFillColor(color)
        self.c.setFont(font, size)
        self.c.drawString(x, self.h-y, text)

    def para(self, text, size=None, color=None, gap=11, x=None, width=None):
        from reportlab.platypus import Paragraph
        from reportlab.lib.styles import ParagraphStyle
        style = ParagraphStyle("p", parent=self.style, fontSize=size or self.style.fontSize,
                               leading=(size or self.style.fontSize)*1.5, textColor=color or "#293b50")
        p = Paragraph(text, style)
        w, h = p.wrap(width or self.width, 700)
        self.check(h)
        p.drawOn(self.c, x or self.left, self.h-self.y-h)
        self.y += h + gap

    def check(self, height):
        if self.y + height > self.h-58:
            raise ValueError(f"Page {self.n} overflow at {self.y:.1f} + {height:.1f}")

    def new(self, tag, title, subtitle=None):
        if self.n:
            self.finish_page()
        self.n += 1
        self.pages.append(title)
        self.c.bookmarkPage(f"p{self.n}")
        self.c.addOutlineEntry(title, f"p{self.n}", 0)
        self.c.setFillColor("#f5f8fb")
        self.c.rect(0, self.h-35, self.w, 35, fill=1, stroke=0)
        self.text("NEBULA / COMPETITION TECHNICAL REPORT", 46, 22, 8, "Strong", "#526479")
        self.text(tag.upper(), 46, 66, 9, "Strong", "#008575")
        self.text(title, 46, 99, 25, "Light")
        self.y = 116
        if subtitle:
            self.para(subtitle, size=10.5, color="#617287", gap=18)

    def finish_page(self):
        self.c.setStrokeColor("#d9e3ec")
        self.c.setLineWidth(.5)
        self.c.line(46, 41, self.w-46, 41)
        self.text("6 SEPTEMBER 2026  |  EVIDENCE SNAPSHOT 2b184f7", 46, self.h-26, 7.3, color="#617287")
        self.text(f"{self.n:02d}", self.w-61, self.h-26, 9, "Strong", "#1764b0")
        self.c.showPage()

    def heading(self, text):
        self.check(32)
        self.text(text, self.left, self.y+13, 13, "Strong")
        self.y += 25

    def box(self, title, text, tone="blue"):
        from reportlab.platypus import Paragraph
        bg = "#edf5fb" if tone == "blue" else "#fff4e9"
        accent = "#1764b0" if tone == "blue" else "#bd6627"
        p = Paragraph(text, self.style)
        _, ht = p.wrap(self.width-28, 600)
        height = ht+48
        self.check(height)
        self.c.setFillColor(bg)
        self.c.roundRect(self.left, self.h-self.y-height, self.width, height, 7, fill=1, stroke=0)
        self.text(title, self.left+14, self.y+21, 11, "Strong", accent)
        p.drawOn(self.c, self.left+14, self.h-self.y-ht-32)
        self.y += height+16

    def table(self, headers, rows, widths=None, size=9):
        from reportlab.platypus import Table, TableStyle, Paragraph
        from reportlab.lib.styles import ParagraphStyle
        st = ParagraphStyle("cell", parent=self.style, fontSize=size, leading=size*1.42)
        sh = ParagraphStyle("head", parent=st, fontName="Strong", textColor="white")
        cells = [[Paragraph(escape(str(t)), sh) for t in headers]]
        cells += [[Paragraph(str(t), st) for t in row] for row in rows]
        widths = widths or [self.width/len(headers)]*len(headers)
        tab = Table(cells, colWidths=widths, hAlign="LEFT")
        tab.setStyle(TableStyle([("BACKGROUND", (0,0),(-1,0),"#162d49"),
                                ("ROWBACKGROUNDS",(0,1),(-1,-1),["#f0f5f9","#ffffff"]),
                                ("VALIGN",(0,0),(-1,-1),"TOP"),
                                ("LEFTPADDING",(0,0),(-1,-1),8), ("RIGHTPADDING",(0,0),(-1,-1),8),
                                ("TOPPADDING",(0,0),(-1,-1),8), ("BOTTOMPADDING",(0,0),(-1,-1),8),
                                ("LINEBELOW",(0,-1),(-1,-1),.5,"#d9e3ec")]))
        _, ht = tab.wrap(self.width, 700)
        self.check(ht)
        tab.drawOn(self.c, self.left, self.h-self.y-ht)
        self.y += ht+16

    def figure(self, name, caption, max_h=290):
        from PIL import Image
        path = SCRATCH / f"{name}.png"
        with Image.open(path) as im:
            iw, ih = im.size
        w, h = self.width, self.width*ih/iw
        if h > max_h:
            w, h = w*max_h/h, max_h
        self.check(h)
        self.c.drawImage(str(path), self.left+(self.width-w)/2, self.h-self.y-h, w, h, mask="auto")
        self.y += h+9
        self.para(caption, size=8.6, color="#617287", gap=17)

    def stages(self, stages):
        for i, (title, desc) in enumerate(stages, 1):
            self.check(65)
            self.c.setFillColor("#e9f3f7")
            self.c.roundRect(self.left, self.h-self.y-47, 32, 32, 8, fill=1, stroke=0)
            self.text(f"{i:02d}", self.left+7, self.y+36, 11, "Strong", "#008575")
            self.text(title, self.left+46, self.y+19, 12, "Strong")
            self.y += 26
            self.para(desc, size=9.6, x=self.left+46, width=self.width-46, gap=15)

    def save(self):
        self.finish_page()
        self.c.save()


def build_legacy_snapshot():
    OUT.mkdir(parents=True, exist_ok=True)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    a, b, req, final, prod, summary = evidence()
    figures(a, b, req, final)
    pdf = OUT / "Nebula_Competition_Report.pdf"
    r = Report(pdf)
    area = read_json(A101 / "area_inventory.json")
    pol = summary["fixed"]["dfe_policies"]
    worst_noise = max(x["meas"]["inoise_vrms"] for x in b)*1000
    worst_power = max(x["meas"]["power_w"] for x in b)*1000
    worst_hd3 = max(x["hd3_100mhz_dbc"] for x in b)
    fmin, fmax = min(2.5*2**x["meas"]["f_peak_oct"] for x in b), max(2.5*2**x["meas"]["f_peak_oct"] for x in b)

    r.new("AI / ML FOR ANALOG CIRCUIT DESIGN", "NEBULA")
    r.y = 143
    r.para("From target specifications<br/>to a traceable equalizer circuit", size=29, gap=23)
    r.para("RL-assisted design automation for a 5 Gbps NRZ, SKY130 source-degenerated CTLE with behavioural 1-tap DFE", size=15, color="#526479", gap=30)
    r.c.setStrokeColor("#008575")
    r.c.setLineWidth(3)
    r.c.line(46, r.h-r.y, 119, r.h-r.y)
    r.y += 32
    r.table(["DESIGN FLOW", "PHYSICAL MODEL", "FRESH FIXED AUDIT"], [["Spec-conditioned PPO<br/>+ deterministic verifier", "130 nm open PDK<br/>+ ngspice", "45/45 PVT corners<br/>315/315 model conditions"]], size=10)
    r.y += 12
    r.para("Competition Technical Report", size=18, gap=9)
    r.para("Nebula Project Team<br/>Evidence frozen at repository snapshot 2b184f7<br/>6 September 2026", size=10.5, gap=24)
    r.box("Scope at a glance", "A working software demonstrator and SPICE-verified CTLE candidate. The eye uses a behavioural DFE; physical Rs/Cs switching, full receiver power and laid-out area remain unverified. The validated fixed candidate is not yet integrated into the current product export.")
    r.para("Prepared afresh from source code, raw audit journals and frozen experiment results. No prior project report is used as the report narrative.", size=8.7, color="#617287")

    r.new("01 / EXECUTIVE SUMMARY", "What the solution delivers")
    r.para("Nebula addresses the competition brief by turning a requested peaking boost and peak frequency into a checked equalizer design package. It combines a learned search policy, a library of real SKY130 circuit simulations, a deterministic specification verifier, and a Python-to-ngspice export path. A local dashboard makes the same flow accessible without editing netlists. [E1-E4]")
    r.para("The current successful RL formulation is deliberately bounded: masked PPO searches an 8 x 8 x 8 library of attenuator, Rs and Cs settings around an engineered transistor core. It is not unconstrained transistor-topology synthesis. Offline circuit characterisation is reused at request time; a final schematic is drawn from the exported deck, keeping the displayed design tied to its source. [E4-E6]")
    r.table(["Evidence layer", "Result", "Interpretation"], [
        ["Frozen RL experiment", "5 seeds; 2,430 held-out conditions; +0.1550 normalised eye-quality gain", "Policy plus shield improves on its fixed starting settings; not global optimality."],
        ["Current product", "9 dB / 1.9 GHz example: 315/315 adaptive conditions", "Codes can differ between conditions. Its single exported setting 425 passes 43/45 fixed PVT corners."],
        ["New fixed candidate", "Setting 490: 45/45 PVT and 315/315 model conditions", "Freshly re-simulated without retuning. Classical bank selection; not yet deployed."],
        ["Hardware completeness", "CTLE real; DFE behavioural; full area unknown", "A verified model result, not a complete silicon receiver sign-off."]
    ], [111, 181, r.width-292], size=9)
    r.heading("Main contribution")
    r.para("The useful contribution is the evidence chain: user intent, bounded learned search, real circuit models, link-level eye checks, refusal when a request is unsupported, and reproducible output artifacts. The report distinguishes what the learner contributes from what the library and verifier contribute.")
    r.para("Reading guide: requirements (p.3); architecture and circuit (pp.4-5); RL and cost (pp.6-8); request and fixed-circuit results (pp.9-12); area and implementation (p.13); product experience (p.14); remaining closure work (p.15); evidence index (p.16).", size=9.1, color="#617287")

    r.new("02 / COMPETITION ALIGNMENT", "Requirement-by-requirement verdict", "The image supplied with the brief is the requirement source. Passing a model row does not close missing hardware.")
    r.table(["Requirement", "Implementation / evidence", "Verdict"], [
        ["S1: 5 Gbps NRZ; 2.5 GHz Nyquist", "NRZ link configuration, 200 ps UI; not the original 112G PAM-4 configuration.", "Implemented"],
        ["S2: one-stage source-degenerated CTLE + 1-tap DFE", "SKY130 transistor CTLE, real passive geometries, behavioural 1-tap cancellation. Rs/Cs selector not realised.", "Partial hardware"],
        ["S3: 3-12 dB peaking; 1.25-2.5 GHz peak", "Spec-conditioned requests; 8/12 audited requests pass all adaptive conditions. Both peak-to-DC and Nyquist-to-DC boost reported.", "Partial coverage"],
        ["S4: HD3 below -30 dB at 100 MHz", f"Fixed 490 worst {worst_hd3:.2f} dBc, 0.1 V differential peak drive. Input amplitude is a disclosed test choice.", "SPICE pass"],
        ["S5: noise below 1.5 mVrms, 10 MHz-5 GHz", f"Fixed 490 worst {worst_noise:.3f} mVrms, differentially input-referred.", "SPICE pass"],
        ["S6: power below 15 mW", f"Fixed 490 worst {worst_power:.3f} mW for the simulated CTLE supply. DFE/clock/control missing.", "CTLE-only pass"],
        ["S7: area below 0.05 mm2", f"Known geometry subtotal {area['geometry_subtotal_mm2']:.6f} mm2; no placed-and-routed receiver area.", "Not verified"],
        ["S8: eye above 100 mV and 0.4 UI", "Fixed 490 minima 132.442 mV and 0.765625 UI with ideal DFE; constructed channels and behavioural eyes.", "Model pass"],
        ["S9: five process corners, VDD +/-5%, 0-125 C", "45 sampled PVT points; fixed 490 passes all, across seven channel views. No continuous-temperature or mismatch proof.", "Sampled model pass"]
    ], [139, 276, r.width-415], size=8.6)
    r.para("Deliverables: Python framework, ngspice integration, exact SPICE deck, core schematic and resulting specifications are implemented. The natural-language wrapper is optional assistance, not an alternative authority for measurements. [E1-E4]", size=9.3)

    r.new("03 / SYSTEM ARCHITECTURE", "A checked path from intent to circuit")
    r.stages([
        ("1. User supplies the response target", "Peaking in dB and peak frequency in GHz. Guarded text input maps to the same numeric fields. The fixed competition limits remain constraints."),
        ("2. Policy proposes local library moves", "The frozen masked-PPO policy sees the request, present code and measured eye history. It visits at most eight settings per test condition."),
        ("3. The design-time verifier checks feasibility", "Real precharacterised ngspice results and link metrics enforce the model constraints. The current selector prioritises target accuracy among safe candidates."),
        ("4. Stored-bank refinement or explicit refusal", "If policy visits are unsafe or poorly centred, inspect existing measurements. No eligible circuit means an unsupported result, not a fabricated success."),
        ("5. Export the selected nominal circuit", "Emit a real SKY130 deck, run its export check, parse that same deck into a schematic, and save JSON plus verification and provenance."),
        ("6. Inspect and share the evidence", "Dashboard, corner explorer, generated-circuit comparison and evidence ZIP expose the result. A separate fixed-code audit tests whether one exported circuit survives PVT.")
    ])
    r.box("Channel loss is not the requested CTLE gain", "The seven 3-12 dB channel losses are evaluation conditions for the link model, not circuit knobs or the user's requested peaking. An uploaded channel is profiled separately and is not automatically covered by the frozen RL bank.", "amber")
    r.para("Figure 1. Implemented product flow, reconstructed from the numeric front door, hybrid selector, exporter and web worker. The shield is a simulator-backed design-time tool, not an on-chip receiver monitor. [E4, E8]", size=8.6, color="#617287")

    r.new("04 / CIRCUIT", "The equalizer behind the software", "Fixed candidate 490: A7, Rs index 5, Cs index 2. Component annotations are parsed from its audited netlist.")
    r.figure("schematic", "Figure 2. Regenerated CTLE-core schematic from the actual setting-490 deck. Input attenuation is implemented upstream but omitted from this core drawing; it comprises a series resistor and three PMOS-switched shunt branches per differential leg. DFE is a behavioural downstream block, not transistors. [E3, E5]", max_h=276)
    r.table(["Circuit quantity", "Setting 490 value", "Physical interpretation"], [
        ["Input pair W / L / nf", "57.977 um / 0.39115 um / 4", "W is total device width, not width per finger."],
        ["Rs / Cs", "356.818 ohm / 2.85155 pF", "Parallel source-to-source degeneration; drawn SKY130 poly / MIM."],
        ["RL / external CL per side", "254.633 ohm / 32.628 fF", "Real poly load; CL is an assumed external capacitive load."],
        ["VDD / input common mode", "1.8 V / 1.50102 V nominal", "Ideal bias/reference infrastructure remains a scope limitation."]
    ], [142, 172, r.width-314], size=8.8)
    r.para("Design intuition: k = 1 + (gm + gmbs)Rs/2, fz = 1/(2 pi Rs Cs), fp1 approximately k fz, and low-frequency core gain approximately gm RL/k. Rs denotes the full source-to-source resistance. Body transconductance is included because the NMOS bodies are grounded. These are sanity-check equations; final numbers come from SPICE, including the attenuator and parasitics. [E5]")

    r.new("05 / REINFORCEMENT LEARNING", "What the agent learns and earns")
    r.para("The successful method uses an oracle-imitation warm start followed by masked categorical PPO. Its reward is normalised feasible eye-area improvement, not simply bigger peaking or an unconstrained larger eye. The reference ceiling is the best compliant eye area in the stored library for the same condition. [E6, E7; R1]")
    r.box("Implemented training objective", "Let A = eye height x eye width and A* be the compliant library maximum.<br/><b>q = clip(A / A*, 0, 1)</b> if the setting is compliant; otherwise q = 0.<br/><b>Move reward: r = q(new) - q(old).</b><br/>At LOCK: add 0 for a compliant setting, otherwise -1 - q(current).<br/>The undiscounted compliant return telescopes to q(final) - q(start); PPO trains with discount 0.99.")
    r.table(["Part", "Actual implementation"], [
        ["Observation: 62 numbers", "Target peaking and log frequency; trial fraction; three codes; eight history slots containing code and measured eye information."],
        ["Hidden from the actor", "PVT, channel loss, compliance verdict, normalised quality and the hidden library optimum. Training and the external verifier can use that information."],
        ["Actions: 7", "Attenuator +/-1, Rs +/-1, Cs +/-1, and LOCK. Boundaries are masked; LOCK starts after two measurements; maximum eight measurements."],
        ["Network and training", "64 x 64 hidden layers; 50 imitation epochs then 200,000 PPO steps per seed; five seeds; learning rate 0.0003; PPO clip 0.2."],
        ["Inference", "Frozen CPU policy, no online training or hidden reward query by the actor. The verifier remains essential to output safety."]
    ], [131, r.width-131], size=9)
    r.heading("A separate production ranking")
    r.para("The current product retains that policy but ranks safe outputs by the largest normalised peaking/frequency error, then total error, then eye area. It checks the bank when visited settings miss the central 0.5 dB / 0.1-octave region. This later target-centred selector is not the selector evaluated in the earlier held-out RL experiment. [E4]")

    r.new("06 / RL EVIDENCE", "Learned search helps; the shield matters", "Frozen experiment Entry 89: five trained seeds, one held-out evaluation, no retraining on the final set.")
    r.figure("rl", "Figure 3. All five seeds improve quality over the fixed start. Policy-only versus shielded output reveals the verifier's contribution. Each seed sees the same 2,430 held-out identities. [E1]", max_h=187)
    r.table(["Held-out metric", "Recorded result"], [
        ["Mean normalised quality: fixed start to policy + shield", "0.5619 to 0.7169; absolute gain +0.1550"],
        ["Paired 95% bootstrap interval for quality gain", "+0.1508 to +0.1593 (10,000 resamples)"],
        ["Mean compliance: fixed start to policy + shield", "82.263% to 83.885%; policy alone 64.444%"],
        ["Mean measured visits / verifier calls", "5.579 per identity (fixed start included); maximum eight"],
        ["Safety limitation across five seeds", "1,958/12,150 seed-condition outputs remained noncompliant; failures were not converted into passes."]
    ], [r.width*.61, r.width*.39], size=9)
    r.para("Policies were frozen at a84082e before fresh midpoint evidence at 51a1146. The final set combines six midpoint channel losses, nine midpoint requests and 45 corners, with zero identity overlap against development. It reuses the same transistor geometries and PVT lattice; it does not establish generalisation to a new topology, load, PDK or measured channel. [E1]")
    r.box("Attribution and version boundary", "This tests warm-started PPO plus a visited-setting shield against a fixed start, not exhaustive transistor-space search. It does not isolate PPO from imitation. The current full-bank fallback and target-centred selector require separate validation.", "amber")

    r.new("07 / COMPUTATIONAL COST", "Fast reuse, with the offline bill visible")
    r.para("The design-space reduction is structural: earlier circuit engineering fixes a useful transistor core, while the deployed policy adapts three discrete dimensions. The resulting 512 settings are not 512 seeds or 512 new simulations for every user request. [E4, E6]")
    r.table(["Stage", "Recorded work", "What it buys"], [
        ["Offline circuit library", "8 attenuator x 8 Rs x 8 Cs x 45 PVT = 23,040 SPICE rows", "A reusable measured circuit bank; this simulation cost is not free."],
        ["Offline channel views", "23,040 rows x 7 channels = 161,280 link points", "Repeated link calculations over seven constructed losses."],
        ["Training", "5 x (50 imitation epochs + 200,000 PPO steps)", "Frozen policies; table-backed training does not invoke new SPICE."],
        ["Frozen final evaluation", "Fresh midpoint journal: 23,040 circuit rows; 2,430 evaluation identities", "A separate evidence acquisition and scoring phase; not ordinary request latency."],
        ["Current 9 dB / 1.9 GHz request", "2,406 policy visits; 119,808 bank-row checks; 0 selection SPICE calls", "Adaptive selection and refinement across 315 conditions."],
        ["Nominal export", "1 ngspice export call; recorded export stage 0.225 s", "Captured exact circuit deck; not a fresh 45-corner sign-off."],
        ["Separate fixed-490 audit", "91 SPICE calls; 88.37 s total", "One export plus two distortion-tone evaluations at each of 45 PVT points."]
    ], [104, 226, r.width-330], size=9)
    r.heading("What can be claimed about speed")
    r.para("The recorded product solve stage took 5.894 s for the 9 dB / 1.9 GHz example, before its separately recorded export stage. Reusing an existing bank eliminates new circuit simulations during selection. These are single-machine observations, not a latency service guarantee. [E4]")
    r.para("The amortised cost is C_offline/N + C_request for N requests. Bank construction, training, validation and future library expansion must remain in C_offline. We do not claim a measured total-work speed-up over sweeping all MOS/R/C/L variables, nor a global near-optimal circuit. The quality ceiling on p.6 is only the available library optimum.")

    r.new("08 / USER REQUEST COVERAGE", "Where the product succeeds and refuses")
    r.figure("coverage", "Figure 4. Current target-centred selector audited on 12 requests. Each cell counts compliant adaptive outputs across 45 PVT points x 7 constructed channels. A cell below 315 means the complete requested family is unsupported, even if some conditions work. [E2]", max_h=292)
    r.para("Eight of twelve sampled requests are fully supported. The high-frequency and high-peaking edge remains the main coverage gap: 9 dB / 2.5 GHz supports 273 conditions; 12 dB requests support 308, 312 and 112 conditions at 1.25, 1.9 and 2.5 GHz respectively. This is a measured twelve-point audit, not proof of continuous coverage between cells.")
    r.heading("Accuracy is different from feasibility")
    r.para("The internal request-match windows are +/-1.5 dB and +/-0.3 octave in peak frequency, in addition to the absolute peaking/frequency limits. These tolerances are the project's implementation choice; the competition image does not specify them. Their adequacy needs organiser acceptance. A passing setting need not hit the exact requested point. [E2, E6]")
    r.box("Example: request 9 dB at 1.9 GHz", "The current nominal export is 8.632696 dB at 1.896053 GHz. It is close to the request, but its adaptive 315/315 result allows different codes by condition. That headline cannot establish fixed-circuit robustness. [E4]", "amber")

    r.new("09 / FIXED-CIRCUIT ROBUSTNESS", "One circuit must survive the corners")
    r.figure("pvt", "Figure 5. Fresh fixed-code audits of settings 425 and 490. No code or geometry changes within each audit. Within each process group: supply 0.95, 1.00, 1.05; temperatures in journal-label order 0, 125, 27 C. Dashed lines are lower request-match edges, not extra competition specifications. [E2, E3]", max_h=326)
    r.para("Setting 425, the current nominal export, passes 43/45 PVT points (301/315 model conditions). At SS and FS, 0.95 supply and 125 C, peaking is about 7.445 and 7.446 dB: approximately 0.055 dB below the 7.5 dB acceptance edge. The correct fixed-circuit verdict is therefore a fail for this request.")
    r.para("Setting 490 was selected classically from the stored all-condition feasible intersection, frozen, then freshly simulated with the same fixed-audit instrument. It passes 45/45 corners and 315/315 model conditions. Nominal peaking is 8.852970 dB at 1.771915 GHz. The current product was not silently switched to this candidate.")
    r.box("Robust within a finite test grid, not unlimited margin", "Setting 490 has only 0.138321 dB minimum peaking-match slack and 0.011880 octave minimum frequency-match slack. PVT sampling does not cover mismatch, extracted layout parasitics, a different load or every temperature between samples.", "amber")

    r.new("10 / ELECTRICAL VERIFICATION", "Measured margins for setting 490")
    r.figure("electrical", "Figure 6. All 45 fixed-candidate PVT results: nine supply/temperature samples for each process. Dashed lines mark the brief's limits. Power is CTLE supply power, not the complete receiver. [E3]", max_h=216)
    r.table(["Metric", "Worst / range over 45 PVT", "Measurement boundary"], [
        ["Peaking", "7.6383 to 9.5354 dB", "Peak-to-DC ratio; not absolute voltage gain."],
        ["Peak frequency", f"{fmin:.4f} to {fmax:.4f} GHz", "Interpolated AC peak, guarded against edge maxima."],
        ["Nyquist-to-DC boost", "7.4516 to 9.4449 dB", "Reported separately to avoid a misleading out-of-band peak."],
        ["HD3 at 100 MHz", f"Worst {worst_hd3:.2f} dBc", "Differential 0.1 V peak sine; not a full receiver transient distortion measurement."],
        ["Input-referred noise", f"Worst {worst_noise:.3f} mVrms", "10 MHz-5 GHz; ngspice integrated RMS, not square-rooted twice."],
        ["Supply power", f"Worst {worst_power:.3f} mW", "Measured VDD branch; includes simulated mirror reference branch; excludes missing receiver blocks."]
    ], [119, 159, r.width-278], size=8.8)
    r.heading("Measurement integrity")
    r.para("The runner checks required measurements and known failure warnings rather than trusting ngspice's exit code. Fixed audits compare circuit signatures across corners and across both distortion-tone runs. AC, noise and operating-point data must be valid before link scoring. A failed or absent measurement cannot become a successful row. [E3, E5]")
    r.para("Both mandated 100 MHz HD3 and the additional Nyquist-tone distortion check pass for this candidate. The latter is an extra operating-point check, not a replacement for the brief's 100 MHz requirement.", size=9.3)

    r.new("11 / LINK AND DFE", "An open eye, with assumptions exposed")
    r.figure("dfe", "Figure 7. Worst height and worst width across 315 conditions for fixed 490, under four DFE assumptions. Height and width minima may occur at different conditions. All four cases pass the model thresholds. [E3, E7]", max_h=213)
    r.figure("channel_eyes", "Figure 8. Min-to-max ideal-DFE eye-height envelope across the 45 PVT samples at each constructed channel loss. This is a measured-model envelope, not a fabricated oscilloscope eye image. [E3]", max_h=189)
    r.para("The link bridge applies the fitted transistor response to an NRZ channel/pulse model. Eye height is a worst-ISI cursor opening in volts; width is the contiguous positive-opening phase interval on a 64-sample/UI grid. The model assumes 0.8 V differential peak-to-peak TX swing, -3.5 dB TX de-emphasis and balanced skin/dielectric channel loss; these are not supplied by the competition image. The eyes are not BER-qualified contours and exclude a transistor DFE, clock jitter and decision-error propagation. [E7]", size=9.5)
    r.para("Ideal DFE removes the first postcursor exactly. Misadaptation leaves 20% of it. The quantisation diagnostic uses step 1/16 clipped to +/-0.5, including both endpoints (17 representable values); it is not a realised 16-code DAC. Even the no-DFE case passes, at minima 131.283 mV and 0.65625 UI. This reduces dependence on ideal cancellation for these channels, but does not waive the required physical 1-tap DFE. [E3, E7]", size=9.3)

    r.new("12 / HARDWARE COMPLETENESS", "Area is an inventory, not a sign-off")
    r.figure("area", "Figure 9. Fixed-490 geometry subtotal reconstructed from netlist instances. No arbitrary layout multiplier is applied. The 0.05 mm2 limit cannot be declared met until the missing geometry is accounted for. [E3, E9]", max_h=168)
    r.table(["Area component", "Known subtotal (mm2)", "Scope"], [
        ["Legacy Rs + Cs + two RL bodies", "0.002005164", "Old optimisation proxy; omits attenuator and MOS geometry."],
        ["All netlisted passive bodies / plates", "0.002503753", "Includes attenuator branches, whether electrically on or off."],
        ["All MOS gate rectangles", "0.000343615", "W x L x parallel multiplier; nf splits total width."],
        ["Known geometry sum", "0.002847367", "A partial physical inventory, not a laid-out cell area."],
        ["Complete receiver area", "Unknown", "Stored as null; S7 status is NOT_VERIFIED."]
    ], [152, 127, r.width-279], size=8.6)
    r.para("Missing area includes the physical 10 pF bias bypass capacitor, reference/bias and common-mode generation, DFE/slicer/clock, Rs/Cs selectors and digital control, contacts, diffusion, wells, guard rings, spacing, routing and floorplan. The two 32.628 fF loads are treated as external; an integrated receiver must account for their realisation. [E9]")
    r.heading("Which switches are real?")
    r.para("The three-bit PMOS input attenuator is netlisted and measured, including OFF branches. In contrast, the 64 Rs/Cs combinations are separate passive geometries, not a physical switched matrix. Registered NMOS selector experiments found an ON-resistance versus OFF-capacitance conflict; later split-capacitor and low-threshold probes did not close both limits. None was inserted into the production CTLE. [E4, E10]")
    r.para("Consequently, present area optimisation only constrains a partial passive proxy. The small subtotal is not evidence of abundant final chip-area margin. Physical switching and DFE implementation are required closure work unless the organisers explicitly accept a behavioural/design-time interpretation.", size=9.3)

    r.new("13 / THE PRODUCT", "Engineering evidence made usable", "A local browser workspace wraps the same checked Python design path; it does not replace it with a mock simulator.")
    r.table(["User-facing capability", "What it does", "Safety / scope boundary"], [
        ["Numeric and natural-language requests", "Turns requested peaking and frequency into the same validated design call.", "Guarded parser; optional LLM does not invent circuit performance."],
        ["Interactive PVT explorer", "Lets the user inspect individual conditions and their margins.", "Adaptive map is separate from fixed-export audit status."],
        ["Generated-circuit comparison", "Compares saved candidate outputs and resulting specifications.", "Circuit comparison, not an algorithm leaderboard in the workspace."],
        ["Channel upload", "Reads Touchstone channel data, checks format and port mapping, and emits a profile.", "Labelled PROFILED_NOT_RL_VERIFIED; the frozen bank was not generated for that channel."],
        ["Failure-aware results", "Shows unsupported requests, missing evidence and reasons for rejection.", "No eligible candidate means refusal, not adjusted targets or invented numbers."],
        ["Evidence bundle", "Packages JSON, exact circuit deck, schematic, verification, scope and audit artifacts.", "Keeps measured numbers and implementation limitations together."],
        ["Judge mode", "Loads a known saved example for an immediate demonstration.", "Explicitly cached; not represented as a new optimisation run."]
    ], [123, 193, r.width-316], size=9)
    r.heading("A representative demonstration")
    r.para("Enter '9 dB peaking at 1.9 GHz', run the design job, inspect the nominal response and condition map, then open the core schematic and download the evidence. The recorded example reports 315/315 adaptive conditions. Its readiness panel must still disclose setting 425's fixed 43/45 result and the missing hardware boundaries. [E4, E8]")
    r.box("Responsiveness by separating work", "The local server uses a background design worker and saved artifacts for inspection. Plots and report views can reuse results without retraining the policy or rerunning SPICE. An unsupported uploaded channel is not allowed to trigger an undisclosed claim of verified RL operation.")
    r.para("Local launch from the repository root: <b>py -3.13 -m nebula.web --no-browser</b>, then open <b>http://127.0.0.1:8765/</b>. Use the configured Python environment with PyTorch; fresh exports also require the local ngspice/PDK setup. This page documents implemented features, not a fabricated live screenshot. [E8]", size=8.7, color="#617287")

    r.new("14 / CONCLUSION AND CLOSURE", "A credible demonstrator; clear next gates")
    r.para("Nebula demonstrates an end-to-end open-tool design workflow with a real SKY130 CTLE, bounded learned search, a deterministic feasibility shield, link-level checking and inspectable outputs. The frozen experiment shows a repeatable eye-quality benefit for the hybrid approach. Fresh fixed-circuit validation supplies a stronger hardware evidence point than an adaptive corner map alone.")
    r.para("It does not yet prove the full competition envelope or a complete physical equalizer. The main remaining risks are programmable Rs/Cs realisation, physical DFE and bias infrastructure, total area/power, request-edge coverage and model-to-layout transfer. These are engineering gaps, not issues that can be solved by relabelling a model pass.")
    r.table(["Next gate", "Required evidence to close it"], [
        ["1. Integrate fixed-robust export", "Add explicit adaptive versus fixed export semantics; use the validated 490 candidate only with visible attribution. Recheck the production path and regression tests."],
        ["2. Agree specification interpretations", "Confirm request-match tolerances, input amplitude, channel/load assumptions, PVT sampling and whether behavioural DFE is acceptable."],
        ["3. Close physical switching and DFE", "Implement credible Rs/Cs control, 1-tap feedback/slicer timing and realistic loading; rerun circuit and link checks with their parasitics."],
        ["4. Account for full area and power", "Realise bias/control/DFE and floorplan; perform layout-rule and connectivity checks, then extraction and full receiver budgeting."],
        ["5. Validate the final deployment", "Freeze the integrated selector, test unseen requests/channels and mismatch/load sensitivity, then measure matched end-to-end cost including offline work."]
    ], [157, r.width-157], size=9)
    r.heading("Competition claim")
    r.box("Evidence-grounded design automation", "Nebula is a functioning RL-assisted circuit-design product with demonstrated library-search improvement and a freshly verified fixed CTLE candidate. It is not presented as tapeout-ready, as universally compliant across the target range, or as a proven global optimum.")
    r.para("Pre-existing work declaration: the team already had a SerDes behavioural modelling framework. Nebula's competition work adds the SKY130/ngspice device path, NRZ device-to-link integration, learned bank search, verification and product/evidence layer. The original 112G PAM-4 track is separate from this 5 Gbps NRZ demonstrator.", size=9.3)

    r.new("15 / REPRODUCIBILITY", "Evidence index and references", "Repository-relative paths below identify the source evidence. The repository and supporting reference collection remain private.")
    refs = [
        ("E1", "Frozen RL evidence", "nebula/experiments/shielded_policy_final_results.json; shielded_policy_manifest.json; shielded_train_2026090500..04.json"),
        ("E2", "Current-product audit", "nebula/product_audits/entry100_20260906/{summary.json, fixed_pvt.jsonl, request_accuracy.jsonl}"),
        ("E3", "Fixed setting 490", "nebula/product_audits/entry101_fixed490_20260906/{candidate.json, design.cir, fixed_pvt.jsonl, summary.json, provenance.json, area_inventory.json}"),
        ("E4", "Current selector and output", "nebula/rl/hybrid_designer.py; nebula/product_demo/rl_hybrid_9db_1p9ghz/design.json; nebula/design.py"),
        ("E5", "Circuit and simulator", "nebula/device/{sky130_runner.py, crosscheck.py}; nebula/common/design_equations.py; nebula/report/schematic.py"),
        ("E6", "Learning and safety", "nebula/rl/{margin_improve_env.py, margin_adapt_env.py, masked_discrete_ppo.py, safety_shield.py, reward_v1.py}; nebula/experiments/exp_shielded_ppo.py"),
        ("E7", "Link and DFE model", "nebula/link/{bridge.py, config.py, cursors.py, dfe_ablation.py}"),
        ("E8", "User product", "nebula/web/; nebula/llm/; nebula/channel_upload.py"),
        ("E9", "Area accounting", "nebula/report/product_scope.py; Entry 100 and Entry 101 area_inventory.json"),
        ("E10", "Physical-selector probes", "nebula/experiments/{tuning_switch_results.json, split_tuning_bank_results.json, lvt_tuning_bank_results.json}; nebula/device/tuning_switch.py")
    ]
    for num, title, path in refs:
        r.para(f"<b>[{num}] {title}.</b> {escape(path)}", size=8.1, gap=7)
    r.heading("External method and tool references")
    r.para('[R1] Schulman et al., <i>Proximal Policy Optimization Algorithms</i>, 2017. <link href="https://arxiv.org/abs/1707.06347" color="#1764b0">arxiv.org/abs/1707.06347</link><br/>[R2] SkyWater SKY130 PDK documentation. <link href="https://skywater-pdk.readthedocs.io/en/main/" color="#1764b0">skywater-pdk.readthedocs.io</link><br/>[R3] ngspice documentation. <link href="https://ngspice.sourceforge.io/docs.html" color="#1764b0">ngspice.sourceforge.io/docs.html</link><br/>Web references accessed 6 September 2026; the installed simulator is ngspice 41, not necessarily the latest documented release.', size=8.2, gap=9)
    r.para("Audit anchors: RL policy freeze a84082e; midpoint evidence 51a1146; fixed-candidate runner freeze 843ca0c; evidence snapshot 2b184f7. A companion SHA-256 manifest records the exact local sources used to generate this report. No new SPICE or RL experiment was run for report generation.", size=8.4)
    r.save()
    sources = [FINAL, PRODUCT, *A100.glob("*.json*"), *A101.glob("*.json*"), A101 / "design.cir",
               ROOT / "nebula/rl/hybrid_designer.py", ROOT / "nebula/rl/margin_improve_env.py",
               ROOT / "nebula/rl/margin_adapt_env.py", ROOT / "nebula/rl/safety_shield.py",
               ROOT / "nebula/link/dfe_ablation.py", ROOT / "nebula/report/product_scope.py"]
    sources += [ROOT / p for p in [
        "nebula/rl/masked_discrete_ppo.py", "nebula/rl/reward_v1.py",
        "nebula/experiments/exp_shielded_ppo.py", "nebula/experiments/exp_shielded_final.py",
        "nebula/experiments/shielded_policy_manifest.json", "nebula/design.py",
        "nebula/link/bridge.py", "nebula/link/config.py", "nebula/link/cursors.py",
        "nebula/link/channel.py", "nebula/link/tx.py", "nebula/channel_upload.py",
        "nebula/device/sky130_runner.py", "nebula/device/crosscheck.py",
        "nebula/common/design_equations.py", "nebula/report/schematic.py",
        "nebula/experiments/tuning_switch_results.json",
        "nebula/experiments/split_tuning_bank_results.json",
        "nebula/experiments/lvt_tuning_bank_results.json", "nebula/device/tuning_switch.py",
        "nebula/experiments/exp_product_readiness.py", "nebula/experiments/exp_fixed_candidate.py",
        "nebula/report/competition_2026.py"]]
    sources += list((ROOT / "nebula/experiments").glob("shielded_train_20260905*.json"))
    sources += list((ROOT / "nebula/web").glob("*.py"))
    sources += list((ROOT / "nebula/web/static").glob("*"))
    sources += list((ROOT / "nebula/llm").glob("*.py"))
    manifest = {"report": pdf.name, "evidence_snapshot": "2b184f7", "page_count": r.n,
                "sources": [{"path": p.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in sources],
                "report_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
                "notes": "Fresh narrative and figures. Setting 490 not deployed. No new circuit simulation."}
    (OUT / "Nebula_Competition_Report_sources.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    print(f"Created {pdf} ({r.n} pages)")
    return pdf


def build():
    """Build the current submission; legacy evidence helpers stay historical."""
    from nebula.report.competition_submission import build as current_build
    return current_build()


if __name__ == "__main__":
    build()
