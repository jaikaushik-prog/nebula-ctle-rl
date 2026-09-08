"""Entry 109 isolated memory instrument; synthetic traces are test-only."""
import json
from pathlib import Path

import numpy as np
import pytest

from nebula.device import dfe_hardware as D
from nebula.link.config import LinkConfig


def bits():
    return D.pattern(LinkConfig(channel_loss_db_at_nyquist=7.5))


def synthetic():
    from nebula.device import dfe_memory_probe as M
    t = np.arange(7601) * 1e-12
    q = np.zeros_like(t)
    for i, bit in enumerate(bits()):
        q[t >= D.edge_time(i) + 10e-12] = 1.8 * bit
    y = np.column_stack((*M.inputs_at(t, bits()), q, 1.8-q,
                         np.full_like(t, -1e-3), np.zeros_like(t), np.zeros_like(t)))
    return t, y


def test_exact_existing_memory_only():
    from nebula.device import dfe_memory_probe as M
    expected = D.dut_lines(4, buffered=True)[-8:]
    assert M.memory_lines() == expected
    deck = M.deck(bits())
    assert [s for s in deck.splitlines() if s.startswith('X')] == expected
    assert '.model' not in deck and '.ic ' not in deck and 'Vclk' not in deck
    assert 'sky130_ctle_pfet__tt.lib.spice' in deck
    assert 'Vset bx 0 PWL(' in deck and 'Vreset by 0 PWL(' in deck
    assert M.geometry()['gate_geometry_mm2'] == pytest.approx(8*4*.15/1e6)
    assert M.geometry()['full_area_mm2'] is None


def test_clean_sources_have_no_illegal_overlap_and_release_before_hold():
    from nebula.device import dfe_memory_probe as M
    t, _ = synthetic()
    bx, by = M.inputs_at(t, bits())
    assert np.all((bx == 1.8) | (by == 1.8))
    for i, bit in enumerate(bits()):
        a, b = M.inputs_at(np.array([D.edge_time(i)+50e-12, D.edge_time(i)+110e-12]), bits())
        assert (a[0], b[0]) == ((0, 1.8) if bit else (1.8, 0))
        assert a[1] == b[1] == 1.8
    assert set(bits()[4:]) == {0, 1}


@pytest.mark.parametrize('invalid', [[0]*35, [0]*35+[2], [0]*35+[float('nan')]])
def test_bad_pattern_rejected(invalid):
    from nebula.device import dfe_memory_probe as M
    with pytest.raises(ValueError):
        M.deck(invalid)


def test_clean_hold_pass_is_not_complete_dfe():
    from nebula.device import dfe_memory_probe as M
    t, y = synthetic()
    r = M.analyze(t, y, bits())
    assert r['memory_hold_pass'] and r['stimulus_valid'] and r['correct_bits'] == 32
    assert not r['hardware_dfe_complete'] and not r['full_receiver_verified']
    assert r['dut_vdd_power_w'] == pytest.approx(.0018)
    assert r['ideal_input_source_net_power_w'] == 0
    assert 'raw_correct_bits' not in r


@pytest.mark.parametrize('fault', ['stuck', 'inverted', 'glitch', 'stimulus'])
def test_false_pass_prevented(fault):
    from nebula.device import dfe_memory_probe as M
    t, y = synthetic()
    if fault == 'stuck':
        y[:, 2:4] = [0, 1.8]
    elif fault == 'inverted':
        y[:, 2:4] = y[:, 2:4][:, ::-1]
    elif fault == 'glitch':
        y[np.argmin(abs(t-D.edge_time(6)-150e-12)), 2:4] = [0, 1.8]
    else:
        y[:, 0] = 1.8
    r = M.analyze(t, y, bits())
    assert not r['memory_hold_pass']
    if fault == 'stuck':
        assert r['correct_bits'] == int(np.sum(bits()[4:] == 0))


@pytest.mark.parametrize('fault', ['nan', 'order', 'truncate', 'sparse', 'shape'])
def test_invalid_trace_rejected(fault):
    from nebula.device import dfe_memory_probe as M
    t, y = synthetic()
    if fault == 'nan':
        y[100, 2] = np.nan
    elif fault == 'order':
        t[10] = t[9]
    elif fault == 'truncate':
        t, y = t[:3000], y[:3000]
    elif fault == 'sparse':
        t, y = t[::4], y[::4]
    else:
        y = y[:, :-1]
    with pytest.raises(ValueError):
        M.analyze(t, y, bits())


def test_reader_requires_identical_vector_times(tmp_path):
    from nebula.device import dfe_memory_probe as M
    t, y = synthetic()
    data = np.empty((len(t), 14))
    data[:, 0::2], data[:, 1::2] = t[:, None], y
    path = tmp_path / 'test-only.txt'
    np.savetxt(path, data)
    a, b = M.read_trace(path)
    assert np.array_equal(a, t) and np.array_equal(b, y)
    data[10, 2] += 1e-12
    np.savetxt(path, data)
    with pytest.raises(ValueError, match='time axis'):
        M.read_trace(path)


def test_failure_preserved_one_call_no_retry(tmp_path, monkeypatch):
    from nebula.experiments import exp_dfe_memory as E
    calls = []
    def fail(deck, folder):
        calls.append(folder)
        folder.mkdir()
        (folder / 'design.cir').write_text(deck, encoding='ascii')
        (folder / 'ngspice.log').write_text('Error: deliberately injected unit test')
        raise ValueError('unit-test failure')
    monkeypatch.setattr(E.P, 'invoke', fail)
    out = tmp_path / 'test-only'
    r = E.run(out)
    assert len(calls) == r['spice_calls'] == 1
    assert not r['memory_hold_pass'] and not r['instrument_ok']
    assert (calls[0] / 'ngspice.log').exists()
    assert (out / 'evidence_sha256.json').exists()
    with pytest.raises(FileExistsError):
        E.run(out)
    manifest = json.loads((out / 'evidence_sha256.json').read_text())
    for key, sha in manifest.items():
        assert E.digest(out / key) == sha


def test_real_entry109_reproduces_clean_memory_only():
    from nebula.device import dfe_memory_probe as M
    from nebula.experiments.exp_dfe_slicer import digest
    root = Path(__file__).resolve().parents[1] / 'product_audits/entry109_dfe_memory_20260906'
    manifest = json.loads((root / 'evidence_sha256.json').read_text())
    assert len(manifest) == 22
    for key, sha in manifest.items():
        assert digest(root / key) == sha
    cfg = json.loads((root / 'config.json').read_text())
    saved = json.loads((root / 'summary.json').read_text())
    assert cfg['max_calls'] == saved['spice_calls'] == 1
    assert cfg['bits'] == bits().tolist() and cfg['ideal_test_inputs']
    assert not cfg['ctle_connected'] and not cfg['buffers_connected']
    assert not cfg['comparator_connected'] and not cfg['feedback_connected']
    folder = root / 'clean_tt_1.00_27'
    assert (folder / 'design.cir').read_text() == M.deck(cfg['bits'])
    t, y = M.read_trace(folder / 'trace.txt')
    actual = M.analyze(t, y, cfg['bits'])
    assert all(saved[key] == value for key, value in actual.items())
    assert actual['memory_hold_pass'] and actual['correct_bits'] == 32
    assert not actual['hardware_dfe_complete'] and not actual['full_receiver_verified']
    assert min(row['held_min_logic_margin_v'] for row in actual['bits']) == pytest.approx(.8931467331769899)
    assert max(row['final_stable_delay_s'] for row in actual['bits']) == pytest.approx(50.5e-12, abs=1e-15)
