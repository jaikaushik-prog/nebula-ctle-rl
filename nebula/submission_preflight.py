"""Read-only saved-submission preflight; no SPICE, training or package creation."""
import argparse
import json
import re
import sys
from pathlib import Path
from nebula.submission_evidence import SAVED_ROOT, FINAL_RUN, checked_file, evidence_index

SPICE_BINARY=Path('C:/Users/DELL/miniforge3/envs/nebula/Library/bin/ngspice_con.exe')

def check_runtime(path=None):
    path=Path(path or SPICE_BINARY)
    if not path.is_file():raise ValueError('Recorded ngspice runtime is unavailable: '+str(path))
    return dict(path=str(path),exists=True,executed=False)

def check_run(root=SAVED_ROOT, run_id=FINAL_RUN):
    folder=Path(root)/run_id
    if Path(run_id).name != run_id or not folder.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError('Unsafe run ID')
    receipt=json.loads((folder/'workflow_receipt.json').read_text(encoding='utf-8'))
    if not receipt.get('output_complete') or not receipt.get('delivered_success'):
        raise ValueError('Saved workflow is not an accepted complete output')
    count=0
    for name,digest in receipt['artifact_sha256'].items():
        checked_file(folder,name,digest); count+=1
    attempt_count=0
    for attempt in receipt.get('attempts',[]):
        candidate=folder/'physical_recovery'/Path(attempt['directory']).name
        manifest=json.loads((candidate/'evidence_sha256.json').read_text(encoding='utf-8'))
        for name,digest in manifest.items():
            checked_file(candidate,name.replace('\\','/'),digest);attempt_count+=1
    runtime=check_runtime()
    index=evidence_index(folder,run_id)
    deck=(folder/'design.cir').read_text(encoding='utf-8')
    libraries=re.findall(r'^\s*\.lib\s+"([^"]+)"',deck,re.M|re.I)
    paths=[dict(path=p,exists=Path(p).is_file()) for p in libraries]
    if not libraries or not all(x['exists'] for x in paths):
        raise ValueError('A recorded direct PDK library is unavailable; decks were not rewritten')
    return dict(status='PASS',run_id=run_id,workflow_artifacts_checked=count,
        evidence_rows=len(index['rows']),attempt_artifacts_checked=attempt_count,
        direct_pdk_paths=paths,ngspice_runtime=runtime,python=sys.version.split()[0],
        simulations_launched=0,files_modified=0,
        scope='Saved output and direct model-path integrity only; not full transitive PDK certification or simulator runtime signoff.')

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-root',type=Path,default=SAVED_ROOT);p.add_argument('--run-id',default=FINAL_RUN)
    args=p.parse_args(argv)
    try: result=check_run(args.run_root,args.run_id)
    except (OSError,ValueError,KeyError,TypeError) as exc:
        print(json.dumps(dict(status='FAIL',error=str(exc),simulations_launched=0)));return 1
    print(json.dumps(result,indent=2));return 0

if __name__=='__main__':raise SystemExit(main())
