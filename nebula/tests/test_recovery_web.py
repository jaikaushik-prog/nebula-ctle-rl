"""Recovery app preserves failed evidence and publishes only complete outputs."""
import json
from copy import deepcopy
from pathlib import Path

import pytest


def _design():
    return json.loads(Path('nebula/product_demo/physical_bias_9db_1p9ghz_20260906/design.json').read_text())


def test_recovery_worker_uses_shared_complete_workflow(tmp_path, monkeypatch):
    from nebula.web import recovery_server as W
    from nebula.web.server import Job
    from nebula.llm.spec_parse import parse_request
    calls = []
    def workflow(text, out, **kwargs):
        calls.append((text, Path(out), kwargs))
        Path(out).mkdir()
        kwargs['progress']('Candidate 2: fresh verification', 60)
        d = deepcopy(_design())
        d['recovery'] = {'status': 'accepted', 'attempt_count': 2}
        return {'status': 'accepted', 'design': d,
                'written': ['design.json', 'design.cir', 'design_schematic.png'],
                'artifact_warnings': [], 'wall_s': 300.0,
                'delivered_success': True, 'output_complete': True}
    monkeypatch.setattr(W, 'run_request', workflow)
    app = W.RecoveryWebApp(run_root=tmp_path)
    job = Job('recovered', 'design')
    try:
        app._run_design(job, parse_request('6 dB at 2.1 GHz'), 'rl-physical')
        assert job.status == 'complete', job.error
        assert job.result['status'] == 'pass'
        assert calls[0][0] == '6 dB at 2.1 GHz'
        assert calls[0][1] == tmp_path / 'recovered'
        assert calls[0][2]['selection_mode'] == 'rl'
        assert calls[0][2]['max_candidates'] == 8
        assert job.result['recovery']['attempt_count'] == 2
        assert job.result['workflow_wall_s'] == 300.0
        assert job.result['wall_s'] == 300.0
    finally:
        app.close()


@pytest.mark.parametrize('status', ['no_eligible_candidates', 'export_failed', 'budget_exhausted'])
def test_recovery_worker_refuses_incomplete_output(tmp_path, monkeypatch, status):
    from nebula.web import recovery_server as W
    from nebula.web.server import Job
    from nebula.llm.spec_parse import parse_request
    def workflow(text, out, **kwargs):
        Path(out).mkdir()
        (Path(out) / 'workflow_receipt.json').write_text('{}')
        return {'status': status, 'design': None, 'written': [],
                'artifact_warnings': [], 'wall_s': 1.0,
                'delivered_success': False, 'output_complete': False}
    monkeypatch.setattr(W, 'run_request', workflow)
    app = W.RecoveryWebApp(run_root=tmp_path)
    job = Job('failed', 'design')
    try:
        app._run_design(job, parse_request('12 dB at 2.5 GHz'), 'rl-physical')
        assert job.status == 'failed'
        assert status in job.error
        assert app.design_dirs[job.id] == tmp_path / job.id
        assert (app.design_dirs[job.id] / 'workflow_receipt.json').is_file()
        assert job.id not in app.designs
    finally:
        app.close()


def test_saved_hybrid_route_remains_original(tmp_path, monkeypatch):
    from nebula.web import recovery_server as W
    from nebula.web.server import Job, NebulaWebApp
    from nebula.llm.spec_parse import parse_request
    calls = []
    monkeypatch.setattr(NebulaWebApp, '_run_design', lambda *a: calls.append(a))
    monkeypatch.setattr(W, 'run_request', lambda *a, **k: pytest.fail('physical workflow used for hybrid'))
    app = W.RecoveryWebApp(run_root=tmp_path)
    job = Job('hybrid', 'design')
    parsed = parse_request('9 dB at 1.9 GHz')
    try:
        app._run_design(job, parsed, 'rl-hybrid')
        assert calls == [(app, job, parsed, 'rl-hybrid')]
    finally:
        app.close()


def test_circuit_pass_does_not_hide_export_failure(tmp_path, monkeypatch):
    from nebula.web import recovery_server as W
    from nebula.web.server import Job
    from nebula.llm.spec_parse import parse_request
    def workflow(text, out, **kwargs):
        Path(out).mkdir()
        return {'status': 'export_or_acceptance_failed', 'design': _design(),
                'written': ['design.json'], 'artifact_warnings': ['schematic failed'],
                'wall_s': 1.0, 'delivered_success': False, 'output_complete': False}
    monkeypatch.setattr(W, 'run_request', workflow)
    app = W.RecoveryWebApp(run_root=tmp_path)
    job = Job('exportfailure', 'design')
    try:
        app._run_design(job, parse_request('9 dB at 1.9 GHz'), 'rl-physical')
        assert job.status == 'failed'
        assert 'schematic failed' in job.error
        assert job.id not in app.designs
    finally:
        app.close()


def test_saved_recovery_uses_complete_timing_and_rejects_changed_export(tmp_path):
    import hashlib
    from nebula.web.recovery_server import RecoveryWebApp
    run_id = 'a' * 32
    folder = tmp_path / run_id
    folder.mkdir()
    source = folder / 'design.json'
    source.write_text(json.dumps(_design()))
    receipt = {'output_complete': True, 'delivered_success': True, 'wall_s': 321.0,
               'status': 'accepted', 'selection_mode': 'rl', 'attempts': [1, 2],
               'spice_calls': 274,
               'artifact_sha256': {'design.json': hashlib.sha256(source.read_bytes()).hexdigest()}}
    (folder / 'workflow_receipt.json').write_text(json.dumps(receipt))
    app = RecoveryWebApp(run_root=tmp_path)
    try:
        assert app.designs[run_id]['wall_s'] == 321.0
        assert app.designs[run_id]['recovery']['spice_calls'] == 274
    finally:
        app.close()
    source.write_text(source.read_text() + ' ')
    app = RecoveryWebApp(run_root=tmp_path)
    try:
        assert run_id not in app.designs
        assert app.design_dirs[run_id] == folder
    finally:
        app.close()


def test_recovery_http_eye_uses_candidate_adapter(tmp_path, monkeypatch):
    from nebula.web import recovery_server as W
    from types import SimpleNamespace
    from urllib.request import urlopen
    import threading
    seen=[]
    monkeypatch.setattr(W, 'recovery_eye', lambda directory: seen.append(directory) or {'design_id': 'selected'})
    app=SimpleNamespace(design_dirs={'saved':tmp_path})
    server=W.make_server(app,'127.0.0.1',0)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with urlopen(f'http://127.0.0.1:{server.server_port}/api/eye/saved') as response:
            result=json.load(response)
        assert result=={'design_id':'selected','run_id':'saved'}
        assert seen==[tmp_path]
    finally:
        server.shutdown();server.server_close();thread.join()
