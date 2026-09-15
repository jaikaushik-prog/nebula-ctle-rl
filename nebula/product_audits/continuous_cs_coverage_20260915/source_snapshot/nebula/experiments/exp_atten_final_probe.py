"""Entry 85: one 7.3 dB measurement at the final compression boundary.

The probe changes only the maximum attenuation ratio at the one registered
entry-84 failure.  Passing all six gates closes the focused 16-case diagnosis;
it does not adopt the range or authorise a full PVT sweep.

    python -m nebula.experiments.exp_atten_final_probe --run
    python -m nebula.experiments.exp_atten_final_probe --analyse
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from nebula.common.types import SPEC_VN_IN_MAX_VRMS
from nebula.experiments import exp_atten_range_probe as A
from nebula.experiments.exp_coverage import FREQ_REQUESTS, PEAKING_REQUESTS

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "atten_cs_probe_results.json"
RESULTS = HERE / "atten_final_probe_results.json"
SOURCE_SHA256 = "BAECB4621818D80B71BFC9CF1977EF81E71A02BB3026CF67211123FCFFA204C5"
ROOT_SOURCE_SHA256 = "9A06AA65D71B463D4F75CC2072D82BC845799BAF6FE073F66C25C069ED2F358B"

PROBE_TOP_DB: float = 7.3
PROBE_MAX_X: float = 10.0 ** (PROBE_TOP_DB / 20.0)
ATTEN_CODE: int = 7
BANK_CODE: int = 50
REQUEST_ID: int = 12
CORNER_LABEL: str = "sf/0.95/125C"
OLD_PROBE_TOP_DB: float = 7.0


@dataclass(frozen=True)
class FinalTask:
    corner_label: str
    request_id: int
    target_peaking_db: float
    target_f_peak_hz: float
    bank_code: int
    atten_code: int
    old_g_dc_db: float


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _request(request_id: int) -> tuple[float, float]:
    requests = [(float(peaking), float(freq))
                for peaking in PEAKING_REQUESTS for freq in FREQ_REQUESTS]
    try:
        return requests[int(request_id)]
    except IndexError as exc:
        raise ValueError(f"unknown request_id {request_id}") from exc


def task_from_source(source: dict) -> FinalTask:
    """Select exactly entry 84's registered compression-only boundary row."""
    if source.get("source_sha256") != ROOT_SOURCE_SHA256:
        raise ValueError("entry-84 root source hash changed")
    if float(source.get("probe_top_db", float("nan"))) != OLD_PROBE_TOP_DB:
        raise ValueError("entry-84 attenuator range changed")

    matches = [
        row for row in source.get("rows", [])
        if str(row.get("corner")) == CORNER_LABEL
        and int(row.get("request_id", -1)) == REQUEST_ID
        and int(row.get("bank_code", -1)) == BANK_CODE
        and int(row.get("atten_code", -1)) == ATTEN_CODE
    ]
    if len(matches) != 1:
        raise ValueError("expected exactly one registered entry-84 row")
    row = matches[0]
    if not row.get("device_ok"):
        raise ValueError("registered entry-84 device row is invalid")
    short_link = (row.get("links") or {}).get("3.0") or {}
    if short_link.get("ok") or short_link.get("reason") != "compression":
        raise ValueError("registered entry-84 row is not a compression failure")
    requests = row.get("requests") or []
    if (len(requests) != 1
            or int(requests[0].get("request_id", -1)) != REQUEST_ID
            or requests[0].get("scorable")
            or requests[0].get("compliant")):
        raise ValueError("registered entry-84 request state changed")
    if not (row.get("links") or {}).get("12.0", {}).get("ok"):
        raise ValueError("registered entry-84 12 dB control is not scorable")
    old_g_dc_db = row.get("g_dc_db")
    if old_g_dc_db is None:
        raise ValueError("registered entry-84 DC gain is unavailable")

    target_peaking_db, target_f_peak_hz = _request(REQUEST_ID)
    return FinalTask(
        corner_label=CORNER_LABEL,
        request_id=REQUEST_ID,
        target_peaking_db=target_peaking_db,
        target_f_peak_hz=target_f_peak_hz,
        bank_code=BANK_CODE,
        atten_code=ATTEN_CODE,
        old_g_dc_db=float(old_g_dc_db),
    )


def _key(row: dict) -> tuple[str, int, int, int]:
    return (str(row.get("corner")), int(row.get("request_id", -1)),
            int(row.get("bank_code", -1)), int(row.get("atten_code", -1)))


def analyse(rows: Sequence[dict], wall_clock_s: float = 0.0) -> dict:
    rows = list(rows)
    expected = (CORNER_LABEL, REQUEST_ID, BANK_CODE, ATTEN_CODE)
    membership_ok = len(rows) == 1 and _key(rows[0]) == expected
    row = rows[0] if membership_ok else {}
    all_device_ok = bool(membership_ok and row.get("device_ok"))

    old_gain = row.get("old_g_dc_db")
    new_gain = row.get("g_dc_db")
    gain_reduction = (float(old_gain) - float(new_gain)
                      if old_gain is not None and new_gain is not None
                      else None)
    requests = row.get("requests") or []
    request_ok = bool(
        len(requests) == 1
        and int(requests[0].get("request_id", -1)) == REQUEST_ID
        and requests[0].get("scorable")
        and requests[0].get("compliant")
        and not requests[0].get("violations")
    )
    links = row.get("links") or {}
    short_ok = bool(links.get("3.0", {}).get("ok"))
    long_ok = bool(links.get("12.0", {}).get("ok"))
    noise = row.get("noise_mvrms")

    checks = {
        "Q1": bool(membership_ok and all_device_ok),
        "Q2": bool(gain_reduction is not None
                   and 0.20 <= gain_reduction <= 0.40),
        "Q3": bool(short_ok and request_ok),
        "Q4": long_ok,
        "Q5": bool(noise is not None
                   and float(noise) < SPEC_VN_IN_MAX_VRMS * 1e3),
        "Q6": bool(float(wall_clock_s) < 10.0),
    }
    return {
        "membership_ok": membership_ok,
        "all_device_ok": all_device_ok,
        "n_rows": len(rows),
        "dc_gain_reduction_db": gain_reduction,
        "short_channel_scorable": short_ok,
        "request_compliant": request_ok,
        "long_channel_scorable": long_ok,
        "noise_mvrms": noise,
        "wall_clock_s": float(wall_clock_s),
        "checks": checks,
        "passed": all(checks.values()),
    }


def run() -> dict:
    if RESULTS.exists():
        raise FileExistsError(f"refusing to overwrite {RESULTS.name}")
    if not SOURCE.exists():
        raise FileNotFoundError(f"source artifact missing: {SOURCE}")
    source_hash = _sha256(SOURCE)
    if source_hash != SOURCE_SHA256:
        raise ValueError("entry-84 source artifact hash changed")
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    task = task_from_source(source)

    root_source = HERE / str(source["source"])
    if not root_source.exists():
        raise FileNotFoundError(f"entry-83 source artifact missing: {root_source}")
    root_source_hash = _sha256(root_source)
    if root_source_hash != ROOT_SOURCE_SHA256:
        raise ValueError("entry-83 source artifact hash changed")
    root = json.loads(root_source.read_text(encoding="utf-8"))
    base_u = tuple(float(value) for value in root["base_u"])

    request = ((task.request_id, task.target_peaking_db,
                task.target_f_peak_hz),)
    t0 = time.perf_counter()
    row = A._measure(
        base_u, task.bank_code, A._parse_corner(task.corner_label),
        task.atten_code, "final_probe", request,
        atten_max_x=PROBE_MAX_X)
    elapsed = time.perf_counter() - t0
    row.update({
        "request_id": task.request_id,
        "old_g_dc_db": task.old_g_dc_db,
    })
    rows = [row]
    summary = analyse(rows, wall_clock_s=elapsed)
    out = {
        "task": "entry 85 final 7.3 dB compression-boundary probe",
        "source": SOURCE.name,
        "source_sha256": source_hash,
        "root_source": root_source.name,
        "root_source_sha256": root_source_hash,
        "probe_top_db": PROBE_TOP_DB,
        "probe_max_x": PROBE_MAX_X,
        "production_atten_max_x_unchanged": A.AT.ATTEN_MAX_X,
        "production_top_db_unchanged": A.AT.attenuation_db(A.AT.N_CODES - 1),
        "spice_invocations": len(rows),
        "rows": rows,
        "summary": summary,
        "scope": ("one focused diagnostic; no production-range change, "
                  "full-PVT coverage claim, full-table run or RL training"),
    }
    RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def _report(out: dict) -> None:
    summary = out["summary"]
    print()
    print("=" * 72)
    print("ENTRY 85 - FINAL 7.3 dB BOUNDARY PROBE")
    print("=" * 72)
    print(f"  SPICE rows: {out['spice_invocations']}  "
          f"device valid: {summary['all_device_ok']}")
    print(f"  DC-gain reduction: {summary['dc_gain_reduction_db']!r} dB")
    print(f"  3 dB request compliant: {summary['request_compliant']}")
    print(f"  12 dB link scorable: {summary['long_channel_scorable']}")
    print(f"  noise: {summary['noise_mvrms']!r} mVrms")
    print(f"  elapsed: {summary['wall_clock_s']:.2f} s")
    for name, passed in summary["checks"].items():
        print(f"  {name}: {'PASS' if passed else 'FAIL'}")
    print(f"  OVERALL: {'PASS' if summary['passed'] else 'FAIL'}")
    print("  Scope: focused diagnostic only; D11 remains unchanged.")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--analyse", action="store_true")
    args = parser.parse_args(argv)
    if args.run:
        out = run()
    elif args.analyse:
        if not RESULTS.exists():
            raise SystemExit(f"{RESULTS.name} missing: run --run first")
        out = json.loads(RESULTS.read_text(encoding="utf-8"))
    else:
        parser.print_help()
        return 0
    _report(out)
    return 0 if out["summary"]["passed"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
