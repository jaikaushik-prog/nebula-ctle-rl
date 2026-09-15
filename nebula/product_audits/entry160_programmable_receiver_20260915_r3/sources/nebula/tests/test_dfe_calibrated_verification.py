"""Parameterization must preserve every frozen analog and control formula."""
import inspect
import json
import numpy as np
import pytest
from nebula.device import dfe_calibrated_verification as V
from nebula.device import dfe_loaded_analog as L, dfe_configurable as C
from nebula.experiments import exp_dfe_linearity_tolerance as E
from nebula.experiments import exp_dfe_calibrated_verification as R

@pytest.mark.parametrize('name',['voltage_audit','static_metrics','tone_metrics'])
def test_only_target_argument_changes_in_frozen_analog_formulas(name):
    old=inspect.getsource(getattr(L,name))
    expected=old.replace('index','target').replace('TARGETS[target]','target')
    assert inspect.getsource(getattr(V,name))==expected

def test_only_control_arguments_change_in_frozen_runtime_audit():
    old=inspect.getsource(C.control_audit)
    expected=old.replace('def control_audit(t,y,nodes,vdd):','def control_audit(t,y,nodes,vdd,r_fraction,c_fraction):')
    expected=expected.replace('(R_FRACTION,C_FRACTION)','(r_fraction,c_fraction)')
    assert inspect.getsource(V.control_audit)==expected

def test_tone_deck_changes_only_selected_physical_controls():
    reference=json.loads((E.PRIOR/'reference_result.json').read_text())
    for tol in E.TOLERANCES:
        for step in L.STEPS:
            original=E.deck(tol,step,reference)
            expected=L.replace_once(original,r'^VrcC .*$','VrcC cctrl 0 0.333')
            assert V.deck('tone',0,tol,step,reference)==expected

def test_seven_call_schedule_requires_all_gates():
    calls=[]
    def evaluate(kind,state,tol,step):
        calls.append((kind,state,tol,step))
        if kind=='static': return {'instrument_ok':True,'initialization_valid':True,
            'small_signal_specs_pass':True,'target_match':True,'calibration_matches':True}
        if kind=='tone': return {'instrument_ok':True,'initialization_valid':True,'hd3_model_pass':True,
            'ctle_hd3':{'hd3_dbc':-50.,'fundamental_peak_v':.04}}
        return {'signal_gate_pass':True}
    s=R.schedule(evaluate)
    assert len(calls)==7 and s['nominal_calibrated_pass'] and not s['pvt_verified']
    assert not R.schedule(lambda *args:{'instrument_ok':False})['nominal_calibrated_pass']

def test_measured_control_selection_prerequisite():
    proofs,config,reference,calibration,ac=R.prerequisites()
    assert proofs['calibration']['file_count']==219 and config['entry']==142
    assert calibration['r_fraction']==V.TARGET[2] and calibration['c_fraction']==V.TARGET[3]
    assert reference['instrument_ok'] and ac.shape==(251,7)
