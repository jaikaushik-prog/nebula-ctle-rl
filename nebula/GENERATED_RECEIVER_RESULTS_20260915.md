# Generated receiver: independent evidence review, 15 September 2026

**Review PASS for evidence integrity and the recorded nominal signal gate. Full receiver verification remains false.** No SPICE was rerun; the saved main and terminal traces were independently read and reanalyzed using the established measurement and acceptance functions.

The generated receiver uses setting 352 from saved run `4608cf1c525f4e59b2d5226059b0ce5d`, requested at 6 dB / 2.1 GHz. The selected CTLE deck matches its recorded SHA-256, and every exported artifact matches the saved workflow manifest. Rebuilding the connected deck and applying the actual Windows text-writer conversion reproduces its raw bytes exactly. Existing CRLF source lines acquire an extra carriage return during writing; this is a serialization difference, not a circuit change.

| Recorded and independently reproduced measurement | Result |
|---|---:|
| Correct decisions after warm-up | 64 / 64 |
| Sampled eye height | 296.981033 mV |
| Minimum signed sample margin | 147.236421 mV |
| Positive eye aperture | 0.720 UI |
| Aperture above 100 mV | 0.675 UI |
| CTLE + DFE VDD power | 9.263600 mW |
| External clock positive supplied power | 0.108407 mW |
| External tap-control positive supplied power | 0.000155 mW |

This is one TT, 1.8 V, 27 C case with a constructed 7.5 dB channel, phase 1 UI, tap code 2, tap-sign setting +1, and 4 um bleed length. The stimulus has 80 bits, with 16 warm-up bits and 64 scored bits. The two tables contain 54,494 finite rows on an identical monotonic 0–16.8 ns time axis; all 25 main vectors and 41 terminal vectors are present. Maximum recorded time step is approximately 0.8 ps.

The deck contains **45 MOS instances: 37 NFET and 8 PFET**, including 32 added DFE instances. It has one model-library reference, no inline model redeclarations, and the established transistor summer, decision memory, current DAC and bleed devices. External stimulus, clocks and tap controls remain verification apparatus. This is separate from the earlier 73-device checkpoint.

The log ends with `ngspice-41 done`, and the established silent-failure scan finds no failures. It is **not warning-free**: 38 model warnings identify ignored resistor parameters `sw_et`, `isnoisy`, `p2`, `q2`, `p3`, and `q3`. The review records the directly referenced model-library hash; it does not independently certify the transitive PDK include closure or a separately retained process exit code.

**Remaining limitation:** the added DFE passes its signed terminal-voltage checks and the whole circuit passes the voltage-envelope check. The whole-circuit signed model-domain check remains false: 276,104 device-quantity samples violate documented signed ranges across `Xatt_swp0`, `Xatt_swn0`, `Xatt_swp1`, `Xatt_swn1`, `Xatt_swp2`, and `Xatt_swn2`. This is not reliability signoff. The run establishes neither BER, analog/link PVT coverage, noise/HD3 signoff, integrated clock/control drivers, nor layout verification. VDD power excludes the separately measured external sources.

Machine-readable checks, source/evidence hashes and exact measurements: [independent_review.json](product_audits/generated_receiver_6db_2p1ghz_20260915/independent_review.json).

- Receiver deck SHA-256: `69c15b41e547c96770d48bb19cf9a193c7f88447b38f82ee86c15bad8924672c`
- Selected CTLE deck SHA-256: `e8f8b0c82e6d797ce6baff14b2df551812915ad575a5b4a6871757b0cce4eaed`
