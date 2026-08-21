"""**Seed the search on BOTH things the user asked for.**

Session 23. The corrected coverage run split cleanly by requested boost —
low boost 6 of 8, **high boost 0 of 5** — and every high-boost failure missed
in the *same direction on both axes*:

    asked 8.0 dB @ 1.63 GHz  ->  delivered 5.20 dB @ 2.50 GHz
    asked 8.0 dB @ 2.25 GHz  ->  delivered 6.33 dB @ 3.37 GHz

Boost low, frequency high, every time. A consistent signed error on both axes
is a starting-point problem, and `choose_start` ranked candidates by
**frequency alone** — so an 8 dB request could start from a 5 dB design near
the right frequency and then had to climb 3 dB, which drags the peak up because
peaking and peak frequency are multiplicatively coupled through the same `Rs`.

It was never an impossibility: over 60 000 analytic designs the fraction
landing inside S3's window is **flat across boost bands** (20.4 % at 3-5 dB,
22.5 % at 11-13 dB), and the library holds 13 236 in-window designs at 7-9 dB.
"""

from __future__ import annotations

import inspect
import math

import numpy as np
import pytest

import nebula.rl.reward_v1 as R
from nebula.experiments import exp_coverage as C


def test_the_seed_ranking_uses_BOTH_axes():
    """The defect, pinned. Ranking on frequency alone is what let an 8 dB
    request start from a 5 dB design."""
    src = inspect.getsource(C.choose_start)
    assert "dev_pk" in src, "the seed ranking ignores the requested peaking"
    assert 'R.TOL["S3_peaking_match"]' in src
    assert 'R.TOL["S3_f_peak_match"]' in src


def test_each_axis_is_NORMALISED_by_its_own_tolerance():
    """dB and octaves are not comparable raw. Dividing each by its own
    tolerance is what makes `max()` of the two meaningful — the same maximin
    shape the objective uses, so the seed is chosen by the criterion the search
    is graded on."""
    src = inspect.getsource(C.choose_start)
    assert "dev_f / R.TOL" in src and "dev_pk / R.TOL" in src


def test_the_probe_REPORTS_peaking_so_the_ranking_can_use_it():
    """`probe_spread` always measured peaking — the same two AC decks give it —
    and threw it away, which is why the ranking could only see frequency."""
    from nebula.experiments.adaptive_screen import Spread

    f = {x.name for x in Spread.__dataclass_fields__.values()}
    assert {"peaking_lo_db", "peaking_hi_db"} <= f


@pytest.mark.parametrize("pk,f_hz", [(4.0, 1.387e9), (8.0, 1.627e9),
                                     (10.0, 1.387e9)])
def test_library_candidates_match_the_REQUESTED_BOOST(pk, f_hz):
    """Not just the frequency. `solve_library` ranks on a reward that ignored
    the requested peaking entirely until this session and only breaks near-ties
    on it, which is why it is no longer the only seed source."""
    cands = C.library_candidates(f_hz, pk, k=4)
    if not cands:
        pytest.skip("design pool unavailable")
    from nebula.experiments import prescreen as P
    from nebula.rl.contract import sizing_from_u

    got = []
    for u in cands:
        try:
            got.append(P.predict_response(sizing_from_u(u).params).peaking_db)
        except Exception:                                       # noqa: BLE001
            pass
    assert got, "no candidate could be described at all"
    assert min(abs(g - pk) for g in got) < 2.0, (
        f"best library seed is {min(got, key=lambda g: abs(g - pk)):.2f} dB "
        f"against a {pk} dB request")


def test_the_analytic_scan_costs_ZERO_SIMULATIONS():
    """It chooses where to look; it never answers anything. Checked by source,
    because a stray import of the device layer is how that would stop being
    true."""
    src = inspect.getsource(C.analytic_candidates)
    for banned in ("run_point", "sky130_runner", "evaluate_at_points",
                   "ngspice", "probe_spread"):
        assert banned not in src, f"the analytic scan references {banned!r}"


def test_every_proposed_seed_is_still_MEASURED_before_it_is_used():
    """The analytic model is off by a full octave at the p99. Its candidates
    are proposals, and `_consider` probes each one with the same 2 decks as
    every other candidate — only the measurement ranks."""
    src = inspect.getsource(C.choose_start)
    i_an = src.index("analytic_candidates(")
    assert "_consider(cand)" in src[i_an:], (
        "analytic candidates must go through _consider, which probes them")
    assert "probe_spread(u)" in src, "seeds are ranked on a MEASUREMENT"


def test_a_missing_pool_degrades_rather_than_raising():
    """A missing artifact is a worse start, not a wrong answer — the search
    must still run from random probes."""
    assert C.library_candidates(1.7e9, 7.5, k=0) == []
    src = inspect.getsource(C.library_candidates)
    assert "return []" in src


def test_the_analytic_scan_is_bounded():
    """It runs per request, so an unbounded scan would make every request
    slower without bound."""
    sig = inspect.signature(C.analytic_candidates)
    assert sig.parameters["n_scan"].default <= 50_000
    assert C.N_ANALYTIC_SEEDS <= 8 and C.N_LIBRARY_SEEDS <= 8
