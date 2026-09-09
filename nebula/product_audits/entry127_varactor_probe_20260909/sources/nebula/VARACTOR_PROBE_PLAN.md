# Entry 127: physical varactor feasibility, before CTLE insertion

Registered 2026-09-09 under the owner's authorization for bounded hardware
architecture/range experiments. DFE is first: finish Entry 126 and preserve
its result before running this stage. Do not change the frozen DFE sources.
Entries 95--97 remain failed under their original gates. No old switch-bank
loss limit is relaxed or relabelled as passed.

## Question and model boundary

Can an official SKY130 accumulation-mode varactor provide a physically
voltage-configurable Cs without the previous series capacitor selectors?
This is a device-characterization stage, NOT a configurable CTLE pass.
The resistor-bank and connected-CTLE integration need their own next stage.
No RL, production registry, report, fixed export or prior evidence changes.

Use the installed, unmodified sky130_fd_pr__cap_var_lvt model through the
FULL official sky130.lib.spice corner section. Do not copy model cards into
the repository, redeclare their parameters, or introduce an unverified trim.
Record the external PDK include-closure hashes, simulator path and .spiceinit.
The official model-valid range is |V(c0)-V(c1)| <= 2.0 V:
https://skywater-pdk.readthedocs.io/en/main/rules/device-details.html
The model source is:
https://github.com/google/skywater-pdk-libs-sky130_fd_pr/blob/main/cells/cap_var_lvt/sky130_fd_pr__cap_var_lvt.model.spice

Use default characterized unit geometry W=5/L=0.5 um, substrate at ground.
The model's vm multiplier scales nonlinear charge and series resistance but
its literal 0.15 fF substrate capacitors do not scale with vm. Therefore vm=N
is NOT assumed equivalent to N complete physical cells. Calibrate native
ngspice m=N against explicit parallel unit instances before using it.
No homemade C-V approximation or ideal capacitor is substituted.
The installed subcircuit contains nonlinear charge, series resistance and
the two substrate capacitors, but no explicit substrate-junction conduction
element. This probe therefore cannot validate substrate leakage/breakdown;
the documentation's general device description is not a substitute for the
actual installed circuit model.

## Membership and stopping: maximum 46 calls

1. One TT/1.00/27 calibration deck, three independent source/control bias
   pairs: source 0.5 V, control 0, 0.45 and 1.8 V. At each pair, excite c0
   and c1 separately in independent copies and save BOTH terminal currents.
   For each excitation compare six kinds: one unit; native m=4; four explicit units;
   vm=4; native m=500; 500 explicit units. All units retain W=5/L=0.5.
   At exactly 1.25, 2.5, 3.75 and 5 GHz require native m=4 and explicit four
   to equal four times the unit admittance, and native m=500 and explicit
   500 to equal 500 times it (relative tolerance 1e-9, absolute 1e-18 S).
   Both driven and grounded terminal currents must scale, preserving the
   transfer admittance and both substrate capacitors. Require correct finite
   DC biases, positive driving-point conductance/capacitance and
   model-valid terminal voltages. Report vm=4 error; do not use vm=4 in the
   candidate. Failure/timeout stops after this call, without a retry.
2. Conditional on calibration, 45 independent PVT calls: all five process
   corners x supply scales .95/1/1.05 x 0/27/125 C. Each deck contains
   electrically isolated copies of the SAME candidate pair at five source
   common modes (.35, .50, .65, .80, .95 V) and 41 external tuning fractions
   (0..1 inclusive, step .025) of that case's VDD. Each pair has one m=500
   unit from each source to a shared ideal external control-voltage node,
   with substrate grounded. Excite sources with +.5/- .5 V small-signal AC.
   Every control is present as an independent probe; this is NOT a fabricated
   bank of 205 settings. One physical candidate pair has 1000 unit cells,
   2500 um2 active geometry, excluding routing, wells, control generation.

Read-only rationale for the source biases: Entry 125's saved XM1/XM2 Vbs
audits (bodies at ground) give source extrema 0.3723930254141027 to
0.601202795799302 V across the 45 primary-channel points. Summary SHA-256:
9bdc1302c0328de73f643b86a34415cb845c92d583cab105ec6e9f90505974f1.
The .35/.50/.65 V probes bracket that measured range; .80/.95 V are declared
extra headroom probes for possible later configurations, not measured CTLE
operating points. No new simulation was used to choose them.

Every call uses a fresh exclusive output folder and the existing run lock;
ngspice_con only, one call at a time, 60 s timeout, raw deck/log/tables retained.
Full PDK parse cost is billed. No retries, hidden extra calls or Monte Carlo.
Freeze the plan, source and tests in a local commit before starting SPICE.

## Measurement and interpretation

Save OP voltages and AC primitive source currents at exactly the four listed
frequencies with 15-digit single-scale output. Parse exact vector counts and
axes; reject nonfinite data, incorrect biases, wrong signs, out-of-range
terminals and simulator warnings/errors under the existing silent-failure
scanner. Compute differential Y=-(Iplus-Iminus)/2 for a 1 V differential AC
excitation. Report G=Re(Y), C=Im(Y)/(2*pi*f), Q=Im(Y)/Re(Y), and equivalent
series resistance Re(1/Y). Do not confuse parallel G with series resistance.

Report every bias point, per-corner C/G/Q ranges, monotonic C versus tuning
voltage, and the prior Entry 96 conductance-error limit as historical context
only. No range, Q or loss result is assumed in advance. Complete instrument
characterization is NOT a claim that an amplifier meets its peaking, eye,
noise, HD3, power or area specs. The GHz loss and nonlinear C-V must be carried
into the later connected circuit; arbitrary remapping cannot erase loss.
The external ideal control source's AC ground is an explicit assumption;
a physical bias feed/bypass and runtime reconfiguration are still required
for the integrated configurable circuit. Typical resistor/MIM process remains
separate from varactor process parameters supplied by each official corner.

Predictions, not results: native m will reproduce explicit complete cells;
vm=4 will differ in substrate loading; raising control voltage will generally
reduce effective capacitance at these source biases. GHz loss may prevent
useful CTLE tuning, so no performance-pass prediction is registered.

Preserve all source snapshots and output hashes, including failed runs.
Tests must reject missing vectors, reversed current polarity, altered axes,
invalid geometry/bias arguments and failed multiplicity evidence. No mocks
enter the saved measured result.
