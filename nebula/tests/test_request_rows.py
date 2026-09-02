"""tests for `reward_v1.request_rows` — the three request-dependent spec rows.

**Why this helper exists (CLAUDEwa.md §8 rule 9: exactly ONE definition).**
`S3_f_peak_band`, `S3_f_peak_match` and `S3_peaking_match` were computed in two
places from the same two primitives: inside `reward_v1.margins`, and again
inside `exp_coverage._rescore`, which re-scores an already-measured point
against a different target. G115 is what a second definition cost the last time
— `_rescore` silently dropped two of the three rows and a design peaking at
**10.818 GHz**, 4.3x outside S3's window, verified at 45 of 45 corners.

Row 4ab needs a THIRD caller: the bank sweep re-scores one (code, corner)
measurement against all 16 requests for free, which is only sound if "re-score
against a different target" has one implementation. This file pins it.
"""

from __future__ import annotations

import math

import pytest

from nebula.rl import reward_v1 as R

#: 2.5 GHz is the octave origin every frequency quantity in this project uses.
NYQ = 2.5e9


def _oct(f_hz: float) -> float:
    return math.log2(f_hz / NYQ)


def test_returns_exactly_the_three_request_rows():
    out = R.request_rows(_oct(1.9e9), 9.0, 1.9e9, 9.0)
    assert set(out) == {"S3_f_peak_band", "S3_f_peak_match", "S3_peaking_match"}


def test_peaking_row_is_omitted_when_no_peaking_is_requested():
    """`margins` emits it only when asked, so V1-V4 stay untouched."""
    out = R.request_rows(_oct(1.9e9), 9.0, 1.9e9, None)
    assert set(out) == {"S3_f_peak_band", "S3_f_peak_match"}


def test_an_exact_hit_leaves_the_full_tolerance_as_margin():
    out = R.request_rows(_oct(1.9e9), 9.0, 1.9e9, 9.0)
    assert out["S3_f_peak_match"] == pytest.approx(R.TOL["S3_f_peak_match"])
    assert out["S3_peaking_match"] == pytest.approx(R.TOL["S3_peaking_match"])


def test_a_miss_of_exactly_one_tolerance_lands_on_zero():
    """The sign convention: positive is satisfied, zero is exactly at the limit."""
    tol_db = R.TOL["S3_peaking_match"]
    out = R.request_rows(_oct(1.9e9), 9.0 + tol_db, 1.9e9, 9.0)
    assert out["S3_peaking_match"] == pytest.approx(0.0)

    tol_oct = R.TOL["S3_f_peak_match"]
    out = R.request_rows(_oct(1.9e9) + tol_oct, 9.0, 1.9e9, 9.0)
    assert out["S3_f_peak_match"] == pytest.approx(0.0)


def test_the_match_rows_are_symmetric_in_the_direction_of_the_miss():
    hi = R.request_rows(_oct(1.9e9), 11.0, 1.9e9, 9.0)["S3_peaking_match"]
    lo = R.request_rows(_oct(1.9e9), 7.0, 1.9e9, 9.0)["S3_peaking_match"]
    assert hi == pytest.approx(lo)


@pytest.mark.parametrize("f_hz,inside", [
    (1.25e9, True), (1.9e9, True), (2.5e9, True),
    (1.20e9, False), (2.6e9, False), (10.818e9, False),
])
def test_the_band_row_signs_S3s_window(f_hz, inside):
    """**This is the G115 row.** Positive inside 1.25-2.5 GHz, negative outside.

    10.818 GHz is not an arbitrary case: it is the design that verified 45 of 45
    while this row was being silently dropped.
    """
    band = R.request_rows(_oct(f_hz), 9.0, 1.9e9, 9.0)["S3_f_peak_band"]
    assert (band >= 0.0) is inside, f"{f_hz / 1e9:g} GHz -> band {band}"


def test_the_band_row_does_not_depend_on_the_request():
    """It is a property of the circuit, so re-scoring must not move it."""
    f_oct = _oct(2.1e9)
    a = R.request_rows(f_oct, 9.0, 1.30e9, 4.0)["S3_f_peak_band"]
    b = R.request_rows(f_oct, 9.0, 2.45e9, 12.0)["S3_f_peak_band"]
    assert a == pytest.approx(b)


# ── the rule-9 gate: margins() and request_rows() must not drift apart ───────


@pytest.mark.parametrize("f_hz,pk,tgt_f,tgt_pk", [
    (1.9e9, 9.0, 1.9e9, 9.0),
    (2.3e9, 4.2, 1.387e9, 10.0),
    (1.1e9, 13.0, 2.253e9, 6.0),
])
def test_margins_agrees_with_request_rows_row_for_row(f_hz, pk, tgt_f, tgt_pk):
    """`margins` must DELEGATE, not reimplement.

    Deliberately break `request_rows` and this goes red — which is the whole
    point of factoring it out (rule 10).
    """
    meas = {
        "g_dc_db": 0.0, "peaking_db": pk, "f_peak_oct": _oct(f_hz),
        "nyq_boost_db": 5.0, "inoise_vrms": 3e-4, "power_w": 5e-3,
        "pair_margin_v": 0.3, "tail_margin_v": 0.2,
    }
    m = R.margins(meas, tgt_f, target_peaking_db=tgt_pk)
    rr = R.request_rows(_oct(f_hz), pk, tgt_f, tgt_pk)
    for k, v in rr.items():
        assert m[k] == pytest.approx(v), k
