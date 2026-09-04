"""
Tests for `nebula/llm/` — deliverable 2's wrapper.

**None of these runs ngspice, and none of them calls Anthropic.** The client is
a stub. That is the point: `NEXT_STEPS.md` step 7 requires a deterministic
offline fallback so CI needs no key and a live demo needs no network.

Four are gates in CLAUDEwa.md §8 rule 10's sense:

  * `test_a_fabricated_number_cannot_pass_through` — step 7's own words: *"a
    test must prove that a fabricated value cannot pass through."*
  * `test_the_template_is_ungrounded_by_construction` — the fallback must
    survive its own checker, or the safe path is not safe.
  * `test_the_parse_validator_is_in_the_TYPE_not_the_prompt` — an LLM must not
    be able to widen the spec.
  * `test_the_model_is_never_in_the_sizing_loop` — the competition asks for
    zero human intervention in the DESIGN.
"""

from __future__ import annotations

import json

import pytest

from nebula.common.types import SPEC_F_PEAK_HZ_RANGE, SPEC_PEAKING_DB_RANGE
from nebula.llm import client as C
from nebula.llm import explanation as E
from nebula.llm import grounding as G
from nebula.llm import spec_parse as P


# ─────────────────────────────────────────────────────────────────────────────
# A stub Anthropic client
# ─────────────────────────────────────────────────────────────────────────────


class _Stub:
    """Returns whatever text it was constructed with, and records the call."""

    def __init__(self, text: str):
        self._text = text
        self.calls: list[dict] = []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)

        class _B:
            type = "text"
            text = self._text

        class _R:
            content = [_B()]

        _B.text = self._text
        return _R()


def _design(ok=True, verified=False, failed=0):
    d = {
        "request": {"peaking_db": 9.0, "f_peak_hz": 1.9e9, "f_peak_ghz": 1.9},
        "method": "library", "robust_search": False,
        "simulations": {"search": 0, "measure": 1, "total": 1},
        "nominal": {"ok": ok, "verdict": "valid" if ok else "invalid",
                    "reward": 8.9995, "feasible": True,
                    "worst_spec": "S3_f_peak",
                    "meas": {"g_dc_db": 1.8172, "peaking_db": 8.7763,
                             "f_peak_oct": -0.4, "nyq_boost_db": 8.7444,
                             "inoise_vrms": 1.633e-4, "power_w": 5.3825e-3,
                             "pair_margin_v": 0.6504, "tail_margin_v": 0.5081,
                             "_f_peak_ghz": 1.8996, "_noise_mv": 0.1633,
                             "_power_mw": 5.3825},
                    "params": {"w_in": 7.1469e-5, "l_in": 2.1757e-7,
                               "nf_in": 4, "i_bias": 2.8541e-3, "rs": 235.87,
                               "cs": 5.9858e-12, "rl": 257.42,
                               "cl": 3.2628e-14, "vcm_in": 1.5888}},
    }
    if verified:
        d["verification"] = {"n_points": 135, "n_corners": 45, "n_loads": 3,
                             "n_failed": failed,
                             "n_failed_outside_the_screen": failed,
                             "all_points_pass": failed == 0,
                             "worst_reward": 8.0210}
    return d


# ─────────────────────────────────────────────────────────────────────────────
# The grounding guard
# ─────────────────────────────────────────────────────────────────────────────


def test_a_fabricated_number_cannot_pass_through():
    """**The gate `NEXT_STEPS.md` step 7 asks for in those words.**

    An LLM writing about a circuit produces numbers, some copied and some
    invented, and a reader cannot tell them apart. So the wrapper checks rather
    than trusting.
    """
    facts = {"peaking_db": 8.7763, "power_mw": 5.3825}

    # copied, at full precision and at a sensible rounding: allowed
    assert G.check("peaks at 8.7763 dB", facts)
    assert G.check("peaks at 8.78 dB", facts)
    assert G.check("draws 5.4 mW", facts)

    # invented: refused, and the text is DISCARDED rather than repaired
    for bad in ("peaks at 8.9 dB", "draws 6 mW", "the gain is 12.5 dB",
                "it uses 5.3826 mW"):
        with pytest.raises(G.UngroundedNumber):
            G.check(bad, facts)


def test_bare_integers_are_not_exempt():
    """An allowlist for small integers would be a hole wide enough to drive a
    fabricated COUNT through -- and counts are what a reader trusts without
    checking. The prompt tells the model to spell them as words instead."""
    facts = {"peaking_db": 8.7763}
    with pytest.raises(G.UngroundedNumber):
        G.check("checked at 45 corners", facts)
    with pytest.raises(G.UngroundedNumber):
        G.check("there are 3 specs", facts)
    # ... and the words go through untouched
    assert G.check("three specifications were checked", facts)
    assert "three" in G.WORD_NUMBERS


def test_booleans_do_not_ground_the_number_one():
    """`True` in a fact dict must not license the literal 1 -- otherwise every
    flag silently grounds a count."""
    with pytest.raises(G.UngroundedNumber):
        G.check("1 corner failed", {"feasible": True, "verified": False})


def test_the_error_names_the_literal_and_shows_where():
    facts = {"peaking_db": 8.7763}
    with pytest.raises(G.UngroundedNumber) as e:
        G.check("the stage peaks at 9.9 dB which is plenty", facts)
    assert e.value.literal == "9.9"
    assert "peaks at 9.9 dB" in e.value.context
    assert "DISCARDED" in str(e.value)


def test_the_prompt_rules_and_the_checker_cannot_drift():
    """A prompt that permits what the guard forbids yields a wrapper that
    always fails; one that forbids less is a hole. They live together."""
    r = G.prompt_rules()
    assert "ONLY numbers that appear in the FACTS" in r
    assert "DISCARDED" in r
    assert "spell it as a word" in r


# ─────────────────────────────────────────────────────────────────────────────
# The explanation
# ─────────────────────────────────────────────────────────────────────────────


def test_the_template_is_ungrounded_by_construction():
    """**The safe path must survive its own checker**, or falling back to it
    proves nothing. Every number in it is substituted from `facts()`."""
    for d in (_design(), _design(verified=True), _design(verified=True,
                                                         failed=8)):
        text = E.template(d)
        assert G.check(text, E.facts(d)) is text


def test_an_ungrounded_llm_answer_falls_back_to_the_template():
    d = _design()
    text, source = E.explain(d, use_llm=True,
                             client=_Stub("It peaks at 9.9 dB, comfortably."))
    assert source == "template"
    assert "discarded" in text
    assert "8.776" in text, "the deterministic wording must still be there"


def test_a_grounded_llm_answer_is_kept():
    d = _design()
    good = ("The stage peaks at 8.7763 dB near 1.8996 GHz and draws "
            "5.3825 mW.")
    text, source = E.explain(d, use_llm=True, client=_Stub(good))
    assert source == "llm" and text == good


def test_an_api_failure_falls_back_rather_than_raising():
    class _Boom:
        messages = property(lambda self: (_ for _ in ()).throw(
            RuntimeError("network")))

    text, source = E.explain(_design(), use_llm=True, client=_Boom())
    assert source == "template" and "unavailable" in text


def test_the_verdicts_carry_no_numbers_at_all():
    """The model is told the judgements so it never re-derives them; if a
    number leaked into that block the model could quote it as measured."""
    w = E.verdicts(_design(verified=True))
    for k, v in w.items():
        assert not isinstance(v, (int, float)) or isinstance(v, bool), k


def test_the_facts_carry_the_units_they_will_be_quoted_in():
    """Converted once, here -- so the model never multiplies and the checker
    compares literals directly."""
    f = E.facts(_design())
    assert f["noise_mv_rms"] == pytest.approx(0.1633)
    assert f["power_mw"] == pytest.approx(5.3825)
    assert f["w_in_um"] == pytest.approx(71.469, rel=1e-4)
    assert f["l_in_nm"] == pytest.approx(217.57, rel=1e-4)


def test_the_explanation_says_when_corners_were_NOT_checked():
    text = E.template(_design(verified=False))
    assert "NOT been verified across corners" in text


# ─────────────────────────────────────────────────────────────────────────────
# The parser
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("text,db,ghz", [
    ("I need about 9 dB of peaking with the peak near 1.9 GHz", 9.0, 1.9),
    ("peak around 2 GHz with 6 dB of boost", 6.0, 2.0),
    ("1900 MHz, 10dB", 10.0, 1.9),
    ("give me 3.5 decibels at 1.25GHz", 3.5, 1.25),
])
def test_the_offline_parser_handles_what_a_designer_types(text, db, ghz):
    r = P.parse_offline(text)
    assert r.target.peaking_db == pytest.approx(db)
    assert r.target.f_peak_hz == pytest.approx(ghz * 1e9)
    assert r.source == "regex"


def test_a_missing_field_is_defaulted_LOUDLY():
    r = P.parse_offline("just give me something")
    assert r.notes and any("assumed" in n for n in r.notes)


def test_the_parse_validator_is_in_the_TYPE_not_the_prompt(monkeypatch):
    """**The whole safety argument for putting a model in front of this.**

    Both paths end at `SpecTarget`, which refuses anything outside S3. So the
    worst an LLM misreading can do is produce a DIFFERENT LEGAL request -- it
    can never widen the spec.
    """
    lo_db, hi_db = SPEC_PEAKING_DB_RANGE
    with pytest.raises(P.SpecOutOfRange):
        P.parse_offline(f"{hi_db + 8:g} dB at 1.9 GHz")
    with pytest.raises(P.SpecOutOfRange):
        P.parse_offline("9 dB at 6 GHz")

    # and the LLM path is refused by the SAME validator, not by the prompt
    stub = _Stub(json.dumps({"peaking_db": hi_db + 8, "f_peak_hz": 1.9e9,
                             "peaking_stated": True, "f_peak_stated": True}))
    with pytest.raises(P.SpecOutOfRange):
        P.parse_llm("twenty dB please", client=stub)


def test_an_out_of_range_request_is_NOT_retried_offline():
    """Quietly trying another parser until one succeeds is how a demo answers
    a question nobody asked. Only infrastructure failures fall back."""
    stub = _Stub(json.dumps({"peaking_db": 40.0, "f_peak_hz": 1.9e9,
                             "peaking_stated": True, "f_peak_stated": True}))
    with pytest.raises(P.SpecOutOfRange):
        P.parse_request("40 dB", use_llm=True, client=stub)


def test_an_unavailable_llm_falls_back_and_SAYS_so(monkeypatch):
    monkeypatch.setattr(C, "get_client", lambda client=None: (_ for _ in ())
                        .throw(C.LlmUnavailable("no package")))
    r = P.parse_request("9 dB at 1.9 GHz", use_llm=True)
    assert r.source == "regex"
    assert any("unavailable" in n for n in r.notes)
    assert r.target.peaking_db == pytest.approx(9.0)


def test_the_llm_path_asks_for_HERTZ_and_says_not_to_clamp():
    """A model that helpfully moves an illegal number into range would hide
    the one thing the caller must be allowed to refuse."""
    assert "HERTZ" in P._SYSTEM
    assert "Never silently move a number into range" in P._SYSTEM
    assert P._SCHEMA["additionalProperties"] is False
    assert set(P._SCHEMA["required"]) == {"peaking_db", "f_peak_hz",
                                          "peaking_stated", "f_peak_stated"}


# ─────────────────────────────────────────────────────────────────────────────
# The boundary
# ─────────────────────────────────────────────────────────────────────────────


def test_the_model_is_never_in_the_sizing_loop():
    """`CLAUDEwa.md` §2's objective is *zero human intervention* in the DESIGN.
    That only coexists with an LLM wrapper if the model stays outside the
    optimiser -- so nothing in `nebula/llm/` may import the search, the
    evaluator, or the reward."""
    import inspect

    from nebula.llm import __main__ as M

    for mod in (P, E, G, C):
        src = inspect.getsource(mod)
        for forbidden in ("reward_v1", "evaluator", "baselines", "sizing_from_u",
                          "METHODS", "Objective"):
            assert forbidden not in src, (
                f"{mod.__name__} references {forbidden}: the model must not be "
                f"able to touch the sizing loop")
    # the CLI may call the designer, but only through its public entry point
    cli = inspect.getsource(M)
    assert "from nebula.design import" in cli
    assert "design, prepare_output_deck, report, write_outputs" in cli
    assert "METHODS" not in cli and "Objective" not in cli


def test_anthropic_is_not_a_dependency():
    """CI must need no key and a live demo no network."""
    assert C.available() in (True, False)          # never raises
    text, source = E.explain(_design(), use_llm=False)
    assert source == "template" and text
    assert P.parse_request("9 dB at 1.9 GHz").source == "regex"


def test_the_model_id_is_current():
    assert C.MODEL == "claude-opus-5"


def test_no_submodule_is_shadowed_by_a_reexport():
    """**Earned twice in one session, from two different call sites.**

    `explain.py` held a function called `explain`, and the package re-exported
    it -- so `from nebula.llm import explain` silently bound the FUNCTION,
    shadowing the module, and `explain.template(...)` raised `AttributeError`.
    The module is now `explanation.py`. This pins the rule generally rather
    than the one instance: nothing this package re-exports may share a name
    with one of its submodules.
    """
    import pkgutil

    import nebula.llm as pkg

    submodules = {m.name for m in pkgutil.iter_modules(pkg.__path__)}
    reexports = set(pkg.__all__)
    clash = submodules & reexports
    assert not clash, (
        f"{sorted(clash)} is both a submodule and a re-export; the attribute "
        f"shadows the module and `from nebula.llm import {sorted(clash)[0]}` "
        f"binds the wrong object")
    # ... and every name __all__ promises actually exists
    for name in reexports:
        assert hasattr(pkg, name), f"__all__ names {name} and it is missing"
