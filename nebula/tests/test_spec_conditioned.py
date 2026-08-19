"""
Tests for `rl/spec_dist.py` and `experiments/spec_pool.py` — the
spec-conditioned scaffolding.

**None of these runs ngspice.** `spec_dist` is pure arithmetic and `spec_pool`
re-scores measurements that are already on disk, which is the whole point of
the pool: a measurement does not know what it was aiming at, so scoring it
against a new target costs nothing.

Four are gates in CLAUDEwa.md §8 rule 10's sense:

  * `test_target_peaking_db_IS_INERT_and_that_is_documented` — the finding that
    halves what "spec-conditioned" can mean here. If it ever starts working,
    this must go red so the change is noticed rather than absorbed.
  * `test_a_held_out_target_is_never_in_the_training_set`
  * `test_the_pool_excludes_P3_rows` — a corner measurement under a nominal
    name is rule 9 in the data.
  * `test_score_pool_is_a_pure_function_of_design_and_target`
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from nebula.common.types import SPEC_F_PEAK_HZ_RANGE, SPEC_PEAKING_DB_RANGE
from nebula.rl import reward_v1 as R
from nebula.rl import spec_dist as SD
from nebula.rl.contract import N_ACTIONS


# ─────────────────────────────────────────────────────────────────────────────
# The distribution — S3's own band, not a choice
# ─────────────────────────────────────────────────────────────────────────────


def test_the_distribution_is_the_spec_table_not_a_preference():
    """CLAUDEwa §8 rule 6 forbids inventing spec-tightness heuristics, so the
    sampler must draw from S3's stated band and nothing else."""
    ts = SD.sample_targets(2000, seed=1)
    db = np.array([t.peaking_db for t in ts])
    hz = np.array([t.f_peak_hz for t in ts])
    lo_db, hi_db = SPEC_PEAKING_DB_RANGE
    lo_hz, hi_hz = SPEC_F_PEAK_HZ_RANGE
    assert db.min() >= lo_db and db.max() <= hi_db
    assert hz.min() >= lo_hz and hz.max() <= hi_hz
    # it must actually reach toward both ends rather than hugging the centre
    assert db.min() < lo_db + 0.1 * (hi_db - lo_db)
    assert db.max() > hi_db - 0.1 * (hi_db - lo_db)


def test_frequency_is_drawn_uniformly_in_OCTAVES_not_in_hertz():
    """S3's window is exactly one octave and every frequency result in this
    project is quoted in octaves. A hertz-uniform draw would put half its mass
    above 1.875 GHz and make the low end of the spec's own window rare."""
    ts = SD.sample_targets(4000, seed=2)
    oct_ = np.array([t.f_peak_oct for t in ts])
    span = oct_.max() - oct_.min()
    assert span == pytest.approx(1.0, abs=0.02), "the window is one octave"
    # uniform in octaves => the MEDIAN is the geometric mean, not the mean
    hz = np.array([t.f_peak_hz for t in ts])
    geo = math.sqrt(SPEC_F_PEAK_HZ_RANGE[0] * SPEC_F_PEAK_HZ_RANGE[1])
    ari = sum(SPEC_F_PEAK_HZ_RANGE) / 2.0
    assert abs(np.median(hz) - geo) < abs(np.median(hz) - ari)


def test_a_target_outside_S3_is_refused_rather_than_clipped():
    lo_db, hi_db = SPEC_PEAKING_DB_RANGE
    with pytest.raises(ValueError, match="outside S3"):
        SD.SpecTarget(peaking_db=hi_db + 1.0, f_peak_hz=1.8e9)
    with pytest.raises(ValueError, match="outside S3"):
        SD.SpecTarget(peaking_db=(lo_db + hi_db) / 2, f_peak_hz=5.0e9)


def test_the_legacy_target_is_the_one_every_published_run_used():
    """Kept so conditioned results can be read against unconditioned ones."""
    assert SD.LEGACY_TARGET.peaking_db == pytest.approx(
        sum(SPEC_PEAKING_DB_RANGE) / 2.0)
    assert SD.LEGACY_TARGET.f_peak_hz == pytest.approx(
        math.sqrt(SPEC_F_PEAK_HZ_RANGE[0] * SPEC_F_PEAK_HZ_RANGE[1]))
    # the geometric centre of a one-octave window is half an octave below
    # Nyquist, which is what every f_peak number in this project is quoted at
    assert SD.LEGACY_TARGET.f_peak_oct == pytest.approx(-0.5, abs=1e-9)


# ─────────────────────────────────────────────────────────────────────────────
# The splits
# ─────────────────────────────────────────────────────────────────────────────


def test_a_held_out_target_is_never_in_the_training_set():
    """**The gate.** A held-out spec that was trained on is not held out, and
    the failure is invisible in every downstream number."""
    for split in (SD.interpolation_split(), SD.extrapolation_split()):
        tr = {t.as_key() for t in split.train}
        te = {t.as_key() for t in split.test}
        assert not (tr & te), f"{split.name}: {len(tr & te)} leaked targets"
    with pytest.raises(ValueError, match="BOTH train and test"):
        t = SD.LEGACY_TARGET
        SD.Split("bad", (t,), (t,), "leaks")


def test_extrapolation_really_extrapolates():
    """Nothing in training may reach the test region, or the 'it learned the
    mapping rather than the neighbourhood' claim is unsupported."""
    sp = SD.extrapolation_split()
    hi_train = max(t.peaking_db for t in sp.train)
    lo_test = min(t.peaking_db for t in sp.test)
    assert hi_train <= SD.EXTRAP_SPLIT_DB <= lo_test
    assert lo_test > hi_train, "the two regions touch or overlap"
    # and the split is on PEAKING, so the frequency ranges must still overlap
    tr_oct = [t.f_peak_oct for t in sp.train]
    te_oct = [t.f_peak_oct for t in sp.test]
    assert min(te_oct) > min(tr_oct) - 0.5 and max(te_oct) < max(tr_oct) + 0.5


def test_the_splits_are_reproducible_from_their_stated_seeds():
    a = SD.interpolation_split()
    b = SD.interpolation_split()
    assert [t.as_key() for t in a.test] == [t.as_key() for t in b.test]
    c = SD.interpolation_split(seed=SD.interpolation_split.__defaults__[2] + 1)
    assert [t.as_key() for t in a.test] != [t.as_key() for t in c.test]


# ─────────────────────────────────────────────────────────────────────────────
# The finding that halves the contribution
# ─────────────────────────────────────────────────────────────────────────────


def test_target_peaking_db_IS_INERT_and_that_is_documented():
    """**The measurement behind session 22j's first finding.**

    `reward_v1.margins` states it: *"`target_peaking_db` is accepted for the
    spec-conditioned form but is NOT used: S3's peaking constraint is a BAND
    (3-12 dB), and CLAUDEwa.md §3 reads the band as the requirement."* So the
    observation's two-channel target block has ONE live channel, and the
    spec-conditioned problem is one-dimensional.

    This test exists to make that visible rather than to enforce it. **If
    peaking ever becomes a real target the test goes red**, which is the point:
    that change moves every published reward and is a `BASELINES.md` §7f re-run
    event, so it must not happen quietly.
    """
    meas = {"g_dc_db": 3.0, "peaking_db": 6.0, "f_peak_oct": -0.5,
            "nyq_boost_db": 4.0, "inoise_vrms": 3.0e-4, "power_w": 5.0e-3,
            "pair_margin_v": 0.25, "tail_margin_v": 0.05}
    f = SD.LEGACY_TARGET.f_peak_hz
    scores = [R.reward(meas, f, target_peaking_db=db).reward
              for db in (3.0, 5.0, 7.5, 10.0, 12.0)]
    assert len(set(round(s, 12) for s in scores)) == 1, (
        "target_peaking_db now changes the reward -- the spec-conditioned "
        "problem has become 2-D and every published number has moved")

    # ... while the FREQUENCY target is live, which is what makes conditioning
    # meaningful at all
    lo, hi = SPEC_F_PEAK_HZ_RANGE
    by_f = [R.reward(meas, hz, target_peaking_db=7.5).reward
            for hz in (lo, math.sqrt(lo * hi), hi)]
    assert by_f[1] > by_f[0] and by_f[1] > by_f[2], (
        "the design peaks at the window centre, so it must score best there")
    # ... and the two edges score EQUALLY, which pins that the f_peak margin is
    # symmetric in OCTAVES rather than in hertz: this design sits half an
    # octave from each edge but 517 MHz from one and 732 MHz from the other.
    assert by_f[0] == pytest.approx(by_f[2], abs=1e-9)


# ─────────────────────────────────────────────────────────────────────────────
# The pool
# ─────────────────────────────────────────────────────────────────────────────


def _fake_log(tmp_path, rows):
    p = tmp_path / "log.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return p


def _trial(design_id, peaking, f_oct, problem="P1", verdict="valid",
           method="uniform", **over):
    m = {"g_dc_db": 3.0, "peaking_db": peaking, "f_peak_oct": f_oct,
         "nyq_boost_db": 4.0, "inoise_vrms": 3.0e-4, "power_w": 5.0e-3,
         "pair_margin_v": 0.25, "tail_margin_v": 0.05}
    m.update(over.pop("meas", {}))
    return {"kind": "event", "event": "trial", "problem": problem,
            "verdict": verdict, "design_id": design_id, "method": method,
            "u": [0.5] * N_ACTIONS, "meas": m, "n_sims": 1, **over}


def test_the_pool_excludes_P3_rows(tmp_path):
    """**Rule 9 in the data.** `Trial.meas` is the NOMINAL measurement, which
    on P1 is tt/cl_mid; on P3 the first evaluated point is a CORNER, so the
    same field means something else. One name, two meanings."""
    from nebula.experiments import spec_pool as SP

    log = _fake_log(tmp_path, [_trial("a", 6.0, -0.5),
                               _trial("b", 6.0, -0.5, problem="P3")])
    pool = SP.load_pool([log])
    assert len(pool) == 1 and pool.design_id == ("a",)
    assert pool.n_dropped["not_P1"] == 1


def test_the_pool_drops_invalid_and_duplicate_rows_and_counts_both(tmp_path):
    from nebula.experiments import spec_pool as SP

    log = _fake_log(tmp_path, [
        _trial("a", 6.0, -0.5),
        _trial("a", 6.0, -0.5),                      # same design, seen twice
        _trial("c", 6.0, -0.5, verdict="invalid"),
    ])
    pool = SP.load_pool([log])
    assert len(pool) == 1
    assert pool.n_dropped["duplicate_design"] == 1
    assert pool.n_dropped["not_valid"] == 1


def test_a_missing_measurement_channel_drops_the_row_rather_than_defaulting(
        tmp_path):
    """Rule 1: a missing channel is a failed evaluation, never a zero."""
    from nebula.experiments import spec_pool as SP

    bad = _trial("a", 6.0, -0.5)
    del bad["meas"]["power_w"]
    log = _fake_log(tmp_path, [bad, _trial("b", 6.0, -0.5)])
    pool = SP.load_pool([log])
    assert len(pool) == 1 and pool.design_id == ("b",)
    assert pool.n_dropped["missing_channel"] == 1


def test_a_named_log_that_is_missing_RAISES_rather_than_shrinking_the_pool(
        tmp_path):
    from nebula.experiments import spec_pool as SP

    with pytest.raises(FileNotFoundError, match="named rather than globbed"):
        SP.load_pool([tmp_path / "nope.jsonl.gz"])


def test_score_pool_is_a_pure_function_of_design_and_target(tmp_path):
    """**The property the whole method rests on.** A design simulated months
    ago under a different target must re-score EXACTLY, not approximately, or
    the pool is not a dataset."""
    from nebula.experiments import spec_pool as SP

    log = _fake_log(tmp_path, [_trial("a", 6.0, -0.5),
                               _trial("b", 9.0, -0.2)])
    pool = SP.load_pool([log])
    t = SD.LEGACY_TARGET
    a = SP.score_pool(pool, t)
    b = SP.score_pool(pool, t)
    assert np.array_equal(a, b)
    # and it agrees with reward_v1 called directly
    for i, m in enumerate(pool.meas):
        assert a[i] == R.reward(m, t.f_peak_hz,
                                target_peaking_db=t.peaking_db).reward


def test_lookup_costs_zero_simulations_and_says_so(tmp_path):
    """The design the library returns was measured when it entered the pool,
    so there is nothing left to verify. That is the baseline's whole claim and
    it is asserted rather than described."""
    from nebula.experiments import spec_pool as SP

    log = _fake_log(tmp_path, [_trial("near", 6.0, -0.5),
                               _trial("far", 6.0, -0.95)])
    pool = SP.load_pool([log])
    res = SP.lookup_best(pool, SD.LEGACY_TARGET)
    assert res.sims_spent == 0
    assert res.design_id == "near", "the closer peak must win"
    assert res.u.shape == (N_ACTIONS,)


def test_the_naive_nearest_neighbour_can_disagree_with_the_reward_lookup(
        tmp_path):
    """The two answer different questions, which is why both exist: 1-NN in S3
    space ignores S5/S6, so it can return a design that is closest in peaking
    and fails on noise or power."""
    from nebula.experiments import spec_pool as SP

    close_but_hungry = _trial("hungry", 7.5, -0.5,
                              meas={"power_w": 1.0})       # blows S6
    further_but_fine = _trial("fine", 7.5, -0.45)
    pool = SP.load_pool([_fake_log(tmp_path,
                                   [close_but_hungry, further_but_fine])])
    t = SD.LEGACY_TARGET
    assert pool.design_id[SP.nearest_in_spec_space(pool, t)] == "hungry"
    assert SP.lookup_best(pool, t).design_id == "fine"


def test_coverage_reports_the_feasible_bonus_it_thresholds_on(tmp_path):
    """A pass rate whose threshold is not stated is not auditable."""
    from nebula.experiments import spec_pool as SP

    pool = SP.load_pool([_fake_log(tmp_path, [_trial("a", 6.0, -0.5)])])
    cov = SP.coverage(pool, [SD.LEGACY_TARGET])
    assert cov["feasible_bonus"] == R.feasible_bonus(len(R.V1_SPECS))
    assert cov["n_targets"] == 1
    assert set(cov["per_target"][0]) >= {"peaking_db", "f_peak_hz",
                                         "best_reward", "feasible",
                                         "design_id"}
