"""Entry 128 physical Rs/Cs CTLE instrument; standalone AC, not a receiver."""
from functools import lru_cache
import re

import numpy as np

from nebula.device import dfe_connected as F, dfe_voltage_audit as A, varactor_probe as V
from nebula.device.split_tuning_bank import bank_targets, _res_line, _cap_line
from nebula.device.sky130_runner import interpolate_peak_log_f
from nebula.report.product_scope import area_inventory
from nebula.report.schematic import params_of

GEOMETRIES=tuple((n,c) for n in (100,250,500) for c in (0.,1.5e-12,2.5e-12))
R_FRACTIONS=(0.,.4,.45,.5,.55,.6,.7,.85,1.)
C_FRACTIONS=(0.,.05,.1,.15,.2,.3,.4,.6,1.)
FREQUENCIES_HZ=np.geomspace(1e6,1e11,251)
PORTS=('inx','iny','cm','vdd','outp','outn','rctrl','cctrl')


def biases():
    return [(r,c) for r in R_FRACTIONS for c in C_FRACTIONS]


def resistor_targets():
    b=bank_targets(); hi,lo=b.rs_values_ohm[-1],b.rs_values_ohm[0]
    ron=b.r_nominal_ron_ohm[0]
    return {'rmax_ohm':hi,'nominal_low_ohm':lo,'measured_ron_ohm':ron,
            'branch_poly_ohm':1/(1/lo-1/hi)-ron}


def added_lines(geometry):
    if geometry not in GEOMETRIES: raise ValueError('unregistered physical RC geometry')
    n,c=geometry; r=resistor_targets()
    lines=[_res_line('Xrc_rmax','s1','s2',r['rmax_ohm']),
           _res_line('Xrc_branch','s1','rc_mid',r['branch_poly_ohm']),
           'Xrc_switch rc_mid rc_gate s2 0 sky130_fd_pr__nfet_01v8 W=80 L=0.15 nf=2',
           _res_line('Xrc_rfeed','rctrl','rc_gate',1e4),
           _res_line('Xrc_cfeed','cctrl','rc_ct',1e4),
           _cap_line('Xrc_rbypass','rc_gate','0',1e-12),
           _cap_line('Xrc_cbypass','rc_ct','0',1e-11)]
    for side in ('s1','s2'):
        lines.append(f'Xrc_var_{side} {side} rc_ct 0 {V.MODEL} w={V.UNIT_W_UM:g} l={V.UNIT_L_UM:g} vm=1 m={n}')
    if c: lines.append(_cap_line('Xrc_fixedc','s1','s2',c))
    return lines


def circuit_body(geometry,source=None):
    if geometry is not None and geometry not in GEOMETRIES:
        raise ValueError('unregistered physical RC geometry')
    source=F.source_deck() if source is None else source
    raw=source.split('.control')[0].splitlines()
    names=[s.split()[0].lower() for s in raw if s.strip()]
    if any(names.count(k)!=1 for k in ('xrs','xcs','vdd','vcm','vid','einp','einn')):
        raise ValueError('baseline physical source membership changed')
    lines=[]
    for line in raw:
        line=line.strip()
        if not line or line.startswith('*'): continue
        head=line.split()[0].lower()
        if head in ('.lib','.temp','vdd','vcm','vid','einp','einn'): continue
        if geometry is not None:
            if head in ('xrs','xcs'): continue
            if head=='.param': line=re.sub(r'\s+(?:RS|CS)=[^\s]+','',line)
        lines.append(line)
    if geometry is not None: lines+=added_lines(geometry)
    return '\n'.join(lines)


@lru_cache(maxsize=10)
def geometry(candidate):
    original=area_inventory(F.source_deck())
    removed=sum(row['geometry_um2'] for row in original['components'] if row['name'] in ('xrs','xcs'))
    # The report inventory requires a full fixed-Rs/Cs deck and does not know
    # varactors. Parse exact drawn dimensions here; never supply fake params.
    components=[]
    for line in added_lines(candidate):
        attrs={k.lower():float(v) for k,v in re.findall(r'\b(\w+)=([-+0-9.eE]+)',line)}
        area=attrs['w']*attrs['l']*attrs.get('m',1.)
        if not np.isfinite(area) or area<=0: raise ValueError('invalid added geometry')
        components.append({'name':line.split()[0],'netlist_line':line,'geometry_um2':area,
                           'varactor':V.MODEL in line})
    varactor_area=sum(x['geometry_um2'] for x in components if x['varactor'])
    nonvar=sum(x['geometry_um2'] for x in components if not x['varactor'])
    subtotal=original['geometry_subtotal_mm2']+(nonvar+varactor_area-removed)*1e-6
    return {'geometry_subtotal_mm2':subtotal,'varactor_active_um2':varactor_area,
            'removed_fixed_rs_cs_um2':removed,'added_nonvaractor_um2':nonvar,'added_components':components,
            'routed_layout':False,'full_area_mm2':None,'control_generator_included':False}


def members(candidate):
    return [(candidate,r,c) for r,c in biases()]+[(None,0.,0.)] if candidate is not None else [(None,0.,0.)]


def node_ref(index,node):
    return f'{node}{index}' if node in PORTS else f'xcase{index}.{node}'


@lru_cache(maxsize=10)
def nodes_for(candidate):
    nodes=set(PORTS)
    for line in F.all_mos(circuit_body(candidate)):
        nodes.update(line.split()[1:5])
    if candidate is not None: nodes.add('rc_ct')
    nodes.discard('0')
    return tuple(sorted(nodes))


def op_layout(candidate,count=None):
    ms=members(candidate)
    if count is not None and count!=len(ms): raise ValueError('OP member count mismatch')
    return [(i,key,vector) for i,(g,_,_) in enumerate(ms)
            for key,vector in [('supply_current_a',f'i(vsupply{i})'),
                               *((n,f'v({node_ref(i,n)})') for n in nodes_for(g))]]


def screen_deck(candidate):
    if candidate is not None and candidate not in GEOMETRIES: raise ValueError('unregistered geometry')
    p=params_of(F.source_deck()); vcm=p['VCM']
    lines=['* Entry 128 physical configurable RC screening, standalone CTLE',
           f'.lib "{V.FULL_LIB.as_posix()}" tt','.temp 27',
           '.subckt rc_fixed '+' '.join(PORTS),circuit_body(None),'.ends rc_fixed']
    if candidate is not None:
        lines+=['.subckt rc_tuned '+' '.join(PORTS),circuit_body(candidate),'.ends rc_tuned']
    ms=members(candidate)
    for i,(g,r,c) in enumerate(ms):
        lines += [f'Vsupply{i} vdd{i} 0 1.8',f'Vcm{i} cm{i} 0 {vcm:.16g}',
                  f'Vid{i} vid{i} 0 dc 0 ac 1',f'Einp{i} inx{i} cm{i} vid{i} 0 0.5',
                  f'Einn{i} iny{i} cm{i} vid{i} 0 -0.5',
                  f'Vr{i} rctrl{i} 0 {1.8*r:.16g}',f'Vc{i} cctrl{i} 0 {1.8*c:.16g}',
                  f'Xcase{i} '+' '.join(f'{n}{i}' for n in PORTS)+(' rc_fixed' if g is None else ' rc_tuned')]
    currents=[f'v({n}{i})' for i in range(len(ms)) for n in ('outp','outn','vid')]
    lines += ['.control','set noaskquit','set numdgt=15','set wr_singlescale','op',
              'wrdata op.txt '+' '.join(v for _,_,v in op_layout(candidate)),
              'ac dec 50 1meg 100g','wrdata ac.txt '+' '.join(currents),
              'quit','.endc','.end']
    return '\n'.join(lines)+'\n'


def parse_ac(raw,count):
    a=np.asarray(raw,dtype=float)
    if (count<1 or a.shape!=(251,1+6*count) or not np.isfinite(a).all()
            or not np.allclose(a[:,0],FREQUENCIES_HZ,rtol=1e-12,atol=1e-3)):
        raise ValueError('malformed complex CTLE vectors or frequency axis')
    y=a[:,1::2]+1j*a[:,2::2]
    if not np.allclose(y[:,2::3],1.,rtol=0,atol=1e-12):
        raise ValueError('differential input primitive differs from 1 V AC')
    return (y[:,1::3]-y[:,0::3])/y[:,2::3]


def response_metrics(h):
    h=np.asarray(h,dtype=complex)
    if h.shape!=(251,) or not np.isfinite(h).all() or np.any(abs(h)<=0):
        raise ValueError('missing/nonfinite/zero CTLE response')
    db=20*np.log10(abs(h)); peak=interpolate_peak_log_f(FREQUENCIES_HZ,db)
    result={'dc_gain_db':float(db[0]),'interior_peak':peak.ok,'ac_shape_pass':False,
            'boost_db':None,'peak_frequency_hz':None}
    if not peak.ok: return {**result,'peak_failure':peak.reason}
    result.update(boost_db=float(peak.g_db-db[0]),peak_frequency_hz=float(peak.f_hz))
    result['ac_shape_pass']=3<=result['boost_db']<=12 and 1.25e9<=result['peak_frequency_hz']<=2.5e9
    return result


def baseline_matches(h,reference_db):
    ref=np.asarray(reference_db)
    return bool(ref.shape==(251,) and np.isfinite(ref).all()
                and np.allclose(20*np.log10(abs(h)),ref,rtol=0,atol=1e-6))


def parse_op(raw,candidate,count=None):
    layout=op_layout(candidate,count); a=np.atleast_2d(np.asarray(raw,dtype=float))
    if a.shape!=(1,len(layout)+1) or not np.isfinite(a).all():
        raise ValueError('malformed/missing/nonfinite DC primitive vectors')
    values=[{} for _ in members(candidate)]
    for (i,key,_),value in zip(layout,a[0,1:]): values[i][key]=float(value)
    result=[]
    for (g,r,c),row in zip(members(candidate),values):
        power=-1.8*row.pop('supply_current_a')
        if power<=0: raise ValueError('nonpositive supplied power or reversed supply polarity')
        if any(abs(row[n]-v)>1e-10 for n,v in (('vdd',1.8),('rctrl',1.8*r),('cctrl',1.8*c))):
            raise ValueError('incorrect external DC supply/control bias')
        if g is not None:
            for n in ('s1','s2'): V.validate_bias(row[n],row['rc_ct'])
        mos=F.all_mos(circuit_body(g))
        signed=A.audit(mos,{n:np.array([v]) for n,v in row.items()})
        body_ok=all(d['vbs']['below_samples']==0 and d['vbs']['above_samples']==0 for d in signed['devices'])
        # Preserve exact signed diagnostics; this envelope is not model-domain signoff.
        envelope=body_ok and signed['max_abs_vds_vgs_v']<=1.95
        result.append({'vdd_power_w':power,'dc_nodes_v':row,'signed_mos_audit':signed,
                       'magnitude_body_envelope_ok':bool(envelope),
                       'electrical_pass':bool(envelope and power<.015)})
    return result
