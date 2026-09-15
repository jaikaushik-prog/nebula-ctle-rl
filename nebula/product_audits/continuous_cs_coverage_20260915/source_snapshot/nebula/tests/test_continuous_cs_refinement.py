"""Continuous Cs pilot contracts; no SPICE in these tests."""
import inspect
import json
from pathlib import Path

import numpy as np
import pytest

from nebula.device import continuous_cs_refinement as C
from nebula.experiments import exp_continuous_cs_refinement as E
from nebula import physical_design as D
from nebula.rl.contract import ACTION_NAMES, sizing_from_u


def test_exact_registration_and_only_cs_changes():
    assert C.FACTORS == (1.01, 1.02, 1.03)
    base = C.load_base()['search']
    old = sizing_from_u(base['u']).params
    for factor in C.FACTORS:
        candidate = C.make_candidate(factor)
        assert candidate['bank_setting'] is None and candidate['bank_code'] is None
        assert candidate['base_setting'] == 480 and candidate['atten_code'] == 7
        assert isinstance(candidate['setting'], str) and candidate['setting'].startswith('base480_cs')
        new = sizing_from_u(candidate['u']).params
        assert new['cs'] == pytest.approx(old['cs']*factor, rel=1e-14)
        assert {k:v for k,v in new.items() if k!='cs'} == {k:v for k,v in old.items() if k!='cs'}
        assert np.where(np.asarray(candidate['u']) != np.asarray(base['u']))[0].tolist() == [ACTION_NAMES.index('cs')]
        assert 'fixed_eligible_settings' not in candidate


@pytest.mark.parametrize('factor', (1., 1.005, 1.04, float('nan')))
def test_unregistered_factor_refused(factor):
    with pytest.raises(ValueError): C.make_candidate(factor)


def test_physical_measurement_and_acceptance_definitions_reused():
    original = inspect.getsource(D.run)
    current = inspect.getsource(C.run_candidate)
    start = "            source, params = capture_candidate"
    stop = "            record_calls('completed'"
    assert original[original.index(start):original.index(stop)] == current[current.index(start):current.index(stop)]
    assert C.is_verified is D.is_verified
    assert C.capture_candidate is D.capture_candidate
    assert C.verification_records is D.verification_records


def test_scheduler_keeps_all_three_after_success_and_failure():
    seen=[]
    def evaluate(factor):
        seen.append(factor)
        return {'accepted': factor!=1.02, 'charged_invocations':137}
    r=E.run_set(evaluate)
    assert seen == list(C.FACTORS) and r['registered_candidates_completed']
    assert r['charged_invocations'] == 411
    assert r['accepted_candidates'] == 2


def test_scheduler_preserves_partial_and_budget_stop():
    seen=[]
    def evaluate(factor):
        seen.append(factor)
        return {'accepted':False,'charged_invocations':17,'budget_stop':factor==1.02}
    r=E.run_set(evaluate)
    assert seen == [1.01,1.02] and not r['registered_candidates_completed']
    assert r['charged_invocations'] == 34 and r['stop_reason'] == 'wall_budget'


def test_full_timeout_reserved_without_charging():
    assert C.call_fits(780.,900.,'legacy_candidate')
    assert not C.call_fits(780.001,900.,'legacy_candidate')
    assert C.call_fits(840.,900.,'ff_1.05_0/ac_noise')
    assert not C.call_fits(840.001,900.,'calibration')


def test_existing_campaign_is_refused(tmp_path):
    with pytest.raises(FileExistsError): E.run(tmp_path)
