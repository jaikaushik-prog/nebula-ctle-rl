"""Fail-capable gates for the adaptation-control benchmark.

The circuit table is synthetic.  These tests protect experiment accounting:
random episodes must not replay one fixed sequence, and the reported policy bar
must be the strongest non-RL Pareto frontier rather than a favoured algorithm.
"""

from __future__ import annotations

import ast
import math
from pathlib import Path

from nebula.experiments.exp_adapt_controls import (
    LEGACY_RESULTS,
    RESULTS,
    make_arm_random,
    pareto_frontier,
    score_random_seeds,
)
from nebula.experiments.exp_bank_sweep import REQUEST_ROWS, SPECS
from nebula.rl.adapt_env import AdaptEnv, AdaptReward, BankTable, N_CODES

CORNERS = ("tt/1.00/27C", "ss/0.95/125C")
REQ = (9.0, 1.9e9)


def test_qualified_controls_cannot_clobber_the_entry79_artifact():
    assert RESULTS != LEGACY_RESULTS
    assert RESULTS.name == "adapt_controls_multiseed_results.json"


def _table(compliant_codes=(5,)) -> BankTable:
    rows = []
    for corner in CORNERS:
        for code in range(N_CODES):
            good = code in compliant_codes
            rows.append({
                "i_rs": code // 8, "i_cs": code % 8, "code": code,
                "corner": corner, "ok": True, "reason": None,
                "peaking_db": 9.0 if good else 40.0,
                "f_peak_oct": math.log2(1.9e9 / 2.5e9),
                "margins": {k: 1.0 for k in SPECS if k not in REQUEST_ROWS},
                "eye_h_v": 0.1 + 0.001 * code, "eye_w_ui": 0.6,
                "power_w": 5e-3, "hd3_nyq_dbc": -40.0,
            })
    return BankTable(rows)


def _random_codes(seed: int, corner: str, request=REQ) -> list[int]:
    env = AdaptEnv(_table(compliant_codes=(5,)), [request], max_trials=8,
                   seed=0)
    env.reset(corner=corner, request=request)
    make_arm_random(seed)(env)
    return list(env.ep.codes_tried)


def test_random_arm_is_reproducible_for_the_same_episode():
    assert _random_codes(17, CORNERS[0]) == _random_codes(17, CORNERS[0])


def test_random_arm_does_not_replay_one_order_for_every_episode():
    """The exact defect frozen as G142 before this repair."""
    assert _random_codes(17, CORNERS[0]) != _random_codes(17, CORNERS[1])


def test_random_arm_changes_with_the_experiment_seed():
    assert _random_codes(17, CORNERS[0]) != _random_codes(18, CORNERS[0])


def test_random_reserves_budget_to_ship_the_best_eye_it_observed():
    env = AdaptEnv(_table(compliant_codes=(5,)), [REQ], max_trials=8, seed=0)
    env.reset(corner=CORNERS[0], request=REQ)
    make_arm_random(17)(env)
    tried = env.ep.codes_tried
    assert env.ep.n_trials <= env.max_trials
    assert env.ep.locked_code == max(tried)  # synthetic eye rises with code


def test_random_summary_reports_between_seed_uncertainty():
    # Make seed 0 a known hit and leave enough other seeds to produce misses;
    # this makes the gate deterministic instead of hoping a particular random
    # sample happens to show spread.
    known_hit = _random_codes(0, CORNERS[0])[-1]
    table = _table(compliant_codes=(known_hit,))
    out = score_random_seeds(table, CORNERS, [REQ], AdaptReward(), 8,
                             seeds=range(32))
    assert out["n_seeds"] == 32
    assert len(out["per_seed"]) == 32
    assert out["compliance_rate_sd"] > 0.0
    assert out["compliance_rate_ci95"][0] <= out["compliance_rate_mean"]
    assert out["compliance_rate_ci95"][1] >= out["compliance_rate_mean"]


def test_pareto_bar_is_not_hard_coded_to_hillclimb():
    rows = [
        {"arm": "hillclimb", "compliance_rate_of_solvable": 0.20,
         "mean_trials_on_solvable": 8.0},
        {"arm": "fixed", "compliance_rate_of_solvable": 0.27,
         "mean_trials_on_solvable": 1.0},
        {"arm": "exhaustive", "compliance_rate_of_solvable": 0.08,
         "mean_trials_on_solvable": 65.0},
    ]
    assert [r["arm"] for r in pareto_frontier(rows)] == ["fixed"]


def test_pareto_frontier_keeps_a_real_compliance_trials_tradeoff():
    rows = [
        {"arm": "fast", "compliance_rate_of_solvable": 0.50,
         "mean_trials_on_solvable": 1.0},
        {"arm": "accurate", "compliance_rate_of_solvable": 0.75,
         "mean_trials_on_solvable": 8.0},
        {"arm": "dominated", "compliance_rate_of_solvable": 0.40,
         "mean_trials_on_solvable": 9.0},
    ]
    assert [r["arm"] for r in pareto_frontier(rows)] == ["fast", "accurate"]


def test_console_print_literals_are_ascii_for_windows_cp1252():
    path = (Path(__file__).parents[1] / "experiments" /
            "exp_adapt_controls.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for call in (n for n in ast.walk(tree) if isinstance(n, ast.Call)):
        if not isinstance(call.func, ast.Name) or call.func.id != "print":
            continue
        for constant in (n for arg in call.args for n in ast.walk(arg)
                         if isinstance(n, ast.Constant)
                         and isinstance(n.value, str)):
            assert constant.value.isascii(), repr(constant.value)
