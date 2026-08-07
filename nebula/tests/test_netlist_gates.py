"""
The two §6a gates: `w` on a fixed-width resistor, and `mult` != 1.

Both parameters are ACCEPTED by ngspice, IGNORED by the model, and followed by
exit code 0 (G56, G57). Nothing else in the toolchain notices, so these tests
are the entire detection mechanism and each one must be seen to fail.

The measurements behind them, so the numbers are here and not only in HANDOFF:

    G56  res_high_po w=1 l=1.78 at 10 uA:  mult=1 -> 942.90 ohm
                                           mult=4 -> 942.90 ohm  (IDENTICAL)
                                           m=4    -> 235.72 ohm  (exactly /4)
    G57  res_high_po_0p69 with w=0.69, w=2.85 and w=99 all -> 2893.64 ohm,
         and the device that IS 2.85 um wide reads 718.61 ohm — 4.03x apart.
"""

from __future__ import annotations

import pytest

from nebula.device import netlist_gates as G
from nebula.device.netlist_gates import InertParameterWrite, assert_no_inert_writes
from nebula.device.passives import FIXED_WIDTH_UM, fixed_width_subckt


# ── G57: `w` on a fixed-width family ────────────────────────────────────────

@pytest.mark.parametrize("w", [0.69, 2.85, 99.0])
def test_w_on_a_fixed_width_family_is_refused(w):
    """Every width, including the one that matches the subckt's own name.

    `w=0.69` on `res_high_po_0p69` is the *correct* width and is still refused,
    deliberately: it reads as though it sets something, and the next person to
    edit the line will change the number and get no error.
    """
    line = f"Xrs s1 s2 0 sky130_fd_pr__res_high_po_0p69 w={w} l=5.0"
    with pytest.raises(InertParameterWrite, match="FIXED-WIDTH"):
        assert_no_inert_writes(line)


@pytest.mark.parametrize("w_um", FIXED_WIDTH_UM)
def test_every_fixed_width_family_the_pdk_provides_is_matched(w_um):
    """The gate matches by SHAPE, so it covers all five PDK widths."""
    for family in ("res_high_po", "res_xhigh_po"):
        sub = fixed_width_subckt(family, w_um)
        assert G.check_inert_writes(f"X1 a b 0 {sub} w=1.0 l=2.0"), (
            f"{sub} was not recognised as a fixed-width family")


def test_l_on_a_fixed_width_family_is_allowed():
    """`l` IS honoured on these families; only `w` is inert (G57)."""
    assert_no_inert_writes("Xrs s1 s2 0 sky130_fd_pr__res_high_po_2p85 l=5.0")


def test_w_on_the_generic_family_is_allowed():
    """The generic `res_high_po` honours `w`, and `to_geometry` relies on it."""
    assert_no_inert_writes("Xrs s1 s2 0 sky130_fd_pr__res_high_po w=2.85 l=4.445")


# ── G56: `mult` / `mf` ──────────────────────────────────────────────────────

@pytest.mark.parametrize("param", ["mult", "mf"])
@pytest.mark.parametrize("value", ["4", "2", "0", "0.5", "-1"])
def test_mult_other_than_one_is_refused(param, value):
    line = f"Xc s1 s2 sky130_fd_pr__cap_mim_m3_1 w=30 l=30 {param}={value}"
    with pytest.raises(InertParameterWrite, match="MISMATCH parameter"):
        assert_no_inert_writes(line)


@pytest.mark.parametrize("param", ["mult", "mf"])
def test_mult_equal_to_one_is_allowed(param):
    """`mult=1` is the identity, and the existing nfet netlists write it.

    Banning it outright would require editing netlists whose numbers are
    published, for no change in behaviour. It is allowed and it is NOT
    evidence that `mult` works.
    """
    assert_no_inert_writes(
        f"XM1 outp inp s1 0 sky130_fd_pr__nfet_01v8 W=40 L=0.15 nf=4 {param}=1")


def test_m_is_never_confused_with_mult():
    """ngspice's native `m=` is the multiplier that works and must pass."""
    assert_no_inert_writes("Xrs s1 s2 0 sky130_fd_pr__res_high_po w=2.85 l=4.445 m=2")


# ── the gate must not be trigger-happy ──────────────────────────────────────

def test_model_and_param_cards_are_not_scanned():
    """The PDK's own `.model` cards declare `mult` as a formal parameter.

    Scanning them would fire on the library rather than on our writes, and a
    gate that fires on correct input gets deleted for being noisy.
    """
    assert_no_inert_writes(
        ".model sky130_fd_pr__res_high_po r mult=4 tc1=0.1\n"
        ".param mult=4\n"
        "+ mult=4\n"
        "* a comment mentioning mult=4\n"
    )


def test_control_block_is_not_scanned():
    """`.control` carries commands, not instances."""
    assert_no_inert_writes(
        ".control\nlet mult=4\nprint mult\nquit\n.endc\n")


def test_a_clean_ctle_netlist_passes():
    """The real thing: what `passive_block(to_geometry(...))` emits."""
    from nebula.device.passives import to_geometry
    from nebula.device.sky130_runner import passive_block

    assert_no_inert_writes(passive_block(to_geometry(318.58, 1.9e-12, 565.0)))
    assert_no_inert_writes(passive_block(None))


# ── the gate is WIRED, not merely present ───────────────────────────────────

def test_run_point_applies_the_gate():
    """`run_point` must call it. A gate nobody calls is a comment.

    Asserted by source inspection rather than by simulating: the point is that
    the call EXISTS on the path, and proving that by running ngspice would
    require constructing a netlist the gate rejects, which `passive_block`
    cannot produce by design.
    """
    import inspect

    from nebula.device import sky130_runner

    src = inspect.getsource(sky130_runner)
    assert "assert_no_inert_writes(text)" in src, (
        "sky130_runner no longer gates its assembled netlist text; G56/G57 are "
        "undetectable again")


def test_env_construction_proves_both_gates_can_fail():
    """`_assert_netlist_gates_wired` is the run-time proof (§6a, rule 10)."""
    from nebula.rl.env import _assert_netlist_gates_wired

    _assert_netlist_gates_wired()          # must not raise


def test_env_wiring_check_notices_a_disabled_gate(monkeypatch):
    """Break the gate; the env must refuse to construct."""
    from nebula.rl import env as env_mod

    monkeypatch.setattr(env_mod, "assert_no_inert_writes", lambda text: None)
    with pytest.raises(AssertionError, match="did NOT reject"):
        env_mod._assert_netlist_gates_wired()
