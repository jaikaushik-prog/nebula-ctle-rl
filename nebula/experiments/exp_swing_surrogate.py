"""
experiments/exp_swing_surrogate.py -- **is output swing predictable without
SPICE? The go/no-go on a swing-aware reward.**

WHY THIS EXISTS
----------------
Entry 36 measured why SAC fails as a proposer, and the diagnosis is not a
guess: **SAC's failing designs score HIGHER on its training reward (median
+6.555) than the library designs that actually pass the screen (+6.530).** The
reward cannot separate a winner from a loser, because the quantity that does
95 % of the rejecting -- the measured 1 dB output-swing compression point --
is not in it and cannot be. `prescreen.predict_response` is a small-signal
frequency-response fit; compression is a large-signal effect.

There are two ways to put it in: SPICE-scored training (1.26 s/step against
0.0009, so 50 000 steps goes from ~23 min to ~17 h) or a **surrogate** that
predicts `vout_swing_v` from the design vector for free. This file measures
whether the second is available. **It is a go/no-go, not an improvement
attempt.** Pre-registered as `PREDICTIONS.md` entry 37.

THE DATA, AND THE THREAT TO IT
-------------------------------
Every sweep this project has run records `vout_swing_v` in the rejection reason
wherever a design compressed. Harvested and deduplicated on `u`, that is **2 228
unique designs**, 35..2147 mVpp.

**The sample is CENSORED and that is the central threat.** A limit is recorded
**only when the design's own required swing exceeded it**, so designs with
comfortable headroom are absent by construction -- the opposite of the region a
policy should be steered toward. The censoring threshold is not constant
(required swing varies with each design's gain, which is why limits up to
2 147 mV appear), but the bias is real and `--transfer` exists to expose it.

WHAT IS MEASURED, AND WHY THE SECOND SPLIT IS THE ONLY ONE THAT MATTERS
------------------------------------------------------------------------
    split A   random 70/30                      the optimistic reading
    split B   train on every NON-SAC design,    THE USE CASE: predicting swing
              test on the 245 a policy invented for designs a POLICY invents

Entry 36 measured that policy-generated designs sit in a different region of the
box (`i_bias` 0.27-0.44 against the library's 0.46, `rl` 0.45-0.56 against 0.70).
**A surrogate that passes A and fails B is useless for training a policy, and
would look fine to anyone who only ran A.**

NOTHING HERE MAY REACH A DELIVERABLE
--------------------------------------
This model predicts. It never replaces the measured value in scoring:
`link/calibration.py` goes on refusing to score a compressing stage, and
`is_surrogate = True` is stamped on every row this file writes.

    python -m nebula.experiments.exp_swing_surrogate --run
    python -m nebula.experiments.exp_swing_surrogate --analyse
"""

from __future__ import annotations

import argparse
import glob
import gzip
import json
import os
import re
import time
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "swing_surrogate_results.json"

SEED: int = 23_0826

#: Entry 37's thresholds. Changing one after the run is what `PREDICTIONS.md`
#: exists to prevent.
Q1_MAX_REL_ERR: float = 0.15
Q2_MAX_REL_ERR: float = 0.25
Q3_MIN_SPEARMAN: float = 0.80
Q4_MIN_AUC: float = 0.75

#: `vout_swing_v=NNN mVpp` is the design's own measured compression point; the
#: `exceeds the linear limit NNN mVpp` form is the same number in the older
#: message. Both are the TARGET; the first number in the message ("output swing
#: NNN mVpp") is the REQUIRED swing and must never be read as the target.
RX_LIMIT = re.compile(r"vout_swing_v=([\d.]+) mVpp")
RX_LIMIT_ALT = re.compile(r"exceeds the linear limit ([\d.]+) mVpp")

#: Which artifacts hold designs a POLICY invented. Split B holds these out.
SAC_SOURCES = ("topk_scan_sac_random_analytic", "topk_scan_sac_random_finetuned",
               "topk_scan_sac_seeded_analytic", "topk_scan_sac_seeded_finetuned")


def _limit_mv(reason: Optional[str]) -> Optional[float]:
    if not reason:
        return None
    m = RX_LIMIT.search(reason) or RX_LIMIT_ALT.search(reason)
    return float(m.group(1)) if m else None


def harvest(root: Optional[Path] = None) -> dict:
    """Every `(design -> MEASURED compression limit)` pair in the repo.

    Deduplicated on `u` rounded to 9 dp. **Without that dedup the same design,
    scored at four corners in three sweeps, lands in both train and test and
    every number this file reports is inflated** -- the oldest way to make a
    surrogate look good.
    """
    root = Path(root) if root is not None else HERE
    rows: dict = {}
    per_file: dict = {}

    def _add(u, mv: float, src: str) -> None:
        key = tuple(np.round(np.asarray(u, dtype=float), 9))
        per_file[src] = per_file.get(src, 0) + 1
        rows.setdefault(key, {"u": list(key), "limit_v": mv / 1000.0,
                              "source": src})

    for path in sorted(glob.glob(str(root / "*.jsonl"))) + \
            sorted(glob.glob(str(root / "*.jsonl.gz"))):
        opener = gzip.open if path.endswith(".gz") else open
        try:
            with opener(path, "rt", encoding="utf-8") as fh:
                for line in fh:
                    try:
                        d = json.loads(line)
                    except Exception:                           # noqa: BLE001
                        continue
                    mv = _limit_mv(d.get("reason"))
                    if mv is not None and "u" in d:
                        _add(d["u"], mv, os.path.basename(path))
        except Exception:                                       # noqa: BLE001
            continue

    for path in sorted(glob.glob(str(root / "*topk_scan*.json"))) + \
            sorted(glob.glob(str(root / "hybrid_*scan.json"))):
        try:
            d = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:                                       # noqa: BLE001
            continue
        for r in d.get("requests", []):
            for c in r.get("candidates", []):
                mv = _limit_mv(c.get("reason"))
                if mv is not None and "u" in c:
                    _add(c["u"], mv, Path(path).stem)

    return {"rows": list(rows.values()), "per_file": per_file}


def features(u) -> np.ndarray:
    """The registered feature set: seven physical parameters, three of them also
    in log10 because they span decades, plus `i_bias * rl`.

    **Nothing derived from a measurement**, so there is no path by which the
    target can leak into an input.
    """
    from nebula.rl.contract import sizing_from_u

    p = sizing_from_u(np.asarray(u, dtype=float)).params
    w, l = float(p["w_in"]), float(p["l_in"])
    ib, rs = float(p["i_bias"]), float(p["rs"])
    cs, rl = float(p["cs"]), float(p["rl"])
    vcm = float(p["vcm_in"])
    return np.array([w, l, ib, rs, cs, rl, vcm,
                     np.log10(max(ib, 1e-12)), np.log10(max(rs, 1e-12)),
                     np.log10(max(rl, 1e-12)), ib * rl], dtype=float)


FEATURE_NAMES = ("w_in", "l_in", "i_bias", "rs", "cs", "rl", "vcm_in",
                 "log10_i_bias", "log10_rs", "log10_rl", "i_bias*rl")


def _fit(Xtr, ytr, kind: str, seed: int = SEED):
    if kind == "gbr":
        from sklearn.ensemble import HistGradientBoostingRegressor
        m = HistGradientBoostingRegressor(random_state=seed)
    elif kind == "ridge":
        from sklearn.linear_model import Ridge
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
        m = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
    else:
        raise ValueError(f"unknown model {kind!r}")
    m.fit(Xtr, ytr)
    return m


def _scores(y, pred) -> dict:
    rel = np.abs(pred - y) / np.maximum(np.abs(y), 1e-9)
    from scipy.stats import spearmanr
    rho = float(spearmanr(y, pred).statistic) if len(y) > 2 else float("nan")
    return {"n": int(len(y)),
            "median_rel_err": float(np.median(rel)),
            "mean_rel_err": float(np.mean(rel)),
            "p90_rel_err": float(np.percentile(rel, 90)),
            "median_abs_err_mv": float(np.median(np.abs(pred - y)) * 1000.0),
            "spearman": rho}


def _auc(labels, scores) -> Optional[float]:
    """Rank-based AUC. `labels` 1 = screen-feasible, 0 = failed on swing."""
    labels = np.asarray(labels, dtype=int)
    if labels.sum() == 0 or labels.sum() == len(labels):
        return None
    from sklearn.metrics import roc_auc_score
    return float(roc_auc_score(labels, np.asarray(scores, dtype=float)))


def _verdict_rows(root: Path) -> list:
    """Candidates carrying a SCREEN verdict, for Q4.

    Only two classes are used: **screen-feasible** and **failed on swing**.
    Candidates that failed for another reason are excluded rather than folded
    into the negative class -- G107, "cannot be measured" is not "fails", and a
    pole-zero fit failure says nothing about swing.
    """
    out = []
    for path in sorted(glob.glob(str(root / "*topk_scan*.json"))):
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        for r in d.get("requests", []):
            for c in r.get("candidates", []):
                if "u" not in c:
                    continue
                if c.get("feasible"):
                    out.append({"u": c["u"], "label": 1})
                elif _limit_mv(c.get("reason")) is not None:
                    out.append({"u": c["u"], "label": 0})
    return out


def load_surrogate(seed: int = SEED, root: Optional[Path] = None):
    """The model `rl/swing_env.py` trains through. **Fitted on ALL rows.**

    Entry 37 validated on a transfer split -- train non-SAC, test the 245
    designs a policy invented -- and that is what justifies using the model at
    all (4.7 % median error, rho 0.993). **Deployment then fits on everything**,
    because holding data out of a model you have already validated buys nothing
    and the extra 245 rows are the ones closest to what a policy proposes.

    The validation split and this fit are deliberately different functions, so
    nobody can report a training fit's numbers as if they were held-out ones.
    """
    root = Path(root) if root is not None else HERE
    rows = harvest(root)["rows"]
    if len(rows) < 100:
        raise RuntimeError(
            f"only {len(rows)} labelled designs -- refusing to train a policy "
            f"through a surrogate fitted on noise (entry 37 used 2 228)")
    X = np.array([features(r["u"]) for r in rows])
    y = np.array([r["limit_v"] for r in rows])
    return _fit(X, y, "gbr", seed=seed), {"n_rows": len(rows),
                                          "is_surrogate": True}


def run(seed: int = SEED, root: Optional[Path] = None) -> dict:
    root = Path(root) if root is not None else HERE
    t0 = time.time()
    h = harvest(root)
    rows = h["rows"]
    if len(rows) < 100:
        raise RuntimeError(
            f"only {len(rows)} labelled designs found -- entry 37 was written "
            f"against 2 228. A harvest that collapses is a bug in the reader, "
            f"not a result about the data.")

    X = np.array([features(r["u"]) for r in rows])
    y = np.array([r["limit_v"] for r in rows])
    is_sac = np.array([any(s in r["source"] for s in SAC_SOURCES)
                       for r in rows])

    out: dict = {"task": "is output swing predictable without SPICE?",
                 "is_surrogate": True, "seed": int(seed),
                 "n_rows": int(len(rows)), "n_sac_rows": int(is_sac.sum()),
                 "per_file": h["per_file"],
                 "features": list(FEATURE_NAMES),
                 "limit_mv": {"min": float(y.min() * 1000),
                              "median": float(np.median(y) * 1000),
                              "max": float(y.max() * 1000)},
                 "splits": {}}

    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(rows))
    cut = int(0.7 * len(rows))
    tr_a, te_a = perm[:cut], perm[cut:]
    splits = {"A_random": (tr_a, te_a),
              "B_transfer_to_policy_designs": (np.where(~is_sac)[0],
                                               np.where(is_sac)[0])}

    models = {}
    for name, (tr, te) in splits.items():
        out["splits"][name] = {}
        for kind in ("gbr", "ridge"):
            m = _fit(X[tr], y[tr], kind, seed=seed)
            out["splits"][name][kind] = _scores(y[te], m.predict(X[te]))
            out["splits"][name][kind]["n_train"] = int(len(tr))
            if name == "B_transfer_to_policy_designs":
                models[kind] = m

    # ---- Q4: does the PRIMARY model separate pass from swing-failure? --------
    vr = _verdict_rows(root)
    if vr:
        Xv = np.array([features(r["u"]) for r in vr])
        lab = [r["label"] for r in vr]
        pred = models["gbr"].predict(Xv)
        out["q4"] = {"n": len(vr), "n_feasible": int(sum(lab)),
                     "n_swing_failed": int(len(lab) - sum(lab)),
                     "auc": _auc(lab, pred),
                     "note": ("trained on the non-SAC split, so the feasible "
                              "class is unseen AND uncensored -- the hardest "
                              "and the only honest form of this test")}
    else:
        out["q4"] = {"n": 0, "auc": None}

    out["wall_s"] = time.time() - t0
    out["verdict"] = _verdict(out)
    RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def _verdict(d: dict) -> dict:
    """Entry 37's decision rule, applied mechanically."""
    a = d["splits"]["A_random"]["gbr"]
    b = d["splits"]["B_transfer_to_policy_designs"]["gbr"]
    auc = (d.get("q4") or {}).get("auc")

    q1 = a["median_rel_err"] <= Q1_MAX_REL_ERR
    q2 = b["median_rel_err"] <= Q2_MAX_REL_ERR
    q3 = (not np.isnan(b["spearman"])) and b["spearman"] >= Q3_MIN_SPEARMAN
    q4 = auc is not None and auc >= Q4_MIN_AUC

    if q2 and q3:
        call = ("GO: the surrogate transfers to policy-generated designs on "
                "BOTH error and ordering. A swing-aware reward is affordable -- "
                "minutes of analytic training instead of ~17 h of SPICE-scored "
                "training. It is still a REWARD-SET CHANGE and therefore the "
                "OWNER's decision (standing rule 6), and the model would "
                "predict only: link/calibration.py goes on refusing to score a "
                "compressing stage, and no deliverable number comes from here.")
    elif q3:
        call = ("PARTIAL: ordering survives transfer, volts do not. The option "
                "is a RANK-SHAPED reward term, not a predicted-volts one. Do "
                "not fit further and do not quote this model's volts anywhere.")
    else:
        call = ("NO: the surrogate does not transfer to the designs a policy "
                "invents, which is the only use it would have had. A "
                "swing-aware reward needs SPICE-scored training or new labelled "
                "data in the UNCENSORED region -- designs that did NOT "
                "compress, which no artifact currently records. DO NOT fit a "
                "third model to rescue this (G110).")
    if not q4:
        call += (" Q4 MISSED: whatever the error numbers say, the predicted "
                 "limit does not separate screen-feasible designs from "
                 "swing-failures well enough to be a training signal on its "
                 "own.")
    return {"Q1_random_split": bool(q1), "Q2_transfer_error": bool(q2),
            "Q3_transfer_ordering": bool(q3), "Q4_decision_utility": bool(q4),
            "call": call}


def _report(d: dict) -> None:
    v = d["verdict"]
    print()
    print("=" * 78)
    print(f"SWING SURROGATE -- {d['n_rows']} labelled designs "
          f"({d['n_sac_rows']} policy-generated), "
          f"{d['limit_mv']['min']:.0f}..{d['limit_mv']['max']:.0f} mVpp")
    print("  NO SPICE. This model predicts; it never replaces a measurement.")
    print("=" * 78)
    print(f"  {'split':34s} {'model':6s} {'n_te':>5s} {'med rel':>8s} "
          f"{'p90 rel':>8s} {'med mV':>7s} {'rho':>6s}")
    for name, block in d["splits"].items():
        for kind, s in block.items():
            print(f"  {name:34s} {kind:6s} {s['n']:5d} "
                  f"{100*s['median_rel_err']:7.1f}% {100*s['p90_rel_err']:7.1f}% "
                  f"{s['median_abs_err_mv']:7.1f} {s['spearman']:6.3f}")
    q4 = d.get("q4") or {}
    if q4.get("auc") is not None:
        print(f"\n  Q4 separation: AUC {q4['auc']:.3f} on {q4['n_feasible']} "
              f"feasible vs {q4['n_swing_failed']} swing-failed")
    print()
    for k in ("Q1_random_split", "Q2_transfer_error", "Q3_transfer_ordering",
              "Q4_decision_utility"):
        print(f"  {'HIT ' if v[k] else 'MISS'}  {k}")
    print()
    print(f"  {v['call']}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--analyse", action="store_true")
    ap.add_argument("--seed", type=int, default=SEED)
    a = ap.parse_args(argv)
    if a.run:
        _report(run(seed=a.seed))
    elif a.analyse:
        if not RESULTS.exists():
            raise SystemExit(f"{RESULTS.name} missing: run --run first")
        _report(json.loads(RESULTS.read_text(encoding="utf-8")))
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":                                  # pragma: no cover
    raise SystemExit(main())
