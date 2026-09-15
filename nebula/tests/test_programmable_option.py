import json
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2]
RUN=ROOT/'nebula/product_demo/submission_runs_20260915_v2/4608cf1c525f4e59b2d5226059b0ce5d'

def test_reviewed_option_has_own_identity_and_no_signoff():
    from nebula import programmable_option as P
    data=P.for_parent(RUN)
    assert data['signal_gate_pass'] and data['nominal_ac_match']
    assert not data['nominal_receiver_verified'] and not data['full_receiver_verified']
    assert data['charged_calls']==8 and data['correct_bits']==64
    assert data['r_fraction']==.73 and data['c_fraction']==.21
    assert len(data['model_violations'])>=6

def test_mismatched_parent_never_inherits_option(tmp_path):
    from nebula import programmable_option as P
    (tmp_path/'design.cir').write_text('unrelated')
    assert P.for_parent(tmp_path) is None

@pytest.mark.parametrize('key',['../summary.json','C:/Windows/test','device/unknown','unrecorded'])
def test_artifact_allowlist(key):
    from nebula import programmable_option as P
    with pytest.raises(ValueError):P.artifact(key)

def test_export_option_is_exact_measured_deck_and_not_parent_mutation(tmp_path):
    from nebula import programmable_option as P
    design=json.loads((RUN/'design.json').read_text());raw=(RUN/'design.cir').read_bytes()
    metadata,files=P.export_option(design,raw,tmp_path/'variant')
    assert metadata['status']=='EXPERIMENTAL_NOMINAL_AC_AND_SIGNAL'
    assert not metadata['full_receiver_verified'] and not metadata['inherits_parent_verification']
    assert (tmp_path/'variant/receiver.cir').read_bytes()==P.artifact('deck').read_bytes()
    assert len(files)==3 and (RUN/'design.cir').read_bytes()==raw
    with pytest.raises(FileExistsError):P.export_option(design,raw,tmp_path/'variant')

def test_other_requests_do_not_inherit_calibrated_option():
    from nebula import programmable_option as P
    design=json.loads((RUN/'design.json').read_text());raw=(RUN/'design.cir').read_bytes()
    assert P.eligible(design,raw)
    design['request']['peaking_db']=9.
    assert not P.eligible(design,raw)
    design['request']['peaking_db']=6.;design['request']['f_peak_hz']=2.5e9
    assert not P.eligible(design,raw)


def test_bad_source_and_failed_design_cannot_export(tmp_path):
    from nebula import programmable_option as P
    design=json.loads((RUN/'design.json').read_text());raw=(RUN/'design.cir').read_bytes()
    with pytest.raises(ValueError):P.export_option(design,raw+b'changed',tmp_path/'bad')
    design['verification']['n_pass']=0
    with pytest.raises(ValueError):P.export_option(design,raw,tmp_path/'failed')
