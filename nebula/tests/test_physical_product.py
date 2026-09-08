"""Product boundaries: old-bank proposals cannot certify new hardware."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from nebula import physical_design as F


class Table:
    settings = (1, 2, 3)
    corners = ('tt/1.00/27C', 'ss/0.95/125C')
    losses = (3., 12.)

    def compliant_settings(self, corner, loss, *request):
        return (1, 2) if corner.startswith('tt') else (2, 3)


def test_fixed_intersection_is_one_setting_not_an_adaptive_map():
    assert F.select_fixed_setting(Table(), (9., 1.9e9), 1, Table.losses) == (2, [2], 12)


def test_keep_nominal_if_eligible_and_refuse_empty_intersection():
    table = Table()
    table.compliant_settings = lambda *a: (1, 2)
    assert F.select_fixed_setting(table, (9., 1.9e9), 2, table.losses)[0] == 2
    table.compliant_settings = lambda c, *a: (1,) if c.startswith('tt') else (3,)
    with pytest.raises(RuntimeError, match='no single fixed'):
        F.select_fixed_setting(table, (9., 1.9e9), 1, table.losses)


def test_physical_mode_requires_new_evidence_directory_before_search(tmp_path, monkeypatch):
    import nebula.design as D
    monkeypatch.setattr(F, 'propose', lambda *a: pytest.fail('must refuse before search'))
    with pytest.raises(ValueError, match='evidence directory'):
        D.design(9, 1.9e9, method='rl-physical')
    with pytest.raises(FileExistsError):
        D.design(9, 1.9e9, method='rl-physical', evidence_dir=tmp_path)


def test_physical_scope_does_not_claim_adaptive_or_full_area():
    from nebula.report.product_scope import implementation_scope
    scope = implementation_scope({'method': 'rl-physical'})
    assert 'one unchanged' in scope['verification_note']
    assert 'reference' in scope['power_scope']
    assert not scope['full_product_compliance']
    assert scope['area_status'] == 'NOT_VERIFIED'


def test_old_bank_pass_cannot_certify_pending_physical_result():
    from nebula.tests.test_web_app import _design
    from nebula.web.server import present_design
    d = _design()
    d['method'] = 'rl-physical'
    assert present_design('pending', d, source='live-run')['status'] == 'fail'


def test_physical_output_reuses_exact_deck_and_refuses_changed_hash(tmp_path, monkeypatch):
    import hashlib
    import nebula.design as D
    monkeypatch.setattr(D, 'netlist_for', lambda *a, **k: pytest.fail('must not export ideal deck'))
    path = tmp_path / 'design.cir'
    path.write_text('physical exact')
    d = {'method': 'rl-physical', 'physical_evidence': {
        'directory': str(tmp_path), 'deck_sha256': hashlib.sha256(path.read_bytes()).hexdigest()},
         'simulations': {'total': 137}}
    assert D.prepare_output_deck(d) == 'physical exact'
    assert d['simulations'] == {'total': 137}
    path.write_text('changed')
    with pytest.raises(ValueError, match='hash'):
        D.prepare_output_deck(d)


def test_physical_cli_requires_out():
    import nebula.design as D
    with pytest.raises(SystemExit) as exc:
        D.main(['--method', 'rl-physical', '--peaking', '9', '--f-peak', '1.9'])
    assert exc.value.code == 2


def test_physical_schematic_checks_ordered_pins_and_all_physical_instances(tmp_path):
    from nebula.report.physical_schematic import physical_components, draw_physical_schematic
    source = Path(__file__).resolve().parents[1] / 'product_audits/entry103_physical_bias_20260906/design.cir'
    deck = source.read_text()
    assert len([k for k in physical_components(deck) if k.startswith('x')]) == 27
    swapped = deck.replace('Xbpfeed nbias p_bias vdd vdd', 'Xbpfeed p_bias nbias vdd vdd')
    with pytest.raises(ValueError, match='ordered connectivity'):
        physical_components(swapped)
    extra = deck.replace('.control', 'Iref vdd nbias 1e-6\n.control')
    with pytest.raises(ValueError, match='unrepresented'):
        physical_components(extra)
    assert draw_physical_schematic(deck, tmp_path / 'physical.png').stat().st_size > 50000


def test_web_rejects_unknown_mode_before_enqueuing(tmp_path):
    from nebula.web.server import NebulaWebApp
    app = NebulaWebApp(run_root=tmp_path)
    try:
        with pytest.raises(ValueError, match='Unknown design mode'):
            app.start_design('9 dB at 1.9 GHz', method='typo')
        assert not app.jobs
    finally:
        app.close()


def test_bundle_contains_nested_raw_evidence(tmp_path):
    import io
    import zipfile
    from nebula.web.server import NebulaWebApp
    app = NebulaWebApp(run_root=tmp_path)
    try:
        folder = tmp_path / 'run'
        raw = folder / 'physical_evidence' / 'tt' / 'ngspice.log'
        raw.parent.mkdir(parents=True)
        raw.write_text('raw')
        app.design_dirs['run'] = folder
        with zipfile.ZipFile(io.BytesIO(app.evidence_zip('run'))) as archive:
            assert archive.read('physical_evidence/tt/ngspice.log') == b'raw'
    finally:
        app.close()


@pytest.mark.parametrize('mode', ['rl-hybrid', 'rl-physical'])
def test_http_design_passes_selected_mode_to_worker(mode):
    from types import SimpleNamespace
    from nebula.web.server import _Handler, Job
    handler = object.__new__(_Handler)
    handler.path = '/api/design'
    handler._json_body = lambda: {'request': '9 dB at 1.9 GHz', 'method': mode}
    calls = []
    handler.app = SimpleNamespace(start_design=lambda text, **kwargs: (calls.append((text, kwargs)) or Job('x', 'design')))
    handler._json = lambda *args: None
    handler.do_POST()
    assert calls == [('9 dB at 1.9 GHz', {'method': mode})]


def test_real_physical_artifact_passes_but_missing_or_changed_condition_fails():
    from nebula.web.server import present_design
    path = Path('nebula/product_demo/physical_bias_9db_1p9ghz_20260906/design.json')
    d = json.loads(path.read_text())
    assert F.is_verified(d)
    shown = present_design('physical', d, source='preverified-demo')
    assert shown['status'] == 'pass'
    assert next(r for r in shown['specs'] if r['key'] == 'area_mm2')['label'] == 'Counted geometry subtotal'
    assert next(r for r in shown['specs'] if r['key'] == 'area_mm2')['status'] is None
    for change in ('missing', 'different-circuit', 'failed', 'control'):
        bad = deepcopy(d)
        if change == 'missing':
            bad['verification']['per_condition'].pop()
        elif change == 'different-circuit':
            bad['verification']['per_condition'][0]['circuit_signature'] = 'different'
        elif change == 'failed':
            bad['verification']['per_condition'][0]['compliant'] = False
        else:
            bad['product_readiness_audit']['fixed']['dfe_control_all_pass'] = False
        assert not F.is_verified(bad)
        assert present_design('bad', bad, source='live-run')['status'] == 'fail'


def test_physical_web_worker_uses_evidence_mode_not_legacy_explainer(tmp_path, monkeypatch):
    import nebula.design as D
    from nebula.web.server import NebulaWebApp, Job
    from nebula.llm.spec_parse import parse_request
    d = json.loads(Path('nebula/product_demo/physical_bias_9db_1p9ghz_20260906/design.json').read_text())
    calls = []
    def fake_design(db, hz, **kwargs):
        calls.append(kwargs)
        kwargs['progress']('fresh 45/45', 80)
        return deepcopy(d)
    monkeypatch.setattr(D, 'design', fake_design)
    monkeypatch.setattr(D, 'write_outputs', lambda *a, **k: ([], []))
    import nebula.llm.explanation as explanation
    monkeypatch.setattr(explanation, 'explain', lambda *a, **k: pytest.fail('old bank explanation must not run'))
    app = NebulaWebApp(run_root=tmp_path)
    job = Job('physical', 'design')
    try:
        app._run_design(job, parse_request('9 dB at 1.9 GHz'), 'rl-physical')
        assert job.status == 'complete', job.error
        assert job.result['status'] == 'pass'
        assert calls[0]['method'] == 'rl-physical'
        assert calls[0]['evidence_dir'] == tmp_path / 'physical/physical_evidence'
        assert job.result['explanation']['source'] == 'physical-evidence-template'
    finally:
        app.close()
