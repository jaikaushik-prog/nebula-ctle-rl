"""
link/config.py — configuration for the link-layer evaluation.

This is the `LinkConfig` named in the §5.1 signature
`evaluate_link(dev: DeviceResult, cfg: LinkConfig) -> LinkResult`.

Relationship to `python_models/link_sim.py::LinkConfig`
------------------------------------------------------
They are different objects on purpose. The one in `link_sim` describes the
full 112G PAM-4 reference receiver (56 GBd, 6-bit ADC, 17-tap FFE, MM CDR)
and is the configuration of the *existing* framework. This one carries only
what the nebula flow needs to turn a `DeviceResult` into an eye. Once the NRZ
retarget lands, `to_link_sim_config()` below builds the `link_sim` object from
this one — lazily, so that importing `nebula.link` does not drag
`python_models` (and therefore the `sys.path` insert in `tests/conftest.py`
and the PAM-4 defaults) into every process that only wants the types.

The two numbers Astera left out of §3, and how we handle them
-------------------------------------------------------------
Neither the input amplitude at the CTLE nor the channel loss appears in the §3
spec table, yet between them they set the entire difficulty of S8. Rather than
pick constants and defend them in September:

**Channel loss is a swept axis, not an assumption.** `channel_loss_db_at_nyquist`
stays a required argument — every config states which point of the sweep it
is — and results are reported as pass rate versus channel loss. S3's 3-12 dB
tunable peaking range is itself the strongest available hint at the intended
loss range at 2.5 GHz: a CTLE is built to undo roughly the loss it can boost.
`DEFAULT_LOSS_SWEEP_DB` follows that reading. This turns an arbitrary constant
into a result, and answers "what channel did you assume?" with a curve.

**Input amplitude is anchored to the PCIe Gen2 transmitter, not invented.**
See `PCIE_GEN2_TX_DIFF_PP_MIN_V` below, including what is and is not verified
about that number. The amplitude at the CTLE input is then *derived* from the
TX swing and the channel loss rather than being a second free constant, so
sweeping the loss moves the input amplitude too — which is what physically
happens.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

from nebula.common.types import BAUD_RATE_HZ, NYQUIST_HZ, SPEC_PEAKING_DB_RANGE

# ─────────────────────────────────────────────────────────────────────────────
# The PCIe Gen2 transmit anchor.
#
# PROVENANCE AND ITS LIMITS — read before citing this in a deliverable.
#
# Value: 0.8 V differential peak-to-peak, the MINIMUM specified transmitter
# swing (V_TX-DIFF-PP) at 5.0 GT/s.
#
# Verified against: Renesas, "Gen2 PCIe Hardware Design Guide" (2007), which
# states the minimum differential voltage swing of the transmitter is 800 mV
# at both 2.5 GT/s and 5.0 GT/s. That is a secondary source.
#
# NOT verified against: the PCI Express Base Specification itself, which is
# paywalled and not in `resources/`. A human must confirm this figure against
# the Base Spec before it appears in the abstract, report or slides
# (CLAUDEwa.md §8 rule 1: every number traceable to something we actually
# checked). Until then it is an assumption, and the report must say so.
#
# Why the MINIMUM rather than a typical or maximum: a receiver equaliser is
# budgeted against the worst transmitter it must interoperate with. Designing
# to the minimum swing is the conservative, defensible choice; designing to a
# typical one would make every eye number optimistic by an unstated margin.
# ─────────────────────────────────────────────────────────────────────────────

PCIE_GEN2_TX_DIFF_PP_MIN_V: float = 0.8

#: Channel-loss sweep axis, TOTAL loss in dB at 2.5 GHz. Read off S3's tunable
#: peaking range (3-12 dB) on the reasoning that a CTLE is sized to undo
#: roughly the tilt it can boost. Report pass rate as a function of this, do
#: not pick a point.
DEFAULT_LOSS_SWEEP_DB: tuple[float, ...] = (3.0, 5.0, 7.0, 9.0, 12.0)

# ─────────────────────────────────────────────────────────────────────────────
# Broadband (DC / low-frequency) channel loss.
#
# WHY THIS FIELD EXISTS. An earlier version of this model carried only the
# loss at Nyquist and compared it directly against the CTLE's *boost*, which
# is a RELATIVE quantity — |H(f_nyq)| / |H(0)|. Comparing an absolute loss to
# a relative tilt is only self-consistent for a channel with exactly 0 dB loss
# at DC, and no real channel has that: conductor resistance, dielectric loss
# and connector/via losses are all broadband.
#
# So the channel is now described by TWO numbers and the CTLE equalises the
# difference:
#
#     tilt_dB = loss_at_nyquist_dB - loss_at_dc_dB      <- what the CTLE undoes
#     amplitude at the CTLE input = TX swing attenuated by loss_at_dc_dB
#
# The default of 1.0 dB is a PLACEHOLDER for a short PCIe Gen2 channel
# (conductor + connector, low frequency). It has no measured provenance and a
# human must replace it — ideally with a real .s4p, which is HANDOFF §8 item 1
# and would make this whole parameterisation unnecessary.
# ─────────────────────────────────────────────────────────────────────────────

CHANNEL_DC_LOSS_DB: float = 1.0


@dataclass(frozen=True)
class LinkConfig:
    """What the link layer needs on top of a `DeviceResult`.

    Attributes
    ----------
    channel_loss_db_at_nyquist
        Channel insertion loss at 2.5 GHz, dB, positive. REQUIRED: this is the
        swept axis, so every config must say which point of the sweep it is.
    tx_swing_diff_pp_v
        Transmitter differential peak-to-peak swing, volts. Defaults to the
        PCIe Gen2 minimum — see the provenance note above; it is an assumption
        pending confirmation against the Base Spec, not a verified fact.
    n_dfe_taps
        Fixed at 1 by S2. Present so the assumption is visible in every log,
        not so it can be tuned.
    fbaud_hz
        5.0e9 from S1.
    target_ber
        BER contour at which eye width is measured. 1e-15 is the depth the
        semi-analytic engine exists to reach (CLAUDEwa.md §12: transient
        simulation cannot).
    rj_ui_rms
        Total random jitter at the sampler, UI rms. Defaults to 0 so that a
        run which never sets it reports an obviously-idealised eye width
        rather than a number smuggled in from the 112G defaults.
    compression_margin
        Fraction of `vout_swing_v` at which the small-signal model is declared
        invalid (calibration convention C4). 1.0 = fail only at hard
        compression. May be tightened, never loosened.
    seed
        Passed through to any stochastic step. Per the repo convention
        (CLAUDE.md / HANDOFF §4) seeds live in the config, never in call sites.
    """

    channel_loss_db_at_nyquist: float
    channel_loss_db_at_dc: float = CHANNEL_DC_LOSS_DB
    tx_swing_diff_pp_v: float = PCIE_GEN2_TX_DIFF_PP_MIN_V
    n_dfe_taps: int = 1
    fbaud_hz: float = BAUD_RATE_HZ
    target_ber: float = 1e-15
    rj_ui_rms: float = 0.0
    compression_margin: float = 1.0
    seed: int = 1

    def __post_init__(self) -> None:
        if (not math.isfinite(self.channel_loss_db_at_nyquist)
                or self.channel_loss_db_at_nyquist < 0.0):
            raise ValueError(
                f"channel_loss_db_at_nyquist is an insertion LOSS and must be "
                f">= 0 dB, got {self.channel_loss_db_at_nyquist!r}"
            )
        if (not math.isfinite(self.channel_loss_db_at_dc)
                or self.channel_loss_db_at_dc < 0.0):
            raise ValueError(
                f"channel_loss_db_at_dc is an insertion LOSS and must be "
                f">= 0 dB, got {self.channel_loss_db_at_dc!r}"
            )
        if self.channel_loss_db_at_nyquist < self.channel_loss_db_at_dc:
            raise ValueError(
                f"channel loss at Nyquist ({self.channel_loss_db_at_nyquist} dB) "
                f"is less than at DC ({self.channel_loss_db_at_dc} dB). That is a "
                f"high-pass channel, which is not a thing — and it would give the "
                f"CTLE a negative tilt to equalise."
            )
        if not math.isfinite(self.tx_swing_diff_pp_v) or self.tx_swing_diff_pp_v <= 0.0:
            raise ValueError(
                f"tx_swing_diff_pp_v must be positive and finite, got "
                f"{self.tx_swing_diff_pp_v!r}"
            )
        if self.n_dfe_taps != 1:
            raise ValueError(
                f"S2 fixes the topology at a 1-tap DFE; got n_dfe_taps="
                f"{self.n_dfe_taps}. Changing the topology is a human decision "
                f"(CLAUDEwa.md §8 rule 5)."
            )
        if not 0.0 < self.target_ber < 1.0:
            raise ValueError(f"target_ber must lie in (0, 1), got {self.target_ber}")
        if self.rj_ui_rms < 0.0:
            raise ValueError(f"rj_ui_rms must be non-negative, got {self.rj_ui_rms}")
        if not 0.0 < self.compression_margin <= 1.0:
            raise ValueError(
                f"compression_margin must lie in (0, 1] — it may only make the "
                f"validity check stricter, never more permissive. Got "
                f"{self.compression_margin}."
            )

    @property
    def nyquist_hz(self) -> float:
        return self.fbaud_hz / 2.0

    @property
    def channel_tilt_db(self) -> float:
        """Loss the CTLE actually has to undo, dB.

        The CTLE's peaking is a RELATIVE quantity — |H(f_nyq)| / |H(0)| — so
        the thing it equalises is the channel's tilt, not its absolute loss.
        Comparing peaking against absolute loss silently assumes a channel
        that is lossless at DC.
        """
        return self.channel_loss_db_at_nyquist - self.channel_loss_db_at_dc

    @property
    def v_in_diff_pp_v(self) -> float:
        """Low-frequency differential amplitude at the CTLE input, volts.

        This is the long-run / DC level — the transmitter swing attenuated by
        the channel's BROADBAND loss. It is what sets how much output swing a
        run of identical bits demands, and therefore what the compression
        check has to survive.

        DERIVED, not configured, so that sweeping the channel moves the input
        amplitude with it — which is what physically happens.
        """
        return self.tx_swing_diff_pp_v * 10.0 ** (
            -self.channel_loss_db_at_dc / 20.0
        )

    @property
    def v_in_nyquist_pp_v(self) -> float:
        """Differential amplitude of the Nyquist content at the CTLE input, V.

        The alternating-bit pattern, attenuated by the full channel loss. This
        is the component the eye opening is built from, and it is smaller than
        `v_in_diff_pp_v` by exactly the tilt.
        """
        return self.tx_swing_diff_pp_v * 10.0 ** (
            -self.channel_loss_db_at_nyquist / 20.0
        )

    def to_link_sim_config(self, **overrides: Any):
        """Build a `python_models.link_sim.LinkConfig` for the real evaluation.

        Imported lazily and left unimplemented until the NRZ retarget lands:
        `link_sim.LinkConfig` has no modulation flag yet, so every field it
        exposes (fbaud 56e9, PAM-4 slicing, 5-tap DFE, 28/56 GHz CTLE poles)
        is a 112G PAM-4 default that would silently apply here. Producing a
        half-retargeted config would be worse than producing none.
        """
        raise NotImplementedError(
            "link_sim.LinkConfig has no NRZ mode yet. The retarget "
            "(CLAUDEwa.md §4.3) must add a modulation flag and audit the PAM-4 "
            "assumptions — see nebula/NRZ_RETARGET_AUDIT.md for the full list — "
            "before this conversion can be trusted."
        )


def sweep_channel_loss(
    losses_db: Sequence[float] = DEFAULT_LOSS_SWEEP_DB,
    **kwargs: Any,
) -> tuple[LinkConfig, ...]:
    """One LinkConfig per point of the channel-loss axis.

    The reporting unit for the link layer is a curve over this sweep, not a
    single number at one assumed loss.
    """
    configs = tuple(LinkConfig(channel_loss_db_at_nyquist=float(x), **kwargs)
                    for x in losses_db)
    if not configs:
        raise ValueError("channel-loss sweep must contain at least one point")
    return configs


def loss_axis(n: int = 10) -> np.ndarray:
    """A finer loss axis over the same S3-derived span, for plotting."""
    lo, hi = SPEC_PEAKING_DB_RANGE
    return np.linspace(lo, hi, int(n))


def nyquist_check() -> float:
    """Guard against the §12 trap: 112G defaults leaking into a 5 Gbps link."""
    assert abs(NYQUIST_HZ - BAUD_RATE_HZ / 2.0) < 1.0
    return NYQUIST_HZ
