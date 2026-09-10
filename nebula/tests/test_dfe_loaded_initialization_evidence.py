"""Replay the three resolved snapshots and retain the fourth-state failure."""
import json
from pathlib import Path
import numpy as np
import pytest
from nebula.device import dfe_loaded_initialization as I, configurable_rc as R
from nebula.experiments import exp_dfe_loaded_initialization as E, raw_manifest as M

ROOT=E.ROOT/'nebula/product_audits/entry138_dfe_loaded_initialization_20260910'


def test_complete_initialization_manifest_and_four_call_stop():
    assert M.verify(ROOT)=={'file_count':106,'manifest_sha256':'9f6f3d5bbd36023329a850d5dc8030492db59464bbe12b97f924ec8957101a27'}
    assert M.digest(ROOT/'summary.json')=='113cc58d909f5d2c4bcc2edb601f7d1c8952eb7e71b749583b32ba63eefab142'
    s=json.loads((ROOT/'summary.json').read_text())
    assert s['spice_calls']==s['attempted_cases']==4 and s['sources_unchanged'] and s['pdk_unchanged']
    assert s['tones']==[] and not s['measurement_complete'] and not s['primary_analog_model_pass']
    replay=I.schedule(lambda kind,state,step,sign:json.loads((ROOT/f'{kind}_state{state}_sign{sign}_step5ps/result.json').read_text()))
    assert all(v==s[k] for k,v in replay.items())


@pytest.mark.parametrize('state,sign',[(1,-1),(1,1),(0,-1),(0,1)])
def test_raw_initialization_case_replay(state,sign):
    folder=ROOT/f'static_state{state}_sign{sign}_step5ps'
    reference=json.loads((ROOT/'reference_result.json').read_text())
    ac=R.parse_ac(np.loadtxt(ROOT/'reference_ac.txt'),1)[:,0]
    text=(folder/'design.cir').read_text()
    assert text==I.deck('static',state,5e-12,sign,reference)
    saved=json.loads((folder/'result.json').read_text())
    if (state,sign)==(1,1):
        assert not saved['instrument_ok']
        with pytest.raises(ValueError,match='unregistered simulator warning'):
            E.extract(folder,text,'static',state,5e-12,sign,reference,ac)
    else:
        r=E.extract(folder,text,'static',state,5e-12,sign,reference,ac)
        assert r=={k:v for k,v in saved.items() if k not in ('kind','clock_state','max_step_s')}
        assert r['initialization_valid'] and r['small_signal_specs_pass'] and not r['target_match']
