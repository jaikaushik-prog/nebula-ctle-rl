"""Gates for `exp_bc` (the generator) and `exp_bc_propose` (its accept rate).

**NO SPICE.** `exp_bc` never simulates at all; `exp_bc_propose`'s only
expensive call is `exp_hybrid.scan_topk`, which is patched with something that
RAISES (G122 -- a counter still lets the real call through if the wrong name
was patched, and the real call is a 320-deck sweep).

The properties worth protecting, in order of what they would cost:

1. **The control must stay a control.** `exp_bc` measured the MLP returning one
   design for every k. If a kind mismatch ever loaded the mixture's weights
   into it, the control would silently become a copy of the arm it exists to
   contradict, and the architecture comparison would be vacuous.
2. **Frequency must enter in octaves.** S3's window is one octave wide and
   every tolerance in this project is stated in octaves; a linear-in-Hz feature
   makes the bottom of the window gratuitously harder to hit than the top.
3. **The mixture must be supported on the open unit box.** A Gaussian on `u`
   directly puts mass outside it, and the clipping piles designs onto the faces.
4. **`fibre_distance` must be able to tell a collapse from a fit** -- it is the
   only free instrument that separates them (G125: the gate's data must
   distinguish the correct rule from the broken one).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

import nebula.experiments.exp_bc as B
import nebula.experiments.exp_bc_propose as P


# ---------------------------------------------------------------------------
# the conditioning vector
# ---------------------------------------------------------------------------

def test_the_spec_box_is_imported_not_restated():
    """Rule 9: `exp_harvest` owns the box; a second copy would drift."""
    from nebula.experiments import exp_harvest as H

    assert (B.PEAKING_LO_DB, B.PEAKING_HI_DB) == (H.PEAKING_LO_DB,
                                                  H.PEAKING_HI_DB)
    assert (B.F_PEAK_LO_HZ, B.F_PEAK_HI_HZ) == (H.F_PEAK_LO_HZ, H.F_PEAK_HI_HZ)
    src = Path(B.__file__).read_text(encoding="utf-8")
    assert "from nebula.experiments.exp_harvest import" in src


def test_the_spec_features_span_minus_one_to_one_at_the_box_corners():
    lo = B.spec_features(B.PEAKING_LO_DB, B.F_PEAK_LO_HZ)
    hi = B.spec_features(B.PEAKING_HI_DB, B.F_PEAK_HI_HZ)
    assert lo == pytest.approx([-1.0, -1.0])
    assert hi == pytest.approx([1.0, 1.0])


def test_FREQUENCY_ENTERS_IN_OCTAVES_NOT_HERTZ():
    """The geometric midpoint of the window must map to 0, not the arithmetic
    one. S3's window is one octave; a linear-in-Hz feature would put the
    midpoint at 1.875 GHz and make the lower half harder to hit for no
    physical reason."""
    geo = math.sqrt(B.F_PEAK_LO_HZ * B.F_PEAK_HI_HZ)          # 1.7678 GHz
    arith = 0.5 * (B.F_PEAK_LO_HZ + B.F_PEAK_HI_HZ)           # 1.8750 GHz
    assert B.spec_features(7.5, geo)[1] == pytest.approx(0.0, abs=1e-12)
    assert abs(B.spec_features(7.5, arith)[1]) > 0.05


def test_spec_features_is_vectorised_and_agrees_with_the_scalar_path():
    pk = np.array([3.0, 7.5, 12.0])
    f = np.array([1.25e9, 1.7678e9, 2.5e9])
    v = B.spec_features(pk, f)
    assert v.shape == (3, 2)
    for i in range(3):
        assert v[i] == pytest.approx(B.spec_features(pk[i], f[i]))


# ---------------------------------------------------------------------------
# the data contract
# ---------------------------------------------------------------------------

def test_load_demonstrations_RAISES_on_a_design_outside_the_box(tmp_path):
    """Standing rule 1 territory: a `u` outside [0,1] means the harvest or the
    contract moved, and training on it would silently learn to leave the box."""
    p = tmp_path / "d.npz"
    np.savez(p, u=np.array([[1.5] * 7]), peaking_db=np.array([7.0]),
             f_peak_hz=np.array([1.8e9]), gated=np.array([True]))
    with pytest.raises(ValueError, match="outside the unit box"):
        B.load_demonstrations(p)


def test_load_demonstrations_RAISES_on_the_wrong_dimension(tmp_path):
    p = tmp_path / "d.npz"
    np.savez(p, u=np.array([[0.5] * 5]), peaking_db=np.array([7.0]),
             f_peak_hz=np.array([1.8e9]), gated=np.array([True]))
    with pytest.raises(ValueError, match="not 7|7"):
        B.load_demonstrations(p)


def test_the_split_is_disjoint_and_reproducible():
    tr, va = B.split(1000, seed=1)
    tr2, va2 = B.split(1000, seed=1)
    assert set(tr).isdisjoint(va)
    assert len(tr) + len(va) == 1000
    assert np.array_equal(tr, tr2) and np.array_equal(va, va2)
    assert not np.array_equal(B.split(1000, seed=2)[0], tr)


# ---------------------------------------------------------------------------
# the models
# ---------------------------------------------------------------------------

def test_the_regressor_returns_ONE_design_k_times():
    """**The control's defining property, pinned.** If this ever stops being
    true the control has become a second generator and the comparison in
    step 4 means nothing."""
    import torch

    m = B._build("mlp")
    x = torch.zeros(1, 2)
    s = m.sample(x, k=8).numpy()[0]
    assert s.shape == (8, B.N_ACTIONS)
    assert len({tuple(np.round(r, 12)) for r in s}) == 1


def test_the_mixture_returns_k_DIFFERENT_designs():
    import torch

    m = B._build("mdn")
    s = m.sample(torch.zeros(1, 2), k=5).numpy()[0]
    assert s.shape == (5, B.N_ACTIONS)
    assert len({tuple(np.round(r, 9)) for r in s}) == 5


def test_both_models_output_inside_the_unit_box():
    """The mixture is fitted in LOGIT space precisely so its support is the
    open unit box; a Gaussian on `u` would put mass outside and the clip would
    pile designs onto the faces."""
    import torch

    x = torch.randn(64, 2) * 3.0            # far outside the training range
    for kind in ("mlp", "mdn"):
        s = B._build(kind).sample(x, k=4).numpy()
        assert np.all(s > 0.0) and np.all(s < 1.0), kind


def test_the_mixture_takes_its_components_heaviest_first():
    """`k < K` must return the k most probable modes, not an arbitrary k."""
    import torch

    m = B._build("mdn")
    x = torch.zeros(1, 2)
    top1 = m.sample(x, k=1).numpy()[0][0]
    top5 = m.sample(x, k=5).numpy()[0]
    assert np.allclose(top1, top5[0])


def test_the_mixture_loss_is_finite_at_the_box_edges():
    """`u` exactly 0 or 1 is a logit singularity; the clamp must hold."""
    import torch

    m = B._build("mdn")
    u = torch.tensor([[0.0] * 7, [1.0] * 7], dtype=torch.float32)
    v = float(m.loss(torch.zeros(2, 2), u))
    assert math.isfinite(v)


def test_the_hidden_shape_matches_SACs_so_step_5_can_fine_tune_it():
    from nebula.rl.sac import SACConfig

    assert tuple(B.HIDDEN) == tuple(SACConfig(seed=0).hidden)


def test_the_component_count_matches_the_topk_the_harness_scores():
    from nebula.experiments.exp_hybrid import DEFAULT_TOPK

    assert B.N_COMPONENTS == DEFAULT_TOPK


# ---------------------------------------------------------------------------
# fibre_distance -- the instrument that separates collapse from fit
# ---------------------------------------------------------------------------

class _Fake:
    """Returns a fixed design, so the metric's own behaviour is testable."""

    def __init__(self, u):
        self.u = np.asarray(u, dtype=float)

    def sample(self, x, k=1, generator=None):
        import torch

        n = x.shape[0]
        return torch.as_tensor(
            np.tile(self.u, (n, k, 1)), dtype=torch.float32)


def _two_mode_fibre(n=200):
    """One spec, two well-separated modes. The centroid lies between them and
    is on NEITHER -- which is the situation the metric must detect."""
    rng = np.random.default_rng(0)
    a = np.full(7, 0.2) + rng.normal(0, 0.01, (n // 2, 7))
    b = np.full(7, 0.8) + rng.normal(0, 0.01, (n // 2, 7))
    u = np.clip(np.vstack([a, b]), 0.0, 1.0)
    x = np.zeros((len(u), 2))
    return x, u


def test_fibre_distance_SCORES_A_MODE_AS_CLOSE():
    x, u = _two_mode_fibre()
    d = B.fibre_distance(_Fake(np.full(7, 0.2)), x, u, np.arange(len(u)),
                         n_probe=20)
    assert d["median_nearest"] < 0.1
    assert d["ratio"] < 0.2


def test_fibre_distance_SCORES_THE_CENTROID_AS_FAR():
    """**The gate's data must separate the rules (G125).** A mean-collapsed
    model sits at 0.5 -- perfect on average, on no mode -- and the metric must
    say so."""
    x, u = _two_mode_fibre()
    d = B.fibre_distance(_Fake(np.full(7, 0.5)), x, u, np.arange(len(u)),
                         n_probe=20)
    assert d["median_nearest"] > 0.7
    assert d["ratio"] > 0.8


def test_fibre_distance_reports_nothing_rather_than_a_number_when_starved():
    x = np.zeros((3, 2))
    u = np.full((3, 7), 0.5)
    assert B.fibre_distance(_Fake(np.full(7, 0.5)), x, u,
                            np.arange(3), n_probe=3)["n"] == 0


def test_fibre_distance_takes_the_BEST_of_k():
    """k candidates are k chances; scoring the first would understate a
    mixture and flatter the deterministic control."""
    x, u = _two_mode_fibre()

    class _TwoShot:
        def sample(self, xx, k=1, generator=None):
            import torch
            picks = [np.full(7, 0.5), np.full(7, 0.2)][:max(k, 1)]
            while len(picks) < k:
                picks.append(np.full(7, 0.5))
            return torch.as_tensor(np.tile(np.array(picks), (xx.shape[0], 1, 1)),
                                   dtype=torch.float32)

    d1 = B.fibre_distance(_TwoShot(), x, u, np.arange(len(u)), n_probe=20, k=1)
    d2 = B.fibre_distance(_TwoShot(), x, u, np.arange(len(u)), n_probe=20, k=2)
    assert d2["median_nearest"] < d1["median_nearest"]


# ---------------------------------------------------------------------------
# step 4's harness
# ---------------------------------------------------------------------------

def test_load_generator_REFUSES_a_kind_mismatch(tmp_path):
    """The control's integrity. Loading the mixture's weights into the
    regressor is how a control silently becomes a copy of the arm it is
    supposed to contradict."""
    import torch

    p = tmp_path / "x.pt"
    torch.save({"kind": "mdn", "n_components": 8,
                "state_dict": B._build("mdn").state_dict()}, p)
    with pytest.raises(ValueError, match="was asked for"):
        P.load_generator(p, kind="mlp")


def test_load_generator_RAISES_on_a_checkpoint_of_nothing(tmp_path):
    import torch

    p = tmp_path / "x.pt"
    torch.save({"kind": "mdn", "state_dict": None}, p)
    with pytest.raises(ValueError, match="checkpoint of nothing"):
        P.load_generator(p, kind="mdn")


def test_load_generator_RAISES_on_a_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError, match="exp_bc"):
        P.load_generator(tmp_path / "nope.pt")


def test_the_source_reports_how_many_of_k_are_DISTINCT():
    """If a deterministic arm reaches the screen it spends 4k decks asking one
    question, and the artifact must say so rather than the accept rate quietly
    absorbing it."""
    src = P.BCSource(_Fake(np.full(7, 0.3)))
    out = src(1.921e9, 10.0, 5)
    assert len(out) == 5
    note = src.notes[(1.921e9, 10.0)]
    assert note["n_proposed"] == 5 and note["n_distinct"] == 1


def test_the_source_clips_into_the_box():
    src = P.BCSource(_Fake(np.array([1.4, -0.3, 0.5, 0.5, 0.5, 0.5, 0.5])))
    u = src(1.8e9, 7.0, 1)[0]
    assert np.all(u >= 0.0) and np.all(u <= 1.0)


def test_the_baseline_quoted_is_entry_32s():
    assert P.BASELINE_A == 6
    assert tuple(P.BASELINE_ACCEPTED_AT_K) == (1, 4, 5, 5, 6)
    assert P.BASELINE_DEPLOYED_DECKS == 260
    assert P.K == 5


def test_the_arms_write_distinct_artifacts_and_never_the_librarys(monkeypatch):
    """G113/G128: identity is the whole filename. An RL arm must not be able to
    overwrite entry 32's committed baseline."""
    src = Path(P.__file__).read_text(encoding="utf-8")
    assert 'f"topk_scan_{name}.json"' in src
    # the library's artifact may be NAMED as provenance for the quoted
    # baseline; what it must never be is a write destination.
    assert 'out=' not in src.replace("out=dest", "")
    assert 'HERE / "hybrid_topk_scan.json"' not in src
    assert P.RESULTS.name == "bc_propose_results.json"
    # every arm's destination is keyed on the arm name, so two arms cannot
    # collide with each other either (G128: identity is the whole filename)
    assert 'dest = HERE / f"topk_scan_{name}.json"' in src


def test_run_cannot_reach_the_expensive_sweep_without_the_lock(monkeypatch):
    """G129: the guard must be checkable without paying for the sweep."""
    whole = Path(P.__file__).read_text(encoding="utf-8")
    body = whole[whole.index("def run(k: int = K"):]
    body = body[:body.index("def _report(")]
    i = body.index('with hold("bc_propose"')
    assert body.index("H.scan_topk(") > i
    assert body.index("RESULTS.write_text") > i


def test_scan_topk_is_never_called_by_the_summary_helper(monkeypatch):
    """G122: patch the expensive path with a raiser and confirm the pure
    helpers do not touch it."""
    from nebula.experiments import exp_hybrid as H

    def _boom(*a, **kw):
        raise AssertionError("scan_topk must not be called here")

    monkeypatch.setattr(H, "scan_topk", _boom)
    scan = {"requests": [{"accepted_rank": 2, "candidates": [
                {"feasible": True, "n_scorable": 4},
                {"feasible": False, "n_scorable": 2,
                 "reason": "output swing 900 mVpp exceeds"}]}],
            "accepted_at_k": [0, 1], "n_accepted": 1, "n_cand_feasible": 1,
            "n_cand_infeasible": 1, "n_cand_unscorable": 0,
            "total_sims_measured": 8, "total_sims_deployed": 8,
            "wall_clock_s": 1.0}
    s = P.arm_summary("bc_mdn", scan, {(1.0, 2.0): {"n_distinct": 5,
                                                    "n_proposed": 5}})
    assert s["n_accepted"] == 1
    assert s["swing_named"] == 1 and s["non_feasible"] == 1
    assert s["mean_scorable_corners"] == pytest.approx(3.0)
    assert s["median_distinct_of_k"] == 5.0


# ---------------------------------------------------------------------------
# the real artifacts
# ---------------------------------------------------------------------------

def test_the_trained_generator_beats_its_control_on_the_fibre_metric():
    """The measured claim step 3 exists to make. If a retrain ever inverts
    this, the architecture decision has to be revisited, not assumed."""
    if not B.RESULTS.exists():
        pytest.skip("exp_bc has not been run in this checkout")
    d = json.loads(B.RESULTS.read_text(encoding="utf-8"))
    arms = {a["arm"]: a for a in d["arms"]}
    assert arms["mdn"]["fibre_k1"]["median_nearest"] < \
        arms["mlp"]["fibre_k1"]["median_nearest"]
    assert arms["mdn"]["fibre_k5"]["median_nearest"] < \
        arms["mlp"]["fibre_k5"]["median_nearest"]
    # the control's k=1 and k=5 are the same design
    assert arms["mlp"]["fibre_k1"]["median_nearest"] == \
        pytest.approx(arms["mlp"]["fibre_k5"]["median_nearest"])


def test_both_checkpoints_exist_and_declare_their_kind():
    if not (B.CKPT.exists() and B.CKPT_MLP.exists()):
        pytest.skip("exp_bc has not been run in this checkout")
    import torch

    for path, kind in ((B.CKPT, "mdn"), (B.CKPT_MLP, "mlp")):
        ck = torch.load(path, map_location="cpu", weights_only=False)
        assert ck["kind"] == kind
        assert ck["state_dict"]
        assert ck["n_demonstrations"] > 30_000
