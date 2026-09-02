"""
tests/test_nan_retry.py — gates on the G54 retry now built into `run_point`
(`PREDICTIONS.md` entry 55, `HANDOFF.md` G54).

WHY EACH GUARD EXISTS
----------------------
1.  **Only the G54 signature may retry.** `scan_for_silent_failures` catches
    nine kinds of silent failure. Eight of them mean the deck is wrong, and
    re-running one with a bigger capacitor is superstition that costs a deck
    and can only ever produce the same failure. A retry that fired on
    `could not find a valid modelname` would be hiding a units bug behind a
    second attempt.
2.  **The retry must be rare, and provably so.** Entry 55 Q2 measured 1 firing
    in 45 corners. A signature broad enough to fire routinely would mean decks
    are quietly simulated with a capacitor the netlist does not name -- and
    nobody would notice, because the retry is the thing making them succeed.
3.  **It must be switchable off, exactly.** Every published number predates it,
    so `nan_retry_bypass_f=None` has to reproduce the old behaviour rather than
    approximately reproduce it.
4.  **A pointless retry is still a cost.** If the tail is already at or above
    the retry value, the second deck is guaranteed identical, so it must not
    run.
5.  **`C_BYPASS_F` must stay 10 pF.** The retry raises the bypass on ONE deck
    that already failed; changing the default would change the value every
    published number was measured against.

No SPICE: every test here builds a point and calls the decision function, which
is where all the judgement lives. The end-to-end behaviour is measured in
entry 55 (315 decks) rather than asserted here.
"""

from __future__ import annotations

import dataclasses
import ast
import inspect
import textwrap

import pytest

from nebula.device import sky130_runner as SR

G54 = "ngspice silent failure: inoise_total = -nan(ind)"


@pytest.fixture(scope="module")
def point():
    """A real `SizingPoint`, built without simulating anything."""
    from nebula.rl.contract import sizing_from_u
    from nebula.rl.evaluator import build_point

    sizing = sizing_from_u([0.5] * 7, cl_f=32.6e-15)
    pt, _ = build_point(sizing, corner="tt", vdd_scale=1.0)
    return pt


# ─────────────────────────────────────────────────────────────────────────────
# Guard 1 / 2 — only the G54 signature, and nothing else
# ─────────────────────────────────────────────────────────────────────────────

def test_the_g54_nan_is_retried(point):
    got = SR._nan_retry_point(point, G54, SR.NAN_RETRY_BYPASS_F)
    assert got is not None
    assert got.tail.c_bypass_f == pytest.approx(SR.NAN_RETRY_BYPASS_F)


def test_an_inf_is_retried_too():
    # Same integration, same singularity, printed differently.
    from nebula.rl.contract import sizing_from_u
    from nebula.rl.evaluator import build_point

    pt, _ = build_point(sizing_from_u([0.5] * 7, cl_f=32.6e-15))
    assert SR._nan_retry_point(pt, "onoise_total = inf", 30e-12) is not None


@pytest.mark.parametrize("offender", [
    "Error: could not find a valid modelname",
    "Undefined parameter [nfactor]",
    "doAnalyses: iteration limit reached",
    "singular matrix",
    "fatal error in ngspice, exit(1)",
    "vector inoise_total_rlp is not available or has zero length",
])
def test_no_other_silent_failure_is_retried(point, offender):
    # Guard 1. These mean the deck is wrong; a bigger capacitor cannot fix one.
    assert SR._nan_retry_point(point, offender, SR.NAN_RETRY_BYPASS_F) is None


def test_a_parameter_merely_containing_nan_does_not_trigger_a_retry(point):
    # The signature is anchored to `= value`, so a model parameter or a banner
    # that happens to contain the letters cannot fire it.
    assert SR._nan_retry_point(point, "nfactor = 1.0", 30e-12) is None
    assert SR._nan_retry_point(point, "* nanometre grid", 30e-12) is None


def test_an_empty_reason_does_not_retry(point):
    assert SR._nan_retry_point(point, "", 30e-12) is None
    assert SR._nan_retry_point(point, None, 30e-12) is None


# ─────────────────────────────────────────────────────────────────────────────
# Guard 3 — switchable off, exactly
# ─────────────────────────────────────────────────────────────────────────────

def test_passing_none_disables_the_retry(point):
    # Every published number predates the retry; this is how they are
    # reproduced.
    assert SR._nan_retry_point(point, G54, None) is None


def test_run_point_exposes_the_switch():
    import inspect

    sig = inspect.signature(SR.run_point)
    assert "nan_retry_bypass_f" in sig.parameters
    assert sig.parameters["nan_retry_bypass_f"].default == SR.NAN_RETRY_BYPASS_F


def test_the_retry_preserves_the_attenuator_and_custom_range():
    """A retry must not silently measure a different circuit."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(SR.run_point)))
    recursive = [
        call for call in ast.walk(tree)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
        and call.func.id == "run_point"
    ]
    assert len(recursive) == 1
    keywords = {item.arg: ast.unparse(item.value)
                for item in recursive[0].keywords}
    assert keywords["atten_code"] == "atten_code"
    assert keywords["atten_max_x"] == "atten_max_x"


# ─────────────────────────────────────────────────────────────────────────────
# Guard 4 — a retry that cannot change anything must not run
# ─────────────────────────────────────────────────────────────────────────────

def test_a_tail_already_at_the_retry_value_is_not_retried(point):
    raised = dataclasses.replace(
        point, tail=dataclasses.replace(point.tail,
                                        c_bypass_f=SR.NAN_RETRY_BYPASS_F))
    assert SR._nan_retry_point(raised, G54, SR.NAN_RETRY_BYPASS_F) is None


def test_a_tail_above_the_retry_value_is_not_retried(point):
    raised = dataclasses.replace(
        point, tail=dataclasses.replace(point.tail, c_bypass_f=1e-9))
    assert SR._nan_retry_point(raised, G54, SR.NAN_RETRY_BYPASS_F) is None


def test_a_point_with_no_tail_is_not_retried(point):
    ideal = dataclasses.replace(point, tail=None)
    assert SR._nan_retry_point(ideal, G54, SR.NAN_RETRY_BYPASS_F) is None


def test_the_retry_changes_the_bypass_and_nothing_else(point):
    got = SR._nan_retry_point(point, G54, SR.NAN_RETRY_BYPASS_F)
    assert got is not None
    # Everything except the tail is the same object-equal value...
    for f in dataclasses.fields(point):
        if f.name == "tail":
            continue
        assert getattr(got, f.name) == getattr(point, f.name), f.name
    # ...and inside the tail, only the bypass moved.
    for f in dataclasses.fields(point.tail):
        if f.name == "c_bypass_f":
            continue
        assert getattr(got.tail, f.name) == getattr(point.tail, f.name), f.name


# ─────────────────────────────────────────────────────────────────────────────
# Guard 5 — the published default is untouched, and the retry is recorded
# ─────────────────────────────────────────────────────────────────────────────

def test_the_published_bypass_default_is_still_10pF():
    from nebula.device.tail import C_BYPASS_F, TailDevice

    assert C_BYPASS_F == 10e-12
    assert TailDevice(w_tail=100.0, l_tail=0.5, nf_tail=8).c_bypass_f == 10e-12


def test_the_retry_value_is_the_smallest_one_measured_to_clear_it():
    # Entry 54 measured 30p / 100p / 1n bit-identical; the smallest keeps the
    # unbilled capacitor area as small as the mechanism allows.
    assert SR.NAN_RETRY_BYPASS_F == 30e-12


def test_a_point_is_not_marked_as_retried_by_default():
    assert SR.Sky130Point(ok=True).nan_retry_used is False


def test_the_flag_is_settable_so_a_retried_point_can_be_identified():
    # It is stamped whether the retry SUCCEEDED or not: a corner still NaN at
    # 30 pF is a different fact from one that was never retried.
    pt = SR.Sky130Point(ok=False, fail_reason=G54)
    pt.nan_retry_used = True
    assert pt.nan_retry_used is True


# ─────────────────────────────────────────────────────────────────────────────
# Row 4u — the retry's second deck must be BILLED
# ─────────────────────────────────────────────────────────────────────────────

def test_a_point_that_did_not_retry_costs_one_deck():
    assert SR.Sky130Point(ok=True).n_decks == 1


def test_a_retried_point_costs_two_decks():
    # Row 4u: the retry is a recursive call inside run_point, so a caller
    # counting one call per call under-bills it. Entry 56 reproduced entry 40's
    # mean_sims_per_request to every digit while spending ~30 decks more.
    pt = SR.Sky130Point(ok=True)
    pt.nan_retry_used = True
    assert pt.n_decks == 2


def test_n_decks_is_derived_and_cannot_drift_from_the_flag():
    pt = SR.Sky130Point(ok=True)
    for flag, want in ((False, 1), (True, 2), (False, 1)):
        pt.nan_retry_used = flag
        assert pt.n_decks == want


def test_the_evaluator_charges_the_retry(monkeypatch):
    """`evaluate` must bill 2 when the point it got was retried."""
    from nebula.rl import evaluator as EV

    retried = SR.Sky130Point(ok=False, fail_reason="nope")
    retried.nan_retry_used = True
    monkeypatch.setattr(EV, "run_point", lambda *a, **k: retried)
    budget = EV.SpiceBudget()
    from nebula.rl.contract import sizing_from_u
    EV.evaluate(sizing_from_u([0.5] * 7, cl_f=32.6e-15), budget)
    # 2 for the first call; the transient re-run does not fire on "nope".
    assert budget.calls == 2


def test_the_evaluator_charges_one_when_there_was_no_retry(monkeypatch):
    from nebula.rl import evaluator as EV

    monkeypatch.setattr(EV, "run_point",
                        lambda *a, **k: SR.Sky130Point(ok=False,
                                                       fail_reason="nope"))
    budget = EV.SpiceBudget()
    from nebula.rl.contract import sizing_from_u
    EV.evaluate(sizing_from_u([0.5] * 7, cl_f=32.6e-15), budget)
    assert budget.calls == 1
