"""Entry 110: exact existing buffers/memory and unchanged clean control."""
import json
from pathlib import Path

import numpy as np
import pytest

from nebula.device import dfe_hardware as D, dfe_memory_probe as M
from nebula.experiments import exp_dfe_memory as E
from nebula.link.config import LinkConfig


def bits():
    return D.pattern(LinkConfig(channel_loss_db_at_nyquist=7.5))


def test_exact_sixteen_existing_mos_and_area():
    lines = M.buffer_memory_lines()
    assert lines == D.dut_lines(4, buffered=True)[11:]
    assert lines[-8:] == M.memory_lines() and len(lines) == 16
    g = M.geometry(with_buffers=True)
    assert g['mos_count'] == 16
    assert g['gate_geometry_mm2'] == pytest.approx(16*4*.15/1e6)
    assert g['full_area_mm2'] is None


def test_clean_sources_drive_raw_inputs_not_memory():
    old = M.deck(bits())
    new = M.deck(bits(), with_buffers=True)
    assert 'Vset x 0 PWL(' in new and 'Vreset y 0 PWL(' in new
    assert 'Vset bx ' not in new and 'Vreset by ' not in new
    assert 'wrdata trace.txt v(x) v(y) v(q) v(qb) i(vdd) i(vset) i(vreset)' in new
    assert 'wrdata buffers.txt v(bx1) v(bx) v(by1) v(by)' in new
    assert [l for l in new.splitlines() if l.startswith('+')] == [l for l in old.splitlines() if l.startswith('+')]
    assert [l for l in new.splitlines() if l.startswith('X')] == M.buffer_memory_lines()
    assert '.ic ' not in new and '.model' not in new and 'Vclk' not in new


@pytest.mark.parametrize('pass_result', [True, False])
def test_one_call_even_if_pass_no_pvt(tmp_path, monkeypatch, pass_result):
    calls = []
    def invoke(deck, folder):
        calls.append(folder)
        folder.mkdir()
        (folder/'design.cir').write_text(deck, encoding='ascii')
    monkeypatch.setattr(E.P, 'invoke', invoke)
    monkeypatch.setattr(M, 'read_trace', lambda path: (np.array([0., 1.]), np.zeros((2,7))))
    monkeypatch.setattr(M, 'analyze', lambda *args: {'memory_hold_pass':pass_result,
        'hardware_dfe_complete':False,'full_receiver_verified':False})
    monkeypatch.setattr(D, 'read_buffer_trace', lambda *args: np.zeros((2,4)))
    out = tmp_path/'test-only'
    r = E.run(out, with_buffers=True)
    assert r['entry'] == 110 and r['spice_calls'] == len(calls) == 1
    assert r['memory_hold_pass'] == pass_result and r['buffer_trace_valid']
    assert not r['hardware_dfe_complete'] and not r['full_receiver_verified']
    cfg = json.loads((out/'config.json').read_text())
    assert cfg['buffers_connected'] and not cfg['comparator_connected']
    assert cfg['max_calls'] == 1 and cfg['bits'] == bits().tolist()


@pytest.mark.parametrize('fault', ['simulator', 'auxiliary'])
def test_failures_keep_evidence_and_do_not_retry(tmp_path, monkeypatch, fault):
    calls = []
    def invoke(deck, folder):
        calls.append(folder)
        folder.mkdir()
        (folder/'design.cir').write_text(deck, encoding='ascii')
        (folder/'ngspice.log').write_text('injected unit-test evidence')
        if fault == 'simulator':
            raise ValueError('injected simulator failure')
    monkeypatch.setattr(E.P, 'invoke', invoke)
    monkeypatch.setattr(M, 'read_trace', lambda path: (np.array([0.,1.]), np.zeros((2,7))))
    monkeypatch.setattr(M, 'analyze', lambda *args: {'memory_hold_pass':True})
    def bad_aux(*args):
        raise ValueError('injected auxiliary time mismatch')
    monkeypatch.setattr(D, 'read_buffer_trace', bad_aux)
    out = tmp_path/'test-only'
    r = E.run(out, with_buffers=True)
    assert r['spice_calls'] == len(calls) == 1 and not r['memory_hold_pass']
    assert not r['instrument_ok'] and (calls[0]/'ngspice.log').exists()
    for key, sha in json.loads((out/'evidence_sha256.json').read_text()).items():
        assert E.digest(out/key) == sha
    with pytest.raises(FileExistsError):
        E.run(out, with_buffers=True)


def test_legacy_deck_remains_byte_equivalent():
    folder = Path(__file__).resolve().parents[1]/'product_audits/entry109_dfe_memory_20260906'
    cfg = json.loads((folder/'config.json').read_text())
    assert M.deck(cfg['bits'], with_buffers=False) == (folder/'clean_tt_1.00_27/design.cir').read_text()
