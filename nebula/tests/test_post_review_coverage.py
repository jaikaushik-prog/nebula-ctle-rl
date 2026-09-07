import pytest
from nebula.experiments import exp_post_review_coverage as C


def test_grid_has_all_twelve_requests_and_a_bounded_budget():
    assert len(C.REQUESTS) == len(set(C.REQUESTS)) == 12
    assert set(C.REQUESTS) == {(p, f) for p in (3, 6, 9, 12) for f in (1.25e9, 1.9e9, 2.5e9)}
    assert C.MAX_CALLS == 1644


@pytest.mark.parametrize('meas, expected', [
    ({}, None),
    ({'peaking_db': 9, 'f_peak_oct': -.5}, True),
    ({'peaking_db': 12.1, 'f_peak_oct': -.5}, False),
    ({'peaking_db': 9, 'f_peak_oct': -1.01}, False),
    ({'peaking_db': 9, 'f_peak_oct': .01}, False),
])
def test_absolute_brief_limits_are_independent_of_request_tolerance(meas, expected):
    assert C.brief_response(meas) is expected


def test_no_bank_candidate_runs_no_spice_and_preserves_each_rejection(monkeypatch, tmp_path):
    monkeypatch.setattr(C, 'frozen_plan', lambda: 'hash')
    class Table:
        losses = (3., 12.)
    monkeypatch.setattr(C.H, '_load_assets', lambda: (Table(),))
    def reject(*args):
        raise RuntimeError('no fixed bank candidate')
    monkeypatch.setattr(C.D, 'select_fixed_setting', reject)
    def forbidden(*args, **kwargs):
        pytest.fail('SPICE must not run for an empty intersection')
    monkeypatch.setattr(C.D, 'run', forbidden)
    result = C.run(tmp_path / 'run')
    assert result['spice_calls'] == 0
    assert result['n_requests'] == 12
    assert all(r['status'] == 'BANK_NO_FIXED' for r in result['requests'])
    assert result['full_product_compliance'] is False
