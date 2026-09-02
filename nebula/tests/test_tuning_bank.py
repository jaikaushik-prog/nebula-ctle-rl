"""tests for `experiments/exp_tuning_bank` — the bank geometry and its artifact.

**Why this file exists.** Section 5z measured the 3x5 bank and committed
`tuning_bank_results.json`. Row 4aa widens the boost axis, and a wider run that
wrote to the same path would **silently overwrite the measurement the report
quotes**. That is this project's recurring shape — a thing that reports success
and exits zero (CLAUDEwa.md §8 rule 10) — so the anti-clobber rule gets a test
that proves it can fail, not a comment.

Nothing here runs SPICE. `bank()` is pure arithmetic over the normalised box and
`results_path()` is a filename decision; both are testable without a simulator,
which is the point of keeping them separate from `run()`.
"""

from __future__ import annotations

import numpy as np
import pytest

from nebula.experiments.exp_tuning_bank import (
    CS_SPAN,
    N_CS_SETTINGS,
    N_RS_SETTINGS,
    RESULTS,
    RS_SPAN,
    I_CS,
    I_RS,
    bank,
    results_path,
)

#: A base sitting mid-box on both tuned axes, so a symmetric span does not clip
#: and monotonicity can be asserted without the clip confounding it.
BASE_MID = [0.5] * 7

#: The real base design's position on the tuned axes (`c507a3ba6f58b9a6`).
#: `u[cs] = 0.8133`, which is why the committed 3x5 run clips at C4 — asserted
#: below rather than left as a surprise.
BASE_REAL = [0.4747, 0.5052, 0.7147, 0.4931, 0.8133, 0.5871, 0.8020]


def test_bank_size_is_the_product_of_its_axes():
    assert len(bank(BASE_MID, n_rs=3, n_cs=5)) == 15
    assert len(bank(BASE_MID, n_rs=8, n_cs=8)) == 64


def test_only_rs_and_cs_move():
    """A bank is a bank, not a second search: every other coordinate is fixed."""
    base = np.asarray(BASE_REAL)
    for st in bank(BASE_REAL, n_rs=8, n_cs=8, rs_span=0.38):
        u = np.asarray(st.u)
        untouched = [i for i in range(len(base)) if i not in (I_RS, I_CS)]
        assert np.allclose(u[untouched], base[untouched]), st.label


def test_settings_are_distinct():
    settings = bank(BASE_MID, n_rs=8, n_cs=8, rs_span=0.38, cs_span=0.20)
    assert len({st.u for st in settings}) == len(settings)


def test_axes_are_monotone_and_separable():
    """`i_rs` moves only `rs`, `i_cs` moves only `cs`, both monotonically.

    This is the property the measured response inherits — section 5z found the
    two axes orthogonal — so it is asserted on the geometry that produces it.
    """
    settings = bank(BASE_MID, n_rs=4, n_cs=6, rs_span=0.3, cs_span=0.2)
    by = {(st.i_rs, st.i_cs): st.u for st in settings}
    for c in range(6):
        col = [by[(r, c)][I_RS] for r in range(4)]
        assert col == sorted(col) and col[0] < col[-1]
        assert len({by[(r, c)][I_CS] for r in range(4)}) == 1
    for r in range(4):
        row = [by[(r, c)][I_CS] for c in range(6)]
        assert row == sorted(row) and row[0] < row[-1]
        assert len({by[(r, c)][I_RS] for c in range(6)}) == 1


def test_spans_are_clipped_into_the_box():
    """A span that leaves the box is clipped, never emitted out of range."""
    for st in bank(BASE_REAL, n_rs=8, n_cs=8, rs_span=0.9, cs_span=0.9):
        assert all(0.0 <= x <= 1.0 for x in st.u), st.label


def test_the_real_base_clips_on_the_cs_axis():
    """`u[cs] = 0.8133`, so +0.20 lands at 1.013 and is clipped to 1.0.

    Recorded as a test because the committed 3x5 artifact's C4 column is
    therefore a slightly shorter step than C0-C3, and a reader comparing the
    measured f_peak steps would otherwise find them uneven for no stated reason.
    """
    top = max(st.u[I_CS] for st in bank(BASE_REAL, n_rs=3, n_cs=5, cs_span=0.20))
    assert top == pytest.approx(1.0)
    assert BASE_REAL[I_CS] + 0.20 > 1.0


def test_single_setting_axis_collapses_to_the_base():
    for st in bank(BASE_REAL, n_rs=1, n_cs=1):
        assert st.u[I_RS] == pytest.approx(BASE_REAL[I_RS])
        assert st.u[I_CS] == pytest.approx(BASE_REAL[I_CS])


# ── the anti-clobber gate ────────────────────────────────────────────────────


def test_default_geometry_keeps_the_committed_artifact_path():
    assert results_path(N_RS_SETTINGS, N_CS_SETTINGS, RS_SPAN, CS_SPAN) == RESULTS


@pytest.mark.parametrize("n_rs,n_cs,rs_span,cs_span", [
    (8, 8, RS_SPAN, CS_SPAN),
    (N_RS_SETTINGS, N_CS_SETTINGS, 0.38, CS_SPAN),
    (N_RS_SETTINGS, N_CS_SETTINGS, RS_SPAN, 0.24),
])
def test_any_other_geometry_writes_somewhere_else(n_rs, n_cs, rs_span, cs_span):
    """**The gate.** Changing ANY of the four geometry knobs must move the file.

    Section 5z's 45-of-45 is quoted in PROGRESS, HANDOFF and the commit message.
    A wide run that overwrote it would leave every one of those citations
    pointing at different numbers, with nothing failing.
    """
    p = results_path(n_rs, n_cs, rs_span, cs_span)
    assert p != RESULTS
    assert p.name.startswith("tuning_bank_") and p.suffix == ".json"


def test_geometry_tag_is_injective():
    """Two different geometries must not collide on one filename."""
    geoms = [(3, 5, 0.12, 0.20), (8, 8, 0.38, 0.20), (8, 8, 0.38, 0.24),
             (5, 8, 0.38, 0.20), (8, 5, 0.38, 0.20), (8, 8, 0.12, 0.20)]
    assert len({results_path(*g) for g in geoms}) == len(geoms)
