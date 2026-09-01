"""
experiments/exp_refine_sampled.py — **entry 48: the policy outputs a
distribution and we only ever asked for its mean.**

    python -m nebula.experiments.exp_refine_sampled --run
    python -m nebula.experiments.exp_refine_sampled --analyse

THE DIAGNOSIS THIS FILE TESTS
-------------------------------
Entry 47 measured the trained policy crossing far less often than uniform
random at a matched budget. A trained policy losing to noise on its own task is
a **symptom**, and the checkpoint names the cause:

    log_std  [-1.363 -1.191 -1.798 -3.022 -2.938 -2.514 -0.719]
    sigma    [ 0.256  0.304  0.166  0.049  0.053  0.081  0.487]
              w_in   l_in   i_bias  rs     cs     rl     vcm_in

`log_std` **started at 0.0** and shrank to **0.049 on `rs`** and **0.053 on
`cs`** -- the two knobs that set the `Rs x Cs` peak. The policy learned a
direction *and* a confidence. And `refine_one`'s default reads:

    a = net.distribution(o).mean          # sigma is DISCARDED

So the policy arm walks **one deterministic path** while the random arm takes
eight scattered steps, and the shared best-of-visited selector pays for
**diversity of samples**. The comparison was never about policy quality. It was
about sample count.

THE FOUR ARMS
--------------
    A  policy MEAN      1 x 8   read from entry 47, not re-run
    B  uniform random   1 x 8   read from entry 47, not re-run
    D  policy SAMPLED   1 x 8   isolates sampling ALONE
    E  policy SAMPLED   4 x 2   sampling AND diversity

**D exists so the two halves of the fix stay separable.** If sampling alone
were enough, D would reach B. If diversity is what matters, only E moves.

NOTHING IS RETRAINED. Same checkpoint, same `max_step` 0.04, same reward, same
screen, same `V6_SPECS`. `R = 4` is registered in entry 48 and **not swept** --
a sweep over R would be tuning (rule 6).

THE START IS MEASURED ONCE, NOT ONCE PER RESTART
--------------------------------------------------
`env.reset(u0)` re-evaluates the start (~4 decks) and every restart returns to
the *same* start, whose evaluation is deterministic. Paying R times would spend
half a 30-deck budget re-learning an identical fact and starve the very arm
under test. `refine_one`'s restart seam restores `(_u, _step)` and replays the
first observation instead -- bit-identical state, zero decks. See entry 48 Q5,
which checks the budgets actually stayed matched.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from nebula.experiments.exp_refine_control import (
    RESULTS as CONTROL_RESULTS, eligible, sampled_actor,
)
from nebula.experiments.exp_rl_refine import (
    REFINE_MAX_STEP, SEED, refine_one, sign_test_p, wilson_ci,
)

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "refine_sampled_results.json"
RUN_LOG = HERE / "refine_sampled_run.jsonl"

#: Entry 48's registered restart schedule. NOT swept.
RESTARTS: int = 4
STEPS_PER_RESTART: int = 2


def control_arms() -> dict:
    """Entry 47's arms A and B, per request. **Read, never re-run.**

    Keyed by the request's original index in the 128-target list, which is what
    makes the comparison paired: D and E are scored against A and B on the very
    same request from the very same start.
    """
    if not CONTROL_RESULTS.exists():
        raise SystemExit(
            f"{CONTROL_RESULTS.name} is missing. Entry 48 is scored AGAINST "
            f"entry 47's arms A and B, so entry 47 must finish first -- "
            f"re-running its arms here would be a second measurement of the "
            f"same thing under different conditions.")
    d = json.loads(CONTROL_RESULTS.read_text(encoding="utf-8"))
    return {int(r["index"]): r for r in d["rows"]}


def run(n: Optional[int] = None, seed: int = SEED) -> dict:
    import torch                                            # noqa: F401

    from nebula.experiments.exp_rl_refine import _load_policy
    from nebula.experiments.runlock import hold, stamp
    from nebula.rl.spec_dist import SpecTarget

    with hold("refine_sampled"):
        t0 = time.time()
        ctrl = control_arms()
        targets = [t for t in eligible() if t["index"] in ctrl]
        if n is not None:
            targets = targets[:int(n)]
        net, ck = _load_policy(7 + 8 + 2 + 1, 7, seed)
        print(f"entry 48: {len(targets)} requests, arms D (1x8 sampled) and "
              f"E ({RESTARTS}x{STEPS_PER_RESTART} sampled), "
              f"max_step={REFINE_MAX_STEP}", flush=True)

        rows: list[dict] = []
        with RUN_LOG.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps({"event": "start", "seed": seed,
                                 "restarts": RESTARTS,
                                 "steps_per_restart": STEPS_PER_RESTART,
                                 "n": len(targets), **stamp()}) + "\n")
            for k, t in enumerate(targets):
                tgt = SpecTarget(peaking_db=t["peaking_db"],
                                 f_peak_hz=t["f_peak_hz"])
                act = sampled_actor(net)
                d_ = refine_one(net, tgt, seed=t["seed"], actor=act)
                e_ = refine_one(net, tgt, seed=t["seed"], actor=act,
                                restarts=RESTARTS,
                                max_steps=STEPS_PER_RESTART)
                c = ctrl[t["index"]]
                row = {
                    "index": t["index"], "peaking_db": t["peaking_db"],
                    "f_peak_hz": t["f_peak_hz"],
                    "A_delta": c["A_delta"], "A_crossed": c["A_crossed"],
                    "A_decks": c["A_decks"],
                    "B_delta": c["B_delta"], "B_crossed": c["B_crossed"],
                    "B_decks": c["B_decks"],
                    "D_delta": d_.delta, "D_crossed": d_.improved,
                    "D_decks": d_.pol_sims, "D_steps": d_.n_steps,
                    "E_delta": e_.delta, "E_crossed": e_.improved,
                    "E_decks": e_.pol_sims, "E_steps": e_.n_steps,
                    # Q1: same start as entry 47, componentwise.
                    "same_start": bool(d_.lib_u is not None
                                       and e_.lib_u is not None
                                       and d_.lib_u == e_.lib_u),
                    "lib_reward": d_.lib_reward,
                }
                rows.append(row)
                fh.write(json.dumps(row) + "\n")
                fh.flush()
                print(f"[{k + 1}/{len(targets)}] {t['peaking_db']:5.2f} dB @ "
                      f"{t['f_peak_hz'] / 1e9:.3f} GHz   "
                      f"A {c['A_delta']:+8.4f}{'*' if c['A_crossed'] else ' '} "
                      f"B {c['B_delta']:+8.4f}{'*' if c['B_crossed'] else ' '} "
                      f"D {d_.delta:+8.4f}{'*' if d_.improved else ' '} "
                      f"E {e_.delta:+8.4f}{'*' if e_.improved else ' '}  "
                      f"decks {c['A_decks']}/{c['B_decks']}/"
                      f"{d_.pol_sims}/{e_.pol_sims}", flush=True)

        out = _summarise(rows)
        out.update({"task": "entry 48: the policy's own distribution",
                    **stamp(), "seed": seed, "restarts": RESTARTS,
                    "steps_per_restart": STEPS_PER_RESTART,
                    "policy_steps": ck["steps"], "max_step": REFINE_MAX_STEP,
                    "wall_clock_s": time.time() - t0, "rows": rows})
        RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
        return out


def _summarise(rows: Sequence[dict]) -> dict:
    n = len(rows)
    out: dict = {"n": n}
    for arm in ("A", "B", "D", "E"):
        cr = sum(1 for r in rows if r[f"{arm}_crossed"])
        lo, hi = wilson_ci(cr, n) if n else (0.0, 0.0)
        out[arm] = {
            "crossings": cr, "cross_rate": cr / n if n else 0.0,
            "cross_ci95": [lo, hi],
            "moved_up": sum(1 for r in rows if r[f"{arm}_delta"] > 1e-9),
            "moved_down": sum(1 for r in rows if r[f"{arm}_delta"] < -1e-9),
            "mean_decks": float(np.mean([r[f"{arm}_decks"] for r in rows]))
            if n else 0.0}

    a_decks = out["A"]["mean_decks"] or 1.0
    out["Q5_budget"] = {
        arm: {"mean_decks": out[arm]["mean_decks"],
              "vs_A_pct": 100.0 * (out[arm]["mean_decks"] - a_decks) / a_decks,
              "within_10pct": abs(out[arm]["mean_decks"] - a_decks) / a_decks
              <= 0.10}
        for arm in ("D", "E")}

    def _mc(x: str, y: str) -> dict:
        ox = sum(1 for r in rows if r[f"{x}_crossed"] and not r[f"{y}_crossed"])
        oy = sum(1 for r in rows if r[f"{y}_crossed"] and not r[f"{x}_crossed"])
        return {"only_" + x: ox, "only_" + y: oy, "p": sign_test_p(ox, oy)}

    out["Q2_E_vs_A"] = {**_mc("E", "A"),
                        "hit": out["E"]["crossings"] > out["A"]["crossings"]}
    out["Q3_E_vs_B"] = {**_mc("E", "B"),
                        "hit": out["E"]["crossings"] >= out["B"]["crossings"]}
    out["Q4_D"] = {"hit": (out["D"]["crossings"] > out["A"]["crossings"]
                           and out["D"]["crossings"] < out["B"]["crossings"])}
    out["Q1_control"] = {
        "n_same_start": sum(1 for r in rows if r["same_start"]), "n": n,
        "reproduced": all(r["same_start"] for r in rows) if n else False}
    return out


def _report(d: dict) -> None:
    n = d["n"]
    print()
    print("=" * 78)
    print(f"ENTRY 48 — THE POLICY'S OWN DISTRIBUTION, {n} requests, "
          f"{d.get('wall_clock_s', 0) / 60:.1f} min")
    print("=" * 78)
    print(f"  {'arm':<34}{'crossed':>9}{'up':>6}{'down':>6}{'decks':>8}")
    print("  " + "-" * 68)
    for arm, name in (("A", "A  policy MEAN        1 x 8"),
                      ("B", "B  uniform random     1 x 8"),
                      ("D", "D  policy SAMPLED     1 x 8"),
                      ("E", f"E  policy SAMPLED     "
                            f"{d.get('restarts', 4)} x "
                            f"{d.get('steps_per_restart', 2)}")):
        a = d[arm]
        print(f"  {name:<34}{a['crossings']:>6} /{n:<2}{a['moved_up']:>6}"
              f"{a['moved_down']:>6}{a['mean_decks']:>8.1f}")
    q1 = d["Q1_control"]
    print()
    print(f"  Q1 control : starts identical to entry 47 on "
          f"{q1['n_same_start']}/{q1['n']}")
    print(f"  Q2 E vs A  : {'HIT ' if d['Q2_E_vs_A']['hit'] else 'MISS'}"
          f"  {d['E']['crossings']} vs {d['A']['crossings']}"
          f"   (McNemar p = {d['Q2_E_vs_A']['p']:.4f})")
    print(f"  Q3 E vs B  : {'HIT ' if d['Q3_E_vs_B']['hit'] else 'MISS'}"
          f"  {d['E']['crossings']} vs {d['B']['crossings']}"
          f"   (McNemar p = {d['Q3_E_vs_B']['p']:.4f})   <-- THE BAR")
    print(f"  Q4 D split : {'HIT ' if d['Q4_D']['hit'] else 'MISS'}"
          f"  D {d['D']['crossings']} between A {d['A']['crossings']} "
          f"and B {d['B']['crossings']}?")
    for arm, q in d["Q5_budget"].items():
        print(f"  Q5 budget {arm}: {q['mean_decks']:.1f} decks, "
              f"{q['vs_A_pct']:+.1f}% vs A  "
              f"{'OK' if q['within_10pct'] else 'OUT OF BAND'}")
    print()
    if not q1["reproduced"]:
        print("  Q1 MISSED -- a start differs from entry 47. READ NOTHING ELSE.")
        return
    if d["Q3_E_vs_B"]["hit"]:
        print("  Q3 HIT: the learned policy MATCHES OR BEATS uniform random at a")
        print("  matched budget from the same start. That is the first genuine RL")
        print("  contribution in this project -- and the mechanism is that the")
        print("  policy was being read at its mean, discarding what it learned.")
    elif d["Q2_E_vs_A"]["hit"]:
        print("  Q2 HIT, Q3 MISSED: evaluating at the mean UNDERSTATED the policy")
        print("  by a measurable amount, and fixing it was still not enough to")
        print("  beat noise. Report both -- this names a cause, which entry 47")
        print("  could not.")
    else:
        print("  Q2 MISSED: the diagnosis is wrong. The policy's learned")
        print("  direction carries nothing this selector can use, and the RL")
        print("  line closes on a MECHANISM rather than on a p-value.")
    print("=" * 78)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--analyse", action="store_true")
    ap.add_argument("--n", type=int, default=None)
    ap.add_argument("--seed", type=int, default=SEED)
    a = ap.parse_args(argv)
    if a.run:
        _report(run(n=a.n, seed=a.seed))
    elif a.analyse:
        if not RESULTS.exists():
            raise SystemExit(f"{RESULTS.name} missing: run --run first")
        _report(json.loads(RESULTS.read_text(encoding="utf-8")))
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":                                  # pragma: no cover
    raise SystemExit(main())
