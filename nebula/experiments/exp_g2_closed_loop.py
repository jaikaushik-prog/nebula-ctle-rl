"""
experiments/exp_g2_closed_loop.py — gate G2, end to end, with no mock anywhere.

    python -m nebula.experiments.exp_g2_closed_loop --tiers      # cost per tier
    python -m nebula.experiments.exp_g2_closed_loop --funnel --n 300
    python -m nebula.experiments.exp_g2_closed_loop --example
    python -m nebula.experiments.exp_g2_closed_loop --analyse FILE.jsonl

WHAT G2 ASKS FOR (CLAUDEwa.md §7)
----------------------------------
> One full evaluation end-to-end: params -> ngspice -> fit -> eye -> scalar
> reward. No RL yet. **Wall-clock cost of each fidelity tier measured.**

So this file does three things and nothing else:

  * `--tiers`   measures what each analysis costs, which is half the criterion;
  * `--funnel`  runs a Latin hypercube over the APPROVED box through the whole
                chain and reports where designs are lost, stage by stage;
  * `--example` prints one worked example from a parameter vector to a sized
                schematic, its measured specs, and its eye.

THE CHAIN, AND THAT EVERY LINK IS REAL
---------------------------------------
    params
      -> to_geometry()          drawn SKY130 resistors and MIM caps
      -> TailDevice             a real current mirror, one per side
      -> run_point(ac_sweep=True, hd3=True, swing=True)
                                .op .ac .noise .dc .tran, one ngspice call
      -> device_result_from_point()
                                pole-zero FIT, rejected above 0.5 dB (§5.3b)
      -> evaluate_link()        channel + TX + CTLE -> pulse -> cursors
                                -> eye height in VOLTS, width in UI
      -> reward_v1              one scalar, now including S8

`device/mock.py` and `link/mock.py` are not imported, reachable, or used.

WHAT THE FUNNEL IS FOR, AND WHY IT IS THE ACTUAL RESULT
-------------------------------------------------------
A single passing example proves the plumbing. It does not tell you whether the
approved box CONTAINS designs that close the loop, and that turned out to be
the interesting question the moment the bridge first ran.

The funnel counts, in order: does it simulate, does the fit hold, does it meet
S3, does the small-signal model still apply at the link's own drive level, and
does the eye clear S8. **The compression stage is the one that matters** — see
`G2_RESULTS.md`.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from nebula.common.types import (
    SPEC_EYE_H_MIN_V,
    SPEC_EYE_W_MIN_UI,
    SPEC_F_PEAK_HZ_RANGE,
    SPEC_PEAKING_DB_RANGE,
)
from nebula.device.passives import to_geometry
from nebula.device.sky130_runner import SizingPoint, run_point
from nebula.device.tail import TailDevice, min_nf_for_width
from nebula.link.bridge import device_result_from_point, evaluate_link
from nebula.link.config import LinkConfig
from nebula.rl.contract import (
    ACTION_SPACE,
    CL_CONTEXT_F,
    NF_IN_FIXED,
    TAIL_MIRROR_RATIO,
    VDD_NOMINAL_V,
    sizing_from_u,
)

HERE = Path(__file__).resolve().parent
RESULTS_JSONL: Path = HERE / "g2_closed_loop_run.jsonl"

#: The channel the funnel is scored at. The TOP of the derived family, because
#: it is the hardest member and because `CHANNEL_MODEL.md` §5 measured the eye
#: open at all 21 members — so a design that closes here closes everywhere.
FUNNEL_LOSS_DB: float = 12.0

#: The stages, in the order a design is lost at them. Order matters: it is
#: cause-before-symptom (G68), so "compressing" is only reported for a design
#: whose fit held and whose S3 is known.
STAGES: tuple[str, ...] = (
    "proposed", "simulated", "fit_ok", "s3_met", "small_signal_valid",
    "eye_open", "s8_met",
)


def _sizing_to_point(params: dict, *, corner_passives: str = "typical"
                     ) -> SizingPoint:
    """The same geometry + tail the RL evaluator builds (rule 9, one mapping)."""
    geo = to_geometry(params["rs"], params["cs"], params["rl"],
                      corner=corner_passives)
    i_side = 0.5 * float(params["i_bias"])
    from nebula.rl.contract import tail_sizing_rule
    j_um_per_a, l_tail_um = tail_sizing_rule()
    w_tail = i_side * j_um_per_a
    tail = TailDevice(w_tail=w_tail, l_tail=l_tail_um,
                      nf_tail=min_nf_for_width(w_tail, TAIL_MIRROR_RATIO),
                      mirror_ratio=TAIL_MIRROR_RATIO)
    return SizingPoint.from_params(params, vdd=VDD_NOMINAL_V, tail=tail,
                                   passives=geo)


# ─────────────────────────────────────────────────────────────────────────────
# The fidelity tiers — half of G2's stated criterion.
# ─────────────────────────────────────────────────────────────────────────────


def measure_tiers(n_repeat: int = 21, seed: int = 20260817) -> dict:
    """What each analysis costs, cumulatively, on one real design.

    Cumulative rather than isolated because that is how they are actually
    bought: one ngspice invocation runs `.op`, `.ac` and `.noise` whatever
    else is asked for, so "the cost of `.ac`" alone is not a number anyone
    pays. The DIFFERENCES are the per-tier costs and they are reported as such.

    **G71'S PROTOCOL IN FULL, and the first version of this function needed
    it.** Run tier-by-tier with one discarded warm-up each, the table came out
    with `op_ac_noise` at 0.3841 s and `+ac_curve` at 0.3138 s — **a NEGATIVE
    increment for strictly more work**, because the tier that happens to go
    first pays the process-level cache warming whatever the per-tier warm-up
    does. That is G71 exactly, in this project's own measurement of its own
    gate criterion.

    So: **interleaved and shuffled.** Every repeat runs all four tiers in a
    freshly drawn random order, and a discarded warm-up precedes the whole
    thing. Single process throughout (G70: one concurrent ngspice makes each
    run 4.8x slower). The spread is reported beside every median, and
    `separable` says whether the increments survive it.
    """
    import random

    params = _reference_params()
    point = _sizing_to_point(params)
    rng = random.Random(seed)

    tiers = (
        ("op_ac_noise", dict(swing=False, ac_sweep=False, hd3=False)),
        ("+ac_curve", dict(swing=False, ac_sweep=True, hd3=False)),
        ("+dc_swing", dict(swing=True, ac_sweep=True, hd3=False)),
        ("+hd3_tran", dict(swing=True, ac_sweep=True, hd3=True)),
    )
    kw_of = dict(tiers)
    names = [n for n, _ in tiers]

    for name in names:                        # discarded warm-up (G71)
        run_point(point, "tt", **kw_of[name])

    samples: dict = {n: [] for n in names}
    failed: dict = {}
    for _ in range(n_repeat):
        order = names[:]
        rng.shuffle(order)                    # re-drawn per repeat
        for name in order:
            t0 = time.perf_counter()
            r = run_point(point, "tt", **kw_of[name])
            dt = time.perf_counter() - t0
            if not r.ok:
                failed[name] = r.fail_reason
            else:
                samples[name].append(dt)

    out: dict = {"n_repeat": n_repeat, "seed": seed, "tiers": {},
                 "protocol": "interleaved, order re-shuffled per repeat, "
                             "warm-up discarded, single process (G70/G71)"}
    for name in names:
        if name in failed:
            out["tiers"][name] = {"failed": failed[name]}
            continue
        ts = np.asarray(samples[name])
        out["tiers"][name] = {
            "median_s": float(np.median(ts)),
            # THE MINIMUM IS THE ESTIMATOR THE INCREMENTS ARE READ FROM, and
            # that is a considered choice rather than the flattering one.
            # Process-launch and OS-scheduling noise is strictly ADDITIVE and
            # one-sided: nothing makes an ngspice run faster than the work it
            # does, so the minimum over repeats is the cleanest estimate of
            # that work while the median carries however much contention the
            # machine happened to have. The medians are reported beside it, and
            # if the two disagree about the ORDERING that is a finding.
            "min_s": float(np.min(ts)),
            "p10_s": float(np.percentile(ts, 10)),
            "p90_s": float(np.percentile(ts, 90)),
            "n": int(ts.size),
        }
    # Are the increments bigger than the noise? A median difference smaller
    # than the p10-p90 spread of either arm is not separable at this n, and
    # saying so is 7h's ranking rule applied to a cost table.
    prev = None
    for name in names:
        v = out["tiers"][name]
        if "median_s" not in v:
            prev = None
            continue
        if prev is not None:
            v["increment_s"] = v["min_s"] - prev["min_s"]
            v["increment_median_s"] = v["median_s"] - prev["median_s"]
            # Separable against the MINIMUM's own resolution, which is the
            # p10-min gap -- how far the best run sits below the tenth
            # percentile. That is the noise floor of a min estimator.
            floor = max(prev["p10_s"] - prev["min_s"], v["p10_s"] - v["min_s"])
            v["separable"] = bool(abs(v["increment_s"]) > floor)
            v["orderings_agree"] = bool(
                (v["increment_s"] > 0) == (v["increment_median_s"] > 0))
        prev = v

    # The link half, which needs no simulator at all once the point is run.
    pt = run_point(point, "tt", swing=True, ac_sweep=True, hd3=True)
    dev = device_result_from_point(pt)
    cfg = LinkConfig(channel_loss_db_at_nyquist=FUNNEL_LOSS_DB)
    if dev.ok:
        ts = []
        for _ in range(n_repeat):
            t0 = time.perf_counter()
            evaluate_link(dev, cfg)
            ts.append(time.perf_counter() - t0)
        out["link_eval_median_s"] = float(np.median(ts))
        ts = []
        for _ in range(n_repeat):
            t0 = time.perf_counter()
            device_result_from_point(pt)
            ts.append(time.perf_counter() - t0)
        out["fit_median_s"] = float(np.median(ts))
    return out


#: The G2 worked example: the design with the largest eye among the ten that
#: met **both S3 and S8** in the 300-sample funnel (`--funnel`, seed 20260817,
#: row i=110).
#:
#: **FOUND BY THE SEARCH, NOT HAND-PICKED FROM OUTSIDE IT.** That distinction
#: matters for what the example is evidence of: it shows the approved box
#: contains designs that close the loop, which a design tuned by hand outside
#: the box would not. Every number in `G2_RESULTS.md` §5 comes from re-running
#: this vector.
G2_EXAMPLE_PARAMS: dict = {
    "w_in": 3.88729525333231e-05,
    "l_in": 1.8762178360731811e-07,
    "nf_in": 4.0,
    "i_bias": 0.003078662088375654,
    "rs": 697.7116931837649,
    "cs": 1.013407656022105e-12,
    "rl": 653.1147421852527,
    "cl": 3.262805963205924e-14,
    "vcm_in": 1.1838385405219503,
}


def _reference_params() -> dict:
    """One realisable design, at the middle of the approved box.

    The MIDPOINT rather than a hand-picked winner: a cost measured on an
    unusually easy or hard point is a cost of that point.
    """
    u = np.full(len(ACTION_SPACE), 0.5)
    return dict(sizing_from_u(u, cl_f=CL_CONTEXT_F).params)


# ─────────────────────────────────────────────────────────────────────────────
# The funnel.
# ─────────────────────────────────────────────────────────────────────────────


def _lhs(n: int, d: int, rng: np.random.Generator) -> np.ndarray:
    cut = np.linspace(0.0, 1.0, n + 1)
    u = np.empty((n, d))
    for j in range(d):
        pts = rng.uniform(cut[:n], cut[1:])
        u[:, j] = rng.permutation(pts)
    return u


def run_funnel(n: int, seed: int, out_path: Path,
               loss_db: float = FUNNEL_LOSS_DB,
               corner: str = "tt") -> Path:
    """LHS over the approved box, through the whole chain. Streams JSONL."""
    rng = np.random.default_rng(seed)
    u = _lhs(n, len(ACTION_SPACE), rng)
    cfg = LinkConfig(channel_loss_db_at_nyquist=loss_db)
    lo_pk, hi_pk = SPEC_PEAKING_DB_RANGE
    lo_f, hi_f = SPEC_F_PEAK_HZ_RANGE

    header = {
        "row": "header",
        "written_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n": n, "seed": seed, "corner": corner,
        "channel_loss_db_at_nyquist": loss_db,
        "cl_f": float(CL_CONTEXT_F), "vdd_v": float(VDD_NOMINAL_V),
        "nf_in": int(NF_IN_FIXED),
        "v_in_diff_pp_v": float(cfg.v_in_diff_pp_v),
        "v_in_nyquist_pp_v": float(cfg.v_in_nyquist_pp_v),
        "box": {d.name: [d.lo, d.hi] for d in ACTION_SPACE},
        "spec": {"peaking_db": list(SPEC_PEAKING_DB_RANGE),
                 "f_peak_hz": list(SPEC_F_PEAK_HZ_RANGE),
                 "eye_h_min_v": SPEC_EYE_H_MIN_V,
                 "eye_w_min_ui": SPEC_EYE_W_MIN_UI},
        "note": ("No mock is imported or reachable. Every number below is "
                 "measured or derived from a measurement."),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    with out_path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(header) + "\n")
        for i in range(n):
            row = {"i": i, "stage": "proposed"}
            params = dict(sizing_from_u(u[i], cl_f=CL_CONTEXT_F).params)
            row["params"] = params
            try:
                point = _sizing_to_point(params)
            except Exception as exc:                        # noqa: BLE001
                row["reason"] = f"unrealisable geometry: {exc}"
                fh.write(json.dumps(row) + "\n")
                continue

            pt = run_point(point, corner, swing=True, ac_sweep=True, hd3=True)
            if not pt.ok:
                row["reason"] = pt.fail_reason
                fh.write(json.dumps(row) + "\n")
                continue
            row["stage"] = "simulated"
            row["runtime_s"] = round(pt.runtime_s, 4)

            dev = device_result_from_point(pt)
            if not dev.ok:
                row["reason"] = dev.fail_reason
                fh.write(json.dumps(row) + "\n")
                continue
            row["stage"] = "fit_ok"
            row.update({
                "g_dc_db": dev.g_dc_db, "fit_residual_db": dev.fit_residual_db,
                "f_zero_hz": dev.f_zero_hz, "f_pole1_hz": dev.f_pole1_hz,
                "f_pole2_hz": dev.f_pole2_hz,
                "peaking_db": dev.peaking_db, "f_peak_hz": dev.f_peak_hz,
                "hd3_dbc": dev.hd3_dbc, "vn_in_vrms": dev.vn_in_vrms,
                "power_w": dev.power_w, "area_mm2": dev.area_mm2,
                "vout_swing_v": dev.vout_swing_v,
            })

            s3 = (lo_pk <= dev.peaking_db <= hi_pk
                  and lo_f <= dev.f_peak_hz <= hi_f)
            row["s3_met"] = bool(s3)
            if s3:
                row["stage"] = "s3_met"

            det: list = []
            lr = evaluate_link(dev, cfg, detail=det)
            if not lr.ok:
                row["link_fail_reason"] = lr.fail_reason
                fh.write(json.dumps(row) + "\n")
                continue
            d = det[0]
            row["peak_excursion_pp_v"] = d.peak_excursion_pp_v
            row["analytic_out_pp_v"] = d.v_out_pp_v
            row["gain_at_nyquist_db"] = d.gain_at_nyquist_db
            row["swing_is_lower_bound"] = d.swing_is_lower_bound
            if s3:
                row["stage"] = "small_signal_valid"
            row.update({"eye_h_v": lr.eye_h_v, "eye_w_ui": lr.eye_w_ui,
                        "ber": lr.ber, "dfe_tap": lr.dfe_tap})
            if lr.eye_h_v > 0.0 and s3:
                row["stage"] = "eye_open"
            s8 = (lr.eye_h_v >= SPEC_EYE_H_MIN_V
                  and lr.eye_w_ui >= SPEC_EYE_W_MIN_UI)
            row["s8_met"] = bool(s8)
            if s8 and s3:
                row["stage"] = "s8_met"
            fh.write(json.dumps(row) + "\n")
            if (i + 1) % 25 == 0:
                print(f"  {i + 1}/{n}  {time.perf_counter() - t0:6.1f} s",
                      flush=True)
        fh.write(json.dumps({"row": "footer",
                             "wall_clock_s": round(time.perf_counter() - t0, 2)})
                 + "\n")
    return out_path


def analyse(path: Path) -> dict:
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    header = rows[0]
    footer = rows[-1] if rows[-1].get("row") == "footer" else {}
    body = [r for r in rows if "i" in r]

    counts = {s: 0 for s in STAGES}
    for r in body:
        reached = STAGES.index(r.get("stage", "proposed"))
        for k in range(reached + 1):
            counts[STAGES[k]] += 1

    # Independent tallies: S3 and compression are NOT nested, so a funnel alone
    # would hide a design that compresses but meets S3 and vice versa.
    n_s3 = sum(1 for r in body if r.get("s3_met"))
    n_compress = sum(1 for r in body
                     if "output swing" in (r.get("link_fail_reason") or ""))
    n_link_ok = sum(1 for r in body if r.get("eye_h_v") is not None)
    n_s8 = sum(1 for r in body if r.get("s8_met"))
    n_both = sum(1 for r in body if r.get("s3_met") and r.get("s8_met"))

    fit = [r["fit_residual_db"] for r in body if r.get("fit_residual_db") is not None]
    ratio = [r["peak_excursion_pp_v"] / r["vout_swing_v"]
             for r in body
             if r.get("peak_excursion_pp_v") and r.get("vout_swing_v")]
    compress_ratio = []
    for r in body:
        why = r.get("link_fail_reason") or ""
        if "output swing" in why and r.get("vout_swing_v"):
            import re
            m = re.search(r"output swing ([\d.]+) mVpp", why)
            if m:
                compress_ratio.append(float(m.group(1)) * 1e-3 / r["vout_swing_v"])

    return {
        "header": header, "footer": footer, "n": len(body),
        "funnel": counts,
        "independent": {
            "s3_met": n_s3, "link_evaluated": n_link_ok,
            "compression_rejected": n_compress,
            "s8_met": n_s8, "s3_and_s8": n_both,
        },
        "fit_residual_db": fit,
        "compression_ratio": compress_ratio + ratio,
    }


def _dist(a, unit: str = "") -> str:
    v = np.asarray([x for x in a if x is not None and np.isfinite(x)], dtype=float)
    if not v.size:
        return "n=0"
    return (f"n={v.size:4d}  median {np.median(v):8.4f}{unit}  "
            f"p10 {np.percentile(v, 10):8.4f}  p90 {np.percentile(v, 90):8.4f}  "
            f"max {v.max():8.4f}")


def print_funnel(res: dict) -> None:
    h = res["header"]
    print("=" * 78)
    print("G2 -- one full evaluation, end to end, no mock in the path")
    print("=" * 78)
    print(f"  {res['n']} LHS samples of the approved box, seed {h['seed']}, "
          f"corner {h['corner']}")
    print(f"  channel {h['channel_loss_db_at_nyquist']} dB at Nyquist, "
          f"cl = {h['cl_f'] * 1e15:.2f} fF")
    print(f"  CTLE input: {h['v_in_diff_pp_v'] * 1e3:.1f} mVpp long-run, "
          f"{h['v_in_nyquist_pp_v'] * 1e3:.1f} mVpp at Nyquist")
    print(f"  wall clock {res['footer'].get('wall_clock_s')} s")
    print()
    print("-" * 78)
    print("THE FUNNEL -- where designs are lost, cause before symptom")
    print("-" * 78)
    prev = None
    for s in STAGES:
        c = res["funnel"][s]
        frac = f"{100.0 * c / res['n']:6.2f} %" if res["n"] else "     -"
        drop = "" if prev is None else f"   (-{prev - c})"
        print(f"  {s:22s} {c:5d}  {frac}{drop}")
        prev = c
    print()
    ind = res["independent"]
    print("-" * 78)
    print("INDEPENDENT TALLIES -- S3 and compression are NOT nested")
    print("-" * 78)
    for k, v in ind.items():
        print(f"  {k:24s} {v:5d}")
    print()
    print("-" * 78)
    print("DISTRIBUTIONS")
    print("-" * 78)
    print(f"  pole-zero fit residual [dB]  {_dist(res['fit_residual_db'])}")
    print(f"  peak excursion / swing limit {_dist(res['compression_ratio'])}")
    print("  (> 1.0 means the small-signal model no longer applies -- C4)")
    print("=" * 78)


# ─────────────────────────────────────────────────────────────────────────────
# The worked example.
# ─────────────────────────────────────────────────────────────────────────────


def worked_example(params: Optional[dict] = None,
                   loss_db: float = FUNNEL_LOSS_DB,
                   corner: str = "tt") -> dict:
    """One parameter vector, printed all the way to an eye and a reward."""
    from nebula.rl import reward_v1 as R

    params = params or dict(G2_EXAMPLE_PARAMS)
    point = _sizing_to_point(params)
    geo = point.passives
    pt = run_point(point, corner, swing=True, ac_sweep=True, hd3=True)
    dev = device_result_from_point(pt)
    cfg = LinkConfig(channel_loss_db_at_nyquist=loss_db)
    det: list = []
    lr = evaluate_link(dev, cfg, detail=det) if dev.ok else None

    return {
        "params": params, "point": point, "geo": geo, "pt": pt, "dev": dev,
        "link": lr, "detail": det[0] if det else None, "cfg": cfg,
    }


def print_example(ex: dict) -> None:
    params, point, geo = ex["params"], ex["point"], ex["geo"]
    pt, dev, lr, d = ex["pt"], ex["dev"], ex["link"], ex["detail"]
    print("=" * 78)
    print("ONE WORKED EVALUATION -- parameter vector to eye")
    print("=" * 78)
    print("  1. PARAMETERS (the RL action space, physical units)")
    for k in ("w_in", "l_in", "i_bias", "rs", "cs", "rl", "vcm_in"):
        print(f"       {k:8s} {params[k]:12.6g}")
    print(f"       {'nf_in':8s} {params['nf_in']:12.0f}   (fixed, G38)")
    print(f"       {'cl':8s} {params['cl']:12.6g}   (context, CL_RANGE.md)")
    print()
    print("  2. THE SCHEMATIC -- drawn SKY130 devices, this is the deliverable")
    print(f"       input pair  W={point.w:g} um L={point.l:g} um nf={point.nf}")
    if point.tail:
        t = point.tail
        print(f"       tail        W={t.w_tail:.3g} um L={t.l_tail:g} um "
              f"nf={t.nf_tail}, mirror 1:{t.mirror_ratio:g}")
    for nm, g in (("Rs", geo.rs), ("Cs", geo.cs), ("RL", geo.rl)):
        print(f"       {nm:11s} {g.subckt.rsplit('__', 1)[-1]} "
              f"w={g.w_um:g} l={g.l_um:g} m={g.m}   "
              f"({'R' if nm != 'Cs' else 'C'} error "
              f"{100 * g.rel_error:+.2f} %)")
    print(f"       passive area {geo.area_um2:.1f} um^2 "
          f"= {geo.area_mm2:.6f} mm^2")
    print()
    print("  3. MEASURED SPECS (one ngspice call: .op .ac .noise .dc .tran)")
    if not pt.ok:
        print(f"       SIMULATION FAILED: {pt.fail_reason}")
        return
    print(f"       S3 peaking     {dev.peaking_db if dev.ok else float('nan'):8.3f} dB"
          f"   @ {(dev.f_peak_hz / 1e9) if dev.ok else float('nan'):.4f} GHz")
    print(f"       S3 nyq boost   {pt.nyquist_boost_db:8.3f} dB")
    print(f"       S4 HD3         {pt.hd3_dbc:8.2f} dBc  @ "
          f"{pt.hd3_detail['f_tone_hz'] / 1e6:.0f} MHz, "
          f"{pt.hd3_detail['vin_diff_pk_v'] * 1e3:.0f} mV pk")
    print(f"       S5 noise       {pt.vn_in_vrms * 1e3:8.4f} mV_rms")
    print(f"       S6 power       {pt.power_measured_w * 1e3:8.4f} mW  (measured supply)")
    print(f"       S7 area        {geo.area_mm2:8.6f} mm^2 (passives, lower bound)")
    print()
    if not dev.ok:
        print(f"  4. THE FIT REJECTED IT: {dev.fail_reason}")
        return
    print("  4. POLE-ZERO FIT (the bridge's first half)")
    print(f"       g_dc  {dev.g_dc:10.5f} V/V = {dev.g_dc_db:+7.3f} dB")
    print(f"       f_zero  {dev.f_zero_hz / 1e9:8.4f} GHz")
    print(f"       f_pole1 {dev.f_pole1_hz / 1e9:8.4f} GHz   "
          f"(k = f_p1/f_z = {dev.f_pole1_hz / dev.f_zero_hz:.4f})")
    print(f"       f_pole2 {dev.f_pole2_hz / 1e9:8.4f} GHz")
    print(f"       residual {dev.fit_residual_db:7.4f} dB   "
          f"(gate: reject above 0.5 dB, §5.3b)")
    print()
    print("  5. THE EYE (channel + TX + CTLE + ideal 1-tap DFE)")
    if lr is None or not lr.ok:
        print(f"       LINK REJECTED IT: {lr.fail_reason if lr else 'n/a'}")
    else:
        print(f"       eye height   {lr.eye_h_mv:8.2f} mV    "
              f"(S8 needs > {SPEC_EYE_H_MIN_V * 1e3:.0f} mV)")
        print(f"       eye width    {lr.eye_w_ui:8.4f} UI    "
              f"(S8 needs > {SPEC_EYE_W_MIN_UI} UI)")
        snr = d.snr_at_slicer
        print(f"       BER bound    {lr.ber:8.3g}   "
              f"(0 = underflow; read the SNR)")
        print(f"       SNR@slicer   {snr:8.1f} = "
              f"{20 * math.log10(snr):+.1f} dB   DEVICE NOISE ONLY")
        print(f"       DFE tap      {lr.dfe_tap:+8.4f}")
        print(f"       gain @ Nyq   {d.gain_at_nyquist_db:+8.3f} dB")
        print(f"       peak swing   {d.peak_excursion_pp_v * 1e3:8.2f} mVpp "
              f"against a {d.vout_swing_v * 1e3:.2f} mVpp limit"
              + ("  (limit is a LOWER BOUND)" if d.swing_is_lower_bound else ""))
    print("=" * 78)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--tiers", action="store_true")
    ap.add_argument("--funnel", action="store_true")
    ap.add_argument("--example", action="store_true")
    ap.add_argument("--analyse", type=Path)
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=20260817)
    ap.add_argument("--loss-db", type=float, default=FUNNEL_LOSS_DB)
    ap.add_argument("--out", type=Path, default=RESULTS_JSONL)
    a = ap.parse_args(argv)

    if a.tiers:
        res = measure_tiers()
        print("=" * 78)
        print("FIDELITY TIERS -- cumulative cost per ngspice invocation")
        print("=" * 78)
        print(f"  {res['n_repeat']} repeats; {res['protocol']}")
        print()
        print(f"  {'tier':14s} {'min s':>9s} {'median s':>9s} {'p90':>8s} "
              f"{'increment':>10s}  separable")
        print(f"  {'':14s} {'(the cost)':>9s} {'(+noise)':>9s}")
        for name, v in res["tiers"].items():
            if "failed" in v:
                print(f"  {name:14s} FAILED: {v['failed'][:60]}")
                continue
            inc = v.get("increment_s")
            sep = v.get("separable")
            inc_s = "        -" if inc is None else f"{inc:+10.4f}"
            sep_s = "-" if sep is None else ("yes" if sep else "NO")
            print(f"  {name:14s} {v['min_s']:9.4f} {v['median_s']:9.4f} "
                  f"{v['p90_s']:8.4f} {inc_s}  {sep_s}")
        vals = [v for v in res["tiers"].values() if "median_s" in v]
        if len(vals) >= 2:
            total = vals[-1]["min_s"] - vals[0]["min_s"]
            spread = max(v["p10_s"] - v["min_s"] for v in vals)
            print()
            print(f"  TOTAL added by the three extra tiers: {total:+.4f} s "
                  f"({vals[-1]['min_s'] / vals[0]['min_s']:.2f}x)")
            n_sep = sum(1 for v in vals if v.get("separable"))
            n_inc = sum(1 for v in vals if "separable" in v)
            print(f"  Min-estimator noise floor: {spread:.4f} s -> the TOTAL is "
                  f"{'separable' if total > spread else 'NOT separable'}; "
                  f"{n_sep} of {n_inc} individual increments are.")
            disagree = [k for k, v in res["tiers"].items()
                        if v.get("orderings_agree") is False]
            if disagree:
                print(f"  WARNING: min and median disagree on the SIGN of the "
                      f"increment for {disagree} -- do not quote either.")
            else:
                print("  The min and median estimators agree on every ordering.")
            print()
        if "fit_median_s" in res:
            print(f"  {'pole-zero fit':14s} {res['fit_median_s']:7.4f} s  "
                  f"(no simulator)")
            print(f"  {'link eval':14s} {res['link_eval_median_s']:7.4f} s  "
                  f"(no simulator)")
        print("=" * 78)
        return 0

    if a.example:
        print_example(worked_example(loss_db=a.loss_db))
        return 0

    if a.funnel:
        print(f"running the funnel: {a.n} designs ...", flush=True)
        p = run_funnel(a.n, a.seed, a.out, loss_db=a.loss_db)
        print(f"wrote {p}")
        print_funnel(analyse(p))
        return 0

    if a.analyse:
        print_funnel(analyse(a.analyse))
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
