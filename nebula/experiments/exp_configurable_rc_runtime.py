"""Entry 134: four-call runtime control gate, with immutable raw evidence."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time

import numpy as np

from nebula.device import configurable_rc as R, configurable_rc_fine as F
from nebula.device import configurable_rc_runtime as U, dfe_timing as T
from nebula.device.ngspice_runner import ngspice_path
from nebula.experiments import exp_configurable_rc_fine as E, exp_physical_bias as P
from nebula.experiments import exp_dfe_configurable_pvt as H
from nebula.experiments import evidence_archive as A, raw_manifest, spice_capture
from nebula.experiments.exp_varactor_probe import pdk_hashes
from nebula.experiments.runlock import hold,stamp

ROOT=E.ROOT
PRIOR=ROOT/'nebula/product_audits/entry131_configurable_rc_fine_20260910'
SOURCES=tuple(sorted(set(E.SOURCES+H.SOURCES+('nebula/CONFIGURABLE_RC_RUNTIME_PLAN.md',
    'nebula/device/configurable_rc_runtime.py','nebula/experiments/exp_configurable_rc_runtime.py',
    'nebula/tests/test_configurable_rc_runtime.py','nebula/device/dfe_timing.py'))))


def prerequisites():
    proof=raw_manifest.verify(PRIOR)
    old=json.loads((PRIOR/'summary.json').read_text());config=json.loads((PRIOR/'config.json').read_text())
    if old['entry']!=131 or not old['characterization_complete'] or old['selected_geometry']!=[500,0.]:
        raise ValueError('missing selected fine-control prerequisite')
    if any(A.digest(ROOT/k)!=v for k,v in config['source_sha256'].items()):
        raise ValueError('Entry 131 scientific source changed')
    candidate=next(x for x in old['candidates'] if x['geometry']==[500,0.])
    rows=candidate['result']['rows'];refs=[]
    for r,c in U.SETPOINTS:
        i=F.biases().index((r,c));dc=rows[i]
        if not dc['ac_spec_pass'] or dc['r_fraction']!=r or dc['c_fraction']!=c:
            raise ValueError('missing measured static control identity')
        path=PRIOR/'candidate_n500_fixed0pf'/f'ac_{i:03d}.txt'
        refs.append({'dc':dc,'ac':R.parse_ac(np.loadtxt(path),2)[:,0],
                     'step_index':i,'ac_sha256':A.digest(path)})
    return proof,config,refs


def extract(folder,kind,index,prior,references):
    folder=Path(folder)
    t,y=T.read_table(A.trace_path(folder/'trace.txt'),len(U.VECTORS))
    _,ny=T.read_table(A.trace_path(folder/'terminals.txt'),len(U.NODES),expected_time=t)
    nodes=dict(zip(U.NODES,ny.T))
    if kind=='runtime': return U.analyze(t,y,nodes,kind,index,references)
    cal=U.reference_match(np.loadtxt(folder/'op.txt'),np.loadtxt(folder/'ac.txt'),index,prior[index])
    h=U.tone_reference(np.loadtxt(folder/'tones.txt'))
    cal.update(tone_real=h.real.tolist(),tone_imag=h.imag.tolist(),low_frequency_gain=float(abs(h[0])))
    refs=list(references);refs[index]=cal
    result={**cal,**U.analyze(t,y,nodes,kind,index,refs)}
    result['baseline_pass']=bool(result['reference_matches'] and result['static_transient_pass'])
    return result


def run(out):
    with hold('dfe_slicer'):
        started=time.perf_counter()
        print('Verifying complete Entry 131 runtime prerequisite before SPICE.',flush=True)
        proof,old_config,prior=prerequisites();preflight=time.perf_counter()-started
        out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
        sources={k:A.digest(ROOT/k) for k in SOURCES}
        for name in SOURCES:
            dest=out/'sources'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
        for i,ref in enumerate(prior):
            P.write_json(out/f'static_reference_{i}.json',{'dc':ref['dc'],'ac_real':ref['ac'].real.tolist(),
                'ac_imag':ref['ac'].imag.tolist(),'step_index':ref['step_index'],'ac_sha256':ref['ac_sha256']})
        calls=attempts=0;references=[None]*3
        result={'entry':134,'runtime_demonstration_pass':False,'full_receiver_verified':False}
        try:
            models=pdk_hashes()
            if models!=old_config['external_pdk_include_closure_sha256']: raise ValueError('measured PDK changed')
            P.write_json(out/'config.json',{'entry':134,'max_calls':4,'timeout_s':spice_capture.MAX_SECONDS,
                'prior_manifest_proof':proof,'prior_summary_sha256':A.digest(PRIOR/'summary.json'),
                'prior_entry131_calls_separately_billed':2,'source_sha256':sources,'setpoints':U.SETPOINTS,
                'frequencies_hz':U.FREQUENCIES.tolist(),'per_tone_peak_v':.001,'max_step_s':U.STEP,
                'runtime_change_starts_s':U.CHANGES.tolist(),'ramp_s':U.EDGE,'runtime_stop_s':U.STOP,
                'geometry':R.geometry(U.GEOMETRY),'connected_dfe_included':False,
                'external_pdk_include_closure_sha256':models,'ngspice_path':str(ngspice_path()),
                'ngspice_sha256':A.digest(ngspice_path()),
                'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,encoding='utf-8').strip(),**stamp()})
            def evaluate(kind,index):
                nonlocal calls,attempts
                attempts+=1
                if attempts>4: raise RuntimeError('registered call budget exceeded')
                folder=out/f'{kind}_{index}'
                try:
                    text=U.deck(kind,index);calls+=1;spice_capture.invoke(text,folder)
                    row=extract(folder,kind,index,prior,references)
                    if kind=='static': references[index]=row
                except Exception as exc:
                    folder.mkdir(parents=True,exist_ok=True)
                    row={'instrument_ok':False,'baseline_pass':False,'runtime_pass':False,
                         'fail_reason':f'{type(exc).__name__}: {exc}','full_receiver_verified':False}
                row.update(kind=kind,index=index);P.write_json(folder/'result.json',row)
                print(f'{attempts}/4 {kind}_{index}: baseline={row.get("baseline_pass")} '
                      f'runtime={row.get("runtime_pass")} error={row.get("fail_reason")}',flush=True)
                return row
            result=U.schedule(evaluate)
            result['pdk_unchanged']=pdk_hashes()==models
            result['sources_unchanged']=all(A.digest(ROOT/k)==v for k,v in sources.items())
            result['runtime_demonstration_pass'] &= result['pdk_unchanged'] and result['sources_unchanged']
        except Exception as exc:
            result.update(runtime_demonstration_pass=False,fail_reason=f'{type(exc).__name__}: {exc}')
        result.update(spice_calls=calls,attempted_cases=attempts,wall_seconds=time.perf_counter()-started,preflight_seconds=preflight)
        P.write_json(out/'summary.json',result)
        P.write_json(out/'evidence_sha256.json',{p.relative_to(out).as_posix():A.digest(p) for p in sorted(out.rglob('*')) if p.is_file()})
        return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True,type=Path)
    raise SystemExit(0 if run(parser.parse_args().out)['runtime_demonstration_pass'] else 1)
