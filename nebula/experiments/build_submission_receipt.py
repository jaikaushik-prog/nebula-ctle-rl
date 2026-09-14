"""Build a receipt from one frozen production run; never simulate or replay PPO."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = 'nebula/product_demo/rl_hybrid_9db_1p9ghz/design.json'
SOURCE_SHA256 = '906bcedce089909acf3504462fad6270d8712a6f9f2c521ef35df356c694e4f3'
DEFAULT_OUT = ROOT / 'nebula/results/submission_receipt_20260914'


def checked_bytes(path: Path, expected: str) -> bytes:
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected.lower():
        raise ValueError(f'source hash mismatch: {path.name}')
    return data


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def _elapsed(value):
    if value is None:
        return None
    value = float(value)
    _require(math.isfinite(value) and value >= 0, 'invalid elapsed time')
    return value


def receipt_model(design: dict) -> dict:
    _require(design['method'] == 'rl-hybrid', 'requires actual rl-hybrid record')
    v, s = design['verification'], design['search']
    rows = v['per_condition']
    losses = set(v['channel_losses_db'])
    corners = {r['corner'] for r in rows}
    identities = [(r['channel_loss_db'], r['corner']) for r in rows]
    expected = {(loss, corner) for loss in losses for corner in corners}
    _require(len(set(identities)) == len(identities) and set(identities) == expected,
             'duplicate or incomplete condition matrix')
    _require(len(rows) == v['n_points'] == v['n_corners'] * v['n_channel_losses'],
             'condition counts disagree')
    _require(len(corners) == v['n_corners'] and len(losses) == v['n_channel_losses'],
             'axes disagree')
    for row in rows:
        t = row['policy_trace']
        tried, measured, actions = t['settings_tried'], t['measurements'], t['actions']
        _require(1 <= len(tried) <= 8 and len(tried) == len(measured), 'invalid trace')
        _require(tried[0] == t['start_setting'] and tried[-1] == t['locked_setting'],
                 'trace endpoints disagree')
        _require(row['rl_measurements'] == row['verifier_calls'] == len(tried),
                 'trace billing mismatch')
        moves = actions[:-1] if actions and actions[-1] == 'lock' else actions
        _require(len(moves) == len(tried)-1, 'action count disagrees')
        for before, after, action in zip(tried, tried[1:], moves):
            a, r, c = before // 64, before % 64 // 8, before % 8
            delta = {'atten_down':(-1,0,0),'atten_up':(1,0,0),
                     'rs_down':(0,-1,0),'rs_up':(0,1,0),
                     'cs_down':(0,0,-1),'cs_up':(0,0,1)}.get(action)
            _require(delta is not None, 'unknown policy action')
            code = tuple(x+y for x,y in zip((a,r,c),delta))
            _require(all(0 <= x < 8 for x in code) and
                     after == code[0]*64+code[1]*8+code[2], 'policy action mismatch')
        _require(all(type(x) is int and 0 <= x < 512 for x in tried), 'invalid code')
        for m in measured:
            _require(type(m['link_valid']) is bool, 'invalid link flag')
            _require(all(math.isfinite(float(m[k])) for k in ('eye_h_v','eye_w_ui')),
                     'nonfinite trace measurement')
        if row['source'] == 'rl-shield':
            _require(row['setting'] in tried and row['selection_reason'] in
                     ('safe-rl-proposal-well-centred','target-refinement-kept-rl'),
                     'selection attribution mismatch')
        elif row['source'] == 'bank-fallback':
            _require(row['setting'] not in tried and row['selection_reason'] in
                     ('target-refinement','no-compliant-rl-proposal'),
                     'fallback was inserted into actor trace')
        else:
            raise ValueError('unsupported selection source')
    counts = {
        'conditions':len(rows), 'passed':sum(r['compliant'] for r in rows),
        'billed_visits':sum(r['rl_measurements'] for r in rows),
        'fixed_start_visits':len(rows),
        'policy_move_visits':sum(len(r['policy_trace']['settings_tried'])-1 for r in rows),
        'verifier_calls':sum(r['verifier_calls'] for r in rows),
        'bank_rows_checked':sum(r['bank_rows_checked'] for r in rows),
        'bank_selected':sum(r['source']=='bank-fallback' for r in rows),
        'rl_shield_selected':sum(r['source']=='rl-shield' for r in rows),
        'target_refinements':sum(r['selection_reason']=='target-refinement' for r in rows),
        'safety_recoveries':sum(r['selection_reason']=='no-compliant-rl-proposal' for r in rows),
    }
    for key, source in [('billed_visits','rl_proposals'),('verifier_calls','shield_verifier_calls'),
                        ('bank_rows_checked','table_rows_checked'),('bank_selected','shield_fallbacks'),
                        ('target_refinements','target_refinements'),('safety_recoveries','safety_fallbacks')]:
        _require(counts[key] == s[source], 'aggregate counts disagree')
    _require(counts['passed'] == v['n_pass'], 'pass counts disagree')
    recovery = next(r for r in rows if r['selection_reason']=='no-compliant-rl-proposal')
    example = {
        'corner':recovery['corner'], 'channel_loss_db':recovery['channel_loss_db'],
        'policy_trace':recovery['policy_trace'], 'selected_setting':recovery['setting'],
        'source':recovery['source'], 'selection_reason':recovery['selection_reason'],
        'bank_rows_checked':recovery['bank_rows_checked'],
        'verifier_decision':'No visited setting met full V6 compliance, as recorded by the selector.',
        'per_visit_failed_constraints':None,
        'decision_scope':'The saved selection reason establishes rejection of all visits in this episode; individual failed constraint rows were not logged. Link-valid alone is not full compliance. Invalid-link zero scalars in the raw trace are sentinels, not measured zero eyes.',
    }
    representative = next(r for r in rows if r['corner']=='tt/1.00/27C' and
                          r['channel_loss_db']==s['representative_channel_loss_db'])
    _require(representative['setting'] == s['setting'], 'representative export mismatch')
    return {
        'schema':'nebula-submission-receipt-v1', 'mode':'SAVED_RECORD_EXTRACTION_NO_POLICY_REPLAY',
        'request':design['request'], 'method':design['method'],
        'policy_seed':s['policy_seed'], 'nearest_training_request':s['nearest_training_request'],
        'selection_objective':s['selection_objective'], 'counts':counts,
        'recovery_example':example, 'representative_selection':representative,
        'nominal':design['nominal'],
        'timing':{'original_recorded_wall_s':_elapsed(design.get('wall_s')),
                  'recorded_export_wall_s':_elapsed(design.get('export_wall_s')),
                  'policy_stage_wall_s':None,'verification_stage_wall_s':None,
                  'fallback_stage_wall_s':None,'artifact_writing_wall_s':None,
                  'end_to_end_wall_s':None,
                  'scope':'Saved design timer plus representative-deck timer. Excludes subsequent drawing/file writing and startup outside the timer. No matched speedup or total end-to-end latency measured.'},
        'spice':{'original_run':design['simulations'], 'receipt_generation_new_calls':0,
                 'offline_characterized_rows':s['offline_spice_rows'],
                 'offline_link_points':s['offline_link_points'],
                 'scope':'Policy visits and verifier/fallback lookups reuse the characterized bank. The original export reports one fresh representative SPICE call; extraction runs none.'},
        'limits':['315 conditions use adaptive codes, not one fixed netlist.',
                  'The representative exported circuit is the earlier CTLE with ideal one-tap DFE scoring; it is not the integrated 73-device checkpoint.',
                  'Per-visit failed constraint names and individual stage timers were not stored.',
                  'No fresh simulation, policy replay, training or runtime comparison is performed.'],
        'per_condition':rows,
    }


def build(out_dir: Path = DEFAULT_OUT) -> Path:
    source = ROOT / SOURCE
    receipt = receipt_model(json.loads(checked_bytes(source, SOURCE_SHA256)))
    artifacts = [source, source.with_name('design.cir'), source.with_name('design_schematic.png'),
                 source.with_name('rl_dashboard.png'), ROOT/'nebula/rl/hybrid_designer.py',
                 ROOT/'nebula/design.py', Path(__file__).resolve()]
    receipt['sources'] = []
    for path in artifacts:
        data = path.read_bytes()
        receipt['sources'].append({'path':path.relative_to(ROOT).as_posix(),
            'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),
            'role':'saved run artifact' if path.parent==source.parent else 'current implementation provenance'})
    out_dir.mkdir(parents=True,exist_ok=True)
    out = out_dir/'receipt.json'
    out.write_text(json.dumps(receipt,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')
    return out


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=DEFAULT_OUT)
    args=parser.parse_args()
    print(build(args.out))
