"""Entry 141: bounded four-way tolerance and timestep agreement."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
import numpy as np
from nebula.experiments import exp_dfe_linearity_gear as G
from nebula.experiments import exp_dfe_clocked_linearity as P
from nebula.experiments import exp_dfe_loaded_initialization as N
from nebula.experiments import evidence_archive as A, spice_capture
from nebula.experiments import exp_physical_bias as W
from nebula.experiments.exp_varactor_probe import pdk_hashes
from nebula.experiments.runlock import hold,stamp
from nebula.device import dfe_loaded_initialization as I, dfe_loaded_analog as L, configurable_rc as R
from nebula.device.ngspice_runner import ngspice_path

ROOT=P.ROOT
PRIOR=ROOT/'nebula/product_audits/entry140_dfe_linearity_gear_20260910'
SOURCES=tuple(sorted(set(G.SOURCES+('nebula/DFE_LINEARITY_TOLERANCE_PLAN.md',
    'nebula/experiments/exp_dfe_linearity_tolerance.py','nebula/tests/test_dfe_linearity_tolerance.py'))))


TOLERANCES=(2e-5,1e-5)
ORIGINAL='.options reltol=1e-7 vntol=1e-10 abstol=1e-13'


def option(tol):
    if tol not in TOLERANCES: raise ValueError('unregistered relative tolerance')
    return f'.options reltol={tol:.16g} vntol=1e-7 abstol=1e-12'


def deck(tol,step,reference):
    text=G.deck(step,reference)
    if text.count(ORIGINAL)!=1: raise ValueError('frozen solver options changed')
    return text.replace(ORIGINAL,option(tol),1)


def abort_audit(log):
    if re.search(r'timestep too small|simulation\(s\) aborted',log,re.I):
        raise ValueError('aborted transient; no distortion measurement credited')


def prerequisites():
    proof=A.verify(PRIOR)
    config=json.loads((PRIOR/'config.json').read_text())
    summary=json.loads((PRIOR/'summary.json').read_text())
    if summary['entry']!=140 or summary['spice_calls']!=2 or summary['clocked_ctle_hd3_model_pass']:
        raise ValueError('expected retained failed Entry 140 pair')
    if any(A.digest(ROOT/k)!=v for k,v in config['source_sha256'].items()):
        raise ValueError('frozen scientific source changed')
    for step in L.STEPS:
        folder=PRIOR/f'tone_step{step*1e12:g}ps'
        if json.loads((folder/'result.json').read_text())['instrument_ok']:
            raise ValueError('expected rejected prior trace')
        if 'Timestep too small' not in (folder/'ngspice.log').read_text():
            raise ValueError('missing actual prior abort diagnostic')
    reference=json.loads((PRIOR/'reference_result.json').read_text())
    ac=R.parse_ac(np.loadtxt(PRIOR/'reference_ac.txt'),1)[:,0]
    I.seed_values(reference,-1)
    return proof,config,reference,ac


def schedule(evaluate):
    rows=[{**evaluate(tol,step),'relative_tolerance':tol,'max_step_s':step}
          for tol in TOLERANCES for step in L.STEPS]
    agreement=all(L.resolution_matches(a,b) for i,a in enumerate(rows) for b in rows[i+1:])
    return {'entry':141,'tones':rows,'four_way_agreement':agreement,
        'clocked_ctle_hd3_model_pass':bool(agreement and all(I.valid(r) and r.get('hd3_model_pass',False) for r in rows)),
        'integration_method':'gear','maximum_order':2,'all_static_states_verified':False,
        'clocked_receiver_noise_verified':False,'tuning_map_verified':False,'full_receiver_verified':False}


def extract(folder,text,step,reference,reference_ac):
    abort_audit((Path(folder)/'ngspice.log').read_text())
    return N.extract(folder,text,'tone',0,step,-1,reference,reference_ac)


def run(out):
    with hold('dfe_slicer'):
        started=time.perf_counter()
        proof,old,reference,reference_ac=prerequisites();preflight=time.perf_counter()-started
        out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
        sources={k:A.digest(ROOT/k) for k in SOURCES}
        for name in SOURCES:
            dest=out/'sources'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
        for name in ('reference_result.json','reference_ac.txt'): shutil.copyfile(PRIOR/name,out/name)
        calls=0
        result={'entry':141,'clocked_ctle_hd3_model_pass':False,'full_receiver_verified':False}
        try:
            models=pdk_hashes()
            if models!=old['external_pdk_include_closure_sha256']: raise ValueError('measured PDK changed')
            dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,encoding='utf-8').strip())
            W.write_json(out/'config.json',{'entry':141,'max_calls':4,'timeout_s':spice_capture.MAX_SECONDS,
                'prior_manifest_proof':proof,'prior_summary_sha256':A.digest(PRIOR/'summary.json'),
                'source_sha256':sources,'source_snapshot_authoritative':True,
                'git_worktree_dirty_at_snapshot':dirty,'git_commit_is_parent_only':dirty,
                'prior_calls_separately_billed':True,'integration_method':'gear','maximum_order':2,
                'external_pdk_include_closure_sha256':models,'ngspice_path':str(ngspice_path()),
                'ngspice_sha256':A.digest(ngspice_path()),'geometry':old['geometry'],
                'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,encoding='utf-8').strip(),**stamp()})
            def evaluate(tol,step):
                nonlocal calls
                folder=out/f'tone_tol{tol:g}_step{step*1e12:g}ps'
                try:
                    text=deck(tol,step,reference);calls+=1
                    if calls>4: raise RuntimeError('registered call budget exceeded')
                    spice_capture.invoke(text,folder)
                    row=extract(folder,text,step,reference,reference_ac)
                except Exception as exc:
                    folder.mkdir(parents=True,exist_ok=True)
                    row={'instrument_ok':False,'initialization_valid':False,
                         'fail_reason':f'{type(exc).__name__}: {exc}','full_receiver_verified':False}
                row['max_step_s']=step;row['relative_tolerance']=tol;W.write_json(folder/'result.json',row)
                print(f'{calls}/4 {folder.name}: instrument={row["instrument_ok"]} '
                      f'HD3={row.get("ctle_hd3",{}).get("hd3_dbc")} error={row.get("fail_reason")}',flush=True)
                return row
            result=schedule(evaluate)
            result['sources_unchanged']=all(A.digest(ROOT/k)==v for k,v in sources.items())
            result['pdk_unchanged']=pdk_hashes()==models
            result['clocked_ctle_hd3_model_pass'] &= result['sources_unchanged'] and result['pdk_unchanged']
        except Exception as exc:
            result.update(clocked_ctle_hd3_model_pass=False,fail_reason=f'{type(exc).__name__}: {exc}')
        result.update(spice_calls=calls,wall_seconds=time.perf_counter()-started,preflight_seconds=preflight)
        W.write_json(out/'summary.json',result)
        W.write_json(out/'evidence_sha256.json',{p.relative_to(out).as_posix():A.digest(p) for p in sorted(out.rglob('*')) if p.is_file()})
        return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True,type=Path)
    raise SystemExit(0 if run(parser.parse_args().out)['clocked_ctle_hd3_model_pass'] else 1)
