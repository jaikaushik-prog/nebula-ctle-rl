"""
rl/corner_env.py — **reward on the worst corner, not on nominal.**

WHAT THIS IS
------------
`CLAUDEwa.md` §7 claims a three-tier corner-aware fidelity hierarchy as the
project's FIRST contribution over the paper it is modelled on, and its load-
bearing sentence is four words: **"Reward on worst-case corner, not nominal."**
§12 states the trap it exists to avoid: *"Optimising at nominal and checking
corners afterwards. Score on worst corner from the start."*

Until now no RL run could do that. `CtleSizingEnv` takes ONE corner and ONE
load, which is why `baselines.method_ppo` refuses a multi-point problem
outright and why P3 has no PPO arm. This module is the missing piece.

WHY IT WRAPS RATHER THAN REPLACES
-----------------------------------
`rl/env.py` is on the do-not-modify list (`CONTINUE_HERE.md` §9 rule 7), and
re-implementing an episode would put **two definitions of one thing** in the
repo — rule 9, and the defect that produced G32. So this composes:

* the base `CtleSizingEnv` owns the episode entirely — action scaling and
  clipping, the box, termination on an invalid evaluation, the observation, the
  step records, the invalid-rate accounting;
* this class adds ONE thing: after the base has moved the design, the same
  sizing is evaluated at the OTHER (corner, load) points and the reward becomes
  the **minimum** over all of them.

The only private thing it reads is the base's current normalised sizing, which
is the one fact it cannot get any other way.

THE SHORT-CIRCUIT IS EXACT, NOT AN APPROXIMATION
--------------------------------------------------
`reward_v1.invalid_reward` is the global minimum of the reward's four bands, so
once any point returns the floor no other point can lower the minimum and the
remaining simulations would buy nothing. `baselines.Objective.evaluate` makes
the same argument and this module reuses it deliberately: a corner-aware method
that pays for simulations a nominal one skips would be measuring the
short-circuit rather than the corner treatment.

THE OBSERVATION IS NOMINAL, AND THAT IS THE CONTRACT RATHER THAN AN OVERSIGHT
------------------------------------------------------------------------------
§7 says *reward* on the worst corner. It does not say the policy sees the worst
corner, and `contract.build_observation` has one measurement block, so showing
the worst point's response instead would be a change to the frozen observation
contract rather than a flag.

**This is a live design question and it is recorded rather than decided.** A
policy rewarded on a corner it cannot observe has to infer which corner binds
from the nominal response alone. Whether that is learnable is unmeasured, and
`which_corner_binds()` exists to give the first evidence either way: if one
corner binds almost always, the nominal observation is nearly sufficient; if it
moves around the box, it is probably not.

EVERY SIMULATION IS COUNTED
----------------------------
The extra points charge the SAME `SpiceBudget` the base env holds, so a
corner-aware run pays honestly for what it costs — `BASELINES.md` 7f rule 1,
and the reason the P3 rung reports 3.3-3.8 simulations per design rather than
one.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable, Optional, Sequence

import numpy as np

from nebula.rl import reward_v1 as R
from nebula.rl.contract import N_ACTIONS, sizing_from_u
from nebula.rl.env import CtleSizingEnv, EnvConfig
from nebula.rl.evaluator import (
    SpiceBudget,
    Verdict,
    evaluate,
    interp_was_refused,
    scoring_meas,
)


@dataclass(frozen=True)
class PointScore:
    """What one (corner, load) point said about the current design."""

    label: str
    reward: float
    feasible: bool
    valid: bool
    verdict: str
    worst_spec: Optional[str]
    n_spice: int


class CornerCtleEnv:
    """`CtleSizingEnv` scored on its WORST (corner, load) point.

    `points` is any sequence of records carrying `label`, `corner`,
    `vdd_scale`, `temp_c` and `cl_f` — `baselines.EvalPoint` is the intended
    type, and `baselines.PROBLEMS[...].points` is where the rungs are DEFINED.
    They are passed in rather than imported so that this module does not depend
    on `experiments/`, and so that the ladder has exactly one definition.

    **`points[0]` is the point the base env runs**, and it must match `cfg`'s
    corner and load or the base would be evaluating something the caller did
    not ask for. That is checked, not assumed.
    """

    def __init__(self, cfg: EnvConfig, points: Sequence[Any],
                 budget: Optional[SpiceBudget] = None,
                 on_step: Optional[Callable] = None):
        pts = tuple(points)
        if not pts:
            raise ValueError("a corner-aware env needs at least one point")
        head = pts[0]
        mismatch = [
            f"corner {cfg.corner!r} != {head.corner!r}"
            if cfg.corner != head.corner else "",
            f"temp_c {cfg.temp_c} != {head.temp_c}"
            if not math.isclose(cfg.temp_c, head.temp_c) else "",
            f"vdd_scale {cfg.vdd_scale} != {head.vdd_scale}"
            if not math.isclose(cfg.vdd_scale, head.vdd_scale) else "",
            f"cl_f {cfg.cl_f} != {head.cl_f}"
            if not math.isclose(cfg.cl_f, head.cl_f, rel_tol=1e-9) else "",
        ]
        mismatch = [m for m in mismatch if m]
        if mismatch:
            raise ValueError(
                "points[0] must be the point `cfg` describes, or the base env "
                "evaluates something the caller did not ask for: "
                + "; ".join(mismatch))

        self.cfg = cfg
        self.points = pts
        self.base = CtleSizingEnv(cfg, budget=budget, on_step=on_step)
        #: One budget for the whole design, so the extra points are charged.
        self.budget = self.base.budget
        self.observation_dim = self.base.observation_dim
        self.action_dim = self.base.action_dim

        #: Per-step diagnostics. `binding` is the report table: which corner is
        #: the worst one, and how often.
        self.binding: Counter = Counter()
        self.n_designs = 0
        self.n_short_circuited = 0
        self.n_extra_sims = 0
        self.last_points: tuple[PointScore, ...] = ()

    @classmethod
    def from_points(cls, points: Sequence[Any], seed: int,
                    budget: Optional[SpiceBudget] = None,
                    on_step: Optional[Callable] = None,
                    **cfg_kw: Any) -> "CornerCtleEnv":
        """Build the `EnvConfig` FROM `points[0]` instead of asking for both.

        The constructor requires `cfg` and `points[0]` to describe the same
        point, and getting that wrong is easy: `EnvConfig` defaults to
        tt/27 C/1.00 while `baselines.PROBLEMS["P3"].points[0]` is
        **ss/0.95/125 C**. Every caller that would have had to remember is a
        caller that could have forgotten, so this derives it.
        """
        head = tuple(points)[0]
        cfg = EnvConfig(seed=seed, corner=head.corner, temp_c=head.temp_c,
                        vdd_scale=head.vdd_scale, cl_f=head.cl_f, **cfg_kw)
        return cls(cfg, points, budget=budget, on_step=on_step)

    # ---- the one added behaviour -------------------------------------------

    @property
    def _u(self) -> np.ndarray:
        """The base env's current normalised sizing. The one private read."""
        return self.base._u

    def _score_extra_points(self, nominal: PointScore
                            ) -> tuple[float, bool, tuple[PointScore, ...]]:
        """Evaluate `points[1:]` at the current sizing; return the worst.

        Short-circuits on the invalid floor, exactly as
        `baselines.Objective.evaluate` does and for the same reason: the floor
        is the global minimum of the reward's bands, so nothing below it exists
        and the remaining simulations would buy nothing.
        """
        floor = R.invalid_reward(len(self.cfg.specs))
        scored = [nominal]
        worst, worst_label = nominal.reward, nominal.label
        worst_feasible = nominal.feasible

        if nominal.reward <= floor:
            self.n_short_circuited += 1
        else:
            for pt in self.points[1:]:
                sizing = sizing_from_u(self._u, cl_f=pt.cl_f)
                ev = evaluate(sizing, self.budget, corner=pt.corner,
                              temp_c=pt.temp_c, vdd_scale=pt.vdd_scale,
                              ac_peak_interp=self.cfg.ac_peak_interp)
                self.n_extra_sims += ev.n_spice
                if interp_was_refused(ev):
                    self.base.n_interp_refused += 1
                rb = R.reward(
                    scoring_meas(ev, self.cfg.ac_peak_interp),
                    self.cfg.target_f_peak_hz, specs=self.cfg.specs,
                    target_peaking_db=self.cfg.target_peaking_db,
                    headroom=(ev.headroom
                              if ev.verdict is Verdict.HEADROOM_ONLY else None))
                ps = PointScore(label=pt.label, reward=float(rb.reward),
                                feasible=bool(rb.feasible), valid=bool(ev.valid),
                                verdict=ev.verdict.value,
                                worst_spec=rb.worst_spec, n_spice=int(ev.n_spice))
                scored.append(ps)
                if ps.reward < worst:
                    worst, worst_label = ps.reward, ps.label
                worst_feasible = worst_feasible and ps.feasible
                if ps.reward <= floor:
                    self.n_short_circuited += 1
                    break

        self.n_designs += 1
        self.binding[worst_label] += 1
        self.last_points = tuple(scored)
        return worst, worst_feasible, tuple(scored)

    @staticmethod
    def _nominal_from_info(label: str, reward: float, info: dict) -> PointScore:
        return PointScore(label=label, reward=float(reward),
                          feasible=bool(info.get("feasible", False)),
                          valid=bool(info.get("valid", False)),
                          verdict=str(info.get("verdict", "?")),
                          worst_spec=info.get("worst_spec"),
                          n_spice=int(info.get("n_spice", 0)))

    # ---- the gym-shaped surface --------------------------------------------

    def reset(self, u0: Optional[Sequence[float]] = None
              ) -> tuple[np.ndarray, dict]:
        """Start an episode. **The base's retry policy is deliberately kept.**

        `CtleSizingEnv.reset` retries until the NOMINAL point is a valid
        circuit. A corner-aware reset could instead demand validity everywhere
        — and would then reject start points that are merely hard, which is the
        population the policy most needs to learn from. So the start is chosen
        on nominal and SCORED on the worst point, which is the same asymmetry
        the rest of this class implements.
        """
        obs, info = self.base.reset(u0)
        nominal = self._nominal_from_info(
            self.points[0].label, float(info.get("reward", 0.0)),
            {**info, "valid": True, "verdict": "valid",
             "feasible": info.get("feasible", False)})
        worst, worst_feasible, scored = self._score_extra_points(nominal)
        info = dict(info)
        info.update(reward=worst, nominal_reward=nominal.reward,
                    worst_point=min(scored, key=lambda p: p.reward).label,
                    feasible=worst_feasible,
                    points=[p.__dict__ for p in scored])
        return obs, info

    def step(self, action: Sequence[float]
             ) -> tuple[np.ndarray, float, bool, bool, dict]:
        """One edit, scored on the worst point.

        Termination follows the WORST point, not the nominal one: an episode
        that ends the moment the nominal corner is feasible would be the exact
        trap §12 names.
        """
        obs, r_nom, terminated, truncated, info = self.base.step(action)
        nominal = self._nominal_from_info(self.points[0].label, r_nom, info)

        if not info.get("valid", False):
            # The base already terminated on an unusable measurement, and the
            # floor is the global minimum, so no other point can lower it.
            self.n_designs += 1
            self.binding[nominal.label] += 1
            self.last_points = (nominal,)
            info = dict(info)
            info.update(nominal_reward=r_nom, worst_point=nominal.label,
                        points=[nominal.__dict__])
            return obs, r_nom, True, False, info

        worst, worst_feasible, scored = self._score_extra_points(nominal)
        info = dict(info)
        info.update(nominal_reward=r_nom, feasible=worst_feasible,
                    worst_point=min(scored, key=lambda p: p.reward).label,
                    points=[p.__dict__ for p in scored],
                    n_spice=sum(p.n_spice for p in scored))
        terminated = bool(worst_feasible)
        truncated = bool(self.base._step >= self.cfg.horizon) and not terminated
        return obs, worst, terminated, truncated, info

    # ---- reporting ----------------------------------------------------------

    def which_corner_binds(self) -> dict:
        """**The table G4's results section is built from.**

        How often each point was the worst one. Two readings matter and they
        point opposite ways: if a single corner binds nearly always, the
        nominal observation is close to sufficient and a cheap two-point screen
        would capture most of the cost; if the binding point moves around the
        box, worst-case scoring is doing real work that no fixed corner
        substitutes for.
        """
        total = sum(self.binding.values())
        return {
            "n_designs": self.n_designs,
            "n_extra_simulations": self.n_extra_sims,
            "n_short_circuited": self.n_short_circuited,
            "points": [p.label for p in self.points],
            "binding_counts": dict(self.binding),
            "binding_fraction": {k: v / total for k, v in self.binding.items()}
            if total else {},
            "most_binding": (self.binding.most_common(1)[0][0]
                             if self.binding else None),
        }

    @property
    def sims_per_design(self) -> float:
        """Measured, not assumed — the short-circuit makes it less than
        `len(points)` and the difference is the point of reporting it."""
        n = self.base.n_eval + 0  # base counts its own evaluations
        return ((n + self.n_extra_sims) / self.n_designs
                if self.n_designs else float("nan"))


__all__ = ["CornerCtleEnv", "PointScore"]
