"""Entry 132 seven-call first connected configurable-Rs/Cs transistor DFE gate."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time

from nebula.common.types import Corner
from nebula.link.config import LinkConfig
from nebula.device import dfe_connected as F, dfe_tail_bleed as B, dfe_timing as T
from nebula.device import dfe_voltage_audit as V, dfe_configurable as C
from nebula.device.ngspice_runner import ngspice_path
from nebula.experiments import exp_configurable_rc_fine as E
from nebula.experiments import exp_dfe_connected as D, exp_physical_bias as P
from nebula.experiments import evidence_archive as A, raw_manifest, spice_capture
from nebula.experiments.exp_varactor_probe import pdk_hashes
from nebula.experiments.runlock import hold, stamp

ROOT=E.ROOT
PRIOR=ROOT/'nebula/product_audits/entry131_configurable_rc_fine_20260910'
DFE_PRIOR=ROOT/'nebula/product_audits/entry125_dfe_tail_bleed_20260909'
CALIBRATION_KEY='pvt_tt_vdd1.00_t27_loss7.5_phase1_code2_sign1_bleedL4/result.json'
DFE_SOURCES=tuple(k[len('sources/'):] for k in json.loads((DFE_PRIOR/'evidence_sha256.json').read_text()) if k.startswith('sources/'))
SOURCES=tuple(sorted(set(E.SOURCES+DFE_SOURCES+('nebula/DFE_CONFIGURABLE_PLAN.md',
    'nebula/device/dfe_configurable.py','nebula/experiments/exp_dfe_configurable.py',
    'nebula/tests/test_dfe_configurable.py'))))


def source_prerequisites():
    proof=raw_manifest.verify(PRIOR)
    old=json.loads((PRIOR/'summary.json').read_text());config=json.loads((PRIOR/'config.json').read_text())
    if not old['characterization_complete'] or old['selected_geometry']!=list(C.GEOMETRY):
        raise ValueError('selected measured tuning geometry differs')
    selected=next(x for x in old['candidates'] if x['geometry']==list(C.GEOMETRY))
    target=next(x for x in selected['targets'] if x['target_boost_db']==9. and x['target_frequency_hz']==1.9e9)
    if not target['found'] or (target['r_fraction'],target['c_fraction'])!=(C.R_FRACTION,C.C_FRACTION):
        raise ValueError('selected measured primary controls differ')
    if any(A.digest(ROOT/k)!=v for k,v in config['source_sha256'].items()):
        raise ValueError('Entry 131 scientific source changed')
    manifest=json.loads((DFE_PRIOR/'evidence_sha256.json').read_text())
    if any(A.digest(ROOT/k)!=manifest['sources/'+k] for k in DFE_SOURCES):
        raise ValueError('verified DFE scientific source changed')
    if A.digest(DFE_PRIOR/CALIBRATION_KEY)!=manifest[CALIBRATION_KEY]:
        raise ValueError('DFE calibration reference changed')
    return proof,config,json.loads((DFE_PRIOR/CALIBRATION_KEY).read_text()),target


def extract(folder,text,tuned,phase,code,sign,reference):
    cfg=LinkConfig(channel_loss_db_at_nyquist=7.5);bits=F.pattern(cfg)
    n=len(F.VECTORS)+(len(C.RC_VECTORS) if tuned else 0)
    t,y=T.read_table(A.trace_path(folder/'trace.txt'),n)
    main=y[:,:len(F.VECTORS)]
    r=F.analyze(t,main,bits,cfg,phase,1.8,code=code)
    names=C.terminals(text)
    _,ny=T.read_table(A.trace_path(folder/'terminals.txt'),len(names),expected_time=t)
    nodes=dict(zip(names,ny.T));mos=F.all_mos(text)
    whole=V.audit(mos,nodes);new=V.audit(F.extra_mos(sign)+B.bleeders(4.),nodes)
    r.update(instrument_ok=True,new_dfe_voltage_audit=new,whole_circuit_voltage_audit=whole,
             whole_circuit_voltage_envelope_pass=D.envelope(whole),aperture=T.aperture(t,main[:,3]-main[:,4],bits,phase))
    if tuned:
        r['tuning_controls']=C.control_audit(t,y[:,len(F.VECTORS):],nodes,1.8)
        r['new_tuning_switch_voltage_audit']=V.audit([s for s in mos if s.startswith('Xrc_switch ')],nodes)
        r['signal_gate_pass']=C.accepted(r)
    else:
        r['calibration_matches']=C.calibration_matches(r,reference)
        r['signal_gate_pass']=C.H.accepted(r)
    return r


def run(out):
    with hold('dfe_slicer'):
        started=time.perf_counter()
        print('Verifying complete measured tuning and DFE prerequisites before SPICE.',flush=True)
        proof,old_config,reference,target=source_prerequisites();dfe_proof=A.verify(DFE_PRIOR)
        preflight_seconds=time.perf_counter()-started
        out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
        sources={k:A.digest(ROOT/k) for k in SOURCES}
        for name in SOURCES:
            dest=out/'sources'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
        shutil.copyfile(PRIOR/'source_ctle.cir',out/'source_ctle.cir')
        shutil.copyfile(DFE_PRIOR/CALIBRATION_KEY,out/'calibration_reference.json')
        calls=attempts=0
        result={'entry':132,'primary_connected_pass':False,'full_receiver_verified':False}
        try:
            models=pdk_hashes()
            if models!=old_config['external_pdk_include_closure_sha256']: raise ValueError('measured external PDK changed')
            P.write_json(out/'config.json',{'entry':132,'max_calls':7,'timeout_s':spice_capture.MAX_SECONDS,
                'tuning_manifest_proof':proof,'dfe_manifest_proof':dfe_proof,
                'prior_summary_sha256':A.digest(PRIOR/'summary.json'),'calibration_reference_sha256':A.digest(DFE_PRIOR/CALIBRATION_KEY),
                'prior_calls_are_separately_billed':{'entry125':57,'entry126':95,'entry127':46,'entry128':10,'entry129':1,'entry130':9,'entry131':2},
                'source_sha256':sources,'geometry':C.geometry(),'selected_standalone_target':target,
                'phases_ui':T.PHASES_UI,'bits':F.pattern(LinkConfig(channel_loss_db_at_nyquist=7.5)).tolist(),
                'external_pdk_include_closure_sha256':models,'ngspice_path':str(ngspice_path()),'ngspice_sha256':A.digest(ngspice_path()),
                'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,encoding='utf-8').strip(),**stamp()})
            def evaluate(tuned,phase,code,sign,stage):
                nonlocal calls,attempts
                attempts+=1
                if attempts>7: raise RuntimeError('registered call budget exceeded')
                folder=out/f'{stage}_tuned{int(tuned)}_phase{phase:g}_code{code}_sign{sign}'
                try:
                    cfg=LinkConfig(channel_loss_db_at_nyquist=7.5)
                    text=C.deck(tuned,Corner('tt',1.,27),cfg,F.pattern(cfg),phase,code,sign)
                    calls+=1;spice_capture.invoke(text,folder)
                    r=extract(folder,text,tuned,phase,code,sign,reference)
                except Exception as exc:
                    folder.mkdir(parents=True,exist_ok=True)
                    r={'instrument_ok':False,'signal_gate_pass':False,'fail_reason':f'{type(exc).__name__}: {exc}','full_receiver_verified':False}
                r.update(tuned=tuned,phase_ui=phase,code=code,sign=sign)
                P.write_json(folder/'result.json',r)
                print(f'{attempts}/7 {folder.name}: pass={r["signal_gate_pass"]} bits={r.get("correct_bits")} '
                      f'eye={r.get("sampled_eye_height_v")} error={r.get("fail_reason")}',flush=True)
                return r
            result=C.schedule(evaluate)
            result['pdk_unchanged']=pdk_hashes()==models
            result['sources_unchanged']=all(A.digest(ROOT/k)==v for k,v in sources.items())
            result['primary_connected_pass'] &= result['pdk_unchanged'] and result['sources_unchanged']
        except Exception as exc:
            result.update(primary_connected_pass=False,fail_reason=f'{type(exc).__name__}: {exc}')
        result.update(spice_calls=calls,attempted_cases=attempts,wall_seconds=time.perf_counter()-started,preflight_seconds=preflight_seconds)
        P.write_json(out/'summary.json',result)
        P.write_json(out/'evidence_sha256.json',{p.relative_to(out).as_posix():A.digest(p) for p in sorted(out.rglob('*')) if p.is_file()})
        return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True,type=Path)
    raise SystemExit(0 if run(parser.parse_args().out)['primary_connected_pass'] else 1)
