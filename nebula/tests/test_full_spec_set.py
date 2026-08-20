"""
Tests for the full competition spec table — session 22o.

The slide lists eleven spec rows. The scored objective had **seven**, and two
of the three missing ones (S4 HD3, S7 area) had no tolerance row at all. This
adds them and pins the two traps found while doing it.

Four are gates in CLAUDEwa.md §8 rule 10's sense:

  * `test_v1_is_LISTED_not_derived_by_exclusion` — V1 used to be "everything
    that is not S8", so any new row joined it silently and moved every
    published reward.
  * `test_v2_is_REACHABLE_through_reward` — `link` was accepted by `reward()`
    and never forwarded, so the eye was unscorable (G73's family).
  * `test_S4_and_S7_are_absent_unless_MEASURED` — the same
    absent-never-defaulted discipline S8 already had.
  * `test_the_new_tolerances_are_DERIVED_by_the_existing_rule`
"""

from __future__ import annotations

import pytest

from nebula.common.types import (
    SPEC_AREA_MAX_MM2,
    SPEC_EYE_H_MIN_V,
    SPEC_EYE_W_MIN_UI,
    SPEC_HD3_MAX_DBC,
    SPEC_POWER_MAX_W,
    SPEC_VN_IN_MAX_VRMS,
)
from nebula.rl import reward_v1 as R


def _meas(peaking=7.5, f_oct=-0.5):
    return {"g_dc_db": 3.0, "peaking_db": peaking, "f_peak_oct": f_oct,
            "nyq_boost_db": 4.0, "inoise_vrms": 3.0e-4, "power_w": 5.0e-3,
            "pair_margin_v": 0.25, "tail_margin_v": 0.05}


class _Link:
    ok = True
    eye_h_v = 0.758
    eye_w_ui = 0.875


TARGET_HZ = 1.7677669529663688e9


# ─────────────────────────────────────────────────────────────────────────────


def test_v1_is_LISTED_not_derived_by_exclusion():
    """**The trap that would have moved every published number.**

    `V1_SPECS` used to read `tuple(n for n in SPEC_NAMES if not
    n.startswith("S8_"))`. Adding S4 and S7 -- neither S8-prefixed -- would
    have grown V1 from seven rows to nine, which changes `len(specs)`, which
    changes the feasibility bonus `B = N + 1`, which changes **every reward
    this project has published** -- including the +8.950669 ceiling -- with
    nothing in the diff to show for it.
    """
    V1 = R.V1_SPECS
    assert len(V1) == 7, "V1 must stay at the seven rows every number used"
    assert set(V1) == {"S3_f_peak", "S3_peaking", "S3_nyq_boost", "S5_noise",
                       "S6_power", "saturation", "tail_saturation"}
    # the new rows exist and are OUTSIDE V1
    assert "S4_hd3" in R.TOL and "S7_area" in R.TOL
    assert "S4_hd3" not in V1 and "S7_area" not in V1
    assert R.feasible_bonus(len(V1)) == 8.0, (
        "the feasibility bonus every published reward was computed with")


def test_v2_and_v3_nest_and_v3_is_the_whole_slide():
    assert set(R.V1_SPECS) < set(R.V2_SPECS) < set(R.V3_SPECS)
    assert len(R.V2_SPECS) == 9 and len(R.V3_SPECS) == 11
    assert set(R.V3_SPECS) - set(R.V2_SPECS) == {"S4_hd3", "S7_area"}


def test_no_tolerance_row_is_an_ORPHAN():
    """Every tolerance row must be reachable from some published spec set.

    **This used to read `set(V3_SPECS) == set(SPEC_NAMES)`** -- V3 is the whole
    slide, so at the time it was also the union of everything. Session 22s
    added `S4_hd3_nyq`, which is deliberately NOT on the slide: it is S4 asked
    at the operating point rather than at its stated 100 MHz, and it lives in
    V4. The old assertion caught that correctly and its premise had simply
    expired -- V3 is the slide, not the universe.

    The property actually worth holding is the one the old comment named: a
    tolerance with no spec set pointing at it is dead weight nothing can score,
    which is G73's family. That is what this checks now, and it is strictly
    stronger than the old form because it covers V0 and V4 too.
    """
    reachable = (set(R.V0_SPECS) | set(R.V1_SPECS) | set(R.V2_SPECS)
                 | set(R.V3_SPECS) | set(R.V4_SPECS) | set(R.V5_SPECS))
    orphans = set(R.SPEC_NAMES) - reachable
    assert not orphans, f"tolerance rows no spec set can score: {sorted(orphans)}"
    # and nothing is named in a set without a tolerance behind it
    assert reachable <= set(R.SPEC_NAMES)


def test_v4_asks_S4_at_the_operating_point_and_v3_asks_it_at_the_slide_point():
    """The two HD3 rows are separate on purpose: 100 MHz / 200 mVpp versus
    2.5 GHz / 535 mVpp, measured 30 dB apart on the delivered design."""
    assert "S4_hd3" in R.V3_SPECS and "S4_hd3_nyq" not in R.V3_SPECS
    assert "S4_hd3_nyq" in R.V4_SPECS and "S4_hd3" not in R.V4_SPECS
    assert R.TOL["S4_hd3"] == R.TOL["S4_hd3_nyq"] == 10.0


def test_v2_is_REACHABLE_through_reward():
    """**G73's family: a spec set with tolerances, a docstring and no reachable
    caller.** `reward()` accepted `link` and never passed it to `margins()`, so
    asking for `V2_SPECS` raised `KeyError('S8_eye_h')` and the eye could not
    be scored at all."""
    rb = R.reward(_meas(), TARGET_HZ, specs=R.V2_SPECS, link=_Link())
    assert rb.valid and rb.feasible
    assert "S8_eye_h" in rb.margins and "S8_eye_w" in rb.margins
    assert rb.margins["S8_eye_h"] == pytest.approx(
        _Link.eye_h_v - SPEC_EYE_H_MIN_V)
    assert rb.margins["S8_eye_w"] == pytest.approx(
        _Link.eye_w_ui - SPEC_EYE_W_MIN_UI)


def test_S4_and_S7_are_absent_unless_MEASURED():
    """The same discipline S8 has: present only when measured, never defaulted.
    A caller asking for `V3_SPECS` without them must get a `KeyError` rather
    than a reward computed from a spec nobody checked."""
    m = R.margins(_meas(), TARGET_HZ)
    assert "S4_hd3" not in m and "S7_area" not in m

    with pytest.raises(KeyError):
        R.reward(_meas(), TARGET_HZ, specs=R.V3_SPECS, link=_Link())

    m2 = R.margins(_meas(), TARGET_HZ, hd3_dbc=-61.10, area_mm2=0.001092)
    assert m2["S4_hd3"] == pytest.approx(SPEC_HD3_MAX_DBC - (-61.10))
    assert m2["S7_area"] == pytest.approx(SPEC_AREA_MAX_MM2 - 0.001092)


def test_the_HD3_margin_has_the_right_SIGN():
    """HD3 is a NEGATIVE dBc number and **more negative is better**, so the
    margin is `limit - measured`. Getting this backwards would score the most
    linear designs as the worst -- which is the mistake session 21 already made
    once, on the compression gate."""
    good = R.margins(_meas(), TARGET_HZ, hd3_dbc=-61.0)["S4_hd3"]
    bad = R.margins(_meas(), TARGET_HZ, hd3_dbc=-10.0)["S4_hd3"]
    assert good > 0 > bad, "a -61 dBc design must pass and a -10 dBc one fail"
    assert good == pytest.approx(31.0)


def test_the_new_tolerances_are_DERIVED_by_the_existing_rule():
    """S5 and S6 already use "one third of the limit". S4 and S7 use the same
    rule, so neither is a number somebody chose."""
    assert R.TOL["S5_noise"] == pytest.approx(SPEC_VN_IN_MAX_VRMS / 3.0,
                                              rel=1e-6)
    assert R.TOL["S6_power"] == pytest.approx(SPEC_POWER_MAX_W / 3.0, rel=1e-6)
    assert R.TOL["S4_hd3"] == pytest.approx(abs(SPEC_HD3_MAX_DBC) / 3.0)
    assert R.TOL["S7_area"] == pytest.approx(SPEC_AREA_MAX_MM2 / 3.0)


def test_adding_rows_did_not_move_the_published_ceiling():
    """The +8.950669 ceiling is a property of `V1_SPECS`. If it moves, every
    published reward moved with it."""
    # Every row generous EXCEPT the peak frequency, so `S3_f_peak` binds --
    # which is the condition the ceiling is a property of. 0.02466 octaves is
    # the distance from the target to the nearest `ac dec 50` grid point (G74).
    m = {"g_dc_db": 3.0, "peaking_db": 7.5, "f_peak_oct": -0.5 + 0.024664,
         "nyq_boost_db": 4.0, "inoise_vrms": 1.0e-5, "power_w": 1.0e-3,
         "pair_margin_v": 0.5, "tail_margin_v": 0.5}
    rb = R.reward(m, TARGET_HZ, specs=R.V1_SPECS)
    assert rb.feasible and rb.worst_spec == "S3_f_peak"
    assert rb.reward == pytest.approx(8.950669, abs=1e-4)


def test_the_full_set_scores_all_eleven_rows():
    rb = R.reward(_meas(), TARGET_HZ, specs=R.V3_SPECS, link=_Link(),
                  hd3_dbc=-61.10, area_mm2=0.001092)
    assert set(rb.margins) == set(R.V3_SPECS)
    assert rb.feasible
    assert rb.reward >= R.feasible_bonus(len(R.V3_SPECS))
    assert R.feasible_bonus(len(R.V3_SPECS)) == 12.0
