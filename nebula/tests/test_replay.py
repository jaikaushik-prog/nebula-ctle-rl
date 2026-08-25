"""**The replay buffer and the pool seeder: is every seeded transition real?**

`rl/replay.py` claims to turn 74 526 already-simulated designs into millions of
`(s, a, r, s', done)` transitions for zero new SPICE. That claim rests on one
piece of arithmetic being EXACT, not approximate: the mined action

    a = (u_j - u_i) / MAX_STEP

pushed through the env's own dynamics `u' = clip(u + clip(a,-1,1)*MAX_STEP,0,1)`
must reproduce `u_j` to floating point. If it does not, the buffer is full of
transitions that never happened, and an off-policy critic trained on them
learns a dynamics that is not the simulator's. Section 3 is that test; it is the
reason this file exists.

The rest fences the seeder the way `test_analytic_env.py` fences the analytic
env: no fabricated measurement reaches the buffer, every drop is counted rather
than silent, and randomness is reproducible from the seed alone (G3).

No SPICE, no `torch`, no `load_pool` in the fast path -- a synthetic pool proves
the mechanism in milliseconds; one `slow` test guards against the real pool's
schema drifting away from what the seeder reads.
"""

from __future__ import annotations

import numpy as np
import pytest

import nebula.rl.reward_v1 as R
from nebula.rl.contract import MAX_STEP, N_ACTIONS, N_OBS, NYQUIST_HZ
from nebula.rl.replay import (
    SEED_SPECS,
    ReplayBuffer,
    SeedReport,
    mine_pool_transitions,
    seed_from_pool,
)
from nebula.rl.spec_dist import SpecTarget

TARGETS = [SpecTarget(peaking_db=7.5, f_peak_hz=1.7677669529663687e9),
           SpecTarget(peaking_db=6.0, f_peak_hz=2.0e9)]


class _FakePool:
    """A small, dense, fully-scorable pool. Dense so adjacency exists.

    The eight `REQUIRED_MEAS` channels only; values in ranges `reward_v1` can
    score without raising, so a drop in a test means the seeder dropped it, not
    that the fixture is unscorable.
    """

    def __init__(self, n: int = 400, seed: int = 0, spread: float = 0.05):
        rng = np.random.default_rng(seed)
        self.u = np.clip(rng.normal(0.5, spread, size=(n, N_ACTIONS)), 0.0, 1.0)
        meas = []
        for _ in range(n):
            meas.append(dict(
                g_dc_db=float(rng.uniform(5, 15)),
                peaking_db=float(rng.uniform(3, 12)),
                f_peak_oct=float(rng.uniform(-1.0, 0.0)),
                nyq_boost_db=float(rng.uniform(0, 6)),
                inoise_vrms=float(rng.uniform(1e-4, 1e-3)),
                power_w=float(rng.uniform(1e-3, 1e-2)),
                pair_margin_v=float(rng.uniform(0.0, 0.3)),
                tail_margin_v=float(rng.uniform(0.0, 0.3)),
            ))
        self.meas = tuple(meas)
        self.design_id = tuple(f"d{k}" for k in range(n))


def _mine(pool=None, n=300, seed=3, her_frac=0.5, targets=None):
    pool = pool if pool is not None else _FakePool()
    return mine_pool_transitions(
        pool, targets or TARGETS, n_transitions=n, seed=seed,
        her_frac=her_frac, count_available=False)


# ── 1. ReplayBuffer: the plain infrastructure ────────────────────────────────

def test_buffer_add_len_and_circular():
    buf = ReplayBuffer(capacity=3)
    z = np.zeros(N_OBS, dtype=np.float32)
    a = np.zeros(N_ACTIONS, dtype=np.float32)
    for r in range(5):
        buf.add(z + r, a, float(r), z + r, r % 2)
    assert len(buf) == 3 and buf.full
    # oldest two (r=0,1) overwritten; buffer holds r=2,3,4 somewhere
    stored = {int(buf._rew[i]) for i in range(3)}
    assert stored == {2, 3, 4}


def test_buffer_rejects_bad_shapes_and_nonfinite():
    buf = ReplayBuffer(capacity=4)
    z = np.zeros(N_OBS, dtype=np.float32)
    a = np.zeros(N_ACTIONS, dtype=np.float32)
    with pytest.raises(ValueError):
        buf.add(np.zeros(N_OBS - 1), a, 0.0, z, False)
    with pytest.raises(ValueError):
        buf.add(z, np.zeros(N_ACTIONS + 1), 0.0, z, False)
    with pytest.raises(ValueError):
        buf.add(z, a, float("nan"), z, False)          # reward
    bad = z.copy(); bad[0] = np.inf
    with pytest.raises(ValueError):
        buf.add(bad, a, 0.0, z, False)                 # obs channel


def test_buffer_sample_shapes_and_empty():
    buf = ReplayBuffer(capacity=10)
    with pytest.raises(ValueError):
        buf.sample(4, np.random.default_rng(0))
    z = np.zeros(N_OBS, dtype=np.float32)
    a = np.zeros(N_ACTIONS, dtype=np.float32)
    for _ in range(5):
        buf.add(z, a, 1.0, z, False)
    mb = buf.sample(32, np.random.default_rng(0))       # replacement > len ok
    assert mb["obs"].shape == (32, N_OBS)
    assert mb["act"].shape == (32, N_ACTIONS)
    assert mb["rew"].shape == (32,) and mb["done"].shape == (32,)


def test_buffer_sample_is_seed_reproducible():
    buf = ReplayBuffer(capacity=64)
    rng = np.random.default_rng(11)
    for _ in range(64):
        o = rng.normal(size=N_OBS).astype(np.float32)
        buf.add(o, np.zeros(N_ACTIONS), float(o[0]), o, False)
    m1 = buf.sample(16, np.random.default_rng(5))
    m2 = buf.sample(16, np.random.default_rng(5))
    assert np.array_equal(m1["rew"], m2["rew"])


def test_add_batch_rejects_ragged():
    buf = ReplayBuffer(capacity=8)
    obs = np.zeros((3, N_OBS), dtype=np.float32)
    with pytest.raises(ValueError):
        buf.add_batch(obs=obs, act=np.zeros((2, N_ACTIONS)),
                      rew=np.zeros(3), next_obs=obs, done=np.zeros(3))


# ── 2. Mining: shapes, ranges, finiteness ────────────────────────────────────

def test_mined_batch_is_finite_and_correctly_shaped():
    batch, rep = _mine(n=250)
    assert rep.n_transitions == batch["obs"].shape[0] == 250
    assert batch["obs"].shape == (250, N_OBS)
    assert batch["act"].shape == (250, N_ACTIONS)
    for k in ("obs", "act", "rew", "next_obs", "done"):
        assert np.all(np.isfinite(batch[k])), k


def test_mined_actions_are_in_the_box():
    batch, _ = _mine(n=500)
    assert batch["act"].min() >= -1.0
    assert batch["act"].max() <= 1.0


def test_mined_done_is_zero_or_one():
    batch, _ = _mine(n=300)
    assert set(np.unique(batch["done"])).issubset({0.0, 1.0})


# ── 3. THE LOAD-BEARING TEST: the mined action reproduces the endpoint ────────

def test_mined_action_reproduces_next_state_exactly():
    """`a = (u_j - u_i)/MAX_STEP` applied by the env's dynamics gives `u_j`.

    This is the whole claim, and it is checked against the action the SEEDER
    STORED -- not against one this test recomputes. The first version of this
    test did the latter: it re-derived `a` from the pool and verified its own
    arithmetic, so deleting the `/ max_step` in `replay.py` left it GREEN. A
    mutation run caught that (rule 4). The action now comes out of the batch.

    `build_observation` puts `clip(u, 0, 1)` in the first `N_ACTIONS` channels,
    so `u_i` and `u_j` are recoverable from `obs` and `next_obs` -- which is what
    makes the round-trip checkable end to end without a private accessor.
    """
    batch, _ = _mine(pool=_FakePool(n=300, seed=1), n=400)
    u_i = batch["obs"][:, :N_ACTIONS]
    u_j = batch["next_obs"][:, :N_ACTIONS]
    a = batch["act"]

    # the env, verbatim: u' = clip(u + clip(a, -1, 1) * MAX_STEP, 0, 1)
    u_next = np.clip(u_i + np.clip(a, -1.0, 1.0) * MAX_STEP, 0.0, 1.0)

    err = np.abs(u_next - u_j).max()
    assert err < 1e-6, (
        f"the STORED action does not reproduce the STORED endpoint: "
        f"max|du| = {err:.3e}. The buffer holds transitions that the env "
        f"cannot produce, so the critic is learning the wrong dynamics.")
    # A degenerate batch (all-zero actions) would also satisfy the above.
    assert np.abs(a).max() > 0.1, "batch is degenerate; the check is vacuous"


def test_mined_action_is_the_full_step_not_a_scaled_one():
    """Guards the `/ max_step` divisor specifically.

    Neighbours are within Chebyshev distance `MAX_STEP` of each other, so an
    action that FORGOT to divide by `MAX_STEP` is still inside `[-1, 1]` and
    still finite -- every bounds check passes. The tell is the magnitude: real
    actions span the box, a scaled-down set is confined to `|a| <= MAX_STEP`.
    """
    batch, _ = _mine(pool=_FakePool(n=300, seed=1), n=400)
    assert np.abs(batch["act"]).max() > MAX_STEP * 2.0, (
        f"largest |a| is {np.abs(batch['act']).max():.4f}, suspiciously close "
        f"to MAX_STEP={MAX_STEP} -- the action was probably never divided by it")


def test_pool_geometry_actually_supports_one_step_adjacency():
    """The premise, stated separately from the implementation: pool designs DO
    sit within one `MAX_STEP` of each other, so mining is not vacuous."""
    from scipy.spatial import cKDTree
    pool = _FakePool(n=300, seed=1)
    tree = cKDTree(pool.u)
    n_pairs = int(tree.count_neighbors(tree, r=MAX_STEP, p=np.inf)) - len(pool.u)
    assert n_pairs > 100, f"only {n_pairs} adjacent pairs; fixture too sparse"


# ── 4. Reward is real, not invented ──────────────────────────────────────────

def test_mined_reward_matches_reward_v1_recomputation():
    """Every stored reward equals `reward_v1.reward(meas_endpoint, target)`.

    The seeder must not shape, clip or rescale the reward; the critic has to see
    exactly what the SPICE env would report. Rebuild a handful from scratch.
    """
    pool = _FakePool(n=300, seed=2)
    batch, _ = _mine(pool=pool, n=200, her_frac=0.0)     # all real-target
    # With her_frac=0 every target is drawn from TARGETS; the stored reward must
    # be reproducible by scoring SOME (endpoint, target) pair on SEED_SPECS.
    # Check the reward LIVES in the set reward_v1 can produce for these targets.
    # Compare with a float32-quantisation tolerance (1e-4): far tighter than any
    # reshaping (which would shift the reward by O(1)), but loose enough to
    # absorb the buffer's float32 storage of a reward computed in float64.
    seen = np.array([
        float(R.reward(m, t.f_peak_hz, specs=SEED_SPECS,
                       target_peaking_db=t.peaking_db).reward)
        for t in TARGETS for m in pool.meas])
    for r in batch["rew"]:
        assert np.min(np.abs(seen - float(r))) < 1e-4, (
            f"stored reward {r} is not reproducible by reward_v1 on any "
            f"(pool design, target) pair -- it was invented or reshaped")


def test_seed_specs_is_the_spice_reward_scale():
    # G114 trap 2 is a reward-scale mismatch; the seed reward must be on the
    # same rows the SPICE corner env scores.
    assert SEED_SPECS == R.V6D_SPECS


# ── 4b. `specs` is a real parameter, not a decoration (G114 trap 2) ────────────

def test_the_two_reward_scales_really_are_different_scales():
    """The premise, before anything is mined: V6A and V6D score differently.

    Five rows with an invalid floor of -8.0 (analytic) against nine rows with a
    floor of -12.0 (SPICE corner). If these two ever became the same scale, the
    tests below would still pass while proving nothing, so state the difference
    here where a PDK or reward change would break it loudly.
    """
    from nebula.rl.analytic_env import V6A_SPECS
    assert len(V6A_SPECS) == 5 and len(R.V6D_SPECS) == 9
    assert R.invalid_reward(len(V6A_SPECS)) == -8.0
    assert R.invalid_reward(len(R.V6D_SPECS)) == -12.0


def test_passing_specs_changes_the_stored_reward_and_nothing_else():
    """Mine the SAME edges on both reward scales; only `rew` may differ.

    This is what stops `specs` from being an accepted-and-ignored keyword. The
    edge sampling never consults `specs`, so with a fully-scorable pool (asserted
    below, via zero drops) the two runs see an identical edge sequence -- which
    makes an element-wise comparison legitimate and isolates the reward as the
    one thing the parameter controls.
    """
    from nebula.rl.analytic_env import V6A_SPECS
    pool = _FakePool(n=300, seed=6)
    kw = dict(n_transitions=200, seed=17, her_frac=0.5, count_available=False)
    b_d, rep_d = mine_pool_transitions(pool, TARGETS, specs=R.V6D_SPECS, **kw)
    b_a, rep_a = mine_pool_transitions(pool, TARGETS, specs=V6A_SPECS, **kw)

    assert rep_d.n_dropped_unscorable == rep_a.n_dropped_unscorable == 0, (
        "a drop desynchronises the two edge sequences and the comparison below "
        "stops being element-wise; the fixture is meant to be fully scorable")
    for k in ("obs", "act", "next_obs"):
        assert np.array_equal(b_d[k], b_a[k]), (
            f"{k} changed with the spec rows -- `specs` is leaking into edge "
            f"selection, so a seeded buffer would not be comparable across runs")
    d = np.abs(b_d["rew"] - b_a["rew"]).max()
    assert d > 0.1, (
        f"switching from 9 rows to 5 moved the largest reward by only {d:.2e} "
        f"-- `specs` is not reaching reward_v1, and a buffer seeded for the "
        f"analytic env would carry SPICE-scale rewards (G114 trap 2)")


def test_report_records_the_specs_that_were_actually_used():
    """The report is the only place a later reader can check the scale matched.
    It must echo what was passed, not the module default."""
    from nebula.rl.analytic_env import V6A_SPECS
    _, rep = mine_pool_transitions(_FakePool(n=200, seed=7), TARGETS,
                                   n_transitions=40, seed=1,
                                   count_available=False, specs=V6A_SPECS)
    assert rep.seed_specs == tuple(V6A_SPECS)
    assert rep.as_dict()["seed_specs"] == list(V6A_SPECS)
    assert rep.seed_specs != tuple(SEED_SPECS)


def test_empty_specs_is_rejected_rather_than_silently_defaulted():
    # An empty row set would score everything against nothing; falling back to
    # SEED_SPECS would be a filtered-set failure (failure mode 1).
    with pytest.raises(ValueError):
        mine_pool_transitions(_FakePool(n=50), TARGETS, 10, seed=0, specs=())


def test_seed_from_pool_forwards_specs_to_the_scorer():
    """`specs` crosses two function boundaries; a missing forward is invisible
    because the default is a valid spec set that scores without error."""
    from nebula.rl.analytic_env import V6A_SPECS
    pool = _FakePool(n=300, seed=8)
    buf_a = ReplayBuffer(capacity=500)
    rep_a = seed_from_pool(buf_a, TARGETS, n_transitions=150, seed=4,
                           pool=pool, specs=V6A_SPECS)
    buf_d = ReplayBuffer(capacity=500)
    seed_from_pool(buf_d, TARGETS, n_transitions=150, seed=4, pool=pool)

    assert rep_a.seed_specs == tuple(V6A_SPECS)
    n = rep_a.n_transitions
    d = np.abs(buf_a._rew[:n] - buf_d._rew[:n]).max()
    assert d > 0.1, (
        f"seed_from_pool produced the same rewards on both scales (max delta "
        f"{d:.2e}) -- it is dropping `specs` on the way to mine_pool_transitions")


# ── 5. HER: relabel to the achieved response; drops are legal and counted ─────

def test_her_only_run_relabels_to_in_box_achieved_response():
    """With her_frac=1, every kept transition is done=1 and its target is a
    legal (in-box) achieved response, so the seeder must drop out-of-box
    endpoints rather than clamp them."""
    # spread wide so many designs sit outside S3's box -> forces drops
    pool = _FakePool(n=400, seed=5)
    # push some peakings out of [3,12] and f_peak out of window
    m = list(pool.meas)
    for k in range(0, 400, 3):
        d = dict(m[k]); d["peaking_db"] = 20.0; m[k] = d   # out of box
    pool.meas = tuple(m)
    batch, rep = mine_pool_transitions(pool, TARGETS, n_transitions=150,
                                       seed=9, her_frac=1.0,
                                       count_available=False)
    assert rep.n_real_target == 0
    assert rep.n_her == rep.n_transitions
    assert np.all(batch["done"] == 1.0), "a reached HER goal is terminal"
    assert rep.n_dropped_no_her_target > 0, (
        "wide pool must have out-of-box endpoints that HER cannot relabel")


def test_out_of_box_endpoint_is_dropped_not_clamped():
    # A single-design "achieved target" helper: illegal -> None, never clamped.
    from nebula.rl.replay import _achieved_target
    assert _achieved_target(20.0, -0.5) is None            # peaking > 12 dB
    assert _achieved_target(7.0, +5.0) is None             # f_peak >> window
    good = _achieved_target(7.0, -0.5)                     # in box
    assert isinstance(good, SpecTarget)
    # -0.5 octaves below 2.5 GHz Nyquist = 1.7678 GHz, inside [1.25, 2.5]
    assert abs(good.f_peak_hz - NYQUIST_HZ * 2 ** -0.5) < 1.0


# ── 6. Accounting: nothing truncates silently ────────────────────────────────def test_report_conserves_edges():
    batch, rep = _mine(n=300, her_frac=0.5)
    assert isinstance(rep, SeedReport)
    assert rep.n_transitions == rep.n_real_target + rep.n_her
    # every sampled edge is either kept or counted as a drop
    assert (rep.n_edges_sampled
            == rep.n_transitions + rep.n_dropped_unscorable)
    # drop_no_her_target happens BEFORE an edge counts as sampled-and-scored,
    # so it is tracked separately; it must be non-negative and finite
    assert rep.n_dropped_no_her_target >= 0
    assert rep.as_dict()["seed_specs"] == list(SEED_SPECS)


def test_report_states_availability_denominator_only_when_asked():
    _, rep_fast = _mine(n=50)                              # count_available=False
    assert rep_fast.n_directed_edges_available == -1


def test_availability_census_counts_DIRECTED_edges():
    """The denominator must be the directed edge count, not half of it.

    `i -> j` and `j -> i` are two minable transitions, so the census must not
    halve. An earlier version did halve it (and the docstring called the halved
    number "directed"), understating what the pool offers by exactly 2x. This
    test recomputes both candidates and requires the larger one.
    """
    from scipy.spatial import cKDTree
    pool = _FakePool(n=200, seed=4)
    _, rep = mine_pool_transitions(pool, TARGETS, n_transitions=20, seed=0,
                                   count_available=True)
    tree = cKDTree(pool.u)
    directed = int(tree.count_neighbors(tree, r=MAX_STEP, p=np.inf)) - len(pool.u)
    assert rep.n_directed_edges_available == directed
    assert rep.n_directed_edges_available != directed // 2, (
        "the census halved the count -- that is the undirected pair count, and "
        "it is not what the seeder can draw")


# ── 7. Determinism (G3): the seed alone reproduces the batch ──────────────────

def test_same_seed_same_batch():
    b1, _ = _mine(n=200, seed=42)
    b2, _ = _mine(n=200, seed=42)
    for k in b1:
        assert np.array_equal(b1[k], b2[k]), k


def test_different_seed_different_batch():
    b1, _ = _mine(n=200, seed=42)
    b2, _ = _mine(n=200, seed=43)
    assert not np.array_equal(b1["act"], b2["act"])


# ── 8. Argument validation ───────────────────────────────────────────────────

def test_mine_rejects_bad_args():
    pool = _FakePool(n=50)
    with pytest.raises(ValueError):
        mine_pool_transitions(pool, [], 10, seed=0)            # no targets
    with pytest.raises(ValueError):
        mine_pool_transitions(pool, TARGETS, 10, seed=0, her_frac=1.5)
    with pytest.raises(ValueError):
        mine_pool_transitions(pool, TARGETS, 0, seed=0)       # n<=0


def test_seed_from_pool_fills_the_buffer():
    pool = _FakePool(n=300)
    buf = ReplayBuffer(capacity=1000)
    rep = seed_from_pool(buf, TARGETS, n_transitions=200, seed=1, pool=pool)
    assert len(buf) == rep.n_transitions == 200


# ── 9. slow: the REAL pool, guarding against schema drift ─────────────────────

@pytest.mark.slow
def test_real_pool_mines_and_the_denominator_is_stated():
    from nebula.experiments.spec_pool import load_pool
    from nebula.rl.spec_dist import interpolation_split

    pool = load_pool()
    split = interpolation_split(n_train=64, n_test=16, seed=230821)
    batch, rep = mine_pool_transitions(pool, split.train, n_transitions=1000,
                                       seed=1, her_frac=0.5)
    assert rep.pool_size == len(pool)
    # Measured 2026-08-22: 74 526 designs, 34 789 444 directed adjacent edges.
    # A large drop means the pool shrank or MAX_STEP moved, not that the seeder
    # broke -- but either way the number in the docstring stopped being true.
    assert rep.n_directed_edges_available > 30_000_000, (
        f"directed-edge census is {rep.n_directed_edges_available}, the "
        f"docstring and entry 33 claim 34 789 444")
    assert rep.n_transitions == 1000
    assert batch["act"].min() >= -1.0 and batch["act"].max() <= 1.0
    assert np.all(np.isfinite(batch["obs"]))
