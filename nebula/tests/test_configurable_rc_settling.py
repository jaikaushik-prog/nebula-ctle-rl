"""Longer observation must not silently relax the original settling gate."""
import re
from pathlib import Path

import numpy as np
import pytest

from nebula.device import configurable_rc_runtime_recovery as V
from nebula.device import configurable_rc_settling as W
from nebula.device import configurable_rc_runtime as U


def test_only_observation_times_change_not_hardware_or_stimulus():
    old=V.deck('runtime',0);new=W.deck()
    def strip(text): return re.sub(r'(?m)^(?:Vr rctrl |Vc cctrl |tran 5p ).*\n','',text)
    assert strip(old)==strip(new)
    assert new.count('\ntran ')==1 and 'reset' not in new.lower() and ' uic' not in new.lower()
    assert W.CHANGES==pytest.approx(np.array([100,1100,2100])*1e-9)
    assert W.STOP==pytest.approx(3100e-9)


def test_eventual_settling_is_separate_from_the_original_latency_gate():
    rows=[{'settling_bound_s':x*1e-9} for x in (850,690,650)]
    assert W.conclusions(True,rows)=={'all_transitions_settled':True,'passes_original_500ns_gate':False}
    assert W.conclusions(True,[{'settling_bound_s':490e-9}]*3)['passes_original_500ns_gate']
    assert not W.conclusions(False,rows)['all_transitions_settled']
    assert not W.conclusions(True,rows[:2])['all_transitions_settled']
    assert not W.conclusions(True,[{'settling_bound_s':None}]*3)['all_transitions_settled']
    assert not W.conclusions(True,[{'settling_bound_s':float('nan')}]*3)['all_transitions_settled']


def test_controls_keep_the_exact_old_levels_and_ramp_width():
    r,c=W.controls(np.array([0,110,1110,2110,3100])*1e-9)
    assert r==pytest.approx(1.8*np.array([.7,.79,.73,.7,.7]))
    assert c==pytest.approx(1.8*np.array([.165,.135,.15,.165,.165]))


@pytest.fixture(scope='module')
def references():
    from nebula.experiments.exp_configurable_rc_settling import prerequisites
    proof,config,refs=prerequisites()
    assert proof['verified_files']==108 and proof['verified_archives']==8 and config['entry']==135
    assert len(refs)==3 and all(r['baseline_pass'] for r in refs)
    return refs


def test_full_extended_extractor_and_late_failure(references):
    # Analytic unit-test fixture only; no synthetic waveform is exported.
    t=np.arange(round(W.STOP/U.STEP)+1)*U.STEP
    knots,_=W.control_knots();sequence=(0,0,1,1,2,2,0,0)
    nodes={n:np.interp(t,knots,[references[i]['op_nodes_v'][n] for i in sequence]) for n in U.NODES}
    hs=np.array([np.array(r['tone_real'])+1j*np.array(r['tone_imag']) for r in references])
    out=np.zeros(len(t))
    for j,f in enumerate(U.FREQUENCIES):
        real=np.interp(t,knots,[hs[i,j].real for i in sequence])
        imag=np.interp(t,knots,[hs[i,j].imag for i in sequence])
        out+=.001*(real*np.sin(2*np.pi*f*t)+imag*np.cos(2*np.pi*f*t))
    y=np.zeros((len(t),len(U.VECTORS)));y[:,0]=U.stimulus(t)
    nodes['outp']-=out/2;nodes['outn']+=out/2
    for n,i in [('outp',1),('outn',2),('vdd',3),('rctrl',5),('cctrl',6),('rc_gate',7),('rc_ct',8)]: y[:,i]=nodes[n]
    y[:,4]=-.004
    result=W.analyze(t,y,nodes,references)
    assert result['all_transitions_settled'] and result['passes_original_500ns_gate']
    assert [r['to_index'] for r in result['transitions']]==[1,2,0]
    assert all(len(r['windows'])==98 and r['settling_bound_s']==0. for r in result['transitions'])
    with pytest.raises(ValueError,match='incomplete'):
        W.analyze(t[:-1],y[:-1],{n:v[:-1] for n,v in nodes.items()},references)
    bad=y.copy();bad[:,0]+=2e-9
    with pytest.raises(ValueError,match='stimulus'): W.analyze(t,bad,nodes,references)
    mask=t>W.STOP-80e-9
    y[mask,1]-=out[mask]/2;y[mask,2]+=out[mask]/2
    nodes['outp']=y[:,1];nodes['outn']=y[:,2]
    result=W.analyze(t,y,nodes,references)
    assert not result['all_transitions_settled'] and not result['passes_original_500ns_gate']
    assert result['transitions'][-1]['settling_bound_s'] is None


def test_shorter_real_run_cannot_satisfy_extended_observation(references):
    from nebula.experiments import exp_configurable_rc_settling as E
    with pytest.raises(ValueError,match='incomplete'):
        E.extract(E.PRIOR/'runtime_0',references)


def test_registration_and_full_source_closure():
    from nebula.experiments import exp_configurable_rc_settling as E, exp_configurable_rc_runtime_recovery as E0
    root=Path(__file__).resolve().parents[2];name='nebula/CONFIGURABLE_RC_SETTLING_OBSERVATION_PLAN.md'
    assert name+' text eol=lf' in (root/'.gitattributes').read_text()
    assert b'\r\n' not in (root/name).read_bytes()
    assert set(E0.SOURCES)<=set(E.SOURCES)
