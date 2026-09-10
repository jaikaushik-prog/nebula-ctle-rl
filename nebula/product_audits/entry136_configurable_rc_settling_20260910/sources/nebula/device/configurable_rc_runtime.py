"""Entry 134: continuous voltage control of the unchanged standalone CTLE."""
import numpy as np

from nebula.device import configurable_rc as R, configurable_rc_precision as P
from nebula.device import dfe_connected as D, dfe_voltage_audit as V, varactor_probe as B
from nebula.report.schematic import params_of

GEOMETRY=(500,0.)
SETPOINTS=((.7,.165),(.79,.135),(.73,.15))
FREQUENCIES=np.array([1e8,1.9e9])
STEP=5e-12
WINDOW=20e-9
CHANGES=np.array([100.,700.,1300.])*1e-9
EDGE=10e-9
STOP=1900e-9
NODES=R.nodes_for(GEOMETRY)
VECTORS=('v(vid)','v(outp)','v(outn)','v(vdd)','i(vdd)',
         'v(rctrl)','v(cctrl)','v(rc_gate)','v(rc_ct)','i(vr)','i(vc)',
         'i(vcm)','i(vlo)','i(vhi)')


def member(kind,index):
    if kind not in ('static','runtime') or index not in range(3) or (kind=='runtime' and index!=0):
        raise ValueError('unregistered runtime experiment member')


def control_knots():
    times=[0.];indices=[0]
    for k,change in enumerate(CHANGES):
        times.extend([float(change),float(change+EDGE)]);indices.extend([k,(k+1)%3])
    times.append(STOP);indices.append(0)
    return np.array(times),np.array([SETPOINTS[i] for i in indices])*1.8


def controls(t,kind,index):
    member(kind,index);t=np.asarray(t)
    if kind=='static': return tuple(np.full(t.shape,1.8*v) for v in SETPOINTS[index])
    times,values=control_knots()
    return tuple(np.interp(t,times,values[:,i]) for i in range(2))


def stimulus(t):
    return sum(.001*np.sin(2*np.pi*f*np.asarray(t)) for f in FREQUENCIES)


def deck(kind,index):
    member(kind,index);r,c=SETPOINTS[index];vcm=params_of(D.source_deck())['VCM']
    lines=['* Entry 134 continuous physical RC control, standalone CTLE',
           f'.lib "{B.FULL_LIB.as_posix()}" tt','.temp 27',P.OPTIONS,
           R.circuit_body(GEOMETRY),'Vdd vdd 0 1.8',f'Vcm cm 0 {vcm:.16g}',
           'Vlo mid 0 dc 0 ac 1 SIN(0 0.001 100meg)',
           'Vhi vid mid dc 0 ac 0 SIN(0 0.001 1.9g)',
           'Einp inx cm vid 0 0.5','Einn iny cm vid 0 -0.5']
    if kind=='static': lines += [f'Vr rctrl 0 {1.8*r:.16g}',f'Vc cctrl 0 {1.8*c:.16g}']
    else:
        times,values=control_knots()
        for j,(name,node) in enumerate((('Vr','rctrl'),('Vc','cctrl'))):
            lines.append(f'{name} {node} 0 PWL('+ ' '.join(f'{t:.16g} {v:.16g}' for t,v in zip(times,values[:,j]))+')')
    lines+=['.control','set noaskquit','set numdgt=15','set wr_singlescale']
    if kind=='static':
        lines+=['op','wrdata op.txt i(vdd) '+' '.join(f'v({n})' for n in NODES),
                'ac dec 50 1meg 100g','wrdata ac.txt v(outp) v(outn) v(vid)',
                'ac lin 2 100meg 1.9g','wrdata tones.txt v(outp) v(outn) v(vid)']
    stop=100e-9 if kind=='static' else STOP
    lines += [f'tran 5p {stop:.16g} 0 5p','wrdata trace.txt '+' '.join(VECTORS),
              'wrdata terminals.txt '+' '.join(f'v({n})' for n in NODES),
              'quit','.endc','.end']
    return '\n'.join(lines)+'\n'


def validate_series(t,*ys):
    t=np.asarray(t)
    if t.ndim!=1 or len(t)<2 or not np.isfinite(t).all() or np.any(np.diff(t)<=0):
        raise ValueError('malformed runtime time axis')
    if any(np.shape(y)!=(len(t),) or not np.isfinite(y).all() for y in ys):
        raise ValueError('malformed/nonfinite runtime primitive')
    return t


def fit_window(t,inp,out,start):
    t=validate_series(t,inp,out)
    if not np.isfinite(start) or t[0]>start+1e-18 or t[-1]<start+WINDOW-1e-18:
        raise ValueError('incomplete tone window')
    grid=start+np.arange(round(WINDOW/STEP))*STEP
    x=np.column_stack([np.ones(len(grid)),*(a for f in FREQUENCIES for a in
                        (np.sin(2*np.pi*f*grid),np.cos(2*np.pi*f*grid)))])
    values=np.column_stack((np.interp(grid,t,inp),np.interp(grid,t,out)))
    coeff,_,rank,singular=np.linalg.lstsq(x,values,rcond=None)
    if rank!=5 or singular[0]/singular[-1]>100: raise ValueError('ill-conditioned tone fit')
    phasors=coeff[1::2]+1j*coeff[2::2]
    if np.any(abs(phasors[:,0])<1e-6) or np.any(abs(phasors[:,0]-.001)>2e-6):
        raise ValueError('missing/incorrect measured input tone')
    h=phasors[:,1]/phasors[:,0]
    ac=x[:,1:]@coeff[1:,1];rms=float(np.sqrt(np.mean(ac**2)))
    if rms<1e-9: raise ValueError('missing output tone')
    return {'transfer_real':h.real.tolist(),'transfer_imag':h.imag.tolist(),
            'residual_fraction':float(np.sqrt(np.mean((values[:,1]-x@coeff[:,1])**2))/rms),
            'output_dc_v':float(coeff[0,1])}


def window_pass(row,reference):
    try:
        h=np.array(row['transfer_real'])+1j*np.array(row['transfer_imag']);ref=np.asarray(reference)
        metrics=np.array([row['residual_fraction'],row['vdd_power_w'],row['control_mean_error_v']])
        return bool(h.shape==ref.shape==(2,) and np.isfinite(h).all() and np.isfinite(ref).all()
                    and np.all(abs(ref)>1e-9) and np.isfinite(metrics).all()
                    and np.all(abs(h-ref)<=.02*abs(ref)) and 0<=metrics[0]<=.05
                    and 0<metrics[1]<.015 and 0<=metrics[2]<=.001)
    except (KeyError,ValueError,TypeError): return False


def settling_bound(rows,end):
    if not rows or not rows[-1]['pass']: return None
    i=len(rows)-1
    while i>0 and rows[i-1]['pass']: i-=1
    return float(rows[i]['start_s']-end)


def tone_reference(raw):
    a=np.asarray(raw)
    if a.shape!=(2,7) or not np.isfinite(a).all() or not np.allclose(a[:,0],FREQUENCIES,rtol=1e-12,atol=1e-3):
        raise ValueError('malformed exact-frequency AC primitives')
    z=a[:,1::2]+1j*a[:,2::2]
    if not np.allclose(z[:,2],1.,rtol=0,atol=1e-12): raise ValueError('incorrect AC input')
    return (z[:,1]-z[:,0])/z[:,2]


def reference_match(op,ac,index,prior):
    a=np.atleast_2d(op)
    if a.shape!=(1,len(NODES)+2) or not np.isfinite(a).all(): raise ValueError('malformed runtime OP')
    nodes=dict(zip(NODES,map(float,a[0,2:])));power=float(-1.8*a[0,1])
    old=prior['dc'];h=R.parse_ac(ac,1)[:,0];ref=np.asarray(prior['ac'])
    if set(nodes)!=set(old['dc_nodes_v']) or ref.shape!=(251,): raise ValueError('reference membership differs')
    if not np.isfinite(ref).all() or np.any(abs(ref)<1e-12) or np.any(abs(h)<1e-12):
        raise ValueError('invalid full-sweep reference')
    drift=max(abs(nodes[k]-old['dc_nodes_v'][k]) for k in nodes)
    mag=float(max(abs(20*np.log10(abs(h/ref)))));phase=float(max(abs(np.angle(h/ref))))
    r,c=SETPOINTS[index]
    bias_ok=all(abs(nodes[n]-v)<=1e-9 for n,v in [('vdd',1.8),('rctrl',1.8*r),('cctrl',1.8*c)])
    return {'reference_matches':bool(bias_ok and drift<=1e-9 and abs(power-old['vdd_power_w'])<=1e-9
                                    and mag<=1e-6 and phase<=1e-6),
            'reference_max_dc_drift_v':drift,'reference_max_ac_magnitude_error_db':mag,
            'reference_max_ac_phase_error_rad':phase,'op_nodes_v':nodes,'op_vdd_power_w':power}


def analyze(t,y,nodes,kind,index,references):
    member(kind,index);t=validate_series(t);y=np.asarray(y)
    stop=100e-9 if kind=='static' else STOP
    if y.shape!=(len(t),len(VECTORS)) or not np.isfinite(y).all(): raise ValueError('malformed runtime trace')
    if abs(t[0])>1e-18 or abs(t[-1]-stop)>1e-15 or max(np.diff(t))>5.01e-12:
        raise ValueError('incomplete/undersampled runtime trace')
    if set(nodes)!=set(NODES): raise ValueError('terminal membership mismatch')
    validate_series(t,*nodes.values())
    for n,i in [('outp',1),('outn',2),('vdd',3),('rctrl',5),('cctrl',6),('rc_gate',7),('rc_ct',8)]:
        if not np.array_equal(nodes[n],y[:,i]): raise ValueError('main/terminal primitive differs')
    expected=controls(t,kind,index)
    errors=[float(max(abs(y[:,0]-stimulus(t)))),float(max(abs(y[:,3]-1.8))),
            *(float(max(abs(y[:,i+5]-v))) for i,v in enumerate(expected))]
    if max(errors)>1e-9: raise ValueError('incorrect runtime stimulus/supply/control')
    audit=V.audit(D.all_mos(R.circuit_body(GEOMETRY)),nodes)
    body=all(d['vbs']['below_samples']==d['vbs']['above_samples']==0 for d in audit['devices'])
    envelope=bool(body and audit['max_abs_vds_vgs_v']<=1.95)
    var_ok=all(np.min(nodes[n])>=0 and np.max(nodes[n])<=1.95
               and max(abs(nodes[n]-nodes['rc_ct']))<=2 for n in ('s1','s2'))
    var_ok=bool(var_ok and np.min(nodes['rc_ct'])>=0 and np.max(nodes['rc_ct'])<=1.95)
    def window(start,target):
        row={'start_s':float(start),**fit_window(t,y[:,0],y[:,2]-y[:,1],start)}
        grid=start+np.arange(round(WINDOW/STEP))*STEP
        row['vdd_power_w']=float(np.mean(np.interp(grid,t,-y[:,3]*y[:,4])))
        ref=references[target]
        row['control_mean_error_v']=float(max(abs(np.mean(np.interp(grid,t,y[:,i]))-ref['op_nodes_v'][n])
                                                for i,n in ((7,'rc_gate'),(8,'rc_ct'))))
        h=np.array(ref['tone_real'])+1j*np.array(ref['tone_imag'])
        row['pass']=window_pass(row,h)
        return row
    initial=[window(x*1e-9,index) for x in (60.,80.)]
    result={'instrument_ok':True,'stimulus_max_errors_v':errors,'whole_mos_signed_audit':audit,
            'whole_magnitude_body_envelope_pass':envelope,'varactor_envelope_pass':var_ok,
            'initial_windows':initial,'transitions':[],'runtime_pass':False,
            'connected_dfe_runtime_verified':False,'full_receiver_verified':False}
    valid=envelope and var_ok and all(row['pass'] for row in initial)
    if kind=='static': result['static_transient_pass']=bool(valid);return result
    for k,change in enumerate(CHANGES):
        end=float(change+EDGE);next_change=float(CHANGES[k+1]) if k<2 else STOP
        starts=end+np.arange(round((next_change-end-WINDOW)/10e-9)+1)*10e-9
        rows=[window(float(s),(k+1)%3) for s in starts]
        bound=settling_bound(rows,end)
        grid=np.arange(round(change/STEP),round(next_change/STEP)+1)*STEP
        def energy(power): return float(np.trapezoid(np.interp(grid,t,power),grid))
        rc=-(y[:,5]*y[:,9]+y[:,6]*y[:,10])
        row={'from_index':k,'to_index':(k+1)%3,'ramp_start_s':float(change),'ramp_end_s':end,
             'windows':rows,'settling_bound_s':bound,'pass':bool(bound is not None and 0<=bound<=500e-9),
             'vdd_energy_j':energy(-y[:,3]*y[:,4]),'external_rc_net_energy_j':energy(rc),
             'external_rc_positive_energy_j':energy(np.maximum(-y[:,5]*y[:,9],0)+np.maximum(-y[:,6]*y[:,10],0))}
        result['transitions'].append(row)
    result['runtime_pass']=bool(valid and all(row['pass'] for row in result['transitions']))
    return result


def schedule(evaluate):
    result={'entry':134,'static':[],'runtime':None,'runtime_demonstration_pass':False,
            'distinct_settings_verified':False,'connected_dfe_runtime_verified':False,'full_receiver_verified':False}
    for i in range(3):
        row=evaluate('static',i);result['static'].append(row)
        if i==0 and not row.get('baseline_pass',False): return result
    if not all(r.get('baseline_pass',False) for r in result['static']): return result
    gains=[r.get('low_frequency_gain',float('nan')) for r in result['static']]
    result['distinct_settings_verified']=bool(all(np.isfinite(g) and g>0 for g in gains)
        and all(abs(a-b)>=.1*max(a,b) for i,a in enumerate(gains) for b in gains[i+1:]))
    if not result['distinct_settings_verified']: return result
    result['runtime']=evaluate('runtime',0)
    result['runtime_demonstration_pass']=bool(result['runtime'].get('runtime_pass',False))
    return result
