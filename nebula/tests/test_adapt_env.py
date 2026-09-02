"""tests for `rl/adapt_env` — the adaptation episode.

Built on a **synthetic** `BankTable` so nothing here depends on the 2 880-deck
artifact or on SPICE. The property under test is the episode contract, not the
circuit.

The gate that matters most: **the observation must not leak the corner or any
spec row the receiver cannot measure.** If it did, a policy could learn to read
the answer instead of inferring it, and the whole adaptation claim would be
measuring a lookup. It is asserted directly, and it is proved able to fail.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from nebula.rl.adapt_env import (
    LOCK,
    N_ACTIONS,
    N_CODES,
    N_OBS,
    OBS_PER_CODE,
    AdaptEnv,
    AdaptReward,
    BankTable,
)

CORNERS = ("tt/1.00/27C", "ss/0.95/125C")
REQ = (9.0, 1.9e9)


def _table(compliant_codes=(5,), eye_by_code=None) -> BankTable:
    """A table where `compliant_codes` meet every row and nothing else does.

    Compliance is driven through the real scorer: a compliant row gets margins
    that pass and a `peaking_db`/`f_peak_oct` on target; everything else is put
    far outside S3's peaking tolerance.
    """
    from nebula.experiments.exp_bank_sweep import REQUEST_ROWS, SPECS
    rows = []
    for corner in CORNERS:
        for code in range(N_CODES):
            good = code in compliant_codes
            eye = (eye_by_code or {}).get(code, 0.2)
            rows.append({
                "i_rs": code // 8, "i_cs": code % 8, "code": code,
                "corner": corner, "ok": True, "reason": None,
                "peaking_db": 9.0 if good else 40.0,
                "f_peak_oct": math.log2(1.9e9 / 2.5e9),
                "margins": {k: 1.0 for k in SPECS if k not in REQUEST_ROWS},
                "eye_h_v": eye, "eye_w_ui": 0.6,
                "power_w": 5e-3, "hd3_nyq_dbc": -40.0,
            })
    return BankTable(rows)


def _env(**kw) -> AdaptEnv:
    return AdaptEnv(_table(**kw.pop("table_kw", {})), [REQ], seed=0, **kw)


def test_shapes():
    assert N_ACTIONS == N_CODES + 1
    assert N_OBS == 3 + N_CODES * OBS_PER_CODE
    assert _env().reset().shape == (N_OBS,)


def test_ground_truth_reaches_the_real_scorer():
    t = _table(compliant_codes=(5,))
    assert t.compliant(5, CORNERS[0], 1.9e9, 9.0)
    assert not t.compliant(6, CORNERS[0], 1.9e9, 9.0)
    assert t.solvable(CORNERS[0], 1.9e9, 9.0) == [5]


# ── the leak gate ────────────────────────────────────────────────────────────


def test_the_observation_never_reveals_which_code_is_compliant():
    """**The gate.** Two tables differing ONLY in which code complies must
    produce identical observations for the same trials.

    If the observation carried compliance, or the corner, these would differ and
    a policy would be reading the answer rather than inferring it.
    """
    trials = [0, 5, 9]
    obs = []
    for good in ((5,), (9,)):
        env = AdaptEnv(_table(compliant_codes=good), [REQ], seed=0)
        env.reset(corner=CORNERS[0], request=REQ)
        for a in trials:
            o, *_ = env.step(a)
        obs.append(o)
    assert np.array_equal(obs[0], obs[1])


def test_the_observation_does_not_depend_on_the_hidden_corner():
    t = _table(compliant_codes=(5,))
    seen = []
    for corner in CORNERS:
        env = AdaptEnv(t, [REQ], seed=0)
        env.reset(corner=corner, request=REQ)
        o, *_ = env.step(3)
        seen.append(o)
    assert np.array_equal(seen[0], seen[1])


def test_a_trial_records_only_the_eye():
    env = AdaptEnv(_table(eye_by_code={7: 0.42}), [REQ], seed=0)
    env.reset(corner=CORNERS[0], request=REQ)
    o, *_ = env.step(7)
    i = 3 + 7 * OBS_PER_CODE
    assert o[i] == pytest.approx(1.0)
    assert o[i + 1] == pytest.approx(0.42 / 0.5)
    untried = 3 + 8 * OBS_PER_CODE
    assert o[untried] == 0.0


# ── the reward ───────────────────────────────────────────────────────────────


def test_locking_a_compliant_code_pays_the_bonus():
    R = AdaptReward()
    env = AdaptEnv(_table(compliant_codes=(5,)), [REQ], reward=R, seed=0)
    env.reset(corner=CORNERS[0], request=REQ)
    env.step(5)
    _, r, term, _, info = env.step(LOCK)
    assert term and info["compliant"] and r == pytest.approx(R.lock_bonus)


def test_a_false_lock_is_penalised_far_harder_than_a_trial():
    """The asymmetry the owner chose: shipping a broken part is the worst case."""
    R = AdaptReward()
    env = AdaptEnv(_table(compliant_codes=(5,)), [REQ], reward=R, seed=0)
    env.reset(corner=CORNERS[0], request=REQ)
    env.step(6)
    _, r, term, _, info = env.step(LOCK)
    assert term and not info["compliant"]
    assert r == pytest.approx(-R.false_lock)
    assert R.false_lock > R.lock_bonus > R.trial_cost


def test_every_trial_costs():
    R = AdaptReward()
    env = AdaptEnv(_table(), [REQ], reward=R, seed=0)
    env.reset(corner=CORNERS[0], request=REQ)
    for a in (0, 1, 2):
        _, r, term, _, _ = env.step(a)
        assert not term and r == pytest.approx(-R.trial_cost)
    assert env.ep.n_trials == 3


def test_locking_before_any_trial_is_refused_not_scored():
    env = _env()
    env.reset(corner=CORNERS[0], request=REQ)
    _, r, term, _, info = env.step(LOCK)
    assert not term and info.get("invalid_lock") and r < 0


def test_the_budget_truncates_and_locks_the_last_code_tried():
    env = AdaptEnv(_table(compliant_codes=(5,)), [REQ], max_trials=3, seed=0)
    env.reset(corner=CORNERS[0], request=REQ)
    env.step(0)
    env.step(1)
    _, _, term, trunc, info = env.step(5)
    assert term and trunc and info["locked"] == 5 and info["compliant"]


def test_solvable_is_recorded_so_an_arm_is_not_blamed_for_an_empty_bank():
    env = AdaptEnv(_table(compliant_codes=()), [REQ], seed=0)
    env.reset(corner=CORNERS[0], request=REQ)
    assert env.ep.solvable is False
    env = AdaptEnv(_table(compliant_codes=(5,)), [REQ], seed=0)
    env.reset(corner=CORNERS[0], request=REQ)
    assert env.ep.solvable is True
