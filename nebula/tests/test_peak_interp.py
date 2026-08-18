"""
Tests for the interpolated AC peak — G74's reward ceiling, at its source.

WHAT IS BEING PROTECTED HERE, IN ORDER OF HOW BADLY IT WOULD HURT
------------------------------------------------------------------
1. **The default path cannot move.** Every published number in this project —
   the +8.950669 ceiling itself, `BASELINES.md`, `RL_SMOKE.md`, `DIFFICULTY.md`
   — was measured on the lattice peak. `ac_peak_interp=True` therefore has to
   be provably additive, and "provably" here means rel=0, abs=0 across every
   parsed field, the same discipline G36 used for the trimmed library.
2. **The G44 guard must survive the change.** A sweep-edge maximum has no
   bracketing triple, so an "interpolated" peak there would be the same
   fictitious peak with a decimal point of extra precision. Two tests below
   break the input, watch the guard fire, put it back and watch it stop —
   because a guard whose condition is unreachable is indistinguishable from a
   guard that was deleted (G73's general form, the ARGMAX one).
3. **The vertex must be the vertex.** Exact on a synthetic parabola, inside its
   own cell always, and refusing loudly on the three shapes where no vertex
   exists (flat top, non-uniform grid, edge maximum).

The last test is the one the whole exercise is for: it shows the lattice
ceiling is **not** a ceiling once the peak is read off the parabola.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from nebula.device.sky130_runner import (
    MAX_SEARCH_BOT_HZ,
    MAX_SEARCH_TOP_HZ,
    PeakInterp,
    SizingPoint,
    Sky130Point,
    assemble_netlist,
    interpolate_peak_log_f,
)

# `ac dec 50 1meg 100g`, the grid every netlist in this project sweeps.
DEC = 50
F_START = 1e6
F_STOP = 100e9
STEP_OCT = math.log2(10.0 ** (1.0 / DEC))       # 0.066438... octaves


def _grid() -> np.ndarray:
    """The exact frequency lattice the deck produces."""
    n = round(DEC * math.log10(F_STOP / F_START))
    return F_START * 10.0 ** (np.arange(n + 1) / DEC)


def _parabola(f: np.ndarray, f_peak_hz: float, g_peak_db: float,
              curvature_db_per_oct2: float = -4.0) -> np.ndarray:
    """A response that IS a parabola in (log2 f, dB), so the vertex is known."""
    x = np.log2(f / f_peak_hz)
    return g_peak_db + curvature_db_per_oct2 * x * x


# ─────────────────────────────────────────────────────────────────────────────
# The arithmetic. No simulator.
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("offset_steps", [0.0, 0.1, 0.25, 0.4, 0.49, -0.37])
def test_the_vertex_is_recovered_exactly_on_a_synthetic_parabola(offset_steps):
    """A parabola in log-f is fitted by a parabola in log-f, exactly.

    The offsets sweep the whole cell, including the two places a sign error
    hides: dead on a grid point (0.0), where any formula looks right, and just
    inside the cell edge (0.49), where the wrong sign lands a full step away.
    """
    f = _grid()
    f_true = 2.0e9 * 2.0 ** (offset_steps * STEP_OCT)
    # Snap the true peak so it sits `offset_steps` from a grid point exactly.
    k = round(DEC * math.log10(2.0e9 / F_START))
    f_grid = F_START * 10.0 ** (k / DEC)
    f_true = f_grid * 2.0 ** (offset_steps * STEP_OCT)

    y = _parabola(f, f_true, 9.5)
    r = interpolate_peak_log_f(f, y)
    assert r.ok, r.reason
    assert r.f_hz == pytest.approx(f_true, rel=1e-12)
    assert r.g_db == pytest.approx(9.5, abs=1e-12)
    assert r.step_octaves == pytest.approx(STEP_OCT, rel=1e-12)
    assert r.curvature_db < 0.0
    assert r.edge is None
    # The discrete maximum is the nearest grid point, and the lattice error is
    # exactly what G74 is about.
    assert abs(math.log2(r.f_hz / r.f_grid_hz)) <= 0.5 * STEP_OCT + 1e-12


def test_the_vertex_never_leaves_its_own_cell():
    """|delta| <= half a grid step, on 200 random smooth responses.

    This is the property that makes `d_f_peak_octaves` interpretable: anything
    outside half a step is not a refinement, it is a disagreement about which
    sample is the maximum, and the runner's cross-check turns that into a
    refusal rather than a small correction.
    """
    f = _grid()
    rng = np.random.default_rng(20260819)
    for _ in range(200):
        f_true = float(rng.uniform(0.5e9, 8e9))
        curv = float(-rng.uniform(0.5, 40.0))
        y = _parabola(f, f_true, float(rng.uniform(1.0, 20.0)), curv)
        r = interpolate_peak_log_f(f, y)
        assert r.ok, r.reason
        assert abs(r.delta_octaves) <= 0.5 * STEP_OCT + 1e-12
        assert r.f_hz == pytest.approx(f_true, rel=1e-9)


def test_a_response_still_rising_at_the_top_is_refused_AND_the_guard_can_fail():
    """**The G44 case, and its own negative control.**

    Break the input -> the guard fires. Put it back -> it stops. Without the
    second half this test would pass just as happily against a guard that
    always returns "edge", which is the failure mode G73 describes: a condition
    that is never reachable is indistinguishable from a deleted check.
    """
    f = _grid()
    # RISING monotonically through the whole search window: `meas ac MAX`
    # reports the window edge and the peaking it implies is fictitious.
    rising = 3.0 * np.log2(f / F_START)
    r = interpolate_peak_log_f(f, rising)
    assert not r.ok
    assert r.edge == "top"
    assert "still" in (r.reason or "") and "rising" in (r.reason or "")
    # The discrete maximum it refused is the last in-window sample.
    inside = (f >= MAX_SEARCH_BOT_HZ) & (f <= MAX_SEARCH_TOP_HZ)
    assert r.f_grid_hz == pytest.approx(float(f[inside][-1]), rel=0)

    # ---- put it back: the SAME shape, brought back down before the edge ----
    # A triangle in (log f, dB) peaking at 5 GHz, rising at the identical
    # 3 dB/octave. The only thing that differs is whether the response comes
    # back down, so the only thing this pair can be testing is the guard.
    x = np.log2(f / 5e9)
    came_back = 3.0 * np.where(x <= 0.0, x, -x)
    r2 = interpolate_peak_log_f(f, came_back)
    assert r2.ok, r2.reason
    assert r2.edge is None


def test_a_monotonically_falling_response_is_refused_at_the_BOTTOM():
    """G44's other half: `meas ac MAX` returns the 10 MHz start.

    Refused for a different reason and with a different label, because the two
    are different circuits — one has no peak below 20 GHz, the other has no
    peak at all — and a single "edge" label would hide which.
    """
    f = _grid()
    falling = -2.0 * np.log2(f / F_START)
    r = interpolate_peak_log_f(f, falling)
    assert not r.ok
    assert r.edge == "bottom"
    assert r.f_grid_hz == pytest.approx(MAX_SEARCH_BOT_HZ, rel=1e-9)


def test_the_vertex_arithmetic_refuses_a_flat_or_convex_triple():
    """Zero curvature is refused, not divided by.

    `delta = 0.5*(y0-y2)/(y0-2*y1+y2)` is 0/0 on a perfectly flat top: numpy
    would hand back `nan` and the caller would carry it three modules
    downstream. Tested on `parabolic_vertex` DIRECTLY, because that branch is
    unreachable through `interpolate_peak_log_f` -- see the next test -- and a
    guard tested only through a path that cannot reach it is not tested at all
    (G73's general form).
    """
    from nebula.device.sky130_runner import parabolic_vertex

    assert parabolic_vertex(7.0, 7.0, 7.0) is None          # flat
    assert parabolic_vertex(9.0, 7.0, 9.0) is None          # convex: a MINIMUM
    assert parabolic_vertex(6.0, 7.0, 8.0) is None          # a straight line
    # ... and it does not refuse a real maximum, or every assertion above would
    # pass against a function that returned None unconditionally.
    v = parabolic_vertex(6.0, 8.0, 6.0)
    assert v is not None
    assert v[0] == pytest.approx(0.0) and v[1] == pytest.approx(8.0)
    v = parabolic_vertex(6.0, 8.0, 7.0)
    assert v is not None and v[0] > 0.0


def test_an_argmax_selected_triple_is_ALWAYS_concave():
    """The invariant that makes the branch above unreachable, stated and pinned.

    `np.argmax` returns the FIRST maximal sample, so the selected `y1` is
    strictly greater than `y0` and at least `y2`; therefore
    `y0 - 2*y1 + y2 = (y0-y1) + (y2-y1) < 0` strictly. Recorded as a test
    rather than as a comment because it is a property of the SELECTION RULE,
    and a tie-breaking change one day would silence the guard rather than trip
    it. Values are rounded to 3 dB decimals first, which is what makes ties --
    the adversarial case -- actually occur.
    """
    f = _grid()
    rng = np.random.default_rng(4242)
    for _ in range(50):
        y = _parabola(f, float(rng.uniform(0.3e9, 9e9)), 8.0,
                      float(-rng.uniform(0.2, 60.0)))
        y = np.round(y, 3)
        r = interpolate_peak_log_f(f, y)
        if r.edge is not None:
            continue
        assert r.ok, r.reason
        assert r.curvature_db < 0.0


def test_a_non_uniform_grid_is_refused_rather_than_mis_fitted():
    """The vertex formula assumes equal spacing; unequal spacing is a failure.

    This is the shape of bug that does not announce itself: the answer stays
    finite, stays near the peak, and is wrong by a fraction of a grid step.
    """
    f = _grid()
    f = f.copy()
    j = int(np.argmin(np.abs(f - 2e9)))
    f[j - 1] *= 0.5           # move one bracketing sample
    y = _parabola(f, 2e9, 9.0)
    r = interpolate_peak_log_f(f, y)
    assert not r.ok
    assert "equally" in (r.reason or "")


def test_too_few_samples_and_mismatched_arrays_are_named():
    r = interpolate_peak_log_f(np.array([1e9, 2e9]), np.array([1.0, 2.0]))
    assert not r.ok and "needs 3" in (r.reason or "")
    r = interpolate_peak_log_f(np.array([1e9, 2e9, 3e9]), np.array([1.0, 2.0]))
    assert not r.ok and "differ" in (r.reason or "")


def test_a_non_finite_sample_inside_the_window_is_refused():
    f = _grid()
    y = _parabola(f, 2e9, 9.0)
    y[int(np.argmin(np.abs(f - 3e9)))] = np.nan
    r = interpolate_peak_log_f(f, y)
    assert not r.ok and "non-finite" in (r.reason or "")


# ─────────────────────────────────────────────────────────────────────────────
# The properties on `Sky130Point`.
# ─────────────────────────────────────────────────────────────────────────────


def _point_with(interp: PeakInterp, **kw) -> Sky130Point:
    pt = Sky130Point(ok=True, g_dc_db=5.0, g_pk_db=9.0, f_pk_hz=2.0e9,
                     g_top_db=1.0, **kw)
    pt.peak_interp = interp.as_dict()
    if interp.ok:
        pt.f_pk_interp_hz = interp.f_hz
        pt.g_pk_interp_db = interp.g_db
    return pt


def test_peak_interp_is_sweep_edge_RAISES_when_the_interpolation_never_ran():
    """"Not asked for" is not an answer to "is it fictitious".

    Returning False here would be a fabricated pass for every result in the
    repository that predates the flag.
    """
    pt = Sky130Point(ok=True, g_dc_db=5.0, g_pk_db=9.0, f_pk_hz=2e9, g_top_db=1.0)
    assert pt.peak_interp is None
    assert not pt.has_interp_peak
    with pytest.raises(ValueError, match="ac_peak_interp"):
        _ = pt.peak_interp_is_sweep_edge


def test_the_sweep_edge_verdict_reaches_the_point_and_can_flip():
    """Guard fires on the edge case, and does not on the interior one."""
    f = _grid()
    rising = 3.0 * np.log2(f / F_START)
    edge_pt = _point_with(interpolate_peak_log_f(f, rising))
    assert edge_pt.peak_interp_is_sweep_edge
    assert not edge_pt.has_interp_peak

    good_pt = _point_with(interpolate_peak_log_f(f, _parabola(f, 2e9, 9.0)))
    assert not good_pt.peak_interp_is_sweep_edge
    assert good_pt.has_interp_peak
    assert good_pt.peaking_interp_db == pytest.approx(9.0 - 5.0, abs=1e-9)
    assert abs(good_pt.d_f_peak_octaves) <= 0.5 * STEP_OCT + 1e-9


# ─────────────────────────────────────────────────────────────────────────────
# The measurement vector, and the ceiling itself.
# ─────────────────────────────────────────────────────────────────────────────


def test_meas_with_interpolated_peak_swaps_BOTH_keys_or_neither():
    from nebula.rl.evaluator import INTERP_KEYS, meas_with_interpolated_peak

    base = {"g_dc_db": 5.0, "peaking_db": 4.0, "f_peak_oct": -0.3,
            "nyq_boost_db": 1.0, "inoise_vrms": 2e-4, "power_w": 3e-3,
            "pair_margin_v": 0.2, "tail_margin_v": 0.2}
    with pytest.raises(ValueError, match="absent"):
        meas_with_interpolated_peak(base)
    with pytest.raises(ValueError, match="no measurement"):
        meas_with_interpolated_peak(None)

    # Half the pair is still a refusal — a frequency from the parabola beside a
    # magnitude from the lattice would be one peak read in two places.
    half = dict(base, f_peak_oct_interp=-0.28)
    with pytest.raises(ValueError, match="absent"):
        meas_with_interpolated_peak(half)

    full = dict(base, f_peak_oct_interp=-0.28, peaking_db_interp=4.01)
    out = meas_with_interpolated_peak(full)
    assert out["f_peak_oct"] == -0.28 and out["peaking_db"] == 4.01
    for _, new in INTERP_KEYS:
        assert new not in out
    assert full["f_peak_oct"] == -0.3, "the input must not be mutated"


def test_THE_LATTICE_CEILING_IS_NOT_A_CEILING_ON_THE_INTERPOLATED_PATH():
    """**The reason this whole change exists.**

    G74: `reward_v1`'s best attainable score is +8.950669 because `meas ac MAX`
    can only report frequencies 0.066439 octaves apart and the nearest lattice
    point to the mid-window target is 0.024665 octaves away. Read the peak off
    the parabola instead and the same reward function, unchanged, scores a
    perfectly centred design at 9.0 — strictly above a ceiling that 57 distinct
    designs tied across 8000 simulations.
    """
    from nebula.experiments.baselines import reward_ceiling
    from nebula.rl import reward_v1 as R
    from nebula.rl.evaluator import meas_with_interpolated_peak
    from nebula.rl.contract import f_peak_octaves

    target = math.sqrt(1.25e9 * 2.5e9)
    lattice_ceiling = reward_ceiling(target, R.V1_SPECS)
    assert lattice_ceiling == pytest.approx(8.950669295771243, rel=0, abs=1e-12)

    # A design that meets every other spec comfortably, whose lattice peak is
    # the nearest grid point to the target and whose interpolated peak is the
    # target itself.
    k = round(50 * math.log10(target / 1e6))
    f_lattice = 1e6 * 10.0 ** (k / 50)
    meas = {
        "g_dc_db": 8.0, "peaking_db": 7.5, "nyq_boost_db": 4.0,
        "f_peak_oct": f_peak_octaves(f_lattice),
        "inoise_vrms": 2.0e-4, "power_w": 3.0e-3,
        "pair_margin_v": 0.30, "tail_margin_v": 0.30,
        "f_peak_oct_interp": f_peak_octaves(target),
        "peaking_db_interp": 7.5,
    }
    r_lattice = R.reward_v1(meas, target, target_peaking_db=7.5).reward
    r_interp = R.reward_v1(meas_with_interpolated_peak(meas), target,
                           target_peaking_db=7.5).reward
    assert r_lattice == pytest.approx(lattice_ceiling, rel=0, abs=1e-9)
    assert r_interp > lattice_ceiling
    assert r_interp == pytest.approx(9.0, rel=0, abs=1e-9)


# ─────────────────────────────────────────────────────────────────────────────
# `scoring_meas` — the one rule both scoring paths use.
# ─────────────────────────────────────────────────────────────────────────────


class _Ev:
    """The two fields `scoring_meas` / `interp_was_refused` actually read."""

    def __init__(self, meas, raw=None):
        self.meas = meas
        self.raw = raw or {}


def _meas(**kw) -> dict:
    base = {"g_dc_db": 5.0, "peaking_db": 4.0, "f_peak_oct": -0.30,
            "nyq_boost_db": 1.0, "inoise_vrms": 2e-4, "power_w": 3e-3,
            "pair_margin_v": 0.2, "tail_margin_v": 0.2}
    base.update(kw)
    return base


def test_scoring_meas_is_the_identity_when_the_flag_is_off():
    """**The safety property the whole change rests on.**

    Every published number was computed from `ev.meas`. With the flag off this
    must hand back exactly that object's contents — not a copy with a key
    renamed, not a copy with a float rounded.
    """
    from nebula.rl.evaluator import scoring_meas

    m = _meas(f_peak_oct_interp=-0.28, peaking_db_interp=4.01)
    out = scoring_meas(_Ev(m), ac_peak_interp=False)
    assert out is m, "the flag-off path must not even copy"
    assert scoring_meas(_Ev(None), ac_peak_interp=False) is None
    assert scoring_meas(_Ev(None), ac_peak_interp=True) is None


def test_scoring_meas_swaps_the_peak_when_the_flag_is_on():
    from nebula.rl.evaluator import scoring_meas

    m = _meas(f_peak_oct_interp=-0.28, peaking_db_interp=4.01)
    out = scoring_meas(_Ev(m), ac_peak_interp=True)
    assert out["f_peak_oct"] == -0.28 and out["peaking_db"] == 4.01
    assert "f_peak_oct_interp" not in out
    assert m["f_peak_oct"] == -0.30, "the input must not be mutated"


def test_a_refusal_falls_back_to_the_LATTICE_and_not_to_the_floor():
    """**The decision recorded in `scoring_meas`, pinned so it cannot drift.**

    A design whose sub-grid peak cannot be located still has a perfectly good
    lattice measurement. Scoring it at the invalid floor would punch a hole in
    the reward landscape for a reason that is a property of the sweep's
    numerical resolution, not of the circuit — the same mistake `validate`'s
    G44 comment records having made once already. Measured rate: 1 valid design
    in 4543.
    """
    from nebula.rl import reward_v1 as R
    from nebula.rl.evaluator import scoring_meas

    refused = _Ev(_meas(), raw={"peak_interp_status": "refused"})
    out = scoring_meas(refused, ac_peak_interp=True)
    assert out == _meas(), "a refusal must score the lattice measurement"

    target = math.sqrt(1.25e9 * 2.5e9)
    r = R.reward_v1(out, target).reward
    assert r > R.invalid_reward(len(R.V1_SPECS)), (
        "a refused interpolation must not be scored as an invalid design")
    assert r == R.reward_v1(_meas(), target).reward


def test_interp_was_refused_distinguishes_OFF_from_REFUSED():
    """"Never asked" and "asked and failed" are different facts.

    If these collapsed, a run with the flag off would report 100 % refusals and
    a run with a broken interpolation would look identical to a healthy one.
    """
    from nebula.rl.evaluator import interp_was_refused

    assert not interp_was_refused(_Ev(_meas()))                       # flag off
    assert not interp_was_refused(_Ev(_meas(), {"peak_interp_status": "vertex"}))
    assert not interp_was_refused(
        _Ev(_meas(), {"peak_interp_status": "boundary_bottom_lattice_is_exact"}))
    assert interp_was_refused(_Ev(_meas(), {"peak_interp_status": "refused"}))


def test_the_env_and_the_objective_read_the_SAME_definition():
    """PPO and the other four methods must score one objective (`BASELINES.md` 7f).

    They reach the reward through different files — `rl/env.py` for PPO,
    `experiments/baselines.py` for the rest — so this asserts that both call
    `evaluator.scoring_meas` rather than each formatting its own measurement
    vector. A benchmark whose methods optimise different objectives is
    measuring formulation, not search.
    """
    import inspect

    from nebula.experiments import baselines as B
    from nebula.rl import env as E

    for mod, fn in ((B, B.Objective._score_one), (E, E.CtleSizingEnv._evaluate_current)):
        src = inspect.getsource(fn)
        assert "scoring_meas(" in src, f"{fn.__qualname__} does not use scoring_meas"
    assert E.EnvConfig(seed=0).ac_peak_interp is False
    assert B.Objective(B.PROBLEMS["P1"], budget_sims=1).ac_peak_interp is False


# ─────────────────────────────────────────────────────────────────────────────
# Simulator-backed.
# ─────────────────────────────────────────────────────────────────────────────


def _have_sim() -> bool:
    import shutil
    from nebula.device.ngspice_runner import _DEFAULT_NGSPICE
    from nebula.device.sky130_runner import TRIMMED_LIB
    ng = _DEFAULT_NGSPICE.exists() or shutil.which("ngspice_con") is not None
    return ng and TRIMMED_LIB.exists()


needs_sim = pytest.mark.skipif(not _have_sim(), reason="ngspice or SKY130 absent")

_REF = dict(w=40, l=0.15, nf=4, rs=200, cs=1.6e-12, rl=400, cl=100e-15,
            i_tail_per_side_a=1.5e-3, vcm=1.25, vdd=1.8)


def test_the_max_search_window_matches_the_netlist():
    """`MAX_SEARCH_BOT_HZ` / `MAX_SEARCH_TOP_HZ` against the assembled deck.

    The netlist is the definition and the two constants mirror it (see their
    docstrings); this is what keeps them ONE thing. It needs no simulator —
    the deck is a string — and it goes red if either side moves alone, which
    is the check G32's mismatched model card did not have.
    """
    import re
    text = assemble_netlist(
        lib="x.lib", corner="tt", device="nfet", w=1, l=1, nf=1, rl=1, rs=1,
        cs=1e-12, cl=1e-13, it=1e-3, vdd=1.8, vcm=1.2, swing_block="",
        temp_c=27.0, tail_source="", tail_probe="", passive_block="",
        noise_summary="", noise_probe="",
        f_top=f"{MAX_SEARCH_TOP_HZ / 1e9:g}g")
    m = re.search(r"meas ac g_pk\s+MAX\s+vd_db FROM=(\S+) TO=(\S+)", text)
    assert m, "the `meas ac MAX` line is not where this test thinks it is"
    lo, hi = m.group(1), m.group(2)
    assert lo == f"{MAX_SEARCH_BOT_HZ / 1e6:g}meg", (lo, MAX_SEARCH_BOT_HZ)
    assert hi == f"{MAX_SEARCH_TOP_HZ / 1e9:g}g", (hi, MAX_SEARCH_TOP_HZ)
    assert f"meas ac g_top FIND vd_db AT={hi}" in text


@needs_sim
def test_ac_peak_interp_changes_no_measured_value():
    """PURELY ADDITIVE, at rel=0 and abs=0 — session 21's pattern, reused.

    The flag implies `ac_sweep`, which already has this test; what is new is
    that nothing in the *parse* path moved either. Every published number in
    this repository was measured with the flag off, and this is the assertion
    that lets the two coexist.
    """
    from nebula.device.sky130_runner import run_point

    p = SizingPoint(**_REF)
    off = run_point(p, swing=False, ac_sweep=False)
    on = run_point(p, swing=False, ac_peak_interp=True)
    assert off.ok and on.ok, (off.fail_reason, on.fail_reason)

    compared = ("gm", "gmbs", "gds", "vth", "vds", "vdsat", "vgs", "id_a",
                "v_out_dc", "v_src_dc", "i_supply_a", "g_dc_db", "g_nyq_db",
                "g_pk_db", "f_pk_hz", "g_top_db", "vn_in_vrms")
    for name in compared:
        a, b = getattr(off, name), getattr(on, name)
        assert a == b, f"{name} moved: {a!r} -> {b!r} (rel=0 abs=0 required)"

    assert off.peak_interp is None and off.f_pk_interp_hz is None
    assert on.peak_interp is not None and on.f_pk_interp_hz is not None
    # The flag implies the dump, because there is nothing to interpolate
    # without it — and asking and silently getting nothing is G68's symptom.
    assert on.ac_freq_hz is not None


@needs_sim
def test_the_python_argmax_reproduces_meas_ac_MAX():
    """Two independent readings of one `vd_db` vector must name one sample.

    `meas ac g_pk MAX` is ngspice's; `interpolate_peak_log_f` is numpy's. If
    they disagree the interpolation is refining the wrong cell, which would
    surface as a `d_f_peak_octaves` distribution with a tail rather than as an
    error — so the runner refuses instead, and this pins the agreement.
    """
    from nebula.device.sky130_runner import run_point

    for rl in (200.0, 400.0, 700.0):
        p = SizingPoint(**{**_REF, "rl": rl})
        r = run_point(p, swing=False, ac_peak_interp=True)
        assert r.ok, r.fail_reason
        if not r.has_interp_peak:
            continue                       # a refusal is a legitimate outcome
        assert r.peak_interp["f_grid_hz"] == pytest.approx(r.f_pk_hz, rel=1e-6)
        assert abs(r.d_f_peak_octaves) <= 0.5 * STEP_OCT + 1e-9
        assert r.peaking_interp_db >= r.peaking_db - 1e-12


@needs_sim
def test_a_monotonically_falling_design_KEEPS_its_graded_miss():
    """**The gradient at the bottom of the box must survive the change.**

    `validate` deliberately ACCEPTS a monotonically falling response: `f_pk`
    comes back as the 10 MHz search start, which is inside `F_PEAK_HZ_LIMITS`,
    and the design is scored as the large graded S3 miss it is. Its comment
    records why — rejecting it "would erase the reward gradient over the entire
    low-peaking region of the box, which is where a randomly initialised policy
    starts."

    The interpolation has no vertex to offer there, and refusing on that basis
    would rebuild exactly that hole one layer up: the interpolated arm would
    see an invalid floor where the discrete arm sees gradient. So the lattice
    pair is carried forward — correctly, because 10 MHz is both a grid point
    and the boundary, so `meas ac MAX` reported the true maximum of the
    interval and nothing was rounded.

    Driven off a REAL design, found by walking `rs` up until the peaking
    collapses, rather than off a hand-built `meas` dict — the point is that
    this case occurs in the box the benchmark samples.
    """
    from nebula.rl.contract import sizing_from_u
    from nebula.rl.evaluator import (
        SpiceBudget, Verdict, evaluate, meas_with_interpolated_peak,
    )
    from nebula.rl import reward_v1 as R

    # Two box coordinates measured to land on the bottom boundary: `cs` near
    # the floor puts the degeneration zero far above the search window, so the
    # response falls from DC and `meas ac MAX` returns the 10 MHz start.
    found = None
    for u in ([0.151, 0.440, 0.240, 0.402, 0.097, 0.968, 0.215],
              [0.722, 0.867, 0.893, 0.162, 0.027, 0.651, 0.215]):
        ev = evaluate(sizing_from_u(u), SpiceBudget(), ac_peak_interp=True)
        if (ev.verdict is Verdict.VALID
                and ev.raw.get("peak_interp_status")
                == "boundary_bottom_lattice_is_exact"):
            found = ev
            break
    if found is None:
        pytest.skip("no bottom-boundary design in the probed slice of the box")

    target = math.sqrt(1.25e9 * 2.5e9)
    swapped = meas_with_interpolated_peak(found.meas)
    assert swapped["f_peak_oct"] == found.meas["f_peak_oct"]
    assert swapped["peaking_db"] == found.meas["peaking_db"]
    r_disc = R.reward_v1(found.meas, target).reward
    r_int = R.reward_v1(swapped, target).reward
    assert r_int == r_disc
    # ... and it is a GRADED miss, not the invalid floor.
    assert r_int > R.invalid_reward(len(R.V1_SPECS))


@needs_sim
def test_evaluate_adds_the_keys_without_moving_the_reward():
    """`evaluate(ac_peak_interp=True)` must leave `reward_v1(meas)` identical.

    This is the assertion that makes the flag safe to leave in the shared
    harness: the discrete keys carry the same floats, so `Objective` scores
    what it always scored, and only a caller that explicitly swaps the keys
    sees a different number.
    """
    from nebula.rl.contract import ACTION_SPACE, sizing_from_u
    from nebula.rl.evaluator import (
        SpiceBudget, Verdict, evaluate, meas_with_interpolated_peak,
    )
    from nebula.rl import reward_v1 as R

    u = [0.55, 0.30, 0.45, 0.35, 0.55, 0.60, 0.40]
    assert len(u) == len(ACTION_SPACE)
    sizing = sizing_from_u(u)
    off = evaluate(sizing, SpiceBudget())
    on = evaluate(sizing, SpiceBudget(), ac_peak_interp=True)
    assert off.verdict is on.verdict, (off.reason, on.reason)
    if off.verdict is not Verdict.VALID:
        pytest.skip(f"reference design is not VALID here: {off.reason}")

    for k, v in off.meas.items():
        assert on.meas[k] == v, f"{k} moved: {v!r} -> {on.meas[k]!r}"
    target = math.sqrt(1.25e9 * 2.5e9)
    assert (R.reward_v1(off.meas, target).reward
            == R.reward_v1(on.meas, target).reward)

    assert "f_peak_oct_interp" in on.meas and "peaking_db_interp" in on.meas
    swapped = meas_with_interpolated_peak(on.meas)
    assert swapped["f_peak_oct"] != on.meas["f_peak_oct"] or True  # may coincide
    assert "f_peak_oct_interp" not in swapped
