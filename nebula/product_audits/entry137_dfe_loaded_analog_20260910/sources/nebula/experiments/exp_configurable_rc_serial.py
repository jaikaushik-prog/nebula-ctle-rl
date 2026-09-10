"""Entry 129: frozen geometry/bias grid, serial DC controls, retained timeout logs."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time

import numpy as np

from nebula.device import configurable_rc as R, configurable_rc_serial as S
from nebula.device.ngspice_runner import ngspice_path
from nebula.experiments import exp_configurable_rc as E, evidence_archive as A
from nebula.experiments import exp_physical_bias as P, raw_manifest, spice_capture
from nebula.experiments.exp_varactor_probe import pdk_hashes
from nebula.experiments.runlock import hold,stamp

ROOT=E.ROOT
PRIOR=ROOT/'nebula/product_audits/entry128_configurable_rc_20260910'
SOURCES=tuple(sorted(set(E.SOURCES+('nebula/CONFIGURABLE_RC_SERIAL_PLAN.md',
    'nebula/device/configurable_rc_serial.py','nebula/experiments/exp_configurable_rc_serial.py',
    'nebula/experiments/spice_capture.py','nebula/tests/test_configurable_rc_serial.py'))))


def schedule(evaluate):
    first=evaluate(R.GEOMETRIES[0])
    rows=[{'geometry':R.GEOMETRIES[0],'result':first}]
    result={'entry':129,'candidates':rows,'characterization_complete':False,'connected_dfe_verified':False}
    if not first.get('instrument_ok') or not first.get('baseline_matches'): return result
    rows += [{'geometry':g,'result':evaluate(g)} for g in R.GEOMETRIES[1:]]
    result['characterization_complete']=all(x['result'].get('instrument_ok',False)
        and x['result'].get('baseline_matches',False) for x in rows)
    return result


def extract(folder,g,reference):
    count=len(R.biases())
    if len(list(folder.glob('op_*.txt')))!=count or len(list(folder.glob('ac_*.txt')))!=count:
        raise ValueError('serial OP/AC file membership mismatch')
    ops=[np.loadtxt(folder/f'op_{i:03d}.txt') for i in range(count)]
    dc=R.parse_op(S.assemble_op(ops,g),g)
    spectra=[R.parse_ac(np.loadtxt(folder/f'ac_{i:03d}.txt'),2) for i in range(count)]
    matches=[R.baseline_matches(h[:,1],reference) for h in spectra]
    result={'instrument_ok':True,'baseline_matches':all(matches),
        'baseline_matches_by_step':matches,'baseline_dc':dc[-1],
        'baseline_max_error_db':max(float(np.max(abs(20*np.log10(abs(h[:,1]))-reference))) for h in spectra),
        'validated_op_ac_pairs':count,'rows':[],'connected_dfe_verified':False}
    for i,(r,c) in enumerate(R.biases()):
        m=R.response_metrics(spectra[i][:,0])
        result['rows'].append({'r_fraction':r,'c_fraction':c,**m,**dc[i],
            'ac_spec_pass':bool(m['ac_shape_pass'] and dc[i]['electrical_pass'])})
    result['ac_spec_pass_count']=sum(x['ac_spec_pass'] for x in result['rows'])
    result['control_variation']=E.variation(result['rows'])
    return result


def run(out):
    with hold('dfe_slicer'):
        cap_proof=raw_manifest.verify(E.PRIOR); prior_proof=raw_manifest.verify(PRIOR)
        old=json.loads((PRIOR/'summary.json').read_text())
        cap=json.loads((E.PRIOR/'summary.json').read_text())
        if not cap.get('characterization_complete') or old.get('entry')!=128 or not old['calibration'].get('instrument_ok') or not old['calibration'].get('baseline_matches'):
            raise ValueError('missing completed capacitor and fixed-CTLE prerequisites')
        old_config=json.loads((PRIOR/'config.json').read_text())
        if any(A.digest(ROOT/k)!=v for k,v in old_config['source_sha256'].items()):
            raise ValueError('Entry 128 scientific source changed')
        reference,baseline_proof=E.baseline_reference()
        out=Path(out).resolve(); out.mkdir(parents=True,exist_ok=False)
        started=time.perf_counter(); attempts=calls=0
        sources={name:A.digest(ROOT/name) for name in SOURCES}
        for name in SOURCES:
            dest=out/'sources'/name; dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/name,dest)
        shutil.copyfile(PRIOR/'source_ctle.cir',out/'source_ctle.cir')
        shutil.copyfile(PRIOR/'baseline_ac.txt',out/'baseline_ac.txt')
        result={'entry':129,'characterization_complete':False,'connected_dfe_verified':False}
        try:
            models=pdk_hashes()
            if models!=old_config['external_pdk_include_closure_sha256']: raise ValueError('calibrated PDK changed')
            P.write_json(out/'config.json',{'entry':129,'max_calls':9,'timeout_s':spice_capture.MAX_SECONDS,
                'op_analyses_per_completed_call':81,'ac_analyses_per_completed_call':81,
                'prior_manifest_sha256':prior_proof['manifest_sha256'],'capacitor_manifest_sha256':cap_proof['manifest_sha256'],
                'prior_summary_sha256':A.digest(PRIOR/'summary.json'),'prior_calls_are_separately_billed':old['spice_calls'],
                'baseline':baseline_proof,'source_sha256':sources,
                'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,encoding='utf-8').strip(),
                'geometries':R.GEOMETRIES,'r_fractions':R.R_FRACTIONS,'c_fractions':R.C_FRACTIONS,
                'geometry_inventories':[R.geometry(g) for g in R.GEOMETRIES],
                'external_pdk_include_closure_sha256':models,'ngspice_path':str(ngspice_path()),
                'ngspice_sha256':A.digest(ngspice_path()),**stamp()})
            def evaluate(g):
                nonlocal calls,attempts
                attempts+=1
                if attempts>9: raise RuntimeError('registered call budget exceeded')
                folder=out/f'candidate_n{g[0]}_fixed{g[1]*1e12:g}pf'
                try:
                    deck=S.deck(g); calls+=1
                    spice_capture.invoke(deck,folder)
                    row=extract(folder,g,reference)
                except Exception as exc:
                    folder.mkdir(parents=True,exist_ok=True)
                    row={'instrument_ok':False,'baseline_matches':False,'fail_reason':f'{type(exc).__name__}: {exc}',
                         'validated_op_ac_pairs':0,'connected_dfe_verified':False}
                row['op_tables_retained']=len(list(folder.glob('op_*.txt')))
                row['ac_tables_retained']=len(list(folder.glob('ac_*.txt')))
                P.write_json(folder/'result.json',row)
                print(f'{attempts}/9 {folder.name}: instrument_ok={row["instrument_ok"]} '
                      f'ac_pass={row.get("ac_spec_pass_count")} error={row.get("fail_reason")}',flush=True)
                return row
            result=schedule(evaluate)
            result['pdk_unchanged']=pdk_hashes()==models
            result['sources_unchanged']=all(A.digest(ROOT/k)==v for k,v in sources.items())
            result['characterization_complete'] &= result['pdk_unchanged'] and result['sources_unchanged']
            result['validated_op_ac_pairs']=sum(x['result']['validated_op_ac_pairs'] for x in result['candidates'])
        except Exception as exc:
            result.update(characterization_complete=False,fail_reason=f'{type(exc).__name__}: {exc}')
        result.update(spice_calls=calls,attempted_cases=attempts,wall_seconds=time.perf_counter()-started)
        P.write_json(out/'summary.json',result)
        P.write_json(out/'evidence_sha256.json',{p.relative_to(out).as_posix():A.digest(p) for p in sorted(out.rglob('*')) if p.is_file()})
        return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True,type=Path)
    raise SystemExit(0 if run(parser.parse_args().out)['characterization_complete'] else 1)
