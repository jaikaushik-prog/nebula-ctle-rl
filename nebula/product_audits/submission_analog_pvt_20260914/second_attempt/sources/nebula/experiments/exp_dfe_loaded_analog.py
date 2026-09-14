"""Entry 137: preregistered twenty-call maximum loaded analog screen."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time

import numpy as np

from nebula.device import dfe_loaded_analog as L, dfe_configurable as C, dfe_timing as T
from nebula.device.ngspice_runner import ngspice_path
from nebula.experiments import exp_dfe_configurable_pvt as Q, exp_physical_bias as P
from nebula.experiments import evidence_archive as A, raw_manifest as M, spice_capture
from nebula.experiments.exp_varactor_probe import pdk_hashes
from nebula.experiments.runlock import hold,stamp

ROOT=Q.ROOT
PRIOR=ROOT/'nebula/product_audits/entry133_dfe_configurable_pvt_20260910'
TUNING=ROOT/'nebula/product_audits/entry131_configurable_rc_fine_20260910'
SOURCES=tuple(sorted(set(Q.SOURCES+('nebula/DFE_LOADED_ANALOG_PLAN.md',
    'nebula/device/dfe_loaded_analog.py','nebula/experiments/exp_dfe_loaded_analog.py',
    'nebula/tests/test_dfe_loaded_analog.py'))))


def prerequisites():
    proofs={'connected_pvt':A.verify(PRIOR),'tuning_map':M.verify(TUNING)}
    old=json.loads((PRIOR/'summary.json').read_text())
    config=json.loads((PRIOR/'config.json').read_text())
    if old['entry']!=133 or not old['primary_channel_pvt_pass'] or old['spice_calls']!=45:
        raise ValueError('expected accepted fixed-control physical connected PVT')
    if any(A.digest(ROOT/k)!=v for k,v in config['source_sha256'].items()):
        raise ValueError('verified connected scientific source changed')
    tuning=json.loads((TUNING/'summary.json').read_text())
    targets=next(r['targets'] for r in tuning['candidates'] if r['geometry']==list(C.GEOMETRY))
    measured=[(t['target_boost_db'],t['target_frequency_hz'],t['r_fraction'],t['c_fraction']) for t in targets]
    if measured!=list(L.TARGETS) or not all(t['found'] for t in targets):
        raise ValueError('registered target controls differ from measured map')
    return proofs,config


def extract(folder,text,index,kind,state,step):
    folder=Path(folder)
    warnings=L.warning_audit((folder/'ngspice.log').read_text(encoding='utf-8'))
    if kind=='static':
        arrays=[np.loadtxt(folder/name) for name in ('op.txt','ac.txt','noise_total.txt','noise_spectrum.txt')]
        result=L.static_metrics(text,index,state,*arrays)
    else:
        t,y=T.read_table(A.trace_path(folder/'trace.txt'),len(L.VECTORS))
        names=L.nodes_for(text)
        _,ny=T.read_table(A.trace_path(folder/'terminals.txt'),len(names),expected_time=t)
        result=L.tone_metrics(text,index,step,t,y,dict(zip(names,ny.T)))
    return {**result,'model_warnings':warnings}


def run(out):
    with hold('dfe_slicer'):
        started=time.perf_counter()
        print('Verifying complete connected-PVT and tuning-map evidence before analog SPICE.',flush=True)
        proofs,old_config=prerequisites();preflight=time.perf_counter()-started
        out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
        sources={k:A.digest(ROOT/k) for k in SOURCES}
        for name in SOURCES:
            dest=out/'sources'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
        calls=attempts=0
        result={'entry':137,'measurement_complete':False,'nominal_loaded_screen_pass':False,'full_receiver_verified':False}
        try:
            models=pdk_hashes()
            if models!=old_config['external_pdk_include_closure_sha256']: raise ValueError('measured external PDK changed')
            P.write_json(out/'config.json',{'entry':137,'max_calls':20,'timeout_s':spice_capture.MAX_SECONDS,
                'prior_manifest_proofs':proofs,'prior_summary_sha256':A.digest(PRIOR/'summary.json'),
                'tuning_summary_sha256':A.digest(TUNING/'summary.json'),'prior_calls_separately_billed':True,
                'source_sha256':sources,'geometry':C.geometry(),'targets':L.TARGETS,
                'clock_states':[0,1],'transient_steps_s':L.STEPS,'transient_stop_s':L.STOP,
                'tone_hz':1e8,'differential_input_peak_v':.1,'clocked_receiver_noise_verified':False,
                'external_pdk_include_closure_sha256':models,'ngspice_path':str(ngspice_path()),
                'ngspice_sha256':A.digest(ngspice_path()),'numpy_version':np.__version__,
                'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,encoding='utf-8').strip(),**stamp()})
            def evaluate(index,kind,state,step):
                nonlocal calls,attempts
                attempts+=1
                if attempts>20: raise RuntimeError('registered call budget exceeded')
                folder=out/f'{kind}_target{index}_state{state}_step{step*1e12:g}ps'
                try:
                    text=L.deck(index,kind,state,step)
                    calls+=1;spice_capture.invoke(text,folder)
                    r=extract(folder,text,index,kind,state,step)
                except Exception as exc:
                    folder.mkdir(parents=True,exist_ok=True)
                    r={'instrument_ok':False,'fail_reason':f'{type(exc).__name__}: {exc}','full_receiver_verified':False}
                r.update(target_index=index,kind=kind,clock_state=state,max_step_s=step)
                P.write_json(folder/'result.json',r)
                print(f'{attempts}/20 {folder.name}: instrument={r["instrument_ok"]} '
                      f'AC/noise={r.get("small_signal_specs_pass")} HD3={r.get("ctle_hd3",{}).get("hd3_dbc")} '
                      f'error={r.get("fail_reason")}',flush=True)
                return r
            result=L.schedule(evaluate)
            result['sources_unchanged']=all(A.digest(ROOT/k)==v for k,v in sources.items())
            result['pdk_unchanged']=pdk_hashes()==models
            result['measurement_complete'] &= result['sources_unchanged'] and result['pdk_unchanged']
            result['nominal_loaded_screen_pass'] &= result['sources_unchanged'] and result['pdk_unchanged']
        except Exception as exc:
            result.update(measurement_complete=False,nominal_loaded_screen_pass=False,
                          fail_reason=f'{type(exc).__name__}: {exc}')
        result.update(spice_calls=calls,attempted_cases=attempts,wall_seconds=time.perf_counter()-started,preflight_seconds=preflight)
        P.write_json(out/'summary.json',result)
        P.write_json(out/'evidence_sha256.json',{p.relative_to(out).as_posix():A.digest(p) for p in sorted(out.rglob('*')) if p.is_file()})
        return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True,type=Path)
    raise SystemExit(0 if run(parser.parse_args().out)['nominal_loaded_screen_pass'] else 1)
