# Entry 134: bounded physical Rs/Cs runtime control demonstration

Registered 2026-09-10 after Entry 133's 45/45 connected electrical PVT pass.
Use the already selected Entry 131 N500/no-fixed-MIM standalone CTLE,
unchanged physical devices, bias reference, control feed/bypass and output
load. TT/1.8 V/27 C only. External voltage generators remain testbench devices.

Four sequential ngspice_con calls maximum, 180 s each, no retries:
three static references at (R,C)/VDD = (.7,.165), (.79,.135), (.73,.15),
then one continuous powered transient stepping index 0 -> 1 -> 2 -> 0.
These are the measured near-9/3/6 dB points on the 1.9 GHz target line.
No other controls, geometry or frequencies may be searched in this run.

Each static call: OP, original 251-point AC sweep, exact AC samples at
100 MHz/1.9 GHz, and a 100 ns transient. Compare every OP node to the saved
Entry 131 point within 1 nV, VDD power within 1 nW, full AC magnitude within
1e-6 dB and complex phase within 1e-6 rad. First-reference failure stops at
one; otherwise retain both remaining references and stop at three if any fail.

The transient stimulus is the sum of 100 MHz and 1.9 GHz differential sine
tones, each 1 mV peak. This is a small-signal instrument check, not HD3/eye.
Keep the previously validated reltol=1e-9, vntol=1e-12, abstol=1e-15 settings.
Use 5 ps maximum transient step, no UIC and no circuit reset during runtime.
Control changes start at 100/700/1300 ns with 10 ns linear ramps; stop at
1900 ns. There is one powered circuit, not independent reinitialized plateaus.

Parse primitive time, input/output, supply/control voltages and currents,
and every MOS terminal. Require finite strictly increasing complete time,
maximum gap <=5.01 ps, analytic stimulus/control agreement within 1 nV,
VDD agreement within 1 nV, actual source/varactor voltage envelope and
whole MOS magnitude/body checks. Keep bilateral signed findings separately.

Fit both tones plus DC on 20 ns windows using uniform 5 ps interpolation;
divide output phasors by measured input phasors, not assumed gain or polarity.
Require each static final window's complex transfer within 2% of its exact
AC sample, output residual RMS <=5% of fitted AC RMS, and average VDD power
between 0 and 15 mW. Reject missing/zero inputs and ill-conditioned fits.

For runtime, evaluate windows every 10 ns after each completed ramp.
Require both complex gains within 2% of the corresponding static AC reference,
control-node mean within 1 mV of that point's measured OP, residual <=5%,
and the same power gate. Report the first window-start after which ALL later
windows before the next change pass. Require this conservative, windowed
settling bound <=500 ns after each ramp end; this is a demonstration gate,
not an organiser-specified tuning latency. Require at least 10% pairwise
separation of the three static 100 MHz gains to exclude an unresponsive bank.
Report transition-supply/control energy and all failures without gate changes.

Verify the complete Entry 131 manifest and source/PDK hashes before SPICE;
snapshot all source dependencies, simulator hash and external PDK closure.
Failure-first unit tests, focused/full regression and local freeze precede
the run into `product_audits/entry134_configurable_rc_runtime_20260910/`.
Use existing lossless archival, retaining originals. Replay saved primitives.

This does not establish uninterrupted transistor-DFE decoding during control
changes, runtime PVT, the full target rectangle, loaded noise/HD3, BER, clock/
control generation, passive tolerance, mismatch, lifetime or routed layout.
No old hardware/RL evidence is altered or silently extended.

Instrument references: ngspice's official transient/AC tutorial,
https://ngspice.sourceforge.io/ngspice-tutorial.html , and explicit maximum
step example, https://ngspice.sourceforge.io/ngspice-electrothermal-tutorial.html .
