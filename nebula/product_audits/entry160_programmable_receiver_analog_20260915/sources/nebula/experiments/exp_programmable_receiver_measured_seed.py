"""Final bounded DC initialization check from this DUT's own measured state."""
from datetime import datetime,timezone
from pathlib import Path
import json,shutil,time
import numpy as np
from nebula import programmable_receiver as P
from nebula.device import loaded_tuning_bound as B
from nebula.experiments import spice_capture as C
from nebula.experiments.runlock import hold,stamp
from nebula.experiments.exp_varactor_probe import pdk_hashes
from nebula.experiments.exp_programmable_receiver_followup import ROOT,RUN,DEADLINE

PRIOR=ROOT/'nebula/product_audits/entry160_programmable_receiver_followup_20260915'
OUT=ROOT/'nebula/product_audits/entry160_programmable_receiver_measured_seed_20260915'
CONTROLS=[(.73,.195),(.73,.210),(.73,.225),(.73,.195)]
def write(path,value):path.write_text(json.dumps(value,indent=2,allow_nan=False),encoding='utf-8')

def seed_from_waveform(state):
    manifest=json.loads((PRIOR/'evidence_sha256.json').read_text())
    files={name:B.checked_file(PRIOR,name,manifest[name]) for name in ('clocked_link/design.cir','clocked_link/trace.txt','clocked_link/terminals.txt','clocked_link/result.json')}
    if not json.loads(files['clocked_link/result.json'].read_text())['signal_gate_pass']:raise ValueError('no valid measured signal source')
    text=files['clocked_link/design.cir'].read_text();names=P.V.nodes_for(text)
    t,y=P.G.T.read_table(files['clocked_link/terminals.txt'],len(names));nodes=dict(zip(names,y.T))
    expected=(.6,1.2) if state==0 else (1.2,.6)
    mask=t>=(P.G.F.WARMUP+2)*P.G.UI
    for n,v in zip(('df_clk','df_clkb'),expected):mask &= abs(nodes[n]-v)<1e-8
    mask &= (nodes['df_q']-nodes['df_qb']<-.1)&(nodes['df_mp']-nodes['df_mn']<-.1)
    indices=np.flatnonzero(mask)
    if not len(indices):raise ValueError('no measured resolved seed for held state')
    index=min(indices,key=lambda i:(abs(nodes['vid'][i]),t[i]))
    excluded={'0','vid','vdd','cm','df_clk','df_clkb','rctrl','cctrl',*(f'tap{i}' for i in range(4))}
    values={n:float(nodes[n][index]) for n in names if n not in excluded}
    return dict(clock_state=state,sample_index=int(index),time_s=float(t[index]),input_v=float(nodes['vid'][index]),nodes=values,
                source_terminal_sha256=manifest['clocked_link/terminals.txt'],nodeset_is_released_guess=True)

def deck(design,source,state,seed):
    text=P.static_batch(design,source,state,CONTROLS)
    return P.V.L.replace_once(text,r'^\.nodeset .*$', '.nodeset '+' '.join(f'v({n})={v:.16g}' for n,v in seed['nodes'].items()))

def run():
    if OUT.exists():raise ValueError('measurement directory exists')
    if (Path(__file__).parent/'.dfe_slicer.runlock.json').exists():raise ValueError('existing simulator lock')
    with hold('dfe_slicer'):
        OUT.mkdir(parents=True);start=time.perf_counter();calls=[];states=[]
        config=json.loads((PRIOR/'config.json').read_text());sources=dict(config['source_sha256'])
        for n in ('nebula/PROGRAMMABLE_RECEIVER_MEASURED_SEED_20260915.md','nebula/experiments/exp_programmable_receiver_measured_seed.py'):sources[n]=B.sha(ROOT/n)
        for n,h in sources.items():
            B.checked_file(ROOT,n,h);dst=OUT/'sources'/n;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,dst)
        if pdk_hashes()!=config['external_pdk_include_closure_sha256']:raise ValueError('PDK changed')
        seeds={s:seed_from_waveform(s) for s in (0,1)}
        write(OUT/'config.json',dict(source_sha256=sources,seeds=seeds,controls=CONTROLS,prior=str(PRIOR),**stamp()))
        design=json.loads((RUN/'design.json').read_text());source=(RUN/'design.cir').read_bytes().decode('ascii')
        def invoke(name,text,extract):
            if (DEADLINE-datetime.now(timezone.utc)).total_seconds()<210:raise ValueError('measurement cutoff')
            for n,h in sources.items():B.checked_file(ROOT,n,h)
            folder=OUT/name;begin=time.perf_counter();call=dict(case=name,index=len(calls)+1);calls.append(call);write(OUT/'progress.json',calls)
            print('Measured-state call '+str(len(calls))+': '+name,flush=True)
            try:C.invoke(text,folder,timeout_s=180);row=extract(folder)
            except Exception as exc:
                folder.mkdir(parents=True,exist_ok=True);row=dict(instrument_ok=False,fail_reason=f'{type(exc).__name__}: {exc}')
            call.update(wall_seconds=time.perf_counter()-begin,instrument_ok=row.get('instrument_ok'),fail_reason=row.get('fail_reason'))
            write(folder/'result.json',row);write(OUT/'progress.json',calls)
            print(json.dumps(call),flush=True);return row
        result=dict(entry=160,full_receiver_verified=False,nominal_receiver_verified=False)
        try:
            for state in (1,0):
                row=invoke(f'held_state{state}',deck(design,source,state,seeds[state]),lambda f,s=state:P.extract_static(f,s,CONTROLS))
                states.append(row)
                if not row.get('instrument_ok'):break
            states.sort(key=lambda s:s.get('clock_state',-1));choice=P.select_control(states,6.,2.1e9)
            result.update(states=states,selected_control=choice)
            if choice['nominal_ac_match']:
                control=(choice['r_fraction'],choice['c_fraction'])
                result['export']=P.export(design,source,OUT/'export',*control)
                result['link']=invoke('selected_control_link',P.build_deck(design,source,*control),lambda f:P.extract_link(f,control))
            result['parent_unchanged']=B.sha(RUN/'design.cir')==design['physical_evidence']['deck_sha256']
            result['sources_unchanged']=all(B.sha(ROOT/n)==h for n,h in sources.items())
        except Exception as exc:result['fail_reason']=f'{type(exc).__name__}: {exc}'
        result.update(calls=calls,charged_calls=len(calls),total_entry160_charged_calls=4+len(calls),wall_seconds=time.perf_counter()-start,completed_utc=datetime.now(timezone.utc).isoformat())
        write(OUT/'summary.json',result)
        write(OUT/'evidence_sha256.json',{p.relative_to(OUT).as_posix():B.sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='evidence_sha256.json'})
        print(json.dumps({k:v for k,v in result.items() if k not in ('states','link')},indent=2),flush=True)
        return result

if __name__=='__main__':run()
