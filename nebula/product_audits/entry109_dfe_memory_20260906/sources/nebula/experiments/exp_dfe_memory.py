"""Entry 109: exactly one clean-input nominal memory diagnostic, no sweep."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import shutil
import time

from nebula.device import dfe_hardware as D, dfe_memory_probe as M
from nebula.experiments import exp_physical_bias as P
from nebula.experiments.exp_dfe_slicer import ROOT, digest
from nebula.experiments.runlock import hold, stamp
from nebula.link.config import LinkConfig


def run(out: Path):
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    with hold('dfe_slicer'):
        cfg = LinkConfig(channel_loss_db_at_nyquist=7.5)
        bits = D.pattern(cfg)
        paths = ('nebula/DFE_MEMORY_PLAN.md', 'nebula/DFE_HARDWARE_PLAN.md',
                 'nebula/device/dfe_hardware.py', 'nebula/device/dfe_memory_probe.py',
                 'nebula/experiments/exp_dfe_memory.py', 'nebula/experiments/exp_physical_bias.py',
                 'nebula/experiments/exp_dfe_slicer.py', 'nebula/experiments/runlock.py',
                 'nebula/tests/test_dfe_memory_probe.py', 'nebula/device/crosscheck.py',
                 'nebula/device/sky130_runner.py', 'nebula/device/ngspice_runner.py',
                 'nebula/common/types.py', 'nebula/link/config.py', 'nebula/device/spice/.spiceinit')
        for rel in paths:
            dest = out / 'sources' / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, dest)
        rendered = M.deck(bits)
        actual = [line for line in rendered.splitlines() if line.startswith('X')]
        if actual != M.memory_lines():
            raise ValueError('rendered memory differs from canonical existing instances')
        signature = hashlib.sha256('\n'.join(actual).encode('ascii')).hexdigest()
        P.write_json(out / 'config.json', {
            'entry': 109, 'seed': cfg.seed, 'bits': bits.tolist(), 'max_calls': 1,
            'process': 'tt', 'vdd_v': M.VDD, 'temperature_c': 27,
            'mos_signature': signature, 'ideal_test_inputs': True,
            'ctle_connected': False, 'comparator_connected': False,
            'buffers_connected': False, 'feedback_connected': False, **stamp()})
        folder = out / 'clean_tt_1.00_27'
        started = time.perf_counter()
        try:
            P.invoke(rendered, folder)
            t, y = M.read_trace(folder / 'trace.txt')
            result = M.analyze(t, y, bits)
            result['instrument_ok'] = True
        except Exception as exc:
            result = {'memory_hold_pass': False, 'instrument_ok': False,
                      'fail_reason': f'{type(exc).__name__}: {exc}',
                      'hardware_dfe_complete': False, 'full_receiver_verified': False}
            folder.mkdir(parents=True, exist_ok=True)
        result.update(entry=109, spice_calls=1, wall_seconds=time.perf_counter()-started,
                      mos_signature=signature, geometry=M.geometry(),
                      status='CLEAN_MEMORY_PASS_NOT_DFE' if result['memory_hold_pass'] else 'CLEAN_MEMORY_FAILED')
        P.write_json(folder / 'result.json', result)
        P.write_json(out / 'summary.json', result)
        P.write_json(out / 'evidence_sha256.json', {
            p.relative_to(out).as_posix(): digest(p) for p in sorted(out.rglob('*')) if p.is_file()})
        print(f'{result["status"]}: {result.get("correct_bits")}/32 held bits, '
              f'1 call in {result["wall_seconds"]:.3f} s', flush=True)
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.out)
    raise SystemExit(0 if result['memory_hold_pass'] else 1)
