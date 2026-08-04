"""
common/design_equations.py — the small-signal model of the S2 topology.

Transcribed verbatim from CLAUDEwa.md §6. Source-degenerated differential pair:

    w_z   = 1 / (Rs * Cs)
    w_p1  = (1 + gm*Rs/2) / (Rs * Cs)
    w_p2  = 1 / (RL * CL)
    A_dc  = gm*RL / (1 + gm*Rs/2)
    peaking_dB ~= 20*log10(1 + gm*Rs/2)

These are used in three places and it matters that all three use the SAME
code:

1. **Initialisation** — putting the policy's starting point somewhere sane.
2. **Sanity-checking the extraction** — §6 makes this a hard requirement:
   "at least one full extraction must be checked by hand against these. If
   A_dc from the wrapper disagrees with gm*RL/(1+gm*Rs/2), something upstream
   is broken and every downstream number is fiction. Do not proceed past that
   discrepancy." `cross_check_extraction()` below is that check, automated.
3. **The mock device layer**, so that the mock is physically coherent rather
   than random — which is what makes it useful for developing the RL loop.

Note the /2 in the degeneration term: Rs here is the FULL resistance between
the two sources of the differential pair, so each half-circuit sees Rs/2.
If you write the equations with a per-side Rs the factor disappears and every
gain and peaking number is off. This convention is fixed here and nowhere else.

THE BODY-EFFECT CORRECTION (measured 2026-08-03, G1)
----------------------------------------------------
§6 as written assumes the bulk is tied to the source. In a bulk CMOS process
it is not — every NMOS sits in the grounded p-substrate, so the source node
moves while the body stays at 0 V and the body transconductance `gmbs`
degenerates alongside `gm`:

    i_d = gm*(v_g - v_s) + gmbs*(0 - v_s)   =>   k = 1 + (gm + gmbs)*Rs/2

This is not a rounding correction. Measured on the G1 hand-design point
(ngspice, generic BSIM4 130nm, gm = 10.97 mS, Rs = 800, RL = 120):

    simulated A_dc                  -14.57 dB
    §6 as written (gmbs = 0)        -12.24 dB   -> off by 2.33 dB, GATE FAILS
    §6 with gmbs = 3.58 mS          -14.29 dB   -> off by 0.28 dB, gate passes

gmbs/gm was 0.33 at that operating point. Ignoring it makes every predicted
gain ~2.3 dB optimistic, which is more than the §6 gate's own 1 dB tolerance —
so the equation as written fails its own acceptance test on a correct circuit.

`predict()` therefore takes `gmbs` and defaults it to 0.0, which reproduces §6
verbatim for anyone checking the transcription. Pass the simulated `gmbs` for
anything that has to agree with SPICE.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

TWO_PI = 2.0 * math.pi


@dataclass(frozen=True)
class SmallSignal:
    """Analytic pole/zero/gain prediction for one set of small-signal values."""

    g_dc: float          # linear V/V
    f_zero_hz: float
    f_pole1_hz: float
    f_pole2_hz: float
    peaking_db: float    # asymptotic, 20*log10(1 + gm*Rs/2)

    @property
    def degeneration_factor(self) -> float:
        """1 + gm*Rs/2, recovered from the pole-zero ratio."""
        return self.f_pole1_hz / self.f_zero_hz


def predict(gm: float, rs: float, cs: float, rl: float, cl: float,
            gmbs: float = 0.0) -> SmallSignal:
    """Apply §6 to one operating point.

    Parameters
    ----------
    gm    transconductance of ONE input device, siemens
    rs    full source-degeneration resistance between the two sources, ohms
    cs    source-degeneration capacitance, farads
    rl    single-ended load resistance, ohms
    cl    single-ended load capacitance, farads
    gmbs  body transconductance of one input device, siemens. Defaults to 0,
          which reproduces §6 exactly as written. Pass the simulated value
          for anything that must agree with SPICE — see the module docstring;
          omitting it cost 2.33 dB on the G1 point, more than the §6 gate's
          own tolerance.
    """
    for name, v in (("gm", gm), ("rs", rs), ("cs", cs), ("rl", rl), ("cl", cl)):
        if not math.isfinite(v) or v <= 0.0:
            raise ValueError(f"{name} must be positive and finite, got {v!r}")
    if not math.isfinite(gmbs) or gmbs < 0.0:
        raise ValueError(f"gmbs must be non-negative and finite, got {gmbs!r}")

    k = 1.0 + (gm + gmbs) * rs / 2.0             # degeneration factor
    w_z = 1.0 / (rs * cs)
    w_p1 = k / (rs * cs)
    w_p2 = 1.0 / (rl * cl)
    a_dc = gm * rl / k

    return SmallSignal(
        g_dc=a_dc,
        f_zero_hz=w_z / TWO_PI,
        f_pole1_hz=w_p1 / TWO_PI,
        f_pole2_hz=w_p2 / TWO_PI,
        peaking_db=20.0 * math.log10(k),
    )


def gain_linear(f_hz: float, ss: SmallSignal) -> float:
    """|H(j2*pi*f)| as a linear V/V ratio.

    This — not `g_dc` — is the gain that sets the eye amplitude. The entire
    point of a CTLE is that its gain at Nyquist is 3-12 dB above its gain at
    DC (S3), so sizing a signal amplitude off `g_dc` understates the output
    by exactly the peaking the circuit was built to provide.
    """
    x_z = f_hz / ss.f_zero_hz
    x_1 = f_hz / ss.f_pole1_hz
    x_2 = f_hz / ss.f_pole2_hz
    return (
        ss.g_dc
        * math.sqrt(1.0 + x_z * x_z)
        / (math.sqrt(1.0 + x_1 * x_1) * math.sqrt(1.0 + x_2 * x_2))
    )


def transfer_db(f_hz: float, ss: SmallSignal) -> float:
    """|H(j2*pi*f)| in dB for the 1-zero/2-pole response.

    Same functional form as `python_models/rx_frontend.py::CTLE.freq_response`,
    which is what the link layer will instantiate from a DeviceResult. Keeping
    the two consistent is what makes the pole-zero bridge meaningful.
    """
    return 20.0 * math.log10(gain_linear(f_hz, ss))


def realised_peaking_db(ss: SmallSignal, n_points: int = 4000) -> tuple[float, float]:
    """Numerically realised (peaking_dB, f_peak_hz) — NOT the asymptote.

    `SmallSignal.peaking_db` is 20*log10(1 + gm*Rs/2), which is only reached
    when f_p2 >> f_p1. At 5 Gbps in 130 nm the second pole sits close to the
    band of interest and erodes the boost, exactly as
    `rx_frontend.CTLE.from_peaking` documents. S3 is written against the
    *realised* peaking, so this is the number that must be compared to spec.
    """
    lo = math.log10(min(ss.f_zero_hz, ss.f_pole1_hz) / 100.0)
    hi = math.log10(max(ss.f_pole1_hz, ss.f_pole2_hz) * 100.0)
    step = (hi - lo) / (n_points - 1)

    dc_db = 20.0 * math.log10(ss.g_dc)
    best_db = -math.inf
    best_f = float("nan")
    for i in range(n_points):
        f = 10.0 ** (lo + i * step)
        db = transfer_db(f, ss)
        if db > best_db:
            best_db, best_f = db, f
    return best_db - dc_db, best_f


def cross_check_extraction(
    extracted_g_dc: float,
    gm: float,
    rs: float,
    rl: float,
    tol_db: float = 1.0,
    gmbs: float = 0.0,
) -> tuple[bool, float]:
    """The §6 hard gate: does the wrapper's A_dc match the design equation?

    Returns (agrees, disagreement_db). A disagreement above `tol_db` means
    something upstream is broken — the operating point, the netlist, the AC
    probe, or the Rs convention — and every downstream number is fiction.
    Callers must stop, not clamp.

    `tol_db` defaults to 1 dB because the analytic form still neglects r_o and
    the second pole's DC contribution; a real extraction landing within 1 dB
    is agreement, and landing 6 dB away is a bug.

    **Pass `gmbs`.** With `gmbs=0` this is §6 verbatim, and §6 verbatim fails
    this very check by 2.33 dB on a correct circuit (module docstring). The
    body effect is not one of the small terms the tolerance is there to
    absorb — at the G1 operating point gmbs was a third of gm.
    """
    if extracted_g_dc <= 0.0:
        return False, math.inf
    predicted = gm * rl / (1.0 + (gm + gmbs) * rs / 2.0)
    if predicted <= 0.0:
        return False, math.inf
    delta_db = abs(20.0 * math.log10(extracted_g_dc / predicted))
    return delta_db <= tol_db, delta_db
