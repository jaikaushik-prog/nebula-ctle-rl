# RL_SMOKE.md — running the loop end to end, badly, on purpose

**Task 6.** Session 17, 2026-08-07.

> The goal is not a good policy. The goal is to surface every integration bug
> between three layers that have never been run together. Each failure, with
> its cause and fix, is the deliverable — a run that works first time means the
> test was too easy.

---

## The result this document exists to report

> **A quarter of the evaluations in a naive RL loop return a number that looks
> valid and is not — and 78 % of those score HIGH under a reward that measures
> peaking.**

Measured, on real SKY130 artifacts, over 500 PPO steps: **765 evaluations,
26.5 % invalid, of which 78.3 % are a fictitious peak reported at the edge of
the simulator's own search range.** Every one of those 159 would have been a
*high* reward for a circuit with no peak at all.

That is the verification contribution of this work, quantified. It is not a
diagnostic and it is not a footnote about our implementation: it is a statement
about what an RL loop over a SPICE simulator does when nobody checks, and
**nobody in this literature reports it because nobody checks.** The reference
implementation this project builds on (`ams_rl_ppo`) runs against a synthetic
analytic simulator with no PDK, so the failure mode cannot arise there; the
paper it comes from optimises at nominal only. The number belongs in the
abstract and on a slide.

The three mechanisms, in full, are §5. The guard that catches them is not
defensive programming — it is doing four fifths of its work against one failure
mode, and without it the reward curve in §9 would have been a curve of the
policy learning to exploit `meas ac MAX`.

---

**Seven integration failures were found.** Five of them produce a plausible
number and raise nothing; two of those would have produced a training run that
reports a policy while scoring a circuit that does not exist, and one would have
put a wrong conclusion into a cost table. They are §2.

**No conclusion about learning is drawn from 500 steps, and none is offered.**
The reward curve in §9 is presented as evidence that the plumbing carries a
gradient, and nothing else. No hyperparameter was tuned. The mean episode
return over the run goes −2.98 → −6.16 → −4.54 → −3.09 → −0.50 across five
buckets of episodes: non-monotone, and consistent with a policy that has
learned nothing. **That is the expected outcome and it is stated rather than
smoothed.**

---

## 0. Assumptions

Every number here was measured on this machine on 2026-08-07 under these
conditions. Anything not on this list was not held fixed.

| | |
|---|---|
| Simulator | ngspice 41, conda env `nebula`, `ngspice_con.exe` (G20) |
| PDK | SKY130A via volare at `C:\Users\DELL\sky130A` (G33) |
| Library | **`sky130_ctle.lib.spice`** — the extended trim, 25 sections (G58) |
| Passives | **REAL drawn SKY130 devices** via `to_geometry()` (task 4i) |
| Tail | current mirror, N = 8, one device per side; `I_ref` still ideal |
| Corner | **TT / 1.00 VDD / 27 °C only.** One corner. |
| Load | `cl` fixed at **`cl_mid` = 32.63 fF**, CONTEXT not action |
| `nf_in` | **fixed at 4**, not searched (G38) |
| Spec target | one fixed point: 7.5 dB, 1.7678 GHz (both mid-window) |
| Seed | 20260807, threaded through `EnvConfig`/`PPOConfig` only (G3) |
| Tests | **1007 → 1246 green** (92 + 1154), 9 deselected |

**Not scored, and each is a conclusion rather than a gap:**

- **S4 (HD3)** — needs transient + FFT; `.disto` returns exactly 0.0 for BSIM4
  (G21), at ~4× the cost of AC + noise. Belongs in a promotion tier.
- **S7 (area)** — a device-area number now exists, but it excludes routing,
  enclosure and the transistors, so it is a lower bound. §5 also measures that
  it is *unstable* against the electrical target by 15×, which makes scoring it
  worse than not scoring it.
- **S8 (eye)** — a link-layer metric, and the link layer is a mock end to end
  (G16). §3 makes any path from a training run to a mock structurally
  impossible, so **S8 cannot be scored here.** That is the correct outcome, not
  a limitation to work around.

**No analytic quantity is anywhere in the reward path.** §6a asks for this to
be stated and it is enforced structurally: every scored number is a measured
SPICE primitive or arithmetic on measured primitives —
`peaking_db = g_pk_db − g_dc_db`, `nyq_boost_db = g_nyq_db − g_dc_db`, `f_peak`
from `meas ac MAX`, power from the **measured** supply branch, margins from
`@m[vds]` and `@m[vdsat]`. The §6 design equations appear exactly once in this
session, as the **expected directions** of the §4 sensitivity gate, and they
are fit for that and nothing more: G60 measured them over-predicting the
Nyquist boost by **+0.77 to +1.47 dB**, growing with `R_s`.

---

## 1. The environment contract

Written before the implementation, and it lives in
[`rl/contract.py`](rl/contract.py) — this section is a summary, not a second
definition.

### 1.1 Action — seven continuous dimensions

Each action is a **delta** in normalised space, clipped to `MAX_STEP` = 0.15 of
the box per dimension per step. The policy never proposes an absolute sizing;
it proposes an edit and sees the result before the next one. Normalised space
is `[0,1]`, **log-scaled where the box spans decades and linear where it does
not**, so a delta of 0.10 is a fixed *ratio* on a resistance and a fixed
*increment* on a width.

| name | lo | hi | metric | unit | provenance |
|---|---|---|---|---|---|
| `w_in` | 20 | 100 | linear | µm | `PROPOSED_BOX` |
| `l_in` | 0.15 | 1.0 | log | µm | `PROPOSED_BOX` |
| `i_bias` | 0.5 | 8.0 | log | mA | `PROPOSED_BOX` |
| `rs` | 50 | 1000 | log | Ω | `PROPOSED_BOX` |
| `cs` | 100 | 10000 | log | fF | `PROPOSED_BOX` |
| `rl` | 50 | 800 | log | Ω | `PROPOSED_BOX` |
| `vcm_in` | 1.1 | 1.6 | linear | V | `PROPOSED_BOX` |

**All seven edges are `s3_yield.PROPOSED_BOX` verbatim.** Nothing here was
chosen by an agent, and `common/params.py` is untouched (rule 6). A test
asserts every edge against `PROPOSED_BOX` so the two documents cannot drift
into describing "the same" box differently — G32's failure, moved from a model
card onto a parameter range.

**`nf_in` is FIXED at 4 and is not an action.** G38 measured that on SKY130 `W`
is the *total* width and `nf` only splits it into fingers: at W = 40 µm,
1.5 mA/side, `nf` = 1, 2, 4, 8, 16, 32 gives gm = 14.22, 13.68, 12.62, 13.12,
12.29, 11.79 mS — **±10 %, non-monotonic**. A policy gradient on a
non-monotonic ±10 % axis learns the noise rather than learning to ignore the
axis, and spends samples doing it. 4 is inside `PROPOSED_BOX`'s 1–8 range.

**THE WHOLE TAIL IS DERIVED, NOT SEARCHED — and this is a reversal.**
`tail_j` (tail width per amp) and `l_tail` were actions in the first version of
this contract, following task 6c. The §4 gate cleared them both as *live* —
and then supplied the measurement that removed them:

| dim | channel | \|d_obs\| under one `MAX_STEP` |
|---|---|---|
| `vcm_in` | `tail_margin_v` | **0.6050** |
| `tail_j` | `tail_margin_v` | 0.1008 |
| `l_tail` | `tail_margin_v` | 0.0982 |

**`vcm_in` is a 6× stronger lever on the tail margin than either tail axis is**,
on the quantity the tail geometry exists to control. That is the `nf_in`
argument again (G38): a policy gradient on a weak, **redundant** dimension
learns noise and spends samples doing it. Human decision, 2026-08-07: remove
them. **9 dimensions → 7**, which at ~142 episodes per 500 steps is worth a
great deal.

What replaces them is the practice the rest of the project already uses: fix
the current, fix a target `vdsat_tail`, size from those, then **verify**.
`w_tail = i_side × TAIL_UM_PER_AMP` at `l_tail = TAIL_L_UM`, imported from
`s9_yield.py` so there is exactly one definition (rule 9).
`TAIL_UM_PER_AMP` = 111.2k µm/A is the **`ss/0.95/125 °C`** width for
`vdsat_tail` = 0.20 V — the corner where the tail needs the *most* width for a
given `vdsat` (111.2k against 58.3k at TT and 43.7k at FF), so sizing there
keeps it saturated everywhere rather than only at nominal.

**Removing the degrees of freedom does not remove the constraint.**
`tail_saturation` remains an active, scored constraint, and it is still the
only row in the spec table coupling five box coordinates — `vds_tail` *is* the
input pair's source node. What is gone is the redundant freedom to move the
tail independently of the current it has to sink, which `TAIL_DEVICE.md` §6
records as producing "tails that are the wrong size for their own current".
`nf_tail` is derived from the per-finger bin ceiling (G53) and never was an
action.

This is `HANDOFF` **G73**, and the transferable habit is: **read a sensitivity
table for REDUNDANCY, not only for zeros.** A table reporting pass/fail against
an inert threshold cannot see this, which is why §4's reports `|d_obs|` per
dimension per channel.

**The disagreement this settles, recorded because it was live for one session.**
`TAIL_DEVICE.md` §6 recommended that *none* of the tail dimensions enter the
action space; task 6c asked for tail geometry as an action. The first version
of this contract followed task 6c, on the grounds that §6's recommendation had
no RL measurement behind it. The gate supplied one, and it agreed with §6.
**The recommendation is now closed rather than standing** — with a number
attached, which is what it was missing.

### 1.2 Context — told to the policy, not movable

- **`cl` = 32.63 fF (`cl_mid`).** Settled in task 2 and re-derived in
  `CL_RANGE.md`. Nobody chooses the following stage's input capacitance, and
  G42 measured that *searching* it lowers the yield. An agent that could choose
  its own load could buy S3 by declaring a load nobody will build.
- **the corner set** — TT only, this run.
- **the target spec** — one fixed point.

### 1.3 Observation — 18 dimensions, fixed scales

| idx | block | dims |
|---|---|---|
| 0–6 | current sizing, normalised box coordinate | 7 |
| 7–14 | last measurement | 8 |
| 15–16 | target spec | 2 |
| 17 | step index / horizon | 1 |

The measurement block still carries `tail_margin_v` even though the tail is no
longer an action. That is deliberate: the tail's headroom is a *consequence* of
`vcm_in`, `w_in`, `l_in` and `i_bias`, all of which the policy does move, so it
is exactly the coupled feedback an observation exists to provide.

**Scales are FIXED and derived from the box and the spec table, never from
running statistics.** A running normaliser makes the observation a function of
the run's own history, so the same circuit reads differently in two runs and
nothing reproduces. Reproducibility beats a slightly better conditioned input;
a test asserts that 50 intervening observations do not move the normalisation
of a repeated one.

| channel | unit | centre | scale | basis |
|---|---|---|---|---|
| `g_dc_db` | dB | 0 | 20 | measured box spread, −15.3 to +6.0 dB |
| `peaking_db` | dB | 7.5 | 9.0 | S3's 3–12 dB band: centre, and twice its half-width |
| `f_peak_oct` | octaves | 0 | 2.0 | `log2(f/2.5 GHz)`; S3's window is **exactly one octave** |
| `nyq_boost_db` | dB | 0 | 12 | S3's ceiling |
| `inoise_vrms` | V rms | 0 | 1.5e−3 | S5's limit |
| `power_w` | W | 0 | 15e−3 | S6's limit |
| `pair_margin_v` | V | 0 | 0.3 | `vds−vdsat`; 0.28 V at the reference point |
| `tail_margin_v` | V | 0 | 0.1 | `vds_tail−vdsat_tail`; the 100 mV of §6's reward |

`inoise` is **RMS volts and is not square-rooted** —
`tests/test_noise_units.py` exists because that was got wrong once. `f_peak`
enters in **octaves and never in hertz**: every other frequency result in this
project is in octaves, S3's window is exactly one, and a hertz-linear encoding
makes a 17 GHz miss and a 40 mV miss incomparable, which is the whole argument
of `TAIL_DEVICE.md` §7.

**There is no "missing measurement" encoding, because there cannot be one.**
The sizing is evaluated at reset, so the measurement block is always real; an
invalid evaluation terminates the episode (§5) rather than becoming a
zero-filled observation for a circuit that does not exist.

### 1.4 Episode — horizon 8

Terminates early on success (all specs met) and on an invalid evaluation.
Nothing else terminates it; the horizon **truncates**, which is a different
thing and is kept different all the way into the GAE recursion — PPO
bootstraps through a truncation and not through a termination, so conflating
them would credit a broken circuit with the value of whatever came next.

Why 8:

- `MAX_STEP` = 0.15, so 8 steps reach **1.2 box-widths** — enough to cross the
  box from any start. A horizon that cannot reach the far side makes the
  *start* the binding variable and the run measures initialisation.
- At the measured ~2.07 s per evaluation, 8 steps is ~17 s of SPICE per
  episode. 500 steps then buys 142 episodes: enough to exercise the plumbing in
  every state it can reach, far too few to learn anything. That asymmetry is
  deliberate.
- Credit assignment over 8 steps is trivial, so a flat return curve cannot be
  blamed on the horizon.

---

## 2. What broke

Seven failures. Each is listed with what it would have done had it not been
caught, because in five of seven cases the answer is "produced a plausible
number and raised nothing".

### F1 — `alter` on a passive that no longer exists (~25 min)

**Found:** while wiring drawn passives into `sky130_runner`.
**Symptom, had it shipped:** `run_tunable_sweep` writes `alter Rdeg` /
`alter Cdeg`, which name the *ideal* elements. Once the passives are drawn
those instances do not exist, ngspice reports the failed `alter` as a
**warning** and exits 0 (G26), and every one of the 67 settings comes back
carrying the **first** geometry's numbers — a converged-looking sweep of a
single point.
**Fix:** `run_tunable_sweep` refuses `passives is not None` outright, with the
reason in the failure string. Pinned by a test.
**Class:** silent success. This is G35 wearing different clothes: the same
"alter accepted, device unchanged, numbers plausible" shape, on a passive
instead of a transistor.

### F2 — the sensitivity gate probed one direction only (~20 min)

**Found:** by §4's gate, which reported `i_bias` as a failed dimension and
blocked training.
**Cause:** `i_bias` is not inert. Perturbing it **+0.15 of the box** takes
3.25 mA → 4.93 mA, which raises gm enough to push the peak clean out of the
sweep; the §5 validity gate then correctly rejected the result at
`f_pk` = 19.95 GHz. A one-sided probe conflates *"this axis does nothing"* with
*"this axis leaves the feasible region"*, and those need opposite responses.
**Fix:** try both directions; report `INVALID BOTH` only if neither produces a
circuit, which is a real finding about the base point rather than about the
axis.
**Class:** a gate that fails for the wrong reason is as bad as one that passes
for the wrong reason — it gets disabled.

### F3 — the validity gate rejected every low-boost design (~35 min)

**Found:** by §7's calibration, which is exactly what §7 is for. The "flat"
reference design and the "operating point fails" reference design scored
**identically**, both at the invalid floor, so the three-way ordering §6f
requires could not be tested at all.
**Cause:** the gate used `Sky130Point.has_interior_peak`, which is the
conjunction of two conditions that reject **different things**:

| condition | what it rejects | is the measurement wrong? |
|---|---|---|
| `g_pk − g_top ≤ 0.25 dB` | response still **rising** at 20 GHz, so `meas ac MAX` returned the range edge | **yes** — `peaking_db` is fictitious and large |
| `peaking_db ≤ 0.25 dB` | a genuine interior maximum that is merely **small** | **no** — the circuit simply does not equalise |

Measured examples of each: `rl` = 800 Ω at 3.25 mA reports **1.08 dB of
"peaking" at 19.95 GHz** with `g_pk − g_top` = −0.001 dB (fictitious);
`rs` = 50 Ω reports **0.165 dB at 1.318 GHz** with `g_pk − g_top` = 9.23 dB
(true, and useless as an equaliser).

Rejecting both made **every low-boost design invalid** — that is, it erased the
reward gradient over the entire bottom of the box, which is precisely where a
randomly initialised policy starts. The policy would have seen the floor
everywhere and had nothing to climb.
**Fix:** split the property. `peak_is_sweep_edge` carries the G44 half alone
and is what the validity gate uses; `has_interior_peak` keeps both halves
unchanged, because `s3_yield.py`, `s9_yield.py` and `robust_geometry.py`
publish counts that use it and those must not move.
**Class:** a guard built for one failure quietly doing a second job nobody
asked for.

### The rule F3 generalises into, and it is worth more than the fix

A validity gate and a reward answer **different questions**:

| | asks | of the two results below |
|---|---|---|
| **validity gate** | *can I trust this measurement?* | rejects the 19.95 GHz peak |
| **reward** | *is this circuit good?* | scores the 0.165 dB peak, badly |

A **0.165 dB peak at 1.318 GHz** is a *trustworthy measurement of a bad
circuit* — low reward. A **peak at 19.95 GHz** is an *untrustworthy
measurement* — invalid. Same-looking output, opposite handling. Conflating them
destroys the gradient exactly where a fresh policy lives.

This is now `HANDOFF` **G72**, and §6.4 carries it further: trustworthiness is
per *analysis*, not per evaluation, which is what Call 1 below is built on.

### F4 — the validity gate reported a symptom, not a cause (~10 min)

**Found:** the same calibration. The `op_fail` reference — `rl` at the box
ceiling — was rejected as *"f_pk is outside its range"*, when what had actually
happened was that the load drop took the input pair **out of saturation**.
**Cause:** the AC plausibility checks ran before the DC operating-point checks.
If the bias point is wrong then every small-signal number describes a different
circuit, so the operating point is the cause and the AC oddity is downstream of
it. A gate that names the symptom sends whoever reads the log to the wrong
file.
**Fix:** `validate()` now runs presence → **operating point** → **device
regions** → AC plausibility → G44. Pinned by a test that constructs a result
failing both and asserts the reported reason is the triode one.

### F5 — the G44 rejection was invisible in the invalid histogram (~10 min)

**Found:** in the first 12-step trial run. All six invalid evaluations were
bucketed as `f_peak_range`, so the run reported a numerical oddity where the
mechanism was a fictitious peak.
**Cause:** the `f_peak` *range* check (10 MHz – 18 GHz) fires on the same
results as the sweep-edge check, and ran first.
**Fix:** the sweep-edge test moved ahead of the range test, and got its own
bucket. **This mattered:** in the 500-step run, `peak_is_sweep_edge` is
**159 of 203 invalid evaluations — 78 %**. Under the original ordering, the
single largest thing the agent was doing would have been reported as an
`f_peak` range anomaly.

### F6 — `shutil.which` cannot find this project's ngspice (~5 min)

**Found:** the one end-to-end env test skipped instead of running.
**Cause:** `shutil.which("ngspice_con")` misses the conda-env binary that the
whole project uses (G20); `ngspice_path()` knows where it lives.
**Why it matters more than it looks:** a skipped test reports as a pass. The
only test exercising the real simulator was silently not running.

### F7 — the parallel benchmark measured its own pass order (~15 min)

**Found:** by noticing that the 2-worker pass reported a **2.55× speedup**,
which two processes cannot produce.
**Symptom, had it shipped:** the sweep reported **4.39× at 11 workers**, better
than G48's 3.18×, and the explanatory sentence was already written — *"the
extended library's longer compute phase amortises process launch better"*. It
is an artifact of the 1-worker pass running **first, on a cold OS file cache**.
Reversing the order drops the serial baseline **2.7×** and the honest answer
becomes **2.64× at 8 workers, with 11 slower than 8** — i.e. the extended
library scales *worse* than the nfet-only one, not better.
**Fix:** run the sweep both ways and quote the warm-cache numbers. §8.
**Class:** a number that looks right, in a benchmark. The general rule —
*randomise or reverse the order of a benchmark's passes, and treat a
super-linear speedup as a bug report* — is the transferable part.

### A near-miss that is not on the list

The two SPICE timings quoted in §8 are not symmetric in confidence, and it is
worth saying which is which. The **v0 run's** decomposition was taken on a
quiet machine and matches an isolated single-point measurement (2.07 s against
1.93–2.26 s), so it is trustworthy. The **v1 run's** was not: it overlapped a
pytest run that calls ngspice and came out at 5.4 s per evaluation. Rather than
average the two or quietly prefer the better one, **v1's timings are discarded
entirely** and only its load-independent results are quoted. The mechanism —
one concurrent ngspice costs **4.8×** against the extended library, four times
worse than G48's 1.13× on the nfet-only one — is itself the finding, and it is
G70.

### What did NOT break: removing the mocks (§3)

§6b: *"Report what broke when you removed them. If nothing broke, check that
the removal actually took effect before believing it."*

**Nothing broke**, and the check was made. `device/mock.py` and `link/mock.py`
were already imported only by `tests/conftest.py` and five test modules — never
by anything on a production path. So the honest report is that the structural
risk §6b is aimed at did not exist in the form it anticipated.

The verification is in §3 and it is deliberately not a self-report.

---

## 3. Removing the mocks structurally (§6b)

> A flag can be set wrong; an import cannot resolve to a module that is not
> reachable.

`nebula/tests/test_no_mocks_in_training_path.py`, 9 tests.

**It runs in a subprocess, and that is the whole design.**
`nebula/tests/conftest.py` imports `nebula.device.mock` at collection time, so
by the time any test in this suite runs the mock is already in `sys.modules`.
Asserting on *this* process's `sys.modules` would be vacuously false — or,
worse, vacuously **true** if the conftest import were ever removed, which is a
gate that passes for the wrong reason. A fresh interpreter is the only place
"what does importing the training entry point pull in?" has an answer.

Seven entry points are checked: `experiments.rl_smoke`, `rl.env`,
`rl.evaluator`, `rl.contract`, `rl.reward_v1`, `rl.ppo`, `rl.runlog`. All
clean.

**The gate is proved able to fail.** `test_the_gate_can_fail` runs the *same*
probe against a script that imports a mock on purpose and asserts it goes red.
Without it, a probe that silently stopped working — a renamed module, a changed
prefix, a subprocess no longer reaching the repo — would report clean forever.

**The real structural risk is different from the one §6b names, and it is now
pinned.** The *link layer* is a mock end to end (G16). Any future reward term
touching S8 would reach `link/mock.py`, and that is a plausible, well-shaped,
entirely fabricated eye height flowing into a training run.
`test_link_layer_is_not_on_the_training_path_at_all` asserts that importing the
reward, the env and the evaluator pulls in **no `nebula.link` module at all**.
That is what makes a future S8 term a red build rather than a discovery in
September.

---

## 4. The action-response sensitivity gate (§6e)

> This catches the failure mode that has bitten this project more than any
> other — a parameter that is written, accepted, and silently ignored. `alter`
> on W did it, `mult` does it, `w` on fixed-width resistors does it. If one
> action dimension is inert, PPO will still train, still produce a curve, and
> still report a policy, and nothing will raise.

**Blocking, and it did block** — see F2.

Base point: **design 432**, the sole corner-and-load-robust survivor, chosen
because it is known to simulate cleanly at every corner and load. A base near a
failure boundary would produce invalid perturbations and hide the answer.
Perturbation: **one `MAX_STEP` = 0.15 of the box**, one dimension at a time —
so the gate measures what a *single action* is worth, not what an arbitrarily
large one is. Direction chosen for validity (F2). `d_obs` is in the
observation channel's own normalised units, i.e. after division by the fixed
scales of §1.3. Inert threshold: `|d_obs| < 0.01`, a hundredth of a channel
scale; a genuinely ignored parameter moves it by exactly 0.0.

| dim | channel | physical, before → after | `d_obs` | want | got | verdict |
|---|---|---|---|---|---|---|
| `w_in` | `peaking_db` | 89.26 → 77.26 µm | −0.0282 | −1 | −1 | **PASS** |
| `l_in` | `peaking_db` | 0.399 → 0.531 µm | −0.0671 | −1 | −1 | **PASS** |
| `i_bias` | `power_w` | 3.252 → 2.146 mA | −0.1336 | −1 | −1 | **PASS** |
| `rs` | `peaking_db` | 318.6 → 499.3 Ω | +0.2947 | +1 | +1 | **PASS** |
| `cs` | `f_peak_oct` | 1.901 → 3.793 pF | −0.2325 | −1 | −1 | **PASS** |
| `rl` | `f_peak_oct` | 565 → 372.8 Ω | +0.1993 | +1 | +1 | **PASS** |
| `vcm_in` | `tail_margin_v` | 1.407 → 1.482 V | +0.6050 | +1 | +1 | **PASS** |

**7/7.** Every action dimension is live and moves its expected channel in the
expected direction.

**The two rows that are no longer here are the reason the space is seven
dimensions and not nine**, and they are kept in
`rl_smoke.RETIRED_SENSITIVITY` rather than deleted, because the numbers *are*
the argument:

| dim | channel | `d_obs` | verdict |
|---|---|---|---|
| `tail_j` | `tail_margin_v` | +0.1008 | PASS — live, and **6× weaker than `vcm_in`** |
| `l_tail` | `tail_margin_v` | −0.0982 | PASS — live, and **6× weaker than `vcm_in`** |

Both were live. Neither was *dead*. They were removed for **redundancy**, not
for weakness — see §1.1 and G73.

Two more things the table says that a pass/fail count does not:

1. **The surviving dimensions differ in strength by 21×.** `vcm_in` moves the
   tail margin by 0.605 of a channel scale under one action; `w_in` moves
   peaking by 0.0282. Both are live, but a policy has 21× more leverage per
   step on one than the other, and that is a property of the *box* —
   `vcm_in`'s range is 0.5 V wide and `v(s1)` tracks it almost 1:1, while
   `w_in`'s 20–100 µm range moves gm sub-linearly.
2. **`w_in` and `l_in` are the two weakest survivors**, and both act on peaking
   through gm, where `rs` acts on the same channel 4–10× harder. Worth carrying
   into task 7: an axis that is live but weak is not free — it is where a
   policy gradient spends samples confirming a small effect. Whether `w_in`
   survives the same redundancy test `tail_j` failed is not yet measured.

---

## 5. The evaluator is poison-safe (§6d)

> An RL agent is an adversarial search for exactly those regions, because a
> garbage result that happens to score well is a free reward.

Every evaluation is either **valid** — every required quantity present, finite,
physically plausible, operating point inside the rails, both transistors in
their intended region — or **invalid**, which is a hard negative reward and a
terminated episode. Never a missing value, never a substituted default, never a
retry that quietly succeeds with different numbers.

The checks, in the order they run (F4 fixed that order):

1. **Presence and finiteness** of 20 required primitives, the tail's among
   them. G54: `.noise` can return `inoise_total = -nan(ind)` and exit 0, and a
   NaN carried into a spec check reads as a genuine *failure* because
   `nan < tau` is False — biasing a yield downward, silently.
2. **DC nodes inside the rails**, 50 mV of slack.
3. **Both transistors in saturation**, and `gm > 0`. Saturation is a *validity*
   condition, not a spec: outside it the small-signal numbers answer a
   different question.
4. **Plausibility** — gain in [−80, +60] dB, noise in [1 nV, 1 V] rms, supply
   current in [1 µA, 100 mA] and **positive** (a supply *sourcing* current is
   not the requested operating point), `f_peak` in [10 MHz, 18 GHz].
5. **The reported peak is not the sweep edge** (G44) — the F3 split.

**The retry policy is deliberately narrower than `s9_yield.py`'s.** That script
retries once and is right to (G45: transient Windows process-launch failures do
not reproduce). Here a retry fires only on a **launch-shaped** failure, because
a retry that succeeds with *different numbers* would make the environment
non-deterministic in a way the policy can exploit. Every retry is charged to
the SPICE budget either way.

### The invalid rate, over the 500-step run

| | |
|---|---|
| overall | **26.54 %** (203 / 765) |
| first half | 28.80 % |
| second half | 24.28 % |

**It does not rise.** §6d asks for this specifically — *"if it rises over the
run, the agent is finding the holes"* — and over 500 steps it falls slightly.
The honest reading is that 500 steps is far too few to distinguish a falling
trend from noise, and the useful output is not the trend but the **mechanism
histogram**:

| mechanism | count | share of invalid |
|---|---|---|
| `peak_is_sweep_edge` (G44) | **159** | **78.3 %** |
| `tail_triode` | 28 | 13.8 % |
| `pair_triode` | 16 | 7.9 % |
| everything else | 0 | — |

**Four fifths of everything the agent found was G44.** A response still rising
at 20 GHz, reporting a large fictitious `peaking_db` at the search edge. Under
reward v0 — which scores S3 peaking — every one of those 159 would have been a
**high** reward for a circuit with no peak at all. That is the single most
important number in this document: the guard is not defensive programming, it
is load-bearing, and it is doing 78 % of its work against one failure mode.

`unrealisable_geometry` never fired, and a test explains why: **the whole
`rs`/`rl` box is realisable.** `PASSIVES.md` §4.2's 1444 Ω head-resistance
floor at w = 0.35 µm reads like the low end of the 50 Ω bound being
unreachable; it is a *per-width* floor, and `to_geometry`'s width ladder plus
`m ≤ 8` clears it everywhere down to 20 Ω.

### Cross-check against an independent recomputation

**14 samples, 14 agree, disagreement rate 0.0 %**, all exact (`rel = 0`).

The independent path is genuinely independent: the sampled point is
**re-simulated** (a second SPICE call, charged to the budget), the raw stdout
is retained, and `crosscheck.derived_ac` re-parses the `meas` lines itself and
forms `peaking_db` and `nyquist_boost_db` from its own `DerivedAc`. So
agreement is evidence that the parse *and* the arithmetic are right, rather
than evidence that one function agrees with itself. `derived_ac` also refuses
to run on output containing warning-shaped failures, so a G26-class run cannot
reach the comparison.

The re-simulation is what makes it more than a unit test: a simulator that was
not deterministic for a fixed netlist would show up here, and does not.

---

## 6. Reward v0 and v1

### 6.1 The shape, and what it supersedes

`rl/reward.py` implements CLAUDEwa.md §9's form — a sum of shortfalls each
divided by `|value| + |target|` — and it is kept and still tested, because it
is the contract §9 specifies. `rl/reward_v1.py` implements the shape the human
decision of 2026-08-06 put in its place, and that decision was a **retraction**
by the person who made the original proposal:

> `min` has the same pathology as the first-failure table, one layer down: it
> reports `S3_f_peak` for as long as that misses by 17 GHz, so the agent gets
> **no gradient on `tail_saturation`** — a constraint binding on 13.3 % of the
> box at slow-hot — until S3 is nearly solved.

```
shortfall_i = max(0, -margin_i / tol_i)          # zero when spec i is satisfied

if any shortfall_i > 0:                          # infeasible
    r = -sum( clip(shortfall_i, 0, 1) )          # gradient on EVERY violation
else:                                            # feasible
    r = B + min_i( margin_i / tol_i )            # now seek margin

r -= lambda * simulation_cost_of_this_step
```

`B = N + 1` and the bound is **exact rather than tuned**: infeasible scores lie
in `[−N, 0)` because every shortfall is clipped to 1, and feasible scores are
`B + min(margin/tol)` with the min ≥ 0 by definition. `B ≥ N` suffices; `N + 1`
leaves one unit so the bands cannot touch at the boundary. Change `N` and `B`
follows — it is not a knob.

### 6.1a Four bands, because trustworthiness is per analysis (Call 1)

The first version had two non-scoring outcomes: score it, or floor it. That was
wrong, and §2's rule is why — a device in **triode** is a *trustworthy
measurement of a bad circuit*, while a peak at **19.95 GHz** is an
*untrustworthy measurement*. `vds` and `vdsat` both come from `.op`; if `.op`
converged they are true whether or not the device is saturated. Only the
AC-derived spec set has to be dropped.

So the evaluator returns three verdicts and the reward has four bands:

| band | range | when |
|---|---|---|
| **feasible** | ≥ `N+1` | every spec met; seek margin |
| **infeasible** | `[−N, 0)` | gradient on every violation |
| **headroom-only** | `(−(N+2), −(N+1)]` | `.op` good, device in triode — **graded** |
| **invalid** | `−(N+3)` | nothing trustworthy — floor, no gradient |

Every boundary is a function of `N` alone; none is tuned. At `N = 7`:
feasible ≥ +8, infeasible `[−7, 0)`, headroom `(−9, −8]`, invalid `−10`.

**Why the graded band exists rather than being tidy.** `tail_saturation` binds
on 2.6–13.3 % of the box, so a fresh policy lands in triode often, and a flat
floor there gives it **no direction out**. Measured on the `op_fail` reference
— 293 mV into triode on the pair, 81 mV on the tail — the score moves from the
floor (−10.0) to **−8.746**. The grading, strictly ordered at every depth:

```
   -1 mV -> -8.0099      -100 mV -> -8.5000
  -10 mV -> -8.0909      -300 mV -> -8.7500
  -50 mV -> -8.3333     -1000 mV -> -8.9091
```

**One design detail that is not a preference.** The band uses the bounded map
`h/(1+h)`, **not** the `clip(h, 0, 1)` used everywhere else. The clip exists in
the infeasible branch so one catastrophic spec cannot drown out the others in a
*sum*; here there is no sum — this is a single ordering quantity — so a clip
buys nothing and costs exactly what the band exists for: a design 500 mV into
triode would score identically to one 50 mV in. A test asserts strict ordering
across 1 µV to 5 V of triode depth.

**What is NOT graded, and why.** A DC node outside the rails on a converged
`.op` is **invalid**, not headroom-only: it means the netlist or the topology
is wrong, so there is no trustworthy headroom to grade. The distinction is that
triode is a *bad bias point*, and a node outside the supply is *not a bias
point at all*.

**This supersedes §9.3's recommendation in the first version of this document**,
which argued for accepting the ungraded floor on the grounds that grading a
triode design's small-signal numbers would be grading fiction. That argument is
correct and is preserved — it is exactly why `meas` is `None` on this branch
and the AC spec set cannot be scored. What it missed is that the *DC* numbers
are not fiction, and they are enough to order the band.

### 6.1b The invalid floor

`−(N + 3)`: strictly below the whole headroom band, whose floor is `−(N+2)`.
More negative would be a tuned penalty; equal to the headroom band would let
the policy prefer a crash to a triode design it could climb out of. It is a
**distinct branch**, not a shortfall of 1.0 everywhere, so an invalid result
can never be confused with a design that merely misses everything.

`lambda_cost` is **0.0** for this run and the reason is stated rather than
defaulted: cost per step is constant here (one SPICE call, one corner), so the
term would be a constant offset that changes no ranking and only obscures the
curve. The parameter exists because the term becomes real the moment a fidelity
scheduler makes cost vary per step, and it should not appear later as a new
idea.

### 6.2 Normalisation — the entire point

§9's `(|x| + |τ|)` denominator is scale-free but not *meaningful*: it makes a
shortfall depend on the magnitude of the quantity rather than on how badly the
design misses. 17 GHz against 2.5 GHz and 40 mV against 200 mV both normalise
to something near −1, which destroys exactly the distinction session 13 paid to
discover. Each `tol_i` answers one question — **what miss is worth caring
about, in this quantity's own units?**

| spec | tol | unit | basis |
|---|---|---|---|
| `S3_f_peak` | **0.5** | octaves | S3's 1.25–2.5 GHz window is **exactly one octave**, so 0.5 is its half-width. Margin is `0.5 − \|log2(f/f_target)\|`, i.e. §6h's form with the half-width folded in. |
| `S3_peaking` | **1.0** | dB | distance outside the 3–12 dB band. 1 dB is production CTLE tuning granularity, so ±0.5 dB would be *tighter than the hardware*. |
| `S3_nyq_boost` | **1.0** | dB | boost at Nyquist below 0. CLAUDEwa.md §3 reads S3 as requiring positive boost where the data is; 1 dB below its own DC gain is meaningfully worse than a wire. |
| `S5_noise` | **0.5 mV** | V rms | one third of S5's 1.5 mV limit. Measured free (90.7 % of the box), so the tolerance only has to produce gradient where it binds. |
| `S6_power` | **5 mW** | W | one third of S6's 15 mW limit, same argument. |
| `saturation` | **0.1** | V | `vds − vdsat`; 0.28 V at the reference point, so 0.1 V is a third of the way to triode. |
| `tail_saturation` | **0.1** | V | `vds_tail − vdsat_tail`. **The tolerance the whole retraction is about**: session 13's tail misses are tens of millivolts and must not be invisible next to a 17 GHz `f_peak` miss. |

**These seven are human-set, not agent-chosen** (rule 6). Every one was
specified in the task 6h brief or follows from a spec limit by a stated rule;
where the brief said "something like 100 mV", the value is 100 mV and it is
recorded as a reporting axis (`TOLERANCE_SCAN`), not a hidden constant.

**Log frequency throughout.** An octave above and an octave below the target
cost exactly the same — a test asserts it — and in linear hertz they would not.
It also matters that `f_peak` is quantised at **0.0664 octaves** by
`meas ac MAX` on an `ac dec 50` grid (session 11): a linear-hertz tolerance
would be finer than the measurement at the bottom of the window and coarser at
the top.

**The property the retraction is about, asserted:** two designs missing
`S3_f_peak` by the same huge amount, one of which also has the tail 50 mV into
triode, must score differently — and by exactly 0.5, being 50 mV at a 100 mV
tolerance. A companion test first asserts that their **worst** shortfalls are
*identical*, so the demonstration is real: a `min`-over-specs reward would give
them the same score and the tail's entire gradient would vanish.

### 6.3 Calibration on three known designs (§6f)

> If the reward does not order these correctly, the reward is wrong and no
> amount of training will fix it.

| design | what it is | peaking | `f_peak` | tail margin | **v0** | **v1** |
|---|---|---|---|---|---|---|
| **432** | the sole corner-and-load-robust survivor (session 12b) | +7.209 dB | −0.525 oct | +0.327 V | **+4.951** feasible | **+8.951** feasible |
| **flat** | `rs` at the box floor: a wire with gain | +0.165 dB | −0.923 oct | +0.327 V | **−1.155** infeasible on 2 | **−1.155** infeasible on 2 |
| **op_fail** | `i_bias` *and* `rl` at their ceilings | — | — | −0.293 V / −0.081 V | **−4.746** graded | **−8.746** graded |

**Ordered correctly in both**, and under Call 1 `op_fail` is no longer *at* the
floor: `.op` converged, so it lands in the **graded headroom band** — strictly
below every infeasible score and strictly above the invalid floor, at a
position set by how far into triode it is. Both devices are out: **−293 mV** on
the pair, **−81 mV** on the tail.

Each reference differs from 432 in **one or two coordinates only**, holding the
rest fixed — the same paired-comparison discipline `s3_yield.pin_param` uses,
so the reward difference is attributable to the change and not to a different
draw.

`op_fail` measures `vds − vdsat` = **−0.293 V** and
`vds_tail − vdsat_tail` = **−0.081 V**: *both* devices in triode, from two
coordinates that are individually inside their own bounds. That is G28's joint
infeasibility, reached from inside the box.

**One field differs from the session-13 record of design 432 and it is
declared:** `nf_in` is 4 here against 8 there, because §1.1 fixes `nf_in` at 4.
On SKY130 that is a parasitic-level change rather than a different device
(G38), but it means the numbers above are **not bit-comparable** with the
session-13 record. Stated rather than discovered.

Getting here took F3 and F4. Before those fixes, `flat` and `op_fail` scored
identically at the floor and the ordering could not be tested — which is
precisely what §6f exists to catch.

---

## 7. The passives are real, and that moved the answer (§6a, task 4d)

§6a requires `to_geometry()` in the loop from the outset — *"this is what makes
the output a schematic; do not defer it"*. Doing that crosses `PASSIVES.md`
§6's item 1, the **4d regression**, which that document says must pass before
anything downstream is trustworthy. It had not been run. It is run here.

Six designs including 432, TT/1.00/27 °C, ideal `R`/`C` versus drawn SKY130
devices, everything else identical:

| # | Δpeaking (dB) | Δ`f_peak` (oct) | Δnyq (dB) | Δ`g_dc` (dB) | Δnoise (rel) | RL bottom plate ÷2 (fF) |
|---|---|---|---|---|---|---|
| 0 (**432**) | −0.2116 | **−0.1329** | −0.3441 | +0.0001 | +0.0015 | 12.50 |
| 1 | −0.1887 | −0.0664 | +0.0276 | +0.0001 | −0.0027 | 24.28 |
| 2 | −0.0101 | −0.0664 | −0.0222 | +0.0002 | +0.0003 | 1.39 |
| 3 | −0.0603 | −0.1329 | −0.3038 | −0.0002 | +0.0019 | 6.35 |
| 4 | −0.0577 | +0.0000 | −0.0003 | +0.0005 | −0.0001 | 6.21 |
| 5 | −0.0317 | −0.0664 | −0.0020 | −0.0006 | −0.0001 | 4.96 |

**The shift is real, systematic, one-directional, and larger than the slack it
has to fit inside.**

- **Worst |Δ`f_peak`| = 0.1329 octaves**, against the **0.12 octaves of
  centring slack** session 12b measured for the load-robust survivor. The
  drawn passives move `f_peak` by *more than the entire slack budget*.
- Every non-zero shift is **negative**, and the mechanism is exactly the one
  `PASSIVES.md` §4.4 predicted: the drawn load resistors carry a
  `res_po` bottom-plate parasitic and **half of it lands on the output node**,
  adding 1.4–24.3 fF to a `cl` of 32.6 fF — up to **+75 %** — which lowers
  `f_p2` and pulls the peak down with it.
- `g_dc` moves by at most **0.0006 dB** and noise by at most 0.27 %. So this is
  not a general accuracy loss; it is one specific, understood capacitance.
- The Δ values are exact multiples of **0.0664 octaves**, which is
  `meas ac MAX`'s own quantisation on an `ac dec 50` grid (session 11). So the
  shift is **0, 1 or 2 sweep-grid steps** and the measurement is at its
  resolution limit. A finer statement would need a finer sweep, and the
  headline — that it exceeds the slack — does not depend on the resolution.

**Consequence, stated plainly: every corner and load number this project has
published held the passives ideal, and a 0.13-octave systematic shift is
enough to move design 432 out of the window it was selected for.** This
document does not re-run the load screen; it establishes that the screen needs
re-running with drawn passives, which is `PASSIVES.md` §6 items 3 and 4.

### `to_geometry` is electrically stable and geometrically chaotic

A second finding, and it was not expected. Near `rs` = 318.6 Ω, a **0.016 %
change in the target flips the chosen device entirely**:

```
318.50 ohm -> w=8     l=6.720   m=1     area  53.8 um^2
318.55 ohm -> w=10    l=18.780  m=2     area 375.6 um^2
318.58 ohm -> w=2.85  l=4.445   m=2     area  25.3 um^2
318.60 ohm -> w=10    l=8.730   m=1     area  87.3 um^2
319.00 ohm -> w=8     l=14.785  m=2     area 236.6 um^2   <- PASSIVES.md's 432
```

Every one lands within `1e-4` relative of its target, so the **electrical**
answer is stable to four figures. The **geometry** is not:
`resistor_geometry` scans a width ladder and keeps whichever candidate lands
nearest after `l` is snapped to the 5 nm grid, and which one wins is
essentially arbitrary at that resolution.

Two consequences that must not be discovered later:

1. **`design_id` grouping by drawn geometry is fine-grained, not coarse.**
   Measured on the 500-step log: **765 step rows, 765 distinct `design_id`s,
   764 distinct geometry tags.** The grouping is still *correct* — identical
   geometry gives an identical id, which is what task 8's grouped train/test
   split needs — but task 8 must not expect it to collapse many continuous
   `rs` values into one group. It will not.
2. **Area is not a stable function of the electrical target.** A **15× area
   spread across a 0.16 % resistance spread** means any S7 number quoted for a
   design is a property of the quantiser as much as of the design. That applies
   directly to `PASSIVES.md` §4.5's 1506 µm² figure, which is the `rs = 319`
   row above — the `rs = 318.58` row would give 25 µm² for the same resistance.

### The two gates §6a puts in the env

> Fail loudly if `w` is ever written to a fixed-width resistor, and fail loudly
> if `mult` is ever written with a value other than 1. Both were found to be
> silently ignored.

They are enforced at the **device layer, on the assembled netlist text**
(`device/netlist_gates.py`, called from `run_point` immediately before the file
is written), which is strictly stronger than enforcing them in the env: no path
through the device layer can emit an inert write, including one written later
by someone who has not read the file. The env asserts at **construction, every
time**, that the wiring is live — `_assert_netlist_gates_wired()` feeds the
gate three netlists that must be rejected and one that must pass. A gate nobody
watches go red is indistinguishable from one that was deleted (rule 10).

The measurements behind them: `mult=1` and `mult=4` on `res_high_po` both give
**942.90 Ω** — a silent 4× error — while `m=4` gives 235.72 Ω, exactly a
quarter (G56). `res_high_po_0p69` with `w=0.69`, `w=2.85` and `w=99` all give
**2893.64 Ω** identically, and the device that really is 2.85 µm wide reads
718.61 Ω — **4.03× apart**, silently (G57). 29 tests.

---

## 8. Cost accounting, established now (§6i)

**The definition, and it is used everywhere after this:** *every* SPICE
invocation is counted, including those spent on setup, warm start, discarded
episodes, and the §5 cross-check re-runs. The counter is a `SpiceBudget` object
threaded through the evaluator, not a module global, so two environments in one
process cannot silently share one and a test can assert on it. Tests assert
that reset evaluations and **discarded reset draws** are charged.

### The 500-step run

| | |
|---|---|
| environment steps | 500 |
| episodes | 142 |
| **evaluations** | **765** |
| **SPICE calls** | **793** |
| wall clock | **1590 s = 26.5 min** |

| metric | value |
|---|---|
| **simulations per step** | **1.586** |
| seconds per simulation | 2.071 |
| **steps per hour** | **1,132** |
| simulations per hour | 1,795 |

`1.586` sims/step is above 1 because a reset is an evaluation, episodes are
short (142 episodes over 500 steps), and invalid resets are re-drawn — all of
which the definition counts on purpose.

### Where the wall clock went (§6g)

Nobody had measured this decomposition, and it determines what is worth
optimising later.

| | seconds | share |
|---|---|---|
| environment (SPICE + parse + validate) | **1585.83** | **99.7 %** |
| policy forward + PPO update | 3.52 | 0.2 % |
|   of which the PPO update alone | 2.67 | 0.2 % |
| logging, cross-check, bookkeeping | 0.87 | 0.1 % |
| **total** | **1590.22** | 100 % |

**The answer is unambiguous and it is not close: 99.7 % of a training run is
the simulator.** Every millisecond of Python, every gradient step, all 1.5 MB
of JSONL logging together account for 0.3 %. Two consequences:

1. **Optimising the RL side is worth nothing.** A PPO implementation ten times
   faster would save 3 seconds in 26 minutes.
2. **The library parse is the whole game.** At 2.07 s per evaluation against
   the extended trim's ~0.33 s on the nfet-only trim for the same netlist
   (§7's table, `t_id` vs `t_re` columns), roughly **6.3× of the inner-loop
   cost is the R/C model cards** — `PASSIVES.md` §3.2 measured 7.3× on its own
   probe and identified the cause (`parameters/typical.spice`, 3023 lines, and
   `invariant.spice`, 7340). **`PASSIVES.md` §6 item 6 is therefore the single
   highest-value open item for RL throughput**, and this is the first
   measurement that says so quantitatively rather than by arithmetic.

Both numbers are reported as §6a asks: **0.33 s** on the nfet-only trim,
**2.07 s** on the extended trim that drawn passives require. The R/C corner-file
trim has **not** landed, so the extended library is what a real loop must use.

### Parallel throughput, and the number that was nearly published

24 identical tasks, real passives, extended library. It took **four runs** to
get a number worth quoting, and the sequence is the finding.

**Run 1 — configurations in ascending order.** Reported **4.39× at 11
workers**, *better* than G48's 3.18×, with the explanatory sentence already
written: "the extended library's longer compute phase amortises process launch
better". The clue that it cannot be real is in its own table: **2 workers
reported 2.55×**, and a super-linear speedup from two processes is not physics.
The 1-worker pass ran first, on a cold OS file cache, and paid to read the PDK
include tree from disk.

**Run 2 — order reversed.** The serial baseline dropped **2.7×**, to 2224 ms,
and the answer became 2.64× at 8 workers with 11 slower than 8.

**Runs 3 and 4 — with randomisation and a control**, after the function was
made order-safe. Run 3 randomised the order and re-ran the first configuration
last as a control. **The control still came back at 1.60×**, on a completely
idle machine: the 8-worker configuration measured 2497 ms/task running first
and 1558 ms/task running last.

**That is the real lesson, and it is stronger than "randomise your
benchmarks".** Randomisation is **necessary but not sufficient**. The penalty
is the OS file cache warming on the PDK include tree, so **the first
configuration always pays, whichever one it is** — shuffling only stops the
penalty from always landing on the same configuration and looking like a
property of it. The fix is a **discarded warm-up pass**; the control is what
detects whether you needed one.

`parallel_throughput` now does all three by default, and run 4 is clean:

```
configuration order: [8, 2, 11, 4, 1]   (randomised)
warm-up: 8 workers, 1472.3 ms/task, DISCARDED
```

| workers | 1 | 2 | 4 | **8** | 11 |
|---|---|---|---|---|---|
| ms/task | 3999.1 | 2007.5 | 1627.8 | **1341.0** | 1547.7 |
| speedup | 1.00× | 1.99× | 2.46× | **2.98×** | 2.58× |

**Control: 8 workers re-run last → 1577.9 ms/task against 1341.0 first pass,
ratio 0.85× — clean.**

**2.98× at 8 workers, and 11 workers is SLOWER than 8.** Against G48's 3.18× at
11 on the nfet-only library, the extended library scales slightly worse *and*
its curve turns **down** past 8 rather than flattening — the same mechanism as
G70: concurrent processes thrash the R/C include files, and past 8 the
contention costs more than the parallelism buys. Both the run-2 and run-4
measurements agree on that shape (2.64× and 2.98× at 8, turn-down at 11), which
is what makes it believable where the run-1 number was not.

`n_valid` is 17/24 at every worker count in every run, which is the consistency
check that makes the timing comparison meaningful at all: the same tasks
produce the same verdicts regardless of how they were scheduled.

**The transferable habit, in the owner's words:** *keep looking for the
impossible number rather than the disappointing one.* 2.55× at two workers was
the tell precisely because it was impossible.

---

## 9. The run (§6g) and the wiring pass (§6h)

### 9.1 The reward curve — evidence, not a result

**No conclusion about learning is drawn from 500 steps.** This is stated in the
run's own output as well as here.

| episodes | mean return | min | max |
|---|---|---|---|
| 0–34 | −2.981 | −15.713 | +4.951 |
| 35–69 | −6.158 | −22.213 | +4.951 |
| 70–104 | −4.537 | −18.959 | +4.807 |
| 105–139 | −3.086 | −12.912 | +4.385 |
| 140–141 | −0.499 | −4.705 | +3.707 |

The curve is **non-monotone**: it gets worse before it gets better and the last
bucket holds two episodes. The right reading is that the plumbing carries a
gradient — rewards span −22 to +5, episodes terminate on success and on
invalidity, the policy update runs and does not diverge — and that **the policy
has learned nothing**, which at 142 episodes on a 9-dimensional continuous
problem is exactly what should happen. Nothing was adjusted to make this look
better.

The `+4.951` maxima are worth naming: that is **design 432's own v0 score**,
reached by a randomly initialised policy from a random start. It means the
feasible region is not vanishingly small under v0 at TT with one fixed target —
which is a statement about the *problem*, not about the policy.

### 9.2 Per-spec shortfall distribution (§6h)

> A spec whose shortfall is identically zero for every step may be correctly
> free, or may be unwired. Distinguish the two.

The distinguishing evidence is the **margin**, not the shortfall: a spec that
is *wired* produces a finite margin on every valid step even when its shortfall
is zero, because the margin is computed and merely happens to be positive. An
*unwired* spec has no margin at all. So `shortfall == 0` everywhere **plus a
margin that varies** means correctly free; a margin that is absent or constant
means look again. `_shortfall_stats` reports both and says which case applies.

**Reward v0 (S3 alone), 562 valid evaluations:**

| spec | violated | share | max shortfall | mean | verdict |
|---|---|---|---|---|---|
| `S3_peaking` | 282 / 562 | 50.2 % | 7.651 | 1.050 | binds |
| `S3_f_peak` | 403 / 562 | 71.7 % | 13.932 | 2.246 | binds |
| `S3_nyq_boost` | 58 / 562 | 10.3 % | 2.621 | 0.070 | binds |

`S3_f_peak` is the dominant constraint, violated on 72 % of valid evaluations
with a mean shortfall of 2.25 — i.e. typically more than a full octave off
target. That is consistent with everything this project has measured about S3
being the binding spec, now seen from inside the search rather than from a
random sample.

### 9.3 The v1 wiring pass, re-run on the 7-dimension contract

**Superseded by §9.4.** The original v1 pass ran on the nine-dimension action
space with the two-valued validity gate, and its finding — that `saturation`
and `tail_saturation` were *wired but structurally unable to be violated* — is
what Call 1 was decided on. It is kept below because it is the evidence, and
because the recommendation it carried was **rejected**, which is worth being
able to check.

### 9.3a The original pass, and the finding it produced

> Run a second short pass with all specs plumbed in, including the ones that
> never bind, purely to confirm the wiring.

200 steps, 61 episodes, **319 evaluations, 329 SPICE calls.** Invalid rate
**29.47 %**, and this is the one place §6d's rising-rate signal fired: **25.16 %
in the first half, 33.75 % in the second.** With 61 episodes that is weak
evidence and it is not offered as more; the mechanism split is the same as
v0's, `peak_is_sweep_edge` 75, `pair_triode` 10, `tail_triode` 9. Cross-check
5/5 exact.

**This run's wall-clock numbers are DISCARDED and are not quoted anywhere.**
It overlapped a pytest run that calls ngspice, and its per-evaluation time came
out at 5.4 s against the clean run's 2.07 s — see G70. Its invalid rate,
shortfall distribution and feasibility are load-independent and are quoted.

| spec | violated | share | max shortfall | mean | verdict |
|---|---|---|---|---|---|
| `S3_f_peak` | 160 / 225 | 71.1 % | 13.932 | 2.062 | binds |
| `S3_peaking` | 121 / 225 | 53.8 % | 5.933 | 0.937 | binds |
| `S3_nyq_boost` | 17 / 225 | 7.6 % | 2.621 | 0.048 | binds |
| `S5_noise` | **0 / 225** | 0 % | 0.000 | 0.000 | free |
| `S6_power` | **0 / 225** | 0 % | 0.000 | 0.000 | free |
| `saturation` | **0 / 225** | 0 % | 0.000 | 0.000 | free |
| `tail_saturation` | **0 / 225** | 0 % | 0.000 | 0.000 | free |

All four added specs are identically zero, and §6h asks the right question
about that: *correctly free, or unwired?* The margins answer it — every one of
the four produces a **finite, varying, never-negative margin** on all 225 valid
evaluations:

| spec | margin range over the run |
|---|---|
| `S5_noise` | +0.93 mV … +1.37 mV of headroom under S5's 1.5 mV |
| `S6_power` | +1.2 mW … +14.1 mW under S6's 15 mW |
| `saturation` | +0.042 V … +1.356 V of `vds − vdsat` |
| `tail_saturation` | +0.013 V … +0.595 V of `vds_tail − vdsat_tail` |

So all four are **wired**, and S5 and S6 are **correctly free** — which is what
every previous session measured (90.7 % of the box meets both).

**But `saturation` and `tail_saturation` are a third category that §6h's
question does not have a name for: wired, and structurally unable to be
violated.** A design whose pair or tail is in triode is rejected by the
**validity gate** (§5) before the reward ever sees it, so on any *valid*
evaluation both margins are positive by construction. Their shortfall can never
be non-zero. They contribute only to the feasible branch's
`min(margin / tol)` — never to the infeasible branch's sum.

**This partly undercuts the motivation for adding `tail_saturation` in the
first place.** The reward retraction's argument was that a `min` reward gives
no gradient on a constraint that misses by tens of millivolts. In this
architecture the tail's "you are violating this" signal is not delivered by a
shortfall at all — it is delivered by the **invalid floor**, which is a
*stronger* signal (−8.0 against a shortfall term worth at most −1.0) but an
*ungraded* one: 1 mV into triode and 500 mV into triode score identically.

Two ways a human might resolve it, and it is a human's call (rule 6):

- **(a) Accept it.** Saturation is a validity condition, not a spec: outside it
  the small-signal numbers describe a circuit that is not amplifying, so a
  graded score computed from them would be grading fiction. G24 is the
  precedent — the link layer used to `min()` an invalid operating point into a
  plausible number, and an RL policy hunting eye height would have lived there.
  The ungraded floor is the price of not doing that. **This is the
  recommendation**, and the observation to carry is that the *margin* term in
  the feasible branch is where the tail's gradient actually lives.
- **(b) Grade it from the DC operating point alone** — `vds − vdsat` is a `.op`
  quantity and is meaningful whether or not the small-signal result is —
  scoring a triode design on its DC margin while still refusing to read its AC
  numbers. That is more code and a new failure surface, and nothing measured so
  far says it is needed.

Either way, **the two rows are not evidence of a wiring bug**, and
distinguishing that from one took the margin column. A run that reported only
shortfalls would have shown four zeros and no way to tell.

**Outcome: option (b) was chosen, in the form of Call 1.** The reasoning that
settled it is the one option (a) rested on and did not follow through: grading
a triode design's *small-signal* numbers would be grading fiction, but its *DC*
numbers are not fiction. `vds` and `vdsat` are `.op` quantities and are true
whether or not the device is saturated. So the AC spec set is dropped —
`meas` is `None`, by construction — and the DC headroom is graded. §6.1a.

### 9.4 The re-run, on the 7-dimension contract with the graded band

200 steps, 44 episodes, **276 evaluations, 286 SPICE calls.** Both Calls are in
force: seven action dimensions with the tail derived, and the four-band reward.

**The invalid rate fell from 29.5 % to 10.5 %, and most of that is real rather
than reclassification:**

| | old (9 dims, 2 bands) | new (7 dims, 4 bands) |
|---|---|---|
| invalid | **29.47 %** | **10.51 %** |
| headroom-only (graded) | — (folded into invalid) | 6.52 % |
| `peak_is_sweep_edge` | 75 | 28 |
| `pair_triode` | 10 | 0 — now graded |
| `tail_triode` | 9 | 0 — now graded |
| `ngspice` (transient) | 0 | 1 |

Reclassification accounts for the 19 triode evaluations. The rest — 75 → 28
sweep-edge rejections — is the **derived tail**: a tail sized from its own
current cannot be starved into a bias point that pushes the peak out of the
sweep, which is the failure the two removed dimensions were free to create.
That is a second, unpredicted argument for Call 2, and it was not the argument
Call 2 was made on.

**The graded band is exercised and it orders strictly.** 18 headroom-only
evaluations, spanning **−1.0 mV to −188.1 mV** of triode depth, producing **18
distinct rewards** from −8.0104 to −8.6529. No ties at any depth — which is
what the bounded map buys over a clip. Split 10 on the input pair, 8 on the
tail.

**Per-spec shortfalls, and the reporting bug the re-run exposed.**
`saturation` and `tail_saturation` still show **0 violations among valid rows**
— and the first version of this report called that "correctly free", which is
now *wrong*. They are violated 10 times each; the violations are simply routed
to the graded band, because violating either is what *makes* a design
HEADROOM_ONLY. `_shortfall_stats` now reports `n_headroom_violated` beside
`n_violated` and says so:

> BINDS VIA THE GRADED BAND: 0 violations among valid rows, but 10 in the
> headroom band. Violating this spec makes a design HEADROOM_ONLY, so it can
> never appear as an infeasible shortfall — by construction, not by luck.

S5 and S6 remain genuinely free (margins vary, never negative), which is what
every previous session measured.

| spec | violated (valid rows) | in the graded band | verdict |
|---|---|---|---|
| `S3_f_peak` | 169 / 229 (73.8 %) | — | binds |
| `S3_peaking` | 124 / 229 (54.1 %) | — | binds |
| `S3_nyq_boost` | 53 / 229 (23.1 %) | — | binds |
| `S5_noise` | 0 | 0 | correctly free |
| `S6_power` | 0 | 0 | correctly free |
| `saturation` | 0 | **10** | binds via the graded band |
| `tail_saturation` | 0 | **10** | binds via the graded band |

**Still no conclusion about learning.** Mean episode return over four buckets:
−10.04, −3.28, −5.81, −3.22. Non-monotone, 44 episodes.

**The cost numbers from this run are quoted with a caveat.** It measured
3.94 s per simulation against the clean 500-step run's 2.07 s. Light Python
activity overlapped it, and G70 says any wall clock gathered that way is
unreliable — but there is also a real candidate: the derived tail is sized from
`i_bias`, so a high-current design now gets a *large* tail (445 µm at 8 mA)
where the nine-dimension space could pair a high current with a narrow one.
Larger devices simulate more slowly. **The two explanations are not separated
here**, so the clean 500-step figure remains the one quoted in §8, and this
one is not.

---

## 10. The logged data (§6j)

`nebula/experiments/rl_smoke_run_v0.jsonl` — **782 rows, 1.5 MB, tracked, not
gitignored** (G49).

One JSON object per line, append-only, flushed per row. Three properties that
matter more than compactness: a **truncated run is still readable** (a single
JSON array would not be); rows are **self-describing**, so adding a field later
cannot shift columns in a file written before the change; and it **streams**, so
a run in progress can be inspected without stopping it.

Row 0 is a **header row, not a separate file** — seed, box with per-edge
provenance, tolerances with their bases, horizon, load, library, PPO config,
platform — so a log can never be read without the conditions that produced it
(rule 8). Every row carries `schema_version`, so a later reader can tell rows
written before a field existed from rows where the field was genuinely absent.

Every step row carries the full §6j tuple: **action, sizing (both normalised
`u` and physical `params`), geometry, raw result, validated result, reward** —
plus the margins, the shortfalls, the invalidity reason where there is one, the
SPICE call count and the seconds.

**`design_id` is emitted here rather than reconstructed later**, because task
8's grouped train/test split needs to know which rows are the same design and
re-deriving that from floats after the fact means choosing a rounding tolerance
nobody measured. It is keyed on the realised design — the drawn passive
geometry is part of the key — so two continuous `rs` values that quantise onto
the same resistor group together. See §7 for why that grouping turns out to be
much finer than one might hope.

Non-finite values are written as `null` with the field name preserved.
`json.dumps` writes bare `NaN`/`Infinity`, which is not valid JSON and which
many readers silently turn back into a float — the same class of trap as G54,
where a NaN that survives a round trip reads as a number.

---

## 11. What this does not establish

- **Nothing about learning.** 500 steps, one seed, one target, one corner.
- **Nothing about corners.** TT only. Every number here is a nominal-only
  number, and S9 requires all specs at every corner.
- **Nothing about S4, S7 or S8.** See §0.
- **The 4d shift is measured but its consequences are not chased.** §7 shows
  drawn passives move `f_peak` by more than the load-robustness slack; it does
  not re-run the load screen, and until that is done every corner-and-load
  result in this project is an ideal-passive result.
- **`I_ref` is still an ideal current source**, declared in `TAIL_DEVICE.md` §0
  and unchanged here.
- **Mismatch is off** (`mc_mm_switch = 0`) everywhere, as in every previous
  session.

---

## 12. New gotchas

Full text in `HANDOFF.md` §9.

| | |
|---|---|
| **G63** | `alter` fails silently on an element the netlist no longer *contains*, and returns the previous geometry's numbers — 67 settings, one point, exit 0 |
| **G64** | `has_interior_peak` is a conjunction whose two terms reject different kinds of thing; using it as a validity gate erased the reward gradient over half the box |
| **G65** | 78 % of everything an RL policy finds is G44 — 159 of 203 invalid evaluations were a fictitious peak at the sweep edge |
| **G66** | drawn passives move `f_peak` by 0.133 octaves, *more* than the 0.12 octaves of load-robustness slack; every published corner/load number held them ideal |
| **G67** | `to_geometry` is electrically stable and geometrically chaotic — 15× area spread across a 0.16 % resistance spread |
| **G68** | two ways to build a gate that fails for the wrong reason: a one-sided perturbation probe, and validity checks ordered symptom-before-cause |
| **G69** | `shutil.which` cannot find this project's ngspice, and a skipped test reports as a pass |
| **G70** | one concurrent ngspice makes each run **4.8× slower** against the extended library — measuring anything on a machine that is also simulating gives a wrong number |
| **G71** | a benchmark whose passes run in a fixed order measures the order too: the 1-worker pass paid a cold file cache and reported a **super-linear 2.55× at two workers**, which would have been published as "the extended library scales better than G48" |
| **G72** | a validity gate asks *can I trust this measurement?*, a reward asks *is this circuit good?* — conflating them destroys the gradient where a fresh policy lives. Trustworthiness is per **analysis**: three verdicts, four reward bands |
| **G73** | a weak-but-live action dimension is worse than a dead one, and the test is **redundancy**, not effect size: `vcm_in` is a 6× stronger lever on the tail margin than either tail axis, so both were removed. 9 → 7 dimensions |

G71 was **amended** after this document was first written: randomising a
benchmark's pass order is necessary but **not sufficient**, because the first
configuration always pays the cold file cache. See §8.
