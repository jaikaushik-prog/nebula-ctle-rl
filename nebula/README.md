# Nebula — RL-driven CTLE sizing

Competition entry for **Nebula** (Astera Labs × BITS Pilani, Goa), *AI/ML for
Analog Circuit Design* track. Final submission **15 Sept 2026**.

**The task:** given a target specification, automatically size a
continuous-time linear equalizer for a 5 Gbps PCIe Gen2 link — from spec vector
to verified, corner-robust transistor-level netlist, with no human in the loop.
Open-source tooling only: Python, ngspice, SkyWater SKY130.

The contract for this track is [`../CLAUDEwa.md`](../CLAUDEwa.md). **Read it in
full before touching anything here** — it carries the spec table, the gates, and
standing rules that were written after specific failures and are not guessable.

---

## Reading order

If you are new to this track, read in this order. Each document is a
self-contained write-up of one experiment.

| # | Document | What it establishes | Read it before… |
|---|---|---|---|
| 1 | [`G0_RESULTS.md`](G0_RESULTS.md) | The toolchain works; `.disto` is unusable for BSIM4 so HD3 needs transient+FFT; the measured cost of each analysis | writing any ngspice wrapper |
| 2 | [`BOUNDS_REDERIVATION.md`](BOUNDS_REDERIVATION.md) | The parameter box with per-edge provenance, the 8.73 % baseline, the measured output swing — and **§4, which retracts the coupled-constraint argument** | writing any deliverable |
| 3 | [`CL_SENSITIVITY.md`](CL_SENSITIVITY.md) | What the load capacitance does to the yield. A search dimension can be worth less than a constant | touching the action space |
| 4 | [`CL_RANGE.md`](CL_RANGE.md) | Where the load capacitance actually comes from: 13.6 / 32.6 / 78.0 fF, derived rather than chosen | measuring any gate capacitance |
| 5 | [`S9_YIELD.md`](S9_YIELD.md) | Corner-robust yield, which spec fails first at each corner, and the corner-screen cost model | quoting any yield number |
| 6 | [`ROBUST_GEOMETRY.md`](ROBUST_GEOMETRY.md) | Robustness is a property of position in the **spec window**, not in the parameter box | touching the reward shape |
| 7 | [`TAIL_DEVICE.md`](TAIL_DEVICE.md) | The tail as a real transistor. What the ideal-sink assumption was worth, and the one constraint that couples five box coordinates | repeating "tail noise is common-mode" |
| 8 | [`PREDICTIONS.md`](PREDICTIONS.md) | Pre-registered predictions vs. outcomes, including the misses | — |
| 9 | [`NRZ_RETARGET_AUDIT.md`](NRZ_RETARGET_AUDIT.md) | All 24 four-level assumptions in the inherited PAM-4 code, risk-marked | retargeting anything |

Each write-up opens with its **assumptions section**. Read it. Several results
are explicitly bounds rather than answers, and the assumptions section is where
that is stated.

---

## Layout

```
common/
  types.py             Frozen interface contracts + the spec constants + the 45-corner grid.
                       ok=False is a VALUE; numeric fields are None on failure, never NaN.
  params.py            Action-space names. BOUNDS is deliberately EMPTY — it raises
                       until a human fills it. See "why" below.
  design_equations.py  The pole/zero/gain equations, including the body-effect term,
                       plus the cross-check that compares them against SPICE.

device/                Where the circuit meets the simulator.
  sky130_runner.py     One sizing point, four analyses, one call. Owns the two unit
                       conversions (metres→microns, total current→per-side).
  tail.py              The tail current source as a real device: a mirror, one per side.
  cap_probe.py         What a following stage presents to the CTLE output, measured as
                       the AC current the driver must supply.
  crosscheck.py        The accuracy gate, in Python where it can actually raise.
                       Refuses to run on output containing warning-shaped failures.
  ngspice_runner.py    Batch-mode driver: netlist template → subprocess → parsed result.
  mock.py              SYNTHETIC. Fake numbers by construction. Never reaches a deliverable.
  spice/               Netlists, the trimmed SKY130 library, and .spiceinit.

link/                  Device result → eye. calibration.py owns the normalised→volts
                       conversion, which is the highest-risk silent bug in the project.
                       Still a mock end to end.

rl/                    reward.py — the shortfall reward with worst-corner aggregation.
                       No PPO loop yet.

experiments/           One script per measurement. Each owns its assumptions and prints
                       them in every run's header. Data files are committed alongside.

tests/                 606 tests. Those needing a simulator skip cleanly without one.
```

---

## Two things that look like bugs and are not

**`common/params.py::BOUNDS` is empty and raises when read.** This is
deliberate. Choosing parameter ranges is a human decision: too wide and the
simulator will not converge over most of the box, too narrow and the optimum is
outside it — and *neither failure announces itself*. Both just look like "the RL
didn't work". The proposed box lives in the experiment scripts and in
`BOUNDS_REDERIVATION.md`, awaiting approval.

**The mocks produce fake numbers.** `device/mock.py` and `link/mock.py` exist so
that three layers could be built in parallel before the simulator was working.
Their *trends* are physically coherent; their *magnitudes* are invented. No
value from either may reach a report, a slide, or a results table.

---

## Running an experiment

```bash
conda activate nebula          # ngspice 41 lives here

# Tests only — no simulator needed, they skip cleanly
python -m pytest nebula/tests -q

# A measurement. Most support --report to re-run the analysis from the
# committed CSV with no simulator at all.
python -m nebula.experiments.cl_range
python -m nebula.experiments.tail_device --report
python -m nebula.experiments.s9_yield --n 2000 --workers 8
```

Two environment facts that cost real time to discover:

- Use **`ngspice_con.exe`**, not `ngspice.exe`. The latter is the GUI build and
  prints nothing in batch mode, which looks exactly like a broken install.
- Run netlists **from `device/spice/`** so the local `.spiceinit` is read at
  parse time.

---

## The three failure modes this track keeps hitting

Stated here because each one produced a wrong number that looked right. The
full list of 54 numbered gotchas is in [`../HANDOFF.md`](../HANDOFF.md) §9.

1. **Silent success.** ngspice reports many failures as warnings and exits 0. A
   verification block in this repo once ran for a week reporting success while
   computing nothing at all. Parse the output and assert; the exit code is never
   a success signal.

2. **Units.** Microns versus metres. A scale factor applied twice. An integrated
   noise figure that is already RMS volts and must not be square-rooted. Each is
   a factor of 10³–10⁶ that still simulates perfectly happily.

3. **Two definitions of one thing.** A netlist and the runner that produced the
   published numbers once described "the same" operating point with model cards
   differing by a single parameter — and that parameter was the body-effect
   coefficient, i.e. exactly the term a correction elsewhere was about. Anyone
   sanity-checking by opening the netlist would have been quietly misled.
