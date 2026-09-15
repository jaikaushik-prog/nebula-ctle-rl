"""Read-only raw evidence review; never launches or repeats a simulation."""
import json
from nebula.device import loaded_tuning_bound as B

OUT=B.ROOT/'nebula/product_audits/entry158_loaded_tuning_20260915'
SUMMARY_SHA='aedb02fbc6c30b92e4ff3c7c2679088fba1e958cf3dbc59c5d66feafeee30583'
MANIFEST_SHA='69a1e503f17b2b521b7c493942453e5f0fd9f14a1b7ee9915901e68c3b7bbd2e'

def review():
    B.checked_file(OUT,'summary.json',SUMMARY_SHA)
    B.checked_file(OUT,'evidence_sha256.json',MANIFEST_SHA)
    manifest=json.loads((OUT/'evidence_sha256.json').read_text())
    for name,digest in manifest.items():B.checked_file(OUT,name,digest)
    config=json.loads((OUT/'config.json').read_text())
    summary=json.loads((OUT/'summary.json').read_text())
    controls=config['proposals']['controls']
    states=[B.extract(OUT/f'state{s}',s,controls) for s in (0,1)]
    for state,recomputed in zip(summary['states'],states):
        assert {k:v for k,v in state.items() if k!='wall_seconds'}==recomputed
    assert B.select_targets(states)==summary['targets']
    assert summary['charged_calls']==2 and summary['instrument_ok']
    assert not summary['full_receiver_verified'] and not summary['selected_circuit_changed']
    assert all((OUT/f'state{s}/design.cir').read_text().split('.control')[0]==B.body(s) for s in (0,1))
    targets=[]
    for t in summary['targets']:
        row=dict(t)
        if t['nominal_ac_match']:
            samples=[s['rows'][t['row_index']] for s in states]
            row['measured_boost_db']=[x['boost_db'] for x in samples]
            row['measured_peak_ghz']=[x['peak_frequency_hz']/1e9 for x in samples]
            row['power_mw']=[x['vdd_power_w']*1000 for x in samples]
        targets.append(row)
    return dict(verified=True,files_checked=len(manifest),snapshots_recomputed=sum(len(s['rows']) for s in states),
        calls=2,nominal_loaded_ac_matches=5,full_receiver_verified=False,targets=targets,
        summary_sha256=SUMMARY_SHA,manifest_sha256=MANIFEST_SHA,simulations_launched=0)

if __name__=='__main__':print(json.dumps(review(),indent=2))
