"""Entry158. Exactly one approved batch; no resume, retry or receiver promotion."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import time
from nebula.device import loaded_tuning_bound as B
from nebula.device.ngspice_runner import ngspice_path
from nebula.experiments import spice_capture as C
from nebula.experiments.exp_varactor_probe import pdk_hashes
from nebula.experiments.runlock import hold, stamp

OUT=B.ROOT/'nebula/product_audits/entry158_loaded_tuning_20260915'
DEADLINE=datetime(2026,9,15,11,17,31,tzinfo=timezone.utc)
NEW_SOURCES=('nebula/LOADED_TUNING_BOUND_PLAN_20260915.md',
 'nebula/device/loaded_tuning_bound.py','nebula/experiments/exp_loaded_tuning_bound.py',
 'nebula/tests/test_loaded_tuning_bound.py','nebula/submission_evidence.py')

def write(path,value):
    Path(path).write_text(json.dumps(value,indent=2,allow_nan=False),encoding='utf-8')

def schedule(evaluate):
    states=[]
    for state in (0,1):
        result=evaluate(state);states.append(result)
        if not result.get('instrument_ok'):break
    return states

def remaining_seconds():
    return (DEADLINE-datetime.now(timezone.utc)).total_seconds()

def prerequisites():
    old=json.loads(B.original_file(B.LOADED,'config.json').read_text())
    for name,digest in old['source_sha256'].items():B.checked_file(B.ROOT,name,digest)
    models=pdk_hashes()
    if models!=old['external_pdk_include_closure_sha256']:raise ValueError('PDK closure changed')
    if B.sha(ngspice_path())!=old['ngspice_sha256']:raise ValueError('Simulator binary changed')
    proposals=B.proposals()
    sources={name:B.sha(B.ROOT/name) for name in (*old['source_sha256'],*NEW_SOURCES)}
    return old,models,proposals,sources

def run():
    if OUT.exists():raise ValueError('Approved output already exists: no overwrite, resume or retry')
    if remaining_seconds()<240:raise ValueError('Insufficient approved time remaining')
    # Refuse even stale locks here; this bounded diagnostic never breaks another run's lock.
    lock=Path(__file__).parent/'.dfe_slicer.runlock.json'
    if lock.exists():raise ValueError('Existing simulation lock; not modified')
    with hold('dfe_slicer'):
        OUT.mkdir(parents=True,exist_ok=False)
        started=time.perf_counter();calls=0;states=[];sources={};models={}
        result=dict(entry=158,full_receiver_verified=False,selected_setting=352,
            selected_circuit_changed=False,end_to_end_target_coverage='4/12 unchanged',
            scope='Independent programmable reference, nominal held-clock OP/AC only',
            max_calls=2,timeout_s=180,states=[],instrument_ok=False)
        try:
            old,models,proposals,sources=prerequisites()
            for name in sources:
                target=OUT/'sources'/name;target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(B.ROOT/name,target)
            controls=proposals['controls']
            decks=[B.deck(s,controls) for s in (0,1)]
            write(OUT/'config.json',dict(entry=158,max_calls=2,timeout_s=180,
                implementation_deadline_utc=DEADLINE.isoformat(),proposals=proposals,
                source_sha256=sources,external_pdk_include_closure_sha256=models,
                ngspice_path=str(ngspice_path()),ngspice_sha256=B.sha(ngspice_path()),
                prior_pins={str(k):v for k,v in B.PINNED.items()},**stamp()))
            def evaluate(state):
                nonlocal calls
                folder=OUT/f'state{state}';begin=time.perf_counter()
                row=dict(clock_state=state,instrument_ok=False,full_receiver_verified=False)
                try:
                    if calls>=2 or remaining_seconds()<210:raise ValueError('Approved budget/deadline guard')
                    calls+=1
                    write(OUT/'progress.json',dict(charged_calls=calls,starting_state=state,
                        utc=datetime.now(timezone.utc).isoformat()))
                    print(f'Approved call {calls}/2: held state {state}, {len(controls)} OP/AC snapshots, timeout 180 s',flush=True)
                    C.invoke(decks[state],folder,timeout_s=180)
                    row=B.extract(folder,state,controls)
                except Exception as exc:
                    folder.mkdir(parents=True,exist_ok=True)
                    row.update(fail_reason=f'{type(exc).__name__}: {exc}')
                row['wall_seconds']=time.perf_counter()-begin
                write(folder/'result.json',row)
                print(f'State {state}: instrument_ok={row["instrument_ok"]}; {row.get("fail_reason", "baseline checked")}',flush=True)
                return row
            states=schedule(evaluate)
            result.update(states=states,targets=B.select_targets(states),
                standalone_ac_matches=sum(t['found'] for t in proposals['targets']),
                scheduled_snapshots_per_call=len(controls),
                pdk_unchanged=pdk_hashes()==models,
                sources_unchanged=all(B.sha(B.ROOT/n)==h for n,h in sources.items()),
                simulator_unchanged=B.sha(ngspice_path())==old['ngspice_sha256'])
            result['instrument_ok']=bool(len(states)==2 and all(s['instrument_ok'] for s in states)
                and result['pdk_unchanged'] and result['sources_unchanged'] and result['simulator_unchanged'])
            if not result['instrument_ok']:
                result['targets']=B.select_targets([])
            result['nominal_loaded_ac_matches']=sum(t['nominal_ac_match'] for t in result['targets'])
        except Exception as exc:
            result.update(fail_reason=f'{type(exc).__name__}: {exc}',states=states,instrument_ok=False)
        result.update(charged_calls=calls,wall_seconds=time.perf_counter()-started,
            unrun_clock_states=[s for s in (0,1) if s not in [r['clock_state'] for r in states]],
            completed_utc=datetime.now(timezone.utc).isoformat())
        write(OUT/'summary.json',result)
        write(OUT/'evidence_sha256.json',{p.relative_to(OUT).as_posix():B.sha(p)
            for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='evidence_sha256.json'})
        print(json.dumps({k:v for k,v in result.items() if k not in ('states','targets')},indent=2),flush=True)
        return result

if __name__=='__main__':run()
