"""tests for `evaluate_at_points(link_losses_db=...)` — the channel axis.

**The claim being pinned is that one SPICE run yields every channel.** That is
sound only because the CTLE's input drive is channel-INDEPENDENT: the channel
family's insertion loss at DC is exactly 0 by construction
(`CHANNEL_MODEL.md`), so `LinkConfig.v_in_diff_pp_v` is the same at 3 dB and at
12 dB and only the *eye* moves. If that ever stops being true, the whole
"free channel axis" argument collapses, so it is asserted here rather than
assumed in a docstring.

Two gates:

1. **the no-change gate** — a caller that does not ask for the axis must get
   byte-identical results, because `evaluate_at_points` is what
   `design.py --method auto` screens on and this is a load-bearing file;
2. **the consistency gate** — the entry at `FUNNEL_LOSS_DB` must reproduce the
   eye the point was actually scored on. If it did not, the axis would be
   measuring a different link from the one in the reward.

These run real SPICE (two points, ~1 s). They are not marked slow because a
change to this file must not be committable without them.
"""

from __future__ import annotations

import pytest

from nebula.experiments.adaptive_screen import CL_MID_F, ScreenPoint, evaluate_at_points
from nebula.experiments.exp_g2_closed_loop import FUNNEL_LOSS_DB
from nebula.link.channel import FAMILY_IL_DB
from nebula.link.config import LinkConfig
from nebula.common.types import Corner
from nebula.rl import reward_v1 as R

#: A mid-box sizing that is comfortably scorable at TT, so these tests measure
#: the channel plumbing rather than a compression rejection.
U = (0.4747, 0.5052, 0.7147, 0.4931, 0.8133, 0.5871, 0.8020)
TT = Corner(process="tt", vdd_scale=1.0, temp_c=27.0)
PTS = (ScreenPoint(TT, CL_MID_F, "channel-axis test"),)


def test_the_drive_is_channel_independent_which_is_why_this_is_sound():
    """The premise. Loss at DC is 0, so the CTLE sees the same amplitude."""
    lo = LinkConfig(channel_loss_db_at_nyquist=min(FAMILY_IL_DB))
    hi = LinkConfig(channel_loss_db_at_nyquist=max(FAMILY_IL_DB))
    assert lo.v_in_diff_pp_v == pytest.approx(hi.v_in_diff_pp_v)


def test_not_asking_for_the_axis_leaves_the_result_untouched():
    """**The no-change gate.** This function is the delivered screen."""
    ev = evaluate_at_points(U, PTS, specs=R.V6_SPECS)
    assert ev.points and ev.points[0].ok
    assert ev.points[0].links_by_loss is None


def test_asking_for_the_axis_changes_no_scored_number():
    a = evaluate_at_points(U, PTS, specs=R.V6_SPECS)
    b = evaluate_at_points(U, PTS, specs=R.V6_SPECS,
                           link_losses_db=[3.0, FUNNEL_LOSS_DB])
    assert a.reward == pytest.approx(b.reward)
    assert a.feasible == b.feasible
    pa, pb = a.points[0], b.points[0]
    assert pa.margins.keys() == pb.margins.keys()
    for k in pa.margins:
        assert pa.margins[k] == pytest.approx(pb.margins[k]), k
    assert pa.eye_h_v == pytest.approx(pb.eye_h_v)


def test_the_default_loss_entry_reproduces_the_scored_eye():
    """**The consistency gate.** The axis must describe the same link."""
    ev = evaluate_at_points(U, PTS, specs=R.V6_SPECS,
                            link_losses_db=[3.0, FUNNEL_LOSS_DB])
    pr = ev.points[0]
    entry = pr.links_by_loss[float(FUNNEL_LOSS_DB)]
    assert entry["ok"]
    assert entry["eye_h_v"] == pytest.approx(pr.eye_h_v)
    assert entry["eye_w_ui"] == pytest.approx(pr.eye_w_ui)


def test_every_requested_loss_is_present():
    ev = evaluate_at_points(U, PTS, specs=R.V6_SPECS,
                            link_losses_db=FAMILY_IL_DB)
    by = ev.points[0].links_by_loss
    assert set(by) == {float(x) for x in FAMILY_IL_DB}


def test_a_worse_channel_never_gives_a_taller_eye():
    """Monotonicity in the physical direction — more loss, more ISI.

    Not a tautology of the code: the eye comes from a pole-zero fit through the
    channel, and a fit that moved the wrong way would say the channel model is
    wrong, which is worth catching here rather than in a coverage number.

    **The `if ok` filter below is load-bearing and nearly cost this project a
    wrong result** — see `test_scorability_is_CHANNEL_DEPENDENT` for what it hid
    and why the filter alone is not enough.
    """
    ev = evaluate_at_points(U, PTS, specs=R.V6_SPECS,
                            link_losses_db=FAMILY_IL_DB)
    by = ev.points[0].links_by_loss
    heights = [(loss, by[loss]["eye_h_v"]) for loss in sorted(by)
               if by[loss]["ok"]]
    assert len(heights) >= 2
    for (l0, h0), (l1, h1) in zip(heights, heights[1:]):
        assert h1 <= h0 + 1e-12, f"eye grew from {l0} dB to {l1} dB"


def test_scorability_is_CHANNEL_DEPENDENT_and_the_short_channel_is_the_hard_one():
    """**Entry 72's Q4 failure, pinned so the false premise cannot come back.**

    Entry 72 was pre-registered on the claim that *"compression rejections are
    channel-independent, so only the eye moves"*. The argument was that the
    family's loss at DC is exactly 0, so `v_in_diff_pp_v` is the same on every
    channel — which is true, and is asserted above — and the conclusion drawn
    from it was **wrong**.

    `v_in_diff_pp_v` is the drive at DC. The link rejection is on the CTLE's
    **output** swing, and a shorter channel delivers far more HIGH-frequency
    content for the stage to amplify. Measured over the 2 880-point probe:

        loss dB   3.0   4.5   6.0   7.5   9.0  10.5  12.0
        scorable    0    18   128   485  1179  1823  2117   (of 2117)

    At 3.0 dB **every** point is rejected, including the lowest-boost code,
    which over-drives by 1.43x. So scorability is strongly channel-dependent and
    the short channel is the hard one — the opposite of the intuition that less
    loss is easier.

    **The test above did not catch this because it filters on `ok`**, which is
    this repository's own recurring shape: a set built by filtering loses
    members without saying so (G101, G106, G115). This test asserts the
    membership itself.
    """
    ev = evaluate_at_points(U, PTS, specs=R.V6_SPECS,
                            link_losses_db=FAMILY_IL_DB)
    by = ev.points[0].links_by_loss
    ok_losses = {loss for loss, v in by.items() if v["ok"]}
    assert ok_losses, "nothing scorable anywhere — the probe cannot be read"
    assert ok_losses != set(by), (
        "every channel scorable at this sizing: the claim that scorability is "
        "channel-dependent is what entry 72 measured, and this test is the "
        "record of it")
    # The rejected ones are the SHORT channels, not the long ones.
    assert max(by) in ok_losses, "the worst channel should be the easy one here"
    assert min(by) not in ok_losses, "the shortest channel should be rejected"
    for loss in sorted(by):
        if not by[loss]["ok"]:
            assert "output swing" in (by[loss]["reason"] or ""), by[loss]
