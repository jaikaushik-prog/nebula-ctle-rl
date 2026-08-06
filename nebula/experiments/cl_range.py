"""
experiments/cl_range.py — where `cl` comes from, and how wide it really is.

WHAT THIS REPLACES
------------------
`cl` has been a pinned constant of 150 fF in every corner experiment
(`S9_YIELD.md` §1, assumption 1). 150 fF is the value that MAXIMISED the S3
yield among the five tested in `CL_SENSITIVITY.md` — which is choosing the
answer. That document says so itself (§6): *"pinning it at whatever value
maximises S3 yield, if that value is not physically justifiable, is choosing
the answer. The honest version fixes it from an estimate of the following
stage's input capacitance."*

This is that estimate, and it makes `cl` a **context variable with a
physically derived range**: not a design variable (nobody chooses the next
stage's input capacitance) and not a constant (it is not known to one value).
The range is then screened like a PVT corner — see `s9_yield.py`.

THREE INPUTS, AND THEY ARE NOT EQUALLY SOLID
--------------------------------------------
Ordered by how much a reader should trust them:

1. **The device capacitance: MEASURED**, per corner and temperature, by
   `device/cap_probe.py`, driving the loading pair differentially and reading
   the AC current the driver has to supply. Not `@m[cgg]`, which understates
   it by ~2x (G50).
2. **The routing allowance: DERIVED FROM PDK DATA, with one design-rule
   input.** Capacitance per unit length is read out of SKY130's own
   `cap_vpp_01p8x01p8_m1m2_noshield` model, whose subckt states both its total
   capacitance and its metal run length in squares. Converting squares to
   microns needs the metal width, which is a design rule and is not in any
   SPICE deck in this install — that one number is declared, not measured.
3. **Which devices hang on the node, and how big they are: A SKETCH.** This is
   the dominant contributor to the WIDTH of the range and the least defensible
   part of it. Each size below carries its reasoning; a reader who disagrees
   with the reasoning gets a different range, which is exactly why the answer
   is delivered as a range with per-edge provenance rather than as a number.

USAGE
    python -m nebula.experiments.cl_range              # measure + report
    python -m nebula.experiments.cl_range --from-csv   # report only, no SPICE
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional, Sequence

from nebula.device.cap_probe import (
    F_NYQUIST_HZ,
    GateLoadPoint,
    LoadStage,
    analytic_load_ff,
    measure_gate_load,
    model_file_for_corner,
    sanity_check_load,
)
from nebula.device.sky130_runner import VALID_CORNERS

HERE = Path(__file__).resolve().parent
DATA_CSV = HERE / "cl_range_data.csv"
RESULTS_JSON = HERE / "cl_range_results.json"


# ─────────────────────────────────────────────────────────────────────────────
# 1. THE SKETCH: what hangs on the CTLE output node.
#
# S2 fixes the topology as "1-stage CTLE with source degeneration + 1-tap DFE".
# The CTLE's differential output therefore drives, per side:
#
#   * the **1-tap DFE summer** input pair — the stage at whose output the DFE
#     tap current is subtracted;
#   * the **slicer** input pair — the decision element.
#
# Both are gate loads, so each contributes one gate to each CTLE output node.
# Both are sized at L = 0.15 um, the minimum SKY130 nfet_01v8 bin: these are
# speed-critical stages, neither needs output resistance, and f_T falls as
# 1/L^2 (G39).
#
# The min/max pair for each stage brackets a real design decision, not an
# arbitrary +/-. They are stated in `why` and repeated in CL_RANGE.md.
# ─────────────────────────────────────────────────────────────────────────────

#: SKY130 nfet_01v8 threshold-mismatch coefficient, in mV*um, read off the
#: PDK's own mismatch card: `vth0 = 0.5190093 + AGAUSS(0,1,1) * (vth0_slope /
#: sqrt(l*w*mult))` with `vth0_slope = 3.356e-3`
#: (`sky130_fd_pr__nfet_01v8__mismatch.corner.spice`).
#:
#: THE UNITS READING IS AN INFERENCE, NOT A MEASUREMENT, and it is stated here
#: so it can be rejected: `l` and `w` inside that expression are taken to be
#: the instance values in MICRONS (the netlist's own units under
#: `.option scale=1.0u`), giving A_VT = 3.356 mV*um. Read as metres it gives
#: sigma_Vth = 3 kV for an 8 x 0.15 um device, which is not a number about a
#: transistor. Only the SIZING SKETCH depends on this; no measured capacitance
#: does.
A_VT_MV_UM: float = 3.356


def sigma_vth_mv(w_um: float, l_um: float) -> float:
    """Pelgrom sigma(Vth) for one device, in mV."""
    return A_VT_MV_UM / math.sqrt(w_um * l_um)


def sigma_offset_mv(w_um: float, l_um: float) -> float:
    """Input-referred offset of a PAIR: two uncorrelated devices, so sqrt(2).

    Load-resistor mismatch and tail asymmetry add to this; ignoring them makes
    the sizing sketch OPTIMISTIC about how small the slicer can be, i.e. it
    biases `cl_lo` downward, which is the conservative direction for a range.
    """
    return math.sqrt(2.0) * sigma_vth_mv(w_um, l_um)


#: Every loading stage must have |A| >= 1 at Nyquist, or it is not a stage.
#:
#: This is the constraint that stops "smallest defensible" collapsing to
#: "smallest". A summer or slicer front end that attenuates is worse than the
#: wire it replaced: it hands the next element a smaller eye and its own noise
#: and offset on top. Checked in `check_stage_gains` and reported in every run,
#: because the minimum sizes were originally chosen with |A| = 0.85 and the
#: number that flagged it was this one.
MIN_STAGE_GAIN: float = 1.0

LOAD_STAGES: dict[str, LoadStage] = {
    "summer_min": LoadStage(
        name="summer_min", w_um=4.0, l_um=0.15, nf=2,
        i_side_a=0.5e-3, rld_ohm=800.0,
        why="1-tap DFE summer input pair, SMALLEST defensible. The summer's "
            "job is to re-amplify and provide the node where the tap current "
            "is subtracted, so unity gain is the floor and a wider device "
            "buys nothing: its own offset is divided by the CTLE gain ahead "
            "of it and so is not the sizing driver. 0.5 mA/side keeps the "
            "whole following stage inside a sensible share of S6's 15 mW. "
            "The 800 ohm load is SET BY THE GAIN GATE, not chosen: at "
            "0.4 mA/500 ohm this stage measures |A| = 0.85 at TT and at "
            "0.5 mA/700 ohm it measures 0.95 at ss/125 C, both attenuators. "
            "0.5 mA/800 ohm is the smallest of the three that clears unity "
            "everywhere (1.07 at ss/125 C, 1.34 at TT).",
    ),
    "summer_max": LoadStage(
        name="summer_max", w_um=12.0, l_um=0.15, nf=6,
        i_side_a=1.0e-3, rld_ohm=800.0,
        why="1-tap DFE summer input pair, LARGEST defensible. A summer built "
            "for gain ~3 at 1 mA/side needs roughly 3x the width, and the "
            "higher gain also triples the Miller multiplication of Cgd. Both "
            "effects push the load up, which is why this is the upper edge "
            "rather than merely a wider device.",
    ),
    "slicer_min": LoadStage(
        name="slicer_min", w_um=4.0, l_um=0.15, nf=2,
        i_side_a=0.5e-3, rld_ohm=800.0,
        why="Slicer input pair, SMALLEST defensible: an OFFSET-TRIMMED "
            "receiver. At W=4 L=0.15 the pair's own 3-sigma input offset is "
            "~18 mV, far too much against S8's 100 mV eye on its own — so "
            "this size is only available if the receiver carries an offset "
            "trim DAC, which is standard in a SerDes slicer. Sizing for "
            "matching is then unnecessary and the device shrinks to whatever "
            "gives MIN_STAGE_GAIN. IDENTICAL to summer_min, and deliberately "
            "not perturbed to look different: two stages whose minimum size "
            "is set by the same gm floor land on the same device.",
    ),
    "slicer_max": LoadStage(
        name="slicer_max", w_um=16.0, l_um=0.15, nf=8,
        i_side_a=1.0e-3, rld_ohm=800.0,
        why="Slicer input pair, LARGEST defensible: an UNTRIMMED receiver, "
            "where matching alone has to deliver the offset. W=16 L=0.15 "
            "gives ~9 mV 3-sigma input offset, under a tenth of S8's 100 mV "
            "eye, which is the usual budget. This is the biggest the pair has "
            "any reason to be: A_VT/sqrt(WL) improves only as sqrt(W), so "
            "another 2x of width buys 30% of offset for 100% of load.",
    ),
}

#: Which stages hang on the node at each edge of the range. One summer and one
#: slicer, per the topology note above.
EDGE_STAGES: dict[str, tuple[str, str]] = {
    "lo": ("summer_min", "slicer_min"),
    "hi": ("summer_max", "slicer_max"),
}


# ─────────────────────────────────────────────────────────────────────────────
# 2. THE ROUTING ALLOWANCE.
# ─────────────────────────────────────────────────────────────────────────────

#: SKY130 met1/met2 minimum drawn width, in microns. **THE ONE GEOMETRIC INPUT
#: THAT IS NOT IN A FILE IN THIS INSTALL** — the tree at C:\\Users\\DELL\\sky130A
#: carries `libs.tech/ngspice` and `libs.ref/sky130_fd_pr/spice` only, no tech
#: LEF and no magic techfile, so this comes from the SKY130 design rules and is
#: declared rather than measured. It is a DIVISOR in the per-micron figure
#: below: if the vpp structure's fingers are drawn wider than minimum, the real
#: capacitance per micron is LOWER than computed here and both range edges move
#: down. Conservative in the direction that matters.
MET_MIN_WIDTH_UM: float = 0.14

#: The PDK structure the per-micron figure is read out of.
VPP_MODEL: str = "sky130_fd_pr__cap_vpp_01p8x01p8_m1m2_noshield"


@dataclass(frozen=True)
class WireCap:
    """Capacitance per micron of a minimum-width lower-metal routing wire."""

    m1_ff_per_um: float
    m2_ff_per_um: float
    ctot_ff: float
    rat_m1: float
    rat_m2: float
    n_sq_m1: float
    n_sq_m2: float
    width_um: float

    @property
    def lo_ff_per_um(self) -> float:
        return min(self.m1_ff_per_um, self.m2_ff_per_um)

    @property
    def hi_ff_per_um(self) -> float:
        return max(self.m1_ff_per_um, self.m2_ff_per_um)


def vpp_wire_cap(width_um: float = MET_MIN_WIDTH_UM) -> WireCap:
    """Read metal capacitance per micron out of SKY130's own vpp cap model.

    `sky130_fd_pr__cap_vpp_01p8x01p8_m1m2_noshield` is an interdigitated m1/m2
    finger capacitor. Its subckt states everything needed:

        ctot_a = 7.833e-16          total capacitance of the structure
        rat_m1 = 0.387              share carried by the m1 fingers
        rat_m2 = 0.596              share carried by the m2 fingers
        rm11 ... r = {22*rm1}       the m1 run is 22 squares
        rm21 ... r = {28*rm2}       the m2 run is 28 squares

    so capacitance per micron of finger = rat * ctot_a / (n_squares * width).

    TWO REASONS THIS IS AN UPPER BOUND on a routing wire, both worth stating
    because they set which range edge it is honest to use it for:
      * a finger capacitor is deliberately dense — every finger has a neighbour
        at minimum spacing on BOTH sides, which routing normally does not;
      * `ctot_a` includes the m1-to-m2 coupling that makes it a capacitor at
        all, which for a routing wire would only exist against whatever
        happens to run above it.

    Nothing here is re-declared: every number is parsed out of the PDK file
    (CLAUDEwa.md §8 rule 9). Raises if the file's structure has changed rather
    than falling back to a remembered value.
    """
    path = model_file_for_corner("tt").parent / f"{VPP_MODEL}.model.spice"
    text = path.read_text(encoding="utf-8", errors="replace")

    def _one(pattern: str, what: str) -> float:
        m = re.search(pattern, text, re.M)
        if not m:
            raise ValueError(f"could not read {what} out of {path.name}")
        return float(m.group(1))

    ctot = _one(r"ctot_a\s*=\s*\{([0-9.eE+-]+)\s*\*", "ctot_a")
    rat_m1 = _one(r"^\+\s*rat_m1\s*=\s*([0-9.eE+-]+)", "rat_m1")
    rat_m2 = _one(r"^\+\s*rat_m2\s*=\s*([0-9.eE+-]+)", "rat_m2")
    n_m1 = _one(r"^rm11\s+\S+\s+\S+\s+r\s*=\s*\{([0-9.]+)\s*\*\s*rm1\}", "m1 squares")
    n_m2 = _one(r"^rm21\s+\S+\s+\S+\s+r\s*=\s*\{([0-9.]+)\s*\*\s*rm2\}", "m2 squares")

    ctot_ff = ctot * 1e15
    return WireCap(
        m1_ff_per_um=rat_m1 * ctot_ff / (n_m1 * width_um),
        m2_ff_per_um=rat_m2 * ctot_ff / (n_m2 * width_um),
        ctot_ff=ctot_ff, rat_m1=rat_m1, rat_m2=rat_m2,
        n_sq_m1=n_m1, n_sq_m2=n_m2, width_um=width_um,
    )


@dataclass(frozen=True)
class RoutingAllowance:
    """One edge's routing contribution, in fF, with its reasoning."""

    length_um: float
    c_ff_per_um: float
    why: str

    @property
    def c_ff(self) -> float:
        return self.length_um * self.c_ff_per_um


#: Wire LENGTHS. Not measured — there is no layout — so they are stated.
ROUTING_LENGTH_LO_UM: float = 20.0
ROUTING_LENGTH_HI_UM: float = 120.0

ROUTING_WHY_LO = (
    "20 um: the summer and slicer abutted to the CTLE, which is how a "
    "bandwidth-critical node is laid out when nothing forces otherwise. The "
    "CTLE's own passives set the floor — its degeneration capacitor is "
    "0.1-10 pF and its load resistors are 50-800 ohm, so the output node "
    "cannot be shorter than the height of that array."
)
ROUTING_WHY_HI = (
    "120 um: the following stages displaced by roughly a lane pitch, e.g. by "
    "a clock distribution or an offset-trim DAC sitting between them. Beyond "
    "this length a designer would buffer the node rather than drive it, so it "
    "is a ceiling on the plausible rather than on the possible."
)


def routing_allowances(wire: Optional[WireCap] = None
                       ) -> tuple[RoutingAllowance, RoutingAllowance]:
    """`(lo, hi)` routing allowances, in fF, from the PDK-derived wire cap."""
    w = wire if wire is not None else vpp_wire_cap()
    return (
        RoutingAllowance(ROUTING_LENGTH_LO_UM, w.lo_ff_per_um,
                         f"{ROUTING_WHY_LO} Capacitance per micron is the "
                         f"LOWER of the two metal layers read out of "
                         f"{VPP_MODEL} ({w.lo_ff_per_um:.4f} fF/um)."),
        RoutingAllowance(ROUTING_LENGTH_HI_UM, w.hi_ff_per_um,
                         f"{ROUTING_WHY_HI} Capacitance per micron is the "
                         f"HIGHER of the two metal layers read out of "
                         f"{VPP_MODEL} ({w.hi_ff_per_um:.4f} fF/um)."),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. THE SWEEP.
# ─────────────────────────────────────────────────────────────────────────────

#: S9's temperature axis.
TEMPS_C: tuple[float, ...] = (0.0, 27.0, 125.0)

#: The CTLE OUTPUT common mode, which is this stage's gate bias. Swept because
#: it is set by the CTLE's own sizing (v_out = VDD - 0.5*i_bias*rl) and moves
#: across the box, so the load is not a single number even for one layout.
#:
#: The floor is not 0.5 V (`s3_yield.MIN_V_OUT_DC`) but ~1.15 V: below that the
#: loading pair's source node goes negative and the stage is unbuildable for
#: exactly the reason session 9c found for the CTLE itself. A receiver whose
#: CTLE output sits lower needs AC coupling or a level shift between the two —
#: recorded as a finding, not solved here.
VCM_OUT_V: tuple[float, ...] = (1.2, 1.4, 1.6)


def _task(args: tuple) -> dict:
    """Module-level so ProcessPoolExecutor can pickle it."""
    stage_name, corner, temp_c, vcm = args
    stage = LOAD_STAGES[stage_name]
    pt = measure_gate_load(stage, corner=corner, temp_c=temp_c, vcm_out_v=vcm)
    return point_to_row(pt, stage_name)


def point_to_row(pt: GateLoadPoint, stage_name: str) -> dict:
    """One measurement as a flat, CSV-able record.

    Floats go through `repr` at write time, so the CSV is lossless and the
    whole derivation re-runs with no simulator (G49: an experiment's output is
    TRACKED if any deliverable quotes a number from it).
    """
    problems = sanity_check_load(pt)
    row = {
        "stage": stage_name,
        "corner": pt.corner,
        "temp_c": pt.temp_c,
        "vcm_out_v": pt.vcm_out_v,
        "ok": bool(pt.ok and not problems),
        "problems": "; ".join(problems),
        "fail_reason": pt.fail_reason or "",
        "c_in_ff": (pt.c_in_f * 1e15) if pt.c_in_f is not None else None,
        "c_in_lo_ff": (pt.c_in_lo_f * 1e15) if pt.c_in_lo_f is not None else None,
        "cgg_ff": (pt.cgg_f * 1e15) if pt.cgg_f is not None else None,
        "cgs_ff": (pt.cgs_f * 1e15) if pt.cgs_f is not None else None,
        "cgd_ff": (pt.cgd_f * 1e15) if pt.cgd_f is not None else None,
        "cgb_ff": (pt.cgb_f * 1e15) if pt.cgb_f is not None else None,
        "a_load": pt.a_load,
        "g_in_s": pt.g_in_s,
        "gm": pt.gm,
        "id_a": pt.id_a,
        "vgs": pt.vgs,
        "vds": pt.vds,
        "vdsat": pt.vdsat,
        "v_src_dc": pt.v_src_dc,
        "v_out_dc": pt.v_out_dc,
        "runtime_s": pt.runtime_s,
    }
    try:
        row["analytic_ff"] = analytic_load_ff(pt) if pt.ok else None
    except ValueError:
        row["analytic_ff"] = None
    return row


def run_sweep(workers: int = 8,
              stages: Optional[Sequence[str]] = None) -> list[dict]:
    """Measure every (stage, corner, temp, vcm) combination."""
    names = list(stages) if stages else list(LOAD_STAGES)
    tasks = [(s, c, t, v) for s in names for c in VALID_CORNERS
             for t in TEMPS_C for v in VCM_OUT_V]
    if workers <= 1:
        return [_task(t) for t in tasks]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(_task, tasks, chunksize=4))


# ─────────────────────────────────────────────────────────────────────────────
# 4. THE DERIVATION. Pure — it reads the table and nothing else, so the whole
#    thing is testable and re-runnable with no simulator.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ClRange:
    """The deliverable: `[cl_lo, cl_hi]` in farads, with per-edge provenance."""

    cl_lo_f: float
    cl_hi_f: float
    device_lo_ff: float
    device_hi_ff: float
    routing_lo_ff: float
    routing_hi_ff: float
    #: Which (corner, temp, vcm) produced each device edge — a range whose
    #: edges cannot be pointed at is not a derived range.
    lo_witness: dict
    hi_witness: dict
    n_rows_used: int
    n_rows_rejected: int

    @property
    def cl_mid_f(self) -> float:
        """GEOMETRIC mean. `cl` is a log-scaled bound in `PROPOSED_BOX` and
        f_p2 = 1/(2*pi*RL*CL) is log-linear in it, so the geometric centre is
        the midpoint in the coordinate the circuit responds to. It is a screen
        point, not a claim about the most likely load."""
        return math.sqrt(self.cl_lo_f * self.cl_hi_f)

    @property
    def ratio(self) -> float:
        return self.cl_hi_f / self.cl_lo_f

    @property
    def octaves(self) -> float:
        return math.log2(self.ratio)


def _usable(rows: Sequence[dict], stage: str) -> list[dict]:
    return [r for r in rows if r["stage"] == stage and r["ok"]
            and r.get("c_in_ff") is not None]


def derive_cl_range(rows: Sequence[dict],
                    routing: Optional[tuple[RoutingAllowance,
                                            RoutingAllowance]] = None,
                    edge_stages: Optional[dict] = None) -> ClRange:
    """`[cl_lo, cl_hi]` from the measured table.

    Each edge is the sum over the stages that hang on the node, taken at the
    (corner, temp, vcm) that MINIMISES (lo) or MAXIMISES (hi) that stage's
    load, plus the routing allowance for that edge. Taking the extreme per
    stage rather than per corner is deliberate: the two stages are different
    devices and nothing requires their extremes to coincide, so pairing them
    corner-by-corner would produce a narrower range than the physics supports.

    Rows that failed `sanity_check_load` are excluded and COUNTED — a load
    number derived from an unknown number of discarded measurements is not
    derived from anything.
    """
    lo_route, hi_route = routing if routing is not None else routing_allowances()
    edges = edge_stages if edge_stages is not None else EDGE_STAGES

    n_rejected = sum(1 for r in rows if not r["ok"])
    n_used = 0
    out: dict[str, tuple[float, dict]] = {}
    for edge, stage_names in edges.items():
        total = 0.0
        witness: dict = {}
        for s in stage_names:
            usable = _usable(rows, s)
            if not usable:
                raise ValueError(
                    f"no usable measurement for stage {s!r}: the range cannot "
                    f"be derived from a table that has none")
            pick = (min if edge == "lo" else max)(usable,
                                                  key=lambda r: r["c_in_ff"])
            total += float(pick["c_in_ff"])
            n_used += len(usable)
            witness[s] = {"c_in_ff": pick["c_in_ff"], "corner": pick["corner"],
                          "temp_c": pick["temp_c"],
                          "vcm_out_v": pick["vcm_out_v"]}
        out[edge] = (total, witness)

    dev_lo, w_lo = out["lo"]
    dev_hi, w_hi = out["hi"]
    return ClRange(
        cl_lo_f=(dev_lo + lo_route.c_ff) * 1e-15,
        cl_hi_f=(dev_hi + hi_route.c_ff) * 1e-15,
        device_lo_ff=dev_lo, device_hi_ff=dev_hi,
        routing_lo_ff=lo_route.c_ff, routing_hi_ff=hi_route.c_ff,
        lo_witness=w_lo, hi_witness=w_hi,
        n_rows_used=n_used, n_rows_rejected=n_rejected,
    )


_COMMITTED: Optional[ClRange] = None


def committed_cl_range() -> ClRange:
    """`[cl_lo, cl_hi]` as published, re-derived from the committed table.

    **THE ONE DEFINITION** of the load range (CLAUDEwa.md §8 rule 9). Anything
    that needs `cl_lo`/`cl_mid`/`cl_hi` — `s9_yield.py`, a future reward, a
    write-up script — calls this rather than repeating the numbers, so a value
    can never drift between the document and the code that produced it. It
    needs no simulator: `cl_range_data.csv` is tracked precisely so this works
    (G49).

    Cached, because the callers are inside experiment loops and the file does
    not change under a running process.
    """
    global _COMMITTED
    if _COMMITTED is None:
        _COMMITTED = derive_cl_range(read_csv())
    return _COMMITTED


def check_stage_gains(rows: Sequence[dict],
                      min_gain: float = MIN_STAGE_GAIN) -> list[str]:
    """Stages that attenuate somewhere in the corner set. Empty = all fine.

    Reported per stage at its WORST corner, because a stage that only clears
    unity at TT is a stage that stops working at SS/125 C — and the load it
    presents there would still have gone into `cl_hi`.
    """
    out: list[str] = []
    for name in LOAD_STAGES:
        u = [r for r in _usable(rows, name) if r.get("a_load") is not None]
        if not u:
            continue
        worst = min(u, key=lambda r: r["a_load"])
        if worst["a_load"] < min_gain:
            out.append(
                f"{name}: |A| = {worst['a_load']:.3f} at {worst['corner']}/"
                f"{worst['temp_c']:.0f}C/vcm {worst['vcm_out_v']:.1f} V, below "
                f"MIN_STAGE_GAIN {min_gain:.2f} — this stage attenuates and is "
                f"not a defensible sizing")
    return out


def fanout_scaled(rng: ClRange, n_extra_gates: float) -> float:
    """`cl_hi` if `n_extra_gates` more identical gates hang on the node.

    Reported, not folded into the bound. S2's topology statement names a CTLE,
    a slicer and a 1-tap DFE and says nothing about a CDR, but a real 5 Gbps
    receiver also samples edges: a half-rate front end puts two data slicers
    and two edge slicers on the node instead of one slicer. The device term
    then roughly doubles. Whether that belongs inside `cl_hi` is a topology
    decision (CLAUDEwa §8 rule 5), so it is quantified here and left to a human.
    """
    per_gate = rng.device_hi_ff / max(1, len(EDGE_STAGES["hi"]))
    return (rng.device_hi_ff + n_extra_gates * per_gate
            + rng.routing_hi_ff) * 1e-15


# ─────────────────────────────────────────────────────────────────────────────
# 5. Reporting + IO.
# ─────────────────────────────────────────────────────────────────────────────

_CSV_FIELDS = ("stage", "corner", "temp_c", "vcm_out_v", "ok", "problems",
               "fail_reason", "c_in_ff", "c_in_lo_ff", "cgg_ff", "cgs_ff",
               "cgd_ff", "cgb_ff", "analytic_ff", "a_load", "g_in_s", "gm",
               "id_a", "vgs", "vds", "vdsat", "v_src_dc", "v_out_dc",
               "runtime_s")


def write_csv(rows: Sequence[dict], path: Path = DATA_CSV) -> None:
    """Lossless `repr` floats — the same convention as
    `robust_geometry_data.csv`, for the same reason (G49)."""
    with path.open("w", newline="", encoding="ascii") as fh:
        w = csv.DictWriter(fh, fieldnames=_CSV_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else
                            (repr(r[k]) if isinstance(r.get(k), float)
                             else r.get(k)))
                        for k in _CSV_FIELDS})


def read_csv(path: Path = DATA_CSV) -> list[dict]:
    rows: list[dict] = []
    with path.open(newline="", encoding="ascii") as fh:
        for r in csv.DictReader(fh):
            row: dict = {}
            for k, v in r.items():
                if k in ("stage", "corner", "problems", "fail_reason"):
                    row[k] = v
                elif k == "ok":
                    row[k] = (v == "True")
                else:
                    row[k] = float(v) if v != "" else None
            rows.append(row)
    return rows


def stage_table(rows: Sequence[dict]) -> str:
    L = ["  --- measured gate load per stage, over 5 corners x 3 temps x "
         "3 output common modes ---",
         f"      {'stage':12} {'n':>3} {'min fF':>8} {'median':>8} "
         f"{'max fF':>8} {'spread':>7}   {'cgg fF':>8} {'c_in/cgg':>9}"]
    for name in LOAD_STAGES:
        u = _usable(rows, name)
        if not u:
            L.append(f"      {name:12}   0   (no usable measurement)")
            continue
        c = sorted(float(r["c_in_ff"]) for r in u)
        g = sorted(float(r["cgg_ff"]) for r in u)
        med = c[len(c) // 2]
        L.append(f"      {name:12} {len(c):3d} {c[0]:8.3f} {med:8.3f} "
                 f"{c[-1]:8.3f} {c[-1] / c[0]:6.2f}x   "
                 f"{g[len(g) // 2]:8.3f} {med / g[len(g) // 2]:8.2f}x")
    return "\n".join(L)


def axis_table(rows: Sequence[dict]) -> str:
    """How much each swept axis moves the load — the answer to 'which of these
    three axes actually matters?', which decides what the write-up leads on."""
    L = ["  --- what moves the load, per axis (max/min within the axis, "
         "median over stages) ---"]
    for axis, values in (("corner", VALID_CORNERS), ("temp_c", TEMPS_C),
                         ("vcm_out_v", VCM_OUT_V)):
        ratios = []
        for name in LOAD_STAGES:
            u = _usable(rows, name)
            per = {}
            for v in values:
                sel = [float(r["c_in_ff"]) for r in u if r[axis] == v]
                if sel:
                    per[v] = sum(sel) / len(sel)
            if len(per) > 1 and min(per.values()) > 0:
                ratios.append(max(per.values()) / min(per.values()))
        if ratios:
            ratios.sort()
            L.append(f"      {axis:12} {ratios[len(ratios) // 2]:6.3f}x "
                     f"(range over stages {ratios[0]:.3f}-{ratios[-1]:.3f}x)")
    return "\n".join(L)


def report(rows: Sequence[dict], rng: ClRange,
           wire: WireCap,
           routing: tuple[RoutingAllowance, RoutingAllowance]) -> str:
    lo_r, hi_r = routing
    gains = check_stage_gains(rows)
    L = ["=" * 78, "cl RANGE - what the CTLE output actually has to drive",
         "=" * 78, "",
         stage_table(rows), "",
         f"  stage gain gate (|A| >= {MIN_STAGE_GAIN:.2f} at every corner): "
         + ("PASS" if not gains else f"FAIL ({len(gains)} stage(s))"), "",
         axis_table(rows), "",
         "  --- routing allowance (PDK-derived per micron, stated length) ---",
         f"      {VPP_MODEL}",
         f"        ctot {wire.ctot_ff:.4f} fF, m1 {wire.rat_m1:.3f} over "
         f"{wire.n_sq_m1:.0f} sq, m2 {wire.rat_m2:.3f} over "
         f"{wire.n_sq_m2:.0f} sq, width {wire.width_um} um",
         f"        -> m1 {wire.m1_ff_per_um:.4f} fF/um, "
         f"m2 {wire.m2_ff_per_um:.4f} fF/um",
         f"      lo  {lo_r.length_um:6.1f} um x {lo_r.c_ff_per_um:.4f} "
         f"= {lo_r.c_ff:6.2f} fF",
         f"      hi  {hi_r.length_um:6.1f} um x {hi_r.c_ff_per_um:.4f} "
         f"= {hi_r.c_ff:6.2f} fF", "",
         "  --- THE RANGE ---",
         f"      cl_lo  = {rng.device_lo_ff:6.2f} fF device + "
         f"{rng.routing_lo_ff:5.2f} fF routing = "
         f"{rng.cl_lo_f * 1e15:7.2f} fF",
         f"      cl_mid = geometric mean                    "
         f"= {rng.cl_mid_f * 1e15:7.2f} fF",
         f"      cl_hi  = {rng.device_hi_ff:6.2f} fF device + "
         f"{rng.routing_hi_ff:5.2f} fF routing = "
         f"{rng.cl_hi_f * 1e15:7.2f} fF",
         f"      ratio  = {rng.ratio:.2f}x  ({rng.octaves:.2f} octaves)",
         f"      rows used {rng.n_rows_used}, rejected "
         f"{rng.n_rows_rejected}", ""]
    for edge, wit in (("lo", rng.lo_witness), ("hi", rng.hi_witness)):
        for stage, w in wit.items():
            L.append(f"      {edge} witness {stage:12} {w['c_in_ff']:7.3f} fF "
                     f"at {w['corner']}/{w['temp_c']:.0f}C/"
                     f"vcm {w['vcm_out_v']:.1f} V")
    L += ["",
          "  --- for comparison ---",
          f"      pinned in S9_YIELD.md so far          150.00 fF  "
          f"({150e-15 / rng.cl_hi_f:.2f}x the derived cl_hi)",
          f"      PROPOSED_BOX cl bound          10.00 - 500.00 fF",
          f"      half-rate fan-out (+2 gates) -> cl_hi "
          f"{fanout_scaled(rng, 2) * 1e15:.2f} fF (reported, NOT in the bound)",
          "=" * 78]
    return "\n".join(L)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--from-csv", action="store_true",
                    help="re-derive from the committed table; no simulator")
    ap.add_argument("--csv", type=Path, default=DATA_CSV)
    ap.add_argument("--out", type=Path, default=RESULTS_JSON)
    args = ap.parse_args(argv)

    if args.from_csv:
        rows = read_csv(args.csv)
        print(f"  re-derived from {args.csv} ({len(rows)} rows, no simulator)")
    else:
        t0 = time.perf_counter()
        rows = run_sweep(workers=args.workers)
        dt = time.perf_counter() - t0
        print(f"  {len(rows)} measurements in {dt:.1f} s "
              f"({dt / len(rows) * 1000:.0f} ms each, {args.workers} workers)")
        write_csv(rows, args.csv)
        print(f"  wrote {args.csv}")

    bad = [r for r in rows if not r["ok"]]
    if bad:
        print(f"  {len(bad)} of {len(rows)} measurements REJECTED:")
        for r in bad[:8]:
            print(f"      {r['stage']:12} {r['corner']}/{r['temp_c']}C/"
                  f"{r['vcm_out_v']}V: {r['problems'] or r['fail_reason']}")

    gain_problems = check_stage_gains(rows)
    if gain_problems:
        print("  *** STAGE GAIN GATE FAILED — a loading stage attenuates ***")
        for p in gain_problems:
            print(f"      {p}")

    wire = vpp_wire_cap()
    routing = routing_allowances(wire)
    rng = derive_cl_range(rows, routing)
    print()
    print(report(rows, rng, wire, routing))

    args.out.write_text(json.dumps({
        "cl_lo_f": rng.cl_lo_f, "cl_mid_f": rng.cl_mid_f,
        "cl_hi_f": rng.cl_hi_f, "range": asdict(rng),
        "wire": asdict(wire),
        "routing": {"lo": asdict(routing[0]), "hi": asdict(routing[1])},
        "stages": {k: asdict(v) for k, v in LOAD_STAGES.items()},
        "n_rows": len(rows),
    }, indent=1), encoding="ascii")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
