"""Replay the complete first connected configurable-DUT experiment."""
import json
from pathlib import Path

import pytest

from nebula.device import dfe_configurable as C
from nebula.experiments import evidence_archive as A
from nebula.experiments.exp_dfe_configurable import extract

ROOT=Path(__file__).resolve().parents[1]/'product_audits/entry132_dfe_configurable_20260910'
CASES=('calibration_tuned0_phase1_code2_sign1','phase_tuned1_phase1_code2_sign1',
       'phase_tuned1_phase1.25_code2_sign1','phase_tuned1_phase1.5_code2_sign1',
       'phase_tuned1_phase1.75_code2_sign1','control_tuned1_phase1_code0_sign1','control_tuned1_phase1_code2_sign-1')


def test_complete_connected_evidence_preserves_failed_phase_and_controls():
    assert A.digest(ROOT/'summary.json')=='73f15bc9b236f1ee404ed2a40ce667ad2f78e9963c78a611f8909eade81e879a'
    assert A.verify(ROOT)=={'verified_files':104,'verified_archives':14,'manifest_sha256':'cf349cc4fc451e16ffe99348a9be7e0ee8805ad02c08497e7e8e1070bae06e46'}
    s=json.loads((ROOT/'summary.json').read_text())
    assert s['primary_connected_pass'] and s['selected_phase_ui']==1.
    assert s['spice_calls']==s['attempted_cases']==7 and s['pdk_unchanged'] and s['sources_unchanged']
    assert not s['full_receiver_verified'] and not s['runtime_settling_verified']
    assert [r['result']['signal_gate_pass'] for r in s['phases']]==[True,True,True,False]
    assert s['phases'][-1]['result']['correct_bits']==28
    assert all(r['result']['new_dfe_voltage_audit']['documented_ranges_ok'] for r in s['phases'])
    chosen=s['phases'][0]['result']
    assert not chosen['new_tuning_switch_voltage_audit']['documented_ranges_ok']
    assert chosen['new_tuning_switch_voltage_audit']['devices'][0]['vds']['min_v']<0
    assert chosen['whole_circuit_voltage_envelope_pass']
    for r in s['controls']:
        assert chosen['sampled_eye_height_v']>r['result']['sampled_eye_height_v']+1e-6


@pytest.mark.parametrize('name',CASES)
def test_each_connected_case_replays_compressed_raw_primitives(name):
    folder=ROOT/name;saved=json.loads((folder/'result.json').read_text())
    reference=json.loads((ROOT/'calibration_reference.json').read_text())
    measured=extract(folder,(folder/'design.cir').read_text(),saved['tuned'],saved['phase_ui'],saved['code'],saved['sign'],reference)
    assert measured=={k:v for k,v in saved.items() if k not in ('tuned','phase_ui','code','sign')}
