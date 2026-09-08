# Targeted buffer sizing: no complete decision/hold pass

2026-09-06, Entry 108. The four owner-approved combinations were measured and
the stopping rule was followed. **No candidate passes; no PVT sweep or product
integration.** Rs/Cs, CTLE, RL, dashboard, cached demo and report are unchanged.

## The four measured results

P1 is the first buffer-stage PMOS width; N2 is the second-stage NMOS width.
Both differential paths use the same pair. The decision core and memory stay
at the Entry 107 4 um geometry, with its 8 um tail. All lengths remain .15 um.

| P1 / N2 (um) | Raw correct | Held correct | Both correct | DUT VDD power |
|---|---:|---:|---:|---:|
| 8 / 8 | 32/32 | 15/32 | 15/32 | 1.001361 mW |
| 8 / 16 | 32/32 | 15/32 | 15/32 | 0.948090 mW |
| 16 / 8 | 28/32 | 15/32 | 14/32 | 1.016568 mW |
| 16 / 16 | 28/32 | 15/32 | 14/32 | 1.004919 mW |

**4 SPICE calls / 3.990993 seconds**, versus the approved maximum 49. All four
instrument checks pass: complete finite traces, correct source waveforms and
valid buffer traces. All 15 zero bits satisfy the hold window; all 17 one bits
fail it. The 16 um first-stage PMOS also makes four raw decisions fail the
original 88-98 ps check window. One of these is a zero, hence 14 rather than
15 bits satisfy BOTH requirements. We did not move the timing window.

## What changed, and what did not improve

The 8/8 combination makes the memory output briefly reach **1.267450 V**, so
it is no longer accurate to say that every tested circuit remains low at
every instant. But that transient high does NOT satisfy the stored-bit gate:
all its one bits still fail the required 110-190 ps hold window. The other
three combinations have maximum q only 0.053705, 0.321515 and 0.025527 V.

For the same bit 6 used in the prior diagnosis:

| P1 / N2 | First buffer peak bx1 | Minimum set input bx | Raw final stable time |
|---|---:|---:|---:|
| 8 / 8 | 0.679213 V | 1.713120 V | 67.5 ps |
| 8 / 16 | 0.516260 V | 1.729977 V | 67.5 ps |
| 16 / 8 | 0.455129 V | 1.752580 V | 89.5 ps |
| 16 / 16 | 0.354537 V | 1.757690 V | 89.5 ps |

The earlier equal-width buffered case reached bx1=0.895247 V for this bit.
Here, increasing first-stage PMOS width degrades the raw decision timing, and
increasing second-stage NMOS width reduces the first buffer's output excursion.
These observations are consistent with loading competing against drive strength;
they do not independently measure every capacitance or prove a unique cause.
The simple stronger-drive proposal did not solve the memory interface.

## Next decision

Stop this width family. Reassess the number of buffer stages, their input
loading and the storage interface before another sizing grid. In particular,
the next proposal should investigate a lower-load/shorter path rather than
continue increasing widths. Architecture and new dimensions need an explicit
approved plan; no next hardware experiment is launched by these results.
Before choosing that revision, separately verify the existing memory using
clean full-swing test inputs and isolate the buffer's load/timing contribution.
Those would be bounded diagnostic tests, not assumed fixes or extra runs
silently taken from this completed experiment's unused allowance.

Only after a complete nominal and PVT decision/hold pass should the causal
previous-bit register, feedback summing and tap control be added and measured
with the actual CTLE. Dynamic noise, mismatch, clock generation, loaded eyes
and full receiver power/area remain separate unfinished verification.

## Evidence and scope

- [Raw summary and per-bit results](product_audits/entry108_dfe_drive_20260906/summary.json).
  All 44 evidence hashes verified; exact decks, logs, both waveform files,
  source common-mode provenance and source/plan snapshots are retained.
- [Frozen plan](DFE_DRIVE_PLAN.md): unchanged input, 5 GHz clock, 32 scored
  bits, VDD/2 logic threshold and raw/held timing windows. No extra trial,
  retry, re-selection or relaxed gate. Old experiments remain reproducible.
- Geometry subtotals are 0.0000192 / 0.0000216 / 0.0000216 / 0.0000240 mm2,
  from MOS W*L only, including all 27 MOS. Full layout area remains unknown.
- The table's power is the failed DUT's measured VDD power, not a functional
  receiver's power. Separate external-clock net/positive supplied power and
  ideal-input-source power are in the raw JSON. No full S6/S7 pass is claimed.
- Full software suite: **2879 passed before / 2896 after**, 13 deselected and
  two unchanged warnings. Before 279.61 s, after 298.44 s. All 17 new tests pass;
  focused group 59 passed. No experiment or test job remains running.

Professor-ready takeaway: "The targeted drive-strength experiment did not
produce a valid stored bit. It showed why a larger buffer is not automatically
faster for the complete path. We retained the failures and stopped before PVT
or integration rather than claiming a working transistor DFE."
