"""experiments/exp_rwr.py -- **entry 45: reward-weighted regression. Offline RL
on 7 622 real corner outcomes, for zero new SPICE.**

WHAT CHANGES FROM BEHAVIOUR CLONING, AND WHY IT IS RL
-------------------------------------------------------
`exp_bc` fit 38 236 demonstrations with **equal weight**, learned the fibre's
density, and scored 2 of 16. Its diagnostic showed it held all 7 of the
library's accepted designs in its training set and had no reason to prefer
them: corner-robustness is a minority property and nothing in the
demonstrations marked it.

This module fits the **same** mixture with the **weights changed**. Every
design that was screened at four corners carries the outcome it earned, so the
**342 feasible designs dominate the gradient** and the 7 280 that failed are
pushed down. That is the policy-improvement step of RWR / AWR --
**offline reinforcement learning from a fixed dataset**, not imitation.

It is also the thing `rl/sac.py` exists for. Its own docstring: *"OFF-POLICY
and can therefore learn from simulations it did not run... This project has
74 526 already-simulated designs on disk and PPO can use NONE of them."* Entry
41 then declined to use them, for a stated reason that does not apply here --
it was rejecting replay transitions that carry a **different reward scale**,
whereas these carry the screen's own verdict.

THE TWO THINGS THAT WOULD HAVE MADE THIS MEANINGLESS
------------------------------------------------------
1. **The corner labels cover only 16 distinct spec targets, and they are the
   SAME 16 the accept rate is measured on.** Training on them and then scoring
   those requests is leakage. So every request gets its **own policy, trained
   with that request's labels removed** -- leave-one-request-out, 16 fits.
2. **No knob is tuned.** The upweight is the inverse frequency of a positive in
   the labelled set (7 622 / 342 = 22.3) -- derived from the data, the same
   rule `class_weight="balanced"` applies. There is no temperature and no
   lambda. Standing rule 6 forbids choosing one, and a tuned knob would make
   the number unreportable.

Pre-registered as `PREDICTIONS.md` entry 45 with Q1-Q5 and falsifiers, before
this file existed. **Q4 predicts it does NOT beat retrieval**, registered that
way so a hit cannot afterwards be told as an unexpected triumph.

    python -m nebula.experiments.exp_rwr --run          # train, zero SPICE
    python -m nebula.experiments.exp_rwr --propose      # 320 decks
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "rwr_results.json"
CKPT_DIR = HERE / "rwr_policies"

SEED: int = 23_0830
EPOCHS: int = 60
K: int = 5

#: Entry 32's baseline and entry 44's BC control, quoted so drift is visible.
BASELINE_LIBRARY_A: int = 6
BC_A: int = 2
BC_FEASIBLE_OF_80: int = 2

#: Entry 45's thresholds. **Not to be edited after the run** (G110).
Q1_CLOSER_FRACTION: float = 0.20
Q2_ACCEPT_MIN: int = 4
Q3_FEASIBLE_MIN: int = 3           # "beats BC's 2 of 80"
Q4_BEATS_RETRIEVAL: int = 7
Q5_MATCH_ROW_FRACTION: float = 0.50


def request_key(peaking_db: float, f_peak_hz: float) -> str:
    """One definition of a request's identity, used by every split here."""
    return f"{float(peaking_db):.3f}@{float(f_peak_hz):.0f}"


# --------------------------------------------------------------------------
# the weighted dataset
# --------------------------------------------------------------------------

def build_dataset(here: Optional[Path] = None) -> dict:
    """Demonstrations + corner outcomes, with the derived weights attached.

    Two populations, deliberately kept distinguishable in the artifact:

    * **38 236 unlabelled demonstrations** (`exp_harvest`) -- they carry no
      corner outcome and get weight 1. They are what stops the policy
      collapsing onto 16 specs: they cover all 100 cells of the box.
    * **7 622 corner-screened (design, target) pairs** -- 342 feasible. The
      feasible ones get the derived upweight; the rest keep weight 1.

    A design can appear in both. That is correct and not double counting: as a
    demonstration it teaches *what achieves this spec*, and as a labelled pair
    it teaches *whether it survives the corners*.
    """
    from nebula.experiments.exp_bc import load_demonstrations, spec_features
    from nebula.experiments.exp_rerank import load_screened

    here = Path(here or HERE)
    x_d, u_d, _ = load_demonstrations()
    rows = load_screened(here=here)["rows"]

    u_l = np.array([r["u"] for r in rows], dtype=float)
    pk_l = np.array([r["target_peaking_db"] for r in rows], dtype=float)
    f_l = np.array([r["target_f_peak_hz"] for r in rows], dtype=float)
    y_l = np.array([r["feasible"] for r in rows], dtype=bool)
    x_l = spec_features(pk_l, f_l)
    grp_l = np.array([request_key(p, f) for p, f in zip(pk_l, f_l)])

    n_pos = int(y_l.sum())
    if n_pos == 0:
        raise ValueError("no corner-feasible design in the label set; there is "
                         "nothing for a reward to weight")
    # **DERIVED, not chosen** -- the inverse frequency of a positive.
    upweight = float(len(y_l)) / float(n_pos)

    w_l = np.where(y_l, upweight, 1.0)
    return {
        "x_demo": x_d, "u_demo": u_d,
        "x_lab": x_l, "u_lab": u_l, "y_lab": y_l, "w_lab": w_l,
        "grp_lab": grp_l,
        "n_demo": int(len(u_d)), "n_lab": int(len(u_l)), "n_pos": n_pos,
        "upweight": upweight,
        "requests": sorted(set(grp_l)),
    }


def train_weighted(x, u, w, epochs: int = EPOCHS, seed: int = SEED,
                   verbose: bool = False):
    """The same mixture as `exp_bc`, fitted to a WEIGHTED likelihood.

    The only change from behaviour cloning is `w`. That is the whole method,
    and keeping it to one line is what makes the comparison honest.
    """
    import torch

    from nebula.experiments.exp_bc import BATCH, LR, _build

    torch.manual_seed(seed)
    model = _build("mdn")
    opt = torch.optim.Adam(model.parameters(), lr=LR)
    X = torch.as_tensor(np.asarray(x), dtype=torch.float32)
    U = torch.as_tensor(np.asarray(u), dtype=torch.float32)
    W = torch.as_tensor(np.asarray(w), dtype=torch.float32)
    W = W / W.mean()                      # scale-free: only ratios matter
    rng = np.random.default_rng(seed)
    n = len(U)
    for ep in range(epochs):
        perm = rng.permutation(n)
        for i in range(0, n, BATCH):
            b = perm[i:i + BATCH]
            # per-sample NLL, then the weighted mean. `loss` returns the mean,
            # so the weighting is applied by re-deriving per-sample terms.
            nll = model.loss(X[b], U[b], reduce=False)
            loss = (nll * W[b]).sum() / W[b].sum()
            opt.zero_grad(); loss.backward(); opt.step()
        if verbose and (ep + 1) % 20 == 0:
            print(f"      epoch {ep + 1}/{epochs}", flush=True)
    model.eval()
    return model


def leave_one_request_out(data: dict, epochs: int = EPOCHS,
                          seed: int = SEED) -> dict:
    """One policy per request, trained with that request's labels REMOVED.

    The unlabelled demonstrations are kept in every fold: they carry no corner
    outcome for the held-out request, so they cannot leak the answer, and
    without them the policy would see only 16 spec points.
    """
    CKPT_DIR.mkdir(exist_ok=True)
    out = []
    for g in data["requests"]:
        keep = data["grp_lab"] != g
        x = np.vstack([data["x_demo"], data["x_lab"][keep]])
        u = np.vstack([data["u_demo"], data["u_lab"][keep]])
        w = np.concatenate([np.ones(len(data["u_demo"])),
                            data["w_lab"][keep]])
        n_pos_train = int(data["y_lab"][keep].sum())
        print(f"    fold {g:26} train {len(u):,} "
              f"({n_pos_train} positives)", flush=True)
        model = train_weighted(x, u, w, epochs=epochs, seed=seed)
        import torch
        torch.save({"stage": "rwr", "kind": "mdn", "held_out": g,
                    "n_components": 8, "seed": seed,
                    "n_train": int(len(u)), "n_pos_train": n_pos_train,
                    "state_dict": model.state_dict()},
                   CKPT_DIR / f"rwr_{g.replace('@', '_')}.pt")
        out.append({"request": g, "n_train": int(len(u)),
                    "n_pos_train": n_pos_train,
                    "n_pos_held_out": int(data["y_lab"][~keep].sum())})
    return {"folds": out, "n_folds": len(out)}


# --------------------------------------------------------------------------
# Q1 -- did the weighting MOVE the policy? Zero SPICE.
# --------------------------------------------------------------------------

def movement(data: dict, seed: int = SEED, k: int = K) -> dict:
    """Distance from the policy's k proposals to that request's KNOWN-GOOD
    designs, RWR against BC, on held-out requests.

    **This is the wiring check.** If the weights did not move the policy, Q1
    misses and nothing downstream means anything -- entry 45 registers that as
    a defect to find, not a result to report.
    """
    import torch

    from nebula.experiments.exp_bc import CKPT as BC_CKPT
    from nebula.experiments.exp_bc_propose import load_generator

    bc, _ = load_generator(BC_CKPT, kind="mdn")
    rows = []
    for g in data["requests"]:
        here = data["grp_lab"] == g
        good = data["u_lab"][here & data["y_lab"]]
        if len(good) == 0:
            rows.append({"request": g, "n_good": 0, "skipped":
                         "no corner-feasible design for this request"})
            continue
        p = CKPT_DIR / f"rwr_{g.replace('@', '_')}.pt"
        if not p.exists():
            rows.append({"request": g, "missing_policy": True})
            continue
        ck = torch.load(p, map_location="cpu", weights_only=False)
        from nebula.experiments.exp_bc import _build
        rwr = _build("mdn"); rwr.load_state_dict(ck["state_dict"]); rwr.eval()

        x = torch.as_tensor(data["x_lab"][here][:1], dtype=torch.float32)
        d = {}
        for name, m in (("bc", bc), ("rwr", rwr)):
            s = m.sample(x, k=k).detach().numpy()[0]
            d[name] = float(min(np.linalg.norm(good - c, axis=1).min()
                                for c in s))
        rows.append({"request": g, "n_good": int(len(good)),
                     "bc_nearest_good": d["bc"], "rwr_nearest_good": d["rwr"],
                     "closer_fraction": (d["bc"] - d["rwr"]) / max(d["bc"], 1e-9)})
    got = [r for r in rows if "closer_fraction" in r]
    return {"per_request": rows, "n_scored": len(got),
            "median_closer_fraction": (float(np.median(
                [r["closer_fraction"] for r in got])) if got else None),
            "median_bc": (float(np.median([r["bc_nearest_good"] for r in got]))
                          if got else None),
            "median_rwr": (float(np.median([r["rwr_nearest_good"] for r in got]))
                           if got else None)}


def run(epochs: int = EPOCHS, seed: int = SEED) -> dict:
    from nebula.experiments.runlock import stamp

    t0 = time.time()
    data = build_dataset()
    print(f"demonstrations {data['n_demo']:,}   corner-labelled "
          f"{data['n_lab']:,} ({data['n_pos']} feasible)   "
          f"derived upweight x{data['upweight']:.1f}")
    print(f"\ntraining {len(data['requests'])} leave-one-request-out "
          f"policies ...", flush=True)
    folds = leave_one_request_out(data, epochs=epochs, seed=seed)
    print("\nQ1: did the weighting move the proposals?", flush=True)
    mv = movement(data, seed=seed)
    print(f"   median nearest-good: BC {mv['median_bc']}  ->  "
          f"RWR {mv['median_rwr']}   "
          f"({100 * (mv['median_closer_fraction'] or 0):.1f} % closer)",
          flush=True)
    out = {"task": "entry 45: reward-weighted regression, offline RL on real "
                   "corner outcomes", **stamp(), "seed": seed,
           "epochs": epochs, "n_demo": data["n_demo"], "n_lab": data["n_lab"],
           "n_pos": data["n_pos"], "upweight": data["upweight"],
           "folds": folds, "Q1": mv, "wall_s": time.time() - t0}
    RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"\nwrote {RESULTS.name}")
    return out


# --------------------------------------------------------------------------
# Q2/Q3/Q5 -- the accept rate. 320 decks.
# --------------------------------------------------------------------------

class LOROSource:
    """A `CandidateSource` that dispatches each request to the policy trained
    WITHOUT that request's corner labels.

    **This is the entire integrity of the experiment.** One policy for all 16
    requests would have seen every label and the accept rate would be
    memorisation. The source therefore refuses rather than falling back if a
    request has no matching checkpoint -- a silent fallback to some other
    policy is exactly the leak this protocol exists to prevent.
    """

    def __init__(self, ckpt_dir: Path = CKPT_DIR):
        self.dir = Path(ckpt_dir)
        self._cache: dict = {}
        self.notes: dict = {}

    def _policy(self, key: str):
        if key not in self._cache:
            import torch

            from nebula.experiments.exp_bc import _build

            p = self.dir / f"rwr_{key.replace('@', '_')}.pt"
            if not p.exists():
                raise FileNotFoundError(
                    f"no leave-one-out policy for request {key}. Scoring it "
                    f"with any other policy would use labels from the request "
                    f"being measured.")
            ck = torch.load(p, map_location="cpu", weights_only=False)
            if ck.get("held_out") != key:
                raise ValueError(
                    f"{p.name} was trained holding out {ck.get('held_out')!r}, "
                    f"not {key!r}. That checkpoint has seen this request.")
            m = _build("mdn")
            m.load_state_dict(ck["state_dict"])
            m.eval()
            self._cache[key] = (m, ck)
        return self._cache[key]

    def __call__(self, f_peak_hz: float, peaking_db: float, k: int) -> list:
        import torch

        from nebula.experiments.exp_bc import spec_features

        key = request_key(peaking_db, f_peak_hz)
        model, ck = self._policy(key)
        x = spec_features(float(peaking_db), float(f_peak_hz))[None, :]
        with torch.no_grad():
            s = model.sample(torch.as_tensor(x, dtype=torch.float32),
                             k=int(k)).numpy()[0]
        out = [np.clip(np.asarray(r, dtype=float), 0.0, 1.0) for r in s]
        self.notes[(float(f_peak_hz), float(peaking_db))] = {
            "held_out": ck.get("held_out"),
            "n_pos_train": ck.get("n_pos_train"),
            "n_distinct": len({tuple(np.round(r, 9)) for r in out})}
        return out


def propose(k: int = K) -> dict:
    """Score the leave-one-out policies through the SAME screen as everything
    else. 16 x k x 4 decks."""
    from nebula.experiments import exp_hybrid as H
    from nebula.experiments.exp_bc_propose import arm_summary
    from nebula.experiments.runlock import hold, stamp

    t0 = time.time()
    src = LOROSource()
    H.CANDIDATE_SOURCES["rwr_loro"] = src
    with hold("rwr_propose", meta={"k": k}):
        dest = HERE / "topk_scan_rwr_loro.json"
        scan = H.scan_topk(source="rwr_loro", k=int(k), out=dest)
        s = arm_summary("rwr_loro", scan, src.notes)

        # Q5: where do the non-feasible candidates fail?
        rows = {}
        for r in scan.get("requests", []):
            for c in r.get("candidates", []):
                if "error" in c or c.get("feasible"):
                    continue
                rows[c.get("worst_spec") or "unscorable"] =                     rows.get(c.get("worst_spec") or "unscorable", 0) + 1
        nf = sum(rows.values())
        match = rows.get("S3_f_peak_match", 0) + rows.get("S3_peaking_match", 0)
        out = {"task": "entry 45 Q2/Q3/Q5: accept rate of the "
                       "leave-one-request-out RWR policies", **stamp(),
               "k": int(k), "arm": s, "failure_rows": rows,
               "n_non_feasible": nf,
               "match_row_fraction": (match / nf) if nf else None,
               "baseline_library_A": BASELINE_LIBRARY_A, "bc_A": BC_A,
               "bc_feasible_of_80": BC_FEASIBLE_OF_80,
               "wall_s": time.time() - t0}
        out["score"] = {
            "Q2": {"A": s["n_accepted"], "threshold": Q2_ACCEPT_MIN,
                   "pass": s["n_accepted"] >= Q2_ACCEPT_MIN},
            "Q3": {"n_feasible": s["n_cand_feasible"],
                   "threshold": Q3_FEASIBLE_MIN,
                   "pass": s["n_cand_feasible"] >= Q3_FEASIBLE_MIN},
            "Q4": {"A": s["n_accepted"], "beats_retrieval_at": Q4_BEATS_RETRIEVAL,
                   "pass": s["n_accepted"] < Q4_BEATS_RETRIEVAL},
            "Q5": {"match_row_fraction": out["match_row_fraction"],
                   "threshold": Q5_MATCH_ROW_FRACTION,
                   "pass": (out["match_row_fraction"] is not None
                            and out["match_row_fraction"] < Q5_MATCH_ROW_FRACTION)}}
        p = HERE / "rwr_propose_results.json"
        p.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"\n  A = {s['n_accepted']} of 16   accepted_at_k "
          f"{s['accepted_at_k']}   feasible {s['n_cand_feasible']} of 80")
    print(f"  library {BASELINE_LIBRARY_A} of 16   BC {BC_A} of 16 "
          f"({BC_FEASIBLE_OF_80} feasible of 80)")
    print(f"  failures: {rows}")
    for q, v in out["score"].items():
        print(f"  {q}: {'PASS' if v['pass'] else 'MISS'}  {v}")
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true", help="train, zero SPICE")
    ap.add_argument("--propose", action="store_true",
                    help="score the LORO policies, 320 decks")
    ap.add_argument("--epochs", type=int, default=EPOCHS)
    ap.add_argument("--seed", type=int, default=SEED)
    a = ap.parse_args(argv)
    if a.propose:
        propose()
        return 0
    if not a.run:
        ap.print_help()
        return 0
    run(epochs=a.epochs, seed=a.seed)
    return 0


if __name__ == "__main__":                                  # pragma: no cover
    raise SystemExit(main())
