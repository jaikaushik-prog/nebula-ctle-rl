"""Submission adapter tests: no simulator calls, including failure cases."""
import inspect
import json
from pathlib import Path
import numpy as np
import pytest
from nebula.common.types import Corner
from nebula.device import dfe_calibrated_verification as V
from nebula.device import dfe_analog_pvt_submission as S

PRIOR=Path('nebula/product_audits/entry143_dfe_calibrated_verification_20260910')
REFERENCE=json.loads((PRIOR/'reference_result.json').read_text())
NOMINAL=Corner('tt',1.,27)
STRESS=Corner('fs',.95,125)
CASES=[('static',0,1e-5,5e-12),('static',1,1e-5,5e-12)]+[
    ('tone',0,tol,step) for tol in V.E.TOLERANCES for step in V.L.STEPS]


@pytest.mark.parametrize('kind,state,tol,step',CASES)
def test_nominal_exact_frozen_deck(kind,state,tol,step,tmp_path):
    folder=PRIOR/f'{kind}_state{state}_tol{tol:g}_step{step*1e12:g}ps'
    emitted=tmp_path/'design.cir'
    emitted.write_text(S.deck(kind,state,tol,step,REFERENCE,NOMINAL),encoding='ascii')
    assert emitted.read_bytes()==folder.joinpath('design.cir').read_bytes()


@pytest.mark.parametrize('state',(0,1))
def test_nominal_static_raw_replay_and_wrong_supply(state):
    folder=PRIOR/f'static_state{state}_tol1e-05_step5ps'
    text=folder.joinpath('design.cir').read_text()
    data=[np.loadtxt(folder/name) for name in ('op.txt','ac.txt','noise_total.txt','noise_spectrum.txt')]
    assert S.static_metrics(text,V.TARGET,state,*data,1.8)==V.static_metrics(text,V.TARGET,state,*data)
    with pytest.raises(ValueError,match='held clock'):
        S.static_metrics(text,V.TARGET,state,*data,1.71)
    malformed=data[0].copy();malformed[1]=float('nan')
    with pytest.raises(ValueError,match='malformed'):
        S.static_metrics(text,V.TARGET,state,malformed,*data[1:],1.8)


def test_metrics_are_only_mechanically_supply_parameterized():
    for name in ('voltage_audit','static_metrics','tone_metrics'):
        old=inspect.getsource(getattr(V,name))
        expected=old.replace('):',',vdd):',1).replace('1.8','vdd')
        if name=='static_metrics':
            expected=expected.replace('expected=(.6,1.2) if state==0 else (1.2,.6)',
                'expected=(vdd/3,2*vdd/3) if state==0 else (2*vdd/3,vdd/3)')
        if name!='voltage_audit':
            expected=expected.replace('voltage_audit(text,nodes,target)','voltage_audit(text,nodes,target,vdd)')
        assert inspect.getsource(getattr(S,name))==expected


@pytest.mark.parametrize('kind,state,tol,step',CASES)
def test_corner_geometry_unchanged_and_supply_consistent(kind,state,tol,step):
    nominal=S.deck(kind,state,tol,step,REFERENCE,NOMINAL)
    stress=S.deck(kind,state,tol,step,REFERENCE,STRESS)
    assert V.F.all_mos(nominal)==V.F.all_mos(stress)
    assert '.temp 125\n' in stress and '" fs\n' in stress
    assert 'VrcR rctrl 0 1.197' in stress and 'VrcC cctrl 0 0.31635' in stress
    assert 'Vid vid 0 DC 0 AC 1' in stress
    assert '.nodeset '+stress.split('.nodeset ')[1].splitlines()[0] in nominal
    assert stress.split('.control')[1]==nominal.split('.control')[1]
    if kind=='static':
        for name,value in zip(('clk','clkb'),((.57,1.14) if state==0 else (1.14,.57))):
            assert f'Vdf{name} df_{name} 0 {value:.16g}' in stress
    else:
        assert 'SIN(0 0.1 100meg)' in stress
        assert V.E.option(tol) in stress and '.options method=gear maxord=2' in stress


def test_unknown_corner_or_analysis_rejected():
    with pytest.raises(ValueError): S.deck('link',0,1e-5,5e-12,REFERENCE,NOMINAL)
    with pytest.raises(ValueError): S.deck('static',0,1e-5,5e-12,REFERENCE,Corner('tt',1.,50))


def test_noise_rms_units_and_band_gate():
    spectrum=np.column_stack((V.L.NOISE_FREQUENCIES,np.full((500,2),1e-8)))
    rms=np.sqrt(1e-16*(5e9-1e7))
    result=S.noise_metrics([[0,rms,rms]],spectrum)
    assert result['input_noise_vrms']==rms
    with pytest.raises(ValueError): S.noise_metrics([[0,np.sqrt(rms),np.sqrt(rms)]],spectrum)


def test_declared_measurement_membership_and_failure_gate():
    assert S.PILOT==(NOMINAL,STRESS)
    assert len(S.measurements())==6
    valid={'instrument_ok':True,'initialization_valid':True,'small_signal_specs_pass':True,'target_match':True,'positive_nyquist_pass':True}
    tone={'instrument_ok':True,'initialization_valid':True,'hd3_model_pass':True,
        'ctle_hd3':{'hd3_dbc':-40.,'fundamental_peak_v':.01}}
    assert S.corner_summary([valid,valid],[tone]*4)['analog_model_pass']
    bad=dict(valid,initialization_valid=False)
    assert not S.corner_summary([bad,valid],[tone]*4)['analog_model_pass']
    assert not S.corner_summary([valid,valid],[tone]*3)['analog_model_pass']
    miss=dict(valid,target_match=False)
    r=S.corner_summary([miss,valid],[tone]*4)
    assert r['analog_model_pass'] and not r['target_match']


def test_broad_s3_has_both_edges_and_nyquist_guard():
    f=V.R.FREQUENCIES_HZ
    for peak in (1e9,3e9):
        h=10**((8*np.exp(-((np.log(f/peak))/.5)**2))/20).astype(complex)
        assert not V.R.response_metrics(h)['ac_shape_pass']


def test_negative_nyquist_rejects_otherwise_in_band_peak():
    f=V.R.FREQUENCIES_HZ
    db=14*np.exp(-((np.log(f/1.5e9))/.15)**2)-6*(1-np.exp(-f/3e8))
    h=10**(db/20).astype(complex)
    assert V.R.response_metrics(h)['ac_shape_pass']
    ac=np.column_stack((f,np.zeros_like(f),np.zeros_like(f),h.real,h.imag,np.ones_like(f),np.zeros_like(f)))
    nyq=S.nyquist_metrics(ac)
    assert nyq['nyquist_boost_db']<0 and not nyq['positive_nyquist_pass']



def fake_row(args):
    return {'instrument_ok':True,'initialization_valid':True,'nominal_replay_matches':True,
        'small_signal_specs_pass':True,'target_match':True,'positive_nyquist_pass':True,
        'hd3_model_pass':True,'ctle_hd3':{'hd3_dbc':-40.,'fundamental_peak_v':.01}}


def test_scheduler_exact_membership_and_partial_coverage():
    from nebula.experiments import exp_dfe_analog_pvt_submission as E
    calls=[]
    def evaluate(c,args):
        calls.append((c,args));return fake_row(args)
    r=E.schedule(evaluate)
    assert len(calls)==12 and r['pilot_complete']
    assert calls==[(c,args) for c in S.PILOT for args in S.measurements()]
    assert len(r['unmeasured_corners'])==43 and not r['analog_pvt45_verified']


@pytest.mark.parametrize('field',('instrument_ok','initialization_valid','nominal_replay_matches'))
def test_scheduler_stops_before_stress_on_nominal_invalidity(field):
    from nebula.experiments import exp_dfe_analog_pvt_submission as E
    calls=[]
    def evaluate(c,args):
        calls.append(c);return dict(fake_row(args),**{field:False})
    r=E.schedule(evaluate)
    assert len(calls)==6 and not r['pilot_complete']
    assert r['stop_reason'] in ('invalid_instrument_or_initialization','nominal_reproduction_or_gate_failed')


def test_valid_stress_spec_failure_is_not_instrument_failure():
    from nebula.experiments import exp_dfe_analog_pvt_submission as E
    def evaluate(c,args):
        r=fake_row(args)
        if not c.is_nominal: r.update(small_signal_specs_pass=False,target_match=False)
        return r
    r=E.schedule(evaluate)
    assert r['pilot_complete'] and r['corners_instrument_complete']==2
    assert r['corners_analog_model_pass']==1 and r['corners_target_match']==1


def test_call_budget_reserves_whole_timeout():
    from nebula.experiments import exp_dfe_analog_pvt_submission as E
    assert E.call_allowed(2520,11)
    assert not E.call_allowed(2520.001,11)
    assert not E.call_allowed(0,12)


def test_existing_output_is_refused_before_expensive_preflight(tmp_path,monkeypatch):
    from nebula.experiments import exp_dfe_analog_pvt_submission as E
    def forbidden(): raise AssertionError('preflight must not run')
    monkeypatch.setattr(E,'prerequisites',forbidden)
    with pytest.raises(FileExistsError): E.run(tmp_path)


@pytest.mark.parametrize('seconds',(0,179.999,2700.001,float('nan'),float('inf')))
def test_invalid_wall_budget_rejected_before_preflight(seconds,tmp_path,monkeypatch):
    from nebula.experiments import exp_dfe_analog_pvt_submission as E
    def forbidden(): raise AssertionError('preflight must not run')
    monkeypatch.setattr(E,'prerequisites',forbidden)
    with pytest.raises(ValueError,match='wall budget'): E.run(tmp_path/'fresh',seconds)


def test_second_attempt_budget_reserves_full_timeout():
    from nebula.experiments import exp_dfe_analog_pvt_submission as E
    assert E.validate_wall_budget(180)==180
    assert E.validate_wall_budget(2700)==2700
    assert E.call_allowed(1020,11,1200)
    assert not E.call_allowed(1020.001,11,1200)
    assert not E.call_allowed(0,12,1200)
