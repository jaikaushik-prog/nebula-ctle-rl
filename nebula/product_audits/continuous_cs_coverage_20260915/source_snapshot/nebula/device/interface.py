"""
device/interface.py — the contract the ngspice wrapper must satisfy.

    def evaluate(params: dict[str, float], corner: Corner) -> DeviceResult
                                                        — CLAUDEwa.md §5.1

The real implementation writes a netlist, runs `.op .ac .disto .noise` under
one PVT corner, fits (g_dc, f_zero, f_pole1, f_pole2) to the AC sweep, and
packs the result. It is not in this file: this file freezes the shape so that
the RL and link layers can be built against `nebula.device.mock` today and
swapped onto the real one when it lands.

The single rule this boundary exists to enforce (CLAUDEwa.md §8 rule 2):

    A failed SPICE run returns ok=False, never raises.

Non-convergence is *normal* at the edges of a sizing space. If it reaches the
RL loop as an exception, training dies overnight and you lose a day. Wrap
every implementation in `safe_evaluate` and the loop keeps running with a bad
reward, which is the correct signal.
"""

from __future__ import annotations

import traceback
from typing import Callable, Mapping, Protocol, runtime_checkable

from nebula.common.types import Corner, DeviceResult, FIT_RESIDUAL_REJECT_DB


@runtime_checkable
class DeviceEvaluator(Protocol):
    """Anything that can turn (params, corner) into a DeviceResult."""

    def evaluate(self, params: Mapping[str, float], corner: Corner) -> DeviceResult:
        ...


EvaluateFn = Callable[[Mapping[str, float], Corner], DeviceResult]


def safe_evaluate(
    fn: EvaluateFn,
    params: Mapping[str, float],
    corner: Corner,
    *,
    include_traceback: bool = True,
) -> DeviceResult:
    """Call `fn` and convert any escaping exception into `ok=False`.

    Use this at the RL-loop boundary, not inside the wrapper. The wrapper
    should still report its own failures with specific reasons ("ngspice
    exit 1: singular matrix at node vout") — this is the backstop for the ones
    nobody predicted, so that an unhandled `IndexError` in the fit code costs
    one bad reward instead of one training run.
    """
    try:
        result = fn(params, corner)
    except BaseException as exc:  # noqa: BLE001 — that is the entire point
        detail = traceback.format_exc(limit=6) if include_traceback else ""
        return DeviceResult.failed(
            f"uncaught {type(exc).__name__} in device.evaluate at {corner}: "
            f"{exc}\n{detail}".strip()
        )

    if not isinstance(result, DeviceResult):
        return DeviceResult.failed(
            f"device.evaluate returned {type(result).__name__}, expected DeviceResult"
        )
    return result


def reject_bad_fit(
    result: DeviceResult,
    max_residual_db: float = FIT_RESIDUAL_REJECT_DB,
) -> DeviceResult:
    """Turn a poor pole-zero fit into a failure (CLAUDEwa.md §5.3b).

    A 1-zero/2-pole model that does not actually describe the simulated AC
    response produces four numbers that the link layer will happily believe.
    Rejecting is cheap; a plausible wrong eye contour in the September results
    table is not.
    """
    if not result.ok:
        return result
    assert result.fit_residual_db is not None
    if result.fit_residual_db > max_residual_db:
        return DeviceResult.failed(
            f"pole-zero fit residual {result.fit_residual_db:.3f} dB exceeds "
            f"{max_residual_db} dB — the 1z/2p model does not describe this "
            f"response, so its poles are meaningless"
        )
    return result
