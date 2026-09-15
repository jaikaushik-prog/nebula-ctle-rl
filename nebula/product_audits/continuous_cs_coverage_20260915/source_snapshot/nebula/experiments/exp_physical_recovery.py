"""Entry 115B: frozen physical recovery candidates for two near-pass targets."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

from nebula import physical_design as D

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "nebula/WINNING_SPRINT_PLAN.md"
SOURCE = ROOT / "nebula/product_audits/entry113_coverage_20260907"
CANDIDATES = (
    (3.0, 1.9e9, (401, 337), 273),
    (6.0, 1.9e9, (481, 474, 473, 417, 410, 353, 352, 346), 288),
)
EXPECTED_ELIGIBLE = {
    (3.0, 1.9e9): [273, 337, 401],
    (6.0, 1.9e9): [288, 346, 352, 353, 410, 417, 473, 474, 481],
}
MAX_CALLS = 137 * sum(len(settings) for _, _, settings, _ in CANDIDATES)


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def frozen_plan() -> str:
    committed = subprocess.check_output(
        ["git", "show", "HEAD:nebula/WINNING_SPRINT_PLAN.md"], cwd=ROOT)
    if committed.replace(b"\r\n", b"\n") != PLAN.read_bytes().replace(b"\r\n", b"\n"):
        raise ValueError("protocol must be committed unchanged before measurement")
    return hashlib.sha256(committed).hexdigest()


def verify_source() -> tuple[str, dict]:
    manifest_path = SOURCE / "sha256.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for name, expected in manifest.items():
        path = (SOURCE / name).resolve()
        if not path.is_relative_to(SOURCE.resolve()):
            raise ValueError("coverage manifest escapes its evidence directory")
        if not path.is_file() or sha(path) != expected:
            raise ValueError(f"coverage source hash mismatch: {name}")
    source = json.loads((SOURCE / "summary.json").read_text(encoding="utf-8"))
    by_request = {(row["peaking_db"], row["f_peak_hz"]): row
                  for row in source["requests"]}
    for peaking, frequency, settings, first_failed in CANDIDATES:
        row = by_request[(peaking, frequency)]
        if row.get("eligible") != EXPECTED_ELIGIBLE[(peaking, frequency)]:
            raise ValueError("historical eligible-setting membership changed")
        if row.get("classical_setting") != first_failed or row.get("status") != "MODEL_FAIL":
            raise ValueError("preserved first physical failure changed")
        if any(setting not in row["eligible"] for setting in settings):
            raise ValueError("recovery candidate is not historically eligible")
    return sha(manifest_path), source


def _candidate_name(peaking: float, frequency: float, setting: int) -> str:
    return f"p{peaking:g}_f{frequency/1e9:g}_s{setting}"


def run(out: Path) -> dict:
    protocol_hash = frozen_plan()
    source_manifest_hash, _ = verify_source()
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    rows = []
    with (out / "recovery.jsonl").open("x", encoding="utf-8") as journal:
        for peaking, frequency, settings, first_failed in CANDIDATES:
            for setting in settings:
                folder = out / _candidate_name(peaking, frequency, setting)
                row = {
                    "peaking_db": peaking,
                    "f_peak_hz": frequency,
                    "setting": setting,
                    "preserved_first_failed_setting": first_failed,
                    "status": "ERROR",
                    "spice_calls": 0,
                    "electrical_model_pass": False,
                    "full_product_compliance": False,
                }
                tick = time.perf_counter()
                try:
                    result = D.run(peaking, frequency, evidence_dir=folder,
                                   forced_setting=setting)
                    row.update(
                        status="MODEL_PASS" if D.is_verified(result) else "MODEL_FAIL",
                        electrical_model_pass=D.is_verified(result),
                        spice_calls=result["simulations"]["total"],
                        n_pass=result["verification"]["n_pass"],
                        n_points=result["verification"]["n_points"],
                        circuit_signature=result["physical_evidence"]["circuit_signature"],
                        deck_sha256=result["physical_evidence"]["deck_sha256"],
                    )
                except Exception as exc:
                    failure = folder / "failure.json"
                    if failure.is_file():
                        detail = json.loads(failure.read_text(encoding="utf-8"))
                        row["spice_calls"] = int(detail.get("spice_calls", 0))
                    row["error"] = f"{type(exc).__name__}: {exc}"
                row["wall_s"] = time.perf_counter() - tick
                rows.append(row)
                journal.write(json.dumps(row, allow_nan=False) + "\n")
                journal.flush()

    by_target = []
    for peaking, frequency, settings, first_failed in CANDIDATES:
        subset = [row for row in rows
                  if row["peaking_db"] == peaking and row["f_peak_hz"] == frequency]
        passing = [row["setting"] for row in subset if row["electrical_model_pass"]]
        by_target.append({
            "peaking_db": peaking,
            "f_peak_hz": frequency,
            "preserved_first_failed_setting": first_failed,
            "attempted_in_order": list(settings),
            "passing_settings": passing,
            "first_passing_setting": passing[0] if passing else None,
            "recovery_pass": bool(passing),
        })
    total_calls = sum(row["spice_calls"] for row in rows)
    if len(rows) != 10 or total_calls > MAX_CALLS:
        raise RuntimeError("recovery experiment violated its frozen budget or membership")
    result = {
        "status": "ENTRY115_FIXED_PHYSICAL_RECOVERY",
        "protocol_sha256": protocol_hash,
        "coverage_manifest_sha256": source_manifest_hash,
        "n_candidates": len(rows),
        "spice_calls": total_calls,
        "max_spice_calls": MAX_CALLS,
        "all_candidates_attempted": len(rows) == 10,
        "targets": by_target,
        "candidates": rows,
        "n_targets_recovered": sum(row["recovery_pass"] for row in by_target),
        "full_product_compliance": False,
        "claim_boundary": "Fresh fixed-circuit electrical model evidence; classical recovery, behavioural DFE, geometry subtotal",
        "wall_s": time.perf_counter() - started,
    }
    (out / "summary.json").write_text(
        json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    hashes = {str(path.relative_to(out)): sha(path)
              for path in out.rglob("*") if path.is_file() and path.name != "sha256.json"}
    (out / "sha256.json").write_text(
        json.dumps(hashes, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    result = run(parser.parse_args().out)
    print(json.dumps({"targets": result["targets"],
                      "spice_calls": result["spice_calls"]}, indent=2))
