"""New workflow outputs retain exact CTLE identity and structural receiver scope."""
import hashlib
import json
from pathlib import Path
import pytest
from nebula import recovery_workflow as W

RUN=Path('nebula/product_demo/submission_runs_20260915_v2/4608cf1c525f4e59b2d5226059b0ce5d')

def prepare(monkeypatch, tmp_path):
    from nebula import physical_design as P
    import nebula.design as D
    design=json.loads((RUN/'design.json').read_text())
    source=RUN/'design.cir'
    # Preserve the saved proof as input only; only temporary outputs are written.
    design['physical_evidence']['directory']=str(RUN.resolve())
    monkeypatch.setattr(W,'_verified',lambda d:True)
    monkeypatch.setattr(P,'report',lambda d:'Recorded CTLE measurements; receiver not measured.')
    def write_outputs(d,out,deck,extra_files):
        out.mkdir(parents=True,exist_ok=True)
        (out/'design.json').write_text(json.dumps(d))
        (out/'design.cir').write_text(deck)
        (out/'design_schematic.png').write_bytes(b'fixture-image')
        (out/'explanation.txt').write_text(extra_files['explanation.txt'])
        return [out/name for name in ('design.json','design.cir','design_schematic.png','explanation.txt')],[]
    monkeypatch.setattr(D,'write_outputs',write_outputs)
    return design, source

def test_export_adds_connected_receiver_without_verification(monkeypatch,tmp_path):
    design,source=prepare(monkeypatch,tmp_path)
    out=tmp_path/'new'
    written,warnings=W._export(design,out)
    assert not warnings
    receiver=out/'receiver/receiver.cir'
    assert receiver.is_file() and receiver in written
    assert (out/'design.cir').read_bytes()==source.read_bytes()
    meta=json.loads((out/'receiver/metadata.json').read_text())
    assert meta['structurally_integrated'] is True
    assert meta['nominal_transistor_verified'] is False and meta['full_receiver_verified'] is False
    assert meta['receiver_deck_sha256']==hashlib.sha256(receiver.read_bytes()).hexdigest()
    assert json.loads((out/'design.json').read_text())['generated_receiver']==meta
    from nebula import programmable_option as O
    option=json.loads((out/'receiver_programmable/metadata.json').read_text())
    assert option['nominal_ac_match'] and not option['full_receiver_verified']
    assert not option['inherits_parent_verification']
    assert (out/'receiver_programmable/receiver.cir').read_bytes()==O.artifact('deck').read_bytes()
    assert json.loads((out/'design.json').read_text())['programmable_receiver_option']==option

def test_workflow_receipt_pins_nested_artifacts(monkeypatch,tmp_path):
    design,_=prepare(monkeypatch,tmp_path)
    monkeypatch.setattr(W,'_parse',lambda text:dict(peaking_db=6,f_peak_hz=2.1e9))
    monkeypatch.setattr(W,'_recover',lambda *args:dict(status='accepted',design=design,attempts=[],spice_calls=0))
    result=W.run_request('6 dB at 2.1 GHz',tmp_path/'new')
    assert result['delivered_success'] is True
    assert set(result['artifact_sha256']) >= {'receiver/receiver.cir','receiver/metadata.json'}
    assert result['full_receiver_compliance'] is False
    assert set(result['artifact_sha256']) >= {'receiver_programmable/receiver.cir','receiver_programmable/metadata.json','receiver_programmable/device_sheet.svg'}

def test_unavailable_optional_evidence_does_not_break_fixed_export(monkeypatch,tmp_path):
    from nebula import programmable_option as O
    design,source=prepare(monkeypatch,tmp_path)
    def unavailable(*args):raise ValueError('Optional evidence integrity mismatch')
    monkeypatch.setattr(O,'export_option',unavailable)
    out=tmp_path/'optional-unavailable'
    written,warnings=W._export(design,out)
    assert not warnings and (out/'receiver/receiver.cir').is_file()
    assert (out/'design.cir').read_bytes()==source.read_bytes()
    assert design['programmable_receiver_option']['status']=='UNAVAILABLE'
    assert not (out/'receiver_programmable').exists()


def test_rejected_design_does_not_gain_receiver(monkeypatch,tmp_path):
    design,_=prepare(monkeypatch,tmp_path)
    monkeypatch.setattr(W,'_verified',lambda d:False)
    out=tmp_path/'rejected'
    W._export(design,out)
    assert not (out/'receiver').exists()
    assert 'generated_receiver' not in design
    assert not (out/'receiver_programmable').exists()
    assert 'programmable_receiver_option' not in design
