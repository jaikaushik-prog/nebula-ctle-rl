"""Physical off-branch discharge recovery; fixtures are not evidence."""
import pytest

from nebula.common.types import Corner
from nebula.device import dfe_connected as F, dfe_tail_bleed as B
from nebula.link.config import LinkConfig


@pytest.mark.parametrize('length',[2.,4.])
def test_bleeders_are_real_fixed_mos_on_existing_nodes(length):
    cfg=LinkConfig(channel_loss_db_at_nyquist=7.5)
    text=B.deck(length,Corner('tt',1,27),cfg,F.pattern(cfg),1.,2,1)
    original=F.deck(Corner('tt',1,27),cfg,F.pattern(cfg),1.,2,1)
    assert all(s in text.splitlines() for s in original.splitlines() if s.startswith('X'))
    assert len(B.bleeders(length))==4
    assert all('df_nbias 0 0 sky130_fd_pr__nfet_01v8 w=0.42' in s for s in B.bleeders(length))
    assert 'wrdata terminals.txt' in text and 'set wr_singlescale' in text
    assert B.geometry(length)['added_bleeder_gate_um2']==pytest.approx(4*.42*length)
    assert B.geometry(length)['added_mos_count']==32
    assert not B.geometry(length)['code_zero_is_feedback_disabled']
    assert not any(s.startswith(('I','B','G')) for s in text.splitlines())


def test_unregistered_bleeder_length_rejected():
    with pytest.raises(ValueError): B.bleeders(8)


def good(eye=.2):
    return {'instrument_ok':True,'new_dfe_voltage_audit':{'documented_ranges_ok':True},
        'whole_circuit_voltage_envelope_pass':True,'logic_pass':True,
        'sampled_eye_height_v':eye,'minimum_sample_signed_v':.05,
        'ctle_plus_dfe_vdd_power_w':.009,'aperture':{'passes_0p4ui':True}}


def test_recovery_keeps_one_geometry_and_does_not_claim_zero_feedback():
    from nebula.experiments import exp_dfe_tail_bleed as E
    calls=[]
    def evaluate(length,corner,loss,phase,code,sign,stage):
        calls.append((length,corner,loss,phase,code,sign,stage))
        return good(.2 if code==2 and sign==1 else .15)
    r=E.schedule(evaluate)
    assert len(calls)==57 and r['selected_length_um']==4
    assert r['primary_channel_pvt_pass'] and len(r['pvt'])==45
    assert all(row[0]==4 and row[2:6]==(7.5,1.,2,1) for row in calls[12:])
    assert not r['full_receiver_verified'] and not r['code_zero_is_feedback_disabled']


@pytest.mark.parametrize('failure',['voltage','no_benefit','invalid_control'])
def test_bleeder_schedule_fails_without_retuning_or_waiver(failure):
    from nebula.experiments import exp_dfe_tail_bleed as E
    calls=[]
    def evaluate(length,corner,loss,phase,code,sign,stage):
        calls.append(stage)
        r=good(.2)
        if failure=='voltage' or (failure=='invalid_control' and stage=='control'):
            r['new_dfe_voltage_audit']['documented_ranges_ok']=False
        return r
    r=E.schedule(evaluate)
    assert r['selected_length_um'] is None and not r['pvt']
    assert len(calls)==(8 if failure=='voltage' else 12)


def test_trial_preserves_simulator_failure_and_never_retries(tmp_path,monkeypatch):
    import json
    from nebula.experiments import exp_dfe_tail_bleed as E
    monkeypatch.setattr(E.A,'verify',lambda root:{'manifest_sha256':'synthetic-only'})
    calls=[]
    def fail(text,folder):
        calls.append(folder)
        folder.mkdir()
        (folder/'design.cir').write_text(text,encoding='ascii')
        (folder/'ngspice.log').write_text('synthetic failure, NOT a simulator measurement')
        raise ValueError('injected failure')
    monkeypatch.setattr(E.P,'invoke',fail)
    out=tmp_path/'synthetic-only'
    trial=E.Trial(out,125,1,E.PRIOR)
    r=trial.evaluate(4.,Corner('tt',1,27),7.5,1.,2,1,'screen')
    assert len(calls)==1 and not r['instrument_ok'] and not r['signal_gate_pass']
    trial.finish({'synthetic_only':True})
    for key,sha in json.loads((out/'evidence_sha256.json').read_text()).items():
        assert E.A.digest(out/key)==sha
    with pytest.raises(RuntimeError): trial.evaluate(4.,Corner('tt',1,27),7.5,1.,2,1,'extra')
    assert len(calls)==1
    with pytest.raises(FileExistsError): E.Trial(out,125,1,E.PRIOR)
