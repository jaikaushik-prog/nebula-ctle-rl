"""Competition-facing editorial revision; preserve measured data and source files."""
from pathlib import Path
import copy,hashlib,json,re,zipfile
from docx import Document
from docx.shared import Pt

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'output/docx/Nebula_Academic_Final_Report_20260915_v4.docx'
OUT=ROOT/'output/docx/Nebula_Competition_Report_20260915_Final.docx'
EXPECTED_SOURCE='f0b59435bb6b25ab36fb41069d09109f910f7971ce476d53871ae653b35872fc'

REVISIONS={
'Nebula Reinforcement Learning Based Equalizer Design': 'Nebula Automated Equalizer Design Using Reinforcement Learning',
'Nebula turns target specifications': 'Nebula delivers a working Python design flow from target specifications to a SKY130 CTLE, generated schematic and measured results. Learned candidate search is coupled to NGSpice verification and automatic recovery: the demonstrated 6 dB / 2.1 GHz request produces setting 352 after rejecting an unsuitable candidate, without manual replacement selection. The fixed CTLE clears the recorded 315-condition gate, whose eye evaluation uses an ideal behavioral one-tap DFE. [E9,E11]',
'The generated 6 dB / 2.1 GHz receiver scores': 'The project also connects the selected CTLE to a transistor DFE and extends it with physical programmable Rs/Cs. The fixed and programmable receiver variants each decode 64/64 nominal test bits, with sampled eyes of 296.981 mV and 325.629 mV respectively. A separate calibrated reference contributes nominal analog and 45-point transistor link evidence. These demonstrations connect the software workflow to receiver hardware; Section 8 defines the remaining receiver qualification work. [E1-E2,E14,E17]',
'Deliverable coverage.': 'Deliverable coverage. The Python framework accepts numerical or natural-language targets, integrates NGSpice and SKY130, selects circuit parameters, and exports the schematic, SPICE deck and resulting specifications. The web application exposes PVT results and downloadable evidence. Sections 3-11 demonstrate these outputs and support the companion demonstration.',
'Innovation.': 'Innovation. Learned search operates on a characterized 512-setting catalogue, while fresh physical verification controls export acceptance. Automatic recovery preserves useful failed attempts, and a continuous-Cs refinement extends measured target coverage. A selected-derived receiver prototype connects physical Rs/Cs controls to transistor decision feedback. Sections 3-4,8,10 explain these contributions.',
'Thought process.': 'Thought process. Circuit decisions follow measured causes: stronger memory drive addresses held-bit errors, bleed devices discharge floating DAC nodes, and loaded calibration compensates for DFE loading. The report connects each intervention to its evidence and uses unchanged acceptance criteria to evaluate progress. Sections 6,8-10 document that engineering reasoning.',
'Accepted physical CTLE.': 'Accepted physical CTLE. One exported fixed circuit evaluated over 45 corners and seven constructed losses, with ideal behavioral DFE eye scoring. This is the primary automated-design output.',
'Generated transistor receiver.': 'Generated transistor receiver. The exact selected CTLE connected to physical decision feedback, with a separate nominal finite-pattern measurement and terminal-domain review.',
'Programmable selected receiver.': 'Programmable selected receiver. A selected-derived variant adds physical Rs/Cs controls to the transistor DFE, with separately recorded nominal response and signal results. [E17]',
'Independent 9 dB reference.': 'Independent 9 dB reference. A separately calibrated configurable receiver supplies nominal analog and 45-point transistor link-PVT evidence, identified independently from generated outputs.',
'Coverage accounting.': 'Coverage progress. A separately registered continuous-Cs pilot adds 6 dB / 2.5 GHz to the three existing grid successes, giving 4/12 demonstrated requests. The exposed 6 dB / 2.1 GHz recovery case gives 5/13 when included separately. The pilot charged 411 calls in 281.4683 s; 2,105 files were checked. The historical grid was not rerun. [E11,E13]',
'Automatic next step.': 'Integrated refinement. For exactly 6 dB / 2.5 GHz, production proposes Cs x1.02 in either selection mode and applies the unchanged fresh 137-call gate. This turns the measured extension into a repeatable product path; full-range coverage remains a development objective. [E13]',
'The catalogue reduces the online decision': 'The catalogue makes online search bounded and interpretable: the policy explores characterized choices, and transistor verification decides whether a fixed export is acceptable. Offline characterization remains part of the cost. Continuous-Cs refinement is a separately registered deterministic extension; it is not an action learned by the frozen policy.',
'Interpretation.': 'Policy contribution. The shielded policy improves measured within-bank quality over its fixed start. The oracle quantifies the remaining optimization gap: mean regret 0.2831, with 20.91% of seed/identity outcomes within 0.05 of the optimum. The evidence therefore supports learned improvement, not established near-optimality. Complete design-time results are reported separately in Section 10.',
'Series-switch studies.': 'Topology selection. Joint ON-loss and OFF-capacitance measurements showed why increasing series-switch width alone could not meet the registered network limits, motivating the controlled-resistor and varactor approach.',
'Retained electrical limit.': 'Receiver qualification. The added DFE passes its signed terminal checks and the whole-circuit voltage envelope passes. The review also identifies six attenuator PMOS devices outside signed model ranges: all six Vds intervals cross zero and two off devices have +0.299 V Vgs. This prevents full receiver verification; terminal relabeling cannot resolve it. The nominal signal result is established at the recorded test point, while analog/link PVT, noise/HD3, BER and reliability require further qualification. [E14,E16]',
'Why the design changed.': 'Measurement driven design. Held-bit failures led to stronger memory drive; floating inactive DAC tails led to physical bleeders. Loaded calibration then recovered the independent variable-Rs/Cs receiver response. Standalone control transitions settled at 850/690/650 ns, establishing eventual tuning while identifying the remaining gap to the original 500 ns target and to DFE-active retuning. [E1-E2]',
'Nominal simulation results are shown;': 'The programmable extension demonstrates a connected nominal tuning and signal result using measured deterministic calibration. All eight simulator calls remain traceable, including a rejected noise instrument. Seven signed device-domain findings and outstanding HD3/PVT checks define the next qualification work; full receiver verification remains future work. Setting 352 remains the primary fixed output, and tested grid coverage stays 4/12. [E17]',
'Scope of the result.': 'Reference contribution. The calibrated receiver provides nominal analog measurements and sampled transistor link PVT on one fixed control setting. Simultaneous all-specification PVT remains open. Signed bilateral Rs-switch Vds findings persist at all 45 points; passive voltage dependence/corners, mismatch, periodic noise, complete clock/control power and layout remain outside this evidence.',
'Bounded programmable tuning.': 'Loaded tuning study. Two bounded calls measured 31 OP/AC snapshots per held-clock state, with both baseline checks passing. Five of 12 requests match in both states within the existing 0.5 dB / 100 MHz tolerances, versus 10/12 in the standalone saved table. This identifies DFE loading as a practical tuning constraint: no 3 dB target matches the loaded sample. These nominal AC results leave end-to-end coverage at 4/12. The earlier FS / 1.71 V / 125 C analog pilot failed latch initialization and adds no analog-PVT coverage. [E10,E15]',
'Paired result.': 'Measured comparison. Both arms delivered in eight target/repetition pairs. The median classical/RL elapsed ratio is 0.939, so this sample does not establish an RL speed advantage. The complete-workflow comparison includes failed and empty-domain requests in the total cost above, making delivery and timing independently reviewable.',
'The rejected 288 candidate is not': 'Recovery decision. At SF, 0.95 VDD and 0 C on the 3 dB channel, candidate 288 exceeded the linear-model output-swing guard. Rejecting the bridge calculation prevented an invalid eye result from being accepted. The framework retained the reason and continued to setting 352, demonstrating automatic recovery from a physically motivated gate failure.',
'Nebula combines learned candidate search': 'Nebula demonstrates the requested target-to-circuit software workflow through learned candidate search, automatic physical recovery and exact schematic/netlist output. The exposed 6 dB / 2.1 GHz request is delivered without manual replacement selection. Continuous-Cs refinement raises demonstrated grid coverage from 3/12 to 4/12; the transistor DFE and programmable receiver add separately measured nominal hardware demonstrations. The web application makes each output and its scope directly inspectable.',
'Remaining work.': 'Next engineering milestones. Extend on-demand target coverage, close the signed model-domain findings, and qualify the generated receivers across analog/link PVT. DFE-active retuning, integrated clock/control drivers, noise/HD3, BER and extracted layout complete the path beyond the present demonstrations. The optional LLM wrapper is implemented but its live provider is unavailable here. The measured benchmark defines the baseline for future RL runtime improvement.',
}

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def replace(p,text):
    first=copy.deepcopy(p.runs[0]._r.rPr) if p.runs and p.runs[0]._r.rPr is not None else None
    mixed=bool(p.runs and p.runs[0].bold and any(not r.bold for r in p.runs[1:] if r.text.strip()))
    p.clear()
    if mixed and '. ' in text:
        lead,body=text.split('. ',1);runs=[p.add_run(lead+'. '),p.add_run(body)]
        for r in runs:
            if first is not None:r._r.insert(0,copy.deepcopy(first))
        runs[0].bold=True;runs[1].bold=False
    else:
        r=p.add_run(text)
        if first is not None:r._r.insert(0,first)

def build():
    assert sha(SOURCE)==EXPECTED_SOURCE,'Source changed; inspect and preserve new edits before continuing'
    d=Document(SOURCE);changes=[]
    for prefix,new in REVISIONS.items():
        matches=[p for p in d.paragraphs if p.text.startswith(prefix)]
        assert len(matches)==1,(prefix,len(matches))
        p=matches[0];changes.append(dict(before=p.text,after=new));replace(p,new)
    # Present specification coverage as an engineering status, not a self-assigned judge score.
    row=d.tables[1].rows[3]
    assert row.cells[0].text=='S3 / Failed'
    replace(row.cells[0].paragraphs[0],'S3 / Partial coverage')
    replace(row.cells[2].paragraphs[0],'4/12 combined grid targets demonstrated. Selected 352: 6.6147 dB / 2.1595 GHz. Full on-demand range not met.')
    # The judging-criteria paragraphs form a coherent opening to the contribution map.
    for prefix in ('Deliverable coverage.','Innovation.','Thought process.'):
        p=next(p for p in d.paragraphs if p.text.startswith(prefix));p.paragraph_format.keep_together=True
    d.core_properties.title=REVISIONS['Nebula Reinforcement Learning Based Equalizer Design']
    d.core_properties.comments='Competition-facing editorial revision; numerical evidence and material qualification boundaries preserved.'
    d.save(OUT);assert sha(SOURCE)==EXPECTED_SOURCE
    words=len(' '.join([p.text for p in d.paragraphs]+[c.text for t in d.tables for r in t.rows for c in r.cells]).split())
    record=dict(path=str(OUT),sha256=sha(OUT),source=str(SOURCE),source_sha256=EXPECTED_SOURCE,word_count=words,figures=len(d.inline_shapes),paragraph_changes=changes,table_changes=['S3 status: Partial coverage; explicit full-range shortfall retained'],scientific_results_changed=False,identity_fields_preserved=True)
    (ROOT/'output/docx/Nebula_Competition_Report_20260915_Final_sources.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in record.items() if k!='paragraph_changes'},indent=2))

if __name__=='__main__':build()
