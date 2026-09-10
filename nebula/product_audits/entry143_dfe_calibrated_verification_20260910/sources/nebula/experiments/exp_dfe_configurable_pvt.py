"""Entry 133 bounded fixed-setting electrical PVT of the configurable transistor DUT."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time

from nebula.common.types import all_corners
from nebula.link.config import LinkConfig
from nebula.device import dfe_connected as F,dfe_configurable as C,dfe_configurable_pvt as Q
from nebula.device.ngspice_runner import ngspice_path
from nebula.experiments import exp_dfe_configurable as E,exp_physical_bias as P
from nebula.experiments import evidence_archive as A,spice_capture
from nebula.experiments.exp_varactor_probe import pdk_hashes
from nebula.experiments.runlock import hold,stamp

ROOT=E.ROOT
PRIOR=ROOT/'nebula/product_audits/entry132_dfe_configurable_20260910'
REFERENCE_KEY='phase_tuned1_phase1_code2_sign1/result.json'
SOURCES=tuple(sorted(set(E.SOURCES+('nebula/DFE_CONFIGURABLE_PVT_PLAN.md',
    'nebula/device/dfe_configurable_pvt.py','nebula/experiments/exp_dfe_configurable_pvt.py',
    'nebula/tests/test_dfe_configurable_pvt.py'))))


def source_prerequisites():
    old=json.loads((PRIOR/'summary.json').read_text());config=json.loads((PRIOR/'config.json').read_text())
    if old['entry']!=132 or not old['primary_connected_pass'] or old['selected_phase_ui']!=Q.PHASE:
        raise ValueError('missing selected connected-DUT prerequisite')
    if any(A.digest(ROOT/k)!=v for k,v in config['source_sha256'].items()):
        raise ValueError('Entry 132 scientific source changed')
    manifest=json.loads((PRIOR/'evidence_sha256.json').read_text())
    if A.digest(PRIOR/REFERENCE_KEY)!=manifest[REFERENCE_KEY]:
        raise ValueError('connected nominal reference changed')
    reference=json.loads((PRIOR/REFERENCE_KEY).read_text())
    if not C.accepted(reference): raise ValueError('nominal reference no longer accepted')
    return config,reference


def run(out):
    with hold('dfe_slicer'):
        started=time.perf_counter()
        print('Verifying complete connected-DUT prerequisite before PVT SPICE.',flush=True)
        old_config,reference=source_prerequisites();proof=A.verify(PRIOR)
        preflight_seconds=time.perf_counter()-started
        out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
        sources={k:A.digest(ROOT/k) for k in SOURCES}
        for name in SOURCES:
            dest=out/'sources'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
        shutil.copyfile(PRIOR/'source_ctle.cir',out/'source_ctle.cir')
        shutil.copyfile(PRIOR/REFERENCE_KEY,out/'nominal_reference.json')
        calls=attempts=0
        result={'entry':133,'primary_channel_pvt_pass':False,'full_receiver_verified':False}
        try:
            models=pdk_hashes();cfg=LinkConfig(channel_loss_db_at_nyquist=7.5);bits=F.pattern(cfg)
            if models!=old_config['external_pdk_include_closure_sha256']: raise ValueError('measured PDK changed')
            if bits.tolist()!=old_config['bits']: raise ValueError('measured bit sequence changed')
            P.write_json(out/'config.json',{'entry':133,'max_calls':45,'timeout_s':spice_capture.MAX_SECONDS,
                'prior_manifest_proof':proof,'prior_summary_sha256':A.digest(PRIOR/'summary.json'),
                'nominal_reference_sha256':A.digest(PRIOR/REFERENCE_KEY),'prior_entry132_calls_separately_billed':7,
                'source_sha256':sources,'geometry':C.geometry(),'r_fraction':C.R_FRACTION,'c_fraction':C.C_FRACTION,
                'fixed_phase_ui':Q.PHASE,'fixed_code':2,'fixed_sign':1,'screen_corners':[str(c) for c in Q.SCREENS],
                'all_corners':[str(c) for c in all_corners()],'bits':bits.tolist(),'channel_loss_db':7.5,
                'external_pdk_include_closure_sha256':models,'ngspice_path':str(ngspice_path()),'ngspice_sha256':A.digest(ngspice_path()),
                'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,encoding='utf-8').strip(),**stamp()})
            def evaluate(corner):
                nonlocal calls,attempts
                attempts+=1
                if attempts>45: raise RuntimeError('registered call budget exceeded')
                folder=out/f'pvt_{corner}'
                try:
                    text=C.deck(True,corner,cfg,bits,Q.PHASE,2,1)
                    calls+=1;spice_capture.invoke(text,folder)
                    r=Q.extract(folder,text,corner,reference)
                except Exception as exc:
                    folder.mkdir(parents=True,exist_ok=True)
                    r={'instrument_ok':False,'signal_gate_pass':False,'fail_reason':f'{type(exc).__name__}: {exc}','full_receiver_verified':False}
                r['corner']=str(corner);P.write_json(folder/'result.json',r)
                print(f'{attempts}/45 {corner}: pass={r["signal_gate_pass"]} bits={r.get("correct_bits")} '
                      f'eye={r.get("sampled_eye_height_v")} nominal_match={r.get("nominal_replay_matches")} '
                      f'error={r.get("fail_reason")}',flush=True)
                return r
            result=Q.schedule(evaluate)
            result['pdk_unchanged']=pdk_hashes()==models
            result['sources_unchanged']=all(A.digest(ROOT/k)==v for k,v in sources.items())
            result['primary_channel_pvt_pass'] &= result['pdk_unchanged'] and result['sources_unchanged']
        except Exception as exc:
            result.update(primary_channel_pvt_pass=False,fail_reason=f'{type(exc).__name__}: {exc}')
        result.update(spice_calls=calls,attempted_cases=attempts,wall_seconds=time.perf_counter()-started,preflight_seconds=preflight_seconds)
        P.write_json(out/'summary.json',result)
        P.write_json(out/'evidence_sha256.json',{p.relative_to(out).as_posix():A.digest(p) for p in sorted(out.rglob('*')) if p.is_file()})
        return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True,type=Path)
    raise SystemExit(0 if run(parser.parse_args().out)['primary_channel_pvt_pass'] else 1)
