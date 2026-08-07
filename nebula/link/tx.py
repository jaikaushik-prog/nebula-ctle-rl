"""
link/tx.py — the PCIe Gen2 transmitter, which is specified and is part of the link.

WHY THIS EXISTS
---------------
Every equalisation number in this project so far has compared a CTLE against a
RAW channel. That is wrong for PCIe Gen2, and wrong in the direction that
overstates the CTLE's job.

**Gen1 and Gen2 specify transmitter de-emphasis and nothing else.** There is no
reference receiver equaliser in those generations — receiver CTLE and DFE enter
the specification at Gen3. What Gen2 mandates is a fixed **-3.5 dB** of
de-emphasis with a **-6 dB** option. So the CTLE is not equalising a channel;
it is equalising a channel plus a partially pre-equalised transmitter, and the
boost it actually has to supply is smaller by exactly the de-emphasis.

THE DEFINITION, STATED, BECAUSE IT IS THE PART PEOPLE GET BACKWARDS
--------------------------------------------------------------------
De-emphasis is the ratio of the DE-EMPHASISED bit level to the TRANSITION bit
level, in dB, and it is negative:

    de_emphasis_db = 20*log10( V_nontransition / V_transition )

The transmitter is a 2-tap FIR with one post-cursor tap,
`y[n] = c0*x[n] + c1*x[n-1]` with `c1 < 0`, normalised so the TRANSITION bit
reaches full swing:

    transition     x[n]=+1, x[n-1]=-1  ->  c0 - c1 = c0 + |c1| = 1
    de-emphasised  x[n]=+1, x[n-1]=+1  ->  c0 + c1 = c0 - |c1| = d

with `d = 10**(de_emphasis_db/20)`. Solving:

    c0 = (1 + d)/2        c1 = -(1 - d)/2

The normalisation matters: PCIe measures `V_TX-DIFF-PP` on the transition bit,
so `c0 + |c1| = 1` is what makes `tx_swing_diff_pp_v` mean what the spec says
it means. Normalising `c0 = 1` instead would quietly launch more than the
specified swing.

THE CONSEQUENCE, WHICH IS EXACT
-------------------------------
The FIR's own frequency response is `|c0 + c1*exp(-j*w*T)|`, so

    at DC       |H_tx(0)|   = c0 + c1 = d
    at Nyquist  |H_tx(f_N)| = c0 - c1 = 1

i.e. the transmitter supplies **exactly `-de_emphasis_db` of tilt at Nyquist**,
by construction and not approximately: 3.5 dB at the mandated setting, 6.0 dB
at the option. The equalisation burden left for the CTLE is therefore

    burden_dB = channel IL at Nyquist  -  de-emphasis magnitude

and that subtraction is the single most consequential thing in this module.

SWING — REFERENCED, NEVER REDECLARED
------------------------------------
`PCIE_GEN2_TX_DIFF_PP_MIN_V` (0.8 Vpp differential minimum) lives in
`link/config.py` with its provenance note and its limits. This module imports
it. CLAUDEwa.md §8 rule 9: exactly one definition, referenced, never
redeclared — earned when two netlists described "the same" reference point with
different model cards (G32).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from nebula.common.types import BAUD_RATE_HZ
from nebula.link.config import (
    PCIE_GEN2_DE_EMPHASIS_DB,
    PCIE_GEN2_DE_EMPHASIS_OPTION_DB,
    PCIE_GEN2_TX_DIFF_PP_MIN_V,
)

#: No de-emphasis. Not a PCIe setting — present as the control that shows how
#: much of the CTLE's job the transmitter is doing.
NO_DE_EMPHASIS_DB: float = 0.0

#: The three settings every table in CHANNEL_MODEL.md reports.
DE_EMPHASIS_SETTINGS_DB: tuple[float, ...] = (
    NO_DE_EMPHASIS_DB, PCIE_GEN2_DE_EMPHASIS_DB, PCIE_GEN2_DE_EMPHASIS_OPTION_DB,
)


@dataclass(frozen=True)
class TxDeEmphasis:
    """A PCIe Gen2 transmitter: 2-tap FIR + a specified differential swing.

    Parameters
    ----------
    de_emphasis_db
        <= 0. `-3.5` is the Gen2 mandate, `-6.0` the option, `0.0` the control.
    swing_diff_pp_v
        Differential peak-to-peak swing on the TRANSITION bit, volts. Defaults
        to the `link/config.py` anchor; do not pass a literal here.
    fbaud_hz
        S1's 5.0 Gbps.
    """

    de_emphasis_db: float = PCIE_GEN2_DE_EMPHASIS_DB
    swing_diff_pp_v: float = PCIE_GEN2_TX_DIFF_PP_MIN_V
    fbaud_hz: float = BAUD_RATE_HZ

    def __post_init__(self) -> None:
        if not math.isfinite(self.de_emphasis_db) or self.de_emphasis_db > 0.0:
            raise ValueError(
                f"de_emphasis_db must be <= 0 — de-emphasis LOWERS the "
                f"non-transition bit. A positive value is pre-emphasis, which "
                f"PCIe Gen2 does not specify. Got {self.de_emphasis_db!r}."
            )
        if not math.isfinite(self.swing_diff_pp_v) or self.swing_diff_pp_v <= 0.0:
            raise ValueError(f"swing_diff_pp_v must be positive, got {self.swing_diff_pp_v!r}")
        if not math.isfinite(self.fbaud_hz) or self.fbaud_hz <= 0.0:
            raise ValueError(f"fbaud_hz must be positive, got {self.fbaud_hz!r}")

    # ---- the taps ----------------------------------------------------------

    @property
    def level_ratio(self) -> float:
        """`d` — de-emphasised level / transition level, linear. 1.0 when off."""
        return 10.0 ** (self.de_emphasis_db / 20.0)

    @property
    def taps(self) -> tuple[float, float]:
        """`(c0, c1)`, normalised so the transition bit reaches full swing."""
        d = self.level_ratio
        return (1.0 + d) / 2.0, -(1.0 - d) / 2.0

    @property
    def c0(self) -> float:
        return self.taps[0]

    @property
    def c1(self) -> float:
        return self.taps[1]

    # ---- what it does to the spectrum --------------------------------------

    @property
    def gain_at_dc(self) -> float:
        """`c0 + c1 = d`. The long-run level: what a run of identical bits reaches."""
        return self.c0 + self.c1

    @property
    def gain_at_nyquist(self) -> float:
        """`c0 - c1 = 1`. Unity by construction — the transition bit is full swing."""
        return self.c0 - self.c1

    @property
    def tilt_db(self) -> float:
        """Nyquist-relative-to-DC tilt the transmitter supplies, dB, positive.

        Exactly `-de_emphasis_db`. This is the number subtracted from the
        channel's insertion loss to get the CTLE's actual burden.
        """
        return 20.0 * math.log10(self.gain_at_nyquist / self.gain_at_dc)

    def response(self, f_hz) -> np.ndarray:
        """Complex `H_tx(f) = c0 + c1*exp(-j*2*pi*f/fbaud)`.

        The FIR alone — the rectangular symbol pulse is applied separately by
        `pulse()`, so this is the tap response and not the launched waveform.
        """
        f = np.asarray(f_hz, dtype=float)
        return self.c0 + self.c1 * np.exp(-2j * np.pi * f / self.fbaud_hz)

    # ---- what it launches --------------------------------------------------

    @property
    def symbol_amplitude_v(self) -> float:
        """Single-ended-equivalent differential amplitude of one symbol, volts.

        A differential peak-to-peak swing of `V` spans `+V/2` to `-V/2`, so the
        `+/-1` NRZ symbol carries `V/2`.
        """
        return self.swing_diff_pp_v / 2.0

    @property
    def long_run_level_v(self) -> float:
        """Differential level a long run of identical bits settles to, volts.

        `symbol_amplitude_v * d`. THIS is what the compression check has to
        survive: a run of identical bits is the largest low-frequency excursion
        the CTLE output ever sees, and de-emphasis makes it SMALLER than the
        transition-bit swing. The deleted DC-loss placeholder stood in for
        this quantity with an invented 1 dB of channel loss; the transmitter's
        own specified de-emphasis is 3.5 dB of it, and it is a fact rather than
        a placeholder.
        """
        return self.symbol_amplitude_v * self.gain_at_dc

    @property
    def long_run_diff_pp_v(self) -> float:
        """The same level as a differential PEAK-TO-PEAK figure, volts.

        `swing_diff_pp_v * d`. Two properties for one quantity because the
        peak/peak-to-peak confusion is how G37 cost this project a factor of
        two on the available swing; the unit is in the name both times.
        """
        return self.swing_diff_pp_v * self.gain_at_dc

    def pulse(self, osr: int) -> np.ndarray:
        """The launched single-symbol pulse, oversampled `osr` per UI, volts.

        A rectangular 1-UI symbol through the 2-tap FIR: `c0` for the first UI,
        `c1` for the second. Length `2*osr`. Amplitude is
        `symbol_amplitude_v`-scaled, so convolving with the channel impulse
        response gives volts directly.
        """
        osr = int(osr)
        if osr < 1:
            raise ValueError(f"osr must be >= 1, got {osr!r}")
        p = np.empty(2 * osr, dtype=float)
        p[:osr] = self.c0
        p[osr:] = self.c1
        return p * self.symbol_amplitude_v

    def burden_db(self, channel_il_db_at_nyquist: float) -> float:
        """CTLE boost still required at Nyquist after the transmitter's share.

        `channel IL at Nyquist - tilt_db`. May be negative, and that is a real
        answer: at the bottom of the channel family the mandated de-emphasis
        already over-equalises, and a CTLE set to S3's 3 dB minimum is adding
        boost the link does not need.
        """
        il = float(channel_il_db_at_nyquist)
        if not math.isfinite(il) or il < 0.0:
            raise ValueError(f"channel IL must be a non-negative dB loss, got {il!r}")
        return il - self.tilt_db

    def __str__(self) -> str:
        if self.de_emphasis_db == 0.0:
            return "TX no de-emphasis"
        return f"TX {self.de_emphasis_db:+.1f} dB de-emphasis"


#: The transmitter every headline number in CHANNEL_MODEL.md assumes: the
#: Gen2 mandate at the Gen2 minimum swing.
PCIE_GEN2_TX = TxDeEmphasis()
