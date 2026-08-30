"""experiments/exp_rerank.py -- **step 5B: can corner-robustness be PREDICTED?
The decisive test costs ZERO SPICE.**

THE QUESTION, AND WHY IT IS THE RIGHT ONE
-------------------------------------------
Step 4 measured a behaviour-cloned generator at **2 of 16** against retrieval's
**6 of 16** (not a significant gap, Fisher p = 0.167 -- but not an improvement
either). A zero-SPICE diagnostic said why:

* **all 7 of the library's accepted designs are in the generator's training
  set**, each inside a fibre of 28-146 demonstrations, and the generator lands
  0.376-0.639 away against a fibre radius of 0.516;
* max-likelihood cloning models the fibre's **density**, and corner-robustness
  is a minority property the demonstrations do not mark;
* **`exp_coverage.library_candidates` ranks on**
  `max(|df_oct|/TOL, |dpk|/TOL)` -- distance from target in exactly the two
  axes that *define* the fibre -- so retrieval **provably** cannot discriminate
  within one either.

So the open question is narrow: **given `(design, requested spec)` and no
simulation, can anything predict whether the design will survive the four
corners?** If yes, it reorders the generator's fibre samples and the RL stage
has a well-posed job. If no, the cheap route is dead.

**THE DECISIVE TEST NEEDS NO SIMULATOR.** The true feasibility of all 160
already-scored candidates (80 library, 80 BC) is on disk. If a ranker cannot
usefully reorder designs that have *already been measured*, it cannot help live.

TWO PROTOCOL TRAPS, HANDLED IN ADVANCE
----------------------------------------
1. **The label data holds only 16 distinct spec targets -- the SAME 16 the
   accept rate is measured on.** A random split leaks: the model would see
   corner labels for designs targeting the very request it is scored on. The
   split is therefore **leave-one-request-out**, 16 folds.
2. **The labels come from CMA-ES trajectories; the generator samples a
   different distribution.** Entry 37 named this ("the training data is
   CENSORED") and it is the most likely way a good AUC becomes a useless
   deployment. The transfer test trains with **no BC design at all** and scores
   the 80 BC candidates.

Pre-registered as `PREDICTIONS.md` entry 44 Part C, with Q1-Q5, before this
module existed. **Q4 is the kill switch:** if the ranker cannot beat `-dev` at
ordering the same candidates, the fibre-selection diagnosis is wrong and the
registered instruction is to stop rather than proceed to SAC.

    python -m nebula.experiments.exp_rerank --run
"""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "rerank_results.json"

#: The corner-screened logs. **Enumerated, never globbed** (G101).
#: `coverage_run.jsonl` is DELIBERATELY ABSENT: it holds the identical 3 200
#: designs as `coverage_run_AFTER_unclip_fix.jsonl` (measured 2026-08-30), and
#: including both would double-weight a third of the dataset while reporting a
#: larger n than exists.
SCREEN_LOGS: tuple[str, ...] = (
    "coverage_run_AFTER_unclip_fix.jsonl",
    "coverage_run_BEFORE_seeding_fix.jsonl",
    "hybrid_run.jsonl",
)

#: The two already-scored candidate sets the deployment test reorders.
LIB_SCAN = HERE / "topk_scan_library_k5.json"
BC_SCAN = HERE / "topk_scan_bc_mdn.json"

SEED: int = 23_0830

#: Entry 44's thresholds. **Not to be edited after the run** (G110).
Q1_AUC_MIN: float = 0.70
Q2_TRANSFER_AUC_MIN: float = 0.65
Q3_RANK_TARGET: int = 2
Q5_BASELINE_FEASIBLE: int = 2


# --------------------------------------------------------------------------
# the data
# --------------------------------------------------------------------------

def load_screened(logs: Sequence[str] = SCREEN_LOGS,
                  here: Optional[Path] = None) -> dict:
    """Every corner-screened design with the target it was screened against.

    **De-duplicated on `(u, target)`, not on `u`**: the same sizing screened
    against two different requests is two genuinely different labels, because
    feasibility includes `S3_peaking_match` and `S3_f_peak_match`, which are
    request-dependent. Collapsing them would merge a pass and a fail.
    """
    here = Path(here or HERE)
    rows: dict[tuple, dict] = {}
    for name in logs:
        p = here / name
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if '"u"' not in line:
                continue
            try:
                r = json.loads(line)
            except Exception:                                   # noqa: BLE001
                continue
            u = r.get("u")
            tp, tf = r.get("target_peaking_db"), r.get("target_f_peak_hz")
            if not u or len(u) != 7 or tp is None or tf is None:
                continue
            key = (tuple(round(float(x), 9) for x in u),
                   round(float(tp), 6), round(float(tf), 3))
            rec = rows.get(key)
            feas = bool(r.get("feasible"))
            if rec is None:
                rows[key] = {"u": [float(x) for x in u],
                             "target_peaking_db": float(tp),
                             "target_f_peak_hz": float(tf),
                             "feasible": feas, "sources": [name]}
            else:
                # a design screened twice against one target: a PASS anywhere
                # is a pass -- the screen is deterministic, so a disagreement
                # would be a real finding and is counted rather than hidden.
                rec["feasible"] = rec["feasible"] or feas
                if name not in rec["sources"]:
                    rec["sources"].append(name)
    return {"rows": list(rows.values())}


def features(u, target_peaking_db, target_f_peak_hz) -> np.ndarray:
    """`(design, requested spec) -> feature vector`. **No simulation.**

    Deliberately only what a proposer knows at deployment: the design vector
    and the request. Adding a measured quantity would make the ranker unusable
    for the job it exists for -- choosing between candidates *before* paying
    for them.
    """
    from nebula.experiments.exp_bc import spec_features

    u = np.atleast_2d(np.asarray(u, dtype=float))
    s = np.atleast_2d(spec_features(target_peaking_db, target_f_peak_hz))
    if s.shape[0] == 1 and u.shape[0] > 1:
        s = np.repeat(s, u.shape[0], axis=0)
    return np.hstack([u, s])


def dev_criterion(achieved_pk, achieved_f_hz, target_pk, target_f_hz):
    """**The library's OWN ranking rule**, imported in spirit from
    `exp_coverage.library_candidates` and restated here only because that
    function ranks a pool rather than scoring a candidate.

        dev = max(|f_oct - tgt_oct| / TOL[f_match], |pk - tgt| / TOL[pk_match])

    Q4 asks whether a learned ranker beats `-dev`. It is the honest baseline:
    within a fibre it is near-constant by construction, but ACROSS requests it
    carries real signal, so it is not a straw man.
    """
    import nebula.rl.reward_v1 as R

    f_oct = np.log2(np.asarray(achieved_f_hz, dtype=float) / 2.5e9)
    t_oct = np.log2(np.asarray(target_f_hz, dtype=float) / 2.5e9)
    return np.maximum(
        np.abs(f_oct - t_oct) / R.TOL["S3_f_peak_match"],
        np.abs(np.asarray(achieved_pk, dtype=float)
               - np.asarray(target_pk, dtype=float)) / R.TOL["S3_peaking_match"])


# --------------------------------------------------------------------------
# the model
# --------------------------------------------------------------------------

def make_model(seed: int = SEED):
    """Gradient boosting. **Not tuned** -- sklearn defaults except the seed and
    a class weight, because 4.5 % positives on 7 622 rows would otherwise be
    predicted away entirely."""
    from sklearn.ensemble import HistGradientBoostingClassifier

    return HistGradientBoostingClassifier(
        random_state=seed, class_weight="balanced")


def auc(y_true, score) -> Optional[float]:
    from sklearn.metrics import roc_auc_score

    y = np.asarray(y_true).astype(int)
    if y.min() == y.max():
        return None                      # undefined, and must not become 0.5
    return float(roc_auc_score(y, np.asarray(score, dtype=float)))


def leave_one_request_out(rows: Sequence[dict], seed: int = SEED) -> dict:
    """**Q1.** Train on 15 requests, score the held-out one, 16 times.

    A random split would leak: only 16 distinct spec targets exist in this
    data, and they are the same 16 the accept rate is measured on.
    """
    X = features([r["u"] for r in rows],
                 np.array([r["target_peaking_db"] for r in rows]),
                 np.array([r["target_f_peak_hz"] for r in rows]))
    y = np.array([r["feasible"] for r in rows], dtype=int)
    grp = np.array([f"{r['target_peaking_db']:.3f}@{r['target_f_peak_hz']:.0f}"
                    for r in rows])
    folds, oof = [], np.full(len(y), np.nan)
    for g in sorted(set(grp)):
        te = grp == g
        tr = ~te
        if y[tr].min() == y[tr].max() or te.sum() == 0:
            folds.append({"group": g, "n_test": int(te.sum()),
                          "n_pos_test": int(y[te].sum()), "auc": None,
                          "skipped": "training fold has one class"})
            continue
        m = make_model(seed)
        m.fit(X[tr], y[tr])
        s = m.predict_proba(X[te])[:, 1]
        oof[te] = s
        folds.append({"group": g, "n_test": int(te.sum()),
                      "n_pos_test": int(y[te].sum()), "auc": auc(y[te], s)})
    got = [f["auc"] for f in folds if f["auc"] is not None]
    ok = ~np.isnan(oof)
    return {"folds": folds, "n_folds": len(folds),
            "n_folds_scored": len(got),
            "mean_fold_auc": (float(np.mean(got)) if got else None),
            "median_fold_auc": (float(np.median(got)) if got else None),
            "pooled_oof_auc": auc(y[ok], oof[ok]),
            "n": int(len(y)), "n_pos": int(y.sum())}


# --------------------------------------------------------------------------
# the deployment test -- zero SPICE, on candidates already scored
# --------------------------------------------------------------------------

def scan_candidates(path: Path) -> list[dict]:
    """Already-scored candidates, with their TRUE feasibility."""
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    out = []
    for r in d.get("requests", []):
        for c in r.get("candidates", []):
            if "error" in c or not c.get("u"):
                continue
            out.append({"index": r["index"], "rank": c.get("rank"),
                        "u": [float(x) for x in c["u"]],
                        "target_peaking_db": float(r["peaking_db"]),
                        "target_f_peak_hz": float(r["f_peak_hz"]),
                        "feasible": bool(c.get("feasible")),
                        "peaking_db_got": c.get("peaking_db_got"),
                        "f_peak_hz_got": c.get("f_peak_hz_got")})
    return out


def rerank(model, cands: Sequence[dict]) -> dict:
    """**Q3.** Reorder each request's candidates by predicted feasibility and
    report where the true acceptances land.

    `rank_before` is the rank the scan actually deployed them at; `rank_after`
    is where the ranker would have put them. Zero simulations -- both orderings
    are over the same measured candidates.
    """
    by_req: dict[int, list] = {}
    for c in cands:
        by_req.setdefault(c["index"], []).append(c)
    out = []
    for idx, cs in sorted(by_req.items()):
        X = features([c["u"] for c in cs],
                     np.array([c["target_peaking_db"] for c in cs]),
                     np.array([c["target_f_peak_hz"] for c in cs]))
        s = model.predict_proba(X)[:, 1]
        order = np.argsort(-s)
        pos_before = [i + 1 for i, c in enumerate(cs) if c["feasible"]]
        pos_after = [int(np.where(order == i)[0][0]) + 1
                     for i, c in enumerate(cs) if c["feasible"]]
        out.append({"index": idx, "n_candidates": len(cs),
                    "n_feasible": len(pos_before),
                    "rank_before": pos_before, "rank_after": pos_after,
                    "best_before": (min(pos_before) if pos_before else None),
                    "best_after": (min(pos_after) if pos_after else None)})
    moved = [r for r in out if r["best_after"] is not None
             and r["best_before"] is not None
             and r["best_after"] < r["best_before"]]
    reached = [r for r in out if r["best_after"] is not None
               and r["best_after"] <= Q3_RANK_TARGET]
    return {"per_request": out, "n_with_feasible": sum(
                1 for r in out if r["n_feasible"]),
            "n_improved": len(moved),
            "n_reaching_rank_target": len(reached),
            "rank_target": Q3_RANK_TARGET}


def run(seed: int = SEED) -> dict:
    from nebula.experiments.runlock import stamp

    t0 = time.time()
    data = load_screened()
    rows = data["rows"]
    y = np.array([r["feasible"] for r in rows], dtype=int)
    print(f"corner-screened (design, target) pairs: {len(rows):,}   "
          f"feasible {int(y.sum()):,} ({100 * y.mean():.1f} %)")

    out: dict = {"task": "step 5B: is corner-robustness predictable without "
                         "simulation?", **stamp(), "seed": seed,
                 "n_pairs": int(len(rows)), "n_feasible": int(y.sum())}

    # ---- Q1 -------------------------------------------------------------
    print("\nQ1: leave-one-request-out ...", flush=True)
    out["Q1"] = leave_one_request_out(rows, seed=seed)
    q1 = out["Q1"]
    print(f"   {q1['n_folds_scored']} of {q1['n_folds']} folds scorable   "
          f"mean fold AUC {q1['mean_fold_auc']}   "
          f"pooled out-of-fold AUC {q1['pooled_oof_auc']}", flush=True)

    # ---- the deployment sets --------------------------------------------
    lib = scan_candidates(LIB_SCAN) if LIB_SCAN.exists() else []
    bc = scan_candidates(BC_SCAN) if BC_SCAN.exists() else []
    print(f"\nalready-scored candidates: library {len(lib)} "
          f"({sum(c['feasible'] for c in lib)} feasible), "
          f"BC {len(bc)} ({sum(c['feasible'] for c in bc)} feasible)")

    # ---- Q2: transfer, trained with NO BC design ------------------------
    X = features([r["u"] for r in rows],
                 np.array([r["target_peaking_db"] for r in rows]),
                 np.array([r["target_f_peak_hz"] for r in rows]))
    bc_keys = {tuple(np.round(c["u"], 9)) for c in bc}
    keep = np.array([tuple(np.round(r["u"], 9)) not in bc_keys for r in rows])
    model = make_model(seed)
    model.fit(X[keep], y[keep])
    out["n_train_transfer"] = int(keep.sum())
    out["n_excluded_as_bc"] = int((~keep).sum())

    if bc:
        Xb = features([c["u"] for c in bc],
                      np.array([c["target_peaking_db"] for c in bc]),
                      np.array([c["target_f_peak_hz"] for c in bc]))
        yb = np.array([c["feasible"] for c in bc], dtype=int)
        sb = model.predict_proba(Xb)[:, 1]
        out["Q2"] = {"n": int(len(yb)), "n_pos": int(yb.sum()),
                     "transfer_auc": auc(yb, sb)}
        print(f"\nQ2: transfer AUC on {len(yb)} BC candidates "
              f"({int(yb.sum())} positive) = {out['Q2']['transfer_auc']}",
              flush=True)

    # ---- Q3: would reranking have helped? -------------------------------
    if bc:
        out["Q3"] = rerank(model, bc)
        q3 = out["Q3"]
        print(f"Q3: of {q3['n_with_feasible']} requests with a feasible "
              f"candidate, {q3['n_improved']} improved, "
              f"{q3['n_reaching_rank_target']} reach rank "
              f"<= {q3['rank_target']}", flush=True)

    # ---- Q4: the kill switch --------------------------------------------
    pooled = lib + bc
    if pooled:
        Xp = features([c["u"] for c in pooled],
                      np.array([c["target_peaking_db"] for c in pooled]),
                      np.array([c["target_f_peak_hz"] for c in pooled]))
        yp = np.array([c["feasible"] for c in pooled], dtype=int)
        # the ranker must not have trained on ANY pooled candidate
        pk = {tuple(np.round(c["u"], 9)) for c in pooled}
        keep2 = np.array([tuple(np.round(r["u"], 9)) not in pk for r in rows])
        m2 = make_model(seed)
        m2.fit(X[keep2], y[keep2])
        s_model = m2.predict_proba(Xp)[:, 1]
        got = np.array([(c["f_peak_hz_got"] is not None) for c in pooled])
        s_dev = np.full(len(pooled), np.nan)
        if got.any():
            s_dev[got] = -dev_criterion(
                [pooled[i]["peaking_db_got"] for i in np.where(got)[0]],
                [pooled[i]["f_peak_hz_got"] for i in np.where(got)[0]],
                [pooled[i]["target_peaking_db"] for i in np.where(got)[0]],
                [pooled[i]["target_f_peak_hz"] for i in np.where(got)[0]])
        out["Q4"] = {
            "n_pooled": int(len(yp)), "n_pos": int(yp.sum()),
            "n_train": int(keep2.sum()),
            "model_auc": auc(yp, s_model),
            "model_auc_on_measurable": auc(yp[got], s_model[got]) if got.any() else None,
            "dev_auc_on_measurable": auc(yp[got], s_dev[got]) if got.any() else None,
            "n_measurable": int(got.sum()),
            "note": ("`dev` needs an ACHIEVED spec, so it can only be scored on "
                     "candidates the screen could measure. The model is scored "
                     "on the same subset for the comparison to be fair, and on "
                     "all pooled candidates separately.")}
        q4 = out["Q4"]
        print(f"\nQ4 (KILL SWITCH): on {q4['n_measurable']} measurable pooled "
              f"candidates -- model AUC {q4['model_auc_on_measurable']} vs "
              f"library `dev` AUC {q4['dev_auc_on_measurable']}", flush=True)

    out["wall_s"] = time.time() - t0
    out["score"] = _score(out)
    RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def _score(d: dict) -> dict:
    q: dict = {}
    q1 = d.get("Q1") or {}
    a1 = q1.get("pooled_oof_auc")
    q["Q1"] = {"pooled_oof_auc": a1, "threshold": Q1_AUC_MIN,
               "pass": bool(a1 is not None and a1 >= Q1_AUC_MIN)}
    q2 = d.get("Q2") or {}
    a2 = q2.get("transfer_auc")
    q["Q2"] = {"transfer_auc": a2, "threshold": Q2_TRANSFER_AUC_MIN,
               "pass": bool(a2 is not None and a2 >= Q2_TRANSFER_AUC_MIN)}
    q3 = d.get("Q3") or {}
    q["Q3"] = {"n_reaching_rank_target": q3.get("n_reaching_rank_target"),
               "pass": bool((q3.get("n_reaching_rank_target") or 0) >= 1)}
    q4 = d.get("Q4") or {}
    m, dv = q4.get("model_auc_on_measurable"), q4.get("dev_auc_on_measurable")
    q["Q4"] = {"model_auc": m, "dev_auc": dv,
               "pass": bool(m is not None and dv is not None and m > dv)}
    q["n_pass"] = sum(1 for k, v in q.items()
                      if k.startswith("Q") and v.get("pass"))
    q["n_scored"] = sum(1 for k in q if k.startswith("Q"))
    return q


def _report(d: dict) -> None:
    print()
    print("STEP 5B -- is corner-robustness predictable without simulation?")
    print(f"  {d['n_pairs']:,} (design, target) pairs, "
          f"{d['n_feasible']} feasible ({100*d['n_feasible']/d['n_pairs']:.1f} %)")
    s = d.get("score") or {}
    print()
    for k in ("Q1", "Q2", "Q3", "Q4"):
        if k in s:
            det = {kk: vv for kk, vv in s[k].items() if kk != "pass"}
            print(f"  {k}: {'PASS' if s[k]['pass'] else 'MISS'}   {det}")
    print(f"\n  SCORE {s.get('n_pass')} of {s.get('n_scored')}")
    print()
    print("  Q4 is the KILL SWITCH. If the ranker does not beat the library's")
    print("  own `dev` at ordering the same candidates, the fibre-selection")
    print("  diagnosis is wrong: stop, do not proceed to SAC on it.")
    print()
    print("  NOT an accept rate, NOT coverage, NOT compliance, and NOT an RL")
    print("  result -- this is a supervised ranker.")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--analyse", action="store_true")
    ap.add_argument("--seed", type=int, default=SEED)
    a = ap.parse_args(argv)
    if a.analyse:
        if not RESULTS.exists():
            raise SystemExit(f"{RESULTS.name} does not exist; --run first")
        _report(json.loads(RESULTS.read_text(encoding="utf-8")))
        return 0
    if not a.run:
        ap.print_help()
        return 0
    _report(run(seed=a.seed))
    return 0


if __name__ == "__main__":                                  # pragma: no cover
    raise SystemExit(main())
