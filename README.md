# SerDes DSP Framework · Nebula CTLE Sizing

Two related projects share this repository. They share a test suite and a
handoff document; they are otherwise independent by design.

| | **SerDes framework** | **Nebula** |
|---|---|---|
| What | Behavioural link-design methodology for a DSP receiver | RL-driven transistor-level CTLE sizing, zero human in the loop |
| Target | 112G PAM-4 RX, 28 nm reference parameters | 5 Gbps NRZ PCIe Gen2 CTLE, SkyWater SKY130 |
| Code | [`python_models/`](python_models/) | [`nebula/`](nebula/) |
| Contract | [`CLAUDE.md`](CLAUDE.md) | [`CLAUDEwa.md`](CLAUDEwa.md) |
| Deadline | open-ended | **15 Sept 2026** (Astera Labs × BITS Goa) |

**Owner:** Jai Kaushik, BITS Pilani EEE.
**Status as of 2026-09-04:** Nebula's frozen shielded-RL product path accepts
two user targets, automatically verifies seven channel losses across all 45
PVT corners, and outputs a code map, exact SPICE deck, schematic and RL
adaptation dashboard. It also emits a 512-setting hardware map which separates
the measured PMOS attenuator from the not-yet-netlisted Rs/Cs selector
switches. The 9 dB / 1.9 GHz demo passes 315/315 conditions. A
separate diagnostic closes the high-frequency 12 dB edge and reaches 314/315
at the low-frequency edge; those candidates are not yet in the shipping bank.
Nebula can also ingest a real Touchstone 1.x `.s4p` without optional RF
packages and produce a hash-grounded channel profile; that profile is clearly
separated from the frozen bank's RL compliance evidence.
See
[`nebula/PROJECT_SOLUTION_OVERVIEW.md`](nebula/PROJECT_SOLUTION_OVERVIEW.md).

> **This repository is private and must stay private.** It sits alongside ten
> copyrighted reference PDFs and the competition organisers' material, all of
> which are `.gitignore`d and have **never** been committed to this history.
> See [gotcha G1](HANDOFF.md#9-gotchas--footguns-each-one-cost-real-debugging-time).

---

## Start here

Depending on why you are reading:

| You are… | Read this |
|---|---|
| **A mentor or teammate wanting the state of play** | [`docs/PROGRESS.md`](docs/PROGRESS.md) — every session, what question it asked, what it measured |
| **Picking up the Nebula work** | [`nebula/README.md`](nebula/README.md) — index + reading order, then [`CLAUDEwa.md`](CLAUDEwa.md) |
| **Picking up the SerDes work** | [`docs/ROADMAP.md`](docs/ROADMAP.md), then `python_models/` |
| **Any agent or developer touching code** | [`HANDOFF.md`](HANDOFF.md) in full — it is the source of truth, including 63 numbered gotchas |

`HANDOFF.md` is long (3,300+ lines) on purpose: it is the living state file,
not an introduction. `docs/PROGRESS.md` is the introduction.

---

## Nebula — the competition track

**The problem statement (Astera Labs):** demonstrate a fully automated
framework that sizes an equalizer from a target specification using
reinforcement learning, integrating with a SPICE simulator, reaching
near-optimal solutions in far less time than sweeping the full MOS/R/C/L
parameter space — with zero human intervention.

**Topology (fixed by the spec):** one-stage differential CTLE with source
degeneration (`Rs`, `Cs`) and a resistive load, plus a 1-tap DFE in the link
layer.

### What has actually been measured

Every number below came from a simulation that was run; none is estimated.
Simulator is ngspice 41 against the real SKY130 PDK.

| Question | Answer | Where |
|---|---|---|
| Does the toolchain work at all? | **Yes** — `.op`/`.ac`/`.noise`/`.dc` all run. `.disto` returns exactly 0 for BSIM4, so HD3 must come from transient+FFT | [`nebula/G0_RESULTS.md`](nebula/G0_RESULTS.md) |
| What fraction of the parameter box meets the peaking spec? | **8.73 %** [7.54, 10.09] — the honest random-search baseline RL has to beat | [`nebula/BOUNDS_REDERIVATION.md`](nebula/BOUNDS_REDERIVATION.md) |
| Is the peaking spec a *coupled* constraint? | **No — falsified.** Coupling factor 1.00–1.06× across three box widths. The low yield is one low marginal | [`nebula/BOUNDS_REDERIVATION.md`](nebula/BOUNDS_REDERIVATION.md) §4 |
| What do the PVT corners cost? | **39 %** of the designs that pass at nominal fail at a corner | [`nebula/S9_YIELD.md`](nebula/S9_YIELD.md) |
| Are 45 corners needed? | **No — 3 corners are worth 98.7 % of 45**, and a screen can only err in one direction | [`nebula/S9_YIELD.md`](nebula/S9_YIELD.md) §3 |
| Which corner is worst? | **Fast-hot, not slow-hot** — because the peaking spec is two-sided, so each edge has its own worst corner | gotcha G46 |
| What separates corner-robust designs? | **Not where they sit in the parameter box** (every coordinate a null) **but where they sit in the spec window** | [`nebula/ROBUST_GEOMETRY.md`](nebula/ROBUST_GEOMETRY.md) |
| Where does the load capacitance come from? | Derived from what physically loads the output: **13.6 / 32.6 / 78.0 fF**, entirely below the 150 fF every earlier result assumed | [`nebula/CL_RANGE.md`](nebula/CL_RANGE.md) |
| What does that load range cost? | **99.4 %** — corner-and-load-robust yield is **1 design in 1890**. The load is the binding constraint, not the corners | [`nebula/S9_YIELD.md`](nebula/S9_YIELD.md) §8 |
| The tail was two ideal current sinks. What did that hide? | **8.8 %** of the corner-robust population and **zero** of the headline yield — same surviving design before and after | [`nebula/TAIL_DEVICE.md`](nebula/TAIL_DEVICE.md) |
| Are R and C real devices yet? | **In the device layer, yes.** Three silent traps measured — `mult`/`mf` do nothing, `w` is inert on the fixed-width families, and the **passive corner axis is orthogonal to the MOS one**, so S9's 45 corners are really **225** | [`nebula/PASSIVES.md`](nebula/PASSIVES.md) |
| What channel are we equalising? | A **family derived from the spec**, not a constant: `IL(f) = A·√f + B·f`, 3–12 dB at Nyquist × three skin/dielectric splits, minimum-phase and causality-gated | [`nebula/CHANNEL_MODEL.md`](nebula/CHANNEL_MODEL.md) |
| Is the mandated 1-tap DFE enough? | **Yes across 3–12 dB** — the eye never closes. But only **14.7 %** of what it cannot reach is in `h₂` and **31 %** is beyond 20 UI, so more taps would not help: the CTLE has to do this work | [`nebula/CHANNEL_MODEL.md`](nebula/CHANNEL_MODEL.md) §5 |
| How much of the equalisation does the transmitter do? | **Exactly 3.5 dB** — PCIe Gen2's mandated de-emphasis. So the CTLE's burden is −0.5…+8.5 dB and **the top 3.5 dB of the tunable range is never called for** | [`nebula/CHANNEL_MODEL.md`](nebula/CHANNEL_MODEL.md) §4 |
| Does the stage compress? | **At 5 of 7 loss points**, worst at *low* loss (1.51× at 3 dB). Measured as peak distortion through the real pulse response — the earlier 1.22× was a different, weaker convention | [`nebula/CHANNEL_MODEL.md`](nebula/CHANNEL_MODEL.md) §6 |
| Can physics alone solve the sizing problem? | **No.** An analytic pre-screen predicts the peak frequency to **4.93 %** and rejects **61.7 %** of the box for free at a **0.39 %** false-rejection rate — but the yield among the designs it keeps is **34.9 %**, not the >50 % that would make search unnecessary. A **2.60× multiplier, not a solution** | [`nebula/BASELINES.md`](nebula/BASELINES.md) §5 |
| What does a benchmark of this problem cost? | Fully crossed, **23.5 h**; what fits an overnight run is **30 000 simulations = 11.2 h**. The cut fell on problems and screen arms, never on seeds or the per-run budget | [`nebula/BASELINES.md`](nebula/BASELINES.md) §1 |
| Is the reward's best score a property of the circuit? | **No — of the AC sweep.** `meas ac MAX` reports on a lattice 0.066 octaves wide, so no design can score above **+8.95067** at nominal. Four different designs measured exactly that | [`nebula/BASELINES.md`](nebula/BASELINES.md) §3 |

**The one-line summary:** PVT corners cost 39 %, the load range costs 99.4 %,
the ideal-tail assumption cost 8.8 %. The load dominates, and it dominates
because the per-load robust sets are large and almost **disjoint** — 159 of the
160 designs robust at one load edge are not robust at the other.

**And on the link side:** the mandated topology is adequate for the channel the
spec implies, so the fight is not the DFE. It is compression at *low* channel
loss, where the equaliser's own minimum setting is more boost than the link
needs.

### Method: predictions are pre-registered

Predictions are written down and committed **before** the experiment runs, and
the outcome is recorded afterwards whichever way it went. See
[`nebula/PREDICTIONS.md`](nebula/PREDICTIONS.md). Six entries so far; the
misses are recorded as misses. Entry 6 — the predicted ordering of five search
methods — was committed before the benchmark harness had run a single
simulation, and the commit timestamp is the evidence.

### Gate status

| Gate | Due | Criterion | Status |
|---|---|---|---|
| G0 | 2 Aug | ngspice + PDK run all four analyses | **Passed** |
| G1 | 3 Aug | Hand-designed reference CTLE meets specs at nominal | **In progress** — bias corrected, real tail added; poly-resistor and MIM-cap models still to land |
| G2 | 20 Aug | One full evaluation end-to-end: params → ngspice → fit → eye → reward | Not started (link bridge is still a mock) |
| G3 | 3 Sep | RL beats random **and** grid search at nominal | Not started |
| G4 | 12 Sep | Corner-robust design generated and verified | Not started |
| G5 | 15 Sep | Submitted | — |

---

## SerDes framework — the prior work

~6,500 lines of test-validated behavioural link modelling (`python_models/`
plus its 92 tests), originally targeting 112G PAM-4. Declared throughout as
**pre-existing team infrastructure**, not as new work for the competition.

**Signal chain (`python_models/link_sim.py`):**

```
PRBS → scramble → Gray/PAM4 → TX-FFE → ×OSR(8) → TX pole → TX jitter
 → channel H(f) → +AWGN → CTLE → gain calibration
 → CDR-driven sampler (closed loop, TI mismatch, 6-bit quantization)
 → joint FFE+DFE single-pass LMS → Gray decode → BER + Wilson bound
```

Two engines are built from one `LinkConfig` and cross-validated against each
other: a **time-domain** engine that counts errors, and a **statistical**
engine that computes BER semi-analytically to 1e-15. They agree within ~3×
where both operate.

**Two findings worth the space:**

1. The unconstrained optimum on a dispersive channel is 0 dB of CTLE peaking —
   a long digital FFE equalizes with less noise boost than analog peaking — but
   **that configuration cannot lock.** This motivated a pattern-dependent
   zero-crossing jitter metric, calibrated against time-domain lock outcomes,
   which is now a constraint in the optimizer.
2. **ADC clipping, not equalization, is what limits the 0-dB-CTLE case**
   (17 % of samples beyond full scale). So the CTLE earns its place twice: for
   timing health and for ADC dynamic range. Only the first is engineerable away.

---

## Repository map

```
├── HANDOFF.md              Living state: history, current numbers, 54 gotchas
├── CLAUDE.md               Working rules for the SerDes track
├── CLAUDEwa.md             The Nebula contract: spec table, gates, standing rules
├── docs/
│   ├── PROGRESS.md         ← session-by-session progress board (start here)
│   └── ROADMAP.md          Audit of the inherited code + phased plan
│
├── python_models/          VALIDATED. The SerDes framework core.
├── tests/                  92 tests — the safety net for python_models/
│
├── nebula/                 The competition track. See nebula/README.md
│   ├── common/             Frozen interface contracts, params, design equations
│   ├── device/             ngspice wrappers, SKY130 netlists, corner runner
│   ├── link/               device → eye bridge (mock only so far)
│   ├── rl/                 reward function (no PPO loop yet)
│   ├── experiments/        One script per measurement, with its data committed
│   └── tests/              606 tests
│
└── ffe_learning/           Teaching sandbox for the UCIe group project
```

### Not audited — treat as untrusted

These directories were inherited with the starter code. They have **never been
simulated or run**, and the audit that found seven correctness bugs in the
Python models has not been repeated on them. They are kept in the tree for
reference and are **not** part of any deliverable:

`rtl/` · `verification/` · `veriloga_models/` · `ams/` · `scripts/cadence/` ·
`matlab_models/` · `python_models/optical_dsp.py` ·
`python_models/ml_equalizer.py` · `python_models/visualization.py` · `Makefile`

The Cadence and Spectre flows in particular are **out of scope** for Nebula,
which mandates open-source tooling.

---

## Running things

**Environment:** Windows 11, Python 3.13, numpy/scipy/pytest.
ngspice 41 lives in the conda env `nebula`; SKY130 is installed at
`C:\Users\DELL\sky130A`.

```bash
# The shielded-RL product: only peaking and peak frequency are user targets.
python -m nebula.design --method rl-hybrid --peaking 9 --f-peak 1.9 --out out

# The same product from plain English; offline and deterministic by default.
python -m nebula.llm "I need 9 dB of peaking near 1.9 GHz" --out out

# The full test suite. Run from the repo root.
python -m pytest tests nebula/tests -q -m "not slow"

# Either suite standalone
python -m pytest tests -q
python -m pytest nebula/tests -q

# SerDes link simulation (run from python_models/)
cd python_models
python link_sim.py --channel_cm 3 --snr_db 26 --plot
python link_sim.py --mode statistical --channel_cm 3 --snr_db 26
python make_report_figures.py
```

`-m "not slow"` deselects 2 tests that re-derive golden values from the full
SKY130 library (~30 s each). Run them after a PDK update.

The Nebula tests skip cleanly when ngspice or the PDK is absent, so the suite
is runnable on a machine without either.

---

## Working rules

If you contribute, these are binding — each was written after a specific
failure:

1. **Update `HANDOFF.md` in the same commit as any change.** A change without
   a handoff update is an incomplete change.
2. **Run the test suite before and after.** Report the count both times. Never
   commit with failures.
3. **Never fabricate a number.** If a value is unknown it stays `None` and
   fails loudly. Every number in a deliverable traces to a simulation that was
   actually run.
4. **ngspice's exit code is not a success signal.** It reports many failures as
   warnings and exits 0. Parse the output and assert.
5. **Model cards have exactly one definition.** Netlists and runners reference
   it; neither redeclares it.
6. **Parameter ranges, reward weights and spec tolerances are human
   decisions.** Propose them; do not set them autonomously.

---

*BITS Pilani, EEE Department — Analog/RF/Mixed-Signal VLSI Group*
