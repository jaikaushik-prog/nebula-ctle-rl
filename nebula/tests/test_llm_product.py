"""Product gates for plain-English request -> shielded-RL deliverables."""

from __future__ import annotations

import inspect


def _rl_design() -> dict:
    return {
        "request": {"peaking_db": 9.0, "f_peak_hz": 1.9e9,
                    "f_peak_ghz": 1.9},
        "method": "rl-hybrid", "robust_search": True,
        "simulations": {"search": 0, "measure": 0, "total": 0},
        "search": {"policy_seed": 2026090500, "rl_proposals": 2406,
                   "shield_fallbacks": 49, "channel_losses_db": [
                       3.0, 4.5, 6.0, 7.5, 9.0, 10.5, 12.0]},
        "nominal": {
            "ok": True, "verdict": "ok", "reward": 14.2738,
            "feasible": True, "worst_spec": "S3_f_peak_match",
            "meas": {"g_dc_db": -3.0249, "peaking_db": 7.99,
                     "f_peak_oct": -0.614, "nyq_boost_db": 7.5175,
                     "inoise_vrms": 0.0003702, "power_w": 0.0066803,
                     "pair_margin_v": 0.6422, "tail_margin_v": 0.3464,
                     "_f_peak_ghz": 1.6337, "_noise_mv": 0.3702,
                     "_power_mw": 6.6803},
            "params": {"w_in": 57.977e-6, "l_in": 391.15e-9,
                       "nf_in": 4, "i_bias": 3.6269e-3,
                       "rs": 356.82, "cs": 1.6846e-12,
                       "rl": 254.63, "cl": 32.63e-15,
                       "vcm_in": 1.5010}},
        "verification": {
            "n_points": 315, "n_pass": 315, "n_failed": 0,
            "n_corners": 45, "n_channel_losses": 7,
            "all_points_pass": True, "mandated_all_pass": True,
        },
        "peaking_is_a_band_not_a_target": "request is scored",
        "wall_s": 1.0,
    }


def test_rl_explanation_understands_the_7_by_45_product_schema():
    from nebula.llm.explanation import facts, template
    from nebula.llm.grounding import check

    text = template(_rl_design())
    for expected in ("315", "7", "45", "2406", "49"):
        assert expected in text
    assert "simulator-backed shield" in text
    assert "tie-break" not in text
    assert check(text, facts(_rl_design())) is text


def test_plain_english_cli_defaults_to_the_shielded_rl_product(monkeypatch):
    import nebula.design as designer
    from nebula.llm import __main__ as cli

    seen = {}

    def fake_design(peaking, frequency, **kwargs):
        seen.update(peaking=peaking, frequency=frequency, **kwargs)
        return _rl_design()

    monkeypatch.setattr(designer, "design", fake_design)
    monkeypatch.setattr(designer, "report", lambda design: "report")
    monkeypatch.setattr(cli, "explain_design",
                        lambda design, use_llm=False: ("safe", "template"))
    assert cli.main(["9 dB near 1.9 GHz"]) == 0
    assert seen["method"] == "rl-hybrid"
    assert seen["peaking"] == 9.0 and seen["frequency"] == 1.9e9
    assert "channel_loss_db" not in seen or seen["channel_loss_db"] is None


def test_plain_english_output_uses_the_same_exporter_as_design(monkeypatch,
                                                               tmp_path):
    import nebula.design as designer
    from nebula.llm import __main__ as cli

    captured = {}
    monkeypatch.setattr(designer, "design", lambda *args, **kwargs: _rl_design())
    monkeypatch.setattr(designer, "report", lambda design: "report")
    monkeypatch.setattr(designer, "prepare_output_deck",
                        lambda design: "deck", raising=False)
    monkeypatch.setattr(cli, "explain_design",
                        lambda design, use_llm=False: ("safe", "template"))

    def fake_write(design, out, extra_files=None, **kwargs):
        captured["design"] = design
        captured["out"] = out
        captured["extra_files"] = extra_files
        captured.update(kwargs)
        return [], []

    monkeypatch.setattr(designer, "write_outputs", fake_write, raising=False)
    assert cli.main(["9 dB at 1.9 GHz", "--out", str(tmp_path)]) == 0
    assert captured["design"]["natural_language"]["parsed_by"] == "regex"
    assert captured["design"]["explanation"]["source"] == "template"
    assert captured["extra_files"] == {"explanation.txt": "safe"}
    assert captured["deck"] == "deck"


def test_plain_english_cli_refuses_an_uncovered_product_request_cleanly(
        monkeypatch, capsys):
    import nebula.design as designer
    from nebula.llm import __main__ as cli

    monkeypatch.setattr(
        designer, "design", lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("no compliant setting at 1 of 315 conditions")))
    assert cli.main(["12 dB at 1.25 GHz"]) == 2
    assert "no compliant setting" in capsys.readouterr().err


def test_both_front_doors_call_one_shared_output_implementation():
    import nebula.design as designer
    from nebula.llm import __main__ as cli

    assert "write_outputs" in inspect.getsource(designer.main)
    assert "write_outputs" in inspect.getsource(cli.main)
