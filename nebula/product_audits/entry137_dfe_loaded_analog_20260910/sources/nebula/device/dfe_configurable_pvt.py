"""Entry 133 fixed-setting configurable-DUT electrical PVT verification."""
from nebula.common.types import Corner,all_corners
from nebula.link.config import LinkConfig
from nebula.device import dfe_connected as F,dfe_tail_bleed as B,dfe_timing as T
from nebula.device import dfe_voltage_audit as V,dfe_configurable as C
from nebula.experiments import evidence_archive as A,exp_dfe_connected as D

SCREENS=(Corner('tt',1.,27),Corner('ss',.95,125),Corner('ff',1.05,0),
         Corner('sf',.95,0),Corner('fs',.95,125))
PHASE=1.


def extract(folder,text,corner,reference):
    cfg=LinkConfig(channel_loss_db_at_nyquist=7.5);bits=F.pattern(cfg);vdd=1.8*corner.vdd_scale
    t,y=T.read_table(A.trace_path(folder/'trace.txt'),len(F.VECTORS)+len(C.RC_VECTORS))
    main=y[:,:len(F.VECTORS)]
    r=F.analyze(t,main,bits,cfg,PHASE,vdd,code=2)
    names=C.terminals(text)
    _,ny=T.read_table(A.trace_path(folder/'terminals.txt'),len(names),expected_time=t)
    nodes=dict(zip(names,ny.T));mos=F.all_mos(text)
    whole=V.audit(mos,nodes);new=V.audit(F.extra_mos(1)+B.bleeders(4.),nodes)
    r.update(instrument_ok=True,new_dfe_voltage_audit=new,whole_circuit_voltage_audit=whole,
             whole_circuit_voltage_envelope_pass=D.envelope(whole),
             aperture=T.aperture(t,main[:,3]-main[:,4],bits,PHASE),
             tuning_controls=C.control_audit(t,y[:,len(F.VECTORS):],nodes,vdd),
             new_tuning_switch_voltage_audit=V.audit([s for s in mos if s.startswith('Xrc_switch ')],nodes))
    r['signal_gate_pass']=C.accepted(r)
    r['nominal_replay_matches']=C.calibration_matches(r,reference) if corner.is_nominal else None
    return r


def schedule(evaluate):
    result={'entry':133,'pvt':[],'primary_channel_pvt_pass':False,'fixed_phase_ui':PHASE,
            'fixed_code':2,'fixed_sign':1,'full_receiver_verified':False,
            'runtime_settling_verified':False,'corner_retuning':False}
    def append(c):
        r=evaluate(c);result['pvt'].append({'corner':str(c),'result':r});return r
    nominal=append(SCREENS[0])
    if not C.accepted(nominal) or not nominal.get('nominal_replay_matches',False): return result
    for c in SCREENS[1:]: append(c)
    if not all(C.accepted(x['result']) for x in result['pvt']): return result
    for c in all_corners():
        if c not in SCREENS: append(c)
    result['primary_channel_pvt_pass']=all(C.accepted(x['result']) for x in result['pvt'])
    return result
