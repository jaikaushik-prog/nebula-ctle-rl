"""Connected DFE instrumentation; synthetic fixtures are not measurements."""
import numpy as np
import pytest

from nebula.device import dfe_connected as F
from nebula.common.types import Corner, UI_SECONDS as UI
from nebula.link.config import LinkConfig


def test_registered_pattern_and_causal_stimulus():
    cfg = LinkConfig(channel_loss_db_at_nyquist=7.5)
    bits = F.pattern(cfg)
    assert bits.shape == (80,) and np.isin(bits, (0, 1)).all()
    assert np.array_equal(bits, F.pattern(cfg))
    t, v = F.stimulus(cfg, bits)
    assert t[0] == 0 and np.all(np.diff(t) > 0)
    assert np.max(np.abs(v[t < 2*UI])) < 1e-12
    assert np.isfinite(v).all() and np.max(np.abs(v)) <= cfg.tx_swing_diff_pp_v/2


def test_code_changes_controls_not_transistor_geometry():
    cfg = LinkConfig(channel_loss_db_at_nyquist=7.5)
    bits = F.pattern(cfg)
    a = F.deck(Corner('tt', 1, 27), cfg, bits, .75, 0, 1)
    b = F.deck(Corner('tt', 1, 27), cfg, bits, .75, 8, 1)
    assert [s for s in a.splitlines() if s.startswith('X')] == [s for s in b.splitlines() if s.startswith('X')]
    assert 'Vtap3 tap3 0 0' in a and 'Vtap3 tap3 0 1.8' in b
    assert 'Xdfe_dacp sum_p df_q fd_common 0' in a
    assert not any(s.startswith(('B', 'I', 'G')) for s in a.splitlines())
    assert 'XM1   outp inp s1 0' in a and 'CLp   outp 0 {CL}' in a


@pytest.mark.parametrize('phase,code,sign', [(.1,1,1),(.75,3,1),(.75,1,0)])
def test_unregistered_membership_rejected(phase, code, sign):
    cfg = LinkConfig(channel_loss_db_at_nyquist=7.5)
    with pytest.raises(ValueError):
        F.deck(Corner('tt', 1, 27), cfg, F.pattern(cfg), phase, code, sign)


def synthetic():
    cfg = LinkConfig(channel_loss_db_at_nyquist=7.5)
    bits = F.pattern(cfg)
    phase = .75
    t = np.arange(0, F.STOP_UI*UI, .5e-12)
    y = np.zeros((len(t), len(F.VECTORS)))
    y[:, 0], y[:, 1] = F.clock_at(t, 1.8, phase)
    ti, vi = F.stimulus(cfg, bits)
    y[:, 2] = np.interp(t, ti, vi)
    capture = np.clip(np.floor(t/UI-2-phase).astype(int), 0, 79)
    analog = np.clip(np.floor(t/UI-2).astype(int), 0, 79)
    y[:, 3] = 1.4+.1*(2*bits[analog]-1)
    y[:, 4] = 2.8-y[:, 3]
    y[:, 5] = 1.4+.2*(2*bits[capture]-1)
    y[:, 6] = 2.8-y[:, 5]
    y[:, 7] = -.005
    y[:, -2:] = y[:, 5:7]
    return cfg, bits, phase, t, y


def test_correct_sampled_logic_not_complete_receiver():
    cfg, bits, phase, t, y = synthetic()
    r = F.analyze(t, y, bits, cfg, phase, 1.8)
    assert r['logic_pass'] and r['correct_bits'] == 64
    assert r['sampled_eye_height_v'] == pytest.approx(.4)
    assert r['ctle_plus_dfe_vdd_power_w'] == pytest.approx(.009)
    assert not r['full_receiver_verified']


@pytest.mark.parametrize('fault', ['follower', 'flipped', 'late', 'clock', 'truncated', 'nan'])
def test_false_connected_pass_rejected(fault):
    cfg, bits, phase, t, y = synthetic()
    if fault == 'follower':
        y[:, 5:7] = y[:, 3:5]
    elif fault == 'flipped':
        y[:, [5, 6]] = y[:, [6, 5]]
    elif fault == 'late':
        y[:, 5:7] = np.roll(y[:, 5:7], 360, axis=0)
    elif fault == 'clock':
        y[:, 0] = 0
    elif fault == 'truncated':
        t, y = t[:100], y[:100]
    else:
        y[100, 5] = np.nan
    if fault in ('truncated', 'nan'):
        with pytest.raises(ValueError):
            F.analyze(t, y, bits, cfg, phase, 1.8)
    else:
        assert not F.analyze(t, y, bits, cfg, phase, 1.8)['logic_pass']


def result(eye):
    return {'instrument_ok': True, 'new_dfe_voltage_audit': {'documented_ranges_ok': True},
            'whole_circuit_voltage_envelope_pass': True, 'sampled_eye_height_v': eye,
            'logic_pass': True, 'minimum_sample_signed_v': .05, 'ctle_plus_dfe_vdd_power_w': .009}


def test_registered_schedule_fixed_winner_and_all_calls():
    from nebula.experiments import exp_dfe_connected as E
    calls = []
    def evaluate(corner, loss, phase, code, sign, stage):
        calls.append((corner, loss, phase, code, sign, stage))
        return result(.13+phase*.01 if code == 0 else .15+.01*code*sign)
    r = E.schedule(evaluate)
    assert len(calls) == 58 and r['selected'] == {'phase_ui': 1., 'code': 8, 'sign': 1}
    assert all(x[2:5] == (1.,8,1) for x in calls[11:])
    assert r['primary_channel_pvt_pass'] and not r['full_receiver_verified']


@pytest.mark.parametrize('case', ['invalid', 'no_benefit', 'invalid_reverse'])
def test_schedule_stops_without_supported_benefit(case):
    from nebula.experiments import exp_dfe_connected as E
    calls = []
    def evaluate(corner, loss, phase, code, sign, stage):
        calls.append(stage)
        if case == 'invalid' or (case == 'invalid_reverse' and sign == -1):
            return {'instrument_ok': False}
        return result(.2 if code == 0 else (.3 if case == 'invalid_reverse' else .19))
    r = E.schedule(evaluate)
    assert r['selected'] is None and not r['pvt']
    assert len(calls) == (3 if case == 'invalid' else 11)


def test_combined_geometry_counts_all_off_branches():
    g = F.geometry()
    assert g['added_mos_count'] == 28 and g['added_poly_count'] == 7
    assert g['added_mos_gate_um2'] == pytest.approx(61.7)
    assert g['added_resistor_body_um2'] == pytest.approx(38.31)
    assert g['geometry_subtotal_mm2'] == pytest.approx(g['ctle_geometry_subtotal_mm2']+.00010001)


def test_failure_kept_without_retry(tmp_path, monkeypatch):
    import json
    from nebula.experiments import exp_dfe_connected as E
    calls = []
    def fail(deck, folder):
        calls.append(folder)
        folder.mkdir()
        (folder/'design.cir').write_text(deck, encoding='ascii')
        (folder/'ngspice.log').write_text('synthetic failure, not a simulator result')
        raise ValueError('injected test failure')
    monkeypatch.setattr(E.P, 'invoke', fail)
    out = tmp_path/'synthetic-only'
    r = E.run(out)
    assert r['spice_calls'] == len(calls) == 3 and r['selected'] is None
    for key, sha in json.loads((out/'evidence_sha256.json').read_text()).items():
        assert E.digest(out/key) == sha
    with pytest.raises(FileExistsError):
        E.run(out)
