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
            "waveform": waveform_eye(pulse, cfg),
            "ac": {"frequency_ghz": (ac[(ac[:, 0] >= 1e7) & (ac[:, 0] <= 1e10), 0] / 1e9).tolist(),
                   "gain_db": ac[(ac[:, 0] >= 1e7) & (ac[:, 0] <= 1e10), 1].tolist(),
                   "target_peak_ghz": design["request"]["f_peak_ghz"],
                   "measured_peak_ghz": meas["_f_peak_ghz"],
                   "dc_gain_db": meas["g_dc_db"], "peaking_db": meas["peaking_db"]},
            "cursors": {"h0_v": cursors.h0_v, "h1_v": cursors.taps[1],
                        "h2_v": cursors.taps[2], "tap": cursors.dfe_tap,
                        "without_dfe_eye_h_v": max(0., 2 * (cursors.h0_v - cursors.residual_abs_v - abs(cursors.taps[1])))},
            "scope": "Saved transistor AC + constructed channel + ideal 1-tap DFE. Worst-case ISI opening, not a transistor transient or BER measurement."}


def waveform_eye(pulse: np.ndarray, cfg) -> dict:
    """Steady-state periodic NRZ through the same complete LTI pulse buffer.

    The ideal DFE uses the known previous bit and the fixed sampled h1 tap.
    Its rectangular feedback updates midway between sample instants. This is
    an explicitly ideal waveform illustration, not a transistor DFE run or
    the phase-by-phase retuned tap used by the conservative width envelope.
    Circular convolution matches the canonical full-buffer cursor convention;
    there is no startup padding, clipped pulse tail or invented noise.
    """
    from nebula.link.cursors import DEFAULT_OSR, cursors_from_pulse

    osr = DEFAULT_OSR
    pulse = np.asarray(pulse, dtype=float)
    if pulse.ndim != 1 or pulse.size % osr or not np.isfinite(pulse).all():
        raise ValueError("Invalid canonical pulse buffer for waveform eye.")
    n_bits = pulse.size // osr
    bits = 2 * np.random.default_rng(cfg.seed).integers(0, 2, n_bits) - 1
    impulse = np.zeros(pulse.size)
    impulse[::osr] = bits
    wave = np.fft.ifft(np.fft.fft(impulse) * np.fft.fft(pulse)).real
    cursor = int(np.argmax(pulse))
    taps = cursors_from_pulse(pulse, osr, cursor, label="waveform eye")
    sample_owner = np.floor_divide(np.arange(pulse.size) - cursor + osr // 2, osr)
    corrected = wave - taps.taps[1] * bits[(sample_owner - 1) % n_bits]
    bit_indices = np.arange(0, n_bits, max(1, n_bits // 128))[:128]
    offsets = np.arange(-osr, osr + 1)
    indices = (cursor + bit_indices[:, None] * osr + offsets) % pulse.size
    before, after = wave[indices], corrected[indices]
    if not np.isfinite(before).all() or not np.isfinite(after).all():
        raise ValueError("Non-finite waveform eye.")
    return {"time_ui": (offsets / osr).tolist(),
            "ctle_v": before.tolist(), "ideal_dfe_v": after.tolist(),
            "previous_bits": bits[(bit_indices - 1) % n_bits].tolist(),
            "sample_bits": bits[bit_indices].tolist(), "h1_v": taps.taps[1],
            "seed": cfg.seed, "period_bits": n_bits, "segments": len(bit_indices),
            "samples_per_ui": osr, "ui_ps": 1e12 / cfg.fbaud_hz,
            "scope": "Modeled noiseless periodic NRZ from saved transistor AC. Ideal fixed-tap DFE uses the known previous bit with rectangular feedback; no decision errors, clock circuit, jitter or noise are simulated. This waveform is not a transistor transient or BER measurement."}
