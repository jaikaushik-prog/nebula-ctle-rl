"""Derived selected-CTLE receiver with physical Rs/Cs controls.

This is a new circuit identity, never a relabeling of the accepted fixed CTLE.
Existing builders supply every device; no model or acceptance bound is copied.
"""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
import numpy as np
from nebula import generated_receiver as G
from nebula.device import configurable_rc as R, configurable_rc_fine as RF
from nebula.device import dfe_configurable as C, dfe_calibrated_verification as V
from nebula.device import dfe_loaded_initialization as I, loaded_tuning_bound as B
from nebula.device import varactor_probe as VP
from nebula.link.config import LinkConfig

GEOMETRY=(500,0.)
VECTORS=G.F.VECTORS+C.RC_VECTORS

def check_controls(r,c):
    if not np.isfinite([r,c]).all() or ((r,c) not in RF.biases() and (r,c)!=B.BASE):
        raise ValueError('controls must be an existing registered finite fine-grid pair')

def build_deck(design,selected_deck,r_fraction,c_fraction):
    check_controls(r_fraction,c_fraction)
    text=G.build_deck(design,selected_deck).replace('\r\n','\n')
    for name in ('Xrs','Xcs'):
        text=V.L.replace_once(text,rf'^{name}\s+[^\n]*\n','')
    text=re.sub(r'(?m)^(\.param[^\n]*)$',lambda m:re.sub(r'\s+(?:RS|CS)=[^\s]+','',m[1]),text)
    text=V.L.replace_once(text,r'^\.lib\s+.*$',f'.lib "{VP.FULL_LIB.as_posix()}" tt')
    added=R.added_lines(GEOMETRY)+[
        f'VrcR rctrl 0 {1.8*r_fraction:.16g}',f'VrcC cctrl 0 {1.8*c_fraction:.16g}',
        '* Derived programmable variant; parent verification does not transfer.']
    text=text.replace('.control','\n'.join(added)+'\n.control',1)
    text=V.L.replace_once(text,r'^wrdata trace.txt .*$', 'wrdata trace.txt '+' '.join(VECTORS))
    text=V.L.replace_once(text,r'^wrdata terminals.txt .*$', 'wrdata terminals.txt '+' '.join(f'v({n})' for n in V.nodes_for(text)))
    if text.count('.lib ')!=1 or text.count('.control')!=1:raise ValueError('ambiguous model or analysis ownership')
    return text

def export(design,selected_deck,directory,r_fraction,c_fraction):
    text=build_deck(design,selected_deck,r_fraction,c_fraction)
    folder=Path(directory);folder.mkdir(parents=True,exist_ok=False)
    path=folder/'receiver.cir';path.write_bytes(text.encode('ascii'))
    record=dict(schema='nebula-programmable-selected-receiver-v1',status='EXPERIMENTAL_UNVERIFIED',
        structurally_integrated=True,derived_from_setting=352,inherits_parent_verification=False,
        parent_ctle_sha256=hashlib.sha256(selected_deck.encode('ascii')).hexdigest(),
        receiver_deck_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        r_fraction=r_fraction,c_fraction=c_fraction,control_voltage_v=[1.8*r_fraction,1.8*c_fraction],
        tuning_geometry=list(GEOMETRY),nominal_receiver_verified=False,full_receiver_verified=False,
        phase_ui=G.PHASE_UI,tap_code=G.TAP_CODE,control_selection='external values, not learned policy output',
        scope='Derived selected amplifier/bias/attenuator with physical Rs/Cs and transistor DFE; external clock and controls; new verification required')
    (folder/'export.json').write_text(json.dumps(record,indent=2,allow_nan=False),encoding='utf-8')
    return record

def static_body(design,source,state,control):
    if state not in (0,1):raise ValueError('invalid held clock state')
    text=build_deck(design,source,*control).split('.control')[0]
    text=V.L.replace_once(text,r'^Vid vid 0 PWL\(\n(?:\+[^\n]*\n)*\+ \)', 'Vid vid 0 DC 0 AC 1')
    for name,level in [('clk',.6 if state==0 else 1.2),('clkb',1.2 if state==0 else .6)]:
        text=V.L.replace_once(text,rf'^Vdf{name} .*$',f'Vdf{name} df_{name} 0 {level:.16g}')
    reference=json.loads(B.original_file(B.LOADED,B.baseline_folder(state)+'/result.json').read_text())
    seed=I.seed_values(reference,-1)
    text+='.options reltol=1e-7 vntol=1e-10 abstol=1e-13\n'
    text+='.nodeset '+' '.join(f'v({n})={seed[n]:.16g}' for n in I.SEED_NODES)+'\n'
    return text

def static_batch(design,source,state,controls):
    if len(controls)<2 or controls[0]!=controls[-1]:raise ValueError('repeatability brackets required')
    for r,c in controls:check_controls(r,c)
    text=static_body(design,source,state,controls[0]);names=V.nodes_for(text)
    lines=['.control','set noaskquit','set numdgt=15','set wr_singlescale']
    for i,(r,c) in enumerate(controls):
        lines += [f'alter VrcR {1.8*r:.16g}',f'alter VrcC {1.8*c:.16g}','op',
                  f'wrdata op_{i:03d}.txt '+' '.join(f'v({n})' for n in names)+' i(vdd)',
                  'ac dec 50 1meg 100g',f'wrdata ac_{i:03d}.txt v(outp) v(outn) v(vid)']
    return text+'\n'.join(lines+['quit','.endc','.end'])+'\n'

def extract_static(folder,state,controls):
    folder=Path(folder);text=(folder/'design.cir').read_text(encoding='ascii')
    log=(folder/'ngspice.log').read_text(encoding='utf-8',errors='replace')
    V.E.abort_audit(log);warnings=V.L.warning_audit(log)
    for kind in ('op','ac'):
        if {p.name for p in folder.glob(kind+'_*.txt')}!={f'{kind}_{i:03d}.txt' for i in range(len(controls))}:
            raise ValueError('incomplete or extra primitive files')
    rows=[];waves=[]
    for i,control in enumerate(controls):
        ac=np.loadtxt(folder/f'ac_{i:03d}.txt');op=np.loadtxt(folder/f'op_{i:03d}.txt')
        try:row=B.parse_row(text,state,control,op,ac)
        except Exception as exc:
            return dict(clock_state=state,instrument_ok=False,rows=rows,fail_reason=f'snapshot {i}: {exc}',all_raw_snapshots_retained=True)
        rows.append(row);waves.append(R.parse_ac(ac,1)[:,0])
    a,b=rows[0],rows[-1]
    errors=dict(max_node_difference_v=max(abs(v-b['dc_nodes_v'][n]) for n,v in a['dc_nodes_v'].items()),
                max_complex_relative_error=float(np.max(abs(waves[-1]/waves[0]-1))),
                power_difference_w=abs(a['vdd_power_w']-b['vdd_power_w']))
    repeat=errors['max_node_difference_v']<=1e-6 and errors['max_complex_relative_error']<=1e-4 and errors['power_difference_w']<=1e-7
    return dict(clock_state=state,instrument_ok=bool(repeat),rows=rows,repeatability=errors,
                repeated_control_pass=bool(repeat),model_warnings=warnings,full_receiver_verified=False)

def select_control(states,boost,freq):
    result=dict(target_boost_db=boost,target_frequency_hz=freq,nominal_ac_match=False,
                nominal_receiver_verified=False,full_receiver_verified=False,signed_model_domain_pass=False)
    if len(states)!=2 or not all(s.get('instrument_ok') for s in states):return result
    keys=[[(r['r_fraction'],r['c_fraction']) for r in s['rows']] for s in states]
    if [s['clock_state'] for s in states]!=[0,1] or keys[0]!=keys[1]:raise ValueError('held-state control alignment mismatch')
    candidates=[]
    for i,pair in enumerate(zip(states[0]['rows'],states[1]['rows'])):
        if any(not r.get('instrument_ok') or not r['ac_model_pass'] or abs(r['boost_db']-boost)>.5 or abs(r['peak_frequency_hz']-freq)>1e8 for r in pair):continue
        error=max(((r['boost_db']-boost)/.5)**2+((r['peak_frequency_hz']-freq)/1e8)**2 for r in pair)
        candidates.append((error,*keys[0][i],i))
    if candidates:
        error,r,c,i=min(candidates)
        result.update(nominal_ac_match=True,r_fraction=r,c_fraction=c,row_index=i,worst_state_normalized_error=error,
                      signed_model_domain_pass=all(s['rows'][i]['signed_model_domain_pass'] for s in states),
                      control_selection='deterministic minimum error among measured controls, not RL')
    return result

def extract_link(folder,control):
    folder=Path(folder);text=(folder/'design.cir').read_text(encoding='ascii')
    log=(folder/'ngspice.log').read_text(encoding='utf-8',errors='replace')
    V.E.abort_audit(log);warnings=V.L.warning_audit(log)
    t,y=G.T.read_table(folder/'trace.txt',len(VECTORS))
    names=V.nodes_for(text);_,ny=G.T.read_table(folder/'terminals.txt',len(names),expected_time=t)
    nodes=dict(zip(names,ny.T))
    for i,v in enumerate(VECTORS):
        if v.startswith('v(') and v[2:-1] in nodes and not np.array_equal(y[:,i],nodes[v[2:-1]]):raise ValueError('duplicated primitive mismatch')
    cfg=LinkConfig(channel_loss_db_at_nyquist=7.5);bits=G.F.pattern(cfg)
    result=G.F.analyze(t,y[:,:len(G.F.VECTORS)],bits,cfg,G.PHASE_UI,1.8,code=G.TAP_CODE)
    whole=G.V.audit(G.F.all_mos(text),nodes)
    new=G.V.audit(G.F.extra_mos(G.TAP_SIGN)+G.B.bleeders(G.BLEED_LENGTH_UM),nodes)
    controls=V.control_audit(t,y[:,-6:],nodes,1.8,*control)
    result.update(instrument_ok=True,new_dfe_voltage_audit=new,whole_circuit_voltage_audit=whole,
        whole_circuit_voltage_envelope_pass=G.E.envelope(whole),tuning_controls=controls,
        aperture=G.T.aperture(t,y[:,3]-y[:,4],bits,G.PHASE_UI),model_warnings=warnings)
    result['signal_gate_pass']=bool(G.H.accepted(result) and controls['control_valid'] and controls['varactor_voltage_envelope_pass'])
    result['signed_model_domain_pass']=bool(whole['documented_ranges_ok'])
    result['nominal_receiver_verified']=bool(result['signal_gate_pass'] and result['signed_model_domain_pass'])
    result.update(full_receiver_verified=False,phase_ui=G.PHASE_UI,tap_code=G.TAP_CODE,
                  r_fraction=control[0],c_fraction=control[1],scope='New derived receiver, nominal finite noiseless pattern, external clocks/controls, constructed 7.5dB channel; no PVT/BER signoff')
    json.dumps(result,allow_nan=False)
    return result
