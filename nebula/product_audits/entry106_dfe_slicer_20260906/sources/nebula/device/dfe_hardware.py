"""Entry 106 MOS decision/hold prototype. NOT a complete transistor DFE.

See DFE_HARDWARE_PLAN.md. No behavioural decision or reference-bit injection
inside DUT. Exceptions here are instrument errors, caught by the experiment;
this standalone prototype is deliberately not in the production RL path.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from nebula.common.types import UI_SECONDS, SPEC_EYE_H_MIN_V, Corner
from nebula.device.sky130_runner import lib_for_device
from nebula.link.config import LinkConfig

WIDTHS_UM = (4, 8, 16)
L_UM = .15
RISE_S = UI_SECONDS / 100
WARMUP = 4
VECTORS = ('v(clk)', 'v(inp)', 'v(inn)', 'v(x)', 'v(y)', 'v(q)', 'v(qb)',
           'i(vdd)', 'i(vclk)', 'i(vinp)', 'i(vinn)')
NFET = 'sky130_fd_pr__nfet_01v8'
PFET = 'sky130_fd_pr__pfet_01v8'


def pattern(cfg: LinkConfig) -> np.ndarray:
    rng = np.random.default_rng(cfg.seed)
    return np.concatenate(([0, 1, 0, 1], [0, 0, 1, 1, 0, 1, 0, 1],
                           rng.integers(0, 2, 24))).astype(int)


def edge_time(bit_index: int) -> float:
    return (bit_index + 1.5) * UI_SECONDS


def _points(bits, cm, polarity):
    levels = cm + polarity * (2 * np.asarray(bits) - 1) * SPEC_EYE_H_MIN_V / 4
    times, volts = [0.0], [float(levels[0])]
    for i in range(1, len(bits)):
        start = (i + 1) * UI_SECONDS
        times.extend([start, start + RISE_S])
        volts.extend([float(levels[i - 1]), float(levels[i])])
    times.append((len(bits) + 2) * UI_SECONDS)
    volts.append(float(levels[-1]))
    return np.asarray(times), np.asarray(volts)


def inputs_at(t, bits, cm):
    return tuple(np.interp(t, *_points(bits, cm, sign)) for sign in (1, -1))


def clock_at(t, vdd):
    t = np.asarray(t)
    phase = np.remainder(t - edge_time(0), UI_SECONDS)
    wave = np.minimum(phase / RISE_S, 1.0)
    wave = np.minimum(wave, (UI_SECONDS / 2 - phase) / RISE_S)
    return np.where(t < edge_time(0), 0, np.clip(wave, 0, 1)) * vdd


def dut_lines(width_um):
    if width_um not in WIDTHS_UM:
        raise ValueError('width is not in the registered 4/8/16 um set')
    lines = []

    def mos(name, nodes, p=False, ratio=1):
        w = width_um * ratio
        lines.append(f'X{name} {nodes} {PFET if p else NFET} '
                     f'w={w:g} l={L_UM:g} nf={w / 2:g}')

    mos('in1', 'p inp tail 0')
    mos('in2', 'n inn tail 0')
    mos('regen1', 'x y p 0')
    mos('regen2', 'y x n 0')
    mos('pull1', 'x y vdd vdd', True)
    mos('pull2', 'y x vdd vdd', True)
    mos('tail', 'tail clk 0 0', ratio=2)
    for node in ('p', 'n', 'x', 'y'):
        mos('pre_' + node, f'{node} clk vdd vdd', True)
    # Cross-coupled static NANDs: active-low x sets q, y resets q.
    for out, active_low, other in (('q', 'x', 'qb'), ('qb', 'y', 'q')):
        mos(out + '_p1', f'{out} {active_low} vdd vdd', True)
        mos(out + '_p2', f'{out} {other} vdd vdd', True)
        mos(out + '_n1', f'{out} {active_low} {out}_series 0')
        mos(out + '_n2', f'{out}_series {other} 0 0')
    return lines


def geometry(width_um):
    dut_lines(width_um)
    return {'mos_count': 19, 'input_total_width_um': width_um,
            'length_um': L_UM, 'gate_geometry_mm2': 20 * width_um * L_UM / 1e6,
            'full_area_mm2': None, 'scope': 'MOS gate W*L only, not layout area'}


def deck(width_um, corner: Corner, common_mode_v: float, bits):
    vdd = 1.8 * corner.vdd_scale
    if not math.isfinite(common_mode_v) or not 0 < common_mode_v < vdd:
        raise ValueError('invalid common mode')
    bits = np.asarray(bits)
    if bits.shape != (36,) or not np.isin(bits, (0, 1)).all():
        raise ValueError('expected registered 36-bit binary pattern')
    lib = lib_for_device(NFET, include_pfet=True, section=corner.process)
    lines = ['* Entry 106: decision and hold only; external clock/input, no DFE feedback',
             f'.lib "{lib.as_posix()}" {corner.process}', f'.temp {corner.temp_c:g}',
             f'Vdd vdd 0 {vdd:.16g}',
             f'Vclk clk 0 PULSE(0 {vdd:g} 300p 2p 2p 96p 200p)']
    for node, sign in (('inp', 1), ('inn', -1)):
        ts, vs = _points(bits, common_mode_v, sign)
        lines.append(f'V{node} {node} 0 PWL(')
        lines.extend(f'+ {t:.16g} {v:.16g}' for t, v in zip(ts, vs))
        lines.append('+ )')
    lines.extend(dut_lines(width_um))
    lines.extend(['.control', 'set noaskquit', 'set numdgt=15',
                  f'tran 1p {(len(bits) + 2) * UI_SECONDS:.16g} 0 1p',
                  'wrdata trace.txt ' + ' '.join(VECTORS), 'quit', '.endc', '.end'])
    return '\n'.join(lines) + '\n'


def read_trace(path: Path):
    data = np.loadtxt(path)
    if data.ndim != 2 or data.shape[1] != 2 * len(VECTORS) or not np.isfinite(data).all():
        raise ValueError('malformed/nonfinite transient data')
    if not np.equal(data[:, 0::2], data[:, :1]).all():
        raise ValueError('wrdata time axis differs between vectors')
    return data[:, 0], data[:, 1::2]


def analyze(t, values, bits, vdd, common_mode_v):
    t, y, bits = np.asarray(t), np.asarray(values), np.asarray(bits)
    if (t.ndim != 1 or y.shape != (len(t), len(VECTORS)) or len(t) < 100
            or not np.isfinite(t).all() or not np.isfinite(y).all()
            or not np.all(np.diff(t) > 0) or t[0] > RISE_S
            or t[-1] < edge_time(len(bits) - 1) + .95 * UI_SECONDS
            or np.max(np.diff(t)) > UI_SECONDS / 100):
        raise ValueError('nonfinite, unordered, truncated or undersampled transient')
    if bits.shape != (36,) or not np.isin(bits, (0, 1)).all():
        raise ValueError('invalid registered binary pattern')
    exp_p, exp_n = inputs_at(t, bits, common_mode_v)
    stimulus_errors = [float(np.max(np.abs(y[:, j] - expected))) for j, expected in
                       enumerate((clock_at(t, vdd), exp_p, exp_n))]
    # Source equations must reproduce voltage to numerical output precision.
    stimulus_ok = all(error < 1e-5 for error in stimulus_errors)
    rows = []
    for i in range(WARMUP, len(bits)):
        edge = edge_time(i)
        raw = (t >= edge + .44 * UI_SECONDS) & (t <= edge + .49 * UI_SECONDS)
        held = (t >= edge + .55 * UI_SECONDS) & (t <= edge + .95 * UI_SECONDS)
        if raw.sum() < 8 or held.sum() < 70:
            raise ValueError('missing decision or hold window')
        sign = 2 * int(bits[i]) - 1
        raw_margin = np.minimum((vdd / 2 - y[:, 3]) * sign,
                                (y[:, 4] - vdd / 2) * sign)
        hold_margin = np.minimum((y[:, 5] - vdd / 2) * sign,
                                 (vdd / 2 - y[:, 6]) * sign)
        evaluation = np.flatnonzero((t >= edge) & (t <= edge + .49 * UI_SECONDS))
        bad = np.flatnonzero(raw_margin[evaluation] <= 0)
        first_stable = int(bad[-1] + 1) if len(bad) else 0
        delay = (float(t[evaluation[first_stable]] - edge)
                 if first_stable < len(evaluation) else None)
        rows.append({'bit_index': i, 'expected_bit': int(bits[i]),
                     'raw_min_logic_margin_v': float(raw_margin[raw].min()),
                     'held_min_logic_margin_v': float(hold_margin[held].min()),
                     'raw_final_stable_delay_s': delay,
                     'pass': bool(np.all(raw_margin[raw] > 0) and
                                  np.all(hold_margin[held] > 0))})
    # Use the same complete post-warmup window for every source energy.
    mask = (t >= (WARMUP + 1) * UI_SECONDS) & (t <= (len(bits) + 1) * UI_SECONDS)
    tt = t[mask]
    def average(power):
        return float(np.trapezoid(power[mask], tt) / (tt[-1] - tt[0]))
    clock_power = -y[:, 0] * y[:, 8]
    return {'block_pass': bool(stimulus_ok and all(row['pass'] for row in rows)),
            'stimulus_valid': stimulus_ok, 'stimulus_max_error_v': stimulus_errors,
            'scored_bits': len(rows), 'correct_bits': sum(row['pass'] for row in rows),
            'bits': rows, 'dut_vdd_power_w': average(-vdd * y[:, 7]),
            'external_clock_net_power_w': average(clock_power),
            'external_clock_positive_supplied_power_w': average(np.maximum(clock_power, 0)),
            'ideal_input_source_net_power_w': average(-y[:, 1] * y[:, 9] - y[:, 2] * y[:, 10]),
            'hardware_dfe_complete': False, 'full_receiver_verified': False}
