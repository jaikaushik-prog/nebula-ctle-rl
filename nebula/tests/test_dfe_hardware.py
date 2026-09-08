"""Entry 106: independent transistor-slicer instrument boundaries."""
import numpy as np
import pytest

from nebula.device import dfe_hardware as D
from nebula.common.types import Corner, UI_SECONDS
from nebula.link.config import LinkConfig


def ideal_trace():
    bits = D.pattern(LinkConfig(channel_loss_db_at_nyquist=7.5))
    t = np.arange(0, (len(bits) + 2) * UI_SECONDS, UI_SECONDS / 200)
    y = np.zeros((len(t), len(D.VECTORS)))
    y[:, 0] = D.clock_at(t, 1.8)
    y[:, 1], y[:, 2] = D.inputs_at(t, bits, 1.36)
    y[:, 3:5] = 1.8
    # Synthetic traces test the instrument only; never exported as evidence.
    for i, bit in enumerate(bits):
        edge = D.edge_time(i)
        active = (t >= edge + 40e-12) & (t < edge + 99e-12)
        y[active, 3] = 0 if bit else 1.8
        y[active, 4] = 1.8 if bit else 0
        held = (t >= edge + 50e-12) & (t < edge + UI_SECONDS + 50e-12)
        y[held, 5] = 1.8 if bit else 0
        y[held, 6] = 0 if bit else 1.8
    y[:, 7] = -1e-3
    return t, y, bits


def test_pattern_seed_and_histories():
    cfg = LinkConfig(channel_loss_db_at_nyquist=7.5)
    b = D.pattern(cfg)
    assert len(b) == 36 and np.array_equal(b, D.pattern(cfg))
    assert set(zip(b[4:-1], b[5:])) == {(0, 0), (0, 1), (1, 0), (1, 1)}
    assert UI_SECONDS == 200e-12


def test_mos_only_canonical_slicer_and_hold():
    lines = D.dut_lines(4)
    assert len(lines) == 19
    assert all(line.startswith('X') and 'sky130_fd_pr__' in line for line in lines)
    assert any(' p inp tail 0 ' in line for line in lines)
    assert any(' x y p 0 ' in line for line in lines)
    assert any(' q x vdd vdd ' in line for line in lines)
    assert 'w=8 l=0.15 nf=4' in next(x for x in lines if x.startswith('Xtail '))
    assert D.geometry(4)['gate_geometry_mm2'] == pytest.approx(20 * 4 * .15 / 1e6)
    assert D.geometry(4)['full_area_mm2'] is None


@pytest.mark.parametrize('width', [0, 2, 32, float('nan')])
def test_unregistered_width_rejected(width):
    with pytest.raises(ValueError):
        D.dut_lines(width)


def test_deck_explicit_clock_units_and_no_behavioral_dut():
    b = D.pattern(LinkConfig(channel_loss_db_at_nyquist=7.5))
    deck = D.deck(4, Corner('tt', 1, 27), 1.36, b)
    assert '.lib ' in deck and '.model ' not in deck
    assert 'PULSE(0 1.8 300p 2p 2p 96p 200p)' in deck
    assert 'tran 1p' in deck and ' 0 1p' in deck
    assert 'Iref' not in deck and 'Bcomp' not in deck


def test_correct_trace_passes_and_power_is_not_full_receiver():
    t, y, b = ideal_trace()
    r = D.analyze(t, y, b, 1.8, 1.36)
    assert r['block_pass'] and r['scored_bits'] == 32
    assert r['dut_vdd_power_w'] == pytest.approx(.0018)
    assert r['full_receiver_verified'] is False
    assert r['hardware_dfe_complete'] is False


@pytest.mark.parametrize('fault', ['polarity', 'stuck', 'clock', 'input', 'late'])
def test_gate_can_fail(fault):
    t, y, b = ideal_trace()
    if fault == 'polarity':
        y[:, [3, 4]] = y[:, [4, 3]]
    elif fault == 'stuck':
        y[:, 5] = 1.8
    elif fault == 'clock':
        y[:, 0] = 0
    elif fault == 'input':
        y[:, 1] += .05
    else:
        y[:, 3:5] = 1.8
    assert not D.analyze(t, y, b, 1.8, 1.36)['block_pass']


@pytest.mark.parametrize('fault', ['nan', 'short', 'order', 'columns'])
def test_broken_data_rejected(fault):
    t, y, b = ideal_trace()
    if fault == 'nan':
        y[100, 0] = np.nan
    elif fault == 'short':
        t, y = t[:100], y[:100]
    elif fault == 'order':
        t[100] = t[99]
    else:
        y = y[:, :-1]
    with pytest.raises(ValueError):
        D.analyze(t, y, b, 1.8, 1.36)


def test_wrdata_repeated_axes_fail_closed(tmp_path):
    t, y, _ = ideal_trace()
    data = np.column_stack([a for j in range(len(D.VECTORS)) for a in (t, y[:, j])])
    p = tmp_path / 'trace.txt'
    np.savetxt(p, data)
    tt, yy = D.read_trace(p)
    assert np.array_equal(tt, t) and np.array_equal(yy, y)
    data[100, 2] += 1e-12
    np.savetxt(p, data)
    with pytest.raises(ValueError, match='axis'):
        D.read_trace(p)


def test_bounded_schedule_no_tt_pass_stops():
    from nebula.experiments.exp_dfe_slicer import schedule
    calls = []
    def evaluate(w, c, phase):
        calls.append((w, c, phase))
        return {'block_pass': False}
    result = schedule(evaluate)
    assert len(calls) == 3 and result['selected_width_um'] is None
    assert not result['all_corner_block_pass']


def test_bounded_schedule_smallest_pass_frozen_even_if_pvt_fails():
    from nebula.experiments.exp_dfe_slicer import schedule
    calls = []
    def evaluate(w, c, phase):
        calls.append((w, c, phase))
        return {'block_pass': w >= 8 and phase == 'screen'}
    result = schedule(evaluate)
    assert len(calls) == 48 and result['selected_width_um'] == 8
    assert {w for w, _, phase in calls if phase == 'pvt'} == {8}
    assert not result['all_corner_block_pass']


def test_common_mode_tamper_rejected(tmp_path):
    import json
    from nebula.experiments.exp_dfe_slicer import source_common_mode
    p = tmp_path / 'tt_1.00_27/ac_noise'
    p.mkdir(parents=True)
    (p / 'ngspice.log').write_text('v(outp) = 1.36')
    (tmp_path / 'evidence_sha256.json').write_text(json.dumps({
        'tt_1.00_27/ac_noise/ngspice.log': 'incorrect'}))
    with pytest.raises(ValueError, match='hash'):
        source_common_mode(tmp_path, Corner('tt', 1, 27))


def test_common_mode_windows_manifest_paths(tmp_path):
    import hashlib
    import json
    from nebula.experiments.exp_dfe_slicer import source_common_mode
    p = tmp_path / 'tt_1.00_27/ac_noise'
    p.mkdir(parents=True)
    log = p / 'ngspice.log'
    log.write_text('v(outp) = 1.36\n')
    sha = hashlib.sha256(log.read_bytes()).hexdigest()
    (tmp_path / 'evidence_sha256.json').write_text(json.dumps({
        'tt_1.00_27\\ac_noise\\ngspice.log': sha}))
    cm, key, actual = source_common_mode(tmp_path, Corner('tt', 1, 27))
    assert cm == 1.36 and actual == sha


def test_common_mode_conflicting_separator_aliases_rejected(tmp_path):
    import json
    from nebula.experiments.exp_dfe_slicer import source_common_mode
    (tmp_path / 'evidence_sha256.json').write_text(json.dumps({
        'tt_1.00_27/ac_noise/ngspice.log': 'one',
        'tt_1.00_27\\ac_noise\\ngspice.log': 'two'}))
    with pytest.raises(ValueError, match='conflicting'):
        source_common_mode(tmp_path, Corner('tt', 1, 27))


def test_real_failed_entry106_evidence_reproduces():
    import hashlib
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / 'product_audits/entry106_dfe_slicer_run_20260906'
    manifest = json.loads((root / 'evidence_sha256.json').read_text())
    for key, expected in manifest.items():
        assert hashlib.sha256((root / key).read_bytes()).hexdigest() == expected
    cfg = json.loads((root / 'config.json').read_text())
    summary = json.loads((root / 'summary.json').read_text())
    assert summary['spice_calls'] == 3 and summary['selected_width_um'] is None
    for width in (4, 8, 16):
        folder = root / f'screen_w{width}_tt_1.00_27'
        saved = json.loads((folder / 'result.json').read_text())
        t, y = D.read_trace(folder / 'trace.txt')
        actual = D.analyze(t, y, cfg['bits'], 1.8, saved['common_mode_v'])
        assert actual['stimulus_valid'] and not actual['block_pass']
        assert actual['correct_bits'] == saved['correct_bits'] == 15
        assert actual['bits'] == saved['bits']
        assert actual['dut_vdd_power_w'] == saved['dut_vdd_power_w']
