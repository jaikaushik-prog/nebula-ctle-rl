"""
rl/swing_env.py -- **the swing-aware training reward. A wrapper, deliberately.**

WHY THIS EXISTS
----------------
Entry 36 measured why SAC fails as a proposer: **its failing designs score
HIGHER on its own training reward (+6.555) than the library designs that pass
the corner screen (+6.530)**, because the quantity doing 95 % of the rejecting
-- the measured 1 dB output-swing compression point -- is not in `V6A_SPECS` and
cannot be. Entry 37 then measured that the same quantity **is predictable from
the design vector to 4.7 % with no SPICE**. This module puts the prediction into
the training reward. Pre-registered as entry 38; authorised by the owner as
`PROGRESS.md` row 4p (standing rule 6's human decision).

WHY A WRAPPER AND NOT A ROW IN `reward_v1.py`
-----------------------------------------------
**A surrogate number must not be able to reach a deliverable.** A new row inside
`reward_v1.py` is visible to the screen, to `exp_coverage` and to the compliance
matrix; a wrapper is visible only to whatever chooses to train through it. The
screen goes on MEASURING swing, `link/calibration.py` goes on refusing to score
a compressing stage, and nothing in this file can change either. Same precedent
as `corner_env`, `analytic_env`, `episode_dynamics` and
`SpecConditionedCornerEnv`: **wrap, do not replace.**

THE PENALTY, AND WHY ITS TWO CONSTANTS ARE WHAT THEY ARE
----------------------------------------------------------
    predicted = surrogate(u)                       entry 37's model
    shortfall = max(0, (TARGET - predicted) / TARGET)          in [0, 1]
    reward    = V6A_reward - SWING_W * shortfall

* **`TARGET = 1.00 V` is derived, not chosen.** Across **3 374** recorded
  compressions in this repo the *required* output swing has median **988 mV**
  (p25 706, p75 1339). The target is the median demand, rounded. 21.4 % of the
  2 228 harvested designs already clear it: demanding, not vacuous.
* **`SWING_W = 6.0`** makes a design with zero headroom lose approximately its
  whole shape score (a good `V6A` score is ~ +6.5). **It is registered, not
  tuned. If entry 38 misses, this value is NOT re-rolled** (G110); a second
  value is a new pre-registration.

The observation is **unchanged at 18 dimensions** -- the policy is not told its
predicted swing. `u` is already in the observation, so the information is
reachable, and the checkpoint contract stays identical to entries 34-36, which
is what makes "the reward is the only difference" true.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

#: Median required output swing across 3 374 recorded compressions, rounded.
SWING_TARGET_V: float = 1.00

#: The one hyper-parameter. Registered in entry 38; not to be re-rolled.
SWING_W: float = 6.0


class SwingAwareEnv:
    """`AnalyticCtleEnv` with a predicted-headroom shortfall penalty.

    Duck-typed to the env it wraps -- `observation_dim`, `action_dim`,
    `reset()`, `step()`, `horizon` -- so `sac.train` cannot tell the difference,
    and neither can a checkpoint.

    **Counters are kept because a term that is computed and discarded is this
    repo's most common silent failure.** `n_penalised` and `sum_shortfall` are
    what let entry 38's Q2 distinguish "the penalty did nothing" from "the
    penalty did something and it did not help".
    """

    def __init__(self, base, surrogate, target_v: float = SWING_TARGET_V,
                 weight: float = SWING_W):
        if target_v <= 0:
            raise ValueError(f"target must be positive, got {target_v}")
        if weight < 0:
            raise ValueError(f"weight must be non-negative, got {weight}")
        self.env = base
        self.surrogate = surrogate
        self.target_v = float(target_v)
        self.weight = float(weight)
        self.observation_dim = base.observation_dim
        self.action_dim = base.action_dim
        self.horizon = base.horizon
        self.n_steps = 0
        self.n_penalised = 0
        self.sum_shortfall = 0.0
        self.last_predicted_v: Optional[float] = None

    # -- the surrogate --------------------------------------------------------

    def predicted_swing_v(self, u) -> float:
        from nebula.experiments.exp_swing_surrogate import features

        x = np.asarray(features(u), dtype=float).reshape(1, -1)
        return float(self.surrogate.predict(x)[0])

    def shortfall(self, u) -> float:
        """Fraction of the target the design falls short by, in `[0, 1]`."""
        pred = self.predicted_swing_v(u)
        self.last_predicted_v = pred
        return float(np.clip((self.target_v - pred) / self.target_v, 0.0, 1.0))

    # -- the MDP --------------------------------------------------------------

    def reset(self, u0=None):
        return self.env.reset() if u0 is None else self.env.reset(u0)

    def step(self, action):
        obs, reward, term, trunc, info = self.env.step(action)
        s = self.shortfall(self.env.u)
        penalty = self.weight * s
        self.n_steps += 1
        self.sum_shortfall += s
        if penalty > 0:
            self.n_penalised += 1
        info = dict(info)
        info.update({"swing_predicted_v": self.last_predicted_v,
                     "swing_shortfall": s, "swing_penalty": penalty,
                     "is_surrogate": True})
        return obs, float(reward) - penalty, term, trunc, info

    # -- passthrough + reporting ---------------------------------------------

    @property
    def u(self) -> np.ndarray:
        return self.env.u

    def report(self) -> dict:
        base = self.env.report() if hasattr(self.env, "report") else {}
        return {**base, "swing_target_v": self.target_v,
                "swing_weight": self.weight, "swing_steps": self.n_steps,
                "swing_penalised": self.n_penalised,
                "swing_mean_shortfall": (self.sum_shortfall / self.n_steps
                                         if self.n_steps else None),
                "is_surrogate": True}


__all__ = ["SwingAwareEnv", "SWING_TARGET_V", "SWING_W"]
