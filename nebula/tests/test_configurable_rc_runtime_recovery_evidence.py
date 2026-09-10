"""Replay Entry 135 without turning signal-only success into a settling pass."""
import json
from pathlib import Path

import numpy as np
import pytest

from nebula.experiments import evidence_archive as A, exp_configurable_rc_runtime_recovery as E

ROOT=Path(__file__).resolve().parents[1]/'product_audits/entry135_configurable_rc_runtime_recovery_20260910'


def test_manifest_preserves_all_three_settling_failures():
    assert A.digest(ROOT/'summary.json')=='7c5b725eba0a7e6420eb7d0e2f743d14c6a4f866cab4f537199b2e39bf7b3624'
    assert A.verify(ROOT)=={'verified_files':108,'verified_archives':8,'manifest_sha256':'77d99d8d188c0026e697cee01c83a6353c59cb57d63c7f131b4e030239d375ed'}
    s=json.loads((ROOT/'summary.json').read_text())
    assert s['spice_calls']==s['attempted_cases']==4
    assert s['pdk_unchanged'] and s['sources_unchanged'] and s['distinct_settings_verified']
    assert all(r['baseline_pass'] for r in s['static'])
    assert s['runtime']['instrument_ok'] and not s['runtime_demonstration_pass']
    assert s['runtime']['whole_magnitude_body_envelope_pass'] and s['runtime']['varactor_envelope_pass']
    for row in s['runtime']['transitions']:
        assert row['settling_bound_s'] is None and not row['pass']
        assert not any(w['pass'] for w in row['windows'])
        assert row['windows'][-1]['control_mean_error_v']>.001


@pytest.mark.parametrize('kind,index',[('static',0),('static',1),('static',2),('runtime',0)])
def test_every_case_replays_exact_raw_primitives(kind,index):
    s=json.loads((ROOT/'summary.json').read_text());prior=[]
    for i in range(3):
        ref=json.loads((ROOT/f'static_reference_{i}.json').read_text())
        prior.append({'dc':ref['dc'],'ac':np.array(ref['ac_real'])+1j*np.array(ref['ac_imag'])})
    folder=ROOT/f'{kind}_{index}';saved=json.loads((folder/'result.json').read_text())
    actual=E.extract(folder,kind,index,prior,s['static'])
    assert actual=={k:v for k,v in saved.items() if k not in ('kind','index')}
