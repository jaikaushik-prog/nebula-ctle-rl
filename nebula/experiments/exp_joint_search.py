"""
experiments/exp_joint_search.py — **the search nobody has run: S3 and S8 and
HD3-at-Nyquist in ONE objective, scored on the worst corner.**

WHY THIS EXISTS
----------------
Session 22r left the project holding two half-designs:

| | delivered | front @ 9.2 dB |
|---|---|---|
| S3 at 135 points | **PASS** | fails f_peak at 61 of 121 |
| S8 at 135 points | **not measurable** (3.1x overdrive) | **PASS**, 226-299 mV |

**Neither had ever been asked for both**, and that is a property of the
objective rather than of the circuit: `V1_SPECS`, which every published search
scores, contains S3 and **not** S8; `V2_SPECS`/`V3_SPECS` contain S8 and have
never been used for a search. So *"why is the eye unverified"* had a one-line
answer -- nothing asked -- and this file asks.

**WHY S3 + S8 ALONE IS NOT THE RIGHT OBJECTIVE.** The eye is computed from a
small-signal AC fit. A design can satisfy S8 while being large-signal
non-linear at the drive: the compression gate catches the gross case, but it
compares a pulse-response excursion against a DC-swept limit, and neither is a
transient at the signal band. **HD3 at Nyquist, at the amplitude the link
actually delivers, is the transient-verified version** -- and session 22r
measured the delivered design at **-17.38 dBc** there against **-48.00 dBc** at
S4's stated 100 MHz / 200 mVpp. Search S3 + S8 without it and the failure
relocates instead of closing.

Hence `V4_SPECS` = every row on the competition's slide, with S4 asked at the
operating point. **`S4_hd3_nyq` is a separate row from `S4_hd3`, not the same
row under different conditions** -- a 30 dB difference under one name is G32
exactly.

THE SEARCH IS DELIBERATELY LOCAL, AND THAT IS A CHOICE WITH A COST
-------------------------------------------------------------------
It is seeded at the 9.2 dB front design, which already scores **10 of 11 rows
at 135 points** with only `S3_f_peak` failing and eye margins that are
comfortable rather than marginal (226-299 mV against a 100 mV floor;
0.781-0.812 UI against 0.4). The remaining problem is one-dimensional in a
useful sense: **move `f_peak` into 1.25-2.5 GHz without giving up the eye.**

`CmaConfig.x0` (added for this, and used by nothing in `BASELINES.md`) starts
the search there with a small `sigma0` rather than uniformly at random.

**What that costs, stated up front: this is no longer a comparable benchmark
arm.** A method starting from a known-good point cannot be ranked against one
starting from noise. Nothing here goes into the benchmark tables; the claim is
"a design meeting all eleven rows exists and here it is", not "local CMA-ES
beats X".

STEERING f_peak WITH THE MEASURED SENSITIVITY
----------------------------------------------
`exp_sweep_cost` measured `|d log2(f_peak) / du|` per axis at real designs:
**cs 3.243, rl 2.702**, everything else below 0.53 octaves per box width. So
`cs` and `rl` are the two knobs that move the peak, and the seed's `f_peak`
has to travel a known distance in octaves. `initial_step()` converts that
distance into a `cs` displacement using the measured sensitivity, and the
result is reported next to what the search actually did -- an analytic
starting guess that is CHECKED rather than trusted (G60: the design equations
over-predict the Nyquist boost by 0.8-1.5 dB).

    python -m nebula.experiments.exp_joint_search --run
    python -m nebula.experiments.exp_joint_search --verify     # 135 points
    python -m nebula.experiments.exp_joint_search --analyse
"""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from nebula.rl import reward_v1 as R
from nebula.rl.contract import (
    ACTION_NAMES,
    ACTION_SPACE,
    N_ACTIONS,
    f_peak_octaves,
)
from nebula.rl.evaluator import annotate_interpolated_peak, scored_meas

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "joint_search_results.json"
RUN_LOG = HERE / "joint_search_run.jsonl"

#: The 135-point checklist for the winner of the joint search.
#:
#: **This file did not exist until session 22u, and the report's headline table
#: was typing its numbers by hand.** `build_pdf` generates the cover counters
#: from artifacts but the body carried literals -- *"11 of 11"*, *"98 of 135"*,
#: *"377.1 - 539.4 mV"* -- with no artifact behind them, which is the one thing
#: `CLAUDEwa.md` §8 rule 1 forbids. `--verify` runs the same `verify_full` the
#: delivered design is measured by, on the winner read out of `RESULTS`, and
#: writes what it measured.
VERIFY_RESULTS = HERE / "joint_verify_full_results.json"

#: The seed: session 22r's best design in the 9.0-9.5 dB peaking bin, read from
#: `linear_pareto_run.jsonl` rather than transcribed.
SEED_PEAKING_BAND: tuple[float, float] = (9.0, 9.5)

#: Corners the search scores on. The same 3-corner x 2-load screen every P3
#: result in this project uses, so the cost is comparable and the known blind
#: spot (no `sf`/`fs` member -- `G4_RESULTS.md`) is the same known blind spot.
#: The 135-point verification is what closes it, and it is a separate step.
SEARCH_ON_SCREEN: bool = True

#: Simulation budget for the local refinement.
BUDGET: int = 400

#: Initial step size, normalised. Small: this is a refinement of a design that
#: is already 10 of 11, not a fresh search. 0.12 is ~1.5 of `MAX_STEP`.
SIGMA0: float = 0.12

#: The target the S3_f_peak row is scored against. Centre of S3's window in
#: LOG frequency, `sqrt(1.25e9 * 2.5e9)`, because every frequency result in
#: this project is in octaves -- the arithmetic centre 1.875 GHz would sit
#: 0.085 octaves off centre and quietly bias the row.
TARGET_F_PEAK_HZ: float = math.sqrt(1.25e9 * 2.5e9)


def seed_design() -> dict:
    """The 9.2 dB front design, out of session 22r's run log."""
    import gzip

    p = HERE / "linear_pareto_run.jsonl.gz"
    best = None
    with gzip.open(p, "rt", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if not r.get("ok") or r.get("limit_is_lower_bound"):
                continue
            if not r.get("has_real_peak") or not r.get("f_peak_hz"):
                continue
            pk = r.get("peaking_db")
            if pk is None or not (SEED_PEAKING_BAND[0] <= pk < SEED_PEAKING_BAND[1]):
                continue
            if not (1.25e9 <= r["f_peak_hz"] <= 2.5e9):
                continue
            if best is None or r["linear_in_nyq_pp_v"] > best["linear_in_nyq_pp_v"]:
                best = r
    if best is None:
        raise RuntimeError(f"no seed candidate in {p}")
    return best


def initial_step(seed: dict) -> dict:
    """Where the measured sensitivity says `cs` should go, and how far.

    `f_peak` must travel `log2(target / f_peak_seed)` octaves. `cs` moves it at
    a MEASURED `-|d log2 f / du_cs|` octaves per box width (raising `cs` lowers
    the peak), so the normalised displacement is that distance over the
    sensitivity. **Reported as a starting guess, never applied blindly**: the
    search is what decides, and the two are compared in the results.
    """
    sc = json.loads((HERE / "sweep_cost_results.json").read_text(encoding="utf-8"))
    s_cs = next(s["median_oct"] for s in sc["sensitivity"] if s["name"] == "cs")
    s_rl = next(s["median_oct"] for s in sc["sensitivity"] if s["name"] == "rl")
    need_oct = math.log2(TARGET_F_PEAK_HZ / float(seed["f_peak_hz"]))
    i_cs = ACTION_NAMES.index("cs")
    du = -need_oct / s_cs                      # raising cs LOWERS f_peak
    return {"octaves_to_travel": need_oct,
            "d_cs_normalised": du,
            "cs_sensitivity_oct_per_box": s_cs,
            "rl_sensitivity_oct_per_box": s_rl,
            "u_cs_seed": float(seed["u"][i_cs]),
            "u_cs_guess": float(np.clip(seed["u"][i_cs] + du, 0.0, 1.0))}


# ─────────────────────────────────────────────────────────────────────────────
# The evaluation: every V4 row, on the worst of the screen points.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class JointEval:
    u: tuple
    ok: bool
    reward: float
    feasible: bool
    reason: Optional[str] = None
    worst_point: Optional[str] = None
    worst_spec: Optional[str] = None
    n_violated: int = 0
    margins: dict = field(default_factory=dict)
    #: Per-point detail is deliberately NOT kept: at 400 designs x 6 points it
    #: would be 2400 rows of duplicate measurement, and G95's family is a run
    #: log that duplicates itself into a results file.
    peaking_db: Optional[float] = None
    f_peak_hz: Optional[float] = None
    power_w: Optional[float] = None
    hd3_nyq_dbc: Optional[float] = None
    eye_h_v: Optional[float] = None
    eye_w_ui: Optional[float] = None
    #: How many of the corner x load points could be scored at all. Carried
    #: because "unscorable" and "failing" are different verdicts and collapsing
    #: them is how session 22o reported "0 of 135 scorable", which was true and
    #: useless.
    n_scorable: int = 0
    n_points: int = 0


def evaluate_joint(u: Sequence[float],
                   corners: Optional[Sequence] = None,
                   loads: Optional[Sequence[float]] = None,
                   ac_peak_interp: bool = True) -> JointEval:
    """Score one sizing on `V4_SPECS`, worst over corners and loads.

    Never raises.

    **A POINT THAT CANNOT BE SCORED IS NOT THE SAME AS A POINT THAT FAILS, and
    the difference decides whether this search can move at all.** The seed
    design is rejected by the pole-zero fit gate at `ss/0.95/125C` with a
    residual of 0.564 dB against the 0.50 dB limit -- correctly: without a
    valid fit there are no poles, so there is no eye, so S8 is unmeasurable
    there. (This is also why `verify_full` reported it at 121 of 135 points
    rather than 135.) Under S9 that is a failed design.

    But scoring it at the flat invalid floor gives a search **no gradient
    anywhere near the seed**, so the run would measure nothing. So the invalid
    band is GRADED by the fraction of points that could be scored:

        r = invalid_reward(N) + n_scorable / n_points        in [-15, -14)

    strictly below the worst infeasible score (`-N` = -12), so a design with an
    unscorable corner can never outrank one that is merely bad -- and ordered,
    so the search can climb out. This is the same device as `headroom_reward`'s
    graded Call-1 band and introduces no new constant: both bounds come from
    `len(specs)`.

    **The gate itself is untouched.** Loosening the 0.50 dB residual limit to
    make the seed evaluable would be the exact move this repository exists to
    refuse.
    """
    from nebula.device.sky130_runner import run_point, swing_limits
    from nebula.experiments.exp_g2_closed_loop import FUNNEL_LOSS_DB
    from nebula.experiments.s9_yield import PROMOTION_LOADS, SCREEN_CORNERS
    from nebula.link.bridge import device_result_from_point, evaluate_link
    from nebula.link.config import LinkConfig
    from nebula.rl.contract import sizing_from_u
    from nebula.rl.evaluator import build_point

    u = tuple(float(x) for x in np.clip(np.asarray(u, dtype=float), 0.0, 1.0))
    corners = list(corners if corners is not None else SCREEN_CORNERS)
    loads = list(loads if loads is not None else PROMOTION_LOADS[::2] or PROMOTION_LOADS)
    cfg = LinkConfig(channel_loss_db_at_nyquist=FUNNEL_LOSS_DB)
    drive_pk = 0.5 * float(cfg.v_in_diff_pp_v)

    n_points = len(corners) * len(loads)
    n_scorable = 0
    first_bad: Optional[str] = None
    bad_point: Optional[str] = None
    worst = None
    for c in corners:
        for cl in loads:
            try:
                sizing = sizing_from_u(np.asarray(u), cl_f=float(cl))
                point, _ = build_point(sizing, corner=c.process,
                                       vdd_scale=c.vdd_scale)
            except Exception as exc:                            # noqa: BLE001
                return JointEval(u=u, ok=False, reward=R.invalid_reward(
                    len(R.V4_SPECS)), feasible=False,
                    reason=f"unrealisable: {exc}",
                    n_scorable=0, n_points=n_points)
            # **HD3 at NYQUIST and at the DRIVE amplitude**, not at S4's
            # stated conditions -- that is the whole point of the row.
            pt = run_point(point, c.process, temp_c=c.temp_c, swing=True,
                           ac_sweep=True, hd3=True,
                           ac_peak_interp=ac_peak_interp,
                           hd3_vin_pk_v=drive_pk, hd3_tone_hz=cfg.nyquist_hz)
            tag = f"{c.process}/{c.vdd_scale:.2f}/{c.temp_c:g}C/cl={cl*1e15:.1f}fF"
            if not pt.ok:
                first_bad = first_bad or pt.fail_reason
                bad_point = bad_point or tag
                continue
            dev = device_result_from_point(pt)
            if not dev.ok:
                first_bad = first_bad or dev.fail_reason
                bad_point = bad_point or tag
                continue
            lr = evaluate_link(dev, cfg)
            if not lr.ok:
                # **An eye that cannot be COMPUTED is unscorable, not failing.**
                # `margins` omits the S8 rows when the link result is absent --
                # deliberately, so nothing scores a defaulted eye -- so asking
                # for V4 here would raise. Same category as the fit rejection
                # above, and it is the category the DELIVERED design falls into
                # at all six points.
                first_bad = first_bad or lr.fail_reason
                bad_point = bad_point or tag
                continue
            n_scorable += 1
            meas = {
                "g_dc_db": dev.g_dc_db, "peaking_db": dev.peaking_db,
                "f_peak_oct": f_peak_octaves(float(dev.f_peak_hz)),
                "nyq_boost_db": float(pt.nyquist_boost_db),
                "inoise_vrms": dev.vn_in_vrms, "power_w": dev.power_w,
                "pair_margin_v": float(pt.vds) - float(pt.vdsat),
                "tail_margin_v": float(pt.tail_margin_v),
            }
            # **THE PEAK THIS SEARCH IS STEERED BY** (session 22u, G108).
            # Until now this scored `dev.f_peak_hz`, the raw `ac dec 50`
            # lattice value -- and S3's 1.2500 GHz floor falls between two of
            # its samples, so the objective reported a pass at 1.258925 GHz for
            # circuits whose peak was anywhere down to 1.2303 GHz. The search
            # was not merely blind to those six corners; it was REWARDED for
            # walking into the rounding band. Same two functions the compliance
            # matrix and the four benchmark arms reach the peak through.
            annotate_interpolated_peak(meas, None, pt)
            meas = scored_meas(meas, ac_peak_interp)
            # `hd3_dbc` is deliberately NOT passed: this deck's transient
            # ran at Nyquist and at the drive amplitude, so the number is the
            # `S4_hd3_nyq` row's, and feeding it to the 100 MHz row as well
            # would put a 2.5 GHz measurement under a 100 MHz name.
            rb = R.reward(meas, TARGET_F_PEAK_HZ, specs=R.V4_SPECS,
                          link=lr, area_mm2=dev.area_mm2,
                          hd3_nyq_dbc=dev.hd3_dbc)
            ev = JointEval(
                u=u, ok=True, reward=float(rb.reward),
                feasible=bool(rb.feasible), worst_point=tag,
                worst_spec=rb.worst_spec, n_violated=rb.n_violated,
                margins={k: float(v) for k, v in rb.margins.items()},
                # **REPORT THE PEAK THAT WAS SCORED**, not the lattice one it
                # was derived from. Leaving `dev.f_peak_hz` here printed
                # "f_peak 1.2589 GHz" beside a margin computed at 1.2417 --
                # two fields of one record disagreeing about the same run,
                # which is the second half of G107 and the exact confusion
                # this session exists to remove.
                peaking_db=float(meas["peaking_db"]),
                f_peak_hz=2.5e9 * 2.0 ** float(meas["f_peak_oct"]),
                power_w=dev.power_w, hd3_nyq_dbc=dev.hd3_dbc,
                eye_h_v=(lr.eye_h_v if lr.ok else None),
                eye_w_ui=(lr.eye_w_ui if lr.ok else None),
                reason=(None if lr.ok else lr.fail_reason))
            ev.n_points = n_points
            if worst is None or ev.reward < worst.reward:
                worst = ev

    if n_scorable < n_points:
        # Graded invalid band -- see the docstring. Ordered by evaluability,
        # strictly below every infeasible score.
        r = R.invalid_reward(len(R.V4_SPECS)) + n_scorable / n_points
        return JointEval(
            u=u, ok=False, reward=float(r), feasible=False,
            reason=(f"{n_points - n_scorable} of {n_points} points unscorable; "
                    f"first: {first_bad}"),
            worst_point=bad_point, n_scorable=n_scorable, n_points=n_points,
            margins=(worst.margins if worst else {}),
            peaking_db=(worst.peaking_db if worst else None),
            f_peak_hz=(worst.f_peak_hz if worst else None),
            power_w=(worst.power_w if worst else None),
            hd3_nyq_dbc=(worst.hd3_nyq_dbc if worst else None),
            eye_h_v=(worst.eye_h_v if worst else None),
            eye_w_ui=(worst.eye_w_ui if worst else None))
    # **Stamped AFTER the loop, not inside it.** Setting this per point wrote
    # the RUNNING count onto whichever point happened to be worst, so a design
    # with all six points scorable could report "2 of 6" beside a feasible
    # verdict -- two fields of one record disagreeing about the same run.
    worst.n_scorable = n_scorable
    worst.n_points = n_points
    return worst


class _JointObjective:
    """`baselines.method_cmaes`'s objective surface, scoring `V4_SPECS`."""

    def __init__(self, budget: int, log):
        self.budget = int(budget)
        self.used = 0
        self.log = log
        self.best: Optional[JointEval] = None

    def check_budget(self) -> None:
        from nebula.experiments.baselines import BudgetExhausted

        if self.used >= self.budget:
            raise BudgetExhausted(f"{self.used}/{self.budget}")

    def evaluate(self, u):
        self.check_budget()
        self.used += 1
        ev = evaluate_joint(u)
        self.log.write(json.dumps({"i": self.used, **asdict(ev)}) + "\n")
        self.log.flush()
        if self.best is None or ev.reward > self.best.reward:
            self.best = ev
        return ev


def run(budget: int = BUDGET, sigma0: float = SIGMA0,
        seed: int = 22_081) -> dict:
    from nebula.experiments.baselines import (BudgetExhausted, CmaConfig,
                                              method_cmaes)

    t0 = time.time()
    sd = seed_design()
    guess = initial_step(sd)
    with RUN_LOG.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({"event": "start", "budget": budget,
                             "sigma0": sigma0, "seed": seed,
                             "spec_set": list(R.V4_SPECS),
                             "target_f_peak_hz": TARGET_F_PEAK_HZ,
                             "seed_design": sd, "initial_step": guess}) + "\n")
        obj = _JointObjective(budget, fh)
        # The seed itself, scored, BEFORE the search -- so "did the search
        # help" has a baseline that is not the search's own first sample.
        seed_eval = obj.evaluate(sd["u"])
        try:
            method_cmaes(obj, np.random.default_rng(seed),
                         CmaConfig(sigma0=sigma0, x0=sd["u"]))
        except BudgetExhausted:
            pass
        fh.write(json.dumps({"event": "end", "used": obj.used}) + "\n")

    best = obj.best
    out = {
        "spec_set": list(R.V4_SPECS), "n_spec_rows": len(R.V4_SPECS),
        "budget": budget, "used": obj.used, "sigma0": sigma0, "seed": seed,
        "target_f_peak_hz": TARGET_F_PEAK_HZ,
        "seed_design_id": sd.get("design_id"),
        "seed_u": list(sd["u"]),
        "seed_scored_on_v4": asdict(seed_eval),
        "initial_step": guess,
        "best": asdict(best) if best else None,
        "improvement": (None if not best else
                        best.reward - seed_eval.reward),
        "wall_clock_s": time.time() - t0,
        "note": ("LOCAL search seeded at a known-good design. Not a benchmark "
                 "arm and not comparable with BASELINES.md, which starts every "
                 "method from uniform random."),
    }
    RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def _report(d: dict) -> None:
    print(f"spec set: {d['n_spec_rows']} rows, {d['used']} simulations, "
          f"{d['wall_clock_s'] / 60:.1f} min")
    g = d["initial_step"]
    print(f"\n  seed f_peak must travel {g['octaves_to_travel']:+.3f} octaves "
          f"to {d['target_f_peak_hz'] / 1e9:.3f} GHz")
    print(f"  measured cs sensitivity {g['cs_sensitivity_oct_per_box']:.3f} "
          f"oct/box  ->  u_cs {g['u_cs_seed']:.4f} -> {g['u_cs_guess']:.4f} "
          f"(analytic guess)")
    for tag, k in (("seed, scored on V4", "seed_scored_on_v4"), ("best", "best")):
        e = d[k]
        if not e:
            continue
        state = ("FEASIBLE" if e["feasible"]
                 else f"{e['n_violated']} row(s) violated")
        print(f"\n  {tag}: reward {e['reward']:+.4f}  {state}")
        print(f"    worst point {e['worst_point']}   worst row {e['worst_spec']}")
        print(f"    peaking {e['peaking_db']:.2f} dB  f_peak "
              f"{(e['f_peak_hz'] or 0) / 1e9:.3f} GHz  power "
              f"{(e['power_w'] or 0) * 1e3:.2f} mW")
        print(f"    HD3@Nyq {e['hd3_nyq_dbc']}  eye "
              f"{e['eye_h_v']} V / {e['eye_w_ui']} UI")
        neg = {k2: v for k2, v in (e["margins"] or {}).items() if v < 0}
        if neg:
            print(f"    failing rows: "
                  + ", ".join(f"{k2} {v:+.3f}" for k2, v in neg.items()))
    if d.get("improvement") is not None:
        print(f"\n  improvement over the seed: {d['improvement']:+.4f}")


def verify(out_path: Path = VERIFY_RESULTS) -> dict:
    """**The winner, on all 135 points, through the SAME routine as the rest.**

    Deliberately `exp_g4_verify.verify_full` rather than anything local. Two
    reasons, both earned:

    * The delivered design's checklist comes from that function, and a
      comparison between two designs measured by two routines measures the
      routines. G32 is that failure one level down.
    * `verify_full` is where session 22u fixed the lattice defect, so anything
      re-implementing it here would inherit the bug it was written to remove.

    The winner's box coordinates are **read out of `RESULTS`**, never
    transcribed. If the search has not been run, this raises rather than
    inventing a design.
    """
    from nebula.experiments.exp_g4_verify import Candidate, verify_full
    from nebula.rl.contract import design_id, sizing_from_u

    if not RESULTS.exists():
        raise FileNotFoundError(
            f"{RESULTS.name} missing: run `--run` before `--verify`; there is "
            f"no winner to verify and one will not be invented")
    d = json.loads(RESULTS.read_text(encoding="utf-8"))
    best = d.get("best")
    if not best or not best.get("ok"):
        raise ValueError(
            "the recorded joint-search winner is not a valid design; there is "
            "nothing to verify")

    u = tuple(float(x) for x in best["u"])
    did = design_id(sizing_from_u(np.asarray(u)))
    cand = Candidate(design_id=did, u=u, role="joint_winner",
                     source="exp_joint_search",
                     claimed_reward=float(best["reward"]),
                     claimed_worst_point=best.get("worst_point"))

    t0 = time.perf_counter()
    r = verify_full(cand)
    out = {
        "task": "the joint-search winner, on every spec row at every corner",
        # **The claim being checked, beside the check.** The search scored this
        # design on 6 points (3 screen corners x 2 loads) and V4_SPECS; this
        # runs 135 points and V3_SPECS. They are different questions and the
        # artifact has to say so or a reader will read the 6-point reward as if
        # it were a 135-point one.
        "searched_on": {"spec_set": list(d["spec_set"]),
                        "n_points": best.get("n_points"),
                        "reward": float(best["reward"])},
        "spec_set": list(r["spec_set"]),
        "wall_s": time.perf_counter() - t0,
        "results": [r],
    }
    out_path.write_text(json.dumps(out, indent=1, default=str),
                        encoding="utf-8")
    print(f"  joint_winner {did[:12]}  "
          f"{r['n_rows_passing']} rows PASS, {r['n_rows_failing']} FAIL, "
          f"{r['n_rows_not_measurable']} not measurable "
          f"(over {r['n_scored']}/{r['n_points']} points)")
    for name in r["spec_set"]:
        v = r["per_spec"][name]
        print(f"        {name:<16} {v['verdict']:<15} "
              f"checked {v['checked_at']:>3}  failed {v['failed_at']:>3}  "
              f"unmeasurable {v['unmeasurable_at']:>3}")
    print(f"  {out['wall_s'] / 60:.1f} min")
    print(f"wrote {out_path}")
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--verify", action="store_true",
                    help="the winner on 45 corners x 3 loads, all eleven spec "
                         "rows, through exp_g4_verify.verify_full")
    ap.add_argument("--analyse", action="store_true")
    ap.add_argument("--budget", type=int, default=BUDGET)
    ap.add_argument("--sigma0", type=float, default=SIGMA0)
    a = ap.parse_args(argv)
    if a.analyse:
        _report(json.loads(RESULTS.read_text(encoding="utf-8")))
        return 0
    if a.verify:
        verify()
        return 0
    if not a.run:
        ap.print_help()
        return 2
    _report(run(a.budget, a.sigma0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
