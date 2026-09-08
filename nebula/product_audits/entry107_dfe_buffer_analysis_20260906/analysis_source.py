"""Read-only diagnosis of Entry 107 raw evidence. Never invokes SPICE."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

import numpy as np

from nebula.common.types import UI_SECONDS
from nebula.device import dfe_hardware as D
from nebula.experiments.exp_dfe_slicer import digest
from nebula.experiments.exp_physical_bias import write_json


def _verify(root):
    root = root.resolve()
    manifest = json.loads((root / 'evidence_sha256.json').read_text(encoding='utf-8'))
    for key, sha in manifest.items():
        path = (root / key).resolve()
        if not path.is_relative_to(root) or digest(path) != sha:
            raise ValueError(f'evidence hash/path mismatch: {key}')
    return len(manifest)


def diagnose(root: Path):
    count = _verify(root)
    cfg = json.loads((root / 'config.json').read_text(encoding='utf-8'))
    summary = json.loads((root / 'summary.json').read_text(encoding='utf-8'))
    if cfg.get('entry') != 107 or cfg.get('buffered') is not True:
        raise ValueError('expected Entry 107 buffered evidence')
    rows = []
    for item in summary['screening']:
        w = item['width_um']
        folder = root / f'screen_w{w}_tt_1.00_27'
        saved = json.loads((folder / 'result.json').read_text(encoding='utf-8'))
        t, y = D.read_trace(folder / 'trace.txt')
        z = D.read_buffer_trace(folder / 'buffers.txt', t)
        result = D.analyze(t, y, cfg['bits'], 1.8, saved['common_mode_v'])
        if any(value != saved[key] for key, value in result.items()):
            raise ValueError('raw waveform does not reproduce saved gate')
        buffer_bits = []
        for row in result['bits']:
            edge = D.edge_time(row['bit_index'])
            mask = (t >= edge) & (t <= edge + .95 * UI_SECONDS)
            active = 1 if row['expected_bit'] else 3  # bx/by active-low input
            buffer_bits.append({'bit_index': row['bit_index'],
                                'expected_bit': row['expected_bit'],
                                'active_low_min_v': float(z[mask, active].min()),
                                'first_inverter_max_v': float(z[mask, active - 1].max())})
        post = (t >= (D.WARMUP + 1) * UI_SECONDS) & (t <= (len(cfg['bits']) + 1) * UI_SECONDS)
        delays = [b['raw_final_stable_delay_s'] for b in result['bits']
                  if b['raw_final_stable_delay_s'] is not None]
        rows.append({'width_um': w, 'raw_correct_bits': sum(b['raw_min_logic_margin_v'] > 0 for b in result['bits']),
                     'held_correct_bits': sum(b['held_min_logic_margin_v'] > 0 for b in result['bits']),
                     'raw_worst_margin_v': min(b['raw_min_logic_margin_v'] for b in result['bits']),
                     'raw_max_final_stable_delay_s': max(delays) if delays else None,
                     'buffer_low_reached_bits': sum(b['active_low_min_v'] < .9 for b in buffer_bits),
                     'active_low_min_v': min(b['active_low_min_v'] for b in buffer_bits),
                     'memory_q_min_v': float(y[post, 5].min()), 'memory_q_max_v': float(y[post, 5].max()),
                     'buffer_bits': buffer_bits,
                     'dut_vdd_power_w': result['dut_vdd_power_w'],
                     'external_clock_net_power_w': result['external_clock_net_power_w'],
                     'external_clock_positive_supplied_power_w': result['external_clock_positive_supplied_power_w'],
                     'gate_geometry_mm2': saved['geometry']['gate_geometry_mm2']})
    return {'entry': 107, 'evidence_hashes_verified': count, 'spice_calls_added': 0,
            'measured_spice_calls': summary['spice_calls'], 'screening': rows,
            'hardware_dfe_complete': False, 'full_receiver_verified': False}


def plot_bit(root: Path, path: Path):
    """Plot measured width-4 bit-6 nodes; no synthetic trace is shown."""
    _verify(root)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    folder = root / 'screen_w4_tt_1.00_27'
    t, y = D.read_trace(folder / 'trace.txt')
    z = D.read_buffer_trace(folder / 'buffers.txt', t)
    ps = (t - D.edge_time(6)) * 1e12
    mask = (ps >= -10) & (ps <= 195)
    fig, axes = plt.subplots(3, 1, figsize=(10, 8.3), sharex=True, constrained_layout=True)
    series = [((y[:, 3], 'raw x'), (y[:, 4], 'raw y')),
              ((z[:, 0], 'first inverter bx1'), (z[:, 1], 'memory set input bx'),
               (z[:, 3], 'memory reset input by')),
              ((y[:, 5], 'stored q'), (y[:, 6], 'stored qb'))]
    titles = ('Decision: correct polarity before reset (x low, y high)',
              'Buffer: set input never becomes logic-low',
              'Memory: q stays low although this bit should be one')
    colors = ('#086fa1', '#d65b27', '#716078')
    for ax, traces, title in zip(axes, series, titles):
        for j, (values, label) in enumerate(traces):
            ax.plot(ps[mask], values[mask], color=colors[j], lw=1.8, label=label)
        ax.axhline(.9, color='#555555', ls='--', lw=.8, label='logic threshold')
        ax.axvspan(88, 98, color='#1d77a5', alpha=.12)
        ax.axvspan(110, 190, color='#389664', alpha=.10)
        ax.axvline(100, color='#777777', lw=.8, ls=':')
        ax.set_title(title, loc='left', fontsize=11)
        ax.set_ylabel('Voltage (V)')
        ax.set_ylim(-.22, 2.05)
        ax.grid(alpha=.16)
        ax.legend(loc='upper left', fontsize=8, ncol=2)
    axes[-1].set_xlabel('Time after evaluation edge (ps); dotted line: reset complete')
    fig.suptitle('Entry 107 | measured 4 um / TT / 1.8 V / 27 C | bit 6 expected = 1\n'
                 'Blue band: raw check 88-98 ps; green band: hold check 110-190 ps', fontsize=12)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args(argv)
    result = diagnose(args.source)
    args.out.mkdir(parents=True, exist_ok=False)
    write_json(args.out / 'diagnosis.json', result)
    plot_bit(args.source, args.out / 'bit6_measured.png')
    shutil.copyfile(__file__, args.out / 'analysis_source.py')
    write_json(args.out / 'evidence_sha256.json', {
        p.name: digest(p) for p in sorted(args.out.iterdir()) if p.is_file()})
    print(json.dumps({k: v for k, v in result.items() if k != 'screening'}))
    for row in result['screening']:
        print(json.dumps({k: v for k, v in row.items() if k != 'buffer_bits'}))


if __name__ == '__main__':
    main()
