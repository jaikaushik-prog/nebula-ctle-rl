"""Entry 130: bounded solver-precision recovery with frozen physical evidence gates."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time

from nebula.device import configurable_rc as R, configurable_rc_precision as Q
from nebula.device.ngspice_runner import ngspice_path
from nebula.experiments import exp_configurable_rc_serial as E
from nebula.experiments import evidence_archive as A, raw_manifest, spice_capture
from nebula.experiments import exp_physical_bias as P
from nebula.experiments.exp_varactor_probe import pdk_hashes
from nebula.experiments.runlock import hold, stamp

ROOT=E.ROOT
PRIOR=ROOT/'nebula/product_audits/entry129_configurable_rc_serial_20260910'
SOURCES=tuple(sorted(set(E.SOURCES+('nebula/CONFIGURABLE_RC_PRECISION_PLAN.md',
    'nebula/device/configurable_rc_precision.py','nebula/experiments/exp_configurable_rc_precision.py',
    'nebula/tests/test_configurable_rc_precision.py'))))


def prerequisites():
    proofs={str(p.relative_to(ROOT)):raw_manifest.verify(p) for p in (E.E.PRIOR,E.PRIOR,PRIOR)}
    old=json.loads((PRIOR/'summary.json').read_text())
    config=json.loads((PRIOR/'config.json').read_text())
    if (old.get('entry')!=129 or old.get('spice_calls')!=1 or old.get('characterization_complete')
            or old['candidates'][0]['result']['fail_reason']!='ValueError: fixed baseline DC changed across serial controls'):
        raise ValueError('expected preserved Entry 129 validation failure')
    if any(A.digest(ROOT/k)!=v for k,v in config['source_sha256'].items()):
        raise ValueError('Entry 129 scientific source changed')
    return proofs,config


def run(out):
    with hold('dfe_slicer'):
        proofs,old_config=prerequisites()
        reference,baseline_proof=E.E.baseline_reference()
        out=Path(out).resolve(); out.mkdir(parents=True,exist_ok=False)
        started=time.perf_counter(); calls=attempts=0
        sources={k:A.digest(ROOT/k) for k in SOURCES}
        for name in SOURCES:
            dest=out/'sources'/name; dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/name,dest)
        for name in ('source_ctle.cir','baseline_ac.txt'): shutil.copyfile(PRIOR/name,out/name)
        result={'entry':130,'characterization_complete':False,'connected_dfe_verified':False}
        try:
            models=pdk_hashes()
            if models!=old_config['external_pdk_include_closure_sha256']: raise ValueError('calibrated PDK changed')
            P.write_json(out/'config.json',{'entry':130,'max_calls':9,'timeout_s':spice_capture.MAX_SECONDS,
                'solver_options':Q.OPTIONS,'op_analyses_per_completed_call':81,'ac_analyses_per_completed_call':81,
                'prior_manifest_proofs':proofs,'prior_summary_sha256':A.digest(PRIOR/'summary.json'),
                'prior_calls_are_separately_billed':{'entry127':46,'entry128':10,'entry129':1},
                'baseline':baseline_proof,'source_sha256':sources,
                'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,encoding='utf-8').strip(),
                'geometries':R.GEOMETRIES,'r_fractions':R.R_FRACTIONS,'c_fractions':R.C_FRACTIONS,
                'geometry_inventories':[R.geometry(g) for g in R.GEOMETRIES],
                'external_pdk_include_closure_sha256':models,'ngspice_path':str(ngspice_path()),
                'ngspice_sha256':A.digest(ngspice_path()),**stamp()})
            def evaluate(g):
                nonlocal attempts,calls
                attempts+=1
                if attempts>9: raise RuntimeError('registered call budget exceeded')
                folder=out/f'candidate_n{g[0]}_fixed{g[1]*1e12:g}pf'
                try:
                    deck=Q.deck(g); calls+=1
                    spice_capture.invoke(deck,folder)
                    row=E.extract(folder,g,reference)
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
            result=E.schedule(evaluate)
            result['pdk_unchanged']=pdk_hashes()==models
            result['sources_unchanged']=all(A.digest(ROOT/k)==v for k,v in sources.items())
            result['characterization_complete'] &= result['pdk_unchanged'] and result['sources_unchanged']
            result['validated_op_ac_pairs']=sum(x['result']['validated_op_ac_pairs'] for x in result['candidates'])
        except Exception as exc:
            result.update(characterization_complete=False,fail_reason=f'{type(exc).__name__}: {exc}')
        result.update(entry=130,spice_calls=calls,attempted_cases=attempts,wall_seconds=time.perf_counter()-started)
        P.write_json(out/'summary.json',result)
        P.write_json(out/'evidence_sha256.json',{p.relative_to(out).as_posix():A.digest(p) for p in sorted(out.rglob('*')) if p.is_file()})
        return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True,type=Path)
    raise SystemExit(0 if run(parser.parse_args().out)['characterization_complete'] else 1)
