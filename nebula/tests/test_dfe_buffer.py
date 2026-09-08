"""Entry 107: exact buffered delta, same measurements, legacy preserved."""
from pathlib import Path
import json

import numpy as np
import pytest

from nebula.device import dfe_hardware as D
from nebula.experiments import exp_dfe_slicer as E
from nebula.common.types import Corner


@pytest.mark.parametrize('width', [4, 8, 16])
def test_buffer_only_connectivity_delta(width):
    before = {x.split()[0]: x for x in D.dut_lines(width)}
    after = {x.split()[0]: x for x in D.dut_lines(width, buffered=True)}
    assert len(before) == 19 and len(after) == 27
    changed = {'Xq_p1': 'bx', 'Xq_n1': 'bx', 'Xqb_p1': 'by', 'Xqb_n1': 'by'}
    for name, line in before.items():
        fields = line.split()
        if name in changed:
            fields[2] = changed[name]
        assert after[name] == ' '.join(fields)
    extras = {name: line.split() for name, line in after.items() if name not in before}
    assert len(extras) == 8
    expected = {}
    for raw, middle, output in [('x', 'bx1', 'bx'), ('y', 'by1', 'by')]:
        for stage, inp, out in [(1, raw, middle), (2, middle, output)]:
            expected[f'Xbuf_{raw}{stage}_n'] = [out, inp, '0', '0', D.NFET]
            expected[f'Xbuf_{raw}{stage}_p'] = [out, inp, 'vdd', 'vdd', D.PFET]
    for name, nodes in expected.items():
        assert extras[name][1:6] == nodes
        assert extras[name][6:] == [f'w={width}', 'l=0.15', f'nf={width // 2}']


@pytest.mark.parametrize('width', [4, 8, 16])
def test_buffer_geometry_counts_total_width_once(width):
    result = D.geometry(width, buffered=True)
    assert result['mos_count'] == 27 and result['buffer_mos_count'] == 8
    assert result['gate_geometry_mm2'] == pytest.approx(28 * width * .15 / 1e6)
    assert result['full_area_mm2'] is None


def test_legacy_decks_byte_identical_and_buffer_stimulus_unchanged():
    root = Path(__file__).resolve().parents[1] / 'product_audits/entry106_dfe_slicer_run_20260906'
    cfg = json.loads((root / 'config.json').read_text())
    for width in (4, 8, 16):
        folder = root / f'screen_w{width}_tt_1.00_27'
        cm = json.loads((folder / 'result.json').read_text())['common_mode_v']
        old = D.deck(width, Corner('tt', 1, 27), cm, cfg['bits'])
        # Normalize filesystem newline encoding only; text contents must match.
        assert old == (folder / 'design.cir').read_text(encoding='ascii')
        new = D.deck(width, Corner('tt', 1, 27), cm, cfg['bits'], buffered=True)
        assert new.split('Xin1')[0].split('\n', 1)[1] == old.split('Xin1')[0].split('\n', 1)[1]
        new_control = new.split('.control')[1]
        assert new_control.replace('wrdata buffers.txt v(bx1) v(bx) v(by1) v(by)\n', '') == old.split('.control')[1]


@pytest.mark.parametrize('fault', ['columns', 'axis', 'time', 'nan'])
def test_buffer_trace_integrity_rejects_malformed(tmp_path, fault):
    t = np.arange(100) * 1e-12
    data = np.column_stack([a for _ in range(4) for a in (t, np.ones(len(t)))])
    if fault == 'columns':
        data = data[:, :-1]
    elif fault == 'axis':
        data[10, 2] += 1e-12
    elif fault == 'time':
        data[:, 0::2] += 1e-12
    else:
        data[10, 1] = np.nan
    path = tmp_path / 'buffers.txt'
    np.savetxt(path, data)
    with pytest.raises(ValueError):
        D.read_buffer_trace(path, t)


def test_buffer_trace_valid(tmp_path):
    t = np.arange(100) * 1e-12
    data = np.column_stack([a for _ in range(4) for a in (t, np.ones(len(t)))])
    path = tmp_path / 'buffers.txt'
    np.savetxt(path, data)
    assert np.array_equal(D.read_buffer_trace(path, t), np.ones((100, 4)))


@pytest.mark.parametrize('buffered', [False, True])
def test_cli_mode_explicit_default_unbuffered(monkeypatch, tmp_path, buffered):
    calls = []
    def fake_run(out, *, buffered=False):
        calls.append((out, buffered))
        return {'all_corner_block_pass': False}
    monkeypatch.setattr(E, 'run', fake_run)
    args = ['--out', str(tmp_path / 'not-created')]
    if buffered:
        args.append('--buffered')
    assert E.main(args) == 1
    assert calls == [(tmp_path / 'not-created', buffered)]
    assert not (tmp_path / 'not-created').exists()


def test_schedule_complete_block_pass_still_not_complete_dfe():
    calls = []
    def evaluate(width, corner, phase):
        calls.append((width, corner, phase))
        return {'block_pass': True}
    result = E.schedule(evaluate)
    assert len(calls) == 48 and result['selected_width_um'] == 4
    assert result['all_corner_block_pass']
    assert not result['hardware_dfe_complete'] and not result['full_receiver_verified']


def test_real_entry107_reproduces_and_separates_decision_from_hold():
    root = Path(__file__).resolve().parents[1] / 'product_audits/entry107_dfe_buffer_20260906'
    manifest = json.loads((root / 'evidence_sha256.json').read_text())
    for key, sha in manifest.items():
        assert E.digest(root / key) == sha
    config = json.loads((root / 'config.json').read_text())
    summary = json.loads((root / 'summary.json').read_text())
    assert config['entry'] == 107 and config['buffered']
    assert summary['spice_calls'] == 3 and summary['selected_width_um'] is None
    assert not summary['corners'] and not summary['all_corner_block_pass']
    for width in (4, 8, 16):
        folder = root / f'screen_w{width}_tt_1.00_27'
        saved = json.loads((folder / 'result.json').read_text())
        t, y = D.read_trace(folder / 'trace.txt')
        D.read_buffer_trace(folder / 'buffers.txt', t)
        actual = D.analyze(t, y, config['bits'], 1.8, saved['common_mode_v'])
        assert all(actual[key] == saved[key] for key in actual)
        assert actual['stimulus_valid'] and not actual['block_pass']
        assert sum(b['raw_min_logic_margin_v'] > 0 for b in actual['bits']) == 32
        assert sum(b['held_min_logic_margin_v'] > 0 for b in actual['bits']) == 15


def test_saved_buffer_diagnosis(tmp_path):
    from nebula.experiments.analyze_dfe_buffer import diagnose, plot_bit
    root = Path(__file__).resolve().parents[1] / 'product_audits/entry107_dfe_buffer_20260906'
    result = diagnose(root)
    assert result['spice_calls_added'] == 0 and len(result['screening']) == 3
    assert all(row['raw_correct_bits'] == 32 and row['held_correct_bits'] == 15
               for row in result['screening'])
    assert result['hardware_dfe_complete'] is False
    output = tmp_path / 'diagnostic.png'
    plot_bit(root, output)
    assert output.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')


def test_saved_buffer_diagnosis_rejects_tampered_manifest(tmp_path):
    from nebula.experiments.analyze_dfe_buffer import diagnose
    (tmp_path / 'file.txt').write_text('changed')
    (tmp_path / 'evidence_sha256.json').write_text(json.dumps({'file.txt': 'wrong'}))
    with pytest.raises(ValueError, match='hash'):
        diagnose(tmp_path)
