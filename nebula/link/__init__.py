"""Link layer: DeviceResult -> pole-zero CTLE -> 1-tap DFE -> LinkResult."""

from nebula.link.calibration import (
    NRZ_IDEAL_EYE_NORM,
    check_compression,
    output_swing_pp_v,
    normalized_to_volts,
    volts_to_normalized,
)
from nebula.link.channel import (
    BALANCED,
    CAUSALITY_ENERGY_THRESHOLD,
    DIELECTRIC_DOMINATED,
    FAMILY_IL_DB,
    FAMILY_SKIN_FRACTIONS,
    FR4_MICROSTRIP,
    SKIN_DOMINATED,
    ChannelModel,
    Reflection,
    Stackup,
    channel_family,
    fit_insertion_loss,
    fit_from_touchstone,
)
from nebula.link.config import (
    DEFAULT_LOSS_SWEEP_DB,
    PCIE_GEN2_DE_EMPHASIS_DB,
    PCIE_GEN2_DE_EMPHASIS_OPTION_DB,
    PCIE_GEN2_TX_DIFF_PP_MIN_V,
    LinkConfig,
    sweep_channel_loss,
)
from nebula.link.cursors import (
    CursorSet,
    MatchedCtle,
    extract_cursors,
    eye_estimate,
    matched_ctle,
    peak_frequency_hz,
)
from nebula.link.interface import LinkEvaluator, safe_evaluate_link
from nebula.link.tx import PCIE_GEN2_TX, TxDeEmphasis

__all__ = [
    "NRZ_IDEAL_EYE_NORM",
    "check_compression",
    "output_swing_pp_v",
    "normalized_to_volts",
    "volts_to_normalized",
    "BALANCED",
    "CAUSALITY_ENERGY_THRESHOLD",
    "DIELECTRIC_DOMINATED",
    "FAMILY_IL_DB",
    "FAMILY_SKIN_FRACTIONS",
    "FR4_MICROSTRIP",
    "SKIN_DOMINATED",
    "ChannelModel",
    "Reflection",
    "Stackup",
    "channel_family",
    "fit_insertion_loss",
    "fit_from_touchstone",
    "DEFAULT_LOSS_SWEEP_DB",
    "PCIE_GEN2_DE_EMPHASIS_DB",
    "PCIE_GEN2_DE_EMPHASIS_OPTION_DB",
    "PCIE_GEN2_TX_DIFF_PP_MIN_V",
    "LinkConfig",
    "sweep_channel_loss",
    "CursorSet",
    "MatchedCtle",
    "extract_cursors",
    "eye_estimate",
    "matched_ctle",
    "peak_frequency_hz",
    "LinkEvaluator",
    "safe_evaluate_link",
    "PCIE_GEN2_TX",
    "TxDeEmphasis",
]
