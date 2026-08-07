"""
Tests for `experiments/prescreen.py` — task 7e's analytic pre-screen.

Two of these are GATES rather than unit tests, in CLAUDEwa.md §8 rule 10's
sense: they exist to fail if someone edits a constant by hand.

  * `test_stored_coefficients_reproduce_a_refit` fails if `GM_LOG_BETA` drifts
    from what the tracked CSV actually fits.
  * `test_margins_follow_the_stated_rule` fails if `MARGIN_OCT`/`MARGIN_DB` are
    not the smallest pair on the published ladder meeting the declared
    false-rejection budget — i.e. it enforces that the widening was set BY A
    RULE and not chosen, which is CLAUDEwa.md §8 rule 6.

None of them runs ngspice: the whole point of the pre-screen is that it costs
no simulations, so its tests cost none either.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from nebula.common.types import SPEC_F_PEAK_HZ_RANGE, SPEC_PEAKING_DB_RANGE
from nebula.device.passives import to_geometry
from nebula.experiments import prescreen as PS
from nebula.experiments.rl_smoke import DESIGN_432


# ─────────────────────────────────────────────────────────────────────────────
# Calibration: the stored constants must be what the data says.
# ─────────────────────────────────────────────────────────────────────────────


def test_stored_coefficients_reproduce_a_refit():
    beta, bb = PS.fit_gm_model()
    assert np.allclose(beta, PS.GM_LOG_BETA, rtol=1e-9, atol=1e-12), (
        "GM_LOG_BETA does not match a refit of robust_geometry_data.csv. "
        "Either the CSV changed or the constant was hand-edited; a stored "
        "coefficient nobody can reproduce is a fabricated number (rule 1)."
    )
    assert np.allclose(bb, PS.GMBS_RATIO_BETA, rtol=1e-9, atol=1e-12)


def test_calibration_csv_is_the_tracked_one():
    assert PS.CALIBRATION_CSV.exists()
    # G49: the file a published number came from is an INPUT, not an artifact.
    assert PS.CALIBRATION_CSV.name == "robust_geometry_data.csv"


# ─────────────────────────────────────────────────────────────────────────────
# The prediction itself.
# ─────────────────────────────────────────────────────────────────────────────


def test_f_zero_and_f_pole2_are_exact_functions_of_the_passives():
    """The two poles that need no device quantity must be EXACT.

    This is the claim the module's docstring makes about why two thirds of the
    prediction cannot be wrong, so it is pinned rather than asserted in prose.
    """
    p = dict(DESIGN_432)
    pred = PS.predict_response(p, drawn=True)
    geo = to_geometry(p["rs"], p["cs"], p["rl"])
    fz = 1.0 / (2 * math.pi * geo.rs.r_actual_ohm * geo.cs.c_actual_f)
    cl_eff = p["cl"] + 0.5 * geo.rl.parasitic_to_bulk_f()
    fp2 = 1.0 / (2 * math.pi * geo.rl.r_actual_ohm * cl_eff)
    assert pred.f_zero_hz == pytest.approx(fz, rel=1e-12)
    assert pred.f_pole2_hz == pytest.approx(fp2, rel=1e-12)


def test_drawn_passives_are_used_and_move_the_answer():
    """G66's mechanism must be IN the predictor, not a caveat next to it."""
    p = dict(DESIGN_432)
    drawn = PS.predict_response(p, drawn=True)
    ideal = PS.predict_response(p, drawn=False)
    assert drawn.f_pole2_hz < ideal.f_pole2_hz, (
        "the drawn load resistor's res_po bottom plate adds to cl, so f_p2 "
        "must come DOWN. Session 17 measured +1.4 to +24.3 fF on a 32.6 fF cl."
    )


def test_k_alpha_one_is_section_6_verbatim():
    """`K_ALPHA = 1.0` must reproduce CLAUDEwa.md §6's k exactly.

    The calibration is a correction TO a published equation, so the
    uncalibrated form has to still be reachable — otherwise nobody can check
    the transcription, which is the same argument `design_equations.predict`
    makes for defaulting `gmbs` to 0.
    """
    p = dict(DESIGN_432)
    pred = PS._predict_with_alpha(p, 1.0)
    geo = to_geometry(p["rs"], p["cs"], p["rl"])
    gm, gmbs = PS.predict_gm(p)
    assert pred.k_eff == pytest.approx(
        1.0 + (gm + gmbs) * geo.rs.r_actual_ohm / 2.0, rel=1e-12)


def test_the_peak_is_computed_not_assumed():
    """7e: use the full zero-and-two-pole expression, not an asymptote.

    Session 10b's "the peak sits near f_p2" is a recorded MISS
    (`PREDICTIONS.md`), so a predictor that returned f_p2 would be repeating a
    falsified assumption. It must also not return the asymptotic 20 log10(k).
    """
    p = dict(DESIGN_432)
    pred = PS.predict_response(p)
    assert pred.f_peak_hz != pytest.approx(pred.f_pole2_hz, rel=1e-3)
    asymptote = 20.0 * math.log10(pred.k_eff)
    assert pred.peaking_db < asymptote, (
        "the realised peaking is always BELOW 20 log10(k) because the load "
        "pole erodes it (session 9c, HANDOFF §12)"
    )


def test_prediction_rejects_a_non_positive_frequency():
    with pytest.raises(ValueError):
        PS.predict_response({"rs": 300.0, "cs": 1e-12, "rl": 500.0,
                             "cl": 0.0, "w_in": 40e-6, "l_in": 0.3e-6,
                             "nf_in": 4.0, "i_bias": 3e-3}, drawn=False)


# ─────────────────────────────────────────────────────────────────────────────
# The screen.
# ─────────────────────────────────────────────────────────────────────────────


def test_screen_accepts_the_known_good_design():
    """Design 432 meets S3 and is the sole load-robust survivor. If the screen
    rejects it, the screen is broken in the one way that matters."""
    v = PS.screen(dict(DESIGN_432))
    assert v.accept, v.reason


def test_screen_rejects_an_unrealisable_geometry_by_name():
    p = dict(DESIGN_432, rs=1e-6)          # below the poly head-resistance floor
    v = PS.screen(p)
    assert not v.accept
    assert v.reason is not None and v.reason.startswith("unrealisable_geometry")


def test_screen_rejects_a_design_with_no_peak_in_the_window():
    """`rs` at the box floor gives 0.165 dB of peaking -- a wire with gain."""
    v = PS.screen(dict(DESIGN_432, rs=50.0))
    assert not v.accept
    assert v.reason is not None and v.reason.startswith("predicted_peaking")


def test_screen_never_raises_on_anything_inside_the_box():
    """A screen that raises is a screen that stops a run (CLAUDEwa.md §8 r2)."""
    from nebula.rl.contract import sizing_from_u, N_ACTIONS

    rng = np.random.default_rng(7)
    for _ in range(200):
        s = sizing_from_u(rng.uniform(0.0, 1.0, N_ACTIONS))
        PS.screen(s.params)                # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# The gates: the operating point was chosen by a rule, and the rule holds.
# ─────────────────────────────────────────────────────────────────────────────


def test_margins_follow_the_stated_rule():
    """`MARGIN_*` is the SMALLEST ladder pair meeting the false-rejection budget.

    CLAUDEwa.md §8 rule 6 forbids an agent choosing a spec-tightness heuristic.
    The defence is that the value follows from a declared cost, so this test
    re-derives it. It fails if the constants are widened, tightened, or if the
    predictor changes enough to move which rung qualifies.
    """
    scan = PS.margin_scan()
    ok = [m for m in scan
          if m["false_rejection_rate"] <= PS.FALSE_REJECTION_BUDGET]
    assert ok, "no widening on the ladder meets the false-rejection budget"
    chosen = min(ok, key=lambda m: (m["margin_oct"], m["margin_db"]))
    assert (chosen["margin_oct"], chosen["margin_db"]) == \
        (PS.MARGIN_OCT, PS.MARGIN_DB), (
        f"MARGIN_OCT/MARGIN_DB = {(PS.MARGIN_OCT, PS.MARGIN_DB)} but the rule "
        f"picks {(chosen['margin_oct'], chosen['margin_db'])}"
    )


def test_false_rejection_is_inside_its_declared_budget():
    r = PS.accuracy()
    assert r["false_rejection_rate"] <= PS.FALSE_REJECTION_BUDGET, (
        "a screen that discards feasible designs is worse than no screen (7e)"
    )


def test_measured_accuracy_is_pinned():
    """A regression pin on 7e's published numbers.

    Tolerances are loose enough to survive a re-fit that moves a coefficient in
    the last digits and tight enough that a real change in the predictor fails
    them. These are the numbers `BASELINES.md` quotes.
    """
    r = PS.accuracy()
    assert r["n"] == 1890
    assert r["n_interior_peak"] == 1311
    assert r["f_peak_mdape_global"] == pytest.approx(0.0493, abs=0.003)
    assert r["f_peak_mdape_band"] == pytest.approx(0.0480, abs=0.003)
    assert r["free_rejection_rate"] == pytest.approx(0.617, abs=0.02)
    assert r["s3_base_rate"] == pytest.approx(0.1344, abs=0.002)
    assert r["effective_yield"] == pytest.approx(0.349, abs=0.02)
    assert r["g44_free_rejection_rate"] == pytest.approx(0.843, abs=0.02)


def test_the_loud_verdict_does_not_fire_and_the_test_says_which_way():
    """7e's threshold, pinned in BOTH directions.

    If a future change pushes the effective yield above 50 % this test fails,
    which is the point: that outcome has to be reported loudly in HANDOFF.md
    and cannot be allowed to slip in as a silently-updated number.
    """
    r = PS.accuracy()
    assert r["effective_yield"] <= 0.50, (
        "7e: if the pre-screen raises the effective yield above ~50 %, say so "
        "LOUDLY in the summary and in HANDOFF.md -- it would mean physics "
        "largely solves the nominal problem and the RL contribution must rest "
        "entirely on amortisation across spec targets."
    )
    assert r["yield_lift"] > 2.0, "and it is still a real saving, not nothing"


def test_zero_widening_would_clear_the_threshold_but_costs_feasible_designs():
    """The nuance that must travel with the headline, pinned so it cannot be
    dropped from a summary: the screen CAN clear 50 %, at a price."""
    zero = [m for m in PS.margin_scan()
            if m["margin_oct"] == 0.0 and m["margin_db"] == 0.0][0]
    assert zero["effective_yield"] > 0.50
    assert zero["false_rejection_rate"] > 0.10


def test_alpha_scan_shows_the_uncalibrated_equation_is_biased():
    """G60's direction, reproduced on this population."""
    scan = {round(a["k_alpha"], 3): a for a in PS.alpha_scan((0.90, 1.00))}
    assert scan[0.9]["peaking_bias_db"] == pytest.approx(0.0, abs=0.05)
    assert scan[1.0]["peaking_bias_db"] > 0.15, (
        "§6 verbatim must still over-predict the boost -- that is G60"
    )


# ─────────────────────────────────────────────────────────────────────────────
# The transfer test: does the TT calibration hold at benchmark conditions?
# ─────────────────────────────────────────────────────────────────────────────


def test_transfer_to_benchmark_conditions_is_measured_and_recorded():
    """`PREDICTIONS.md` entry 6, falsification condition 2 — and it FIRED.

    The calibration set sits at cl = 150 fF with nf_in varying and ideal R/C;
    the benchmark runs nf_in = 4 at cl_mid with drawn passives and a real
    mirror. The population-level rates transfer and the predictor's ACCURACY
    does not. This test pins the measured gap so it cannot quietly close or
    quietly widen without someone noticing.
    """
    from pathlib import Path

    log = Path(PS.__file__).parent / "baselines_pilot.jsonl"
    if not log.exists():                       # pragma: no cover
        pytest.skip("no pilot log in this checkout")
    r = PS.accuracy_from_log(log)
    # Transfers:
    assert r["free_rejection_rate"] == pytest.approx(0.639, abs=0.05)
    assert r["yield_lift"] == pytest.approx(2.66, abs=0.3)
    # Does NOT transfer, and the test says so in both directions:
    assert r["f_peak_mdape_global"] > 0.10, (
        "the predictor was 4.93 % on the calibration set and 15.85 % here; if "
        "this ever drops below 10 % the re-fit in BASELINES.md sec 12 item 1 "
        "has happened and that file needs updating"
    )
    assert r["peaking_bias_db"] > 0.15, (
        "the +0.36 dB bias is the ideal-tail gm model meeting a real mirror "
        "that delivers 4-8 % less current (session 13)"
    )
    assert not r["within_budget"], (
        "the screen breaches its own 1 % false-rejection budget at benchmark "
        "conditions (3.88 %); if that is fixed, say so in BASELINES.md"
    )
