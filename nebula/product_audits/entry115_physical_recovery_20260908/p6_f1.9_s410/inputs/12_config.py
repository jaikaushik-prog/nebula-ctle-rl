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
TX swing, the transmitter's mandated de-emphasis and the channel response
rather than being a free constant, so sweeping the loss moves the input
amplitude too — which is what physically happens.

WHAT WAS DELETED HERE, AND WHY IT IS NOT BEING RE-VALUED
---------------------------------------------------------
This file used to carry a hard-coded 1.0 dB "channel loss at DC" constant,
a placeholder with no
measured provenance whose own docstring said a human had to replace it. It
decided every compression verdict this project published
(`BOUNDS_REDERIVATION.md` §2's blockquote). **It is deleted, and the symbol is
gone from every executable file in the tree** — `nebula/tests/test_channel_model.py`
asserts that.

The name encoded the mistake: a lossy transmission line has essentially **zero**
insertion loss at DC. What is non-zero is the loss at Nyquist, and the correct
low-frequency correction is not a channel property at all — it is the
transmitter's **specified -3.5 dB de-emphasis**, which is a fact about PCIe
Gen2 rather than a number someone picked.

So the two properties that used to read the constant now read a model:

    channel_loss_db_at_dc  ->  ChannelModel.il_db_at_dc, which is 0.0 by
                               construction (A*sqrt(0) + B*0)
    v_in_diff_pp_v         ->  the TX long-run level (swing * de-emphasis
                               ratio) attenuated by the channel at DC

See `link/channel.py` for the family and `link/tx.py` for the transmitter.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

from nebula.common.types import BAUD_RATE_HZ, NYQUIST_HZ, SPEC_PEAKING_DB_RANGE
from nebula.link.channel import BALANCED, ChannelModel

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

# ─────────────────────────────────────────────────────────────────────────────
# The PCIe Gen2 transmit de-emphasis anchor.
#
# Gen1 and Gen2 specify TRANSMITTER de-emphasis and nothing else: there is no
# reference receiver equaliser in those generations, and receiver CTLE and DFE
# enter the specification at Gen3. The mandated value is -3.5 dB, with a -6 dB
# option selected during link training for longer channels.
#
# Same provenance caveat as the swing above: the Base Specification is
# paywalled and not in `resources/`, so these are secondary-source figures and
# a human must confirm them before they appear in a deliverable.
#
# They live HERE, next to the swing, because this file is where the PCIe Gen2
# anchors are defined. `link/tx.py` imports them; it does not redeclare them
# (CLAUDEwa.md §8 rule 9).
# ─────────────────────────────────────────────────────────────────────────────

PCIE_GEN2_DE_EMPHASIS_DB: float = -3.5
PCIE_GEN2_DE_EMPHASIS_OPTION_DB: float = -6.0

#: Channel-loss sweep axis, TOTAL loss in dB at 2.5 GHz. Read off S3's tunable
#: peaking range (3-12 dB) on the reasoning that a CTLE is sized to undo
#: roughly the tilt it can boost. Report pass rate as a function of this, do
#: not pick a point.
DEFAULT_LOSS_SWEEP_DB: tuple[float, ...] = (3.0, 5.0, 7.0, 9.0, 12.0)

#: Split ratio `r` used when a `LinkConfig` builds its own channel: the share
#: of the Nyquist loss carried by the sqrt(f) skin term. Balanced by default,
#: which is the middle of the family grid rather than a claim about any
#: particular board — see `channel.FR4_MICROSTRIP.natural_skin_fraction()` for
#: what a stated stackup actually gives, and sweep `channel_skin_fraction` if
#: the answer depends on it.
DEFAULT_SKIN_FRACTION: float = BALANCED


@dataclass(frozen=True)
class LinkConfig:
    """What the link layer needs on top of a `DeviceResult`.

    Attributes
    ----------
    channel_loss_db_at_nyquist
        Channel insertion loss at 2.5 GHz, dB, positive. REQUIRED: this is the
        swept axis, so every config must say which point of the sweep it is.
        It is also the conditioning variable the rest of the project indexes
        on, and it is a first-class attribute of `ChannelModel` for that reason.
    channel_skin_fraction
        The share of that loss carried by the sqrt(f) skin-effect term,
        evaluated at Nyquist. Two channels with the same loss at Nyquist and
        different splits have materially different pulse responses, so this is
        a real axis and not a refinement — see `link/channel.py`.
    tx_de_emphasis_db
        Transmitter de-emphasis, dB, <= 0. Defaults to the PCIe Gen2 mandate of
        -3.5 dB. Gen1/Gen2 specify TX de-emphasis and no receiver equaliser at
        all, so this is part of the link whether or not we model it, and
        leaving it out overstates the CTLE's job by exactly 3.5 dB.
    tx_swing_diff_pp_v
        Transmitter differential peak-to-peak swing on the TRANSITION bit,
        volts. Defaults to the PCIe Gen2 minimum — see the provenance note
        above; it is an assumption pending confirmation against the Base Spec,
        not a verified fact.
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
    channel_skin_fraction: float = DEFAULT_SKIN_FRACTION
    tx_de_emphasis_db: float = PCIE_GEN2_DE_EMPHASIS_DB
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
        # The old "is this a high-pass channel?" guard is gone because the
        # question can no longer be asked: `A*sqrt(f) + B*f` with A, B >= 0 is
        # monotonically increasing in loss by construction, so the channel is
        # low-pass or it does not exist. `ChannelModel.assert_passive()` is the
        # real version of that check, and it gates the magnitude everywhere
        # rather than at two frequencies. The constructor below raises on an
        # out-of-range split fraction, which is the surviving failure mode.
        # Both sub-models validate in their own constructors; touch them here
        # so a bad split fraction or a positive (pre-emphasis) de-emphasis
        # fails where it was configured rather than at first use.
        self.channel
        self.tx
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
    def channel(self) -> ChannelModel:
        """The channel this config describes, as a response rather than a number.

        Built fresh each access from the two stored parameters; `ChannelModel`
        is frozen and stateless, so this is a pure function and two configs
        with equal parameters give bit-identical responses. There is no random
        element anywhere in it, so `seed` never enters — the strongest form of
        the repo's determinism rule.
        """
        return ChannelModel(
            il_db_at_nyquist=self.channel_loss_db_at_nyquist,
            skin_fraction=self.channel_skin_fraction,
            f_nyquist_hz=self.nyquist_hz,
        )

    @property
    def tx(self):
        """The transmitter, as the 2-tap FIR PCIe Gen2 actually specifies.

        Imported lazily: `link/tx.py` imports the PCIe anchors from this
        module, so a module-level import here would be circular.
        """
        from nebula.link.tx import TxDeEmphasis

        return TxDeEmphasis(de_emphasis_db=self.tx_de_emphasis_db,
                            swing_diff_pp_v=self.tx_swing_diff_pp_v,
                            fbaud_hz=self.fbaud_hz)

    @property
    def channel_loss_db_at_dc(self) -> float:
        """The channel's own loss at DC — 0.0, and that is the point.

        This used to be a stored field defaulting to the invented
        the invented 1.0 dB DC-loss placeholder. It is now the MODEL's answer:
        `A*sqrt(0) + B*0 = 0`. A lossy transmission line has essentially no
        insertion loss at DC, which is why the deleted constant's own name
        encoded its mistake.
        """
        return self.channel.il_db_at_dc

    @property
    def channel_tilt_db(self) -> float:
        """Loss the CHANNEL alone presents as a tilt, dB.

        The CTLE's peaking is a RELATIVE quantity — |H(f_nyq)| / |H(0)| — so
        what it equalises is a tilt, not an absolute loss. With the DC loss now
        derived and equal to zero, the channel's tilt equals its Nyquist loss;
        the two properties are kept separate because the transmitter's tilt is
        a third thing, and conflating any two of them is the error this whole
        parameterisation exists to prevent. See `equalisation_burden_db`.
        """
        return self.channel_loss_db_at_nyquist - self.channel_loss_db_at_dc

    @property
    def tx_tilt_db(self) -> float:
        """Tilt the TRANSMITTER supplies at Nyquist, dB, positive.

        Exactly `-tx_de_emphasis_db`: the 2-tap FIR has gain `d` at DC and 1 at
        Nyquist by construction. This is not an approximation.
        """
        return self.tx.tilt_db

    @property
    def equalisation_burden_db(self) -> float:
        """Boost the CTLE actually has to supply at Nyquist, dB.

        `channel tilt - TX tilt`. **This, not the channel loss, is what S3's
        3-12 dB range should be compared against.** May be negative at the
        bottom of the loss family, which is a real answer: the mandated
        de-emphasis already over-equalises a short channel, and a CTLE pinned
        at S3's 3 dB floor is then adding boost the link does not need.
        """
        return self.channel_tilt_db - self.tx_tilt_db

    @property
    def v_in_diff_pp_v(self) -> float:
        """Long-run differential amplitude at the CTLE input, volts.

        The level a run of identical bits settles to: the transmitter's
        DE-EMPHASISED level, attenuated by the channel at DC. It is what sets
        how much output swing the worst low-frequency pattern demands, and
        therefore what the compression check has to survive.

        Both factors changed when the DC-loss placeholder was deleted, and in
        opposite directions: the channel's DC attenuation went from an invented
        1.0 dB to a derived 0 dB (raising this), and the transmitter's
        specified -3.5 dB de-emphasis entered (lowering it by more). Net at the
        defaults: 0.713 V under the placeholder, **0.535 V** now.

        DERIVED, not configured.
        """
        return self.tx.long_run_diff_pp_v * 10.0 ** (
            -self.channel_loss_db_at_dc / 20.0
        )

    @property
    def v_in_nyquist_pp_v(self) -> float:
        """Differential amplitude of the Nyquist content at the CTLE input, V.

        The alternating-bit pattern, attenuated by the full channel loss. The
        transmitter's FIR has unity gain at Nyquist by construction (the
        transition bit is full swing), so de-emphasis does NOT reduce this —
        which is exactly what makes de-emphasis useful rather than merely a
        loss of amplitude.
        """
        return self.tx_swing_diff_pp_v * self.tx.gain_at_nyquist * 10.0 ** (
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
