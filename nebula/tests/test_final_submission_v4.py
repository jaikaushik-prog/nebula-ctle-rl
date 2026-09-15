"""Saved-only report and frozen control checks. Never builds or simulates."""
import json
from statistics import mean
import pytest
from nebula.report import final_submission_v4 as R

def test_v4_report_structure_and_exact_evidence():
    from nebula.report.check_final_submission_v4 import check
    assert check()['page_count']==12

def test_saved_rl_comparison_keeps_provenance_separate():
    final=json.loads((R.ROOT/'nebula/experiments/shielded_policy_final_results.json').read_text())
    post=json.loads((R.ROOT/'nebula/product_audits/entry113_attribution_20260907/summary.json').read_text())
    assert post['status']=='POST_REVIEW_EXPOSED_DIAGNOSTIC'
    assert mean(r['mean_quality'] for r in final['controls']['entry89_unshielded'])==pytest.approx(.5481312047188969)
    assert mean(r['quality'] for r in post['results'] if r['arm']=='ppo' and r['budget']==8)==pytest.approx(.7169017256313512)

def test_missing_ngspice_runtime_fails_without_invocation(tmp_path):
    from nebula.submission_preflight import check_runtime
    with pytest.raises(ValueError,match='runtime is unavailable'):check_runtime(tmp_path/'missing.exe')
