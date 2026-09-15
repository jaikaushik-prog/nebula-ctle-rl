"""Saved diagnostics must not turn search reduction into a speed/pass claim."""
import pytest
from nebula import deadline_evidence as E

def test_saved_rl_certificate_recomputes_denominators():
    r=E.rl_certificate()
    assert r['episodes']==12150 and r['identities']==2430 and r['seeds']==5
    assert r['arms']['rl']['charged_calls']==r['arms']['classical']['charged_calls']==1644
    assert r['both_success_pairs']==8 and r['paired_classical_over_rl_median']==pytest.approx(.9394150795)
    assert r['mean_quality_regret']==pytest.approx(.2830982743686488)
    assert not r['speed_advantage_established'] and not r['near_optimality_established']

def test_receiver_gap_is_selected_not_reference():
    r=E.receiver_gap()
    assert r['selected_setting']==352 and r['affected_devices']==6
    assert sum(x['positive_vgs_v']>0 for x in r['devices'])==2
    assert all(x['vds_min_v']<0<x['vds_max_v'] for x in r['devices'])
    assert not r['full_receiver_verified']

def test_missing_or_corrupt_source_is_refused(monkeypatch):
    monkeypatch.setattr(E,'checked_file',lambda *a:(_ for _ in ()).throw(ValueError('hash mismatch')))
    with pytest.raises(ValueError,match='hash'):E.rl_certificate()
