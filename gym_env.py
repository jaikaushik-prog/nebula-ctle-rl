"""
evaluate.py
-----------
Loads a trained policy (from train.py's run_dir) and reports pass rates
against SNDR >= 60 dB / SNDR >= 75 dB on unseen test parameter proposals,
matching Sec. V.C's evaluation protocol: "percentage of generated parameter
sets that achieve SNDR >= 60dB and SNDR >= 75dB ... on unseen test points."

Ground-truth pass/fail is decided using the REAL simulator (SyntheticSpiceEnv,
i.e. our SPICE stand-in), not the regressor -- consistent with the paper
evaluating final designs against SPICE, not against the surrogate.

Usage:
    python evaluate.py --run-dir ../results/buffer_switch_offline --n-test 200
"""
from __future__ import annotations
import argparse, json, os
import numpy as np
from stable_baselines3 import PPO, DDPG

from circuits import dim, denormalize
from simulator import SyntheticSpiceEnv
from regressor import EnsembleRegressor
from discriminator import DiscriminatorTrainer
from gym_env import AMSDesignEnv


def load_regressor(run_dir, circuit, device="cpu"):
    import torch
    d = dim(circuit)
    reg = EnsembleRegressor(in_dim=d, n_models=5)
    sd = torch.load(os.path.join(run_dir, "regressor.pt"), map_location=device)
    for i, m in enumerate(reg.models):
        m.load_state_dict(sd[f"member_{i}"])
        m.eval()
    norm = np.load(os.path.join(run_dir, "regressor_norm.npz"))
    reg.x_mean, reg.x_std = norm["x_mean"], norm["x_std"]
    reg.y_mean, reg.y_std = norm["y_mean"], norm["y_std"]
    return reg


def evaluate(run_dir: str, n_test: int = 200, tau_sndr=60.0, tau_sfdr=60.0, seed=123):
    with open(os.path.join(run_dir, "train_summary.json")) as f:
        summary = json.load(f)
    circuit = summary["circuit"]
    mode = summary["mode"]
    d = dim(circuit)

    algo_cls = DDPG if mode == "ddpg" else PPO
    model = algo_cls.load(os.path.join(run_dir, "policy"))

    spice = SyntheticSpiceEnv(circuit, seed=seed + 1)  # independent seed from training
    regressor = load_regressor(run_dir, circuit)

    # dummy env just to get correctly-shaped observations conditioned on the
    # requested thresholds; policy is queried directly (no discriminator needed at eval time)
    env = AMSDesignEnv(circuit, spice, regressor, discriminator=None, mode="ppo", seed=seed)

    results_60, results_75 = [], []
    sndr_list, sfdr_list = [], []
    for i in range(n_test):
        env._cur_tau_sndr = tau_sndr
        env._cur_tau_sfdr = tau_sfdr
        obs = env._obs()
        action, _ = model.predict(obs, deterministic=True)
        phys = denormalize(np.asarray(action), circuit)
        sndr, sfdr, _ = spice.evaluate(phys)
        sndr_list.append(sndr); sfdr_list.append(sfdr)
        results_60.append(sndr >= 60.0)
        results_75.append(sndr >= 75.0)

    out = {
        "run_dir": run_dir, "circuit": circuit, "mode": mode,
        "n_test": n_test,
        "pass_rate_SNDR_ge_60dB": float(np.mean(results_60)) * 100,
        "pass_rate_SNDR_ge_75dB": float(np.mean(results_75)) * 100,
        "mean_SNDR_dB": float(np.mean(sndr_list)),
        "mean_SFDR_dB": float(np.mean(sfdr_list)),
        "time_per_1k_steps_s": summary.get("time_per_1k_steps_s"),
        "total_spice_calls_during_training": summary.get("total_spice_calls"),
    }
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--n-test", type=int, default=200)
    args = ap.parse_args()
    result = evaluate(args.run_dir, n_test=args.n_test)
    print(json.dumps(result, indent=2))
    with open(os.path.join(args.run_dir, "eval_result.json"), "w") as f:
        json.dump(result, f, indent=2)
