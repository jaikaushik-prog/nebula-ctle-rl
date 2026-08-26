"""
tests/test_dfe_ablation.py — gates on `link/dfe_ablation.py` and
`exp_dfe_ablation` (`PREDICTIONS.md` entry 39).

WHAT IS GUARDED, AND WHICH FAILURE EACH GUARD IS FOR
------------------------------------------------------
1.  **THE `ideal` POLICY MUST REPRODUCE `eye_opening_vs_phase` EXACTLY**, height
    and width. It is not a convenience path — it is the control that licenses
    every other policy. Entry 39's Q1 caught a real defect here: the first
    version reported height at the *best phase* while the bridge reports it at
    the *cursor*, a 7 mV disagreement on a 456 mV eye that no eyeball would
    have questioned.
2.  **The height is read at the CURSOR and the width from the SWEEP** — the
    bridge's two conventions, kept apart.
3.  **Deleting the DFE can only shrink the eye.** A policy that ever *increases*
    an opening is an arithmetic sign error wearing a physical name.
4.  **`ideal` and `none` differ by exactly `2|h1|`** at the reporting phase.
    That is the whole physical content of the ablation, and it is pinned
    rather than trusted.
5.  **The experiment ablates THE SHIPPED DESIGN.** Ablating a different design
    under this entry's name would be a different experiment.
6.  **Q1 dominates the verdict**: a control that did not reproduce makes every
    other number uninterpretable.

No SPICE: the pulse responses here are synthetic, which is what lets the
arithmetic be checked exactly.
"""

from __future__ import annotations

import numpy as np
import pytest

import nebula.link.dfe_ablation as A
from nebula.experiments import exp_dfe_ablation as X
from nebula.link.cursors import cursors_from_pulse, eye_opening_vs_phase

OSR = 16


def _pulse(h1: float = 0.15, pre: float = 0.04, post2: float = 0.03,
           n_ui: int = 12, cursor_ui: int = 3) -> tuple:
    """A synthetic pulse response with known cursors."""
    n = OSR * n_ui
    pr = np.zeros(n)
    c = OSR * cursor_ui
    pr[c] = 1.0
    pr[c + OSR] = h1
    pr[c - OSR] = pre
    pr[c + 2 * OSR] = post2
    return pr, c


# ---------------------------------------------------------------------------
# 1 + 2. the control, and the two conventions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("h1", [0.0, 0.05, 0.15, 0.30, -0.12])
def test_ideal_reproduces_the_real_eye_exactly(h1):
    pr, c = _pulse(h1=h1)
    ref = eye_opening_vs_phase(pr, OSR, c)
    got = A.eye_under_policy(pr, OSR, c, "ideal")
    at_cursor = cursors_from_pulse(pr, OSR, c)
    assert got.eye_h_v == at_cursor.eye_h_v, "height must be read AT THE CURSOR"
    assert got.eye_w_ui == ref.width_ui, "width must come from the phase sweep"


def _skewed_pulse(skew: float = 0.15, tail: float = 0.25):
    """A pulse whose BEST sampling phase is NOT the cursor phase.

    **The symmetric pulse above cannot tell the two conventions apart** — its
    argmax phase is also its best phase, so a gate built only on it stays green
    when the height is read from the wrong one. That is exactly what entry 39's
    sabotage round found, and it is G125: the test DATA has to separate the
    correct rule from the broken one.
    """
    n = OSR * 12
    t = np.arange(n)
    c = OSR * 3
    pr = np.exp(-((t - (c + skew * OSR)) / (0.42 * OSR)) ** 2)
    pr += tail * np.exp(-((t - (c + OSR + skew * OSR)) / (0.55 * OSR)) ** 2)
    return pr, int(np.argmax(pr))


def test_the_test_data_can_TELL_the_two_conventions_apart():
    """If this fails, the gate below is worthless however green it looks."""
    pr, c = _skewed_pulse()
    ref = eye_opening_vs_phase(pr, OSR, c)
    at_cursor = cursors_from_pulse(pr, OSR, c).eye_h_v
    assert ref.eye_h_max_v != at_cursor, (
        "best-phase and cursor heights are equal on this pulse, so no gate "
        "built on it can catch the convention being swapped")
    assert ref.best_phase_ui != 0.0


def test_ideal_reads_the_height_at_the_CURSOR_on_a_skewed_pulse():
    """The gate the sabotage round proved was needed."""
    pr, c = _skewed_pulse()
    got = A.eye_under_policy(pr, OSR, c, "ideal")
    ref = eye_opening_vs_phase(pr, OSR, c)
    assert got.eye_h_v == cursors_from_pulse(pr, OSR, c).eye_h_v
    assert got.eye_h_v != ref.eye_h_max_v, (
        "the height came from the best phase, which is the bridge's OTHER "
        "convention — 7 mV on a 456 mV eye in the real run")
    assert got.eye_w_ui == ref.width_ui


def test_the_control_is_exact_not_approximate():
    """1e-9, not 'close'. Entry 39's Q1 threshold is an equality in practice."""
    pr, c = _pulse(h1=0.18)
    assert abs(A.eye_under_policy(pr, OSR, c, "ideal").eye_h_v
               - cursors_from_pulse(pr, OSR, c).eye_h_v) == 0.0


# ---------------------------------------------------------------------------
# 3 + 4. the physics of the ablation
# ---------------------------------------------------------------------------

def test_deleting_the_dfe_costs_exactly_twice_the_post_cursor():
    pr, c = _pulse(h1=0.15)
    ideal = A.eye_under_policy(pr, OSR, c, "ideal")
    none = A.eye_under_policy(pr, OSR, c, "none")
    assert none.eye_h_v == pytest.approx(ideal.eye_h_v - 2 * abs(ideal.h1_v))


@pytest.mark.parametrize("policy", ["none", "misadapted", "quantised"])
def test_no_policy_can_open_the_eye_wider_than_ideal(policy):
    """A policy that INCREASES an opening is a sign error with a physical name."""
    for h1 in (0.02, 0.1, 0.25, -0.2):
        pr, c = _pulse(h1=h1)
        ideal = A.eye_under_policy(pr, OSR, c, "ideal")
        got = A.eye_under_policy(pr, OSR, c, policy)
        assert got.eye_h_v <= ideal.eye_h_v + 1e-12
        assert got.eye_w_ui <= ideal.eye_w_ui + 1e-12


def test_a_zero_post_cursor_makes_every_policy_identical():
    pr, c = _pulse(h1=0.0)
    eyes = A.all_policies(pr, OSR, c)
    hs = {p: e.eye_h_v for p, e in eyes.items()}
    assert len(set(hs.values())) == 1, hs


def test_misadaptation_leaves_exactly_its_fraction():
    assert A.leftover_v(0.20, 1.0, "misadapted", eps=0.25) == pytest.approx(0.05)
    assert A.leftover_v(0.20, 1.0, "ideal") == 0.0
    assert A.leftover_v(0.20, 1.0, "none") == pytest.approx(0.20)


def test_quantisation_leftover_is_the_rounding_error_and_is_bounded():
    """A 4-bit tap on [-0.5, 0.5] has a step of 1/16; the leftover cannot
    exceed half a step."""
    half_step = 0.5 / (2 ** A.QUANT_BITS)
    for tap in (0.0, 0.019, 0.0689, 0.15, -0.02, 0.33):
        left = A.leftover_v(tap, 1.0, "quantised")
        assert left <= half_step + 1e-12, (tap, left)


def test_an_unknown_policy_raises_rather_than_defaulting_to_ideal():
    pr, c = _pulse()
    with pytest.raises(ValueError, match="unknown policy"):
        A.eye_under_policy(pr, OSR, c, "wishful")
    with pytest.raises(ValueError, match="unknown policy"):
        A.leftover_v(0.1, 1.0, "wishful")


def test_the_registered_policy_constants_are_entry_39s():
    assert (A.MISADAPT_EPS, A.QUANT_BITS) == (0.20, 4)
    assert A.POLICIES == ("ideal", "none", "misadapted", "quantised")


def test_too_few_phases_raises():
    pr, c = _pulse()
    with pytest.raises(ValueError, match="osr"):
        A.eye_under_policy(pr, 2, c, "ideal")


# ---------------------------------------------------------------------------
# 5 + 6. the experiment
# ---------------------------------------------------------------------------

def test_the_shipped_design_is_the_one_the_compliance_artifact_verified():
    """Guard 5, run against the real artifacts."""
    u, committed = X.shipped_design()
    assert len(u) == 7
    assert committed["design_id"] == "c507a3ba6f58b9a6"


def test_the_design_load_is_the_middle_of_three():
    pts = [{"cl_f": 1e-14}, {"cl_f": 3e-14}, {"cl_f": 7e-14}]
    assert X._design_load_f(pts) == 3e-14
    with pytest.raises(RuntimeError, match="3 loads"):
        X._design_load_f([{"cl_f": 1e-14}, {"cl_f": 3e-14}])


def _row(h_ideal=0.4, h_none=0.35, w_ideal=0.85, w_none=0.75, cl=3e-14,
         committed_h=None, committed_w=None):
    pol = {p: {"eye_h_v": h, "eye_w_ui": w, "h0_v": 0.2, "h1_v": 0.004,
               "leftover_v": 0.0}
           for p, h, w in (("ideal", h_ideal, w_ideal), ("none", h_none, w_none),
                           ("misadapted", h_ideal, w_ideal),
                           ("quantised", h_ideal, w_ideal))}
    return {"corner": "tt", "vdd_scale": 1.0, "temp_c": 27.0, "cl_f": cl,
            "dfe_tap": 0.02, "policies": pol,
            "committed_eye_h_v": h_ideal if committed_h is None else committed_h,
            "committed_eye_w_ui": w_ideal if committed_w is None else committed_w}


def _res(rows):
    return {"design_load_f": 3e-14, "rows": rows, "n_points": len(rows)}


def test_the_go_branch_needs_both_height_and_width():
    v = X._verdict(_res([_row()]))
    assert v["Q1_control_reproduced"] and v["Q2_height_survives"]
    assert v["Q3_width_survives"]
    assert "REMOVED ENTIRELY" in v["call"]


def test_a_control_that_did_not_reproduce_dominates_everything():
    v = X._verdict(_res([_row(committed_h=0.41)]))
    assert not v["Q1_control_reproduced"]
    assert "measuring its own" in v["call"]
    assert "REMOVED ENTIRELY" not in v["call"]


def test_a_width_that_needs_the_tap_is_reported_as_such():
    v = X._verdict(_res([_row(w_none=0.30)]))
    assert v["Q2_height_survives"] and not v["Q3_width_survives"]
    assert "WIDTH does not" in v["call"]


def test_a_load_bearing_dfe_says_so_and_forbids_adjusting_the_model():
    v = X._verdict(_res([_row(h_none=0.05)]))
    assert not v["Q2_height_survives"]
    assert "IS load-bearing" in v["call"]
    assert "DO NOT adjust the tap model" in v["call"]


def test_only_the_design_load_counts_toward_the_mandated_45():
    rows = [_row(cl=3e-14), _row(cl=1e-14, h_none=0.05)]
    v = X._verdict(_res(rows))
    assert v["n_mandated"] == 1
    assert v["Q2_height_survives"], (
        "a failure at the LIGHT load is not a mandated-corner failure")
