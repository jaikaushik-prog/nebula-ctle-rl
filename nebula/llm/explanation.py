"""
llm/explain.py — a finished design in, prose out, **every number checked**.

THE CONTRACT
-------------
`facts()` builds the ONLY numbers that may appear in the explanation, in the
units they will be quoted in. `explain()` produces text and then hands it to
`grounding.check`, which raises on the first literal no fact supports. **A
failing explanation is discarded, not repaired** -- and the caller falls back
to the deterministic template, which is built from the same facts by
`str.format` and therefore cannot be ungrounded by construction.

So the worst case of the LLM path is the offline path. That is the property
worth having.

WHAT THE MODEL IS ASKED FOR
-----------------------------
Wording, ordering, and emphasis -- the things prose is for. Not judgement: it
is told the verdicts (`feasible`, which spec binds, whether the corners were
checked) rather than being asked to work them out, because a model inferring
"this looks fine" from a table is exactly the failure the rest of this project
is built to prevent.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from nebula.llm import client as C
from nebula.llm import grounding as G


def facts(d: Mapping[str, Any]) -> dict:
    """The numbers an explanation may use, in the units it will quote.

    Built from `nebula.design.design()`'s result. **Units are converted HERE,
    once**, so the model never has to multiply -- and `grounding.check` can
    compare literals directly rather than guessing what scale a number is in.
    """
    req = d["request"]
    n = d["nominal"]
    out: dict = {
        "requested_peaking_db": req["peaking_db"],
        "requested_f_peak_ghz": req["f_peak_ghz"],
        "simulations_total": d["simulations"]["total"],
        "simulations_search": d["simulations"]["search"],
    }
    if not n.get("ok"):
        return out

    m, p = n["meas"], n["params"]
    out.update({
        "peaking_db": m["peaking_db"],
        "f_peak_ghz": m["_f_peak_ghz"],
        "nyquist_boost_db": m["nyq_boost_db"],
        "dc_gain_db": m["g_dc_db"],
        "noise_mv_rms": m["_noise_mv"],
        "power_mw": m["_power_mw"],
        "pair_margin_v": m["pair_margin_v"],
        "tail_margin_v": m["tail_margin_v"],
        "reward": n["reward"],
        "w_in_um": p["w_in"] * 1e6,
        "l_in_nm": p["l_in"] * 1e9,
        "nf_in": p["nf_in"],
        "i_bias_ma": p["i_bias"] * 1e3,
        "rs_ohm": p["rs"],
        "cs_pf": p["cs"] * 1e12,
        "rl_ohm": p["rl"],
        "vcm_in_v": p["vcm_in"],
        "cl_ff": p["cl"] * 1e15,
        # the limits, so the model may quote a requirement it is comparing to
        "noise_limit_mv": 1.5,
        "power_limit_mw": 15.0,
        "peaking_band_lo_db": 3.0,
        "peaking_band_hi_db": 12.0,
        "f_peak_window_lo_ghz": 1.25,
        "f_peak_window_hi_ghz": 2.5,
    })
    v = d.get("verification")
    if v:
        out.update({"corner_points": v["n_points"],
                    "corner_points_failed": v["n_failed"],
                    "n_corners": v["n_corners"]})
        if d.get("method") == "rl-hybrid":
            search = d.get("search") or {}
            out.update({
                "n_channel_losses": v["n_channel_losses"],
                "rl_proposals": search["rl_proposals"],
                "shield_fallbacks": search["shield_fallbacks"],
                "rl_shield_selections": (
                    v["n_points"] - v["n_failed"]
                    - search["shield_fallbacks"]),
            })
        else:
            out.update({
                "corner_points_failed_unscreened":
                    v["n_failed_outside_the_screen"],
                "worst_corner_reward": v["worst_reward"],
                "n_loads": v["n_loads"],
            })
    return out


def verdicts(d: Mapping[str, Any]) -> dict:
    """The judgements, stated rather than inferred. **No numbers here.**"""
    n = d["nominal"]
    v = d.get("verification")
    return {
        "ok": bool(n.get("ok")),
        "feasible_at_nominal": bool(n.get("feasible")),
        "binding_spec": n.get("worst_spec") or "none",
        "method": d["method"],
        "robust_search": bool(d["robust_search"]),
        "corner_verified": v is not None,
        "corner_verdict": (None if v is None else
                           ("passes every point" if v["all_points_pass"]
                            else "FAILS at least one point")),
        "peaking_is_a_band": True,
        "request_scored": d["method"] in ("auto", "rl-hybrid"),
    }


def template(d: Mapping[str, Any]) -> str:
    """**The deterministic path.** Ungrounded by construction: every number is
    substituted from `facts()`, so there is nothing for a checker to catch."""
    f, w = facts(d), verdicts(d)
    if not w["ok"]:
        return ("The requested specification could not be met by a valid "
                "circuit: the evaluation returned "
                f"{d['nominal'].get('verdict')}.")

    L = [
        f"You asked for {f['requested_peaking_db']:g} dB of high-frequency "
        f"peaking with the peak near {f['requested_f_peak_ghz']:.4g} GHz.",
        "",
        f"The sized stage peaks at {f['peaking_db']:.4g} dB at "
        f"{f['f_peak_ghz']:.4g} GHz, and lifts the response by "
        f"{f['nyquist_boost_db']:.4g} dB at Nyquist -- so it equalises rather "
        f"than merely peaking somewhere below the data band.",
        f"Input-referred noise is {f['noise_mv_rms']:.4g} mV_rms against a "
        f"{f['noise_limit_mv']:g} mV limit, and it draws "
        f"{f['power_mw']:.4g} mW against {f['power_limit_mw']:g} mW.",
        f"The input pair sits {f['pair_margin_v']:.4g} V into saturation and "
        f"the tail {f['tail_margin_v']:.4g} V.",
        "",
        f"Sizing: input pair {f['w_in_um']:.4g} um wide and "
        f"{f['l_in_nm']:.4g} nm long in {f['nf_in']:g} fingers, tail current "
        f"{f['i_bias_ma']:.4g} mA, degeneration {f['rs_ohm']:.4g} ohm with "
        f"{f['cs_pf']:.4g} pF, load {f['rl_ohm']:.4g} ohm, input common mode "
        f"{f['vcm_in_v']:.4g} V.",
        "",
        (f"It cost {f['simulations_total']:g} SPICE simulation"
         + ("s." if f["simulations_total"] != 1 else ".")),
    ]
    if w["method"] == "rl-hybrid":
        L.extend([
            "",
            f"The frozen RL proposer used {f['rl_proposals']:g} eye "
            f"measurements. The simulator-backed shield accepted an "
            f"RL-visited code at {f['rl_shield_selections']:g} conditions; "
            f"the deterministic measured-bank fallback supplied "
            f"{f['shield_fallbacks']:g} conditions.",
        ])
    if w["corner_verified"]:
        if w["method"] == "rl-hybrid":
            L.append(
                f"Across {f['n_channel_losses']:g} characterised channel "
                f"losses and {f['n_corners']:g} process-voltage-temperature "
                f"corners -- {f['corner_points']:g} conditions -- it "
                f"{w['corner_verdict']}.")
        else:
            L.append(
                f"Across {f['n_corners']:g} process-voltage-temperature "
                f"corners at {f['n_loads']:g} loads -- "
                f"{f['corner_points']:g} points -- it {w['corner_verdict']}"
                + (f", failing {f['corner_points_failed']:g} of them, "
                   f"{f['corner_points_failed_unscreened']:g} at corners the "
                   f"three-corner screen never evaluates."
                   if f.get("corner_points_failed") else
                   f", with a worst-case score of "
                   f"{f['worst_corner_reward']:.4g}."))
    else:
        L.append("It has NOT been verified across corners; the search saw one "
                 "corner and one load.")
    L.append("")
    if w["request_scored"]:
        L.append("Note: the requested peaking and peak frequency are both "
                 "scored by the acceptance test; they are not post-processing "
                 "preferences.")
    else:
        L.append("Note: the peaking figure is a BAND requirement, not a target "
                 "the optimiser aims at -- the request is honoured as a "
                 "tie-break among designs that already meet every "
                 "specification.")
    return "\n".join(L)


_SYSTEM = (
    "You explain a transistor-level CTLE equaliser design to an analog "
    "designer. You are given FACTS (measured numbers) and VERDICTS "
    "(judgements already made by the tooling).\n"
    "Explain what was asked for, what the circuit does, how much margin it "
    "has, and whether it was checked across process corners. Be concrete and "
    "brief -- at most two short paragraphs. Do not hedge, do not speculate "
    "about causes, and do not offer improvements.\n"
    "Do NOT decide whether anything passes: the VERDICTS already say so. "
    "Repeat them; never re-derive them.\n\n" + G.prompt_rules()
)


def explain(d: Mapping[str, Any], use_llm: bool = False,
            client: Optional[Any] = None) -> tuple[str, str]:
    """`(text, source)` where source is `"template"` or `"llm"`.

    The LLM path falls back to the template on **any** failure -- no client, no
    key, an API error, or an ungrounded number. The caller always gets prose,
    and it is always made of measured numbers.
    """
    if not use_llm:
        return template(d), "template"
    f, w = facts(d), verdicts(d)
    prompt = ("FACTS (the only numbers you may use):\n"
              + "\n".join(f"  {k} = {v}" for k, v in f.items())
              + "\n\nVERDICTS (already decided; repeat, do not re-derive):\n"
              + "\n".join(f"  {k} = {v}" for k, v in w.items()))
    try:
        text = C.ask_text(prompt, _SYSTEM, client=client)
        return G.check(text, f), "llm"
    except G.UngroundedNumber as exc:
        return (template(d)
                + f"\n\n[the model's wording was discarded: {exc}]",
                "template")
    except Exception as exc:                                # noqa: BLE001
        return (template(d)
                + f"\n\n[the LLM path was unavailable: "
                  f"{exc.__class__.__name__}]",
                "template")


__all__ = ["facts", "verdicts", "template", "explain"]
