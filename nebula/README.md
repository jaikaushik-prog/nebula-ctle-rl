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
| 8 | [`PASSIVES.md`](PASSIVES.md) | R and C as real SKY130 devices; `mult`/`mf` do nothing and `w` is inert on the fixed-width families; the passive corner axis is **orthogonal** to the MOS one, so S9's 45 corners are really 225 | instantiating any passive, or quoting a corner count |
| 9 | [`CHANNEL_MODEL.md`](CHANNEL_MODEL.md) | The channel as a **derived family**, not a constant. A 1-tap DFE is sufficient across 3-12 dB — but only 15 % of what it cannot reach is in `h2`. The TX de-emphasis is worth exactly 3.5 dB of the CTLE's job. The compression verdict, re-measured | quoting any compression, eye or ISI number |
| 10 | [`RL_SMOKE.md`](RL_SMOKE.md) | The RL loop, run end to end **badly on purpose**. The environment contract; the six integration bugs it surfaced; **78 % of what a policy finds is a fictitious peak at the sweep edge**; drawn passives move `f_peak` by more than the load-robustness slack; and where the wall clock actually goes (**99.7 % simulator**) | writing any RL code, or quoting any cost |
| 11 | [`PREDICTIONS.md`](PREDICTIONS.md) | Pre-registered predictions vs. outcomes, including the misses | — |
| 12 | [`NRZ_RETARGET_AUDIT.md`](NRZ_RETARGET_AUDIT.md) | All 24 four-level assumptions in the inherited PAM-4 code, risk-marked | retargeting anything |
| 13 | [`G2_RESULTS.md`](G2_RESULTS.md) | **Gate G2, passed.** The device→link bridge: one parameter vector → a drawn SKY130 schematic meeting **all of S3–S8 at TT** (eye 758 mV × 0.875 UI). The funnel's finding: **compression binds, not the eye** — 61 % of the approved box cannot be evaluated at the PCIe input level. S8 confirmed non-binding by measurement, agreeing with `CHANNEL_MODEL.md` §5 by an independent path. Read §7 before quoting anything: TT-only, and the BER is a bound with device noise only | quoting any eye number, or believing "the link layer is a mock" |
| 14 | [`GMID_MAP.md`](GMID_MAP.md) | A gm/I_D table and a design-space inverse map, **measured and not adopted**. The reparameterization's stated mechanism is false (G44 among simulated designs is unchanged, 38.07 → 37.74 %); its real benefit is 1.16× on simulations per valid design. Three PDK findings that outlive it: the gm/I_D W-independence premise fails on SKY130 at fixed `nf`; you write microns and read back metres; an out-of-bin **length** is silently extrapolated where an out-of-bin **width** is refused | doing any gm/I_D work, or building any pre-simulation filter |

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
  mock.py              SYNTHETIC. Fake numbers by construction. Never reaches a deliverable,
                       and no longer reachable from a training run — a test asserts it.
  passives.py          R and C as real SKY130 devices, with the three silent traps pinned.
  netlist_gates.py     Refuses to EMIT a parameter SKY130 accepts and then ignores:
                       `w` on a fixed-width resistor, `mult`/`mf` other than 1. Gated on
                       the assembled text, so no path through the device layer escapes it.

link/                  Device result -> eye.
  channel.py           The channel FAMILY: IL(f) = A*sqrt(f) + B*f, parameterised by
                       (loss at Nyquist, skin/dielectric split). Minimum-phase
                       reconstruction, then causality / passivity / monotonicity GATES.
                       Equivalent length is reported from a stated stackup, never used
                       to derive the loss. Dependency-free Touchstone 1.x parsing.
  tx.py                The PCIe Gen2 transmitter as the 2-tap FIR it actually is.
                       Supplies exactly -de_emphasis_dB of tilt at Nyquist.
  cursors.py           Pulse response -> UI sampling -> h_-2..h_4 -> residual ISI after
                       an ideal 1-tap DFE -> eye. Closed-form CTLE peak location.
  calibration.py       Normalised amplitude -> volts. THE conversion, in one place.
  config.py            LinkConfig + the PCIe Gen2 anchors (swing, de-emphasis).
  spice/               Netlists, the trimmed SKY130 library, and .spiceinit.

  fit.py               The POLE-ZERO FIT: measured AC curve -> (g_dc, f_z, f_p1, f_p2)
                       + residual, REJECTED above 0.5 dB (§5.3b). Exact on synthetic
                       data; the basin is probed from +/-2 decades, not assumed.
  bridge.py            THE G2 DELIVERABLE. `device_result_from_point` is the adapter
                       that had never existed -- only device/mock.py ever built a
                       DeviceResult, so the two real layers had never been joined.
                       `evaluate_link` is the real one. Volts end to end, so §5.3a
                       needs no conversion; compression is a VALIDITY condition, not
                       a clamp. See G2_RESULTS.md.
  mock.py              SYNTHETIC. Superseded by bridge.py for every real path; kept
                       because the interface tests are written against it.

rl/                    THE LOOP. contract.py is the environment contract — the nine-
                       dimensional box (copied from the experiments, never re-derived),
                       the 20-dim observation, and FIXED normalisation scales.
                       evaluator.py validates every result before it becomes an
                       observation; an invalid one is a hard negative and a terminated
                       episode, never a default. env.py owns the episode; ppo.py is a
                       minimal torch PPO (neither SB3 nor gymnasium is installed);
                       runlog.py writes the tracked JSONL. reward.py is CLAUDEwa §9's
                       form; reward_v1.py is the shape that replaced it, scoring EVERY
                       violated constraint rather than only the worst.
                       hybrid_designer.py keeps V6 compliance as a hard gate,
                       then centres safe choices on requested peaking/frequency;
                       an existing-bank refinement launches no new SPICE run.

experiments/           One script per measurement. Each owns its assumptions and prints
                       them in every run's header. Data files are committed alongside.

tests/                 2,777 non-slow tests across both projects. Simulator
                       cases skip cleanly when their required tool is absent.

web/                   Local evidence-grounded dashboard. One background worker
                       calls the existing RL-hybrid product; the browser only
                       presents recorded results. Includes PVT exploration,
                       circuit-to-circuit comparison, channel intake, Judge mode
                       and evidence ZIP download. No algorithm leaderboard.

channel_upload.py      Real .sNp intake: hash/provenance, chosen port path,
                       measured Nyquist loss, reduced-model fit and diagnostic PNG.
                       Explicitly not an RL verification of the uploaded channel.
```

---

## Two things that look like bugs and are not

**`common/params.py::BOUNDS` is not what the RL loop reads.** Choosing
parameter ranges is a human decision: too wide and the simulator will not
converge over most of the box, too narrow and the optimum is outside it — and
*neither failure announces itself*. Both just look like "the RL didn't work".
So `params.py` still carries the superseded 1.2 V box and is **untouched**; the
proposed box lives in `experiments/s3_yield.py::PROPOSED_BOX` and in
`BOUNDS_REDERIVATION.md`, awaiting approval, and `rl/contract.py` copies seven
of its nine edges verbatim with a test asserting they have not drifted apart.

**The mocks produce fake numbers.** `device/mock.py` and `link/mock.py` exist so
that three layers could be built in parallel before the simulator was working.
Their *trends* are physically coherent; their *magnitudes* are invented. No
value from either may reach a report, a slide, or a results table — and since
session 17 there is **no import path from a training run to either of them**,
checked in a subprocess by `tests/test_no_mocks_in_training_path.py`. That test
also pins the consequence: because the whole link layer is synthetic, **S8
cannot be scored by the RL reward at all**, which is a conclusion rather than a
gap.

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

# Profile a real channel file (does not claim the frozen RL bank verified it)
python -m nebula.channel_upload board.s4p --ports 1 3 --out channel_report

# Open the local engineering dashboard (Python 3.13 on this Windows machine)
py -3.13 -m nebula.web
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
