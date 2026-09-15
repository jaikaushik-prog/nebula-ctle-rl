"""Lossless gzip siblings for large immutable traces; never delete raw data."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def archive(root):
    root = Path(root).resolve()
    index = root/'trace_archives.json'
    if index.exists():
        raise FileExistsError(index)
    manifest = json.loads((root/'evidence_sha256.json').read_text())
    traces = []
    # Validate the entire immutable source set before writing any archive.
    for key, expected in manifest.items():
        path = (root/key).resolve()
        if not path.is_relative_to(root):
            raise ValueError('manifest path escapes artifact root')
        if sha(path.read_bytes()) != expected:
            raise ValueError(f'evidence hash differs: {key}')
        if path.name in ('trace.txt', 'terminals.txt'):
            dest = path.with_suffix('.txt.gz')
            if dest.exists():
                raise FileExistsError(dest)
            traces.append((path, dest, expected))
    rows = []
    for raw, dest, expected in traces:
        data = raw.read_bytes()
        compressed = gzip.compress(data, compresslevel=6, mtime=0)
        if sha(gzip.decompress(compressed)) != expected:
            raise ValueError('gzip round-trip changed original bytes')
        with dest.open('xb') as stream:
            stream.write(compressed)
        if sha(gzip.decompress(dest.read_bytes())) != expected:
            raise ValueError('stored gzip differs from original trace')
        rows.append({'raw': raw.relative_to(root).as_posix(),
                     'gzip': dest.relative_to(root).as_posix(),
                     'raw_sha256': expected, 'gzip_sha256': sha(compressed),
                     'raw_bytes': len(data), 'gzip_bytes': len(compressed)})
    result = {'raw_bytes_preserved': True, 'archives': rows,
              'original_manifest_sha256': sha((root/'evidence_sha256.json').read_bytes())}
    with index.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    result = archive(parser.parse_args().root)
    print(f'Archived {len(result["archives"])} traces; originals retained.')
