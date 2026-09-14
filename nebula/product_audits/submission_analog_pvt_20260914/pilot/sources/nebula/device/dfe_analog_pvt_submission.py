"""Supply-parameterized Entry 143 measurements, separate submission evidence.

The three copied measurement functions retain the frozen arithmetic, with only
explicit supply parameters. Source-equivalence tests guard that narrow change.
Physical device parameters remain defined in the original generator.
"""
from pathlib import Path
import numpy as np
from nebula.common.types import Corner, all_corners
from nebula.link.config import LinkConfig
from nebula.device import dfe_calibrated_verification as N

L,I,C=N.L,N.I,N.C
F,B,V,D,R,T=N.F,N.B,N.V,N.D,N.R,N.T
E,K,A=N.E,N.K,N.A
nodes_for,noise_metrics,harmonics=L.nodes_for,L.noise_metrics,L.harmonics
VECTORS,STOP=L.VECTORS,L.STOP
TARGET=N.TARGET
PILOT=(Corner('tt',1.,27),Corner('fs',.95,125))


def measurements():
    return [('static',s,E.TOLERANCES[-1],L.STEPS[0]) for s in (0,1)]+[
        ('tone',0,tol,step) for tol in E.TOLERANCES for step in L.STEPS]


def deck(kind,state,tol,step,reference,corner):
    if corner not in all_corners(): raise ValueError('unregistered PVT corner')
    if (kind,state,tol,step) not in measurements(): raise ValueError('unregistered analog case')
    vdd=1.8*corner.vdd_scale
    cfg=LinkConfig(channel_loss_db_at_nyquist=7.5)
    text=C.deck(True,corner,cfg,F.pattern(cfg),1.,2,1).split('.control')[0]
    text=L.replace_once(text,r'^Vid vid 0 PWL\(\n(?:\+[^\n]*\n)*\+ \)',
        'Vid vid 0 DC 0 AC 1'+(' SIN(0 0.1 100meg)' if kind=='tone' else ''))
    for name,node,fraction in [('VrcR','rctrl',TARGET[2]),('VrcC','cctrl',TARGET[3])]:
        text=L.replace_once(text,rf'^{name} .*$',f'{name} {node} 0 {vdd*fraction:.16g}')
    if kind=='static':
        for name,voltage in [('clk',.6 if state==0 else 1.2),('clkb',1.2 if state==0 else .6)]:
            text=L.replace_once(text,rf'^Vdf{name} .*$',f'Vdf{name} df_{name} 0 {voltage*corner.vdd_scale:.16g}')
    # Frozen nominal deck supplies all analysis settings and released NODESET.
    nominal=N.deck(kind,state,tol,step,reference)
    suffix=nominal[nominal.index('.options reltol='):]
    return text+suffix


def voltage_audit(text,nodes,target,vdd):
    whole=V.audit(F.all_mos(text),nodes)
    new=V.audit(F.extra_mos(1)+B.bleeders(4.),nodes)
    switch=V.audit([s for s in F.all_mos(text) if s.startswith('Xrc_switch ')],nodes)
    valid=all(np.max(abs(nodes[n]-v))<=1e-8 for n,v in
              [('vdd',vdd),('rctrl',vdd*target[2]),('cctrl',vdd*target[3])])
    varactor=all(np.all((nodes[n]>=0)&(nodes[n]<=1.95)&(abs(nodes[n]-nodes['rc_ct'])<=2.))
                 for n in ('s1','s2'))
    varactor &= bool(np.all((nodes['rc_ct']>=0)&(nodes['rc_ct']<=1.95)))
    return {'whole_circuit_voltage_audit':whole,'new_dfe_voltage_audit':new,
            'new_tuning_switch_voltage_audit':switch,'external_controls_valid':bool(valid),
            'varactor_voltage_envelope_pass':bool(varactor),
            'voltage_gate_pass':bool(valid and varactor and D.envelope(whole) and new['documented_ranges_ok'])}


def static_metrics(text,target,state,op,ac,total,spectrum,vdd):
    names=nodes_for(text);op=np.atleast_2d(np.asarray(op,dtype=float))
    if op.shape!=(1,len(names)+2) or not np.isfinite(op).all():
        raise ValueError('malformed loaded DC primitives')
    nodes={n:op[:,i+1] for i,n in enumerate(names)}
    expected=(vdd/3,2*vdd/3) if state==0 else (2*vdd/3,vdd/3)
    if any(np.max(abs(nodes[n]-v))>1e-8 for n,v in zip(('df_clk','df_clkb'),expected)):
        raise ValueError('wrong held clock state')
    if abs(float(nodes['vid'][0]))>1e-12: raise ValueError('wrong DC differential input')
    power=float(-vdd*op[0,-1])
    if power<=0: raise ValueError('nonpositive supplied DC power')
    response=R.response_metrics(R.parse_ac(ac,1)[:,0])
    noise=noise_metrics(total,spectrum);audit=voltage_audit(text,nodes,target,vdd)
    boost,freq=target[:2]
    match=bool(response['interior_peak'] and abs(response['boost_db']-boost)<=.5
               and abs(response['peak_frequency_hz']-freq)<=1e8)
    return {'instrument_ok':True,'response':response,'noise':noise,'vdd_power_w':power,
            'dc_nodes_v':{n:float(v[0]) for n,v in nodes.items()},**audit,
            'target_match':match,'target_tolerance_is_internal':True,
            'small_signal_specs_pass':bool(response['ac_shape_pass'] and noise['noise_limit_pass']
                                           and power<.015 and audit['voltage_gate_pass']),
            'full_receiver_verified':False}


def tone_metrics(text,target,step,t,y,nodes,vdd):
    t,y=np.asarray(t),np.asarray(y)
    if (t.ndim!=1 or len(t)<100 or y.shape!=(len(t),len(VECTORS)) or not np.isfinite(y).all()
            or not np.isfinite(t).all() or np.any(np.diff(t)<=0)
            or t[0]>1e-15 or t[-1]<STOP-1e-15 or np.max(np.diff(t))>step*1.002):
        raise ValueError('incomplete or malformed clocked distortion trace')
    for j,vector in enumerate(VECTORS):
        if vector.startswith('v(') and vector[2:-1] in nodes and not np.array_equal(y[:,j],nodes[vector[2:-1]]):
            raise ValueError('duplicated main/terminal primitive differs')
    expected=(*F.clock_at(t,vdd,1.),.1*np.sin(2*np.pi*1e8*t))
    errors=[float(np.max(abs(y[:,j]-value))) for j,value in enumerate(expected)]
    if max(errors)>1e-6: raise ValueError('clock or differential tone primitive mismatch')
    for k in range(4):
        if np.max(abs(y[:,14+2*k]-(vdd if k==1 else 0)))>1e-8:
            raise ValueError('wrong physical DAC code')
    differential=y[:,12]-y[:,11]
    windows=[harmonics(t,differential,a,b) for a,b in ((50e-9,150e-9),(50e-9,100e-9),(100e-9,150e-9))]
    stable=abs(windows[1]['hd3_dbc']-windows[2]['hd3_dbc'])<=.5
    audit=voltage_audit(text,nodes,target,vdd)
    uniform=50e-9+np.arange(40001)*2.5e-12
    def average(a): return float(np.trapezoid(np.interp(uniform,t,a),uniform)/(100e-9))
    power=average(-vdd*y[:,7])
    if power<=0: raise ValueError('nonpositive clocked supplied power')
    clock=sum(average(np.maximum(-y[:,j]*y[:,j+8],0)) for j in (0,1))
    rc=sum(average(np.maximum(-y[:,25+j]*y[:,29+j],0)) for j in (0,1))
    return {'instrument_ok':True,'stimulus_max_error_v':errors,**audit,
            'ctle_hd3':windows[0],'subwindow_hd3':windows[1:],'harmonic_window_stable':bool(stable),
            'summer_harmonics_diagnostic':harmonics(t,y[:,3]-y[:,4],50e-9,150e-9),
            'ctle_plus_dfe_vdd_power_w':power,'external_clock_positive_power_w':clock,
            'external_rc_control_positive_power_w':rc,'input_differential_peak_v':.1,
            'tone_hz':1e8,'hd3_model_pass':bool(all(w['hd3_dbc']<-30 for w in windows)
                and stable and audit['voltage_gate_pass'] and power<.015),
            'passive_nonlinearity_verified':False,'full_receiver_verified':False}


def nyquist_metrics(ac):
    h=R.parse_ac(ac,1)[:,0]
    db=20*np.log10(abs(h))
    boost=float(np.interp(np.log(2.5e9),np.log(R.FREQUENCIES_HZ),db)-db[0])
    return {'nyquist_boost_db':boost,'positive_nyquist_pass':bool(boost>0)}


def corner_summary(static,tones):
    complete=len(static)==2 and len(tones)==4
    valid=bool(complete and all(I.valid(r) for r in static+tones))
    agreement=bool(len(tones)==4 and all(L.resolution_matches(a,b)
        for i,a in enumerate(tones) for b in tones[i+1:]))
    return {'instrument_complete':valid,'four_way_agreement':agreement,
        'analog_model_pass':bool(valid and agreement
            and all(r.get('small_signal_specs_pass',False) and r.get('positive_nyquist_pass',False) for r in static)
            and all(r.get('hd3_model_pass',False) for r in tones)),
        'target_match':bool(len(static)==2 and all(r.get('target_match',False) for r in static)),
        'all_static_branches_verified':False,'clocked_receiver_noise_verified':False,
        'full_receiver_verified':False}


def extract(folder,text,kind,state,step,corner):
    folder=Path(folder);log=(folder/'ngspice.log').read_text()
    E.abort_audit(log);warnings=L.warning_audit(log)
    vdd=1.8*corner.vdd_scale
    if kind=='static':
        op,ac,total,spectrum=[np.loadtxt(folder/name) for name in ('op.txt','ac.txt','noise_total.txt','noise_spectrum.txt')]
        result=static_metrics(text,TARGET,state,op,ac,total,spectrum,vdd)
        result.update(nyquist_metrics(ac))
        q=result['dc_nodes_v']['df_q']-result['dc_nodes_v']['df_qb']
    else:
        t,y=T.read_table(A.trace_path(folder/'trace.txt'),len(VECTORS))
        names=nodes_for(text);_,ny=T.read_table(A.trace_path(folder/'terminals.txt'),len(names),expected_time=t)
        result=tone_metrics(text,TARGET,step,t,y,dict(zip(names,ny.T)),vdd)
        q=float(y[0,5]-y[0,6])
    result.update(initialization_valid=bool(q<-.1),initial_stored_differential_v=q,
        nodeset_is_released_initial_guess=True,model_warnings=warnings)
    return result
