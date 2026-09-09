# Entry 132: tunable physical CTLE + transistor DFE passes the first connected gate

The selected N500/no-fixed-MIM tuning network is now connected to the
unchanged transistor CML summer, master/slave decision memory, feedback DAC
and four tail-discharge devices. The same physical control values as the
measured near-9 dB/1.9 GHz standalone point are used: R=.7 VDD, C=.165 VDD.
Rs and Cs are physical poly/NMOS and official varactor devices, not ideal
variable replacements or per-request fixed-passive substitutions.

At TT/1.8 V/27 C on the declared 7.5 dB constructed channel, phase 1 UI and
normal DAC code 2 pass all registered connected gates:

- 64/64 master, held and previous-bit checks.
- Sampled eye 223.974919 mV, positive-eye width .690 UI; width above 100 mV
  is .650 UI. These are finite noiseless waveform metrics, not BER contours.
- CTLE + physical reference + transistor DFE VDD power 9.263703 mW.
  External-clock positive supplied power is separately .108293 mW; external
  R/C-control positive supplied power is 1.415724 nW. Drivers are not built.
- Strict signed new-DFE transistor checks and the whole-circuit magnitude/
  body envelope pass. Varactor source/control envelope passes at all samples.

Normal feedback improves sampled eye over minimum-current code 0 by
17.372250 mV (206.602668 mV control eye), and over reversed code 2 by
98.574487 mV (125.400432 mV control eye). Code 0 is NOT feedback-disabled:
the physical discharge devices leave residual feedback. This comparison
demonstrates useful physical feedback at the declared operating point.

Phases 1, 1.25 and 1.5 UI pass; 1.75 UI fails with 28/64 correct bits and
-264.396607 mV sampled eye. That failure is retained. Phase 1 is chosen by
the preregistered largest-eye rule. The preceding full-library fixed-circuit
calibration reproduces the old 237.637196 mV/64-bit result exactly.

Source nodes span .473276..527907 V. Gate/control ripple in the scored window
is .378738 mVpp for R and .626993 mVpp for C. Geometry subtotal including the
new tuning network and transistor DFE is .014715765982 mm2, not routed area.
The bilateral Rs MOS has signed Vds from -.050453 to +.046570 V; exact signed
findings remain visible and are not clipped or swapped. The passed magnitude/
body envelope is not foundry signed-domain or lifetime signoff. Legacy PMOS
qualifications remain, and passive nonlinear/leakage verification is unchanged.

This is ONE nominal target/channel point. The old fixed-passive 135/135 result
does not transfer to this new topology. Other tuning targets with DFE loading,
new PVT, runtime control settling, loaded noise/HD3, BER and layout are not yet
verified. Entry 133 separately preregisters fixed-setting PVT. Both existing
PDFs and the frozen RL experiment remain untouched.

Run from 5360e9f: seven calls, no retries, 382.673750 s including 47.852153 s
prior-evidence verification. Source/PDK hashes are unchanged. Original
manifest has 104 entries; 14 lossless gzip siblings preserve 658,278,760 raw
bytes in 185,722,916 compressed bytes. Largest gzip is 16,024,884 bytes.
Raw originals are retained locally.
Summary SHA-256: `73f15bc9b236f1ee404ed2a40ce667ad2f78e9963c78a611f8909eade81e879a`.
Original manifest SHA-256: `cf349cc4fc451e16ffe99348a9be7e0ee8805ad02c08497e7e8e1070bae06e46`.
Evidence: `product_audits/entry132_dfe_configurable_20260910/`.
