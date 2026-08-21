"""search_score.py — an UNCLIPPED ranking scalar for the search. Verdict untouched.

**The defect this fixes, in one sentence.** `reward_v1.reward` scores an
infeasible design as `-sum(min(shortfall_i, 1.0))` (line ~808), so **once a spec
row misses by more than one tolerance its penalty stops growing** — and a search
ranking candidates on that number is optimising on a plateau.

Measured, 2026-08-22, zero SPICE, on the live `reward_v1.shortfalls` with the
real `TOL["S3_f_peak_match"] = 0.30` octaves and a 1.387 GHz request:

    delivered 1.378 GHz   0.009 oct off   shortfall 0.031   clipped 0.031
    delivered 2.500 GHz   0.850 oct off   shortfall 2.833   clipped 1.000
    delivered 10.303 GHz  2.893 oct off   shortfall 9.644   clipped 1.000
    delivered 11.800 GHz  3.087 oct off   shortfall 10.291  clipped 1.000
                                                            ^^^^^^^^^^^^^
                            a 10 GHz peak and a legal 2.5 GHz peak are TIED

**The gradient pulling a runaway peak back into the band is exactly 0.0.**
Corroborated by the artifact rather than by argument: all four out-of-window
requests in `coverage_results_AFTER_seeding_fix.json` recorded `screen_reward` of
**exactly -2.0000** — an integer, because it is simply *how many rows are fully
saturated* (`S3_f_peak_band` and `S3_f_peak_match`), carrying no information
about how far out. Delivered frequency errors of 1.901, 2.386, 2.715 and 2.893
octaves all produced the same score.

**The clip is right for SCORING and wrong for SEARCHING, and both statements
come from the same comment.** `reward_v1` clips so that one catastrophic row
cannot drown out the other twelve — that is a real requirement and this module
keeps it. What it does not have to do is destroy the ordering between two
infeasible designs, and that is what a search needs.

**Why this is a separate module and not an edit.** `rl/reward_v1.py`, `V1_SPECS`
and the tolerances may not be modified without a human decision (`PROGRESS.md`
§8 rule 7, `CLAUDEwa.md` §8). Every published reward, the `+8.950669` ceiling and
the whole `BASELINES.md` ranking are defined by that file. So the verdict —
FEASIBLE / infeasible / headroom / invalid, and the number reported as
`screen_reward` — is still `reward_v1`'s, unchanged and un-rescaled. This module
produces a **second, private scalar used only to rank candidates during a
search**, and nothing it computes is ever reported as a compliance result.

---

## The transform

Per spec row, given `v = shortfall = max(0, -margin/tol)`:

    penalty(v) = min(v, 1.0) + W * log1p(max(0, v - 1.0))        capped at ROW_CAP

then, summed over the `N` rows of the spec set:

    search_spec_reward = -sum(penalty_i) / ROW_CAP               in [-N, 0]

Three properties, each of which is a test in `tests/test_search_score.py`:

1. **Order-identical to the clipped reward wherever the clip never bites.**
   For `v <= 1` the first term *is* `min(v, 1.0)` and the tail is exactly zero,
   so the sum is the clipped sum and the division by `ROW_CAP` is a single
   positive constant applied to every candidate. **The region every one of the
   eight currently-solved requests lives in is re-ranked identically.** This is
   the safety property: the fix cannot disturb what already works.

2. **Strictly monotone past the clip.** `log1p` is strictly increasing, so
   10.303 GHz now ranks strictly worse than 2.500 GHz. That is the gradient the
   plateau removed, and recovering it is the entire point.

3. **Band-safe, which is not cosmetic.** `reward_v1`'s bands are
   `infeasible [-N, 0)`, `headroom (-(N+2), -(N+1)]`, `invalid -(N+3)`. An
   *uncapped, undivided* sum would send a badly infeasible design to -50 and the
   search would then prefer an **INVALID** design at -16 over a measurable one —
   G107 (*"cannot be scored is not fails"*) committed deliberately. Dividing by
   `ROW_CAP` keeps the infeasible band exactly where `reward_v1` put it, so the
   ordering *between* bands is preserved by construction rather than by luck.
   **`ROW_CAP` is a band-safety requirement, not a tuning knob.**

`W = 1.0` and `ROW_CAP = 4.0` are deliberately not tuned. `ROW_CAP` saturates at
`v = e**3 + 1 = 21.1` tolerances — a **6.3-octave** frequency miss, far outside
anything this box can produce (the widest ever observed is 3.09 octaves), so the
cap is inert on real data and exists only to bound the band. `W = 1.0` is the
natural logarithm with no coefficient chosen to make a number look better.

---

## What this module deliberately does NOT do

* It does not touch the FEASIBLE band. A feasible design keeps
  `feasible_bonus(N) + min(margin/tol)` exactly, so "seek margin once compliant"
  is unchanged and every feasible design still outranks every infeasible one.
* It does not touch the headroom or invalid bands — they pass through
  bit-identically, so an unbuildable design remains the floor.
* It does not loosen a tolerance. `TOL` is read, never written. Loosening
  tolerances to improve coverage is the G111 defect committed on purpose
  (`NEXT_AGENT_SAC.md` §7) and this module is the alternative to it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

from nebula.rl import reward_v1 as R

#: Weight on the log tail. **1.0 = the natural log with no coefficient.** Not
#: fitted to anything; chosen so the tail term needs no justification beyond
#: "it is a logarithm".
SEARCH_TAIL_W: float = 1.0

#: Per-row ceiling, and therefore the divisor that keeps the infeasible band at
#: `[-N, 0]`. **A band-safety constant, not a tuning knob** — see property 3
#: above. Saturates at `v = exp((ROW_CAP - 1) / W) + 1 = 21.1` tolerances, i.e.
#: a 6.3-octave frequency miss, so it is inert on every design this box can
#: produce and exists only to bound the arithmetic.
SEARCH_ROW_CAP: float = 4.0


def row_penalty(shortfall: float, w: float = SEARCH_TAIL_W,
                row_cap: float = SEARCH_ROW_CAP) -> float:
    """`min(v,1) + w*log1p(v-1)`, capped. **Equals `min(v,1)` for `v <= 1`.**

    That equality is the point and it is exact, not approximate: `log1p(0.0)` is
    `0.0`, so the near-feasible region is untouched to the last bit.
    """
    v = float(shortfall)
    if not math.isfinite(v):
        raise ValueError(f"shortfall must be finite, got {v!r}")
    if v < 0.0:
        raise ValueError(f"shortfall must be >= 0 (it is max(0, ...)), got {v!r}")
    p = min(v, 1.0)
    if v > 1.0:
        p += float(w) * math.log1p(v - 1.0)
    return min(p, float(row_cap))


def search_spec_reward(shortfalls: Mapping[str, float],
                       w: float = SEARCH_TAIL_W,
                       row_cap: float = SEARCH_ROW_CAP) -> float:
    """The infeasible-band ranking score: `-sum(row_penalty)/row_cap`, in `[-N, 0]`.

    Takes `shortfalls` — the dict `reward_v1.shortfalls()` returns — rather than
    margins, so the tolerances are read through `reward_v1` and this module never
    holds a second copy of them. **Exactly one definition of `TOL`** (the repo's
    third named failure mode: two definitions of one thing).
    """
    if not shortfalls:
        raise ValueError("shortfalls is empty; nothing to rank")
    total = sum(row_penalty(v, w, row_cap) for v in shortfalls.values())
    return -total / float(row_cap)


def score_breakdown(rb: R.RewardBreakdown, w: float = SEARCH_TAIL_W,
                    row_cap: float = SEARCH_ROW_CAP) -> float:
    """Rank score for one `RewardBreakdown`. **Only the infeasible band moves.**

    Feasible, headroom-only and invalid all return `rb.reward` untouched, so the
    band ordering is `reward_v1`'s and this function cannot invert it.
    """
    if not rb.valid or rb.headroom_only or rb.feasible:
        return float(rb.reward)
    if not rb.shortfalls:
        return float(rb.reward)
    return search_spec_reward(rb.shortfalls, w, row_cap) - float(rb.cost_penalty)


def score_margins(margins: Mapping[str, float], specs: Sequence[str],
                  w: float = SEARCH_TAIL_W,
                  row_cap: float = SEARCH_ROW_CAP) -> Optional[float]:
    """Rank score from a stored per-row `margins` dict, or `None` if incomplete.

    This is the path used on `adaptive_screen.PointResult.margins`, which is what
    a screened evaluation keeps. **Returns `None` rather than guessing** when a
    row named in `specs` is absent from `margins`: a missing row is exactly the
    G101/G106 shape (a set that loses members silently), and a ranking computed
    from a partial spec set would be systematically higher than one computed from
    the full set — which is the *"rewards not being measured"* defect
    `PROGRESS.md` §6 records the spread probe hitting.
    """
    names = tuple(specs)
    if not names or any(k not in margins for k in names):
        return None
    s = R.shortfalls(margins, names)
    if not any(v > 0.0 for v in s.values()):
        # Every row met at this point: the clipped and unclipped scores agree by
        # construction and this function has no business inventing a feasible
        # score (which needs `feasible_bonus`, not a shortfall sum).
        return None
    return search_spec_reward(s, w, row_cap)


def score_design_eval(ev, specs: Sequence[str], w: float = SEARCH_TAIL_W,
                      row_cap: float = SEARCH_ROW_CAP) -> float:
    """Rank score for an `adaptive_screen.DesignEval`. **Worst point wins.**

    Two things happen here, and the second is a defect fix in its own right.

    1. An evaluation that is not `ok` — a point that could not be scored at all —
       **passes straight through**. `evaluate_at_points` puts those in a graded
       invalid band (`invalid_reward(N) + n_scorable/n_points`) that sits below
       every real score, and G107 is explicit that *"cannot be scored" is not
       "fails"*. Re-ranking it here would either kill the search or fake a pass.

    2. The worst point is re-selected **by the unclipped score**. `DesignEval`
       chose its worst point with `pr.reward < worst.reward` — the *clipped*
       number — so with two rows saturated at different corners the recorded
       "worst" point was whichever tied first. On a plateau that choice was
       arbitrary; unclipped it is determined. So this re-derives the minimum over
       all scorable points rather than trusting `ev.margins`, and falls back to
       `ev.reward` if no point carries a complete margin set.
    """
    if not getattr(ev, "ok", False):
        return float(ev.reward)

    best: Optional[float] = None
    for pr in (getattr(ev, "points", None) or ()):
        if not getattr(pr, "ok", False):
            continue
        if getattr(pr, "feasible", False):
            sc = float(pr.reward)
        else:
            sc = score_margins(getattr(pr, "margins", {}) or {}, specs, w, row_cap)
            if sc is None:
                sc = float(pr.reward)
        best = sc if best is None else min(best, sc)

    if best is None:
        # No per-point detail retained (some callers drop it). Fall back to the
        # design-level margins, and to the clipped verdict if those are absent.
        sc = score_margins(getattr(ev, "margins", {}) or {}, specs, w, row_cap)
        return float(ev.reward) if sc is None else sc
    return best


@dataclass(frozen=True)
class RankView:
    """A one-field shim: the scalar `method_cmaes` minimises, and nothing else.

    `baselines.method_cmaes` reads exactly one attribute from whatever an
    objective returns — `f[i] = -obj.evaluate(X[i]).reward` — and uses it only as
    an `argsort` key. So handing it a `RankView` steers the search on the
    unclipped score **without touching `baselines.py`**, which is the benchmark
    every published arm was measured through and must not move.

    **It carries the rank scalar ONLY, deliberately.** A shim that proxied
    `feasible`, `margins` or `u` as well would be a second thing shaped like a
    `DesignEval` (`CLAUDEwa.md` §8 rule 9: one definition, referenced, never
    redeclared), and a caller reaching for `.feasible` would silently read the
    search's opinion instead of the verdict. Here that attempt raises
    `AttributeError` at once. The real `DesignEval` stays on the objective.
    """

    reward: float


__all__ = (
    "SEARCH_TAIL_W", "SEARCH_ROW_CAP", "row_penalty", "search_spec_reward",
    "score_breakdown", "score_margins", "score_design_eval", "RankView",
)
