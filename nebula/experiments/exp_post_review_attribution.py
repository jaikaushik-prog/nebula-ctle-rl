"""Entry 113: post-review, cached attribution; never trains or simulates."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import subprocess
import time
from pathlib import Path

import numpy as np
import torch

from nebula.experiments import exp_shielded_final as F
from nebula.experiments import exp_shielded_ppo as P
from nebula.experiments import exp_margin_improve_controls as B
from nebula.rl.margin_improve_env import MarginImproveEnv
from nebula.rl.masked_discrete_ppo import MaskedActorCritic, deterministic_action
from nebula.rl.safety_shield import select_best_compliant_visited

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "nebula/POST_REVIEW_PLAN.md"
BUDGETS = (2, 4, 8)
RANDOM_SEEDS = tuple(range(2026090700, 2026090720))
BOOTSTRAP_SEED = 20260907113


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def frozen_plan():
    committed = subprocess.check_output(
        ["git", "show", "HEAD:nebula/POST_REVIEW_PLAN.md"], cwd=ROOT)
    # Git normalises working-tree CRLF.
    if committed.replace(b"\r\n", b"\n") != PLAN.read_bytes().replace(b"\r\n", b"\n"):
        raise ValueError("protocol must be committed unchanged before measurement")
    return hashlib.sha256(committed).hexdigest()


def policy_trace(table, identity, starts, net):
    env = MarginImproveEnv(table, [identity], starts)
    obs = env.reset(corner=identity[0], loss_db=identity[1], request=identity[2:])
    while env.ep.locked_setting is None:
        obs, _, done, _, _ = env.step(deterministic_action(net, obs, env.action_mask()))
        if done:
            break
    return list(env.ep.settings_tried)


def random_trace(start, rng, *, global_search=False):
    if global_search:
        candidates = [s for s in range(512) if s != start]
        return [start] + [int(s) for s in rng.choice(candidates, 7, replace=False)]
    visits = [start]
    for _ in range(7):
        current = visits[-1]
        moves = [a for a in range(6)
                 if MarginImproveEnv.moved_setting(current, a) != current]
        visits.append(MarginImproveEnv.moved_setting(current, int(rng.choice(moves))))
    return visits


def hill_trace(table, identity, starts):
    env = MarginImproveEnv(table, [identity], starts)
    env.reset(corner=identity[0], loss_db=identity[1], request=identity[2:])
    B.arm_hillclimb(env)
    return list(env.ep.settings_tried)


def score_trace(table, identity, visits, cap):
    if not visits or not 1 <= len(visits) <= 8:
        raise ValueError("invalid trajectory length")
    used = visits[:cap]
    selected = select_best_compliant_visited(table, identity, used)
    return dict(identity=list(identity), visits=used, selected=selected.setting,
                compliant=selected.compliant, quality=selected.quality,
                n_visits=len(used), n_unique=len(set(used)),
                shield_intervened=selected.intervened,
                verifier_calls=selected.n_verifier_calls)


def summary(rows):
    return {key: float(np.mean([r[key] for r in rows]))
            for key in ("compliant", "quality", "n_visits", "n_unique",
                        "verifier_calls", "shield_intervened")}


def grouped_interval(identities, differences, seed=BOOTSTRAP_SEED):
    groups = {}
    for identity, delta in zip(identities, differences, strict=True):
        groups.setdefault(tuple(identity[1:]), []).append(float(delta))
    values = np.array([np.mean(v) for _, v in sorted(groups.items())])
    rng = np.random.default_rng(seed)
    boot = values[rng.integers(len(values), size=(10000, len(values)))].mean(axis=1)
    return [float(v) for v in np.percentile(boot, [2.5, 97.5])]


def assert_replay(records, historical):
    if len(records) != len(historical):
        raise ValueError("PPO replay identity count mismatch")
    by_id = {(r["corner"], r["loss_db"], r["target_peaking_db"],
              r["target_f_peak_hz"]): r for r in historical}
    for row in records:
        old = by_id[tuple(row["identity"])]
        if (row["selected"] != old["locked_setting"]
                or row["compliant"] != bool(old["compliant"])
                or row["n_visits"] != old["n_trials"]
                or abs(row["quality"] - old["quality"]) > 1e-12):
            raise ValueError("frozen PPO replay differs from historical result")


def run(out):
    out = Path(out)
    protocol_hash = frozen_plan()
    out.mkdir(parents=True, exist_ok=False)
    start_time = time.perf_counter()
    torch.set_num_threads(1)
    source_hashes = {}
    for path, expected in [(P.HERE / P.MANIFEST_NAME, F.POLICY_MANIFEST_SHA256)]:
        if sha(path).upper() != expected:
            raise ValueError("frozen manifest hash mismatch")
        source_hashes[str(path.relative_to(ROOT))] = sha(path)
    manifest = json.loads((P.HERE / P.MANIFEST_NAME).read_text())
    nets = {}
    for artifact in manifest["policies"]:
        seed = artifact["seed"]
        for kind, label in (("bc", "bc"), ("policy", "ppo")):
            path = P.HERE / artifact[kind + "_file"]
            if sha(path).upper() != artifact[kind + "_sha256"]:
                raise ValueError("checkpoint hash mismatch")
            source_hashes[str(path.relative_to(ROOT))] = sha(path)
            payload = torch.load(path, map_location="cpu", weights_only=True)
            net = MaskedActorCritic(62, 7, (64, 64))
            net.load_state_dict(payload["state_dict"])
            net.eval()
            nets[label, seed] = net
    table, _, facts = F._load_midpoint_table()
    starts, _ = F.map_final_starts(F._load_development_starts()[0])
    identities = F.final_identities()
    historical_path = F.results_path()
    source_hashes[str(historical_path.relative_to(ROOT))] = sha(historical_path)
    historical = json.loads(historical_path.read_text())
    source_hashes[str(F.midpoint_path().relative_to(ROOT))] = sha(F.midpoint_path())
    source_hashes[str(F.metadata_path().relative_to(ROOT))] = sha(F.metadata_path())
    source_hashes[str(P.development_results_path().relative_to(ROOT))] = sha(P.development_results_path())
    arms = [("fixed", None), ("hill", None)]
    arms += [(kind, seed) for kind in ("random_local", "random_global") for seed in RANDOM_SEEDS]
    arms += [(kind, seed) for kind in ("bc", "ppo") for seed in P.TRAIN_SEEDS]
    results, arrays = [], {}
    with gzip.open(out / "episodes.jsonl.gz", "wt", encoding="utf-8") as journal:
        for kind, seed in arms:
            rng = np.random.default_rng(seed) if seed is not None else None
            per_cap = {cap: [] for cap in BUDGETS}
            proposal_s = 0.0
            arm_start = time.perf_counter()
            for identity in identities:
                start_setting = starts[identity[2:]]
                tick = time.perf_counter()
                if kind == "fixed":
                    visits = [start_setting]
                elif kind.startswith("random"):
                    visits = random_trace(start_setting, rng, global_search=kind == "random_global")
                elif kind == "hill":
                    visits = hill_trace(table, identity, starts)
                else:
                    visits = policy_trace(table, identity, starts, nets[kind, seed])
                proposal_s += time.perf_counter() - tick
                for cap in BUDGETS:
                    record = score_trace(table, identity, visits, cap)
                    per_cap[cap].append(record)
                    journal.write(json.dumps(dict(arm=kind, seed=seed, budget=cap, **record)) + "\n")
            if kind == "ppo":
                old = next(r for r in historical["controls"]["entry89_shielded"] if r["seed"] == seed)
                assert_replay(per_cap[8], old["per_identity"])
            for cap, records in per_cap.items():
                results.append(dict(arm=kind, seed=seed, budget=cap, **summary(records),
                                    trajectory_generation_s=proposal_s,
                                    total_arm_s=time.perf_counter() - arm_start))
                arrays.setdefault((kind, cap), []).append(
                    np.array([[r["quality"], float(r["compliant"])] for r in records]))
            journal.flush()
            print(f"{kind} seed={seed}: {summary(per_cap[8])}", flush=True)
    means = {key: np.mean(values, axis=0) for key, values in arrays.items()}
    comparisons = []
    for cap in BUDGETS:
        for comparator in ("fixed", "hill", "random_local", "random_global", "bc"):
            delta = means["ppo", cap] - means[comparator, cap]
            comparisons.append(dict(budget=cap, comparator=comparator,
                quality_delta=float(delta[:, 0].mean()),
                compliance_delta=float(delta[:, 1].mean()),
                quality_ci95=grouped_interval(identities, delta[:, 0]),
                compliance_ci95=grouped_interval(identities, delta[:, 1])))
    result = dict(status="POST_REVIEW_EXPOSED_DIAGNOSTIC", simulations_run=0,
        training_steps=0, n_identities=len(identities), protocol_sha256=protocol_hash,
        source_sha256=source_hashes, source_facts=facts, budgets=list(BUDGETS),
        cost_scope="Cached CPU timings include Python environment/oracle scoring overhead; not SPICE speedups. Prefix curves share eight-visit trajectories; do not sum arm times across budgets.",
        ci_scope="54 request/loss blocks; seed-averaged; conditional on shared circuit/PVT library",
        results=results, comparisons=comparisons, ppo_replay_matches=True,
        wall_s=time.perf_counter()-start_time)
    (out / "summary.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    files = [p for p in out.iterdir() if p.is_file()]
    (out / "sha256.json").write_text(json.dumps({p.name: sha(p) for p in files}, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    run(parser.parse_args().out)

