"""
tests/test_refine_widened.py — gates on `exp_refine_widened`, entry 57's arm F.

WHY EACH GUARD EXISTS
----------------------
1.  **The spread must be the CONTROL's, not a chosen one.** The whole claim of
    the entry is that `SPREAD` was derived (`1/sqrt(3)` is the standard
    deviation of arm B's own uniform action) rather than picked because it
    worked. A test pins the value so a later "small adjustment" is a red test
    and not a silent tuning of the result.
2.  **Arm F must be neither of the arms it sits between.** Sampling the
    policy's own sigma is arm D; ignoring the policy is arm B. F is the
    policy's MEAN with B's spread, and if it collapsed into either the entry
    would be measuring a question that has already been answered.
3.  **The action must stay in the box every other arm lives in.** The env
    squashes to `[-1, 1]`; an actor emitting outside it would be exploring a
    space the control cannot reach, and F's win would be an artefact of range.
4.  **The prior arms are READ, never re-run.** F is scored paired against A, B
    and D on the same request from the same start. Recomputing them here would
    be a second measurement of the same thing under different conditions, and
    the missing-artifact path must say so rather than silently running fewer
    requests.
5.  **The scorer must implement the registered thresholds**, including the
    expected null: a tie must be reported as a tie, not rounded into a win.

No SPICE and no checkpoint: the actor is tested against a stub policy.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from nebula.experiments import exp_refine_widened as W


class _StubDist:
    def __init__(self, mean):
        self.mean = mean

    def sample(self):
        raise AssertionError(
            "arm F must not call .sample() -- sampling the policy's own sigma "
            "is arm D, which entry 48 already measured")


class _StubNet:
    """A policy whose mean is a fixed vector, so the actor is testable alone."""

    def __init__(self, mean):
        import torch

        self._m = torch.as_tensor(mean, dtype=torch.float32).unsqueeze(0)

    def distribution(self, o):
        return _StubDist(self._m)


# ─────────────────────────────────────────────────────────────────────────────
# Guard 1 — the spread is the control's
# ─────────────────────────────────────────────────────────────────────────────

def test_the_spread_is_the_standard_deviation_of_the_control_arm():
    # Uniform on [-1, 1] has variance 1/3. Arm B IS that distribution, so this
    # is the one value that equalises diversity between F and B.
    assert W.SPREAD == pytest.approx(1.0 / math.sqrt(3.0))
    assert W.SPREAD == pytest.approx(0.5773502691896258)


def test_the_spread_matches_a_measured_uniform_sample():
    # The derivation restated as a measurement, so the constant cannot drift
    # away from the thing it claims to be.
    rng = np.random.default_rng(0)
    assert float(np.std(rng.uniform(-1.0, 1.0, size=2_000_000))) == \
        pytest.approx(W.SPREAD, abs=2e-3)


# ─────────────────────────────────────────────────────────────────────────────
# Guards 2 and 3 — arm F is its own arm, inside the box
# ─────────────────────────────────────────────────────────────────────────────

def test_the_actor_centres_on_the_policy_mean():
    net = _StubNet([0.2, -0.4, 0.0, 0.1, -0.1, 0.3, 0.0])
    act = W.widened_actor(net)
    rng = np.random.default_rng(11)
    got = np.mean([act(np.zeros(18), rng) for _ in range(4000)], axis=0)
    assert np.allclose(got, [0.2, -0.4, 0.0, 0.1, -0.1, 0.3, 0.0], atol=0.05)


def test_the_actor_does_not_sample_the_policys_own_sigma():
    # Guard 2. `_StubDist.sample` raises: calling it would make this arm D.
    net = _StubNet([0.0] * 7)
    W.widened_actor(net)(np.zeros(18), np.random.default_rng(1))


def test_the_spread_is_the_controls_and_not_the_policys():
    net = _StubNet([0.0] * 7)
    act = W.widened_actor(net)
    rng = np.random.default_rng(5)
    xs = np.array([act(np.zeros(18), rng) for _ in range(6000)])
    # Centred at 0 the clip is nearly inactive, so the realised SD should sit
    # just under the control's -- an order of magnitude above the policy's
    # 0.0487 on `rs`, which is the entire mechanism under test.
    sd = float(np.std(xs))
    assert 0.45 < sd <= W.SPREAD + 1e-9
    assert sd > 10 * 0.0487


def test_every_action_stays_inside_the_box(monkeypatch):
    # Guard 3. A mean near the edge plus wide noise must still be clipped.
    net = _StubNet([0.98] * 7)
    act = W.widened_actor(net)
    rng = np.random.default_rng(7)
    xs = np.array([act(np.zeros(18), rng) for _ in range(2000)])
    assert xs.max() <= 1.0 and xs.min() >= -1.0


def test_the_actor_is_reproducible_for_a_given_rng():
    net = _StubNet([0.1] * 7)
    a = W.widened_actor(net)(np.zeros(18), np.random.default_rng(3))
    b = W.widened_actor(net)(np.zeros(18), np.random.default_rng(3))
    assert np.allclose(a, b)


# ─────────────────────────────────────────────────────────────────────────────
# Guard 4 — the prior arms are read, and a missing one stops the run
# ─────────────────────────────────────────────────────────────────────────────

def test_a_missing_prior_artifact_stops_rather_than_running_fewer_requests(
        monkeypatch, tmp_path):
    monkeypatch.setattr(W, "CONTROL_RESULTS", tmp_path / "nope.json")
    with pytest.raises(SystemExit, match="missing"):
        W.prior_arms()


def test_prior_arms_joins_the_two_entries_on_request_index(monkeypatch, tmp_path):
    import json

    ctrl = tmp_path / "c.json"
    samp = tmp_path / "s.json"
    ctrl.write_text(json.dumps({"rows": [
        {"index": 3, "A_delta": 1.0, "A_crossed": False, "A_decks": 30,
         "B_delta": 2.0, "B_crossed": True, "B_decks": 30}]}))
    samp.write_text(json.dumps({"rows": [
        {"index": 3, "D_delta": 1.5, "D_crossed": True, "D_decks": 29}]}))
    monkeypatch.setattr(W, "CONTROL_RESULTS", ctrl)
    monkeypatch.setattr(W, "SAMPLED_RESULTS", samp)
    got = W.prior_arms()
    assert set(got) == {3}
    assert got[3]["D_crossed"] is True and got[3]["B_crossed"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Guard 5 — the scorer implements the registered thresholds
# ─────────────────────────────────────────────────────────────────────────────

def _rows(f_cross, b_cross, d_cross, n=58, decks=30.0):
    out = []
    for i in range(n):
        out.append({
            "index": i, "same_start": True,
            "A_delta": 0.0, "A_crossed": False, "A_decks": decks,
            "B_delta": 0.0, "B_crossed": i < b_cross, "B_decks": decks,
            "D_delta": 0.0, "D_crossed": i < d_cross, "D_decks": decks,
            "F_delta": 0.0, "F_crossed": i < f_cross, "F_decks": decks,
        })
    return out


def test_q2_hits_only_when_F_reaches_the_control():
    assert W._summarise(_rows(13, 13, 10))["Q2_F_vs_B"]["hit"] is True
    assert W._summarise(_rows(14, 13, 10))["Q2_F_vs_B"]["hit"] is True
    assert W._summarise(_rows(12, 13, 10))["Q2_F_vs_B"]["hit"] is False


def test_q3_needs_F_to_beat_the_policys_own_sampling():
    assert W._summarise(_rows(11, 13, 10))["Q3_F_vs_D"]["hit"] is True
    assert W._summarise(_rows(10, 13, 10))["Q3_F_vs_D"]["hit"] is False


def test_the_expected_null_is_scored_as_a_null():
    # Guard 5: a tie must be reported as a tie. Identical crossing sets give
    # zero discordant pairs, so the test cannot reach significance.
    got = W._summarise(_rows(13, 13, 10))
    assert got["Q5_expected_null"]["hit"] is True
    assert got["Q2_F_vs_B"]["p"] >= 0.05


def test_the_budget_gate_fires_when_the_arms_stop_being_matched():
    rows = _rows(13, 13, 10)
    for r in rows:
        r["F_decks"] = 40.0          # +33 % against A's 30
    got = W._summarise(rows)
    assert got["Q4_budget"]["hit"] is False


def test_the_control_reports_a_start_mismatch():
    rows = _rows(13, 13, 10)
    rows[0]["same_start"] = False
    assert W._summarise(rows)["Q1_control"]["reproduced"] is False
