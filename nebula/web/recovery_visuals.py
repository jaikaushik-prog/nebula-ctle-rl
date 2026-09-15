"""Adapt recovery directories to the unchanged saved-eye implementation.

No simulator, fitting or eye equations live here. Copied runs use only their
local candidate files; historical absolute paths are identity labels, not
locations to read.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile

from nebula.web import design_visuals as canonical


def _local_file(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Selected eye candidate path escapes its local run")
    if not path.is_file():
        raise FileNotFoundError(f"Selected eye local candidate file missing: {relative}")
    return path


def selected_eye(directory: Path) -> dict:
    directory = Path(directory).resolve()
    if (directory / "physical_evidence").is_dir():
        return canonical.selected_eye(directory)

    design_bytes = _local_file(directory, "design.json").read_bytes()
    receipt = json.loads(_local_file(directory, "workflow_receipt.json").read_text(encoding="utf-8"))
    expected = receipt.get("artifact_sha256") or {}
    if hashlib.sha256(design_bytes).hexdigest() != expected.get("design.json"):
        raise ValueError("Selected recovery design.json hash mismatch")
    design = json.loads(design_bytes)
    attempts = receipt.get("attempts")
    if not isinstance(attempts, list) or not 1 <= len(attempts) <= 8:
        raise ValueError("Selected recovery candidate attempt record is missing or invalid")
    last = attempts[-1]
    setting = last.get("setting")
    if isinstance(setting, bool) or not isinstance(setting, int) or not 0 <= setting < 512:
        raise ValueError("Selected recovery candidate setting is invalid")
    if (design.get("search") or {}).get("setting") != setting:
        raise ValueError("Selected design setting does not match the last candidate attempt")
    candidate_name = f"candidate_{len(attempts):02d}_setting_{setting}"
    # Windows and POSIX source records may both be viewed on this machine.
    # Ignore every parent component; require exactly the derived safe basename.
    recorded_name = str(last.get("directory", "")).replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    if recorded_name != candidate_name:
        raise ValueError("Selected recovery candidate basename disagrees with its attempt index")

    visible_deck = _local_file(directory, "design.cir").read_bytes()
    if hashlib.sha256(visible_deck).hexdigest() != expected.get("design.cir"):
        raise ValueError("Selected recovery design.cir hash mismatch")
    candidate = f"physical_recovery/{candidate_name}"
    members = ("design.cir", "evidence_sha256.json", "tt_1.00_27/ac_noise/ac.txt")
    saved = {name: _local_file(directory, f"{candidate}/{name}").read_bytes()
             for name in members}
    if saved["design.cir"] != visible_deck:
        raise ValueError("Selected recovery candidate deck differs from the visible exported deck")

    with tempfile.TemporaryDirectory(prefix="nebula_recovery_eye_") as scratch:
        compatible = Path(scratch)
        (compatible / "design.json").write_bytes(design_bytes)
        for name, data in saved.items():
            destination = compatible / "physical_evidence" / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        return canonical.selected_eye(compatible)

