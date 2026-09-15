"""Failure-first guardrails for the approved two-call nominal diagnostic."""
import copy
import numpy as np
import pytest
from nebula.device import loaded_tuning_bound as B

def test_proposals_are_existing_controls_and_body_unchanged():
    p=B.proposals(); controls=p['controls']
    assert sum(t['found'] for t in p['targets'])==10
    assert controls[0]==controls[-1]==B.BASE
    assert len(set(controls[1:-1]))==len(controls)-2
    for state in (0,1):
        text=B.deck(state,controls)
        assert text.split('.control')[0]==B.body(state)
        assert text.count('\nop\n')==len(controls)
        assert text.count('ac dec 50 1meg 100g')==len(controls)
        assert '\ntran ' not in text and '\nnoise ' not in text
    with pytest.raises(ValueError,match='Unmeasured'):
        B.deck(0,[B.BASE,(.123,.123),B.BASE])

@pytest.mark.parametrize('state',[0,1])
def test_saved_baseline_and_corrupt_primitives(state):
    folder=B.baseline_folder(state)
    op=np.loadtxt(B.original_file(B.LOADED,folder+'/op.txt'))
    ac=np.loadtxt(B.original_file(B.LOADED,folder+'/ac.txt'))
    text=B.body(state); row=B.parse_row(text,state,B.BASE,op,ac)
    assert B.baseline_matches(row,ac,state)
    assert not row['full_receiver_verified']
    assert not row['signed_model_domain_pass']
    with pytest.raises(ValueError,match='clock'):
        B.parse_row(text,1-state,B.BASE,op,ac)
    with pytest.raises(ValueError,match='controls'):
        B.parse_row(text,state,(.71,.185),op,ac)
    bad=op.copy();bad[-1]=0
    with pytest.raises(ValueError,match='power'):
        B.parse_row(text,state,B.BASE,bad,ac)
    bad=op.copy();bad[1]=np.nan
    with pytest.raises(ValueError,match='Malformed'):
        B.parse_row(text,state,B.BASE,bad,ac)
    assert not B.baseline_matches(row,ac*.9,state)

def states():
    row=dict(r_fraction=.7,c_fraction=.185,ac_model_pass=True,boost_db=9.,peak_frequency_hz=1.9e9)
    return [dict(instrument_ok=True,clock_state=s,rows=[dict(row)]) for s in (0,1)]

def test_selection_requires_two_aligned_valid_states():
    s=states()
    assert sum(r['nominal_ac_match'] for r in B.select_targets(s))==1
    assert not any(r['nominal_ac_match'] for r in B.select_targets(s[:1]))
    bad=copy.deepcopy(s);bad[1]['rows'][0]['ac_model_pass']=False
    assert not any(r['nominal_ac_match'] for r in B.select_targets(bad))
    bad=copy.deepcopy(s);bad[1]['rows'][0]['r_fraction']=.71
    with pytest.raises(ValueError,match='alignment'):B.select_targets(bad)
    bad=copy.deepcopy(s);bad[1]['clock_state']=0
    with pytest.raises(ValueError,match='alignment'):B.select_targets(bad)

def test_schedule_stops_after_first_failure():
    from nebula.experiments.exp_loaded_tuning_bound import schedule
    calls=[]
    def fail(state):
        calls.append(state);return dict(instrument_ok=False)
    assert len(schedule(fail))==1 and calls==[0]
    calls=[]
    def good(state):
        calls.append(state);return dict(instrument_ok=True)
    assert len(schedule(good))==2 and calls==[0,1]

def test_runner_retains_timeout_and_never_retries(tmp_path,monkeypatch):
    from nebula.experiments import exp_loaded_tuning_bound as E
    out=tmp_path/'new';monkeypatch.setattr(E,'OUT',out)
    monkeypatch.setattr(E,'remaining_seconds',lambda:1000)
    old={'ngspice_sha256':B.sha(E.ngspice_path())}
    monkeypatch.setattr(E,'prerequisites',lambda:(old,{},dict(controls=[B.BASE,B.BASE],targets=[]),{}))
    monkeypatch.setattr(E,'pdk_hashes',lambda:{})
    calls=[]
    def timeout(deck,folder,timeout_s):
        assert timeout_s==180
        calls.append(folder);folder.mkdir();(folder/'ngspice.log').write_text('partial timeout evidence')
        raise ValueError('timeout; partial log retained')
    monkeypatch.setattr(E.C,'invoke',timeout)
    result=E.run()
    assert len(calls)==1 and result['charged_calls']==1
    assert result['unrun_clock_states']==[1] and not result['instrument_ok']
    assert (out/'state0/ngspice.log').read_text()=='partial timeout evidence'
    assert (out/'evidence_sha256.json').is_file()
    with pytest.raises(ValueError,match='already exists'):E.run()

def test_runner_deadline_refuses_before_output(tmp_path,monkeypatch):
    from nebula.experiments import exp_loaded_tuning_bound as E
    out=tmp_path/'new';monkeypatch.setattr(E,'OUT',out)
    monkeypatch.setattr(E,'remaining_seconds',lambda:200)
    with pytest.raises(ValueError,match='Insufficient'):E.run()
    assert not out.exists()
