"""Draw the delivered 512-code CTLE architecture and its evidence boundary.

This is deliberately an architecture/status view, not a claim that every
selector transistor has been implemented.  It distinguishes the measured
PMOS input attenuator from the Rs/Cs geometries whose physical selector
switches and parasitics remain unbuilt.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle


INK = "#18202A"
MUTED = "#66717E"
BLUE = "#006DAA"
PALE_BLUE = "#E7F2F8"
GREEN = "#167A53"
PALE_GREEN = "#E7F4EE"
ORANGE = "#C95616"
PALE_ORANGE = "#FFF0E5"
LINE = "#B9C3CC"


def architecture_model(design: dict) -> dict:
    """Validate and decode the hardware manifest carried by a design."""
    if design.get("method") != "rl-hybrid":
        raise ValueError("programmable architecture requires an rl-hybrid design")
    search = design.get("search") or {}
    manifest = search.get("programmable_hardware")
    if not isinstance(manifest, dict):
        raise ValueError("design is missing its programmable hardware manifest")
    if manifest.get("setting_encoding") != "setting = A*64 + R*8 + C":
        raise ValueError("unexpected 512-setting code encoding")
    if int(manifest.get("total_logical_settings", 0)) != 512:
        raise ValueError("programmable hardware manifest must contain 512 settings")

    atten = manifest.get("attenuator") or {}
    rs_bank = manifest.get("rs_bank") or {}
    cs_bank = manifest.get("cs_bank") or {}
    if atten.get("switch_status") != "netlisted-and-measured":
        raise ValueError("input attenuator switch evidence is not measured")
    if rs_bank.get("switch_status") != "not-netlisted":
        raise ValueError("Rs selector switches must not be claimed as measured")
    if cs_bank.get("switch_status") != "not-netlisted":
        raise ValueError("Cs selector switches must not be claimed as measured")
    for name, block in (("attenuator", atten), ("Rs", rs_bank),
                        ("Cs", cs_bank)):
        codes = block.get("codes") or []
        if [int(row.get("code", -1)) for row in codes] != list(range(8)):
            raise ValueError(f"{name} must contain ordered codes 0..7")

    atten_code = int(search.get("atten_code", -1))
    bank_code = int(search.get("bank_code", -1))
    rs_code, cs_code = divmod(bank_code, 8)
    if not (0 <= atten_code < 8 and 0 <= rs_code < 8 and 0 <= cs_code < 8):
        raise ValueError("selected programmable code is outside the 8x8x8 bank")
    return {
        "manifest": manifest,
        "selected": {"atten_code": atten_code, "rs_code": rs_code,
                     "cs_code": cs_code},
        "rs_cs_switches_verified": False,
    }


def _box(ax, xy, width, height, *, face, edge, radius=0.02, lw=1.5):
    patch = FancyBboxPatch(
        xy, width, height,
        boxstyle=f"round,pad=0.012,rounding_size={radius}",
        facecolor=face, edgecolor=edge, linewidth=lw)
    ax.add_patch(patch)
    return patch


def _code_table(ax, block: dict, x: float, y: float, width: float,
                selected: int, value_key: str, formatter) -> None:
    row_h = 0.040
    for index, row in enumerate(block["codes"]):
        yy = y - index * row_h
        chosen = int(row["code"]) == selected
        ax.add_patch(Rectangle(
            (x, yy - 0.027), width, 0.033,
            facecolor=(PALE_BLUE if chosen else "white"),
            edgecolor=(BLUE if chosen else LINE), linewidth=(1.5 if chosen else 0.6)))
        ax.text(x + 0.010, yy - 0.011, f"{row['code']}", ha="left",
                va="center", fontsize=7.3, fontweight=("bold" if chosen else "normal"))
        ax.text(x + width - 0.010, yy - 0.011, formatter(row[value_key]),
                ha="right", va="center", fontsize=7.3,
                color=(BLUE if chosen else INK),
                fontweight=("bold" if chosen else "normal"))


def draw_programmable_architecture(design: dict, out_path) -> Path:
    """Write a judge-facing PNG of the functional code-controlled hardware."""
    model = architecture_model(design)
    manifest = model["manifest"]
    selected = model["selected"]
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(14.4, 8.1), dpi=180)
    fig.patch.set_facecolor("white")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    request = design.get("request") or {}
    fig.text(0.055, 0.945, "Nebula programmable CTLE architecture",
             ha="left", fontsize=18, fontweight="bold", color=INK)
    fig.text(
        0.055, 0.905,
        f"Request  {float(request.get('peaking_db', 0)):.1f} dB @ "
        f"{float(request.get('f_peak_hz', 0))/1e9:.3f} GHz   |   "
        f"selected A{selected['atten_code']} / R{selected['rs_code']} / "
        f"C{selected['cs_code']}   |   8 x 8 x 8 = 512 logical settings",
        ha="left", fontsize=10.5, color=MUTED)

    # Controller and decode path.
    _box(ax, (0.04, 0.70), 0.16, 0.12, face=PALE_BLUE, edge=BLUE)
    ax.text(0.12, 0.775, "RL proposer", ha="center", va="center",
            fontsize=11, fontweight="bold", color=BLUE)
    ax.text(0.12, 0.735, "+ safety shield", ha="center", va="center",
            fontsize=9, color=INK)
    ax.annotate("A/R/C code", xy=(0.265, 0.76), xytext=(0.205, 0.76),
                arrowprops=dict(arrowstyle="->", lw=1.8, color=BLUE),
                ha="center", va="bottom", fontsize=8, color=BLUE)
    _box(ax, (0.275, 0.70), 0.13, 0.12, face="white", edge=BLUE)
    ax.text(0.34, 0.772, "3 decoders", ha="center", fontsize=10,
            fontweight="bold")
    ax.text(0.34, 0.735, "A[2:0] R[2:0] C[2:0]", ha="center", fontsize=8)

    # Actual attenuator, shown as a differential series-shunt network.
    _box(ax, (0.44, 0.59), 0.25, 0.28, face=PALE_GREEN, edge=GREEN)
    ax.text(0.565, 0.835, "INPUT ATTENUATOR", ha="center", fontsize=11,
            fontweight="bold", color=GREEN)
    ax.text(0.565, 0.806, "NETLISTED + REAL-PMOS MEASURED", ha="center",
            fontsize=7.8, fontweight="bold", color=GREEN)
    for yy, label in ((0.755, "IN+"), (0.685, "IN-")):
        ax.text(0.457, yy, label, ha="left", va="center", fontsize=8)
        ax.plot([0.49, 0.545], [yy, yy], color=INK, lw=1.5)
        ax.add_patch(Rectangle((0.505, yy - 0.012), 0.028, 0.024,
                               facecolor="white", edgecolor=INK, lw=1.0))
        ax.text(0.519, yy + 0.020, "150R", ha="center", fontsize=6.3)
        ax.plot([0.545, 0.665], [yy, yy], color=INK, lw=1.5)
        for xx, bit in ((0.565, "b0"), (0.605, "b1"), (0.645, "b2")):
            ax.plot([xx, xx], [yy, yy - 0.020], color=INK, lw=0.9)
            ax.text(xx, yy - 0.031, bit, ha="center", fontsize=6.2)
    ax.text(0.565, 0.608, "3 binary resistor + PMOS shunt legs / side -> VCM",
            ha="center", fontsize=7.5, color=MUTED)

    # CTLE and source degeneration selectors.
    ax.annotate("", xy=(0.735, 0.74), xytext=(0.695, 0.74),
                arrowprops=dict(arrowstyle="->", lw=1.8, color=GREEN),
                ha="left", va="bottom", fontsize=7.5, color=GREEN)
    _box(ax, (0.75, 0.65), 0.20, 0.18, face="#F4F5F7", edge=INK)
    ax.text(0.85, 0.785, "1-stage CTLE core", ha="center", fontsize=11,
            fontweight="bold")
    ax.text(0.85, 0.722, "SKY130 differential pair", ha="center", fontsize=8)
    ax.text(0.85, 0.692, "fixed input devices, bias and load", ha="center",
            fontsize=7.5, color=MUTED)
    ax.text(0.85, 0.662, "source degeneration <- Rs || Cs", ha="center",
            fontsize=8.5, color=INK)

    # Tables show every exact selectable target carried by this design.
    ax.text(0.09, 0.550, "Rs target bank", ha="left", fontsize=11,
            fontweight="bold")
    ax.text(0.09, 0.525, "code     target resistance", ha="left", fontsize=7,
            color=MUTED)
    _code_table(ax, manifest["rs_bank"], 0.09, 0.490, 0.205,
                selected["rs_code"], "target_ohm", lambda v: f"{v:.2f} ohm")
    ax.text(0.37, 0.550, "Cs target bank", ha="left", fontsize=11,
            fontweight="bold")
    ax.text(0.37, 0.525, "code     target capacitance", ha="left", fontsize=7,
            color=MUTED)
    _code_table(ax, manifest["cs_bank"], 0.37, 0.490, 0.205,
                selected["cs_code"], "target_f", lambda v: f"{v*1e12:.4f} pF")
    ax.text(0.65, 0.550, "Input attenuation codes", ha="left", fontsize=11,
            fontweight="bold")
    ax.text(0.65, 0.525, "code     attenuation", ha="left", fontsize=7,
            color=MUTED)
    _code_table(ax, manifest["attenuator"], 0.65, 0.490, 0.205,
                selected["atten_code"], "attenuation_db", lambda v: f"{v:.3f} dB")

    _box(ax, (0.05, 0.055), 0.90, 0.115, face=PALE_ORANGE, edge=ORANGE,
         radius=0.015, lw=1.7)
    ax.text(0.075, 0.132, "IMPLEMENTATION BOUNDARY", ha="left", va="center",
            fontsize=9.5, fontweight="bold", color=ORANGE)
    ax.text(
        0.075, 0.095,
        "Rs/Cs selector switches and their parasitics are NOT NETLISTED or "
        "transistor-level verified. The evidence is 64 separately drawn "
        "passive variants.",
        ha="left", va="center", fontsize=8.7, color=INK)
    ax.text(
        0.075, 0.068,
        "Therefore this figure is a complete logical architecture and status "
        "map, not a claim of a tapeout-ready switch matrix.",
        ha="left", va="center", fontsize=8.2, color=MUTED)

    fig.savefig(out, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    return out


__all__ = ("architecture_model", "draw_programmable_architecture")
