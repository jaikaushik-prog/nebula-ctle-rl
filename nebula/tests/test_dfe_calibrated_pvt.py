"""Calibrated fixed-control PVT must replay nominal and retain every corner."""
import copy
import json
import pytest
from nebula.common.types import all_corners,Corner
from nebula.device import dfe_calibrated_verification as V
from nebula.experiments import exp_dfe_calibrated_pvt as E

def test_nominal_deck_is_exact_and_controls_scale_with_supply():
    assert E.deck(Corner('tt',1.,27))==V.link_deck()
    for corner in all_corners():
        text=E.deck(corner)
        for name,node,fraction in [('VrcR','rctrl',.7),('VrcC','cctrl',.185)]:
            assert f'{name} {node} 0 {1.8*corner.vdd_scale*fraction:.16g}' in text
        assert '.nodeset' not in text

def test_schedule_requires_nominal_calibration_and_retains_five_screen_failures():
    reference=json.loads((E.PRIOR/E.REFERENCE).read_text())
    calls=[]
    def good(corner):
        calls.append(corner)
        return {**copy.deepcopy(reference),'nominal_replay_matches':True}
    s=E.schedule(good)
    assert len(calls)==45 and s['entry']==144 and s['primary_channel_pvt_pass']
    assert s['r_fraction']==.7 and s['c_fraction']==.185 and not s['corner_retuning']
    calls.clear()
    def no_cal(corner): return {**good(corner),'nominal_replay_matches':False}
    assert not E.schedule(no_cal)['primary_channel_pvt_pass'] and len(calls)==1
    calls.clear()
    def fail_screen(corner):
        r=good(corner)
        if not corner.is_nominal: r['instrument_ok']=False
        return r
    assert not E.schedule(fail_screen)['primary_channel_pvt_pass'] and len(calls)==5

def test_prior_nominal_evidence_and_exact_fresh_decoder_replay():
    proof,config,reference=E.prerequisites()
    assert proof['verified_archives']==10 and config['entry']==143
    folder=E.PRIOR/E.REFERENCE.parent
    r=E.extract(folder,(folder/'design.cir').read_text(),Corner('tt',1.,27),reference)
    assert r['signal_gate_pass'] and r['nominal_replay_matches']
    assert r['correct_bits']==64
    assert r['sampled_eye_height_v']==reference['sampled_eye_height_v']
