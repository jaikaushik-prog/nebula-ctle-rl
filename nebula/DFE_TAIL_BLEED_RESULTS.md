# Connected transistor DFE recovery: Entry 125

Measured 2026-09-09 after freeze commit `14bcdaa`. Evidence is in
`product_audits/entry125_dfe_tail_bleed_20260909/`.
57 real SPICE calls in 988.869287 s; no retries or per-corner tuning.

## Result

One fixed physical CTLE + summer + decision/hold + feedback-DAC circuit now
passes **45/45** registered primary-channel PVT cases, including all 64
scored master/held/previous-bit checks and the new finite-pattern eye-width
gate. All 57 calls pass the exact signed voltage audit for every new DFE
transistor. This closes Entry 124's measured inactive-branch voltage failure
without changing its voltage limits or rewriting its failed evidence.

The fix is four real SKY130 NMOS discharge devices, W=0.42/L=4 um, nf=1,
connected from the four DAC tail nodes to ground and biased by the existing
physical reference. Both registered L=4 and L=2 candidates passed screening;
the frozen rule chose the longer, weaker device. No original CTLE, CML or
DAC transistor was resized, and no ideal current source was added.

Across the 45 points at the 7.5 dB constructed channel:

- Minimum sampled eye: 111.169499 mV.
- Minimum positive-eye aperture: at least 0.635 UI.
- Minimum aperture with height above 100 mV: at least 0.555 UI.
- Maximum combined CTLE/summer/latch/DAC VDD power: 12.523549 mW.
- Maximum external-clock positive supplied power: separately 0.128166 mW.
- Minimum held/previous-bit margins: 38.759386 / 53.983084 mV.
- Drawn-geometry subtotal: 0.007961241107 mm2, not routed area.

The original failing branch now has minimum Vds +351.003594 mV across all
45 points, versus -2.451058 mV at the failed Entry 124 corner. The eye
apertures are conservative finite-grid widths; scan-boundary flags remain
in each result. They are NOT BER contours or proof that every shifted clock
phase works.

At TT, code 2 produces 237.637196 mV sampled eye; minimum-current code 0
gives 204.312377 mV and reversed code 2 gives 123.127425 mV. The discharge
devices allow residual feedback even with all four enables low. Therefore
code 0 is explicitly **minimum current**, not feedback disabled.

## Scope and next check

This is a connected transistor-level 1-tap feedback demonstration using the
same geometry/code/clock phase at every primary-channel PVT point. Typical
passives, a finite noiseless bit pattern and external clock/control/common-
mode sources remain declared assumptions. The whole-circuit signed audit
still records the legacy bidirectional PMOS attenuator's reverse-Vds cases;
the 45/45 registered gate is not whole-circuit model-domain or reliability
signoff. Physical clock drivers, loaded noise/HD3, mismatch, BER and routed
layout are not verified here. Rs/Cs remain fixed.

Next, Entry 126 tests later external sampling phases at 12 dB, with matched
minimum-current/reversed controls and conditional 45-PVT at both 3 and 12 dB.
Do not inherit the old 315/315 model count or claim arbitrary-channel
coverage. The original reports, registry and frozen RL remain unchanged.

Original evidence manifest: 377 file hashes. Summary SHA-256:
`9bdc1302c0328de73f643b86a34415cb845c92d583cab105ec6e9f90505974f1`.
Manifest SHA-256:
`cee000d7a86b352844f743e06eb57ddc6b98ce58bdfe99666118e33fb7503ef4`.
Exact gzip siblings preserve raw bytes; local originals are retained.
There are 114 archives: 1,383,204,851 compressed bytes preserving
4,870,455,744 raw bytes. The largest archive is 15,254,468 bytes.
