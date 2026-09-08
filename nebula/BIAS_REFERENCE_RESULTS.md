# Physical Iref and bypass capacitor: first hardware prototype

6 September 2026, Entry 103. **Implemented and measured as a separate prototype;
not integrated into the RL product. Full receiver compliance is not established.**

Follow-up: [Entry 104b distortion/eye validation](BIAS_VALIDATION_RESULTS.md)
now passes 315/315 electrical model cases. The measurements below remain the
original Entry 103 results; full receiver area/hardware is still unverified.

## What changed

The old tail transistors and diode-connected NMOS reference were already real
SKY130 devices. The source feeding that reference was an ideal current source.
It is now replaced, in the prototype, by two SKY130 PMOS transistors and one
SKY130 poly resistor. One PMOS and the resistor establish the current; the
second PMOS mirrors it into the existing NMOS reference/tail network.

The old ideal 10 pF bypass is replaced by a PDK MIM capacitor. The dimensions
are exported explicitly, not inferred from a capacitance-only symbol.

- Both added PMOS: total W = 25.2069 um, L = 0.5 um, nf = 1.
- Bias resistor: W = 1 um, L = 5.34 um, m = 1; nominal model resistance
  2072.198448 ohm. It was derived from one isolated nominal diode-PMOS
  measurement, not tuned across corners.
- MIM bypass: W = L = 70.545 um, m = 1; nominal model capacitance
  9.999453162 pF, against the 10 pF target.

One calibration current source exists only in the isolated measurement fixture.
There is **no ideal Iref or ideal Cbyp in the resulting CTLE prototype**.
Supply, differential-input stimulus and input common mode are still testbench
sources; common-mode generation has not been implemented.

## Fresh results, unchanged hardware across 45 corners

Five MOS process corners x three supply values x 0/27/125 C. Passive process is
typical, as in the earlier 45-point audit; independent passive corners are not
covered. Same dimensions and settings throughout, no retuning or retries.

| Measurement | Nominal TT / 1.8 V / 27 C | Range across 45 points |
|---|---:|---:|
| Actual reference current | 222.385 uA | 165.885-301.412 uA |
| Peaking, peak relative to DC | 8.834174 dB | 7.618983-9.666630 dB |
| Peak frequency | 1.768990 GHz | 1.548007-1.891556 GHz |
| Input-referred integrated noise | 0.589729 mV RMS | 0.522836-0.768042 mV RMS |
| CTLE + reference VDD supply power | 6.965787 mW | 5.006975-9.802119 mW |

All 45 points meet the broad S3 peaking/frequency limits, positive Nyquist
boost, S5 noise and S6 measured VDD-power limit. **This is not an all-spec pass
or a verification of the requested target tolerance.** No new HD3 or link-eye
measurement was included in this bounded first test. Old fixed-490 HD3/eye
results cannot be transferred to the changed circuit.

The nominal resistor branch produces 226.684 uA; the mirror output produces
222.385 uA versus a target of 226.681 uA. The approximately 1.9% output mismatch
is observed, not corrected away by an ideal source. Current varies roughly
-27% to +33% relative to the nominal sizing target across PVT. This simple
reference is therefore **not temperature compensated or supply independent**.

A single nominal 20 ns supply ramp, with externally supplied common mode
ramping alongside it, reaches nbias = 0.7709919 V at 200 ns versus the DC
0.7709919216 V. That is one startup diagnostic, not startup qualification across
PVT/ramp rates or verification of a real common-mode generator.

## Area: the omitted capacitor matters

| Counted geometry | mm2 |
|---|---:|
| Previous fixed-490 body/plate + MOS-gate subtotal | 0.002847367 |
| Added bypass-capacitor plate | 0.004976597 |
| Added PMOS gates + bias-resistor body | 0.000030547 |
| New geometry subtotal | **0.007854511** |
| Full receiver layout area | **Unknown** |
| Statement's maximum | 0.05 |

The bypass capacitor is larger than the entire previously counted subtotal.
This corrects a material omission. Still, geometry sum is not placed/routed
cell area: contacts, diffusion, wells, guards, routing and spacing are absent;
overlap between layers is not modelled either. DFE/slicer/clock hardware,
physical Rs/Cs selectors/control and common-mode circuitry remain absent.
CLp/CLn remain assumed external loads. No invented overhead multiplier is used.

Existing PDK/model limitations still apply: ngspice ignores some generic-poly
resistor voltage-coefficient parameters, and this two-terminal MIM model does
not include bottom-plate-to-substrate parasitics. PDK device instances are more
physical than ideal sources, but are not a substitute for extracted layout.

The area ceiling need not be nearly exhausted by every successful design. But
the current incomplete estimate cannot establish compliance with that ceiling.

## DFE and PVT assumptions for the team

For a fully transistor-level receiver claim, implement the 1-tap DFE feedback,
decision/storage and necessary clock circuitry, and count their power and area.
The statement does not explicitly specify DFE modelling fidelity; using a
behavioural DFE is a scoped modelling result, not completed receiver hardware.
We will not treat its hardware cost as zero.

Different Rs/Cs codes across PVT can be a legitimate calibration strategy.
They are not automatically required: some fixed hardware can meet its limits
across corners. More importantly, different drawn resistor/capacitor geometries
in separate simulations do not constitute a physical tuning system. Adaptive
claims need one implemented switchable bank and a way to choose its codes.
So the organiser question should be about allowed recalibration of the same
hardware, not whether a resistor can magically be redrawn with temperature.

## Evidence and next step

Plan: [BIAS_REFERENCE_PLAN.md](BIAS_REFERENCE_PLAN.md).
Implementation: [bias_reference.py](device/bias_reference.py).
Raw experiment: [Entry 103](product_audits/entry103_physical_bias_20260906/).
Authoritative parsed results: [summary_reparsed.json](product_audits/entry103_physical_bias_20260906/summary_reparsed.json).

Exactly 47 SPICE invocations completed in 13.766 s: one calibration, 45
DC/AC/noise checks and one startup run. The first reader mistakenly expected
`vdd#branch` instead of the printed `i(vdd)`, so its original journal reports
parser failures. That instrument error was reproduced by a failing unit test,
fixed, and all saved raw logs/AC data were reparsed with **zero new simulations**.
Original failure records and the original instrument snapshot are retained;
the reparse has separate filenames and hashes. No failed simulator row was
replaced, no circuit was changed after measurement, and no tolerance was relaxed.
Independent integrity checks found zero raw-hash mismatches and one common
circuit signature across all 45 rows; the original instrument snapshot matches
the preregistered source hash exactly.

Next: fresh HD3 and link-eye verification of this exact physical-bias circuit,
then evaluate remaining hardware and independent passive/mismatch variation.
Keep the current product and frozen RL evidence unchanged until integration
has its own measured acceptance gate. The existing competition PDF describes
the earlier implementation and has not been silently updated.

Software verification: full regression **2,812 passed**, 13 deselected, two
known warnings, versus 2,798 passed before the change. No training, simulation
or test process remains running; no commit or push was performed.
