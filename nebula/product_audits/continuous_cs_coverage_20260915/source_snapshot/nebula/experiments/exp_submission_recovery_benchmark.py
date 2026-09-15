"""Frozen target coverage and matched complete-workflow recovery benchmark.

preflight/check never run SPICE. coverage/benchmark are explicit measurement
commands; each workflow uses a fresh Python interpreter and fresh raw evidence.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "nebula/SUBMISSION_RECOVERY_BENCHMARK_PLAN_20260915.md"
MAX_CANDIDATES = 8
MAX_WALL_S = 10800.
SCHEMA = "nebula-physical-recovery-benchmark-v1"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n",
                          encoding="utf-8", newline="\n")


def target(boost, ghz, *, diagnostic=False):
    return dict(target_id=f"{boost:g}db_{ghz:g}ghz".replace(".", "p"),
                peaking_db=float(boost), f_peak_hz=float(ghz)*1e9,
                request_text=f"{boost:g} dB at {ghz:g} GHz",
                diagnostic_exposed=diagnostic)


def schedule(purpose):
    if purpose == "coverage":
        points = [target(b, f) for b in (3, 6, 9, 12) for f in (1.25, 1.9, 2.5)]
        points.append(target(6, 2.1, diagnostic=True))
        return [dict(p, purpose=purpose, repeat=0, selection_mode="rl",
                     max_candidates=MAX_CANDIDATES) for p in points]
    if purpose != "benchmark":
        raise ValueError("unknown experiment purpose")
    points = [target(3, 1.9), target(6, 2.1, diagnostic=True),
              target(9, 1.9), target(12, 2.5)]
    jobs = []
    for repeat in range(3):
        for index, point in enumerate(points):
            order = ("rl", "classical") if (repeat + index) % 2 == 0 else ("classical", "rl")
            for arm in order:
                jobs.append(dict(point, purpose=purpose, repeat=repeat,
                                 selection_mode=arm, max_candidates=MAX_CANDIDATES))
    return jobs


def key(row):
    return row["purpose"], row["target_id"], row["repeat"], row["selection_mode"]


def validate_workflow(row):
    duration = row.get("parent_wall_s")
    if not isinstance(duration, (float, int)) or not math.isfinite(duration) or duration < 0:
        raise ValueError("invalid parent elapsed time")
    attempts = row.get("attempts") or []
    settings = [a["setting"] for a in attempts]
    if len(settings) != len(set(settings)) or len(settings) > MAX_CANDIDATES:
        raise ValueError("duplicate candidate or candidate budget exceeded")
    calls = row.get("spice_calls")
    if calls is not None:
        if not isinstance(calls, int) or calls < 0:
            raise ValueError("invalid SPICE calls")
        recorded = [a.get("spice_calls") for a in attempts]
        if any(not isinstance(n, int) or not 0 <= n <= 137 for n in recorded) or sum(recorded) != calls:
            raise ValueError("SPICE calls do not bill every attempt")
    accepted = [a for a in attempts if a.get("accepted")]
    if len(accepted) > 1 or (accepted and not attempts[-1].get("accepted")):
        raise ValueError("continued after accepted candidate")
    if row.get("delivered_success"):
        if (row.get("status") != "accepted" or len(accepted) != 1 or calls is None
                or not row.get("output_complete") or not row.get("request_met")
                or accepted[0].get("spice_calls") != 137
                or accepted[0].get("n_pass") != 315 or accepted[0].get("n_points") != 315):
            raise ValueError("delivered success lacks complete physical and artifact acceptance")


def summarise(rows):
    seen = set()
    for row in rows:
        if key(row) in seen:
            raise ValueError("duplicate workflow")
        seen.add(key(row))
        validate_workflow(row)
    known = sum(r["spice_calls"] if r.get("spice_calls") is not None else
                r.get("known_spice_calls", sum(a.get("spice_calls") or 0 for a in r.get("attempts", [])))
                for r in rows)
    unknown = sum(r.get("spice_calls") is None for r in rows)
    arms = {}
    for arm in ("rl", "classical"):
        selected = [r for r in rows if r["purpose"] == "benchmark" and r["selection_mode"] == arm]
        passed = [r for r in selected if r["delivered_success"]]
        arms[arm] = dict(attempted_workflows=len(selected), delivered_successes=len(passed),
                         success_fraction=len(passed)/len(selected) if selected else None,
                         wall_s=sum(r["parent_wall_s"] for r in selected),
                         rejected_candidates=sum(not a.get("accepted") for r in selected
                                                 for a in r.get("attempts", [])),
                         mean_abs_peaking_error_db=statistics.mean(
                             abs(r["peaking_error_db"]) for r in passed) if passed else None,
                         mean_abs_frequency_error_oct=statistics.mean(
                             abs(r["frequency_error_oct"]) for r in passed) if passed else None)
    paired = {}
    for row in rows:
        if row["purpose"] == "benchmark":
            paired.setdefault((row["target_id"], row["repeat"]), {})[row["selection_mode"]] = row
    pairs = [p for p in paired.values() if set(p) == {"rl", "classical"}]
    ratios = [p["classical"]["parent_wall_s"]/p["rl"]["parent_wall_s"] for p in pairs
              if p["rl"]["delivered_success"] and p["classical"]["delivered_success"]
              and p["rl"]["parent_wall_s"] > 0]
    coverage = [r for r in rows if r["purpose"] == "coverage"]
    return dict(schema=SCHEMA, completed_workflows=len(rows), arms=arms,
                readiness_matrix=readiness_matrix(rows),
                coverage=dict(attempted_workflows=len(coverage),
                              delivered_successes=sum(r["delivered_success"] for r in coverage),
                              rows=coverage),
                total_parent_wall_s=sum(r["parent_wall_s"] for r in rows),
                total_spice_calls=None if unknown else known, known_spice_calls=known,
                known_charged_invocations=sum(r["spice_calls"] if r.get("spice_calls") is not None
                    else r.get("known_charged_invocations", r.get("known_spice_calls", 0)) for r in rows),
                unknown_call_workflows=unknown, matched_pairs=len(pairs),
                both_success_pairs=len(ratios), paired_classical_over_rl_ratios=ratios,
                median_classical_over_rl_ratio=statistics.median(ratios) if ratios else None,
                scope="Exposed finite target grid; physical CTLE plus ideal DFE; not full-range or transistor-receiver signoff.",
                timing_scope="Fresh interpreter launch through complete workflow output, accounting receipt and exit; OS/filesystem caches not cleared.",
                ratio_scope="Ratios only for matched target/repeat pairs with both delivered successfully; all failed work remains billed separately.",
                statistical_scope="Three planned repeats per target are descriptive; no significance or universal speedup claim.")


def frozen_plan():
    committed = subprocess.check_output(
        ["git", "show", "HEAD:nebula/SUBMISSION_RECOVERY_BENCHMARK_PLAN_20260915.md"], cwd=ROOT)
    if committed.replace(b"\r\n", b"\n") != PLAN.read_bytes().replace(b"\r\n", b"\n"):
        raise ValueError("benchmark plan must be committed unchanged before measurements")
    return sha(PLAN)


def environment_fingerprints():
    # Hash source and exact compressed assets; never copy PDK files into results.
    sources = set()
    for folder in ("nebula/device", "nebula/rl", "nebula/link", "nebula/common",
                   "nebula/experiments", "python_models"):
        sources.update((ROOT/folder).glob("*.py"))
    sources.update((ROOT/"nebula/report").glob("*schematic*.py"))
    sources.update(ROOT/p for p in (
        "nebula/design.py", "nebula/physical_design.py", "nebula/physical_recovery.py",
        "nebula/recovery_workflow.py", "nebula/report/product_scope.py",
        "nebula/llm/spec_parse.py", "nebula/physical_verified_registry.json",
        "nebula/device/spice/.spiceinit"))
    from nebula.experiments import exp_shielded_ppo as E, exp_joint_bank_73 as B
    assets = {E.source_path(), E.development_results_path(), E.policy_manifest_path(),
              B.ENTRY85, B.BASELINE_JOURNAL}
    assets.update((ROOT/"nebula/experiments").glob("*shielded*.npz"))
    assets.update((ROOT/"nebula/rl").rglob("*.npz"))
    entry85 = json.loads(B.ENTRY85.read_text(encoding="utf-8"))
    assets.add(B.HERE / entry85["root_source"])
    # Include every path explicitly named by the frozen policy manifest.
    manifest = json.loads(E.policy_manifest_path().read_text(encoding="utf-8"))
    def collect(value):
        if isinstance(value, dict):
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)
        elif isinstance(value, str) and value.endswith((".json", ".npz", ".gz", ".jsonl", ".pth", ".pt")):
            for parent in (ROOT, E.policy_manifest_path().parent):
                candidate = parent/value
                if candidate.is_file():
                    assets.add(candidate)
    collect(manifest)
    from nebula.device import pdk_trim as PT, sky130_runner as S
    from nebula.device.ngspice_runner import ngspice_path
    closure = {}
    for corner in ("tt", "ss", "ff", "sf", "fs"):
        PT._walk(S.lib_for_device(S.NFET_01V8, real_passives=True,
                                 section=corner, include_pfet=True), closure, set())
    exe = ngspice_path()
    return dict(source_sha256={p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(sources)},
                asset_sha256={p.resolve().as_posix(): sha(p) for p in sorted(assets)},
                pdk_include_closure_sha256={p.as_posix(): sha(p) for p in sorted(closure)},
                ngspice_path=str(exe), ngspice_sha256=sha(exe),
                python_executable=sys.executable, python_version=sys.version,
                model_scope="Actual five MOS-corner PFET-capable trimmed library include closure; passive typical, no mismatch.")


def preflight(out):
    out = Path(out).resolve()
    plan_hash = frozen_plan()
    occupied = active_ngspice()
    if occupied:
        raise RuntimeError(f"simulator slot occupied: {occupied}")
    out.mkdir(parents=True, exist_ok=False)
    config = dict(schema=SCHEMA, plan_sha256=plan_hash,
                  base_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                  working_tree_hashes_authoritative=True,
                  commit_scope="Base commit contains frozen plan; implementation identity is exact working-tree hashes and copied project-owned inputs.",
                  max_total_wall_s=MAX_WALL_S, max_candidates=MAX_CANDIDATES,
                  theoretical_call_ceiling=37*MAX_CANDIDATES*137,
                  coverage_schedule=schedule("coverage"), benchmark_schedule=schedule("benchmark"),
                  environment=environment_fingerprints(), measurement_started_utc=None,
                  preflight_cache_effect="File hashing touches source/model/asset pages; OS cache is not cold. Each measured workflow still loads assets in a fresh interpreter.")
    for name, digest in config["environment"]["source_sha256"].items():
        destination = out/"inputs"/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, destination)
        if sha(destination) != digest:
            raise ValueError("source snapshot changed during preflight")
    plan_copy = out/"inputs"/PLAN.relative_to(ROOT)
    plan_copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PLAN, plan_copy)
    write_json(out/"protocol.json", config)
    write_json(out/"protocol_sha256.json", {"protocol.json": sha(out/"protocol.json")})
    return config


def load_protocol(out):
    config = json.loads((out/"protocol.json").read_text())
    expected = json.loads((out/"protocol_sha256.json").read_text())["protocol.json"]
    if sha(out/"protocol.json") != expected or config["plan_sha256"] != frozen_plan():
        raise ValueError("frozen benchmark protocol changed")
    for name, digest in config["environment"]["source_sha256"].items():
        if sha(ROOT/name) != digest or sha(out/"inputs"/name) != digest:
            raise ValueError(f"source changed after preflight: {name}")
    for category in ("asset_sha256", "pdk_include_closure_sha256"):
        for path, digest in config["environment"][category].items():
            if sha(path) != digest:
                raise ValueError(f"frozen {category} changed: {path}")
    if sha(config["environment"]["ngspice_path"]) != config["environment"]["ngspice_sha256"]:
        raise ValueError("ngspice executable changed")
    return config


def _worker(payload_path):
    payload = json.loads(Path(payload_path).read_text())
    from nebula.recovery_workflow import run_request
    result = run_request(payload["request_text"], payload["output_dir"],
                         selection_mode=payload["selection_mode"], max_candidates=MAX_CANDIDATES)
    # Common geometry/reward helpers live under nebula.rl; only policy execution is forbidden.
    if payload["selection_mode"] == "classical" and "nebula.rl.hybrid_designer" in sys.modules:
        raise RuntimeError("classical workflow imported the policy proposer")
    return 0 if result.get("status") in ("accepted", "exhausted", "no_eligible") else 2


def _kill_tree(process):
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    else:
        import signal
        os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=30)


def run_jobs(out, purpose):
    out = Path(out).resolve()
    config = load_protocol(out)
    journal = out/"workflows.jsonl"
    rows = [json.loads(line) for line in journal.read_text().splitlines()] if journal.exists() else []
    if any(r["purpose"] == purpose for r in rows):
        raise ValueError("purpose already started; no favorable reruns or replacement")
    started_path = out/"measurement_started.json"
    if started_path.exists():
        start_utc = datetime.fromisoformat(json.loads(started_path.read_text())["utc"])
    else:
        start_utc = datetime.now(timezone.utc)
        write_json(started_path, {"utc": start_utc.isoformat()})
    reason = "schedule_complete"
    for index, job in enumerate(schedule(purpose)):
        occupied = active_ngspice()
        if occupied:
            reason = "simulator_slot_occupied"
            write_json(out/"blocked_simulator.json", {"processes":occupied,"next_job":job})
            break
        remaining = MAX_WALL_S - (datetime.now(timezone.utc)-start_utc).total_seconds()
        if remaining <= 0:
            reason = "registered_wall_budget_exhausted"
            break
        folder = out/f"{purpose}_{index:03d}_{job['target_id']}_{job['selection_mode']}_r{job['repeat']}"
        folder.mkdir(exist_ok=False)
        payload = dict(job, output_dir=str(folder/"output"))
        write_json(folder/"input.json", payload)
        command = [sys.executable, "-m", "nebula.experiments.exp_submission_recovery_benchmark",
                   "_worker", "--payload", str(folder/"input.json")]
        started = time.perf_counter()
        timed_out = False
        with (folder/"stdout.log").open("wb") as stdout, (folder/"stderr.log").open("wb") as stderr:
            process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr,
                                       start_new_session=os.name != "nt")
            try:
                code = process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                timed_out = True
                _kill_tree(process)
                code = process.returncode
        elapsed = time.perf_counter()-started
        receipt_path = folder/"output/workflow_receipt.json"
        receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else partial_recovery(folder/"output")
        row = dict(job, status=receipt.get("status", "incomplete_timeout" if timed_out else "worker_error"),
                   delivered_success=bool(code == 0 and not timed_out and receipt.get("delivered_success")),
                   parent_wall_s=elapsed, worker_exit_code=code, timed_out=timed_out,
                   spice_calls=receipt.get("spice_calls"), attempts=receipt.get("attempts", []),
                   known_spice_calls=receipt.get("known_spice_calls", 0),
                   known_charged_invocations=receipt.get("known_charged_invocations", receipt.get("known_spice_calls", 0)),
                   output_complete=receipt.get("output_complete", False),
                   request_met=receipt.get("request_met", False),
                   workflow_wall_s=receipt.get("wall_s"),
                   workflow_receipt=receipt_path.relative_to(out).as_posix() if receipt_path.exists() else None,
                   workflow_receipt_sha256=sha(receipt_path) if receipt_path.exists() else None,
                   peaking_error_db=None, frequency_error_oct=None)
        design_path = folder/"output/design.json"
        if design_path.exists():
            design = json.loads(design_path.read_text())
            match = design.get("request_match") or {}
            row["peaking_error_db"] = match.get("peaking_err_db")
            row["frequency_error_oct"] = match.get("f_peak_err_oct")
        validate_workflow(row)
        with journal.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(row, allow_nan=False)+"\n")
            stream.flush()
        rows.append(row)
        write_json(out/"summary.json", dict(summarise(rows), stop_reason=reason,
                   planned_coverage_workflows=13, planned_benchmark_workflows=24))
        if timed_out or row["spice_calls"] is None or code != 0:
            reason = "timeout_or_instrumentation_error"
            break
    result = dict(summarise(rows), stop_reason=reason,
                  planned_coverage_workflows=13, planned_benchmark_workflows=24,
                  coverage_complete=sum(r["purpose"] == "coverage" for r in rows)==13,
                  benchmark_complete=sum(r["purpose"] == "benchmark" for r in rows)==24)
    write_json(out/"summary.json", result)
    write_json(out/"result_sha256.json", {p.name: sha(p) for p in (journal, out/"summary.json") if p.exists()})
    return result



def active_ngspice():
    if os.name == "nt":
        output = subprocess.check_output(["tasklist", "/FO", "CSV", "/NH", "/FI",
                                          "IMAGENAME eq ngspice*"], text=True)
        return [{"pid":int(r[1]), "name":r[0]} for r in csv.reader(output.splitlines())
                if len(r) > 1 and r[0].lower().startswith("ngspice")]
    output = subprocess.check_output(["ps", "-eo", "pid=,comm="], text=True)
    rows = [line.split(None,1) for line in output.splitlines()]
    return [{"pid":int(r[0]), "name":r[1]} for r in rows
            if len(r)==2 and Path(r[1]).name.lower().startswith("ngspice")]


def readiness_matrix(rows):
    actual = {key(r):r for r in rows}
    return [dict(job, outcome=actual[key(job)]["status"] if key(job) in actual else "unrun",
                 delivered_success=actual[key(job)]["delivered_success"] if key(job) in actual else None,
                 spice_calls=actual[key(job)].get("spice_calls") if key(job) in actual else None)
            for job in schedule("coverage") + schedule("benchmark")]


def partial_recovery(output):
    recovery = Path(output)/"physical_recovery"
    complete = recovery/"recovery_receipt.json"
    progress = recovery/"progress.json"
    path = complete if complete.is_file() else progress
    receipt = json.loads(path.read_text()) if path.is_file() else {"attempts":[]}
    attempts = receipt.get("attempts", [])
    known_dirs = {Path(a["directory"]).resolve() for a in attempts if a.get("directory")}
    for folder in sorted(recovery.glob("candidate_*_setting_*")):
        if folder.resolve() in known_dirs:
            continue
        attempt = dict(setting=int(folder.name.rsplit("_",1)[1]), directory=str(folder.resolve()),
                       accepted=False, spice_calls=None, error="interrupted; no completed call ledger")
        failure = folder/"failure.json"
        result_path = folder/"result.json"
        if result_path.is_file():
            design = json.loads(result_path.read_text())
            attempt.update(spice_calls=design["simulations"]["total"],
                           n_pass=design["verification"]["n_pass"], n_points=design["verification"]["n_points"])
        elif failure.is_file():
            attempt["spice_calls"] = json.loads(failure.read_text()).get("spice_calls")
        charge_path = folder/"call_progress.json"
        if charge_path.is_file():
            charge = json.loads(charge_path.read_text())
            attempt["charged_invocations"] = charge.get("charged_invocations", charge.get("spice_calls"))
            attempt["invocation_state"] = charge.get("invocation_state")
            attempt["charge_scope"] = "Charged before invocation; interrupted process launch/completion is not established."
        attempts.append(attempt)
    receipt["attempts"] = attempts
    receipt["known_spice_calls"] = sum(a.get("spice_calls") or 0 for a in attempts)
    receipt["known_charged_invocations"] = sum(a.get("spice_calls") if a.get("spice_calls") is not None
                                                else a.get("charged_invocations") or 0 for a in attempts)
    if not complete.is_file():
        receipt["spice_calls"] = None
    receipt.update(status="incomplete_workflow", delivered_success=False, output_complete=False)
    return receipt


def verify_manifest(directory):
    directory = Path(directory).resolve()
    path = directory/"evidence_sha256.json"
    manifest = json.loads(path.read_text())
    for name, expected in manifest.items():
        source = (directory/name).resolve()
        if not source.is_relative_to(directory):
            raise ValueError("raw evidence manifest escapes its directory")
        if not source.is_file() or sha(source) != expected:
            raise ValueError(f"raw evidence hash mismatch: {name}")
    return len(manifest)


def check(out):
    out = Path(out).resolve()
    load_protocol(out)
    for name, expected in json.loads((out/"result_sha256.json").read_text()).items():
        if Path(name).name != name or sha(out/name) != expected:
            raise ValueError("parent result hash mismatch")
    rows = [json.loads(line) for line in (out/"workflows.jsonl").read_text().splitlines()]
    for row in rows:
        validate_workflow(row)
        if row.get("workflow_receipt"):
            path = (out/row["workflow_receipt"]).resolve()
            if not path.is_relative_to(out) or sha(path) != row["workflow_receipt_sha256"]:
                raise ValueError("workflow receipt hash mismatch")
            receipt = json.loads(path.read_text())
            for field in ("attempts", "spice_calls", "output_complete", "request_met"):
                if row.get(field) != receipt.get(field):
                    raise ValueError("parent row differs from workflow receipt")
            recovery_dir = path.parent/"physical_recovery"
            if (recovery_dir/"evidence_sha256.json").exists():
                verify_manifest(recovery_dir)
            elif receipt.get("spice_calls"):
                raise ValueError("completed physical work lacks raw manifest")
            for attempt in receipt.get("attempts", []):
                folder = Path(attempt["directory"]).resolve()
                if not folder.is_relative_to(recovery_dir.resolve()):
                    raise ValueError("candidate evidence escapes workflow")
                verify_manifest(folder)
            for name, expected in receipt.get("artifact_sha256", {}).items():
                artifact = (path.parent/name).resolve()
                if not artifact.is_relative_to(path.parent) or sha(artifact) != expected:
                    raise ValueError("exported artifact hash mismatch")
    result = summarise(rows)
    saved = json.loads((out/"summary.json").read_text())
    if any(saved.get(k) != value for k, value in result.items()):
        raise ValueError("summary differs from preserved workflow records")
    return dict(status="PASS", checked_workflows=len(rows), simulations_run=0)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("preflight", "coverage", "benchmark", "check"):
        child = sub.add_parser(command)
        child.add_argument("--out", type=Path, required=True)
    child = sub.add_parser("_worker")
    child.add_argument("--payload", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "_worker":
        return _worker(args.payload)
    operation = {"preflight": preflight, "coverage": lambda p: run_jobs(p, "coverage"),
                 "benchmark": lambda p: run_jobs(p, "benchmark"), "check": check}[args.command]
    result = operation(args.out)
    print(json.dumps(result if args.command != "preflight" else
                     {"status": "FROZEN", "simulations_run": 0}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

