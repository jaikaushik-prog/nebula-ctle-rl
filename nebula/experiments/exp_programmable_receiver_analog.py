"""Small nominal analog completion, not full receiver verification."""
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

PRIOR=ROOT/'nebula/product_audits/entry160_programmable_receiver_measured_seed_20260915'
OUT=ROOT/'nebula/product_audits/entry160_programmable_receiver_analog_20260915'
TARGET=(6.,2.1e9,.73,.21)

def deck(design,source,kind,state,step,seed):
    if kind=='static':text=P.static_body(design,source,state,TARGET[2:])
    else:
        text=P.build_deck(design,source,*TARGET[2:]).split('.control')[0]
        text=P.V.L.replace_once(text,r'^Vid vid 0 PWL\(\n(?:\+[^\n]*\n)*\+ \)', 'Vid vid 0 DC 0 AC 1 SIN(0 0.1 100meg)')
        text+=P.V.E.option(1e-5)+'\n.options method=gear maxord=2\n'
    line='.nodeset '+' '.join(f'v({n})={v:.16g}' for n,v in seed.items() if n not in {'0','vid','vdd','cm','df_clk','df_clkb','rctrl','cctrl',*(f'tap{i}' for i in range(4))})
    if '.nodeset ' in text:text=P.V.L.replace_once(text,r'^\.nodeset .*$',line)
    else:text+=line+'\n'
    names=P.V.nodes_for(text);lines=['.control','set noaskquit','set numdgt=15','set wr_singlescale','unset sqrnoise']
    if kind=='static':
        lines+=['op','wrdata op.txt '+' '.join(f'v({n})' for n in names)+' i(vdd)',
          'ac dec 50 1meg 100g','wrdata ac.txt v(outp) v(outn) v(vid)',
          'noise v(outn,outp) Vid lin 500 10meg 5g','wrdata noise_total.txt inoise_total onoise_total',
          'setplot noise1','wrdata noise_spectrum.txt inoise_spectrum onoise_spectrum']
    else:lines += [f'tran {step:.16g} 150n 0 {step:.16g}','wrdata trace.txt '+' '.join(P.VECTORS),'wrdata terminals.txt '+' '.join(f'v({n})' for n in names)]
    return text+'\n'.join(lines+['quit','.endc','.end'])+'\n'

def extract(folder,kind,state,step,reference):
    text=(folder/'design.cir').read_text();log=(folder/'ngspice.log').read_text(errors='replace')
    P.V.E.abort_audit(log);warnings=P.V.L.warning_audit(log)
    if kind=='static':
        data=[np.loadtxt(folder/n) for n in ('op.txt','ac.txt','noise_total.txt','noise_spectrum.txt')]
        row=P.V.static_metrics(text,TARGET,state,*data)
        if row['dc_nodes_v']['df_q']-row['dc_nodes_v']['df_qb']>=-.1:raise ValueError('invalid negative latch')
        nodes_error=max(abs(v-reference['dc_nodes_v'][n]) for n,v in row['dc_nodes_v'].items())
        if nodes_error>1e-6:raise ValueError('same-DUT DC consistency failure')
        if abs(row['response']['boost_db']-reference['boost_db'])>1e-5 or abs(row['response']['peak_frequency_hz']-reference['peak_frequency_hz'])>1000:raise ValueError('same-DUT AC consistency failure')
        row['same_dut_max_node_error_v']=nodes_error
    else:
        t,y=P.G.T.read_table(folder/'trace.txt',len(P.VECTORS));names=P.V.nodes_for(text)
        _,ny=P.G.T.read_table(folder/'terminals.txt',len(names),expected_time=t)
        row=P.V.tone_metrics(text,TARGET,step,t,y,dict(zip(names,ny.T)))
        if y[0,5]-y[0,6]>=-.1:raise ValueError('invalid initial stored state')
        row['initial_stored_differential_v']=float(y[0,5]-y[0,6])
    row.update(model_warnings=warnings,initialization_valid=True,full_receiver_verified=False,
               nominal_receiver_verified=False,signed_model_domain_pass=row['whole_circuit_voltage_audit']['documented_ranges_ok'])
    return row

def write(path,value):path.write_text(json.dumps(value,indent=2,allow_nan=False),encoding='utf-8')
def run():
    if OUT.exists():raise ValueError('analog output exists')
    if (Path(__file__).parent/'.dfe_slicer.runlock.json').exists():raise ValueError('existing simulator lock')
    with hold('dfe_slicer'):
        OUT.mkdir(parents=True);start=time.perf_counter();calls=[]
        config=json.loads((PRIOR/'config.json').read_text());sources=dict(config['source_sha256'])
        for n in ('nebula/PROGRAMMABLE_RECEIVER_ANALOG_PLAN_20260915.md','nebula/experiments/exp_programmable_receiver_analog.py'):sources[n]=B.sha(ROOT/n)
        for n,h in sources.items():
            B.checked_file(ROOT,n,h);dst=OUT/'sources'/n;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,dst)
        old=json.loads((ROOT/'nebula/product_audits/entry160_programmable_receiver_followup_20260915/config.json').read_text())
        if pdk_hashes()!=old['external_pdk_include_closure_sha256']:raise ValueError('PDK changed')
        manifest=json.loads((PRIOR/'evidence_sha256.json').read_text())
        summary=json.loads(B.checked_file(PRIOR,'summary.json',manifest['summary.json']).read_text())
        choice=summary['selected_control'];assert choice['nominal_ac_match'] and (choice['r_fraction'],choice['c_fraction'])==TARGET[2:]
        refs={s['clock_state']:s['rows'][choice['row_index']] for s in summary['states']}
        write(OUT/'config.json',dict(source_sha256=sources,target=TARGET,prior_summary_sha256=manifest['summary.json'],prior=str(PRIOR),
             external_pdk_include_closure_sha256=old['external_pdk_include_closure_sha256'],ngspice_sha256=old['ngspice_sha256'],**stamp()))
        design=json.loads((RUN/'design.json').read_text());source=(RUN/'design.cir').read_bytes().decode('ascii')
        result=dict(entry=160,full_receiver_verified=False,nominal_receiver_verified=False,static=[],tones=[])
        try:
            for kind,state,step in [('static',0,5e-12),('static',1,5e-12),('tone',0,5e-12),('tone',0,2.5e-12)]:
                if (DEADLINE-datetime.now(timezone.utc)).total_seconds()<210:raise ValueError('measurement cutoff')
                for n,h in sources.items():B.checked_file(ROOT,n,h)
                seed=refs[state if kind=='static' else 1]['dc_nodes_v'];text=deck(design,source,kind,state,step,seed)
                name=f'{kind}_state{state}_step{step*1e12:g}ps';folder=OUT/name;begin=time.perf_counter();call=dict(index=len(calls)+1,case=name)
                calls.append(call);write(OUT/'progress.json',calls);print(f'Analog call {len(calls)}/4: {name}',flush=True)
                try:C.invoke(text,folder,timeout_s=180);row=extract(folder,kind,state,step,refs[state])
                except Exception as exc:
                    folder.mkdir(parents=True,exist_ok=True);row=dict(instrument_ok=False,full_receiver_verified=False,fail_reason=f'{type(exc).__name__}: {exc}')
                row.update(kind=kind,clock_state=state,max_step_s=step);call.update(wall_seconds=time.perf_counter()-begin,instrument_ok=row['instrument_ok'],fail_reason=row.get('fail_reason'))
                write(folder/'result.json',row);write(OUT/'progress.json',calls);result['static' if kind=='static' else 'tones'].append(row)
                print(json.dumps(call),flush=True)
                if not row['instrument_ok']:break
            result['resolution_agreement']=len(result['tones'])==2 and P.V.L.resolution_matches(*result['tones'])
            result['sources_unchanged']=all(B.sha(ROOT/n)==h for n,h in sources.items())
            result['parent_unchanged']=B.sha(RUN/'design.cir')==design['physical_evidence']['deck_sha256']
        except Exception as exc:result['fail_reason']=f'{type(exc).__name__}: {exc}'
        result.update(calls=calls,charged_calls=len(calls),total_entry160_charged_calls=7+len(calls),wall_seconds=time.perf_counter()-start,completed_utc=datetime.now(timezone.utc).isoformat())
        write(OUT/'summary.json',result)
        write(OUT/'evidence_sha256.json',{p.relative_to(OUT).as_posix():B.sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='evidence_sha256.json'})
        print(json.dumps({k:v for k,v in result.items() if k not in ('static','tones')},indent=2),flush=True)
        return result

if __name__=='__main__':run()
