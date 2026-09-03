# Nebula Project Solution Overview

Date: 2026-09-03

## What problem are we trying to solve?

The competition asks us to build an automated framework that designs an
equalizer for a 5 Gbps PCIe Gen2 receiver.

The user should provide target specifications, such as:

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

1. The user enters the requested peaking and peak frequency.
2. The framework selects transistor and circuit values for a SKY130 CTLE.
3. The exact transistor-level circuit is simulated using ngspice.
4. The framework checks gain, peak frequency, Nyquist boost, noise, power,
   linearity, area, device saturation and output-swing compression.
5. The measured CTLE response is passed into the link model.
6. The link model applies the required one-tap DFE and calculates the vertical
   and horizontal eye opening.
7. The design can be checked across the complete 45-corner process, voltage
   and temperature grid.
8. The framework returns the measured results, exact SPICE netlist and a
   schematic image generated from that same netlist.

An optional natural-language interface allows a request such as "9 dB near
1.9 GHz" to be converted into the same validated design flow. The language
model is not allowed to change the circuit or invent measurement results.

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
measurements.

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
| Resulting measured specifications | Covered |
| One-stage CTLE with variable Rs and Cs | Covered |
| One-tap DFE | Covered in the link model |
| Noise, power, linearity and area checks | Covered |
| Horizontal and vertical eye opening | Covered by the statistical link model |
| Process, voltage and temperature checks | Covered over the 45 required corners |
| Lower online design effort than exhaustive search | Potentially covered: at most 8 measured settings instead of 512 |
| Zero human intervention during a design run | Covered |
| Optional LLM-based interaction | Covered |
| A useful and safe RL result on unseen conditions | Final Entry 89 evaluation is still pending |
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
- It produces a traceable netlist, schematic and measurement record.
- It compares RL with fixed selection, random search, grid search, CMA-ES and
  hidden-oracle limits.
- It preserves unsuccessful experiments instead of changing the test after
  seeing the result.

These features make the project much stronger than a demonstration in which a
neural network optimizes a synthetic formula.

## What is not completely solved yet?

### 1. Useful RL is not yet proven

The first RL approach produced only a very small improvement. The second
approach learned useful eye-quality improvements, but it reduced compliance
too much and was rejected by the registered safety gate.

Entry 89 is designed to repair that exact failure using oracle imitation and a
hard safety shield. All five training seeds are complete and frozen. On exposed
development data, the shielded policies retain every compliant fixed start and
improve mean quality by +0.1507 to +0.2214. The policies must still be evaluated
once on genuinely fresh midpoint conditions.

Until that final evaluation passes, we cannot honestly claim that RL is the
best working part of the product.

### 2. The strongest existing product path is not RL

The current user-facing automatic design command is strongest when it uses
analytic design, library retrieval and classical search. That path works, but
it is not the RL contribution requested by the problem statement.

If Entry 89 passes, its frozen controller must be integrated into the same
user-facing design command so that the demonstration clearly shows target
specifications entering an RL-based flow and a verified design coming out.

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

## How is a judge likely to see the product?

An analog or SerDes judge will probably see a technically serious automation
framework with unusually careful circuit verification. The direct ngspice and
SKY130 integration, PVT analysis, eye calculation, exact netlist output and
honest baselines are major strengths.

The judge's main question will be:

> Is reinforcement learning actually responsible for producing the final
> verified design, or is RL an experiment attached to a stronger classical
> design flow?

Today, that question is not completely resolved. The answer depends on Entry
89's fresh final test and whether the successful frozen controller is connected
to the front-door design command.

The judge may also ask whether choosing a tuning-bank setting counts as device
sizing. Our honest answer should be that the system contains both continuous
transistor sizing and RL-based configuration search, while the current rescue
experiment specifically tests the RL configuration controller.

## Honest overall assessment

As an analog automation product, the project is strong. It already contains a
working specification-to-netlist flow, transistor-level simulation, PVT
verification, link and eye analysis, schematic generation, classical
baselines and an optional natural-language interface.

As a proven RL-driven device-sizing product, it is not finished yet. The
remaining decisive work is:

1. Generate the fresh midpoint ngspice journal only after the frozen-policy
   commit.
2. Evaluate the frozen policies exactly once.
3. Confirm that compliance does not fall and mean eye quality improves by at
   least the registered amount.
4. If all gates pass, integrate the frozen RL controller into the user-facing
   design command and demonstrate the complete input-to-schematic flow.

If Entry 89 fails, the project still remains a strong analog automation
framework, but the report must present RL as an honest negative result and the
analytic/lookup/search flow as the reliable product.

## One-sentence summary

> We built a complete simulator-backed CTLE automation framework; the final
> unanswered question is whether the new safety-shielded RL controller can
> select a better compliant tuning configuration in fewer than eight
> measurements on genuinely unseen conditions.
