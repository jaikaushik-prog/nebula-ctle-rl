"""Nodeset is a released initial guess, not an ideal decision in the DUT."""
import json
import numpy as np
import pytest
from nebula.device import dfe_loaded_initialization as I, dfe_loaded_analog as L, dfe_connected as F
from nebula.experiments import exp_dfe_loaded_analog as E


@pytest.fixture
def reference():
    root=E.ROOT/'nebula/product_audits/entry137_dfe_loaded_analog_20260910/static_target7_state1_step5ps'
    return json.loads((root/'result.json').read_text())


@pytest.mark.parametrize('state,sign',[(0,-1),(0,1),(1,-1),(1,1)])
def test_only_released_initial_guesses_added(reference,state,sign):
    before=L.deck(7,'static',state,5e-12)
    after=I.deck('static',state,5e-12,sign,reference)
    lines=after.splitlines();guess=[s for s in lines if s.startswith('.nodeset ')]
    assert len(guess)==1 and all(f'v({n})=' in guess[0] for n in I.SEED_NODES)
    assert '\n'.join(s for s in lines if not s.startswith('.nodeset '))+'\n'==before
    assert F.all_mos(before)==F.all_mos(after) and '.ic ' not in after and ' uic' not in after
    seeds=I.seed_values(reference,sign)
    assert sign*(seeds['df_q']-seeds['df_qb'])>.1


def test_tone_keeps_original_clock_and_input(reference):
    for step in L.STEPS:
        text=I.deck('tone',0,step,-1,reference)
        assert text.count('PULSE(')==2 and 'SIN(0 0.1 100meg)' in text
        assert '\n'.join(s for s in text.splitlines() if not s.startswith('.nodeset '))+'\n'==L.deck(7,'tone',0,step)
    with pytest.raises(ValueError): I.seed_values(reference,0)
    with pytest.raises(ValueError): I.seed_values({'dc_nodes_v':{}},1)


def good():
    return {'instrument_ok':True,'initialization_valid':True,'calibration_matches':True,
            'small_signal_specs_pass':True,'hd3_model_pass':True,'target_match':False,
            'ctle_hd3':{'hd3_dbc':-60.,'fundamental_peak_v':.05}}


def test_one_four_six_call_stopping_and_no_target_promotion():
    calls=[]
    def run(kind,state,step,sign): calls.append((kind,state,step,sign));return good()
    r=I.schedule(run)
    assert len(calls)==6 and r['primary_analog_model_pass'] and not r['primary_target_match']
    assert not r['clocked_receiver_noise_verified'] and not r['full_receiver_verified']
    calls.clear()
    def bad(*args): calls.append(args);return {'instrument_ok':False}
    assert not I.schedule(bad)['primary_analog_model_pass'] and len(calls)==1
    calls.clear()
    def bad_state(kind,state,step,sign):
        calls.append((kind,state,step,sign));return {**good(),'initialization_valid':state==1}
    assert not I.schedule(bad_state)['primary_analog_model_pass'] and len(calls)==4


def test_calibration_requires_full_primitive_agreement(reference):
    ac=np.ones((251,),complex)
    assert I.calibration_matches(reference,reference,ac,ac)
    bad=json.loads(json.dumps(reference));bad['dc_nodes_v']['df_q']+=2e-6
    assert not I.calibration_matches(bad,reference,ac,ac)


def test_complete_reference_and_source_closure():
    from pathlib import Path
    from nebula.experiments import exp_dfe_loaded_initialization as N
    proof,config,reference,ac=N.prerequisites()
    assert proof['file_count']==84 and config['entry']==137 and ac.shape==(251,)
    assert reference['small_signal_specs_pass'] and not reference['target_match']
    assert set(E.SOURCES)<=set(N.SOURCES)
    root=Path(__file__).resolve().parents[2];name='nebula/DFE_LOADED_INITIALIZATION_PLAN.md'
    assert name+' text eol=lf' in (root/'.gitattributes').read_text()
    assert b'\r\n' not in (root/name).read_bytes()
    assert not I.calibration_matches(reference,reference,ac,ac*1.01)
    bad=json.loads(json.dumps(reference));bad['noise']['input_noise_vrms']*=1.01
    assert not I.calibration_matches(bad,reference,ac,ac)
