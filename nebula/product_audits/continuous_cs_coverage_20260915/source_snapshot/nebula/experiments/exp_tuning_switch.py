"""Entry 95: characterise the real NMOS selector for the Rs/Cs bank.

Run once after the preregistration commit::

    python -m nebula.experiments.exp_tuning_switch --run --workers 8

The result is an isolated device qualification.  It does not upgrade the
production bank or the frozen RL policy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Sequence

from nebula.device.tuning_switch import SwitchRow, assess, run_probe

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "tuning_switch_results.json"


def _git_head() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=HERE.parent.parent,
        capture_output=True, text=True, timeout=10)
    value = proc.stdout.strip()
    return value if proc.returncode == 0 and len(value) == 40 else "unknown"


def result_payload(rows: Sequence[SwitchRow], assessment: dict) -> dict:
    """Validate and serialise the registered result without changing gates."""
    checked = assess(rows)
    for key in ("P1_integrity", "P2_scaling", "P3_one_hot", "P4_binary",
                "one_hot", "binary", "width_summary"):
        if checked[key] != assessment[key]:
            raise ValueError(f"assessment mismatch at {key}")
    serial = [row.to_dict() for row in rows]
    row_bytes = json.dumps(serial, sort_keys=True,
                           separators=(",", ":")).encode("ascii")
    return {
        "entry": 95,
        "status": "ISOLATED_SWITCH_ONLY_NOT_PRODUCTION",
        "preregistration_commit": _git_head(),
        "n_rows": len(serial),
        "rows_sha256": hashlib.sha256(row_bytes).hexdigest().upper(),
        "assessment": assessment,
        "rows": serial,
        "limitations": [
            "No selector transistor has been inserted into the CTLE yet.",
            "A passing isolated gate does not transfer Entry 86 or Entry 89 evidence.",
            "A binary-bank pass changes intermediate code values and requires new characterisation and RL training.",
        ],
    }


def write_result(path: Path, payload: dict) -> None:
    if path.exists():
        raise FileExistsError(f"{path} exists; refusing to overwrite evidence")
    path.write_text(json.dumps(payload, indent=1) + "\n", encoding="ascii")


def run(workers: int = 8, path: Path = RESULTS) -> dict:
    if path.exists():
        raise FileExistsError(f"{path} exists; refusing to rerun")
    rows, assessment = run_probe(workers=workers)
    payload = result_payload(rows, assessment)
    write_result(path, payload)
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true",
                        help="run the frozen 45-corner real-PDK probe")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args(argv)
    if not args.run:
        parser.error("pass --run to create the immutable result")
    result = run(workers=args.workers)
    a = result["assessment"]
    print(f"rows: {result['n_rows']}  P1={a['P1_integrity']} "
          f"P2={a['P2_scaling']}")
    print(f"exact one-hot: P3={a['P3_one_hot']} "
          f"W={a['one_hot']['selected_width_um']}")
    print(f"binary fallback: P4={a['P4_binary']} "
          f"W={a['binary']['selected_width_um']}")
    print(f"result: {RESULTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
