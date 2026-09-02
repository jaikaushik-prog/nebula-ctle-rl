"""Entry 86: verify the 7.3 dB attenuator over the full bank and PVT grid.

This driver reuses entry 81's qualified sweep and analysis machinery while
changing only the opt-in maximum divider ratio.  Its journal and result are
distinct and crash-resumable.

    python -m nebula.experiments.exp_joint_bank_73 --run --workers 8
    python -m nebula.experiments.exp_joint_bank_73 --resume --workers 8
    python -m nebula.experiments.exp_joint_bank_73 --analyse
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import time
from pathlib import Path
from typing import Optional, Sequence

from nebula.device import attenuator as AT
from nebula.experiments import exp_joint_bank as J

HERE = Path(__file__).resolve().parent
RUN_LOG = HERE / "joint_bank_73_run.jsonl"
RESULTS = HERE / "joint_bank_73_results.json"
ENTRY85 = HERE / "atten_final_probe_results.json"
BASELINE_JOURNAL = HERE / "joint_bank_run.jsonl.gz"

ENTRY85_SHA256 = "352D8589CCF0D0874F1C8359E6F9B4122A802B418EDCD82E41A64A3A0102E1BF"
BASELINE_DECODED_SHA256 = (
    "A205303614ABCC5F76D6EA78CFA1C9687E49A3817FA1E9FA9EC314336E20CA33")
PROBE_TOP_DB: float = 7.3
PROBE_MAX_X: float = 10.0 ** (PROBE_TOP_DB / 20.0)
EXPECTED_ROWS: int = len(J.ATTEN_CODES) * J.N_BANK_CODES * 45

ATTEN_CODE: int = 7
BANK_CODE: int = 50
CORNER_LABEL: str = "sf/0.95/125C"
ENTRY85_G_DC_DB: float = -11.002473381707903
ENTRY85_PEAKING_DB: float = 9.879560171693162
ENTRY85_F_PEAK_HZ: float = 1565785667.344873
ENTRY85_F_PEAK_OCT: float = math.log2(ENTRY85_F_PEAK_HZ / 2.5e9)
LONG_COVERAGE_FLOORS: tuple[int, ...] = (15, 16, 16, 16, 16, 16)
MAX_WALL_CLOCK_S: float = 180.0 * 60.0


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _per_code_scorable(rows: Sequence[J.JointRow]) -> dict:
    out = {}
    for loss in J.LOSSES_DB:
        key = str(float(loss))
        out[key] = {
            str(code): sum(
                row.atten_code == code and row.ok
                and bool((row.links or {}).get(key, {}).get("ok"))
                for row in rows)
            for code in J.ATTEN_CODES
        }
    return out


def _corner_scorable_3db(rows: Sequence[J.JointRow]) -> dict[str, int]:
    counts = collections.Counter()
    key = str(float(J.LOSSES_DB[0]))
    for row in rows:
        if row.ok and bool((row.links or {}).get(key, {}).get("ok")):
            counts[row.corner] += 1
    return {corner: int(value) for corner, value in sorted(counts.items())}


def _control_row(rows: Sequence[J.JointRow]) -> Optional[J.JointRow]:
    matches = [
        row for row in rows
        if row.atten_code == ATTEN_CODE and row.bank_code == BANK_CODE
        and row.corner == CORNER_LABEL
    ]
    if len(matches) != 1:
        return None
    return matches[0]


def score(current: dict, baseline: dict, rows: Sequence[J.JointRow],
          corner_scorable_3db: dict[str, int], wall_clock_s: float,
          wall_clock_scope: str = "complete uninterrupted run") -> dict:
    """Score Q1-Q7 exactly as preregistered in PREDICTIONS entry 86."""
    rows = list(rows)
    hard_failures = sum(not row.ok for row in rows)
    control = _control_row(rows)
    control_links = (control.links or {}) if control is not None else {}
    control_ok = bool(
        control is not None and control.ok
        and control.g_dc_db is not None
        and abs(float(control.g_dc_db) - ENTRY85_G_DC_DB) <= 0.02
        and control.peaking_db is not None
        and abs(float(control.peaking_db) - ENTRY85_PEAKING_DB) <= 0.02
        and control.f_peak_oct is not None
        and abs((2.5e9 * 2.0 ** float(control.f_peak_oct))
                / ENTRY85_F_PEAK_HZ - 1.0) <= 0.01
        and bool(control_links.get("3.0", {}).get("ok"))
        and bool(control_links.get("12.0", {}).get("ok"))
    )

    cur_loss = current.get("per_loss", [])
    base_loss = baseline.get("per_loss", [])
    short = cur_loss[0] if len(cur_loss) == len(J.LOSSES_DB) else {}
    short_coverage_ok = bool(
        short.get("n_requests_served_all_corners") == 16
        and short.get("n_solvable_corner_requests") == 720)
    long_coverage = tuple(
        int(row.get("n_requests_served_all_corners", -1))
        for row in cur_loss[1:])
    long_ok = len(long_coverage) == len(LONG_COVERAGE_FLOORS) and all(
        actual >= floor
        for actual, floor in zip(long_coverage, LONG_COVERAGE_FLOORS))
    baseline_short_scorable = (
        int(base_loss[0]["n_scorable"]) if len(base_loss) == len(J.LOSSES_DB)
        else 7519)
    scorable_guard = bool(
        int(short.get("n_scorable", -1)) > baseline_short_scorable
        and len(corner_scorable_3db) == 45
        and min(corner_scorable_3db.values(), default=0) > 0)
    reporting_ok = bool(
        len(cur_loss) == len(base_loss) == len(J.LOSSES_DB)
        and all("n_scorable" in row and
                "n_requests_served_all_corners" in row for row in cur_loss)
        and all(name in current.get("channel_adaptation", {}) for name in (
            "n_corner_requests_solvable_on_every_channel",
            "n_needing_different_setting_for_compliance",
            "n_whose_best_eye_setting_moves")))

    checks = {
        "Q1": bool(current.get("membership_ok")
                   and current.get("n_rows") == EXPECTED_ROWS
                   and hard_failures == 0),
        "Q2": control_ok,
        "Q3": short_coverage_ok,
        "Q4": bool(long_ok),
        "Q5": scorable_guard,
        "Q6": bool(wall_clock_scope == "complete uninterrupted run"
                   and float(wall_clock_s) < MAX_WALL_CLOCK_S),
        "Q7": reporting_ok,
    }
    return {
        "hard_device_failures": int(hard_failures),
        "entry85_control_ok": control_ok,
        "entry85_control": ({
            "g_dc_db": control.g_dc_db,
            "peaking_db": control.peaking_db,
            "f_peak_hz": (None if control.f_peak_oct is None else
                          2.5e9 * 2.0 ** float(control.f_peak_oct)),
            "noise_mvrms": control.noise_mvrms,
            "links": control.links,
        } if control is not None else None),
        "short_channel_coverage": short.get(
            "n_requests_served_all_corners"),
        "short_channel_solvable_pairs": short.get(
            "n_solvable_corner_requests"),
        "long_channel_coverage": list(long_coverage),
        "baseline_short_scorable": baseline_short_scorable,
        "short_scorable": short.get("n_scorable"),
        "minimum_corner_scorable_3db": min(
            corner_scorable_3db.values(), default=0),
        "wall_clock_s": float(wall_clock_s),
        "wall_clock_scope": wall_clock_scope,
        "checks": checks,
        "passed": all(checks.values()),
        "recommend_adoption": all(checks[f"Q{i}"] for i in range(1, 6)),
    }


def analyse(rows: Sequence[J.JointRow], baseline_rows: Sequence[J.JointRow],
            wall_clock_s: float,
            wall_clock_scope: str = "complete uninterrupted run") -> dict:
    current = J.analyse(rows)
    baseline = J.analyse(baseline_rows)
    per_code = _per_code_scorable(rows)
    corner_counts = _corner_scorable_3db(rows)
    summary = score(current, baseline, rows, corner_counts, wall_clock_s,
                    wall_clock_scope=wall_clock_scope)
    coverage_delta = []
    for now, old in zip(current["per_loss"], baseline["per_loss"]):
        coverage_delta.append({
            "loss_db": float(now["loss_db"]),
            "scorable_delta": int(now["n_scorable"] - old["n_scorable"]),
            "solvable_pair_delta": int(
                now["n_solvable_corner_requests"]
                - old["n_solvable_corner_requests"]),
            "all_corner_request_delta": int(
                now["n_requests_served_all_corners"]
                - old["n_requests_served_all_corners"]),
        })
    return {
        "current": current,
        "baseline": baseline,
        "coverage_delta": coverage_delta,
        "per_code_scorable": per_code,
        "corner_scorable_3db": corner_counts,
        "summary": summary,
    }


def _load_sources() -> tuple[dict, list[J.JointRow], tuple[float, ...], dict]:
    if not ENTRY85.exists():
        raise FileNotFoundError(f"entry-85 artifact missing: {ENTRY85}")
    entry85_hash = _sha256(ENTRY85)
    if entry85_hash != ENTRY85_SHA256:
        raise ValueError("entry-85 artifact hash changed")
    entry85 = json.loads(ENTRY85.read_text(encoding="utf-8"))
    if float(entry85.get("probe_top_db", float("nan"))) != PROBE_TOP_DB:
        raise ValueError("entry-85 range changed")
    if int(entry85.get("spice_invocations", -1)) != 1:
        raise ValueError("entry-85 source membership changed")

    if not BASELINE_JOURNAL.exists():
        raise FileNotFoundError(
            f"entry-81 comparison journal missing: {BASELINE_JOURNAL}")
    baseline_hash = J._decoded_sha256(BASELINE_JOURNAL)
    if baseline_hash != BASELINE_DECODED_SHA256:
        raise ValueError("entry-81 comparison journal hash changed")
    baseline_rows = J._load_rows(BASELINE_JOURNAL)

    root_source = HERE / str(entry85["root_source"])
    if not root_source.exists():
        raise FileNotFoundError(f"entry-85 root source missing: {root_source}")
    root_hash = _sha256(root_source)
    if root_hash != str(entry85["root_source_sha256"]):
        raise ValueError("entry-85 root source hash changed")
    root = json.loads(root_source.read_text(encoding="utf-8"))
    base_u = tuple(float(value) for value in root["base_u"])
    hashes = {
        "entry85_sha256": entry85_hash,
        "baseline_decoded_sha256": baseline_hash,
        "root_source_sha256": root_hash,
    }
    return entry85, baseline_rows, base_u, hashes


def run(workers: int = 1, resume: bool = False) -> dict:
    if RESULTS.exists():
        raise FileExistsError(f"refusing to overwrite {RESULTS.name}")
    _, baseline_rows, base_u, hashes = _load_sources()
    rows_before = (len(J._load_rows(RUN_LOG))
                   if resume and RUN_LOG.exists() else 0)
    t0 = time.time()
    rows = J.sweep(
        base_u, workers=workers, resume=resume, log_path=RUN_LOG,
        atten_max_x=PROBE_MAX_X)
    elapsed_s = time.time() - t0
    wall_scope = ("resume segment only" if resume else
                  "complete uninterrupted run")
    analysis = analyse(rows, baseline_rows, elapsed_s,
                       wall_clock_scope=wall_scope)
    out = {
        "task": "entry 86 full 7.3 dB attenuator x CTLE bank verification",
        "probe_top_db": PROBE_TOP_DB,
        "probe_max_x": PROBE_MAX_X,
        "production_atten_max_x_unchanged": AT.ATTEN_MAX_X,
        "source_hashes": hashes,
        "geometry": {
            "attenuator_codes": len(J.ATTEN_CODES),
            "ctle_codes": J.N_BANK_CODES,
            "corners": 45,
            "expected_rows": EXPECTED_ROWS,
        },
        "losses_db": list(J.LOSSES_DB),
        "analysis": analysis,
        "spice_invocations": len(rows),
        "resumed": bool(resume),
        "rows_before_segment": rows_before,
        "spice_invocations_this_segment": len(rows) - rows_before,
        "retry_decks_unbilled": True,
        "wall_clock_s": elapsed_s,
        "wall_clock_scope": wall_scope,
        "scope": ("45 mandated PVT corners at one design load, V6_SPECS and "
                  "seven constructed channels; not the 135-point load grid, "
                  "not measured channels and not production adoption"),
    }
    RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def _report(out: dict) -> None:
    analysis = out["analysis"]
    current = analysis["current"]
    summary = analysis["summary"]
    print()
    print("=" * 78)
    print("ENTRY 86 - FULL 7.3 dB JOINT BANK VERIFICATION")
    print("=" * 78)
    print(f"  rows: {current['n_rows']}/{current['n_expected']}")
    print(f"  hard device failures: {summary['hard_device_failures']}")
    print("  loss dB   scorable   all-corner requests   delta")
    for row, delta in zip(current["per_loss"], analysis["coverage_delta"]):
        print(f"   {row['loss_db']:5.1f}      {row['n_scorable']:5d}"
              f"          {row['n_requests_served_all_corners']:2d}/16"
              f"             {delta['all_corner_request_delta']:+d}")
    print(f"  entry-85 control: "
          f"{'PASS' if summary['entry85_control_ok'] else 'FAIL'}")
    print(f"  minimum 3 dB scorable settings/corner: "
          f"{summary['minimum_corner_scorable_3db']}")
    print(f"  wall clock ({out['wall_clock_scope']}): "
          f"{out['wall_clock_s'] / 60.0:.2f} min")
    for name, passed in summary["checks"].items():
        print(f"  {name}: {'PASS' if passed else 'FAIL'}")
    print(f"  ADOPTION RECOMMENDATION GATE: "
          f"{'PASS' if summary['recommend_adoption'] else 'FAIL'}")
    print("  Scope: evidence only; the owner makes any range adoption decision.")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--resume", action="store_true")
    mode.add_argument("--analyse", action="store_true")
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args(argv)
    if args.run or args.resume:
        out = run(workers=max(1, args.workers), resume=args.resume)
    elif args.analyse:
        if not RESULTS.exists():
            raise SystemExit(f"{RESULTS.name} missing: run the sweep first")
        out = json.loads(RESULTS.read_text(encoding="utf-8"))
    else:
        parser.print_help()
        return 0
    _report(out)
    return 0 if out["analysis"]["summary"]["checks"]["Q1"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
