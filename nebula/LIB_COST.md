# LIB_COST.md — where an evaluation's time actually went

**Session 19a, 2026-08-12; measured again and written up 2026-08-17.**
`NEXT_STEPS.md` step 1 — *"cut the per-evaluation SPICE cost, and prove the
trim is bit-identical"*.

| | |
|---|---|
| The trim generator | `nebula/device/pdk_trim.py` (`--write` to regenerate, no argument to report) |
| The generated tree | `nebula/device/spice/pdk_trim/` — 40 files, **never hand-edited** (G77) |
| The measurement | `nebula/experiments/lib_cost.py` -> `lib_cost_results.json` (tracked, G49) |
| Tests | `nebula/tests/test_pdk_trim.py` — 22 fast + 2 `slow` |
| One command | `python -m nebula.experiments.lib_cost --designs 50` |

---

## 0. What a reader in a hurry needs

1. **An evaluation with drawn SKY130 passives went from 2.887 s to 0.222 s —
   13.02x — and not one measured number moved** (50 designs x 11 fields,
   rel = 0, abs = 0).

2. **The standing explanation for the cost was wrong in both halves, and had
   been quoted for four sessions.** `PASSIVES.md` §3.2 and G70 both said the
   R/C corner files pull in `parameters/typical.spice` (3023 lines) *and*
   `invariant.spice` (7340). **`invariant.spice` is not in the include tree at
   all.** `typical.spice` is real but minor — worth **1.48x**.

3. **The real cause is that ngspice expands EVERY `.lib` section in a file,
   not just the one you ask for (G78).** One section parses in 0.093 s; the
   real 25-section extended library takes 1.386 s. The cost scales with the
   **section count**, not with what the netlist uses.

4. **The whole overhead was library PARSING — 100 % of it.** Section count
   **65 %**, parameter decks **35 %**. The passive model cards and the drawn
   devices themselves are **free**, which is the opposite of what
   `PASSIVES.md` §3.2's "the price of drawing the passives" said.

5. **This is a SINGLE-PROCESS ratio and it does not transfer** (G75).
   `baselines.SEC_PER_SIM_AT_8` must be **re-measured**, not divided.

---

## 1. Why this was the top open item

Session 17 measured that **99.7 % of a training run is the simulator** —
1585.8 s of environment against a 3.5 s PPO update and 0.9 s of logging. Every
experiment in this project is bought at the per-evaluation rate, so it is the
only throughput lever that pays; optimising the RL side is worth nothing.
`PASSIVES.md` §6 listed the fix as open from session 15 and it stayed open
through 18.

The number that made it urgent: a real-passives evaluation cost **2.07 s**
against **~0.33 s** on the nfet-only library, and the baselines sweep is
25 500 simulations.

---

## 2. The explanation that was wrong, and how it survived four sessions

The standing account, in `PASSIVES.md` §3.2 and repeated in G70 and in
`sky130_runner.lib_for_device`'s own docstring:

> the R/C corner files pull in `parameters/typical.spice` (3023 lines) and
> `invariant.spice` (7340)

**Both halves fail on inspection.**

* **`invariant.spice` is not reachable from the library.** Only
  `parameters/montecarlo.spice` includes it, and no section this project uses
  reaches that. Verified by walking the include tree:
  `pdk_trim.library_include_tree()` returns **36 files, 245 606 lines**, and
  `invariant.spice` is not among them.
* **`typical.spice` is real but minor.** It is 3023 lines, 3021 `.param`
  definition lines, defining **8909 distinct names**, of which the library
  references **86**. Dropping the other 8823 is worth **1.48x** — not nothing,
  and not the answer.

**Why it survived:** every previous measurement compared *whole libraries
against each other* — extended against nfet-only — and never a library against
**itself** with one part removed. A comparison between two libraries that
differ in four things cannot attribute the difference to any of them. The
arms in §4 each differ from their neighbour in exactly one thing, which is the
only reason their differences mean anything.

**The transferable form (G78):** *when a cost explanation has never been tested
by removing the thing it blames, it is a hypothesis, not a diagnosis.*

---

## 3. What the trim does

### 3.1 The parameter decks

`device/pdk_trim.py` reads the extended library's **own include list**, walks
it, collects every identifier it references (3777), and keeps only the
`.param` definitions reachable from those — closed over right-hand sides, PDK
order preserved.

| deck | kept | of | |
|---|---|---|---|
| `fast.spice` | 43 | 3021 | 1.4 % |
| `fast_70p.spice` | 43 | 3021 | 1.4 % |
| `slow.spice` | 43 | 3021 | 1.4 % |
| `slow_70p.spice` | 43 | 3021 | 1.4 % |
| `typical.spice` | 43 | 3021 | 1.4 % |
| **total** | **215** | **15 105** | **1.4 %** |

**The keep-set is derived, never listed.** Because it is read out of the
library's include list, **adding a device to the library automatically widens
it**, and the regeneration test goes red until someone reruns the module. That
is what stops the trim going stale — G32's failure (the file a human reads is
not the one that produced the numbers) one layer up.

### 3.2 The section split (the actual fix)

`.lib <file> <section>` does not parse only `<section>`. ngspice expands the
whole file. Measured on the same netlist and machine:

| | parse |
|---|---|
| extended library, **one** section extracted | **0.093 s** |
| extended library, the real **25**-section file | **1.386 s** |
| nfet-only library, the real **5**-section file | 0.297 s |

The extended library grew to 25 sections the day **G58** added the 5 x 5
(MOS x passive) corner cross product — so a decision about *corner coverage*
showed up as a *throughput* regression that nobody could attribute to it.

`pdk_trim` therefore also emits one file per section — 25 for `sky130_ctle`,
5 for `sky130_nfet_only` — and `sky130_runner.lib_for_device(..., section=)`
selects one, **falling back to the monolithic library when the file is
missing** so an un-regenerated tree still runs, just slowly.

---

## 4. The measurement

**Five arms, each differing from its neighbour in exactly one thing.** 50
realisable box designs, corner TT, **single process** (G70: one concurrent
ngspice makes each run 4.8x slower, which would make the number meaningless).

    untrimmed_mono   PDK parameter decks + 25-section file   <- session 18's state
    trimmed_mono     trimmed decks       + 25-section file   <- the deck trim alone
    trimmed_split    trimmed decks       + 1-section file    <- today
    extended_ideal   IDEAL R/C netlist   + 1-section file    <- the drawn-device cost
    nfet_only        IDEAL R/C netlist   + nfet-only library <- the floor

**G71's protocol, all three defences on**, because a benchmark run in a fixed
order measures the order and it nearly published a wrong conclusion once:
a **discarded warm-up**; **arm order re-shuffled per design** (stronger than
once per sweep — it also averages out drift); and a **control**, the first arm
re-run at the end over the same designs.

### 4.1 Timings

| arm | median s | mean s | p10 | p90 | failed |
|---|---|---|---|---|---|
| `extended_untrimmed_mono` | **2.887** | 3.156 | 2.778 | 3.963 | 0 |
| `extended_trimmed_mono` | 1.955 | 2.089 | 1.865 | 2.639 | 0 |
| `extended_trimmed_split` | **0.222** | 0.228 | 0.200 | 0.281 | 0 |
| `extended_ideal` | 0.209 | 0.221 | 0.186 | 0.271 | 0 |
| `nfet_only` | 0.216 | 0.217 | 0.186 | 0.260 | 0 |

**End to end: 13.02x.** Of which the parameter-deck trim alone is **1.48x**.

**Control: 2.740 s against a first pass of 2.887 s, ratio 1.05x — clean.**
Outside [0.8, 1.25] the wall-clock numbers would be **void, not adjusted**.

### 4.2 Where the time went — additive, and the answer is not the circuit

      0.216 s   floor: ideal R/C netlist on the nfet-only library
    + 0.000 s   the passive model cards          (indistinguishable from zero)
    + 0.012 s   DRAWING the passives                            (0.5 %)
    = 0.222 s   a real evaluation TODAY
    + 1.733 s   the 24 sections the run never uses              ( 65 %)
    + 0.932 s   the R/C parameter decks                         ( 35 %)
    = 2.887 s   what an evaluation cost before this session

**Two results here that were not the question and matter more than the answer
was going to.**

* **Drawing the passives is free.** 0.012 s on a 0.222 s evaluation — half a
  percent. `PASSIVES.md` §3.2 called the extended library's cost "the price of
  drawing the passives"; **it was never the passives.** Nothing about running
  the framework's output as a real schematic is expensive.
* **The passive model cards are free too.** The measured term is **-0.007 s**
  — `extended_ideal` came out *faster* than `nfet_only`, which is noise on a
  p10-p90 spread of ~0.09 s, and the honest reading is **zero**, not a
  negative cost. Carrying the poly-R and MIM model cards costs nothing.

So **100 % of the overhead was library parsing**, and both terms are now
fixed.

---

## 5. Equivalence — the gate, and it is not optional

G36 set the precedent: a speed-up obtained by dropping model cards is
worthless unless it changes no number, and "bit-identical" means **rel = 0,
abs = 0**, not "within tolerance".

* `test_pdk_trim.py` runs a probe exercising **every device the netlists
  use** — the nfet, both generic poly families, five fixed-width variants of
  each, the `res_po` parasitic, the MIM, and routing capacitors that make the
  kept parameters load-bearing — through the untrimmed library and the trimmed
  one, and compares the **raw printed text**, not floats parsed first.
* Further tests do the same for the one-section split, and a `slow`-marked
  pair against the **full** SKY130 library.
* **`experiments/lib_cost.py` re-checks on 50 real designs through
  `run_point`**: 11 fields each, **0 differing values**, and it exits non-zero
  if one moves.

**Three tests exist to prove the gate can fail** (rule 10): dropping a kept
parameter, editing a process constant in a copied R/C deck
(`crpf_precision`), and an undefined-parameter run. Each is deliberately
broken and watched go red.

### 5.1 A G26 inside the G26 guard

Building this found that `crosscheck.scan_for_silent_failures` **missed
ngspice's own fatal error**. Two lines got through:

    Undefined parameter [cm3d]
    ERROR: fatal error in ngspice, exit(1)

The first was not in the pattern list at all; the second missed
`^\s*Error[:,]` **on case** — the pattern was anchored case-sensitively and
ngspice shouts. The equivalence probe was therefore reading a run that had
**aborted**, and comparing empty result sets, which compare equal. Fixed, with
a test carrying the verbatim output.

**The asymmetry is worth knowing on its own:** a `.model` card whose parameters
are undefined is accepted **in silence** as long as nothing instantiates it,
and is **fatal** the moment something does.

---

## 6. What it bought downstream

At **0.222 s** against the 2.07 s that every plan was costed at:

* `NEXT_STEPS.md` step 2's baselines sweep was budgeted at **~12.0 h**;
* session 20's validation experiment ran **1500 drawn-passive evaluations in
  320.9 s** — 0.214 s each, independently confirming this number on a
  different workload;
* the sweep may now afford the **P2 rung** and **P3's screened arm**, which
  `BASELINES.md` §1 cut **only for cost**.

---

## 7. What this does NOT license

**Do not divide this ratio into a parallel budget.** G75, measured: a speed-up
obtained on isolated evaluations does not transfer to a workload whose workers
also compute — session 17's **2.98x at 8 workers became 1.80x** on the
benchmark's own task mix. `baselines.SEC_PER_SIM_AT_8` is a *parallel*
constant (1.698 s, from a single-process 3.060 s at 1.802x) and it must be
**re-measured with `--pilot`**, not derived from anything here.

**Do not read the 13.02x as a claim about the RL loop.** It is a
per-evaluation ratio at TT on 50 designs. What a training run does with it
depends on the parallel rate above.

**The `nfet_only` arm is not an apples-to-apples comparison** and is not
offered as one: it runs a **different netlist** (ideal R/C), because the
nfet-only library has no resistor or capacitor model cards at all. It is
measured because ~0.33 s is the figure every throughput estimate in this repo
was anchored to, and the useful question is "how close does the trim get to
the floor" — answer, **it reaches it**.

---

## 8. Open

1. **Re-measure `baselines.SEC_PER_SIM_AT_8`** with `--pilot`, then re-run
   `python -m nebula.experiments.baselines --budget`. Until that lands, the
   sweep's 12 h estimate stands as the planning number even though it is
   certainly stale.
2. **`PASSIVES.md` §3.2 still carries the wrong explanation** and the "7.3x
   regression" framing. It should be corrected in place, the way HANDOFF §8's
   compression line was — the old text is wrong, not merely superseded.
3. **G70's own text repeats the `invariant.spice` claim** and needs the same
   correction.
4. **The passive corner axis is still 5 x 5 = 225 corners** (`PASSIVES.md` §6
   item 3). The split makes each one cheap; it does not reduce how many there
   are.
