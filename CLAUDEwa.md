# CLAUDE.md — Nebula: RL-Driven CTLE Sizing

Read this file fully before writing any code. It is the contract for this repo.

---

## 1. What this project is

We are building a **fully automated reinforcement-learning framework that sizes a
CTLE equalizer for a 5 Gbps PCIe Gen2 link**, from a target specification vector to
a verified, corner-robust transistor-level netlist, with no human in the loop.

This is a competition entry for **Nebula**, a technical challenge run by
**Astera Labs** with BITS Pilani (K K Birla Goa campus), in the *AI/ML for Analog
Circuit Design* track. The judges are practising analog/SerDes design engineers.
They care about circuit correctness and honest results far more than ML novelty.

### Hard deadlines

| Date | Milestone |
|---|---|
| 6 Aug 2026 | Abstract submission |
| 12 Aug 2026 | Abstract shortlisting |
| **15 Sept 2026** | **Final submission — the real deadline** |
| 19 Sept 2026 | Final shortlisting |
| 25 Sept 2026 | Final presentation, live, at BITS Goa |

Team of three. Prizes ₹50k / ₹30k / ₹20k, plus internship consideration.

---

## 2. The problem statement (verbatim from Astera)

> Demonstrate a fully automated framework for schematic design of analog circuits
> using Reinforcement Learning. Given circuit specifications, build an automated
> design flow that sizes devices using fewer search spaces (lowest design time) to
> reach near-optimal solutions. Use case: Equalizer circuit design (PCIe PHY).
> Should take significantly lower time than sweeping all MOS, R, C, L parameter
> space, **with zero human intervention**.

### Objective

Develop an RL-based automation framework to automatically design an equalizer for
the given specifications, with minimal to zero human intervention.

### Deliverables (mirror this language in all reports)

1. A Reinforcement Learning based **Python framework that takes target specs as
   input**, seamlessly integrates with a SPICE simulator, and **outputs the final
   schematic and resulting specs**.
2. *Bonus:* LLM-based human interaction with a wrapper to fine-tune.

### Tools mandated

Python, Anaconda · LLM, Gym utils · **NGSpice or PySpice** · **Open-source PDK
(IHP 130nm BiCMOS or SkyWater SKY130)**.

Do not propose Cadence, Spectre, or any commercial tool in deliverables. The
open-source constraint is explicit and non-negotiable.

---

## 3. The specification — the single source of truth

| # | Spec | Target | Notes |
|---|---|---|---|
| S1 | Signalling | NRZ, PCIe Gen2, 5.0 Gbps | Nyquist = 2.5 GHz |
| S2 | Topology | 1-stage CTLE with source degeneration (variable Rs, Cs) + 1-tap DFE | fixed, do not change |
| S3 | HF peaking boost | **3–12 dB**, tunable, peak in 1.25–2.5 GHz | **THE binding constraint — measured 5.3% hit rate.** tunable = the policy must reach any point in this range on demand |
| S4 | Linearity | **HD3 < −30 dB** @ 100 MHz differential input | relatively relaxed; do not over-engineer. Measured ~60 dB inside spec |
| S5 | Input-referred noise | **< 1.5 mV_rms**, integrated 10 MHz – 5 GHz | measured **free** — 90.7% of the box meets it |
| S6 | Power | **< 15 mW** | measured **free** — 90.7% of the box meets it |
| S7 | Area | **< 0.05 mm²** in 130nm | passives (Cs, RL) dominate |
| S8 | Eye opening | **> 0.4 UI horizontal AND > 100 mV vertical** | link-level metric — see §5.3 |
| S9 | PVT | TT, SS, FF, SF, FS × VDD ±5% × 0–125 °C | **all specs must hold at every corner** |

**S9 applies to S3–S8 simultaneously.** A design that meets everything at TT/27 °C
and fails at SS/125 °C is a failed design and must score as such.

### S3 is ambiguous, and we state our reading rather than pick the convenient one

"HF peaking boost 3–12 dB, peak in 1.25–2.5 GHz" admits two readings:

- **(a) peak-to-DC ratio** — max|H(f)| / |H(0)|, wherever the max falls.
- **(b) in-band boost** — |H(f_Nyquist)| / |H(0)|, the gain where the data is.

They are **not the same number and can have opposite signs.** A measured
example from this project (the SKY130 smoke test): peaking **+3.82 dB** — a
pass under reading (a), inside the 3–12 dB band — with the peak at **724 MHz**
and the response **0.99 dB BELOW its own DC gain at 2.5 GHz**. Under reading
(b) that stage is worse than a wire. It equalises nothing.

**Our interpretation: BOTH must be reported and BOTH must be met.** The
frequency window in S3 exists precisely to stop reading (a) being gamed, so we
read the spec as requiring the peak magnitude *and* its location *and*,
implied by intent, positive boost at Nyquist. A stage that peaks below the
window is useless regardless of its peak-to-DC ratio.

Implementation: `nebula/device/crosscheck.py::DerivedAc` exposes `peaking_db`
and `nyquist_boost_db` as separate properties, and a test pins the distinction
using the real SKY130 numbers above. **If a judge reads S3 the other way, we
have shown we considered both** rather than having quietly chosen whichever
was easier to pass. Say so in the report.

Note on binding constraints: with HD3 at −30 dB, linearity is comfortable. The
real fights will be **noise vs. power** (S5/S6) and **corner spread** (S9). Bias
effort accordingly.

---

## 4. Provided resources and how to treat each

Everything below lives in `resources/`. **Read this section before using any of them.**

### 4.1 `ISCAS_ML_EDA_2026.pdf` — Guo, Fu, Bhanushali, Zeng, Banerjee, Sanyal

*"Balancing Speed and Accuracy for Robust Analog-Mixed Signal Circuit Design using
Closed-Loop Reinforcement Learning with Ensemble Neural Network Surrogates"*, ISCAS 2026.

**This is our methodological base.** Key ideas we adopt:
- PPO policy proposing normalized parameter vectors in [0,1]^d
- Ensemble MLP surrogate regressor trained with a **regression focal loss** (their Eq. 1, γ=2)
- **Discriminator critic** penalising out-of-distribution proposals (their Eq. 3–4)
- **Blend scheduling**: run real SPICE on only 0.2–5% of steps, surrogate on the rest.
  Their result: 0.5–1% SPICE beats full SPICE-in-the-loop accuracy at 2–3× the speed.
- Component-importance scoring from first-layer regressor weights (their Eq. 5–6)

**What the paper does NOT do, and we must:** it optimises SNDR/SFDR on an ADC
front-end at nominal only. **No PVT corners. No link-level metrics. No spec
conditioning.** Those gaps are our contribution — see §5.

### 4.2 `ams_rl_ppo/` — reference implementation of the above

Working Python: PPO/DDPG via Stable-Baselines3, ensemble regressor, discriminator,
the four mode schedules, evaluation harness.

> **Treat this as plumbing to port, not as a source of truth.**
> Its `simulator.py` is a **synthetic analytic stand-in, not SPICE**. There is no PDK.
> The shipped `results/table_bootstrapped_switch.md` is **degenerate** (100% at the
> 60 dB threshold and 0% at 75 dB for every method — the thresholds discriminate
> nothing). Do not anchor on those numbers, do not cite them, do not treat them as
> a target to reproduce.

Reuse: `regressor.py`, `discriminator.py`, reward structure, mode scheduling, the
component-importance analysis. Replace: the simulator, entirely.

Keep a fast synthetic environment behind a flag for CI and for developing the RL
loop without waiting on SPICE. Do not delete it.

### 4.3 `serdes-dsp-framework/` — our own prior work

~7,200 lines of **test-validated** behavioural link modelling (48 passing tests),
originally targeting 112G PAM-4 in 28nm. This is our biggest asset. Relevant modules:

| Module | What we use it for |
|---|---|
| `rx_frontend.py` → `CTLE` | 1-zero/2-pole model `H(s) = g_dc(1+s/ωz)/((1+s/ωp1)(1+s/ωp2))`; the target of our pole-zero fit |
| `statistical_eye.py` | Semi-analytic BER engine: ISI PMF + Q-folding, bathtub to 1e-15, eye width in UI, crossing-jitter and clip feasibility |
| `statistical_eye.py` → `optimize_ctle()` | Classical grid-search CTLE optimiser — **our baseline to beat** |
| `equalizers.py` → `DFE` | Joint LMS FFE+DFE; set `n_taps=1` for S2 |
| `channel.py` | Loss-model / S-parameter channel, pulse response extraction |

**Honesty rule:** this framework is pre-existing team infrastructure and is
declared as such in the abstract, report, and slides. The RL sizing loop, the
corner-aware fidelity hierarchy, and the device→link bridge are new work.

Retarget needed: **112G PAM-4 → 5 Gbps NRZ.** Audit every 4-level assumption —
`_slice_pam4`, `hard_slicer_pam4`, `PAM4_RMS = sqrt(5)`, the `0.75·Q(·)` BER
prefactor in `statistical_eye.py`, Gray coding in `pam4_chain.py`. **Keep the PAM-4
path working behind a flag. Do not fork the repo.**

The Cadence Ocean scripts, Verilog-A models, SystemVerilog RTL and UVM in that repo
are good engineering but **out of scope** — open-source tooling only. Leave them in
the tree; do not reference them in deliverables.

---

## 5. Architecture — three layers

```
┌─ RL layer (rl/) ───────────────────────────────────────────────┐
│  PPO · ensemble surrogate · OOD discriminator                  │
│  spec-conditioned observation · hierarchical fidelity schedule │
└───────────────────────────┬────────────────────────────────────┘
                            │ params: dict[str, float]
┌─ Device layer (device/) ──▼────────────────────────────────────┐
│  CTLE netlist → ngspice (.op .ac .disto .noise) per PVT corner │
│  → DeviceResult (gain, poles/zero, HD3, noise, power, area)    │
└───────────────────────────┬────────────────────────────────────┘
                            │ DeviceResult
┌─ Link layer (link/) ──────▼────────────────────────────────────┐
│  pole-zero fit → CTLE model → 1-tap DFE → StatisticalEye       │
│  → eye height (mV), eye width (UI), BER bathtub                │
└────────────────────────────────────────────────────────────────┘
```

The **device→link bridge** is the intellectually distinctive part of this project.
Nobody else in this competition will close the loop from transistor W/L to a
BER-1e-15 eye contour. Get it right and validate it.

### 5.1 Interface contracts — freeze these before writing implementations

```python
# common/types.py

@dataclass(frozen=True)
class Corner:
    process: Literal["tt", "ss", "ff", "sf", "fs"]
    vdd_scale: float          # 0.95, 1.00, 1.05
    temp_c: float             # 0, 27, 125

@dataclass(frozen=True)
class TargetSpec:
    peaking_db: float         # 3..12
    f_peak_hz: float          # 1.25e9..2.5e9
    hd3_max_dbc: float        # -30
    vn_in_max_vrms: float     # 1.5e-3
    power_max_w: float        # 15e-3
    area_max_mm2: float       # 0.05
    eye_h_min_v: float        # 100e-3
    eye_w_min_ui: float       # 0.4

@dataclass
class DeviceResult:
    ok: bool                  # False => simulation failed; never raise
    fail_reason: str | None
    g_dc: float               # linear V/V
    f_zero_hz: float
    f_pole1_hz: float
    f_pole2_hz: float
    fit_residual_db: float    # RMS error of pole-zero fit; reject if > 0.5 dB
    peaking_db: float
    f_peak_hz: float
    hd3_dbc: float
    vn_in_vrms: float
    power_w: float
    area_mm2: float
    vout_swing_v: float       # REQUIRED for the mV calibration in §5.3
    ac_freq_hz: np.ndarray    # raw response, kept for diagnostics
    ac_mag_db: np.ndarray

@dataclass
class LinkResult:
    ok: bool
    eye_h_v: float            # volts, NOT normalized
    eye_w_ui: float
    ber: float
    dfe_tap: float
    bathtub: np.ndarray | None
```

```python
# device layer
def evaluate(params: dict[str, float], corner: Corner) -> DeviceResult: ...

# link layer
def evaluate_link(dev: DeviceResult, cfg: LinkConfig) -> LinkResult: ...

# rl layer
def reward(dev: DeviceResult, link: LinkResult, target: TargetSpec) -> float: ...
```

**Write mocks and interface tests for all three before any real implementation.**
Three people building in parallel against a frozen interface is the only way this
finishes by 15 September.

### 5.2 Parameter space (the RL action space)

Roughly 14–16 dimensions, normalized to [0,1]. Comparable to the paper's 26/38.

| Group | Parameters |
|---|---|
| Input pair | W, L, nf |
| Tail current source | W, L, nf, I_bias |
| Degeneration | Rs, Cs |
| Load | RL, CL |
| Bias | Vcm_in |
| (link layer) | DFE tap weight — not silicon, adapted in the link layer |

Ranges must be set by a human after the hand-design in §7, not guessed by an agent.

### 5.3 The two things most likely to be silently wrong

**(a) Millivolt calibration.** `statistical_eye.py` works in normalized amplitude.
S8 demands eye height in **volts**. `vout_swing_v` from the device layer must be
carried through to convert. This is the highest-risk silent bug in the project —
a wrong scale factor produces plausible-looking numbers that are meaningless.
**Write a dedicated test with a hand-computed expected value.**

**(b) Pole-zero fit validity.** The bridge fits ngspice AC output onto
`(g_dc, f_zero, f_pole1, f_pole2)` via `scipy.optimize.curve_fit`. Cross-check
against the analytic design equations in §6. Reject fits with residual > 0.5 dB
rather than passing garbage downstream.

---

## 6. Circuit design equations

Source-degenerated differential pair CTLE. Use these for initialisation, for
sanity-checking the extraction, and for parameter-range setting.

```
k     = 1 + (gm + gmbs)·Rs/2          ← degeneration factor, see below
ω_z   = 1 / (Rs · Cs)
ω_p1  = k / (Rs · Cs)
ω_p2  = 1 / (RL · CL)
A_dc  = gm·RL / k
peaking_dB ≈ 20·log10(k)
```

`Rs` is the FULL resistance between the two sources, so each half-circuit sees
`Rs/2` — that is where the factor of two comes from. Write these with a
per-side `Rs` and every gain and peaking number is wrong.

### The body-effect term is not optional (measured, 2026-08-03)

An earlier revision of this section wrote `k = 1 + gm·Rs/2`, which silently
assumes the bulk is tied to the source. **In a bulk CMOS process it is not:**
every NMOS sits in the grounded p-substrate, so the source node swings while
the body stays at 0 V and the body transconductance degenerates alongside `gm`:

```
i_d = gm·(v_g − v_s) + gmbs·(0 − v_s)   ⇒   k = 1 + (gm + gmbs)·Rs/2
```

At the G1 hand-design point (ngspice, generic BSIM4 130nm, gm = 10.97 mS,
gmbs = 3.58 mS, Rs = 800 Ω, RL = 120 Ω) **gmbs/gm = 0.33**, and the omission
costs more than this section's own acceptance tolerance:

| | A_dc |
|---|---|
| simulated | **−14.57 dB** |
| this section as previously written (gmbs = 0) | −12.24 dB → off by **2.33 dB**, GATE FAILS |
| with gmbs | −14.29 dB → off by **0.28 dB**, passes |

So the old form failed its own 1 dB gate on a correct circuit.
`common/design_equations.py::predict()` and `cross_check_extraction()` take
`gmbs`, defaulting to `0.0` so the pre-correction form stays reproducible for
anyone checking the transcription. **Pass the simulated `gmbs` for anything
that has to agree with SPICE.**

**Consequence for hand-sizing.** The familiar `Rs ≈ 3/gm` rule of thumb
oversizes the degeneration by about a third, because it budgets the whole
degeneration to `gm`. Use `Rs ≈ 3/(gm + gmbs)`, i.e. roughly **`2.25/gm`** at
the measured gmbs/gm = 0.33. Deep n-well would tie each body to its own source
and eliminate the term entirely, at an area cost — considered and rejected;
say so in the report rather than leaving it unexplained.

**Verification requirement:** at least one full extraction must be checked
against these. If `A_dc` from the wrapper disagrees with `gm·RL/k`, something
upstream is broken and every downstream number is fiction. Do not proceed past
that discrepancy. That check is `common/design_equations.cross_check_extraction()`
and it runs **in Python against parsed `.op` output**, never inside a
`.control` block — see §8 rule 9 for why.

---

## 7. Roadmap and gates

Take the fallback the same day a gate fails. Sunk cost is how student projects miss
deadlines.

| Gate | Date | Criterion | Fallback if failed |
|---|---|---|---|
| **G0** | Aug 2 | ngspice + PDK runs DC sweep, AC sweep, `.noise`, `.disto` on a diff pair | Generic BSIM4 130nm model cards |
| **G1** | Aug 3 | Hand-designed reference CTLE meets S3–S7 at TT | Report the achievable Pareto honestly as a finding |
| **G2** | Aug 20 | One full evaluation end-to-end: params → ngspice → fit → eye → scalar reward. No RL yet. Wall-clock cost of each fidelity tier measured. | Reduce corner count; simplify link model |
| **G3** | Sep 3 | RL beats random search **and** grid search at TT, with a plot | **Stop and debug the reward function.** Do not proceed to corners. |
| **G4** | Sep 12 | Corner-robust design generated and verified; results table drafted | Ship framework + honest negative result |
| **G5** | Sep 15 | Submitted, morning | — |

Three days of slack between G4 and G5 exist deliberately. Protect them.

### Our two claimed contributions over the paper

1. **Three-tier corner-aware fidelity hierarchy.** Surrogate → TT ngspice → full
   45-corner sweep (5 process × 3 VDD × 3 temp). Promotion only on clearing the
   tier below by a margin. **Reward on worst-case corner, not nominal.** Sweep the
   promotion fraction as the paper sweeps p ∈ {0.2, 0.5, 1, 2, 5}%.
2. **Spec-conditioned policy.** `TargetSpec` enters the observation. Train across a
   distribution of specs; evaluate on held-out specs never seen in training. This is
   the live demo: type in a new spec, get a sized netlist in seconds.

### Baselines we must report against

Random search (free, from the surrogate training set) · grid search via
`optimize_ctle()` · Bayesian optimisation or CMA-ES (`scikit-optimize` / `cma`).
If BO matches RL, **say so**. That is a finding, not a loss.

---

## 8. Standing rules

1. **Never fabricate a number.** Not in code comments, not in reports, not in
   placeholder results. If a value is unknown, leave it `None` and fail loudly. Every
   number in a deliverable must be traceable to a simulation we actually ran.
2. **A failed SPICE run returns `ok=False`, never raises.** Non-convergence is normal
   and must map to a bad reward, not a crash. The RL loop cannot tolerate exceptions.
3. **The 48 existing tests in `serdes-dsp-framework` stay green.** They are the
   contract that the NRZ retarget did not silently break the eye engine.
4. **Tests before implementation** at every layer boundary.
5. **Do not change the topology (S2) or the spec table (§3)** without a human decision.
6. **Do not choose parameter ranges, reward weights, or spec-tightness heuristics
   autonomously.** Propose, and wait for a human.
7. Commit daily. One branch per workstream. Tag every gate.
8. Log every experiment from day one. Hundreds of configurations will run; without
   tracking, the September results table cannot be written.
9. **Model cards and device parameters have exactly ONE definition in the
   repo.** Netlists and runners both *reference* it; neither redeclares it.
   **A human reading any netlist must see the values that produced the
   published numbers.**

   Earned: `device/spice/g1_handdesign.cir` and `device/ngspice_runner.py`
   described "the same" G1 reference point with different `.model` cards,
   differing by one parameter — `k2`, BSIM4's body-effect coefficient, i.e.
   precisely the term §6's correction is about. Effect: gmbs/gm 0.250 vs
   0.327, A_dc −14.12 vs −14.57 dB, peaking 8.19 vs 8.29 dB. Every published
   figure came from the runner, so anyone sanity-checking by opening the
   netlist would have been quietly misled — and it silently explained away a
   discrepancy nobody could account for. If you clone a netlist, **diff the
   `.model` line**; a one-parameter drift is invisible and moved the
   body-effect term by 30%.

10. **A check that reports failure as a warning and exits zero is not a gate.**
   Every verification step must fail loudly or it is not verification. **ngspice's
   exit code alone is never a success signal** — parse the output and assert.

   Earned, not theoretical. The §6 cross-check lived in a `.control` block and
   never executed: `@m1[gm]` is in the `op1` plot, and after `.ac` the current
   plot is `ac1`, so every `let` referencing it errored. ngspice printed those
   as warnings, carried on, and exited 0. The gate looked green while computing
   nothing, and the number it was supposed to check turned out to be 2.33 dB
   wrong (§6). Consequences, now binding:
   - Derived quantities are computed **in Python from parsed primitives**, not
     in `.control`. `common/design_equations.py` is where the §6 check lives.
   - Grep ngspice output for `not available|Error:` before believing any
     derived number.
   - Every gate gets a test that proves it can fail — deliberately break the
     input, watch it go red, put it back.

---

## 9. Reward design

Extend the paper's shortfall form (their Eq. 2) across all constraints, **normalized
per-spec** so no single term dominates, and non-positive so it saturates at zero once
a spec is met:

```
R_spec = Σ_i  min( (x_i − τ_i) / (|x_i| + |τ_i|), 0 )    over S3..S8
R_total = R_spec(worst corner) + R_discriminator
```

Do not add bonus terms for exceeding a spec. Once met, further improvement should be
worth nothing — that is what keeps the policy from trading a met spec against an
unmet one.

---

## 10. Repo layout

```
nebula/
├── CLAUDE.md               ← this file
├── common/types.py         ← frozen interface contracts (§5.1)
├── device/                 ← netlist, ngspice wrapper, corner runner, PDK config
├── link/                   ← NRZ retarget, pole-zero bridge, eye extraction
├── rl/                     ← env, PPO, surrogate, discriminator, fidelity scheduler
├── baselines/              ← random, grid, BO/CMA-ES
├── llm/                    ← natural-language spec entry + design explanation
├── resources/              ← paper, ams_rl_ppo, serdes-dsp-framework (read-only)
├── experiments/            ← configs + logs, one dir per run
├── results/                ← final tables and figures
└── tests/
```

Monorepo, three packages. The interfaces are where this project breaks; keeping them
in one place with one test suite beats clean separation.

---

## 11. How we work

Human (team of 3) ⇄ Claude Code ⇄ Claude chat, in a deliberate loop:

- **Claude Code** implements: extraction wrappers, the NRZ retarget, the Gym env,
  corner parallelisation, plotting, debugging convergence failures.
- **Claude chat** is used for judgment: reward shaping, parameter ranges, "is this
  result believable or is the simulation lying", abstract/report/slide drafting,
  Q&A preparation.
- **Humans decide** anything where being wrong costs a week, and verify every number
  that reaches a deliverable.

The reason for the split: an agent will cheerfully produce clean, well-tested code
that computes a number from a broken simulation, and tests written by the same agent
will not catch it. Results get argued with by a human before they are believed.

---

## 12. Known traps

- Optimising at nominal and checking corners afterwards. **Score on worst corner from
  the start.**
- Normalized eye height presented as millivolts (§5.3a).
- Anchoring on `ams_rl_ppo`'s degenerate result tables (§4.2).
- Pole frequencies: the SerDes framework defaults to 28/56 GHz for a 28nm 112G part.
  We are at 2.5 GHz Nyquist in 130nm. Every default needs re-checking.
- Comparing RL only against random search — a judge will immediately ask about
  Bayesian optimisation.
- Full PRBS transient inside the RL loop. Unnecessary: AC + `.disto` + `.noise`
  extraction feeding the statistical eye is orders of magnitude cheaper and reaches
  BER depths transient never can.
