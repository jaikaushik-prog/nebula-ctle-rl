"""
§6b — there must be NO code path from the training entry point to a mock.

    "G16 says the mocks produce fake numbers. A flag can be set wrong; an
     import cannot resolve to a module that is not reachable."

WHY THIS TEST RUNS IN A SUBPROCESS
-----------------------------------
`nebula/tests/conftest.py` imports `nebula.device.mock` at collection time, so
by the time any test in this suite runs, the mock is already in `sys.modules`.
Asserting on this process's `sys.modules` would therefore be **vacuously
false** — or, worse, vacuously true if the conftest import were ever removed,
which is a gate that passes for the wrong reason.

A fresh interpreter is the only place the question "what does importing the
training entry point pull in?" has a meaningful answer. That is the "or
equivalent" §6b allows, and it is the stronger form.

WHAT BROKE WHEN THE MOCKS WERE REMOVED: NOTHING, AND THAT IS CHECKED
---------------------------------------------------------------------
§6b: *"Report what broke when you removed them. If nothing broke, check that
the removal actually took effect before believing it."*

Nothing broke, because nothing in the production path ever imported them —
`device/mock.py` and `link/mock.py` are imported only by `tests/conftest.py`
and five test modules. So the honest report is that the mocks were already
test-only and the structural risk was never a mock import.

**That is exactly the situation §6b warns about**, so the second sentence is
the load-bearing one and `test_the_gate_can_fail` is how it is honoured: it
runs the SAME check against a script that DOES import a mock and asserts the
check goes red. A gate that has never been seen to fail is indistinguishable
from a gate that is not running (CLAUDEwa.md §8 rule 10).

The real structural risk this test pins is different and worth naming: the
LINK layer is a mock end to end (G16, `nebula/README.md`), so any future
reward term touching S8 would reach `link/mock.py` — and that would be a
plausible, well-shaped, entirely fake eye height flowing into a training run.
This test is what makes that a red build rather than a discovery in September.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Every module whose numbers are synthetic (G16). Matched as a PREFIX so a
#: future `nebula.link.mock_channel` is caught without editing this list.
MOCK_MODULE_PREFIXES: tuple[str, ...] = (
    "nebula.device.mock",
    "nebula.link.mock",
)

#: The training entry point, and every module a training run imports directly.
TRAINING_ENTRY_POINTS: tuple[str, ...] = (
    "nebula.experiments.rl_smoke",
    "nebula.rl.env",
    "nebula.rl.evaluator",
    "nebula.rl.contract",
    "nebula.rl.reward_v1",
    "nebula.rl.ppo",
    "nebula.rl.runlog",
)

_PROBE = """\
import json, sys
import {module}
bad = sorted(m for m in sys.modules
             if any(m == p or m.startswith(p + ".") for p in {prefixes!r}))
print("MOCKS=" + json.dumps(bad))
"""


def _mocks_pulled_in_by(module: str, extra: str = "") -> list:
    """Import `module` in a FRESH interpreter; return the mocks it dragged in."""
    src = _PROBE.format(module=module, prefixes=list(MOCK_MODULE_PREFIXES))
    if extra:
        src = extra + "\n" + src
    proc = subprocess.run(
        [sys.executable, "-c", src],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=180,
    )
    assert proc.returncode == 0, (
        f"importing {module} in a fresh interpreter failed:\n"
        f"{proc.stdout}\n{proc.stderr}"
    )
    line = [ln for ln in proc.stdout.splitlines() if ln.startswith("MOCKS=")]
    assert line, f"probe produced no MOCKS= line:\n{proc.stdout}\n{proc.stderr}"
    import json
    return json.loads(line[-1][len("MOCKS="):])


@pytest.mark.parametrize("module", TRAINING_ENTRY_POINTS)
def test_training_entry_point_cannot_reach_a_mock(module):
    """No mock module is importable-by-consequence from the training path."""
    pulled = _mocks_pulled_in_by(module)
    assert pulled == [], (
        f"importing {module} pulled in {pulled}. G16: those modules produce "
        f"FAKE numbers by construction, and §6b requires that there be no code "
        f"path from a training run to one. A flag can be set wrong; an import "
        f"that does not exist cannot."
    )


def test_the_gate_can_fail():
    """The same check, against a module that DOES import a mock, must go red.

    Without this, a probe that silently stopped working — a renamed module, a
    changed prefix, a subprocess that no longer reaches the repo — would report
    a clean result forever. CLAUDEwa.md §8 rule 10: deliberately break the
    input, watch it go red, put it back.
    """
    pulled = _mocks_pulled_in_by("nebula.rl.contract",
                                 extra="import nebula.device.mock")
    assert "nebula.device.mock" in pulled, (
        "the mock-detection probe did NOT notice a mock that was imported on "
        "purpose. The gate is not running; every green result above is "
        "meaningless."
    )


def test_link_layer_is_not_on_the_training_path_at_all():
    """S8 cannot be scored, and the reason is structural rather than a choice.

    The link layer is a mock end to end (G16). §6h's reward therefore CANNOT
    carry S8 — not because it was decided against, but because the only
    implementation is synthetic and §6b forbids reaching it. Pinning that here
    means a future S8 term fails this test rather than quietly importing a
    fabricated eye height.
    """
    src = textwrap.dedent("""\
        import json, sys
        import nebula.rl.reward_v1, nebula.rl.env, nebula.rl.evaluator
        link = sorted(m for m in sys.modules if m.startswith("nebula.link"))
        print("LINK=" + json.dumps(link))
    """)
    proc = subprocess.run([sys.executable, "-c", src], cwd=str(REPO_ROOT),
                          capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    import json
    line = [ln for ln in proc.stdout.splitlines() if ln.startswith("LINK=")][-1]
    link = json.loads(line[len("LINK="):])
    assert link == [], (
        f"the reward/env/evaluator import graph reaches {link}. The link layer "
        f"is a MOCK end to end (G16), so an S8 term would score a fabricated "
        f"eye height. If a real link layer lands, update this test with the "
        f"measurement that made it real."
    )
