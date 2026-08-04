"""
reproduce_tables.py
--------------------
End-to-end driver: trains RL-PPO, RL-PPO-Offline, RL-PPO-Online,
RL-PPO-Blend-{p} for p in {0.2,0.5,1,2,5}, and RL-DDPG on a chosen circuit,
evaluates each against SNDR>=60dB/75dB pass rates, and prints/saves a
Table-II/III-style comparison (pandas DataFrame -> CSV + Markdown).

This uses small default timesteps so the *pipeline* runs quickly end-to-end
in this sandbox; it will NOT reproduce the paper's exact percentages (that
needs the paper's real Spectre PDK + 1e5-step training runs, see
simulator.py's docstring). Bump --timesteps / --n-init / --n-test to scale
toward the paper's regime; expect RL-PPO-Online / higher blend fractions to
get much slower as SPICE-call count grows, exactly as Table III shows.

Usage:
    python reproduce_tables.py --circuit buffer_switch --timesteps 4000
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys
import pandas as pd

from evaluate import evaluate


def run_train(circuit, mode, timesteps, n_init, K, B, blend_p, seed, outdir):
    cmd = [sys.executable, "train.py", "--circuit", circuit, "--mode", mode,
           "--timesteps", str(timesteps), "--n-init", str(n_init),
           "--K", str(K), "--B", str(B), "--blend-p", str(blend_p),
           "--seed", str(seed), "--outdir", outdir]
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)
    name = f"{circuit}_{mode}" + (f"_p{blend_p}" if mode == "blend" else "")
    return os.path.join(outdir, name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--circuit", choices=["bootstrapped_switch", "buffer_switch"], required=True)
    ap.add_argument("--timesteps", type=int, default=4000)
    ap.add_argument("--online-timesteps", type=int, default=None,
                     help="override timesteps for RL-PPO-Online (paper: 19x slower per step)")
    ap.add_argument("--n-init", type=int, default=600)
    ap.add_argument("--n-test", type=int, default=100)
    ap.add_argument("--K", type=int, default=25)
    ap.add_argument("--B", type=int, default=32)
    ap.add_argument("--blend-schedule", type=float, nargs="+", default=[0.2, 0.5, 1, 2, 5])
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--outdir", type=str, default="../results")
    ap.add_argument("--skip-online", action="store_true", help="online mode is the slowest; skip for a quick smoke run")
    args = ap.parse_args()

    online_ts = args.online_timesteps or args.timesteps
    rows = []

    plan = [
        ("ddpg", {}), ("ppo", {}), ("offline", {}),
    ]
    if not args.skip_online:
        plan.append(("online", {}))
    for p in args.blend_schedule:
        plan.append(("blend", {"blend_p": p}))

    for mode, kw in plan:
        ts = online_ts if mode == "online" else args.timesteps
        run_dir = run_train(args.circuit, mode, ts, args.n_init, args.K, args.B,
                             kw.get("blend_p", 1.0), args.seed, args.outdir)
        result = evaluate(run_dir, n_test=args.n_test)
        label = {"ppo": "RL-PPO", "offline": "RL-PPO-Offline", "online": "RL-PPO-Online",
                 "ddpg": "RL-DDPG"}.get(mode, f"RL-PPO-Blend-{kw.get('blend_p')}")
        rows.append({
            "Method": label, "Circuit": args.circuit,
            "SNDR>=60dB (%)": round(result["pass_rate_SNDR_ge_60dB"], 1),
            "SNDR>=75dB (%)": round(result["pass_rate_SNDR_ge_75dB"], 1),
            "Time (s) / 1k steps": round(result["time_per_1k_steps_s"], 1),
            "SPICE calls (train)": result["total_spice_calls_during_training"],
        })

    df = pd.DataFrame(rows)
    print("\n" + df.to_string(index=False))
    csv_path = os.path.join(args.outdir, f"table_{args.circuit}.csv")
    md_path = os.path.join(args.outdir, f"table_{args.circuit}.md")
    df.to_csv(csv_path, index=False)
    with open(md_path, "w") as f:
        f.write(df.to_markdown(index=False))
    print(f"\nSaved: {csv_path}\nSaved: {md_path}")


if __name__ == "__main__":
    main()
