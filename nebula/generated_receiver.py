"""Connect an accepted generated CTLE to the established transistor DFE.

The selected CTLE deck remains the source of truth.  This module replaces only
its analysis control block and input stimulus, then appends the already tested
Entry 125 CML memory, current summer, feedback DAC and bleed devices.  There is
no ideal decision or behavioral cancellation in the generated receiver deck.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from nebula.common.types import Corner, UI_SECONDS as UI
from nebula.device import dfe_cml as C
from nebula.device import dfe_connected as F
from nebula.device import dfe_hardware as D
from nebula.device import dfe_tail_bleed as B
from nebula.device import dfe_timing as T
from nebula.device import dfe_voltage_audit as V
from nebula.experiments import exp_physical_bias as P
from nebula.experiments import exp_dfe_connected as E
from nebula.experiments import exp_dfe_tail_bleed as H
from nebula.experiments import spice_capture
from nebula.link.config import LinkConfig


PHASE_UI = 1.0
TAP_CODE = 2
TAP_SIGN = 1
BLEED_LENGTH_UM = 4.0


def _accepted(design: dict) -> None:
    verification = design.get("verification") or {}
    if (design.get("method") != "rl-physical"
            or verification.get("n_pass") != verification.get("n_points")
            or not verification.get("n_points")):
        raise ValueError("receiver export requires an accepted physical design")


def _selected_deck(design: dict, source: str) -> None:
    expected = (design.get("physical_evidence") or {}).get("deck_sha256")
    actual = hashlib.sha256(source.encode("ascii")).hexdigest()
    if not expected or actual != expected:
        raise ValueError("selected CTLE deck hash mismatch")


def build_deck(design: dict, selected_deck: str, *,
               corner: Corner = Corner("tt", 1.0, 27),
               channel_loss_db: float = 7.5) -> str:
    """Return one exact selected-CTLE plus transistor-DFE transient deck."""
    _accepted(design)
    _selected_deck(design, selected_deck)
    cfg = LinkConfig(channel_loss_db_at_nyquist=channel_loss_db)
    bits = F.pattern(cfg)
    base = P.corner_deck(selected_deck, corner.process, corner.vdd_scale,
                         corner.temp_c).split(".control", 1)[0].rstrip()
    t, v = F.stimulus(cfg, bits)
    stimulus = "Vid vid 0 PWL(\n" + "\n".join(
        f"+ {a:.16g} {b:.16g}" for a, b in zip(t, v)) + "\n+ )"
    base, count = re.subn(r"^Vid\s+.*$", lambda _: stimulus, base, flags=re.M)
    if count != 1:
        raise ValueError("selected CTLE deck has no unique input source")

    vdd = 1.8 * corner.vdd_scale
    lines = [base,
             "* Generated receiver: selected physical CTLE + transistor 1-tap DFE",
             "* External stimulus/clock/tap controls are verification apparatus."]
    for name, lo, hi in (("clk", vdd/3, 2*vdd/3),
                         ("clkb", 2*vdd/3, vdd/3)):
        lines.append(
            f"Vdf{name} df_{name} 0 PULSE({lo:.16g} {hi:.16g} "
            f"{F.edge_time(0, PHASE_UI):.16g} {C.EDGE_S:.16g} {C.EDGE_S:.16g} "
            f"{UI/2-2*C.EDGE_S:.16g} {UI:.16g})")
    for index in range(4):
        level = vdd if TAP_CODE & (1 << index) else 0.0
        lines.append(f"Vtap{index} tap{index} 0 {level:.16g}")
    lines.extend(F.extra_mos(TAP_SIGN))
    lines.extend(F.extra_resistors())
    lines.extend(B.bleeders(BLEED_LENGTH_UM))
    circuit = "\n".join(lines)
    terminals = D.terminal_nodes(F.all_mos(circuit))
    lines.extend([
        ".control", "set noaskquit", "set numdgt=15", "set wr_singlescale",
        f"tran 1p {F.STOP_UI*UI:.16g} 0 1p",
        "wrdata trace.txt " + " ".join(F.VECTORS),
        "wrdata terminals.txt " + " ".join(f"v({name})" for name in terminals),
        "quit", ".endc", ".end",
    ])
    deck = "\n".join(lines) + "\n"
    if deck.count(".lib ") != 1 or deck.count(".control") != 1:
        raise ValueError("generated receiver has ambiguous model/control ownership")
    return deck


def export(design: dict, selected_deck: str, directory: Path) -> dict:
    """Write the connected deck without treating generation as verification."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    deck = build_deck(design, selected_deck)
    path = directory / "receiver.cir"
    path.write_text(deck, encoding="ascii", newline="\n")
    return {
        "schema": "nebula-generated-transistor-receiver-v1",
        "structurally_integrated": True,
        "selected_ctle_deck_sha256": hashlib.sha256(
            selected_deck.encode("ascii")).hexdigest(),
        "receiver_deck_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "nominal_transistor_verified": False,
        "full_receiver_verified": False,
        "phase_ui": PHASE_UI,
        "tap_code": TAP_CODE,
        "tap_sign": TAP_SIGN,
        "scope": ("Exact selected physical CTLE connected to a transistor CML "
                  "summer, decision memory and current DAC; external clocks and "
                  "controls; verification is a separate gate."),
    }


def verify_nominal(design: dict, selected_deck: str, directory: Path) -> dict:
    """Measure one nominal connected-receiver case with the established gates.

    This is one externally clocked, finite-pattern check at the registered
    phase/code and 7.5 dB constructed channel. It does not establish full PVT.
    """
    directory = Path(directory)
    if directory.exists():
        raise FileExistsError(f"verification directory already exists: {directory}")
    corner = Corner("tt", 1.0, 27)
    loss = 7.5
    calls = 0
    try:
        deck = build_deck(design, selected_deck, corner=corner,
                          channel_loss_db=loss)
        cfg = LinkConfig(channel_loss_db_at_nyquist=loss)
        bits = F.pattern(cfg)
        calls += 1
        spice_capture.invoke(deck, directory)
        t, y = T.read_table(directory / "trace.txt", len(F.VECTORS))
        result = F.analyze(t, y, bits, cfg, PHASE_UI, 1.8, code=TAP_CODE)
        mos = F.all_mos(deck)
        names = D.terminal_nodes(mos)
        _, ny = T.read_table(directory / "terminals.txt", len(names),
                             expected_time=t)
        nodes = dict(zip(names, ny.T))
        whole = V.audit(mos, nodes)
        new = V.audit(F.extra_mos(TAP_SIGN) + B.bleeders(BLEED_LENGTH_UM), nodes)
        result.update(
            instrument_ok=True,
            new_dfe_voltage_audit=new,
            whole_circuit_voltage_audit=whole,
            whole_circuit_voltage_envelope_pass=E.envelope(whole),
            aperture=T.aperture(t, y[:, 3] - y[:, 4], bits, PHASE_UI))
        # Refuse non-JSON/NaN measurements before recording any positive gate.
        json.dumps(result, allow_nan=False)
        result["signal_gate_pass"] = bool(H.accepted(result))
    except Exception as exc:
        directory.mkdir(parents=True, exist_ok=True)
        result = {"instrument_ok": False, "logic_pass": False,
                  "signal_gate_pass": False,
                  "fail_reason": f"{type(exc).__name__}: {exc}"}
    result.update(
        phase_ui=PHASE_UI, code=TAP_CODE, sign=TAP_SIGN,
        length_um=BLEED_LENGTH_UM, corner=str(corner), loss_db=loss,
        nominal_transistor_verified=result["signal_gate_pass"],
        full_receiver_verified=False, spice_calls=calls,
        scope="Nominal finite-pattern transistor check only; external clock and controls, fixed phase/tap, constructed 7.5 dB channel; no analog or link PVT claim.")
    P.write_json(directory / "result.json", result)
    return result


__all__ = ["build_deck", "export", "verify_nominal"]
