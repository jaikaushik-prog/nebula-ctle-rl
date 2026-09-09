"""Replay every frozen Entry 133 PVT waveform, without running SPICE."""
import json
from pathlib import Path

import pytest

from nebula.common.types import all_corners
from nebula.device import dfe_configurable as C, dfe_configurable_pvt as Q
from nebula.experiments import evidence_archive as A
from nebula.link.config import LinkConfig

ROOT = Path(__file__).resolve().parents[1] / 'product_audits/entry133_dfe_configurable_pvt_20260910'
# Preserve the actual scheduler objects: its five screens use integer
# temperatures, whereas all_corners uses floats. Do not normalize raw decks.
RUN_CORNERS = Q.SCREENS + tuple(c for c in all_corners() if c not in Q.SCREENS)


def test_complete_pvt_manifest_and_fixed_schedule():
    assert A.digest(ROOT / 'summary.json') == '17887e5aa9e10fe7692e0c12fe103d7a4588432061f4dae9be4286062081f09d'
    assert A.verify(ROOT) == {
        'verified_files': 336, 'verified_archives': 90,
        'manifest_sha256': '01083693b0c963b62789d96584470d3918ab844c313debfc21ea3daa0bfd1585',
    }
    summary = json.loads((ROOT / 'summary.json').read_text())
    config = json.loads((ROOT / 'config.json').read_text())
    assert summary['spice_calls'] == summary['attempted_cases'] == 45
    assert summary['primary_channel_pvt_pass'] and summary['sources_unchanged'] and summary['pdk_unchanged']
    assert not summary['corner_retuning'] and not summary['full_receiver_verified']
    assert not summary['runtime_settling_verified']
    assert config['r_fraction'] == .7 and config['c_fraction'] == .165
    assert config['fixed_phase_ui'] == 1 and config['fixed_code'] == 2 and config['fixed_sign'] == 1
    assert config['channel_loss_db'] == 7.5
    assert {row['corner'] for row in summary['pvt']} == {str(c) for c in all_corners()}
    replay = Q.schedule(lambda c: json.loads((ROOT / f'pvt_{c}' / 'result.json').read_text()))
    assert all(value == summary[key] for key, value in replay.items())
    measured = [row['result'] for row in summary['pvt']]
    assert all(C.accepted(r) and r['correct_bits'] == r['scored_bits'] == 64 for r in measured)
    assert all(r['new_dfe_voltage_audit']['documented_ranges_ok'] for r in measured)
    assert all(r['whole_circuit_voltage_envelope_pass'] for r in measured)
    # Preserve the bilateral switch's actual signed-domain qualification.
    assert not any(r['new_tuning_switch_voltage_audit']['documented_ranges_ok'] for r in measured)
    assert all(r['new_tuning_switch_voltage_audit']['devices'][0]['vds']['min_v'] < 0 for r in measured)
    assert min(r['sampled_eye_height_v'] for r in measured) == pytest.approx(.10975761563611197, abs=1e-12)
    assert max(r['ctle_plus_dfe_vdd_power_w'] for r in measured) == pytest.approx(.012524099064111234, abs=1e-12)
    assert min(r['aperture']['eye_width_ui'] for r in measured) == .63
    assert min(r['aperture']['eye_width_at_100mv_ui'] for r in measured) == .555


@pytest.mark.parametrize('corner', RUN_CORNERS, ids=str)
def test_every_pvt_case_replays_compressed_raw_and_exact_deck(corner):
    folder = ROOT / f'pvt_{corner}'
    saved = json.loads((folder / 'result.json').read_text())
    reference = json.loads((ROOT / 'nominal_reference.json').read_text())
    config = json.loads((ROOT / 'config.json').read_text())
    text = (folder / 'design.cir').read_text()
    cfg = LinkConfig(channel_loss_db_at_nyquist=7.5)
    assert text == C.deck(True, corner, cfg, config['bits'], 1., 2, 1)
    actual = Q.extract(folder, text, corner, reference)
    assert actual == {key: value for key, value in saved.items() if key != 'corner'}
    assert actual['nominal_replay_matches'] is (True if corner.is_nominal else None)
