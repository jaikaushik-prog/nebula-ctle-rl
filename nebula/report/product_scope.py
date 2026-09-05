"""Export-derived area inventory and explicit limits of product verification.

The frozen RL area field is a passive-only proxy. This reporting module never
changes that historical field or treats drawn bodies/gates as a layout footprint.
"""
from __future__ import annotations

import hashlib
import math
import re

from nebula.report.schematic import params_of


def circuit_lines(deck: str) -> list[str]:
    """Top-level circuit only; measurement commands are not components."""
    lines = []
    for raw in deck.splitlines():
        line = raw.strip().lower()
        if line == ".control":
            break
        if not line or line.startswith("*"):
            continue
        if line.startswith("+"):
            raise ValueError("continued circuit lines require an explicit parser update")
        lines.append(" ".join(line.split()))
    return lines


def circuit_signature(deck: str) -> str:
    """Freeze topology, values and switch states; allow PVT/stimulus changes.

Only library selection, temperature, VDD's parameter value and the optional
transient suffix on Vid may differ. Bias/common-mode and every geometry stay.
"""
    lines = []
    for line in circuit_lines(deck):
        if line.startswith((".lib ", ".temp ")):
            continue
        if line.startswith(".param "):
            line = re.sub(r"\bvdd=[-+0-9.e]+", "vdd=<pvt>", line)
        if line.startswith("vid "):
            line = re.sub(r" sin\([^)]*\)$", "", line)
        lines.append(line)
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def area_inventory(deck: str) -> dict:
    """Account for every top-level component, retaining unimplemented items.

W is total MOS width in this runner; nf divides it into fingers. Multiplying
W*L by nf again would overcount. Device m, including OFF branches, does count.
MOS gate area and passive body/plate area are geometry proxies, NOT cell area.
"""
    params = {k.lower(): v for k, v in params_of(deck).items()}

    def number(token):
        value = params[token[1:-1]] if token.startswith("{") else float(token)
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"invalid physical dimension/value: {token}")
        return value

    components = []
    for line in circuit_lines(deck):
        if line.startswith("."):
            continue
        words = line.split()
        name = words[0]
        row = {"name": name, "netlist_line": line, "geometry_um2": None}
        if name.startswith("x"):
            attrs = dict(re.findall(r"\b(\w+)\s*=\s*([^\s]+)", line))
            model = next((word for word in words if word.startswith("sky130_")), "")
            if model not in ("sky130_fd_pr__res_high_po", "sky130_fd_pr__cap_mim_m3_1",
                             "sky130_fd_pr__nfet_01v8", "sky130_fd_pr__pfet_01v8"):
                raise ValueError(f"unknown physical model on {name}: {model}")
            try:
                w, l, m = number(attrs["w"]), number(attrs["l"]), number(attrs.get("m", "1"))
            except (KeyError, ValueError) as exc:
                raise ValueError(f"unresolved geometry on {name}: {exc}") from exc
            row.update(model=model, w_um=w, l_um=l, multiplier=m,
                       geometry_um2=w * l * m,
                       kind="mos_gate" if "fet_" in model else "passive_body_plate")
        elif name in ("clp", "cln"):
            row.update(kind="external_load_assumption", value=number(words[-1]))
        elif name == "cbyp":
            row.update(kind="unimplemented_bias_capacitor", value=number(words[-1]))
        elif name == "iref":
            row.update(kind="unimplemented_bias_source", value=number(words[-1]))
        elif name in ("vdd", "vcm", "vid", "einp", "einn"):
            row["kind"] = "supply_or_testbench"
        else:
            row["kind"] = "unimplemented_element"
        components.append(row)
    if len({r["name"] for r in components}) != len(components):
        raise ValueError("duplicate component names in exported circuit")
    passive = sum(r["geometry_um2"] for r in components if r["kind"] == "passive_body_plate")
    mos = sum(r["geometry_um2"] for r in components if r["kind"] == "mos_gate")
    legacy = sum(r["geometry_um2"] for r in components if r["name"] in ("xrs", "xcs", "xrlp", "xrln"))
    return {
        "deck_sha256": hashlib.sha256(deck.encode()).hexdigest(),
        "components": components,
        "legacy_passive_area_mm2": legacy * 1e-6,
        "passive_body_plate_mm2": passive * 1e-6,
        "mos_gate_area_mm2": mos * 1e-6,
        "geometry_subtotal_mm2": (passive + mos) * 1e-6,
        "full_area_mm2": None, "layout_overhead_mm2": None,
        "s7_status": "NOT_VERIFIED",
        "unresolved": [r["name"] for r in components if r["kind"].startswith("unimplemented")],
        "not_in_netlist": ["transistor-level DFE/slicer/clocking",
                           "physical Rs/Cs selector and control logic",
                           "bias/common-mode generation",
                           "contacts, diffusion, wells, guards, routing, spacing and floorplan"],
        "note": "Geometry subtotal only, not laid-out cell/core area. No arbitrary overhead factor. "
                "Cbyp has a capacitance but no physical implementation. CLp/CLn are assumed "
                "external loads; an integrated receiver must account for their realization.",
    }


def implementation_scope(design: dict) -> dict:
    adaptive = design.get("method") == "rl-hybrid"
    verification_note = (
        "Recorded PVT results use an adaptive per-condition setting map; they do not "
        "verify the single exported setting across PVT."
        if adaptive else "Results describe only the recorded circuit/link model and tested conditions."
    )
    audit = design.get("product_readiness_audit") or {}
    fixed = audit.get("fixed") or {}
    audit_notes = []
    if fixed and fixed.get("setting") == (design.get("search") or {}).get("setting"):
        audit_notes.append(
            f"Separate fixed-code audit: {fixed.get('n_representative_pvt_pass')}/"
            f"{fixed.get('n_corners')} PVT corners and {fixed.get('n_model_pass')}/"
            f"{fixed.get('n_expected_conditions')} model conditions pass. "
            "This result does not replace the adaptive map above.")
    return {
        "full_product_compliance": False,
        "area_status": "NOT_VERIFIED",
        "power_scope": "SPICE CTLE supply power; full receiver power is not verified.",
        "dfe_scope": "Behavioural 1-tap DFE; no transistor-level DFE, slicer or clock implementation.",
        "verification_note": verification_note,
        "notes": [verification_note, *audit_notes,
                  "S7 full area is not verified: the legacy number includes Rs, Cs and two RL bodies only.",
                  "Power is CTLE-only; DFE and full bias/control implementation are not included.",
                  "DFE is behavioural; physical Rs/Cs selector switches remain unimplemented."],
    }
