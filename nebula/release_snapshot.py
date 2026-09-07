"""Private working-tree release snapshot; excludes references and credentials."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUFFIXES = {'.py','.md','.json','.jsonl','.gz','.pth','.pt','.npz','.npy',
            '.cir','.spice','.spiceinit','.log','.js','.css','.html','.txt','.png','.svg','.s2p','.s4p'}
BLOCKED = {'resources','references','.claude','.git','__pycache__','.pytest_cache','node_modules'}
TOP = {'AGENTS.md','HANDOFF.md','CLAUDEwa.md','README.md','requirements.txt','pytest.ini','pyproject.toml'}


def included(relative):
    p = Path(relative)
    if p.is_absolute() or '..' in p.parts or set(p.parts).intersection(BLOCKED):
        return False
    if any(x.startswith('.env') or 'secret' in x.lower() or 'credential' in x.lower() for x in p.parts):
        return False
    if len(p.parts)==1:
        return p.name in TOP
    if p.parts[0] in ('nebula','python_models','tests'):
        return p.suffix.lower() in SUFFIXES or p.name == '.spiceinit'
    return p.as_posix() in {
        'output/pdf/Nebula_Competition_Report.pdf',
        'output/pdf/Nebula_Competition_Report_sources.json',
        'output/pdf/Nebula_Competition_Report_review.json'}


def verify_archive(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('duplicate archive names')
        manifest = json.loads(archive.read('RELEASE_MANIFEST.json'))
        expected = set(manifest['files']) | {'RELEASE_MANIFEST.json'}
        if set(names) != expected:
            raise ValueError('release membership mismatch')
        for name, expected_hash in manifest['files'].items():
            if not included(name):
                raise ValueError('forbidden release member: '+name)
            if hashlib.sha256(archive.read(name)).hexdigest() != expected_hash:
                raise ValueError('release hash mismatch: '+name)
    return manifest


def build(out):
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        raise FileExistsError(out)
    paths = []
    for name in TOP:
        if (ROOT/name).is_file(): paths.append(ROOT/name)
    for name in ('nebula','python_models','tests'):
        paths += [p for p in (ROOT/name).rglob('*') if p.is_file() and included(p.relative_to(ROOT))]
    paths += [ROOT/'output/pdf'/name for name in (
        'Nebula_Competition_Report.pdf','Nebula_Competition_Report_sources.json','Nebula_Competition_Report_review.json')]
    paths = sorted(set(paths))
    for p in paths:
        if not p.resolve().is_relative_to(ROOT.resolve()):
            raise ValueError('release path escapes workspace')
    packages={}
    for name in ('numpy','scipy','torch','matplotlib','pandas','pytest','reportlab','pypdf','pdfplumber','PyMuPDF','Pillow'):
        try: packages[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: packages[name]=None
    manifest=dict(scope='Private working-tree source/evidence snapshot, including pre-existing uncommitted product files. Not a clean-commit or clean-machine claim.',
        python=platform.python_version(), platform=platform.platform(), packages=packages,
        head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        pdk='External SKY130A; recorded volare revision c6d73a35f524070e85faff4a6a9eef49553ebc2b; installed files are separately fingerprinted in the model audit.',
        simulator='ngspice 41, ngspice_con.exe', files={})
    with zipfile.ZipFile(out,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for p in paths:
            name=p.relative_to(ROOT).as_posix()
            data=p.read_bytes()
            manifest['files'][name]=hashlib.sha256(data).hexdigest()
            archive.writestr(name,data)
        archive.writestr('RELEASE_MANIFEST.json',json.dumps(manifest,indent=2))
    verified=verify_archive(out)
    digest=hashlib.sha256(out.read_bytes()).hexdigest()
    out.with_suffix(out.suffix+'.sha256').write_text(digest+'  '+out.name+'\n')
    print(f"Verified {len(verified['files'])} source/evidence files; {out.stat().st_size/1e6:.1f} MB; SHA256 {digest}")
    return verified


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,required=True)
    build(parser.parse_args().out)
