"""
rl/adapt_env.py — **the adaptation episode: pick the CTLE code without being
told the corner.**

This is where decision D10 puts the reinforcement learning. The sizing problem
is a 2x2 analytic inversion -- `Rs*Cs` sets the zero, `RL*CL` sets the pole --
and the project measured what happens when a policy is pointed at it: SAC
proposes 1 of 16 against retrieval's 6 (entry 36), and PPO is statistically
indistinguishable from uniform random at every budget from 150 to 2 400
(`BASELINES.md`). A learner does not beat closed form at inverting a quadratic,
and it should not be asked to.

**Adaptation is a different problem, and it is the one silicon actually has.**
The part is taped out once. Which corner it landed on is unknown, and cannot be
measured in the field. What the receiver *can* see is its own eye. So: given a
target specification and a budget of trial codes, find a compliant code from eye
measurements alone.

WHAT IS OBSERVABLE, AND WHY THAT IS THE WHOLE POINT
-----------------------------------------------------
The policy sees **the request** (it is an input specification) and, for every
code it has tried, **the eye height and width that code produced**. It does
**not** see:

* the corner -- that is the hidden state, and the reason this is a POMDP;
* `peaking_db` or `f_peak` -- those need an AC sweep, which no receiver has;
* **any of the other eleven `V6_SPECS` rows**, and this is the load-bearing
  omission. HD3 at the operating point, noise, power, saturation and area all
  decide compliance and **none of them is visible from the eye.**

That asymmetry is why a learner has something to contribute here that it did not
have in sizing. A myopic loop that maximises the observed eye is exactly the
bisection control in `exp_adapt_controls`, and it will walk straight into codes
whose eye looks good and whose HD3 does not -- G103 makes peaking and drive
handling one knob, so the high-boost codes with the biggest eyes are precisely
the ones that fail linearity. A policy trained across corners can learn a prior
over *where compliance lives* that the eye alone does not reveal. **Whether it
actually does is the measurement, not the premise** -- and if the bisection
control wins, that is the honest result and it gets reported the way entry 36's
was.

THE ENVIRONMENT IS A TABLE, SO TRAINING COSTS NO SPICE
--------------------------------------------------------
`exp_bank_sweep` measured all 64 codes at all 45 mandated corners once -- 2 880
decks. Every episode here is a lookup into that artifact. Training a policy for
a million steps costs zero simulations, which matters because `RL_SMOKE.md`
measured **99.7 % of this project's wall clock inside the simulator**.

STATED IDEALISATIONS
---------------------
Recorded here rather than discovered later:

1. **The eye is read without noise.** A real receiver estimates eye margin from
   a finite number of samples and gets a noisy answer. `obs_noise_v` adds
   Gaussian noise to the observed eye so the dependence can be measured; it
   defaults to 0.0, which is optimistic in the policy's favour.
2. **The eye itself is modelled**, from a pole-zero fit through an analytic
   channel (`link/bridge.py`), not from a transient. `SCOPE_BOUNDARY.md` §1
   carries that boundary.
3. **One channel.** The 21-member channel family is free to add later --
   `evaluate_link` re-scores a cached device result in Python -- but the swept
   artifact holds one channel, so a policy trained here has seen one.
4. **Trying a code is free of link-training time.** Each trial costs 1 in the
   reward and nothing in the model; a real part pays a settling time per code.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from nebula.common.types import SPEC_F_PEAK_HZ_RANGE, SPEC_PEAKING_DB_RANGE

#: Action `N_CODES` is LOCK. Actions `0..N_CODES-1` try that code.
N_CODES: int = 64
LOCK: int = N_CODES
N_ACTIONS: int = N_CODES + 1

#: Per code: tried?, eye height, eye width. Plus request (2) and budget (1).
OBS_PER_CODE: int = 3
N_OBS: int = 3 + N_CODES * OBS_PER_CODE

#: Eye normalisation, in the spec's own units so the numbers stay readable.
#: S8 asks for > 100 mV and > 0.4 UI; a full-scale eye is well under 1 V / 1 UI.
EYE_H_SCALE_V: float = 0.5
EYE_W_SCALE_UI: float = 1.0


@dataclass(frozen=True)
class AdaptReward:
    """**Trials-to-lock with an asymmetric false-lock penalty** (owner, D10).

    `trial_cost` is the link-training budget: every code tried costs time a real
    part does not have. `lock_bonus` pays for a compliant lock. `false_lock`
    is deliberately several times larger, because the two errors are not
    symmetric in silicon -- failing to find a code costs margin, locking a
    non-compliant one ships a broken part.

    **These three numbers are a reward-weight choice and therefore the owner's**
    (CLAUDEwa.md §8 rule 6). They are recorded in every artifact rather than
    left in a default, and `exp_adapt_controls` reports the control scores under
    the identical weights so no comparison is confounded by them.
    """

    trial_cost: float = 1.0
    lock_bonus: float = 20.0
    false_lock: float = 60.0
    #: Locking before trying anything is meaningless; it is refused, not scored.
    invalid_lock: float = 1.0


@dataclass
class Episode:
    """What one adaptation attempt did. The artifact row for every arm."""

    corner: str
    target_peaking_db: float
    target_f_peak_hz: float
    codes_tried: list = field(default_factory=list)
    locked_code: Optional[int] = None
    locked_compliant: Optional[bool] = None
    n_trials: int = 0
    ret: float = 0.0
    #: True when a compliant code existed at all. An arm cannot be blamed for
    #: failing where the bank has no answer, and an aggregate that mixes the two
    #: is the "aggregate hiding a systematic case" shape this repo keeps hitting.
    solvable: bool = False


class BankTable:
    """The measured environment: (code, corner) -> what that point did.

    Built from `experiments/bank_sweep_run.jsonl`, which is the artifact
    `exp_bank_sweep` writes. **Nothing here simulates.**
    """

    def __init__(self, rows: Sequence[dict]):
        self.by: dict = {}
        self.corners: list = []
        for r in rows:
            key = (int(r["code"]), str(r["corner"]))
            self.by[key] = r
            if r["corner"] not in self.corners:
                self.corners.append(str(r["corner"]))
        self.codes = sorted({int(r["code"]) for r in rows})
        if not self.by:
            raise ValueError("empty bank table")

    @classmethod
    def from_jsonl(cls, path: Path) -> "BankTable":
        rows = [json.loads(l) for l in
                Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
        return cls(rows)

    def row(self, code: int, corner: str) -> dict:
        return self.by[(int(code), str(corner))]

    def observe(self, code: int, corner: str) -> tuple:
        """**What the receiver can see.** `(ok, eye_h_v, eye_w_ui)` and no more."""
        r = self.row(code, corner)
        if not r.get("ok"):
            return (False, 0.0, 0.0)
        return (True, float(r.get("eye_h_v") or 0.0),
                float(r.get("eye_w_ui") or 0.0))

    def compliant(self, code: int, corner: str, target_f_peak_hz: float,
                  target_peaking_db: float) -> bool:
        """Ground truth, for the reward only. **Never in an observation.**"""
        from nebula.experiments.exp_bank_sweep import SweepRow, is_compliant
        r = dict(self.row(code, corner))
        r.pop("code", None)
        row = SweepRow(code=int(code), **{k: v for k, v in r.items()
                                          if k in SweepRow.__dataclass_fields__
                                          and k != "code"})
        return bool(is_compliant(row, target_f_peak_hz, target_peaking_db))

    def solvable(self, corner: str, target_f_peak_hz: float,
                 target_peaking_db: float) -> list:
        """Every code that IS compliant here — the ceiling any arm can reach."""
        return [c for c in self.codes
                if self.compliant(c, corner, target_f_peak_hz,
                                  target_peaking_db)]


class AdaptEnv:
    """Gym-shaped, no gym dependency — the same choice `rl/env.py` made.

    `reset() -> obs`, `step(a) -> (obs, reward, terminated, truncated, info)`.
    """

    def __init__(self, table: BankTable, requests: Sequence[tuple],
                 reward: AdaptReward = AdaptReward(), max_trials: int = 8,
                 obs_noise_v: float = 0.0, seed: int = 0):
        self.t = table
        self.requests = [(float(pk), float(f)) for pk, f in requests]
        self.R = reward
        self.max_trials = int(max_trials)
        self.obs_noise_v = float(obs_noise_v)
        self.rng = np.random.default_rng(seed)
        self.ep: Optional[Episode] = None
        self._tried: dict = {}

    # -- episode ---------------------------------------------------------

    def reset(self, corner: Optional[str] = None,
              request: Optional[tuple] = None) -> np.ndarray:
        c = corner or str(self.rng.choice(self.t.corners))
        pk, f = (request if request is not None
                 else self.requests[int(self.rng.integers(len(self.requests)))])
        self.ep = Episode(corner=c, target_peaking_db=pk, target_f_peak_hz=f)
        self.ep.solvable = bool(self.t.solvable(c, f, pk))
        self._tried = {}
        return self._obs()

    def step(self, action: int):
        assert self.ep is not None, "reset() first"
        a = int(action)
        if a == LOCK:
            if not self.ep.codes_tried:
                # Refused, not scored: locking nothing is not a decision.
                return self._obs(), -self.R.invalid_lock, False, False, \
                    {"invalid_lock": True}
            return self._lock(self.ep.codes_tried[-1])
        ok, h, w = self.t.observe(a, self.ep.corner)
        if self.obs_noise_v > 0.0:
            h = max(0.0, h + float(self.rng.normal(0.0, self.obs_noise_v)))
        self._tried[a] = (ok, h, w)
        self.ep.codes_tried.append(a)
        self.ep.n_trials += 1
        r = -self.R.trial_cost
        self.ep.ret += r
        if self.ep.n_trials >= self.max_trials:
            # Budget exhausted: the last code tried is what the part ships with.
            obs, r2, term, trunc, info = self._lock(a)
            return obs, r + r2, term, True, info
        return self._obs(), r, False, False, {}

    def _lock(self, code: int):
        ep = self.ep
        good = self.t.compliant(code, ep.corner, ep.target_f_peak_hz,
                                ep.target_peaking_db)
        r = self.R.lock_bonus if good else -self.R.false_lock
        ep.locked_code, ep.locked_compliant = int(code), bool(good)
        ep.ret += r
        return self._obs(), r, True, False, {"locked": int(code),
                                             "compliant": bool(good)}

    # -- observation -----------------------------------------------------

    def _obs(self) -> np.ndarray:
        ep = self.ep
        pk_lo, pk_hi = SPEC_PEAKING_DB_RANGE
        f_lo, f_hi = SPEC_F_PEAK_HZ_RANGE
        o = np.zeros(N_OBS, dtype=np.float32)
        o[0] = (ep.target_peaking_db - pk_lo) / (pk_hi - pk_lo)
        o[1] = math.log2(ep.target_f_peak_hz / f_lo) / math.log2(f_hi / f_lo)
        o[2] = ep.n_trials / self.max_trials
        for code, (ok, h, w) in self._tried.items():
            i = 3 + code * OBS_PER_CODE
            o[i] = 1.0
            o[i + 1] = (h / EYE_H_SCALE_V) if ok else 0.0
            o[i + 2] = (w / EYE_W_SCALE_UI) if ok else 0.0
        return o


__all__ = ("N_CODES", "LOCK", "N_ACTIONS", "N_OBS", "AdaptReward", "Episode",
           "BankTable", "AdaptEnv")
