"""
device/mock.py — SYNTHETIC stand-in for the ngspice device layer.

======================================================================
  EVERY NUMBER THIS MODULE PRODUCES IS FAKE.
  There is no PDK behind it. No value from here may appear in the
  abstract, the report, the slides, or the results table
  (CLAUDEwa.md §8 rule 1).
======================================================================

What it is for
--------------
Three people are building three layers in parallel against a frozen
interface. The RL layer cannot wait for ngspice + a PDK to exist, and the
link layer cannot wait either. This module lets both proceed today, and it is
what CI runs (CLAUDEwa.md §4.2: "keep a fast synthetic environment behind a
flag ... do not delete it").

Why it is not random
--------------------
A mock that returns noise teaches the RL loop nothing and hides integration
bugs. This one is built on the §6 design equations with a square-law device,
so it is *physically coherent*: increasing Rs raises peaking and lowers gain;
raising I_bias raises gm, lowers input-referred noise and raises power. The
S5-vs-S6 (noise vs power) and corner-spread tensions that CLAUDEwa.md §3 flags
as the real fights are therefore present, and a reward function that games
this mock would game the real thing too.

It is still a lie about magnitudes. Trust the *shape*, never the values.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

import numpy as np

from nebula.common import design_equations as deq
from nebula.common.params import PARAM_NAMES
from nebula.common.types import Corner, DeviceResult, NOISE_BAND_HZ

BOLTZMANN = 1.380649e-23
KELVIN_0C = 273.15

# ── Synthetic "process" constants. NOT a PDK. Loosely 130 nm shaped. ────────
_MOCK_VDD_NOM_V = 1.2
_MOCK_KP_NMOS = 200e-6          # mu*Cox, A/V^2
_MOCK_VTH_NMOS_V = 0.35
_MOCK_LAMBDA = 0.08             # channel-length modulation, 1/V
_MOCK_GAMMA_THERMAL = 2.0 / 3.0 # channel thermal noise factor
_MOCK_VDSAT_TAIL_V = 0.20       # headroom the tail source needs
_MOCK_RES_SHEET_OHM_SQ = 100.0  # poly resistor
_MOCK_RES_AREA_MM2_PER_SQ = 4e-8
_MOCK_CAP_DENSITY_F_PER_MM2 = 2e-9   # MIM
_MOCK_ACTIVE_AREA_MM2 = 2e-4         # fixed overhead for devices + routing

#: Synthetic per-process (mobility, Vth) multipliers.
_PROCESS_SCALE: dict[str, tuple[float, float]] = {
    #        mu_mult, vth_mult      (fast = more mobility, lower Vth)
    "tt": (1.00, 1.00),
    "ss": (0.82, 1.12),
    "ff": (1.18, 0.88),
    "sf": (0.82, 0.88),   # slow NMOS, fast PMOS -> NMOS-side slow, low Vth
    "fs": (1.18, 1.12),
}


@dataclass(frozen=True)
class _Bias:
    """Resolved operating point of the synthetic differential pair."""

    vdd: float
    i_tail: float
    i_branch: float
    gm: float
    vov: float
    temp_k: float


class MockDevice:
    """Synthetic `DeviceEvaluator`. See the module docstring before using.

    Parameters
    ----------
    vin_diff_pp_v
        Differential input amplitude assumed for the HD3 estimate only. HD3 is
        an amplitude-dependent quantity and S4 pins it at a 100 MHz
        differential input; this is the synthetic stand-in for that test
        amplitude. It does NOT affect `vout_swing_v`, which is a compression
        limit and therefore a property of the device alone.
    n_ac_points
        Points in the returned AC sweep (diagnostics only).
    """

    def __init__(self, vin_diff_pp_v: float = 0.2, n_ac_points: int = 201) -> None:
        self.vin_diff_pp_v = float(vin_diff_pp_v)
        self.n_ac_points = int(n_ac_points)

    # ── the interface ───────────────────────────────────────────────────────
    def evaluate(self, params: Mapping[str, float], corner: Corner) -> DeviceResult:
        """(params, corner) -> DeviceResult. Never raises on bad params."""
        try:
            missing = [n for n in PARAM_NAMES if n not in params]
            if missing:
                return DeviceResult.failed(f"params missing keys: {missing}")

            p = {n: float(params[n]) for n in PARAM_NAMES}
            for name, v in p.items():
                if not math.isfinite(v):
                    return DeviceResult.failed(f"param {name} is not finite: {v}")
                if v <= 0.0:
                    return DeviceResult.failed(f"param {name} must be positive, got {v}")

            bias = self._solve_bias(p, corner)
            if isinstance(bias, str):
                return DeviceResult.failed(bias)

            headroom = self._check_headroom(p, bias)
            if headroom is not None:
                return DeviceResult.failed(headroom)

            ss = deq.predict(gm=bias.gm, rs=p["rs"], cs=p["cs"], rl=p["rl"], cl=p["cl"])
            peaking_db, f_peak_hz = deq.realised_peaking_db(ss)

            f = np.logspace(6.0, 11.0, self.n_ac_points)
            mag_db = np.array([deq.transfer_db(float(fi), ss) for fi in f])

            return DeviceResult(
                ok=True,
                fail_reason=None,
                g_dc=ss.g_dc,
                f_zero_hz=ss.f_zero_hz,
                f_pole1_hz=ss.f_pole1_hz,
                f_pole2_hz=ss.f_pole2_hz,
                # Analytic model, so the "fit" is exact by construction. The
                # real wrapper computes this from curve_fit residuals (§5.3b).
                fit_residual_db=0.0,
                peaking_db=peaking_db,
                f_peak_hz=f_peak_hz,
                hd3_dbc=self._hd3_dbc(p, bias),
                vn_in_vrms=self._input_noise_vrms(p, bias, ss),
                power_w=bias.vdd * bias.i_tail,
                area_mm2=self._area_mm2(p),
                vout_swing_v=self._max_linear_swing_v(p, bias),
                ac_freq_hz=f,
                ac_mag_db=mag_db,
            )
        except BaseException as exc:  # noqa: BLE001 — §8 rule 2, no escapes
            return DeviceResult.failed(f"mock device {type(exc).__name__}: {exc}")

    # ── synthetic physics ───────────────────────────────────────────────────
    def _solve_bias(self, p: Mapping[str, float], corner: Corner) -> "_Bias | str":
        mu_mult, _vth_mult = _PROCESS_SCALE[corner.process]
        temp_k = corner.temp_c + KELVIN_0C

        # Mobility falls with temperature (mu ~ T^-1.5), the dominant
        # first-order temperature effect on gm at fixed current.
        mu_temp = (300.0 / temp_k) ** 1.5
        kp = _MOCK_KP_NMOS * mu_mult * mu_temp

        vdd = _MOCK_VDD_NOM_V * corner.vdd_scale
        i_tail = p["i_bias"]
        i_branch = i_tail / 2.0

        wl = (p["w_in"] / p["l_in"]) * p["nf_in"]
        if wl <= 0.0:
            return f"degenerate input pair W/L*nf = {wl}"

        # Square law: I = 0.5*kp*(W/L)*Vov^2, gm = 2I/Vov
        vov = math.sqrt(2.0 * i_branch / (kp * wl))
        gm = 2.0 * i_branch / vov
        # Crude channel-length-modulation boost on gm via r_o loading is
        # folded into the load resistance instead; keep gm clean here.
        return _Bias(vdd=vdd, i_tail=i_tail, i_branch=i_branch, gm=gm,
                     vov=vov, temp_k=temp_k)

    def _check_headroom(self, p: Mapping[str, float], b: _Bias) -> "str | None":
        """Reject operating points that do not fit under VDD.

        This is the mock's stand-in for ngspice non-convergence, and it is the
        main reason the mock is useful: it makes a large slab of the sizing
        space return ok=False, which is exactly what the RL loop must learn to
        avoid and exactly what a naive reward function mishandles.
        """
        v_drop_load = b.i_branch * p["rl"]
        v_out_dc = b.vdd - v_drop_load
        v_gs = b.vov + _MOCK_VTH_NMOS_V
        v_source = p["vcm_in"] - v_gs

        if v_out_dc <= 0.2:
            return (
                f"load drop {v_drop_load:.3f} V leaves V_out_dc={v_out_dc:.3f} V "
                f"under VDD={b.vdd:.3f} V — transistors out of saturation"
            )
        if v_source < _MOCK_VDSAT_TAIL_V:
            return (
                f"tail source node at {v_source:.3f} V < V_dsat "
                f"{_MOCK_VDSAT_TAIL_V} V — tail current source in triode"
            )
        if v_out_dc < p["vcm_in"] - _MOCK_VTH_NMOS_V:
            return (
                f"V_out_dc {v_out_dc:.3f} V below V_gs-V_th "
                f"{p['vcm_in'] - _MOCK_VTH_NMOS_V:.3f} V — input pair in triode"
            )
        if b.vov > 0.5:
            return f"overdrive {b.vov:.3f} V unrealistically large for this W/L"
        return None

    def _max_linear_swing_v(self, p: Mapping[str, float], b: _Bias) -> float:
        """Compression limit: differential peak-to-peak, volts.

        Bounded both by the tail current through the load (2*I_branch*RL
        differentially) and by the DC headroom above the saturation edge.
        """
        current_limited = 2.0 * b.i_branch * p["rl"]
        v_out_dc = b.vdd - b.i_branch * p["rl"]
        headroom_limited = 2.0 * max(v_out_dc - (p["vcm_in"] - _MOCK_VTH_NMOS_V), 0.0)
        return max(min(current_limited, headroom_limited), 1e-6)

    def _hd3_dbc(self, p: Mapping[str, float], b: _Bias) -> float:
        """Third harmonic, dBc. Synthetic but monotone in the right things.

        For a square-law differential pair HD3 falls as (Vin/Vov)^2 and is
        suppressed by the degeneration factor (1 + gm*Rs/2) cubed. Both
        dependencies are real; the prefactor is invented.
        """
        k = 1.0 + b.gm * p["rs"] / 2.0
        x = (self.vin_diff_pp_v / 2.0) / (b.vov * k)
        hd3_lin = (x * x) / 32.0
        return 20.0 * math.log10(max(hd3_lin, 1e-12))

    def _input_noise_vrms(
        self, p: Mapping[str, float], b: _Bias, ss: deq.SmallSignal
    ) -> float:
        """Input-referred noise integrated over the S5 band, V_rms.

        Channel thermal noise of the pair, thermal noise of RL referred back
        through the stage gain, and thermal noise of Rs. Degeneration is a
        wash: it attenuates signal and the pair's own noise together.
        The point is the 1/sqrt(gm) dependence, which is what puts S5 in
        direct conflict with S6.
        """
        f_lo, f_hi = NOISE_BAND_HZ
        kt4 = 4.0 * BOLTZMANN * b.temp_k

        # Effective noise bandwidth: the stage rolls off at f_p2, so the band
        # that actually contributes is capped there.
        bw = max(min(f_hi, ss.f_pole2_hz * math.pi / 2.0) - f_lo, 1.0)

        s_pair = kt4 * _MOCK_GAMMA_THERMAL / b.gm          # V^2/Hz, input-ref
        s_load = kt4 * p["rl"] / (b.gm * p["rl"]) ** 2      # RL referred to input
        s_degen = kt4 * (p["rs"] / 2.0)                     # Rs sits in series

        # 2 for the differential pair (two devices, two loads).
        return math.sqrt(2.0 * (s_pair + s_load + s_degen) * bw)

    def _area_mm2(self, p: Mapping[str, float]) -> float:
        """Passive-dominated area, mm^2 (S7 notes passives dominate)."""
        squares = p["rs"] / _MOCK_RES_SHEET_OHM_SQ + 2.0 * p["rl"] / _MOCK_RES_SHEET_OHM_SQ
        area_r = squares * _MOCK_RES_AREA_MM2_PER_SQ
        area_c = (p["cs"] + 2.0 * p["cl"]) / _MOCK_CAP_DENSITY_F_PER_MM2
        return area_r + area_c + _MOCK_ACTIVE_AREA_MM2


# ─────────────────────────────────────────────────────────────────────────────
# A reference operating point for exercising the interface.
#
# THESE ARE NOT A HAND-DESIGN AND NOT PARAMETER BOUNDS. They exist so tests
# have something to call `evaluate()` with before G1 lands. Do not copy them
# into `nebula/common/params.py::BOUNDS` (CLAUDEwa.md §8 rule 6).
#
# Chosen by grid search over the mock for the property that makes it useful as
# a test fixture: `ok=True` at all 45 S9 corners AND non-compressing at every
# point of the default channel-loss sweep. In the mock's own (fake) numbers it
# lands at ~9.7 dB peaking near 1.6 GHz with a worst-case eye of ~108 mV.
#
# Note what the search had to do to get there: `g_dc` is 0.27, i.e. the stage
# ATTENUATES at DC. That is not a quirk of the mock — it is how a real CTLE
# driven by a PCIe-class transmit swing has to be biased. An earlier reference
# point with g_dc ~ 0.87 drove 994 mVpp into a 460 mVpp linear limit, and the
# compression check (calibration convention C4) correctly refused to report an
# eye for it. Expect G1 to run into the same wall.
# ─────────────────────────────────────────────────────────────────────────────

MOCK_REFERENCE_PARAMS: dict[str, float] = {
    "w_in": 40e-6,
    "l_in": 0.35e-6,
    "nf_in": 4.0,
    "w_tail": 40e-6,
    "l_tail": 1.0e-6,
    "nf_tail": 4.0,
    "i_bias": 5.0e-3,
    "rs": 800.0,
    "cs": 0.8e-12,
    "rl": 120.0,
    "cl": 1.2e-12,
    "vcm_in": 0.88,
}


_DEFAULT = MockDevice()


def evaluate(params: Mapping[str, float], corner: Corner) -> DeviceResult:
    """Module-level `evaluate` matching the §5.1 signature."""
    return _DEFAULT.evaluate(params, corner)
