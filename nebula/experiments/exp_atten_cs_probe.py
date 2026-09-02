"""Entry 84: test the adjacent higher-Cs code at three frequency misses.

This probe keeps entry 83's 7 dB compression candidate fixed.  It changes only
the CTLE bank from C1 to C2 at the three fully-scorable rows whose peak was
slightly too high.

    python -m nebula.experiments.exp_atten_cs_probe --run
    python -m nebula.experiments.exp_atten_cs_probe --analyse
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
SOURCE = HERE / "atten_range_probe_results.json"
RESULTS = HERE / "atten_cs_probe_results.json"
SOURCE_SHA256 = "9A06AA65D71B463D4F75CC2072D82BC845799BAF6FE073F66C25C069ED2F358B"
EXPECTED_ROWS: tuple[tuple[str, int, int, int], ...] = (
    ("ff/0.95/125C", 12, 49, 50),
    ("sf/0.95/0C", 13, 41, 42),
    ("sf/0.95/125C", 12, 49, 50),
)


@dataclass(frozen=True)
class CsTask:
    corner_label: str
    request_id: int
    target_peaking_db: float
    target_f_peak_hz: float
    old_bank_code: int
    new_bank_code: int
    old_f_peak_hz: float

    @property
    def i_rs(self) -> int:
        return self.old_bank_code // A.N_CS

    @property
    def old_i_cs(self) -> int:
        return self.old_bank_code % A.N_CS

    @property
    def new_i_cs(self) -> int:
        return self.new_bank_code % A.N_CS


def _request(request_id: int) -> tuple[float, float]:
    requests = [(float(peaking), float(freq))
                for peaking in PEAKING_REQUESTS for freq in FREQ_REQUESTS]
    try:
        return requests[int(request_id)]
    except IndexError as exc:
        raise ValueError(f"unknown request_id {request_id}") from exc


def tasks_from_source(source: dict) -> list[CsTask]:
    """Select only entry 83's scorable, frequency-only C1 misses."""
    tasks = []
    seen = set()
    for row in source.get("rows", []):
        if row.get("kind") != "critical":
            continue
        for request in row.get("requests", []):
            if request.get("compliant"):
                continue
            key = (str(row["corner"]), int(request["request_id"]))
            if key in seen:
                raise ValueError(f"duplicate source corner/request {key}")
            seen.add(key)
            if not request.get("scorable"):
                raise ValueError(f"source request {key} is not scorable")
            if request.get("violations") != ["S3_f_peak_match"]:
                raise ValueError("entry 84 accepts only S3_f_peak_match misses")
            if not (row.get("links") or {}).get("3.0", {}).get("ok"):
                raise ValueError(f"source request {key} has no scorable 3 dB link")
            old_bank = int(row["bank_code"])
            old_i_cs = old_bank % A.N_CS
            if old_i_cs != 1:
                raise ValueError(f"source request {key} is not at C1")
            target_peaking, target_freq = _request(int(request["request_id"]))
            tasks.append(CsTask(
                corner_label=str(row["corner"]),
                request_id=int(request["request_id"]),
                target_peaking_db=target_peaking,
                target_f_peak_hz=target_freq,
                old_bank_code=old_bank, new_bank_code=old_bank + 1,
                old_f_peak_hz=float(row["f_peak_hz"])))
    return sorted(tasks, key=lambda task: (task.corner_label, task.request_id))


def _key(row: dict) -> tuple[str, int, int, int]:
    return (str(row.get("corner")), int(row.get("request_id", -1)),
            int(row.get("old_bank_code", -1)), int(row.get("bank_code", -1)))


def analyse(rows: Sequence[dict], expected_rows: int = len(EXPECTED_ROWS),
            wall_clock_s: float = 0.0) -> dict:
    rows = list(rows)
    keys = [_key(row) for row in rows]
    membership_ok = len(rows) == expected_rows and len(keys) == len(set(keys))
    all_device_ok = membership_ok and all(row.get("device_ok") for row in rows)
    lowered = sum(
        row.get("f_peak_hz") is not None
        and float(row["f_peak_hz"]) < float(row["old_f_peak_hz"])
        for row in rows)
    recovered = sum(
        len(row.get("requests", [])) == 1
        and int(row["requests"][0].get("request_id", -1))
        == int(row.get("request_id", -2))
        and row["requests"][0].get("scorable")
        and row["requests"][0].get("compliant")
        for row in rows)
    long_ok = sum(bool((row.get("links") or {}).get("12.0", {}).get("ok"))
                  for row in rows)
    noise_ok = sum(row.get("noise_mvrms") is not None
                   and float(row["noise_mvrms"])
                   < SPEC_VN_IN_MAX_VRMS * 1e3 for row in rows)
    checks = {
        "Q1": bool(membership_ok and all_device_ok),
        "Q2": bool(lowered == expected_rows),
        "Q3": bool(recovered == expected_rows),
        "Q4": bool(long_ok == expected_rows),
        "Q5": bool(noise_ok == expected_rows),
        "Q6": bool(float(wall_clock_s) < 15.0),
    }
    return {
        "membership_ok": membership_ok, "all_device_ok": all_device_ok,
        "n_rows": len(rows), "frequency_lowered": int(lowered),
        "requests_recovered": int(recovered),
        "long_channel_scorable": int(long_ok), "noise_pass": int(noise_ok),
        "wall_clock_s": float(wall_clock_s), "checks": checks,
        "passed": all(checks.values()),
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def run() -> dict:
    if RESULTS.exists():
        raise FileExistsError(f"refusing to overwrite {RESULTS.name}")
    if not SOURCE.exists():
        raise FileNotFoundError(f"source artifact missing: {SOURCE}")
    source_hash = _sha256(SOURCE)
    if source_hash != SOURCE_SHA256:
        raise ValueError("entry-83 source artifact hash changed")
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    tasks = tasks_from_source(source)
    actual = tuple((task.corner_label, task.request_id, task.old_bank_code,
                    task.new_bank_code) for task in tasks)
    if actual != EXPECTED_ROWS:
        raise ValueError(f"entry-84 task membership changed: {actual!r}")

    base_u = tuple(float(value) for value in source["base_u"])
    t0 = time.perf_counter()
    rows = []
    for index, task in enumerate(tasks, 1):
        request = ((task.request_id, task.target_peaking_db,
                    task.target_f_peak_hz),)
        row = A._measure(base_u, task.new_bank_code,
                         A._parse_corner(task.corner_label),
                         A.PROBE_ATTEN_CODE, "cs_probe", request)
        row.update({
            "request_id": task.request_id,
            "old_bank_code": task.old_bank_code,
            "old_f_peak_hz": task.old_f_peak_hz,
        })
        rows.append(row)
        print(f"  C2 probe {index}/{len(tasks)}: {task.corner_label} "
              f"bank {task.old_bank_code}->{task.new_bank_code}", flush=True)
    elapsed = time.perf_counter() - t0
    summary = analyse(rows, wall_clock_s=elapsed)
    out = {
        "task": "entry 84 adjacent-Cs correction at three frequency misses",
        "source": SOURCE.name, "source_sha256": source_hash,
        "probe_top_db": A.PROBE_TOP_DB, "probe_max_x": A.PROBE_MAX_X,
        "spice_invocations": len(rows), "rows": rows, "summary": summary,
        "scope": ("three focused C1-to-C2 measurements; no production-range "
                  "change, full-PVT coverage claim or RL training"),
    }
    RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def _report(out: dict) -> None:
    summary = out["summary"]
    print()
    print("=" * 72)
    print("ENTRY 84 - ADJACENT Cs CLOSURE PROBE")
    print("=" * 72)
    print(f"  rows: {summary['n_rows']}")
    print(f"  frequency moved lower: {summary['frequency_lowered']}/"
          f"{summary['n_rows']}")
    print(f"  3 dB requests recovered: {summary['requests_recovered']}/"
          f"{summary['n_rows']}")
    print(f"  12 dB links scorable: {summary['long_channel_scorable']}/"
          f"{summary['n_rows']}")
    print(f"  noise rows passing: {summary['noise_pass']}/{summary['n_rows']}")
    print(f"  elapsed: {summary['wall_clock_s']:.2f} s")
    for name, passed in summary["checks"].items():
        print(f"  {name}: {'PASS' if passed else 'FAIL'}")
    print(f"  OVERALL: {'PASS' if summary['passed'] else 'FAIL'}")


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
