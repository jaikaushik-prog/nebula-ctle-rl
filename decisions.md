# decisions.md — every decision in this project, and why

**Written 2026-08-17.** A register, not a contract. Where this file disagrees
with `HANDOFF.md` or `CLAUDEwa.md`, **those win**; this is assembled from them
plus the ten `nebula/*.md` write-ups and the code.

Companion file: [`flow.md`](flow.md) — how the pieces fit together.

**How to read an entry.** Each has **Decision → Why → Consequence → Where.**
Decisions marked **[REVERSED]** were later withdrawn — they are kept, with the
reversal, because the argument that failed is worth more than the tidy version.
Decisions marked **[OPEN]** are waiting on a human.

---

## A. Framing — what this project is

### A1. Run two projects in one repository, sharing only HANDOFF.md and the test suite
**Why.** The Nebula competition entry needs the SerDes framework's eye engine.
Forking would mean maintaining two copies of a 7 200-line validated codebase
under a six-week deadline.
**Consequence.** `python_models/` and `nebula/` are independent by design and
have separate contracts (`CLAUDE.md` vs `CLAUDEwa.md`), separate spec tables and
separate gates. Both `conftest.py` files coexist without colliding.
**Where.** `CLAUDE.md` table; `nebula/README.md`.

### A2. Declare the SerDes framework as pre-existing team infrastructure
**Why.** Honesty in front of a panel of practising engineers. The RL sizing
loop, the corner-aware fidelity hierarchy and the device→link bridge are new
work; the eye engine is not.
**Consequence.** This sentence must appear in the abstract, report and slides.
**Where.** `CLAUDEwa.md` §4.3 (honesty rule).

### A3. Keep the repository private, permanently
**Why.** It contains ten copyrighted reference PDFs (IEEE, theses, vendor
material) and the organisers' `PCI.2/` material, which is not ours to
redistribute.
**Consequence.** `.gitignore` is sectioned **by reason** (copyright /
redistribution / regenerable), not by extension. `git init` was re-run on
2026-08-04 and the PDFs were verified absent from the index *before* the first
commit, so there is no history to strip.
**Where.** G1, G41; `HANDOFF.md` §2.

### A4. Commit as `Jai Kaushik <jaikaushik-prog@users.noreply.github.com>`
**Why.** The BITS Pilani email produces wrong GitHub attribution.
**Where.** G12.

### A5. Target SKY130, not IHP 130 nm BiCMOS
**Why.** Both were permitted. SKY130 has a working ngspice flow and an
installable distribution (volare).
**Consequence.** Everything is 1.8 V, and the 1.2 V bounds derived before the
switch **do not transfer** and were re-derived.
**Where.** `CLAUDEwa.md` §2; `nebula/BOUNDS_REDERIVATION.md`.

### A6. Reject Cadence / Spectre / any commercial tool in the deliverables
**Why.** The competition's open-source constraint is explicit and
non-negotiable.
**Consequence.** `ams/`, `scripts/cadence/`, `veriloga_models/` stay in the tree
but are never referenced in a deliverable.
**Where.** `CLAUDEwa.md` §2, §4.3.

---

## B. Reading the specification

### B1. Read S3 ("HF peaking boost 3–12 dB, peak in 1.25–2.5 GHz") **both ways, and require both**
**Why.** The wording admits two readings that are *not the same number and can
have opposite signs*: (a) peak-to-DC ratio wherever the max falls, (b) in-band
boost at Nyquist. A measured SKY130 example: peaking **+3.82 dB** — a pass under
(a) — with the peak at **724 MHz** and the response **0.99 dB below its own DC
gain at 2.5 GHz**. Under (b) that stage is worse than a wire.
**Consequence.** `crosscheck.py::DerivedAc` exposes `peaking_db` and
`nyquist_boost_db` as separate properties, a test pins the distinction using
those real numbers, and both are reported. If a judge reads S3 the other way,
the project has shown it considered both rather than quietly choosing the easier
one.
**Where.** `CLAUDEwa.md` §3.

### B2. Score on the **worst corner from the start**, never at nominal with corners checked afterwards
**Why.** S9 applies to S3–S8 simultaneously. A design that meets everything at
TT/27 °C and fails at SS/125 °C is a failed design and must score as such.
Measured: **100 of 255 nominal winners (39.2 %) fail at a corner**, and 0 go the
other way — *"an optimiser scored at nominal is wrong about two of every five
designs it calls a success."*
**Where.** `CLAUDEwa.md` §12 (first named trap); `nebula/S9_YIELD.md` §4.

### B3. Do not change the topology (S2) or the spec table without a human decision
**Why.** Both are the competition's, not ours.
**Where.** `CLAUDEwa.md` §8 rule 5.

### B4. No bonus terms for exceeding a spec
**Why.** Once a spec is met, further improvement should be worth nothing —
that is what stops the policy trading a met spec against an unmet one.
**Where.** `CLAUDEwa.md` §9.

---

## C. Method and epistemics — the decisions that are the project's best asset

### C1. Every number in a deliverable must trace to a simulation actually run
**Why.** Standing rule 1. An agent will cheerfully produce clean, well-tested
code that computes a number from a broken simulation.
**Consequence.** If a value is unknown it stays `None` and fails loudly. No
placeholder results.
**Where.** `CLAUDEwa.md` §8 rule 1.

### C2. Pre-register every prediction, with acceptance bands and falsification conditions, **committed before the run**
**Why.** It is the only defence against post-hoc rescue, and it makes a miss
into a result rather than an embarrassment.
**Consequence.** `nebula/PREDICTIONS.md`, six entries. Misses are recorded as
misses (entry 2's 2e and half of 2g; four of nine in entry 4). One falsification
condition **fired** (the pre-screen does not transfer). Nothing above an Outcome
heading may be edited afterwards.
**Where.** `nebula/PREDICTIONS.md`.

### C3. A check that reports failure as a warning and exits zero **is not a gate**
**Why.** Earned, not theoretical. The §6 cross-check lived in an ngspice
`.control` block and never executed — `@m1[gm]` is in the `op1` plot and after
`.ac` the current plot is `ac1`, so every `let` errored. ngspice printed them as
warnings and exited 0. **The gate looked green for a week while computing
nothing**, and the number it was meant to check turned out to be **2.33 dB
wrong**.
**Consequence, now binding.** Derived quantities are computed **in Python from
parsed primitives**, never in `.control`. Output is grepped for warning-shaped
failures before anything is believed. **Every gate gets a test that proves it
can fail** — break the input deliberately, watch it go red, put it back.
**Where.** `CLAUDEwa.md` §8 rule 10; `nebula/device/crosscheck.py`.

### C4. Exactly ONE definition of every model card and device parameter
**Why.** `device/spice/g1_handdesign.cir` and `device/ngspice_runner.py`
described "the same" reference point with `.model` cards differing by one
parameter — `k2`, BSIM4's body-effect coefficient, i.e. *precisely* the term the
§6 correction was about. Effect: gmbs/gm 0.250 vs 0.327, A_dc −14.12 vs
−14.57 dB. Every published figure came from the runner, so anyone
sanity-checking by opening the netlist would have been quietly misled.
**Consequence.** Netlists and runners **reference**, never redeclare. If you
clone a netlist, diff the `.model` line.
**Where.** `CLAUDEwa.md` §8 rule 9; G32.

### C5. Tests before implementation at every layer boundary; mocks for all three layers first
**Why.** Three people building in parallel against a frozen interface is the
only way this finishes by 15 September.
**Where.** `CLAUDEwa.md` §5.1, §8 rule 4.

### C6. The mocks produce fake numbers, and no path from a training run may reach them
**Why.** A synthetic stand-in that leaks into a results table is
indistinguishable from fabrication.
**Consequence.** `tests/test_no_mocks_in_training_path.py` checks this **in a
subprocess**, with a companion test proving it can fail. The test also pins the
consequence: because the link layer is synthetic end to end, **S8 cannot be
scored by the RL reward at all** — a conclusion, not a gap.
**Where.** G16; `nebula/rl/reward_v1.py`.

### C7. Raw results are **tracked in git**, not gitignored — and aggregates are not results
**Why.** A 47-minute experiment's raw results were gitignored and had to be
rebuilt at 23 minutes of ngspice. Worse, one level up: `s9_yield_results.json`
was tracked but stored only *counts*, so **20 205 individual (design, corner)
measurements were never written to disk** and task 8 could not use them.
**Consequence.** `.gitignore` amended. Every experiment commits its CSV/JSONL
alongside the write-up. Log **rows**, not summaries.
**Where.** G49; `nebula/NEXT_STEPS.md` step 8.

### C8. Every experiment script owns its assumptions and prints them in every run's header
**Why.** An assumption stated only in a write-up drifts out of the code.
**Consequence.** `s9_yield.py` prints its three assumptions every run.
**Where.** `nebula/README.md`.

### C9. Every experiment has a `--report` / `--analyse` mode that runs with **no simulator**
**Why.** Re-deriving an analysis must not cost hours of ngspice, and a reviewer
without the toolchain must still be able to check the arithmetic.
**Where.** `nebula/experiments/*.py`.

### C10. Stream results to JSONL as they arrive; row 0 is a header row
**Why.** An interrupted 12-hour run must be recovered, not lost — this is not
hypothetical, the task-7 pilot was killed one job from the end and **every row
survived**. And a log that can be read without its conditions will be.
**Where.** `nebula/rl/runlog.py`; `nebula/experiments/baselines.py`.

### C11. Update `HANDOFF.md` in the same commit as any change
**Why.** A change without a handoff update is an incomplete change. The file
exists so any agent or person with zero context can pick the project up.
**Where.** `CLAUDE.md` rule 1.

### C12. The human decides anything where being wrong costs a week
**Why.** *"An agent will cheerfully produce clean, well-tested code that
computes a number from a broken simulation, and tests written by the same agent
will not catch it."*
**Consequence.** Rule 6: agents do not choose parameter ranges, reward weights
or spec-tightness heuristics autonomously. They propose and wait.
**Where.** `CLAUDEwa.md` §8 rule 6, §11.

### C13. Report a ranking only when the confidence intervals do not overlap
**Why.** Otherwise the benchmark reports noise as a result.
**Consequence.** Any ordering whose CIs overlap is reported as *"not separable
at this sample size"*. Every rate carries a Wilson interval; the coupling factor
carries a percentile bootstrap.
**Where.** `nebula/BASELINES.md` §8 (7h).

---

## D. Circuit and device layer

### D1. Include the body-effect term: `k = 1 + (gm + gmbs)·Rs/2`
**Why.** In bulk CMOS every NMOS sits in the grounded p-substrate, so the source
swings while the body stays at 0 V and `gmbs` degenerates alongside `gm`.
Measured at the G1 point: **gmbs/gm = 0.33**. Omitting it gives A_dc −12.24 dB
against a simulated **−14.57 dB** — off by **2.33 dB**, and the equation
**fails its own 1 dB gate on a correct circuit**.
**Consequence.** `Rs ≈ 3/gm` oversizes the degeneration by about a third; use
`Rs ≈ 3/(gm + gmbs)` ≈ `2.25/gm`. Deep n-well would remove the term at an area
cost — considered and rejected, and said so rather than left unexplained.
**Where.** `CLAUDEwa.md` §6; G27.

### D2. `Rs` is the FULL resistance between the two sources; each half-circuit sees `Rs/2`
**Why.** Writing the equations with a per-side `Rs` makes every gain and peaking
number wrong.
**Where.** `CLAUDEwa.md` §6.

### D3. The tail is a real current mirror with **one device per side**, not a shared tail
**Why.** A shared tail would short out the Rs/Cs degeneration, which is the
whole topology.
**Consequence.** Two devices have **independent noise**, so tail noise is *not*
common-mode in this topology: S5 rises **1.61×** (0.275 → 0.442 mV_rms) with the
two tails at **66 % of the noise power**. The mirror *reference*, whose noise
really is common-mode, is rejected to 2e-21. Still passes S5.
**Where.** `nebula/TAIL_DEVICE.md` §4.

### D4. Replace the two ideal current sinks with a real mirror — and keep `I_ref` ideal, declared
**Why.** An ideal sink does not lose current at SS/125 °C, does not gain it at
FF/0 °C and never falls out of saturation. That single assumption made every S9
number an optimistic bound.
**Consequence.** Measured cost: **8.8 %** of the corner-robust-at-some-load
population (160 → 146) and **zero** of the headline yield (1/1890 before and
after, *the same design*, index 432). Also: **the mirror delivers 4–8 % less
current than requested and that is physics** (channel-length modulation across a
0.7 V vds mismatch), so S6 is now billed on **measured** supply current.
**Where.** `nebula/TAIL_DEVICE.md`; G47.

### D5. Do **not** search `w_tail`, `l_tail`, `nf_tail`; derive them from `i_bias`
**Why.** `w_tail` follows from `i_bias` by a current density (105–124k µm/A,
1.18× drift across a 4× current change), `nf_tail` is near-dead (0.6 %), and
`l_tail` spans one octave. Then the RL sensitivity gate settled it with a
number: **`vcm_in` is a 6× stronger lever on the tail margin than `tail_j` is**,
on the very quantity the tail geometry exists to control.
**Consequence.** Action space stays at nine dimensions rather than twelve.
**[REVERSED once]** — the first version of `rl/contract.py` *did* make `tail_j`
and `l_tail` actions, on the grounds that the recommendation had no measurement
behind it in an RL setting. The §6e gate supplied that measurement and argued the
other way; the axes were removed by human decision on 2026-08-07.
**Where.** `nebula/TAIL_DEVICE.md` §6; `nebula/RL_SMOKE.md` §6e.

### D6. Fix `nf_in` at 4 and make it **not** an action
**Why.** On SKY130 `nf` does **not** multiply device width — `W` is the total
width and `nf` only splits it into fingers. Measured at W = 40 µm, 1.5 mA/side:
`nf` = 1, 2, 4, 8, 16, 32 gives gm = 14.22, 13.68, 12.62, 13.12, 12.29,
11.79 mS — a **±10 % non-monotonic** parasitic effect. A policy gradient on a
non-monotonic ±10 % axis learns the noise, and spends samples doing it.
**Where.** G38; `nebula/rl/contract.py` §1.

### D7. Remove `cl` from the search and treat it as a screened **context range**
**Why.** Two findings. First, `cl` is a bad search dimension: **pinning it
raises** the random-search S3 yield from 8.73 % to 13.54 % (disjoint 95 % CIs),
because it trades peak magnitude against peak location and location wins only up
to ~150 fF. Second, 150 fF was chosen because it maximised yield among five
tested values — *choosing the answer*. Derived instead from what physically
loads the CTLE output (1-tap DFE summer pair + slicer pair + routing):
**13.64 / 32.63 / 78.04 fF, a 5.72× range** whose top is **1.92× below** the
value every published corner number had used.
**Consequence.** Every corner number before session 12a was measured at a load
the following stage cannot present. `CL_LEGACY_PIN_F = 150 fF` is kept **only**
so the older runs stay reproducible.
**Where.** `nebula/CL_SENSITIVITY.md`, `nebula/CL_RANGE.md`; G42.

### D8. Measure gate load as the AC current the driver must supply, not `@m[cgg]`
**Why.** `@m[cgg]` is the *intrinsic* capacitance: it excludes the overlap
capacitance and the Miller multiplication of C_gd. Measured understatement
**2.00× / 2.52× / 2.70×** on the 4/12/16 µm stages — it grows with gain, which
is the Miller signature. At the 16 µm stage **52 % of the load is
C_gd,overlap × (1 + |A|)**.
**Consequence.** Cross-checked against parsed primitives plus the model card's
own overlap constants to 1.02 % median; `sanity_check_load` rejects a point that
disagrees by more than 5 %. 0 of 180 rejected.
**Where.** G50; `nebula/CL_RANGE.md` §2.

### D9. Reject the 3.3 V / 5 V SKY130 devices
**Why.** They cannot do S3 at 2.5 GHz — f_T is insufficient — and the swing they
buy is only **+12 %**, because the binding limit is **current steering, not
headroom**.
**Where.** G39; `nebula/BOUNDS_REDERIVATION.md`.

### D10. Draw the passives as real SKY130 devices (`res_high_po`, `res_xhigh_po`, `cap_mim_m3_1`)
**Why.** S7 is an area spec and the passives dominate it; and an ideal R/C
result is not a schematic.
**Consequence, and it is not small.** Drawn passives move `f_peak` by up to
**0.1329 octaves** — *more* than the **0.12 octaves of centring slack** that
selected the sole load-robust design — always in the same direction, via the
`res_po` bottom plate adding **+1.4 to +24.3 fF onto a 32.6 fF `cl` (up to
+75 %)**, while `g_dc` moves 0.0006 dB. **The load and corner screens both need
re-running before "1 in 1890 is corner-and-load-robust" can be repeated.**
**Where.** `nebula/PASSIVES.md`; G66.

### D11. Gate the assembled netlist text against parameters SKY130 accepts and ignores
**Why.** `w` is **inert** on the fixed-width resistor families (G57) and
`mult`/`mf` are **mismatch** parameters, not device multipliers (G56). Both are
accepted, ignored, and followed by exit 0.
**Consequence.** `device/netlist_gates.py` refuses to *emit* them, gated on the
text rather than the call site — strictly stronger, since no path through the
device layer escapes it, including one written by someone who has not read the
file. `rl/env.py` asserts at construction that the gate is live.
**Where.** `nebula/device/netlist_gates.py`.

### D12. HD3 comes from transient + FFT, not from `.disto`
**Why.** `.disto` returns exactly 0.0 for BSIM4 — it is not a linearity result,
it is an unimplemented analysis.
**Consequence.** A 175× cost spread across fidelity tiers, measured.
**Where.** G21, G22; `nebula/G0_RESULTS.md`.

### D13. `to_geometry()` is accepted as electrically stable and geometrically chaotic
**Why.** A **0.016 % change in `rs` flips the device**, giving a **15× area
spread across a 0.16 % resistance spread**.
**Consequence.** `PASSIVES.md`'s 1506 µm² is a property of the **quantiser** as
much as of the design, and task 8's `design_id` grouping is fine-grained rather
than coarse. Stated rather than smoothed over.
**Where.** G67.

---

## E. Simulator and toolchain

### E1. ngspice 41 in a conda env named `nebula`, invoked as **`ngspice_con.exe`**
**Why.** `ngspice.exe` is the GUI build: it prints nothing in batch mode, which
looks exactly like a broken install.
**Where.** G20.

### E2. Do not use PySpice, despite it being a mandated-tool option
**Why.** It is installed and does not work here (bundled ngspice mismatch).
Subprocess + parse is the working path.
**Where.** G23.

### E3. Install SKY130 via volare; run netlists **from `nebula/device/spice/`**
**Why.** The raw `sky130_fd_pr` clone is not ngspice-ready. And `.spiceinit`
(`ngbehavior=hsa`) is read at **parse time**, so the working directory matters.
**Where.** G29, G33.

### E4. Trim the PDK library, and hold the trim to **bit-identical** output
**Why.** The full library costs 16–35 s to *parse*, per invocation.
**Consequence.** `sky130_nfet_only.lib.spice`: **0.42 s**, verified identical at
**rel = 0, abs = 0** — not "within tolerance" — against a 20-point golden set
from the full library. The precedent this set is now applied to every trim.
**Where.** G34, G36.

### E5. Build an **extended** trimmed library (25 sections = 5 MOS × 5 passive corners) once drawn passives were needed
**Why.** The nfet-only trim carries no R or C model sections. And the passive
corner axis is **orthogonal** to the MOS one — so S9's 45 corners are really
**225**.
**Consequence.** A cost regression that was not understood for four sessions.
**Where.** G58; `nebula/PASSIVES.md` §3.

### E6. **[REVERSED]** "The extended library is slow because the R/C corner files pull in `typical.spice` (3023 lines) and `invariant.spice` (7340)"
**Why it was believed.** It was measured that the extended library was ~6–7×
slower, and those includes were visible in the corner files.
**Why it is wrong (session 19, 2026-08-12).** Both halves fail on inspection.
`invariant.spice` **is not in the include tree at all** — only
`parameters/montecarlo.spice` includes it, which no section this project
reaches. `typical.spice` is real but minor: 8 909 named parameters of which the
library references **86**; dropping the other 8 823 is worth about **1.55×**.
**The actual cause: ngspice expands EVERY `.lib` section in a file, not just the
one asked for.** Same netlist, same machine — one section **0.093 s**, the real
25-section file **1.386 s**, a **15×** difference. The cost scales with
*section count*, not with what the netlist uses. It was invisible because every
previous measurement compared whole libraries against each other, never a
library against itself with one section removed.
**Consequence.** `device/pdk_trim.py` generates one file per `.lib` section and
`lib_for_device(..., section=)` selects it, falling back to the monolithic
library so an unregenerated tree still runs, just slowly.
**Where.** `nebula/device/pdk_trim.py`; `HANDOFF.md` §2 (session 19); write-up
`nebula/LIB_COST.md` **not yet written**.

### E7. Generate the trim, never hand-write it; re-derive it byte-for-byte in a test
**Why.** Rule 9. A hand-edited generated file is a second definition waiting to
drift.
**Consequence.** The keep-set is read out of the library's **own include list**,
so adding a device automatically widens it and the regeneration test goes red
until someone reruns the module.
**Where.** `nebula/device/pdk_trim.py`; `nebula/tests/test_pdk_trim.py`.

### E8. Budget parallelism at ~8 workers, and measure the speed-up honestly
**Why.** 11 cores buy **3.2×**, not 11×. Then a benchmark run in a fixed order
reported **4.39× at 11 workers** and the tell was that **2 workers reported
2.55×, which two processes cannot do** — the 1-worker pass had run first on a
cold file cache. Reversing the order gives the honest answer: **2.64× at 8
workers, with 11 slower than 8**. And a speed-up measured on isolated
evaluations does not transfer to a workload whose workers also compute: **2.98×
became 1.80×**.
**Consequence.** Benchmarks now use a discarded warm-up, per-design shuffled arm
order, and a control arm re-run last. **Look for the impossible number, not the
disappointing one.**
**Where.** G48, G70, G71, G75.

### E9. Count **every** ngspice invocation, including setup and discards
**Why.** A cost model that excludes discards understates the thing being
optimised.
**Consequence.** `SpiceBudget` in `rl/evaluator.py`; measured 1.586 sims/step,
1132 steps/hour.
**Where.** `nebula/RL_SMOKE.md`.

---

## F. Link layer

### F1. Delete `CHANNEL_DC_LOSS_DB = 1.0` rather than re-value it
**Why.** The constant had no provenance, its own docstring said a human had to
replace it, and it — not the circuit — had decided a published compression
verdict. **The name encoded the mistake**: a lossy line's insertion loss at DC
is essentially zero, and the real low-frequency correction is not a channel
property at all but the transmitter's specified **−3.5 dB de-emphasis**.
**Consequence.** A test greps every executable file in the tree for the
identifier. `channel_loss_db_at_dc` is now a derived property returning exactly
0.0.
**Where.** `nebula/CHANNEL_MODEL.md`; G62 (how to write that grep so it can fail).

### F2. Derive the channel as a **family**, not a single case: `IL_dB(f) = A·√f + B·f`
**Why.** A scalar cannot represent a channel, and that is now measured: at a
fixed loss at Nyquist, skin-dominated leaves **1.60×** the residual of
dielectric-dominated at 12 dB and **1.99×** at 3 dB. The ratio is largest where
the channel is *easiest*, which is the opposite of where one would look.
**Consequence.** 7 losses × 3 splits = 21 members, parameterised by (loss at
Nyquist, skin/dielectric split), with loss at Nyquist read off S3's own 3–12 dB
range. Equivalent length is *reported* from a stated stackup, never used to
derive the loss.
**Where.** `nebula/CHANNEL_MODEL.md` §§4–5.

### F3. Reconstruct phase as minimum-phase and **gate on causality**
**Why.** A channel model with a magnitude and no phase is non-causal — **48 % of
its energy sits at t < 0** — and raises nothing on its own.
**Consequence.** Real-cepstrum fold of `ln|H|`, then a gate on pre-`t=0` energy,
plus a power-law test that distinguishes aliasing from a broken reconstruction.
**Where.** G59.

### F4. Model the PCIe Gen2 transmitter as the 2-tap FIR it actually is
**Why.** The −3.5 dB de-emphasis is mandated, and it is worth **exactly 3.5 dB**
of the CTLE's job (the FIR has gain `d` at DC and 1 at Nyquist by construction).
**Consequence.** The CTLE's burden spans **−0.5 to +8.5 dB**, so **the top
3.5 dB of S3's range is never called for** on this family, and at 3/4.5/6 dB of
loss the burden is *below* S3's 3 dB floor — the minimum setting
over-equalises. **[OPEN]** either S3's tunable range must reach below 3 dB, or
the low-loss end of the channel family is declared out of scope.
**Where.** `nebula/link/tx.py`; `nebula/CHANNEL_MODEL.md`.

### F5. Accept a 1-tap DFE (S2's mandate) on measured evidence — and name why it is not reassuring
**Why.** The eye is open at **all 21 channel members**, all three de-emphasis
settings, with and without a CTLE (worst residual 0.847 bare / 0.613 with the
Gen2 mandate / 0.276 with a matched CTLE). So S3's top of range and S8 can both
be met with S2's topology.
**But.** Only **14.7 %** of what the DFE cannot reach is in `h2`, and **31.2 %
sits beyond 20 UI** — the `√f` algebraic tail, exactly what decision feedback is
worst at. A second tap buys 15 %; a twenty-tap DFE still leaves 31 %. **The CTLE
is the block that has to do this work.**
**Where.** `nebula/CHANNEL_MODEL.md` §5.

### F6. State that every ISI number from this family is a **lower bound**
**Why.** The family contains no impedance discontinuities — no connectors, vias,
stubs, crosstalk, mode conversion or fibre-weave skew. Reflections are the ISI a
DFE handles worst. A stated two-reflection probe adds **+0.064 to +0.122**, and
at 12 dB that takes the channel-only eye from 118 mV to **81 mV, below S8's
100 mV floor**.
**Consequence.** Any deliverable says *"constructed from the specification"*,
never *"the channel"*. `fit_from_touchstone` is the seam a real `.s4p` enters
through.
**Where.** `nebula/CHANNEL_MODEL.md` §8, §12; `HANDOFF.md` §7.

### F7. Put the normalised→volts conversion in exactly one function
**Why.** `statistical_eye.py` works in normalised amplitude; S8 demands volts.
A wrong scale factor produces plausible-looking numbers that are meaningless —
named as the highest-risk silent bug in the project *before* it could happen.
**Consequence.** `link/calibration.py`, with a dedicated test carrying a
hand-computed expected value. Even the mock converts through it, so a
calibration bug shows up in the mock as loudly as in the real thing.
**Where.** `CLAUDEwa.md` §5.3a; G18.

### F8. Reject pole-zero fits with residual > 0.5 dB rather than passing garbage downstream
**Why.** The bridge fits ngspice AC output onto `(g_dc, f_zero, f_pole1,
f_pole2)`. A bad fit produces a CTLE model that is not the circuit.
**Where.** `CLAUDEwa.md` §5.3b; `device/interface.py::reject_bad_fit`.

### F9. Use the **closed form** for the CTLE peak, never the `20·log10(k)` asymptote
**Why.** The exact peak of a one-zero/two-pole magnitude is
`f_peak = √( √((f_z² − f_p1²)(f_z² − f_p2²)) − f_z² )`, with no fitted constant.
Measured across 1311 designs, `20·log10(k)` **over-predicts peaking by a median
+1.199 dB**.
**Where.** `nebula/experiments/task8_symbolic.py`; `nebula/link/cursors.py`.

### F10. Never integrate a waveform through `design_equations.predict()`
**Why.** The §6 equations neglect `r_o` and **over-predict the Nyquist boost by
+0.77 to +1.47 dB**. That became a **28 % error** in a published compression
ratio before it was calibrated out.
**Consequence.** Calibrate the CTLE model to the **measured** boost.
**Where.** G60.

### F11. Report "compression ratio" under a named convention, and use convention C
**Why.** The phrase has **three** definitions in this repo and they disagree by
**1.8×**: (A) Nyquist content in / Nyquist gain out → 2 of 7 compressing;
(B) long-run level in / peak gain out → 7 of 7; (C) peak distortion through the
real pulse response → **5 of 7**.
**Consequence.** The old headline "1.22× at 3 dB" **survives verbatim under
convention A** — which never read the deleted DC-loss constant — but the honest
number is **1.51× at 3 dB**. The old line is *replaced*, not amended.
**Where.** G61; `nebula/CHANNEL_MODEL.md` §6.

### F12. Feed the statistical eye, not a full PRBS transient, inside the RL loop
**Why.** AC + `.noise` + HD3 extraction feeding a semi-analytic engine is orders
of magnitude cheaper and reaches BER depths transient never can (1e-15).
**Where.** `CLAUDEwa.md` §12.

### F13. Keep the PAM-4 path working behind a flag; do not fork the repo
**Why.** The inherited framework is 112G PAM-4 in 28 nm and its 48 tests are the
contract that the NRZ retarget did not silently break the eye engine.
**Consequence.** `modulation.py` makes the symbol alphabet one object and
derives every alphabet-dependent constant from `levels`, so PAM-4's E[a²] comes
out at exactly the 5.0 that used to be hard-coded. **21 of 24 audited four-level
assumptions remain open.**
**Where.** `CLAUDEwa.md` §4.3; `nebula/NRZ_RETARGET_AUDIT.md`.

---

## G. The RL layer

### G1. Write the environment **contract** before the implementation, in one file
**Why.** An observation vector assembled in the env and re-assembled in an
analysis script is exactly the "two definitions of one thing" bug.
**Where.** `nebula/rl/contract.py`.

### G2. Actions are **deltas**, not absolute sizings, clipped to `MAX_STEP`
**Why.** The policy proposes an *edit* to the current design and sees the result
before the next edit. That is what makes an episode a design session rather than
seven independent bandit pulls.
**Where.** `nebula/rl/contract.py` §1.

### G3. Normalise per dimension to [0,1], **log-scaled where the box spans decades**, linear where it does not
**Why.** A delta of 0.10 should mean "one tenth of the box in the box's own
metric" — a fixed *ratio* for a resistance or a current, a fixed *increment* for
a width.
**Consequence.** log: `l_in`, `i_bias`, `rs`, `cs`, `rl`. linear: `w_in`,
`vcm_in`.
**Where.** `nebula/rl/contract.py` §1.

### G4. Store widths in SI metres in the box and convert to microns in exactly one place
**Why.** G31 — SKY130 instance W/L are plain numbers in microns, and the units
error still simulates happily.
**Where.** `SizingPoint.from_params`.

### G5. **[REVERSED]** the reward is *not* worst-normalised-margin (`min` over specs and corners)
**Why the reversal.** Withdrawn on 2026-08-06 by the person who proposed it,
on the evidence of session 13's violation table. *"`min` has the same pathology
as the first-failure table, one layer down: it reports `S3_f_peak` for as long
as that misses by 17 GHz, so the agent gets no gradient on `tail_saturation` — a
constraint binding on 13.3 % of the box at slow-hot — until S3 is nearly
solved."*
**The shape that replaced it.**
```
while ANY constraint violated:  r = −Σ clip(shortfall_i, 0, 1)   # gradient on EVERY miss
once ALL satisfied:             r = B + min_i(margin_i / tol_i)  # now seek margin
```
**Where.** `HANDOFF.md` §8; `nebula/rl/reward_v1.py`.

### G6. Normalise each margin so that **1.0 means "meaningfully off"**, and quote every tolerance
**Why.** `CLAUDEwa.md` §9's `(|x| + |τ|)` denominator is scale-free but not
*meaningful*: 17 GHz against 2.5 GHz and 40 mV against 200 mV both normalise to
about −1, destroying exactly the distinction session 13 paid to discover.
**Consequence.** `S3_f_peak` **0.5 octaves** (S3's window is exactly one octave,
so the half-width is 0.5); `S3_peaking` **1.0 dB** (the granularity real CTLEs
tune at); `S3_nyq_boost` **1.0 dB** below zero; `S5_noise` **0.5 mV_rms** (a
third of the limit); `S6_power` **5 mW** (same argument); `saturation`
**0.1 V** of `vds − vdsat`.
**Where.** `nebula/rl/reward_v1.py`.

### G7. Keep `f_peak` in **log** frequency
**Why.** `f_peak` is quantised at **0.0664 octaves** by `meas ac MAX` on an
`ac dec 50` grid, so a linear-hertz tolerance would be finer than the
measurement at the bottom of the window and coarser at the top.
**Where.** `nebula/rl/reward_v1.py`; session 11.

### G8. **Validity and reward answer different questions** — three verdicts, not two
**Why.** The first version was two-valued (VALID / INVALID) and that was wrong
in a costly way. Two results can look identical — no usable AC spec set — and
need opposite handling: a peak reported at 19.95 GHz is an **untrustworthy
measurement** (`meas ac MAX` returned the edge of its own range; the number is
fiction), while a device in **triode** is a trustworthy measurement of a bad
circuit.
**Consequence.** `VALID` / `HEADROOM_ONLY` (AC set dropped, graded on
`vds − vdsat`, which is a `.op` quantity and therefore still true) / `INVALID`
(floor, no gradient). Trustworthiness is **per analysis**, not per evaluation.
This matters because `tail_saturation` binds on 2.6–13.3 % of the box, so a
fresh policy lands in triode often and a flat floor there gives it no way out.
**Where.** `nebula/rl/evaluator.py`; G72.

### G9. An invalid result is never a default, a clamp, or a retry that quietly succeeds
**Why.** Each of those hands the RL loop a finite reward for a design that does
not simulate. The distinction from `s9_yield.py`, which *does* retry once and is
right to (G45, transient Windows process-launch failures): there a successful
retry **replaces a failure**; here a retry that succeeds with **different
numbers** is a different answer.
**Where.** `nebula/rl/evaluator.py`.

### G10. Split `has_interior_peak` into a separate `peak_is_sweep_edge` guard
**Why.** It was a **conjunction whose two terms rejected different kinds of
thing**: one is a fictitious peak at the sweep edge (`rl` = 800: 1.08 dB of
"peaking" at 19.95 GHz), the other a genuine-but-small maximum (`rs` = 50:
0.165 dB at 1.318 GHz — a *correct* measurement of a circuit that does not
equalise). Using it as a validity gate put the reward **floor across the whole
low-peaking bottom of the box**, which is exactly where a random policy starts.
**Consequence.** `has_interior_peak` left **unchanged** because three
experiments publish counts with it.
**Where.** G64.

### G11. Keep the G44 sweep-edge guard: it is load-bearing, not defensive
**Why.** **78 % of everything the policy found was a fictitious peak** — 159 of
203 invalid evaluations (26.5 % invalid overall). Under a reward reading S3
peaking, every one of those 159 would have scored **high** for a circuit with no
peak at all.
**Where.** G44, G65.

### G12. Accept that `saturation` and `tail_saturation` are wired but structurally cannot be violated
**Why.** A triode design is rejected by the validity gate before the reward sees
it, so their gradient lives only in the feasible branch's margin term.
**Consequence.** Accepted by human decision, because grading a triode design's
small-signal numbers would be grading fiction (G24's precedent). The retraction's
"the tail needs its own shortfall" argument is delivered instead by the ungraded
invalid floor.
**Where.** `nebula/RL_SMOKE.md` §6h.

### G13. Write a minimal PPO in torch; no gymnasium, no stable-baselines3
**Why.** Neither is installed here, and a missing package must not block a smoke
run. Every constant is a PPO-paper or SB3 default, **written down**, and nothing
is tuned. PPO is worth **0.2 % of a run's wall clock**, so optimising the RL
side is worth nothing.
**Consequence.** The interface is gym-*shaped* (`reset() → obs`,
`step(a) → obs, r, terminated, truncated, info`), so an SB3 adapter is ~60 lines
if one is ever wanted. `CLAUDEwa.md` §2 lists "Gym utils" among the mandated
tools and that satisfies it.
**Where.** `nebula/rl/env.py`, `nebula/rl/ppo.py`.

### G14. Put `to_geometry()` in the loop **from the outset**
**Why.** The deliverable is a schematic. A loop that optimises ideal R and C
does not produce one.
**Where.** `nebula/RL_SMOKE.md`.

### G15. Draw **no conclusion about learning** from the smoke run
**Why.** Mean episode return went −2.98 / −6.16 / −4.54 / −3.09 / −0.50 across
five buckets — non-monotone — and nothing was tuned. 142 episodes.
**Consequence.** The write-up says so explicitly. The headline of that session
is the **failure catalogue**, not the curve.
**Where.** `nebula/RL_SMOKE.md` §11.

---

## H. The benchmark (task 7)

### H1. Build a **problem ladder** (P1–P4), and report all rungs
**Why.** A benchmark on an infeasible problem measures nothing — every method
scores "never found one" and the comparison is empty. And the robust problem
**may be** infeasible: session 12b left 1 design in 1890, and drawn passives
then moved `f_peak` by more than that design's centring slack.
**Consequence.** P1 TT/`cl_mid` (base rate 13.44 %), P2 3 corners, P3 3 corners
× 2 loads (**possibly empty**), P4 tunable (**seam only** — blocked by G63, not
by effort: with drawn passives there is no `Rs` element to `alter`, so the 11×
that made the inner search affordable is destroyed).
**Where.** `nebula/BASELINES.md` §2.

### H2. Cut the sweep on **problems**, never on seeds or the per-run budget
**Why.** Fully crossed the sweep is 63 000 simulations = 23.5 h and does not
fit. Cutting seeds would make the comparison unfalsifiable; cutting the per-run
budget would change what is being compared.
**Consequence.** 25 500 simulations ≈ 12.0 h. P2 cut entirely; P3 loses its
pre-screened and PPO arms.
**Where.** `nebula/BASELINES.md` §1.

### H3. Report **simulations-to-ceiling** beside best-reward-at-budget
**Why.** A finding the brief did not ask for: **the primary metric has a ceiling
that belongs to the AC sweep, not the circuit.** `meas ac MAX` reports on a
0.066439-octave lattice and `S3_f_peak` is the binding reward row, so **no
design can score above +8.950669** on P1. Derived analytically, then measured —
four *different* designs all scored 8.950670.
**Consequence.** Best-reward-at-budget **saturates** on P1 and cannot separate
methods there.
**Where.** G74; `nebula/BASELINES.md` §3.

### H4. Add the tuning budget to PPO's cost
**Why.** A method that needed 50 000 simulations of tuning to win a
150-simulation comparison has not won it.
**Consequence.** Tune only on P1; hold out the spec target used for the final
claim; do not touch the evaluator, tolerances, box or geometry mapping — if any
of those change, **every baseline must be re-run**.
**Where.** `nebula/NEXT_STEPS.md` step 5.

### H5. Report a negative RL result as a finding if that is what happens
**Why.** *"If BO matches RL, say so. That is a finding, not a loss."* And
§7's fallback for G3 is explicit: if RL does not beat random search, **stop and
debug the reward function; do not proceed to corners.**
**Where.** `CLAUDEwa.md` §7.

### H6. Build an analytic pre-screen, and publish that it is **not enough**
**Why.** The pivotal question was whether physics alone solves the nominal
problem. Answer: the screen predicts `f_peak` to **4.93 %** MdAPE and removes
**61.7 % of the box for free** at a 0.39 % false-rejection rate, lifting the S3
rate among accepted designs from **13.44 % to 34.94 %** — a **2.60× multiplier,
not the >50 % that would mean physics solves it.** So a learned method is still
needed for search.
**Consequence.** A test pins the verdict in **both** directions. What the screen
actually removes is **84.3 % of the G44 population** (488 of 579 designs with no
interior peak).
**Where.** `nebula/BASELINES.md` §5.

### H7. Treat the pre-screen's failure to transfer as a **bias**, not a window problem
**Why.** A pre-registered falsification condition **fired**. Moved to the
benchmark's own conditions the screen's *population rates* transfer (free
rejection 61.7 → 63.9 %, lift 2.60 → 2.66×) but its **accuracy does not**:
`f_peak` MdAPE **4.93 → 15.85 %**, peaking bias **−0.009 → +0.361 dB**,
false-rejection **0.39 → 3.88 %**, ten times its declared 1 % budget. **Widening
does not fix it** — at 2.5× the widening the rate is still 2.33 % while free
rejection falls from 64 % to 40 %. **A window absorbs variance; this is bias.**
**Consequence.** The mechanism is specific and checkable: the gm/I_D model was
fitted where `I_D = i_bias/2` exactly, true of an ideal tail, and the real mirror
delivers **4–8 % less**. The re-fit is deliberately **not** done on a 3-seed
pilot. Known bound: re-fitting can buy at most ~1.2 % of the `f_peak` spread
(grid discretisation 0.17 %, predicted-`k` 1.20 %, the one-zero/two-pole model
itself 4.25 %) — do it anyway, because the target is the **bias** and the
false-rejection rate, which are a different failure from the spread.
**Where.** G76; `nebula/BASELINES.md` §11.

### H8. **[OPEN]** re-fit the screen before the sweep, or run the sweep against this screen?
**Why it is open.** Re-fitting first changes what the screened arms measure.
Either re-fit first and run once, or run now and label the screened arms as a
measurement of *this* screen. Stated in `HANDOFF.md` as *"a human's call."*
**Where.** `HANDOFF.md` §8.

### H9. A surrogate must beat a one-line formula before it earns a place
**Why.** Measured on TT: an exact closed form with **one fitted scalar** reached
**4.25 % MdAPE** on `f_peak` against XGBoost's **4.64 %** held out.
**Consequence.** Task 8's rule is applied as written, without lowering the bar
(worst-corner `peaking_db` MAE < 0.5 dB, worst-corner `log10(f_peak)` MAE <
0.03, boundary error no worse than 2× overall) — **and if it misses, abandon the
surrogate and say so**: the 3-corner deterministic screen is only 3× the cost,
needs no ML, and cannot silently mispredict.
**Where.** `nebula/experiments/task8_symbolic.py`, `task8_blackbox.py`.

---

## I. Retractions — claims this project withdrew

These are listed separately because they are the strongest evidence for the
methodology, and because a reader who finds only the tidy version will not trust
the rest.

| # | The claim | What happened |
|---|---|---|
| **R1** | *"S3 is a coupled constraint"* — the intended central argument | **FALSIFIED by the measurement meant to confirm it.** Measured box-independently (P(A)·P(B) vs P(A∧B) across three box widths) the coupling factor is **1.04×**: the two S3 conditions are **independent**. The low yield is just one low marginal — `f_peak` lands in-window 16 % of the time. Sharpened later: the raw coupling factor tracks the **no-peak fraction**, and conditional on a peak existing every interval covers 1.00. (G40, G43) |
| **R2** | The reward should be worst-normalised-margin | Withdrawn by its own proposer on measured evidence — see G5 above |
| **R3** | *"The tail is the one experiment that could still turn corner robustness into a real constraint rather than a tax"* | **RETIRED given the current screen.** The 8.8 % was measured on a population the load screen had already cut by 99.4 %, so the tail is **masked, not unimportant**. Must be re-read off the violation table the moment the load screen narrows |
| **R4** | *"Compression is real but small, localised at the two lowest-loss points, 1.22× and 1.04×"* | **REPLACED, not amended.** 1.51× at 3 dB, binding at 5 of 7 loss points, under a named convention (G61) |
| **R5** | `cl` should be pinned at 150–250 fF | Superseded: that was the yield maximum of five tested values. The *derived* range's top is **1.92× below** it |
| **R6** | The extended library is slow because of `typical.spice` + `invariant.spice` | Wrong in both halves — see E6. `invariant.spice` is not even in the include tree |
| **R7** | *"1 in 1890 is corner-and-load-robust"* | Not retracted but **now an ideal-passive statement**: drawn passives move `f_peak` by more than that design's 0.12 octaves of centring slack (G66). The screens need re-running |
| **R8** | `w_tail` / `l_tail` belong in the action space | Added, then removed on the sensitivity gate's own number (`vcm_in` is a 6× stronger lever) |

---

## J. Open decisions — waiting on a human

Nothing below may be decided by an agent (rule 6).

1. **Approve the parameter box** and copy it into `common/params.py::BOUNDS`,
   which is deliberately empty and raises. Seven of nine edges are already
   copied verbatim into `rl/contract.py` with a test asserting no drift.
2. **Full-rate or half-rate receiver?** S2 names no CDR. Full rate gives
   `cl` = 13.6–78.0 fF (5.72×); half rate gives 13.6–141.8 fF (10.4×) — and the
   150 fF pin was the right number for a topology S2 does not describe.
3. **S3's floor, or the channel family's low-loss end.** Below ~6.5 dB of
   channel loss the CTLE's burden is *below* S3's 3 dB floor, so a compliant
   CTLE adds boost the link does not need. Either the tunable range reaches
   below 3 dB, or the low-loss end goes out of scope.
4. **Re-fit the pre-screen before or after the sweep** (H8).
5. **Which random-search baseline G3 must beat** — 8.73 % (`cl` searched) or
   13.54 % (`cl` pinned). Note the second makes G3 *harder*.
6. **The CTLE output common mode may not be able to bias the stage it drives.**
   `headroom_ok_1v8()` lets v_out fall to 0.5 V; the loading pair needs roughly
   1.15 V or its source node goes negative — session 9c's unbuildable-tail
   failure, one stage downstream. **Nothing in the project currently notices
   this.** Either the box needs a tighter v_out floor, or the RX needs AC
   coupling / a level shift.
7. **Whether the endpoints of S3's own tunable range (3 dB and 12 dB) are
   corner-robust at all** in this topology. Session 11's 1.0 dB peaking-margin
   filter bans them, so the rule belongs on the search and not on the
   deliverable — and the underlying question is unmeasured.
8. **Session 11's two proposals**: warm-start the policy and the baselines from
   designs with f_peak margin ≥ 0.133 oct and peaking margin ≥ 1.0 dB; and shape
   the S3 reward on the two **folded** margins rather than on peaking and
   `f_peak` directly.

---

## K. Decisions inherited from the SerDes framework (context, not Nebula)

Listed briefly because they constrain what the link layer can borrow.

- **Seeds are threaded through `LinkConfig.seed` only** — never
  `np.random.seed()` (G3).
- **Compare RX bits against LINE bits**, not source bits, for scrambler
  coherence (G2).
- **FFE cursor convention**: warm starts place the cursor at the configured
  index (G4).
- **Do not RMS-AGC a peaked waveform**; use pulse-cursor gain calibration (G5).
- **Never let sign-sign LMS adapt during CDR acquisition** (G9).
- **Windows console is cp1252** — no non-ASCII glyphs in `print()` (G10).
- **`rtl/`, `verification/`, `veriloga_models/`, `matlab_models/`,
  `ml_equalizer.py`, `optical_dsp.py`, `visualization.py`, `Makefile` are
  NOT AUDITED** and are treated as untrusted. The Phase-0 experience says assume
  bugs: the inherited 6.8k-line starter code "looked complete" and contained
  many correctness bugs.
- **Power numbers in the SerDes framework are literature-based placeholders**,
  never simulated. (Nebula's S6 is measured, and billed on measured supply
  current.)
