"""Entry 87 controls measured before categorical-PPO policy code exists.

All arms use the frozen Entry 86 table.  This module never calls SPICE and
refuses to overwrite its result artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Callable, Optional, Sequence

import numpy as np

from nebula.common.types import all_corners
from nebula.experiments import exp_joint_bank as J
from nebula.experiments.exp_coverage import FREQ_REQUESTS, PEAKING_REQUESTS
from nebula.rl.margin_adapt_env import (
    A_ATTEN_DOWN, A_ATTEN_UP, A_CS_DOWN, A_CS_UP, A_LOCK, A_RS_DOWN,
    A_RS_UP, MAX_TRIALS, MarginAdaptEnv, MarginBankTable, MarginEpisode,
)

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "joint_bank_73_run.jsonl.gz"
RESULTS = HERE / "margin_adapt_controls_results.json"
SOURCE_SHA256 = "1B5F941DF4B34F3C90F6DD050F264D8A77C7BB2E5CE4D9EED8CC29EBD9F9843F"

TRAIN_PROCESSES = ("tt", "ss", "ff")
TEST_PROCESSES = ("sf", "fs")
TRAIN_LOSSES = (3.0, 6.0, 9.0, 12.0)
TEST_LOSSES = (4.5, 7.5, 10.5)
REQUESTS = tuple((float(pk), float(freq)) for pk in PEAKING_REQUESTS
                 for freq in FREQ_REQUESTS)
RANDOM_SEEDS = tuple(range(2026090310, 2026090330))
MOVES = (A_ATTEN_DOWN, A_ATTEN_UP, A_RS_DOWN, A_RS_UP, A_CS_DOWN, A_CS_UP)
OPPOSITE = {
    A_ATTEN_DOWN: A_ATTEN_UP, A_ATTEN_UP: A_ATTEN_DOWN,
    A_RS_DOWN: A_RS_UP, A_RS_UP: A_RS_DOWN,
    A_CS_DOWN: A_CS_UP, A_CS_UP: A_CS_DOWN,
}


def identities(requests: Sequence[tuple] = REQUESTS) -> tuple[list, list]:
    labels = [J._corner_label(c) for c in all_corners()]
    train = [(c, loss, float(pk), float(freq)) for c in labels
             if c.split("/")[0] in TRAIN_PROCESSES
             for loss in TRAIN_LOSSES for pk, freq in requests]
    test = [(c, loss, float(pk), float(freq)) for c in labels
            if c.split("/")[0] in TEST_PROCESSES
            for loss in TEST_LOSSES for pk, freq in requests]
    return train, test


def _request(identity: tuple) -> tuple[float, float]:
    return float(identity[2]), float(identity[3])


def select_start_settings(table: MarginBankTable,
                          train_ids: Sequence[tuple]) -> dict:
    """Best TRAIN-only fixed setting per request; test rows cannot affect it."""
    out = {}
    requests = sorted({_request(i) for i in train_ids})
    for request in requests:
        relevant = [i for i in train_ids if _request(i) == request]
        ranked = []
        for setting in table.settings:
            areas = []
            for corner, loss, pk, freq in relevant:
                if table.compliant(setting, corner, loss, pk, freq):
                    areas.append(table.eye_area(setting, corner, loss))
            ranked.append((len(areas), float(np.mean(areas)) if areas else 0.0,
                           -setting, setting))
        out[request] = int(max(ranked)[3])
    return out


def arm_fixed(env: MarginAdaptEnv) -> MarginEpisode:
    env.step(A_LOCK)
    return env.ep


def random_action_trace(seed: int, identity: tuple) -> list[int]:
    material = f"{int(seed)}|{identity!r}".encode("ascii")
    derived = int.from_bytes(hashlib.sha256(material).digest()[:8], "little")
    rng = np.random.default_rng(derived)
    return [int(x) for x in rng.integers(0, 7, size=MAX_TRIALS)]


def make_arm_random(seed: int) -> Callable:
    def arm(env: MarginAdaptEnv) -> MarginEpisode:
        for action in random_action_trace(seed, env.ep.identity):
            _, _, term, _, _ = env.step(action)
            if term:
                break
        return env.ep
    arm.__name__ = f"random_{seed}"
    return arm


def _area_now(env: MarginAdaptEnv) -> float:
    ok, h, w = env.ep.measurements[-1]
    return h * w if ok else 0.0


def arm_hillclimb(env: MarginAdaptEnv) -> MarginEpisode:
    """Physical local probing: a rejected probe is explicitly moved back."""
    best_area = _area_now(env)
    for direction in MOVES:
        while env.ep.n_trials <= env.max_trials - 2:
            _, _, term, _, _ = env.step(direction)
            if term:
                return env.ep
            area = _area_now(env)
            if area > best_area:
                best_area = area
                continue
            _, _, term, _, _ = env.step(OPPOSITE[direction])
            if term:
                return env.ep
            break
    if env.ep.locked_setting is None:
        env.step(A_LOCK)
    return env.ep


def _episode_record(ep: MarginEpisode) -> dict:
    return {
        "corner": ep.corner, "loss_db": ep.loss_db,
        "target_peaking_db": ep.target_peaking_db,
        "target_f_peak_hz": ep.target_f_peak_hz,
        "locked_setting": ep.locked_setting,
        "compliant": bool(ep.locked_compliant), "quality": ep.quality,
        "n_trials": ep.n_trials, "return": ep.ret,
    }


def _summarise(arm_name: str, episodes: Sequence[dict]) -> dict:
    return {
        "arm": arm_name, "n_episodes": len(episodes),
        "n_compliant": sum(e["compliant"] for e in episodes),
        "compliance_rate": float(np.mean([e["compliant"] for e in episodes])),
        "mean_quality": float(np.mean([e["quality"] for e in episodes])),
        "mean_quality_compliant": float(np.mean(
            [e["quality"] for e in episodes if e["compliant"]]))
            if any(e["compliant"] for e in episodes) else 0.0,
        "mean_trials": float(np.mean([e["n_trials"] for e in episodes])),
        "mean_return": float(np.mean([e["return"] for e in episodes])),
        "n_false_locks": sum(not e["compliant"] for e in episodes),
        "per_identity": list(episodes),
    }


def score_arm(table: MarginBankTable, arm: Callable,
              episode_ids: Sequence[tuple], start_by_request: dict) -> dict:
    records = []
    for corner, loss, pk, freq in episode_ids:
        env = MarginAdaptEnv(table, [(corner, loss, pk, freq)],
                             start_by_request, seed=0)
        env.reset(corner=corner, loss_db=loss, request=(pk, freq))
        records.append(_episode_record(arm(env)))
    return _summarise(getattr(arm, "__name__", str(arm)), records)


def score_random(table: MarginBankTable, episode_ids: Sequence[tuple],
                 start_by_request: dict) -> dict:
    rows = [score_arm(table, make_arm_random(seed), episode_ids,
                      start_by_request) for seed in RANDOM_SEEDS]
    per_identity = []
    for index, identity in enumerate(episode_ids):
        eps = [row["per_identity"][index] for row in rows]
        base = dict(eps[0])
        base.update({
            "compliant": float(np.mean([e["compliant"] for e in eps])),
            "quality": float(np.mean([e["quality"] for e in eps])),
            "n_trials": float(np.mean([e["n_trials"] for e in eps])),
            "return": float(np.mean([e["return"] for e in eps])),
            "locked_setting": None,
        })
        per_identity.append(base)
    summary = _summarise("random_mean", per_identity)
    summary["n_seeds"] = len(rows)
    summary["seeds"] = list(RANDOM_SEEDS)
    summary["per_seed"] = [{k: v for k, v in row.items()
                             if k != "per_identity"} for row in rows]
    return summary


def _direct_ceiling(table: MarginBankTable, episode_ids: Sequence[tuple],
                    oracle: bool) -> dict:
    records = []
    for corner, loss, pk, freq in episode_ids:
        if oracle:
            candidates = table.compliant_settings(corner, loss, pk, freq)
        else:
            candidates = table.settings
        setting = max(candidates, key=lambda s: (
            table.eye_area(s, corner, loss), -s))
        good = table.compliant(setting, corner, loss, pk, freq)
        q = table.quality(setting, corner, loss, pk, freq) if good else 0.0
        trials = 1 if oracle else len(table.settings)
        records.append({
            "corner": corner, "loss_db": loss, "target_peaking_db": pk,
            "target_f_peak_hz": freq, "locked_setting": setting,
            "compliant": good, "quality": q, "n_trials": trials,
            "return": -trials + (20.0 * q if good else -60.0),
        })
    return _summarise("oracle" if oracle else "exhaustive", records)


def primary_comparator(rows: Sequence[dict]) -> dict:
    """Registered safety band, then quality, trials, and arm-name tie break."""
    best_safety = max(float(row["compliance_rate"]) for row in rows)
    eligible = [row for row in rows
                if float(row["compliance_rate"]) >= best_safety - 0.01]
    return sorted(eligible, key=lambda row: (
        -float(row["mean_quality"]), float(row["mean_trials"]),
        str(row["arm"])))[0]


def run() -> dict:
    if RESULTS.exists():
        raise FileExistsError(f"refusing to overwrite {RESULTS.name}")
    decoded = J._decoded_sha256(SOURCE)
    if decoded != SOURCE_SHA256:
        raise ValueError(f"source hash mismatch: {decoded}")
    t0 = time.time()
    table = MarginBankTable.from_path(SOURCE)
    train, test = identities()
    start = select_start_settings(table, train)
    fixed = score_arm(table, arm_fixed, test, start)
    hill = score_arm(table, arm_hillclimb, test, start)
    random = score_random(table, test, start)
    exhaustive = _direct_ceiling(table, test, oracle=False)
    oracle = _direct_ceiling(table, test, oracle=True)
    practical = [fixed, hill, random]
    comparator = primary_comparator(practical)
    out = {
        "task": "entry 87 margin-adaptation controls before policy",
        "source": SOURCE.name, "source_decoded_sha256": decoded,
        "split": {
            "train_processes": list(TRAIN_PROCESSES),
            "train_losses_db": list(TRAIN_LOSSES),
            "test_processes": list(TEST_PROCESSES),
            "test_losses_db": list(TEST_LOSSES),
            "n_train_identities": len(train), "n_test_identities": len(test),
            "overlap": len(set(train).intersection(test)),
        },
        "n_settings": len(table.settings), "n_requests": len(REQUESTS),
        "start_by_request": {f"{pk:g}/{freq:g}": setting
                             for (pk, freq), setting in sorted(start.items())},
        "reward": asdict(MarginAdaptEnv(
            table, [train[0]], start).R),
        "max_trials": MAX_TRIALS,
        "practical_controls": practical,
        "primary_comparator": {k: v for k, v in comparator.items()
                               if k != "per_identity"},
        "primary_comparator_per_identity": comparator["per_identity"],
        "exhaustive": exhaustive, "oracle": oracle,
        "simulations_run": 0, "wall_clock_s": time.time() - t0,
    }
    RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def report(out: dict) -> None:
    print("=" * 78)
    print("ENTRY 87 MARGIN-ADAPTATION CONTROLS - ZERO SPICE")
    print("=" * 78)
    for row in out["practical_controls"]:
        print(f"  {row['arm']:<18} compliance {row['compliance_rate']:.4f}  "
              f"quality {row['mean_quality']:.4f}  "
              f"trials {row['mean_trials']:.3f}")
    for name in ("exhaustive", "oracle"):
        row = out[name]
        print(f"  {row['arm']:<18} compliance {row['compliance_rate']:.4f}  "
              f"quality {row['mean_quality']:.4f}  "
              f"trials {row['mean_trials']:.3f}")
    print(f"  PRIMARY COMPARATOR: {out['primary_comparator']['arm']}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--analyse", action="store_true")
    args = parser.parse_args(argv)
    if args.run:
        out = run()
    else:
        if not RESULTS.exists():
            raise SystemExit(f"missing {RESULTS.name}; run controls first")
        out = json.loads(RESULTS.read_text(encoding="utf-8"))
    report(out)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
