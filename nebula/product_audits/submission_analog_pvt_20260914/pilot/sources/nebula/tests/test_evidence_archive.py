"""Portable trace archives must retain the original evidence, not just gzip CRC."""
import gzip
import hashlib
import json

import pytest

from nebula.experiments import evidence_archive as A


def fixture(root):
    (root/'case').mkdir()
    raw=b'0 1 0 2\r\n1 3 1 4\r\n'
    compressed=gzip.compress(raw,mtime=0)
    (root/'case/trace.txt.gz').write_bytes(compressed)
    (root/'summary.json').write_text('{}')
    sha=lambda b: hashlib.sha256(b).hexdigest()
    manifest={'case/trace.txt':sha(raw),'summary.json':sha(b'{}')}
    (root/'evidence_sha256.json').write_text(json.dumps(manifest))
    index={'original_manifest_sha256':A.digest(root/'evidence_sha256.json'),
           'raw_bytes_preserved':True,'archives':[{'raw':'case/trace.txt',
           'gzip':'case/trace.txt.gz','raw_sha256':sha(raw),'gzip_sha256':sha(compressed),
           'raw_bytes':len(raw),'gzip_bytes':len(compressed)}]}
    (root/'trace_archives.json').write_text(json.dumps(index))
    return index


def test_archive_validates_without_local_uncompressed_originals(tmp_path):
    fixture(tmp_path)
    result=A.verify(tmp_path)
    assert result['verified_files']==2 and result['verified_archives']==1
    assert A.trace_path(tmp_path/'case/trace.txt').name=='trace.txt.gz'
    assert not (tmp_path/'case/trace.txt').exists()


@pytest.mark.parametrize('fault',['gzip','summary','index_sha','escape','duplicate','size'])
def test_archive_rejects_changed_or_ambiguous_evidence(tmp_path,fault):
    index=fixture(tmp_path)
    if fault=='gzip': (tmp_path/'case/trace.txt.gz').write_bytes(gzip.compress(b'wrong'))
    elif fault=='summary': (tmp_path/'summary.json').write_text('{"changed":true}')
    elif fault=='index_sha': index['original_manifest_sha256']='0'*64
    elif fault=='escape': index['archives'][0]['gzip']='../outside.gz'
    elif fault=='duplicate': index['archives'].append(index['archives'][0])
    else: index['archives'][0]['raw_bytes']+=1
    (tmp_path/'trace_archives.json').write_text(json.dumps(index))
    with pytest.raises(ValueError): A.verify(tmp_path)
