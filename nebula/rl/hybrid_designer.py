"""Production inference for the frozen Entry-89 RL policy.

The actor is only a proposer.  For each characterised channel-loss/PVT
condition it sees the same 62 values it saw during training (request, current
code and measured eye history), and proposes at most eight settings.  A
simulator-backed shield then checks the proposed settings against the immutable
ngspice bank.  When no proposal is compliant, a deterministic exhaustive
lookup over that same 512-setting bank supplies the classical fallback.

This module deliberately contains no training environment and no FINAL-test
loader.  Production inference must not obtain compliance, quality, PVT or an
oracle through the actor observation.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence

import numpy as np

from nebula.common.types import (
    SPEC_AREA_MAX_MM2, SPEC_F_PEAK_HZ_RANGE, SPEC_HD3_MAX_DBC,
    SPEC_PEAKING_DB_RANGE,
)
from nebula.experiments import exp_joint_bank as J
from nebula.rl.contract import design_id, sizing_from_u
from nebula.rl.margin_adapt_env import (
    A_ATTEN_DOWN, A_ATTEN_UP, A_CS_DOWN, A_CS_UP, A_LOCK, A_RS_DOWN,
    A_RS_UP, HISTORY_FIELDS, MAX_TRIALS, N_ACTIONS, N_OBS, MarginBankTable,
)
from nebula.rl.masked_discrete_ppo import deterministic_action


@dataclass(frozen=True)
class PolicyTrace:
    start_setting: int
    locked_setting: int
    settings_tried: tuple[int, ...]
    measurements: tuple[tuple[bool, float, float], ...]
    actions: tuple[int, ...]


@dataclass(frozen=True)
class HybridSelection:
    setting: int
    compliant: bool
    source: str
    eye_area: float
    verifier_calls: int
    bank_rows_checked: int


ACTION_NAMES = {
    A_ATTEN_DOWN: "atten_down",
    A_ATTEN_UP: "atten_up",
    A_RS_DOWN: "rs_down",
    A_RS_UP: "rs_up",
    A_CS_DOWN: "cs_down",
    A_CS_UP: "cs_up",
    A_LOCK: "lock",
}


def policy_trace_record(trace: PolicyTrace) -> dict:
    """JSON-safe, human-readable copy of the actor's actual eye trace."""
    try:
        actions = [ACTION_NAMES[int(action)] for action in trace.actions]
    except KeyError as exc:
        raise ValueError(f"unknown policy action {exc.args[0]}") from exc
    return {
        "start_setting": int(trace.start_setting),
        "locked_setting": int(trace.locked_setting),
        "settings_tried": [int(setting) for setting in trace.settings_tried],
        "measurements": [
            {"link_valid": bool(ok), "eye_h_v": float(eye_h),
             "eye_w_ui": float(eye_w)}
            for ok, eye_h, eye_w in trace.measurements
        ],
        "actions": actions,
    }


def build_observation(
        request: tuple[float, float], current_setting: int,
        settings_tried: Sequence[int],
        measurements: Sequence[tuple[bool, float, float]],
        max_trials: int = MAX_TRIALS) -> np.ndarray:
    """Build the frozen actor's exact 62-field observation, without reward."""
    if len(settings_tried) != len(measurements):
        raise ValueError("every tried setting needs exactly one measurement")
    if not 1 <= len(settings_tried) <= int(max_trials) <= MAX_TRIALS:
        raise ValueError(f"measurement history must contain 1..{MAX_TRIALS} rows")
    peaking, frequency = map(float, request)
    pk_lo, pk_hi = SPEC_PEAKING_DB_RANGE
    f_lo, f_hi = SPEC_F_PEAK_HZ_RANGE
    out = np.zeros(N_OBS, dtype=np.float32)
    out[0] = (peaking - pk_lo) / (pk_hi - pk_lo)
    out[1] = math.log2(frequency / f_lo) / math.log2(f_hi / f_lo)
    out[2] = len(settings_tried) / int(max_trials)
    atten, bank_code = J.split_setting(current_setting)
    rs_code, cs_code = divmod(bank_code, 8)
    out[3:6] = (atten / 7.0, rs_code / 7.0, cs_code / 7.0)
    for slot, (setting, measurement) in enumerate(
            zip(settings_tried, measurements)):
        i = 6 + slot * HISTORY_FIELDS
        a_code, passive_code = J.split_setting(setting)
        r_code, c_code = divmod(passive_code, 8)
        ok, eye_h, eye_w = measurement
        out[i:i + HISTORY_FIELDS] = (
            1.0, a_code / 7.0, r_code / 7.0, c_code / 7.0,
            float(ok), float(eye_h), float(eye_w))
    return out


def available_actions(current_setting: int, n_trials: int) -> np.ndarray:
    """The same boundary and lock mask used during Entry-89 training."""
    atten, bank_code = J.split_setting(current_setting)
    rs_code, cs_code = divmod(bank_code, 8)
    return np.asarray([
        atten > 0, atten < 7, rs_code > 0, rs_code < 7,
        cs_code > 0, cs_code < 7, int(n_trials) >= 2,
    ], dtype=np.bool_)


def moved_setting(setting: int, action: int) -> int:
    """Apply one legal local action to the 8 x 8 x 8 code cube."""
    atten, bank_code = J.split_setting(setting)
    rs_code, cs_code = divmod(bank_code, 8)
    if action == A_ATTEN_DOWN:
        atten -= 1
    elif action == A_ATTEN_UP:
        atten += 1
    elif action == A_RS_DOWN:
        rs_code -= 1
    elif action == A_RS_UP:
        rs_code += 1
    elif action == A_CS_DOWN:
        cs_code -= 1
    elif action == A_CS_UP:
        cs_code += 1
    else:
        raise ValueError(f"action {action} is not a move")
    if not (0 <= atten < 8 and 0 <= rs_code < 8 and 0 <= cs_code < 8):
        raise ValueError("move crosses the characterised code-bank boundary")
    return J.setting_id(atten, rs_code * 8 + cs_code)


def trace_policy(
        net, observe: Callable[[int], tuple[bool, float, float]],
        request: tuple[float, float], start_setting: int,
        max_trials: int = MAX_TRIALS,
        choose_action: Callable = deterministic_action) -> PolicyTrace:
    """Run the frozen proposer with measured-eye inputs and no hidden truth."""
    if not 2 <= int(max_trials) <= MAX_TRIALS:
        raise ValueError(f"max_trials must be in 2..{MAX_TRIALS}")
    current = int(start_setting)
    tried = [current]
    measured = [tuple(observe(current))]
    actions: list[int] = []
    while len(tried) < int(max_trials):
        obs = build_observation(request, current, tried, measured, max_trials)
        mask = available_actions(current, len(tried))
        action = int(choose_action(net, obs, mask))
        if not 0 <= action < N_ACTIONS or not bool(mask[action]):
            raise ValueError(f"policy selected unavailable action {action}")
        actions.append(action)
        if action == A_LOCK:
            break
        current = moved_setting(current, action)
        tried.append(current)
        measured.append(tuple(observe(current)))
    return PolicyTrace(
        start_setting=int(start_setting), locked_setting=current,
        settings_tried=tuple(tried), measurements=tuple(measured),
        actions=tuple(actions))


def select_with_bank_fallback(
        table: MarginBankTable, identity: tuple[str, float, float, float],
        settings_tried: Sequence[int]) -> HybridSelection:
    """Shield proposed settings, then search the measured bank if necessary."""
    settings = [int(value) for value in settings_tried]
    if not settings:
        raise ValueError("the safety shield needs at least one proposal")
    corner, loss, peaking, frequency = identity
    good = []
    for index, setting in enumerate(settings):
        if table.compliant(setting, corner, loss, peaking, frequency):
            good.append((table.eye_area(setting, corner, loss), -index,
                         -setting, setting))
    if good:
        area, _, _, setting = max(good)
        return HybridSelection(
            setting=int(setting), compliant=True, source="rl-shield",
            eye_area=float(area), verifier_calls=len(settings),
            bank_rows_checked=0)

    candidates = table.compliant_settings(corner, loss, peaking, frequency)
    if not candidates:
        return HybridSelection(
            setting=settings[0], compliant=False, source="bank-miss",
            eye_area=float(table.eye_area(settings[0], corner, loss)),
            verifier_calls=len(settings), bank_rows_checked=len(table.settings))
    setting = max(candidates, key=lambda value: (
        table.eye_area(value, corner, loss), -int(value)))
    return HybridSelection(
        setting=int(setting), compliant=True, source="bank-fallback",
        eye_area=float(table.eye_area(setting, corner, loss)),
        verifier_calls=len(settings), bank_rows_checked=len(table.settings))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _nearest_request(target: tuple[float, float], requests: Sequence[tuple]
                     ) -> tuple[float, float]:
    pk_lo, pk_hi = SPEC_PEAKING_DB_RANGE
    f_lo, f_hi = SPEC_F_PEAK_HZ_RANGE

    def point(row):
        return ((float(row[0]) - pk_lo) / (pk_hi - pk_lo),
                math.log2(float(row[1]) / f_lo) / math.log2(f_hi / f_lo))

    target_point = point(target)
    return min((tuple(map(float, row)) for row in requests), key=lambda row: (
        round((point(row)[0] - target_point[0]) ** 2
              + (point(row)[1] - target_point[1]) ** 2, 15), row))


def _load_assets():
    """Load and hash-check the frozen DEVELOPMENT table/policy/start map."""
    from nebula.experiments import exp_margin_improve_controls as BASE
    from nebula.experiments import exp_shielded_ppo as ENTRY89

    if J._decoded_sha256(ENTRY89.source_path()) != ENTRY89.SOURCE_SHA256:
        raise ValueError("RL-hybrid source table hash mismatch")
    manifest_path = ENTRY89.policy_manifest_path()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("status") != "FIVE_POLICIES_FROZEN"
            or int(manifest.get("deployment_seed", -1))
            != ENTRY89.DEPLOYMENT_SEED):
        raise ValueError("RL-hybrid frozen policy manifest mismatch")
    development_path = ENTRY89.development_results_path()
    if _sha256(development_path) != manifest["development_results_sha256"]:
        raise ValueError("RL-hybrid DEVELOPMENT start-map hash mismatch")
    development = json.loads(development_path.read_text(encoding="utf-8"))
    starts: dict[tuple[float, float], int] = {}
    for row in development["fixed"]["per_identity"]:
        request = (float(row["target_peaking_db"]),
                   float(row["target_f_peak_hz"]))
        setting = int(row["start_setting"])
        previous = starts.setdefault(request, setting)
        if previous != setting:
            raise ValueError("RL-hybrid start changes within one request")
    if set(starts) != set(BASE.REQUESTS):
        raise ValueError("RL-hybrid DEVELOPMENT request membership mismatch")
    _, nets = ENTRY89.validate_training_artifacts()
    table = MarginBankTable.from_path(ENTRY89.source_path())
    return table, nets[ENTRY89.DEPLOYMENT_SEED], starts, manifest


def losses_to_verify(table: MarginBankTable,
                     loss_db: Optional[float]) -> tuple[float, ...]:
    """Return the automatic channel family or one diagnostic override.

    Channel loss is an external operating condition, not part of the user's
    requested CTLE response.  ``None`` is therefore the product default and
    means every characterised channel.  A scalar remains available for a
    deliberately narrower diagnostic run.
    """
    characterised = tuple(float(value) for value in table.losses)
    if loss_db is None:
        return characterised
    requested = float(loss_db)
    if requested not in characterised:
        raise ValueError(
            f"channel loss must be one of the characterised values "
            f"{characterised}")
    return (requested,)


def verification_conditions(
        table: MarginBankTable,
        losses: Sequence[float]) -> tuple[tuple[float, str], ...]:
    """The complete loss-by-PVT product, made explicit and testable."""
    return tuple((float(loss), str(corner))
                 for loss in losses for corner in table.corners)


def _nominal_from_row(row: J.JointRow, u: Sequence[float], loss_db: float,
                      request: tuple[float, float]) -> dict:
    from nebula.rl import reward_v1 as R

    margins = J.margins_at(row, loss_db, request[1], request[0])
    if margins is None:
        raise ValueError("selected nominal bank row is not scorable")
    sizing = sizing_from_u(u)
    link = row.links[str(float(loss_db))]
    ratios = {name: float(margins[name]) / float(R.TOL[name])
              for name in J.SPECS}
    worst = min(ratios, key=ratios.get)
    reward = R.feasible_bonus(len(J.SPECS)) + ratios[worst]
    meas = {
        "peaking_db": float(row.peaking_db),
        "f_peak_oct": float(row.f_peak_oct),
        "nyq_boost_db": float(row.margins["S3_nyq_boost"]),
        "inoise_vrms": float(row.noise_mvrms) * 1e-3,
        "power_w": float(row.power_w),
        "g_dc_db": float(row.g_dc_db),
        "pair_margin_v": float(row.margins["saturation"]),
        "tail_margin_v": float(row.margins["tail_saturation"]),
        "eye_h_v": float(link["eye_h_v"]),
        "eye_w_ui": float(link["eye_w_ui"]),
        "area_mm2": SPEC_AREA_MAX_MM2 - float(row.margins["S7_area"]),
        "hd3_nyq_dbc": (SPEC_HD3_MAX_DBC
                         - float(row.margins["S4_hd3_nyq"])),
    }
    meas["_f_peak_ghz"] = 2.5 * 2.0 ** meas["f_peak_oct"]
    meas["_noise_mv"] = meas["inoise_vrms"] * 1e3
    meas["_power_mw"] = meas["power_w"] * 1e3
    return {
        "ok": True, "verdict": "ok", "meas": meas,
        "params": dict(sizing.params), "reward": float(reward),
        "feasible": True, "worst_spec": worst,
        "design_id": design_id(sizing, geometry_tag=(
            f"entry89-a{row.atten_code}-bank{row.bank_code}")),
    }


def solve(peaking_db: float, f_peak_hz: float,
          loss_db: Optional[float] = None) -> dict:
    """Produce the verified channel/PVT code map for a requested response."""
    from nebula.experiments import exp_joint_bank_73 as BANK73
    from nebula.experiments import exp_shielded_ppo as ENTRY89

    request = (float(peaking_db), float(f_peak_hz))
    table, net, starts, manifest = _load_assets()
    losses = losses_to_verify(table, loss_db)
    nearest = _nearest_request(request, tuple(starts))
    start = starts[nearest]
    records = []
    for channel_loss, corner in verification_conditions(table, losses):
        identity = (corner, channel_loss, *request)
        trace = trace_policy(
            net, lambda setting, c=corner, loss=channel_loss: table.observe(
                setting, c, loss), request, start)
        selected = select_with_bank_fallback(
            table, identity, trace.settings_tried)
        records.append({
            "channel_loss_db": channel_loss, "corner": corner,
            "setting": selected.setting,
            "atten_code": J.split_setting(selected.setting)[0],
            "bank_code": J.split_setting(selected.setting)[1],
            "source": selected.source, "compliant": selected.compliant,
            "eye_area": selected.eye_area,
            "rl_measurements": len(trace.settings_tried),
            "verifier_calls": selected.verifier_calls,
            "bank_rows_checked": selected.bank_rows_checked,
            "policy_trace": policy_trace_record(trace),
        })
    misses = [row for row in records if not row["compliant"]]
    if misses:
        raise RuntimeError(
            f"the characterised bank has no compliant setting at "
            f"{len(misses)} of {len(records)} channel/PVT conditions; "
            f"refusing to emit "
            f"an unverified RL design")

    _, _, base_u, _ = BANK73._load_sources()
    bank = J.bank(base_u, n_rs=J.N_RS, n_cs=J.N_CS,
                  rs_span=J.RS_SPAN, cs_span=J.CS_SPAN)
    nominal_corner = "tt/1.00/27C"
    # For the automatic family this is its actual middle characterised point
    # (7.5 dB for the registered seven-point grid), not a new design target.
    # For a diagnostic override the sole requested loss is representative.
    representative_loss = losses[len(losses) // 2]
    nominal_record = next(row for row in records
                          if row["corner"] == nominal_corner
                          and row["channel_loss_db"] == representative_loss)
    atten_code, bank_code = J.split_setting(nominal_record["setting"])
    u = bank[bank_code].u
    nominal_row = table.row(nominal_record["setting"], nominal_corner)
    nominal = _nominal_from_row(
        nominal_row, u, representative_loss, request)
    fallbacks = sum(row["source"] == "bank-fallback" for row in records)
    verification = {
        "mode": "precharacterised-ngspice-bank-v6",
        "n_corners": len(table.corners),
        "n_channel_losses": len(losses), "n_points": len(records),
        "n_pass": len(records), "n_failed": 0, "all_points_pass": True,
        # S9 mandates the 45-corner PVT grid.  The seven-channel sweep is an
        # additional robustness axis, so keep the two counts distinct.
        "n_mandated_points": len(table.corners),
        "n_mandated_pass": len(table.corners), "mandated_all_pass": True,
        "all_pvt_pass_at_every_channel_loss": True,
        "channel_loss_mode": ("automatic-family" if loss_db is None
                              else "diagnostic-override"),
        "channel_losses_db": list(losses),
        "representative_channel_loss_db": representative_loss,
        "spec_set": "V6_SPECS (13 rows, operating-point HD3)",
        "per_condition": records,
    }
    return {
        "u": list(u), "reward": nominal["reward"], "sims": 0,
        "n_candidates": len(table.settings), "n_tied_at_best": 1,
        "design_id": nominal["design_id"], "which_path": "rl-bank",
        "policy_seed": int(ENTRY89.DEPLOYMENT_SEED),
        "policy_file": next(row["policy_file"] for row in manifest["policies"]
                            if int(row["seed"]) == ENTRY89.DEPLOYMENT_SEED),
        "channel_loss_mode": ("automatic-family" if loss_db is None
                              else "diagnostic-override"),
        "channel_losses_db": list(losses),
        "representative_channel_loss_db": representative_loss,
        "nearest_training_request": list(nearest),
        "setting": int(nominal_record["setting"]),
        "atten_code": int(atten_code), "bank_code": int(bank_code),
        "atten_max_x": float(BANK73.PROBE_MAX_X),
        "rl_proposals": int(sum(row["rl_measurements"] for row in records)),
        "shield_verifier_calls": int(sum(
            row["verifier_calls"] for row in records)),
        "shield_fallbacks": int(fallbacks),
        "table_rows_checked": int(sum(
            row["bank_rows_checked"] for row in records)),
        "offline_spice_rows": len(table.settings) * len(table.corners),
        "offline_link_points": (len(table.settings) * len(table.corners)
                                * len(table.losses)),
        "_nominal": nominal, "_verification": verification,
    }


__all__ = (
    "PolicyTrace", "HybridSelection", "ACTION_NAMES", "policy_trace_record",
    "build_observation",
    "available_actions", "moved_setting", "trace_policy",
    "select_with_bank_fallback", "losses_to_verify",
    "verification_conditions", "solve")
