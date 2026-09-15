# Generated CTLE to transistor DFE integration plan

Registered 15 September 2026 before new simulation.

## Question

Can the accepted automatic-recovery CTLE be connected directly to the existing
SKY130 one-tap transistor DFE and produce an exact reviewable receiver deck?

## Frozen pilot

- Input: accepted 6 dB / 2.1 GHz recovery run, setting 352.
- CTLE: exact exported `design.cir`; its recorded SHA-256 must match.
- DFE: unchanged Entry 125 summer, master/slave CML memory, four-branch current
  DAC and off-branch bleeders.
- Stimulus/check: unchanged 64-bit 5 Gbps NRZ pattern, constructed 7.5 dB
  channel, TT / 1.8 V / 27 C, phase 1 UI, tap code 2, polarity +1.
- Budget: one ngspice call, 180 second timeout, no retry and no tuning.
- Output: a separate `receiver.cir`, raw trace, terminal voltages and a result
  record. The original accepted CTLE evidence is immutable.

## Interpretation

Deck generation establishes structural integration for every accepted recovery
output. This one-call pilot establishes only nominal finite-pattern behavior for
one selected circuit. It cannot establish BER, analog PVT, full-range receiver
coverage, clock/control implementation or routed area. A failed pilot remains a
connected implementation and a measured limitation; it is not relabeled as a
pass.

