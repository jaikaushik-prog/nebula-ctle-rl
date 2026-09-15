"""Bounded automatic recovery; old-bank proposals never certify physical hardware."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import time

from nebula import physical_design as D
from nebula.experiments.runlock import RunLockBusy, stamp

LOCK_FILE = D.ROOT / 'nebula/experiments/.physical_recovery.runlock.json'
MAX_CANDIDATES = 8


@contextmanager
def recovery_lock():
    """Atomic same-machine exclusion across outputs; never break another lock."""
    try:
        stream = LOCK_FILE.open('x', encoding='utf-8')
    except FileExistsError as exc:
        raise RunLockBusy('physical recovery is busy; existing lock retained') from exc
    try:
        with stream:
            json.dump(stamp(), stream)
        yield
    finally:
        LOCK_FILE.unlink()


def candidate_order(eligible, selection_mode, nominal=None, registered=None):
    if selection_mode not in ('rl', 'classical'):
        raise ValueError('selection_mode must be rl or classical')
    choices = sorted(set(map(int, eligible)))
    if registered is not None and registered not in choices:
        raise ValueError('registered candidate is not fixed eligible')
    first = registered if registered is not None else nominal if selection_mode == 'rl' and nominal in choices else None
    return ([int(first)] if first is not None else []) + [x for x in choices if x != first]


def validate_request(request):
    from nebula.rl.spec_dist import SpecTarget
    if request.get('channel_loss_db') is not None:
        raise ValueError('recovery requires the complete seven-channel family')
    target = SpecTarget(float(request['peaking_db']), float(request['f_peak_hz']))
    return {'peaking_db': target.peaking_db, 'f_peak_hz': target.f_peak_hz}


def load_bank():
    """Shared DEVELOPMENT table and geometry; no policy import or inference."""
    from nebula.experiments import exp_joint_bank as J, exp_joint_bank_73 as B
    from nebula.experiments import exp_margin_improve_controls as BASE
    from nebula.rl.margin_adapt_env import MarginBankTable
    if J._decoded_sha256(BASE.SOURCE) != BASE.SOURCE_SHA256:
        raise ValueError('fixed recovery source table hash mismatch')
    table = MarginBankTable.from_path(BASE.SOURCE)
    expected = {J._corner_label(c) for c in D.all_corners()}
    if set(table.corners) != expected or table.settings != list(range(512)) or tuple(table.losses) != tuple(J.LOSSES_DB):
        raise ValueError('fixed recovery table membership differs')
    _, _, base_u, hashes = B._load_sources()
    bank = J.bank(base_u, n_rs=J.N_RS, n_cs=J.N_CS, rs_span=J.RS_SPAN, cs_span=J.CS_SPAN)
    return table, bank, dict(hashes, table_decoded_sha256=BASE.SOURCE_SHA256)


def rl_proposal(request):
    from nebula.rl import hybrid_designer as H
    return H.solve(request['peaking_db'], request['f_peak_hz'])


def prepare(request, selection_mode):
    from nebula.experiments import exp_joint_bank as J, exp_joint_bank_73 as B
    table, bank, hashes = load_bank()
    candidate_order([], selection_mode)
    registered = D.verified_physical_entry(**request)
    try:
        _, eligible, checks = D.select_fixed_setting(
            table, (request['peaking_db'], request['f_peak_hz']), None, table.losses)
    except RuntimeError as exc:
        if 'no single fixed setting' not in str(exc):
            raise
        eligible, checks = [], len(table.settings) * len(table.corners) * len(table.losses)
    old = rl_proposal(request) if selection_mode == 'rl' and eligible else {
        'which_path': 'classical-fixed-intersection', 'rl_proposals': 0,
        'shield_verifier_calls': 0, 'sims': 0, 'reward': None}
    nominal = old.get('setting')
    order = candidate_order(eligible, selection_mode, nominal, registered['setting'] if registered else None)
    proposals = []
    for setting in order:
        atten, code = J.split_setting(setting)
        search = {k: deepcopy(v) for k, v in old.items() if not k.startswith('_')}
        search.update(u=list(bank[code].u), setting=setting, atten_code=atten, bank_code=code,
            atten_max_x=B.PROBE_MAX_X, reward=None, design_id=None,
            channel_losses_db=list(table.losses), representative_channel_loss_db=table.losses[len(table.losses)//2],
            channel_loss_mode='automatic-family', fixed_eligible_settings=eligible,
            fixed_prescreen_rows_checked=checks, legacy_nominal_setting=nominal,
            verified_physical_entry=registered, which_path=f'{selection_mode}-proposal/automatic-fixed-recovery/fresh-physical',
            fixed_selection_reason='verified-physical-registry' if registered and setting == registered['setting'] else
                'eligible-rl-nominal' if selection_mode == 'rl' and setting == nominal else 'ascending-fixed-eligible',
            selection_objective='fixed legacy intersection proposes; unchanged fresh physical electrical gate decides',
            evidence_warning='Old-bank measurements and registry select candidates only; no cached physical pass.')
        proposals.append((search, old))
    return proposals, {'eligible_settings': eligible, 'candidate_order': order,
        'legacy_nominal_setting': nominal, 'registered_setting': registered['setting'] if registered else None,
        'source_hashes': hashes, 'fixed_prescreen_rows_checked': checks,
        'rl_proposals': old.get('rl_proposals', 0), 'channel_losses_db': list(table.losses)}


def run(request, evidence_dir, selection_mode='rl', max_candidates=MAX_CANDIDATES, progress=None):
    """Return a receipt envelope and accepted/last-failed design, never reuse a pass."""
    started = time.perf_counter()
    out = Path(evidence_dir).resolve()
    out.mkdir(parents=True, exist_ok=False)
    receipt = dict(schema='nebula-physical-recovery-v1', selection_mode=selection_mode,
        status='error', max_candidates=max_candidates if isinstance(max_candidates, int) else repr(max_candidates), max_spice_calls=MAX_CANDIDATES * D.MAX_CALLS,
        attempts=[], spice_calls=0, known_spice_calls=0, call_count_complete=True,
        selection_wall_s=0., physical_wall_s=0., cached_physical_passes_used=False,
        same_candidate_retries=0, full_receiver_verified=False, **stamp())
    selected = None
    try:
        if isinstance(max_candidates, bool) or not isinstance(max_candidates, int) or not 1 <= max_candidates <= MAX_CANDIDATES:
            raise ValueError('max_candidates must be an integer in 1..8')
        candidate_order([], selection_mode)
        request = validate_request(request)
        receipt.update(request=request, max_spice_calls=max_candidates * D.MAX_CALLS)
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        receipt.update(status='rejected', error=f'{type(exc).__name__}: {exc}')
    else:
        try:
            with recovery_lock():
                inputs = out / 'inputs'; inputs.mkdir()
                for source in (Path(__file__), Path(D.__file__)):
                    shutil.copyfile(source, inputs / source.name)
                select_start = time.perf_counter()
                try:
                    proposals, metadata = prepare(request, selection_mode)
                finally:
                    receipt['selection_wall_s'] = time.perf_counter() - select_start
                receipt.update(metadata)
                D.P.write_json(out / 'selection.json', metadata)
                receipt['status'] = 'exhausted' if proposals else 'no_eligible'
                for index, (search, legacy) in enumerate(proposals[:max_candidates]):
                    folder = out / f'candidate_{index+1:02d}_setting_{search["setting"]}'
                    attempt = dict(setting=search['setting'], directory=str(folder), accepted=False)
                    begin = time.perf_counter()
                    try:
                        design = D.run(request['peaking_db'], request['f_peak_hz'], evidence_dir=folder, prepared_proposal={
                            'request': request, 'search': search, 'legacy': legacy},
                            **({'progress': progress} if progress is not None else {}))
                        selected = deepcopy(design)
                        attempt.update(accepted=D.is_verified(design), spice_calls=design['simulations']['total'],
                            n_pass=design['verification']['n_pass'], n_points=design['verification']['n_points'])
                    except Exception as exc:
                        failure = folder / 'failure.json'
                        try:
                            count = json.loads(failure.read_text(encoding='utf-8')).get('spice_calls') if failure.is_file() else None
                        except (ValueError, OSError):
                            count = None
                        attempt.update(error=f'{type(exc).__name__}: {exc}', spice_calls=count)
                    attempt['wall_s'] = time.perf_counter() - begin
                    receipt['physical_wall_s'] += attempt['wall_s']
                    receipt['attempts'].append(attempt)
                    count = attempt['spice_calls']
                    if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= D.MAX_CALLS:
                        attempt.update(accepted=False, spice_calls=None)
                        receipt.update(status='fatal', call_count_complete=False, spice_calls=None,
                            error='candidate exception has no trustworthy simulator-call receipt')
                        break
                    receipt['known_spice_calls'] += count
                    receipt['spice_calls'] = receipt['known_spice_calls']
                    D.P.write_json(out / 'progress.json', receipt)
                    if attempt['accepted']:
                        receipt['status'] = 'accepted'
                        break
        except RunLockBusy as exc:
            receipt.update(status='busy', error=str(exc))
        except Exception as exc:
            receipt.update(status='error', error=f'{type(exc).__name__}: {exc}')
    receipt['wall_s'] = time.perf_counter() - started
    if selected is not None:
        candidate_calls = selected['simulations']['total']
        selected['simulations']['recovery_other_attempts'] = receipt['known_spice_calls'] - candidate_calls
        selected['simulations']['total'] = receipt['spice_calls']
        selected['recovery'] = {'status': receipt['status'], 'attempt_count': len(receipt['attempts']),
            'spice_calls': receipt['spice_calls'], 'selection_mode': selection_mode}
        selected['recovery_receipt'] = deepcopy(receipt)
        selected['wall_s'] = receipt['wall_s']
    D.P.write_json(out / 'recovery_receipt.json', receipt)
    result = dict(receipt, design=selected, recovery_receipt=deepcopy(receipt))
    D.P.write_json(out / 'result.json', result)
    D.P.write_json(out / 'evidence_sha256.json', {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in out.rglob('*') if p.is_file()})
    return result
