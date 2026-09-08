# Transistor DFE work: first building block does not pass

2026-09-06, Entry 106. Rs/Cs switching was left unchanged, as requested.
The working CTLE product and its existing behavioural DFE are unchanged.

## What was built and tested

A 19-transistor SKY130 clocked decision circuit plus static decision-hold
memory, with external input and clock stimuli. All DUT devices are PDK MOS
instances, not a Python/behavioural comparator. This is NOT yet a full DFE:
there is no feedback summer or correctly phased previous-bit feedback register.

The [frozen plan](DFE_HARDWARE_PLAN.md) allowed three nominal sizes, followed
by 45 PVT checks only if one passed. All three failed, so the experiment stopped
after **3 calls / 2.423 seconds**. No PVT sweep, new size, retry, or integration.

| Input total width | Correct tested bits | DUT VDD power | Gate result |
|---|---:|---:|---|
| 4 um | 15/32 | 0.681107 mW | Fail |
| 8 um | 15/32 | 1.360216 mW | Fail |
| 16 um | 15/32 | 2.728493 mW | Fail |

At nominal 1.8 V / 27 C / TT, the applied input common mode was 1.364486680 V,
from the hash-verified physical CTLE operating point. Differential levels were
+/-50 mV, with a 5 GHz clock. All 15 zero bits passed; all 17 one bits failed.
The independent stimulus check passed; ngspice logs contain no detected silent
failure and complete finite waveforms were saved. This is a hardware-block
functional failure, not proof that a hardware DFE is impossible in SKY130.

The largest size increased power without repairing the decision failure.
For 4 um, 95 ps after the evaluation edge for scored bit 6 (expected one),
raw x/y were 1.028096/0.646466 V and held q was 0.036314 V: wrong polarity,
not a valid one. For bit 4 (zero), x/y were 1.531231/0.135135 V and q was
0.017656 V, correctly low. The held output preferentially remains zero.

## Interpretation and next decision

The raw latch nodes directly drive the static memory's transistor gates.
State-dependent loading from that connection is a plausible cause of the
observed preferred state, **not a proven cause yet**. The architecture reference,
[Razavi's StrongARM article](https://www.seas.ucla.edu/brweb/papers/Journals/BR_Magzine4.pdf),
shows buffering between dynamic decisions and static storage. This prototype
used direct active-low NAND storage instead; it must not be described as a
verified implementation of the complete reference circuit.

Recommended next bounded experiment: isolate the dynamic latch from the memory
with transistor buffers and test both input polarities before feedback work.
Proposed, NOT run or approved here: two cascaded inverters per output to retain
active-low polarity, each inverter's NMOS and PMOS total width equal to that
trial's existing 4/8/16 um width, length 0.15 um and 2 um fingers. Keep the
decision/hold devices, clock, input and measurement windows unchanged. Three
nominal trials, then the same fixed smallest passing design at 45 PVT points:
48 calls maximum, stopping after three if none pass. These are starting sizes,
not an assertion of optimum buffering. Obtain the owner's sizing decision and
freeze the new plan before measurement.
Do not keep enlarging every device or promote these failed sizes into the product.

After a decision/hold block passes, a complete DFE still needs causal previous-
bit memory, feedback summing and tap control, then loaded CTLE/DFE transient
checks, all-corner timing/eyes, mismatch/dynamic noise and total power/area.

## Power and area honesty

The table is DUT VDD power, NOT full-receiver power. Ideal clock net supplied
power was respectively 0.090495, 0.184655 and 0.371975 mW; integrating only
positive supplied clock power gives 0.427559, 0.804091 and 1.144760 mW.
Neither is a fabricated clock-generator measurement. Input drivers are ideal.

MOS W*L subtotals are 0.000012, 0.000024 and 0.000048 mm2. These exclude
diffusion, wells, contacts, routing, clock circuitry and the missing DFE blocks.
Full area remains unknown. No full S2/S5/S6/S7/S8/S9 hardware pass is claimed.

## Reproducibility

- [Raw evidence and summary](product_audits/entry106_dfe_slicer_run_20260906/summary.json):
  three exact decks, logs, waveforms, per-bit results and source snapshots.
- Thirty evidence SHA256 entries; the regression reparses every waveform and
  checks every hash. Synthetic unit-test traces never enter this evidence.
- An earlier preflight attempt made zero SPICE calls: Windows backslashes in
  the older manifest did not match forward-slash lookup keys. Original snapshots
  are preserved in `entry106_dfe_slicer_20260906`; separator-normalisation tests
  now catch this while refusing hash mismatches and conflicting aliases.
- Full regression: **2837 passed before / 2861 after**, 13 deselected and two
  known warnings. After-run 355.09 s; all 24 new tests pass. No code or measured
  waveforms changed after the acceptance run; the last two tests add alias
  conflict and stored-evidence reconstruction checks.

Professor-ready takeaway: "We added and measured a real transistor decision
and memory prototype. Its nominal bit test failed, so we stopped before corner
validation and kept it out of the product. The software DFE remains behavioural
until the hardware feedback loop itself is measured and passes."
