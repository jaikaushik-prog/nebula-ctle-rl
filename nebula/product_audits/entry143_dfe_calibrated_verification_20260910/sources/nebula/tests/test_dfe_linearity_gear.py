"""Solver-only recovery preserves all physical and measurement conditions."""
import json
import pytest
from nebula.experiments import exp_dfe_linearity_gear as E
from nebula.experiments import exp_dfe_clocked_linearity as P
from nebula.device import dfe_loaded_initialization as I, dfe_loaded_analog as L


def test_only_gear_option_changes_and_unregistered_steps_rejected():
    reference=json.loads((P.PRIOR/'reference_result.json').read_text())
    for step in L.STEPS:
        original=I.deck('tone',0,step,-1,reference)
        assert E.deck(step,reference).replace('.options method=gear maxord=2\n','')==original
    with pytest.raises(ValueError): E.deck(1e-12,reference)


def test_explicit_abort_diagnostics_and_no_benign_false_positive():
    for text in ('doAnalyses: TRAN: Timestep too small', 'tran simulation(s) aborted'):
        with pytest.raises(ValueError,match='aborted transient'): E.abort_audit(text)
    E.abort_audit('ngspice-41 done')


def test_prior_failed_pair_stays_rejected_and_source_snapshot_matches():
    proof,config,reference,ac=E.prerequisites()
    assert proof['verified_archives']==4 and config['entry']==139 and ac.shape==(251,)
    assert reference['instrument_ok']
    for step in L.STEPS:
        folder=E.PRIOR/f'tone_step{step*1e12:g}ps'
        with pytest.raises(ValueError,match='aborted transient'):
            E.abort_audit((folder/'ngspice.log').read_text())


def test_schedule_does_not_promote_failed_resolution_or_other_scope():
    calls=[]
    def evaluate(step):
        calls.append(step)
        return {'instrument_ok':True,'initialization_valid':True,'hd3_model_pass':True,
                'ctle_hd3':{'hd3_dbc':-50.,'fundamental_peak_v':.04}}
    result=E.schedule(evaluate)
    assert calls==list(L.STEPS) and result['entry']==140
    assert result['clocked_ctle_hd3_model_pass'] and not result['full_receiver_verified']
    assert not result['all_static_states_verified'] and not result['tuning_map_verified']
    assert not E.schedule(lambda step:{'instrument_ok':False})['clocked_ctle_hd3_model_pass']
