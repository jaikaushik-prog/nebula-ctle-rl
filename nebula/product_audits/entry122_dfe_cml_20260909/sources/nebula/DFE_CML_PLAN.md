# Entry 122: current-mode decision and hold, registered before simulation

Date: 2026-09-09. The owner authorized agent-selected bounded architecture,
sizing and clock experiments for transistor DFE and configurable Rs/Cs.
DFE is first. Specifications, existing exports and frozen RL evidence stay fixed.

## Why this architecture

Entries 106-111 retained failed StrongARM/buffer/storage timing and signed
terminal excursions. This is a new architecture, not a reclassification of
those failures. Two differential current-mode latches form a master/slave
edge-triggered decision/hold. Each has input pair, regenerative pair,
clock-steering pair and a tail NMOS. A diode-connected NMOS and real poly
resistor bias both tails. Four real poly load resistors complete the core.
There is no behavioral decision, input-bit feedback, forced initial state,
ideal DUT current source, or rail-restoring inverter chain.

Topology background (not SKY130 sizing evidence):
Razavi, The Design of an Equalizer, Part Two (2022),
https://www.seas.ucla.edu/brweb/papers/Journals/BR_SSCM_1_2022.pdf .
The full-rate feedback timing condition motivates separating latch, feedback
and setup delays. That paper's process and numerical results do not transfer.

## Frozen membership and schedule

- Three TT screens: input and regeneration total widths 4, 8, 16 um, L=.15 um,
  nf=W/2 (2 um fingers). Clock pair W=8, L=.15, nf=4. Each tail W=20,
  L=.5, nf=10. Bias diode W=4, L=.5, nf=2. All standard SKY130 1.8 V NMOS.
- Four poly loads W=1 um, L=1.33 um, m=1: modeled 800.1471 ohm at 27 C.
  Bias resistor W=1 um, L=30.33 um, m=1: modeled 9999.5210 ohm. Dimensions
  are on the .005 um grid, evaluated with the existing validated poly model.
  These compact geometries trade <0.02% target error for less drawn area
  than the global accuracy-prioritized selector. No ideal R substitution.
- External complementary 5 GHz clocks: VDD/3 to 2*VDD/3, 10 ps edges,
  80 ps high plateau, 200 ps period, first rising edge at 300 ps.
  This is a declared clock-source assumption, not an implemented clock driver.
- Existing 36-bit pattern from LinkConfig seed: four warmup, 32 scored.
  Differential input is +/-50 mV (100 mV peak-to-peak); common mode comes
  from the hash-verified physical CTLE log at each corner. No CTLE is attached
  at this stage; input loading and feedback are later experiments.
- 1 ps maximum transient step, full 7.6 ns trace. Exactly three TT calls.
  Select the smallest width passing BOTH logic and signed voltage checks.
  Only if selected, run the same geometry at all 45 PVT points, including
  independent TT. At most 48 calls, no retries or size changes within PVT.

## Gates and accounting

CML uses the sign of differential voltage, not a CMOS VDD/2 rail threshold.
Require the correct master decision at +88..98 ps, correct held slave decision
through +110..190 ps, and the previous decision at -10..-1 ps for every scored
edge. The previous-bit check rejects a combinational follower. Report minimum
differential margins and final stable clock-to-Q delay; this finite clean-bit
test does not establish sensitivity, BER, metastability or feedback settling.

Reject malformed, nonfinite, undersampled, truncated or wrong-stimulus traces.
Use the existing strict ngspice warning parser and exact signed D/G/S/B
model-domain audit on every MOS over the complete trace, including startup.
No clipping, source/drain swapping or excursions waived. Voltage domain is
not reliability/lifetime signoff. Official bounds:
https://skywater-pdk.readthedocs.io/en/main/rules/device-details.html .

Report VDD power including bias, external clock net/positive supplied energy,
ideal input energy and drawn gate/resistor geometry separately. Typical
passives only; generic poly passive nonlinearity remains unverified. No
external clock generator, common-mode source, DAC, receiver, layout or BER
claim. `hardware_dfe_complete` and `full_receiver_verified` remain false.

Freeze tested implementation and this plan in Git before invoking SPICE.
Store exclusive output directories, copied source files, raw decks/logs/traces,
source common-mode evidence and SHA-256 manifest. Retain all failures. A
failed screen ends THIS experiment; another trial requires a new written
registration under the owner's current authorization, not a hidden retry.
