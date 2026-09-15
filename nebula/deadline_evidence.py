"""Recompute narrow deadline diagnostics from pinned saved records; no simulation."""
import gzip
import json
from statistics import mean, median
from nebula.submission_evidence import ROOT,checked_file,sha,receiver_artifact,CTLE_SHA

ORACLE=ROOT/'nebula/product_audits/entry115_exhaustive_benchmark_20260908'
COST=ROOT/'nebula/product_audits/submission_recovery_20260915'

def rl_certificate():
    path=checked_file(ORACLE,'per_identity.jsonl.gz','d5b52971ad58a69989c43b73f2b96e1fc4914c89eff95f68b7b4d4a0faa7644a')
    summary_path=checked_file(ORACLE,'summary.json','b5c33e4584a4054ea21d6e8ff4f78f67834900862212f305f863cccc0fcbd9e6')
    with gzip.open(path,'rt') as stream:rows=[json.loads(line) for line in stream]
    unique={(r['seed'],tuple(r['identity'])) for r in rows}
    if len(rows)!=12150 or len(unique)!=len(rows):raise ValueError('Incomplete or duplicate oracle identities')
    for r in rows:
        if abs(r['quality_regret']-(r['oracle_quality']-r['policy_quality']))>1e-12:raise ValueError('Inconsistent row regret')
        if r['within_0p05']!=(r['quality_regret']<=.05):raise ValueError('Inconsistent near-oracle flag')
        if r['exhaustive_visits']!=512:raise ValueError('Different candidate bank')
    old=json.loads(summary_path.read_text())['aggregate']
    regret=mean(r['quality_regret'] for r in rows);within=mean(r['within_0p05'] for r in rows)
    if abs(regret-old['mean_regret_oracle_solvable'])>1e-12 or abs(within-old['fraction_within_0p05'])>1e-12:
        raise ValueError('Aggregate does not reproduce')
    costs=checked_file(COST,'workflows.jsonl','674cb77d7c71070fea4432d46575d12a3402dfa8bbf2bcb72a7380f83fbe0cd8')
    workflows=[json.loads(line) for line in costs.read_text().splitlines()]
    bench=[r for r in workflows if r['purpose']=='benchmark']
    if len(workflows)!=37 or len(bench)!=24:raise ValueError('Incomplete workflow membership')
    arms={};pairs={}
    for arm in ('rl','classical'):
        selected=[r for r in bench if r['selection_mode']==arm]
        if len(selected)!=12:raise ValueError('Unequal planned arms')
        arms[arm]=dict(attempted=12,delivered=sum(r['delivered_success'] for r in selected),
            charged_calls=sum(r['spice_calls'] for r in selected),wall_seconds=sum(r['parent_wall_s'] for r in selected))
        for r in selected:
            key=(r['target_id'],r['repeat']);pair=pairs.setdefault(key,{})
            if arm in pair:raise ValueError('Duplicate benchmark pair')
            pair[arm]=r
            if r.get('workflow_receipt'):
                checked_file(COST,r['workflow_receipt'],r['workflow_receipt_sha256'])
    if len(pairs)!=12 or any(set(p)!=set(arms) for p in pairs.values()):raise ValueError('Incomplete pairing')
    ratios=[p['classical']['parent_wall_s']/p['rl']['parent_wall_s'] for p in pairs.values()
        if all(r['delivered_success'] for r in p.values())]
    return dict(episodes=len(rows),identities=len({tuple(r['identity']) for r in rows}),seeds=len({r['seed'] for r in rows}),
        mean_quality_regret=regret,fraction_within_0p05=within,policy_quality=mean(r['policy_quality'] for r in rows),
        mean_policy_visits=mean(r['policy_visits'] for r in rows),
        cached_visit_reduction_factor=512/mean(r['policy_visits'] for r in rows),
        arms=arms,both_success_pairs=len(ratios),paired_classical_over_rl_median=median(ratios),
        near_optimality_established=False,speed_advantage_established=False,
        scope='Exposed 512-setting cached oracle; separate 24 complete physical workflows. No new evaluation or training.',
        failure_caveat='One classical non-delivery is a Windows ledger failure, not electrical or RL superiority evidence.',
        source_sha256={str(p.relative_to(ROOT)):sha(p) for p in (path,summary_path,costs)})

def receiver_gap():
    path=receiver_artifact('result.json');r=json.loads(path.read_text())
    devices=[]
    for d in r['whole_circuit_voltage_audit']['devices']:
        if not any(d[k]['below_samples'] or d[k]['above_samples'] for k in ('vds','vgs','vbs')):continue
        devices.append(dict(instance=d['instance'],vds_min_v=d['vds']['min_v'],vds_max_v=d['vds']['max_v'],
            positive_vgs_v=max(0,d['vgs']['max_v']),model=d['model']))
    return dict(selected_setting=352,selected_ctle_sha256=CTLE_SHA,affected_devices=len(devices),devices=devices,
        full_receiver_verified=False,nominal_signal_gate_pass=r['signal_gate_pass'],
        selected_receiver_link_pvt_corners=1,required_pvt_corners=45,
        scope='Selected CTLE plus transistor DFE only; independent reference PVT cannot fill these gaps.',
        decision='Do not swap source/drain labels: all six measured Vds intervals cross zero. Off-state positive Vgs also remains. No topology/model/gate change is authorized by the two-call check.',
        next_gate='A separately approved attenuation-switch design/model-domain review, then nominal OP/AC and signal checks, must precede any receiver PVT campaign.',
        source_sha256={str(path.relative_to(ROOT)):sha(path)})

def diagnostics():
    from nebula.experiments.review_loaded_tuning_bound import review
    return dict(read_only=True,simulations_launched=0,training_steps=0,tuning=review(),rl=rl_certificate(),receiver=receiver_gap())

if __name__=='__main__':print(json.dumps(diagnostics(),indent=2))
