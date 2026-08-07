"""pytest configuration for the nebula interface tests.

Puts the repository root on the import path so `import nebula...` works when
pytest is invoked from anywhere. Deliberately does NOT put `python_models/` on
the path — the interface layer must not depend on it (see
`nebula/link/config.py`), and if one of these tests ever starts needing it,
that is a coupling regression worth noticing.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nebula.common.types import TargetSpec  # noqa: E402
from nebula.device.mock import MOCK_REFERENCE_PARAMS  # noqa: E402
from nebula.link.config import LinkConfig  # noqa: E402
from nebula.rl.reward import RewardConfig  # noqa: E402


def pytest_configure(config: pytest.Config) -> None:
    """Register the `slow` marker.

    Used by `test_trimmed_lib.py` for the checks that re-derive golden values
    from the FULL SKY130 library (~30 s per point, versus ~0.4 s against the
    trimmed one). Deselected by default with `-m "not slow"`; run them after a
    PDK update to confirm the goldens are still the right answer.
    """
    config.addinivalue_line(
        "markers", "slow: needs the full SKY130 library; tens of seconds per test"
    )


@pytest.fixture
def ref_params() -> dict[str, float]:
    """Synthetic reference sizing. NOT a hand-design — see device/mock.py."""
    return dict(MOCK_REFERENCE_PARAMS)


@pytest.fixture
def target() -> TargetSpec:
    """A mid-range S3 operating point with the fixed S4-S8 constraints."""
    return TargetSpec.pcie_gen2(peaking_db=6.0, f_peak_hz=2.0e9)


@pytest.fixture
def link_cfg() -> LinkConfig:
    """Link config at one point of the channel-loss sweep.

    The loss is stated explicitly because it is the swept axis, not an
    assumption. Input amplitude is derived from the PCIe Gen2 TX anchor.

    WAS 8.0 dB. Moved to 12.0 dB when the transmitter's mandated -3.5 dB
    de-emphasis entered the model: the CTLE's burden is the channel tilt MINUS
    the TX tilt, so an 8 dB channel now leaves only 4.5 dB for a mock device
    that boosts 8.98 dB — a badly OVER-equalised link, which is not what the
    bridge tests below are trying to exercise. 12 dB leaves 8.5 dB, which is
    near-matched, and it is the top of the derived channel family
    (`link/channel.py::FAMILY_IL_DB`) rather than a number picked to make a
    test pass.
    """
    return LinkConfig(channel_loss_db_at_nyquist=12.0)


@pytest.fixture
def reward_cfg() -> RewardConfig:
    """Reward config with the human-set 2026-08-03 tolerances (+/-1 dB, +/-10%)."""
    return RewardConfig()
