"""Independent Entry160 link/state1 instruments; previous failures immutable."""
from datetime import datetime,timezone
from pathlib import Path
import json,shutil,time
import numpy as np
from nebula import programmable_receiver as P
from nebula.device import loaded_tuning_bound as B
from nebula.experiments import spice_capture as C
from nebula.experiments.runlock import hold,stamp
from nebula.experiments.exp_varactor_probe import pdk_hashes
from nebula.device.ngspice_runner import ngspice_path

ROOT=B.ROOT
RUN=ROOT/'nebula/product_demo/submission_runs_20260915_v2/4608cf1c525f4e59b2d5226059b0ce5d'
OUT=ROOT/'nebula/product_audits/entry160_programmable_receiver_followup_20260915'
CONTROL=(.73,.195)
DEADLINE=datetime(2026,9,15,14,4,35,tzinfo=timezone.utc)

def static_deck(design,source,state,seed=None):
    text=P.static_body(design,source,state,CONTROL)
    if seed is not None:
        if seed['df_q']-seed['df_qb']>=-.1:raise ValueError('unresolved measured seed')
        text=P.V.L.replace_once(text,r'^\.nodeset .*$', '.nodeset '+' '.join(f'v({n})={seed[n]:.16g}' for n in P.I.SEED_NODES))
    names=P.V.nodes_for(text)
    return text+'\n'.join(['.control','set noaskquit','set numdgt=15','set wr_singlescale','unset sqrnoise',
        'op','wrdata op.txt '+' '.join(f'v({n})' for n in names)+' i(vdd)',
        'ac dec 50 1meg 100g','wrdata ac.txt v(outp) v(outn) v(vid)',
        'noise v(outn,outp) Vid lin 500 10meg 5g','wrdata noise_total.txt inoise_total onoise_total',
        'setplot noise1','wrdata noise_spectrum.txt inoise_spectrum onoise_spectrum','quit','.endc','.end'])+'\n'

def extract_static(folder,state):
    text=(folder/'design.cir').read_text();log=(folder/'ngspice.log').read_text(errors='replace')
    P.V.E.abort_audit(log);warnings=P.V.L.warning_audit(log)
    op=np.loadtxt(folder/'op.txt');ac=np.loadtxt(folder/'ac.txt')
    core=B.parse_row(text,state,CONTROL,op,ac)
    noise=P.V.noise_metrics(np.loadtxt(folder/'noise_total.txt'),np.loadtxt(folder/'noise_spectrum.txt'))
    return {**core,'noise':noise,'model_warnings':warnings,'clock_state':state}

def write(path,value):path.write_text(json.dumps(value,indent=2,allow_nan=False),encoding='utf-8')

def run():
    if OUT.exists():raise ValueError('followup exists; no overwrite')
    if (Path(__file__).parent/'.dfe_slicer.runlock.json').exists():raise ValueError('existing simulator lock')
    if (DEADLINE-datetime.now(timezone.utc)).total_seconds()<240:raise ValueError('measurement deadline')
    with hold('dfe_slicer'):
        OUT.mkdir(parents=True);start=time.perf_counter();calls=[]
        design=json.loads((RUN/'design.json').read_text());source=(RUN/'design.cir').read_bytes().decode('ascii')
        config=json.loads((ROOT/'nebula/product_audits/entry160_programmable_receiver_20260915_r3/config.json').read_text())
        sources=dict(config['source_sha256'])
        for n in ('nebula/PROGRAMMABLE_RECEIVER_FOLLOWUP_20260915.md','nebula/experiments/exp_programmable_receiver_followup.py'):sources[n]=B.sha(ROOT/n)
        for name,digest in sources.items():
            B.checked_file(ROOT,name,digest);dst=OUT/'sources'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dst)
        if pdk_hashes()!=config['external_pdk_include_closure_sha256']:raise ValueError('PDK changed')
        write(OUT/'config.json',dict(source_sha256=sources,control=CONTROL,prior_experiment=str(ROOT/'nebula/product_audits/entry160_programmable_receiver_20260915_r3'),
              external_pdk_include_closure_sha256=config['external_pdk_include_closure_sha256'],ngspice_sha256=B.sha(ngspice_path()),**stamp()))
        def invoke(name,text,extract):
            if (DEADLINE-datetime.now(timezone.utc)).total_seconds()<210:raise ValueError('measurement deadline')
            for n,h in sources.items():B.checked_file(ROOT,n,h)
            folder=OUT/name;row=dict(case=name,instrument_ok=False);begin=time.perf_counter()
            call=dict(index=len(calls)+1,case=name);calls.append(call);write(OUT/'progress.json',calls)
            print(f'Followup call {len(calls)}: {name}',flush=True)
            try:
                C.invoke(text,folder,timeout_s=180);row.update(extract(folder))
            except Exception as exc:
                folder.mkdir(parents=True,exist_ok=True);row.update(fail_reason=f'{type(exc).__name__}: {exc}')
            call.update(wall_seconds=time.perf_counter()-begin,instrument_ok=row['instrument_ok'],fail_reason=row.get('fail_reason'))
            write(folder/'result.json',row);write(OUT/'progress.json',calls)
            print(json.dumps({k:row[k] for k in ('case','instrument_ok','fail_reason','signal_gate_pass','sampled_eye_height_v','signed_model_domain_pass') if k in row}),flush=True)
            return row
        result=dict(entry=160,full_receiver_verified=False,nominal_receiver_verified=False,prior_charged_calls=2)
        try:
            result['link']=invoke('clocked_link',P.build_deck(design,source,*CONTROL),lambda f:P.extract_link(f,CONTROL))
            result['state1']=invoke('held_state1',static_deck(design,source,1),lambda f:extract_static(f,1))
            if result['state1']['instrument_ok']:
                result['state0']=invoke('held_state0_measured_seed',static_deck(design,source,0,result['state1']['dc_nodes_v']),lambda f:extract_static(f,0))
            result['sources_unchanged']=all(B.sha(ROOT/n)==h for n,h in sources.items())
            result['parent_unchanged']=B.sha(RUN/'design.cir')==design['physical_evidence']['deck_sha256']
        except Exception as exc:result['fail_reason']=f'{type(exc).__name__}: {exc}'
        result.update(calls=calls,charged_calls=len(calls),total_entry160_charged_calls=2+len(calls),wall_seconds=time.perf_counter()-start,
                      completed_utc=datetime.now(timezone.utc).isoformat())
        write(OUT/'summary.json',result)
        write(OUT/'evidence_sha256.json',{p.relative_to(OUT).as_posix():B.sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='evidence_sha256.json'})
        print(json.dumps({k:v for k,v in result.items() if k not in ('link','state1','state0')},indent=2),flush=True)
        return result

if __name__=='__main__':run()
