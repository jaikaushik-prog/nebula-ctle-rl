"""
rl/reward.py — the scalar the policy maximises. CLAUDEwa.md §9.

    R_spec  = SUM_i  min( (x_i - tau_i) / (|x_i| + |tau_i|), 0 )   over S3..S8
    R_total = R_spec(worst corner) + R_discriminator

Three properties of that form, and why each one matters
-------------------------------------------------------
1. **Non-positive, saturating at zero.** Once a spec is met the term is
   exactly 0 and further improvement is worth *nothing*. §9 is explicit:
   "Do not add bonus terms for exceeding a spec." A bonus is what lets a
   policy trade a met spec against an unmet one — it buys 3 dB of spare
   peaking with a noise violation and the reward goes up.

2. **Normalised per spec.** Dividing by (|x| + |tau|) puts every term on the
   same [-1, 0] scale, so 15 mW of power and 1.5 mV of noise contribute
   comparably. Without it, whichever spec happens to have the largest
   numerical magnitude dominates the gradient.

3. **Worst corner, not nominal.** CLAUDEwa.md §12 lists "optimising at nominal
   and checking corners afterwards" as the first known trap, and §7 makes
   worst-case scoring one of the two claimed contributions. `min` over
   corners, from the start.

What this module deliberately does NOT decide
---------------------------------------------
§8 rule 6: an agent does not choose reward weights or spec-tightness
heuristics. So:

* there are no per-term weights — §9 specifies equal weighting via the
  normalisation, and adding weights would be inventing a knob;
* the S3 match tolerances were set by a human on 2026-08-03 (+/-1 dB,
  +/-10% of f_peak) with the reasoning recorded on `RewardConfig`, and they
  are reporting axes rather than hidden constants — see `TOLERANCE_SWEEP`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Iterable, Literal, Sequence

from nebula.common.types import DeviceResult, LinkResult, TargetSpec

Direction = Literal["min", "max", "match"]


@dataclass(frozen=True)
class SpecTerm:
    """One constrained quantity: its measured value, its target, its sense.

    direction
        "max"    satisfied when value >= target   (eye height, eye width)
        "min"    satisfied when value <= target   (HD3, noise, power, area)
        "match"  satisfied when |value - target| <= tol   (the S3 tunables)
    """

    name: str
    value: float
    target: float
    direction: Direction
    tol: float = 0.0

    def margin(self) -> float:
        """Signed slack in the quantity's own units. >= 0 means satisfied."""
        if self.direction == "max":
            return self.value - self.target
        if self.direction == "min":
            return self.target - self.value
        if self.direction == "match":
            return self.tol - abs(self.value - self.target)
        raise ValueError(f"unknown direction {self.direction!r}")

    def shortfall(self) -> float:
        """The §9 term: min(margin / (|value| + |target|), 0), in [-1, 0].

        Known asymmetry: the normaliser depends on `value`, so for a "match"
        term an undershoot is penalised slightly harder than an equal
        overshoot (the denominator is smaller). That is inherent to the §9
        form, not an implementation choice. It is pinned by a test so it stays
        a known property rather than becoming a September surprise.
        """
        denom = abs(self.value) + abs(self.target)
        if denom == 0.0:
            # value == target == 0: satisfied for "max"/"min", and for "match"
            # only if tol >= 0, which it always is. No shortfall either way.
            return 0.0
        return min(self.margin() / denom, 0.0)

    @property
    def met(self) -> bool:
        return self.margin() >= 0.0


def shortfall(value: float, target: float, direction: Direction, tol: float = 0.0) -> float:
    """Functional form of `SpecTerm.shortfall`, for tests and analysis."""
    return SpecTerm("_", value, target, direction, tol).shortfall()


@dataclass(frozen=True)
class RewardConfig:
    """The two S3 tolerances §9 does not fix, plus the failure floor.

    peaking_tol_db
        How close to the requested peaking counts as reaching it. Default
        +/-1.0 dB, set by a human on 2026-08-03 and deliberately LOOSE: at
        G3 the policy has to be able to learn something, and a tolerance
        tighter than the reward gradient can resolve just makes every early
        proposal score identically badly.

        Worth stating in the report: real CTLEs tune in discrete steps,
        typically a dB or two apart, so +/-1 dB is already at production
        granularity and +/-0.5 dB would be *tighter than the hardware*. That
        is what makes a loose-looking tolerance defensible rather than lazy.

    f_peak_tol_frac
        Peak-frequency tolerance as a FRACTION of the requested f_peak, so it
        scales across the 1.25-2.5 GHz S3 range instead of being absurdly
        tight at one end. Default 0.10 (+/-10%), same reasoning as above.

    Both are reporting axes, not hidden constants: sweep them and show pass
    rate versus tolerance rather than quoting a single pass/fail at one
    setting. `TOLERANCE_SWEEP` below is the intended axis.

    failed_reward
        Reward for an evaluation that did not produce numbers (non-convergent
        ngspice, rejected pole-zero fit, compressed stage, failed link).
        Defaults to -N_SPEC_TERMS, which is the mathematical floor of R_spec
        rather than a tuned penalty: every term is bounded below by -1, so a
        failure is scored exactly as badly as violating every spec maximally
        and no worse. Making it *more* negative would be a tuned heuristic;
        making it less negative would let the policy prefer crashing to trying.
    """

    peaking_tol_db: float = 1.0
    f_peak_tol_frac: float = 0.10
    failed_reward: float | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.peaking_tol_db) or self.peaking_tol_db <= 0.0:
            raise ValueError(
                f"peaking_tol_db must be positive and finite, got {self.peaking_tol_db!r}"
            )
        if not math.isfinite(self.f_peak_tol_frac) or not 0.0 < self.f_peak_tol_frac < 1.0:
            raise ValueError(
                f"f_peak_tol_frac is a fraction of the target f_peak and must lie "
                f"in (0, 1), got {self.f_peak_tol_frac!r}"
            )
        if self.failed_reward is None:
            object.__setattr__(self, "failed_reward", -float(N_SPEC_TERMS))
        elif self.failed_reward > 0.0:
            raise ValueError("failed_reward must be non-positive")

    def f_peak_tol_hz(self, target_f_peak_hz: float) -> float:
        """Absolute peak-frequency tolerance for a given requested f_peak."""
        return self.f_peak_tol_frac * float(target_f_peak_hz)


#: The tolerance axis to report against, rather than a single hidden setting.
#: (peaking_tol_db, f_peak_tol_frac) pairs, loosest first.
TOLERANCE_SWEEP: tuple[tuple[float, float], ...] = (
    (2.0, 0.20),
    (1.0, 0.10),   # default
    (0.5, 0.05),   # tighter than typical production CTLE tuning steps
)


#: S3 (2 terms), S4, S5, S6, S7, S8 (2 terms).
SPEC_TERM_NAMES: tuple[str, ...] = (
    "peaking_db",   # S3
    "f_peak_hz",    # S3
    "hd3_dbc",      # S4
    "vn_in_vrms",   # S5
    "power_w",      # S6
    "area_mm2",     # S7
    "eye_h_v",      # S8
    "eye_w_ui",     # S8
)
N_SPEC_TERMS: int = len(SPEC_TERM_NAMES)


def spec_terms(
    dev: DeviceResult,
    link: LinkResult,
    target: TargetSpec,
    cfg: RewardConfig,
) -> tuple[SpecTerm, ...]:
    """Build the S3..S8 terms. Both results must be ok.

    Exposed separately from `reward()` because the September results table
    needs per-spec margins, not just the scalar — §8 rule 8, log everything.
    """
    if not dev.ok or not link.ok:
        raise ValueError("spec_terms requires ok results; call reward() instead")

    return (
        SpecTerm("peaking_db", dev.peaking_db, target.peaking_db,      # type: ignore[arg-type]
                 "match", cfg.peaking_tol_db),
        SpecTerm("f_peak_hz", dev.f_peak_hz, target.f_peak_hz,         # type: ignore[arg-type]
                 "match", cfg.f_peak_tol_hz(target.f_peak_hz)),
        SpecTerm("hd3_dbc", dev.hd3_dbc, target.hd3_max_dbc, "min"),   # type: ignore[arg-type]
        SpecTerm("vn_in_vrms", dev.vn_in_vrms, target.vn_in_max_vrms, "min"),   # type: ignore[arg-type]
        SpecTerm("power_w", dev.power_w, target.power_max_w, "min"),   # type: ignore[arg-type]
        SpecTerm("area_mm2", dev.area_mm2, target.area_max_mm2, "min"),  # type: ignore[arg-type]
        SpecTerm("eye_h_v", link.eye_h_v, target.eye_h_min_v, "max"),  # type: ignore[arg-type]
        SpecTerm("eye_w_ui", link.eye_w_ui, target.eye_w_min_ui, "max"),  # type: ignore[arg-type]
    )


def reward(
    dev: DeviceResult,
    link: LinkResult,
    target: TargetSpec,
    cfg: RewardConfig,
) -> float:
    """R_spec for ONE corner. Non-positive, zero exactly when all specs are met.

    The §5.1 signature is `reward(dev, link, target)`; `cfg` carries the two
    human-set tolerances. Use `make_reward_fn(cfg)` to get the three-argument
    callable that §5.1 specifies.

    Never raises: a failed device or link evaluation returns
    `cfg.failed_reward`, because the RL loop cannot tolerate exceptions
    (§8 rule 2).
    """
    if not dev.ok or not link.ok:
        return float(cfg.failed_reward)  # type: ignore[arg-type]
    return float(sum(t.shortfall() for t in spec_terms(dev, link, target, cfg)))


def make_reward_fn(
    cfg: RewardConfig,
) -> Callable[[DeviceResult, LinkResult, TargetSpec], float]:
    """Bind a config to get the exact §5.1 signature."""

    def _reward(dev: DeviceResult, link: LinkResult, target: TargetSpec) -> float:
        return reward(dev, link, target, cfg)

    return _reward


def worst_corner_reward(
    per_corner: Iterable[float] | Sequence[float],
) -> float:
    """R_spec(worst corner) = min over corners (CLAUDEwa.md §9, §12).

    An empty sequence is an error, not a zero: "no corners evaluated" must not
    read as "all corners passed".
    """
    values = [float(v) for v in per_corner]
    if not values:
        raise ValueError(
            "worst_corner_reward got no corners. An empty corner set is a bug "
            "in the fidelity scheduler, not a design that passed everywhere."
        )
    if any(math.isnan(v) for v in values):
        raise ValueError("per-corner rewards contain nan — a failed corner must "
                         "map to cfg.failed_reward, not nan")
    return min(values)


def total_reward(spec_reward_worst_corner: float, r_discriminator: float = 0.0) -> float:
    """R_total = R_spec(worst corner) + R_discriminator (§9).

    The discriminator term (the OOD penalty from the ISCAS paper's Eq. 3-4)
    is passed in already scaled. Its weight is an RL-layer hyperparameter and
    a human decision — this function does not invent one.
    """
    if r_discriminator > 0.0:
        raise ValueError(
            f"r_discriminator must be non-positive (it is a penalty), got "
            f"{r_discriminator}. A positive OOD term would reward the policy "
            f"for leaving the surrogate's trust region."
        )
    return float(spec_reward_worst_corner + r_discriminator)
