# Eval — Proposal 002 (designer-side adoption criteria)

**Evaluated 2026-08-29, session 29. 17 days to G5 (15 Sept), demo 25 Sept at BITS Goa.**

The brief's own type warning is correct and is honoured here: this is a practitioner
opinion piece with no algorithm, no experiment and no reproducible number. It is
**not** scored on adopt / prototype / skip. It is scored on the two uses the brief
names — a reviewer-objection checklist, and one research direction.

**Headline: this is the highest value-per-hour item in the three briefs, and it needs
no code, no simulation, and invalidates nothing.** Two of its objections already have
*measured* answers sitting unquoted in the repo.

---

## 1. Objection 1.1 — layout parasitics. We have a bounded, PDK-derived answer already.

The objection: sizing on schematic alone produces numbers that move after layout.
It is the objection this project is most exposed to — every yield number in the repo
is a schematic number, and there is no layout, no extraction, no LVS anywhere
(`grep` for `post-layout|parasitic extraction|GDS|LVS` across the repo's markdown
returns only the proposal briefs themselves).

**But `CL_RANGE.md` §4 already bounds the dominant layout parasitic on the critical
node, from PDK data, and nothing quotes it.** What it does:

* Parses `sky130_fd_pr__cap_vpp_01p8x01p8_m1m2_noshield` **at run time** —
  `ctot_a = 7.833e-16 F`, `rat_m1 = 0.387`, `rat_m2 = 0.596`, 22 and 28 squares —
  and raises if the file's structure changes rather than falling back on a
  remembered value.
* Derives **m1 = 0.0984 fF/µm, m2 = 0.1191 fF/µm**.
* Applies stated wire lengths (20 µm abutted / 120 µm displaced by a lane pitch)
  to get **1.97 fF / 14.29 fF**.
* Measures that routing is **14 % of `cl_lo` and 18 % of `cl_hi`**, and that
  **doubling the entire allowance moves `cl_hi` by 18 % — a fifth of an octave
  against a range 2.52 octaves wide.**

So the honest sentence, which is far stronger than a caveat, is:

> We do not run post-layout extraction. We bound the dominant layout parasitic on
> the output node from PDK capacitor data, carry it inside the load range the design
> is verified across, and measure that doubling it moves the range by a fifth of an
> octave against 2.52 octaves. The compliance result is not sensitive to the routing
> assumption.

**The weaknesses must be stated with it**, and `CL_RANGE.md` already states them:
the 0.14 µm metal width is **declared, not measured** (this install has no tech LEF
and no magic techfile), and **wire length is stated, not measured — there is no
layout.** Quoting the document's own honesty is what makes the claim credible; the
doc also argues the number is an *upper* bound on a routing wire, because a finger
capacitor has minimum-spaced neighbours on both sides and `ctot_a` includes the
m1-m2 coupling that makes it a capacitor at all.

**What this does NOT answer**, and we should not pretend otherwise: STI stress,
well proximity, and device mismatch. Those are the other three effects the author
names and we bound none of them. The GNN-based parasitic prediction he points at is
a research programme, not a 17-day item.

## 2. Objection 1.2 — the generalisation boundary. We have one and have never written it down.

His argument is that a practical tool must **state its own similarity boundary
explicitly**. Ours exists and is fully determined by artifacts already in the repo;
it has simply never been collected into one place:

| Axis | Our stated boundary | Source |
|---|---|---|
| Topology | one — 1-stage CTLE, source degeneration (variable Rs, Cs), no retraining claim across topologies | S2, mandated; CLAUDEwa §8 rule 5 |
| PDK / supply | SKY130, `nfet_01v8`, VDD 1.8 V ±5 % | `G0_RESULTS.md`, G33/G36 |
| Parameter box | `w_in` 20-100 µm · `l_in` 0.15-1.0 µm · `i_bias` 0.5-8 mA · `rs` 50-1000 Ω · `cs` 100 fF-10 pF · `rl` 50-800 Ω · `vcm_in` 1.1-1.6 V | `rl/contract.py` |
| Load | 13.64-78.04 fF (5.72x, 2.52 octaves), per-edge provenance | `CL_RANGE.md` §5 |
| Channel | `IL_dB(f) = A√f + B·f`, 21-member family, **loss at DC exactly 0 by construction** | `CHANNEL_MODEL.md` |
| Corners | 45 mandated (5 process × 3 VDD × 3 temp) × 3 loads = 135 points | CLAUDEwa §3, `S9_YIELD.md` |
| Spec target | effectively **1-D** — `target_peaking_db` is accepted and deliberately ignored | `CONTINUE_HERE.md` §5 OPEN item 5 |

That last row is the uncomfortable one and it belongs in the boundary statement
rather than being discovered by a judge. It is also the honest explanation for why
a lookup table serves 32 of 32 held-out targets: **on a 1-D manifold a lookup *is*
the optimal policy.**

**Cost: about two hours of writing. Blast radius: zero.** It directly serves the
brief's "zero human intervention" claim by saying what the automation is claimed to
cover — an unstated boundary invites exactly the same question with no answer ready.

## 3. Criterion 4 — consistency. Measurable here, cheap, and it is fRL-AD's own axis.

Of his four adoption criteria (scale, shared training data, ROI, consistency), three
are business arguments we can cite as motivation and cannot act on. **Consistency is
different: it is measurable from logs we already have.** `BASELINES.md` §7f runs
parallelism *across runs*, so seeded repeat runs of the same method exist in
`baselines_run_interp.jsonl.gz` and the budget-ladder logs.

Reporting run-to-run variance of the delivered design costs an analysis pass over
existing artifacts and **zero simulations**. It is worth doing for two reasons
beyond this brief: it is the *exact* axis proposal 001's paper claims (fRL-AD's
headline is variance reduction against AutoCkt, not a better mean), and
`CONTINUE_HERE.md` §5 notes that whether our variance-across-repeats is measurable
at all is an open question. Answering it closes a stated open item.

## 4. What this source does not support

No evidence, no baseline, no numbers. **Nothing here may be cited as a result.**
Cite it only as a designer's stated priorities, and only where a citation to an
opinion is appropriate: motivation, related-work framing, the reviewer-objection
checklist.

Keep the brief's own correction: the article is **Vikas Vijay (Cirrus Logic)**; the
viksnewsletter.com URL is **Vikram Sekar** and a different piece, covered in
proposal 003. Do not cite the two together.

## 5. His overall stance is human-in-the-loop; the brief mandates zero human intervention.

Worth stating explicitly because it is a genuine tension, not a detail. The Astera
problem statement asks for "**zero human intervention**"; this author's conclusion is
that assistance beats automation. The defensible position is that these are claims
about *different things* — we automate **sizing within a stated boundary** and make
no claim about topology selection, layout, or verification sign-off, which is where
his human-in-the-loop argument actually bites. That sentence is worth writing down;
it is the boundary statement of §2 doing its job.

---

## 6. Verdict

| Use | Verdict | Cost | Blast radius |
|---|---|---|---|
| Quote `CL_RANGE.md` §4 as the bounded layout answer | **DO** | ~1 h | none |
| Write the similarity boundary as an explicit deliverable | **DO** | ~2 h | none |
| Report run-to-run variance from existing logs | **DO** | ~2 h analysis, 0 simulations | none |
| Adopt anything as method | **N/A** — there is no method here | — | — |

## 7. Strongest argument against this verdict

Someone wanting the opposite would say: **this is all documentation, and documentation
does not win an engineering competition.** The brief asks for a framework that sizes
devices in fewer search spaces; the judges will look at the 8 086x speed-up, the
compliance matrix and the live demo, and none of the three items above moves any of
those numbers. Three of our 17 remaining days spent writing boundary statements is
three days not spent on the one thing that would change the result — closing the
0.0076-octave gap that stands between us and an eleven-row compliant design
(`CONTINUE_HERE.md` §5 OPEN item 2, five independent measurements of the same screen
blind spot).

**That objection has real force and should not be waved away.** The counter is
narrow and it is about *risk*, not value: OPEN item 2 is an owner decision that
carries a benchmark re-run risk (`BASELINES.md` §7f) and ~400 simulations, whereas
these three items carry none and are pure additions to a report that already exists.
They are the correct thing to do *while* waiting on the owner's call on item 2 —
not instead of it.
