"""
experiments/exp_gmid_validation.py — does the design-space map actually work?

THE QUESTION
------------
`common/design_space.py` claims that searching in `(gm/I_D, L, I, f_z, k, RL,
VCM)` is better conditioned than searching in `(W, L, I, Rs, Cs, RL, VCM)`.
The map is worthless if it does not predict SPICE, and "better conditioned" is
worthless if it does not change an outcome. So this file measures three things
against the REAL `sky130_runner` with drawn passives, and nothing else:

  **1. Does the map hit what it asked for?** Requested `f_z`, `k` and `A_dc`
     against measured `f_peak`, `peaking_db` and `g_dc`. Distributions, not
     means — a median hides the tail that decides whether a search can use it.

  **2. Does it reduce G44?** `RL_SMOKE.md` §5 measured **159 of 203 invalid
     evaluations — 78.3 % of a 26.54 % invalid rate — as `peak_is_sweep_edge`**,
     a response still rising at 20 GHz that `meas ac MAX` reports as a large
     fictitious peak. That single number is the justification for the whole
     reparameterization.

  **3. Can the sweep-edge region be identified BEFORE simulating?**
     `design_space.predicted_peak` evaluates the exact peak-existence condition
     on the request. If it agrees with SPICE, a search never has to spend a
     simulation discovering that a design has no peak.

THE CONTROL, AND WHY IT IS NOT THE RL SMOKE RUN
------------------------------------------------
The 26.5 % / 78.3 % baseline came from a **policy's proposals** over 500 PPO
steps. Comparing a uniform sample of design space against that would compare
two different samplers as well as two different parameterizations, and the
answer would be uninterpretable — G71's shape, one layer up.

So the control is **arm A: the same sampler, the same evaluator, the same
corner and load, over the approved DEVICE box**. The smoke-run numbers are
quoted as context, and labelled as context.

THE DESIGN BOX IS DERIVED, NOT CHOSEN
--------------------------------------
CLAUDEwa.md §8 rule 6 forbids an agent picking parameter ranges. So the design
box is not picked: it is the **measured image of the approved device box**,
computed from the 1890 already-paid-for TT operating points in
`robust_geometry_data.csv` —

    gm_over_id = gm / (i_bias/2)          both columns measured
    k          = 1 + (gm + gmbs)*rs/2     CLAUDEwa.md §6, measured gm and gmbs
    f_z        = 1 / (2*pi*rs*cs)         exact, from the box coordinates

— so the two arms sample the same physical region by construction, and neither
gets a region the other cannot reach. `--box` prints it.

**One declared asymmetry.** That CSV varies `nf_in` where `rl/contract.py`
fixes it at 4 (G38), so the measured image is slightly WIDER than the
contract's box would produce. Widening the design arm can only make it look
worse, so the comparison is conservative in the direction that matters.

WHAT THIS FILE MAY NOT DO
--------------------------
**Nothing requested may be scored.** Every accuracy number below is
`measured - requested`, and the measured side always comes from
`rl/evaluator.py` — the same validator the RL loop uses, so the verdicts are
comparable by construction (rule 9). A requested `f_z` is a REQUEST: between it
and the measurement sit `to_geometry`'s chaotic quantiser (G67), the `res_po`
bottom plate moving `f_p2` (G66), and the one-zero/two-pole model's own 4.25 %
(session 18c).

**Nothing here changes the RL contract.** `common/params.py`,
`rl/contract.py` and `rl/env.py` are untouched (rules 5 and 6). This is a
measurement brought back for a human decision.

RUN
---
    python -m nebula.experiments.exp_gmid_validation --box
    python -m nebula.experiments.exp_gmid_validation --run --n 400
    python -m nebula.experiments.exp_gmid_validation --analyse <file.jsonl>
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Sequence

import numpy as np

from nebula.common import design_space as dsp
from nebula.common.design_space import predicted_peak, to_device
from nebula.common.types import SPEC_F_PEAK_HZ_RANGE
from nebula.device.gmid_lut import LUT_PATH, GmidLut
from nebula.device.sky130_runner import MAX_SEARCH_TOP_HZ
from nebula.rl.contract import (
    ACTION_SPACE,
    CL_CONTEXT_F,
    NF_IN_FIXED,
    VDD_NOMINAL_V,
    Sizing,
    sizing_from_u,
    u_from_params,
)
from nebula.rl.evaluator import SpiceBudget, Verdict, evaluate

HERE = Path(__file__).resolve().parent

#: The measured population the design box is the image of. Tracked (G49).
CALIBRATION_CSV: Path = HERE / "robust_geometry_data.csv"

RESULTS_JSONL: Path = HERE / "gmid_validation_run.jsonl"

#: Context numbers from `RL_SMOKE.md` §5, quoted so the write-up cannot drift
#: from them. **These are CONTEXT, not the control** — see the module
#: docstring. One definition, here, referenced everywhere below.
SMOKE_INVALID_RATE: float = 203 / 765          # 26.54 %
SMOKE_G44_SHARE: float = 159 / 203             # 78.33 %
SMOKE_N_EVALUATIONS: int = 765


# ─────────────────────────────────────────────────────────────────────────────
# The design box, derived.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DesignDim:
    """One design coordinate and how it is sampled."""

    name: str
    lo: float
    hi: float
    log: bool
    unit: str
    provenance: str

    def to_physical(self, u: float) -> float:
        u = min(max(float(u), 0.0), 1.0)
        if self.log:
            return float(math.exp(math.log(self.lo)
                                  + u * (math.log(self.hi) - math.log(self.lo))))
        return float(self.lo + u * (self.hi - self.lo))


def _measured_image(path: Path = CALIBRATION_CSV) -> dict[str, tuple[float, float]]:
    """`(min, max)` of the three swapped coordinates over the measured set.

    Uses the FULL range rather than a percentile clip. A percentile would be a
    picked number (rule 6); min/max is the image, and the image is what the
    device box actually reaches.
    """
    gmid: list[float] = []
    kk: list[float] = []
    fz: list[float] = []
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if str(row.get("tt_ok", "")).lower() not in ("true", "1"):
                continue
            try:
                gm = float(row["gm"]); gmbs = float(row["gmbs"])
                ib = float(row["i_bias"]); rs = float(row["rs"]); cs = float(row["cs"])
                rl = float(row["rl"]); vcm = float(row["vcm_in"])
                lin = float(row["l_in"])
            except (TypeError, ValueError, KeyError):
                continue
            if not all(map(math.isfinite, (gm, gmbs, ib, rs, cs))):
                continue
            # THE FORWARD MAP, not a second copy of it. A first version of this
            # function wrote out `gm/(i_bias/2)`, `1 + (gm+gmbs)*rs/2` and
            # `1/(2*pi*rs*cs)` inline — which is rule 9's exact failure: the
            # design box would have been derived by one definition and sampled
            # through another, and nothing would have said so.
            d = dsp.to_design(gm, gmbs, {"i_bias": ib, "rs": rs, "cs": cs,
                                         "rl": rl, "vcm_in": vcm, "l_in": lin})
            gmid.append(d["gm_over_id"])
            kk.append(d["k"])
            fz.append(d["f_z"])
    if not gmid:
        raise RuntimeError(f"no usable rows in {path}")
    return {"gm_over_id": (min(gmid), max(gmid)),
            "k": (min(kk), max(kk)),
            "f_z": (min(fz), max(fz)),
            "_n": (float(len(gmid)), float(len(gmid)))}


def design_box(path: Path = CALIBRATION_CSV) -> tuple[DesignDim, ...]:
    """The design box: three coordinates derived, four copied from the device
    box VERBATIM (rule 9 — the edges are not re-typed, they are read off
    `ACTION_SPACE`)."""
    img = _measured_image(path)
    dev = {d.name: d for d in ACTION_SPACE}
    n = int(img["_n"][0])
    src = f"measured image of the device box over {n} TT points in {path.name}"
    return (
        DesignDim("gm_over_id", img["gm_over_id"][0], img["gm_over_id"][1],
                  False, "1/V", src + "; gm/(i_bias/2), both columns measured"),
        DesignDim("l_in", dev["l_in"].lo, dev["l_in"].hi, True, "m",
                  "ACTION_SPACE verbatim"),
        DesignDim("i_bias", dev["i_bias"].lo, dev["i_bias"].hi, True, "A",
                  "ACTION_SPACE verbatim"),
        DesignDim("f_z", img["f_z"][0], img["f_z"][1], True, "Hz",
                  src + "; 1/(2*pi*rs*cs), exact"),
        DesignDim("k", img["k"][0], img["k"][1], True, "-",
                  src + "; 1 + (gm+gmbs)*rs/2, CLAUDEwa section 6"),
        DesignDim("rl", dev["rl"].lo, dev["rl"].hi, True, "ohm",
                  "ACTION_SPACE verbatim"),
        DesignDim("vcm_in", dev["vcm_in"].lo, dev["vcm_in"].hi, False, "V",
                  "ACTION_SPACE verbatim"),
    )


def device_box() -> dict[str, tuple[float, float]]:
    """`{name: (lo, hi)}` off `ACTION_SPACE`. Never redeclared here."""
    return {d.name: (d.lo, d.hi) for d in ACTION_SPACE}


# ─────────────────────────────────────────────────────────────────────────────
# Sampling. One Latin hypercube per arm, same generator, same n.
# ─────────────────────────────────────────────────────────────────────────────


def _lhs(n: int, d: int, rng: np.random.Generator) -> np.ndarray:
    """Latin hypercube on `[0,1]^d`. The sampler both arms share."""
    cut = np.linspace(0.0, 1.0, n + 1)
    u = np.empty((n, d))
    for j in range(d):
        pts = rng.uniform(cut[:n], cut[1:])
        u[:, j] = rng.permutation(pts)
    return u


# ─────────────────────────────────────────────────────────────────────────────
# One evaluation, in either arm.
# ─────────────────────────────────────────────────────────────────────────────


def _sizing_from_params(params: Mapping[str, float]) -> Sizing:
    """Device params -> `Sizing`, going through `u_from_params` so the
    normalised coordinate is the contract's and not a second opinion."""
    full = {
        "w_in": params["w_in"], "l_in": params["l_in"],
        "nf_in": float(NF_IN_FIXED), "i_bias": params["i_bias"],
        "rs": params["rs"], "cs": params["cs"], "rl": params["rl"],
        "cl": float(CL_CONTEXT_F), "vcm_in": params["vcm_in"],
    }
    return Sizing(u=tuple(float(x) for x in u_from_params(full)), params=full)


def _row_from_eval(ev, arm: str, i: int) -> dict:
    """The part of a result both arms record identically.

    `meas` and `raw` are DIFFERENT dicts with different lifetimes, and reading
    the wrong one is silent: `peaking_db` and `g_dc_db` live in `meas`, which
    is populated **only on VALID** (`rl/evaluator.EvalResult`'s docstring says
    so by construction — a HEADROOM_ONLY row has no trustworthy AC spec set).
    `f_pk_hz`, `gm` and the `.op` primitives live in `raw`. A first version of
    this function read them all out of `raw` and silently recorded `None` for
    every peaking number.
    """
    raw = ev.raw or {}
    meas = ev.meas or {}
    return {
        "arm": arm, "i": i,
        "verdict": ev.verdict.value,
        "reason": ev.reason,
        "mechanism": classify_reason(ev.reason or ""),
        "design_id": ev.design_id,
        "n_spice": ev.n_spice,
        "seconds": round(ev.seconds, 4),
        # from `meas` — VALID only, by construction
        "meas_peaking_db": meas.get("peaking_db"),
        "meas_g_dc_db": meas.get("g_dc_db"),
        "meas_nyq_boost_db": meas.get("nyq_boost_db"),
        # from `raw` — present whenever the run was parsed
        "meas_f_pk_hz": raw.get("f_pk_hz"),
        "meas_gm": raw.get("gm"),
        "meas_gmbs": raw.get("gmbs"),
        "meas_id_a": raw.get("id_a"),
        "meas_vds": raw.get("vds"),
        "meas_vdsat": raw.get("vdsat"),
        "meas_v_src_dc": raw.get("v_src_dc"),
        "meas_rs_actual_ohm": raw.get("rs_actual_ohm"),
        "meas_cs_actual_f": raw.get("cs_actual_f"),
        "meas_rl_actual_ohm": raw.get("rl_actual_ohm"),
        "meas_f_zero_error_octaves": raw.get("f_zero_error_octaves"),
    }


def run_arms(n: int, seed: int, lut: GmidLut, out: Path,
             corner: str = "tt", temp_c: float = 27.0,
             k_alpha: float = 1.0,
             mirror_efficiency: float = 1.0,
             design_only: bool = False) -> Path:
    """Run both arms and stream to JSONL. Row 0 is a HEADER row (rule: a log
    cannot be read without its conditions — `rl/runlog.py`'s convention)."""
    dbox = design_box()
    vbox = device_box()
    rng = np.random.default_rng(seed)
    budget = SpiceBudget()

    header = {
        "row": "header",
        "written_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_per_arm": n, "seed": seed, "corner": corner, "temp_c": temp_c,
        "cl_f": float(CL_CONTEXT_F), "vdd_v": float(VDD_NOMINAL_V),
        "nf_in": int(NF_IN_FIXED),
        "k_alpha": k_alpha, "mirror_efficiency": mirror_efficiency,
        "lut": str(LUT_PATH.name),
        "lut_provenance": dict(lut.provenance),
        "device_box": {k: list(v) for k, v in vbox.items()},
        "design_box": [{"name": d.name, "lo": d.lo, "hi": d.hi, "log": d.log,
                        "unit": d.unit, "provenance": d.provenance}
                       for d in dbox],
        "context_not_control": {
            "source": "RL_SMOKE.md section 5, a POLICY's proposals",
            "n_evaluations": SMOKE_N_EVALUATIONS,
            "invalid_rate": SMOKE_INVALID_RATE,
            "g44_share_of_invalid": SMOKE_G44_SHARE,
        },
        "note": ("Requested values are REQUESTS. Only meas_* fields are "
                 "measurements. G66/G67."),
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(header) + "\n")

        # ── ARM A: the control. The approved device box, sampled directly. ──
        ua = _lhs(n, len(ACTION_SPACE), rng)
        t0 = time.perf_counter()
        # `design_only` skips the control. Legitimate ONLY when re-running at a
        # different `k_alpha` or `mirror_efficiency`: neither touches the device
        # arm, which never calls the map. Any other change invalidates the
        # control and it must be re-run.
        for i in range(0 if not design_only else n, n):
            sizing = sizing_from_u(ua[i], cl_f=CL_CONTEXT_F)
            ev = evaluate(sizing, budget, corner=corner, temp_c=temp_c)
            row = _row_from_eval(ev, "device", i)
            row["params"] = {k: sizing.params[k] for k in dsp.DEVICE_NAMES}
            fh.write(json.dumps(row) + "\n")
            if (i + 1) % 50 == 0:
                print(f"  device arm {i + 1}/{n}  "
                      f"{time.perf_counter() - t0:6.1f} s", flush=True)
        fh.flush()

        # ── ARM B: design space. Map first; a rejection costs NO simulation. ─
        ub = _lhs(n, len(dbox), rng)
        t1 = time.perf_counter()
        for i in range(n):
            design = {d.name: d.to_physical(ub[i, j])
                      for j, d in enumerate(dbox)}
            mr = to_device(lut, design, cl_f=float(CL_CONTEXT_F),
                           process=corner, temp_c=temp_c,
                           vdd_v=float(VDD_NOMINAL_V), k_alpha=k_alpha,
                           mirror_efficiency=mirror_efficiency, box=vbox)

            base = {"arm": "design", "i": i, "design": design}
            if mr.f_z_hz is not None and mr.f_p1_hz is not None \
                    and mr.f_p2_hz is not None:
                pk = predicted_peak(mr.f_z_hz, mr.f_p1_hz, mr.f_p2_hz)
                base["req_f_z_hz"] = mr.f_z_hz
                base["req_f_p1_hz"] = mr.f_p1_hz
                base["req_f_p2_hz"] = mr.f_p2_hz
                base["pred_has_peak"] = pk.has_interior_peak
                base["pred_f_peak_hz"] = pk.f_peak_hz
                base["pred_peaking_db"] = pk.peaking_db

            if not mr.ok:
                base.update({"verdict": "map_rejected", "reason": mr.fail_reason,
                             "n_spice": 0, "seconds": 0.0})
                fh.write(json.dumps(base) + "\n")
                continue

            assert mr.params is not None and mr.bias is not None
            sizing = _sizing_from_params(mr.params)
            ev = evaluate(sizing, budget, corner=corner, temp_c=temp_c)
            row = _row_from_eval(ev, "design", i)
            row.update(base)
            row["params"] = dict(mr.params)
            row["req_rs_ohm"] = mr.rs_ohm
            row["req_cs_f"] = mr.cs_f
            row["req_gm_s"] = mr.bias.gm_s
            row["req_gmbs_s"] = mr.bias.gmbs_s
            row["req_w_um"] = mr.bias.w_um
            row["req_vgs_v"] = mr.bias.vgs_v
            row["req_vsb_v"] = mr.bias.vsb_v
            row["req_vds_v"] = mr.bias.vds_v
            row["req_a_dc_linear"] = (mr.bias.gm_s * design["rl"] / design["k"])
            row["req_in_saturation"] = mr.bias.predicted_in_saturation
            fh.write(json.dumps(row) + "\n")
            if (i + 1) % 50 == 0:
                print(f"  design arm {i + 1}/{n}  "
                      f"{time.perf_counter() - t1:6.1f} s", flush=True)

        fh.write(json.dumps({"row": "footer",
                             "spice_invocations": budget.calls,
                             "spice_seconds": round(budget.seconds, 2),
                             "device_arm_s": round(t1 - t0, 2),
                             "design_arm_s": round(time.perf_counter() - t1, 2)})
                 + "\n")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Analysis. Runs from the JSONL with NO simulator.
# ─────────────────────────────────────────────────────────────────────────────


def _pct(x: float) -> str:
    return f"{100.0 * x:6.2f} %"


def _dist(a: Sequence[float], unit: str = "") -> str:
    if not len(a):
        return "n=0"
    v = np.asarray(a, dtype=float)
    v = v[np.isfinite(v)]
    if not v.size:
        return "n=0 finite"
    return (f"n={v.size:4d}  median {np.median(v):8.4f}{unit}  "
            f"p10 {np.percentile(v, 10):8.4f}  p90 {np.percentile(v, 90):8.4f}  "
            f"max|.| {np.max(np.abs(v)):8.4f}")


def analyse(path: Path) -> dict:
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    header = rows[0]
    footer = rows[-1] if rows[-1].get("row") == "footer" else {}
    body = [r for r in rows if "arm" in r]

    out: dict = {"header": header, "footer": footer, "arms": {}}

    for arm in ("device", "design"):
        a = [r for r in body if r["arm"] == arm]
        rejected = [r for r in a if r.get("verdict") == "map_rejected"]
        simmed = [r for r in a if r.get("verdict") != "map_rejected"]
        verdicts: dict[str, int] = {}
        reasons: dict[str, int] = {}
        for r in simmed:
            verdicts[r["verdict"]] = verdicts.get(r["verdict"], 0) + 1
            if r["verdict"] == Verdict.INVALID.value:
                key = r.get("mechanism") or classify_reason(r.get("reason") or "")
                reasons[key] = reasons.get(key, 0) + 1
        n_inv = verdicts.get(Verdict.INVALID.value, 0)
        out["arms"][arm] = {
            "n_proposed": len(a),
            "n_rejected_by_map": len(rejected),
            "n_simulated": len(simmed),
            "verdicts": verdicts,
            "invalid_reasons": reasons,
            "invalid_rate": (n_inv / len(simmed)) if simmed else float("nan"),
            "g44_count": reasons.get("peak_is_sweep_edge", 0),
            "g44_share_of_invalid": (reasons.get("peak_is_sweep_edge", 0) / n_inv)
                                     if n_inv else float("nan"),
            "g44_rate_of_simulated": (reasons.get("peak_is_sweep_edge", 0)
                                      / len(simmed)) if simmed else float("nan"),
            "g44_rate_of_proposed": (reasons.get("peak_is_sweep_edge", 0)
                                     / len(a)) if a else float("nan"),
            # The yield trade, which is the whole question: the map rejects a
            # lot for free, so does what survives pay for it?
            "valid_rate_of_simulated": (verdicts.get(Verdict.VALID.value, 0)
                                        / len(simmed)) if simmed else float("nan"),
            "valid_rate_of_proposed": (verdicts.get(Verdict.VALID.value, 0)
                                       / len(a)) if a else float("nan"),
            "free_rejection_rate": (len(rejected) / len(a)) if a else 0.0,
            # THE METRIC A SEARCH ACTUALLY CARES ABOUT. The two arms waste
            # differently — the device arm simulates everything and a third of
            # it comes back untrustworthy; the design arm rejects a lot for
            # free and simulates a cleaner remainder — and "simulations spent
            # per usable design" is the only number that prices both.
            "sims_per_valid": (len(simmed) / verdicts.get(Verdict.VALID.value, 0)
                               if verdicts.get(Verdict.VALID.value, 0)
                               else float("inf")),
            "map_reject_reasons": _tally(_map_reason_key(r.get("reason") or "")
                                         for r in rejected),
        }

    out["accuracy"] = _accuracy(body)
    # The same accuracy, restricted to designs whose MEASURED peak lands in
    # S3's window. The box-wide number answers "does the map work?"; this one
    # answers "does it work where the spec lives?", and they are different
    # questions — the design box is the image of the whole device box, so most
    # of it is nowhere near 1.25-2.5 GHz.
    out["accuracy_in_s3_window"] = _accuracy(body, s3_window_only=True)
    out["peak_predictor"] = _peak_predictor(body)
    out["peak_predictor_with_ceiling"] = _peak_predictor(
        body, search_top_hz=MAX_SEARCH_TOP_HZ)
    return out


def classify_reason(reason: str) -> str:
    """Bucket an invalidity by MECHANISM, using the RL env's own table.

    **Rule 9: one definition.** `CtleSizingEnv._classify` already owns the
    reason-string-to-mechanism mapping, and `RL_SMOKE.md`'s 159/28/16
    histogram — the number this whole experiment is compared against — was
    produced by it. A second copy here would be exactly the "two definitions
    of one thing" failure (G32), and it would be invisible: the analysis would
    simply bucket differently and the comparison would be wrong by an amount
    nobody could see.

    It takes `self` but does not use it, so it is called through the class.
    `tests/test_exp_gmid_validation.py::test_mechanism_names_match_the_env`
    pins the two together, and goes red if the env's table moves.
    """
    from nebula.rl.env import CtleSizingEnv
    return CtleSizingEnv._classify(None, reason or "")   # type: ignore[arg-type]


def _map_reason_key(reason: str) -> str:
    """Bucket a `design_space` rejection. DIFFERENT namespace from the env's.

    Map rejections are `design_space`'s own named failures
    (`current_unreachable`, `rs_outside_box`, ...) and the env's mechanism
    table knows nothing about them — feeding them to `classify_reason` would
    bucket every one as "other" and silently erase the most interesting column
    in the experiment.
    """
    return (reason or "unnamed").split(":")[0].strip()[:48] or "unnamed"


def _tally(it) -> dict[str, int]:
    d: dict[str, int] = {}
    for x in it:
        d[x] = d.get(x, 0) + 1
    return dict(sorted(d.items(), key=lambda kv: -kv[1]))


def _accuracy(body: Sequence[dict], s3_window_only: bool = False) -> dict:
    """Requested vs measured, on the design arm's VALID rows only.

    Only VALID: a HEADROOM_ONLY row has no trustworthy AC spec set by
    construction (`rl/evaluator.py`), so comparing a requested `f_z` against
    its `f_peak` would be comparing against a number the evaluator has already
    said not to believe.

    `s3_window_only` restricts to rows whose MEASURED `f_peak` is inside S3's
    1.25-2.5 GHz window — measured, never requested, so the filter cannot
    select on the quantity being scored.
    """
    rows = [r for r in body
            if r["arm"] == "design" and r.get("verdict") == Verdict.VALID.value]
    if s3_window_only:
        lo, hi = SPEC_F_PEAK_HZ_RANGE
        rows = [r for r in rows
                if r.get("meas_f_pk_hz") and lo <= r["meas_f_pk_hz"] <= hi]
    f_oct, f_rel, pk_db, gdc_db = [], [], [], []
    pred_f_oct, pred_pk_db = [], []
    for r in rows:
        m_f, m_pk = r.get("meas_f_pk_hz"), r.get("meas_peaking_db")
        m_g = r.get("meas_g_dc_db")
        p_f, p_pk = r.get("pred_f_peak_hz"), r.get("pred_peaking_db")
        a_dc = r.get("req_a_dc_linear")
        if m_f and p_f and m_f > 0 and p_f > 0:
            pred_f_oct.append(math.log2(m_f / p_f))
            f_rel.append((m_f - p_f) / p_f)
        if m_pk is not None and p_pk is not None:
            pred_pk_db.append(m_pk - p_pk)
        if m_g is not None and a_dc and a_dc > 0:
            gdc_db.append(m_g - 20.0 * math.log10(a_dc))
        # `f_z` is not directly measurable; the closed-form peak IS the
        # comparable prediction, which is why it carries the f_z/k request.
        rq = r.get("req_f_z_hz")
        if m_f and rq:
            f_oct.append(math.log2(m_f / rq))
    return {
        "n_valid_design_rows": len(rows),
        "f_peak_error_octaves": pred_f_oct,
        "f_peak_error_relative": f_rel,
        "peaking_error_db": pred_pk_db,
        "g_dc_error_db": gdc_db,
        "f_peak_over_f_z_octaves": f_oct,
    }


def _peak_predictor(body: Sequence[dict], search_top_hz: Optional[float] = None
                    ) -> dict:
    """Confusion matrix: the analytic peak condition against SPICE.

    Positive = "has an interior peak". A design-arm row that reached the
    simulator and came back `peak_is_sweep_edge` is a measured NEGATIVE.

    `search_top_hz` applies the guard's own ceiling to the prediction. Computed
    from the LOGGED `pred_f_peak_hz`, so both variants come out of one run and
    the difference between them is attributable rather than inferred.
    """
    tp = fp = tn = fn = 0
    for r in body:
        if r["arm"] != "design" or "pred_has_peak" not in r:
            continue
        if r.get("verdict") in (None, "map_rejected"):
            continue
        mech = r.get("mechanism") or classify_reason(r.get("reason") or "")
        measured_peak = not (r.get("verdict") == Verdict.INVALID.value
                             and mech == "peak_is_sweep_edge")
        pred = bool(r["pred_has_peak"])
        if pred and search_top_hz is not None:
            fpk = r.get("pred_f_peak_hz")
            pred = fpk is not None and fpk < search_top_hz
        if pred and measured_peak:
            tp += 1
        elif pred and not measured_peak:
            fp += 1
        elif not pred and not measured_peak:
            tn += 1
        else:
            fn += 1
    n = tp + fp + tn + fn
    return {
        "n": n, "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "search_top_hz": search_top_hz,
        "accuracy": (tp + tn) / n if n else float("nan"),
        "precision": tp / (tp + fp) if (tp + fp) else float("nan"),
        "recall": tp / (tp + fn) if (tp + fn) else float("nan"),
    }


def print_analysis(res: dict) -> None:
    h = res["header"]
    print("=" * 78)
    print("gm/I_D design-space map -- validation against real SKY130")
    print("=" * 78)
    print(f"  {h['n_per_arm']} samples per arm, seed {h['seed']}, "
          f"corner {h['corner']}@{h['temp_c']}, cl = {h['cl_f'] * 1e15:.2f} fF")
    print(f"  k_alpha {h['k_alpha']} (1.0 = CLAUDEwa section 6 verbatim, "
          f"unfitted), mirror_efficiency {h['mirror_efficiency']}")
    print(f"  SPICE invocations: {res['footer'].get('spice_invocations')}")
    print()

    print("-" * 78)
    print("1. VALIDITY -- the control is the device arm, same sampler")
    print("-" * 78)
    print(f"  {'':22s} {'device':>14s} {'design':>14s}")
    d, g = res["arms"]["device"], res["arms"]["design"]
    print(f"  {'proposed':22s} {d['n_proposed']:14d} {g['n_proposed']:14d}")
    print(f"  {'rejected by map':22s} {d['n_rejected_by_map']:14d} "
          f"{g['n_rejected_by_map']:14d}   <- costs NO simulation")
    print(f"  {'simulated':22s} {d['n_simulated']:14d} {g['n_simulated']:14d}")
    for key in ("valid", "headroom_only", "invalid"):
        print(f"  {key:22s} {d['verdicts'].get(key, 0):14d} "
              f"{g['verdicts'].get(key, 0):14d}")
    print(f"  {'invalid rate':22s} {_pct(d['invalid_rate']):>14s} "
          f"{_pct(g['invalid_rate']):>14s}")
    print()
    print(f"  {'free rejection':22s} {_pct(d['free_rejection_rate']):>14s} "
          f"{_pct(g['free_rejection_rate']):>14s}")
    print(f"  {'VALID % of simulated':22s} "
          f"{_pct(d['valid_rate_of_simulated']):>14s} "
          f"{_pct(g['valid_rate_of_simulated']):>14s}   <- was a simulation worth it")
    print(f"  {'VALID % of proposed':22s} "
          f"{_pct(d['valid_rate_of_proposed']):>14s} "
          f"{_pct(g['valid_rate_of_proposed']):>14s}   <- end-to-end yield")
    if g["n_simulated"]:
        lift = (g["valid_rate_of_simulated"] / d["valid_rate_of_simulated"]
                if d["valid_rate_of_simulated"] else float("nan"))
        print(f"  {'yield lift per sim':22s} {'':>14s} {lift:13.2f}x")
    print(f"  {'SIMULATIONS per VALID':22s} {d['sims_per_valid']:14.2f} "
          f"{g['sims_per_valid']:14.2f}   <- what a search pays")
    print()
    print(f"  {'G44 count':22s} {d['g44_count']:14d} {g['g44_count']:14d}")
    print(f"  {'G44 % of invalid':22s} {_pct(d['g44_share_of_invalid']):>14s} "
          f"{_pct(g['g44_share_of_invalid']):>14s}")
    print(f"  {'G44 % of simulated':22s} {_pct(d['g44_rate_of_simulated']):>14s} "
          f"{_pct(g['g44_rate_of_simulated']):>14s}")
    print(f"  {'G44 % of PROPOSED':22s} {_pct(d['g44_rate_of_proposed']):>14s} "
          f"{_pct(g['g44_rate_of_proposed']):>14s}   <- the honest comparison")
    print()
    ctx = h["context_not_control"]
    print(f"  CONTEXT (not the control): the RL smoke run's policy proposals "
          f"scored")
    print(f"    invalid {_pct(ctx['invalid_rate'])} over "
          f"{ctx['n_evaluations']} evaluations, "
          f"G44 {_pct(ctx['g44_share_of_invalid'])} of invalid.")
    print(f"    Different SAMPLER, so not comparable as a control. "
          f"{ctx['source']}.")
    print()

    print("-" * 78)
    print("2. WHAT THE MAP REJECTED BEFORE SIMULATING (design arm)")
    print("-" * 78)
    if not g["map_reject_reasons"]:
        print("  nothing rejected")
    for reason, count in g["map_reject_reasons"].items():
        print(f"  {count:5d}  {reason}")
    print()
    print("-" * 78)
    print("3. INVALID MECHANISMS, per arm")
    print("-" * 78)
    for arm in ("device", "design"):
        print(f"  {arm}:")
        rs = res["arms"][arm]["invalid_reasons"]
        if not rs:
            print("     none")
        for reason, count in rs.items():
            print(f"     {count:5d}  {reason}")
    print()

    print("-" * 78)
    print("4. ACCURACY -- requested vs MEASURED, design arm, VALID rows only")
    print("-" * 78)
    a = res["accuracy"]
    print(f"  valid design rows: {a['n_valid_design_rows']}")
    print(f"  f_peak error  [oct] {_dist(a['f_peak_error_octaves'])}")
    print(f"  f_peak error  [rel] {_dist(a['f_peak_error_relative'])}")
    print(f"  peaking error [dB]  {_dist(a['peaking_error_db'])}")
    print(f"  g_dc error    [dB]  {_dist(a['g_dc_error_db'])}")
    print()
    print("  Read these as measured MINUS requested. A requested value is a")
    print("  REQUEST: to_geometry quantises (G67), the res_po bottom plate")
    print("  moves f_p2 (G66), and the 1z/2p model itself is 4.25 % (18c).")
    print()
    s3 = res.get("accuracy_in_s3_window", {})
    lo, hi = SPEC_F_PEAK_HZ_RANGE
    print(f"  ... and restricted to rows whose MEASURED f_peak is inside S3's")
    print(f"  {lo / 1e9:.2f}-{hi / 1e9:.2f} GHz window "
          f"({s3.get('n_valid_design_rows', 0)} rows):")
    print(f"  f_peak error  [oct] {_dist(s3.get('f_peak_error_octaves', []))}")
    print(f"  peaking error [dB]  {_dist(s3.get('peaking_error_db', []))}")
    print(f"  g_dc error    [dB]  {_dist(s3.get('g_dc_error_db', []))}")
    print()

    print("-" * 78)
    print("5. CAN G44 BE SEEN BEFORE SIMULATING? (analytic peak condition)")
    print("-" * 78)
    for label, key in (("bare condition (peak ANYWHERE)", "peak_predictor"),
                       (f"+ the guard's own {MAX_SEARCH_TOP_HZ / 1e9:g} GHz "
                        f"search ceiling", "peak_predictor_with_ceiling")):
        p = res.get(key, {})
        if not p:
            continue
        print(f"  {label}")
        print(f"    n = {p['n']}   TP {p['tp']}  FP {p['fp']}  "
              f"TN {p['tn']}  FN {p['fn']}")
        print(f"    accuracy {_pct(p['accuracy'])}   precision "
              f"{_pct(p['precision'])}   recall {_pct(p['recall'])}")
    print()
    print("  TN is the number that matters: it counts the designs the")
    print("  predictor correctly kept OUT of the simulator. A predictor with")
    print("  TN = 0 has not saved a single simulation, whatever its accuracy.")
    print("=" * 78)


# ─────────────────────────────────────────────────────────────────────────────
# CLI.
# ─────────────────────────────────────────────────────────────────────────────


def print_box() -> None:
    print("=" * 78)
    print("THE DESIGN BOX -- derived, not chosen (CLAUDEwa.md rule 6)")
    print("=" * 78)
    for d in design_box():
        lo = f"{d.lo:.4g}"; hi = f"{d.hi:.4g}"
        print(f"  {d.name:12s} {lo:>10s} .. {hi:>10s}  {d.unit:5s} "
              f"{'log' if d.log else 'lin'}")
        print(f"               {d.provenance}")
    print()
    print("THE DEVICE BOX -- rl/contract.ACTION_SPACE, unchanged")
    for name, (lo, hi) in device_box().items():
        print(f"  {name:12s} {lo:>10.4g} .. {hi:>10.4g}")
    print("=" * 78)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--box", action="store_true", help="print the derived boxes")
    ap.add_argument("--run", action="store_true", help="run both arms")
    ap.add_argument("--analyse", type=Path, help="analyse an existing JSONL")
    ap.add_argument("--n", type=int, default=400, help="samples per arm")
    ap.add_argument("--seed", type=int, default=20260817)
    ap.add_argument("--k-alpha", type=float, default=1.0)
    ap.add_argument("--mirror-efficiency", type=float, default=1.0)
    ap.add_argument("--design-only", action="store_true",
                    help="skip the control arm; valid ONLY when re-running at a "
                         "different --k-alpha or --mirror-efficiency, neither "
                         "of which touches the device arm")
    ap.add_argument("--out", type=Path, default=RESULTS_JSONL)
    a = ap.parse_args(argv)

    if a.box:
        print_box()
        return 0
    if a.analyse:
        print_analysis(analyse(a.analyse))
        return 0
    if a.run:
        lut = GmidLut.load()
        print(f"running {a.n} samples per arm ...", flush=True)
        out = run_arms(a.n, a.seed, lut, a.out, k_alpha=a.k_alpha,
                       mirror_efficiency=a.mirror_efficiency,
                       design_only=a.design_only)
        print(f"wrote {out}")
        print_analysis(analyse(out))
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
