"""Fail-closed browser adapter for the calibrated transistor hardware evidence.

The frontend does not own any circuit result.  This module validates the exact
Entry 143/144 summaries and nominal link deck, then emits a compact display
payload derived from those frozen files.  A changed or incomplete artifact is
an error, never a reason to keep showing an old green status.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Optional


ROOT = Path(__file__).resolve().parents[2]
NOMINAL_ROOT = (
    ROOT / "nebula" / "product_audits" /
    "entry143_dfe_calibrated_verification_20260910"
)
PVT_ROOT = (
    ROOT / "nebula" / "product_audits" /
    "entry144_dfe_calibrated_pvt_20260910"
)
NOMINAL_SUMMARY = NOMINAL_ROOT / "summary.json"
PVT_SUMMARY = PVT_ROOT / "summary.json"
NOMINAL_NETLIST = (
    NOMINAL_ROOT / "link_state0_tol1e-05_step5ps" / "design.cir"
)

EXPECTED_NOMINAL_SHA256 = (
    "14d7d368163652235378e1566e4800a7d26ec2a550922300a015978b74602d96"
)
EXPECTED_PVT_SHA256 = (
    "21a6b7cb5d81bd0e23981d2cc3741a9a0147b6793f401d63c646c5e08f06e424"
)
EXPECTED_NETLIST_SHA256 = (
    "c1b2598b57278cbc1101bf8600284bcf95f853cd612c36ceb1b809dade89bede"
)

HARDWARE_ARTIFACTS = {
    "hardware-schematic": ROOT / "nebula/web/assets/transistor_schematic.png",
    "nominal-eye": ROOT / "nebula/web/assets/nominal_eye.png",
    "visual-sources": ROOT / "nebula/web/assets/visual_sources.json",
    "nominal-netlist": NOMINAL_NETLIST,
    "nominal-result": (
        NOMINAL_ROOT / "link_state0_tol1e-05_step5ps" / "result.json"
    ),
    "nominal-summary": NOMINAL_SUMMARY,
    "pvt-summary": PVT_SUMMARY,
    "results-guide": ROOT / "nebula" / "DFE_CALIBRATED_RESULTS.md",
}

VISUAL_HASHES = {
    "hardware-schematic": "bcb4eb2d92a5ed52020cbea5cb8957cfeb08fe64abb41121f74997309d0b629f",
    "nominal-eye": "cd8f4d33eae4d5663f5d83f732f58fac18952f19770fda2266150861c5828c9e",
}

_CORNER = re.compile(
    r"^(?P<process>ss|sf|tt|fs|ff)_vdd"
    r"(?P<vdd>0\.95|1\.00|1\.05)_t(?P<temp>0|27|125)$"
)


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _load_pinned(path: Path, expected: str, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"The pinned {label} evidence is missing.")
    actual = _sha256(path)
    if actual != expected:
        raise ValueError(
            f"The pinned {label} SHA-256 changed; hardware status is unavailable."
        )
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"The pinned {label} is not a JSON object.")
    return value


def _require(condition: Any, message: str) -> None:
    if not condition:
        raise ValueError(f"Calibrated hardware evidence is incomplete: {message}.")


def _range(values: list[float]) -> dict[str, float]:
    return {"min": min(values), "max": max(values)}


def _validate_netlist(path: Path = NOMINAL_NETLIST) -> None:
    if _sha256(path) != EXPECTED_NETLIST_SHA256:
        raise ValueError(
            "The pinned nominal netlist SHA-256 changed; hardware status is unavailable."
        )
    deck = path.read_text(encoding="utf-8")
    required = {
        "configurable Rs switch": "Xrc_switch rc_mid rc_gate s2",
        "first configurable Cs varactor": "Xrc_var_s1 s1 rc_ct",
        "second configurable Cs varactor": "Xrc_var_s2 s2 rc_ct",
        "DFE master memory": "Xdf_mtrack df_ma df_clkb",
        "DFE slave memory": "Xdf_strack df_sa df_clk",
        "DFE CML summer": "Xdfe_sump sum_n outn sum_tail",
        "DFE feedback DAC": "Xdfe_dacp sum_p df_q fd_common",
    }
    missing = [name for name, token in required.items() if token not in deck]
    _require(not missing, "nominal netlist lacks " + ", ".join(missing))


def _corner_row(item: dict[str, Any]) -> dict[str, Any]:
    corner = item.get("corner")
    match = _CORNER.fullmatch(str(corner))
    _require(match is not None, f"unrecognised PVT corner {corner!r}")
    result = item.get("result") or {}
    passed = (
        result.get("instrument_ok") is True
        and result.get("logic_pass") is True
        and result.get("signal_gate_pass") is True
        and result.get("correct_bits") == result.get("scored_bits") == 64
    )
    _require(passed, f"PVT corner {corner} does not pass its frozen gate")
    aperture = result.get("aperture") or {}
    return {
        "corner": corner,
        "label": (
            f"{match.group('process').upper()} / {1.8*float(match.group('vdd')):.2f} V / "
            f"{match.group('temp')} C"
        ),
        "process": match.group("process"),
        "vdd": float(match.group("vdd")),
        "temp_c": int(match.group("temp")),
        "status": "pass",
        "correct_bits": result["correct_bits"],
        "scored_bits": result["scored_bits"],
        "sampled_eye_height_v": float(result["sampled_eye_height_v"]),
        "positive_width_ui": float(aperture["eye_width_ui"]),
        "width_above_100mv_ui": float(
            aperture["eye_width_at_100mv_ui"]
        ),
        "vdd_power_w": float(result["ctle_plus_dfe_vdd_power_w"]),
        "external_clock_positive_power_w": float(
            result["external_clock_positive_supplied_power_w"]
        ),
    }


def build_hardware_checkpoint(
    *,
    nominal_summary: Path = NOMINAL_SUMMARY,
    pvt_summary: Path = PVT_SUMMARY,
) -> dict[str, Any]:
    """Return a compact, evidence-derived payload for the hardware UI."""
    nominal = _load_pinned(
        Path(nominal_summary), EXPECTED_NOMINAL_SHA256, "Entry 143 summary"
    )
    pvt = _load_pinned(
        Path(pvt_summary), EXPECTED_PVT_SHA256, "Entry 144 summary"
    )
    _validate_netlist()
    for name, expected in VISUAL_HASHES.items():
        _require(_sha256(HARDWARE_ARTIFACTS[name]) == expected,
                 f"{name} visual SHA-256 changed")

    _require(nominal.get("entry") == 143, "wrong nominal entry")
    _require(nominal.get("nominal_calibrated_pass") is True,
             "nominal calibrated gate is not passing")
    _require(nominal.get("sources_unchanged") is True, "nominal sources changed")
    _require(nominal.get("pdk_unchanged") is True, "nominal PDK changed")
    static = nominal.get("static") or []
    tones = nominal.get("tones") or []
    link = nominal.get("link") or {}
    _require(len(static) == 2, "two held-state static checks were not recorded")
    _require(len(tones) == 4, "four clocked HD3 checks were not recorded")
    for item in static:
        _require(
            item.get("instrument_ok") is True
            and item.get("small_signal_specs_pass") is True
            and item.get("target_match") is True
            and item.get("noise", {}).get("noise_limit_pass") is True,
            "a held-state nominal analog check does not pass",
        )
    for item in tones:
        _require(
            item.get("instrument_ok") is True
            and item.get("hd3_model_pass") is True
            and item.get("harmonic_window_stable") is True,
            "a clocked HD3 check does not pass",
        )
    _require(
        link.get("instrument_ok") is True
        and link.get("logic_pass") is True
        and link.get("signal_gate_pass") is True
        and link.get("correct_bits") == link.get("scored_bits") == 64,
        "fresh nominal transistor link check does not pass",
    )

    _require(pvt.get("entry") == 144, "wrong PVT entry")
    _require(pvt.get("primary_channel_pvt_pass") is True,
             "link PVT gate is not passing")
    _require(pvt.get("sources_unchanged") is True, "PVT sources changed")
    _require(pvt.get("pdk_unchanged") is True, "PVT PDK changed")
    corners = [_corner_row(item) for item in (pvt.get("pvt") or [])]
    _require(len(corners) == 45, "45 link PVT corners were not recorded")

    target = nominal.get("target") or []
    _require(target == [9.0, 1.9e9, 0.7, 0.185],
             "calibrated target/control identity changed")
    _require(pvt.get("r_fraction") == target[2], "PVT R control changed")
    _require(pvt.get("c_fraction") == target[3], "PVT C control changed")
    _require(pvt.get("corner_retuning") is False, "corner retuning was used")

    boosts = [float(item["response"]["boost_db"]) for item in static]
    peaks = [float(item["response"]["peak_frequency_hz"]) for item in static]
    noises = [float(item["noise"]["input_noise_vrms"]) for item in static]
    hd3 = [float(item["ctle_hd3"]["hd3_dbc"]) for item in tones]
    aperture = link.get("aperture") or {}

    return {
        "id": "calibrated-transistor-dfe-entry144",
        "title": "Configurable transistor CTLE + 1-tap DFE",
        "status": "pass",
        "status_label": "45/45 LINK PVT",
        "topology": [
            {
                "key": "ctle", "label": "SKY130 CTLE core",
                "detail": "Differential transistor core with physical bias reference.",
                "status": "implemented",
            },
            {
                "key": "rs", "label": "Configurable Rs",
                "detail": "High-poly degeneration branch selected by a SKY130 NMOS.",
                "status": "implemented",
            },
            {
                "key": "cs", "label": "Configurable Cs",
                "detail": "Two physical N500 SKY130 varactors controlled together.",
                "status": "implemented",
            },
            {
                "key": "summer", "label": "CML summer",
                "detail": "Transistor differential summing node loaded by real poly resistors.",
                "status": "implemented",
            },
            {
                "key": "memory", "label": "Decision memory",
                "detail": "Clocked transistor master/slave CML decision-and-hold path.",
                "status": "implemented",
            },
            {
                "key": "dac", "label": "1-tap feedback DAC",
                "detail": "Four-code switched-current DAC with physical tail bleeders.",
                "status": "implemented",
            },
        ],
        "controls": {
            "r_fraction": float(target[2]),
            "c_fraction": float(target[3]),
            "r_control_v_nominal": round(float(target[2]) * 1.8, 6),
            "c_control_v_nominal": round(float(target[3]) * 1.8, 6),
            "corner_retuning": bool(pvt["corner_retuning"]),
            "runtime_settling_verified": bool(
                pvt.get("runtime_settling_verified", False)
            ),
        },
        "nominal": {
            "target_boost_db": float(target[0]),
            "target_peak_frequency_hz": float(target[1]),
            "boost_db": _range(boosts),
            "peak_frequency_hz": _range(peaks),
            "input_noise_vrms": _range(noises),
            "hd3_dbc": _range(hd3),
            "correct_bits": int(link["correct_bits"]),
            "scored_bits": int(link["scored_bits"]),
            "sampled_eye_height_v": float(link["sampled_eye_height_v"]),
            "positive_width_ui": float(aperture["eye_width_ui"]),
            "width_above_100mv_ui": float(
                aperture["eye_width_at_100mv_ui"]
            ),
            "vdd_power_w": float(link["ctle_plus_dfe_vdd_power_w"]),
        },
        "pvt": {
            "n_pass": len(corners),
            "n_points": len(corners),
            "all_pass": True,
            "channel_loss_db": 7.5,
            "corner_retuning": False,
            "minimum_eye_height_v": min(
                item["sampled_eye_height_v"] for item in corners
            ),
            "minimum_positive_width_ui": min(
                item["positive_width_ui"] for item in corners
            ),
            "minimum_width_above_100mv_ui": min(
                item["width_above_100mv_ui"] for item in corners
            ),
            "maximum_vdd_power_w": max(
                item["vdd_power_w"] for item in corners
            ),
            "maximum_external_clock_positive_power_w": max(
                item["external_clock_positive_power_w"] for item in corners
            ),
            "corners": corners,
        },
        "boundaries": [
            {
                "label": "Analog checks",
                "detail": "Noise and HD3 are nominal checks. Analog PVT is not verified.",
            },
            {
                "label": "Link checks",
                "detail": (
                    "The 45/45 result uses a finite noiseless pattern on one "
                    "constructed 7.5 dB channel; it is not BER or arbitrary-channel proof."
                ),
            },
            {
                "label": "Controls and clocks",
                "detail": (
                    "Control, common-mode and clock generators remain external; "
                    "DFE-active runtime tuning and lifetime reliability are not verified."
                ),
            },
            {
                "label": "Physical completion",
                "detail": (
                    "Device geometry is netlist-derived, not a routed extracted layout; "
                    "passive tolerance and mismatch are not included."
                ),
            },
        ],
        "evidence": [
            {
                "key": key,
                "label": label,
                "url": f"/api/hardware/artifacts/{key}",
            }
            for key, label in (
                ("hardware-schematic", "Transistor device schematic (PNG)"),
                ("nominal-eye", "Nominal transistor eye diagram (PNG)"),
                ("visual-sources", "Visual source hashes and provenance"),
                ("nominal-netlist", "Exact calibrated transistor netlist"),
                ("nominal-result", "Fresh nominal link result"),
                ("nominal-summary", "Nominal analog and link summary"),
                ("pvt-summary", "Complete 45-corner link PVT summary"),
                ("results-guide", "Plain-language calibrated result guide"),
            )
        ],
        "provenance": {
            "nominal_entry": 143,
            "pvt_entry": 144,
            "nominal_summary_sha256": EXPECTED_NOMINAL_SHA256,
            "pvt_summary_sha256": EXPECTED_PVT_SHA256,
            "nominal_netlist_sha256": EXPECTED_NETLIST_SHA256,
            "simulator": "ngspice 41",
            "pdk": "SKY130",
        },
    }


def hardware_artifact(name: str) -> Optional[Path]:
    """Resolve one allow-listed hardware review artifact."""
    if Path(name).name != name:
        return None
    path = HARDWARE_ARTIFACTS.get(name)
    if path is not None and name in VISUAL_HASHES:
        _validate_netlist()
        _require(_sha256(path) == VISUAL_HASHES[name],
                 f"{name} visual SHA-256 changed")
    return path if path is not None and path.is_file() else None


__all__ = (
    "NOMINAL_SUMMARY",
    "PVT_SUMMARY",
    "build_hardware_checkpoint",
    "hardware_artifact",
)
