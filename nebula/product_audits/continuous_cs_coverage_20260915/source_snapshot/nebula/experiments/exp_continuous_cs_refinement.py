"""All three preregistered continuous-Cs candidates, with no favorable stopping."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import time
from nebula.device import continuous_cs_refinement as C
from nebula.physical_recovery import recovery_lock
from nebula.experiments.exp_submission_recovery_benchmark import environment_fingerprints, active_ngspice

WALL_BUDGET_S = 900.
MAX_CHARGED = 411

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def run_set(evaluate):
    rows=[]
    for factor in C.FACTORS:
        row=evaluate(factor)
        rows.append(row)
        if row.get('budget_stop'):
            break
    counts=[r.get('charged_invocations') for r in rows]
    return dict(candidates=rows, registered_candidates_completed=len(rows)==len(C.FACTORS) and not rows[-1].get('budget_stop',False),
                accepted_candidates=sum(bool(r.get('accepted')) for r in rows),
                charged_invocations=sum(counts) if all(isinstance(n,int) for n in counts) else None,
                stop_reason='wall_budget' if rows[-1].get('budget_stop') else 'completed_registered_set')

def verify_manifest(directory):
    directory=Path(directory).resolve()
    data=json.loads((directory/'evidence_sha256.json').read_text(encoding='utf-8'))
    for name, digest in data.items():
        path=(directory/name).resolve()
        if not path.is_relative_to(directory) or not path.is_file() or sha(path)!=digest:
            raise ValueError('evidence hash mismatch: '+name)
    return len(data)

def fingerprints():
    result=environment_fingerprints()
    for path in (C.PLAN, Path(__file__), Path(C.__file__), C.ROOT/'nebula/tests/test_continuous_cs_refinement.py'):
        result['source_sha256'][path.relative_to(C.ROOT).as_posix()]=sha(path)
    result['base_result_sha256']=sha(C.BASE)
    result['base_manifest_sha256']=sha(C.BASE.parent/'evidence_sha256.json')
    return result

def run(evidence_dir):
    out=Path(evidence_dir).resolve()
    if out.exists():
        raise FileExistsError('campaign output must be fresh')
    if active_ngspice():
        raise RuntimeError('ngspice already active; no launch')
    started=time.perf_counter()
    deadline=started+WALL_BUDGET_S
    with recovery_lock():
        C.load_base()
        base_files=verify_manifest(C.BASE.parent)
        before=fingerprints()
        out.mkdir(parents=True,exist_ok=False)
        C.P.write_json(out/'preregistration.json',dict(factors=C.FACTORS, request=dict(peaking_db=6.,f_peak_hz=2.5e9),
            max_charged=MAX_CHARGED, wall_budget_s=WALL_BUDGET_S, base_manifest_verified_files=base_files,
            count_scope='Charged invocations; not confirmation that ngspice launched or completed.',
            source_fingerprints=before))
        snapshots=out/'source_snapshot'
        for relative in before['source_sha256']:
            target=snapshots/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes((C.ROOT/relative).read_bytes())
        completed=[]
        def evaluate(factor):
            directory=out/C.candidate_id(factor)
            then=time.perf_counter()
            row=dict(candidate_id=C.candidate_id(factor),cs_factor=factor,base_setting=480,bank_setting=None,
                     directory=str(directory),accepted=False)
            try:
                result=C.run_candidate(factor,directory,deadline)
                row.update(accepted=C.is_verified(result) and bool(result['request_match']['request_met']),
                           charged_invocations=result['simulations']['total'],
                           n_pass=result['verification']['n_pass'],n_points=result['verification']['n_points'],
                           nominal=result['nominal'],result_sha256=sha(directory/'result.json'))
            except Exception as exc:
                failure=directory/'failure.json'
                data=json.loads(failure.read_text(encoding='utf-8')) if failure.exists() else {}
                row.update(error=f'{type(exc).__name__}: {exc}', charged_invocations=data.get('spice_calls'),
                           budget_stop=isinstance(exc,C.BudgetExceeded))
            row['wall_s']=time.perf_counter()-then
            if (directory/'evidence_sha256.json').exists():
                row['manifest_verified_files']=verify_manifest(directory)
                row['manifest_sha256']=sha(directory/'evidence_sha256.json')
            completed.append(row)
            C.P.write_json(out/'progress.json',dict(candidates=completed,wall_s=time.perf_counter()-started))
            print(json.dumps({k:v for k,v in row.items() if k!='nominal'}),flush=True)
            return row
        result=run_set(evaluate)
        result.update(wall_s=time.perf_counter()-started,full_product_compliance=False,
            evidence_scope='Fixed physical CTLE and ideal behavioral DFE; no full S7, analog DFE PVT or continuous-range coverage.',
            source_fingerprints_unchanged=before==fingerprints())
        if result['charged_invocations'] is not None and result['charged_invocations']>MAX_CHARGED:
            raise RuntimeError('registered charged budget exceeded')
        C.P.write_json(out/'summary.json',result)
        hashes={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file() and p!=out/'evidence_sha256.json'}
        C.P.write_json(out/'evidence_sha256.json',hashes)
        return result

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    result=run(args.out)
    print(json.dumps({k:v for k,v in result.items() if k!='candidates'}),flush=True)
