"""Unchanged workbench with bounded physical recovery and shared benchmark workflow."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import threading
import webbrowser
import uuid
from .server import NebulaWebApp, _Handler, present_design, Job
from .optional_llm import LanguageAssistant, opt_in
from nebula.submission_evidence import SAVED_ROOT, evidence_index, receiver_artifact
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from urllib.parse import urlparse, unquote



RECEIVER_ARTIFACTS = frozenset(("receiver/receiver.cir", "receiver/metadata.json",
    "receiver_programmable/receiver.cir", "receiver_programmable/metadata.json", "receiver_programmable/device_sheet.svg"))


def _recorded_artifact(folder, name, digest):
    """Resolve only a safe recorded filename or an allowlisted receiver artifact."""
    if not isinstance(name, str) or not name or "\\" in name or ":" in name:
        return None
    if name not in RECEIVER_ARTIFACTS and Path(name).name != name:
        return None
    if name in (".", ".."):
        return None
    root = Path(folder).resolve()
    path = Path(folder) / name
    try:
        if not path.resolve().is_relative_to(root) or not path.is_file():
            return None
        if not isinstance(digest, str) or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            return None
    except (OSError, ValueError):
        return None
    return path


def recovery_eye(directory):
    from .recovery_visuals import selected_eye
    return selected_eye(directory)


class _RecoveryHandler(_Handler):
    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        if path.startswith('/api/submission/'):
            try:
                if path == '/api/submission/diagnostics':
                    from nebula.deadline_evidence import diagnostics
                    self._json(diagnostics())
                elif path.startswith('/api/submission/programmable-artifact/'):
                    from nebula.programmable_option import artifact
                    self._file(artifact(path[len('/api/submission/programmable-artifact/'):]))
                elif path.startswith('/api/submission/programmable/'):
                    from nebula.programmable_option import for_parent
                    run_id = path.rsplit('/', 1)[-1]
                    if run_id not in self.app.designs:
                        raise ValueError('Unknown saved design')
                    self._json(dict(programmable=for_parent(self.app.design_dirs[run_id]), read_only=True))
                elif path.startswith('/api/submission/index/'):
                    run_id = path.rsplit('/', 1)[-1]
                    if run_id not in self.app.designs:
                        raise ValueError('Unknown saved design')
                    self._json(evidence_index(self.app.design_dirs[run_id], run_id))
                elif path.startswith('/api/submission/receiver/'):
                    self._file(receiver_artifact(path[len('/api/submission/receiver/'):]))
                else:
                    raise ValueError('Unknown evidence route')
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self._error(HTTPStatus.NOT_FOUND, str(exc))
            return
        if path.startswith('/api/artifacts/'):
            parts = path.split('/', 4)
            artifact = self.app.artifact(parts[3], parts[4]) if len(parts) == 5 else None
            if artifact is None:
                self._error(HTTPStatus.NOT_FOUND, 'Artifact not found.')
            else:
                self._file(artifact)
            return
        if path == '/api/llm/availability':
            self._json(self.app.language.availability())
            return
        if not path.startswith('/api/eye/'):
            return super().do_GET()
        item_id = path.rsplit('/', 1)[-1]
        directory = self.app.design_dirs.get(item_id)
        if directory is None:
            self._error(HTTPStatus.NOT_FOUND, 'Unknown design.')
            return
        try:
            self._json(dict(recovery_eye(directory), run_id=item_id))
        except (FileNotFoundError, ValueError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in ('/api/parse', '/api/design', '/api/llm/explain'):
            return super().do_POST()
        try:
            data = self._json_body()
            use_llm = opt_in(data)
            if path == '/api/llm/explain':
                self._json(self.app.explain_design(str(data.get('run_id', '')), use_llm))
                return
            text = str(data.get('request', '')).strip()
            if not text:
                raise ValueError('Enter a circuit request first.')
            if path == '/api/parse':
                parsed = self.app.language.parse(text, use_llm)
                self._json(self.app.language.parsed_view(parsed, use_llm))
                return
            job = self.app.start_design(text, method=data.get('method', 'rl-hybrid'), use_llm=use_llm)
            self._json(job.public(), HTTPStatus.ACCEPTED)
        except (ValueError, FileNotFoundError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))


def make_server(app, host, port):
    handler = type('NebulaRecoveryHandler', (_RecoveryHandler,), {'app': app})
    return ThreadingHTTPServer((host, port), handler)


def run_request(*args, **kwargs):
    from nebula.recovery_workflow import run_request as workflow
    return workflow(*args, **kwargs)


class RecoveryWebApp(NebulaWebApp):
    def __init__(self, *args, language=None, **kwargs):
        self.language = language or LanguageAssistant()
        self.language_requests = {}
        super().__init__(*args, **kwargs)
        for run_id, shown in list(self.designs.items()):
            folder = self.design_dirs[run_id]
            path = folder / 'workflow_receipt.json'
            if not path.is_file():
                continue
            try:
                receipt = json.loads(path.read_text(encoding='utf-8'))
                if not receipt.get('output_complete'):
                    raise ValueError('incomplete output receipt')
                for name, digest in receipt['artifact_sha256'].items():
                    if _recorded_artifact(folder, name, digest) is None:
                        raise ValueError('saved workflow artifact changed')
                shown['artifacts'] = sorted(set(shown['artifacts']) | (set(receipt['artifact_sha256']) & RECEIVER_ARTIFACTS))
                shown['wall_s'] = receipt['wall_s']
                shown['workflow_wall_s'] = receipt['wall_s']
                language_path = folder / 'language_request.json'
                try:
                    if language_path.is_file():
                        language = json.loads(language_path.read_text(encoding='utf-8'))
                        if isinstance(language, dict):
                            shown['natural_language'] = language
                except (OSError, ValueError):
                    pass  # Optional wording provenance cannot invalidate circuit evidence.
                shown['recovery'] = {key: receipt.get(key) for key in
                    ('status', 'selection_mode', 'attempts', 'spice_calls')}
                if not receipt.get('delivered_success') and shown['status'] == 'pass':
                    raise ValueError('saved workflow was not accepted')
            except (ValueError, KeyError, TypeError, OSError):
                del self.designs[run_id]

    def artifact(self, item_id, name):
        if name not in RECEIVER_ARTIFACTS:
            if "/" in name or "\\" in name or ":" in name or name in (".", ".."):
                return None
            return super().artifact(item_id, name)
        with self.lock:
            directory = self.design_dirs.get(item_id) if item_id in self.designs else None
        if directory is None:
            return None
        try:
            receipt = json.loads((directory / "workflow_receipt.json").read_text(encoding="utf-8"))
            if not receipt.get("output_complete"):
                return None
            return _recorded_artifact(directory, name, receipt.get("artifact_sha256", {}).get(name))
        except (OSError, ValueError, TypeError):
            return None

    def start_design(self, request_text, method='rl-hybrid', use_llm=False):
        if method not in ('rl-hybrid', 'rl-physical'):
            raise ValueError('Unknown design mode; choose rl-hybrid or rl-physical.')
        if not isinstance(use_llm, bool):
            raise ValueError('use_llm must be true or false.')
        parsed = self.language.parse(request_text, use_llm)
        job = Job(uuid.uuid4().hex, 'design')
        with self.lock:
            self.jobs[job.id] = job
            self.language_requests[job.id] = self.language.parsed_view(parsed, use_llm)
        self.executor.submit(self._run_design, job, parsed, method)
        return job

    def explain_design(self, run_id, use_llm=False):
        # Resolve only app-known, accepted outputs; never accept a user filesystem path.
        if run_id not in self.designs or run_id not in self.design_dirs:
            raise ValueError('Unknown or incomplete design.')
        directory = self.design_dirs[run_id]
        payload = (directory / 'design.json').read_bytes()
        receipt_path = directory / 'workflow_receipt.json'
        if receipt_path.is_file():
            receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
            expected = receipt.get('artifact_sha256', {}).get('design.json')
            if not expected or hashlib.sha256(payload).hexdigest() != expected:
                raise ValueError('Saved design changed; explanation refused.')
        return self.language.explain(json.loads(payload), use_llm)

    def _run_design(self, job, parsed, method='rl-hybrid'):
        if method != 'rl-physical':
            return super()._run_design(job, parsed, method)
        out = self.run_root / job.id
        job.output_dir = out
        with self.lock:
            self.design_dirs[job.id] = out
        try:
            self._update(job, status='running', stage='Selecting physical candidates', progress=5)
            # The shared workflow reparses numeric text; preserve the validated LLM target.
            text = (f'{parsed.target.peaking_db:.17g} dB at {parsed.target.f_peak_hz / 1e9:.17g} GHz'
                    if parsed.source == 'llm' else parsed.raw)
            receipt = run_request(text, out, selection_mode='rl', max_candidates=8,
                progress=lambda stage, value: self._update(job, stage=stage, progress=value))
            design = receipt.get('design')
            if design is None or not receipt.get('output_complete'):
                detail = '; '.join(receipt.get('artifact_warnings', []))
                raise RuntimeError(f"{receipt['status']}: {detail or 'no complete circuit output; attempt evidence retained'}")
            artifacts = [(Path(p).resolve().relative_to(out.resolve()).as_posix()
                          if Path(p).is_absolute() else Path(p).as_posix())
                         for p in receipt.get('written', [])]
            shown = present_design(job.id, design, source='live-run', artifacts=artifacts)
            shown['natural_language'] = self.language_requests.get(job.id, parsed.as_dict())
            # Provenance is separate from immutable scientific outputs and their timing boundary.
            try:
                (out / 'language_request.json').write_text(json.dumps(shown['natural_language'], indent=2) + '\n', encoding='utf-8')
            except OSError:
                shown['natural_language'].setdefault('notes', []).append('Optional parser provenance could not be saved.')
            shown['recovery'] = design.get('recovery_workflow', design.get('recovery', {}))
            shown['workflow_wall_s'] = receipt['wall_s']
            shown['wall_s'] = receipt['wall_s']
            if receipt.get('artifact_warnings'):
                shown['artifact_warnings'] = receipt['artifact_warnings']
            if not receipt.get('delivered_success') and shown['status'] == 'pass':
                raise RuntimeError('workflow did not deliver an accepted circuit')
            with self.lock:
                self.designs[job.id] = shown
            self._update(job, status='complete', stage=('Complete' if receipt.get('delivered_success')
                else 'Verification failed; attempts preserved'), progress=100, result=shown)
        except Exception as exc:
            self._update(job, status='failed', stage='Generation stopped', progress=100,
                error=f'{exc.__class__.__name__}: {exc}')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Nebula workbench with automatic physical recovery')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--run-root', type=Path, default=SAVED_ROOT,
        help='Saved submission results by default; choose another root explicitly for new work.')
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args(argv)
    app = RecoveryWebApp(run_root=args.run_root)
    server = make_server(app, args.host, args.port)
    url = f'http://{args.host}:{server.server_port}/'
    print(f'Nebula automatic recovery: {url}')
    if not args.no_browser:
        threading.Timer(.4, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('Stopping Nebula recovery workbench.')
    finally:
        server.server_close()
        app.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
