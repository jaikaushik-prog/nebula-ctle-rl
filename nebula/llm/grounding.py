"""
llm/grounding.py — **the guard that makes an LLM safe to put in front of a
measurement project.**

THE RULE IT ENFORCES
---------------------
`CLAUDEwa.md` §8 rule 1: *"Never fabricate a number. Not in code comments, not
in reports, not in placeholder results... Every number in a deliverable must be
traceable to a simulation we actually ran."*

An LLM writing prose about a circuit will produce numbers. Some will be copied
from the facts it was given and some will be plausible inventions, and **the
two are indistinguishable to a reader.** That is exactly the failure mode this
whole repository is organised against, so the wrapper does not ask the model to
be careful -- it **checks**.

HOW
---
Every numeric literal in the generated text must match a value in the fact
dictionary, at the precision it was written to. "8.78 dB" matches a fact of
8.7763; "8.9 dB" does not. A number that matches nothing raises
`UngroundedNumber` and the text is **discarded**, not patched.

WHY THE RULE IS "EVERY LITERAL" AND NOT "EVERY LITERAL WITH A UNIT"
--------------------------------------------------------------------
Allowing bare integers -- "the three specs", "2 corners" -- would be a hole
wide enough to drive a fabricated count through, and counts are exactly what a
reader trusts without checking. So the prompt instructs the model to spell
small numbers as words, and this checker admits no exceptions. A guard with an
allowlist is a guard someone will widen.

WHAT IT DOES NOT DO
--------------------
It cannot catch a *wrong claim built from right numbers* -- "the noise margin
is comfortable" when it is not. That is what the offline template is for: the
deterministic path states only relations the code computed. The checker bounds
the damage an LLM can do; it does not make the LLM an authority.
"""

from __future__ import annotations

import math
import re
from typing import Iterable, Mapping

#: Any numeric literal: optional sign, digits, optional decimals, optional
#: exponent. Deliberately greedy about what counts as a number.
_NUMBER = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")

#: Written out so the model can say "three corners" without tripping the guard.
#: **Not an exemption** -- these are words, and the checker never sees a digit.
WORD_NUMBERS: tuple[str, ...] = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve",
)


class UngroundedNumber(ValueError):
    """A number appeared in generated text that no fact supports."""

    def __init__(self, literal: str, context: str, n_facts: int):
        self.literal = literal
        self.context = context
        super().__init__(
            f"the model wrote {literal!r} and no fact supports it "
            f"(checked {n_facts} facts). Context: ...{context}... "
            f"The text is DISCARDED rather than corrected -- a number that "
            f"cannot be traced to a run is exactly what CLAUDEwa rule 1 "
            f"forbids.")


def _decimals(literal: str) -> int:
    """How many decimal places the model chose to write."""
    if "e" in literal.lower():
        return -1                      # exponent form: compare as float
    _, _, frac = literal.partition(".")
    return len(frac)


def _matches(literal: str, value: float) -> bool:
    """Does `literal` state `value`, at the precision it was written to?

    Rounding to the WRITTEN precision is what lets a model say "8.78 dB" for a
    measured 8.7763 without being accused of inventing it, while "8.9 dB" --
    which is a different claim at that precision -- is refused.
    """
    try:
        lit = float(literal)
    except ValueError:                                      # pragma: no cover
        return False
    if not math.isfinite(value):
        return False
    d = _decimals(literal)
    if d < 0:
        return math.isclose(lit, value, rel_tol=1e-9, abs_tol=0.0)
    return round(float(value), d) == round(lit, d)


def fact_values(facts: Mapping[str, object]) -> list[float]:
    """Every numeric value a fact dictionary supports, flattened."""
    out: list[float] = []
    for v in facts.values():
        if isinstance(v, bool):
            continue                    # True is not the number 1
        if isinstance(v, (int, float)):
            out.append(float(v))
        elif isinstance(v, (list, tuple)):
            out.extend(float(x) for x in v
                       if isinstance(x, (int, float))
                       and not isinstance(x, bool))
    return out


def ungrounded(text: str, facts: Mapping[str, object]) -> list[tuple[str, str]]:
    """Every `(literal, context)` in `text` that no fact supports."""
    values = fact_values(facts)
    bad: list[tuple[str, str]] = []
    for m in _NUMBER.finditer(text):
        lit = m.group()
        if not any(_matches(lit, v) for v in values):
            lo, hi = max(0, m.start() - 40), min(len(text), m.end() + 40)
            bad.append((lit, text[lo:hi].replace("\n", " ")))
    return bad


def check(text: str, facts: Mapping[str, object]) -> str:
    """Return `text` unchanged, or raise on the first ungrounded number.

    **Raises rather than repairs.** Silently deleting or correcting a
    fabricated number would leave prose whose remaining claims were written
    around it, which is worse than no prose.
    """
    bad = ungrounded(text, facts)
    if bad:
        lit, ctx = bad[0]
        raise UngroundedNumber(lit, ctx, len(fact_values(facts)))
    return text


def prompt_rules() -> str:
    """The instructions handed to the model. Kept beside the checker so the
    two cannot drift -- a prompt that permits what the guard forbids produces
    a wrapper that always fails, and one that forbids less is a hole."""
    return (
        "HARD RULES ON NUMBERS:\n"
        "- Use ONLY numbers that appear in the FACTS block. Do not compute, "
        "round differently, average, convert units, or estimate.\n"
        "- Every digit you write is checked against the FACTS. A number that "
        "does not match one exactly, at the precision you write it, causes "
        "your whole answer to be DISCARDED.\n"
        "- If you need to say a small count, spell it as a word "
        f"({', '.join(WORD_NUMBERS[:5])}, ...). Do not write digits for "
        "counts.\n"
        "- If a fact you want is not in the FACTS block, say so in words "
        "instead of supplying a number.\n"
    )


__all__ = ["UngroundedNumber", "check", "ungrounded", "fact_values",
           "prompt_rules", "WORD_NUMBERS"]
