"""
tests/test_invert_response.py — gates on the closed-form inverse of
`prescreen.predict_response` (`PREDICTIONS.md` entry 58).

WHY EACH GUARD EXISTS
----------------------
1.  **The closed form must agree with the function it claims to invert.** The
    derivation is algebra done by hand; the only thing that makes it
    trustworthy is that it reproduces `predict_response` on the same inputs.
    The round trip -- invert a target, predict the result, compare -- is
    therefore the central gate, and it runs over the whole S3 box rather than a
    convenient point.
2.  **`peaking <= 20*log10(k)` is a claim, so it is tested as one.** It is the
    design rule the module contributes; if it were wrong, `m_for_peaking` would
    silently return absurd values near the ceiling instead of refusing.
3.  **Units.** `predict_gm` takes METRES and takes `log(l)`. Passing microns
    gives `gm` 2.5x wrong **and the round trip still closes**, because both
    halves use the same wrong `gm` -- so no amount of self-consistency testing
    can catch it. Only an explicit guard can, and entry 58 records that this
    defect cost a whole feasibility map before it was found.
4.  **Infeasible must return None, not a bad design.** A caller that gets a
    silently wrong `Inversion` will simulate it and blame the simulator.

No SPICE: `predict_response` is the analytic model and costs microseconds.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from nebula.experiments import invert_response as IR
from nebula.experiments.prescreen import _GRID, _mag, predict_response

#: A legal mid-box bias, in METRES.
BIAS = {"w_in": 6e-5, "l_in": 5e-7, "nf_in": 4.0, "i_bias": 2e-3,
        "vcm_in": 1.35}
CL = 32.6e-15


# ─────────────────────────────────────────────────────────────────────────────
# Guard 1 — the closed form agrees with the model it inverts
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("k,m", [(3.0, 4.0), (5.0, 12.0), (2.2, 3.0),
                                 (1.5, 30.0), (4.0, 6.0)])
def test_the_closed_form_peak_matches_a_numeric_argmax(k, m):
    fz = 1.0e9
    fp1, fp2 = k * fz, m * fz
    got = IR.f_peak_of(fz, k, m)
    h = _mag(_GRID, fz, fp1, fp2)
    want = float(_GRID[int(np.argmax(h))])
    # The model maximises on a 1200-point log grid over 3.3 decades, so its own
    # resolution is 0.0091 octaves; the closed form must land inside that.
    assert abs(math.log2(got / want)) < 0.01


@pytest.mark.parametrize("k,m", [(3.0, 4.0), (5.0, 12.0), (2.2, 3.0)])
def test_the_closed_form_peaking_matches_the_model(k, m):
    fz = 1.0e9
    h = _mag(_GRID, fz, k * fz, m * fz)
    want = 20.0 * math.log10(h[int(np.argmax(h))] / h[0])
    assert IR.peaking_db_of(k, m) == pytest.approx(want, abs=0.01)


@pytest.mark.parametrize("peaking_db", [3.0, 6.0, 9.0, 12.0])
@pytest.mark.parametrize("f_peak_hz", [1.25e9, 1.9e9, 2.5e9])
def test_the_round_trip_hits_the_target(peaking_db, f_peak_hz):
    # Guard 1, the central gate: entry 58 measured 24 of 24 over this box.
    sol = IR.invert(peaking_db, f_peak_hz, BIAS, CL)
    assert sol is not None
    params = {**BIAS, "rs": sol.rs, "cs": sol.cs, "rl": sol.rl, "cl": CL}
    pred = predict_response(params, drawn=False)
    assert pred.peaking_db == pytest.approx(peaking_db, abs=0.05)
    assert abs(math.log2(pred.f_peak_hz / f_peak_hz)) < 0.02


def test_the_solution_reproduces_its_own_pole_zero_placement():
    sol = IR.invert(8.0, 1.9e9, BIAS, CL)
    assert sol is not None
    assert 1.0 / (2 * math.pi * sol.rs * sol.cs) == pytest.approx(sol.fz_hz,
                                                                 rel=1e-9)
    assert 1.0 / (2 * math.pi * sol.rl * CL) == pytest.approx(sol.fp2_hz,
                                                              rel=1e-9)
    assert sol.fp1_hz == pytest.approx(sol.k * sol.fz_hz, rel=1e-12)


# ─────────────────────────────────────────────────────────────────────────────
# Guard 2 — the ceiling is a real constraint
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("k", [1.5, 2.0, 3.0, 4.0, 6.0])
def test_peaking_approaches_20log10k_from_below(k):
    ceiling = IR.max_peaking_db(k)
    assert ceiling == pytest.approx(20.0 * math.log10(k))
    # Never exceeded, and approached as m grows.
    assert IR.peaking_db_of(k, 1e6) < ceiling
    assert IR.peaking_db_of(k, 1e6) > ceiling - 0.01
    assert IR.peaking_db_of(k, 3.0) < ceiling


def test_a_target_above_the_ceiling_is_refused():
    # Guard 2: refusing is the correct answer, not returning a near-miss.
    k = 2.0                                   # ceiling 6.02 dB
    assert IR.m_for_peaking(k, 6.5) is None
    assert IR.m_for_peaking(k, 20.0) is None


def test_a_target_below_the_ceiling_is_solved():
    k = 4.0                                   # ceiling 12.04 dB
    m = IR.m_for_peaking(k, 9.0)
    assert m is not None and m > 1.0
    assert IR.peaking_db_of(k, m) == pytest.approx(9.0, abs=1e-6)


def test_k_needed_and_rs_needed_are_consistent():
    gm, gmbs = 7.5e-3, 1.4e-3
    for p in (3.0, 6.0, 9.0, 12.0):
        rs = IR.rs_needed_for(p, gm, gmbs)
        from nebula.experiments.prescreen import K_ALPHA
        k = 1.0 + K_ALPHA * (gm + gmbs) * rs / 2.0
        assert k == pytest.approx(IR.k_needed_for(p), rel=1e-9)
        assert IR.max_peaking_db(k) == pytest.approx(p, abs=1e-9)


def test_a_bias_too_weak_for_the_target_returns_none():
    weak = {**BIAS, "i_bias": 5e-4}
    # 12 dB needs k > 3.98; at a small rs that is unreachable.
    assert IR.invert(12.0, 1.9e9, weak, CL, rs=50.0) is None


# ─────────────────────────────────────────────────────────────────────────────
# Guard 3 — units
# ─────────────────────────────────────────────────────────────────────────────

def test_microns_are_refused():
    microns = {"w_in": 60.0, "l_in": 0.5, "nf_in": 4.0, "i_bias": 2e-3}
    with pytest.raises(ValueError, match="MICRONS"):
        IR.invert(6.0, 1.9e9, microns, CL)


def test_a_micron_length_alone_is_refused():
    # `l_in` is the one that enters as log(l); it must trip the guard on its own.
    bad = {**BIAS, "l_in": 0.5}
    with pytest.raises(ValueError, match="MICRONS"):
        IR.invert(6.0, 1.9e9, bad, CL)


def test_metres_are_accepted():
    assert IR.invert(6.0, 1.9e9, BIAS, CL) is not None


def test_the_round_trip_would_NOT_have_caught_the_units_bug():
    # The reason guard 3 exists at all: self-consistency is blind to it,
    # because both halves of the round trip use the same wrong gm. Here we
    # show the inversion is internally consistent for ANY gm, so no round-trip
    # test could ever have flagged microns.
    from nebula.experiments.prescreen import K_ALPHA
    for gm_sum in (1e-3, 8e-3, 3e-2):          # spans the wrong and right gm
        rs = 300.0
        k = 1.0 + K_ALPHA * gm_sum * rs / 2.0
        # Aim at half of THIS k's ceiling, so the target is reachable at every
        # gm. (An earlier version asked for a fixed 6 dB and failed at the
        # smallest gm, where the ceiling is only 1.10 dB -- the refusal was
        # correct and the test was wrong.)
        target = 0.5 * IR.max_peaking_db(k)
        m = IR.m_for_peaking(k, target)
        assert m is not None, f"k={k} ceiling={IR.max_peaking_db(k)}"
        assert IR.peaking_db_of(k, m) == pytest.approx(target, abs=1e-6)


# ─────────────────────────────────────────────────────────────────────────────
# Guard 4 — infeasible returns None
# ─────────────────────────────────────────────────────────────────────────────

def test_a_zero_or_negative_rs_returns_none():
    assert IR.invert(6.0, 1.9e9, BIAS, CL, rs=0.0) is None
    assert IR.invert(6.0, 1.9e9, BIAS, CL, rs=-10.0) is None


def test_a_nonpositive_peaking_returns_none():
    assert IR.invert(0.0, 1.9e9, BIAS, CL) is None


def test_every_returned_passive_is_positive_and_finite():
    for p in (3.0, 6.0, 9.0, 12.0):
        sol = IR.invert(p, 1.9e9, BIAS, CL)
        if sol is None:
            continue
        for v in (sol.rs, sol.cs, sol.rl, sol.fz_hz, sol.fp1_hz, sol.fp2_hz):
            assert math.isfinite(v) and v > 0.0
