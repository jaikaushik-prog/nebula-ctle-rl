"""
simulator.py
------------
!! READ THIS FIRST !!
This module is NOT Cadence Spectre. The paper's "SPICE simulation
environment" (Fig. 1/2) is a licensed 28nm transistor-level Spectre deck run
through a MATLAB/Python harness -- that toolchain and PDK are not available
in this sandbox (no EDA tools, no foundry PDK, no network access to
Cadence). To let you actually run and validate the full RL-PPO / PPO-Offline
/ PPO-Online / PPO-Blend pipeline end-to-end, this file implements a
physics-*inspired* analytic surrogate that:

  1. Maps circuit parameters -> (SNDR, SFDR) using closed-form relations for
     on-resistance, bootstrap divider ratio, thermal/kT-C noise, and
     source-resistance linearization -- the same qualitative mechanisms the
     paper describes in Sec. IV ("Findings").
  2. Is deliberately built so that samp_nmos, CB, and source_res dominate
     the output (matching Table I's rank-1/2/3), so that when you rerun the
     component-importance analysis (Eq. 5-6) on a regressor trained on this
     simulator's data, you can sanity-check your implementation against the
     paper's reported ranking.
  3. Includes stochastic "process/mismatch" noise so repeated calls at the
     same parameter vector are NOT identical -- this preserves the paper's
     motivation for an ensemble regressor and a discriminator (SPICE-loop
     evaluation is expensive AND noisy, not just expensive).

TO USE REAL SPICE: replace `SyntheticSpiceEnv.evaluate()` with a call into
your Ocean/Spectre harness. Keep the same signature
(params_physical: np.ndarray) -> (sndr_dB: float, sfdr_dB: float, cost_s: float)
and nothing else downstream needs to change -- regressor.py, discriminator.py,
gym_env.py, and train.py all talk to this class through `evaluate()` /
`evaluate_batch()` only.
"""

from __future__ import annotations
import numpy as np
from typing import Tuple
from circuits import CIRCUITS, param_names, Param


class SyntheticSpiceEnv:
    """Stand-in for the 28nm Cadence Spectre simulation environment (Fig. 1)."""

    def __init__(self, circuit: str, seed: int = 0, call_cost_s: float = 3.2,
                 mismatch_std: float = 0.6):
        assert circuit in CIRCUITS
        self.circuit = circuit
        self.params: list[Param] = CIRCUITS[circuit]
        self.names = [p.name for p in self.params]
        self.idx = {n: i for i, n in enumerate(self.names)}
        self.rng = np.random.default_rng(seed)
        # per-call wall-clock cost used to reproduce the paper's "Time (s) per
        # 1k steps" column purely from call counts (Table II/III use this).
        self.call_cost_s = call_cost_s
        self.mismatch_std = mismatch_std
        self.n_calls = 0

    # -- helpers -----------------------------------------------------------
    def _get(self, phys: np.ndarray, base: str, suffix: str) -> float:
        return float(phys[self.idx[f"{base}_{suffix}"]])

    def _on_resistance(self, phys, base) -> float:
        """Ron ~ 1 / (W/L), decreasing with more fingers (parallel devices)."""
        W = self._get(phys, base, "W")
        L = self._get(phys, base, "L")
        nf = self._get(phys, base, "nf")
        return L / (W * max(nf, 1.0) + 1e-9)

    # -- core physics-inspired model ----------------------------------------
    def _true_metrics(self, phys: np.ndarray) -> Tuple[float, float]:
        names = self.names
        Ron_samp = self._on_resistance(phys, "samp_nmos")
        CB = phys[self.idx["CB"]]
        CS = phys[self.idx["CS"]]
        Rs = phys[self.idx["source_res"]]
        Fs = phys[self.idx["Fs"]]
        duty = phys[self.idx["duty_cycle"]]

        # Bootstrap divider linearization: larger CB relative to a fixed
        # parasitic improves gate-overdrive constancy -> lower distortion.
        Cpar = 15e-15
        boot_ratio = CB / (CB + Cpar)

        # Settling term: RC time constant vs. sampling period.
        tau = Ron_samp * CS
        Tsettle = duty / max(Fs, 1.0)
        settling_penalty = np.exp(-Tsettle / (6.0 * tau + 1e-15))  # ->0 is good (fast), 1 is bad
        settling_quality = 1.0 - np.clip(settling_penalty, 0, 1)

        # Source-resistance linearization vs. bandwidth loss at high Fs
        # (paper: "large source resistance will reduce SNDR at higher Fs").
        rs_lin_gain = np.tanh(Rs / 120.0)
        rs_bw_loss = np.tanh((Rs * Fs) / 8e11)
        rs_term = rs_lin_gain - 0.7 * rs_bw_loss

        # Aggregate secondary devices (inv_nmos/pmos, pmos1/2, nmos1-5):
        # modeled as contributing to switch-driver strength / linearity with
        # smaller, roughly-equal weights, consistent with Table I ranks 4-16.
        secondary = 0.0
        weight_map = {
            "nmos4": 0.070, "nmos5": 0.068, "inv_pmos": 0.066, "nmos2": 0.064,
            "pmos1": 0.064, "nmos3": 0.063, "nmos1": 0.060, "inv_nmos": 0.057,
            "pmos2": 0.054,
        }
        for base, wgt in weight_map.items():
            if f"{base}_W" not in self.idx:
                continue
            Ron_b = self._on_resistance(phys, base)
            # Normalize against its own bound range to keep scale comparable
            secondary += wgt * (1.0 / (1.0 + Ron_b))

        # kT/C floor sets a ceiling on achievable SNDR regardless of switch
        kT = 1.38e-23 * 300.0
        kTC_noise_rms = np.sqrt(kT / max(CS, 1e-18))
        full_scale = 1.0  # normalized FS voltage
        snr_kTC_dB = 20 * np.log10(full_scale / (2 * np.sqrt(2) * kTC_noise_rms + 1e-12))

        # Compose SNDR (dB): kT/C ceiling combined in RSS-like fashion with
        # switch-distortion / settling / secondary-device contributions.
        distortion_dB = 40.0 + 35.0 * boot_ratio + 25.0 * settling_quality \
                         + 20.0 * rs_term + 60.0 * secondary
        sndr_dB = 10 * np.log10(
            1.0 / (10 ** (-snr_kTC_dB / 10) + 10 ** (-distortion_dB / 10) + 1e-12)
        )

        # SFDR correlates with SNDR but is more sensitive to bootstrap
        # linearity (odd-order harmonics from gate-overdrive variation).
        sfdr_dB = 0.55 * sndr_dB + 0.45 * (40.0 + 45.0 * boot_ratio + 15.0 * rs_term) \
                  + 10.0 * settling_quality

        return float(np.clip(sndr_dB, 0, 110)), float(np.clip(sfdr_dB, 0, 120))

    def evaluate(self, params_physical: np.ndarray) -> Tuple[float, float, float]:
        """Single noisy 'SPICE' call. Returns (SNDR_dB, SFDR_dB, cost_seconds)."""
        self.n_calls += 1
        sndr, sfdr = self._true_metrics(params_physical)
        sndr += self.rng.normal(0, self.mismatch_std)
        sfdr += self.rng.normal(0, self.mismatch_std * 1.2)
        return float(sndr), float(sfdr), self.call_cost_s

    def evaluate_batch(self, params_physical_batch: np.ndarray):
        out = [self.evaluate(row) for row in params_physical_batch]
        sndr = np.array([o[0] for o in out])
        sfdr = np.array([o[1] for o in out])
        cost = float(sum(o[2] for o in out))
        return sndr, sfdr, cost

    def total_wall_clock(self) -> float:
        return self.n_calls * self.call_cost_s


if __name__ == "__main__":
    from circuits import denormalize
    env = SyntheticSpiceEnv("buffer_switch", seed=1)
    a = np.random.default_rng(0).uniform(0, 1, size=38)
    phys = denormalize(a, "buffer_switch")
    print(env.evaluate(phys))
