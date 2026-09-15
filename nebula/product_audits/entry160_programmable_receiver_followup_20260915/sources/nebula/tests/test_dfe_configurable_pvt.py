"""PVT verification must keep one physical circuit, setting, phase and strict gate."""
import json
from pathlib import Path

from nebula.common.types import Corner,all_corners
from nebula.link.config import LinkConfig
from nebula.device import dfe_connected as F,dfe_configurable as C
from nebula.device import dfe_configurable_pvt as P


def good():
    return {'instrument_ok':True,'new_dfe_voltage_audit':{'documented_ranges_ok':True},
            'whole_circuit_voltage_envelope_pass':True,'logic_pass':True,'sampled_eye_height_v':.2,
            'minimum_sample_signed_v':.05,'ctle_plus_dfe_vdd_power_w':.012,
            'aperture':{'passes_0p4ui':True},'tuning_controls':{'control_valid':True,'varactor_voltage_envelope_pass':True},
            'nominal_replay_matches':True}


def test_pvt_schedule_is_exact_unique_45_and_has_no_corner_retuning():
    seen=[]
    def evaluate(c): seen.append(c);return good()
    r=P.schedule(evaluate)
    assert r['primary_channel_pvt_pass'] and len(seen)==len(set(seen))==45
    assert set(seen)==set(all_corners())
    assert tuple(seen[:5])==P.SCREENS
    assert r['fixed_phase_ui']==1. and r['fixed_code']==2


def test_bad_nominal_replay_stops_after_one_call():
    seen=[]
    def evaluate(c): seen.append(c);return {**good(),'nominal_replay_matches':False}
    r=P.schedule(evaluate)
    assert not r['primary_channel_pvt_pass'] and len(seen)==1


def test_corner_screen_failure_stops_after_five_and_remains_failed():
    seen=[]
    def evaluate(c):
        seen.append(c);return {**good(),'logic_pass':len(seen)!=3}
    r=P.schedule(evaluate)
    assert not r['primary_channel_pvt_pass'] and len(seen)==5


def test_late_failure_preserves_all_45_registered_cases():
    seen=[]
    def evaluate(c):
        seen.append(c);return {**good(),'new_dfe_voltage_audit':{'documented_ranges_ok':len(seen)!=20}}
    r=P.schedule(evaluate)
    assert not r['primary_channel_pvt_pass'] and len(seen)==45


def test_new_pvt_extractor_exactly_replays_measured_nominal_circuit():
    root=Path(__file__).resolve().parents[1]/'product_audits/entry132_dfe_configurable_20260910/phase_tuned1_phase1_code2_sign1'
    saved=json.loads((root/'result.json').read_text());cfg=LinkConfig(channel_loss_db_at_nyquist=7.5)
    text=C.deck(True,Corner('tt',1.,27),cfg,F.pattern(cfg),1.,2,1)
    assert text==(root/'design.cir').read_text()
    r=P.extract(root,text,Corner('tt',1.,27),saved)
    assert r['nominal_replay_matches'] and C.accepted(r)
    for k in ('new_dfe_voltage_audit','whole_circuit_voltage_audit','tuning_controls','sampled_eye_height_v','aperture'):
        assert r[k]==saved[k]


def test_pvt_registration_hash_is_checkout_stable():
    root=Path(__file__).resolve().parents[2];name='nebula/DFE_CONFIGURABLE_PVT_PLAN.md'
    assert name+' text eol=lf' in (root/'.gitattributes').read_text()
    assert b'\r\n' not in (root/name).read_bytes()


def test_pvt_preflight_pins_the_successful_primary_and_prior_sources():
    from nebula.experiments.exp_dfe_configurable_pvt import source_prerequisites,SOURCES
    config,reference=source_prerequisites()
    assert config['entry']==132 and reference['signal_gate_pass']
    assert set(config['source_sha256'])<=set(SOURCES)


def test_corner_changes_supply_controls_but_not_device_geometry():
    cfg=LinkConfig(channel_loss_db_at_nyquist=7.5);bits=F.pattern(cfg)
    tt=C.deck(True,Corner('tt',1.,27),cfg,bits,1.,2,1)
    ss=C.deck(True,Corner('ss',.95,125),cfg,bits,1.,2,1)
    assert F.all_mos(tt)==F.all_mos(ss)
    sources={s.split()[0]:s.split() for s in ss.splitlines() if s.startswith(('VrcR ','VrcC '))}
    assert abs(float(sources['VrcR'][-1])-1.8*.95*.7)<1e-14
    assert abs(float(sources['VrcC'][-1])-1.8*.95*.165)<1e-14
    assert '.temp 125' in ss
