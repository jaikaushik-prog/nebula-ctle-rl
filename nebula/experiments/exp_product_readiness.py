"""Entry 100: audit one exported circuit, never retune it or retrain the RL.

Run: python -m nebula.experiments.exp_product_readiness --out <new-directory>
Writes an exclusive journal and source hashes. A failed model is a result, not
a reason to swap settings. Full area/receiver implementation remain unverified.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import json
import math
from pathlib import Path
import time

import numpy as np

from nebula.common.types import all_corners, SPEC_EYE_H_MIN_V, SPEC_EYE_W_MIN_UI
from nebula.report.product_scope import area_inventory, circuit_signature


REQUESTS = tuple((p, f) for p in (3.0, 6.0, 9.0, 12.0)
                 for f in (1.25e9, 1.9e9, 2.5e9))
DEMO = Path(__file__).resolve().parents[1] / "product_demo/rl_hybrid_9db_1p9ghz"


def control_matches(ideal, height, width) -> bool:
    return all(math.isfinite(float(x)) for x in (height, width, ideal.eye_h_v, ideal.eye_w_ui)) and (
        abs(ideal.eye_h_v - height) <= 1e-9 and abs(ideal.eye_w_ui - width) <= 1e-9)


def _label(c):
    from nebula.experiments.exp_joint_bank import _corner_label
    return _corner_label(c)


def measure_fixed(design: dict, deck: str, corner, losses) -> dict:
    """Same sizing and attenuator at every corner; two HD3 tones, one AC model."""
    from nebula.device.sky130_runner import run_point, HD3_TONE_HZ, HD3_VIN_DIFF_PK_V
    from nebula.experiments.adaptive_screen import _attenuation_run_args
    from nebula.link.bridge import device_result_from_point, evaluate_link
    from nebula.link.channel import DEFAULT_OSR
    from nebula.link.config import LinkConfig
    from nebula.link.cursors import pulse_response
    from nebula.link import dfe_ablation as DFE
    from nebula.report.schematic import params_of
    from nebula.rl import reward_v1 as R
    from nebula.rl.contract import sizing_from_u, f_peak_octaves
    from nebula.rl.evaluator import build_point, annotate_interpolated_peak, scored_meas, validate, Verdict

    search, request = design["search"], design["request"]
    sizing = sizing_from_u(np.asarray(search["u"]), cl_f=params_of(deck)["CL"])
    point, _ = build_point(sizing, corner=corner.process, vdd_scale=corner.vdd_scale)
    cfg = LinkConfig(channel_loss_db_at_nyquist=losses[0])
    args = _attenuation_run_args(search["atten_code"], search["atten_max_x"])
    pt = run_point(point, corner.process, temp_c=corner.temp_c, swing=True,
                   ac_sweep=True, hd3=True, ac_peak_interp=True, keep_netlist=True,
                   hd3_vin_pk_v=.5 * cfg.v_in_diff_pp_v, hd3_tone_hz=cfg.nyquist_hz,
                   nan_retry_bypass_f=None, **args)
    # Match the existing S4 checklist's standard drive, not an invented amplitude.
    s4 = run_point(point, corner.process, temp_c=corner.temp_c, hd3=True, swing=False,
                   hd3_tone_hz=HD3_TONE_HZ, hd3_vin_pk_v=HD3_VIN_DIFF_PK_V,
                   keep_netlist=True, nan_retry_bypass_f=None, **args)
    base = {"corner": _label(corner), "setting": search["setting"], "spice_calls": 2,
            "hd3_100mhz_dbc": s4.hd3_dbc if s4.ok else None,
            "s4_reason": s4.fail_reason if not s4.ok else None, "links": []}
    if not pt.netlist or not s4.netlist:
        raise RuntimeError("runner did not preserve the circuit for identity verification")
    signature = circuit_signature(deck)
    if any(circuit_signature(d) != signature for d in (pt.netlist, s4.netlist)):
        raise RuntimeError(f"fixed circuit changed at {_label(corner)}; refusing attribution")
    base["circuit_signature"] = signature
    verdict, reason = validate(pt, point)
    dev = device_result_from_point(pt)
    if verdict is Verdict.INVALID or not dev.ok:
        base.update(ok=False, reason=reason or dev.fail_reason)
        return base
    meas = {"g_dc_db": dev.g_dc_db, "peaking_db": dev.peaking_db,
            "f_peak_oct": f_peak_octaves(dev.f_peak_hz),
            "nyq_boost_db": pt.nyquist_boost_db, "inoise_vrms": dev.vn_in_vrms,
            "power_w": dev.power_w, "pair_margin_v": pt.vds - pt.vdsat,
            "tail_margin_v": pt.tail_margin_v}
    annotate_interpolated_peak(meas, None, pt)
    meas = scored_meas(meas, True)
    base.update(ok=True, meas=meas, hd3_nyq_dbc=dev.hd3_dbc,
                legacy_passive_area_mm2=dev.area_mm2)
    for loss in losses:
        cfg = LinkConfig(channel_loss_db_at_nyquist=loss)
        detail = []
        link = evaluate_link(dev, cfg, detail=detail)
        margins = R.margins(meas, request["f_peak_hz"], target_peaking_db=request["peaking_db"],
                            link=link if link.ok else None, area_mm2=dev.area_mm2,
                            hd3_dbc=base["hd3_100mhz_dbc"], hd3_nyq_dbc=dev.hd3_dbc)
        specs = tuple(dict.fromkeys((*R.V6_SPECS, "S4_hd3")))
        missing = [s for s in specs if s not in margins]
        shortfalls = R.shortfalls(margins, tuple(s for s in specs if s in margins))
        failed = [s for s, value in shortfalls.items() if value != 0.0]
        row = {"loss_db": loss, "ok": link.ok, "reason": link.fail_reason if not link.ok else None,
               "model_pass": not missing and not failed,
               "margins": {s: margins[s] for s in specs if s in margins},
               "failed_specs": failed, "unmeasured_specs": missing, "policies": {},
               "control_pass": False}
        if link.ok and detail:
            pr = pulse_response(cfg.channel, cfg.tx, detail[0].ctle)
            eyes = DFE.all_policies(pr, DEFAULT_OSR, int(np.argmax(pr)))
            row.update(bridge_eye_h_v=link.eye_h_v, bridge_eye_w_ui=link.eye_w_ui,
                       policies={k: asdict(v) for k, v in eyes.items()},
                       control_pass=control_matches(eyes["ideal"], link.eye_h_v, link.eye_w_ui))
        base["links"].append(row)
    return base


def summarise_fixed(rows, losses, representative_loss):
    expected = {_label(c) for c in all_corners()}
    if len(rows) != len(expected) or {r["corner"] for r in rows} != expected:
        raise ValueError("fixed PVT membership must contain exactly all 45 corners")
    if len({r["setting"] for r in rows}) != 1 or len({r["circuit_signature"] for r in rows}) != 1:
        raise ValueError("fixed audit changed its setting/circuit")
    if any(r["ok"] and (len(r["links"]) != len(losses) or
           {p["loss_db"] for p in r["links"]} != set(losses)) for r in rows):
        raise ValueError("fixed link membership mismatch")
    links = [dict(p, corner=r["corner"]) for r in rows for p in r["links"]]
    failures = Counter(s for p in links for s in (*p["failed_specs"], *p["unmeasured_specs"]))
    control_ok = (len(links) == len(rows) * len(losses) and all(p["control_pass"] for p in links))
    policies = {}
    from nebula.link.dfe_ablation import POLICIES
    for policy in POLICIES:
        valid = [(p, p["policies"][policy]) for p in links if p["control_pass"]]
        policies[policy] = {
            "n_valid_control": len(valid), "n_expected": len(rows) * len(losses),
            "n_eye_pass": sum(e["eye_h_v"] > SPEC_EYE_H_MIN_V and e["eye_w_ui"] > SPEC_EYE_W_MIN_UI
                              for _, e in valid),
            "min_eye_h_v": min((e["eye_h_v"] for _, e in valid), default=None),
            "min_eye_w_ui": min((e["eye_w_ui"] for _, e in valid), default=None),
            "all_eyes_pass": control_ok and all(e["eye_h_v"] > SPEC_EYE_H_MIN_V and
                                               e["eye_w_ui"] > SPEC_EYE_W_MIN_UI for _, e in valid),
        }
    return {"setting": rows[0]["setting"], "n_corners": len(rows),
            "n_invalid_corners": sum(not r["ok"] for r in rows),
            "n_expected_conditions": len(rows) * len(losses),
            "n_model_pass": sum(p["model_pass"] for p in links),
            "representative_loss_db": representative_loss,
            "n_representative_pvt_pass": sum(p["model_pass"] for p in links if p["loss_db"] == representative_loss),
            "failed_spec_counts": dict(failures), "dfe_control_all_pass": control_ok,
            "dfe_policies": policies, "full_product_compliance": False,
            "note": "Fixed code, 45 PVT corners, one load, seven constructed channels. "
                    "Model pass still uses partial passive area and behavioural eyes; not full silicon compliance."}


def audit_requests(table, net, starts, journal):
    from nebula.rl import hybrid_designer as H
    results = []
    for request in REQUESTS:
        records = []
        start = starts[H._nearest_request(request, tuple(starts))]
        for loss, corner in H.verification_conditions(table, table.losses):
            trace = H.trace_policy(net, lambda s: table.observe(s, corner, loss), request, start)
            selected = H.select_with_bank_fallback(table, (corner, loss, *request), trace.settings_tried)
            row = table.row(selected.setting, corner)
            records.append({"corner": corner, "loss_db": loss, "setting": selected.setting,
                            "compliant": selected.compliant, "source": selected.source,
                            "reason": selected.reason,
                            "peaking_error_db": float(row.peaking_db) - request[0] if row.ok else None,
                            "frequency_error_oct": float(row.f_peak_oct) - H.f_peak_octaves(request[1]) if row.ok else None})
        accepted = [r for r in records if r["compliant"]]
        nominal = next(r for r in records if r["corner"] == "tt/1.00/27C" and r["loss_db"] == table.losses[len(table.losses)//2])
        result = {"target_peaking_db": request[0], "target_f_peak_hz": request[1],
                  "n_conditions": len(records), "n_compliant": len(accepted),
                  "product_deliverable_under_current_model": len(accepted) == len(records),
                  "max_accepted_abs_peaking_error_db": max((abs(r["peaking_error_db"]) for r in accepted), default=None),
                  "max_accepted_abs_frequency_error_oct": max((abs(r["frequency_error_oct"]) for r in accepted), default=None),
                  "nominal": nominal, "per_condition": records}
        journal.write(json.dumps(result, allow_nan=False) + "\n")
        journal.flush()
        results.append(result)
        print(f"request {len(results)}/{len(REQUESTS)}: {request[0]:g} dB, {request[1]/1e9:g} GHz: "
              f"{len(accepted)}/{len(records)} model conditions", flush=True)
    return results


def run(out: Path, demo: Path = DEMO):
    from nebula.experiments import exp_shielded_ppo as E89
    from nebula.experiments.runlock import hold, stamp
    from nebula.rl import hybrid_designer as H
    from nebula.device.sky130_runner import HD3_TONE_HZ, HD3_VIN_DIFF_PK_V

    if out.exists():
        raise FileExistsError(f"refusing to overwrite audit directory: {out}")
    table, net, starts, manifest = H._load_assets()
    design = json.loads((demo / "design.json").read_text(encoding="utf-8"))
    deck = (demo / "design.cir").read_text(encoding="utf-8")
    losses = table.losses
    out.mkdir(parents=True)
    with hold("product_readiness", here=out):
        t0 = time.perf_counter()
        provenance = {**stamp(), "design_json_sha256": H._sha256(demo / "design.json"),
                      "deck_file_sha256": H._sha256(demo / "design.cir"),
                      "runner_sha256": H._sha256(Path(__file__)),
                      "plan_sha256": H._sha256(Path(__file__).resolve().parents[1] / "PRODUCT_READINESS_PLAN.md"),
                      "table_decoded_sha256": E89.SOURCE_SHA256,
                      "policy_manifest_sha256": H._sha256(E89.policy_manifest_path()),
                      "s4_tone_hz": HD3_TONE_HZ, "s4_vin_diff_peak_v": HD3_VIN_DIFF_PK_V,
                      "scope": "Entry 100 product diagnostic; no training, FINAL evaluation or topology changes"}
        (out / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
        # Preserve hashed inputs even if the demo later gains reporting metadata.
        (out / "source_design.json").write_bytes((demo / "design.json").read_bytes())
        (out / "source_design.cir").write_bytes((demo / "design.cir").read_bytes())
        inventory = area_inventory(deck)
        (out / "area_inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
        fixed = []
        with (out / "fixed_pvt.jsonl").open("x", encoding="utf-8") as journal:
            for corner in all_corners():
                row = measure_fixed(design, deck, corner, losses)
                fixed.append(row)
                journal.write(json.dumps(row, allow_nan=False) + "\n")
                journal.flush()
                print(f"fixed circuit {len(fixed)}/45: {_label(corner)}; "
                      f"{sum(p['model_pass'] for p in row['links'])}/{len(losses)} model passes", flush=True)
        fixed_summary = summarise_fixed(fixed, losses, design["search"]["representative_channel_loss_db"])
        with (out / "request_accuracy.jsonl").open("x", encoding="utf-8") as journal:
            requests = audit_requests(table, net, starts, journal)
        summary = {"provenance": provenance, "spice_calls": sum(r["spice_calls"] for r in fixed),
                   "fixed": fixed_summary,
                   "accuracy": [{k: v for k, v in r.items() if k != "per_condition"} for r in requests],
                   "wall_s": time.perf_counter() - t0}
        (out / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False), encoding="utf-8")
        print(json.dumps(fixed_summary, indent=2), flush=True)
        return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.out)
    # Refuse to call a finished-but-failing fixed circuit a successful gate.
    fixed = result["fixed"]
    return 0 if fixed["n_model_pass"] == fixed["n_expected_conditions"] and fixed["dfe_control_all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
