# Nebula submission video: recording script

Use your own voice. The main narration is designed for about 5-6 minutes with
short pauses for clicks. Screen actions are directions for you; read only the
quoted text. The report provides the detailed methods, results and limitations.

## Before recording

1. Use the running app at http://127.0.0.1:8765. Start a server only if no
   instance is running: from the repository root, run `py -3.13 -m nebula.web`
   and open the printed URL. Keep the current instance for your saved 3 dB run;
   restarting with its original `--run-root` restores that result.
2. Use a desktop browser at 1440 x 1000 or larger, 100% zoom. Hide unrelated
   tabs and notifications. Use browser full screen if it makes text clearer.
3. Open `output/pdf/Nebula_Submission_Report_20260914.pdf` in another tab.
   Bookmark pages 8, 18 and 23 for the policy comparison, hardware PVT plot and
   requirement matrix. Both older PDFs remain available for comparison.
4. Click **Enter judge mode**. Confirm the selected design target is **9 dB at 1.9 GHz**.
   Expand **Explore the separate transistor CTLE + DFE checkpoint** and confirm its measured hardware region shows **45/45 points pass**. Collapse it again before starting.
5. The reliable recording route uses saved completed results. You can optionally
   show a new request with **RL shield - adaptive bank**, then **Generate and
   verify**. That path uses frozen bank measurements for search and PVT, then
   makes one SPICE call for the representative export deck. Physical
   CTLE export is a different path and may launch fresh simulator work; it is
   not needed for this recording.

## 0:00-0:35 | Introduce the problem

**Screen:** Design Explorer, top of page. Keep the selected result, measured response and verification coverage visible.

> Hello, we are Jai Kaushik, Rishabh Agarwal and Avi Mehta from BITS Pilani.
> Our project is Nebula, an RL-assisted design framework for a five-gigabit
> NRZ equalizer using the open-source SKY130 process and ngspice.
>
> The challenge is not simply to predict component values. We need to accept
> a target response, find a useful circuit, verify it, and return the schematic
> together with evidence of what it actually achieves. Nebula brings those
> steps into one inspectable workflow.

## 0:35-1:25 | Show specifications becoming a result

**Screen:** In **Design explorer**, click **New target**. Expand **Describe the target in words**, enter the nine-decibel request and click **Read this request**. Point to the numerical fields and **RL shield - adaptive bank**, then close the editor to continue with the saved run. The CTLE with tail devices opens first beside the inspector. For the saved adaptive-bank demo, choose **Specs**: this artifact has scalar measurements but no retained raw AC plot. Your saved physical 3 dB run also offers the **Response** plot. Use the four block controls to switch drawings; **Expand circuit** gives any drawing the full width. In the right inspector, choose **Specs**, **Sizing** or **Run record**. The two panels below open the exact generated drawing and the independent transistor checkpoint. **Inspect all PVT corners** opens the grid directly.

> Here I can describe the response in plain language, and the tool extracts
> the numerical target. For this example, we request nine decibels of peaking
> around one point nine gigahertz.
>
> The policy proposes attenuation, resistance and capacitance codes. A
> deterministic verifier checks the proposals, and a measured-bank fallback
> can recover or center the result. The output includes the circuit drawing,
> measured specifications and downloadable files.
>
> I am showing a saved completed run for a repeatable demonstration. This
> adaptive-bank path reuses SPICE-characterized data. Its link score uses a
> behavioral one-tap DFE; the newer transistor receiver has separate evidence,
> which I will show next.

**If recording a newly generated bank run instead:** replace the last paragraph
with: "This is a newly generated result using the frozen, SPICE-characterized
bank. Search and PVT reuse saved measurements; one SPICE call produces the
representative export deck. Its link score uses a behavioral one-tap DFE;
the newer transistor receiver has separate evidence, which I will show next."
Do not call a saved run a live generation.

## 1:25-2:20 | Explain the physical implementation

**Screen:** In **Design explorer**, expand **Explore the separate transistor CTLE + DFE checkpoint**. Clearly point to its independent **9 dB / 1.9 GHz** label. Its inspector starts with **CTLE core + tail current sources**; select **Rs/Cs controls**, then **1-tap DFE**. Each drawing fits the panel.

> This separate checkpoint implements the complete transistor feedback path.
> Its physical signal path starts with an input attenuator, followed by the
> source-degenerated CTLE. Resistance and capacitance shape the response.
> Here they are implemented as electrical controls: an NMOS-controlled
> resistor branch and two bias-controlled varactors.
>
> The CTLE drives a transistor CML summer. Master and slave latches hold the
> decision, and a current DAC feeds the previous decision back into the summer.
> The complete calibrated deck contains seventy-three SKY130 device instances.
>
> Integrating this feedback circuit changed the CTLE loading. We therefore
> calibrated the loaded receiver and independently verified the selected
> controls. That was an important engineering step: a standalone result could
> not simply be transferred to the integrated circuit.

## 2:20-3:15 | Show the measured hardware result

**Screen:** Scroll to **See the recovered signal** and **Measured performance**.
Then switch to report page **18**, which plots the hardware PVT measurements.
The application's **Design PVT** tab concerns the generated-run model; it is
not this transistor-receiver plot.

> The measured nominal response is about eight point seven four decibels,
> with the peak near one point nine zero five gigahertz, within our stated
> target tolerances. Nominal input noise is about zero point six five four
> millivolts RMS, and HD3 is about minus fifty-five dBc under the stated tone test.
>
> The same control fractions, tap code and phase pass all forty-five sampled
> link PVT points without corner retuning. The minimum sampled eye is about
> one hundred thirteen millivolts, and maximum CTLE-plus-DFE supply power is
> about twelve point five milliwatts.
>
> These are sixty-four-bit, noiseless waveform checks on a constructed
> channel. They demonstrate a working calibrated feedback path, not a BER
> measurement or complete receiver signoff.

## 3:15-4:00 | Explain what RL contributed

**Screen:** Report page **8**. Point to both comparison charts, then the
candidate-visit and near-optimality paragraphs.

> We evaluated five frozen policy seeds on two thousand four hundred thirty
> final identities. The policy improves mean quality over the fixed starting
> point. Here quality means eye area relative to the best compliant bank
> candidate; a noncompliant candidate scores zero.
>
> The exhaustive-library comparison shows about ninety-two times fewer
> cached candidate visits. This is not a ninety-two-times SPICE speedup:
> characterization and training have their own cost. The production flow also
> includes classical fallback checks.
>
> We retained the less favorable results too. Local random search has higher
> compliance, and our near-optimality gate fails. The evidence supports useful
> RL-assisted search, without claiming that learning solves every design case.

## 4:00-4:40 | Demonstrate trustworthy behavior

**Screen:** Return to **Design explorer**. Open **New target**, change peaking to **8**, and close the editor. The selected completed run retains its original target and evidence. Expand the separate **9 dB / 1.9 GHz** checkpoint, then **Inspect the transistor device schematic**. Point to **Exact SPICE deck** and **45-point measurement record**.

> Editing a future request does not relabel a completed circuit. The selected
> run keeps its original measurements, while the independent transistor
> checkpoint keeps its own nine-decibel target and source files.
> A new circuit needs its own verification before it can claim a pass.
>
> Every displayed hardware result links back to the exact circuit and
> measurement record. The tool checks source integrity and preserves failed
> or unsupported outcomes. That makes the verification part of the product,
> rather than just a final presentation slide.

## 4:40-5:15 | Close with the contribution

**Screen:** Report page **23** for the requirement matrix, then page **24** or
the Design Explorer overview for the final sentence.

> Our submission delivers the Python automation workflow, open-source SPICE
> integration, circuit outputs and a calibrated transistor CTLE-plus-DFE
> implementation. The report maps each requested deliverable and electrical
> requirement to its supporting evidence.
>
> Full target coverage, analog PVT, extracted layout and complete receiver
> power remain the next steps. The contribution today is a working design
> product with measured results that an engineer can inspect, reproduce and
> challenge. Thank you.

## Shorten or extend without changing the claims

- For a 3-minute cut: omit the detailed Rs/Cs explanation, spend 25 seconds on
  the RL comparison, and show the selected-run behavior in one sentence. Keep the
  saved/live distinction and the finite-pattern limitation.
- For a longer version: open the bias-reference view, explain that it derives
  its bias from VDD, and show the exact transistor device sheet. Use report
  pages 9-17 for circuit implementation and independent measurement methods.
- If a generation is slow: stop narrating the wait, use **Enter judge mode**,
  and say, "I will continue with the saved completed run; the evidence and
  method are labeled on screen." Do not imply the wait produced that result.

## Questions you should be ready to answer

**Did RL discover the final transistor receiver?** No. The frozen policy study
uses the earlier characterized bank. The integrated receiver was developed and
calibrated later; those results are kept separate.

**Is the whole circuit fully compliant?** No full signoff claim is made. The
topology and calibrated nominal/link results are demonstrated; page 23 shows
which requirements remain unverified.

**What does 45/45 mean?** Five transistor corners, three supply values and three
temperatures, using fixed control fractions, code and phase on one constructed
7.5 dB channel. Each point recovers 64/64 scored bits. It is not 45 channels.

**Why do other pages say 315 cases?** Those are earlier generated CTLE/model
records: 45 PVT points times seven constructed channel-loss values, with
behavioral DFE scoring. They are not the newer transistor receiver campaign.

**Are the controls tuned at each corner?** Their fractions of VDD remain
0.70 and 0.185. Actual voltage follows VDD; there is no corner-specific
recalibration. Runtime tuning with the active DFE remains unverified.

**What does zero human intervention mean here?** The implemented request-to-
result flow runs automatically within its characterized paths. Engineers
selected the architecture, built the bank and calibrated the newer receiver.
The full open-ended autonomous-sizing objective remains incomplete.

**Is the reported area final?** No. 0.014715766 mm2 is a geometry subtotal,
not routed layout. External clock, control and common-mode generation are
also outside the reported receiver VDD power.

**Is the plain-language box an LLM demonstration?** This recording demonstrates
request parsing and validated numerical input. Do not describe it as an
LLM-backed tuning conversation unless that optional backend is actually used.

## Rehearsal record

The saved route was exercised at 1440 x 1000 and 1280 x 900 with all five
circuit selections, shared circuit canvas, four inspector modes, full-width expansion, comparison eye modes, target-editor independence,
judge target reset, generated-design PVT and run files. No new SPICE or
training was required for that rehearsal. The exact results are recorded in
the final submission HANDOFF entry. The video itself is to be recorded by the
team in its own voice.

A separate new 9 dB / 1.9 GHz adaptive-bank generation was also rehearsed:
315/315 cached conditions pass, with zero search/measurement calls and one
representative export SPICE call. It is separate from the zero-job saved-route
rehearsal and from the pinned 45-point transistor receiver evidence.

## Optional: show your completed 3 dB physical run (about 25 seconds)

**Screen:** Choose **3 dB / 1.9 GHz - physical CTLE** in **Selected design**.
Point to MODEL PASS, the actual measured response, and **315/315** coverage.
The CTLE opens first. Click **Compare eyes** to open **Compare circuits**. Circuit A shows the saved physical run; select **CTLE output**, then **Ideal 1-tap DFE**. The bank demo has no retained raw AC, so its waveform is explicitly unavailable. **Margin envelope** shows the conservative opening underlying the recorded dimensions.

> This is our completed three-decibel physical CTLE request. The result shows
> the actual measured response and all three hundred fifteen checked conditions:
> forty-five PVT corners across seven channel losses. This eye opening comes
> from this circuit's saved AC response with our ideal one-tap DFE model.
> These traces show the modeled signal; the displayed margin dimensions use
> a separate conservative cursor calculation.
> It measures about three hundred forty-two millivolts and zero point eight
> five nine UI. The separate transistor checkpoint keeps its own evidence.

The recorded response is **3.910 dB at 2.131 GHz**, accepted under the physical
export path's existing 1.5 dB / 0.3 octave target tolerances. Say "requested"
for 3 dB / 1.9 GHz and "measured" for these actual values. The waveform is a noiseless, finite-pattern model with ideal known-bit feedback.
The separate margin envelope supplies the recorded height and width. Neither
is a transistor transient measurement or BER test.
