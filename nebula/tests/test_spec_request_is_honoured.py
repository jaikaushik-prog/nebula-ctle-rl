"""**The deliverable takes a spec as INPUT. These tests pin that it uses it.**

Session 23. `SPEC_CONDITIONED.md` §0 measured the defect this file exists to
prevent recurring:

    one fixed design scores 8.999984 against targets of
    3, 5, 7.5, 10 and 12 dB -- IDENTICALLY

`margins()` accepted `target_peaking_db` and discarded it, because S3's peaking
constraint is a BAND and the band is the right reading of a *constraint*. It is
the wrong reading of a *request*, and the competition slide asks for "a
framework that takes target specs as input". A user asking for 11 dB and being
handed 6.4 dB with a PASS beside it is a tool ignoring its own input.

The two properties that matter pull in opposite directions and both are pinned:

1. `V5_SPECS` **honours** the request -- the score moves with the target.
2. `V1_SPECS`..`V4_SPECS` are **bit-identical** to what they were, whether or
   not a target is supplied, because `BASELINES.md` §7f makes every published
   reward number hostage to `len(specs)`.

Each assertion here was watched go red before it was made to pass (rule 4):
deleting the `if target_peaking_db is not None` block reddens the first group,
and putting `"S3_peaking_match"` into `V1_SPECS` reddens the second.
"""

from __future__ import annotations

import pytest

import nebula.rl.reward_v1 as R

#: A design measuring 6.65 dB of peaking, comfortably inside S3's 3-12 dB band
#: and sitting near the centre of S3's frequency window. Every number here is
#: in the units `contract.OBS_SCALES` declares.
MEAS = dict(g_dc_db=-3.4, peaking_db=6.65, f_peak_oct=-0.0749,
            nyq_boost_db=6.65, inoise_vrms=2.1e-4, power_w=7.1e-3,
            pair_margin_v=0.64, tail_margin_v=0.35)

#: The centre of S3's window in LOG frequency, which is what every frequency
#: quantity in this project is measured in.
TARGET_F = 1.7677669529663687e9


class _Link:
    """The minimum a `LinkResult` needs to look like for the S8 rows."""

    ok = True
    eye_h_v = 0.38
    eye_w_ui = 0.86


def _v5(target_peaking_db):
    return R.reward(MEAS, TARGET_F, specs=R.V5_SPECS,
                    target_peaking_db=target_peaking_db, link=_Link(),
                    area_mm2=0.0027, hd3_nyq_dbc=-34.0)


# ── 1. the request is honoured ───────────────────────────────────────────────


def test_v5_score_MOVES_with_the_requested_peaking():
    """The exact defect `SPEC_CONDITIONED.md` §0 measured, inverted."""
    scores = {t: _v5(t).reward for t in (3.0, 5.0, 7.5, 10.0, 12.0)}
    assert len(set(scores.values())) > 1, (
        f"one design scored identically against five different peaking "
        f"requests -- the request is still being discarded: {scores}")


def test_a_request_the_design_cannot_meet_is_INFEASIBLE():
    """6.65 dB delivered against 10 dB asked is a miss, not a pass.

    This is the user-visible bug: under `V1_SPECS` this design is feasible
    against *every* target in the band, including ones it misses by 5 dB.
    """
    assert _v5(10.0).feasible is False
    assert _v5(10.0).worst_spec == "S3_peaking_match"
    # ...while the same design against what it actually delivers is fine.
    assert _v5(6.65).feasible is True


def test_the_band_constraint_SURVIVES_alongside_the_match_row():
    """`S3_peaking` is kept, and that is not redundancy.

    A request for 2 dB must not be honoured by leaving S3's 3-12 dB band. The
    match row alone would happily reward a design that matched an out-of-band
    request exactly.
    """
    assert "S3_peaking" in R.V5_SPECS and "S3_peaking_match" in R.V5_SPECS
    out_of_band = dict(MEAS, peaking_db=2.0)
    rb = R.reward(out_of_band, TARGET_F, specs=R.V5_SPECS,
                  target_peaking_db=2.0, link=_Link(), area_mm2=0.0027,
                  hd3_nyq_dbc=-34.0)
    assert rb.feasible is False, "matched the request but left the band"
    assert rb.margins["S3_peaking_match"] > 0.0, "the request WAS matched"
    assert rb.margins["S3_peaking"] < 0.0, "and the band was left"


def test_the_match_tolerance_is_NOT_tighter_than_peakings_own_PVT_EXCURSION():
    """The tolerance is derived from a measurement, and this pins the argument.

    Peaking moves **1.48-1.65 dB across the 45 mandated PVT corners** on the
    two compliant designs (session 23, measured off the 135-point artifacts).
    The row is scored per corner, so a tolerance at or below half that
    excursion is unmeetable at ANY target however well the design is centred.
    A future edit tightening this to "1 dB, the production tuning step" would
    look reasonable and would make the spec set empty by construction.
    """
    worst_measured_excursion_db = 1.65
    assert R.TOL["S3_peaking_match"] > worst_measured_excursion_db / 2.0, (
        "tolerance is below half of peaking's own PVT excursion: no design "
        "can satisfy this row at any target")


# ── 2. nothing published moved ───────────────────────────────────────────────


@pytest.mark.parametrize("specs", [R.V0_SPECS, R.V1_SPECS, R.V2_SPECS,
                                   R.V3_SPECS, R.V4_SPECS])
def test_published_spec_sets_are_BIT_IDENTICAL_with_and_without_a_target(specs):
    """`BASELINES.md` §7f: touching the reward means re-running every arm.

    The new row is emitted only when a target is supplied AND is only selected
    by `V5_SPECS`, so both guards have to fail before a published number moves.
    """
    kw = dict(link=_Link(), area_mm2=0.0027, hd3_dbc=-61.0,
              hd3_nyq_dbc=-34.0)
    a = R.reward(MEAS, TARGET_F, specs=specs, target_peaking_db=None, **kw)
    b = R.reward(MEAS, TARGET_F, specs=specs, target_peaking_db=11.0, **kw)
    assert a.reward == b.reward, (
        f"{specs} moved when a peaking target was supplied: "
        f"{a.reward!r} -> {b.reward!r}")
    assert a.margins == b.margins and a.worst_spec == b.worst_spec


def test_the_new_row_is_ABSENT_unless_a_target_was_actually_requested():
    """Present when asked for, absent otherwise, never defaulted.

    The same rule S4, S7 and S8 already follow. A defaulted match row would
    make every design look like it just satisfied a request nobody made.
    """
    assert "S3_peaking_match" not in R.margins(MEAS, TARGET_F)
    assert "S3_peaking_match" in R.margins(MEAS, TARGET_F,
                                           target_peaking_db=7.5)


def test_v5_is_listed_by_ENUMERATION_not_derived_from_another_set():
    """G101/G106: a set defined by exclusion or by addition grows silently."""
    src = (R.__file__ or "")
    text = open(src, encoding="utf-8").read()
    start = text.index("V5_SPECS: tuple[str, ...] = (")
    body = text[start:text.index(")", start)]
    assert "V4_SPECS" not in body and "for s in" not in body, (
        "V5_SPECS is derived from another tuple; every inherited member must "
        "be re-checked when the parent changes (G106)")
    assert len(set(R.V5_SPECS)) == len(R.V5_SPECS), "duplicate row in V5_SPECS"


def test_every_v5_row_has_a_tolerance_behind_it():
    assert set(R.V5_SPECS) <= set(R.SPEC_NAMES)


# ── 3. the frequency BAND, which was never written (G111) ────────────────────


def _at(f_hz, peaking=7.0):
    import math
    return dict(MEAS, peaking_db=peaking, f_peak_oct=math.log2(f_hz / 2.5e9))


def test_a_peak_OUTSIDE_S3s_window_now_FAILS_however_the_target_was_set():
    """**The defect that shipped 4 of 16 coverage designs outside the window.**

    `S3_peaking` is a BAND. `S3_f_peak` is a DISTANCE FROM TARGET. So until
    `S3_f_peak_band` existed, nothing in any spec set required the peak to lie
    inside 1.25-2.5 GHz -- and with an off-centre target the distance row
    happily accepted peaks well past the ceiling.

    The measured case, verbatim from the coverage sweep: asked 2.253 GHz,
    delivered **3.174 GHz**, scored **45 of 45 corners PASS**.
    """
    m = R.margins(_at(3.174e9), 2.253e9)
    assert m["S3_f_peak"] > 0.0, (
        "premise check: the OLD row accepted this design, which is why the "
        "band row had to be added")
    assert m["S3_f_peak_band"] < 0.0, (
        "3.174 GHz is outside S3's 1.25-2.5 GHz window and must fail the band")


def test_the_band_is_positive_INSIDE_and_zero_AT_the_window_edges():
    for f in (1.25e9, 1.7677669529663687e9, 2.5e9):
        assert R.margins(_at(f), 1.7677669529663687e9)["S3_f_peak_band"] >= 0.0
    lo = R.margins(_at(1.25e9), 1.77e9)["S3_f_peak_band"]
    hi = R.margins(_at(2.5e9), 1.77e9)["S3_f_peak_band"]
    mid = R.margins(_at(1.7677669529663687e9), 1.77e9)["S3_f_peak_band"]
    assert lo == pytest.approx(0.0, abs=1e-9)
    assert hi == pytest.approx(0.0, abs=1e-9)
    assert mid == pytest.approx(0.5, abs=1e-3), "centre is half a window in"


def test_the_band_fails_BELOW_the_window_too_not_just_above():
    """Both edges, like `S3_peaking`. A one-sided band is not a band."""
    assert R.margins(_at(1.0e9), 1.77e9)["S3_f_peak_band"] < 0.0


def test_the_frequency_REQUEST_tolerance_is_tighter_than_the_WINDOW_half_width():
    """`S3_f_peak`'s 0.5 octaves is +/-41 % -- half the whole window -- so any
    design peaking anywhere in band satisfied any request. Measured: asked
    2.253 GHz, delivered 1.776 GHz, scored a pass."""
    assert R.TOL["S3_f_peak_match"] < R.TOL["S3_f_peak"]
    # the case that used to pass
    assert R.margins(_at(1.776e9), 2.253e9)["S3_f_peak"] > 0.0
    assert R.margins(_at(1.776e9), 2.253e9)["S3_f_peak_match"] < 0.0


def test_the_frequency_match_tolerance_is_NOT_tighter_than_f_peaks_PVT_EXCURSION():
    """Derived, not chosen: the peak's own excursion across the 45 mandated
    corners is 0.23-0.30 octaves, so a tolerance below ~0.15 is unmeetable at
    any target however well the design is centred."""
    assert R.TOL["S3_f_peak_match"] >= 0.30 / 2.0


def test_V6_replaces_the_old_row_rather_than_ADDING_to_it():
    """Scoring band + match + the old distance row would count one frequency
    miss three times in the shortfall sum."""
    assert "S3_f_peak" not in R.V6_SPECS
    assert {"S3_f_peak_band", "S3_f_peak_match"} <= set(R.V6_SPECS)
    assert "S3_f_peak" in R.V1_SPECS, "V1 must be untouched"


def test_the_SEARCH_and_the_VERIFICATION_sets_differ_only_in_the_HD3_ROW():
    """**Two HD3 rows, one spec, different conditions -- and only one of them
    is measurable at 135 points.**

    The slide says HD3 < -30 dB at 100 MHz; that is `S4_hd3`. `S4_hd3_nyq` is
    this project's harder self-imposed version at the operating point, measured
    30 dB apart on one design. `verify_full` runs ONE transient, at the slide's
    100 MHz, so the checklist can only produce `S4_hd3`.

    Substituting one for the other silently would be G32; dropping it silently
    would be G115 again. Naming a verification set is the only option that is
    neither -- and this pins that the two sets differ in nothing else.
    """
    assert set(R.V6_SPECS) - set(R.V6V_SPECS) == {"S4_hd3_nyq"}
    assert set(R.V6V_SPECS) - set(R.V6_SPECS) == {"S4_hd3"}
    assert len(R.V6_SPECS) == len(R.V6V_SPECS)


def test_V6_mirrors_the_peaking_axis_exactly():
    """Both axes end up with one band row and one request row. If they ever
    stop mirroring, one of them has drifted."""
    for band, match in (("S3_peaking", "S3_peaking_match"),
                        ("S3_f_peak_band", "S3_f_peak_match")):
        assert band in R.V6_SPECS and match in R.V6_SPECS


@pytest.mark.parametrize("specs", [R.V1_SPECS, R.V2_SPECS, R.V3_SPECS,
                                   R.V4_SPECS, R.V5_SPECS])
def test_the_new_frequency_rows_did_not_move_any_PUBLISHED_spec_set(specs):
    """Both rows are emitted unconditionally by `margins()`, so the only thing
    keeping V1-V5 fixed is that they do not NAME them. Pinned."""
    assert "S3_f_peak_band" not in specs and "S3_f_peak_match" not in specs


# ── 4. the verification must score every row it claims to (G115) ─────────────


def test_the_135_point_verification_SCORES_EVERY_V6V_ROW():
    """**The bug that let a 10.818 GHz peak verify at 45 of 45 corners.**

    `_rescore` computed `S3_f_peak` -- not even a member of `V6_SPECS` -- plus
    `S3_peaking_match`, then selected rows with
    `[k for k in V6_SPECS if k in m]`. That filter silently dropped
    `S3_f_peak_band` and `S3_f_peak_match`, so the verification scored 11 rows
    while reporting a 13-row result, and **never applied the frequency
    constraint at all**.

    Third instance in one session of a single shape: a set built by FILTERING
    loses members without saying so (G101, G106).
    """
    import math

    from nebula.experiments.exp_coverage import _rescore

    pt = {"ok": True, "cl_f": 3.26e-14, "corner": "tt", "vdd_scale": 1.0,
          "temp_c": 27.0,
          "margins": {k: 1.0 for k in R.V6V_SPECS
                      if not k.startswith(("S3_f_peak", "S3_peaking_match"))},
          "f_peak_oct_scored": math.log2(1.9e9 / 2.5e9),
          "peaking_db_scored": 7.0}
    out = _rescore([pt], 1.921e9, 7.0)[0]
    assert set(out["margins"]) == set(R.V6V_SPECS), (
        f"verification scored {len(out['margins'])} of {len(R.V6V_SPECS)} "
        f"rows; missing {sorted(set(R.V6V_SPECS) - set(out['margins']))}")


def test_a_peak_FAR_outside_the_window_cannot_verify_as_compliant():
    """The measured case, verbatim: 10.0 dB @ 1.921 GHz requested, 10.818 GHz
    delivered, previously verified at 45 of 45 corners."""
    import math

    from nebula.experiments.exp_coverage import _rescore

    pt = {"ok": True, "cl_f": 3.26e-14, "corner": "tt", "vdd_scale": 1.0,
          "temp_c": 27.0,
          "margins": {k: 1.0 for k in R.V6V_SPECS
                      if not k.startswith(("S3_f_peak", "S3_peaking_match"))},
          "f_peak_oct_scored": math.log2(10.818e9 / 2.5e9),
          "peaking_db_scored": 9.99}
    out = _rescore([pt], 1.921e9, 10.0)[0]
    assert out["feasible"] is False
    assert "S3_f_peak_band" in out["failed"]


def test_a_row_that_cannot_be_scored_RAISES_rather_than_being_dropped():
    """An assertion replaced the filter, because the filter was the defect."""
    import math

    import pytest as _pytest

    from nebula.experiments.exp_coverage import _rescore

    pt = {"ok": True, "cl_f": 3.26e-14, "corner": "tt", "vdd_scale": 1.0,
          "temp_c": 27.0,
          "margins": {"S3_nyq_boost": 1.0},          # almost everything absent
          "f_peak_oct_scored": math.log2(1.9e9 / 2.5e9),
          "peaking_db_scored": 7.0}
    with _pytest.raises(KeyError):
        _rescore([pt], 1.921e9, 7.0)


def test_an_UNMEASURABLE_EYE_makes_the_point_unscorable_not_a_crash():
    """**G107 inside the assertion.** The eye is computed from a pole-zero fit
    that is rejected under compression (G103: peaking and drive handling are
    one knob), so at some corners it genuinely cannot be measured. That point
    is UNSCORABLE — counted, blocking compliance, but not a code defect.
    """
    import math

    from nebula.experiments.exp_coverage import _rescore

    pt = {"ok": True, "cl_f": 3.26e-14, "corner": "sf", "vdd_scale": 1.05,
          "temp_c": 0.0,
          "margins": {k: 1.0 for k in R.V6V_SPECS
                      if k not in R.S8_SPECS
                      and not k.startswith(("S3_f_peak", "S3_peaking_match"))},
          "f_peak_oct_scored": math.log2(1.9e9 / 2.5e9),
          "peaking_db_scored": 7.0}
    out = _rescore([pt], 1.921e9, 7.0)[0]
    assert out["unscorable"] is True
    assert out["reward"] is None, "an unscorable point must not carry a number"
    assert out["feasible"] is False, "it still blocks compliance"


def test_a_MISSING_DEVICE_ROW_still_raises():
    """The eye may be absent; a device row may not. G115 was exactly a device
    row going missing behind a filter, and weakening the assertion to let the
    eye through must not weaken it for anything else."""
    import math

    import pytest as _pytest

    from nebula.experiments.exp_coverage import _rescore

    pt = {"ok": True, "cl_f": 3.26e-14, "corner": "tt", "vdd_scale": 1.0,
          "temp_c": 27.0,
          "margins": {k: 1.0 for k in R.V6V_SPECS
                      if k not in R.S8_SPECS and k != "S6_power"
                      and not k.startswith(("S3_f_peak", "S3_peaking_match"))},
          "f_peak_oct_scored": math.log2(1.9e9 / 2.5e9),
          "peaking_db_scored": 7.0}
    with _pytest.raises(KeyError, match="S6_power"):
        _rescore([pt], 1.921e9, 7.0)
