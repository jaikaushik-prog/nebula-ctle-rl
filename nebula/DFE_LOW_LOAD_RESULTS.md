# Lower load helps simulated raw timing, but neither candidate passes

2026-09-06, Entry 111. The two owner-approved trials finished: **both fail**
the unchanged complete decision/hold gate and show terminal-voltage excursions
outside documented model ranges. Stopped after **2 calls / 2.621075 s**;
no PVT, selection, additional size, retry or integration.

## Results

Only the sixteen buffer/memory MOS change to the approved widths, each with
nf=1 and L=.15 um. The eleven comparator MOS retain their exact width-4
definition, including width-8 tail. All connections and stimuli are unchanged.

| Buffer/memory W | Raw correct | Held correct | Latest raw settling | DUT VDD power |
|---|---:|---:|---:|---:|
| 2 um | 32/32 | 14/32 | 45.5 ps | 0.953274 mW |
| 1 um | 32/32 | 14/32 | 40.5 ps | 0.776334 mW |

Every one of the 14 repeated bits passes; **every one of the 18 bit changes
fails** the complete held window. Unlike the earlier circuit that stayed low,
these simulated memory outputs now change to the new decision, but late.
For bit 6, a zero-to-one transition:

| Buffer/memory W | First set-input low sample | First correct complementary stored-one sample |
|---|---:|---:|
| 2 um | 111.5 ps | 164.5 ps |
| 1 um | 104.5 ps | 157.5 ps |

Times are relative to that bit's evaluation edge. The required hold window
starts at **110 ps**, so neither is a pass. Earlier Entry 107's width-4 chain
had worst raw delay about 57.5 ps and no successful stored ones. Reducing load
improves the simulated decision timing and produces larger buffer pulses,
but the complete path still does not meet the frozen timing. A single late
sample cannot replace the full-window test. These waveforms are exploratory,
not qualified physical timing evidence because the model-domain check fails.

## Voltage-domain findings

All named device nodes were captured on the same solver time axis. Signed
VDS, VGS and VBS are derived using each exact netlisted D/G/S/B connection.
The diagnostic preserves negative/reverse/off-state excursions separately
from excursions exceeding the published 1.95 V drain/gate magnitude.

- W=2: maximum absolute VDS/VGS **2.176608 V**, at comparator input device
  Xin1 VDS. First buffer NMOS VGS reaches approximately **2.154772 V**.
- W=1: maximum absolute VDS/VGS **2.227363 V**, at first buffer NMOS
  Xbuf_y1_n VGS. Comparator input VDS also exceeds 1.95 V.

These exceed the standard 1.8 V devices' documented SPICE model domains.
[SKY130 device details](https://skywater-pdk.readthedocs.io/en/main/rules/device-details.html).
They are NOT proof of physical damage or a substitute for reliability rules.
Signed per-device intervals, extrema and out-of-range sample counts are all
in the raw JSON. Counts span the full saved transient and count each
device/quantity separately; they are not unique time events or a failure rate.
No waveform clipping or transient-duration exemption is applied.

## Power, area and unchanged scope

External clock net / positive supplied average powers are **0.091879 /
0.427961 mW** for W=2 and **0.094861 / 0.444501 mW** for W=1, separate from
the table's DUT supply power. Ideal input-source energy is also in the JSON.
These are failed standalone prototype measurements, not complete receiver
power. MOS gate W*L subtotals are **0.000012 / 0.0000096 mm2**, not layout
area or S7 compliance. Full hardware DFE and full receiver verification stay
false. No RL, CTLE, Rs/Cs, behavioral DFE, dashboard, cached demo or PDF changes.

## Next decision

Stop this size family. The evidence now calls for an architecture and clock/
storage-interface review, including pulse regeneration, path depth and the
observed excursions, before any new circuit or sizing proposal. Retain the
original failed gates; do not move the hold window to turn a late transition
into a retroactive pass. Any proposed timing change must be explicitly
justified against the 200 ps bit period and causal feedback requirements and
approved before measurement, not treated as a bookkeeping fix.

## Evidence and verification

[Frozen plan](DFE_LOW_LOAD_PLAN.md) and
[raw results](product_audits/entry111_dfe_low_load_20260906/summary.json).
All **35 evidence hashes** verified; exact decks, logs, primary/buffer/all-node
traces, common-mode source log and source/plan snapshots retained. Raw
reanalysis reproduces the bit gates and voltage audit. The overlapping node
values also match across the three waveform files. Legacy DFE defaults remain
unchanged and all previous raw results stay reproducible.

Full suite: **2922 passed before / 2940 after**, 13 deselected, two unchanged
warnings, 302.48 / 296.01 s. Seventeen new tests failed before implementation;
focused DFE tests passed 102 before measurement and 103 after adding the
raw-result regression. All 18 new tests pass. No experiment or test job
remains running.

Professor-ready takeaway: "Lowering the comparator load improved simulated
decision speed, but bit transitions are still stored too late and voltage
excursions exceed the documented model range. We stopped both failed trials
instead of calling this a working transistor DFE."
