"""Tolerance recovery must agree across all four numerical settings."""
import json
import pytest
from nebula.experiments import exp_dfe_linearity_tolerance as E
from nebula.experiments import exp_dfe_linearity_gear as G
from nebula.device import dfe_loaded_analog as L

def test_only_registered_solver_tolerances_change():
    reference=json.loads((G.PRIOR/'reference_result.json').read_text())
    for tol in E.TOLERANCES:
        for step in L.STEPS:
            expected=G.deck(step,reference)
            assert E.deck(tol,step,reference).replace(E.option(tol),E.ORIGINAL)==expected
    with pytest.raises(ValueError): E.deck(1e-3,L.STEPS[0],reference)

def test_four_way_agreement_and_no_partial_success():
    calls=[]
    def good(tol,step):
        calls.append((tol,step))
        return {'instrument_ok':True,'initialization_valid':True,'hd3_model_pass':True,
                'ctle_hd3':{'hd3_dbc':-50.,'fundamental_peak_v':.04}}
    r=E.schedule(good)
    assert calls==[(tol,step) for tol in E.TOLERANCES for step in L.STEPS]
    assert r['clocked_ctle_hd3_model_pass'] and r['four_way_agreement']
    assert not r['full_receiver_verified'] and not r['tuning_map_verified']
    def mismatch(tol,step):
        r=good(tol,step)
        if tol==E.TOLERANCES[1]: r['ctle_hd3']['hd3_dbc']=-48.
        return r
    assert not E.schedule(mismatch)['clocked_ctle_hd3_model_pass']
    assert not E.schedule(lambda tol,step:{'instrument_ok':False})['clocked_ctle_hd3_model_pass']

def test_complete_gear_failure_archive_prerequisite():
    proof,config,reference,ac=E.prerequisites()
    assert proof['verified_archives']==4 and config['entry']==140 and ac.shape==(251,)
    assert reference['instrument_ok']
