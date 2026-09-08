# Entry 106: transistor DFE, first decision/hold gate

Frozen 2026-09-06 before measurements. Owner: leave Rs/Cs switching alone;
work on transistor-level DFE only. This takes the previously proposed bounded
4/8/16 um slicer experiment, not a new CTLE or RL parameter range.

## What this stage does

Build a SKY130 MOS-only StrongARM decision circuit and static NAND SR hold.
Architecture reference: B. Razavi, [The StrongARM Latch, 2015](https://www.seas.ucla.edu/brweb/papers/Journals/BR_Magzine4.pdf),
Figures 1(b) and 4. A dynamic decision is invalid during precharge; a separate
static memory must retain it. This is a building block, not yet a causal
one-tap feedback path or a completed transistor DFE. No reference bits drive
the DUT's memory. External input and clock sources are testbench stimuli.

## Fixed experiment, no outcome-driven extension

- Input total widths 4, 8, 16 um, length 0.15 um (previous proposal).
  One common width also sizes regenerative and precharge devices and NAND
  devices. Tail width is twice the common width, serving both input branches.
  These fixed starting ratios are an unoptimised prototype, not sizes claimed
  from the paper. Finger width 2 um; W is TOTAL width, not width per finger.
- Three TT/1.00/27 C runs. Choose the smallest passing width, or STOP if none
  pass. Then test that ONE fixed width at the 45 specified PVT conditions.
  At most 48 calls, no retries, enlargement, alternate architecture or
  per-corner sizing. A PVT failure remains a failure.
- Input common mode comes from the matching Entry 105 physical CTLE corner's
  measured output operating point. Verify the stored evidence hash before use.
  Ideal sources impose this common mode: this is NOT a connected CTLE test.
- 5 GHz clock / 200 ps UI from S1, not a 2.5 GHz clock. Clock starts at 300 ps,
  with 2 ps rise/fall and 96 ps high plateau (100 ps evaluation including edges).
  Max transient step 1 ps. Input changes at UI boundaries with 2 ps ramps.
- Differential input levels +/-50 mV, anchored to the S8 100 mV vertical
  opening. This is a deterministic sensitivity stimulus, not an eye or noise
  test. First four bits warm up; 32 scored bits combine all adjacent binary
  histories with seeded data (`LinkConfig.seed`, default 1).
- Decode at VDD/2. During each final 10 ps before precharge, raw outputs must
  have complementary correct polarity. During 10-90 ps after precharge the
  SR output must hold the correct bit and its complement. No late-decision
  pass, end-of-file-only test, polarity auto-flip or unclocked/stuck-output pass.
  Record minimum margins and final stable decision time; no extra S3-S8
  threshold or reward change. Validate input and clock against the stimulus.
- Integrate DUT VDD power and separately report net/positive supplied clock
  power after warmup. No ideal clock power hidden in a full-receiver claim.
  Count MOS gate geometry only, not fabricated layout area.

## Evidence and scope

Tests first, including deliberately wrong polarity, held/stuck decisions,
missing clock, truncated/nonfinite data and wrong units. Store every deck,
waveform, log, configuration, source snapshot and hashes, including failures.
Baseline full regression: 2837 passed, 13 deselected, two known warnings.

Rs/Cs, CTLE, bias reference, bank, rewards, frontend and old report unchanged.
Even a pass leaves feedback summing, a correctly phased previous-bit register,
tap setting/calibration, loaded CTLE kickback, clock generation, mismatch,
dynamic noise, closed-loop eyes, receiver power and layout area unverified.
Further hardware stages require an explicit bounded plan; do not label the
existing behavioural DFE as hardware or promote a block test to S2/S5-S9 pass.
