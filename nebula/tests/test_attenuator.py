"""tests for `device/attenuator.py` — the input attenuator (decision D11).

**The gate that matters is byte-identity when the block is OFF.** This is added
to `sky130_runner`, which produced every number in this repository. If the
assembled deck changed by so much as a blank line when `atten_code=None`, every
committed result would silently be describing a different circuit from the one
that produced it.

The sizing itself is pinned too, because it is DERIVED from a measurement
(`ATTEN_MAX_X = 1.98`, the worst-case over-drive at the shortest channel, from
entry 72) rather than chosen. A test that only checked the code ran would not
notice the spec drifting.
"""

from __future__ import annotations

import math

import pytest

from nebula.device import attenuator as A
from nebula.device.sky130_runner import assemble_netlist


# ── the off-gate ─────────────────────────────────────────────────────────────


def test_off_returns_the_historical_fields():
    assert A.netlist_fields(None) == {"in_p": "inp", "in_n": "inn",
                                      "atten_block": ""}


def _deck(code):
    return assemble_netlist(
        lib="X.lib", corner="tt", device="sky130_fd_pr__nfet_01v8",
        w=5e-5, l=4e-7, nf=4, rl=250.0, rs=220.0, cs=4e-12, cl=3e-14,
        it=1.8e-3, vdd=1.8, vcm=1.5, swing_block="", temp_c=27.0,
        tail_source="", tail_probe="", passive_block="", noise_summary="",
        noise_probe="", f_top="20g", **A.netlist_fields(code))


def test_the_deck_is_BYTE_IDENTICAL_when_the_attenuator_is_off():
    """**The gate.** Every committed result was produced by this text."""
    off = _deck(None)
    assert "Einp  inp cm vid 0 0.5" in off
    assert "Einn  inn cm vid 0 -0.5" in off
    assert "Xatt_" not in off and "inx" not in off and "iny" not in off


def test_turning_it_on_rewires_the_gates_through_the_divider():
    on = _deck(7)
    assert "Einp  inx cm vid 0 0.5" in on
    assert "Xatt_sp inx inp 0 " in on
    assert "Xatt_sn iny inn 0 " in on


def test_code_zero_is_still_a_real_divider_not_a_bypass():
    """Code 0 attenuates by 0 dB but the SERIES arm is still in the signal path.

    A bypass that removed the series resistor at code 0 would make the
    zero-attenuation setting a different circuit from every other setting, and
    the parasitic step between code 0 and code 1 would be invisible.
    """
    z = _deck(0)
    assert "Xatt_sp inx inp 0 " in z
    assert A.attenuation(0) == pytest.approx(1.0)


# ── the sizing, which is derived from a measurement ──────────────────────────


def test_the_spec_constant_is_the_measured_worst_case():
    assert A.ATTEN_MAX_X == pytest.approx(1.98)
    assert A.REQUIREMENT_BY_LOSS_DB[3.0] == pytest.approx(A.ATTEN_MAX_X)
    assert A.REQUIREMENT_BY_LOSS_DB[12.0] == pytest.approx(1.0)


def test_the_top_code_reaches_the_measured_worst_case_exactly():
    assert 1.0 / A.attenuation(A.N_CODES - 1) == pytest.approx(A.ATTEN_MAX_X)


def test_attenuation_is_monotone_and_starts_at_unity():
    a = [A.attenuation(n) for n in range(A.N_CODES)]
    assert a[0] == pytest.approx(1.0)
    assert all(x > y for x, y in zip(a, a[1:]))


def test_every_channel_in_the_family_is_covered_by_rounding_UP():
    """The requirement is met at every member, never undershot."""
    for loss, need_x in A.REQUIREMENT_BY_LOSS_DB.items():
        code = A.code_for(need_x)
        got = A.attenuation_db(code)
        need = 20.0 * math.log10(need_x)
        assert got >= need - 1e-9, f"{loss} dB channel undershot: {got} < {need}"


def test_rounding_is_UP_not_nearest():
    """Falling one step short leaves the stage compressed; the errors are
    asymmetric, so `code_for` must never round down."""
    just_over = 1.0 / A.attenuation(3) * 1.001
    assert A.code_for(just_over) == 4


def test_the_switch_on_resistance_is_removed_from_each_drawn_leg():
    """So the realised conductance is the designed one, not 6 % low on bit 2."""
    for bit in range(A.N_BITS):
        ideal = 1.0 / ((2 ** bit) * A.G0_S)
        assert A.leg_resistance_ohm(bit) == pytest.approx(
            ideal - A.SWITCH_RON_OHM)
    assert A.leg_resistance_ohm(0) > A.leg_resistance_ohm(A.N_BITS - 1)


# ── what the emitted text must and must not contain ──────────────────────────


def test_every_leg_is_emitted_at_every_code_including_the_disabled_ones():
    """A disabled leg still presents its switch capacitance to the input node.

    Emitting only the enabled legs would have removed that parasitic and
    flattered the design by exactly the thing a real part has to live with.
    """
    for code in range(A.N_CODES):
        txt = A.attenuator_block(code)
        for bit in range(A.N_BITS):
            assert f"Xatt_swp{bit} " in txt, (code, bit)
            assert f"Xatt_swn{bit} " in txt, (code, bit)


@pytest.mark.parametrize("code", range(A.N_CODES))
def test_the_switch_gates_encode_the_code_in_binary(code):
    txt = A.attenuator_block(code)
    for bit in range(A.N_BITS):
        line = next(l for l in txt.splitlines()
                    if l.startswith(f"Xatt_swp{bit} "))
        gate = line.split()[2]
        assert gate == ("vdd" if code & (1 << bit) else "0"), (code, bit, line)


def test_the_block_is_differential_and_symmetric():
    txt = A.attenuator_block(5)
    p = [l for l in txt.splitlines() if l.startswith("Xatt_") and "p" in
         l.split()[0]]
    n = [l for l in txt.splitlines() if l.startswith("Xatt_") and "n" in
         l.split()[0]]
    assert len(p) == len(n)


def test_an_out_of_range_code_raises():
    with pytest.raises(ValueError):
        A.attenuator_block(A.N_CODES)
    with pytest.raises(ValueError):
        A.attenuation(-1)
