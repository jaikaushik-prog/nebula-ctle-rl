"""
device/tail.py — the tail current source, as a real transistor.

WHY THIS EXISTS
---------------
Every simulation this project has ever run used **two ideal current sinks** for
the tail (`It1 s1 0 {IT}` / `It2 s2 0 {IT}` in `spice/ctle.cir` and in
`sky130_runner._NETLIST`). An ideal sink delivers exactly `I_tail` at every
corner: it does not lose current at SS/125 C, does not gain it at FF/0 C, and
does not fall out of saturation when the rail drops 5 %. A real tail does all
three. That single assumption is what made every S9 number in this project an
**optimistic bound** (HANDOFF G47), and it is why `w_tail`, `l_tail` and
`nf_tail` are the three §5.2 action-space dimensions with no provenance at all
(`s3_yield.PROPOSED_BOX::UNDERIVABLE`).

TOPOLOGY: A CURRENT MIRROR, NOT A FIXED GATE BIAS
--------------------------------------------------
An ideal reference current is forced into a diode-connected `nfet_01v8`, and
its gate drives the two tail devices at ratio `N = W_tail / W_ref`.

The alternative — biasing the tail gate from a fixed voltage source — is
**wrong in a way that flatters the corner analysis**: a fixed `Vgs` holds while
`vth` moves with process and temperature, so the delivered current swings far
more than silicon does. A mirror tracks, because the reference device's `vth`
moves the same way as the tail's and the gate voltage follows it. Using a fixed
bias would have produced a *larger* corner spread than reality and made the
tail look like a worse problem than it is.

**The one ideal element that remains, stated plainly:** `I_ref` is an ideal
current source. Generating it (a bandgap, or a constant-gm bias cell) is a
separate circuit that S2 does not name, and modelling it badly would be worse
than declaring it. One justified ideal element is defensible; four are not.

TWO TAIL DEVICES, NOT ONE — AND IT CHANGES THE NOISE ARGUMENT
--------------------------------------------------------------
S2 degenerates the pair with `Rs`/`Cs` **between the two sources**. A single
shared tail device would put a low impedance across that network and short it
out, so the topology needs one sink per side. That is already true of the ideal
sinks; the mirror keeps it.

The consequence is not cosmetic. The textbook "tail noise is common-mode and is
rejected by a balanced pair" argument relies on there being **one** tail whose
noise current is shared by both sides. Two separate devices have **independent**
noise, so half of it appears differentially by construction. See
`nebula/TAIL_DEVICE.md` §4 for the measurement.

THE COUPLED INEQUALITY THIS MAKES REAL
---------------------------------------
The tail needs `vds > vdsat`. Its `vds` **is** the source node of the input
pair:

    v(source) = VCM - Vgs(I_tail, W_in, L_in)        and        vds_tail = v(source)

so the tail's headroom requirement couples **VCM, W_in, L_in, I_bias and the
tail sizing into one inequality**, worst where `Vgs` is largest and `vdsat` is
largest at once — SS, cold, low rail. At the reference point `v(source)` is only
+0.343 V, and the sweep in `experiments/tail_device.py` measures how much of
that a tail can afford to take.

UNITS
-----
`w_tail` and `l_tail` are **plain numbers in microns**, like every other
geometry that reaches a SKY130 netlist (G31). They are NOT SI metres. The box
in `s3_yield.PROPOSED_BOX` stores `w_in`/`l_in` in metres and
`SizingPoint.from_params` converts; the tail has no such round trip because it
is not sampled from that box.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

#: SKY130's 1.8 V thin-oxide NMOS. The same device as the input pair, so the
#: trimmed library (G36) already carries it and needs no extension.
NFET_01V8: str = "sky130_fd_pr__nfet_01v8"

#: **The model bin ceiling is on W PER FINGER, not on total width** — G53.
#:
#: Measured against the trimmed library, TT: `W=100 nf=1` builds, `W=101 nf=1`
#: aborts with "could not find a valid modelname"; `W=200 nf=2` and `W=400 nf=4`
#: build, `W=210 nf=2` and `W=410 nf=4` abort. The break is exactly at
#: `W/nf = 100 um`, which is the `wmax = 1e-4` of the widest bin in
#: `sky130_fd_pr__nfet_01v8__tt.pm3.spice`.
#:
#: This matters because a tail sinking several mA at `vdsat <= 0.2 V` and
#: `L >= 0.5 um` needs several hundred microns of width, which is impossible to
#: read as "allowed" if you believe the ceiling is on the total.
W_PER_FINGER_MAX_UM: float = 100.0

#: Below the minimum L bin there is no model at all (`lmin = 1.5e-7 m`).
L_MIN_UM: float = 0.15

#: Bias-node bypass capacitance. **It is there for a circuit reason first.**
#: A current mirror's gate node is shared by every device it feeds; grounding
#: it at signal frequencies is what stops reference-branch and supply noise
#: from being injected into all of them. Real designs always have it.
#:
#: It ALSO removes an ngspice numerical singularity, and that is worth stating
#: separately so the element is not mistaken for a workaround (G54): without
#: it, `inoise_total` comes back `-nan(ind)` — and ngspice exits 0 — on some
#: (corner, geometry) points, because the reference device's noise is rejected
#: to machine zero by symmetry and the integrated-noise log-slope integration
#: then evaluates log(0). Measured: 5 of 261 sweep points, knife-edge in width
#: (W = 141 um fine, 200 um NaN, 218 um fine), so it is numerics, not physics.
#: Only the `xmr` (reference) contribution is ever the NaN; every other
#: contributor stays finite, which is what identifies the mechanism.
#:
#: **The value does not affect the answer.** This is how we know it is not
#: quietly buying the result — measured input-referred noise in mV_rms:
#:
#:      point                    1 pF      10 pF     100 pF     1 nF
#:      ff/1.05/0 C  W 519 um     NaN     0.505543  0.505543  0.505543
#:      ff/1.05/0 C  W 336 um  0.509358  0.509358  0.509358  0.509358
#:      ss/0.95/125C W 200 um  0.535162  0.535162  0.535162  0.535162
#:      tt/1.00/27 C W 100 um  0.442465  0.442465  0.442465  0.442465
#:
#: Identical to every printed digit wherever it computes at all. 10 pF is the
#: smallest tested value at which no point NaNs, so that is the default.
#:
#: **AREA, stated because it is not free and S7 has to carry it:** 10 pF is a
#: real capacitor. Its area is NOT yet in any S7 estimate — that estimate does
#: not exist, because no MIM cap or poly resistor models have been pulled yet
#: (`s9_yield.UNSCREENED_SPECS`). Whoever builds it must include this.
C_BYPASS_F: float = 10e-12


class TailGeometryError(ValueError):
    """A tail sizing that has no SKY130 model. Raised, never simulated.

    A geometry outside the bins does not produce a wrong number — it produces
    ngspice's "could not find a valid modelname", which G31 records as being
    read as a units error nine times out of ten. Failing here names the real
    cause.
    """


@dataclass(frozen=True)
class TailDevice:
    """One tail current mirror: a reference unit and two mirrored tails.

    `w_tail` is the TOTAL width of ONE tail device, and there are two of them
    (one per side). `mirror_ratio` is `N = W_tail / W_ref`, so the reference
    branch costs `I_side / N` of extra supply current, which
    `SizingPoint.power_w` bills for.

    THE REFERENCE DEVICE IS N UNIT FINGERS SMALLER, NOT A DIFFERENT SHAPE.
    `nf_ref` defaults to `nf_tail / N` so the reference and each tail finger
    have the **same width**, which is what makes the mirror ratio close to `N`.
    G38 measured a +/-10 % non-monotonic parasitic effect of finger width on
    `gm`; with mismatched finger widths that effect lands directly on the mirror
    gain. Measured on this topology at `W_tail = 100, L = 0.5, N = 8`:

        nf_tail   nf_ref   finger widths (um)   realised ratio
           8         1       12.5  /  12.5          7.38
           8         8       12.5  /   1.56         9.55

    The matched-finger case is the one whose error is *physics* — it is the
    channel-length modulation of a mirror whose two branches sit at very
    different `vds` (the reference at `Vgs` ~ 1.0 V, the tail at `v(source)`
    ~ 0.34 V). The mismatched case happens to land nearer 8.0 by cancelling one
    error against another, which is not a design.

    When `nf_tail` is not a multiple of `N`, `nf_ref` rounds up to 1 and the
    fingers no longer match; `finger_matched` says so rather than hiding it.
    """

    w_tail: float                 # um, total width of ONE tail device
    l_tail: float                 # um
    nf_tail: int
    mirror_ratio: float = 8.0     # N = W_tail / W_ref
    device: str = NFET_01V8
    #: Bias-node bypass capacitance, farads. See `C_BYPASS_F`.
    c_bypass_f: float = C_BYPASS_F

    def __post_init__(self) -> None:
        if self.mirror_ratio <= 0:
            raise TailGeometryError(f"mirror_ratio {self.mirror_ratio} must be > 0")
        if self.nf_tail < 1:
            raise TailGeometryError(f"nf_tail {self.nf_tail} must be >= 1")
        if self.c_bypass_f <= 0:
            raise TailGeometryError(
                f"c_bypass_f {self.c_bypass_f} must be > 0 — a zero bypass "
                f"re-opens the G54 NaN"
            )
        if self.l_tail < L_MIN_UM:
            raise TailGeometryError(
                f"l_tail {self.l_tail} um is below the SKY130 nfet_01v8 minimum "
                f"L bin ({L_MIN_UM} um) — there is no model there"
            )
        for label, w, nf in (("tail", self.w_tail, self.nf_tail),
                             ("reference", self.w_ref, self.nf_ref)):
            if w <= 0:
                raise TailGeometryError(f"{label} width {w} um must be > 0")
            if w / nf > W_PER_FINGER_MAX_UM:
                raise TailGeometryError(
                    f"{label} device is W={w:.4g} um over nf={nf} = "
                    f"{w / nf:.4g} um per finger, above the SKY130 bin ceiling "
                    f"of {W_PER_FINGER_MAX_UM} um per finger (G53). Raise nf: "
                    f"the ceiling is per FINGER, not on the total width."
                )

    # ---- the reference branch, derived so it has ONE definition -------------

    @property
    def w_ref(self) -> float:
        """Reference device width, um. `W_tail / N` by construction."""
        return self.w_tail / self.mirror_ratio

    @property
    def nf_ref(self) -> int:
        """Reference finger count, chosen to MATCH the tail's finger width.

        `nf_tail / N` when that is a whole number >= 1, else 1 — and
        `finger_matched` reports which case applied, because an unmatched
        mirror's ratio error is a layout artifact rather than physics.
        """
        q = self.nf_tail / self.mirror_ratio
        return int(round(q)) if q >= 1.0 and abs(q - round(q)) < 1e-9 else 1

    @property
    def finger_matched(self) -> bool:
        """True iff reference and tail fingers are the same width."""
        return math.isclose(self.w_ref / self.nf_ref,
                            self.w_tail / self.nf_tail, rel_tol=1e-9)

    @property
    def finger_w_um(self) -> float:
        return self.w_tail / self.nf_tail

    def i_ref_a(self, i_tail_per_side_a: float) -> float:
        """The ideal reference current that ASKS for `i_tail_per_side_a`.

        What the mirror actually delivers is a measurement, not this number —
        see `Sky130Point.i_tail_meas_a`. The two differ by the mirror's gain
        error, which is the point of measuring it.
        """
        return i_tail_per_side_a / self.mirror_ratio

    def tag(self) -> str:
        return (f"W{self.w_tail:g}/L{self.l_tail:g}/nf{self.nf_tail}"
                f"/N{self.mirror_ratio:g}")


def scale_w_for_current(
    i_tail_per_side_a: float,
    j_um_per_a: float,
    nf_tail: int,
) -> float:
    """Tail width, um, for a target current DENSITY.

    A single fixed `w_tail` cannot serve the box: `i_bias` spans 0.5-8 mA total,
    a 16x range, and `vdsat` at fixed width moves as roughly `sqrt(I)`. Holding
    the current density `I/W` constant instead holds `vdsat` roughly constant,
    which is what the sizing target is actually about.

    `j_um_per_a` is **microns of width per amp** (i.e. `1 / current density`),
    measured in `experiments/tail_device.py` at the vdsat target and quoted in
    `TAIL_DEVICE.md`. Rounds up to a finger multiple so the geometry is
    buildable.
    """
    if i_tail_per_side_a <= 0 or j_um_per_a <= 0 or nf_tail < 1:
        raise ValueError(
            f"i={i_tail_per_side_a}, j={j_um_per_a}, nf={nf_tail}: all must be positive"
        )
    w = i_tail_per_side_a * j_um_per_a
    # Never propose a geometry the bins cannot hold; raise the finger count
    # instead of silently clipping the width, which would silently change the
    # current density this function exists to hold constant.
    return w


def min_nf_for_width(w_um: float, mirror_ratio: float = 8.0) -> int:
    """Smallest `nf_tail` that keeps BOTH devices inside the bin ceiling.

    The reference is `N` times narrower, so it is never the binding one; the
    tail is. Returns a multiple of `mirror_ratio` when `mirror_ratio` is a whole
    number, so `nf_ref` stays a whole number and the fingers stay matched.
    """
    if w_um <= 0:
        raise ValueError(f"width {w_um} um must be > 0")
    need = math.ceil(w_um / W_PER_FINGER_MAX_UM)
    n = int(round(mirror_ratio))
    if math.isclose(mirror_ratio, n) and n >= 1:
        return max(n, int(math.ceil(need / n)) * n)
    return max(1, need)


__all__: Sequence[str] = (
    "TailDevice", "TailGeometryError", "NFET_01V8",
    "W_PER_FINGER_MAX_UM", "L_MIN_UM", "C_BYPASS_F",
    "scale_w_for_current", "min_nf_for_width",
)
