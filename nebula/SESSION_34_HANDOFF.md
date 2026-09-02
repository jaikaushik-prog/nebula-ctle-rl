# SESSION_34_HANDOFF.md — the tuning-bank / RL / attenuator line

**Written 2026-09-02 at the end of session 34, for whoever picks this up.**
Branch **`nebula/tuning-bank-rl`**, 20 commits ahead of `main`, working tree
clean (only the pre-existing untracked `gmcmp.pkl`).

Read `CLAUDE.md`, then `CLAUDEwa.md`, then `nebula/CONTINUE_HERE.md`, then this.
Everything below is in `PROGRESS.md` §5z–§5ad and `PREDICTIONS.md` entries 70–75
with full detail; this file is the map, not the record.

---

## 1. What this session was asked to do, and what happened

The owner asked to make the **reinforcement learning actually contribute**,
after an independent review scored the RL dimension 6/20 because the delivered
path (`design.py --method auto`) contains no RL at all.

The chosen line was **decision D10**: build the CTLE's tunable bank as the
delivered topology and put the RL on the **adaptation** problem — infer the
tuning code from what a receiver can observe, without being told the corner.

**That line produced three measured negatives and one real circuit finding.**
No policy was trained, and the reason is recorded rather than worked around
every time.

---

## 2. The five results, in order

| # | Entry | Result |
|---|---|---|
| 1 | §5z | The 3×5 bank RAN (it had been written in session 22 and never run): **45 of 45 mandated corners served**. The same base design *fixed* serves **0.0 %** of S3's frequency window; banked, **100 %** |
| 2 | 70 | The wide 8×8 bank (64 codes = 6 bits) reaches **1.78–13.05 dB** and **1.109–3.387 GHz**, covering S3's mandated ranges, and the code→response map is **monotone and separable**. Scored **5 of 5** |
| 3 | 71 | One fixed part + 6-bit code serves **8 of 16** requests at 45 mandated corners. **Q3 failed — six of the eight need only ONE code**, so across PVT the knob is decoration. Scored **2 of 5** |
| 4 | 72 | The channel probe: the stage **saturates on every channel shorter than ~9 dB**, at every code. Q4 failed; Q1/Q2 **not read**, per the rule committed before the run |
| 5 | 73–75 | The missing block is **input attenuation**, not a load trim; it is sized, built opt-in, and measured working; and its switch must be a **PMOS**, binary-weighted |

### Why the RL line closed

Entry 71 is the one that matters. **The right tuning code depends on the
*request*, which the policy is handed — not on the hidden corner.** A policy
trained on that artifact would be learning a 16-row lookup table, which is this
project's recurring result (entry 36, `POSITIONING.md` §1) arriving by a third
road.

Entry 72 tried the channel as the hidden variable instead, and could not measure
it: the stage saturates across most of the channel family, so there were no
scorable codes to move *between*. **Q1/Q2 are unmeasured, not refuted.**

`rl/adapt_env.py` and `experiments/exp_adapt_controls.py` are committed
**unrun**, complete with an observation-leak gate and the oracle / exhaustive /
hillclimb / fixed / random controls, split by **process** so test corners are
held out. They are ready the moment there is an adaptation problem worth having.

---

## 3. Where the work stopped, and the exact next step

**Defect 1 from entry 74 is solved in design but not in code.**

The attenuator's shunt switches were NMOS to `cm = 1.5 V`: `Vgs = 0.3 V` against
a body-effect-raised `Vth = 0.890 V`, measured at **9.15 GΩ** — off. Entry 75
measured the replacement:

    device               Vgs     Vth   overdrive       Ron
    PMOS, gate at 0    1.500   0.872      +0.628     102.17 ohm
    NMOS, gate at VDD  0.300   0.890      -0.590    9.148e9 ohm

    Ron * W = 4086.8 ohm.um, 0.0 % spread over W = 40..400 um

and the design that follows — **switches binary-weighted alongside the
resistors**, so `Ron` is a constant fraction of every leg and the 1:2:4
conductance ratio survives any PVT shift:

    bit  switch W  nf   Ron     drawn R   leg total   target
     0     40 um    1  102.17    969.2     1071.4     1071.4
     1     80 um    2   51.09    484.6      535.7      535.7
     2    160 um    4   25.54    242.3      267.9      267.9

### THE NEXT STEP, precisely

**The trim carries no pfet, so `run_point` cannot instantiate any of this.**
Every entry-75 number comes from the FULL `sky130.lib.spice`.

1. **Measure the parse cost first.** The trim exists to keep the inner loop fast
   (16.5 s → 0.02 s, G34) and the extended library is 25 sections. Adding a
   device family to all of them is exactly the cost the section-splitting work
   was about. `experiments/lib_cost.py` is the instrument.
2. **If the cost is immaterial:** add the pfet includes to
   `nebula/device/spice/sky130_ctle.lib.spice` — 25 `nfet_01v8__<corner>.pm3`
   sites and 25 `nfet_01v8__mismatch` sites, one pfet line after each, corner
   for corner (all five pfet corner files exist) — then
   `python -m nebula.device.pdk_trim --write`. The generator's `needed_names`
   pulls the pfet parameter set (`lod.spice`, `invariant.spice`) in
   automatically; that is why the standalone deck needed them and the trimmed
   decks do not carry them today.
3. **If the cost is material:** build a pfet-only library variant used only when
   `atten_code is not None`, so the delivered path stays byte-identical and
   un-slowed.
4. Then set `attenuator.SWITCH_RON_OHM` from the **measured** PMOS number,
   switch the emitted device to `pfet_01v8` with per-bit widths, and re-run
   `exp_atten_verify --run` with `switched=True`. **It must reproduce the
   switchless table** (first clearing code 5, limit constant ~1110 mVpp).

`nebula/device/spice/g5_pmos_switch.cir` and
`experiments/pmos_switch_results.json` hold the characterisation.

---

## 4. Standing traps this session hit — do not re-learn these

* **G140 (new).** `run_point(vid_max=0.8)` is a **fixed** sweep range. Anything
  that reduces gain into the input pair means the pair never reaches its own
  limit inside the sweep, so the reported "linear limit" collapses in proportion
  and the compression ratio looks constant no matter what you do. **Scale
  `vid_max` by `1/A`.** This made input attenuation look impossible for an hour.
  No committed number is affected — they are all at unity input gain.
* **G139 (new).** A test that filters `if ok` and then asserts a property over
  the survivors silently skips the cases that matter. Mine passed while five of
  seven channels were being rejected outright. Assert the **membership**.
* **`W` is the TOTAL width in a SKY130 subckt; `nf` only splits it into
  fingers.** `Ron` is flat in `nf` and scales as `1/W`. The **per-finger** width
  is what must stay in bin: `W=120 nf=1` is refused, `W=120 nf=3` is fine.
* **`resistor_geometry` returns an `m` multiplier.** Drop it and you emit a
  resistor `m` times too large; the deck still simulates. Use `_m_suffix` — ` m=`,
  never `mult=` (G56).
* **Do not carry a measured constant across without its condition.** The whole
  attenuator defect was the nfet's `Ron = 16.5 Ω`, measured at `Vgs = 1.8 V`
  with the source near ground, reused at a 1.5 V source.

---

## 5. What must NOT be said about any of this

* **8 of 16 (entry 71) may not be compared with, or added to, entry 69's 14 of
  16.** Different evaluator (`evaluate_at_points`, not `verify_full`), one load
  not three, and `S4_hd3_nyq` at the operating point rather than S4's literal
  100 MHz row — so entry 71's set is **stricter**, not laxer.
* **The 135-point load grid is still 0 of 16.** Untouched by this session.
* **The attenuator has no coverage number.** One bank code, TT, one load, and
  the switches bypassed. It is an instrument, not a deliverable: a fixed pad
  cannot adapt.
* **Entry 72's Q1/Q2 are unmeasured, not refuted.**
* Every attenuator result assumes an **ideal VCVS source**. A real receiver
  terminates its input (100 Ω differential) and a resistive divider interacts
  with that termination. Out of scope at schematic level.

---

## 6. State

* Branch `nebula/tuning-bank-rl`, 20 commits, tree clean.
* Suite **2 522 passed, 13 deselected, 334 s**, certified on the final commit
  (2 433 at session start — this session added **89** tests across
  `test_tuning_bank`, `test_bank_sweep`, `test_request_rows`, `test_adapt_env`,
  `test_channel_axis`, `test_attenuator`). Run it from the repo root with the
  **system** interpreter: `python -m pytest tests nebula/tests -q -m "not slow"`.
* Decisions **D10** (bank as delivered topology, RL on adaptation) and **D11**
  (build the input attenuator) recorded in `PROGRESS.md` §3.
* Gotchas **G139**, **G140** added to `HANDOFF.md`.
* `reward_v1.request_rows()` is new and is now the ONE definition of the three
  request-dependent spec rows; `margins()` and `exp_coverage._rescore` both
  delegate to it. That duplicate was G115.

---

## 7. The unglamorous thing that is still the highest-value item

**The report is roughly three weeks behind the code**, and none of the above
exists in the document a judge will read. `nebula/report/Nebula_CTLE_Report.pdf`
still says the flow answers *"in one SPICE simulation, under five seconds"* (the
superseded `--method library` default; the real one is 17 sims / 22 s), mentions
**"8 of 16"** once when the delivered path does **14 of 16**, contains the word
**"SAC" zero times**, and states 1665 tests on one page and 1653 on another.

The saturation chain 72 → 73 → 74 → 75 is a genuinely strong four-step
narrative — *verified across PVT at one channel, swept the channel, found the
stage saturates on short links, proved a load trim cannot fix it, derived and
built the input attenuator that can* — and it is invisible outside the repo.

The owner deferred this deliberately, twice, to keep the engineering moving. It
should be raised again before 15 Sept.
