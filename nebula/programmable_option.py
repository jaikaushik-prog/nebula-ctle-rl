"""Hash-bound experimental programmable receiver option; no simulator calls."""
from pathlib import Path
import hashlib,json,shutil
from nebula.submission_evidence import ROOT,CTLE_SHA,checked_file,sha

REVIEW_ROOT=ROOT/'nebula/product_audits/entry160_programmable_receiver_review_20260915'
REVIEW_SHA='f41a0255f6167ceb291aaf6ed359f53b1a800468123deb2591c949e98773e147'
VISUALS={
 'drawing':('device_sheet.svg','cb783a42c742498fdb6279473f834c179a5c05ee81c65c819be3c363a53ed4a5'),
 'drawing-png':('device_sheet.png','9be7f73da2d4cee035ef6f5f0cf46192c9436342a2498b839cc23cbb17601125'),
 'response-eye':('measured_response_eye.png','e5b93dbe7b7f9e446875aac30b7e97214fb724a51b7eae00f9887851674a30c4')}

def _review():
    data=json.loads(checked_file(REVIEW_ROOT,'review.json',REVIEW_SHA).read_text())
    if data['parent_ctle_sha256']!=CTLE_SHA or data['full_receiver_verified'] or data['nominal_receiver_verified']:
        raise ValueError('experimental evidence ownership/status changed')
    return data

def artifact(key):
    data=_review()
    if key=='review':return checked_file(REVIEW_ROOT,'review.json',REVIEW_SHA)
    if key in VISUALS:return checked_file(REVIEW_ROOT,*VISUALS[key])
    if key not in data['artifacts']:raise ValueError('unrecorded programmable artifact')
    record=data['artifacts'][key]
    return checked_file(ROOT,record['path'],record['sha256'])

def for_parent(folder):
    path=Path(folder)/'design.cir'
    if not path.is_file() or sha(path)!=CTLE_SHA:return None
    data=_review()
    for key in ('deck','link-result','summary','ac-state0','ac-state1','response-eye'):artifact(key)
    data['artifact_links']=[dict(key=k,url='/api/submission/programmable-artifact/'+k,sha256=sha(artifact(k)))
        for k in ('deck','drawing','response-eye','review','link-result','config','waveform','terminals')]
    return data

def export_option(design,selected_bytes,directory):
    from nebula.generated_receiver import _accepted,_selected_deck
    _accepted(design);_selected_deck(design,selected_bytes.decode('ascii'))
    if hashlib.sha256(selected_bytes).hexdigest()!=CTLE_SHA:raise ValueError('no measured programmable option for this parent')
    if design['request']['peaking_db']!=6. or design['request']['f_peak_hz']!=2.1e9:
        raise ValueError('no measured programmable calibration for this request')
    data=_review();folder=Path(directory);folder.mkdir(parents=True,exist_ok=False)
    # Copy the exact measured deck, not an unverified regenerated serialization.
    circuit=folder/'receiver.cir';drawing=folder/'device_sheet.svg';metadata_path=folder/'metadata.json'
    shutil.copyfile(artifact('deck'),circuit);shutil.copyfile(artifact('drawing'),drawing)
    metadata=dict(schema='nebula-programmable-option-v1',status=data['status'],derived_from_setting=352,
        parent_ctle_sha256=CTLE_SHA,receiver_deck_sha256=sha(circuit),drawing_sha256=sha(drawing),
        r_fraction=data['r_fraction'],c_fraction=data['c_fraction'],control_voltage_v=data['control_voltage_v'],
        nominal_ac_match=True,signal_gate_pass=True,nominal_receiver_verified=False,full_receiver_verified=False,
        inherits_parent_verification=False,review_sha256=REVIEW_SHA,
        evidence_source='Saved exact measured programmable variant, not fresh verification of this export',
        scope=data['scope'],limits=dict(signed_model_domain_pass=False,noise=data['noise_status'],hd3=data['hd3_status'],pvt=data['pvt_status']))
    metadata_path.write_text(json.dumps(metadata,indent=2,allow_nan=False),encoding='utf-8')
    return metadata,[circuit,drawing,metadata_path]

def eligible(design,selected_bytes):
    return (hashlib.sha256(selected_bytes).hexdigest()==CTLE_SHA and
            design.get('request',{}).get('peaking_db')==6. and design.get('request',{}).get('f_peak_hz')==2.1e9)

def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();metadata,files=export_option(json.loads((args.run/'design.json').read_text()),(args.run/'design.cir').read_bytes(),args.out)
    print(json.dumps(dict(metadata=metadata,files=[str(p) for p in files]),indent=2))

if __name__=='__main__':main()
