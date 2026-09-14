"""Loaded calibration uses real physical controls and preserves a raw baseline."""
import json
import numpy as np
import pytest
from nebula.experiments import exp_dfe_loaded_calibration as E
from nebula.device import dfe_loaded_initialization as I, dfe_loaded_analog as L

def reference():
    return json.loads((E.STATIC/'static_state0_sign-1_step5ps/result.json').read_text())

def test_registered_grid_and_unchanged_physical_deck():
    pairs=E.biases()
    assert len(pairs)==65 and len(set(pairs))==65 and pairs[0]==(.7,.165)
    text=E.deck(reference())
    assert text.split('.control')[0]==I.deck('static',0,5e-12,-1,reference()).split('.control')[0]
    assert text.count('\nop\n')==65 and text.count('ac dec 50 1meg 100g')==65
    assert all(f'op_{i:03d}.txt' in text and f'ac_{i:03d}.txt' in text for i in range(65))

def test_parser_calibrates_real_first_snapshot_and_rejects_wrong_controls():
    folder=E.STATIC/'static_state0_sign-1_step5ps'
    op=np.loadtxt(folder/'op.txt'); ac=np.loadtxt(folder/'ac.txt')
    text=E.deck(reference())
    r=E.parse_row(text,.7,.165,op,ac)
    assert r['ac_spec_pass'] and not E.select([r])['found']
    assert E.calibration_matches(r,reference(),ac,ac)
    with pytest.raises(ValueError,match='control'):
        E.parse_row(text,.7,.17,op,ac)
    bad=np.asarray(op).copy(); bad[-1]=0
    with pytest.raises(ValueError,match='power'):
        E.parse_row(text,.7,.165,bad,ac)
    assert not E.calibration_matches(r,reference(),ac*.9,ac)

def test_selection_is_deterministic_and_never_relaxes_target():
    row={'ac_spec_pass':True,'boost_db':9.,'peak_frequency_hz':1.9e9,'r_fraction':.7,'c_fraction':.2,'vdd_power_w':.0093}
    assert E.select([row])['found']
    assert E.select([{**row,'peak_frequency_hz':1.75e9}])['found'] is False
    assert E.select([{**row,'ac_spec_pass':False}])['found'] is False
    assert E.select([row,{**row,'c_fraction':.195}])['selected']['c_fraction']==.195

def test_complete_prerequisites():
    proofs,config,ref,ac=E.prerequisites()
    assert proofs['linearity']['verified_archives']==8
    assert proofs['static']['file_count']==106 and config['entry']==141
    assert ref['initialization_valid'] and np.asarray(ac).shape==(251,7)
