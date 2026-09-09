"""Read-only, streaming verification of original manifests and gzip siblings."""
import gzip
import hashlib
import json
from pathlib import Path


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def trace_path(raw):
    raw=Path(raw)
    compressed=raw.with_suffix(raw.suffix+'.gz')
    if compressed.is_file(): return compressed
    if raw.is_file(): return raw
    raise FileNotFoundError(raw)


def verify(root):
    root=Path(root).resolve()
    manifest=json.loads((root/'evidence_sha256.json').read_text())
    index=json.loads((root/'trace_archives.json').read_text())
    if (not manifest or index.get('raw_bytes_preserved') is not True
            or digest(root/'evidence_sha256.json') != index['original_manifest_sha256']):
        raise ValueError('original evidence manifest hash differs')
    def member(key):
        path=(root/key).resolve()
        if not path.is_relative_to(root):
            raise ValueError('evidence path escapes root')
        return path
    rows={}
    for row in index['archives']:
        key=row['raw']
        if key in rows or key not in manifest or row['gzip'] != key+'.gz':
            raise ValueError('duplicate or invalid archive mapping')
        member(key)
        compressed=member(row['gzip'])
        if (Path(key).name not in ('trace.txt','terminals.txt')
                or row['raw_sha256'] != manifest[key]
                or compressed.stat().st_size != row['gzip_bytes']
                or digest(compressed) != row['gzip_sha256']):
            raise ValueError('archive hash or size differs')
        sha=hashlib.sha256()
        size=0
        with gzip.open(compressed,'rb') as stream:
            while chunk := stream.read(4*1024*1024):
                sha.update(chunk)
                size+=len(chunk)
        if sha.hexdigest() != manifest[key] or size != row['raw_bytes']:
            raise ValueError('original trace hash or size differs')
        rows[key]=row
    expected_traces={key for key in manifest if Path(key).name in ('trace.txt','terminals.txt')}
    if set(rows) != expected_traces:
        raise ValueError('missing or extra trace archives')
    for key,expected in manifest.items():
        path=member(key)
        if key not in rows and digest(path) != expected:
            raise ValueError(f'evidence hash differs: {key}')
    return {'verified_files':len(manifest),'verified_archives':len(rows),
            'manifest_sha256':index['original_manifest_sha256']}
