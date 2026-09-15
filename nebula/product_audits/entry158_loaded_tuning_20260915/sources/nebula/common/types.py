"""
common/types.py — the frozen interface contract between the three layers.

This file is transcribed from CLAUDEwa.md §5.1. It is the ONLY place these
shapes are defined. Changing a field here is a human decision that breaks
three workstreams at once: propose it, do not do it unilaterally
(CLAUDEwa.md §8 rule 5).

Two conventions that everything downstream depends on
-----------------------------------------------------
1. **Units are explicit in every field name.** `_hz`, `_v`, `_w`, `_db`,
   `_dbc`, `_ui`, `_mm2`, `_vrms`, `_mm2`. `g_dc` is the one exception and it
   is linear V/V, never dB. If you are unsure what unit a number is in, the
   field name is wrong, not the number.

2. **Failure is a value, not an exception** (CLAUDEwa.md §8 rule 2). A
   non-converging ngspice run returns `DeviceResult(ok=False, ...)`. The RL
   loop must never see a traceback from the device or link layer.
   Numeric fields on a failed result are `None`, deliberately: `None`
   explodes the moment anyone does arithmetic on it, whereas `nan` would
   propagate silently into a reward and poison a training run without a
   single error message. That is CLAUDEwa.md §8 rule 1 ("if a value is
   unknown, leave it None and fail loudly") applied literally.

Numeric fields are annotated `Optional[float]` for that reason. The
invariant, enforced in `__post_init__`, is:

    ok is True   <=>  every numeric field is a finite float
    ok is False  <=>  fail_reason is a non-empty string

so consumer code may treat `ok=True` results as fully populated without
defensive checks.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal, Optional, Sequence

import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
# Specification constants — transcribed verbatim from CLAUDEwa.md §3.
#
# These are HUMAN-DECIDED values from the Astera problem statement. They are
# not tunable, not heuristics, and not to be edited by an agent (§8 rule 5).
# Every one of them is traceable to a row of the §3 spec table.
# ─────────────────────────────────────────────────────────────────────────────

BAUD_RATE_HZ: float = 5.0e9          # S1: PCIe Gen2, NRZ, 5.0 Gbps
NYQUIST_HZ: float = 2.5e9            # S1: fbaud / 2
UI_SECONDS: float = 1.0 / BAUD_RATE_HZ

SPEC_PEAKING_DB_RANGE: tuple[float, float] = (3.0, 12.0)        # S3
SPEC_F_PEAK_HZ_RANGE: tuple[float, float] = (1.25e9, 2.5e9)     # S3
SPEC_HD3_MAX_DBC: float = -30.0                                 # S4
SPEC_VN_IN_MAX_VRMS: float = 1.5e-3                             # S5
SPEC_POWER_MAX_W: float = 15.0e-3                               # S6
SPEC_AREA_MAX_MM2: float = 0.05                                 # S7
SPEC_EYE_H_MIN_V: float = 100.0e-3                              # S8
SPEC_EYE_W_MIN_UI: float = 0.4                                  # S8

# S5 integration band for input-referred noise.
NOISE_BAND_HZ: tuple[float, float] = (10.0e6, 5.0e9)

# S4 test tone for HD3.
HD3_TONE_HZ: float = 100.0e6

# §5.3b: a pole-zero fit worse than this is garbage and must be rejected
# rather than passed downstream.
FIT_RESIDUAL_REJECT_DB: float = 0.5


# ─────────────────────────────────────────────────────────────────────────────
# Corner
# ─────────────────────────────────────────────────────────────────────────────

ProcessCorner = Literal["tt", "ss", "ff", "sf", "fs"]

PROCESS_CORNERS: tuple[ProcessCorner, ...] = ("tt", "ss", "ff", "sf", "fs")
VDD_SCALES: tuple[float, ...] = (0.95, 1.00, 1.05)
TEMPS_C: tuple[float, ...] = (0.0, 27.0, 125.0)


@dataclass(frozen=True)
class Corner:
    """One PVT corner (CLAUDEwa.md S9).

    S9 requires S3-S8 to hold at *every* corner simultaneously. A design that
    passes at tt/1.00/27 and fails at ss/0.95/125 is a failed design.
    """

    process: ProcessCorner
    vdd_scale: float          # 0.95, 1.00, 1.05
    temp_c: float             # 0, 27, 125

    def __post_init__(self) -> None:
        if self.process not in PROCESS_CORNERS:
            raise ValueError(
                f"process must be one of {PROCESS_CORNERS}, got {self.process!r}"
            )
        if not math.isfinite(self.vdd_scale) or self.vdd_scale <= 0.0:
            raise ValueError(f"vdd_scale must be positive and finite, got {self.vdd_scale!r}")
        if not math.isfinite(self.temp_c):
            raise ValueError(f"temp_c must be finite, got {self.temp_c!r}")

    @property
    def is_nominal(self) -> bool:
        return self.process == "tt" and self.vdd_scale == 1.00 and self.temp_c == 27.0

    def __str__(self) -> str:
        """Stable, filesystem-safe tag for experiment logging (§8 rule 8)."""
        return f"{self.process}_vdd{self.vdd_scale:.2f}_t{self.temp_c:g}"


TT_NOMINAL = Corner("tt", 1.00, 27.0)


def all_corners() -> tuple[Corner, ...]:
    """The full S9 sweep: 5 process x 3 VDD x 3 temp = 45 corners.

    Ordered with TT/1.00/27 first so that a truncated run (fidelity tier 2 in
    §7) always evaluates nominal before anything else.
    """
    rest = [
        Corner(p, v, t)
        for p in PROCESS_CORNERS
        for v in VDD_SCALES
        for t in TEMPS_C
        if not (p == "tt" and v == 1.00 and t == 27.0)
    ]
    return (TT_NOMINAL, *rest)


# ─────────────────────────────────────────────────────────────────────────────
# TargetSpec
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TargetSpec:
    """The target specification vector — the RL policy's conditioning input.

    `peaking_db` and `f_peak_hz` are the *requested operating point* inside the
    S3 tunable range, not the range itself. The spec-conditioned policy
    (CLAUDEwa.md §7, contribution 2) is trained over a distribution of these
    and evaluated on held-out values. The remaining six fields are hard
    constraints from §3 and are the same for every episode.
    """

    peaking_db: float         # 3..12
    f_peak_hz: float          # 1.25e9..2.5e9
    hd3_max_dbc: float        # -30
    vn_in_max_vrms: float     # 1.5e-3
    power_max_w: float        # 15e-3
    area_max_mm2: float       # 0.05
    eye_h_min_v: float        # 100e-3
    eye_w_min_ui: float       # 0.4

    def __post_init__(self) -> None:
        for name in (
            "peaking_db", "f_peak_hz", "hd3_max_dbc", "vn_in_max_vrms",
            "power_max_w", "area_max_mm2", "eye_h_min_v", "eye_w_min_ui",
        ):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise TypeError(f"TargetSpec.{name} must be a real number, got {value!r}")
            if not math.isfinite(float(value)):
                raise ValueError(f"TargetSpec.{name} must be finite, got {value!r}")

        lo, hi = SPEC_PEAKING_DB_RANGE
        if not lo <= self.peaking_db <= hi:
            raise ValueError(
                f"peaking_db {self.peaking_db} outside the S3 tunable range {lo}..{hi} dB"
            )
        lo, hi = SPEC_F_PEAK_HZ_RANGE
        if not lo <= self.f_peak_hz <= hi:
            raise ValueError(
                f"f_peak_hz {self.f_peak_hz:.4g} outside the S3 range {lo:.4g}..{hi:.4g} Hz"
            )

    @classmethod
    def pcie_gen2(cls, peaking_db: float, f_peak_hz: float) -> "TargetSpec":
        """Build a spec with the six fixed S4-S8 constraints from §3.

        Only the two tunable S3 values are arguments: there is no defensible
        default for the requested operating point, so the caller must state it.
        """
        return cls(
            peaking_db=float(peaking_db),
            f_peak_hz=float(f_peak_hz),
            hd3_max_dbc=SPEC_HD3_MAX_DBC,
            vn_in_max_vrms=SPEC_VN_IN_MAX_VRMS,
            power_max_w=SPEC_POWER_MAX_W,
            area_max_mm2=SPEC_AREA_MAX_MM2,
            eye_h_min_v=SPEC_EYE_H_MIN_V,
            eye_w_min_ui=SPEC_EYE_W_MIN_UI,
        )

    def as_vector(self) -> np.ndarray:
        """Observation-space encoding, in declaration order.

        Raw units. Normalisation for the policy observation is an RL-layer
        concern and is deliberately not baked in here.
        """
        return np.array(
            [
                self.peaking_db, self.f_peak_hz, self.hd3_max_dbc,
                self.vn_in_max_vrms, self.power_max_w, self.area_max_mm2,
                self.eye_h_min_v, self.eye_w_min_ui,
            ],
            dtype=float,
        )


# ─────────────────────────────────────────────────────────────────────────────
# DeviceResult
# ─────────────────────────────────────────────────────────────────────────────

#: Numeric fields of DeviceResult that must be finite when ok is True.
DEVICE_NUMERIC_FIELDS: tuple[str, ...] = (
    "g_dc", "f_zero_hz", "f_pole1_hz", "f_pole2_hz", "fit_residual_db",
    "peaking_db", "f_peak_hz", "hd3_dbc", "vn_in_vrms", "power_w",
    "area_mm2", "vout_swing_v",
)


@dataclass
class DeviceResult:
    """Output of the device layer: one CTLE evaluated at one corner.

    `vout_swing_v` is load-bearing and its definition is fixed here:

        the MAXIMUM LINEAR DIFFERENTIAL PEAK-TO-PEAK output swing of the CTLE
        at this corner, i.e. the compression limit, in volts.

    It is a property of the device alone — it does not depend on the input
    amplitude, which the device layer has no way of knowing. The link layer
    combines it with `g_dc` and its own input amplitude to get the actual
    output swing, and only then converts the normalised eye into millivolts
    (CLAUDEwa.md §5.3a). Get this definition wrong and every eye number in the
    report is fiction while looking entirely plausible. See
    `nebula.link.calibration` — that is the single place the conversion lives.
    """

    ok: bool
    fail_reason: Optional[str]
    g_dc: Optional[float]              # linear V/V, NOT dB
    f_zero_hz: Optional[float]
    f_pole1_hz: Optional[float]
    f_pole2_hz: Optional[float]
    fit_residual_db: Optional[float]   # RMS error of pole-zero fit
    peaking_db: Optional[float]
    f_peak_hz: Optional[float]
    hd3_dbc: Optional[float]
    vn_in_vrms: Optional[float]
    power_w: Optional[float]
    area_mm2: Optional[float]
    vout_swing_v: Optional[float]      # differential peak-to-peak, volts
    ac_freq_hz: Optional[np.ndarray] = None   # raw response, for diagnostics
    ac_mag_db: Optional[np.ndarray] = None

    def __post_init__(self) -> None:
        _validate_result(self, DEVICE_NUMERIC_FIELDS)
        if self.ok:
            if self.ac_freq_hz is None or self.ac_mag_db is None:
                raise ValueError("ok=True DeviceResult must carry the raw AC sweep")
            self.ac_freq_hz = np.asarray(self.ac_freq_hz, dtype=float)
            self.ac_mag_db = np.asarray(self.ac_mag_db, dtype=float)
            if self.ac_freq_hz.shape != self.ac_mag_db.shape:
                raise ValueError(
                    f"ac_freq_hz {self.ac_freq_hz.shape} and ac_mag_db "
                    f"{self.ac_mag_db.shape} must have the same shape"
                )

    @classmethod
    def failed(cls, reason: str) -> "DeviceResult":
        """The only way to build a failed result. `reason` must be specific.

        Use this for non-convergence, netlist errors, timeouts, and for
        pole-zero fits with residual > FIT_RESIDUAL_REJECT_DB (§5.3b): a bad
        fit is a failed evaluation, not a result to pass downstream.
        """
        if not reason or not reason.strip():
            raise ValueError("fail_reason must be a specific, non-empty string")
        return cls(
            ok=False, fail_reason=reason,
            g_dc=None, f_zero_hz=None, f_pole1_hz=None, f_pole2_hz=None,
            fit_residual_db=None, peaking_db=None, f_peak_hz=None,
            hd3_dbc=None, vn_in_vrms=None, power_w=None, area_mm2=None,
            vout_swing_v=None, ac_freq_hz=None, ac_mag_db=None,
        )

    @property
    def g_dc_db(self) -> float:
        """DC gain in dB. Guards against the linear/dB mix-up in `g_dc`."""
        if not self.ok:
            raise ValueError("g_dc_db is undefined on a failed DeviceResult")
        assert self.g_dc is not None
        if self.g_dc <= 0.0:
            raise ValueError(f"g_dc must be positive to express in dB, got {self.g_dc}")
        return 20.0 * math.log10(self.g_dc)


# ─────────────────────────────────────────────────────────────────────────────
# LinkResult
# ─────────────────────────────────────────────────────────────────────────────

LINK_NUMERIC_FIELDS: tuple[str, ...] = ("eye_h_v", "eye_w_ui", "ber", "dfe_tap")


@dataclass
class LinkResult:
    """Output of the link layer: the eye that a given CTLE actually delivers.

    `eye_h_v` is in VOLTS. Not normalised amplitude, not millivolts. The
    conversion happens exactly once, in `nebula.link.calibration`.
    """

    ok: bool
    eye_h_v: Optional[float]           # volts, NOT normalized
    eye_w_ui: Optional[float]
    ber: Optional[float]
    dfe_tap: Optional[float]
    bathtub: Optional[np.ndarray] = None
    fail_reason: Optional[str] = None

    def __post_init__(self) -> None:
        _validate_result(self, LINK_NUMERIC_FIELDS)
        if self.ok and not 0.0 <= float(self.ber) <= 1.0:  # type: ignore[arg-type]
            raise ValueError(f"ber must lie in [0, 1], got {self.ber}")
        if self.bathtub is not None:
            self.bathtub = np.asarray(self.bathtub, dtype=float)

    @classmethod
    def failed(cls, reason: str) -> "LinkResult":
        if not reason or not reason.strip():
            raise ValueError("fail_reason must be a specific, non-empty string")
        return cls(
            ok=False, eye_h_v=None, eye_w_ui=None, ber=None, dfe_tap=None,
            bathtub=None, fail_reason=reason,
        )

    @property
    def eye_h_mv(self) -> float:
        """Eye height in millivolts — for reporting only, never for maths."""
        if not self.ok:
            raise ValueError("eye_h_mv is undefined on a failed LinkResult")
        assert self.eye_h_v is not None
        return self.eye_h_v * 1e3


# ─────────────────────────────────────────────────────────────────────────────
# Shared validation
# ─────────────────────────────────────────────────────────────────────────────


def _validate_result(obj: object, numeric_fields: Sequence[str]) -> None:
    """Enforce the ok/None invariant documented at the top of this module."""
    cls_name = type(obj).__name__
    ok = getattr(obj, "ok")
    if not isinstance(ok, bool):
        raise TypeError(f"{cls_name}.ok must be a bool, got {ok!r}")

    fail_reason = getattr(obj, "fail_reason")

    if ok:
        if fail_reason is not None:
            raise ValueError(
                f"{cls_name}: ok=True must not carry a fail_reason "
                f"(got {fail_reason!r}) — a partial success is a failure"
            )
        for name in numeric_fields:
            value = getattr(obj, name)
            if value is None:
                raise ValueError(
                    f"{cls_name}: ok=True but {name} is None. Every numeric "
                    f"field must be populated on success (§8 rule 1)."
                )
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise TypeError(f"{cls_name}.{name} must be a real number, got {value!r}")
            if not math.isfinite(float(value)):
                raise ValueError(
                    f"{cls_name}.{name} is {value} — nan/inf must be reported as "
                    f"ok=False, never passed downstream"
                )
            setattr(obj, name, float(value))
    else:
        if not fail_reason or not str(fail_reason).strip():
            raise ValueError(
                f"{cls_name}: ok=False requires a specific fail_reason so the "
                f"experiment log says *why* (§8 rule 8)"
            )
        for name in numeric_fields:
            if getattr(obj, name) is not None:
                raise ValueError(
                    f"{cls_name}: ok=False but {name} is populated. A failed "
                    f"evaluation has no numbers — see §8 rule 1."
                )
