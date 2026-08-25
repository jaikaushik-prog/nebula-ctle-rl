"""
rl/replay.py — the off-policy replay buffer, and the SPICE-measured transitions
we can seed it with for **zero** new simulations.

WHY THIS FILE EXISTS
--------------------
PPO is on-policy: every gradient step needs data collected by the *current*
policy, so the 74 526 designs this project has already simulated are useless to
it. That is not a tuning detail, it is the structural reason the project is
switching to SAC (HANDOFF G114 trap 1). SAC is off-policy — its critic learns
from a replay buffer that can hold data from any policy, or from no policy at
all. This file is that buffer, and the machinery to fill it from the pool.

THE MEASUREMENT THIS FILE IS BUILT ON
--------------------------------------
`spec_pool.load_pool()` returns 74 526 distinct valid designs, each with a real
SKY130 measurement block (`REQUIRED_MEAS`, the eight channels the observation is
built from). A design on its own is a *state*, not a *transition* — SAC's critic
needs `(s, a, r, s', done)`. The pool has no stored actions and no trajectory
structure (measured 2026-08-22: only ~1 041 rows in the whole repo carry an
`action`, none of the big logs do), so the transitions have to be **recovered**.

They can be, exactly, from geometry. The env's dynamics are

    u' = clip(u + clip(a, -1, 1) * MAX_STEP, 0, 1)

so any two pool designs whose sizings differ by at most `MAX_STEP` in every
coordinate are one legal action apart, and that action is recoverable with no
approximation:

    a = (u_j - u_i) / MAX_STEP          (in [-1, 1] by construction)

Both endpoints carry real measurements, so both observations are real and the
reward `reward_v1.reward(meas_j, target)` is real. Measured on the pool
(`nebula/PREDICTIONS.md` entry 33, re-verified 2026-08-22):

    pool designs                        74 526
    DIRECTED adjacent edges         34 789 444    <- one per minable transition
    (undirected pairs)              17 394 722    <- half the above; NOT the count
    designs with >= 1 neighbour         74 256    (99.64 %)
    neighbours per design         median 15, mean 466.8, max 2963

**The directed count is the one that matters, and getting that wrong is a factor
of two.** `i -> j` and `j -> i` are different transitions: different action,
different endpoint, different reward. An earlier draft of this docstring quoted
the undirected 17 394 722 and called it directed. The library of "already paid
for" transitions is combinatorial in the designs, not linear.

HINDSIGHT EXPERIENCE REPLAY (HER), AND WHY IT FITS UNUSUALLY WELL
------------------------------------------------------------------
The reward is spec-conditioned: `reward(meas, target)` scores a measurement
against a requested (peaking, f_peak). The target enters only at scoring time,
so **any measured design can be re-scored against any target for free** — the
same observation `spec_pool` is built on. HER exploits exactly this: for a mined
edge `i -> j`, relabel the target with the response design `j` *actually
achieved*, and the transition becomes a demonstration that action `a` from state
`i` reaches a design meeting that target. A failed reach for one spec is a
successful reach for the spec it hit. This is "the single highest-value addition
after off-policy itself" (`NEXT_AGENT_SAC.md` §4). Measured: **33 071** designs
(44.4 %) land inside S3's box and so are legal HER targets.

WHAT IS DELIBERATELY NOT DONE HERE
-----------------------------------
* **No CMA-ES pairs.** Trap 2 (G114): CMA-ES `sigma0 = 0.30` is 2x `MAX_STEP`,
  so its consecutive samples are usually NOT one action apart. The pool route
  above sidesteps that entirely by *filtering on the geometry* rather than
  trusting an optimiser's step size, so the whole buffer is provably reachable.
* **No fabricated measurement.** Every transition here is two real SPICE rows
  and a reward computed from them. `normalise_measurements` still raises on a
  missing channel; a pool row that cannot be scored is dropped and COUNTED
  (`SeedReport`), never defaulted (CLAUDEwa.md §8 rule 1).
* **Nothing here trains, and nothing here simulates.**

SEEDING
-------
HANDOFF G3: never `np.random.seed()`. Randomness arrives as a `seed` argument
and is threaded into a local `numpy.random.default_rng`. One seed, one place.

    from nebula.rl.replay import ReplayBuffer, seed_from_pool
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np

import nebula.rl.reward_v1 as R
from nebula.rl.contract import (
    HORIZON,
    MAX_STEP,
    N_ACTIONS,
    N_OBS,
    NYQUIST_HZ,
    build_observation,
)
from nebula.rl.spec_dist import SpecTarget

#: The spec set the SPICE corner env scores (`exp_corner_rl._score`). Seeded
#: transitions are scored on the SAME rows so the reward scale the critic learns
#: from the pool is the reward scale it will meet on SPICE — G114 trap 2 is a
#: reward-scale mismatch between pre-train and fine-tune, and this avoids
#: introducing a third scale. Listed by reference, never redeclared (rule 9).
SEED_SPECS: tuple[str, ...] = R.V6D_SPECS

#: S3's box, the only region a `SpecTarget` may be constructed in. A pool design
#: whose achieved response is outside this cannot be a HER target — its own
#: response is not a legal request — so it is filtered, not clamped.
from nebula.common.types import (  # noqa: E402  (kept beside its use)
    SPEC_F_PEAK_HZ_RANGE,
    SPEC_PEAKING_DB_RANGE,
)


# ─────────────────────────────────────────────────────────────────────────────
# The buffer.
# ─────────────────────────────────────────────────────────────────────────────


class ReplayBuffer:
    """A fixed-capacity circular buffer of `(obs, act, rew, next_obs, done)`.

    Pre-allocated `float32` arrays, uniform sampling — the standard off-policy
    buffer, written to be read. It holds transitions from any source: the SAC
    agent's own rollouts, and the pool-seeded transitions this module mines.
    The buffer does not know or care which is which; a transition is a
    transition, which is the whole point of off-policy learning.
    """

    def __init__(self, capacity: int, obs_dim: int = N_OBS,
                 act_dim: int = N_ACTIONS):
        if capacity <= 0:
            raise ValueError(f"capacity must be positive, got {capacity}")
        self.capacity = int(capacity)
        self.obs_dim = int(obs_dim)
        self.act_dim = int(act_dim)
        self._obs = np.zeros((capacity, obs_dim), dtype=np.float32)
        self._act = np.zeros((capacity, act_dim), dtype=np.float32)
        self._rew = np.zeros(capacity, dtype=np.float32)
        self._next = np.zeros((capacity, obs_dim), dtype=np.float32)
        self._done = np.zeros(capacity, dtype=np.float32)
        self._i = 0          # write cursor
        self._n = 0          # number of valid entries (<= capacity)

    def __len__(self) -> int:
        return self._n

    @property
    def full(self) -> bool:
        return self._n >= self.capacity

    def add(self, obs, act, rew: float, next_obs, done: bool) -> None:
        """Insert one transition, overwriting the oldest when full."""
        obs = np.asarray(obs, dtype=np.float32)
        act = np.asarray(act, dtype=np.float32)
        next_obs = np.asarray(next_obs, dtype=np.float32)
        if obs.shape != (self.obs_dim,):
            raise ValueError(f"obs shape {obs.shape} != ({self.obs_dim},)")
        if act.shape != (self.act_dim,):
            raise ValueError(f"act shape {act.shape} != ({self.act_dim},)")
        if next_obs.shape != (self.obs_dim,):
            raise ValueError(f"next_obs shape {next_obs.shape} != "
                             f"({self.obs_dim},)")
        if not (np.all(np.isfinite(obs)) and np.all(np.isfinite(act))
                and np.all(np.isfinite(next_obs)) and np.isfinite(rew)):
            # A non-finite transition is a broken evaluation upstream, and
            # storing one silently poisons every minibatch it is later drawn
            # into. Fail where it enters, not 100 000 gradient steps later.
            raise ValueError("refusing to store a non-finite transition")
        i = self._i
        self._obs[i] = obs
        self._act[i] = act
        self._rew[i] = float(rew)
        self._next[i] = next_obs
        self._done[i] = float(bool(done))
        self._i = (i + 1) % self.capacity
        self._n = min(self._n + 1, self.capacity)

    def add_batch(self, obs, act, rew, next_obs, done) -> int:
        """Insert many transitions at once. Returns the number inserted.

        Used by the pool seeder, which produces its transitions in bulk. Loops
        `add` so every row goes through the same finiteness and shape checks;
        the buffer is filled once at startup, so the per-row Python cost is
        paid once and never in the training loop.
        """
        obs = np.asarray(obs, dtype=np.float32)
        act = np.asarray(act, dtype=np.float32)
        rew = np.asarray(rew, dtype=np.float32).ravel()
        next_obs = np.asarray(next_obs, dtype=np.float32)
        done = np.asarray(done, dtype=np.float32).ravel()
        k = obs.shape[0]
        if not (act.shape[0] == rew.shape[0] == next_obs.shape[0]
                == done.shape[0] == k):
            raise ValueError("add_batch got ragged arrays")
        for j in range(k):
            self.add(obs[j], act[j], rew[j], next_obs[j], done[j])
        return k

    def sample(self, batch_size: int, rng: np.random.Generator) -> dict:
        """Uniform minibatch of `float32` arrays. Raises if too small.

        The `rng` is passed in rather than owned so the agent threads its one
        seed through here too (G3). Sampling with replacement is standard for a
        replay buffer and is what lets `batch_size` exceed the transient buffer
        size early in training.
        """
        if self._n == 0:
            raise ValueError("cannot sample from an empty buffer")
        idx = rng.integers(0, self._n, size=int(batch_size))
        return {
            "obs": self._obs[idx],
            "act": self._act[idx],
            "rew": self._rew[idx],
            "next_obs": self._next[idx],
            "done": self._done[idx],
        }


# ─────────────────────────────────────────────────────────────────────────────
# Pool seeding — the 17.4M SPICE-measured transitions, mined and HER-relabelled.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class SeedReport:
    """What the seeder did, in numbers. **Nothing is truncated silently.**

    A seeder that quietly caps its output reads as "used everything available"
    when it did not, so every reduction from the theoretical maximum is named
    here: the pairs available, the edges sampled, and how many of those became
    real / HER transitions vs were dropped for an unscorable endpoint.
    """

    pool_size: int
    #: **DIRECTED (ordered) adjacent pairs**, i.e. one per minable transition:
    #: `i -> j` and `j -> i` are different transitions with different actions and
    #: different rewards, so both count. `-1` when `count_available=False`.
    #:
    #: Named `directed` because the first version of this field held the
    #: UNDIRECTED count (34 789 444 / 2 = 17 394 722) while the docstring called
    #: it directed -- a factor of two between two names for one thing, which is
    #: this repo's failure mode 3. Say which one it is, in the name.
    n_directed_edges_available: int
    n_edges_requested: int
    n_edges_sampled: int
    n_real_target: int                   # scored against a training target
    n_her: int                           # relabelled to an achieved response
    n_dropped_unscorable: int            # reward_v1 refused the endpoint
    n_dropped_no_her_target: int         # endpoint response outside S3's box
    n_transitions: int                   # total inserted
    max_step: float
    seed_specs: tuple
    #: Whether a reached goal was stored as a TERMINATION. Recorded because it
    #: must match the env being trained: `corner_env.py` terminates on success,
    #: `analytic_env.py` NEVER terminates (it reverts instead, G100). Seeding
    #: terminal transitions into a non-terminating env gives the critic two
    #: different backups for the same state -- G114's third lever.
    seed_terminal_on_success: bool = True
    wall_s: float = 0.0

    def as_dict(self) -> dict:
        d = dict(self.__dict__)
        d["seed_specs"] = list(self.seed_specs)
        return d


def _achieved_target(peaking_db: float, f_peak_oct: float
                     ) -> Optional[SpecTarget]:
    """The `SpecTarget` a design's own response represents, or None if illegal.

    A design whose measured peaking or f_peak falls outside S3's advertised box
    is not a legal request, so its response cannot be a HER goal. Returning None
    (and letting the caller COUNT it) is the honest outcome; clamping it into
    the box would relabel the transition with a target the design never met.
    """
    f_hz = NYQUIST_HZ * (2.0 ** f_peak_oct)
    lo_db, hi_db = SPEC_PEAKING_DB_RANGE
    lo_hz, hi_hz = SPEC_F_PEAK_HZ_RANGE
    if not (lo_db <= peaking_db <= hi_db):
        return None
    if not (lo_hz <= f_hz <= hi_hz):
        return None
    try:
        return SpecTarget(peaking_db=float(peaking_db), f_peak_hz=float(f_hz))
    except ValueError:
        return None


def _score(meas: dict, target: SpecTarget,
           specs: Sequence[str] = SEED_SPECS) -> tuple[float, bool]:
    """`reward_v1.reward` on a pool measurement against a target. No simulation.

    The one scorer for seeded transitions, so the reward scale is defined once
    (rule 9). Returns `(reward, feasible)`; raises nothing the caller does not
    handle, because a `reward_v1` refusal on a valid pool row is a real drop to
    be counted, not an exception to swallow.

    **`specs` must be the row set the ENV being trained also scores.** That is
    G114's trap 2, stated as a parameter instead of a comment: the analytic env
    scores `V6A_SPECS` (5 rows, invalid floor -8) and the SPICE corner env scores
    `V6D_SPECS` (9 rows, floor -12). A buffer seeded on one scale and topped up
    from an env on the other gives the critic two incompatible reward ranges for
    the same states, which is one of the three uncontrolled changes that erased
    the PPO policy.
    """
    rb = R.reward(meas, target.f_peak_hz, specs=tuple(specs),
                  target_peaking_db=target.peaking_db)
    return float(rb.reward), bool(rb.feasible)


def mine_pool_transitions(
    pool,
    targets: Sequence[SpecTarget],
    n_transitions: int,
    *,
    seed: int,
    her_frac: float = 0.5,
    max_step: float = MAX_STEP,
    horizon: int = HORIZON,
    count_available: bool = True,
    specs: Sequence[str] = SEED_SPECS,
    terminal_on_success: bool = True,
) -> tuple[dict, SeedReport]:
    """Mine `(s, a, r, s', done)` transitions from the pool. **Zero SPICE.**

    For each of `n_transitions` sampled directed adjacent edges `i -> j`
    (`||u_j - u_i||_inf <= max_step`), build a transition:

      * action `a = (u_j - u_i) / max_step`, exact and in `[-1, 1]`;
      * target `T`: with probability `her_frac` the response design `j`
        actually achieved (HER), otherwise a target drawn from `targets` (the
        same distribution the env samples), so the critic sees the full reward
        range rather than only "already at the goal";
      * reward `= reward_v1.reward(meas_j, T)` — scored at the RESULTING state,
        matching `rl/env.py`;
      * `done`: for a HER transition, True — the relabelled goal is reached, the
        standard HER convention. For a real-target transition, `feasible(j, T)`,
        which matches the SPICE env's early-success termination
        (`corner_env.py`). The G100 tension (early-success termination is two
        objectives) is the ENV's to resolve; a seeded transition must carry the
        same `done` the live env would, or the critic bootstraps inconsistently.
        **`terminal_on_success=False` forces every `done` to 0**, which is what
        `analytic_env.py` requires: that env never terminates (it reverts a bad
        edit and always returns `terminated=False`), so a terminal seeded
        transition would give the critic `Q = r` for a state the env itself
        backs up as `r + gamma*Q'`. That disagreement is G114's third lever
        (changed episode dynamics), made a parameter rather than a comment.
      * step: sampled uniformly in `[0, horizon - 2]` so `step + 1 <= horizon-1`.
        A mined pair has no trajectory position; spreading it over the episode
        phase is honest about that rather than pinning every synthetic edit to
        step 0.

    Neighbours are found with a batched k-nearest query (`KNN` candidates per
    source, filtered to those within `max_step`) rather than a full radius ball.
    A design can have thousands of neighbours; materialising all of them per
    edge is what made an earlier version 400x slower. Sampling among the `KNN`
    NEAREST also biases toward smaller `||a||`, which is a feature: a tanh
    policy almost never emits `|a_i| = 1`, so the closer pairs are the more
    policy-realistic transitions.

    Returns `(batch, report)` where `batch` is the dict `ReplayBuffer.add_batch`
    consumes. `report` states the directed-edge denominator and every drop, and
    records the `specs` the rewards were scored on so a later reader can check
    the scale matched the env (G114 trap 2).
    """
    from scipy.spatial import cKDTree

    if not targets:
        raise ValueError("mining needs training targets for the non-HER half")
    if not (0.0 <= her_frac <= 1.0):
        raise ValueError(f"her_frac must be in [0, 1], got {her_frac}")
    if n_transitions <= 0:
        raise ValueError(f"n_transitions must be positive, got {n_transitions}")
    if not specs:
        raise ValueError("scoring needs a spec row set; see G114 trap 2")
    specs = tuple(specs)

    #: k-nearest candidates fetched per source. Larger than the median
    #: neighbour count (15, measured) so a source rarely exhausts its
    #: candidates, small enough that the query stays cheap.
    KNN = 32

    t0 = time.perf_counter()
    rng = np.random.default_rng(seed)
    u = np.asarray(pool.u, dtype=float)
    n = u.shape[0]
    if u.shape[1] != N_ACTIONS:
        raise ValueError(f"pool sizing width {u.shape[1]} != {N_ACTIONS}")

    tree = cKDTree(u)
    n_edges_available = -1
    if count_available:
        # `count_neighbors` returns ORDERED pairs and includes each point with
        # itself, so subtracting `n` leaves the directed edge count. Do NOT
        # halve it: the seeder draws `i -> j` and `j -> i` as separate
        # transitions (different action, different reward), so the directed
        # count is the denominator that matches what can actually be mined.
        both = int(tree.count_neighbors(tree, r=max_step, p=np.inf))
        n_edges_available = both - n

    targets = list(targets)
    obs_l, act_l, rew_l, next_l, done_l = [], [], [], [], []
    n_real = n_her = 0
    n_drop_unscorable = n_drop_no_her = 0
    n_sampled = 0

    # Sample edges in chunks: batch-query the k nearest of many sources at once
    # (vectorised in scipy), then pick one in-radius neighbour per source in
    # Python. Never materialises the full 17.4M adjacency.
    guard = 0
    max_guard = n_transitions * 20 + 10_000
    while len(obs_l) < n_transitions and guard < max_guard:
        chunk = min(max(2 * (n_transitions - len(obs_l)), 4096), 50_000)
        src = rng.integers(n, size=chunk)
        dist, idx = tree.query(u[src], k=min(KNN + 1, n), p=np.inf,
                               workers=-1)
        dist = np.atleast_2d(dist)
        idx = np.atleast_2d(idx)
        for row in range(chunk):
            guard += 1
            if len(obs_l) >= n_transitions:
                break
            i = int(src[row])
            cand = idx[row][(dist[row] <= max_step) & (idx[row] != i)]
            if cand.size == 0:
                continue
            j = int(cand[int(rng.integers(cand.size))])
            n_sampled += 1

            a = (u[j] - u[i]) / max_step
            # Guaranteed in [-1, 1] by the radius, but clip defensively: a float
            # round-trip at exactly the radius could land at 1.0 + 1e-16.
            a = np.clip(a, -1.0, 1.0)

            use_her = rng.random() < her_frac
            if use_her:
                t = _achieved_target(pool.meas[j]["peaking_db"],
                                     pool.meas[j]["f_peak_oct"])
                if t is None:
                    n_drop_no_her += 1
                    continue
            else:
                t = targets[int(rng.integers(len(targets)))]

            try:
                rew, feasible = _score(pool.meas[j], t, specs)
            except (KeyError, ValueError):
                n_drop_unscorable += 1
                continue

            step = int(rng.integers(0, max(1, horizon - 1)))
            try:
                obs = build_observation(u[i], pool.meas[i], t.peaking_db,
                                        t.f_peak_hz, step, horizon)
                next_obs = build_observation(u[j], pool.meas[j], t.peaking_db,
                                             t.f_peak_hz, step + 1, horizon)
            except (KeyError, ValueError):
                n_drop_unscorable += 1
                continue

            done = True if use_her else feasible
            if not terminal_on_success:
                done = False
            obs_l.append(obs)
            act_l.append(a)
            rew_l.append(rew)
            next_l.append(next_obs)
            done_l.append(done)
            n_her += int(use_her)
            n_real += int(not use_her)

    batch = {
        "obs": np.asarray(obs_l, dtype=np.float32),
        "act": np.asarray(act_l, dtype=np.float32),
        "rew": np.asarray(rew_l, dtype=np.float32),
        "next_obs": np.asarray(next_l, dtype=np.float32),
        "done": np.asarray(done_l, dtype=np.float32),
    }
    report = SeedReport(
        pool_size=n,
        n_directed_edges_available=n_edges_available,
        n_edges_requested=int(n_transitions),
        n_edges_sampled=n_sampled,
        n_real_target=n_real,
        n_her=n_her,
        n_dropped_unscorable=n_drop_unscorable,
        n_dropped_no_her_target=n_drop_no_her,
        n_transitions=len(obs_l),
        max_step=float(max_step),
        seed_specs=specs,
        seed_terminal_on_success=bool(terminal_on_success),
        wall_s=time.perf_counter() - t0,
    )
    return batch, report


def seed_from_pool(
    buffer: ReplayBuffer,
    targets: Sequence[SpecTarget],
    n_transitions: int,
    *,
    seed: int,
    her_frac: float = 0.5,
    pool=None,
    specs: Sequence[str] = SEED_SPECS,
    terminal_on_success: bool = True,
) -> SeedReport:
    """Load the pool, mine transitions, fill `buffer`. Returns the `SeedReport`.

    The one call a training script makes to convert sunk simulations into
    replay data. `pool` may be passed in to avoid re-parsing 74 526 rows when
    the caller already holds it (G123: `load_pool` is uncached).

    **Two arguments must match the env you are about to train on**, because they
    are two of G114's three levers, and the defaults here are the SPICE env's:

    * `specs` — the reward scale. The default is `SEED_SPECS` (= `V6D_SPECS`,
      9 rows, invalid floor -12); training on the analytic env means passing
      `analytic_env.V6A_SPECS` (5 rows, floor -8) instead.
    * `terminal_on_success` — the episode dynamics. `corner_env.py` terminates
      on success, so the default is True; `analytic_env.py` never terminates, so
      training there requires False.

    Getting either wrong does not raise. It gives the critic two incompatible
    descriptions of the same state, which is how the PPO policy was erased.
    """
    if pool is None:
        from nebula.experiments.spec_pool import load_pool
        pool = load_pool()
    batch, report = mine_pool_transitions(
        pool, targets, n_transitions, seed=seed, her_frac=her_frac,
        specs=specs, terminal_on_success=terminal_on_success)
    buffer.add_batch(**batch)
    return report


__all__ = [
    "ReplayBuffer",
    "SeedReport",
    "mine_pool_transitions",
    "seed_from_pool",
    "SEED_SPECS",
]
