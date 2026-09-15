"""Entry 139: independent clocked CTLE HD3 using the validated starting state."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time
import numpy as np
from nebula.device import dfe_loaded_analog as L, dfe_loaded_initialization as I, configurable_rc as R
from nebula.device.ngspice_runner import ngspice_path
from nebula.experiments import exp_dfe_loaded_initialization as N, exp_physical_bias as P
from nebula.experiments import evidence_archive as A, raw_manifest as M, spice_capture
from nebula.experiments.exp_varactor_probe import pdk_hashes
from nebula.experiments.runlock import hold,stamp

ROOT=N.ROOT
PRIOR=ROOT/'nebula/product_audits/entry138_dfe_loaded_initialization_20260910'
SOURCES=tuple(sorted(set(N.SOURCES+('nebula/DFE_CLOCKED_LINEARITY_PLAN.md',
    'nebula/experiments/exp_dfe_clocked_linearity.py','nebula/tests/test_dfe_clocked_linearity.py'))))


def prerequisites():
    proof=M.verify(PRIOR)
    summary=json.loads((PRIOR/'summary.json').read_text());config=json.loads((PRIOR/'config.json').read_text())
    start=json.loads((PRIOR/'static_state0_sign-1_step5ps/result.json').read_text())
    calibration=json.loads((PRIOR/'static_state1_sign-1_step5ps/result.json').read_text())
    if (summary['entry']!=138 or summary['spice_calls']!=4 or summary['measurement_complete']
            or not I.valid(start) or not start['small_signal_specs_pass']
            or not I.valid(calibration) or not calibration['calibration_matches']):
        raise ValueError('missing validated negative starting state and calibration')
    if any(A.digest(ROOT/k)!=v for k,v in config['source_sha256'].items()):
        raise ValueError('frozen circuit or analyzer source changed')
    reference=json.loads((PRIOR/'reference_result.json').read_text())
    ac=R.parse_ac(np.loadtxt(PRIOR/'reference_ac.txt'),1)[:,0]
    I.seed_values(reference,-1)
    return proof,config,reference,ac


def schedule(evaluate):
    rows=[evaluate(step) for step in L.STEPS]
    agreement=L.resolution_matches(*rows)
    return {'entry':139,'tones':rows,'resolution_agreement':agreement,
        'clocked_ctle_hd3_model_pass':bool(agreement and all(I.valid(r) and r.get('hd3_model_pass',False) for r in rows)),
        'all_static_states_verified':False,'clocked_receiver_noise_verified':False,
        'tuning_map_verified':False,'full_receiver_verified':False}


def run(out):
    with hold('dfe_slicer'):
        started=time.perf_counter()
        proof,old_config,reference,reference_ac=prerequisites();preflight=time.perf_counter()-started
        out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
        sources={k:A.digest(ROOT/k) for k in SOURCES}
        for name in SOURCES:
            dest=out/'sources'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
        for name in ('reference_result.json','reference_ac.txt'): shutil.copyfile(PRIOR/name,out/name)
        calls=0
        result={'entry':139,'clocked_ctle_hd3_model_pass':False,'full_receiver_verified':False}
        try:
            models=pdk_hashes()
            if models!=old_config['external_pdk_include_closure_sha256']: raise ValueError('measured PDK changed')
            dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,encoding='utf-8').strip())
            P.write_json(out/'config.json',{'entry':139,'max_calls':2,'timeout_s':spice_capture.MAX_SECONDS,
                'prior_manifest_proof':proof,'prior_summary_sha256':A.digest(PRIOR/'summary.json'),
                'source_sha256':sources,'source_snapshot_authoritative':True,'git_worktree_dirty_at_snapshot':dirty,
                'git_commit_is_parent_only':dirty,'prior_calls_separately_billed':True,
                'external_pdk_include_closure_sha256':models,'ngspice_path':str(ngspice_path()),
                'ngspice_sha256':A.digest(ngspice_path()),'geometry':old_config['geometry'],
                'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,encoding='utf-8').strip(),**stamp()})
            def evaluate(step):
                nonlocal calls
                folder=out/f'tone_step{step*1e12:g}ps'
                try:
                    text=I.deck('tone',0,step,-1,reference)
                    calls+=1
                    if calls>2: raise RuntimeError('registered call budget exceeded')
                    spice_capture.invoke(text,folder)
                    row=N.extract(folder,text,'tone',0,step,-1,reference,reference_ac)
                except Exception as exc:
                    folder.mkdir(parents=True,exist_ok=True)
                    row={'instrument_ok':False,'initialization_valid':False,'fail_reason':f'{type(exc).__name__}: {exc}','full_receiver_verified':False}
                row['max_step_s']=step;P.write_json(folder/'result.json',row)
                print(f'{calls}/2 {folder.name}: instrument={row["instrument_ok"]} '
                      f'HD3={row.get("ctle_hd3",{}).get("hd3_dbc")} error={row.get("fail_reason")}',flush=True)
                return row
            result=schedule(evaluate)
            result['sources_unchanged']=all(A.digest(ROOT/k)==v for k,v in sources.items())
            result['pdk_unchanged']=pdk_hashes()==models
            result['clocked_ctle_hd3_model_pass'] &= result['sources_unchanged'] and result['pdk_unchanged']
        except Exception as exc:
            result.update(clocked_ctle_hd3_model_pass=False,fail_reason=f'{type(exc).__name__}: {exc}')
        result.update(spice_calls=calls,wall_seconds=time.perf_counter()-started,preflight_seconds=preflight)
        P.write_json(out/'summary.json',result)
        P.write_json(out/'evidence_sha256.json',{p.relative_to(out).as_posix():A.digest(p) for p in sorted(out.rglob('*')) if p.is_file()})
        return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True,type=Path)
    raise SystemExit(0 if run(parser.parse_args().out)['clocked_ctle_hd3_model_pass'] else 1)
