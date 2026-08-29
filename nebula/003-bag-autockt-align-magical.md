# Proposal 003 — Four AMS automation frameworks: BAG, AutoCkt, ALIGN, MAGICAL

**Source:** Vikram Sekar, "Applications of AI/ML to Analog and Mixed Signal Circuit Design",
Vik's Newsletter, 8 Apr 2024.
https://www.viksnewsletter.com/p/ai-ml-for-automated-analog-circuit-design

**Status:** UNEVALUATED. See `EVAL_PROTOCOL.md`.

**Type warning.** This is a secondary source — a survey of four primary works, written for a
general engineering audience. Nothing in it is evidence. Its value is as a *map*: it tells you
which four tools exist and roughly what each does, so you can decide which primary source is worth
fetching. Every number below is second-hand and must be checked against the primary paper before
it appears in any deliverable. Evaluate the four tools, not the article.

Primary sources, in priority order for our project:

1. Settaluri, Haj-Ali, Huang, Hakhamaneshi, Nikolić, "AutoCkt: Deep Reinforcement Learning of
   Analog Circuit Designs", DATE 2020 / arXiv:2001.01808.
2. Dhar et al., "ALIGN: A System for Automating Analog Layout", arXiv:2008.10682.
3. Chang et al., "BAG2: A process-portable framework for generator-based AMS circuit design",
   CICC 2018.
4. Xu et al., "MAGICAL: Toward Fully Automated Analog IC Layout", ICCAD 2019.

---

## 1. AutoCkt — highest relevance, and it is already our named baseline

This is reference [17] of proposal 001. The fRL-AD paper's central quantitative claim is a
variance comparison *against* AutoCkt, and the mentor-supplied `nebula_ctle_rl` package is in the
same lineage (PPO, delta actions, spec-vector observation). So this is not a new idea to consider
adopting — it is the thing our work is implicitly positioned against, and we have never stated
that positioning.

Mechanism as described in the survey:

- Start each trajectory from the **centre of the design space** rather than a random point, and
  step until the simulated result meets the target. One completed walk is one trajectory.
- Train on a **set of randomly drawn target specifications** (the article says ~50), scoring each
  trajectory by how close it lands. Training ends when all targets are met past a score threshold.
- At deployment, a previously unseen target is served by the closest learned trajectory, giving a
  good starting point that needs far fewer subsequent iterations.
- Simulation data comes from BAG, so **layout parasitics are inside the training loop** rather
  than being a post-hoc correction.

Second-hand claims to verify against the primary paper: ~10x fewer iterations than a GA+ML
baseline; 40 LVS-passing designs for a 2-stage OTA with negative-gm load in under 3 days on one
CPU core.

Note the tension with proposal 001 that will need resolving: fRL-AD claims *lower variance* than
AutoCkt, while AutoCkt claims *fewer simulations* than its own baseline. These are different
axes. Neither is a claim about final design quality.

## 2. ALIGN — the only concrete answer to our schematic-only limitation

Netlist in, GDSII out. Flow as described: detect hierarchy in the netlist, abstract the PDK design
rules into a compact JSON form, generate parameterised primitive cells (differential pairs, current
mirrors) from those rules, then place and route the hierarchy under analog constraints.

The upstream repo ships a mock FinFET PDK, but a separate `ALIGN-pdk-sky130` repository exists and
its documented entry point is a single `schematic2layout.py` invocation, with a five-transistor OTA
as the worked example. Whether it runs on our netlist, in our environment, in the time available,
is unverified and is exactly what a spike would answer.

Why this matters here: every yield number in this repo is a schematic number. Proposal 002 §1.1
is the designer's objection to that, and this is the one tool in the set that could turn it from
a caveat into a measurement, even for a single design.

## 3. BAG / BAG2 — generator-based, probably out of scope

A designer writes a schematic template, marks which parameters are free, and writes both a
schematic generator and a layout generator against a Python API; the framework then iterates
template → layout → extraction → measurement → new parameters until specs are met. Reported to
have produced a time-interleaved SAR ADC and a SerDes front end in TSMC 16nm, then ported across
nodes and foundries.

The relevant weakness the survey names: BAG needs a decent initial design point and restarts from
scratch when the spec changes — which is the gap AutoCkt was built to fill.

## 4. MAGICAL — layout, with symmetry as the organising idea

Similar hierarchical netlist-to-layout goal. Distinguishing feature per the survey is explicit
symmetry handling: detecting sources tied together to form a virtual ground ("seed pattern
detection") so differential devices get matched, matching passives, then a post-pass looking for
symmetry it missed such as bias-circuit symmetry.

## 5. Calibration on scope

Final submission is 15 Sept. Whatever is picked from this brief has to be sized against that, and
the honest default for items 2–4 is a **time-boxed spike producing a yes/no on feasibility**, not
an integration. Item 1 is different — it is a positioning question and costs reading time, not
build time.

## 6. Framing content, usable but not citable as evidence

The survey's editorial line — automated analog layout matters more now because design rules are
more restrictive, analog content is growing, experienced designers are scarce, cycle times are
shrinking, and cross-node portability is a business requirement — is reasonable motivation
material. It is opinion. Cite the primary sources for anything load-bearing.
