"""
link/interface.py — the contract the device->link bridge must satisfy.

    def evaluate_link(dev: DeviceResult, cfg: LinkConfig) -> LinkResult
                                                        — CLAUDEwa.md §5.1

CLAUDEwa.md §5 calls this bridge "the intellectually distinctive part of this
project ... nobody else in this competition will close the loop from
transistor W/L to a BER-1e-15 eye contour." Which is also why it is the part
most worth freezing before three people start building against it.

Same failure discipline as the device layer: a link evaluation that cannot be
completed returns `LinkResult(ok=False, ...)`. A failed `DeviceResult` must
propagate to a failed `LinkResult` and never be silently treated as zeros.
"""

from __future__ import annotations

import traceback
from typing import Callable, Protocol, runtime_checkable

from nebula.common.types import DeviceResult, LinkResult
from nebula.link.config import LinkConfig


@runtime_checkable
class LinkEvaluator(Protocol):
    """Anything that can turn a (DeviceResult, LinkConfig) into a LinkResult."""

    def evaluate_link(self, dev: DeviceResult, cfg: LinkConfig) -> LinkResult:
        ...


EvaluateLinkFn = Callable[[DeviceResult, LinkConfig], LinkResult]


def propagate_device_failure(dev: DeviceResult) -> LinkResult | None:
    """Return a failed LinkResult if `dev` failed, else None.

    Every link implementation calls this first. A failed device evaluation has
    no poles, so there is no CTLE to build and no eye to measure — and
    substituting zeros would hand the RL loop a *finite* reward for a design
    that does not simulate.
    """
    if dev.ok:
        return None
    return LinkResult.failed(f"device evaluation failed: {dev.fail_reason}")


def safe_evaluate_link(
    fn: EvaluateLinkFn,
    dev: DeviceResult,
    cfg: LinkConfig,
    *,
    include_traceback: bool = True,
) -> LinkResult:
    """Call `fn` and convert any escaping exception into `ok=False`."""
    try:
        result = fn(dev, cfg)
    except BaseException as exc:  # noqa: BLE001 — §8 rule 2
        detail = traceback.format_exc(limit=6) if include_traceback else ""
        return LinkResult.failed(
            f"uncaught {type(exc).__name__} in evaluate_link: {exc}\n{detail}".strip()
        )

    if not isinstance(result, LinkResult):
        return LinkResult.failed(
            f"evaluate_link returned {type(result).__name__}, expected LinkResult"
        )
    return result
