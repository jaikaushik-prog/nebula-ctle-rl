"""Retain Entry 137's convergence failure and its single accepted snapshot."""
import json
from pathlib import Path
import pytest
from nebula.device import dfe_loaded_analog as L
from nebula.experiments import exp_dfe_loaded_analog as E, raw_manifest as M

ROOT=E.ROOT/'nebula/product_audits/entry137_dfe_loaded_analog_20260910'


def test_complete_failed_screen_manifest_and_frozen_stop():
    assert M.digest(ROOT/'summary.json')=='5a0ee9d638785de33e11c5c23e2b878c39601280354e74b04b8307987598f802'
    assert M.verify(ROOT)=={'file_count':84,'manifest_sha256':'1b422c6c56894809ce87adbd845ccb4b77fa0abaaaa399f2ddf05c6cab349119'}
    s=json.loads((ROOT/'summary.json').read_text())
    assert s['spice_calls']==s['attempted_cases']==2 and s['sources_unchanged'] and s['pdk_unchanged']
    assert not s['measurement_complete'] and not s['nominal_loaded_screen_pass'] and s['tones']==[]
    replay=L.schedule(lambda i,k,state,step:json.loads((ROOT/f'static_target7_state{state}_step5ps/result.json').read_text()))
    assert all(v==s[k] for k,v in replay.items())


@pytest.mark.parametrize('state',[0,1])
def test_exact_decks_and_retained_raw_rejection_or_replay(state):
    folder=ROOT/f'static_target7_state{state}_step5ps'
    text=(folder/'design.cir').read_text()
    assert text==L.deck(7,'static',state,5e-12)
    saved=json.loads((folder/'result.json').read_text())
    if state==0:
        assert not saved['instrument_ok']
        assert 'Warning: Last gmin step failed' in (folder/'ngspice.log').read_text()
        with pytest.raises(ValueError,match='unregistered simulator warning'):
            E.extract(folder,text,7,'static',state,5e-12)
    else:
        r=E.extract(folder,text,7,'static',state,5e-12)
        assert r=={k:v for k,v in saved.items() if k not in ('target_index','kind','clock_state','max_step_s')}
        assert r['small_signal_specs_pass'] and not r['target_match']
        assert r['noise']['input_noise_vrms']==pytest.approx(.0006358646548141916,abs=1e-15)
        assert r['response']['peak_frequency_hz']==pytest.approx(1750132069.0518737,abs=1e-3)
