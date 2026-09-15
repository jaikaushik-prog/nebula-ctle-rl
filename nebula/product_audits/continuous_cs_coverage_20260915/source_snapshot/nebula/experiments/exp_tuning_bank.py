"""
experiments/exp_tuning_bank.py — **the 2-D bank: `Rs` sets the boost, `Cs` sets
where it peaks, and PVT drift is absorbed by re-tuning rather than by luck.**

WHY A SECOND AXIS, WHEN A BANK ALREADY EXISTS
-----------------------------------------------
`exp_tunable_trade.py` (session 22s) builds an 8-setting bank that holds
**`Rs * Cs` constant** so the zero -- and therefore the peak -- deliberately
**does not move**. That is a *peaking* bank, and it answered the question it was
built for (what the peaking control trades: drive handling, G103).

It cannot answer the question this file exists for. The competition slide says

    HF peaking boost 3-12 dB (**tunable 1.25-2.5 GHz**);
    1-Stage CTLE w/ source degeneration (**variable Rs, Cs**)

and "tunable" governs **both** ranges, exactly as it does for the 3-12 dB.
Under the alternative reading -- one fixed sizing whose peak stays inside
1.25-2.5 GHz at every PVT corner -- session 23 measured the consequence and it
is close to fatal:

    design                45 mandated corners, design load    request range servable
    57cba07581cd  spread 0.938 oct  ->  1.693 - 1.768 GHz  ->  **4.4 %** of the window
    c507a3ba6f58  spread 0.99979    ->  1.768 GHz exactly  ->  **0.0 %**

**A judge asking for a peak at 1.5 GHz or 2.2 GHz cannot be served by any fixed
design.** That is not a shortfall in our search; it is arithmetic, because PVT
alone moves the peak by most of the window the spec allows. The reading that
makes the spec satisfiable is the one every production adaptive CTLE
implements: **a knob, turned per part.**

WHAT THIS FILE MEASURES, STATED BEFORE IT RUNS
-----------------------------------------------
Two numbers, and neither is allowed to be softened afterwards:

1. **Tuning range.** Over the bank's settings at nominal, what span of
   `f_peak` and `peaking` is reachable? The claim to support is *"covers
   1.25-2.5 GHz and 3-12 dB"*, and if it does not, the measured span is the
   result.
2. **PVT compensation, and this is the compliance criterion.**

       At every one of the 45 mandated PVT corners, is there AT LEAST ONE bank
       setting meeting all twelve `V5_SPECS` rows -- and which setting is it?

   Reported per corner, never as an aggregate that hides which corners needed
   which setting. A corner served only by the extreme setting is a corner with
   no tuning margin left, and that has to be visible.

HOW THE BANK IS BUILT, AND THE TRAP IN BUILDING IT
----------------------------------------------------
For a degenerated pair the two controls are not independent in the obvious way:

    peaking  ~  20 log10(1 + (gm + gmbs) Rs / 2)      <- Rs
    zero     =  1 / (2 pi Rs Cs)                       <- Rs AND Cs

so **moving `Rs` for boost drags the zero, and the peak with it.** The bank
therefore moves `Rs` for the boost axis and then moves `Cs` to put the zero
back -- which is what a switched bank with complementary R and C segments does.
Both axes are swept explicitly here rather than solved analytically, because
§6's design equations were measured over-predicting the Nyquist boost by
0.8-1.5 dB and growing with `Rs` (G60): the grid is measured, the equations
only choose where to look.

**G63 APPLIES AND IT IS THE EXPENSIVE PART.** The search path uses **drawn**
passives (`build_point(real_passives=True)`), so a setting **cannot** be applied
with ngspice `alter` the way `experiments/tunable.py` does -- with drawn
passives there is no `Rs` element to alter, `alter` fails **silently**, and every
setting returns the first geometry's numbers and exits 0. Each setting is
therefore a full re-parse and a real SPICE run, and the cost model in this file
budgets it that way. Any future speed-up must prove the ideal-element inner
search transfers before it is used for a published number.

    python -m nebula.experiments.exp_tuning_bank --run
    python -m nebula.experiments.exp_tuning_bank --analyse
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

import nebula.rl.reward_v1 as R
from nebula.common.types import Corner, all_corners
from nebula.experiments.adaptive_screen import (
    CL_MID_F,
    ScreenPoint,
    evaluate_at_points,
)
from nebula.rl.contract import ACTION_NAMES, design_id, sizing_from_u

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "tuning_bank_results.json"


def results_path(n_rs: int, n_cs: int, rs_span: float, cs_span: float) -> Path:
    """Where a run of THIS geometry writes. **Anti-clobber, not cosmetics.**

    Section 5z's 45-of-45 was measured at the committed default geometry and is
    quoted in `PROGRESS.md`, `HANDOFF.md` and a commit message. Row 4aa widens
    the boost axis; a wider run writing to the same path would overwrite that
    measurement and every citation of it would silently start pointing at
    different numbers -- the exact shape CLAUDEwa.md sec 8 rule 10 forbids.

    The default geometry keeps the historical filename so nothing that already
    reads `tuning_bank_results.json` breaks. Any other geometry is tagged with
    all four knobs, so two different banks can never collide on one file.
    `nebula/tests/test_tuning_bank.py` proves both halves can fail.
    """
    if (n_rs, n_cs, float(rs_span), float(cs_span)) == (
            N_RS_SETTINGS, N_CS_SETTINGS, float(RS_SPAN), float(CS_SPAN)):
        return RESULTS
    return HERE / (f"tuning_bank_{n_rs}x{n_cs}"
                   f"_rs{float(rs_span):g}_cs{float(cs_span):g}_results.json")

#: Which normalised coordinates the bank moves. `Rs` is the boost axis, `Cs`
#: the frequency axis. Read from `ACTION_NAMES` rather than hard-coded, so a
#: change to the action space breaks loudly here instead of silently tuning
#: the wrong device.
I_RS: int = ACTION_NAMES.index("rs")
I_CS: int = ACTION_NAMES.index("cs")

#: Bank size: 3 boost settings x 5 frequency settings = 15. Three bits of
#: control in total, which is what a real part exposes. The frequency axis is
#: finer because it is the one that has to absorb PVT drift; the boost axis
#: only has to reach the requested value.
N_RS_SETTINGS: int = 3
N_CS_SETTINGS: int = 5

#: How far each axis moves, in NORMALISED box units, either side of the base
#: design. `cs` is log-scaled in the box, and session 22s measured its
#: sensitivity at **3.243 octaves of f_peak per box width**, so one octave of
#: peak -- the whole of S3's window -- needs 1/3.243 = **0.308 box widths**.
#: +/-0.20 therefore reaches +/-0.65 octaves, comfortably more than the
#: 0.30-octave PVT excursion it has to absorb, without running the axis into
#: the box edges from a mid-box base design.
CS_SPAN: float = 0.20
RS_SPAN: float = 0.12


@dataclass(frozen=True)
class Setting:
    """One bank setting: an index pair and the sizing it selects."""

    i_rs: int
    i_cs: int
    u: tuple

    @property
    def label(self) -> str:
        return f"R{self.i_rs}C{self.i_cs}"


def bank(base_u: Sequence[float], n_rs: int = N_RS_SETTINGS,
         n_cs: int = N_CS_SETTINGS, rs_span: float = RS_SPAN,
         cs_span: float = CS_SPAN) -> list[Setting]:
    """The settings, as sizings. **Only `rs` and `cs` move.**

    Every other coordinate is the base design's, which is what makes this a
    tuning bank rather than a second search: the transistors, the bias and the
    load are drawn once and the knob switches passive segments.
    """
    base = np.clip(np.asarray(base_u, dtype=float), 0.0, 1.0)
    rs_vals = ([base[I_RS]] if n_rs == 1 else
               np.linspace(base[I_RS] - rs_span, base[I_RS] + rs_span, n_rs))
    cs_vals = ([base[I_CS]] if n_cs == 1 else
               np.linspace(base[I_CS] - cs_span, base[I_CS] + cs_span, n_cs))
    out: list[Setting] = []
    for a, rv in enumerate(rs_vals):
        for b, cv in enumerate(cs_vals):
            u = base.copy()
            u[I_RS] = float(np.clip(rv, 0.0, 1.0))
            u[I_CS] = float(np.clip(cv, 0.0, 1.0))
            out.append(Setting(a, b, tuple(float(x) for x in u)))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 1. The tuning range, at nominal.
# ─────────────────────────────────────────────────────────────────────────────


def tuning_range(settings: Sequence[Setting],
                 corner: Corner = Corner(process="tt", vdd_scale=1.0,
                                         temp_c=27.0),
                 cl_f: float = CL_MID_F) -> dict:
    """What the knob reaches at TT. **One SPICE run per setting.**

    Reports the measured span of `f_peak` and `peaking`, and how much of S3's
    two ranges each covers. A bank that does not reach the whole window is
    reported as reaching what it reaches; the shortfall is the finding.
    """
    pts = [ScreenPoint(corner, cl_f, "tuning-range probe at TT")]
    rows = []
    n_sims = 0
    for st in settings:
        ev = evaluate_at_points(st.u, pts, ac_only=True)
        n_sims += ev.n_sims
        p = ev.points[0] if ev.points else None
        rows.append({"setting": st.label, "i_rs": st.i_rs, "i_cs": st.i_cs,
                     "ok": bool(p and p.ok),
                     "f_peak_hz": (None if not (p and p.ok) else
                                   2.5e9 * 2.0 ** p.f_peak_oct),
                     "peaking_db": (None if not (p and p.ok) else p.peaking_db)})
    good = [r for r in rows if r["ok"]]
    f = [r["f_peak_hz"] for r in good]
    pk = [r["peaking_db"] for r in good]
    return {
        "n_settings": len(settings), "n_ok": len(good), "n_sims": n_sims,
        "f_peak_lo_hz": (min(f) if f else None),
        "f_peak_hi_hz": (max(f) if f else None),
        "f_peak_span_oct": (math.log2(max(f) / min(f)) if f and min(f) > 0
                            else None),
        "peaking_lo_db": (min(pk) if pk else None),
        "peaking_hi_db": (max(pk) if pk else None),
        # S3's window is EXACTLY one octave, so the fraction covered is the
        # span in octaves. Clipped at the window edges: reaching BEYOND the
        # window is not extra coverage, it is out of spec.
        "window_covered_frac": (None if not f else
                                (min(math.log2(min(max(max(f), 1.25e9), 2.5e9)
                                               / 1.25e9), 1.0)
                                 - max(math.log2(min(max(min(f), 1.25e9), 2.5e9)
                                                 / 1.25e9), 0.0))),
        "settings": rows,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. PVT compensation — the compliance criterion.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class CornerCoverage:
    """One PVT corner: is there a setting that meets every row here?"""

    label: str
    served: bool
    best_setting: Optional[str] = None
    best_reward: Optional[float] = None
    n_settings_passing: int = 0
    failing_rows: list = field(default_factory=list)


def compensate(base_u: Sequence[float], target_f_peak_hz: float,
               target_peaking_db: float,
               settings: Optional[Sequence[Setting]] = None,
               corners: Optional[Sequence[Corner]] = None,
               cl_f: float = CL_MID_F,
               specs: Sequence[str] = R.V5_SPECS) -> dict:
    """**At every mandated PVT corner, is SOME setting compliant?**

    This is reading (B) of S3 made falsifiable. The fixed-sizing question is
    *"does one setting pass everywhere"*; this one is *"does the part have a
    setting for everywhere"*, which is what a tunable part promises and what
    `CL_RANGE.md` §9 anticipated on 2026-08-06.

    **Every corner is reported individually, with the setting that served it.**
    An aggregate "45 of 45" would hide the case that matters: a corner served
    only by the last setting on the knob has no tuning margin left, and the
    next lot of silicon walks off the end of the bank.
    """
    settings = list(settings if settings is not None else bank(base_u))
    corners = list(corners if corners is not None else all_corners())
    out: list[CornerCoverage] = []
    n_sims = 0
    used: dict = {}
    for c in corners:
        pts = [ScreenPoint(c, cl_f, "PVT compensation")]
        best = None
        best_st = None
        n_pass = 0
        rows: set = set()
        for st in settings:
            ev = evaluate_at_points(st.u, pts, target_f_peak_hz=target_f_peak_hz,
                                    target_peaking_db=target_peaking_db,
                                    specs=specs)
            n_sims += ev.n_sims
            if not ev.ok:
                continue
            if ev.feasible:
                n_pass += 1
            if best is None or ev.reward > best:
                best, best_st = ev.reward, st.label
            if not ev.feasible:
                rows.update(k for k, v in (ev.margins or {}).items() if v < 0)
        served = n_pass > 0
        label = (f"{c.process}/{c.vdd_scale:.2f}/{c.temp_c:g}C")
        out.append(CornerCoverage(label=label, served=served,
                                  best_setting=best_st, best_reward=best,
                                  n_settings_passing=n_pass,
                                  failing_rows=(sorted(rows) if not served
                                                else [])))
        if served and best_st:
            used[best_st] = used.get(best_st, 0) + 1
    return {
        "n_corners": len(out),
        "n_served": sum(1 for r in out if r.served),
        "n_sims": n_sims,
        "n_settings": len(settings),
        "settings_used": used,
        "corners": [asdict(r) for r in out],
    }


# ─────────────────────────────────────────────────────────────────────────────


def run(base_u: Optional[Sequence[float]] = None,
        target_f_peak_hz: Optional[float] = None,
        target_peaking_db: float = 7.5,
        n_rs: int = N_RS_SETTINGS, n_cs: int = N_CS_SETTINGS,
        rs_span: float = RS_SPAN, cs_span: float = CS_SPAN,
        tt_only: bool = False) -> dict:
    """Both measurements, on one base design. Writes its own artifact.

    `tt_only` runs measurement 1 and **skips** measurement 2 -- the cheap gate
    row 4aa asks for, because the tuning range costs `n_rs * n_cs` decks and the
    PVT compensation costs 45x that. A geometry whose boost axis does not reach
    S3's range should be found for 64 decks, not 2 880.
    """
    from nebula.experiments.adaptive_screen import TARGET_F_PEAK_HZ

    if base_u is None:
        base_u = _base_from_artifacts()
    target_f_peak_hz = float(target_f_peak_hz or TARGET_F_PEAK_HZ)
    t0 = time.time()
    settings = bank(base_u, n_rs=n_rs, n_cs=n_cs, rs_span=rs_span,
                    cs_span=cs_span)
    did = design_id(sizing_from_u(np.asarray(base_u)))
    out_path = results_path(n_rs, n_cs, rs_span, cs_span)
    print(f"base design {did}, {len(settings)} bank settings "
          f"({n_rs} boost x {n_cs} frequency, rs_span {rs_span:g}, "
          f"cs_span {cs_span:g}) -> {out_path.name}", flush=True)

    tr = tuning_range(settings)
    print(f"  tuning range: {tr['n_ok']}/{tr['n_settings']} settings scorable, "
          f"f_peak {(tr['f_peak_lo_hz'] or 0) / 1e9:.3f}-"
          f"{(tr['f_peak_hi_hz'] or 0) / 1e9:.3f} GHz "
          f"({tr['f_peak_span_oct'] or 0:.3f} oct), peaking "
          f"{tr['peaking_lo_db'] or 0:.2f}-{tr['peaking_hi_db'] or 0:.2f} dB",
          flush=True)

    if tt_only:
        cp = {"n_corners": 0, "n_served": 0, "n_sims": 0,
              "n_settings": len(settings), "settings_used": {}, "corners": [],
              "skipped": "tt_only: the 45-corner compensation was NOT run"}
        print("  PVT compensation: SKIPPED (--tt-only)", flush=True)
    else:
        cp = compensate(base_u, target_f_peak_hz, target_peaking_db,
                        settings=settings)
        print(f"  PVT compensation: {cp['n_served']}/{cp['n_corners']} mandated "
              f"corners served by at least one setting ({cp['n_sims']} sims)",
              flush=True)

    out = {
        "task": "the 2-D tuning bank: Rs sets boost, Cs sets frequency",
        "base_design_id": did, "base_u": list(base_u),
        "target_f_peak_hz": target_f_peak_hz,
        "target_peaking_db": target_peaking_db,
        "spec_set": list(R.V5_SPECS),
        "n_rs_settings": n_rs, "n_cs_settings": n_cs,
        "rs_span": rs_span, "cs_span": cs_span, "tt_only": bool(tt_only),
        "tuning_range": tr, "pvt_compensation": cp,
        "total_sims": tr["n_sims"] + cp["n_sims"],
        "wall_clock_s": time.time() - t0,
        "note": ("Drawn passives, so every setting is a full re-parse and a "
                 "real SPICE run: `alter` fails SILENTLY on drawn geometry "
                 "(G63) and must not be used here."),
    }
    out_path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def _base_from_artifacts() -> list:
    """The joint-search winner, **read from its artifact, never transcribed.**"""
    p = HERE / "joint_search_results.json"
    if not p.exists():
        raise FileNotFoundError(
            f"{p.name} missing: this file tunes an EXISTING design and will "
            f"not invent one. Run `exp_joint_search --run` first, or pass "
            f"--base-u.")
    d = json.loads(p.read_text(encoding="utf-8"))
    best = (d or {}).get("best")
    if not best or not best.get("ok"):
        raise ValueError("the recorded joint-search winner is not valid")
    return [float(x) for x in best["u"]]


def _report(d: dict) -> None:
    tr, cp = d["tuning_range"], d["pvt_compensation"]
    print()
    print("=" * 78)
    print(f"TUNING BANK — base {d['base_design_id']}, "
          f"{d['n_rs_settings']}x{d['n_cs_settings']} settings, "
          f"{d['total_sims']} SPICE runs, {d['wall_clock_s'] / 60:.1f} min")
    print("=" * 78)
    print("  1. TUNING RANGE at TT")
    print(f"     f_peak   {(tr['f_peak_lo_hz'] or 0) / 1e9:.3f} - "
          f"{(tr['f_peak_hi_hz'] or 0) / 1e9:.3f} GHz    "
          f"({tr['f_peak_span_oct'] or 0:.3f} octaves)")
    print(f"     peaking  {tr['peaking_lo_db'] or 0:.2f} - "
          f"{tr['peaking_hi_db'] or 0:.2f} dB")
    print(f"     S3 window 1.25-2.5 GHz covered: "
          f"{100.0 * (tr['window_covered_frac'] or 0.0):.1f} %")
    print()
    if cp.get("skipped"):
        print()
        print(f"  2. PVT COMPENSATION: {cp['skipped']}")
        return
    print("  2. PVT COMPENSATION (reading B of S3)")
    print(f"     {cp['n_served']} of {cp['n_corners']} mandated corners have at "
          f"least one compliant setting")
    print(f"     settings actually used: {cp['settings_used']}")
    bad = [c for c in cp["corners"] if not c["served"]]
    for c in bad[:10]:
        print(f"       UNSERVED {c['label']}: best {c['best_reward']}, "
              f"failing {c['failing_rows']}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--analyse", action="store_true")
    ap.add_argument("--peaking", type=float, default=7.5)
    ap.add_argument("--f-peak", type=float, default=None)
    ap.add_argument("--n-rs", type=int, default=N_RS_SETTINGS,
                    help="boost settings (default: the committed 3)")
    ap.add_argument("--n-cs", type=int, default=N_CS_SETTINGS,
                    help="frequency settings (default: the committed 5)")
    ap.add_argument("--rs-span", type=float, default=RS_SPAN,
                    help="boost half-span in normalised box units")
    ap.add_argument("--cs-span", type=float, default=CS_SPAN,
                    help="frequency half-span in normalised box units")
    ap.add_argument("--tt-only", action="store_true",
                    help="measure the tuning range and SKIP the 45 corners")
    a = ap.parse_args(argv)
    geom = dict(n_rs=a.n_rs, n_cs=a.n_cs, rs_span=a.rs_span, cs_span=a.cs_span)
    if a.run:
        _report(run(target_f_peak_hz=a.f_peak, target_peaking_db=a.peaking,
                    tt_only=a.tt_only, **geom))
    elif a.analyse:
        p = results_path(**geom)
        if not p.exists():
            raise SystemExit(f"{p.name} missing: run --run first")
        _report(json.loads(p.read_text(encoding="utf-8")))
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":                                  # pragma: no cover
    raise SystemExit(main())
