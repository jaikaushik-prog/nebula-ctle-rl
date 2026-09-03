"""Simulator-backed output shield for Entry 89.

The policy never receives the verifier verdict.  After its rollout, the shield
selects the largest visible eye among verifier-compliant settings that were
actually measured, including the fixed start.  This supports the simulator
sizing flow; it is not a receiver-only hardware monitor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from nebula.rl.margin_adapt_env import MarginBankTable


@dataclass(frozen=True)
class ShieldSelection:
    setting: int
    compliant: bool
    eye_area: float
    quality: float
    first_visit: int
    n_verifier_calls: int
    intervened: bool
    shield_failure: bool


def select_best_compliant_visited(
        table: MarginBankTable, identity: tuple[str, float, float, float],
        settings_tried: Sequence[int]) -> ShieldSelection:
    """Return the best compliant measured setting, or the fixed start.

    ``settings_tried[0]`` is the fixed comparator setting.  Each occurrence is
    billed as one verifier call; repeated measurements are not free.
    """
    settings = [int(value) for value in settings_tried]
    if not settings:
        raise ValueError("shield needs at least the fixed start measurement")
    corner, loss, peaking, frequency = identity
    compliant = []
    for index, setting in enumerate(settings):
        if table.compliant(setting, corner, loss, peaking, frequency):
            compliant.append((
                float(table.eye_area(setting, corner, loss)),
                -index, -setting, index, setting))
    policy_setting = settings[-1]
    if not compliant:
        start = settings[0]
        return ShieldSelection(
            setting=start, compliant=False,
            eye_area=float(table.eye_area(start, corner, loss)), quality=0.0,
            first_visit=0, n_verifier_calls=len(settings),
            intervened=(start != policy_setting), shield_failure=True)
    _, _, _, first, selected = max(compliant)
    return ShieldSelection(
        setting=selected, compliant=True,
        eye_area=float(table.eye_area(selected, corner, loss)),
        quality=float(table.quality(
            selected, corner, loss, peaking, frequency)),
        first_visit=first, n_verifier_calls=len(settings),
        intervened=(selected != policy_setting), shield_failure=False)


__all__ = ("ShieldSelection", "select_best_compliant_visited")
