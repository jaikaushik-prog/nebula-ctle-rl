# Entry 134: runtime instrument stopped on the documented two-point AC quirk

This is an instrument failure, not a runtime hardware pass or failure.
One registered call ran from `67dac07ad9311d322c804793ba9fe751f0ffca25`,
taking 27.867328 s including 2.365775 s prerequisite verification. No retry
or runtime control-changing call ran. All source and external PDK hashes
remain unchanged.

The first static call completed its OP, 251-point AC and 100 ns transient,
but `ac lin 2 100meg 1.9g` emitted only the 100 MHz row. The strict parser
correctly rejected the missing 1.9 GHz measurement. This exact issue was
already documented in HANDOFF G164; the new instrument mistakenly repeated
it. Do not describe this as a newly discovered simulator behavior.

Independent inspection of the retained OP/full-sweep primitives reproduces
the saved Entry 131 circuit: maximum DC-node difference 8.8817842e-16 V,
full-AC magnitude difference 1.1571930e-14 dB, phase difference
7.3762805e-16 rad. These checks do not repair the missing endpoint or promote
the failed runtime gate. All measurements and the failed source stay frozen.

The existing G164 workaround is a three-point linear AC sweep with strict
low/mid/high validation and selection of the actually measured endpoints.
Entry 135 preregisters that correction without changing circuit geometry,
controls, solver precision, transient stimulus, duration or acceptance gates.

Evidence: `product_audits/entry134_configurable_rc_runtime_20260910/`.
80 original manifest entries. Two lossless gzip files preserve 18,659,710
raw bytes in 4,799,373 bytes; originals retained.
Summary SHA-256: `041f2f243634859dc4e8aa1884a2bd3b519d194de0ad65214a2d0d22c526309d`.
Manifest SHA-256: `9cb555a0264202056e2e63e904b77bea547d3fbb2c2fd649b07c5e0d767e7140`.
