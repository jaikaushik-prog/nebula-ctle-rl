"""Full immutable calibrated PVT archive and all 45 real waveform replays."""
import json
import pytest
from nebula.common.types import all_corners
from nebula.experiments import exp_dfe_calibrated_pvt as E, evidence_archive as A
ROOT=E.ROOT/'nebula/product_audits/entry144_dfe_calibrated_pvt_20260910'

def test_complete_calibrated_pvt_archive():
    assert A.verify(ROOT)=={'verified_files':362,'verified_archives':90,
        'manifest_sha256':'c5213fb228fc450b882b2ce7b4be7219adc6f352d63315b5195af32a4e63afe1'}
    assert A.digest(ROOT/'summary.json')=='21a6b7cb5d81bd0e23981d2cc3741a9a0147b6793f401d63c646c5e08f06e424'

def test_measured_fixed_setting_schedule_and_extrema():
    s=json.loads((ROOT/'summary.json').read_text())
    assert s['spice_calls']==45 and s['primary_channel_pvt_pass']
    assert s['sources_unchanged'] and s['pdk_unchanged'] and not s['corner_retuning']
    assert not s['analog_pvt_verified'] and not s['full_receiver_verified']
    assert (s['r_fraction'],s['c_fraction'])==(.7,.185)
    replay=E.schedule(lambda c:json.loads((ROOT/f'pvt_{c}/result.json').read_text()))
    assert all(s[k]==v for k,v in replay.items())
    rows=[x['result'] for x in s['pvt']]
    assert min(r['sampled_eye_height_v'] for r in rows)==pytest.approx(.11324371549900603)
    assert min(r['aperture']['eye_width_ui'] for r in rows)==pytest.approx(.635)
    assert min(r['aperture']['eye_width_at_100mv_ui'] for r in rows)==pytest.approx(.56)
    assert max(r['ctle_plus_dfe_vdd_power_w'] for r in rows)==pytest.approx(.0125240811345151)
    assert all(r['correct_bits']==64 and r['new_dfe_voltage_audit']['documented_ranges_ok'] for r in rows)
    assert all(not r['new_tuning_switch_voltage_audit']['documented_ranges_ok'] for r in rows)

# Replay the actual scheduler's inputs: its five screen objects use integer
# temperatures, whereas all_corners() uses floats. Never normalize raw decks.
CORNERS=(*E.Q.SCREENS,*(c for c in all_corners() if c not in E.Q.SCREENS))
@pytest.mark.parametrize('corner',CORNERS)
def test_every_actual_calibrated_corner_replays(corner):
    folder=ROOT/f'pvt_{corner}';text=(folder/'design.cir').read_text()
    assert text==E.deck(corner)
    reference=json.loads((ROOT/'nominal_reference.json').read_text())
    actual=E.extract(folder,text,corner,reference)
    saved=json.loads((folder/'result.json').read_text())
    assert actual=={k:v for k,v in saved.items() if k!='corner'}
    assert actual['signal_gate_pass'] and actual['correct_bits']==64
