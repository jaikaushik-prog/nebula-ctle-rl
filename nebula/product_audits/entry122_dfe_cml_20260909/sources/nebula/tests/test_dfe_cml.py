"""Instrument tests use synthetic waveforms, never deliverable measurements."""
import numpy as np
import pytest

from nebula.device import dfe_cml as C
from nebula.device import dfe_hardware as D
from nebula.common.types import Corner, UI_SECONDS as UI
from nebula.link.config import LinkConfig


def fixture():
    bits = D.pattern(LinkConfig(channel_loss_db_at_nyquist=7.5))
    t = np.arange(0, 38 * UI, .5e-12)
    y = np.zeros((len(t), len(C.VECTORS)))
    y[:, 0], y[:, 1] = C.clock_at(t, 1.8)
    y[:, 2], y[:, 3] = D.inputs_at(t, bits, 1.36)
    captured = np.clip(np.floor(t / UI - 1.5).astype(int), 0, 35)
    # Master holds first half, tracks the new bit during the second half.
    data_index = np.clip(np.floor(t / UI - 1).astype(int), 0, 35)
    y[:, 4] = 1.4 + .2 * (2 * bits[data_index] - 1)
    y[:, 5] = 2.8 - y[:, 4]
    y[:, 6] = 1.4 + .2 * (2 * bits[captured] - 1)
    y[:, 7] = 2.8 - y[:, 6]
    y[:, 8] = -.001
    return t, y, bits


@pytest.mark.parametrize('width', C.WIDTHS_UM)
def test_canonical_devices_and_deck(width):
    mos = C.mos_lines(width)
    assert len(mos) == 15
    assert all(len(line.split()) == 9 for line in mos)
    assert all(D.NFET in line for line in mos)
    bits = fixture()[2]
    deck = C.deck(width, Corner('tt', 1, 27), 1.36, bits)
    assert [x for x in deck.splitlines() if x.startswith('X')] == mos + C.resistor_lines()
    assert not any(x[0].upper() in 'BIG' for x in deck.splitlines() if x and x[0] not in '*+.')
    assert 'wrdata terminals.txt' in deck
    assert 'm=' in C.resistor_lines()[0]


def test_reject_unregistered_width():
    with pytest.raises(ValueError):
        C.mos_lines(6)


def test_geometry_uses_total_width_not_extra_nf_multiplier():
    g = C.geometry(4)
    assert g['mos_gate_um2'] == pytest.approx(31.6)
    assert g['geometry_subtotal_mm2'] == pytest.approx((31.6+4*1.33+30.33)/1e6)
    assert g['resistors'][0]['r_actual_ohm'] == pytest.approx(800.1470835642745)


def test_failure_retention_and_no_retry(tmp_path, monkeypatch):
    import json
    from nebula.experiments import exp_dfe_cml as E
    calls = []
    def fail(deck, folder):
        calls.append(folder)
        folder.mkdir()
        (folder/'design.cir').write_text(deck, encoding='ascii')
        (folder/'ngspice.log').write_text('synthetic test-only failure')
        raise ValueError('unit-test failure')
    monkeypatch.setattr(E.P, 'invoke', fail)
    out = tmp_path/'synthetic-only'
    result = E.run(out)
    assert result['spice_calls'] == len(calls) == 3
    assert all(not r['result']['instrument_ok'] for r in result['screening'])
    for key, sha in json.loads((out/'evidence_sha256.json').read_text()).items():
        assert E.digest(out/key) == sha
    with pytest.raises(FileExistsError):
        E.run(out)


@pytest.mark.parametrize('fault', ['columns', 'axis', 'nan'])
def test_trace_reader_fail_closed(tmp_path, fault):
    t, y, _ = fixture()
    data = np.empty((len(t), 2*len(C.VECTORS)))
    data[:, 0::2], data[:, 1::2] = t[:, None], y
    if fault == 'columns':
        data = data[:, :-1]
    elif fault == 'axis':
        data[5, 2] += 1e-13
    else:
        data[5, 5] = np.nan
    path = tmp_path/'synthetic.txt'
    np.savetxt(path, data)
    with pytest.raises(ValueError):
        C.read_trace(path)


def test_differential_logic_and_energy():
    t, y, bits = fixture()
    r = C.analyze(t, y, bits, 1.8, 1.36)
    assert r['block_pass'] and r['correct_bits'] == 32
    assert r['dut_vdd_power_w'] == pytest.approx(.0018)
    assert not r['hardware_dfe_complete']


@pytest.mark.parametrize('kind', ['inverted', 'follower', 'clock', 'nan', 'truncated', 'axis'])
def test_false_pass_rejected(kind):
    t, y, bits = fixture()
    if kind == 'inverted':
        y[:, [6, 7]] = y[:, [7, 6]]
    elif kind == 'follower':
        y[:, 6:8] = y[:, 4:6]
    elif kind == 'clock':
        y[:, 0] = 0
    elif kind == 'nan':
        y[200, 6] = np.nan
    elif kind == 'truncated':
        t, y = t[:2000], y[:2000]
    elif kind == 'axis':
        t[200] = t[199]
    if kind in ('nan', 'truncated', 'axis'):
        with pytest.raises(ValueError):
            C.analyze(t, y, bits, 1.8, 1.36)
    else:
        assert not C.analyze(t, y, bits, 1.8, 1.36)['block_pass']


def test_schedule_smallest_pass_and_fixed_pvt():
    from nebula.experiments.exp_dfe_cml import schedule
    calls = []
    def evaluate(w, corner, phase):
        calls.append((w, corner, phase))
        return {'block_pass': w >= 8, 'voltage_audit': {'documented_ranges_ok': True}}
    result = schedule(evaluate)
    assert result['selected_width_um'] == 8
    assert len(calls) == 48 and all(c[0] == 8 for c in calls[3:])


def test_excursion_stops_pvt():
    from nebula.experiments.exp_dfe_cml import schedule
    calls = []
    def evaluate(*args):
        calls.append(args)
        return {'block_pass': True, 'voltage_audit': {'documented_ranges_ok': False}}
    result = schedule(evaluate)
    assert len(calls) == 3 and result['selected_width_um'] is None
    assert not result['hardware_dfe_complete']
