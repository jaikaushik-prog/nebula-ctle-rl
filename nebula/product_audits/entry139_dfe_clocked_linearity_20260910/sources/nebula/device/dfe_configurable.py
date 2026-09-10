"""Entry 132: measured physical Rs/Cs network connected to the unchanged CML DFE."""
import re

import numpy as np

from nebula.common.types import UI_SECONDS as UI
from nebula.device import dfe_connected as F, dfe_hardware as D, dfe_timing as T
from nebula.device import dfe_tail_bleed as B, configurable_rc as R, varactor_probe as V
from nebula.experiments import exp_dfe_connected as E, exp_dfe_tail_bleed as H

GEOMETRY=(500,0.)
R_FRACTION,C_FRACTION=.7,.165
RC_VECTORS=('v(rctrl)','v(cctrl)','v(rc_gate)','v(rc_ct)','i(vrcr)','i(vrcc)')


def terminals(text): return D.terminal_nodes(F.all_mos(text))


def deck(tuned,corner,cfg,bits,phase,code,sign):
    text=B.deck(4.,corner,cfg,bits,phase,code,sign)
    text,n=re.subn(r'^\.lib\s+.*$',lambda _:f'.lib "{V.FULL_LIB.as_posix()}" {corner.process}',text,flags=re.M)
    if n!=1: raise ValueError('expected exactly one physical model library')
    if not tuned: return text
    for name in ('Xrs','Xcs'):
        text,n=re.subn(rf'^{name}\s+.*\n','',text,flags=re.M)
        if n!=1: raise ValueError('fixed tuning element membership changed')
    text=re.sub(r'(?m)^(\.param[^\n]*)$',lambda m:re.sub(r'\s+(?:RS|CS)=[^\s]+','',m[1]),text)
    vdd=1.8*corner.vdd_scale
    added=R.added_lines(GEOMETRY)+[f'VrcR rctrl 0 {vdd*R_FRACTION:.16g}',f'VrcC cctrl 0 {vdd*C_FRACTION:.16g}']
    text=text.replace('.control','\n'.join(added)+'\n.control',1)
    for filename,vectors in (('trace.txt',F.VECTORS+RC_VECTORS),
                             ('terminals.txt',tuple(f'v({n})' for n in terminals(text)))):
        text,n=re.subn(rf'^wrdata {re.escape(filename)} .+$',lambda _:f'wrdata {filename} '+' '.join(vectors),text,flags=re.M)
        if n!=1: raise ValueError('missing connected primitive output')
    return text


def geometry():
    old=B.geometry(4.)
    subtotal=R.geometry(GEOMETRY)['geometry_subtotal_mm2']+old['geometry_subtotal_mm2']-old['ctle_geometry_subtotal_mm2']
    return {'geometry_subtotal_mm2':subtotal,'routed_layout':False,'full_area_mm2':None,
            'tuning_network':R.geometry(GEOMETRY),'dfe_added_mos_count':old['added_mos_count'],
            'external_clock_and_control_generators':True,'runtime_settling_verified':False}


def control_audit(t,y,nodes,vdd):
    t=np.asarray(t);y=np.asarray(y)
    if (t.ndim!=1 or len(t)<2 or y.shape!=(len(t),6) or not np.isfinite(t).all()
            or not np.isfinite(y).all() or np.any(np.diff(t)<=0) or not np.isfinite(vdd) or vdd<=0):
        raise ValueError('malformed configurable control primitives')
    sources=[np.asarray(nodes[n]) for n in ('s1','s2')]
    if any(a.shape!=t.shape or not np.isfinite(a).all() for a in sources):
        raise ValueError('missing/nonfinite varactor source terminals')
    mask=(t>=(F.WARMUP+2)*UI)&(t<=(F.N_BITS+2)*UI)
    if mask.sum()<2: raise ValueError('missing control energy window')
    errors=[float(max(abs(y[:,i]-vdd*f))) for i,f in enumerate((R_FRACTION,C_FRACTION))]
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


def valid(r):
    c=r.get('tuning_controls',{})
    return E.valid(r) and c.get('control_valid',False) and c.get('varactor_voltage_envelope_pass',False)


def accepted(r): return H.accepted(r) and valid(r)


def calibration_matches(measured,reference):
    return (measured['correct_bits']==reference['correct_bits']==64
            and abs(measured['sampled_eye_height_v']-reference['sampled_eye_height_v'])<=1e-6
            and abs(measured['ctle_plus_dfe_vdd_power_w']-reference['ctle_plus_dfe_vdd_power_w'])<=1e-9
            and abs(measured['aperture']['eye_width_ui']-reference['aperture']['eye_width_ui'])<=.005)


def schedule(evaluate):
    calibration=evaluate(False,1.,2,1,'calibration')
    result={'entry':132,'calibration':calibration,'phases':[],'controls':[],
            'selected_phase_ui':None,'primary_connected_pass':False,'full_receiver_verified':False,
            'code_zero_is_feedback_disabled':False,'runtime_settling_verified':False}
    if not H.accepted(calibration) or not calibration.get('calibration_matches',False): return result
    result['phases']=[{'phase_ui':p,'result':evaluate(True,p,2,1,'phase')} for p in T.PHASES_UI]
    good=[x for x in result['phases'] if accepted(x['result'])]
    if not good: return result
    best=max(good,key=lambda x:(x['result']['sampled_eye_height_v'],-x['phase_ui']))
    phase=best['phase_ui'];result['selected_phase_ui']=phase
    result['controls']=[{'code':code,'sign':sign,'result':evaluate(True,phase,code,sign,'control')}
                        for code,sign in ((0,1),(2,-1))]
    result['primary_connected_pass']=all(valid(x['result']) and
        best['result']['sampled_eye_height_v']-x['result']['sampled_eye_height_v']>1e-6 for x in result['controls'])
    return result
