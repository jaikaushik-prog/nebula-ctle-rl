"""Entry 138 six-call initialized primary analog recovery, no warning relaxation."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time
import numpy as np
from nebula.device import dfe_loaded_analog as L, dfe_loaded_initialization as I
from nebula.device import dfe_timing as T, configurable_rc as R, dfe_configurable as C
from nebula.device.ngspice_runner import ngspice_path
from nebula.experiments import exp_dfe_loaded_analog as E, exp_physical_bias as P
from nebula.experiments import evidence_archive as A, raw_manifest as M, spice_capture
from nebula.experiments.exp_varactor_probe import pdk_hashes
from nebula.experiments.runlock import hold,stamp

ROOT=E.ROOT
PRIOR=ROOT/'nebula/product_audits/entry137_dfe_loaded_analog_20260910'
REFERENCE=PRIOR/'static_target7_state1_step5ps'
SOURCES=tuple(sorted(set(E.SOURCES+('nebula/DFE_LOADED_INITIALIZATION_PLAN.md',
    'nebula/device/dfe_loaded_initialization.py','nebula/experiments/exp_dfe_loaded_initialization.py',
    'nebula/tests/test_dfe_loaded_initialization.py'))))


def prerequisites():
    proof=M.verify(PRIOR)
    summary=json.loads((PRIOR/'summary.json').read_text())
    config=json.loads((PRIOR/'config.json').read_text())
    reference=json.loads((REFERENCE/'result.json').read_text())
    if (summary['entry']!=137 or summary['spice_calls']!=2 or summary['measurement_complete']
            or not reference['instrument_ok'] or not reference['small_signal_specs_pass']):
        raise ValueError('expected retained two-call failure and accepted state-1 reference')
    if any(A.digest(ROOT/k)!=v for k,v in config['source_sha256'].items()):
        raise ValueError('Entry 137 scientific source changed')
    I.seed_values(reference,-1)
    ac=R.parse_ac(np.loadtxt(REFERENCE/'ac.txt'),1)[:,0]
    return proof,config,reference,ac


def extract(folder,text,kind,state,step,sign,reference,reference_ac):
    row=E.extract(folder,text,L.PRIMARY,kind,state,step)
    if kind=='static':
        q=row['dc_nodes_v']['df_q']-row['dc_nodes_v']['df_qb']
        h=R.parse_ac(np.loadtxt(Path(folder)/'ac.txt'),1)[:,0]
        row['calibration_matches']=(I.calibration_matches(row,reference,h,reference_ac) if state==1 and sign==-1 else None)
    else:
        _,y=T.read_table(A.trace_path(Path(folder)/'trace.txt'),len(L.VECTORS))
        q=float(y[0,5]-y[0,6])
    row.update(initialization_valid=bool(sign*q>.1),initial_stored_differential_v=q,
               initial_polarity=sign,nodeset_is_released_initial_guess=True)
    return row


def run(out):
    with hold('dfe_slicer'):
        started=time.perf_counter()
        proof,old_config,reference,reference_ac=prerequisites();preflight=time.perf_counter()-started
        out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
        sources={k:A.digest(ROOT/k) for k in SOURCES}
        for name in SOURCES:
            dest=out/'sources'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
        for name in ('result.json','ac.txt'): shutil.copyfile(REFERENCE/name,out/('reference_'+name))
        calls=attempts=0
        result={'entry':138,'measurement_complete':False,'primary_analog_model_pass':False,'full_receiver_verified':False}
        try:
            models=pdk_hashes()
            if models!=old_config['external_pdk_include_closure_sha256']: raise ValueError('measured PDK changed')
            P.write_json(out/'config.json',{'entry':138,'max_calls':6,'timeout_s':spice_capture.MAX_SECONDS,
                'prior_manifest_proof':proof,'prior_summary_sha256':A.digest(PRIOR/'summary.json'),
                'source_sha256':sources,'geometry':C.geometry(),'prior_calls_separately_billed':True,
                'seed_values_negative':I.seed_values(reference,-1),'seed_values_positive':I.seed_values(reference,1),
                'transient_steps_s':L.STEPS,'external_pdk_include_closure_sha256':models,
                'ngspice_path':str(ngspice_path()),'ngspice_sha256':A.digest(ngspice_path()),
                'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,encoding='utf-8').strip(),**stamp()})
            def evaluate(kind,state,step,sign):
                nonlocal calls,attempts
                attempts+=1
                if attempts>6: raise RuntimeError('registered call budget exceeded')
                folder=out/f'{kind}_state{state}_sign{sign}_step{step*1e12:g}ps'
                try:
                    text=I.deck(kind,state,step,sign,reference)
                    calls+=1;spice_capture.invoke(text,folder)
                    row=extract(folder,text,kind,state,step,sign,reference,reference_ac)
                except Exception as exc:
                    folder.mkdir(parents=True,exist_ok=True)
                    row={'instrument_ok':False,'initialization_valid':False,'fail_reason':f'{type(exc).__name__}: {exc}','full_receiver_verified':False}
                row.update(kind=kind,clock_state=state,max_step_s=step,initial_polarity=sign)
                P.write_json(folder/'result.json',row)
                print(f'{attempts}/6 {folder.name}: instrument={row["instrument_ok"]} '
                      f'initialization={row["initialization_valid"]} calibration={row.get("calibration_matches")} '
                      f'HD3={row.get("ctle_hd3",{}).get("hd3_dbc")} error={row.get("fail_reason")}',flush=True)
                return row
            result=I.schedule(evaluate)
            result['sources_unchanged']=all(A.digest(ROOT/k)==v for k,v in sources.items())
            result['pdk_unchanged']=pdk_hashes()==models
            result['measurement_complete'] &= result['sources_unchanged'] and result['pdk_unchanged']
            result['primary_analog_model_pass'] &= result['sources_unchanged'] and result['pdk_unchanged']
        except Exception as exc:
            result.update(measurement_complete=False,primary_analog_model_pass=False,fail_reason=f'{type(exc).__name__}: {exc}')
        result.update(spice_calls=calls,attempted_cases=attempts,wall_seconds=time.perf_counter()-started,preflight_seconds=preflight)
        P.write_json(out/'summary.json',result)
        P.write_json(out/'evidence_sha256.json',{p.relative_to(out).as_posix():A.digest(p) for p in sorted(out.rglob('*')) if p.is_file()})
        return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True,type=Path)
    raise SystemExit(0 if run(parser.parse_args().out)['primary_analog_model_pass'] else 1)
