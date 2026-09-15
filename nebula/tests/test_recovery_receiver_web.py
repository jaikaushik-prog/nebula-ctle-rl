"""Recorded nested receiver files are hash-checked and confined to their run."""
import hashlib
import json
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import urlopen
import pytest
from nebula.web.recovery_server import RecoveryWebApp, make_server

@pytest.fixture
def app(tmp_path):
    folder=tmp_path/('c'*32);(folder/'receiver').mkdir(parents=True)
    source=Path('nebula/product_demo/physical_bias_9db_1p9ghz_20260906/design.json')
    (folder/'design.json').write_bytes(source.read_bytes())
    (folder/'receiver/receiver.cir').write_bytes(b'* structural test receiver\n.end\n')
    (folder/'receiver/metadata.json').write_text(json.dumps({'structurally_integrated':True,'nominal_transistor_verified':False,'full_receiver_verified':False}))
    names=['design.json','receiver/receiver.cir','receiver/metadata.json']
    receipt=dict(output_complete=True,delivered_success=True,wall_s=1,status='accepted',attempts=[],spice_calls=0,
        artifact_sha256={n:hashlib.sha256((folder/n).read_bytes()).hexdigest() for n in names})
    (folder/'workflow_receipt.json').write_text(json.dumps(receipt))
    instance=RecoveryWebApp(run_root=tmp_path)
    yield instance,folder
    instance.close()

def test_saved_receiver_is_published_and_hashed(app):
    instance,folder=app
    assert 'receiver/receiver.cir' in instance.designs[folder.name]['artifacts']
    assert instance.artifact(folder.name,'receiver/receiver.cir')==folder/'receiver/receiver.cir'
    (folder/'receiver/receiver.cir').write_text('changed')
    assert instance.artifact(folder.name,'receiver/receiver.cir') is None

@pytest.mark.parametrize('name',['receiver/../design.json','receiver\\receiver.cir','../design.json','receiver/unrecorded.cir','receiver/receiver.cir/extra'])
def test_unsafe_or_unrecorded_nested_path_is_rejected(app,name):
    instance,folder=app
    assert instance.artifact(folder.name,name) is None

def test_http_opens_recorded_receiver_and_refuses_unrecorded(app):
    instance,folder=app
    server=make_server(instance,'127.0.0.1',0)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}/api/artifacts/{folder.name}/'
    try:
        with urlopen(base+quote('receiver/receiver.cir',safe='')) as response:
            assert response.read()==(folder/'receiver/receiver.cir').read_bytes()
        with pytest.raises(HTTPError) as failure:
            urlopen(base+'receiver/unrecorded.cir')
        assert failure.value.code==404
    finally:
        server.shutdown();server.server_close();thread.join()
