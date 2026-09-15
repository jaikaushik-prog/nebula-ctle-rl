"""
rl/analytic_env.py — **the same MDP with the simulator taken out, so a policy
can be pre-trained a thousand times faster and then corrected on SPICE.**

WHY THIS EXISTS, WITH THE MEASUREMENT THAT MOTIVATES IT
--------------------------------------------------------
Session 23 trained a corner-aware policy for 1200 environment steps and it
learned nothing measurable. The evidence is not the score, it is the parameter
that tracks learning: PPO's `log_std` starts at 0.0 and **shrinks** as a policy
becomes confident. After training it read **-0.05 to +0.053** -- unmoved. The
exploration noise (sigma ~ 1.0) is also as large as the entire tanh-bounded
action, so what the policy "chose" was mostly drowned out by its own sampling.

**1200 steps is not a small training run for this problem; it is ~1 % of one.**
PPO on a 7-D continuous control task normally needs 10^5-10^6 steps. The reason
we ran 1200 is arithmetic:

    one step = 4 SPICE decks = 1.26 s

        1 200 steps       0.4 hours     <- what was run
       12 000 steps       4.2 hours
      120 000 steps      42   hours     <- roughly what PPO needs
    1 000 000 steps     350   hours

**So the blocker was never the algorithm. It was the cost of a practice
attempt.** In ordinary RL the environment is a game or a physics model at
microseconds per step; here it is a circuit simulator. This module makes the
practice attempts cheap:

    analytic step (4 corners)   0.0009 s     measured, 1386x faster
    1 000 000 steps             15 minutes   against 350 hours

WHAT IT PREDICTS, AND WHAT IT CANNOT
--------------------------------------
`experiments/prescreen.predict_response` returns a one-zero/two-pole fit of the
CTLE's AC response for zero simulations. Measured against SPICE on the
calibration set (`prescreen.accuracy()`):

    f_peak median absolute error      4.93 %
    f_peak bias                      -0.023 octaves    (essentially unbiased)
    peaking mean absolute error       0.284 dB
    peaking bias                     -0.009 dB
    f_peak p99 absolute error          1.078 octaves   <- THE TAIL, see below

So it is accurate and unbiased **typically**, and about 1 % of the time it is
off by a full octave. That profile is right for pre-training and wrong for
anything else.

**It predicts four of the eight observation channels and five of the nine
`V6D_SPECS` rows** -- and they are the ones that bind:

    predicted     g_dc_db, peaking_db, f_peak_oct, nyq_boost_db
    NOT predicted inoise_vrms, power_w, pair_margin_v, tail_margin_v

THE HONEST-DEFAULT PROBLEM, AND HOW IT IS BOUNDED
---------------------------------------------------
This project's standing rule is that a measurement is never defaulted: a spec
nobody measured must raise rather than be filled in (rule 5, and `margins()`
omits unmeasured rows on purpose so the attempt fails loudly).

**This module deliberately fills four observation channels with stated
constants, and that is only defensible because of what it is forbidden to do:**

* it scores `V6A_SPECS` -- the five rows the analytic model actually predicts.
  It does **not** score noise, power or saturation, so no reward here depends
  on a filled-in number;
* the filled channels are `OBS_SCALES` centres, i.e. exactly the value that
  normalises to zero, so they carry **no** information rather than misleading
  information;
* **no number produced by this module may appear in any deliverable.** It
  trains a policy. The policy is then fine-tuned and MEASURED on real SPICE,
  and only those numbers are reportable. `is_analytic = True` is stamped on
  every result this env produces so a downstream consumer cannot mistake one
  for a measurement.

If those three conditions ever stop holding, this module becomes exactly the
"invented number in a deliverable" failure the rules exist to prevent.

    from nebula.rl.analytic_env import AnalyticCtleEnv
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np

import nebula.rl.reward_v1 as R
from nebula.rl.contract import (
    HORIZON,
    MAX_STEP,
    N_ACTIONS,
    OBS_SCALES,
    build_observation,
    sizing_from_u,
)

#: **The rows the analytic model can actually score.** Five of `V6D_SPECS`'s
#: nine, and the four that bind. Listed by ENUMERATION (G101/G106).
#:
#: `S5_noise`, `S6_power`, `saturation` and `tail_saturation` are absent because
#: `predict_response` does not predict them. Including them would mean scoring a
#: number nobody computed, which is rule 5's failure with extra steps.
V6A_SPECS: tuple[str, ...] = (
    "S3_f_peak_band", "S3_f_peak_match",
    "S3_peaking", "S3_peaking_match", "S3_nyq_boost",
)

#: Observation channels the analytic model does not predict. Filled with each
#: channel's own `OBS_SCALES` centre, which normalises to exactly 0.0 -- no
#: information rather than wrong information. Named here so the set is
#: auditable rather than buried in a dict literal.
UNPREDICTED_CHANNELS: tuple[str, ...] = (
    "inoise_vrms", "power_w", "pair_margin_v", "tail_margin_v",
)


@dataclass
class AnalyticStep:
    """One analytic evaluation. `is_analytic` is not decoration."""

    ok: bool
    reward: float
    feasible: bool
    meas: dict = field(default_factory=dict)
    margins: dict = field(default_factory=dict)
    worst_spec: Optional[str] = None
    reason: Optional[str] = None
    #: **Stamped on every result.** A consumer that cannot tell an analytic
    #: estimate from a SPICE measurement will eventually publish one as the
    #: other; this is the field that makes that a type error rather than a
    #: judgement call.
    is_analytic: bool = True


class AnalyticCtleEnv:
    """`CtleSizingEnv`'s MDP, scored analytically. **Zero SPICE calls.**

    Deliberately duck-typed to `CornerCtleEnv` rather than subclassing it: the
    two share no code path, so there is no way for an analytic score to reach a
    SPICE-scored run by inheritance. The only thing they share is the
    OBSERVATION, which comes from `contract.build_observation` in both -- that
    is the whole point, because a policy pre-trained here has to be loadable
    there.

    **An invalid edit does NOT end the episode here.** `rl/env.py` terminates
    on an unbuildable design, and it is right to: it cannot show the policy an
    observation it could not measure. This env can always evaluate, so the
    episode continues and the policy gets all `horizon` moves -- which is the
    second half of why the SPICE run learned nothing (measured: 1-3 of 8 moves
    at evaluation, because the first bad edit ended the episode).
    """

    def __init__(self, targets: Sequence, seed: int,
                 specs: Sequence[str] = V6A_SPECS,
                 horizon: int = HORIZON, max_step: float = MAX_STEP):
        if not targets:
            raise ValueError("an analytic env needs spec targets to sample")
        self.targets = list(targets)
        self.specs = tuple(specs)
        self.horizon = int(horizon)
        self.max_step = float(max_step)
        self.rng = np.random.default_rng(seed)
        self.observation_dim = 7 + 8 + 2 + 1
        self.action_dim = N_ACTIONS

        self._u = np.full(N_ACTIONS, 0.5)
        self._step = 0
        self._target = self.targets[0]
        self._last_meas: Optional[dict] = None
        #: Counters the caller reports rather than guesses at.
        self.n_evals = 0
        self.n_unpredictable = 0
        self.n_reverted = 0

    # -- the model ------------------------------------------------------------

    def _measure(self, u) -> Optional[dict]:
        """Analytic `meas`, or None when the model cannot describe the design.

        `None` is a real outcome: `predict_response` raises on geometries it
        cannot fit, and inventing a response for those would teach the policy
        that unrealisable designs are fine.
        """
        from nebula.experiments import prescreen as P

        try:
            pr = P.predict_response(sizing_from_u(np.asarray(u)).params)
        except Exception:                                       # noqa: BLE001
            return None
        if not all(np.isfinite([pr.f_peak_hz, pr.peaking_db, pr.nyq_boost_db])):
            return None
        if pr.f_peak_hz <= 0.0:
            return None

        centres = {s.name: s.centre for s in OBS_SCALES}
        meas = {name: float(centres[name]) for name in UNPREDICTED_CHANNELS}
        meas.update({
            # `g_dc_db` is not in V6A and is carried only so the observation
            # has the shape the policy will meet on SPICE.
            "g_dc_db": float(centres["g_dc_db"]),
            "peaking_db": float(pr.peaking_db),
            "f_peak_oct": float(pr.f_peak_oct),
            "nyq_boost_db": float(pr.nyq_boost_db),
        })
        return meas

    def _score(self, meas: Optional[dict]) -> AnalyticStep:
        if meas is None:
            self.n_unpredictable += 1
            return AnalyticStep(
                ok=False, reward=R.invalid_reward(len(self.specs)),
                feasible=False,
                reason="the analytic model cannot describe this geometry")
        rb = R.reward(meas, self._target.f_peak_hz, specs=self.specs,
                      target_peaking_db=self._target.peaking_db)
        return AnalyticStep(
            ok=True, reward=float(rb.reward), feasible=bool(rb.feasible),
            meas=meas, margins={k: float(v) for k, v in rb.margins.items()},
            worst_spec=rb.worst_spec)

    def _obs(self, meas: dict) -> np.ndarray:
        return build_observation(self._u, meas, self._target.peaking_db,
                                 self._target.f_peak_hz, self._step,
                                 self.horizon)

    @property
    def u(self) -> np.ndarray:
        """The design the env is CURRENTLY at, as a copy.

        Additive and read-only. A rollout that wants the best design it visited
        needs the design, and `step` returns an observation; slicing `u` back
        out of the observation would couple a caller to the observation layout
        and fail silently the day that layout changes. Returning a copy stops a
        caller mutating the env's state by accident.
        """
        return self._u.copy()

    # -- the MDP --------------------------------------------------------------

    def reset(self, u0=None):
        """Fresh target, fresh start point. Retries until the model can fit."""
        self._target = self.targets[int(self.rng.integers(len(self.targets)))]
        for _ in range(64):
            self._u = (np.asarray(u0, dtype=float).copy() if u0 is not None
                       else self.rng.uniform(0.0, 1.0, N_ACTIONS))
            self._step = 0
            m = self._measure(self._u)
            self.n_evals += 1
            if m is not None:
                self._last_meas = m
                return self._obs(m), {"is_analytic": True}
            if u0 is not None:
                raise ValueError(
                    "the requested start point cannot be described by the "
                    "analytic model; a seeded start must be checked, not "
                    "assumed")
        raise RuntimeError(
            "64 random starts and the analytic model fitted none of them -- "
            "the box or the model is broken, not the draw")

    def step(self, action):
        """One edit. **A bad edit is REVERTED, not fatal.**

        `rl/env.py` ends the episode on an unbuildable design because it cannot
        build an observation for one. Here the alternative is available and is
        strictly better for learning: undo the edit, hand back the observation
        of the design we are ACTUALLY at (which is true, not stale), charge the
        move, and let the policy try again. A policy punished by having the game
        ended cannot learn to back out of a corner -- it only ever sees that the
        corner is where episodes stop.
        """
        a = np.asarray(action, dtype=float).ravel()
        if a.shape[0] != N_ACTIONS:
            raise ValueError(f"expected {N_ACTIONS} action dims, got {a.shape[0]}")
        if not np.all(np.isfinite(a)):
            raise ValueError("action contains nan/inf - a policy blow-up")

        u_before = self._u.copy()
        delta = np.clip(a, -1.0, 1.0) * self.max_step
        self._u = np.clip(self._u + delta, 0.0, 1.0)
        self._step += 1

        m = self._measure(self._u)
        self.n_evals += 1
        ev = self._score(m)

        if m is None:
            # Revert, and report the LAST TRUE observation. The design is
            # genuinely back where it was, so nothing here is stale.
            self._u = u_before
            self.n_reverted += 1
            assert self._last_meas is not None
            obs = self._obs(self._last_meas)
            truncated = self._step >= self.horizon
            return obs, ev.reward, False, truncated, {
                "is_analytic": True, "reverted": True, "reason": ev.reason}

        self._last_meas = m
        obs = self._obs(m)
        # **No early-success termination** (G100): an episode that ends on the
        # condition the metric rewards exceeding is two objectives, not one.
        # The policy keeps its remaining moves and may buy margin with them.
        truncated = self._step >= self.horizon
        return obs, ev.reward, False, truncated, {
            "is_analytic": True, "reverted": False,
            "feasible": ev.feasible, "worst_spec": ev.worst_spec,
            "margins": ev.margins}

    # -- reporting ------------------------------------------------------------

    def report(self) -> dict:
        return {"is_analytic": True, "n_evals": self.n_evals,
                "n_unpredictable": self.n_unpredictable,
                "n_reverted": self.n_reverted,
                "specs": list(self.specs), "horizon": self.horizon,
                "note": ("analytic pre-training only; no number from this env "
                         "is reportable, every policy trained here is "
                         "fine-tuned and measured on SPICE")}


__all__ = ["AnalyticCtleEnv", "AnalyticStep", "V6A_SPECS",
           "UNPREDICTED_CHANNELS"]
