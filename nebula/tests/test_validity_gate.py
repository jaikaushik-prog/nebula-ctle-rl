"""Gates for the G44 validity gate in `adaptive_screen.evaluate_at_points`.

**The defect (G130):** `rl/evaluator.validate` is this project's one definition
of "is this measurement trustworthy", and implements G44 -- a response still
RISING at the top of the 20 GHz search returns the range edge from
`meas ac MAX`, so `peaking_db` is fictitious and large. `design.py`,
`baselines.py` and `rl/env.py` have always reached it. **`evaluate_at_points`
never did**, so every accept rate and every compliance number in this project
was produced without it, and a non-CTLE at the sweep edge scored about **-2**
instead of the **-16** invalid floor. Entry 41's SAC policy converged on
exactly that region: **all 52 of its fully-scorable proposals peak at
19.95 GHz.**

Two properties are pinned here and they pull in opposite directions:

* with the gate ON, an INVALID point is UNSCORABLE (G107 -- not "failing");
* with the gate OFF, `validate` is **never called at all**, so every committed
  artifact reproduces bit-for-bit.

Most of this file runs **no SPICE**: `run_point` and `validate` are patched at
the seam. The one test that does is marked `slow` and uses a real `u` from a
committed artifact, because "a design whose peak sits at 19.95 GHz is rejected"
is the actual claim and a mock cannot make it.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

import nebula.experiments.adaptive_screen as S
import nebula.rl.reward_v1 as R
from nebula.rl.evaluator import Verdict

HERE = Path(__file__).resolve().parents[1] / "experiments"


# ---------------------------------------------------------------------------
# the seam, with no simulator
# ---------------------------------------------------------------------------

class _Pt:
    """The minimum `evaluate_at_points` touches before the gate fires."""
    ok = True
    fail_reason = None
    f_pk_hz = 2.0e9
    peaking_db = 8.0
    nyquist_boost_db = 3.0
    vds = 0.30
    vdsat = 0.10
    tail_margin_v = 0.20
    has_interior_peak = True
    g_pk_db = -6.0
    g_top_db = -15.0
    f_pk_interp_hz = 2.0e9


def _patch(monkeypatch, verdict, why="fictitious peak at the sweep edge"):
    """Patch the simulator away and force one `validate` verdict."""
    calls: list = []

    monkeypatch.setattr(S, "evaluate_at_points", S.evaluate_at_points)
    import nebula.device.sky130_runner as RUN
    import nebula.rl.evaluator as EV

    monkeypatch.setattr(RUN, "run_point", lambda *a, **kw: _Pt())

    def _fake_validate(pt, point):
        calls.append((pt, point))
        return verdict, (None if verdict is Verdict.VALID else why)

    monkeypatch.setattr(EV, "validate", _fake_validate)
    return calls


def _one_point():
    return [S.EDGE4_MANDATED[0]]


def test_the_gate_is_OFF_by_default_and_validate_is_never_called(monkeypatch):
    """**The reproducibility guarantee.** Every published accept rate, coverage
    sweep and compliance table was produced without this check, and CMA-ES is
    path-dependent (G121). If the default ever flips, committed runs stop
    reproducing -- so the default is pinned by a test, not by a comment."""
    calls = _patch(monkeypatch, Verdict.INVALID)
    S.evaluate_at_points(np.full(7, 0.5), _one_point(), specs=R.V6_SPECS)
    assert calls == [], "validate was called with the gate off"


def test_an_INVALID_point_becomes_UNSCORABLE_when_the_gate_is_on(monkeypatch):
    """G107: 'cannot be trusted' is not 'fails'. An invalid measurement must
    land in the graded invalid band, not be scored as a bad design."""
    _patch(monkeypatch, Verdict.INVALID)
    ev = S.evaluate_at_points(np.full(7, 0.5), _one_point(), specs=R.V6_SPECS,
                              validity_gate=True)
    assert ev.ok is False and ev.feasible is False
    assert ev.n_scorable == 0
    assert "validity gate" in (ev.reason or "")
    assert ev.reward == pytest.approx(R.invalid_reward(len(R.V6_SPECS)))


def test_the_gate_SHORT_CIRCUITS_before_the_link_bridge(monkeypatch):
    """**The distinguishing gate (G117).** The first sabotage round could not
    tell "unscorable because the gate rejected it" from "unscorable because the
    fake could not be processed downstream" -- both produce `n_scorable == 0`,
    so removing the guard stayed GREEN.

    This separates them: `device_result_from_point` is patched to RAISE. If the
    gate rejects first, nothing downstream runs and the call returns normally.
    If the guard is removed, the raiser fires. A counter would not do -- G122:
    patch the path you must not reach with something that raises."""
    _patch(monkeypatch, Verdict.INVALID)
    import nebula.link.bridge as B

    def _boom(pt):
        raise AssertionError("the gate did not short-circuit: the link bridge "
                             "was reached with an INVALID measurement")

    monkeypatch.setattr(B, "device_result_from_point", _boom)
    ev = S.evaluate_at_points(np.full(7, 0.5), _one_point(), specs=R.V6_SPECS,
                              validity_gate=True)
    assert ev.ok is False and ev.n_scorable == 0


def test_the_gate_names_the_MECHANISM_in_the_reason(monkeypatch):
    """`evaluator.validate`'s own comment: reporting 'f_pk out of range' reads
    as a numerical oddity, while 'the peak is fictitious' is the finding. The
    reason must survive to the caller."""
    _patch(monkeypatch, Verdict.INVALID, why="peak is the sweep edge (G44)")
    ev = S.evaluate_at_points(np.full(7, 0.5), _one_point(), specs=R.V6_SPECS,
                              validity_gate=True)
    assert "sweep edge" in ev.reason and "G44" in ev.reason


def test_a_VALID_point_is_unaffected_by_the_gate(monkeypatch):
    """The gate must not change any design that was already trustworthy --
    that is what makes entry 43's 'zero blast radius' measurement meaningful."""
    calls = _patch(monkeypatch, Verdict.VALID)
    off = S.evaluate_at_points(np.full(7, 0.5), _one_point(), specs=R.V6_SPECS)
    on = S.evaluate_at_points(np.full(7, 0.5), _one_point(), specs=R.V6_SPECS,
                              validity_gate=True)
    assert len(calls) == 1                      # called once, on the gated run
    assert off.ok == on.ok and off.n_scorable == on.n_scorable
    assert off.reward == pytest.approx(on.reward)


def test_HEADROOM_ONLY_does_NOT_reject(monkeypatch):
    """**The one verdict that must pass through.** `HEADROOM_ONLY` means the
    `.op` is trustworthy and the device is out of saturation -- which this
    function already scores through its own `saturation` / `tail_saturation`
    rows. Rejecting it here would count one failure twice and erase the
    gradient over the whole low-peaking region of the box, which is where a
    fresh policy starts (`evaluator.validate`'s own docstring)."""
    _patch(monkeypatch, Verdict.HEADROOM_ONLY, why="out of saturation")
    ev = S.evaluate_at_points(np.full(7, 0.5), _one_point(), specs=R.V6_SPECS,
                              validity_gate=True)
    assert "validity gate" not in (ev.reason or "")


def test_the_gate_is_IMPORTED_and_not_reimplemented():
    """CLAUDEwa.md section 8 rule 9. A second copy of the G44 rule inside the
    screen would be a THIRD definition of validity in a repository that
    already had two -- the exact defect this change repairs."""
    src = Path(S.__file__).read_text(encoding="utf-8")
    assert "validate)" in src or "validate," in src
    assert "from nebula.rl.evaluator import" in src
    assert "peak_is_sweep_edge" not in src, "the rule is restated, not imported"
    assert "g_top_db" not in src
    assert "PEAK_MARGIN_DB" not in src


def test_screen_env_defaults_the_gate_OFF_so_entry_41_reproduces():
    """Entry 41 trained 25 000 steps through this env. If the default flips,
    that run is no longer reproducible and its artifact is unattributable."""
    import inspect

    from nebula.rl.screen_env import ScreenEnv  # noqa: F401

    sig = inspect.signature(ScreenEnv.__init__)
    assert sig.parameters["validity_gate"].default is False
    src = (Path(__file__).resolve().parents[1] / "rl" / "screen_env.py"
           ).read_text(encoding="utf-8")
    assert "validity_gate=self.validity_gate" in src, \
        "ScreenEnv accepts the flag but never forwards it"


def test_screen_env_reports_the_gate_setting():
    """A run whose artifact does not state its own instrument cannot be
    compared with one that does (G108's lesson, applied to a flag)."""
    from nebula.rl.screen_env import ScreenEnv
    from nebula.rl.spec_dist import SpecTarget

    env = ScreenEnv([SpecTarget(peaking_db=8.0, f_peak_hz=1.921e9)], seed=1)
    assert env.report()["validity_gate"] is False
    env2 = ScreenEnv([SpecTarget(peaking_db=8.0, f_peak_hz=1.921e9)], seed=1,
                     validity_gate=True)
    assert env2.report()["validity_gate"] is True


# ---------------------------------------------------------------------------
# the real thing -- one design, 19.95 GHz, 4 decks
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_a_REAL_sweep_edge_design_is_rejected_only_when_the_gate_is_on():
    """**The claim, made against SPICE rather than a mock.**

    `u` is taken from `topk_scan_screen_random.json` -- one of entry 41's
    proposals that the ungated screen scored as a merely-bad design at about
    -2 while reporting a peak at 19.95 GHz. With the gate on it must become
    unscorable; with it off it must still score as before.

    8 decks. Marked `slow` so the default suite stays SPICE-free here.
    """
    scan = json.loads((HERE / "topk_scan_screen_random.json"
                       ).read_text(encoding="utf-8"))
    cand = None
    for r in scan["requests"]:
        for c in r["candidates"]:
            if "error" in c:
                continue
            f = c.get("f_peak_hz_got")
            if f and f > 19.0e9 and c.get("n_scorable") == 4:
                cand, req = c, r
                break
        if cand:
            break
    assert cand is not None, "no fully-scorable sweep-edge candidate on disk"

    kw = dict(target_f_peak_hz=float(req["f_peak_hz"]),
              target_peaking_db=float(req["peaking_db"]), specs=R.V6_SPECS)
    pts = [S.EDGE4_MANDATED[0]]
    off = S.evaluate_at_points(np.asarray(cand["u"]), pts, **kw)
    on = S.evaluate_at_points(np.asarray(cand["u"]), pts, validity_gate=True,
                              **kw)

    assert off.ok is True, "the ungated screen used to score this design"
    assert off.reward > R.invalid_reward(len(R.V6_SPECS)) + 1.0
    assert on.ok is False, "the gate did not reject a 19.95 GHz peak"
    assert on.reward == pytest.approx(R.invalid_reward(len(R.V6_SPECS)))
    assert "validity gate" in (on.reason or "")
