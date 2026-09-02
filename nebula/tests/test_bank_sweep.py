"""tests for `experiments/exp_bank_sweep` — the free re-score and its gates.

Nothing here runs SPICE. The whole point of the sweep is that the expensive part
happens **once** and every request after that is arithmetic, so the arithmetic is
what gets pinned.

Two gates are proved able to fail (CLAUDEwa.md §8 rule 10):

1. **the stale-row gate** — a request row that survived `_strip_request_rows`
   would be scored against the wrong target, silently. That is the G115 shape.
2. **the missing-row gate** — a margin dict that cannot fill all 13 of `SPECS`
   must raise rather than report a 12-row result as a 13-row one.
"""

from __future__ import annotations

import math

import pytest

import nebula.rl.reward_v1 as R
from nebula.experiments.exp_bank_sweep import (
    REQUEST_ROWS,
    SPECS,
    SweepRow,
    _strip_request_rows,
    coverage,
    is_compliant,
    rescore_margins,
)

NYQ = 2.5e9


def _passing_margins() -> dict:
    """Every non-request row of `SPECS`, comfortably satisfied."""
    return {k: 1.0 for k in SPECS if k not in REQUEST_ROWS}


def _row(peaking_db=9.0, f_peak_hz=1.9e9, ok=True, margins=None,
         corner="tt/1.00/27C", code=0) -> SweepRow:
    return SweepRow(
        i_rs=code // 8, i_cs=code % 8, code=code, corner=corner, ok=ok,
        peaking_db=peaking_db, f_peak_oct=math.log2(f_peak_hz / NYQ),
        margins=(_passing_margins() if margins is None else margins),
        eye_h_v=0.3, eye_w_ui=0.6, power_w=5e-3, hd3_nyq_dbc=-40.0)


# ── the strip ────────────────────────────────────────────────────────────────


def test_strip_removes_exactly_the_request_rows():
    m = _passing_margins() | {k: 99.0 for k in REQUEST_ROWS}
    out = _strip_request_rows(m)
    assert not (set(out) & set(REQUEST_ROWS))
    assert set(out) == set(_passing_margins())


def test_rescore_fills_every_spec_row():
    m = rescore_margins(_row(), 1.9e9, 9.0)
    assert all(k in m for k in SPECS)


def test_rescore_uses_the_request_it_is_given_not_the_one_measured():
    """The whole free-re-score claim, in one assertion."""
    row = _row(peaking_db=9.0, f_peak_hz=1.9e9)
    exact = rescore_margins(row, 1.9e9, 9.0)
    other = rescore_margins(row, 1.9e9, 4.0)
    assert exact["S3_peaking_match"] == pytest.approx(R.TOL["S3_peaking_match"])
    # 5 dB away from a 1.5 dB tolerance.
    assert other["S3_peaking_match"] == pytest.approx(R.TOL["S3_peaking_match"] - 5.0)


# ── gate 1: the stale row ────────────────────────────────────────────────────


@pytest.mark.parametrize("stale", REQUEST_ROWS)
def test_a_stale_request_row_raises_rather_than_being_scored(stale):
    """**The G115 gate.** Break `_strip_request_rows` and this is what catches it."""
    row = _row()
    row.margins = dict(row.margins) | {stale: 99.0}
    with pytest.raises(KeyError, match="G115"):
        rescore_margins(row, 1.9e9, 9.0)


def test_a_stale_row_would_otherwise_have_faked_a_pass():
    """Proves the gate is load-bearing, not decorative.

    Without the raise, a `S3_peaking_match` of +99 measured against a different
    target would mark a 5 dB miss compliant.
    """
    row = _row(peaking_db=9.0)
    assert not is_compliant(row, 1.9e9, 4.0)          # honestly scored: a miss
    row.margins = dict(row.margins) | {"S3_peaking_match": 99.0}
    with pytest.raises(KeyError):
        is_compliant(row, 1.9e9, 4.0)                 # not silently a pass


# ── gate 2: the missing row ──────────────────────────────────────────────────


def test_a_margin_short_of_a_spec_row_raises():
    m = _passing_margins()
    m.pop("S8_eye_h")
    with pytest.raises(KeyError, match="S8_eye_h"):
        rescore_margins(_row(margins=m), 1.9e9, 9.0)


def test_an_unscorable_row_is_never_compliant_and_never_raises():
    assert is_compliant(_row(ok=False, margins={}), 1.9e9, 9.0) is False


# ── compliance and coverage ──────────────────────────────────────────────────


def test_a_row_matching_its_request_is_compliant():
    assert is_compliant(_row(peaking_db=9.0, f_peak_hz=1.9e9), 1.9e9, 9.0)


def test_a_row_outside_the_peaking_tolerance_is_not():
    off = 9.0 + R.TOL["S3_peaking_match"] + 0.5
    assert not is_compliant(_row(peaking_db=off), 1.9e9, 9.0)


def test_a_row_outside_S3s_frequency_window_is_not_compliant():
    """The 10.818 GHz case G111/G115 let through."""
    assert not is_compliant(_row(f_peak_hz=10.818e9), 10.818e9, 9.0)


def test_coverage_counts_corners_not_points():
    rows = [_row(corner="tt/1.00/27C", code=0),
            _row(corner="tt/1.00/27C", code=1),
            _row(corner="ss/0.95/125C", code=0, peaking_db=99.0)]
    cov = coverage(rows, 1.9e9, 9.0)
    assert cov["n_corners"] == 2
    assert cov["n_served"] == 1
    assert cov["all_corners_served"] is False
    assert cov["unserved"] == ["ss/0.95/125C"]


def test_coverage_flags_a_corner_with_a_single_code():
    """No tuning margin left there — the thing an aggregate must not hide."""
    rows = [_row(corner="ff/0.95/125C", code=0),
            _row(corner="ff/0.95/125C", code=1, peaking_db=99.0),
            _row(corner="tt/1.00/27C", code=0),
            _row(corner="tt/1.00/27C", code=1)]
    cov = coverage(rows, 1.9e9, 9.0)
    assert cov["corners_with_one_code"] == ["ff/0.95/125C"]
    assert cov["n_codes_per_corner"]["tt/1.00/27C"] == 2
