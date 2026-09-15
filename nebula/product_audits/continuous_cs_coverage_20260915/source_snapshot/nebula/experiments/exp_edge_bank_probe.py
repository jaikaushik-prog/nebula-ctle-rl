"""Entry 90: focused physical-bank probe for the two 12 dB request edges.

The immutable 512-setting bank is reused.  Only 30 registered candidate
settings are simulated: six top-attenuation settings for the low-frequency
edge, plus 24 extra-low-Cs settings spanning all attenuator codes and the two
highest Rs settings with their midpoint.  Each setting is measured over all
45 PVT corners and all seven characterised channel losses.

This is a diagnostic.  It neither changes the production bank nor retrains RL.

    python -m nebula.experiments.exp_edge_bank_probe --run --workers 8
    python -m nebula.experiments.exp_edge_bank_probe --resume --workers 8
    python -m nebula.experiments.exp_edge_bank_probe --analyse
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures
import gzip
import hashlib
import json
import math
import shutil
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from nebula.common.types import Corner, all_corners
from nebula.device import attenuator as AT
from nebula.experiments import exp_joint_bank as J
from nebula.experiments.exp_tuning_bank import I_CS, I_RS, Setting
from nebula.rl.contract import sizing_from_u

HERE = Path(__file__).resolve().parent
ROOT_SOURCE = HERE / "atten_range_probe_results.json"
SOURCE = HERE / "joint_bank_73_run.jsonl.gz"
RUN_LOG = HERE / "edge_bank_probe_run.jsonl"
GZIP_LOG = HERE / "edge_bank_probe_run.jsonl.gz"
RESULTS = HERE / "edge_bank_probe_results.json"

ROOT_SOURCE_SHA256 = (
    "9A06AA65D71B463D4F75CC2072D82BC845799BAF6FE073F66C25C069ED2F358B")
SOURCE_DECODED_SHA256 = (
    "1B5F941DF4B34F3C90F6DD050F264D8A77C7BB2E5CE4D9EED8CC29EBD9F9843F")

PROBE_TOP_DB: float = 8.3
PROBE_MAX_X: float = 10.0 ** (PROBE_TOP_DB / 20.0)
FIRST_PROBE_SETTING: int = 512
N_CANDIDATES: int = 30
EXPECTED_ROWS: int = N_CANDIDATES * 45
STATUS: str = "FOCUSED_DIAGNOSTIC_NOT_ADOPTED"

LOW_EDGE_REQUEST: tuple[float, float] = (12.0, 1.25e9)
HIGH_EDGE_REQUEST: tuple[float, float] = (12.0, 2.5e9)
CONTROL_REQUESTS: tuple[tuple[float, float], ...] = (
    (3.0, 1.25e9),
    (3.0, 2.5e9),
    (7.5, math.sqrt(1.25e9 * 2.5e9)),
)
REQUESTS: tuple[tuple[float, float], ...] = (
    *CONTROL_REQUESTS, LOW_EDGE_REQUEST, HIGH_EDGE_REQUEST)


@dataclass(frozen=True)
class ProbeCandidate:
    """One registered physical candidate outside the immutable 512 rows."""

    setting: int
    label: str
    group: str
    atten_code: int
    u: tuple[float, ...]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def load_base_u() -> tuple[float, ...]:
    """Load the exact base design without loading or simulating the old bank."""
    if not ROOT_SOURCE.exists():
        raise FileNotFoundError(f"base source missing: {ROOT_SOURCE.name}")
    if _sha256(ROOT_SOURCE) != ROOT_SOURCE_SHA256:
        raise ValueError("Entry 90 base source hash changed")
    source = json.loads(ROOT_SOURCE.read_text(encoding="utf-8"))
    base_u = tuple(float(value) for value in source["base_u"])
    if len(base_u) != 7:
        raise ValueError("Entry 90 base design dimension changed")
    return base_u


def _standard_bank(base_u: Sequence[float]) -> list[Setting]:
    return J.bank(base_u, n_rs=J.N_RS, n_cs=J.N_CS,
                  rs_span=J.RS_SPAN, cs_span=J.CS_SPAN)


def _registered_coordinates(base_u: Sequence[float]) -> tuple[float, float,
                                                                float, float]:
    bank = _standard_bank(base_u)
    rs6 = float(bank[6 * J.N_CS].u[I_RS])
    rs7 = float(bank[7 * J.N_CS].u[I_RS])
    rs_mid = 0.5 * (rs6 + rs7)
    cs0 = float(bank[0].u[I_CS])
    cs1 = float(bank[1].u[I_CS])
    cs_extra = 2.0 * cs0 - cs1
    if not 0.0 <= cs_extra < cs0 <= 1.0:
        raise ValueError("registered extra-low Cs coordinate left the box")
    return rs6, rs_mid, rs7, cs_extra


def extra_cs_f(base_u: Sequence[float]) -> float:
    """Requested physical Cs of the one-step geometric continuation."""
    _, _, _, cs_extra = _registered_coordinates(base_u)
    u = np.asarray(base_u, dtype=float).copy()
    u[I_CS] = cs_extra
    return float(sizing_from_u(u).params["cs"])


def mid_rs_ohm(base_u: Sequence[float]) -> float:
    """Requested physical Rs midway between existing codes 6 and 7 in log."""
    _, rs_mid, _, _ = _registered_coordinates(base_u)
    u = np.asarray(base_u, dtype=float).copy()
    u[I_RS] = rs_mid
    return float(sizing_from_u(u).params["rs"])


def build_candidates(base_u: Sequence[float]) -> list[ProbeCandidate]:
    """Build the exact 6 + 24 candidate membership frozen in Entry 90."""
    bank = _standard_bank(base_u)
    candidates: list[ProbeCandidate] = []

    for i_rs in (6, 7):
        for i_cs in (2, 3, 4):
            bank_code = i_rs * J.N_CS + i_cs
            candidates.append(ProbeCandidate(
                setting=FIRST_PROBE_SETTING + len(candidates),
                label=f"low-r{i_rs}-c{i_cs}-a7", group="low-edge",
                atten_code=AT.N_CODES - 1,
                u=tuple(float(value) for value in bank[bank_code].u)))

    rs6, rs_mid, rs7, cs_extra = _registered_coordinates(base_u)
    for atten_code in range(AT.N_CODES):
        for name, rs_value in (("r6", rs6), ("rmid", rs_mid), ("r7", rs7)):
            u = np.asarray(base_u, dtype=float).copy()
            u[I_RS] = rs_value
            u[I_CS] = cs_extra
            candidates.append(ProbeCandidate(
                setting=FIRST_PROBE_SETTING + len(candidates),
                label=f"high-{name}-cx-a{atten_code}", group="high-edge",
                atten_code=int(atten_code),
                u=tuple(float(value) for value in u)))

    if len(candidates) != N_CANDIDATES:
        raise RuntimeError("Entry 90 candidate membership changed")
    if len({candidate.setting for candidate in candidates}) != N_CANDIDATES:
        raise RuntimeError("Entry 90 candidate IDs are not unique")
    return candidates


def _measure_candidate(task: tuple[ProbeCandidate, Corner]) -> J.JointRow:
    candidate, corner = task
    setting = Setting(i_rs=-1, i_cs=-1, u=candidate.u)
    measured = J._measure((
        0, setting, candidate.atten_code, corner, PROBE_MAX_X, J.LOSSES_DB))
    return replace(
        measured, setting=candidate.setting, bank_code=-1, i_rs=-1, i_cs=-1)


def membership_ok(rows: Sequence[J.JointRow],
                  candidates: Sequence[ProbeCandidate],
                  corners: Sequence[str],
                  losses: Sequence[float] = J.LOSSES_DB) -> bool:
    """Require every candidate/corner row and every registered link key."""
    expected = {(int(candidate.setting), str(corner))
                for candidate in candidates for corner in corners}
    actual = {(int(row.setting), str(row.corner)) for row in rows}
    link_keys = {str(float(loss)) for loss in losses}
    return bool(
        len(rows) == len(expected) == len(actual)
        and actual == expected
        and all(set(row.links or {}) == link_keys for row in rows))


def sweep(candidates: Sequence[ProbeCandidate],
          corners: Optional[Sequence[Corner]] = None,
          workers: int = 1, resume: bool = False,
          log_path: Path = RUN_LOG) -> list[J.JointRow]:
    """Measure or resume the exact candidate/PVT table, journalling each row."""
    candidates = tuple(candidates)
    corners = tuple(corners if corners is not None else all_corners())
    tasks = [(candidate, corner) for candidate in candidates
             for corner in corners]
    old = J._load_rows(log_path) if resume and log_path.exists() else []
    if log_path.exists() and not resume:
        raise FileExistsError(f"{log_path.name} exists; use --resume")
    done = {(int(row.setting), str(row.corner)) for row in old}
    pending = [task for task in tasks
               if (task[0].setting, J._corner_label(task[1])) not in done]
    rows = list(old)
    mode = "a" if old else "w"
    with log_path.open(mode, encoding="utf-8") as stream:
        if workers <= 1:
            iterator = map(_measure_candidate, pending)
            pool = None
        else:
            pool = concurrent.futures.ThreadPoolExecutor(
                max_workers=max(1, int(workers)))
            iterator = pool.map(_measure_candidate, pending)
        try:
            for index, row in enumerate(iterator, 1):
                rows.append(row)
                stream.write(json.dumps(asdict(row), separators=(",", ":"))
                             + "\n")
                stream.flush()
                if index == 1 or index % 50 == 0 or index == len(pending):
                    print(f"  completed {len(old) + index}/{len(tasks)} rows",
                          flush=True)
        finally:
            if pool is not None:
                pool.shutdown(wait=True, cancel_futures=True)

    corner_labels = tuple(J._corner_label(corner) for corner in corners)
    if not membership_ok(rows, candidates, corner_labels):
        raise RuntimeError("Entry 90 candidate/corner/link membership failed")
    return rows


def request_key(request: tuple[float, float]) -> str:
    peaking, frequency = request
    return f"{float(peaking):g}dB@{float(frequency) / 1e9:.9g}GHz"


def coverage(source_rows: Sequence[J.JointRow],
             probe_rows: Sequence[J.JointRow],
             requests: Sequence[tuple[float, float]] = REQUESTS,
             losses: Sequence[float] = J.LOSSES_DB,
             corners: Optional[Sequence[str]] = None,
             candidates: Optional[Sequence[ProbeCandidate]] = None) -> dict:
    """Score old and union pools separately, with new-only attribution."""
    old_by_corner: dict[str, list[J.JointRow]] = collections.defaultdict(list)
    new_by_corner: dict[str, list[J.JointRow]] = collections.defaultdict(list)
    for row in source_rows:
        old_by_corner[str(row.corner)].append(row)
    for row in probe_rows:
        new_by_corner[str(row.corner)].append(row)
    corners = tuple(corners if corners is not None else sorted(old_by_corner))
    labels = ({candidate.setting: candidate.label for candidate in candidates}
              if candidates is not None else {})
    out = {}
    for request in requests:
        target_peaking, target_frequency = map(float, request)
        n_old = 0
        n_union = 0
        n_new_only = 0
        usage = collections.Counter()
        failed = []
        per_loss = []
        for loss in losses:
            loss_old = 0
            loss_union = 0
            loss_new_only = 0
            for corner in corners:
                old_good = [row for row in old_by_corner.get(str(corner), ())
                            if J.is_compliant(row, loss, target_frequency,
                                              target_peaking)]
                new_good = [row for row in new_by_corner.get(str(corner), ())
                            if J.is_compliant(row, loss, target_frequency,
                                              target_peaking)]
                old_ok = bool(old_good)
                union_ok = bool(old_good or new_good)
                n_old += old_ok
                n_union += union_ok
                loss_old += old_ok
                loss_union += union_ok
                if union_ok and not old_ok:
                    n_new_only += 1
                    loss_new_only += 1
                    def eye_area(row: J.JointRow) -> float:
                        link = (row.links or {}).get(str(float(loss)), {})
                        return (float(link.get("eye_h_v", 0.0))
                                * float(link.get("eye_w_ui", 0.0)))

                    chosen = max(new_good, key=lambda row: (
                        eye_area(row), -int(row.setting)))
                    usage[labels.get(chosen.setting,
                                     f"setting-{chosen.setting}")] += 1
                if not union_ok:
                    failed.append({"loss_db": float(loss),
                                   "corner": str(corner)})
            per_loss.append({
                "loss_db": float(loss), "n_old_pass": int(loss_old),
                "n_pass": int(loss_union),
                "n_new_only": int(loss_new_only),
            })
        out[request_key(request)] = {
            "target_peaking_db": target_peaking,
            "target_f_peak_hz": target_frequency,
            "n_total": len(tuple(losses)) * len(corners),
            "n_old_pass": int(n_old), "n_pass": int(n_union),
            "n_new_only": int(n_new_only), "per_loss": per_loss,
            "candidate_usage": dict(sorted(usage.items())),
            "failed_conditions": failed,
        }
    return out


def score(membership_ok: bool, hard_device_failures: int,
          coverage_by_request: dict, source_hash_ok: bool,
          isolation_ok: bool) -> dict:
    """Apply Entry 90's frozen Q1-Q7 gates without changing a threshold."""
    low = coverage_by_request[request_key(LOW_EDGE_REQUEST)]
    high = coverage_by_request[request_key(HIGH_EDGE_REQUEST)]
    controls = [coverage_by_request[request_key(request)]
                for request in CONTROL_REQUESTS]
    new_usage = int(low.get("n_new_only", 0)) + int(high.get("n_new_only", 0))
    attribution = bool(
        new_usage > 0
        and (low.get("candidate_usage") or high.get("candidate_usage")))
    checks = {
        "Q1": bool(membership_ok),
        "Q2": int(hard_device_failures) == 0,
        "Q3": int(low.get("n_pass", -1)) == 315,
        "Q4": int(high.get("n_pass", -1)) == 315,
        "Q5": all(int(row.get("n_pass", -1)) == 315 for row in controls),
        "Q6": attribution,
        "Q7": bool(source_hash_ok and isolation_ok),
    }
    passed = all(checks.values())
    return {
        "checks": checks, "passed": passed,
        "recommend_production_redesign": passed,
        "newly_covered_edge_conditions": new_usage,
    }


def analyse(probe_rows: Sequence[J.JointRow],
            source_rows: Sequence[J.JointRow],
            candidates: Sequence[ProbeCandidate],
            source_hash_ok: bool = True) -> dict:
    corner_labels = tuple(sorted({str(row.corner) for row in source_rows}))
    member_ok = membership_ok(
        probe_rows, candidates, corner_labels, losses=J.LOSSES_DB)
    hard_failures = sum(
        not row.ok and J._SWING.search(str(row.reason or "")) is None
        for row in probe_rows)
    by_request = coverage(
        source_rows, probe_rows, candidates=candidates,
        corners=corner_labels, losses=J.LOSSES_DB)
    result = score(
        member_ok, hard_failures, by_request,
        source_hash_ok=source_hash_ok, isolation_ok=True)
    result.update({
        "membership_ok": member_ok,
        "n_probe_rows": len(probe_rows),
        "hard_device_failures": int(hard_failures),
        "coverage": by_request,
    })
    return result


def _compress_exact(source: Path, target: Path) -> None:
    with source.open("rb") as raw, gzip.open(target, "wb", compresslevel=9) as out:
        shutil.copyfileobj(raw, out, length=1024 * 1024)


def _candidate_record(candidate: ProbeCandidate) -> dict:
    params = sizing_from_u(np.asarray(candidate.u, dtype=float)).params
    return {
        "setting": candidate.setting, "label": candidate.label,
        "group": candidate.group, "atten_code": candidate.atten_code,
        "attenuation_db": AT.attenuation_db(
            candidate.atten_code, atten_max_x=PROBE_MAX_X),
        "rs_ohm": float(params["rs"]), "cs_f": float(params["cs"]),
        "u": list(candidate.u),
    }


def run(workers: int = 1, resume: bool = False) -> dict:
    if RESULTS.exists():
        raise FileExistsError(f"refusing to overwrite {RESULTS.name}")
    base_u = load_base_u()
    candidates = build_candidates(base_u)
    before = (len(J._load_rows(RUN_LOG))
              if resume and RUN_LOG.exists() else 0)
    started = time.time()
    probe_rows = sweep(
        candidates, workers=max(1, int(workers)), resume=bool(resume),
        log_path=RUN_LOG)
    elapsed = time.time() - started

    if not SOURCE.exists():
        raise FileNotFoundError(f"immutable source missing: {SOURCE.name}")
    source_hash = J._decoded_sha256(SOURCE)
    if source_hash != SOURCE_DECODED_SHA256:
        raise ValueError("Entry 90 immutable source hash changed")
    source_rows = J._load_rows(SOURCE)
    summary = analyse(
        probe_rows, source_rows, candidates, source_hash_ok=True)

    raw_hash = _sha256(RUN_LOG)
    if GZIP_LOG.exists():
        if J._decoded_sha256(GZIP_LOG) != raw_hash:
            raise FileExistsError(
                f"{GZIP_LOG.name} exists and does not match the raw journal")
    else:
        _compress_exact(RUN_LOG, GZIP_LOG)
    decoded_hash = J._decoded_sha256(GZIP_LOG)
    if decoded_hash != raw_hash:
        raise RuntimeError("compressed Entry 90 journal is not byte-preserving")

    out = {
        "task": "Entry 90 focused physical bank probe for 12 dB edges",
        "status": STATUS,
        "scope": ("focused diagnostic only; no production range adoption, "
                  "policy retraining or immutable FINAL access"),
        "probe_top_db": PROBE_TOP_DB, "probe_max_x": PROBE_MAX_X,
        "production_top_db_unchanged": AT.attenuation_db(AT.N_CODES - 1),
        "root_source": ROOT_SOURCE.name,
        "root_source_sha256": ROOT_SOURCE_SHA256,
        "source": SOURCE.name,
        "source_decoded_sha256": source_hash,
        "n_candidates": len(candidates),
        "candidates": [_candidate_record(candidate)
                       for candidate in candidates],
        "n_rows": len(probe_rows), "expected_rows": EXPECTED_ROWS,
        "rows_before_segment": before,
        "rows_this_segment": len(probe_rows) - before,
        "resumed": bool(resume), "wall_clock_s": float(elapsed),
        "wall_clock_scope": ("resume segment only" if resume else
                             "complete uninterrupted run"),
        "raw_sha256": raw_hash, "gzip_sha256": _sha256(GZIP_LOG),
        "decoded_sha256": decoded_hash,
        "summary": summary,
    }
    RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def _report(out: dict) -> None:
    summary = out["summary"]
    print()
    print("=" * 72)
    print("ENTRY 90 - 12 dB PHYSICAL EDGE PROBE")
    print("=" * 72)
    print(f"  candidates: {out['n_candidates']}  rows: {out['n_rows']}")
    print(f"  elapsed: {out['wall_clock_s'] / 60.0:.2f} min")
    for request in REQUESTS:
        row = summary["coverage"][request_key(request)]
        print(f"  {request_key(request)}: {row['n_pass']}/{row['n_total']} "
              f"(old {row['n_old_pass']}, new-only {row['n_new_only']})")
    for name, passed in summary["checks"].items():
        print(f"  {name}: {'PASS' if passed else 'FAIL'}")
    print(f"  OVERALL: {'PASS' if summary['passed'] else 'FAIL'}")
    print("  Scope: diagnostic only; production bank remains unchanged.")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--resume", action="store_true")
    mode.add_argument("--analyse", action="store_true")
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args(argv)
    if args.analyse:
        if not RESULTS.exists():
            raise SystemExit(f"{RESULTS.name} missing: run the probe first")
        out = json.loads(RESULTS.read_text(encoding="utf-8"))
    else:
        out = run(workers=args.workers, resume=args.resume)
    _report(out)
    return 0 if out["summary"]["passed"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = (
    "ProbeCandidate", "PROBE_TOP_DB", "PROBE_MAX_X",
    "FIRST_PROBE_SETTING", "LOW_EDGE_REQUEST", "HIGH_EDGE_REQUEST",
    "CONTROL_REQUESTS", "REQUESTS", "load_base_u", "extra_cs_f",
    "mid_rs_ohm", "build_candidates", "membership_ok", "coverage",
    "request_key", "score", "analyse", "sweep", "run", "main",
)
