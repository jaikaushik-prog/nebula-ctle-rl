# Eval — Proposal 003 (BAG, AutoCkt, ALIGN, MAGICAL)

**Evaluated 2026-08-29, session 29. 17 days to G5 (15 Sept).**

The brief's type warning is honoured: the source is a secondary survey and **nothing
in it is evidence**. The four tools are evaluated, not the article. Every
second-hand number below is flagged as such and none may enter a deliverable without
the primary paper.

**Headline: one of the four is worth acting on and it costs no build time.** AutoCkt
is not a new idea to adopt — it is the thing this project is implicitly positioned
against, and we have **already measured the comparison without naming it**. The other
three are layout or generator frameworks and are out of reach in 17 days.

---

## 1. AutoCkt — **ADOPT, as positioning.** Reading time, not build time.

The survey's description of AutoCkt's mechanism:

* start each trajectory from the **centre of the design space**, step until the
  simulated result meets the target;
* train on ~50 randomly drawn target specifications;
* at deployment, serve an unseen target from the **closest learned trajectory**,
  giving a warm start that needs far fewer subsequent iterations;
* simulation data from BAG, so layout parasitics sit inside the training loop.

**`exp_hybrid` is structurally the same idea with the learned trajectory replaced by
a library lookup** — propose a warm start, deliver it if the corner screen accepts,
else fall back to the full search. And this repo has run the comparison *both ways*
on the same harness, which is the useful and reportable thing:

| Proposer | Accept rate | Deck cost | Source |
|---|---|---|---|
| **Library lookup** (zero-simulation retrieval), k = 5 | **6 of 16** | **35.6 % fewer decks** than the 13 718-deck search | entry 32 |
| **Library lookup**, full sweep | mandated-corner coverage **7 -> 8 of 16** | **25 % fewer simulations**; 1 284 decks per delivered compliant design vs 1 960 = **34 % cheaper** | entry 40 |
| **SAC policy** (the AutoCkt-shaped, learned warm start) | **1 of 16** | 1 600 decks, 5 arms | entry 36 |
| **SAC policy**, swing-aware retrain | **0-1 of 16** | — | entry 38 |

So the positioning sentence we have never written is:

> On this problem the **retrieval** warm start delivers the benefit AutoCkt claims —
> fewer simulations to a compliant design — and the **learned** warm start does not.

And the mechanism is named, not hand-waved: the spec manifold is effectively **1-D**
(`target_peaking_db` is accepted by `reward_v1.margins` and deliberately ignored,
`CONTINUE_HERE.md` §5 OPEN item 5), and **on a 1-D manifold a lookup is the optimal
policy**; separately, **95 % of the policy's rejections are output-swing compression**
(entry 36), a quantity its reward never contained.

**Resolve the tension the brief names**, because a reviewer will: fRL-AD claims lower
*variance* than AutoCkt; AutoCkt claims fewer *simulations* than a GA+ML baseline.
**Neither is a claim about final design quality.** Our headline metric — all-45-corner
compliance coverage — *is* a design-quality claim, and that is a defensible
differentiator to state rather than a coincidence.

**Second-hand numbers that must be checked against arXiv:2001.01808 before quoting:**
~10x fewer iterations than the GA+ML baseline; 40 LVS-passing designs for a 2-stage
OTA in under 3 days on one CPU core.

**Cost:** read the primary paper, write ~1 h of related-work and one benchmark-table
row. **Blast radius: none** — it quotes results already measured and committed.

## 2. ALIGN — **SKIP for 15 Sept. Name as future work, with the cost stated.**

It is genuinely the only concrete answer to our schematic-only limitation, and the
brief is right that `ALIGN-pdk-sky130` exists with a documented
`schematic2layout.py` entry point and a five-transistor OTA worked example. The
verdict is about the calendar and the downstream, not about the tool.

Three reasons, in order of force:

1. **A GDS is not the deliverable.** The deliverable would be layout -> extraction ->
   re-simulation -> re-verification at **135 points**. That is a second pipeline
   downstream of the layout, and none of it exists.
2. **Our compliance result is currently decided by 0.0076 octaves** (`CONTINUE_HERE.md`
   §4.3: PVT spread fills **99.98 %** of S3's frequency window; room left after a
   perfect re-centring is 0.00023 octaves). Post-layout parasitics would swamp that
   margin. **The most likely outcome of a *successful* spike is "the design no longer
   complies" — a true result we would have no time to act on**, arriving days before
   submission.
3. **Toolchain risk is not hypothetical here.** This repo's own history is a
   documented sequence of exactly this failure mode: PySpice installed and broken
   (G23), volare PDK install (G33), `.spiceinit` read from the cwd at parse time
   (G29), `ngspice.exe` vs `ngspice_con.exe` (G20). A new external flow with an
   unverified PDK port is a multi-day risk against a 17-day budget with a report
   still carrying 12 open items.

**The defensible version, which costs nothing:** state ALIGN by name as the intended
next step, quote `CL_RANGE.md` §4's bounded routing answer as the interim measure
(see the 002 eval §1), and say what would have to be true to do it properly — a
working sky130 flow, an extraction path, and budget for a 135-point re-verify.

**If the owner wants it anyway:** time-box it hard, as the brief's own §5 recommends —
a strict yes/no on whether `schematic2layout.py` runs on our netlist at all, a hard
stop, and **no commitment to act on the answer**. That is a defensible use of half a
day and an indefensible use of three.

## 3. BAG / BAG2 — **SKIP.**

Generator-based: a designer writes a schematic template, marks the free parameters,
and writes **both a schematic generator and a layout generator** against a Python API.
Two disqualifiers:

* It is the opposite of the brief's mandated "**zero human intervention**" — the human
  writes the generators.
* It is a multi-week build with a layout generator at the end of it.

The survey's own named weakness for BAG — needs a good initial design point, restarts
from scratch when the spec changes — is the gap AutoCkt was built to fill, and is
already addressed here by `exp_hybrid`'s propose-else-search structure. Cite it as
related work; build nothing.

## 4. MAGICAL — **SKIP.**

Same category as ALIGN with less relevance. Its distinguishing feature per the survey
is explicit symmetry handling (seed-pattern detection for virtual grounds, passive
matching, a post-pass for missed symmetry such as bias-circuit symmetry). That is a
layout concern this project does not reach. Cite in one line alongside ALIGN.

---

## 5. Verdicts

| Tool | Verdict | Cost | Blast radius |
|---|---|---|---|
| **AutoCkt** | **ADOPT as positioning** | read primary paper + ~1 h writing | none |
| **ALIGN** | **SKIP for 15 Sept**; name as future work | 0 (or a hard-time-boxed half-day spike if the owner asks) | none if skipped; unbounded if not time-boxed |
| **BAG / BAG2** | **SKIP** | cite only | none |
| **MAGICAL** | **SKIP** | cite only | none |

## 6. Strongest argument against these verdicts

**Against SKIP on ALIGN.** Proposal 002 §1.1 is the single strongest objection an
analog-designer judge can raise, and our answer to it is currently "we bounded one
capacitance from a PDK file and assumed a wire length." ALIGN is the one tool in the
set that could turn that from a caveat into a measurement, **even for a single
design at a single corner** — and a demo that shows a real GDS next to the schematic
would land harder with a panel of designers than any number in the report. The
argument that post-layout would break compliance cuts both ways: **discovering that
ourselves and reporting it is a better outcome than a judge asking whether we
checked.** This repo's whole discipline is that a completed negative beats a deferred
one (`CONTINUE_HERE.md` §6.2 item 5 says so in those words), and skipping ALIGN is
precisely a deferred negative.

That is the best argument in this file and it is not fully answerable. The reason it
does not carry: the completed-negative principle assumes the negative can be
*completed*. With no extraction path, no 135-point post-layout verify, and a
documented history of multi-day toolchain surprises, the realistic outcome at 17 days
is not a completed negative but an **abandoned spike** — which costs the days and
produces neither the measurement nor the demo.

**Against ADOPT on AutoCkt positioning.** Naming AutoCkt as our baseline invites the
comparison to be made properly, and we would lose it on its own terms: AutoCkt reports
40 LVS-passing designs with layout parasitics **inside** the training loop, and our
RL arm is a measured null against random search. A reviewer wanting the opposite would
say we are volunteering an unflattering comparison we were not asked to make. The
counter is that the comparison is already implicit — the mentor-supplied
`nebula_ctle_rl` package is in the same lineage (PPO, delta actions, spec-vector
observation) — so the choice is between stating the positioning ourselves with the
6-of-16 vs 1-of-16 result attached, or having it inferred without that context.
