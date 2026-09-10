"""Entry 142: bounded loaded control calibration of the unchanged physical DUT."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time
import numpy as np
from nebula.experiments import exp_dfe_linearity_tolerance as E, evidence_archive as A, raw_manifest as M
from nebula.experiments import exp_physical_bias as P, spice_capture
from nebula.experiments.exp_varactor_probe import pdk_hashes
from nebula.experiments.runlock import hold,stamp
from nebula.device import dfe_loaded_initialization as I, dfe_loaded_analog as L, configurable_rc as R
from nebula.device import dfe_connected as F, dfe_tail_bleed as B, dfe_voltage_audit as V
from nebula.experiments import exp_dfe_connected as D
from nebula.device.ngspice_runner import ngspice_path

ROOT=E.ROOT
PRIOR=ROOT/'nebula/product_audits/entry141_dfe_linearity_tolerance_20260910'
STATIC=ROOT/'nebula/product_audits/entry138_dfe_loaded_initialization_20260910'
SOURCES=tuple(sorted(set(E.SOURCES+('nebula/DFE_LOADED_CALIBRATION_PLAN.md',
    'nebula/experiments/exp_dfe_loaded_calibration.py','nebula/tests/test_dfe_loaded_calibration.py'))))
R_FRACTIONS=(.7,.68,.69,.71,.72)
C_FRACTIONS=tuple(round(.165+.005*i,3) for i in range(13))


def biases(): return [(r,c) for r in R_FRACTIONS for c in C_FRACTIONS]


def deck(reference):
    body=I.deck('static',0,5e-12,-1,reference).split('.control')[0]
    names=L.nodes_for(body)
    lines=['.control','set noaskquit','set numdgt=15','set wr_singlescale']
    for i,(r,c) in enumerate(biases()):
        lines += [f'alter VrcR {1.8*r:.16g}',f'alter VrcC {1.8*c:.16g}',
            'op',f'wrdata op_{i:03d}.txt '+' '.join(f'v({n})' for n in names)+' i(vdd)',
            'ac dec 50 1meg 100g',f'wrdata ac_{i:03d}.txt v(outp) v(outn) v(vid)']
    return body+'\n'.join(lines+['quit','.endc','.end'])+'\n'


def parse_row(text,r,c,op,ac):
    names=L.nodes_for(text);op=np.atleast_2d(np.asarray(op,dtype=float))
    if op.shape!=(1,len(names)+2) or not np.isfinite(op).all():
        raise ValueError('malformed loaded calibration DC')
    nodes={n:op[:,j+1] for j,n in enumerate(names)}
    for n,value in [('vid',0.),('df_clk',.6),('df_clkb',1.2),('vdd',1.8),('rctrl',1.8*r),('cctrl',1.8*c)]:
        if np.max(abs(nodes[n]-value))>1e-8: raise ValueError('wrong calibration input/clock/control')
    power=float(-1.8*op[0,-1])
    if power<=0: raise ValueError('nonpositive calibration power')
    branch=bool(float(nodes['df_q'][0]-nodes['df_qb'][0])<-.1)
    whole=V.audit(F.all_mos(text),nodes)
    new=V.audit(F.extra_mos(1)+B.bleeders(4.),nodes)
    switch=V.audit([s for s in F.all_mos(text) if s.startswith('Xrc_switch ')],nodes)
    varactor=all(np.all((nodes[n]>=0)&(nodes[n]<=1.95)&(abs(nodes[n]-nodes['rc_ct'])<=2)) for n in ('s1','s2'))
    varactor &= bool(np.all((nodes['rc_ct']>=0)&(nodes['rc_ct']<=1.95)))
    electrical=bool(branch and varactor and D.envelope(whole) and new['documented_ranges_ok'] and power<.015)
    response=R.response_metrics(R.parse_ac(ac,1)[:,0])
    return {'r_fraction':r,'c_fraction':c,**response,'vdd_power_w':power,
        'dc_nodes_v':{n:float(v[0]) for n,v in nodes.items()},'negative_branch_valid':branch,
        'whole_circuit_voltage_audit':whole,'new_dfe_voltage_audit':new,'new_tuning_switch_voltage_audit':switch,
        'varactor_voltage_envelope_pass':bool(varactor),'electrical_pass':electrical,
        'ac_spec_pass':bool(electrical and response['ac_shape_pass'])}


def calibration_matches(row,reference,ac,reference_ac):
    try:
        a,b=R.parse_ac(ac,1)[:,0],R.parse_ac(reference_ac,1)[:,0]
        old=reference['dc_nodes_v'];new=row['dc_nodes_v']
        return bool(set(old)==set(new) and all(abs(old[n]-new[n])<=1e-6 for n in old)
            and np.max(abs(a/b-1))<=1e-4 and abs(row['vdd_power_w']-reference['vdd_power_w'])<=1e-7)
    except (ValueError,KeyError): return False


def select(rows):
    candidates=[]
    for row in rows:
        db=abs(row['boost_db']-9.);df=abs(row['peak_frequency_hz']-1.9e9)
        if row['ac_spec_pass'] and db<=.5 and df<=1e8:
            candidates.append(((db/.5)**2+(df/1e8)**2,row['r_fraction'],row['c_fraction'],row))
    result={'target_boost_db':9.,'target_frequency_hz':1.9e9,'found':bool(candidates),
            'target_tolerance_is_internal':True}
    if candidates:
        error,r,c,row=min(candidates,key=lambda x:x[:3])
        result.update(normalized_squared_error=error,selected={k:row[k] for k in
            ('r_fraction','c_fraction','boost_db','peak_frequency_hz','vdd_power_w')})
    return result


def prerequisites():
    proofs={'linearity':A.verify(PRIOR),'static':M.verify(STATIC)}
    s=json.loads((PRIOR/'summary.json').read_text());config=json.loads((PRIOR/'config.json').read_text())
    if s['entry']!=141 or s['spice_calls']!=4 or not s['clocked_ctle_hd3_model_pass']:
        raise ValueError('missing four-way loaded linearity prerequisite')
    if any(A.digest(ROOT/k)!=v for k,v in config['source_sha256'].items()):
        raise ValueError('frozen scientific source changed')
    folder=STATIC/'static_state0_sign-1_step5ps'
    reference=json.loads((folder/'result.json').read_text());ac=np.loadtxt(folder/'ac.txt')
    if not reference['initialization_valid'] or not reference['small_signal_specs_pass']:
        raise ValueError('missing accepted loaded baseline')
    return proofs,config,reference,ac


def extract(folder,text,reference,reference_ac):
    folder=Path(folder);warnings=L.warning_audit((folder/'ngspice.log').read_text())
    for kind in ('op','ac'):
        if {p.name for p in folder.glob(kind+'_*.txt')}!={f'{kind}_{i:03d}.txt' for i in range(65)}:
            raise ValueError('incomplete or extra calibration file membership')
    rows=[]
    for i,(r,c) in enumerate(biases()):
        ac=np.loadtxt(folder/f'ac_{i:03d}.txt')
        row=parse_row(text,r,c,np.loadtxt(folder/f'op_{i:03d}.txt'),ac)
        if i==0 and not calibration_matches(row,reference,ac,reference_ac):
            raise ValueError('loaded baseline calibration failed')
        rows.append(row)
    return {'instrument_ok':True,'baseline_matches':True,'rows':rows,'selection':select(rows),
        'model_warnings':warnings,'selected_controls_transient_verified':False,
        'selected_controls_noise_verified':False,'selected_controls_pvt_verified':False,
        'nine_target_map_verified':False,'full_receiver_verified':False}


def run(out):
    with hold('dfe_slicer'):
        started=time.perf_counter()
        proofs,old,reference,reference_ac=prerequisites();preflight=time.perf_counter()-started
        out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
        sources={k:A.digest(ROOT/k) for k in SOURCES}
        for name in SOURCES:
            dest=out/'sources'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
        for source,dest in [('result.json','reference_result.json'),('ac.txt','reference_ac.txt')]:
            shutil.copyfile(STATIC/'static_state0_sign-1_step5ps'/source,out/dest)
        calls=0;result={'entry':142,'instrument_ok':False,'target_found':False,'full_receiver_verified':False}
        try:
            models=pdk_hashes()
            if models!=old['external_pdk_include_closure_sha256']: raise ValueError('measured PDK changed')
            dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,encoding='utf-8').strip())
            P.write_json(out/'config.json',{'entry':142,'max_calls':1,'op_ac_pairs':65,'biases':biases(),
                'timeout_s':spice_capture.MAX_SECONDS,'source_sha256':sources,'prior_manifest_proofs':proofs,
                'source_snapshot_authoritative':True,'git_worktree_dirty_at_snapshot':dirty,'git_commit_is_parent_only':dirty,
                'prior_calls_separately_billed':True,'external_pdk_include_closure_sha256':models,
                'ngspice_path':str(ngspice_path()),'ngspice_sha256':A.digest(ngspice_path()),'geometry':old['geometry'],
                'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,encoding='utf-8').strip(),**stamp()})
            text=deck(reference);folder=out/'calibration';calls+=1;spice_capture.invoke(text,folder)
            result.update(extract(folder,text,reference,reference_ac))
            result['target_found']=result['selection']['found']
            result['sources_unchanged']=all(A.digest(ROOT/k)==v for k,v in sources.items())
            result['pdk_unchanged']=pdk_hashes()==models
            result['target_found'] &= result['sources_unchanged'] and result['pdk_unchanged']
        except Exception as exc:
            result.update(instrument_ok=False,target_found=False,fail_reason=f'{type(exc).__name__}: {exc}')
        result.update(spice_calls=calls,wall_seconds=time.perf_counter()-started,preflight_seconds=preflight)
        P.write_json(out/'summary.json',result)
        P.write_json(out/'evidence_sha256.json',{p.relative_to(out).as_posix():A.digest(p) for p in sorted(out.rglob('*')) if p.is_file()})
        print({k:v for k,v in result.items() if k not in ('rows','model_warnings')},flush=True)
        return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True,type=Path)
    raise SystemExit(0 if run(parser.parse_args().out)['target_found'] else 1)
