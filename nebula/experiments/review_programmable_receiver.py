"""Read-only recomputation and provenance review of Entry160 measurements."""
from pathlib import Path
import json
import numpy as np
from nebula import programmable_receiver as P
from nebula.device import loaded_tuning_bound as B

ROOT=B.ROOT
BASE=ROOT/'nebula/product_audits'
MAIN=BASE/'entry160_programmable_receiver_measured_seed_20260915'
OUT=BASE/'entry160_programmable_receiver_review_20260915'
NAMES=('entry160_programmable_receiver_20260915','entry160_programmable_receiver_20260915_r2',
       'entry160_programmable_receiver_20260915_r3','entry160_programmable_receiver_followup_20260915',
       'entry160_programmable_receiver_measured_seed_20260915','entry160_programmable_receiver_analog_20260915')

def review():
    history=[];verified=0;bindings={}
    for name in NAMES:
        root=BASE/name;manifest=json.loads((root/'evidence_sha256.json').read_text())
        for rel,digest in manifest.items():B.checked_file(root,rel,digest);verified+=1
        summary=json.loads((root/'summary.json').read_text())
        history.append(dict(experiment=name,charged_calls=summary['charged_calls'],wall_seconds=summary['wall_seconds'],
                            calls=summary.get('calls',[]),failure=summary.get('fail_reason'),status=summary.get('status')))
        bindings[name]=dict(manifest_sha256=B.sha(root/'evidence_sha256.json'),summary_sha256=B.sha(root/'summary.json'))
    saved=json.loads((MAIN/'summary.json').read_text());config=json.loads((MAIN/'config.json').read_text())
    controls=[tuple(x) for x in config['controls']]
    states=[P.extract_static(MAIN/f'held_state{s}',s,controls) for s in (0,1)]
    if states!=saved['states']:raise ValueError('recomputed held-state evidence differs')
    choice=P.select_control(states,6.,2.1e9)
    if choice!=saved['selected_control'] or not choice['nominal_ac_match']:raise ValueError('control selection does not reproduce')
    control=(choice['r_fraction'],choice['c_fraction']);link=P.extract_link(MAIN/'selected_control_link',control)
    if link!=saved['link'] or not link['signal_gate_pass']:raise ValueError('nominal link evidence does not reproduce')
    parent=ROOT/'nebula/product_demo/submission_runs_20260915_v2/4608cf1c525f4e59b2d5226059b0ce5d'
    initial=json.loads((BASE/NAMES[1]/'config.json').read_text())
    for name,digest in initial['parent_files_sha256'].items():B.checked_file(parent,name,digest)
    design=json.loads((parent/'design.json').read_text());source=(parent/'design.cir').read_bytes().decode('ascii')
    built=P.build_deck(design,source,*control)
    measured=(MAIN/'selected_control_link/design.cir').read_bytes().decode('ascii')
    if built.replace('\r\n','\n')!=measured.replace('\r\n','\n'):raise ValueError('current generator does not reproduce measured circuit')
    violations=[]
    for d in link['whole_circuit_voltage_audit']['devices']:
        q={k:d[k] for k in ('vds','vgs','vbs') if d[k]['below_samples']+d[k]['above_samples']}
        if q:violations.append(dict(instance=d['instance'],model=d['model'],quantities=q))
    points=[]
    for i,(r,c) in enumerate(controls[:-1]):
        points.append(dict(r_fraction=r,c_fraction=c,states=[dict(clock_state=s['clock_state'],boost_db=s['rows'][i]['boost_db'],
            peak_frequency_hz=s['rows'][i]['peak_frequency_hz']) for s in states]))
    response=[dict(clock_state=s['clock_state'],boost_db=s['rows'][choice['row_index']]['boost_db'],
        peak_frequency_hz=s['rows'][choice['row_index']]['peak_frequency_hz'],vdd_power_w=s['rows'][choice['row_index']]['vdd_power_w']) for s in states]
    artifacts={name:dict(path=(MAIN/rel).relative_to(ROOT).as_posix(),sha256=B.sha(MAIN/rel)) for name,rel in
        [('deck','selected_control_link/design.cir'),('waveform','selected_control_link/trace.txt'),('terminals','selected_control_link/terminals.txt'),
         ('link-result','selected_control_link/result.json'),('summary','summary.json'),('config','config.json'),
         ('ac-state0','held_state0/ac_001.txt'),('ac-state1','held_state1/ac_001.txt')]}
    return dict(schema='nebula-programmable-receiver-reviewed-v1',parent_setting=352,parent_ctle_sha256=B.sha(parent/'design.cir'),
        parent_unchanged=True,status='EXPERIMENTAL_NOMINAL_AC_AND_SIGNAL',nominal_ac_match=True,signal_gate_pass=True,
        nominal_receiver_verified=False,full_receiver_verified=False,signed_model_domain_pass=link['signed_model_domain_pass'],
        control_voltage_v=[1.8*x for x in control],r_fraction=control[0],c_fraction=control[1],
        target_boost_db=6.,target_frequency_hz=2.1e9,internal_tolerance_db=.5,internal_tolerance_hz=1e8,
        response=response,control_points=points,correct_bits=link['correct_bits'],scored_bits=link['scored_bits'],
        eye_height_mv=1e3*link['sampled_eye_height_v'],positive_aperture_ui=link['aperture']['eye_width_ui'],
        aperture_above_100mv_ui=link['aperture']['eye_width_at_100mv_ui'],power_mw=1e3*link['ctle_plus_dfe_vdd_power_w'],
        model_violations=violations,noise_status='Instrument rejected on convergence warning; no measurement credited',hd3_status='Not run after noise instrument rejection',
        pvt_status='Not verified for this derived receiver',runtime_tuning_verified=False,
        control_selection='Deterministic calibration among three measured existing controls, not RL',
        scope='Derived from selected352; same amplifier, attenuator, bias and DFE, new physical Rs/Cs network. Nominal TT/1.8V/27C, external clock phase1UI/tap2, constructed7.5dB channel. Not the fixed352 circuit or independent9dB reference.',
        retained_failures='Two unresolved held-state batches and two convergence-warning analog cases; initial zero-call control-validation failure retained.',
        charged_calls=sum(h['charged_calls'] for h in history),call_history=history,verified_archived_files=verified,
        experiment_bindings=bindings,artifacts=artifacts,generator_matches_normalized_measured_deck=True,
        newline_note='Structural export is LF; measurement writer records Windows newlines. Exact measured deck is served; normalized generator equivalence is checked separately.',
        simulations_launched=0,read_only=True)

def main():
    result=review();OUT.mkdir(parents=True,exist_ok=False)
    (OUT/'review.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('status','charged_calls','verified_archived_files','response','eye_height_mv','power_mw','signed_model_domain_pass')},indent=2))

if __name__=='__main__':main()
