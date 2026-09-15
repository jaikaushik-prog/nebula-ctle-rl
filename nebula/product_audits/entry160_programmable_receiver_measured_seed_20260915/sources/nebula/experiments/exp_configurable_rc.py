"""Entry 128 bounded physical Rs/Cs CTLE screen. See its frozen plan."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time

import numpy as np

from nebula.device import configurable_rc as R, dfe_connected as F
from nebula.device.ngspice_runner import ngspice_path
from nebula.experiments import evidence_archive as A, exp_physical_bias as P
from nebula.experiments import raw_manifest
from nebula.experiments.exp_varactor_probe import pdk_hashes
from nebula.experiments.runlock import hold, stamp

ROOT=Path(__file__).resolve().parents[2]
PRIOR=ROOT/'nebula/product_audits/entry127_varactor_probe_20260909'
BASELINE_KEY='tt_1.00_27/ac_noise/ac.txt'
SOURCES=('nebula/CONFIGURABLE_RC_SCREEN_PLAN.md','nebula/device/configurable_rc.py',
 'nebula/experiments/exp_configurable_rc.py','nebula/tests/test_configurable_rc.py',
 'nebula/device/dfe_connected.py','nebula/device/dfe_voltage_audit.py',
 'nebula/device/varactor_probe.py','nebula/device/split_tuning_bank.py',
 'nebula/device/passives.py','nebula/device/sky130_runner.py',
 'nebula/device/pdk_trim.py','nebula/device/ngspice_runner.py','nebula/device/crosscheck.py',
 'nebula/report/product_scope.py','nebula/report/schematic.py',
 'nebula/common/types.py','nebula/experiments/exp_physical_bias.py',
 'nebula/experiments/exp_varactor_probe.py','nebula/experiments/exp_dfe_slicer.py',
 'nebula/experiments/evidence_archive.py','nebula/experiments/raw_manifest.py','nebula/experiments/runlock.py',
 'nebula/device/spice/.spiceinit')


def schedule(evaluate):
    cal=evaluate(None)
    result={'entry':128,'calibration':cal,'candidates':[],
            'characterization_complete':False,'connected_dfe_verified':False}
    if not cal.get('instrument_ok') or not cal.get('baseline_matches'): return result
    result['candidates']=[{'geometry':g,'result':evaluate(g)} for g in R.GEOMETRIES]
    result['characterization_complete']=all(x['result'].get('instrument_ok',False)
        and x['result'].get('baseline_matches',False) for x in result['candidates'])
    return result


def baseline_reference():
    manifest=F.SOURCE/'evidence_sha256.json'
    rows={k.replace('\\','/'):v for k,v in json.loads(manifest.read_text()).items()}
    for key in ('design.cir',BASELINE_KEY):
        if A.digest(F.SOURCE/key)!=rows[key]: raise ValueError('fixed baseline hash mismatch: '+key)
    raw=np.loadtxt(F.SOURCE/BASELINE_KEY)
    if raw.shape!=(251,2) or not np.isfinite(raw).all() or not np.allclose(raw[:,0],R.FREQUENCIES_HZ,rtol=1e-12,atol=1e-3):
        raise ValueError('malformed saved baseline spectrum')
    return raw[:,1],{'manifest_sha256':A.digest(manifest),
                    'source_sha256':rows['design.cir'],'ac_sha256':rows[BASELINE_KEY]}


def variation(rows):
    valid={ (r['r_fraction'],r['c_fraction']):r for r in rows if r['interior_peak'] }
    changes=[]
    for axis,fractions,other in (('R',R.R_FRACTIONS,R.C_FRACTIONS),('C',R.C_FRACTIONS,R.R_FRACTIONS)):
        for fixed in other:
            for lo,hi in zip(fractions[:-1],fractions[1:]):
                keys=((lo,fixed),(hi,fixed)) if axis=='R' else ((fixed,lo),(fixed,hi))
                if not all(k in valid for k in keys): continue
                a,b=(valid[k] for k in keys)
                changes.append({'changed_control':axis,'fixed_other_fraction':fixed,
                    'from_fraction':lo,'to_fraction':hi,
                    'delta_boost_db':b['boost_db']-a['boost_db'],
                    'delta_peak_hz':b['peak_frequency_hz']-a['peak_frequency_hz'],
                    'both_ac_spec_pass':a['ac_spec_pass'] and b['ac_spec_pass']})
    return changes


def run(out):
    with hold('dfe_slicer'):
        proof=raw_manifest.verify(PRIOR)
        previous=json.loads((PRIOR/'summary.json').read_text())
        if previous.get('entry')!=127 or not previous.get('characterization_complete') or not previous['calibration'].get('native_m_equivalent'):
            raise ValueError('Entry 127 is not a complete calibrated prerequisite')
        reference,baseline_proof=baseline_reference()
        out=Path(out).resolve(); out.mkdir(parents=True,exist_ok=False)
        started=time.perf_counter(); attempts=calls=0
        source_hashes={name:A.digest(ROOT/name) for name in SOURCES}
        for name in SOURCES:
            dest=out/'sources'/name; dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/name,dest)
        shutil.copyfile(F.SOURCE/'design.cir',out/'source_ctle.cir')
        shutil.copyfile(F.SOURCE/BASELINE_KEY,out/'baseline_ac.txt')
        result={'entry':128,'characterization_complete':False,'connected_dfe_verified':False}
        try:
            models=pdk_hashes()
            if models!=json.loads((PRIOR/'config.json').read_text())['external_pdk_include_closure_sha256']:
                raise ValueError('PDK differs from calibrated capacitor experiment')
            P.write_json(out/'config.json',{'entry':128,'max_calls':10,
                'prior_manifest_sha256':proof['manifest_sha256'],'prior_summary_sha256':A.digest(PRIOR/'summary.json'),
                'baseline':baseline_proof,'source_sha256':source_hashes,
                'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,encoding='utf-8').strip(),
                'geometries':R.GEOMETRIES,'r_fractions':R.R_FRACTIONS,'c_fractions':R.C_FRACTIONS,
                'geometry_inventories':[R.geometry(g) for g in R.GEOMETRIES],
                'nominal_resistor_sizing':R.resistor_targets(),
                'external_pdk_include_closure_sha256':models,
                'ngspice_path':str(ngspice_path()),'ngspice_sha256':A.digest(ngspice_path()),**stamp()})
            def evaluate(g):
                nonlocal attempts,calls
                attempts+=1
                if attempts>10: raise RuntimeError('registered call budget exceeded')
                name='calibration' if g is None else f'candidate_n{g[0]}_fixed{g[1]*1e12:g}pf'
                folder=out/name
                try:
                    deck=R.screen_deck(g); calls+=1; P.invoke(deck,folder)
                    ms=R.members(g)
                    h=R.parse_ac(np.loadtxt(folder/'ac.txt'),len(ms))
                    dc=R.parse_op(np.loadtxt(folder/'op.txt'),g)
                    row={'instrument_ok':True,'baseline_matches':R.baseline_matches(h[:,-1],reference),
                         'baseline_max_error_db':float(np.max(abs(20*np.log10(abs(h[:,-1]))-reference))),
                         'baseline_dc':dc[-1],'rows':[],'connected_dfe_verified':False}
                    for i,(cg,r,c) in enumerate(ms):
                        if cg is None: continue
                        m=R.response_metrics(h[:,i])
                        row['rows'].append({'r_fraction':r,'c_fraction':c,**m,**dc[i],
                            'ac_spec_pass':bool(m['ac_shape_pass'] and dc[i]['electrical_pass'])})
                    row['ac_spec_pass_count']=sum(x['ac_spec_pass'] for x in row['rows'])
                    row['control_variation']=variation(row['rows'])
                except Exception as exc:
                    folder.mkdir(parents=True,exist_ok=True)
                    row={'instrument_ok':False,'baseline_matches':False,'fail_reason':f'{type(exc).__name__}: {exc}',
                         'connected_dfe_verified':False}
                P.write_json(folder/'result.json',row)
                print(f'{attempts}/10 {name}: instrument_ok={row["instrument_ok"]} '
                      f'ac_pass={row.get("ac_spec_pass_count")} error={row.get("fail_reason")}',flush=True)
                return row
            result=schedule(evaluate)
            result['pdk_unchanged']=pdk_hashes()==models
            result['sources_unchanged']=all(A.digest(ROOT/name)==v for name,v in source_hashes.items())
            result['characterization_complete'] &= result['pdk_unchanged'] and result['sources_unchanged']
        except Exception as exc:
            result.update(characterization_complete=False,fail_reason=f'{type(exc).__name__}: {exc}')
        result.update(spice_calls=calls,attempted_cases=attempts,wall_seconds=time.perf_counter()-started)
        P.write_json(out/'summary.json',result)
        P.write_json(out/'evidence_sha256.json',{p.relative_to(out).as_posix():A.digest(p) for p in sorted(out.rglob('*')) if p.is_file()})
        return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    raise SystemExit(0 if run(parser.parse_args().out)['characterization_complete'] else 1)
