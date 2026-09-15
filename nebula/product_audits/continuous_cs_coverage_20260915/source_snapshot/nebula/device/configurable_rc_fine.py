"""Entry 131: denser external-control mapping on two measured physical circuits."""
import numpy as np

from nebula.device import configurable_rc as R, configurable_rc_serial as S
from nebula.device import configurable_rc_precision as Q
from nebula.device import dfe_connected as D, dfe_voltage_audit as A, varactor_probe as V

GEOMETRIES=((250,0.),(500,0.))
R_FRACTIONS=tuple(round(.65+.01*i,3) for i in range(21))
C_FRACTIONS=tuple(round(.015*i,3) for i in range(21))
TARGETS=tuple((b,f*1e9) for b in (3.,6.,9.) for f in (1.5,1.9,2.25))


def biases(): return [(r,c) for r in R_FRACTIONS for c in C_FRACTIONS]


def deck(g):
    if g not in GEOMETRIES: raise ValueError('unregistered fine geometry')
    lines=[Q.deck(g).split('.control')[0].rstrip(),'.control','set noaskquit','set numdgt=15','set wr_singlescale']
    op=' '.join(x[2] for x in S.layout(g))
    ac=' '.join(f'v({n}{i})' for i in (0,81) for n in ('outp','outn','vid'))
    for i,(r,c) in enumerate(biases()):
        lines += [f'alter Vr0 {1.8*r:.16g}',f'alter Vc0 {1.8*c:.16g}',
                  'op',f'wrdata op_{i:03d}.txt {op}','ac dec 50 1meg 100g',f'wrdata ac_{i:03d}.txt {ac}']
    return '\n'.join(lines+['quit','.endc','.end'])+'\n'


def primitives(raw,g):
    labels=S.layout(g);a=np.atleast_2d(np.asarray(raw,dtype=float))
    if a.shape!=(1,1+len(labels)) or not np.isfinite(a).all():
        raise ValueError('malformed/nonfinite fine DC primitives')
    rows=[{},{}]
    for (i,key,_),value in zip(labels,a[0,1:]): rows[0 if i==0 else 1][key]=float(value)
    return rows


def check_fixed(first,current):
    if set(first)!=set(current) or any(not np.isfinite(current[k]) or abs(first[k]-current[k])>1e-9 for k in first):
        raise ValueError('fixed baseline DC changed across fine controls')


def parse_op(raw,g,r,c):
    if g not in GEOMETRIES or r not in R_FRACTIONS or c not in C_FRACTIONS:
        raise ValueError('unregistered fine geometry/control')
    result=[]
    for geom,rf,cf,row in zip((g,None),(r,0.),(c,0.),primitives(raw,g)):
        power=-1.8*row.pop('supply_current_a')
        if power<=0: raise ValueError('nonpositive supplied power')
        if any(abs(row[n]-v)>1e-10 for n,v in (('vdd',1.8),('rctrl',1.8*rf),('cctrl',1.8*cf))):
            raise ValueError('incorrect external DC supply/control bias')
        if geom is not None:
            for n in ('s1','s2'): V.validate_bias(row[n],row['rc_ct'])
        audit=A.audit(D.all_mos(R.circuit_body(geom)),{n:np.array([v]) for n,v in row.items()})
        body=all(d['vbs']['below_samples']==0 and d['vbs']['above_samples']==0 for d in audit['devices'])
        envelope=body and audit['max_abs_vds_vgs_v']<=1.95
        result.append({'vdd_power_w':power,'dc_nodes_v':row,'signed_mos_audit':audit,
                       'magnitude_body_envelope_ok':bool(envelope),'electrical_pass':bool(envelope and power<.015)})
    return result


def select_target(rows,boost,frequency):
    candidates=[]
    for row in rows:
        if not row['ac_spec_pass']: continue
        db=abs(row['boost_db']-boost);df=abs(row['peak_frequency_hz']-frequency)
        if db<=.5 and df<=1e8:
            error=(db/.5)**2+(df/1e8)**2
            candidates.append((error,row['r_fraction'],row['c_fraction'],row))
    result={'target_boost_db':boost,'target_frequency_hz':frequency,'found':bool(candidates)}
    if candidates:
        error,r,c,row=min(candidates,key=lambda x:x[:3])
        result.update(error=error,r_fraction=r,c_fraction=c,boost_db=row['boost_db'],peak_frequency_hz=row['peak_frequency_hz'])
    return result


def schedule(evaluate):
    result={'entry':131,'candidates':[],'characterization_complete':False,
            'selected_geometry':None,'connected_dfe_verified':False,'full_target_rectangle_verified':False}
    for i,g in enumerate(GEOMETRIES):
        row=evaluate(g);result['candidates'].append({'geometry':g,'result':row})
        if i==0 and (not row.get('instrument_ok') or not row.get('baseline_matches')): return result
    result['characterization_complete']=all(x['result'].get('instrument_ok') and x['result'].get('baseline_matches') for x in result['candidates'])
    ranking=[]
    for x in result['candidates']:
        if not x['result'].get('instrument_ok') or not x['result'].get('baseline_matches'): continue
        targets=[select_target(x['result']['rows'],b,f) for b,f in TARGETS]
        x['targets']=targets;x['target_count']=sum(t['found'] for t in targets)
        if not any(t['found'] and t['target_boost_db']==9. and t['target_frequency_hz']==1.9e9 for t in targets): continue
        error=sum(t['error'] for t in targets if t['found'])/x['target_count']
        ranking.append((-x['target_count'],error,R.geometry(x['geometry'])['geometry_subtotal_mm2'],x['geometry']))
    if result['characterization_complete'] and ranking: result['selected_geometry']=min(ranking)[-1]
    return result
