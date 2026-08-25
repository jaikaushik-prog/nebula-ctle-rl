"""
rl/episode_dynamics.py — **G114 fix 4 and G100, applied to the SPICE env as a
wrapper, with nothing under it modified.**

WHY THIS FILE EXISTS
--------------------
G114 recorded that fine-tuning a pre-trained policy on SPICE *erased* it, and
listed three uncontrolled changes as the cause. The third was:

    the episode dynamics change -- the analytic env REVERTS a bad edit, the
    SPICE env TERMINATES on one, so the state distribution differs.

and the fixes-to-try list ends with *"making the SPICE env revert rather than
terminate (the wrapper precedent exists)"*. This is that wrapper.

G100 is the second half. `CtleSizingEnv.step` sets `terminated = bool(rb.feasible)`
and `CornerCtleEnv.step` sets `terminated = bool(worst_feasible)` -- the episode
ends the instant the specs are met, while the metric rewards how far PAST the
band you get, so **the region the metric rewards is the region the policy is
never in**. `rl/analytic_env.py` already removed that ("**No early-success
termination** (G100)"). The SPICE path never had it removed. So a policy
pre-trained analytically and fine-tuned on SPICE meets two different MDPs, and
`analytic_env`'s docstring measures the cost: **1-3 of 8 moves** at evaluation.

**This module makes the two match, and it changes exactly one thing at a time**
so G114's own instruction ("Change them one at a time and measure") is
executable: `revert_on_invalid` and `keep_going_on_success` are separate flags.

THE TRAP THIS WRAPPER EXISTS TO AVOID, AND IT IS NOT THE OBVIOUS ONE
---------------------------------------------------------------------
`rl/env.py:427` returns, on an invalid evaluation,

    return self._observation(self._last), rb.reward, True, False, info

and `_observation` reads `self._u`. By that line `self._u` has **already been
moved to the bad point**, while `self._last` is the **previous** evaluation. So
the observation handed back mixes

    sizing block        the NEW, unbuildable design
    measurement block   the PREVIOUS design's measurement

**That is harmless in `env.py` and it must not be "fixed" there.** The episode
terminates, and no algorithm in this repo bootstraps through a termination
(`ppo.py` fills `buf_last_val` only on truncation), so the value is never read.
The docstring's claim that the terminal observation "is the LAST VALID one" is
true of the measurement block and not of the sizing block, and nothing depends
on the difference.

**It becomes a live defect the moment a wrapper un-terminates that step**, which
is precisely what this module does: the observation becomes a real successor
state and SAC's critic *will* bootstrap through it. A policy would be told it is
at a design it is not at. So this wrapper **rebuilds the observation** from the
reverted `u` and the last valid measurement, using
`contract.build_observation` -- the one definition (rule 9 / G32), not a second
one.

WHAT IS AND IS NOT CHANGED
--------------------------
Changed, and only in this wrapper's return values:

* `terminated` on an invalid evaluation -> `False`, the edit is undone, the move
  is still charged (same accounting as `analytic_env.step`);
* `terminated` on early feasibility -> `False` (G100);
* `truncated` recomputed from the base env's own step counter and horizon.

**Not** changed: the reward, the specs, the box, `MAX_STEP`, the observation
contract, the screen, the corner set, the SPICE cost of a step, or one line of
`env.py` / `corner_env.py` / `contract.py`.

THE COST, STATED UP FRONT
-------------------------
Removing early-success termination makes episodes LONGER, and on this env a step
is 4 SPICE decks. `analytic_env`'s docstring measures the status quo at 1-3 of 8
moves; a full horizon is 8. So expect up to ~4x the decks per episode. That is
the correct MDP per G100 and it is not free -- budget for it rather than being
surprised by it.

    from nebula.rl.episode_dynamics import RevertOnInvalidEnv
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

import numpy as np

from nebula.rl.contract import build_observation


def resolve_base(env: Any) -> Any:
    """Find the `CtleSizingEnv` under any stack of this repo's env wrappers.

    Walks `.env` (the `SpecConditionedCornerEnv` hop) and `.base` (the
    `CornerCtleEnv` hop) until it reaches an object carrying the three private
    attributes a revert needs: `_u`, `_step` and `_last`.

    **It raises rather than returning None, and that is the whole point.** A
    wrapper that silently fails to find the base would silently fail to revert,
    report success, and reproduce G114 while looking like the fix for it --
    which is this repo's failure mode 1 (silent success) in its purest form.
    """
    seen = []
    node = env
    for _ in range(8):
        seen.append(type(node).__name__)
        if all(hasattr(node, a) for a in ("_u", "_step", "_last", "cfg")):
            return node
        nxt = getattr(node, "base", None)
        if nxt is None:
            nxt = getattr(node, "env", None)
        if nxt is None or nxt is node:
            break
        node = nxt
    raise AttributeError(
        "cannot find the sizing env under this wrapper stack "
        f"(walked {' -> '.join(seen)}); a revert wrapper that cannot reach "
        "`_u`/`_step`/`_last` would silently not revert, which is worse than "
        "not wrapping at all -- see G114 and this module's docstring")


class RevertOnInvalidEnv:
    """**A wrapper.** Matches the SPICE env's episode dynamics to the analytic
    env's, one flag at a time.

    Duck-typed to the same 5-tuple `step` / 2-tuple `reset` API as everything
    else in `rl/`, and forwards every other attribute to the wrapped env, so it
    drops in wherever `SpecConditionedCornerEnv` goes.

    Parameters
    ----------
    env
        Any env in this repo's stack: `CtleSizingEnv`, `CornerCtleEnv`,
        `SpecConditionedCornerEnv`, or another wrapper around them.
    revert_on_invalid
        G114 fix 4. An unbuildable design undoes its own edit instead of ending
        the episode; the move is still charged against the horizon.
    keep_going_on_success
        G100. Feasibility no longer ends the episode, so the policy can spend
        its remaining moves buying margin -- which is what the metric scores.

    Both default to True because both are the documented fixes. Set either to
    False to measure the other in isolation, which is what G114 asks for.
    """

    def __init__(self, env: Any, *, revert_on_invalid: bool = True,
                 keep_going_on_success: bool = True):
        self.env = env
        self.revert_on_invalid = bool(revert_on_invalid)
        self.keep_going_on_success = bool(keep_going_on_success)
        self.base = resolve_base(env)
        self.observation_dim = env.observation_dim
        self.action_dim = env.action_dim
        #: Counters the caller REPORTS rather than infers. Named to line up
        #: with `AnalyticCtleEnv.report()` so the two runs are comparable.
        self.n_reverted = 0
        self.n_success_continued = 0
        self.n_steps = 0

    # -- the wrapped MDP ------------------------------------------------------

    def reset(self, u0: Optional[Sequence[float]] = None):
        return self.env.reset(u0)

    def step(self, action: Sequence[float]):
        u_before = np.asarray(self.base._u, dtype=float).copy()
        obs, rew, terminated, truncated, info = self.env.step(action)
        self.n_steps += 1
        info = dict(info)

        at_horizon = bool(self.base._step >= self.base.cfg.horizon)

        if self.revert_on_invalid and not info.get("valid", False):
            # Undo the edit. The design really is back where it was, so the
            # observation below is current, not stale.
            self.base._u = u_before
            self.n_reverted += 1
            info["reverted"] = True
            return (self._observation_at(u_before), rew, False, at_horizon,
                    info)

        info.setdefault("reverted", False)

        if self.keep_going_on_success and terminated:
            # G100: the only remaining reason the base terminates a VALID step
            # is early feasibility. Keep the episode alive.
            self.n_success_continued += 1
            info["success_continued"] = True
            return obs, rew, False, at_horizon, info

        return obs, rew, terminated, truncated, info

    # -- the rebuilt observation ---------------------------------------------

    def _observation_at(self, u: np.ndarray) -> np.ndarray:
        """The observation of the design we are ACTUALLY at, after a revert.

        Rebuilt rather than reused: see the module docstring. `env.py`'s
        terminal observation carries the *new* sizing beside the *old*
        measurement, which is fine for a state nobody bootstraps through and
        wrong for a successor state -- and un-terminating the step turns the
        first into the second.

        `self.base._last` is the last VALID `EvalResult`, so its `meas` is the
        measurement of exactly the design `u` describes. Asserted, not assumed:
        a missing `_last` means the very first evaluation of the episode was
        invalid, which `reset`'s retry loop is supposed to make impossible.
        """
        last = self.base._last
        if last is None or last.meas is None:
            raise AssertionError(
                "revert has no valid measurement to fall back to: the first "
                "evaluation of this episode was invalid, which `reset`'s retry "
                "loop should have prevented -- do not substitute a default")
        cfg = self.base.cfg
        return build_observation(u, last.meas,
                                 cfg.target_peaking_db, cfg.target_f_peak_hz,
                                 self.base._step, cfg.horizon)

    # -- reporting ------------------------------------------------------------

    def report(self) -> dict:
        return {
            "wrapper": "RevertOnInvalidEnv",
            "revert_on_invalid": self.revert_on_invalid,
            "keep_going_on_success": self.keep_going_on_success,
            "n_steps": self.n_steps,
            "n_reverted": self.n_reverted,
            "n_success_continued": self.n_success_continued,
            "revert_rate": (self.n_reverted / self.n_steps
                            if self.n_steps else 0.0),
            "note": ("episode dynamics matched to rl/analytic_env.py per G114 "
                     "fix 4 and G100; nothing under this wrapper is modified"),
        }

    def __getattr__(self, name: str):
        # Only reached for attributes this wrapper does not define, so it
        # cannot shadow `step`/`reset`/`base`/the counters above.
        return getattr(self.env, name)


__all__ = ["RevertOnInvalidEnv", "resolve_base"]
