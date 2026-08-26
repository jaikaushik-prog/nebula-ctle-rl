"""
experiments/exp_sac_propose.py -- **stage 3: does SAC contribute AS RL?
Accept rate against the non-RL 6 of 16.**

WHAT THIS DECIDES
------------------
Entries 34 and 35 measured the LEARNER: `alpha` moved, `log_std` moved, the
policy survived the SPICE transfer that erased PPO. Neither is a claim about
the deliverable. **This file measures the deliverable.** Mentor decision D9
approved the SAC + CMA-ES hybrid *"if the SAC contributes as RL"*, and the only
number that discharges it is accept rate on the same 16 coverage-grid requests
that entry 32 measured the library proposer on:

    entry 32, source=library, k=8:  accepted_at_k [1, 4, 5, 5, 6, 6, 6, 6]
                                    A = 6 of 16 from k = 5 on
                                    512 decks measured / 380 deployed

Pre-registered as `PREDICTIONS.md` entry 36, BEFORE this file existed.

THE FACT REGISTERED IN ADVANCE, BECAUSE IT PREDICTS A NEGATIVE
---------------------------------------------------------------
**115 of the 121 non-feasible library candidates -- 95.0 % -- fail on OUTPUT
SWING compression.** `V6A_SPECS`, the reward SAC was trained on, has no swing
row: the policy optimises two frequency rows, two peaking rows and the Nyquist
boost, and has never been shown swing, noise, power, saturation, area or HD3.

Output swing is not a spec that was left out of the scoring -- it is a
VALIDITY GATE. `link/calibration.py` refuses to score a compressing stage at
all ("the AC/pole-zero model behind every number no longer describes it"), which
is why 116 of 128 library candidates came back *unscorable* rather than
*infeasible* (G107: those are not the same thing). So the policy is measured
here against a bar it was never trained to clear, and entry 36 says so in
advance so that a negative cannot be explained away afterwards.

THE FIVE ARMS, ALL AT k = 5
----------------------------
    0  library      entry 32's proposer, unchanged        the CONTROL
    1  R-analytic   sac_policy_analytic.pt,  random starts
    2  R-finetuned  sac_policy_finetuned.pt, random starts
    3  S-analytic   sac_policy_analytic.pt,  started on the library's top 5
    4  S-finetuned  sac_policy_finetuned.pt, started on the library's top 5

Arms 1-2 ask **can the policy GENERATE**; arms 3-4 ask **can it IMPROVE what
retrieval already found**. Both, because a negative on one alone is
misreadable. Every arm is scored by `exp_hybrid.scan_topk` -- the same screen,
the same `evaluate_at_points`, the same `V6_SPECS`, the same accept rule -- so
there is exactly one definition of "accepted" (CLAUDEwa.md section 8 rule 9).

`5 x 16 x 4 = 320` decks per arm, **1 600 total.** No wall-clock target is
registered: **G126** -- wall clocks on this machine are not comparable across
runs, so cost is stated in decks.

WHAT THE PROPOSAL IS, AND WHAT IT IS NOT
------------------------------------------
A rollout visits `HORIZON` designs after `HORIZON` edits. The proposal is the
**best of those by analytic reward**, not the last one: the analytic model
scores every visited design for zero simulations, so proposing the final `u`
would throw away information the proposer already holds.

**The seeded start is NOT a candidate.** In arms 3-4 the start IS a library
candidate, so allowing the policy to propose it unchanged would make those arms
`>= library` by construction and the measurement would report retrieval's
result as RL's. Excluding it means these arms report what the policy DID.
Nothing is lost: arm 0 scores those same library designs, so "the better of
retrieval and the policy" is recoverable from the two artifacts afterwards
without spending a deck.

    python -m nebula.experiments.exp_sac_propose --run
    python -m nebula.experiments.exp_sac_propose --analyse
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Callable, Optional, Sequence

import numpy as np

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "sac_propose_results.json"
CKPT_ANALYTIC = HERE / "sac_policy_analytic.pt"
CKPT_FINETUNED = HERE / "sac_policy_finetuned.pt"

#: Entry 36's comparison point. Entry 32 measured k=5 as the optimum -- the same
#: `A` as k=8 for 120 fewer decks -- so the RL arms are scored where the
#: baseline is best, not where it is weakest.
K: int = 5

#: Entry 32's measured baseline, quoted so a drift in either is visible.
BASELINE_ACCEPTED_AT_K: tuple[int, ...] = (1, 4, 5, 5, 6)
BASELINE_A: int = 6
BASELINE_DEPLOYED_DECKS: int = 260

SEED: int = 23_0826

#: Entry 36's thresholds. Changing one after the run is the thing
#: `PREDICTIONS.md` exists to prevent.
Q2_MAX_RANDOM_ACCEPT: int = 2
Q3_BASELINE: int = BASELINE_A
Q4_MIN_SWING_FRACTION: float = 0.50
Q5_MAX_CHECKPOINT_GAP: int = 1

ARMS: tuple[tuple[str, str, str], ...] = (
    ("library", "", ""),
    ("sac_random_analytic", "analytic", "random"),
    ("sac_random_finetuned", "finetuned", "random"),
    ("sac_seeded_analytic", "analytic", "seeded"),
    ("sac_seeded_finetuned", "finetuned", "seeded"),
)


# --------------------------------------------------------------------------
# the policy
# --------------------------------------------------------------------------

def load_agent(path: Path):
    """A trained SAC agent from one of entry 35's checkpoints.

    **Raises on a checkpoint with no weights.** `exp_sac_finetune` writes
    `state_dict: None` when the agent has none, which produces a file of the
    right name and roughly the right size holding nothing -- G113's shape. A
    proposer silently backed by an untrained network would report an honest
    accept rate for a policy that never existed.
    """
    import torch

    from nebula.rl.sac import SACAgent, SACConfig

    if not Path(path).exists():
        raise FileNotFoundError(
            f"{path} is missing. It is written by exp_sac_finetune --run and is "
            f"`.gitignore`d (*.pt), so a fresh clone has to re-run that "
            f"experiment before this one can propose anything.")
    ck = torch.load(path, map_location="cpu", weights_only=False)
    sd = ck.get("state_dict")
    if not sd:
        raise ValueError(
            f"{Path(path).name} carries no state_dict -- it is a checkpoint of "
            f"nothing. Re-run exp_sac_finetune rather than proposing from it.")
    agent = SACAgent(int(sd["obs_dim"]), int(sd["act_dim"]), SACConfig(seed=SEED))
    agent.load_state_dict(sd)
    return agent, {"stage": ck.get("stage"), "steps": ck.get("steps"),
                   "spice_calls": ck.get("spice_calls")}


def rollout(agent, env, u0=None) -> tuple[np.ndarray, float, int]:
    """One episode. Returns the BEST design visited, its analytic reward, and
    the step it was found on.

    Deterministic: `actor.act(deterministic=True)` is the distribution mean, so
    two rollouts differ only through their start points. A proposal is scored
    once and there is no reason to add exploration noise to it.
    """
    obs, _ = env.reset() if u0 is None else env.reset(np.asarray(u0, dtype=float))
    best_u, best_r, best_step = None, -np.inf, -1
    for t in range(1, env.horizon + 1):
        a = agent.actor.act(obs, deterministic=True)
        obs, r, term, trunc, info = env.step(a)
        if not info.get("reverted", False) and float(r) > best_r:
            best_u, best_r, best_step = env.u, float(r), t
        if term or trunc:
            break
    return best_u, best_r, best_step


class _Rollouts:
    """`k` rollouts for one request, ranked by analytic reward, best first.

    A `CandidateSource` in `exp_hybrid`'s sense: `(f_peak_hz, peaking_db, k) ->
    [u, ...]`. **Zero SPICE** -- every evaluation inside is the analytic model.
    The caller pays 4 decks per candidate it chooses to score, exactly as it
    does for the library.
    """

    def __init__(self, agent, mode: str, seed: int = SEED,
                 library_fn: Optional[Callable] = None):
        if mode not in ("random", "seeded"):
            raise ValueError(f"mode must be 'random' or 'seeded', got {mode!r}")
        self.agent, self.mode, self.seed = agent, mode, int(seed)
        self._library_fn = library_fn
        self._memo: dict = {}
        #: Per-request diagnostics, keyed by `(f_peak_hz, peaking_db)`.
        self.notes: dict = {}

    # -- the library, fetched once per request ------------------------------
    def _library(self, f_peak_hz: float, peaking_db: float, k: int) -> list:
        """`exp_coverage.library_candidates`, memoised **with copies**.

        G123: `load_pool` re-parses the 74 526-row pool on every call, which is
        6-10 s. Three arms ask for the same rows, so this holds them. Copies are
        handed out because the pool object is shared and G123 records that
        memoising it in place changes aliasing, not just speed -- that hazard is
        declined here rather than introduced.
        """
        if self._library_fn is None:
            from nebula.experiments import exp_coverage as C
            self._library_fn = C.library_candidates
        key = (float(f_peak_hz), float(peaking_db), int(k))
        if key not in self._memo:
            self._memo[key] = [np.asarray(u, dtype=float)
                               for u in self._library_fn(float(f_peak_hz),
                                                         float(peaking_db),
                                                         int(k))]
        return [np.array(u, copy=True) for u in self._memo[key]]

    def __call__(self, f_peak_hz: float, peaking_db: float, k: int) -> list:
        from nebula.rl.analytic_env import AnalyticCtleEnv
        from nebula.rl.spec_dist import SpecTarget

        k = int(k)
        target = SpecTarget(peaking_db=float(peaking_db),
                            f_peak_hz=float(f_peak_hz))
        starts: list = [None] * k
        if self.mode == "seeded":
            lib = self._library(f_peak_hz, peaking_db, k)
            starts = [lib[i] if i < len(lib) else None for i in range(k)]

        scored, declined = [], 0
        for i, u0 in enumerate(starts):
            env = AnalyticCtleEnv([target], seed=self.seed + 1000 * i)
            try:
                u, r, step = rollout(self.agent, env, u0=u0)
            except ValueError:
                # **The analytic model cannot describe this start.** `reset`
                # raises by design rather than inventing a response. That is
                # "the policy could not act here", NOT "the policy acted and
                # failed" (G107), so the untouched library design is proposed
                # and the row is flagged instead of the difference being lost.
                declined += 1
                if u0 is not None:
                    scored.append((float("-inf"), np.asarray(u0, dtype=float),
                                   -1, True))
                continue
            if u is None:
                # Every edit was reverted: the policy proposed nothing usable.
                continue
            scored.append((r, u, step, False))

        scored.sort(key=lambda t: t[0], reverse=True)
        self.notes[(float(f_peak_hz), float(peaking_db))] = {
            "n_rollouts": len(starts), "n_declined": declined,
            "n_proposed": len(scored),
            "analytic_rewards": [None if not np.isfinite(r) else float(r)
                                 for r, _, _, _ in scored],
            "best_steps": [int(s) for _, _, s, _ in scored],
            "declined_flags": [bool(d) for _, _, _, d in scored]}
        return [u for _, u, _, _ in scored]


def register_sources(agents: dict, seed: int = SEED) -> dict:
    """Put the four SAC candidate sources into `exp_hybrid.CANDIDATE_SOURCES`.

    **Registration, not modification** (standing rule 6: wrap, do not replace).
    `library_candidates_k`, `scan_topk`, the screen and the scoring are
    untouched; this only adds names the same dispatch can find, so the RL arms
    and the control run through one code path by construction.
    """
    from nebula.experiments import exp_hybrid as H

    sources = {}
    for name, ckpt, mode in ARMS:
        if not ckpt:
            continue
        sources[name] = _Rollouts(agents[ckpt], mode, seed=seed)
    H.CANDIDATE_SOURCES.update(sources)
    return sources


# --------------------------------------------------------------------------
# the run
# --------------------------------------------------------------------------

def _swing_fraction(scan: dict) -> tuple[int, int]:
    """(candidates naming output swing, non-feasible candidates). Q4's number."""
    tot = sw = 0
    for r in scan.get("requests", []):
        for c in r.get("candidates", []):
            if "error" in c or c.get("feasible"):
                continue
            tot += 1
            if "output swing" in (c.get("reason") or ""):
                sw += 1
    return sw, tot


def _arm_summary(name: str, scan: dict, notes: dict) -> dict:
    ranks = [r.get("accepted_rank") for r in scan["requests"]]
    sw, tot = _swing_fraction(scan)
    declined = sum(int(v["n_declined"]) for v in notes.values()) if notes else 0
    return {
        "arm": name,
        "accepted_at_k": list(scan["accepted_at_k"]),
        "n_accepted": int(scan["n_accepted"]),
        "accepted_ranks": ranks,
        "n_cand_feasible": int(scan["n_cand_feasible"]),
        "n_cand_infeasible": int(scan["n_cand_infeasible"]),
        "n_cand_unscorable": int(scan["n_cand_unscorable"]),
        "n_sims_measured": int(scan["total_sims_measured"]),
        "n_sims_deployed": int(scan["total_sims_deployed"]),
        "swing_named": sw, "non_feasible": tot,
        "swing_fraction": (sw / tot) if tot else None,
        "n_declined": declined,
        "artifact": scan.get("artifact"),
        "wall_clock_s": float(scan["wall_clock_s"]),
    }


def run(k: int = K, seed: int = SEED) -> dict:
    from nebula.experiments import exp_hybrid as H
    from nebula.experiments.runlock import stamp

    t0 = time.time()
    agents, meta = {}, {}
    for ckpt, path in (("analytic", CKPT_ANALYTIC),
                       ("finetuned", CKPT_FINETUNED)):
        agents[ckpt], meta[ckpt] = load_agent(path)
        print(f"loaded {path.name}: {meta[ckpt]}", flush=True)
    sources = register_sources(agents, seed=seed)

    out: dict = {"task": "stage 3: does SAC contribute as RL? accept rate",
                 **stamp(), "k": int(k), "seed": int(seed),
                 "baseline": {"accepted_at_k": list(BASELINE_ACCEPTED_AT_K),
                              "n_accepted": BASELINE_A,
                              "n_sims_deployed": BASELINE_DEPLOYED_DECKS,
                              "source": "entry 32, hybrid_topk_scan.json"},
                 "checkpoints": meta, "arms": []}

    for name, _ckpt, _mode in ARMS:
        print(f"\n=== arm {name}, k={k}, {16 * k * 4} decks ===", flush=True)
        # **Every arm names its own artifact explicitly**, the control
        # included. `topk_scan_path` already refuses to let anything but
        # `("library", DEFAULT_TOPK)` write the baseline, but stage 3 runs the
        # library at k=5 and the first version of that guard keyed on `source`
        # alone -- so the control overwrote entry 32's k=8 artifact with a k=5
        # one that looked entirely legitimate (G128). Two independent guards,
        # because the one that was reasoned about is the one that failed.
        scan = H.scan_topk(source=name, k=int(k),
                           out=HERE / f"topk_scan_{name}_k{int(k)}.json"
                           if name == "library"
                           else HERE / f"topk_scan_{name}.json")
        notes = sources[name].notes if name in sources else {}
        out["arms"].append(_arm_summary(name, scan, notes))
        a = out["arms"][-1]
        print(f"  {name}: A = {a['n_accepted']} of 16, "
              f"accepted_at_k {a['accepted_at_k']}, "
              f"{a['n_sims_measured']} decks measured", flush=True)

    out["wall_s"] = time.time() - t0
    out["verdict"] = _verdict(out)
    RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def _by_arm(d: dict) -> dict:
    return {a["arm"]: a for a in d["arms"]}


def _verdict(d: dict) -> dict:
    """Entry 36's decision rule, applied mechanically."""
    A = _by_arm(d)
    k = int(d["k"])
    lib = A["library"]
    rnd = [A[n] for n, _, m in ARMS if m == "random"]
    seeded = [A[n] for n, _, m in ARMS if m == "seeded"]

    q1 = (lib["accepted_at_k"] == list(BASELINE_ACCEPTED_AT_K))
    q2 = all(a["n_accepted"] <= Q2_MAX_RANDOM_ACCEPT for a in rnd)
    q3 = all(a["n_accepted"] <= Q3_BASELINE for a in seeded)
    sw = [a["swing_fraction"] for a in rnd if a["swing_fraction"] is not None]
    q4 = bool(sw) and all(f >= Q4_MIN_SWING_FRACTION for f in sw)

    def _gap(mode: str) -> Optional[int]:
        arms = [A[n] for n, _, m in ARMS if m == mode]
        if len(arms) != 2:
            return None
        return abs(arms[0]["n_accepted"] - arms[1]["n_accepted"])

    gaps = {m: _gap(m) for m in ("random", "seeded")}
    q5 = all(g is not None and g <= Q5_MAX_CHECKPOINT_GAP for g in gaps.values())
    q6 = (all(a["n_sims_measured"] == 16 * k * 4 for a in d["arms"])
          and lib["n_sims_deployed"] == BASELINE_DEPLOYED_DECKS)

    best_seeded = max(a["n_accepted"] for a in seeded)
    best_random = max(a["n_accepted"] for a in rnd)

    if not q1:
        call = ("Q1 MISSED -- THE CONTROL DID NOT REPRODUCE. The library arm "
                f"returned {lib['accepted_at_k']}, not "
                f"{list(BASELINE_ACCEPTED_AT_K)}. Nothing else in this run is "
                "interpretable: the harness, the screen or the pool moved "
                "under a published result. Find that before reading any RL "
                "number.")
    elif best_seeded > Q3_BASELINE:
        call = (f"Q3 FALSIFIED: a library-seeded arm accepted {best_seeded} of "
                f"16 against the non-RL baseline of {Q3_BASELINE}. THE POLICY "
                "ADDS ACCEPTANCES ON TOP OF RETRIEVAL, on the deliverable's own "
                "metric -- that is what D9's condition asks for. Report it with "
                "the paired per-request ranks, then ask the OWNER about the "
                "~90-minute full hybrid sweep; it stays the owner's call.")
    elif best_random >= 3:
        call = (f"Q3 held, Q2 falsified: a random-start arm accepted "
                f"{best_random} of 16 -- the policy GENERATES without "
                "retrieval but does not beat it. Report as partial. DO NOT "
                "TUNE. The lever is the reward's blindness to output swing, "
                "and changing the reward set is the owner's decision.")
    else:
        call = (f"Q2 and Q3 both held: best seeded {best_seeded}, best random "
                f"{best_random}, against the non-RL {Q3_BASELINE} of 16. SAC "
                "DOES NOT CONTRIBUTE AS A PROPOSER at the bar D9 names. Say so "
                "plainly rather than presenting the hybrid as RL-driven. The "
                "three options -- retrain on a reward containing the spec that "
                "actually rejects proposals; move SAC inside the search and "
                "measure decks-to-feasible; or ship retrieval + CMA-ES with "
                "the RL arm reported as a measured negative -- are ALL owner "
                "decisions.")

    return {"Q1_control_reproduced": bool(q1),
            "Q2_random_weak": bool(q2), "Q3_seeded_not_above_baseline": bool(q3),
            "Q4_swing_dominates": bool(q4),
            "Q5_checkpoint_not_decisive": bool(q5),
            "Q6_accounting": bool(q6),
            "best_seeded": int(best_seeded), "best_random": int(best_random),
            "checkpoint_gaps": gaps, "call": call}


def _report(d: dict) -> None:
    v = d["verdict"]
    print()
    print("=" * 78)
    print(f"SAC AS PROPOSER -- 5 arms at k={d['k']}, "
          f"{sum(a['n_sims_measured'] for a in d['arms'])} decks, "
          f"{d['wall_s'] / 60:.1f} min")
    print(f"  the bar: the non-RL library proposer, A = {BASELINE_A} of 16 "
          f"(entry 32)")
    print("=" * 78)
    print(f"  {'arm':22s} {'A/16':>5s}  {'accepted_at_k':>18s}  "
          f"{'decks':>6s}  {'swing%':>7s}  decl")
    for a in d["arms"]:
        sw = "" if a["swing_fraction"] is None else f"{100*a['swing_fraction']:.0f}%"
        print(f"  {a['arm']:22s} {a['n_accepted']:5d}  "
              f"{str(a['accepted_at_k']):>18s}  {a['n_sims_measured']:6d}  "
              f"{sw:>7s}  {a['n_declined']:4d}")
    print()
    for key in ("Q1_control_reproduced", "Q2_random_weak",
                "Q3_seeded_not_above_baseline", "Q4_swing_dominates",
                "Q5_checkpoint_not_decisive", "Q6_accounting"):
        print(f"  {'HIT ' if v[key] else 'MISS'}  {key}")
    print()
    print(f"  {v['call']}")
    print()
    print("  Accept rate is a PROPOSAL metric on the 4-corner screen. It is")
    print("  not coverage (still 7 of 16 at 45 corners) and not compliance.")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--analyse", action="store_true")
    ap.add_argument("--k", type=int, default=K)
    ap.add_argument("--seed", type=int, default=SEED)
    a = ap.parse_args(argv)
    if a.run:
        _report(run(k=a.k, seed=a.seed))
    elif a.analyse:
        if not RESULTS.exists():
            raise SystemExit(f"{RESULTS.name} missing: run --run first")
        _report(json.loads(RESULTS.read_text(encoding="utf-8")))
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":                                  # pragma: no cover
    raise SystemExit(main())
