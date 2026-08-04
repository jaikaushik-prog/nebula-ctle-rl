"""
gym_env.py
----------
Gymnasium environment implementing the four training setups shown in Fig. 2:

  RL-PPO           : plain PPO, reward directly from the (frozen, pre-trained)
                      ensemble regressor, no discriminator.
  RL-PPO-Offline    : regressor reward + discriminator OOD penalty (Eq. 4),
                      discriminator retrained every B steps on
                      (recent SPICE data) vs (recent policy actions).
  RL-PPO-Online     : every K steps, a real ("SPICE") evaluation is used for
                      the reward instead of the regressor, and the new
                      (params, SNDR, SFDR) triple is appended to the buffer
                      used to incrementally retrain the regressor
                      (EnsembleRegressor.partial_fit).
  RL-PPO-Blend      : discriminator always on (as in Offline); with
                      probability p% per step, a SPICE call is used instead
                      of the regressor (Sec. III.B / III.E, "blend mode...
                      scheduled fraction p% of SPICE-verified steps").

Episodes are single-shot (one parameter proposal = one episode), matching
Sec. III.G: "Although the steps are single-shot, s allow the policy to
adapt to goals."

Action space: a in [0,1]^d (normalized circuit parameters, Sec. III.G).
State space: normalized [tau_SNDR, tau_SFDR, Fs_norm] (targets + optional
constraint), consistent with "s contains normalized targets ... and
optional constraints (e.g., Fs)".
"""
from __future__ import annotations
import numpy as np
import gymnasium as gym
from gymnasium import spaces
from typing import Optional, Literal

from circuits import dim, denormalize
from simulator import SyntheticSpiceEnv
from regressor import EnsembleRegressor
from discriminator import DiscriminatorTrainer
from reward import r_total, r_pred


Mode = Literal["ppo", "offline", "online", "blend"]


class AMSDesignEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(
        self,
        circuit: str,
        spice_env: SyntheticSpiceEnv,
        regressor: EnsembleRegressor,
        discriminator: Optional[DiscriminatorTrainer] = None,
        mode: Mode = "ppo",
        K: int = 50,            # SPICE interval for 'online' mode
        B: int = 32,            # discriminator retrain interval (steps) for offline/blend
        blend_p: float = 1.0,   # % of steps that use real SPICE in 'blend' mode
        tau_sndr_range=(55.0, 80.0),
        tau_sfdr_range=(55.0, 90.0),
        lam_disc: float = 0.1,
        real_pool_X: Optional[np.ndarray] = None,   # SPICE-labeled real params for D
        seed: int = 0,
    ):
        super().__init__()
        self.circuit = circuit
        self.d = dim(circuit)
        self.spice = spice_env
        self.regressor = regressor
        self.discriminator = discriminator
        self.mode = mode
        self.K, self.B, self.blend_p = K, B, blend_p
        self.tau_sndr_range = tau_sndr_range
        self.tau_sfdr_range = tau_sfdr_range
        self.lam_disc = lam_disc
        self.real_pool_X = real_pool_X
        self.rng = np.random.default_rng(seed)

        self.action_space = spaces.Box(low=0.0, high=1.0, shape=(self.d,), dtype=np.float32)
        self.observation_space = spaces.Box(low=0.0, high=1.0, shape=(3,), dtype=np.float32)

        self.step_count = 0
        self._fake_buffer = []          # recent policy actions (physical units), for D
        self._online_buffer_X = []      # (physical params) collected via SPICE, for regressor retrain
        self._online_buffer_y = []      # (SNDR, SFDR) collected via SPICE
        self.total_spice_calls = 0
        self.total_spice_time_s = 0.0

        self._cur_tau_sndr = None
        self._cur_tau_sfdr = None

    # ------------------------------------------------------------------
    def _sample_targets(self):
        self._cur_tau_sndr = self.rng.uniform(*self.tau_sndr_range)
        self._cur_tau_sfdr = self.rng.uniform(*self.tau_sfdr_range)

    def _obs(self):
        return np.array([
            self._cur_tau_sndr / 100.0,
            self._cur_tau_sfdr / 100.0,
            0.5,  # placeholder normalized Fs constraint slot (unused directly)
        ], dtype=np.float32)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self._sample_targets()
        # NOTE: step_count is intentionally NOT incremented here. Episodes are
        # single-shot (Sec. III.G) and get auto-reset by the VecEnv after
        # every step(); step_count must therefore only advance inside step(),
        # or K-step / B-step modulo scheduling (online/blend/discriminator)
        # would silently never align (e.g. an always-odd counter vs. even K).
        return self._obs(), {}


    # ------------------------------------------------------------------
    def _use_spice_this_step(self) -> bool:
        if self.mode == "online":
            return (self.step_count % self.K) == 0
        if self.mode == "blend":
            return self.rng.uniform(0, 100) < self.blend_p
        return False

    def _maybe_train_discriminator(self, fake_phys: np.ndarray):
        if self.discriminator is None or self.real_pool_X is None:
            return
        self._fake_buffer.append(fake_phys)
        if (self.step_count % self.B) == 0 and len(self._fake_buffer) >= self.B:
            batch_fake = np.array(self._fake_buffer[-2 * self.B:])
            idx = self.rng.choice(len(self.real_pool_X), size=len(batch_fake), replace=True)
            batch_real = self.real_pool_X[idx]
            self.discriminator.train_step(batch_real, batch_fake)
            self._fake_buffer = self._fake_buffer[-2 * self.B:]

    def step(self, action: np.ndarray):
        self.step_count += 1  # single authoritative counter, advanced once per real env step
        phys = denormalize(np.asarray(action, dtype=np.float64), self.circuit)
        use_spice = self._use_spice_this_step()

        if use_spice:
            sndr, sfdr, cost = self.spice.evaluate(phys)
            self.total_spice_calls += 1
            self.total_spice_time_s += cost
            self._online_buffer_X.append(phys)
            self._online_buffer_y.append([sndr, sfdr])
            # periodically retrain the regressor on freshly collected SPICE data
            if len(self._online_buffer_X) >= max(8, self.K // 2):
                Xb = np.array(self._online_buffer_X[-64:])
                yb = np.array(self._online_buffer_y[-64:])
                self.regressor.partial_fit(Xb, yb, epochs=5)
        else:
            pred = self.regressor.predict(phys.reshape(1, -1))[0]
            sndr, sfdr = float(pred[0]), float(pred[1])

        d_score = None
        if self.mode in ("offline", "blend") and self.discriminator is not None:
            d_score = float(self.discriminator.score(phys.reshape(1, -1))[0])
            self._maybe_train_discriminator(phys)

        reward = r_total(sndr, sfdr, self._cur_tau_sndr, self._cur_tau_sfdr,
                          d_score=d_score, lam=self.lam_disc)

        terminated = True   # single-shot episodes (Sec. III.G)
        truncated = False
        info = {
            "sndr": sndr, "sfdr": sfdr, "used_spice": use_spice,
            "tau_sndr": self._cur_tau_sndr, "tau_sfdr": self._cur_tau_sfdr,
            "d_score": d_score,
        }
        return self._obs(), float(reward), terminated, truncated, info


if __name__ == "__main__":
    reg = EnsembleRegressor(in_dim=dim("bootstrapped_switch"), n_models=2)
    # bootstrap regressor with a little synthetic data so predict() works
    spice = SyntheticSpiceEnv("bootstrapped_switch", seed=0)
    rng = np.random.default_rng(0)
    A = rng.uniform(0, 1, size=(100, dim("bootstrapped_switch")))
    X = np.array([denormalize(a, "bootstrapped_switch") for a in A])
    y = np.array([spice.evaluate(x)[:2] for x in X])
    reg.fit(X, y, epochs=10)

    disc = DiscriminatorTrainer(in_dim=dim("bootstrapped_switch"))
    disc.set_norm(X)

    env = AMSDesignEnv("bootstrapped_switch", spice, reg, disc, mode="blend",
                        K=10, B=16, blend_p=5.0, real_pool_X=X)
    obs, _ = env.reset()
    for _ in range(5):
        a = env.action_space.sample()
        obs, r, term, trunc, info = env.step(a)
        print(f"reward={r:.3f} spice={info['used_spice']} sndr={info['sndr']:.1f} sfdr={info['sfdr']:.1f}")
        if term:
            obs, _ = env.reset()
