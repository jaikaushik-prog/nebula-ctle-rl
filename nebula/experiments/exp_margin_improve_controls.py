"""Entry 88 TRAIN-only controls before masked-PPO policy code exists.

The policy-untouched FINAL TEST split is defined and hash-pinned here but never
scored by :func:`run`.  All measurements are frozen-table lookups; no SPICE
method is imported or invoked.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Callable, Optional, Sequence

import numpy as np

from nebula.common.types import all_corners
from nebula.experiments import exp_joint_bank as J
from nebula.experiments.exp_coverage import FREQ_REQUESTS, PEAKING_REQUESTS
from nebula.rl.margin_adapt_env import MarginBankTable
from nebula.rl.margin_improve_env import (
    A_ATTEN_DOWN, A_ATTEN_UP, A_CS_DOWN, A_CS_UP, A_LOCK, A_RS_DOWN,
    A_RS_UP, MAX_TRIALS, ImproveEpisode, MarginImproveEnv,
)

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "joint_bank_73_run.jsonl.gz"
RESULTS = HERE / "margin_improve_controls_results.json"
SOURCE_SHA256 = "1B5F941DF4B34F3C90F6DD050F264D8A77C7BB2E5CE4D9EED8CC29EBD9F9843F"

EDGE_PROCESSES = ("tt", "ss", "ff")
CROSS_PROCESSES = ("sf", "fs")
EDGE_LOSSES = (3.0, 6.0, 9.0, 12.0)
MID_LOSSES = (4.5, 7.5, 10.5)
REQUESTS = tuple((float(pk), float(freq)) for pk in PEAKING_REQUESTS
                 for freq in FREQ_REQUESTS)
RANDOM_SEEDS = tuple(range(20260904100, 20260904120))
MOVES = (A_ATTEN_DOWN, A_ATTEN_UP, A_RS_DOWN, A_RS_UP, A_CS_DOWN, A_CS_UP)
OPPOSITE = {
    A_ATTEN_DOWN: A_ATTEN_UP, A_ATTEN_UP: A_ATTEN_DOWN,
    A_RS_DOWN: A_RS_UP, A_RS_UP: A_RS_DOWN,
    A_CS_DOWN: A_CS_UP, A_CS_UP: A_CS_DOWN,
}


def identities(requests: Sequence[tuple] = REQUESTS) -> tuple[list, list]:
    labels = [J._corner_label(c) for c in all_corners()]
    train = []
    final = []
    for corner in labels:
        process = corner.split("/")[0]
        for loss in (*EDGE_LOSSES, *MID_LOSSES):
            destination = train if (
                (process in EDGE_PROCESSES and loss in EDGE_LOSSES) or
                (process in CROSS_PROCESSES and loss in MID_LOSSES)
            ) else final
            destination.extend((corner, float(loss), float(pk), float(freq))
                               for pk, freq in requests)
    return train, final


def identities_sha256(values: Sequence[tuple]) -> str:
    payload = json.dumps(list(values), separators=(",", ":"),
                         ensure_ascii=True).encode("ascii")
    return hashlib.sha256(payload).hexdigest().upper()


def _request(identity: tuple) -> tuple[float, float]:
    return float(identity[2]), float(identity[3])


def select_start_settings(table: MarginBankTable,
                          train_ids: Sequence[tuple]) -> dict:
    """Best fixed compliance count then mean area, using supplied TRAIN only."""
    out = {}
    for request in sorted({_request(i) for i in train_ids}):
        relevant = [i for i in train_ids if _request(i) == request]
        ranked = []
        for setting in table.settings:
            areas = [table.eye_area(setting, corner, loss)
                     for corner, loss, pk, freq in relevant
                     if table.compliant(setting, corner, loss, pk, freq)]
            ranked.append((len(areas), float(np.mean(areas)) if areas else 0.0,
                           -int(setting), int(setting)))
        out[request] = max(ranked)[3]
    return out


def setting_distance(one: int, two: int) -> int:
    a1, b1 = J.split_setting(one)
    a2, b2 = J.split_setting(two)
    r1, c1 = divmod(b1, 8)
    r2, c2 = divmod(b2, 8)
    return abs(a1 - a2) + abs(r1 - r2) + abs(c1 - c2)


def _direct_record(table: MarginBankTable, identity: tuple, start: int,
                   setting: int, trials: int, move_distance: int) -> dict:
    corner, loss, pk, freq = identity
    start_q = table.quality(start, corner, loss, pk, freq)
    good = table.compliant(setting, corner, loss, pk, freq)
    q = table.quality(setting, corner, loss, pk, freq) if good else 0.0
    ret = q - start_q if good else -1.0 - start_q
    return {
        "corner": corner, "loss_db": loss, "target_peaking_db": pk,
        "target_f_peak_hz": freq, "start_setting": int(start),
        "locked_setting": int(setting), "compliant": bool(good),
        "start_quality": float(start_q), "quality": float(q),
        "quality_improvement": float(q - start_q),
        "n_trials": int(trials), "return": float(ret),
        "move_distance": int(move_distance),
    }


def _episode_record(ep: ImproveEpisode) -> dict:
    return {
        "corner": ep.corner, "loss_db": ep.loss_db,
        "target_peaking_db": ep.target_peaking_db,
        "target_f_peak_hz": ep.target_f_peak_hz,
        "start_setting": ep.start_setting,
        "locked_setting": ep.locked_setting,
        "compliant": bool(ep.locked_compliant),
        "start_quality": ep.start_quality, "quality": ep.quality,
        "quality_improvement": ep.quality - ep.start_quality,
        "n_trials": ep.n_trials, "return": ep.ret,
        "move_distance": setting_distance(ep.start_setting,
                                           ep.locked_setting),
    }


def _summarise(name: str, episodes: Sequence[dict]) -> dict:
    compliant_count = float(sum(float(e["compliant"]) for e in episodes))
    return {
        "arm": name, "n_episodes": len(episodes),
        "n_compliant": compliant_count,
        "compliance_rate": float(np.mean([e["compliant"] for e in episodes])),
        "mean_start_quality": float(np.mean(
            [e["start_quality"] for e in episodes])),
        "mean_quality": float(np.mean([e["quality"] for e in episodes])),
        "mean_quality_improvement": float(np.mean(
            [e["quality_improvement"] for e in episodes])),
        "mean_trials": float(np.mean([e["n_trials"] for e in episodes])),
        "mean_return": float(np.mean([e["return"] for e in episodes])),
        "n_false_locks": float(len(episodes) - compliant_count),
        "code_change_rate": float(np.mean([
            e.get("code_changed",
                  e["locked_setting"] != e["start_setting"])
            for e in episodes])),
        "mean_move_distance": float(np.mean(
            [e["move_distance"] for e in episodes])),
        "per_identity": list(episodes),
    }


def score_fixed(table: MarginBankTable, episode_ids: Sequence[tuple],
                start_by_request: dict) -> dict:
    rows = [_direct_record(table, identity, start_by_request[_request(identity)],
                           start_by_request[_request(identity)], 1, 0)
            for identity in episode_ids]
    return _summarise("fixed", rows)


def score_arm(table: MarginBankTable, arm: Callable,
              episode_ids: Sequence[tuple], start_by_request: dict) -> dict:
    rows = []
    for corner, loss, pk, freq in episode_ids:
        env = MarginImproveEnv(table, [(corner, loss, pk, freq)],
                               start_by_request, seed=0)
        env.reset(corner=corner, loss_db=loss, request=(pk, freq))
        rows.append(_episode_record(arm(env)))
    return _summarise(getattr(arm, "__name__", str(arm)), rows)


def random_uniforms(seed: int, identity: tuple) -> tuple[float, ...]:
    material = f"{int(seed)}|{identity!r}".encode("ascii")
    derived = int.from_bytes(hashlib.sha256(material).digest()[:8], "little")
    return tuple(float(x) for x in np.random.default_rng(derived).random(
        MAX_TRIALS))


def make_arm_random(seed: int) -> Callable:
    def arm(env: MarginImproveEnv) -> ImproveEpisode:
        for draw in random_uniforms(seed, env.ep.identity):
            available = np.flatnonzero(env.action_mask())
            action = int(available[min(int(draw * len(available)),
                                       len(available) - 1)])
            _, _, term, _, _ = env.step(action)
            if term:
                break
        return env.ep
    arm.__name__ = f"random_{seed}"
    return arm


def score_random(table: MarginBankTable, episode_ids: Sequence[tuple],
                 start_by_request: dict) -> dict:
    seeds = [score_arm(table, make_arm_random(seed), episode_ids,
                       start_by_request) for seed in RANDOM_SEEDS]
    averaged = []
    for index in range(len(episode_ids)):
        rows = [seed["per_identity"][index] for seed in seeds]
        base = dict(rows[0])
        base.update({
            "compliant": float(np.mean([r["compliant"] for r in rows])),
            "quality": float(np.mean([r["quality"] for r in rows])),
            "quality_improvement": float(np.mean(
                [r["quality_improvement"] for r in rows])),
            "n_trials": float(np.mean([r["n_trials"] for r in rows])),
            "return": float(np.mean([r["return"] for r in rows])),
            "move_distance": float(np.mean(
                [r["move_distance"] for r in rows])),
            "code_changed": float(np.mean([
                r["locked_setting"] != r["start_setting"] for r in rows])),
            "locked_setting": None,
        })
        averaged.append(base)
    summary = _summarise("random_mean", averaged)
    summary["n_seeds"] = len(seeds)
    summary["seeds"] = list(RANDOM_SEEDS)
    summary["per_seed"] = [{k: v for k, v in row.items()
                             if k != "per_identity"} for row in seeds]
    return summary


def _visible_area(env: MarginImproveEnv) -> float:
    ok, h, w = env.ep.measurements[-1]
    return h * w if ok else 0.0


def arm_hillclimb(env: MarginImproveEnv) -> ImproveEpisode:
    """Probe visible-eye directions and return after a non-improving move."""
    best = _visible_area(env)
    for direction in MOVES:
        if env.ep.locked_setting is not None:
            break
        if not env.action_mask()[direction]:
            continue
        _, _, term, _, _ = env.step(direction)
        if term:
            break
        area = _visible_area(env)
        if area > best:
            best = area
            continue
        reverse = OPPOSITE[direction]
        if env.action_mask()[reverse]:
            _, _, term, _, _ = env.step(reverse)
            if term:
                break
    if env.ep.locked_setting is None:
        env.step(A_LOCK)
    return env.ep


def score_exhaustive_visible(table: MarginBankTable,
                             episode_ids: Sequence[tuple],
                             start_by_request: dict) -> dict:
    rows = []
    for identity in episode_ids:
        corner, loss, _, _ = identity
        setting = max(table.settings,
                      key=lambda s: (table.eye_area(s, corner, loss), -s))
        start = start_by_request[_request(identity)]
        rows.append(_direct_record(table, identity, start, setting,
                                   len(table.settings),
                                   setting_distance(start, setting)))
    return _summarise("exhaustive_visible_eye", rows)


def score_global_oracle(table: MarginBankTable, episode_ids: Sequence[tuple],
                        start_by_request: dict) -> dict:
    rows = []
    for identity in episode_ids:
        corner, loss, pk, freq = identity
        start = start_by_request[_request(identity)]
        candidates = table.compliant_settings(corner, loss, pk, freq)
        setting = max(candidates,
                      key=lambda s: (table.quality(s, *identity), -s))
        rows.append(_direct_record(table, identity, start, setting, 1,
                                   setting_distance(start, setting)))
    return _summarise("global_hidden_oracle", rows)


def score_reachable_oracle(table: MarginBankTable,
                           episode_ids: Sequence[tuple],
                           start_by_request: dict, radius: int = 7) -> dict:
    rows = []
    for identity in episode_ids:
        corner, loss, pk, freq = identity
        start = start_by_request[_request(identity)]
        candidates = [s for s in table.compliant_settings(
            corner, loss, pk, freq) if setting_distance(start, s) <= radius]
        setting = (max(candidates,
                       key=lambda s: (table.quality(s, *identity), -s))
                   if candidates else start)
        distance = setting_distance(start, setting)
        rows.append(_direct_record(table, identity, start, setting,
                                   distance + 1, distance))
    return _summarise("reachable_hidden_oracle", rows)


def run() -> dict:
    if RESULTS.exists():
        raise FileExistsError(f"refusing to overwrite {RESULTS.name}")
    decoded = J._decoded_sha256(SOURCE)
    if decoded != SOURCE_SHA256:
        raise ValueError(f"source hash mismatch: {decoded}")
    started = time.time()
    table = MarginBankTable.from_path(SOURCE)
    train, final = identities()
    if (len(train), len(final), len(set(train).intersection(final)),
            len(set(train).union(final))) != (2592, 2448, 0, 5040):
        raise ValueError("Entry 88 split membership failed")
    start = select_start_settings(table, train)
    fixed = score_fixed(table, train, start)
    hill = score_arm(table, arm_hillclimb, train, start)
    random = score_random(table, train, start)
    exhaustive = score_exhaustive_visible(table, train, start)
    oracle = score_global_oracle(table, train, start)
    reachable = score_reachable_oracle(table, train, start)
    out = {
        "task": "entry 88 TRAIN-only controls before policy",
        "source": SOURCE.name, "source_decoded_sha256": decoded,
        "split": {
            "n_train_identities": len(train),
            "n_final_test_identities": len(final),
            "overlap": 0, "union": len(set(train).union(final)),
            "train_identities_sha256": identities_sha256(train),
            "final_test_identities_sha256": identities_sha256(final),
            "final_test_status": "DEFINED_NOT_SCORED",
        },
        "n_settings": len(table.settings), "n_requests": len(REQUESTS),
        "start_by_request": [
            {"target_peaking_db": pk, "target_f_peak_hz": freq,
             "setting": setting}
            for (pk, freq), setting in sorted(start.items())],
        "reward": {
            "move": "q_new - q_previous", "compliant_lock": 0.0,
            "false_lock": "-1 - q_current", "trial_cost": None,
        },
        "max_trials": MAX_TRIALS,
        "random_seeds": list(RANDOM_SEEDS),
        "practical_controls": [fixed, hill, random],
        "primary_comparator": {k: v for k, v in fixed.items()
                               if k != "per_identity"},
        "primary_comparator_per_identity": fixed["per_identity"],
        "exhaustive_visible_eye": exhaustive,
        "global_hidden_oracle": oracle,
        "reachable_hidden_oracle": reachable,
        "simulations_run": 0, "wall_clock_s": time.time() - started,
    }
    RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def report(out: dict) -> None:
    print("=" * 78)
    print("ENTRY 88 TRAIN-ONLY IMPROVEMENT CONTROLS - ZERO SPICE")
    print("=" * 78)
    for row in (*out["practical_controls"],
                out["exhaustive_visible_eye"],
                out["global_hidden_oracle"],
                out["reachable_hidden_oracle"]):
        print(f"  {row['arm']:<24} compliance {row['compliance_rate']:.4f}  "
              f"quality {row['mean_quality']:.4f}  "
              f"delta {row['mean_quality_improvement']:+.4f}  "
              f"trials {row['mean_trials']:.3f}")
    print(f"  FINAL TEST: {out['split']['final_test_status']}")


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
