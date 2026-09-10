"""Entry 137: loaded CTLE analog screen, not periodic receiver-noise signoff."""
import re

import numpy as np

from nebula.common.types import Corner
from nebula.link.config import LinkConfig
from nebula.device import dfe_configurable as C, dfe_connected as F, dfe_tail_bleed as B
from nebula.device import dfe_voltage_audit as V, configurable_rc as R, dfe_timing as T
from nebula.device.crosscheck import assert_no_silent_failures
from nebula.experiments import exp_dfe_connected as D

# Already selected in Entry 131; no fitting to the new loaded measurements.
TARGETS=((3.,1.5e9,.81,0.),(3.,1.9e9,.79,.135),(3.,2.25e9,.78,.18),
         (6.,1.5e9,.73,.075),(6.,1.9e9,.73,.15),(6.,2.25e9,.73,.195),
         (9.,1.5e9,.7,.105),(9.,1.9e9,.7,.165),(9.,2.25e9,.7,.21))
PRIMARY=7
NOISE_FREQUENCIES=np.arange(1,501,dtype=float)*1e7
STEPS=(5e-12,2.5e-12)
STOP=150e-9
VECTORS=F.VECTORS+C.RC_VECTORS


def replace_once(text,pattern,replacement):
    text,n=re.subn(pattern,lambda _:replacement,text,flags=re.M)
    if n!=1: raise ValueError('expected exactly one source or control block')
    return text


def deck(index,kind,state=0,step=5e-12):
    if index not in range(9) or kind not in ('static','tone') or state not in (0,1) or step not in STEPS:
        raise ValueError('unregistered loaded analog case')
    if kind=='tone' and (index!=PRIMARY or state!=0):
        raise ValueError('only the primary clocked distortion case is registered')
    cfg=LinkConfig(channel_loss_db_at_nyquist=7.5)
    text=C.deck(True,Corner('tt',1.,27),cfg,F.pattern(cfg),1.,2,1).split('.control')[0]
    text=replace_once(text,r'^Vid vid 0 PWL\(\n(?:\+[^\n]*\n)*\+ \)',
                      'Vid vid 0 DC 0 AC 1'+(' SIN(0 0.1 100meg)' if kind=='tone' else ''))
    for name,node,fraction in [('VrcR','rctrl',TARGETS[index][2]),('VrcC','cctrl',TARGETS[index][3])]:
        text=replace_once(text,rf'^{name} .*$',f'{name} {node} 0 {1.8*fraction:.16g}')
    if kind=='static':
        for name,voltage in [('clk',.6 if state==0 else 1.2),('clkb',1.2 if state==0 else .6)]:
            text=replace_once(text,rf'^Vdf{name} .*$',f'Vdf{name} df_{name} 0 {voltage:.16g}')
    # Precision is an analysis setting, not a geometry/clock change.
    text+='.options reltol=1e-7 vntol=1e-10 abstol=1e-13\n'
    names=nodes_for(text)
    lines=['.control','set noaskquit','set numdgt=15','set wr_singlescale','unset sqrnoise']
    if kind=='static':
        lines+=['op','wrdata op.txt '+' '.join(f'v({n})' for n in names)+' i(vdd)',
                'ac dec 50 1meg 100g','wrdata ac.txt v(outp) v(outn) v(vid)',
                'noise v(outn,outp) Vid lin 500 10meg 5g',
                'wrdata noise_total.txt inoise_total onoise_total',
                'setplot noise1','wrdata noise_spectrum.txt inoise_spectrum onoise_spectrum']
    else:
        lines+=[f'tran {step:.16g} 150n 0 {step:.16g}',
                'wrdata trace.txt '+' '.join(VECTORS),
                'wrdata terminals.txt '+' '.join(f'v({n})' for n in names)]
    return text+'\n'.join(lines+['quit','.endc','.end'])+'\n'


def nodes_for(text):
    return tuple(sorted(set(C.terminals(text))|{'vid','rctrl','cctrl','rc_ct','rc_gate','vdd'}))


def warning_audit(log):
    assert_no_silent_failures(log)
    lines=log.splitlines();ignored=[]
    for i,line in enumerate(lines):
        match=re.search(r'unrecognized parameter \(([^)]+)\) - ignored',line,re.I)
        if match:
            if match[1] not in ('sw_et','isnoisy','p2','q2','p3','q3'):
                raise ValueError('unregistered ignored model parameter')
            ignored.append(match[1])
        elif 'unrecognized' in line.lower():
            raise ValueError('unregistered model message')
        if re.search(r'\bwarning\b',line,re.I):
            if 'm=xx on .subckt line will override multiplier' in line or 'conductance reset to' in line:
                continue
            if ('Warning: Model issue on line 0 :' in line and i+1<len(lines)
                    and re.search(r'^\s*\.model\s+\S+\s+r\s',lines[i+1],re.I)):
                continue
            raise ValueError('unregistered simulator warning: '+line.strip())
    return {'ignored_model_parameters':sorted(set(ignored)),
            'passive_nonlinearity_verified':False,'reliability_verified':False}


def voltage_audit(text,nodes,index):
    whole=V.audit(F.all_mos(text),nodes)
    new=V.audit(F.extra_mos(1)+B.bleeders(4.),nodes)
    switch=V.audit([s for s in F.all_mos(text) if s.startswith('Xrc_switch ')],nodes)
    valid=all(np.max(abs(nodes[n]-v))<=1e-8 for n,v in
              [('vdd',1.8),('rctrl',1.8*TARGETS[index][2]),('cctrl',1.8*TARGETS[index][3])])
    varactor=all(np.all((nodes[n]>=0)&(nodes[n]<=1.95)&(abs(nodes[n]-nodes['rc_ct'])<=2.))
                 for n in ('s1','s2'))
    varactor &= bool(np.all((nodes['rc_ct']>=0)&(nodes['rc_ct']<=1.95)))
    return {'whole_circuit_voltage_audit':whole,'new_dfe_voltage_audit':new,
            'new_tuning_switch_voltage_audit':switch,'external_controls_valid':bool(valid),
            'varactor_voltage_envelope_pass':bool(varactor),
            'voltage_gate_pass':bool(valid and varactor and D.envelope(whole) and new['documented_ranges_ok'])}


def noise_metrics(total,spectrum):
    total=np.atleast_2d(np.asarray(total,dtype=float));spectrum=np.asarray(spectrum,dtype=float)
    if (total.shape!=(1,3) or spectrum.shape!=(500,3) or not np.isfinite(total).all()
            or not np.isfinite(spectrum).all() or np.any(total[:,1:]<=0)
            or np.any(spectrum[:,1:]<=0)
            or not np.allclose(spectrum[:,0],NOISE_FREQUENCIES,rtol=1e-12,atol=1e-3)):
        raise ValueError('missing/nonfinite noise primitives or incomplete 10 MHz to 5 GHz band')
    # Default ngspice output: totals are RMS V, spectra are V/sqrt(Hz).
    reintegrated=np.sqrt(np.trapezoid(spectrum[:,1:]**2,spectrum[:,0],axis=0))
    errors=abs(reintegrated/total[0,1:]-1.)
    if np.any(errors>.02): raise ValueError('noise total disagrees with independent spectral integral')
    return {'input_noise_vrms':float(total[0,1]),'output_noise_vrms':float(total[0,2]),
            'spectrum_reintegrated_vrms':reintegrated.tolist(),'integral_relative_errors':errors.tolist(),
            'noise_limit_pass':bool(total[0,1]<.0015),'band_hz':[1e7,5e9],
            'clocked_receiver_noise_verified':False,
            'scope':'loaded CTLE output, held-clock DC small-signal model; not periodic receiver noise'}


def static_metrics(text,index,state,op,ac,total,spectrum):
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
    noise=noise_metrics(total,spectrum);audit=voltage_audit(text,nodes,index)
    boost,freq=TARGETS[index][:2]
    match=bool(response['interior_peak'] and abs(response['boost_db']-boost)<=.5
               and abs(response['peak_frequency_hz']-freq)<=1e8)
    return {'instrument_ok':True,'response':response,'noise':noise,'vdd_power_w':power,
            'dc_nodes_v':{n:float(v[0]) for n,v in nodes.items()},**audit,
            'target_match':match,'target_tolerance_is_internal':True,
            'small_signal_specs_pass':bool(response['ac_shape_pass'] and noise['noise_limit_pass']
                                           and power<.015 and audit['voltage_gate_pass']),
            'full_receiver_verified':False}


def harmonics(t,v,start,stop):
    t,v=np.asarray(t,dtype=float),np.asarray(v,dtype=float)
    cycles=(stop-start)*1e8
    if (t.ndim!=1 or len(t)<100 or v.shape!=t.shape or not np.isfinite(t).all()
            or not np.isfinite(v).all() or np.any(np.diff(t)<=0) or np.max(np.diff(t))>5.01e-12
            or t[0]>start+1e-15 or t[-1]<stop-1e-15
            or abs(cycles-round(cycles))>1e-8 or cycles<1):
        raise ValueError('invalid, incomplete or non-integer harmonic capture')
    n=round((stop-start)/2.5e-12);uniform=start+np.arange(n)*2.5e-12
    y=np.interp(uniform,t,v);fft=np.fft.rfft(y-y.mean())*2/n
    k=round(cycles);v1,v3,vc=map(float,abs(fft[[k,3*k,50*k]]))
    if v1<1e-6 or v3<=0: raise ValueError('missing fundamental or third-harmonic primitive')
    return {'hd3_dbc':float(20*np.log10(v3/v1)),'fundamental_peak_v':v1,
            'third_harmonic_peak_v':v3,'clock_5ghz_peak_v':vc,
            'start_s':start,'stop_s':stop,'cycles':round(cycles),'uniform_samples':n}


def tone_metrics(text,index,step,t,y,nodes):
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
    audit=voltage_audit(text,nodes,index)
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


def resolution_matches(a,b):
    if not a.get('instrument_ok') or not b.get('instrument_ok'): return False
    x,y=a['ctle_hd3'],b['ctle_hd3']
    return bool(abs(x['hd3_dbc']-y['hd3_dbc'])<=.5
                and abs(x['fundamental_peak_v']/y['fundamental_peak_v']-1)<=.01)


def schedule(evaluate):
    result={'entry':137,'static':[],'tones':[],'nominal_loaded_screen_pass':False,
            'measurement_complete':False,'full_receiver_verified':False,
            'clocked_receiver_noise_verified':False,'full_tuning_rectangle_verified':False}
    def static(i,state):
        r=evaluate(i,'static',state,STEPS[0])
        result['static'].append({'target_index':i,'clock_state':state,'result':r})
        return r
    first=[static(PRIMARY,s) for s in (0,1)]
    if not all(r.get('instrument_ok') for r in first): return result
    result['tones']=[evaluate(PRIMARY,'tone',0,s) for s in STEPS]
    if not all(r.get('instrument_ok') for r in result['tones']): return result
    result['resolution_agreement']=resolution_matches(*result['tones'])
    for i in range(9):
        if i!=PRIMARY:
            for state in (0,1): static(i,state)
    result['measurement_complete']=all(r['result'].get('instrument_ok',False) for r in result['static'])
    result['loaded_target_count']=sum(all(r['result'].get('target_match',False)
        and r['result'].get('small_signal_specs_pass',False) for r in result['static'] if r['target_index']==i)
        for i in range(9))
    result['nominal_loaded_screen_pass']=bool(result['measurement_complete'] and result['resolution_agreement']
        and all(r['result'].get('small_signal_specs_pass',False) for r in result['static'])
        and all(r.get('hd3_model_pass',False) for r in result['tones']))
    return result
