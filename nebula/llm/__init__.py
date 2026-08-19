"""
nebula/llm — **deliverable 2: LLM-based human interaction with a wrapper.**

    python -m nebula.llm "I need about 9 dB of peaking with the peak near 1.9 GHz"

`CLAUDEwa.md` §2 lists this as the bonus deliverable, and its objective in the
same section says **"with zero human intervention"** in the design. Those two
only coexist if the model stays outside the sizing loop, so it does:

    natural language  --spec_parse-->  a VALIDATED SpecTarget
                                            |
                                       nebula.design  (SPICE, unchanged)
                                            |
    prose  <--explain--  a finished result, EVERY NUMBER CHECKED

Three properties, each with a test that goes red without it:

* **The model cannot widen the spec.** Both parse paths end at the same
  `SpecTarget` constructor, which refuses anything outside S3's band. The
  validator is in the type, not in the prompt.
* **The model cannot invent a number.** `grounding.check` refuses any numeric
  literal no fact supports, and the text is DISCARDED rather than repaired.
* **The model is never required.** `anthropic` is not a dependency; every path
  has a deterministic offline fallback, so CI needs no key and a live demo
  needs no network.

**Naming rule, earned twice in one session:** no submodule may share a name
with something this file re-exports. `explain.py` holding a function called
`explain` meant `from nebula.llm import explain` silently bound the FUNCTION,
shadowing the module, and `explain.template` raised `AttributeError` from two
different call sites. The module is `explanation.py`; the function is
`explain`. `test_no_submodule_is_shadowed_by_a_reexport` pins it.
"""

from nebula.llm.explanation import explain, facts, template, verdicts
from nebula.llm.grounding import UngroundedNumber, check
from nebula.llm.spec_parse import ParsedRequest, SpecOutOfRange, parse_request

__all__ = ["parse_request", "ParsedRequest", "SpecOutOfRange",
           "explain", "facts", "template", "verdicts",
           "check", "UngroundedNumber"]
