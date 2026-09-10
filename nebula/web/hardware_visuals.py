"""Render the calibrated receiver from pinned device and waveform evidence.

The schematic is a named-net sheet: equal net labels connect every device.
External stimulus, clocks and controls are identified as testbench apparatus.
No SPICE or new measurement is performed by this presentation renderer.
"""
from pathlib import Path
import hashlib
import json
import re

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "nebula/product_audits/entry143_dfe_calibrated_verification_20260910"
POINT = SOURCE / "link_state0_tol1e-05_step5ps"
OUTPUT = ROOT / "nebula/web/assets"
DECK_SHA = "c1b2598b57278cbc1101bf8600284bcf95f853cd612c36ceb1b809dade89bede"
TRACE_SHA = "c0607f6b2baff56a5316878dc768bc9fe22f534816e2cc1cd480e65e80ded943"


def pinned(path, expected):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("Hardware visual source SHA-256 mismatch")
    return raw


def devices():
    text = pinned(POINT / "design.cir", DECK_SHA).decode()
    rows = []
    for line in text.splitlines():
        f = line.split()
        if not f or not f[0].lower().startswith("x"):
            continue
        model_index = next((i for i, token in enumerate(f) if token.startswith("sky130_")), None)
        if model_index is None:
            raise ValueError("Unrepresented hardware device")
        model = f[model_index].removeprefix("sky130_fd_pr__")
        rows.append((f[0], f[1:model_index], model, " ".join(f[model_index+1:])))
    if len({r[0].lower() for r in rows}) != len(rows):
        raise ValueError("Duplicate device identity")
    return rows


def eye_data():
    from nebula.device import dfe_connected as F, dfe_timing as T
    from nebula.link.config import LinkConfig
    from nebula.common.types import UI_SECONDS
    pinned(POINT / "trace.txt.gz", TRACE_SHA)
    t, y = T.read_table(POINT / "trace.txt.gz", len(F.VECTORS)+6)
    bits = F.pattern(LinkConfig(channel_loss_db_at_nyquist=7.5))
    offsets = np.arange(-200, 201)*.005
    indices = np.arange(F.WARMUP, F.N_BITS)
    times = (indices[:, None]+3+offsets[None, :])*UI_SECONDS
    if times.min() < t[0] or times.max() > t[-1]:
        raise ValueError("Truncated eye trace")
    waves = np.interp(times, t, y[:, 3]-y[:, 4])
    aperture = T.aperture(t, y[:, 3]-y[:, 4], bits, 1.)
    return offsets, waves, aperture


def render_hardware_visuals(schematic=None, eye=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle, Circle
    schematic = Path(schematic or OUTPUT / "transistor_schematic.png")
    eye = Path(eye or OUTPUT / "nominal_eye.png")
    for path in (schematic, eye):
        path.parent.mkdir(parents=True, exist_ok=True)
    rows = devices()
    columns = 4
    nrows = (len(rows)+columns-1)//columns
    with plt.rc_context({"font.family": "DejaVu Sans", "text.color": "#102e4e",
                         "axes.labelcolor": "#102e4e", "font.size": 9}):
        fig, axes = plt.subplots(nrows, columns, figsize=(20, nrows*2.35))
        fig.subplots_adjust(top=.956, bottom=.022, left=.025, right=.975,
                            hspace=.28, wspace=.1)
        fig.text(.025, .985, "Nebula | Configurable CTLE + transistor 1-tap DFE",
                 fontsize=22, weight="bold", va="top")
        fig.text(.025, .970, "Named-net device schematic: matching labels connect. All drawn SKY130 devices are parsed from the calibrated deck.", fontsize=11)
        for ax in axes.flat:
            ax.set(xlim=(0, 10), ylim=(0, 5))
            ax.axis("off")
        for ax, (name, nets, model, params) in zip(axes.flat, rows):
            ax.text(.1, 4.7, name, fontsize=12, weight="bold")
            ax.text(.1, 4.25, model, fontsize=8, color="#537184")
            def wire(xs, ys):
                ax.plot(xs, ys, color="#102e4e", lw=1.2)
            if "fet" in model:
                if len(nets) != 4:
                    raise ValueError("MOS terminal count changed")
                wire([4.8,4.8,4.1], [3.9,3.2,3.2])
                wire([4.8,4.8,4.1], [1.2,1.9,1.9])
                wire([4.1,4.1], [1.75,3.35])
                wire([3.8,3.8], [1.9,3.2])
                wire([2.4,3.8], [2.55,2.55])
                ax.text(5.1,3.65,"D: "+nets[0],fontsize=9)
                ax.text(2.25,2.55,"G: "+nets[1],ha="right",va="center",fontsize=8)
                ax.text(5.1,1.35,"S: "+nets[2],fontsize=9)
                ax.text(5.1,2.55,"B: "+nets[3],fontsize=9)
                if model.startswith("pfet"):
                    ax.add_patch(Circle((3.6,2.55),.13,fc="white",ec="#102e4e"))
            else:
                wire([1.8,4.2],[2.6,2.6]); wire([5.8,8.2],[2.6,2.6])
                if "res_" in model:
                    ax.add_patch(Rectangle((4.2,2.25),1.6,.7,fc="white",ec="#102e4e",lw=1.2))
                else:
                    wire([4.7,4.7],[1.9,3.3]); wire([5.3,5.3],[1.9,3.3])
                    wire([4.2,4.7],[2.6,2.6]); wire([5.3,5.8],[2.6,2.6])
                    if "var_" in model:
                        ax.annotate("",xy=(5.8,3.4),xytext=(4.2,1.8),
                                    arrowprops={"arrowstyle":"->","color":"#008fb4"})
                ax.text(1.8,3.05,nets[0],ha="center")
                ax.text(8.2,3.05,nets[1],ha="center")
                if len(nets)>2: ax.text(5,1.25,"bulk: "+nets[2],ha="center")
            ax.text(.1,.3,params,fontsize=8)
        fig.text(.025,.011, "W/L in microns. {W}=57.9767, {L}=0.391149, {NF}=4; {WT}=201.656, {LT}=0.5, {NFT}=8; {WREF}=25.2069, {NFREF}=1.\nExternal apparatus: VDD, input/common-mode sources, clocks, tap and R/C controls; CLp/CLn=32.628 fF each. Deck SHA-256: "+DECK_SHA,fontsize=8)
        fig.savefig(schematic,dpi=150,facecolor="white",metadata={"Software":"Nebula hardware visuals"})
        plt.close(fig)
        offsets, waves, aperture = eye_data()
        fig, ax = plt.subplots(figsize=(10,5.8))
        fig.subplots_adjust(left=.10,right=.97,bottom=.17,top=.84)
        fig.text(.10,.95,"Eye at the transistor DFE summer",fontsize=18,weight="bold")
        fig.text(.10,.895,"TT / 1.8 V / 27 C   |   5 Gbps NRZ   |   64 scored bits",fontsize=10,color="#537184")
        for wave in waves:
            ax.plot(offsets,wave*1e3,color="#008aa5",alpha=.24,lw=.85)
        ax.axvspan(-.05,-.005,color="#dc9b35",alpha=.22,label="Scored sample window")
        ax.axhline(0,color="#8193a3",lw=.8)
        ax.set(xlim=(-1,1),ylim=(-370,370),xlabel="Time relative to clock edge (UI)",
               ylabel="v(sum_p) - v(sum_n) (mV)")
        ax.grid(alpha=.18)
        ax.spines[["top","right"]].set_visible(False)
        ax.legend(loc="upper right",frameon=False,fontsize=9)
        fig.text(.10,.045,"Frozen ngspice waveform, constructed 7.5 dB channel. Finite noiseless eye; not BER.\nPositive aperture: 0.705 UI (scan limited); aperture above 100 mV: 0.655 UI.",fontsize=9,color="#537184")
        fig.savefig(eye,dpi=180,facecolor="white",metadata={"Software":"Nebula hardware visuals"})
        plt.close(fig)
    manifest = {"deck_sha256":DECK_SHA,"trace_sha256":TRACE_SHA,
                "device_count":len(rows),"waveform_bits":len(waves),
                "eye_width_above_100mv_ui":aperture["eye_width_at_100mv_ui"],
                "artifacts":{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (schematic,eye)}}
    if schematic.parent == OUTPUT and eye.parent == OUTPUT:
        (OUTPUT/"visual_sources.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    return manifest


if __name__ == "__main__":
    print(json.dumps(render_hardware_visuals(),indent=2))
