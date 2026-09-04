"""Dependency-free local web interface for the verified Nebula pipeline.

The browser never calculates specifications.  This module calls the existing
natural-language parser, design front door, artifact writer and Touchstone
profiler, then reduces their recorded outputs into a presentation-only JSON
view.  Expensive design work runs on one background worker so the interface
remains responsive and concurrent clicks cannot compete for ngspice.
"""

from __future__ import annotations

import argparse
import io
import json
import mimetypes
import re
import tempfile
import threading
import time
import uuid
import webbrowser
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional, Sequence
from urllib.parse import parse_qs, unquote, urlparse

from nebula.common.types import (
    SPEC_AREA_MAX_MM2,
    SPEC_EYE_H_MIN_V,
    SPEC_EYE_W_MIN_UI,
    SPEC_F_PEAK_HZ_RANGE,
    SPEC_HD3_MAX_DBC,
    SPEC_PEAKING_DB_RANGE,
    SPEC_POWER_MAX_W,
    SPEC_VN_IN_MAX_VRMS,
)
from nebula.llm.spec_parse import SpecOutOfRange, parse_request


ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = Path(__file__).with_name("static")
DEMO_DIR = ROOT / "nebula" / "product_demo" / "rl_hybrid_9db_1p9ghz"
MAX_JSON_BYTES = 64 * 1024
MAX_CHANNEL_BYTES = 32 * 1024 * 1024
WORKER_LIMIT = 1
TOUCHSTONE_NAME = re.compile(r"^[^/\\]+\.s([1-9]\d*)p$", re.I)


def _number(value: Any) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out


def _spec_rows(design: dict) -> list[dict]:
    """Build display rows from measured fields and contract constants."""
    meas = (design.get("nominal") or {}).get("meas") or {}
    request = design.get("request") or {}
    rows = [
        ("Peaking", "peaking_db", "dB", request.get("peaking_db"),
         "target", 1.5),
        ("Peak frequency", "_f_peak_ghz", "GHz",
         _number(request.get("f_peak_hz")) / 1e9
         if _number(request.get("f_peak_hz")) is not None else None,
         "target_oct", 0.3),
        ("Nyquist boost", "nyq_boost_db", "dB", 0.0, "min", None),
        ("Input noise", "_noise_mv", "mV rms",
         SPEC_VN_IN_MAX_VRMS * 1e3, "max", None),
        ("Power", "_power_mw", "mW", SPEC_POWER_MAX_W * 1e3, "max", None),
        ("HD3 at Nyquist", "hd3_nyq_dbc", "dBc", SPEC_HD3_MAX_DBC,
         "max", None),
        ("Area", "area_mm2", "mm2", SPEC_AREA_MAX_MM2, "max", None),
        ("Eye height", "eye_h_v", "V", SPEC_EYE_H_MIN_V, "min", None),
        ("Eye width", "eye_w_ui", "UI", SPEC_EYE_W_MIN_UI, "min", None),
    ]
    out: list[dict] = []
    for label, key, unit, target, rule, tolerance in rows:
        measured = _number(meas.get(key))
        target_n = _number(target)
        status: Optional[bool] = None
        if measured is not None and target_n is not None:
            if rule == "min":
                status = measured >= target_n
            elif rule == "max":
                status = measured <= target_n
            elif rule == "target":
                status = abs(measured - target_n) <= float(tolerance)
            elif rule == "target_oct" and measured > 0 and target_n > 0:
                import math

                status = abs(math.log2(measured / target_n)) <= float(tolerance)
        out.append({"label": label, "key": key, "unit": unit,
                    "measured": measured, "target": target_n,
                    "rule": rule, "status": status})
    return out


def _hardware_truth(design: dict) -> dict:
    search = design.get("search") or {}
    hardware = search.get("programmable_hardware") or {}
    atten = hardware.get("attenuator") or {}
    rs = hardware.get("rs_bank") or {}
    cs = hardware.get("cs_bank") or {}
    statuses = {
        "Input attenuator switches": atten.get("switch_status", "not recorded"),
        "Rs selector switches": rs.get("switch_status", "not recorded"),
        "Cs selector switches": cs.get("switch_status", "not recorded"),
    }
    incomplete = [name for name, status in statuses.items()
                  if status != "netlisted-and-measured"]
    return {
        "items": statuses,
        "programmable_selector_complete": not incomplete and bool(hardware),
        "incomplete_items": incomplete,
        "note": (
            "The representative SKY130 circuit and passive values are real. "
            "The adaptive Rs/Cs selector network is not yet a tapeout-ready "
            "switch matrix."
            if incomplete else
            "Every recorded selector block is netlisted and measured."
        ),
    }


def present_design(design_id: str, design: dict, *, source: str,
                   artifacts: Sequence[str] = ()) -> dict:
    """Reduce one immutable design artifact for the browser.

    No browser-facing fallback values are invented.  Missing measurements stay
    ``null`` and are rendered as "not measured" by the client.
    """
    nominal = design.get("nominal") or {}
    verification = design.get("verification") or {}
    request_match = design.get("request_match")
    conditions = []
    for row in verification.get("per_condition") or ():
        conditions.append({
            "channel_loss_db": _number(row.get("channel_loss_db")),
            "corner": row.get("corner"),
            "setting": row.get("setting"),
            "atten_code": row.get("atten_code"),
            "bank_code": row.get("bank_code"),
            "source": row.get("source"),
            "compliant": row.get("compliant"),
            "eye_area": _number(row.get("eye_area")),
            "rl_measurements": row.get("rl_measurements"),
            "verifier_calls": row.get("verifier_calls"),
            "bank_rows_checked": row.get("bank_rows_checked"),
        })

    failures: list[str] = []
    if not nominal.get("ok", False):
        failures.append(str(nominal.get("reason") or nominal.get("verdict")
                            or "The representative simulation was not valid."))
    if request_match is None:
        failures.append("The requested peaking and frequency were not measured.")
    elif not request_match.get("request_met", False):
        failures.append("The generated circuit did not reach the requested target tolerance.")
    if verification and not verification.get("all_points_pass", False):
        failed = verification.get("n_failed")
        total = verification.get("n_points")
        failures.append(f"{failed} of {total} recorded verification conditions failed.")

    verified = bool(verification.get("all_points_pass", False))
    request_met = bool(request_match and request_match.get("request_met", False))
    status = "pass" if nominal.get("ok") and request_met and verified else "fail"
    search = design.get("search") or {}
    return {
        "id": design_id,
        "source": source,
        "cached": source == "preverified-demo",
        "request": design.get("request") or {},
        "natural_language": design.get("natural_language"),
        "method": design.get("method"),
        "method_label": "RL policy with simulator safety shield"
        if design.get("method") == "rl-hybrid" else str(design.get("method")),
        "status": status,
        "failure_reasons": failures,
        "request_match": request_match,
        "nominal": {
            "ok": nominal.get("ok"),
            "verdict": nominal.get("verdict"),
            "reason": nominal.get("reason"),
            "design_id": nominal.get("design_id"),
            "reward": _number(nominal.get("reward")),
            "meas": nominal.get("meas") or {},
            "params": nominal.get("params") or {},
        },
        "specs": _spec_rows(design),
        "verification": {
            "mode": verification.get("mode"),
            "n_points": verification.get("n_points"),
            "n_pass": verification.get("n_pass"),
            "n_failed": verification.get("n_failed"),
            "all_points_pass": verification.get("all_points_pass"),
            "n_corners": verification.get("n_corners"),
            "n_channel_losses": verification.get("n_channel_losses"),
            "channel_losses_db": verification.get("channel_losses_db") or [],
            "conditions": conditions,
            "spec_set": verification.get("spec_set"),
        },
        "search": {
            "which_path": search.get("which_path"),
            "design_id": search.get("design_id"),
            "setting": search.get("setting"),
            "atten_code": search.get("atten_code"),
            "bank_code": search.get("bank_code"),
            "policy_seed": search.get("policy_seed"),
            "rl_proposals": search.get("rl_proposals"),
            "shield_fallbacks": search.get("shield_fallbacks"),
        },
        "simulations": design.get("simulations") or {},
        "wall_s": _number(design.get("wall_s")),
        "hardware": _hardware_truth(design),
        "artifacts": list(artifacts),
        "explanation": design.get("explanation"),
    }


@dataclass
class Job:
    id: str
    kind: str
    status: str = "queued"
    stage: str = "Waiting for the simulator worker"
    progress: int = 0
    created_at: float = field(default_factory=time.time)
    result: Optional[dict] = None
    error: Optional[str] = None
    output_dir: Optional[Path] = None

    def public(self) -> dict:
        return {"id": self.id, "kind": self.kind, "status": self.status,
                "stage": self.stage, "progress": self.progress,
                "result": self.result, "error": self.error}


class NebulaWebApp:
    """State shared by HTTP request handlers."""

    def __init__(self, run_root: Optional[Path] = None,
                 demo_dir: Path = DEMO_DIR):
        self.run_root = Path(run_root or tempfile.mkdtemp(prefix="nebula-web-"))
        self.run_root.mkdir(parents=True, exist_ok=True)
        self.demo_dir = Path(demo_dir)
        self.jobs: dict[str, Job] = {}
        self.designs: dict[str, dict] = {}
        self.design_dirs: dict[str, Path] = {}
        self.lock = threading.Lock()
        # Deliberately one worker: ngspice and result directories are isolated,
        # but serial work avoids demo-machine contention and unpredictable lag.
        self.executor = ThreadPoolExecutor(max_workers=WORKER_LIMIT,
                                           thread_name_prefix="nebula-design")

    def close(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)

    def demo(self) -> dict:
        path = self.demo_dir / "design.json"
        if not path.is_file():
            raise FileNotFoundError("The preverified judge artifact is missing.")
        design = json.loads(path.read_text(encoding="utf-8"))
        artifacts = sorted(p.name for p in self.demo_dir.iterdir() if p.is_file())
        shown = present_design("judge-demo", design,
                               source="preverified-demo", artifacts=artifacts)
        with self.lock:
            self.designs[shown["id"]] = shown
            self.design_dirs[shown["id"]] = self.demo_dir
        return shown

    def start_design(self, request_text: str) -> Job:
        # Parse before enqueueing so a malformed request fails immediately and
        # never occupies the single simulator worker.
        parsed = parse_request(request_text, use_llm=False)
        job = Job(uuid.uuid4().hex, "design")
        with self.lock:
            self.jobs[job.id] = job
        self.executor.submit(self._run_design, job, parsed)
        return job

    def _update(self, job: Job, *, status: Optional[str] = None,
                stage: Optional[str] = None, progress: Optional[int] = None,
                result: Optional[dict] = None, error: Optional[str] = None) -> None:
        with self.lock:
            if status is not None:
                job.status = status
            if stage is not None:
                job.stage = stage
            if progress is not None:
                job.progress = progress
            if result is not None:
                job.result = result
            if error is not None:
                job.error = error

    def _run_design(self, job: Job, parsed) -> None:
        out_dir = self.run_root / job.id
        out_dir.mkdir(parents=True, exist_ok=False)
        job.output_dir = out_dir
        try:
            self._update(job, status="running", stage="Selecting and shielding the circuit", progress=15)
            from nebula.design import design, prepare_output_deck, write_outputs
            from nebula.llm.explanation import explain as explain_design

            design_data = design(parsed.target.peaking_db,
                                 parsed.target.f_peak_hz,
                                 method="rl-hybrid", verify=True)
            design_data["natural_language"] = parsed.as_dict()
            self._update(job, stage="Exporting the exact representative SPICE deck", progress=72)
            deck = prepare_output_deck(design_data)
            explanation, explanation_source = explain_design(
                design_data, use_llm=False)
            design_data["explanation"] = {
                "text": explanation, "source": explanation_source}
            self._update(job, stage="Building the evidence bundle", progress=88)
            written, warnings = write_outputs(
                design_data, out_dir, deck=deck,
                extra_files={"explanation.txt": explanation})
            artifacts = [p.name for p in written]
            shown = present_design(job.id, design_data, source="live-run",
                                   artifacts=artifacts)
            if warnings:
                shown["artifact_warnings"] = warnings
            with self.lock:
                self.designs[job.id] = shown
                self.design_dirs[job.id] = out_dir
            self._update(job, status="complete", stage="Complete", progress=100,
                         result=shown)
        except Exception as exc:  # failure is data for this UI, not a crash
            self._update(job, status="failed", stage="Generation stopped",
                         progress=100, error=f"{exc.__class__.__name__}: {exc}")

    def start_channel(self, filename: str, data: bytes,
                      ports: tuple[int, int]) -> Job:
        safe_name = Path(filename).name
        if not TOUCHSTONE_NAME.fullmatch(safe_name):
            raise ValueError("Upload a Touchstone file named .s2p, .s4p, or another .sNp form.")
        if not data:
            raise ValueError("The uploaded channel file is empty.")
        if len(data) > MAX_CHANNEL_BYTES:
            raise ValueError("The uploaded channel file exceeds the 32 MB limit.")
        job = Job(uuid.uuid4().hex, "channel")
        out_dir = self.run_root / job.id
        out_dir.mkdir(parents=True, exist_ok=False)
        source = out_dir / safe_name
        source.write_bytes(data)
        job.output_dir = out_dir
        with self.lock:
            self.jobs[job.id] = job
        self.executor.submit(self._run_channel, job, source, ports)
        return job

    def _run_channel(self, job: Job, source: Path,
                     ports: tuple[int, int]) -> None:
        try:
            self._update(job, status="running", stage="Parsing measured S-parameters", progress=30)
            from nebula.channel_upload import write_channel_report

            written = write_channel_report(source, job.output_dir,
                                            ports=ports)
            self._update(job, stage="Recording provenance and fit", progress=85)
            profile = json.loads(written[0].read_text(encoding="utf-8"))
            profile["artifacts"] = [p.name for p in written]
            profile["id"] = job.id
            with self.lock:
                self.design_dirs[job.id] = job.output_dir
            self._update(job, status="complete", stage="Profile complete",
                         progress=100, result=profile)
        except Exception as exc:
            self._update(job, status="failed", stage="Channel profile stopped",
                         progress=100, error=f"{exc.__class__.__name__}: {exc}")

    def job(self, job_id: str) -> Optional[dict]:
        with self.lock:
            job = self.jobs.get(job_id)
            return job.public() if job else None

    def design_list(self) -> list[dict]:
        if "judge-demo" not in self.designs:
            self.demo()
        with self.lock:
            return [{"id": d["id"], "source": d["source"],
                     "request": d["request"], "status": d["status"],
                     "design_id": d["nominal"].get("design_id")}
                    for d in self.designs.values()]

    def get_design(self, design_id: str) -> Optional[dict]:
        if design_id == "judge-demo" and design_id not in self.designs:
            self.demo()
        with self.lock:
            return self.designs.get(design_id)

    def artifact(self, item_id: str, name: str) -> Optional[Path]:
        if Path(name).name != name:
            return None
        with self.lock:
            directory = self.design_dirs.get(item_id)
        if directory is None and item_id == "judge-demo":
            self.demo()
            directory = self.demo_dir
        path = directory / name if directory else None
        return path if path and path.is_file() else None

    def evidence_zip(self, item_id: str) -> Optional[bytes]:
        with self.lock:
            directory = self.design_dirs.get(item_id)
        if directory is None and item_id == "judge-demo":
            self.demo()
            directory = self.demo_dir
        if directory is None or not directory.is_dir():
            return None
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(directory.iterdir()):
                if path.is_file():
                    zf.write(path, arcname=path.name)
        return buf.getvalue()


class _Handler(BaseHTTPRequestHandler):
    app: NebulaWebApp

    def log_message(self, fmt: str, *args: object) -> None:
        print("web: " + fmt % args)

    def _json(self, data: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(data, separators=(",", ":"), default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: HTTPStatus, message: str) -> None:
        self._json({"error": message}, status)

    def _body(self, limit: int) -> bytes:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Invalid Content-Length header.") from exc
        if length < 0 or length > limit:
            raise ValueError(f"Request body exceeds the {limit} byte limit.")
        return self.rfile.read(length)

    def _json_body(self) -> dict:
        raw = self._body(MAX_JSON_BYTES)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Request body must be valid UTF-8 JSON.") from exc
        if not isinstance(data, dict):
            raise ValueError("Request body must be a JSON object.")
        return data

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        try:
            if path == "/api/health":
                self._json({"ok": True, "worker_limit": WORKER_LIMIT})
                return
            if path == "/api/demo":
                self._json(self.app.demo())
                return
            if path == "/api/designs":
                self._json({"designs": self.app.design_list()})
                return
            if path.startswith("/api/designs/"):
                design = self.app.get_design(path.rsplit("/", 1)[-1])
                if design is None:
                    self._error(HTTPStatus.NOT_FOUND, "Unknown design.")
                else:
                    self._json(design)
                return
            if path.startswith("/api/jobs/"):
                job = self.app.job(path.rsplit("/", 1)[-1])
                if job is None:
                    self._error(HTTPStatus.NOT_FOUND, "Unknown job.")
                else:
                    self._json(job)
                return
            if path.startswith("/api/evidence/") and path.endswith(".zip"):
                item_id = path.rsplit("/", 1)[-1][:-4]
                payload = self.app.evidence_zip(item_id)
                if payload is None:
                    self._error(HTTPStatus.NOT_FOUND, "Evidence bundle not found.")
                else:
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "application/zip")
                    self.send_header("Content-Disposition",
                                     f'attachment; filename="nebula-{item_id}.zip"')
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                return
            if path.startswith("/api/artifacts/"):
                parts = path.split("/")
                if len(parts) != 5:
                    self._error(HTTPStatus.NOT_FOUND, "Artifact not found.")
                    return
                artifact = self.app.artifact(parts[3], parts[4])
                if artifact is None:
                    self._error(HTTPStatus.NOT_FOUND, "Artifact not found.")
                else:
                    self._file(artifact)
                return
            self._static(path)
        except (FileNotFoundError, ValueError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/parse":
                data = self._json_body()
                text = str(data.get("request", "")).strip()
                if not text:
                    raise ValueError("Enter a circuit request first.")
                parsed_request = parse_request(text, use_llm=False)
                self._json(parsed_request.as_dict())
                return
            if parsed.path == "/api/design":
                data = self._json_body()
                text = str(data.get("request", "")).strip()
                if not text:
                    raise ValueError("Enter a circuit request first.")
                job = self.app.start_design(text)
                self._json(job.public(), HTTPStatus.ACCEPTED)
                return
            if parsed.path == "/api/channel":
                query = parse_qs(parsed.query)
                filename = self.headers.get("X-Filename", "")
                try:
                    ports = (int(query.get("out", ["1"])[0]),
                             int(query.get("in", ["3"])[0]))
                except ValueError as exc:
                    raise ValueError("Channel ports must be integers.") from exc
                job = self.app.start_channel(
                    filename, self._body(MAX_CHANNEL_BYTES), ports)
                self._json(job.public(), HTTPStatus.ACCEPTED)
                return
            self._error(HTTPStatus.NOT_FOUND, "Unknown API endpoint.")
        except (SpecOutOfRange, ValueError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))

    def _static(self, url_path: str) -> None:
        relative = "index.html" if url_path in ("", "/") else url_path.lstrip("/")
        candidate = (STATIC_DIR / relative).resolve()
        if STATIC_DIR.resolve() not in candidate.parents and candidate != STATIC_DIR.resolve():
            self._error(HTTPStatus.NOT_FOUND, "File not found.")
            return
        if not candidate.is_file():
            self._error(HTTPStatus.NOT_FOUND, "File not found.")
            return
        self._file(candidate)

    def _file(self, path: Path) -> None:
        payload = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(payload)


def make_server(app: NebulaWebApp, host: str, port: int) -> ThreadingHTTPServer:
    handler = type("NebulaHandler", (_Handler,), {"app": app})
    return ThreadingHTTPServer((host, port), handler)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the local Nebula CTLE engineering dashboard.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--run-root", type=Path, default=None,
                        help="optional directory for generated run artifacts")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    app = NebulaWebApp(run_root=args.run_root)
    server = make_server(app, args.host, args.port)
    url = f"http://{args.host}:{server.server_port}/"
    print(f"Nebula dashboard: {url}")
    print("Press Ctrl+C to stop.")
    if not args.no_browser:
        threading.Timer(0.4, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping Nebula dashboard.")
    finally:
        server.server_close()
        app.close()
    return 0


__all__ = ("NebulaWebApp", "present_design", "make_server", "main")
