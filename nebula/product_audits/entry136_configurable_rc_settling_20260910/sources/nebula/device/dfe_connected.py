"""Entry 124 physical CTLE, CML summer, stored decision and current DAC.

External sources are stimulus/clock/control apparatus. There is no ideal
decision, reference-bit injection, or behavioral cancellation inside the DUT.
"""
import hashlib
import json
import re
from pathlib import Path

import numpy as np
from scipy.signal import fftconvolve

from nebula.common.types import UI_SECONDS as UI
from nebula.device import dfe_cml as C, dfe_hardware as D
from nebula.experiments import exp_physical_bias as P
from nebula.experiments.exp_dfe_slicer import SOURCE
from nebula.report.product_scope import area_inventory

PHASES_UI = (.5, .75, 1.)
TAP_CODES = (1, 2, 4, 8)
OSR, N_FFT, WARMUP, N_BITS, STOP_UI = 128, 32768, 16, 80, 84
VECTORS = ('v(df_clk)', 'v(df_clkb)', 'v(vid)', 'v(sum_p)', 'v(sum_n)',
           'v(df_q)', 'v(df_qb)', 'i(vdd)', 'i(vdfclk)', 'i(vdfclkb)',
           'i(vid)', 'v(outp)', 'v(outn)', 'i(vcm)',
           *tuple(x for k in range(4) for x in (f'v(tap{k})', f'i(vtap{k})')),
           'v(cm)', 'v(df_mp)', 'v(df_mn)')


def pattern(cfg):
    rng = np.random.default_rng(cfg.seed)
    return np.r_[np.tile([0, 0, 1, 1, 0, 1, 0, 1], 4), rng.integers(0, 2, 48)].astype(int)


def stimulus(cfg, bits):
    bits = np.asarray(bits)
    if bits.shape != (N_BITS,) or not np.isin(bits, (0, 1)).all():
        raise ValueError('invalid registered connected pattern')
    cfg.channel.assert_causal(osr=OSR, n_fft=N_FFT)
    cfg.channel.assert_passive()
    h = cfg.channel.impulse_response(osr=OSR, n_fft=N_FFT)
    impulse = np.zeros((N_BITS+4)*OSR+1)
    padded = np.r_[bits, bits[-1], bits[-1]]
    impulse[2*OSR:(2+len(padded))*OSR:OSR] = 2*padded-1
    pulse = fftconvolve(cfg.tx.pulse(OSR), h)
    v = fftconvolve(impulse, pulse)[:len(impulse)]
    t = np.arange(len(v)) * UI/OSR
    if not np.isfinite(v).all() or np.max(np.abs(v[t < 2*UI])) > 1e-12:
        raise ValueError('nonfinite or noncausal input waveform')
    return t, v


def edge_time(i, phase):
    return (i+2+phase)*UI


def clock_at(t, vdd, phase):
    return C.clock_at(np.asarray(t)-edge_time(0, phase)+D.edge_time(0), vdd)


def source_deck():
    path = SOURCE/'design.cir'
    expected = json.loads((SOURCE/'evidence_sha256.json').read_text())['design.cir']
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError('physical CTLE source hash changed')
    return path.read_text()


def extra_mos(sign):
    if sign not in (-1, 1):
        raise ValueError('invalid fixed feedback polarity')
    nodes = {'0': '0', 'vdd': 'vdd', 'inp': 'sum_p', 'inn': 'sum_n'}
    rows = []
    for line in C.mos_lines(8):
        f = line.split()
        f[0] = 'Xdf_'+f[0][1:]
        f[1:5] = [nodes.get(n, 'df_'+n) for n in f[1:5]]
        rows.append(' '.join(f))
    def mos(name, terminals, width, length=.15, nf=None):
        rows.append(f'Xdfe_{name} {terminals} {D.NFET} w={width:g} l={length:g} '
                    f'nf={max(1, width/2) if nf is None else nf:g}')
    # CTLE outn rises for a positive input symbol. The summer preserves that
    # polarity, while a high stored q steers cancellation into sum_p.
    mos('sump', 'sum_n outn sum_tail 0', 8)
    mos('sumn', 'sum_p outp sum_tail 0', 8)
    mos('sumtail', 'sum_tail df_nbias 0 0', 20, .5)
    qp, qn = ('df_q', 'df_qb') if sign == 1 else ('df_qb', 'df_q')
    mos('dacp', f'sum_p {qp} fd_common 0', 2)
    mos('dacn', f'sum_n {qn} fd_common 0', 2)
    for k, width in enumerate((1, 2, 4, 8)):
        mos(f'tail{k}', f'fd_common df_nbias fd_tail{k} 0', width, .5)
        mos(f'en{k}', f'fd_tail{k} tap{k} 0 0', 8)
    return rows


def extra_resistors():
    rows = []
    for line in C.resistor_lines():
        f = line.split()
        f[0] = 'Xdf_'+f[0][1:]
        f[2] = 'df_'+f[2]
        rows.append(' '.join(f))
    g = C.resistor_geometries()[0]
    for node in ('sum_p', 'sum_n'):
        rows.append(f'Xdfe_R{node} vdd {node} 0 {g.subckt} w={g.w_um:g} l={g.l_um:g} m={g.m}')
    return rows


def all_mos(deck):
    return [line for line in deck.splitlines() if len(line.split()) >= 6
            and line.startswith('X') and line.split()[5] in (D.NFET, D.PFET)]


def geometry():
    original = area_inventory(source_deck())
    gate = sum(float(s.split()[6][2:])*float(s.split()[7][2:]) for s in extra_mos(1))
    body = sum(g.area_um2 for g in C.resistor_geometries()) + 2*C.resistor_geometries()[0].area_um2
    return {'ctle_geometry_subtotal_mm2': original['geometry_subtotal_mm2'],
            'added_mos_gate_um2': gate, 'added_resistor_body_um2': body,
            'added_mos_count': len(extra_mos(1)), 'added_poly_count': 7,
            'geometry_subtotal_mm2': original['geometry_subtotal_mm2']+(gate+body)*1e-6,
            'full_area_mm2': None, 'routed_layout': False,
            'excluded': ['clock/control drivers', 'common-mode generator',
                         'Rs/Cs selectors', 'contacts/wells/routing/spacing']}


def deck(corner, cfg, bits, phase, code, sign):
    if phase not in PHASES_UI or code not in (0, *TAP_CODES) or sign not in (-1, 1):
        raise ValueError('unregistered connected experiment member')
    base = P.corner_deck(source_deck(), corner.process, corner.vdd_scale, corner.temp_c).split('.control')[0]
    t, v = stimulus(cfg, bits)
    inp = 'Vid vid 0 PWL(\n' + '\n'.join(f'+ {a:.16g} {b:.16g}' for a, b in zip(t, v)) + '\n+ )'
    base = re.sub(r'^Vid\s+.*$', lambda _: inp, base, flags=re.M)
    vdd = 1.8*corner.vdd_scale
    lines = [base, '* Entry 124: real current summer, CML decision memory, switched-current DAC']
    for name, lo, hi in [('clk', vdd/3, 2*vdd/3), ('clkb', 2*vdd/3, vdd/3)]:
        lines.append(f'Vdf{name} df_{name} 0 PULSE({lo:.16g} {hi:.16g} {edge_time(0,phase):.16g} '
                     f'{C.EDGE_S:.16g} {C.EDGE_S:.16g} {UI/2-2*C.EDGE_S:.16g} {UI:.16g})')
    for k in range(4):
        lines.append(f'Vtap{k} tap{k} 0 {vdd if code & (1<<k) else 0:.16g}')
    lines.extend(extra_mos(sign)+extra_resistors())
    circuit = '\n'.join(lines)
    terminals = D.terminal_nodes(all_mos(circuit))
    lines.extend(['.control', 'set noaskquit', 'set numdgt=15',
                  f'tran 1p {STOP_UI*UI:.16g} 0 1p',
                  'wrdata trace.txt '+' '.join(VECTORS),
                  'wrdata terminals.txt '+' '.join(f'v({n})' for n in terminals),
                  'quit', '.endc', '.end'])
    return '\n'.join(lines)+'\n'


def read_trace(path):
    data = np.loadtxt(path)
    if (data.ndim != 2 or data.shape[1] != 2*len(VECTORS) or not np.isfinite(data).all()
            or not np.equal(data[:, 0::2], data[:, :1]).all()):
        raise ValueError('malformed connected trace')
    return data[:, 0], data[:, 1::2]


def analyze(t, values, bits, cfg, phase, vdd, *, code=0):
    t, y, bits = np.asarray(t), np.asarray(values), np.asarray(bits)
    if (t.ndim != 1 or len(t) < 100 or y.shape != (len(t), len(VECTORS))
            or not np.isfinite(t).all() or not np.isfinite(y).all()
            or np.any(np.diff(t) <= 0) or np.max(np.diff(t)) > UI/100
            or t[0] > 2e-12 or t[-1] < edge_time(N_BITS-1, phase)+.95*UI
            or bits.shape != (N_BITS,) or not np.isin(bits, (0, 1)).all()):
        raise ValueError('invalid, undersampled or truncated connected data')
    ti, vi = stimulus(cfg, bits)
    expected = (*clock_at(t, vdd, phase), np.interp(t, ti, vi))
    errors = [float(np.max(np.abs(y[:, j]-e))) for j,e in enumerate(expected)]
    errors += [float(np.max(np.abs(y[:, 14+2*k] - (vdd if code & (1<<k) else 0)))) for k in range(4)]
    rows, positive, negative = [], [], []
    for i in range(WARMUP, N_BITS):
        edge, sign = edge_time(i, phase), 2*int(bits[i])-1
        raw = (t >= edge+.44*UI) & (t <= edge+.49*UI)
        held = (t >= edge+.55*UI) & (t <= edge+.95*UI)
        pre = (t >= edge-.05*UI) & (t <= edge-.005*UI)
        if raw.sum() < 8 or held.sum() < 70 or pre.sum() < 8:
            raise ValueError('missing connected sample/hold windows')
        decision = (y[:, 5]-y[:, 6])*sign
        raw_margin = float(((y[:, -2]-y[:, -1])*sign)[raw].min())
        hold_margin = float(decision[held].min())
        prev_margin = float(((y[:, 5]-y[:, 6])*(2*int(bits[i-1])-1))[pre].min())
        analog = (y[:, 3]-y[:, 4])[pre]
        (positive if sign == 1 else negative).extend(analog.tolist())
        rows.append({'bit_index': i, 'expected_bit': int(bits[i]),
                     'master_min_differential_v': raw_margin,
                     'held_min_differential_v': hold_margin,
                     'previous_min_differential_v': prev_margin,
                     'sample_min_signed_v': float((analog*sign).min()),
                     'pass': min(raw_margin, hold_margin, prev_margin) > 0})
    if not positive or not negative:
        raise ValueError('missing both binary eye levels')
    mask = (t >= (2+WARMUP)*UI) & (t <= (2+N_BITS)*UI)
    def average(w):
        return float(np.trapezoid(w[mask], t[mask])/(t[mask][-1]-t[mask][0]))
    clk = [-y[:, j]*y[:, j+8] for j in (0,1)]
    controls = [-y[:, 14+2*k]*y[:, 15+2*k] for k in range(4)]
    return {'logic_pass': bool(max(errors) < 1e-5 and all(r['pass'] for r in rows)),
            'stimulus_valid': max(errors) < 1e-5, 'stimulus_max_error_v': errors,
            'correct_bits': sum(r['pass'] for r in rows), 'scored_bits': N_BITS-WARMUP,
            'bits': rows, 'sampled_eye_height_v': float(min(positive)-max(negative)),
            'minimum_sample_signed_v': min(r['sample_min_signed_v'] for r in rows),
            'ctle_plus_dfe_vdd_power_w': average(-vdd*y[:, 7]),
            'external_clock_net_power_w': sum(average(w) for w in clk),
            'external_clock_positive_supplied_power_w': sum(average(np.maximum(w,0)) for w in clk),
            'external_tap_control_positive_supplied_power_w': sum(average(np.maximum(w,0)) for w in controls),
            'ideal_signal_source_net_power_w': average(-y[:,2]*y[:,10]),
            'ideal_common_mode_source_net_power_w': average(-y[:,-3]*y[:,13]),
            'full_receiver_verified': False,
            'scope': 'finite noiseless transistor transient, not BER or full S3-S9 signoff'}
