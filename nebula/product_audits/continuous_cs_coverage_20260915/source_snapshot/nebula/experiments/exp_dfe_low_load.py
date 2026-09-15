"""Entry 111: two approved peripheral widths, TT only, no automatic follow-up."""
import argparse
import hashlib
from pathlib import Path
import shutil
import time

from nebula.common.types import Corner
from nebula.device import dfe_hardware as D
from nebula.device import dfe_voltage_audit as V
from nebula.experiments import exp_physical_bias as P
from nebula.experiments.exp_dfe_drive import mos_signature
from nebula.experiments.exp_dfe_slicer import ROOT, SOURCE, digest, source_common_mode
from nebula.experiments.runlock import hold, stamp
from nebula.link.config import LinkConfig


def schedule(evaluate):
    rows = [{'chain_width_um': width, 'result': evaluate(width)} for width in D.CHAIN_WIDTHS_UM]
    return {'entry': 111, 'screening': rows, 'selected_width_um': None, 'pvt_calls': 0,
            'hardware_dfe_complete': False, 'full_receiver_verified': False}


def run(out: Path):
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    with hold('dfe_slicer'):
        cfg = LinkConfig(channel_loss_db_at_nyquist=7.5)
        bits = D.pattern(cfg)
        paths = ('nebula/DFE_LOW_LOAD_PLAN.md', 'nebula/DFE_HARDWARE_PLAN.md',
                 'nebula/DFE_BUFFER_PLAN.md', 'nebula/device/dfe_hardware.py',
                 'nebula/device/dfe_voltage_audit.py', 'nebula/experiments/exp_dfe_low_load.py',
                 'nebula/experiments/exp_dfe_drive.py', 'nebula/experiments/exp_dfe_slicer.py',
                 'nebula/experiments/exp_physical_bias.py', 'nebula/experiments/runlock.py',
                 'nebula/tests/test_dfe_low_load.py', 'nebula/device/crosscheck.py',
                 'nebula/device/sky130_runner.py', 'nebula/device/ngspice_runner.py',
                 'nebula/common/types.py', 'nebula/link/config.py', 'nebula/device/spice/.spiceinit')
        for rel in paths:
            dest = out / 'sources' / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, dest)
        P.write_json(out / 'config.json', {'entry': 111, 'bits': bits.tolist(), 'seed': cfg.seed,
            'chain_widths_um': D.CHAIN_WIDTHS_UM, 'chain_nf': 1, 'core_width_um': 4,
            'max_calls': 2, 'source': str(SOURCE),
            'source_manifest_sha256': digest(SOURCE / 'evidence_sha256.json'),
            'clock_external': True, 'ctle_connected': False, **stamp()})
        corner = Corner('tt', 1, 27)
        cm, key, sha = source_common_mode(SOURCE, corner)
        started, calls = time.perf_counter(), 0

        def evaluate(width):
            nonlocal calls
            devices = D.dut_lines(4, buffered=True, chain_width_um=width)
            rendered = D.deck(4, corner, cm, bits, buffered=True, chain_width_um=width)
            signature = mos_signature(rendered)
            if signature != hashlib.sha256('\n'.join(devices).encode('ascii')).hexdigest():
                raise ValueError('rendered DUT changed canonical instances')
            folder = out / f'screen_chain{width}_tt_1.00_27'
            calls += 1
            if calls > 2:
                raise RuntimeError('two-call budget exhausted')
            try:
                P.invoke(rendered, folder)
                t, y = D.read_trace(folder / 'trace.txt')
                result = D.analyze(t, y, bits, 1.8, cm)
                D.read_buffer_trace(folder / 'buffers.txt', t)
                nodes = V.read_nodes(folder / 'terminals.txt', D.terminal_nodes(devices), t)
                result.update(voltage_audit=V.audit(devices, nodes), instrument_ok=True,
                    buffer_trace_valid=True, terminal_trace_valid=True,
                    raw_correct_bits=sum(b['raw_min_logic_margin_v'] > 0 for b in result['bits']),
                    held_correct_bits=sum(b['held_min_logic_margin_v'] > 0 for b in result['bits']))
            except Exception as exc:
                result = {'block_pass': False, 'instrument_ok': False,
                    'fail_reason': f'{type(exc).__name__}: {exc}',
                    'hardware_dfe_complete': False, 'full_receiver_verified': False}
                folder.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / key, folder / 'source_ctle_ac_noise.log')
            result.update(chain_width_um=width, mos_signature=signature, common_mode_v=cm,
                common_mode_source_key=key, common_mode_source_sha256=sha,
                geometry=D.geometry(4, buffered=True, chain_width_um=width))
            P.write_json(folder / 'result.json', result)
            print(f'{calls}/2 chain W={width}: logic={result["block_pass"]}, '
                  f'raw={result.get("raw_correct_bits")}/32 held={result.get("held_correct_bits")}/32 '
                  f'ranges={result.get("voltage_audit", {}).get("documented_ranges_ok")}', flush=True)
            return result

        result = schedule(evaluate)
        result.update(spice_calls=calls, wall_seconds=time.perf_counter()-started,
                      status='TWO_TT_CHECKS_FINISHED_NOT_DFE')
        P.write_json(out / 'summary.json', result)
        P.write_json(out / 'evidence_sha256.json', {
            p.relative_to(out).as_posix(): digest(p) for p in sorted(out.rglob('*')) if p.is_file()})
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    result = run(parser.parse_args().out)
    # A logic pass alone cannot produce a green process exit after an excursion.
    accepted = any(s['result']['block_pass'] and
                   s['result'].get('voltage_audit', {}).get('documented_ranges_ok', False)
                   for s in result['screening'])
    raise SystemExit(0 if accepted else 1)
