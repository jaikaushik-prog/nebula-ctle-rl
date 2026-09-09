"""
experiments/runlock.py — **one experiment, one artifact, one writer.**

WHY THIS EXISTS
----------------
On 2026-08-21 two coverage sweeps ran concurrently. The older one was believed
killed, was not, and **finished last — so it overwrote the corrected run's
artifact.** The numbers that had already been read, reported and written into
`PREDICTIONS.md` came from a file that no longer existed.

    run           screen audit          mandated 45-corner   SPICE   wall
    b234jcq3l     correct               10 / 16              16 094  149.7 min
    bjzvuvxy7     the G110 bug          8 / 16               24 294  209 min   <- won

Three failures stacked, and only the first was visible at the time:

1. the surviving artifact was from the run with the known-bad audit;
2. **both runs' wall-clock numbers are inflated** — G70, one concurrent ngspice
   is ~4.8x slower. Simulation COUNTS survive concurrency; MINUTES do not;
3. a completed run silently clobbered a completed run: no run id, no refusal.

This module fixes (3), which is the one that turns a mistake into a wrong
published number. (1) is a code bug and is fixed. (2) cannot be fixed after the
fact and is why `hold()` refuses to START rather than warning afterwards.

WHAT IT DOES NOT DO
--------------------
It is **not** a general mutual-exclusion primitive and does not try to be
robust against a hostile process. It is a stale-tolerant advisory lock for one
machine running one experiment at a time, which is the actual situation. A lock
whose holder died is broken automatically, because the alternative -- a run
refusing to start because of a crash three days ago -- is a worse failure than
the one being prevented.
"""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

#: A lock older than this with no live holder is treated as abandoned.
STALE_AFTER_S: float = 6 * 3600.0


def _alive(pid: int) -> bool:
    """Is `pid` a live process? **Unknown counts as ALIVE.**

    A false "dead" breaks a lock that is doing its job and reintroduces exactly
    the concurrency this module exists to stop, so the uncertain case is
    resolved toward refusing to start.
    """
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            import subprocess

            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True, timeout=20)
            return str(pid) in (out.stdout or "")
        os.kill(pid, 0)
        return True
    except Exception:                                           # noqa: BLE001
        return True


class RunLockBusy(RuntimeError):
    """Another live run holds this experiment's lock."""


@contextmanager
def hold(name: str, here: Optional[Path] = None, meta: Optional[dict] = None):
    """Hold the lock for experiment `name` for the duration of the block.

    Raises `RunLockBusy` **before** the run starts if a live holder exists.
    Refusing to start is the whole point: a warning printed at the end cannot
    un-inflate a wall clock that two ngspice streams already shared.
    """
    d = Path(here) if here is not None else Path(__file__).resolve().parent
    lock = d / f".{name}.runlock.json"

    if lock.exists():
        try:
            cur = json.loads(lock.read_text(encoding="utf-8"))
        except Exception:                                       # noqa: BLE001
            cur = {}
        pid = int(cur.get("pid", -1))
        age = time.time() - float(cur.get("started", 0.0))
        if _alive(pid) and age < STALE_AFTER_S:
            raise RunLockBusy(
                f"experiment {name!r} is already running: pid {pid}, started "
                f"{age / 60:.1f} min ago. Two concurrent runs would (a) share "
                f"one ngspice and inflate BOTH wall clocks ~4.8x (G70), and "
                f"(b) race to overwrite {name}'s artifact -- which is exactly "
                f"how a corrected run's results were lost on 2026-08-21. "
                f"Stop that run, or delete {lock.name} if you are certain it "
                f"is dead.")
        print(f"  breaking a stale {name!r} lock (pid {pid}, "
              f"{age / 60:.0f} min old, alive={_alive(pid)})", flush=True)

    lock.write_text(json.dumps({
        "pid": os.getpid(), "started": time.time(),
        "name": name, **(meta or {})}, indent=1), encoding="utf-8")
    try:
        yield lock
    finally:
        try:
            lock.unlink()
        except OSError:
            pass


def stamp(meta: Optional[dict] = None) -> dict:
    """Provenance every artifact should carry, so two runs are never confused.

    `pid` and `started_unix` together identify the writer. An artifact without
    them cannot be attributed, which is the state that made the 2026-08-21
    loss invisible until a figure was rendered from the wrong file.
    """
    return {"run_pid": os.getpid(), "run_started_unix": time.time(),
            "run_host": os.environ.get("COMPUTERNAME", "?"), **(meta or {})}


__all__ = ["hold", "stamp", "RunLockBusy", "STALE_AFTER_S"]
