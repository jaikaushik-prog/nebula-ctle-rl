"""experiments/exp_rl_diagnose.py -- entry 42. **Why does the RL policy produce
nothing? Deployment, or the shape of the reward?**

Entry 41 scored 0 of 5. Its policy is measurable (2.64 of 4 screen points
scorable, against the library's 0.30) and never right: **all 52 of its
fully-scorable proposals peak at 19.95 GHz**, a median 3.377 octaves from the
request against a 0.30-octave tolerance. This file separates two explanations
that predict that same observation.

ARM A -- IS IT DEPLOYMENT? (the owner's hypothesis 1)
------------------------------------------------------
`ScreenEnv.step` reverts an unscorable edit and returns the PRIOR observation.
Entry 41's Q3 had **3 of 8 requests with 16 of 16 moves reverted**. Four
rollout policies on the same 8 requests, the same checkpoint, the same horizon:

    A1  det        deterministic + revert     reproduces entry 41's Q3 (control)
    A2  sto        stochastic + revert        the remedy hypothesis 1 proposes
    A3  best4      4 independent stochastic rollouts, best kept
    A4  norevert   deterministic, the edit KEPT even when unscorable

**Every one of these is a change to DEPLOYMENT ONLY.** No reward, tolerance,
screen point or spec set is touched, and `ScreenEnv` is SUBCLASSED rather than
edited -- `rl/corner_env.py` is the precedent and `CONTINUE_HERE.md` sec 9
rule 7 is the rule ("wrap, do not replace").

ARM B -- OR IS IT THE REWARD'S GEOMETRY?
------------------------------------------
Six requests have BOTH a library design that the screen accepts (reward +14.06
to +14.35) and a `screen_random` proposal from entry 41's policy (reward -2.08
to -3.53, all at 19.95 GHz). Arm B walks the straight line in `u` between them,
scoring 9 equally spaced interior points on the SAME
`evaluate_at_points(EDGE4_MANDATED, V6_SPECS)` the acceptance is decided by.

The question is what kind of barrier sits between the policy's optimum and an
accepted design:

* a **reward plateau** -- both frequency rows clipped at 1.0 shortfall, so the
  reward is flat and a gradient method has nothing to follow, but the path is
  walkable; or
* an **unscorability moat** -- the interior points cannot be measured at all,
  so under `ScreenEnv`'s revert the path is not merely uninformative but
  **impassable**, since every step into it is undone.

They need different fixes, so they are measured rather than assumed (G107 is
the same distinction one level down).

WHAT THIS FILE MAY NOT DO
--------------------------
No tolerance, screen point, spec set or reward is modified (G111). "Feasible"
means `evaluate_at_points` said so; "compliant" means
`exp_g4_verify.verify_full` passed all 45 mandated corners -- the same verifier
every coverage number in this project used (rule 9). Artifacts are written to
names no other experiment owns (G113/G128).

Pre-registered as `PREDICTIONS.md` entry 42, with eight disclosures, before this
module existed.

    python -m nebula.experiments.exp_rl_diagnose --run
    python -m nebula.experiments.exp_rl_diagnose --arm b        # 216 decks only
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import time
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

HERE = Path(__file__).resolve().parent
CKPT = HERE / "sac_policy_screen.pt"
RESULTS = HERE / "rl_diagnose_results.json"

#: The two committed scans arm B reads its endpoints from. Both are inputs;
#: neither is written.
LIB_SCAN = HERE / "topk_scan_library_k5.json"
SAC_SCAN = HERE / "topk_scan_screen_random.json"

HORIZON: int = 16
SEED: int = 23_0826

#: Arm A's modes. `n_starts` is how many independent episodes the arm runs per
#: request; the arm's proposal is the best screen reward over all of them.
ARMS_A: tuple[tuple[str, str, bool, int], ...] = (
    # (name,       action mode,   revert, n_starts)
    ("det",        "det",         True,   1),
    ("sto",        "sto",         True,   1),
    ("best4",      "sto",         True,   4),
    ("norevert",   "det",         False,  1),
)

#: Arm B's interior sampling. 9 points, none of them an endpoint -- the
#: endpoints are already measured in the two committed scans and re-measuring
#: them would spend 48 decks to reproduce numbers that are on disk.
N_INTERIOR: int = 9

#: Q4's threshold, from entry 42 and NOT to be edited after the run (G110).
Q4_INFORMATIVE_DELTA: float = 0.05
Q4_MEDIAN_MAX: float = 0.5

#: Q1's band on A2's revert count, from entry 42. A1's entry-41 value is 48.
Q1_REVERTS_LO: int = 36
Q1_REVERTS_HI: int = 60

#: Q3's threshold, from entry 42.
Q3_MEDIAN_F_PEAK_HZ: float = 4.0e9

#: Entry 41's per-request revert counts, for Q5. Order is `exp_sac_q3.HARD`.
ENTRY41_Q3_REVERTS: tuple[int, ...] = (16, 0, 16, 0, 16, 0, 0, 0)
ENTRY41_Q3_DECKS: int = 636


# --------------------------------------------------------------------------
# the no-revert environment -- a SUBCLASS, so `ScreenEnv` is untouched
# --------------------------------------------------------------------------

def make_env(target, seed: int, revert: bool, horizon: int = HORIZON):
    """A `ScreenEnv` for one target, optionally without the revert rule.

    Split out as a plain function so the tests can build both variants without
    importing the experiment's expensive entry point (G129).
    """
    if revert:
        return ScreenEnv([target], seed=seed, horizon=horizon)
    return _NoRevertScreenEnv([target], seed=seed, horizon=horizon)


def _no_revert_step(env, action):
    """`ScreenEnv.step` with the revert removed. **Pure w.r.t. the class.**

    Everything else is identical to the parent, deliberately: the observation
    after an unmeasurable edit is still the last TRUE one (there is no other
    honest choice -- the measurement channels of an unscorable evaluation are
    filled-in centres), the reward is still the graded invalid floor, and the
    episode still does not terminate early (G100). **The single difference is
    that `u` keeps the edit**, so the walk can leave the region it started in.

    Kept as a module-level function, not only a method, so a test can drive it
    against a fake env with no SPICE anywhere.
    """
    from nebula.rl.contract import N_ACTIONS

    a = np.asarray(action, dtype=float).ravel()
    if a.shape[0] != N_ACTIONS:
        raise ValueError(f"expected {N_ACTIONS} action dims, got {a.shape[0]}")
    if not np.all(np.isfinite(a)):
        raise ValueError("action contains nan/inf - a policy blow-up")

    env._u = np.clip(env._u + np.clip(a, -1.0, 1.0) * env.max_step, 0.0, 1.0)
    env._step += 1
    ev = env._evaluate(env._u)
    trunc = env._step >= env.horizon

    if not ev.ok:
        env.n_kept_unscorable += 1
        assert env._last is not None
        return (env._obs(env._last), float(ev.reward), False, trunc,
                {"is_analytic": False, "reverted": False,
                 "kept_unscorable": True, "reason": ev.reason,
                 "n_decks": int(ev.n_sims)})

    env._last = ev
    return (env._obs(ev), float(ev.reward), False, trunc,
            {"is_analytic": False, "reverted": False, "kept_unscorable": False,
             "feasible": bool(ev.feasible), "worst_spec": ev.worst_spec,
             "f_peak_hz": ev.f_peak_hz, "peaking_db": ev.peaking_db,
             "n_decks": int(ev.n_sims)})


from nebula.rl.screen_env import ScreenEnv                   # noqa: E402


class _NoRevertScreenEnv(ScreenEnv):
    """`ScreenEnv` that KEEPS an unmeasurable edit. Arm A4."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.n_kept_unscorable = 0

    def step(self, action):
        return _no_revert_step(self, action)


# --------------------------------------------------------------------------
# arm A -- deployment
# --------------------------------------------------------------------------

def rollout_once(agent, target, seed: int, mode: str, revert: bool,
                 horizon: int = HORIZON) -> dict:
    """One episode. Records every design visited and how the screen read it.

    `mode` is `"det"` (the distribution mean, entry 41's deployment) or
    `"sto"` (a sample from the tanh-squashed Gaussian).
    """
    if mode not in ("det", "sto"):
        raise ValueError(f"mode must be 'det' or 'sto', got {mode!r}")
    env = make_env(target, seed, revert, horizon)
    obs, info = env.reset()

    last = getattr(env, "_last", None)
    visited = [{"step": 0, "u": env.u.tolist(),
                "feasible": bool(info.get("feasible", False)),
                "reward": (None if last is None else float(last.reward)),
                "scorable": bool(getattr(last, "ok", False)),
                "f_peak_hz": getattr(last, "f_peak_hz", None),
                "peaking_db": getattr(last, "peaking_db", None),
                "reverted": False}]

    for t in range(1, horizon + 1):
        a = agent.actor.act(obs, deterministic=(mode == "det"))
        obs, reward, _term, trunc, step_info = env.step(a)
        last = getattr(env, "_last", None)
        scorable = not (step_info.get("reverted") or
                        step_info.get("kept_unscorable"))
        visited.append({
            "step": t, "u": env.u.tolist(),
            "feasible": bool(step_info.get("feasible", False)),
            "reward": float(reward), "scorable": bool(scorable),
            "f_peak_hz": (getattr(last, "f_peak_hz", None) if scorable else None),
            "peaking_db": (getattr(last, "peaking_db", None) if scorable else None),
            "reverted": bool(step_info.get("reverted", False)),
            "kept_unscorable": bool(step_info.get("kept_unscorable", False)),
            "worst_spec": step_info.get("worst_spec"),
            "reason": step_info.get("reason")})
        if trunc:
            break

    rep = env.report()
    return {"visited": visited, "n_decks": int(rep.get("n_decks", 0)),
            "n_reverted": int(rep.get("n_reverted", 0)),
            "n_kept_unscorable": int(getattr(env, "n_kept_unscorable", 0)),
            "warm_start_scorable": bool(visited[0]["scorable"]),
            "warm_start_feasible": bool(visited[0]["feasible"])}


def delivered_f_peak_hz(visited: Sequence[dict]) -> Optional[float]:
    """**Q3's "delivered" quantity, defined here before the run.**

    The `f_peak` of the LAST evaluation in the episode the screen could
    measure. An episode with no scorable evaluation contributes nothing to the
    median and is counted separately -- a design that could not be measured has
    no peak frequency, and defaulting one would be inventing a number.
    """
    for v in reversed(list(visited)):
        if v.get("scorable") and v.get("f_peak_hz"):
            return float(v["f_peak_hz"])
    return None


def best_feasible(visited: Sequence[dict]) -> Optional[dict]:
    """The highest-reward SCREEN-FEASIBLE design visited, or None."""
    feas = [v for v in visited if v.get("feasible") and v.get("reward") is not None]
    return max(feas, key=lambda v: float(v["reward"])) if feas else None


def run_arm_a(agent, reqs: Sequence[dict], name: str, mode: str, revert: bool,
              n_starts: int, seed: int = SEED,
              horizon: int = HORIZON, verify: bool = True) -> dict:
    from nebula.rl.spec_dist import SpecTarget

    out: dict = {"arm": name, "mode": mode, "revert": bool(revert),
                 "n_starts": int(n_starts), "requests": []}
    for req in reqs:
        target = SpecTarget(peaking_db=req["peaking_db"],
                            f_peak_hz=req["f_peak_hz"])
        eps, decks, rev, kept = [], 0, 0, 0
        for j in range(n_starts):
            r = rollout_once(agent, target, seed + 1000 * j, mode, revert,
                             horizon)
            eps.append(r)
            decks += r["n_decks"]; rev += r["n_reverted"]
            kept += r["n_kept_unscorable"]
        visited = [v for r in eps for v in r["visited"]]
        best = best_feasible(visited)
        # "delivered" is per EPISODE; with several starts, take the last
        # scorable reading of the best-scoring episode, else of the first.
        pick = max(eps, key=lambda r: max(
            (v["reward"] for v in r["visited"] if v["reward"] is not None),
            default=-1e18))
        rec = {k: req[k] for k in ("index", "peaking_db", "f_peak_hz",
                                   "cma_es_pvt45")}
        rec.update({
            "n_decks": decks, "n_reverted": rev, "n_kept_unscorable": kept,
            "n_scorable_evals": sum(1 for v in visited if v["scorable"]),
            "n_evals": len(visited),
            "n_feasible": sum(1 for v in visited if v["feasible"]),
            "warm_starts_scorable": sum(1 for r in eps
                                        if r["warm_start_scorable"]),
            "delivered_f_peak_hz": delivered_f_peak_hz(pick["visited"]),
            "best_reward_seen": max(
                (v["reward"] for v in visited if v["reward"] is not None),
                default=None)})
        if best is not None and verify:
            from nebula.experiments.exp_sac_q3 import verify45
            rec["u"] = best["u"]
            rec["verified"] = verify45(best["u"], req)
            print(f"     45-corner: {rec['verified']['n_pvt45_pass']}/"
                  f"{rec['verified']['n_pvt45_total']}  "
                  f"compliant={rec['verified']['compliant']}", flush=True)
        else:
            rec["verified"] = None
        f = rec["delivered_f_peak_hz"]
        print(f"  req {rec['index']:2d} {rec['peaking_db']:5.1f} dB @ "
              f"{rec['f_peak_hz']/1e9:.3f} GHz: "
              f"{rec['n_feasible']} feasible / {rec['n_scorable_evals']} "
              f"scorable of {rec['n_evals']}, {rec['n_reverted']} reverted, "
              f"delivered {('%.2f GHz' % (f/1e9)) if f else '--'}, "
              f"{rec['n_decks']} decks", flush=True)
        out["requests"].append(rec)

    fs = [r["delivered_f_peak_hz"] for r in out["requests"]
          if r["delivered_f_peak_hz"]]
    out.update({
        "total_decks": sum(r["n_decks"] for r in out["requests"]),
        "total_reverted": sum(r["n_reverted"] for r in out["requests"]),
        "total_kept_unscorable": sum(r["n_kept_unscorable"]
                                     for r in out["requests"]),
        "n_feasible_designs": sum(r["n_feasible"] for r in out["requests"]),
        "n_requests_with_feasible": sum(1 for r in out["requests"]
                                        if r["n_feasible"]),
        "n_delivered": len(fs),
        "median_delivered_f_peak_hz": (st.median(fs) if fs else None),
        "n_compliant": sum(1 for r in out["requests"]
                           if r.get("verified") and r["verified"]["compliant"]),
        "compliant_indices": [r["index"] for r in out["requests"]
                              if r.get("verified") and r["verified"]["compliant"]],
        "reverts_per_request": [r["n_reverted"] for r in out["requests"]]})
    return out


# --------------------------------------------------------------------------
# arm B -- the barrier
# --------------------------------------------------------------------------

def transect_endpoints(lib_scan: dict, sac_scan: dict) -> list[dict]:
    """(request, library-feasible `u`, best SAC `u`) for every request that has
    both. **Pure -- reads two dicts, runs nothing.**

    Raises rather than returning a short list when a request the library solved
    has no SAC counterpart: a silently shorter transect set would report a
    weaker barrier than was measured, which is G115's shape.
    """
    sac_by_index = {r["index"]: r for r in sac_scan.get("requests", [])}
    out = []
    for r in lib_scan.get("requests", []):
        feas = [c for c in r.get("candidates", []) if c.get("feasible")]
        if not feas:
            continue
        lib = max(feas, key=lambda c: float(c["reward"]))
        sr = sac_by_index.get(r["index"])
        if sr is None:
            raise ValueError(
                f"request {r['index']} is feasible in the library scan and "
                f"absent from the SAC scan -- the two artifacts describe "
                f"different request sets and the transects would not be "
                f"comparable")
        cands = [c for c in sr.get("candidates", [])
                 if "error" not in c and c.get("reward") is not None]
        if not cands:
            raise ValueError(f"request {r['index']} has no scored SAC candidate")
        sac = max(cands, key=lambda c: float(c["reward"]))
        out.append({"index": r["index"], "peaking_db": r["peaking_db"],
                    "f_peak_hz": r["f_peak_hz"],
                    "u_sac": [float(x) for x in sac["u"]],
                    "u_lib": [float(x) for x in lib["u"]],
                    "reward_sac": float(sac["reward"]),
                    "reward_lib": float(lib["reward"]),
                    "f_peak_sac_hz": sac.get("f_peak_hz_got"),
                    "f_peak_lib_hz": lib.get("f_peak_hz_got")})
    if not out:
        raise ValueError("no request has both a feasible library design and a "
                         "SAC candidate; there is nothing to transect")
    return out


def informative_fraction(rewards: Sequence[Optional[float]],
                         delta: float = Q4_INFORMATIVE_DELTA) -> Optional[float]:
    """**Q4's statistic, defined here before the run.**

    The share of consecutive intervals along a transect whose reward moves by
    more than `delta`. An interval with an unscorable endpoint is counted as
    NOT informative even though the -16 floor is numerically far away: a
    gradient method cannot use it, because under `ScreenEnv`'s revert that step
    is undone and the state does not move. Recording it as informative would
    credit the reward with a signal the dynamics throw away.
    """
    r = list(rewards)
    if len(r) < 2:
        return None
    n = 0
    for a, b in zip(r[:-1], r[1:]):
        if a is None or b is None:
            continue
        if abs(float(b) - float(a)) > delta:
            n += 1
    return n / (len(r) - 1)


def run_arm_b(pairs: Sequence[dict], n_interior: int = N_INTERIOR) -> dict:
    from nebula.experiments.adaptive_screen import EDGE4_MANDATED, evaluate_at_points
    import nebula.rl.reward_v1 as R

    ts = np.linspace(0.0, 1.0, n_interior + 2)[1:-1]
    out: dict = {"n_interior": int(n_interior),
                 "delta": Q4_INFORMATIVE_DELTA, "transects": []}
    for p in pairs:
        us, ul = np.asarray(p["u_sac"]), np.asarray(p["u_lib"])
        pts = []
        for t in ts:
            u = (1.0 - t) * us + t * ul
            ev = evaluate_at_points(u, EDGE4_MANDATED,
                                    target_f_peak_hz=float(p["f_peak_hz"]),
                                    target_peaking_db=float(p["peaking_db"]),
                                    specs=R.V6_SPECS)
            pts.append({"t": float(t), "u": [float(x) for x in u],
                        "ok": bool(ev.ok), "reward": float(ev.reward),
                        "feasible": bool(ev.feasible),
                        "n_scorable": int(ev.n_scorable),
                        "worst_spec": ev.worst_spec,
                        "f_peak_hz": ev.f_peak_hz,
                        "peaking_db": ev.peaking_db,
                        "n_sims": int(ev.n_sims),
                        "reason": ev.reason})
        rewards = [q["reward"] for q in pts]
        rec = dict(p)
        rec.update({
            "points": pts,
            "n_sims": sum(q["n_sims"] for q in pts),
            "n_unscorable": sum(1 for q in pts if not q["ok"]),
            "n_feasible": sum(1 for q in pts if q["feasible"]),
            "informative_fraction": informative_fraction(rewards),
            "u_distance": float(np.linalg.norm(ul - us)),
            "reward_min": min(rewards), "reward_max": max(rewards)})
        print(f"  req {rec['index']:2d}: |u| gap {rec['u_distance']:.3f}, "
              f"{rec['n_unscorable']}/{n_interior} interior points unscorable, "
              f"informative fraction {rec['informative_fraction']:.3f}, "
              f"reward {rec['reward_min']:.3f} .. {rec['reward_max']:.3f}",
              flush=True)
        out["transects"].append(rec)

    fr = [t["informative_fraction"] for t in out["transects"]
          if t["informative_fraction"] is not None]
    out.update({
        "total_decks": sum(t["n_sims"] for t in out["transects"]),
        "median_informative_fraction": (st.median(fr) if fr else None),
        "total_interior_points": sum(len(t["points"]) for t in out["transects"]),
        "total_unscorable": sum(t["n_unscorable"] for t in out["transects"]),
        "total_feasible": sum(t["n_feasible"] for t in out["transects"])})
    return out


# --------------------------------------------------------------------------
# scoring -- the pre-registered thresholds, applied mechanically
# --------------------------------------------------------------------------

def score(d: dict) -> dict:
    """Entry 42's five predictions, scored from the artifact. No thresholds
    are read from anywhere but this module's constants (G110)."""
    a = {arm["arm"]: arm for arm in d.get("arms_a", [])}
    b = d.get("arm_b") or {}
    q: dict = {}

    det, sto = a.get("det"), a.get("sto")
    if sto is not None:
        q["Q1"] = {
            "n_feasible_designs": sto["n_feasible_designs"],
            "total_reverted": sto["total_reverted"],
            "band": [Q1_REVERTS_LO, Q1_REVERTS_HI],
            "pass": bool(sto["n_feasible_designs"] == 0
                         and Q1_REVERTS_LO <= sto["total_reverted"]
                         <= Q1_REVERTS_HI)}
    b4 = a.get("best4")
    if b4 is not None:
        q["Q2"] = {"n_compliant": b4["n_compliant"],
                   "compliant_indices": b4["compliant_indices"],
                   "pass": bool(b4["n_compliant"] == 0),
                   "secondary_feasible_design": bool(b4["n_feasible_designs"]),
                   "secondary_pass": bool(b4["n_feasible_designs"] > 0)}
    nr = a.get("norevert")
    if nr is not None:
        med = nr["median_delivered_f_peak_hz"]
        q["Q3"] = {"median_delivered_f_peak_hz": med,
                   "n_delivered": nr["n_delivered"],
                   "threshold_hz": Q3_MEDIAN_F_PEAK_HZ,
                   "pass": bool(med is not None and med > Q3_MEDIAN_F_PEAK_HZ)}
    if b:
        med = b.get("median_informative_fraction")
        q["Q4"] = {"median_informative_fraction": med,
                   "threshold": Q4_MEDIAN_MAX,
                   "unscorable_interior_points": b.get("total_unscorable"),
                   "total_interior_points": b.get("total_interior_points"),
                   "pass": bool(med is not None and med <= Q4_MEDIAN_MAX)}
    if det is not None:
        same = (tuple(det["reverts_per_request"]) == ENTRY41_Q3_REVERTS)
        q["Q5"] = {"reverts_per_request": det["reverts_per_request"],
                   "entry41": list(ENTRY41_Q3_REVERTS),
                   "n_compliant": det["n_compliant"],
                   "total_decks": det["total_decks"],
                   "entry41_decks": ENTRY41_Q3_DECKS,
                   "pass": bool(same and det["n_compliant"] == 0
                                and det["total_decks"] == ENTRY41_Q3_DECKS)}
    q["n_pass"] = sum(1 for k, v in q.items()
                      if k.startswith("Q") and v.get("pass"))
    q["n_scored"] = sum(1 for k in q if k.startswith("Q"))
    return q


# --------------------------------------------------------------------------
# the run
# --------------------------------------------------------------------------

def run(ckpt: Path = CKPT, seed: int = SEED, horizon: int = HORIZON,
        arms: str = "ab") -> dict:
    from nebula.experiments.exp_sac_propose import load_agent
    from nebula.experiments.exp_sac_q3 import hard_requests
    from nebula.experiments.runlock import hold, stamp

    t0 = time.time()
    out: dict = {"task": "entry 42: deployment or reward geometry?",
                 **stamp(), "seed": seed, "horizon": horizon,
                 "arms_a": [], "arm_b": None}

    # **Arm B runs FIRST, and the order is G112.** Arm A costs ~4 500 decks
    # and arm B ~216; a name error in the cheap phase must not be discovered
    # after the expensive one has been paid for. Arm B also exercises the
    # artifact write, the scorer and the report on real data.
    with hold("rl_diagnose", meta={"arms": arms}):
        if "b" in arms:
            print("\n=== ARM B: transects ===", flush=True)
            pairs = transect_endpoints(
                json.loads(LIB_SCAN.read_text(encoding="utf-8")),
                json.loads(SAC_SCAN.read_text(encoding="utf-8")))
            out["arm_b"] = run_arm_b(pairs)
            out["total_decks"] = out["arm_b"]["total_decks"]
            out["score"] = score(out)
            RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
            print(f"  wrote {RESULTS.name} (arm B checkpoint)", flush=True)
        if "a" in arms:
            reqs = hard_requests()
            agent, meta = load_agent(Path(ckpt))
            out["checkpoint"] = {"path": Path(ckpt).name, **meta}
            print(f"loaded {Path(ckpt).name}: {meta}", flush=True)
            for name, mode, revert, n_starts in ARMS_A:
                print(f"\n=== ARM A/{name}: mode={mode} revert={revert} "
                      f"n_starts={n_starts} ===", flush=True)
                out["arms_a"].append(
                    run_arm_a(agent, reqs, name, mode, revert, n_starts,
                              seed=seed, horizon=horizon))
                arm = out["arms_a"][-1]
                print(f"  -> {arm['n_feasible_designs']} screen-feasible "
                      f"designs, {arm['n_compliant']} compliant at 45 corners, "
                      f"{arm['total_reverted']} reverts, "
                      f"{arm['total_decks']} decks", flush=True)
                # Checkpoint after EVERY arm: an hour of decks must not be
                # lost to a defect in the arm that follows (G112 lever 3).
                out["total_decks"] = (sum(x["total_decks"] for x in out["arms_a"])
                                      + (out["arm_b"]["total_decks"]
                                         if out["arm_b"] else 0))
                out["score"] = score(out)
                RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")

        out["total_decks"] = (sum(a["total_decks"] for a in out["arms_a"])
                              + (out["arm_b"]["total_decks"]
                                 if out["arm_b"] else 0))
        out["score"] = score(out)
        out["wall_s"] = time.time() - t0
        RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print(f"\nwrote {RESULTS.name}", flush=True)
    return out


def _report(d: dict) -> None:
    print()
    print("ENTRY 42 -- deployment, or the shape of the reward?")
    if d.get("arms_a"):
        print()
        print(f"  {'arm':10} {'feas':>5} {'compl':>6} {'revert':>7} "
              f"{'kept':>5} {'scorable':>9} {'med f_peak':>11} {'decks':>7}")
        for a in d["arms_a"]:
            m = a["median_delivered_f_peak_hz"]
            sc = sum(r["n_scorable_evals"] for r in a["requests"])
            ev = sum(r["n_evals"] for r in a["requests"])
            print(f"  {a['arm']:10} {a['n_feasible_designs']:5d} "
                  f"{a['n_compliant']:6d} {a['total_reverted']:7d} "
                  f"{a['total_kept_unscorable']:5d} {sc:4d}/{ev:<4d} "
                  f"{('%.2f GHz' % (m/1e9)) if m else '--':>11} "
                  f"{a['total_decks']:7d}")
    if d.get("arm_b"):
        b = d["arm_b"]
        print()
        print(f"  ARM B: {len(b['transects'])} transects x {b['n_interior']} "
              f"interior points = {b['total_decks']} decks")
        print(f"    median informative fraction  "
              f"{b['median_informative_fraction']}")
        print(f"    interior points unscorable   {b['total_unscorable']}"
              f" of {b['total_interior_points']}")
        print(f"    interior points FEASIBLE     {b['total_feasible']}")
    s = d.get("score") or {}
    print()
    for k in ("Q1", "Q2", "Q3", "Q4", "Q5"):
        if k in s:
            detail = {kk: vv for kk, vv in s[k].items() if kk != "pass"}
            print(f"  {k}: {'PASS' if s[k]['pass'] else 'MISS'}   {detail}")
    print(f"\n  SCORE {s.get('n_pass')} of {s.get('n_scored')}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--analyse", action="store_true")
    ap.add_argument("--arm", type=str, default="ab",
                    help="which arms to run: 'a', 'b' or 'ab'")
    ap.add_argument("--ckpt", type=str, default=str(CKPT))
    ap.add_argument("--seed", type=int, default=SEED)
    a = ap.parse_args(argv)
    if a.analyse:
        if not RESULTS.exists():
            raise SystemExit(f"{RESULTS.name} does not exist; run first")
        _report(json.loads(RESULTS.read_text(encoding="utf-8")))
        return 0
    if not a.run:
        ap.print_help()
        return 0
    if a.arm not in ("a", "b", "ab"):
        raise SystemExit("--arm must be 'a', 'b' or 'ab'")
    _report(run(ckpt=Path(a.ckpt), seed=a.seed, arms=a.arm))
    return 0


if __name__ == "__main__":                                  # pragma: no cover
    raise SystemExit(main())
