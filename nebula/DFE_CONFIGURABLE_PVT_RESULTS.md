# Entry 133: configurable transistor CTLE + DFE passes 45/45 electrical PVT points

The same connected physical circuit passes all 45 sampled process, supply
and temperature points on the declared 7.5 dB constructed channel. Every
case decodes all 64 scored bits correctly. No geometry, control fraction,
DFE code or clock phase is retuned between corners.

The hardware is the Entry 132 N500/no-fixed-MIM network: physical poly/NMOS
resistance control and official SKY130 varactors, connected to the transistor
CTLE, physical bias reference, CML summer, decision memory and feedback DAC.
R control stays at .7 VDD, C control at .165 VDD; DAC code 2, normal sign,
external clock phase 1 UI. The original standalone nominal setting measures
8.909067327 dB / 1.857653018 GHz. Those AC numbers are not newly measured
loaded-PVT peak specifications.

## Measured result

- 45/45 accepted unique points: TT/SS/FF/SF/FS x .95/1/1.05 VDD x 0/27/125 C.
- Minimum sampled eye: **109.757616 mV**, FS/.95/125 C, above the 100 mV gate.
  This is only 9.757616 mV of margin at that sampled corner.
- Minimum positive-eye width: **.630 UI**, FS/.95/0 C. Minimum width above
  100 mV: **.555 UI**, FS/.95/125 C. These are finite noiseless waveform
  apertures, not BER contours.
- Maximum CTLE + reference + transistor DFE VDD power: **12.524099 mW**,
  FF/1.05/125 C, below 15 mW. External-clock positive supplied power is
  separately at most .128163 mW; external R/C-control positive power is at
  most 17.052511 nW. Physical generators for those external sources are not
  implemented or included in the VDD result.
- All 45 strict signed new-DFE transistor audits, whole-circuit magnitude/
  body envelopes and physical tuning-control envelopes pass.
- Nominal TT replay exactly reproduces Entry 132 within the registered
  tolerances; every scientific source and all 319 external PDK dependencies
  remain unchanged.

The bilateral Rs switch reverses current: its drawn-terminal signed Vds
spans -.067479 to +.064297 V across this sweep. Its separate strict signed
audit therefore remains false at all 45 points. This finding is preserved,
not clipped or terminal-swapped; the passing magnitude/body envelope is not
foundry signed-domain or lifetime signoff. Legacy PMOS qualifications remain.

Control source nodes span .381274..606653 V. Maximum scored-window R-gate
ripple is 1.308920 mVpp; C-control ripple is .857147 mVpp. These are settled
fixed-control observations, not runtime reconfiguration settling measurements.
Geometry subtotal remains .014715765982 mm2, not routed layout area.

## Evidence and presentation scope

This closes the registered primary-channel electrical PVT gate for the NEW
configurable CTLE + transistor DFE, independently of the older fixed-passive
135/135 result. Nine tuning identities were demonstrated separately on one
standalone physical circuit in Entry 131; this sweep does not establish all
nine with DFE loading or the full requested tuning rectangle.

PVT AC peak/frequency, loaded noise/HD3, other channels, runtime control
changes, arbitrary data/BER, passive tolerance, mismatch and extracted layout
remain unverified. External clock, common-mode and control generation remain
testbench sources. Existing production exports, registry, PDFs and frozen RL
claims have not been replaced or extended by this experiment.

Run from `3e4dfcedc19afd8202458ed1155138c6bb4a2134`: exactly 45 calls,
no retries, 2065.701124 s including 5.440404 s prerequisite verification.
All five initial screens pass, then all remaining 40 unique points run once.
Raw waveforms, terminal voltages, decks, logs and failures from previous
experiments are preserved. Lossless gzip siblings retain original trace bytes.
The 90 archives preserve 4,296,306,960 raw bytes in 1,212,259,908 compressed
bytes; the largest is 16,092,813 bytes. All raw originals remain local.
The regression tests verify the complete bundle and replay all 45 raw cases.
Validation: 146 focused tests passed; full suite 3253 passed, 13 deselected,
two known warnings in 739.41 s (before-change baseline: 3207 passed).

Evidence: `product_audits/entry133_dfe_configurable_pvt_20260910/`.
Summary SHA-256: `17887e5aa9e10fe7692e0c12fe103d7a4588432061f4dae9be4286062081f09d`.
Original manifest: 336 entries; SHA-256
`01083693b0c963b62789d96584470d3918ab844c313debfc21ea3daa0bfd1585`.
