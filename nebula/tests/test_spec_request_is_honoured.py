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
