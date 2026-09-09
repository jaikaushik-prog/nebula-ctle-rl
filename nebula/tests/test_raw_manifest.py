import hashlib
import json

import pytest

from nebula.experiments import raw_manifest as M


def bundle(tmp_path):
    p=tmp_path/'raw.txt'; p.write_bytes(b'raw measurement\n')
    (tmp_path/'evidence_sha256.json').write_text(json.dumps({'raw.txt':hashlib.sha256(p.read_bytes()).hexdigest()}))


def test_exact_raw_bundle_and_corruption(tmp_path):
    bundle(tmp_path)
    assert M.verify(tmp_path)['file_count']==1
    (tmp_path/'raw.txt').write_bytes(b'changed')
    with pytest.raises(ValueError,match='hash mismatch'): M.verify(tmp_path)


@pytest.mark.parametrize('change',['extra','missing','escape','duplicate','bad_hash'])
def test_invalid_raw_membership_is_not_verified(tmp_path,change):
    bundle(tmp_path); manifest=tmp_path/'evidence_sha256.json'
    if change=='extra': (tmp_path/'extra.txt').write_text('unexpected')
    if change=='missing': (tmp_path/'raw.txt').unlink()
    if change=='escape': manifest.write_text(json.dumps({'../outside':'0'*64}))
    if change=='duplicate': manifest.write_text('{"raw.txt":"'+'0'*64+'","raw.txt":"'+'0'*64+'"}')
    if change=='bad_hash': manifest.write_text(json.dumps({'raw.txt':'invalid'}))
    with pytest.raises(ValueError): M.verify(tmp_path)
