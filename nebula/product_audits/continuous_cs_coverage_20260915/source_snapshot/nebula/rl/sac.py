"""
rl/sac.py — **Soft Actor-Critic. The point is not that it is newer than PPO; it
is that it is OFF-POLICY and can therefore learn from simulations it did not
run.**

WHY THIS FILE EXISTS, IN ONE MEASUREMENT
-----------------------------------------
`rl/ppo.py` is on-policy: it uses each sample once and throws it away. This
project has **74 526 already-simulated designs** on disk (`experiments/
spec_pool.py`) and spends ~12 800 more per 16-request CMA-ES sweep. PPO can use
**none** of them. That is not a tuning problem, it is a structural one, and it
is the whole reason for this file (`NEXT_AGENT_SAC.md` trap 1).

What PPO actually achieved here, so the bar is honest:

    PPO, from scratch, 16 held-out requests      0 of 16     corner_rl_results.json
    PPO, after 200k analytic steps               1 of 16     rl_pretrain_results.json
    PPO, then SPICE fine-tuned                   0 of 16     fine-tuning ERASED it (G114)
    library lookup, 4 sims each                  9 of 16     corner_rl_results.json
    CMA-ES, 800 sims each                       14 of 16     corner_rl_results.json

**RL has never beaten a dictionary lookup on this problem.** This file does not
claim it will. The claim SAC owns is the amortisation curve of §3 — fewer
simulations per request as the proposer improves — and `exp_hybrid.py` already
measures that curve with a non-RL proposer at **35.6 % fewer simulations**
(entry 32, k=8 top-k scan). **That 35.6 % is the number to beat, not zero.**

**NOTHING HERE IS TUNED.** Same rule as `ppo.py` (§6: *"Do not tune
hyperparameters. Do not chase reward."*). Every value below is the SAC paper's
(Haarnoja et al. 2018, arXiv:1801.01290 / 1812.05905) or Stable-Baselines3's
`SAC` default, written down so a later change is visible AS a change:

    gamma              0.99        SAC paper
    tau                0.005       SAC paper (target smoothing)
    lr                 3e-4        SAC paper, all three optimisers
    batch_size         256         SAC paper
    hidden             (256, 256)  SAC paper / SB3 net_arch default
                                   NOTE: ppo.py uses (64, 64), SB3's PPO
                                   default. The two differ upstream; neither
                                   was chosen here.
    gradient_steps     1           SB3 default (one update per env step)
    learning_starts    100         SB3 default
    target_entropy     -dim(A)=-7  SAC paper's automatic-tuning heuristic
    log_std clamp      [-20, 2]    the reference implementation's guard

THE GATE, AND WHY IT IS THE ENTROPY COEFFICIENT
------------------------------------------------
PPO's failure was diagnosed by watching `log_std`, not the score: it starts at
0.0 and shrinks as a policy grows confident. Measured:

    1 200 SPICE steps        -0.05 .. +0.053   sigma 1.000   <- never trained
    200 000 analytic steps   -3.022 .. -0.719  sigma 0.199   <- trained hard
    then 3 000 SPICE steps   -0.097 .. +0.063  sigma 0.988   <- ERASED (G114)

SAC has the same tell in two places: the actor's state-dependent `log_std`, and
`alpha`, the automatically-tuned entropy coefficient. **Both are recorded every
update in `SACStats`.** `NEXT_AGENT_SAC.md` §4 stage 1: *"`log_std` (or SAC's
entropy coefficient) must move. If it does not, stop — the problem is not the
algorithm, and say so."* This module's job is to make that gate checkable, not
to pass it.

TERMINATED IS NOT TRUNCATED, AND THE BOOTSTRAP DEPENDS ON IT
-------------------------------------------------------------
`ppo.py` keeps `terminated` and `truncated` separate all the way through GAE.
The same distinction is load-bearing here, in the Bellman backup:

    backup = r + gamma * (1 - terminated) * (min Q_target - alpha * logp)

A horizon cut (`truncated`) must be **bootstrapped through** — the episode did
not fail, we simply stopped watching. A genuine termination must not be. So
**only `terminated` is stored in the replay buffer's `done` column.** Conflating
them teaches the critic that the horizon is a cliff, which is `ppo.py`'s comment
on the same line and it is repeated here because the buffer only has one slot
and the mistake is invisible.

G114, AND THE THREE LEVERS THIS FILE EXPOSES ONE AT A TIME
-----------------------------------------------------------
PPO's fine-tuning collapse had **three uncontrolled changes at once**: a fresh
optimiser at full learning rate, a different reward scale (analytic 5 rows,
floor -8; SPICE 9 rows, floor -12), and different episode dynamics (analytic
reverts a bad edit, SPICE terminates). The instruction is to change one at a
time. So:

* the optimiser state lives on `SACAgent`, not in `train()`, and `train()`
  accepts an existing agent — **fine-tuning does not reset Adam** unless asked;
* `replay.SEED_SPECS` is `V6D_SPECS`, the SPICE scale, so seeding introduces no
  third reward scale;
* `cfg.lr_finetune` exists so the learning rate can be the ONLY thing that
  changes on the second leg.

Episode dynamics are the env's business, not this file's. Use the revert
behaviour of `rl/analytic_env.py` (`NEXT_AGENT_SAC.md` §4).

WHAT THIS FILE DELIBERATELY DOES NOT DO
----------------------------------------
* It does not touch `ppo.py` (rule 6 — every published RL number came from it).
* It does not import an env. It is trained against anything exposing
  `observation_dim`, `action_dim`, `reset()` and `step()` — the duck type
  `analytic_env.py` and `corner_env.py` already share.
* It produces **no reportable number by itself**. A policy pre-trained on the
  analytic env carries that env's `is_analytic=True` provenance; only SPICE
  measurements are reportable.

SEEDING
-------
HANDOFF G3: never `np.random.seed()`. One seed arrives through `SACConfig` and
is threaded into `torch.manual_seed` and a `numpy.random.default_rng` used for
replay sampling. Stated in the run header, reproducible from the config alone.

    from nebula.rl.sac import SACConfig, SACAgent, train
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from nebula.rl.replay import ReplayBuffer

#: The reference SAC implementation's clamp on the state-dependent log-sigma
#: head. Not a tuning knob: without it an early gradient can drive sigma to 0
#: (log-prob -> inf) or to e^large (the tanh saturates and no gradient flows).
LOG_STD_MIN: float = -20.0
LOG_STD_MAX: float = 2.0


@dataclass
class SACConfig:
    """Every hyperparameter, with its origin. See the module docstring."""

    seed: int
    total_steps: int = 1000
    #: SAC paper / SB3 defaults. Changing any of these is a change to report.
    gamma: float = 0.99
    tau: float = 0.005
    lr: float = 3e-4
    batch_size: int = 256
    hidden: tuple = (256, 256)
    gradient_steps: int = 1
    learning_starts: int = 100
    buffer_capacity: int = 1_000_000
    #: `-dim(A)`. Left as None so it is derived from the env's action dim rather
    #: than hard-coded to 7 in two places (rule: one definition, referenced).
    target_entropy: Optional[float] = None
    #: alpha's initial value is exp(0) = 1.0, SB3's `ent_coef="auto"` start.
    log_alpha_init: float = 0.0
    #: **G114 lever 3.** Set on the SECOND leg of a two-stage run so the
    #: learning rate is the only thing that changed. None = use `lr`.
    lr_finetune: Optional[float] = None
    #: How often to record the gate telemetry (alpha, log_std). Every update is
    #: cheap and the run is long; 1 keeps the full trace.
    log_every: int = 1


def _mlp(in_dim: int, hidden: Sequence[int], out_dim: int) -> nn.Sequential:
    """SAC's default trunk: ReLU, unlike `ppo.py`'s Tanh. Both are upstream
    defaults for their own algorithm; neither was chosen here."""
    layers: list = []
    last = in_dim
    for h in hidden:
        layers += [nn.Linear(last, h), nn.ReLU()]
        last = h
    layers += [nn.Linear(last, out_dim)]
    return nn.Sequential(*layers)


class SquashedGaussianActor(nn.Module):
    """Gaussian policy, `tanh`-squashed, with the EXACT log-probability.

    **This is the one place SAC and `ppo.py` genuinely disagree, and both are
    right for their own algorithm.** `ppo.py` puts `tanh` on the MEAN and keeps
    the sample Gaussian, because PPO needs `log_prob(a)` of a stored action and
    a clipped action's log-probability would be wrong. SAC squashes the SAMPLE
    and corrects the density analytically:

        a = tanh(x),  x ~ N(mu, sigma)
        log pi(a) = log N(x) - sum_i log(1 - tanh(x_i)^2)

    The correction term is computed as `2*(log 2 - x - softplus(-2x))`, which is
    algebraically identical to `log(1 - tanh(x)^2)` and does not lose precision
    when `|x|` is large — the naive form underflows to `log(0)` exactly where a
    saturated action lives, which is where a converging policy spends its time.
    """

    def __init__(self, obs_dim: int, act_dim: int, hidden: Sequence[int]):
        super().__init__()
        self.trunk = _mlp(obs_dim, hidden, 2 * act_dim)
        self.act_dim = int(act_dim)

    def forward(self, obs: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        out = self.trunk(obs)
        mean, log_std = out[..., :self.act_dim], out[..., self.act_dim:]
        return mean, torch.clamp(log_std, LOG_STD_MIN, LOG_STD_MAX)

    def sample(self, obs: torch.Tensor):
        """Returns `(action, log_prob, mean, log_std)`. `rsample` — the actor
        loss differentiates THROUGH the sample (reparameterisation), which is
        what makes SAC's policy gradient low-variance."""
        mean, log_std = self.forward(obs)
        std = log_std.exp()
        x = mean + std * torch.randn_like(mean)          # reparameterised
        a = torch.tanh(x)
        logp = (-0.5 * (((x - mean) / std) ** 2) - log_std
                - 0.5 * math.log(2.0 * math.pi)).sum(-1)
        logp = logp - (2.0 * (math.log(2.0) - x
                              - F.softplus(-2.0 * x))).sum(-1)
        return a, logp, mean, log_std

    @torch.no_grad()
    def act(self, obs, deterministic: bool = False) -> np.ndarray:
        """One action for one observation, as a numpy array in `[-1, 1]^A`.

        `deterministic=True` returns `tanh(mean)` — the right thing for
        EVALUATION and for proposing a design to `exp_hybrid`, because a
        proposal is scored once and there is no reason to add noise to it.
        """
        o = torch.as_tensor(np.asarray(obs, dtype=np.float32)).unsqueeze(0)
        if deterministic:
            mean, _ = self.forward(o)
            return torch.tanh(mean).squeeze(0).numpy()
        a, _, _, _ = self.sample(o)
        return a.squeeze(0).numpy()


class TwinQ(nn.Module):
    """Two independent Q heads. The `min` of the pair is SAC's answer to the
    overestimation bias every value-based method has; one critic would learn a
    Q that is optimistic exactly where the data is thin."""

    def __init__(self, obs_dim: int, act_dim: int, hidden: Sequence[int]):
        super().__init__()
        self.q1 = _mlp(obs_dim + act_dim, hidden, 1)
        self.q2 = _mlp(obs_dim + act_dim, hidden, 1)

    def forward(self, obs: torch.Tensor, act: torch.Tensor):
        x = torch.cat([obs, act], dim=-1)
        return self.q1(x).squeeze(-1), self.q2(x).squeeze(-1)


@dataclass
class SACStats:
    """What a run reports. **`alpha` and `log_std_mean` ARE the stage-1 gate**
    (`NEXT_AGENT_SAC.md` §4); everything else is diagnosis."""

    step: list = field(default_factory=list)
    episode_return: list = field(default_factory=list)
    episode_length: list = field(default_factory=list)
    episode_end_step: list = field(default_factory=list)
    q_loss: list = field(default_factory=list)
    pi_loss: list = field(default_factory=list)
    alpha_loss: list = field(default_factory=list)
    #: The gate. Entropy coefficient, automatically tuned.
    alpha: list = field(default_factory=list)
    #: The gate's second witness: mean of the actor's log-sigma head.
    log_std_mean: list = field(default_factory=list)
    entropy: list = field(default_factory=list)
    n_updates: int = 0
    env_seconds: float = 0.0
    policy_seconds: float = 0.0
    update_seconds: float = 0.0

    def gate_report(self) -> dict:
        """The stage-1 gate, as a dict, with no verdict attached.

        Reports how far `alpha` and `log_std_mean` moved from their first
        recorded value. **It deliberately does not return a pass/fail** — the
        band belongs in `PREDICTIONS.md`, pre-registered before the run, not in
        the code that produces the number (rule 3).
        """
        if not self.alpha:
            raise RuntimeError(
                "no updates were recorded, so there is no gate to report -- "
                "a run shorter than learning_starts measures nothing")
        return {
            "n_updates": self.n_updates,
            "alpha_first": self.alpha[0], "alpha_last": self.alpha[-1],
            "alpha_min": min(self.alpha), "alpha_max": max(self.alpha),
            "log_std_first": self.log_std_mean[0],
            "log_std_last": self.log_std_mean[-1],
            "log_std_min": min(self.log_std_mean),
            "log_std_max": max(self.log_std_mean),
            "sigma_last": float(math.exp(self.log_std_mean[-1])),
        }


class SACAgent:
    """Actor, twin critics, targets, `log_alpha`, **and the three optimisers.**

    The optimisers live here rather than inside `train()` on purpose: G114's
    first uncontrolled change was a fresh Adam at full learning rate on the
    second leg of a two-stage run. Holding them on the agent means resuming
    training is the DEFAULT and resetting them has to be asked for.
    """

    def __init__(self, obs_dim: int, act_dim: int, cfg: SACConfig):
        self.obs_dim, self.act_dim = int(obs_dim), int(act_dim)
        self.cfg = cfg
        self.actor = SquashedGaussianActor(obs_dim, act_dim, cfg.hidden)
        self.critic = TwinQ(obs_dim, act_dim, cfg.hidden)
        self.critic_target = TwinQ(obs_dim, act_dim, cfg.hidden)
        self.critic_target.load_state_dict(self.critic.state_dict())
        for p in self.critic_target.parameters():
            p.requires_grad_(False)         # updated by soft copy, never Adam
        self.log_alpha = torch.tensor(float(cfg.log_alpha_init),
                                      requires_grad=True)
        self.target_entropy = float(
            cfg.target_entropy if cfg.target_entropy is not None
            else -float(act_dim))           # SAC's -dim(A) heuristic
        self.opt_actor = torch.optim.Adam(self.actor.parameters(), lr=cfg.lr)
        self.opt_critic = torch.optim.Adam(self.critic.parameters(), lr=cfg.lr)
        self.opt_alpha = torch.optim.Adam([self.log_alpha], lr=cfg.lr)

    # -- G114 lever 3 ---------------------------------------------------------

    def set_lr(self, lr: float) -> None:
        """Change the learning rate of all three optimisers **in place**, so
        Adam's moment estimates survive. This is the supported way to run a
        gentler second leg without also resetting the optimiser."""
        for opt in (self.opt_actor, self.opt_critic, self.opt_alpha):
            for g in opt.param_groups:
                g["lr"] = float(lr)

    @property
    def alpha(self) -> torch.Tensor:
        return self.log_alpha.exp()

    # -- one gradient step ----------------------------------------------------

    def update(self, batch: dict) -> dict:
        """One SAC update on one minibatch. Returns the telemetry, no side
        effects beyond the parameters and the target copy.

        `batch["done"]` **must be `terminated`, not `terminated or truncated`**
        — see the module docstring. A horizon cut is bootstrapped through.
        """
        obs = torch.as_tensor(batch["obs"], dtype=torch.float32)
        act = torch.as_tensor(batch["act"], dtype=torch.float32)
        rew = torch.as_tensor(batch["rew"], dtype=torch.float32)
        nxt = torch.as_tensor(batch["next_obs"], dtype=torch.float32)
        done = torch.as_tensor(batch["done"], dtype=torch.float32)

        alpha = self.alpha.detach()

        # ---- critics: the entropy-regularised Bellman backup ----------------
        with torch.no_grad():
            a2, logp2, _, _ = self.actor.sample(nxt)
            q1t, q2t = self.critic_target(nxt, a2)
            # The `- alpha * logp2` term is the whole of "soft": the value of a
            # state includes the entropy the policy will enjoy from it.
            backup = rew + self.cfg.gamma * (1.0 - done) * (
                torch.min(q1t, q2t) - alpha * logp2)
        q1, q2 = self.critic(obs, act)
        loss_q = F.mse_loss(q1, backup) + F.mse_loss(q2, backup)
        self.opt_critic.zero_grad()
        loss_q.backward()
        self.opt_critic.step()

        # ---- actor: maximise Q minus alpha * log pi -------------------------
        # Critic parameters are frozen for this backward so the actor's gradient
        # does not also drag the Q function toward whatever the actor prefers.
        for p in self.critic.parameters():
            p.requires_grad_(False)
        a_pi, logp_pi, _, log_std = self.actor.sample(obs)
        q1p, q2p = self.critic(obs, a_pi)
        loss_pi = (alpha * logp_pi - torch.min(q1p, q2p)).mean()
        self.opt_actor.zero_grad()
        loss_pi.backward()
        self.opt_actor.step()
        for p in self.critic.parameters():
            p.requires_grad_(True)

        # ---- alpha: drive entropy toward -dim(A) ----------------------------
        loss_alpha = -(self.log_alpha.exp()
                       * (logp_pi.detach() + self.target_entropy)).mean()
        self.opt_alpha.zero_grad()
        loss_alpha.backward()
        self.opt_alpha.step()

        # ---- target networks: Polyak, tau = 0.005 ---------------------------
        with torch.no_grad():
            for p, pt in zip(self.critic.parameters(),
                             self.critic_target.parameters()):
                pt.mul_(1.0 - self.cfg.tau).add_(self.cfg.tau * p)

        return {
            "q_loss": float(loss_q.item()),
            "pi_loss": float(loss_pi.item()),
            "alpha_loss": float(loss_alpha.item()),
            "alpha": float(self.alpha.item()),
            "log_std_mean": float(log_std.mean().item()),
            "entropy": float(-logp_pi.mean().item()),
        }

    # -- persistence ----------------------------------------------------------

    def state_dict(self) -> dict:
        """Everything needed to resume, **optimisers included** (G114)."""
        return {
            "actor": self.actor.state_dict(),
            "critic": self.critic.state_dict(),
            "critic_target": self.critic_target.state_dict(),
            "log_alpha": self.log_alpha.detach().clone(),
            "opt_actor": self.opt_actor.state_dict(),
            "opt_critic": self.opt_critic.state_dict(),
            "opt_alpha": self.opt_alpha.state_dict(),
            "obs_dim": self.obs_dim, "act_dim": self.act_dim,
            "target_entropy": self.target_entropy,
        }

    def load_state_dict(self, sd: dict) -> None:
        if int(sd["obs_dim"]) != self.obs_dim or int(sd["act_dim"]) != self.act_dim:
            raise ValueError(
                f"checkpoint is {sd['obs_dim']}x{sd['act_dim']}, this agent is "
                f"{self.obs_dim}x{self.act_dim} -- loading it would silently "
                f"mismatch the observation contract")
        self.actor.load_state_dict(sd["actor"])
        self.critic.load_state_dict(sd["critic"])
        self.critic_target.load_state_dict(sd["critic_target"])
        with torch.no_grad():
            self.log_alpha.copy_(sd["log_alpha"])
        self.opt_actor.load_state_dict(sd["opt_actor"])
        self.opt_critic.load_state_dict(sd["opt_critic"])
        self.opt_alpha.load_state_dict(sd["opt_alpha"])
        self.target_entropy = float(sd["target_entropy"])


def train(
    env,
    cfg: SACConfig,
    buffer: Optional[ReplayBuffer] = None,
    agent: Optional[SACAgent] = None,
    on_episode: Optional[Callable[[int, float, int], None]] = None,
) -> tuple[SACAgent, SACStats]:
    """Run `cfg.total_steps` environment steps of SAC. Returns (agent, stats).

    `total_steps` counts ENVIRONMENT steps — the same unit `ppo.py` counts and
    the unit the cost accounting divides by. On the SPICE env one step is 4
    decks, 1.26 s.

    `buffer` may arrive **already seeded** from `replay.seed_from_pool` — that
    is stage 2, and it is the reason SAC is here at all. A seeded buffer means
    the first gradient step sees real SPICE-measured transitions instead of
    `learning_starts` random flailing.

    `agent` may be an existing agent, in which case **its optimiser state is
    kept** and this call is a continuation, not a fresh run (G114 lever 1).
    """
    torch.manual_seed(cfg.seed)
    obs_dim, act_dim = env.observation_dim, env.action_dim
    if agent is None:
        agent = SACAgent(obs_dim, act_dim, cfg)
    elif (agent.obs_dim, agent.act_dim) != (obs_dim, act_dim):
        raise ValueError(
            f"agent is {agent.obs_dim}x{agent.act_dim} but env is "
            f"{obs_dim}x{act_dim} -- refusing to train across a contract change")
    if cfg.lr_finetune is not None:
        agent.set_lr(cfg.lr_finetune)     # the ONLY change on a second leg
    if buffer is None:
        buffer = ReplayBuffer(cfg.buffer_capacity, obs_dim, act_dim)

    # G3: one seed, threaded. Never `np.random.seed()`.
    rng = np.random.default_rng(cfg.seed)
    stats = SACStats()

    t0 = time.perf_counter()
    obs, _ = env.reset()
    stats.env_seconds += time.perf_counter() - t0

    ep_return, ep_len, n_done = 0.0, 0, 0

    for step in range(int(cfg.total_steps)):
        # Before `learning_starts`, act uniformly at random. SB3's default, and
        # it matters more than usual here: an untrained tanh policy concentrates
        # near a = 0, which explores almost nothing in a 7-D box.
        t0 = time.perf_counter()
        if len(buffer) < cfg.learning_starts:
            action = rng.uniform(-1.0, 1.0, act_dim).astype(np.float32)
        else:
            action = agent.actor.act(obs, deterministic=False)
        stats.policy_seconds += time.perf_counter() - t0

        t0 = time.perf_counter()
        obs2, rew, terminated, truncated, _ = env.step(action)
        stats.env_seconds += time.perf_counter() - t0

        # **`terminated` only.** A truncated episode is bootstrapped through;
        # storing `truncated` here would teach the critic the horizon is a
        # cliff. See the module docstring.
        buffer.add(obs, action, float(rew), obs2, bool(terminated))

        ep_return += float(rew)
        ep_len += 1
        obs = obs2

        if terminated or truncated:
            stats.episode_return.append(ep_return)
            stats.episode_length.append(ep_len)
            stats.episode_end_step.append(step + 1)
            if on_episode is not None:
                on_episode(n_done, ep_return, ep_len)
            n_done += 1
            ep_return, ep_len = 0.0, 0
            t0 = time.perf_counter()
            obs, _ = env.reset()
            stats.env_seconds += time.perf_counter() - t0

        if len(buffer) < cfg.learning_starts:
            continue

        t0 = time.perf_counter()
        for _ in range(int(cfg.gradient_steps)):
            tel = agent.update(buffer.sample(cfg.batch_size, rng))
            stats.n_updates += 1
            if stats.n_updates % max(1, int(cfg.log_every)) == 0:
                stats.step.append(step + 1)
                stats.q_loss.append(tel["q_loss"])
                stats.pi_loss.append(tel["pi_loss"])
                stats.alpha_loss.append(tel["alpha_loss"])
                stats.alpha.append(tel["alpha"])
                stats.log_std_mean.append(tel["log_std_mean"])
                stats.entropy.append(tel["entropy"])
        stats.update_seconds += time.perf_counter() - t0

    return agent, stats


__all__: Sequence[str] = ("SACConfig", "SACAgent", "SquashedGaussianActor",
                          "TwinQ", "SACStats", "train",
                          "LOG_STD_MIN", "LOG_STD_MAX")
