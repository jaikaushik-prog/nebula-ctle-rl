"""The fixed-candidate validation must not quietly become an adaptive run."""
import pytest
from nebula.experiments import exp_fixed_candidate as C


class Table:
    settings = [425, 490]
    corners = ["tt", "ss"]
    losses = [3., 12.]

    def compliant_settings(self, corner, loss, pk, hz):
        return (425, 490) if corner == "tt" else (490,)


def test_candidate_must_be_the_all_condition_intersection():
    assert C.fixed_candidates(Table(), (9., 1.9e9)) == [490]


def test_a_single_missing_condition_eliminates_candidate():
    table = Table()
    table.compliant_settings = lambda corner, loss, pk, hz: () if loss == 12. else (490,)
    assert C.fixed_candidates(table, (9., 1.9e9)) == []


def test_overwrite_is_refused_before_loading_or_simulation(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "candidate_design", lambda: pytest.fail("must not load"))
    with pytest.raises(FileExistsError):
        C.run(tmp_path)
