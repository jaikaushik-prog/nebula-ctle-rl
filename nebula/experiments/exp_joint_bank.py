"""Measure the real input-attenuator x CTLE-bank design over PVT and channel.

This is the circuit table required before an adaptation policy can be honest:
8 real-PMOS attenuator codes x 64 CTLE Rs/Cs codes x 45 mandated PVT corners.
Each SPICE result is re-scored over the seven constructed channel losses in
Python.  A crash-safe JSONL journal supports ``--resume``; completed runs are
never silently overwritten.

    python -m nebula.experiments.exp_joint_bank --run --workers 8
    python -m nebula.experiments.exp_joint_bank --resume --workers 8
    python -m nebula.experiments.exp_joint_bank --analyse
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures
import gzip
import hashlib
import json
import math
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

import nebula.rl.reward_v1 as R
from nebula.common.types import SPEC_EYE_H_MIN_V, SPEC_EYE_W_MIN_UI, Corner, all_corners
from nebula.device import attenuator as AT
from nebula.experiments.adaptive_screen import CL_MID_F, ScreenPoint, evaluate_at_points
from nebula.experiments.exp_bank_sweep import REQUEST_ROWS, SPECS, _strip_request_rows
from nebula.experiments.exp_coverage import FREQ_REQUESTS, PEAKING_REQUESTS
from nebula.experiments.exp_tuning_bank import Setting, bank
from nebula.link.channel import FAMILY_IL_DB
from nebula.rl.contract import design_id, sizing_from_u

HERE = Path(__file__).resolve().parent
RUN_LOG = HERE / "joint_bank_run.jsonl"
RESULTS = HERE / "joint_bank_results.json"
DIAGNOSIS = HERE / "joint_bank_diagnosis.json"

N_RS, N_CS, RS_SPAN, CS_SPAN = 8, 8, 0.38, 0.20
N_BANK_CODES = N_RS * N_CS
ATTEN_CODES = tuple(range(AT.N_CODES))
LOSSES_DB = tuple(float(x) for x in FAMILY_IL_DB)

_SWING = re.compile(r"output swing ([\d.]+) mVpp exceeds the linear limit ([\d.]+)")


@dataclass
class JointRow:
    """One measured (attenuator, CTLE, corner) setting and seven link views."""

    setting: int
    atten_code: int
    bank_code: int
    i_rs: int
    i_cs: int
    corner: str
    ok: bool
    reason: Optional[str] = None
    peaking_db: Optional[float] = None
    f_peak_oct: Optional[float] = None
    margins: dict = None
    eye_h_v: Optional[float] = None
    eye_w_ui: Optional[float] = None
    power_w: Optional[float] = None
    hd3_nyq_dbc: Optional[float] = None
    links: dict = None
    g_dc_db: Optional[float] = None
    noise_mvrms: Optional[float] = None


def setting_id(atten_code: int, bank_code: int) -> int:
    """One stable action number; attenuator is the major axis."""
    return int(atten_code) * N_BANK_CODES + int(bank_code)


def split_setting(value: int) -> tuple[int, int]:
    return divmod(int(value), N_BANK_CODES)


def _corner_label(c: Corner) -> str:
    return f"{c.process}/{c.vdd_scale:.2f}/{c.temp_c:g}C"


def _compact_link(link: Optional[dict]) -> dict:
    if not link:
        return {"ok": False, "reason": "missing link result"}
    if link.get("ok"):
        return {"ok": True, "eye_h_v": float(link["eye_h_v"]),
                "eye_w_ui": float(link["eye_w_ui"])}
    reason = str(link.get("reason") or "unknown link failure")
    match = _SWING.search(reason)
    if match:
        return {"ok": False, "reason": "compression",
                "demand_mvpp": float(match.group(1)),
                "limit_mvpp": float(match.group(2))}
    return {"ok": False, "reason": reason}


def _measure(task: tuple) -> JointRow:
    if len(task) == 4:
        bank_code, st, atten_code, corner = task
        atten_max_x = None
    elif len(task) == 5:
        bank_code, st, atten_code, corner, atten_max_x = task
    else:
        raise ValueError(f"expected a 4- or 5-field joint-bank task, got {len(task)}")
    ev = evaluate_at_points(
        st.u, [ScreenPoint(corner, CL_MID_F, "joint bank")],
        target_f_peak_hz=1.9e9, target_peaking_db=7.5, specs=SPECS,
        link_losses_db=LOSSES_DB, atten_code=atten_code,
        atten_max_x=atten_max_x)
    point = ev.points[0] if ev.points else None
    ok = bool(point and point.ok)
    links = ({str(loss): _compact_link((point.links_by_loss or {}).get(loss))
              for loss in LOSSES_DB} if ok else {})
    return JointRow(
        setting=setting_id(atten_code, bank_code), atten_code=atten_code,
        bank_code=bank_code, i_rs=st.i_rs, i_cs=st.i_cs,
        corner=_corner_label(corner), ok=ok,
        reason=(None if ok else (point.reason if point else ev.reason or "no point")),
        peaking_db=(point.peaking_db if ok else None),
        f_peak_oct=(point.f_peak_oct if ok else None),
        margins=(_strip_request_rows(point.margins) if ok else {}),
        eye_h_v=(point.eye_h_v if ok else None),
        eye_w_ui=(point.eye_w_ui if ok else None),
        power_w=(point.power_w if ok else None),
        hd3_nyq_dbc=(point.hd3_nyq_dbc if ok else None), links=links,
        g_dc_db=(point.g_dc_db if ok else None),
        noise_mvrms=(float(point.noise_vrms) * 1e3 if ok else None))


def _load_rows(path: Path) -> list[JointRow]:
    rows = []
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                rows.append(JointRow(**json.loads(line)))
            except Exception as exc:
                raise ValueError(
                    f"{path.name}:{lineno}: invalid journal row: {exc}") from exc
    keys = [(r.setting, r.corner) for r in rows]
    if len(keys) != len(set(keys)):
        raise ValueError(f"{path.name}: duplicate setting/corner rows")
    return rows


def _tasks(base_u: Sequence[float], corners: Sequence[Corner],
           atten_codes: Sequence[int],
           atten_max_x: Optional[float] = None) -> list[tuple]:
    settings = bank(base_u, n_rs=N_RS, n_cs=N_CS, rs_span=RS_SPAN,
                    cs_span=CS_SPAN)
    tasks = [(bank_code, st, int(a), c)
             for a in atten_codes for bank_code, st in enumerate(settings)
             for c in corners]
    if atten_max_x is None:
        return tasks
    return [task + (float(atten_max_x),) for task in tasks]


def sweep(base_u: Sequence[float], corners: Optional[Sequence[Corner]] = None,
          atten_codes: Sequence[int] = ATTEN_CODES, workers: int = 1,
          resume: bool = False, log_path: Path = RUN_LOG,
          atten_max_x: Optional[float] = None) -> list[JointRow]:
    """Run or resume the full table, journalling every completed SPICE call."""
    corners = list(corners if corners is not None else all_corners())
    tasks = _tasks(base_u, corners, atten_codes, atten_max_x=atten_max_x)
    old = _load_rows(log_path) if resume and log_path.exists() else []
    if log_path.exists() and not resume:
        raise FileExistsError(f"{log_path} exists; use --resume, never overwrite")
    done = {(r.setting, r.corner) for r in old}
    pending = [t for t in tasks
               if (setting_id(t[2], t[0]), _corner_label(t[3])) not in done]
    mode = "a" if old else "w"
    rows = list(old)
    with log_path.open(mode, encoding="utf-8") as fh:
        if workers <= 1:
            iterator = map(_measure, pending)
            pool = None
        else:
            pool = concurrent.futures.ThreadPoolExecutor(max_workers=int(workers))
            iterator = pool.map(_measure, pending)
        try:
            for i, row in enumerate(iterator, 1):
                rows.append(row)
                fh.write(json.dumps(asdict(row), separators=(",", ":")) + "\n")
                fh.flush()
                if i == 1 or i % 64 == 0 or i == len(pending):
                    print(f"  completed {len(old) + i}/{len(tasks)} settings/corners",
                          flush=True)
        finally:
            if pool is not None:
                pool.shutdown(wait=True, cancel_futures=True)
    keys = {(r.setting, r.corner) for r in rows}
    expected = {(setting_id(t[2], t[0]), _corner_label(t[3])) for t in tasks}
    if keys != expected or len(rows) != len(expected):
        raise RuntimeError(f"membership gate failed: {len(rows)} rows, "
                           f"{len(keys)} unique, {len(expected)} expected")
    return rows


def margins_at(row: JointRow, loss_db: float, target_f_peak_hz: float,
               target_peaking_db: float) -> Optional[dict]:
    if not row.ok:
        return None
    link = (row.links or {}).get(str(float(loss_db)))
    if not link or not link.get("ok"):
        return None
    margins = dict(row.margins or {})
    margins["S8_eye_h"] = float(link["eye_h_v"]) - SPEC_EYE_H_MIN_V
    margins["S8_eye_w"] = float(link["eye_w_ui"]) - SPEC_EYE_W_MIN_UI
    margins.update(R.request_rows(float(row.f_peak_oct), float(row.peaking_db),
                                  float(target_f_peak_hz),
                                  float(target_peaking_db)))
    missing = [name for name in SPECS if name not in margins]
    if missing:
        raise KeyError(f"missing spec rows: {missing}")
    return margins


def is_compliant(row: JointRow, loss_db: float, target_f_peak_hz: float,
                 target_peaking_db: float) -> bool:
    margins = margins_at(row, loss_db, target_f_peak_hz, target_peaking_db)
    return bool(margins is not None and
                all(v == 0.0 for v in R.shortfalls(margins, SPECS).values()))


def analyse(rows: Sequence[JointRow]) -> dict:
    corners = sorted({r.corner for r in rows})
    requests = [(float(pk), float(f)) for pk in PEAKING_REQUESTS
                for f in FREQ_REQUESTS]
    by_corner = collections.defaultdict(list)
    for row in rows:
        by_corner[row.corner].append(row)

    per_loss = []
    for loss in LOSSES_DB:
        full = 0
        solvable_pairs = 0
        for pk, freq in requests:
            served = 0
            for corner in corners:
                good = [r for r in by_corner[corner]
                        if is_compliant(r, loss, freq, pk)]
                solvable_pairs += bool(good)
                served += bool(good)
            full += served == len(corners)
        scorable = sum(1 for r in rows
                       if r.ok and (r.links or {}).get(str(float(loss)), {}).get("ok"))
        per_loss.append({"loss_db": loss, "n_scorable": scorable,
                         "n_solvable_corner_requests": solvable_pairs,
                         "n_requests_served_all_corners": full})

    n_all_solvable = 0
    n_need_adapt = 0
    n_best_moves = 0
    atten_best = collections.Counter()
    for corner in corners:
        for pk, freq in requests:
            sets = []
            bests = []
            for loss in LOSSES_DB:
                good = [r for r in by_corner[corner]
                        if is_compliant(r, loss, freq, pk)]
                sets.append({r.setting for r in good})
                if good:
                    best = max(good, key=lambda r: (
                        float(r.links[str(float(loss))]["eye_h_v"]), -r.setting))
                    bests.append(best.setting)
                    atten_best[best.atten_code] += 1
            if all(sets):
                n_all_solvable += 1
                if not set.intersection(*sets):
                    n_need_adapt += 1
                if len(set(bests)) > 1:
                    n_best_moves += 1

    expected = len(ATTEN_CODES) * N_BANK_CODES * len(corners)
    return {
        "n_rows": len(rows), "n_expected": expected,
        "membership_ok": len(rows) == expected and
                         len({(r.setting, r.corner) for r in rows}) == expected,
        "n_corners": len(corners), "n_requests": len(requests),
        "per_loss": per_loss,
        "channel_adaptation": {
            "n_corner_requests_solvable_on_every_channel": n_all_solvable,
            "n_needing_different_setting_for_compliance": n_need_adapt,
            "n_whose_best_eye_setting_moves": n_best_moves,
            "best_setting_attenuator_histogram": {
                str(k): int(v) for k, v in sorted(atten_best.items())},
        },
    }


def diagnose(rows: Sequence[JointRow], loss_db: float = 3.0,
             requests: Optional[Sequence[tuple[float, float]]] = None) -> dict:
    """Explain unserved corner/requests without changing a circuit value.

    ``least_extra_attenuation_db`` is only the compression ratio expressed in
    dB.  It is a lower-bound diagnostic, not a prediction that a resized
    attenuator will pass: extra attenuation also changes noise and eye height.
    """
    requests = list(requests if requests is not None else
                    ((float(pk), float(freq)) for pk in PEAKING_REQUESTS
                     for freq in FREQ_REQUESTS))
    by_corner = collections.defaultdict(list)
    for row in rows:
        by_corner[row.corner].append(row)
    non_eye_specs = tuple(name for name in SPECS
                          if not name.startswith("S8_"))
    unserved = []
    single_violation = collections.Counter()
    extra_values = []
    n_at_max_atten = 0

    for corner in sorted(by_corner):
        corner_rows = by_corner[corner]
        for request_id, (target_pk, target_freq) in enumerate(requests):
            if any(is_compliant(row, loss_db, target_freq, target_pk)
                   for row in corner_rows):
                continue

            scored = []
            compressed = []
            for row in corner_rows:
                margins = margins_at(row, loss_db, target_freq, target_pk)
                if margins is not None:
                    sf = R.shortfalls(margins, SPECS)
                    violations = sorted(name for name, value in sf.items()
                                        if value > 0.0)
                    scored.append((len(violations), max(sf.values()),
                                   sum(sf.values()), row.setting,
                                   row, violations))

                if not row.ok:
                    continue
                link = (row.links or {}).get(str(float(loss_db)), {})
                if link.get("reason") != "compression":
                    continue
                shape_margins = dict(row.margins or {})
                shape_margins.update(R.request_rows(
                    float(row.f_peak_oct), float(row.peaking_db),
                    float(target_freq), float(target_pk)))
                if not all(float(shape_margins[name]) >= 0.0
                           for name in non_eye_specs):
                    continue
                demand = float(link["demand_mvpp"])
                limit = float(link["limit_mvpp"])
                if not demand > limit > 0.0:
                    raise ValueError("compression row has an invalid swing ratio")
                extra_db = 20.0 * math.log10(demand / limit)
                compressed.append((extra_db, row.setting, row, demand, limit))

            best = min(scored, key=lambda item: item[:4]) if scored else None
            least = min(compressed, key=lambda item: item[:2]) if compressed else None
            violations = [] if best is None else best[5]
            if len(violations) == 1:
                single_violation[violations[0]] += 1
            if least is not None:
                extra_values.append(least[0])
                n_at_max_atten += least[2].atten_code == max(ATTEN_CODES)

            unserved.append({
                "corner": corner, "request_id": request_id,
                "target_peaking_db": float(target_pk),
                "target_f_peak_hz": float(target_freq),
                "n_scorable": len(scored),
                "best_scorable_setting": (None if best is None else
                                           best[4].setting),
                "best_scorable_violations": violations,
                "shape_compliant_compressed_candidates": len(compressed),
                "least_extra_attenuation_db": (None if least is None else
                                                least[0]),
                "least_extra_setting": (None if least is None else
                                         least[2].setting),
                "least_extra_atten_code": (None if least is None else
                                            least[2].atten_code),
                "least_extra_demand_mvpp": (None if least is None else
                                             least[3]),
                "least_extra_limit_mvpp": (None if least is None else
                                            least[4]),
            })

    return {
        "loss_db": float(loss_db), "n_rows": len(rows),
        "n_corners": len(by_corner), "n_requests": len(requests),
        "n_unserved_corner_requests": len(unserved),
        "best_scorable_single_violation_histogram": {
            key: int(value) for key, value in sorted(single_violation.items())},
        "n_with_shape_compliant_compressed_candidate": len(extra_values),
        "n_min_extra_candidate_at_max_attenuator": n_at_max_atten,
        "least_extra_attenuation_db_min": (min(extra_values)
                                            if extra_values else None),
        "least_extra_attenuation_db_max": (max(extra_values)
                                            if extra_values else None),
        "extra_attenuation_interpretation": (
            "compression-ratio lower bound only; noise and eye are unverified"),
        "unserved": unserved,
    }


def _decoded_sha256(path: Path) -> str:
    opener = gzip.open if path.suffix == ".gz" else open
    digest = hashlib.sha256()
    with opener(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def run_diagnosis(source: Optional[Path] = None) -> dict:
    """Write the deterministic, zero-SPICE boundary diagnosis."""
    archive = Path(str(RUN_LOG) + ".gz")
    source = Path(source) if source is not None else (
        archive if archive.exists() else RUN_LOG)
    if not source.exists():
        raise FileNotFoundError(f"joint-bank journal not found: {source}")
    out = diagnose(_load_rows(source))
    out["source"] = source.name
    out["source_decoded_sha256"] = _decoded_sha256(source)
    out["scope"] = ("post-outcome descriptive diagnosis; zero SPICE and no "
                    "circuit, range, tolerance or reward change")
    DIAGNOSIS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def run(workers: int = 1, resume: bool = False) -> dict:
    from nebula.experiments.exp_tuning_bank import _base_from_artifacts
    base_u = _base_from_artifacts()
    rows_before = (len(_load_rows(RUN_LOG))
                   if resume and RUN_LOG.exists() else 0)
    t0 = time.time()
    rows = sweep(base_u, workers=workers, resume=resume)
    analysis = analyse(rows)
    elapsed_s = time.time() - t0
    out = {
        "task": "real attenuator x CTLE bank over 45 PVT corners and 7 channels",
        "base_design_id": design_id(sizing_from_u(np.asarray(base_u))),
        "base_u": [float(x) for x in base_u],
        "geometry": {"attenuator_codes": len(ATTEN_CODES),
                     "ctle_codes": N_BANK_CODES, "n_rs": N_RS, "n_cs": N_CS,
                     "rs_span": RS_SPAN, "cs_span": CS_SPAN},
        "losses_db": list(LOSSES_DB), "analysis": analysis,
        "spice_invocations": len(rows),
        "resumed": bool(resume),
        "rows_before_segment": rows_before,
        "spice_invocations_this_segment": len(rows) - rows_before,
        "retry_decks_unbilled": True,
        "wall_clock_s": elapsed_s,
        "wall_clock_scope": ("resume segment only" if resume else
                             "complete uninterrupted run"),
        "scope": ("45 mandated PVT corners at the design load, V6_SPECS with "
                  "operating-point HD3; seven constructed channel losses. "
                  "Not the 135-point load grid."),
    }
    RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def _report(out: dict) -> None:
    a = out["analysis"]
    print()
    print("=" * 78)
    print("JOINT ATTENUATOR / CTLE BANK")
    print("=" * 78)
    print(f"  rows {a['n_rows']}/{a['n_expected']}  membership "
          f"{'PASS' if a['membership_ok'] else 'FAIL'}")
    print("  loss dB   scorable settings   requests at all 45 corners")
    for row in a["per_loss"]:
        print(f"   {row['loss_db']:5.1f}       {row['n_scorable']:5d}"
              f"                    {row['n_requests_served_all_corners']:2d}/16")
    ch = a["channel_adaptation"]
    print(f"  corner/request pairs solvable on all channels: "
          f"{ch['n_corner_requests_solvable_on_every_channel']}")
    print(f"  pairs requiring channel-specific setting for compliance: "
          f"{ch['n_needing_different_setting_for_compliance']}")
    print(f"  pairs whose best-eye setting moves: "
          f"{ch['n_whose_best_eye_setting_moves']}")
    timing_scope = out.get("wall_clock_scope", "scope not recorded")
    print(f"  wall clock ({timing_scope}) "
          f"{out['wall_clock_s'] / 60:.1f} min")


def _report_diagnosis(out: dict) -> None:
    print()
    print("=" * 78)
    print("JOINT BANK - 3 DB FAILURE DIAGNOSIS")
    print("=" * 78)
    print(f"  unserved corner/request pairs: "
          f"{out['n_unserved_corner_requests']}")
    print(f"  closest scorable one-row misses: "
          f"{out['best_scorable_single_violation_histogram']}")
    print(f"  pairs with a shape-compliant compressed candidate: "
          f"{out['n_with_shape_compliant_compressed_candidate']}")
    print(f"  least extra attenuation lower-bound range: "
          f"{out['least_extra_attenuation_db_min']:.3f} to "
          f"{out['least_extra_attenuation_db_max']:.3f} dB")
    print("  NOTE: this range does not verify noise or eye height")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--resume", action="store_true")
    mode.add_argument("--analyse", action="store_true")
    mode.add_argument("--diagnose", action="store_true")
    ap.add_argument("--workers", type=int, default=1)
    args = ap.parse_args(argv)
    if args.run or args.resume:
        out = run(workers=max(1, args.workers), resume=args.resume)
        _report(out)
        return 0 if out["analysis"]["membership_ok"] else 1
    if args.analyse:
        if not RESULTS.exists():
            raise SystemExit(f"{RESULTS.name} missing: run the sweep first")
        _report(json.loads(RESULTS.read_text(encoding="utf-8")))
        return 0
    if args.diagnose:
        _report_diagnosis(run_diagnosis())
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
