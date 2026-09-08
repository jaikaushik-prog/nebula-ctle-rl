"""Entries 109/110: clean-input memory, optionally with buffers; NOT a DFE."""
from __future__ import annotations

import numpy as np

from nebula.device import dfe_hardware as D
from nebula.device.sky130_runner import lib_for_device

VDD = 1.8
VECTORS = ('v(bx)', 'v(by)', 'v(q)', 'v(qb)', 'i(vdd)', 'i(vset)', 'i(vreset)')


def checked_bits(bits):
    bits = np.asarray(bits)
    if bits.shape != (36,) or not np.isin(bits, (0, 1)).all():
        raise ValueError('expected registered 36-bit binary pattern')
    return bits


def memory_lines():
    # Single definition: use the exact existing device instances, not a copy.
    lines = [line for line in D.dut_lines(4, buffered=True)
             if line.split()[0].startswith(('Xq_', 'Xqb_'))]
    names = {f'X{node}_{kind}' for node in ('q', 'qb')
             for kind in ('p1', 'p2', 'n1', 'n2')}
    if len(lines) != 8 or {line.split()[0] for line in lines} != names:
        raise ValueError('existing eight-MOS memory definition changed')
    return lines


def buffer_memory_lines():
    """Extract, never redeclare, the existing equal-width buffer/storage path."""
    buffers = [line for line in D.dut_lines(4, buffered=True)
               if line.split()[0].startswith('Xbuf_')]
    names = {f'Xbuf_{side}{stage}_{kind}' for side in ('x', 'y')
             for stage in (1, 2) for kind in ('n', 'p')}
    if len(buffers) != 8 or {line.split()[0] for line in buffers} != names:
        raise ValueError('existing eight-MOS buffer definition changed')
    return buffers + memory_lines()


def geometry(*, with_buffers=False):
    lines = buffer_memory_lines() if with_buffers else memory_lines()
    area = 0.0
    for line in lines:
        params = dict(field.split('=') for field in line.split()[6:])
        area += float(params['w']) * float(params['l']) / 1e6
    scope = 'isolated buffers plus memory' if with_buffers else 'isolated memory'
    return {'mos_count': len(lines), 'gate_geometry_mm2': area, 'full_area_mm2': None,
            'scope': scope + ' MOS gate W*L only, not layout or receiver area'}


def points(bits, active_bit):
    bits = checked_bits(bits)
    ts, vs = [0.0], [VDD]
    for i, bit in enumerate(bits):
        if bit != active_bit:
            continue
        edge = D.edge_time(i)
        ts.extend((edge, edge + D.RISE_S,
                   edge + D.UI_SECONDS/2 - D.RISE_S, edge + D.UI_SECONDS/2))
        vs.extend((VDD, 0.0, 0.0, VDD))
    ts.append((len(bits)+2)*D.UI_SECONDS)
    vs.append(VDD)
    return np.asarray(ts), np.asarray(vs)


def inputs_at(t, bits):
    return tuple(np.interp(t, *points(bits, active)) for active in (1, 0))


def deck(bits, *, with_buffers=False):
    bits = checked_bits(bits)
    lib = lib_for_device(D.NFET, include_pfet=True, section='tt')
    lines = ['* Entry 109: isolated memory; ideal test inputs, NOT a hardware DFE',
             f'.lib "{lib.as_posix()}" tt', '.temp 27', f'Vdd vdd 0 {VDD:g}']
    if with_buffers:
        lines[0] = '* Entry 110: isolated buffers and memory; ideal inputs, NOT a hardware DFE'
    set_node, reset_node = ('x', 'y') if with_buffers else ('bx', 'by')
    for source, node, active in (('Vset', set_node, 1), ('Vreset', reset_node, 0)):
        ts, vs = points(bits, active)
        lines.append(f'{source} {node} 0 PWL(')
        lines.extend(f'+ {t:.16g} {v:.16g}' for t, v in zip(ts, vs))
        lines.append('+ )')
    lines.extend(buffer_memory_lines() if with_buffers else memory_lines())
    vectors = (f'v({set_node})', f'v({reset_node})') + VECTORS[2:]
    lines.extend(['.control', 'set noaskquit', 'set numdgt=15',
                  f'tran 1p {(len(bits)+2)*D.UI_SECONDS:.16g} 0 1p',
                  'wrdata trace.txt ' + ' '.join(vectors)])
    if with_buffers:
        lines.append('wrdata buffers.txt v(bx1) v(bx) v(by1) v(by)')
    lines.extend(['quit', '.endc', '.end'])
    return '\n'.join(lines) + '\n'


def read_trace(path):
    data = np.loadtxt(path)
    if data.ndim != 2 or data.shape[1] != 2*len(VECTORS) or not np.isfinite(data).all():
        raise ValueError('malformed/nonfinite memory transient data')
    if not np.equal(data[:, 0::2], data[:, :1]).all():
        raise ValueError('wrdata time axis differs between vectors')
    return data[:, 0], data[:, 1::2]


def analyze(t, values, bits):
    # First two columns always measure the actual external sources. With
    # buffers they are x/y, not the internal bx/by. No synthetic raw decisions.
    bits = checked_bits(bits)
    t, y = np.asarray(t), np.asarray(values)
    if (t.ndim != 1 or y.shape != (len(t), len(VECTORS)) or len(t) < 100
            or not np.isfinite(t).all() or not np.isfinite(y).all()
            or not np.all(np.diff(t) > 0) or t[0] > D.RISE_S
            or t[-1] < D.edge_time(len(bits)-1) + .95*D.UI_SECONDS
            or np.max(np.diff(t)) > D.UI_SECONDS/100):
        raise ValueError('nonfinite, unordered, truncated or undersampled transient')
    errors = [float(np.max(np.abs(y[:, j]-expected)))
              for j, expected in enumerate(inputs_at(t, bits))]
    stimulus_ok = all(error < 1e-5 for error in errors)
    rows = []
    for i in range(D.WARMUP, len(bits)):
        edge = D.edge_time(i)
        held = (t >= edge+.55*D.UI_SECONDS) & (t <= edge+.95*D.UI_SECONDS)
        if held.sum() < 70:
            raise ValueError('missing memory hold window')
        sign = 2*int(bits[i])-1
        margin = np.minimum((y[:, 2]-VDD/2)*sign, (VDD/2-y[:, 3])*sign)
        evaluation = np.flatnonzero((t >= edge) & (t <= edge+.95*D.UI_SECONDS))
        bad = np.flatnonzero(margin[evaluation] <= 0)
        first_stable = int(bad[-1]+1) if len(bad) else 0
        delay = (float(t[evaluation[first_stable]]-edge)
                 if first_stable < len(evaluation) else None)
        rows.append({'bit_index': i, 'expected_bit': int(bits[i]),
                     'held_min_logic_margin_v': float(margin[held].min()),
                     'final_stable_delay_s': delay, 'pass': bool(np.all(margin[held] > 0))})
    post = (t >= (D.WARMUP+1)*D.UI_SECONDS) & (t <= (len(bits)+1)*D.UI_SECONDS)
    tt = t[post]
    def average(power):
        return float(np.trapezoid(power[post], tt)/(tt[-1]-tt[0]))
    source_power = -y[:, 0]*y[:, 5]-y[:, 1]*y[:, 6]
    return {'memory_hold_pass': bool(stimulus_ok and all(row['pass'] for row in rows)),
            'stimulus_valid': stimulus_ok, 'stimulus_max_error_v': errors,
            'scored_bits': len(rows), 'correct_bits': sum(row['pass'] for row in rows),
            'bits': rows, 'dut_vdd_power_w': average(-VDD*y[:, 4]),
            'ideal_input_source_net_power_w': average(source_power),
            'ideal_input_sources_positive_supplied_power_w': average(
                np.maximum(-y[:, 0]*y[:, 5], 0)+np.maximum(-y[:, 1]*y[:, 6], 0)),
            'hardware_dfe_complete': False, 'full_receiver_verified': False}
