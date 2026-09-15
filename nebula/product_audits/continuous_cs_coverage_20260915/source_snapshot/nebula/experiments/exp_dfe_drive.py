"""Entry 108: four approved drive pairs, then one fixed 45-PVT gate at most."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
from pathlib import Path
import shutil
import time

from nebula.common.types import Corner, all_corners
from nebula.device import dfe_hardware as D
from nebula.experiments import exp_physical_bias as P
from nebula.experiments.exp_dfe_slicer import ROOT, SOURCE, digest, source_common_mode
from nebula.experiments.runlock import hold, stamp
from nebula.link.config import LinkConfig


def mos_signature(deck):
    lines = [line for line in deck.splitlines() if line.startswith('X')]
    if len(lines) != 27 or len({line.split()[0] for line in lines}) != 27:
        raise ValueError('expected 27 unique MOS instances')
    return hashlib.sha256('\n'.join(lines).encode('ascii')).hexdigest()


def schedule(evaluate):
    screening = [{'drive_um': pair, 'result': evaluate(pair, Corner('tt', 1, 27), 'screen')}
                 for pair in D.BUFFER_DRIVE_PAIRS_UM]
    passing = [row['drive_um'] for row in screening if row['result']['block_pass']]
    selected = min(passing, key=lambda pair: (sum(pair), pair)) if passing else None
    corners = []
    if selected is not None:
        for corner in all_corners():
            corners.append({'corner': asdict(corner), 'result': evaluate(selected, corner, 'pvt')})
    return {'entry': 108, 'screening': screening, 'selected_drive_um': selected, 'corners': corners,
            'all_corner_block_pass': bool(len(corners) == 45 and all(r['result']['block_pass'] for r in corners)),
            'hardware_dfe_complete': False, 'full_receiver_verified': False}


def run(out: Path):
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    # Shared lock with earlier DFE experiments, not a parallel new lock name.
    with hold('dfe_slicer'):
        cfg = LinkConfig(channel_loss_db_at_nyquist=7.5)
        bits = D.pattern(cfg)
        paths = ('nebula/DFE_DRIVE_PLAN.md', 'nebula/DFE_BUFFER_PLAN.md', 'nebula/DFE_HARDWARE_PLAN.md',
                 'nebula/device/dfe_hardware.py', 'nebula/experiments/exp_dfe_drive.py',
                 'nebula/experiments/exp_dfe_slicer.py', 'nebula/experiments/exp_physical_bias.py',
                 'nebula/tests/test_dfe_drive.py', 'nebula/device/crosscheck.py',
                 'nebula/device/sky130_runner.py', 'nebula/device/ngspice_runner.py',
                 'nebula/common/types.py', 'nebula/link/config.py', 'nebula/device/spice/.spiceinit')
        for rel in paths:
            dest = out / 'sources' / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, dest)
        P.write_json(out / 'config.json', {
            'entry': 108, 'seed': cfg.seed, 'bits': bits.tolist(), 'core_width_um': 4,
            'drive_pair_order': ['first_stage_pmos_width_um', 'second_stage_nmos_width_um'],
            'drive_pairs_um': D.BUFFER_DRIVE_PAIRS_UM, 'max_calls': 49,
            'source': str(SOURCE), 'source_manifest_sha256': digest(SOURCE / 'evidence_sha256.json'),
            'clock_external': True, 'ctle_connected': False, **stamp()})
        expected_signatures = {
            pair: hashlib.sha256('\n'.join(D.dut_lines(4, buffered=True, buffer_drive_um=pair)).encode('ascii')).hexdigest()
            for pair in D.BUFFER_DRIVE_PAIRS_UM}
        started, calls = time.perf_counter(), 0

        def evaluate(pair, corner, phase):
            nonlocal calls
            cm, key, sha = source_common_mode(SOURCE, corner)
            rendered = D.deck(4, corner, cm, bits, buffered=True, buffer_drive_um=pair)
            signature = mos_signature(rendered)
            if signature != expected_signatures[pair]:
                raise ValueError('PVT changed fixed MOS circuit')
            folder = out / f'{phase}_p{pair[0]}_n{pair[1]}_{corner.process}_{corner.vdd_scale:.2f}_{corner.temp_c:g}'
            calls += 1
            if calls > 49:
                raise RuntimeError('registered 49-call budget exhausted')
            try:
                P.invoke(rendered, folder)
                t, y = D.read_trace(folder / 'trace.txt')
                result = D.analyze(t, y, bits, 1.8 * corner.vdd_scale, cm)
                D.read_buffer_trace(folder / 'buffers.txt', t)
                result.update(instrument_ok=True, buffer_trace_valid=True,
                              raw_correct_bits=sum(b['raw_min_logic_margin_v'] > 0 for b in result['bits']),
                              held_correct_bits=sum(b['held_min_logic_margin_v'] > 0 for b in result['bits']))
            except Exception as exc:
                result = {'block_pass': False, 'instrument_ok': False,
                          'fail_reason': f'{type(exc).__name__}: {exc}',
                          'hardware_dfe_complete': False, 'full_receiver_verified': False}
                folder.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / key, folder / 'source_ctle_ac_noise.log')
            result.update(drive_um=pair, mos_signature=signature, common_mode_v=cm,
                          common_mode_source_key=key, common_mode_source_sha256=sha,
                          geometry=D.geometry(4, buffered=True, buffer_drive_um=pair))
            P.write_json(folder / 'result.json', result)
            print(f'{calls}/49 {folder.name}: pass={result["block_pass"]}, '
                  f'raw={result.get("raw_correct_bits")}/32 held={result.get("held_correct_bits")}/32 '
                  f'instrument={result["instrument_ok"]}', flush=True)
            return result

        result = schedule(evaluate)
        result.update(spice_calls=calls, wall_seconds=time.perf_counter() - started,
                      status='BLOCK_PASS_NOT_DFE' if result['all_corner_block_pass'] else 'BLOCK_GATE_FAILED')
        P.write_json(out / 'summary.json', result)
        P.write_json(out / 'evidence_sha256.json', {
            p.relative_to(out).as_posix(): digest(p) for p in sorted(out.rglob('*')) if p.is_file()})
        print(f'{result["status"]}: {calls} calls in {result["wall_seconds"]:.3f} s', flush=True)
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.out)
    raise SystemExit(0 if result['all_corner_block_pass'] else 1)
