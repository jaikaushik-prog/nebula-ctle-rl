"""Entry 101: fresh verification of fixed setting 490, without adoption.

python -m nebula.experiments.exp_fixed_candidate --out <new-directory>
Reuses Entry 100's physical-identity and DFE controls; never switches codes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

from nebula.common.types import all_corners
from nebula.experiments import exp_product_readiness as A
from nebula.report.product_scope import area_inventory


REQUEST = (9.0, 1.9e9)
SETTING = 490


def fixed_candidates(table, request):
    good = set(table.settings)
    for corner in table.corners:
        for loss in table.losses:
            good.intersection_update(table.compliant_settings(corner, loss, *request))
    return sorted(good)


def candidate_design():
    from nebula.rl import hybrid_designer as H
    from nebula.experiments import exp_joint_bank as J, exp_joint_bank_73 as B
    table, _, _, _ = H._load_assets()
    candidates = fixed_candidates(table, REQUEST)
    if candidates != [SETTING]:
        raise ValueError(f"registered fixed candidate membership changed: {candidates}")
    _, _, base_u, _ = B._load_sources()
    bank = J.bank(base_u, n_rs=J.N_RS, n_cs=J.N_CS,
                  rs_span=J.RS_SPAN, cs_span=J.CS_SPAN)
    atten, bank_code = J.split_setting(SETTING)
    u = list(bank[bank_code].u)
    representative_loss = table.losses[len(table.losses) // 2]
    return {
        "method": "fixed-bank-candidate-diagnostic-not-RL-selection",
        "request": {"peaking_db": REQUEST[0], "f_peak_hz": REQUEST[1]},
        "search": {"setting": SETTING, "u": u, "atten_code": atten,
                   "bank_code": bank_code, "atten_max_x": B.PROBE_MAX_X,
                   "representative_channel_loss_db": representative_loss},
        "bank_reference": H._nominal_from_row(table.row(SETTING, "tt/1.00/27C"),
                                               u, representative_loss, REQUEST),
        "channel_losses_db": list(table.losses),
        "adopted": False, "full_product_compliance": False,
    }


def run(out: Path):
    if out.exists():
        raise FileExistsError(f"refusing to overwrite {out}")
    design = candidate_design()
    from nebula.device.sky130_runner import run_point
    from nebula.experiments.adaptive_screen import _attenuation_run_args
    from nebula.experiments.cl_range import committed_cl_range
    from nebula.experiments.runlock import hold, stamp
    from nebula.rl.contract import sizing_from_u
    from nebula.rl.evaluator import build_point
    from nebula.rl.hybrid_designer import _sha256

    out.mkdir(parents=True)
    with hold("fixed_candidate_490", here=out):
        started = time.perf_counter()
        search = design["search"]
        point, _ = build_point(sizing_from_u(search["u"], cl_f=committed_cl_range().cl_mid_f))
        export = run_point(point, "tt", temp_c=27., swing=False, ac_peak_interp=True,
                           keep_netlist=True, nan_retry_bypass_f=None,
                           **_attenuation_run_args(search["atten_code"], search["atten_max_x"]))
        if not export.ok or not export.netlist:
            raise RuntimeError(f"candidate export failed: {export.fail_reason}")
        deck = export.netlist
        (out / "design.cir").write_text(deck, encoding="utf-8")
        (out / "candidate.json").write_text(json.dumps(design, indent=2), encoding="utf-8")
        provenance = {**stamp(), "runner_sha256": _sha256(Path(__file__)),
                      "shared_audit_sha256": _sha256(Path(A.__file__)),
                      "plan_sha256": _sha256(Path(__file__).resolve().parents[1] / "FIXED_490_PLAN.md"),
                      "candidate_sha256": _sha256(out / "candidate.json"),
                      "deck_sha256": _sha256(out / "design.cir")}
        (out / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
        (out / "area_inventory.json").write_text(json.dumps(area_inventory(deck), indent=2), encoding="utf-8")
        rows = []
        losses = design["channel_losses_db"]
        with (out / "fixed_pvt.jsonl").open("x", encoding="utf-8") as journal:
            for corner in all_corners():
                row = A.measure_fixed(design, deck, corner, losses)
                rows.append(row)
                journal.write(json.dumps(row, allow_nan=False) + "\n")
                journal.flush()
                print(f"490 fixed PVT {len(rows)}/45: {row['corner']}; "
                      f"{sum(p['model_pass'] for p in row['links'])}/{len(losses)} model passes", flush=True)
        summary = {"provenance": provenance, "spice_calls": 1 + sum(r["spice_calls"] for r in rows),
                   "fixed": A.summarise_fixed(rows, losses, search["representative_channel_loss_db"]),
                   "wall_s": time.perf_counter() - started, "adopted": False}
        (out / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False), encoding="utf-8")
        print(json.dumps(summary["fixed"], indent=2), flush=True)
        return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    result = run(parser.parse_args().out)
    fixed = result["fixed"]
    return 0 if fixed["n_model_pass"] == fixed["n_expected_conditions"] and fixed["dfe_control_all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
