"""Replay the measured loaded-control calibration and independent nominal proof."""
import json
import numpy as np
import pytest
from nebula.experiments import raw_manifest as M, evidence_archive as A
from nebula.experiments import exp_dfe_loaded_calibration as K, exp_dfe_calibrated_verification as E
from nebula.device import dfe_calibrated_verification as V
ROOT=K.ROOT/'nebula/product_audits'
CAL=ROOT/'entry142_dfe_loaded_calibration_20260910'
NOM=ROOT/'entry143_dfe_calibrated_verification_20260910'
META=('kind','clock_state','relative_tolerance','max_step_s')

def test_complete_loaded_calibration_manifest():
    assert M.verify(CAL)=={'file_count':219,'manifest_sha256':'ed79551ac05cd5c42e01bf57af8d94c3510ebcbb593808c5779f82bdc5a16bfb'}
    assert A.digest(CAL/'summary.json')=='8e705658406a1851f6db3e4f8626c88a0bfb7322d705cd398d9fc092f33ec10a'
    s=json.loads((CAL/'summary.json').read_text())
    assert s['spice_calls']==1 and s['target_found'] and s['sources_unchanged'] and s['pdk_unchanged']
    assert len(s['rows'])==65 and not s['selected_controls_transient_verified']

def test_all_65_loaded_control_measurements_replay():
    reference=json.loads((CAL/'reference_result.json').read_text())
    ac=np.loadtxt(CAL/'reference_ac.txt');folder=CAL/'calibration'
    text=(folder/'design.cir').read_text()
    assert text==K.deck(reference)
    actual=K.extract(folder,text,reference,ac)
    saved=json.loads((CAL/'summary.json').read_text())
    assert all(saved[k]==v for k,v in actual.items())
    assert actual['selection']['selected']['c_fraction']==.185

def test_complete_independent_nominal_archive_and_schedule():
    assert A.verify(NOM)=={'verified_files':137,'verified_archives':10,
        'manifest_sha256':'59a7deec832a1d744ad7175bd1eeed7fb0d21b376e1d03c15acb24e1888c99c7'}
    assert A.digest(NOM/'summary.json')=='14d7d368163652235378e1566e4800a7d26ec2a550922300a015978b74602d96'
    s=json.loads((NOM/'summary.json').read_text())
    assert s['spice_calls']==7 and s['nominal_calibrated_pass'] and s['four_way_agreement']
    def evaluate(kind,state,tol,step):
        return json.loads((NOM/f'{kind}_state{state}_tol{tol:g}_step{step*1e12:g}ps/result.json').read_text())
    replay=E.schedule(evaluate)
    # Saved JSON encodes the immutable target tuple as a list.
    assert json.loads(json.dumps(replay))=={k:s[k] for k in replay}
    assert s['sources_unchanged'] and s['pdk_unchanged'] and not s['pvt_verified']

CASES=[('static',state,1e-5,5e-12) for state in (0,1)]
CASES += [('tone',0,tol,step) for tol in (2e-5,1e-5) for step in (5e-12,2.5e-12)]
CASES += [('link',0,1e-5,5e-12)]
@pytest.mark.parametrize('kind,state,tol,step',CASES)
def test_actual_calibrated_nominal_raw_replay(kind,state,tol,step):
    folder=NOM/f'{kind}_state{state}_tol{tol:g}_step{step*1e12:g}ps'
    reference=json.loads((NOM/'reference_result.json').read_text())
    calibration=json.loads((NOM/'calibration_result.json').read_text())
    ac=np.loadtxt(NOM/'calibration_ac.txt');text=(folder/'design.cir').read_text()
    assert text==(V.link_deck() if kind=='link' else V.deck(kind,state,tol,step,reference))
    actual=V.link_extract(folder,text) if kind=='link' else V.analog_extract(folder,text,kind,state,step,calibration,ac)
    saved=json.loads((folder/'result.json').read_text())
    assert actual=={k:v for k,v in saved.items() if k not in META}
    assert actual['instrument_ok']
    if kind=='static': assert actual['target_match'] and actual['noise']['noise_limit_pass']
    elif kind=='tone': assert actual['hd3_model_pass']
    else: assert actual['signal_gate_pass'] and actual['correct_bits']==64
