"""Gates for `experiments/exp_variance.py`.

No SPICE. Every test reads the committed sweep log, so these are safe to run
while an experiment holds the simulator (G70).

The load-bearing test here is `test_pooling_problems_inflates_the_spread`: the
first version of the analysis grouped by (method, prescreen) WITHOUT `problem`
and reported `uniform`'s standard deviation as 4.6186 instead of 0.1110. It did
not raise, it did not look wrong, and it would have been a published number.
"""

from __future__ import annotations

import gzip
import json
import statistics as st
from collections import defaultdict

import pytest

from nebula.experiments import exp_variance as V


@pytest.fixture(scope="module")
def rows():
    if not V.LOG.exists():                                      # pragma: no cover
        pytest.skip(f"{V.LOG.name} not present")
    return V.load_summaries()


@pytest.fixture(scope="module")
def result():
    if not V.LOG.exists():                                      # pragma: no cover
        pytest.skip(f"{V.LOG.name} not present")
    return V.analyse()


def test_only_measured_role_and_one_problem(rows):
    assert rows, "no summary rows loaded"
    assert {r["role"] for r in rows} == {"measured"}
    assert {r["problem"] for r in rows} == {"P1"}


def test_pooling_problems_inflates_the_spread():
    """The bug this module was written around. Must stay reproducible."""
    per_problem = defaultdict(list)
    pooled = defaultdict(list)
    with gzip.open(V.LOG, "rt", encoding="utf-8") as fh:
        for line in fh:
            d = json.loads(line)
            if d.get("event") != "run_summary" or d.get("role") != "measured":
                continue
            key = (d["method"], bool(d["prescreen"]))
            pooled[key].append(float(d["best_reward"]))
            if d["problem"] == "P1":
                per_problem[key].append(float(d["best_reward"]))

    k = ("uniform", False)
    sd_p1 = st.stdev(per_problem[k])
    sd_pooled = st.stdev(pooled[k])
    # P3's rewards are negative and P1's saturate near +8.95, so pooling does not
    # widen the spread a little -- it changes its order of magnitude.
    assert sd_pooled > 10 * sd_p1, (
        f"pooling no longer inflates the spread (P1 {sd_p1:.4f}, "
        f"pooled {sd_pooled:.4f}) -- if the log changed, re-derive the docstring")


def test_load_summaries_refuses_to_pool_problems():
    with pytest.raises(ValueError, match="pooling"):
        V.load_summaries(problem="")


def test_every_arm_has_at_least_two_replicates(result):
    for name, a in result["arms"].items():
        assert a["n"] >= 2, f"{name} has n={a['n']}; a spread needs two runs"


def test_sd_is_consistent_with_min_max(result):
    for name, a in result["arms"].items():
        assert a["min"] <= a["mean"] <= a["max"], name
        assert a["sd"] >= 0.0, name


def test_cmaes_is_more_consistent_than_uniform(result):
    """The headline. Reported with a CI, so the gate is on the CI, not the point."""
    c = next(x for x in result["comparisons"]
             if x["a"] == "uniform" and x["b"] == "cmaes")
    assert c["ratio"] > 1.0
    assert c["distinguishable"], "CI now spans 1.0; the headline must be restated"
    assert c["ci95"][0] > 1.0


def test_ppo_vs_screened_uniform_is_reported_as_not_distinguishable(result):
    """The honest negative. If this ever flips, the report claim must change."""
    c = next(x for x in result["comparisons"]
             if x["a"] == "ppo+screen" and x["b"] == "uniform+screen")
    assert not c["distinguishable"], (
        "PPO vs screened uniform is now distinguishable on spread -- "
        "VARIANCE.md section 3 says it is not, and must be rewritten")
    assert c["ci95"][0] < 1.0 < c["ci95"][1]


def test_bootstrap_is_deterministic():
    a = [1.0, 2.0, 3.0, 4.0, 5.0]
    b = [1.0, 1.1, 0.9, 1.05, 0.95]
    assert V.sd_ratio_ci(a, b, n_boot=500) == V.sd_ratio_ci(a, b, n_boot=500)


def test_sd_ratio_ci_brackets_a_known_ratio():
    """A 10x-wider sample must produce an interval above 1.0."""
    rng = __import__("random").Random(3)
    a = [rng.gauss(0, 10) for _ in range(30)]
    b = [rng.gauss(0, 1) for _ in range(30)]
    lo, hi = V.sd_ratio_ci(a, b, n_boot=2000)
    assert lo > 1.0
    assert lo < 10.0 < hi


def test_identical_data_gives_an_interval_containing_one():
    """The invariant is about IDENTICAL data, not same-distribution data.

    A percentile bootstrap is centred on the OBSERVED ratio, so two independent
    draws from one distribution can easily yield an interval excluding 1.0 --
    the first version of this test asserted otherwise and failed at [1.05, ...].
    Comparing a sample against itself is the case that must contain 1.0.
    """
    rng = __import__("random").Random(11)
    a = [rng.gauss(0, 1) for _ in range(40)]
    lo, hi = V.sd_ratio_ci(a, list(a), n_boot=2000)
    assert lo < 1.0 < hi
