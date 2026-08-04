"""
modulation.py — the symbol alphabet, as one object instead of scattered literals.

WHY THIS EXISTS
---------------
This framework was built for 112G **PAM-4**. The Nebula track (CLAUDEwa.md)
needs 5 Gbps **NRZ**. `nebula/NRZ_RETARGET_AUDIT.md` found **24** places where
a four-level assumption is baked in as a bare literal — `sqrt(5)`, `0.25`,
`3.0`, `/4.0`, `4.0` — most of them SILENT: wrong by a finite factor, no error,
completely plausible output.

The rule governing the retarget (CLAUDEwa.md §4.3, §8 rule 3):

    Keep the PAM-4 path working behind a flag. Do not fork the repo.
    The existing tests stay green.

So every alphabet-dependent constant should be read off one of these objects
rather than written as a number at its point of use. `PAM4` reproduces the
current behaviour exactly, and is the default everywhere, which is what keeps
the existing suite green without editing it.

Every quantity here is DERIVED from `levels`. None of them is a tuned or
chosen number, which matters because CLAUDEwa.md §8 rule 6 forbids an agent
picking values autonomously — `mean_square` for PAM-4 comes out at exactly the
5.0 that was previously hard-coded, because it is E[a²] over {±1, ±3} and
nothing else.

SCOPE WARNING — READ BEFORE USING `NRZ`
---------------------------------------
As of 2026-08-04 only ONE consumer reads this object: `StatisticalEye`'s
`crossing_jitter_ui()`. The BER mathematics (audit group B), the slicers
(group C), the bit mapping (group D) and the remaining amplitude constants
(group E) are still PAM-4-only. `StatisticalEye` therefore REFUSES to run its
BER path in NRZ mode rather than returning a number that is 0.75x the truth.
Extend deliberately, group by group, in the order the audit recommends.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple, Union

import numpy as np


@dataclass(frozen=True)
class Modulation:
    """A pulse-amplitude symbol alphabet and everything derivable from it.

    Attributes
    ----------
    name             "pam4" or "nrz"; the value of the `modulation` flag.
    levels           the equiprobable symbol amplitudes, ascending.
    thresholds       the slicer decision boundaries, ascending. Always one
                     fewer than `levels`.
    bits_per_symbol  log2(len(levels)). Used by BER denominators, which is
                     audit item D4 — a denominator still assuming 2 bits per
                     symbol reports HALF the true NRZ BER.
    """

    name: str
    levels: np.ndarray
    thresholds: np.ndarray
    bits_per_symbol: int

    def __post_init__(self) -> None:
        levels = np.asarray(self.levels, dtype=float)
        thresh = np.asarray(self.thresholds, dtype=float)
        object.__setattr__(self, "levels", levels)
        object.__setattr__(self, "thresholds", thresh)

        if levels.ndim != 1 or levels.size < 2:
            raise ValueError(f"{self.name}: need at least two levels, got {levels}")
        if not np.all(np.diff(levels) > 0):
            raise ValueError(f"{self.name}: levels must be strictly ascending, got {levels}")
        if thresh.size != levels.size - 1:
            raise ValueError(
                f"{self.name}: {levels.size} levels need {levels.size - 1} "
                f"thresholds, got {thresh.size}"
            )
        if 2 ** self.bits_per_symbol != levels.size:
            raise ValueError(
                f"{self.name}: {levels.size} levels is not 2^{self.bits_per_symbol}"
            )
        if not np.isclose(levels.mean(), 0.0):
            raise ValueError(f"{self.name}: alphabet must be zero-mean, got {levels}")

    # ── derived quantities: every one of these replaces a bare literal ──────

    @property
    def n_levels(self) -> int:
        return int(self.levels.size)

    @property
    def symbol_probability(self) -> float:
        """1/M. Replaces the `0.25` in `isi_pmf` (audit B4)."""
        return 1.0 / self.n_levels

    @property
    def max_level(self) -> float:
        """max|a|. Replaces the `3.0` ISI grid span in `isi_pmf` (audit B5)."""
        return float(np.max(np.abs(self.levels)))

    @property
    def mean_square(self) -> float:
        """E[a²] for equiprobable symbols.

        PAM-4: (9+1+1+9)/4 = **5.0** — the literal that appears as `sqrt(5)`
        in the AGC (audit E1) and as `sqrt(5.0 * ...)` in `crossing_jitter_ui`
        (audit E5). NRZ: (1+1)/2 = **1.0**.

        Using the PAM-4 value on NRZ overestimates crossing jitter by
        sqrt(5) = 2.24x, which would falsely declare the CDR infeasible on
        perfectly good configurations.
        """
        return float(np.mean(self.levels ** 2))

    @property
    def rms(self) -> float:
        """sqrt(E[a²]). PAM-4: sqrt(5) = 2.236. NRZ: 1.0. (audit E1)"""
        return float(np.sqrt(self.mean_square))

    @property
    def level_spacing(self) -> float:
        """Distance between adjacent levels — 2.0 for both alphabets here."""
        return float(np.min(np.diff(self.levels)))

    def is_adjacent(self, level: float, threshold: float) -> bool:
        """Is `threshold` the boundary immediately beside `level`?

        Replaces the bare `abs(a0 - thr) > 1.01` literal in the BER sum
        (audit B3), which happens to work for NRZ *by luck* because the
        level-to-threshold distance is 1.0 in both alphabets.
        """
        return bool(abs(level - threshold) <= self.level_spacing / 2.0 + 1e-9)


#: Four-level, Gray-coded. The framework's original and still-default target.
PAM4 = Modulation(
    name="pam4",
    levels=np.array([-3.0, -1.0, 1.0, 3.0]),
    thresholds=np.array([-2.0, 0.0, 2.0]),
    bits_per_symbol=2,
)

#: Two-level. What CLAUDEwa.md's 5 Gbps PCIe Gen2 link actually uses.
NRZ = Modulation(
    name="nrz",
    levels=np.array([-1.0, 1.0]),
    thresholds=np.array([0.0]),
    bits_per_symbol=1,
)

_REGISTRY = {m.name: m for m in (PAM4, NRZ)}

ModulationLike = Union[str, Modulation]


def get(modulation: ModulationLike) -> Modulation:
    """Resolve a flag value to a `Modulation`. Unknown names fail loudly."""
    if isinstance(modulation, Modulation):
        return modulation
    try:
        return _REGISTRY[str(modulation).lower()]
    except KeyError:
        raise ValueError(
            f"unknown modulation {modulation!r}; expected one of "
            f"{sorted(_REGISTRY)}"
        ) from None


__all__: Tuple[str, ...] = ("Modulation", "PAM4", "NRZ", "get", "ModulationLike")
