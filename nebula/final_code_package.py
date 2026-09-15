"""Explicit source/saved-evidence ZIP; never runs a simulator or edits evidence."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess,zipfile,datetime,shutil

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/submission/Nebula_Final_Code_20260915.zip'
STAGE=ROOT/'tmp/final-code-package/extracted-final'
SKIP_DIRS={'.git','.claude','.pytest_cache','__pycache__','node_modules','resources','references','web_preview_runs','quarantine','.venv','venv'}
EXT={'.spiceinit','.py','.md','.json','.jsonl','.gz','.pth','.pt','.npz','.npy','.cir','.spice','.log','.csv','.js','.css','.html','.txt','.png','.svg','.s2p','.s4p','.yaml','.yml','.toml','.ini'}
FULL_AUDITS={'generated_receiver_6db_2p1ghz_20260915','entry158_loaded_tuning_20260915'}
AUDITS={'entry100_20260906','entry101_fixed490_20260906','entry113_attribution_20260907','entry113_models_20260907','entry115_exhaustive_benchmark_20260908','entry115_physical_recovery_20260908','entry131_configurable_rc_fine_20260910','entry143_dfe_calibrated_verification_20260910','entry144_dfe_calibrated_pvt_20260910','entry158_loaded_tuning_20260915','generated_receiver_6db_2p1ghz_20260915','submission_recovery_20260915','continuous_cs_coverage_20260915','submission_analog_pvt_20260914'}
RUNS={'4608cf1c525f4e59b2d5226059b0ce5d','daf7cf8a8bb5425b9be750f6cd804a87'}
TOP={'AGENTS.md','HANDOFF.md','CLAUDEwa.md','requirements.txt','.gitignore','.gitattributes','pytest.ini','pyproject.toml'}
EXCLUDE_NAMES=re.compile(r'demo.*(script|word|natural|note)|(?:script|recording|narration).*demo|final_demo|SUBMISSION_.*DEMO|recording_checklist|email_draft|independent_judge|presentation_note|current_app_demo|final_web_app_demo',re.I)
SECRET=re.compile(rb'(?:sk-ant-[A-Za-z0-9_-]{35,}|sk-proj-[A-Za-z0-9_-]{35,}|gh[pousr]_[A-Za-z0-9]{30,}|AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def safe(r):
    p=Path(r)
    if p.is_absolute() or '..' in p.parts or set(p.parts)&SKIP_DIRS:return False
    if any(x.lower().startswith('.env') or x.lower() in {'sky130a','sky130_fd_pr','libs.tech','libs.ref','open_pdks','volare'} for x in p.parts):return False
    if EXCLUDE_NAMES.search(p.name) or p.name.endswith('.runlock.json'):return False
    if any(x in p.name.lower() for x in ('credential','secret','api_key')):return False
    if p.name.startswith('final_demo_script') or p.suffix.lower() in {'.pdf','.docx','.doc','.mp4','.mov','.avi','.zip','.pem','.key','.exe','.dll','.jpg','.jpeg'}:return False
    return p.suffix.lower() in EXT or p.name in TOP or p.name=='.spiceinit'

def members():
    chosen={ROOT/n for n in TOP if (ROOT/n).is_file()};omitted=[]
    registry=json.loads((ROOT/'nebula/physical_verified_registry.json').read_text())
    registry_roots=[e['evidence_dir'].replace('\\','/') for e in registry['entries']]
    for base in ('nebula','python_models','tests'):
        for folder,dirs,files in os.walk(ROOT/base):
            dirs[:]=[d for d in dirs if d not in SKIP_DIRS and not os.path.islink(Path(folder)/d) and not os.path.isjunction(Path(folder)/d)]
            relative=Path(folder).relative_to(ROOT)
            if relative==Path('nebula/product_audits'):
                dirs[:]=[d for d in dirs if d in AUDITS or d.startswith('entry160_programmable_receiver')]
            if relative==Path('nebula/product_demo'):
                dirs[:]=[d for d in dirs if d in {'submission_runs_20260915_v2','rl_hybrid_9db_1p9ghz','touchstone_synthetic_demo'}]
            if relative==Path('nebula/product_demo/submission_runs_20260915_v2'):
                dirs[:]=[d for d in dirs if d in RUNS]
            for name in files:
                p=Path(folder)/name;r=p.relative_to(ROOT);s=r.as_posix()
                if not safe(r):continue
                if p.is_symlink() or os.path.isjunction(p):raise ValueError('Unsafe source path '+s)
                size=p.stat().st_size
                if len(r.parts)>2 and r.parts[1]=='product_audits':
                    if r.parts[2]=='submission_recovery_20260915' and len(r.parts)>4 and p.name!='workflow_receipt.json':
                        continue
                    if r.parts[2]=='entry115_physical_recovery_20260908' and len(r.parts)>4 and not any(s.startswith(x+'/') for x in registry_roots):
                        continue
                    full=r.parts[2] in FULL_AUDITS or r.parts[2].startswith('entry160_programmable_receiver') or any(s.startswith(x+'/') for x in registry_roots)
                    # Preserve complete chosen science; leave enormous older traces external.
                    if not full and p.suffix.lower() in {'.txt','.raw','.csv','.npy','.npz'} and size>1_000_000:
                        omitted.append({'path':s,'bytes':size,'reason':'Historical large raw data; not required for saved application replay'});continue
                if p.suffix.lower()=='.spice':
                    raw=p.read_bytes()
                    if re.search(rb'^\s*\.model\s+sky130_',raw,re.I|re.M):
                        omitted.append({'path':s,'bytes':size,'reason':'External PDK model card'});continue
                chosen.add(p)
    # Some experiment modules read historical root manifests at import time.
    for folder in (ROOT/'nebula/product_audits').iterdir():
        if folder.is_dir() and not folder.is_symlink():
            chosen.update(p for p in folder.iterdir() if p.is_file() and p.suffix=='.json' and safe(p.relative_to(ROOT)))
    return sorted(chosen),omitted

VERIFY='''"""Verify extracted package membership hashes; no third-party modules needed."""
from pathlib import Path
import hashlib,json,sys
root=Path(__file__).resolve().parent
m=json.loads((root/'CODE_MANIFEST.json').read_text(encoding='utf-8'))
fail=[]
for name,digest in m['files'].items():
    p=(root/name).resolve()
    if not p.is_relative_to(root) or not p.is_file():fail.append(name);continue
    with p.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
    if actual!=digest:fail.append(name)
if fail:
    print('FAIL: missing or changed files: '+', '.join(fail[:20]));sys.exit(1)
print('PASS: '+str(len(m['files']))+' packaged files match their SHA-256 hashes.')
'''

def prepare():
    if STAGE.exists():raise FileExistsError('Preserve prior extraction: '+str(STAGE))
    paths,omitted=members()
    print('Selected files:',len(paths),'Uncompressed MB:',round(sum(p.stat().st_size for p in paths)/1e6,1),'Omitted large raw files:',len(omitted),flush=True)
    STAGE.mkdir(parents=True)
    manifest=dict(schema='nebula-final-code-v1',created_local=datetime.datetime.now().astimezone().isoformat(),
        scope='Current working-tree source and saved application evidence; report/video supplied separately; not clean-machine scientific reproduction',
        git_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        source_tree_was_dirty=True,files={},omitted_large_or_external_evidence=omitted,
        exclusions=['Duplicate benchmark raw candidate trees and unregistered historical candidates (summaries/receipts retained)','Reports/videos/narration','Installed PDK and external references','Environments/credentials/Git/scratch','Unselected saved UI runs','Historical raw traces listed above; unrelated audit roots omitted'])
    for i,p in enumerate(paths):
        name=p.relative_to(ROOT).as_posix();data=p.read_bytes()
        if p.suffix.lower() in {'.py','.json','.jsonl','.md','.txt','.log','.yaml','.yml','.toml','.ini'} and SECRET.search(data):raise ValueError('Possible secret in '+name)
        dest=STAGE/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
        digest=hashlib.sha256(data).hexdigest()
        if sha(p)!=digest:raise ValueError('Source changed while copying '+name)
        manifest['files'][name]=digest
        if i and i%4000==0:print('Copied',i,'files',flush=True)
    for name,data in {'START_HERE.md':(ROOT/'nebula/SUBMISSION_CODE_README.md').read_bytes(),'verify_package.py':VERIFY.encode()}.items():
        (STAGE/name).write_bytes(data);manifest['files'][name]=hashlib.sha256(data).hexdigest()
    (STAGE/'CODE_MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('Prepared isolated copy:',STAGE,flush=True)

def pack():
    if OUT.exists():raise FileExistsError(OUT)
    m=json.loads((STAGE/'CODE_MANIFEST.json').read_text())
    validation=STAGE/'PACKAGE_VALIDATION.json'
    if not validation.is_file() or json.loads(validation.read_text()).get('status')!='PASS':raise ValueError('Extracted package validation required')
    m['files']['PACKAGE_VALIDATION.json']=sha(validation)
    (STAGE/'CODE_MANIFEST.json').write_text(json.dumps(m,indent=2),encoding='utf-8')
    with zipfile.ZipFile(OUT,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as z:
        for i,name in enumerate(sorted(m['files'])):
            p=STAGE/name
            if sha(p)!=m['files'][name]:raise ValueError('Package changed '+name)
            z.write(p,name)
            if i and i%4000==0:print('Archived',i,'files',flush=True)
        z.write(STAGE/'CODE_MANIFEST.json','CODE_MANIFEST.json')
    with zipfile.ZipFile(OUT) as z:
        assert len(z.namelist())==len(set(z.namelist()))==len(m['files'])+1
        for name,digest in m['files'].items():
            with z.open(name) as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
            if actual!=digest:raise ValueError('ZIP verification failed '+name)
    digest=sha(OUT)
    OUT.with_suffix('.zip.sha256').write_text(digest+'  '+OUT.name+'\n',encoding='ascii')
    result=dict(status='PASS',zip=str(OUT),bytes=OUT.stat().st_size,sha256=digest,files=len(m['files']),omitted_large_raw_files=len(m['omitted_large_or_external_evidence']))
    OUT.with_suffix('.validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','pack']);a=p.parse_args()
    prepare() if a.action=='prepare' else pack()
