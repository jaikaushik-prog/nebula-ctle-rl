"""
experiments/exp_sac_swing.py -- **the swing-aware reward, trained and measured
on the same 6-of-16 bar.**

THE CHAIN THIS CLOSES
----------------------
    entry 36   SAC as a proposer: 1 of 16 against the library's 6 of 16, and its
               FAILING designs score higher on its own reward (+6.555) than the
               library designs that PASS (+6.530) -- the reward cannot see what
               rejects designs
    entry 37   that quantity, the measured 1 dB compression point, is
               predictable from the design vector to 4.7 % with NO SPICE
    entry 38   put it in the reward, retrain, and does the accept rate move?

Pre-registered as `PREDICTIONS.md` entry 38; authorised by the owner as
`PROGRESS.md` row 4p, which is standing rule 6's human decision for a
reward-set change.

WHAT CHANGES, AND WHAT DELIBERATELY DOES NOT
----------------------------------------------
Exactly one thing changes against entry 36: **the training reward gains a
predicted-headroom shortfall penalty** (`rl/swing_env.py`, a WRAPPER, so no
surrogate number can reach the screen, `exp_coverage` or the compliance
matrix). Same 50 000 analytic steps, same seed, same `SACConfig`, same 18-dim
observation, same arms, same screen, same `V6_SPECS`, same accept rule.

**No SPICE fine-tune.** Entry 36 measured the fine-tuned checkpoint as the
WORSE proposer -- 0 of 16 against the analytic-only policy's 2 -- so the
analytic-only policy is what gets measured here. That decision was taken from a
measurement and registered before this run.

    python -m nebula.experiments.exp_sac_swing --run
    python -m nebula.experiments.exp_sac_swing --analyse
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from nebula.experiments import exp_sac_propose as PR

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "sac_swing_results.json"
CKPT = HERE / "sac_policy_swing.pt"

ANALYTIC_STEPS: int = 50_000
K: int = PR.K
SEED: int = PR.SEED

#: Entry 38's thresholds.
Q2_MIN_MEDIAN_SWING_MV: float = 700.0
Q3_BASELINE: int = PR.BASELINE_A          # 6 of 16, the non-RL library
Q4_MIN_ACCEPT: int = 3                    # entry 36's best SAC arm was 2
Q5_MAX_SWING_FRACTION: float = 0.50

ARMS: tuple[tuple[str, str], ...] = (
    ("library", ""),
    ("swing_random", "random"),
    ("swing_seeded", "seeded"),
)

RX_LIMIT = re.compile(r"vout_swing_v=([\d.]+) mVpp")
RX_LIMIT_ALT = re.compile(r"exceeds the linear limit ([\d.]+) mVpp")


def _measured_limits_mv(scan: dict) -> list:
    """Every MEASURED `vout_swing_v` among an arm's non-feasible candidates.

    **Measured, not predicted.** Q2 asks whether the policy actually builds more
    headroom, and answering it with the surrogate's own output would be the
    model grading itself.
    """
    out = []
    for r in scan.get("requests", []):
        for c in r.get("candidates", []):
            if c.get("feasible") or "error" in c:
                continue
            m = RX_LIMIT.search(c.get("reason") or "") or \
                RX_LIMIT_ALT.search(c.get("reason") or "")
            if m:
                out.append(float(m.group(1)))
    return out


def train(steps: int = ANALYTIC_STEPS, seed: int = SEED) -> tuple:
    import torch

    from nebula.experiments.exp_swing_surrogate import load_surrogate
    from nebula.rl.analytic_env import AnalyticCtleEnv
    from nebula.rl.sac import SACConfig
    from nebula.rl.sac import train as sac_train
    from nebula.rl.spec_dist import interpolation_split
    from nebula.rl.swing_env import SWING_TARGET_V, SWING_W, SwingAwareEnv

    surrogate, smeta = load_surrogate(seed=seed)
    # **The same split as entries 34-36**, so the training targets are
    # identical and the reward is the only thing that changed.
    split = interpolation_split(n_train=64, n_test=16, seed=seed)
    base = AnalyticCtleEnv(split.train, seed=seed)
    env = SwingAwareEnv(base, surrogate)
    print(f"training {steps:,} analytic steps through the swing-aware reward "
          f"(target {SWING_TARGET_V} V, weight {SWING_W}), ZERO SPICE",
          flush=True)
    t0 = time.time()
    agent, stats = sac_train(env, SACConfig(seed=seed, total_steps=steps))
    gate = stats.gate_report()
    rep = env.report()
    torch.save({"state_dict": agent.state_dict(), "stage": "swing_analytic",
                "steps": steps, "seed": seed, "spice_calls": 0,
                "swing_target_v": SWING_TARGET_V, "swing_weight": SWING_W},
               CKPT)
    print(f"  log_std {gate['log_std_last']:+.4f}  alpha "
          f"{gate['alpha_last']:.4f}  mean shortfall "
          f"{rep['swing_mean_shortfall']:.3f}  ({(time.time()-t0)/60:.1f} min)",
          flush=True)
    return agent, {**gate, "seconds": time.time() - t0,
                   "surrogate": smeta, "env_report": rep,
                   "swing_target_v": SWING_TARGET_V, "swing_weight": SWING_W}


def _env_factory(surrogate):
    """Rollouts are ranked by the reward the policy was TRAINED on (entry 38)."""
    from nebula.rl.analytic_env import AnalyticCtleEnv
    from nebula.rl.swing_env import SwingAwareEnv

    def make(target, seed):
        return SwingAwareEnv(AnalyticCtleEnv([target], seed=seed), surrogate)

    return make


def run(steps: int = ANALYTIC_STEPS, k: int = K, seed: int = SEED) -> dict:
    from nebula.experiments import exp_hybrid as H
    from nebula.experiments.exp_swing_surrogate import load_surrogate
    from nebula.experiments.runlock import stamp

    t0 = time.time()
    agent, tmeta = train(steps=steps, seed=seed)
    surrogate, _ = load_surrogate(seed=seed)

    sources = {}
    for name, mode in ARMS:
        if not mode:
            continue
        sources[name] = PR._Rollouts(agent, mode, seed=seed,
                                     env_factory=_env_factory(surrogate))
    H.CANDIDATE_SOURCES.update(sources)

    out: dict = {"task": "entry 38: does a swing-aware reward move accept rate?",
                 **stamp(), "k": int(k), "seed": int(seed),
                 "analytic_steps": int(steps), "training": tmeta,
                 "baseline": {"n_accepted": PR.BASELINE_A,
                              "accepted_at_k": list(PR.BASELINE_ACCEPTED_AT_K),
                              "source": "entry 32/36, library at k=5"},
                 "blind_policy": {"best_random": 2, "best_seeded": 1,
                                  "source": "entry 36"},
                 "arms": []}

    for name, _mode in ARMS:
        print(f"\n=== arm {name}, k={k}, {16 * k * 4} decks ===", flush=True)
        scan = H.scan_topk(source=name, k=int(k),
                           out=HERE / f"topk_scan_{name}_k{int(k)}.json")
        notes = sources[name].notes if name in sources else {}
        row = PR._arm_summary(name, scan, notes)
        limits = _measured_limits_mv(scan)
        row["measured_limit_mv"] = {
            "n": len(limits),
            "median": float(np.median(limits)) if limits else None,
            "p25": float(np.percentile(limits, 25)) if limits else None,
            "p75": float(np.percentile(limits, 75)) if limits else None}
        out["arms"].append(row)
        print(f"  {name}: A = {row['n_accepted']} of 16, "
              f"accepted_at_k {row['accepted_at_k']}, median measured swing "
              f"{row['measured_limit_mv']['median']} mV", flush=True)

    out["wall_s"] = time.time() - t0
    out["verdict"] = _verdict(out)
    RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def _verdict(d: dict) -> dict:
    """Entry 38's decision rule, applied mechanically."""
    A = {a["arm"]: a for a in d["arms"]}
    k = int(d["k"])
    lib = A["library"]
    swing = [A[n] for n, m in ARMS if m]

    q1 = lib["accepted_at_k"] == list(PR.BASELINE_ACCEPTED_AT_K)
    meds = [a["measured_limit_mv"]["median"] for a in swing
            if a["measured_limit_mv"]["median"] is not None]
    q2 = bool(meds) and float(np.median(meds)) >= Q2_MIN_MEDIAN_SWING_MV
    best = max(a["n_accepted"] for a in swing)
    q3 = best >= Q3_BASELINE + 1
    q4 = best >= Q4_MIN_ACCEPT
    fracs = [a["swing_fraction"] for a in swing
             if a["swing_fraction"] is not None]
    q5 = bool(fracs) and all(f < Q5_MAX_SWING_FRACTION for f in fracs)
    q6 = (all(a["n_sims_measured"] == 16 * k * 4 for a in d["arms"])
          and lib["n_sims_deployed"] == PR.BASELINE_DEPLOYED_DECKS)

    if not q1:
        call = ("Q1 MISSED -- THE CONTROL DID NOT REPRODUCE "
                f"({lib['accepted_at_k']} against "
                f"{list(PR.BASELINE_ACCEPTED_AT_K)}). Nothing else here is "
                "interpretable. Find that before reading any RL number.")
    elif q3:
        call = (f"Q3 HIT: a swing-aware arm accepted {best} of 16 against the "
                f"non-RL library's {Q3_BASELINE}. **RL BEATS RETRIEVAL ON THE "
                "DELIVERABLE'S OWN METRIC AND D9'S CONDITION IS MET.** Report "
                "it with the paired per-request ranks and take it to the "
                "mentor. The ~90-minute full sweep becomes worth asking the "
                "OWNER about; it stays the owner's call.")
    elif q4:
        call = (f"Q3 missed, Q4 HIT: {best} of 16 -- better than its blind "
                f"predecessor (2 random / 1 seeded, entry 36) and still short "
                f"of the library's {Q3_BASELINE}. **The diagnosis was right "
                "and the fix is real but insufficient.** Report against BOTH "
                "baselines. DO NOT re-roll SWING_W (G110): the next lever is "
                "the owner's.")
    elif q2:
        call = ("Q2 hit, Q4 missed: the reward moved the designs in the "
                "intended direction -- they genuinely have more headroom -- and "
                "it did NOT convert into acceptances. That is a clean negative "
                "about the APPROACH, not about the surrogate: the screen "
                "rejects policy-generated designs for reasons that do not "
                "reduce to one quantity. Report it and stop.")
    else:
        call = ("Q2 MISSED: the penalty did not change what the policy builds. "
                "CHECK THE WIRING before concluding anything -- a term that is "
                "computed and discarded is this repo's most common silent "
                "failure -- and if the wiring is sound, report it and stop. "
                "SWING_W is not to be re-rolled without a new entry.")

    return {"Q1_control_reproduced": bool(q1),
            "Q2_headroom_moved": bool(q2),
            "Q3_beats_the_library": bool(q3),
            "Q4_beats_its_blind_predecessor": bool(q4),
            "Q5_failure_mode_shifted": bool(q5),
            "Q6_accounting": bool(q6),
            "best_swing_arm": int(best),
            "median_measured_swing_mv": (float(np.median(meds)) if meds
                                         else None),
            "call": call}


def _report(d: dict) -> None:
    v, t = d["verdict"], d["training"]
    print()
    print("=" * 78)
    print(f"SWING-AWARE SAC -- {d['analytic_steps']:,} analytic steps, "
          f"{sum(a['n_sims_measured'] for a in d['arms'])} decks, "
          f"{d['wall_s']/60:.1f} min")
    print(f"  the bar: the non-RL library, A = {PR.BASELINE_A} of 16. Its own "
          f"blind predecessor: 2 of 16 (entry 36)")
    print(f"  reward: V6A - {t['swing_weight']} * shortfall against "
          f"{t['swing_target_v']} V; mean shortfall in training "
          f"{t['env_report']['swing_mean_shortfall']:.3f}")
    print("=" * 78)
    print(f"  {'arm':16s} {'A/16':>5s}  {'accepted_at_k':>18s}  "
          f"{'decks':>6s}  {'swing%':>7s}  {'med swing mV':>12s}")
    for a in d["arms"]:
        sw = "" if a["swing_fraction"] is None else f"{100*a['swing_fraction']:.0f}%"
        med = a["measured_limit_mv"]["median"]
        print(f"  {a['arm']:16s} {a['n_accepted']:5d}  "
              f"{str(a['accepted_at_k']):>18s}  {a['n_sims_measured']:6d}  "
              f"{sw:>7s}  {('n/a' if med is None else f'{med:.0f}'):>12s}")
    print()
    for key in ("Q1_control_reproduced", "Q2_headroom_moved",
                "Q3_beats_the_library", "Q4_beats_its_blind_predecessor",
                "Q5_failure_mode_shifted", "Q6_accounting"):
        print(f"  {'HIT ' if v[key] else 'MISS'}  {key}")
    print()
    print(f"  {v['call']}")
    print()
    print("  A proposer metric on the 4-corner screen at k=5. NOT coverage")
    print("  (still 7 of 16) and NOT compliance. No surrogate number is scored.")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--analyse", action="store_true")
    ap.add_argument("--steps", type=int, default=ANALYTIC_STEPS)
    ap.add_argument("--k", type=int, default=K)
    ap.add_argument("--seed", type=int, default=SEED)
    a = ap.parse_args(argv)
    if a.run:
        _report(run(steps=a.steps, k=a.k, seed=a.seed))
    elif a.analyse:
        if not RESULTS.exists():
            raise SystemExit(f"{RESULTS.name} missing: run --run first")
        _report(json.loads(RESULTS.read_text(encoding="utf-8")))
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":                                  # pragma: no cover
    raise SystemExit(main())
