"""Entry 113: enumerated coverage using the unchanged physical product."""
from __future__ import annotations
import argparse
import hashlib
import json
import time
from pathlib import Path

from nebula import physical_design as D
from nebula.rl import hybrid_designer as H
from nebula.experiments.exp_post_review_attribution import frozen_plan, sha

REQUESTS = tuple((p, f) for p in (3., 6., 9., 12.)
                 for f in (1.25e9, 1.9e9, 2.5e9))
MAX_CALLS = 137 * len(REQUESTS)


def brief_response(meas):
    pk, octaves = meas.get("peaking_db"), meas.get("f_peak_oct")
    if pk is None or octaves is None:
        return None
    f = 2.5e9 * 2 ** octaves
    return bool(3 <= pk <= 12 and 1.25e9 <= f <= 2.5e9)


def run(out):
    protocol = frozen_plan()
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    load_started = time.perf_counter()
    table = H._load_assets()[0]
    table_load_s = time.perf_counter() - load_started
    rows, calls = [], 0
    with (out / "coverage.jsonl").open("x", encoding="utf-8") as journal:
        for peaking, frequency in REQUESTS:
            row = dict(peaking_db=peaking, f_peak_hz=frequency, full_product_compliance=False)
            tick = time.perf_counter()
            try:
                selected, eligible, checks = D.select_fixed_setting(
                    table, (peaking, frequency), -1, list(table.losses))
                row.update(classical_setting=selected, eligible=eligible,
                           classical_rows_checked=checks)
            except RuntimeError as exc:
                row.update(status="BANK_NO_FIXED", reason=str(exc), spice_calls=0)
            row["classical_selection_s"] = time.perf_counter() - tick
            if row.get("status") != "BANK_NO_FIXED":
                folder = out / f"p{peaking:g}_f{frequency/1e9:g}"
                try:
                    result = D.run(peaking, frequency, evidence_dir=folder,
                        progress=lambda message, percent: print(message, flush=True))
                    count = result["simulations"]["total"]
                    row.update(status="MODEL_PASS" if D.is_verified(result) else "MODEL_FAIL",
                               spice_calls=count, physical_wall_s=result["wall_s"],
                               selected=result["search"]["setting"],
                               same_selection_without_rl=selected == result["search"]["setting"],
                               singleton_intersection=len(eligible) == 1,
                               nominal=result["nominal"],
                               verification=result["verification"],
                               final_search=result["search"])
                    raw = [json.loads(x) for x in (folder / "fixed_pvt.jsonl").read_text().splitlines()]
                    absolute = [brief_response(r.get("meas", {})) for r in raw]
                    row.update(absolute_response_points=len(absolute),
                               absolute_response_pass=sum(v is True for v in absolute),
                               absolute_response_unknown=sum(v is None for v in absolute),
                               circuit_signatures=sorted({r["circuit_signature"] for r in raw}))
                except Exception as exc:
                    failure = folder / "failure.json"
                    detail = json.loads(failure.read_text()) if failure.exists() else {}
                    row.update(status="RUN_FAILED", reason=f"{type(exc).__name__}: {exc}",
                               spice_calls=detail.get("spice_calls", 0))
                calls += row["spice_calls"]
                if calls > MAX_CALLS:
                    raise RuntimeError("registered total SPICE budget exceeded")
            rows.append(row)
            journal.write(json.dumps(row, allow_nan=False) + "\n")
            journal.flush()
            print(f"TARGET {peaking:g} dB {frequency/1e9:g} GHz: {row['status']}", flush=True)
    result = dict(status="POST_REVIEW_PHYSICAL_COVERAGE", requests=rows,
                  protocol_sha256=protocol, spice_calls=calls,
                  wall_s=time.perf_counter()-started, table_load_s=table_load_s,
                  n_requests=len(rows), full_product_compliance=False,
                  caveats=["Generic resistor voltage dependence omitted by ngspice.",
                           "Fixed generated geometries; no physical Rs/Cs switching.",
                           "Classical selection time excludes table loading and fresh verification.",
                           "Project request tolerances and absolute brief bounds are reported separately."])
    (out / "summary.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    (out / "sha256.json").write_text(json.dumps(
        {str(p.relative_to(out)): sha(p) for p in out.rglob("*") if p.is_file()}, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    run(parser.parse_args().out)

