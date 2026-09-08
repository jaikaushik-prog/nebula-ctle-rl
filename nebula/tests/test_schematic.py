"""
tests/test_schematic.py — gates on `report/schematic.py`, the drawing
`design.py --out` now writes beside `design.cir`.

WHY EACH GUARD EXISTS
----------------------
1.  **A schematic is the most dangerous place in the repository for G32.** A
    picture is believed on sight and re-derived never, so every annotated value
    must come from the deck that was simulated. These tests pin that the
    numbers on the drawing are the numbers in the netlist, and that a deck
    missing any of them RAISES rather than rendering a plausible one.
2.  **A drawing of the wrong circuit with the right numbers is worse than no
    drawing.** `_check_topology` is what stops that, so it is tested against
    each way the deck could stop being this circuit: an element deleted, and an
    element re-wired to a different node.
3.  **`eng` had a real defect** -- an unconditional `.rstrip("0")` turned
    `610 uA` into `61 uA`, a factor of ten on a label. Pinned in both
    directions: trailing zeros before the decimal point must survive, and
    trailing zeros after it must go.
4.  **The panel may never invent a measurement.** `design._schematic_panel`
    reports "not verified" unless `--verify` actually ran, because a picture
    claiming 45 corners that nobody ran is rule 4's worst case.

Only the last group touches `design.py`; nothing here runs SPICE.
"""

from __future__ import annotations

import pytest

from nebula.report import schematic as S

# A deck with the shape `sky130_runner` emits, trimmed to what the drawing
# reads. Built here rather than loaded, so these tests need no artifact.
DECK = """* nebula sky130 sizing point
.param W=61.63568645558893 L=0.8463046966829757 NF=4
.param RL=607.1734204576622 RS=447.00127653262837 CS=6.03939740845026e-13 IT=0.0006096369408065885 CL=3.262805963205924e-14
.param VDD=1.8 VCM=1.5149986408468037
.param WT=67.7916 LT=0.5 NFT=8
.param WREF=8.47395 NFREF=1 IREF=7.62046176e-05 CBYP=1e-11

Vdd   vdd 0 {VDD}
XM1   outp inp s1 0 sky130_fd_pr__nfet_01v8 W={W} L={L} nf={NF}
XM2   outn inn s2 0 sky130_fd_pr__nfet_01v8 W={W} L={L} nf={NF}
Xrlp  vdd outp 0 sky130_fd_pr__res_high_po w=10 l=17.835
Xrln  vdd outn 0 sky130_fd_pr__res_high_po w=10 l=17.835
Xrs   s1 s2 0 sky130_fd_pr__res_high_po w=5.73 l=6.77
Xcs   s1 s2 sky130_fd_pr__cap_mim_m3_1 w=17.215 l=17.215
Iref  vdd nbias {IREF}
XMR   nbias nbias 0 0 sky130_fd_pr__nfet_01v8 W={WREF} L={LT} nf={NFREF}
XMT1  s1    nbias 0 0 sky130_fd_pr__nfet_01v8 W={WT} L={LT} nf={NFT}
XMT2  s2    nbias 0 0 sky130_fd_pr__nfet_01v8 W={WT} L={LT} nf={NFT}
Cbyp  nbias 0 {CBYP}
CLp   outp 0 {CL}
CLn   outn 0 {CL}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Guard 1 — the values are the deck's
# ─────────────────────────────────────────────────────────────────────────────

def test_every_value_is_read_from_the_deck():
    p = S.params_of(DECK)
    assert p["RL"] == pytest.approx(607.1734204576622)
    assert p["RS"] == pytest.approx(447.00127653262837)
    assert p["CS"] == pytest.approx(6.03939740845026e-13)
    assert p["W"] == pytest.approx(61.63568645558893)
    assert p["CBYP"] == pytest.approx(1e-11)


def test_a_deck_missing_a_value_raises_rather_than_defaulting_it():
    stripped = DECK.replace(".param VDD=1.8 VCM=1.5149986408468037\n", "")
    with pytest.raises(ValueError, match="carries no"):
        S.params_of(stripped)


def test_the_missing_name_is_reported_so_the_failure_is_actionable():
    stripped = DECK.replace("CBYP=1e-11", "")
    with pytest.raises(ValueError, match="CBYP"):
        S.params_of(stripped)


# ─────────────────────────────────────────────────────────────────────────────
# Guard 2 — the drawn circuit is the netlisted circuit
# ─────────────────────────────────────────────────────────────────────────────

def test_the_reference_deck_passes_the_topology_check():
    S._check_topology(DECK)          # must not raise


@pytest.mark.parametrize("element", ["XM1", "Xrs", "Xcs", "XMT2", "XMR", "CLp"])
def test_deleting_any_drawn_element_is_refused(element):
    deck = "\n".join(ln for ln in DECK.splitlines()
                     if not ln.startswith(element))
    with pytest.raises(ValueError, match="not the topology"):
        S._check_topology(deck)


def test_rewiring_the_degeneration_off_the_sources_is_refused():
    # The whole S2 topology claim is that Rs sits between s1 and s2. A deck
    # that grounds it is a different circuit and must not be drawn as this one.
    deck = DECK.replace("Xrs   s1 s2 0", "Xrs   s1 0 0")
    with pytest.raises(ValueError, match="Xrs"):
        S._check_topology(deck)


def test_a_tail_that_is_no_longer_mirrored_is_refused():
    deck = DECK.replace("XMT1  s1    nbias", "XMT1  s1    vgg  ")
    with pytest.raises(ValueError, match="XMT1"):
        S._check_topology(deck)


# ─────────────────────────────────────────────────────────────────────────────
# Guard 3 — engineering notation
# ─────────────────────────────────────────────────────────────────────────────

def test_a_trailing_zero_before_the_decimal_point_survives():
    # The defect: `.rstrip("0")` turned 610 uA into 61 uA.
    assert S.eng(0.0006096369408065885, "A") == "610 uA"


def test_a_trailing_zero_after_the_decimal_point_is_dropped():
    assert S.eng(1.8, "V") == "1.8 V"


@pytest.mark.parametrize("value,unit,want", [
    (607.1734204576622, "Ohm", "607 Ohm"),
    (6.03939740845026e-13, "F", "604 fF"),
    (3.262805963205924e-14, "F", "32.6 fF"),
    (1e-11, "F", "10 pF"),
    (7.62046176e-05, "A", "76.2 uA"),
])
def test_known_labels(value, unit, want):
    assert S.eng(value, unit) == want


def test_zero_is_not_given_a_prefix():
    assert S.eng(0.0, "F") == "0 F"


# ─────────────────────────────────────────────────────────────────────────────
# The render itself
# ─────────────────────────────────────────────────────────────────────────────

def test_it_renders_a_png(tmp_path):
    out = S.draw_schematic(DECK, tmp_path / "s.png")
    assert out.exists() and out.stat().st_size > 10_000


def test_a_wrong_topology_is_refused_before_anything_is_written(tmp_path):
    deck = DECK.replace("Xcs   s1 s2", "Xcs   s1 0 ")
    out = tmp_path / "s.png"
    with pytest.raises(ValueError):
        S.draw_schematic(deck, out)
    assert not out.exists()


# ─────────────────────────────────────────────────────────────────────────────
# Guard 4 — the panel states only what the run measured
# ─────────────────────────────────────────────────────────────────────────────

def test_the_panel_says_not_verified_when_verify_did_not_run():
    from nebula.design import _schematic_panel

    panel = _schematic_panel({"method": "auto", "nominal": {}})
    assert panel["verified points"] == "not verified (--verify)"


def test_the_panel_reports_the_grid_the_verifier_actually_ran():
    from nebula.design import _schematic_panel

    panel = _schematic_panel({
        "method": "auto", "nominal": {},
        "verification": {"n_points": 135, "n_failed": 3, "n_corners": 45,
                         "n_loads": 3}})
    assert panel["verified points"] == "132 / 135 PASS (45x3)"


def test_the_panel_omits_measurements_the_run_does_not_carry():
    from nebula.design import _schematic_panel

    panel = _schematic_panel({"method": "library", "nominal": {"meas": {}}})
    assert "peaking (TT)" not in panel
    assert "power (TT)" not in panel


def test_the_panel_leads_with_the_verdict_when_the_run_failed():
    # A failed sizing run still has a netlist, so the drawing must say so.
    from nebula.design import _schematic_panel

    panel = _schematic_panel({"method": "auto",
                              "nominal": {"ok": False,
                                          "verdict": "headroom_only"}})
    assert panel["status"] == "headroom_only"


def test_the_panel_says_pass_only_when_the_design_is_feasible():
    from nebula.design import _schematic_panel

    ok = _schematic_panel({"method": "auto",
                           "nominal": {"ok": True, "feasible": True,
                                       "verdict": "measured"}})
    assert ok["status"] == "PASS"
    # Measured but infeasible is NOT a pass, and must not read as one.
    bad = _schematic_panel({"method": "auto",
                            "nominal": {"ok": True, "feasible": False,
                                        "verdict": "measured"}})
    assert bad["status"] != "PASS"


def test_a_warning_still_renders(tmp_path):
    out = S.draw_schematic(DECK, tmp_path / "warn.png",
                           warning="headroom_only")
    assert out.exists() and out.stat().st_size > 10_000
