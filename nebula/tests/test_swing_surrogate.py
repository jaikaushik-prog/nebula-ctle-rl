"""
tests/test_swing_surrogate.py — gates on `exp_swing_surrogate`
(`PREDICTIONS.md` entry 37).

WHAT IS GUARDED, AND WHICH FAILURE EACH GUARD IS FOR
------------------------------------------------------
1.  **THE TARGET IS THE LIMIT, NOT THE REQUIRED SWING.** The rejection message
    carries two millivolt numbers — `output swing 1614.7 mVpp exceeds the
    linear limit 1108.7 mVpp` — and reading the first one trains the model on
    the wrong quantity. It would still fit, still report clean errors, and be
    wrong by roughly the overdrive ratio. This project's second named failure
    mode: a wrong value that formats cleanly.
2.  **Dedup on `u`.** The same design is scored at four corners in three
    sweeps. Without dedup it lands in train and test, and every accuracy number
    is inflated — the oldest way to make a surrogate look good.
3.  **"Cannot be measured" is not "fails"** (G107). Q4's negative class is
    designs that failed ON SWING. A pole-zero fit failure says nothing about
    swing and must not be folded in to pad the class.
4.  **A collapsed harvest raises.** Entry 37 was written against 2 228 rows; if
    a reader change drops that to 30, the honest outcome is a stopped run, not
    a surrogate fitted to noise and reported as a result.
5.  **The verdict is mechanical**, and the NO branch must survive a good-looking
    random split: entry 37's whole point is that split A can pass while split B
    fails.

No SPICE, no sklearn fitting in most tests — the gates are on the reader, the
splitter and the decision rule.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from nebula.experiments import exp_swing_surrogate as S

REAL_MESSAGE = ("4 of 4 points unscorable; first: output swing 1614.7 mVpp "
                "exceeds the linear limit 1108.7 mVpp (vout_swing_v=1108.7 "
                "mVpp). The stage is compressing, so the AC/pole-zero model "
                "behind every number in this DeviceResult no longer describes "
                "it")
OLD_MESSAGE = ("4 of 4 points unscorable; first: output swing 979.6 mVpp "
               "exceeds the linear limit 542.2 mVpp")


# ---------------------------------------------------------------------------
# 1. the target is the LIMIT, not the required swing
# ---------------------------------------------------------------------------

def test_the_parsed_target_is_the_limit_not_the_required_swing():
    """Both numbers are millivolts and both parse. Only one is the target."""
    assert S._limit_mv(REAL_MESSAGE) == 1108.7
    assert S._limit_mv(REAL_MESSAGE) != 1614.7


def test_the_older_message_form_parses_to_the_same_quantity():
    assert S._limit_mv(OLD_MESSAGE) == 542.2


def test_a_reason_without_a_swing_number_yields_nothing():
    assert S._limit_mv("4 of 4 points unscorable; first: pole-zero fit failed") is None
    assert S._limit_mv(None) is None
    assert S._limit_mv("") is None


# ---------------------------------------------------------------------------
# 2. dedup
# ---------------------------------------------------------------------------

def _write_jsonl(tmp_path, rows, name="coverage_run.jsonl"):
    p = tmp_path / name
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return p


def test_the_same_design_seen_many_times_contributes_once(tmp_path):
    u = [0.5] * 7
    _write_jsonl(tmp_path, [{"u": u, "reason": REAL_MESSAGE}] * 5)
    h = S.harvest(tmp_path)
    assert len(h["rows"]) == 1
    assert h["per_file"]["coverage_run.jsonl"] == 5


def test_different_designs_are_kept_apart(tmp_path):
    _write_jsonl(tmp_path, [{"u": [0.5] * 7, "reason": REAL_MESSAGE},
                            {"u": [0.4] * 7, "reason": OLD_MESSAGE}])
    rows = S.harvest(tmp_path)["rows"]
    assert len(rows) == 2
    assert sorted(r["limit_v"] for r in rows) == [0.5422, 1.1087]


def test_the_harvest_reads_scan_artifacts_too(tmp_path):
    (tmp_path / "topk_scan_fake.json").write_text(json.dumps({
        "requests": [{"candidates": [{"u": [0.3] * 7, "reason": OLD_MESSAGE}]}]
    }), encoding="utf-8")
    rows = S.harvest(tmp_path)["rows"]
    assert len(rows) == 1 and rows[0]["limit_v"] == 0.5422


def test_a_row_without_a_design_vector_is_skipped(tmp_path):
    _write_jsonl(tmp_path, [{"reason": REAL_MESSAGE}])
    assert S.harvest(tmp_path)["rows"] == []


# ---------------------------------------------------------------------------
# 3. G107: the negative class is SWING failures only
# ---------------------------------------------------------------------------

def test_q4_negatives_are_swing_failures_not_every_failure(tmp_path):
    (tmp_path / "topk_scan_fake.json").write_text(json.dumps({"requests": [{
        "candidates": [
            {"u": [0.5] * 7, "feasible": True},
            {"u": [0.4] * 7, "feasible": False, "reason": OLD_MESSAGE},
            {"u": [0.3] * 7, "feasible": False,
             "reason": "4 of 4 points unscorable; first: pole-zero fit failed"},
        ]}]}), encoding="utf-8")
    rows = S._verdict_rows(tmp_path)
    assert [r["label"] for r in rows] == [1, 0]
    assert len(rows) == 2, "a pole-zero failure is not evidence about swing"


# ---------------------------------------------------------------------------
# 4. features
# ---------------------------------------------------------------------------

def test_features_match_their_names_and_are_finite():
    f = S.features([0.5] * 7)
    assert len(f) == len(S.FEATURE_NAMES)
    assert np.all(np.isfinite(f))


def test_features_depend_only_on_the_design_vector():
    """No measurement may reach an input, or the model predicts itself."""
    a = S.features([0.42] * 7)
    b = S.features([0.42] * 7)
    assert np.allclose(a, b)
    assert not np.allclose(a, S.features([0.43] * 7))


# ---------------------------------------------------------------------------
# 5. a collapsed harvest stops the run
# ---------------------------------------------------------------------------

def test_a_collapsed_harvest_raises_instead_of_fitting_noise(tmp_path):
    _write_jsonl(tmp_path, [{"u": [i / 100] * 7, "reason": OLD_MESSAGE}
                            for i in range(20)])
    with pytest.raises(RuntimeError, match="2 228|bug in the reader"):
        S.run(root=tmp_path)


# ---------------------------------------------------------------------------
# 6. the verdict is mechanical
# ---------------------------------------------------------------------------

def _res(*, a_err=0.06, b_err=0.05, rho=0.99, auc=0.79) -> dict:
    return {"splits": {
        "A_random": {"gbr": {"median_rel_err": a_err, "spearman": 0.9,
                             "p90_rel_err": 0.2, "median_abs_err_mv": 30.0,
                             "n": 669}},
        "B_transfer_to_policy_designs": {
            "gbr": {"median_rel_err": b_err, "spearman": rho,
                    "p90_rel_err": 0.2, "median_abs_err_mv": 30.0, "n": 245}}},
        "q4": {"auc": auc}}


def test_the_go_branch_needs_both_error_and_ordering():
    v = S._verdict(_res())
    assert v["Q2_transfer_error"] and v["Q3_transfer_ordering"]
    assert v["call"].startswith("GO")


def test_ordering_without_volts_is_only_a_rank_shaped_option():
    v = S._verdict(_res(b_err=0.40))
    assert not v["Q2_transfer_error"] and v["Q3_transfer_ordering"]
    assert v["call"].startswith("PARTIAL") and "RANK-SHAPED" in v["call"]


def test_a_good_random_split_cannot_rescue_a_failed_transfer():
    """Entry 37's whole point: split A passing proves nothing."""
    v = S._verdict(_res(a_err=0.02, b_err=0.60, rho=0.10))
    assert v["Q1_random_split"] is True
    assert v["call"].startswith("NO")
    assert "G110" in v["call"], "the NO branch must forbid a rescue fit"


def test_a_missed_q4_is_appended_to_every_branch():
    for kw in ({}, {"b_err": 0.40}, {"b_err": 0.60, "rho": 0.1}):
        v = S._verdict(_res(auc=0.55, **kw))
        assert not v["Q4_decision_utility"]
        assert "Q4 MISSED" in v["call"]


def test_a_missing_auc_is_a_miss_not_a_pass():
    v = S._verdict(_res(auc=None))
    assert v["Q4_decision_utility"] is False


def test_the_thresholds_are_entry_37s():
    assert (S.Q1_MAX_REL_ERR, S.Q2_MAX_REL_ERR) == (0.15, 0.25)
    assert S.Q3_MIN_SPEARMAN == 0.80
    assert S.Q4_MIN_AUC == 0.75


# ---------------------------------------------------------------------------
# 7. the artifact says what it is
# ---------------------------------------------------------------------------

def test_the_result_is_stamped_as_a_surrogate(tmp_path):
    """`is_analytic` exists on the analytic env for the same reason: a consumer
    must not be able to mistake a predicted number for a measured one."""
    d = json.loads((S.RESULTS).read_text(encoding="utf-8"))
    assert d["is_surrogate"] is True
