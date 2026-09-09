# Connected transistor CTLE + 1-tap DFE: three-channel verification

Entry 126 measured 2026-09-09 after verified checkpoint `f2e0519`; its
scientific source was frozen in `14bcdaa`. All 95 registered calls ran once,
without retries. Trial time was 1522.135503 s, excluding prerequisite hash
verification and later archival. Raw evidence is in
`product_audits/entry126_dfe_timing_20260909/`.

## What now works

The recovered physical CTLE, CML summing stage, transistor decision/hold
pair and transistor feedback DAC pass **135/135 declared channel/PVT cases**
across three constructed channel losses. Every case decodes all 64 scored
master, held and previous-bit decisions and passes the registered sampled-eye,
finite-aperture, VDD-power and new-DFE signed-terminal gates.

One transistor geometry and DAC code 2 are used throughout. The high-loss
channel uses an external sampling clock delayed by another 0.5 UI (100 ps);
there is no per-PVT retuning. This is a working connected transistor-level
feedback demonstrator, not a fabricated clock-recovery system.

| Channel loss at Nyquist | External timing offset | PVT passes | Minimum sampled eye | Minimum positive-eye aperture | Maximum VDD power |
|---|---|---|---|---|---|
| 3 dB | 1.0 UI | 45/45 | 191.307 mV | 0.755 UI | 12.526228 mW |
| 7.5 dB, reused Entry 125 | 1.0 UI | 45/45 | 111.169 mV | at least 0.635 UI | 12.523549 mW |
| 12 dB | 1.5 UI | 45/45 | 133.818 mV | 0.710 UI | 12.522617 mW |

These are finite, noiseless waveform apertures, not BER contours or proof
that every shifted sampling phase works. The narrower aperture above 100 mV
is at least 0.735 / 0.555 / 0.485 UI for the three rows, respectively.
External-clock positive supplied power is separate, at most 0.128404 mW
across the two new sweeps. Physical clock drivers are not included in VDD
power. Geometry remains 0.007961241107 mm2, an active-device/passive geometry
subtotal rather than a routed layout area.

## Why the timing change matters

The retained Entry 124 12 dB trial failed at the original sampling time.
In Entry 126, the 1.25 UI screen gets all 64 bits right but only 50.858 mV
sampled eye, so it correctly FAILS the complete gate. The 1.5 and 1.75 UI
screens pass; the frozen selection rule chooses 1.5 UI because it produces
the larger eye, 226.205 mV versus 164.751 mV. No failed screen is dropped.

At the selected TT timing, minimum-current code 0 gives 219.232 mV and
reversed code 2 gives 139.077 mV. The selected code 2 is better than both,
as preregistered. Code 0 still has residual feedback through the physical
discharge devices; it is NOT a feedback-disabled baseline. The old Entry 124
disabled-feedback comparison remains separate.

All 95 new calls pass the exact signed-voltage audit for every new DFE MOS.
The whole-circuit audit still exposes reverse-Vds operation in the legacy
bidirectional PMOS input attenuator; this is not whole-circuit model-domain
or reliability signoff. No voltage gate was relaxed.

## Evidence and remaining integration

Entry 126 contributes 90 new PVT simulations plus five screening/control
calls. The reused primary-channel 45-PVT set belongs to Entry 125's separately
billed 57-call experiment. Do not describe this as 315/315, arbitrary-channel
coverage, a BER demonstration, or a new frozen-RL result.

Rs/Cs are still fixed. Entry 127 next characterizes an official voltage-
tunable capacitor model before any configurable-passive CTLE insertion.
Loaded CTLE noise/HD3, passive tolerance, mismatch, realistic clock/control/
common-mode generation, longer histories and extracted layout remain outside
these signal-function gates. The original reports and production registry
are unchanged; their older fixed-circuit results do not transfer automatically.

Original manifest: 605 files. Summary SHA-256:
`1f7b35bdd5fdfa00c29919ce46977a1a72c77b79c0841fa51d4e346fb37740a9`.
Manifest SHA-256:
`e5a52225a37ba62f4b1347599fd2640b1102d707f64b75657f4e4f978d0eb302`.
Byte-verified gzip siblings preserve every adaptive sample; raw originals
remain local. Separate regression tests replay frozen membership, failed
screens, exact decks, waveform metrics, aperture and terminal audits.
The 190 archives preserve 8,117,418,400 raw bytes in 2,305,436,700 compressed
bytes; the largest individual archive is 15,292,483 bytes.
