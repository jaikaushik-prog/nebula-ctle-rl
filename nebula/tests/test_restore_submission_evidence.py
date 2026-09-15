import gzip
import hashlib
import pytest
from nebula.restore_submission_evidence import restore, safe_path


def fixture_manifest(root):
    raw = b'original\r\nwaveform\n' * 10
    compressed = gzip.compress(raw, mtime=0)
    (root / 'trace.txt.gz').write_bytes(compressed)
    return {'files': [{'path': 'trace.txt', 'gzip_path': 'trace.txt.gz',
        'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
        'gzip_sha256': hashlib.sha256(compressed).hexdigest()}]}, raw


def test_restores_exact_bytes_and_is_idempotent(tmp_path):
    m, raw = fixture_manifest(tmp_path)
    assert restore(tmp_path, m)['restored'] == 1
    assert (tmp_path / 'trace.txt').read_bytes() == raw
    assert restore(tmp_path, m, True)['already_present'] == 1


def test_never_overwrites_changed_evidence(tmp_path):
    m, _ = fixture_manifest(tmp_path)
    (tmp_path / 'trace.txt').write_bytes(b'user bytes')
    with pytest.raises(ValueError, match='refusing to overwrite'):
        restore(tmp_path, m)
    assert (tmp_path / 'trace.txt').read_bytes() == b'user bytes'


def test_rejects_damaged_gzip(tmp_path):
    m, _ = fixture_manifest(tmp_path)
    (tmp_path / 'trace.txt.gz').write_bytes(b'damaged')
    with pytest.raises(ValueError, match='Compressed evidence hash mismatch'):
        restore(tmp_path, m)
    assert not (tmp_path / 'trace.txt').exists()


def test_rejects_wrong_uncompressed_hash(tmp_path):
    m, _ = fixture_manifest(tmp_path)
    m['files'][0]['sha256'] = '0' * 64
    with pytest.raises(ValueError, match='Restored evidence hash mismatch'):
        restore(tmp_path, m)
    assert not (tmp_path / 'trace.txt').exists()


def test_check_is_read_only(tmp_path):
    m, _ = fixture_manifest(tmp_path)
    with pytest.raises(FileNotFoundError):
        restore(tmp_path, m, True)
    assert not (tmp_path / 'trace.txt').exists()


@pytest.mark.parametrize('name', ['../outside', '/absolute', 'C:/absolute', 'x\\y'])
def test_rejects_unsafe_paths(tmp_path, name):
    with pytest.raises(ValueError):
        safe_path(tmp_path, name)
