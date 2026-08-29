# Proposal 002 — Designer-side adoption criteria for automated sizing

**Source:** Vikas Vijay (Analog Design Engineer, Cirrus Logic), "AI-Driven Automation of Analog
Circuit Sizing — A Designer's Perspective", 26 Oct 2025.

Note: an earlier draft of this brief attached the viksnewsletter.com URL to this article. That URL
is a different author (Vikram Sekar) and a different piece, covered in proposal 003. Do not cite
the two together.

**Status:** UNEVALUATED. See `EVAL_PROTOCOL.md`.

**Type warning — read this before evaluating.** This is a practitioner opinion piece, not a
method paper. It contains no algorithm, no equations beyond a generic weighted cost function, no
experiments, and no reproducible result. It cannot be "implemented" and should not be scored on
the adopt/prototype/skip scale used for method proposals. It is useful for exactly two things:
(a) a checklist of objections a real analog designer raises against a tool like ours, which can be
turned into tests or into slides; (b) one concrete research direction. Evaluate it on that basis.

---

## 1. The two challenges the author says a sizing tool must solve

**1.1 Layout parasitics.** Layout-dependent effects — STI stress, well-proximity, matching, RLC
parasitics — are argued to dominate at advanced nodes and high speed, so any tool that sizes on
schematic alone is producing numbers that move after layout. Putting layout in the optimisation
loop is expensive; the direction he points at is predicting parasitics with graph neural networks
instead of running a layout.

**1.2 Generalisation boundary.** Generating training data per circuit variant is prohibitive, so
the tool must handle "similar" blocks — but similarity is undefined. His examples: does adding
pull-up/pull-down switches to prevent floating nodes break the model? Do different compensation
schemes on the same OTA (output, Miller, Ahuja) each require retraining? His claim is that a
practical tool must state its own similarity boundary explicitly.

## 2. The four adoption criteria

1. **Scale.** Tools that work on small blocks and fail at subsystem level get abandoned; designers
   won't re-learn a tool twice. Build small, but design for the larger case.
2. **Shared training data.** Suggests a cross-company consortium holding simple analog IP blocks so
   vendors can train on a common base and companies fine-tune on their variants.
3. **ROI.** Licensing cost has to be paid for by faster cycles / fewer errors, not novelty.
4. **Consistency and trust.** Adoption follows several silicon revisions of predictable results.
   Unpredictable output sends designers back to manual methods.

His overall stance is human-in-the-loop assistance rather than full automation.

## 3. Where this touches our work — as questions, not conclusions

- Our tool sizes on schematic. Every published yield number in this repo is a schematic number.
  What is the honest statement of that limitation, and is there a cheap partial answer (e.g. the
  measured routing capacitance already folded into the cl range) that is short of full layout?
- We already have a similarity boundary but have never written it down: one topology, one PDK,
  a stated parameter box, a stated channel-loss range, a stated load range. Should that be an
  explicit deliverable rather than an implicit one?
- Criterion 4 (consistency) is closer to our abstract's automation-and-tunability framing than
  criterion 3 is. Whether our variance-across-repeats is measurable at all is an open question.

## 4. What this source does not support

It contains no evidence, no baseline, and no numbers. Nothing here should be cited as a result.
Cite it only as a designer's stated priorities, and only where a citation to an opinion is
appropriate — motivation slides, related-work framing, or the reviewer-objection checklist.
