"""Entry 143: unchanged measurement formulas with explicit calibrated controls.

Analog and RC-audit functions below are frozen predecessors parameterized
only by target/control arguments. Exact-source regression tests enforce that
boundary; no model card or physical circuit is redeclared.
"""
from pathlib import Path
import numpy as np
from nebula.common.types import Corner, UI_SECONDS as UI
from nebula.link.config import LinkConfig
from nebula.device import dfe_loaded_analog as L, dfe_loaded_initialization as I, dfe_configurable as C
from nebula.experiments import exp_dfe_linearity_tolerance as E, exp_dfe_loaded_calibration as K
from nebula.experiments import evidence_archive as A

F,B,V,D,R,T=L.F,L.B,L.V,L.D,L.R,L.T
nodes_for,noise_metrics,harmonics=L.nodes_for,L.noise_metrics,L.harmonics
VECTORS,STOP=L.VECTORS,L.STOP
TARGET=(9.,1.9e9,.7,.185)


def deck(kind,state,tol,step,reference):
    text=I.deck('static',state,step,-1,reference) if kind=='static' else E.deck(tol,step,reference)
    if kind not in ('static','tone'): raise ValueError('unregistered calibrated analysis')
    for name,node,fraction in [('VrcR','rctrl',TARGET[2]),('VrcC','cctrl',TARGET[3])]:
        text=L.replace_once(text,rf'^{name} .*$',f'{name} {node} 0 {1.8*fraction:.16g}')
    return text


def link_deck():
    corner=Corner('tt',1.,27);cfg=LinkConfig(channel_loss_db_at_nyquist=7.5)
    text=C.deck(True,corner,cfg,F.pattern(cfg),1.,2,1)
    for name,node,fraction in [('VrcR','rctrl',TARGET[2]),('VrcC','cctrl',TARGET[3])]:
        text=L.replace_once(text,rf'^{name} .*$',f'{name} {node} 0 {1.8*fraction:.16g}')
    return text


def voltage_audit(text,nodes,target):
    whole=V.audit(F.all_mos(text),nodes)
    new=V.audit(F.extra_mos(1)+B.bleeders(4.),nodes)
    switch=V.audit([s for s in F.all_mos(text) if s.startswith('Xrc_switch ')],nodes)
    valid=all(np.max(abs(nodes[n]-v))<=1e-8 for n,v in
              [('vdd',1.8),('rctrl',1.8*target[2]),('cctrl',1.8*target[3])])
    varactor=all(np.all((nodes[n]>=0)&(nodes[n]<=1.95)&(abs(nodes[n]-nodes['rc_ct'])<=2.))
                 for n in ('s1','s2'))
    varactor &= bool(np.all((nodes['rc_ct']>=0)&(nodes['rc_ct']<=1.95)))
    return {'whole_circuit_voltage_audit':whole,'new_dfe_voltage_audit':new,
            'new_tuning_switch_voltage_audit':switch,'external_controls_valid':bool(valid),
            'varactor_voltage_envelope_pass':bool(varactor),
            'voltage_gate_pass':bool(valid and varactor and D.envelope(whole) and new['documented_ranges_ok'])}


def static_metrics(text,target,state,op,ac,total,spectrum):
    names=nodes_for(text);op=np.atleast_2d(np.asarray(op,dtype=float))
    if op.shape!=(1,len(names)+2) or not np.isfinite(op).all():
        raise ValueError('malformed loaded DC primitives')
    nodes={n:op[:,i+1] for i,n in enumerate(names)}
    expected=(.6,1.2) if state==0 else (1.2,.6)
    if any(np.max(abs(nodes[n]-v))>1e-8 for n,v in zip(('df_clk','df_clkb'),expected)):
        raise ValueError('wrong held clock state')
    if abs(float(nodes['vid'][0]))>1e-12: raise ValueError('wrong DC differential input')
    power=float(-1.8*op[0,-1])
    if power<=0: raise ValueError('nonpositive supplied DC power')
    response=R.response_metrics(R.parse_ac(ac,1)[:,0])
    noise=noise_metrics(total,spectrum);audit=voltage_audit(text,nodes,target)
    boost,freq=target[:2]
    match=bool(response['interior_peak'] and abs(response['boost_db']-boost)<=.5
               and abs(response['peak_frequency_hz']-freq)<=1e8)
    return {'instrument_ok':True,'response':response,'noise':noise,'vdd_power_w':power,
            'dc_nodes_v':{n:float(v[0]) for n,v in nodes.items()},**audit,
            'target_match':match,'target_tolerance_is_internal':True,
            'small_signal_specs_pass':bool(response['ac_shape_pass'] and noise['noise_limit_pass']
                                           and power<.015 and audit['voltage_gate_pass']),
            'full_receiver_verified':False}


def tone_metrics(text,target,step,t,y,nodes):
    t,y=np.asarray(t),np.asarray(y)
    if (t.ndim!=1 or len(t)<100 or y.shape!=(len(t),len(VECTORS)) or not np.isfinite(y).all()
            or not np.isfinite(t).all() or np.any(np.diff(t)<=0)
            or t[0]>1e-15 or t[-1]<STOP-1e-15 or np.max(np.diff(t))>step*1.002):
        raise ValueError('incomplete or malformed clocked distortion trace')
    for j,vector in enumerate(VECTORS):
        if vector.startswith('v(') and vector[2:-1] in nodes and not np.array_equal(y[:,j],nodes[vector[2:-1]]):
            raise ValueError('duplicated main/terminal primitive differs')
    expected=(*F.clock_at(t,1.8,1.),.1*np.sin(2*np.pi*1e8*t))
    errors=[float(np.max(abs(y[:,j]-value))) for j,value in enumerate(expected)]
    if max(errors)>1e-6: raise ValueError('clock or differential tone primitive mismatch')
    for k in range(4):
        if np.max(abs(y[:,14+2*k]-(1.8 if k==1 else 0)))>1e-8:
            raise ValueError('wrong physical DAC code')
    differential=y[:,12]-y[:,11]
    windows=[harmonics(t,differential,a,b) for a,b in ((50e-9,150e-9),(50e-9,100e-9),(100e-9,150e-9))]
    stable=abs(windows[1]['hd3_dbc']-windows[2]['hd3_dbc'])<=.5
    audit=voltage_audit(text,nodes,target)
    uniform=50e-9+np.arange(40001)*2.5e-12
    def average(a): return float(np.trapezoid(np.interp(uniform,t,a),uniform)/(100e-9))
    power=average(-1.8*y[:,7])
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


def control_audit(t,y,nodes,vdd,r_fraction,c_fraction):
    t=np.asarray(t);y=np.asarray(y)
    if (t.ndim!=1 or len(t)<2 or y.shape!=(len(t),6) or not np.isfinite(t).all()
            or not np.isfinite(y).all() or np.any(np.diff(t)<=0) or not np.isfinite(vdd) or vdd<=0):
        raise ValueError('malformed configurable control primitives')
    sources=[np.asarray(nodes[n]) for n in ('s1','s2')]
    if any(a.shape!=t.shape or not np.isfinite(a).all() for a in sources):
        raise ValueError('missing/nonfinite varactor source terminals')
    mask=(t>=(F.WARMUP+2)*UI)&(t<=(F.N_BITS+2)*UI)
    if mask.sum()<2: raise ValueError('missing control energy window')
    errors=[float(max(abs(y[:,i]-vdd*f))) for i,f in enumerate((r_fraction,c_fraction))]
    envelope=all(np.all((a>=0)&(a<=1.95)&(abs(a-y[:,3])<=2.)) for a in sources)
    envelope &= bool(np.all((y[:,3]>=0)&(y[:,3]<=1.95)))
    power=-y[:,:2]*y[:,4:6]
    def average(a): return float(np.trapezoid(a[mask],t[mask])/(t[mask][-1]-t[mask][0]))
    return {'control_valid':max(errors)<=1e-8,'external_bias_max_error_v':errors,
            'varactor_voltage_envelope_pass':bool(envelope),
            'source_min_v':min(float(a.min()) for a in sources),'source_max_v':max(float(a.max()) for a in sources),
            'internal_control_min_v':float(y[:,3].min()),'internal_control_max_v':float(y[:,3].max()),
            'r_gate_ripple_pp_v':float(np.ptp(y[mask,2])),'c_node_ripple_pp_v':float(np.ptp(y[mask,3])),
            'external_rc_control_net_power_w':sum(average(power[:,i]) for i in range(2)),
            'external_rc_control_positive_power_w':sum(average(np.maximum(power[:,i],0)) for i in range(2)),
            'runtime_settling_verified':False,'reliability_verified':False}


def analog_extract(folder,text,kind,state,step,calibration,calibration_ac):
    folder=Path(folder);log=(folder/'ngspice.log').read_text()
    E.abort_audit(log);warnings=L.warning_audit(log)
    if kind=='static':
        op,ac,total,spectrum=[np.loadtxt(folder/name) for name in ('op.txt','ac.txt','noise_total.txt','noise_spectrum.txt')]
        result=static_metrics(text,TARGET,state,op,ac,total,spectrum)
        q=result['dc_nodes_v']['df_q']-result['dc_nodes_v']['df_qb']
        result['calibration_matches']=K.calibration_matches(result,calibration,ac,calibration_ac) if state==0 else None
    else:
        t,y=T.read_table(A.trace_path(folder/'trace.txt'),len(VECTORS))
        names=nodes_for(text);_,ny=T.read_table(A.trace_path(folder/'terminals.txt'),len(names),expected_time=t)
        result=tone_metrics(text,TARGET,step,t,y,dict(zip(names,ny.T)))
        q=float(y[0,5]-y[0,6])
    result.update(initialization_valid=bool(q<-.1),initial_stored_differential_v=q,
                  nodeset_is_released_initial_guess=True,model_warnings=warnings)
    return result


def link_extract(folder,text):
    folder=Path(folder);log=(folder/'ngspice.log').read_text()
    E.abort_audit(log);warnings=L.warning_audit(log)
    cfg=LinkConfig(channel_loss_db_at_nyquist=7.5);bits=F.pattern(cfg)
    t,y=T.read_table(A.trace_path(folder/'trace.txt'),len(VECTORS));main=y[:,:len(F.VECTORS)]
    result=F.analyze(t,main,bits,cfg,1.,1.8,code=2)
    names=C.terminals(text);_,ny=T.read_table(A.trace_path(folder/'terminals.txt'),len(names),expected_time=t)
    nodes=dict(zip(names,ny.T));mos=F.all_mos(text)
    whole=V.audit(mos,nodes);new=V.audit(F.extra_mos(1)+B.bleeders(4.),nodes)
    result.update(instrument_ok=True,new_dfe_voltage_audit=new,whole_circuit_voltage_audit=whole,
        whole_circuit_voltage_envelope_pass=D.envelope(whole),
        aperture=T.aperture(t,main[:,3]-main[:,4],bits,1.),
        tuning_controls=control_audit(t,y[:,len(F.VECTORS):],nodes,1.8,TARGET[2],TARGET[3]),
        new_tuning_switch_voltage_audit=V.audit([s for s in mos if s.startswith('Xrc_switch ')],nodes),
        model_warnings=warnings)
    result['signal_gate_pass']=C.accepted(result)
    return result
