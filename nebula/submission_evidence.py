"""Read-only submission evidence index. Never invokes a simulator or alters receipts."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAVED_ROOT = ROOT / 'nebula/product_demo/submission_runs_20260915_v2'
FINAL_RUN = '4608cf1c525f4e59b2d5226059b0ce5d'
GEN_ROOT = ROOT / 'nebula/product_audits/generated_receiver_6db_2p1ghz_20260915'
CTLE_SHA = 'e8f8b0c82e6d797ce6baff14b2df551812915ad575a5b4a6871757b0cce4eaed'
REVIEW_SHA = '5c51c7c8bad36bde3ef691f3d8f23800f345ad5209cf3fb3ffa4b15d406b260f'
RESULT_SHA = 'ab4af88fbb993809e0615935787dc5f56544bbfc609cc9e0f5ba4faa2514d2b2'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def checked_file(root, name, digest):
    if not isinstance(name, str) or '\\' in name or ':' in name:
        raise ValueError('Unsafe evidence path')
    root=Path(root).resolve(); path=(root/name).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError(f'Missing or unsafe evidence: {name}')
    if sha(path) != digest:
        raise ValueError(f'Evidence hash mismatch: {name}')
    return path

def receiver_artifact(name):
    proof=json.loads(checked_file(GEN_ROOT,'independent_review.json',REVIEW_SHA).read_text(encoding='utf-8'))
    # A pinned result and selected circuit are independent of mutable display metadata.
    checked_file(GEN_ROOT,'result.json',RESULT_SHA)
    if proof['selected_ctle']['deck_sha256'] != CTLE_SHA:
        raise ValueError('Receiver CTLE identity mismatch')
    digest=proof['evidence_sha256'].get(name)
    if not digest: raise ValueError('Unrecorded receiver artifact')
    return checked_file(GEN_ROOT,name,digest)

def receiver_for(folder):
    folder=Path(folder)
    if not (folder/'design.cir').is_file() or sha(folder/'design.cir') != CTLE_SHA:
        return None
    result=json.loads(receiver_artifact('result.json').read_text(encoding='utf-8'))
    receiver_artifact('design.cir')
    return dict(circuit_sha256=CTLE_SHA, identity='Selected CTLE + transistor DFE',
        correct_bits=result['correct_bits'], scored_bits=result['scored_bits'],
        eye_height_mv=1000*result['sampled_eye_height_v'],
        positive_aperture_ui=result['aperture']['eye_width_ui'],
        aperture_above_100mv_ui=result['aperture']['eye_width_at_100mv_ui'],
        power_mw=1000*result['ctle_plus_dfe_vdd_power_w'],
        corner=result['corner'], loss_db=result['loss_db'],
        signed_model_domain_pass=result['whole_circuit_voltage_audit']['documented_ranges_ok'],
        full_receiver_verified=result['full_receiver_verified'],
        scope=result['scope'], phase_ui=result['phase_ui'], tap_code=result['code'],
        artifacts=[dict(name=n,url='/api/submission/receiver/'+n,sha256=sha(receiver_artifact(n)))
                   for n in ('result.json','design.cir','trace.txt','terminals.txt','ngspice.log')])

def evidence_index(folder, run_id):
    folder=Path(folder)
    receipt_path=folder/'workflow_receipt.json'
    rows=[]
    if receipt_path.is_file():
        receipt=json.loads(receipt_path.read_text(encoding='utf-8'))
        for name,digest in receipt.get('artifact_sha256',{}).items():
            checked_file(folder,name,digest)
            rows.append(dict(circuit='Selected physical CTLE', artifact=name,
                url=f'/api/artifacts/{run_id}/{name}',sha256=digest,
                scope='45 PVT x 7 constructed losses; 0.8 Vpp differential TX, -3.5 dB de-emphasis; eyes use ideal behavioral DFE. Fixed Rs/Cs; no full receiver or routed area signoff.'))
    receiver=receiver_for(folder)
    if receiver:
        rows += [dict(circuit=receiver['identity'],artifact=a['name'],url=a['url'],sha256=a['sha256'],
                 scope='Nominal TT / 1.8 V / 27 C; 7.5 dB constructed channel, 0.8 Vpp differential TX; external clock phase 1 UI, tap code 2. Six PMOS signed-domain violations; not PVT/BER.') for a in receiver['artifacts']]
    from nebula.web.hardware_checkpoint import NOMINAL_NETLIST, PVT_SUMMARY
    for name,path in [('nominal-netlist',NOMINAL_NETLIST),('pvt-summary',PVT_SUMMARY)]:
        rows.append(dict(circuit='Independent 9 dB / 1.9 GHz reference',artifact=name,
            url='/api/hardware/artifacts/'+name,sha256=sha(path),
            scope='Separate circuit; fixed control fractions Rs 0.7 VDD / Cs 0.185 VDD. 45 transistor link PVT on 7.5 dB channel. Nominal HD3: 100 MHz / 100 mV differential peak; held-clock noise. Not selected-circuit analog PVT.'))
    return dict(run_id=run_id,receiver=receiver,rows=rows,read_only=True,
        note='Hashes identify exact saved bytes. Separate evidence is not appended to historical workflow receipts.')
