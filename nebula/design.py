"""
nebula/design.py — **the deliverable: target specs in, a sized schematic and
its measured specs out.**

    python -m nebula.design --peaking 9 --f-peak 1.9e9
    python -m nebula.design --peaking 9 --f-peak 1.9e9 --method cmaes --budget 150
    python -m nebula.design --peaking 9 --f-peak 1.9e9 --robust --verify --out out/

WHY THIS FILE EXISTS
---------------------
`CLAUDEwa.md` §2 states deliverable 1 in the competition's own words:

    "A Reinforcement Learning based Python framework that **takes target specs
     as input**, seamlessly integrates with a SPICE simulator, and **outputs
     the final schematic and resulting specs**."

Every piece of that has existed for weeks -- the box, the evaluator, the
reward, six search methods, the corner verification -- and **there was no front
door.** A reviewer opening this repository found fifteen experiment scripts and
no single command. This is the command.

THREE THINGS IT REFUSES TO PRETEND
-----------------------------------
**1. Whether the peaking request is in the objective depends on the SPEC SET,
and the run says which one it used.** This paragraph previously claimed
`reward_v1.margins` "deliberately ignores `target_peaking_db`". **That was true
before decision D6 and has been false since.** `margins()` emits
`S3_peaking_match` whenever a request is passed; what decides if it is *scored*
is the spec set:

* `V1_SPECS` (7 device rows) has no such row -- so on `--method library` and
  the plain searchers, `--peaking` is a **tie-break applied outside the
  reward**, among designs that already meet every spec. S3 reads *"3-12 dB,
  tunable"* as a band and `CLAUDEwa.md` §3 takes the band as the requirement;
  measured, one design scores identically against 3, 5, 7.5, 10 and 12 dB
  (`SPEC_CONDITIONED.md` §0).
* `V6_SPECS` (13 rows) carries **`S3_peaking_match` and `S3_f_peak_match`** --
  and that is what `--method auto` screens on. On the default path the request
  is in the objective, not beside it.

The distinction is printed on every run rather than left in a docstring,
because silently optimising a number the objective cannot see would be the
worst kind of demo -- and so would silently claiming one it can.

**2. The default method is not RL, and nobody chooses it.** `--method auto`
escalates by itself: candidates are proposed, the live 4-corner screen decides,
and the full search runs only if none survives. That is
`exp_hybrid.propose_then_search`, called rather than copied.

**The proposer is ANALYTIC FIRST, library after** (row 4y). The analytic
proposer solves the passives in closed form from the requested peak and peaking
(`experiments/invert_response.py`) and ranks candidates by a **max-min** margin
over DC headroom and output swing -- the two constraints that pull against each
other through `I_d * RL`. Entry 64 measured it accepting **11 of 16** against
the library's 6, and **entry 67 verified the SHIPPED path end to end: 13 of 16
requests answered at all 45 mandated corners, with eight already-solved controls
and none lost -- coverage 9 -> 13 of 16.** Twelve of the thirteen come from the
analytic proposer, at ranks 1-5, for 8-20 decks each against the search's
~1 085.

The library stays behind it because the analytic proposer fails 5 of 16 -- all
four 10 dB requests and 4 dB @ 1.387 GHz -- and on those the tool must be no
worse than before. `propose_then_search` screens in order and stops at the first
feasible candidate, so **the ordering is the policy**.

The earlier default was `--method library`, which meant the operator picked the
strategy. The brief says *"with zero human intervention"*, and a tool whose
first question is *"which of seven search methods would you like?"* has a human
in the loop at the moment a judge watches it run. The methods are all still
reachable by name, and the run reports which path answered, because a framework
that hid that would be advertising rather than reporting.

`cmaes` remains the measured best searcher (`BASELINES.md` §14). PPO is
available and is measured as *statistically
indistinguishable from uniform random search at every budget from 150 to
2400*.

**3. A nominal design is not a corner-robust design.** Without `--robust` the
search scores at TT only, and the report says the result is unverified at
corners. `G4_RESULTS.md` measured what that is worth: the best design at
nominal **failed 75 of 135** corner points.

THE NETLIST IS THE ONE THAT RAN
--------------------------------
`--out` writes the assembled SPICE deck captured from `run_point(keep_netlist=
True)` -- the exact string handed to ngspice, not a re-rendering. G32 is that
defect: a netlist a human reads that differs from the runner which produced the
numbers. It costs one extra simulation and is worth it.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import textwrap
import time
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from nebula.common.types import SPEC_F_PEAK_HZ_RANGE, SPEC_PEAKING_DB_RANGE
from nebula.device.sky130_runner import run_point
from nebula.rl import reward_v1 as R
from nebula.rl.contract import (ACTION_NAMES, ACTION_SPACE, N_ACTIONS,
                                sizing_from_u)
from nebula.rl.evaluator import SpiceBudget, Verdict, build_point, evaluate, scoring_meas
from nebula.rl.spec_dist import SpecTarget

#: What a design is reported against, in the units a datasheet would use.
SPEC_ROWS: tuple[tuple[str, str, str, str], ...] = (
    ("S3  peaking", "peaking_db", "dB", "3 - 12"),
    ("S3  peak frequency", "_f_peak_ghz", "GHz", "1.25 - 2.50"),
    ("S3  boost at Nyquist", "nyq_boost_db", "dB", "> 0"),
    ("S5  input noise", "_noise_mv", "mV_rms", "< 1.5"),
    ("S6  power", "_power_mw", "mW", "< 15"),
    ("    DC gain", "g_dc_db", "dB", "-"),
    ("    pair saturation", "pair_margin_v", "V", "> 0"),
    ("    tail saturation", "tail_margin_v", "V", "> 0"),
)


def _derived(meas: dict) -> dict:
    m = dict(meas)
    m["_f_peak_ghz"] = 2.5 * 2.0 ** float(meas["f_peak_oct"])
    m["_noise_mv"] = float(meas["inoise_vrms"]) * 1e3
    m["_power_mw"] = float(meas["power_w"]) * 1e3
    return m


# ─────────────────────────────────────────────────────────────────────────────
# The methods a spec can be answered with
# ─────────────────────────────────────────────────────────────────────────────


def solve_library(target: SpecTarget, peaking_tiebreak: bool = True) -> dict:
    """**Zero simulations.** Look the answer up among designs already measured.

    A measurement does not know what it was aiming at, so every design this
    project has ever simulated can be re-scored against a new target for free
    (`SPEC_CONDITIONED.md`). Measured: ~600 random designs answer any S3 spec at
    8.99 of a 9.0 ceiling, and the crossover against CMA-ES-at-150 is **two
    spec requests**.

    `peaking_tiebreak` is the honest half of `--peaking`: among designs whose
    reward is within `1e-3` of the best, prefer the one closest to the
    requested peaking. That is a preference expressed OUTSIDE the objective and
    it is labelled as one everywhere it appears.
    """
    from nebula.experiments import spec_pool as SP

    pool = SP.load_pool()
    scores = SP.score_pool(pool, target)
    best = float(np.max(scores))
    near = np.flatnonzero(scores >= best - 1e-3)
    if peaking_tiebreak and near.size > 1:
        pk = np.array([pool.meas[i]["peaking_db"] for i in near])
        idx = int(near[int(np.argmin(np.abs(pk - target.peaking_db)))])
    else:
        idx = int(np.argmax(scores))
    return {"u": [float(x) for x in pool.u[idx]], "reward": float(scores[idx]),
            "sims": 0, "n_candidates": len(pool),
            "n_tied_at_best": int(near.size),
            "design_id": pool.design_id[idx]}


#: Depth the auto path reads the library to. **5, not `exp_hybrid`'s 8.**
#: Entry 32 measured `accepted_at_k = [1, 4, 5, 5, 6, 6, 6, 6]`: k=5 reaches
#: the same acceptance as k=8 for 120 fewer decks, so it is the measured
#: optimum. `DEFAULT_TOPK` stays 8 in `exp_hybrid` because retuning it on the
#: run that measured it would be tuning; this is the delivery setting.
AUTO_K: int = 5


def solve_auto(target: SpecTarget, budget: int, seed: int,
               k: int = AUTO_K) -> dict:
    """**The default. No human picks a search strategy.**

    Retrieval proposes up to `k` candidates, the live 4-corner screen decides,
    and if none survives it falls back to the full search -- `exp_hybrid.
    propose_then_search`, called rather than copied, so the delivered tool and
    the measured sweep are the same code path (rule 9).

    This is what entry 40 measured over 16 requests: **mandated 45-corner
    coverage 7 -> 8 of 16 for 25 % fewer simulations**, and **1 284 decks per
    delivered compliant design against 1 960 -- 34 % cheaper**.

    **Why it is the default and `library` no longer is.** The brief says *"with
    zero human intervention"*. A tool whose first prompt is "which of seven
    search methods would you like?" has a human in the loop at the moment a
    judge watches it run. The escalation is now the tool's decision, made on a
    measured screen, and the run reports which path answered.
    """
    from nebula.experiments import exp_hybrid as H
    from nebula.experiments.adaptive_screen import EDGE4_MANDATED, AdaptiveScreen
    from nebula.experiments.exp_invert_screen import analytic_then_library

    # **Row 4y.** The candidate source is now ANALYTIC FIRST, library after.
    # Entry 64 measured the analytic proposer accepting 11 of 16 against the
    # library's 6, and entry 65 verified all 11 at the 45 mandated corners with
    # eight already-solved controls, none lost. The library stays behind it
    # because the analytic source fails 5 of 16 and the tool must not get worse
    # on those; `propose_then_search` screens in order and stops at the first
    # feasible candidate, so the ordering IS the policy.
    screen = AdaptiveScreen(EDGE4_MANDATED)
    hyb, res, _best = H.propose_then_search(
        target.peaking_db, target.f_peak_hz, screen,
        candidates=analytic_then_library, k=int(k),
        proposer_name="analytic+library", budget=budget, seed=seed)
    if res.u is None:
        raise RuntimeError(
            f"neither the {k}-candidate proposal nor the {budget}-evaluation "
            f"search produced an evaluable design for "
            f"{target.peaking_db:.2f} dB @ {target.f_peak_hz / 1e9:.3f} GHz. "
            f"This is a coverage miss, not a crash: the framework answers 12 "
            f"of 16 requests at the mandated 45 corners (entry 65).")
    return {"u": [float(x) for x in res.u],
            "reward": float(res.screen_reward), "sims": int(res.n_sims),
            "n_candidates": int(hyb.n_candidates),
            "n_tied_at_best": 1,
            "design_id": res.design_id,
            "which_path": hyb.which_path,
            "proposal_rank": hyb.proposal_rank,
            "n_sims_proposal": int(hyb.n_sims_proposal),
            "n_sims_search": int(hyb.n_sims_search),
            "screened_on": [p.label for p in screen.points]}


def solve_search(target: SpecTarget, method: str, budget: int, seed: int,
                 robust: bool, peaking_tiebreak: bool = True) -> dict:
    """Run one of the benchmarked search methods against this target."""
    from nebula.experiments import baselines as B

    problem = B.PROBLEMS["P3" if robust else "P1"]
    obj = B.Objective(problem, budget, ac_peak_interp=True,
                      target_f_peak_hz=target.f_peak_hz,
                      target_peaking_db=target.peaking_db)
    rng = np.random.default_rng(seed)
    try:
        B.METHODS[method](obj, rng)
    except B.BudgetExhausted:
        pass
    scored = [t for t in obj.trials if t.n_sims > 0]
    if not scored:
        raise RuntimeError(f"{method} produced no evaluated design in {budget} "
                           f"simulations")
    best = max(t.reward for t in scored)
    near = [t for t in scored if t.reward >= best - 1e-3]
    if peaking_tiebreak and len(near) > 1:
        near.sort(key=lambda t: abs((t.meas or {}).get("peaking_db", 1e9)
                                    - target.peaking_db))
    win = near[0]
    return {"u": list(win.u), "reward": float(win.reward), "sims": obj.n_sims,
            "n_candidates": len(scored), "n_tied_at_best": len(near),
            "design_id": win.design_id}


# ─────────────────────────────────────────────────────────────────────────────


def measure(u: Sequence[float], cl_f: float, budget: SpiceBudget,
            target: SpecTarget, corner: str = "tt", temp_c: float = 27.0,
            vdd_scale: float = 1.0) -> dict:
    sizing = sizing_from_u(np.asarray(u, dtype=float), cl_f=cl_f)
    ev = evaluate(sizing, budget, corner=corner, temp_c=temp_c,
                  vdd_scale=vdd_scale, ac_peak_interp=True)
    if ev.meas is None:
        return {"ok": False, "verdict": ev.verdict.value, "reason": ev.reason}
    rb = R.reward(scoring_meas(ev, True), target.f_peak_hz,
                  target_peaking_db=target.peaking_db,
                  headroom=(ev.headroom if ev.verdict is Verdict.HEADROOM_ONLY
                            else None))
    return {"ok": True, "verdict": ev.verdict.value,
            "meas": _derived(scoring_meas(ev, True)), "params": dict(sizing.params),
            "reward": float(rb.reward), "feasible": bool(rb.feasible),
            "worst_spec": rb.worst_spec, "design_id": ev.design_id}


def _schematic_panel(d: dict) -> dict:
    """The side panel on the drawing: only what this run actually measured.

    Every row is read off `d`; nothing is recomputed and nothing is defaulted.
    A row whose source is absent is **omitted**, never filled in -- a schematic
    that states a corner count nobody ran would be the worst instance of rule 4
    in the repository, because a picture is believed on sight.
    """
    panel: dict[str, str] = {"method": str(d.get("method", "?"))}
    nom = d.get("nominal") or {}
    # The verdict leads, because every row under it is only as meaningful as
    # this one. `library`/`cmaes` runs that fail still produce a netlist.
    panel["status"] = ("PASS" if nom.get("ok") and nom.get("feasible")
                       else str(nom.get("verdict") or "no measurement"))
    if nom.get("design_id"):
        panel["design id"] = str(nom["design_id"])
    panel["PDK"] = "SKY130 nfet_01v8"
    m = nom.get("meas") or {}
    if "peaking_db" in m:
        panel["peaking (TT)"] = f"{float(m['peaking_db']):.2f} dB"
    if "_f_peak_ghz" in m:
        panel["f_peak (TT)"] = f"{float(m['_f_peak_ghz']):.3f} GHz"
    if "_power_mw" in m:
        panel["power (TT)"] = f"{float(m['_power_mw']):.2f} mW"
    if "_noise_mv" in m:
        panel["input noise"] = f"{float(m['_noise_mv']):.3f} mVrms"
    v = d.get("verification") or {}
    # **Stated only when --verify actually ran.** Without it this design has
    # been measured at ONE corner, and a panel implying 45 would be a claim the
    # run never made.
    if "n_points" in v and "n_failed" in v:
        n, f = int(v["n_points"]), int(v["n_failed"])
        grid = (f" ({int(v['n_corners'])}x{int(v['n_loads'])})"
                if "n_corners" in v and "n_loads" in v else "")
        panel["verified points"] = f"{n - f} / {n} PASS{grid}"
    else:
        panel["verified points"] = "not verified (--verify)"
    sims = d.get("simulations") or {}
    if "total" in sims:
        panel["simulations"] = str(sims["total"])
    return panel



def request_miss(d: dict) -> Optional[dict]:
    """How far the DELIVERED design is from the REQUEST, against `TOL`.

    **Decision D6 exists because of exactly this** -- *"a judge asking for 11 dB
    must not be handed 6.4 dB with a PASS beside it"* -- and until now the
    delivered path could do that. `nominal.feasible` is scored on `V1_SPECS`,
    which carries **no request rows**: it means "meets the seven device specs at
    TT", not "matches what you asked for". Measured: `--peaking 12 --f-peak
    1.4e9` returns 9.10 dB @ 1.774 GHz -- **2.90 dB and 0.341 octaves out,
    against tolerances of 1.5 dB and 0.3 oct** -- with `feasible: True` and
    nothing flagged.

    Returns None when the request cannot be scored (no measurement), else the
    two misses and whether either exceeds its own tolerance. The caller decides
    what to do; this only measures.
    """
    m = (d.get("nominal") or {}).get("meas") or {}
    req = d.get("request") or {}
    if "peaking_db" not in m or "_f_peak_ghz" not in m:
        return None
    d_db = float(m["peaking_db"]) - float(req["peaking_db"])
    d_oct = math.log2(float(m["_f_peak_ghz"]) / float(req["f_peak_ghz"]))
    tol_db = float(R.TOL["S3_peaking_match"])
    tol_oct = float(R.TOL["S3_f_peak_match"])
    return {"peaking_err_db": d_db, "f_peak_err_oct": d_oct,
            "tol_peaking_db": tol_db, "tol_f_peak_oct": tol_oct,
            "peaking_missed": abs(d_db) > tol_db,
            "f_peak_missed": abs(d_oct) > tol_oct,
            "request_met": abs(d_db) <= tol_db and abs(d_oct) <= tol_oct}


def netlist_for(u: Sequence[float], cl_f: float) -> Optional[str]:
    """The deck that RAN, captured rather than re-rendered (rule 9, G32)."""
    sizing = sizing_from_u(np.asarray(u, dtype=float), cl_f=cl_f)
    point, _ = build_point(sizing, corner="tt", vdd_scale=1.0)
    pt = run_point(point, corner="tt", temp_c=27.0, swing=False,
                   ac_peak_interp=True, keep_netlist=True)
    return pt.netlist


def design(peaking_db: float, f_peak_hz: float, method: str = "auto",
           budget: int = 150, seed: int = 0, robust: bool = False,
           verify: bool = False, peaking_tiebreak: bool = True) -> dict:
    """Target specs in; a sized schematic and its measured specs out."""
    target = SpecTarget(peaking_db=float(peaking_db), f_peak_hz=float(f_peak_hz))
    t0 = time.perf_counter()
    if method == "auto":
        sol = solve_auto(target, budget, seed)
    elif method == "library":
        sol = solve_library(target, peaking_tiebreak)
    else:
        sol = solve_search(target, method, budget, seed, robust,
                           peaking_tiebreak)

    from nebula.experiments.cl_range import committed_cl_range

    cl_mid = committed_cl_range().cl_mid_f
    budget_obj = SpiceBudget()
    nominal = measure(sol["u"], cl_mid, budget_obj, target)

    out = {
        "request": {"peaking_db": target.peaking_db,
                    "f_peak_hz": target.f_peak_hz,
                    "f_peak_ghz": target.f_peak_hz / 1e9},
        # `auto` screens every candidate on the live 4-corner screen before it
        # delivers, so its search IS corner-aware; `robust` stays the flag for
        # the other methods. Reporting `auto` as a nominal-only search would
        # understate it, and reporting it as 45-corner verified would overstate
        # it -- it is neither, and `--verify` is still what buys the 45.
        "method": method,
        "robust_search": bool(robust) or method == "auto",
        "search": sol, "nominal": nominal,
        "simulations": {"search": sol["sims"],
                        "measure": budget_obj.calls},
        # **This note was WRONG for a fortnight and is now a function of the
        # path.** Decision D6 created `S3_peaking_match` and `V6_SPECS`, and
        # the auto path scores them -- so on that path the requested peaking IS
        # in the objective. The old blanket sentence survived D6 unchanged,
        # printed on every run, and `SCOPE_BOUNDARY.md` §3 built the "the spec
        # manifold is 1-D" argument on top of it. It is true of `V1_SPECS`
        # only, and it now says so.
        "peaking_is_a_band_not_a_target": (
            "the auto path scores V6_SPECS, which contains S3_peaking_match "
            "and S3_f_peak_match: the requested peaking and frequency are IN "
            "the screened objective, not tie-breaks. The nominal row below is "
            "still scored on V1_SPECS (7 device rows at TT), where the request "
            "is a tie-break only."
            if method == "auto" else
            "reward_v1's DEFAULT spec set, V1_SPECS, has no S3_peaking_match "
            "row, so on this path target_peaking_db is honoured as a TIE-BREAK "
            "outside the objective. NOTE this is a property of V1_SPECS, not "
            "of reward_v1: V5/V6_SPECS do score the request (decision D6), and "
            "--method auto uses them."),
        "wall_s": time.perf_counter() - t0,
    }
    # **D6, enforced on the delivered path.** Measured and attached to every
    # run, so a request the tool could not reach is visible in the JSON as well
    # as on the console.
    out["request_match"] = request_miss(out)

    if verify:
        from nebula.experiments.exp_g4_verify import Candidate, verify as g4_verify

        cand = Candidate(design_id=str(nominal.get("design_id", "?")),
                         u=tuple(sol["u"]), role="requested",
                         source=f"{method}", claimed_reward=sol["reward"],
                         claimed_worst_point=None)
        vb = SpiceBudget()
        v = g4_verify(cand, vb)
        # **BREAK OUT THE 45 MANDATED CORNERS BEFORE DISCARDING THE POINTS.**
        # The brief mandates PVT only -- 5 process x 3 VDD x 3 temp = 45 -- and
        # the third axis (load) is this project's own addition. Reporting only
        # the 135-point verdict meant `--verify` could print "FAILS" on a design
        # that meets every mandated corner, and the number the project actually
        # claims coverage on could not be produced by the tool at all. It could
        # only be recovered from an experiment script, which is exactly the
        # measured-versus-shipped gap rows 4r and 4y were about.
        pts = v.get("points") or []
        if pts:
            loads = sorted({round(float(q["cl_f"]), 20) for q in pts})
            design_load = loads[len(loads) // 2]
            mand = [q for q in pts
                    if abs(float(q["cl_f"]) - design_load) < 1e-20]
            v["n_mandated_points"] = len(mand)
            v["n_mandated_pass"] = sum(1 for q in mand if q.get("feasible"))
            v["mandated_all_pass"] = (v["n_mandated_pass"] == len(mand)
                                      and bool(mand))
            v["design_load_f"] = float(design_load)
        v.pop("points", None)
        out["verification"] = v
        out["simulations"]["verify"] = vb.calls
    out["simulations"]["total"] = sum(
        v for k, v in out["simulations"].items() if k != "total")
    return out


# ─────────────────────────────────────────────────────────────────────────────


def report(d: dict) -> str:
    L: list[str] = []
    req = d["request"]
    L.append("=" * 74)
    L.append("NEBULA -- CTLE sizing.  Target specs in, schematic and specs out.")
    L.append("=" * 74)
    L.append(f"  REQUESTED   peaking {req['peaking_db']:.2f} dB   "
             f"peak at {req['f_peak_ghz']:.4f} GHz")
    # `.get`: `report()` is called on hand-built dicts in tests and on the
    # early-failure path, neither of which carries a search record.
    sr = d.get("search") or {}
    if d["method"] == "auto":
        # **Name the SOURCE, not just "a proposal".** This printed
        # "retrieval" for every accepted proposal regardless of where the
        # candidate came from -- and since row 4y the analytic solver answers
        # 12 of the 13 proposal-answered requests, so the tool was crediting
        # retrieval for its own best feature. The ordering is
        # analytic[1..K] -> library[1..K] -> analytic-deep[K+1..DEEP_K], so the
        # rank says which source answered.
        rank = sr.get("proposal_rank")
        if sr.get("which_path") == "proposal" and rank:
            from nebula.experiments.exp_invert_screen import K as _K
            src = ("the closed-form ANALYTIC solve" if rank <= _K
                   else "RETRIEVAL from the library" if rank <= 2 * _K
                   else "the closed-form ANALYTIC solve (deep tail)")
            how = f"{src}, accepted at rank {rank} of {sr.get('n_candidates')}"
        elif sr.get("which_path") == "proposal":
            how = f"a proposal at rank {rank} of {sr.get('n_candidates')}"
        else:
            how = "the search -- no proposed candidate passed the screen"
        L.append("  METHOD      auto   (no strategy was chosen by a human)")
        L.append(f"              answered by {how}")
        L.append(f"              screened on {len(sr.get('screened_on', []))} "
                 f"corner/load points before delivery")
    else:
        L.append(f"  METHOD      {d['method']}"
                 + ("   (corner-robust search)" if d["robust_search"] else
                    "   (nominal search -- NOT verified at corners)"))
    n = d["nominal"]
    if not n["ok"]:
        L.append(f"\n  FAILED: {n['verdict']} -- {n.get('reason')}")
        return "\n".join(L)

    L.append("")
    L.append("  SCHEMATIC  (drawn SKY130 devices)")
    p = n["params"]
    L.append(f"    w_in    {p['w_in'] * 1e6:10.3f} um      "
             f"l_in    {p['l_in'] * 1e9:10.2f} nm      nf_in {int(p['nf_in']):3d}")
    L.append(f"    i_bias  {p['i_bias'] * 1e3:10.4f} mA      "
             f"vcm_in  {p['vcm_in']:10.4f} V")
    L.append(f"    rs      {p['rs']:10.2f} ohm     "
             f"cs      {p['cs'] * 1e12:10.4f} pF")
    L.append(f"    rl      {p['rl']:10.2f} ohm     "
             f"cl      {p['cl'] * 1e15:10.2f} fF  (context)")
    L.append("")
    L.append("  RESULTING SPECS  at TT / 1.00 / 27 C")
    L.append(f"    {'spec':<24}{'measured':>14}  {'requirement':<14}")
    L.append("    " + "-" * 56)
    m = n["meas"]
    for label, key, unit, req_s in SPEC_ROWS:
        L.append(f"    {label:<24}{m[key]:>10.4f} {unit:<4} {req_s:<14}")
    L.append("")
    L.append(f"    reward {n['reward']:.4f}   feasible={n['feasible']}"
             + (f"   binding: {n['worst_spec']}" if n["worst_spec"] else ""))
    # **What that word means, printed beside it.** `measure()` scores
    # `reward_v1.reward`'s default `V1_SPECS` -- seven device rows, at TT only.
    # It is NOT the 13-row `V6_SPECS` the coverage sweep and the 135-point
    # checklist score. A reader who takes `feasible=True` for "meets the
    # specification" would be reading three specs that were never measured
    # here, so the scope is stated rather than left to be discovered.
    L.append(f"    ^ feasible = {len(R.V1_SPECS)} device rows at TT/1.00/27C. "
             f"NOT S4 (linearity), S7 (area) or S8 (eye):")
    L.append(f"      those need the link bridge and the 45-corner checklist "
             f"({len(R.V6V_SPECS)} rows) -- see --verify.")

    # **DID IT ANSWER THE QUESTION THAT WAS ASKED?** (decision D6.) `feasible`
    # above is V1_SPECS, which has no request rows, so a design can meet every
    # device spec and still be nowhere near what was requested. Measured before
    # this was added: `--peaking 12 --f-peak 1.4e9` returned 9.10 dB @
    # 1.774 GHz -- 2.90 dB and 0.341 oct out, against 1.5 and 0.3 -- and said
    # `feasible=True` with nothing flagged.
    rm = d.get("request_match")
    if rm:
        L.append("")
        if rm["request_met"]:
            L.append(f"  REQUEST MET   peaking {rm['peaking_err_db']:+.2f} dB "
                     f"(tol {rm['tol_peaking_db']:.2f}), "
                     f"f_peak {rm['f_peak_err_oct']:+.3f} oct "
                     f"(tol {rm['tol_f_peak_oct']:.2f})")
        else:
            L.append("  *** REQUEST NOT MET -- the delivered design does not "
                     "match what was asked for ***")
            if rm["peaking_missed"]:
                L.append(f"      peaking off by {rm['peaking_err_db']:+.2f} dB"
                         f"   (tolerance {rm['tol_peaking_db']:.2f} dB)")
            if rm["f_peak_missed"]:
                L.append(f"      f_peak  off by {rm['f_peak_err_oct']:+.3f} oct"
                         f"  (tolerance {rm['tol_f_peak_oct']:.2f} oct)")
            L.append("      `feasible` above is V1_SPECS (device rows at TT) "
                     "and does NOT include the request.")

    v = d.get("verification")
    if v:
        L.append("")
        L.append(f"  CORNER VERIFICATION")
        if "n_mandated_pass" in v:
            L.append(f"    MANDATED PVT (S9): "
                     f"{v['n_mandated_pass']} / {v['n_mandated_points']}"
                     f"   {'PASS' if v['mandated_all_pass'] else 'FAIL'}"
                     f"   <- the brief's own grid, at the design load")
        L.append(f"    load sweep (this project's extra axis): "
                 f"{v['n_corners']} corners x {v['n_loads']} loads = "
                 f"{v['n_points']} points")
        L.append(f"    {'ALL POINTS PASS' if v['all_points_pass'] else 'FAILS'}"
                 f"   {v['n_failed']} failed"
                 f"   ({v['n_failed_outside_the_screen']} of them at corners "
                 f"the 3-corner screen never evaluates)")
        L.append(f"    worst {v['worst_reward']:.4f} at {v['worst_point']}"
                 f"  ({v['worst_spec']})"
                 f"   screened corner: {v['worst_is_a_screen_corner']}")
    elif d["method"] == "auto":
        # **`auto` sets `robust_search`, so without this branch it would print
        # NOTHING about the mandated 45** -- the loudest possible silence, on
        # the default path. Screened is not verified, and the gap is four
        # points against forty-five.
        n_screen = len(sr.get("screened_on", []))
        L.append("")
        L.append(f"  SCREENED at {n_screen} corner/load points, NOT VERIFIED "
                 f"at the mandated 45.")
        L.append("  The screen reproduces the full-135 worst case exactly on "
                 "every design")
        L.append("  ever fully verified (PROGRESS.md 4), which is evidence and "
                 "not proof.")
        L.append("  Add --verify for 45 corners x 3 loads = 135 points.")
    elif not d["robust_search"]:
        L.append("")
        L.append("  NOT VERIFIED AT CORNERS. Re-run with --robust --verify.")
        L.append("  G4_RESULTS.md measured what that is worth: the best design")
        L.append("  at nominal failed 75 of 135 corner points.")

    s = d["simulations"]
    L.append("")
    L.append(f"  COST  {s['total']} SPICE simulations "
             f"(search {s['search']}, measure {s['measure']}"
             + (f", verify {s['verify']}" if "verify" in s else "")
             + f")   {d['wall_s']:.1f} s")
    L.append("")
    L.append("  NOTE ON --peaking: " + d["peaking_is_a_band_not_a_target"])
    L.append("=" * 74)
    return "\n".join(L)


def provenance_report() -> str:
    """**Why the search box is these numbers and not a preference.**

    The brief's *"zero human intervention"* is fairly read as a question about
    where the human judgement went. It went into the box, once -- and every
    edge of it is a measurement, not a taste. `ActionDim.__post_init__`
    **raises on a bound with no provenance**, so an unjustified edge cannot be
    committed; this only prints what the type already enforces.

    Read it aloud at the demo when someone asks "who chose those ranges".
    """
    L = ["=" * 74,
         "THE SEARCH BOX, AND THE MEASUREMENT BEHIND EACH EDGE",
         "=" * 74,
         "  Not a preference. `rl/contract.py::ActionDim` REFUSES a bound with",
         "  no provenance, so the justification below is enforced by the type,",
         "  not by a convention someone might forget.",
         ""]
    for d in ACTION_SPACE:
        scale = "log" if d.log else "linear"
        L.append(f"  {d.name:<8} {d.lo:>10.4g} .. {d.hi:<10.4g} {d.unit:<5} "
                 f"({scale})")
        for line in textwrap.wrap(d.provenance, 66):
            L.append(f"           {line}")
        L.append("")
    L.append(f"  {len(ACTION_SPACE)} dimensions. A full factorial over them at "
             f"the resolution the")
    L.append("  simulator can actually resolve is 3,402,000 simulations / 92 h")
    L.append("  (`experiments/sweep_cost_results.json`), which is the number")
    L.append("  the brief's 'significantly lower time than sweeping' asks for.")
    L.append("=" * 74)
    return "\n".join(L)


def main(argv: Optional[Sequence[str]] = None) -> int:
    lo_db, hi_db = SPEC_PEAKING_DB_RANGE
    lo_hz, hi_hz = SPEC_F_PEAK_HZ_RANGE
    ap = argparse.ArgumentParser(
        prog="python -m nebula.design", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    # NOT `required=True`: `--provenance` is a question about the tool, not
    # a design request, and making it demand a spec it will not use would be
    # exactly the sort of friction this file is trying to remove.
    ap.add_argument("--peaking", type=float, default=None,
                    help=f"HF peaking, dB. S3's band is {lo_db}-{hi_db}. "
                         f"Scored by the objective on --method auto; a "
                         f"TIE-BREAK on the others. See the module docstring.")
    ap.add_argument("--f-peak", type=float, default=None,
                    help=f"peak frequency in Hz (or GHz if < 100). S3's window "
                         f"is {lo_hz/1e9:.2f}-{hi_hz/1e9:.2f} GHz. This IS the "
                         f"reward's target.")
    ap.add_argument("--method", default="auto",
                    choices=("auto", "library", "uniform", "lhs", "grid",
                             "cmaes", "gp_bo", "ppo"),
                    help="auto = THE DEFAULT and the deliverable: the "
                         "passives are SOLVED in closed form and proposed "
                         "first, retrieval proposes next, the 4-corner screen "
                         "decides, and the search runs only if it must -- "
                         "no human picks a strategy. "
                         "library = 0 simulations, no corner screen; "
                         "cmaes = the best SEARCHER; ppo = the RL policy, "
                         "measured indistinguishable from uniform random")
    ap.add_argument("--budget", type=int, default=150,
                    help="simulation budget for search methods")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--robust", action="store_true",
                    help="search on the worst of 3 corners x 2 loads instead "
                         "of at TT only")
    ap.add_argument("--verify", action="store_true",
                    help="verify at 45 corners x 3 loads (135 simulations)")
    ap.add_argument("--no-peaking-tiebreak", action="store_true")
    ap.add_argument("--out", type=Path, default=None,
                    help="write design.json and design.cir here")
    ap.add_argument("--json", action="store_true", help="print JSON only")
    ap.add_argument("--provenance", action="store_true",
                    help="print the search box and the measurement behind "
                         "each of its edges, then exit. Answers 'who chose "
                         "those ranges' with data rather than a claim.")
    args = ap.parse_args(argv)

    if args.provenance:
        print(provenance_report())
        return 0
    missing = [f"--{n}" for n, v in (("peaking", args.peaking),
                                     ("f-peak", args.f_peak)) if v is None]
    if missing:
        ap.error(f"the following arguments are required: {', '.join(missing)}")

    f_peak = args.f_peak * 1e9 if args.f_peak < 100 else args.f_peak
    try:
        d = design(args.peaking, f_peak, method=args.method,
                   budget=args.budget, seed=args.seed, robust=args.robust,
                   verify=args.verify,
                   peaking_tiebreak=not args.no_peaking_tiebreak)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(d, indent=1, default=str) if args.json else report(d))

    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "design.json").write_text(
            json.dumps(d, indent=1, default=str), encoding="utf-8")
        from nebula.experiments.cl_range import committed_cl_range

        deck = netlist_for(d["search"]["u"], committed_cl_range().cl_mid_f)
        written = [args.out / "design.json"]
        if deck:
            (args.out / "design.cir").write_text(deck, encoding="utf-8")
            written.append(args.out / "design.cir")
            # **The brief asks for a SCHEMATIC, and a SPICE deck is one only to
            # a reader who parses SPICE.** The drawing is rendered FROM `deck`
            # -- the same string just written to `design.cir` -- so the picture
            # and the netlist cannot disagree (G32). A drawing failure must not
            # cost the caller the deck and the JSON that already succeeded, so
            # it is reported and not raised.
            try:
                from nebula.report.schematic import draw_schematic

                nom = d.get("nominal") or {}
                # **A failed run still has a netlist.** Drawing it silently
                # under a panel headed "Delivered design" would hand a reader
                # a picture of a circuit that does not meet the request.
                warn = None
                if not nom.get("ok", False):
                    warn = str(nom.get("verdict") or "no valid measurement")
                written.append(draw_schematic(
                    deck, args.out / "design_schematic.png",
                    subtitle=f"target {d['request']['peaking_db']:.1f} dB @ "
                             f"{d['request']['f_peak_hz'] / 1e9:.3f} GHz"
                             f"  -  values parsed from the netlist beside it",
                    extra=_schematic_panel(d), warning=warn))
            except Exception as exc:                        # noqa: BLE001
                print(f"\nwarning: the schematic could not be drawn ({exc}). "
                      f"design.json and design.cir are unaffected.",
                      file=sys.stderr)
        print("\nwrote " + ", ".join(str(w) for w in written))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
