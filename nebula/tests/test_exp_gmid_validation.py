"""
The gm/I_D validation experiment: the parts that must be right before the
numbers mean anything.

None of these need a simulator. What they pin is the experiment's HONESTY
rather than its result:

  * the design box is DERIVED from measured data and copies the device box's
    edges verbatim — CLAUDEwa.md §8 rule 6 forbids an agent choosing ranges,
    and rule 9 forbids re-typing an edge that already exists;
  * the mechanism buckets are the RL env's own, so the G44 counts are
    comparable with `RL_SMOKE.md`'s 159/28/16 by construction rather than by
    coincidence;
  * the two reason NAMESPACES do not get confused (a real bug, caught in
    development — see `test_map_rejections_are_not_bucketed_as_other`);
  * the analysis runs from the log with no simulator at all.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from nebula.experiments import exp_gmid_validation as X
from nebula.rl.contract import ACTION_SPACE
from nebula.rl.env import CtleSizingEnv


# ─────────────────────────────────────────────────────────────────────────────
# 1. The boxes.
# ─────────────────────────────────────────────────────────────────────────────


def test_design_box_has_the_same_dimension_as_the_action_space():
    assert len(X.design_box()) == len(ACTION_SPACE) == 7


def test_the_four_pass_through_edges_are_the_action_space_verbatim():
    """Rule 9: an edge that already exists is referenced, never re-typed.

    If these were copied by hand they would drift the first time the box moved,
    and the drift would look like an experimental result.
    """
    dev = {d.name: d for d in ACTION_SPACE}
    for d in X.design_box():
        if d.name in ("l_in", "i_bias", "rl", "vcm_in"):
            assert d.lo == dev[d.name].lo, d.name
            assert d.hi == dev[d.name].hi, d.name


def test_the_three_derived_edges_come_from_the_measured_csv():
    """Not chosen (rule 6): recomputed here from the same file, independently."""
    import csv

    gmid, kk, fz = [], [], []
    with X.CALIBRATION_CSV.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if str(row.get("tt_ok", "")).lower() not in ("true", "1"):
                continue
            try:
                gm, gmbs = float(row["gm"]), float(row["gmbs"])
                ib, rs, cs = (float(row["i_bias"]), float(row["rs"]),
                              float(row["cs"]))
            except (TypeError, ValueError, KeyError):
                continue
            if not all(map(math.isfinite, (gm, gmbs, ib, rs, cs))):
                continue
            gmid.append(gm / (0.5 * ib))
            kk.append(1.0 + (gm + gmbs) * rs / 2.0)
            fz.append(1.0 / (2 * math.pi * rs * cs))

    box = {d.name: d for d in X.design_box()}
    assert box["gm_over_id"].lo == pytest.approx(min(gmid))
    assert box["gm_over_id"].hi == pytest.approx(max(gmid))
    assert box["k"].lo == pytest.approx(min(kk))
    assert box["k"].hi == pytest.approx(max(kk))
    assert box["f_z"].lo == pytest.approx(min(fz))
    assert box["f_z"].hi == pytest.approx(max(fz))


def test_every_design_dimension_states_its_provenance():
    """A box edge with no provenance is a chosen number wearing a disguise."""
    for d in X.design_box():
        assert d.provenance and len(d.provenance) > 10, d.name


def test_k_box_starts_above_unity():
    """`k <= 1` has no `Rs`, so a sampler that could produce it would spend
    samples on requests the map must reject for arithmetic reasons."""
    box = {d.name: d for d in X.design_box()}
    assert box["k"].lo > 1.0


def test_log_axes_are_the_ones_that_span_decades():
    box = {d.name: d for d in X.design_box()}
    for name in ("f_z", "i_bias", "rl", "l_in", "k"):
        assert box[name].log, f"{name} spans decades and must be log-sampled"
    for name in ("gm_over_id", "vcm_in"):
        assert not box[name].log


def test_to_physical_hits_both_edges_exactly():
    for d in X.design_box():
        assert d.to_physical(0.0) == pytest.approx(d.lo)
        assert d.to_physical(1.0) == pytest.approx(d.hi)


# ─────────────────────────────────────────────────────────────────────────────
# 2. The mechanism buckets — the rule-9 pin.
# ─────────────────────────────────────────────────────────────────────────────


def test_mechanism_names_match_the_env():
    """THE COMPARISON'S FOUNDATION.

    `RL_SMOKE.md`'s 159 `peak_is_sweep_edge` / 28 `tail_triode` / 16
    `pair_triode` histogram was produced by `CtleSizingEnv._classify`. If this
    experiment bucketed differently, the comparison against it would be wrong
    by an amount nobody could see. So it calls the env's own table, and this
    test proves the call still resolves to the same answers.
    """
    cases = {
        "the reported peak IS the sweep edge: f_pk = 19.95e9": "peak_is_sweep_edge",
        "input pair is in triode: vds 0.01 < vdsat 0.20": "pair_triode",
        "tail is in triode: vds_tail 0.02 < vdsat_tail 0.15": "tail_triode",
        "unrealisable geometry: target below the poly floor": "unrealisable_geometry",
        "ngspice: singular matrix": "ngspice",
    }
    for reason, want in cases.items():
        assert X.classify_reason(reason) == want, reason
        assert CtleSizingEnv._classify(None, reason) == want, reason


def test_map_rejections_are_not_bucketed_as_other():
    """TWO REASON NAMESPACES, AND CONFUSING THEM ERASES A COLUMN.

    `design_space`'s failures (`current_unreachable`, `rs_outside_box`, ...)
    are not in the env's mechanism table. A first version fed them to
    `classify_reason` and every one came back "other", which silently deleted
    the most interesting result in the experiment — what the map rejects for
    free, and why.
    """
    for reason in ("current_unreachable: I_D=5 mA at gm/I_D=10 needs W outside",
                   "rs_outside_box: 1420 not in [50, 1000]",
                   "cs_outside_box: 4.1e-11 not in [1e-13, 1e-11]",
                   "source_node_outside_table: V_sb=-0.02 V implied by",
                   "bias_no_convergence: |dV_sb| still above 0.0002"):
        key = X._map_reason_key(reason)
        assert key == reason.split(":")[0]
        assert key != "other"
        # ... and the env's table would indeed have lost it.
        assert X.classify_reason(reason) == "other"


# ─────────────────────────────────────────────────────────────────────────────
# 3. The sampler.
# ─────────────────────────────────────────────────────────────────────────────


def test_lhs_is_a_latin_hypercube():
    rng = np.random.default_rng(7)
    n, d = 200, 7
    u = X._lhs(n, d, rng)
    assert u.shape == (n, d)
    assert u.min() >= 0.0 and u.max() <= 1.0
    # Exactly one sample per stratum, per dimension — that is what makes it a
    # Latin hypercube rather than uniform sampling.
    for j in range(d):
        strata = np.floor(u[:, j] * n).astype(int)
        assert len(set(strata)) == n


def test_lhs_is_reproducible_from_the_seed():
    a = X._lhs(50, 7, np.random.default_rng(3))
    b = X._lhs(50, 7, np.random.default_rng(3))
    np.testing.assert_array_equal(a, b)


# ─────────────────────────────────────────────────────────────────────────────
# 4. The analysis runs with no simulator.
# ─────────────────────────────────────────────────────────────────────────────


def _tiny_log(tmp_path: Path) -> Path:
    """A hand-built log with a known answer, so the arithmetic can be checked."""
    p = tmp_path / "tiny.jsonl"
    header = {
        "row": "header", "n_per_arm": 4, "seed": 1, "corner": "tt",
        "temp_c": 27.0, "cl_f": 32.63e-15, "vdd_v": 1.8, "nf_in": 4,
        "k_alpha": 1.0, "mirror_efficiency": 1.0, "lut": "x.npz",
        "lut_provenance": {}, "device_box": {}, "design_box": [],
        "context_not_control": {
            "source": "RL_SMOKE.md", "n_evaluations": X.SMOKE_N_EVALUATIONS,
            "invalid_rate": X.SMOKE_INVALID_RATE,
            "g44_share_of_invalid": X.SMOKE_G44_SHARE},
    }
    rows = [header]
    # device arm: 2 valid, 2 invalid (both G44)
    for i in range(2):
        rows.append({"arm": "device", "i": i, "verdict": "valid",
                     "mechanism": "", "reason": None})
    for i in range(2, 4):
        rows.append({"arm": "device", "i": i, "verdict": "invalid",
                     "mechanism": "peak_is_sweep_edge",
                     "reason": "the reported peak IS the sweep edge"})
    # design arm: 2 rejected by the map, 1 valid, 1 G44
    for i in range(2):
        rows.append({"arm": "design", "i": i, "verdict": "map_rejected",
                     "reason": "current_unreachable: ...", "pred_has_peak": True})
    rows.append({"arm": "design", "i": 2, "verdict": "valid", "mechanism": "",
                 "reason": None, "pred_has_peak": True,
                 "meas_f_pk_hz": 2.0e9, "pred_f_peak_hz": 2.0e9,
                 "meas_peaking_db": 6.0, "pred_peaking_db": 7.0,
                 "meas_g_dc_db": 0.0, "req_a_dc_linear": 1.0,
                 "req_f_z_hz": 1.0e9})
    rows.append({"arm": "design", "i": 3, "verdict": "invalid",
                 "mechanism": "peak_is_sweep_edge",
                 "reason": "the reported peak IS the sweep edge",
                 "pred_has_peak": False})
    rows.append({"row": "footer", "spice_invocations": 6})
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return p


def test_analysis_runs_from_a_log_with_no_simulator(tmp_path):
    res = X.analyse(_tiny_log(tmp_path))
    d, g = res["arms"]["device"], res["arms"]["design"]

    assert d["n_proposed"] == 4 and d["n_simulated"] == 4
    assert d["n_rejected_by_map"] == 0
    assert d["invalid_rate"] == pytest.approx(0.5)
    assert d["g44_count"] == 2
    assert d["g44_rate_of_proposed"] == pytest.approx(0.5)

    assert g["n_proposed"] == 4 and g["n_simulated"] == 2
    assert g["n_rejected_by_map"] == 2
    assert g["free_rejection_rate"] == pytest.approx(0.5)
    assert g["g44_count"] == 1
    # 1 of 4 PROPOSED, not 1 of 2 simulated — the honest comparison.
    assert g["g44_rate_of_proposed"] == pytest.approx(0.25)
    assert g["g44_rate_of_simulated"] == pytest.approx(0.5)
    assert g["map_reject_reasons"] == {"current_unreachable": 2}


def test_simulations_per_valid_prices_both_kinds_of_waste(tmp_path):
    """The two arms waste differently, and only this metric prices both.

    Device arm: 4 simulated, 2 valid -> 2.00 simulations per usable design.
    Design arm: 2 simulated (2 rejected for free), 1 valid -> 2.00.
    Equal here BY CONSTRUCTION of the fixture, which is the point: the metric
    does not flatter the arm that rejects more, it charges only for
    simulations actually spent.
    """
    res = X.analyse(_tiny_log(tmp_path))
    assert res["arms"]["device"]["sims_per_valid"] == pytest.approx(2.0)
    assert res["arms"]["design"]["sims_per_valid"] == pytest.approx(2.0)


def test_sims_per_valid_is_infinite_when_nothing_was_valid(tmp_path):
    """An arm that never produced a usable design must not report a finite
    cost per design — that would read as a good score."""
    p = tmp_path / "novalid.jsonl"
    rows = [{"row": "header", "n_per_arm": 1, "seed": 0, "corner": "tt",
             "temp_c": 27.0, "cl_f": 1e-14, "vdd_v": 1.8, "nf_in": 4,
             "k_alpha": 1.0, "mirror_efficiency": 1.0, "lut": "x",
             "lut_provenance": {}, "device_box": {}, "design_box": [],
             "context_not_control": {"source": "s", "n_evaluations": 1,
                                     "invalid_rate": 0.0,
                                     "g44_share_of_invalid": 0.0}},
            {"arm": "device", "i": 0, "verdict": "invalid",
             "mechanism": "peak_is_sweep_edge", "reason": "x"},
            {"arm": "design", "i": 0, "verdict": "invalid",
             "mechanism": "peak_is_sweep_edge", "reason": "x"},
            {"row": "footer", "spice_invocations": 2}]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    res = X.analyse(p)
    assert math.isinf(res["arms"]["device"]["sims_per_valid"])
    assert math.isinf(res["arms"]["design"]["sims_per_valid"])


def test_the_peak_predictor_confusion_matrix_is_counted_correctly(tmp_path):
    """One TP (predicted peak, measured peak) and one TN (predicted no peak,
    measured sweep edge). The map-rejected rows must NOT be counted: they were
    never simulated, so there is no measurement to be right or wrong about."""
    p = X.analyse(_tiny_log(tmp_path))["peak_predictor"]
    assert p["n"] == 2
    assert (p["tp"], p["fp"], p["tn"], p["fn"]) == (1, 0, 1, 0)
    assert p["accuracy"] == pytest.approx(1.0)


def test_accuracy_uses_valid_rows_only(tmp_path):
    """A HEADROOM_ONLY or INVALID row has no trustworthy AC spec set
    (`rl/evaluator.py`), so comparing a request against it would be comparing
    against a number the evaluator has already said not to believe."""
    a = X.analyse(_tiny_log(tmp_path))["accuracy"]
    assert a["n_valid_design_rows"] == 1
    assert a["peaking_error_db"] == [pytest.approx(-1.0)]
    assert a["f_peak_error_octaves"] == [pytest.approx(0.0)]
    assert a["g_dc_error_db"] == [pytest.approx(0.0)]


def test_printing_the_analysis_does_not_raise(tmp_path, capsys):
    X.print_analysis(X.analyse(_tiny_log(tmp_path)))
    out = capsys.readouterr().out
    assert "the honest comparison" in out
    assert "CONTEXT (not the control)" in out
    # G10: the Windows console is cp1252 — no non-ASCII may reach print().
    out.encode("cp1252")


# ─────────────────────────────────────────────────────────────────────────────
# 5. The quoted context must match its source.
# ─────────────────────────────────────────────────────────────────────────────


def test_the_smoke_run_context_numbers_match_RL_SMOKE_md():
    """These are quoted in the write-up, so they get a test rather than a
    comment. `RL_SMOKE.md` §5: 203/765 invalid, 159 of them G44."""
    assert X.SMOKE_N_EVALUATIONS == 765
    assert X.SMOKE_INVALID_RATE == pytest.approx(203 / 765)
    assert X.SMOKE_INVALID_RATE == pytest.approx(0.2654, abs=5e-5)
    assert X.SMOKE_G44_SHARE == pytest.approx(159 / 203)
    assert X.SMOKE_G44_SHARE == pytest.approx(0.7833, abs=5e-5)


def test_the_context_is_labelled_as_context_not_as_a_control(tmp_path, capsys):
    """The smoke run used a POLICY's proposals; this experiment uses LHS.
    Presenting one as the other's control would be G71's error one layer up."""
    X.print_analysis(X.analyse(_tiny_log(tmp_path)))
    out = capsys.readouterr().out
    assert "Different SAMPLER" in out
