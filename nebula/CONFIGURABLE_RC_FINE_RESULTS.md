# Entry 131: nine sampled targets reached on one physical tunable circuit

Two calls from b1d47ec complete 882 OP/AC pairs in 191.949657 s, no retries.
N250/no-fixed-MIM reaches five declared identities (149 passing settings).
N500/no-fixed-MIM reaches all nine (246 passing settings) and is selected by
the preregistered coverage/error/area rule. Its topology and drawn geometry
are unchanged across all nine targets; only external R/C voltages differ.

For N500, 500 complete official varactor cells per source side implement Cs;
the measured poly/NMOS branch implements Rs. Both physical control-feed and
bypass networks are present. The selected measured targets are:

| Requested boost / peak | R / C control fractions of VDD | Measured boost / peak |
| --- | --- | --- |
| 3 dB / 1.5 GHz | .81 / .000 | 3.047763 dB / 1.565166 GHz |
| 3 dB / 1.9 GHz | .79 / .135 | 3.079552 dB / 1.905639 GHz |
| 3 dB / 2.25 GHz | .78 / .180 | 3.101998 dB / 2.257033 GHz |
| 6 dB / 1.5 GHz | .73 / .075 | 6.330757 dB / 1.497896 GHz |
| 6 dB / 1.9 GHz | .73 / .150 | 6.077889 dB / 1.851382 GHz |
| 6 dB / 2.25 GHz | .73 / .195 | 5.884202 dB / 2.237858 GHz |
| 9 dB / 1.5 GHz | .70 / .105 | 9.125265 dB / 1.498181 GHz |
| 9 dB / 1.9 GHz | .70 / .165 | 8.909067 dB / 1.857653 GHz |
| 9 dB / 2.25 GHz | .70 / .210 | 8.770956 dB / 2.233390 GHz |

Every identity satisfies the registered measured-error tolerances of 0.5 dB
and 0.1 GHz, as well as standalone AC/electrical gates. This is nine sampled
identities, not the full 3-12 dB by 1.25-2.5 GHz rectangle. N250's four missing
identities remain explicit in its raw summary; they are not relabelled.

All 882 fixed-reference AC comparisons pass, max error 2.8122434780897265e-7
dB. Fixed-reference DC drift is zero at the saved precision in both calls.
PDK and scientific source hashes remain unchanged. Prior failed experiments
and all offline characterization costs remain billed. No frozen RL changes.

This is TT/1.8 V/27 C standalone CTLE with the original output load, external
control generators and typical passives. The existing model-domain envelope
qualification remains: exact signed audits are retained, not reliability
signoff. DFE loading, dynamic control settling, new PVT, noise/HD3, routed
layout and full receiver signoff are not established. Entry 132 separately
registers connecting the selected near-9 dB/1.9 GHz setting to the existing
transistor DFE. Both report PDFs remain unchanged.

Raw bundle: 1812 manifest entries, 97,335,518 bytes including manifest.
Summary SHA-256: `06f6344b3802bf863f3ceb80be847cd0ab6c95debe3c0c3760a8ce590ef87b12`.
Manifest SHA-256: `03585ee1a882bb36523557bfa029b61cb9f29edcc21cd0eaf402d33372e3ab01`.
Evidence: `product_audits/entry131_configurable_rc_fine_20260910/`.
