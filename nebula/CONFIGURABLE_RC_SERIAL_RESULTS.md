# Entry 129: measurements retained; reference DC consistency gate failed

Run 2026-09-10 from local checkpoint 4b16c5f. The first geometry,
N100/fixed0pF, produces all 81 operating-point and 81 AC tables in one
51.303298 s process. The registered first-call gate stops the remaining
eight geometries: no retry and no physical candidate is promoted.

All 81 fixed-control AC curves match the original 251-point reference;
maximum error is 2.812165408039302e-7 dB, below the 1e-6 dB gate. However,
the unchanged fixed-control source node s1 changes by 1.579230290982281e-8 V
between control settings, above the 1e-9 absolute DC consistency gate.
The simulator completes normally; the strict parser correctly rejects its
output as a validated candidate batch. All source/PDK hashes are unchanged.

This is a numerical validation failure, not a measured tuning-spec failure
or a pass. Retained AC data alone do not override the failed experiment gate.
Entry 130 preregisters tighter solver tolerances with exactly the same
circuit, all controls, parsers and pass thresholds. It is not yet measured.

The complete original manifest contains 198 files, plus the manifest itself.
Summary SHA-256:
`3f4c1536754a27eadd661b3e2dc7536d6e53c9b2e217a5bf4bb027fe797bfdb8`.
Manifest SHA-256:
`ee32dd501afab1813e373aaba63574a46ba334bda8296f8bc392d30d3e1c15e0`.
Raw evidence: `product_audits/entry129_configurable_rc_serial_20260910/`.
The transistor DFE checkpoint and both existing PDFs remain unchanged.
