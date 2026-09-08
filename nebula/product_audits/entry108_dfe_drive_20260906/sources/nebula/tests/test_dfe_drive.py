"""Entry 108: approved buffer-only dimensions and bounded selection."""
from pathlib import Path

import pytest

from nebula.common.types import Corner
from nebula.device import dfe_hardware as D
from nebula.link.config import LinkConfig


@pytest.mark.parametrize('pair', [(8, 8), (8, 16), (16, 8), (16, 16)])
def test_only_four_buffer_widths_and_fingers_change(pair):
    before = {line.split()[0]: line.split() for line in D.dut_lines(4, buffered=True)}
    after = {line.split()[0]: line.split() for line in
             D.dut_lines(4, buffered=True, buffer_drive_um=pair)}
    changed = {'Xbuf_x1_p': pair[0], 'Xbuf_y1_p': pair[0],
               'Xbuf_x2_n': pair[1], 'Xbuf_y2_n': pair[1]}
    assert before.keys() == after.keys() and len(after) == 27
    for name, fields in before.items():
        if name in changed:
            fields[6] = f'w={changed[name]}'
            fields[8] = f'nf={changed[name] // 2}'
        assert fields == after[name]
    geometry = D.geometry(4, buffered=True, buffer_drive_um=pair)
    assert geometry['mos_count'] == 27 and geometry['full_area_mm2'] is None
    expected = sum(float(fields[6].split('=')[1]) * .15 for fields in after.values()) / 1e6
    assert geometry['gate_geometry_mm2'] == pytest.approx(expected)


@pytest.mark.parametrize('width,buffered,pair', [(8, True, (8, 8)), (4, False, (8, 8)),
                          (4, True, (4, 8)), (4, True, (8, 32)), (4, True, (8,)),
                          (4, True, (float('nan'), 8))])
def test_unapproved_drive_rejected(width, buffered, pair):
    with pytest.raises(ValueError):
        D.dut_lines(width, buffered=buffered, buffer_drive_um=pair)


def test_targeted_deck_preserves_stimulus_and_measurement():
    bits = D.pattern(LinkConfig(channel_loss_db_at_nyquist=7.5))
    old = D.deck(4, Corner('tt', 1, 27), 1.36, bits, buffered=True)
    new = D.deck(4, Corner('tt', 1, 27), 1.36, bits, buffered=True, buffer_drive_um=(8, 16))
    assert new.split('.control')[1] == old.split('.control')[1]
    assert new.split('Xin1')[0].split('\n', 1)[1] == old.split('Xin1')[0].split('\n', 1)[1]
    assert '* Entry 108:' in new


def test_no_passing_complete_gate_stops_after_four():
    from nebula.experiments.exp_dfe_drive import schedule
    calls = []
    def evaluate(pair, corner, phase):
        calls.append((pair, corner, phase))
        return {'block_pass': False, 'raw_correct_bits': 32}
    result = schedule(evaluate)
    assert len(calls) == 4 and result['selected_drive_um'] is None
    assert not result['all_corner_block_pass'] and not result['corners']


def test_tie_break_fixed_no_reselection_after_pvt_failure():
    from nebula.experiments.exp_dfe_drive import schedule
    calls = []
    def evaluate(pair, corner, phase):
        calls.append((pair, corner, phase))
        return {'block_pass': pair != (8, 8) and phase == 'screen'}
    result = schedule(evaluate)
    assert len(calls) == 49 and result['selected_drive_um'] == (8, 16)
    assert {pair for pair, _, phase in calls if phase == 'pvt'} == {(8, 16)}
    assert not result['all_corner_block_pass']


def test_full_block_pass_does_not_claim_dfe_or_receiver():
    from nebula.experiments.exp_dfe_drive import schedule
    result = schedule(lambda pair, corner, phase: {'block_pass': True})
    assert result['selected_drive_um'] == (8, 8) and result['all_corner_block_pass']
    assert len(result['corners']) == 45
    assert not result['hardware_dfe_complete'] and not result['full_receiver_verified']


def test_exact_signature_ignores_only_testbench_not_mos_change():
    from nebula.experiments.exp_dfe_drive import mos_signature
    bits = D.pattern(LinkConfig(channel_loss_db_at_nyquist=7.5))
    a = D.deck(4, Corner('tt', 1, 27), 1.36, bits, buffered=True, buffer_drive_um=(8, 8))
    b = D.deck(4, Corner('ss', .95, 125), 1.25, bits, buffered=True, buffer_drive_um=(8, 8))
    assert mos_signature(a) == mos_signature(b)
    assert mos_signature(a) != mos_signature(a.replace('w=8', 'w=16', 1))


def test_simulator_failure_is_saved_without_retry(tmp_path, monkeypatch):
    from nebula.experiments import exp_dfe_drive as E
    calls = []
    def fail(deck, folder):
        calls.append(folder)
        folder.mkdir()
        (folder / 'design.cir').write_text(deck, encoding='ascii')
        (folder / 'ngspice.log').write_text('Error: deliberately injected by unit test')
        raise ValueError('unit-test simulator failure')
    monkeypatch.setattr(E.P, 'invoke', fail)
    result = E.run(tmp_path / 'unit-test-only')
    assert len(calls) == 4 and result['spice_calls'] == 4
    assert result['selected_drive_um'] is None
    for folder in calls:
        assert (folder / 'result.json').exists() and (folder / 'ngspice.log').exists()
    assert (tmp_path / 'unit-test-only/evidence_sha256.json').exists()
