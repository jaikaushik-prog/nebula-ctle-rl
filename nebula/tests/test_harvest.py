"""Gates for `experiments/exp_harvest.py` -- the hindsight-relabelled
demonstration set. **NO SPICE: this module only reads files.**

What must not be allowed to go wrong here, in order of how much it would cost:

1. **A sweep-edge design entering the training set.** 41 790 of the logged
   rows are recorded G44 rejects. Cloning one teaches a policy that "to achieve
   4 dB at 19.95 GHz, output this" is a valid answer -- the exact pathology
   that broke SAC (G130).
2. **A row vanishing silently.** `rl_smoke_run_v0.jsonl` carries 765 rows in an
   older
   action space; dropping them is right, dropping them *quietly* is G115.
3. **Reading the lattice peak instead of the interpolated one** (G108) -- a
   demonstration set built on the grid teaches a policy to aim at a grid.
4. **De-duplicating on `design_id`** (G124), which does not join across
   artifact boundaries.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import numpy as np
import pytest

import nebula.experiments.exp_harvest as H


# ---------------------------------------------------------------------------
# the contract
# ---------------------------------------------------------------------------

def test_the_log_list_is_enumerated_not_globbed():
    """G101: a set defined by what it MATCHES grows silently. A new run log
    joining the training set is a decision, not a side effect."""
    src = Path(H.__file__).read_text(encoding="utf-8")
    # the word "globbed" appears in the comment explaining why it is not; the
    # check is on the CODE, which must never call glob.
    assert "glob.glob" not in src and "Path.glob" not in src
    assert ".glob(" not in src
    assert len(H.LOGS) == 13
    assert len(set(H.LOGS)) == len(H.LOGS), "a log is listed twice"


def test_the_gated_logs_are_the_ones_that_went_through_evaluator_evaluate():
    """The distinction is load-bearing: only these carry `validate`'s verdict.
    Mislabelling an ungated log as gated would claim a check that never ran."""
    assert H.GATED_LOGS == frozenset(H.LOGS[:7])
    for name in H.GATED_LOGS:
        assert any(k in name for k in
                   ("baselines", "budget_ladder", "rl_smoke", "corner_rl")), name
    for name in set(H.LOGS) - H.GATED_LOGS:
        assert ("coverage" in name or "hybrid" in name
                or "joint_search" in name or "linear_pareto" in name)


def test_the_spec_box_is_S3s_stated_range_and_nothing_else():
    """Not a quality filter and not a tolerance. If these drift from the slide,
    the demonstration set silently stops describing the competition."""
    assert (H.PEAKING_LO_DB, H.PEAKING_HI_DB) == (3.0, 12.0)
    assert (H.F_PEAK_LO_HZ, H.F_PEAK_HI_HZ) == (1.25e9, 2.5e9)
    assert H.F_REF_HZ == 2.5e9                     # Nyquist, the octave origin


# ---------------------------------------------------------------------------
# the gate is READ, not recomputed
# ---------------------------------------------------------------------------

def test_a_recorded_sweep_edge_row_is_DROPPED():
    """The single most important line in the module."""
    keep, why = H.gate_verdict(
        {"invalid_reason": "the reported peak IS the sweep edge: f_pk 1.995e10"},
        gated=True)
    assert keep is False and "sweep_edge" in why


def test_the_drop_reason_is_BUCKETED_not_echoed():
    """`validate` embeds measured millivolts in its message, so echoing makes
    every row its own category and the breakdown becomes 40 000 buckets of
    one. A histogram that cannot be read is the same as no histogram."""
    a, _ = H.gate_verdict({"invalid_reason":
                           "out of saturation (tail -14.6 mV of vds - vdsat)"},
                          gated=True)
    b_keep, b_why = H.gate_verdict(
        {"invalid_reason": "out of saturation (tail -3.2 mV of vds - vdsat)"},
        gated=True)
    _, a_why = H.gate_verdict({"invalid_reason":
                               "out of saturation (tail -14.6 mV of vds)"},
                              gated=True)
    assert a is False and b_keep is False
    assert a_why == b_why == "out of saturation (headroom-only)"


def test_a_clean_gated_row_is_KEPT():
    keep, why = H.gate_verdict({"invalid_reason": None}, gated=True)
    assert keep is True and why == "valid"


def test_an_ungated_row_is_kept_but_LABELLED_as_ungated():
    """Honesty about which rows were never checked. The artifact reports the
    count so a reader can discount them."""
    keep, why = H.gate_verdict({}, gated=False)
    assert keep is True and why == "ungated log"


def test_an_ok_false_row_is_dropped_on_either_kind_of_log():
    for gated in (True, False):
        keep, _ = H.gate_verdict({"ok": False}, gated=gated)
        assert keep is False


def test_the_module_does_not_reimplement_the_G44_rule():
    """Rule 9. The verdict was computed by `evaluator.validate` at simulation
    time; a second copy here would be a third definition of validity."""
    src = Path(H.__file__).read_text(encoding="utf-8")
    code = src[src.index('"""', src.index('"""') + 3) + 3:]
    for forbidden in ("peak_is_sweep_edge", "g_top_db", "PEAK_MARGIN_DB",
                      "has_interior_peak"):
        assert forbidden not in code


# ---------------------------------------------------------------------------
# the achieved spec -- hindsight's whole content
# ---------------------------------------------------------------------------

def test_the_INTERPOLATED_peak_wins(monkeypatch):
    """G108: S3's 1.2500 GHz floor falls between two `ac dec 50` samples, so
    the lattice reading rounds a 1.6 %-wide band of failures into passes. A
    demonstration set on the lattice teaches a policy to aim at a grid."""
    row = {"meas": {"peaking_db": 8.0, "peaking_db_interp": 8.4,
                    "f_peak_oct": -0.5, "f_peak_oct_interp": -0.4}}
    pk, f = H.achieved_spec(row)
    assert pk == 8.4
    assert f == pytest.approx(2.5e9 * 2.0 ** -0.4)


def test_the_lattice_peak_is_used_only_when_there_is_no_interpolated_one():
    row = {"meas": {"peaking_db": 8.0, "f_peak_oct": -1.0}}
    pk, f = H.achieved_spec(row)
    assert pk == 8.0 and f == pytest.approx(1.25e9)


def test_a_flat_row_without_meas_still_yields_its_achieved_spec():
    """The coverage and hybrid logs record the spec at the top level."""
    pk, f = H.achieved_spec({"peaking_db": 6.5, "f_peak_hz": 1.8e9})
    assert pk == 6.5 and f == 1.8e9


def test_a_row_with_no_achieved_spec_returns_None_rather_than_a_default():
    """Standing rule 1: a missing value fails loudly, it does not become 0.0."""
    assert H.achieved_spec({}) == (None, None)


def test_the_octave_conversion_round_trips_at_nyquist():
    pk, f = H.achieved_spec({"meas": {"peaking_db": 5.0, "f_peak_oct": 0.0}})
    assert f == pytest.approx(H.F_REF_HZ)


# ---------------------------------------------------------------------------
# the box
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pk,f,expected", [
    (3.0, 1.25e9, True), (12.0, 2.5e9, True), (7.0, 1.8e9, True),
    (2.99, 1.8e9, False), (12.01, 1.8e9, False),
    (7.0, 1.24e9, False), (7.0, 2.51e9, False),
    (4.0, 19.95e9, False),           # the sweep-edge family, by frequency
])
def test_in_spec_box_boundaries(pk, f, expected):
    assert H.in_spec_box(pk, f) is expected


def test_the_box_excludes_every_sweep_edge_design_by_construction():
    """Worth pinning: for the DEMONSTRATION set the box subsumes the frequency
    half of the gate, which is why the ungated logs are usable at all."""
    assert H.in_spec_box(4.0, 19.952620e9) is False
    assert H.F_PEAK_HI_HZ < 1.8e10                 # the gate's own upper limit


# ---------------------------------------------------------------------------
# reading rows
# ---------------------------------------------------------------------------

def _write(tmp_path, name, rows):
    p = tmp_path / name
    text = "\n".join(json.dumps(r) for r in rows)
    if name.endswith(".gz"):
        with gzip.open(p, "wt", encoding="utf-8") as fh:
            fh.write(text)
    else:
        p.write_text(text, encoding="utf-8")
    return p


def test_a_row_in_an_OLDER_ACTION_SPACE_is_flagged_not_dropped(tmp_path):
    """G115: a set that loses members without saying so. `rl_smoke_run_v0`
    carries 765 such rows and they must appear in the drop breakdown."""
    p = _write(tmp_path, "x.jsonl", [{"u": [0.5] * 5, "meas": {}},
                                     {"u": [0.5] * 7, "meas": {}}])
    rows = list(H.iter_rows(p))
    assert len(rows) == 2
    assert rows[0]["_wrong_dim"] == 5
    assert "_wrong_dim" not in rows[1]


def test_the_wrong_dimension_rows_reach_the_drop_breakdown(tmp_path):
    _write(tmp_path, "corner_rl_run.jsonl",
           [{"u": [0.5] * 5, "meas": {"peaking_db": 7.0, "f_peak_oct": -0.5}}])
    out = H.harvest(("corner_rl_run.jsonl",), here=tmp_path)
    assert out["n_unique_demonstrations"] == 0
    assert any("wrong action dimension" in k for k in out["drop_reasons"])


def test_rows_without_a_u_are_skipped(tmp_path):
    p = _write(tmp_path, "x.jsonl", [{"event": "start"}, {"u": None}])
    assert list(H.iter_rows(p)) == []


def test_a_missing_log_is_recorded_not_skipped(tmp_path):
    out = H.harvest(("nope.jsonl",), here=tmp_path)
    assert out["per_log"][0]["missing"] is True


# ---------------------------------------------------------------------------
# harvesting
# ---------------------------------------------------------------------------

def _row(u, pk, f_hz, invalid=None):
    import math
    r = {"u": list(u), "meas": {"peaking_db_interp": pk,
                                "f_peak_oct_interp": math.log2(f_hz / 2.5e9)}}
    if invalid:
        r["invalid_reason"] = invalid
    return r


def test_harvest_dedups_on_u_and_keeps_every_source(tmp_path):
    """G124: `design_id` does not join across artifact boundaries, so an
    id-keyed dedup would keep the same design twice under two ids."""
    _write(tmp_path, "corner_rl_run.jsonl", [
        dict(_row([0.3] * 7, 7.0, 1.8e9), design_id="aaaa"),
        dict(_row([0.3] * 7, 7.0, 1.8e9), design_id="bbbb"),   # same u, new id
        _row([0.4] * 7, 8.0, 2.0e9)])
    out = H.harvest(("corner_rl_run.jsonl",), here=tmp_path)
    assert out["n_unique_demonstrations"] == 2


def test_harvest_EXCLUDES_a_sweep_edge_row_end_to_end(tmp_path):
    """The whole reason the gate had to come before the relabelling."""
    _write(tmp_path, "corner_rl_run.jsonl", [
        _row([0.3] * 7, 7.0, 1.8e9),
        _row([0.9] * 7, 4.0, 1.9e9,
             invalid="the reported peak IS the sweep edge: f_pk 1.995e10")])
    out = H.harvest(("corner_rl_run.jsonl",), here=tmp_path)
    assert out["n_unique_demonstrations"] == 1
    assert any("sweep_edge" in k for k in out["drop_reasons"])


def test_harvest_excludes_designs_outside_the_requestable_box(tmp_path):
    _write(tmp_path, "corner_rl_run.jsonl", [
        _row([0.3] * 7, 7.0, 1.8e9),
        _row([0.5] * 7, 7.0, 9.0e9),               # valid, just not requestable
        _row([0.6] * 7, 20.0, 1.8e9)])
    out = H.harvest(("corner_rl_run.jsonl",), here=tmp_path)
    assert out["n_unique_demonstrations"] == 1
    assert out["drop_reasons"]["outside the requestable spec box"] == 2


def test_harvest_counts_ungated_demonstrations_separately(tmp_path):
    _write(tmp_path, "corner_rl_run.jsonl", [_row([0.3] * 7, 7.0, 1.8e9)])
    _write(tmp_path, "hybrid_run.jsonl", [_row([0.4] * 7, 8.0, 2.0e9)])
    out = H.harvest(("corner_rl_run.jsonl", "hybrid_run.jsonl"), here=tmp_path)
    assert out["n_unique_demonstrations"] == 2
    assert out["n_from_ungated_logs"] == 1


# ---------------------------------------------------------------------------
# coverage -- the number that says whether BC can answer an arbitrary request
# ---------------------------------------------------------------------------

def test_coverage_grid_reports_an_empty_corner(tmp_path):
    """A dataset of 50 000 pairs is worthless for spec conditioning if they all
    sit in one place. This is the check that would catch that."""
    demos = [{"peaking_db": 3.1, "f_peak_hz": 1.26e9} for _ in range(100)]
    c = H.coverage_grid(demos, n_pk=10, n_f=10)
    assert c["n_occupied"] == 1 and c["min_count"] == 0
    assert c["fraction"] == pytest.approx(0.01)


def test_coverage_grid_is_full_when_the_box_is_spanned():
    demos = []
    for i in range(10):
        for j in range(10):
            demos.append({"peaking_db": 3.0 + (i + 0.5) * 0.9,
                          "f_peak_hz": 1.25e9 * 2.0 ** ((j + 0.5) / 10.0)})
    c = H.coverage_grid(demos, n_pk=10, n_f=10)
    assert c["n_occupied"] == 100 and c["min_count"] == 1


def test_coverage_grid_handles_an_empty_set():
    assert H.coverage_grid([])["n_occupied"] == 0


# ---------------------------------------------------------------------------
# the real artifact
# ---------------------------------------------------------------------------

def test_the_real_harvest_spans_the_whole_requestable_box():
    """The measured claim this step exists to make. If a future log narrows the
    demonstration set, this reddens rather than a policy quietly losing the
    ability to answer part of the spec range."""
    if not H.RESULTS.exists():
        pytest.skip("harvest has not been run in this checkout")
    d = json.loads(H.RESULTS.read_text(encoding="utf-8"))
    assert d["n_unique_demonstrations"] >= 30_000
    assert d["coverage"]["n_occupied"] == d["coverage"]["n_cells"]
    assert d["coverage"]["min_count"] >= 10
    assert any("sweep_edge" in k for k in d["drop_reasons"])


def test_the_dataset_and_the_summary_agree():
    if not (H.DATASET.exists() and H.RESULTS.exists()):
        pytest.skip("harvest has not been run in this checkout")
    d = json.loads(H.RESULTS.read_text(encoding="utf-8"))
    z = np.load(H.DATASET)
    assert len(z["u"]) == d["n_unique_demonstrations"]
    assert z["u"].shape[1] == H.N_ACTIONS
    assert int((~z["gated"]).sum()) == d["n_from_ungated_logs"]
    # every stored demonstration is inside the box it claims to be in
    assert bool(np.all((z["peaking_db"] >= H.PEAKING_LO_DB)
                       & (z["peaking_db"] <= H.PEAKING_HI_DB)))
    assert bool(np.all((z["f_peak_hz"] >= H.F_PEAK_LO_HZ)
                       & (z["f_peak_hz"] <= H.F_PEAK_HI_HZ)))
    assert bool(np.all((z["u"] >= 0.0) & (z["u"] <= 1.0)))
