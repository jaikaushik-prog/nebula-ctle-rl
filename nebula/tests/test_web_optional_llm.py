"""Optional web LLM tests use injected clients; no network or simulator calls."""
import copy
import json
import threading
from pathlib import Path
from types import SimpleNamespace
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest

from nebula.web.optional_llm import LanguageAssistant, opt_in
from nebula.llm.spec_parse import SpecOutOfRange


class Stub:
    def __init__(self, text=None, error=None):
        self.text, self.error, self.calls, self.messages = text, error, [], self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(content=[SimpleNamespace(type='text', text=self.text)])


def physical():
    return json.loads(Path('nebula/product_demo/physical_bias_9db_1p9ghz_20260906/design.json').read_text())


def parsed_client(**extra):
    return Stub(json.dumps(dict(peaking_db=6, f_peak_hz=2.1e9,
                               peaking_stated=True, f_peak_stated=True, **extra)))


def test_default_no_provider_and_explicit_opt_in():
    client = Stub(error=AssertionError('provider must not run'))
    service = LanguageAssistant(client)
    assert service.parse('6 dB at 2.1 GHz').source == 'regex'
    assert service.explain(physical())['source'] == 'template'
    assert client.calls == []
    assert opt_in({}) is False
    with pytest.raises(ValueError):
        opt_in({'use_llm': 'false'})


def test_unavailable_is_visible_and_reveals_no_credentials(monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'secret-not-for-output')
    monkeypatch.setattr('nebula.web.optional_llm.importlib.util.find_spec', lambda name: None)
    service = LanguageAssistant()
    availability = service.availability()
    assert availability['available'] is False
    assert availability['provider_verified'] is False
    assert 'secret-not-for-output' not in json.dumps(availability)
    parsed = service.parse('6 dB at 2.1 GHz', True)
    assert parsed.source == 'regex'
    assert 'fallback' in ' '.join(parsed.notes)
    assert service.parsed_view(parsed, True)['label'] == 'Deterministic fallback'


def test_injected_parser_validates_target_but_cannot_select_method():
    client = parsed_client(method='library', setting=999, accepted=True)
    parsed = LanguageAssistant(client).parse('six decibels around two point one gigahertz', True)
    assert parsed.source == 'llm'
    assert parsed.target.peaking_db == 6
    assert parsed.target.f_peak_hz == 2.1e9
    assert not hasattr(parsed, 'method')
    schema = client.calls[0]['output_config']['format']['schema']
    assert schema['additionalProperties'] is False
    assert 'method' not in schema['properties']


@pytest.mark.parametrize('peaking,frequency', [(20, 2e9), (6, 9e9), (float('nan'), 2e9)])
def test_out_of_range_model_target_is_refused_without_retry(peaking, frequency):
    client = Stub(json.dumps({'peaking_db': peaking, 'f_peak_hz': frequency}))
    with pytest.raises(SpecOutOfRange):
        LanguageAssistant(client).parse('6 dB at 2.1 GHz', True)
    assert len(client.calls) == 1


def test_malformed_model_target_refused_with_sanitized_error():
    with pytest.raises(ValueError, match='invalid target'):
        LanguageAssistant(Stub('not-json-secret')).parse('6 dB at 2.1 GHz', True)


def test_provider_error_falls_back_without_exception_or_secret():
    service = LanguageAssistant(Stub(error=RuntimeError('Authorization: secret')))
    parsed = service.parse('6 dB at 2.1 GHz', True)
    assert parsed.source == 'regex'
    assert 'secret' not in json.dumps(parsed.as_dict())
    explanation = service.explain(physical(), True)
    assert explanation['source'] == 'template'
    assert 'fallback' in explanation['label']
    assert 'secret' not in json.dumps(explanation)


def test_physical_wording_grounded_and_never_mutates_acceptance():
    design = physical()
    original = copy.deepcopy(design)
    service = LanguageAssistant(Stub('The measured result is summarized by the fixed verification verdict.'))
    explanation = service.explain(design, True)
    assert explanation['source'] == 'llm'
    assert 'ideal DFE' in explanation['scope']
    assert explanation['verdict'] == service.explain(design)['verdict']
    assert design == original


def test_fabricated_number_discards_whole_wording():
    service = LanguageAssistant(Stub('The power is 987654321 mW.'))
    result = service.explain(physical(), True)
    assert result['source'] == 'template'
    assert '987654321' not in result['text']
    assert 'wording rejected' in result['label']


def test_sdk_client_has_bounded_timeout_and_no_retries(monkeypatch):
    import sys
    calls = []
    client = Stub('ok')
    monkeypatch.setitem(sys.modules, 'anthropic', SimpleNamespace(
        Anthropic=lambda **kwargs: calls.append(kwargs) or client))
    service = LanguageAssistant()
    monkeypatch.setattr(service, 'availability', lambda: {'available': True})
    monkeypatch.setenv('NEBULA_LLM_MODEL', 'configured-model')
    service._client().messages.create(model='old-model')
    assert calls == [{'timeout': 15.0, 'max_retries': 0}]
    assert client.calls == [{'model': 'configured-model'}]


def test_llm_generation_submits_only_validated_numeric_target(tmp_path, monkeypatch):
    from nebula.web import recovery_server as W
    calls = []
    def workflow(text, out, **kwargs):
        calls.append((text, kwargs))
        out.mkdir()
        return {'status': 'accepted', 'design': physical(), 'written': [],
                'output_complete': True, 'delivered_success': True, 'wall_s': 1.0}
    monkeypatch.setattr(W, 'run_request', workflow)
    app = W.RecoveryWebApp(run_root=tmp_path, language=LanguageAssistant(parsed_client(method='library')))
    class Immediate:
        def submit(self, fn, *args):
            fn(*args)
        def shutdown(self, **kwargs):
            pass
    app.executor.shutdown()
    app.executor = Immediate()
    try:
        job = app.start_design('six decibels around two point one gigahertz', 'rl-physical', True)
        assert job.status == 'complete', job.error
        assert calls[0][0] == '6 dB at 2.1000000000000001 GHz'
        assert calls[0][1]['selection_mode'] == 'rl'
        assert calls[0][1]['max_candidates'] == 8
        assert job.result['natural_language']['parsed_by'] == 'llm'
        saved = json.loads((tmp_path / job.id / 'language_request.json').read_text())
        assert saved['request'] == 'six decibels around two point one gigahertz'
    finally:
        app.close()


def test_http_availability_parse_and_explanation_default_offline(tmp_path):
    from nebula.web.recovery_server import RecoveryWebApp, make_server
    client = parsed_client()
    app = RecoveryWebApp(run_root=tmp_path, language=LanguageAssistant(client))
    app.demo()
    directory = tmp_path / 'physical'
    directory.mkdir()
    (directory / 'design.json').write_text(json.dumps(physical()))
    app.designs['physical'] = {}
    app.design_dirs['physical'] = directory
    server = make_server(app, '127.0.0.1', 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = f'http://127.0.0.1:{server.server_port}'
    def post(path, data):
        with urlopen(Request(root + path, data=json.dumps(data).encode(),
                             headers={'Content-Type': 'application/json'})) as response:
            return json.load(response)
    try:
        with urlopen(root + '/api/llm/availability') as response:
            assert json.load(response)['available'] is True
        assert post('/api/parse', {'request': '6 dB at 2.1 GHz'})['parsed_by'] == 'regex'
        assert client.calls == []
        explanation = post('/api/llm/explain', {'run_id': 'physical'})
        assert explanation['source'] == 'template'
        assert 'ideal DFE' in explanation['scope']
        assert client.calls == []
        assert post('/api/parse', {'request': 'six decibels', 'use_llm': True})['parsed_by'] == 'llm'
        with pytest.raises(HTTPError) as error:
            post('/api/design', {'request': '6 dB at 2.1 GHz', 'use_llm': 'false'})
        assert error.value.code == 400
        with pytest.raises(HTTPError):
            post('/api/llm/explain', {'run_id': '../design.json'})
    finally:
        server.shutdown(); server.server_close(); thread.join(); app.close()


def test_changed_saved_design_refuses_explanation(tmp_path):
    from nebula.web.recovery_server import RecoveryWebApp
    app = RecoveryWebApp(run_root=tmp_path)
    directory = tmp_path / 'saved'
    directory.mkdir()
    (directory / 'design.json').write_text(json.dumps(physical()))
    (directory / 'workflow_receipt.json').write_text(json.dumps({'artifact_sha256': {'design.json': 'wrong'}}))
    app.designs['saved'] = {}
    app.design_dirs['saved'] = directory
    try:
        with pytest.raises(ValueError, match='changed'):
            app.explain_design('saved', True)
    finally:
        app.close()


@pytest.mark.parametrize('malformed', [False, True])
def test_saved_parser_provenance_survives_restart(tmp_path, malformed):
    import hashlib
    from nebula.web.recovery_server import RecoveryWebApp
    directory = tmp_path / ('a' * 32)
    directory.mkdir()
    payload = json.dumps(physical()).encode()
    (directory / 'design.json').write_bytes(payload)
    (directory / 'workflow_receipt.json').write_text(json.dumps({
        'output_complete': True, 'delivered_success': True, 'wall_s': 1.0,
        'artifact_sha256': {'design.json': hashlib.sha256(payload).hexdigest()}}))
    provenance = {'parsed_by': 'llm', 'request': 'six decibels', 'notes': ['Provider parsing precedes workflow timing.']}
    (directory / 'language_request.json').write_text('invalid json' if malformed else json.dumps(provenance))
    app = RecoveryWebApp(run_root=tmp_path)
    try:
        assert 'a' * 32 in app.designs
        if not malformed:
            assert app.designs['a' * 32]['natural_language'] == provenance
        assert (directory / 'design.json').read_bytes() == payload
    finally:
        app.close()
