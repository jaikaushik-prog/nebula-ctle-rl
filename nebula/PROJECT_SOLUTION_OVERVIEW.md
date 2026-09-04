# Nebula Project Solution Overview

Date: 2026-09-04

## What problem are we trying to solve?

The competition asks us to build an automated framework that designs an
equalizer for a 5 Gbps PCIe Gen2 receiver.

The user provides the two variable target specifications, such as:

> I need 7 dB of high-frequency peaking near 1.8 GHz.

The framework should then choose the circuit values, simulate the circuit,
check the specifications, and return the final design without requiring a
human to manually try hundreds or millions of combinations.

The required circuit is a one-stage CTLE with variable source-degeneration
resistance and capacitance, followed by a one-tap DFE. The result must satisfy
the electrical and eye-opening specifications across process, voltage and
temperature variation.

## What is our solution?

Our project is a simulator-backed automatic CTLE design and tuning system.

The complete flow is:

1. The user enters only the requested peaking and peak frequency.
2. The framework selects transistor and circuit values for a SKY130 CTLE.
3. The exact transistor-level circuit is simulated using ngspice.
4. The framework checks gain, peak frequency, Nyquist boost, noise, power,
   linearity, area, device saturation and output-swing compression.
5. The measured CTLE response is passed into the link model.
6. The link model applies the required one-tap DFE and calculates the vertical
   and horizontal eye opening.
7. The RL product automatically checks all seven characterised channel losses
   across the complete 45-corner process, voltage and temperature grid: 315
   operating conditions. Channel loss is an external verification condition,
   not a user target.
8. The framework returns the measured results, exact SPICE netlist and a
   schematic image generated from that same netlist, and an RL adaptation
   dashboard generated from the same delivered 315-condition record. It also
   returns a complete 512-code architecture map: all attenuation/Rs/Cs target
   values, the selected A/R/C code, and the verification status of each block.

The natural-language interface allows a request such as "9 dB near 1.9 GHz"
to enter the same validated shielded-RL design flow. Its default parser is
deterministic and offline; an LLM is optional. Neither path can change the
circuit, widen the legal request range or invent measurement results. With
`--out`, it uses the same exporter as the numeric front door and writes the
netlist, schematic, dashboard, JSON record and grounded explanation.

A separate real-channel intake accepts Touchstone 1.x `.sNp` files without an
optional RF package:

```powershell
python -m nebula.channel_upload board.s4p --ports 1 3 --out channel_report
```

It hashes the exact file, validates the chosen port path and frequency span,
measures loss at 2.5 GHz, fits the current two-term channel model, reports its
residual and draws measured-versus-fit loss. It intentionally does not label
the uploaded file RL-verified: the frozen 512-setting eye bank was generated
for the constructed channel family, so arbitrary measured reflections and
phase need a new link characterisation before compliance can be claimed.

## What is the RL system doing?

The current configurable CTLE contains 512 possible tuning settings. Testing
all 512 settings for every new operating condition would be slow.

The RL controller tries to find a good setting using no more than eight
measured settings. It therefore acts as an intelligent search controller for
the configurable CTLE.

The latest RL method, Entry 89, has two parts:

1. **Oracle imitation:** On development data, the controller is first taught
   which local actions move toward a high-quality compliant setting.
2. **Safety shield:** The RL policy proposes settings to measure, but a
   separate simulator-backed verifier checks compliance. The final output is
   the compliant visited setting with the largest visible eye opening.

This separation is important. The RL policy proposes useful candidates; the
verifier and shield prevent an unsafe final selection. Every measurement and
verifier call is counted, and the controller is still limited to eight
measurements per operating condition.

Entry 89 is now connected to the product command:

```powershell
python -m nebula.design --peaking 9 --f-peak 1.9 --method rl-hybrid --out out
```

For each of the 7 channel losses and 45 PVT corners, the frozen deployment
policy proposes at most eight codes. It is not told the channel loss or PVT
label; it receives only the request, present code and measured eye history.
The safety shield checks those codes against the immutable ngspice
characterisation. If none is compliant, a classical lookup searches the 512
measured bank settings for that condition. The output is one tunable CTLE, its
315-condition code map, the representative TT configuration's exact SPICE
deck, measured specifications, an adaptive-code schematic and a 7 x 45 RL
adaptation dashboard.

The 512-setting architecture is `A x R x C = 8 x 8 x 8`. Its input
attenuator is physically netlisted with real PMOS switches and measured in the
SKY130 simulations. The Rs/Cs evidence consists of 64 separately drawn passive
geometries. Their final selector transistors and switch parasitics have not yet
been netlisted, so the architecture image marks that boundary prominently
instead of implying the complete switch matrix is tapeout-ready.

`--channel-loss` still exists as an explicitly optional diagnostic override
when a developer intentionally wants to inspect one characterised channel.

## Does the project cover the problem statement?

| Problem-statement requirement | Project status |
|---|---|
| Python and Anaconda framework | Covered |
| Direct SPICE integration | Covered with ngspice |
| Open-source PDK | Covered with SKY130 |
| Target specifications as input | Covered |
| Automatic design flow | Covered |
| Exact SPICE netlist as output | Covered |
| Human-readable schematic image | Covered |
| RL trace and RL-versus-fallback condition dashboard | Covered |
| Resulting measured specifications | Covered |
| One-stage CTLE with variable Rs and Cs | Functionally covered by 64 measured passive geometries; physical selector switches/parasitics are not yet netlisted |
| One-tap DFE | Covered in the link model |
| Noise, power, linearity and area checks | Covered |
| Horizontal and vertical eye opening | Covered by the statistical link model |
| Process, voltage and temperature checks | Covered over the 45 required corners at every characterised channel loss |
| Lower online design effort than exhaustive search | Covered experimentally: 5.579 mean measured settings instead of 512 |
| Zero human intervention during a design run | Covered |
| Natural-language interaction with optional LLM wording | Covered and connected to the shielded-RL product |
| Real Touchstone file intake | Covered for validated parsing, provenance and loss-model fitting; uploaded-channel RL/eye compliance is not yet claimed |
| A useful and safe RL result on unseen conditions | Covered: Entry 89 passed all R1-R10 gates and is integrated as `--method rl-hybrid` |
| Fabricated-silicon validation | Not covered; present evidence is simulator-backed |

## What is already strong?

The strongest part of the project is its engineering foundation:

- It uses transistor-level SKY130 device models rather than fake circuit
  numbers.
- It runs the real circuit through ngspice and parses the simulator output.
- It connects transistor-level measurements to a complete PCIe link and eye
  calculation.
- It checks process, voltage and temperature variation rather than reporting
  only a nominal result.
- It produces a traceable netlist, schematic, measurement record and RL
  adaptation dashboard, plus an honest 512-setting hardware/status map.
- It compares RL with fixed selection, random search, grid search, CMA-ES and
  hidden-oracle limits.
- It preserves unsuccessful experiments instead of changing the test after
  seeing the result.

These features make the project much stronger than a demonstration in which a
neural network optimizes a synthetic formula.

## What is not completely solved yet?

### 1. Useful shielded RL is proven at experiment level

The first RL approach produced only a very small improvement. The second
approach learned useful eye-quality improvements, but it reduced compliance
too much and was rejected by the registered safety gate.

Entry 89 repaired that exact failure using oracle imitation and a hard safety
shield. Its one-time test used 2,430 fresh midpoint identities after all five
policies and the ngspice dataset were separately frozen. Fixed compliance/q was
0.8226/0.5619; shielded RL averaged 0.8388/0.7169 in 5.579 measurements. The
quality improvement was +0.1550 with a paired 95% interval of
[+0.1508,+0.1593]. All five seeds and the deployment seed improved, and all
registered R1-R10 gates passed.

Pure unshielded RL is still unsafe: its mean compliance was only 0.6444. The
validated contribution is therefore the combined RL proposer plus simulator
shield, not the neural policy by itself.

### 2. The RL system is integrated, but it is not the whole solver

The user-facing command now exposes `--method rl-hybrid`. RL proposes the
short candidate path; the simulator-backed shield decides what is safe; and a
classical measured-bank lookup fills any corner where RL did not visit a safe
setting. This division must remain visible. Pure RL is not safe enough, and
the product never claims otherwise.

The original `--method auto` path remains the stronger route for continuous
transistor sizing. It uses analytic design, library retrieval and classical
search. The RL-hybrid route configures the already designed tunable bank.

### 3. The new RL controller tunes a pre-designed circuit bank

Entry 89 searches the 512 settings of an already designed configurable CTLE.
It changes the attenuation and Rs/Cs tuning codes; it does not create every MOS
width and length from scratch.

The wider framework can size continuous transistor parameters, but its best
continuous sizing methods are presently analytic or classical search methods.
A judge may therefore describe Entry 89 as RL-driven circuit tuning rather
than complete RL-driven transistor sizing. This distinction must be stated
honestly.

### 4. The evidence is simulator-backed, not silicon-backed

The safety shield can see full compliance because the simulator provides
noise, power, linearity, saturation, eye and PVT results. A physical receiver
would not automatically know all of those quantities.

Therefore, the correct claim is "simulator-backed automatic sizing and
tuning." It is not yet an on-chip adaptive calibration system.

### 5. Offline characterization is expensive

Once trained, the controller may need no more than eight measurements instead
of a 512-setting sweep. However, creating the training and verification tables
required many ngspice simulations.

The fair claim is that the cost is paid offline and reused across many future
design requests. The report should show both the offline cost and the much
smaller per-request online cost.

### 6. The complete edge of the requested S3 rectangle is not yet covered

A predeclared five-request product check used both corners of the stated S3
input rectangle and its centre. The 3 dB requests at 1.25 and 2.5 GHz, and the
7.5 dB centre request, passed all 315 conditions. The two 12 dB requests did
not: the existing bank had no compliant fallback at 7/315 conditions for
12 dB at 1.25 GHz and at 203/315 for 12 dB at 2.5 GHz.

The software refuses those requests cleanly rather than returning an unsafe
circuit. This is a circuit-bank coverage limitation, not an RL runtime error.
Closing it requires a separately approved expansion of the physical design
range or architecture; the project rules forbid silently widening device
ranges after observing a result.

### 7. The Rs/Cs code bank is not yet a transistor-level switch matrix

The product has measured all 64 Rs/Cs targets as separately generated passive
geometries, and the real PMOS-switched input attenuator is already present in
the simulation netlists. However, the physical switches that would select the
eight Rs and eight Cs values in one fabricated CTLE have not been designed or
simulated. Their on-resistance and parasitic capacitance could shift the
response. The product therefore emits a logical architecture/status drawing
and labels this gap rather than presenting it as completed silicon hardware.

### 8. Uploaded Touchstone data are profiled, not yet RL-verified

The intake reads the real S-parameter file and exposes how well or badly its
insertion loss matches the smooth channel model. The current RL table contains
eyes for seven constructed balanced-loss channels, not arbitrary uploaded
phase and reflection responses. Therefore, a channel upload produces a
provenance/audit report and never reuses the old 315/315 result as though it
belonged to the new file. Closing this gap requires re-evaluating the measured
CTLE bank through the uploaded channel response.

## How is a judge likely to see the product?

An analog or SerDes judge will probably see a technically serious automation
framework with unusually careful circuit verification. The direct ngspice and
SKY130 integration, PVT analysis, eye calculation, exact netlist output and
honest baselines are major strengths.

The judge's main question will be:

> Is reinforcement learning actually responsible for producing the final
> verified design, or is RL an experiment attached to a stronger classical
> design flow?

The fresh test proves that the RL proposer contributes useful candidates when
combined with the simulator shield. That frozen controller and its classical
fallback are now connected to the front-door design command, with their
separate costs and decisions written into `design.json`.

The judge may also ask whether choosing a tuning-bank setting counts as device
sizing. Our honest answer should be that the system contains both continuous
transistor sizing and RL-based configuration search, while the current rescue
experiment specifically tests the RL configuration controller.

## Honest overall assessment

As an analog automation product, the project is strong. It already contains a
working specification-to-netlist flow, transistor-level simulation, PVT
verification, link and eye analysis, schematic generation, classical
baselines and an optional natural-language interface.

As a proven RL-assisted tuning product, the core experiment and product
integration are successful. It is not a fully RL-driven device-sizing product.
The remaining decisive work is:

1. Decide whether to expand the circuit bank to close the unsupported 12 dB
   edge; this needs a human-approved range or architecture decision.
2. Update the final report and slides with Entry 89, the 315-condition product
   result and the honest upper-edge limitation.
3. Draw or document the complete switched Rs/Cs implementation; the emitted
   deck is the representative configuration, while `design.json` carries the
   315-condition code map.
4. Keep continuous transistor sizing in the analytic/classical front end and
   describe Entry 89 accurately as RL-driven configuration search.

The generated product example is in
`nebula/product_demo/rl_hybrid_9db_1p9ghz/`: `design.json` contains all 315
condition decisions and policy traces, `design.cir` is the exact representative
deck that ran, `design_schematic.png` is drawn from that deck, and
`rl_dashboard.png` visualises the delivered condition records without replaying
the policy or inventing a value.

## One-sentence summary

> We built a simulator-backed CTLE automation framework whose frozen RL
> proposer, safety shield and classical measured-bank fallback now turn two
> user targets into a 315-condition channel/PVT tuning map, exact SKY130
> netlist, measured specifications and schematic with no human choosing the
> codes, while refusing unsupported request edges honestly.
