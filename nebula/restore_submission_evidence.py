"""Restore byte-identical saved waveforms from Git-friendly gzip files; no SPICE."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def safe_path(root: Path, name: str) -> Path:
    if not isinstance(name, str) or not name or '\\' in name or ':' in name:
        raise ValueError('Invalid evidence path')
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()) or Path(name).is_absolute():
        raise ValueError('Evidence path escapes repository')
    return path


def restore(root: Path, manifest: dict, check_only: bool = False) -> dict:
    counts = {'restored': 0, 'already_present': 0}
    for row in manifest['files']:
        target = safe_path(root, row['path'])
        source = safe_path(root, row['gzip_path'])
        if target.exists():
            if not target.is_file() or digest(target) != row['sha256']:
                raise ValueError('Existing evidence differs; refusing to overwrite: ' + row['path'])
            counts['already_present'] += 1
            continue
        if check_only:
            raise FileNotFoundError('Run restore first: ' + row['path'])
        if digest(source) != row['gzip_sha256']:
            raise ValueError('Compressed evidence hash mismatch: ' + row['gzip_path'])
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.nebula-restore-', delete=False) as output:
                temporary = Path(output.name)
                total = 0
                with gzip.open(source, 'rb') as stream:
                    while chunk := stream.read(1024 * 1024):
                        total += len(chunk)
                        if total > row['bytes']:
                            raise ValueError('Expanded evidence exceeds recorded size')
                        output.write(chunk)
            if total != row['bytes'] or digest(temporary) != row['sha256']:
                raise ValueError('Restored evidence hash mismatch: ' + row['path'])
            # Exclusive creation prevents replacing a concurrently created file.
            with target.open('xb') as output, temporary.open('rb') as stream:
                while chunk := stream.read(1024 * 1024):
                    output.write(chunk)
            counts['restored'] += 1
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Verify restored files without writing')
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'nebula/submission_compressed_evidence.json').read_text(encoding='utf-8'))
    counts = restore(ROOT, manifest, args.check)
    print('PASS: saved evidence ' + json.dumps(counts) + '; zero simulations or training.')


if __name__ == '__main__':
    main()
