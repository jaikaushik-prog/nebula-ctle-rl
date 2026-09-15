"""Verify a complete uncompressed experiment bundle without a gzip index."""
import json
from pathlib import Path, PurePosixPath
import re

from nebula.experiments.evidence_archive import digest


def _unique(pairs):
    result={}
    for key,value in pairs:
        if key in result: raise ValueError('duplicate manifest key')
        result[key]=value
    return result


def verify(root):
    root=Path(root).resolve(); manifest=root/'evidence_sha256.json'
    rows=json.loads(manifest.read_text(encoding='utf-8'),object_pairs_hook=_unique)
    if not isinstance(rows,dict) or not rows: raise ValueError('empty/invalid raw manifest')
    for key,expected in rows.items():
        p=PurePosixPath(key)
        if (not key or p.is_absolute() or '..' in p.parts or '\\' in key or ':' in key
                or key!=p.as_posix() or key=='evidence_sha256.json'
                or not isinstance(expected,str) or not re.fullmatch('[0-9a-f]{64}',expected)):
            raise ValueError('invalid raw manifest path/hash')
        file=(root/key).resolve()
        if not file.is_relative_to(root) or not file.is_file(): raise ValueError('missing/escaping raw evidence')
        if digest(file)!=expected: raise ValueError('raw evidence hash mismatch: '+key)
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p!=manifest}
    if actual!=set(rows): raise ValueError('raw evidence membership mismatch')
    return {'manifest_sha256':digest(manifest),'file_count':len(rows)}
