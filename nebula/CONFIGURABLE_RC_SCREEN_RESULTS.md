# Entry 128: calibration passed; simultaneous-copy screen timed out

Run 2026-09-10 from verified checkpoint 952a648. All ten registered calls
were attempted once, without retries; wall time 600.551942 s. PDK and
scientific source hashes remained unchanged.

The full-library, subcircuit-wrapped unchanged CTLE reproduces all 251 saved
TT AC samples, maximum magnitude error 5.4361848356165865e-11 dB. VDD power
is 6.965786645 mW and the existing magnitude/body envelope passes. This
calibrates the interface, not a tunable circuit.

All nine candidate decks instantiate 81 independent voltage-setting copies
plus one fixed control. Every candidate call hit the registered 60-second
budget before any OP or AC output table was produced. The existing frozen
timeout handler then failed while combining text and byte capture streams,
recording `TypeError: can't concat str to bytes` instead of its intended
timeout message. Consequently their captured ngspice logs were not written.
The decks, .spiceinit and exact failure records are retained; missing logs
cannot be reconstructed and must not be invented. There are no measured
candidate gains, capacitances, eyes or physical pass/fail conclusions here.

Entry 129 is a separately preregistered instrument recovery: keep all
geometries, controls and response gates unchanged, instantiate one tunable
circuit plus a fixed control, and step only external DC control voltages.
Use directly streamed retained diagnostics and a 180 s bound, at most nine
fresh processes. First-call instrument failure stops that recovery stage.
Count the 81 OP and 81 AC analyses per complete process explicitly. No
Entry 128 circuit failure is relabelled as a pass and no extra call enters
the original ten-call experiment.

Original manifest: 60 files. Summary SHA-256:
`eb2a01bf10c47d9af5b372668d64c819b28c84461caec9e359d936fffb51a67b`.
Manifest SHA-256:
`4a2a4e3472a84145f7ff705fe3d42027f6bab4ad0ca05015f9f5b5e770bc65a3`.
Raw evidence: `product_audits/entry128_configurable_rc_20260910/`.
