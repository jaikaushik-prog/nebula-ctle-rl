"""Entry 136: one extended settling observation; never relabel the 500 ns gate."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time

from nebula.device import configurable_rc_settling as W, configurable_rc_runtime as U, dfe_timing as T
from nebula.device.ngspice_runner import ngspice_path
from nebula.experiments import exp_configurable_rc_runtime_recovery as E, exp_physical_bias as P
from nebula.experiments import evidence_archive as A, spice_capture
from nebula.experiments.exp_varactor_probe import pdk_hashes
from nebula.experiments.runlock import hold,stamp

ROOT=E.ROOT
PRIOR=ROOT/'nebula/product_audits/entry135_configurable_rc_runtime_recovery_20260910'
SOURCES=tuple(sorted(set(E.SOURCES+('nebula/CONFIGURABLE_RC_SETTLING_OBSERVATION_PLAN.md',
    'nebula/device/configurable_rc_settling.py','nebula/experiments/exp_configurable_rc_settling.py',
    'nebula/tests/test_configurable_rc_settling.py'))))


def prerequisites():
    proof=A.verify(PRIOR)
    old=json.loads((PRIOR/'summary.json').read_text());config=json.loads((PRIOR/'config.json').read_text())
    if (old['entry']!=135 or old['spice_calls']!=4 or old['runtime_demonstration_pass']
            or not old['runtime']['instrument_ok'] or not all(r['baseline_pass'] for r in old['static'])):
        raise ValueError('expected valid prior runtime with failed settling and three accepted references')
    if any(A.digest(ROOT/k)!=v for k,v in config['source_sha256'].items()):
        raise ValueError('Entry 135 scientific source changed')
    return proof,config,old['static']


def extract(folder,references):
    folder=Path(folder)
    t,y=T.read_table(A.trace_path(folder/'trace.txt'),len(U.VECTORS))
    _,ny=T.read_table(A.trace_path(folder/'terminals.txt'),len(U.NODES),expected_time=t)
    return W.analyze(t,y,dict(zip(U.NODES,ny.T)),references)


def run(out):
    with hold('dfe_slicer'):
        started=time.perf_counter()
        print('Verifying complete Entry 135 evidence; no static SPICE reruns.',flush=True)
        proof,old_config,references=prerequisites();preflight=time.perf_counter()-started
        out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
        sources={k:A.digest(ROOT/k) for k in SOURCES}
        for name in SOURCES:
            dest=out/'sources'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
        for i in range(3): shutil.copyfile(PRIOR/f'static_{i}'/'result.json',out/f'static_reference_{i}.json')
        calls=0
        result={'entry':136,'all_transitions_settled':False,'passes_original_500ns_gate':False,
                'connected_dfe_runtime_verified':False,'full_receiver_verified':False}
        try:
            models=pdk_hashes()
            if models!=old_config['external_pdk_include_closure_sha256']: raise ValueError('measured PDK changed')
            P.write_json(out/'config.json',{'entry':136,'max_calls':1,'timeout_s':spice_capture.MAX_SECONDS,
                'prior_manifest_proof':proof,'prior_summary_sha256':A.digest(PRIOR/'summary.json'),
                'prior_entry135_calls_separately_billed':4,'source_sha256':sources,
                'geometry':old_config['geometry'],'setpoints':U.SETPOINTS,
                'frequencies_hz':U.FREQUENCIES.tolist(),'per_tone_peak_v':.001,'max_step_s':U.STEP,
                'runtime_change_starts_s':W.CHANGES.tolist(),'ramp_s':U.EDGE,'runtime_stop_s':W.STOP,
                'original_settling_limit_s':500e-9,'connected_dfe_included':False,
                'external_pdk_include_closure_sha256':models,'ngspice_path':str(ngspice_path()),
                'ngspice_sha256':A.digest(ngspice_path()),
                'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,encoding='utf-8').strip(),**stamp()})
            folder=out/'runtime_0';text=W.deck();calls+=1
            try:
                spice_capture.invoke(text,folder)
                row=extract(folder,references)
            except Exception as exc:
                folder.mkdir(parents=True,exist_ok=True)
                row={'instrument_ok':False,'all_transitions_settled':False,'passes_original_500ns_gate':False,
                     'fail_reason':f'{type(exc).__name__}: {exc}','full_receiver_verified':False}
            P.write_json(folder/'result.json',row);result.update(row)
            result['pdk_unchanged']=pdk_hashes()==models
            result['sources_unchanged']=all(A.digest(ROOT/k)==v for k,v in sources.items())
            result['all_transitions_settled'] &= result['pdk_unchanged'] and result['sources_unchanged']
            result['passes_original_500ns_gate'] &= result['pdk_unchanged'] and result['sources_unchanged']
        except Exception as exc:
            result.update(all_transitions_settled=False,passes_original_500ns_gate=False,fail_reason=f'{type(exc).__name__}: {exc}')
        result.update(spice_calls=calls,wall_seconds=time.perf_counter()-started,preflight_seconds=preflight)
        P.write_json(out/'summary.json',result)
        P.write_json(out/'evidence_sha256.json',{p.relative_to(out).as_posix():A.digest(p) for p in sorted(out.rglob('*')) if p.is_file()})
        print(f'1/1 eventual_settling={result["all_transitions_settled"]} '
              f'original_500ns_gate={result["passes_original_500ns_gate"]} error={result.get("fail_reason")}',flush=True)
        return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True,type=Path)
    raise SystemExit(0 if run(parser.parse_args().out)['all_transitions_settled'] else 1)
