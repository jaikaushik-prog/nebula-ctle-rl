"""Entry 106, max 48 fresh calls, no retry or production adoption."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shutil
import time

from nebula.common.types import Corner, all_corners
from nebula.device import dfe_hardware as D
from nebula.experiments import exp_physical_bias as P
from nebula.experiments.runlock import hold
from nebula.link.config import LinkConfig

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'nebula/product_demo/physical_bias_9db_1p9ghz_20260906/physical_evidence'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_common_mode(source, corner):
    key = f'{corner.process}_{corner.vdd_scale:.2f}_{corner.temp_c:g}/ac_noise/ngspice.log'
    manifest = json.loads((source / 'evidence_sha256.json').read_text(encoding='utf-8'))
    path = source / key
    if digest(path) != manifest.get(key):
        raise ValueError(f'common-mode source hash mismatch: {key}')
    return P.scalar(path.read_text(encoding='utf-8'), 'v(outp)'), key, digest(path)


def schedule(evaluate):
    """Evaluator returns failure values; no hidden retry/fallback after PVT."""
    nominal = Corner('tt', 1, 27)
    screening = []
    for width in D.WIDTHS_UM:
        screening.append({'width_um': width, 'result': evaluate(width, nominal, 'screen')})
    eligible = [row['width_um'] for row in screening if row['result']['block_pass']]
    selected = min(eligible) if eligible else None
    corners = []
    if selected is not None:
        for corner in all_corners():
            corners.append({'corner': asdict(corner),
                            'result': evaluate(selected, corner, 'pvt')})
    return {'screening': screening, 'selected_width_um': selected, 'corners': corners,
            'all_corner_block_pass': bool(len(corners) == 45 and
                                          all(r['result']['block_pass'] for r in corners)),
            'hardware_dfe_complete': False, 'full_receiver_verified': False}


def run(out: Path):
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    with hold('dfe_slicer'):
        cfg = LinkConfig(channel_loss_db_at_nyquist=7.5)
        bits = D.pattern(cfg)
        snapshots = out / 'sources'
        snapshots.mkdir()
        paths = ('nebula/DFE_HARDWARE_PLAN.md', 'nebula/device/dfe_hardware.py',
                 'nebula/experiments/exp_dfe_slicer.py', 'nebula/tests/test_dfe_hardware.py',
                 'nebula/experiments/exp_physical_bias.py', 'nebula/device/crosscheck.py',
                 'nebula/device/sky130_runner.py', 'nebula/common/types.py',
                 'nebula/link/config.py', 'nebula/device/spice/.spiceinit')
        for rel in paths:
            destination = snapshots / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, destination)
        P.write_json(out / 'config.json', {'seed': cfg.seed, 'bits': bits.tolist(),
                     'widths_um': D.WIDTHS_UM, 'max_calls': 48,
                     'source': str(SOURCE), 'source_manifest_sha256': digest(SOURCE / 'evidence_sha256.json'),
                     'clock_external': True, 'ctle_connected': False,
                     'input_differential_pp_v': .1})
        started, calls = time.perf_counter(), 0
        def evaluate(width, corner, phase):
            nonlocal calls
            folder = out / f'{phase}_w{width}_{corner.process}_{corner.vdd_scale:.2f}_{corner.temp_c:g}'
            cm, key, sha = source_common_mode(SOURCE, corner)
            rendered = D.deck(width, corner, cm, bits)
            calls += 1
            assert calls <= 48
            try:
                P.invoke(rendered, folder)
                t, y = D.read_trace(folder / 'trace.txt')
                result = D.analyze(t, y, bits, 1.8 * corner.vdd_scale, cm)
                result['instrument_ok'] = True
            except Exception as exc:
                result = {'block_pass': False, 'instrument_ok': False,
                          'fail_reason': f'{type(exc).__name__}: {exc}',
                          'hardware_dfe_complete': False, 'full_receiver_verified': False}
                folder.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / key, folder / 'source_ctle_ac_noise.log')
            result.update({'common_mode_v': cm, 'common_mode_source_key': key,
                           'common_mode_source_sha256': sha, 'geometry': D.geometry(width)})
            P.write_json(folder / 'result.json', result)
            print(f'{calls}/48 {folder.name}: block_pass={result["block_pass"]}, '
                  f'correct={result.get("correct_bits")}/32, instrument={result["instrument_ok"]}', flush=True)
            return result
        result = schedule(evaluate)
        result.update({'spice_calls': calls, 'wall_seconds': time.perf_counter() - started,
                       'status': 'BLOCK_PASS_NOT_DFE' if result['all_corner_block_pass'] else 'BLOCK_GATE_FAILED'})
        P.write_json(out / 'summary.json', result)
        P.write_json(out / 'evidence_sha256.json', {
            p.relative_to(out).as_posix(): digest(p) for p in sorted(out.rglob('*')) if p.is_file()})
        print(f'{result["status"]}: {calls} calls in {result["wall_seconds"]:.3f} s', flush=True)
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    summary = run(args.out)
    raise SystemExit(0 if summary['all_corner_block_pass'] else 1)
