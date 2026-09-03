"""Generate Entry 89's fresh midpoint-channel journal without scoring FINAL.

The runner is inert until a five-policy freeze manifest exists.  It reuses the
qualified Entry 86 circuit/range and the joint-bank simulator while changing
only the link-view loss list to the six preregistered midpoints.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import time
from pathlib import Path
from typing import Optional, Sequence

from nebula.experiments import exp_joint_bank as J
from nebula.experiments import exp_joint_bank_73 as E86
from nebula.experiments import exp_shielded_ppo as PPO

HERE = Path(__file__).resolve().parent
RUN_NAME = "joint_bank_midpoint_run.jsonl"
GZIP_NAME = "joint_bank_midpoint_run.jsonl.gz"
METADATA_NAME = "joint_bank_midpoint_metadata.json"
MANIFEST_NAME = "shielded_policy_manifest.json"

MIDPOINT_LOSSES_DB = (3.75, 5.25, 6.75, 8.25, 9.75, 11.25)
FINAL_PEAKING_DB = (5.0, 7.0, 9.0)
FINAL_FREQ_EXPONENTS = (0.265, 0.5, 0.735)
FINAL_FREQUENCIES_HZ = tuple(
    1.25e9 * 2.0 ** exponent for exponent in FINAL_FREQ_EXPONENTS)
FINAL_REQUESTS = tuple(
    (peaking, frequency) for peaking in FINAL_PEAKING_DB
    for frequency in FINAL_FREQUENCIES_HZ)
EXPECTED_ROWS = 512 * 45
N_FINAL_IDENTITIES = 45 * len(MIDPOINT_LOSSES_DB) * len(FINAL_REQUESTS)
FINAL_STATUS = "GENERATED_NOT_SCORED"


def run_path() -> Path:
    return HERE / RUN_NAME


def gzip_path() -> Path:
    return HERE / GZIP_NAME


def metadata_path() -> Path:
    return HERE / METADATA_NAME


def manifest_path() -> Path:
    return HERE / MANIFEST_NAME


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def validate_policy_freeze() -> dict:
    path = manifest_path()
    if not path.exists():
        raise FileNotFoundError(f"policy freeze manifest missing: {path.name}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("status") != "FIVE_POLICIES_FROZEN":
        raise ValueError("policy freeze manifest status is not final")
    rows = manifest.get("policies", [])
    if {int(row.get("seed", -1)) for row in rows} != set(PPO.TRAIN_SEEDS):
        raise ValueError("policy freeze manifest seed membership mismatch")
    for row in rows:
        seed = int(row["seed"])
        for key, path_fn in (
                ("bc_sha256", PPO.bc_path),
                ("policy_sha256", PPO.policy_path),
                ("training_sha256", PPO.training_path)):
            artifact = path_fn(seed)
            if not artifact.exists() or _sha256(artifact) != row.get(key):
                raise ValueError(f"policy freeze artifact mismatch: {seed} {key}")
    return manifest


def _compress_exact(source: Path, target: Path) -> None:
    if target.exists():
        raise FileExistsError(f"refusing to overwrite {target.name}")
    with source.open("rb") as raw, gzip.open(target, "wb", compresslevel=9) as out:
        shutil.copyfileobj(raw, out, length=1024 * 1024)


def run(workers: int = 1, resume: bool = False) -> dict:
    manifest = validate_policy_freeze()
    if metadata_path().exists():
        raise FileExistsError(f"refusing to overwrite {metadata_path().name}")
    _, _, base_u, source_hashes = E86._load_sources()
    rows_before = (len(J._load_rows(run_path()))
                   if resume and run_path().exists() else 0)
    started = time.time()
    rows = J.sweep(
        base_u, workers=max(1, int(workers)), resume=bool(resume),
        log_path=run_path(), atten_max_x=E86.PROBE_MAX_X,
        losses_db=MIDPOINT_LOSSES_DB)
    elapsed = time.time() - started
    if len(rows) != EXPECTED_ROWS:
        raise RuntimeError(f"midpoint membership {len(rows)} != {EXPECTED_ROWS}")
    for row in rows:
        if row.ok and set(row.links or {}) != {
                str(value) for value in MIDPOINT_LOSSES_DB}:
            raise RuntimeError("midpoint row link-key membership mismatch")
    raw_sha = _sha256(run_path())
    _compress_exact(run_path(), gzip_path())
    decoded_sha = J._decoded_sha256(gzip_path())
    if decoded_sha != raw_sha:
        raise RuntimeError("compressed midpoint journal is not byte-preserving")
    out = {
        "task": "entry 89 fresh midpoint bank generation without FINAL scoring",
        "status": FINAL_STATUS,
        "policy_manifest_sha256": _sha256(manifest_path()),
        "policy_manifest": manifest,
        "source_hashes": source_hashes,
        "losses_db": list(MIDPOINT_LOSSES_DB),
        "n_rows": len(rows), "expected_rows": EXPECTED_ROWS,
        "n_final_identities_defined": N_FINAL_IDENTITIES,
        "final_requests_defined_not_scored": [
            [float(a), float(b)] for a, b in FINAL_REQUESTS],
        "raw_sha256": raw_sha,
        "gzip_sha256": _sha256(gzip_path()),
        "decoded_sha256": decoded_sha,
        "rows_before_segment": rows_before,
        "rows_this_segment": len(rows) - rows_before,
        "resumed": bool(resume),
        "wall_clock_s": float(elapsed),
        "simulations_run": len(rows) - rows_before,
    }
    metadata_path().write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--resume", action="store_true")
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args(argv)
    out = run(workers=args.workers, resume=args.resume)
    print(f"midpoint journal complete: {out['n_rows']} rows, "
          f"{out['wall_clock_s'] / 60.0:.2f} min, FINAL not scored")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
