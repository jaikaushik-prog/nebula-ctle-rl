# Fresh physical-bias product example

Request: 9 dB at 1.9 GHz. Fresh result: **315/315 electrical model cases pass**,
one fixed setting 490 across 45 PVT corners and seven constructed channels.
This is not a full receiver or laid-out-area compliance certificate.

- [Schematic](design_schematic.png): physical CTLE, PMOS reference, MIM bypass
  and both input-attenuator halves, parsed from the measured deck.
- [Exact circuit](design.cir): byte-identical to the nominal AC/noise deck.
- [Product result](design.json): fresh nominal values and fixed condition matrix.
- [Measurement summary](physical_evidence/summary.json): both HD3 tones,
  behavioural eyes, DFE controls and explicit unknown-area boundary.
- [Raw file hashes](physical_evidence/evidence_sha256.json),
  [source provenance](physical_evidence/provenance.json), and
  [per-corner journal](physical_evidence/fixed_pvt.jsonl).

`physical_evidence/<corner>/ac_noise`, `s4` and `nyquist` contain exact decks,
ngspice logs and raw data. `calibration` is a measurement fixture; its ideal
calibration current is not a component in the delivered circuit.
`legacy_candidate` and `legacy_proposal_not_physical_evidence.json` document
proposal selection only. `inputs` preserves the actual measurement-source
snapshots, including the original version of the final presentation gate.

137 SPICE calls, 107.908 seconds on the recorded machine. No training update.
Nominal response: 8.834174 dB at 1.768990 GHz; CTLE + reference power 6.965787 mW.
The original Judge demo remains separate and describes ideal-Iref hardware.

Full usage and limitations: [PHYSICAL_PRODUCT_RESULTS.md](../../PHYSICAL_PRODUCT_RESULTS.md).
