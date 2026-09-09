"""Academic-format Nebula competition report derived from saved evidence.

This is a separate candidate report. It does not overwrite the current 20-page
competition report and does not start SPICE, training, or product mutation.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from nebula.report.competition_submission import (
    DEMO,
    FINAL,
    INSTITUTION,
    OUT,
    PHYS,
    POST_DIRS,
    PROJECT_NAME,
    ROOT,
    SIGNATURE,
    TEAM_MEMBERS,
    WIN_BENCH,
    WIN_RECOVERY,
    WIN_REGISTRY,
    SubmissionReport,
    load_evidence,
    make_figures,
    metrics,
)


class AcademicReport(SubmissionReport):
    """Formal report variant with its own footer and preserved evidence layout."""

    def finish_page(self):
        self.content_bottoms.append(round(self.y, 2))
        self.c.setStrokeColor('#d9e3ec')
        self.c.setLineWidth(.5)
        self.c.line(46, 41, self.w - 46, 41)
        self.text('9 SEPTEMBER 2026  |  BITS PILANI / NEBULA COMPETITION REPORT',
                  46, self.h - 26, 7.3, color='#617287')
        self.text(f'{self.n:02d}', self.w - 61, self.h - 26, 9,
                  'Strong', '#1764b0')
        self.c.showPage()

def build():
    e=load_evidence(); m=metrics(e); make_figures(e)
    OUT.mkdir(parents=True,exist_ok=True)
    pdf=OUT/'Nebula_Competition_Report_Academic.pdf'
    r=AcademicReport(pdf)
    n=m['nominal']; mm=n['meas']; fixed=e['summary']['fixed']; agg=e['final']['aggregate']

    r.new('Competition technical report','NEBULA','RL-assisted automated analog circuit design for a PCIe Gen2 equalizer')
    r.y = 155
    r.para('Competition Technical Report',size=18,gap=26)
    r.c.setStrokeColor('#008575'); r.c.setLineWidth(3)
    r.c.line(46,r.h-r.y,125,r.h-r.y); r.y += 30
    r.para('<b>' + INSTITUTION + '</b>',size=14,gap=26)
    r.heading('Project team')
    r.table(['NAME','EMAIL ADDRESS'],[[name,email] for name,email in TEAM_MEMBERS],[170,333],9.8)
    r.para('Submitted 9 September 2026<br/>PCIe Gen2 equalizer design automation using SKY130, ngspice and reinforcement learning.',size=10.5,color='#526479',gap=16)

    r.new('Front matter / Abstract','Abstract and project objectives','A concise statement of the problem, method, principal evidence and intended contribution.')
    r.heading('Abstract')
    r.para('Nebula is a specification-to-circuit Python framework for a 5 Gbps NRZ PCIe Gen2 receiver equalizer. A frozen policy proposes settings in a bounded, characterised CTLE design space; deterministic checks select a fixed circuit; and ngspice remeasures the exported SKY130 design across the declared process, voltage and temperature grid. The product emits a readable schematic, exact SPICE deck, measured specifications and hash-verified evidence. Fixed physical CTLE demonstrations at 3, 6 and 9 dB, all at 1.9 GHz, pass 315/315 declared electrical-model conditions each. In the controlled cached-library experiment, PPO improves mean feasible eye quality over imitation and averages 5.579 candidate visits, a 91.8x reduction relative to enumerating 512 candidates. The report separates the learned proposal, classical verification, circuit measurements and link assumptions so each contribution can be audited.',size=10.4,gap=17)
    r.table(['DEMONSTRATED TARGETS','FIXED-CIRCUIT VERIFICATION','CACHED SEARCH'],[
        ['3, 6 and 9 dB at 1.9 GHz','45/45 PVT points and 315/315 cases per target','5.579 mean visits; 91.8x fewer than 512']],[168,168,167],9.4)
    r.heading('Project objectives')
    r.para('<b>1.</b> Accept peaking and peak-frequency targets through one validated interface.<br/><b>2.</b> Size and export an inspectable SKY130 source-degenerated CTLE.<br/><b>3.</b> Use reinforcement learning to reduce candidate visits within the characterised space.<br/><b>4.</b> Verify one fixed circuit across PVT, noise, distortion, power and link conditions.<br/><b>5.</b> Package the schematic, measurements and provenance for independent review.',size=9.8,gap=14)
    r.para('<b>Keywords:</b> analog design automation, reinforcement learning, CTLE, PCIe Gen2, SKY130, ngspice, PVT verification, decision-feedback equalization.',size=9.2,color='#526479')

    r.new('Front matter / Contents','Contents and evidence map','The academic sequence follows the problem, implementation, validation, learning evidence, product and conclusions.')
    r.table(['SECTION','SUBJECT','PAGES'],[
        ['1','Problem statement and success criteria','4'],
        ['2','Automation architecture and circuit implementation','5-8'],
        ['3','Analog, link and DFE verification','9-13'],
        ['4','Reinforcement-learning method and controlled evidence','14-16'],
        ['5','Engineering evolution, product, area and reproducibility','17-20'],
        ['6','Conclusions and future work','21-22']],[67,340,96],9.4)
    r.heading('Figure and evidence guide')
    r.table(['PAGES','PRIMARY EVIDENCE'],[
        ['5-8','Automated flow, CTLE topology, physical bias, switched attenuation and AC response'],
        ['9-13','Fixed PVT response, noise, power, HD3, headroom, eye model and DFE'],
        ['14-16','RL formulation, five-seed held-out experiment and equal-budget controls'],
        ['17-20','Design decisions, product workflow, computational cost, area and audit trail']],[90,413],9.1)
    r.heading('How to read the report')
    r.para('Headline circuit results come from one fixed physical CTLE at every tested corner. The RL pages separately establish proposal quality and candidate-visit reduction. Page 20 gives the exact evidence paths and reproduction command; page 22 ends with the prioritised future-work programme.',size=9.8)

    r.new('Chapter 1 / Problem and objectives','Problem statement and success criteria','The competition asks for a working equalizer, not eye opening in isolation.')
    r.table(['BRIEF REQUIREMENT','IMPLEMENTED INTERPRETATION / EVIDENCE'],[
        ['5 Gbps NRZ; 2.5 GHz Nyquist','Fixed link rate; differential signal convention throughout.'],
        ['Peaking 3-12 dB; tunable peak 1.25-2.5 GHz','User inputs are peaking and peak frequency. Fixed physical demonstrations: 3, 6 and 9 dB at 1.9 GHz.'],
        ['Source-degenerated CTLE + 1-tap DFE','SKY130 transistor CTLE; physical Rs/Cs geometry selected by software; behavioural first-post-cursor cancellation.'],
        ['HD3 < -30 dB at 100 MHz, 100 mV differential input','SPICE tone test uses 100 mV differential peak. A separate 2.5 GHz test checks high-frequency linearity.'],
        ['Input-referred noise < 1.5 mVrms','Differential input reference; 10 MHz-5 GHz integrated SPICE noise.'],
        ['Power < 15 mW; area < 0.05 mm2','Supply-current power measured for CTLE + reference. Geometry inventoried; complete receiver area/power require integration.'],
        ['Eye > 100 mV and > 0.4 UI','Worst-ISI cursor model; absolute differential voltage and contiguous positive-opening width.'],
        ['TT / SS / FF / SF / FS; VDD +/-5%; 0-125 C','45 sampled combinations: 5 processes x 1.71/1.80/1.89 V x 0/27/125 C. Same circuit at every point.'],
        ['Automated Python flow + simulator + schematic','CLI and browser product; frozen RL policy, verifier, ngspice deck, readable schematic and evidence export.']],[150,353],9.3)
    r.para('<b>Declared acceptance assumptions.</b> Request matching uses +/-1.5 dB and +/-0.3 octave, in addition to the absolute response band. These are project tolerances, not extra numbers supplied by the competition. Channel loss is a verification condition, not a CTLE gain request.',size=9.5)
    r.para('<b>PVT scope.</b> Transistor process corners are combined with typical passive models. Independent resistor/capacitor spread, local mismatch and extracted layout parasitics are separate closure tasks. The grid samples the temperature range at three points; it is not a continuous-temperature guarantee.',size=9.5)
    r.takeaway('How to read the result','Electrical acceptance and physical integration are reported separately: the 315-case grid verifies circuit/link behaviour under the stated conditions; layout and complete receiver area remain integration milestones.')

    r.new('Chapter 2 / Automated framework','Automation architecture','The final flow makes the boundary between learning, search and circuit verification explicit.')
    r.figure('submission_flow','Figure 1. Offline data are reused for proposals. Acceptance of the physical-bias export requires fresh simulator evidence, not a cached legacy score.',max_h=228)
    r.stages([
        ('1. Interpret a target','Validate peaking and peak frequency. Natural-language assistance maps a request into these structured fields; engineering constraints remain in the verifier.'),
        ('2. Propose and intersect','The frozen RL-hybrid policy proposes a library setting. A deterministic all-corner intersection identifies fixed setting 490 (A7, Rs index 5, Cs index 2).'),
        ('3. Realise and remeasure','Instantiate the physical reference and MIM bypass. Check DC/AC/noise and two HD3 tones at all 45 PVT points; evaluate seven link conditions per point.'),
        ('4. Export or explain','Export the exact accepted deck, schematic, structured results and raw evidence. An unsupported target receives an explicit status, not a fabricated compliant circuit.')])
    r.takeaway('Attribution matters','The deployed result is a hybrid system: RL supplies a proposal, classical verification enforces a fixed-circuit decision, and fresh SPICE establishes the final evidence. The physical-bias circuit was not used to retrain the frozen policy.')

    r.new('Chapter 2 / Circuit implementation','The source-degenerated CTLE','A differential NMOS pair with resistive loads and a shared Rs || Cs degeneration network.')
    r.figure('submission_core','Figure 2. Connectivity redrawn from the exported deck and checked against all physical instances. Input attenuator and bias are expanded on the following pages. NMOS bulks connect to ground.',max_h=300)
    r.table(['DEVICE / ELEMENT','FINAL NOMINAL GEOMETRY OR VALUE'],[
        ['M1 / M2','W = 57.9767 um total; L = 0.39115 um; nf = 4'],
        ['MT1 / MT2','W = 201.656 um; L = 0.5 um; nf = 8'],
        ['RL per side / external CL','254.633 ohm / 32.628 fF per output'],
        ['Rs / Cs between sources','356.818 ohm / 2.85155 pF; fixed drawn elements']],[175,328],9.5)
    r.para('At low frequency Rs reduces effective transconductance. At high frequency Cs bypasses the degeneration, raising the response before output parasitics impose roll-off. The input attenuator controls signal excursion without being mistaken for the peaking mechanism.',size=10)
    r.takeaway('A device-level implementation','The delivered netlist uses SKY130 MOS, poly-resistor and MIM models. External loading and common-mode excitation are explicitly documented testbench interfaces for the next stage of receiver integration.')

    r.new('Chapter 2 / Circuit implementation','Reference current made physical','The final export replaces the ideal Iref source and counts the bypass capacitor explicitly.')
    r.figure('submission_bias','Figure 3. PMOS reference/feed mirror, poly bias resistor, diode-connected NMOS reference and MIM bypass. Equal net names connect to the CTLE. PMOS bulks = VDD; NMOS bulk = 0.',max_h=290)
    r.table(['IMPLEMENTATION','VALUE / PURPOSE'],[
        ['MPref / MPfeed','W/L = 25.2069/0.5 um; PMOS supply-dependent reference'],
        ['MR and tail mirror','MR W/L = 25.2069/0.5 um; each tail has 8x width'],
        ['Rbias','Physical poly, W/L = 1/5.34 um; nominal 2.072 kohm'],
        ['Cbyp','Physical MIM, 70.545 x 70.545 um; 9.99945 pF'],
        ['Nominal supply power',f"{mm['power_w']*1000:.3f} mW, obtained from -VDD x I(VDD)"]],[166,337],9.6)
    r.para('The sizing target sets the reference geometry; the operating current is then determined by the transistors and resistor. Supply-current measurement includes the reference branch and mirror error. The complete physical circuit is rechecked across PVT rather than assuming the nominal mirror ratio remains exact.',size=10)
    r.takeaway('Design interpretation','This is a compact supply-dependent bias circuit, not a precision bandgap reference. Its practical value here is replacing an ideal source with a simulated physical implementation while preserving the fixed-circuit acceptance result.')

    r.new('Chapter 2 / Circuit implementation','Physical attenuation and peaking','The input switches are real; the Rs/Cs search indices do not imply a fabricated tuning bank.')
    r.figure('submission_attenuator','Figure 4. Positive input leg; the negative leg is identical. Three PMOS-switched shunt branches join inp to cm. A7 holds all three gates at 0 V (ON). W labels are total microns; L = 0.15 um.',max_h=204)
    r.para('The differential series-shunt network uses a 150 ohm series target per leg and binary-weighted shunt branches. Its switch resistance and parasitic loading are included in the measured response. In this export the attenuator code, Rs and Cs are held fixed across PVT.',size=10)
    r.figure('submission_ac',f"Figure 5. Raw SPICE AC magnitude: final nominal peaking {m['nom_peak']:.3f} dB at {m['nom_freq']:.3f} GHz; shaded limits show the 45-corner envelope. The curve is absolute voltage gain, not gain normalised to 0 dB.",max_h=246)
    r.takeaway('Peaking is a ratio, not absolute gain','Peaking is the maximum AC gain relative to low-frequency gain. A CTLE can therefore provide about 9 dB of peaking while its absolute peak gain remains near 0 dB; channel insertion loss is a different quantity.')

    r.new('Chapter 3 / Analog verification','One setting across the PVT grid','No corner-specific Rs/Cs retuning is used for this physical-product demonstration.')
    r.figure('submission_pvt','Figure 6. All 45 measured points. Shading and dashed lines mark project request-matching bands; dotted lines mark the requested centres. Point order within each process is supply/temperature order.',max_h=320)
    r.table(['METRIC','NOMINAL','45-CORNER RANGE'],[
        ['Peaking',f"{m['nom_peak']:.3f} dB",f"{m['min_peak']:.3f} to {m['max_peak']:.3f} dB"],
        ['Peak frequency',f"{m['nom_freq']:.3f} GHz",f"{m['min_freq']:.3f} to {m['max_freq']:.3f} GHz"],
        ['Peak extraction','Log-frequency interpolation','Shared extraction rule for all points'],
        ['Device-to-link fit residual',f"{n['fit_residual_db']:.4f} dB",f"Maximum {fixed['max_fit_residual_db']:.4f} dB"]],[168,137,198],9.5)
    r.para('The response shape follows the expected degeneration behaviour: approximately fz = 1/(2 pi Rs Cs), with degeneration pole multiplier k = 1 + (gm + gmb)Rs/2. The final response and peak are taken from SPICE, not these first-order equations.',size=10)
    r.takeaway('Margin to watch',f"All points meet the declared response checks, but the tightest peak-frequency matching margin is {m['min_frequency_margin_oct']:.4f} octave. This is a sampled-corner result; mismatch, extracted parasitics and finer PVT sweeps remain separate sign-off steps.")

    r.new('Chapter 3 / Analog verification','Noise and supply power','Results are measured at the differential interface of the final physical CTLE.')
    r.figure('submission_noise_power','Figure 7. Nine operating points per process corner. Dashed lines are the competition ceilings; power includes the CTLE and physical bias reference, not a transistor DFE or clock network.',max_h=265)
    r.table(['WORST OBSERVED','RESULT','REQUIREMENT'],[
        ['Input noise, 10 MHz-5 GHz',f"{m['max_noise_mv']:.3f} mVrms",'< 1.5 mVrms'],
        ['CTLE + bias power',f"{m['max_power_mw']:.3f} mW",'< 15 mW receiver target'],
        ['HD3, 100 MHz',f"{fixed['hd3_100mhz_worst_dbc']:.2f} dBc",'< -30 dBc'],
        ['HD3, 2.5 GHz',f"{fixed['hd3_nyquist_worst_dbc']:.2f} dBc",'Additional high-frequency check']],[204,133,166],9.1)
    r.para('Noise is referred to the differential input source before attenuation and integrated over the specified 10 MHz-5 GHz band. Supply power comes from the simulated VDD branch rather than nominal tail-current targets, so the physical reference and mirror behaviour are included.',size=10.3)
    r.para('Power excludes the decision circuit, feedback path, clocking, tuning controls and common-mode generator. HD3 is a simulated-model result: ngspice ignores the generic poly resistor voltage coefficients p2/q2/p3/q3. Their distortion contribution remains NOT_VERIFIED; see page 21.',size=10.3)
    r.takeaway('Measurement discipline','The simulator returns integrated noise as RMS voltage, not a variance to square-root again. Output parsing, finite-value checks and transistor operating-point guards accompany every result; simulator exit status alone is not accepted as proof.')

    r.new('Chapter 3 / Analog verification','Linearity and signal headroom','Harmonic distortion and DC swing complement small-signal AC measurements.')
    r.figure('submission_linearity','Figure 8. HD3 at two separately tested tone frequencies across PVT (left) and the raw nominal DC transfer (right). Input amplitudes are differential peak values, not peak-to-peak.',max_h=285)
    r.table(['MEASUREMENT','TEST CONDITION / RESULT'],[
        ['Competition HD3 test',f"100 MHz, 100 mV differential peak; worst {fixed['hd3_100mhz_worst_dbc']:.2f} dBc"],
        ['Additional Nyquist test',f"2.5 GHz, 267.338 mV differential peak; worst {fixed['hd3_nyquist_worst_dbc']:.2f} dBc"],
        ['Nominal output swing guard',f"Measured limit {n['measured_swing_pp_v']:.3f} V differential peak-to-peak"],
        ['Nominal saturation margins',f"Input pair {mm['pair_margin_v']:.3f} V; tail {mm['tail_margin_v']:.3f} V (VDS - VDSAT)"]],[196,307],9.6)
    r.para('HD3 is computed as 20 log10(V3/V1) using a coherent steady-state window: 20 fundamental cycles and 2,000 uniform samples. The same extraction routine is used at both frequencies. The differential DC transfer is inspected separately because an acceptable small-signal response does not guarantee adequate large-signal headroom.',size=10.3)
    r.takeaway('Device-to-link guard','The FFT results reproduce, but generic poly resistor voltage coefficients are ignored by ngspice. Full passive linearity remains NOT_VERIFIED. Replacing those resistors changes resistance and parasitics and requires fresh circuit verification; numerical HD3 margin cannot bound the omitted effect.')

    r.new('Chapter 3 / Link validation','From transistor response to eye','Absolute signal amplitude is carried into a 5 Gbps NRZ link model.')
    r.para('The bridge fits a one-zero/two-pole response to the measured CTLE magnitude, checks fit quality and measured output swing, and composes it with the transmitter and channel. Pulse cursors then give worst-ISI opening after first-post-cursor cancellation. This links device choices to a receiver metric without a transient SPICE run for every bit pattern.',size=10.5)
    r.figure('submission_eyes','Figure 9. Minimum-to-maximum modelled eye over the 45 PVT points at each constructed channel loss, with ideal behavioural 1-tap DFE. Dashed lines: 100 mV and 0.4 UI thresholds.',max_h=249)
    r.table(['LINK CONDITION','DECLARED SETTING'],[
        ['Transmitter','0.8 V differential peak-to-peak; -3.5 dB de-emphasis'],
        ['Channel family','Constructed minimum-phase skin/dielectric-loss channels; 3 to 12 dB at Nyquist in 1.5 dB steps'],
        ['Sampling / eye definition','64 samples/UI; height at pulse cursor; contiguous positive-opening width'],
        ['Final circuit across all conditions','One fixed geometry and code; no channel-specific resizing'],
        ['Lowest ideal-DFE opening',f"{m['min_eye_mv']:.2f} mV; {fixed['dfe_policies']['ideal']['min_eye_w_ui']:.4f} UI (separate minima)"]],[165,338],9.3)
    r.takeaway('What this visual establishes','These are noiseless cursor-based ISI openings: noise is not subtracted and width is measured at zero height. They are not BER contours. Phase is inferred from the magnitude fit, not independently validated; random jitter, clock recovery and DFE error propagation are absent.')

    r.new('Chapter 3 / Link validation','What the 1-tap DFE contributes','A controlled behavioural model makes the cancellation assumption inspectable.')
    r.figure('submission_dfe','Figure 10. Nominal 7.5 dB-channel cursors (left) and worst width under four DFE policies over all 315 conditions (right). These are saved link-model results, not transistor-level DFE measurements.',max_h=236)
    r.para('<b>Operation.</b> The normalised tap is b1 = h1/h0. The previous decision removes the first post-cursor, while the remaining pre- and post-cursors set the worst-ISI opening. For ideal cancellation, eye height is 2(h0 - sum of the remaining absolute cursor amplitudes), clipped at zero.',size=10.3)
    pol=fixed['dfe_policies']
    r.table(['TAP POLICY','MIN HEIGHT','MIN WIDTH'],[
        [label,f"{pol[key]['min_eye_h_v']*1000:.2f} mV",f"{pol[key]['min_eye_w_ui']:.4f} UI"] for key,label in [('ideal','Ideal first-post-cursor cancellation'),('misadapted','20% of first post-cursor remains'),('quantised','Tap step 1/16; clipped to +/-0.5'),('none','No cancellation')]], [259,122,122],9.6)
    r.para('All four policies remain above the eye thresholds for this circuit and channel family. The clearest benefit here is width margin; the CTLE itself already supports the height target. The tap-quantisation model includes both endpoints and must not be presented as a realised 4-bit DAC.',size=10)
    r.para('For the nominal 7.5 dB channel, h0 = 184.99 mV and h1 = -43.43 mV, giving b1 = -0.2348. The ideal-tap opening is 255.81 mV and 0.8125 UI. This concrete operating point connects the cursor plot to the cancellation arithmetic.',size=9.6)
    r.takeaway('Hardware boundary','The final DFE is behavioural. The latest physical decision/hold study passed 14/32 held bits; all 18 transitions missed the timing window and some terminals exceeded the model domain. The failed prototype is preserved in DFE_LOW_LOAD_RESULTS.md; no integrated transistor DFE is demonstrated.')

    r.new('Chapter 4 / Reinforcement learning','Learning a useful search policy','The policy learns incremental improvement inside a bounded, characterised design space.')
    r.table(['RL ELEMENT','IMPLEMENTATION'],[
        ['State','62 features: six request/current-search fields plus eight seven-field history slots. Each slot records presence, three indices, measurement validity, eye height and eye width. PVT/channel identity and oracle quality are hidden.'],
        ['Actions','Increase/decrease attenuation, Rs or Cs index; or LOCK. Seven actions, with bounds masks.'],
        ['Episode','At most eight visits; lock is available after two visits. After rollout, the shield selects the best compliant visited candidate, including the start.'],
        ['Network / training','Two 64-unit hidden layers; imitation warm start followed by PPO; five independent training seeds.'],
        ['Training scale','50 imitation epochs and 200,000 PPO steps per seed. Frozen policy is reused at inference.']],[136,367],9.5)
    r.heading('Reward: improve feasible eye quality')
    r.box('Normalised quality and incremental reward','q(s) = clip(A(s)/A*, 0, 1) for a compliant state; otherwise q(s) = 0.<br/>Move reward = q(next) - q(current).<br/>LOCK reward = 0 if compliant; otherwise -1 - q(current).<br/>A is eye-opening area; A* is the per-condition feasible reference. Discount factor: 0.99.')
    r.para('Reward and compliance are distinct: a large eye does not compensate for failing noise, power or response checks. The training oracle supplies quality labels; the deployed actor sees only its observation. The deterministic verifier remains the authority on acceptance.',size=10.3)
    r.para('The actor therefore learns from how candidate changes affect the observed eye. Action masks prevent out-of-range index moves, while the safety shield adds constraint knowledge outside the neural network. These roles are deliberately separate in the implementation.',size=10)
    r.takeaway('Why this formulation','Early continuous-search experiments motivated a bounded library formulation with explicit requests and feasibility checks. This made improvement measurable, training reusable and the final decision explainable instead of relying on an opaque reward alone.')

    r.new('Chapter 4 / Held-out experiment','The frozen hybrid-policy experiment','Original five-seed held-out result, preserved. Equal-budget attribution controls appear on page 16.')
    r.figure('submission_rl','Figure 11. Every seed improves normalised quality over the fixed start. Compliance compares the same held-out conditions. This is the frozen library-policy study [E3], not a re-training result for the later physical-bias circuit.',max_h=235)
    r.table(['HELD-OUT RESULT','VALUE'],[
        ['Condition identities','2,430 per seed; 12,150 seed-condition evaluations'],
        ['Mean normalised quality',f"{e['final']['fixed']['mean_quality']:.4f} fixed start -> {agg['mean_quality']:.4f} shielded RL"],
        ['Mean paired quality improvement',f"+{agg['quality_delta']:.4f}; 95% bootstrap CI [{agg['paired_quality_delta_ci95'][0]:.4f}, {agg['paired_quality_delta_ci95'][1]:.4f}]"],
        ['Positive training seeds','5 of 5'],
        ['Mean policy visits',f"{agg['mean_trials']:.3f} per evaluated identity"],
        ['Mean model compliance',f"{100*e['final']['fixed']['compliance_rate']:.2f}% -> {100*agg['mean_compliance_rate']:.2f}%"]],[217,286],9.6)
    r.para('The held-out set exercises midpoint loss/request conditions within the established device library and PVT lattice. The result supports a repeatable improvement in feasible eye quality. It is not evidence of generalisation to a new process, a measured board channel or an arbitrary circuit topology.',size=10)
    r.takeaway('Interpretation for the submission','RL contributes useful, repeatable local improvement. The final physical product adds deterministic fixed-circuit selection and fresh verification on top; it should be presented as RL-assisted automation, not as proof that RL alone guarantees every specification.')
    r.new('Chapter 4 / Controlled comparisons','Policy value under controlled comparisons','Frozen policy and supplemental cached diagnostics; no retraining or new SPICE.')
    import statistics
    a = e['supplemental']['attribution']
    def mean(arm, budget, key):
        return statistics.mean(x[key] for x in a['results'] if x['arm']==arm and x['budget']==budget)
    labels = [('fixed','Fixed start'),('hill','Visible-eye hill climb'),('random_local','Random local moves'),('random_global','Uniform global samples'),('bc','Imitation only'),('ppo','Imitation + PPO')]
    r.table(['SAME 8-VISIT CAP','COMPLIANCE','QUALITY q','ACTUAL VISITS'],[
        [label,f"{100*mean(arm,8,'compliant'):.2f}%",f"{mean(arm,8,'quality'):.4f}",f"{mean(arm,8,'n_visits'):.3f}"]
        for arm,label in labels],[177,111,102,113],9.4)
    r.para('All arms use the same starting lookup and best-compliant-visited shield. Random arms use 20 persistent seeded streams; imitation and PPO use five matching frozen checkpoints. Local controls share one-index moves; global sampling has a different move space and is a practical sizing control. Repeats are billed.',size=10)
    delta = next(x for x in a['comparisons'] if x['budget']==8 and x['comparator']=='bc')
    r.para(f"PPO versus imitation: quality +{delta['quality_delta']:.4f}, paired 95% interval [{delta['quality_ci95'][0]:.4f}, {delta['quality_ci95'][1]:.4f}]; compliance +{100*delta['compliance_delta']:.2f} percentage points. PPO uses more visits than imitation. Random local exploration achieves higher compliance, while PPO achieves higher mean quality with fewer visits.",size=10)
    r.table(['EXTERNAL VISIT CAP','IMITATION q','PPO q','RANDOM LOCAL q'],[
        [str(b),f"{mean('bc',b,'quality'):.4f}",f"{mean('ppo',b,'quality'):.4f}",f"{mean('random_local',b,'quality'):.4f}"] for b in (2,4,8)],[177,111,102,113],9.4)
    r.para('Caps interrupt original eight-visit trajectories; trained observation scaling stays unchanged and early LOCK is honoured. Intervals resample 54 request/loss blocks after averaging seeds and PVT within each block. They are conditional on the shared circuit library. Every eight-visit PPO output reproduces the original result.',size=9.4)
    r.para('The Entry 115 exhaustive comparison independently anchors the search budget: PPO averages 5.579 visits against 512 candidates, a 91.8x reduction. The comparison is evaluated on the exposed cached library; fresh physical acceptance remains separately billed.',size=8.8)
    r.takeaway('Defensible contribution','PPO improves quality and compliance over imitation at the same visit cap and uses 91.8x fewer cached candidate visits than exhaustive enumeration. A deterministic evidence layer then selects and freshly verifies the physical circuit.')
    r.new('Chapter 5 / Engineering implementation','How the final architecture emerged','Each stage converted a modelling assumption into a more testable engineering decision.')
    r.stages([
        ('Physics and a reproducible simulator interface','Established the SKY130 CTLE, differential units, source degeneration and device-to-link bridge. Added output parsing and operating-point guards so a simulator exit code was not the sole evidence.'),
        ('A bounded, specification-driven search problem','Organised the candidate space as eight attenuation choices x eight Rs choices x eight Cs choices. Reused measured circuit data for policy training and request-specific evaluation.'),
        ('A shielded policy with held-out evidence','Combined imitation warm start, PPO and best-compliant-visited selection. The original result improves quality over a fixed start; page 16 separately tests imitation and classical controls.'),
        ('From adaptive candidates to one robust export','Added target-centred matching and all-corner intersection. Selected setting 490 so the physical demonstration uses the same circuit across every tested process, voltage and temperature.'),
        ('Physical bias, bypass and auditable geometry','Replaced ideal Iref with a PMOS/resistor reference, realised the bypass as MIM and remeasured the whole candidate. Bound raw outputs, schematic and inventory to one circuit identity.'),
        ('Product integration and a controlled submission scope','Integrated the physical mode into CLI and browser workflows. Hardware decision/retention studies failed transition timing and model-domain checks; the submission preserves the verified CTLE and behavioural DFE.')])
    r.table(['DESIGN DECISION','RESULTING EVIDENCE'],[
        ['Freeze the learning policy','5/5 seeds with positive held-out quality gain'],
        ['Freeze one physical circuit','45 PVT points; 315 electrical-model cases'],
        ['Bind the exported artifacts','616 raw/evidence hashes; exact nominal deck']],[217,286],9.2)
    r.takeaway('The final design choice','The final architecture balances deployability, reproducibility and traceable device-level verification. Each stage strengthened the delivered workflow: from physical models to reusable learning, fixed-circuit acceptance and inspectable exports.')

    r.new('Chapter 5 / Product and efficiency','A usable engineering workspace','A structured request becomes a circuit artifact, not merely a reward curve.')
    r.table(['PRODUCT CAPABILITY','ENGINEERING USE'],[
        ['Structured / natural-language input','Translate intent into peaking and peak-frequency targets; confirm the actual structured values.'],
        ['PVT exploration','Inspect corner-dependent metrics and margins rather than only nominal headline values.'],
        ['Circuit comparison','Compare selected circuit artifacts and their response; no benchmark leaderboard is required in the user workspace.'],
        ['Channel upload','Supports a separate channel-assessment workflow. The 315-case result in this report uses the declared constructed family, not arbitrary uploaded data.'],
        ['Failure-aware output','Expose unsupported requests and unverified scope without manufacturing a pass.'],
        ['Evidence bundle and demonstration view','Export circuit, schematic, JSON, raw evidence and hashes. Cached legacy demo artifacts remain distinguishable from the final physical run.']],[165,338],9.3)
    r.heading('Where the computational work happens')
    r.para('<b>Offline:</b> 512 settings x 45 PVT points = 23,040 measured library rows; seven channel views give 161,280 condition rows. Additional midpoint characterisation and five-seed training are separate development costs.<br/><b>Online physical example:</b> the saved final run used 137 fresh simulator calls: one legacy capture, one bias calibration and 135 PVT measurement calls. Recorded run wall time: 107.91 s on the development machine.',size=10)
    r.para('The physical mode uses policy proposals, a fixed-setting prescreen and fresh acceptance. In the exposed 512-setting benchmark, PPO averages 5.579 candidate visits: 91.8x fewer than exhaustive enumeration. This is candidate-visit reduction in the cached library, not complete physical-export wall-clock speedup.',size=9.7)
    r.heading('Suggested demonstration sequence')
    r.para('Enter 9 dB and 1.9 GHz, select the physical-bias mode, then inspect nominal response and the fixed PVT matrix. Open the schematic and export the bundle. For an immediate review, use the saved physical example instead of starting a fresh run.',size=9.7)
    r.takeaway('Efficiency at a defined boundary','Characterisation is amortised across requests. The measured 91.8x candidate-visit reduction passes the frozen efficiency gate; offline banks, imitation, five PPO runs and each 137-call physical acceptance remain billed separately. End-to-end wall-clock speedup remains unverified.')

    r.new('Chapter 5 / Area and integration','Geometry counted at the right boundary','A physical capacitor can dominate area even when MOS gate rectangles are small.')
    r.figure('submission_area','Figure 12. Netlist-derived geometry inventory for all 27 physical instances. Values count passive bodies/plates and MOS W x L rectangles, with instance multiplicity; they are not a routed floorplan.',max_h=221)
    r.table(['AREA ACCOUNT','RESULT'],[
        ['Physical bypass MIM plate','0.004977 mm2'],
        ['All passive bodies / plates',f"{e['area']['passive_body_plate_mm2']:.6f} mm2"],
        ['All MOS gate rectangles',f"{e['area']['mos_gate_area_mm2']:.6f} mm2"],
        ['Known geometry subtotal',f"{e['area']['geometry_subtotal_mm2']:.6f} mm2"],
        ['Complete receiver area vs 0.05 mm2','NOT_VERIFIED; no guessed layout multiplier']],[250,253],9.6)
    r.para('The inventory includes the input attenuator, core, physical reference, degeneration elements and bypass. Contacts, diffusion, wells, guard rings, routing, spacing and a floorplan are not represented by the subtotal. The transistor DFE, clocks, Rs/Cs selectors and common-mode generator also require an integration budget.',size=10)
    r.para('Physical Rs/Cs tuning is an extension to the present fixed-geometry export. Selector parasitics must be characterised in the final topology, followed by complete receiver simulation and layout extraction. The assumed 32.628 fF load per output must be replaced or justified when a real next stage is attached.',size=10)
    r.takeaway('Next technical closure','Integrate the decision/feedback path and control, verify device operating limits and timing, then perform layout-aware area/power and post-extraction PVT checks. These steps extend the delivered platform; the current subtotal is not used to certify full S7 compliance.')

    r.new('Chapter 5 / Reproducibility','Evidence an evaluator can inspect','Every headline result is tied to saved source artifacts; report generation performs no new SPICE or RL run.')
    r.heading('Reproduce the physical product')
    r.para('From the repository root, in the documented Python/ngspice/PDK environment:<br/><font face="Strong">py -3.13 -m nebula.design --method rl-physical --peaking 9 --f-peak 1.9 --out output/my_physical_design</font><br/>Use a new output directory. The command launches fresh acceptance; opening the saved demonstration is the quick review path.',size=9.4)
    refs=[
        ('E1','Final physical export','nebula/product_demo/physical_bias_9db_1p9ghz_20260906/','design.json, design.cir, physical_evidence/summary.json and fixed_pvt.jsonl; 616 evidence-file hashes checked.'),
        ('E2','Physical implementation and product integration','nebula/physical_design.py; nebula/PHYSICAL_PRODUCT_RESULTS.md','One fixed signature, physical reference/MIM generation, fresh acceptance and artifact export.'),
        ('E3','Frozen RL experiment','nebula/experiments/shielded_policy_final_results.json','Five seeds, paired held-out metrics and bootstrap confidence interval; policy freeze a84082e.'),
        ('E4','Reward and deterministic verification','nebula/rl/margin_improve_env.py; nebula/rl/safety_shield.py','Incremental quality reward, action validation and termination rules.'),
        ('E5','Device-to-eye and DFE controls','nebula/link/bridge.py; nebula/link/cursors.py; nebula/link/dfe_ablation.py','Measured-response adapter, cursor definitions and four cancellation policies.'),
        ('E6','Geometry and exact-deck checks','nebula/report/product_scope.py; nebula/report/physical_schematic.py','Physical inventory, ordered connectivity checks and canonical circuit identity.')]
    for key,title,path,desc in refs:
        r.para(f'<b>[{key}] {title}.</b> {path}<br/>{desc}',size=8.8,gap=9)
    r.heading('Method and tool references')
    r.para('[R1] Schulman et al., <i>Proximal Policy Optimization Algorithms</i>, 2017. <link href="https://arxiv.org/abs/1707.06347" color="#1764b0">arxiv.org/abs/1707.06347</link><br/>[R2] SkyWater, SKY130 device documentation. <link href="https://skywater-pdk.readthedocs.io/en/main/rules/device-details.html" color="#1764b0">SKY130 device details</link><br/>[R3] ngspice documentation. <link href="https://ngspice.sourceforge.io/docs.html" color="#1764b0">ngspice.sourceforge.io/docs.html</link><br/>References accessed 6 September 2026. Installed simulator: ngspice 41.',size=8.8,gap=10)
    r.heading('A short evidence-review protocol')
    r.para('<b>1.</b> Match design.json to the nominal TT values and inspect the exported transistor/passive deck.<br/><b>2.</b> Confirm one circuit signature across the 45 PVT journal rows, each with seven link conditions.<br/><b>3.</b> Inspect raw AC, noise, HD3 and swing files for a nominal and a limiting corner.<br/><b>4.</b> Review the separate RL held-out result and geometry inventory at their stated boundaries.',size=9.4,gap=12)
    r.takeaway('Artifact integrity','Physical circuit signature: 21f09626c56aeb70... . The companion report source manifest records exact source and output SHA-256 hashes. The final report separates physical CTLE evidence, library-policy experiments and system-model assumptions throughout.')
    r.new('Chapter 6 / Conclusions','Conclusions and delivered framework','From target specifications to a fixed circuit and inspectable results.')
    r.heading('Demonstrated physical design')
    r.para('Nebula now demonstrates fixed SKY130 CTLEs at 3, 6 and 9 dB, all at 1.9 GHz. Each accepted circuit uses a physical bias reference and MIM bypass and passes 315/315 declared electrical-model conditions across 45 PVT points and seven channels, without corner-by-corner resizing.',size=10.5)
    r.stages([
        ('Specify the response', 'Enter peaking and peak frequency through the Python interface or dashboard. The request uses the same structured specification and validation path.'),
        ('Select and verify', 'A frozen learned policy supplies a proposal; deterministic fixed-setting selection and fresh ngspice measurements establish acceptance for the exported circuit.'),
        ('Inspect and reproduce', 'Open the schematic, exact SPICE deck and resulting specifications. Corner journals, raw measurements and source hashes make the result independently auditable.')])
    r.heading('Acceptance across requests')
    r.para('A frozen recovery run measured all ten remaining eligible candidates for the two near-pass 1.9 GHz targets. Setting 401 recovered 3 dB and setting 474 recovered 6 dB; both pass 315/315 conditions. Together with the original 9 dB result, this establishes three fixed target points and an automatic, hash-verified selection path.',size=10)
    r.heading('Evidence supplied with the framework')
    r.para('Every accepted target includes a fingerprinted raw-evidence set, the exact measured nominal deck and a fixed-circuit PVT journal. The recovery experiment retains all ten candidate outcomes and 1,370 billed SPICE calls; separate frozen-policy, control and exhaustive-oracle diagnostics document the learning contribution.',size=10)
    r.para('Measurement definitions and integration scope are given alongside the relevant results: noise and HD3 on pages 10-11, link/DFE assumptions on pages 12-13, and geometry accounting on page 19. These definitions also apply to the closing result above.',size=9.4)
    r.para('Companion evidence: nebula/product_demo/physical_bias_9db_1p9ghz_20260906/; nebula/product_audits/entry115_physical_recovery_20260908/; nebula/product_audits/entry115_exhaustive_benchmark_20260908/; and nebula/WINNING_SPRINT_RESULTS.md.',size=8.8)
    r.takeaway('Delivered contribution','Nebula connects specification input, RL-assisted search, physical CTLE verification and inspectable circuit exports in one automated Python framework. The saved demonstration provides a reproducible starting point for extending tuning coverage and receiver integration.')

    r.new('Chapter 6 / Future work','Future work and development priorities','A prioritized engineering roadmap that builds directly on the delivered automation and evidence framework.')
    r.stages([
        ('1. Extend physical tuning coverage','Implement the programmable Rs/Cs selector network with extracted switch parasitics, then demonstrate fixed circuits across the 1.25-2.5 GHz peak-frequency range and the remaining peaking targets.'),
        ('2. Complete the transistor-level 1-tap DFE','Integrate a slicer, decision storage, feedback timing and a physical feedback DAC. Verify 5 Gbps settling, logic levels and cancellation across the same PVT matrix.'),
        ('3. Close layout and post-extraction verification','Create the CTLE-plus-DFE floorplan, complete DRC/LVS and parasitic extraction, and re-evaluate area, power, noise, distortion, eye opening and device operating limits.'),
        ('4. Expand robustness evidence','Add passive variation, mismatch and Monte Carlo analysis; replace the assumed output load with the integrated next stage and validate using measured or supplied channel S-parameters.'),
        ('5. Grow the learning problem','Extend RL control to selected transistor dimensions, bias and programmable passives. Compare against Bayesian and evolutionary optimizers using equal physical SPICE-call and wall-clock budgets.'),
        ('6. Strengthen deployment and interaction','Package the toolchain for repeatable installation and extend the LLM wrapper so engineers can request trade-offs while the deterministic verifier remains the authority for circuit acceptance.')])
    r.takeaway('Development priority','First close physical frequency tuning and the transistor DFE; next complete layout extraction and broader robustness evidence. The existing artifact and hash framework can carry each new result into the same auditable workflow.')
    r.save()
    sources=[FINAL,DEMO/'design.json',DEMO/'design.cir',PHYS/'summary.json',PHYS/'fixed_pvt.jsonl',PHYS/'evidence_sha256.json',
             PHYS/'area_inventory.json',PHYS/'geometry.json',Path(__file__),ROOT/'nebula/report/competition_submission.py',ROOT/'nebula/report/competition_2026.py',
             ROOT/'nebula/report/check_competition_pdf.py',ROOT/'nebula/physical_design.py',ROOT/'nebula/report/physical_schematic.py',
             ROOT/'nebula/report/product_scope.py',ROOT/'nebula/link/dfe_ablation.py',ROOT/'nebula/link/bridge.py',
             ROOT/'nebula/link/cursors.py',ROOT/'nebula/rl/margin_improve_env.py',ROOT/'nebula/rl/safety_shield.py']
    sources += [folder / 'summary.json' for folder in POST_DIRS.values()]
    sources += [WIN_BENCH/'summary.json', WIN_BENCH/'sha256.json',
                WIN_RECOVERY/'summary.json', WIN_RECOVERY/'recovery.jsonl',
                WIN_RECOVERY/'sha256.json', WIN_REGISTRY,
                ROOT/'nebula/WINNING_SPRINT_PLAN.md',
                ROOT/'nebula/WINNING_SPRINT_RESULTS.md']
    sources += [ROOT/'nebula/POST_REVIEW_PLAN.md', ROOT/'nebula/experiments/exp_post_review_attribution.py',
                ROOT/'nebula/experiments/exp_post_review_coverage.py', ROOT/'nebula/experiments/audit_post_review_models.py',
                ROOT/'nebula/PASSIVES.md', ROOT/'nebula/DFE_LOW_LOAD_RESULTS.md',
                ROOT/'nebula/experiments/joint_bank_73_results.json', ROOT/'nebula/experiments/joint_bank_midpoint_metadata.json']
    sources += [ROOT/f'nebula/experiments/shielded_train_{seed}.json' for seed in range(2026090500,2026090505)]
    manifest=dict(report=pdf.name,revision='Entry 119 / academic structure candidate with preserved competition report',page_count=r.n,
                  circuit_signature=SIGNATURE,physical_evidence_hashes_checked=e['manifest_count'],
                  report_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),content_bottoms_pt=r.content_bottoms,
                  sources=[dict(path=p.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sources],
                  notes='Physical mode integrated; behavioural DFE; full receiver area/power not verified. Report build uses saved evidence only; supplemental runs are separately recorded.')
    (OUT/'Nebula_Competition_Report_Academic_sources.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(f'Created {pdf} ({r.n} pages)')
    return pdf

if __name__ == '__main__':
    build()
