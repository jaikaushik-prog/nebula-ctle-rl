"""Entry 123 schedules and lossless preservation; mocks are test-only."""
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from nebula.experiments import exp_dfe_cml as E


def test_recovery_screen_and_fixed_pvt():
    calls = []
    def evaluate(w, corner, phase):
        calls.append((w, corner, phase))
        return {'block_pass': w == 16, 'voltage_audit': {'documented_ranges_ok': True}}
    r = E.recovery_schedule(evaluate)
    assert len(calls) == 51 and r['selected_width_um'] == 16
    assert all(w == 16 for w, _, _ in calls[6:])
    assert r['standalone_pvt_pass'] and not r['hardware_dfe_complete']


def test_failed_recovery_does_not_expand():
    calls = []
    def evaluate(*args):
        calls.append(args)
        return {'block_pass': False}
    r = E.recovery_schedule(evaluate)
    assert len(calls) == 6 and r['selected_width_um'] is None and not r['pvt']


def test_archive_is_lossless_no_overwrite(tmp_path):
    from nebula.experiments.archive_traces import archive
    raw = tmp_path/'point'/'trace.txt'
    raw.parent.mkdir()
    raw.write_bytes(b'1.00 2.00\r\n' * 10)
    sha = hashlib.sha256(raw.read_bytes()).hexdigest()
    (tmp_path/'evidence_sha256.json').write_text(json.dumps({'point/trace.txt': sha}))
    result = archive(tmp_path)
    assert raw.exists() and gzip.decompress(raw.with_suffix('.txt.gz').read_bytes()) == raw.read_bytes()
    assert result['raw_bytes_preserved'] and len(result['archives']) == 1
    with pytest.raises(FileExistsError):
        archive(tmp_path)


def test_archive_rejects_changed_evidence(tmp_path):
    from nebula.experiments.archive_traces import archive
    (tmp_path/'trace.txt').write_bytes(b'changed')
    (tmp_path/'evidence_sha256.json').write_text(json.dumps({'trace.txt': '0'*64}))
    with pytest.raises(ValueError, match='hash'):
        archive(tmp_path)


def test_archive_rejects_escape(tmp_path):
    from nebula.experiments.archive_traces import archive
    (tmp_path/'evidence_sha256.json').write_text(json.dumps({'../trace.txt': '0'*64}))
    with pytest.raises(ValueError):
        archive(tmp_path)


@pytest.mark.parametrize('directory,files,traces,calls,width,passes', [
    ('entry122_dfe_cml_20260909',354,96,48,4,34),
    ('entry123_dfe_cml_recovery_20260909',377,102,51,8,45)])
def test_real_cml_reproduces_all_corners_from_archived_traces(directory, files, traces, calls, width, passes):
    from nebula.common.types import Corner
    from nebula.device import dfe_cml as C, dfe_hardware as D, dfe_voltage_audit as V
    root = Path(__file__).resolve().parents[1]/'product_audits'/directory
    config = json.loads((root/'config.json').read_text())
    summary = json.loads((root/'summary.json').read_text())
    manifest = json.loads((root/'evidence_sha256.json').read_text())
    archives = json.loads((root/'trace_archives.json').read_text())
    assert E.digest(root/'evidence_sha256.json') == archives['original_manifest_sha256']
    by_raw = {r['raw']: r for r in archives['archives']}
    assert len(manifest) == files and len(by_raw) == traces
    for key, expected in manifest.items():
        if key in by_raw:
            row = by_raw[key]
            compressed = (root/row['gzip']).read_bytes()
            assert hashlib.sha256(compressed).hexdigest() == row['gzip_sha256']
            assert hashlib.sha256(gzip.decompress(compressed)).hexdigest() == expected == row['raw_sha256']
        else:
            assert E.digest(root/key) == expected
    assert summary['spice_calls'] == calls and summary['selected_width_um'] == width
    assert summary['standalone_pvt_pass'] == (passes == 45)
    assert sum(r['result']['block_pass'] for r in summary['pvt']) == passes
    for folder in sorted(root.glob('*_w*')):
        saved = json.loads((folder/'result.json').read_text())
        key = saved['common_mode_source_key'].split('/')[0].split('_')
        corner = Corner(key[0], float(key[1]), float(key[2]))
        t, y = C.read_trace(folder/'trace.txt.gz')
        result = C.analyze(t, y, config['bits'], 1.8*corner.vdd_scale, saved['common_mode_v'])
        assert all(value == saved[k] for k, value in result.items())
        mos = C.mos_lines(saved['width_um'])
        nodes = V.read_nodes(folder/'terminals.txt.gz', D.terminal_nodes(mos), t)
        assert V.audit(mos, nodes) == saved['voltage_audit']
        assert saved['voltage_audit']['documented_ranges_ok']
        assert (folder/'design.cir').read_text() == C.deck(saved['width_um'], corner,
                                                       saved['common_mode_v'], config['bits'])
