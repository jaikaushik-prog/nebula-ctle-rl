"""
experiments/rl_smoke.py — task 6. Run the loop end to end, badly, on purpose.

    "The goal is not a good policy. The goal is to surface every integration
     bug between three layers that have never been run together."

THE ORDER IS NOT NEGOTIABLE, and each stage gates the next:

    --regression-4d   real passives vs ideal R/C at nominal. PASSIVES.md §6
                      item 1: "nothing downstream is trustworthy until this
                      passes". It is not a pass/fail gate here — it is a
                      MEASUREMENT of what swapping the passives costs, and
                      §6's whole point is that it be reported rather than
                      assumed to be zero.
    --sensitivity     §6e. Per-dimension perturbation. BLOCKING: a dimension
                      the simulator ignores makes PPO train on noise and
                      report a policy, and nothing raises.
    --calibrate       §6f. Three known designs must ORDER correctly under the
                      reward. If they do not, no amount of training helps.
    --train           §6g/§6h. The run.
    --parallel        §6i. Throughput against G48's 3.2x at 11 cores.

USAGE
    python -m nebula.experiments.rl_smoke --regression-4d
    python -m nebula.experiments.rl_smoke --sensitivity
    python -m nebula.experiments.rl_smoke --calibrate
    python -m nebula.experiments.rl_smoke --train --steps 500 --reward v0
    python -m nebula.experiments.rl_smoke --train --steps 200 --reward v1
    python -m nebula.experiments.rl_smoke --parallel
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from nebula.common.types import SPEC_F_PEAK_HZ_RANGE, SPEC_PEAKING_DB_RANGE
from nebula.device.passives import to_geometry
from nebula.device.sky130_runner import CTLE_LIB, TRIMMED_LIB, SizingPoint, run_point
from nebula.device.tail import TailDevice
from nebula.rl import reward_v1 as R
from nebula.rl.contract import (
    ACTION_NAMES,
    ACTION_SPACE,
    CL_CONTEXT_F,
    HORIZON,
    MAX_STEP,
    NF_IN_FIXED,
    N_ACTIONS,
    TAIL_MIRROR_RATIO,
    Sizing,
    sizing_from_u,
    u_from_params,
)
from nebula.rl.env import CtleSizingEnv, EnvConfig
from nebula.rl.evaluator import SpiceBudget, cross_check_sample, evaluate
from nebula.rl.ppo import PPOConfig, train
from nebula.rl.runlog import RunLog

HERE = Path(__file__).resolve().parent

# ─────────────────────────────────────────────────────────────────────────────
# The three reference designs §6f calibrates on.
# ─────────────────────────────────────────────────────────────────────────────

#: **Design 432** — the sole survivor of the load-range screen (session 12b),
#: re-confirmed unchanged by the real tail (session 13b). Parameters copied
#: verbatim from `s9_yield_results.json::stage2.robust_params[0]`, which is the
#: tracked output of the run that found it (G49).
#:
#: ONE FIELD IS CHANGED AND IT IS DECLARED: `nf_in` is 4 here against 8 in the
#: original record, because §6c fixes `nf_in` at 4 and does not search it
#: (G38). On SKY130 `nf` splits width rather than multiplying it, so this is a
#: parasitic-level change, not a different device — but it means the numbers
#: below are NOT bit-comparable with the session-13 record and that is stated
#: rather than discovered.
DESIGN_432: dict = {
    "w_in": 8.92625545820961e-05,
    "l_in": 3.9917271009602323e-07,
    "nf_in": float(NF_IN_FIXED),
    "i_bias": 0.003252196452599106,
    "rs": 318.57999068221557,
    "cs": 1.9012489554268408e-12,
    "rl": 565.0262262062228,
    "cl": 3.262805963205924e-14,
    "vcm_in": 1.4069295334468683,
}

#: The tail sizing rule, `s9_yield.py`'s value. One definition (rule 9) — this
#: script imports the constant rather than restating it.
def _tail_rule_j() -> float:
    from nebula.experiments.s9_yield import TAIL_UM_PER_AMP
    return float(TAIL_UM_PER_AMP)


def _tail_rule_l() -> float:
    from nebula.experiments.s9_yield import TAIL_L_UM
    return float(TAIL_L_UM)


def design_432_u() -> np.ndarray:
    return u_from_params(DESIGN_432, _tail_rule_j(), _tail_rule_l())


def flat_design_u() -> np.ndarray:
    """A design with essentially NO peaking, from 432 by lowering `rs` alone.

    `rs` = 50 ohm is the box floor and `s3_yield.PROPOSED_BOX` measures it at
    **0.08 dB of peaking** — a wire with gain. Everything else is held at 432,
    so the reward difference is attributable to the degeneration and not to a
    different draw. That is the same paired-comparison discipline
    `s3_yield.pin_param` uses.
    """
    p = dict(DESIGN_432, rs=ACTION_SPACE[3].lo)
    return u_from_params(p, _tail_rule_j(), _tail_rule_l())


def op_fail_design_u() -> np.ndarray:
    """A design whose OPERATING POINT fails. Both devices, measured.

    `i_bias` and `rl` both at the box ceiling: 8 mA total through 800 ohm per
    side drops `0.5 * 8 mA * 800` = 3.2 V into a 1.8 V rail. Measured at this
    point: `vds - vdsat` = **-0.293 V** (input pair in triode) and
    `vds_tail - vdsat_tail` = **-0.081 V** (tail in triode too). Both
    coordinates are individually inside their own bounds, which is the joint
    infeasibility G28 is about, reached from inside the box.

    **This replaces a first attempt that was mislabelled**, and the mislabel is
    worth keeping: `rl` alone at 800 ohm with 432's 3.25 mA was called an
    operating-point failure, and it does fail — but at `vds - vdsat` =
    -0.072 V, which the evaluator then reported as an *f_peak range* failure
    because the AC plausibility checks ran first. The design was right and the
    diagnosis was wrong, which is why `validate` now checks the DC operating
    point before the AC result.
    """
    p = dict(DESIGN_432, rl=ACTION_SPACE[5].hi, i_bias=ACTION_SPACE[2].hi)
    return u_from_params(p, _tail_rule_j(), _tail_rule_l())


REFERENCE_DESIGNS: tuple[tuple[str, str], ...] = (
    ("design_432", "the sole corner-and-load-robust survivor (session 12b)"),
    ("flat", "rs at the box floor: 0.165 dB of peaking, a wire with gain"),
    ("op_fail", "i_bias AND rl at their ceilings: both devices in triode"),
)


def reference_u(name: str) -> np.ndarray:
    return {"design_432": design_432_u, "flat": flat_design_u,
            "op_fail": op_fail_design_u}[name]()


# ─────────────────────────────────────────────────────────────────────────────
# Assumptions header. Printed by EVERY subcommand (§8 rule 8).
# ─────────────────────────────────────────────────────────────────────────────


def assumptions_header(seed: int, reward_name: str) -> str:
    L = ["=" * 78, "RL SMOKE RUN (task 6) -- ASSUMPTIONS", "=" * 78]
    L.append("  THE GOAL IS INTEGRATION BUGS, NOT A POLICY. No hyperparameter")
    L.append("  is tuned and no conclusion about learning is drawn (task 6).")
    L.append("")
    L.append(f"  seed                {seed}  (threaded via EnvConfig/PPOConfig only, G3)")
    L.append(f"  corner              TT / 1.00 VDD / 27 C  -- ONE corner")
    L.append(f"  cl                  {CL_CONTEXT_F * 1e15:.2f} fF = cl_mid, CONTEXT not action")
    L.append(f"  nf_in               FIXED at {NF_IN_FIXED} (G38: +/-10% NON-MONOTONIC)")
    L.append(f"  action dims         {N_ACTIONS}: {', '.join(ACTION_NAMES)}")
    L.append(f"  max step            {MAX_STEP} of the box per dim per step")
    L.append(f"  horizon             {HORIZON} edits, early-terminate on success")
    L.append(f"  reward              {reward_name}")
    L.append(f"  passives            REAL SKY130 devices via to_geometry() (task 4i)")
    L.append(f"  library             {CTLE_LIB.name}  (extended trim, G58's 25 sections)")
    L.append(f"  tail                current mirror, N = {TAIL_MIRROR_RATIO:g}; I_ref still ideal")
    L.append("")
    L.append("  NOT IN THE REWARD, and each is a conclusion rather than a gap:")
    L.append("    S4 (HD3)   needs transient+FFT; .disto is exactly 0.0 on BSIM4 (G21)")
    L.append("    S7 (area)  device area only exists as a LOWER bound (PASSIVES.md 4.5)")
    L.append("    S8 (eye)   a link-layer metric, and the link layer is a MOCK (G16).")
    L.append("               Task 6b makes any path from training to a mock impossible,")
    L.append("               so S8 CANNOT be scored here. That is the correct outcome.")
    L.append("")
    L.append("  NO ANALYTIC QUANTITY IS IN THE REWARD PATH (task 6a). Every scored")
    L.append("  number is a measured SPICE primitive or arithmetic on measured")
    L.append("  primitives. The sec 6 design equations appear ONLY as the expected")
    L.append("  DIRECTIONS of the 6e gate -- G60 measured them over-predicting the")
    L.append("  Nyquist boost by 0.77-1.47 dB, growing with Rs.")
    L.append("=" * 78)
    return "\n".join(L)


# ─────────────────────────────────────────────────────────────────────────────
# 4d — the regression PASSIVES.md §6 lists first.
# ─────────────────────────────────────────────────────────────────────────────


def regression_4d(n_designs: int = 6, seed: int = 20260807) -> dict:
    """Real drawn passives vs ideal R/C, same designs, same corner.

    PASSIVES.md §6 item 1. **Not a pass/fail gate**: the honest output is the
    SIZE of the shift and its mechanism, because a shift is expected — the
    drawn resistors carry a `res_po` bottom-plate parasitic that the ideal
    elements do not, and half of it lands on the output node (PASSIVES.md
    §4.4), i.e. it adds to `cl` and moves `f_p2`.

    Reporting it as "within tolerance" would be the wrong shape of answer.
    The number that matters is the shift in OCTAVES of `f_peak`, against the
    0.12 octaves of centring slack session 12b measured.
    """
    from nebula.experiments.s3_yield import PROPOSED_BOX, sample_box

    rows = [DESIGN_432] + sample_box(PROPOSED_BOX, n_designs - 1, seed)
    out = []
    for i, p in enumerate(rows[:n_designs]):
        p = dict(p, nf_in=float(NF_IN_FIXED), cl=CL_CONTEXT_F)
        i_side = float(p["i_bias"]) / 2.0
        w_t = i_side * _tail_rule_j()
        from nebula.device.tail import min_nf_for_width
        tail = TailDevice(w_tail=w_t, l_tail=_tail_rule_l(),
                          nf_tail=min_nf_for_width(w_t, TAIL_MIRROR_RATIO),
                          mirror_ratio=TAIL_MIRROR_RATIO)
        try:
            geo = to_geometry(p["rs"], p["cs"], p["rl"])
        except ValueError as exc:
            out.append({"idx": i, "skipped": f"unrealisable: {exc}"})
            continue
        rec = {"idx": i, "rs": p["rs"], "cs": p["cs"], "rl": p["rl"]}
        for label, pas in (("ideal", None), ("real", geo)):
            pt = SizingPoint.from_params(p, vdd=1.8, tail=tail, passives=pas)
            t0 = time.perf_counter()
            r = run_point(pt, corner="tt", swing=False)
            rec[f"{label}_s"] = time.perf_counter() - t0
            if not r.ok:
                rec[f"{label}_fail"] = r.fail_reason
                continue
            rec[f"{label}_peaking_db"] = r.peaking_db
            rec[f"{label}_f_pk_hz"] = r.f_pk_hz
            rec[f"{label}_nyq_db"] = r.nyquist_boost_db
            rec[f"{label}_g_dc_db"] = r.g_dc_db
            rec[f"{label}_noise"] = r.vn_in_vrms
        if "real_f_pk_hz" in rec and "ideal_f_pk_hz" in rec:
            rec["d_peaking_db"] = rec["real_peaking_db"] - rec["ideal_peaking_db"]
            rec["d_f_pk_oct"] = math.log2(rec["real_f_pk_hz"] / rec["ideal_f_pk_hz"])
            rec["d_nyq_db"] = rec["real_nyq_db"] - rec["ideal_nyq_db"]
            rec["d_g_dc_db"] = rec["real_g_dc_db"] - rec["ideal_g_dc_db"]
            rec["d_noise_rel"] = rec["real_noise"] / rec["ideal_noise"] - 1.0
            rec["rs_quant_rel"] = geo.rs.rel_error
            rec["cs_quant_rel"] = geo.cs.rel_error
            rec["rl_quant_rel"] = geo.rl.rel_error
            rec["rl_bottom_plate_half_f"] = geo.rl.parasitic_to_bulk_f() / 2.0
        out.append(rec)
    return {"rows": out}


def print_4d(res: dict) -> None:
    print("\n" + "=" * 78)
    print("4d REGRESSION -- drawn SKY130 passives vs ideal R/C, TT/1.00/27 C")
    print("=" * 78)
    print("  PASSIVES.md sec 6 item 1. The expected mechanism is NOT zero: the")
    print("  drawn load resistors carry a res_po bottom-plate parasitic, half of")
    print("  which lands on the output node, adding to cl and moving f_p2 down.")
    print()
    hdr = (f"  {'#':>2}  {'d_peak':>8} {'d_fpk':>9} {'d_nyq':>8} {'d_gdc':>8} "
           f"{'d_nois':>8} {'C_bot/2':>9} {'t_id':>6} {'t_re':>6}")
    print(hdr)
    print(f"  {'':>2}  {'dB':>8} {'oct':>9} {'dB':>8} {'dB':>8} {'rel':>8} "
          f"{'fF':>9} {'s':>6} {'s':>6}")
    print("  " + "-" * 74)
    dfp, dpk = [], []
    for r in res["rows"]:
        if "d_f_pk_oct" not in r:
            print(f"  {r['idx']:>2}  {r.get('skipped', r.get('real_fail', 'no data'))[:60]}")
            continue
        dfp.append(r["d_f_pk_oct"]); dpk.append(r["d_peaking_db"])
        print(f"  {r['idx']:>2}  {r['d_peaking_db']:>+8.4f} {r['d_f_pk_oct']:>+9.4f} "
              f"{r['d_nyq_db']:>+8.4f} {r['d_g_dc_db']:>+8.4f} "
              f"{r['d_noise_rel']:>+8.4f} {r['rl_bottom_plate_half_f'] * 1e15:>9.2f} "
              f"{r['ideal_s']:>6.2f} {r['real_s']:>6.2f}")
    if dfp:
        print("  " + "-" * 74)
        print(f"  worst |d_f_peak| = {max(abs(x) for x in dfp):.4f} octaves "
              f"against 0.12 octaves of centring slack (session 12b)")
        print(f"  worst |d_peaking| = {max(abs(x) for x in dpk):.4f} dB "
              f"against 1.0 dB of corner-robustness margin (session 11)")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# 6e — the action-response sensitivity gate. BLOCKING.
# ─────────────────────────────────────────────────────────────────────────────

#: For each action dimension: the observation channel it should move most, the
#: expected SIGN of that move for a POSITIVE perturbation, and the reasoning.
#:
#: **These are EXPECTATIONS for a gate, not scored quantities.** They come from
#: the §6 design equations (`k = 1 + (gm+gmbs)*Rs/2`, `w_z = 1/(Rs*Cs)`,
#: `w_p2 = 1/(RL*CL)`, `A_dc = gm*RL/k`) and from measured monotonicities in
#: `s3_yield.PROPOSED_BOX`'s provenance strings. G60 measured those equations
#: over-predicting the Nyquist boost by 0.8-1.5 dB, so they are fit to predict
#: a DIRECTION and not a magnitude — which is exactly what this gate needs and
#: all it is allowed to use them for.
SENSITIVITY: tuple[tuple[str, str, int, str], ...] = (
    ("w_in", "peaking_db", +1,
     "wider device -> more gm -> larger k = 1+(gm+gmbs)Rs/2 -> more peaking"),
    ("l_in", "peaking_db", -1,
     "longer channel -> less gm at fixed current -> smaller k"),
    ("i_bias", "power_w", +1,
     "more current -> more power, directly (billed on the MEASURED supply)"),
    ("rs", "peaking_db", +1,
     "PROPOSED_BOX measured Rs 50->800 taking peaking 0.08 -> 13.25 dB"),
    ("cs", "f_peak_oct", -1,
     "f_zero = 1/(2 pi Rs Cs): more Cs -> lower zero -> lower peak"),
    ("rl", "f_peak_oct", -1,
     "f_p2 = 1/(2 pi RL CL): more RL -> lower second pole -> lower peak"),
    ("vcm_in", "tail_margin_v", +1,
     "v(source) tracks VCM almost 1:1 while vdsat_tail barely moves, so the "
     "tail's vds - vdsat opens up"),
    ("tail_j", "tail_margin_v", +1,
     "more tail width per amp -> lower current density -> lower vdsat_tail"),
    ("l_tail", "tail_margin_v", -1,
     "longer tail needs more Vgs for the same current at fixed width, which "
     "raises vdsat_tail and closes the margin"),
)

#: The perturbation, in normalised box units. One `MAX_STEP` — the largest edit
#: the policy can make in a single step — so the gate measures what ONE ACTION
#: is worth, not what an arbitrarily large one is.
SENS_DELTA: float = MAX_STEP

#: Below this the dimension is treated as INERT and the gate FAILS. It is a
#: floor on the OBSERVATION channel in its normalised units, i.e. after
#: division by `OBS_SCALES`. 0.01 means "one percent of the channel's own
#: scale" — a hundredth of a spec window. A truly ignored parameter moves it by
#: exactly 0.0, so the threshold only has to separate zero from measurable.
SENS_MIN_ABS: float = 0.01


def sensitivity_gate(budget: SpiceBudget, base_u: Optional[np.ndarray] = None
                     ) -> dict:
    """§6e. Perturb each dimension alone; assert direction and magnitude.

    *"This catches the failure mode that has bitten this project more than any
    other -- a parameter that is written, accepted, and silently ignored.
    `alter` on W did it, `mult` does it, `w` on fixed-width resistors does it.
    If one action dimension is inert, PPO will still train, still produce a
    curve, and still report a policy, and nothing will raise."*

    The base point is design 432, because it is a design known to simulate
    cleanly at every corner and load — a base that is itself near a failure
    boundary would produce invalid perturbations and hide the answer.
    """
    from nebula.rl.contract import OBS_SCALES

    scale = {s.name: s.scale for s in OBS_SCALES}
    base_u = design_432_u() if base_u is None else np.asarray(base_u, float)
    base = evaluate(sizing_from_u(base_u), budget)
    if not base.valid:
        raise RuntimeError(
            f"the 6e base point is not a valid circuit: {base.reason}. "
            f"The gate cannot run against a base it cannot measure."
        )

    rows = []
    for name, channel, expect, why in SENSITIVITY:
        i = ACTION_NAMES.index(name)
        row = {"dim": name, "channel": channel, "expected_sign": expect,
               "reasoning": why, "delta_u": SENS_DELTA}
        # TRY BOTH DIRECTIONS, and this is a FIX, not a refinement.
        #
        # The gate as first written perturbed one way — up unless the base sat
        # against the ceiling — and reported `i_bias` as a failed dimension.
        # It was not inert: +0.15 of the box took 3.25 mA to 4.93 mA, which
        # raised gm enough to push the peak clean out of the sweep, and the
        # §6d validity gate rejected the result at f_pk = 19.95 GHz. A
        # perturbation is only evidence about a dimension if the perturbed
        # point is a circuit; a one-sided probe conflates "this axis does
        # nothing" with "this axis leaves the feasible region", and those need
        # opposite responses. Both directions invalid IS reported, as
        # `INVALID BOTH` — that is a real finding about the base point.
        order = ([+1.0, -1.0] if base_u[i] + SENS_DELTA <= 1.0
                 else [-1.0, +1.0])
        ev = None
        tried = []
        for sign in order:
            u2 = base_u.copy()
            u2[i] = float(np.clip(u2[i] + sign * SENS_DELTA, 0.0, 1.0))
            if abs(u2[i] - base_u[i]) < 1e-12:
                continue                      # pinned against this edge
            cand = evaluate(sizing_from_u(u2), budget)
            tried.append({"sign": sign, "valid": cand.valid,
                          "reason": cand.reason})
            if cand.valid:
                ev = cand
                row["applied_sign"] = sign
                row["u_before"], row["u_after"] = float(base_u[i]), float(u2[i])
                row["phys_before"] = ACTION_SPACE[i].to_physical(base_u[i])
                row["phys_after"] = ACTION_SPACE[i].to_physical(u2[i])
                break
        row["attempts"] = tried
        if ev is None:
            row.update(valid=False, passed=False, verdict="INVALID BOTH",
                       reason="; ".join(f"{t['sign']:+.0f}: {t['reason']}"
                                        for t in tried),
                       applied_sign=0.0,
                       u_before=float(base_u[i]), u_after=float(base_u[i]),
                       phys_before=ACTION_SPACE[i].to_physical(base_u[i]),
                       phys_after=ACTION_SPACE[i].to_physical(base_u[i]))
            rows.append(row)
            continue
        sign = row["applied_sign"]

        raw_delta = ev.meas[channel] - base.meas[channel]
        norm_delta = raw_delta / scale[channel]
        # A negative applied sign flips what "expected" means.
        observed_sign = int(np.sign(norm_delta)) if norm_delta != 0 else 0
        want = expect * int(sign)
        big_enough = abs(norm_delta) >= SENS_MIN_ABS
        right_way = observed_sign == want
        row.update(valid=True, raw_delta=raw_delta, norm_delta=norm_delta,
                   observed_sign=observed_sign, wanted_sign=want,
                   big_enough=big_enough, right_way=right_way,
                   passed=bool(big_enough and right_way),
                   verdict=("PASS" if (big_enough and right_way)
                            else ("INERT" if not big_enough else "WRONG SIGN")),
                   # Every channel, so a dimension that moves the "wrong" thing
                   # is visible rather than merely failing.
                   all_deltas={k: (ev.meas[k] - base.meas[k]) / scale[k]
                               for k in base.meas})
        rows.append(row)
    return {"base_meas": dict(base.meas), "base_design_id": base.design_id,
            "rows": rows,
            "n_pass": sum(1 for r in rows if r.get("passed")),
            "n_total": len(rows)}


def print_sensitivity(res: dict) -> None:
    print("\n" + "=" * 78)
    print("6e ACTION-RESPONSE SENSITIVITY GATE  (BLOCKING)")
    print("=" * 78)
    print(f"  base: design 432, id {res['base_design_id']}")
    print(f"  perturbation: {SENS_DELTA} of the box (= one MAX_STEP), one dim at a time")
    print(f"  inert threshold: |d_obs| < {SENS_MIN_ABS} of the channel's own scale")
    print()
    print(f"  {'dim':<8} {'channel':<14} {'phys before -> after':<26} "
          f"{'d_obs':>9} {'want':>5} {'got':>5}  verdict")
    print("  " + "-" * 88)
    for r in res["rows"]:
        pa = f"{r['phys_before']:.4g} -> {r['phys_after']:.4g}"
        if not r.get("valid"):
            print(f"  {r['dim']:<8} {r['channel']:<14} {pa:<26} "
                  f"{'--':>9} {'':>5} {'':>5}  INVALID: {r['reason'][:40]}")
            continue
        print(f"  {r['dim']:<8} {r['channel']:<14} {pa:<26} "
              f"{r['norm_delta']:>+9.4f} {r['wanted_sign']:>+5d} "
              f"{r['observed_sign']:>+5d}  {r['verdict']}")
    print("  " + "-" * 88)
    print(f"  {res['n_pass']}/{res['n_total']} dimensions pass.")
    if res["n_pass"] < res["n_total"]:
        print("  >>> BLOCKING. A dimension the simulator ignores makes PPO train")
        print("  >>> on noise and still report a policy. Fix before training.")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# 6f — reward calibration on known designs.
# ─────────────────────────────────────────────────────────────────────────────


def calibrate(budget: SpiceBudget, cfg: EnvConfig) -> dict:
    """§6f. Three known designs must ORDER correctly, or the reward is wrong.

    *"If the reward does not order these correctly, the reward is wrong and no
    amount of training will fix it."*
    """
    out = []
    for name, note in REFERENCE_DESIGNS:
        u = reference_u(name)
        ev = evaluate(sizing_from_u(u, cl_f=cfg.cl_f), budget,
                      corner=cfg.corner, temp_c=cfg.temp_c)
        row = {"name": name, "note": note, "valid": ev.valid,
               "reason": ev.reason, "design_id": ev.design_id}
        for label, specs in (("v0", R.V0_SPECS), ("v1", R.V1_SPECS)):
            rb = R.reward(ev.meas, cfg.target_f_peak_hz, specs=specs,
                          target_peaking_db=cfg.target_peaking_db)
            row[label] = {"reward": rb.reward, "feasible": rb.feasible,
                          "valid": rb.valid, "worst": rb.worst_spec,
                          "n_violated": rb.n_violated,
                          "shortfalls": rb.shortfalls}
        if ev.valid:
            row["meas"] = dict(ev.meas)
        out.append(row)

    verdict = {}
    for label in ("v0", "v1"):
        r = {x["name"]: x[label]["reward"] for x in out}
        ordered = (r["design_432"] > r["flat"] > r["op_fail"])
        floor = R.invalid_reward(len(R.V0_SPECS if label == "v0" else R.V1_SPECS))
        verdict[label] = {
            "rewards": r, "ordered": bool(ordered),
            "op_fail_at_floor": bool(abs(r["op_fail"] - floor) < 1e-9),
            "floor": floor,
        }
    return {"rows": out, "verdict": verdict}


def print_calibration(res: dict) -> None:
    print("\n" + "=" * 78)
    print("6f REWARD CALIBRATION -- three known designs")
    print("=" * 78)
    for x in res["rows"]:
        print(f"  {x['name']:<12} {x['note']}")
        if not x["valid"]:
            print(f"               INVALID: {x['reason'][:64]}")
        else:
            m = x["meas"]
            print(f"               peaking {m['peaking_db']:+7.3f} dB   "
                  f"f_peak {m['f_peak_oct']:+6.3f} oct   "
                  f"nyq {m['nyq_boost_db']:+7.3f} dB   "
                  f"tail {m['tail_margin_v']:+6.3f} V")
        for label in ("v0", "v1"):
            v = x[label]
            state = ("INVALID" if not v["valid"]
                     else ("FEASIBLE" if v["feasible"]
                           else f"infeasible on {v['n_violated']}, worst {v['worst']}"))
            print(f"               reward {label}: {v['reward']:+9.4f}   {state}")
        print()
    for label in ("v0", "v1"):
        w = res["verdict"][label]
        r = w["rewards"]
        print(f"  {label}: 432 {r['design_432']:+8.4f} > flat {r['flat']:+8.4f} "
              f"> op_fail {r['op_fail']:+8.4f}   "
              f"ordered={w['ordered']}  op_fail at floor "
              f"({w['floor']:+.1f})={w['op_fail_at_floor']}")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# 6g/6h — the run.
# ─────────────────────────────────────────────────────────────────────────────


def run_training(steps: int, seed: int, reward_name: str,
                 log_path: Path, cross_check_every: int = 40) -> dict:
    specs = R.V0_SPECS if reward_name == "v0" else R.V1_SPECS
    cfg = EnvConfig(seed=seed, specs=specs)
    budget = SpiceBudget()

    header = {
        "task": "6g/6h RL smoke run",
        "seed": seed, "reward": reward_name, "steps_requested": steps,
        "specs": list(specs),
        "tolerances": {t.name: {"value": t.value, "unit": t.unit,
                                "basis": t.basis} for t in R.TOLERANCES},
        "action_space": [{"name": d.name, "lo": d.lo, "hi": d.hi,
                          "log": d.log, "unit": d.unit,
                          "provenance": d.provenance} for d in ACTION_SPACE],
        "horizon": cfg.horizon, "max_step": cfg.max_step,
        "cl_f": cfg.cl_f, "corner": cfg.corner, "temp_c": cfg.temp_c,
        "nf_in_fixed": NF_IN_FIXED,
        "target_f_peak_hz": cfg.target_f_peak_hz,
        "target_peaking_db": cfg.target_peaking_db,
        "library": CTLE_LIB.name, "passives": "real (to_geometry)",
        "platform": platform.platform(), "python": sys.version.split()[0],
        "started": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    t_wall = time.perf_counter()
    with RunLog(log_path, header) as log:
        env = CtleSizingEnv(cfg, budget=budget, on_step=log.step)
        ppo_cfg = PPOConfig(seed=seed, total_steps=steps)
        log.event("ppo_config", **asdict(ppo_cfg))
        net, stats = train(env, ppo_cfg)
        wall = time.perf_counter() - t_wall

        # §6d: a random sample cross-checked against an INDEPENDENT
        # recomputation from raw SPICE output. Every call is charged (§6i).
        checks = []
        rng = np.random.default_rng(seed + 1)
        valid_records = [r for r in env.records if r.valid]
        if valid_records:
            k = max(1, len(valid_records) // cross_check_every)
            for idx in rng.choice(len(valid_records), size=min(k, len(valid_records)),
                                  replace=False):
                rec = valid_records[int(idx)]
                s = sizing_from_u(rec.u, cl_f=cfg.cl_f)
                cc = cross_check_sample(s, budget)
                checks.append(asdict(cc))
                log.event("cross_check", **asdict(cc))

        # §6d: does the invalid rate RISE over the run? If it does, the agent
        # is finding the holes -- which is exactly what this run is for.
        halves = _invalid_by_half(env.records)
        summary = {
            "wall_s": wall,
            "env_s": stats.env_seconds, "policy_s": stats.policy_seconds,
            "update_s": float(sum(stats.update_seconds)),
            "spice_calls": budget.calls, "spice_s": budget.seconds,
            "steps": steps, "episodes": len(stats.episode_return),
            "invalid_rate": env.invalid_rate,
            "invalid_reasons": dict(env.invalid_reasons),
            "invalid_first_half": halves[0], "invalid_second_half": halves[1],
            "episode_return": stats.episode_return,
            "episode_length": stats.episode_length,
            "episode_end_step": stats.episode_end_step,
            "policy_loss": stats.policy_loss, "value_loss": stats.value_loss,
            "entropy": stats.entropy,
            "cross_checks": checks,
            "n_records": len(env.records),
            "n_feasible": sum(1 for r in env.records if r.feasible),
            "shortfall_stats": _shortfall_stats(env.records, specs),
        }
        log.event("summary", **summary)
    return summary


def _invalid_by_half(records) -> tuple[float, float]:
    """Invalid rate in the first and second half of the run, by EVALUATION.

    Split by evaluation index rather than by wall clock, so an episode that
    happens to run long cannot move the boundary.
    """
    if not records:
        return 0.0, 0.0
    mid = len(records) // 2
    def _rate(rs):
        return (sum(1 for r in rs if not r.valid) / len(rs)) if rs else 0.0
    return _rate(records[:mid]), _rate(records[mid:])


def _shortfall_stats(records, specs) -> dict:
    """§6h: per-spec shortfall distribution over the run.

    *"a spec whose shortfall is identically zero for every step may be
    correctly free, or may be unwired. Distinguish the two."*

    The distinguishing evidence is `n_margin_finite`: a spec that is WIRED
    produces a finite MARGIN on every valid step even when its shortfall is
    zero, because the margin is computed and merely happens to be positive.
    An UNWIRED spec has no margin at all. So `shortfall == 0 everywhere` plus
    `margin present and varying` means correctly free; `margin absent or
    constant` means look again.
    """
    out = {}
    for name in specs:
        sf = [r.shortfalls[name] for r in records
              if r.valid and name in r.shortfalls]
        mg = [r.margins[name] for r in records
              if r.valid and name in r.margins]
        if not sf:
            out[name] = {"n": 0, "wired": False,
                         "note": "NO ROWS -- the spec is not wired at all"}
            continue
        arr = np.asarray(sf, dtype=float)
        marr = np.asarray(mg, dtype=float)
        n_pos = int((arr > 0).sum())
        out[name] = {
            "n": int(arr.size),
            "n_violated": n_pos,
            "frac_violated": float(n_pos / arr.size),
            "shortfall_max": float(arr.max()),
            "shortfall_mean": float(arr.mean()),
            "shortfall_p90": float(np.percentile(arr, 90)),
            "margin_min": float(marr.min()), "margin_max": float(marr.max()),
            "margin_spread": float(marr.max() - marr.min()),
            "wired": bool(marr.max() != marr.min() or n_pos > 0),
            "note": ("binds" if n_pos else
                     ("correctly free: margin varies over "
                      f"{marr.min():+.4g}..{marr.max():+.4g} and never goes "
                      f"negative"
                      if marr.max() != marr.min() else
                      "SUSPECT: shortfall zero AND margin constant -- check wiring")),
        }
    return out


def print_run(summary: dict, reward_name: str) -> None:
    print("\n" + "=" * 78)
    print(f"6g THE RUN -- reward {reward_name}")
    print("=" * 78)
    s = summary
    print(f"  {s['steps']} env steps, {s['episodes']} episodes, "
          f"{s['n_records']} evaluations, {s['spice_calls']} SPICE calls")
    print()
    print("  WALL CLOCK DECOMPOSITION (6g)")
    other = s["wall_s"] - s["env_s"] - s["policy_s"]
    for label, v in (("environment (SPICE + parse + validate)", s["env_s"]),
                     ("policy forward + PPO update", s["policy_s"]),
                     ("   of which PPO update alone", s["update_s"]),
                     ("logging, cross-check, bookkeeping", other),
                     ("TOTAL", s["wall_s"])):
        print(f"    {label:<40s} {v:8.2f} s  {100 * v / s['wall_s']:5.1f}%")
    print()
    print("  COST ACCOUNTING (6i)")
    hrs = s["wall_s"] / 3600.0
    print(f"    simulations per step    {s['spice_calls'] / max(s['steps'], 1):.3f}")
    print(f"    seconds per simulation  {s['spice_s'] / max(s['spice_calls'], 1):.3f}")
    print(f"    steps per hour          {s['steps'] / hrs:,.0f}")
    print(f"    simulations per hour    {s['spice_calls'] / hrs:,.0f}")
    print()
    print("  INVALID-EVALUATION RATE (6d)")
    print(f"    overall     {100 * s['invalid_rate']:6.2f}%")
    print(f"    first half  {100 * s['invalid_first_half']:6.2f}%")
    print(f"    second half {100 * s['invalid_second_half']:6.2f}%   "
          f"{'RISING -- the agent is finding the holes' if s['invalid_second_half'] > s['invalid_first_half'] + 0.02 else 'not rising'}")
    for k, v in sorted(s["invalid_reasons"].items(), key=lambda kv: -kv[1]):
        print(f"      {k:<24s} {v:5d}")
    print()
    if s["cross_checks"]:
        agree = sum(1 for c in s["cross_checks"] if c["agrees"])
        print(f"  CROSS-CHECK (6d): {agree}/{len(s['cross_checks'])} agree; "
              f"disagreement rate {100 * (1 - agree / len(s['cross_checks'])):.1f}%")
        for c in s["cross_checks"][:5]:
            print(f"      {c['design_id']}  {c['detail']}")
        print()
    print("  REWARD CURVE -- EVIDENCE THE PLUMBING WORKS, NOT A RESULT.")
    print("  NO CONCLUSION ABOUT LEARNING IS DRAWN FROM 500 STEPS.")
    rets = s["episode_return"]
    if rets:
        q = max(1, len(rets) // 4)
        for i in range(0, len(rets), q):
            chunk = rets[i:i + q]
            print(f"    episodes {i:>3}-{i + len(chunk) - 1:<3}  "
                  f"mean return {np.mean(chunk):+9.3f}  "
                  f"min {min(chunk):+9.3f}  max {max(chunk):+9.3f}")
    print()
    print("  PER-SPEC SHORTFALL DISTRIBUTION (6h)")
    for name, st in s["shortfall_stats"].items():
        if st["n"] == 0:
            print(f"    {name:<18s} {st['note']}")
            continue
        print(f"    {name:<18s} violated {st['n_violated']:>4}/{st['n']:<4} "
              f"({100 * st['frac_violated']:5.1f}%)  max {st['shortfall_max']:6.3f}  "
              f"mean {st['shortfall_mean']:6.3f}")
        print(f"    {'':<18s}   {st['note']}")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# 6i — parallel throughput, against G48.
# ─────────────────────────────────────────────────────────────────────────────


def _one_task(u_list):
    """Module-level so ProcessPoolExecutor can pickle it."""
    b = SpiceBudget()
    ev = evaluate(sizing_from_u(np.asarray(u_list, dtype=float)), b)
    return (ev.valid, b.calls, b.seconds)


def parallel_throughput(n_tasks: int = 24, worker_counts: Sequence[int] = (1, 2, 4, 8, 11),
                        seed: int = 20260807) -> dict:
    """§6i. Measure the speedup curve, against G48's measured 3.2x at 11 cores.

    G48 measured that on the NFET-ONLY library at ~318 ms serial. This run uses
    the EXTENDED library at ~4x that, so the arithmetic prediction is that the
    curve improves: a longer compute phase per process amortises the same
    process-launch and disk contention over more work. Whether it does is the
    measurement.
    """
    from concurrent.futures import ProcessPoolExecutor

    rng = np.random.default_rng(seed)
    tasks = [rng.uniform(0.0, 1.0, N_ACTIONS).tolist() for _ in range(n_tasks)]
    out = []
    for w in worker_counts:
        t0 = time.perf_counter()
        if w <= 1:
            res = [_one_task(t) for t in tasks]
        else:
            with ProcessPoolExecutor(max_workers=w) as ex:
                res = list(ex.map(_one_task, tasks, chunksize=1))
        dt = time.perf_counter() - t0
        out.append({"workers": w, "wall_s": dt, "ms_per_task": 1e3 * dt / n_tasks,
                    "n_valid": sum(1 for r in res if r[0]),
                    "spice_calls": sum(r[1] for r in res)})
    base = out[0]["ms_per_task"]
    for r in out:
        r["speedup"] = base / r["ms_per_task"]
    return {"n_tasks": n_tasks, "rows": out}


def print_parallel(res: dict) -> None:
    print("\n" + "=" * 78)
    print("6i PARALLEL THROUGHPUT -- against G48's 3.2x at 11 cores")
    print("=" * 78)
    print(f"  {res['n_tasks']} identical-cost tasks, real passives, extended library")
    print()
    print(f"  {'workers':>8} {'ms/task':>10} {'speedup':>9} {'valid':>7}")
    print("  " + "-" * 38)
    for r in res["rows"]:
        print(f"  {r['workers']:>8} {r['ms_per_task']:>10.1f} "
              f"{r['speedup']:>9.2f}x {r['n_valid']:>7}")
    print()
    print("  G48 measured, on the NFET-ONLY library: 318 / 179 / 150 / 106 / 100")
    print("  ms/task at 1 / 2 / 4 / 8 / 11 workers -- 3.18x, flat past 8.")
    print()


# ─────────────────────────────────────────────────────────────────────────────


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--regression-4d", action="store_true")
    ap.add_argument("--sensitivity", action="store_true")
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--parallel", action="store_true")
    ap.add_argument("--steps", type=int, default=500)
    ap.add_argument("--reward", choices=("v0", "v1"), default="v0")
    ap.add_argument("--seed", type=int, default=20260807)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    if not any((args.regression_4d, args.sensitivity, args.calibrate,
                args.train, args.parallel)):
        ap.error("choose at least one stage; see the module docstring")

    print(assumptions_header(args.seed, args.reward))
    results: dict = {"seed": args.seed}
    budget = SpiceBudget()
    t0 = time.perf_counter()

    if args.regression_4d:
        r = regression_4d()
        print_4d(r)
        results["regression_4d"] = r

    if args.sensitivity:
        r = sensitivity_gate(budget)
        print_sensitivity(r)
        results["sensitivity"] = r
        if r["n_pass"] < r["n_total"]:
            print("BLOCKING: 6e failed. Not proceeding to training.")
            _save(results, args.out, "rl_smoke_results.json")
            return 1

    if args.calibrate:
        cfg = EnvConfig(seed=args.seed)
        r = calibrate(budget, cfg)
        print_calibration(r)
        results["calibration"] = r

    if args.train:
        log_path = HERE / f"rl_smoke_run_{args.reward}.jsonl"
        r = run_training(args.steps, args.seed, args.reward, log_path)
        print_run(r, args.reward)
        r["log_path"] = str(log_path.relative_to(HERE.parents[1]))
        results[f"train_{args.reward}"] = r

    if args.parallel:
        r = parallel_throughput()
        print_parallel(r)
        results["parallel"] = r

    results["gate_spice_calls"] = budget.calls
    results["total_wall_s"] = time.perf_counter() - t0
    _save(results, args.out, "rl_smoke_results.json")
    return 0


def _save(results: dict, out: Optional[Path], default: str) -> None:
    path = out or (HERE / default)
    # TRACKED, not gitignored (G49): the write-up quotes numbers from it.
    prev = {}
    if path.exists():
        try:
            prev = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            prev = {}
    prev.update(results)
    path.write_text(json.dumps(prev, indent=1, default=str), encoding="utf-8")
    print(f"wrote {path}")


if __name__ == "__main__":
    raise SystemExit(main())
