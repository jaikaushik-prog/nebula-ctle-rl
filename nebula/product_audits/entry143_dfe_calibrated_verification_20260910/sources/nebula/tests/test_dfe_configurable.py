"""The configurable connection must preserve the verified transistor DFE."""
from pathlib import Path
import json

import numpy as np
import pytest

from nebula.common.types import Corner
from nebula.link.config import LinkConfig
from nebula.device import dfe_connected as F, dfe_tail_bleed as B
from nebula.device import configurable_rc as R, dfe_configurable as C


def test_only_passive_tuning_network_changes_in_connected_dut():
    corner=Corner('tt',1.,27);cfg=LinkConfig(channel_loss_db_at_nyquist=7.5);bits=F.pattern(cfg)
    before=B.deck(4.,corner,cfg,bits,1.,2,1)
    after=C.deck(True,corner,cfg,bits,1.,2,1)
    old=F.all_mos(before);new=F.all_mos(after)
    assert all(line in new for line in old)
    assert len(new)==len(old)+1
    assert all(line in after for line in R.added_lines((500,0.)))
    assert not any(line.startswith(('Xrs ','Xcs ')) for line in after.splitlines())
    assert after.count('.lib ')==1 and str(C.V.FULL_LIB.as_posix()) in after
    assert 'VrcR rctrl 0 1.26' in after and 'VrcC cctrl 0 0.297' in after
    assert all('v('+n+')' in after for n in C.terminals(after))
    assert 'rc_mid' in C.terminals(after)
    assert 'i(vrcr)' in after and 'i(vrcc)' in after
    assert all(line in after for line in F.extra_mos(1)+B.bleeders(4.))
    with pytest.raises(ValueError): C.deck(True,corner,cfg,bits,.5,2,1)


def test_fixed_calibration_changes_only_full_library():
    corner=Corner('tt',1.,27);cfg=LinkConfig(channel_loss_db_at_nyquist=7.5);bits=F.pattern(cfg)
    old=B.deck(4.,corner,cfg,bits,1.,2,1);new=C.deck(False,corner,cfg,bits,1.,2,1)
    strip=lambda d:'\n'.join(s for s in d.splitlines() if not s.startswith('.lib '))
    assert strip(old)==strip(new)


def test_primary_controls_are_the_measured_selected_identity():
    root=Path(__file__).resolve().parents[1]/'product_audits/entry131_configurable_rc_fine_20260910'
    r=json.loads((root/'summary.json').read_text())
    selected=next(x for x in r['candidates'] if x['geometry']==[500,0.])
    t=next(x for x in selected['targets'] if x['target_boost_db']==9 and x['target_frequency_hz']==1.9e9)
    assert t['found'] and (C.R_FRACTION,C.C_FRACTION)==(t['r_fraction'],t['c_fraction'])
    assert C.geometry()['geometry_subtotal_mm2']<.05
    assert not C.geometry()['routed_layout']


def test_control_audit_rejects_wrong_bias_nonfinite_and_varactor_overvoltage():
    t=np.linspace(0,1e-8,200);y=np.zeros((len(t),6))
    y[:,0]=y[:,2]=1.26;y[:,1]=y[:,3]=.297
    nodes={'s1':np.full(len(t),.5),'s2':np.full(len(t),.5)}
    good=C.control_audit(t,y,nodes,1.8)
    assert good['control_valid'] and good['varactor_voltage_envelope_pass']
    shifted=y.copy();shifted[:,0]+=.01
    assert not C.control_audit(t,shifted,nodes,1.8)['control_valid']
    assert not C.control_audit(t,y,{**nodes,'s1':np.full(len(t),2.)},1.8)['varactor_voltage_envelope_pass']
    y[0,0]=np.nan
    with pytest.raises(ValueError): C.control_audit(t,y,nodes,1.8)


def passing(eye=.2):
    return {'instrument_ok':True,'new_dfe_voltage_audit':{'documented_ranges_ok':True},
            'whole_circuit_voltage_envelope_pass':True,'logic_pass':True,'sampled_eye_height_v':eye,
            'minimum_sample_signed_v':.05,'ctle_plus_dfe_vdd_power_w':.012,
            'aperture':{'passes_0p4ui':True},'tuning_controls':{'control_valid':True,'varactor_voltage_envelope_pass':True}}


def test_connection_reuses_strict_dfe_and_tuning_gates():
    r=passing();assert C.accepted(r)
    for key,value in [('new_dfe_voltage_audit',{'documented_ranges_ok':False}),('logic_pass',False),
                      ('sampled_eye_height_v',.09),('ctle_plus_dfe_vdd_power_w',.016),
                      ('aperture',{'passes_0p4ui':False}),('tuning_controls',{'control_valid':False,'varactor_voltage_envelope_pass':True})]:
        assert not C.accepted({**r,key:value})


def test_connected_schedule_stops_bad_calibration_and_requires_real_feedback_benefit():
    calls=[]
    def failed(*args): calls.append(args);return {'instrument_ok':False}
    assert not C.schedule(failed)['primary_connected_pass'] and len(calls)==1
    calls.clear()
    def evaluate(tuned,phase,code,sign,stage):
        calls.append((tuned,phase,code,sign,stage))
        if not tuned: return {**passing(),'calibration_matches':True}
        return passing(.2 if stage=='phase' else .15)
    result=C.schedule(evaluate)
    assert len(calls)==7 and result['primary_connected_pass'] and result['selected_phase_ui']==1.
    def no_benefit(tuned,phase,code,sign,stage): return {**passing(),'calibration_matches':True}
    assert not C.schedule(no_benefit)['primary_connected_pass']


def test_connection_plan_hash_is_checkout_stable():
    root=Path(__file__).resolve().parents[2];name='nebula/DFE_CONFIGURABLE_PLAN.md'
    assert name+' text eol=lf' in (root/'.gitattributes').read_text()
    assert b'\r\n' not in (root/name).read_bytes()


def test_calibration_rejects_voltage_power_width_or_bit_changes():
    r={'correct_bits':64,'sampled_eye_height_v':.2,'ctle_plus_dfe_vdd_power_w':.012,'aperture':{'eye_width_ui':.6}}
    assert C.calibration_matches(r,dict(r))
    for k,v in [('correct_bits',63),('sampled_eye_height_v',.200002),
                ('ctle_plus_dfe_vdd_power_w',.012000002),('aperture',{'eye_width_ui':.61})]:
        assert not C.calibration_matches({**r,k:v},r)


def test_connected_preflight_pins_measured_geometry_and_all_old_sources():
    from nebula.experiments.exp_dfe_configurable import source_prerequisites,SOURCES,DFE_SOURCES
    proof,config,reference,target=source_prerequisites()
    assert proof['file_count']==1812 and config['entry']==131
    assert reference['correct_bits']==64 and reference['signal_gate_pass']
    assert target['r_fraction']==.7 and target['c_fraction']==.165
    assert set(DFE_SOURCES)<=set(SOURCES)


def test_connected_extractor_replays_original_fixed_dfe_raw_measurement():
    from nebula.experiments.exp_dfe_configurable import extract,DFE_PRIOR,CALIBRATION_KEY
    folder=(DFE_PRIOR/CALIBRATION_KEY).parent
    reference=json.loads((folder/'result.json').read_text())
    cfg=LinkConfig(channel_loss_db_at_nyquist=7.5)
    text=C.deck(False,Corner('tt',1.,27),cfg,F.pattern(cfg),1.,2,1)
    replay=extract(folder,text,False,1.,2,1,reference)
    assert replay['calibration_matches'] and replay['signal_gate_pass']
    assert replay['correct_bits']==64
    assert replay['sampled_eye_height_v']==reference['sampled_eye_height_v']
