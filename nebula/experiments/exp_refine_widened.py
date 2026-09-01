"""
experiments/exp_refine_widened.py — **entry 57: give the policy the control's
SPREAD and ask whether its learned DIRECTION is worth anything.**

    python -m nebula.experiments.exp_refine_widened --run
    python -m nebula.experiments.exp_refine_widened --analyse

THE MECHANISM, MEASURED RATHER THAN DESCRIBED
-----------------------------------------------
Entries 47 and 48 established the failure and named its cause, and the cause is
a number in the committed checkpoint:

    sigma  [0.2559 0.3040 0.1656 0.0487 0.0530 0.0810 0.4871]
            w_in   l_in   i_bias rs     cs     rl     vcm_in

Uniform on the tanh-bounded action box -- **arm B's own action distribution** --
has standard deviation `1/sqrt(3) = 0.5774`. So the trained policy explores
**11.85x narrower than the control on `rs`** and **10.90x on `cs`**, the two
knobs that set the `Rs x Cs` peak. The shared selector is best-of-visited,
which pays for the spread of what was visited, and every arm so far is exactly
what that predicts:

    A  policy MEAN      1x8     5 / 58    no spread at all
    D  policy SAMPLED   1x8    10 / 58    its own narrow spread
    E  policy SAMPLED   4x2    12 / 58    +19 % budget, NOT matched
    B  uniform RANDOM   1x8    13 / 58    full spread

More spread moved the policy up every time. **None reached the control.**

WHAT ARM F IS
--------------
The policy's **mean** action plus Gaussian noise of standard deviation
**`1/sqrt(3)`**, clipped to the same `[-1, 1]` box. `1 x 8`, one trajectory,
the same 58 requests, the same seeds, the same start, the same selector.

So the only thing left differing between F and B is **where the centre of the
cloud sits** -- which is precisely the learned direction, and precisely the
thing that has never been shown to be worth anything.

THE SPREAD IS DERIVED, NOT CHOSEN, AND THIS MUST NOT BECOME A SWEEP
--------------------------------------------------------------------
`SPREAD` is the standard deviation of **arm B's own actions**. It is the one
value that equalises the registered mechanism between the two arms; it was not
picked because it worked, and it was fixed before the run. **A later run at
0.2, 0.3, 0.4 would be tuning and would make this result unreportable**
(standing rule 6). If the answer is "no", the answer is no.

NOTHING IS RETRAINED. Same checkpoint, same `max_step` 0.04, same reward, same
screen, same `V6_SPECS`, same eligible set. The policy is read differently, not
changed.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from nebula.experiments.exp_refine_control import (
    RESULTS as CONTROL_RESULTS, eligible,
)
from nebula.experiments.exp_refine_sampled import (
    RESULTS as SAMPLED_RESULTS,
)
from nebula.experiments.exp_rl_refine import (
    REFINE_MAX_STEP, SEED, refine_one, sign_test_p, wilson_ci,
)

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "refine_widened_results.json"
RUN_LOG = HERE / "refine_widened_run.jsonl"

#: **The standard deviation of a uniform distribution on [-1, 1]** -- i.e. of
#: arm B's own action, the control this arm is measured against. Registered in
#: entry 57 and NOT swept: it is the value that makes "diversity" equal between
#: F and B so that the only remaining difference is the learned centre.
SPREAD: float = 1.0 / math.sqrt(3.0)


def widened_actor(net, spread: float = SPREAD):
    """Arm F. The policy's MEAN, with the CONTROL's spread around it.

    Not `distribution(o).sample()` -- that is arm D, and it samples the
    policy's own sigma, which is the quantity under suspicion. Not
    `rng.uniform(-1, 1)` -- that is arm B, and it discards the policy
    entirely. This is the one combination that isolates the learned direction:
    B's spread, the policy's centre.

    Clipped to `[-1, 1]` because that is the box both other arms live in. The
    clip slightly reduces the realised standard deviation near the edges, which
    is stated rather than corrected: correcting it would mean choosing a
    `spread` bigger than the control's, and the whole point is that this number
    is the control's and was not chosen.
    """
    import torch

    def _act(obs, rng):
        with torch.no_grad():
            o = torch.as_tensor(obs, dtype=torch.float32).unsqueeze(0)
            mean = net.distribution(o).mean.squeeze(0).numpy()
        return np.clip(mean + rng.normal(0.0, spread, size=mean.shape),
                       -1.0, 1.0)

    return _act


def prior_arms() -> dict:
    """Arms A, B and D per request. **Read, never re-run.**

    Keyed by the request's original index, which is what makes the comparison
    paired: F is scored against A, B and D on the very same request from the
    very same start. Re-running them here would be a second measurement of the
    same thing under different conditions.
    """
    for p in (CONTROL_RESULTS, SAMPLED_RESULTS):
        if not p.exists():
            raise SystemExit(
                f"{p.name} is missing. Entry 57 is scored AGAINST entries 47 "
                f"and 48, so both must be on disk before this runs.")
    ctrl = {int(r["index"]): r
            for r in json.loads(CONTROL_RESULTS.read_text(encoding="utf-8"))["rows"]}
    samp = {int(r["index"]): r
            for r in json.loads(SAMPLED_RESULTS.read_text(encoding="utf-8"))["rows"]}
    out = {}
    for i, r in ctrl.items():
        if i in samp:
            out[i] = {**r, "D_delta": samp[i]["D_delta"],
                      "D_crossed": samp[i]["D_crossed"],
                      "D_decks": samp[i]["D_decks"]}
    return out


def run(n: Optional[int] = None, seed: int = SEED) -> dict:
    import torch                                            # noqa: F401

    from nebula.experiments.exp_rl_refine import _load_policy
    from nebula.experiments.runlock import hold, stamp
    from nebula.rl.spec_dist import SpecTarget

    with hold("refine_widened"):
        t0 = time.time()
        prior = prior_arms()
        targets = [t for t in eligible() if t["index"] in prior]
        if n is not None:
            targets = targets[:int(n)]
        net, ck = _load_policy(7 + 8 + 2 + 1, 7, seed)
        print(f"entry 57: {len(targets)} requests, arm F (1x8, policy mean + "
              f"spread {SPREAD:.4f}), max_step={REFINE_MAX_STEP}", flush=True)

        rows: list[dict] = []
        with RUN_LOG.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps({"event": "start", "seed": seed,
                                 "spread": SPREAD, "n": len(targets),
                                 **stamp()}) + "\n")
            for k, t in enumerate(targets):
                tgt = SpecTarget(peaking_db=t["peaking_db"],
                                 f_peak_hz=t["f_peak_hz"])
                f_ = refine_one(net, tgt, seed=t["seed"],
                                actor=widened_actor(net))
                c = prior[t["index"]]
                row = {
                    "index": t["index"], "peaking_db": t["peaking_db"],
                    "f_peak_hz": t["f_peak_hz"],
                    "A_delta": c["A_delta"], "A_crossed": c["A_crossed"],
                    "A_decks": c["A_decks"],
                    "B_delta": c["B_delta"], "B_crossed": c["B_crossed"],
                    "B_decks": c["B_decks"],
                    "D_delta": c["D_delta"], "D_crossed": c["D_crossed"],
                    "D_decks": c["D_decks"],
                    "F_delta": f_.delta, "F_crossed": f_.improved,
                    "F_decks": f_.pol_sims, "F_steps": f_.n_steps,
                    # Q1: the same start as entries 47 and 48, componentwise.
                    "same_start": bool(f_.lib_u is not None),
                    "lib_reward": f_.lib_reward,
                }
                rows.append(row)
                fh.write(json.dumps(row) + "\n")
                fh.flush()
                print(f"[{k + 1}/{len(targets)}] {t['peaking_db']:5.2f} dB @ "
                      f"{t['f_peak_hz'] / 1e9:.3f} GHz   "
                      f"A {c['A_delta']:+8.4f}{'*' if c['A_crossed'] else ' '} "
                      f"B {c['B_delta']:+8.4f}{'*' if c['B_crossed'] else ' '} "
                      f"D {c['D_delta']:+8.4f}{'*' if c['D_crossed'] else ' '} "
                      f"F {f_.delta:+8.4f}{'*' if f_.improved else ' '}  "
                      f"decks {f_.pol_sims}", flush=True)

        out = _summarise(rows)
        out.update({"task": "entry 57: the control's spread, the policy's mean",
                    **stamp(), "seed": seed, "spread": SPREAD,
                    "policy_steps": ck["steps"], "max_step": REFINE_MAX_STEP,
                    "wall_clock_s": time.time() - t0, "rows": rows})
        RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
        return out


def _summarise(rows: Sequence[dict]) -> dict:
    """Score entry 57's five questions. Thresholds are the registered ones."""
    n = len(rows)
    out: dict = {"n": n}
    for arm in ("A", "B", "D", "F"):
        cr = sum(1 for r in rows if r[f"{arm}_crossed"])
        lo, hi = wilson_ci(cr, n) if n else (0.0, 0.0)
        out[arm] = {
            "crossings": cr, "cross_rate": cr / n if n else 0.0,
            "cross_ci95": [lo, hi],
            "moved_up": sum(1 for r in rows if r[f"{arm}_delta"] > 1e-9),
            "moved_down": sum(1 for r in rows if r[f"{arm}_delta"] < -1e-9),
            "mean_decks": float(np.mean([r[f"{arm}_decks"] for r in rows]))
            if n else 0.0}

    def _mc(x: str, y: str) -> dict:
        ox = sum(1 for r in rows if r[f"{x}_crossed"] and not r[f"{y}_crossed"])
        oy = sum(1 for r in rows if r[f"{y}_crossed"] and not r[f"{x}_crossed"])
        return {"only_" + x: ox, "only_" + y: oy, "p": sign_test_p(ox, oy)}

    a_decks = out["A"]["mean_decks"] or 1.0
    pct = 100.0 * (out["F"]["mean_decks"] - a_decks) / a_decks
    out["Q1_control"] = {
        "n_same_start": sum(1 for r in rows if r["same_start"]), "n": n,
        "reproduced": all(r["same_start"] for r in rows) if n else False}
    out["Q2_F_vs_B"] = {**_mc("F", "B"),
                        "hit": out["F"]["crossings"] >= out["B"]["crossings"]}
    out["Q3_F_vs_D"] = {**_mc("F", "D"),
                        "hit": out["F"]["crossings"] > out["D"]["crossings"]}
    out["Q4_budget"] = {"mean_decks": out["F"]["mean_decks"],
                        "vs_A_pct": pct, "hit": abs(pct) <= 10.0}
    out["Q5_expected_null"] = {"p": out["Q2_F_vs_B"]["p"],
                               "hit": out["Q2_F_vs_B"]["p"] >= 0.05}
    out["n_hit"] = sum(int(out[q]["hit"] if "hit" in out[q]
                           else out[q]["reproduced"])
                       for q in ("Q1_control", "Q2_F_vs_B", "Q3_F_vs_D",
                                 "Q4_budget", "Q5_expected_null"))
    return out


def _report(d: dict) -> None:
    n = d["n"]
    print()
    print("=" * 78)
    print("ENTRY 57 -- the control's spread, the policy's mean")
    print("=" * 78)
    print(f"  {n} requests, spread {d.get('spread', SPREAD):.4f}, "
          f"max_step {d.get('max_step')}")
    print()
    print("  arm                       crossed    up  down   decks")
    for arm, label in (("A", "policy MEAN     1x8"),
                       ("D", "policy SAMPLED  1x8"),
                       ("F", "policy + B's SD 1x8"),
                       ("B", "uniform random  1x8")):
        a = d[arm]
        print(f"  {arm}  {label:22} {a['crossings']:3}/{n}  "
              f"{a['moved_up']:4} {a['moved_down']:4}   {a['mean_decks']:5.1f}")
    print()
    for q in ("Q1_control", "Q2_F_vs_B", "Q3_F_vs_D", "Q4_budget",
              "Q5_expected_null"):
        v = d[q]
        hit = v.get("hit", v.get("reproduced"))
        print(f"    {q:20} {'HIT' if hit else 'MISS':4}  "
              + json.dumps({k: (round(x, 4) if isinstance(x, float) else x)
                            for k, x in v.items()
                            if k not in ("hit", "reproduced")}))
    print(f"    scored {d.get('n_hit')} of 5")
    print()
    print(f"  wall clock {d.get('wall_clock_s', 0.0):.1f} s")
    print()


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--analyse", action="store_true")
    ap.add_argument("-n", type=int, default=None,
                    help="first N requests only (a smoke run, not the entry)")
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args(argv)

    if args.run:
        _report(run(n=args.n, seed=args.seed))
        return 0
    if args.analyse:
        if not RESULTS.exists():
            print(f"no artifact at {RESULTS}")
            return 1
        _report(json.loads(RESULTS.read_text(encoding="utf-8")))
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
