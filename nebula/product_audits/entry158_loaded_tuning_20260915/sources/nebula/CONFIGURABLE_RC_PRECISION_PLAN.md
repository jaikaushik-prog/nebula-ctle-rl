# Entry 130: precision-only serial instrument recovery

Registered 2026-09-10 after Entry 129 stopped at its first instrument gate.
Entry 129 retained 81 OP and 81 AC tables in one 51.303298 s process. Every
fixed-reference AC comparison passes (maximum error 2.812165408e-7 dB), but
fixed-reference source-node DC drift reaches 1.579230291e-8 V, exceeding the
unchanged 1e-9 absolute baseline consistency gate. This is a failed numerical
validation, not a passing physical circuit. Its original result stays failed.

Hypothesis: tightening Newton convergence removes the reference drift.
Use exactly one additional line before .control:
`.options reltol=1e-9 vntol=1e-12 abstol=1e-15`.
The official ngspice option implementation maps these to relative, voltage
and absolute current tolerances; no device/model parameter is changed:
https://raw.githubusercontent.com/ngspice/ngspice/master/src/spicelib/analysis/cktsopt.c
Do not relax the 1e-9 DC or 1e-6 dB AC comparison gates. Do not change
iteration limits, physical topology, device sizes, bias pairs or shape gates.

Reuse the exact Entry 129 serial deck and its existing extraction/schedule.
At most nine sequential ngspice_con processes, 180 s each, no retries.
Run N100/fixed0pF first. Stop if its instrument/baseline gate fails, regardless
of why. Only on success run the other eight registered geometries once each.
Each completed process performs 81 OP and 81 AC analyses; maximum 729 each.
Retain every raw table, streamed log, deck, source snapshot and failure.
Pin Entry 129's complete manifest and all scientific source hashes; verify
the same external PDK closure and original fixed-circuit reference.

First write rejection tests, run focused/full regression, and freeze a local
commit before SPICE. Run once into
`product_audits/entry130_configurable_rc_precision_20260910/`.
Prior Entry 127/128/129 costs remain billed separately. No frozen RL changes.
No automatic geometry promotion into the delivered receiver is authorized
by this AC/DC screen alone. This is TT/1.8 V/27 C standalone CTLE with the
original output load, external control generators and typical passives.
It does not establish DFE loading, runtime settling, PVT coverage, noise,
HD3, full tuning-rectangle coverage, layout or model-domain reliability.
