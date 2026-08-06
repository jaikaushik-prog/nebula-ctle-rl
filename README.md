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
**Status as of 2026-08-06:** 698 tests green. Nebula gate G0 passed; G1 in
progress.

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
| **Any agent or developer touching code** | [`HANDOFF.md`](HANDOFF.md) in full — it is the source of truth, including 54 numbered gotchas |

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

**The one-line summary:** PVT corners cost 39 %, the load range costs 99.4 %,
the ideal-tail assumption cost 8.8 %. The load dominates, and it dominates
because the per-load robust sets are large and almost **disjoint** — 159 of the
160 designs robust at one load edge are not robust at the other.

### Method: predictions are pre-registered

Predictions are written down and committed **before** the experiment runs, and
the outcome is recorded afterwards whichever way it went. See
[`nebula/PREDICTIONS.md`](nebula/PREDICTIONS.md). Three entries so far; the
misses are recorded as misses.

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
# The full test suite — 698 tests, ~2 min. Run from the repo root.
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
