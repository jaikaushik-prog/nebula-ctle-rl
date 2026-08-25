"""**SAC: is the algorithm actually the algorithm?**

`rl/sac.py` is 400 lines of standard SAC, and standard SAC has three places
where a wrong implementation still trains, still produces plausible curves, and
is simply solving a different problem:

1. **the tanh log-probability correction.** Drop it, or get its sign wrong, and
   the entropy term is nonsense -- so `alpha` (the stage-1 gate) tunes toward a
   target entropy that is not the policy's entropy. Section 2 checks it against
   an independent construction.
2. **`terminated` vs `truncated` in the Bellman backup.** Bootstrapping through
   a real termination inflates every Q; not bootstrapping through a horizon cut
   makes the horizon a cliff. Section 4 pins it by training to a value that is
   only correct if `done` is honoured exactly.
3. **the Polyak update.** `tau = 0.005` copied the wrong way round, or applied
   to the wrong network, is a stable-looking run that never improves. Section 3
   checks the arithmetic term by term.

Everything else here fences the G114 machinery: the optimiser state must SURVIVE
a fine-tuning leg, because the last time it did not, a trained policy was
erased and the run reported success.

No SPICE, no env import -- a fake env exercises the loop in milliseconds.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
import torch

from nebula.rl.replay import ReplayBuffer
from nebula.rl.sac import (
    LOG_STD_MAX,
    LOG_STD_MIN,
    SACAgent,
    SACConfig,
    SACStats,
    SquashedGaussianActor,
    TwinQ,
    train,
)

OBS_DIM, ACT_DIM = 4, 2
SMALL = (16, 16)          # test-only network size; the default (256,256) is slow


def _cfg(**kw) -> SACConfig:
    base = dict(seed=7, total_steps=40, hidden=SMALL, batch_size=8,
                learning_starts=10, buffer_capacity=1000)
    base.update(kw)
    return SACConfig(**base)


def _agent(**kw) -> SACAgent:
    return SACAgent(OBS_DIM, ACT_DIM, _cfg(**kw))


class _FakeEnv:
    """Cheap, deterministic-given-seed, and it TRUNCATES rather than
    terminating, so the loop's two exit paths are both exercised."""

    def __init__(self, seed: int = 0, horizon: int = 5, terminate_at=None):
        self.observation_dim, self.action_dim = OBS_DIM, ACT_DIM
        self.horizon = horizon
        self.terminate_at = terminate_at
        self.rng = np.random.default_rng(seed)
        self._t = 0
        self._s = np.zeros(OBS_DIM, dtype=np.float32)
        self.n_reset = 0

    def reset(self):
        self.n_reset += 1
        self._t = 0
        self._s = self.rng.uniform(-1, 1, OBS_DIM).astype(np.float32)
        return self._s.copy(), {}

    def step(self, action):
        a = np.asarray(action, dtype=np.float32)
        self._s = np.clip(self._s + 0.1 * np.resize(a, OBS_DIM), -1, 1)
        self._t += 1
        rew = float(-np.abs(self._s).sum())
        terminated = bool(self.terminate_at is not None
                          and self._t >= self.terminate_at)
        truncated = bool(self._t >= self.horizon) and not terminated
        return self._s.copy(), rew, terminated, truncated, {}


def _fill(buf: ReplayBuffer, n: int, *, rew: float, done: bool, seed: int = 0):
    rng = np.random.default_rng(seed)
    for _ in range(n):
        o = rng.uniform(-1, 1, OBS_DIM).astype(np.float32)
        a = rng.uniform(-1, 1, ACT_DIM).astype(np.float32)
        buf.add(o, a, rew, o, done)
    return buf


# ── 1. Actor: shapes, bounds, the log_std clamp ───────────────────────────────

def test_actor_actions_are_inside_the_tanh_box():
    torch.manual_seed(0)
    actor = SquashedGaussianActor(OBS_DIM, ACT_DIM, SMALL)
    obs = torch.randn(256, OBS_DIM)
    a, logp, mean, log_std = actor.sample(obs)
    assert a.shape == (256, ACT_DIM) and logp.shape == (256,)
    assert a.min().item() > -1.0 and a.max().item() < 1.0
    assert torch.all(torch.isfinite(logp))


def test_log_std_is_clamped_to_the_reference_range():
    torch.manual_seed(0)
    actor = SquashedGaussianActor(OBS_DIM, ACT_DIM, SMALL)
    # Drive the log_std head hard in both directions and require the clamp.
    with torch.no_grad():
        actor.trunk[-1].bias[ACT_DIM:] = 500.0
    _, ls = actor.forward(torch.randn(8, OBS_DIM))
    assert torch.all(ls <= LOG_STD_MAX + 1e-6)
    with torch.no_grad():
        actor.trunk[-1].bias[ACT_DIM:] = -500.0
    _, ls = actor.forward(torch.randn(8, OBS_DIM))
    assert torch.all(ls >= LOG_STD_MIN - 1e-6)


def test_deterministic_act_is_tanh_of_the_mean_and_is_noiseless():
    torch.manual_seed(0)
    actor = SquashedGaussianActor(OBS_DIM, ACT_DIM, SMALL)
    obs = np.linspace(-1, 1, OBS_DIM).astype(np.float32)
    a1 = actor.act(obs, deterministic=True)
    a2 = actor.act(obs, deterministic=True)
    assert np.array_equal(a1, a2), "a proposal must not be noisy"
    mean, _ = actor.forward(torch.as_tensor(obs).unsqueeze(0))
    assert np.allclose(a1, torch.tanh(mean).detach().squeeze(0).numpy(),
                       atol=1e-6)
    assert not np.array_equal(a1, actor.act(obs, deterministic=False))


# ── 2. THE LOG-PROBABILITY, against an independent construction ───────────────

def test_squashed_log_prob_matches_change_of_variables():
    """`log pi(a) = log N(x) - sum log(1 - tanh(x)^2)`, checked the naive way.

    `sac.py` uses the numerically stable `2*(log2 - x - softplus(-2x))` form.
    Here the SAME quantity is rebuilt from `torch.distributions.Normal` and the
    textbook `log(1 - a^2)`, which is accurate for the moderate `|a|` a fresh
    policy produces. Agreement means the algebra is right; the stable form is
    then strictly better where the naive one underflows.
    """
    torch.manual_seed(3)
    actor = SquashedGaussianActor(OBS_DIM, ACT_DIM, SMALL)
    obs = torch.randn(512, OBS_DIM)
    a, logp, mean, log_std = actor.sample(obs)

    x = torch.atanh(a.clamp(-1 + 1e-6, 1 - 1e-6))
    ref = torch.distributions.Normal(mean, log_std.exp()).log_prob(x).sum(-1)
    ref = ref - torch.log(1.0 - a.pow(2) + 1e-12).sum(-1)

    assert torch.allclose(logp, ref, atol=1e-3, rtol=1e-3), (
        f"max |logp - reference| = {(logp - ref).abs().max().item():.3e}")


def test_squashed_log_prob_stays_finite_where_the_naive_form_dies():
    """The reason for the `softplus` form: a saturated action.

    A converging policy spends its time near `|a| = 1`, where `log(1 - a^2)`
    underflows to `-inf`. The stable form must still return a finite number --
    otherwise the actor loss becomes `nan` exactly when training starts working.
    """
    torch.manual_seed(0)
    actor = SquashedGaussianActor(OBS_DIM, ACT_DIM, SMALL)
    with torch.no_grad():                      # push the mean far out
        actor.trunk[-1].bias[:ACT_DIM] = 30.0
        actor.trunk[-1].bias[ACT_DIM:] = -3.0
    a, logp, _, _ = actor.sample(torch.randn(64, OBS_DIM))
    assert torch.all(a.abs() > 1.0 - 1e-6), "fixture failed to saturate tanh"
    assert torch.all(torch.isfinite(logp)), "the stable log-prob went non-finite"


# ── 3. Twin critics and the Polyak target update ──────────────────────────────

def test_twin_critics_are_independent_heads():
    torch.manual_seed(0)
    critic = TwinQ(OBS_DIM, ACT_DIM, SMALL)
    q1, q2 = critic(torch.randn(32, OBS_DIM), torch.randn(32, ACT_DIM))
    assert q1.shape == (32,) and q2.shape == (32,)
    assert not torch.allclose(q1, q2), (
        "both Q heads returned the same value -- min(Q1,Q2) is then a no-op "
        "and the overestimation guard is absent")


def test_target_starts_equal_and_moves_by_exactly_tau():
    agent = _agent()
    for p, pt in zip(agent.critic.parameters(),
                     agent.critic_target.parameters()):
        assert torch.allclose(p, pt), "target must start as a copy of the critic"

    before_c = [p.detach().clone() for p in agent.critic.parameters()]
    before_t = [p.detach().clone() for p in agent.critic_target.parameters()]
    buf = _fill(ReplayBuffer(64, OBS_DIM, ACT_DIM), 32, rew=1.0, done=False)
    agent.update(buf.sample(8, np.random.default_rng(0)))

    tau = agent.cfg.tau
    moved = False
    for pt_new, c_old, t_old, p_new in zip(
            agent.critic_target.parameters(), before_c, before_t,
            agent.critic.parameters()):
        # The target is smoothed toward the critic's value AFTER its own step.
        expect = (1.0 - tau) * t_old + tau * p_new.detach()
        assert torch.allclose(pt_new, expect, atol=1e-6), (
            "Polyak update does not match (1-tau)*target + tau*critic")
        if not torch.allclose(pt_new, t_old):
            moved = True
        del c_old
    assert moved, "the target network did not move at all"


def test_target_parameters_are_not_owned_by_an_optimiser():
    agent = _agent()
    owned = {id(p) for g in agent.opt_critic.param_groups for p in g["params"]}
    for p in agent.critic_target.parameters():
        assert id(p) not in owned, "target params must move by soft copy only"
        assert not p.requires_grad


# ── 4. THE BOOTSTRAP: `done` is terminated-only, and it is load-bearing ────────

def test_terminal_transitions_make_q_converge_to_the_reward_alone():
    """With `done = 1`, the backup is `r` exactly -- gamma and the target net
    drop out. Train on a constant-reward terminal buffer and Q must land on the
    reward. If `done` were ignored, Q would run off toward `r/(1-gamma)`.
    """
    agent = _agent(hidden=SMALL)
    buf = _fill(ReplayBuffer(256, OBS_DIM, ACT_DIM), 128, rew=1.0, done=True)
    rng = np.random.default_rng(0)
    for _ in range(600):
        agent.update(buf.sample(64, rng))
    mb = buf.sample(64, rng)
    with torch.no_grad():
        q1, q2 = agent.critic(torch.as_tensor(mb["obs"]),
                              torch.as_tensor(mb["act"]))
    assert abs(float(q1.mean()) - 1.0) < 0.25, float(q1.mean())
    assert abs(float(q2.mean()) - 1.0) < 0.25, float(q2.mean())


def test_nonterminal_transitions_bootstrap_to_a_larger_value():
    """Same data, `done = 0`: the backup now includes `gamma * Q(s')`, so the
    value must be clearly ABOVE the one-step reward. This is the discriminator
    -- a run that stored `truncated` in `done` would collapse the two."""
    rng = np.random.default_rng(0)
    q = {}
    for done in (True, False):
        agent = _agent()
        buf = _fill(ReplayBuffer(256, OBS_DIM, ACT_DIM), 128,
                    rew=1.0, done=done, seed=1)
        for _ in range(600):
            agent.update(buf.sample(64, np.random.default_rng(2)))
        mb = buf.sample(64, rng)
        with torch.no_grad():
            q1, _ = agent.critic(torch.as_tensor(mb["obs"]),
                                 torch.as_tensor(mb["act"]))
        q[done] = float(q1.mean())
    assert q[False] > q[True] + 0.5, (
        f"bootstrapped Q ({q[False]:.3f}) is not clearly above the terminal one "
        f"({q[True]:.3f}) -- the done flag is not reaching the backup")


def test_train_stores_terminated_not_truncated():
    """The fake env truncates at the horizon and never terminates, so a correct
    loop stores `done = 0` for every transition."""
    env = _FakeEnv(seed=0, horizon=4, terminate_at=None)
    buf = ReplayBuffer(1000, OBS_DIM, ACT_DIM)
    train(env, _cfg(total_steps=24, learning_starts=1000), buffer=buf)
    assert len(buf) == 24
    assert float(buf._done[:24].max()) == 0.0, (
        "a horizon cut was stored as a termination -- the critic will treat "
        "the horizon as a cliff")


def test_train_does_store_a_real_termination():
    env = _FakeEnv(seed=0, horizon=9, terminate_at=3)
    buf = ReplayBuffer(1000, OBS_DIM, ACT_DIM)
    train(env, _cfg(total_steps=24, learning_starts=1000), buffer=buf)
    assert float(buf._done[:24].max()) == 1.0
    assert float(buf._done[:24].sum()) == 8.0      # 24 steps / terminate at 3


# ── 5. The stage-1 gate is measurable and never fabricated ────────────────────

def test_alpha_and_log_std_are_recorded_every_update():
    env = _FakeEnv(seed=1)
    cfg = _cfg(total_steps=40, learning_starts=10)
    _, stats = train(env, cfg)
    # one update per env step once the buffer reaches learning_starts
    assert stats.n_updates == cfg.total_steps - cfg.learning_starts + 1
    assert len(stats.alpha) == stats.n_updates
    assert len(stats.log_std_mean) == stats.n_updates
    assert all(math.isfinite(v) for v in stats.alpha)
    assert all(v > 0.0 for v in stats.alpha), "alpha = exp(log_alpha) > 0"


def test_alpha_moves_off_its_initial_value():
    """The gate itself, on a toy problem. `alpha` starts at exp(0) = 1.0 and the
    entropy loss must push it somewhere. A frozen alpha means the entropy term
    is disconnected -- which is precisely PPO's unmoved `log_std`."""
    _, stats = train(_FakeEnv(seed=2), _cfg(total_steps=60, learning_starts=10))
    g = stats.gate_report()
    assert g["alpha_first"] == pytest.approx(1.0, abs=0.05)
    assert abs(g["alpha_last"] - g["alpha_first"]) > 1e-4, (
        f"alpha never moved: {g}")


def test_gate_report_raises_rather_than_inventing_a_number():
    # Rule 5: a missing measurement raises; it never gets a placeholder.
    with pytest.raises(RuntimeError):
        SACStats().gate_report()
    # A run shorter than learning_starts genuinely measures nothing.
    _, stats = train(_FakeEnv(seed=0), _cfg(total_steps=5, learning_starts=100))
    assert stats.n_updates == 0
    with pytest.raises(RuntimeError):
        stats.gate_report()


def test_gate_report_sigma_is_exp_of_log_std():
    _, stats = train(_FakeEnv(seed=3), _cfg(total_steps=30, learning_starts=10))
    g = stats.gate_report()
    assert g["sigma_last"] == pytest.approx(math.exp(g["log_std_last"]))


# ── 6. Target entropy is -dim(A), derived once ────────────────────────────────

def test_target_entropy_defaults_to_minus_action_dim():
    assert _agent().target_entropy == -float(ACT_DIM)
    a = SACAgent(OBS_DIM, ACT_DIM, _cfg(target_entropy=-3.0))
    assert a.target_entropy == -3.0


# ── 7. G114: the optimiser survives a fine-tuning leg ─────────────────────────

def _adam_steps(opt) -> float:
    """A SNAPSHOT of Adam's step counter, as a float.

    `opt.state_dict()["state"][i]["step"]` hands back the LIVE 0-dim tensor, not
    a copy. Holding that handle across a training leg and comparing it to itself
    is a test that can never fail -- which is what the first version of
    `test_train_reuses_a_passed_agent_and_keeps_adam_state` did. Snapshot it.
    """
    return float(opt.state_dict()["state"][0]["step"])


def test_train_reuses_a_passed_agent_and_keeps_adam_state():
    env = _FakeEnv(seed=4)
    agent, _ = train(env, _cfg(total_steps=30, learning_starts=10))
    steps_before = _adam_steps(agent.opt_actor)
    assert steps_before > 0
    same, _ = train(_FakeEnv(seed=5), _cfg(total_steps=30, learning_starts=10),
                    agent=agent)
    assert same is agent, "train() must continue the agent it was given"
    assert _adam_steps(agent.opt_actor) > steps_before, (
        "Adam's step counter reset -- this is G114's first uncontrolled change")


def test_set_lr_changes_the_rate_without_resetting_the_optimiser():
    agent = _agent()
    buf = _fill(ReplayBuffer(64, OBS_DIM, ACT_DIM), 32, rew=0.5, done=False)
    agent.update(buf.sample(8, np.random.default_rng(0)))
    before = _adam_steps(agent.opt_actor)
    agent.set_lr(1e-5)
    for opt in (agent.opt_actor, agent.opt_critic, agent.opt_alpha):
        assert all(g["lr"] == 1e-5 for g in opt.param_groups)
    assert _adam_steps(agent.opt_actor) == before


def test_lr_finetune_is_applied_and_is_the_only_change():
    agent = _agent()
    train(_FakeEnv(seed=6), _cfg(total_steps=12, learning_starts=1000,
                                 lr_finetune=1e-6), agent=agent)
    assert all(g["lr"] == 1e-6 for g in agent.opt_actor.param_groups)


# ── 8. Persistence and the contract guard ─────────────────────────────────────

def test_state_dict_round_trip_restores_behaviour():
    agent = _agent()
    buf = _fill(ReplayBuffer(128, OBS_DIM, ACT_DIM), 64, rew=1.0, done=False)
    for _ in range(20):
        agent.update(buf.sample(16, np.random.default_rng(0)))
    obs = np.linspace(-1, 1, OBS_DIM).astype(np.float32)
    want = agent.actor.act(obs, deterministic=True)

    fresh = _agent()
    assert not np.allclose(fresh.actor.act(obs, deterministic=True), want)
    fresh.load_state_dict(agent.state_dict())
    assert np.allclose(fresh.actor.act(obs, deterministic=True), want, atol=1e-6)
    assert float(fresh.log_alpha.detach()) == pytest.approx(
        float(agent.log_alpha.detach()))


def test_load_state_dict_refuses_a_dimension_mismatch():
    sd = _agent().state_dict()
    other = SACAgent(OBS_DIM + 1, ACT_DIM, _cfg())
    with pytest.raises(ValueError):
        other.load_state_dict(sd)


def test_train_refuses_an_agent_that_does_not_match_the_env():
    agent = SACAgent(OBS_DIM + 3, ACT_DIM, _cfg())
    with pytest.raises(ValueError):
        train(_FakeEnv(seed=0), _cfg(total_steps=4), agent=agent)


# ── 9. Determinism (G3) and the seeded-buffer path (stage 2) ───────────────────

def test_same_seed_same_run():
    r1 = train(_FakeEnv(seed=0), _cfg(total_steps=30))[1].episode_return
    r2 = train(_FakeEnv(seed=0), _cfg(total_steps=30))[1].episode_return
    assert r1 == r2 and len(r1) > 0


def test_different_seed_different_run():
    a = train(_FakeEnv(seed=0), _cfg(total_steps=30, seed=1))[1].alpha
    b = train(_FakeEnv(seed=0), _cfg(total_steps=30, seed=2))[1].alpha
    assert a != b


def test_a_prefilled_buffer_starts_learning_immediately():
    """Stage 2's whole point: a buffer seeded from `spec_pool` means the first
    environment step already has a gradient step behind it, instead of
    `learning_starts` random actions."""
    buf = _fill(ReplayBuffer(1000, OBS_DIM, ACT_DIM), 200, rew=1.0, done=False)
    cfg = _cfg(total_steps=10, learning_starts=100)
    _, stats = train(_FakeEnv(seed=0), cfg, buffer=buf)
    assert stats.n_updates == cfg.total_steps, (
        "a pre-seeded buffer must skip the random warm-up entirely")


def test_random_warmup_actions_are_in_the_action_box():
    buf = ReplayBuffer(1000, OBS_DIM, ACT_DIM)
    train(_FakeEnv(seed=0), _cfg(total_steps=20, learning_starts=1000),
          buffer=buf)
    assert buf._act[:20].min() >= -1.0 and buf._act[:20].max() <= 1.0


def test_episode_bookkeeping_is_consistent():
    env = _FakeEnv(seed=0, horizon=5)
    _, stats = train(env, _cfg(total_steps=25, learning_starts=1000))
    assert len(stats.episode_return) == len(stats.episode_length) == 5
    assert all(n == 5 for n in stats.episode_length)
    assert env.n_reset == 6            # one initial + one per finished episode
