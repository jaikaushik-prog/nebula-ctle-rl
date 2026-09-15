"""Entry 144: fixed calibrated physical controls across the original 45 PVT points."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time
from nebula.common.types import all_corners
from nebula.link.config import LinkConfig
from nebula.device import dfe_calibrated_verification as V, dfe_configurable as C, dfe_configurable_pvt as Q
from nebula.device import dfe_connected as F, dfe_tail_bleed as B, dfe_timing as T, dfe_voltage_audit as W
from nebula.experiments import exp_dfe_calibrated_verification as N, exp_dfe_linearity_tolerance as E
from nebula.experiments import evidence_archive as A, spice_capture, exp_physical_bias as P, exp_dfe_connected as D
from nebula.experiments.exp_varactor_probe import pdk_hashes
from nebula.experiments.runlock import hold,stamp
from nebula.device.ngspice_runner import ngspice_path
ROOT=N.ROOT
PRIOR=ROOT/'nebula/product_audits/entry143_dfe_calibrated_verification_20260910'
REFERENCE=Path('link_state0_tol1e-05_step5ps/result.json')
SOURCES=tuple(sorted(set(N.SOURCES+('nebula/DFE_CALIBRATED_PVT_PLAN.md',
    'nebula/experiments/exp_dfe_calibrated_pvt.py','nebula/tests/test_dfe_calibrated_pvt.py'))))


def deck(corner):
    cfg=LinkConfig(channel_loss_db_at_nyquist=7.5)
    text=C.deck(True,corner,cfg,F.pattern(cfg),Q.PHASE,2,1)
    for name,node,fraction in [('VrcR','rctrl',V.TARGET[2]),('VrcC','cctrl',V.TARGET[3])]:
        text=V.L.replace_once(text,rf'^{name} .*$',f'{name} {node} 0 {1.8*corner.vdd_scale*fraction:.16g}')
    return text


def extract(folder,text,corner,reference):
    folder=Path(folder);log=(folder/'ngspice.log').read_text()
    E.abort_audit(log);warnings=V.L.warning_audit(log)
    cfg=LinkConfig(channel_loss_db_at_nyquist=7.5);bits=F.pattern(cfg);vdd=1.8*corner.vdd_scale
    t,y=T.read_table(A.trace_path(folder/'trace.txt'),len(F.VECTORS)+len(C.RC_VECTORS))
    main=y[:,:len(F.VECTORS)]
    r=F.analyze(t,main,bits,cfg,Q.PHASE,vdd,code=2)
    names=C.terminals(text);_,ny=T.read_table(A.trace_path(folder/'terminals.txt'),len(names),expected_time=t)
    nodes=dict(zip(names,ny.T));mos=F.all_mos(text)
    whole=W.audit(mos,nodes);new=W.audit(F.extra_mos(1)+B.bleeders(4.),nodes)
    r.update(instrument_ok=True,new_dfe_voltage_audit=new,whole_circuit_voltage_audit=whole,
        whole_circuit_voltage_envelope_pass=D.envelope(whole),
        aperture=T.aperture(t,main[:,3]-main[:,4],bits,Q.PHASE),
        tuning_controls=V.control_audit(t,y[:,len(F.VECTORS):],nodes,vdd,V.TARGET[2],V.TARGET[3]),
        new_tuning_switch_voltage_audit=W.audit([s for s in mos if s.startswith('Xrc_switch ')],nodes),
        model_warnings=warnings)
    r['signal_gate_pass']=C.accepted(r)
    r['nominal_replay_matches']=C.calibration_matches(r,reference) if corner.is_nominal else None
    return r


def prerequisites():
    proof=A.verify(PRIOR)
    summary=json.loads((PRIOR/'summary.json').read_text());config=json.loads((PRIOR/'config.json').read_text())
    if summary['entry']!=143 or summary['spice_calls']!=7 or not summary['nominal_calibrated_pass']:
        raise ValueError('missing independent calibrated nominal verification')
    if config['target']!=list(V.TARGET): raise ValueError('calibrated target changed')
    if any(A.digest(ROOT/k)!=v for k,v in config['source_sha256'].items()):
        raise ValueError('frozen scientific source changed')
    reference=json.loads((PRIOR/REFERENCE).read_text())
    if not C.accepted(reference): raise ValueError('nominal physical decoder no longer accepted')
    return proof,config,reference


def schedule(evaluate):
    result=Q.schedule(evaluate)
    result.update(entry=144,r_fraction=V.TARGET[2],c_fraction=V.TARGET[3],
        analog_pvt_verified=False,clocked_receiver_noise_verified=False)
    return result


def run(out):
    with hold('dfe_slicer'):
        started=time.perf_counter()
        proof,old,reference=prerequisites();preflight=time.perf_counter()-started
        out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
        sources={k:A.digest(ROOT/k) for k in SOURCES}
        for name in SOURCES:
            dest=out/'sources'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
        shutil.copyfile(PRIOR/REFERENCE,out/'nominal_reference.json')
        calls=0;result={'entry':144,'primary_channel_pvt_pass':False,'full_receiver_verified':False}
        try:
            models=pdk_hashes()
            if models!=old['external_pdk_include_closure_sha256']: raise ValueError('measured PDK changed')
            dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,encoding='utf-8').strip())
            P.write_json(out/'config.json',{'entry':144,'max_calls':45,'target':V.TARGET,
                'timeout_s':spice_capture.MAX_SECONDS,'source_sha256':sources,'prior_manifest_proof':proof,
                'source_snapshot_authoritative':True,'git_worktree_dirty_at_snapshot':dirty,'git_commit_is_parent_only':dirty,
                'prior_calls_separately_billed':True,'external_pdk_include_closure_sha256':models,
                'ngspice_path':str(ngspice_path()),'ngspice_sha256':A.digest(ngspice_path()),'geometry':old['geometry'],
                'corners':[str(c) for c in all_corners()],'fixed_phase_ui':Q.PHASE,'fixed_code':2,'fixed_sign':1,
                'channel_loss_db':7.5,'r_fraction':V.TARGET[2],'c_fraction':V.TARGET[3],
                'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,encoding='utf-8').strip(),**stamp()})
            def evaluate(corner):
                nonlocal calls
                folder=out/f'pvt_{corner}'
                try:
                    text=deck(corner);calls+=1
                    if calls>45: raise RuntimeError('registered call budget exceeded')
                    spice_capture.invoke(text,folder)
                    row=extract(folder,text,corner,reference)
                except Exception as exc:
                    folder.mkdir(parents=True,exist_ok=True)
                    row={'instrument_ok':False,'signal_gate_pass':False,
                         'fail_reason':f'{type(exc).__name__}: {exc}','full_receiver_verified':False}
                row['corner']=str(corner);P.write_json(folder/'result.json',row)
                print(f'{calls}/45 {corner}: pass={row["signal_gate_pass"]} '
                    f'bits={row.get("correct_bits")} eye={row.get("sampled_eye_height_v")} '
                    f'error={row.get("fail_reason")}',flush=True)
                return row
            result=schedule(evaluate)
            result['sources_unchanged']=all(A.digest(ROOT/k)==v for k,v in sources.items())
            result['pdk_unchanged']=pdk_hashes()==models
            result['primary_channel_pvt_pass'] &= result['sources_unchanged'] and result['pdk_unchanged']
        except Exception as exc:
            result.update(primary_channel_pvt_pass=False,fail_reason=f'{type(exc).__name__}: {exc}')
        result.update(spice_calls=calls,wall_seconds=time.perf_counter()-started,preflight_seconds=preflight)
        P.write_json(out/'summary.json',result)
        P.write_json(out/'evidence_sha256.json',{p.relative_to(out).as_posix():A.digest(p) for p in sorted(out.rglob('*')) if p.is_file()})
        return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True,type=Path)
    raise SystemExit(0 if run(parser.parse_args().out)['primary_channel_pvt_pass'] else 1)
