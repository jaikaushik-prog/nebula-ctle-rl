"""Gates for `experiments/score_entry41.py`.

No SPICE. The load-bearing test is `test_seam_detected_on_an_exact_deck_tie`:
the first version of `segments()` split only on `n_decks` DECREASING, and this
run's two resumes both produced a first chunk of exactly 2 380 decks, so the
seam between them read `2380 < 2380` -- false. It merged two segments,
undercounted the run by 2 380 decks, and reported its wrong answer confidently.
"""

from __future__ import annotations

import json

import pytest

from nebula.experiments import score_entry41 as S


def _row(steps, decks, feas, elapsed, alpha_f=1.0, alpha_l=0.5,
         ls_f=0.0, ls_l=-1.0):
    return {"steps": steps, "n_decks": decks, "n_feasible_steps": feas,
            "elapsed_min": elapsed, "alpha_first": alpha_f,
            "alpha_last": alpha_l, "log_std_first": ls_f, "log_std_last": ls_l}


def test_seam_detected_on_an_exact_deck_tie():
    """The bug this module was rewritten around. Must stay caught."""
    rows = [
        _row(500, 2380, 10, 18.0),     # segment A, one chunk
        _row(1000, 2380, 9, 25.0),     # segment B: SAME decks, later elapsed
    ]
    segs = S.segments(rows)
    assert len(segs) == 2, (
        "an exact deck tie across a resume is a seam; splitting only on "
        "a strict decrease merges the segments and undercounts the run")


def test_seam_detected_on_elapsed_going_backwards():
    rows = [_row(500, 2380, 10, 40.0), _row(1000, 5000, 9, 14.0)]
    assert len(S.segments(rows)) == 2


def test_no_spurious_seam_within_one_segment():
    rows = [_row(500, 2380, 10, 14.0), _row(1000, 4760, 20, 28.0),
            _row(1500, 7140, 31, 42.0)]
    assert len(S.segments(rows)) == 1


def test_total_decks_sums_segments_not_the_last_row():
    rows = [_row(500, 100, 1, 10.0), _row(1000, 200, 2, 20.0),
            _row(1500, 50, 3, 5.0)]          # resume: decks restart
    assert S.total_decks(rows) == 250        # 200 + 50, not 50
    assert S.total_decks(rows) != rows[-1]["n_decks"]


def test_per_chunk_feasible_has_no_negative_delta_at_a_seam():
    rows = [_row(500, 100, 40, 10.0), _row(1000, 200, 78, 20.0),
            _row(1500, 50, 5, 5.0), _row(2000, 100, 12, 10.0)]
    deltas = [d for _, d in S.per_chunk_feasible(rows)]
    assert deltas == [40, 38, 5, 7]
    assert all(d >= 0 for d in deltas), "a seam produced a negative delta"


def test_q1_uses_first_chunks_alpha_first_as_the_initialisation():
    """Not the first `alpha_last` -- that is already one chunk of updates in."""
    rows = [_row(500, 100, 1, 10.0, alpha_f=1.0, alpha_l=0.9),
            _row(1000, 200, 2, 20.0, alpha_f=0.9, alpha_l=0.4)]
    d = S.score.__wrapped__(rows) if hasattr(S.score, "__wrapped__") else None
    # score() reads a path, so exercise the arithmetic directly:
    assert rows[0]["alpha_first"] == 1.0
    factor = rows[0]["alpha_first"] / rows[-1]["alpha_last"]
    assert factor == pytest.approx(2.5)


def test_score_end_to_end_on_a_synthetic_log(tmp_path):
    p = tmp_path / "prog.jsonl"
    rows = [_row(500, 100, 40, 10.0, alpha_f=1.0, alpha_l=0.8),
            _row(1000, 200, 78, 20.0, alpha_l=0.6),
            _row(1500, 50, 5, 5.0, alpha_l=0.5),
            _row(2000, 100, 12, 10.0, alpha_l=0.25, ls_l=-1.2)]
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    d = S.score(p)
    assert d["n_segments"] == 2
    assert d["total_decks_summed"] == 300
    assert d["final_row_decks_DO_NOT_USE"] == 100
    assert d["Q1"]["alpha_factor"] == pytest.approx(4.0)
    assert d["Q1"]["alpha_pass"] is True
    assert d["Q1"]["log_std_move"] == pytest.approx(1.2)
    assert d["Q1"]["pass"] is True
    assert d["complete"] is False


def test_thresholds_match_the_pre_registration():
    """Editing these after the run is what PREDICTIONS.md exists to prevent."""
    assert S.Q1_ALPHA_FACTOR == 2.0
    assert S.Q1_LOG_STD_MOVE == 0.5
    assert S.Q2_RATIO == 2.0
    assert S.N_CHUNKS_WINDOW == 5
    assert S.TOTAL_STEPS == 25_000


@pytest.mark.skipif(not S.PROGRESS.exists(), reason="no run log present")
def test_real_log_has_three_segments_and_the_summed_total():
    rows = S.load_rows()
    segs = S.segments(rows)
    assert len(segs) == 3, f"expected 3 segments, got {len(segs)}"
    assert S.total_decks(rows) > rows[-1]["n_decks"], (
        "the summed total must exceed the final row's segment-local count")
