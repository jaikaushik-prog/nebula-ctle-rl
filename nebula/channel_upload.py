"""Dependency-free Touchstone intake and provenance report.

Usage::

    python -m nebula.channel_upload board.s4p --ports 1 3 --out channel_report

This command profiles real input data; it does not silently substitute that
file into the frozen RL bank.  The bank was characterised on the constructed
channel family, so an uploaded channel needs a new link re-characterisation
before it can support a product compliance claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Optional, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from nebula.common.types import NYQUIST_HZ
from nebula.link.channel import (
    FAMILY_IL_DB, fit_insertion_loss, insertion_loss_from_touchstone,
)


STATUS = "PROFILED_NOT_RL_VERIFIED"
LIMITATION = (
    "The uploaded S-parameter file was parsed and fitted, but it was not used "
    "to regenerate the frozen 512-setting RL eye bank. This report is not an "
    "RL compliance or eye-opening claim for the uploaded channel."
)


def _loaded(path, ports, f_max_hz=None):
    source = Path(path)
    frequency, loss = insertion_loss_from_touchstone(
        source, ports=ports, f_max_hz=f_max_hz)
    if frequency[0] > NYQUIST_HZ or frequency[-1] < NYQUIST_HZ:
        raise ValueError(
            "Touchstone frequency span must include PCIe Gen2 Nyquist "
            f"({NYQUIST_HZ / 1e9:g} GHz); got "
            f"{frequency[0] / 1e9:g}..{frequency[-1] / 1e9:g} GHz")
    fit = fit_insertion_loss(frequency, loss)
    measured_nyquist = float(np.interp(NYQUIST_HZ, frequency, loss))
    return source, frequency, loss, fit, measured_nyquist


def profile_touchstone(path, ports: tuple[int, int] = (1, 3),
                       f_max_hz: Optional[float] = None) -> dict:
    """Return a JSON-safe, hash-grounded profile of one insertion path."""
    source, frequency, _, fit, measured_nyquist = _loaded(
        path, ports, f_max_hz=f_max_hz)
    nearest = min(FAMILY_IL_DB, key=lambda value: (
        abs(float(value) - measured_nyquist), float(value)))
    return {
        "status": STATUS,
        "rl_product_verified": False,
        "source_file": source.name,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest().upper(),
        "ports": {"output": int(ports[0]), "input": int(ports[1])},
        "n_points": int(frequency.size),
        "frequency_span_hz": [float(frequency[0]), float(frequency[-1])],
        "nyquist_hz": float(NYQUIST_HZ),
        "measured_loss_at_nyquist_db": measured_nyquist,
        "fit": {
            "model": "IL_dB(f) = A*sqrt(f_GHz) + B*f_GHz",
            "loss_at_nyquist_db": float(fit.channel.il_db_at_nyquist),
            "skin_fraction_at_nyquist": float(fit.channel.skin_fraction),
            "a_db_per_sqrt_ghz": float(fit.channel.a_db_per_sqrt_ghz),
            "b_db_per_ghz": float(fit.channel.b_db_per_ghz),
            "rms_residual_db": float(fit.rms_residual_db),
            "max_residual_db": float(fit.max_residual_db),
        },
        "nearest_characterised_loss_db": float(nearest),
        "characterised_loss_range_db": [
            float(min(FAMILY_IL_DB)), float(max(FAMILY_IL_DB))],
        "limitation": LIMITATION,
    }


def _draw(path, out_path, ports=(1, 3), f_max_hz=None) -> Path:
    source, frequency, loss, fit, measured_nyquist = _loaded(
        path, ports, f_max_hz=f_max_hz)
    fitted = fit.channel.il_db(frequency)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(10.8, 6.4), dpi=180)
    fig.patch.set_facecolor("white")
    ax.plot(frequency / 1e9, loss, color="#0072B2", lw=2.1,
            label=f"uploaded S{ports[0]}{ports[1]} magnitude")
    ax.plot(frequency / 1e9, fitted, color="#D55E00", lw=1.8, ls="--",
            label="two-term link-model fit")
    ax.axvline(NYQUIST_HZ / 1e9, color="#222222", lw=1.0, ls=":")
    ax.scatter([NYQUIST_HZ / 1e9], [measured_nyquist], s=55,
               color="#0072B2", edgecolor="white", zorder=5)
    ax.set_xlabel("frequency (GHz)")
    ax.set_ylabel("positive insertion loss (dB)")
    ax.grid(color="#D8DDE3", lw=0.7)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, loc="upper left")
    fig.suptitle("Touchstone channel intake", x=0.09, ha="left",
                 fontsize=17, fontweight="bold", color="#18202A")
    ax.set_title(
        f"{source.name}  |  ports out={ports[0]}, in={ports[1]}  |  "
        f"Nyquist loss {measured_nyquist:.3f} dB\n"
        f"fit residual RMS {fit.rms_residual_db:.3f} dB, max "
        f"{fit.max_residual_db:.3f} dB",
        loc="left", fontsize=9.5, color="#596573", pad=12)
    fig.text(
        0.09, 0.025,
        "STATUS: PROFILED, NOT RL VERIFIED. The frozen 512-setting eye bank "
        "was not regenerated for this file.",
        ha="left", va="bottom", fontsize=8.5, color="#C95616",
        fontweight="bold")
    fig.subplots_adjust(left=0.10, right=0.97, top=0.82, bottom=0.15)
    fig.savefig(out, facecolor="white")
    plt.close(fig)
    return out


def write_channel_report(path, out_path, ports: tuple[int, int] = (1, 3),
                         f_max_hz: Optional[float] = None) -> list[Path]:
    """Write the immutable-source profile and measured-versus-fit plot."""
    out = Path(out_path)
    out.mkdir(parents=True, exist_ok=True)
    profile = profile_touchstone(path, ports=ports, f_max_hz=f_max_hz)
    json_path = out / "channel_profile.json"
    json_path.write_text(json.dumps(profile, indent=1), encoding="utf-8")
    png_path = _draw(path, out / "channel_profile.png", ports, f_max_hz)
    return [json_path, png_path]


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("touchstone", help="input .sNp file, normally .s4p")
    parser.add_argument(
        "--ports", nargs=2, type=int, metavar=("OUT", "IN"), default=(1, 3),
        help="1-based insertion path in file port numbering (default: 1 3)")
    parser.add_argument("--f-max", type=float, default=None,
                        help="optional maximum fitting frequency in Hz")
    parser.add_argument("--out", required=True, help="report output directory")
    args = parser.parse_args(argv)
    try:
        written = write_channel_report(
            args.touchstone, args.out, ports=tuple(args.ports),
            f_max_hz=args.f_max)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    profile = json.loads(written[0].read_text(encoding="utf-8"))
    print(f"profiled {profile['source_file']} at ports "
          f"{profile['ports']['output']}<-{profile['ports']['input']}")
    print(f"Nyquist loss: {profile['measured_loss_at_nyquist_db']:.3f} dB")
    print(f"status: {profile['status']}")
    print("wrote " + ", ".join(str(path) for path in written))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ("STATUS", "LIMITATION", "profile_touchstone",
           "write_channel_report", "main")
