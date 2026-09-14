"""Independent checks for the selected-run modeled waveform illustration."""
from dataclasses import replace

import numpy as np
import pytest

from nebula.link.config import LinkConfig
from nebula.link.cursors import DEFAULT_OSR
from nebula.web.design_visuals import waveform_eye


def test_waveform_matches_explicit_symbol_superposition_and_fixed_feedback():
    """Compare FFT output against direct shifted-pulse summation in volts."""
    osr = DEFAULT_OSR
    pulse = np.zeros(16 * osr)
    cursor = osr // 2
    pulse[cursor] = .2
    pulse[cursor + osr] = .04
    pulse[cursor + 2 * osr] = -.01
    cfg = LinkConfig(channel_loss_db_at_nyquist=7.5, seed=29)
    result = waveform_eye(pulse, cfg)
    bits = 2 * np.random.default_rng(cfg.seed).integers(0, 2, 16) - 1
    reference = sum(bit * np.roll(pulse, k * osr)
                    for k, bit in enumerate(bits))
    offsets = np.arange(-osr, osr + 1)
    indices = (cursor + np.arange(16)[:, None] * osr + offsets) % pulse.size
    np.testing.assert_allclose(result["ctle_v"], reference[indices], atol=1e-15)
    before = np.asarray(result["ctle_v"])[:, osr]
    after = np.asarray(result["ideal_dfe_v"])[:, osr]
    np.testing.assert_allclose(before - after, .04 * np.roll(bits, 1), atol=1e-15)
    # One previous symbol is removed, while the second postcursor remains.
    np.testing.assert_allclose(after, .2 * bits - .01 * np.roll(bits, 2), atol=1e-15)
    assert min(after[bits == 1]) >= .19 - 1e-15
    assert max(after[bits == -1]) <= -.19 + 1e-15
    assert result["ui_ps"] == 200
    assert result["time_ui"][osr] == 0


def test_waveform_seed_and_voltage_scaling_are_explicit():
    osr = DEFAULT_OSR
    pulse = np.zeros(16 * osr)
    pulse[:osr] = np.linspace(.01, .2, osr)
    cfg = LinkConfig(channel_loss_db_at_nyquist=7.5, seed=11)
    a = waveform_eye(pulse, cfg)
    assert a == waveform_eye(pulse, cfg)
    b = waveform_eye(3 * pulse, cfg)
    np.testing.assert_allclose(b["ctle_v"], 3 * np.asarray(a["ctle_v"]), atol=1e-14)
    np.testing.assert_allclose(b["ideal_dfe_v"], 3 * np.asarray(a["ideal_dfe_v"]), atol=1e-14)
    assert a["sample_bits"] != waveform_eye(pulse, replace(cfg, seed=12))["sample_bits"]


@pytest.mark.parametrize("pulse", [np.array([np.nan] * 64), np.zeros((64, 64)), np.ones(65)])
def test_waveform_rejects_invalid_buffers(pulse):
    with pytest.raises(ValueError):
        waveform_eye(pulse, LinkConfig(channel_loss_db_at_nyquist=7.5))
