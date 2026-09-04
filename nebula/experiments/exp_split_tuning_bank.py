"""Entry 96 anti-clobber runner for the split tuning-bank block."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Sequence

from nebula.device.split_tuning_bank import BankRow, assess, run_bank

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "split_tuning_bank_results.json"


def _git_head() -> str:
    proc = subprocess.run(["git", "rev-parse", "HEAD"],
                          cwd=HERE.parent.parent, capture_output=True,
                          text=True, timeout=10)
    value = proc.stdout.strip()
    return value if proc.returncode == 0 and len(value) == 40 else "unknown"


def result_payload(rows: Sequence[BankRow], result: dict) -> dict:
    checked = assess(rows)
    for key in ("S1", "S2", "S3", "S4", "S5", "S6", "overall",
                "max_g_error_s", "max_c_error_f"):
        if checked[key] != result[key]:
            raise ValueError(f"assessment mismatch at {key}")
    serial = [row.to_dict() for row in rows]
    raw = json.dumps(serial, sort_keys=True,
                     separators=(",", ":")).encode("ascii")
    return {
        "entry": 96,
        "status": ("TT_BLOCK_PASS_NOT_CTLE" if result["overall"]
                   else "TT_BLOCK_FAIL_NOT_CTLE"),
        "runner_commit": _git_head(),
        "n_rows": len(serial),
        "rows_sha256": hashlib.sha256(raw).hexdigest().upper(),
        "assessment": result,
        "rows": serial,
        "limitations": [
            "This is a two-terminal TT block test, not a CTLE result.",
            "No link, eye, reward, policy or FINAL artifact is used.",
            "Intermediate binary codes differ from the frozen production bank.",
        ],
    }


def write_result(path: Path, payload: dict) -> None:
    if path.exists():
        raise FileExistsError(f"{path} exists; refusing to overwrite evidence")
    path.write_text(json.dumps(payload, indent=1) + "\n", encoding="ascii")


def run(workers: int = 8, path: Path = RESULTS) -> dict:
    if path.exists():
        raise FileExistsError(f"{path} exists; refusing to rerun")
    rows, result = run_bank(workers=workers)
    payload = result_payload(rows, result)
    write_result(path, payload)
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args(argv)
    if not args.run:
        parser.error("pass --run to create the immutable result")
    result = run(workers=args.workers)
    a = result["assessment"]
    print(f"rows: {result['n_rows']}  overall={a['overall']}")
    print("g error: "
          f"{a['max_g_error_s'] * 1e3:.6f} / "
          f"{a['g_error_limit_s'] * 1e3:.6f} mS")
    print("C error: "
          f"{a['max_c_error_f'] * 1e12:.6f} / "
          f"{a['c_error_limit_f'] * 1e12:.6f} pF")
    print(f"result: {RESULTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
