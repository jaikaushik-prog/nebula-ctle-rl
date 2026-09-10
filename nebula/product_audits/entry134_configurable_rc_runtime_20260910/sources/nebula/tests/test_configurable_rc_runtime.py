"""Failure-first tests of the bounded runtime control instrument."""
import numpy as np
import pytest
from pathlib import Path

from nebula.device import configurable_rc as R, configurable_rc_precision as P
from nebula.device import configurable_rc_runtime as U


def test_one_physical_circuit_and_continuous_control_sequence():
    runtime = U.deck('runtime', 0)
    assert R.circuit_body((500, 0.)) in runtime
    assert P.OPTIONS in runtime
    assert runtime.count('\ntran ') == 1 and 'alter ' not in runtime
    assert ' uic' not in runtime.lower() and 'reset' not in runtime.lower()
    assert runtime.count('Xrc_switch ') == 1
    assert 'df_' not in runtime
    for i in range(3):
        assert R.circuit_body((500, 0.)) in U.deck('static', i)
    with pytest.raises(ValueError): U.deck('runtime', 1)
    with pytest.raises(ValueError): U.deck('static', 3)


def test_control_sources_have_measured_endpoints_and_finite_ramps():
    t=np.array([0,100,105,110,700,710,1300,1310,1900])*1e-9
    r,c=U.controls(t,'runtime',0)
    assert r[[0,3,5,7]].tolist()==pytest.approx(1.8*np.array([.7,.79,.73,.7]))
    assert c[[0,3,5,7]].tolist()==pytest.approx(1.8*np.array([.165,.135,.15,.165]))
    assert r[2]==pytest.approx((r[0]+r[3])/2)
    a,b=U.controls(t,'static',2)
    assert np.all(a==1.8*.73) and np.all(b==1.8*.15)


def test_two_tone_complex_fit_has_correct_polarity_and_phase():
    t=np.arange(0,25e-9,2.5e-12)
    h=np.array([.2+.1j,-.1+.3j])
    inp=U.stimulus(t)
    out=.03+sum(.001*(z.real*np.sin(2*np.pi*f*t)+z.imag*np.cos(2*np.pi*f*t)) for f,z in zip(U.FREQUENCIES,h))
    fit=U.fit_window(t,inp,out,0.)
    assert np.array(fit['transfer_real'])+1j*np.array(fit['transfer_imag'])==pytest.approx(h,abs=1e-9)
    assert fit['residual_fraction']<1e-9
    with pytest.raises(ValueError): U.fit_window(t,np.zeros_like(t),out,0.)
    with pytest.raises(ValueError): U.fit_window(t,inp,out,10e-9)
    with pytest.raises(ValueError): U.fit_window(t[::-1],inp,out,0.)
    with pytest.raises(ValueError): U.fit_window(t,np.full_like(t,np.nan),out,0.)


def test_window_gate_rejects_each_independent_failure():
    fit={'transfer_real':[.2,.4],'transfer_imag':[0.,0.], 'residual_fraction':0.,
         'vdd_power_w':.007,'control_mean_error_v':0.}
    ref=np.array([.2,.4],complex)
    assert U.window_pass(fit,ref)
    for changed in ({'transfer_real':[.1,.4]},{'residual_fraction':.051},
                    {'vdd_power_w':.015},{'vdd_power_w':0.},
                    {'control_mean_error_v':.00101},{'residual_fraction':float('nan')}):
        assert not U.window_pass({**fit,**changed},ref)


def test_settling_requires_a_contiguous_passing_tail_not_one_good_window():
    rows=[{'start_s':x*1e-9,'pass':p} for x,p in [(10,False),(20,True),(30,False),(40,True),(50,True)]]
    assert U.settling_bound(rows,0.)==pytest.approx(40e-9)
    assert U.settling_bound(rows+[{'start_s':60e-9,'pass':False}],0.) is None
    assert U.settling_bound([],0.) is None


def test_registered_schedule_stops_and_retains_failures():
    calls=[]
    def fail(kind,i): calls.append((kind,i));return {'baseline_pass':False}
    assert not U.schedule(fail)['runtime_demonstration_pass'] and len(calls)==1
    calls.clear()
    def third_fail(kind,i): calls.append((kind,i));return {'baseline_pass':i!=2}
    assert not U.schedule(third_fail)['runtime_demonstration_pass'] and len(calls)==3
    calls.clear()
    def ok(kind,i): calls.append((kind,i));return {'baseline_pass':True,'runtime_pass':True,'low_frequency_gain':(.2,.4,.6)[i]}
    result=U.schedule(ok)
    assert len(calls)==4 and result['runtime_demonstration_pass']
    assert not result['connected_dfe_runtime_verified'] and not result['full_receiver_verified']
    calls.clear()
    result=U.schedule(lambda kind,i: {'baseline_pass':True,'runtime_pass':True,'low_frequency_gain':.2})
    assert not result['runtime_demonstration_pass'] and not result['distinct_settings_verified']


@pytest.fixture(scope='module')
def prior():
    from nebula.experiments.exp_configurable_rc_runtime import prerequisites
    proof,config,refs=prerequisites()
    assert proof['file_count']==1812 and len(config['external_pdk_include_closure_sha256'])==319
    return refs


def test_real_saved_ac_and_op_replay_without_imputation(prior):
    from nebula.experiments.exp_configurable_rc_runtime import PRIOR
    for i,ref in enumerate(prior):
        folder=PRIOR/'candidate_n500_fixed0pf';step=ref['step_index']
        op=np.atleast_2d(np.loadtxt(folder/f'op_{step:03d}.txt'))[:,:len(U.NODES)+2]
        ac=np.loadtxt(folder/f'ac_{step:03d}.txt')[:,:7]
        assert U.reference_match(op,ac,i,ref)['reference_matches']
        bad=op.copy();bad[0,2]+=2e-9
        assert not U.reference_match(bad,ac,i,ref)['reference_matches']
        bad=ac.copy();bad[:,1:5]*=1.001
        assert not U.reference_match(op,bad,i,ref)['reference_matches']


def test_exact_ac_parser_rejects_missing_input_and_wrong_frequency():
    raw=np.array([[f,0,0,.2,.1,1,0] for f in U.FREQUENCIES])
    assert U.tone_reference(raw)==pytest.approx([.2+.1j,.2+.1j])
    for bad in (raw[:1],np.full_like(raw,np.nan)):
        with pytest.raises(ValueError): U.tone_reference(bad)
    bad=raw.copy();bad[0,0]+=1e6
    with pytest.raises(ValueError): U.tone_reference(bad)
    bad=raw.copy();bad[:,5]=0
    with pytest.raises(ValueError): U.tone_reference(bad)


def artificial_trace(prior):
    # Analytic UNIT-TEST fixture only, never written to evidence/deliverables.
    t=np.arange(20001)*U.STEP;h=np.array([.2+.1j,.4-.1j])
    dc=prior[0]['dc'];nodes={n:np.full(len(t),v) for n,v in dc['dc_nodes_v'].items()}
    out=sum(.001*(z.real*np.sin(2*np.pi*f*t)+z.imag*np.cos(2*np.pi*f*t)) for f,z in zip(U.FREQUENCIES,h))
    y=np.zeros((len(t),len(U.VECTORS)));y[:,0]=U.stimulus(t)
    nodes['outp']-=out/2;nodes['outn']+=out/2
    for n,i in [('outp',1),('outn',2),('vdd',3),('rctrl',5),('cctrl',6),('rc_gate',7),('rc_ct',8)]: y[:,i]=nodes[n]
    y[:,4]=-dc['vdd_power_w']/1.8
    refs=[{'op_nodes_v':dc['dc_nodes_v'],'tone_real':h.real.tolist(),'tone_imag':h.imag.tolist()},None,None]
    return t,y,nodes,refs


def test_complete_trace_checks_every_primitive_and_power_gate(prior):
    t,y,nodes,refs=artificial_trace(prior)
    assert U.analyze(t,y,nodes,'static',0,refs)['static_transient_pass']
    bad=y.copy();bad[:,0]+=2e-9
    with pytest.raises(ValueError,match='stimulus'): U.analyze(t,bad,nodes,'static',0,refs)
    bad=y.copy();bad[:,4]=0
    assert not U.analyze(t,bad,nodes,'static',0,refs)['static_transient_pass']
    bad_nodes={**nodes,'outp':nodes['outp']+1e-6}
    with pytest.raises(ValueError,match='primitive differs'): U.analyze(t,y,bad_nodes,'static',0,refs)
    with pytest.raises(ValueError,match='incomplete'):
        U.analyze(t[:-1],y[:-1],{n:v[:-1] for n,v in nodes.items()},'static',0,refs)
    select=np.arange(len(t))!=10
    with pytest.raises(ValueError,match='undersampled'):
        U.analyze(t[select],y[select],{n:v[select] for n,v in nodes.items()},'static',0,refs)
    bad=y.copy();bad[:,8]=2.1;bad_nodes={**nodes,'rc_ct':bad[:,8]}
    assert not U.analyze(t,bad,bad_nodes,'static',0,refs)['varactor_envelope_pass']


def test_missing_trace_is_an_instrument_failure(tmp_path):
    from nebula.experiments.exp_configurable_rc_runtime import extract
    with pytest.raises(FileNotFoundError): extract(tmp_path,'static',0,[],[])


def test_registration_is_checkout_stable_and_source_closure_is_pinned():
    from nebula.experiments import exp_configurable_rc_runtime as E, exp_dfe_configurable_pvt as H
    root=Path(__file__).resolve().parents[2];name='nebula/CONFIGURABLE_RC_RUNTIME_PLAN.md'
    assert name+' text eol=lf' in (root/'.gitattributes').read_text()
    assert b'\r\n' not in (root/name).read_bytes()
    assert set(H.SOURCES)<=set(E.SOURCES)


def test_full_runtime_extractor_visits_all_three_transitions(prior):
    # Analytic fixture exercises extraction, not a physical simulation result.
    t=np.arange(round(U.STOP/U.STEP)+1)*U.STEP
    knots,_=U.control_knots();sequence=(0,0,1,1,2,2,0,0)
    nodes={n:np.interp(t,knots,[prior[i]['dc']['dc_nodes_v'][n] for i in sequence]) for n in U.NODES}
    hs=np.array([[.2+.1j,.4-.1j],[.4+.1j,.5+.2j],[.3-.1j,.4+.3j]])
    out=np.zeros(len(t))
    for j,f in enumerate(U.FREQUENCIES):
        real=np.interp(t,knots,[hs[i,j].real for i in sequence])
        imag=np.interp(t,knots,[hs[i,j].imag for i in sequence])
        out+=.001*(real*np.sin(2*np.pi*f*t)+imag*np.cos(2*np.pi*f*t))
    y=np.zeros((len(t),len(U.VECTORS)));y[:,0]=U.stimulus(t)
    nodes['outp']-=out/2;nodes['outn']+=out/2
    for n,i in [('outp',1),('outn',2),('vdd',3),('rctrl',5),('cctrl',6),('rc_gate',7),('rc_ct',8)]: y[:,i]=nodes[n]
    y[:,4]=-.004
    refs=[{'op_nodes_v':p['dc']['dc_nodes_v'],'tone_real':h.real.tolist(),'tone_imag':h.imag.tolist()} for p,h in zip(prior,hs)]
    result=U.analyze(t,y,nodes,'runtime',0,refs)
    assert result['runtime_pass'] and len(result['transitions'])==3
    assert [r['to_index'] for r in result['transitions']]==[1,2,0]
    assert all(r['settling_bound_s']==0. for r in result['transitions'])
    assert all(len(r['windows'])==58 for r in result['transitions'])
    # Corrupt only the final plateau output; a prior good window cannot save it.
    mask=t>U.STOP-80e-9
    y[mask,1]-=out[mask]/2;y[mask,2]+=out[mask]/2
    nodes['outp']=y[:,1];nodes['outn']=y[:,2]
    result=U.analyze(t,y,nodes,'runtime',0,refs)
    assert not result['runtime_pass']
    assert result['transitions'][-1]['settling_bound_s'] is None
