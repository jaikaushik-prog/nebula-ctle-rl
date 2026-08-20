"""**Does the delivery screen actually predict the 135-point grid?**

Session 23. These tests are the evidence behind `adaptive_screen.EDGE4`, and
they run against the REAL artifacts rather than against a fixture, because the
claim being pinned is a claim about measured silicon behaviour:

    EDGE4 reproduces the full-135 worst case exactly, on every design this
    project has ever fully verified, using 4 SPICE runs where the legacy
    3-corner screen uses 6 -- and the legacy screen is off by up to +10.03,
    which is the entire scale of the reward.

No simulator is needed: every assertion reads `*_verify_full_results.json`.
Tests that would need ngspice are marked `slow` and are not part of the
1667-test default run.

Each gate was watched go red (rule 4): removing `sf` from `EDGE4` reddens the
predictiveness test, and inverting the comparison in `audit_screen` reddens
the self-check tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nebula.experiments.adaptive_screen import (
    EDGE4,
    MAX_SPREAD_OCT,
    SPREAD_PROBE,
    AdaptiveScreen,
    DesignEval,
    ScreenPoint,
    audit_screen,
)
from nebula.experiments.s9_yield import SCREEN_CORNERS

HERE = Path(__file__).resolve().parent
EXP = HERE.parent / "experiments"

ARTIFACTS = ("joint_verify_full_results.json", "g4_verify_full_results.json")

#: The legacy benchmark screen, as (corner, load) pairs: 3 corners x the two
#: outer loads. What every published search in this project is graded on.
LEGACY6 = [(c.process, round(c.vdd_scale, 2), float(c.temp_c), which)
           for which in ("lo", "hi") for c in SCREEN_CORNERS]


def _full_results():
    """Every fully-verified design on disk, as (design_id, points).

    Skips the nominal-only control: it fails everywhere by construction and
    is a measurement of a bad design rather than of a screen.
    """
    out = []
    for name in ARTIFACTS:
        p = EXP / name
        if not p.exists():
            continue
        for res in json.loads(p.read_text(encoding="utf-8"))["results"]:
            pts = res.get("points") or []
            if len(pts) < 130 or res.get("role") == "nominal_only":
                continue
            out.append((res["design_id"], pts))
    return out


def _key(p, lo, hi):
    which = ("lo" if abs(float(p["cl_f"]) - lo) < 1e-18
             else "hi" if abs(float(p["cl_f"]) - hi) < 1e-18 else "mid")
    return (p["corner"], round(float(p["vdd_scale"]), 2),
            float(p["temp_c"]), which)


def _edge4_keys(lo, hi):
    return [(sp.corner.process, round(sp.corner.vdd_scale, 2),
             float(sp.corner.temp_c),
             "lo" if abs(sp.cl_f - lo) < 1e-18 else "hi") for sp in EDGE4]


def test_there_ARE_fully_verified_designs_to_test_against():
    """A missing artifact must raise, not silently pass every test below."""
    assert _full_results(), (
        "no 135-point artifacts on disk: every claim in this file would "
        "vacuously pass. Run `exp_joint_search --verify` / `exp_g4_verify "
        "--full` before trusting a green run here")


def test_EDGE4_reproduces_the_full_grid_worst_case_EXACTLY():
    """THE claim. Four points, and the answer is the same as 135."""
    checked = 0
    for did, pts in _full_results():
        loads = sorted({float(p["cl_f"]) for p in pts})
        lo, hi = loads[0], loads[-1]
        want = set(_edge4_keys(lo, hi))
        sub = [float(p["reward"]) for p in pts if _key(p, lo, hi) in want]
        assert len(sub) == len(EDGE4), (
            f"{did}: EDGE4 selected {len(sub)} of {len(EDGE4)} points")
        full = min(float(p["reward"]) for p in pts)
        assert min(sub) == pytest.approx(full, abs=1e-9), (
            f"{did}: EDGE4 worst {min(sub):+.6f} != full-grid worst "
            f"{full:+.6f}")
        checked += 1
    assert checked >= 3, f"only {checked} designs available; claim needs 3+"


def test_the_LEGACY_screen_is_optimistic_and_that_is_the_whole_point():
    """It is not merely less accurate -- it calls an infeasible design feasible.

    A pessimistic screen wastes simulations. An optimistic one ships a design
    that does not work, which is what happened.
    """
    worst_error = 0.0
    called_feasible = 0
    for did, pts in _full_results():
        loads = sorted({float(p["cl_f"]) for p in pts})
        lo, hi = loads[0], loads[-1]
        want = set(LEGACY6)
        sub = [float(p["reward"]) for p in pts if _key(p, lo, hi) in want]
        if not sub:
            continue
        full = min(float(p["reward"]) for p in pts)
        err = min(sub) - full
        worst_error = max(worst_error, err)
        if full < 0.0 <= min(sub):
            called_feasible += 1
    assert worst_error > 0.01, (
        "the legacy screen no longer mis-predicts; EDGE4's justification has "
        "expired and this whole module should be re-argued")
    assert called_feasible >= 1, (
        "expected at least one design the legacy screen puts in the feasible "
        "band while the full grid says infeasible")


def test_EDGE4_is_CHEAPER_than_the_screen_it_replaces():
    """4 SPICE runs against 6. Cheaper AND correct is the argument."""
    assert len(EDGE4) == 4
    assert len(EDGE4) < len(LEGACY6)


def test_EDGE4_contains_BOTH_mixed_process_corners():
    """`sf` and `fs` are the extreme PASSIVE corners and the peak is an RC
    product. The legacy screen contains neither, which is the blind spot five
    independent measurements found before this one."""
    procs = {sp.corner.process for sp in EDGE4}
    assert "sf" in procs and "fs" in procs
    assert not ({"sf", "fs"} & {c.process for c in SCREEN_CORNERS}), (
        "the legacy screen has gained a mixed corner; this test's premise has "
        "changed and the EDGE4 argument needs re-checking")


def test_EDGE4_pairs_the_light_load_with_the_TOP_and_heavy_with_the_BOTTOM():
    """The saving is that these are PAIRS, not a cross product.

    Load is perfectly monotone in f_peak (135/135), so the top edge can only
    ever bind at the lightest load and the bottom edge at the heaviest. A
    5-corner x 2-load cross product would spend 10 runs to learn the same
    thing.
    """
    for sp in EDGE4:
        hot = sp.corner.temp_c >= 100.0
        heavy = sp.cl_f > 5e-14
        assert hot == heavy, (
            f"{sp.label}: hot corners must carry the HEAVY load and cold "
            f"corners the LIGHT one; this pair mixes the two edges")


def test_the_spread_probe_brackets_the_grid_and_is_a_SUBSET_of_the_screen():
    assert len(SPREAD_PROBE) == 2
    assert set(SPREAD_PROBE) <= set(EDGE4)
    a, b = SPREAD_PROBE
    assert {a.corner.process, b.corner.process} == {"sf", "fs"}


def test_the_spread_gate_leaves_real_room_in_S3s_one_octave_window():
    """S3's window is EXACTLY 1.000 octave. A gate at 1.0 admits designs whose
    best possible outcome is a 0-octave margin, which is what session 22u's
    winner was (0.99979 spread -> 0.00021 slack)."""
    assert 0.90 <= MAX_SPREAD_OCT < 1.0


# ── the self-check ───────────────────────────────────────────────────────────


def _fake_full(rewards):
    return [{"corner": "tt", "vdd_scale": 1.0, "temp_c": 27.0,
             "cl_f": 3.26e-14, "reward": r} for r in rewards]


def _eval(reward):
    return DesignEval(u=(0.5,) * 7, ok=True, reward=reward, feasible=reward > 0,
                      n_sims=4, n_points=4, n_scorable=4)


def test_audit_flags_an_OPTIMISTIC_screen_and_hands_back_the_point():
    a = audit_screen(_eval(+0.5), _fake_full([+2.0, -0.3, +1.0]))
    assert a.was_predictive is False
    assert a.full_worst == pytest.approx(-0.3)
    assert len(a.added) == 1, "an optimistic screen must yield a point to add"


def test_audit_accepts_a_PESSIMISTIC_screen_without_adding_anything():
    """Pessimism is safe: the search is being held to a harder standard than
    the truth, which costs margin, never correctness."""
    a = audit_screen(_eval(-1.0), _fake_full([+2.0, -0.3, +1.0]))
    assert a.was_predictive is True and not a.added


def test_audit_REFUSES_to_report_against_an_empty_grid():
    """Rule 5: a missing artifact raises; it does not get a placeholder."""
    with pytest.raises(ValueError):
        audit_screen(_eval(0.0), [])


def test_the_screen_GROWS_when_the_self_check_finds_a_miss():
    s = AdaptiveScreen()
    assert s.n_points == 4
    s.extend(audit_screen(_eval(+0.5), _fake_full([-0.3])))
    assert s.n_points == 5, "the found point was not added to the screen"
    assert s.n_predictive == 0


def test_the_screen_does_not_grow_TWICE_on_the_same_point():
    s = AdaptiveScreen()
    audit = audit_screen(_eval(+0.5), _fake_full([-0.3]))
    s.extend(audit)
    s.extend(audit)
    assert s.n_points == 5, "the same point was appended twice"


def test_a_clean_run_REPORTS_that_the_check_ran():
    """A run that never extends the screen is evidence FOR the screen, and is
    only evidence at all because the audit ran and is reported."""
    s = AdaptiveScreen()
    for _ in range(3):
        s.extend(audit_screen(_eval(-1.0), _fake_full([+2.0, +0.3])))
    rep = s.report()
    assert rep["n_audits"] == 3 and rep["n_predictive"] == 3
    assert rep["n_points"] == 4


def test_every_screen_point_carries_its_reason():
    """A corner in a screen with no stated reason is a guess nobody can audit."""
    for sp in EDGE4:
        assert len(sp.why) > 30, f"{sp.label} has no reasoning attached"
