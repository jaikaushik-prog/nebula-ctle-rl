"""Entry 131: bounded fine-control characterization, not connected DFE proof."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time

import numpy as np

from nebula.device import configurable_rc as R, configurable_rc_fine as F
from nebula.device.ngspice_runner import ngspice_path
from nebula.experiments import exp_configurable_rc_precision as E
from nebula.experiments import exp_configurable_rc as C
from nebula.experiments import evidence_archive as A, raw_manifest, spice_capture
from nebula.experiments import exp_physical_bias as P
from nebula.experiments.exp_varactor_probe import pdk_hashes
from nebula.experiments.runlock import hold, stamp

ROOT=E.ROOT
PRIOR=ROOT/'nebula/product_audits/entry130_configurable_rc_precision_20260910'
SOURCES=tuple(sorted(set(E.SOURCES+('nebula/CONFIGURABLE_RC_FINE_PLAN.md',
    'nebula/device/configurable_rc_fine.py','nebula/experiments/exp_configurable_rc_fine.py',
    'nebula/tests/test_configurable_rc_fine.py'))))


def extract(folder,g,reference):
    folder=Path(folder);count=len(F.biases())
    for kind in ('op','ac'):
        if {p.name for p in folder.glob(kind+'_*.txt')}!={f'{kind}_{i:03d}.txt' for i in range(count)}:
            raise ValueError('fine OP/AC file membership mismatch')
    result={'instrument_ok':True,'baseline_matches':True,'validated_op_ac_pairs':count,
            'baseline_matches_by_step':[],'baseline_max_error_db':0.,'baseline_max_dc_drift':0.,
            'rows':[],'connected_dfe_verified':False}
    fixed=None
    for i,(r,c) in enumerate(F.biases()):
        raw=np.loadtxt(folder/f'op_{i:03d}.txt');current=F.primitives(raw,g)[1]
        if fixed is None: fixed=current
        F.check_fixed(fixed,current)
        result['baseline_max_dc_drift']=max(result['baseline_max_dc_drift'],max(abs(fixed[k]-current[k]) for k in fixed))
        dc=F.parse_op(raw,g,r,c)
        h=R.parse_ac(np.loadtxt(folder/f'ac_{i:03d}.txt'),2)
        match=R.baseline_matches(h[:,1],reference)
        result['baseline_matches_by_step'].append(match);result['baseline_matches'] &= match
        result['baseline_max_error_db']=max(result['baseline_max_error_db'],float(max(abs(20*np.log10(abs(h[:,1]))-reference))))
        if i==0: result['baseline_dc']=dc[1]
        metrics=R.response_metrics(h[:,0])
        result['rows'].append({'r_fraction':r,'c_fraction':c,**metrics,**dc[0],
            'ac_spec_pass':bool(metrics['ac_shape_pass'] and dc[0]['electrical_pass'])})
    result['ac_spec_pass_count']=sum(x['ac_spec_pass'] for x in result['rows'])
    return result


def prerequisites():
    proof=raw_manifest.verify(PRIOR)
    old=json.loads((PRIOR/'summary.json').read_text())
    config=json.loads((PRIOR/'config.json').read_text())
    if old.get('entry')!=130 or not old.get('characterization_complete') or old.get('validated_op_ac_pairs')!=729:
        raise ValueError('expected complete Entry 130 prerequisite')
    if any(A.digest(ROOT/k)!=v for k,v in config['source_sha256'].items()):
        raise ValueError('Entry 130 scientific source changed')
    return proof,config


def run(out):
    with hold('dfe_slicer'):
        proof,old_config=prerequisites();reference,baseline_proof=C.baseline_reference()
        out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
        started=time.perf_counter();calls=attempts=0
        sources={k:A.digest(ROOT/k) for k in SOURCES}
        for name in SOURCES:
            dest=out/'sources'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
        for name in ('source_ctle.cir','baseline_ac.txt'): shutil.copyfile(PRIOR/name,out/name)
        result={'entry':131,'characterization_complete':False,'connected_dfe_verified':False}
        try:
            models=pdk_hashes()
            if models!=old_config['external_pdk_include_closure_sha256']: raise ValueError('calibrated PDK changed')
            P.write_json(out/'config.json',{'entry':131,'max_calls':2,'timeout_s':spice_capture.MAX_SECONDS,
                'op_analyses_per_completed_call':441,'ac_analyses_per_completed_call':441,
                'prior_manifest_proof':proof,'prior_summary_sha256':A.digest(PRIOR/'summary.json'),
                'prior_calls_are_separately_billed':{'entry127':46,'entry128':10,'entry129':1,'entry130':9},
                'baseline':baseline_proof,'source_sha256':sources,
                'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,encoding='utf-8').strip(),
                'geometries':F.GEOMETRIES,'r_fractions':F.R_FRACTIONS,'c_fractions':F.C_FRACTIONS,
                'targets':F.TARGETS,'target_boost_tolerance_db':.5,'target_frequency_tolerance_hz':1e8,
                'geometry_inventories':[R.geometry(g) for g in F.GEOMETRIES],
                'external_pdk_include_closure_sha256':models,'ngspice_path':str(ngspice_path()),
                'ngspice_sha256':A.digest(ngspice_path()),**stamp()})
            def evaluate(g):
                nonlocal attempts,calls
                attempts+=1
                if attempts>2: raise RuntimeError('registered call budget exceeded')
                folder=out/f'candidate_n{g[0]}_fixed0pf'
                try:
                    deck=F.deck(g);calls+=1;spice_capture.invoke(deck,folder)
                    row=extract(folder,g,reference)
                except Exception as exc:
                    folder.mkdir(parents=True,exist_ok=True)
                    row={'instrument_ok':False,'baseline_matches':False,'fail_reason':f'{type(exc).__name__}: {exc}',
                         'validated_op_ac_pairs':0,'connected_dfe_verified':False}
                row['op_tables_retained']=len(list(folder.glob('op_*.txt')))
                row['ac_tables_retained']=len(list(folder.glob('ac_*.txt')))
                P.write_json(folder/'result.json',row)
                print(f'{attempts}/2 {folder.name}: instrument_ok={row["instrument_ok"]} '
                      f'ac_pass={row.get("ac_spec_pass_count")} error={row.get("fail_reason")}',flush=True)
                return row
            result=F.schedule(evaluate)
            result['pdk_unchanged']=pdk_hashes()==models
            result['sources_unchanged']=all(A.digest(ROOT/k)==v for k,v in sources.items())
            result['characterization_complete'] &= result['pdk_unchanged'] and result['sources_unchanged']
            if not result['characterization_complete']: result['selected_geometry']=None
            result['validated_op_ac_pairs']=sum(x['result']['validated_op_ac_pairs'] for x in result['candidates'])
        except Exception as exc:
            result.update(characterization_complete=False,selected_geometry=None,fail_reason=f'{type(exc).__name__}: {exc}')
        result.update(entry=131,spice_calls=calls,attempted_cases=attempts,wall_seconds=time.perf_counter()-started)
        P.write_json(out/'summary.json',result)
        P.write_json(out/'evidence_sha256.json',{p.relative_to(out).as_posix():A.digest(p) for p in sorted(out.rglob('*')) if p.is_file()})
        return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True,type=Path)
    raise SystemExit(0 if run(parser.parse_args().out)['characterization_complete'] else 1)
