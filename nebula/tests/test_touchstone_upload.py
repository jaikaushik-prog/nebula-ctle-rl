"""Fail-capable gates for the dependency-free Touchstone intake product."""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pytest


def _s4p(path, *, fmt="RI", frequencies=(1.0, 2.5, 5.0),
         transmission=(0.8, 0.5, 0.25)):
    lines = [f"# GHz S {fmt} R 50", "! synthetic test fixture; not measured"]
    for freq, mag in zip(frequencies, transmission):
        pairs = []
        for index in range(16):
            # Touchstone 1.x is row-wise for 3+ ports: index 2 is S13,
            # i.e. output port 1 from input port 3.
            value = mag if index == 2 else (0.05 if index % 5 == 0 else 0.0)
            if fmt == "RI":
                pairs.extend((value, 0.0))
            elif fmt == "MA":
                pairs.extend((value, 0.0))
            else:
                pairs.extend((20.0 * np.log10(max(value, 1e-12)), 0.0))
        # Exercise legal continuation lines instead of relying on one-line data.
        tokens = [f"{freq:g}"] + [f"{value:.12g}" for value in pairs]
        lines.append(" ".join(tokens[:13]))
        lines.append(" ".join(tokens[13:]))
    path.write_text("\n".join(lines) + "\n", encoding="ascii")
    return path


@pytest.mark.parametrize("fmt", ["RI", "MA", "DB"])
def test_dependency_free_s4p_parser_reads_s31_in_all_standard_formats(
        tmp_path, fmt):
    from nebula.link.channel import insertion_loss_from_touchstone

    path = _s4p(tmp_path / f"channel_{fmt.lower()}.s4p", fmt=fmt)
    frequency, loss = insertion_loss_from_touchstone(path, ports=(1, 3))
    assert frequency.tolist() == pytest.approx([1e9, 2.5e9, 5e9])
    assert loss.tolist() == pytest.approx(
        [-20 * np.log10(0.8), -20 * np.log10(0.5),
         -20 * np.log10(0.25)], abs=1e-8)


def test_touchstone_parser_rejects_truncation_and_bad_port_map(tmp_path):
    from nebula.link.channel import insertion_loss_from_touchstone

    broken = tmp_path / "broken.s4p"
    broken.write_text("# GHz S RI R 50\n1 0 0 0 0\n", encoding="ascii")
    with pytest.raises(ValueError, match="truncated|record|values"):
        insertion_loss_from_touchstone(broken)

    good = _s4p(tmp_path / "good.s4p")
    with pytest.raises(ValueError, match="port"):
        insertion_loss_from_touchstone(good, ports=(1, 5))


def test_two_port_historical_data_order_is_handled_explicitly(tmp_path):
    from nebula.link.channel import insertion_loss_from_touchstone

    path = tmp_path / "two_port.s2p"
    # Touchstone's two-port exception is S11,S21,S12,S22.
    path.write_text(
        "# GHz S RI R 50\n1 0 0 0.7 0 0.1 0 0 0\n"
        "2.5 0 0 0.5 0 0.2 0 0 0\n", encoding="ascii")
    frequency, loss = insertion_loss_from_touchstone(path, ports=(2, 1))
    assert frequency.tolist() == pytest.approx([1e9, 2.5e9])
    assert loss.tolist() == pytest.approx(
        [-20 * np.log10(0.7), -20 * np.log10(0.5)])


def test_profile_records_file_identity_and_refuses_to_claim_rl_verification(
        tmp_path):
    from nebula.channel_upload import profile_touchstone

    path = _s4p(tmp_path / "board.s4p")
    profile = profile_touchstone(path, ports=(1, 3))
    assert profile["source_file"] == "board.s4p"
    assert profile["source_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest().upper()
    assert profile["ports"] == {"output": 1, "input": 3}
    assert profile["frequency_span_hz"] == [1e9, 5e9]
    assert profile["measured_loss_at_nyquist_db"] == pytest.approx(
        -20 * np.log10(0.5))
    assert profile["rl_product_verified"] is False
    assert profile["status"] == "PROFILED_NOT_RL_VERIFIED"
    assert "not" in profile["limitation"].lower()


def test_profile_refuses_a_file_that_does_not_reach_nyquist(tmp_path):
    from nebula.channel_upload import profile_touchstone

    path = _s4p(tmp_path / "short.s4p", frequencies=(0.5, 1.0, 2.0),
                transmission=(0.9, 0.8, 0.7))
    with pytest.raises(ValueError, match="Nyquist|2.5"):
        profile_touchstone(path)


def test_upload_writes_json_and_a_real_measured_vs_fit_png(tmp_path):
    from nebula.channel_upload import write_channel_report

    path = _s4p(tmp_path / "board.s4p")
    out = tmp_path / "report"
    written = write_channel_report(path, out, ports=(1, 3))
    assert {item.name for item in written} == {
        "channel_profile.json", "channel_profile.png"}
    profile = json.loads((out / "channel_profile.json").read_text())
    assert profile["status"] == "PROFILED_NOT_RL_VERIFIED"
    png = (out / "channel_profile.png").read_bytes()
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(png) > 10_000


def test_command_line_front_door_writes_the_same_report(tmp_path, capsys):
    from nebula.channel_upload import main

    path = _s4p(tmp_path / "board.s4p")
    out = tmp_path / "cli_report"
    assert main([str(path), "--ports", "1", "3", "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "PROFILED_NOT_RL_VERIFIED" in printed
    assert (out / "channel_profile.json").is_file()
    assert (out / "channel_profile.png").is_file()
