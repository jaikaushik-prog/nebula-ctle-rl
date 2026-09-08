# Entry 104 - distortion and eye gate for the physical reference

Owner said "continue" after Entry 103. Baseline: 2,812 passed, 13 deselected,
two known warnings, 270.53 s. This is validation, not production integration.

## Frozen measurement plan

- Preserve Entry 103's exact PMOS/poly/MIM reference and fixed-490 CTLE geometry.
  No recalibration, resizing, code changes, bypass retries or RL training.
- Verify hashes and circuit identities before reusing the 45 saved DC/AC/noise
  datasets. No reason to repeat those analyses. Probe DC operating points again
  before transient to cross-check that the bias is unchanged.
- Exactly two new SPICE calls per PVT point, maximum 90 calls:
  100 MHz at the existing 0.1 V differential peak, and 2.5 GHz at half the
  existing LinkConfig input Vpp (report the actual rounded netlist amplitude).
  The Nyquist call also measures the existing +/-0.8 V, 4 mV-step DC swing.
- Reuse sky130_runner's existing transient window, settling, sampling and FFT
  instrument; do not introduce another HD3 definition. Preserve all raw waveforms,
  swing curves, decks and logs. Failed simulations stay failed; no repeat calls.
- Use the unchanged device-to-link fit/compression gate and seven existing
  constructed channel cases (3, 4.5, 6, 7.5, 9, 10.5, 12 dB at Nyquist).
  Compare ideal/none/20%-misadapted/quantised behavioural DFE policies using the
  existing ablation and require the ideal control to reproduce the bridge.
- Electrical model gate uses the existing 9 dB / 1.9 GHz request tolerances,
  electrical constraints and both HD3 tones. S7 area is explicitly EXCLUDED
  from electrical pass: its complete receiver value is unknown. The larger
  Entry 103 geometry subtotal is reported, never substituted as full S7 area.
- Full product compliance remains false regardless of electrical results.
  DFE/slicer/clock hardware, physical Rs/Cs selector/control, common-mode
  generation, layout, independent passive corners and mismatch remain open.
- Unit tests must reject changed circuits, incomplete grids, invalid waveforms,
  missing DC swing and missing measurements. Full regression after changes.
  No report/demo/bank/policy overwrite and no automatic deployment on a pass.
