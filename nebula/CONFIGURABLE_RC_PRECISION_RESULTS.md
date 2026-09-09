# Entry 130: physical Rs/Cs control produces valid CTLE tuning measurements

Nine registered geometries completed once in 309.915343 s from checkpoint
23d8efb. All 729 OP/AC pairs pass the unchanged instrument/reference checks;
65 settings pass the standalone 3-12 dB boost, 1.25-2.5 GHz peak, sub-15 mW
and magnitude/body voltage-envelope gates. Per-geometry pass counts, ordered
N100/250/500 with fixed MIM 0/1.5/2.5 pF, are 0,9,9,11,9,9,5,7,6.
This counts tested settings, not coverage of the entire specification box.

Only numerical convergence was tightened. Maximum unchanged-reference DC
drift is now 2.6840751843337785e-12 V, below the original 1e-9 gate. Maximum
AC reference error is 2.8122435474786656e-7 dB, below the original 1e-6 gate.
The hypothesis is supported: solver precision closes Entry 129's numerical
failure. Entry 129 remains recorded as failed. All source/PDK hashes match.

Example physical control results, with unchanged geometry within each:

- N100 plus 1.5 pF fixed MIM, R control 0.7 VDD: C control 0..VDD moves the
  peak 1.836014..2.222265 GHz while peaking stays 8.920629..9.056791 dB.
- N250, no fixed MIM, C control 0.15 VDD: changing R control 0.6 to 0.7 VDD
  changes peaking 11.7088 to 8.2921 dB (peak 2.2679 to 2.3660 GHz).
- N500, no fixed MIM, R control 0.7 VDD: C control 0..0.2 VDD spans five
  passing states, peak 1.301117..2.152079 GHz and boost 8.795943..9.316740 dB.
  Higher C-control voltages move the peak above 2.5 GHz and fail that gate.

These are actual poly/NMOS resistor control and official SKY130 varactor
arrays, not ideal variable R/C replacements. Control feeds and bypasses are
physical poly/MIM; voltage generators remain external. Coarse R sampling
jumps across much of the useful peaking range, motivating Entry 131's finer
control map on two already measured geometries, without transistor resizing.

Important adjacent scope: standalone CTLE, TT/1.8 V/27 C, original 32.628 fF
output load, typical passives. Max measured CTLE/reference VDD power is
6.965786651 mW; this excludes DFE and external control generators. Exact
signed transistor audits are retained; the envelope is not foundry signed-
domain/reliability signoff. No connected DFE, dynamic settling, PVT, noise,
HD3, routed area or full target-rectangle verification follows from this run.
Both old PDFs, delivered fixed-passive DFE and frozen RL remain unchanged.

Cost: nine processes, 729 OP plus 729 AC analyses, no retries. Prior isolated
capacitor, timeout and numerical-failure experiments remain billed separately.
Original manifest: 1530 entries (1531 files including manifest), 81,670,967 bytes.
Summary SHA-256: `5285ad72e81dda0e5ff85acbcad7ed4d29f7f6ad09d72cc297a87ac51d96fbfa`.
Manifest SHA-256: `407e9ffa00af20cb3f3275b372d4089655d1430bc26c0ddc637778fc7c5d5ee7`.
Raw evidence: `product_audits/entry130_configurable_rc_precision_20260910/`.
