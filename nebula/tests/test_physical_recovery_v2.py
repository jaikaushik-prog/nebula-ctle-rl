"""Automatic recovery contracts; fake verifier only, never SPICE."""
import json
from contextlib import contextmanager
from copy import deepcopy

import pytest

from nebula import physical_recovery as R

REQUEST = {'peaking_db': 6., 'f_peak_hz': 2.1e9}


def test_order_registry_equal_and_no_duplicates():
    assert R.candidate_order([4, 2, 3], 'rl', nominal=3) == [3, 2, 4]
    assert R.candidate_order([4, 2, 3], 'classical', nominal=3) == [2, 3, 4]
    for mode in ('rl', 'classical'):
        assert R.candidate_order([4, 2, 3], mode, nominal=3, registered=4) == [4, 2, 3]
    assert R.candidate_order([2, 3], 'rl', nominal=8) == [2, 3]
    with pytest.raises(ValueError):
        R.candidate_order([2, 3], 'rl', registered=8)


@pytest.fixture
def harness(tmp_path, monkeypatch):
    monkeypatch.setattr(R, 'LOCK_FILE', tmp_path / 'global.lock')
    prepared = [({'setting': i}, {}) for i in (2, 3, 4)]
    monkeypatch.setattr(R, 'prepare', lambda *a: (prepared, {'eligible_settings': [2, 3, 4]}))
    monkeypatch.setattr(R.D, 'is_verified', lambda d: d.get('accepted', False))
    return tmp_path


def test_failure_then_success_bills_both_and_stops(harness, monkeypatch):
    calls = []
    def verify(pk, hz, *, evidence_dir, prepared_proposal):
        setting = prepared_proposal['search']['setting']
        calls.append(setting)
        evidence_dir.mkdir()
        return {'accepted': setting == 3, 'search': {'setting': setting},
                'simulations': {'total': 137}, 'verification': {'n_pass': 315 if setting == 3 else 314, 'n_points': 315}}
    monkeypatch.setattr(R.D, 'run', verify)
    result = R.run(REQUEST, harness / 'run')
    assert calls == [2, 3] and result['status'] == 'accepted'
    assert result['spice_calls'] == 274
    assert result['design']['search']['setting'] == 3
    assert result['design']['simulations']['total'] == 274
    assert len(result['attempts']) == 2
    assert json.loads((harness / 'run/recovery_receipt.json').read_text())['spice_calls'] == 274


def test_partial_exception_is_billed_and_next_candidate_is_fresh(harness, monkeypatch):
    def verify(pk, hz, *, evidence_dir, prepared_proposal):
        evidence_dir.mkdir()
        if prepared_proposal['search']['setting'] == 2:
            (evidence_dir / 'failure.json').write_text(json.dumps({'spice_calls': 17}))
            raise RuntimeError('instrument failed')
        return {'accepted': False, 'simulations': {'total': 137}, 'verification': {'n_pass': 314, 'n_points': 315}}
    monkeypatch.setattr(R.D, 'run', verify)
    result = R.run(REQUEST, harness / 'run', max_candidates=2)
    assert result['status'] == 'exhausted' and result['spice_calls'] == 154
    assert result['attempts'][0]['spice_calls'] == 17
    assert result['attempts'][0]['error'].startswith('RuntimeError:')
    assert result['design'] is not None


def test_no_eligible_returns_receipt_without_simulator(harness, monkeypatch):
    monkeypatch.setattr(R, 'prepare', lambda *a: ([], {'eligible_settings': []}))
    monkeypatch.setattr(R.D, 'run', lambda *a, **k: pytest.fail('no eligible candidate'))
    result = R.run(REQUEST, harness / 'run')
    assert result['status'] == 'no_eligible' and result['design'] is None
    assert result['spice_calls'] == 0 and not result['attempts']


def test_live_global_lock_refuses_without_deleting(harness, monkeypatch):
    R.LOCK_FILE.write_text('occupied')
    result = R.run(REQUEST, harness / 'run')
    assert result['status'] == 'busy' and result['spice_calls'] == 0
    assert R.LOCK_FILE.read_text() == 'occupied'


@pytest.mark.parametrize('maximum', [0, 9, 1.5, True])
def test_invalid_budget_rejected(harness, maximum):
    result = R.run(REQUEST, harness / 'run', max_candidates=maximum)
    assert result['status'] == 'rejected' and not result['attempts']


def test_rejects_diagnostic_loss_and_out_of_domain(harness):
    for i, request in enumerate((dict(REQUEST, channel_loss_db=7.5), dict(REQUEST, peaking_db=13.))):
        result = R.run(request, harness / str(i))
        assert result['status'] == 'rejected' and result['spice_calls'] == 0


def test_existing_output_refused(harness):
    with pytest.raises(FileExistsError):
        R.run(REQUEST, harness)


def test_classical_prepare_never_imports_or_calls_policy(monkeypatch):
    import builtins
    from types import SimpleNamespace
    class Table:
        settings = (2, 3, 4)
        corners = ('tt', 'ss')
        losses = (3., 4.5, 6., 7.5, 9., 10.5, 12.)
        def compliant_settings(self, *args): return (2, 3, 4)
    monkeypatch.setattr(R, 'load_bank', lambda: (Table(), [SimpleNamespace(u=[.1]*8)]*64, {}))
    monkeypatch.setattr(R.D, 'verified_physical_entry', lambda **k: {'setting': 4})
    monkeypatch.setattr(R, 'rl_proposal', lambda *a: pytest.fail('classical must not invoke policy'))
    original_import = builtins.__import__
    def guarded(name, *args, **kwargs):
        fromlist = kwargs.get('fromlist', args[2] if len(args)>2 else ()) or ()
        if 'hybrid_designer' in name or 'hybrid_designer' in fromlist:
            pytest.fail('classical imported policy module')
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded)
    proposals, metadata = R.prepare(REQUEST, 'classical')
    assert [s['setting'] for s, _ in proposals] == [4, 2, 3]
    assert metadata['rl_proposals'] == 0
    assert all(s['channel_losses_db'] == list(Table.losses) for s, _ in proposals)


def test_prepared_hook_bypasses_proposer_and_preserves_zero_call_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(R.D, '_snapshots', lambda *a: None)
    monkeypatch.setattr(R.D, 'propose', lambda *a, **k: pytest.fail('prepared path called proposer'))
    bad = {'request': dict(REQUEST, peaking_db=9.), 'search': {}, 'legacy': {}}
    folder = tmp_path / 'candidate'
    with pytest.raises(ValueError, match='request differs'):
        R.D.run(6., 2.1e9, evidence_dir=folder, prepared_proposal=bad)
    assert json.loads((folder/'failure.json').read_text())['spice_calls'] == 0
    assert json.loads((folder/'call_progress.json').read_text())['charged_invocations'] == 0


def test_prepared_hook_reaches_same_capture_without_policy(tmp_path, monkeypatch):
    from nebula.experiments.exp_joint_bank import LOSSES_DB
    monkeypatch.setattr(R.D, '_snapshots', lambda *a: None)
    monkeypatch.setattr(R.D, 'propose', lambda *a, **k: pytest.fail('prepared path called proposer'))
    def capture(search, folder):
        assert search['setting'] == 3
        raise RuntimeError('capture boundary reached')
    monkeypatch.setattr(R.D, 'capture_candidate', capture)
    prepared = {'request': REQUEST, 'search': {'setting': 3, 'fixed_eligible_settings': [3],
        'channel_losses_db': list(LOSSES_DB)}, 'legacy': {}}
    folder = tmp_path / 'candidate'
    with pytest.raises(RuntimeError, match='capture boundary'):
        R.D.run(6., 2.1e9, evidence_dir=folder, prepared_proposal=prepared)
    assert json.loads((folder/'failure.json').read_text())['spice_calls'] == 1
    counter = json.loads((folder/'call_progress.json').read_text())
    assert counter['charged_invocations'] == 1 and counter['invocation_state'] == 'exception'
    assert prepared['search']['setting'] == 3


def test_missing_call_receipt_is_fatal_not_zero_cost(harness, monkeypatch):
    def broken(*a, **k): raise RuntimeError('no durable count')
    monkeypatch.setattr(R.D, 'run', broken)
    result = R.run(REQUEST, harness/'run')
    assert result['status'] == 'fatal' and result['spice_calls'] is None
    assert not result['call_count_complete'] and len(result['attempts']) == 1
    assert result['design'] is None


def test_selection_exception_has_structured_receipt(harness, monkeypatch):
    def broken(*a): raise ValueError('source hash mismatch')
    monkeypatch.setattr(R, 'prepare', broken)
    result = R.run(REQUEST, harness/'run')
    assert result['status'] == 'error' and result['spice_calls'] == 0
    assert result['design'] is None and not result['attempts']
    assert result['selection_wall_s'] >= 0
    assert not R.LOCK_FILE.exists()


def test_progress_is_forwarded_and_recovery_alias_is_present(harness, monkeypatch):
    events = []
    def verify(pk, hz, *, evidence_dir, prepared_proposal, progress):
        progress('fresh verification', 50)
        return {'accepted': True, 'simulations': {'total': 137},
                'verification': {'n_pass': 315, 'n_points': 315}}
    monkeypatch.setattr(R.D, 'run', verify)
    result = R.run(REQUEST, harness/'run', progress=lambda *a: events.append(a))
    assert events == [('fresh verification', 50)]
    assert result['design']['recovery']['attempt_count'] == 1
    assert result['design']['recovery']['spice_calls'] == 137


def test_malformed_failure_receipt_is_retained_as_fatal(harness, monkeypatch):
    def broken(pk, hz, *, evidence_dir, prepared_proposal):
        evidence_dir.mkdir()
        (evidence_dir/'failure.json').write_text('invalid JSON')
        raise RuntimeError('failed before closeout')
    monkeypatch.setattr(R.D, 'run', broken)
    result = R.run(REQUEST, harness/'run')
    assert result['status'] == 'fatal' and len(result['attempts']) == 1
    assert result['attempts'][0]['spice_calls'] is None
    assert result['spice_calls'] is None


def test_durable_counter_zero_completion_and_atomic_failure(tmp_path, monkeypatch):
    from pathlib import Path
    R.D._record_call_progress(tmp_path, 0, 'created', 'none_charged', 0.)
    assert json.loads((tmp_path/'call_progress.json').read_text())['spice_calls'] == 0
    R.D._record_call_progress(tmp_path, 137, 'completed', 'verification_finished', 50.)
    saved = (tmp_path/'call_progress.json').read_bytes()
    counter = json.loads(saved)
    assert counter['charged_invocations'] == 137 and counter['invocation_state'] == 'verification_finished'
    assert 'not confirmation' in counter['count_scope']
    assert not (tmp_path/'call_progress.json.tmp').exists()
    def blocked(*a): raise OSError('interrupted replace')
    monkeypatch.setattr(Path, 'replace', blocked)
    with pytest.raises(OSError):
        R.D._record_call_progress(tmp_path, 138, 'invalid test update', 'potentially_active', 51.)
    assert (tmp_path/'call_progress.json').read_bytes() == saved


def test_progress_replace_transient_permission_error_retries_same_bytes(tmp_path, monkeypatch):
    from pathlib import Path
    original = Path.replace
    attempts, delays = [], []
    def transient(path, target):
        attempts.append(path.read_bytes())
        if len(attempts) < 3:
            raise PermissionError('temporary Windows sharing denial')
        return original(path, target)
    monkeypatch.setattr(Path, 'replace', transient)
    monkeypatch.setattr(R.D.time, 'sleep', delays.append)
    R.D._record_call_progress(tmp_path, 5, 'tt/ac_noise', 'potentially_active', 1.)
    assert len(attempts) == 3 and len(set(attempts)) == 1
    assert delays == [.05, .05]
    assert json.loads((tmp_path/'call_progress.json').read_text())['charged_invocations'] == 5
    assert not (tmp_path/'call_progress.json.tmp').exists()


def test_progress_replace_permanent_permission_error_is_bounded(tmp_path, monkeypatch):
    from pathlib import Path
    R.D._record_call_progress(tmp_path, 4, 'previous', 'potentially_active', 0.)
    previous = (tmp_path/'call_progress.json').read_bytes()
    attempts, delays = [], []
    error = PermissionError('permanent Windows sharing denial')
    def permanent(path, target):
        attempts.append(path.read_bytes())
        raise error
    monkeypatch.setattr(Path, 'replace', permanent)
    monkeypatch.setattr(R.D.time, 'sleep', delays.append)
    with pytest.raises(PermissionError) as failure:
        R.D._record_call_progress(tmp_path, 5, 'next', 'potentially_active', 1.)
    assert failure.value is error
    assert len(attempts) == 7 and len(set(attempts)) == 1
    assert delays == [.05]*6
    assert sum(delays) == pytest.approx(.3)
    assert (tmp_path/'call_progress.json').read_bytes() == previous
