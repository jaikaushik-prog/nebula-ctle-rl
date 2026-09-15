"""Entry 83: focused real-PMOS test of a 7 dB attenuator top code.

The experiment is deliberately small.  It re-runs only the 14 unique physical
points selected by the committed entry-82 diagnosis, which cover all 16
unserved 3 dB requests, plus code-0/code-7 TT controls.  Passing this probe
makes 7 dB a candidate; it does not change D11's registered 5.933 dB range.

    python -m nebula.experiments.exp_atten_range_probe --run
    python -m nebula.experiments.exp_atten_range_probe --analyse
"""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import nebula.rl.reward_v1 as R
from nebula.common.types import Corner, SPEC_VN_IN_MAX_VRMS
from nebula.device import attenuator as AT
from nebula.experiments import exp_joint_bank as J
from nebula.experiments.adaptive_screen import (
    CL_MID_F,
    ScreenPoint,
    evaluate_at_points,
)
from nebula.experiments.exp_bank_sweep import SPECS, _strip_request_rows
from nebula.experiments.exp_tuning_bank import bank

HERE = Path(__file__).resolve().parent
DIAGNOSIS = HERE / "joint_bank_diagnosis.json"
RESULTS = HERE / "atten_range_probe_results.json"

PROBE_TOP_DB: float = 7.0
PROBE_MAX_X: float = 10.0 ** (PROBE_TOP_DB / 20.0)
PROBE_ATTEN_CODE: int = AT.N_CODES - 1
PROBE_BANK_CODE: int = 4 * 8 + 3
LOSS_SHORT_DB: float = 3.0
LOSS_LONG_DB: float = 12.0
EXPECTED_CRITICAL: int = 14
EXPECTED_REQUESTS: int = 16
N_RS, N_CS, RS_SPAN, CS_SPAN = 8, 8, 0.38, 0.20


@dataclass(frozen=True)
class CriticalTask:
    corner_label: str
    corner: Corner
    setting: int
    atten_code: int
    bank_code: int
    request_ids: tuple[int, ...]
    requests: tuple[tuple[int, float, float], ...]


def _parse_corner(label: str) -> Corner:
    process, vdd, temp = str(label).split("/")
    if not temp.endswith("C"):
        raise ValueError(f"invalid corner label {label!r}")
    return Corner(process, float(vdd), float(temp[:-1]))


def critical_tasks(diagnosis: dict) -> list[CriticalTask]:
    """Collapse 16 request rows onto their 14 unique SPICE measurements."""
    grouped: dict[tuple[str, int], list[dict]] = {}
    seen_requests = set()
    for row in diagnosis.get("unserved", []):
        request_id = int(row["request_id"])
        request_key = (str(row["corner"]), request_id)
        if request_key in seen_requests:
            raise ValueError(f"duplicate diagnosis corner/request {request_key}")
        seen_requests.add(request_key)
        setting = int(row["least_extra_setting"])
        atten_code, bank_code = J.split_setting(setting)
        if int(row["least_extra_atten_code"]) != atten_code:
            raise ValueError("diagnosis attenuator code disagrees with setting")
        if atten_code != PROBE_ATTEN_CODE:
            raise ValueError("entry 83 only tests failures selected at top code 7")
        grouped.setdefault((str(row["corner"]), setting), []).append(row)

    tasks = []
    for (corner_label, setting), rows in sorted(grouped.items()):
        atten_code, bank_code = J.split_setting(setting)
        requests = tuple(sorted(
            (int(row["request_id"]), float(row["target_peaking_db"]),
             float(row["target_f_peak_hz"]))
            for row in rows
        ))
        tasks.append(CriticalTask(
            corner_label=corner_label, corner=_parse_corner(corner_label),
            setting=setting, atten_code=atten_code, bank_code=bank_code,
            request_ids=tuple(row[0] for row in requests), requests=requests))
    return tasks


def _links(point) -> dict:
    by_loss = point.links_by_loss or {}
    return {
        str(loss): J._compact_link(by_loss.get(loss))
        for loss in (LOSS_SHORT_DB, LOSS_LONG_DB)
    }


def _measurement_row(kind: str, corner_label: str, bank_code: int,
                     atten_code: int, ev, requests=()) -> dict:
    point = ev.points[0] if ev.points else None
    if point is None or not point.ok:
        return {
            "kind": kind, "corner": corner_label,
            "bank_code": int(bank_code), "atten_code": int(atten_code),
            "device_ok": False,
            "reason": (point.reason if point is not None else ev.reason),
            "g_dc_db": None, "noise_mvrms": None, "links": {},
            "requests": [
                {"request_id": int(request_id), "scorable": False,
                 "compliant": False, "violations": ["unscorable"]}
                for request_id, _, _ in requests
            ],
        }

    links = _links(point)
    joint = J.JointRow(
        setting=J.setting_id(atten_code, bank_code),
        atten_code=int(atten_code), bank_code=int(bank_code),
        i_rs=int(bank_code) // N_CS, i_cs=int(bank_code) % N_CS,
        corner=corner_label, ok=True, peaking_db=point.peaking_db,
        f_peak_oct=point.f_peak_oct,
        margins=_strip_request_rows(point.margins),
        eye_h_v=point.eye_h_v, eye_w_ui=point.eye_w_ui,
        power_w=point.power_w, hd3_nyq_dbc=point.hd3_nyq_dbc,
        links=links)
    scored_requests = []
    for request_id, target_peaking_db, target_f_peak_hz in requests:
        margins = J.margins_at(joint, LOSS_SHORT_DB, target_f_peak_hz,
                               target_peaking_db)
        if margins is None:
            scored_requests.append({
                "request_id": int(request_id), "scorable": False,
                "compliant": False, "violations": ["unscorable"]})
            continue
        shortfalls = R.shortfalls(margins, SPECS)
        violations = sorted(name for name, value in shortfalls.items()
                            if float(value) > 0.0)
        scored_requests.append({
            "request_id": int(request_id), "scorable": True,
            "compliant": not violations, "violations": violations,
            "margins": {name: float(margins[name]) for name in SPECS},
        })

    return {
        "kind": kind, "corner": corner_label,
        "bank_code": int(bank_code), "atten_code": int(atten_code),
        "device_ok": True, "reason": None,
        "g_dc_db": float(point.g_dc_db),
        "noise_mvrms": float(point.noise_vrms) * 1e3,
        "peaking_db": float(point.peaking_db),
        "f_peak_hz": 2.5e9 * 2.0 ** float(point.f_peak_oct),
        "links": links, "requests": scored_requests,
    }


def _measure(base_u: Sequence[float], bank_code: int, corner: Corner,
             atten_code: int, kind: str, requests=(),
             atten_max_x: float = PROBE_MAX_X) -> dict:
    settings = bank(base_u, n_rs=N_RS, n_cs=N_CS, rs_span=RS_SPAN,
                    cs_span=CS_SPAN)
    st = settings[int(bank_code)]
    label = f"{corner.process}/{corner.vdd_scale:.2f}/{corner.temp_c:g}C"
    ev = evaluate_at_points(
        st.u, [ScreenPoint(corner, CL_MID_F, label)],
        target_f_peak_hz=1.9e9, target_peaking_db=7.5, specs=SPECS,
        link_losses_db=(LOSS_SHORT_DB, LOSS_LONG_DB),
        atten_code=int(atten_code), atten_max_x=float(atten_max_x))
    return _measurement_row(kind, label, bank_code, atten_code, ev, requests)


def _unique_key(row: dict) -> tuple:
    if row.get("kind") == "critical":
        return ("critical", row.get("corner"), int(row.get("bank_code", -1)))
    return ("control", int(row.get("atten_code", -1)))


def analyse(rows: Sequence[dict], expected_critical: int = EXPECTED_CRITICAL,
            expected_requests: int = EXPECTED_REQUESTS,
            wall_clock_s: float = 0.0) -> dict:
    rows = list(rows)
    critical = [row for row in rows if row.get("kind") == "critical"]
    controls = [row for row in rows if row.get("kind") == "control"]
    keys = [_unique_key(row) for row in rows]
    control_by_code = {int(row["atten_code"]): row for row in controls}

    membership_ok = bool(
        len(rows) == expected_critical + 2
        and len(critical) == expected_critical
        and len(controls) == 2
        and len(keys) == len(set(keys))
        and set(control_by_code) == {0, PROBE_ATTEN_CODE})
    all_device_ok = membership_ok and all(
        bool(row.get("device_ok")) for row in rows)

    c0 = control_by_code.get(0, {})
    c7 = control_by_code.get(PROBE_ATTEN_CODE, {})
    g0, g7 = c0.get("g_dc_db"), c7.get("g_dc_db")
    realised = (float(g0) - float(g7)
                if g0 is not None and g7 is not None else None)
    top_noise = c7.get("noise_mvrms")

    request_rows = [req for row in critical
                    for req in row.get("requests", [])]
    recovered = sum(bool(req.get("scorable") and req.get("compliant"))
                    for req in request_rows)
    long_ok = sum(bool((row.get("links") or {}).get("12.0", {}).get("ok"))
                  for row in critical)
    top_links = c7.get("links") or {}

    checks = {
        "Q1": bool(membership_ok and all_device_ok),
        "Q2": bool(realised is not None and 6.75 <= realised <= 7.25),
        "Q3": bool(top_noise is not None
                   and float(top_noise) < SPEC_VN_IN_MAX_VRMS * 1e3),
        "Q4": bool(len(request_rows) == expected_requests
                   and recovered == expected_requests),
        "Q5": bool(long_ok == expected_critical),
        "Q6": bool(top_links.get("3.0", {}).get("ok")
                   and top_links.get("12.0", {}).get("ok")
                   and float(wall_clock_s) < 60.0),
    }
    return {
        "membership_ok": membership_ok,
        "all_device_ok": all_device_ok,
        "n_rows": len(rows), "n_critical_rows": len(critical),
        "n_control_rows": len(controls),
        "n_request_rows": len(request_rows),
        "n_recovered_requests": recovered,
        "n_long_channel_scorable": long_ok,
        "realised_top_attenuation_db": realised,
        "top_noise_mvrms": top_noise,
        "wall_clock_s": float(wall_clock_s),
        "checks": checks, "passed": all(checks.values()),
    }


def run(base_u: Optional[Sequence[float]] = None) -> dict:
    if RESULTS.exists():
        raise FileExistsError(f"refusing to overwrite {RESULTS.name}")
    if not DIAGNOSIS.exists():
        raise FileNotFoundError(f"diagnosis missing: {DIAGNOSIS}")
    diagnosis = json.loads(DIAGNOSIS.read_text(encoding="utf-8"))
    tasks = critical_tasks(diagnosis)
    if len(tasks) != EXPECTED_CRITICAL:
        raise ValueError(f"expected {EXPECTED_CRITICAL} critical points, "
                         f"found {len(tasks)}")
    if sum(len(task.request_ids) for task in tasks) != EXPECTED_REQUESTS:
        raise ValueError(f"expected {EXPECTED_REQUESTS} request rows")

    source = HERE / str(diagnosis["source"])
    if not source.exists():
        raise FileNotFoundError(f"diagnosis source missing: {source}")
    source_hash = J._decoded_sha256(source)
    if source_hash != diagnosis["source_decoded_sha256"]:
        raise ValueError("diagnosis source hash changed")

    if base_u is None:
        from nebula.experiments.exp_tuning_bank import _base_from_artifacts
        base_u = _base_from_artifacts()
    base_u = tuple(float(value) for value in base_u)

    t0 = time.perf_counter()
    rows = []
    for index, task in enumerate(tasks, 1):
        rows.append(_measure(base_u, task.bank_code, task.corner,
                             task.atten_code, "critical", task.requests))
        print(f"  critical {index}/{len(tasks)}: {task.corner_label} "
              f"bank {task.bank_code}", flush=True)
    control_corner = Corner("tt", 1.0, 27.0)
    for code in (0, PROBE_ATTEN_CODE):
        rows.append(_measure(base_u, PROBE_BANK_CODE, control_corner,
                             code, "control"))
        print(f"  control code {code}: complete", flush=True)
    elapsed = time.perf_counter() - t0

    summary = analyse(rows, wall_clock_s=elapsed)
    out = {
        "task": "entry 83 focused 7 dB attenuator top-code probe",
        "probe_top_db": PROBE_TOP_DB, "probe_max_x": PROBE_MAX_X,
        "production_atten_max_x_unchanged": AT.ATTEN_MAX_X,
        "production_top_db_unchanged": AT.attenuation_db(AT.N_CODES - 1),
        "base_u": list(base_u),
        "source_diagnosis": DIAGNOSIS.name,
        "source_joint_bank": source.name,
        "source_decoded_sha256": source_hash,
        "spice_invocations": len(rows), "rows": rows,
        "summary": summary,
        "scope": ("focused diagnostic only; no D11 range adoption, no full "
                  "PVT coverage claim and no RL training"),
    }
    RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def _report(out: dict) -> None:
    summary = out["summary"]
    print()
    print("=" * 72)
    print("ENTRY 83 - FOCUSED 7.0 dB ATTENUATOR PROBE")
    print("=" * 72)
    print(f"  SPICE rows: {out['spice_invocations']}  "
          f"device valid: {summary['all_device_ok']}")
    print(f"  realised top attenuation: "
          f"{summary['realised_top_attenuation_db']!r} dB")
    print(f"  TT top-code noise: {summary['top_noise_mvrms']!r} mVrms")
    print(f"  recovered 3 dB requests: "
          f"{summary['n_recovered_requests']}/{summary['n_request_rows']}")
    print(f"  12 dB critical links: "
          f"{summary['n_long_channel_scorable']}/"
          f"{summary['n_critical_rows']}")
    print(f"  elapsed: {summary['wall_clock_s']:.2f} s")
    for name, passed in summary["checks"].items():
        print(f"  {name}: {'PASS' if passed else 'FAIL'}")
    print(f"  OVERALL: {'PASS' if summary['passed'] else 'FAIL'}")
    print("  Scope: diagnostic candidate only; D11 remains unchanged.")


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
