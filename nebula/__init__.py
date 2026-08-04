"""
nebula — RL-driven CTLE sizing for a 5 Gbps PCIe Gen2 link.

See CLAUDEwa.md at the repository root for the project contract.

Layer map (CLAUDEwa.md §5):

    rl/      PPO, surrogate, discriminator, reward, fidelity schedule
    device/  params + corner -> ngspice -> DeviceResult
    link/    DeviceResult -> pole-zero CTLE -> 1-tap DFE -> LinkResult
    common/  frozen interface contracts shared by all three

Nothing in `common/` may import from `rl/`, `device/` or `link/`.
That is what lets the three layers be built in parallel.
"""

__all__ = ["common", "device", "link", "rl"]
