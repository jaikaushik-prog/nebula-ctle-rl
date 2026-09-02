"""
Tests for `nebula/design.py` — the deliverable's front door.

**None of these runs ngspice.** What is under test is the CLI's honesty: that
it refuses a spec outside S3, that it says the peaking request is a band rather
than a target, and that it never reports a nominal design as corner-verified.

Three are gates in CLAUDEwa.md §8 rule 10's sense:

  * `test_the_report_never_calls_a_nominal_design_corner_verified` — the single
    most damaging thing a demo could imply. `G4_RESULTS.md` measured the cost:
    the best design at nominal failed 75 of 135 corner points.
  * `test_the_peaking_request_is_labelled_as_a_BAND_on_every_run` — the reward
    cannot see it, and a tool that quietly optimised a number its objective
    ignores would be advertising.
  * `test_a_target_outside_S3_is_refused_rather_than_clipped`
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from nebula import design as D
from nebula.common.types import SPEC_F_PEAK_HZ_RANGE, SPEC_PEAKING_DB_RANGE
from nebula.rl import reward_v1 as R
from nebula.rl.contract import ACTION_SPACE, N_ACTIONS


def _meas(peaking=7.5, f_oct=-0.5):
    return {"g_dc_db": 3.0, "peaking_db": peaking, "f_peak_oct": f_oct,
            "nyq_boost_db": 4.0, "inoise_vrms": 3.0e-4, "power_w": 5.0e-3,
            "pair_margin_v": 0.25, "tail_margin_v": 0.05}


def _fake_nominal(feasible=True, worst_spec="S3_f_peak"):
    return {"ok": True, "verdict": "valid", "meas": D._derived(_meas()),
            "params": {"w_in": 8.0e-5, "l_in": 2.2e-7, "nf_in": 4,
                       "i_bias": 1.1e-3, "rs": 430.0, "cs": 3.2e-12,
                       "rl": 240.0, "cl": 3.26e-14, "vcm_in": 1.58},
            "reward": 8.99, "feasible": feasible, "worst_spec": worst_spec,
            "design_id": "stub"}


# ─────────────────────────────────────────────────────────────────────────────


def test_a_target_outside_S3_is_refused_rather_than_clipped():
    lo_db, hi_db = SPEC_PEAKING_DB_RANGE
    lo_hz, hi_hz = SPEC_F_PEAK_HZ_RANGE
    with pytest.raises(ValueError, match="outside S3"):
        D.design(hi_db + 1.0, 1.9e9)
    with pytest.raises(ValueError, match="outside S3"):
        D.design((lo_db + hi_db) / 2, hi_hz * 2)
    # ... and the CLI turns that into an exit code, not a traceback
    assert D.main(["--peaking", str(hi_db + 1), "--f-peak", "1.9e9"]) == 2


def test_ghz_and_hz_are_both_accepted_and_mean_the_same_thing(monkeypatch):
    seen = {}

    def _fake_design(peaking_db, f_peak_hz, **kw):
        seen["f"] = f_peak_hz
        return {"request": {"peaking_db": peaking_db, "f_peak_hz": f_peak_hz,
                            "f_peak_ghz": f_peak_hz / 1e9},
                "method": "library", "robust_search": False,
                "nominal": {"ok": False, "verdict": "x", "reason": "stub"},
                "simulations": {"total": 0}, "wall_s": 0.0,
                "peaking_is_a_band_not_a_target": "..."}

    monkeypatch.setattr(D, "design", _fake_design)
    D.main(["--peaking", "9", "--f-peak", "1.9"])
    a = seen["f"]
    D.main(["--peaking", "9", "--f-peak", "1.9e9"])
    assert a == seen["f"] == pytest.approx(1.9e9), (
        "a GHz-shaped number and a Hz-shaped number must land on one target")


def test_the_peaking_request_is_labelled_as_a_BAND_on_every_run(monkeypatch):
    """**The gate, and it was pinning a claim that had gone stale.**

    This test used to assert the note said *"reward_v1 deliberately ignores
    target_peaking_db"*. That was true when it was written and **false since
    decision D6**, which created `S3_peaking_match` and `V6_SPECS`. The note,
    printed on every run, kept saying it -- and `SCOPE_BOUNDARY.md` §3 built
    the "the spec manifold is 1-D" argument on top of it.

    What is actually true is a property of the SPEC SET, not of `reward_v1`:
    `V1_SPECS` has no request row, `V6_SPECS` does. So the gate is now that the
    note names the spec set, and says which path scores which.
    """
    monkeypatch.setattr(D, "solve_library",
                        lambda t, tb=True: {"u": [0.5] * N_ACTIONS,
                                            "reward": 8.99, "sims": 0,
                                            "n_candidates": 10,
                                            "n_tied_at_best": 1,
                                            "design_id": "stub"})
    monkeypatch.setattr(D, "measure", lambda *a, **k: _fake_nominal())
    d = D.design(9.0, 1.9e9, method="library")
    note = d["peaking_is_a_band_not_a_target"]
    assert "TIE-BREAK" in note
    assert "V1_SPECS" in note, "the note must name the spec set it is about"
    assert "V5/V6_SPECS do score the request" in note, (
        "a reader must not be left believing reward_v1 cannot see a request")
    assert "ignores target_peaking_db" not in note, (
        "the pre-D6 claim must not come back")
    # and it must survive into the human-readable report, not only the JSON
    assert "TIE-BREAK" in D.report(d)


def test_the_report_never_calls_a_nominal_design_corner_verified(monkeypatch):
    """**The most damaging thing a demo could imply.** Without `--robust` the
    search saw one corner. `G4_RESULTS.md` measured the cost: the strongest
    design at nominal failed **75 of 135** corner points."""
    monkeypatch.setattr(D, "solve_library",
                        lambda t, tb=True: {"u": [0.5] * N_ACTIONS,
                                            "reward": 8.99, "sims": 0,
                                            "n_candidates": 10,
                                            "n_tied_at_best": 1,
                                            "design_id": "stub"})
    monkeypatch.setattr(D, "measure", lambda *a, **k: _fake_nominal())
    # `method="library"` explicitly: this test is about the NOMINAL path,
    # and since session 31 the default is `auto`, which screens four
    # corner/load points and would legitimately not carry this warning.
    text = D.report(D.design(9.0, 1.9e9, method="library"))
    assert "NOT VERIFIED AT CORNERS" in text
    assert "75 of 135" in text
    # the real property: there is no POSITIVE claim of corner verification.
    # Every occurrence of "verified" must be negated -- the METHOD line
    # legitimately reads "NOT verified at corners", which is the point.
    low = text.lower()
    assert "corner verification" not in low and "all points pass" not in low
    i = 0
    while (i := low.find("verified", i)) != -1:
        assert low[max(0, i - 4):i] == "not ", (
            f"an un-negated 'verified' at offset {i}: "
            f"{text[max(0, i - 40):i + 30]!r}")
        i += 1


def test_the_peaking_tiebreak_only_breaks_TIES(monkeypatch):
    """It reorders designs that are already equal on the objective. If it ever
    started overriding the reward, the tool would be optimising a different
    problem from the one every published number was measured on."""
    import nebula.experiments.spec_pool as SP

    class _Pool:
        u = np.tile(np.linspace(0.1, 0.9, N_ACTIONS), (3, 1))
        meas = ({"peaking_db": 4.0}, {"peaking_db": 11.0}, {"peaking_db": 9.1})
        design_id = ("a", "b", "c")

        def __len__(self):
            return 3

    monkeypatch.setattr(SP, "load_pool", lambda *a, **k: _Pool())
    # b and c tie at the top; a is strictly worse
    monkeypatch.setattr(SP, "score_pool",
                        lambda pool, t: np.array([8.0, 8.9995, 8.9995]))
    t = D.SpecTarget(peaking_db=9.0, f_peak_hz=1.9e9)
    assert D.solve_library(t)["design_id"] == "c", "the tie-break lost"
    assert D.solve_library(t, peaking_tiebreak=False)["design_id"] == "b"

    # and when there is NO tie it must not override the objective
    monkeypatch.setattr(SP, "score_pool",
                        lambda pool, t: np.array([8.0, 8.9995, 8.5]))
    assert D.solve_library(t)["design_id"] == "b", (
        "the tie-break overrode a strictly better design")


def test_the_library_path_costs_zero_simulations(monkeypatch):
    import nebula.experiments.spec_pool as SP

    class _Pool:
        u = np.full((2, N_ACTIONS), 0.5)
        meas = ({"peaking_db": 7.0}, {"peaking_db": 8.0})
        design_id = ("a", "b")

        def __len__(self):
            return 2

    monkeypatch.setattr(SP, "load_pool", lambda *a, **k: _Pool())
    monkeypatch.setattr(SP, "score_pool", lambda pool, t: np.array([8.0, 8.9]))
    out = D.solve_library(D.SpecTarget(peaking_db=8.0, f_peak_hz=1.9e9))
    assert out["sims"] == 0


def test_every_reported_spec_row_names_its_requirement():
    """A measured number printed without the limit it is measured against is
    not a spec table."""
    for label, key, unit, req in D.SPEC_ROWS:
        assert label.strip() and key and unit and req
    keys = {k for _, k, _, _ in D.SPEC_ROWS}
    m = D._derived(_meas())
    assert keys <= set(m), f"the report asks for {keys - set(m)}"
    # the three S3 rows and both saturation margins must be present
    assert {"peaking_db", "_f_peak_ghz", "nyq_boost_db"} <= keys
    assert {"pair_margin_v", "tail_margin_v"} <= keys


def test_the_default_method_is_not_RL_and_the_choices_say_why():
    """CLAUDEwa §7: *"If BO matches RL, say so. That is a finding, not a
    loss."* The default is the measured-best answer, and `--help` states what
    PPO was measured to be rather than leaving a reader to assume."""
    import argparse

    p = [a for a in D.main.__doc__ or ""]          # main has no docstring; use the parser
    parser_help = D.__doc__
    assert "default method is not RL" in parser_help
    assert "indistinguishable from uniform random search" in parser_help


# ─────────────────────────────────────────────────────────────────────────────
# SESSION 31 — the default stopped being a question put to the operator.
#
# The brief says "with zero human intervention". A tool whose first prompt is
# "which of seven search methods would you like?" has a human in the loop at
# the moment a judge watches it run. These tests are about that sentence.
# ─────────────────────────────────────────────────────────────────────────────


def test_the_default_is_AUTO_in_both_the_API_and_the_CLI():
    """**One default, not two.** A CLI that defaults to `auto` while
    `design()` defaults to `library` would mean the demo and the library user
    run different pipelines, which is G32's shape of defect."""
    import inspect

    assert inspect.signature(D.design).parameters["method"].default == "auto"
    with pytest.raises(SystemExit):
        D.main([])                                   # no spec, no default run
    # the parser's own default, read from the parser rather than assumed
    text = _help_text()
    assert "--method" in text
    assert "auto" in text


def _help_text() -> str:
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.suppress(SystemExit), contextlib.redirect_stdout(buf):
        D.main(["--help"])
    return buf.getvalue()


def test_auto_is_documented_as_ESCALATION_not_as_a_seventh_method():
    """The help text must say what `auto` does, or the operator will still
    reach for a named method out of habit.

    **Asserted on the ESCALATION, not on one phrase.** Row 4y changed the first
    proposer from retrieval to the closed-form solve, and the old assertion
    (`"retrieval proposes"`) went red for the right reason -- the help text had
    become inaccurate. The guard is that every stage the tool escalates through
    is named and that the operator is told they need not choose, so it is
    written that way rather than pinned to today's wording.
    """
    # **Whitespace-normalised.** argparse re-wraps help text, so a phrase can
    # break across lines and a raw substring check goes red for a formatting
    # reason rather than a content one -- which it did, once.
    text = " ".join(_help_text().split())
    for stage in ("SOLVED", "retrieval", "screen", "search"):
        assert stage in text, f"the help text does not name the {stage!r} stage"
    assert "no human picks a strategy" in text


def test_auto_CALLS_the_measured_hybrid_rather_than_reimplementing_it():
    """Rule 9: one definition. The delivered tool and the sweep that measured
    it (entry 40) must be the same code path, or the quoted 8-of-16 coverage
    describes something the front door does not do.

    Checked at the source rather than by running, because running it costs
    SPICE and the property is structural.
    """
    import inspect

    src = inspect.getsource(D.solve_auto)
    assert "propose_then_search" in src
    assert "AdaptiveScreen" in src
    assert "EDGE4_MANDATED" in src


def test_auto_reads_the_library_to_the_MEASURED_optimum_depth():
    """k=5, from entry 32's `accepted_at_k = [1,4,5,5,6,6,6,6]` -- the same
    acceptance as k=8 for 120 fewer decks. Not a round number someone liked."""
    assert D.AUTO_K == 5


def test_auto_is_reported_as_corner_SCREENED_but_not_corner_VERIFIED(monkeypatch):
    """The two things it must not be confused with.

    `auto` screens four corner/load points before delivering, so calling it a
    nominal search understates it. It does NOT run the 45-corner checklist, so
    calling it verified overstates it. Both errors are one word wide.
    """
    monkeypatch.setattr(D, "solve_auto", lambda t, b, s, k=5: {
        "u": [0.5] * N_ACTIONS, "reward": 8.99, "sims": 12,
        "n_candidates": 5, "n_tied_at_best": 1, "design_id": "stub",
        "which_path": "proposal", "proposal_rank": 2,
        "n_sims_proposal": 12, "n_sims_search": 0,
        "screened_on": ["a", "b", "c", "d"]})
    monkeypatch.setattr(D, "measure", lambda *a, **k: _fake_nominal())
    d = D.design(9.0, 1.9e9, method="auto")
    assert d["robust_search"] is True
    text = D.report(d)
    assert "no strategy was chosen by a human" in text
    assert "accepted at rank 2 of 5" in text
    assert "screened on 4 corner/load points" in text
    # **Screened is not verified, and the default path must SAY so.**
    # `auto` sets `robust_search`, so the old "NOT VERIFIED AT CORNERS" branch
    # no longer fires for it -- without its own branch the default run would
    # print nothing at all about the mandated 45, which is the loudest
    # possible silence in this whole report.
    assert "NOT VERIFIED" in text
    assert "mandated 45" in text
    assert "--verify" in text


def test_auto_says_when_the_PROPOSAL_FAILED_and_the_search_answered(monkeypatch):
    """A framework that hid the escalation would be advertising, not
    reporting. The fallback is the honest half of the cost claim."""
    monkeypatch.setattr(D, "solve_auto", lambda t, b, s, k=5: {
        "u": [0.5] * N_ACTIONS, "reward": 8.5, "sims": 604,
        "n_candidates": 5, "n_tied_at_best": 1, "design_id": "stub",
        "which_path": "search", "proposal_rank": None,
        "n_sims_proposal": 20, "n_sims_search": 584,
        "screened_on": ["a", "b", "c", "d"]})
    monkeypatch.setattr(D, "measure", lambda *a, **k: _fake_nominal())
    text = D.report(D.design(9.0, 1.9e9, method="auto"))
    assert "no retrieved candidate passed the screen" in text


def test_the_word_FEASIBLE_states_which_rows_and_which_corner(monkeypatch):
    """**The demo's most misreadable line.** `measure()` scores `reward_v1`'s
    default `V1_SPECS`: seven device rows, at TT only. A reader who takes
    `feasible=True` for "meets the specification" is reading S4, S7 and S8 --
    linearity, area and the eye -- as passing when they were never measured
    on that path."""
    monkeypatch.setattr(D, "solve_library",
                        lambda t, tb=True: {"u": [0.5] * N_ACTIONS,
                                            "reward": 8.99, "sims": 0,
                                            "n_candidates": 10,
                                            "n_tied_at_best": 1,
                                            "design_id": "stub"})
    monkeypatch.setattr(D, "measure", lambda *a, **k: _fake_nominal())
    text = D.report(D.design(9.0, 1.9e9, method="library"))
    assert "feasible=" in text
    assert f"{len(R.V1_SPECS)} device rows at TT" in text
    assert "S4" in text and "S7" in text and "S8" in text
    assert "--verify" in text


def test_provenance_answers_who_chose_the_ranges_without_a_spec():
    """`--provenance` is a question about the tool, not a design request, so
    it must not demand a spec it will not use."""
    text = D.provenance_report()
    for dim in ACTION_SPACE:
        assert dim.name in text
        assert dim.provenance.split(":")[0] in text
    assert "REFUSES a bound with" in text
    assert "3,402,000" in text, "the sweep it is being compared against"


def test_an_unjustified_BOX_EDGE_cannot_be_committed():
    """The provenance report is only worth printing because the type enforces
    it. Asserted here so a future edit that relaxes `ActionDim` fails a test
    that explains why it mattered."""
    from nebula.rl.contract import ActionDim

    with pytest.raises(ValueError, match="provenance"):
        ActionDim("bogus", 1.0, 2.0, False, "V", "   ")
