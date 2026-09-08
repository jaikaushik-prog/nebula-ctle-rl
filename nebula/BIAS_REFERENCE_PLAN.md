# Entry 103 - physical reference and bypass-capacitor prototype

Owner request, 2026-09-06: implement the ideal Iref physically first and count
bypass capacitors. Entry 102 integration is paused. Existing production decks,
RL bank, policies and earlier measurements remain unchanged.

## Frozen bounded experiment

- Starting circuit: exact Entry 101 fixed-490 deck, not a new RL-selected circuit.
- Replace Iref by a diode-connected PMOS plus a 1:1 PMOS output mirror and a
  ground-connected SKY130 poly resistor. Both PMOS devices initially reuse the
  existing reference width, tail length and reference finger count. This is a
  simple supply-dependent bias, NOT a precision or temperature-compensated source.
- One isolated TT/1.8 V/27 C calibration: force the old IREF through the diode
  PMOS, measure its gate voltage, and derive R=V/I using the existing passive
  geometry mapper. The ideal current is calibration apparatus only. Freeze the
  resulting resistor geometry; no per-corner recalibration or search.
- Replace the ideal CBYP with a SKY130 MIM capacitor sized by the existing
  capacitor geometry mapper. Count that plate, both PMOS gates, and the bias
  resistor body in the area inventory, including native m multipliers.
- Maximum 47 SPICE invocations: one calibration, 45 fixed-geometry DC/AC/noise
  corners (5 process x 3 supplies x 3 temperatures), one TT supply-ramp startup.
  No bypass-changing retries or replacement of failed rows. Typical passive
  process only; full independent passive-corner/mismatch/layout checks remain.
- Preserve exact decks, raw logs and AC data in a new exclusive directory;
  journal every corner, including failures; check invariant circuit signatures.
- Report actual reference/tail current, CTLE+bias supply power, noise, peak gain
  and frequency. Do not infer HD3 or eyes for this new circuit from old evidence.
- This is NOT production integration or full compliance. DFE/slicer/clock,
  physical Rs/Cs selectors, common-mode generation and layout remain missing.
  Full receiver area stays unknown; no arbitrary layout overhead multiplier.
- Guard the old schematic renderer from depicting this new topology as ideal
  Iref/Cbyp. Add fail-first regression tests and run the full suite before/after.

Baseline before hardware edits: 2,798 passed, 13 deselected, two known warnings
(262.60 s). The deferred Entry 102 test was created after that collection and
failed separately on its intentionally absent module; it is retained as a plan,
not counted as a passing implemented test.
