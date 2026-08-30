"""experiments/score_entry41.py — score entry 41's Q1 and Q2 from the progress log.

**No SPICE.** Q3, Q4 and Q5 test the FINISHED POLICY and need simulation; they
are scored by `exp_sac_propose --ckpt` and by the Q3 rollout loop. This file
does only the two predictions that are read off the training log.

WHY THIS IS NOT A THREE-LINE SCRIPT
------------------------------------
The run was interrupted twice (a stopped process, then a machine restart) and
resumed from checkpoints. That leaves two traps in the log, both of which
produce a confident wrong number rather than an error:

1. **`sac_screen_results.json` holds only the LAST segment.** `run()` rebuilds
   `out["chunks"]` from empty each invocation, so the JSON written at the end
   describes steps 10 000-25 000 and nothing before. **The complete record is
   the JSONL**, which is opened in append mode. This module reads the JSONL.

2. **The env counters RESET at every resume.** `env.report()` is a fresh env,
   so `n_decks`, `n_feasible_steps`, `n_warm_starts` and `n_starts_filtered`
   restart at 0 while `steps` keeps counting. A cumulative diff across the
   whole file therefore hits a NEGATIVE delta at each seam, and a naive total
   reads the last row instead of the sum. Same family as G124.

`segments()` splits on the seam so both are handled explicitly.

A NOTE ON Q2, WRITTEN BEFORE THE NUMBER IS READ
------------------------------------------------
Q2 compares screen-feasible steps in the final five chunks against the first
five. The run **warm-starts on library designs that are already feasible**, so
early chunks are feasible-rich because the policy has not yet learned to move,
not because it is good. As it explores, the count falls. Q2 assumed the count
would RISE with competence; on a seeded start it does the opposite.

That is a defect in the prediction, not a result about the policy, and it is
recorded here rather than discovered afterwards. **Q2 is still scored as
written and still counted as a miss if it misses** -- reinterpreting a
pre-registered metric after seeing it is the thing `PREDICTIONS.md` exists to
prevent.

Reproduce:

    python -m nebula.experiments.score_entry41
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Optional, Sequence

HERE = Path(__file__).resolve().parent
PROGRESS = HERE / "sac_screen_progress.jsonl"
OUT = HERE / "entry41_q1q2_score.json"

#: Entry 41's thresholds, copied from `PREDICTIONS.md` entry 41 and NOT to be
#: edited after the run. Q1: alpha moves >= 2x from init AND log_std >= 0.5.
Q1_ALPHA_FACTOR: float = 2.0
Q1_LOG_STD_MOVE: float = 0.5
Q2_RATIO: float = 2.0
N_CHUNKS_WINDOW: int = 5
TOTAL_STEPS: int = 25_000

#: Counters that restart at zero on every resume.
RESET_KEYS = ("n_decks", "n_feasible_steps", "n_warm_starts",
              "n_starts_filtered", "n_reverted", "n_unscorable")


def load_rows(path: Path = PROGRESS) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def segments(rows: Sequence[dict]) -> list[list[dict]]:
    """Split the log wherever a resume reset the env counters.

    **Two tests, because one is not enough — measured, not assumed.** The first
    version split only on `n_decks` DECREASING, and it silently merged two of
    this run's three segments: both resumes happened to produce a first chunk
    of exactly **2 380 decks**, so the seam between them was `2380 < 2380`,
    which is false. It undercounted the run by 2 380 decks and reported
    "2 segments" with complete confidence.

    So a seam is `n_decks` failing to INCREASE (`<=`, not `<`) **or**
    `elapsed_min` going backwards. Each run restarts its own `t0` and its own
    env, so both reset; requiring only one of them to fire is what makes an
    exact tie visible. Within a segment `n_decks` strictly increases every
    chunk (every step costs decks) and `elapsed_min` strictly increases, so
    neither test can fire spuriously.
    """
    segs: list[list[dict]] = []
    cur: list[dict] = []
    prev_d = prev_e = None
    for r in rows:
        d = int(r["n_decks"])
        e = float(r.get("elapsed_min", 0.0))
        seam = (prev_d is not None
                and (d <= prev_d or e < prev_e))            # type: ignore[operator]
        if seam:
            segs.append(cur)
            cur = []
        cur.append(r)
        prev_d, prev_e = d, e
    if cur:
        segs.append(cur)
    return segs


def per_chunk_feasible(rows: Sequence[dict]) -> list[tuple[int, int]]:
    """[(steps, feasible IN that chunk)], correct across resume seams."""
    out: list[tuple[int, int]] = []
    for seg in segments(rows):
        prev = 0
        for r in seg:
            out.append((int(r["steps"]), int(r["n_feasible_steps"]) - prev))
            prev = int(r["n_feasible_steps"])
    return out


def total_decks(rows: Sequence[dict]) -> int:
    """Sum of each segment's LAST value. Never the final row alone."""
    return sum(int(seg[-1]["n_decks"]) for seg in segments(rows))


def score(path: Path = PROGRESS) -> dict:
    rows = load_rows(path)
    if not rows:
        raise SystemExit(f"{path.name} is empty")
    segs = segments(rows)
    chunks = per_chunk_feasible(rows)

    # ---- Q1 -------------------------------------------------------------
    # Initialisation is the FIRST chunk's `*_first`, which is the value before
    # any update -- not the first `*_last`.
    a0 = float(rows[0]["alpha_first"])
    a1 = float(rows[-1]["alpha_last"])
    l0 = float(rows[0]["log_std_first"])
    l1 = float(rows[-1]["log_std_last"])
    alpha_factor = (a0 / a1) if a1 > 0 else math.inf
    log_std_move = abs(l1 - l0)
    q1_alpha = alpha_factor >= Q1_ALPHA_FACTOR
    q1_log_std = log_std_move >= Q1_LOG_STD_MOVE
    q1 = bool(q1_alpha and q1_log_std)

    # the pre-interruption reading, for the disclosure
    best = min(rows, key=lambda r: float(r["alpha_last"]))

    # ---- Q2 -------------------------------------------------------------
    first_w = chunks[:N_CHUNKS_WINDOW]
    last_w = chunks[-N_CHUNKS_WINDOW:]
    f_first = sum(c for _, c in first_w)
    f_last = sum(c for _, c in last_w)
    ratio = (f_last / f_first) if f_first else None
    q2 = bool(ratio is not None and ratio >= Q2_RATIO)

    return {
        "task": "entry 41 Q1/Q2, scored from the progress log",
        "source": path.name,
        "n_rows": len(rows),
        "n_segments": len(segs),
        "segment_step_ranges": [[s[0]["steps"], s[-1]["steps"]] for s in segs],
        "final_steps": int(rows[-1]["steps"]),
        "complete": int(rows[-1]["steps"]) >= TOTAL_STEPS,
        "total_decks_summed": total_decks(rows),
        "final_row_decks_DO_NOT_USE": int(rows[-1]["n_decks"]),
        "Q1": {
            "alpha_init": a0, "alpha_final": a1, "alpha_factor": alpha_factor,
            "alpha_gate": Q1_ALPHA_FACTOR, "alpha_pass": q1_alpha,
            "log_std_init": l0, "log_std_final": l1,
            "log_std_move": log_std_move, "log_std_gate": Q1_LOG_STD_MOVE,
            "log_std_pass": q1_log_std,
            "pass": q1,
            "best_alpha_seen": float(best["alpha_last"]),
            "best_alpha_at_step": int(best["steps"]),
            "best_alpha_factor": a0 / float(best["alpha_last"]),
        },
        "Q2": {
            "first_window": first_w, "last_window": last_w,
            "feasible_first": f_first, "feasible_last": f_last,
            "ratio": ratio, "gate": Q2_RATIO, "pass": q2,
            "premise_note": "seeded starts make early chunks feasible-rich; "
                            "see module docstring",
        },
    }


def _report(d: dict) -> None:
    print(f"ENTRY 41 -- Q1/Q2 from {d['source']}")
    print(f"  rows {d['n_rows']}  segments {d['n_segments']} "
          f"{d['segment_step_ranges']}")
    print(f"  final step {d['final_steps']}  complete={d['complete']}")
    print(f"  TOTAL DECKS (summed across segments): {d['total_decks_summed']:,}"
          f"   [final row alone reads {d['final_row_decks_DO_NOT_USE']:,}]")
    q1, q2 = d["Q1"], d["Q2"]
    print()
    print(f"  Q1  alpha   {q1['alpha_init']:.4f} -> {q1['alpha_final']:.4f}"
          f"  = {q1['alpha_factor']:.2f}x  (gate {q1['alpha_gate']}x)  "
          f"{'PASS' if q1['alpha_pass'] else 'MISS'}")
    print(f"      log_std {q1['log_std_init']:+.4f} -> {q1['log_std_final']:+.4f}"
          f"  = {q1['log_std_move']:.3f}   (gate {q1['log_std_gate']})   "
          f"{'PASS' if q1['log_std_pass'] else 'MISS'}")
    print(f"      => Q1 {'PASS' if q1['pass'] else 'MISS'}")
    print(f"      disclosure: best alpha {q1['best_alpha_seen']:.4f} "
          f"({q1['best_alpha_factor']:.2f}x) at step "
          f"{q1['best_alpha_at_step']:,}, before the interruptions")
    print()
    print(f"  Q2  feasible first {N_CHUNKS_WINDOW} chunks: {q2['feasible_first']}"
          f"   last {N_CHUNKS_WINDOW}: {q2['feasible_last']}")
    r = q2["ratio"]
    print(f"      ratio {r:.2f}x (gate {q2['gate']}x)   "
          f"{'PASS' if q2['pass'] else 'MISS'}" if r is not None else "      n/a")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--log", type=str, default=str(PROGRESS))
    a = ap.parse_args(argv)
    d = score(Path(a.log))
    _report(d)
    OUT.write_text(json.dumps(d, indent=1), encoding="utf-8")
    print(f"\nwrote {OUT.name}")
    return 0


if __name__ == "__main__":                                  # pragma: no cover
    raise SystemExit(main())
