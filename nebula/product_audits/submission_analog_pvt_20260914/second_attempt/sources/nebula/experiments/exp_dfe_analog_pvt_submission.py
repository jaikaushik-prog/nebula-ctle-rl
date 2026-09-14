"""Bounded submission analog pilot; no implicit continuation or retuning."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time
import numpy as np
from nebula.common.types import all_corners
from nebula.device import dfe_analog_pvt_submission as S
from nebula.experiments import exp_dfe_calibrated_verification as N
from nebula.experiments import evidence_archive as A, spice_capture, exp_physical_bias as P
from nebula.experiments.exp_varactor_probe import pdk_hashes
from nebula.experiments.runlock import hold, stamp
from nebula.device.ngspice_runner import ngspice_path

ROOT=N.ROOT
PRIOR=ROOT/'nebula/product_audits/entry143_dfe_calibrated_verification_20260910'
PRIOR_SUMMARY='14d7d368163652235378e1566e4800a7d26ec2a550922300a015978b74602d96'
MAX_CALLS=12
WALL_BUDGET_SECONDS=2700
SOURCES=tuple(sorted(set(N.SOURCES+(
    'nebula/DFE_ANALOG_PVT_SUBMISSION_PLAN.md',
    'nebula/DFE_ANALOG_PVT_SECOND_ATTEMPT_PLAN.md',
    'nebula/device/dfe_analog_pvt_submission.py',
    'nebula/experiments/exp_dfe_analog_pvt_submission.py',
    'nebula/tests/test_dfe_analog_pvt_submission.py'))))


def case_name(kind,state,tol,step):
    return f'{kind}_state{state}_tol{tol:g}_step{step*1e12:g}ps'


def prerequisites():
    proof=A.verify(PRIOR)
    if A.digest(PRIOR/'summary.json')!=PRIOR_SUMMARY:
        raise ValueError('frozen nominal summary identity differs')
    old=json.loads((PRIOR/'config.json').read_text())
    summary=json.loads((PRIOR/'summary.json').read_text())
    if not summary['nominal_calibrated_pass'] or old['target']!=list(S.TARGET):
        raise ValueError('missing calibrated nominal prerequisite')
    if any(A.digest(ROOT/k)!=v for k,v in old['source_sha256'].items()):
        raise ValueError('frozen scientific source changed')
    reference=json.loads((PRIOR/'reference_result.json').read_text())
    for args in S.measurements():
        original=(PRIOR/case_name(*args)/'design.cir').read_text()
        if S.deck(*args,reference,S.PILOT[0])!=original:
            raise ValueError('nominal deck no longer matches frozen original')
    return proof,old,reference


def nominal_matches(folder,result,args):
    kind,state,_,_=args
    previous=PRIOR/case_name(*args)
    old=json.loads((previous/'result.json').read_text())
    if kind=='static':
        h=S.R.parse_ac(np.loadtxt(folder/'ac.txt'),1)[:,0]
        old_h=S.R.parse_ac(np.loadtxt(previous/'ac.txt'),1)[:,0]
        return S.I.calibration_matches(result,old,h,old_h)
    return S.L.resolution_matches(result,old)


def validate_wall_budget(seconds):
    if not np.isfinite(seconds) or not spice_capture.MAX_SECONDS<=seconds<=WALL_BUDGET_SECONDS:
        raise ValueError("wall budget must be finite and between 180 and 2700 seconds")
    return float(seconds)


def call_allowed(elapsed,calls,wall_budget_seconds=WALL_BUDGET_SECONDS):
    budget=validate_wall_budget(wall_budget_seconds)
    return bool(calls<MAX_CALLS and elapsed+spice_capture.MAX_SECONDS<=budget)


def schedule(evaluate):
    rows=[]
    reason=None
    for corner in S.PILOT:
        static=[];tones=[]
        for args in S.measurements():
            row=evaluate(corner,args)
            (static if args[0]=='static' else tones).append(row)
            if row.get('budget_stop'):
                reason='wall_or_call_budget';break
        result=S.corner_summary(static,tones)
        result.update(corner=str(corner),static=static,tones=tones)
        rows.append(result)
        if reason: break
        if not result['instrument_complete']:
            reason='invalid_instrument_or_initialization';break
        if corner.is_nominal and (not result['analog_model_pass'] or not result['target_match']
                or not all(x.get('nominal_replay_matches',False) for x in static+tones)):
            reason='nominal_reproduction_or_gate_failed';break
    measured={r['corner'] for r in rows if r['instrument_complete']}
    return {'campaign':'submission_analog_pilot_20260914','corners':rows,'stop_reason':reason,
        'corners_instrument_complete':len(measured),
        'corners_analog_model_pass':sum(r['analog_model_pass'] for r in rows),
        'corners_target_match':sum(r['target_match'] for r in rows),
        'pilot_complete':bool(len(rows)==len(S.PILOT) and len(measured)==len(S.PILOT)),
        'unmeasured_corners':[str(c) for c in all_corners() if str(c) not in measured],
        'fixed_target':S.TARGET,'corner_retuning':False,'analog_pvt45_verified':False,
        'clocked_receiver_noise_verified':False,'all_static_branches_verified':False,
        'passive_nonlinearity_verified':False,'full_receiver_verified':False}


def run(out,wall_budget_seconds=WALL_BUDGET_SECONDS):
    wall_budget_seconds=validate_wall_budget(wall_budget_seconds)
    out=Path(out).resolve()
    if out.exists(): raise FileExistsError('refuse existing submission evidence directory')
    with hold('dfe_slicer'):
        started=time.perf_counter()
        proof,old,reference=prerequisites()
        models=pdk_hashes()
        if models!=old['external_pdk_include_closure_sha256']:
            raise ValueError('frozen PDK include closure changed')
        preflight=time.perf_counter()-started
        out.mkdir(parents=True,exist_ok=False)
        sources={k:A.digest(ROOT/k) for k in SOURCES}
        for name in SOURCES:
            dest=out/'sources'/name;dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/name,dest)
        shutil.copyfile(PRIOR/'reference_result.json',out/'reference_result.json')
        status=subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,encoding='utf-8')
        P.write_json(out/'config.json',{
            'campaign':'submission_analog_pilot_20260914','max_calls':MAX_CALLS,
            'wall_budget_seconds':wall_budget_seconds,'timeout_s':spice_capture.MAX_SECONDS,
            'target':S.TARGET,'corners':[str(c) for c in S.PILOT],
            'source_sha256':sources,'source_snapshot_authoritative':True,
            'git_worktree_dirty_at_snapshot':bool(status.strip()),
            'git_commit_is_parent_only':bool(status.strip()),
            'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,encoding='utf-8').strip(),
            'prior_manifest_proof':proof,'prior_summary_sha256':PRIOR_SUMMARY,
            'prior_calls_separately_billed':True,'external_pdk_include_closure_sha256':models,
            'ngspice_path':str(ngspice_path()),'ngspice_sha256':A.digest(ngspice_path()),
            'geometry':old['geometry'],'fixed_code':2,'fixed_sign':1,'fixed_phase_ui':1.,
            'static_solver':{'reltol':1e-7,'vntol':1e-10,'abstol':1e-13},
            'tone_solvers':[{'reltol':a[2],'max_step_s':a[3],'vntol':1e-7,'abstol':1e-12,
                'method':'gear','maxord':2} for a in S.measurements() if a[0]=='tone'],**stamp()})
        calls=0;ledger=[]
        def evaluate(corner,args):
            nonlocal calls
            kind,state,tol,step=args
            folder=out/f'pvt_{corner}'/case_name(*args)
            if not call_allowed(time.perf_counter()-started,calls,wall_budget_seconds):
                return {'instrument_ok':False,'initialization_valid':False,'budget_stop':True,
                    'fail_reason':'full simulator timeout would exceed registered budget'}
            begin=time.perf_counter();sim_seconds=None;attempted=False
            try:
                text=S.deck(*args,reference,corner)
                calls+=1;attempted=True
                sim_start=time.perf_counter()
                try: spice_capture.invoke(text,folder)
                finally: sim_seconds=time.perf_counter()-sim_start
                row=S.extract(folder,text,kind,state,step,corner)
                row['nominal_replay_matches']=nominal_matches(folder,row,args) if corner.is_nominal else None
            except Exception as exc:
                folder.mkdir(parents=True,exist_ok=True)
                row={'instrument_ok':False,'initialization_valid':False,
                    'fail_reason':f'{type(exc).__name__}: {exc}','full_receiver_verified':False}
            row.update(kind=kind,clock_state=state,corner=str(corner))
            row['relative_tolerance' if kind=='tone' else 'dispatch_tolerance']=tol
            row['max_step_s' if kind=='tone' else 'dispatch_step_s']=step
            row.update(simulator_attempted=attempted,simulator_wall_seconds=sim_seconds,
                measurement_wall_seconds=time.perf_counter()-begin,
                evidence_folder=folder.relative_to(out).as_posix())
            P.write_json(folder/'result.json',row)
            ledger.append({'corner':str(corner),'case':case_name(*args),'simulator_attempted':attempted,
                'simulator_wall_seconds':sim_seconds,'measurement_wall_seconds':row['measurement_wall_seconds'],
                'instrument_ok':row['instrument_ok'],'evidence_folder':row['evidence_folder']})
            P.write_json(out/'progress.json',{'spice_calls':calls,'measurements':ledger,
                'elapsed_seconds':time.perf_counter()-started})
            print(f'{calls}/{MAX_CALLS} {corner} {case_name(*args)}: instrument={row["instrument_ok"]} '
                f'HD3={row.get("ctle_hd3",{}).get("hd3_dbc")} error={row.get("fail_reason")}',flush=True)
            return row
        try: result=schedule(evaluate)
        except Exception as exc:
            result={'pilot_complete':False,'fail_reason':f'{type(exc).__name__}: {exc}',
                'full_receiver_verified':False}
        result.update(sources_unchanged=all(A.digest(ROOT/k)==v for k,v in sources.items()),
            pdk_unchanged=pdk_hashes()==models,spice_calls=calls,
            wall_seconds=time.perf_counter()-started,preflight_seconds=preflight,
            measured_simulator_wall_seconds=sum(x['simulator_wall_seconds'] or 0 for x in ledger),
            measurement_ledger=ledger)
        if not result['sources_unchanged'] or not result['pdk_unchanged']:
            result.update(pilot_complete=False,fail_reason='source or PDK changed during pilot')
        P.write_json(out/'summary.json',result)
        P.write_json(out/'evidence_sha256.json',{p.relative_to(out).as_posix():A.digest(p)
            for p in sorted(out.rglob('*')) if p.is_file()})
        return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--wall-budget-seconds',type=float,default=WALL_BUDGET_SECONDS)
    args=parser.parse_args()
    result=run(args.out,args.wall_budget_seconds)
    raise SystemExit(0 if result['pilot_complete'] else 1)
