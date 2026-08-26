"""
rl/screen_env.py -- **train on the thing we are scored on. The corner screen
itself, as the reward.**

WHY THIS EXISTS, AND WHAT IT FIXES THAT ENTRY 35 DID NOT
----------------------------------------------------------
Four experiments have measured SAC losing to a library lookup:

    entry 36   SAC as proposer         1 of 16   against retrieval's 6 of 16
    entry 38   + a swing-aware reward  0-1 of 16 -- the fix WORKED and did not pay

Entry 38's failure breakdown is the clue. Once output-swing compression was
fixed, the rejections moved to **`S3_peaking_match` and `S3_f_peak_match` --
rows the policy was explicitly trained to hit.** How does a policy trained to
hit a peaking target miss on peaking?

**Because it is trained at NOMINAL and scored at CORNERS.**
`prescreen.predict_response` returns one response for one operating point. The
screen takes the **worst of four** (corner, load) pairs. The measured corner
spread on `f_peak` is **0.23-0.30 octaves** against a 0.5 tolerance, so a design
that lands dead centre at nominal can be outside tolerance at a corner while its
training reward reports success.

**`CLAUDEwa.md` names this trap in its own words:** *"optimising at nominal and
checking corners afterwards -- score on worst corner from the start."* Entry 35
closed the analytic-vs-SPICE gap; **this closes the nominal-vs-corner gap**,
which is the one that was left.

THE PROPERTY THAT MAKES THIS DIFFERENT
----------------------------------------
`step()` scores through **`adaptive_screen.evaluate_at_points` on
`EDGE4_MANDATED` with `V6_SPECS`** -- the *same function, points and spec set*
that decide whether a proposal is accepted. So the reward the policy climbs and
the metric it is judged on are **one definition, not two** (CLAUDEwa.md section 8
rule 9). There is no transfer left to survive: the training signal IS the
acceptance criterion.

The price is honest and large: **4 SPICE decks per step**, against the analytic
env's zero. That is the whole reason this was not tried first, and the owner has
now decided the cost is worth paying.

WARM STARTS, AND WHY THE DATA ASKS FOR THEM
---------------------------------------------
Entry 36 measured the policy **destroying five of the six designs retrieval
found** when started from them. Those states are exactly where it needs to learn
restraint, and a policy that only ever starts from random points never visits
them. `start_from_library=True` begins episodes at a library candidate for the
sampled target, so the states it is asked to improve are the states it fails on.

    from nebula.rl.screen_env import ScreenEnv
"""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np

import nebula.rl.reward_v1 as R
from nebula.rl.contract import N_ACTIONS, build_observation

#: The MDP shape. The observation contract matches `AnalyticCtleEnv` so a
#: checkpoint loads either way; the HORIZON does not, and deliberately: 8 edits
#: was chosen when a step cost nothing to simulate. Here a step costs 4 decks
#: and the policy is being asked to REPAIR a retrieved design, which needs room.
HORIZON: int = 16
MAX_STEP: float = 0.15


class ScreenEnv:
    """The 4-corner screen as an RL environment. **Every step costs 4 decks.**

    Duck-typed to `AnalyticCtleEnv`: `observation_dim`, `action_dim`, `reset`,
    `step`, `horizon`, `u`. A policy trained here loads into the analytic env
    and vice versa, because both build their observation through
    `contract.build_observation`.

    **A bad edit is REVERTED, not fatal** -- the lesson of G114's third lever,
    which is why PPO only ever got 1-3 of its 8 moves on the bare SPICE env.
    """

    def __init__(self, targets: Sequence, seed: int,
                 specs: Sequence[str] = R.V6_SPECS,
                 horizon: int = HORIZON, max_step: float = MAX_STEP,
                 start_from_library: bool = True,
                 library_k: int = 16, points=None,
                 surrogate_filter: bool = True,
                 min_start_swing_v: float = 0.9):
        from nebula.experiments.adaptive_screen import EDGE4_MANDATED

        if not targets:
            raise ValueError("a spec-conditioned env needs targets to sample")
        self.targets = list(targets)
        self.specs = tuple(specs)
        self.horizon = int(horizon)
        self.max_step = float(max_step)
        self.rng = np.random.default_rng(seed)
        self.points = list(points if points is not None else EDGE4_MANDATED)
        self.start_from_library = bool(start_from_library)
        self.library_k = int(library_k)
        # **The start distribution is the difference between a three-day run
        # that learns and one that does not.** `evaluate_at_points` grades an
        # unscorable design as `invalid_reward + n_scorable/4` -- a FOUR-LEVEL
        # staircase -- and entry 32 measured 116 of 128 library candidates
        # unscorable, essentially all on output-swing compression. A policy
        # started there sees almost no gradient. Entry 37's surrogate predicts
        # that compression point to 4.7 % for ZERO simulations, so it is used
        # to pick starts inside the measurable region. It never touches the
        # reward -- the reward stays the screen's own (rule 9).
        self.surrogate_filter = bool(surrogate_filter)
        self.min_start_swing_v = float(min_start_swing_v)
        self._surrogate = None
        self.n_starts_filtered = 0

        self.observation_dim = 7 + 8 + 2 + 1
        self.action_dim = N_ACTIONS

        self._u = np.full(N_ACTIONS, 0.5)
        self._step = 0
        self._target = self.targets[0]
        self._last: Optional[object] = None
        #: Counters the caller reports rather than guesses at (G112).
        self.n_evals = 0
        self.n_decks = 0
        self.n_reverted = 0
        self.n_unscorable = 0
        self.n_feasible_steps = 0
        self.n_warm_starts = 0

    # -- scoring: ONE definition, the screen's own ---------------------------

    def _evaluate(self, u) -> object:
        """`evaluate_at_points` -- the function acceptance is decided by.

        Not a reimplementation and not a subset: the same points, the same spec
        set, the same worst-corner rule. That identity is the entire design.
        """
        from nebula.experiments.adaptive_screen import evaluate_at_points

        ev = evaluate_at_points(
            np.asarray(u, dtype=float), self.points,
            target_f_peak_hz=float(self._target.f_peak_hz),
            target_peaking_db=float(self._target.peaking_db),
            specs=self.specs)
        self.n_evals += 1
        self.n_decks += int(ev.n_sims)
        if not ev.ok:
            self.n_unscorable += 1
        if ev.feasible:
            self.n_feasible_steps += 1
        return ev

    def _obs(self, ev) -> np.ndarray:
        """The observation contract, filled from the WORST corner's measurement.

        A policy that saw a nominal measurement while being rewarded on the
        worst corner would be asked to predict a number it cannot see -- the
        same split this env exists to remove.
        """
        from nebula.rl.analytic_env import OBS_SCALES

        centres = {s.name: s.centre for s in OBS_SCALES}
        meas = {name: float(c) for name, c in centres.items()}
        for k in ("g_dc_db", "peaking_db", "nyq_boost_db", "inoise_vrms",
                  "power_w", "pair_margin_v", "tail_margin_v"):
            v = getattr(ev, k, None)
            if v is not None and np.isfinite(v):
                meas[k] = float(v)
        if getattr(ev, "f_peak_hz", None):
            from nebula.rl.contract import f_peak_octaves
            meas["f_peak_oct"] = float(f_peak_octaves(ev.f_peak_hz))
        return build_observation(self._u, meas, self._target.peaking_db,
                                 self._target.f_peak_hz, self._step,
                                 self.horizon)

    # -- the MDP -------------------------------------------------------------

    def _library_start(self) -> Optional[np.ndarray]:
        """A library candidate for this target. **Zero simulations.**

        Entry 36 measured the policy destroying five of the six designs
        retrieval found. Starting episodes there is how it gets the chance to
        learn not to.
        """
        from nebula.experiments import exp_coverage as C

        cands = C.library_candidates(float(self._target.f_peak_hz),
                                     float(self._target.peaking_db),
                                     k=self.library_k)
        if not cands:
            return None
        if self.surrogate_filter:
            keep = self._with_headroom(cands)
            if keep:
                self.n_starts_filtered += 1
                cands = keep
        i = int(self.rng.integers(len(cands)))
        return np.asarray(cands[i], dtype=float)

    def _with_headroom(self, cands: list) -> list:
        """Library candidates whose PREDICTED compression point clears the bar.

        Zero simulations. Returns `[]` when the surrogate is unavailable or
        nothing clears, and the caller then falls back to the unfiltered list --
        a missing model must degrade the start distribution, never the run.
        """
        try:
            if self._surrogate is None:
                from nebula.experiments.exp_swing_surrogate import load_surrogate
                self._surrogate, _ = load_surrogate()
            from nebula.experiments.exp_swing_surrogate import features

            X = np.array([features(u) for u in cands], dtype=float)
            pred = self._surrogate.predict(X)
            return [u for u, p in zip(cands, pred)
                    if float(p) >= self.min_start_swing_v]
        except Exception:                                       # noqa: BLE001
            return []

    def reset(self, u0=None):
        self._target = self.targets[int(self.rng.integers(len(self.targets)))]
        self._step = 0
        for _ in range(16):
            if u0 is not None:
                self._u = np.asarray(u0, dtype=float).copy()
            elif self.start_from_library:
                lib = self._library_start()
                self._u = (lib if lib is not None
                           else self.rng.uniform(0.0, 1.0, N_ACTIONS))
                if lib is not None:
                    self.n_warm_starts += 1
            else:
                self._u = self.rng.uniform(0.0, 1.0, N_ACTIONS)
            ev = self._evaluate(self._u)
            if ev.ok or u0 is not None:
                self._last = ev
                return self._obs(ev), {"is_analytic": False,
                                       "feasible": bool(ev.feasible)}
            # An unscorable start is a bad place to begin an episode, not a
            # failure: draw again rather than teaching the policy from a state
            # whose observation is mostly filled-in centres.
        self._last = ev
        return self._obs(ev), {"is_analytic": False, "unscorable_start": True}

    def step(self, action):
        a = np.asarray(action, dtype=float).ravel()
        if a.shape[0] != N_ACTIONS:
            raise ValueError(f"expected {N_ACTIONS} action dims, got {a.shape[0]}")
        if not np.all(np.isfinite(a)):
            raise ValueError("action contains nan/inf - a policy blow-up")

        u_before = self._u.copy()
        self._u = np.clip(self._u + np.clip(a, -1.0, 1.0) * self.max_step,
                          0.0, 1.0)
        self._step += 1
        ev = self._evaluate(self._u)

        if not ev.ok:
            # **Revert, and report the last TRUE observation** (G114 lever 3).
            self._u = u_before
            self.n_reverted += 1
            assert self._last is not None
            return (self._obs(self._last), float(ev.reward), False,
                    self._step >= self.horizon,
                    {"is_analytic": False, "reverted": True,
                     "reason": ev.reason, "n_decks": int(ev.n_sims)})

        self._last = ev
        # **No early-success termination** (G100): an episode that ends on the
        # condition the metric rewards exceeding is two objectives, not one.
        return (self._obs(ev), float(ev.reward), False,
                self._step >= self.horizon,
                {"is_analytic": False, "reverted": False,
                 "feasible": bool(ev.feasible), "worst_spec": ev.worst_spec,
                 "n_decks": int(ev.n_sims)})

    @property
    def u(self) -> np.ndarray:
        return self._u.copy()

    def report(self) -> dict:
        return {"is_analytic": False, "n_evals": self.n_evals,
                "n_decks": self.n_decks, "n_reverted": self.n_reverted,
                "n_unscorable": self.n_unscorable,
                "n_feasible_steps": self.n_feasible_steps,
                "n_warm_starts": self.n_warm_starts,
                "n_starts_filtered": self.n_starts_filtered,
                "min_start_swing_v": self.min_start_swing_v,
                "specs": list(self.specs), "horizon": self.horizon,
                "points": [p.label for p in self.points],
                "note": ("scored through evaluate_at_points on the mandated "
                         "screen: the reward IS the acceptance criterion")}


__all__ = ["ScreenEnv", "HORIZON", "MAX_STEP"]
