"""Draw the RL adaptation evidence carried by one delivered design run.

The dashboard does not load an experiment artifact, rerun a policy or infer a
missing value.  It accepts the dictionary that ``nebula.design`` is already
writing and refuses an incomplete or duplicated condition matrix.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.patches import Patch

from nebula.experiments import exp_joint_bank as J


INK = "#1a1a1a"
GREY = "#777777"
LIGHT = "#d8d8d8"
RL_BLUE = "#0072B2"
FALLBACK_ORANGE = "#D55E00"
MISS_GREY = "#8a8a8a"

SOURCE_VALUE = {"rl-shield": 0, "bank-fallback": 1, "bank-miss": 2}
SOURCE_LABEL = {
    "rl-shield": "R", "bank-fallback": "B", "bank-miss": "X"}


def _validate_trace(row: dict) -> None:
    trace = row.get("policy_trace")
    if not isinstance(trace, dict):
        raise ValueError("every condition needs its actual policy_trace")
    tried = trace.get("settings_tried") or []
    measured = trace.get("measurements") or []
    actions = trace.get("actions") or []
    if not tried or len(tried) != len(measured):
        raise ValueError("policy trace settings and measurements do not align")
    if len(tried) > 8:
        raise ValueError("policy trace exceeds the frozen eight-measurement cap")
    if len(actions) not in (len(tried) - 1, len(tried)):
        raise ValueError("policy trace actions do not align with its settings")
    for measurement in measured:
        if not {"link_valid", "eye_h_v", "eye_w_ui"} <= set(measurement):
            raise ValueError("policy trace measurement is incomplete")


def dashboard_model(design: dict) -> dict:
    """Validate and arrange the delivered loss-by-PVT records for plotting."""
    if design.get("method") != "rl-hybrid":
        raise ValueError("the RL dashboard requires an rl-hybrid design")
    verification = design.get("verification") or {}
    rows = verification.get("per_condition") or []
    if not rows:
        raise ValueError("the delivered design carries no condition matrix")

    losses = tuple(float(value) for value in (
        verification.get("channel_losses_db") or
        dict.fromkeys(float(row["channel_loss_db"]) for row in rows)))
    corners = tuple(dict.fromkeys(str(row["corner"]) for row in rows))
    expected_shape = (
        int(verification.get("n_channel_losses", len(losses))),
        int(verification.get("n_corners", len(corners))),
    )
    if expected_shape != (len(losses), len(corners)):
        raise ValueError("declared loss/PVT matrix dimensions disagree")

    by_condition = {}
    for row in rows:
        key = (float(row["channel_loss_db"]), str(row["corner"]))
        if key in by_condition:
            raise ValueError(f"duplicate condition in dashboard matrix: {key}")
        if row.get("source") not in SOURCE_VALUE:
            raise ValueError(f"unknown selection source {row.get('source')!r}")
        _validate_trace(row)
        by_condition[key] = row

    expected = {(loss, corner) for loss in losses for corner in corners}
    if set(by_condition) != expected:
        missing = len(expected - set(by_condition))
        extra = len(set(by_condition) - expected)
        raise ValueError(
            f"incomplete condition matrix: {missing} missing, {extra} extra")
    if len(rows) != expected_shape[0] * expected_shape[1]:
        raise ValueError(
            f"condition matrix has {len(rows)} rows, expected "
            f"{expected_shape[0] * expected_shape[1]}")

    matrix = np.asarray([
        [SOURCE_VALUE[by_condition[(loss, corner)]["source"]]
         for corner in corners]
        for loss in losses
    ], dtype=int)
    trace = max(rows, key=lambda row: (
        len(row["policy_trace"]["settings_tried"]),
        row["source"] == "bank-fallback",
        float(row["channel_loss_db"]), str(row["corner"])))
    return {
        "shape": expected_shape,
        "n_conditions": len(rows),
        "losses": losses,
        "corners": corners,
        "matrix": matrix,
        "n_rl_shield": sum(row["source"] == "rl-shield" for row in rows),
        "n_bank_fallback": sum(
            row["source"] == "bank-fallback" for row in rows),
        "n_bank_miss": sum(row["source"] == "bank-miss" for row in rows),
        "mean_measurements": float(np.mean([
            len(row["policy_trace"]["settings_tried"]) for row in rows])),
        "max_measurements": max(
            len(row["policy_trace"]["settings_tried"]) for row in rows),
        "trace": trace,
    }


def _code(setting: int) -> str:
    atten, bank = J.split_setting(int(setting))
    rs, cs = divmod(bank, 8)
    return f"A{atten}/R{rs}/C{cs}"


def _corner_label(corner: str) -> str:
    process, vdd, temp = corner.split("/")
    return f"{process}\n{vdd}\n{temp.replace('C', '')}"


def draw_rl_dashboard(design: dict, out_path) -> Path:
    """Write a judge-facing PNG from the exact delivered condition records."""
    model = dashboard_model(design)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    plt.rcParams.update({
        "font.size": 9, "text.color": INK, "axes.labelcolor": INK,
        "xtick.color": GREY, "ytick.color": GREY,
    })
    fig = plt.figure(figsize=(14.2, 8.4), dpi=180, facecolor="white")
    grid = fig.add_gridspec(2, 1, height_ratios=(1.55, 1.0), hspace=0.56,
                            top=0.79, bottom=0.09, left=0.065, right=0.985)
    request = design.get("request") or {}
    fig.suptitle("Nebula RL adaptation dashboard", x=0.065, y=0.965,
                 ha="left", fontsize=17, fontweight="bold", color=INK)
    fig.text(
        0.065, 0.915,
        f"Request  {float(request.get('peaking_db', 0.0)):.1f} dB @ "
        f"{float(request.get('f_peak_hz', 0.0)) / 1e9:.3f} GHz   |   "
        f"frozen policy seed {(design.get('search') or {}).get('policy_seed')}   |   "
        f"{model['n_conditions'] - model['n_bank_miss']} / "
        f"{model['n_conditions']} verified",
        ha="left", va="center", fontsize=11, color=INK)
    fig.text(
        0.065, 0.872,
        f"RL shield selected {model['n_rl_shield']} conditions   |   "
        f"measured-bank fallback selected {model['n_bank_fallback']}   |   "
        f"mean {model['mean_measurements']:.2f}, max "
        f"{model['max_measurements']} eye measurements per condition",
        ha="left", va="center", fontsize=9.5, color=GREY)

    ax = fig.add_subplot(grid[0])
    cmap = ListedColormap([RL_BLUE, FALLBACK_ORANGE, MISS_GREY])
    norm = BoundaryNorm([-0.5, 0.5, 1.5, 2.5], cmap.N)
    ax.imshow(model["matrix"], aspect="auto", cmap=cmap, norm=norm,
              interpolation="nearest")
    ax.set_yticks(range(len(model["losses"])))
    ax.set_yticklabels([f"{loss:g}" for loss in model["losses"]])
    ax.set_ylabel("channel loss at 2.5 GHz (dB)")
    ax.set_xticks(range(len(model["corners"])))
    ax.set_xticklabels([_corner_label(corner) for corner in model["corners"]],
                       fontsize=6.2)
    ax.set_xlabel("45 PVT conditions: process / VDD scale / temperature (C)")
    ax.tick_params(length=0)
    for x in range(9, len(model["corners"]), 9):
        ax.axvline(x - 0.5, color="white", linewidth=1.8)
    for y in range(1, len(model["losses"])):
        ax.axhline(y - 0.5, color="white", linewidth=0.45, alpha=0.8)
    for i, loss in enumerate(model["losses"]):
        for j, corner in enumerate(model["corners"]):
            source = next(name for name, value in SOURCE_VALUE.items()
                          if value == int(model["matrix"][i, j]))
            ax.text(j, i, SOURCE_LABEL[source], ha="center", va="center",
                    color="white", fontsize=5.2, fontweight="bold")
    ax.set_title("Who supplied each verified tuning code", loc="left",
                 fontsize=11, pad=9)
    ax.legend(handles=[
        Patch(facecolor=RL_BLUE, label="R  RL proposal accepted by shield"),
        Patch(facecolor=FALLBACK_ORANGE,
              label="B  classical measured-bank fallback"),
        Patch(facecolor=MISS_GREY, label="X  no compliant bank code"),
    ], frameon=False, ncol=3, loc="upper left", bbox_to_anchor=(0, -0.30),
              fontsize=8)

    trace_row = model["trace"]
    trace = trace_row["policy_trace"]
    measured = trace["measurements"]
    x = np.arange(1, len(measured) + 1)
    areas = np.asarray([
        float(item["eye_h_v"]) * 1e3 * float(item["eye_w_ui"])
        if item["link_valid"] else 0.0 for item in measured])
    ax2 = fig.add_subplot(grid[1])
    ax2.plot(x, areas, color=RL_BLUE, marker="o", linewidth=2.0,
             markersize=6)
    for step, area, setting in zip(x, areas, trace["settings_tried"]):
        ax2.annotate(_code(setting), (step, area), xytext=(0, 9),
                     textcoords="offset points", ha="center", fontsize=7,
                     color=INK)
    selected = int(trace_row["setting"])
    tried = [int(value) for value in trace["settings_tried"]]
    if selected in tried:
        selected_x = tried.index(selected) + 1
        ax2.scatter([selected_x], [areas[selected_x - 1]], marker="*", s=170,
                    color=FALLBACK_ORANGE, edgecolor="white", linewidth=0.8,
                    zorder=5, label="delivered code")
    else:
        selected_x = len(x) + 1
        selected_area = float(trace_row["eye_area"]) * 1e3
        ax2.plot([x[-1], selected_x], [areas[-1], selected_area],
                 color=FALLBACK_ORANGE, linestyle="--", linewidth=1.4)
        ax2.scatter([selected_x], [selected_area], marker="*", s=170,
                    color=FALLBACK_ORANGE, edgecolor="white", linewidth=0.8,
                    zorder=5, label="bank fallback delivered")
        ax2.annotate(_code(selected), (selected_x, selected_area),
                     xytext=(0, 9), textcoords="offset points", ha="center",
                     fontsize=7, color=INK)
    ax2.set_xlim(0.65, selected_x + 0.45)
    ax2.set_xticks(range(1, selected_x + 1))
    ax2.set_xlabel("measurement step")
    ax2.set_ylabel("observed eye area (mV x UI)")
    ax2.grid(axis="y", color=LIGHT, linewidth=0.7)
    ax2.spines[["top", "right"]].set_visible(False)
    ax2.set_title(
        f"Longest policy trace: {trace_row['channel_loss_db']:g} dB, "
        f"{trace_row['corner']}   ({trace_row['source']})",
        loc="left", fontsize=11, pad=9)
    ax2.legend(frameon=False, loc="best", fontsize=8)
    actions = "  ->  ".join(trace["actions"]) or "no move"
    fig.text(0.065, 0.025, f"Actor actions: {actions}.  "
             "The actor saw only request, code and measured eye history; "
             "the simulator-backed shield made the final safety decision.",
             ha="left", va="bottom", fontsize=8, color=GREY)

    fig.savefig(out, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    return out


__all__ = ("dashboard_model", "draw_rl_dashboard")
