# CML decision/hold development

## Entry 122 (2026-09-09)

Registration commit: b11fb22. Measured 48 calls in 56.5842 s, no retries.
Evidence: `product_audits/entry122_dfe_cml_20260909/` (354 original hash entries).

All three TT sizes (4, 8, 16 um) correctly decide and retain 32/32 scored bits,
including the previous-bit check. Every transistor stays inside the exact
signed terminal model bounds, including startup. This is a real improvement
over Entry 111, which had 14/32 held bits and terminal excursions. It is a
new architecture, not a changed threshold applied to that old waveform.

| Input/regen width | TT held minimum | Final stable clock-to-Q, worst bit | VDD power |
|---|---:|---:|---:|
| 4 um | 47.256 mV | 22.5 ps | 1.440495 mW |
| 8 um | 143.435 mV | 39.5 ps | 1.452115 mW |
| 16 um | 124.291 mV | 57.5 ps | 1.459292 mW |

External-clock positive supplied power is separately 0.110564, 0.106759,
0.103543 mW, respectively; this does not implement or fully bill a physical
clock generator. W=4 geometry subtotal is 0.00006725 mm2, not routed area.

The registered smallest-width selection chose W=4. It passes **34/45** PVT
points, not 45/45. Eleven failures are TT/0.95/125, and SS or FS at
0.95/(0,27,125), 1.00/125, and 1.05/125. Weak held/previous-bit differential
signs cause the failures; all 48 runs pass the signed voltage-domain check.
The runner correctly exits nonzero. Do not promote nominal success to PVT.

This circuit contains 15 real SKY130 MOS devices and five drawn poly
resistors. Clocks and data/common mode are external ideal testbench sources.
It is not connected to the CTLE and has no feedback DAC/summer. Complete DFE,
receiver power, loaded eyes, mismatch, BER and physical clock remain unverified.
The old fixed-passive physical export and frozen RL evidence are unchanged.

Next bounded trial: `DFE_CML_RECOVERY_PLAN.md`; no change to Entry 122 results.
