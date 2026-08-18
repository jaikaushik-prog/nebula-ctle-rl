# HANDOFF.md — Living Project State & Continuation Guide

> **READ THIS FIRST.** This file is the single source of truth for project
> state. It exists so that ANY person or AI agent picking up this repository —
> at any point, with zero prior context — knows what this project is, what has
> been done, why every non-obvious decision was made, what the current state
> is, and what to do next.
>
> **THE RULE: if you change this repository, you update this file in the same
> commit.** Add a dated entry to the Session Log (bottom), update the Current
> State and Next Steps sections if they changed, and add any new gotcha you
> discovered to the Gotchas section. A change without a handoff update is an
> incomplete change.

Last updated: **2026-08-19** (session 22e: **task 1's mechanism is in and
PRE-REGISTERED, with no measurement yet.** The AC peak can now be read off
the parabola through the three samples bracketing the discrete maximum
instead of off the `dec 50` lattice -- `run_point(ac_peak_interp=True)`,
**zero extra simulation**, opt-in, and the default path is provably
byte-identical, so G74's **+8.950669** ceiling and every published reward
still reproduce. Whether that ceiling is GONE or merely MOVED is measured
by `experiments/exp_peak_interp.py`; `PREDICTIONS.md` entry 9 is committed
ahead of the numbers. Tests **1480 -> 1504**. New gotcha **G92**: two
arithmetics over the same events are ONE measurement.)

Earlier session 21: **GATE G2 IS PASSED, three days
early, and the first thing the closed loop revealed is that COMPRESSION binds
rather than the eye.** One parameter vector -> a drawn SKY130 schematic meeting
**all of S3-S8 at TT**: peaking **9.667 dB @ 2.188 GHz**, HD3 **-61.10 dBc**,
noise **0.290 mV_rms**, power **5.289 mW**, passive area **0.001092 mm^2**, eye
**758.1 mV x 0.875 UI**, fit residual **0.0222 dB**. **"The link layer is a mock
end to end" OVERSTATED the gap**: the channel, TX, cursors and calibration were
all real -- what was missing is that **nothing had ever CONSTRUCTED a
`DeviceResult`** (only `device/mock.py` did, so the two real layers had never
been joined) and that **the AC sweep was measured and thrown away**, only four
`meas` scalars kept, and a pole-zero fit cannot be made to four numbers. New:
`link/fit.py` (fit, rejected above 0.5 dB, exact on synthetic data, basin
probed from +/-2 decades) and `link/bridge.py`. **THE FUNNEL IS THE RESULT:**
300 LHS box samples -> 276 fit (92 %), **26 meet S3 (8.67 %)**, and **168 of
276 -- 61 % -- are REJECTED because the small-signal model no longer applies at
the link's own drive level**; median overshoot **1.29x**. Ten designs meet S3
and S8 together. **S8 is CONFIRMED NON-BINDING by measurement** -- 82 of 108
valid designs meet it (76 %) -- which reproduces `CHANNEL_MODEL.md` §5's
transistor-free prediction by an independent path, as the compression finding
reproduces its §6. **Fidelity tiers (G2's other half, min estimator, 21
interleaved shuffled repeats):** .op+.ac+.noise **0.1768 s**, +AC dump 0.2047,
+.dc swing 0.2257, **+HD3 transient 0.2787**, fit 0.0114 and link eval 0.0372
with NO simulator. The transient is **cheap** (+1.23x) against `s9_yield.py`'s
recorded "~4x" -- that figure was measured when PARSING dominated. **G71 fired
on this session's own gate measurement** (a NEGATIVE increment for strictly
more work), and three of the four other failures found were mine: `linearize`
takes VECTOR NAMES not a timestep and destroys the plot on error; my
missing-file check ran BEFORE the silent-failure scan, reporting the symptom and
hiding the cause (G68, violated by the person who had just cited it); my FFT
window was 20.01 cycles because `tran` yields an INCLUSIVE grid; and the
compression gate initially rejected the MOST LINEAR designs. **S8 is in
`V2_SPECS` and `V1_SPECS` is UNTOUCHED**, so the +8.950669 ceiling and every
published reward still reproduce. `params.py`/`contract.py`/`env.py` untouched.
Full write-up `nebula/G2_RESULTS.md`.
Earlier session 20: **a teammate's reparameterization
idea, built and measured -- its benefit is real and small, its stated mechanism
is false.** A gm/I_D lookup table built by direct `.dc` sweep
(`device/gmid_lut.py`, 3000 invocations / 510 s, 100 % monotone, `gmbs` on its
own axis) and a pure inverse map `(gm/I_D, L, I, f_z, k, R_L, VCM) -> device
coordinates` (`common/design_space.py`, seven in / seven out, every failure
NAMED and nothing clamped). **THE HYPOTHESIS -- that making `f_z` a coordinate
puts G44 out of reach -- IS MEASURED FALSE: G44 among designs that reach the
simulator is 38.07 % in device coordinates and 37.74 % in design coordinates,
unchanged**, on 1500 LHS samples per arm with the same sampler and evaluator.
What the map does buy is **89.40 % free rejection** -- but **65 % of that is
`current_unreachable`**, the request not being representable in the device box,
which is not a physics screen -- netting **1.90 -> 1.64 simulations per valid
design, 1.16x**. **THE PRE-SIMULATION G44 FILTER SCORED TN = 0** and the reason
generalises (**G82**): the closed form asks "is there a peak ANYWHERE" while the
guard asks "is the max within the 20 GHz SEARCH RANGE at its edge", so a design
peaking at 37 GHz has a real peak and trips the guard correctly; adding the
ceiling took TN 0 -> 8, and the other 52 misses are model error. **Read TN on
any pre-simulation filter, not accuracy.** What the map gets RIGHT: `f_z` and
`k` round-trip algebraically and `g_dc` lands at a median **-0.20 dB**, inside
§6's own gate. `f_peak` is over-predicted by **0.355 octaves**, and a
`k_alpha = 0.90` re-run quantifies a trade nobody had priced: peaking bias
**-0.816 -> -0.157 dB** while `g_dc` goes **-0.181 -> -0.663 dB**, because both
read the same `k`. **THREE NEW PDK GOTCHAS: G79** -- the gm/I_D method's
W-independence premise is FALSE on SKY130 at fixed `nf` (`I_D/W` moves **1.56x**
across the `w_in` box via G53's per-finger bins, smoothly, so textbook linear-in-W
scaling is a **56 % width error**); **G80** -- you write MICRONS and read back
METRES; **G81** -- SKY130 refuses an out-of-bin WIDTH and silently
EXTRAPOLATES an out-of-bin LENGTH. **`params.py`, `contract.py` and `env.py`
UNTOUCHED** (rules 5, 6) -- adopting this invalidates every baseline, so it is a
human decision, and `GMID_MAP.md` §8 recommends **not before G2** while noting
the one argument the other way: the sweep has not run, so now is the only moment
the change is free. **1314 -> 1389 green.** Full write-up `nebula/GMID_MAP.md`.
Earlier session 18: **the benchmark the final claim
rests on is built, and it moved two of its own inputs.** Task 7. **7e's LOUD
VERDICT DOES NOT FIRE**: the analytic pre-screen predicts `f_peak` to **4.93 %**
MdAPE (4.80 % in the 0.5-5 GHz decision region), rejects **61.7 % of the box for
free** at a 0.39 % false-rejection rate, and lifts the S3 rate among accepted
designs from **13.44 % to 34.94 %** -- a **2.60x multiplier, not the >50 % that
would mean physics solves the nominal problem**. So a learned method is still
needed for SEARCH. It CAN be pushed to 76.4 % at zero widening, but only by
discarding **15.75 %** of the designs that meet S3, and a test pins the verdict
in BOTH directions. What it actually removes is **84.3 % of the G44 population**
(488 of 579 designs with no interior peak). **A FINDING THE BRIEF DID NOT ASK
FOR: the primary metric has a CEILING that belongs to the AC sweep, not the
circuit** -- `meas ac MAX` reports on a 0.066439-octave lattice and `S3_f_peak`
is the binding reward row, so **no design can score above +8.950669**; derived
analytically, then measured as **four different designs all scoring 8.950670**.
Best-reward-at-budget therefore SATURATES on P1, so the harness also reports
simulations-to-ceiling. **A 1992-simulation PILOT (7.4 h, 33 runs) moved two
inputs: 8 workers buy 1.80x, NOT session 17's 2.98x** (that number came from
isolated evaluations; here each worker also runs CMA-ES/GP/torch between
simulations), which took the sweep from 11.2 h to 14.2 h and forced a re-cut to
**25 500 simulations = 12.0 h** -- the cut falling on PROBLEMS, never on seeds
or the per-run budget; and **A PRE-REGISTERED FALSIFICATION CONDITION FIRED --
the pre-screen does not fully transfer.** Its population rates hold
(free rejection 61.7 -> 63.9 %, lift 2.60 -> 2.66x) but its ACCURACY does not
(f_peak MdAPE 4.93 -> **15.85 %**, peaking bias -0.009 -> **+0.361 dB**, false
rejection 0.39 -> **3.88 %**, 10x over its declared budget), and **widening
cannot fix it** -- at 2.5x the widening it is still 2.33 % while free rejection
falls 64 -> 40 %. **A window cannot absorb a bias.** The mechanism is specific
and checkable: the gm/I_D model was fitted on an IDEAL-TAIL population where
`I_D` is exactly `i_bias/2`, and the real mirror delivers **4-8 % less**
(session 13). The re-fit is deliberately NOT done on a 3-seed pilot. **The
sweep is specified, costed, tested and reproducible by one command, and has NOT
been run.** The pilot was killed one job from the end and **every row survived
because the log streams** -- `--analyse` now rebuilds the whole analysis from
it, which matters far more for a 12-hour sweep. Its timing control never ran,
so **this pilot's wall-clock numbers are unvalidated by 7g's own rule** and its
simulation counts stand. **1246 -> 1292 green.** Full write-up
`nebula/BASELINES.md`; pre-registration `nebula/PREDICTIONS.md` entry 6,
committed BEFORE the run.
Earlier session 17: **the RL loop runs end to end, and
the six things that broke are the deliverable.** 500 PPO steps at TT with REAL
drawn passives (`to_geometry()` in the loop from the outset, so the output is a
schematic), 26.5 min, 793 SPICE calls, 765 evaluations. **NO CONCLUSION ABOUT
LEARNING IS DRAWN** — mean episode return goes -2.98 / -6.16 / -4.54 / -3.09 /
-0.50 across five buckets, non-monotone, and nothing was tuned to improve it.
**THE HEADLINE IS THE FAILURE CATALOGUE.** Four of the six produce a plausible
number and raise nothing. The worst: **`has_interior_peak` is a CONJUNCTION
whose two terms reject different kinds of thing (G64)** — one is G44's
fictitious peak (`rl`=800: 1.08 dB of "peaking" at 19.95 GHz, `g_pk-g_top` =
-0.001), the other is a genuine-but-small maximum (`rs`=50: 0.165 dB at
1.318 GHz, a correct measurement of a circuit that does not equalise) — so
using it as a validity gate put the reward FLOOR across the whole low-peaking
bottom of the box, which is exactly where a random policy starts. Split into
`peak_is_sweep_edge`; `has_interior_peak` UNCHANGED because three experiments
publish counts with it. Then **`alter` fails silently on an element the netlist
no longer CONTAINS (G63)** — with drawn passives there is no `Rdeg`, so all 67
sweep settings return the FIRST geometry's numbers, exit 0. Then **two gates
that failed for the WRONG reason (G68)**: a one-sided sensitivity probe called
`i_bias` INERT when it had merely left the feasible region, and validity checks
ordered symptom-before-cause hid **159 of 203 invalidities** behind the wrong
label. Then **`shutil.which` cannot find this project's ngspice (G69)**, so the
only end-to-end test was silently skipping — and a skip reports as a pass.
**THE MEASUREMENT THAT JUSTIFIES THE WHOLE POISON-SAFE EVALUATOR: 78% of
everything the policy found was G44 (G65)** — 26.5% invalid overall, split
`peak_is_sweep_edge` 159 / `tail_triode` 28 / `pair_triode` 16 / nothing else,
and under a reward reading S3 peaking every one of those 159 would have scored
HIGH for a circuit with no peak. **THE 4d REGRESSION IS RUN AND IT MOVES A
PUBLISHED VERDICT (G66):** drawn passives shift `f_peak` by **0.1329 octaves
against the 0.12 octaves of centring slack** that selected design 432, always
in the same direction, via the `res_po` bottom plate putting **+1.4 to +24.3 fF
on a 32.6 fF `cl` (up to +75%)** while `g_dc` moves 0.0006 dB — **so the load
and corner screens both need re-running before "1 in 1890 is
corner-and-load-robust" can be repeated.** Also **`to_geometry` is
electrically stable and geometrically CHAOTIC (G67)**: 0.016% change in `rs`
flips the device, **15x area spread across a 0.16% resistance spread**, so
`PASSIVES.md`'s 1506 um^2 is a property of the quantiser. **WHERE THE WALL
CLOCK GOES, measured for the first time: 99.7% is the simulator** (env 1585.8 s
vs PPO update 3.5 s), and the extended trim costs **2.07 s/eval against
~0.33 s** on the nfet-only one — **making `PASSIVES.md` §6 item 6 the highest-
value throughput item in the project**, with a number behind it at last. Cost
accounting DEFINED and binding afterwards: every invocation counted including
setup and discards — **1.586 sims/step, 1132 steps/hour**. **G70: one
concurrent ngspice makes each run 4.8x slower**, which invalidated this
session's own reward-v1 timings (discarded; only its load-independent results
are quoted). §6f's calibration orders correctly — 432 **+8.951 FEASIBLE**, flat
**-1.155**, op-fail **-8.000 exactly at the floor** — but did NOT before the
fixes above. §6e: **9/9 action dimensions live**, and `vcm_in` is a **6x
stronger lever on the tail margin than `tail_j`**, which is evidence FOR
`TAIL_DEVICE.md` §6's "do not search the tail". §6b: nothing broke removing the
mocks (they were already test-only), and the check runs in a SUBPROCESS with a
companion test proving it can fail; the real risk it pins is that **the link
layer is a mock end to end, so S8 CANNOT be in the reward**. **THE SEVENTH
FAILURE, caught by arithmetic rather than by a gate (G71): the parallel sweep
reported 4.39x at 11 workers — BETTER than G48's 3.18x — and the tell was that
2 workers reported 2.55x, which two processes cannot do.** The 1-worker pass
ran FIRST on a cold file cache; reversing the order drops the baseline 2.7x and
the honest answer is **2.64x at 8 workers with 11 SLOWER than 8**, i.e. the
extended library scales WORSE than the nfet-only one and the curve turns down.
**The v1 wiring pass found a third category §6h has no name for: `saturation`
and `tail_saturation` are WIRED but structurally unable to be VIOLATED**, since
a triode design is rejected by the validity gate before the reward sees it — so
their gradient lives only in the feasible branch's margin term, and the
retraction's "tail needs its own shortfall" argument is delivered instead by the
ungraded invalid floor. Recommendation (a human's, rule 6): accept it, because
grading a triode design's small-signal numbers would be grading fiction (G24's
precedent). `params.py` untouched (rule 6). **1007 -> 1246 green.** Full
write-up `nebula/RL_SMOKE.md`; new gotchas **G63-G71**.
Earlier session 16: **the channel is a derived family
now, not an invented constant — and the compression verdict it decided is
worse than the number it replaces, not better.** `CHANNEL_DC_LOSS_DB = 1.0`
had no provenance, its own docstring said a human had to replace it, and
`BOUNDS_REDERIVATION.md` §2 says in a blockquote that **that constant, not the
circuit, decided the compression verdict**. It is **DELETED, not re-valued**
(a test greps every executable file in the tree), because **the name encoded
the mistake**: a lossy line's insertion loss at DC is essentially ZERO, and the
real low-frequency correction is not a channel property at all — it is the
transmitter's **specified -3.5 dB de-emphasis**. Replaced by
`IL_dB(f) = A*sqrt(f) + B*f` parameterised by **(loss at Nyquist,
skin/dielectric split)**, 7 x 3 = 21 members, **minimum-phase** via the
real-cepstrum fold of `ln|H|` and **gated** on pre-`t=0` energy. **THE DECISIVE
RESULT: a 1-tap DFE IS SUFFICIENT across the whole 3-12 dB family** — the eye
is open at all 21 members, all three de-emphasis settings, with and without a
CTLE (worst residual 0.847 bare / 0.613 with the Gen2 mandate / 0.276 with a
matched CTLE), so **S3's top of range and S8 can both be met with S2's
topology**. **But the mechanism is not reassuring: only 14.7% of what the DFE
cannot reach is in `h2`, and 31.2% sits BEYOND 20 UI** — a second tap buys 15%,
a twenty-tap DFE still leaves 31%, so **the CTLE is the block that has to do
this work**. **The mandated de-emphasis is worth EXACTLY 3.5 dB of the CTLE's
job**, so the burden spans **-0.5 to +8.5 dB**: the **top 3.5 dB of S3 is never
called for**, and at 3/4.5/6 dB of loss the burden is BELOW S3's 3 dB floor.
**THE COMPRESSION RE-RUN (66 SPICE runs, reproduction gate 5/5 on the published
reference device): the 1.22x at 3 dB SURVIVES VERBATIM under its own
convention** — because that convention reads Nyquist content through Nyquist
gain and neither the deleted constant nor the de-emphasis touches either — **so
§2's blockquote was right about the C3 table and wrong to imply the headline
hung on it. Measured honestly (peak distortion through the real pulse
response), 3 dB is 1.51x and 5 of 7 loss points compress**, against the old
"two lowest points, 1.22x and 1.04x". **HANDOFF §8's compression line is
REPLACED IN PLACE.** Two further results: **S8's 100 mV vertical is met with
the CTLE ATTENUATING 13-15 dB** (8.6x more gain available than needed — S8
vertical has never been binding and now we can say so with a pulse response
behind it); and **the §6 design equations over-predict the Nyquist boost by
+0.77 to +1.47 dB** because they neglect `r_o`, which put the first compression
table 28% high before it was calibrated out (**G60**). New gotchas **G59** (a
magnitude-only channel is non-causal — 48% of its energy at t<0 — and raises
nothing; the power-law test that tells aliasing from a broken reconstruction),
**G60**, **G61** ("compression ratio" has three definitions here and they
disagree by 1.8x) and **G62**. **725 -> 1007 green.** Full write-up
`nebula/CHANNEL_MODEL.md`; prediction vs outcome `nebula/PREDICTIONS.md` entry
4, where **four of nine supporting predictions are recorded misses** and one
pre-registered falsification condition **FIRED**: the stated reflection probe
adds +0.122 at 12 dB, taking the channel-only eye to **81 mV, below S8's
floor** — so **every residual in this task is a LOWER BOUND**.
Earlier session 13: **the tail is a real transistor, and
the assumption it replaced was worth 8.8% — not the missing coupled
constraint.** The tail had been TWO IDEAL CURRENT SINKS in every simulation
this project ever ran, which is why every corner spread was an UNDERSTATEMENT
and every yield an OPTIMISTIC bound (G47), and why three of nine box dimensions
had no provenance. It is now a **current mirror**: one device per side (a
shared tail would short out the Rs/Cs degeneration), gates from a
diode-connected reference at ratio N=8. **`I_ref` is the one remaining ideal
element**, declared. **THE RESULT: the corner-and-load-robust yield did not
move — 1/1890 before and after, and it is the SAME design** (index 432,
identical parameters); 15 255 SPICE runs, 35.2 min. What the ideal tail cost is
**8.8% of the corner-robust-at-some-load population** (160 -> 146) and **zero**
of the headline. Next to what was already measured: **the PVT corners cost 39%,
the LOAD range 99.4%, the ideal tail 8.8%** — the load is still binding by a
wide margin, and **HANDOFF §8's claim that the tail was "the one experiment
that could still turn corner robustness into a real constraint rather than a
tax" is RETIRED **GIVEN THE CURRENT SCREEN** — the 8.8% is measured on a
population the LOAD had already cut by 99.4%, so **the tail is MASKED, not
unimportant**, and it must be re-read off the VIOLATION table the moment the
load screen narrows to a tolerance band. `tail_saturation` IS a genuine
coupled inequality — `vds_tail` IS the input pair's source node, so it ties
**VCM, W_in, L_in, i_bias and the tail geometry into ONE inequality**, the only
row in the spec table coupling five box coordinates — but it binds on
2.6-13.3% of the box. **The transferable finding is methodological: "which spec
binds" has TWO meanings and they disagree by an order of magnitude** —
`tail_saturation` is VIOLATED by 13.3% at ss/0.95/125C and RANKED WORST by
1.5%, because it misses by tens of millivolts while `S3_f_peak` misses by
17 GHz. The first-failure table systematically hides any constraint that
travels with a larger one; `s9_yield.py` now prints a violation table beside
it. Three further results: **the mirror delivers 4-8% LESS than requested and
that is physics** (channel-length modulation across a 0.7 V vds mismatch), so
S6 is billed on MEASURED supply current; **tail noise is NOT common-mode in
this topology** — S5 rises 1.61x to 0.442 mV with the two tails at **66% of
the noise POWER**, while the mirror REFERENCE (whose noise really is
common-mode) is rejected to 2e-21, because S2 needs one sink per side and two
devices have independent noise; and **`w_tail`/`l_tail`/`nf_tail` now have
provenance and the recommendation is NOT to search them**, keeping the action
space at nine dimensions (`TAIL_DEVICE.md` §6; `params.py` untouched, rule 6).
7 of 9 pre-registered predictions held; **2e and half of 2g are recorded
misses**. New gotchas **G53** (the SKY130 bin ceiling is on W per FINGER, not
total width — so `w_in`'s own provenance describes a per-finger limit as a
total) and **G54** (`.noise` can return `-nan(ind)` and exit 0; caught only by
accident). **618 -> 679 green.** Full write-ups `nebula/TAIL_DEVICE.md`,
`nebula/S9_YIELD.md` §9, `nebula/PREDICTIONS.md` entry 2.
Earlier session 12b: **the LOAD, not the corner set, is
the binding constraint — and it is not close.** Screening `cl` over the derived
range instead of pinning it at 150 fF takes the corner-robust yield from
**8.20% to 0.05% — one design in 1890** [0.01, 0.30]. Same box, same seed, same
1890 designs (`headroom_ok_1v8` never reads `cl`, so the comparison is paired).
15 255 SPICE runs, 49.3 min. **Corners cost 39% of the nominal winners; the
load range costs 99.4%.** The mechanism is the useful part and it was
pre-registered: the per-load sets are **large and DISJOINT** — 43 designs are
corner-robust at `cl_lo` alone, 118 at `cl_hi` alone, **160 at SOME load
(8.47%, i.e. essentially 10d's 8.20%) and 1 at BOTH.** 159 of 160 are robust at
exactly one edge. **The prediction's NUMBER held (predicted 0-10, measured 1);
its REASONING did not** — f_peak moves as `cl^-0.349`, not `cl^-0.5`, so the
1.84x = 0.88-octave shift is SMALLER than S3's 1.00-octave window, and the
yield is near zero for a different reason: **146 of 200 designs (73%) lose
their interior peak entirely across the load range** rather than moving out of
the window, and the 27% that keep it have only 0.12 octaves of centring slack —
about 2 of the 15 distinct f_peak values the window holds (session 11). The
single survivor tolerates 13.6-78.0 fF, i.e. **at least 5.72x and at most
7.76x** — it fits with less than one ladder rung of margin. New gotcha **G52**
(a resolution ladder that does not contain the points the verdict was made at
can contradict it — the first tolerance number, 4.32x, did, and was nearly
published). `.gitignore` amended: `s9_yield_results.json` is now TRACKED (G49's
rule, applied). **592 -> 618 green** (+26 in `test_s9_yield.py`). Full write-up
`nebula/S9_YIELD.md` §8; prediction vs outcome `nebula/PREDICTIONS.md`;
`params.py` untouched (rule 6).
Earlier session 12a: **`cl` has a physically derived
range, and every corner number this project has published was measured
1.92x above the top of it.** `cl` was pinned at 150 fF because that maximised
the S3 yield among five values tested — `CL_SENSITIVITY.md` §6 flagged that as
choosing the answer. Deriving it instead from what actually loads the CTLE
output (the 1-tap DFE summer input pair + the slicer input pair + routing)
gives **cl_lo 13.64 fF, cl_mid 32.63 fF, cl_hi 78.04 fF — a 5.72x range, 2.52
octaves**, entirely below the 150 fF pin. 180 SPICE runs, 16 s. Three results:
(1) **`@m[cgg]` is NOT the gate load — it understates it 1.9-2.7x** by
excluding the overlap capacitance and the Miller multiplication of C_gd, so
the load is measured as the AC current the driver must supply into the gate,
cross-checked against the primitives to 1.0% median (**G50**); (2) **the
sizing sketch moves the load 5.9x while the process corner moves it 1.16x**,
so the range is wide because the next stage is undesigned, not because silicon
varies — and **the corner that loads the node most (`fs`) is the one with the
LEAST gm**, the inverse of the device ordering; (3) a **half-rate front end
gives cl_hi = 141.8 fF**, i.e. the 150 fF pin was the right number for a
topology S2 does not describe. Full write-up `nebula/CL_RANGE.md`;
`params.py` untouched (rule 6) and §8 of that file is the proposal.
**528 -> 592 green** (+64: `test_cap_probe.py` 36, `test_cl_range.py` 28).
`nebula/PREDICTIONS.md` is new and carries the pre-registered prediction for
session 12b, committed before that experiment runs.
Earlier session 11 + 11b: **corner robustness is not a
property of where a design sits in the parameter BOX; it is a property of where
it sits in the SPEC WINDOW** — 7560 SPICE runs, 23 min, re-simulating 10d's
population from its seed and reproducing 10d's counts exactly. Splitting the
255 nominal winners into the 155 corner-robust and the 100 corner-fragile:
**every box coordinate is a null** (q > 0.16, and the two purpose-built
interiority statistics are the LEAST significant rows at q = 0.98), so the
"robust designs are interior in the box" hypothesis is **FALSIFIED**; but
**both S3 axes separate the groups once FOLDED onto distance-to-nearer-edge**,
and neither does before — f_peak margin **0.325 vs 0.126 octaves**
(p = 2.8e-12), peaking margin **2.70 vs 0.86 dB** (p = 3.2e-11), while the raw
medians are identical to four figures. The methodological lesson, which is the
transferable part: **a two-sided spec makes its own raw coordinate
uninformative**, because top-edge and bottom-edge failures sit on opposite
sides of any median and cancel. The usable output is a **joint filter — f_peak
margin >= 0.133 oct AND peaking margin >= 1.0 dB gives 92.1% [86.5, 95.6]
corner-robust against a 60.8% base rate**, keeping 140 of 255; either alone
reaches only ~75%, and both come free from an AC run the evaluator already
does. Proposal only, for the SEARCH — `params.py` untouched (rule 6), and
`ROBUST_GEOMETRY.md` §7 lists the three caveats a human must weigh (ideal tail,
in-sample thresholds, and that a 1 dB peaking margin bans the endpoints of
S3's own tunable range). Also: **f_peak is quantised at 0.0664 octaves** by
`meas ac MAX` on an `ac dec 50` grid, so the one-octave window holds exactly 15
distinct values and finer margins quote the sweep setup. Full write-up
`nebula/ROBUST_GEOMETRY.md`. **481 -> 528 green** (+47, all
`test_robust_geometry.py`; verified twice in 11b, 98 s and 95 s).
Session 11b landed it as `de874db`, which also carries the sessions **10c and
10d work that had never been committed** (the G44 peak-detector fix,
`s9_yield.py`, `S9_YIELD.md`), and restores §9's gotchas, which an earlier
commit had truncated from ~415 lines to 77. See G49.
Earlier session 10d: **the corner-robust yield is
measured — 20 205 SPICE runs, 47 min.** The same 1890 designs give **13.49% at
TT/27C, 8.20% [7.05, 9.52] across three corners, 8.10% [6.95, 9.41] across all
45**, and cross-tabulating design by design shows **100 of the 255 nominal
winners (39.2%) fail at a corner**, with 0 going the other way. Quote it as a
**tax on the baseline**, not as a coupled constraint — S9 was listed as the
cheapest route to replacing the argument G40 retired, and it did not deliver
one. What it did deliver is three reusable results: **three corners are worth
98.7% of forty-five** and the screen can only ever be wrong in one direction,
so budget the RL reward at 3-5 corners and put the full sweep in a verification
tier (G47); **the worst corner is FAST-hot, not slow-hot**, because S3 is a
two-sided spec and its two edges sit on opposite sides of the process axis
(G46); and **11 cores buy 3.2x, not 11x** — ~100 ms per corner evaluation, flat
past 8 workers (G48). Health: 0 hard failures, 0 retries, 0 screen/promotion
mismatches. **All of it is an OPTIMISTIC bound because the tail is still two
ideal current sinks**, which is why the tail transistor is now the top open
item in §8. Full write-up `nebula/S9_YIELD.md`; `params.py` untouched (rule 6).
444 (session 10b) -> **481 green**, of which
29 are `nebula/tests/test_s9_yield.py`. See G46, G47, G48.
Earlier session 10b: **`cl` is a BAD SEARCH DIMENSION —
removing it from the search RAISES the S3 yield.** Pinning `cl` at 150 fF and
holding every other bound takes the random-search yield from
**8.73% [7.54, 10.09] to 13.54% [12.08, 15.16]**, disjoint 95% intervals, on
2000 paired LHS samples. The optimum is bracketed (50/100/150/250/400 fF gives
8.73/11.27/13.54/12.06/9.52%), so 150 fF is a real interior maximum, though not
separable from 250 fF at this n. Mechanism: `cl` trades peak MAGNITUDE against
peak LOCATION and location wins up to ~150 fF, after which the load pole stops
relocating peaks and starts extinguishing them. **Second result, and it
sharpens G40:** the RAW coupling factor falls 1.05 -> 0.68 across the sweep
while the conditional-on-a-peak one stays flat at 0.97-1.06 with **every one of
the five 95% intervals covering 1.00** — so the raw statistic is unstable and
contaminated, and there is no measured coupling anywhere. **Third, and it must
not be buried: this makes G3 HARDER**, because the random-search baseline RL
has to beat rises from ~11 samples per hit to ~7.
Full write-up `nebula/CL_SENSITIVITY.md`; `params.py` untouched (rule 6).
430 -> **444 green**. See G42, G43.
**All coupling numbers above are POST-G44-FIX (session 10c) and supersede the
first pass**, which reported a 1.10x [1.02, 1.20] adverse effect at 100 fF —
an artifact of a peak detector that counted sweep-edge maxima as real and
inflated the has-peak population by up to 42%. The S3 yields themselves barely
moved. See G44 (fixed) and G45 (transient ngspice failures under load).
Earlier session 10a: **this checkout is a git repository
again, and for the first time its history is CLEAN of the copyrighted PDFs.**
Session 9d ended with a note that `git init` had never been run here, so the
"update HANDOFF in the same commit" rule could not be honoured mechanically.
It is now: `main`, one initial commit, 102 files, committed as
`Jai Kaushik <jaikaushik-prog@users.noreply.github.com>` (G12). The ten
reference PDFs/DOCXs are gitignored and were verified absent from the index
BEFORE committing, which means G1's "a public version must strip them from
HISTORY" no longer applies to this tree — there is nothing to strip. Tests
430 green before and after (nothing executable changed). See G41.
Earlier session 9d: the START HERE item is CLOSED. Bounds
re-derived on the corrected 1.8 V SKY130 bias and the S3 yield re-run —
**8.73%**, not 5.3%. But the headline is a **negative result: the "S3 is a
coupled constraint" argument is falsified.** Measured as a box-independent
statistic — P(A)·P(B) vs P(A and B) across three box widths — the **coupling
factor is 1.04x**, i.e. the two S3 conditions are INDEPENDENT. The low yield is
just one low marginal (f_peak lands in-window 16% of the time). That sentence
must not go in the abstract. Also: `2*I*RL` understated the available swing
~2x and the real limit is current steering, not headroom (measured 1.43 Vpp
linear / 2.28 Vpp ceiling); the compression verdict was partly a fixed-boost
artifact; a 3.3 V device is rejected on f_T; and `nf` does NOT multiply width
on SKY130. Full write-up: `nebula/BOUNDS_REDERIVATION.md`.
407 -> **430 green**. Earlier session 9: CLAUDEwa.md corrected in four places
(§6 body effect, §3 binding constraints, new §8 rule 9, bound provenance);
the §6 cross-check moved out of `.control` into Python where it can actually
fail, with captured-output fixtures and a falsifiability test; **SKY130
installed and simulating via volare — G29 cleared**, and it independently
re-confirms the body-effect finding with gmbs/gm = 0.40; NRZ retarget fixes
1-3 landed behind a `modulation` flag. Then 9b: `alter` proved silently wrong
for device geometry, and a **trimmed SKY130 library** cut an ngspice run from
16-35 s to 0.42 s, bit-identical. Then 9c (hand-sizing at the terminal): the
G1 bias point was found **badly mis-biased at gm/I_D = 1.7** with the sources
below ground; corrected to gm/I_D = 8.4, which moves DC gain from -6.4 dB to
+5.1 dB and makes **compression, not noise, the binding problem**.
315 nebula + 92 existing = **407 green** (+2 slow, deselected by default).
Earlier session 8: G1 hand-design audited against
ngspice — §6's gain equation found to fail its own gate without the body-effect
term; parameter bounds measured at 5.3% S3 yield and two bound errors fixed;
SKY130 blocker precisely diagnosed. 267 nebula + 65 existing = 332 green.
Earlier session 7 + addendum: Nebula G0 gate PASSED —
ngspice 41 in a conda env, all four analyses run; `.disto` found unusable for
BSIM4, HD3 must come from transient+FFT (175x cost spread across fidelity
tiers, measured). Link-layer compression bug and channel DC-loss
inconsistency both fixed; reference sizing verified against S8. 255 nebula
tests + 65 existing = 320 green.)

---

## 1. What this project is

A **simulation and design framework for a 112G PAM-4 SerDes receiver** —
the chip-to-chip link technology used in AI datacenters (56 Gbaud, 4-level
signaling, ADC-based DSP receiver, 28 nm CMOS reference parameters).

- **Owner:** Jai Kaushik, BITS Pilani EEE undergraduate
  (GitHub: `jaikaushik-prog`; commits use `jaikaushik-prog@users.noreply.github.com` — see Gotcha G12).
- **Supervisor:** research professor at BITS Pilani who provided the original
  materials (papers + starter code). The professor receives progress via
  figures + explanations; the owner is a **beginner in this domain** — when
  working with them, explain changes in plain language, one at a time.
- **Origin:** the owner received a folder of research papers, video links, and
  a starter codebase (~6.8k lines) built by previous students. The starter
  code looked complete but contained many correctness bugs (see §5).
- **Long-term goal (scope deliberately open):** a credible link-design
  methodology + verified RX DSP architecture; potential thesis/paper; possible
  scaled FPGA/shuttle demonstrator. NOT a competitive commercial PHY (that
  requires a large team and advanced nodes — documented expectation).
- **NEW DIRECTION (2026-07-23) — UCIe group project.** The professor pointed the
  owner at `hussin-mohamed/UCIE_GP` (a UCIe 3.0 *logical/digital* PHY: RTL +
  UVM — link-training FSM, sideband, TX path with byte-to-lane + LFSR scramble
  + serializer, RX path). That repo **explicitly excludes the analog front-end**
  (no channel/driver/CTLE/FFE/DFE — "signal integrity and channel modeling out
  of scope"). The group's task is to **build the analog electrical PHY around
  it**, split into 6 parts: (1) channel (2) serializer (3) driver (4) CTLE
  (5) DFE (6) FFE. **The owner has taken FFE.** Professor confirmed the target
  is the **high-data-rate DSP-equalization regime** (NOT light UCIe short-reach
  NRZ) — so this framework's 112G PAM-4 DSP-RX context IS the intended context,
  and `equalizers.py` (FFE/DFE joint LMS) + `pam4_chain.py` (TX-FFE) are the
  starting points. See §8 item 0 and Session 5.
- **GitHub:** https://github.com/jaikaushik-prog/serdes-dsp-framework —
  **PRIVATE, and must stay private** (contains copyrighted PDFs, see G1).

## 2. Repository map (what every file/folder is)

```
├── .gitignore              ← sectioned BY REASON (copyright / redistribution /
│                             regenerable), not by extension. Keeps the ten
│                             copyrighted reference PDFs out of history (G1,
│                             G41) and the SKY130 tree out of the repo. One
│                             explicit `!` un-ignore: our own trimmed library.
├── HANDOFF.md              ← this file. Update it every session.
├── CLAUDE.md               ← instructs AI agents to read + maintain HANDOFF.md
├── CLAUDEwa.md             ← NEW (2026-08-03). Contract for the **Nebula**
│                             competition track (Astera Labs x BITS Goa,
│                             RL-driven CTLE sizing, 5 Gbps PCIe Gen2).
│                             Separate project; own spec table, gates and
│                             rules. Read it in full before touching nebula/.
├── README.md               ← REWRITTEN 2026-08-06 (session 14b). The public
│                             landing page. WAS the inherited starter-code
│                             README, which advertised ten never-run
│                             directories as working features and claimed 48
│                             tests against 698 — see G55. Now carries the
│                             two-project table, a measured-results table where
│                             every row links to its write-up, gate status, and
│                             an explicit "Not audited" section. If you add a
│                             capability, add it here; if you retire one,
│                             remove it here.
├── PLAN.md                 ← NEW (2026-08-17, session 21b). The TEAM's
│                             operating plan for the 29 days to submission:
│                             three lanes (RL / analog / delivery), the seven
│                             DECISIONS with owners and deadlines, phase gates,
│                             and the cut order if time runs short. SUPERSEDES
│                             `nebula/NEXT_STEPS.md`'s ordering — its steps 1
│                             and 3 are done — but not its per-step prompts.
├── decisions.md            ← NEW (2026-08-17, session 19b). The decision
│                             register: what was decided, why, what it cost,
│                             and where it is written down. Grouped framing /
│                             spec-reading / method / device / toolchain /
│                             link / RL / benchmark. Two sections exist nowhere
│                             else: §I the eight RETRACTIONS, §J the eight
│                             decisions still waiting on a human (rule 6).
│                             Introduces no number of its own.
├── flow.md                 ← NEW (2026-08-17, session 19b). The pipeline, with
│                             the state of every arrow marked — including the
│                             one that is a MOCK (device→link, i.e. G2). Also
│                             the 13-step single-evaluation walkthrough, the
│                             experiment protocol, and what is uncommitted in
│                             the working tree. A reading aid, not a contract.
├── docs/PROGRESS.md        ← NEW (2026-08-06, session 14b). The progress
│                             board: session-by-session, question asked ->
│                             what was found, for a reader with zero context.
│                             This is what a mentor or teammate reads instead
│                             of HANDOFF's 3,400 lines. A SUMMARY — where it
│                             disagrees with HANDOFF, HANDOFF wins.
├── nebula/README.md        ← NEW (2026-08-06, session 14b). Reading order for
│                             the nine Nebula write-ups + the layout + the two
│                             things that look like bugs and are not.
├── docs/ROADMAP.md         ← full audit of the original code + phased plan
│                             with per-phase completion status. Keep in sync.
├── python_models/          ← THE CORE. All validated work lives here.
│   ├── pam4_chain.py       TX: PRBS (LFSR), self-sync scrambler (x^58+x^39+1),
│   │                       Gray mapping, TX-FFE, tx_waveform() = oversampled
│   │                       waveform w/ TX bandwidth pole + RJ/SJ jitter
│   ├── channel.py          PCB-trace loss model (skin+dielectric), S-param
│   │                       import hook (unused; needs scikit-rf), apply() =
│   │                       frequency-domain waveform filtering, PAM4 BER theory
│   ├── rx_frontend.py      CTLE (1z/2p, calibrated peaking), AGC, CDRSampler:
│   │                       closed timing loop, TWO architectures (see §6),
│   │                       TI-ADC mismatch + quantization at the sampling
│   │                       instant, estimate_delay() cross-correlator
│   ├── equalizers.py       FFE + DFE (joint single-pass LMS receiver), MMSE
│   │                       warm start (mmse_init_ffe), MLSE (Viterbi),
│   │                       fractional FFE, adaptive thresholds
│   ├── adc_model.py        Standalone ADC characterization (ENOB/SINAD, TI
│   │                       spurs). NOTE: the LINK uses the sampler's inline
│   │                       quantization, not this file's convert() chain.
│   ├── statistical_eye.py  Semi-analytic BER engine (StatEye-class): exact ISI
│   │                       PMF, correlated-noise w'Rw, bathtub, RJ folding,
│   │                       crossing_jitter_ui() CDR-feasibility metric,
│   │                       clip_probability(), optimize_ctle()
│   ├── link_sim.py         Top harness. LinkConfig dataclass = single source
│   │                       of config for BOTH engines. Modes: single,
│   │                       sweep_snr, sweep_loss, monte_carlo, jtol,
│   │                       statistical, optimize. CLI flags incl. --cdr_arch.
│   ├── make_report_figures.py  Generates figs 1-8 into results/ from sweep
│   │                       CSVs (caches some; delete CSV to force recompute)
│   ├── modulation.py      NEW (2026-08-04). The symbol alphabet as ONE object
│   │                       (PAM4 | NRZ). Every alphabet-dependent constant is
│   │                       DERIVED from `levels` — mean_square, max_level,
│   │                       symbol_probability, rms — so PAM-4's E[a^2] comes
│   │                       out at exactly the 5.0 that used to be hard-coded.
│   │                       Default is PAM4 everywhere; that is what keeps the
│   │                       existing suite green. NOTE only crossing_jitter_ui
│   │                       reads it so far — see NRZ_RETARGET_AUDIT.md.
│   ├── ml_equalizer.py     PyTorch LSTM/GRU/CNN equalizers. NOT INTEGRATED,
│   │                       NOT VALIDATED. Future work (needs equal-complexity
│   │                       benchmark vs FFE/DFE/MLSE).
│   ├── optical_dsp.py      IM-DD + coherent DSP models. NOT AUDITED YET.
│   ├── cdr.py              Standalone CDR study models (older). The LINK uses
│   │                       rx_frontend.CDRSampler, not these. Partially
│   │                       superseded; keep for reference.
│   ├── visualization.py    Older plotting helpers. Partially superseded by
│   │                       make_report_figures.py. NOT AUDITED.
│   └── results/            Generated CSVs + PNGs (gitignored). Regenerate:
│                           run sweeps then make_report_figures.py
├── nebula/                 NEW (2026-08-03). The Nebula competition track:
│   ├── BOUNDS_REDERIVATION.md  NEW (2026-08-04). Closes the START HERE item:
│   │                       the 1.8 V box with per-edge provenance, the 8.73%
│   │                       yield, the measured output swing, the fixed-vs-
│   │                       matched boost comparison, the 3.3 V rejection —
│   │                       and §4, which RETRACTS the coupled-constraint
│   │                       argument. Read §4 before writing any deliverable.
│   ├── CL_SENSITIVITY.md   NEW (2026-08-04). What `cl` does to the S3 yield,
│   │                       measured by pinning it. Removing cl from the search
│   │                       RAISES yield 8.73% -> 13.54%; the optimum is
│   │                       bracketed at ~150-250 fF. Also the cleanest
│   │                       demonstration that a RAW coupling factor tracks the
│   │                       no-peak fraction (G43). Read §5 before touching the
│   │                       action space and §7 before quoting any coupling
│   │                       number.
│   ├── CL_RANGE.md         NEW (2026-08-06, session 12a). Where `cl` comes
│   │                       from. Derives it from the gate load of the stages
│   │                       the CTLE drives instead of pinning it at the
│   │                       yield-maximising 150 fF: **13.64 / 32.63 /
│   │                       78.04 fF, a 5.72x range** whose TOP is 1.92x below
│   │                       the value every published corner number used.
│   │                       Read §2 before measuring any gate capacitance
│   │                       (`@m[cgg]` is not it, G50), §3 for what actually
│   │                       moves the load (the sketch, not the corners), and
│   │                       §9 before quoting a yield derived from it.
│   ├── CHANNEL_MODEL.md    NEW (2026-08-07, session 16). The channel, DERIVED
│   │                       from S3 instead of invented. Retires
│   │                       `CHANNEL_DC_LOSS_DB`. Read §0 (the four sentences),
│   │                       §2 before trusting any phase (the causality gate
│   │                       and how it tells aliasing from a broken
│   │                       reconstruction, G59), §5 for THE answer — a 1-tap
│   │                       DFE is sufficient across 3-12 dB, but only 15% of
│   │                       what it cannot reach is in h2 — §6 before quoting
│   │                       any compression number (three conventions, they
│   │                       disagree 1.8x, G61), and §8 + §12 before quoting
│   │                       ANYTHING: reflections are excluded and they push
│   │                       the 12 dB eye below S8's floor.
│   ├── PREDICTIONS.md      NEW (2026-08-06). Pre-registered predictions,
│   │                       committed BEFORE the experiment they are about,
│   │                       with the outcome written in afterwards whichever
│   │                       way it went. Entry 1 predicts a near-ZERO
│   │                       corner-and-load-robust yield, against the stated
│   │                       expectation of 8.73-13.54%. Precedent: G40 and
│   │                       10b's failed f_p2 prediction.
│   ├── TAIL_DEVICE.md      NEW (2026-08-06, session 13). The tail transistor,
│   │                       measured. Closes the ideal-current-sink assumption
│   │                       that made every S9 number an optimistic bound
│   │                       (G47). Answer: it was worth **8.8%** of the
│   │                       corner-robust population and **zero** of the
│   │                       headline yield. Read §0 first (I_ref is still
│   │                       ideal; matching is not modelled), §2 for the
│   │                       coupling identity vds_tail == v(source), §4 before
│   │                       repeating "tail noise is common-mode" (it is not,
│   │                       in this topology), and §6 for the three box edges
│   │                       — which recommend NOT searching any of them.
│   ├── S9_YIELD.md         NEW (2026-08-05). Corner-robust yield: 3-corner
│   │                       screen -> 45-corner promotion, with CIs, the
│   │                       measured parallel speedup, and — the actual
│   │                       headline — WHICH SPEC FAILS FIRST at each corner
│   │                       and by how much. 13.49% at TT -> 8.20% at 3
│   │                       corners -> 8.10% at 45, so **39% of nominal
│   │                       winners are corner-fragile** (§4), three corners
│   │                       are worth 98.7% of forty-five (§3, G47), and the
│   │                       worst corner is fast-hot not slow-hot (G46).
│   │                       Read its assumptions section first: the tail is
│   │                       still ideal, so every corner spread in it is an
│   │                       UNDERSTATEMENT.
│   ├── ROBUST_GEOMETRY.md  NEW (2026-08-05, session 11). WHERE the
│   │                       corner-robust designs live. Splits 10d's 255
│   │                       nominal winners into the 155 robust and 100
│   │                       fragile and asks what separates them. Answer:
│   │                       **not the parameter box (every coordinate is a
│   │                       null, q > 0.16, and the two interiority statistics
│   │                       are the LEAST significant rows at q = 0.98) but
│   │                       the SPEC WINDOW** — and only once both S3 axes are
│   │                       FOLDED onto distance-to-nearer-edge, because raw
│   │                       f_peak and raw peaking carry no information at all
│   │                       (identical medians). Joint filter f_peak margin
│   │                       >= 0.133 oct AND peaking margin >= 1.0 dB gives
│   │                       92.1% corner-robust vs a 60.8% base rate. Read §7
│   │                       before touching the reward shape, and §0 first:
│   │                       it is a RE-SIMULATION (G49), thresholds are
│   │                       IN-SAMPLE, and the tail is still ideal.
│   ├── experiments/robust_geometry.py  the session-11 experiment. Reproduces
│   │                       10d's population FROM THE SEED and asserts the
│   │                       published counts before analysing anything
│   │                       (`check_reproduction`; main() refuses to draw a
│   │                       figure on a mismatch). Owns the statistics —
│   │                       tie-corrected Mann-Whitney U, Benjamini-Hochberg,
│   │                       the octave margin, the normalised box position —
│   │                       all pure and all tested. `--collect` re-simulates
│   │                       (7560 runs, ~23 min); without it the analysis and
│   │                       figures run from the CSV with NO simulator.
│   ├── experiments/robust_geometry_data.csv  TRACKED ON PURPOSE (G49). The
│   │                       per-design table behind ROBUST_GEOMETRY.md: 1890
│   │                       rows, lossless `repr` floats, TT measurements plus
│   │                       the four corner verdicts. This is the file whose
│   │                       absence for S9 cost 23 minutes to rebuild.
│   ├── figures/            PNGs for the write-ups. robust_s3_plane.png is the
│   │                       one that carries session 11 on its own: all 255
│   │                       designs pass S3 at TT, and only the ones away from
│   │                       the window edges survive three corners.
│   ├── experiments/s9_yield.py  the corner-AND-LOAD sweep. Owns the three
│   │                       ASSUMPTIONS (since 12b: cl SCREENED over the
│   │                       CL_RANGE.md range, not pinned; VCM does not track
│   │                       VDD; ideal tail) and prints them in every run's
│   │                       header. Three stages now: nominal x 2 loads,
│   │                       screen 3 corners x 2 loads, promote 45 x 3.
│   │                       `--tolerance-only` runs the PREDICTIONS.md
│   │                       follow-up off the committed JSON in ~3 min.
│   │                       `CL_LEGACY_PIN_F` = 150 fF is kept ONLY so 10d/11
│   │                       stay reproducible.
│   ├── experiments/s9_yield_results.json  TRACKED since 12b (G49's rule
│   │                       applied, .gitignore amended): S9_YIELD.md §8 quotes
│   │                       numbers from it, so it is an INPUT to the write-up. VDD scaling lives in
│   │                       `point_at_corner` and nowhere else; temperature is
│   │                       a `.temp` card via `run_point(temp_c=)`. Retries
│   │                       once on failure (G45) and prints a `health:` line
│   │                       per stage so the denominator is never implicit.
│   │                       `screen_augmentation()` names which corner would
│   │                       have caught each of the screen's false positives,
│   │                       so the screen is re-cut from data, not intuition.
│   │                       Writes results NEXT TO THE SCRIPT, not the cwd.
│   ├── experiments/s3_yield.py  the random-search baseline, as a coupling
│   │                       factor rather than a bare percentage. Carries
│   │                       PROPOSED_BOX (not yet in params.py — rule 6).
│   │                       `--cl-fixed F` pins one axis by overwriting that
│   │                       coordinate of the SAME seeded LHS design, so runs
│   │                       are PAIRED. Every rate carries a two-sided Wilson
│   │                       95% interval; the coupling factor carries a
│   │                       percentile bootstrap (resolution ~+/-10% at n=2000).
│   ├── experiments/cl_range.py  session 12a. The `cl` derivation: the sizing
│   │                       SKETCH (4 loading stages, each with its reasoning
│   │                       and a MIN_STAGE_GAIN >= 1 gate that fired for
│   │                       real), the PDK-derived routing allowance (read out
│   │                       of SKY130's own vpp cap model, one declared design
│   │                       rule), and `derive_cl_range()` — pure, so the whole
│   │                       thing re-runs from the CSV with no simulator.
│   ├── experiments/cl_range_data.csv  TRACKED ON PURPOSE (G49). 180 rows:
│   │                       every (stage, corner, temp, output common mode)
│   │                       measurement behind CL_RANGE.md.
│   ├── device/cap_probe.py  session 12a. What a following stage presents to
│   │                       the CTLE output, measured as the AC current the
│   │                       driver must supply into one gate under
│   │                       DIFFERENTIAL drive — not `@m[cgg]`, which
│   │                       understates it 1.9-2.7x (G50). Cross-checked
│   │                       against parsed primitives + the model card's own
│   │                       overlap constants (`analytic_load_ff`), and
│   │                       `sanity_check_load` REJECTS a point that
│   │                       disagrees, is out of saturation, or is not
│   │                       capacitive. PDK constants are READ from the model
│   │                       file, never re-declared (rule 9), and the reader
│   │                       raises on a parameter the 180 bins disagree on.
│   ├── device/tail.py       NEW (2026-08-06, session 13). The tail current
│   │                       source as a REAL DEVICE: a mirror, one tail per
│   │                       side (a shared tail would short the degeneration),
│   │                       reference derived as N MATCHED UNIT FINGERS.
│   │                       Owns the per-finger bin ceiling (G53) and the
│   │                       bias-node bypass (G54). A geometry outside the bins
│   │                       RAISES here rather than reaching ngspice.
│   ├── experiments/tail_device.py  session 13. Five stages: --identity (three
│   │                       checks that can each FAIL, incl. the coupling
│   │                       identity vds_tail == v(source)), --sweep (261 runs,
│   │                       the sizing rule), --noise (per-instance
│   │                       attribution), --rout (what the tail does to S3),
│   │                       --bounds (the three box edges, derived from the
│   │                       CSV). `--report` re-runs the analysis with NO
│   │                       simulator.
│   ├── experiments/tail_device_data.csv  TRACKED ON PURPOSE (G49). 261 rows
│   │                       behind TAIL_DEVICE.md sections 3-6.
│   ├── device/pdk_trim.py   NEW (2026-08-12, session 19). Generates
│   │                       device/spice/pdk_trim/. The R/C corner decks drag
│   │                       in parameters/typical.spice — 3023 lines defining
│   │                       8909 named parameters, of which the extended
│   │                       library references 86. Keeps those 86, closed over
│   │                       right-hand sides; drops 8823. The keep-set is READ
│   │                       OUT OF THE LIBRARY's own include list, so adding a
│   │                       device widens it automatically and the regeneration
│   │                       test goes red until someone reruns the module
│   │                       (rule 9, and the answer to G32). `--write` to
│   │                       regenerate; no argument to report and check.
│   ├── experiments/lib_cost.py  NEW (2026-08-12, session 19). What the trim
│   │                       bought, on 50 real designs through run_point, with
│   │                       G71's full protocol (discarded warm-up, arm order
│   │                       re-shuffled PER DESIGN, control re-run last). Also
│   │                       asserts the two extended arms agree at rel=0 abs=0
│   │                       on 11 fields and exits non-zero if not. FIVE arms,
│   │                       each differing from its neighbour in ONE thing, so
│   │                       the differences decompose an evaluation's cost
│   │                       additively. `_no_section_libraries()` is not
│   │                       optional -- without it the "before" arms are served
│   │                       the split library (G77).
│   ├── experiments/lib_cost_results.json  TRACKED ON PURPOSE (G49). The five-arm
│   │                       timing + the equivalence check behind LIB_COST.md.
│   ├── LIB_COST.md         NEW (2026-08-17, session 19a write-up). Where an
│   │                       evaluation's time goes, and the correction of a
│   │                       cost explanation that was wrong in both halves for
│   │                       four sessions (G78). Read §2 before quoting any
│   │                       per-evaluation cost, and §7 before dividing this
│   │                       ratio into anything parallel (G75).
│   ├── device/gmid_lut.py   NEW (2026-08-17, session 20). The SKY130 nfet as a
│   │                       MEASURED table: `.dc` V_gs sweeps indexed on
│   │                       (process, temp, W, L, V_ds, V_sb), storing nine .op
│   │                       PRIMITIVES; gm/I_D, f_T, gm*ro computed in Python
│   │                       (rule 10). 3000 invocations, 510 s at 6 workers.
│   │                       **W is an AXIS, not a scaling reference** -- the
│   │                       classical W-independence premise is measured FALSE
│   │                       here (G79). NOT a replacement for
│   │                       prescreen.predict_gm; they answer different
│   │                       questions and a test holds them together.
│   ├── device/data/gmid_lut_sky130_nfet01v8.npz  TRACKED ON PURPOSE (G49),
│   │                       27.6 MB, un-ignored explicitly in .gitignore.
│   │                       Regenerable: `--build --workers 6`.
│   ├── common/design_space.py  NEW (2026-08-17, session 20). The inverse map,
│   │                       PURE: (gm_over_id, l_in, i_bias, f_z, k, rl,
│   │                       vcm_in) -> the seven device coordinates. Seven in,
│   │                       seven out, SAME dimension as ACTION_SPACE on
│   │                       purpose. Bias solve is a fixed point with an
│   │                       explicit cap; every failure NAMED, nothing clamped.
│   │                       Imports GmidLut TYPE-ONLY so common/ keeps no
│   │                       runtime dependency on device/.
│   │                       **NOT WIRED INTO THE RL LOOP** (rules 5, 6).
│   ├── experiments/exp_gmid_validation.py  NEW (2026-08-17, session 20). Two
│   │                       arms, same sampler and evaluator: the approved
│   │                       device box against the design box. 1500 each.
│   │                       Design box DERIVED as the measured image of the
│   │                       device box, not chosen (rule 6). `--analyse` runs
│   │                       with no simulator.
│   ├── link/fit.py         NEW (2026-08-17, session 21). The pole-zero FIT --
│   │                       measured AC curve -> (g_dc, f_z, f_p1, f_p2) +
│   │                       residual, REJECTED above 0.5 dB (§5.3b). Exact on
│   │                       synthetic data; basin probed from +/-2 decades.
│   │                       Poles come back ORDERED because §6 gives them
│   │                       different meanings.
│   ├── link/bridge.py      NEW (2026-08-17, session 21). THE G2 DELIVERABLE.
│   │                       `device_result_from_point` is the adapter that had
│   │                       never existed (only device/mock.py built a
│   │                       DeviceResult); `evaluate_link` is the real one.
│   │                       Volts end to end, so §5.3a needs no conversion;
│   │                       compression is a VALIDITY condition (C4), checked
│   │                       on the pulse response's own peak excursion
│   │                       (G61 convention C).
│   ├── experiments/exp_g2_closed_loop.py  NEW (2026-08-17, session 21).
│   │                       `--tiers` (G2's cost criterion), `--funnel` (300
│   │                       box samples through the whole chain), `--example`
│   │                       (one vector to an eye). Carries the G2 worked
│   │                       example, FOUND BY THE SEARCH not hand-picked.
│   ├── G2_RESULTS.md       NEW (2026-08-17, session 21). Gate G2, PASSED.
│   │                       Read §0 then §7 -- §7 is what it does NOT license
│   │                       (TT-only, a BER BOUND with device noise only, no
│   │                       1e-15 bathtub, S7 a lower bound).
│   ├── GMID_MAP.md         NEW (2026-08-17, session 20). The write-up. Read
│   │                       §0 and §8 first: the motivating mechanism is
│   │                       measured FALSE and the recommendation is not to
│   │                       adopt before G2.
│   ├── device/sky130_runner.py  one SKY130 point, four analyses (.op .ac
│   │                       .noise .dc), one call. Owns the two unit
│   │                       conversions (metres->microns, i_bias->per-side)
│   │                       and the MEASURED swing (G37).
│   │                       RL-driven CTLE sizing. Contract = CLAUDEwa.md.
│   │                       INTERFACES + MOCKS + G0 SPICE PROBES. No PDK, no
│   │                       RL yet. Independent of python_models/ by design.
│   ├── G0_RESULTS.md       G0 gate: PASSED. ngspice 41 env, all 4 analyses,
│   │                       and the .disto/BSIM4 finding (G21). Read before
│   │                       writing the ngspice wrapper.
│   ├── NRZ_RETARGET_AUDIT.md  All 24 four-level assumptions in python_models/,
│   │                       risk-marked, with a recommended order of work.
│   ├── device/spice/       netlists + the PDK plumbing:
│   │                       .spiceinit          ngbehavior=hsa (PARSE-TIME, G29)
│   │                       sky130_nfet_only.lib.spice  TRIMMED SKY130, all 5
│   │                                           corners. 0.42 s vs 16-35 s,
│   │                                           bit-identical (G36). USE THIS.
│   │                       sky130_ctle.lib.spice  the EXTENDED trim: nfet +
│   │                                           poly R + MIM, 25 sections =
│   │                                           5 MOS x 5 PASSIVE corners
│   │                                           (G58). Needed the moment
│   │                                           to_geometry() output reaches a
│   │                                           netlist.
│   │                       pdk_trim/           GENERATED, do not edit (G77).
│   │                                           The 5 R/C corner decks with
│   │                                           their parameter includes cut
│   │                                           from 3021 lines to 43. Derived
│   │                                           by device/pdk_trim.py and
│   │                                           re-derived byte for byte by
│   │                                           test_pdk_trim.py.
│   │                       ctle.cir            hand-sizing sandbox, interactive
│   │                       g1_handdesign.cir   generic BSIM4 1.2 V reference
│   │                       g1_sky130_volare.cir  SKY130 1.8 V, full lib
│   │                       g1_sky130.cir       SUPERSEDED (raw repo, G29)
│   │                       g0_diffpair.cir (4 analyses), g0_disto_control.cir
│   │                       (BSIM4 vs level=1 A/B), g0_hd3_tran_fft.cir
│   ├── common/types.py     Frozen §5.1 contracts: Corner, TargetSpec,
│   │                       DeviceResult, LinkResult + the §3 spec constants
│   │                       and the 45-corner S9 grid. ok=False is a VALUE;
│   │                       numeric fields are None on failure, never nan.
│   ├── common/params.py    Action-space NAMES (§5.2). BOUNDS deliberately
│   │                       EMPTY — param_space() raises until a human fills
│   │                       them from the G1 hand-design (§8 rule 6).
│   ├── common/design_equations.py  §6 pole/zero/gain equations (incl. the
│   │                       gmbs body-effect term) + cross_check_extraction().
│   ├── device/crosscheck.py  NEW (2026-08-04). The §6 gate, in PYTHON, where
│   │                       it raises. Parses ngspice stdout; refuses to run on
│   │                       output containing warning-shaped failures
│   │                       (scan_for_silent_failures). Replaces the .control
│   │                       block that exited 0 while computing nothing (G26,
│   │                       G30). derived_ac() separates peaking_db from
│   │                       nyquist_boost_db — they are not the same number.
│   ├── device/ngspice_runner.py  batch-mode driver: netlist template ->
│   │                       subprocess -> parsed SpicePoint.
│   ├── tests/fixtures/     REAL captured ngspice output (3 files): the G1
│   │                       BSIM4 point, the SKY130 point, and the historical
│   │                       BROKEN run that exited 0. Lets the parser and the
│   │                       gate be tested with no simulator, in 0.2 s. Plus
│   │                       sky130_full_lib_golden.json = 20 points from the
│   │                       FULL library, the reference the trimmed one is
│   │                       held to.
│   └── tests/              315 tests. Needing a simulator: test_trimmed_lib.py
│                           (equivalence of the trim) and test_noise_units.py
│                           (inoise_total is RMS VOLTS, verified against
│                           4kTR*BW; do NOT square-root it). Both skip cleanly
│                           if ngspice or the PDK is absent.
│   ├── device/interface.py evaluate() protocol, safe_evaluate (exception ->
│   │                       ok=False), reject_bad_fit (§5.3b, >0.5 dB).
│   ├── device/mock.py      SYNTHETIC square-law stand-in. NOT A PDK. Every
│   │                       number fake. Physically coherent trends only.
│   ├── link/calibration.py THE normalised->volts conversion (§5.3a). The
│   │                       single highest-risk silent bug in that project.
│   ├── link/config.py      LinkConfig for the nebula flow.
│   │                       channel_loss_db_at_nyquist has NO default (it is
│   │                       the swept axis). Owns the PCIe Gen2 anchors: the
│   │                       0.8 Vpp swing and the -3.5/-6 dB de-emphasis, each
│   │                       with its provenance note. `channel_loss_db_at_dc`
│   │                       is a DERIVED property returning exactly 0.0 since
│   │                       session 16 — it was a field defaulting to an
│   │                       invented 1.0 dB constant.
│   ├── link/channel.py     NEW (2026-08-07, session 16). The channel FAMILY:
│   │                       IL_dB(f) = A*sqrt(f) + B*f, parameterised by
│   │                       (loss at Nyquist, skin/dielectric split), with
│   │                       minimum-phase reconstruction and CAUSALITY,
│   │                       PASSIVITY and MONOTONICITY gates. Also `Stackup`
│   │                       (loss -> equivalent length, never the reverse), a
│   │                       stated two-reflection probe, and the Touchstone
│   │                       ingestion path for real data. NO random element at
│   │                       all, so LinkConfig.seed never enters it.
│   ├── link/tx.py          NEW (2026-08-07). The PCIe Gen2 transmitter as the
│   │                       2-tap FIR it is: -3.5 dB mandated, -6 dB option,
│   │                       normalised so the TRANSITION bit carries full
│   │                       swing. Supplies EXACTLY -de_emphasis_db of tilt at
│   │                       Nyquist, so `equalisation_burden_db` is an exact
│   │                       subtraction. Imports the swing anchor; never
│   │                       redeclares it (rule 9).
│   ├── link/cursors.py     NEW (2026-08-07). Pulse response -> UI sampling at
│   │                       the h0-maximising phase -> h_-2..h_4 -> residual
│   │                       ISI after an ideal 1-tap DFE -> eye. Owns the
│   │                       CLOSED-FORM CTLE peak location and the exact
│   │                       peak-existence condition 1/fz^2 > 1/fp1^2 + 1/fp2^2
│   │                       (session 9c's finding, stated exactly).
│   ├── experiments/channel_family.py  session 16. Four stages: --gates
│   │                       (causality/passivity per member), --cursors (the
│   │                       headline table), --reflections, and --compression
│   │                       (the ONLY stage needing ngspice). The compression
│   │                       stage REPRODUCES the published reference device
│   │                       before analysing anything and aborts on a mismatch
│   │                       (5/5, G52's shape), and calibrates the CTLE model
│   │                       to the MEASURED boost because §6 is 0.8-1.5 dB
│   │                       optimistic (G60).
│   ├── experiments/channel_family_data.csv  TRACKED ON PURPOSE (G49). 114
│   │                       rows: every (channel, de-emphasis, CTLE) cursor set
│   │                       behind CHANNEL_MODEL.md §5.
│   ├── link/mock.py        SYNTHETIC device->link bridge. Equalises the
│   │                       BURDEN (channel tilt - TX tilt), not the raw tilt.
│   ├── rl/reward.py        §9 shortfall reward, worst-corner aggregation.
│   │                       KEPT: it is the CLAUDEwa §9 contract. Superseded
│   │                       for the RL loop by reward_v1.py — see HANDOFF §8's
│   │                       reward retraction.
│   ├── rl/contract.py      THE ENVIRONMENT CONTRACT (session 17). Nine
│   │                       ActionDims with per-edge provenance (7 copied
│   │                       verbatim from s3_yield.PROPOSED_BOX, 2 from
│   │                       TAIL_DEVICE.md §6 — params.py untouched, rule 6),
│   │                       the 20-dim observation layout, and the FIXED
│   │                       normalisation scales. nf_in is fixed at 4 (G38) and
│   │                       the tail is a current DENSITY, not a width.
│   ├── rl/evaluator.py     THE POISON-SAFE EVALUATOR. One sizing point -> a
│   │                       validated measurement vector or a NAMED invalidity;
│   │                       nothing in between. Checks run cause-before-symptom
│   │                       (G68). Owns SpiceBudget, which counts EVERY
│   │                       invocation including setup and discards.
│   ├── rl/env.py           The episode: horizon 8, early-terminate on success,
│   │                       terminate on an invalidity (never default, never
│   │                       retry into a different answer). gym-SHAPED, no gym
│   │                       dependency — neither gymnasium nor SB3 is installed.
│   ├── rl/reward_v1.py     The §6h shape: sum of clipped shortfalls while
│   │                       infeasible, B + min margin once feasible. Seven
│   │                       tolerances in units where 1.0 means "meaningfully
│   │                       off", each quoted. NO analytic quantity in the path.
│   ├── rl/ppo.py           Minimal PPO in torch, ~150 lines. Every constant is
│   │                       a PPO-paper or SB3 default, written down. NOTHING
│   │                       TUNED. Worth 0.2% of a run's wall clock (G65 note).
│   ├── rl/runlog.py        JSONL run log. Row 0 is a HEADER row, not a separate
│   │                       file, so a log cannot be read without its conditions.
│   ├── device/netlist_gates.py  §6a's two gates, on the ASSEMBLED netlist text:
│   │                       `w` on a fixed-width resistor family (G57) and
│   │                       `mult`/`mf` != 1 (G56). Both are ACCEPTED by ngspice,
│   │                       IGNORED by the model, and followed by exit 0.
│   ├── experiments/rl_smoke.py  session 17, task 6. Five stages, each gating
│   │                       the next: --regression-4d (PASSIVES.md §6 item 1),
│   │                       --sensitivity (BLOCKING), --calibrate, --train,
│   │                       --parallel. Owns the three §6f reference designs.
│   ├── experiments/rl_smoke_run_v0.jsonl  TRACKED ON PURPOSE (G49). 782 rows,
│   │                       1.5 MB: every (action, sizing, geometry, raw result,
│   │                       validated result, reward) with a design_id — free
│   │                       training data for task 8's surrogate.
│   └── tests/              228 tests, <1 s. Run: python -m pytest nebula/tests -q
├── tests/                  pytest suite — 92 tests, ~1.5 min. THE safety net.
│   │                       Run from REPO ROOT: python -m pytest tests -q
│   ├── conftest.py         puts python_models/ on sys.path
│   ├── test_pam4_chain.py  PRBS/Gray/scrambler/TX-coherence/Wilson bound
│   ├── test_channel_adc.py IL vs analytic, BER theory vs Monte Carlo, SQNR
│   ├── test_equalizers.py  MMSE init, FFE/DFE convergence, MLSE exactness
│   ├── test_rx_frontend.py CTLE peaking/noise-enhancement, CDR lock/track
│   ├── test_statistical_eye.py  PMF properties, closed-form check,
│   │                       CROSS-VALIDATION of the two engines, optimizer
│   └── test_link_e2e.py    full-link regressions incl. mm_postffe cases
├── rtl/                    SystemVerilog: 32-parallel FFE+DFE+SS-LMS
│                           (ffe_dfe_lms.sv), BB-CDR + PRBS BER checker
│                           (bb_cdr_ber.sv). WRITTEN, NEVER SIMULATED. Phase 4.
├── verification/           UVM testbench skeleton. NEVER RUN. Phase 4.
├── veriloga_models/        Verilog-A TIA/CTLE/VGA/ADC/PD for Cadence. UNRUN.
├── ams/, scripts/cadence/  Spectre TB + Ocean scripts. Require Cadence. UNRUN.
├── matlab_models/          dsp_verify.m algorithm cross-checks. NOT AUDITED.
├── ffe_learning/           NEW (2026-07-23). Owner's FFE teaching sandbox for
│   └── ffe_demo.py         the UCIe project (§8 item 0). Self-contained demo
│                           (numpy/scipy/matplotlib) that visualizes ISI ->
│                           eye closing -> zero-forcing FFE -> eye reopening +
│                           channel/FFE/combined freq response (ffe_demo.png).
│                           Does NOT touch validated python_models/. Not a test.
├── *.pdf, *.docx           Reference library (see §3). COPYRIGHTED — do not
│                           redistribute; keep repo private.
├── PCI.2/                  GITIGNORED (2026-08-05). Nebula competition material
│                           supplied by the organisers: two handouts plus
│                           `nebula_ctle_rl_1.zip`, a reference PPO+CTLE
│                           implementation (src/env.py, reward.py, train.py, a
│                           generic 130 nm lib, a trained agent, a PVT report).
│                           On disk, out of history — not ours to redistribute.
│                           Worth READING before the RL work starts; do NOT
│                           anchor on its numbers (same rule as ams_rl_ppo,
│                           CLAUDEwa §4.2).
└── Makefile                Build automation (predates audit; NOT AUDITED).
```

## 3. Reference library (what the PDFs/docs are)

| File | Identity | Role |
|---|---|---|
| High-Speed_Wireline_Links Part I / II | Shakiba, Tonietto, Sheikholeslami, IEEE OJ-SSCS 2024 (invited) | **The core methodology** — reference link modeling (I) and optimization/BER assessment (II). The statistical engine follows this school. |
| Modelling (1).pdf | Davide Menin PhD thesis, Univ. Udine 2021 | Fully-adaptive equalization; the guide for Phase 3 joint-adaptation work (tap walking, loop interaction) |
| EECS-2019-143.pdf | Jaeduk Han PhD dissertation, UC Berkeley (Alon/Stojanović) | Automated 60G transceiver generation (BAG); circuit-generation reference |
| PAM4.pdf | Intel AN-835 PAM4 fundamentals | PAM-4 measurement definitions (levels, EH/EW, RLM) |
| PAM4 (1).pdf | Zhang et al., Xilinx, DesignCon 2016 | Practical 56G PAM4 link tradeoffs |
| Introduction.pdf | CERN intro-to-PAM4 slides | Background |
| A (1).docx | Substack-style overview of optical interconnects (IM-DD→CPO→coherent) | Optical track background |
| wireline-video-links.docx | Sheikholeslami lecture series + **Toronto StatOpt** tool links | StatOpt = the template for statistical_eye.py |
| `hussin-mohamed/UCIE_GP` (external GitHub, public) | UCIe 3.0 **logical/digital** PHY, SystemVerilog + UVM, 14 nm, 16 lanes, up to 32 GT/s NRZ forwarded-clock, 500 MHz logical clock | Digital-half reference for the new UCIe group project (§1 New Direction). Contains the **serializer + LFSR scrambler** RTL; NO analog blocks. Also a **gold-standard UVM verification template** (found/fixed 55+ RTL bugs) — relevant to §8 #5. |
| `Part 11 FFE.pdf` (professor's handwritten note, 12 pp) | The professor's own FFE lecture, sent to the owner after they chose FFE | **The syllabus/scope for the owner's FFE block.** Covers: 2-tap FFE + freq response (DC=1+a, Nyquist=1-a, high-pass boost); FIR/z-transform (unconditionally stable); RC toy example; **zero-forcing** matrix method + 3-tap worked example + general (2M+1)-tap form + limits (only sampled points -> no jitter fix, neglects far ISI); full-rate vs half-rate circuits; combiner (IDAC taps, sign bit, inductive peaking); **max boost = 1/(1-2K)** (K=1/3 -> 9.54 dB, verified), fixed by K not N; practical limits; sim (channel+FFE+eyes). NOTE: the 3-tap worked answer [-0.25,1.05,0.28] does not match the matrix as read (solve gives [-0.275,1.169,-0.243], post-tap sign flips) — confirm exact pulse-sample layout w/ professor. |

## 4. The simulated system (architecture + conventions)

Signal chain (waveform engine, `link_sim.run_link`):

```
PRBS → scramble → Gray/PAM4 → TX-FFE → ZOH ×OSR(8) → TX pole (0.75·fbaud)
 → TX jitter (RJ/SJ, time-warp) → channel H(f) → +AWGN (AT CTLE INPUT!)
 → CTLE (1z/2p) → gain calibration → CDR-driven sampler (closed loop,
   ppm offset, aperture RJ, 16-way TI mismatch, 6-bit quantization ±vref)
 → joint FFE(3+1+17)+DFE(5) single-pass LMS (supervised→DD at training_len)
 → Gray decode → bit errors vs LINE bits → BER + Wilson 95% bound
```

**Conventions you MUST know before touching code** (each earned by a bug):

- **Symbol units:** post-calibration, the cursor sample = 1.0, so PAM-4 levels
  sit at ±1/±3, slicer thresholds at −2/0/+2, ADC full scale = ±4.0
  (`adc_vref`). All slicer-domain sigmas are in these units.
- **Gain calibration** is pulse-cursor-based (scale = 1/pr[cursor]), NOT
  RMS-AGC — CTLE edge overshoot inflates RMS and compresses levels (G5).
- **Noise definition:** `noise_db` = SNR at channel output measured in the
  SYMBOL Nyquist band [0, fbaud/2]. Simulated white noise on the OSR grid
  therefore has total power P_sig·osr/SNR (factor osr is intentional).
- **Alignment:** samples[k + delay] carries symbol k, delay found by
  `estimate_delay` (cross-correlation, scans negative lags — CDR can slip
  whole UIs during acquisition). Inside the equalizer, decisions[k] is the
  decision FOR symbol k (FFE pre-cursor delay handled internally).
- **Reference bits:** `PAM4Transmitter.generate` returns LINE bits
  (post-scrambler) — these are coherent with the transmitted symbols. Raw
  PRBS bits are `.raw_bits` (comparing against them is bug G2).
- **Seeds:** ALL randomness flows from `LinkConfig.seed` via a
  `np.random.Generator`. Never call `np.random.seed()` (G3).
- **Both engines share `LinkConfig`** and build from the same calibration
  path (`StatisticalEye.from_link_config`) — that's what makes cross-
  validation meaningful. If you change the chain in link_sim, mirror it there.

## 5. Complete history (what was done, in order, with the WHY)

### Phase 0 — audit + correctness (commit `ce733a8` equivalent; authors later rewritten, see G12)
Bugs found in the inherited code and fixed:
1. **MC seeding no-op:** `np.random.seed(42)` inside run_link made all Monte
   Carlo runs identical.
2. **Scrambler not self-synchronizing:** fed the INPUT bit back into the LFSR;
   multiplicative scramblers must feed back the OUTPUT bit. Roundtrip failed.
3. **MLSE trellis inconsistent:** state decode used newest-symbol=MSB, state
   update wrote newest=LSB → SER 0.72 (random). One convention → SER 5e-4.
4. **TX reference incoherent:** returned pre-scrambler bits as the BER/training
   reference while transmitting scrambled symbols.
5. **PAM4 BER theory 2× high:** used erfc where Q was meant. Correct:
   BER = (3/8)·erfc(√(SNR/10)).
6. **FFE/DFE two-pass processing** reset delay lines at the training→DD switch;
   replaced with single-pass joint receiver, delay-aware references.
7. **README FEC target wrong:** claimed pre-FEC 2e-2; KP4 RS(544,514) needs
   ~2.4e-4 (802.3bs); 802.3dj concatenated ≈ 1e-3 class.
Plus: git init, .gitignore, 28 tests, Wilson-bound BER reporting.

### Phase 1 — honest waveform engine (commit `8cbd26a` equivalent)
- Oversampled waveform chain (OSR 8) replacing baud-rate-only shortcuts.
- Real CTLE with noise injected BEFORE it (noise enhancement modeled, tested).
- Closed CDR loop: **Alexander BB PD** (T/2 interpolated mid-samples, gated on
  symmetric transitions) + PI filter. Lessons (all documented in code):
  - Sign-MM on raw waveforms locks at the eye EDGE (h(−1)=h(+1) equilibrium).
  - Pattern-gated BB loop: effective integral gain ×(update gap); keep
    4·ki/kp ≲ 2% or it limit-cycles.
  - Gear-shift (P-only acquisition, then enable integrator w/ clamp) or the
    integrator winds up during acquisition → cycle slips → runaway.
  - Lock metric must check phase slope is explained by the freq word.
- MMSE warm start fixed: cursor placed at FFE's n_pre (was centred at
  n_taps/2 → 7-symbol reference misalignment, ~4 dB penalty), Wiener gain
  preserved, full-cyclic peak search.
- `adapt_start`: LMS held until after CDR acquisition (silicon bring-up order).
- JTOL mode; validation: 0 errors @ 28 dB/3 cm; JTOL corner ~1–3 MHz, 0.1 UI
  floor; lock lost ≥30 dB loss with 6 dB CTLE (honest architecture limit).

### Phase 2 — statistical engine (commit `83ee4bf` equivalent)
- `statistical_eye.py`: exact ISI PMF (per-tap 4-point shifted adds), slicer
  noise via wᵀRw with CTLE-colored autocorrelation at baud spacing, ideal-DFE
  cancellation, per-boundary Gray BER, bathtub, Gaussian RJ fold, eye widths.
- Cross-validation: engines agree within ~3× over BER 1e-1…1e-4 (statistical
  mildly conservative — reference-receiver assumptions). fig5.
- `optimize_ctle`: Part II-style sweep. **Finding #1: unconstrained slicer
  optimum on dispersive channels is 0 dB CTLE** (long digital FFE equalizes
  with less noise boost than analog peaking) **but that config was unlockable**
  → derived `crossing_jitter_ui()` = pattern-dependent zero-crossing jitter at
  the eye edge (edge-ISI σ / edge slope), calibrated vs time-domain lock
  outcomes: healthy <0.45 UI, boundary ~0.6–0.75 UI. Constraint added.

### Phase 3a — post-FFE MM PD + clipping discovery (commit `6c84e89` → `3aa5b28` after author rewrite)
- `CDRSampler pd_mode='mm_postffe'`: MM PD behind a FROZEN MMSE timing-path
  FFE (production arrangement; freezing sidesteps the FFE↔CDR tap-rotation
  degeneracy — true co-adaptation is future work). `LinkConfig.cdr_arch`.
- **MM sign lesson:** E[y_k·d_{k−1} − y_{k−1}·d_k] ∝ h(+1)−h(−1) = positive
  when EARLY; with this loop's convention (phase↑ = sample earlier) the raw
  product locks 0.5 UI off-centre. Negated + verified.
- Results: locks at 6 cm/0 dB (Alexander-infeasible) and 10 cm/6 dB
  (Alexander lock-lost); CDR jitter flat ~20 mUI across ALL CTLE settings vs
  28–75 mUI Alexander (fig8) — timing decoupled from AFE tuning.
- **Finding #2: ADC clipping is the real 0-dB-CTLE limiter** — 17 % of samples
  beyond ±4 full scale (peaks 7.65) → BER 2e-2 for BOTH architectures;
  explains the 1000× stat-vs-TD gap at that point (stat engine assumes a
  linear unclipped ADC). Added `clip_probability()` (exact, from pre-FFE ISI
  PMF incl. cursor), `adc_clip_frac` in run_link results, calibrated clip
  constraint (<12 %; 10 % survivable / 16 % fatal measured) in optimize_ctle;
  timing constraint is now architecture-aware.
- **Refined design rule: the CTLE is needed for timing health (Alexander arch)
  AND ADC dynamic range (any arch). Only the first is engineerable away.**

### Repo/GitHub (2026-07-18, latest session)
- Pushed to private GitHub repo. Commit authors REWRITTEN via filter-branch to
  `Jai Kaushik <jaikaushik-prog@users.noreply.github.com>` (original author
  email attributed commits to a wrong GitHub account) — hashes changed;
  current HEAD `3aa5b28`. See G12.
- Report figures 1–8 generated (`make_report_figures.py`); figs explained to
  the owner in plain language for professor communication.

## 6. Key numbers & validated behavior (current state)

- Tests: **1448 passing** (session 21) —
  `python -m pytest tests nebula/tests -q -m "not slow"`.
  (Was 65 + 267 = 332 at the start of session 9; 430 at the end of it; 444
  after 10b; 528 after 11; 618 after 12b; 679 after 13; 1007 after 16; 1246
  after 17; 1292 after 18; **1314** with session 19a's uncommitted trim tests;
  **1389** after session 20; **1448** after session 21 closed G2.) **11** further tests are marked `slow` and
  deselected by default — they re-derive golden values from the FULL SKY130
  library (~30 s each). Run them after a PDK update. **Note `CLAUDE.md` is
  STALE on this**: it says 407 tests and 2 deselected. **Runtime is machine-load dependent** — the same suite has
  taken 1.5 min on a quiet machine and 34 min while an 11-worker ngspice pool
  was running. A slow suite is contention, not a hang.
- **The gm/I_D design space: measured, not adopted** (session 20,
  `nebula/GMID_MAP.md`; 3000 LUT sweeps + 1810 evaluation SPICE invocations).
  Two arms, 1500 LHS samples each, same sampler and evaluator, TT/27,
  `cl_mid`, drawn passives and a real mirror:

        G44 % of designs that REACHED the simulator
          device coordinates   38.07 %
          design coordinates   37.74 %     <- the hypothesis, MISSED
        free rejection (design arm)   89.40 %, but 65 % of it is
                                      `current_unreachable` -- not a screen
        simulations per VALID design  1.90 -> 1.64   (1.16x, the real benefit)
        pre-simulation G44 filter     TN = 0 bare, TN = 8 with the ceiling

  Accuracy of the map against SPICE, design-arm VALID rows, measured minus
  requested: `g_dc` median **-0.20 dB** (inside CLAUDEwa §6's own 1 dB gate),
  `f_peak` median **-0.355 octaves**, `peaking` median **-0.933 dB**. At
  `k_alpha = 0.90` (G60-calibrated) the S3-window peaking bias improves
  **-0.816 -> -0.157 dB** while `g_dc` degrades **-0.181 -> -0.663 dB** --
  both read the same `k`, and that trade had not been priced before.
  **Not wired in; `params.py`/`contract.py`/`env.py` untouched.**
- **Measured output swing at the corrected point (session 9d).** 1 dB gain
  compression at **1427 mVpp** differential; saturation limit 2161 mVpp;
  steering ceiling 2281 mVpp; `4*I*RL` textbook value 2400 mVpp. Session 9c
  used `2*I*RL` = 1200 mVpp, which is **a peak read as a peak-to-peak** — the
  ceiling is `4*I*RL`. And the binding mechanism is **current steering, not
  headroom**: at the 1 dB point the pair still has vds 1.29 V against vdsat
  0.079 V. `DeviceResult.vout_swing_v` should carry the 1 dB number.
- **The G1 reference point is superseded (session 9c).** The published
  numbers — peaking 8.29 dB @ 1.259 GHz, 0.275 mVrms, 6.0 mW — are correct for
  what they describe, but that operating point runs at **gm/I_D = 1.7 V^-1**
  with its sources 0.44 V BELOW ground, which no real tail transistor can
  provide. Corrected bias: **W=40 nf=4, I_tail=1.5 mA, VCM=1.25 V, VDD=1.8 V,
  SKY130 -> gm 12.62 mS, gm/I_D 8.42, v(s1) +0.343 V, noise 0.275 mV.**
  The parameter BOUNDS and the 5.3% S3 yield were both derived inside the old
  bias and are **provisional until re-run**.
- **The honest random-search baseline is 8.73%** (165 of 1890 simulated, from
  2000 Latin-hypercube samples of the re-derived 1.8 V box), **95% CI
  [7.54, 10.09]**. It is a baseline for G3 to beat, not evidence of a
  mechanism. **It rises to 13.54% [12.08, 15.16] if `cl` is pinned at 150 fF
  instead of searched** (session 10b, `nebula/CL_SENSITIVITY.md`) — so which
  number G3 must beat is a live decision, not a fact.
- **Corner-robust yield, the same 1890 designs at 45 corners** (session 10d,
  `nebula/S9_YIELD.md`, 20 205 SPICE runs). **CONDITIONAL ON `cl` = 150 fF, a
  load the following stage cannot present — see the 12b entry above and
  S9_YIELD §8 before quoting any of it.** Not retracted: it is the right
  measurement of what the PVT corners alone cost, and G46/G47/G48 stand.
  **13.49% at TT/27C ->
  8.20% [7.05, 9.52] across three corners -> 8.10% [6.95, 9.41] across all
  45.** Cross-tabulated design by design: **100 of the 255 nominal winners
  (39.2%) fail at a corner**, and 0 designs fail nominal yet pass the corners.
  The quotable sentence is **"an optimiser scored at nominal is wrong about two
  of every five designs it calls a success"** — a tax on the baseline, NOT a
  coupled constraint (do not let it drift back into one; see G40). Two further
  results: **three corners are worth 98.7% of forty-five** (G47) and **the
  worst corner is fast-hot, not slow-hot** (G46). Health: 0 hard simulator
  failures, 0 retries, 0 screen/promotion mismatches across 465 repeated
  (design, corner) pairs. **Optimistic bound** — the tail is still ideal
  current sinks, so all corner spreads here are understatements.
- **Geometry of corner-robust designs** (session 11,
  `nebula/ROBUST_GEOMETRY.md`, 7560 SPICE runs re-simulating 10d's population).
  **Corner robustness is not a property of where a design sits in the parameter
  BOX; it is a property of where it sits in the SPEC WINDOW.** Splitting 10d's
  255 nominal winners into the 155 corner-robust and 100 corner-fragile:
  - **Every box coordinate is a null.** rs, cs, rl, i_bias, w_in, l_in, vcm_in,
    nf_in all have q > 0.16, and the two purpose-built interiority statistics
    (distance to the nearest box face, min and mean over dimensions) are the
    LEAST significant rows in the table at q = 0.98. **The "robust designs are
    interior in the box" half of the hypothesis is FALSIFIED.**
  - **Both S3 axes separate the groups once FOLDED onto distance-to-nearer-
    edge**, and neither does before: raw f_peak medians are 1.738 GHz in BOTH
    groups (q = 0.81) and raw peaking differs by 0.05 dB (q = 0.81), while
    f_peak margin reads **0.325 vs 0.126 octaves (p = 2.8e-12)** and peaking
    margin **2.70 vs 0.86 dB (p = 3.2e-11)**. A two-sided spec makes the raw
    coordinate uninformative by construction — the two failure modes point in
    opposite directions and cancel in any median. Starkest single number:
    **0 of 155 robust designs sit within 0.5 dB of a peaking edge, against 37
    of 100 fragile.**
  - **The usable output is a JOINT filter:** f_peak margin >= 0.133 octaves AND
    peaking margin >= 1.0 dB gives **92.1% [86.5, 95.6] corner-robust against a
    60.8% base rate**, keeping 140 of 255. Either condition alone reaches only
    ~75%. Both are computed from an AC run the evaluator already does, so the
    filter is free. **Thresholds are IN-SAMPLE** — a fresh seed would cost
    23 min and has not been run.
  - **Resolution limit:** `meas ac MAX` returns a grid sample and the sweep is
    `ac dec 50`, so f_peak is quantised at **0.0664 octaves** and the 1-octave
    S3 window holds only **15 distinct f_peak values**. Margin thresholds finer
    than that quote the sweep setup, not the circuit.
  Proposal only — `params.py` untouched (rule 6). Still an optimistic bound:
  the tail is ideal, so the required margins are lower bounds.
- **Corner-AND-LOAD-robust yield: 0.05%, one design in 1890** (session 12b,
  `nebula/S9_YIELD.md` §8, 15 255 SPICE runs / 49.3 min). The same 1890 designs
  as 10d, with `cl` screened over the derived range instead of pinned:

        nominal PVT, both loads      15/1890 =  0.79%   (was 13.49% at 150 fF)
        3 corners x 2 loads           1/1890 =  0.05%   (was  8.20%)
        45 corners x 3 loads          1/1890 =  0.05%   (was  8.10%)

  **Corners cost 39% of the nominal winners; the load range costs 99.4%.** The
  load is the binding constraint and it is not close. Mechanism, and it is the
  quotable part: **the per-load sets are large and DISJOINT** —

        corner-robust at cl_lo 13.6f alone    43/1890 = 2.28%
        corner-robust at cl_hi 78.0f alone   118/1890 = 6.24%
        corner-robust at ANY load            160/1890 = 8.47%  <- ~10d's 8.20%
        corner-robust at EVERY load            1/1890 = 0.05%

  **159 of the 160 designs robust at one load edge are not robust at the
  other.** The joint set is not small because the parts are small; it is small
  because they barely intersect (independence would have given 2.68).
  Two further results:
  - **`S3_f_peak`'s share of first failures is monotone in the load: 42% at
    150 fF, 57% at 78 fF, 84% at 13.6 fF.** Less load capacitance puts f_p2 and
    the peak higher, out through S3's 2.5 GHz top edge. S5 is still never the
    first failure; S6 twice in 11 340 runs.
  - **73% of designs LOSE their interior peak across the load range** rather
    than moving it out of the window, and f_peak moves as `cl^-0.349` (not the
    `cl^-0.5` that `CL_SENSITIVITY.md`'s single probe suggested), so the 0.88
    octaves of movement is SMALLER than the 1.00-octave window and leaves 0.12
    octaves of slack — ~2 of the 15 distinct f_peak values session 11 measured.
  The single survivor tolerates **13.6-78.0 fF, at least 5.72x and at most
  7.76x** — it fits the demanded range with under one ladder rung of margin,
  at `w_in 89.3 um, l_in 0.399 um, nf 8, i_bias 3.25 mA, rs 319, cs 1.90 p,
  rl 565, vcm 1.407`. Health: 0 hard failures, 0 retries, 0 screen/promotion
  mismatches; 192-199 ms per (design, corner, load) at 8 workers under load,
  against G48's 106 ms on a quiet machine. **Still an OPTIMISTIC bound — the
  tail is ideal** — and still a fixed-sizing score, so it is a lower bound on
  what S3's own R_s/C_s tunability could achieve (unmeasured).
- **The tail is a real transistor, and the ideal-tail assumption was worth
  8.8%** (session 13, `nebula/TAIL_DEVICE.md`, 15 255 + 261 SPICE runs).
  Every S9 number this project published carried "optimistic bound — the tail
  is two ideal current sinks" (G47). **Discharged:**

        corner-and-load-robust yield   1/1890 (ideal)  ->  1/1890 (real tail)
        and it is the SAME design, index 432, identical parameters
        robust at ANY load               160          ->    146   (-8.8%)
        headroom rejections               52          ->     52   (unchanged)

  What the tail cost, next to what was already known: **PVT corners 39%, the
  LOAD range 99.4%, the ideal tail 8.8%.** The load is still the binding
  constraint by a wide margin. **But 8.8% is CONDITIONAL — it is measured on a
  population the load screen had already cut by 99.4%, so the tail is MASKED,
  not unimportant.** Unconditionally it binds on 2.6-13.3% of the box. Re-check
  it off the VIOLATION table whenever the load screen narrows to a tolerance
  band. Five things worth carrying:
  - **The coupling identity is exact.** `vds_tail == v(source)` to 0 and
    `v(source) == VCM - Vgs_in` to 6e-17, so `tail_saturation` ties **VCM,
    W_in, L_in, i_bias and the tail geometry into one inequality** — the only
    row in the spec table that couples five box coordinates. It binds on
    **13.3% at ss/0.95/125C, 2.6% at ff/1.05/0C**.
  - **"Which spec binds" now has two meanings and they DISAGREE by an order of
    magnitude.** Ranked-worst vs ever-violated: `tail_saturation` is 13.3% of
    the second and 1.5% of the first, because it misses by tens of millivolts
    while `S3_f_peak` misses by 17 GHz. `s9_yield.py` prints both now; without
    the second table the tail reads as a 1% footnote.
  - **The mirror delivers 4-8% LESS than requested, and that is physics** —
    channel-length modulation across a 0.7 V vds mismatch between reference and
    tail. It moves with corner (-5.4% ff, -6.6% tt, -8.1% ss), which is exactly
    what an ideal sink could not do. S6 is billed on **measured** supply current
    now.
  - **Tail noise is NOT common-mode in this topology, and S5 rises 1.61x**
    (0.275 -> 0.442 mV_rms) with the **two tail devices at 66% of the noise
    POWER**. The common-mode argument is real and visible — the mirror
    REFERENCE is rejected to 2e-21 — but S2 needs one sink per side or the
    degeneration is shorted, and two devices have independent noise. Still
    passes: headroom 5.5x -> 3.4x against 1.5 mV.
  - **`w_tail`, `l_tail`, `nf_tail` now have provenance and the recommendation
    is NOT to search them** (`TAIL_DEVICE.md` §6): `w_tail` follows from
    `i_bias` by a current density (**105-124k um/A**, 1.18x drift across a 4x
    current change), `nf_tail` is near-dead (**0.6%**), `l_tail` spans one
    octave. Keeps the action space at nine dimensions rather than twelve.
    `params.py` untouched (rule 6).
  Two new gotchas, **G53** (the SKY130 bin ceiling is on W per FINGER) and
  **G54** (`.noise` can return `-nan(ind)` and exit 0). Also: session 11's
  margin thresholds were flagged as lower bounds because the tail was ideal —
  a rule-sized tail moves peaking by ~0.05 dB, below the 0.0664-octave
  quantisation, so **re-running `robust_geometry.py --collect` is now a
  low-value experiment.**
- **`cl` has a derived range, and it is entirely below the value every corner
  number used** (session 12a, `nebula/CL_RANGE.md`, 180 SPICE runs / 16 s).
  Derived from what physically loads the CTLE output — the 1-tap DFE summer
  input pair, the slicer input pair, and the wire:

        cl_lo   13.64 fF   (11.67 device + 1.97 routing)
        cl_mid  32.63 fF   (geometric mean; a screen point, not a claim)
        cl_hi   78.04 fF   (63.74 device + 14.29 routing)
        ratio    5.72x  =  2.52 octaves   vs S3's 1.00-octave f_peak window

  **The 150 fF pin behind 13.49 / 8.20 / 8.10 % is 1.92x above `cl_hi`.**
  Four things worth carrying:
  - **`@m[cgg]` is not the gate load (G50).** It is the INTRINSIC capacitance
    and excludes the overlap (`cgso = cgdo = 2.449e-10 F/m`) and the Miller
    multiplication of C_gd by the loading stage's gain. Measured
    understatement **2.00x / 2.52x / 2.70x** on the 4 / 12 / 16 um stages —
    it grows with gain, which is the Miller signature. At the 16 um stage
    **52% of the load is C_gd,overlap x (1 + |A|)**.
  - **The sizing sketch moves the load 5.9x; the process corner moves it
    1.16x, temperature 1.08x, the CTLE output common mode 1.04x.** The range
    is wide because the following stage is undesigned, not because silicon
    varies. Designing the slicer would narrow `cl` far more than any corner
    analysis.
  - **The corner that loads the node most has the LEAST gm.** C_in orders
    `fs` > `ss` > `tt` > `ff` > `sf`, exactly inverse to gm. Do not screen the
    load and the device at "the" worst corner — same shape as G46. (Also: for
    the nfet, `sf` behaves fast and `fs` slow; the label order is not
    (nfet, pfet).)
  - **A half-rate front end gives `cl_hi` = 141.8 fF** — the 150 fF pin was
    the right number for a topology S2 does not describe. Reported, NOT folded
    into the bound (rule 5).
  Cross-check: the AC measurement is reconstructed from `.op` primitives plus
  the model card's overlap constants to **1.02% median / 2.20% worst** over
  180 runs, and `sanity_check_load` rejects a point that disagrees by >5%.
  0 of 180 rejected. Proposal only; `params.py` untouched.
- **`cl` sensitivity, 2000 paired LHS samples per point** (session 10b). Pin
  `cl`, hold every other bound:

        cl        50f     100f     150f     250f     400f    (sampled 10-500f)
        S3      8.73%   11.27%   13.54%   12.06%    9.52%          8.73%
        A       52.65   48.52    46.14    39.26    33.54           48.47
        B       16.61   21.90    24.02    22.80    19.21           16.03
        peaks    1673    1559     1469     1313     1168            1578

  Both marginals turn over; A falls monotonically (the load pole eats peaking)
  while B rises then falls (the load pole first relocates the peak into the S3
  window, then extinguishes it). 150 fF is a genuine interior maximum but is
  NOT separable from 250 fF at this n. S5, S6 and the saturated fraction do
  not move at all with `cl`, as expected.
- **The channel is a derived family, and a 1-tap DFE is sufficient across it**
  (session 16, `nebula/CHANNEL_MODEL.md`; 21 channels x 3 de-emphasis settings,
  pure numpy, plus 66 SPICE runs for the compression re-run). `IL_dB(f) =
  A*sqrt(f) + B*f`, parameterised by **(loss at Nyquist, skin/dielectric
  split)** — 7 losses x 3 splits — with minimum-phase reconstruction and a
  stated causality gate. Loss at Nyquist read off S3's own 3-12 dB tunable
  range; **loss at DC is 0.0 by construction**, which is what the deleted
  constant got wrong.

        residual ISI a 1-tap DFE cannot reach, as a fraction of the cursor:
        worst anywhere (12 dB, skin, no de-emphasis)        0.847   eye OPEN
        worst in the PCIe Gen2 config (12 dB, skin, -3.5)   0.613   eye OPEN
        worst with a matched CTLE in front                  0.276   eye OPEN

  **The eye is open at every one of the 21 members, in every configuration**, so
  S3's top of range and S8 can both be met with S2's mandated topology.
  Five things worth carrying:
  - **A second DFE tap buys 15%; a twenty-tap DFE still leaves 31%.** At 12 dB
    skin-dominated only **14.7% of the residual is in `h2`** and **31.2% sits
    beyond 20 UI** — the `sqrt(f)` algebraic tail, which is exactly what a
    decision-feedback architecture is worst at. **The CTLE is the block that
    has to do this work**, not the DFE.
  - **A scalar cannot represent a channel, and it is now measured.** At a fixed
    loss at Nyquist, skin-dominated leaves **1.60x** the residual of
    dielectric-dominated at 12 dB and **1.99x** at 3 dB. The ratio is largest
    where the channel is EASIEST, which is the opposite of where one would look.
  - **The mandated -3.5 dB TX de-emphasis is worth exactly 3.5 dB** of the
    CTLE's job (the 2-tap FIR has gain `d` at DC and 1 at Nyquist by
    construction), so the burden spans **-0.5 to +8.5 dB**: the **top 3.5 dB of
    S3's range is never called for** on this family, and at 3/4.5/6 dB the
    burden is BELOW S3's 3 dB floor — the minimum setting over-equalises.
  - **S8's 100 mV vertical is met with the CTLE ATTENUATING by 13-15 dB**
    (required A_dc 0.181-0.217 V/V against a measured 1.79). S8 vertical is not
    binding and never has been.
  - **Every residual above is a LOWER BOUND.** A stated two-reflection probe
    (rho 0.05 at 2 UI, 0.02 at 5 UI) adds **+0.064 to +0.122**, and at 12 dB
    that takes the channel-only eye from 118 mV to **81 mV, below S8's floor**.
    Reflections are the ISI a DFE handles worst and the smooth form cannot
    represent them (`CHANNEL_MODEL.md` §8).
- **Compression, re-measured against the derived channel** (session 16,
  `CHANNEL_MODEL.md` §6). Reproduction gate on the published reference device
  passed 5/5 (gm 12.623 vs 12.62 mS, 1 dB swing 1426.9 vs 1427 mVpp). Matched
  boost, 14 of 66 (Rs, Cs) settings meeting S3:

        convention                                        compressing
        A  Nyquist content in, Nyquist gain out (9c/9d)      2 / 7
        B  long-run level in, peak gain out (C3)             7 / 7
        C  peak distortion through the REAL pulse response   5 / 7   <- use C

  **The 1.22x at 3 dB survives VERBATIM under convention A** — that convention
  never read the deleted constant, so `BOUNDS_REDERIVATION.md` §2's blockquote
  was right about the C3 table and wrong to imply the headline hung on it.
  **The honest number is 1.51x at 3 dB, and compression binds at 5 of 7 loss
  points**, still worst at LOW loss (where S3's floor forces boost the link does
  not need). **Prerequisite finding: the §6 design equations over-predict the
  Nyquist boost by +0.77 to +1.47 dB** (they neglect `r_o`), which put the first
  version of that table 28% high — see G60.
- Reference operating point: 3 cm (9 dB) channel, SNR 26 dB, CTLE 6 dB,
  Alexander: BER ≈ 1e-4; SNR 28: 0 errors (bound ~1e-4→ 8.7e-5 at 30k syms).
- Loss sweep (SNR 28, CTLE 6 dB): clean ≤12 dB; ~1e-2 at 24 dB; lock lost
  ≥30 dB (Alexander) / locks but BER-fails (mm_postffe).
- JTOL (3 cm): 1.0 UI below ~1–3 MHz, 0.1 UI floor above (grid-limited res).
- Optimizer @ 6 cm: 1.5 dB peaking optimum (both archs, constraints active);
  time-domain confirms 3.4e-4 there.
- CDR: tracks 50–100 ppm; Alexander jitter 26–35 mUI typical; mm_postffe
  ~17–23 mUI, flat vs CTLE peaking.
- Two engines agree within ~3× where both operate (fig5).
- Figures: results/fig1_eyes … fig8_arch_compare (+ link_run.png dashboard).

## 7. Known model limitations (honest list — do not overclaim)

- Statistical engine: ideal DFE (no error propagation), MMSE-designed FFE
  (assumes white noise in design, correlated in evaluation), Gaussianized
  quantization, NO clipping distortion in the BER itself (only a constraint),
  fixed rj_cdr=0.015 UI approximation in from_link_config.
- Time-domain: no CDR loop latency modeled (RTL has ~32-symbol parallelism
  latency → lower usable kp); TI gain error applied post-AGC; single-pole TX
  model; loss-model channel only (no reflections/crosstalk until .s4p data).
- **(nebula) The channel family is a CONSTRUCTION, not a measurement.** It is
  derived from S3 defensibly, and `link/channel.py::fit_from_touchstone` is the
  seam a real `.s4p` enters through — but any deliverable must say "constructed
  from the specification", never "the channel". It also contains **no impedance
  discontinuities**: no connectors, vias, stubs, crosstalk, mode conversion or
  fibre-weave skew. Reflections are the ISI a DFE handles worst, and the stated
  probe in `CHANNEL_MODEL.md` §8 shows they push the 12 dB channel-only eye
  below S8's 100 mV floor. Every ISI number from that family is a lower bound.
- **(nebula) EVERY corner and load result in this project holds the passives
  IDEAL, and session 17 measured that this is not a small assumption.** Drawn
  SKY130 devices move `f_peak` by up to **0.1329 octaves** — more than the
  **0.12 octaves** of centring slack that selected the sole load-robust design
  — in a single direction, via the `res_po` bottom-plate parasitic
  (G66, `RL_SMOKE.md` §7). The load screen and the corner screen both need
  re-running before design 432 can be quoted as load-robust.
- **(nebula) G2 IS PASSED, and everything in it is TT-only.** (Session 21,
  `nebula/G2_RESULTS.md`.) One design meets **all of S3-S8 at TT/27 C, nominal
  VDD, one load** — S9 is NOT claimed and is gate G4. The BER on this path is a
  **worst-case ISI bound with DEVICE NOISE ONLY**, `Q((eye/2)/sigma)`: no
  reference-clock jitter, no crosstalk, no TX noise, and the residual ISI
  treated as a deterministic subtraction rather than a distribution. At the
  worked example's SNR of 298 it UNDERFLOWS double precision and reports 0.0,
  which means "below ~1e-308", **not** "verified error-free" -- read the SNR.
  The 1e-15 bathtub is NOT delivered: `statistical_eye.py`'s NRZ path
  deliberately raises rather than reporting a BER 0.75x the truth from
  four-level mathematics. The eye WIDTH is a zero-height noiseless width
  quantised at 1/64 UI, i.e. a strict upper bound at any finite BER.
- **(nebula) The RL results are TT-only, one seed, one spec target, 500
  steps.** `RL_SMOKE.md` establishes that the plumbing works and what breaks;
  it establishes **nothing about learning**, and its §11 says so explicitly.
  S4, S7 and S8 are not in the reward — for stated reasons, and in S8's case
  because the link layer is a mock end to end and a training run structurally
  cannot reach it.
- **(nebula) The gm/I_D design-space map is TT-only, one seed, one load, and
  ITS TWO ARMS DO NOT SAMPLE THE SAME SET.** (Session 20,
  `nebula/GMID_MAP.md` §6.) The table carries three more corners; the
  validation experiment uses none of them. And the design box is the image of
  the device box under **independent-coordinate** sampling, so it contains
  corner combinations that never co-occur -- which is why 65 % of its
  rejections are `current_unreachable`. The cost metrics ("simulations per
  valid design") price that correctly because they charge only for simulations
  actually spent, but the *distributions over the feasible region* are not
  identical between arms and no claim depends on their being so. Also: the
  device arm gets **no free filter**, where a fair comparison would put
  `experiments/prescreen.py` in front of it. That experiment is not done.
- **(nebula) The peak-distortion compression bound is a WORST-CASE pattern.**
  Real PCIe traffic is 8b/10b-coded and run-length-limited, so the true peak
  excursion is smaller. Convention C is the right bound; the gap to typical
  traffic is unmeasured.
- JTOL amplitude grid is coarse (0.05/0.1/0.2/0.4/0.7/1.0 UI).
- Power numbers are PLACEHOLDERS (literature-based), never simulated.
- rtl/, verification/, veriloga_models/, matlab_models/, optical_dsp.py,
  ml_equalizer.py, visualization.py, Makefile: NOT AUDITED/RUN — treat as
  untrusted until proven (the Phase-0 experience says assume bugs).

## 8. Next steps (prioritized backlog with context)

**-1. NEBULA competition track (ACTIVE, started 2026-08-03).** Separate
   project, own contract (`CLAUDEwa.md`), hard deadline 15 Sept 2026.
   DONE: layer interfaces + mocks + 251 tests; **G0 PASSED**
   (`nebula/G0_RESULTS.md`); NRZ retarget audit written
   (`nebula/NRZ_RETARGET_AUDIT.md`); bounds re-derived; robust geometry
   confirmed; corner-yield swept (13.49% -> 8.10%). Blocking next actions,
   in priority order:
   - **>>> G2 IS PASSED. THE NEXT GATE IS G4, AND ONE DESIGN QUESTION NOW
     OUTRANKS IT. <<<** (Session 21, `nebula/G2_RESULTS.md`.) The loop closes
     and all of S3-S8 are met at TT on a design the search found. Next, in
     order:
     1. **COMPRESSION IS THE TOP OPEN DESIGN QUESTION AND IT IS A HUMAN'S
        CALL.** 61 % of the approved box cannot be evaluated at the PCIe input
        level -- the small-signal model that produced every pole stops
        applying, and the median design overshoots its measured linear limit by
        1.29x. Three routes, all already on record: reach below S3's 3 dB
        floor; declare the low-loss end of the channel family out of scope; or
        accept that the CTLE must ATTENUATE and re-derive the box's `rl` range
        downward. `CHANNEL_MODEL.md` §6 and this file both already point here.
     2. **The NRZ retarget of the BER path**, to replace the worst-case bound
        with a real bathtub. SCOPED: ~6 items, all inside
        `statistical_eye.py` (A1, B1-B5, E6), each with a hand-computable NRZ
        value, and the fence exists so it is done group by group. Groups C and
        D are the time-domain CDR/FFE chain and S2 does not use them.
     3. **G4, the corner axis.** Nothing structural is missing -- the bridge
        takes a `DeviceResult` per corner already. At 0.279 s full fidelity,
        3 corners x 2 loads is 1.7 s per design.
   - **>>> A DECISION IS WAITING, AND IT HAS A DEADLINE THAT IS NOT ITS OWN.
     <<<** (Session 20, `nebula/GMID_MAP.md`.) A gm/I_D table and a
     design-space inverse map are **built, tested and measured**, and
     **nothing is wired in** -- `params.py`, `contract.py` and `env.py` are
     untouched (rules 5, 6). The measurement: the idea's stated mechanism is
     **false** (G44 among simulated designs is 38.07 % in device coordinates
     against 37.74 % in design coordinates, unchanged), its actual benefit is
     **1.16x** on simulations per valid design, and its pre-simulation G44
     filter scored **TN = 0** (G82). §8 of that file recommends **not adopting
     before G2**. **The deadline is the sweep, not the gate:** adopting would
     invalidate the 8.73 % baseline, the +8.950669 ceiling and every benchmark
     arm, so the only moment this is free is BEFORE
     `baselines --sweep` runs. Decide before that, either way, and record it.
     **What to keep regardless of the decision:** the table is the natural
     input to the pre-screen re-fit below -- `solve_bias` already takes
     `mirror_efficiency` for exactly the 4-8 % mechanism that item names.
   - **>>> RE-FIT THE PRE-SCREEN AT BENCHMARK CONDITIONS. FIRST. <<<**
     (Session 18, `nebula/BASELINES.md` §11 and §12 item 1.) The analytic
     pre-screen is calibrated on `robust_geometry_data.csv` -- `cl` = 150 fF,
     `nf_in` varying, IDEAL R/C, IDEAL tail. Moved to the benchmark's own
     conditions (`cl_mid`, `nf_in` = 4, drawn passives, real mirror) its
     population rates transfer but **its accuracy does not**: `f_peak` MdAPE
     **4.93 % -> 15.85 %**, peaking bias **-0.009 -> +0.361 dB**, and the
     false-rejection rate **0.39 % -> 3.88 %**, ten times the 1 % budget the
     operating point was chosen against. **Widening does not fix a bias** --
     measured, at 2.5x the widening it is still 2.33 % while the free-rejection
     rate falls from 64 % to 40 %. The first thing to try is the mechanism the
     numbers point at: the gm/I_D model assumes `I_D = i_bias/2`, which is true
     of an ideal tail and **4-8 % optimistic against the real mirror**
     (session 13). The data to re-fit on already exists -- 457 valid rows in
     `baselines_pilot.jsonl` -- and `prescreen.accuracy_from_log()` is the
     measurement to beat. **Until this lands, every screened arm in the
     benchmark carries a known 3.9 % false-rejection rate and must be read with
     it.**
   - **>>> RUN THE BASELINE SWEEP. <<<** `python -m
     nebula.experiments.baselines --sweep`. **25 500 simulations, ~12.0 h at
     the measured 1.698 s/sim at 8 workers**, machine otherwise idle. It
     streams `baselines_run.jsonl`, so an interrupted run is recovered with
     `--analyse FILE.jsonl` rather than lost -- which is not hypothetical, the
     pilot was killed one job from the end. Afterwards, fill in
     `PREDICTIONS.md` entry 6's outcome **from the sweep, not from the pilot**.
     Note the ordering question this raises and does not answer: re-fitting the
     screen first changes what the screened arms measure, so either re-fit
     first and run once, or run now and treat the screened arms as a
     measurement of THIS screen. **That is a human's call.**
   - **>>> THE TAIL TRANSISTOR IS DONE (session 13). <<<** Kept here in full
     because the ARGUMENT it was promoted on turned out to be wrong, and that
     is worth more than the closure. **Measured cost of the ideal-tail
     assumption: 8.8% of the corner-robust-at-some-load population and ZERO of
     the headline yield** (1/1890 before and after, and the SAME design).
     `tail_saturation` IS a genuine coupled inequality — the only row in the
     spec table tying five box coordinates together — but it binds on
     2.6-13.3% of the box depending on corner. **The claim below that this was
     "the one experiment that could still turn corner robustness into a real
     constraint rather than a tax" is RETIRED **GIVEN THE CURRENT SCREEN**.
     **The 8.8% is CONDITIONAL** on a population the load screen had already
     reduced by 99.4%, so the tail is **masked, not unimportant**; what is
     unconditional is that it binds on 2.6-13.3% of the box and is the only
     constraint coupling five box coordinates. **RE-CHECK IT off the VIOLATION
     table whenever the load screen narrows to a tolerance band** — which is
     exactly what the tunable experiment does. Full write-up `nebula/TAIL_DEVICE.md`; S9 re-run
     `nebula/S9_YIELD.md` §9; prediction vs outcome `nebula/PREDICTIONS.md`
     entry 2. **The remaining ideal element is `I_ref`**, declared in
     `TAIL_DEVICE.md` §0.
     ORIGINAL ITEM, for the record:
     (Promoted 2026-08-05.) Every simulation this project has ever run uses
     **two ideal current sinks** for the tail. An ideal sink delivers exactly
     I_tail at every corner: it does not lose current at SS/125C, does not
     gain it at FF/0 C, and does not fall out of saturation when the rail
     drops 5%. That single assumption is what makes the whole S9 result an
     **optimistic bound** (G47), and it also blocks three of the nine box
     dimensions (`w_tail`, `l_tail`, `nf_tail` have no provenance). Everything
     needed to re-measure is already instrumented: add the device, then re-run
     `python -m nebula.experiments.s9_yield --n 2000` unchanged and diff
     against `nebula/S9_YIELD.md`. **This is the one experiment that could
     still turn corner robustness into a real constraint rather than a tax.**
     Session 11 adds a second reason to do it now: `ROBUST_GEOMETRY.md`
     measures how much S3 margin a design needs to survive the corners
     (0.133 octaves of f_peak margin plus 1.0 dB of peaking margin buys
     92.1% robustness against a 60.8% base rate), and **every one of those
     margins is a LOWER BOUND while the tail is ideal.** Re-running
     `robust_geometry.py --collect` afterwards is the cheapest way to see how
     far the requirement moves — 23 min, no new code.
   - **>>> THE REWARD SHAPE IS DECIDED, AND IT IS NOT WORST-NORMALISED-MARGIN.
     <<<** (Human decision, 2026-08-06, after session 13.) The earlier
     recommendation — a pure `min` over specs and corners — is **withdrawn by
     the person who proposed it**, on the evidence of session 13's violation
     table. **`min` has the same pathology as the first-failure table, one
     layer down:** it reports `S3_f_peak` for as long as that misses by
     17 GHz, so the agent gets **no gradient on `tail_saturation`** — a
     constraint binding on 13.3% of the box at slow-hot — until S3 is nearly
     solved. Session 13 measured that ranked-worst and ever-violated disagree
     by an order of magnitude; a `min` reward can only ever see the first.

     **The shape to build instead:**

         while ANY constraint is violated:   r = sum of clipped shortfalls
         once ALL are satisfied:             r = max over policy of (min margin)

     Every violated constraint contributes gradient; margin-seeking starts only
     when the design is feasible. **And normalisation matters more than the
     earlier note said:** express each margin in units where **1.0 means
     "meaningfully off"** — `f_peak` in **octaves**, peaking in **dB**,
     `tail_saturation` in **(vds - vdsat)/100 mV**. Raw magnitudes are
     incomparable, which is precisely what the 17 GHz vs 40 mV comparison
     demonstrates. Keep the `f_peak` term in LOG frequency
     (`-|log2(f_peak/f_target)|`), per the original note.
     This supersedes the worst-normalised-margin sketch for task 6.
   - **Session 11's two proposals, for a human** (`ROBUST_GEOMETRY.md` §7).
     Neither touches `params.py`; both are about the SEARCH, not the box.
     (a) **warm-start** the policy and the baselines from designs with
     f_peak margin >= 0.133 oct and peaking margin >= 1.0 dB — free, since
     both come out of an AC run the evaluator already does; (b) **shape the S3
     reward on the two FOLDED margins** rather than on peaking and f_peak
     directly, since §3 of that file shows the raw coordinates carry no
     information about corner robustness and the folded ones carry essentially
     all of it. Caveat the human must weigh: a 1.0 dB peaking margin bans the
     3 dB and 12 dB endpoints of S3's own tunable range, so the rule belongs
     on the search and not on the deliverable. Whether those endpoints are
     corner-robust AT ALL in this topology is unmeasured and worth asking.
   - **>>> THE LOOP RUNS, AND THE 4d REGRESSION MOVED A PUBLISHED VERDICT.
     <<<** (Session 17, task 6, `nebula/RL_SMOKE.md`.) 500 PPO steps at TT with
     REAL drawn passives, 26.5 min, 793 SPICE calls. **No conclusion about
     learning is drawn and none is offered.** What it established, in priority
     order for whoever picks this up:
     1. **RE-RUN THE LOAD AND CORNER SCREENS WITH DRAWN PASSIVES.** The 4d
        regression `PASSIVES.md` §6 listed first had never been run. It now
        has: drawn passives move `f_peak` by **0.1329 octaves** against the
        **0.12 octaves of centring slack** that made design 432 the sole
        load-robust survivor (G66). The mechanism is the predicted `res_po`
        bottom plate — **+1.4 to +24.3 fF on a 32.6 fF `cl`, up to +75 %** —
        and every shift is in the same direction. **Until this re-run happens,
        "one design in 1890 is corner-and-load-robust" is an ideal-passive
        statement.**
     2. **`PASSIVES.md` §6 item 6 is the highest-value throughput item**, and
        now there is a number behind it: **99.7 % of a training run is the
        simulator** (environment 1585.8 s, PPO update 3.5 s, logging 0.9 s),
        and the extended trim costs **2.07 s/evaluation against ~0.33 s** on
        the nfet-only one for the same netlist. Trimming
        `parameters/typical.spice` and `invariant.spice` is worth roughly 6x on
        the inner loop; optimising the RL side is worth nothing.
     3. **The G44 guard is load-bearing, not defensive.** 78 % of everything
        the policy found — 159 of 203 invalid evaluations — was a fictitious
        peak at the sweep edge (G65), each of which would have scored HIGH
        under a reward that reads S3 peaking.
     4. **`to_geometry` is geometrically chaotic** (G67): a 0.016 % change in
        `rs` flips the device, giving a **15x area spread across a 0.16 %
        resistance spread**. `PASSIVES.md` §4.5's 1506 um^2 is a property of
        the quantiser as much as of design 432, and task 8's `design_id`
        grouping will be fine-grained rather than coarse.
     5. **The tail may not be worth searching after all, with a number.**
        `vcm_in` is a **6x stronger lever on the tail margin** than `tail_j`
        is, on the quantity the tail geometry exists to control — which is
        evidence FOR `TAIL_DEVICE.md` §6's recommendation, and it is a human's
        call.
     Open from this task: a second seed; and the obvious next experiment,
     which is **not** more PPO steps but the corner axis, since every number
     above is TT-only.
   - **>>> THE RE-RUN ORDER, DECIDED. DO NOT RE-RUN THE SCREENS FIRST. <<<**
     (Human decision, 2026-08-07, session 17 review.) G66 says the load and
     corner screens need re-running with drawn passives. They do — but
     **re-running before the `cl` range is corrected means re-running with the
     WRONG range**, and each screen is tens of minutes of ngspice. The order:

     1. **Trim `parameters/typical.spice` and `invariant.spice` out of the
        extended library** (`PASSIVES.md` §6 item 6) and re-verify bit-identity.
        This is first because it is now measured, not guessed: **99.7 % of a
        training run is the simulator**, and the extended trim costs 2.07 s per
        evaluation against ~0.33 s on the nfet-only one. Everything downstream
        is bought at that rate.
     2. **Update the `cl` budget with the `RL` bottom-plate parasitic**
        (`PASSIVES.md` §6 item 4). Session 17 measured it at **+1.4 to
        +24.3 fF on a 32.6 fF `cl`**, so `CL_RANGE.md`'s 13.64-78.04 fF is
        stale by up to +75 % at the bottom end. **A prediction is registered
        before this runs** — `PREDICTIONS.md` entry 5: the parasitic adds a
        floor to BOTH ends, and since the load's damage comes from its RATIO
        (5.72x) rather than its width, the direction is COMPRESSION, nominally
        to ~3.7x. Compression is what design 432 needed, so this may HELP.
     3. **Collapse the passive corner axis** (`PASSIVES.md` §6 item 3, G58's
        5 x 5 = 225 corners) to a screen set, the way G47 did for the MOS axis.
     4. **Then re-run the load and corner screens** and diff against
        `S9_YIELD.md`.

     Doing 4 before 2 would produce a number that has to be thrown away, and
     G49 is the standing reminder of what that costs.
   - **Approve or amend the proposed box**, then copy it into
     `common/params.py::BOUNDS`. The `cl` dimension is recommended to be
     **removed from the SEARCH and replaced by a screened CONTEXT RANGE**,
     `cl = 13.6-78.0 fF` (`nebula/CL_RANGE.md` §8, session 12a). This
     supersedes `CL_SENSITIVITY.md`'s "pin at 150-250 fF": that value was the
     S3-yield maximum of five tested, and the derived range's TOP is 1.92x
     below it. **One topology question rides on this and is a human's**: if
     the receiver is half-rate (two data + two edge slicers on the node), the
     range becomes 13.6-141.8 fF and the ratio 10.4x instead of 5.7x. S2 names
     no CDR, so the bound above assumes full rate.
   - **>>> THE LOAD IS NOW THE BINDING CONSTRAINT, AHEAD OF THE CORNERS. <<<**
     (Session 12b.) 0.05% corner-and-load-robust yield, against 8.20% at the
     old pin. The actionable output is NOT that number, it is the tolerance:
     this topology absorbs a 5.72-7.76x load spread for **one design in 1890**,
     so either the following stage's input capacitance gets specified far more
     tightly than 5.72x, or the CTLE needs a knob (`CL_RANGE.md` §7b —
     capacitance can always be ADDED to the output node, never removed).
     **The cheapest thing that could change this verdict is scoring a TUNABLE
     design**: S3 says the peaking is tunable via R_s/C_s, and `s9_yield.py`
     scores fixed sizing points, so 0.05% is a lower bound on what a real
     tunable part achieves. That experiment is not written.
   - **The CTLE output common mode may not be able to bias the stage it
     drives** (`CL_RANGE.md` §7a). `headroom_ok_1v8()` lets v_out fall to
     0.5 V; the loading pair needs roughly 1.15 V or its source node goes
     negative — session 9c's unbuildable-tail failure, one stage downstream.
     Either the box needs a tighter v_out floor or the RX needs AC coupling /
     a level shift. Nothing in the project currently notices this.
   - **G1 — was "hand-size a reference CTLE at TT".** Port to 1.8 V (the bounds
     are 1.2 V numbers and do NOT transfer — see the provenance audit), add
     a real tail transistor (above), and pull the **MIM cap and poly resistor**
     models the S7 area estimate needs.
   - **>>> COMPRESSION: RE-MEASURED, AND IT IS WORSE THAN THE LINE THIS
     REPLACES. <<<** (Session 16, `CHANNEL_MODEL.md` §6.) **The line that used
     to sit here — "real, but much smaller than 9c reported; localised at the
     two lowest-loss points, 1.22x and 1.04x" — is REPLACED, not amended.**
     Measured against the derived channel family and the mandated -3.5 dB TX
     de-emphasis, with the reproduction gate passing 5/5 on the published
     reference device: **compression binds at 5 of 7 loss points, and 3 dB is
     1.51x.** The old **1.22x survives VERBATIM** under its own convention
     (Nyquist content through Nyquist gain) — which the deleted DC-loss
     constant never touched, so `BOUNDS_REDERIVATION.md` §2's blockquote was
     right about the C3 table and wrong to imply the headline hung on it.
     **"Worst at LOW loss" survives and is now explained**: below 6.5 dB of
     channel loss the CTLE's burden is *below* S3's 3 dB floor, so a compliant
     CTLE adds boost the link does not need, on top of an input the channel has
     barely attenuated. **Still true, unchanged:** the limit is **current
     steering, not headroom** — which is also why a 3.3 V device buys only +12%
     swing (G39). **The actionable item is now S3's floor**, not the device:
     either the tunable range needs to reach below 3 dB, or the low-loss end of
     the channel family has to be declared out of scope, and that is a human's
     call. Read G61 before quoting any compression ratio — the word has three
     definitions in this repo and they disagree by 1.8x.
   - **Abstract due Aug 6.** Write it around what G1 shows is achievable.
     **The "coupled constraint" argument is RETRACTED (G40).** State the
     ideal-tail assumption plainly; it is the live one.
   - **The NRZ retarget.** 21 of the 24 audit items remain; order of work at
     bottom of `nebula/NRZ_RETARGET_AUDIT.md`.

**0. UCIe group project — owner's FFE block (ACTIVE, started 2026-07-23).**
   STATUS: starting Part A step 2 (zero-forcing math).

**1-9.** (See existing backlog: .s4p, clipping disto, joint adaptation, etc.)

## 9. Gotchas & footguns (each one cost real debugging time)

- **G1 — Repo must stay PRIVATE.** The PDFs are copyrighted (IEEE, theses,
  Intel/Xilinx). A public/portfolio version must strip them from HISTORY
  (they're in the baseline commit), not just delete the files.
  **AMENDED 2026-08-04 (session 10a) — true of the GitHub repo, NOT of this
  checkout.** `github.com/jaikaushik-prog/serdes-dsp-framework` still carries
  them in its baseline commit and still needs a history rewrite before it could
  ever go public. This working tree was `git init`-ed fresh with the PDFs
  already in `.gitignore`, and the index was checked empty of them before the
  initial commit, so **its** history has never contained them. The two are now
  unrelated histories. Do not `git remote add origin` that URL and push — it
  would either be rejected as unrelated or, if forced, replace a repo whose
  history you have not audited. Decide deliberately (new remote vs. rewrite of
  the old one); see G41.
- **G41 — (repo) `git init` was run on 2026-08-04 and the history starts
  clean.** One initial commit on `main`, 102 files.
  **AMENDED 2026-08-07: there IS a remote now** —
  `origin = https://github.com/jaikaushik-prog/nebula-ctle-rl.git`, a **NEW,
  PRIVATE** repo built from this clean history, not the old
  `serdes-dsp-framework` one (which is an unrelated history and still carries
  the PDFs in its baseline commit — see G1 as amended). Credentials are cached
  in Windows Credential Manager, so `git push` works; `gh` is installed but
  **not authenticated**, and authenticating it is interactive and the owner's.
  **Before any push, re-run the two checks below**, plus
  `curl -s -o /dev/null -w "%{http_code}" https://api.github.com/repos/jaikaushik-prog/nebula-ctle-rl`
  — **404 means still private, 200 means it went public and G1 is violated.**
  The checks that make the clean-history claim real are two commands, and they
  are the ones to re-run before any future `git add -A`:

        git diff --cached --name-only | grep -iE '\.(pdf|docx)$'   # must be empty
        git status --ignored --porcelain | grep '^!!'              # what was skipped

  `.gitignore` is now sectioned and commented by *reason* rather than by file
  type, because the reasons differ in kind: copyright (PDFs — never commit),
  redistribution (the PDK tree at `C:\Users\DELL\sky130A`, out of tree today
  but the patterns exist so an in-tree copy cannot slip in), and mere
  regenerability (results, `__pycache__`, ngspice scratch, the `ams_rl_ppo`
  checkpoints). **One deliberate non-ignore:**
  `nebula/device/spice/sky130_nfet_only.lib.spice` is OURS (G36) — 69 lines of
  `.include` pointers plus `.option scale=1.0u`, redistributing no model cards
  — and is excluded from the `sky130*` pattern by an explicit `!` rule. Losing
  it would cost the 40-80x inner-loop speedup.
- **G2 — Scrambler coherence:** always compare RX bits against LINE bits
  (post-scrambler) or descramble first. `generate()` returns line bits.
- **G3 — Never `np.random.seed()`.** Thread `LinkConfig.seed` →
  `np.random.default_rng`. The TIADC class in adc_model.py still has an
  internal seed=42 (standalone use only; the link path doesn't use it).
- **G4 — FFE cursor convention:** warm starts must place the cursor at
  `n_pre`, not the filter centre. `mmse_init_ffe(..., n_pre=)`.
- **G5 — Don't RMS-AGC a peaked waveform;** use pulse-cursor gain calibration.
- **G6 — BB-loop stability:** pattern-gated updates ⇒ effective ki multiplied
  by mean update gap (~4). Keep 4·ki/kp ≲ 2 %. Gear-shift + integrator clamp
  are load-bearing, not decoration.
- **G7 — MM PD sign:** raw MM product is positive-when-early; this loop needs
  positive-when-late (phase↑ = earlier). See rx_frontend comment.
- **G8 — Alexander PD needs a partially-open RAW eye** (crossing jitter
  <~0.6 UI); MM-postffe needs an FFE-openable eye. Neither is universal.
- **G9 — adapt_start:** never let sign-sign LMS adapt during CDR acquisition
  (|Δtap|=µ regardless of error size — it walks off the warm start).
- **G10 — Windows console is cp1252:** no →, ≤, µ, ≈, em-dash in print()
  strings (crashes under redirection). Files themselves are UTF-8, fine.
- **G11 — Working directory:** run pytest from repo ROOT; run link_sim from
  python_models/. PowerShell sessions persist cwd between tool calls.
- **G12 — Git identity:** commit as `Jai Kaushik
  <jaikaushik-prog@users.noreply.github.com>` (global config is set). Do NOT
  use the BITS email — it attributes commits to a wrong GitHub account
  (history was already rewritten once to fix this; hashes changed).
- **G13 — Figure caching:** make_report_figures reads cached CSVs
  (arch_compare_pk.csv etc.); delete the CSV to force recomputation.
- **G14 — `Channel.pulse_response` uses argmax cursor + trimming; the
  waveform path avoids `np.convolve(mode='same')` deliberately.** Keep
  explicit alignment; never reintroduce 'same'-mode shortcuts.
- **G15 — scikit-rf not installed** (S-param import raises); matplotlib may
  need `MPLBACKEND=Agg` for headless runs.
- **G16 — (nebula) `nebula/device/mock.py` and `nebula/link/mock.py` produce
  FAKE numbers.** They exist so three people can build three layers in
  parallel before ngspice exists. No value from either may reach the abstract,
  report, slides or results table (CLAUDEwa.md §8 rule 1). Their *trends* are
  physically coherent; their *magnitudes* are invented. The mock's noise floor
  in particular is optimistic — do not read S5 headroom off it.
- **G20 — (nebula) ngspice: use `ngspice_con.exe`, NOT `ngspice.exe`.** The
  latter is the GUI build and prints nothing under `-b`, which looks exactly
  like a broken install. Binary lives in
  `C:\Users\DELL\miniforge3\envs\nebula\Library\bin\`. Activate with
  `conda activate nebula`.
- **G21 — (nebula) `.disto` returns exactly 0.0 for BSIM4.** Not a linear
  circuit — BSIM4 does not implement the higher-order derivatives the analysis
  needs, so it silently contributes no distortion at all. Proven with an A/B
  against a `level=1` model in one netlist (see `nebula/G0_RESULTS.md`). Every
  open PDK is BSIM4-based, so no PDK fixes this. **HD3 (S4) must come from
  transient + FFT**, ~0.26 s/corner vs 0.066 s for AC+noise.
- **G22 — (nebula) `.disto` with a trailing `f2overf1` argument** switches to
  two-tone intermodulation mode and aborts with "No source with f2 distortion
  input". Single-tone harmonic mode is the form WITHOUT that argument. Also:
  `meas` does not accept the two-argument `vdb(a,b)`; `maxat` is not a `meas`
  function; `linearize` takes vector names, not a timestep; ngspice's own
  `fft` zero-pads to a power of two so bin indices are not `f/binwidth` —
  dump with `wrdata` and FFT in numpy.
- **G23 — (nebula) PySpice is installed but does not work** (bundled ngspice
  DLL fails to load, 0x7e; post-install downloader dead). Do not spend time on
  it: batch `ngspice_con -b` via `subprocess` is the better fit for the RL loop
  anyway — no FFI state, trivially parallel per corner, crashes are exit codes.
- **G24 — (nebula) compression is a validity condition, not a clamp.** The
  link layer used to compute `min(g_dc * v_in_pp, vout_swing_v)`. Both halves
  were wrong: (a) `g_dc` is the DC gain, but the eye is set by `|H(f_nyquist)|`
  which is 3-12 dB higher by construction (S3); (b) `min()` silently converted
  an invalid operating point into a plausible number, and an RL policy hunting
  eye height would have found that region and lived in it. Now:
  `output_swing_pp_v()` returns the unclamped linear prediction from the
  PEAKED gain, and `check_compression()` returns a reason string that the link
  layer turns into `ok=False`. See `nebula/link/calibration.py` conventions
  C3/C4.
- **G26 — (nebula) ngspice `let` failures are WARNINGS, and the run exits 0.**
  `@m1[gm]` and friends live in the `op1` plot; after an `.ac` the current
  plot is `ac1` and every `let` referencing them fails with
  "vector ... is not available or has zero length" while the script carries on
  and returns success. The G1 netlist's entire §6 cross-check block failed
  this way and was reported as passing. **Grep ngspice output for
  `not available|Error:` before believing any derived number**, or compute
  derived quantities in Python from parsed primitives (which is what
  `nebula/device/ngspice_runner.py` does).
- **G27 — (nebula) §6's gain equation is missing the body effect and fails
  its own 1 dB gate.** In a bulk process the bulk is grounded, the source
  moves, so `k = 1 + (gm + gmbs)*Rs/2`. Measured at the G1 point gmbs/gm was
  0.33 and §6-as-written was **2.33 dB** optimistic. `predict()` and
  `cross_check_extraction()` take `gmbs` (default 0.0 = §6 verbatim). Always
  pass the simulated gmbs when comparing to SPICE.
- **G28 — (nebula) `rl`'s ceiling is JOINT with `i_bias`, not independent.**
  Load drop is `0.5*i_bias*rl` and must fit under VDD=1.2 V. 12 mA x 500 ohm
  drops 3.0 V. Both values are individually inside their bounds. Use
  `params.headroom_ok()` to reject the pair before spending a SPICE call
  (measured: 9.5% of samples, and it cuts triode failures 9.3% -> 2.5%).
- **G30 — (nebula) `.param` names are NOT visible as `.control` vectors.**
  The second, independent reason the §6 cross-check block never ran (the first
  is G26's plot-context trap). `let k = 1 + gm * {RS_OHM} / 2` does not
  substitute — ngspice reports `vector rs_ohm is not available`, then
  `Error: RHS "1 + gm * rs_ohm / 2" invalid`, and **exits 0**. Same for
  `let power_mw = v(vdd) * {ITAIL} * 1000`. **Put no derived arithmetic in
  `.control` at all.** Print primitives; compute in Python
  (`nebula/device/crosscheck.py`). CLAUDEwa.md §8 rule 9.
- **G31 — (nebula) SKY130 instance W and L are PLAIN NUMBERS IN MICRONS.**
  `libs.tech/ngspice/sky130.lib.spice` sets `option scale=1e-6` and the
  `sky130_fd_pr` subckts default to `l=1 w=1` meaning one micron. So write
  `W=5 L=0.15`, not `W=5u L=0.15u` — the latter gives 5 pm, falls outside all
  180 model bins, and aborts with the *misleading* **"could not find a valid
  modelname"** (which reads like a missing library, not a units error). The
  generic-BSIM4 netlists in the same directory use SI metres. Never copy W/L
  between the two families without converting.
- **G32 — (nebula) two netlists described "the same" reference point with
  different model cards.** `g1_handdesign.cir` was missing `k2=0.05`, which
  `ngspice_runner.py::_NETLIST` had — and `k2` is BSIM4's body-effect
  coefficient, i.e. exactly the term G27 is about. Effect: gmbs/gm 0.250 vs
  0.327, A_dc −14.123 vs −14.569 dB, peaking 8.19 vs 8.29 dB. All published
  numbers came from the runner. Fixed by matching the cards. **If you clone a
  netlist, diff the `.model` line**; a one-parameter drift is invisible and
  moves the body-effect term by 30%.
- **G29 — (nebula) the raw `sky130_fd_pr` clone is NOT ngspice-ready.**
  **RESOLVED 2026-08-04 — see G33.** Kept for the diagnosis.
  `ngbehavior=hsa` must go in a **`.spiceinit`**, not `.control` (too late —
  `.include` runs at parse time); that clears the `sqrt()` problem. What it
  does not clear: the `.pm3.spice` `.subckt` declares its parameters via a
  `.param` line inside the body ("13 formal but 0 actual params"), and the
  `.corner.spice` files contain zero `.model` cards. **Install `open_pdks` or
  use `volare`** for the generated `libs.tech/ngspice/sky130.lib.spice`. Do
  not patch the raw repo.
- **G33 — (nebula) the WORKING SKY130 install.** `C:\Users\DELL\sky130A`
  (`libs.tech/ngspice` + `libs.ref/sky130_fd_pr/spice`, ~52 MB, 856 files),
  copied out of a `volare` install in WSL2 Ubuntu. Use
  `.lib "C:/Users/DELL/sky130A/libs.tech/ngspice/sky130.lib.spice" tt` — and
  `ss`/`ff`/`sf`/`fs` for the other four S9 process corners. Reference
  netlist: `nebula/device/spice/g1_sky130_volare.cir`; run it from
  `nebula/device/spice/` so the local `.spiceinit` (`ngbehavior=hsa`) is read
  at parse time. Reinstall recipe if the tree is lost:
  `pip3 install --user --break-system-packages volare` inside WSL
  (**not** a venv — `python3-venv` is absent and installing it needs sudo),
  then `~/.local/bin/volare enable --pdk sky130 c6d73a35f524070e85faff4a6a9eef49553ebc2b`.
  Superseded: `g1_sky130.cir` (raw-repo version). **See G34 for the cost.**
- **G34 — (nebula) the SKY130 library costs 16.5 s to PARSE, per ngspice
  process.** Measured: the same netlist takes **0.02 s** on generic BSIM4
  cards and **16.5 s** on the SKY130 lib — a ~700× penalty that is almost
  entirely parsing, not analysis. It amortises completely if the process is
  reused: 20 points in one process took 16.57 s, **200 points took 16.89 s**
  (~0.002 s marginal per point). Therefore **the device layer must hold
  ngspice processes open and `alter` between sizing points; one `subprocess`
  call per evaluation is not viable against a PDK** — at 1e5 PPO steps that is
  19 days for TT alone versus the 1.8 hours the generic-BSIM4 cost table
  records. This revises G23: batch mode is still right, but processes must be
  REUSED, not respawned. **SUPERSEDED 2026-08-04 by G35 and G36:** `alter`
  turned out to be unsafe for W/L, so process reuse is NOT the answer — the
  trimmed library is, and it makes the question moot.
- **G35 — (nebula) `alter` CANNOT move W/L of a subckt-wrapped PDK device.
  It fails SILENTLY, returning plausible wrong numbers.** Measured against
  fresh-parse ground truth:

        W (um)   bin vs baseline     gm fresh    gm altered   error
        4.5      SAME bin [3,5]      2.358e-3    2.272e-3     -3.6%
        6.0      crosses to [5,7]    3.175e-3    2.407e-3     -24.2%
        9.0      crosses to [7,100]  3.6e-3      NaN          broken

  **Even within one bin it is wrong**, which rules out "only alter inside a
  bin" as a workaround. Cause: the `sky130_fd_pr` subckt derives
  `ad/as/pd/ps/nrd/nrs` from W by `.param` expression at PARSE time. `alter`
  writes the `w` instance parameter and leaves every geometry-derived
  parasitic at its old value, so the device becomes internally inconsistent.
  Two further traps found on the way: `alter @m...[w] = 3.2u` applies
  `scale=1e-6` a SECOND time (giving 3.2e-12 m), so alter takes PLAIN numbers
  exactly as the netlist does; and `alter xm1 w=...` (the X-instance form)
  does not work at all — only the hierarchical
  `@m.xm1.msky130_fd_pr__nfet_01v8[w]` form reaches the device. In the failing
  cases ngspice printed `Error: no model available for w=...` and then
  **`print @m1[gm]` still returned the stale value** — exactly the §8 rule 10
  failure mode. **Do not use `alter` for device geometry.** It is fine for the
  ideal R/C/I elements (rs, cs, rl1/rl2, cl1/cl2, it1/it2), which are not
  subckts.
- **G36 — (nebula) TRIM THE PDK LIBRARY: 16-35 s -> 0.42 s, bit-identical.**
  `nebula/device/spice/sky130_nfet_only.lib.spice` includes only the
  `nfet_01v8` model files instead of the 30 device families the full
  `sky130.lib.spice` loads per corner (20 V devices, BJTs, ESD, RF, the whole
  pfet set — none of which the S2 CTLE instantiates). All five process corners
  provided. Verified **exactly equal** (`rel=0, abs=0`) to the full library on
  gm, gmbs, vth, id, g_dc, g_pk and inoise_total across 5 corners x 4 (W,L)
  points chosen to straddle three W bins and two L bins —
  `nebula/tests/test_trimmed_lib.py`, 22 tests, 7 s. Goldens captured from the
  full library live in `tests/fixtures/sky130_full_lib_golden.json`; a
  `slow`-marked test re-derives them after a PDK update.
  **Gotcha within the gotcha:** a trimmed library MUST declare
  `.option scale=1.0u` itself. The full library sets it in
  `libs.tech/ngspice/all.spice`, which the trim does not include; omit it and
  W=5 means five METRES, producing G31's misleading "could not find a valid
  modelname" from the opposite cause.
- **G37 — (nebula) `2*I_tail*RL` is a PEAK, not a peak-to-peak, and it is a
  steering ceiling, not the linear swing.** Three separate traps in one
  formula, and session 9c hit all three. Full steering puts `2*I*RL` across
  the load in EACH polarity, so the differential output spans `+/- 2*I*RL` and
  the peak-to-peak figure is **`4*I*RL`** — 9c compared required swings against
  `2*I*RL` read as peak-to-peak and so ran 2x pessimistic. Then even `4*I*RL`
  is the hard ceiling with the device slammed into triode; the number a
  compression check needs is the **1 dB gain-compression** point, measured off
  a `.dc` differential transfer curve. At the corrected reference: 1427 mVpp
  linear, 2161 mVpp saturation-limited, 2281 mVpp steering, 2400 mVpp
  textbook. And third: at this operating point the pair is still saturated far
  past the 1 dB point (vds 1.29 V vs vdsat 0.079 V), so the limit is
  **steering, not headroom** — which is why raising the supply barely helps
  (G39). Use `sky130_runner.swing_limits()`; it returns `None` rather than
  falling back to a computed ceiling when the sweep never reached compression.
- **G38 — (nebula) on SKY130 `nf` does NOT multiply device width.** `W` is the
  TOTAL width and `nf` only splits it into fingers. Measured at W=40,
  1.5 mA/side: gm = 14.22, 13.68, 12.62, 13.12, 12.29, 11.79 mS for
  nf = 1, 2, 4, 8, 16, 32 — a **+/-10% NON-MONOTONIC** parasitic effect. The
  generic-BSIM4 netlists in the same directory write `m={NF}`, where nf really
  is a multiplier, which is where `BOUNDS["nf_in"]`'s "1-32 multiplies
  effective W" came from. Consequence for the action space: `nf_in`/`nf_tail`
  are near-dead dimensions AND non-monotonic, which is worse than dead for a
  policy gradient. Extra width must come from W (bin-capped at 100 um) or a
  device multiplier.
- **G39 — (nebula) the SKY130 3.3/5 V devices cannot do S3 at 2.5 GHz.**
  `nfet_g5v0d10v5`'s model bins give it a **minimum L of 1.0 um** against
  0.15 um for `nfet_01v8`, and f_T falls ~1/L^2. Measured at VDD=3.3 V over
  six sizings: best peaking **2.66 dB**, below S3's 3 dB floor, at
  1.32-1.38 GHz; pushing RL to 1200 ohm for gain moves the peak to 0.398 GHz
  and drives the Nyquist boost to **-5.14 dB** (worse than a wire where the
  data is — the CLAUDEwa §3 reading-(a)/(b) counterexample, on a second device
  family). Swing improves only +12%, because the limit is steering not
  headroom (G37), and power rises 5.4 -> 9.9 mW. **Rejected on f_T, not on
  headroom.** Do not re-propose "use a higher-voltage device" without reading
  this.
- **G40 — (nebula) a bare yield percentage is not evidence of coupling, and
  ours was not.** "5.3% of random samples meet S3, therefore S3 is a coupled
  constraint" does not follow: a hit rate depends entirely on how wide the box
  was drawn. The box-independent test is to decompose the conjunction and
  compare the joint against the product of its marginals. Done for S3 across
  three box widths: the raw yield swings **5.5x** (17.25% -> 8.73% -> 3.13%)
  while the coupling factor stays at **1.00-1.06x**. The conditions are
  independent; there is no coupling. One trap inside the trap: designs with no
  peak at all fail both conditions together and make them look positively
  associated, so the statistic must also be computed **conditional on a peak
  existing** (that is the 1.04x figure). Costs the same simulations as the
  bare percentage — three counters instead of one. Generalise the habit: any
  "X% therefore hard" claim in this project needs the marginals next to it.
- **G42 — (nebula) a search DIMENSION can be worth less than a constant, and
  `cl` is.** Pinning `cl` at 150 fF and holding every other bound raises the S3
  random-search yield from **8.73% [7.54, 10.09] to 13.54% [12.08, 15.16]** —
  disjoint intervals, 2000 paired samples. The whole 10-500 fF bound is worse
  than a single well-chosen value inside it, so the axis is not carrying
  information, it is spending samples. That is now **two** of nine sampled
  parameters that measurement says should not be in the action space
  (`nf_in` is the other, G38). **The trap this sets: improving the box
  improves the RANDOM-SEARCH BASELINE, which is what CLAUDEwa §7 requires RL
  to beat at G3.** 8.73% -> 13.54% moves the bar from ~11 samples per hit to
  ~7. Take the better box anyway — a baseline that was weak only because of a
  badly chosen dimension is not one worth beating, and a judge will ask why
  `cl` was searched at all — but record it as a deliberate decision, not as a
  silent improvement that raises the bar three weeks before the gate. Full
  data: `nebula/CL_SENSITIVITY.md`.
- **G43 — (nebula) a RAW coupling factor tracks the no-peak fraction, not the
  coupling.** G40 already said the statistic must also be computed conditional
  on a peak existing. Session 10b shows *how badly* it matters, as a trend
  rather than a footnote. Sweeping `cl` over 50/100/150/250/400 fF:

        raw coupling          1.00  0.94  0.82  0.74  0.68   monotone
        conditional coupling  1.08  1.10  1.01  1.02  1.05   flat
        designs with a peak   1673  1559  1469  1313  1168   monotone

  The raw factor moves by 32% while the real one does not move at all, and it
  moves in lockstep with the number of designs that have no interior maximum.
  Those fail A and B together and make the two look positively associated for
  a reason that has nothing to do with S3. **Never quote a raw coupling factor
  without the conditional one beside it** — it is the no-peak fraction in
  disguise. (One honest wrinkle: at `cl` = 100 fF the conditional interval
  [1.02, 1.20] does exclude 1.0, so there is a real ~10% adverse effect there.
  Ten percent cannot explain a 8.73% yield; G40 stands.)
- **G44 — (nebula) `meas ac MAX ... TO=50g` reports the SWEEP EDGE as a peak.**
  The `has_peak` filter in `s3_yield.py` is
  `peaking_db > 0.25 and f_pk_hz > 50e6`, which catches a monotonically
  FALLING response (it reports `f_pk` at the 10 MHz start) but **not** a
  response still rising at the top of the sweep, which reports `f_pk` at
  ~47.9 GHz and sails through both tests. Observed on a real sample:
  rl=111, cl=50f -> `f_pk = 47.863 GHz`, i.e. no interior maximum at all.
  Those designs are counted in `n_has_peak` and should not be. It does not
  affect S3 itself (47.9 GHz fails the 1.25-2.5 GHz window anyway) but it
  inflates the has-peak denominator and therefore slightly biases the
  conditional coupling factor. Fix is a symmetric upper guard
  (`f_pk_hz < 0.9 * f_sweep_max`); not applied yet because it changes a
  published statistic and needs the re-run to go with it.
- **G25 — (nebula) the channel needs TWO loss numbers, not one.** A CTLE's
  peaking is RELATIVE (|H(f_nyq)|/|H(0)|), so what it equalises is the
  channel's **tilt**, not its absolute loss. Comparing peaking against
  absolute loss silently assumes a channel that is lossless at DC — which no
  real channel is. `LinkConfig` now carries `channel_loss_db_at_nyquist`
  (swept) and `channel_loss_db_at_dc` (placeholder, 1.0 dB, no measured
  provenance), with `channel_tilt_db` derived. Two amplitudes follow:
  `v_in_diff_pp_v` (long-run level, set by DC loss — this is what the
  compression check has to survive) and `v_in_nyquist_pp_v` (the content the
  eye is built from). Do not collapse them back into one.
- **G17 — (nebula) `nebula/common/params.py::BOUNDS` is empty ON PURPOSE.**
  `param_space()` raises until a human fills it from the G1 hand-design.
  CLAUDEwa.md §8 rule 6 forbids an agent choosing parameter ranges: too wide
  and ngspice will not converge over most of the box, too narrow and the
  optimum is outside it — and neither failure announces itself, they both
  just look like "RL didn't work". Same rule covers the reward tolerances in
  `RewardConfig` and the two link numbers in `LinkConfig`; all four are
  required arguments with no defaults for exactly this reason.
- **G18 — (nebula) the millivolt calibration is one function.**
  `nebula/link/calibration.py`. NRZ symbols are +/-1, so a fully open eye is
  2.0 normalised units and maps to the FULL differential peak-to-peak swing;
  one normalised unit is HALF the swing. `DeviceResult.vout_swing_v` is the
  compression limit (a device property), not the actual swing — the actual
  swing is `min(g_dc * v_in_pp, vout_swing_v)`. Nothing else in the codebase
  may multiply a normalised amplitude by a voltage. A factor-of-two error here
  crashes nothing and silently moves the S8 spec line by 2x.
- **G19 — (nebula) run its tests separately or together, both work:**
  `python -m pytest nebula/tests -q` (228 tests, <1 s) or
  `python -m pytest tests nebula/tests -q` (293 total, ~50 s). The two
  conftest.py files put different things on `sys.path` and do not collide.
- **G45 — (nebula) ngspice failures under machine LOAD are transient and do
  not reproduce.** A 2000-point run at 11 workers, sharing the box with a
  second pool and a pytest run, reported **20 failures**; the identical
  configuration and seed on a quiet machine reported **0/1890**. Cause is
  process-launch or temp-directory contention on Windows, not any property of
  the design. Harmless in `s3_yield.py`, where a failed run drops out of the
  denominator. **NOT harmless in a corner experiment**, where scoring a
  transient failure as "this design fails at SS/125C" biases the corner yield
  downward and does it silently, because a failed corner and a failed spec
  look identical once counted. `s9_yield.py::evaluate_at_corner` therefore
  **retries once** and reports retries separately from hard failures — a
  genuine non-convergence fails twice and is real; a transient one succeeds on
  the retry and is reported as noise. Every stage prints a `health:` line
  (simulated / headroom-rejected / hard failures / retried) so the denominator
  is never implicit.
- **G46 — (nebula) "slow-hot is the worst corner" is FALSE for a two-sided
  spec, and S3 is two-sided.** The S9 screen was built on the standard
  intuition — ss/0.95V/125C, ff/1.05V/0C, ss/0.95V/0C. Promoting its survivors
  to all 45 corners shows every remaining failure lands at **125 C on ff, sf or
  tt**, and **none on ss at any rail**. Mechanism: a FASTER device has higher
  gm, which pushes the peak UP in frequency and out through S3's 2.5 GHz top
  edge. A one-sided spec (max power, max noise) has a worst corner; a spec with
  a window has a worst corner per EDGE, and the two are on opposite sides of
  the process axis. **Choose corners per spec edge, not per folklore** — and if
  a corner set was chosen by intuition, promote a sample and check, because the
  screen will look perfectly healthy either way.
  **REFINED 2026-08-05 (session 11, `ROBUST_GEOMETRY.md` §5).** The mechanism
  is real but NOT symmetric, and the asymmetry matters. Among the 100
  corner-fragile designs: those sitting BELOW the window centre die at SS 4.5x
  more often than at FF (45 vs 10), as predicted — but those ABOVE the centre
  die about EQUALLY at both (29 vs 27), which the clean two-mechanism story
  does not predict. Cause: **SS has two ways to kill a design and FF has one.**
  Lower gm drops f_peak (killing the low side) AND drops peaking toward the
  3 dB floor (killing anything with little peaking margin, at any frequency).
  SS's 69 failures split 40/26 across those two routes; FF's split 19/19. Do
  not write "designs above the centre are predominantly killed by FF" — 29 vs
  27 on 56 events is a coin flip. Note also that "which corner kills the most
  designs" (`ss/0.95/125`, at the screen stage) and "which corner does the
  screen MISS" (fast-hot, at the promotion stage) are different questions with
  different answers; G46 as originally written is about the second.
- **G47 — (nebula) a corner SCREEN can only be wrong in one direction, and
  three corners are worth 98.7% of forty-five.** The screen corners are a
  SUBSET of the 45, so any design the screen rejects the full sweep would also
  have rejected: **no false negatives, by construction**, and the 3-corner
  yield is a hard upper bound on the 45-corner one. The only possible error is
  a false positive. Measured: 155 designs passed 3 corners, **153 passed all
  45** — the full sweep consumed **64% of the wall clock to reject two
  designs**. Budget the RL reward at 3-5 corners and put the 45-corner sweep in
  a final verification tier; that is a ~15x throughput factor over a training
  run. **The caveat that limits this:** the tail is still two ideal current
  sinks, which do not lose current at SS/125C or drop out of saturation at
  0.95 VDD, so every corner spread measured so far is an UNDERSTATEMENT and
  8.10% is an OPTIMISTIC bound. Re-run `s9_yield.py` unchanged once a tail
  transistor exists before relying on the 3-corner shortcut.
  Full data: `nebula/S9_YIELD.md`.
- **G48 — (nebula) 11 cores do NOT buy 11x; budget ~100 ms per corner
  evaluation, not 0.42 s and not 38 ms.** Measured on 220 identical tasks:
  1 worker 318 ms/task, 2 workers 179 (1.78x), 4 workers 150 (2.11x), 8
  workers 106 (3.00x), 11 workers 100 (3.18x). **Efficiency collapses after
  2 workers and the curve is flat past 8** — 8 to 11 buys 6%. Each run spawns
  a process, parses the trimmed library and writes `wrdata` files, so wall
  clock is dominated by process launch and disk I/O, and extra workers contend
  for the same disk. Two ways to get this wrong: dividing the 0.42 s single-run
  figure (G36) by the core count (predicts 38 ms, off by 2.6x), or quoting the
  serial number for a parallel run (predicts 318 ms, off by 3.2x). Both have
  appeared in cost estimates in this project.
- **G49 — (nebula) a 47-minute experiment's raw results were gitignored, and
  they are gone.** `s9_yield_results.json` is `.gitignore` line 67, filed under
  "RUN ARTIFACTS — regenerable. Nothing here is an input to anything." It was
  regenerable in principle — the Latin-hypercube sampling is seeded — but
  nobody had to regenerate it until session 11 wanted the per-design
  coordinates behind `S9_YIELD.md` §4's 155/100 split, at which point it cost
  **7560 fresh SPICE runs / 23 min** to get back. It would have cost the full
  47 min if the population had not been seeded, and it could not have been
  recovered at all if the box or the seed had moved in between.
  **The rule: an experiment's output is TRACKED if any deliverable quotes a
  number from it.** A results file that took longer to produce than it takes to
  review is an INPUT to the write-up, not a build artifact.
  Two further things the loss cost, both worth knowing before trusting the word
  "regenerable" again: the JSON stored only **counts and design indices**, so
  even surviving it would not have carried per-design `f_peak`/`peaking` and
  this analysis would have needed the re-simulation anyway; and regeneration
  reproduces bit-identically only on the same machine, PDK and trimmed library.
  `nebula/experiments/robust_geometry_data.csv` is tracked for exactly this
  reason (1890 rows, lossless `repr` floats), and it makes the whole session-11
  analysis re-runnable with **no simulator**. `check_reproduction()` asserts the
  regenerated population against 10d's published counts and refuses to draw a
  figure on a mismatch — without that gate a silently different population
  would have produced a plausible, wrong write-up.
  **Same class of loss, one level up:** the commit that added
  `ROBUST_GEOMETRY.md` also rewrote this section and collapsed G2–G28 into
  one-line stubs, dropping G29 and G31–G47 entirely. It was recovered by
  splicing §9 out of commit `4a286a8` (44 gotchas, 347 lines) and re-appending
  G45–G49. **Before rewriting HANDOFF wholesale, diff the gotcha count**:
  `grep -c '^- \*\*G' HANDOFF.md`.
- **G50 — (nebula) `@m[cgg]` is NOT the gate load a driver has to supply. It
  understates it by 1.9-2.7x, silently.** BSIM4's `cgg` instance parameter is
  the **intrinsic** gate charge derivative. Two real terms are missing:
  (a) the gate **overlap** capacitance — SKY130's `nfet_01v8` card carries
  `cgso = cgdo = 2.449e-10 F/m`, i.e. ~3.9 fF per side on a 16 um device;
  (b) **Miller multiplication of C_gd** by the following stage's own voltage
  gain. The trap is that the *intrinsic* C_gd of a saturated device really is
  ~0 (measured 1.8e-17 F), which makes "C_gd is negligible" feel safe — but
  the *overlap* C_gd is not, and it is multiplied by (1 + |A|). Measured on
  the loading stages of `CL_RANGE.md`:

        stage         W      |A|    @m[cgg]    real load    ratio
        summer_min    4 um   1.34    3.27 fF     6.56 fF     2.00x
        summer_max   12 um   3.00    9.68 fF    24.43 fF     2.52x
        slicer_max   16 um   3.52   12.71 fF    34.34 fF     2.70x

  The ratio grows with gain, which is the signature. **Measure it as the AC
  current the driver must supply** into the gate under the drive the real
  circuit applies (differential, here), through a zero-volt ammeter:
  `C = Im{i(Vgp)} / (omega * v_gate)` — `nebula/device/cap_probe.py`. And
  cross-check it against the primitives (`analytic_load_ff`), because an AC
  current is not self-evidently a capacitance; agreement is 1.0% median.
  Consequence if ignored: a `cl` that is 2x low moves f_p2 and hence f_peak by
  ~0.5 octaves, half of S3's entire window, and nothing errors.
- **G51 — (nebula) a routing/parasitic number cannot be measured from this
  PDK install, but it can be DERIVED from it.** `C:\\Users\\DELL\\sky130A` carries
  `libs.tech/ngspice` and `libs.ref/sky130_fd_pr/spice` only — no tech LEF, no
  magic techfile — so there is no interconnect model to query. The route that
  works: SKY130's own vpp finger capacitors state both their total capacitance
  and their metal run length in squares
  (`cap_vpp_01p8x01p8_m1m2_noshield`: `ctot_a = 7.833e-16`, `rat_m1 = 0.387`
  over `22*rm1` squares, `rat_m2 = 0.596` over `28*rm2`), so capacitance per
  micron = rat*ctot/(n_sq*width) = **0.0984 fF/um (m1), 0.1191 fF/um (m2)**.
  The only declared input is the metal width (0.14 um, a design rule), and it
  is a DIVISOR — assume it wrong high and the answer comes out low. The figure
  is an UPPER bound for routing: a finger cap has a minimum-spaced neighbour on
  both sides and its `ctot` includes the m1-m2 coupling that makes it a
  capacitor. Prefer this to any remembered fF/um: it is in the repo's own PDK
  and it is parsed, not recalled.
- **G52 — (nebula) a resolution ladder that does not contain the points the
  verdict was made at can CONTRADICT that verdict, and it will look fine.**
  Session 12b measured "how wide a `cl` range can this design tolerate?" on an
  18-rung geometric ladder from 5 to 300 fF and reported **4.32x
  (16.1-69.5 fF)** for the one corner-and-load-robust design — while the screen
  that had just *found* that design passed it at **13.64 and 78.04 fF, i.e.
  5.72x**. Nothing errored; the ladder simply had no rung at either screen load,
  so the contiguous passing run stopped one step early on both sides. The
  measurement was of the ladder, not of the circuit. **Fix: merge the points the
  verdict was made at into any grid you then measure that verdict on** —
  `s9_yield.cl_ladder(include=PROMOTION_LOADS)`, pinned by a test. With them in,
  the answer is exactly 5.72x and consistent by construction. Generalise: when
  a follow-up re-measures something an earlier stage already decided, make the
  earlier stage's operating points members of the follow-up's grid, then
  disagreement is a bug rather than a resolution artifact.
  Related and worth pairing with it: the same run's median `S3_f_peak` margin at
  `cl_lo` is **-17.453 GHz**, which is *exactly* the last `ac dec 50` grid point
  at or below the `meas ac MAX` 20 GHz search ceiling. It is the **search edge,
  not a peak** — the honest reading is "above 20 GHz or no peak at all". Harmless
  to the verdict (either way it fails the window, unlike G44), but a median
  margin quoted from it is a property of the sweep setup.

- **G53 — (nebula) the SKY130 model-bin ceiling is on W PER FINGER, not on
  total width.** Measured against the trimmed library at TT: `W=100 nf=1`
  builds and `W=101 nf=1` aborts with "could not find a valid modelname";
  `W=200 nf=2` and `W=400 nf=4` build, `W=210 nf=2` and `W=410 nf=4` abort. The
  break is exactly at **W/nf = 100 um**, which is the `wmax = 1e-4` of the
  widest bin in `sky130_fd_pr__nfet_01v8__tt.pm3.spice`. So `nf` does not
  multiply width (G38 stands) but it DOES multiply the ceiling: total width up
  to `nf x 100 um` is available.
  **Why it matters:** a tail sinking several mA at `vdsat <= 0.2 V` with
  `L >= 0.5 um` needs several hundred microns of width. Read the limit as a
  total and that device looks unbuildable when it is routine. `PROPOSED_BOX`'s
  `w_in` provenance says "the SKY130 nfet_01v8 W bin limit (wmax = 1.0e-4 m)",
  which is the PER-FINGER limit described as if it were a total — at
  `nf_in` = 8 the real ceiling is 800 um. **Reported, not folded into the
  bound** (rule 6): widening `w_in` is a human's call and it would change the
  sampled population.
  `nebula/device/tail.py::W_PER_FINGER_MAX_UM` and `min_nf_for_width()` own it;
  a geometry outside the bins RAISES rather than reaching ngspice, because
  ngspice's message for it is G31's misleading one.
- **G54 — (nebula) ngspice's `.noise` can return `inoise_total = -nan(ind)`,
  and it exits 0.** Found on a current-mirror tail: the mirror's REFERENCE
  device drives both tail gates equally, so its noise is perfectly common-mode
  and is rejected to machine zero, and ngspice's integrated-noise log-slope
  integration then evaluates `log(0)`. Only that one contributor is ever NaN;
  every other stays finite, which is what identifies the mechanism. Knife-edge
  in geometry — W = 141 um fine, 200 um NaN, 218 um fine — so it is numerics,
  not physics.
  **It was caught only by ACCIDENT**: `crosscheck.py`'s numeric regexes do not
  match "nan", so the value parsed as `None` and the run failed as "could not
  parse". A laxer parser would have carried NaN into a spec check, where
  `nan < tau` is False and reads as a genuine FAILURE — biasing a yield
  downward, silently. `_SILENT_FAILURE_PATTERNS` now carries an explicit
  `=\s*[-+]?(nan|inf)` pattern, anchored to `= value` so `nfactor` and
  `.param nano=1e-9` cannot trip it.
  **The fix is a real circuit element, not a workaround:** a bias-node bypass
  capacitor, which every current mirror has, to keep reference and supply noise
  off the shared gate. `C_BYPASS_F = 10 pF`. **The value provably does not
  change the answer** — 1p/10p/100p/1n give `inoise_total` identical to every
  printed digit wherever they all compute — which is how we know it is not
  buying the result. A residual ~0.4% of runs still NaN at extreme widths;
  raising the bypass clears individual cases, so it is a bounded numerical
  nuisance rather than a physical limit. **Its area is not yet in any S7
  estimate** — there is no S7 estimate — and whoever builds one must include it.
- **G55 — (repo) the root `README.md` was the INHERITED one, and it was the
  most visible false claim in the project.** Rule 1 ("never fabricate a
  number") was being enforced rigorously inside `nebula/` while the front page
  of the repository advertised `rtl/`, `verification/`, `veriloga_models/`,
  `matlab_models/`, `optical_dsp.py`, `ml_equalizer.py` and three Cadence/Ocean
  flows as working features — every one of which §7 lists as **NEVER RUN / NOT
  AUDITED**. It also stated **48 tests** against an actual **698**, and gave a
  Cadence quick-start for a repository whose competition track **mandates
  open-source tooling and forbids proposing commercial tools in deliverables**
  (CLAUDEwa.md §2).
  **Why it survived 14 sessions:** every session edited `HANDOFF.md`, which is
  the file the working rules point at, and nobody had a reason to open
  `README.md` — the rule says update the handoff, and the handoff was always
  updated. **An inherited file that no rule points at does not get audited by a
  rule that points somewhere else.** The generalisation, which is the useful
  part: the Phase-0 audit assumed bugs in inherited *code* and found seven; it
  never extended that assumption to inherited *documentation*, which cannot
  fail a test and therefore cannot be caught by the test suite.
  Fixed 2026-08-06 (session 14b): `README.md` rewritten with an explicit
  "Not audited — treat as untrusted" section naming all ten items, plus
  `docs/PROGRESS.md` and `nebula/README.md` as reader entry points.
  **Before publishing anything outward-facing, re-read it as a stranger would**
  — and check that every capability it claims has a test or a write-up behind
  it.
- **G56 — (nebula) `mult` and `mf` are MISMATCH parameters, not device
  multipliers. They do NOTHING, silently.** Every SKY130 resistor and MIM
  subckt declares `mult` (or `mf` on the MIM), which reads exactly like a
  parallel-device multiplier. In every one of them the parameter appears
  **only inside mismatch terms**, all multiplied by `MC_MM_SWITCH`, which the
  corner files set to 0. Measured on `res_high_po` w=1 l=1.78 at 10 uA:

        mult=1   942.90 ohm
        mult=4   942.90 ohm      <- IDENTICAL, a silent 4x error
        m=4      235.72 ohm      <- exactly /4

  and on `cap_mim_m3_1` w=l=30: `mf=4` gives 1.8197 pF, `m=4` gives 7.2789 pF.
  **Use ngspice's native `m=`.** It agrees with four explicitly instantiated
  parallel devices to every printed digit. Note the EXISTING netlists write
  `mult=1` on nfet instances (`test_trimmed_lib.py`, `ngspice_runner.py`) —
  harmless at 1, but do not read it as evidence that `mult` works.
  `device/passives.py` and `test_passives.py` own this.
- **G57 — (nebula) `w` is INERT on the fixed-width resistor families, and an
  absurd value raises nothing.** `sky130_fd_pr__res_high_po_0p69` with
  `w=0.69`, `w=2.85` and `w=99` all return **2893.64 ohm**, identical to every
  digit. The width is encoded in the SUBCKT NAME and baked into that subckt's
  `rsheet`; the `w` parameter survives only in mismatch terms. The device that
  really is 2.85 um wide (`res_high_po_2p85`) reads **718.61 ohm** — so asking
  the wrong subckt for a width is a **4.03x error, silently**. `l` IS honoured
  on these families; only `w` is inert.
  The five widths that exist are **0.35, 0.69, 1.41, 2.85, 5.73 um**, for both
  `res_high_po_*` and `res_xhigh_po_*`. `passives.fixed_width_subckt()` raises
  on anything else rather than letting it through.
  **Related and separate:** ngspice DISCARDS the GENERIC families' `p2`, `q2`,
  `p3`, `q3` ("unrecognized parameter - ignored"), which are the
  voltage-coefficient terms — so `res_high_po` simulates as perfectly LINEAR
  while the fixed-width families, which carry their voltage coefficients as
  behavioural `r = {...}` expressions, do not. **The two families disagree
  about whether a poly resistor is linear, and the generic one is optimistic.
  Do not quote an S4 number off it.**
- **G58 — (nebula) the PASSIVE corner axis is ORTHOGONAL to the MOS one, and
  every corner number this project published held the passives at TYPICAL.**
  All five MOS sections (`tt ss ff sf fs`) in `sky130.lib.spice` include the
  same `r+c/res_typical__cap_typical.spice`. That was never a decision — the
  MOS corner names simply do not touch the passives. The library provides the
  **full 5 x 5 cross product** as named sections:

        tt ss ff sf fs        MOS corner, passives typical
        ll hh hl lh           passives varied, MOS TYPICAL (no `tt_` prefix!)
        ss_ll ... fs_lh       every remaining combination

  so **S9's 45 corners become 225**, not the 135 a three-passive-corner guess
  gives. `passives.lib_section(mos, passive)` owns the naming, including the
  dropped `tt_` prefix. Measured spreads: poly resistor **+/-12.5%**, MIM
  **-11.7/+12.9%**.
  **The trap inside the trap: the MIM capacitance depends on BOTH letters, and
  the second one is not the capacitor.** `camimc` follows the capacitor letter
  as expected, but `tol_m3` — the metal width tolerance, which sets the plate
  SIZE — follows the **RESISTOR** letter, because it is the same metal layer
  the resistor's interconnect is drawn in. Magnitudes are asymmetric too
  (mixed corners +/-0.065 um, matched +/-0.0455 um). So `hh` and `lh` both
  carry "cap_high" and differ by **0.7%**. A model validated at ONE corner
  misses this entirely; it was caught only by measuring at four.
- **G59 — (nebula) a channel model with a magnitude and no phase is
  NON-CAUSAL, and nothing raises.** `|H(f)| = 10**(-IL_dB(f)/20)` with zero
  phase has an impulse response symmetric about `t = 0`: **48.0% of its energy
  arrives before the pulse was launched.** Every cursor, residual-ISI and eye
  number computed from it is finite, plausible and wrong. This is the repo's
  failure mode #1 in its purest form — the pulse response even *looks* right,
  because it is the correct shape smeared symmetrically.
  **Fix:** reconstruct minimum phase from `ln|H|` (`link/channel.py`
  `_min_phase_from_magnitude`, the standard real-cepstrum fold) and then GATE
  on the measured energy at `t < 0`.
  **The part that is genuinely useful, and it generalises to any FFT-based
  channel work: how to tell time-domain ALIASING from a broken reconstruction.**
  A correct min-phase response in a finite buffer still shows some pre-`t=0`
  energy, because the tail wraps. Sweep the buffer length:

        n_fft   4096     8192    16384    32768    65536
        pre E  8.7e-5   1.3e-5   1.8e-6   2.5e-7   3.5e-8

  A **clean power law is aliasing** and is fixed by lengthening the buffer. A
  **floor** is a phase error and lengthening does nothing. `DEFAULT_N_FFT`
  (32768 = 512 UI at 64 samples/UI) was chosen this way, and the threshold
  (1e-6) was stated BEFORE the measurement and not moved to fit it.
- **G60 — (nebula) §6's design equations over-predict the Nyquist boost by
  0.8-1.5 dB, and the error GROWS with `R_s`.** Measured over the 14
  S3-meeting settings of the session-16 compression sweep:
  **+0.77 dB at Rs=150 up to +1.47 dB at Rs=600.** The cause is the same
  omission that makes §6's `A_dc` gate marginal — it neglects `r_o`, so the
  degeneration factor `k` comes out too large — but the CONSEQUENCE is
  different in kind. `cross_check_extraction()` only compares `A_dc`, so a
  1.5 dB shape error passes a gate aimed at gain.
  **Why it bit:** the compression re-run integrates the whole pulse response
  *through* the analytic model, so a 1.5 dB boost error became a **28% error in
  the headline compression ratio** (3 dB read 1.93x instead of 1.51x). It was
  caught only by comparing the model's boost against the measured one.
  **Rule: never integrate a waveform through `deq.predict()`.** Calibrate first
  — `f_z = 1/(2*pi*Rs*Cs)` and `f_p2 = 1/(2*pi*RL*CL)` are EXACT (passives),
  `g_dc` comes from the measurement, and only `k` is fitted, from the measured
  boost at Nyquist. Then the peaking and the peak frequency are INDEPENDENT
  checks and §5.3b's 0.5 dB reject threshold applies to them (measured
  +0.094-0.232 dB, and f_peak -8.6 to -4.8% against `meas ac MAX`'s own 4.7%
  quantisation).
- **G61 — (nebula) "compression ratio" has THREE definitions in this repo and
  they disagree by up to 1.8x.** All three are "required output swing / measured
  1 dB limit"; they differ in what pattern they assume:

        A  Nyquist content in, Nyquist gain out   (session 9c/9d)   2/7 compress
        B  long-run level in, PEAK gain out       (calibration C3)  7/7 compress
        C  peak distortion through the real pulse response          5/7 compress

  At 3 dB of channel loss they read **1.22 / 1.16 / 1.51**. A and B are
  *proxies* for a worst-case data pattern; **C computes it** — the worst pattern
  puts every UI-spaced sample of the pulse response on the same side, so the
  excursion is `sum_k |pr(t + kT)|` maximised over `t`. **Use C, and say which
  one you used.** The trap that makes this a gotcha rather than a preference:
  A and B respond to DIFFERENT inputs, so a change to the model can move one and
  leave the other untouched — the deleted DC-loss constant moved B and never
  touched A, which is why the published 1.22x survived a change that was
  supposed to invalidate it.
- **G62 — (nebula) a test that greps the tree for a forbidden identifier must
  not contain that identifier.** `test_channel_model.py` asserts the retired
  DC-loss constant appears in no executable file; written with the name as a
  literal, it finds ITSELF and fails forever. Assemble it from pieces
  (`RETIRED_CONSTANT = "CHANNEL_DC" + "_LOSS_DB"`). Same applies to the
  documentation sweep: the retirement has to be written down somewhere, so the
  Markdown check uses an explicit allowlist of the files that record the
  history rather than banning the string outright. A gate that cannot pass is
  indistinguishable from a gate that is ignored.

- **G63 — (nebula) `alter` fails silently on an element the netlist no longer
  CONTAINS, and returns the previous geometry's numbers.** G35 is about `alter`
  on a subckt-wrapped device. This is the other half: once
  `SizingPoint.passives` carries drawn devices, the ideal `Rdeg`/`Cdeg`
  instances do not exist at all, so `run_tunable_sweep`'s `alter Rdeg = ...`
  matches nothing. ngspice reports it as a **warning**, carries on, and
  **exits 0** (G26) — and all 67 settings come back carrying the FIRST
  geometry's numbers. A converged-looking sweep of a single point, at 13.6 ms
  per "setting", with a monotone-looking table at the end.
  **`run_tunable_sweep` now REFUSES `passives is not None`** and says so in the
  failure string; a test pins it. Generalise: `alter` is only safe on an
  element you can prove is in the netlist you just wrote, and the netlist is
  now a function of two independent switches (`tail`, `passives`).
- **G64 — (nebula) a validity guard built for one failure was silently doing a
  second job, and the second job erased the reward gradient over half the box.**
  `Sky130Point.has_interior_peak` is a CONJUNCTION:

        peaking_db > 0.25            AND        (g_pk_db - g_top_db) > 0.25

  The right-hand condition is G44 — a response still RISING at 20 GHz, where
  `meas ac MAX` returns the range edge and `peaking_db` is **fictitious and
  large**. Measured: `rl` = 800 ohm at 3.25 mA reports **1.08 dB of "peaking"
  at 19.95 GHz** with `g_pk - g_top` = -0.001 dB.
  The left-hand condition rejects something completely different: a **genuine
  interior maximum that is merely SMALL**. Measured: `rs` = 50 ohm reports
  **0.165 dB at 1.318 GHz** with `g_pk - g_top` = 9.23 dB. Nothing about that
  measurement is wrong — the circuit simply does not equalise.
  Using the conjunction as an RL validity gate made **every low-boost design
  INVALID**, i.e. it put the reward floor across the entire bottom of the
  parameter box — which is exactly where a randomly initialised policy starts,
  so the policy would have seen a flat floor and had nothing to climb. It also
  made the "flat" and "operating point fails" calibration references score
  IDENTICALLY, which is what surfaced it.
  **Fix: `Sky130Point.peak_is_sweep_edge` carries the G44 half alone** and is
  what `rl/evaluator.validate` uses. `has_interior_peak` keeps both halves
  UNCHANGED, because `s3_yield.py`, `s9_yield.py` and `robust_geometry.py`
  publish counts computed with it. **Generalise: before reusing a boolean as a
  gate, check whether it is a conjunction, and whether every term of it rejects
  the same KIND of thing.**
- **G65 — (nebula) 78% of everything an RL policy finds is G44.** Measured over
  a 500-step PPO run at TT with real passives: 765 evaluations, **203 invalid
  (26.5%)**, of which

        peak_is_sweep_edge   159   78.3%
        tail_triode           28   13.8%
        pair_triode           16    7.9%
        everything else        0

  Under a reward that scores S3 peaking, **every one of those 159 would have
  been a HIGH reward for a circuit with no peak at all** — a large fictitious
  `peaking_db` read off the sweep edge. So the G44 guard is not defensive
  programming; it is load-bearing, and it is doing four fifths of its work
  against one failure mode. The invalid rate did NOT rise over the run (28.8%
  first half, 24.3% second), but 500 steps cannot distinguish a trend from
  noise and the useful output is the histogram, not the trend. **Bucket
  invalidities by MECHANISM from the first run**: a single aggregate rate says
  the agent found holes and not which ones.
- **G66 — (nebula) drawn passives move `f_peak` by MORE than the whole
  load-robustness slack, and every published corner/load number held them
  ideal.** `PASSIVES.md` §6 item 1 (the "4d regression") had not been run. Run
  on six designs including 432, TT, ideal `R`/`C` vs `to_geometry()` devices:
  worst **|d f_peak| = 0.1329 octaves** against the **0.12 octaves of centring
  slack** session 12b measured for the sole load-robust survivor. Worst
  |d peaking| = 0.2116 dB. **Every non-zero shift is NEGATIVE**, and the
  mechanism is the one `PASSIVES.md` §4.4 predicted: the drawn load resistors
  carry a `res_po` bottom-plate parasitic and **half of it lands on the output
  node**, adding **1.4-24.3 fF to a `cl` of 32.6 fF — up to +75%** — which
  lowers `f_p2`. `g_dc` moves at most 0.0006 dB and noise at most 0.27%, so
  this is not general accuracy loss; it is one specific capacitance.
  The deltas are exact multiples of **0.0664 octaves**, `meas ac MAX`'s own
  quantisation on an `ac dec 50` grid (session 11), so the shift is 0, 1 or 2
  grid steps and the measurement sits at its resolution limit — but the
  headline does not depend on the resolution. **Consequence: the load screen
  and the corner screen both need re-running with drawn passives before design
  432 can be quoted as load-robust.**
- **G67 — (nebula) `to_geometry` is ELECTRICALLY stable and GEOMETRICALLY
  chaotic.** Near `rs` = 318.6 ohm a **0.016% change in the target flips the
  chosen device entirely**:

        318.50 ohm -> w=8     l=6.720   m=1     area  53.8 um^2
        318.55 ohm -> w=10    l=18.780  m=2     area 375.6 um^2
        318.58 ohm -> w=2.85  l=4.445   m=2     area  25.3 um^2
        318.60 ohm -> w=10    l=8.730   m=1     area  87.3 um^2
        319.00 ohm -> w=8     l=14.785  m=2     area 236.6 um^2  <- PASSIVES.md

  Every one lands within 1e-4 relative of its target, so the resistance is
  stable to four figures; `resistor_geometry` scans a width ladder and keeps
  whichever candidate lands nearest after `l` snaps to the 5 nm grid, and which
  one wins is arbitrary at that resolution. Two consequences:
  **(a) `design_id` grouping by drawn geometry is FINE-GRAINED, not coarse** —
  measured on the 500-step log, 765 step rows gave 765 distinct `design_id`s
  and 764 distinct geometry tags. The grouping is still CORRECT for task 8's
  grouped train/test split (identical geometry, identical id), but do not
  expect it to collapse many continuous values into one group.
  **(b) AREA is not a stable function of the electrical target** — a **15x area
  spread across a 0.16% resistance spread**. `PASSIVES.md` §4.5's 1506 um^2
  figure for design 432 is the `rs = 319` row; the `rs = 318.58` row is 25 um^2
  for the same resistance. Any S7 number is a property of the quantiser as much
  as of the design.
- **G68 — (nebula) two ways to build a gate that fails for the WRONG reason,
  both found in one session.**
  **(a) A one-sided perturbation conflates "inert" with "leaves the feasible
  region".** The §6e sensitivity gate perturbs each action dimension and asserts
  the observation moves. Probing one direction only, it reported `i_bias` as a
  FAILED dimension and blocked training — but `i_bias` is not inert: +0.15 of
  the box takes 3.25 -> 4.93 mA, which raises gm enough to push the peak out of
  the sweep, and the validity gate correctly rejected the result. Those two
  diagnoses need opposite responses. **Try both directions; report `INVALID
  BOTH` only if neither produces a circuit** — which is a finding about the
  base point, not about the axis.
  **(b) Order validity checks CAUSE BEFORE SYMPTOM.** The same gate reported
  `rl` at the box ceiling as an *f_peak range* failure when what had happened
  was that the load drop took the input pair **out of saturation**; the AC
  plausibility checks ran before the DC operating-point checks. If the bias
  point is wrong, every small-signal number describes a different circuit.
  `validate()` now runs presence -> operating point -> device regions -> AC
  plausibility -> G44. Same fix applied a second time: the G44 sweep-edge test
  moved AHEAD of the `f_peak` range test, because both fire on the same results
  and the range test was reporting a numerical oddity where the mechanism was a
  fictitious peak — **hiding 159 of 203 invalidities behind the wrong label**
  (G65).
- **G69 — (nebula) `shutil.which("ngspice_con")` cannot find this project's
  ngspice, and a skipped test reports as a PASS.** The binary lives in the
  conda env (G20) and is not on PATH in a plain shell. A test guarded with
  `pytest.mark.skipif(shutil.which(...) is None)` therefore SKIPS silently —
  and the skipped test was the only one exercising the real simulator end to
  end. **Use `nebula.device.ngspice_runner.ngspice_path()`**, which checks the
  conda location first and falls back to PATH. Generalise: a skip condition is
  a gate, and a gate that is always true is indistinguishable from a deleted
  test. Check that your skip guard can be FALSE on the machine you are on.
- **G70 — (nebula) ONE concurrent ngspice makes each run 4.8x slower against
  the EXTENDED library, and G48's numbers do not transfer.** Measured on the
  same netlist and the same machine: a bare `run_point` with drawn passives
  costs **1.93 s alone and 9.28 s** with a single other ngspice process
  running. G48 measured the nfet-only library at 318 ms serial and 179 ms/task
  at 2 workers, i.e. per-task time rose only **1.13x** under one competitor.
  The extended trim's per-task degradation is **4.8x** — four times worse —
  because the R/C corner files pull in `parameters/typical.spice` (3023 lines)
  and `invariant.spice` (7340), so two processes thrash the same files
  (`PASSIVES.md` §6 item 6).
  **Two things this breaks, both of which happened:**
  (a) **A training run's wall-clock decomposition is meaningless if anything
  else was simulating.** Session 17's reward-v1 pass overlapped a pytest run
  that calls ngspice, and its per-evaluation times came out 7-40 s against the
  clean run's 2.07 s. Its timings are DISCARDED and only its load-independent
  results (invalid rate, shortfall distribution) are quoted.
  (b) **Never probe a machine that is mid-experiment.** The diagnosis above was
  itself made by running a timing probe alongside the training run, which is
  why the probe read 9.28 s.
  Practical rule: run one SPICE experiment at a time, and treat any
  wall-clock number gathered otherwise as an upper bound on nothing.
- **G71 — (nebula) a benchmark whose passes run in a fixed order MEASURES THE
  ORDER, and it nearly published a wrong conclusion.** The §6i parallel sweep
  runs 24 identical tasks at 1, 2, 4, 8 and 11 workers. Run in that order it
  reported **4.39x at 11 workers — BETTER than G48's 3.18x** — and the
  explanation was ready ("the extended library's longer compute phase amortises
  process launch better"). It is an artifact: the **1-worker pass ran FIRST, on
  a cold OS file cache**, and paid to read the PDK include tree from disk;
  every later pass hit a warm cache.
  **The tell was in the table and it is worth memorising: 2 workers reported
  2.55x.** A super-linear speedup from two processes is not physics, so the
  BASELINE was wrong, not the parallelism.
  Re-run with the worker counts REVERSED, so the 1-worker pass runs last:

        workers          1       2       4       8      11
        forward  ms   6075.6  2380.5  1667.9  1518.8  1383.0
        reversed ms   2224.0  1335.7   942.2   841.0   888.5
        true speedup   1.00x   1.67x   2.36x   2.64x   2.50x

  The serial baseline drops **2.7x**.
  **AMENDED after two further runs: RANDOMISING IS NECESSARY BUT NOT
  SUFFICIENT.** With the configuration order randomised AND a control re-run of
  the first configuration at the end, on a completely IDLE machine, the control
  still came back at **1.60x** — 8 workers measured 2497 ms/task running first
  and 1558 ms/task running last. **The first configuration always pays,
  whichever one it is**, because the penalty is the OS file cache warming on the
  PDK include tree, not a competing process. Shuffling only stops the penalty
  from always landing on the same configuration and looking like a property of
  it.
  **The fix is a DISCARDED WARM-UP PASS; the control is the DETECTOR.**
  `parallel_throughput` now does three things by default — warm up and discard,
  randomise the order, re-run the first configuration last and flag a ratio
  outside [0.8, 1.25]. With all three, clean:

        workers          1       2       4       8      11
        ms/task     3999.1  2007.5  1627.8  1341.0  1547.7
        speedup      1.00x   1.99x   2.46x   2.98x   2.58x
        control: 8 workers re-run last 1577.9 vs 1341.0 = 0.85x, CLEAN

  **The honest answer is 2.98x at 8 workers, and 11 workers is SLOWER than 8** —
  so the extended library scales worse than G48's nfet-only 3.18x AND its curve
  turns DOWN past 8 rather than flattening. Same mechanism as G70. `n_valid` was
  identical at every worker count in every run, which is what makes the timing
  comparison meaningful at all.
  **Rules: (1) warm up and discard before measuring; (2) randomise the pass
  order; (3) re-run the first configuration last as a control; (4) treat a
  super-linear speedup as a bug report rather than a result.**
- **G72 — (nebula) A VALIDITY GATE AND A REWARD ANSWER DIFFERENT QUESTIONS,
  AND CONFLATING THEM DESTROYS THE GRADIENT WHERE A FRESH POLICY LIVES.**
  The generalisation of G64, promoted to its own gotcha because it is the rule
  and G64 is one instance of it.

        a validity gate asks:  "can I TRUST this measurement?"
        a reward asks:         "is this CIRCUIT good?"

  Two results can look identical — no usable AC spec set — and need OPPOSITE
  handling:

        peak reported at 19.95 GHz    UNTRUSTWORTHY measurement. `meas ac MAX`
                                      returned its own search edge; the number
                                      is fiction. Nothing may be scored.
        device in TRIODE              TRUSTWORTHY measurement of a BAD circuit.
                                      `.op` converged; vds and vdsat are real.
                                      Only the AC spec set is untrustworthy.

  **So trustworthiness is per ANALYSIS, not per evaluation.** `rl/evaluator.py`
  returns three verdicts — VALID, HEADROOM_ONLY (`.op` good, device in triode,
  AC dropped, graded on `vds - vdsat`), INVALID — and `rl/reward_v1.py` has
  four exactly-separated bands to match, every boundary a function of the spec
  count `N` alone:

        feasible       >= N+1
        infeasible     [-N, 0)
        headroom-only  (-(N+2), -(N+1)]     graded, ordered by triode depth
        invalid        -(N+3)

  **Why it matters rather than being tidy:** `tail_saturation` binds on
  2.6-13.3 % of the box, so a fresh policy lands in triode often. A flat floor
  there gives it no direction out; a graded band does. Measured on design 432
  with `i_bias` and `rl` both at their ceilings — 293 mV into triode on the
  pair, 81 mV on the tail — the score moves from the floor (-10.0) to **-8.746**,
  and 1 mV / 10 / 50 / 100 / 300 / 1000 mV grade to -8.010 / -8.091 / -8.333 /
  -8.500 / -8.750 / -8.909, strictly ordered at every depth.
  **One design detail that is not a preference:** the graded band uses the
  bounded map `h/(1+h)` and **not** the `clip(h, 0, 1)` used everywhere else.
  The clip exists in the infeasible branch so one catastrophic spec cannot
  drown out the others in a SUM; here there is no sum, so a clip buys nothing
  and costs exactly what the band exists for — a design 500 mV into triode
  would score identically to one 50 mV in.
- **G73 — (nebula) a weak-but-live action dimension is worse than a dead one,
  and the test for "worse" is REDUNDANCY, not effect size.** The §6e gate
  cleared `tail_j` and `l_tail` as live: both moved `tail_margin_v` by ~0.10 of
  a channel scale under one `MAX_STEP`, well above the inert threshold. They
  were removed anyway, because `vcm_in` moves the SAME channel by **0.605** —
  a **6x stronger lever on the quantity the tail geometry exists to control**.
  A policy gradient on a weak dimension that is redundant with a strong one
  learns noise and spends samples doing it; this is G38's `nf_in` argument
  (+/-10 % non-monotonic) generalised from "the axis barely moves anything" to
  "the axis moves something another axis already moves better".
  **The action space went 9 -> 7** (`w_in`, `l_in`, `i_bias`, `rs`, `cs`, `rl`,
  `vcm_in`), the tail is DERIVED — `w_tail = i_side * TAIL_UM_PER_AMP` at
  `TAIL_L_UM`, imported from `s9_yield.py` so there is one definition — and
  `tail_saturation` REMAINS an active scored constraint. **Removing the degrees
  of freedom does not remove the coupling**: `vds_tail` is still the input
  pair's source node, so VCM, `w_in`, `l_in` and `i_bias` still meet in one
  inequality. This closes `TAIL_DEVICE.md` §6's recommendation, which had been
  a proposal without an RL measurement behind it.
  **The habit: read a sensitivity table for REDUNDANCY, not only for zeros.**
  A table that only reports pass/fail against an inert threshold cannot see
  this, which is why §6e's table reports `|d_obs|` per dimension per channel.

- **G73 -- (nebula) a "peak at the sweep edge" test written as an ARGMAX test
  can never fire on a one-zero/two-pole response.** That magnitude falls as
  1/f eventually, so its maximum is ALWAYS interior and an
  argmax-at-the-top-of-the-grid check is dead code that looks like a guard. It
  fired **zero times on 1890 designs**, which is how it was caught. What the
  SIMULATOR reports as an edge is a peak above ITS OWN search top, so the
  analytic predictor must use `evaluator.F_PEAK_HZ_LIMITS[1]` -- the same
  number, one definition (rule 9). The G44 population is caught anyway, 84.3 %
  of it, under the f_peak-out-of-window label. **The general form: a guard
  whose condition is unreachable is indistinguishable from a guard that was
  deleted. Count how often each one fires.**
- **G74 -- (nebula) the reward has a CEILING set by the AC sweep grid, not by
  the circuit, and it is worth +8.950669.** `meas ac MAX` can only report
  frequencies on `ac dec 50 1meg 100g`, i.e. a lattice **0.066439 octaves**
  apart, and `reward_v1`'s feasible branch is `B + min_i(margin_i/tol_i)` with
  `S3_f_peak` binding at nominal. The nearest lattice point to the mid-window
  target is 0.024665 octaves away, so `8 + (0.5-0.024665)/0.5 = 8.950669` is
  unreachable-from-above. **Measured: four independent runs found four
  DIFFERENT designs all scoring 8.950670.** Consequence for any benchmark:
  best-reward-at-budget SATURATES and cannot separate methods at nominal --
  report simulations-to-CEILING beside it. It is not a defect in the reward; it
  is the reward faithfully reporting the resolution of the measurement
  underneath it. **Before using any "best score" as a discriminator, work out
  whether the measurement can resolve it.**
- **G75 -- (nebula) a parallel speed-up measured on isolated evaluations does
  not transfer to a workload whose workers also compute.** Session 17 measured
  **2.98x at 8 workers** on 24 bare ngspice evaluations. The same 8 workers on
  the baseline benchmark -- where each also runs CMA-ES's eigendecomposition,
  GP-BO's O(n^3) fit or PPO's torch forward between simulations -- measure
  **1.80x** (3.060 s/sim single process against 1.698 s/sim aggregate, over 33
  runs and 1992 simulations). Sizing an overnight run to the first number plans
  12 hours and takes 15. **Measure the speed-up on the workload you are going
  to run, not on the simulator alone.**
- **G76 -- (nebula) a screen's population rates can transfer while its
  ACCURACY does not, and widening cannot fix a bias.** The analytic pre-screen
  moved from its calibration population to the benchmark's kept its
  free-rejection rate (61.7 -> 63.9 %) and its yield lift (2.60 -> 2.66x) --
  both of which look like "it transfers" -- while its `f_peak` MdAPE went
  **4.93 -> 15.85 %** and its false-rejection rate **0.39 -> 3.88 %**, ten
  times its declared budget. Widening the accept window 2.5x left the false
  rejection at 2.33 % and cost 24 points of free rejection, because **a window
  absorbs VARIANCE and this was BIAS** (+0.361 dB of peaking, traced to a gm
  model fitted where `I_D = i_bias/2` exactly against a real mirror delivering
  4-8 % less). **Validate a calibration on the population you will USE it on,
  and check the bias separately from the spread -- an aggregate rate can hide
  a systematic offset completely.**

- **NUMBERING NOTE, 2026-08-17.** Two entries above are BOTH numbered **G73**
  (the weak-but-live action dimension, and the ARGMAX peak test). Left as they
  are on purpose -- other files cite "G73" and renumbering would break those
  references silently, which is worse than the duplicate. **G77 and G78 were
  cited in code before they existed here; both are now written in below**, so
  the gap session 20 left open is closed.

- **G77 -- (nebula) a GENERATED artifact that a caller silently PREFERS is a
  second definition, and it can make a benchmark measure its own treatment as
  its baseline.** `device/spice/pdk_trim/` is generated by
  `device/pdk_trim.py` and must never be hand-edited: every file there is a
  pure function of the PDK plus the monolithic libraries, the keep-set is read
  out of the library's own include list so adding a device widens it
  automatically, and `test_pdk_trim.py` **re-derives all forty files on every
  run and fails on a single differing byte**. That is what stops a trim from
  going stale -- the G32 failure (the file a human reads is not the one that
  produced the numbers), one layer up.

  **The earned half is the selection, not the editing.**
  `sky130_runner.lib_for_device` takes the one-section fast path **whenever
  the file exists**, silently and by design. So `experiments/lib_cost.py`'s
  "before" arm, which swapped only `CTLE_LIB`, was still being served the
  SPLIT library -- i.e. the control arm was running the treatment, and the
  benchmark would have reported the improvement as its own baseline. **It was
  live for one run before being caught.** The fix is
  `_no_section_libraries()`, which points `pdk_trim.SECTION_DIR` at an empty
  directory so the real fallback branch runs. **If a lookup has a silent fast
  path, any A/B that swaps the slow input has to disable the fast path too.**

  Corollary, same session: a hand-made `sky130_ctle.lib.spice.bak` sat in the
  tree showing the OLD PDK include paths. It was deleted once
  `pdk_trim.untrimmed_library_text()` was shown to reproduce it byte for byte
  -- **a backup of a file you can derive is a second definition with none of
  the guarantees.**

- **G78 -- (nebula) ngspice expands EVERY `.lib` SECTION in a file, not just
  the one you ask for.** This is the whole reason the extended library was
  slow, and it was invisible for four sessions because every measurement
  compared whole libraries against each other and never a library against
  ITSELF with sections removed. Same netlist, same machine:

        extended library, ONE section extracted     0.093 s
        extended library, the real 25-section file  1.386 s   <- 15x
        nfet-only library, the real 5-section file  0.297 s

  **The cost scales with the SECTION COUNT, not with what the netlist uses.**
  The extended library grew to 25 sections the day G58 added the 5x5
  (MOS x passive) corner cross product, and its per-evaluation cost went with
  it -- so the fix for a corner-coverage decision showed up as a throughput
  regression nobody could attribute.

  **The standing explanation was wrong in BOTH halves, and both were quoted in
  `PASSIVES.md` §3.2 and in G70 and believed for four sessions:** that the R/C
  corner files pull in `parameters/typical.spice` (3023 lines) *and*
  `invariant.spice` (7340). **`invariant.spice` is not in the include tree at
  all** -- only `parameters/montecarlo.spice` includes it, and no section this
  project uses reaches that. And `typical.spice` is real but MINOR: it defines
  **8909 named parameters of which the library references 86**, and removing
  the other 8823 is worth about **1.55x** against the section split's 15x.
  **When a cost explanation has never been tested by removing the thing it
  blames, it is a hypothesis, not a diagnosis.**

- **G79 -- (nebula) the gm/I_D method's central premise is FALSE on SKY130 at
  fixed `nf`, and it fails smoothly.** The classical method assumes `gm/I_D`
  depends on the inversion level and not on `W`, so one sweep at a reference
  width scales to any width through the current density `I_D/W`. Measured at
  TT/27, L = 0.30 um, V_ds = 0.75 V, V_sb = 0.40 V, V_gs = 0.90 V:

        W (um)     10       20       40       60      100
        W/nf     2.50     5.00    10.00    15.00    25.00
        I_D/W  1.25e-5  1.43e-5  1.72e-5  1.87e-5  1.95e-5
        gm/I_D   10.74    10.23     9.63     9.31     9.14

  `I_D/W` moves **1.56x across the `w_in` box**; `gm/I_D` moves 15 %. Median
  relative spread at matched `V_gs` across W = {20, 40, 100}: **2.33 % for
  gm/I_D, 33.13 % for I_D/W**. The mechanism is **G53's** -- the SKY130 model
  bins are cut on **W per FINGER**, and holding `nf` at 4 (G38) while sweeping
  `W` 20 -> 100 um sweeps W/nf 5 -> 25 um straight across the bin set.
  **The variation is SMOOTH AND MONOTONE, which is what makes it dangerous**:
  it interpolates beautifully, and scaling `I_D` linearly in `W` -- the
  textbook step -- is a **56 % width error** on a device that simulates
  perfectly happily. Any gm/I_D work here needs `W` as a real axis
  (`device/gmid_lut.py`; `check_width_independence()` is the measurement).

- **G80 -- (nebula) you write MICRONS and you read back METRES.** `W=40` in a
  netlist means 40 um because the libraries set `.option scale=1e-6` (G31), but
  `print @m.xm1.m<dev>[w]` returns `4.000000e-05` -- SI metres. **A geometry
  read-back check written the obvious way (compare the number you wrote against
  the number you read) fails by 1e6 on a completely correct circuit**, which is
  G31's failure mode wearing the opposite sign, and the natural reaction is to
  delete the check. Do the conversion in one place and say why:
  `gmid_lut._assert_geometry_applied`. Two corollaries measured at the same
  time: `nf` does NOT divide the read-back (at `W=40 nf=4` the instance reports
  4e-05, the TOTAL, confirming G38 from the other side); and BSIM4's **`cgs` is
  NEGATIVE** as reported (`cgg` +2.455e-14, `cgs` -1.663e-14, `cgd` +1.199e-16)
  because these are charge-derivative matrix entries, not terminal
  capacitances.

- **G81 -- (nebula) SKY130 REFUSES an out-of-bin WIDTH and SILENTLY
  EXTRAPOLATES an out-of-bin LENGTH.** `W = 0.1 um` aborts with "could not find
  a valid modelname" (the message G31 records as being read as a units error
  nine times out of ten -- here it is correct). `L = 99 um` **simulates
  happily**, and the current scales as a clean 1/L: I_D at V_gs = 1.2 V is
  5.92e-3 / 1.37e-3 / 1.56e-4 / 1.59e-5 at L = 0.15 / 1.0 / 10 / 99 um. So the
  answer looks entirely reasonable all the way out to a length nobody draws.
  **Consequence: on the L axis the PDK will not protect you.** Any table or map
  indexed on L must refuse to extrapolate on its own account --
  `common/design_space._axis_weights` is the only guard there is, and it raises
  rather than edge-clamping for exactly this reason.

- **G82 -- (nebula) an analytic peak-existence condition and the G44 guard ask
  DIFFERENT QUESTIONS, and the difference is the search ceiling.** The closed
  form asks *"does |H| have an interior maximum ANYWHERE?"*;
  `peak_is_sweep_edge` asks *"is the maximum WITHIN the 20 GHz search range
  sitting at the range edge?"*. A design peaking at 37 GHz has a genuine
  interior peak -- the closed form is RIGHT to say so -- and trips the guard
  anyway, correctly, because inside the search window the response is
  monotonically rising. Measured on 159 designs: the bare condition scored
  **TN = 0** against the guard -- it never once correctly excluded a design --
  and adding `search_top_hz = MAX_SEARCH_TOP_HZ` took it to TN = 8, FP 60 -> 52.
  **TN is the number to read on any pre-simulation filter**, not accuracy: a
  filter with TN = 0 has saved zero simulations however accurate it looks. The
  remaining 52 misses are model error (G66's `res_po` bottom plate on `cl`,
  G67's quantiser, and the 1z/2p model's own 4.25 %), not the ceiling.

- **G87 -- (nebula) adding a placeholder to a shared `str.format` template
  breaks every caller that formats it directly, and there is no warning.**
  `ac_sweep` and `hd3` added three fields to `sky130_runner._NETLIST`; the two
  production call sites were updated, and **five `test_tail.py` tests and two
  `test_tunable.py` tests went red with a bare `KeyError: 'tran_src'`** because
  they assemble the deck themselves. Mechanical to fix, but the lesson is not:
  **a shared template with growing placeholders needs ONE place that knows the
  optional fields and their absent-values**, or the next block added has to
  find every caller again. That place is `assemble_netlist()`, and every caller
  now goes through it.

- **G83 -- (nebula) `linearize` takes VECTOR NAMES, not a timestep, and getting
  it wrong DESTROYS THE PLOT while ngspice exits normally.** Measured while
  building the HD3 tier: `linearize 1e-10` prints

        Error: no such vector 1e-10
        Warning from checkvalid: vector outp is not available or has zero length.
        Error: RHS "v(outp) - v(outn)" invalid

  -- so **every later line in the `.control` block fails too**, the `wrdata`
  writes nothing, and the exit status is clean. G26 in a new place. Bare
  `linearize` is correct when the `tran` already uses a fixed step; it only
  resamples onto the uniform grid an FFT needs.

- **G84 -- (nebula) a `tran ... <stop> <start>` window is INCLUSIVE, so an
  "integer number of cycles" is one sample too long for an FFT.** 20 cycles at
  100 points/cycle arrives as **2001** samples, and `t[0]` and `t[-1]` are the
  SAME PHASE one period apart. Feeding all 2001 to an FFT describes a
  **20.01-cycle** window, which is not periodic: the fundamental leaks across
  every bin and buries the third harmonic under its own skirt, **while still
  returning a number**. Drop the duplicate endpoint. Caught on the first real
  run only because `hd3_from_waveform` checks the cycle count and raises --
  which is the reason to write that check even when the arithmetic looks
  obvious.

- **G85 -- (nebula) "the limit was not reached" is INFORMATION, and reading it
  as "unknown" rejected the BEST designs.** `measured_swing_pp_v` returns the
  1 dB compression point or `None`, and is right to refuse a fallback to
  `4*I*RL`. But `SwingLimits` says in its own docstring that `None` means *"the
  limit was not reached inside the swept input range -- which is information,
  not a failure"*. The first version of the link bridge read it as unknown and
  failed the design, which **rejected every `rs >= 400` sizing in the box --
  i.e. every heavily degenerated, and therefore most linear, stage.** The
  fallback is `max_swept_pp_v`: still MEASURED, and a LOWER bound, so the
  compression gate stays conservative rather than looser. **A sentinel that
  means "better than we could measure" must not be handled like one that means
  "we do not know".**

- **G86 -- (nebula) G68's ordering rule is easy to violate WHILE CITING IT.**
  The AC/HD3 dump checks were written as "asked for and not produced -> fail",
  placed BEFORE `scan_for_silent_failures`. So the first real HD3 failure
  reported *"hd3=True but ngspice wrote no hd3.txt"* -- the SYMPTOM -- while
  the cause (`Error: no such vector 1e-10`, G83) sat unread in the output the
  scan would have surfaced. The files are now read inside the temp directory
  but JUDGED after the scan. **Reading files and judging them are separate
  steps, and the judging belongs after the cause check.**

- **G88 -- (nebula) a SIMULATION budget does not terminate a PRE-SCREENED arm,
  and the failure is a silent hang rather than an error.** Every method loop in
  `experiments/baselines.py` terminates on `Objective.n_sims`, which is right
  and is 7f's first fairness rule (G65: charge every ngspice invocation). But a
  pre-screened rejection costs **zero simulations by design** -- that is the
  whole point of the screen -- so a screen that rejects every proposal leaves
  `n_sims` at 0 forever. `check_budget()` never raises, the LHS stream never
  ends, and the process spins at full CPU producing nothing. **Found by the
  test suite hanging for 400 s** on the test that asserts a screened rejection
  is free; the assertion itself was correct and the loop around it was not.
  Two consequences, both now in `exp_difficulty.py`:
  **(a) a screened arm needs a SECOND termination condition** -- a proposal
  cap, sized against the measured screen (61.7 % free rejection is ~2.6
  proposals per simulation, so 100x cannot bind by accident); and
  **(b) hitting it must be RECORDED** (`proposal_cap_hit`), because a run that
  stopped on the cap and a run that searched its whole budget and found nothing
  are the same three `None`s otherwise. Generalise: **whenever a cost model
  makes some action free, check that the free action cannot be taken forever.**
  Note this bites `baselines.py`'s screened arms too if the screen ever became
  pathological; there it has not been hit because the real screen accepts
  ~38 % of proposals.

- **G89 -- (nebula) RAISED AND KILLED IN ONE DAY: the pre-screen does NOT
  discard ceiling-capable designs, and the way the suspicion survived a day is
  the lesson.** Session 22's first pools measured the per-proposal ceiling rate
  at 9/2000 = 0.4500 % unscreened against 16/6645 = 0.2408 % screened -- a rate
  ratio of **0.535**, implying the screen threw away **46.5 %** of
  ceiling-capable designs, which would have biased every screened arm of the G3
  sweep against the metric the sweep reports. It was recorded as a **suspicion**
  because the 95 % CI **[0.236, 1.211] spanned 1.0**, and a confirmation run was
  ordered. Doubling the events killed it:

        arm            replicate 0        pooled r0 + r1
        unscreened      9 / 2000           14 / 4000   = 0.3500 %
        screened       16 / 6645           43 / 13391  = 0.3211 %
        rate ratio        0.535               0.917
        95 % CI      [0.236, 1.211]      [0.502, 1.677]

  **Implied false rejection on the ceiling population: 8.3 %, CI [-67.7, 49.8].
  No effect.** Both arms regressed to the mean from opposite directions (9 -> 5
  and 16 -> 27).
  **THE REUSABLE PART IS THE METHODOLOGICAL ERROR, NOT THE NUMBER.** The
  suspicion was written up as having *"an independent route agreeing with it"*:
  the closed form `ceiling rate = S3 rate / 15` predicted the unscreened rate to
  5 % and missed the screened one by 2.1x, which looked like corroboration by a
  different mechanism. **It was not independent -- it is computed from the same
  9 and 16 counts.** Two statistics derived from one small sample agreeing with
  each other is the same noise twice. On the pooled data the "2.1x
  arm-specific discrepancy" is 1.36x against 1.56x, i.e. a uniform
  over-prediction in BOTH arms and no arm-specific effect at all.
  **Generalise: before calling a second statistic independent corroboration,
  check whether it shares its DATA with the first. Different arithmetic on the
  same counts is not a second measurement.** And: a point estimate whose CI
  spans 1.0 is not a small finding, it is not a finding -- G89 exists as a
  record of one that was correctly labelled and correctly killed. Full data
  `nebula/DIFFICULTY.md` sec 4.3; both pools tracked as
  `experiments/difficulty_run.jsonl` and `experiments/difficulty_pool_r1.jsonl`.

- **G90 -- (nebula) the evaluator REQUIRES a real tail, so "ideal tail" is not
  a configuration you can measure -- it is an invalidity.**
  `rl.evaluator.validate` checks `vds_tail` and `vdsat_tail` for presence and
  finiteness, and ideal current sinks do not produce those primitives at all.
  So `evaluate(..., real_tail=False)` returns
  `invalid: vds_tail is missing from the ngspice output` for **every** design,
  not a measurement -- which silently converts "measure the ideal-tail
  population" into "measure nothing" while looking like a 100 % invalid rate.
  Consequence, session 22c: the 4th candidate cause of the 13.44 -> 7.10 % S3
  gap (session 13's 4-8 % mirror deficit) **cannot be attributed** without
  changing what `validate` treats as a failure, which is `BASELINES.md` sec 7f
  territory and a human decision. **Generalise: before designing an experiment
  whose arms turn a subsystem off, check that the VALIDATOR regards the
  turned-off state as legal.** A validator written for one configuration will
  report a different configuration as broken, correctly and uselessly.
  `exp_attribution.TAIL_AXIS_BLOCKED` records it and
  `test_the_tail_axis_is_blocked_and_the_block_is_measured` runs one and reads
  the reason, so the constant cannot drift from the behaviour.

- **G91 -- (nebula) `pytest.approx` has a default `abs=1e-12`, and every
  capacitance in this repo is smaller than that.**
  `150e-15 != approx(32.63e-15)` evaluates **False**: the two loads are 4.598x
  apart and compare EQUAL, because both sit far inside the absolute tolerance.
  A test written to assert that the calibration population is NOT at `cl_mid`
  therefore passed while asserting nothing. Found in session 22c on the test
  that carries the D4 finding. **Compare femtofarad and picofarad quantities by
  RATIO** (`abs(a/b - 1) > x`) **or pass an explicit `abs=`; never use a bare
  `approx` on a farad value.** Same shape as G31 and G80 -- the units in this
  project are small enough that library defaults chosen for volts and ohms are
  meaningless for capacitance.

- **G92 -- (nebula) TWO ARITHMETICS OVER THE SAME EVENTS ARE ONE MEASUREMENT,
  and computing a number twice is not corroborating it.** Session 22c raised
  G89 (the pre-screen discards ceiling-capable designs) and called it
  *"supported two independent ways"*: a direct rate ratio 9/2000 against
  16/2000, and a lattice argument `ceiling_rate ~ S3_rate/15` that missed the
  screened arm by 2.1x. **Those are not two supports. Both are functions of the
  same 9 and 16 counts.** Doubling the events took the ratio 0.535 -> 0.917 and
  killed the effect; on the pooled data the lattice arithmetic over-predicts by
  1.36x unscreened and 1.56x screened -- uniformly, with no arm-specific effect
  at all. **A second statistic computed from the same sample inherits that
  sample's noise in full, so agreement between the two says something about the
  algebra and nothing about the world.** The owner's own review then promoted
  the suspicion further, from "a suspicion with a CI spanning 1.0" to "caught
  three separate ways", by counting the same pair again.
  **Same family as G71**, which is the wall-clock version: a number that looked
  corroborated because it was measured twice in one ordering. The test in both
  cases is the same one -- *what would have to be independently true for these
  two figures to disagree?* If the answer is "nothing", there is one
  measurement. **More events, or a different population; not different
  algebra.** What survives about the pre-screen is narrower and rests on two
  genuinely independent measurements: session 18b's accuracy falsification
  (MdAPE 4.93 -> 15.85 %, false rejection 0.39 -> 3.88 %) and session 20's
  TN = 0. Its population rates transfer; its per-design accuracy does not.

## 10. Environment

- Windows 11, PowerShell 5.1 (+ Git Bash available), Python 3.13.14,
  numpy 2.2.6, scipy 1.15.3, pytest 9.1.1, matplotlib, pandas. No scikit-rf,
  no torch verified in current env (ml_equalizer imports torch — untested).
- git 2.52 for Windows. **This checkout: `main`, initial commit 2026-08-04,
  pushing to `origin` = https://github.com/jaikaushik-prog/nebula-ctle-rl.git —
  a NEW, PRIVATE repo built from this clean history** (the decision session 14b
  recorded, now carried out; verified private on 2026-08-07 and last pushed at
  `4b63021`). The older
  https://github.com/jaikaushik-prog/serdes-dsp-framework.git still exists and
  still has the PDFs in its baseline commit; it is an **unrelated history** to
  this one and must not be pushed to — see G1 as amended and G41.
  Credentials for `jaikaushik-prog` are in Windows Credential Manager, so
  `git push` works non-interactively; `gh` is installed but NOT authenticated.
  Commit identity comes from the global config (G12); never pass `-c user.*`.
- Cadence/Xcelium NOT available on this machine (Phase 4 blocked on access
  or open-source simulators).

## 11. Communication guidance (for agents working with the owner)

- The owner is a beginner: explain every change in plain language — what,
  why, what it implies — so they can present the work to their professor as
  AI-assisted work they fully understand. Prepare "professor-ready"
  one-sentence takeaways for findings and figures.
- Findings are presented with figures: fig1 (eyes closing = the problem),
  fig2 (waterfall + implementation penalty), fig5 (engine cross-validation),
  fig7/fig8 (CTLE role findings). fig3 answers "when does each EQ stage stop
  sufficing" (professor's framing).
- Professor context so far: responded to fig1 with the classic escalation
  ladder (CTLE → FFE → "DSP technique"); the framework already implements the
  full DSP receiver — communication should clarify rungs and offer fig3.

---

## 12. SESSION LOG (append-only — newest at bottom; NEVER delete old entries)

### 2026-07-18 — Session 1 (audit) 
Mapped reference library; audited codebase; wrote docs/ROADMAP.md with
findings (4 confirmed bugs, modeling gaps, phased plan).

### 2026-07-18 — Session 2 (Phases 0–1)
git init + baseline; fixed 7 correctness bugs (scrambler, MLSE, seeds,
references, theory, two-pass EQ, README FEC); 28 tests. Built waveform
engine: Channel.apply, tx_waveform w/ jitter, CTLE class, Alexander-BB
CDRSampler (gearshift+clamp), MMSE cursor fix, adapt_start, JTOL mode.
48 tests. Commits: baseline, Phase 0, Phase 1.

### 2026-07-18 — Session 3 (figures + Phase 2)
make_report_figures.py (figs 1–4, palette-styled). statistical_eye.py:
ISI-PMF engine, wᵀRw noise, bathtub, RJ fold; cross-validation (~3×
agreement, fig5); optimize_ctle with crossing_jitter_ui() CDR-feasibility
constraint (Finding #1: CTLE's job = timing health). CLI modes statistical/
optimize; figs 5–7. 60 tests. Commits: figure generator, Phase 2.

### 2026-07-18 — Session 4 (Phase 3a + GitHub)
pd_mode='mm_postffe' (frozen timing-FFE + MM PD; sign convention fixed and
documented); locks where Alexander fails; jitter flat ~20 mUI (fig8).
Finding #2: ADC clipping limits 0-dB-CTLE BER (17 % clipped); added
clip_probability(), adc_clip_frac, calibrated clip constraint. 65 tests.
Pushed to private GitHub; commit authors rewritten to Jai Kaushik (G12);
HEAD 3aa5b28. Explained figs/circuits to owner for professor comms.
Created HANDOFF.md + CLAUDE.md (this change).

<!-- NEW SESSIONS: append below this line using the same format:
### YYYY-MM-DD — Session N (short title)
What changed, why, key results, new gotchas, commits/hashes, test count.
Then update §2/§5/§6/§7/§8/§9 above if they changed. -->

### 2026-07-23 — Session 5 (UCIe direction + owner takes FFE; no code change)
Docs-only session; no code touched, tests unchanged (still 65 passing).
- Professor pointed owner at external repo `hussin-mohamed/UCIE_GP`. Analyzed it:
  it is the UCIe 3.0 **logical/digital** PHY (SystemVerilog + UVM, 14 nm, 16
  lanes, up to 32 GT/s NRZ forwarded-clock, 500 MHz logical clock). Blocks:
  link-training FSM, sideband, TX path (byte-to-lane -> LFSR scramble ->
  serializer), RX path (detectors -> lane-assembly -> descramble). It
  **explicitly excludes the analog front-end / channel / SI modeling.**
- Relationship to this framework: two different halves of a link at two layers
  (this repo = analog/DSP electrical PHY; UCIE_GP = digital logical PHY). They
  meet only at the serializer-output -> analog-TX seam (where TX-FFE lives).
  UCIE_GP does NOT improve this framework's analog models, but offers (a) a
  proven UVM verification template for our un-simulated rtl/*.sv (§8 #5), and
  (b) a serializer/scrambler RTL reference.
- Group task = build the analog PHY around UCIE_GP, split 6 ways: channel,
  serializer, driver, CTLE, DFE, FFE. **Owner chose FFE** (most AI-tractable:
  pure DSP/math, no transistor-level ambiguity, existing code to build on).
- Professor answered scope Q1: aim for the **high-rate regime WITH DSP
  equalization** (not light UCIe NRZ). So this framework's context is on-target;
  FFE = a real multi-tap adaptive equalizer, not token de-emphasis.
- Recorded the FFE math+build plan as §8 item 0. Next: teach Part A step 1
  (ISI + why an FFE is needed) in beginner plain language.
- Added §3 reference row for UCIE_GP and §1 "New Direction" paragraph.
- Professor then sent his own 12-page handwritten FFE note (`Part 11 FFE.pdf`);
  analyzed it in depth (added §3 reference row). It is effectively the owner's
  FFE syllabus and maps onto the §8 item-0 plan. Verified his boosting formula
  (K=1/3 -> 9.54 dB). Flagged a mismatch in his 3-tap zero-forcing worked answer
  (see §3 note) as a question to bring back to him.
- Taught Part A step 1 (ISI/pulse response) in chat, then built `ffe_learning/
  ffe_demo.py` to VISUALIZE it (added to §2): channel low-pass -> ISI -> eye
  closes -> 7-tap zero-forcing FFE -> eye reopens, plus channel/FFE/combined
  freq response. Teaching point captured: zero-forcing over-boosts a lossy
  channel (taps exploded to ~5.8 / main tap 1.27 -> noise enhancement) which
  motivates MMSE (already in equalizers.py) as Step 3.
- NEXT: Part A step 2 = zero-forcing math by hand (using professor's 3-tap
  example, which also resolves the tap-sign question).

### 2026-08-03 — Session 6 (Nebula track: interface freeze + mocks + tests)

New parallel project, separate contract: **`CLAUDEwa.md`** — the Nebula
competition (Astera Labs x BITS Goa), RL-driven CTLE sizing for a 5 Gbps PCIe
Gen2 link, team of three, final deadline 15 Sept 2026. Added §2 repo-map
entries, §8 item -1, and gotchas G16-G19.

**What was built.** The thing CLAUDEwa.md §5.1 says must exist before any
implementation: `common/types.py` plus mocks and interface tests for all three
layers, so three people can build in parallel against a frozen interface.

- `nebula/common/types.py` — §5.1 contracts verbatim (Corner, TargetSpec,
  DeviceResult, LinkResult), the §3 spec constants with per-row provenance
  comments, and `all_corners()` = the 45-corner S9 grid with TT/1.00/27 first.
  One deliberate strengthening of §5.1: numeric fields are `Optional[float]`
  and `__post_init__` enforces `ok=True <=> every field finite` /
  `ok=False <=> fail_reason set and no numbers`. Failure carries `None`, not
  `nan`, because `None` explodes on first arithmetic whereas `nan` propagates
  silently into a reward and poisons a training run without an error message.
- `nebula/common/design_equations.py` — §6 equations, plus
  `cross_check_extraction()`: the §6 "if A_dc disagrees, stop" gate as code.
- `nebula/common/params.py` — action-space names from §5.2. **BOUNDS is empty
  and `param_space()` raises.** See G17.
- `nebula/device/` — `evaluate()` protocol, `safe_evaluate` (any exception ->
  `ok=False`), `reject_bad_fit` (§5.3b), and a synthetic square-law mock whose
  headroom checks make a large slab of the sizing space return `ok=False`,
  which is what the RL loop must learn to avoid.
- `nebula/link/` — `calibration.py` (the §5.3a conversion, see G18),
  `config.py` (two required numbers with no defaults), `interface.py`
  (`propagate_device_failure`, `safe_evaluate_link`), synthetic bridge mock.
- `nebula/rl/reward.py` — the §9 shortfall reward: non-positive, saturating at
  zero, per-spec normalised, eight terms (S3 x2, S4, S5, S6, S7, S8 x2),
  `worst_corner_reward` = min over corners, `total_reward` = + discriminator.
  Failure floor defaults to `-N_SPEC_TERMS`, which is the mathematical minimum
  of R_spec rather than a tuned penalty.

**Tests: 228 new, all passing, <1 s.** `python -m pytest nebula/tests -q`.
Existing suite re-run before and after: **65 passing, unchanged**. Together:
293 passing, ~50 s (G19). Highlights: `test_mv_calibration.py` is the
dedicated hand-computed test §5.3a demands (every expected value derived in a
comment, not by calling the code under test); `test_reward.py` pins "no bonus
for exceeding a spec" by showing a met spec cannot pay for an unmet one;
`test_design_equations.py` pins the factor of two in `1 + gm*Rs/2`.

**Known asymmetry recorded, not fixed:** the §9 normaliser `(|x| + |tau|)`
depends on `x`, so for the S3 "match" terms an undershoot is penalised
slightly harder than an equal overshoot. Inherent to the §9 form; pinned by a
test so it stays known.

**Four decisions deliberately left to a human** (CLAUDEwa.md §8 rule 6 — all
four are required arguments with no defaults, so nothing runs until they are
stated): the 12 parameter ranges (needs G1), the two link numbers
(`v_in_diff_pp_v`, `channel_loss_db_at_nyquist` — neither is in the §3 spec
table), and the two S3 reward tolerances (`peaking_tol_db`, `f_peak_tol_hz`).

**Not done / next:** G0 and G1 are both overdue and both gate everything else.
No ngspice, no PDK, no netlist, no RL, no NRZ retarget yet.

### 2026-08-03 — Session 7 (Nebula: G0 passed, compression bug fixed, NRZ audit)

Three workstreams, all in `nebula/` plus one toolchain install. Tests:
**251 nebula + 65 existing = 316 passing** (`python -m pytest tests nebula/tests -q`).

**1. G0 GATE PASSED — `nebula/G0_RESULTS.md`.**
Installed Miniforge3 (user scope) and a `nebula` conda env with **ngspice 41**
from conda-forge, then ran a source-degenerated diff pair through all four
analyses. `.op`, `.ac`, `.noise` all work.

**The finding: `.disto` returns exactly 0.0 for BSIM4.** Proven with a
controlled A/B in one netlist — same topology twice, BSIM4 (`level=54`) vs
Shichman-Hodges (`level=1`), same source. level=1 gives HD3 = −59.3 dBc;
BSIM4 gives 0.0 for both HD2 and HD3. `.disto` itself works; BSIM4 just does
not implement the derivatives. Every open PDK is BSIM4-based, so no PDK fixes
it. **S4 must be measured by transient + FFT.** That fallback is built and
verified: HD3 = −89.7 dBc on the reference point, with HD2 ~180 dB down
(correct for a balanced pair — its absence would have meant an unbalanced
netlist). Cost: **0.256 s/corner vs 0.066 s** for AC+noise, so ~12 s for a
full 45-corner sweep with HD3. Recommendation recorded: put HD3 in the
promotion tier only, keeping the inner loop at 0.066 s/corner.

New gotchas G20–G23 (use `ngspice_con.exe`; `.disto` two-tone trap; PySpice
broken and not worth fixing; several `meas`/`fft` syntax traps).

Still outstanding for G0: **no PDK installed** (generic BSIM4 cards were used
— CLAUDEwa.md's own documented fallback), no tail-transistor headroom, no
corner model cards. The PDK is specifically needed for MIM caps and poly
resistors, without which the S7 area estimate has nothing behind it.

**2. Link-layer compression bug fixed (gotcha G24).**
`min(g_dc * v_in_pp, vout_swing_v)` was wrong twice over — wrong gain (DC
instead of the peaked response the eye actually sees, understating the swing
by exactly the S3 peaking) and a silent clamp where the correct answer is
"the small-signal model does not apply here". Now split into
`output_swing_pp_v()` (unclamped, takes `|H(f_nyquist)|`) and
`check_compression()` (returns a reason the link layer turns into `ok=False`).
Calibration conventions rewritten as C1–C4.

This immediately found something real: the previous mock reference sizing
drove **994 mVpp into a 460 mVpp linear limit** under a PCIe Gen2 minimum TX
swing. The replacement reference point (found by grid search, valid at all 45
corners AND every point of the loss sweep) has **g_dc = 0.27 — it attenuates
at DC.** That is not a mock artifact; it is how a CTLE driven by a
PCIe-class swing has to be biased, and G0's independent ngspice run agrees
(DC gain −14.6 dB, peak −6.3 dB, i.e. 8.3 dB of peaking at 1.26 GHz).
**Expect G1 to hit the same wall.**

Also per human decision this session:
- **Channel loss is now a swept axis, not an assumption.** `LinkConfig`
  requires `channel_loss_db_at_nyquist`; `sweep_channel_loss()` and
  `DEFAULT_LOSS_SWEEP_DB` (3–12 dB, read off S3's tunable range) give the
  reporting axis. Pass rate vs channel loss is a curve, not a number to defend.
- **Input amplitude is derived, not configured**: `v_in_diff_pp_v` is now a
  property = TX swing × channel attenuation, anchored to
  `PCIE_GEN2_TX_DIFF_PP_MIN_V = 0.8 V`. **Provenance is a secondary source
  only** (Renesas Gen2 PCIe Hardware Design Guide); the PCI Express Base Spec
  is paywalled and not in `resources/`. A human must confirm it before it
  appears in any deliverable — until then the report must call it an
  assumption.
- **Reward tolerances set**: ±1 dB peaking, ±10% of target f_peak
  (`f_peak_tol_frac`, fractional so it scales across S3's 1.25–2.5 GHz).
  Deliberately loose so the policy can learn at G3; real CTLEs tune in
  discrete steps a dB or two apart, so ±1 dB is at production granularity and
  ±0.5 dB would be tighter than the hardware. `TOLERANCE_SWEEP` makes it a
  reported axis rather than a hidden constant.

**3. NRZ retarget audit — `nebula/NRZ_RETARGET_AUDIT.md`. No code changed.**
CLAUDEwa.md §4.3 names five four-level assumptions; the audit found **24**,
grouped A–G with a SILENT/LOUD/PERF risk marking on each and a recommended
order of work. The dangerous ones are the SILENT group: the `0.75·Q` BER
prefactor (must become `1.0·Q` — leaving it reports BER 0.75× the truth),
`PAM4_RMS = sqrt(5)` in the AGC (scales every downstream amplitude by 2.24×),
`adc_vref = 4.0` (wastes two ADC bits on a ±1 signal), `sqrt(5·Σg²)` in
`crossing_jitter_ui` (overestimates jitter by 2.24×, would falsely declare the
CDR infeasible), and `CTLE.from_peaking`'s **absolute** 28/56 GHz pole
defaults — CLAUDEwa.md §12's named trap, callable without arguments.

**Next:** G1 hand-design (human, blocks the parameter bounds and the abstract),
PDK install, abstract due Aug 6.

### 2026-08-03 — Session 7 addendum (channel model corrected; reference verified)

Review follow-up on session 7. **320 tests passing** (255 nebula + 65 existing).

**1. Channel model had a real inconsistency — fixed (new gotcha G25).**
`link/mock.py` compared the channel's **absolute** loss at Nyquist against the
CTLE's **boost**, which is a *relative* quantity (|H(f_nyq)|/|H(0)|). That is
only self-consistent for a channel with exactly 0 dB loss at DC, and no real
channel has that — conductor, dielectric and connector losses are broadband.

The channel is now two numbers, and the CTLE equalises the difference:

    tilt_dB = channel_loss_db_at_nyquist - channel_loss_db_at_dc
    v_in_diff_pp_v     = TX swing attenuated by the DC loss   (long-run level)
    v_in_nyquist_pp_v  = TX swing attenuated by the full loss (eye content)

`channel_loss_db_at_dc` defaults to **1.0 dB** and is a **placeholder with no
measured provenance** — a human must replace it, ideally with a real `.s4p`
(§8 item 1), which would retire this whole parameterisation. A high-pass
channel (Nyquist loss < DC loss) is now rejected outright.

Compression is now checked against `max(equalised Nyquist level, long-run
level)`: a run of identical bits sits at the DC level through `g_dc`, and that
excursion has to fit linearly too.

Effect on the reference point: eye at 3 dB total loss moved 172 -> 129 mV
(the tilt there is 2 dB, not 3, so the CTLE is more over-equalised than the
old model thought). Everything still passes.

**2. The reference sizing was verified, not assumed (the falsifiable test).**
Eye height at TT across the whole loss sweep: **129 / 171 / 189 / 193 / 143 mV**
at 3/5/7/9/12 dB. Worst case over all 45 corners x 5 loss points is
**111.6 mV** against S8's 100 mV. So the DC attenuation (g_dc = 0.27,
-11.4 dB) is an *expected property* of a degeneration CTLE at PCIe TX levels,
not a symptom of a bad search. G0's independent ngspice run agrees
(-14.6 dB DC, -6.3 dB peak, 8.3 dB peaking at 1.26 GHz).

**3. The squeeze is from both ends of the loss sweep.** Maximum permissible
peak gain set purely by compression: **+0.5 dB at 3 dB loss**, rising to
+9.5 dB at 12 dB loss. So compression binds hardest at LOW channel loss (big
input) while S8 binds hardest at HIGH loss (small input). A single design must
satisfy the tightest of each. Worth knowing before G1: it is the low-loss end
that forces the low gain.

**4. The reference search was checked for degeneracy and is not degenerate.**
Concern raised: a search whose only constraint is "does not compress" is
trivially won by minimising gain. It is not, because in this topology
`vout_swing_v` scales with RL alongside the gain, and lowering RL also raises
f_p2 and hence the peaking. Measured, sweeping RL with everything else fixed:

    rl= 40  g_dc=0.090  pk=14.94 dB  -> 81/225 link evaluations COMPRESS
    rl= 60  g_dc=0.134  pk=13.31 dB  -> 45/225 COMPRESS
    rl=120  g_dc=0.269  pk= 9.74 dB  -> all ok, worst eye 111.6 mV, S8 PASS
    rl=200  g_dc=0.448  pk= 6.56 dB  -> 103/225 COMPRESS

The chosen point is bracketed by failures on both sides. (Correction to the
session-7 summary: low-gain designs fail by *compressing*, not by failing S8 —
the ranking was already on worst-case eye height, but the earlier one-line
claim about why low gain loses was wrong.)

**5. Cost scaled to a training run — the abstract's number.** At 1e5 PPO steps:
TT no HD3 **1.8 h**; TT with HD3 **7.1 h**; 45 corners no HD3 **3.4 days**;
45 corners with HD3 **13.3 days**. A **175x spread**, measured on this
machine, which is the quantitative justification for the three-tier fidelity
hierarchy. Recorded in `nebula/G0_RESULTS.md`.

**Note for G1:** `vout_swing_v` (600 mVpp at the reference point) is itself a
design variable — headroom, VDD, device sizing — not a constant. If gain turns
out to be the binding problem, that is the lever.

### 2026-08-03 — Session 8 (G1 hand-design audited against ngspice)

Owner did the G1 hand-design and populated `nebula/common/params.py::BOUNDS`.
This session verified it **against the simulator**, not by inspection.
**332 tests passing** (267 nebula + 65 existing). New: G26–G29.

**What was right.** The netlist (`nebula/device/spice/g1_handdesign.cir`) is
sound and uses the correct `1 + gm*Rs/2` degeneration factor. The reference
point reproduces: peaking **8.29 dB @ 1.259 GHz**, noise **0.275 mVrms**,
power **6.0 mW** — S3/S5/S6 all met with margin at TT/27C. Starting from the
already-validated G0 point rather than a fresh guess was the right call.

**1. The §6 cross-check silently failed and was reported as passing (G26).**
Every `let` after the `.ac` in that netlist errored — `@m1[gm]` is not
available in the `ac1` plot, only in `op1`. So `k_degen`, `Adc_predicted`,
`gain_error_db` and even `peaking_db` were never computed. The 8.19 dB figure
was correct arithmetic done by hand; the automated gate CLAUDEwa §6 says must
not be passed simply did not run. ngspice reports these as warnings, not
errors, and exits 0.

**2. Run properly, §6 AS WRITTEN FAILS ITS OWN GATE (G27).** Measured at the
G1 point (gm = 10.973 mS, gmbs = 3.583 mS, Rs = 800, RL = 120):

    simulated A_dc            -14.57 dB
    §6 as written             -12.24 dB   -> off by 2.33 dB   GATE FAILS (tol 1 dB)
    §6 + gmbs                 -14.29 dB   -> off by 0.28 dB   passes

§6 assumes the bulk is tied to the source. In a bulk process every NMOS sits
in the grounded substrate, so the moving source drives the body too and
`k = 1 + (gm + gmbs)*Rs/2`. gmbs/gm was **0.33** here — not a small term the
1 dB tolerance can absorb. `design_equations.predict()` and
`cross_check_extraction()` now take `gmbs`, defaulting to 0.0 so §6 verbatim
is still reproducible. Five new tests pin this.

**3. The bounds were audited with 2000 ngspice runs.** Latin hypercube over
the 12-dim box, one `.op`+`.ac`+`.noise` per point:

    90.7% simulate (0% non-convergence; 9.3% land in triode)
    90.7% meet S5 — free in this box     90.7% meet S6 — free
     5.3% meet S3 (peaking 3-12 dB AND f_peak 1.25-2.5 GHz)

**S3 is the binding constraint, not S5/S6.** But the box is not wrong: passing
points span peaking **3.06-11.88 dB** and f_peak **1.26-2.40 GHz**, i.e. it
reaches every corner of S3. The 5.3% is because S3 couples (gm, Rs, Cs, RL, CL)
and no axis-aligned box can be efficient against it — which is exactly what
the surrogate and OOD discriminator are for. **5.3% is the honest random-search
baseline G3 must beat. Recorded, not engineered away.**

**4. Two concrete bound errors fixed (G28).**
- `rl`'s provenance justified its 500 ohm ceiling with *"barely fits in
  VDD=1.8V"* — but the BSIM4 hand-design runs at **VDD = 1.2 V**. The 1.8 V
  came from the separate SKY130 netlist. At 12 mA and 500 ohm the load drops
  **3.0 V into a 1.2 V supply**. The ceiling is kept (at 1 mA it drops only
  0.25 V and that corner is useful) but it is now documented as JOINT with
  i_bias, and `params.headroom_ok()` rejects the infeasible pairs analytically.
- `cl` trimmed **5 pF -> 3 pF**: measured, no sample above 2.92 pF ever met S3
  (f_p2 falls below the peak window). Cost nothing, removed dead space.
- `nf_in` provenance said "ref 1" while the synthetic mock uses nf_in=4. Noted
  in the provenance string — they are different devices, do not compare.

Combined effect, re-measured over 400 samples: **9.5% rejected for free**
(no SPICE call), triode failures 9.3% -> 2.5%, and yield **2.7% -> 4.7% per
SPICE call**.

**5. Noise number is structurally sound.** Checked whether the bare model card
omits flicker noise: it does not — BSIM4's default noia/noib/noic are non-zero
and 1/f is present. Integrating from 1 kHz instead of 10 MHz changes the total
by <1%, so the S5 band sits above the flicker corner and is thermal-dominated.
The *magnitude* is still uncalibrated generic-BSIM4, not a PDK.

**6. SKY130 is installed but does not parse — precise diagnosis (G29).**
The PDK IS at `C:\Users\DELL\sky130_fd_pr` with all five corner files. The
blocker is not `sqrt()`: setting `set ngbehavior=hsa` in a **`.spiceinit`**
(not in `.control`, which is too late — `.include` is processed at parse time)
clears that. The real blocker is that the raw `sky130_fd_pr` repo is the
Spectre/HSPICE-oriented source form: `...__tt.pm3.spice` holds a `.subckt`
whose parameters are declared by a `.param` line INSIDE the body, which
ngspice reads as "13 formal but 0 actual params", and the corner file contains
**zero `.model` cards** so `sky130_fd_pr__nfet_01v8__model` is never defined.
**Fix: install `open_pdks` (or use `volare`), which generates the
ngspice-ready `libs.tech/ngspice/sky130.lib.spice`.** Do not keep patching the
raw repo. Estimated 1-2 h; it does NOT block the abstract.

**Still outstanding.** S9 is unverified — every number above is TT/27C, and
corner cards need the PDK. The bounds may not survive SS/125C.

**New this session:** `nebula/device/ngspice_runner.py` — batch-mode driver
(netlist template -> subprocess -> parsed `SpicePoint`). Not the full device
layer (no `DeviceResult`, no corners) but it is what made this audit possible
and is the foundation the real wrapper builds on.

### 2026-08-04 — Session 9 (contract corrections, SS6 gate moved to Python, SKY130 installed, NRZ fixes 1-3)

**Tests: 332 before -> 383 after.** (`python -m pytest tests nebula/tests -q`,
~77 s.) Split: `tests/` 65 -> 92, `nebula/tests/` 267 -> 291.
Nothing was deleted or weakened; two existing tests gained explicit arguments
where a dangerous default was removed.

**P0 — four corrections to CLAUDEwa.md, all applied.**

1. **SS6 now carries the body-effect term.** `k = 1 + (gm + gmbs)*Rs/2`, with
   the measurement table and the reason (bulk process, grounded body, moving
   source). Also recorded the hand-sizing consequence: `Rs ~ 3/gm` oversizes
   by a third, use `Rs ~ 3/(gm+gmbs) ~ 2.25/gm`; deep n-well would remove the
   term at an area cost, considered and rejected.
2. **New standing rule SS8 #9 — "a check that reports failure as a warning and
   exits zero is not a gate."** ngspice's exit code is never a success signal.
3. **Provenance audit of all 12 bounds** (see below).
4. **SS3 reframed:** S5/S6 marked *measured free* (90.7% each), S3 marked
   **the** binding constraint at 5.3%. The old "noise vs power will be the
   real fight" note is gone — it would have aimed the next session at the
   wrong problem.

**The provenance audit found the confusion was real but contained.** Three
bounds are supply-dependent and are now labelled as such — `i_bias` (its
12 mA ceiling is S6 evaluated at 1.2 V: 14.4 mW; at 1.8 V the same current is
21.6 mW and fails S6 outright), `rl` (joint with `i_bias`, and its string used
to cite 1.8 V), and `vcm_in`. The other nine are supply-independent. The stray
1.8 V came from `spice/g1_sky130.cir`, which really is an 1.8 V device — so
the number was not invented, it was transplanted. One unrelated defect found
and recorded rather than papered over: `rs`'s measured evidence covers
100-2000 ohm but the bound is 50-2500, i.e. the ends are extrapolation.

**P1 — the SS6 cross-check now lives in Python and can fail.**
New `nebula/device/crosscheck.py` + `nebula/tests/test_crosscheck.py`
(24 tests). It parses `.op` primitives and `meas` results out of raw ngspice
stdout, does the arithmetic in Python, and **raises**. `scan_for_silent_
failures()` greps for the G26 warning shapes first, so a dirty run can never
be read as a clean result; a short, justified benign-list keeps SKY130's
per-device conductance-reset warnings from crying wolf.

Three fixtures of **real captured ngspice output** are checked in under
`nebula/tests/fixtures/`, so the suite needs no simulator and runs in 0.2 s.
One of them is the historical broken run itself — the exact text that exited 0
while computing nothing — so the scanner is tested against the real thing.

**Verified falsifiable, twice.** A parametrised test corrupts A_dc by ±3 and
+12 dB and requires `CrossCheckFailure`. Separately, `raise_if_failed` was
temporarily neutered and 4 tests went red, confirming they are not vacuous.

**Running the netlist properly turned up more than G26 recorded.** The
`.control` block failed for a *second* independent reason: `.param` names such
as `{RS_OHM}` are not visible as `.control` vectors at all, so even
`let power_mw = v(vdd) * {ITAIL} * 1000` had nothing to multiply. All derived
arithmetic has been removed from `g1_handdesign.cir`; it now prints primitives
only and the file carries a comment saying why. New gotcha **G30**.

**A real inconsistency surfaced while building the fixtures (G32).** The two
netlists that describe "the same" G1 reference point had **different model
cards**, differing by exactly one parameter — `k2`, BSIM4's body-effect
coefficient, i.e. precisely the term the SS6 correction turns on:

        parameter        g1_handdesign.cir      ngspice_runner.py
        k2               absent                 0.05
        gm               11.154 mS              10.973 mS
        gmbs              2.787 mS               3.583 mS
        gmbs/gm             0.250                  0.327
        A_dc            -14.123 dB             -14.569 dB
        peaking            8.19 dB                8.29 dB

Every measured number in HANDOFF came from the runner; the `.cir` a human
opens and edits gave different ones. `k2=0.05` added to the netlist, which now
reproduces HANDOFF SS2 exactly (gm 10.97342 mS, gmbs 3.582543 mS,
A_dc -14.56892 dB, peak -6.279118 dB at 1.258925 GHz -> peaking 8.2898 dB).
This also explains session 8's unexplained 8.19-vs-8.29 dB discrepancy.

**P2 — SKY130 INSTALLED AND SIMULATING. G29 is cleared.**
Inside timebox. `volare` 0.20.6 into WSL2 Ubuntu (`pip install --user
--break-system-packages`; `python3-venv` is absent and needs sudo, so the venv
route is a dead end). `volare enable --pdk sky130 c6d73a35...` pulled the
open_pdks-generated tree, which **does** contain
`libs.tech/ngspice/sky130.lib.spice` with real `.model` cards and working
`.lib tt|ss|ff|sf|fs` sections — all five S9 process corners. Copied to
`C:\Users\DELL\sky130A` (libs.tech/ngspice + libs.ref/sky130_fd_pr/spice,
~52 MB, 856 files) so the existing Windows conda ngspice drives it.

`nebula/device/spice/g1_sky130_volare.cir` runs `.op` + `.ac` + `.noise`
against it cleanly. **The raw-repo blockers are gone**: no "13 formal but 0
actual params", real `.model` cards. `g1_sky130.cir` (raw-repo version) is
superseded.

Two things cost time and are now gotchas. **G31: sky130 instance W/L are plain
numbers in MICRONS**, because the lib sets `option scale=1e-6` and the subckts
default to `l=1 w=1`. Writing `W=5u` gives 5 picometres, falls outside all 180
model bins, and aborts with the *misleading* "could not find a valid
modelname". The generic-BSIM4 netlists in the same directory use SI metres —
do not copy W/L between the two families.

**The SKY130 run independently re-confirms the SS6 finding on a completely
different device model**, which is the strongest form this result has taken:

                            generic BSIM4        real SKY130
        simulated A_dc        -14.57 dB           -13.54 dB
        SS6 verbatim          -12.24 dB           -11.80 dB
          error                 2.33 dB             1.74 dB   BOTH FAIL (tol 1 dB)
        SS6 + gmbs            -14.29 dB           -13.41 dB
          error                 0.28 dB             0.13 dB   both pass
        gmbs/gm                  0.327               0.396

**gmbs/gm is WORSE on the real PDK (0.40) than on the generic cards (0.33)**,
so the correction matters more with the PDK, not less. Both fixtures are
pinned by tests.

**Caveat, stated plainly: that netlist is a toolchain smoke test, not a design
point.** VDD is 1.8 V (nfet_01v8), ideal tail sinks pull the sources to
-0.68 V, and Vds = 1.98 V exceeds the rail. Its AC numbers (peaking 3.82 dB at
**724 MHz**, noise 0.60 mVrms) show a stage that peaks *below* S3's
1.25-2.5 GHz window and is **0.99 dB below its own DC gain at Nyquist**. Not a
result about a design; a result about the toolchain.

That last point is worth keeping: **peaking and in-band boost are different
numbers.** A stage can show 3.8 dB of peaking, inside S3's band, and still
deliver less than its DC gain where the data lives. `DerivedAc` exposes
`peaking_db` and `nyquist_boost_db` separately and a test pins the distinction.

**P3 — NRZ retarget, the three named fixes only.**
New `python_models/modulation.py`: a `Modulation` object carrying
`(levels, thresholds, bits_per_symbol)` with **every** other quantity derived
(`mean_square`, `symbol_probability`, `max_level`, `rms`, `level_spacing`,
`is_adjacent`). PAM-4's `mean_square` comes out at exactly the 5.0 that was
hard-coded, because it is E[a^2] over {+/-1,+/-3} — no chosen numbers, per
SS8 rule 6. `PAM4` is the default everywhere, which is what kept the existing
suite green without editing it.

1. **`crossing_jitter_ui`'s `sqrt(5.0 * ...)` is now `sqrt(mod.mean_square *
   ...)`.** Highest priority because it is a *wrong result*, not a slow one:
   the PAM-4 factor on an NRZ link overestimates jitter by exactly
   sqrt(5) = 2.2361x and would have declared a lockable CDR infeasible. Pinned
   by a test asserting the PAM-4/NRZ ratio is sqrt(5) to 1e-12, plus a
   regression test reproducing the old literal for the PAM-4 path.
2. **`CTLE.from_peaking`'s pole arguments are now REQUIRED.** They defaulted to
   28e9/56e9 — absolute 112G frequencies — so `from_peaking(6.0)` silently
   built a 5 Gbps equaliser with poles eleven times above the band. There is
   no correct default because the right poles depend on fbaud, so there is now
   no default. A test shows the trapped construction delivers <1 dB of in-band
   boost where correct poles give >3 dB. Two existing tests now pass poles
   explicitly; what they assert is unchanged.
3. **`adc_vref = 4.0`: established MOOT, and left alone.** S2's topology is
   CTLE + slicer + 1-tap DFE — **there is no ADC in it.** `nebula/link/`
   imports neither `link_sim` nor `adc_model`, and
   `LinkConfig.to_link_sim_config()` still raises. So `adc_vref` cannot reach
   a Nebula number. Three tests pin that conclusion so it stays checkable
   rather than being a claim in a document.

**The staging boundary is enforced, not just documented.** `StatisticalEye`
now takes `modulation="pam4"` and **refuses** to run `ber_at_phase`,
`analyse` or `clip_probability` in NRZ mode, because audit groups A-E are
still four-level. Running anyway would report a BER 0.75x the truth —
optimistic, finite and plausible. A loud `NotImplementedError` costs one
traceback; the silent factor costs a wrong number in a report.

**ONE MEASURED RESULT CONTRADICTS THE RECORDED COST TABLE, and it is the most
consequential finding of this session (G34).** The 175x fidelity-tier spread
was measured on **generic BSIM4 cards with no PDK library**. On SKY130 the
same netlist takes **16.5 s instead of 0.02 s** — a ~700x per-invocation
penalty that is almost entirely *library parsing*, not analysis. If the device
layer spawns one ngspice process per evaluation, 1e5 PPO steps at TT alone is
**~19 days**, against the 1.8 hours the table records.

It amortises completely when the process is reused: 20 points in one process
took 16.57 s, **200 points took 16.89 s** (~0.002 s marginal each). So
**holding ngspice processes open and using `alter` between sizing points is
not an optimisation — it is the difference between feasible and infeasible**,
and it revises G23 (batch mode still right; respawning per evaluation not).

Load-bearing caveat, unproven: the probe altered resistors only. The input
pair is a **subckt** instance, so changing its W/L/nf may need `altermod` or
re-instantiation — and if that forces a re-parse, the amortisation does not
cover the parameters the policy moves most. **Measure this before the device
layer is designed around it.**

**Nothing else in SS2 was contradicted.** Everything else measured this
session agreed with it or sharpened it. The two other numbers worth carrying
forward are gmbs/gm = **0.40 on the real PDK** (up from 0.33) and the `k2`
model-card drift (G32), which was a genuine internal inconsistency rather than
a wrong published figure.

**Not started, by instruction:** S-parameter channel, any RL training, corner
verification. G2 remains unmet.

### 2026-08-04 — Session 9b (the parse-cost question settled; it changes the device layer)

**Tests: 383 -> 405** (+22, `nebula/tests/test_trimmed_lib.py`; 2 more behind
`-m slow`). Follow-up to G34, which was the session's most consequential
finding and was left with an unproven caveat. The caveat turned out to be
worse than stated, and the fix turned out to be somewhere else entirely.

**`alter` is not the answer — it is silently WRONG (G35).** Fresh-parse ground
truth vs `alter`, on the input pair's W:

    W=4.5 um, SAME bin [3,5]      gm 2.358e-3 vs 2.272e-3    -3.6%
    W=6.0 um, crosses to [5,7]    gm 3.175e-3 vs 2.407e-3   -24.2%
    W=9.0 um, crosses to [7,100]  gm 3.6e-3   vs NaN        broken

The **same-bin** failure is what kills it: this is not a bin-resolution
problem that could be avoided by staying inside a bin. The `sky130_fd_pr`
subckt derives `ad/as/pd/ps/nrd/nrs` from W by `.param` expression at PARSE
time, so `alter` moves W and leaves every geometry-derived parasitic stale.
And it fails in the §8-rule-10 shape: ngspice printed
`Error: no model available for w=...` while `print @m1[gm]` kept returning the
**stale** value. An RL loop sweeping W would have read the same gm for every W
and never known. Two side-traps recorded: `alter` applies `scale` a second
time (so it takes plain numbers), and the `alter xm1 w=` form does not work —
only the hierarchical `@m.xm1.m<subckt>[w]`.

**Trimming the library is the answer, and it is a bigger win (G36).** The S2
CTLE instantiates ONE device type; the full library parses 30 families per
corner. `nebula/device/spice/sky130_nfet_only.lib.spice` (all five process
corners) takes an invocation from **16-35 s, variable, to 0.42 s, tight** —
~40-80x — and is **bit-identical**: verified `rel=0, abs=0` on gm, gmbs, vth,
id, g_dc, g_pk and inoise_total across 5 corners x 4 (W,L) points straddling
three W bins and two L bins. Removing the *variability* matters as much as the
mean, because a variable per-point cost makes a fidelity schedule
non-deterministic. One trap: a trimmed library must declare
`.option scale=1.0u` itself — the full one sets it in `all.spice`.

**Revised cost at 1e5 PPO steps, TT only:**

    generic BSIM4, no PDK (the original table)        1.8 h
    full SKY130 lib, one process per evaluation      ~19 days
    TRIMMED SKY130 lib, one process per evaluation   ~11.7 h

So a PDK-backed inner loop is **~6.5x the no-PDK baseline, not 250x**, and
needs no process-reuse machinery. `alter` stays available for the ideal R/C/I
elements (not subckts) if that 6.5x ever needs attacking.

**Two smaller items closed.**
- **New CLAUDEwa.md §8 rule 9 — model cards and device parameters have exactly
  ONE definition in the repo.** Netlists and runners reference it; neither
  redeclares it. A human reading any netlist must see the values that produced
  the published numbers. (The old rule 9 became rule 10.) This is the standing
  rule for the `k2` class of bug found in session 9a.
- **`rs` bound tightened 50-2500 -> 100-2000**, i.e. exactly the range that
  was deliberately swept. Given the choice between extending the evidence and
  tightening the bound, the bound moved.

### 2026-08-04 — Session 9c (hand-sizing at the terminal; the G1 bias was wrong)

**Tests: 405 -> 407** (+2, `nebula/tests/test_noise_units.py`). Human-led
hand-sizing session at the ngspice prompt; these numbers come from twenty-odd
AC runs done deliberately, not from a script.

**1. `inoise_total` is RMS VOLTS, not V^2 — verified, and now pinned.**
Settled against a closed-form case (one resistor, 4kTR*BW): ngspice returns
**4.069e-06** for 1 kohm over 1 Hz-1 MHz, and sqrt(4kTR*BW) = **4.071e-06 V**.
Match to 0.05%. So every noise figure in this project is already in volts and
must NOT be square-rooted. Had the squared reading been right, the G1 point's
0.275 mV would have been 16.6 mV and **S5 would have flipped from "free at
90.7%" to failing by ~11x**. `test_noise_units.py` pins it, including a test
that states what the wrong reading would look like.

**2. THE G1 BIAS POINT IS BADLY MIS-BIASED. gm/I_D = 1.7 V^-1.**
A well-biased MOSFET runs at 8-15. At W=5 nf=4 and 1.5 mA the device needs
vgs = 1.34 V, so with the gates at VCM = 0.9 V the sources sit at
**v(s1) = -0.44 V** — below ground. Ideal tail sinks permit that; a real tail
transistor cannot, so the operating point is physically unbuildable even
though it simulates cleanly. Measured sweep at IT = 1.5 mA, VCM = 0.9:

        W    nf   gm(mS)   gm/ID   v(s1)
        5     4    2.577    1.72   -0.439
        10    4    4.822    3.21   -0.184
        20    4    8.735    5.82   -0.042
        40    4   12.992    8.66   +0.050
        80    4   19.850   13.23   +0.089

Width alone does not fix v(s1); VCM must rise too (it is a placeholder, not a
constraint — a real RX AC-couples and biases the gates itself). **Corrected
reference: W=40 nf=4, IT=1.5 mA, VCM=1.25 V -> gm = 12.62 mS, gm/I_D = 8.42,
v(s1) = +0.343 V, vds-vdsat = 0.74 V, noise 0.275 mV.**

**3. Consequences, and they move the design point.**
- **DC gain went from -6.4 dB to +5.1 dB.** The stage no longer attenuates.
  Session 7's conclusion that "a CTLE at PCIe levels has to attenuate at DC"
  was drawn on a device with gm/I_D = 1.7 and does not survive the bias fix.
- **The asymptotic peaking formula is now badly optimistic.** At Rs=200,
  20*log10(k) = 7.66 dB but the REALISED peaking is **0.00 dB** — the entire
  boost is eaten by the load pole. Do not size Rs from `20*log10(k)`.
- **f_z must sit BELOW f_p2 or there is no peak at all.** Measured at Rs=200,
  Cs=400f: RL=400/CL=100f (f_p2 = 3.98 GHz) gives 1.06 dB at 2.96 GHz;
  CL=200f (f_p2 = 1.99 GHz) gives **no peak whatsoever**. Lowering f_p2 does
  not move the peak down, it EXTINGUISHES it. The ordering f_z < f_p2 is a
  hard structural constraint, not a tuning preference.
- **Rs sets how much, Cs sets where — cleanly separated.** Sweeping Cs at
  fixed Rs=200 left `gdc` at 5.05 dB for every value while the peak moved
  7.96 -> 0.50 GHz. That separation is the single most useful fact for the
  presentation.

**4. Twelve configurations now MEET S3** (3-12 dB peaking, f_pk in
1.25-2.5 GHz), spanning 4.63-10.01 dB at 1.32-2.30 GHz — e.g. Rs=200,
Cs=1.6p, RL=400, CL=100f -> 4.63 dB at 1.95 GHz.

**5. But compression is now the binding problem, exactly as predicted.**
Available differential swing is 2*IT*RL = 1.2 Vpp. At the LOW-loss end of the
channel sweep (3 dB) a 0.8 Vpp PCIe TX needs **1465-1944 mVpp** at the output
across all twelve S3-meeting points — every one compresses. At 9 dB loss they
are all fine (734-974 mV). This reproduces session 7's "compression binds
hardest at LOW channel loss" on a properly biased device, and it is now worse
because the gain is higher.

**The lever is NOT RL.** Compression ratio is
`TX_pp*|H_pk| / (2*IT*RL)`, and `|H_pk| ~ gm*RL/k`, so **RL very nearly
cancels** — measured, dropping RL 400->300 made it slightly *worse*
(ratio 1.44 -> 1.63). Raising Rs does not help either (1.44 -> 1.48 at
Rs=400), because lower DC gain buys back exactly the peaking it adds. What is
left is **I_tail up, or gm/I_D down**. So there is a real tension: high gm/I_D
is efficient for noise and power but *directly worsens compression headroom*
at PCIe input levels. That tension, not noise, is the actual design problem.

**Consequence to act on:** the parameter BOUNDS in `common/params.py` were
derived from the mis-biased 1.2 V generic-BSIM4 design and the 5.3% S3 yield
was measured inside them. Both need re-deriving once the bias is settled. Do
not quote 5.3% as a corner-robust figure without re-running it.

**S3's ambiguity is now stated in the contract, not resolved silently.**
"3-12 dB peaking, peak in 1.25-2.5 GHz" admits (a) peak-to-DC ratio anywhere
and (b) boost at Nyquist. Our SKY130 smoke test is the counterexample that
makes the difference concrete: **+3.82 dB peaking — a pass under (a) — with
the peak at 724 MHz and the response 0.99 dB BELOW its own DC gain at
2.5 GHz.** We require and report BOTH. If a judge reads S3 the other way, we
have shown we considered it rather than picking the convenient reading.

### 2026-08-04 — Session 9d (bounds re-derived; the central argument falsified)

**Tests: 407 -> 430** (+23, `nebula/tests/test_sky130_runner.py`; 3 need the
simulator and skip cleanly). Full write-up: `nebula/BOUNDS_REDERIVATION.md`.
This session closed the START HERE item and, in doing so, overturned four
prior conclusions. Ordered by how much they matter.

**1. THE COUPLED-CONSTRAINT ARGUMENT IS FALSIFIED (G40).** The project's
designated "strongest single sentence for the abstract" was: S3 couples gm,
Rs, Cs, RL and CL, no axis-aligned box can exploit a coupled constraint, hence
random search lands only 5.3% of the time. A bare percentage cannot support
that, because it depends entirely on the box width. The box-independent form
decomposes S3 into A (peaking 3-12 dB) and B (f_peak 1.25-2.5 GHz) and
compares the joint against the product of the marginals. 2000 Latin-hypercube
samples per box, three widths:

        width   P(A)     P(B)     P(A)P(B)   P(A and B)   coupling
        x0.6    69.40%   24.95%    17.32%      17.25%      1.00x
        x1.0    48.47%   16.03%     7.77%       8.73%      0.89x
        x1.5    35.04%    8.01%     2.81%       3.13%      0.90x

and, conditioned on a peak existing at all (the shared no-peak region
otherwise associates A and B for an unrelated reason), **1.00 / 1.04 / 1.06x**.
The raw yield swings 5.5x across box widths; the coupling factor does not
move. **The two conditions are independent.** S3's yield is low because one
marginal is low — f_peak lands in-window 16% of the time — not because
anything is coupled. Four candidate replacement arguments are listed in
BOUNDS_REDERIVATION §4; the recommendation is **tunability** (S3 wants any
point in 3-12 dB on demand, which random search cannot deliver at all) with
8.73% quoted purely as a baseline. **Human decision, and the abstract is due
6 Aug.**

**2. The available swing was understated ~2x, and by the wrong mechanism
(G37).** `2*I*RL` is a PEAK; the peak-to-peak ceiling is `4*I*RL`. Measured at
the corrected point by DC transfer curve: **1427 mVpp at 1 dB compression**,
2161 mVpp saturation-limited, 2281 mVpp steering, against the 1200 mVpp
session 9c compared everything to. And at the 1 dB point the pair is still
saturated with vds 1.29 V against vdsat 0.079 V — so the limit is **current
steering, not headroom**, which contradicts 9c's diagnosis and predicts (
correctly, see 4) that more supply voltage will not help.

**3. The compression verdict was partly a fixed-boost artifact.** S3's peaking
is tunable and S2's knobs are Rs/Cs, but 9c evaluated twelve FIXED designs
against all five loss points — nobody runs a tunable equaliser that way. With
the boost matched to each channel's tilt, compression goes from "11/11 at 3 dB
loss, up to 1.9x over" to **1.22x at 3 dB, 1.04x at 5 dB, clean at 7/9/12 dB**.
Real, but localised, and not the project-defining constraint. **Caveat that
dominates the whole question:** under `calibration.py` C3's long-run
convention the verdict flips to 11/11 compressing at EVERY loss point, because
`CHANNEL_DC_LOSS_DB` is a fixed 1.0 dB placeholder with no provenance. A
made-up constant currently decides this. Strongest case yet for a real .s4p.

**4. A 3.3 V device is rejected, on f_T not headroom (G39).**
`nfet_g5v0d10v5`'s minimum L is 1.0 um against 0.15 um. Best peaking achieved
**2.66 dB** — under S3's floor — and pushing RL for gain puts the peak at
0.398 GHz with the Nyquist boost at -5.14 dB. Swing improves only +12%,
exactly as 2's steering-limited finding predicts. Power 5.4 -> 9.9 mW.

**5. `nf` does not multiply width on SKY130 (G38).** W is the total; nf splits
it into fingers. gm moves +/-10%, non-monotonically, over nf = 1..32. Two
action-space dimensions are near-dead and non-monotonic, and `BOUNDS`'s
provenance string for `nf_in` is factually wrong for the PDK.

**6. The re-derived box and its yield.** Nine of the twelve §5.2 parameters,
each edge traced to a measurement, in
`nebula/experiments/s3_yield.py::PROPOSED_BOX`. `cl` is ~6x tighter than the
1.2 V box (400 fF already drives the Nyquist boost negative). Yield: 8.73% S3,
100% S5, 100% S6, 99.05% saturated, 0 non-convergences.
**`w_tail`/`l_tail`/`nf_tail` are deliberately absent** — the tail is still two
ideal current sinks, so no simulation in this project has ever contained a
tail transistor, and inventing ranges for it is what §8 rule 6 forbids.
**The box is NOT written into `params.py`** (rule 6); the old bounds now carry
a superseded banner naming their three known defects.

**Also checked and NOT a bug:** `.noise`'s input reference. Naming a
single-ended `vinp` (ac 0.5) versus a differential `Vid` (ac 1) looked like a
guaranteed 2x on every input-referred noise number; measured on the identical
circuit, both give inoise_total = 1.723594e-04. ngspice normalises by the
named source's AC magnitude. Recorded because "obviously a factor of two" is
how the last three units bugs here introduced themselves.

**Note for whoever commits this:** the working tree is NOT a git repository
(`git init` has not been run in this checkout), so the CLAUDE.md rule about
updating HANDOFF.md in the same commit could not be honoured mechanically.
HANDOFF.md is updated; the commit still needs making.
**RESOLVED in session 10a below** — this and every earlier session's work went
into the initial commit.

### 2026-08-04 — Session 10a (git init; the history starts clean of the PDFs)

**Tests: 430 before, 430 after** (`python -m pytest tests nebula/tests -q
-m "not slow"`, 73.9 s, 2 deselected). Nothing executable changed — this
session touched `.gitignore` and `HANDOFF.md` only.

Closes the note directly above, which had been open since session 9d: the rule
in CLAUDE.md that HANDOFF is updated *in the same commit* as any change had no
commit to be in.

**What was done.** `git init -b main`, a rewritten `.gitignore`, and one
initial commit of **102 files** under the global identity
`Jai Kaushik <jaikaushik-prog@users.noreply.github.com>` (G12 — the BITS
address attributes to the wrong GitHub account and has already forced one
history rewrite).

**The part that matters, and it is a one-time opportunity that was taken.**
G1 says the reference PDFs are copyrighted and that a public version of the
GitHub repo would have to strip them from **history**, because they are in that
repo's baseline commit — deleting the files later does not help. This checkout
had no history at all, so the PDFs could simply be excluded from commit #1.
They were, and it was **verified rather than assumed**:

        git diff --cached --name-only | grep -iE '\.(pdf|docx|doc|pptx)$'
        -> empty
        git status --ignored --porcelain | grep '^!!'
        -> all 10 reference documents listed as ignored

All ten (the two Shakiba wireline papers, Menin, Han/EECS-2019-143, both PAM4
notes, the CERN intro, the professor's `Part 11 FFE.pdf`, and the two `.docx`
files) are ignored. So **this tree's history is clean and needs no rewrite**;
the GitHub repo's is not and still does. They are now unrelated histories, and
G1 has been amended to say so, because "the repo has the PDFs in history" was
about to become half-true and half-false with no marker saying which half.

**`.gitignore` is organised by reason, not by extension**, because the reasons
are not interchangeable:

| section | why | if violated |
|---|---|---|
| reference library | copyright (G1) | cannot ever be made public |
| PDK | not ours to redistribute; 52 MB | licence + repo bloat |
| run artifacts | regenerable | noise in every diff |
| `__pycache__`, caches | regenerable | noise |

The PDK patterns (`sky130*/`, `libs.tech/`, `libs.ref/`, `*.pm3.spice`) match
**nothing today** — the install is out of tree at `C:\Users\DELL\sky130A`
(G33). They are there so that a copy dropped in-tree cannot be committed by
accident. That created the one trap in the file: `sky130*/` would also have
caught **our own** trimmed library, so
`!nebula/device/spice/sky130_nfet_only.lib.spice` is an explicit un-ignore. It
is 69 lines of `.include` pointers and `.option scale=1.0u`, redistributes no
model cards, and is what makes an ngspice invocation 0.42 s instead of 16-35 s
(G36) — losing it silently would have been expensive and would have looked
like a performance regression, not a missing file.

**Committed vs. not, for the `ams_rl_ppo` files sitting loose at repo root**
(CLAUDEwa §4.2's reference implementation, unpacked at top level rather than
into `resources/`): the **source** is tracked (`train.py`, `gym_env.py`,
`discriminator.py`, `circuits.py`, `evaluate.py`, `reward.py`,
`component_importance.py`, `reproduce_tables.py`, `llm_baseline.py`, the two
YAMLs) because §4.2 calls it plumbing to port; the **checkpoints and training
logs** (`*.pt`, `*.npz`, `policy*.zip`, `train_summary*.json` — 20-odd files,
several byte-identical duplicates with `(15)`-style suffixes) are ignored,
because they are the artifacts behind the degenerate results table §4.2 says
explicitly not to anchor on. Nothing was deleted; they are still on disk.

**New gotcha G41** (the two verification commands, the reason-based structure,
and the `!`-rule trap). **G1 amended.** **§10 corrected** — it claimed a remote
`origin` that this checkout does not have.

**Not done, deliberately:** no remote, no push. Pointing this history at the
existing GitHub repo is a real choice between a new remote and a rewrite of the
old one, and it is a human's (G1 as amended).

### 2026-08-04 — Session 10b (`cl` sensitivity: a search dimension worth less than a constant)

> **CORRECTION, added by session 10c — read before quoting anything below.**
> Every *coupling* number in this entry was measured with a peak detector that
> counted `meas ac MAX` sweep-edge maxima as genuine peaks (G44), inflating the
> has-peak population by up to 42%. Session 10c fixed it and re-ran all five
> points. **What changes:** the raw coupling reads 1.05 -> 0.68 (not
> 1.00 -> 0.68); the conditional reads 0.97-1.06 with all five intervals
> covering 1.00; the "real ~10% adverse effect at 100 fF" reported below is
> **RETRACTED** — 1.10x [1.02, 1.20] became 1.06x [0.99, 1.15]; and the
> "lockstep with the falling peak count" explanation is **wrong**, because the
> peak count is hump-shaped post-fix. **What does NOT change:** the S3 yields
> (166/213/256/226/180 vs 165/213/256/228/180) and therefore every conclusion
> in G42 about `cl` being a bad search dimension. Corrected numbers are in
> `nebula/CL_SENSITIVITY.md` sec 9 and in G43/G44 as amended.

**Tests: 430 -> 444** (+14, all in `nebula/tests/test_sky130_runner.py`;
105.9 s, 2 deselected). Full write-up: `nebula/CL_SENSITIVITY.md`.
**`common/params.py` is untouched** — this is a measurement and a proposal,
and rule 6 reserves the bound change for a human.

**What was added.** `--cl-fixed FARADS` in `experiments/s3_yield.py`, plus the
uncertainty machinery the conclusions need.

The pin **overwrites the `cl` coordinate of the same seeded LHS design** rather
than re-sampling in eight dimensions. That is the load-bearing design choice:
the other eight coordinates are identical sample-by-sample across all runs, so
a yield difference is attributable to `cl` and nothing else. A free consistency
check falls out — `headroom_ok_1v8()` never reads `cl`, so the free-rejection
count must be identical across runs, and it is (110 rejected / 1890 simulated,
every time).

**Result 1 — pinning `cl` BEATS searching it (G42).** 2000 samples per point:

        cl        50f     100f     150f     250f     400f    sampled 10-500f
        S3      8.73%   11.27%   13.54%   12.06%    9.52%          8.73%
                                  ^^^ max, and disjoint CIs vs both ends

8.73% [7.54, 10.09] -> 13.54% [12.08, 15.16]. The whole bound is worse than a
single value inside it. 150 fF is a real interior maximum, **but is not
separable from 250 fF** at this n — the supportable claim is "the optimum is in
150-250 fF", not "the optimum is 150 fF".

Mechanism, visible in the marginals: A (peaking 3-12 dB) falls monotonically
52.65 -> 33.54% as the load pole eats peaking, while B (f_peak in window) rises
16.61 -> 24.02% then falls back to 19.21%. Extra `cl` first *relocates* the
peak into the S3 window and then *extinguishes* it — session 9c's finding,
re-measured across 9450 designs instead of two. The count of designs with any
interior peak falls monotonically 1673 -> 1168.

**Result 2 — the raw coupling factor is the no-peak fraction in disguise
(G43).** Across the same sweep the raw factor moves 1.00 -> 0.68 (32%) while
the conditional-on-a-peak factor sits flat at 1.01-1.10, in lockstep with the
falling peak count. This is the strongest form G40 has taken: not an argument
that the conditional version is better, but a five-point trend showing the raw
one measuring something else entirely. Honest wrinkle recorded rather than
smoothed: at `cl` = 100 fF the conditional interval [1.02, 1.20] does exclude
1.0, so there is a real ~10% adverse effect there — an order of magnitude too
small to be the retracted sentence's mechanism, and G40 stands.

**Result 3, and it is the uncomfortable one — this makes G3 HARDER.** RL must
beat random search. A better box means a better baseline: ~11 samples per hit
becomes ~7. Recorded in G42 as a decision to take deliberately rather than a
free win.

**An analytic prediction was made in advance and FAILED, which is why it is
written down.** The obvious model — peak of a 1-zero/2-pole response sits near
f_p2 — predicts *zero* S3 yield at `cl` = 50 fF, because no `rl` in 50-800 ohm
puts f_p2 inside 1.25-2.5 GHz (it would need 1273-2547). Measured: 8.73%. One
probed sample has f_p2 = 55.3 GHz and peaks at 9.55 GHz. **f_peak is set by
the zero interacting with both poles, not by the load pole alone** — the first
evidence that the analytic pre-screen in the next work item will not be a
one-liner.

**A near-miss worth recording.** `cl` = 50 fF returned 165/1890, the same
integer as the baseline, which is exactly what a silently-ignored CLI flag
looks like. It was tested rather than explained away: A moved 916 -> 995 and
B moved 303 -> 314, and a direct probe showed `f_pk` moving 9.55 -> 6.61 ->
5.50 -> 3.16 GHz across cl = 50/100/150/500 fF on one sample. Genuine
coincidence. (The identical `n_simulated` is not a coincidence — see above.)

**New: uncertainty on every number.** `wilson_ci()` (two-sided Wilson score —
stays in [0,1] and gives a real upper bound at zero successes, which the
45-corner sweep will need) and `bootstrap_coupling_ci()` (percentile bootstrap
over whole rows, the only honest option for a ratio of three correlated
proportions; measured resolution ~+/-10% at n=2000). Wilson is deliberately
NOT imported from `python_models/pam4_chain.py` — nebula is independent by
design — and a test holds the two implementations to each other so they cannot
drift.

**New gotchas G42** (a dimension worth less than a constant; and the G3
tension), **G43** (raw coupling = no-peak fraction), **G44** (`meas ac MAX`
reports the 50 GHz sweep edge as a peak, so `has_peak` over-counts; found
while probing, not yet fixed because fixing it moves a published statistic).

### 2026-08-05 — Session 10d (the corner-robust yield: a tax, not a constraint)

**Tests: 444 -> 481** (+37; `nebula/tests/test_s9_yield.py` is 29 of them,
the rest landed in `test_sky130_runner.py` alongside the runner work).
`python -m pytest tests nebula/tests -q -m "not slow"`, split 92 + 389,
2 deselected. Full write-up: `nebula/S9_YIELD.md`. **`common/params.py` is
untouched** — rule 6 again; this is a measurement, not a bound change.

*(Session 10c has no entry of its own: its work was the G44 peak-detector fix,
recorded as the correction block at the head of the 10b entry and in G43/G44.)*

**What this closes.** HANDOFF §8's third follow-on and `BOUNDS_REDERIVATION.md`
§7 item 3: every yield this project had published was TT/27 C, while S9
requires every spec to hold at every corner. **20 205 SPICE runs, 47 min.**

**The number, three ways, on the SAME 1890 designs:**

        TT / 1.00 / 27 C          255/1890 = 13.49%
        all 3 screen corners      155/1890 =  8.20%  [7.05, 9.52]
        all 45 corners            153/1890 =  8.10%  [6.95, 9.41]

        cross-tab:  TT pass + corners pass   155
                    TT pass + corners FAIL   100   <- 39.2% of the winners
                    TT fail + corners pass     0

**39.2% of designs that meet every spec at nominal fail at a corner.** The
defensible sentence is *"an optimiser scored at nominal is wrong about two of
every five designs it calls a success"*. It is a **tax on the baseline**, not
a coupled constraint — S9 was listed in BOUNDS_REDERIVATION §4 as the cheapest
route to replacing the argument G40 retired, and **it did not deliver one**.
Recorded plainly because the temptation to dress 13.49 -> 8.10 up as coupling
is exactly the mistake G40 exists to prevent.

**The bottom-right zero is a real check, not a tautology.** tt/1.00/27 C is NOT
one of the three screen corners, so "no design fails nominal yet passes all
three extremes" had to be measured.

**Consistency with 10b.** CL_SENSITIVITY reports 13.54% (256/1890) at
cl = 150 fF counting S3 alone; this run additionally requires Nyquist boost,
S5, S6 and saturation, and gets 255. Four extra conditions remove exactly one
design — outside S3, nothing in this box binds at nominal.

**Three reusable results, which are worth more than the yield:**

1. **G47 — three corners are worth 98.7% of forty-five.** The screen corners
   are a SUBSET of the 45, so the screen has **no false negatives by
   construction** and its yield is a hard upper bound; the only error possible
   is a false positive, and it made two out of 155. Stage 2 spent **64% of the
   wall clock to reject two designs**. Budget the RL reward at 3-5 corners,
   full sweep in a verification tier.
2. **G46 — the worst corner is FAST-hot, not slow-hot.** Every promotion-stage
   failure lands at 125 C on ff/sf/tt and **none on ss at any rail**. A faster
   device has higher gm, which pushes the peak out through S3's 2.5 GHz top
   edge. S3 is a two-sided spec and its two edges sit on opposite sides of the
   process axis, so "the worst corner" is not a well-formed idea for it. The
   screen had been built on the slow-hot folklore.
3. **G48 — 11 cores buy 3.2x, not 11x.** 318 / 179 / 150 / 106 / 100 ms per
   task at 1 / 2 / 4 / 8 / 11 workers. Efficiency collapses after 2 and the
   curve is flat past 8. **~100 ms per (design, corner) is the number to
   budget** — dividing G36's 0.42 s by the core count is off by 2.6x, and
   quoting the serial figure is off by 3.2x. Both have appeared in estimates
   here.

**What binds, which is the headline the script was written to produce.** Of
1890 designs at each screen corner, first failure by normalised shortfall
(CLAUDEwa §9):

        S3_f_peak      800 / 799 / 786   (42%)   median -1.7 to -2.1 GHz
        S3_peaking     686 / 719 / 688   (37%)   median -3.000 dB
        S3_nyq_boost   162 / 126 / 144   ( 8%)   median about -1.0 dB
        headroom        13 /   - /  13
        saturation       5 /   1 /   3
        S6_power         - /   2 /   -

The median S3_peaking failure misses by **exactly -3.000 dB, i.e. its peaking
is 0.000 dB** — a flat stage, not a mis-tuned one. Same population 9d found
behind the low P(B) marginal, seen from the other side. **S5 never ranks as
the binding constraint anywhere**, and S6 does so twice in 5670 runs: what
binds in this box is bandwidth PLACEMENT, and it is not close.

**Health, and why it is printed.** 0 hard simulator failures, 0 retries, 26
(design, corner) headroom rejections (13 at each 0.95 V slow corner), and
**0 screen/promotion mismatches across 465 repeated (design, corner) pairs** —
the free determinism check that falls out of the screen corners being members
of the 45. A mismatch would have invalidated everything downstream (G45).

**THE CAVEAT THAT OUTRANKS ALL OF IT: the tail is still two ideal current
sinks.** An ideal sink does not lose current at SS/125 C, does not gain it at
FF/0 C, and does not fall out of saturation at 0.95 VDD. Every corner spread
above is therefore an **understatement** and 8.10% is an **optimistic bound** —
it is the corner spread attributable to the input pair alone. **This is why
§8 now lists the tail transistor as the top open item**, above everything else
in the Nebula backlog: it is the one experiment that could still turn corner
robustness into a real constraint, and re-running it costs nothing new
(`python -m nebula.experiments.s9_yield --n 2000`, unchanged).

**Added this session:** `nebula/experiments/s9_yield.py` (the two-stage sweep,
owning the three assumptions and printing them in every run header),
`nebula/tests/test_s9_yield.py` (29 tests, all simulator-free — the arithmetic
and the assumption-plumbing, which is where a wrong answer would be invisible),
and `screen_augmentation()`, which maps each corner to the false positives it
would have caught so the screen can be re-cut from data rather than intuition.
Its default `--out` now resolves next to the script, not to the cwd: a 28-min
run must not scatter its only record wherever it was launched from.

### 2026-08-05 — Session 11 (where the robust designs live: in the window, not in the box)

**Tests: 481 -> 528** (+47, all in `nebula/tests/test_robust_geometry.py`;
`python -m pytest tests nebula/tests -q -m "not slow"`, split 92 + 436,
2 deselected). Full write-up: `nebula/ROBUST_GEOMETRY.md`.
**`common/params.py` untouched** — rule 6; §7 of that file is a proposal about
the SEARCH, not a bound change.

**The task premise did not hold, and that is the first result.** This was
scoped as "no new SPICE — it uses data you already have". Session 10d's
20 205-run, 47-minute sweep wrote `s9_yield_results.json`, which is
`.gitignore` line 67 under "run artifacts - regenerable". It was never
committed and is not on disk. It would not have been enough anyway: it stored
counts and design indices, not the per-design f_peak/peaking values this
analysis plots. **New gotcha G49.** Recovery: the LHS is seeded, so the 1890
designs regenerate for free; re-simulating them at TT plus the 3 screen corners
cost **7560 runs / 23 min**. The per-design table is now **committed** as
`nebula/experiments/robust_geometry_data.csv`, so the whole analysis is
simulator-free from here.

**10d's counts reproduced EXACTLY**, and this is asserted rather than assumed
(`check_reproduction()`; `main()` refuses to draw a figure on a mismatch):
1890 designs, 255 TT winners, 155 corner-robust, 100 corner-fragile. That is a
stronger statement than it looks — box, seed, `cl` pin, headroom filter, corner
plumbing, spec checker and peak detector all still produce, design for design,
what they produced in 10d.

**The hypothesis was HALF right, and the wrong half is the more useful half.**
- **FALSIFIED: "robust designs are interior in the box".** All eight sampled
  dimensions are nulls after BH correction, and the two purpose-built
  interiority statistics are the least significant rows in the table
  (q = 0.98). Corners do not move a design's parameters, they move its
  RESPONSE — so a design is fragile when its response starts near a SPEC edge,
  and a response can be near a spec edge from anywhere in the box.
- **CONFIRMED, overwhelmingly: robustness needs f_peak centred in the WINDOW.**
  Median margin 0.325 vs 0.126 octaves, p = 2.8e-12.
- **NOT PREDICTED, and it is the session's own finding: the same holds on S3's
  OTHER axis.** Peaking margin 2.70 vs 0.86 dB, p = 3.2e-11.

**The methodological point worth carrying forward.** Raw `f_peak` and raw
`peaking` carry NO information about corner robustness (medians identical to
four figures; q = 0.81 both). Folded onto distance-to-nearer-edge, the same
numbers separate the groups at 12 sigma. **A two-sided spec makes its own raw
coordinate uninformative**: designs failing at the top edge and at the bottom
edge sit on opposite sides of any median and cancel. Same family as G40 and
G43 — ask the question in the coordinate the SPEC is written in, not the one
the simulator reports.

**The deliverable number: a joint filter, and it is free.** f_peak margin
>= 0.133 oct AND peaking margin >= 1.0 dB gives **92.1% [86.5, 95.6]
corner-robust against a 60.8% base rate**, keeping 140 of 255 designs. Either
condition alone reaches only ~75%, so they guard two independent failure
routes. Both come out of an AC run the evaluator already performs. Proposed as
a warm-start prior and as the S3 reward shape (fold both axes); §7 of the
write-up, for a human to accept or reject.

**G46 partly corrected.** Designs below the window centre die at SS 4.5x more
often than at FF (45 vs 10) — as predicted. Designs ABOVE the centre die about
EQUALLY at both (29 vs 27), which the clean two-mechanism story does not
predict and which an earlier draft of this entry mis-stated as "predominantly
FF". Mechanism: **SS has two ways to kill a design and FF has one** — lower gm
drops f_peak (killing the low side) AND drops peaking toward the 3 dB floor
(killing anything with little peaking margin, at any frequency). SS's 69
failures split 40/26 across those routes; FF's split 19/19. No contradiction
with G46, which was about the PROMOTION stage (the screen's blind spot is
fast-hot) rather than about which corner kills most (`ss/0.95/125`).

**Resolution limit found and pinned.** `meas ac MAX` returns a grid SAMPLE and
the netlist sweeps `ac dec 50`, so f_peak is quantised at log2(10)/50 =
**0.0664 octaves** and the one-octave S3 window holds exactly **15 distinct
f_peak values**. That is why the threshold table has duplicate rows and the
margin histogram has empty bins. Any margin quoted finer than ~0.07 octaves is
quoting the sweep setup.

**Added this session:** `nebula/experiments/robust_geometry.py` (population
reproduction + collection + statistics + four figures, with the reproduction
GATE), `nebula/tests/test_robust_geometry.py` (47 tests, all simulator-free —
the Mann-Whitney implementation is held to `scipy.stats.mannwhitneyu` over
tie-heavy cases rather than to hand-copied numbers), the committed CSV, and
`nebula/figures/`. One additive change to `s9_yield.py`: `CornerResult` gained
a `measured` dict populated from scalars the evaluator already had in hand, so
the pass/fail LABEL and the coordinates plotted against it come from the same
evaluation (rule 9) at zero extra SPICE cost.

**Still an optimistic bound.** The tail is two ideal current sinks, so the
margins above are the margins needed against the input pair's spread alone.
The thresholds are also IN-SAMPLE; a fresh seed costs 23 min and has not been
run.

### 2026-08-05 — Session 11b (verification + the commit)

Housekeeping session; **no analysis changed and no number moved.** Task 1 was
complete on disk but uncommitted and unverified, so this session verified it
and landed it.

**Verified before committing, all four green:**
- **Suite: 528 passed, 2 deselected, 98 s** (`python -m pytest tests
  nebula/tests -q -m "not slow"`, split 92 + 436) — the count §6 already
  claimed, now measured. Re-run after the commit: **528, 95 s.** Note the
  runtime against §6's warning — 98 s here versus the 21.5 min the same suite
  took in session 11 under an 11-worker ngspice pool. Contention, not a hang.
- **Gotcha count 49, no duplicates**, by the §9 splice check — i.e. the
  truncation `df2f7d4` caused is genuinely repaired, not just papered over.
- **`ROBUST_GEOMETRY.md` regenerates from the committed CSV**, with no
  simulator, including the reproduction gate (1890 / 255 / 155 / 100). Every
  number in the write-up was re-derived, including the ones the default report
  does not print: the t = 0.066 row (220 kept, 153 robust, 69.5%), 33-vs-2 and
  51-vs-12 within one and two grid steps of a window edge, 0-vs-37 within
  0.5 dB of a peaking edge, and the 60.9% / 60.7% symmetry about the centre.
- **G41's staging check clean** — no PDF or DOCX in the index.

**The commit (`de874db`) is wider than session 11.** Sessions **10c** (the G44
peak-detector fix in `sky130_runner.py` + `s3_yield.py`) and **10d**
(`s9_yield.py`, `S9_YIELD.md`, `test_s9_yield.py`, and `run_point(temp_c=)`)
were on disk but had never been committed — `4a286a8` was 10b. They are in it,
named in the message, and their absence from history was itself a small version
of G49.

**`PCI.2/` is now gitignored** (owner's call, asked before acting): competition
material from the organisers — two handouts and `nebula_ctle_rl_1.zip`, a
reference PPO+CTLE implementation with a trained agent and a PVT report. Not
ours to redistribute. It stays on disk and is worth reading before the RL work;
CLAUDEwa §4.2's "do not anchor on the reference implementation's numbers"
applies to it exactly as it does to `ams_rl_ppo`.

**Deleted `nebula/SESSION_11_HANDOFF.md`** — session-11 scaffolding that said
to delete itself once Task 1 was committed. Nothing else referenced it.

**Task 2 (`cl` as a robustness axis) has NOT been started**, by instruction: it
needs a pre-registered prediction committed to `nebula/PREDICTIONS.md` *before*
the experiment runs, and the owner reviews between tasks.

### 2026-08-06 — Session 12a (`cl` becomes a derived range, not a chosen constant)

**Tests: 528 -> 592** (+64: `nebula/tests/test_cap_probe.py` 36,
`nebula/tests/test_cl_range.py` 28). `python -m pytest tests nebula/tests -q
-m "not slow"`, split 92 + 500, 2 deselected, 150 s (baseline before the
session: 528, 130 s). Full write-up: `nebula/CL_RANGE.md`.
**`common/params.py` untouched** — rule 6; §8 of that file is the proposal.

**What this closes.** `CL_SENSITIVITY.md` §6's own caveat, open since session
10b: *"`cl` is the one parameter here that is not really free... pinning it at
whatever value maximises S3 yield, if that value is not physically
justifiable, is choosing the answer."* Every corner number this project has
published — 13.49 % / 8.20 % / 8.10 % — was measured with `cl` pinned at
**150 fF**, which was the best of five values tested for S3 yield.

**The decision this session implements** (human, taken for this task): `cl` is
**neither a design variable nor a constant**. Nobody chooses the following
stage's input capacitance, so it is not a knob (G42 already measured that
searching it LOWERS the yield); but it is not known to one value either. It is
a **context variable with a physically derived range**, to be screened like a
PVT corner.

**The range: `cl_lo` = 13.64 fF, `cl_mid` = 32.63 fF, `cl_hi` = 78.04 fF —
5.72x, 2.52 octaves.** 180 SPICE runs, 16 s. Built from what actually loads
the node under S2's topology: the 1-tap DFE summer input pair, the slicer
input pair, and the wire between them.

**`@m[cgg]` is NOT the gate load — new gotcha G50.** It is the obvious probe
and it understates the load by **1.9-2.7x**, silently, because it is the
INTRINSIC capacitance: no gate overlap (`cgso = cgdo = 2.449e-10 F/m`, ~3.9 fF
per side on a 16 um device) and no Miller multiplication of C_gd. The trap is
that the *intrinsic* C_gd of a saturated device really is ~0 (measured
1.8e-17 F), which makes "C_gd is negligible" feel safe while the *overlap*
C_gd gets multiplied by (1 + |A|). At the 16 um slicer, **52 % of the load is
that one term.** So the load is measured as the AC current the driver has to
supply into one gate under differential drive, through a zero-volt ammeter,
and cross-checked against the parsed primitives plus the model card's own
overlap constants: **1.02 % median disagreement, 2.20 % worst, over 180 runs.**
`sanity_check_load()` rejects any point that disagrees by >5 %, is out of
saturation, or is not capacitive; **0 of 180 rejected**, and a test corrupts
the AC number by 1.5x and requires the check to go red.

**The range is wide because of the SKETCH, not because of silicon.** Measured
per axis: the sizing decision moves the load **5.9x**, the process corner
1.16x, temperature 1.08x, the CTLE output common mode 1.04x. Stated plainly in
the write-up because it is the honest headline — designing the slicer would
narrow `cl` far more than any amount of corner analysis. Two smaller results
from the same runs: capacitance dispersion across S3's window is **0.17 %**
(so a lumped `cl` in the netlist is honest, previously assumed), and **the
corner that loads the node most is the one with the LEAST gm** (`fs` > `ss` >
`tt` > `ff` > `sf` for C_in, exactly inverse to gm) — the same shape of
mistake G46 had to correct once for S3.

**The minimum sizes were set by a gate that fired.** `MIN_STAGE_GAIN = 1.0`:
a summer or slicer front end that attenuates is worse than the wire it
replaced. The first sizing tried measured **|A| = 0.85 at TT**, the second
**0.95 at ss/125 C**; only 0.5 mA into 800 ohm clears unity everywhere. The
gate runs on every sweep and prints PASS/FAIL.

**The routing allowance is derived from PDK data, with one declared input —
new gotcha G51.** This install has no tech LEF and no magic techfile, so there
is no interconnect model to query. SKY130's own vpp finger capacitors state
both their total capacitance and their metal run length in squares, which
gives **0.0984 fF/um (m1) and 0.1191 fF/um (m2)**; the only declared number is
the 0.14 um metal width, and it is a divisor. Routing is 14-18 % of each edge,
so doubling the whole allowance moves `cl_hi` by a fifth of an octave against
a 2.52-octave range. **The routing assumption is not what makes the range
wide.**

**The comparison that matters, and the coincidence inside it.** The 150 fF pin
is **1.92x above `cl_hi`** — outside the derived range entirely. But a
**half-rate front end** (two data + two edge slicers on the node, which is
what a real 5 Gbps receiver with a CDR looks like) gives `cl_hi` = **141.8 fF**.
So the pinned value was not absurd; it was the right number **for a topology
S2 does not describe**. Reported and deliberately NOT folded into the bound
(rule 5) — that is a human's call and it changes the ratio from 5.7x to 10.4x.

**One finding outside `cl`, recorded because nothing else in the project
notices it:** `headroom_ok_1v8()` lets the CTLE output DC fall to 0.5 V, but
the stage it drives needs roughly **1.15 V** or its source node goes negative
— session 9c's unbuildable-tail failure, one stage downstream. Either the box
needs a tighter v_out floor or the RX needs AC coupling / a level shift.

**Added this session:** `nebula/device/cap_probe.py` (the measurement, with
the PDK constants READ from the model file and a reader that raises on a
parameter the 180 bins disagree on — `cgso` agrees, `u0` does not),
`nebula/experiments/cl_range.py` (the sketch, the routing model, and
`derive_cl_range()`, which is pure so the whole derivation re-runs from the
CSV with no simulator), the tracked 180-row `cl_range_data.csv` (G49), and
two ngspice fixtures so the parser is testable with no simulator.

**`nebula/PREDICTIONS.md` is new**, and it is committed in this same commit
**before** session 12b's experiment runs. Entry 1 predicts the
corner-and-load-robust yield at **essentially zero (0-10 of 1890)**, against
the stated expectation of 8.73-13.54 %, on the argument that S3's f_peak
window is 1.00 octave and the derived `cl` range moves f_peak by 1.26. Whether
that holds or not, the outcome goes in that file next to the prediction.

**Not started, by instruction:** the second half of task 2 (folding the range
into `s9_yield.py` and re-running). The owner reviews between tasks.

### 2026-08-06 — Session 12b (the load is the binding constraint, not the corners)

**Tests: 592 -> 618** (+26 in `nebula/tests/test_s9_yield.py`, which goes
29 -> 55). `python -m pytest tests nebula/tests -q -m "not slow"`, split
92 + 526, 2 deselected, 94.6 s. *(Commit `6d07ca5`'s message says 591; the
true post-12a figure was 592 — one test,
`test_committed_cl_range_is_the_single_definition`, was added after that count
was taken and before the commit. Corrected here rather than in history.)* Full write-up: `nebula/S9_YIELD.md` §8; prediction vs outcome in
`nebula/PREDICTIONS.md`. **`common/params.py` untouched** — rule 6.

**What was done.** `s9_yield.py`'s screen set became the cross product of the 3
corners with `{cl_lo, cl_hi}` (6 evaluations per design) and its promotion tier
45 corners x `{cl_lo, cl_mid, cl_hi}` (135 per survivor), using session 12a's
derived range. A **stage 0** was added — nominal PVT at both load edges —
because without it "the load costs X%" cannot be separated from "the corners
cost X%". **15 255 SPICE runs, 49.3 min, 8 workers.**

**THE NUMBER: 8.20% -> 0.05%.** One design in 1890, [0.01, 0.30].

        pinned 150 fF (10d)          range 13.6-78.0 fF (12b)
        nominal   255/1890  13.49%    15/1890   0.79%
        3 corners 155/1890   8.20%     1/1890   0.05%
        45 corners 153/1890  8.10%     1/1890   0.05%

Same box, same seed, **same 1890 designs** — `headroom_ok_1v8` never reads
`cl`, so the population is identical to 10d's and the comparison is paired, not
between two samples. **Corners cost 39% of the nominal winners; the load range
costs 99.4%.**

**THE MECHANISM, and it is the part worth keeping: the per-load sets are large
and DISJOINT.** 43 designs are corner-robust at `cl_lo` alone, 118 at `cl_hi`
alone, **160 at SOME load (8.47% — essentially 10d's 8.20%) and 1 at BOTH**.
159 of 160 are robust at exactly one edge. The joint set is not small because
the parts are small; it is small because they barely intersect (independence
would have predicted 2.68). At nominal PVT the same shape appears one level
down: 75 and 197 pass at the two loads, 15 at both against 7.8 expected.

**The prediction's NUMBER held and its REASONING did not, which is why the
follow-up was worth running.** `PREDICTIONS.md` entry 1, committed before the
run, predicted 0-10 designs against the stated expectation of 8.73-13.54%;
measured 1. But it argued from f_peak moving as `cl^-0.5`. Measured on 200
designs at 5 loads: **the median exponent is -0.349**, so the shift is
**0.88 octaves — SMALLER than S3's 1.00-octave window**, which by the
prediction's own logic should have left a few percent alive. Two things
actually kill them:
- **146 of 200 designs (73%) lose their interior peak entirely** across the
  load range rather than moving it out of the window. An exponent cannot see
  this — a design with no peak has no f_peak. Session 9c's "lowering f_p2
  EXTINGUISHES the peak", measured along the load axis.
- the 27% that keep a peak have **0.12 octaves of centring slack**, about
  **2 of the 15 distinct f_peak values** the window holds at session 11's
  measured 0.0664-octave quantisation.
`CL_SENSITIVITY.md` §3's single probe measured -0.48 and was taken as
representative; across 54 designs it sits at the extreme of the distribution.
**One probed sample is one probed sample** — the same lesson as G43, one
experiment later.

**Which spec binds moves monotonically with the load.** `S3_f_peak`'s share of
first failures: **42% at 150 fF, 57% at 78 fF, 84% at 13.6 fF.** Less load
capacitance puts f_p2 and the peak higher, out through the 2.5 GHz top edge.
S5 is still never the first failure anywhere; S6 twice in 11 340 runs (10d saw
twice in 5670).

**The number that turns 0.05% into a specification.** The single survivor
passes across **13.6-78.0 fF** and fails at the next ladder rung on both sides
(12.0 and 93.1 fF), so its load tolerance is **at least 5.72x and at most
7.76x** — it fits the demanded range with under one rung of margin. Its sizing
is `w_in 89.3 um, l_in 0.399 um, nf 8, i_bias 3.25 mA, rs 319, cs 1.90 p,
rl 565, vcm 1.407` — note L well above the 0.15 um minimum bin, which is the
obvious first hypothesis for anyone looking for more of them, on n = 1.

**New gotcha G52, and it was nearly published.** The first tolerance ladder
reported **4.32x** for that design — contradicting the screen that had just
passed it across 5.72x — because the ladder had no rung at `cl_lo` or `cl_hi`.
Nothing errored. **Merge the points a verdict was made at into any grid you
then re-measure that verdict on.** `cl_ladder(include=...)` does, and a test
pins it. G52 also records that the median `S3_f_peak` margin at `cl_lo`
(-17.453 GHz) is exactly the `meas ac MAX` search edge, so it reads "above
20 GHz or no peak at all", not "peaks at 19.95 GHz".

**`.gitignore` amended — G49's rule finally applied.**
`s9_yield_results.json` was on the ignore list under "regenerable"; S9_YIELD.md
§8 quotes numbers from it, so it is an INPUT to the write-up and is now
tracked. `s3_yield_results.json` and `cl_sensitivity_results.json` stay ignored
**deliberately and at a stated cost**: the copies on disk are stale relative to
what their write-ups publish, so tracking them would ship files that disagree
with their own documents.

**Renamed** `s9_yield.CL_FIXED_F` -> `CL_LEGACY_PIN_F` (with
`robust_geometry.py` and its tests), because the constant no longer describes
what the script does — it is kept only so sessions 10d and 11 stay
reproducible, and `check_reproduction()` breaks loudly if it moves.

**Health:** 0 hard simulator failures, 0 retries, 0 screen/promotion mismatches.
52 headroom rejections in the screen = exactly 2x 10d's 26, as expected since
`headroom_ok_1v8` does not read `cl`. Cost **192-199 ms per (design, corner,
load) at 8 workers** against G48's 106 ms — G48 was measured on a quiet
machine, so its number is a floor, not a budget; the shape of its conclusion is
unchanged.

**Still an OPTIMISTIC bound.** The tail is two ideal current sinks. And every
design scored here is a FIXED sizing point, while S3 says the peaking is
tunable via R_s/C_s — so 0.05% is a lower bound on what a tunable part could
do, and measuring the tunable version is the cheapest thing that could change
this verdict. Not written.

**Not started, by instruction:** task 3 (the tail transistor). The owner
reviews between tasks.

### 2026-08-06 — Session 13a (the tail transistor: device, measurements, pre-registration)

**Tests: 618 -> 679** (+61: `nebula/tests/test_tail.py` 50, plus 8 in
`test_s9_yield.py` and 3 in `test_crosscheck.py`).
`python -m pytest tests nebula/tests -q -m "not slow"`, split 92 + 587,
2 deselected, 63 s.

**This commit is the PRE-REGISTRATION.** It carries the tail device, the four
measurement stages, the tests, and `PREDICTIONS.md` entry 2 — and it is
committed **before** `s9_yield.py --n 2000` is re-run, per the standing rule.
The re-run and its write-up land in 13b.

**What closes.** HANDOFF §8's top open item since 2026-08-05: every simulation
this project had ever run used **two ideal current sinks** for the tail. That
one assumption is why every corner spread was an UNDERSTATEMENT and every yield
an OPTIMISTIC bound (G47), and it blocked three of the nine box dimensions.
The tail is now a **current mirror** — one device per side, gates driven by a
diode-connected reference at ratio N = 8. **`I_ref` is still ideal** and is the
one remaining ideal element; a fixed gate bias was rejected because it holds
`Vgs` while `vth` moves with corner, which would EXAGGERATE the corner spread.

**Four results, in the order they were measured.**

1. **The coupling identity holds exactly**, and it is what the experiment is
   about: `vds_tail == v(source)` to 0, and `v(source) == VCM - Vgs_in` to
   6e-17. So the tail's headroom requirement is **one inequality tying VCM,
   W_in, L_in, i_bias and the tail geometry together** — the only constraint in
   the spec table that couples five box coordinates. A test breaks each
   identity by hand and requires the gate to go red (rule 10).
2. **The mirror delivers 7.7% LESS than asked, and that is physics, not a bug.**
   The reference sits at `vds = vgs` ~ 1.0 V and the tail at `v(source)`
   ~ 0.34 V, so channel-length modulation gives the reference more current per
   micron. Median error -6.6% at TT, **-8.1% at ss/0.95/125 C**, -5.4% at
   ff/1.05/0 C. S6 is therefore billed on the **measured** supply current now,
   which also carries the reference branch.
3. **The tail is the LARGEST noise contributor, and the common-mode argument
   fails for a topological reason.** S5 moves **0.275 -> 0.442 mV_rms (1.61x)**
   and the two tail devices are **66.1% of the noise POWER**. The
   common-mode-rejection intuition is REAL and is visible in the same data —
   the mirror *reference* device's noise is rejected to **2e-21 of the total** —
   but it does not apply to the tails, because S2 needs **one sink per side** (a
   shared tail would short out the Rs/Cs degeneration) and two separate devices
   have INDEPENDENT noise. S5 still passes: headroom 5.5x -> 3.4x against the
   1.5 mV spec.
4. **The tail moves S3 peaking by up to 2.15 dB if it is sized freely, and by
   only -0.32 to +0.29 dB if it is sized by rule.** Small tails give peaking
   away (low `r_o` shunts the degeneration); large tails ADD it (their
   source-node capacitance degenerates less at high frequency, like Cs). The
   two cancel near W = 200 um at L = 0.5 um. Against session 11's measured
   **1.0 dB** peaking-margin requirement for corner robustness, a free `w_tail`
   consumes the entire budget on its own. **That is the case for sizing the
   tail, not searching it.**

**The bounds, all three, with per-edge provenance** — `TAIL_DEVICE.md` §6,
derived from the committed CSV by `--bounds`, and **NOT written into
`params.py`** (rule 6). The recommendation is that none of the three should be
SEARCHED: `w_tail` follows from `i_bias` by a current-density rule
(**105-124k um/A**, only 1.18x drift across a 4x current change, so it really
is a density), `nf_tail` follows from `w_tail` and the per-finger bin ceiling
and is **near-dead (0.6%)**, and `l_tail` spans only 0.5-1.0 um. That keeps the
action space at nine dimensions rather than twelve. Same shape of finding as
G38 (`nf_in`) and G42 (`cl`).

**Three new gotchas.**
- **G53** — the SKY130 bin ceiling is on **W per FINGER**, not on total width.
  `W=100 nf=1` builds, `W=101 nf=1` does not; `W=400 nf=4` builds, `W=410 nf=4`
  does not. This matters because a tail sinking several mA at `vdsat <= 0.2 V`
  and `L >= 0.5 um` needs several hundred microns of width, which reads as
  unbuildable if the limit is believed to be on the total.
- **G54** — ngspice's `.noise` can return **`inoise_total = -nan(ind)` and
  exit 0.** Caught only by accident before this (the numeric regexes do not
  match "nan"). A bias-node bypass capacitor — a real element in any mirror —
  removes it, and the value provably does not change the answer. An explicit
  non-finite pattern is now in `scan_for_silent_failures`.
- **G52 applied again, and it caught a live error.** The tail's saturation
  floor was first read off the width ladder and came out at 112.1k um/A —
  *above* the vdsat-target rule's own 105.4k lower edge, which is impossible.
  It was the ladder, not the device. Interpolated instead: **82.9k um/A**.

**One reporting change that is load-bearing.** `s9_yield.py` now prints a
**violation table** next to the first-failure table. The first-failure ranking
systematically hides any constraint that is usually accompanied by a larger
one, and `tail_saturation` is exactly that: in a 38-design pilot it was
violated by **15.8%** of designs and ranked worst in **0%**, because it misses
by tens of millivolts while `S3_f_peak` misses by 17 GHz.

**`s9_yield.py`'s default output filename now depends on the topology**, so
session 12b's `s9_yield_results.json` cannot be overwritten by a run with a
different circuit in it. It already was once, during this session's plumbing
checks, and was recoverable only because G49 had made it tracked.

**Not done, by instruction:** the `--n 2000` re-run. It follows this commit.

### 2026-08-06 — Session 13b (the tail transistor: the S9 re-run)

**Tests: 679, unchanged** (nothing executable changed in this half; 13a added
the +61). `python -m pytest tests nebula/tests -q -m "not slow"`, split
92 + 587, 2 deselected, 81 s. Write-ups: `nebula/TAIL_DEVICE.md` §8,
`nebula/S9_YIELD.md` §9, `nebula/PREDICTIONS.md` entry 2 outcome.
**`common/params.py` untouched** — rule 6.

**THE RESULT: the yield did not move. 1/1890 before, 1/1890 after, and it is
the SAME design** (index 432, identical parameters). 15 255 SPICE runs,
35.2 min, 8 workers.

        pinned-ideal (12b)     real tail (13b)
        nominal, both loads     15/1890  0.79%     15/1890  0.79%
        3 corners x 2 loads      1/1890  0.05%      1/1890  0.05%
        45 corners x 3 loads     1/1890  0.05%      1/1890  0.05%

**What the ideal-tail assumption was actually worth: 8.8%** of the
corner-robust-at-some-load population (160 -> 146), and **zero** of the
headline yield. Put next to what was already measured, that is the sentence
this session produces:

        the PVT corners cost   39%   of the nominal winners  (10d)
        the LOAD range costs   99.4%                         (12b)
        the IDEAL TAIL cost     8.8%                         (13b)

**So the argument the item was promoted on is RETIRED.** HANDOFF §8 called the
tail *"the one experiment that could still turn corner robustness into a real
constraint rather than a tax."* It did not. `tail_saturation` **is** a genuine
coupled inequality — `vds_tail` IS the input pair's source node, so it ties
**VCM, W_in, L_in, i_bias and the tail geometry into one inequality**, the only
row in the spec table that couples five box coordinates — but it binds on
2.6-13.3% of the box and costs 8.8%. Retired on the same footing as G40's
coupling claim, and §8 of this file now says so in place rather than quietly
dropping it. **AMENDED after review, and the amendment matters: retired GIVEN
THE CURRENT SCREEN, not absolutely.** The 8.8% is measured on a population the
LOAD screen had already reduced by 99.4%, so it is a conditional number — the
tail is **masked**, not unimportant. Unconditionally `tail_saturation` binds on
2.6-13.3% of the box. **When the load screen narrows to a tolerance band, the
surviving population grows and `tail_saturation` must be re-read off the
VIOLATION table**; a constraint that binds on an eighth of the box cannot stay
a footnote once the thing masking it is gone.

**The methodological finding, and it is the transferable part: "which spec
binds" has TWO meanings and they disagree by an order of magnitude.**

        tail_saturation at ss/0.95/125C:   VIOLATED 13.3%   RANKED WORST 1.5%

The first-failure ranking scores by normalised shortfall, so a constraint
missing by tens of millivolts always loses to an `S3_f_peak` missing by
**17 GHz**. `S9_YIELD.md` §2 declares "which spec fails first" the headline
output; on this evidence that table **systematically hides any constraint that
travels with a larger one**, and a real 13% constraint reads as a 1% footnote.
`s9_yield.py` now prints a violation table beside it. This was pre-registered
(`PREDICTIONS.md` 2d vs 2e predicted the gap) and the gap is why the table was
built before the run rather than after.

**Prediction vs outcome: 7 of 9 held, 2 missed, both recorded.**
- ✅ 2a yield 0-2 (**1**); 2b nominal 6-16 (**15**); 2c headroom **unchanged at
  52**, exactly; 2d `tail_saturation` first-fail 0-3% (**0.1-1.5%**); 2f S5
  never the first failure (**never, and never even violated**); 2g S6 first
  failures ~2 (**exactly 2**); 2h `S3_f_peak` dominant and worse at `cl_lo`
  (**84.4% vs 56.2%**).
- ❌ **2e** predicted `tail_saturation` violated 10-20% **at every screen
  point**; measured **2.6% to 13.3%, ordered by corner**. The reasoning was
  right about the rule and wrong about where it applies: **the rule sizes the
  tail at `ss/0.95/125C`, so at every other corner it is deliberately
  oversized** (`vdsat_tail` 0.201 V at SS vs 0.134 V at FF for the survivor).
  Sizing at the worst corner buys a **5x** reduction in tail-saturation
  failures at the best one — a result, not an accident.
- ❌ **2g's second half** predicted measured power within ±3% of requested;
  it is **-7.3%**, and the arithmetic was available beforehand
  (`1.971/2.125`). Against **12b's** billing it is only **-1.4%**, which is the
  number the claim should have been about and why S6 did not get harder.
- ⚠ 2i predicted a 0.1-1% G54 NaN rate; measured **0.07-0.11%**, at or just
  below the bottom edge.

**The pre-registered falsification mechanism is REAL but does not dominate.**
I wrote that a yield rise would mean the mirror's current shortfall was pulling
`f_peak` back under S3's top edge. Measured paired over 600 designs at `cl_hi`
(same design, ideal tail vs mirror, so the tail is the only difference):

        ff/1.05/0     6 gained,  5 lost   net +1
        ss/0.95/125   6 gained, 10 lost   net -4

4 of the 10 slow-hot losses are ranked `tail_saturation`, against 1 of 5 at
fast-cold. **The supportable statement is "the tail costs designs at slow-hot
and is roughly neutral at fast-cold"** — +1 on 600 paired designs is noise, and
the full run's `+5, +7` at the two FF columns should not be read as a gain.

**The survivor, now with a real tail under it.** Design 432 gets
**W 180.8 um / L 0.5 um / nf 8**, reference 22.6 um / nf 1, `I_ref` 203 uA.
Its tail margin is **+0.247 to +0.363 V** across the six screen points, so it
did not survive by luck on that axis. What it spends is the WINDOW: `f_peak`
ranges **1.259-2.399 GHz**, i.e. **0.93 of the 1.00-octave S3 window** —
confirming 12b's "less than one ladder rung of margin" from an independent
direction.

**One planned experiment just got cheaper to skip.** Session 11's margin
thresholds (0.133 octaves of `f_peak` margin, 1.0 dB of peaking margin) were
flagged as LOWER bounds because the tail was ideal. A rule-sized tail moves a
design's peaking by ~0.05 dB, below session 11's own 0.0664-octave `f_peak`
quantisation. **Re-running `robust_geometry.py --collect` is now low-value**,
which is worth knowing before spending 23 minutes on it.

**Health:** 0 screen/promotion mismatches, 52 headroom rejections (exactly
12b's), **12 hard failures in 15 255 runs (0.08%), all G54 NaN**. The screen
was exact again — 1 promoted, 1 robust, 0 false positives — so G46, G47 and G48
all survive.

**Still open, and now unambiguously the highest-value item:** every design
scored here is a **fixed sizing point**, while S3 says the peaking is tunable
via `R_s`/`C_s`. **0.05% is a lower bound on what a tunable part achieves**, and
that experiment is not written.

### 2026-08-06 — Session 14a (the tunable experiment: build + pre-registration)

**Tests: 679 -> 698** (+19, `nebula/tests/test_tunable.py`). Split 92 + 606,
2 deselected, 137 s. **This commit is the PRE-REGISTRATION** — code, tests and
`PREDICTIONS.md` entry 3, committed before `tunable.py --n 2000` runs.

**What it closes.** Every yield this project has published scores a **fixed
sizing point**, while S3 says the peaking is *tunable* via `R_s`/`C_s`. So
12b's and 13's 0.05 % are both **lower bounds**, and both write-ups name the
tunable version as the cheapest thing that could change the verdict.

**The design vector now splits** — FIXED (`w_in, l_in, nf_in, i_bias, rl,
vcm_in`, tail) vs TUNABLE (`rs, cs`) — and a design is *tunable-robust* iff
**for every (corner, load) point there EXISTS an (rs, cs) meeting all specs.**

**Three review corrections landed first, all from the human:**
1. **The tail's retirement is CONDITIONAL.** 8.8 % was measured on a population
   the LOAD screen had already cut by 99.4 %, so the tail is **masked, not
   unimportant**. Amended in HANDOFF §6/§8, `S9_YIELD.md` §9 and
   `TAIL_DEVICE.md` §8, with an explicit re-check trigger: **when the load
   screen narrows to a tolerance band, re-read `tail_saturation` off the
   VIOLATION table.**
2. **A second coupling through the tail, recorded** (`TAIL_DEVICE.md` §4):
   `gm_tail = 2*I/vdsat`, so `vdsat` trades headroom against noise on the same
   device. Slack today (S5 3.4x inside spec) and **it becomes live in the
   tunable experiment**, where high `R_s` adds `4kT*R_s` on top.
3. **THE REWARD SHAPE IS DECIDED and it is NOT worst-normalised-margin**
   (HANDOFF §8). A pure `min` has the same pathology as the first-failure
   table: it reports `S3_f_peak` while that misses by 17 GHz, so the agent gets
   **no gradient on `tail_saturation`** until S3 is nearly solved. Replaced by
   *sum of clipped shortfalls while any constraint is violated, then max-min
   once all are satisfied*, with margins normalised so **1.0 means
   "meaningfully off"** (octaves, dB, 100 mV).

**The enabling measurement: `alter` IS safe for `rs`/`cs`, and it is now
proven.** G35 found `alter` **silently wrong** for device geometry and merely
*asserted* it was fine for ideal R/C/I. Verified here to **rel=0, abs=0**
against fresh-parse ground truth across 3 corners x 4 targets x 2 starting
points on 8-12 quantities. That licenses sweeping the whole grid inside ONE
process: **13.6 ms per setting against ~150 ms** (G48) — an **11x speedup**,
and the only reason a tunable sweep over the whole population is affordable.
`_NETLIST` was split into `_TOPOLOGY` + `_CONTROL_SINGLE` so the sweep puts a
different control block on the SAME circuit (rule 9, G32); a test asserts the
two halves still reassemble byte-identically.

**Two bugs found and fixed while smoke-testing, both worth the space:**
- **A process-wide silent-failure scan cost 6.1 % of processes.** One G54 NaN
  in 67 settings failed all 67. The scan is now **per block**; a truncated or
  malformed run still fails everything because the block COUNT will not match.
  228/228 clean afterwards, from 214/228.
- **The G52 consistency gate fired on smoke runs.** It compares against session
  13's 1 and 146, which mean nothing at a different (n, seed). Now it only
  applies on `(2000, 20260804)` and says so otherwise — a gate that cries wolf
  on every smoke run is a gate that gets ignored.

**`PointResult` records EVERY violated spec, not just the worst** — session
13's lesson applied before the fact. The pre-registered S5 question is
unanswerable from a `first_fail` column, because high `R_s` raises noise AND
overshoots the 12 dB peaking ceiling, so S5 would nearly always lose the rank.

**Not run yet, by design:** `--n 2000`. Predictions in `PREDICTIONS.md` entry 3
— headline **10-25 % tunable-robust against 0.05 % fixed**, and **S5 predicted
to be violated somewhere for the first time in this project.**

### 2026-08-06 — Session 14b (the repository is published; docs reorganised for readers)

**No executable change. Tests 698 green before and after** (92 + 606, 2
deselected). This session is documentation and repository plumbing only.

**Why.** The owner asked for the work to go on GitHub in a form a mentor and
two teammates can actually follow. Two problems blocked that, and the second
was the real one.

1. **There was no remote.** Session 10a `git init`-ed this checkout with the
   PDFs already ignored, so its history is clean, but it has never been pushed
   anywhere. The old private repo `jaikaushik-prog/serdes-dsp-framework` is an
   **unrelated history** that still carries the ten copyrighted PDFs in its
   baseline commit (G1 as amended). **Decision: a NEW repo, from this clean
   history.** Force-pushing over the old one would discard a history nobody has
   audited, and would not fix its PDF problem.

2. **The root `README.md` was still the INHERITED starter-code one, and it
   misrepresented the project.** It advertised `rtl/`, `verification/`,
   `veriloga_models/`, `matlab_models/`, `optical_dsp.py` and three Cadence
   flows as working features. §7 of this file lists every one of them as NEVER
   RUN / NOT AUDITED. It also claimed 48 tests against an actual 698, gave a
   Cadence quick-start for a project whose competition track **mandates
   open-source tooling**, and did not mention Nebula at all. Publishing it
   unchanged would have been the most visible fabricated claim in the repo —
   rule 1, one level up from code.

**What was written.**
- **`README.md`**, rewritten as an honest landing page: the two-project table,
  a measured-results table where every row links to the write-up it came from,
  the gate status with G1 marked in progress and G2/G3 marked not started, and
  an explicit **"Not audited — treat as untrusted"** section naming all ten
  directories and files.
- **`docs/PROGRESS.md`** (new): the session-by-session progress board, written
  for a reader with zero context. Question asked -> what was found, per
  session, plus the cost table, the two methodological findings, a glossary,
  and an **honest-risk paragraph** stating plainly that the RL loop itself is
  not built yet and G2/G3 are the gates that matter.
- **`nebula/README.md`** (new): reading order for the nine write-ups, the
  layout, the two things that look like bugs and are not (`BOUNDS` empty on
  purpose; the mocks are fake by construction), and the three failure modes.

**Facts checked rather than repeated, and one correction.** The gotcha count
was verified with this file's own check (`grep -c '^- \*\*G'` gives 62 lines
but only **54 unique IDs** — G41, G52, G53 and G54 are each defined twice).
Test split re-counted: `tests/` 92, `nebula/tests/` 608 collected, 606 after
the 2 slow deselections. **CLAUDEwa.md §4.3's "~7,200 lines" does not match
this tree** — `python_models/` plus `tests/` measures **6,457**; the README
says ~6,500 rather than repeating the contract's figure.

**Also landed this session:** the session-14a work, which had been sitting
uncommitted in the working tree, is now committed as `3a037b7` — its own log
entry describes it as the pre-registration commit, and a pre-registration that
is not committed before the run is worth nothing.

**Tooling:** `gh` CLI 2.97.0 installed via winget (it was absent). Auth is
interactive and must be done by the owner (`gh auth login`); nothing was pushed
without that.

**New gotcha G55.** See §9.

### 2026-08-07 — Session 15 (the passives: real SKY130 R and C, device layer only)

**Tests 698 -> 725** (+27: `test_passives.py` 26, `test_trimmed_lib_passives.py`
partly slow-marked), 9 deselected (was 2), 140 s. Full write-up
`nebula/PASSIVES.md`. **No published number changes** — `s9_yield.py` and
`tunable.py` still instantiate ideal R and C. What landed is the device layer
they will need.

**Four of task 4's ten parts are DONE (4a, 4b, 4c, 4i), one is structurally
established (4f), and the rest are listed open rather than sketched.**

**The MIM question 4a said to answer before anything else: MIM IS available**
in this metal stack (`cap_mim_m3_1`/`_m3_2`), so the task proceeds as written.

**Three silent traps, each measured, each now pinned by a test:**
1. **`mult` and `mf` DO NOTHING** (G56). They read like device multipliers;
   they appear only inside mismatch terms, all x `MC_MM_SWITCH` = 0. `mult=4`
   gives 942.90 ohm against `mult=1`'s 942.90 ohm — a silent 4x error. **`m=`
   is the multiplier that works**, and it equals four explicit parallel devices
   to every printed digit.
2. **`w` is INERT on the fixed-width families** (G57). `res_high_po_0p69` with
   `w=0.69`, `w=2.85` and `w=99` all return 2893.64 ohm identically, and `w=99`
   raises nothing. The real 2.85 um device reads 718.61 ohm — **4.03x apart**.
3. **ngspice DISCARDS the generic families' non-linearity terms** — `p2`, `q2`,
   `p3`, `q3` all print "unrecognized parameter - ignored", so `res_high_po`
   simulates as perfectly LINEAR while the fixed-width families do not. **An S4
   claim must not be quoted off the generic family.**

**The structural 4f finding, and it is the important one: SKY130's passive
corner axis is INDEPENDENT of the MOS one, and all five MOS corners hold the
passives at TYPICAL** (G58). So **every corner number this project has
published held `rs`, `cs`, `rl` fixed** — not by decision, but because the MOS
corner names do not touch them. The library provides the **full 5 x 5 cross
product**, so **S9's 45 corners become 225**, not the 135 a three-passive-corner
guess would give. Measured spreads: poly resistor **+/-12.5%**, MIM
**-11.7/+12.9%**. Arithmetic consequence, **pre-registered not measured**: f_z
would move ~1.29x = **~0.37 octaves against 0.12 octaves of slack, ~3x** — which
points the same way 4e's own arithmetic did, and could eliminate design 432.
**The screen recommendation is deliberately NOT made** without the sweep.

**4i is a NEGATIVE result and a clean one: quantisation is not first-order.**
Over 4000 box samples, worst |f_z| rounding error is **1.04e-3 octaves =
0.87% of the 0.12-octave slack**, 4000/4000 realisable, worst component error
0.070%. `l` is free on a 5 nm grid while `f_z` depends on it through a ratio,
so the grid is ~3 orders finer than the thing it resolves.
`device/passives.py::to_geometry()` is the deliverable — it **rejects rather
than clamps**, because a clamped geometry reaches a netlist that simulates fine.

**The head resistance is why `to_geometry` widens instead of shortening.**
`res_high_po` is not `rsheet*l/w`: a fixed head term puts the floor at
**1444 ohm at w=0.35 um** and 58 ohm at w=10 um, so the whole `rs` bound is
unreachable at minimum width.

**4c: the extended trim is bit-identical but NOT free.**
`device/spice/sky130_ctle.lib.spice`, 25 sections. **rel=0, abs=0** over 8
resistor geometries, 4 MIM plates and the nfet, across 6 (MOS x passive)
sections — G36's verification covered nfet cards only and did NOT survive
adding these. Criterion did not need relaxing. **Cost: 634 ms -> 4655 ms, a
7.3x regression** on the inner loop (full library 47 s). **Variability did NOT
come back** — the extended trim's spread is 1.14x against nfet-only's 1.51x.
Likely cause identified, not yet acted on: the R/C corner files pull in
`parameters/typical.spice` (3023 lines) and `invariant.spice` (7340).

**A real bug the four-corner measurement caught:** the MIM plate offset is
**per corner and asymmetric**, and `tol_m3` follows the **RESISTOR** letter,
not the capacitor one, because it is the same metal layer. `hh` and `lh` both
have "cap_high" and differ by **0.7%**. A single-corner check would have missed
it.

**Also caught, and it is the project's own failure mode:** an equivalence
comparison passed vacuously because both sides were empty — `/usr/bin/time`
does not exist in Git Bash, so ngspice never ran and `diff` compared two empty
sets. The test now asserts a minimum value count first.

**First area numbers (4h, partial):** at design 432 the drawn passives are
**1506 um^2 = 3% of the 0.05 mm^2 S7 budget**, of which **cs is 62%** —
confirming 4h's expectation that cs leads, but **refuting any sense that S7 is
tight**. Even 10 pF is under 10% of budget. Routing, enclosure, transistors and
the ladder projection are NOT included, so it is a lower bound.

**Not done, and listed in PASSIVES.md §6 in priority order:** 4d (the
regression gate — nothing downstream is trustworthy until it passes), 4e, the
4f sweep, 4g's fold into `CL_RANGE.md`, 4h's real budget.

### 2026-08-07 — Session 16a (the channel becomes a family; pre-registration)

**Tests: 725 -> 1007** (+282: `test_channel_model.py` 133,
`test_cursors.py` 157, plus rewrites in `test_link_interface.py`), 9 deselected,
4 min 38 s. **This commit is the PRE-REGISTRATION** — code, tests and
`PREDICTIONS.md` entry 4, committed before `channel_family.py` runs the full
grid and before `--compression` runs at all.

**What it retires.** `link/config.py` carried
`<the invented DC-loss constant> = 1.0` — a placeholder whose own docstring
admitted it had no measured provenance — and `BOUNDS_REDERIVATION.md` §2 says
in a blockquote that **that constant, not the circuit, decided the compression
verdict**. It is **deleted, not re-valued**, and the symbol is gone from every
executable file in the tree (a test greps for it, and assembles the identifier
from pieces so it does not match itself).

**The constant's own name encoded the mistake.** For a lossy transmission line
the insertion loss at DC is essentially zero. What is non-zero is the loss at
**Nyquist**, and the correct low-frequency correction is not a channel property
at all: it is the transmitter's **specified -3.5 dB de-emphasis**.

**What replaces it, and where it comes from.** There is no PCIe Gen2 reference
receiver to copy — Gen1/Gen2 specify TX de-emphasis only, and receiver CTLE/DFE
enter at Gen3 — so the channel is ours to define. Industry practice sets CTLE
boost at Nyquist ~= channel IL at Nyquist, so **S3's own 3-12 dB tunable range
implies a channel family spanning 3-12 dB of IL at 2.5 GHz**. The specification
we were given defines the channel we have to equalise; that is a defensible
construction and an invented scalar is not.

**Three new modules.**
- `link/channel.py` — `IL_dB(f) = A*sqrt(f) + B*f`, parameterised by
  **(IL at Nyquist, skin/dielectric split)** with IL at Nyquist as the primary
  constructor argument and a first-class attribute (it is the conditioning
  variable the RL layer will index on — design note only, no RL plumbing).
  **Minimum-phase reconstruction** via the real-cepstrum fold of `ln|H|`, then
  **gated** on pre-`t=0` energy, passivity and monotonicity. Plus `Stackup`
  (loss -> equivalent length, never the other way), an optional stated
  two-reflection probe, and a Touchstone ingestion path.
- `link/tx.py` — the 2-tap FIR at the mandated -3.5 dB (and the -6 dB option),
  normalised so the TRANSITION bit carries full swing. It supplies **exactly**
  `-de_emphasis_db` of tilt at Nyquist, so `equalisation_burden_db =
  channel IL - TX tilt` is an exact subtraction, not an approximation.
- `link/cursors.py` — pulse response -> UI sampling at the phase maximising
  `h0` -> `h_-2..h_4` -> residual ISI after an ideal 1-tap DFE -> eye. Plus a
  **closed-form CTLE peak location**: a peak exists iff
  `1/fz^2 > 1/fp1^2 + 1/fp2^2`, which is session 9c's measured "f_z must sit
  below f_p2 or there is no peak at all" in exact form.

**Two numerical findings that are the reason to trust the rest.**
1. **The causality threshold was stated first and then MET by lengthening the
   grid, not by moving the threshold.** Pre-`t=0` energy falls as a clean power
   law with buffer length (8.7e-5 / 1.3e-5 / 1.8e-6 / 2.5e-7 / 3.5e-8 at
   n_fft = 4096..65536), which is how you tell tail ALIASING from a broken
   phase reconstruction — a broken one would sit at a floor. `DEFAULT_N_FFT` is
   32768 (512 UI) because that is the first power of two clearing 1e-6
   everywhere. **The zero-phase control puts 48.5% of the energy at t < 0** and
   raises nothing on its own, which is exactly the failure this gate exists for.
2. **Two hand-checkable references pin the whole chain.** A lossless channel
   reproduces the TX pulse to 1e-12 (`h0 = c0*A`, `h1 = c1*A`, nothing else);
   and **the UI-spaced cursors sum to the transmitter's long-run level to seven
   figures** for every family member, which is the physical statement that
   replaced the deleted constant, checked end to end.

**Also landed:** `LinkConfig` gains `channel`, `tx`, `tx_tilt_db` and
`equalisation_burden_db`; `channel_loss_db_at_dc` is now a derived property
returning **exactly 0.0**; `link/mock.py` equalises the BURDEN rather than the
raw channel tilt; the `link_cfg` fixture moved 8 -> 12 dB, because with 3.5 dB
of the work done by the transmitter an 8 dB channel leaves a badly
OVER-equalised link that the bridge tests were not written to exercise.

**Not run yet, by design:** the 21-member grid and the ngspice compression
re-run. Predictions are in `PREDICTIONS.md` entry 4 — headline **the eye stays
open across the whole 3-12 dB family, so a 1-tap DFE is sufficient**, plus
eight supporting predictions and four falsification conditions. Pilot data seen
while checking the numerics is declared in that entry rather than presented
afterwards as foresight.

### 2026-08-07 — Session 16b (the run: the answer, and a verdict replaced)

**Tests 1007 green before and after** (92 + 915, 9 deselected). Full write-up
`nebula/CHANNEL_MODEL.md`; prediction vs outcome `PREDICTIONS.md` entry 4.
Data: `experiments/channel_family_data.csv` (114 rows, tracked, G49) and
`channel_family_results.json`.

**THE ANSWER TO THE PRE-REGISTERED QUESTION: a 1-tap DFE is sufficient across
the whole 3-12 dB family.** The eye is open at all 21 members, all three
de-emphasis settings, with and without a CTLE. Worst residual **0.847** bare,
**0.613** in the actual PCIe Gen2 configuration, **0.276** with a matched CTLE.
So **S3's top of range and S8 can both be met with S2's mandated topology** —
which is the opposite of the finding the task allowed for, and it is clean.

**But the mechanism is what to carry, and it is not reassuring.** At 12 dB
skin-dominated, of the 0.613 the DFE cannot reach: **14.7% is in `h2`**, 66.3%
is in `h2..h20`, and **31.2% sits beyond 20 UI**. **A second DFE tap buys 15%;
a twenty-tap DFE still leaves 31%.** That is the `sqrt(f)` algebraic tail —
precisely what a decision-feedback architecture is worst at, since a DFE's cost
is linear in taps while the tail decays as a power law. **The CTLE is the block
that has to do this work.**

**"A scalar cannot represent a channel" is now MEASURED, not asserted.** At a
fixed loss at Nyquist, skin-dominated leaves **1.60x** the residual of
dielectric-dominated at 12 dB — and **1.99x** at 3 dB. The ratio is largest
where the channel is EASIEST, which is the opposite of where I predicted to
look, and it is recorded as a miss.

**The transmitter is worth exactly 3.5 dB of the CTLE's job**, so the burden
spans **-0.5 to +8.5 dB**. Two consequences pointing opposite ways: the **top
3.5 dB of S3's tunable range is never called for** on this family, and at
3/4.5/6 dB the burden is **below S3's 3 dB floor**, so a compliant CTLE
over-equalises. Also visible only because the TX is modelled: **`h1` changes
sign** below ~8 dB of loss — the fixed de-emphasis over-cancels the first
post-cursor and the DFE has to put energy back.

**THE COMPRESSION RE-RUN (66 SPICE runs, 64.6 s, reproduction gate 5/5).**
The gate re-simulates the published reference device before analysing anything
and matched all five published numbers (gm 12.623 vs 12.62 mS, 1 dB swing
**1426.9 vs 1427 mVpp**). Result:

        A  Nyquist in / Nyquist out (9c/9d)   3 dB = 1.22x   2/7 compress
        B  long-run in / peak out (C3)        3 dB = 1.16x   7/7 compress
        C  peak distortion, REAL pulse resp.  3 dB = 1.51x   5/7 compress

**The 1.22x SURVIVES VERBATIM under convention A** — 1689 mVpp against 1389,
digit for digit — because that convention reads Nyquist content through Nyquist
gain and **neither the deleted constant nor the de-emphasis touches either**.
So `BOUNDS_REDERIVATION.md` §2's blockquote was right that a made-up constant
decided the **C3** table, and wrong to imply the headline hung on it. **The
honest number is 1.51x, and compression binds at 5 of 7 loss points** — worse
than the line it replaces, not better. **HANDOFF §8's compression bullet is
REPLACED IN PLACE**, on the same footing as G40 and the retired tail claim.
"Worst at low loss" survives and is now explained: below 6.5 dB the burden is
under S3's floor, so a compliant CTLE adds boost the link does not need.

**A correction that had to be made before that table could be trusted (G60):
§6's design equations over-predict the Nyquist boost by +0.77 to +1.47 dB**,
growing with `R_s`, because they neglect `r_o`. Convention C integrates the
pulse response *through* that model, so the first version of the table was
**28% high** (3 dB read 1.93x). Fixed by calibrating `k` to the measured boost
with `f_z` and `f_p2` exact from the passives, leaving peaking and `f_peak` as
independent checks (+0.094 to +0.232 dB against §5.3b's 0.5 dB limit).

**S8's vertical floor is met with the CTLE ATTENUATING 13-15 dB** (required
A_dc 0.181-0.217 V/V against a measured 1.79 — 8.6x more gain than needed).
S8 vertical is not binding, and this is the first time the project can say so
with a real pulse response behind it.

**A pre-registered falsification condition FIRED.** The stated two-reflection
probe adds **+0.064 to +0.122** to the residual — within the predicted band at
low loss, well above it at high loss, because an echo is a copy of the *whole*
response and at high loss that response is itself spread. At 12 dB it takes the
channel-only eye from 118 mV to **81 mV, below S8's floor**. **Every ISI number
in this session is therefore a LOWER BOUND**, and that is now in §7,
`CHANNEL_MODEL.md` §8 and §12.

**Four of nine supporting predictions are recorded misses** (`PREDICTIONS.md`
entry 4): the 4a band was quoted from a pilot in the wrong de-emphasis
configuration; 4c's "roughly constant" was wrong; 4d underestimated how much a
TX FIR reshapes cursors it is not aimed at; and 4g/4h had the peak-distortion
bound on the wrong side of both proxies. Nothing was edited to match.

**New gotchas G59** (a magnitude-only channel is non-causal and raises nothing;
the power-law test that distinguishes aliasing from a broken reconstruction),
**G60**, **G61** ("compression ratio" has three definitions and they disagree
1.8x) and **G62** (a grep test must not contain its own needle).

### 2026-08-07 — Session 17 (task 6: the RL loop runs end to end, and six things broke)

**Tests 1007 -> 1246 green** (92 + 1154), 9 deselected. Full write-up
`nebula/RL_SMOKE.md`. Data: `experiments/rl_smoke_results.json` and
`rl_smoke_run_v0.jsonl` / `_v1.jsonl` — **all three TRACKED** (G49, and the
stronger reason that every row is free training data for task 8).
**`common/params.py` untouched** (rule 6): the RL box is nine `ActionDim`s in
`rl/contract.py`, seven copied verbatim from `s3_yield.PROPOSED_BOX` and two
from `TAIL_DEVICE.md` §6, with a test asserting the seven against the box so
the two documents cannot drift.

**THE POINT OF THE TASK WAS THE FAILURES, AND THERE WERE SIX.** Four of them
produce a plausible number and raise nothing; two of those would have produced
a training run that reports a policy while scoring a circuit that does not
exist. Cost 105 minutes in total. In order of how much they mattered:

1. **`has_interior_peak` is a CONJUNCTION and its two terms reject different
   kinds of thing (G64).** Used as an RL validity gate it rejected both the
   G44 fictitious peak (`g_pk - g_top` ~ 0, response still rising at 20 GHz,
   `peaking_db` large and fake) AND a genuine-but-small interior maximum
   (`rs` = 50 ohm: 0.165 dB at 1.318 GHz, a perfectly good measurement of a
   circuit that does not equalise). That put the reward FLOOR across the whole
   low-peaking bottom of the box — which is exactly where a randomly
   initialised policy starts. Split into `peak_is_sweep_edge`;
   `has_interior_peak` is UNCHANGED because three experiments publish counts
   with it. Found by the §6f calibration, which is what §6f is for.
2. **`alter` fails silently on an element the netlist no longer CONTAINS
   (G63).** With drawn passives there is no `Rdeg`, so `run_tunable_sweep`'s
   `alter Rdeg` matches nothing, ngspice warns and exits 0 (G26), and all 67
   settings return the FIRST geometry's numbers. Now refused outright.
3. **Two gates that failed for the WRONG reason (G68):** a one-sided
   sensitivity probe reported `i_bias` as INERT when it had merely left the
   feasible region; and validity checks ordered symptom-before-cause reported
   an out-of-saturation design as an `f_peak` range anomaly. The same ordering
   fix, applied twice, moved **159 of 203 invalidities** out of the wrong
   bucket.
4. **`shutil.which` cannot find this project's ngspice (G69)** — the only test
   exercising the real simulator end to end was silently skipping, and a skip
   reports as a pass.

**THE HEADLINE MEASUREMENT, and it justifies the whole poison-safe evaluator:
78% of everything the policy found was G44 (G65).** Over 500 PPO steps / 765
evaluations, **26.5% were invalid**, split `peak_is_sweep_edge` 159,
`tail_triode` 28, `pair_triode` 16, everything else 0. Under a reward scoring
S3 peaking, every one of those 159 would have been a HIGH reward for a circuit
with no peak at all. The rate did NOT rise (28.8% -> 24.3%), but 500 steps
cannot separate a trend from noise and the histogram is the useful output.

**THE 4d REGRESSION IS RUN, AND IT MOVES A PUBLISHED VERDICT (G66).**
`PASSIVES.md` §6 item 1 said nothing downstream is trustworthy until this
passes; it had not been run, and §6a's "use `to_geometry()` from the outset"
forces it. Six designs including 432, ideal R/C vs drawn SKY130 devices:
**worst |d f_peak| = 0.1329 octaves against the 0.12 octaves of centring
slack** session 12b measured for the sole load-robust survivor. Every non-zero
shift is NEGATIVE and the mechanism is the predicted one — the `res_po`
bottom-plate parasitic puts **1.4-24.3 fF on a `cl` of 32.6 fF, up to +75%** —
while `g_dc` moves at most 0.0006 dB. **So the load screen and the corner
screen both need re-running with drawn passives before design 432 can be
quoted as load-robust.** Second finding: **`to_geometry` is electrically
stable and geometrically chaotic (G67)** — a 0.016% change in `rs` flips the
device, giving a **15x area spread across a 0.16% resistance spread**, which
makes `PASSIVES.md` §4.5's 1506 um^2 a property of the quantiser, and makes
`design_id` grouping fine-grained rather than coarse (765 rows, 765 ids, 764
geometry tags).

**WHERE THE WALL CLOCK GOES, measured for the first time: 99.7% is the
simulator.** 500 steps = 1590 s = 26.5 min; environment 1585.83 s, policy
forward + PPO update **3.52 s**, logging and cross-check 0.87 s. Optimising
the RL side is worth nothing. **The library parse is the whole game**: 2.07 s
per evaluation on the extended trim against ~0.33 s on the nfet-only trim for
the same netlist, so **`PASSIVES.md` §6 item 6 (trim `parameters/typical.spice`
and `invariant.spice`) is the highest-value open item for RL throughput** and
this is the first number that says so. Cost accounting, defined here and
binding afterwards — **every** SPICE invocation counted, including setup, warm
start, discarded episodes and cross-check re-runs: **1.586 sims/step, 1132
steps/hour, 793 calls for 500 steps.**

**Also measured, and it invalidated one of this session's own runs (G70): ONE
concurrent ngspice makes each run 4.8x slower** (1.93 s -> 9.28 s) against the
extended library, four times worse than G48's 1.13x on the nfet-only one. The
reward-v1 pass overlapped a pytest run that calls ngspice, so **its timings are
DISCARDED** and only its load-independent results are quoted.

**§6f's calibration orders correctly**: design 432 **+8.951 FEASIBLE**, flat
(rs at the box floor) **-1.155 infeasible on 2**, op-fail (i_bias AND rl at
their ceilings, both devices in triode) **-8.000, exactly the floor**. It did
NOT order correctly before fixes 1 and 3 — flat and op-fail both sat on the
floor and the test could not run.

**§6e's sensitivity gate: 9/9 dimensions live**, each moving its expected
channel in the expected direction under one `MAX_STEP`. Three things the table
says that the count does not: the dimensions differ in strength by **21x**;
**`vcm_in` is a 6x stronger lever on the tail margin than `tail_j` is**, which
is evidence FOR `TAIL_DEVICE.md` §6's recommendation not to search the tail;
and `w_in`/`l_in` are the two weakest axes, acting on peaking through gm where
`rs` acts 4-10x harder.

**§6b: nothing broke when the mocks were removed, and the check was made
anyway.** They were already imported only by `tests/conftest.py` and five test
modules. The verification runs in a SUBPROCESS — asserting on this process's
`sys.modules` would be vacuous, since conftest imports the mock at collection
time — and `test_the_gate_can_fail` runs the same probe against a script that
imports one on purpose. **The real structural risk is different and is now
pinned: the LINK layer is a mock end to end, so any future S8 reward term would
score a fabricated eye height.** A test asserts the reward/env/evaluator import
graph reaches no `nebula.link` module at all.

**NO CONCLUSION ABOUT LEARNING IS DRAWN.** Mean episode return over five
buckets: -2.98, -6.16, -4.54, -3.09, -0.50. Non-monotone, 142 episodes, one
seed, one target, one corner. Nothing was tuned and nothing was adjusted to
make the curve look better.

**The parallel sweep needed running twice (G71).** Forward order reported
**4.39x at 11 workers, better than G48's 3.18x**, with 2 workers at a
physically impossible **2.55x** — the 1-worker pass ran first on a cold file
cache. Reversed, the baseline drops 2.7x and the answer is **2.64x at 8
workers, 11 SLOWER than 8**: the extended library scales WORSE than the
nfet-only one and the curve turns DOWN past 8, same mechanism as G70.

**The v1 wiring pass (200 steps, 319 evaluations) confirmed the wiring and
found a third category.** All four added specs are identically zero and all
four are WIRED — margins vary and never go negative: S5 +0.93 to +1.37 mV of
headroom, S6 +1.2 to +14.1 mW, `saturation` +0.042 to +1.356 V,
`tail_saturation` +0.013 to +0.595 V. But **`saturation` and `tail_saturation`
can NEVER be violated on a valid evaluation**, because a triode design is
rejected by the validity gate before the reward sees it. They contribute only
to the feasible branch's `min(margin/tol)`. **This partly undercuts the reward
retraction's own motivation**: the tail's "you are violating this" signal is
delivered by the invalid FLOOR (-8.0), which is stronger than a shortfall but
UNGRADED — 1 mV and 500 mV into triode score identically. Recommendation, and
it is a human's (rule 6): **accept it**, because grading a triode design's
small-signal numbers would be grading fiction, which is exactly what G24
records the link layer doing with `min()`. The alternative — grade it from the
`.op` `vds - vdsat` alone — is more code and a new failure surface and nothing
measured says it is needed. The v1 invalid rate DID rise (25.2% -> 33.8%), the
one place §6d's signal fired, but on 61 episodes that is weak evidence and is
not offered as more.

New gotchas **G63-G73**.

---

**SESSION 17b — the review, and three decisions that changed the code.**
The owner reviewed the above and made four calls. Three of them are now
implemented; the fourth is an ordering decision recorded in §8.

**The headline was re-framed, and it is not a diagnostic.** *"A quarter of
evaluations in a naive RL loop return a number that looks valid and isn't, and
78% of those score high under a reward that measures peaking"* is **the
verification contribution, quantified, on real artifacts** — it belongs in the
abstract and on a slide. Nobody in this literature reports it because nobody
checks: the reference implementation (`ams_rl_ppo`) runs against a synthetic
analytic simulator with no PDK, so the failure mode cannot arise there.

**CALL 1 — the §9.3 recommendation was REJECTED, and the graded band built
(G72).** The rule: **a validity gate asks "can I trust this measurement?", a
reward asks "is this circuit good?"** A 0.165 dB peak is a trustworthy
measurement of a bad circuit; a peak at 19.95 GHz is an untrustworthy
measurement. Same-looking output, opposite handling. So **trustworthiness is
per ANALYSIS**: `vds`/`vdsat` come from `.op` and are true whether or not the
device is saturated, so a triode design keeps its DC headroom and loses only
its AC spec set. Three verdicts (VALID / HEADROOM_ONLY / INVALID), four
exactly-separated reward bands, every boundary a function of the spec count:
feasible >= N+1, infeasible [-N, 0), **headroom (-(N+2), -(N+1)] graded by
`vds - vdsat`**, invalid -(N+3). Measured: the `op_fail` reference moves from
the -10.0 floor to **-8.746**, and 1/10/50/100/300/1000 mV of triode depth
grade to -8.010/-8.091/-8.333/-8.500/-8.750/-8.909. The band uses `h/(1+h)`
and NOT the `clip(h,0,1)` used elsewhere — there is no sum here, so a clip
would make 500 mV and 50 mV score identically and leave no direction out of the
deep end.

**CALL 2 — the tail LEFT the action space, 9 -> 7 dimensions (G73).** The §6e
gate had cleared `tail_j` and `l_tail` as live (|d_obs| 0.1008 and 0.0982), but
`vcm_in` moves the SAME channel by **0.605** — a **6x stronger lever on the
quantity the tail geometry exists to control**. A weak dimension that is
REDUNDANT with a strong one is worse than a dead one: the policy gradient
learns noise and spends samples doing it. The tail is now derived
(`w_tail = i_side * TAIL_UM_PER_AMP` at `TAIL_L_UM`, imported from `s9_yield`,
one definition) and **`tail_saturation` remains an active scored constraint** —
removing degrees of freedom does not remove the coupling.

**The re-run on the new contract (200 steps, 276 evaluations) produced an
unpredicted second argument for Call 2.** Invalid rate **29.5% -> 10.5%**, and
only 19 of that is the triode reclassification: `peak_is_sweep_edge` fell
**75 -> 28**, because a tail sized from its own current cannot be starved into
a bias point that pushes the peak out of the sweep. The graded band was
exercised **18 times, spanning -1.0 to -188.1 mV, producing 18 DISTINCT
rewards** — strict ordering at every depth, no ties.
**And it exposed a reporting bug in this session's own write-up:**
`saturation`/`tail_saturation` still show 0 violations among valid rows, which
17a called "correctly free". It is **wrong** — they are violated 10 times each
and the violations are routed to the graded band, because violating either is
what MAKES a design HEADROOM_ONLY. `_shortfall_stats` now reports
`n_headroom_violated` beside `n_violated` and says "BINDS VIA THE GRADED BAND".

**CALL 3 — the re-run ORDER, in §8.** Trim the R/C corner files first (99.7% of
a run is the simulator), then correct the `cl` budget with the resistor
parasitic, then collapse the passive corner axis, THEN re-run the screens.
Re-running before the `cl` range is corrected means re-running with the wrong
range. **A prediction is pre-registered before step 2** (`PREDICTIONS.md`
entry 5, the owner's): the parasitic adds a floor to BOTH ends of the load
range, and since the load's damage comes from its RATIO (5.72x) rather than its
width, the direction is **COMPRESSION** — nominally to ~3.7x — so **it may
HELP**, which is the opposite of how G66 reads on first sight.

**The benchmark is now order-safe, and making it so produced a stronger
finding than the original (G71, amended).** Randomising the configuration order
and adding a control re-run was NOT ENOUGH: on a completely idle machine the
control still reported **1.60x**, because **the first configuration always pays
the cold file cache, whichever one it is.** Randomising only stops the penalty
always landing on the same configuration. The fix is a **discarded warm-up
pass**; the control is the **detector**. With warm-up + randomisation + control
the sweep is clean (control 0.85x) and the answer is **2.98x at 8 workers with
11 SLOWER than 8** — the extended library scales worse than G48's nfet-only
3.18x and its curve turns DOWN past 8. Standing rule, from the owner: *"keep
looking for the impossible number rather than the disappointing one"* — 2.55x
at two workers was the tell precisely because it was impossible.

### 2026-08-07 — Session 18a (task 7 PRE-REGISTRATION, committed before the run)

**This commit exists so that its timestamp is evidence.** `PREDICTIONS.md`'s
own rule: *"Any experiment whose result could be argued for after the fact gets
a prediction committed to git BEFORE it runs."* Task 7 builds the benchmark the
final claim rests on, so the predicted ordering goes in first and the sweep
runs afterwards.

**Landed here, none of it yet run against ngspice:**

* `nebula/experiments/baselines.py` — the benchmark harness. Problem ladder
  P1/P2/P3 (P4 a declared seam), five methods against ONE evaluator, ONE
  scalar (`reward_v1`, seven rows, worst case over evaluation points) and ONE
  geometry mapping; every simulation charged including retries; seeds by a
  stated rule; evaluator commit pinned into every artifact.
* `nebula/experiments/prescreen.py` — 7e's analytic pre-screen, **calibrated
  and measured on already-paid-for data** (`robust_geometry_data.csv`, 1890
  simulated designs from session 11). No new simulation was run to produce it.
* `nebula/PREDICTIONS.md` entry 6 — the predicted ordering per rung, the
  numbers it rests on, and five falsification conditions.

**7a's arithmetic, computed rather than asserted** (`--budget`): the fully
crossed design (3 rungs x 5 methods x 2 screen arms) is **63 000 simulations =
23.5 h** at the measured 1.341 s/simulation at 8 workers, so it does not fit an
overnight run. The cut falls on **problems and pre-screen arms, never on the
per-run budget and never on the seed counts**: P2 is dropped entirely, P3 loses
its screened arm and its PPO arm. What remains is **200 runs, 30 000
simulations, 11.2 h** at the pessimistic rate and 5.8 h at the optimistic one.

**7e's headline, measured before this was written and therefore declared as
seen data in the prediction: the loud verdict DOES NOT FIRE.** The analytic
pre-screen predicts `f_peak` to **4.93 % MdAPE** globally and **4.80 %** in the
0.5-5 GHz decision region, rejects **61.7 %** of the box for free at a
**0.39 %** false-rejection rate, and takes the S3 rate among accepted designs
from **13.44 % to 34.94 %** — a **2.60x** lift that does **not** clear 7e's
50 % threshold. **Physics does not solve the nominal problem; it removes
three-fifths of the box for free.** The nuance that must travel with that
number: the screen CAN be pushed to **76.4 %** effective yield at zero
widening, but only by discarding **15.75 %** of the designs that actually meet
S3, and a rejected design is gone from the run while a false acceptance costs
one simulation and is then caught by the evaluator.

**Two corrections earned while building it, both from the same habit of
checking that a gate can fire:**

* the G60 correction is **one scalar on `k`, fitted from the measured PEAKING
  and nothing else**, exactly as G60 prescribes — which leaves the f_peak error
  as an INDEPENDENT check rather than a fit target. `alpha` = 0.90; `alpha` =
  1.0 is §6 verbatim and biases peaking by **+0.27 dB**, the same direction as
  G60's +0.77 to +1.47 dB on a higher-`Rs` population.
* a **"peak is at the grid edge" test can never fire on a one-zero/two-pole
  response**, because that magnitude falls as 1/f and its maximum is always
  interior. It fired zero times on 1890 designs. What the SIMULATOR reports as
  an edge is a peak above its own 20 GHz search top, so the predictor uses
  `evaluator.F_PEAK_HZ_LIMITS[1]` — and the G44 population is caught anyway,
  **84.3 % of it (488 of 579)**, under the f_peak label.

**1246 green before and after** (nothing executable was changed in an existing
module). The sweep, the tests for `baselines.py`, and `nebula/BASELINES.md`
follow in 18b.

### 2026-08-08 — Session 18b (task 7: the benchmark runs, and it moved two of its own inputs)

**Tests 1246 -> 1292 green** (+46: `test_baselines.py` 28, `test_prescreen.py`
18). Full write-up `nebula/BASELINES.md`; pre-registration `PREDICTIONS.md`
entry 6, committed in 18a **before** any of this ran.

**WHAT WAS RUN: a 1992-simulation PILOT, not the sweep.** 33 runs, 7.4 h,
60 simulations per run against the sweep's 150, 3 seeds against 10-20. It
exists to validate the harness end to end and to test whether the pre-screen
transfers. **Nothing in it is separable at 3 seeds and every table says so.**
The 25 500-simulation sweep is specified, costed, tested and reproducible by
one command; it has not been run.

**THE PILOT MOVED TWO OF THE BENCHMARK'S OWN INPUTS, which is the most useful
thing it did.**

**1. 8 workers buy 1.80x, not 2.98x — and the difference is what the workers
are doing.** Measured on 33 real runs / 1992 simulations / 27 064 summed
worker-seconds: single process **3.060 s/sim**, 8-worker aggregate **1.698
s/sim**. Session 17's 2.98x came from 24 ISOLATED evaluations dispatched to a
pool, where a worker ran nothing but ngspice. Here each worker also runs
CMA-ES's eigendecomposition, GP-BO's O(n^3) fit and PPO's torch forward between
simulations. **Sizing to 1.341 would have planned a 12-hour run that takes 15.**
The allocation was re-cut on the spot: 30 000 sims was 14.2 h, so P3 lost its
LHS and GP-BO arms (the pilot found 0/2 seeds feasible there for both methods
it ran) giving **25 500 simulations = 12.0 h**. Per 7a the cut fell on
PROBLEMS, never on the per-run budget and never on the seed counts, and a test
enforces that.

**2. THE PRE-SCREEN DOES NOT FULLY TRANSFER, AND A PRE-REGISTERED
FALSIFICATION CONDITION FIRED.** Measured on the pilot's 900 unscreened P1
evaluations against the calibration set:

    free-rejection rate    61.7 % -> 63.9 %     transfers
    effective yield        34.9 % -> 38.2 %     transfers
    yield lift              2.60x -> 2.66x      transfers
    f_peak MdAPE           4.93 % -> 15.85 %    3.2x WORSE
    peaking bias         -0.009 dB -> +0.361 dB the bias is BACK
    false rejection        0.39 % -> 3.88 %     10x OVER its 1 % budget

**The population-level rates transfer and the predictor's ACCURACY does not.**
And **widening cannot fix it**: at 2.5x the chosen widening the false-rejection
rate is still 2.33 % while free rejection falls 64 % -> 40 %. **A window cannot
absorb a bias.** The likely mechanism is checkable and specific: the gm/I_D
model was fitted on an IDEAL-TAIL population where `I_D` is exactly
`i_bias / 2`, and the real mirror delivers **4-8 % less** (session 13) — so
`I_D`, `gm`, `k` and the peaking are all over-estimated, +0.361 dB being the
right direction and about the right size. Drawn passives add a second term:
`to_geometry` quantises `rs` by up to ~6 % and `k` is linear in `rs`.
**The re-fit is deliberately NOT done here** — re-fitting a calibrated constant
on a 3-seed pilot without the ability to re-verify it is what rule 6 exists to
prevent — and it is item 1 of `BASELINES.md` §12. Until it happens **every
screened arm carries a known 3.9 % false-rejection rate and must be read with
it.**

**7e's LOUD VERDICT, measured before any of the above and on already-paid-for
data: IT DOES NOT FIRE.** The analytic pre-screen predicts `f_peak` to
**4.93 %** MdAPE (**4.80 %** in the 0.5-5 GHz decision region), rejects
**61.7 %** of the box for free at a **0.39 %** false-rejection rate, and lifts
the S3 rate among accepted designs from **13.44 % to 34.94 %** — **2.60x, and
not the >50 % that would mean physics solves the nominal problem.** So a
learned method is still needed for SEARCH and the RL contribution does not
collapse onto amortisation alone. **The nuance that must travel with it:** the
screen CAN be pushed to **76.4 %** effective yield at zero widening, but only
by discarding **15.75 %** of the designs that actually meet S3, and a rejected
design is gone from the run while a false acceptance costs one simulation and
is then caught by the evaluator. A test pins the verdict IN BOTH DIRECTIONS, so
if a future change clears 50 % it fails loudly rather than updating a number.
**What the screen actually removes: 84.3 % of the G44 population (488 of 579
designs with no interior peak at all)** — the class session 17 measured as 78 %
of everything its policy found.

**A NEW FINDING THE BRIEF DID NOT ASK FOR AND THE BENCHMARK NEEDED: THE PRIMARY
METRIC HAS A CEILING, AND IT BELONGS TO THE AC SWEEP RATHER THAN TO THE
CIRCUIT.** `meas ac MAX` can only report a frequency on the `ac dec 50 1meg
100g` lattice — **0.066439 octaves apart** — and `S3_f_peak` is reward v1's
binding row on P1. With the target at the geometric centre of S3's octave the
nearest grid point is **0.024665 octaves** away, so **no design can score above
+8.950669**. Derived analytically, then measured: **four independent pilot
runs found four DIFFERENT designs all scoring 8.950670.** Consequences:
best-reward-at-budget SATURATES on P1 — six of ten P1 groups sit exactly at the
ceiling and no P1 pair is separable — so the harness also reports **simulations
to reach the ceiling**, censored and handled identically to
simulations-to-first-feasible. This is not a defect in the reward; it is the
reward faithfully reporting that the measurement cannot resolve `f_peak` more
finely than 0.066 octaves.

**7a's arithmetic, computed rather than asserted.** Fully crossed (3 rungs x
5 methods x 2 screen arms) is **63 000 simulations = 29.7 h** at the revised
rate. Allocated: **170 runs, 25 500 simulations, 12.0 h**. **P2 cut entirely**
(the split it would resolve is already measured twice: corners 39 %, load
99.4 %); **P3 cut to uniform + CMA-ES**; **P3's screened arm cut** (the screen
is calibrated at TT and its corner behaviour is unmeasured — a screened P3 arm
would confound "the screen helps" with "the screen is miscalibrated off
nominal"); **P3's PPO arm cut structurally**, because `CtleSizingEnv` takes one
corner and one load and inventing a worst-over-corners environment for one
method would make the comparison about corner handling rather than about
search.

**Pilot indications, none of them conclusions at 3 seeds.** On P1 every method
found a feasible design on every seed; medians to first feasible were uniform
**3.0**, +screen **1.0**; CMA-ES **6.0**, +screen **1.5**; GP-BO **6.0**,
+screen **1.0**; PPO **4.0**; LHS **38.0**. Two are worth watching:
**PPO was pre-registered to lose and did not obviously lose** on
time-to-feasible (3/3 seeds, median 4.0) while having the worst FINAL reward of
the ten groups (8.252) — which is the shape the pre-registration's reasoning
predicted, reached feasibility fast and then failed to climb; and **LHS is the
worst method here**, against the pre-registration, on an interval of [3, 41]
that may be noise. **On P3, 0 of 4 seeds found anything feasible**, consistent
with the prediction that the robust rung is empty.
**`PREDICTIONS.md` entry 6's outcome section stays EMPTY until the sweep runs**
— a pilot must not close a pre-registration.

**Invalid rates, per method (7f).** P1 unscreened 13.3 % (GP-BO) to 38.3 %
(LHS); P3 44.9-52.1 %; all far above session 17's 10.5 % on a uniform box
sample. The mechanism is overwhelmingly one thing: **392 of ~430 invalid
evaluations — 91 % — are `peak_is_sweep_edge`**, against G65's 78 % on a policy
trajectory. The pre-screen removes 84.3 % of that population for free, which is
why screened arms roughly halve their invalid rate and GP-BO+screen reaches
**3.3 %**.

**THE RUN DID NOT FINISH CLEANLY, AND THE RECOVERY IS NOW PART OF THE TOOL.**
33 of 34 jobs completed and the process was killed before it wrote a summary or
ran the timing control. **Every row survived because the log streams**, and
`baselines.analyse_log()` was written to rebuild the whole analysis from the
`trial` rows — which is now the documented recovery path
(`--analyse FILE.jsonl`) and matters far more for a 12-hour sweep than for a
7-hour pilot. It rebuilds from trials rather than from the logged run summaries
on purpose: the summaries omit the anytime curve, and a summary that disagreed
with its own trials would be two definitions of one thing (rule 9).
**Consequence stated rather than hidden: the timing control never ran, so by
7g's own rule this pilot's WALL-CLOCK numbers are unvalidated.** The simulation
counts stand — which is exactly why 7g asks for simulations as the headline.

**Everything is tracked, not gitignored (G49):** `baselines_pilot.jsonl` is
4.2 MB of real SPICE evaluations with a `design_id` on every row, and it is
**free labelled training data for task 8's surrogate** — regenerating it costs
7.4 hours.

### 2026-08-08 — Session 18c (task 8 first cut: the closed form matches the black box)

**Two scripts debugged and run** — `experiments/task8_blackbox.py` and
`experiments/task8_symbolic.py`. Results tracked as
`task8_blackbox_results.csv` and `task8_symbolic_results.csv`. Tests unchanged
at **1292 green** (neither script is imported by the suite yet).

**THE HEADLINE: an exact closed form with ONE fitted scalar matches gradient
boosting on `f_peak`.**

    exact closed form, calibrated k        4.25 % MdAPE   (1 fitted scalar)
    the analytic pre-screen (grid argmax)  4.32 %
    XGBoost, 17 features, 300 trees        4.64 % MdAPE   (held out)
    Ridge on physics features, scaled     11.09 %

On `peaking_db` the black boxes do win: XGBoost 0.227 dB against the closed
form's 0.266 dB. On `f_peak` they do not.

**PySR NEVER RAN AND CANNOT HERE.** `pysr` is installed but `juliapkg` dies
with `OSError errno 22` on `WindowsApps\...\python.exe` — the Microsoft Store
app-execution alias is a zero-byte reparse point that cannot be opened as a
file. **This is an interpreter problem, not a code problem**; no conda is on
PATH in this checkout. `task8_symbolic.run_pysr()` is kept, with two of its own
bugs fixed (`parallelism=False` is not a valid value, it wants `"serial"`; and
it fitted and scored on the SAME rows and then compared that in-sample number
to the pre-screen's).

**The search was unnecessary, because the answer is derivable.** For a
one-zero/two-pole magnitude the peak is a stationary point; substituting
`u = w^2` and setting `N'D = ND'` gives `u^2 + 2 a u + (ab + ac - bc) = 0`,
hence

    f_peak = sqrt( sqrt((f_z^2 - f_p1^2)(f_z^2 - f_p2^2)) - f_z^2 )

with **no fitted constant at all**. A searched expression would have confounded
model error with fit error; this separates them.

**THE ERROR DECOMPOSITION IS THE USEFUL OUTPUT, and it bounds an open item.**
The pre-screen's ~4.3 % `f_peak` error splits as:

    grid discretisation (1200-point log argmax)   0.17 %
    predicted k vs MEASURED gm/gmbs               1.20 %
    the 1-zero/2-pole MODEL against SPICE         4.25 %

**So the error is the topology model, not the gm surrogate and not the grid.**
Consequence: re-fitting the gm/I_D model — HANDOFF §8's top item — can buy
**at most ~1.2 %** of the f_peak spread, and nothing that keeps this transfer
function goes below ~4.25 %. That bounds the improvement effort before anyone
spends a day on it. **It does NOT retire the re-fit**, because that item is
about the **+0.361 dB peaking BIAS** at benchmark conditions, which is a
different failure from the f_peak spread.

**The retracted `20 log10(k)` is now quantified over 1311 designs**, not one:
closed form median |error| **0.266 dB**, asymptote **1.199 dB** — and the
asymptote's median BIAS is **+1.199 dB**, i.e. it essentially always
over-predicts. Session 9c saw 7.66 dB predicted against 0.00 dB realised at a
single point; this is that effect measured across the box.

**The existence condition falls out of the algebra**: the discriminant needs
`f_z < f_p1` (automatic, `k > 1`) **and** `f_z < f_p2` — which is session 9c's
bench finding *"f_z must sit BELOW f_p2 or there is no peak at all"*, derived
rather than observed. **But it is SENSITIVE, not SPECIFIC**: it holds for
99.9 % of designs that measured a peak and rejects only **56.6 %** of the 579
that measured none, against the pre-screen's 84.3 %. So the existence test is
not a free screen on its own; the f_peak-window test is what does the work.

**FOUR BUGS FIXED IN `task8_blackbox.py`, one of which would have produced a
wrong published conclusion:**
1. **Ridge on UNSCALED features.** The matrix spans `cs` ~ 1e-12 to `f_z` ~ 1e9
   and an L2 penalty is scale-dependent, so "physics regression loses" would
   have been a numerical artifact. Now `StandardScaler` in a pipeline — and it
   still loses, at 11.09 %, which is now a real result rather than an artifact.
2. **The G44 filter was `1e6 < f_pk < 19e9`**, which admits sweep-edge maxima
   below 19 GHz. Replaced by the interior-peak test `g_pk - g_top > 0.25`:
   1867 rows -> **1311**.
3. **One fold, not five**, and no untouched held-out split.
4. **No boundary-restricted error and no fit wall-clock**, both of which 8b and
   8f require.

**8b's GroupKFold IS A NO-OP ON THIS FILE and the script now says so out
loud.** `robust_geometry_data.csv` is **one row per design** — 1311 rows,
1311 groups — so grouping degenerates to a plain K-fold. There was no leakage
to prevent and none was prevented. The grouped split is kept so the protocol
stays correct when per-corner rows arrive.

**Boundary error is BETTER than average error, not worse** (ratio 0.73-0.86
across every model), which is the opposite of 8b's stated worry and is reported
as such rather than quietly passed.

**AND THE BLOCKER FOR THE REST OF TASK 8: THE PER-CORNER DATA DOES NOT EXIST.**
Task 8a's premise — *"we already have roughly 20 205 (design, corner) SPICE
results from the S9 sweep"* — **is false for this repo.**
`s9_yield_results.json` kept only COUNTS (`per_point_met`,
`first_fail_counts`, index lists); the 20 205 individual measurements were
never written to disk. That is **G49's failure mode one level up: the file is
tracked, but it only ever stored aggregates.** Inventory of per-corner MEASURED
rows on disk: `tail_device_data.csv` 261 (a tail-geometry study, not a box
sample), `cl_range_data.csv` 180 (`gm` only), `baselines_pilot.jsonl` P3 arm
~240, and the baselines sweep's P3 arm **4 500 when it runs**. **So 8d's
accept-or-abandon rule — written against WORST-CORNER MAE — is NOT EVALUABLE
today**, and `task8_blackbox.py` prints that rather than quietly scoring TT and
calling it a verdict. Either run the sweep or re-run S9 with row-level logging;
4 500 rows from a rung the pilot suggests is empty may be the worse of the two,
and that is a human's call.

### 2026-08-08 - Session 18d (the ordered plan for whoever is next)

**`nebula/NEXT_STEPS.md` is new**, written because the owner is out of agent
sessions for three days and the next continuation may be a chat agent with no
repository access. It carries the ordered plan, a ready-to-use prompt per step,
and the exact files to paste alongside each prompt for an agent that cannot
read the tree.

**The two things it says that are not obvious from HANDOFF alone:**

**1. G2 is 12 days away and not started, and it is the deliverable.** The
competition asks for a framework that takes target specs in and emits a sized
schematic plus its specs. **The link half does not exist** -- the link layer is
a mock end to end (G16), which is why `rl/reward_v1.py` correctly refuses to
score S8. Everything measured so far is device-layer. NEXT_STEPS puts G2 in parallel
with the sweep rather than behind it, because it depends on neither the trim
nor the benchmark.

**2. The ordering is: trim the library, then close the loop.** Everything else
-- the sweep, the pre-screen re-fit, the surrogate -- is an improvement to
measurement the project already has in abundance. The recommended cut order if
time runs short is task 8 first, then the spec-conditioned policy, then the
depth of PPO tuning; never G2.

Nothing executable changed. **1292 green, unchanged.**

### 2026-08-12 - Session 19a (the library trim: an evaluation costs 13x less, and the standing explanation for the cost was wrong in both halves)

**`NEXT_STEPS.md` step 1, and it was the top open item since session 17.**
Session 17 measured **99.7 % of a training run is the simulator**, so the
per-evaluation SPICE cost is the only throughput lever that pays. **An
evaluation with drawn SKY130 passives now costs 0.222 s against 2.887 s --
13.02x -- and not one measured number moved** (50 designs x 11 fields, rel = 0,
abs = 0). Full write-up `nebula/LIB_COST.md`.

**THE HEADLINE IS THAT THE DIAGNOSIS WAS WRONG, NOT THAT THE FIX WORKED.** The
standing account -- in `PASSIVES.md` §3.2, in G70, and in
`sky130_runner.lib_for_device`'s own docstring -- was that the R/C corner files
pull in `parameters/typical.spice` (3023 lines) *and* `invariant.spice` (7340).
**Both halves fail on inspection.** `invariant.spice` **is not in the include
tree at all** (only `parameters/montecarlo.spice` includes it, which no section
this project reaches; the tree is 36 files / 245 606 lines and it is not among
them). And `typical.spice` is real but MINOR: 8909 named parameters of which
the library references **86**, and dropping the other 8823 is worth **1.48x**.

**The actual cause (G78): ngspice expands EVERY `.lib` section in a file, not
just the one asked for.** One section parses in **0.093 s**; the real
25-section extended library takes **1.386 s**. The cost scales with the
**section count**, not with what the netlist uses -- so **G58's 5x5 MOS x
passive corner cross product**, a decision about corner COVERAGE, showed up as
a throughput regression nobody could attribute to it. **It survived four
sessions because every previous measurement compared whole libraries against
each other and never a library against ITSELF with one part removed.**

**WHERE THE TIME WENT, additive, five arms each differing from its neighbour
in exactly one thing:**

        0.216 s  floor: ideal R/C netlist on the nfet-only library
      + 0.000 s  the passive model cards       (indistinguishable from zero)
      + 0.012 s  DRAWING the passives                          (0.5 %)
      = 0.222 s  a real evaluation TODAY
      + 1.733 s  the 24 sections the run never uses            ( 65 %)
      + 0.932 s  the R/C parameter decks                       ( 35 %)
      = 2.887 s  what an evaluation cost before this session

**TWO RESULTS THAT WERE NOT THE QUESTION AND MATTER MORE THAN THE ANSWER.**
**Drawing the passives is FREE** -- 0.012 s on a 0.222 s evaluation.
`PASSIVES.md` §3.2 called the extended library's cost "the price of drawing the
passives"; **it was never the passives**, and nothing about emitting the
framework's output as a real schematic is expensive. **The passive model cards
are free too** (measured -0.007 s, i.e. noise on a ~0.09 s spread; read as
zero, not as a negative cost). **100 % of the overhead was library parsing**,
and both terms are now fixed.

**THE GATE, and G36's precedent applied without softening.** Bit-identical
means rel = 0, abs = 0 on the **raw printed text**, not floats parsed first.
`test_pdk_trim.py` (22 fast + 2 `slow`) probes every device the netlists use
through untrimmed and trimmed libraries, re-derives all forty generated files
byte for byte on every run, and carries **three deliberate falsifications**:
a dropped kept parameter, an edited process constant in a copied R/C deck
(`crpf_precision`), and an undefined-parameter run.

**A G26 INSIDE THE G26 GUARD.** Building this found that
`crosscheck.scan_for_silent_failures` **missed ngspice's own fatal error**:
`Undefined parameter [cm3d]` was not in the pattern list, and
`ERROR: fatal error in ngspice, exit(1)` missed `^\s*Error[:,]` **on case** --
the pattern was anchored case-sensitively and ngspice shouts. **The
equivalence probe was reading a run that had ABORTED and comparing empty
result sets, which compare equal.** Fixed, with a test carrying the verbatim
output. Worth knowing on its own: **a `.model` card whose parameters are
undefined is accepted in SILENCE until something instantiates it, and is FATAL
the moment something does.**

**A CONTROL ARM THAT WAS SILENTLY RUNNING THE TREATMENT (G77).**
`lib_for_device` takes the one-section fast path **whenever the file exists**,
by design and without saying so. So `lib_cost.py`'s "before" arm, which swapped
only `CTLE_LIB`, was still served the SPLIT library -- the benchmark would have
reported the improvement as its own baseline. **Live for one run before being
caught.** `_no_section_libraries()` points `pdk_trim.SECTION_DIR` at an empty
directory so the real fallback branch runs. **If a lookup has a silent fast
path, an A/B that swaps the slow input must disable the fast path too.**

Timing discipline was G71's in full -- discarded warm-up, arm order re-shuffled
**per design**, control re-run last: **2.740 s against a first pass of
2.887 s, ratio 1.05x, clean.** Outside [0.8, 1.25] the numbers would be void,
not adjusted.

**WHAT THIS DOES NOT LICENSE.** It is a **single-process** ratio.
`baselines.SEC_PER_SIM_AT_8` is a PARALLEL constant (1.698 s) and G75 is the
standing warning that isolated speed-ups do not transfer -- session 17's 2.98x
became 1.80x on the benchmark's own task mix. **Re-measure with `--pilot`; do
not divide.** Left open in `LIB_COST.md` §8, along with correcting
`PASSIVES.md` §3.2 and G70 in place, since their text is wrong rather than
merely superseded.

New gotchas **G77** and **G78**. **1292 -> 1314 green** (+22
`test_pdk_trim.py`; +2 more marked `slow`).

### 2026-08-17 - Session 19b (two orientation documents; no code change)

**`decisions.md` and `flow.md` are new**, at the repository root, written for
the owner to hand to a supervisor or a teammate. Neither is a contract --
both say so in their first line, and both defer to `HANDOFF.md` and
`CLAUDEwa.md` where they disagree.

* **`flow.md`** -- the pipeline, layer by layer, with the state of every arrow
  marked. The one that matters: `DeviceResult -> LinkResult` is **MOCK end to
  end**, which is gate G2 and the gap against the competition's own wording
  ("outputs the final schematic and resulting specs"). It also carries the
  single-evaluation walkthrough (13 steps, with the G2 insertion point marked),
  the experiment protocol, the gate table, and a section on **what is in the
  working tree uncommitted**, because session 19a's library trim is mid-flight.
* **`decisions.md`** -- 80-odd decisions with the reasoning for each, grouped
  framing / spec-reading / method / device / toolchain / link / RL / benchmark,
  plus two sections the rest of the repo does not collect in one place: **§I,
  the eight retractions** (R1 is G40's falsified central argument; R6 is
  session 19a's finding that the standing explanation for the extended
  library's cost was wrong in both halves), and **§J, the eight decisions still
  waiting on a human** (rule 6).

**Neither file introduces a number.** Every figure in both is quoted from
`HANDOFF.md`, `CLAUDEwa.md` or a `nebula/*.md` write-up, with the source named
(rule 1: nothing traceless).

Nothing executable changed. Suite verified before and after: **1314 passed,
11 deselected, 676 s** (`python -m pytest tests nebula/tests -q -m "not slow"`).
Note that is **1314, not 18d's 1292** -- the difference is session 19a's
UNCOMMITTED `test_pdk_trim.py` and trimmed-library tests, which are green. Note
also that **`CLAUDE.md` is stale on this**: it says 407 tests and 2 deselected.

### 2026-08-17 - Session 20 (a gm/I_D table and a design-space map: the idea's benefit is real, its stated mechanism is not)

**A teammate's proposal, analysed and then built:** search in DESIGN
coordinates `(gm/I_D, L, I, f_z, k, R_L, VCM)` instead of device coordinates
`(W, L, I, R_s, C_s, R_L, VCM)`, on two measured grounds -- **G44 was 159 of
203 invalid evaluations (78.3 %)** and **the seven device axes differ in
strength by 21x** with `rs` acting 4-10x harder on peaking than `w_in`/`l_in`.
Both citations verified exact against `RL_SMOKE.md` §§4-5 before any code was
written.

**IT FITS THE BRIEF** -- the problem statement asks for a framework that "sizes
devices using fewer search spaces (lowest design time)", which is literally a
reparameterization, and gm/I_D is the methodology the judging panel uses
professionally. **So it was built, measured, and the measurement disagrees with
the argument for it.** Full write-up `nebula/GMID_MAP.md`; read §0 and §8.

**THE HEADLINE IS A MISS ON THE STATED MECHANISM.** The hypothesis was that
making `f_z` a coordinate would put the sweep-edge region out of reach by
construction. Two arms, 1500 LHS samples each, same sampler, same evaluator,
TT/27, `cl_mid`, drawn passives and a real mirror throughout:

        G44 as a share of designs that REACHED the simulator
            device coordinates  38.07 %
            design coordinates  37.74 %      <- unchanged

The reparameterization does not make the bad region less reachable. What it
does do is reject **89.40 %** of proposals before spending a simulation -- but
**878 of those 1341 rejections (65 %) are `current_unreachable`**, i.e. the
request is not representable in the device box at all, which is not a physics
screen. Net effect on what a search actually pays: **1.90 -> 1.64 simulations
per valid design, 1.16x.** Real, and small.

**THE PRE-SIMULATION G44 FILTER DOES NOT WORK, AND FINDING OUT WHY IS THE MOST
TRANSFERABLE PART (G82).** Against SPICE the analytic peak condition scored
**TN = 0** -- it never once correctly excluded a design. The cause is that the
closed form and the guard ask different questions: a design peaking at 37 GHz
has a *genuine* interior peak and still trips `peak_is_sweep_edge`, because
`meas ac MAX` only searches to 20 GHz and inside that window the response is
monotonically rising. Adding the ceiling took TN 0 -> 8 and FP 60 -> 52; **the
other 52 are model error** (G66, G67, and the 1z/2p model's own 4.25 %). The
lesson generalises: **read TN on any pre-simulation filter, not accuracy** -- a
filter with TN = 0 has saved zero simulations however accurate it looks.

**WHAT THE MAP DOES GET RIGHT.** `f_z` and `k` round-trip through the geometry
algebraically (rel < 1e-9), and the DC gain lands at a median **-0.20 dB**
against SPICE -- inside CLAUDEwa.md §6's own 1 dB gate, which says the bias
solve and the body-effect term both work. `f_peak` is over-predicted by a
median **0.355 octaves (28 %)**, worse than the pre-screen's 15.85 % at
benchmark conditions, in the direction G60 predicts. **Re-running the design
arm at `k_alpha = 0.90` confirms the mechanism and exposes a trade** the
project had not previously quantified: peaking bias **-0.816 -> -0.157 dB** (5x
better) while `g_dc` goes **-0.181 -> -0.663 dB** (3.7x worse), because
`A_dc = gm*R_L/k` and both read the same `k`.

**THREE PDK FINDINGS THAT OUTLIVE THE EXPERIMENT, all new gotchas.**
**G79: the gm/I_D method's central premise is false on SKY130 at fixed `nf`** --
`I_D/W` moves **1.56x across the `w_in` box** because W/nf sweeps the model
bins (G53's axis), so the textbook linear-in-W scaling is a **56 % width
error**, smoothly and monotonically, on a device that simulates happily. `W`
had to become a real LUT axis. **G80: you write MICRONS and read back METRES**
-- a geometry read-back written the obvious way fails by 1e6 on a correct
circuit, G31 with the sign reversed. **G81: SKY130 refuses an out-of-bin WIDTH
and silently EXTRAPOLATES an out-of-bin LENGTH** -- `L = 99 um` simulates and
scales as a clean 1/L, so on the L axis the map's refusal to extrapolate is the
only guard there is.

**SCOPE HELD.** `common/params.py`, `rl/contract.py` and `rl/env.py` are
**untouched** (rules 5 and 6), verified by diff. Nothing is wired into the RL
loop. Adopting this would invalidate the 8.73 % random-search baseline, the
+8.950669 ceiling and every benchmark arm, so it is a human decision -- and
§8's recommendation is **not to adopt before G2**, with the one argument on the
other side stated plainly: the baselines sweep has not run, so **now is the
only moment the change would be free**.

**Also this session:** the gm/I_D table was nearly lost to G49 -- `*.npz` is
gitignored (the rule exists for `ams_rl_ppo`'s shipped checkpoints), so it
needed an explicit narrow un-ignore, the same treatment the trimmed library
gets. And a **numbering note** was added to §9: two entries are both numbered
G73, left alone deliberately because other files cite it; and **G77/G78 are
referenced in code but not yet written into §9** -- they belong to session
19a's uncommitted library trim, so session 20 starts at G79 rather than
reusing them.

**AND A GATE FIRED ON THIS SESSION'S OWN WORK, which is worth recording
because it is the system behaving correctly.** The full-suite run came back
**1 failed, 1388 passed** -- `test_markdown_mentions_are_confined_to_the_
historical_record`, G62's grep for the retired `CHANNEL_DC_LOSS_DB`. The
offender was **session 19b's `decisions.md`**, whose §F1 entry documents the
decision to delete that constant. That is precisely the case the test's own
comment exempts ("the name may appear in write-ups that RETIRE it"), so the
ALLOWLIST was extended rather than the text reworded, with the reason written
into the test. Noted here rather than quietly fixed: extending an allowlist to
make a test pass is a move that deserves to be visible.

**Artifacts:** `nebula/device/gmid_lut.py`, `nebula/common/design_space.py`,
`nebula/experiments/exp_gmid_validation.py`, `nebula/GMID_MAP.md`,
`nebula/device/data/gmid_lut_sky130_nfet01v8.npz` (27.6 MB, tracked),
`gmid_validation_run.jsonl` + `gmid_validation_kalpha090.jsonl` (tracked).
Cost: 3000 sweeps / 510 s for the table, 1659 + 151 SPICE invocations for the
experiment.

### 2026-08-17 - Session 21 (G2: the loop is closed, and the first thing it revealed is that compression binds)

**GATE G2 IS PASSED, three days before its 20 Aug date.** One parameter vector
produces a drawn SKY130 schematic that meets **every one of S3-S8 at TT**, with
no mock anywhere in the path. Full write-up `nebula/G2_RESULTS.md`; read §0
and §7.

**"THE LINK LAYER IS A MOCK END TO END" OVERSTATED THE GAP, and the two things
genuinely missing were both structural rather than large.** `link/channel.py`,
`link/tx.py`, `link/cursors.py` and `link/calibration.py` were all real, tested
and had already produced published results. What did not exist:

1. **Nothing in the repo had ever CONSTRUCTED a `DeviceResult`.**
   `device/mock.py` was the only constructor; `sky130_runner` produced a
   `Sky130Point` and stopped. **So the real device layer and the real link
   layer had never been connected by anything** -- which is why the mock was
   the only way to exercise the bridge, and why G16 read as "the link layer is
   fake" when the truth was "the two halves were never joined".
2. **The AC sweep was measured and thrown away.** `ac dec 50 1meg 100g` has
   always run, but only four `meas` scalars were parsed off it, and **a
   pole-zero fit cannot be made to four numbers.** `DeviceResult` has declared
   `ac_freq_hz`/`ac_mag_db` since the interface freeze for exactly this.

**THE WORKED EXAMPLE, every number measured** (funnel row i=110, the largest
eye among the ten designs meeting both S3 and S8 -- **found by the search, not
hand-picked from outside the box**):

        w_in 38.873 um  l_in 0.18762 um  nf 4  i_bias 3.0787 mA
        rs 697.71  cs 1.0134 p  rl 653.11  vcm 1.18384
        -> Rs res_high_po w=10 l=20.69 | Cs cap_mim_m3_1 22.345^2
           RL res_high_po w=10 l=19.285 | tail W=171 um 1:8 mirror

        S3  9.667 dB @ 2.1878 GHz   (3-12 dB, 1.25-2.5 GHz)   PASS
        S4  -61.10 dBc @ 100 MHz    (< -30 dBc)               PASS
        S5  0.2897 mV_rms           (< 1.5 mV)                PASS
        S6  5.289 mW  measured      (< 15 mW)                 PASS
        S7  0.001092 mm^2 passives  (< 0.05 mm^2)             PASS (2.2 %)
        S8  758.11 mV x 0.8750 UI   (> 100 mV, > 0.4 UI)      PASS
        fit residual 0.0222 dB      (gate 0.5 dB)             PASS

**THE FUNNEL IS THE ACTUAL RESULT: COMPRESSION BINDS, NOT THE EYE.** 300 LHS
samples of the approved box, TT, drawn passives, real mirror, 12 dB channel,
161 s: 300 simulated, **276 fit (92 %)**, **26 meet S3 (8.67 %)**, and then
**168 of the 276 fitted designs -- 61 % -- are REJECTED because the
small-signal model no longer applies at the link's own drive level.** The
median design overshoots its measured linear limit by **1.29x** (p90 3.02, max
7.77). Ten designs meet S3 and S8 together.

**S8 IS CONFIRMED NON-BINDING, now by measurement through real silicon:** 82 of
the 108 designs whose small-signal model holds meet S8 (**76 %**), and all ten
S3-compliant valid designs have an open eye. `CHANNEL_MODEL.md` §5 predicted
this from a pulse response with no transistors in it -- *"S8 vertical is not
binding and never has been"* -- so **two independent paths now agree**. The
compression finding likewise reproduces `CHANNEL_MODEL.md` §6's "compression
binds at 5 of 7 loss points" from transistor-level silicon instead.

**THE FIDELITY-TIER TABLE, which is the other half of G2's criterion** (min
estimator, 21 interleaved shuffled repeats):

        .op + .ac + .noise          0.1768 s
        + AC curve dump             0.2047 s   (+0.0279)
        + .dc swing sweep           0.2257 s   (+0.0210)
        + HD3 transient + FFT       0.2787 s   (+0.0530)
        pole-zero fit               0.0114 s   no simulator
        link eval (pulse->eye)      0.0372 s   no simulator

A full-fidelity evaluation is **0.279 s**; before session 19a's trim an
AC-ONLY one cost 2.887 s. **The transient is CHEAP** -- +1.23x, against
`s9_yield.py`'s recorded "~4x the cost of AC+noise" and G0's 175x spread. Those
were measured when library PARSING dominated; the trim made the analyses
themselves visible.

**G71 FIRED ON THIS SESSION'S OWN MEASUREMENT OF ITS OWN GATE CRITERION.** Run
tier-by-tier with a per-tier warm-up, the table came out with `.op+.ac+.noise`
at 0.3841 s and `+ac_curve` at 0.3138 s -- **a NEGATIVE increment for strictly
more work**, because whichever tier goes first pays the process-level cache
warming. Fixed with the full protocol: interleaved, order re-shuffled every
repeat. And **the MINIMUM is the estimator the increments are read from**, with
the reason stated: process-launch noise is additive and one-sided, so the min
estimates the work while the median carries contention. Both are reported and
they agree on every ordering.

**FOUR MORE FAILURES FOUND AND FIXED, three of them mine.** **`linearize` takes
VECTOR NAMES, not a timestep** -- `linearize 1e-10` prints
`Error: no such vector 1e-10`, **destroys the plot** so every later line in the
block fails too, and ngspice still exits normally. G26 in a new place.
**My missing-file check ran BEFORE `scan_for_silent_failures`**, so it reported
"wrote no hd3.txt" (the symptom) while the real message sat unread in the
output (the cause) -- G68's ordering, violated by the person who had just cited
it. **My FFT window was 20.01 cycles, not 20**: `tran` yields an INCLUSIVE
grid, so 20 cycles at 100 points/cycle arrives as 2001 samples whose first and
last are the same phase; the duplicate endpoint has to be dropped or the window
is not periodic and leaks. Caught by the integer-cycle check on the first real
run. And **the compression gate initially rejected the MOST LINEAR designs**:
`measured_swing_pp_v` returns `None` when the sweep never reaches 1 dB
compression, which `SwingLimits` documents as *"information, not a failure"*,
and reading it as unknown failed every `rs >= 400` sizing in the box.

**S8 IS WIRED INTO THE REWARD AS `V2_SPECS`, AND `V1_SPECS` IS UNTOUCHED.**
Adding two rows changes `len(specs)`, hence `B = N + 1`, hence **every reward
number this project has published** -- including the **+8.950669** ceiling
(G74), which is a property of the spec set rather than of the circuit.
`BASELINES.md` §7f forbids moving that without re-running every baseline, so v2
is opt-in until a human decides to. 88 reward tests pass unchanged, and
`feasible_bonus(len(V1_SPECS))` is still exactly 8.0. `margins()` OMITS the S8
rows without a link result rather than defaulting them, so `V2_SPECS` without
an eye raises rather than scoring a missing eye as satisfied.

**Scope note:** `ac_sweep` and `hd3` both default **OFF**, so the netlist stays
byte-identical to the one every published number came from, and
`test_ac_sweep_capture_changes_no_measured_value` compares 17 parsed fields
across both settings at **rel = 0, abs = 0**. `common/params.py`,
`rl/contract.py` and `rl/env.py` are untouched.

**AND ADDING THOSE TWO FLAGS BROKE SEVEN TESTS THAT NOBODY WOULD HAVE
PREDICTED (G87).** Three new `str.format` placeholders in the shared netlist
template meant five `test_tail.py` tests and two `test_tunable.py` tests failed
with a bare `KeyError: 'tran_src'`, because they assemble the deck directly.
Fixed by routing every caller through `assemble_netlist()`, which is now the
single place that knows the optional fields -- so the next block added does not
have to find every caller again.

**And one of MY OWN new tests then went red on a pure rewording**, which is
worth recording as its own small lesson: `test_asking_for_the_sweep_and_not_
getting_it_is_a_FAILURE` asserted `"no ac.txt" in fail_reason`, and the G68
ordering fix inserted the word "readable". **A test that pins prose rather than
behaviour will go red for the right change.** It now asserts the stable half --
that the flag was asked for and the file is what is missing.

**Artifacts:** `nebula/link/fit.py`, `nebula/link/bridge.py`,
`nebula/experiments/exp_g2_closed_loop.py`, `nebula/G2_RESULTS.md`,
`g2_closed_loop_run.jsonl` (tracked), `nebula/tests/test_link_fit.py` (30),
`nebula/tests/test_link_bridge.py` (26), plus HD3 + AC-capture + area additions
to `sky130_runner.py`, `passives.py`, `cursors.py` and `reward_v1.py`.

**1389 -> 1448 green** (+59: `test_link_fit.py` 30, `test_link_bridge.py` 26,
three AC-capture tests in `test_sky130_runner.py`), 11 deselected, 218 s.

### 2026-08-17 - Session 21b (PLAN.md: the team's operating plan; no code change)

**`PLAN.md` is new**, at the repository root, written because the project now
has THREE PEOPLE working in parallel rather than one agent working serially,
and `nebula/NEXT_STEPS.md` was written for the latter.

What it carries that nothing else does:

* **Three lanes with one-line jobs** -- RL (owns G3), analog (owns G4 and the
  design decisions), delivery (owns the report, the demo and the schedule) --
  and the single hard dependency between them, deliberately placed first so it
  never blocks anything.
* **Seven decisions with OWNERS and DEADLINES**, each with a recommended
  answer and its reasoning, so the team is deciding rather than starting from
  blank. D1 (compression) is the one that blocks the sweep and therefore G3.
* **A hard stop on G3 tuning at Day 14.** The largest schedule risk is not
  technical -- it is G3 becoming a tuning rabbit hole. `CLAUDEwa.md` §7 already
  says a measured negative result is an acceptable answer; this puts a date on
  taking it.
* **The cut order**, and what may never be cut (G4 and the report).

**Relationship to `NEXT_STEPS.md`, stated in both directions:** that file's
steps 1 and 3 are DONE (the library trim, session 19a; the closed loop,
session 21). Its remaining steps are folded into the phases. Its per-step
PROMPTS are still useful and are not superseded.

Nothing executable changed. **1448 green, unchanged.**

### 2026-08-18 - Session 22 (task 0: the difficulty of the problem the G3 sweep will run -- PRE-REGISTERED, NOT YET RUN)

**This commit contains no result.** It contains the experiment, its tests, and
a prediction committed **before** the experiment ran (PLAN.md §7 rule 6). The
result lands in the next commit, whatever it says.

**The question.** `PLAN.md` §3's G3 sweep is specified and costed at ~12 h and
has never been run. Three already-measured numbers -- random LHS meets S3 at
**13.44 %** (`BASELINES.md` §5 / D4), the reward **saturates at +8.950669**
(G74), one evaluation costs **0.28 s** (`G2_RESULTS.md` §3) -- together suggest
the sweep may be arithmetically incapable of separating its arms, because every
arm would tie at the ceiling and `BASELINES.md`'s own CI-overlap rule then
forbids reporting a ranking. **Measure it before spending 12 hours on it.**

**New:** `nebula/experiments/exp_difficulty.py`, `nebula/tests/test_exp_difficulty.py` (15).
**Pre-registration:** `nebula/PREDICTIONS.md` entry 7, with the decision rule
(`< 50` simulations to ceiling in either arm -> the thesis holds; `> 500` in
every arm -> it fails; in between -> stop and let a human decide) encoded in
`decide()` so the verdict is read off the data rather than argued after it.

**Nothing about the problem definition changed** -- same box
(`rl.contract.ACTION_SPACE`), same sampler (`baselines._lhs`), same evaluator,
same reward (`V1_SPECS`), same rung (P1: TT / 1.00 / 27 C / `cl_mid`, drawn
passives). `params.py`, `contract.py`, `env.py`, `V1_SPECS` **untouched**.
`test_the_restart_loop_matches_method_lhs_exactly` is the gate on that claim:
it asserts this module's loop emits the identical `u` sequence
`baselines.method_lhs` does from the same seed.

**One real defect found while building it, and it is now G88:** a simulation
budget does not terminate a pre-screened arm. A screened rejection costs zero
simulations *by design*, so an arm whose screen rejects everything never
advances `n_sims` and loops forever at full CPU. Found by the test suite
hanging for 400 s on `test_a_screened_out_proposal_costs_zero_simulations`.
`run_restart`/`run_pool` now carry a proposal cap and **log `proposal_cap_hit`**,
so hitting it is distinguishable from a run that searched properly and found
nothing.

**Five gates were deliberately broken and watched go red** before being put
back (PLAN.md §7 rule 3): the LHS-equivalence gate (block size `n` -> `n+1`),
the no-substitution gate (budget written over a censored `None`), the
decision-rule gate (`DECISION_LO` 50 -> 5), the 90 %-band gate (`alpha` dropped,
falling back to the helper's 95 %), and the ceiling-tolerance gate
(`CEILING_TOL` 1e-6 -> 1e-3). The sixth -- removing the proposal cap -- **hangs
rather than failing**, which is exactly why the flag is logged.

**Measured while sizing the run, quoted here because it is the only number in
this commit:** the evaluator costs **0.2537 s/sim** on a cold cache and
**0.1665 s/sim** warm, serial, on this machine today, against
`G2_RESULTS.md`'s 0.2787 s at full fidelity (this tier omits the `.dc` swing
and the HD3 transient). G71's ordering effect is visible in the gap between
those two and neither is quoted as *the* cost.

**Tests 1448 -> 1463 green.**

### 2026-08-18 - Session 22b (task 0 RESULT: the sweep's metric does NOT saturate at its own budget, and D4's baseline does not reproduce)

**Verdict `IN_BETWEEN`, so the pre-registered rule says STOP and the decision is
a human's.** Full write-up `nebula/DIFFICULTY.md`; outcome scored into
`PREDICTIONS.md` entry 7 (six hits, two misses); figure
`nebula/figures/difficulty.png`; data `experiments/difficulty_run.jsonl`.

**The thesis splits in half and the halves point opposite ways.** *"S3 is
trivial"* is CONFIRMED -- median **7.5** simulations to a first S3-meeting
design unscreened, **3.0** screened. *"Random search reaches the ceiling in
single-digit samples"* is FALSIFIED by ~30x -- median **221** unscreened
(90 % CI [142, 315], 22/24 reached, 2 censored at 600) and **68.5** screened
(CI [42, 117], 24/24).

**THE HEADLINE RUNS AGAINST THE BRIEF'S CONCLUSION.** The sweep's per-run budget
is 150 simulations (`baselines.BUDGET_SIMS`), and only **8 of 24 unscreened
restarts (33 %)** reach the ceiling inside it, against 18 of 24 (75 %) screened.
So best-reward-at-budget is **still a live discriminator** in the unscreened
arms and "every arm ties at the ceiling, nothing separable" is not what the
arithmetic says. `BASELINES.md` §3 introduced simulations-to-ceiling *because*
saturation was expected; both metrics are now worth reporting and neither is
redundant.

**`PLAN.md` D4's RECOMMENDED BASELINE DOES NOT REPRODUCE** (a pre-registered
falsification condition, fired). Measured S3 rate over 2000 simulations of the
sweep's own sampler, evaluator and box: **7.10 %**, 95 % Wilson
**[6.05, 8.31] %** -- and **13.44 % is outside that interval**. The 13.44 %
figure is `robust_geometry_data.csv`, a session-11 population. Four measured
candidates now exist (7.10 / 13.44 / 13.54 / 8.73 %) and they are not the same
measurement. **D4 is a human decision and nothing here adopts one.**

**THE OTHER FOUR V1 SPECS NEVER BIND.** Simulations-to-first-feasible equals
simulations-to-first-S3 **exactly** (7.5 and 3.0) and the pooled feasible rate
equals the pooled S3 rate **to the digit** in both arms (7.10 %, 25.55 %). So
reward v1's seven-row feasibility is no harder than the S3 rate everyone
quotes, which settles `PREDICTIONS.md` entry 6's falsification condition 3 in
the opposite direction to the worry it was written about.

**G74 reconfirmed at 2.8x the evidence:** 9 ceiling ties on **9 distinct**
designs unscreened and 16 on **16 distinct** screened -- 25 designs, 25 ids,
one reward to six decimals, and nothing in 4000 simulations above it.

**A NEW SUSPICION, RECORDED AS SUSPICION (G89).** The screen lifts the S3 rate
**3.60x** but the ceiling rate only **1.78x**. Per proposal the ceiling rate is
0.4500 % unscreened against 0.2408 % screened -- rate ratio 0.535, **95 % CI
[0.236, 1.211]**, i.e. a point estimate of **46.5 % false rejection on the
CEILING population** whose interval spans 1.0. It agrees with an independent
route (the "S3 rate / 15" lattice arithmetic predicts the unscreened ceiling
rate to 5 % and misses the screened one by 2.1x) and it is the failure mode G76
already caught this screen in once. **Not established** -- 9 and 16 events.
Confirming it costs one pooled re-run and no new code.

**Cost, all serial with nothing else simulating (G70):** 8394 simulations,
3222 s. 0.2629 s/sim unscreened restarts, 0.2800 s/sim screened, against a
0.2537 s/sim cold probe and a 0.1665 s/sim warm smoke test (the spread is G71).

**A G70 VIOLATION HAPPENED AND IS IN THE RECORD.** The first launch was wrapped
in a `timeout` that would have killed the run mid-flight; stopping it killed the
shell but **not its Python child**, and a second run started alongside the first
-- two concurrent ngspice drivers writing one log. Both killed by PID, the
contaminated log deleted, the machine verified idle, the run restarted from
scratch. **No published number comes from those runs.** Generalise: killing a
task runner is not killing the process it started; check `ps` before restarting
a SPICE experiment.

**`params.py`, `contract.py`, `env.py`, `V1_SPECS`, the box, the tolerances and
the pre-screen are all UNTOUCHED.** Tests **1463 green**, unchanged.

### 2026-08-18 - Session 22c (D4 decided; the attribution and the G89 confirmation, PRE-REGISTERED and NOT YET RUN)

**Decisions the owner made in the session-22 review, recorded so they are not
re-litigated:**

* **D4 is DECIDED: the baseline is 7.10 %**, the rate measured under the
  sampler, evaluator and box the sweep will actually use (n = 2000, 95 % Wilson
  [6.05, 8.31]). Reason: a baseline the current pipeline cannot reproduce is
  indefensible in a report. **`PLAN.md` sec 2's recommended 13.44 % is
  superseded.**
* **Task order: Task 1 (remove the reward ceiling) BEFORE Task 3 (corners)** --
  not for separability, which task 0 showed mostly does not need it, but
  because (a) **75 % of SCREENED runs reach the ceiling inside the
  150-simulation budget**, so those arms saturate and become unrankable, and
  (b) a plateau of 9-16 designs at exactly the top is the objective shape where
  PPO gets no gradient near the optimum, which `PLAN.md` sec 4 tells lane A to
  check for before touching hyperparameters. In Task 3, **scope the G66 screen
  re-run FIRST, not last.**
* **G88's accounting is a DECISION, not just a bug.** If screened rejections
  cost nothing in the cost metric, the screened arm gets unlimited proposals
  per simulation and its efficiency is inflated by an unbounded factor.
  **Whether the screen's analytic evaluations are charged, and at what rate, is
  a Task 2 fairness item and must be written into `FAIRNESS.md` BEFORE the
  sweep.** It applies to `baselines.py` as well as to `exp_difficulty.py`.

**The finding session 22's report under-weighted, now promoted:**
**median-to-first-feasible is IDENTICAL to median-to-first-S3** -- not close,
identical, in both arms (7.5 and 3.0), with the pooled rates equal to the digit
(7.10 %, 25.55 %). **Reward v1 has ONE active dimension where it advertises
seven.** So the sweep is not measuring a seven-constraint search; it is
measuring margin-maximisation on one row against a lattice-quantised `f_peak`.
Consistent with G74, but measured as a WAITING TIME rather than inferred. It is
also the strongest argument yet for the corner axis, which adds binding
constraints nominal does not have.

**Two things established with NO SIMULATION, by re-scoring
`robust_geometry_data.csv` (in `exp_attribution.definition_report`):**

1. **The definition explains NONE of the 13.44 -> 7.10 % gap.**
   `prescreen.s3_true` (2 rows) = **13.44 %**; `reward_v1.V0_SPECS` (3 rows,
   adding `S3_nyq_boost`) = **13.44 %**; zero designs die to the Nyquist row.
   The 7-row `V1_SPECS` rate on that population is **13.39 %**, which
   reproduces the one-active-dimension finding on a DIFFERENT population with
   ideal passives and an ideal tail.
2. **THE 13.44 % POPULATION IS AT `cl` = 150 fF, THE LEGACY PIN -- NOT
   `cl_mid`.** Read off the file, every row, ratio **4.598x**. `PLAN.md` D4
   calls 13.44 % "the measured rate at `cl_mid`" and `BASELINES.md` sec 2's
   ladder table puts it on the `cl_mid` row. **Both are wrong.** The
   consequence is sharper than a mislabel: D4 rejects 13.54 % because it was
   "`cl` pinned at a load the next stage cannot present", and 13.44 % was
   measured at **that same load** -- so the stated discriminator between the
   recommended number and its rejected alternative does not exist. Corrected in
   `BASELINES.md` and `PLAN.md` in the same commit as the run.

**New:** `nebula/experiments/exp_attribution.py`,
`nebula/tests/test_exp_attribution.py` (11), plus `--more-pools` / `--ratio` on
`exp_difficulty.py` and 4 more tests there. Pre-registration:
`PREDICTIONS.md` entry 8, committed BEFORE either run.

**A default-preserving change to the evaluator, and why it is safe.**
`build_point`/`evaluate` now take `real_tail` / `real_passives`, **defaulting
to the published configuration**. They exist solely for the attribution arms.
`test_build_point_defaults_are_byte_identical_to_the_published_path` compares
every parsed field at **rel=0, abs=0** between no-flags and explicit-True, the
same gate session 21 used for `ac_sweep` -- so `BASELINES.md` sec 7f's
"touching the evaluator means re-running every baseline" is not triggered.

**G90 (new): the mirror axis CANNOT be measured through the current evaluator,
and finding that out cost a run.** `validate` requires `vds_tail`/`vdsat_tail`,
which ideal current sinks never produce, so every ideal-tail design returns
`invalid: vds_tail is missing from the ngspice output` rather than a
measurement. So the 4th candidate cause of the D4 gap (session 13's 4-8 %
mirror deficit) is **blocked pending a human decision about what `validate`
treats as a failure**. Recorded in `exp_attribution.TAIL_AXIS_BLOCKED` and
pinned by a test that RUNS one and reads the reason, so a docstring cannot
drift from the code.

**Two of my own bugs, both caught by the gates:**
(a) `evaluate` dereferenced `geo.rs` unconditionally, so `real_passives=False`
raised `AttributeError` instead of returning a result -- found because the
byte-identical gate failed **for the wrong reason** (G68/G86's rule, again).
The realised-passive rows are now ABSENT rather than defaulted when no device
was drawn, because a `0.0` quantisation error for an element that was never
drawn reads as a perfectly drawn device (G85's shape).
(b) `pytest.approx` carries a default **abs=1e-12**, so
`150 fF != approx(32.63 fF)` is FALSE and a test asserting the two loads differ
passed vacuously. Every capacitance in this project is femtofarads. **Compare
femtofarad quantities by RATIO, never by bare `approx`.** (G91.)

**Tests 1463 -> 1480 green.** `params.py`, `contract.py`, `env.py`,
`V1_SPECS`, the box, the tolerances and the pre-screen all untouched.

### 2026-08-18 - Session 22d (the attribution lands, and G89 is KILLED by its own confirmation run)

Both runs from session 22c, executed serially on an idle machine (G70).
Pre-registration `PREDICTIONS.md` entry 8, committed at `b6fe85e` before either.
**Scored: A hit, B miss, C miss.**

**THE D4 GAP IS ATTRIBUTED, AND THE MECHANISM IS NOT WHAT THE HEADLINE NUMBER
SUGGESTS.** Full write-up `nebula/ATTRIBUTION.md`.

        cause                        worth      how
        S3 definition (2 vs 3 rows)  +0.00 pts  re-scoring, NO simulation
        load, cl 32.63 -> 150 fF     +4.47 pts  one arm, 1500 sims
        drawn passives (G66)         +0.33 pts  one arm, not significant
        real mirror                  BLOCKED    G90
        residual                     ~2.04 pts  named, not apportioned

**The load is the cause, but NOT because the box is better at 150 fF.** The S3
rate among designs that are **scorable at all** is **13.94 / 13.91 / 14.16 %**
across all three arms -- flat. What the load changes is the **G44 population**:
**40.13 % sweep-edge invalid at `cl_mid` against 8.67 % at 150 fF**. At the
lighter load `f_p2` moves up and two fifths of the box has no interior maximum
below the 20 GHz search ceiling. **The published baseline was measuring a box
less of which is wasted, not a box that designs better.** Two consequences:
this explains the pre-screen's 3.60x lift here against the published 2.60x
(more G44 population available to remove at `cl_mid`), and **G65's "78 % of
what a policy finds is G44" is a property of the LOAD as much as of the policy**.

**Drawn passives cost nothing measurable (6.93 % vs 6.60 %, CIs overlapping),
and that does NOT contradict G66.** G66 is a **per-design** 0.1329-octave shift
that moves designs both into and out of the window; a population rate is the
wrong instrument for it. G66's claim about design 432's 0.12 octaves of slack
is untouched. **My prediction B was wrong because I used a rate to test a
per-design effect** -- the pre-registration named this exact case in advance.

**G89 IS KILLED, AND THE WAY IT SURVIVED A DAY IS THE LESSON.** The
confirmation run doubled the events and the rate ratio moved **0.535 -> 0.917**
(unscreened 14/4000 = 0.3500 %, screened 43/13391 = 0.3211 %, CI
[0.502, 1.677], implied false rejection **8.3 %**). Both arms regressed to the
mean from opposite directions (9 -> 5 and 16 -> 27). **The screened arms of the
G3 sweep carry no known ceiling bias**, which is `PREDICTIONS.md` entry 8's
falsification condition 4 firing verbatim, and it is the outcome that saves the
12-hour run from a caveat.
**The methodological error was mine and it is now the body of G89:** I wrote
the suspicion up as having *"two independent supports"* -- the direct rate
ratio, and the lattice arithmetic `ceiling = S3/15` missing the screened arm by
2.1x. **They are not independent; both are computed from the same 9 and 16
counts.** On the pooled data the arithmetic over-predicts by 1.36x unscreened
and 1.56x screened -- uniform, no arm-specific effect. **Different arithmetic
on the same small sample is not a second measurement.** `DIFFICULTY.md` sec 4.2
and sec 4.3 are corrected; the earlier "agrees to 5 %" claim is retracted in
place rather than deleted.

**G74 reconfirmed at 6.4x its original evidence:** pooled over both replicates,
**57 ceiling ties on 57 DISTINCT designs** (14 unscreened, 43 screened), one
reward to six decimals, nothing above it in 8000 simulations.

**Also measured, and it strengthens session 22's promoted finding:** on the
session-11 population the 7-row `V1_SPECS` rate is **13.39 %** against the
3-row **13.44 %** -- so noise, power and the pair-saturation margin cost
**0.05 points between them**, reproducing *"reward v1 has one active dimension
where it advertises seven"* on a **different population**, with ideal passives
and an ideal tail. That finding is now measured twice on disjoint data.

**Cost:** attribution 4500 simulations / 877 s (0.183-0.208 s/sim); pools 4000
simulations / 853 s. All serial, nothing else simulating.

**New:** `nebula/ATTRIBUTION.md`, `experiments/attribution_run.jsonl`,
`experiments/difficulty_pool_r1.jsonl`. **Tests 1480 green, unchanged.**
`params.py`, `contract.py`, `env.py`, `V1_SPECS`, the box, the tolerances and
the pre-screen all untouched.

**Next, per the owner's decision:** Task 1 (interpolate the AC peak to remove
the ceiling), then Task 3 (corners) with the G66 screen re-run scoped first.
The Task 1 case now rests on the screened arms -- **75 % of them reach the
ceiling inside the 150-simulation budget and become unrankable** -- and on the
G3 argument that a 57-design plateau at one value is where a policy gradient
vanishes near the optimum.

### 2026-08-19 - Session 22e (task 1: the interpolated AC peak - CODE + TESTS + PRE-REGISTRATION, NOT YET RUN)

**No measurement in this commit.** It contains the mechanism, its tests, and
`PREDICTIONS.md` entry 9 written before any of the three runs. Split out
deliberately so the predictions are in git history ahead of the numbers, which
is the same shape as session 22's task-0 commit.

**What G74 says, and what task 0 measured about it.** `meas ac g_pk MAX` can
only report frequencies on the `ac dec 50 1meg 100g` lattice -- a grid
**0.0664386 octaves** apart -- and `reward_v1`'s feasible branch is
`B + min_i(margin_i/tol_i)` with `S3_f_peak`'s margin
`0.5 - |log2(f_peak/f_target)|`. The nearest lattice point to the mid-window
target (1.767767 GHz) is **1.737801 GHz, 0.0246654 octaves below**, so the best
attainable score is **8.950669** and it is a property of the SWEEP GRID.
Task 0 then measured the consequence at 6.4x the original evidence:
**57 distinct designs tied at that one value across 8000 simulations, with
nothing above.** A plateau at the optimum is the objective shape a policy
gradient cannot climb.

**The mechanism.** `device/sky130_runner.interpolate_peak_log_f` fits the
parabola through the three samples bracketing the discrete maximum, in
`(log2 f, dB)`, and returns its vertex. **Zero extra simulation:** the curve is
already dumped by `run_point(ac_sweep=True)`, which session 21 proved inert at
rel=0/abs=0. `dec` is NOT raised -- that would be a cost change and it is the
owner's call.

**Everything is opt-in and the default path is provably untouched.**
`run_point(ac_peak_interp=True)` (implies `ac_sweep`) fills NEW fields
`f_pk_interp_hz` / `g_pk_interp_db` / `peak_interp`; `f_pk_hz` and `g_pk_db` are
never written. `evaluate(ac_peak_interp=True)` adds NEW `meas` keys
`f_peak_oct_interp` / `peaking_db_interp` and leaves `f_peak_oct` /
`peaking_db` alone, so `reward_v1(meas)` is bit-identical with the flag on or
off. `Objective(ac_peak_interp=...)` threads it and defaults False. The single
definition of the swapped measurement vector is
`evaluator.meas_with_interpolated_peak` (rule 9) -- both keys move together or
neither does, because a frequency from the parabola beside a magnitude from the
lattice is one peak read in two places.

**The G44 guard, and the asymmetry that is deliberate.**
`Sky130Point.peak_interp_is_sweep_edge` is the interpolated counterpart of
`peak_is_sweep_edge` and RAISES rather than returning False when the
interpolation never ran -- "not asked for" is not an answer to "is this peak
fictitious". A **top**-edge maximum is refused (G44: the response is still
rising, there is no bracketing triple, and an interpolated peak there would be
the same fictitious peak with extra decimals). A **bottom**-edge maximum
carries the lattice pair forward instead, because 10 MHz is both a grid point
AND the boundary, so `meas ac MAX` reported the true maximum of the searched
interval and nothing was rounded. That asymmetry mirrors one this repo already
made on purpose: `validate` rejects the rising case and ACCEPTS the falling one,
and its comment records why -- rejecting the falling case "would erase the
reward gradient over the entire low-peaking region of the box, which is where a
randomly initialised policy starts". Refusing them on the interpolated path
would rebuild that hole one layer up.

**One structural change made for testability, and it is the interesting one.**
The vertex arithmetic lives in its own function `parabolic_vertex(y0, y1, y2)`
because its two refusals -- a non-concave triple, and a vertex outside its own
cell -- are **UNREACHABLE** through `interpolate_peak_log_f`: `np.argmax`
returns the FIRST maximal sample, which forces `y1 > y0` and `y1 >= y2`, hence
`y0 - 2*y1 + y2 < 0` strictly. A guard whose condition cannot be reached is
indistinguishable from a guard that was deleted, so the arithmetic is tested
directly where a flat triple can be handed to it, and the composition is
asserted separately as the invariant it is.

**New constant `MAX_SEARCH_BOT_HZ = 10e6`, and a deliberate rule-9 exception.**
The netlist's `FROM=10meg` stays the definition; turning it into a placeholder
would edit a template every published number came from, for no gain.
`test_the_max_search_window_matches_the_netlist` parses `FROM=`/`TO=` out of the
assembled deck and asserts both constants against it, so either side moving
alone goes red. G32 was a model card that differed between netlist and runner
with no such test.

**Tests: 1480 -> 1504 green** (+23 in `nebula/tests/test_peak_interp.py`, +1 in
`test_baselines.py`). The two G44 tests break the input, watch the guard fire,
put the input back and watch it stop. The two stub evaluators in
`test_baselines.py` / `test_exp_difficulty.py` now name `ac_peak_interp`
explicitly rather than swallowing `**kw`, because a keyword the harness starts
passing and a stub silently absorbs is a threading bug no test can see.

**New:** `nebula/experiments/exp_peak_interp.py` (three sub-experiments: the
300-design G2 funnel replay, a `dec 50` vs `dec 500` validation of whether the
vertex is RIGHT rather than merely finer, and a replay of all four task-0 pools
at the same seeds with `ac_peak_interp=True` as the only difference),
`nebula/tests/test_peak_interp.py`, `PREDICTIONS.md` entry 9.

**Untouched:** `params.py`, `contract.py`, `env.py`, `V1_SPECS`, the
tolerances, the box, the pre-screen, every seed.

**Next:** run the three experiments and write `nebula/PEAK_INTERP.md`. The
headline prediction, pre-registered: **all 57 ties separate, and 28 of them
(half the cell, because the lattice point sits below the target) score ABOVE
8.950669.** Falsification condition 1 is the one that stops the task: if any of
the four pools fails to reproduce its published `n_s3`, `n_at_ceiling` and
`ceiling_design_ids`, the flag is not additive and nothing measured here
extends what it claims to extend.
