"""
rl/env.py — the CTLE sizing environment. The contract is `rl/contract.py`.

NO GYM DEPENDENCY, DELIBERATELY. `gymnasium` is not installed in this
environment and `stable_baselines3` is not either (both checked, 2026-08-07).
The interface below is gym-SHAPED — `reset() -> obs`, `step(a) -> (obs, r,
terminated, truncated, info)` — so an SB3 wrapper is a thin adapter if one is
ever wanted, but nothing here imports a framework. CLAUDEwa.md §2 lists "Gym
utils" among the mandated tools; a 60-line adapter satisfies that and a
missing package must not block a smoke run.

WHAT THIS FILE IS RESPONSIBLE FOR, AND WHAT IT IS NOT
------------------------------------------------------
It owns the EPISODE: where a design starts, how an action edits it, when the
episode ends, and what the policy sees. It owns none of the physics — the
evaluation and its validation are `rl/evaluator.py`, the scoring is
`rl/reward_v1.py`, and the box and the observation layout are
`rl/contract.py`. That split exists so that "what did the agent see?" and
"what did the simulator say?" are answerable from different files.

THE TWO GATES §6a PUTS IN THE ENV
----------------------------------
Task 6a: *"fail loudly if `w` is ever written to a fixed-width resistor, and
fail loudly if `mult` is ever written with a value other than 1. Both were
found to be silently ignored."*

They are enforced at the DEVICE layer, on the assembled netlist text
(`device/netlist_gates.py`, called from `run_point` immediately before the
file is written), and this env asserts at construction that the wiring is
live — `_assert_netlist_gates_wired()` feeds the gate two netlists that must
be rejected and one that must pass. Gating the text rather than the call site
is strictly stronger than gating here: no path through the device layer can
emit an inert write, including one written by someone who has not read this
file. Asserting the wiring at construction is what stops the gate becoming
decoration if someone removes the call (CLAUDEwa.md §8 rule 10: every gate
gets a test that proves it can fail).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

import numpy as np

from nebula.common.types import SPEC_F_PEAK_HZ_RANGE, SPEC_PEAKING_DB_RANGE
from nebula.device.netlist_gates import InertParameterWrite, assert_no_inert_writes
from nebula.rl import reward_v1 as R
from nebula.rl.contract import (
    ACTION_NAMES,
    ACTION_SPACE,
    CL_CONTEXT_F,
    HORIZON,
    MAX_STEP,
    N_ACTIONS,
    N_OBS,
    Sizing,
    build_observation,
    sizing_from_u,
)
from nebula.rl.evaluator import EvalResult, SpiceBudget, Verdict, evaluate

# ─────────────────────────────────────────────────────────────────────────────
# The construction-time proof that the two §6a gates are live.
# ─────────────────────────────────────────────────────────────────────────────

_GATE_MUST_REJECT: tuple[str, ...] = (
    # G57: `w` on a fixed-width family is inert, and w=99 raises nothing.
    "Xrs s1 s2 0 sky130_fd_pr__res_high_po_0p69 w=99 l=5.0",
    # G56: `mult` is a mismatch parameter and does nothing.
    "Xrl vdd outp 0 sky130_fd_pr__res_high_po w=10 l=16.5 mult=4",
    "Xcs s1 s2 sky130_fd_pr__cap_mim_m3_1 w=30 l=30 mf=4",
)

_GATE_MUST_PASS: str = (
    "Xrs s1 s2 0 sky130_fd_pr__res_high_po w=2.85 l=4.445 m=2\n"
    "XM1 outp inp s1 0 sky130_fd_pr__nfet_01v8 W=40 L=0.15 nf=4 mult=1\n"
)


def _assert_netlist_gates_wired() -> None:
    """Prove both §6a gates can fail, and that neither is trigger-happy.

    Runs at env construction, every time. It costs microseconds and it is the
    difference between a gate and a comment: a gate nobody watches go red is
    indistinguishable from a gate that was deleted (CLAUDEwa.md §8 rule 10).
    """
    for bad in _GATE_MUST_REJECT:
        try:
            assert_no_inert_writes(bad)
        except InertParameterWrite:
            continue
        raise AssertionError(
            f"netlist gate did NOT reject a known silent write: {bad!r}. "
            f"G56/G57 say ngspice accepts it and exits 0, so nothing else "
            f"will catch it."
        )
    # And it must not fire on the legitimate forms, or every run fails and the
    # gate gets removed for being noisy.
    assert_no_inert_writes(_GATE_MUST_PASS)


# ─────────────────────────────────────────────────────────────────────────────
# Episode records — §6j's logged tuple.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class StepRecord:
    """One (action, sizing, geometry, raw result, validated result, reward).

    §6j: these are real SPICE evaluations and they are free training data for
    the task-8 surrogate, which needs a `design_id` per sizing point so the
    GROUPED train/test split works. It is emitted here rather than
    reconstructed later, because reconstructing it means choosing a float
    rounding tolerance nobody measured.
    """

    episode: int
    step: int
    design_id: Optional[str]
    geometry_tag: Optional[str]
    action: list
    u: list
    params: dict
    tail_j_um_per_a: float
    l_tail_um: float
    valid: bool
    #: "valid" | "headroom_only" | "invalid". `valid` alone cannot distinguish
    #: a broken measurement from a trustworthy measurement of a triode design,
    #: and those need opposite handling downstream.
    verdict: str
    invalid_reason: Optional[str]
    meas: Optional[dict]
    #: `.op` headroom. Present on VALID and HEADROOM_ONLY, None on INVALID.
    headroom: Optional[dict]
    raw: dict
    reward: float
    feasible: bool
    margins: dict
    shortfalls: dict
    worst_spec: Optional[str]
    n_spice: int
    seconds: float


# ─────────────────────────────────────────────────────────────────────────────
# The environment.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class EnvConfig:
    """Everything about the episode that is not the circuit.

    `seed` is threaded from here into `numpy.random.default_rng` and NOWHERE
    else. HANDOFF G3: never call `np.random.seed()`; the seed travels through
    a config object, exactly as `LinkConfig.seed` does on the SerDes side.
    """

    seed: int
    horizon: int = HORIZON
    max_step: float = MAX_STEP
    cl_f: float = CL_CONTEXT_F
    corner: str = "tt"
    temp_c: float = 27.0
    vdd_scale: float = 1.0
    #: `V0_SPECS` for §6f's first run, `V1_SPECS` for §6h's second.
    specs: tuple = R.V1_SPECS
    #: The one fixed spec target for this run (§6a). Mid-window in BOTH axes:
    #: 1.7678 GHz is the geometric centre of S3's 1.25-2.5 GHz octave, and
    #: 7.5 dB is the arithmetic centre of its 3-12 dB band. Chosen as the
    #: centre rather than as an interesting point, because a target near an
    #: edge would make the run a measurement of that edge.
    target_f_peak_hz: float = math.sqrt(SPEC_F_PEAK_HZ_RANGE[0]
                                        * SPEC_F_PEAK_HZ_RANGE[1])
    target_peaking_db: float = sum(SPEC_PEAKING_DB_RANGE) / 2.0
    lambda_cost: float = 0.0


class CtleSizingEnv:
    """One CTLE sizing episode. gym-shaped, framework-free.

    Observation: `float64[N_OBS]`, layout in `contract.OBS_BLOCKS`.
    Action:      `float64[N_ACTIONS]` in [-1, 1]; scaled by `max_step` and
                 applied as a DELTA to the normalised sizing, then clipped
                 back into the box.
    """

    observation_dim: int = N_OBS
    action_dim: int = N_ACTIONS

    def __init__(self, cfg: EnvConfig, budget: Optional[SpiceBudget] = None,
                 on_step: Optional[Callable[[StepRecord], None]] = None):
        _assert_netlist_gates_wired()
        self.cfg = cfg
        self.budget = budget if budget is not None else SpiceBudget()
        self.on_step = on_step
        self.rng = np.random.default_rng(cfg.seed)
        self._u: np.ndarray = np.full(N_ACTIONS, 0.5)
        self._step = 0
        self._episode = -1
        self._last: Optional[EvalResult] = None
        #: §6d: the invalid rate, over the whole run. If it RISES the agent is
        #: finding the holes, which is exactly what this smoke run is for.
        self.n_eval = 0
        self.n_invalid = 0
        #: §Call 1: `.op` good, device in triode. Tracked apart from
        #: `n_invalid` because the two mean different things about the box.
        self.n_headroom = 0
        self.invalid_reasons: dict = {}
        self.records: list = []

    # ---- helpers -----------------------------------------------------------

    def _classify(self, reason: str) -> str:
        """Bucket an invalidity so the rate can be read per MECHANISM.

        A single "invalid: 12 %" number says the agent found holes; it does not
        say which. The buckets are the failure classes of `evaluator.validate`.
        """
        r = reason.lower()
        for key, needle in (
            ("unrealisable_geometry", "unrealisable geometry"),
            # G44's fictitious peak. Its own bucket, separate from the f_peak
            # RANGE check, because the two describe different circuits: this
            # one has no maximum at all, the other has one in a place that
            # means the sweep was set up wrong.
            ("peak_is_sweep_edge", "peak is the sweep edge"),
            ("pair_triode", "input pair is in triode"),
            ("tail_triode", "tail is in triode"),
            ("outside_rails", "outside the rails"),
            ("f_peak_range", "f_pk ="),
            ("gain_range", "not an amplifier"),
            ("noise_range", "integration collapsed"),
            ("supply_range", "i_supply ="),
            ("ngspice", "ngspice:"),
        ):
            if needle in r:
                return key
        return "other"

    def _evaluate_current(self) -> tuple[EvalResult, R.RewardBreakdown, Sizing]:
        sizing = sizing_from_u(self._u, cl_f=self.cfg.cl_f)
        ev = evaluate(sizing, self.budget, corner=self.cfg.corner,
                      temp_c=self.cfg.temp_c, vdd_scale=self.cfg.vdd_scale)
        self.n_eval += 1
        if ev.verdict is Verdict.HEADROOM_ONLY:
            # Counted SEPARATELY from invalid. It is not a broken measurement —
            # `.op` converged — so folding it into the invalid rate would
            # overstate how much of the box the simulator cannot describe, and
            # would hide the one band that carries a gradient out of triode.
            self.n_headroom += 1
        elif not ev.valid:
            self.n_invalid += 1
            bucket = self._classify(ev.reason or "")
            self.invalid_reasons[bucket] = self.invalid_reasons.get(bucket, 0) + 1
        rb = R.reward(ev.meas, self.cfg.target_f_peak_hz, specs=self.cfg.specs,
                      lambda_cost=self.cfg.lambda_cost, sim_cost=ev.n_spice,
                      target_peaking_db=self.cfg.target_peaking_db,
                      headroom=(ev.headroom
                                if ev.verdict is Verdict.HEADROOM_ONLY else None))
        return ev, rb, sizing

    def _observation(self, ev: EvalResult) -> np.ndarray:
        """The observation. Only ever called with a VALID `ev`.

        An invalid evaluation TERMINATES the episode (§6d), so there is no
        code path that builds an observation from a missing measurement — and
        therefore no default, no zero-fill and no clamp. The terminal
        observation handed back after an invalidity is the LAST VALID one,
        which is a true statement about the circuit that was measured; PPO
        never bootstraps through it because the episode is terminated, not
        truncated.
        """
        assert ev.valid and ev.meas is not None
        return build_observation(self._u, ev.meas,
                                 self.cfg.target_peaking_db,
                                 self.cfg.target_f_peak_hz,
                                 self._step, self.cfg.horizon)

    def _record(self, ev, rb, sizing, action) -> StepRecord:
        rec = StepRecord(
            episode=self._episode, step=self._step,
            design_id=ev.design_id, geometry_tag=ev.geometry_tag,
            action=[float(a) for a in np.asarray(action).ravel()],
            u=[float(x) for x in self._u],
            params=dict(sizing.params),
            tail_j_um_per_a=sizing.tail_j_um_per_a,
            l_tail_um=sizing.l_tail_um,
            valid=ev.valid, verdict=ev.verdict.value, invalid_reason=ev.reason,
            meas=(dict(ev.meas) if ev.meas else None),
            headroom=(dict(ev.headroom) if ev.headroom else None),
            raw=dict(ev.raw),
            reward=rb.reward, feasible=rb.feasible,
            margins=dict(rb.margins), shortfalls=dict(rb.shortfalls),
            worst_spec=rb.worst_spec,
            n_spice=ev.n_spice, seconds=ev.seconds,
        )
        self.records.append(rec)
        if self.on_step is not None:
            self.on_step(rec)
        return rec

    # ---- the gym-shaped API -------------------------------------------------

    def reset(self, u0: Optional[Sequence[float]] = None
              ) -> tuple[np.ndarray, dict]:
        """Start an episode. Returns `(obs, info)`.

        **A reset can fail**, because a uniformly random start lands outside
        the feasible region often enough that pretending otherwise would be a
        lie. It retries up to `_RESET_TRIES` fresh starts, charging every SPICE
        call to the budget (§6i counts setup), and raises only if none of them
        produce a valid circuit — which would mean the box is broken, not the
        draw.
        """
        self._episode += 1
        for attempt in range(_RESET_TRIES):
            self._u = (np.asarray(u0, dtype=float).copy() if u0 is not None
                       else self.rng.uniform(0.0, 1.0, size=N_ACTIONS))
            self._step = 0
            ev, rb, sizing = self._evaluate_current()
            self._record(ev, rb, sizing, np.zeros(N_ACTIONS))
            if ev.valid:
                self._last = ev
                return self._observation(ev), {
                    "reset_attempts": attempt + 1,
                    "design_id": ev.design_id,
                    "reward": rb.reward,
                }
            if u0 is not None:
                raise ValueError(
                    f"the requested start point is not a valid circuit: "
                    f"{ev.reason}. A seeded start must be measured before it "
                    f"is used, not assumed."
                )
        raise RuntimeError(
            f"no valid start point in {_RESET_TRIES} draws. That is a broken "
            f"box or a broken evaluator, not bad luck — check the invalid "
            f"reason histogram: {self.invalid_reasons}"
        )

    def step(self, action: Sequence[float]
             ) -> tuple[np.ndarray, float, bool, bool, dict]:
        """Apply one edit. Returns `(obs, reward, terminated, truncated, info)`.

        `terminated` means the episode ENDED for a reason inside the MDP —
        success, or an invalid evaluation. `truncated` means the horizon ran
        out. PPO bootstraps through a truncation and not through a termination,
        so conflating them would credit a broken circuit with the value of
        whatever came next.
        """
        a = np.asarray(action, dtype=float).ravel()
        if a.shape[0] != N_ACTIONS:
            raise ValueError(f"expected {N_ACTIONS} action dims, got {a.shape[0]}")
        if not np.all(np.isfinite(a)):
            raise ValueError("action contains nan/inf — a policy blow-up, not a design")

        # Clip, THEN scale. The action is a delta in normalised space; the
        # result is clipped back into the box because the box edges are
        # physical (`w_in`'s ceiling is where SKY130's model bins stop) and a
        # coordinate outside it has no device behind it.
        delta = np.clip(a, -1.0, 1.0) * self.cfg.max_step
        self._u = np.clip(self._u + delta, 0.0, 1.0)
        self._step += 1

        ev, rb, sizing = self._evaluate_current()
        self._record(ev, rb, sizing, a)

        info = {
            "design_id": ev.design_id, "valid": ev.valid,
            "invalid_reason": ev.reason, "feasible": rb.feasible,
            "verdict": ev.verdict.value, "headroom_only": rb.headroom_only,
            "worst_spec": rb.worst_spec, "n_spice": ev.n_spice,
            "seconds": ev.seconds, "margins": rb.margins,
            "shortfalls": rb.shortfalls,
        }

        if not ev.valid:
            # §6d: a result that cannot become an observation is a negative
            # reward AND a terminated episode. Never a missing value, never a
            # substituted default, never a retry that quietly succeeds with
            # different numbers.
            #
            # HEADROOM_ONLY lands here too, and it should: there is no AC
            # measurement block to observe, because the whole point is that the
            # AC spec set was dropped. What differs is the REWARD — graded and
            # ordered by how far into triode the design is, rather than a flat
            # floor — which is where the gradient out of triode lives. The
            # episode still ends, because continuing to edit a design whose
            # observation cannot be built would mean feeding the policy a stale
            # measurement and calling it current.
            assert self._last is not None
            return self._observation(self._last), rb.reward, True, False, info

        self._last = ev
        obs = self._observation(ev)
        terminated = bool(rb.feasible)     # early success
        truncated = bool(self._step >= self.cfg.horizon) and not terminated
        return obs, rb.reward, terminated, truncated, info

    # ---- reporting ----------------------------------------------------------

    @property
    def invalid_rate(self) -> float:
        """Fraction of evaluations nothing could be believed from.

        HEADROOM_ONLY is NOT counted here — see `headroom_rate`. The headline
        "a quarter of evaluations return a number that looks valid and isn't"
        is about untrustworthy MEASUREMENTS, and a converged `.op` on a triode
        device is not one of those.
        """
        return self.n_invalid / self.n_eval if self.n_eval else 0.0

    @property
    def headroom_rate(self) -> float:
        return self.n_headroom / self.n_eval if self.n_eval else 0.0

    def invalid_report(self) -> str:
        lines = [f"invalid {self.n_invalid}/{self.n_eval} "
                 f"= {100 * self.invalid_rate:.2f}%   "
                 f"headroom-only {self.n_headroom}/{self.n_eval} "
                 f"= {100 * self.headroom_rate:.2f}%"]
        for k, v in sorted(self.invalid_reasons.items(), key=lambda kv: -kv[1]):
            lines.append(f"    {k:<24s} {v:5d}  ({100 * v / max(self.n_eval, 1):5.2f}%)")
        return "\n".join(lines)


#: How many fresh random starts a `reset` will try before declaring the box
#: broken. Not a tuned number: it is large enough that a 10 % valid rate almost
#: never exhausts it, and small enough that a genuinely broken evaluator fails
#: in seconds rather than looping.
_RESET_TRIES: int = 25


__all__: Sequence[str] = (
    "CtleSizingEnv", "EnvConfig", "StepRecord",
    "_assert_netlist_gates_wired",
)
