"""
rl/runlog.py — §6j. Every evaluation, to disk, in a stable format.

WHY THIS FILE EXISTS RATHER THAN A `print`
-------------------------------------------
G49: a 47-minute experiment's raw results were gitignored and are gone. The
rule it produced is quoted here because it is the reason this module writes
where it writes:

    "An experiment's output is TRACKED if any deliverable quotes a number
     from it. A results file that took longer to produce than it takes to
     review is an INPUT to the write-up, not a build artifact."

And §6j adds the second reason, which is stronger: **these are real SPICE
evaluations and they are free training data for task 8's surrogate.** A
40-minute run that has to be repeated because its rows were not kept has cost
40 minutes twice.

THE FORMAT, AND WHY JSONL
--------------------------
One JSON object per line, append-only, UTF-8, no trailing state. Three
properties that matter more than compactness:

* **A truncated run is still readable.** If the process dies at step 312 the
  first 312 rows parse. A single JSON array would not.
* **Rows are self-describing.** A CSV of this shape would need a 60-column
  header nobody can read, and adding a field later would silently shift
  columns in any file written before the change.
* **It streams.** The writer flushes every row, so a run in progress can be
  inspected without stopping it.

`design_id` is on every row (§6j, and task 8's grouped train/test split needs
it). `schema_version` is on every row too, so a later reader can tell rows
written before a field was added from rows where the field was genuinely
absent — the distinction a bare append-only log otherwise loses.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Iterator, Optional, Sequence

#: Bump when a FIELD is added, removed or changes meaning. Never reuse a value.
SCHEMA_VERSION: int = 1


def _clean(obj: Any) -> Any:
    """JSON-safe, and NaN-free.

    `json.dumps` writes bare `NaN`/`Infinity`, which is not valid JSON and
    which many readers silently turn back into a float. That is the same class
    of trap as G54: a NaN that survives a round trip reads as a number. Any
    non-finite value is written as `null` with the field name preserved, so a
    reader sees a missing value rather than a plausible one.
    """
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, bool) or obj is None:
        return obj
    if isinstance(obj, (int,)):
        return int(obj)
    if isinstance(obj, float):
        return float(obj) if math.isfinite(obj) else None
    if is_dataclass(obj) and not isinstance(obj, type):
        return _clean(asdict(obj))
    if hasattr(obj, "item"):                      # numpy scalar
        try:
            return _clean(obj.item())
        except Exception:                          # pragma: no cover
            pass
    if hasattr(obj, "tolist"):                     # numpy array
        return _clean(obj.tolist())
    return str(obj)


class RunLog:
    """Append-only JSONL writer. Use as a context manager."""

    def __init__(self, path: Path, header: Optional[dict] = None,
                 append: bool = False):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = None
        self._header = header or {}
        #: Continue an existing log instead of truncating it. **Default
        #: False, so nothing that already uses this class changes.** It
        #: exists because a long run can be interrupted -- a 96 000-
        #: simulation sweep does not fit in one sitting -- and this format's
        #: whole first property is that *a truncated run is still readable*.
        #: A resumed chunk writes its OWN header row before continuing:
        #: not a duplicate but the provenance of that chunk, since readers
        #: already filter by `kind`/`event` and a chunk whose conditions
        #: differ from the first must be able to say so.
        self.append = bool(append)
        self.n_rows = 0

    def __enter__(self) -> "RunLog":
        mode = "a" if self.append and self.path.exists() else "w"
        self._fh = self.path.open(mode, encoding="utf-8", newline="\n")
        # Row 0 is the header: the seed, the box, the tolerances, the library.
        # It is a ROW, not a separate file, so a log can never be read without
        # the conditions that produced it (CLAUDEwa.md §8 rule 8).
        self._write({"kind": "header", **self._header})
        return self

    def __exit__(self, *exc) -> None:
        if self._fh is not None:
            self._fh.flush()
            self._fh.close()
            self._fh = None

    def _write(self, row: dict) -> None:
        assert self._fh is not None, "RunLog used outside its context manager"
        payload = {"schema_version": SCHEMA_VERSION, **_clean(row)}
        self._fh.write(json.dumps(payload, sort_keys=False, allow_nan=False) + "\n")
        self._fh.flush()          # a run in progress must be inspectable
        self.n_rows += 1

    def step(self, record) -> None:
        """Log one `env.StepRecord`."""
        self._write({"kind": "step", **_clean(asdict(record))})

    def event(self, name: str, **fields) -> None:
        """Log anything that is not a step: a gate result, a timing, a phase."""
        self._write({"kind": "event", "event": name, **fields})


def read(path: Path) -> Iterator[dict]:
    """Stream a run log back. Skips blank lines; raises on a corrupt one."""
    with Path(path).open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno} is not valid JSON: {exc}") from exc


def steps(path: Path) -> Iterator[dict]:
    """Just the step rows — the ones task 8's surrogate trains on."""
    for row in read(path):
        if row.get("kind") == "step":
            yield row


__all__: Sequence[str] = ("RunLog", "SCHEMA_VERSION", "read", "steps")
