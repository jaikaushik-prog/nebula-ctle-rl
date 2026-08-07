# Progress board

A reader's summary of what has been done and what each step established.
Written for someone with no prior context — a mentor, a teammate joining, or a
judge.

**This file is a summary. It is not the source of truth.**
[`HANDOFF.md`](../HANDOFF.md) is, and where the two disagree, HANDOFF wins.

Last updated: **2026-08-06**, after session 14a. Tests: **698 green**.

---

## How to read this

The project runs as a sequence of numbered sessions. Each one asks a question
that can be answered by measurement, runs the simulation, and writes the answer
down — including when the answer contradicts what we expected. Three rules make
that trustworthy:

- **No fabricated numbers.** Every figure below traces to a simulation that was
  actually run, with the run count and wall-clock time recorded.
- **Predictions are pre-registered.** For the larger experiments, the expected
  result is committed to git *before* the experiment runs
  ([`nebula/PREDICTIONS.md`](../nebula/PREDICTIONS.md)). Misses are recorded as
  misses.
- **Negative results are kept.** Two central arguments this project was built
  on have been falsified by its own measurements. Both are documented in place
  rather than quietly dropped — see sessions 9d and 13b.

---

## Part 1 — the SerDes framework (sessions 1–5)

Inherited ~6,800 lines of starter code from previous students, plus a folder of
reference papers. The code looked complete.

| Session | Question | What was found |
|---|---|---|
| 1 | Is the inherited code correct? | Audit found **7 correctness bugs**, several silent |
| 2 | Fix them, and build an honest waveform engine | Scrambler fed back the wrong bit; MLSE trellis used two conventions; Monte Carlo seeding was a no-op making every run identical; BER theory was 2× off. Fixed, 48 tests added |
| 3 | Can BER be computed without counting errors? | Statistical engine built (ISI PMF + Q-folding, bathtub to 1e-15). Cross-validates against the time-domain engine within ~3× |
| 4 | Which receiver architecture actually locks? | Post-FFE Mueller-Müller locks where Alexander cannot. **ADC clipping — not equalization — limits the 0-dB-CTLE case** |
| 5 | New direction: UCIe group project | Owner takes the FFE block. No code change |

**The transferable lesson from Part 1:** the starter code passed visual
inspection and produced plausible plots while containing bugs that made its
central results meaningless. Everything after this point is written test-first.

---

## Part 2 — Nebula (sessions 6–18)

A competition track with a hard deadline: automate transistor-level CTLE sizing
with reinforcement learning, on an open-source PDK, with no human in the loop.

### Building the foundation

| Session | Question | What was found |
|---|---|---|
| 6 | Can three people build three layers in parallel? | Interfaces frozen first, mocks written for all three layers, 251 tests. Mocks produce **fake numbers by construction** and are fenced off from every deliverable |
| 7 | **Gate G0:** does the toolchain work? | **Passed.** But `.disto` returns **exactly 0** for BSIM4 — it does not implement the needed derivatives, and every open PDK is BSIM4-based. So HD3 must come from transient + FFT, at 4× the cost |
| 8 | Does the hand-designed reference circuit hold up? | The gain equation in our own contract **failed its own accuracy gate** — it omitted the body effect. In a bulk process the bulk is grounded, so the source swings against a fixed body and `gmbs` degenerates alongside `gm`. Correcting it moved the answer by 2.33 dB |
| 9 | Get the real PDK running | SKY130 installed and simulating. The contract was corrected in four places. A verification block that had been **reporting success while computing nothing** was found and moved into Python where it can actually fail |
| 9b | Why is each simulation so slow? | The full PDK costs **16.5 s to parse** per invocation. Trimming the library to the one device the circuit uses gives **0.42 s — a 40× speedup, verified bit-identical** |
| 9c | Is the reference operating point sound? | **No.** It ran at a bias no real tail transistor could provide — the sources sat 0.44 V below ground. Corrected |

### Measuring what the problem actually is

| Session | Question | What was found |
|---|---|---|
| 9d | Is the peaking spec a *coupled* constraint? | **No — falsified.** This was the project's central argument. Measured as a box-independent statistic, the coupling factor is **1.04×**: the two conditions are independent. The low yield is simply one low marginal. The claim was retracted rather than softened |
| 10b | Is the load capacitance a useful search dimension? | **No — removing it raises the yield**, 8.73 % → 13.54 %. A dimension can be worth less than a well-chosen constant |
| 10d | What do the PVT corners cost? | **39 %** of designs that pass at nominal fail at a corner. Also: **3 corners are worth 98.7 % of 45**, and the worst corner is **fast-hot, not slow-hot**, because a two-sided spec has a worst corner *per edge* |
| 11 | *Where* do the robust designs live? | **Not in the parameter box** — every coordinate is statistically null, and the two purpose-built "interiority" statistics are the *least* significant rows. They live in the **spec window**, but only once both axes are folded onto distance-to-nearest-edge. Raw coordinates carry no information at all |
| 12a | Where does the load capacitance come from? | It had been pinned at the value that maximised yield — i.e. choosing the answer. Derived instead from what physically loads the output: **13.6 / 32.6 / 78.0 fF**, entirely below the pinned value. Also: the obvious way to measure gate load **understates it 1.9–2.7×** by missing overlap capacitance and Miller multiplication |
| 12b | What does the real load range cost? | **99.4 %.** Yield falls to **1 design in 1890**. The per-load robust sets are large but almost **disjoint** — 159 of 160 designs robust at one load edge fail at the other. **The load, not the corner set, is the binding constraint** |
| 13 | The tail was two ideal current sinks. What did that hide? | **8.8 %** of the corner-robust population and **zero** of the headline — same surviving design, before and after. But the 8.8 % is *conditional* on a population the load screen had already cut by 99.4 %, so the tail is **masked, not unimportant** |
| 14a | The spec says the peaking is *tunable*. Score that | Built and **pre-registered**; the large run has not been executed yet |
| 15 | Are the resistors and capacitors real devices? | In the device layer, now yes. Three traps measured: two "multiplier" parameters that **do nothing**, a width parameter that is **inert** on the fixed-width families (4× error, silently), and — structurally — the **passive corner axis is independent of the transistor one**, so every corner number so far held the passives at typical, and the real sweep is **225 corners, not 45** |
| 16 | What channel are we actually equalising? | It had been a **single invented number with no provenance** — and by the project's own admission that number, not the circuit, decided the compression verdict. Replaced by a **family derived from the spec itself**. Its own name encoded the error: a transmission line's loss at DC is essentially **zero** |
| 16 | **Is the mandated 1-tap equaliser feedback enough?** | **Yes, across the whole 3–12 dB range** — the eye never closes. But only **15 %** of the interference it cannot cancel sits in the next symbol, and **31 % arrives more than 20 symbols later**, so extra taps would barely help. The continuous-time equaliser is the block that has to do this work |
| 16 | How much of the job does the *transmitter* do? | **Exactly 3.5 dB** — PCIe Gen2 mandates transmitter de-emphasis and specifies no receiver equaliser at all. Leaving it out had been overstating the equaliser's task by that much, and it means **the top quarter of the specified tuning range is never called for** |
| 17 | Does the whole RL loop actually run? | Yes, end to end — and **the deliverable was the failure catalogue, not the curve**. Seven integration bugs, four of which produced a plausible number and raised nothing. The largest: **78 % of everything the policy found was a fictitious peak** at the edge of the frequency sweep, which a reward reading "peaking" would have scored highly |
| 18 | **Can physics alone solve the sizing problem?** | **No, and this is the answer the project needed now rather than in September.** An analytic pre-screen predicts the peak frequency to **4.9 %** and rejects **62 % of the search space for free**, but the success rate among what it keeps is **35 %**, not the >50 % that would make a learned search method unnecessary. It is a **2.6× multiplier, not a solution** |
| 18 | Is the benchmark's best score a property of the circuit? | **No — of the measurement.** The simulator can only report peak frequencies on a fixed grid, so the reward has a hard ceiling nothing can beat. **Four different designs scored the identical number to six decimals.** The consequence is that "best score" cannot rank methods at nominal, and the benchmark had to add a second metric |
| 18 | Does a calibration transfer between populations? | **Its headline rates did and its accuracy did not** — the screen kept its rejection rate and its yield lift while its prediction error tripled and it started discarding **ten times** as many good designs as it was budgeted for. **Widening the tolerance could not fix it, because the error was a bias rather than a spread** |
| 16 | Does the stage overload? | **At 5 of 7 channel-loss points**, and worst where the channel is *easiest* — because there the equaliser's own minimum setting is more boost than the link needs. The earlier, milder reading survives, but only under a weaker definition of the question |

---

## Where the project stands

### The cost table — the single most useful output so far

| What was assumed away | What it actually costs |
|---|---|
| PVT corners | **39 %** of designs that pass at nominal |
| The load-capacitance range | **99.4 %** |
| An ideal (transistor-free) tail | **8.8 %**, and masked by the above |
| Typical-only passives | unmeasured — but the real corner count is **225, not 45** |
| A single-number channel | changed the overload verdict from **2 of 7** loss points to **5 of 7** |

The load dominates by a wide margin. The actionable consequence is *not* the
yield number — it is the tolerance: this topology absorbs a 5.7× load spread
for one design in 1890. So either the stage the CTLE drives gets specified far
more tightly, or the CTLE needs a tuning knob. Session 14 tests the second.

### Two findings about method, not about circuits

These generalise beyond this project and are the ones worth presenting:

1. **"Which spec binds" has two meanings and they disagree by an order of
   magnitude.** Ranked by *worst violation*, the tail-saturation constraint is
   1.5 % of failures. Ranked by *ever violated*, it is 13.3 %. The difference is
   that it misses by tens of millivolts while another spec misses by gigahertz.
   A first-failure table systematically hides any constraint that travels with a
   larger one — so both tables are now printed.

2. **A two-sided spec makes its own raw coordinate uninformative.** Failures off
   the top edge and off the bottom edge sit on opposite sides of any median and
   cancel exactly. Two groups with identical medians to four significant figures
   separated at p = 3e-12 once the coordinate was folded onto
   distance-to-nearest-edge.

### Open items

The full prioritised backlog is [`HANDOFF.md` §8](../HANDOFF.md). The
near-term ones:

- **Replace the ideal `R` and `C` with real SKY130 devices.** The zero
  frequency is placed entirely by two components currently modelled as perfect,
  and the competition asks for a *schematic* — real device geometries, not a
  parameter vector. This also decides whether the 3-corner screen still holds,
  since the passive families carry their own corner axis.
- **Run the tunable experiment** that session 14a pre-registered.
- **Approve the parameter box** and copy it into `common/params.py`. It is
  deliberately empty until a human fills it — an agent choosing ranges is
  forbidden, because too wide and the simulator will not converge, too narrow
  and the optimum is outside, and neither failure announces itself.
- **Gate G2:** one full evaluation end-to-end. The link bridge is still a mock.
- **Gate G3:** RL beating random and grid search. Not started.

### The honest risk

The RL loop — the thing the competition is actually about — is not built yet.
What exists is the measurement infrastructure underneath it, and a
well-characterised understanding of the search problem. That is deliberate: the
reward function has to score the worst corner, and until we knew what the
corners cost, any reward would have been guesswork. But the schedule is tight,
and G2 and G3 are the gates that matter.

---

## Glossary

| Term | Meaning |
|---|---|
| **CTLE** | Continuous-Time Linear Equalizer — an analog filter that boosts high frequencies to undo channel loss |
| **Peaking** | How much the CTLE boosts, in dB. The spec asks for 3–12 dB with the peak between 1.25 and 2.5 GHz |
| **PVT corners** | Process, Voltage, Temperature. Manufacturing spread — a design must work at all of them |
| **TT / SS / FF / SF / FS** | Process corners: typical, slow, fast, and two mixed |
| **Yield** | Fraction of randomly sampled designs meeting the specs |
| **`Rs`, `Cs`** | Source-degeneration resistor and capacitor. Together they place the zero that creates the peaking |
| **`CL`** | Capacitance loading the CTLE output — set by whatever stage comes next |
| **SPICE / ngspice** | The circuit simulator. ngspice is the open-source one the competition mandates |
| **SKY130** | SkyWater's open-source 130 nm process design kit |
| **Gate** | A dated checkpoint with a pass criterion and a pre-agreed fallback |
