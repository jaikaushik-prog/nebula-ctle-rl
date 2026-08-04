"""
Tests for the §6 cross-check gate (`nebula/device/crosscheck.py`).

These run against **captured real ngspice output**, checked into
`nebula/tests/fixtures/`, so the suite needs no simulator and stays sub-second
while still testing the actual parser against actual text.

Three fixtures, each earning its place:

  g1_bsim4_tt.out
      The G1 hand-design at TT, generic BSIM4 130nm, VDD=1.2 V, AFTER the
      `.control` derived-arithmetic block was removed. Clean.

  g1_sky130_tt.out
      The same topology on the real SKY130 PDK (open_pdks/volare), VDD=1.8 V.
      A different device model entirely — which is what makes it worth having:
      it confirms the body-effect finding independently.

  g1_bsim4_broken_control_block.out
      The historical failure. The exact output the netlist produced while its
      §6 cross-check was reported as passing and was in fact computing
      nothing. ngspice exited 0 on this. Kept so the scanner is tested against
      the real thing rather than a hand-written imitation.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from nebula.device.crosscheck import (
    CrossCheckFailure,
    SilentFailure,
    assert_no_silent_failures,
    check_all,
    cross_check_ngspice_output,
    derived_ac,
    find_device_scalar,
    in_saturation,
    overdrive_v,
    parse_meas,
    power_w,
    scan_for_silent_failures,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8", errors="replace")


@pytest.fixture(scope="module")
def bsim4() -> str:
    return _load("g1_bsim4_tt.out")


@pytest.fixture(scope="module")
def sky130() -> str:
    return _load("g1_sky130_tt.out")


@pytest.fixture(scope="module")
def broken() -> str:
    return _load("g1_bsim4_broken_control_block.out")


# The netlist constants each fixture was generated with. If a fixture is
# regenerated with different values, these must move with it.
BSIM4_RS, BSIM4_RL = 800.0, 120.0
BSIM4_VDD, BSIM4_ITAIL = 1.2, 5e-3
SKY130_RS, SKY130_RL = 800.0, 200.0


# ─────────────────────────────────────────────────────────────────────────────
# The scanner. This is the G26 defence.
# ─────────────────────────────────────────────────────────────────────────────


def test_scanner_catches_the_historical_silent_failure(broken: str) -> None:
    """The run that exited 0 while computing nothing must be caught."""
    offenders = scan_for_silent_failures(broken)
    assert offenders, (
        "the scanner missed the exact output that fooled us once — this "
        "fixture is a real ngspice run that returned exit code 0"
    )
    # Both failure shapes documented in G26/G30 are present in that output.
    assert any("not available or has zero length" in o for o in offenders)
    assert any(o.startswith("Error") for o in offenders)


def test_scanner_is_clean_on_the_fixed_netlists(bsim4: str, sky130: str) -> None:
    assert scan_for_silent_failures(bsim4) == []
    assert scan_for_silent_failures(sky130) == []
    assert_no_silent_failures(bsim4)
    assert_no_silent_failures(sky130)


def test_sky130_benign_warnings_are_not_flagged(sky130: str) -> None:
    """SKY130 prints conductance-reset warnings for every device.

    They are noise, not failures. If they were flagged, the scanner would cry
    wolf on every PDK run and get switched off — which is how a real gate dies.
    """
    assert "conductance reset to" in sky130
    assert scan_for_silent_failures(sky130) == []


def test_crosscheck_refuses_to_run_on_a_dirty_output(broken: str) -> None:
    with pytest.raises(SilentFailure):
        cross_check_ngspice_output(broken, rs=BSIM4_RS, rl=BSIM4_RL,
                                   g_dc_meas_name="gain_dc_db")


# ─────────────────────────────────────────────────────────────────────────────
# Parsing primitives.
# ─────────────────────────────────────────────────────────────────────────────


def test_parses_plain_device_reference(bsim4: str) -> None:
    assert find_device_scalar(bsim4, "gm") == pytest.approx(1.097342e-02)
    assert find_device_scalar(bsim4, "gmbs") == pytest.approx(3.582543e-03)


def test_parses_subckt_qualified_device_reference(sky130: str) -> None:
    """sky130 devices print as `@m.xm1.msky130_fd_pr__nfet_01v8[gm]`.

    Callers must not have to know which model family produced the output.
    """
    assert find_device_scalar(sky130, "gm") == pytest.approx(2.647756e-03)
    assert find_device_scalar(sky130, "gmbs") == pytest.approx(1.049598e-03)


def test_parses_meas_with_and_without_at(bsim4: str) -> None:
    dc, at_dc = parse_meas(bsim4, "gain_dc_db")
    assert dc == pytest.approx(-14.56892, abs=1e-4)
    assert at_dc is None, "a FIND measurement has no at= field"

    pk, at_pk = parse_meas(bsim4, "gain_peak_db")
    assert pk == pytest.approx(-6.279118, abs=1e-4)
    assert at_pk == pytest.approx(1.258925e9, rel=1e-6)


def test_missing_primitive_is_an_error_not_a_default() -> None:
    """CLAUDEwa.md §8 rule 1: unknown values fail loudly, they never default."""
    text = "@m1[gm] = 1.0e-02\ngain_dc_db = -14.0\n"  # no gmbs
    with pytest.raises(ValueError, match="gmbs"):
        cross_check_ngspice_output(text, rs=BSIM4_RS, rl=BSIM4_RL,
                                   g_dc_meas_name="gain_dc_db")


# ─────────────────────────────────────────────────────────────────────────────
# The gate, on real output.
# ─────────────────────────────────────────────────────────────────────────────


def test_gate_passes_on_the_g1_reference_point(bsim4: str) -> None:
    r = cross_check_ngspice_output(bsim4, rs=BSIM4_RS, rl=BSIM4_RL,
                                   g_dc_meas_name="gain_dc_db")
    assert r.passed
    assert r.disagreement_db < 1.0
    # Pins the numbers HANDOFF §2 quotes, so a silent model-card change
    # (this fixture already caught one — a missing k2) shows up as a failure.
    assert r.gm == pytest.approx(10.97342e-3, rel=1e-4)
    assert r.gmbs == pytest.approx(3.582543e-3, rel=1e-4)
    assert r.gmbs_over_gm == pytest.approx(0.3265, abs=5e-4)
    assert r.simulated_g_dc_db == pytest.approx(-14.569, abs=1e-3)
    assert r.predicted_g_dc_db == pytest.approx(-14.29, abs=0.02)
    assert r.disagreement_db == pytest.approx(0.28, abs=0.02)


def test_gate_passes_on_the_real_sky130_pdk(sky130: str) -> None:
    """Independent confirmation on a completely different device model."""
    r = cross_check_ngspice_output(sky130, rs=SKY130_RS, rl=SKY130_RL)
    assert r.passed
    assert r.gmbs_over_gm == pytest.approx(0.396, abs=2e-3)
    assert r.simulated_g_dc_db == pytest.approx(-13.545, abs=1e-3)
    assert r.predicted_g_dc_db == pytest.approx(-13.41, abs=0.02)
    assert r.disagreement_db == pytest.approx(0.13, abs=0.03)


@pytest.mark.parametrize(
    "fixture_name,rs,rl,g_dc_name,expected_error_db",
    [
        ("g1_bsim4_tt.out", BSIM4_RS, BSIM4_RL, "gain_dc_db", 2.33),
        ("g1_sky130_tt.out", SKY130_RS, SKY130_RL, "g_dc", 1.74),
    ],
)
def test_section6_verbatim_fails_its_own_gate(
    fixture_name: str, rs: float, rl: float,
    g_dc_name: str, expected_error_db: float,
) -> None:
    """§6 WITHOUT the body-effect term is wrong by more than its own tolerance.

    This is the finding that motivated the correction, pinned on two
    independent device models so it cannot be dismissed as an artefact of the
    generic BSIM4 cards. `include_body_effect=False` reproduces §6 exactly as
    it was written.
    """
    r = cross_check_ngspice_output(
        _load(fixture_name), rs=rs, rl=rl,
        g_dc_meas_name=g_dc_name, include_body_effect=False,
    )
    assert not r.passed, "§6 verbatim should FAIL its own 1 dB gate"
    assert r.disagreement_db == pytest.approx(expected_error_db, abs=0.05)
    assert r.disagreement_db > r.tol_db


def test_body_effect_is_always_optimistic(bsim4: str, sky130: str) -> None:
    """Dropping gmbs shrinks the degeneration, so it overstates the gain.

    A sign error here would be invisible in the magnitude tests above.
    """
    for text, rs, rl, name in ((bsim4, BSIM4_RS, BSIM4_RL, "gain_dc_db"),
                               (sky130, SKY130_RS, SKY130_RL, "g_dc")):
        r = cross_check_ngspice_output(text, rs=rs, rl=rl, g_dc_meas_name=name)
        assert r.predicted_verbatim_db > r.predicted_g_dc_db
        assert r.body_effect_db > 0.0


# ─────────────────────────────────────────────────────────────────────────────
# THE FALSIFIABILITY TEST. A gate that cannot be shown to fail is not a gate.
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("corruption_db", [3.0, -3.0, 12.0])
def test_a_wrong_a_dc_makes_the_gate_fail_loudly(
    bsim4: str, corruption_db: float,
) -> None:
    """Deliberately break the extracted A_dc and require a raised exception.

    This is the test the old `.control` gate could never have passed: there,
    a wrong A_dc produced a warning and exit code 0.
    """
    true_db = -14.56892
    corrupted = bsim4.replace(
        "gain_dc_db          =  -1.456892e+01",
        f"gain_dc_db          =  {true_db + corruption_db:.6e}",
    )
    assert corrupted != bsim4, "the corruption did not apply — test is vacuous"

    r = cross_check_ngspice_output(corrupted, rs=BSIM4_RS, rl=BSIM4_RL,
                                   g_dc_meas_name="gain_dc_db")
    assert not r.passed
    assert r.disagreement_db > 1.0

    with pytest.raises(CrossCheckFailure) as exc:
        r.raise_if_failed()
    assert "fiction" in str(exc.value)


def test_check_all_will_not_hand_back_numbers_when_the_gate_fails(
    bsim4: str,
) -> None:
    """The convenience path must not be a way around the gate."""
    corrupted = bsim4.replace(
        "gain_dc_db          =  -1.456892e+01",
        "gain_dc_db          =  -5.000000e+00",
    )
    with pytest.raises(CrossCheckFailure):
        check_all(corrupted, rs=BSIM4_RS, rl=BSIM4_RL,
                  vdd_v=BSIM4_VDD, i_tail_a=BSIM4_ITAIL,
                  dc_name="gain_dc_db", nyq_name="gain_nyq_db",
                  pk_name="gain_peak_db")


def test_check_all_returns_both_results_on_a_good_run(bsim4: str) -> None:
    result, ac = check_all(bsim4, rs=BSIM4_RS, rl=BSIM4_RL,
                           vdd_v=BSIM4_VDD, i_tail_a=BSIM4_ITAIL,
                           dc_name="gain_dc_db", nyq_name="gain_nyq_db",
                           pk_name="gain_peak_db")
    assert result.passed
    assert ac.peaking_db == pytest.approx(8.29, abs=0.01)
    assert power_w(BSIM4_VDD, BSIM4_ITAIL) == pytest.approx(6.0e-3)


# ─────────────────────────────────────────────────────────────────────────────
# Derived quantities — the arithmetic that used to silently not happen.
# ─────────────────────────────────────────────────────────────────────────────


def test_peaking_is_derived_correctly(bsim4: str) -> None:
    ac = derived_ac(bsim4, dc_name="gain_dc_db", nyq_name="gain_nyq_db",
                    pk_name="gain_peak_db")
    # Hand-computed: -6.279118 - (-14.56892) = 8.289802 dB
    assert ac.peaking_db == pytest.approx(8.289802, abs=1e-5)
    assert ac.f_pk_hz == pytest.approx(1.258925e9, rel=1e-6)
    # HANDOFF §2's reference point, to 2 dp.
    assert round(ac.peaking_db, 2) == 8.29


def test_nyquist_boost_is_not_the_same_thing_as_peaking(sky130: str) -> None:
    """A stage can peak nicely and still lose gain where the data lives.

    The SKY130 smoke-test point does exactly that: 3.8 dB of peaking, which
    is inside S3's 3-12 dB band, but the peak sits at 724 MHz and by 2.5 GHz
    the response is *below* its own DC value. Reporting only `peaking_db`
    would call this a passing design.
    """
    ac = derived_ac(sky130)
    assert ac.peaking_db == pytest.approx(3.82, abs=0.01)
    assert ac.f_pk_hz == pytest.approx(7.24436e8, rel=1e-4)
    assert ac.nyquist_boost_db == pytest.approx(-0.99, abs=0.01)
    assert ac.nyquist_boost_db < 0.0 < ac.peaking_db
    # f_peak is outside S3's 1.25-2.5 GHz window, so S3 fails despite the boost.
    assert not (1.25e9 <= ac.f_pk_hz <= 2.5e9)


def test_power_is_computed_here_not_in_control() -> None:
    assert power_w(1.2, 5e-3) == pytest.approx(6.0e-3)
    with pytest.raises(ValueError):
        power_w(0.0, 5e-3)
    with pytest.raises(ValueError):
        power_w(1.2, -1e-3)


def test_overdrive_and_saturation_from_primitives(bsim4: str) -> None:
    # Vgs - Vth = 0.8349940 - 0.4759025 = 0.3590915 V
    assert overdrive_v(bsim4) == pytest.approx(0.3590915, abs=1e-6)
    # Vds = 0.8549940 > Vdsat = 0.2889172, so the pair is in saturation with
    # 0.566 V of margin — this is the reference point, it should be healthy.
    assert in_saturation(bsim4) is True


def test_saturation_check_can_report_false() -> None:
    """A predicate that only ever returns True is not a check."""
    triode = "@m1[vds] = 1.000000e-01\n@m1[vdsat] = 2.941201e-01\n"
    assert in_saturation(triode) is False


def test_summary_mentions_both_predictions(bsim4: str) -> None:
    r = cross_check_ngspice_output(bsim4, rs=BSIM4_RS, rl=BSIM4_RL,
                                   g_dc_meas_name="gain_dc_db")
    s = r.summary()
    assert "PASS" in s
    assert "gmbs/gm" in s
    assert "body-effect" in s
    assert math.isfinite(r.body_effect_db)
