"""
rl/contract.py — THE ENVIRONMENT CONTRACT. Written before the implementation.

Everything the policy sees, everything it may move, and every unit and scale
involved, in ONE place (CLAUDEwa.md §8 rule 9). Two definitions of one quantity
is the failure mode this repo keeps hitting; an observation vector assembled in
the env and re-assembled in an analysis script is exactly that shape of bug,
so the assembly lives here and both callers import it.

═══════════════════════════════════════════════════════════════════════════
1. ACTION — what the policy may move
═══════════════════════════════════════════════════════════════════════════

**Seven continuous dimensions**, each a DELTA in normalised space, clipped to
`MAX_STEP`. The policy never proposes an absolute sizing; it proposes an edit
to the current one, and sees the result before the next edit. That is what
makes the episode a design session rather than seven independent bandit pulls.

Normalised space is `[0, 1]` per dimension, LOG-scaled where the box spans
decades and LINEAR where it does not — the `log` column below. A delta of
0.10 therefore means "one tenth of the box, in the box's own metric": on a log
axis that is a fixed RATIO, which is the right invariance for a resistance or
a current, and on a linear axis a fixed increment, which is right for a width.

    name          lo        hi       log   unit    what it does
    ------------------------------------------------------------------------
    w_in         20        100      no     um*     gm, and hence peaking
    l_in          0.15       1.0    yes    um*     gm and f_T
    i_bias        0.5e-3     8.0e-3 yes    A       gm, power, swing
    rs           50       1000      yes    ohm     peaking (k), f_zero
    cs          100e-15    10e-12   yes    F       f_zero
    rl           50        800      yes    ohm     g_dc, f_p2
    vcm_in        1.1        1.6    no     V       source node, tail headroom

    (*) `w_in`/`l_in` are stored in SI METRES in the box, like everywhere else
        in this repo; `SizingPoint.from_params` does the single conversion to
        the microns the netlist wants (G31). The table shows microns because
        that is the number a human recognises.

**`nf_in` IS FIXED AT 4 AND IS NOT AN ACTION.** This is a deliberate choice
with a measurement behind it, not an oversight. G38: on SKY130 `W` is the
TOTAL device width and `nf` only splits it into fingers. Measured at W = 40 um,
1.5 mA/side, `nf` = 1, 2, 4, 8, 16, 32 gives gm = 14.22, 13.68, 12.62, 13.12,
12.29, 11.79 mS — a **+/-10 % NON-MONOTONIC** parasitic effect. A policy
gradient on a non-monotonic +/-10 % axis learns the noise, not the axis, and
it costs samples to do it. 4 is inside `PROPOSED_BOX`'s 1-8 range and is the
value the existing reference points use.

**THE WHOLE TAIL IS DERIVED, NOT SEARCHED — and this is a REVERSAL.** The
first version of this contract followed task 6c and made `tail_j` (tail width
per amp of side current) and `l_tail` actions, on the grounds that
`TAIL_DEVICE.md` §6's recommendation against searching them had no measurement
behind it in an RL setting. The §6e gate supplied that measurement, and it
argues the other way:

    dim       channel          |d_obs| under one MAX_STEP
    vcm_in    tail_margin_v    0.6050
    tail_j    tail_margin_v    0.1008
    l_tail    tail_margin_v    0.0982

**`vcm_in` is a 6x stronger lever on the tail margin than either tail axis is**,
on the quantity the tail geometry exists to control. That is the `nf_in`
argument again (G38): a policy gradient on a weak, REDUNDANT dimension learns
noise, and spends samples doing it. The tail axes are live — the gate proved
that — but they are redundant with a dimension that has to be in the space
anyway. Human decision, 2026-08-07: **remove them.**

What replaces them is the practice the rest of this project already uses: fix
the current, fix a target `vdsat_tail`, size the device from those, then
VERIFY. `w_tail = i_side * TAIL_UM_PER_AMP` at `l_tail = TAIL_L_UM`, imported
from `experiments/s9_yield.py` so there is exactly ONE definition (rule 9).
`TAIL_UM_PER_AMP` = 111.2k um/A is the **`ss/0.95/125 C`** width for
`vdsat_tail` = 0.20 V — deliberately the corner where the tail needs the most
width for a given `vdsat` (111.2k against 58.3k at TT and 43.7k at FF, a 2.5x
spread), so sizing there keeps the tail saturated at every corner rather than
only at nominal.

**Removing the degrees of freedom does NOT remove the constraint.**
`tail_saturation` remains an active, scored constraint, and it is still the
only row in the spec table coupling five box coordinates — `vds_tail` IS the
input pair's source node, so VCM, `w_in`, `l_in`, `i_bias` and the tail sizing
all meet in it. What is gone is the redundant freedom to move the tail
INDEPENDENTLY of the current it has to sink, which `TAIL_DEVICE.md` §6 records
as producing "tails that are the wrong size for their own current".

**`nf_tail` IS NOT AN ACTION EITHER, and never was.** It is derived as the
smallest multiple of the mirror ratio keeping `W/nf <= 100 um` (G53). Writing
it independently produces geometries with no SKY130 model bin, whose error
message is G31's misleading "could not find a valid modelname".

So the action space is **seven dimensions**: the input pair (`w_in`, `l_in`),
the bias (`i_bias`, `vcm_in`), and the three passives that place the poles and
the zero (`rs`, `cs`, `rl`). At ~142 episodes per 500 steps, dropping two of
nine axes is worth a great deal.

═══════════════════════════════════════════════════════════════════════════
2. CONTEXT — what the policy is TOLD but may not move
═══════════════════════════════════════════════════════════════════════════

* **`cl`** — the load. Settled in task 2 and re-measured in `CL_RANGE.md`:
  nobody chooses the following stage's input capacitance, and G42 measured
  that SEARCHING it lowers the yield. Fixed at `cl_mid` = 32.63 fF for this
  run. An agent that could choose its own load could buy S3 by declaring a
  load nobody will build.
* **the corner set** — TT/1.00/27 C only for this smoke run.
* **the target spec** — one fixed point inside S3.

═══════════════════════════════════════════════════════════════════════════
3. OBSERVATION — 18 dimensions, all normalised by FIXED scales
═══════════════════════════════════════════════════════════════════════════

    idx    block                    dims
    0-6    current sizing           7    normalised box coordinate, [0,1]
    7-14   last measurement         8    see the scale table below
    15-16  target spec              2    peaking target, f_peak target
    17     step index               1    step / horizon, [0,1]

The measurement block still carries `tail_margin_v` even though the tail is no
longer an action. That is deliberate: the tail's headroom is a CONSEQUENCE of
`vcm_in`, `w_in`, `l_in` and `i_bias`, all of which the policy does move, so it
is exactly the kind of coupled feedback the observation exists to provide.

**Scales are FIXED and derived from the box and the spec, never from running
statistics.** A running normaliser makes the observation depend on the history
of the run, so the same circuit produces different numbers in two runs and
nothing reproduces. The scales are the `OBS_SCALES` table below and every one
carries its basis.

    quantity        unit      centre    scale     basis
    ---------------------------------------------------------------------
    g_dc_db         dB          0.0     20.0      measured box spread
    peaking_db      dB          7.5      9.0      S3's 3-12 band, centre and
                                                  twice its half-width
    f_peak          octaves     0.0      2.0      log2(f/2.5 GHz); S3's window
                                                  is exactly 1 octave wide
    nyq_boost_db    dB          0.0     12.0      S3's ceiling
    inoise          V rms       0.0      1.5e-3   S5's limit
    power           W           0.0     15e-3     S6's limit
    pair_margin     V           0.0      0.3      vds-vdsat; ~0.28 V at the
                                                  reference point
    tail_margin     V           0.0      0.1      vds_tail-vdsat_tail; the
                                                  100 mV of §6h's reward

**`inoise` is RMS VOLTS and is NOT square-rooted.** `tests/test_noise_units.py`
exists because that was got wrong once.

**`f_peak` enters the observation in OCTAVES, never in hertz.** Every other
result in this project is in octaves, S3's window is exactly one octave, and a
linear-hertz observation makes a 17 GHz miss and a 40 mV miss incomparable —
which is the whole argument of `TAIL_DEVICE.md` §7.

**On the FIRST step of an episode there is no last measurement.** The sizing is
evaluated once at reset, so the measurement block is always real. There is no
"missing" encoding and no zero-fill: a zero-filled measurement block is a
plausible-looking observation for a circuit that does not exist, which is
failure mode #1.

═══════════════════════════════════════════════════════════════════════════
4. EPISODE
═══════════════════════════════════════════════════════════════════════════

**Horizon: 8 edits.** Why 8 and not 3 or 50:

* `MAX_STEP` is 0.15 of the box per dimension per step, so 8 steps can move
  1.2 box-widths — enough to cross the box from any start. A horizon that
  cannot reach the far side makes the START the binding variable rather than
  the policy, and the run would measure initialisation.
* At the measured ~1.9 s per evaluation with real passives, 8 steps is ~15 s
  of SPICE per episode. 500 PPO steps is then ~62 episodes, which is enough
  for the plumbing to be exercised in every state it can reach and far too few
  for anything to be learned. That asymmetry is deliberate: §6 says the goal
  is integration bugs, not a policy.
* Credit assignment over 8 steps is trivial, so a flat return curve cannot be
  blamed on the horizon.

**Terminates early on success** (all specs met) and **on an invalid
evaluation** (§6d). Nothing else terminates it.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

import numpy as np

from nebula.common.types import (
    NYQUIST_HZ,
    SPEC_F_PEAK_HZ_RANGE,
    SPEC_PEAKING_DB_RANGE,
    SPEC_POWER_MAX_W,
    SPEC_VN_IN_MAX_VRMS,
)

# ─────────────────────────────────────────────────────────────────────────────
# The action space.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ActionDim:
    """One searchable coordinate: its box, its metric, and its provenance."""

    name: str
    lo: float
    hi: float
    log: bool
    unit: str
    provenance: str

    def __post_init__(self) -> None:
        if not (self.lo < self.hi):
            raise ValueError(f"{self.name}: need lo < hi, got {self.lo}, {self.hi}")
        if self.log and self.lo <= 0.0:
            raise ValueError(f"{self.name}: log metric needs lo > 0, got {self.lo}")
        if not self.provenance.strip():
            raise ValueError(f"{self.name}: every bound needs a provenance")

    def to_physical(self, u: float) -> float:
        """`u` in [0,1] -> the physical value, in `unit`."""
        u = min(max(float(u), 0.0), 1.0)
        if self.log:
            return float(math.exp(math.log(self.lo)
                                  + u * (math.log(self.hi) - math.log(self.lo))))
        return float(self.lo + u * (self.hi - self.lo))

    def to_normalised(self, v: float) -> float:
        """Inverse of `to_physical`, clipped into [0,1]."""
        v = float(v)
        if self.log:
            if v <= 0.0:
                raise ValueError(f"{self.name}={v} is not positive but the metric is log")
            u = (math.log(v) - math.log(self.lo)) / (math.log(self.hi) - math.log(self.lo))
        else:
            u = (v - self.lo) / (self.hi - self.lo)
        return float(min(max(u, 0.0), 1.0))


#: The box. **This is NOT `common/params.py::BOUNDS` and does not write to it**
#: — CLAUDEwa.md §8 rule 6 makes the box a human decision and rule 6 is why
#: `params.py` is untouched by this session. **All seven edges are
#: `s3_yield.PROPOSED_BOX` verbatim** (session 9d, measured against SKY130
#: nfet_01v8 at 1.8 V). Nothing here was chosen by an agent; every number is
#: copied from a document that measured it. The two tail edges that used to sit
#: here are gone — the tail is derived, see the module docstring.
ACTION_SPACE: tuple[ActionDim, ...] = (
    ActionDim("w_in", 20e-6, 100e-6, False, "m",
              "s3_yield.PROPOSED_BOX: gm/I_D 5.62 at W=20 um rising to 14.36 "
              "at W=100 um; ceiling is the SKY130 W bin limit"),
    ActionDim("l_in", 0.15e-6, 1.0e-6, True, "m",
              "s3_yield.PROPOSED_BOX: 0.15 um is the minimum L bin; at 1.0 um "
              "peaking is 2.37 dB, already below S3"),
    ActionDim("i_bias", 0.5e-3, 8.0e-3, True, "A",
              "s3_yield.PROPOSED_BOX: TOTAL supply current; ceiling is S6 at "
              "1.8 V (8 mA x 1.8 V = 14.4 mW)"),
    ActionDim("rs", 50.0, 1000.0, True, "ohm",
              "s3_yield.PROPOSED_BOX: FULL source-to-source; Rs=50 gives "
              "0.08 dB peaking, Rs=800 gives 13.25 dB, through S3's ceiling"),
    ActionDim("cs", 100e-15, 10e-12, True, "F",
              "s3_yield.PROPOSED_BOX: Cs <= 200 fF produces no peak at all; "
              "6.4 pF puts f_peak at 1.047 GHz, below the S3 window"),
    ActionDim("rl", 50.0, 800.0, True, "ohm",
              "s3_yield.PROPOSED_BOX: per side; RL=50 puts f_peak at 5.75 GHz, "
              "RL=1000 takes the pair out of saturation"),
    ActionDim("vcm_in", 1.1, 1.6, False, "V",
              "s3_yield.PROPOSED_BOX: v(s1) tracks VCM almost 1:1; floor needs "
              "v(s1) >= ~0.2 V for a real tail"),
)

ACTION_NAMES: tuple[str, ...] = tuple(d.name for d in ACTION_SPACE)
N_ACTIONS: int = len(ACTION_SPACE)

#: Largest edit, per dimension, per step, in normalised units. The policy's
#: raw output is `tanh`-squashed and multiplied by this, so it is a hard clip
#: rather than a penalty. 0.15 x 8 steps = 1.2 box-widths of reach — see the
#: horizon argument in the module docstring.
MAX_STEP: float = 0.15

#: Episode length. See the module docstring for why 8.
HORIZON: int = 8

# ── the fixed dimensions, and why each is fixed ─────────────────────────────

#: G38: `nf` splits width into fingers on SKY130, it does not multiply it, and
#: its residual parasitic effect is +/-10 % NON-MONOTONIC. Not an action.
NF_IN_FIXED: int = 4

#: G53 + TAIL_DEVICE.md §5: derived, never chosen. See `nf_tail_for_width`.
TAIL_MIRROR_RATIO: float = 8.0

#: Every result this project has published uses this. One definition (rule 9).
VDD_NOMINAL_V: float = 1.8


# ─────────────────────────────────────────────────────────────────────────────
# Context: fixed, told to the policy, not movable.
# ─────────────────────────────────────────────────────────────────────────────


def _cl_mid_f() -> float:
    """`cl_mid` re-derived from the committed CSV, never restated (rule 9)."""
    from nebula.experiments.cl_range import committed_cl_range

    return committed_cl_range().cl_mid_f


#: The load. Task 2 settled that this is context, not action (G42, CL_RANGE.md).
CL_CONTEXT_F: float = _cl_mid_f()


# ─────────────────────────────────────────────────────────────────────────────
# Observation.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ObsScale:
    """One measurement channel: its unit, its centre, its scale, its basis.

    `normalise(x) = (x - centre) / scale`. Nothing here is fitted; every
    `scale` is a spec limit or a measured box spread, quoted in `basis`.
    """

    name: str
    unit: str
    centre: float
    scale: float
    basis: str


#: The measurement block of the observation, in order. **Fixed scales, derived
#: from the box and the spec table — never running statistics.** A running
#: normaliser makes the observation a function of the run's own history, so the
#: same circuit reads differently in two runs and nothing reproduces.
OBS_SCALES: tuple[ObsScale, ...] = (
    ObsScale("g_dc_db", "dB", 0.0, 20.0,
             "measured box spread: -15.3 dB to +6.0 dB over the 1890-design "
             "population in robust_geometry_data.csv"),
    ObsScale("peaking_db", "dB", sum(SPEC_PEAKING_DB_RANGE) / 2.0, 9.0,
             "S3's 3-12 dB band: centre 7.5 dB, scale is twice the half-width "
             "so +/-1 covers 2x the spec window"),
    ObsScale("f_peak_oct", "octaves", 0.0, 2.0,
             "log2(f_peak / 2.5 GHz). S3's 1.25-2.5 GHz window is EXACTLY one "
             "octave, so +/-1 here covers 4x the window"),
    ObsScale("nyq_boost_db", "dB", 0.0, 12.0,
             "S3's 12 dB ceiling, read as a boost at Nyquist (reading (b))"),
    ObsScale("inoise_vrms", "V rms", 0.0, SPEC_VN_IN_MAX_VRMS,
             "S5's 1.5 mV_rms limit. RMS VOLTS, NOT square-rooted "
             "(tests/test_noise_units.py)"),
    ObsScale("power_w", "W", 0.0, SPEC_POWER_MAX_W,
             "S6's 15 mW limit, billed on the MEASURED supply current"),
    ObsScale("pair_margin_v", "V", 0.0, 0.3,
             "vds - vdsat of the input pair; 0.28 V at the corrected reference "
             "point (session 9c)"),
    ObsScale("tail_margin_v", "V", 0.0, 0.1,
             "vds_tail - vdsat_tail. 100 mV is the same scale sec 6h's reward "
             "uses, so observation and reward speak one unit"),
)

MEAS_NAMES: tuple[str, ...] = tuple(s.name for s in OBS_SCALES)
N_MEAS: int = len(OBS_SCALES)

#: (target peaking, target f_peak in octaves relative to Nyquist).
N_TARGET: int = 2

#: 9 sizing + 8 measurement + 2 target + 1 step index.
N_OBS: int = N_ACTIONS + N_MEAS + N_TARGET + 1

OBS_BLOCKS: tuple[tuple[str, int, int], ...] = (
    ("sizing", 0, N_ACTIONS),
    ("measurement", N_ACTIONS, N_ACTIONS + N_MEAS),
    ("target", N_ACTIONS + N_MEAS, N_ACTIONS + N_MEAS + N_TARGET),
    ("step", N_OBS - 1, N_OBS),
)


def f_peak_octaves(f_hz: float) -> float:
    """`log2(f / f_Nyquist)`. THE conversion; nothing else may write it.

    Octaves relative to 2.5 GHz, because S3's 1.25-2.5 GHz window is exactly
    one octave and every other frequency result in this project is quoted this
    way. A hertz-linear encoding makes a 17 GHz miss and a 40 mV miss
    incomparable, which is the argument of TAIL_DEVICE.md §7.
    """
    if not (f_hz > 0.0) or not math.isfinite(f_hz):
        raise ValueError(f"f_peak must be a positive finite frequency, got {f_hz}")
    return float(math.log2(f_hz / NYQUIST_HZ))


def normalise_measurements(meas: Mapping[str, float]) -> np.ndarray:
    """The 8-channel measurement block, in `OBS_SCALES` order.

    Raises on a missing or non-finite channel. A zero-filled measurement block
    is a plausible-looking observation for a circuit that does not exist, and
    §6d requires an invalid evaluation to terminate the episode rather than
    become a defaulted observation.
    """
    out = np.empty(N_MEAS, dtype=float)
    for i, s in enumerate(OBS_SCALES):
        if s.name not in meas:
            raise KeyError(
                f"measurement block is missing {s.name!r}; a missing channel is "
                f"a failed evaluation, never a zero (CLAUDEwa.md §8 rule 1)"
            )
        v = float(meas[s.name])
        if not math.isfinite(v):
            raise ValueError(f"measurement {s.name} is {v}, not finite")
        out[i] = (v - s.centre) / s.scale
    return out


def build_observation(
    sizing_u: Sequence[float],
    meas: Mapping[str, float],
    target_peaking_db: float,
    target_f_peak_hz: float,
    step: int,
    horizon: int = HORIZON,
) -> np.ndarray:
    """Assemble the full observation. ONE definition (rule 9)."""
    u = np.asarray(sizing_u, dtype=float).ravel()
    if u.shape[0] != N_ACTIONS:
        raise ValueError(f"expected {N_ACTIONS} sizing coordinates, got {u.shape[0]}")
    if not np.all(np.isfinite(u)):
        raise ValueError("sizing coordinates contain nan/inf")

    pk_c, pk_s = OBS_SCALES[1].centre, OBS_SCALES[1].scale
    obs = np.concatenate([
        np.clip(u, 0.0, 1.0),
        normalise_measurements(meas),
        np.array([(float(target_peaking_db) - pk_c) / pk_s,
                  f_peak_octaves(float(target_f_peak_hz)) / OBS_SCALES[2].scale]),
        np.array([float(step) / float(horizon)]),
    ])
    if obs.shape[0] != N_OBS:            # pragma: no cover - structural
        raise AssertionError(f"observation is {obs.shape[0]} wide, contract says {N_OBS}")
    return obs


# ─────────────────────────────────────────────────────────────────────────────
# Normalised sizing -> the physical parameter dict the device layer wants.
# ─────────────────────────────────────────────────────────────────────────────


def nf_tail_for_width(w_um: float, mirror_ratio: float = TAIL_MIRROR_RATIO) -> int:
    """Derived, never chosen (G53). Re-exported so there is one caller path."""
    from nebula.device.tail import min_nf_for_width

    return min_nf_for_width(w_um, mirror_ratio)


def tail_sizing_rule() -> tuple[float, float]:
    """`(um of tail width per amp, l_tail in um)`. ONE definition (rule 9).

    Imported from `experiments/s9_yield.py` rather than restated, because that
    is where the rule's provenance lives and a second copy is G32's failure
    mode applied to a sizing rule. `TAIL_UM_PER_AMP` is the `ss/0.95/125 C`
    width for `vdsat_tail` = 0.20 V — the corner where the tail needs the most
    width for a given `vdsat`, so sizing there keeps it saturated everywhere
    rather than only at nominal.
    """
    from nebula.experiments.s9_yield import TAIL_L_UM, TAIL_UM_PER_AMP

    return float(TAIL_UM_PER_AMP), float(TAIL_L_UM)


@dataclass(frozen=True)
class Sizing:
    """One point of the search, in every representation anyone needs.

    `u` is what the policy moves (SEVEN coordinates) and `params` is what the
    device layer eats. **The tail is DERIVED from `i_bias`**, not carried as
    free state — see the module docstring for why the two tail axes were
    removed from the action space. Both tail properties are computed, so there
    is no way to construct a `Sizing` whose tail disagrees with its current.
    """

    u: tuple[float, ...]
    params: dict            # w_in, l_in, nf_in, i_bias, rs, cs, rl, cl, vcm_in

    @property
    def tail_j_um_per_a(self) -> float:
        return tail_sizing_rule()[0]

    @property
    def l_tail_um(self) -> float:
        return tail_sizing_rule()[1]

    @property
    def w_tail_um(self) -> float:
        """`i_side * TAIL_UM_PER_AMP`. Holding the current DENSITY is what
        holds `vdsat_tail`; `i_bias` spans 16x, so a fixed WIDTH could not
        (TAIL_DEVICE.md §3)."""
        return 0.5 * float(self.params["i_bias"]) * self.tail_j_um_per_a

    @property
    def nf_tail(self) -> int:
        return nf_tail_for_width(self.w_tail_um)


def sizing_from_u(u: Sequence[float], cl_f: float = CL_CONTEXT_F) -> Sizing:
    """Normalised box coordinate -> physical sizing. THE mapping (rule 9)."""
    u = np.clip(np.asarray(u, dtype=float).ravel(), 0.0, 1.0)
    if u.shape[0] != N_ACTIONS:
        raise ValueError(f"expected {N_ACTIONS} coordinates, got {u.shape[0]}")
    phys = {d.name: d.to_physical(ui) for ui, d in zip(u, ACTION_SPACE)}
    params = {
        "w_in": phys["w_in"], "l_in": phys["l_in"],
        "nf_in": float(NF_IN_FIXED),
        "i_bias": phys["i_bias"], "rs": phys["rs"], "cs": phys["cs"],
        "rl": phys["rl"], "cl": float(cl_f), "vcm_in": phys["vcm_in"],
    }
    return Sizing(u=tuple(float(x) for x in u), params=params)


def u_from_params(params: Mapping[str, float]) -> np.ndarray:
    """Inverse of `sizing_from_u`, for seeding from a known design.

    Takes no tail arguments: the tail is derived, so there is nothing to seed.
    A caller that passes one is calling the OLD signature and should be told,
    rather than having the argument silently ignored.
    """
    return np.array([d.to_normalised(params[d.name]) for d in ACTION_SPACE],
                    dtype=float)


# ─────────────────────────────────────────────────────────────────────────────
# design_id — the grouping key task 8's surrogate needs.
# ─────────────────────────────────────────────────────────────────────────────


def design_id(sizing: Sizing, geometry_tag: Optional[str] = None) -> str:
    """A stable 16-hex-digit id for one sizing point.

    **Emitted here rather than reconstructed later**, because task 8's grouped
    train/test split needs to know which rows are the same design, and
    re-deriving that from floats after the fact means choosing a rounding
    tolerance that nobody measured.

    Keyed on the REALISED design where possible: `geometry_tag` carries the
    drawn passive geometry, so two continuous `rs` values that quantise onto
    the same resistor get the SAME id — which is the correct grouping, because
    they are the same silicon and the surrogate must not be tested on a design
    it trained on under a different float.
    """
    parts = [f"{name}={sizing.params[name]!r}"
             for name in sorted(sizing.params)]
    # The tail is derived, but it is still part of the DEVICE, so it stays in
    # the key: if the sizing rule is ever re-measured, ids must not collide
    # across the change.
    parts.append(f"tail_j={sizing.tail_j_um_per_a!r}")
    parts.append(f"l_tail={sizing.l_tail_um!r}")
    if geometry_tag:
        parts.append(f"geom={geometry_tag}")
    key = "|".join(parts).encode("utf-8")
    return hashlib.blake2b(key, digest_size=8).hexdigest()


__all__: Sequence[str] = (
    "ActionDim", "ACTION_SPACE", "ACTION_NAMES", "N_ACTIONS",
    "tail_sizing_rule",
    "MAX_STEP", "HORIZON", "NF_IN_FIXED", "TAIL_MIRROR_RATIO",
    "VDD_NOMINAL_V", "CL_CONTEXT_F",
    "ObsScale", "OBS_SCALES", "MEAS_NAMES", "N_MEAS", "N_TARGET", "N_OBS",
    "OBS_BLOCKS", "f_peak_octaves", "normalise_measurements",
    "build_observation", "Sizing", "sizing_from_u", "u_from_params",
    "nf_tail_for_width", "design_id",
    "SPEC_F_PEAK_HZ_RANGE", "SPEC_PEAKING_DB_RANGE",
)
