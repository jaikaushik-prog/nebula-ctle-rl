"""Bounded current-mode decision/hold prototype; not an integrated DFE."""
from dataclasses import asdict
import numpy as np

from nebula.common.types import UI_SECONDS as UI
from nebula.device import dfe_hardware as D
from nebula.device.passives import RES_HIGH_PO, ResistorGeometry
from nebula.device.sky130_runner import lib_for_device

WIDTHS_UM = (4, 8, 16)
EDGE_S = UI / 20
VECTORS = ('v(clk)', 'v(clkb)', 'v(inp)', 'v(inn)', 'v(mp)', 'v(mn)',
           'v(q)', 'v(qb)', 'i(vdd)', 'i(vclk)', 'i(vclkb)', 'i(vinp)', 'i(vinn)')


def mos_lines(width):
    if width not in WIDTHS_UM:
        raise ValueError('width outside registered CML set')
    rows = []
    def mos(name, nodes, w, length=.15):
        rows.append(f'X{name} {nodes} {D.NFET} w={w:g} l={length:g} nf={w/2:g}')
    for name, ip, inn, op, on, track, hold in (
            ('m', 'inp', 'inn', 'mp', 'mn', 'clkb', 'clk'),
            ('s', 'mp', 'mn', 'q', 'qb', 'clk', 'clkb')):
        mos(name+'ip', f'{on} {ip} {name}a 0', width)
        mos(name+'in', f'{op} {inn} {name}a 0', width)
        mos(name+'rp', f'{op} {on} {name}b 0', width)
        mos(name+'rn', f'{on} {op} {name}b 0', width)
        mos(name+'track', f'{name}a {track} {name}tail 0', 8)
        mos(name+'hold', f'{name}b {hold} {name}tail 0', 8)
        mos(name+'tail', f'{name}tail nbias 0 0', 20, .5)
    mos('ref', 'nbias nbias 0 0', 4, .5)
    return rows


def resistor_geometries():
    # Deliberate compact drawn geometry; the global selector prioritizes
    # resistance accuracy over node capacitance. Do not change that selector.
    return [ResistorGeometry(w_um=1, l_um=length, m=1, subckt=RES_HIGH_PO.name,
                r_target_ohm=target, r_actual_ohm=RES_HIGH_PO.resistance(1, length))
            for length, target in [(1.33, 800)]*4 + [(30.33, 10000)]]


def resistor_lines():
    rows = []
    for node, g in zip(('mp', 'mn', 'q', 'qb', 'nbias'), resistor_geometries()):
        rows.append(f'XR_{node} vdd {node} 0 {g.subckt} w={g.w_um:g} l={g.l_um:g} m={g.m}')
    return rows


def geometry(width):
    mos = mos_lines(width)
    area = sum(float(r.split()[6][2:]) * float(r.split()[7][2:]) for r in mos)
    resistors = resistor_geometries()
    return {'mos_count': len(mos), 'mos_gate_um2': area,
            'resistors': [asdict(g) for g in resistors],
            'geometry_subtotal_mm2': (area + sum(g.area_um2 for g in resistors)) / 1e6,
            'routed_layout': False}


def clock_at(t, vdd):
    t = np.asarray(t)
    phase = np.remainder(t - D.edge_time(0), UI)
    fraction = np.where(t < D.edge_time(0), 0,
        np.clip(np.minimum(phase / EDGE_S, (UI/2 - phase) / EDGE_S), 0, 1))
    return vdd/3 * (1 + fraction), vdd/3 * (2 - fraction)


def deck(width, corner, cm, bits):
    if not np.isfinite(cm) or np.asarray(bits).shape != (36,) or not np.isin(bits, (0, 1)).all():
        raise ValueError('invalid common mode or bit pattern')
    vdd = 1.8 * corner.vdd_scale
    lib = lib_for_device(D.NFET, real_passives=True, section=corner.process)
    lines = ['* Entry 122 CML master/slave; external differential clock, no feedback DAC',
             f'.lib "{lib.as_posix()}" {corner.process}', f'.temp {corner.temp_c:g}',
             f'Vdd vdd 0 {vdd:.16g}']
    for name, lo, hi in [('clk', vdd/3, 2*vdd/3), ('clkb', 2*vdd/3, vdd/3)]:
        lines.append(f'V{name} {name} 0 PULSE({lo:.16g} {hi:.16g} {D.edge_time(0):.16g} '
                     f'{EDGE_S:.16g} {EDGE_S:.16g} {UI/2-2*EDGE_S:.16g} {UI:.16g})')
    for node, sign in [('inp', 1), ('inn', -1)]:
        ts, vs = D._points(bits, cm, sign)
        lines.append(f'V{node} {node} 0 PWL(')
        lines.extend(f'+ {t:.16g} {v:.16g}' for t, v in zip(ts, vs))
        lines.append('+ )')
    devices = mos_lines(width)
    lines.extend(devices + resistor_lines())
    lines.extend(['.control', 'set noaskquit', 'set numdgt=15',
                  f'tran 1p {38*UI:.16g} 0 1p',
                  'wrdata trace.txt ' + ' '.join(VECTORS),
                  'wrdata terminals.txt ' + ' '.join(f'v({n})' for n in D.terminal_nodes(devices)),
                  'quit', '.endc', '.end'])
    return '\n'.join(lines) + '\n'


def read_trace(path):
    data = np.loadtxt(path)
    if (data.ndim != 2 or data.shape[1] != 2*len(VECTORS) or not np.isfinite(data).all()
            or not np.equal(data[:, 0::2], data[:, :1]).all()):
        raise ValueError('malformed CML trace or inconsistent axes')
    return data[:, 0], data[:, 1::2]


def analyze(t, values, bits, vdd, cm):
    t, y, bits = np.asarray(t), np.asarray(values), np.asarray(bits)
    if (t.ndim != 1 or len(t) < 100 or y.shape != (len(t), len(VECTORS))
            or not np.isfinite(t).all() or not np.isfinite(y).all()
            or np.any(np.diff(t) <= 0) or np.max(np.diff(t)) > UI/100
            or t[0] > D.RISE_S or t[-1] < D.edge_time(35) + .95*UI
            or bits.shape != (36,) or not np.isin(bits, (0, 1)).all()):
        raise ValueError('nonfinite, unordered, undersampled or truncated CML data')
    expected = (*clock_at(t, vdd), *D.inputs_at(t, bits, cm))
    errors = [float(np.max(np.abs(y[:, j] - e))) for j, e in enumerate(expected)]
    rows = []
    for i in range(D.WARMUP, 36):
        edge, sign = D.edge_time(i), 2*int(bits[i])-1
        masks = [(t >= edge+.44*UI) & (t <= edge+.49*UI),
                 (t >= edge+.55*UI) & (t <= edge+.95*UI),
                 (t >= edge-.05*UI) & (t <= edge-.005*UI)]
        if any(m.sum() < n for m, n in zip(masks, (8, 70, 8))):
            raise ValueError('missing decision, hold or previous-bit window')
        margins = [(y[:, 4]-y[:, 5])*sign, (y[:, 6]-y[:, 7])*sign,
                   (y[:, 6]-y[:, 7])*(2*int(bits[i-1])-1)]
        minimum = [float(w[m].min()) for w, m in zip(margins, masks)]
        interval = np.flatnonzero((t >= edge) & (t <= edge+.95*UI))
        bad = np.flatnonzero(margins[1][interval] <= 0)
        stable = int(bad[-1]+1) if len(bad) else 0
        delay = float(t[interval[stable]]-edge) if stable < len(interval) else None
        rows.append({'bit_index': i, 'expected_bit': int(bits[i]),
                     'raw_min_differential_v': minimum[0], 'held_min_differential_v': minimum[1],
                     'previous_min_differential_v': minimum[2], 'final_stable_delay_s': delay,
                     'pass': all(v > 0 for v in minimum)})
    mask = (t >= (D.WARMUP+1)*UI) & (t <= 37*UI)
    def average(w):
        return float(np.trapezoid(w[mask], t[mask]) / (t[mask][-1]-t[mask][0]))
    clocks = [-y[:, j] * y[:, j+9] for j in (0, 1)]
    return {'block_pass': bool(max(errors) < 1e-5 and all(r['pass'] for r in rows)),
            'stimulus_valid': max(errors) < 1e-5, 'stimulus_max_error_v': errors,
            'correct_bits': sum(r['pass'] for r in rows), 'scored_bits': 32, 'bits': rows,
            'dut_vdd_power_w': average(-vdd*y[:, 8]),
            'external_clock_net_power_w': sum(average(w) for w in clocks),
            'external_clock_positive_supplied_power_w': sum(average(np.maximum(w, 0)) for w in clocks),
            'ideal_input_source_net_power_w': average(-y[:, 2]*y[:, 11]-y[:, 3]*y[:, 12]),
            'hardware_dfe_complete': False, 'full_receiver_verified': False}
