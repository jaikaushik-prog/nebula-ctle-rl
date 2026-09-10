"""Entry 143: independent nominal verification of measured calibrated controls."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time
import numpy as np
from nebula.device import dfe_calibrated_verification as V, dfe_loaded_analog as L, dfe_loaded_initialization as I
from nebula.experiments import exp_dfe_loaded_calibration as K, exp_dfe_linearity_tolerance as E
from nebula.experiments import evidence_archive as A, raw_manifest as M, spice_capture, exp_physical_bias as P
from nebula.experiments.exp_varactor_probe import pdk_hashes
from nebula.experiments.runlock import hold,stamp
from nebula.device.ngspice_runner import ngspice_path
ROOT=K.ROOT
PRIOR=ROOT/'nebula/product_audits/entry142_dfe_loaded_calibration_20260910'
SOURCES=tuple(sorted(set(K.SOURCES+('nebula/DFE_CALIBRATED_VERIFICATION_PLAN.md',
    'nebula/device/dfe_calibrated_verification.py','nebula/experiments/exp_dfe_calibrated_verification.py',
    'nebula/tests/test_dfe_calibrated_verification.py'))))


def prerequisites():
    proofs={'calibration':M.verify(PRIOR),'linearity':A.verify(K.PRIOR)}
    summary=json.loads((PRIOR/'summary.json').read_text());config=json.loads((PRIOR/'config.json').read_text())
    if summary['entry']!=142 or summary['spice_calls']!=1 or not summary['target_found']:
        raise ValueError('missing calibrated primary target')
    selected=summary['selection']['selected']
    if (selected['r_fraction'],selected['c_fraction'])!=V.TARGET[2:]:
        raise ValueError('registered controls differ from measured selection')
    if any(A.digest(ROOT/k)!=v for k,v in config['source_sha256'].items()):
        raise ValueError('frozen scientific source changed')
    index=K.biases().index(V.TARGET[2:]);calibration=summary['rows'][index]
    reference=json.loads((K.PRIOR/'reference_result.json').read_text())
    ac=np.loadtxt(PRIOR/f'calibration/ac_{index:03d}.txt')
    return proofs,config,reference,calibration,ac


def schedule(evaluate):
    static=[evaluate('static',state,E.TOLERANCES[-1],L.STEPS[0]) for state in (0,1)]
    tones=[evaluate('tone',0,tol,step) for tol in E.TOLERANCES for step in L.STEPS]
    link=evaluate('link',0,E.TOLERANCES[-1],L.STEPS[0])
    agreement=all(L.resolution_matches(a,b) for i,a in enumerate(tones) for b in tones[i+1:])
    passed=bool(all(I.valid(r) and r.get('small_signal_specs_pass') and r.get('target_match') for r in static)
        and static[0].get('calibration_matches') and agreement
        and all(I.valid(r) and r.get('hd3_model_pass') for r in tones) and link.get('signal_gate_pass',False))
    return {'entry':143,'static':static,'tones':tones,'link':link,'four_way_agreement':agreement,
        'nominal_calibrated_pass':passed,'target':V.TARGET,'pvt_verified':False,
        'all_static_states_verified':False,'clocked_receiver_noise_verified':False,'full_receiver_verified':False}


def run(out):
    with hold('dfe_slicer'):
        started=time.perf_counter()
        proofs,old,reference,calibration,calibration_ac=prerequisites();preflight=time.perf_counter()-started
        out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
        sources={k:A.digest(ROOT/k) for k in SOURCES}
        for name in SOURCES:
            dest=out/'sources'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
        shutil.copyfile(K.PRIOR/'reference_result.json',out/'reference_result.json')
        index=K.biases().index(V.TARGET[2:])
        shutil.copyfile(PRIOR/f'calibration/ac_{index:03d}.txt',out/'calibration_ac.txt')
        P.write_json(out/'calibration_result.json',calibration)
        calls=0;result={'entry':143,'nominal_calibrated_pass':False,'full_receiver_verified':False}
        try:
            models=pdk_hashes()
            if models!=old['external_pdk_include_closure_sha256']: raise ValueError('measured PDK changed')
            dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,encoding='utf-8').strip())
            P.write_json(out/'config.json',{'entry':143,'max_calls':7,'target':V.TARGET,
                'timeout_s':spice_capture.MAX_SECONDS,'source_sha256':sources,'prior_manifest_proofs':proofs,
                'source_snapshot_authoritative':True,'git_worktree_dirty_at_snapshot':dirty,'git_commit_is_parent_only':dirty,
                'prior_calls_separately_billed':True,'external_pdk_include_closure_sha256':models,
                'ngspice_path':str(ngspice_path()),'ngspice_sha256':A.digest(ngspice_path()),'geometry':old['geometry'],
                'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,encoding='utf-8').strip(),**stamp()})
            def evaluate(kind,state,tol,step):
                nonlocal calls
                folder=out/f'{kind}_state{state}_tol{tol:g}_step{step*1e12:g}ps'
                try:
                    text=V.link_deck() if kind=='link' else V.deck(kind,state,tol,step,reference)
                    calls+=1
                    if calls>7: raise RuntimeError('registered call budget exceeded')
                    spice_capture.invoke(text,folder)
                    row=V.link_extract(folder,text) if kind=='link' else V.analog_extract(folder,text,kind,state,step,calibration,calibration_ac)
                except Exception as exc:
                    folder.mkdir(parents=True,exist_ok=True)
                    row={'instrument_ok':False,'initialization_valid':False,'fail_reason':f'{type(exc).__name__}: {exc}','full_receiver_verified':False}
                row.update(kind=kind,clock_state=state,relative_tolerance=tol,max_step_s=step)
                P.write_json(folder/'result.json',row)
                print(f'{calls}/7 {folder.name}: instrument={row["instrument_ok"]} '
                    f'HD3={row.get("ctle_hd3",{}).get("hd3_dbc")} link={row.get("signal_gate_pass")} '
                    f'error={row.get("fail_reason")}',flush=True)
                return row
            result=schedule(evaluate)
            result['sources_unchanged']=all(A.digest(ROOT/k)==v for k,v in sources.items())
            result['pdk_unchanged']=pdk_hashes()==models
            result['nominal_calibrated_pass'] &= result['sources_unchanged'] and result['pdk_unchanged']
        except Exception as exc:
            result.update(nominal_calibrated_pass=False,fail_reason=f'{type(exc).__name__}: {exc}')
        result.update(spice_calls=calls,wall_seconds=time.perf_counter()-started,preflight_seconds=preflight)
        P.write_json(out/'summary.json',result)
        P.write_json(out/'evidence_sha256.json',{p.relative_to(out).as_posix():A.digest(p) for p in sorted(out.rglob('*')) if p.is_file()})
        return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True,type=Path)
    raise SystemExit(0 if run(parser.parse_args().out)['nominal_calibrated_pass'] else 1)
