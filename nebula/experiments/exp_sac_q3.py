"""experiments/exp_sac_q3.py — entry 41's Q3: the one that would be the headline.

THE QUESTION, VERBATIM FROM THE PRE-REGISTRATION
-------------------------------------------------
    "Q3 -- THE POINT. On the 8 requests neither retrieval nor CMA-ES solved, a
     warm-started 16-step rollout produces a design that passes all 45 mandated
     corners for at least ONE of them. Confidence: 0.35.
     Falsifier: 0 of 8."

Entry 40 left eight requests unanswered after ~1 085 decks of CMA-ES each:

    idx   request                45-corner result after CMA-ES
      0   4.0 dB @ 1.387 GHz           32 / 45
      3   4.0 dB @ 2.253 GHz           11 / 45
      5   6.0 dB @ 1.627 GHz           44 / 45   <- one corner short
      8   8.0 dB @ 1.387 GHz           35 / 45
     12  10.0 dB @ 1.387 GHz            0 / 45
     13  10.0 dB @ 1.627 GHz           17 / 45
     14  10.0 dB @ 1.921 GHz           44 / 45   <- one corner short
     15  10.0 dB @ 2.253 GHz           37 / 45

A hit means **RL solved a request the classical optimiser could not, at 64
decks against 1 085.**

WHY THIS ROLLS OUT IN `ScreenEnv` AND NOT IN THE ANALYTIC ENV
--------------------------------------------------------------
`exp_sac_propose`'s `_Rollouts` proposes from `AnalyticCtleEnv` -- **zero
SPICE**, 4 decks paid only for the candidate finally scored. That is the right
harness for entries 36 and 38, whose policies were trained analytically, and
Q4 is measured there for comparability.

Entry 41's policy was trained **in `ScreenEnv`**, where every observation is
built from four real SPICE corners. Its own cost model says so: *"A 16-step
warm-started rollout costs 64 decks"* -- 16 steps x 4 corners. Rolling it out
analytically would deploy it on an observation distribution it never saw, which
is the exact class of mismatch entries 34-38 spent five experiments removing.

So Q3 rolls out in `ScreenEnv`, at the pre-registered 64 decks per request.
**This also makes Q3 an independent read on Q4**: if SPICE-in-the-loop rollouts
find feasible designs where analytic rollouts found none, the gap is the
deployment mismatch and not the policy.

WHAT IS NOT DONE HERE
----------------------
No tolerance is loosened, no screen point is changed, no reward is touched
(G111). A design is "feasible" iff `ScreenEnv`'s own `evaluate_at_points`
says so, and "compliant" iff `exp_g4_verify.verify_full` passes it at all 45
mandated corners -- the same verifier every coverage number in this project
used (rule 9).

Reproduce:

    python -m nebula.experiments.exp_sac_q3 --run
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

HERE = Path(__file__).resolve().parent
CKPT = HERE / "sac_policy_screen.pt"
RESULTS = HERE / "sac_q3_results.json"

#: Entry 41's eight, as (grid index, CMA-ES 45-corner result). The requests
#: themselves are DERIVED from `exp_coverage`'s grid and cross-checked against
#: this table, so a change to the grid fails loudly instead of silently
#: measuring different requests (rule 9).
HARD: tuple[tuple[int, int], ...] = (
    (0, 32), (3, 11), (5, 44), (8, 35), (12, 0), (13, 17), (14, 44), (15, 37),
)

HORIZON: int = 16
SEED: int = 23_0826


def hard_requests() -> list[dict]:
    """The eight requests, derived from the coverage grid and checked."""
    from nebula.experiments import exp_coverage as C

    grid = [(p, f) for p in C.PEAKING_REQUESTS for f in C.FREQ_REQUESTS]
    if len(grid) != 16:
        raise ValueError(f"coverage grid is {len(grid)} requests, expected 16")
    out = []
    for idx, cma45 in HARD:
        peaking, f_hz = grid[idx]
        out.append({"index": idx, "peaking_db": float(peaking),
                    "f_peak_hz": float(f_hz), "cma_es_pvt45": cma45})
    # Cross-check against the pre-registration's own printed table.
    expect = {0: (4.0, 1.387), 3: (4.0, 2.253), 5: (6.0, 1.627),
              8: (8.0, 1.387), 12: (10.0, 1.387), 13: (10.0, 1.627),
              14: (10.0, 1.921), 15: (10.0, 2.253)}
    for r in out:
        p, g = expect[r["index"]]
        if abs(r["peaking_db"] - p) > 1e-9 or abs(r["f_peak_hz"] / 1e9 - g) > 5e-3:
            raise ValueError(
                f"request {r['index']} is {r['peaking_db']} dB @ "
                f"{r['f_peak_hz']/1e9:.3f} GHz; entry 41 recorded {p} dB @ "
                f"{g} GHz. The grid moved -- Q3 would measure something else.")
    return out


def rollout(agent, req: dict, seed: int = SEED, horizon: int = HORIZON) -> dict:
    """One warm-started rollout for one request. 4 decks per step."""
    from nebula.rl.screen_env import ScreenEnv
    from nebula.rl.spec_dist import SpecTarget

    target = SpecTarget(peaking_db=req["peaking_db"],
                        f_peak_hz=req["f_peak_hz"])
    env = ScreenEnv([target], seed=seed, horizon=horizon)
    obs, info = env.reset()

    visited: list[dict] = []
    # The start IS a candidate -- it was evaluated by reset() and cost 4 decks.
    visited.append({"step": 0, "u": env.u.tolist(),
                    "feasible": bool(info.get("feasible", False)),
                    "reward": None, "reverted": False})

    for t in range(1, horizon + 1):
        a = agent.actor.act(obs, deterministic=True)
        obs, reward, _term, trunc, info = env.step(a)
        visited.append({"step": t, "u": env.u.tolist(),
                        "feasible": bool(info.get("feasible", False)),
                        "reward": float(reward),
                        "reverted": bool(info.get("reverted", False)),
                        "worst_spec": info.get("worst_spec"),
                        "reason": info.get("reason")})
        if trunc:
            break

    rep = env.report()
    feas = [v for v in visited if v["feasible"]]
    best = (max(feas, key=lambda v: (v["reward"] if v["reward"] is not None
                                     else -1e9))
            if feas else None)
    return {"visited": visited, "n_feasible": len(feas), "best": best,
            "n_decks": int(rep.get("n_decks", 0)),
            "n_reverted": int(rep.get("n_reverted", 0)),
            "warm_start_feasible": bool(visited[0]["feasible"])}


def verify45(u: Sequence[float], req: dict) -> dict:
    """All 45 mandated corners, through the project's one verifier."""
    from nebula.experiments.exp_g4_verify import Candidate, verify_full

    cand = Candidate(design_id="q3", u=tuple(float(x) for x in u), role="q3",
                     source=f"q3/{req['peaking_db']:.1f}dB@"
                            f"{req['f_peak_hz']/1e9:.3f}GHz",
                     claimed_reward=0.0, claimed_worst_point=None)
    out = verify_full(cand, ac_peak_interp=True)
    pts = out.get("points") or []
    mand = [p for p in pts if p.get("mandated", True)]
    npass = sum(1 for p in mand if p.get("pass"))
    return {"n_pvt45_pass": npass, "n_pvt45_total": len(mand),
            "compliant": bool(mand and npass == len(mand))}


def run(ckpt: Path = CKPT, seed: int = SEED, horizon: int = HORIZON) -> dict:
    from nebula.experiments.exp_sac_propose import load_agent
    from nebula.experiments.runlock import hold, stamp

    reqs = hard_requests()
    agent, meta = load_agent(ckpt)
    print(f"loaded {ckpt.name}: {meta}", flush=True)

    with hold("sac_q3", meta={"n_requests": len(reqs)}):
        t0 = time.time()
        out: dict = {"task": "entry 41 Q3: can RL solve what CMA-ES could not?",
                     **stamp(), "checkpoint": {"path": ckpt.name, **meta},
                     "horizon": horizon, "seed": seed,
                     "rollout_env": "ScreenEnv (4 SPICE decks per step)",
                     "requests": []}

        for req in reqs:
            print(f"\n=== request {req['index']}: {req['peaking_db']:.1f} dB @ "
                  f"{req['f_peak_hz']/1e9:.3f} GHz  "
                  f"(CMA-ES: {req['cma_es_pvt45']}/45) ===", flush=True)
            r = rollout(agent, req, seed=seed, horizon=horizon)
            rec = dict(req)
            rec.update({k: r[k] for k in
                        ("n_feasible", "n_decks", "n_reverted",
                         "warm_start_feasible")})
            print(f"  warm start feasible: {r['warm_start_feasible']}   "
                  f"screen-feasible steps: {r['n_feasible']}/{horizon + 1}   "
                  f"{r['n_decks']} decks", flush=True)

            if r["best"] is not None:
                print("  -> screen-feasible design found; verifying 45 corners",
                      flush=True)
                v = verify45(r["best"]["u"], req)
                rec["verified"] = v
                rec["u"] = r["best"]["u"]
                print(f"     45-corner: {v['n_pvt45_pass']}/{v['n_pvt45_total']}"
                      f"   compliant={v['compliant']}", flush=True)
            else:
                rec["verified"] = None
                best_r = max((v["reward"] for v in r["visited"]
                              if v["reward"] is not None), default=None)
                rec["best_reward_seen"] = best_r
                print(f"  -> no screen-feasible design; best reward "
                      f"{best_r if best_r is None else round(best_r, 4)}",
                      flush=True)
            out["requests"].append(rec)

        solved = [r for r in out["requests"]
                  if r.get("verified") and r["verified"]["compliant"]]
        out["n_solved"] = len(solved)
        out["solved_indices"] = [r["index"] for r in solved]
        out["total_decks"] = sum(int(r["n_decks"]) for r in out["requests"])
        out["Q3_pass"] = bool(solved)
        out["wall_s"] = time.time() - t0
        RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def _report(d: dict) -> None:
    print()
    print(f"ENTRY 41 Q3 -- {d['checkpoint']['path']}, "
          f"{d['checkpoint'].get('steps')} steps, rollouts in "
          f"{d['rollout_env']}")
    print()
    print(f"  {'idx':>3} {'request':22} {'CMA-ES':>7} {'feas':>5} "
          f"{'45-corner':>10} {'decks':>6}")
    for r in d["requests"]:
        v = r.get("verified")
        pv = (f"{v['n_pvt45_pass']}/{v['n_pvt45_total']}" if v else "--")
        print(f"  {r['index']:3d} {r['peaking_db']:5.1f} dB @ "
              f"{r['f_peak_hz']/1e9:.3f} GHz {r['cma_es_pvt45']:5d}/45 "
              f"{r['n_feasible']:5d} {pv:>10} {r['n_decks']:6d}")
    print()
    print(f"  TOTAL {d['total_decks']} decks   "
          f"(CMA-ES spent ~1 085 per request = ~8 680)")
    print(f"  Q3: {d['n_solved']} of 8 solved -> "
          f"{'PASS' if d['Q3_pass'] else 'MISS (falsifier was 0 of 8)'}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--ckpt", type=str, default=str(CKPT))
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--horizon", type=int, default=HORIZON)
    a = ap.parse_args(argv)
    if not a.run:
        ap.print_help()
        return 0
    _report(run(ckpt=Path(a.ckpt), seed=a.seed, horizon=a.horizon))
    return 0


if __name__ == "__main__":                                  # pragma: no cover
    raise SystemExit(main())
