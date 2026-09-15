"""Entry 127: bounded official-model capacitor probe, no CTLE insertion."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time

import numpy as np

from nebula.common.types import Corner, all_corners
from nebula.device import pdk_trim as PT, varactor_probe as V
from nebula.device.ngspice_runner import ngspice_path
from nebula.device.split_tuning_bank import G_ERROR_LIMIT_S
from nebula.experiments import evidence_archive as A, exp_physical_bias as P
from nebula.experiments.runlock import hold, stamp

ROOT=Path(__file__).resolve().parents[2]
PRIOR=ROOT/'nebula/product_audits/entry126_dfe_timing_20260909'
SOURCES=('nebula/VARACTOR_PROBE_PLAN.md','nebula/device/varactor_probe.py',
    'nebula/experiments/exp_varactor_probe.py','nebula/tests/test_varactor_probe.py',
    'nebula/device/pdk_trim.py','nebula/device/ngspice_runner.py',
    'nebula/device/crosscheck.py','nebula/device/split_tuning_bank.py',
    'nebula/common/types.py','nebula/experiments/exp_physical_bias.py',
    'nebula/experiments/evidence_archive.py','nebula/experiments/runlock.py',
    'nebula/device/spice/.spiceinit')


def schedule(evaluate):
    calibration=evaluate('calibration',Corner('tt',1,27))
    result={'entry':127,'calibration':calibration,'pvt':[],
            'characterization_complete':False,'configurable_ctle_verified':False}
    if not calibration.get('instrument_ok') or not calibration.get('native_m_equivalent'):
        return result
    result['pvt']=[{'corner':str(c),'result':evaluate('probe',c)} for c in all_corners()]
    result['characterization_complete']=all(r['result'].get('instrument_ok',False) for r in result['pvt'])
    return result


def pdk_hashes():
    # Unlike the trim consumer tree, retain every parameter deck in this audit.
    closure={}
    PT._walk(V.FULL_LIB,closure,set())
    return {p.as_posix():A.digest(p) for p in sorted(closure)}


def run(out):
    with hold('dfe_slicer'):
        proof=A.verify(PRIOR)
        old=json.loads((PRIOR/'summary.json').read_text())
        if old['entry']!=126: raise ValueError('unexpected preceding DFE stage')
        out=Path(out).resolve(); out.mkdir(parents=True,exist_ok=False)
        started=time.perf_counter(); attempts=calls=0
        for name in SOURCES:
            dest=out/'sources'/name
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/name,dest)
        result={'entry':127,'characterization_complete':False,'configurable_ctle_verified':False}
        try:
            models=pdk_hashes()
            P.write_json(out/'config.json',{'entry':127,'max_calls':46,
                'prior_manifest_sha256':proof['manifest_sha256'],
                'prior_summary_sha256':A.digest(PRIOR/'summary.json'),
                'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                'frequencies_hz':V.FREQUENCIES_HZ,'source_biases_v':V.SOURCE_BIASES_V,
                'tuning_fractions':V.TUNING_FRACTIONS,'candidate_geometry':V.candidate_geometry(),
                'external_pdk_include_closure_sha256':models,
                'ngspice_path':str(ngspice_path()),'ngspice_sha256':A.digest(ngspice_path()),
                'historical_entry96_g_error_limit_s':G_ERROR_LIMIT_S,
                'historical_limit_is_not_a_current_gate':True,**stamp()})
            def evaluate(kind,corner):
                nonlocal attempts,calls
                attempts+=1
                if attempts>46: raise RuntimeError('registered call budget exceeded')
                folder=out/f'{kind}_{corner}'
                try:
                    cal=kind=='calibration'
                    deck=V.calibration_deck() if cal else V.probe_deck(corner)
                    calls+=1
                    P.invoke(deck,folder)
                    expected=V.calibration_op_expected() if cal else V.probe_op_expected(corner)
                    V.check_op(np.loadtxt(folder/'op.txt'),expected)
                    currents=V.parse_ac(np.loadtxt(folder/'admittance.txt'),72 if cal else 410)
                    row=V.calibration_currents_metrics(currents) if cal else V.probe_metrics(currents,corner)
                    row.update(instrument_ok=True,configurable_ctle_verified=False)
                except Exception as exc:
                    folder.mkdir(parents=True,exist_ok=True)
                    row={'instrument_ok':False,'fail_reason':f'{type(exc).__name__}: {exc}',
                         'configurable_ctle_verified':False}
                P.write_json(folder/'result.json',row)
                print(f'{attempts}/46 {folder.name}: instrument_ok={row["instrument_ok"]} '
                      f'error={row.get("fail_reason")}',flush=True)
                return row
            result=schedule(evaluate)
            result['pdk_unchanged']=pdk_hashes()==models
            result['characterization_complete'] &= result['pdk_unchanged']
        except Exception as exc:
            result.update(characterization_complete=False,fail_reason=f'{type(exc).__name__}: {exc}')
        result.update(spice_calls=calls,attempted_cases=attempts,wall_seconds=time.perf_counter()-started)
        P.write_json(out/'summary.json',result)
        P.write_json(out/'evidence_sha256.json',{
            p.relative_to(out).as_posix():A.digest(p) for p in sorted(out.rglob('*')) if p.is_file()})
        return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True,type=Path)
    raise SystemExit(0 if run(parser.parse_args().out)['characterization_complete'] else 1)
