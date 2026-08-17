# flow.md — how this project actually flows, end to end

**Written 2026-08-17.** A map, not a contract. Where this file disagrees with
`HANDOFF.md` or `CLAUDEwa.md`, **those win** — they are the source of truth and
this is a reading aid built from them.

Companion file: [`decisions.md`](decisions.md) — every decision and why.

---

## 0. The one-paragraph version

There are **two projects** in this repository. The **SerDes framework**
(`python_models/`) is pre-existing, test-validated behavioural modelling of a
112G PAM-4 receiver. **Nebula** (`nebula/`) is the live competition entry: an
RL loop that sizes a CTLE for a 5 Gbps PCIe Gen2 link on SKY130, judged
15 Sept 2026. Nebula *borrows* the SerDes framework's eye engine to turn a
transistor-level AC response into a bit-error-rate eye. That borrowing — the
**device→link bridge** — is the part that does not exist yet, and it is the
deliverable.

---

## 1. The intended flow (what the competition asks for)

```
   target spec vector                                                 sized schematic
   (peaking, f_peak, HD3,          ┌──────────────────┐               (W/L/nf, Rs, Cs,
    noise, power, area,  ────────► │  RL policy (PPO) │ ────────►      RL, I_bias, VCM)
    eye height, eye width)         └────────┬─────────┘                     +
                                            │ proposes a sizing        its measured specs
                                            ▼
                                   ┌──────────────────┐
                                   │  device layer    │  ngspice + SKY130, per PVT corner
                                   │  .op .ac .noise  │
                                   └────────┬─────────┘
                                            │ DeviceResult
                                            ▼
                                   ┌──────────────────┐
                                   │  link layer      │  pole-zero fit → CTLE model
                                   │  channel+CTLE+DFE│  → statistical eye
                                   └────────┬─────────┘
                                            │ LinkResult (eye height V, eye width UI)
                                            ▼
                                   ┌──────────────────┐
                                   │  reward          │  one scalar
                                   └────────┬─────────┘
                                            └──► back to the policy
```

**Status of each arrow:**

| Arrow | State |
|---|---|
| policy → sizing | **real** (`nebula/rl/contract.py`, `nebula/rl/env.py`, `nebula/rl/ppo.py`) |
| sizing → ngspice → DeviceResult | **real and heavily measured** (`nebula/device/`) |
| DeviceResult → LinkResult | **REAL since 2026-08-17** (`nebula/link/fit.py` + `nebula/link/bridge.py`) — gate G2, passed |
| DeviceResult → reward | **real**, and S8 is now scorable via `reward_v1.V2_SPECS`. `V1_SPECS` is deliberately unchanged so every published reward number still reproduces |

**Gate G2 is passed** (`nebula/G2_RESULTS.md`): one parameter vector produces a
drawn SKY130 schematic meeting **all of S3–S8 at TT** — eye 758 mV × 0.875 UI.
The competition's wording *"outputs the final schematic and resulting specs"* is
now satisfied at TT; S9 (corners) is gate G4 and is not claimed.

**What the closed loop revealed on its first run is the interesting part:**
**compression binds, not the eye.** 61 % of the approved parameter box cannot be
evaluated at the PCIe input level, because the small-signal model that produced
every pole stops applying. S8 turns out to be met by 76 % of the designs that
are valid — confirming, by an independent path, a prediction `CHANNEL_MODEL.md`
§5 made from a pulse response with no transistors in it.

---

## 2. The layer stack, file by file

### Layer 0 — the contracts (`nebula/common/`)

Frozen first, before any implementation, so three people could build in
parallel against them.

| File | Owns |
|---|---|
| `types.py` | `Corner`, `TargetSpec`, `DeviceResult`, `LinkResult`, the S1–S9 spec constants, the 45-corner grid. **`ok=False` is a value, never an exception**; numeric fields are `None` on failure, never NaN |
| `params.py` | Action-space *names*. `BOUNDS` is **deliberately empty and raises** — filling it is a human decision (rule 6) |
| `design_equations.py` | The §6 analytic pole/zero/gain equations *including the body-effect term*, plus `cross_check_extraction()` which compares them against parsed SPICE |

### Layer 1 — device (`nebula/device/`) — **real, measured, the strongest part**

```
Sizing (7 numbers)
   │
   ├─ to_geometry()        passives.py    Rs/Cs/RL  →  drawn SKY130 devices
   │                                      (res_high_po, res_xhigh_po, cap_mim_m3_1)
   ├─ tail.py                             i_bias → a real current-mirror device,
   │                                      ONE PER SIDE (a shared tail would short
   │                                      out the Rs/Cs degeneration)
   ▼
build_point() ──► netlist text
   │
   ├─ netlist_gates.py   REFUSES to emit `w` on a fixed-width resistor family (G57)
   │                     or `mult`/`mf` ≠ 1 (G56). SKY130 accepts both and IGNORES
   │                     them, then exits 0.
   ▼
run_point()   sky130_runner.py
   │   one subprocess, one netlist, FOUR analyses: .op .ac .noise .dc
   │   library selected by lib_for_device(device, real_passives, section)
   ▼
raw stdout
   │
   ├─ crosscheck.py::scan_for_silent_failures()   greps for warning-shaped
   │                                              failures BEFORE anything is parsed
   ├─ parse → Sky130Point
   ├─ crosscheck.py::derived_ac()   peaking_db AND nyquist_boost_db, kept separate
   └─ design_equations.cross_check_extraction()   SPICE vs the analytic equations
```

**Why it looks paranoid:** every gate above exists because ngspice reported a
real failure as a warning and exited 0. See `decisions.md` §C.

### Layer 2 — link (`nebula/link/`) — **half real, half mock**

| File | State | What it does |
|---|---|---|
| `channel.py` | **real** | The channel as a *derived family*: `IL_dB(f) = A·√f + B·f`, 7 losses × 3 skin/dielectric splits = 21 members, minimum-phase reconstruction, causality/passivity/monotonicity gates |
| `tx.py` | **real** | PCIe Gen2 transmitter as the 2-tap FIR it is; supplies exactly −de_emphasis_dB of tilt at Nyquist |
| `cursors.py` | **real** | Pulse response → UI sampling at the h0-maximising phase → h₋₂…h₄ → residual ISI after an ideal 1-tap DFE → eye |
| `calibration.py` | **real** | THE normalised-amplitude → volts conversion. One place, one function (§5.3a, the highest-risk silent bug in the project) |
| `config.py` | **real** | `LinkConfig` + the PCIe Gen2 anchors (0.8 Vpp swing, −3.5/−6 dB de-emphasis) |
| **`mock.py`** | **FAKE** | The device→link bridge. Trends are physically coherent; **magnitudes are invented.** This is the G2 hole |

**What "real" buys today:** the channel work already answered a design
question — a 1-tap DFE is sufficient across the whole 3–12 dB family, the eye
is open at all 21 members. What is missing is the *wiring* from a measured
ngspice AC sweep into that machinery.

### Layer 3 — RL (`nebula/rl/`) — **real, runs end to end, untuned**

```
contract.py     THE environment contract, written before the implementation.
                7 action dims (deltas, clipped to MAX_STEP), 20-dim observation,
                fixed normalisation scales. nf_in fixed at 4; tail derived, not searched.
   │
env.py          The episode: horizon 8, early-terminate on success,
                terminate on an invalidity (never default, never retry into a
                different answer). gym-SHAPED, no gym dependency.
   │
evaluator.py    THE POISON-SAFE EVALUATOR — the highest-risk file.
                One sizing point → a validated measurement vector or a NAMED
                invalidity. Three verdicts:
                   VALID          .op and .ac both trustworthy
                   HEADROOM_ONLY  .op fine, device in triode → AC set DROPPED,
                                  graded on (vds − vdsat) so there is a way out
                   INVALID        nothing trustworthy → floor, no gradient
                Owns SpiceBudget, which counts EVERY invocation incl. discards.
   │
reward_v1.py    while ANY constraint violated:  r = −Σ clip(shortfall_i, 0, 1)
                once ALL satisfied:             r = B + min_i(margin_i / tol_i)
                Seven tolerances, each in units where 1.0 = "meaningfully off"
                (f_peak in octaves, peaking in dB, saturation in 100 mV).
   │
ppo.py          ~150 lines of torch. Every constant is a PPO-paper or SB3
                default, written down. NOTHING TUNED. Worth 0.2 % of wall clock.
   │
runlog.py       JSONL. Row 0 is a HEADER row, so a log cannot be read without
                its conditions.
```

---

## 3. One evaluation, step by step

This is the path a single design takes. It is the thing G2 has to close.

```
 1. policy emits a 7-vector of DELTAS in [0,1]-normalised space
 2. contract.sizing_from_u()   → absolute Sizing (log axes for R, C, I; linear for W, VCM)
 3. passives.to_geometry()     → drawn resistor/capacitor geometries
 4. tail.py                    → tail device sized from i_bias at a target vdsat
 5. sky130_runner.build_point()→ netlist text
 6. netlist_gates              → refuse inert parameter writes
 7. ngspice_con.exe            → .op .ac .noise .dc, run FROM nebula/device/spice/
 8. crosscheck.scan_for_silent_failures()  → abort on warning-shaped failure
 9. parse → Sky130Point        → gm, gmbs, vds, vdsat, AC magnitude sweep, inoise_total, power
10. evaluator.validate()       → VALID / HEADROOM_ONLY / INVALID  (+ named reason)
11. crosscheck.derived_ac()    → peaking_db, f_peak_hz, nyquist_boost_db
        ├──────────── TODAY: stops here. reward_v1 scores S3/S5/S6 + headroom.
        │
        └─ G2 ADDS: fit (g_dc, f_zero, f_pole1, f_pole2) to the AC sweep
                    reject fit residual > 0.5 dB
                    instantiate the CTLE model
                    channel (link/channel.py) + CTLE + 1-tap DFE
                    → statistical eye → eye height in VOLTS, eye width in UI
                    → S8 enters the reward
12. reward_v1.reward()         → one scalar
13. runlog                     → JSONL row: action, sizing, geometry, raw, validated, reward
```

**Corner handling:** steps 5–11 repeat per PVT corner and per load, and the
score is the **worst** over them — never the nominal. The evaluation
short-circuits the moment a point returns the invalid floor, and that
short-circuit is exact, not an approximation.

---

## 4. The experiment flow (how every published number was made)

Every measurement in `nebula/` follows the same shape, and it is deliberate:

```
1. Write the question down and PRE-REGISTER the prediction
       nebula/PREDICTIONS.md   — committed BEFORE the run, with acceptance
                                 bands and explicit falsification conditions
2. Build the experiment as one script in nebula/experiments/
       - it owns its ASSUMPTIONS and prints them in every run's header
       - it has a --report / --analyse mode that re-runs the whole analysis
         from the committed data file with NO simulator
3. Run it. Stream results to JSONL/CSV as they arrive (an interrupted run is
   recovered, not lost — the task-7 pilot was killed one job from the end and
   every row survived)
4. COMMIT THE RAW DATA. Results are tracked, not gitignored (G49), and
   aggregates are not results (S9's 20 205 measurements were lost because only
   counts were written)
5. Write the outcome into PREDICTIONS.md — hit or miss, whichever way it went.
   Do not edit anything above the Outcome heading.
6. Write the full-length write-up as its own nebula/*.md
7. Update HANDOFF.md in the SAME COMMIT
```

The write-ups, in the intended reading order, are listed in
[`nebula/README.md`](nebula/README.md).

---

## 5. The gate timeline

| Gate | Due | Criterion | Honest status (2026-08-17) |
|---|---|---|---|
| G0 | 2 Aug | toolchain runs all four analyses | **passed** |
| G1 | 3 Aug | hand-designed reference meets S3–S7 at TT | **substantially passed**; MIM-cap / poly-resistor area models still open |
| **G2** | **20 Aug** | one full evaluation: params → ngspice → fit → eye → scalar reward | **NOT STARTED — 3 days out.** The link layer is a mock end to end |
| G3 | 3 Sep | RL beats random **and** grid search, with a plot | harness built and tested; **the sweep has not run**; no tuned policy |
| G4 | 12 Sep | corner-robust design generated and verified | blocked behind G2/G3 |
| G5 | 15 Sep | submitted | — |

Fallbacks are written into `CLAUDEwa.md` §7 and are meant to be taken **the
same day** a gate fails.

---

## 6. The work queue, in order

From `nebula/NEXT_STEPS.md`, with session-19's in-flight work folded in:

| # | Step | Cost | Unblocks | State |
|---|---|---|---|---|
| 1 | Trim the SPICE library | ~half a day | **everything**, at ~6× | **IN FLIGHT, uncommitted** — see §8 |
| 2 | Run the baselines sweep | 12 h → ~2 h after step 1 | G3, the surrogate dataset | not started |
| 3 | **G2: close device→link→reward** | days | G2, G4, the deliverable | **not started — do this** |
| 4 | Re-fit the pre-screen at benchmark conditions | hours | honest screened arms | not started |
| 5 | Tune PPO enough to have a G3 answer | days | G3 | not started |
| 6 | Spec-conditioned policy | days | contribution #2 + the live demo | not started |
| 7 | LLM wrapper (`nebula/llm/`) | ~a day | the stated bonus deliverable | **directory does not exist** |
| 8 | Task 8 worst-corner surrogate | days | contribution #1, optional | first cut done, blocked on data |
| 9 | Report, slides, figures | days | G5 | not started |

**Cut order if time runs short: 8, then 6, then 5's tuning depth. Never cut 3.**

---

## 7. How to run things

```bash
conda activate nebula                                   # ngspice 41 lives here

# The safety net. Run from REPO ROOT. ~1.5 min on a quiet machine.
python -m pytest tests nebula/tests -q -m "not slow"

# Re-run any analysis with NO simulator, from committed data
python -m nebula.experiments.tail_device --report
python -m nebula.experiments.baselines --analyse nebula/experiments/baselines_pilot.jsonl

# Measurements that need ngspice
python -m nebula.experiments.cl_range
python -m nebula.experiments.s9_yield --n 2000 --workers 8
python -m nebula.experiments.baselines --sweep          # 25 500 sims, ~12 h

# Hand-sizing sandbox (interactive, not a deliverable)
cd nebula/device/spice && ngspice_con ctle.cir
```

Three environment facts that cost real time to discover:

- **`ngspice_con.exe`, never `ngspice.exe`** (G20). The latter is the GUI build
  and prints nothing in batch mode, which looks exactly like a broken install.
- **Run netlists from `nebula/device/spice/`** (G29) so the local `.spiceinit`
  is read at parse time.
- **Instance W/L are plain numbers in microns** (G31), not SI metres.

---

## 8. What is in the working tree right now and NOT committed

Session 19 (2026-08-12) is mid-flight on step 1, the library trim, and it found
that **the standing explanation for the cost was wrong in both halves**:

- `invariant.spice` **is not in the include tree at all** — only
  `parameters/montecarlo.spice` includes it, which no section this project
  reaches. Four sessions of notes said otherwise.
- `typical.spice` is real but minor: 8 909 named parameters of which the
  library references **86**; dropping the other 8 823 is worth about **1.55×**.
- The actual cause: **ngspice expands EVERY `.lib` section in a file, not just
  the one asked for.** Same netlist — one section 0.093 s, the 25-section
  extended library 1.386 s, a **15×** difference. The extended library grew to
  25 sections the day the 5×5 MOS×passive corner cross-product landed.

New/changed, uncommitted: `nebula/device/pdk_trim.py`,
`nebula/experiments/lib_cost.py`, `nebula/device/spice/pdk_trim/` (generated),
plus a `crosscheck.py` fix (the `Error:` pattern was anchored **case-sensitively**
and missed ngspice's own upper-case `ERROR: fatal error`, so the equivalence
probe was reading an aborted run — G26 inside the G26 guard).

**Not yet done for that work:** the `nebula/LIB_COST.md` write-up it references
does not exist, `HANDOFF.md` has no session-19 log entry, and
`lib_cost_results.json` currently records the *parameter-deck* arms
(1.55× extended-trimmed, 6.14× nfet-only) rather than the section-split arm the
docstrings quote. Finish those before committing.

---

## 9. The three failure modes this repo keeps hitting

Every one produced a wrong number that looked right.

1. **Silent success.** ngspice reports many failures as warnings and exits 0
   (G26, G30, G35, G54, G63). Parse the output and assert. An exit code is
   never a success signal. A verification block here once ran for a week
   reporting success while computing nothing at all.
2. **Units.** Microns vs metres (G31), a scale applied twice (G35),
   `inoise_total` is already RMS volts and must **not** be square-rooted. Each
   is a factor of 10³–10⁶ that still simulates perfectly happily.
3. **Two definitions of one thing** (G32). A netlist and the runner that
   produced the published numbers described "the same" operating point with
   model cards differing by one parameter — and that parameter was the
   body-effect coefficient, i.e. exactly the term a correction elsewhere was
   about.

Four more earned since:

4. **A gate whose condition is unreachable is indistinguishable from a deleted
   gate** (G73). Count how often each guard fires.
5. **A benchmark run in a fixed order measures the order** (G71). The first
   configuration always pays the cold file cache.
6. **A speed-up measured on isolated evaluations does not transfer to a
   workload whose workers also compute** (G75). 2.98× became 1.80×.
7. **An aggregate rate can hide a systematic bias completely** (G76). The
   pre-screen kept its rejection rate and its yield lift while its error
   tripled.
