"""experiments/exp_bc_propose.py -- **step 4: the accept rate. Does the learned
generator match the library it replaces?**

THE BAR, AND IT IS NOT ZERO
-----------------------------
Entry 32 measured the non-RL library proposer at **A = 6 of 16** on the
coverage grid at k=5, 260 decks deployed. Every RL arm since has been scored
against it and lost:

    library (retrieval)        6 of 16      entry 32, reproduced in entries 36 and 41
    SAC analytic / finetuned   0-2 of 16    entry 36
    SAC + swing-aware reward   0-1 of 16    entry 38
    SAC on the screen itself   0 of 16      entry 41

This module scores the **behaviour-cloned mixture generator** through the SAME
`exp_hybrid.scan_topk`, the same 4-corner screen, the same `V6_SPECS`, the same
accept rule -- so there is exactly one definition of "accepted" (rule 9) and the
number is directly comparable to all four rows above.

WHAT WOULD MAKE THIS WORTH SHIPPING
-------------------------------------
**Not beating the library. Matching it.** A network that generates 6-of-16
designs from a 2-D spec has replaced a 74 526-row lookup table with 97 400
weights, and it is differentiable -- which is what lets step 5 fine-tune it on
the corner reward. Retrieval cannot be fine-tuned.

And the fibre measurement in `exp_bc` says why that matters: within +-0.25 dB
and +-0.02 oct there are a median of **252** demonstrations spanning **1.638**
of a 2.646 box, and the library ranks them on `|achieved - target|`, which is
near-constant across that whole set. **Retrieval picks arbitrarily inside a 5-D
fibre.** Choosing WHERE in the fibre to land is the decision RL is for, and a
generator is the thing that can be taught to make it.

THE CONTROL ARM IS THE POINT OF THE COMPARISON
------------------------------------------------
`mlp` is scored beside `mdn` because `exp_bc` measured it producing the
**identical design for every k** -- 8 candidates, one design, 32 decks. If that
shows up here as a much lower accept rate at the same deck cost, the
architecture choice is measured rather than argued.

    python -m nebula.experiments.exp_bc_propose --run
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "bc_propose_results.json"
CKPT = HERE / "bc_policy.pt"
CKPT_MLP = HERE / "bc_policy_mlp.pt"

K: int = 5
SEED: int = 23_0830

#: Entry 32's measured baseline, quoted so a drift in either is visible.
BASELINE_ACCEPTED_AT_K: tuple[int, ...] = (1, 4, 5, 5, 6)
BASELINE_A: int = 6
BASELINE_DEPLOYED_DECKS: int = 260


def load_generator(path: Path = CKPT, kind: Optional[str] = None):
    """A trained generator from `exp_bc`. **Raises on a checkpoint of nothing.**

    `exp_sac_propose.load_agent`'s lesson (G113's shape): a file of the right
    name and roughly the right size holding no weights produces an honest
    accept rate for a policy that never existed.
    """
    import torch

    from nebula.experiments.exp_bc import _build

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"{p} is missing. It is written by `exp_bc --run`, which needs "
            f"`demonstrations.npz` from `exp_harvest --run`.")
    ck = torch.load(p, map_location="cpu", weights_only=False)
    if kind is not None and ck.get("kind") not in (None, kind):
        raise ValueError(
            f"{p.name} holds a {ck.get('kind')!r} checkpoint but a {kind!r} "
            f"model was asked for. Loading one architecture's weights into "
            f"another is how a control silently becomes a copy of the arm it "
            f"is supposed to contradict.")
    sd = ck.get("state_dict")
    if not sd:
        raise ValueError(f"{p.name} carries no state_dict -- it is a "
                         f"checkpoint of nothing.")
    model = _build(kind or ck.get("kind", "mdn"),
                   n_components=int(ck.get("n_components", 8)))
    model.load_state_dict(sd)
    model.eval()
    return model, {"kind": ck.get("kind"), "stage": ck.get("stage"),
                   "n_components": ck.get("n_components"),
                   "n_demonstrations": ck.get("n_demonstrations")}


class BCSource:
    """A `CandidateSource` in `exp_hybrid`'s sense: `(f_peak_hz, peaking_db, k)
    -> [u, ...]`. **Zero SPICE** -- the caller pays 4 decks per candidate it
    chooses to score, exactly as it does for the library."""

    def __init__(self, model, label: str = "bc"):
        self.model = model
        self.label = label
        self.notes: dict = {}

    def __call__(self, f_peak_hz: float, peaking_db: float, k: int) -> list:
        import torch

        from nebula.experiments.exp_bc import spec_features

        x = spec_features(float(peaking_db), float(f_peak_hz))[None, :]
        with torch.no_grad():
            s = self.model.sample(torch.as_tensor(x, dtype=torch.float32),
                                  k=int(k)).numpy()[0]
        out = [np.clip(np.asarray(r, dtype=float), 0.0, 1.0) for r in s]
        # **How many of the k are genuinely different designs.** `exp_bc`
        # measured the MLP returning one design k times; if that reaches the
        # screen it spends 4k decks to ask one question, and the artifact must
        # say so rather than the accept rate quietly absorbing it.
        uniq = len({tuple(np.round(r, 9)) for r in out})
        self.notes[(float(f_peak_hz), float(peaking_db))] = {
            "n_proposed": len(out), "n_distinct": uniq}
        return out


def arm_summary(name: str, scan: dict, notes: dict) -> dict:
    ranks = [r.get("accepted_rank") for r in scan["requests"]]
    sw = tot = 0
    nsc = []
    for r in scan.get("requests", []):
        for c in r.get("candidates", []):
            if "error" in c:
                continue
            if c.get("n_scorable") is not None:
                nsc.append(c["n_scorable"])
            if c.get("feasible"):
                continue
            tot += 1
            if "output swing" in (c.get("reason") or ""):
                sw += 1
    d = [v["n_distinct"] for v in notes.values()] if notes else []
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
        "mean_scorable_corners": (float(np.mean(nsc)) if nsc else None),
        "median_distinct_of_k": (float(np.median(d)) if d else None),
        "min_distinct_of_k": (int(min(d)) if d else None),
        "artifact": scan.get("artifact"),
        "wall_clock_s": float(scan["wall_clock_s"]),
    }


def run(k: int = K, seed: int = SEED, arms: Sequence[str] = ("mdn", "mlp"),
        ckpt: Path = CKPT) -> dict:
    from nebula.experiments import exp_hybrid as H
    from nebula.experiments.runlock import hold, stamp

    t0 = time.time()
    out: dict = {"task": "step 4: accept rate for the behaviour-cloned "
                         "generator, against entry 32's non-RL 6 of 16",
                 **stamp(), "k": int(k), "seed": int(seed),
                 "baseline": {"accepted_at_k": list(BASELINE_ACCEPTED_AT_K),
                              "n_accepted": BASELINE_A,
                              "n_sims_deployed": BASELINE_DEPLOYED_DECKS,
                              "source": "entry 32, hybrid_topk_scan.json",
                              "rerun_here": False},
                 "arms": []}

    sources = {}
    for kind in arms:
        # each arm loads ITS OWN checkpoint; loading the mixture's weights
        # into the regressor is a silent shape error at best (measured: it
        # raises) and a wrong control at worst.
        path = CKPT if kind == "mdn" else CKPT_MLP
        model, meta = load_generator(path, kind=kind)
        name = f"bc_{kind}"
        sources[name] = BCSource(model, label=name)
        out.setdefault("checkpoint", meta)
    H.CANDIDATE_SOURCES.update(sources)

    with hold("bc_propose", meta={"arms": list(arms), "k": k}):
        for name, src in sources.items():
            print(f"\n=== arm {name}, k={k}, {16 * k * 4} decks ===", flush=True)
            dest = HERE / f"topk_scan_{name}.json"
            scan = H.scan_topk(source=name, k=int(k), out=dest)
            s = arm_summary(name, scan, src.notes)
            out["arms"].append(s)
            print(f"  {name}: A = {s['n_accepted']} of 16   "
                  f"accepted_at_k {s['accepted_at_k']}   "
                  f"distinct of k: median {s['median_distinct_of_k']}, "
                  f"min {s['min_distinct_of_k']}   "
                  f"scorable {s['mean_scorable_corners']}", flush=True)
        out["wall_s"] = time.time() - t0
        RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def _report(d: dict) -> None:
    print()
    print("STEP 4 -- accept rate, the learned generator against retrieval")
    print(f"  baseline (entry 32, library k=5): A = {d['baseline']['n_accepted']}"
          f" of 16   {d['baseline']['accepted_at_k']}")
    print()
    print(f"  {'arm':10} {'A':>3}  {'accepted_at_k':18} {'distinct/k':>11} "
          f"{'scorable/4':>11} {'decks':>7}")
    for a in d["arms"]:
        sc = a.get("mean_scorable_corners")
        print(f"  {a['arm']:10} {a['n_accepted']:3d}  "
              f"{str(a['accepted_at_k']):18} "
              f"{a['median_distinct_of_k']!s:>11} "
              f"{('%.2f' % sc) if sc is not None else '--':>11} "
              f"{a['n_sims_deployed']:7d}")
    print()
    print("  'distinct/k' is how many of the k proposals are DIFFERENT designs.")
    print("  A deterministic regressor returns one design k times and spends")
    print("  4k decks asking one question.")
    print()
    print("  Accept rate is a PROPOSAL metric on 4 corners. It is NOT coverage")
    print("  (8 of 16, entry 40) and NOT compliance.")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--analyse", action="store_true")
    ap.add_argument("--k", type=int, default=K)
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
    _report(run(k=a.k, seed=a.seed))
    return 0


if __name__ == "__main__":                                  # pragma: no cover
    raise SystemExit(main())
