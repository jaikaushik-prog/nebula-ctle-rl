"""Entry 136: longer observation on unchanged hardware, unchanged latency gate."""
import re

import numpy as np

from nebula.device import configurable_rc_runtime as U, configurable_rc_runtime_recovery as V
from nebula.device import configurable_rc as R, dfe_connected as D, dfe_voltage_audit as A

CHANGES=np.array([100.,1100.,2100.])*1e-9
STOP=3100e-9


def control_knots():
    times=[0.];indices=[0]
    for k,change in enumerate(CHANGES):
        times.extend([float(change),float(change+U.EDGE)]);indices.extend([k,(k+1)%3])
    times.append(STOP);indices.append(0)
    return np.array(times),np.array([U.SETPOINTS[i] for i in indices])*1.8


def controls(t):
    times,values=control_knots()
    return tuple(np.interp(t,times,values[:,i]) for i in range(2))


def deck():
    text=V.deck('runtime',0);times,values=control_knots()
    for j,(name,node) in enumerate((('Vr','rctrl'),('Vc','cctrl'))):
        line=f'{name} {node} 0 PWL('+' '.join(f'{t:.16g} {v:.16g}' for t,v in zip(times,values[:,j]))+')'
        text,n=re.subn(rf'(?m)^{name} {node} .*$',lambda _:line,text)
        if n!=1: raise ValueError('runtime control source membership changed')
    text,n=re.subn(r'(?m)^tran 5p .*$',f'tran 5p {STOP:.16g} 0 5p',text)
    if n!=1: raise ValueError('runtime transient membership changed')
    return text


def conclusions(valid,rows):
    bounds=[r.get('settling_bound_s') for r in rows]
    settled=bool(valid and len(rows)==3 and all(b is not None and np.isfinite(b) and 0<=b<=970e-9 for b in bounds))
    return {'all_transitions_settled':settled,
            'passes_original_500ns_gate':bool(settled and all(b<=500e-9 for b in bounds))}


def analyze(t,y,nodes,references):
    t=U.validate_series(t);y=np.asarray(y)
    if y.shape!=(len(t),len(U.VECTORS)) or not np.isfinite(y).all(): raise ValueError('malformed extended trace')
    if abs(t[0])>1e-18 or abs(t[-1]-STOP)>1e-15 or max(np.diff(t))>5.01e-12:
        raise ValueError('incomplete/undersampled extended trace')
    if set(nodes)!=set(U.NODES): raise ValueError('terminal membership mismatch')
    U.validate_series(t,*nodes.values())
    for n,i in [('outp',1),('outn',2),('vdd',3),('rctrl',5),('cctrl',6),('rc_gate',7),('rc_ct',8)]:
        if not np.array_equal(nodes[n],y[:,i]): raise ValueError('main/terminal primitive differs')
    errors=[float(max(abs(y[:,0]-U.stimulus(t)))),float(max(abs(y[:,3]-1.8))),
            *(float(max(abs(y[:,i+5]-v))) for i,v in enumerate(controls(t)))]
    if max(errors)>1e-9: raise ValueError('incorrect extended stimulus/supply/control')
    audit=A.audit(D.all_mos(R.circuit_body(U.GEOMETRY)),nodes)
    body=all(d['vbs']['below_samples']==d['vbs']['above_samples']==0 for d in audit['devices'])
    envelope=bool(body and audit['max_abs_vds_vgs_v']<=1.95)
    var_ok=all(np.min(nodes[n])>=0 and np.max(nodes[n])<=1.95
               and max(abs(nodes[n]-nodes['rc_ct']))<=2 for n in ('s1','s2'))
    var_ok=bool(var_ok and np.min(nodes['rc_ct'])>=0 and np.max(nodes['rc_ct'])<=1.95)
    def window(start,target):
        row={'start_s':float(start),**U.fit_window(t,y[:,0],y[:,2]-y[:,1],start)}
        grid=start+np.arange(round(U.WINDOW/U.STEP))*U.STEP;ref=references[target]
        row['vdd_power_w']=float(np.mean(np.interp(grid,t,-y[:,3]*y[:,4])))
        row['control_mean_error_v']=float(max(abs(np.mean(np.interp(grid,t,y[:,i]))-ref['op_nodes_v'][n])
                                                for i,n in ((7,'rc_gate'),(8,'rc_ct'))))
        h=np.array(ref['tone_real'])+1j*np.array(ref['tone_imag'])
        row['pass']=U.window_pass(row,h)
        return row
    initial=[window(x*1e-9,0) for x in (60.,80.)]
    result={'instrument_ok':True,'stimulus_max_errors_v':errors,'whole_mos_signed_audit':audit,
            'whole_magnitude_body_envelope_pass':envelope,'varactor_envelope_pass':var_ok,
            'initial_windows':initial,'transitions':[],
            'connected_dfe_runtime_verified':False,'full_receiver_verified':False}
    valid=envelope and var_ok and all(row['pass'] for row in initial)
    for k,change in enumerate(CHANGES):
        end=float(change+U.EDGE);next_change=float(CHANGES[k+1]) if k<2 else STOP
        starts=end+np.arange(round((next_change-end-U.WINDOW)/10e-9)+1)*10e-9
        rows=[window(float(s),(k+1)%3) for s in starts];bound=U.settling_bound(rows,end)
        grid=np.arange(round(change/U.STEP),round(next_change/U.STEP)+1)*U.STEP
        def energy(power): return float(np.trapezoid(np.interp(grid,t,power),grid))
        rc=-(y[:,5]*y[:,9]+y[:,6]*y[:,10])
        result['transitions'].append({'from_index':k,'to_index':(k+1)%3,'ramp_start_s':float(change),
            'ramp_end_s':end,'windows':rows,'settling_bound_s':bound,
            'passes_original_500ns_gate':bool(bound is not None and 0<=bound<=500e-9),
            'vdd_energy_j':energy(-y[:,3]*y[:,4]),'external_rc_net_energy_j':energy(rc),
            'external_rc_positive_energy_j':energy(np.maximum(-y[:,5]*y[:,9],0)+np.maximum(-y[:,6]*y[:,10],0))})
    result.update(conclusions(valid,result['transitions']))
    return result
