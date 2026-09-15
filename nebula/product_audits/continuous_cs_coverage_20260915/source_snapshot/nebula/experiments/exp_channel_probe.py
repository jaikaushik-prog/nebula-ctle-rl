"""
experiments/exp_channel_probe.py — **is the channel the hidden variable that
makes adaptation a real problem?**

    python -m nebula.experiments.exp_channel_probe --run

WHY THIS EXISTS
----------------
Entry 71 killed the first framing of D10's adaptation problem. Across PVT, six
of the eight served requests are met at all 45 mandated corners by a **single**
code, so the right code depends on the **request** -- which the policy is handed
-- and not on the hidden corner. A policy there would be learning a 16-row
lookup table.

**PVT may simply be the wrong hidden variable.** A PCIe receiver does not know
its process corner, but it also barely needs to: entry 71 measured that. What it
genuinely does not know, and what actually varies part to part in the field, is
**the channel it is plugged into**. That is what a real RX equalisation loop
adapts to during link training.

TWO FRAMINGS, AND THE DIFFERENCE BETWEEN THEM IS THE WHOLE QUESTION
--------------------------------------------------------------------
**(a) The REQUEST framing** -- `V6_SPECS`, exactly as entry 71 scored it. A
judge names a peaking and a frequency, and `S3_peaking_match` /
`S3_f_peak_match` pin the code to whatever delivers them. The channel can then
only prune that set through S8. **Prediction: the code barely moves**, because
the request already determined it.

**(b) The LINK framing** -- `V6_LINK` below: every row `V6_SPECS` has **except**
the two request-match rows. Nobody names a peaking; the part is asked to make
the link work. This is what a receiver actually faces, and here the amount of
boost needed **is** a function of the channel.

If (b) shows the best code moving with channel loss while (a) does not, then the
adaptation problem is real and it was pointed at the wrong variable. If neither
moves, this circuit does not need a learned adapter and that is the answer.

WHY ONE SPICE RUN COVERS SEVEN CHANNELS
-----------------------------------------
The channel family's insertion loss at DC is **exactly 0 by construction**
(`CHANNEL_MODEL.md`), so `LinkConfig.v_in_diff_pp_v` is identical at 3 dB and
12 dB -- measured in `test_channel_axis.py`. The CTLE therefore sees the same
input amplitude on every channel, the compression rejections are
channel-independent, and **only the eye moves**. So the device is simulated once
per (code, corner) and the link is re-evaluated per channel in Python.

**This is not free, and entry 71's session claimed it was.** The correction:
`bank_sweep_run.jsonl` stored the eye at one channel and not the device result,
so the seven channels need the 2 880 decks re-run. What is free is the *seventh*
channel given the first, not the sweep.

CORRECTED 2026-09-02 BY ENTRY 72'S OWN RESULT
-----------------------------------------------
**The paragraph above is right that one SPICE run yields every channel, and
WRONG that "only the eye moves".** `v_in_diff_pp_v` is the drive at DC; the link
rejection is on the CTLE's **output** swing, and a shorter channel delivers far
more high-frequency content for the stage to amplify. Measured over this probe:

    loss dB   3.0   4.5   6.0   7.5   9.0  10.5  12.0
    scorable    0    18   128   485  1179  1823  2117   (of 2117)

At 3 dB **every** point is rejected on output swing, the lowest-boost code
included, over-driving by 1.43x. **Less channel loss is a HARDER problem for
this stage, not an easier one**, and no bank code fixes it because the binding
quantity is total gain rather than peaking. See `PREDICTIONS.md` entry 72.
"""

from __future__ import annotations

import argparse
import collections
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

import nebula.rl.reward_v1 as R
from nebula.common.types import (SPEC_EYE_H_MIN_V, SPEC_EYE_W_MIN_UI, Corner,
                                 all_corners)
from nebula.experiments.adaptive_screen import CL_MID_F, ScreenPoint, evaluate_at_points
from nebula.experiments.exp_bank_sweep import REQUEST_ROWS, SPECS, _strip_request_rows
from nebula.experiments.exp_coverage import FREQ_REQUESTS, PEAKING_REQUESTS
from nebula.experiments.exp_tuning_bank import bank
from nebula.link.channel import FAMILY_IL_DB
from nebula.rl.contract import design_id, sizing_from_u

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "channel_probe_results.json"
RUN_LOG = HERE / "channel_probe_run.jsonl"

N_RS, N_CS, RS_SPAN, CS_SPAN = 8, 8, 0.38, 0.20

#: **Framing (b).** Every mandated row except the two that encode a human's
#: explicit request. `S3_peaking` and `S3_f_peak_band` STAY -- those are the
#: spec's own 3-12 dB and 1.25-2.5 GHz windows, which hold whether or not
#: anybody named a number. Only `S3_peaking_match` and `S3_f_peak_match` go.
#:
#: **This is a reporting axis, not a new compliance set** (CLAUDEwa.md §8
#: rule 6). No coverage claim is made on it; it exists to answer one question --
#: does the best code move with the channel -- and it is named rather than
#: assembled inline so that what it drops is visible.
V6_LINK: tuple[str, ...] = tuple(s for s in R.V6_SPECS
                                 if s not in ("S3_peaking_match",
                                              "S3_f_peak_match"))


@dataclass
class ChannelRow:
    """One (code, corner) measurement plus its eye on every channel."""

    code: int
    i_rs: int
    i_cs: int
    corner: str
    ok: bool
    reason: Optional[str] = None
    peaking_db: Optional[float] = None
    f_peak_oct: Optional[float] = None
    margins: dict = None
    #: `{loss_db: {"ok", "eye_h_v", "eye_w_ui"}}`
    links: dict = None


def _margins_at(row: ChannelRow, loss_db: float,
                target_f_peak_hz: Optional[float],
                target_peaking_db: Optional[float]) -> Optional[dict]:
    """Margins for this point ON THIS CHANNEL, or None if unscorable there."""
    if not row.ok:
        return None
    link = (row.links or {}).get(str(loss_db)) or (row.links or {}).get(loss_db)
    if not link or not link.get("ok"):
        return None
    m = dict(row.margins or {})
    # The two S8 rows are the ONLY ones the channel moves. Everything else is a
    # property of the device and was measured once.
    m["S8_eye_h"] = float(link["eye_h_v"]) - SPEC_EYE_H_MIN_V
    m["S8_eye_w"] = float(link["eye_w_ui"]) - SPEC_EYE_W_MIN_UI
    if target_f_peak_hz is not None:
        m.update(R.request_rows(float(row.f_peak_oct), float(row.peaking_db),
                                float(target_f_peak_hz),
                                float(target_peaking_db)))
    return m


def compliant_codes(rows: Sequence[ChannelRow], corner: str, loss_db: float,
                    specs: Sequence[str], target_f_peak_hz=None,
                    target_peaking_db=None) -> list:
    out = []
    for r in rows:
        if r.corner != corner:
            continue
        m = _margins_at(r, loss_db, target_f_peak_hz, target_peaking_db)
        if m is None:
            continue
        if any(k not in m for k in specs):
            continue
        if all(v == 0.0 for v in R.shortfalls(m, specs).values()):
            out.append(r.code)
    return sorted(out)


def best_code_link(rows: Sequence[ChannelRow], corner: str,
                   loss_db: float) -> Optional[int]:
    """**Framing (b).** The compliant code with the tallest eye on this channel.

    Tallest eye rather than lowest index, because that is what an adaptation
    loop maximises and what the `hillclimb` control in `exp_adapt_controls`
    ascends. Ties break to the lower code so the answer is deterministic.
    """
    best, best_h = None, -1.0
    for r in rows:
        if r.corner != corner:
            continue
        m = _margins_at(r, loss_db, None, None)
        if m is None or any(k not in m for k in V6_LINK):
            continue
        if not all(v == 0.0 for v in R.shortfalls(m, V6_LINK).values()):
            continue
        link = (r.links or {}).get(str(loss_db)) or (r.links or {}).get(loss_db)
        h = float(link["eye_h_v"])
        if h > best_h + 1e-15:
            best, best_h = r.code, h
    return best


def sweep(base_u: Sequence[float], losses: Sequence[float],
          corners: Optional[Sequence[Corner]] = None) -> list:
    settings = bank(base_u, n_rs=N_RS, n_cs=N_CS, rs_span=RS_SPAN,
                    cs_span=CS_SPAN)
    corners = list(corners if corners is not None else all_corners())
    rows: list[ChannelRow] = []
    n_sims = 0
    with RUN_LOG.open("w", encoding="utf-8") as fh:
        for n, st in enumerate(settings):
            for c in corners:
                pts = [ScreenPoint(c, CL_MID_F, "channel probe")]
                ev = evaluate_at_points(st.u, pts, target_f_peak_hz=1.9e9,
                                        target_peaking_db=7.5, specs=SPECS,
                                        link_losses_db=losses)
                n_sims += ev.n_sims
                p = ev.points[0] if ev.points else None
                row = ChannelRow(
                    code=n, i_rs=st.i_rs, i_cs=st.i_cs,
                    corner=f"{c.process}/{c.vdd_scale:.2f}/{c.temp_c:g}C",
                    ok=bool(p and p.ok),
                    reason=(None if (p and p.ok) else
                            (p.reason if p else "no point")),
                    peaking_db=(p.peaking_db if p and p.ok else None),
                    f_peak_oct=(p.f_peak_oct if p and p.ok else None),
                    margins=(_strip_request_rows(p.margins) if p and p.ok
                             else {}),
                    links=({str(k): v for k, v in (p.links_by_loss or {}).items()}
                           if p and p.ok else {}))
                rows.append(row)
                fh.write(json.dumps(asdict(row)) + "\n")
            print(f"  [{n + 1}/{len(settings)}] code {n} "
                  f"(R{st.i_rs}C{st.i_cs}): {n_sims} decks", flush=True)
    return rows


def analyse(rows: Sequence[ChannelRow], losses: Sequence[float]) -> dict:
    corners = sorted({r.corner for r in rows})
    requests = [(pk, f) for pk in PEAKING_REQUESTS for f in FREQ_REQUESTS]

    # -- framing (a): the request pins the code; does coverage move? ----------
    per_loss = []
    for L in losses:
        served = 0
        code_sets = {}
        for pk, f in requests:
            n = sum(1 for c in corners
                    if compliant_codes(rows, c, L, SPECS, f, pk))
            if n == len(corners):
                served += 1
            # best-single: the code compliant at the most corners
            cnt = collections.Counter()
            for c in corners:
                for k in compliant_codes(rows, c, L, SPECS, f, pk):
                    cnt[k] += 1
            code_sets[f"{pk:.1f}@{f / 1e9:.3f}"] = (
                cnt.most_common(1)[0][0] if cnt else None)
        per_loss.append({"loss_db": float(L), "n_requests_served": served,
                         "best_single_code": code_sets})

    # how many requests change their best-single code across channels
    keys = list(per_loss[0]["best_single_code"])
    moved_a = [k for k in keys
               if len({p["best_single_code"][k] for p in per_loss
                       if p["best_single_code"][k] is not None}) > 1]

    # -- framing (b): nobody names a peaking; the channel decides ------------
    best_b = {c: {float(L): best_code_link(rows, c, L) for L in losses}
              for c in corners}
    moved_b = [c for c, d in best_b.items()
               if len({v for v in d.values() if v is not None}) > 1]
    spans_b = []
    for c, d in best_b.items():
        vals = [v for v in d.values() if v is not None]
        if len(vals) > 1:
            spans_b.append(max(vals) - min(vals))

    return {
        "losses_db": [float(x) for x in losses],
        "n_corners": len(corners), "n_requests": len(requests),
        "framing_a_request": {
            "per_loss": per_loss,
            "requests_whose_best_code_moves": moved_a,
            "n_moved": len(moved_a),
        },
        "framing_b_link": {
            "spec_set": list(V6_LINK),
            "best_code_by_corner_and_loss": {c: {str(k): v for k, v in d.items()}
                                             for c, d in best_b.items()},
            "corners_whose_best_code_moves": moved_b,
            "n_corners_moved": len(moved_b),
            "median_code_span": (float(np.median(spans_b)) if spans_b else 0.0),
            "max_code_span": (int(max(spans_b)) if spans_b else 0),
        },
    }


def run(base_u: Optional[Sequence[float]] = None) -> dict:
    from nebula.experiments.exp_tuning_bank import _base_from_artifacts
    if base_u is None:
        base_u = _base_from_artifacts()
    t0 = time.time()
    losses = list(FAMILY_IL_DB)
    did = design_id(sizing_from_u(np.asarray(base_u)))
    print(f"base {did}: {N_RS * N_CS} codes x 45 corners x {len(losses)} "
          f"channels ({losses} dB)", flush=True)
    rows = sweep(base_u, losses)
    out = {
        "task": "is the CHANNEL the hidden variable that makes adaptation real?",
        "base_design_id": did, "base_u": [float(x) for x in base_u],
        "geometry": {"n_rs": N_RS, "n_cs": N_CS, "rs_span": RS_SPAN,
                     "cs_span": CS_SPAN},
        "n_rows": len(rows), "n_scorable": sum(1 for r in rows if r.ok),
        "analysis": analyse(rows, losses),
        "wall_clock_s": time.time() - t0,
    }
    RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def _report(d: dict) -> None:
    a = d["analysis"]
    print()
    print("=" * 78)
    print(f"CHANNEL PROBE - {d['n_rows']} points, "
          f"{d['n_scorable']} scorable, {d['wall_clock_s'] / 60:.1f} min")
    print("=" * 78)
    print("  (a) REQUEST framing - V6_SPECS, the request pins the code")
    print("      loss dB   requests served at all 45 corners")
    for p in a["framing_a_request"]["per_loss"]:
        print(f"       {p['loss_db']:5.1f}          {p['n_requests_served']:2d} of "
              f"{a['n_requests']}")
    print(f"      requests whose best-single code MOVES with the channel: "
          f"{a['framing_a_request']['n_moved']} of {a['n_requests']}")
    print()
    print("  (b) LINK framing - V6_LINK, nobody names a peaking")
    b = a["framing_b_link"]
    print(f"      corners whose best code MOVES with the channel: "
          f"{b['n_corners_moved']} of {a['n_corners']}")
    print(f"      median code span across channels: {b['median_code_span']:.1f}"
          f"   max: {b['max_code_span']}")
    print()
    print("  THE QUESTION: if (b) moves and (a) does not, the adaptation")
    print("  problem is real and PVT was the wrong hidden variable.")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--analyse", action="store_true")
    a = ap.parse_args(argv)
    if a.run:
        _report(run())
    elif a.analyse:
        if not RESULTS.exists():
            raise SystemExit(f"{RESULTS.name} missing: run --run first")
        _report(json.loads(RESULTS.read_text(encoding="utf-8")))
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":                                  # pragma: no cover
    raise SystemExit(main())
