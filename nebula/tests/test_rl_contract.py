"""
§6c — the environment contract. Units, scales, and the two fixed dimensions.

*"Document every unit and every scale. Two definitions of one quantity is the
failure mode this repo keeps hitting."*

So these tests are mostly about IDENTITY: that a quantity is computed in one
place, that the observation is assembled by one function, and that the scales
are constants rather than statistics.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from nebula.common.types import (
    NYQUIST_HZ,
    SPEC_F_PEAK_HZ_RANGE,
    SPEC_PEAKING_DB_RANGE,
    SPEC_POWER_MAX_W,
    SPEC_VN_IN_MAX_VRMS,
)
from nebula.rl import contract as C


# ── the box ─────────────────────────────────────────────────────────────────

def test_every_action_bound_has_a_provenance():
    """CLAUDEwa.md §8 rule 6, applied to a box this session did not choose."""
    for d in C.ACTION_SPACE:
        assert d.provenance.strip(), f"{d.name} has no provenance"
        assert len(d.provenance) > 40, (
            f"{d.name}'s provenance is a label, not a provenance: "
            f"{d.provenance!r}")


def test_every_edge_matches_the_proposed_box_exactly():
    """The box is COPIED from `s3_yield.PROPOSED_BOX`, not re-derived.

    If these drift apart, two documents describe "the same" box differently —
    G32's failure, on the parameter ranges instead of on a model card.
    """
    from nebula.experiments.s3_yield import PROPOSED_BOX

    for d in C.ACTION_SPACE:
        lo, hi, log, _ = PROPOSED_BOX[d.name]
        assert (d.lo, d.hi, d.log) == (lo, hi, log), (
            f"{d.name} differs from PROPOSED_BOX: contract has "
            f"({d.lo}, {d.hi}, {d.log}), box has ({lo}, {hi}, {log})")


def test_the_tail_is_not_in_the_action_space():
    """CALL 2. The §6e gate measured `vcm_in` as a **6x stronger lever on the
    tail margin** than either tail axis — 0.605 against 0.1008 and 0.0982 of a
    channel scale under one `MAX_STEP`. Both tail axes were live, and both were
    redundant with a dimension that has to be in the space anyway; a policy
    gradient on a weak, redundant axis learns noise (the G38 argument)."""
    assert "tail_j" not in C.ACTION_NAMES
    assert "l_tail" not in C.ACTION_NAMES
    assert "nf_tail" not in C.ACTION_NAMES
    assert C.N_ACTIONS == 7
    assert set(C.ACTION_NAMES) == {"w_in", "l_in", "i_bias", "rs", "cs", "rl",
                                   "vcm_in"}


def test_the_tail_rule_is_s9_yields_and_is_not_restated():
    """ONE definition (rule 9). If these drift apart, the RL loop and the
    corner sweep are sizing different tails and nothing says so."""
    from nebula.experiments.s9_yield import TAIL_L_UM, TAIL_UM_PER_AMP

    assert C.tail_sizing_rule() == (float(TAIL_UM_PER_AMP), float(TAIL_L_UM))


def test_the_derived_tail_is_a_function_of_i_bias_alone():
    """Removing the degrees of freedom must not leave the tail free-floating."""
    a = C.sizing_from_u(np.full(C.N_ACTIONS, 0.5))
    b = C.sizing_from_u(np.full(C.N_ACTIONS, 0.5))
    assert a.w_tail_um == b.w_tail_um == pytest.approx(
        0.5 * a.params["i_bias"] * a.tail_j_um_per_a)
    # Two designs differing ONLY in i_bias must differ only in w_tail.
    i = C.ACTION_NAMES.index("i_bias")
    u2 = np.full(C.N_ACTIONS, 0.5); u2[i] = 0.9
    c = C.sizing_from_u(u2)
    assert c.l_tail_um == a.l_tail_um
    assert c.tail_j_um_per_a == a.tail_j_um_per_a
    assert c.w_tail_um != a.w_tail_um


def test_nf_in_is_fixed_and_inside_the_proposed_range():
    """G38: `nf` is +/-10 % NON-MONOTONIC on SKY130, so it is not an action."""
    from nebula.experiments.s3_yield import PROPOSED_BOX

    lo, hi, _, _ = PROPOSED_BOX["nf_in"]
    assert lo <= C.NF_IN_FIXED <= hi
    assert "nf_in" not in C.ACTION_NAMES
    assert "nf_tail" not in C.ACTION_NAMES


def test_cl_is_context_not_action():
    """Settled in task 2; G42 measured that searching it LOWERS the yield."""
    assert "cl" not in C.ACTION_NAMES
    from nebula.experiments.cl_range import committed_cl_range

    assert C.CL_CONTEXT_F == committed_cl_range().cl_mid_f


# ── normalisation round trips ───────────────────────────────────────────────

@pytest.mark.parametrize("d", C.ACTION_SPACE, ids=lambda d: d.name)
@pytest.mark.parametrize("u", [0.0, 0.25, 0.5, 0.75, 1.0])
def test_normalised_physical_round_trip(d, u):
    assert d.to_normalised(d.to_physical(u)) == pytest.approx(u, abs=1e-12)


@pytest.mark.parametrize("d", C.ACTION_SPACE, ids=lambda d: d.name)
def test_log_axes_are_geometric_and_linear_axes_arithmetic(d):
    """A delta of 0.1 means a fixed RATIO on a log axis, a fixed INCREMENT on a
    linear one. That invariance is why the metric column exists."""
    a, b = d.to_physical(0.3), d.to_physical(0.4)
    c, e = d.to_physical(0.6), d.to_physical(0.7)
    if d.log:
        assert b / a == pytest.approx(e / c, rel=1e-9)
    else:
        assert b - a == pytest.approx(e - c, rel=1e-9)


def test_out_of_range_normalised_input_is_clipped_not_rejected():
    """PPO's head puts mass outside [0,1] by construction (params.denormalize
    makes the same choice, for the same reason)."""
    d = C.ACTION_SPACE[0]
    assert d.to_physical(-5.0) == d.lo
    assert d.to_physical(+5.0) == d.hi


# ── f_peak in octaves ───────────────────────────────────────────────────────

def test_f_peak_octaves_is_relative_to_nyquist():
    assert C.f_peak_octaves(NYQUIST_HZ) == 0.0
    assert C.f_peak_octaves(NYQUIST_HZ / 2) == pytest.approx(-1.0)
    assert C.f_peak_octaves(NYQUIST_HZ * 2) == pytest.approx(+1.0)


def test_s3_window_is_exactly_one_octave_in_these_units():
    """The reason the unit is octaves at all, asserted rather than asserted-in-
    a-comment."""
    lo, hi = SPEC_F_PEAK_HZ_RANGE
    assert C.f_peak_octaves(hi) - C.f_peak_octaves(lo) == pytest.approx(1.0)


@pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), float("inf")])
def test_f_peak_octaves_refuses_a_non_frequency(bad):
    with pytest.raises(ValueError):
        C.f_peak_octaves(bad)


# ── the observation ─────────────────────────────────────────────────────────

def _meas(**over):
    m = {"g_dc_db": 6.0, "peaking_db": 7.2, "f_peak_oct": -0.5,
         "nyq_boost_db": 6.9, "inoise_vrms": 2.2e-4, "power_w": 6.0e-3,
         "pair_margin_v": 0.26, "tail_margin_v": 0.33}
    m.update(over)
    return m


def test_observation_width_matches_the_declared_contract():
    obs = C.build_observation([0.5] * C.N_ACTIONS, _meas(), 7.5, 1.7678e9, 0)
    assert obs.shape == (C.N_OBS,)
    assert C.N_OBS == C.N_ACTIONS + C.N_MEAS + C.N_TARGET + 1
    assert C.N_OBS == 18, "7 sizing + 8 measurement + 2 target + 1 step"


def test_the_measurement_block_still_carries_the_tail_margin():
    """The tail left the ACTION space, not the OBSERVATION. Its headroom is a
    consequence of `vcm_in`, `w_in`, `l_in` and `i_bias`, all of which the
    policy does move, so it is exactly the coupled feedback the observation
    exists to provide."""
    assert "tail_margin_v" in C.MEAS_NAMES


def test_observation_blocks_do_not_overlap_and_cover_everything():
    spans = [(a, b) for _, a, b in C.OBS_BLOCKS]
    covered = sorted(i for a, b in spans for i in range(a, b))
    assert covered == list(range(C.N_OBS))


def test_scales_are_the_spec_limits_they_claim_to_be():
    """`OBS_SCALES`'s `basis` strings must be true, not decorative."""
    by = {s.name: s for s in C.OBS_SCALES}
    assert by["inoise_vrms"].scale == SPEC_VN_IN_MAX_VRMS
    assert by["power_w"].scale == SPEC_POWER_MAX_W
    assert by["peaking_db"].centre == sum(SPEC_PEAKING_DB_RANGE) / 2.0
    assert by["nyq_boost_db"].scale == SPEC_PEAKING_DB_RANGE[1]


def test_normalisation_is_fixed_and_not_a_running_statistic():
    """The SAME measurement must normalise identically regardless of what came
    before it. A running normaliser makes the observation a function of the
    run's history, and then nothing reproduces."""
    a = C.normalise_measurements(_meas())
    for _ in range(50):
        C.normalise_measurements(_meas(peaking_db=float(np.random.rand() * 20)))
    b = C.normalise_measurements(_meas())
    assert np.array_equal(a, b)


def test_a_missing_measurement_channel_raises_rather_than_defaulting():
    """§6d: never a missing value, never a substituted default."""
    m = _meas()
    del m["tail_margin_v"]
    with pytest.raises(KeyError, match="tail_margin_v"):
        C.normalise_measurements(m)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_a_non_finite_measurement_raises(bad):
    """G54: `.noise` can return -nan(ind) and exit 0."""
    with pytest.raises(ValueError):
        C.normalise_measurements(_meas(inoise_vrms=bad))


def test_step_index_is_normalised_by_the_horizon():
    o0 = C.build_observation([0.5] * C.N_ACTIONS, _meas(), 7.5, 1.7678e9, 0)
    oh = C.build_observation([0.5] * C.N_ACTIONS, _meas(), 7.5, 1.7678e9,
                             C.HORIZON)
    assert o0[-1] == 0.0
    assert oh[-1] == 1.0


# ── sizing ──────────────────────────────────────────────────────────────────

def test_sizing_round_trips_through_u():
    u = np.linspace(0.1, 0.9, C.N_ACTIONS)
    s = C.sizing_from_u(u)
    assert np.allclose(u, C.u_from_params(s.params), atol=1e-12)


def test_u_from_params_takes_no_tail_arguments():
    """The old signature took two. A caller still passing them is calling the
    pre-Call-2 API and must be told, not silently ignored."""
    import inspect

    sig = inspect.signature(C.u_from_params)
    assert list(sig.parameters) == ["params"]


def test_sizing_fixes_nf_in_and_carries_the_context_load():
    s = C.sizing_from_u([0.5] * C.N_ACTIONS)
    assert s.params["nf_in"] == float(C.NF_IN_FIXED)
    assert s.params["cl"] == C.CL_CONTEXT_F


def test_w_tail_follows_i_bias_by_the_current_density_rule():
    """`w_tail = i_side * tail_j`. TAIL_DEVICE.md §3: holding the DENSITY is
    what holds vdsat, and `i_bias` spans 16x, so a fixed WIDTH could not."""
    u = np.full(C.N_ACTIONS, 0.5)
    s = C.sizing_from_u(u)
    assert s.w_tail_um == pytest.approx(
        0.5 * s.params["i_bias"] * s.tail_j_um_per_a)

    # Double the current at the same density and the width doubles.
    i = C.ACTION_NAMES.index("i_bias")
    u2 = u.copy()
    u2[i] = C.ACTION_SPACE[i].to_normalised(2.0 * s.params["i_bias"])
    s2 = C.sizing_from_u(u2)
    assert s2.w_tail_um == pytest.approx(2.0 * s.w_tail_um, rel=1e-9)
    assert s2.tail_j_um_per_a == pytest.approx(s.tail_j_um_per_a)


def test_nf_tail_is_derived_and_respects_the_per_finger_ceiling():
    """G53: the bin ceiling is on W PER FINGER, not on total width."""
    from nebula.device.tail import W_PER_FINGER_MAX_UM

    for ui in (0.0, 0.5, 1.0):
        u = np.full(C.N_ACTIONS, ui)
        s = C.sizing_from_u(u)
        assert s.w_tail_um / s.nf_tail <= W_PER_FINGER_MAX_UM
        assert s.nf_tail % int(C.TAIL_MIRROR_RATIO) == 0


# ── design_id ───────────────────────────────────────────────────────────────

def test_design_id_is_stable_and_distinguishes_designs():
    a = C.sizing_from_u([0.5] * C.N_ACTIONS)
    b = C.sizing_from_u([0.5] * C.N_ACTIONS)
    c = C.sizing_from_u([0.6] + [0.5] * (C.N_ACTIONS - 1))
    assert C.design_id(a) == C.design_id(b)
    assert C.design_id(a) != C.design_id(c)


def test_design_id_groups_by_realised_geometry_when_given_one():
    """Task 8's grouped train/test split needs two continuous values that
    quantise onto the SAME device to share an id — they are the same silicon."""
    a = C.sizing_from_u([0.5] * C.N_ACTIONS)
    assert C.design_id(a, "geomX") == C.design_id(a, "geomX")
    assert C.design_id(a, "geomX") != C.design_id(a, "geomY")
    assert C.design_id(a, "geomX") != C.design_id(a)
