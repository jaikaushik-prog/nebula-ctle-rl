"""Entry 97 anti-clobber runner for the safe LVT selector screen."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Sequence

from nebula.device.lvt_tuning_bank import LvtBankRow, assess, run_screen

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "lvt_tuning_bank_results.json"


def _git_head() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=HERE.parent.parent,
        capture_output=True, text=True, timeout=10)
    value = proc.stdout.strip()
    return value if proc.returncode == 0 and len(value) == 40 else "unknown"


def result_payload(rows: Sequence[LvtBankRow], result: dict) -> dict:
    checked = assess(rows)
    for key in ("L1_integrity", "L2_ordering", "L3_any_loss_pass",
                "L4_any_cap_pass", "L5_selection", "L6_isolation_safety",
                "overall", "selected_scale", "scale_summary"):
        if checked[key] != result[key]:
            raise ValueError(f"assessment mismatch at {key}")
    serial = [row.to_dict() for row in rows]
    raw = json.dumps(serial, sort_keys=True,
                     separators=(",", ":")).encode("ascii")
    return {
        "entry": 97,
        "status": ("TT_LVT_SCREEN_PASS_NOT_CTLE" if result["overall"]
                   else "TT_LVT_SCREEN_FAIL_NOT_CTLE"),
        "runner_commit": _git_head(),
        "n_rows": len(serial),
        "rows_sha256": hashlib.sha256(raw).hexdigest().upper(),
        "assessment": result,
        "rows": serial,
        "limitations": [
            "This is a TT two-terminal feasibility screen, not a CTLE result.",
            "No boosted gate, link, eye, reward, policy or FINAL artifact is used.",
            "A pass permits only a separately preregistered all-corner bank test.",
        ],
    }


def write_result(path: Path, payload: dict) -> None:
    if path.exists():
        raise FileExistsError(f"{path} exists; refusing to overwrite evidence")
    path.write_text(json.dumps(payload, indent=1) + "\n", encoding="ascii")


def run(workers: int = 6, path: Path = RESULTS) -> dict:
    if path.exists():
        raise FileExistsError(f"{path} exists; refusing to rerun")
    rows, result = run_screen(workers=workers)
    payload = result_payload(rows, result)
    write_result(path, payload)
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args(argv)
    if not args.run:
        parser.error("pass --run to create the immutable result")
    result = run(workers=args.workers)
    a = result["assessment"]
    print(f"rows: {result['n_rows']}  overall={a['overall']}")
    for item in a["scale_summary"]:
        print(f"scale {item['scale']:>2}: "
              f"Gerr={item['max_g_error_s'] * 1e3:.6f} mS "
              f"Cerr={item['max_c_error_f'] * 1e12:.6f} pF "
              f"pass={item['loss_pass'] and item['cap_pass']}")
    print(f"selected scale: {a['selected_scale']}")
    print(f"result: {RESULTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
