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


def test_cli_exposes_the_shielded_RL_product_path():
    text = " ".join(_help_text().split())
    assert "rl-hybrid" in text
    assert "--channel-loss" in text
    assert "safety shield" in text.lower()
    assert "automatically checks all seven" in text.lower()
    assert "diagnostic override" in text.lower()


def test_rl_hybrid_default_needs_only_the_two_problem_statement_inputs(
        monkeypatch):
    """Channel loss is swept internally unless a diagnostic override is set."""
    import inspect

    assert inspect.signature(D.design).parameters["channel_loss_db"].default is None
    seen = {}
    stub = {
        "u": [0.5] * N_ACTIONS, "reward": None, "sims": 0,
        "n_candidates": 512, "n_tied_at_best": 1, "design_id": "bank",
        "atten_code": 3, "atten_max_x": 2.0, "bank_code": 4,
        "which_path": "rl-bank", "_nominal": _fake_nominal(),
        "_verification": {"n_corners": 45, "n_channel_losses": 7,
                          "n_points": 315, "n_pass": 315, "n_failed": 0,
                          "all_points_pass": True,
                          "n_mandated_points": 45,
                          "n_mandated_pass": 45,
                          "mandated_all_pass": True},
        "policy_seed": 2026090500,
        "channel_losses_db": [3.0, 4.5, 6.0, 7.5, 9.0, 10.5, 12.0],
        "representative_channel_loss_db": 7.5,
        "rl_proposals": 100, "shield_fallbacks": 4,
        "table_rows_checked": 2048, "offline_spice_rows": 23040,
    }

    def fake_solve(target, loss):
        seen["loss"] = loss
        return dict(stub)

    monkeypatch.setattr(D, "solve_rl_hybrid", fake_solve)
    out = D.design(9.0, 1.9e9, method="rl-hybrid")
    assert seen["loss"] is None
    assert out["verification"]["n_points"] == 315
    text = D.report(out)
    assert "7 channel losses x 45 PVT corners = 315" in text
    assert "315 / 315" in text


def test_cli_reports_an_uncovered_request_without_a_traceback(
        monkeypatch, capsys):
    """A safe refusal is a product outcome, not an internal crash."""
    monkeypatch.setattr(
        D, "design", lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("no compliant setting at 7 of 315 conditions")))
    rc = D.main(["--method", "rl-hybrid", "--peaking", "12",
                 "--f-peak", "1.25"])
    assert rc == 2
    assert "no compliant setting" in capsys.readouterr().err


def test_rl_hybrid_dispatch_does_not_remeasure_without_the_attenuator(monkeypatch):
    """Its table row includes the PMOS attenuator; plain ``measure(u)`` does not."""
    stub = {
        "u": [0.5] * N_ACTIONS, "reward": None, "sims": 0,
        "n_candidates": 512, "n_tied_at_best": 1, "design_id": "bank",
        "atten_code": 3, "atten_max_x": 2.0, "bank_code": 4,
        "which_path": "rl-bank", "_nominal": _fake_nominal(),
        "_verification": {"n_corners": 45, "n_points": 45,
                          "n_pass": 45, "n_failed": 0,
                          "all_points_pass": True,
                          "n_channel_losses": 1,
                          "n_mandated_points": 45,
                          "n_mandated_pass": 45,
                          "mandated_all_pass": True},
        "policy_seed": 2026090500,
        "channel_loss_mode": "diagnostic-override",
        "channel_losses_db": [7.5],
        "representative_channel_loss_db": 7.5,
        "rl_proposals": 100, "shield_fallbacks": 4,
        "table_rows_checked": 2048,
    }
    monkeypatch.setattr(D, "solve_rl_hybrid", lambda target, loss: dict(stub))
    monkeypatch.setattr(D, "measure", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("rl-hybrid must use its attenuator-aware measured row")))
    out = D.design(9.0, 1.9e9, method="rl-hybrid", channel_loss_db=7.5)
    assert out["verification"]["all_points_pass"]
    assert out["nominal"]["design_id"] == "stub"
    assert out["simulations"]["total"] == 0
    report = D.report(out)
    assert "RL PROPOSER" in report
    assert "45 / 45" in report
    assert "classical bank fallback" in report


def test_netlist_forwards_the_exact_attenuator_range(monkeypatch):
    seen = {}

    class _Point:
        netlist = "deck"

    monkeypatch.setattr(D, "build_point", lambda sizing, **kw: (object(), None))

    def run(point, **kwargs):
        seen.update(kwargs)
        return _Point()

    monkeypatch.setattr(D, "run_point", run)
    deck = D.netlist_for([0.5] * N_ACTIONS, 32.6e-15,
                         atten_code=7, atten_max_x=2.3)
    assert deck == "deck"
    assert seen["atten_code"] == 7
    assert seen["atten_max_x"] == 2.3
    assert seen["vid_max"] > 0.8


def test_rl_hybrid_schematic_panel_cannot_look_like_one_fixed_code_passed():
    panel = D._schematic_panel({
        "method": "rl-hybrid",
        "search": {"atten_code": 1, "bank_code": 40,
                   "policy_seed": 2026090500,
                   "channel_loss_mode": "automatic-family",
                   "channel_losses_db": [3.0, 4.5, 6.0, 7.5, 9.0, 10.5,
                                         12.0]},
        "nominal": _fake_nominal(),
        "verification": {"n_points": 315, "n_failed": 0,
                         "n_corners": 45, "n_channel_losses": 7,
                         "n_mandated_points": 45},
        "simulations": {"total": 0},
    })
    assert panel["PDK"] == "SKY130 nfet+pfet"
    assert panel["TT tuning code"] == "A1 / B40"
    assert panel["PVT mode"] == "adaptive code map"
    assert panel["PVT per channel"] == "45/45 PASS"
    assert panel["all conditions"] == "315/315 PASS"
    assert panel["channel sweep"] == "3-12 dB (7 points)"


def test_rl_hybrid_report_counts_the_extra_deck_used_by_output_export(monkeypatch):
    stub = {
        "u": [0.5] * N_ACTIONS, "reward": None, "sims": 0,
        "n_candidates": 512, "n_tied_at_best": 1, "design_id": "bank",
        "atten_code": 1, "atten_max_x": 2.3, "bank_code": 40,
        "which_path": "rl-bank", "_nominal": _fake_nominal(),
        "_verification": {"n_corners": 45, "n_points": 45,
                          "n_pass": 45, "n_failed": 0,
                          "all_points_pass": True,
                          "n_channel_losses": 1,
                          "n_mandated_points": 45,
                          "n_mandated_pass": 45,
                          "mandated_all_pass": True},
        "policy_seed": 2026090500,
        "channel_loss_mode": "diagnostic-override",
        "channel_losses_db": [7.5],
        "representative_channel_loss_db": 7.5,
        "rl_proposals": 100, "shield_fallbacks": 4,
        "table_rows_checked": 2048, "offline_spice_rows": 23040,
    }
    monkeypatch.setattr(D, "solve_rl_hybrid", lambda target, loss: dict(stub))
    out = D.design(9.0, 1.9e9, method="rl-hybrid")
    out["simulations"]["export"] = 1
    out["simulations"]["total"] += 1
    text = D.report(out)
    assert "export 1" in text
    assert "output export ran 1 new representative deck" in text


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
    # Wording widened by row 4y: the proposer is no longer only
    # retrieval, so the sentence says "proposed" (G138).
    assert "no proposed candidate passed the screen" in text


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


# ─────────────────────────────────────────────────────────────────────────────
# The three defects an independent review found on the delivered path
# ─────────────────────────────────────────────────────────────────────────────

def test_the_request_miss_is_measured_against_the_LIVE_tolerances():
    """D6, enforced. `feasible` is V1_SPECS and carries no request row, so a
    design can meet every device spec and be nowhere near what was asked.

    Measured before this existed: `--peaking 12 --f-peak 1.4e9` returned
    9.10 dB @ 1.774 GHz -- 2.90 dB and 0.341 oct out against 1.5 and 0.3 --
    with `feasible: True` and nothing flagged.
    """
    import math

    from nebula.rl import reward_v1 as R

    d = {"request": {"peaking_db": 12.0, "f_peak_hz": 1.4e9,
                     "f_peak_ghz": 1.4},
         "nominal": {"meas": {"peaking_db": 9.10, "_f_peak_ghz": 1.7735}}}
    rm = D.request_miss(d)
    assert rm["peaking_missed"] and rm["f_peak_missed"]
    assert rm["request_met"] is False
    assert rm["peaking_err_db"] == pytest.approx(-2.90, abs=0.01)
    assert rm["f_peak_err_oct"] == pytest.approx(
        math.log2(1.7735 / 1.4), abs=1e-6)
    # The tolerances are READ from reward_v1, never restated here.
    assert rm["tol_peaking_db"] == R.TOL["S3_peaking_match"]
    assert rm["tol_f_peak_oct"] == R.TOL["S3_f_peak_match"]


def test_a_request_that_IS_met_is_reported_as_met():
    d = {"request": {"peaking_db": 8.0, "f_peak_hz": 1.9e9, "f_peak_ghz": 1.9},
         "nominal": {"meas": {"peaking_db": 8.2, "_f_peak_ghz": 1.93}}}
    assert D.request_miss(d)["request_met"] is True


def test_an_unmeasurable_run_reports_no_request_match_rather_than_a_fake_one():
    assert D.request_miss({"request": {"peaking_db": 8.0, "f_peak_hz": 1.9e9,
                                       "f_peak_ghz": 1.9},
                           "nominal": {}}) is None


def test_the_report_SHOUTS_when_the_request_is_not_met():
    d = {"request": {"peaking_db": 12.0, "f_peak_hz": 1.4e9, "f_peak_ghz": 1.4},
         "method": "library", "robust_search": False,
         "nominal": {"ok": True, "feasible": True, "reward": 8.3,
                     "worst_spec": None, "params": {"w_in": 6e-5, "l_in": 5e-7, "nf_in": 4, "i_bias": 2e-3,
                       "rs": 300.0, "cs": 1e-12, "rl": 400.0,
                       "cl": 32.6e-15, "vcm_in": 1.35},
                     "meas": {"peaking_db": 9.10, "_f_peak_ghz": 1.7735,
                     "nyq_boost_db": 1.0, "_noise_mv": 0.4,
                     "_power_mw": 2.0, "g_dc_db": 1.0,
                     "pair_margin_v": 0.2, "tail_margin_v": 0.2,
                     "f_peak_oct": 0.0, "inoise_vrms": 4e-4,
                     "power_w": 2e-3}},
         "simulations": {"total": 829, "search": 828, "measure": 1},
         "wall_s": 1.0,
         "peaking_is_a_band_not_a_target": "x"}
    d["request_match"] = D.request_miss(d)
    text = D.report(d)
    assert "REQUEST NOT MET" in text
    assert "2.90" in text and "0.341" in text


def test_the_proposer_SOURCE_is_named_not_always_called_retrieval():
    """It printed "retrieval" for every accepted proposal regardless of source.
    Since row 4y the analytic solve answers 12 of the 13 proposal-answered
    requests, so the tool was crediting retrieval for its own best feature."""
    from nebula.experiments.exp_invert_screen import K

    base = {"request": {"peaking_db": 8.0, "f_peak_hz": 1.9e9,
                        "f_peak_ghz": 1.9},
            "method": "auto", "robust_search": True,
            "nominal": {"ok": False, "verdict": "x", "reason": "y"},
            "simulations": {"total": 1}, "wall_s": 1.0,
            "peaking_is_a_band_not_a_target": "x"}
    shallow = D.report({**base, "search": {"which_path": "proposal",
                                           "proposal_rank": 2,
                                           "n_candidates": 45,
                                           "screened_on": [1, 2, 3, 4]}})
    assert "ANALYTIC" in shallow and "retrieval" not in shallow.lower()

    lib = D.report({**base, "search": {"which_path": "proposal",
                                       "proposal_rank": K + 2,
                                       "n_candidates": 45,
                                       "screened_on": [1, 2, 3, 4]}})
    assert "RETRIEVAL" in lib

    deep = D.report({**base, "search": {"which_path": "proposal",
                                        "proposal_rank": 2 * K + 5,
                                        "n_candidates": 45,
                                        "screened_on": [1, 2, 3, 4]}})
    assert "ANALYTIC" in deep and "deep tail" in deep


def test_verify_reports_the_MANDATED_45_separately_from_the_load_sweep():
    """The brief mandates PVT only. Reporting just the 135-point verdict meant
    `--verify` printed FAILS on a design meeting every mandated corner, and the
    number the project claims coverage on could not be produced by the tool."""
    d = {"request": {"peaking_db": 8.0, "f_peak_hz": 1.9e9, "f_peak_ghz": 1.9},
         "method": "auto", "robust_search": True,
         "nominal": {"ok": True, "feasible": True, "reward": 8.3,
                     "worst_spec": None, "params": {"w_in": 6e-5, "l_in": 5e-7, "nf_in": 4, "i_bias": 2e-3,
                       "rs": 300.0, "cs": 1e-12, "rl": 400.0,
                       "cl": 32.6e-15, "vcm_in": 1.35},
                     "meas": {"peaking_db": 9.10, "_f_peak_ghz": 1.7735,
                     "nyq_boost_db": 1.0, "_noise_mv": 0.4,
                     "_power_mw": 2.0, "g_dc_db": 1.0,
                     "pair_margin_v": 0.2, "tail_margin_v": 0.2,
                     "f_peak_oct": 0.0, "inoise_vrms": 4e-4,
                     "power_w": 2e-3}},
         "simulations": {"total": 149, "search": 8, "measure": 1,
                         "verify": 140}, "wall_s": 1.0,
         "peaking_is_a_band_not_a_target": "x",
         "verification": {"n_corners": 45, "n_loads": 3, "n_points": 135,
                          "n_failed": 90, "n_failed_outside_the_screen": 84,
                          "all_points_pass": False, "worst_reward": -10.0,
                          "worst_point": "tt", "worst_spec": None,
                          "worst_is_a_screen_corner": False,
                          "n_mandated_points": 45, "n_mandated_pass": 45,
                          "mandated_all_pass": True,
                          "design_load_f": 32.6e-15}}
    text = D.report(d)
    assert "MANDATED PVT (S9): 45 / 45" in text and "PASS" in text
    # ...and the 135-point result is still shown, not hidden behind it.
    assert "135 points" in text and "90 failed" in text
