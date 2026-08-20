"""
experiments/exp_linear_pareto.py — **how much differential input will this
topology take, and what does S3 charge for it?**

THE QUESTION, AND WHY IT IS THE ONE THAT DECIDES S8
----------------------------------------------------
S8 is blocked at all 135 points of the delivered design because the stage is
driven past its linear range. Session 22q measured WHERE that comes from:

    linear input range at f  =  linear input range at DC / |H(f)/H(0)|

A source-degenerated pair gets its linear input range from `Rs` and its peaking
from `Cs` shorting that same `Rs` out at the signal band. **The two are one
knob read in opposite directions**, so a peaking spec is also, silently, a
linearity budget. The delivered design measures 520 mVpp at DC, 172 mVpp at
Nyquist, against a 535 mVpp drive.

That is one design. This file asks the question of the WHOLE BOX: **plot the
attainable linear input range against peaking, and find where — if anywhere —
it crosses the drive the link actually delivers.**

WHAT IS AND IS NOT CLAIMED BY A "PARETO FRONT" HERE
-----------------------------------------------------
**This is an ATTAINED front from a finite sample, not a proven envelope.**
Nothing here can show that no sizing anywhere does better; it can only show
what 1600-odd simulations found. Two arms, because they fail differently:

* **`pool`** — replay of designs this project has ALREADY simulated
  (`spec_pool`, 74 526 distinct valid designs), stratified into 0.5 dB peaking
  bins so the high-peaking end is populated at all. Broad, unbiased with
  respect to linear range, and blind to any region the past searches never
  visited.
* **`targeted`** — CMA-ES run with linear input range at Nyquist AS THE
  OBJECTIVE, inside a narrow peaking band. This is the arm that makes a
  negative result worth something: if a search that wants nothing but linear
  range cannot reach the drive level, "the sample missed it" stops being the
  explanation.

The CMA-ES core is `baselines.method_cmaes` — imported, not re-implemented, so
Hansen's equations have one definition in this repo (rule 9). It needs only
`check_budget()` and `evaluate(u).reward` from its objective, which is what
`_LinearObjective` provides.

COST
----
`pool` 28 bins x 30 = 840 simulations; `targeted` 5 bands x 150 = 750. About
1 600 simulations, ~10 minutes at the measured 0.35 s/point for `.op + .ac +
.dc`. No `.noise` and no transient: neither enters the quantity under study,
and leaving them out is most of the per-point cost.

NOTHING HERE CHANGES THE SEARCH. `V1_SPECS`, the tolerances and the box are
untouched; the objective below is local to this file and is never imported by
`rl/`. `test_no_mocks_in_training_path.py`'s spirit applies: a reward invented
for one experiment must not leak into the one the benchmark is scored on.
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

from nebula.device.sky130_runner import run_point, swing_limits
from nebula.link.config import LinkConfig, PCIE_GEN2_TX_DIFF_PP_MIN_V
from nebula.experiments.exp_g2_closed_loop import FUNNEL_LOSS_DB
from nebula.rl.contract import N_ACTIONS, sizing_from_u
from nebula.rl.evaluator import build_point

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "linear_pareto_results.json"
RUN_LOG = HERE / "linear_pareto_run.jsonl"

#: Peaking bins for the `pool` arm, in dB. S3's band is 3-12; the range is
#: deliberately WIDER so the front can be seen entering and leaving the spec.
BIN_EDGES: tuple[float, ...] = tuple(np.arange(0.0, 14.01, 0.5))
#: Designs replayed per bin. 30 is what makes 28 bins fit inside ~5 minutes;
#: it is a sample size, not a threshold, and the front is reported with its
#: bin count so a reader can see how thin the tails are.
PER_BIN: int = 30

#: Peaking bands the `targeted` arm searches inside, in dB. 3.0 is S3's floor,
#: 9.78 is the DELIVERED design's peaking, 12.0 is S3's ceiling.
TARGET_PEAKING_DB: tuple[float, ...] = (3.0, 6.0, 9.0, 9.78, 12.0)
#: Half-width of the band the targeted arm must stay inside, dB.
BAND_HALF_DB: float = 0.5
#: Simulations per targeted band.
TARGET_BUDGET: int = 150


def drive_pp_v(loss_db: float = FUNNEL_LOSS_DB) -> float:
    """The differential input the link delivers, Vpp. **Derived, not typed.**

    Read from `LinkConfig` so this file cannot drift from the number the eye is
    computed against. At the defaults it is the PCIe Gen2 minimum TX swing
    (800 mVpp) reduced by the mandated -3.5 dB de-emphasis and attenuated by
    the channel at DC, which is 0 dB by construction -- so 535 mVpp, and it is
    a POST-CHANNEL instantaneous excursion, not the raw TX swing.
    """
    return float(LinkConfig(channel_loss_db_at_nyquist=loss_db).v_in_diff_pp_v)


@dataclass
class Probe:
    """One sizing, measured for peaking and for linear input range."""

    u: tuple
    ok: bool
    arm: str
    reason: Optional[str] = None
    peaking_db: Optional[float] = None
    nyq_boost_db: Optional[float] = None
    f_peak_hz: Optional[float] = None
    g_dc_db: Optional[float] = None
    power_w: Optional[float] = None
    #: 1 dB gain compression, differential input Vpp, off the `.dc` curve.
    linear_in_dc_pp_v: Optional[float] = None
    #: The same, de-rated by the MEASURED Nyquist boost. `None` when the sweep
    #: never reached compression -- a LOWER bound, never a computed fallback.
    linear_in_nyq_pp_v: Optional[float] = None
    #: True when the `.dc` sweep never compressed, so the DC figure below is a
    #: bound rather than a limit. Carried so the front can exclude them or
    #: report them separately rather than silently treating a bound as a value.
    limit_is_lower_bound: bool = False


def probe(u: Sequence[float], arm: str, cl_f: Optional[float] = None,
          corner: str = "tt", temp_c: float = 27.0) -> Probe:
    """Simulate one sizing and read both quantities off it. Never raises.

    `.op + .ac + .dc` only. `.noise` and the HD3 transient are skipped because
    neither enters peaking or linear range, and they are most of the per-point
    cost.
    """
    from nebula.experiments.cl_range import committed_cl_range

    u = tuple(float(x) for x in np.clip(np.asarray(u, dtype=float), 0.0, 1.0))
    if len(u) != N_ACTIONS:
        raise ValueError(f"u has {len(u)} dims, expected {N_ACTIONS}")
    cl = committed_cl_range().cl_mid_f if cl_f is None else float(cl_f)
    try:
        sizing = sizing_from_u(np.asarray(u), cl_f=cl)
        point, _ = build_point(sizing, corner=corner, vdd_scale=1.0)
    except Exception as exc:                                    # noqa: BLE001
        return Probe(u=u, ok=False, arm=arm, reason=f"unrealisable: {exc}")

    pt = run_point(point, corner, temp_c=temp_c, swing=True, ac_sweep=True,
                   ac_peak_interp=True)
    if not pt.ok:
        return Probe(u=u, ok=False, arm=arm, reason=pt.fail_reason)
    if pt.vid is None:
        return Probe(u=u, ok=False, arm=arm, reason="no .dc transfer curve")

    try:
        lim = swing_limits(pt.vid, pt.vod, pt.sat_ok, pt.id_min,
                           i_ref_a=pt.point.i_tail_per_side_a)
    except ValueError as exc:
        return Probe(u=u, ok=False, arm=arm, reason=f"swing: {exc}")

    boost = float(pt.nyquist_boost_db)
    lower = lim.linear_in_pp_v is None
    lin_dc = lim.max_swept_in_pp_v if lower else float(lim.linear_in_pp_v)
    return Probe(
        u=u, ok=True, arm=arm,
        peaking_db=float(pt.peaking_db), nyq_boost_db=boost,
        f_peak_hz=float(pt.f_pk_hz) if pt.f_pk_hz else None,
        g_dc_db=float(pt.g_dc_db), power_w=pt.power_measured_w,
        linear_in_dc_pp_v=lin_dc,
        linear_in_nyq_pp_v=lin_dc / (10.0 ** (boost / 20.0)),
        limit_is_lower_bound=lower,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Arm 1 — replay of what has already been simulated, stratified by peaking.
# ─────────────────────────────────────────────────────────────────────────────


def stratified_u(per_bin: int = PER_BIN, seed: int = 22_071) -> list[tuple]:
    """`per_bin` sizings from each peaking bin, drawn from the existing pool.

    **Seeded from a stable function of the bin**, not from one stream shared
    across bins (G96): otherwise adding a bin would silently re-draw every
    other bin's sample and move the front with nothing in the diff.
    """
    from nebula.experiments import spec_pool as SP

    pool = SP.load_pool()
    pk = np.array([float(m["peaking_db"]) for m in pool.meas])
    out: list[tuple] = []
    for lo, hi in zip(BIN_EDGES[:-1], BIN_EDGES[1:]):
        idx = np.flatnonzero((pk >= lo) & (pk < hi))
        if idx.size == 0:
            continue
        rng = np.random.default_rng(seed + int(round(lo * 100)))
        take = idx if idx.size <= per_bin else rng.choice(idx, per_bin,
                                                          replace=False)
        out.extend(tuple(float(x) for x in pool.u[i]) for i in take)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Arm 2 — CMA-ES with linear range AS the objective, inside a peaking band.
# ─────────────────────────────────────────────────────────────────────────────


class _LinearObjective:
    """Maximise linear input range at Nyquist, subject to a peaking band.

    Duck-types just enough of `baselines.Objective` for `method_cmaes`:
    `check_budget()` and `evaluate(u).reward`. **The CMA-ES itself is imported,
    not copied** (rule 9).

    The score is deliberately crude, because its job is to find a physical
    ceiling rather than to be a defensible design objective:

        outside the peaking band ->  -|distance from the band|, in dB
        inside it                ->  linear_in_nyq_pp_v, in volts

    Those two branches cannot touch: the first is <= 0 and the second is > 0.
    An invalid simulation scores below both. **This objective never leaves this
    file** and is not a candidate to replace `reward_v1`.
    """

    def __init__(self, target_db: float, budget: int, half_db: float = BAND_HALF_DB):
        self.target_db = float(target_db)
        self.half_db = float(half_db)
        self.budget = int(budget)
        self.used = 0
        self.probes: list[Probe] = []

    def check_budget(self) -> None:
        from nebula.experiments.baselines import BudgetExhausted

        if self.used >= self.budget:
            raise BudgetExhausted(f"{self.used}/{self.budget}")

    def evaluate(self, u):
        self.check_budget()
        self.used += 1
        p = probe(u, arm=f"targeted@{self.target_db:g}")
        self.probes.append(p)
        if not p.ok or p.peaking_db is None:
            return _Scored(-1e3)
        d = abs(p.peaking_db - self.target_db)
        if d > self.half_db:
            return _Scored(-(d - self.half_db))
        return _Scored(float(p.linear_in_nyq_pp_v))


@dataclass(frozen=True)
class _Scored:
    reward: float


def run_targeted(target_db: float, budget: int = TARGET_BUDGET,
                 seed: int = 22_072) -> list[Probe]:
    from nebula.experiments.baselines import BudgetExhausted, method_cmaes

    obj = _LinearObjective(target_db, budget)
    rng = np.random.default_rng(seed + int(round(target_db * 100)))
    try:
        method_cmaes(obj, rng)
    except BudgetExhausted:
        pass
    return obj.probes


# ─────────────────────────────────────────────────────────────────────────────
# The front.
# ─────────────────────────────────────────────────────────────────────────────


def front(probes: Sequence[Probe], key: str,
          edges: Sequence[float] = BIN_EDGES) -> list[dict]:
    """Max of `key` in each peaking bin, with the bin's population.

    **Designs whose `.dc` sweep never compressed are EXCLUDED from the max**
    and counted separately: their figure is a lower bound on the true limit,
    and taking a max over a mixture of limits and bounds would report a bound
    as the front.
    """
    rows = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        inb = [p for p in probes
               if p.ok and p.peaking_db is not None and lo <= p.peaking_db < hi]
        hard = [p for p in inb if not p.limit_is_lower_bound
                and getattr(p, key) is not None]
        if not inb:
            continue
        best = max(hard, key=lambda p: getattr(p, key)) if hard else None
        rows.append({
            "peaking_lo_db": float(lo), "peaking_hi_db": float(hi),
            "n": len(inb), "n_with_a_hard_limit": len(hard),
            "n_lower_bound_only": sum(1 for p in inb if p.limit_is_lower_bound),
            "best": None if best is None else float(getattr(best, key)),
            "best_u": None if best is None else list(best.u),
            "best_power_w": None if best is None else best.power_w,
            "best_peaking_db": None if best is None else best.peaking_db,
        })
    return rows


def crossing(rows: Sequence[dict], drive_v: float) -> Optional[dict]:
    """Highest peaking bin whose attained front still reaches `drive_v`.

    Returns `None` when no bin does -- which is a result, not an error, and the
    caller must report it as one rather than as a missing number.
    """
    ok = [r for r in rows if r["best"] is not None and r["best"] >= drive_v]
    if not ok:
        return None
    top = max(ok, key=lambda r: r["peaking_hi_db"])
    return {"peaking_lo_db": top["peaking_lo_db"],
            "peaking_hi_db": top["peaking_hi_db"],
            "best": top["best"], "n": top["n"]}


def run(pool_arm: bool = True, targeted_arm: bool = True,
        per_bin: int = PER_BIN, budget: int = TARGET_BUDGET,
        loss_db: float = FUNNEL_LOSS_DB) -> dict:
    t0 = time.time()
    probes: list[Probe] = []
    with RUN_LOG.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({"event": "start", "per_bin": per_bin,
                             "budget": budget, "loss_db": loss_db,
                             "bin_edges": list(BIN_EDGES)}) + "\n")
        if pool_arm:
            for u in stratified_u(per_bin):
                p = probe(u, arm="pool")
                probes.append(p)
                fh.write(json.dumps(asdict(p)) + "\n")
        if targeted_arm:
            for tdb in TARGET_PEAKING_DB:
                for p in run_targeted(tdb, budget):
                    probes.append(p)
                    fh.write(json.dumps(asdict(p)) + "\n")
        fh.write(json.dumps({"event": "end", "n": len(probes)}) + "\n")

    drive = drive_pp_v(loss_db)
    ok = [p for p in probes if p.ok]
    f_dc = front(probes, "linear_in_dc_pp_v")
    f_ny = front(probes, "linear_in_nyq_pp_v")
    out = {
        "n_simulations": len(probes),
        "n_ok": len(ok),
        "wall_clock_s": time.time() - t0,
        "drive_pp_v": drive,
        "drive_basis": ("PCIe Gen2 min TX swing 800 mVpp, -3.5 dB mandated "
                        "de-emphasis, channel at DC (0 dB by construction). "
                        "A POST-CHANNEL instantaneous excursion."),
        "front_dc": f_dc,
        "front_nyquist": f_ny,
        "crossing_nyquist": crossing(f_ny, drive),
        "crossing_dc": crossing(f_dc, drive),
        "max_linear_in_nyq_pp_v": max(
            (p.linear_in_nyq_pp_v for p in ok
             if not p.limit_is_lower_bound and p.linear_in_nyq_pp_v is not None),
            default=None),
        "n_lower_bound_only": sum(1 for p in ok if p.limit_is_lower_bound),
    }
    RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def _report(out: dict) -> None:
    print(f"{out['n_simulations']} simulations, {out['n_ok']} ok, "
          f"{out['wall_clock_s'] / 60:.1f} min")
    print(f"drive = {1e3 * out['drive_pp_v']:.1f} mVpp   ({out['drive_basis']})")
    print()
    print("  peaking band   n   hard   front DC   front Nyq   vs drive")
    ny = {(r["peaking_lo_db"], r["peaking_hi_db"]): r for r in out["front_nyquist"]}
    for r in out["front_dc"]:
        k = (r["peaking_lo_db"], r["peaking_hi_db"])
        n = ny.get(k, {})
        dc = "-" if r["best"] is None else f"{1e3 * r['best']:8.1f}"
        nq = "-" if n.get("best") is None else f"{1e3 * n['best']:8.1f}"
        rat = ("-" if n.get("best") is None
               else f"{n['best'] / out['drive_pp_v']:6.2f}x")
        print(f"  {r['peaking_lo_db']:4.1f}-{r['peaking_hi_db']:4.1f} dB "
              f"{r['n']:4d} {r['n_with_a_hard_limit']:6d} {dc} {nq}   {rat}")
    print()
    c = out["crossing_nyquist"]
    if c is None:
        print("  CROSSING: none. No peaking bin's attained front reaches the "
              "drive at Nyquist.")
    else:
        print(f"  CROSSING: the front still reaches the drive at "
              f"{c['peaking_lo_db']:.1f}-{c['peaking_hi_db']:.1f} dB "
              f"({1e3 * c['best']:.1f} mVpp against "
              f"{1e3 * out['drive_pp_v']:.1f})")
    m = out["max_linear_in_nyq_pp_v"]
    if m is not None:
        print(f"  best linear range at Nyquist anywhere: {1e3 * m:.1f} mVpp "
              f"({m / out['drive_pp_v']:.2f}x the drive)")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--pool-only", action="store_true")
    ap.add_argument("--targeted-only", action="store_true")
    ap.add_argument("--per-bin", type=int, default=PER_BIN)
    ap.add_argument("--budget", type=int, default=TARGET_BUDGET)
    ap.add_argument("--analyse", action="store_true")
    a = ap.parse_args(argv)
    if a.analyse:
        _report(json.loads(RESULTS.read_text(encoding="utf-8")))
        return 0
    if not a.run:
        ap.print_help()
        return 2
    _report(run(pool_arm=not a.targeted_only, targeted_arm=not a.pool_only,
                per_bin=a.per_bin, budget=a.budget))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
