"""
Tests for the derived channel family (`nebula/link/channel.py`).

Four groups, in the order the task that produced them lists:

1. **The retired constant.** The invented DC-loss placeholder is gone from
   every executable file in the tree, and the symbol no longer resolves.
   (Its identifier is assembled from pieces below so this file does not match
   its own grep.)
2. **Closed form.** The constructed insertion loss at 2.5 GHz equals the target
   to a stated tolerance, across the whole family, and A/B are hand-checkable.
3. **The gates.** Causality (reported per member, and watched to FAIL on the
   zero-phase control), passivity, monotonicity.
4. **Determinism and ingestion.** Same parameters -> bit-identical response;
   a synthetic Touchstone-shaped fit recovers the coefficients it was built
   from.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from nebula.common.types import NYQUIST_HZ
from nebula.link.channel import (
    BALANCED,
    CAUSALITY_ENERGY_THRESHOLD,
    DEFAULT_N_FFT,
    DEFAULT_OSR,
    DIELECTRIC_DOMINATED,
    FAMILY_IL_DB,
    FAMILY_SKIN_FRACTIONS,
    FR4_MICROSTRIP,
    SKIN_DOMINATED,
    STATED_REFLECTION_PROBE,
    ChannelModel,
    Reflection,
    Stackup,
    causality_of,
    channel_family,
    fit_insertion_loss,
    insertion_loss_from_touchstone,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The retired symbol, ASSEMBLED FROM PIECES ON PURPOSE. This file greps the
#: whole tree for the identifier, and a literal here would make the test find
#: itself and fail forever — a self-defeating gate is worse than no gate.
RETIRED_CONSTANT = "CHANNEL_DC" + "_LOSS_DB"

#: Tolerance on "the constructed IL at Nyquist equals the target". The
#: construction is closed form, so this is float noise and nothing else.
IL_TOL_DB = 1e-12


# ─────────────────────────────────────────────────────────────────────────────
# 1. The retired constant
# ─────────────────────────────────────────────────────────────────────────────


class TestTheInventedConstantIsGone:
    """The invented DC-loss placeholder had no provenance and decided every
    compression verdict this project published. It was DELETED, not re-valued:
    the loss of a transmission line at DC is essentially zero, so the
    constant's own name encoded its mistake."""

    def test_the_symbol_is_not_defined_anywhere_importable(self):
        import importlib

        for name in ("nebula.link.config", "nebula.link", "nebula.link.channel",
                     "nebula.link.tx", "nebula.link.calibration"):
            mod = importlib.import_module(name)
            with pytest.raises(AttributeError):
                getattr(mod, RETIRED_CONSTANT)

    def test_the_identifier_appears_in_no_executable_file_in_the_tree(self):
        # Scope, stated: every file that could EXECUTE the name. Markdown is
        # excluded and handled by the next test, because the retirement has to
        # be written down somewhere and a project that erases its own history
        # cannot show its working.
        suffixes = {".py", ".cir", ".spice", ".sv", ".m", ".sh", ".yaml", ".yml"}
        offenders = []
        for path in REPO_ROOT.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in suffixes:
                continue
            if any(part in {".git", "__pycache__", ".pytest_cache"} for part in path.parts):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:                                   # pragma: no cover
                continue
            if RETIRED_CONSTANT in text:
                offenders.append(str(path.relative_to(REPO_ROOT)))
        assert offenders == [], (
            f"{RETIRED_CONSTANT} is back in {offenders}. It is an invented "
            f"constant standing in for a quantity that is physically zero — "
            f"use ChannelModel.il_db_at_dc and TxDeEmphasis instead."
        )

    def test_markdown_mentions_are_confined_to_the_historical_record(self):
        # The name may appear in write-ups that RETIRE it. It must not appear
        # in a new document as though it were live.
        allowed = {
            "HANDOFF.md",                       # session log + gotchas
            "nebula/CHANNEL_MODEL.md",          # the write-up that retires it
            "nebula/PREDICTIONS.md",            # the pre-registration
            "nebula/BOUNDS_REDERIVATION.md",    # where it decided the verdict
            "nebula/S9_YIELD.md",               # where it was listed as a blocker
            # Added 2026-08-17. The decision register's §F1 entry IS a record
            # of the retirement — "delete it rather than re-value it, because
            # the NAME encoded the mistake" — which is the case this test's own
            # comment allows. It was caught by this test on the day it was
            # written, which is the gate working, and the allowlist is extended
            # rather than the text reworded because the entry is exactly the
            # historical record the exemption exists for.
            "decisions.md",
        }
        found = set()
        for path in REPO_ROOT.rglob("*.md"):
            if any(part in {".git", "__pycache__"} for part in path.parts):
                continue
            if RETIRED_CONSTANT in path.read_text(encoding="utf-8", errors="ignore"):
                found.add(path.relative_to(REPO_ROOT).as_posix())
        assert found <= allowed, f"new document(s) still name the retired constant: {found - allowed}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Closed form
# ─────────────────────────────────────────────────────────────────────────────


class TestClosedForm:
    @pytest.mark.parametrize("il", FAMILY_IL_DB)
    @pytest.mark.parametrize("r", FAMILY_SKIN_FRACTIONS)
    def test_constructed_loss_at_nyquist_equals_the_target(self, il, r):
        ch = ChannelModel(il_db_at_nyquist=il, skin_fraction=r)
        assert ch.il_db(NYQUIST_HZ) == pytest.approx(il, abs=IL_TOL_DB)

    @pytest.mark.parametrize("il", FAMILY_IL_DB)
    @pytest.mark.parametrize("r", FAMILY_SKIN_FRACTIONS)
    def test_the_split_is_what_it_says_at_nyquist(self, il, r):
        ch = ChannelModel(il_db_at_nyquist=il, skin_fraction=r)
        skin = ch.a_db_per_sqrt_ghz * math.sqrt(ch.f_nyquist_ghz)
        assert skin / il == pytest.approx(r, abs=1e-12)

    def test_a_and_b_by_hand(self):
        # 12 dB at 2.5 GHz, half from each mechanism.
        #   skin part      = 6 dB = A*sqrt(2.5)  -> A = 6/1.5811 = 3.7947
        #   dielectric part= 6 dB = B*2.5        -> B = 2.4
        ch = ChannelModel(12.0, BALANCED)
        assert ch.a_db_per_sqrt_ghz == pytest.approx(6.0 / math.sqrt(2.5), rel=1e-12)
        assert ch.a_db_per_sqrt_ghz == pytest.approx(3.79473, rel=1e-5)
        assert ch.b_db_per_ghz == pytest.approx(2.4, rel=1e-12)

    def test_loss_at_dc_is_exactly_zero_not_approximately(self):
        for ch in channel_family():
            assert ch.il_db_at_dc == 0.0
            assert ch.magnitude(0.0) == 1.0

    def test_a_pure_skin_channel_has_no_dielectric_term_and_vice_versa(self):
        assert ChannelModel(9.0, 1.0).b_db_per_ghz == 0.0
        assert ChannelModel(9.0, 0.0).a_db_per_sqrt_ghz == 0.0

    def test_the_split_changes_the_shape_at_a_fixed_headline_number(self):
        # 5c's point: a scalar cannot represent a channel. Same 12 dB at
        # Nyquist, materially different loss at every OTHER frequency.
        skin = ChannelModel(12.0, SKIN_DOMINATED)
        diel = ChannelModel(12.0, DIELECTRIC_DOMINATED)
        assert skin.il_db(NYQUIST_HZ) == pytest.approx(diel.il_db(NYQUIST_HZ))
        # Below Nyquist the sqrt(f) mechanism has already spent more of its loss.
        assert skin.il_db(0.5e9) > 1.4 * diel.il_db(0.5e9)
        # Above it, the linear mechanism overtakes.
        assert diel.il_db(10e9) > 1.4 * skin.il_db(10e9)

    def test_the_family_grid_is_the_full_cross_product(self):
        fam = channel_family()
        assert len(fam) == len(FAMILY_IL_DB) * len(FAMILY_SKIN_FRACTIONS)
        assert len({(c.il_db_at_nyquist, c.skin_fraction) for c in fam}) == len(fam)
        assert min(FAMILY_IL_DB) == 3.0 and max(FAMILY_IL_DB) == 12.0

    def test_a_negative_loss_or_an_out_of_range_split_is_rejected(self):
        with pytest.raises(ValueError, match="insertion LOSS"):
            ChannelModel(-1.0)
        with pytest.raises(ValueError, match="skin_fraction"):
            ChannelModel(6.0, skin_fraction=1.2)
        with pytest.raises(ValueError, match="skin_fraction"):
            ChannelModel(6.0, skin_fraction=-0.01)


# ─────────────────────────────────────────────────────────────────────────────
# 3. The gates
# ─────────────────────────────────────────────────────────────────────────────


class TestCausality:
    """5b. A magnitude-only response with zero phase is non-causal, and every
    ISI number computed from it is finite, plausible and wrong."""

    @pytest.mark.parametrize("ch", channel_family(), ids=str)
    def test_every_family_member_is_causal(self, ch):
        rep = ch.assert_causal()
        assert rep.pre_energy_fraction <= CAUSALITY_ENERGY_THRESHOLD

    def test_the_gate_fails_on_the_thing_it_exists_to_catch(self):
        # CLAUDEwa.md §8 rule 10: every gate gets a test that proves it can
        # fail. The zero-phase reconstruction puts ~half the energy at t < 0.
        ch = ChannelModel(12.0, SKIN_DOMINATED)
        bad = causality_of(ch.zero_phase_impulse_response(), DEFAULT_OSR)
        assert bad.pre_energy_fraction > 0.4
        assert not bad.passes
        assert ch.causality_report().passes

    def test_pre_t0_energy_falls_with_buffer_length_ie_it_is_aliasing(self):
        # How you tell a broken reconstruction from a truncated one: aliasing
        # of the tail scales down with the buffer, a phase error does not.
        ch = ChannelModel(12.0, SKIN_DOMINATED)
        e = [ch.causality_report(n_fft=n).pre_energy_fraction
             for n in (4096, 8192, 16384, 32768)]
        assert all(e[i + 1] < 0.4 * e[i] for i in range(len(e) - 1))

    def test_the_minimum_phase_magnitude_reproduces_the_target(self):
        ch = ChannelModel(9.0, BALANCED)
        h = ch.transfer_function()
        target = ch.magnitude(ch.frequency_grid())
        assert np.allclose(np.abs(h), target, rtol=1e-10, atol=1e-12)

    def test_the_impulse_response_is_real(self):
        ch = ChannelModel(9.0, BALANCED)
        spectrum = ch.transfer_function()
        assert np.max(np.abs(np.fft.ifft(spectrum).imag)) < 1e-12

    def test_a_grid_too_coarse_to_resolve_a_ui_is_refused(self):
        ch = ChannelModel(6.0)
        with pytest.raises(ValueError, match="at least 32 samples per UI"):
            ch.impulse_response(osr=16)
        with pytest.raises(ValueError, match="n_fft"):
            ch.impulse_response(osr=64, n_fft=64)


class TestPassivity:
    @pytest.mark.parametrize("ch", channel_family(), ids=str)
    def test_every_family_member_is_passive_and_monotone(self, ch):
        rep = ch.assert_passive()
        assert rep.max_magnitude <= 1.0 + 1e-12
        assert rep.worst_monotonicity_violation <= 1e-12

    def test_the_passivity_gate_can_fail(self):
        # Feed the report a magnitude it must reject. Built by hand rather
        # than by breaking ChannelModel, whose parameterisation cannot
        # produce a gain.
        from nebula.link.channel import PassivityReport

        bad = PassivityReport(max_magnitude=1.4, max_magnitude_excess=0.4,
                              worst_monotonicity_violation=0.02, n_points=10)
        assert not bad.passes


# ─────────────────────────────────────────────────────────────────────────────
# 4. Reporting, determinism, ingestion
# ─────────────────────────────────────────────────────────────────────────────


class TestEquivalentLength:
    def test_a_12_db_channel_is_a_plausible_board_length(self):
        el = ChannelModel(12.0, BALANCED).equivalent_length()
        # A foot and a half of FR-4 microstrip, not a millimetre and not a mile.
        assert 8.0 < el.from_total_inch < 30.0

    def test_a_3_db_channel_is_a_few_inches(self):
        el = ChannelModel(3.0, BALANCED).equivalent_length()
        assert 2.0 < el.from_total_inch < 8.0

    def test_the_two_mechanisms_agree_only_at_the_stackups_own_split(self):
        nat = FR4_MICROSTRIP.natural_skin_fraction(NYQUIST_HZ)
        matched = ChannelModel(9.0, nat).equivalent_length()
        assert matched.self_consistent
        assert matched.from_skin_m == pytest.approx(matched.from_dielectric_m, rel=1e-9)
        assert matched.from_total_m == pytest.approx(matched.from_skin_m, rel=1e-9)
        # ...and the balanced family member is NOT a homogeneous length of it.
        assert not ChannelModel(9.0, DIELECTRIC_DOMINATED).equivalent_length().self_consistent

    def test_the_stackup_coefficients_by_hand(self):
        # Dielectric: 8.686 * pi * 1e9 * sqrt(4.3) * 0.02 / 2.998e8 dB/m/GHz.
        expect_b = (20.0 / math.log(10.0)) * math.pi * 1e9 * math.sqrt(4.3) * 0.02 / 2.99792458e8
        assert FR4_MICROSTRIP.b_db_per_ghz_per_m == pytest.approx(expect_b, rel=1e-12)
        assert FR4_MICROSTRIP.b_db_per_ghz_per_m == pytest.approx(3.7749, rel=1e-4)
        # Conductor: 2 * R_s / (Z0 * w), R_s = sqrt(pi * 1e9 * mu0 / sigma).
        assert FR4_MICROSTRIP.a_db_per_sqrt_ghz_per_m == pytest.approx(11.2851, rel=1e-4)
        # Total at 2.5 GHz -> 0.69 dB/inch, a recognisable FR-4 figure.
        assert FR4_MICROSTRIP.il_db_per_m(NYQUIST_HZ) * 0.0254 == pytest.approx(0.693, rel=1e-2)

    def test_a_bad_stackup_is_rejected(self):
        with pytest.raises(ValueError, match="tan_delta"):
            Stackup(name="x", dk=4.3, tan_delta=0.0, z0_ohm=50.0, trace_width_m=1e-4)


class TestDeterminism:
    def test_two_identical_channels_give_bit_identical_responses(self):
        a = ChannelModel(7.5, 0.3).impulse_response()
        b = ChannelModel(7.5, 0.3).impulse_response()
        assert np.array_equal(a, b)

    def test_the_model_carries_no_random_state_at_all(self):
        # Stronger than "seeded reproducibly": the response is a pure function
        # of two floats, so LinkConfig.seed never enters it. Perturbing numpy's
        # global RNG must change nothing.
        ch = ChannelModel(7.5, 0.3)
        first = ch.impulse_response()
        np.random.seed(12345)
        np.random.random(1000)
        assert np.array_equal(ch.impulse_response(), first)

    def test_the_channel_is_frozen(self):
        ch = ChannelModel(7.5)
        with pytest.raises(Exception):
            ch.il_db_at_nyquist = 3.0  # type: ignore[misc]


class TestReflections:
    def test_a_reflection_must_arrive_after_the_pulse(self):
        with pytest.raises(ValueError, match="AFTER the pulse"):
            Reflection(rho=0.05, delay_ui=-1.0)
        with pytest.raises(ValueError, match="rho"):
            Reflection(rho=1.5, delay_ui=2.0)

    @pytest.mark.parametrize("refl", STATED_REFLECTION_PROBE, ids=str)
    def test_each_echo_is_the_response_scaled_and_shifted(self, refl):
        # One reflection at a time: with both fitted, the earlier echo's own
        # tail also lands at the later echo's delay, so the two cannot be
        # checked independently off the same waveform.
        ch = ChannelModel(9.0, BALANCED)
        base = ch.impulse_response()
        with_r = ch.with_reflections([refl]).impulse_response()
        k = int(round(refl.delay_ui * DEFAULT_OSR))
        assert with_r[k:k + 8] - base[k:k + 8] == pytest.approx(
            refl.rho * base[:8], rel=1e-9, abs=1e-18)
        assert np.array_equal(with_r[:k], base[:k])

    def test_the_probe_fits_both_stated_echoes(self):
        ch = ChannelModel(9.0, BALANCED)
        both = ch.with_reflections().impulse_response()
        one_at_a_time = ch.impulse_response()
        for r in STATED_REFLECTION_PROBE:
            k = int(round(r.delay_ui * DEFAULT_OSR))
            one_at_a_time[k:] += r.rho * ch.impulse_response()[:ch.impulse_response().size - k]
        assert np.allclose(both, one_at_a_time, rtol=1e-12, atol=1e-18)

    def test_reflections_are_off_by_default(self):
        assert ChannelModel(9.0).reflections == ()
        assert np.array_equal(ChannelModel(9.0).impulse_response(),
                              ChannelModel(9.0, reflections=()).impulse_response())

    def test_reflections_do_not_break_causality(self):
        # They are applied in the time domain at positive delays, so they
        # cannot: the point of the check is that the gate still runs on them.
        assert ChannelModel(12.0, SKIN_DOMINATED).with_reflections().causality_report().passes


class TestIngestion:
    """5i. The seam a real .s4p enters through."""

    def test_a_synthetic_channel_is_recovered_from_its_own_insertion_loss(self):
        truth = ChannelModel(8.0, 0.65)
        f = np.linspace(10e6, 20e9, 4000)
        fit = fit_insertion_loss(f, truth.il_db(f))
        assert fit.rms_residual_db < 1e-10
        assert fit.channel.il_db_at_nyquist == pytest.approx(8.0, rel=1e-9)
        assert fit.channel.skin_fraction == pytest.approx(0.65, rel=1e-9)

    def test_the_residual_reports_a_shape_the_two_term_form_cannot_follow(self):
        # A resonant dip — what a connector or a stub does. The fit does not
        # fail; it reports that it cannot represent this, which is the useful
        # behaviour when real data arrives.
        f = np.linspace(10e6, 20e9, 4000)
        il = ChannelModel(8.0, 0.65).il_db(f) + 3.0 * np.exp(-((f - 8e9) / 4e8) ** 2)
        fit = fit_insertion_loss(f, il)
        assert fit.rms_residual_db > 0.1
        assert fit.max_residual_db > 1.0

    def test_non_negativity_is_enforced(self):
        # Data that wants a negative dielectric term: pure sqrt(f) with a
        # downward bend. B is pinned to zero rather than allowed to be a gain.
        f = np.linspace(10e6, 20e9, 2000)
        il = 10.0 * np.sqrt(f / 1e9) - 0.4 * (f / 1e9)
        fit = fit_insertion_loss(f, il)
        assert fit.channel.b_db_per_ghz >= 0.0
        assert fit.channel.a_db_per_sqrt_ghz > 0.0

    def test_a_gain_is_rejected_rather_than_fitted(self):
        f = np.linspace(10e6, 20e9, 100)
        with pytest.raises(ValueError, match="POSITIVE insertion loss"):
            fit_insertion_loss(f, -ChannelModel(8.0).il_db(f))

    def test_touchstone_reading_fails_loudly_without_scikit_rf(self):
        pytest.importorskip  # noqa: B018 - documented below
        try:
            import skrf  # noqa: F401
        except ImportError:
            with pytest.raises(RuntimeError, match="scikit-rf"):
                insertion_loss_from_touchstone("nonexistent.s4p")
        else:                                             # pragma: no cover - env
            with pytest.raises(Exception):
                insertion_loss_from_touchstone("nonexistent.s4p")


class TestGridConstants:
    def test_the_internal_oversampling_meets_the_stated_minimum(self):
        assert DEFAULT_OSR >= 32
        assert DEFAULT_N_FFT % DEFAULT_OSR == 0
        assert DEFAULT_N_FFT // DEFAULT_OSR >= 128     # UI of memory
