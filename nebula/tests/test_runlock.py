"""**One experiment, one artifact, one writer.**

Session 23. Two coverage sweeps ran concurrently; the older one was believed
killed, was not, and **finished last, overwriting the corrected run's
artifact**. The numbers already read and reported came from a file that no
longer existed, and nothing in either file said which process wrote it — so
the loss stayed invisible until a figure was rendered from the wrong one.

    run          screen audit     mandated 45-corner   SPICE    wall
    b234jcq3l    correct          10 / 16              16 094   149.7 min
    bjzvuvxy7    the G110 bug      8 / 16              24 294   209 min   <- won

Two properties are pinned here, and the second is the one that matters:

1. a second live holder is REFUSED, before the run starts;
2. every experiment that writes a shared artifact actually TAKES the lock —
   checked over the source, because a lock nobody acquires is decoration.
"""

from __future__ import annotations

import inspect
import json
import os

import pytest

from nebula.experiments.runlock import RunLockBusy, hold, stamp


def test_a_second_LIVE_holder_is_refused(tmp_path):
    with hold("t", here=tmp_path):
        with pytest.raises(RunLockBusy):
            with hold("t", here=tmp_path):
                pass


def test_the_refusal_explains_BOTH_costs_of_concurrency(tmp_path):
    """A run told only "already running" will delete the lock and carry on.
    It has to know that concurrency inflates the wall clock (G70) *and* races
    on the artifact, because those are two different reasons and only one is
    obvious."""
    with hold("t", here=tmp_path):
        with pytest.raises(RunLockBusy) as e:
            with hold("t", here=tmp_path):
                pass
    msg = str(e.value)
    assert "4.8x" in msg and "overwrite" in msg
    assert "runlock" in msg, "the message must name the file to delete"


def test_the_lock_is_RELEASED_on_success_and_on_exception(tmp_path):
    with hold("t", here=tmp_path) as p:
        assert p.exists()
    assert not p.exists()

    with pytest.raises(ValueError):
        with hold("t", here=tmp_path) as p2:
            raise ValueError("boom")
    assert not p2.exists(), "an exception must not strand the lock forever"


def test_a_lock_held_by_a_DEAD_process_is_broken(tmp_path):
    """A run blocked by a crash from three days ago is a worse failure than
    the one being prevented."""
    lock = tmp_path / ".t.runlock.json"
    lock.write_text(json.dumps({"pid": 0, "started": 0.0}), encoding="utf-8")
    with hold("t", here=tmp_path):
        pass  # acquired: pid 0 is not alive and the lock is ancient


def test_an_UNKNOWABLE_process_state_counts_as_ALIVE():
    """The uncertain case must resolve toward refusing to start. A false
    "dead" breaks a lock that is doing its job."""
    from nebula.experiments.runlock import _alive

    assert _alive(os.getpid()) is True
    assert _alive(-1) is False
    src = inspect.getsource(_alive)
    assert "return True" in src.split("except")[-1], (
        "the exception path must return True (alive), not False")


def test_the_stamp_identifies_the_WRITER():
    s = stamp()
    assert s["run_pid"] == os.getpid()
    assert "run_started_unix" in s and "run_host" in s


@pytest.mark.parametrize("module,lockname", [
    ("nebula.experiments.exp_coverage", "coverage"),
    ("nebula.experiments.exp_corner_rl", "corner_rl"),
])
def test_every_shared_artifact_writer_TAKES_the_lock(module, lockname):
    """**A lock nobody acquires is decoration.** Checked over the source of
    `run()` rather than by running it, since running it is the expensive thing
    the lock exists to protect."""
    import importlib

    m = importlib.import_module(module)
    src = inspect.getsource(m.run)
    assert f'hold("{lockname}"' in src, (
        f"{module}.run() writes a shared artifact without taking the lock")


@pytest.mark.parametrize("module", ["nebula.experiments.exp_coverage",
                                    "nebula.experiments.exp_corner_rl"])
def test_every_artifact_carries_its_PROVENANCE(module):
    """An artifact that cannot be attributed to a process is how the
    2026-08-21 loss stayed invisible."""
    import importlib

    m = importlib.import_module(module)
    src = inspect.getsource(m)
    assert "**stamp()" in src, f"{module} writes an artifact with no writer id"
