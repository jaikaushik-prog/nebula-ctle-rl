"""The required transient measurement is independent of optional DC coverage."""
from nebula.experiments import exp_dfe_clocked_linearity as E
from nebula.device import dfe_loaded_analog as L


def good():
    return {'instrument_ok':True,'initialization_valid':True,'hd3_model_pass':True,
            'ctle_hd3':{'hd3_dbc':-60.,'fundamental_peak_v':.05}}


def test_exactly_two_calls_and_no_noise_or_target_promotion():
    calls=[]
    def run(step): calls.append(step);return good()
    r=E.schedule(run)
    assert calls==list(L.STEPS) and r['clocked_ctle_hd3_model_pass']
    assert not r['all_static_states_verified'] and not r['full_receiver_verified']
    assert not r['clocked_receiver_noise_verified'] and not r['tuning_map_verified']
    calls.clear()
    def bad(step): calls.append(step);return {'instrument_ok':False}
    assert not E.schedule(bad)['clocked_ctle_hd3_model_pass'] and len(calls)==2
    def disagree(step):
        return {**good(),'ctle_hd3':{'hd3_dbc':-60 if step==L.STEPS[0] else -58,'fundamental_peak_v':.05}}
    assert not E.schedule(disagree)['clocked_ctle_hd3_model_pass']


def test_valid_starting_state_and_full_source_closure():
    from nebula.experiments import exp_dfe_loaded_initialization as N
    proof,config,reference,ac=E.prerequisites()
    assert proof['file_count']==106 and config['entry']==138 and ac.shape==(251,)
    assert reference['instrument_ok'] and set(N.SOURCES)<=set(E.SOURCES)
    name='nebula/DFE_CLOCKED_LINEARITY_PLAN.md'
    assert name+' text eol=lf' in (E.ROOT/'.gitattributes').read_text()
    assert b'\r\n' not in (E.ROOT/name).read_bytes()
