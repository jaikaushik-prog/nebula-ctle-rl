"""
experiments/spec_pool.py — **the 128 000 simulations we have already paid for,
turned into an amortised design method.**

THE OBSERVATION THIS FILE IS BUILT ON
--------------------------------------
**A measurement does not know what it was aiming at.** `evaluator.evaluate`
returns `peaking_db`, `f_peak_oct`, `inoise_vrms`, `power_w` and the rest for a
sizing; `reward_v1.reward` then scores that measurement AGAINST A TARGET. The
target enters only at the scoring step.

So every trial row this project has ever logged can be re-scored against **any**
target, for **zero** simulations. The run logs already on disk hold

    baselines_run_interp_grid.jsonl.gz   31 879 trials, 12 arms, P1 + P3
    budget_ladder_run.jsonl.gz           96 000 trials, 3 arms, P1

which is a labelled dataset for the INVERSE problem — *given a response, what
sizing produced it* — built from real SKY130 SPICE at a cost that has already
been sunk.

WHY THAT MATTERS FOR THE SPEC-CONDITIONED CLAIM
-------------------------------------------------
`CLAUDEwa.md` §7's second contribution is a policy that answers a NEW spec
without re-optimising. The comparison everyone reaches for is against CMA-ES
starting fresh, which a policy wins trivially because CMA-ES has no memory.

**That is the wrong opponent.** The honest opponent is the cheapest thing that
also has memory, and it is this: keep every design you ever simulated, and when
a new spec arrives, look up the one that best meets it. Zero simulations, no
model, no training. A panel of practising designers will think of it
immediately — several of them keep exactly such a database.

So `lookup_best` is the baseline the policy has to beat, and its one-off cost
(the 128 000 simulations that built the pool) is stated in the same units as a
policy's training cost, so the two amortise on the same axis.

WHAT IS AND IS NOT IN THE POOL
-------------------------------
* **P1 rows only.** `Trial.meas` carries the NOMINAL measurement, which on P1
  is tt/1.00/27C/cl_mid. On P3 the first evaluated point is a corner, so the
  same field means something else. Mixing them would put corner measurements
  and nominal ones in one table under one name (rule 9).
* **Valid rows only.** An invalid evaluation has no measurement to re-score.
* **De-duplicated by `design_id`**, because the same sizing appears in many
  runs and a pool that counts it twice reports a bigger library than it has.
* **The interpolated peak is used when present** (`peaking_db_interp`,
  `f_peak_oct_interp`, G74/session 22e), matching the objective every published
  ranking since session 22f is scored on.

NOTHING HERE SIMULATES.
"""

from __future__ import annotations

import gzip
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Optional, Sequence

import numpy as np

from nebula.rl import reward_v1 as R
from nebula.rl.contract import N_ACTIONS
from nebula.rl.spec_dist import SpecTarget

HERE = Path(__file__).resolve().parent

#: The logs the pool is built from. **Named, not globbed**: a glob would
#: silently change the pool whenever a new experiment writes a log, and every
#: number derived from the pool would move without anything being edited.
POOL_LOGS: tuple[Path, ...] = (
    HERE / "baselines_run_interp_grid.jsonl.gz",
    HERE / "budget_ladder_run.jsonl.gz",
)

#: The measurement channels `reward_v1` needs. Listed so a row missing one is
#: DROPPED loudly rather than defaulted (rule 1).
REQUIRED_MEAS: tuple[str, ...] = (
    "g_dc_db", "peaking_db", "f_peak_oct", "nyq_boost_db",
    "inoise_vrms", "power_w", "pair_margin_v", "tail_margin_v",
)


@dataclass(frozen=True)
class Pool:
    """Every distinct valid P1 design this project has simulated.

    `meas` rows are ready to hand to `reward_v1.reward` as-is.
    """

    u: np.ndarray                      # (N, N_ACTIONS) normalised sizing
    meas: tuple[dict, ...]             # (N,) measurement dicts
    design_id: tuple[str, ...]
    source: tuple[str, ...]            # which log each row came from
    n_rows_read: int
    n_dropped: dict

    #: Which SEARCH METHOD proposed each design. Kept because a pool built by
    #: CMA-ES or PPO was steered toward the legacy target and is therefore a
    #: biased sample of the box, while `uniform` rows are not. Any claim of the
    #: form "N simulations buy a library that answers any spec" has to be made
    #: on the unbiased sub-pool or it is a claim about the optimiser.
    method: tuple[str, ...] = ()

    def __len__(self) -> int:
        return len(self.meas)

    @property
    def peaking_db(self) -> np.ndarray:
        return np.array([m["peaking_db"] for m in self.meas], dtype=float)

    @property
    def f_peak_oct(self) -> np.ndarray:
        return np.array([m["f_peak_oct"] for m in self.meas], dtype=float)

    def subset(self, idx: Sequence[int]) -> "Pool":
        """A sub-pool, for asking how big a library has to be."""
        idx = [int(i) for i in idx]
        return Pool(u=self.u[idx], meas=tuple(self.meas[i] for i in idx),
                    design_id=tuple(self.design_id[i] for i in idx),
                    source=tuple(self.source[i] for i in idx),
                    n_rows_read=len(idx), n_dropped={"subset_of": len(self)},
                    method=tuple(self.method[i] for i in idx))

    def where_method(self, name: str) -> list[int]:
        return [i for i, m in enumerate(self.method) if m == name]

    def summary(self) -> dict:
        import collections
        return {"n_designs": len(self), "n_rows_read": self.n_rows_read,
                "by_method": dict(collections.Counter(self.method)),
                "dropped": dict(self.n_dropped),
                "sources": sorted(set(self.source)),
                "peaking_db_range": [float(self.peaking_db.min()),
                                     float(self.peaking_db.max())],
                "f_peak_oct_range": [float(self.f_peak_oct.min()),
                                     float(self.f_peak_oct.max())],
                "simulations_sunk": self.n_rows_read,
                "note": ("the pool's one-off cost is `simulations_sunk`, and it "
                         "is quoted in the same units as a policy's training "
                         "cost so the two amortise on one axis")}


def _open(path: Path):
    return (gzip.open(path, "rt", encoding="utf-8") if path.suffix == ".gz"
            else open(path, "r", encoding="utf-8"))


def load_pool(paths: Sequence[Path] = POOL_LOGS,
              ac_peak_interp: bool = True) -> Pool:
    """Build the pool. **Every rejection is counted and named.**

    `ac_peak_interp` selects the sub-grid peak where the row carries it, which
    is the objective every ranking since session 22f is scored on. Rows written
    before the interpolation existed fall back to the lattice value, and the
    fallback is COUNTED — a fallback nobody counts is indistinguishable from
    one that never fires (G73).
    """
    u_rows: list[list[float]] = []
    meas_rows: list[dict] = []
    ids: list[str] = []
    src: list[str] = []
    meth: list[str] = []
    seen: set[str] = set()
    n_read = 0
    dropped = {"not_a_trial": 0, "not_P1": 0, "not_valid": 0, "no_meas": 0,
               "missing_channel": 0, "non_finite": 0, "duplicate_design": 0,
               "no_design_id": 0}
    n_interp_used = 0
    n_interp_fallback = 0

    for path in paths:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(
                f"{path} is missing. The pool is named rather than globbed on "
                f"purpose; a missing log must fail, not shrink the pool.")
        with _open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{path}: corrupt row: {exc}") from exc
                if row.get("event") != "trial":
                    dropped["not_a_trial"] += 1
                    continue
                n_read += 1
                if row.get("problem") != "P1":
                    dropped["not_P1"] += 1
                    continue
                if row.get("verdict") != "valid":
                    dropped["not_valid"] += 1
                    continue
                m = row.get("meas")
                if not m:
                    dropped["no_meas"] += 1
                    continue
                did = row.get("design_id")
                if not did:
                    dropped["no_design_id"] += 1
                    continue
                if did in seen:
                    dropped["duplicate_design"] += 1
                    continue
                out = {}
                bad = False
                for k in REQUIRED_MEAS:
                    if k not in m:
                        dropped["missing_channel"] += 1
                        bad = True
                        break
                    v = float(m[k])
                    if not math.isfinite(v):
                        dropped["non_finite"] += 1
                        bad = True
                        break
                    out[k] = v
                if bad:
                    continue
                if ac_peak_interp:
                    got = False
                    for src_k, dst_k in (("peaking_db_interp", "peaking_db"),
                                         ("f_peak_oct_interp", "f_peak_oct")):
                        v = m.get(src_k)
                        if v is not None and math.isfinite(float(v)):
                            out[dst_k] = float(v)
                            got = True
                    n_interp_used += int(got)
                    n_interp_fallback += int(not got)
                seen.add(did)
                u_rows.append([float(x) for x in row["u"]])
                meas_rows.append(out)
                ids.append(str(did))
                src.append(path.name)
                meth.append(str(row.get("method", "?")))

    if not meas_rows:
        raise ValueError("the pool is empty; nothing can be looked up in it")
    u = np.asarray(u_rows, dtype=float)
    if u.shape[1] != N_ACTIONS:
        raise ValueError(f"pool sizing width {u.shape[1]} != {N_ACTIONS}")
    dropped["interp_used"] = n_interp_used
    dropped["interp_fallback_to_lattice"] = n_interp_fallback
    return Pool(u=u, meas=tuple(meas_rows), design_id=tuple(ids),
                source=tuple(src), n_rows_read=n_read, n_dropped=dropped,
                method=tuple(meth))


def score_pool(pool: Pool, target: SpecTarget,
               specs: Sequence[str] = R.V1_SPECS) -> np.ndarray:
    """Every pool design's reward **against this target**. Zero simulations.

    This is the whole trick: `reward` takes the measurement and the target
    separately, so a design simulated months ago under a different target is
    re-scored exactly, not approximately.
    """
    out = np.empty(len(pool), dtype=float)
    for i, m in enumerate(pool.meas):
        out[i] = R.reward(m, target.f_peak_hz, specs=specs,
                          target_peaking_db=target.peaking_db).reward
    return out


@dataclass(frozen=True)
class LookupResult:
    """What the zero-simulation library answers for one target."""

    target: SpecTarget
    index: int
    design_id: str
    u: np.ndarray
    reward: float
    feasible: bool
    n_feasible_in_pool: int
    sims_spent: int              # ALWAYS 0 — the design is already measured


def lookup_best(pool: Pool, target: SpecTarget,
                specs: Sequence[str] = R.V1_SPECS) -> LookupResult:
    """**The baseline the spec-conditioned policy has to beat.**

    Keep every design you ever simulated; when a new spec arrives, return the
    one that scores best against it. No model, no training, no simulation --
    and it has memory, which is the only property that made the policy
    interesting in the first place.

    `sims_spent` is 0 and that is not a trick: the returned design's response
    was measured when it entered the pool, so there is nothing left to verify.
    What the method costs is the pool, and `Pool.summary()['simulations_sunk']`
    states it in the same units as a training budget.
    """
    r = score_pool(pool, target, specs=specs)
    i = int(np.argmax(r))
    bonus = R.feasible_bonus(len(specs))
    return LookupResult(
        target=target, index=i, design_id=pool.design_id[i],
        u=pool.u[i].copy(), reward=float(r[i]),
        feasible=bool(r[i] >= bonus),
        n_feasible_in_pool=int(np.sum(r >= bonus)), sims_spent=0)


def nearest_in_spec_space(pool: Pool, target: SpecTarget) -> int:
    """1-NN on (peaking dB, f_peak octaves) — the *naive* library lookup.

    Kept beside `lookup_best` because the two answer different questions and a
    panel will ask about this one. This one does not consult the reward at all,
    so it can return a design that is closest in S3 and fails S5 or S6; the
    difference between the two is a measurement of how much the OTHER specs
    bind. Distances are in each axis's own spec units -- dB against S3's 9 dB
    band, octaves against its 1-octave window -- so neither axis dominates by
    accident of scale.
    """
    d_db = (pool.peaking_db - target.peaking_db) / 9.0
    d_oc = (pool.f_peak_oct - target.f_peak_oct) / 1.0
    return int(np.argmin(d_db * d_db + d_oc * d_oc))


def coverage(pool: Pool, targets: Sequence[SpecTarget],
             specs: Sequence[str] = R.V1_SPECS) -> dict:
    """How much of S3 the pool can already serve, per target.

    **The number that decides whether the amortised comparison is interesting
    at all.** If the library answers every held-out spec with a feasible design
    for free, a policy has to justify itself against zero.
    """
    bonus = R.feasible_bonus(len(specs))
    rows = []
    for t in targets:
        res = lookup_best(pool, t, specs=specs)
        rows.append({"peaking_db": t.peaking_db, "f_peak_hz": t.f_peak_hz,
                     "f_peak_oct": t.f_peak_oct, "best_reward": res.reward,
                     "feasible": res.feasible,
                     "n_feasible_in_pool": res.n_feasible_in_pool,
                     "design_id": res.design_id})
    feas = [r for r in rows if r["feasible"]]
    return {"n_targets": len(rows), "n_served": len(feas),
            "fraction_served": len(feas) / len(rows) if rows else 0.0,
            "median_best_reward": float(np.median([r["best_reward"]
                                                   for r in rows])),
            "feasible_bonus": float(bonus), "per_target": rows}


__all__ = ["Pool", "POOL_LOGS", "load_pool", "score_pool", "LookupResult",
           "lookup_best", "nearest_in_spec_space", "coverage"]
