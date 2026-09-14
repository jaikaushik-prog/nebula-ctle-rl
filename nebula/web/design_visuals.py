"""Selected-run eye opening reconstructed from saved AC; never reruns SPICE."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np


def selected_eye(directory: Path) -> dict:
    from nebula.link.config import LinkConfig
    from nebula.link.fit import fit_ctle
    from nebula.link.cursors import (DEFAULT_OSR, pulse_response,
                                    cursors_from_pulse, eye_opening_vs_phase)

    directory = Path(directory)
    design = json.loads((directory / "design.json").read_text(encoding="utf-8"))
    if design.get("method") != "rl-physical":
        raise ValueError("This bank artifact records eye dimensions but does not retain its AC samples. No eye trace is reconstructed from scalar values.")
    root = directory / "physical_evidence"
    manifest = json.loads((root / "evidence_sha256.json").read_text(encoding="utf-8"))
    manifest = {k.replace(chr(92), "/"): v for k, v in manifest.items()}
    ac_name = "tt_1.00_27/ac_noise/ac.txt"
    used = {}
    for name in ("design.cir", ac_name):
        digest = hashlib.sha256((root / name).read_bytes()).hexdigest()
        if manifest.get(name) != digest:
            raise ValueError(f"Selected eye source hash mismatch: {name}")
        used[name] = digest
    if used["design.cir"] != design.get("physical_evidence", {}).get("deck_sha256"):
        raise ValueError("The saved AC evidence does not identify the selected deck.")
    ac = np.loadtxt(root / ac_name)
    meas = design["nominal"]["meas"]
    fit = fit_ctle(ac[:, 0], ac[:, 1], measured_g_dc_db=meas["g_dc_db"])
    if not fit.ok:
        raise ValueError(f"Selected AC fit rejected: {fit.fail_reason}")
    loss = float(design["search"]["representative_channel_loss_db"])
    cfg = LinkConfig(channel_loss_db_at_nyquist=loss)
    pulse = pulse_response(cfg.channel, cfg.tx, fit)
    cursor = int(np.argmax(pulse))
    cursors = cursors_from_pulse(pulse, DEFAULT_OSR, cursor, label="selected web run")
    eye = eye_opening_vs_phase(pulse, DEFAULT_OSR, cursor)
    if not (np.isclose(cursors.eye_h_v, meas["eye_h_v"], rtol=1e-7, atol=1e-9)
            and np.isclose(eye.width_ui, meas["eye_w_ui"], atol=1e-12)):
        raise ValueError("Reconstructed eye disagrees with the selected run's recorded dimensions.")
    return {"kind": "worst-case-isi-envelope", "phase_ui": eye.phase_ui.tolist(),
            "height_v": eye.eye_h_v.tolist(), "eye_h_v": cursors.eye_h_v,
            "eye_w_ui": eye.width_ui, "channel_loss_db": loss,
            "design_id": design["nominal"]["design_id"], "source_sha256": used,
            "scope": "Saved transistor AC + constructed channel + ideal 1-tap DFE. Worst-case ISI opening, not a transistor transient or BER measurement."}
