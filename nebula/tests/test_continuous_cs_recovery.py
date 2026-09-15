"""Production dispatch of the validated continuous candidate, without SPICE."""
import json
from copy import deepcopy
import pytest
from nebula import physical_recovery as R
from nebula.device import continuous_cs_refinement as C

TARGET={'peaking_db':6.,'f_peak_hz':2.5e9}

def test_exact_target_only_and_truthful_identity():
    search,provenance=R.continuous_proposal(TARGET)
    assert search['candidate_id']=='base480_cs1p02'
    assert search['base_setting']==480 and search['bank_setting'] is None and search['bank_code'] is None
    assert search['u']==C.make_candidate(1.02)['u']
    assert provenance['prior_pass_is_selection_only']
    assert R.continuous_proposal(dict(TARGET,f_peak_hz=2.5e9-1)) is None
    assert R.continuous_proposal(dict(TARGET,peaking_db=6.0001)) is None

def test_both_modes_prefer_continuous_before_bank(monkeypatch):
    from types import SimpleNamespace
    class Table:
        settings=[480]
        corners=['tt']
        losses=[3.,4.5,6.,7.5,9.,10.5,12.]
        def compliant_settings(self,*args):return [480]
    monkeypatch.setattr(R,'load_bank',lambda:(Table(),[SimpleNamespace(u=[.1]*7)]*64,{}))
    monkeypatch.setattr(R.D,'verified_physical_entry',lambda **kw:None)
    monkeypatch.setattr(R,'rl_proposal',lambda request:{'setting':480,'rl_proposals':1})
    for mode in ('rl','classical'):
        proposals,meta=R.prepare(TARGET,mode)
        assert [s['setting'] for s,_ in proposals]==['base480_cs1p02',480]
        assert meta['candidate_order']==['base480_cs1p02',480]
        assert meta['eligible_settings']==[480]
        assert meta['continuous_candidates']==['base480_cs1p02']

@pytest.mark.parametrize('fresh_pass', [False, True])
def test_fresh_gate_is_required_and_failed_candidate_billed(tmp_path,monkeypatch,fresh_pass):
    proposal=R.continuous_proposal(TARGET)
    monkeypatch.setattr(R,'LOCK_FILE',tmp_path/'lock')
    monkeypatch.setattr(R,'prepare',lambda *a:([proposal],{}))
    monkeypatch.setattr(R.D,'run',lambda *a,**kw:pytest.fail('continuous cannot use bank prepared hook'))
    calls=[]
    def verify(factor,folder,deadline):
        calls.append((factor,deadline))
        folder.mkdir()
        return {'search':deepcopy(proposal[0]),'accepted':fresh_pass,'simulations':{'total':137},
                'verification':{'n_pass':315 if fresh_pass else 314,'n_points':315}}
    monkeypatch.setattr(C,'run_candidate',verify)
    monkeypatch.setattr(R.D,'is_verified',lambda d:d.get('accepted',False))
    result=R.run(TARGET,tmp_path/'run')
    assert len(calls)==1 and calls[0][0]==1.02
    assert result['status']==('accepted' if fresh_pass else 'exhausted') and result['spice_calls']==137
    assert not result['cached_physical_passes_used']
    assert result['attempts'][0]['bank_setting'] is None
    assert result['design']['search']['bank_code'] is None

def test_corrupt_continuous_evidence_is_refused(tmp_path,monkeypatch):
    monkeypatch.setattr(R,'CONTINUOUS_RESULT',tmp_path/'missing.json')
    with pytest.raises((ValueError,FileNotFoundError)):
        R.continuous_proposal(TARGET)
