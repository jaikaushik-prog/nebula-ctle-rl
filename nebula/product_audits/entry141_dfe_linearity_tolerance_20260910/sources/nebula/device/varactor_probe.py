"""Entry 127: exact official-model varactor admittance instrument, not a CTLE."""
import math

import numpy as np

from nebula.common.types import Corner
from nebula.device.pdk_trim import PDK_NGSPICE

MODEL='sky130_fd_pr__cap_var_lvt'
UNIT_W_UM=5.
UNIT_L_UM=.5
CELLS_PER_SIDE=500
FULL_LIB=PDK_NGSPICE/'sky130.lib.spice'
FREQUENCIES_HZ=(1.25e9,2.5e9,3.75e9,5e9)
SOURCE_BIASES_V=(.35,.5,.65,.8,.95)
TUNING_FRACTIONS=tuple(i/40 for i in range(41))
CALIBRATION_CONTROLS_V=(0.,.45,1.8)
CALIBRATION_KINDS=('unit','native4','explicit4','vm4','native500','explicit500')


def validate_bias(source,control):
    if (not all(math.isfinite(x) for x in (source,control))
            or not 0<=source<=1.95 or not 0<=control<=1.95
            or abs(source-control)>2.):
        raise ValueError('invalid varactor terminal bias')


def probe_members():
    return [(source,fraction) for source in SOURCE_BIASES_V for fraction in TUNING_FRACTIONS]


def candidate_geometry():
    return {'unit_w_um':UNIT_W_UM,'unit_l_um':UNIT_L_UM,'cells_per_side':CELLS_PER_SIDE,
            'total_unit_cells':2*CELLS_PER_SIDE,
            'active_geometry_um2':2*CELLS_PER_SIDE*UNIT_W_UM*UNIT_L_UM,
            'routed_area_verified':False,'control_generator_included':False}


def _header(corner):
    if (corner.process not in ('tt','ss','ff','sf','fs')
            or corner.vdd_scale not in (.95,1.,1.05) or corner.temp_c not in (0,27,125)):
        raise ValueError('unregistered varactor corner')
    return ['* Entry 127 isolated official SKY130 varactor probes',
            f'.lib "{FULL_LIB.as_posix()}" {corner.process}',f'.temp {corner.temp_c:g}']


def _cells(name,node,control,kind):
    if kind not in CALIBRATION_KINDS: raise ValueError('unregistered cell multiplier')
    explicit={'explicit4':4,'explicit500':CELLS_PER_SIDE}.get(kind,1)
    multiplier={'native4':4,'native500':CELLS_PER_SIDE}.get(kind,1)
    vm=4 if kind=='vm4' else 1
    return [f'X{name}_{k} {node} {control} 0 {MODEL} w={UNIT_W_UM:g} l={UNIT_L_UM:g} vm={vm} m={multiplier}'
            for k in range(explicit)]


def _finish(lines,op_nodes,currents):
    return '\n'.join(lines+['.control','set noaskquit','set numdgt=15','set wr_singlescale',
        'op','wrdata op.txt '+' '.join(f'v({n})' for n in op_nodes),
        f'ac lin {len(FREQUENCIES_HZ)} {FREQUENCIES_HZ[0]:.16g} {FREQUENCIES_HZ[-1]:.16g}',
        'wrdata admittance.txt '+' '.join(f'i({n})' for n in currents),
        'quit','.endc','.end'])+'\n'


def calibration_layout():
    return [(control,drive,kind) for control in CALIBRATION_CONTROLS_V
            for drive in ('c0','c1') for kind in CALIBRATION_KINDS]


def calibration_op_expected():
    return [value for control,_,_ in calibration_layout() for value in (.5,control)]


def calibration_deck():
    lines=_header(Corner('tt',1,27)); op_nodes=[]; currents=[]
    for i,(control,drive,kind) in enumerate(calibration_layout()):
        validate_bias(.5,control)
        node,cn=f'p{i}',f'c{i}'
        lines += [f'Vp{i} {node} 0 dc 0.5 ac {int(drive=="c0")}',
                  f'Vc{i} {cn} 0 dc {control:.16g} ac {int(drive=="c1")}']
        lines += _cells(f'var{i}',node,cn,kind)
        op_nodes += [node,cn]; currents += [f'Vp{i}',f'Vc{i}']
    return _finish(lines,op_nodes,currents)


def probe_op_expected(corner):
    return [value for source,fraction in probe_members()
            for value in (source,source,1.8*corner.vdd_scale*fraction)]


def probe_deck(corner):
    lines=_header(corner); op_nodes=[]; currents=[]
    for i,(source,fraction) in enumerate(probe_members()):
        control=1.8*corner.vdd_scale*fraction
        validate_bias(source,control)
        p,n,cn=f'p{i}',f'n{i}',f'c{i}'
        lines += [f'Vp{i} {p} 0 dc {source:.16g} ac 0.5',
                  f'Vn{i} {n} 0 dc {source:.16g} ac -0.5',f'Vc{i} {cn} 0 {control:.16g}']
        lines += _cells(f'varp{i}',p,cn,'native500')+_cells(f'varn{i}',n,cn,'native500')
        op_nodes += [p,n,cn]; currents += [f'Vp{i}',f'Vn{i}']
    return _finish(lines,op_nodes,currents)


def parse_ac(raw,vector_count):
    a=np.asarray(raw,dtype=float)
    if (vector_count<1 or a.shape!=(4,1+2*vector_count) or not np.isfinite(a).all()
            or not np.allclose(a[:,0],FREQUENCIES_HZ,rtol=1e-12,atol=1e-3)):
        raise ValueError('missing/malformed complex AC vectors or frequency axis')
    return a[:,1::2]+1j*a[:,2::2]


def check_op(raw,expected):
    a=np.atleast_2d(np.asarray(raw,dtype=float)); expected=np.asarray(expected)
    if (a.shape!=(1,len(expected)+1) or not np.isfinite(a).all()
            or not np.allclose(a[0,1:],expected,rtol=0,atol=1e-10)):
        raise ValueError('missing/malformed OP vectors or incorrect terminal biases')


def metrics(admittance):
    y=np.asarray(admittance,dtype=complex)
    if y.shape!=(4,) or not np.isfinite(y).all() or np.any(y.real<=0) or np.any(y.imag<=0):
        raise ValueError('nonfinite/nonpositive varactor admittance or reversed current polarity')
    return {'parallel_g_s':y.real.tolist(),
            'capacitance_f':(y.imag/(2*np.pi*np.array(FREQUENCIES_HZ))).tolist(),
            'quality_factor':(y.imag/y.real).tolist(),
            'series_resistance_ohm':(1/y).real.tolist()}


def calibration_metrics(admittances):
    a=np.asarray(admittances,dtype=complex)
    if a.shape!=(4,36): raise ValueError('calibration membership mismatch')
    rows=[]; native_ok=True; vm_ok=True
    groups=[(control,drive) for control in CALIBRATION_CONTROLS_V for drive in ('c0','c1')]
    for i,(control,drive) in enumerate(groups):
        group=a[:,6*i:6*(i+1)]
        row={'source_v':.5,'control_v':control,'driven_terminal':drive,'devices':{}}
        for j,kind in enumerate(CALIBRATION_KINDS): row['devices'][kind]=metrics(group[:,j])
        for j,scale in ((1,4),(2,4),(4,CELLS_PER_SIDE),(5,CELLS_PER_SIDE)):
            native_ok &= bool(np.allclose(group[:,j],scale*group[:,0],rtol=1e-9,atol=1e-18))
        vm_ok &= bool(np.allclose(group[:,3],4*group[:,0],rtol=1e-9,atol=1e-18))
        row['vm4_relative_admittance_error']=(abs(group[:,3]/(4*group[:,0])-1)).tolist()
        rows.append(row)
    return {'native_m_equivalent':native_ok,'vm4_equivalent':vm_ok,'rows':rows}


def calibration_currents_metrics(currents):
    a=np.asarray(currents,dtype=complex)
    if a.shape!=(4,72) or not np.isfinite(a).all():
        raise ValueError('calibration terminal-current membership mismatch')
    driven=np.column_stack([-a[:,2*i+(0 if drive=='c0' else 1)]
                            for i,(_,drive,_) in enumerate(calibration_layout())])
    result=calibration_metrics(driven)
    # Both driven and grounded terminal currents must scale: preserve the
    # transfer admittance and both substrate loads, not just one input Y.
    full=all(np.allclose(a[:,12*g+2*j+p],scale*a[:,12*g+p],rtol=1e-9,atol=1e-18)
             for g in range(6) for j,scale in ((1,4),(2,4),(4,CELLS_PER_SIDE),(5,CELLS_PER_SIDE)) for p in (0,1))
    result['all_terminal_currents_scale']=bool(full)
    result['native_m_equivalent'] &= bool(full)
    return result


def probe_metrics(currents,corner):
    a=np.asarray(currents,dtype=complex)
    if a.shape!=(4,410): raise ValueError('probe membership mismatch')
    rows=[]
    for i,(source,fraction) in enumerate(probe_members()):
        control=1.8*corner.vdd_scale*fraction
        validate_bias(source,control)
        yp,yn=-2*a[:,2*i],2*a[:,2*i+1]
        if not np.allclose(yp,yn,rtol=1e-9,atol=1e-18):
            raise ValueError('independent balanced sides disagree')
        rows.append({'source_v':source,'control_fraction':fraction,'control_v':control,
                     **metrics(-.5*(a[:,2*i]-a[:,2*i+1]))})
    monotonic={str(source):all(
        rows[j]['capacitance_f'][f]>rows[j+1]['capacitance_f'][f]
        for j in range(k*41,k*41+40) for f in range(4))
        for k,source in enumerate(SOURCE_BIASES_V)}
    ranges={key:[[min(r[key][f] for r in rows),max(r[key][f] for r in rows)]
                 for f in range(4)] for key in
            ('parallel_g_s','capacitance_f','quality_factor','series_resistance_ohm')}
    return {'rows':rows,'capacitance_strictly_decreases':monotonic,'ranges_by_frequency':ranges,
            'geometry':candidate_geometry(),'configurable_ctle_verified':False}
