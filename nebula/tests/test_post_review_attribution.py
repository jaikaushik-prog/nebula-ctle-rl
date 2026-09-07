import numpy as np
import pytest
from nebula.experiments import exp_post_review_attribution as A

ID = ("tt/1.00/27C", 7.5, 9.0, 1.9e9)


class Table:
    def compliant(self, setting, *args):
        return setting in (0, 1)
    def eye_area(self, setting, *args):
        return {0: 1., 1: 2., 2: 100.}[setting]
    def quality(self, setting, *args):
        return self.eye_area(setting) / 2 if self.compliant(setting) else 0.


def test_prefix_shield_cannot_select_unvisited_or_unsafe():
    row = A.score_trace(Table(), ID, [0, 2, 1], 2)
    assert row["selected"] == 0
    assert row["quality"] == .5
    assert A.score_trace(Table(), ID, [0, 2, 1], 4)["selected"] == 1


def test_repeated_visits_are_billed_and_not_unique():
    row = A.score_trace(Table(), ID, [0, 1, 0, 1], 4)
    assert row["n_visits"] == row["verifier_calls"] == 4
    assert row["n_unique"] == 2


@pytest.mark.parametrize("start", [0, 7, 63, 448, 511])
def test_random_local_moves_are_legal_and_local(start):
    visits = A.random_trace(start, np.random.default_rng(7))
    assert len(visits) == 8 and visits[0] == start
    for one, two in zip(visits, visits[1:]):
        assert 0 <= two < 512
        assert A.B.setting_distance(one, two) == 1


def test_random_stream_is_persistent_and_reproducible():
    rng = np.random.default_rng(123)
    one, two = A.random_trace(300, rng), A.random_trace(300, rng)
    again = np.random.default_rng(123)
    assert one == A.random_trace(300, again)
    assert two == A.random_trace(300, again)
    assert one != two


def test_global_control_counts_start_and_has_no_duplicates():
    visits = A.random_trace(0, np.random.default_rng(8), global_search=True)
    assert visits[0] == 0 and len(visits) == len(set(visits)) == 8


def test_replay_gate_rejects_changed_selection():
    rows = [A.score_trace(Table(), ID, [0, 1], 8)]
    old = [dict(corner=ID[0], loss_db=ID[1], target_peaking_db=ID[2],
                target_f_peak_hz=ID[3], locked_setting=1, compliant=True,
                n_trials=2, quality=1.)]
    A.assert_replay(rows, old)
    old[0]["locked_setting"] = 0
    with pytest.raises(ValueError, match="differs"):
        A.assert_replay(rows, old)


def test_grouped_interval_counts_request_loss_blocks_not_pvt_rows():
    identities = [("tt", 3., 5., 1e9), ("ss", 3., 5., 1e9),
                  ("tt", 6., 5., 1e9), ("ss", 6., 5., 1e9)]
    assert A.grouped_interval(identities, [1, -1, 1, -1]) == [0., 0.]


def test_uncommitted_protocol_is_rejected(monkeypatch, tmp_path):
    path = tmp_path / "plan.md"
    path.write_text("changed")
    monkeypatch.setattr(A, "PLAN", path)
    monkeypatch.setattr(A.subprocess, "check_output", lambda *a, **k: b"frozen")
    with pytest.raises(ValueError, match="committed"):
        A.frozen_plan()


def test_existing_output_is_never_overwritten(monkeypatch, tmp_path):
    monkeypatch.setattr(A, "frozen_plan", lambda: "hash")
    with pytest.raises(FileExistsError):
        A.run(tmp_path)


def test_scoring_rejects_missing_or_over_budget_trajectory():
    for visits in ([], [0] * 9):
        with pytest.raises(ValueError, match="trajectory"):
            A.score_trace(Table(), ID, visits, 8)

