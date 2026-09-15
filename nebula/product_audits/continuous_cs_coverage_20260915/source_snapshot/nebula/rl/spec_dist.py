"""
rl/spec_dist.py — **the distribution of target specs, and the two splits.**

WHY THIS FILE EXISTS
---------------------
`CLAUDEwa.md` §7 claims a **spec-conditioned policy** as one of the project's
two contributions: *"`TargetSpec` enters the observation. Train across a
distribution of specs; evaluate on held-out specs never seen in training. This
is the live demo."*

The plumbing for that has existed since the interface froze —
`contract.build_observation` carries a two-channel target block and
`EnvConfig` takes `target_peaking_db` and `target_f_peak_hz`. **What has never
existed is the distribution.** Every run this project has ever done froze both
channels at the window centre, and a constant input carries no information, so
no policy has ever had a reason to read them. This file is the missing half.

**ONLY S3 IS A TARGET. EVERYTHING ELSE IN THE SPEC TABLE IS A LIMIT.**
This is worth stating because it decides the whole shape of the problem. S4
(HD3 < -30 dBc), S5 (noise < 1.5 mV), S6 (power < 15 mW), S7 (area), S8 (eye)
are **thresholds**: every design faces the same one and "exceeding" it is worth
nothing (`CLAUDEwa.md` §9 — the reward saturates at zero once a spec is met).
S3 alone says *"3-12 dB, tunable, peak in 1.25-2.5 GHz"* — a value to HIT, and
the only row whose margin is a signed distance to a requested number. So a
spec-conditioned policy here is conditioned on **two numbers**, and the
observation's target block is exactly those two.

THE DISTRIBUTION IS THE SPEC TABLE, NOT A CHOICE
--------------------------------------------------
`CLAUDEwa.md` §8 rule 6 forbids choosing spec-tightness heuristics
autonomously, so nothing here is invented:

* **peaking**: uniform on **[3, 12] dB** — S3's band, verbatim.
* **f_peak**: uniform in **OCTAVES** on [1.25, 2.5] GHz, i.e. log-uniform in
  hertz. Not a preference: S3's window is exactly one octave, every frequency
  result in this project is quoted in octaves (`contract.f_peak_octaves`), and
  a hertz-uniform draw would put half its mass above 1.875 GHz and make the
  low end of the spec's own window rare.

THE TWO SPLITS, AND WHY BOTH
------------------------------
Decided by the owner, 2026-08-20, and reported separately:

* **INTERPOLATION** (`interpolation_split`) — train on targets scattered over
  the whole band, hold out a random handful. Answers *"can it fill in between
  things it has seen?"* This is the claim a live demo actually makes, and it is
  the headline.
* **EXTRAPOLATION** (`extrapolation_split`) — train on the LOW half of the
  peaking band, test on the HIGH half. Answers *"has it learned the mapping or
  memorised the neighbourhood?"* A much stronger claim, and much more likely to
  fail.

**The split is on PEAKING, not on frequency**, for two reasons that are
measured rather than aesthetic. High peaking is the hard end — session 9c's
hand-sizing found configurations spanning **4.63-10.01 dB** and never reached
S3's 12 dB ceiling — so the low->high direction is the demanding one. And the
frequency window is only ONE octave wide, so halving it leaves a test region
too thin to be a region.

NOTHING HERE SIMULATES, AND NOTHING HERE IS RANDOM WITHOUT A SEED.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterator, Sequence

import numpy as np

from nebula.common.types import SPEC_F_PEAK_HZ_RANGE, SPEC_PEAKING_DB_RANGE
from nebula.rl.contract import f_peak_octaves


@dataclass(frozen=True)
class SpecTarget:
    """The two numbers a spec-conditioned policy is conditioned on.

    Deliberately NOT `common.types.TargetSpec`: that carries all eight spec
    rows, six of which are fixed limits identical for every design. Mixing a
    target with a threshold in one object is how a limit ends up being treated
    as something to aim at.
    """

    peaking_db: float
    f_peak_hz: float

    def __post_init__(self) -> None:
        lo_db, hi_db = SPEC_PEAKING_DB_RANGE
        lo_hz, hi_hz = SPEC_F_PEAK_HZ_RANGE
        if not (lo_db <= self.peaking_db <= hi_db):
            raise ValueError(
                f"peaking {self.peaking_db} dB is outside S3's {lo_db}-{hi_db} dB "
                f"band; a target outside the spec is not a target")
        if not (lo_hz <= self.f_peak_hz <= hi_hz):
            raise ValueError(
                f"f_peak {self.f_peak_hz/1e9:.3f} GHz is outside S3's "
                f"{lo_hz/1e9:.2f}-{hi_hz/1e9:.2f} GHz window")

    @property
    def f_peak_oct(self) -> float:
        """Octaves relative to Nyquist. THE conversion, imported not restated."""
        return f_peak_octaves(self.f_peak_hz)

    def as_key(self) -> tuple[float, float]:
        """A hashable identity, rounded so a float round trip cannot split one
        target into two."""
        return (round(self.peaking_db, 6), round(self.f_peak_hz, 3))


#: The centre of the band — **the single target every published run used**, and
#: therefore the point every existing number is comparable at. Kept here so the
#: conditioned work can always be read against the unconditioned baseline.
LEGACY_TARGET: SpecTarget = SpecTarget(
    peaking_db=sum(SPEC_PEAKING_DB_RANGE) / 2.0,
    f_peak_hz=math.sqrt(SPEC_F_PEAK_HZ_RANGE[0] * SPEC_F_PEAK_HZ_RANGE[1]),
)

#: Where the extrapolation split cuts the peaking band. The MIDPOINT of S3,
#: which is also `LEGACY_TARGET`'s peaking — so the training region for the
#: extrapolation arm is exactly "everything at or below what every previous run
#: aimed at", and the test region is everything above it.
EXTRAP_SPLIT_DB: float = sum(SPEC_PEAKING_DB_RANGE) / 2.0


def sample_target(rng: np.random.Generator,
                  peaking_db_range: Sequence[float] = SPEC_PEAKING_DB_RANGE,
                  f_peak_hz_range: Sequence[float] = SPEC_F_PEAK_HZ_RANGE
                  ) -> SpecTarget:
    """One target: uniform in dB, uniform in OCTAVES.

    The octave draw is `2 ** U(log2 lo, log2 hi)`, which is log-uniform in
    hertz. See the module docstring for why that is the spec's own scale and
    not a preference.
    """
    lo_db, hi_db = float(peaking_db_range[0]), float(peaking_db_range[1])
    lo_hz, hi_hz = float(f_peak_hz_range[0]), float(f_peak_hz_range[1])
    if not (lo_db < hi_db and 0.0 < lo_hz < hi_hz):
        raise ValueError(f"degenerate range: {peaking_db_range} {f_peak_hz_range}")
    db = float(rng.uniform(lo_db, hi_db))
    oct_lo, oct_hi = math.log2(lo_hz), math.log2(hi_hz)
    hz = float(2.0 ** rng.uniform(oct_lo, oct_hi))
    # The uniform draw can land a hair outside after the exponentiation's
    # rounding; clip rather than raise, because the band edge is a legal target.
    hz = min(max(hz, lo_hz), hi_hz)
    return SpecTarget(peaking_db=db, f_peak_hz=hz)


def sample_targets(n: int, seed: int, **kw) -> list[SpecTarget]:
    """`n` independent targets from one stated seed."""
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    rng = np.random.default_rng(seed)
    return [sample_target(rng, **kw) for _ in range(n)]


@dataclass(frozen=True)
class Split:
    """A train/test partition of target space, and what it licenses."""

    name: str
    train: tuple[SpecTarget, ...]
    test: tuple[SpecTarget, ...]
    claim: str

    def __post_init__(self) -> None:
        overlap = {t.as_key() for t in self.train} & {t.as_key() for t in self.test}
        if overlap:
            raise ValueError(
                f"{self.name}: {len(overlap)} target(s) are in BOTH train and "
                f"test. A held-out spec that was trained on is not held out.")


def interpolation_split(n_train: int = 64, n_test: int = 16,
                        seed: int = 20260820) -> Split:
    """Random targets over the whole band; a random handful held out.

    **The headline split.** It answers the question a live demo poses: someone
    types a spec inside S3 and the policy has seen targets on both sides of it.
    """
    all_t = sample_targets(n_train + n_test, seed)
    return Split(
        name="interpolation",
        train=tuple(all_t[:n_train]),
        test=tuple(all_t[n_train:]),
        claim=("held-out targets are interior to the training band, so this "
               "licenses 'it fills in between specs it has seen' and NOT 'it "
               "generalises beyond them'"),
    )


def extrapolation_split(n_train: int = 64, n_test: int = 16,
                        seed: int = 20260821,
                        split_db: float = EXTRAP_SPLIT_DB) -> Split:
    """Train on the LOW half of S3's peaking band, test on the HIGH half.

    **The stronger and riskier claim.** Nothing in training sits above
    `split_db`, so a policy that has memorised neighbourhoods has nothing to
    interpolate from and must have learned the mapping to score at all.
    """
    lo_db, hi_db = SPEC_PEAKING_DB_RANGE
    if not (lo_db < split_db < hi_db):
        raise ValueError(f"split_db {split_db} is not inside {lo_db}-{hi_db}")
    train = sample_targets(n_train, seed, peaking_db_range=(lo_db, split_db))
    test = sample_targets(n_test, seed + 1,
                          peaking_db_range=(split_db, hi_db))
    return Split(
        name="extrapolation",
        train=tuple(train), test=tuple(test),
        claim=(f"no training target exceeds {split_db:.1f} dB of peaking and "
               f"every test target does, so this licenses 'it learned the "
               f"mapping' rather than 'it memorised the neighbourhood'"),
    )


def describe(split: Split) -> dict:
    """Auditable summary. Every experiment writes this into its log header."""
    def _stats(ts: Sequence[SpecTarget]) -> dict:
        db = np.array([t.peaking_db for t in ts], dtype=float)
        oc = np.array([t.f_peak_oct for t in ts], dtype=float)
        return {"n": int(db.size),
                "peaking_db": [float(db.min()), float(db.max())],
                "f_peak_oct": [float(oc.min()), float(oc.max())]}

    return {"name": split.name, "claim": split.claim,
            "train": _stats(split.train), "test": _stats(split.test),
            "legacy_target": {"peaking_db": LEGACY_TARGET.peaking_db,
                              "f_peak_hz": LEGACY_TARGET.f_peak_hz,
                              "note": "the single target every published run "
                                      "used; kept so conditioned results can "
                                      "be read against unconditioned ones"}}


__all__ = ["SpecTarget", "Split", "LEGACY_TARGET", "EXTRAP_SPLIT_DB",
           "sample_target", "sample_targets", "interpolation_split",
           "extrapolation_split", "describe"]
