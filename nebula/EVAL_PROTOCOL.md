# Evaluation protocol for external proposals

Purpose: decide whether an idea from outside the project is worth adding, without the evaluation
degenerating into "yes, great fit" — which is the default failure mode when you hand a model a
paper and your own codebase in the same breath.

Three bias controls, all of which have already earned their keep elsewhere in this project:

1. **Sealed first pass.** The evaluator forms a view from the brief and the code alone, before
   seeing any note about how it might fit our direction. Section 3 of each brief and this file's
   Stage 2 are withheld until Stage 1 is written to disk.
2. **Pre-registration.** Before any experiment runs, the falsification condition goes into
   `PREDICTIONS.md` with a number attached. An idea that cannot be given a falsification condition
   is not ready to prototype.
3. **Mandatory counterargument.** Every verdict ships with the strongest argument against itself.
   A verdict with a weak counterargument is treated as not yet evaluated.

Run one proposal per session, on a fresh context.

---

## Stage 1 — sealed assessment

Paste this. Substitute the proposal number.

> Read `docs/proposals/001-frl-ad-gmid-sequential.md`, sections 1 through 6 EXCEPT any section
> marked as touching on our work. Then read `CLAUDE.md` and `HANDOFF.md`. Then read only the
> source files you actually need to answer — name them before you open them.
>
> Do not implement anything. Do not modify code. Produce an assessment with these parts:
>
> 1. **Precondition audit.** For each precondition in §3 of the brief, state whether our project
>    satisfies it, violates it, or partially satisfies it, and cite the specific file, measurement
>    or gotcha number that decides it. Where you cannot decide from the repo, say so — do not fill
>    the gap by inference.
> 2. **Mechanism-by-mechanism verdict.** The brief lists the mechanism in separable pieces. Score
>    each piece independently. Do not let a strong piece carry a weak one.
> 3. **Blast radius.** For each piece you'd consider adopting: which files change, which frozen
>    interfaces move, which currently-passing tests would need to change meaning, and which
>    published numbers in the repo would have to be re-run before they could be quoted again.
> 4. **Transfer analysis.** The claimed gain was measured in the setting described in §4 of the
>    brief. State which specific differences between that setting and ours would attenuate or
>    invert the gain, and by what mechanism.
> 5. **Cheapest falsifying experiment.** For each piece worth prototyping, the smallest experiment
>    that could show it does NOT help here — with a pre-registered number, a runtime estimate, and
>    the condition under which you would abandon it.
> 6. **Verdict per piece:** adopt / prototype / skip / not-decidable-yet.
> 7. **Strongest argument against your own verdict**, for each piece, written as if by someone who
>    wants the opposite outcome and has read the same repo.
>
> Where the brief and the repo disagree on a fact, the repo wins and you say so explicitly.
> Write the result to `docs/proposals/001-frl-ad-gmid-sequential.eval.md`. Nothing else.

## Stage 2 — reveal and reconcile

Only after Stage 1 is committed.

> Now read §3 of `docs/proposals/002-designer-adoption-criteria.md` and the notes below, which are
> our team's own views and were deliberately withheld from you. Append a `## Stage 2` section to
> the eval file covering: where our view and yours agree, where they disagree, and — for each
> disagreement — which piece of evidence would settle it. Do not revise your Stage 1 verdicts in
> place. If a verdict changes, add it as a superseding entry with the reason, so the change is
> visible.

## Stage 3 — pre-register, then run

For each piece that came out of Stage 2 as `prototype`:

> Add an entry to `PREDICTIONS.md` for <piece>. State the metric, the current measured value, the
> value you predict after the change, and at least two conditions that would falsify it. Commit
> that before writing any implementation code. Then implement the smallest version that can be
> measured, run it, and report against the pre-registration including any prediction that missed.

## Anti-patterns to watch for in the output

- A verdict that never names a file or a number. That's a summary wearing a verdict's clothes.
- All pieces scored the same way. The pieces are independent; identical scores suggest the paper
  was evaluated as a unit.
- A counterargument shorter than the argument.
- Adoption justified by the source's reported gain rather than by a mechanism that exists here.
- Silence on preconditions the repo has already measured as violated.
