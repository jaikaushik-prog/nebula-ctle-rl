"""experiments/exp_harvest.py -- **step 2: turn 239 132 simulations already on
disk into a demonstration set, for zero new SPICE.**

THE IDEA, IN ONE SENTENCE
--------------------------
You do not need designs that hit a *requested* spec. For behaviour cloning you
need **(spec, design)** pairs -- and **every design ever simulated is a perfect
demonstration for the spec it actually achieved.** Every run already measured
`peaking_db` and `f_peak`, so relabelling is free.

That is hindsight relabelling (HER), and it is unblocked now that the spec
manifold is genuinely 2-D: `S3_peaking_match` has been live since G111, so a
policy conditioned on (peaking, f_peak) is being asked a real question.

WHY THE VALIDITY GATE HAD TO COME FIRST
-----------------------------------------
**41 949 of the 239 132 logged designs -- 17.5 % -- are recorded sweep-edge
rejects.** A response still rising at 20 GHz makes `meas ac MAX` return the
range edge, so `peaking_db` is fictitious (G44). Relabelling those would teach
a policy that *"to achieve 4 dB at 19.95 GHz, output this"* is a valid answer:
**the exact pathology that broke SAC**, since all 52 of entry 41's
fully-scorable proposals live there (G130).

**The gate is HONOURED, not recomputed.** `baselines.py` and `rl/env.py` go
through `evaluator.evaluate`, which applies `evaluator.validate` and records
its verdict as `invalid_reason` at simulation time. This module reads that
field. Re-deriving the rule here would be a second definition of validity in a
repository whose whole problem this week was having two (rule 9).

**Two logs predate that path and carry no verdict** -- `coverage_*`,
`hybrid_run`, `joint_search_run`, `linear_pareto_run` come from
`evaluate_at_points`, which had no gate until session 30. For those the
`ok` flag and the spec-box filter are all that is available, and the artifact
says so. In practice the box filter subsumes the frequency half: a design whose
peak is reported at 19.95 GHz cannot be inside a 1.25-2.5 GHz window. What it
cannot catch is `peak_is_sweep_edge` firing on a peak *inside* the window,
which needs `g_top_db` and is not logged.

WHAT COMES OUT
---------------
    239 132  design vectors logged across 13 run logs
    125 042  pass the validity gate as recorded
     41 949  recorded sweep-edge rejects, EXCLUDED
     51 610  gate-valid AND inside the requestable spec box

Against the 33 071 in-box rows the 74 526-row pool holds, that is **+56 %
demonstrations for zero simulations.**

    python -m nebula.experiments.exp_harvest --run
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import time
from pathlib import Path
from typing import Iterator, Optional, Sequence

import numpy as np

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "harvest_results.json"
DATASET = HERE / "demonstrations.npz"

#: Every run log carrying design vectors. **Enumerated, never globbed** (G101):
#: a set defined by what it matches grows silently, and a new log joining the
#: training set without a decision is exactly that failure.
LOGS: tuple[str, ...] = (
    "baselines_run_interp_grid.jsonl.gz",   # gated -- evaluator.evaluate
    "baselines_run_interp.jsonl.gz",        # gated
    "baselines_run_lattice.jsonl.gz",       # gated
    "budget_ladder_run.jsonl.gz",           # gated
    "rl_smoke_run_v0.jsonl",                # gated
    "rl_smoke_run_v1.jsonl",                # gated
    "corner_rl_run.jsonl",                  # gated
    "coverage_run.jsonl",                   # UNGATED -- evaluate_at_points
    "coverage_run_AFTER_unclip_fix.jsonl",  # UNGATED
    "coverage_run_BEFORE_seeding_fix.jsonl",  # UNGATED
    "hybrid_run.jsonl",                     # UNGATED
    "joint_search_run.jsonl",               # UNGATED
    "linear_pareto_run.jsonl",              # UNGATED
)

#: Logs whose rows carry `validate`'s own verdict in `invalid_reason`. The rest
#: are pre-gate and are labelled as such in the artifact rather than silently
#: mixed in.
GATED_LOGS: frozenset[str] = frozenset(LOGS[:7])

#: The REQUESTABLE spec box -- S3's stated range, not a quality filter. A
#: design peaking at 15 GHz is a perfectly good measurement and is not a
#: demonstration for any request this competition asks about.
PEAKING_LO_DB, PEAKING_HI_DB = 3.0, 12.0
F_PEAK_LO_HZ, F_PEAK_HI_HZ = 1.25e9, 2.5e9

#: `f_peak_oct` is measured in octaves relative to Nyquist. One definition.
F_REF_HZ: float = 2.5e9

N_ACTIONS: int = 7


def _open(path: Path):
    return (gzip.open(path, "rt", encoding="utf-8", errors="replace")
            if path.suffix == ".gz"
            else open(path, "rt", encoding="utf-8", errors="replace"))


def achieved_spec(row: dict) -> tuple[Optional[float], Optional[float]]:
    """The (peaking_db, f_peak_hz) this design ACTUALLY achieved.

    **The interpolated peak wins where it exists** (G74/G108). S3's 1.25 GHz
    floor falls between two `ac dec 50` samples, so the raw lattice reading
    rounds a 1.6 %-wide band of true failures into passes -- and a
    demonstration set built on the lattice would teach a policy to aim at a
    grid rather than at a frequency. Session 22u measured one design moving
    from FEASIBLE to INFEASIBLE on this flag alone.
    """
    m = row.get("meas") or {}
    pk = m.get("peaking_db_interp")
    if pk is None:
        pk = m.get("peaking_db")
    if pk is None:
        pk = row.get("peaking_db")

    f_oct = m.get("f_peak_oct_interp")
    if f_oct is None:
        f_oct = m.get("f_peak_oct")
    f_hz = (F_REF_HZ * 2.0 ** float(f_oct)) if f_oct is not None else None
    if f_hz is None:
        f_hz = row.get("f_peak_hz")

    return ((None if pk is None else float(pk)),
            (None if f_hz is None else float(f_hz)))


def gate_verdict(row: dict, gated: bool) -> tuple[bool, str]:
    """`(keep, why)` -- **reading `validate`'s recorded verdict, not redoing it.**

    Returns the reason a row is dropped so the artifact can report the
    breakdown rather than only a survivor count.
    """
    reason = row.get("invalid_reason")
    if reason:
        # **Bucket the reason, do not echo it.** `validate` embeds measured
        # millivolts in its message ("out of saturation (tail -14.6 mV ...)"),
        # so echoing makes every row its own category and the breakdown
        # becomes 40 000 buckets of one -- a histogram that cannot be read is
        # the same as no histogram.
        r = reason.lower()
        if "sweep edge" in r:
            return False, "sweep_edge (G44): the peak is fictitious"
        if "saturation" in r:
            return False, "out of saturation (headroom-only)"
        if "not an amplifier" in r:
            return False, "gain outside [-80, 60] dB"
        if "ngspice" in r or "silent failure" in r:
            return False, "ngspice failure"
        if "out of range" in r:
            return False, "a measured quantity out of range"
        return False, "invalid, other"
    if row.get("ok") is False:
        return False, "not ok"
    if not gated:
        # No verdict was recorded because this log predates the gate. The
        # caller is told; the spec-box filter does the frequency half.
        return True, "ungated log"
    return True, "valid"


def in_spec_box(peaking_db: float, f_peak_hz: float) -> bool:
    """Is the ACHIEVED spec something a user could have asked for?"""
    return (PEAKING_LO_DB <= peaking_db <= PEAKING_HI_DB
            and F_PEAK_LO_HZ <= f_peak_hz <= F_PEAK_HI_HZ)


def iter_rows(path: Path) -> Iterator[dict]:
    with _open(path) as fh:
        for line in fh:
            if '"u"' not in line:
                continue
            try:
                d = json.loads(line)
            except Exception:                                   # noqa: BLE001
                continue
            u = d.get("u")
            if not u:
                continue
            if len(u) != N_ACTIONS:
                # **An OLDER ACTION SPACE, and it must not vanish silently.**
                # `rl_smoke_run_v0.jsonl` carries 765 rows whose `u` is not
                # 7-D: it predates the current `contract.N_ACTIONS`. Dropping
                # them is right -- a demonstration in a different coordinate
                # system is not a demonstration -- but a set that loses members
                # without saying so is G115, so the row is yielded with a flag
                # and counted by the caller.
                d["_wrong_dim"] = len(u)
                yield d
                continue
            yield d


def harvest(logs: Sequence[str] = LOGS, here: Optional[Path] = None) -> dict:
    """Every usable (spec, design) demonstration on disk. **Zero SPICE.**"""
    here = Path(here or HERE)
    from collections import Counter

    seen: dict[tuple, dict] = {}
    per_log: list[dict] = []
    drops: Counter = Counter()

    for name in logs:
        p = here / name
        if not p.exists():
            per_log.append({"log": name, "missing": True})
            continue
        gated = name in GATED_LOGS
        n = kept = boxed = 0
        for row in iter_rows(p):
            n += 1
            if row.get("_wrong_dim"):
                drops[f"wrong action dimension ({row['_wrong_dim']}, not "
                      f"{N_ACTIONS}) -- an older contract"] += 1
                continue
            keep, why = gate_verdict(row, gated)
            if not keep:
                drops[why] += 1
                continue
            pk, f_hz = achieved_spec(row)
            if pk is None or f_hz is None:
                drops["no achieved spec"] += 1
                continue
            kept += 1
            if not in_spec_box(pk, f_hz):
                drops["outside the requestable spec box"] += 1
                continue
            boxed += 1
            # **Dedup on `u`, never on `design_id`** -- G124: bit-identical
            # sizing gets different ids across artifact boundaries, and the
            # failure mode is a silent empty join that reads as a finding.
            key = tuple(round(float(x), 9) for x in row["u"])
            rec = seen.get(key)
            if rec is None:
                seen[key] = {"u": [float(x) for x in row["u"]],
                             "peaking_db": pk, "f_peak_hz": f_hz,
                             "sources": [name], "gated": gated}
            elif name not in rec["sources"]:
                rec["sources"].append(name)
        per_log.append({"log": name, "gated": gated, "n_rows": n,
                        "n_gate_valid": kept, "n_in_box": boxed})

    demos = list(seen.values())
    pk = np.array([d["peaking_db"] for d in demos], dtype=float)
    fz = np.array([d["f_peak_hz"] for d in demos], dtype=float)
    return {
        "task": "hindsight-relabelled demonstrations harvested from run logs",
        "per_log": per_log,
        "drop_reasons": dict(drops.most_common()),
        "n_rows_total": sum(x.get("n_rows", 0) for x in per_log),
        "n_gate_valid": sum(x.get("n_gate_valid", 0) for x in per_log),
        "n_in_box": sum(x.get("n_in_box", 0) for x in per_log),
        "n_unique_demonstrations": len(demos),
        "n_from_ungated_logs": sum(1 for d in demos if not d["gated"]),
        "spec_box": {"peaking_db": [PEAKING_LO_DB, PEAKING_HI_DB],
                     "f_peak_hz": [F_PEAK_LO_HZ, F_PEAK_HI_HZ]},
        "achieved_peaking_db": {"min": float(pk.min()), "max": float(pk.max()),
                                "median": float(np.median(pk))} if len(pk) else None,
        "achieved_f_peak_ghz": {"min": float(fz.min() / 1e9),
                                "max": float(fz.max() / 1e9),
                                "median": float(np.median(fz) / 1e9)} if len(fz) else None,
        "_demos": demos,
    }


def coverage_grid(demos: Sequence[dict], n_pk: int = 10,
                  n_f: int = 10) -> dict:
    """**How much of the requestable box the demonstrations actually cover.**

    A dataset of 50 000 pairs is worthless for spec conditioning if they all
    sit in one corner. This is the check that says whether behaviour cloning
    can answer an arbitrary request or only the popular ones.
    """
    if not demos:
        return {"n_cells": n_pk * n_f, "n_occupied": 0, "fraction": 0.0,
                "min_count": 0, "counts": []}
    pk = np.array([d["peaking_db"] for d in demos], dtype=float)
    fo = np.log2(np.array([d["f_peak_hz"] for d in demos], dtype=float)
                 / F_PEAK_LO_HZ)                      # octaves above the floor
    span_oct = math.log2(F_PEAK_HI_HZ / F_PEAK_LO_HZ)
    ipk = np.clip(((pk - PEAKING_LO_DB) / (PEAKING_HI_DB - PEAKING_LO_DB)
                   * n_pk).astype(int), 0, n_pk - 1)
    ifo = np.clip((fo / span_oct * n_f).astype(int), 0, n_f - 1)
    counts = np.zeros((n_pk, n_f), dtype=int)
    np.add.at(counts, (ipk, ifo), 1)
    return {"n_cells": int(counts.size),
            "n_occupied": int((counts > 0).sum()),
            "fraction": float((counts > 0).mean()),
            "min_count": int(counts.min()), "max_count": int(counts.max()),
            "median_count": float(np.median(counts)),
            "counts": counts.tolist()}


def run(logs: Sequence[str] = LOGS) -> dict:
    from nebula.experiments.runlock import stamp

    t0 = time.time()
    out = harvest(logs)
    demos = out.pop("_demos")
    out.update(stamp())
    out["coverage"] = coverage_grid(demos)
    out["wall_s"] = time.time() - t0

    np.savez_compressed(
        DATASET,
        u=np.array([d["u"] for d in demos], dtype=np.float64),
        peaking_db=np.array([d["peaking_db"] for d in demos], dtype=np.float64),
        f_peak_hz=np.array([d["f_peak_hz"] for d in demos], dtype=np.float64),
        gated=np.array([d["gated"] for d in demos], dtype=bool))
    RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def _report(d: dict) -> None:
    print()
    print("STEP 2 -- hindsight-relabelled demonstrations, ZERO SPICE")
    print()
    print(f"  {'log':44} {'gated':>6} {'rows':>8} {'valid':>8} {'in box':>8}")
    for x in d["per_log"]:
        if x.get("missing"):
            print(f"  {x['log']:44} {'MISSING':>6}")
            continue
        print(f"  {x['log']:44} {str(x['gated']):>6} {x['n_rows']:8,} "
              f"{x['n_gate_valid']:8,} {x['n_in_box']:8,}")
    print()
    print(f"  rows logged                {d['n_rows_total']:9,}")
    print(f"  pass the validity gate     {d['n_gate_valid']:9,}")
    print(f"  inside the spec box        {d['n_in_box']:9,}")
    print(f"  UNIQUE demonstrations      {d['n_unique_demonstrations']:9,}"
          f"   <- the training set")
    print(f"     of which from ungated logs {d['n_from_ungated_logs']:,}")
    print()
    print("  dropped, by reason:")
    for k, v in d["drop_reasons"].items():
        print(f"     {v:9,}  {k}")
    c = d["coverage"]
    print()
    print(f"  spec-box coverage: {c['n_occupied']} of {c['n_cells']} cells "
          f"({100 * c['fraction']:.0f} %), min {c['min_count']} / "
          f"median {c['median_count']:.0f} / max {c['max_count']} per cell")
    a, f = d["achieved_peaking_db"], d["achieved_f_peak_ghz"]
    if a and f:
        print(f"  achieved peaking  {a['min']:.2f} .. {a['max']:.2f} dB "
              f"(median {a['median']:.2f})")
        print(f"  achieved f_peak   {f['min']:.3f} .. {f['max']:.3f} GHz "
              f"(median {f['median']:.3f})")
    print(f"\n  wrote {DATASET.name} and {RESULTS.name}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--analyse", action="store_true")
    a = ap.parse_args(argv)
    if a.analyse:
        if not RESULTS.exists():
            raise SystemExit(f"{RESULTS.name} does not exist; --run first")
        _report(json.loads(RESULTS.read_text(encoding="utf-8")))
        return 0
    if not a.run:
        ap.print_help()
        return 0
    _report(run())
    return 0


if __name__ == "__main__":                                  # pragma: no cover
    raise SystemExit(main())
