"""
experiments/exp_tunable_trade.py — **S3 says the peaking is tunable. What the
tuning control actually trades is drive.**

THE REFRAMING, AND WHY IT IS BETTER THAN A BANK TABLE
------------------------------------------------------
S3 asks for peaking *"3-12 dB, tunable, via variable Rs and Cs"*. The obvious
deliverable is a table: settings down one axis, measured peaking across. That
is worth having and it is not the interesting thing.

Session 22r measured the interesting thing. A source-degenerated pair gets its
**linear input range** from `Rs` and its **peaking** from `Cs` shorting that
same `Rs` out at the signal band, so

    linear input range at f  =  linear input range at DC / |H(f)/H(0)|

**The two are one knob read in opposite directions.** So a peaking control is
also, unavoidably, a drive-handling control -- and the bank setting is the
Pareto front of session 22r *exposed to the user as a dial*. Turning up
equalisation turns down how hard the stage may be driven, and this file
measures both on the same axes with the **534.7 mVpp** the link actually
delivers drawn across them.

That reframes a checkbox ("tunable: yes, here are the settings") into the
sentence a designer needs: *above setting N this stage stops accepting PCIe
Gen2 drive.*

HOW THE BANK IS CONSTRUCTED
----------------------------
A real CTLE tuning bank does not move `Rs` alone. Peaking is `20 log10(k)` with
`k = 1 + (gm + gmbs) Rs / 2`, and the zero is `1 / (Rs Cs)` -- so raising `Rs`
for more peaking would drag the zero, and the peak with it, straight out of
S3's 1.25-2.5 GHz window. The settings here therefore hold **`Rs * Cs`
constant** at the delivered design's value and vary `Rs`, which is what a
switched bank with complementary R and C segments does: **peaking moves, the
zero does not.** Whether the peak stays in the window is then a measurement,
and it is reported per setting rather than assumed.

THE SWITCHES ARE MEASURED, NOT ASSUMED
---------------------------------------
Each segment is switched by an nfet in series, and its on-resistance adds to
`Rs` -- which matters most at the LOW-`Rs` settings, where it is the largest
fraction. `switch_on_resistance()` measures `Ron` for a stated `W/L` at
`Vgs = VDD` by a `.dc` sweep of a real SKY130 device rather than taking a
number from a datasheet, and every setting's `rs_total` is the intended segment
resistance **plus** that measured `Ron`.

**Stated limitation:** the switches are modelled as that measured series
resistance, not drawn as devices in the CTLE netlist, so their parasitic
capacitance and their own non-linearity are not in these numbers. That is a
real gap and it is in the report rather than in a footnote here.

    python -m nebula.experiments.exp_tunable_trade --run
    python -m nebula.experiments.exp_tunable_trade --analyse
"""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "tunable_trade_results.json"

#: How many bank settings. Eight is a 3-bit control, which is what a real part
#: exposes, and it is enough to resolve the crossing rather than bracket it.
N_SETTINGS: int = 8

#: The `Rs` span, ohms, BEFORE the switch on-resistance is added. The floor and
#: ceiling are `contract.ACTION_SPACE`'s own `rs` bounds, whose provenance is
#: `s3_yield.PROPOSED_BOX`: "Rs=50 gives 0.08 dB peaking, Rs=800 gives
#: 13.25 dB, through S3's ceiling". Nothing here is a new choice.
RS_LO_OHM: float = 120.0
RS_HI_OHM: float = 900.0

#: The switch device. `W/L` is chosen so `Ron` is small against `RS_LO_OHM`
#: rather than to hit a target; the measurement reports what it actually is and
#: the ratio is in the results.
SWITCH_W_UM: float = 40.0
SWITCH_L_UM: float = 0.15


@dataclass
class Setting:
    """One bank code and everything measured at it."""

    code: int
    rs_segment_ohm: float
    rs_switch_ohm: float
    rs_total_ohm: float
    cs_f: float
    ok: bool
    reason: Optional[str] = None
    peaking_db: Optional[float] = None
    f_peak_hz: Optional[float] = None
    f_zero_hz: Optional[float] = None
    nyq_boost_db: Optional[float] = None
    g_dc_db: Optional[float] = None
    #: 1 dB gain compression referred to the INPUT, at DC and de-rated to the
    #: signal band. The second is the one the drive line is compared against.
    linear_in_dc_pp_v: Optional[float] = None
    linear_in_nyq_pp_v: Optional[float] = None
    hd3_nyq_dbc: Optional[float] = None
    power_w: Optional[float] = None
    in_s3_window: bool = False
    accepts_drive: bool = False


def switch_on_resistance(w_um: float = SWITCH_W_UM, l_um: float = SWITCH_L_UM,
                         vdd: float = 1.8) -> dict:
    """Measure `Ron` of one nfet_01v8 at `Vgs = vdd`, by `.dc`.

    **Measured, not quoted.** A switched bank's on-resistance sits in series
    with the degeneration it is switching, so it is part of `Rs` and it is
    largest, proportionally, exactly where `Rs` is smallest. Taking it from a
    process datasheet would be the kind of number `CLAUDEwa.md` rule 1 forbids
    in a deliverable.

    `Ron` is read as `dV/dI` at small `Vds` -- the linear-region slope -- not
    as `Vds/Id` at one point, because the latter is a chord and over-states the
    resistance the signal sees.
    """
    import shutil
    import subprocess
    import tempfile

    from nebula.device.ngspice_runner import ngspice_path
    from nebula.device.sky130_runner import SPICE_DIR, TRIMMED_LIB

    deck = f"""* switch Ron measurement -- GENERATED by exp_tunable_trade.py
.lib "{TRIMMED_LIB.name}" tt
.temp 27
Vg g 0 {vdd}
Vd d 0 0
XM1 d g 0 0 sky130_fd_pr__nfet_01v8 W={w_um} L={l_um} nf=1
.control
set filetype=ascii
dc Vd 0 0.05 0.001
wrdata ron.txt i(Vd)
quit
.endc
.end
"""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        # `.spiceinit` is read from the CURRENT DIRECTORY at parse time (G29),
        # and the library is referenced by name, so both travel to the temp
        # directory rather than the deck travelling to `SPICE_DIR` -- which
        # keeps this parallel-safe and stops `wrdata` littering the tree.
        shutil.copy(SPICE_DIR / ".spiceinit", d / ".spiceinit")
        shutil.copy(TRIMMED_LIB, d / TRIMMED_LIB.name)
        (d / "deck.cir").write_text(deck, encoding="ascii")
        r = subprocess.run([str(ngspice_path()), "-b", "deck.cir"],
                           cwd=str(d), capture_output=True, text=True,
                           timeout=120)
        out = d / "ron.txt"
        if not out.exists():
            # G26/G30: ngspice reports many failures as warnings and exits 0,
            # so the missing artifact is the only reliable signal.
            raise RuntimeError(f"ron.txt not written; ngspice said: "
                               f"{r.stdout[-600:]} {r.stderr[-300:]}")
        raw = np.loadtxt(out)
    vd, i = raw[:, 0], -raw[:, 1]        # i(Vd) is into the source, so negate
    ok = (vd > 0.005) & (vd < 0.045)
    slope = np.polyfit(i[ok], vd[ok], 1)[0]
    return {"w_um": w_um, "l_um": l_um, "vgs_v": vdd,
            "ron_ohm": float(slope),
            "basis": "dV/dI slope over 5-45 mV of Vds on a real SKY130 "
                     "nfet_01v8, measured not quoted"}


def bank_settings(rs_cs_product: float, ron_ohm: float,
                  n: int = N_SETTINGS) -> list[tuple]:
    """`n` (rs_segment, rs_total, cs) triples with `Rs * Cs` held constant.

    **`Rs * Cs` is held on the TOTAL resistance, switch included**, because the
    zero is set by what the signal sees, not by the segment value a designer
    typed. Getting that wrong would move the zero by the switch fraction --
    largest at the low-peaking end, i.e. exactly where the bank is supposed to
    be most benign.
    """
    out = []
    for k, rs_seg in enumerate(np.geomspace(RS_LO_OHM, RS_HI_OHM, n)):
        rs_total = float(rs_seg) + float(ron_ohm)
        out.append((float(rs_seg), rs_total, rs_cs_product / rs_total))
    return out


def base_design(which: str) -> tuple:
    """`(design_id, u)` for the fixed part the bank is built around.

    **Which design the bank sits on decides whether the trade is visible at
    all, and that is itself the finding.** On the DELIVERED design the bank
    spans 4.5-14.3 dB of peaking and its linear range at Nyquist stays
    130-201 mVpp -- always ~4x below the 535 mVpp drive, so the drive line
    never crosses and the control has no usable range. On the joint-search
    winner, whose fixed part was chosen with the eye in the objective, the
    range straddles the drive and the crossing is where the control stops
    being usable. Both are reported.
    """
    if which == "delivered":
        from nebula.experiments.exp_g4_verify import candidates

        c = [x for x in candidates(n_control=0) if x.role == "robust"][0]
        return c.design_id, tuple(c.u)
    if which == "joint":
        d = json.loads((HERE / "joint_search_results.json").read_text(
            encoding="utf-8"))
        return "joint_v4_winner", tuple(d["best"]["u"])
    raise ValueError(f"unknown base {which!r}; use 'delivered' or 'joint'")


def run(n: int = N_SETTINGS, which_base: str = "joint") -> dict:
    from nebula.device.sky130_runner import run_point, swing_limits
    from nebula.experiments.cl_range import committed_cl_range
    from nebula.experiments.exp_g2_closed_loop import FUNNEL_LOSS_DB
    from nebula.link.config import LinkConfig
    from nebula.rl.contract import ACTION_SPACE, Sizing, sizing_from_u
    from nebula.rl.evaluator import build_point
    from nebula.common.types import SPEC_F_PEAK_HZ_RANGE, SPEC_PEAKING_DB_RANGE

    t0 = time.time()
    sw = switch_on_resistance()
    cfg = LinkConfig(channel_loss_db_at_nyquist=FUNNEL_LOSS_DB)
    drive = float(cfg.v_in_diff_pp_v)

    base_id, base_u = base_design(which_base)
    base = sizing_from_u(np.asarray(base_u),
                         cl_f=committed_cl_range().cl_mid_f)
    rs0 = float(base.params["rs"])
    cs0 = float(base.params["cs"])
    product = rs0 * cs0

    rows: list[Setting] = []
    for code, (rs_seg, rs_tot, cs) in enumerate(
            bank_settings(product, sw["ron_ohm"], n)):
        params = dict(base.params)
        params["rs"] = rs_tot
        params["cs"] = cs
        # **`u` is re-derived, not carried over.** `Sizing` holds both a
        # normalised coordinate and the physical parameters, and handing it the
        # base design's `u` beside edited `params` would make the two disagree
        # -- a `Sizing` whose own two representations describe different
        # circuits. Nothing downstream here reads `u`, which is exactly why it
        # would have gone unnoticed. `ActionDim.to_normalised` is the inverse
        # the box already owns (rule 9).
        u = list(base.u)
        for dim_i, dim in enumerate(ACTION_SPACE):
            if dim.name in ("rs", "cs"):
                u[dim_i] = dim.to_normalised(params[dim.name])
        try:
            point, _ = build_point(Sizing(u=tuple(u), params=params),
                                   corner="tt", vdd_scale=1.0)
        except Exception as exc:                                # noqa: BLE001
            rows.append(Setting(code, rs_seg, sw["ron_ohm"], rs_tot, cs,
                                ok=False, reason=f"unrealisable: {exc}"))
            continue
        pt = run_point(point, "tt", temp_c=27.0, swing=True, ac_sweep=True,
                       hd3=True, hd3_vin_pk_v=0.5 * drive,
                       hd3_tone_hz=cfg.nyquist_hz)
        if not pt.ok or pt.vid is None:
            rows.append(Setting(code, rs_seg, sw["ron_ohm"], rs_tot, cs,
                                ok=False, reason=pt.fail_reason or "no .dc"))
            continue
        lim = swing_limits(pt.vid, pt.vod, pt.sat_ok, pt.id_min,
                           i_ref_a=pt.point.i_tail_per_side_a)
        boost = float(pt.nyquist_boost_db)
        lower = lim.linear_in_pp_v is None
        lin_dc = lim.max_swept_in_pp_v if lower else float(lim.linear_in_pp_v)
        lin_ny = lin_dc / (10.0 ** (boost / 20.0))
        pk_lo, pk_hi = SPEC_PEAKING_DB_RANGE
        f_lo, f_hi = SPEC_F_PEAK_HZ_RANGE
        in_s3 = bool(pt.has_interior_peak and pt.f_pk_hz
                     and pk_lo <= pt.peaking_db <= pk_hi
                     and f_lo <= pt.f_pk_hz <= f_hi and boost > 0.0)
        rows.append(Setting(
            code, rs_seg, sw["ron_ohm"], rs_tot, cs, ok=True,
            peaking_db=float(pt.peaking_db),
            f_peak_hz=float(pt.f_pk_hz) if pt.f_pk_hz else None,
            f_zero_hz=1.0 / (2.0 * math.pi * rs_tot * cs),
            nyq_boost_db=boost, g_dc_db=float(pt.g_dc_db),
            linear_in_dc_pp_v=lin_dc, linear_in_nyq_pp_v=lin_ny,
            hd3_nyq_dbc=pt.hd3_dbc, power_w=pt.power_measured_w,
            in_s3_window=in_s3, accepts_drive=bool(lin_ny >= drive)))

    ok = [r for r in rows if r.ok]
    span = [r.peaking_db for r in ok if r.peaking_db is not None]
    crossing = None
    for a, b in zip(ok, ok[1:]):
        if (a.linear_in_nyq_pp_v and b.linear_in_nyq_pp_v
                and a.linear_in_nyq_pp_v >= drive > b.linear_in_nyq_pp_v):
            crossing = {"between_codes": [a.code, b.code],
                        "peaking_db": [a.peaking_db, b.peaking_db],
                        "linear_in_nyq_pp_v": [a.linear_in_nyq_pp_v,
                                               b.linear_in_nyq_pp_v]}
            break

    out = {
        "n_settings": len(rows), "n_ok": len(ok),
        "switch": sw,
        "switch_fraction_at_lowest_rs": sw["ron_ohm"] / (RS_LO_OHM + sw["ron_ohm"]),
        "base": which_base,
        "base_design_id": base_id,
        "rs_cs_product_held_at": product,
        "base_rs_ohm": rs0, "base_cs_f": cs0,
        "drive_pp_v": drive,
        "peaking_span_db": [min(span), max(span)] if span else None,
        "n_in_s3_window": sum(1 for r in ok if r.in_s3_window),
        "n_accepting_drive": sum(1 for r in ok if r.accepts_drive),
        "drive_crossing": crossing,
        "settings": [asdict(r) for r in rows],
        "wall_clock_s": time.time() - t0,
        "limitation": (
            "Switches enter as a MEASURED series on-resistance, not as drawn "
            "devices in the CTLE netlist, so their parasitic capacitance and "
            "their own non-linearity are not in these numbers."),
    }
    RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def _report(d: dict) -> None:
    sw = d["switch"]
    print(f"switch: W={sw['w_um']:g}/L={sw['l_um']:g} um at Vgs={sw['vgs_v']} V "
          f"-> Ron = {sw['ron_ohm']:.2f} ohm "
          f"({100 * d['switch_fraction_at_lowest_rs']:.1f} % of the lowest "
          f"setting)")
    print(f"base: {d['base']} ({d['base_design_id']})")
    print(f"Rs*Cs held at {d['rs_cs_product_held_at']:.4g}, "
          f"drive = {1e3 * d['drive_pp_v']:.1f} mVpp\n")
    print("  code  Rs_tot   Cs      peaking   f_peak   f_zero   lin@Nyq  "
          "vs drive  HD3@Nyq  S3?")
    for r in d["settings"]:
        if not r["ok"]:
            print(f"  {r['code']:4d}  FAILED: {r['reason']}")
            continue
        print(f"  {r['code']:4d} {r['rs_total_ohm']:7.1f} "
              f"{r['cs_f'] * 1e12:6.3f}p {r['peaking_db']:8.2f} dB "
              f"{(r['f_peak_hz'] or 0) / 1e9:7.3f}G "
              f"{r['f_zero_hz'] / 1e6:7.1f}M "
              f"{1e3 * r['linear_in_nyq_pp_v']:8.0f} "
              f"{r['linear_in_nyq_pp_v'] / d['drive_pp_v']:8.2f}x "
              f"{r['hd3_nyq_dbc']:8.1f} "
              f"{'yes' if r['in_s3_window'] else 'no'}")
    print(f"\n  peaking span {d['peaking_span_db'][0]:.2f} - "
          f"{d['peaking_span_db'][1]:.2f} dB over {d['n_ok']} settings")
    print(f"  settings inside S3's window: {d['n_in_s3_window']} of {d['n_ok']}")
    print(f"  settings accepting the drive: {d['n_accepting_drive']} of {d['n_ok']}")
    c = d["drive_crossing"]
    if c:
        print(f"  **the stage stops accepting PCIe Gen2 drive between codes "
              f"{c['between_codes'][0]} and {c['between_codes'][1]}, i.e. "
              f"between {c['peaking_db'][0]:.2f} and {c['peaking_db'][1]:.2f} dB "
              f"of peaking**")
    else:
        print("  no crossing inside the bank's range")
    print(f"\n  limitation: {d['limitation']}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--analyse", action="store_true")
    ap.add_argument("--n", type=int, default=N_SETTINGS)
    ap.add_argument("--base", choices=("joint", "delivered"), default="joint",
                    help="whose fixed part the bank sits on")
    a = ap.parse_args(argv)
    if a.analyse:
        _report(json.loads(RESULTS.read_text(encoding="utf-8")))
        return 0
    if not a.run:
        ap.print_help()
        return 2
    _report(run(a.n, a.base))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
