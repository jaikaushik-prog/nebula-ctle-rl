"""Failure-first checks for loaded analog measurements; no synthetic evidence."""
from pathlib import Path
import json
import numpy as np
import pytest

from nebula.common.types import Corner
from nebula.link.config import LinkConfig
from nebula.device import dfe_loaded_analog as L, dfe_configurable as C, dfe_connected as F


def test_deck_preserves_every_physical_device_and_clocked_feedback():
    cfg=LinkConfig(channel_loss_db_at_nyquist=7.5)
    old=C.deck(True,Corner('tt',1.,27),cfg,F.pattern(cfg),1.,2,1)
    for kind,state,step in [('static',0,5e-12),('static',1,5e-12),('tone',0,5e-12),('tone',0,2.5e-12)]:
        text=L.deck(7,kind,state,step)
        assert F.all_mos(text)==F.all_mos(old)
        assert [s for s in old.splitlines() if s.startswith(('X','CL'))]==[s for s in text.splitlines() if s.startswith(('X','CL'))]
        assert text.count('.lib ')==1 and 'PWL(' not in text
        assert 'Vid vid 0 DC 0 AC 1' in text
        if kind=='tone':
            assert text.count('PULSE(')==2 and 'SIN(0 0.1 100meg)' in text
            assert f'tran {step:.16g} 150n 0 {step:.16g}' in text
        else:
            assert 'PULSE(' not in text and 'noise v(outn,outp) Vid lin 500 10meg 5g' in text
            assert 'unset sqrnoise' in text and 'setplot noise1' in text
    for args in [(9,'static',0,5e-12),(0,'bad',0,5e-12),(0,'static',2,5e-12),(7,'tone',0,1e-12)]:
        with pytest.raises(ValueError): L.deck(*args)


def test_targets_match_saved_nine_target_map():
    root=Path(__file__).resolve().parents[1]/'product_audits/entry131_configurable_rc_fine_20260910'
    summary=json.loads((root/'summary.json').read_text())
    targets=next(r['targets'] for r in summary['candidates'] if r['geometry']==[500,0.])
    assert [(t['target_boost_db'],t['target_frequency_hz'],t['r_fraction'],t['c_fraction']) for t in targets]==list(L.TARGETS)


def test_noise_is_rms_with_independent_spectrum_integral():
    f=L.NOISE_FREQUENCIES;ni=np.full(500,1e-8);no=2*ni
    totals=np.array([[0.,np.sqrt(np.trapezoid(ni**2,f)),np.sqrt(np.trapezoid(no**2,f))]])
    spectrum=np.column_stack([f,ni,no])
    r=L.noise_metrics(totals,spectrum)
    assert r['input_noise_vrms']==totals[0,1] and r['noise_limit_pass']
    for bad in [spectrum[:-1],spectrum[:,::-1],np.full_like(spectrum,np.nan)]:
        with pytest.raises(ValueError): L.noise_metrics(totals,bad)
    for bad in [totals**.5,totals*0,np.full_like(totals,np.nan)]:
        with pytest.raises(ValueError): L.noise_metrics(bad,spectrum)
    assert not L.noise_metrics(totals*10,np.column_stack([f,ni*10,no*10]))['noise_limit_pass']


def test_harmonics_use_exact_integer_windows_and_detect_instability():
    t=np.arange(60001)*2.5e-12
    v=.05*np.sin(2*np.pi*1e8*t)+.00005*np.sin(2*np.pi*3e8*t)
    r=L.harmonics(t,v,50e-9,150e-9)
    assert r['hd3_dbc']==pytest.approx(-60,abs=1e-8)
    assert r['fundamental_peak_v']==pytest.approx(.05)
    for bad_t,bad_v in [(t[:-1],v[:-1]),(t[::-1],v),(t,np.full_like(v,np.nan))]:
        with pytest.raises(ValueError): L.harmonics(bad_t,bad_v,50e-9,150e-9)
    with pytest.raises(ValueError): L.harmonics(t,v,50e-9,149e-9)


def test_warning_guard_accepts_only_documented_model_qualifications():
    log='Warning: Model issue on line 0 :\n .model x:rbody_model r p2=0\nunrecognized parameter (p2) - ignored\n'
    assert L.warning_audit(log)['passive_nonlinearity_verified'] is False
    for extra in ['Warning: iteration limit reached','unrecognized parameter (invented) - ignored',
                  'Error: no such vector','Warning: Model issue on line 0 :\n .model foo nmos']:
        with pytest.raises((ValueError,RuntimeError)): L.warning_audit(log+'\n'+extra)


def good(kind):
    return {'instrument_ok':True,'small_signal_specs_pass':True,'hd3_model_pass':True,
            'ctle_hd3':{'hd3_dbc':-60.,'fundamental_peak_v':.05},'harmonic_window_stable':True}


def test_schedule_bounded_stops_bad_instruments_retains_target_failures():
    calls=[]
    def run(i,kind,state,step): calls.append((i,kind,state,step));return good(kind)
    r=L.schedule(run)
    assert len(calls)==20 and r['nominal_loaded_screen_pass']
    assert not r['full_receiver_verified'] and not r['clocked_receiver_noise_verified']
    assert len(set(calls))==20
    calls.clear()
    def fail(i,kind,state,step): calls.append(kind);return {'instrument_ok':False}
    r=L.schedule(fail);assert len(calls)==2 and not r['nominal_loaded_screen_pass']
    calls.clear()
    def target_fail(i,kind,state,step):
        calls.append((i,kind));return {**good(kind),'small_signal_specs_pass':False}
    r=L.schedule(target_fail);assert len(calls)==20 and not r['nominal_loaded_screen_pass']
    calls.clear()
    def bad_tone(i,kind,state,step):
        calls.append(kind);return good(kind) if kind=='static' else {'instrument_ok':False}
    r=L.schedule(bad_tone);assert len(calls)==4 and not r['nominal_loaded_screen_pass']


def test_resolution_agreement_is_not_a_spec_relaxation():
    a=good('tone');b=good('tone')
    assert L.resolution_matches(a,b)
    b={**b,'ctle_hd3':{'hd3_dbc':-59.,'fundamental_peak_v':.05}}
    assert not L.resolution_matches(a,b)
    assert not L.resolution_matches(a,{'instrument_ok':False})


def test_plan_and_source_closure():
    from nebula.experiments import exp_dfe_loaded_analog as E, exp_dfe_configurable_pvt as Q
    root=Path(__file__).resolve().parents[2]
    name='nebula/DFE_LOADED_ANALOG_PLAN.md'
    assert name+' text eol=lf' in (root/'.gitattributes').read_text()
    assert b'\r\n' not in (root/name).read_bytes()
    assert set(Q.SOURCES)<=set(E.SOURCES)


def test_complete_tone_extractor_checks_input_clock_power_and_late_harmonics():
    # Analytic fixture only. Real prior DC terminal biases supply sensible
    # common modes; synthetic signals are never saved as experiment evidence.
    from nebula.device import dfe_timing as T
    from nebula.experiments import evidence_archive as A
    root=Path(__file__).resolve().parents[1]/'product_audits/entry132_dfe_configurable_20260910/phase_tuned1_phase1_code2_sign1'
    source=(root/'design.cir').read_text()
    _,raw=T.read_table(A.trace_path(root/'terminals.txt'),len(C.terminals(source)))
    bias=dict(zip(C.terminals(source),raw[0]))
    bias.update(vid=0.,rctrl=1.26,cctrl=.297,rc_gate=1.26,rc_ct=.297,vdd=1.8)
    text=L.deck(7,'tone',0,5e-12)
    t=np.arange(30001)*5e-12
    nodes={n:np.full(len(t),bias[n]) for n in L.nodes_for(text)}
    nodes['df_clk'],nodes['df_clkb']=F.clock_at(t,1.8,1.)
    nodes['vid']=.1*np.sin(2*np.pi*1e8*t)
    output=.05*np.sin(2*np.pi*1e8*t)+.00005*np.sin(2*np.pi*3e8*t)
    nodes['outn']+=output/2;nodes['outp']-=output/2
    nodes['sum_p']+=output/2;nodes['sum_n']-=output/2
    y=np.zeros((len(t),len(L.VECTORS)))
    for j,v in enumerate(L.VECTORS):
        if v.startswith('v('): y[:,j]=nodes[v[2:-1]]
    y[:,7]=-.005
    r=L.tone_metrics(text,7,5e-12,t,y,nodes)
    assert r['instrument_ok'] and r['harmonic_window_stable']
    assert r['ctle_hd3']['hd3_dbc']==pytest.approx(-60,abs=.001)
    assert r['ctle_plus_dfe_vdd_power_w']==pytest.approx(.009)
    assert not r['full_receiver_verified'] and not r['passive_nonlinearity_verified']
    bad=y.copy();bad[:,7]=0
    with pytest.raises(ValueError,match='power'): L.tone_metrics(text,7,5e-12,t,bad,nodes)
    bad=y.copy();bad[:,0]+=.01
    with pytest.raises(ValueError,match='differs'): L.tone_metrics(text,7,5e-12,t,bad,nodes)
    with pytest.raises(ValueError,match='incomplete'):
        L.tone_metrics(text,7,5e-12,t[:-1],y[:-1],{n:a[:-1] for n,a in nodes.items()})
    extra=.0002*np.sin(2*np.pi*3e8*t)*(t>=100e-9)
    nodes['outn']+=extra/2;nodes['outp']-=extra/2
    y[:,12]=nodes['outn'];y[:,11]=nodes['outp']
    r=L.tone_metrics(text,7,5e-12,t,y,nodes)
    assert not r['harmonic_window_stable'] and not r['hd3_model_pass']
