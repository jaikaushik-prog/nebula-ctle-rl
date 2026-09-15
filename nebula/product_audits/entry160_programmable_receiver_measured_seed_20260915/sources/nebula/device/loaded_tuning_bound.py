"""Entry158: existing control proposals and nominal loaded OP/AC extraction."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
from nebula.submission_evidence import ROOT,checked_file,sha
from nebula.device import configurable_rc_fine as F, configurable_rc as R
from nebula.device import dfe_calibrated_verification as V

STANDALONE=ROOT/'nebula/product_audits/entry131_configurable_rc_fine_20260910'
LOADED=ROOT/'nebula/product_audits/entry143_dfe_calibrated_verification_20260910'
PINNED={STANDALONE:{'summary.json':'06f6344b3802bf863f3ceb80be847cd0ab6c95debe3c0c3760a8ce590ef87b12','evidence_sha256.json':'03585ee1a882bb36523557bfa029b61cb9f29edcc21cd0eaf402d33372e3ab01'},LOADED:{'summary.json':'14d7d368163652235378e1566e4800a7d26ec2a550922300a015978b74602d96','evidence_sha256.json':'59a7deec832a1d744ad7175bd1eeed7fb0d21b376e1d03c15acb24e1888c99c7'}}
TARGETS=tuple((b,f*1e9) for b in (3.,6.,9.,12.) for f in (1.25,1.9,2.5))
BASE=(.7,.185)

def original_file(root,name):
    for filename,digest in PINNED[root].items():checked_file(root,filename,digest)
    manifest=json.loads((root/'evidence_sha256.json').read_text())
    return checked_file(root,name,manifest[name])

def proposals():
    original_file(STANDALONE,'summary.json')
    summary=json.loads((STANDALONE/'summary.json').read_text())
    item=next(x for x in summary['candidates'] if x['geometry']==[500,0.])
    rows=item['result']['rows']; matches=[F.select_target(rows,*target) for target in TARGETS]
    controls=[]
    for target in matches:
        if not target['found']:continue
        r,c=target['r_fraction'],target['c_fraction'];ci=F.C_FRACTIONS.index(c)
        for candidate_c in F.C_FRACTIONS[ci:ci+3]:
            pair=(r,candidate_c)
            if pair not in controls:controls.append(pair)
    for r,c in controls:
        index=F.biases().index((r,c));prefix='candidate_n500_fixed0pf/'
        op=np.loadtxt(original_file(STANDALONE,prefix+f'op_{index:03d}.txt'))
        ac=np.loadtxt(original_file(STANDALONE,prefix+f'ac_{index:03d}.txt'))
        dc=F.parse_op(op,(500,0.),r,c)[0];metrics=R.response_metrics(R.parse_ac(ac,2)[:,0])
        saved=rows[index]
        if abs(metrics['boost_db']-saved['boost_db'])>1e-8 or abs(metrics['peak_frequency_hz']-saved['peak_frequency_hz'])>1:
            raise ValueError('Standalone control metrics do not reproduce')
        if dc['electrical_pass']!=saved['electrical_pass']:raise ValueError('Standalone electrical gate changed')
    return dict(targets=matches,controls=[BASE]+[p for p in controls if p!=BASE]+[BASE],
        scope='Exposed nominal standalone proposals; not selected-circuit/full-flow coverage.')

def baseline_folder(state):
    if state not in (0,1):raise ValueError('Unregistered held clock state')
    return f'static_state{state}_tol1e-05_step5ps'

def body(state):
    return original_file(LOADED,baseline_folder(state)+'/design.cir').read_text(encoding='ascii').split('.control')[0]

def deck(state,controls):
    if not controls or tuple(controls[0])!=BASE or tuple(controls[-1])!=BASE:
        raise ValueError('Both calibrated baseline snapshots are required')
    for pair in controls:
        if tuple(pair)!=BASE and tuple(pair) not in F.biases():raise ValueError('Unmeasured external control')
    text=body(state);names=V.nodes_for(text)
    lines=['.control','set noaskquit','set numdgt=15','set wr_singlescale']
    for i,(r,c) in enumerate(controls):
        lines += [f'alter VrcR {1.8*r:.16g}',f'alter VrcC {1.8*c:.16g}','op',
            f'wrdata op_{i:03d}.txt '+' '.join('v('+n+')' for n in names)+' i(vdd)',
            'ac dec 50 1meg 100g',f'wrdata ac_{i:03d}.txt v(outp) v(outn) v(vid)']
    return text+'\n'.join(lines+['quit','.endc','.end'])+'\n'

def parse_row(text,state,control,op,ac):
    names=V.nodes_for(text);a=np.atleast_2d(np.asarray(op,dtype=float))
    if a.shape!=(1,len(names)+2) or not np.isfinite(a).all():raise ValueError('Malformed OP primitives')
    nodes={n:a[:,i+1] for i,n in enumerate(names)}
    expected=(.6,1.2) if state==0 else (1.2,.6)
    if any(abs(nodes[n][0]-value)>1e-8 for n,value in zip(('df_clk','df_clkb'),expected)):
        raise ValueError('Wrong held-clock stimulus')
    if abs(nodes['vid'][0])>1e-12:raise ValueError('Wrong differential DC stimulus')
    if nodes['df_q'][0]-nodes['df_qb'][0]>=-.1:raise ValueError('Invalid negative-latch initialization')
    power=float(-1.8*a[0,-1])
    if power<=0:raise ValueError('Nonpositive supplied power')
    audit=V.voltage_audit(text,nodes,(9.,1.9e9,*control))
    if not audit['external_controls_valid']:raise ValueError('Wrong physical controls or supply')
    metrics=R.response_metrics(R.parse_ac(ac,1)[:,0])
    return dict(instrument_ok=True,r_fraction=control[0],c_fraction=control[1],**metrics,
        dc_nodes_v={n:float(v[0]) for n,v in nodes.items()},vdd_power_w=power,**audit,
        ac_model_pass=bool(metrics['ac_shape_pass'] and power<.015 and audit['voltage_gate_pass']),
        signed_model_domain_pass=audit['whole_circuit_voltage_audit']['documented_ranges_ok'],
        full_receiver_verified=False)

def baseline_matches(row,ac,state):
    folder=baseline_folder(state)
    reference=json.loads(original_file(LOADED,folder+'/result.json').read_text())
    saved_ac=np.loadtxt(original_file(LOADED,folder+'/ac.txt'))
    return V.K.calibration_matches(row,reference,ac,saved_ac)

def extract(folder,state,controls):
    folder=Path(folder);text=(folder/'design.cir').read_text(encoding='ascii')
    log=(folder/'ngspice.log').read_text(encoding='utf-8',errors='replace')
    V.E.abort_audit(log);warnings=V.L.warning_audit(log)
    for kind in ('op','ac'):
        if {p.name for p in folder.glob(kind+'_*.txt')}!={f'{kind}_{i:03d}.txt' for i in range(len(controls))}:
            raise ValueError('Incomplete or extra OP/AC files')
    rows=[]
    for i,control in enumerate(controls):
        ac=np.loadtxt(folder/f'ac_{i:03d}.txt');op=np.loadtxt(folder/f'op_{i:03d}.txt')
        try:
            row=parse_row(text,state,control,op,ac)
            if i in (0,len(controls)-1) and not baseline_matches(row,ac,state):raise ValueError('Calibrated baseline drift')
        except Exception as exc:
            rows.append(dict(instrument_ok=False,row_index=i,r_fraction=control[0],c_fraction=control[1],fail_reason=str(exc)))
            return dict(instrument_ok=False,clock_state=state,rows=rows,
                fail_reason=f'Invalid snapshot {i}: {exc}',unparsed_snapshots=len(controls)-i-1,
                all_raw_snapshots_retained=True,model_warnings=warnings)
        rows.append(row)
    return dict(instrument_ok=True,baseline_matches=True,clock_state=state,rows=rows,model_warnings=warnings)

def select_targets(states):
    if len(states)==2 and all(s.get('instrument_ok') for s in states):
        keys=[[(r['r_fraction'],r['c_fraction']) for r in s['rows']] for s in states]
        if [s['clock_state'] for s in states]!=[0,1] or keys[0]!=keys[1]:
            raise ValueError('Held-state control alignment mismatch')
    results=[]
    for boost,freq in TARGETS:
        candidates=[]
        if len(states)==2 and all(s.get('instrument_ok') for s in states):
            for index,first in enumerate(states[0]['rows']):
                pair=[s['rows'][index] for s in states]
                if any(not r['ac_model_pass'] or abs(r['boost_db']-boost)>.5 or abs(r['peak_frequency_hz']-freq)>1e8 for r in pair):continue
                error=max(((r['boost_db']-boost)/.5)**2+((r['peak_frequency_hz']-freq)/1e8)**2 for r in pair)
                candidates.append((error,first['r_fraction'],first['c_fraction'],index))
        row=dict(target_boost_db=boost,target_frequency_hz=freq,nominal_ac_match=bool(candidates),full_receiver_verified=False)
        if candidates:
            error,r,c,index=min(candidates);row.update(r_fraction=r,c_fraction=c,row_index=index,worst_state_normalized_error=error)
        results.append(row)
    return results
