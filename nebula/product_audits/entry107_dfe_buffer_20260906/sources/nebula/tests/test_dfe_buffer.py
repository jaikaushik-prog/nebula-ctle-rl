"""Entry 107: exact buffered delta, same measurements, legacy preserved."""
from pathlib import Path
import json

import numpy as np
import pytest

from nebula.device import dfe_hardware as D
from nebula.experiments import exp_dfe_slicer as E
from nebula.common.types import Corner
from nebula.link.config import LinkConfig


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
