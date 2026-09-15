"""Entry 125 timing checks. Synthetic fixtures are never measurements."""
import numpy as np
import pytest

from nebula.common.types import Corner, UI_SECONDS as UI
from nebula.device import dfe_connected as F, dfe_timing as T
from nebula.link.config import LinkConfig


def test_retiming_changes_only_external_clocks_and_output_format():
    cfg = LinkConfig(channel_loss_db_at_nyquist=12)
    bits = F.pattern(cfg)
    original = F.deck(Corner('tt', 1, 27), cfg, bits, 1., 2, 1)
    actual = T.deck(Corner('tt', 1, 27), cfg, bits, 1.5, 2, 1)
    keep = lambda text: [s for s in text.splitlines()
        if not s.startswith(('Vdfclk', 'set wr_singlescale'))]
    assert keep(actual) == keep(original)
    assert 'set wr_singlescale' in actual
    clock=next(s for s in actual.splitlines() if s.startswith('Vdfclk '))
    values=[float(v) for v in clock.split('PULSE(')[1].rstrip(')').split()]
    assert values==pytest.approx([.6,1.2,7e-10,1e-11,1e-11,8e-11,2e-10],rel=1e-14,abs=0)


@pytest.mark.parametrize('phase,code,sign', [(0.5,2,1),(1.5,4,1),(1.5,2,0)])
def test_unregistered_timing_members_rejected(phase, code, sign):
    cfg = LinkConfig(channel_loss_db_at_nyquist=12)
    with pytest.raises(ValueError):
        T.deck(Corner('tt', 1, 27), cfg, F.pattern(cfg), phase, code, sign)


def test_single_scale_parser_checks_shape_time_and_finiteness(tmp_path):
    path = tmp_path/'synthetic.txt'
    t = np.arange(10)*1e-12
    a = np.column_stack([t, t+1, t+2])
    np.savetxt(path, a, fmt='%.16g')
    rt, y = T.read_table(path, 2)
    assert np.allclose(y, a[:,1:])
    assert np.array_equal(rt, t)
    with pytest.raises(ValueError):
        T.read_table(path, 3)
    with pytest.raises(ValueError):
        T.read_table(path, 2, expected_time=t+1e-15)
    a[5,1] = np.nan
    np.savetxt(path, a)
    with pytest.raises(ValueError):
        T.read_table(path, 2)


def fixture():
    cfg = LinkConfig(channel_loss_db_at_nyquist=7.5)
    bits = F.pattern(cfg)
    t = np.arange(0, F.STOP_UI*UI+.1e-12, .5e-12)
    # A known one-UI-wide symbol; sampling is in its centre.
    ix = np.clip(np.floor(t/UI-2.5).astype(int),0,F.N_BITS-1)
    v = .2*(2*bits[ix]-1)
    return t, v, bits


def test_finite_pattern_aperture_not_ber_or_clock_sweep():
    t, v, bits = fixture()
    r = T.aperture(t,v,bits,1.)
    assert r['eye_width_ui'] >= .99
    assert r['eye_width_at_100mv_ui'] >= .99
    assert r['passes_0p4ui'] and not r['ber_verified']
    assert r['grid_step_ui'] == .005
    assert r['sample_anchor_ui'] == -.025


def test_aperture_requires_correct_absolute_sign_not_just_separation():
    t, v, bits = fixture()
    r = T.aperture(t,v+.3,bits,1.)
    assert r['eye_width_ui'] == 0 and not r['passes_0p4ui']


@pytest.mark.parametrize('fault', ['flipped','truncated','sparse','nan'])
def test_bad_aperture_data_fails(fault):
    t,v,bits = fixture()
    if fault == 'flipped':
        assert T.aperture(t,-v,bits,1.)['eye_width_ui'] == 0
        return
    if fault == 'truncated': t,v=t[:200],v[:200]
    elif fault == 'sparse': t,v=t[::10],v[::10]
    else: v[100]=np.nan
    with pytest.raises(ValueError): T.aperture(t,v,bits,1.)


def fake(eye=.2, passed=True):
    return {'instrument_ok': True, 'new_dfe_voltage_audit': {'documented_ranges_ok': True},
        'whole_circuit_voltage_envelope_pass': True, 'sampled_eye_height_v': eye,
        'logic_pass': passed, 'minimum_sample_signed_v': .05,
        'ctle_plus_dfe_vdd_power_w': .009, 'aperture': {'passes_0p4ui': passed}}


def test_registered_timing_schedule_has_no_per_corner_retuning():
    from nebula.experiments import exp_dfe_timing as E
    calls=[]
    def evaluate(corner,loss,phase,code,sign,stage):
        calls.append((corner,loss,phase,code,sign,stage))
        return fake(.2+phase*.01 if code==2 and sign==1 else .15)
    r=E.schedule(evaluate)
    assert len(calls)==95 and r['selected_phase_ui']==1.75
    assert len(r['pvt'])==90 and r['new_channel_pvt_pass']
    assert all(c[2:5]==((1.,2,1) if c[1]==3 else (1.75,2,1)) for c in calls[5:])
    assert not r['full_receiver_verified']


@pytest.mark.parametrize('mode', ['bad_phase','no_benefit','bad_reverse'])
def test_timing_schedule_stops_at_registered_failure(mode):
    from nebula.experiments import exp_dfe_timing as E
    calls=[]
    def evaluate(corner,loss,phase,code,sign,stage):
        calls.append(stage)
        if mode=='bad_phase': return fake(passed=False)
        if mode=='bad_reverse' and sign==-1: return {'instrument_ok': False}
        return fake(.2 if mode=='no_benefit' else (.3 if sign==1 and code else .15))
    r=E.schedule(evaluate)
    assert len(calls)==(3 if mode=='bad_phase' else 5)
    assert not r['pvt'] and not r['new_channel_pvt_pass']
