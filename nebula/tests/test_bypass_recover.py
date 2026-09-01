"""
tests/test_bypass_recover.py — gates on `exp_unscorable` and
`exp_bypass_recover` (`PREDICTIONS.md` entry 54).

WHY EACH GUARD EXISTS
----------------------
1.  **The two unscorable verdicts must not be merged.** `exp_coverage._rescore`
    emits `UNSCORABLE` when the POINT never ran and `EYE_UNMEASURABLE` when the
    point ran and the LINK refused. The first version of `exp_unscorable`
    filtered on `ok` alone, saw only the first, and reported request 5 as
    "45 of 45 evaluable" while 8 of its corners carried no eye. Same shape as
    G115: a set built by testing the convenient flag loses members silently.
2.  **The invariance control must compare exactly, not approximately.** The
    claim entry 54 rests on is *bit-identical*, and a tolerance is precisely
    where a real drift caused by the raised bypass could hide.
3.  **A lost corner is as disqualifying as a changed one.** A bypass value that
    recovers one point while breaking another has changed the circuit, not
    cleared a singularity, so `identical` must be False when anything is lost.
4.  **Q1 must gate the later numbers in CODE.** Entry 54's decision rule says a
    failed control makes every coverage number inadmissible. Prose cannot
    enforce that: if the run writes them to disk anyway they can be quoted, so
    the gate is tested.
5.  **The bypass patch must be restored even when the wrapped call raises.** A
    leaked patch silently contaminates the control arm of any later call in the
    same process -- the one failure mode that would make the whole entry
    unfalsifiable.
6.  **A no-op wrapper must raise rather than pass.** If `build_point` returns a
    point with no tail there is no bypass to raise, and a silent no-op would
    report "raised bypass, same answer" as an invariance HIT.

No SPICE and no artifacts: every test builds its own points.
"""

from __future__ import annotations

import dataclasses

import pytest

from nebula.experiments import exp_bypass_recover as BR
from nebula.experiments import exp_unscorable as UN


# ─────────────────────────────────────────────────────────────────────────────
# exp_unscorable.classify — guard 1
# ─────────────────────────────────────────────────────────────────────────────

_COMP = ("output swing 1193.5 mVpp exceeds the linear limit 1191.5 mVpp "
         "(vout_swing_v=1191.5 mVpp). The stage is compressing, so the "
         "AC/pole-zero model behind every number in this DeviceResult no "
         "longer describes it")


def test_compression_reason_is_parsed_into_numbers():
    got = UN.classify(_COMP)
    assert got["kind"] == "compression"
    assert got["required_pp_mv"] == pytest.approx(1193.5)
    assert got["limit_pp_mv"] == pytest.approx(1191.5)
    assert got["ratio"] == pytest.approx(1193.5 / 1191.5)


def test_a_refusal_just_over_the_line_is_flagged_a_near_miss():
    assert UN.classify(_COMP)["near_miss"] is True


def test_a_refusal_far_over_the_line_is_not_a_near_miss():
    far = ("output swing 2400.0 mVpp exceeds the linear limit 800.0 mVpp "
           "(vout_swing_v=800.0 mVpp).")
    got = UN.classify(far)
    assert got["ratio"] == pytest.approx(3.0)
    assert got["near_miss"] is False


def test_the_nan_failure_is_classified_as_ngspice_not_compression():
    got = UN.classify("ngspice silent failure: inoise_total = -nan(ind)")
    assert got["kind"] == "ngspice"
    assert "ratio" not in got


def test_an_unrecognised_reason_keeps_its_text_and_is_never_bucketed():
    got = UN.classify("something nobody has seen before")
    assert got["kind"] == "other"
    assert got["reason"] == "something nobody has seen before"


def test_no_reason_is_its_own_kind():
    assert UN.classify(None)["kind"] == "none"


def test_near_miss_threshold_is_a_named_constant_not_a_literal():
    # It is registered in entry 54; a test that re-hardcodes it would let the
    # constant move without anything firing.
    assert UN.NEAR_MISS_RATIO == 1.05


# ─────────────────────────────────────────────────────────────────────────────
# exp_bypass_recover.compare — guards 2 and 3
# ─────────────────────────────────────────────────────────────────────────────

def _pt(corner="tt", vdd=1.0, temp=27.0, ok=True, vn=1.0e-4, g=2.0,
        f=2.0e9, reason=None):
    return {"corner": corner, "vdd_scale": vdd, "temp_c": temp, "ok": ok,
            "fail_reason": reason, "vn_in_vrms": vn, "g_dc_db": g,
            "f_pk_interp_hz": f}


def test_identical_arms_compare_clean():
    base = [_pt(), _pt(temp=0.0)]
    got = BR.compare(base, [dict(p) for p in base])
    assert got["identical"] is True
    assert got["n_differing"] == 0 and got["n_compared"] == 2


def test_a_recovered_corner_is_reported_and_does_not_break_invariance():
    base = [_pt(temp=0.0, ok=False, vn=None, g=None, f=None,
                reason="ngspice silent failure: inoise_total = -nan(ind)"),
            _pt()]
    raised = [_pt(temp=0.0), _pt()]
    got = BR.compare(base, raised)
    assert got["identical"] is True
    assert len(got["recovered"]) == 1
    assert got["recovered"][0]["corner"] == ("tt", 1.0, 0.0)
    # The point that never computed at baseline is NOT counted as compared.
    assert got["n_compared"] == 1


def test_a_field_that_moves_at_all_breaks_invariance():
    base = [_pt(vn=1.0e-4)]
    raised = [_pt(vn=1.0000001e-4)]
    got = BR.compare(base, raised)
    assert got["identical"] is False
    assert got["n_differing"] == 1
    assert "vn_in_vrms" in got["differing"][0]["fields"]


def test_invariance_is_exact_and_not_a_tolerance():
    # Guard 2. A relative difference of 1e-12 is far inside any tolerance
    # anyone would write, and must still fire.
    got = BR.compare([_pt(g=2.0)], [_pt(g=2.0 * (1 + 1e-12))])
    assert got["identical"] is False


def test_a_lost_corner_breaks_invariance():
    # Guard 3. Recovering one point while breaking another is a changed
    # circuit, not a cleared singularity.
    base = [_pt()]
    raised = [_pt(ok=False, reason="broke")]
    got = BR.compare(base, raised)
    assert got["identical"] is False
    assert len(got["lost"]) == 1


def test_a_grid_of_a_different_size_raises():
    with pytest.raises(ValueError, match="grid mismatch"):
        BR.compare([_pt()], [_pt(), _pt(temp=0.0)])


def test_corners_compared_out_of_order_raise_rather_than_pair_up():
    with pytest.raises(ValueError, match="corner order differs"):
        BR.compare([_pt(temp=0.0), _pt()], [_pt(), _pt(temp=0.0)])


# ─────────────────────────────────────────────────────────────────────────────
# exp_bypass_recover.analyse — guard 4
# ─────────────────────────────────────────────────────────────────────────────

def _artifact(*, n_pass_target=45, n_pass_null=37, recovered=True,
              vn_recovered=3.478e-4):
    base = [_pt(temp=0.0, ok=not recovered, vn=None if recovered else 3.5e-4,
                reason="ngspice silent failure: inoise_total = -nan(ind)"
                if recovered else None),
            _pt(temp=27.0, vn=3.731e-4), _pt(temp=125.0, vn=4.659e-4)]
    raised = [_pt(temp=0.0, vn=vn_recovered),
              _pt(temp=27.0, vn=3.731e-4), _pt(temp=125.0, vn=4.659e-4)]
    return {"entry40_coverage": 8,
            "invariance": BR.compare(base, raised),
            "baseline_points": base, "raised_points": raised,
            "n_nan_blocked_baseline": 1 if recovered else 0,
            "target": {"before": {"n_pvt45_pass": 44},
                       "after": {"n_pvt45_pass": n_pass_target}},
            "null": {"before": {"n_pvt45_pass": 37},
                     "after": {"n_pvt45_pass": n_pass_null}}}


def test_the_registered_outcome_scores_the_way_the_run_did():
    a = BR.analyse(_artifact())
    assert a["Q1_invariance"] and a["Q2_corner_computes"]
    assert a["Q3_coverage_9"] and a["Q5_null_holds"] and a["Q6_bounded_nuisance"]
    assert a["coverage_after"] == 9


def test_coverage_does_not_move_when_the_target_falls_short():
    a = BR.analyse(_artifact(n_pass_target=44))
    assert a["Q3_coverage_9"] is False
    assert a["coverage_after"] == 8


def test_the_null_moving_is_recorded_as_a_miss():
    # Q5 is a registered expected null: request 5 fails in the LINK, so a
    # device-side bypass moving it would mean the wrapper did something else.
    a = BR.analyse(_artifact(n_pass_null=40))
    assert a["Q5_null_holds"] is False


def test_a_failed_control_makes_the_run_inadmissible():
    # Guard 4, the prose half.
    d = _artifact()
    d["raised_points"][1] = _pt(temp=27.0, vn=9.9e-4)
    d["invariance"] = BR.compare(d["baseline_points"], d["raised_points"])
    a = BR.analyse(d)
    assert a["Q1_invariance"] is False
    assert a["admissible"] is False


def test_main_refuses_to_write_coverage_numbers_when_the_control_fails(
        monkeypatch, tmp_path):
    # Guard 4, the code half: the arms must not even RUN, so their numbers
    # cannot reach the artifact where they could be quoted.
    ran = []
    monkeypatch.setattr(BR, "RESULTS", tmp_path / "out.json")
    monkeypatch.setattr(BR, "_row", lambda i: {"index": i, "u": [0.5] * 7,
                                               "n_pvt45_pass": 44})
    monkeypatch.setattr(BR, "invariance_pass",
                        lambda row, c: [_pt(vn=1.0e-4 if c is None else 2.0e-4)])
    monkeypatch.setattr(BR, "rescore",
                        lambda *a, **k: ran.append(1) or {"n_pvt45_pass": 45})
    assert BR.main([]) == 1
    assert ran == []


# ─────────────────────────────────────────────────────────────────────────────
# _raised_bypass — guards 5 and 6
# ─────────────────────────────────────────────────────────────────────────────

@dataclasses.dataclass(frozen=True)
class _Tail:
    c_bypass_f: float = 10e-12


@dataclasses.dataclass(frozen=True)
class _Point:
    tail: object = None


def test_the_bypass_patch_raises_the_value_it_is_given():
    import nebula.experiments.exp_g4_verify as V

    real = V.build_point
    try:
        V.build_point = lambda sizing, **kw: (_Point(tail=_Tail()), None)
        with BR._raised_bypass(30e-12):
            pt, _ = V.build_point(None)
        assert pt.tail.c_bypass_f == pytest.approx(30e-12)
    finally:
        V.build_point = real


def test_the_patch_is_restored_even_when_the_body_raises():
    # Guard 5. A leaked patch contaminates the control arm of any later call.
    import nebula.experiments.exp_g4_verify as V

    before = V.build_point
    with pytest.raises(RuntimeError):
        with BR._raised_bypass(30e-12):
            raise RuntimeError("boom")
    assert V.build_point is before


def test_a_point_with_no_tail_raises_rather_than_silently_doing_nothing():
    # Guard 6. A no-op wrapper reports "same answer" as an invariance HIT.
    import nebula.experiments.exp_g4_verify as V

    real = V.build_point
    try:
        V.build_point = lambda sizing, **kw: (_Point(tail=None), None)
        with BR._raised_bypass(30e-12):
            with pytest.raises(ValueError, match="no tail"):
                V.build_point(None)
    finally:
        V.build_point = real


def test_the_raised_value_is_the_smallest_measured_to_clear_it():
    # Entry 54 declared 30 p / 100 p / 1 n as bit-identical and picked the
    # smallest; a silent bump would add capacitor area for nothing.
    assert BR.RAISED_BYPASS_F == 30e-12


def test_the_default_bypass_is_not_changed_by_this_experiment():
    # The whole entry rests on 10 pF remaining the published default.
    from nebula.device.tail import C_BYPASS_F, TailDevice

    assert C_BYPASS_F == 10e-12
    assert TailDevice(w_tail=100.0, l_tail=0.5, nf_tail=8).c_bypass_f == 10e-12
