"""Entry 122 registered three-size CML screen and conditional fixed-size PVT."""
import argparse
from pathlib import Path
import shutil
import time

from nebula.common.types import Corner, all_corners
from nebula.device import dfe_cml as C, dfe_hardware as D, dfe_voltage_audit as V
from nebula.experiments import exp_physical_bias as P
from nebula.experiments.exp_dfe_slicer import ROOT, SOURCE, digest, source_common_mode
from nebula.experiments.runlock import hold, stamp
from nebula.link.config import LinkConfig


def accepted(result):
    return result.get('block_pass', False) and result.get('voltage_audit', {}).get('documented_ranges_ok', False)


def schedule(evaluate):
    rows = [{'width_um': w, 'result': evaluate(w, Corner('tt', 1, 27), 'screen')}
            for w in C.WIDTHS_UM]
    selected = next((r['width_um'] for r in rows if accepted(r['result'])), None)
    pvt = [] if selected is None else [
        {'corner': str(c), 'result': evaluate(selected, c, 'pvt')} for c in all_corners()]
    return {'entry': 122, 'screening': rows, 'selected_width_um': selected, 'pvt': pvt,
            'standalone_pvt_pass': len(pvt) == 45 and all(accepted(r['result']) for r in pvt),
            'hardware_dfe_complete': False, 'full_receiver_verified': False}


def recovery_schedule(evaluate):
    corners = (Corner('ss', .95, 125), Corner('fs', .95, 125), Corner('ff', 1.05, 0))
    rows = [{'width_um': w, 'corners': [
        {'corner': str(c), 'result': evaluate(w, c, 'screen')} for c in corners]}
        for w in (8, 16)]
    selected = next((r['width_um'] for r in rows
                     if all(accepted(c['result']) for c in r['corners'])), None)
    pvt = [] if selected is None else [
        {'corner': str(c), 'result': evaluate(selected, c, 'pvt')} for c in all_corners()]
    return {'entry': 123, 'screening': rows, 'selected_width_um': selected, 'pvt': pvt,
            'standalone_pvt_pass': len(pvt) == 45 and all(accepted(r['result']) for r in pvt),
            'hardware_dfe_complete': False, 'full_receiver_verified': False}


def run(out, *, recovery=False):
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    with hold('dfe_slicer'):
        entry, budget = (123, 51) if recovery else (122, 48)
        cfg = LinkConfig(channel_loss_db_at_nyquist=7.5)
        bits = D.pattern(cfg)
        paths = ('nebula/DFE_CML_PLAN.md', 'nebula/device/dfe_cml.py',
                 'nebula/experiments/exp_dfe_cml.py', 'nebula/tests/test_dfe_cml.py',
                 'nebula/device/dfe_hardware.py', 'nebula/device/dfe_voltage_audit.py',
                 'nebula/device/passives.py', 'nebula/experiments/exp_dfe_slicer.py',
                 'nebula/experiments/exp_physical_bias.py', 'nebula/experiments/runlock.py',
                 'nebula/device/crosscheck.py', 'nebula/device/sky130_runner.py',
                 'nebula/device/ngspice_runner.py', 'nebula/common/types.py',
                 'nebula/link/config.py', 'nebula/device/spice/.spiceinit')
        if recovery:
            paths += ('nebula/DFE_CML_RECOVERY_PLAN.md', 'nebula/tests/test_dfe_cml_recovery.py')
        for rel in paths:
            dest = out / 'sources' / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, dest)
        P.write_json(out/'config.json', {'entry': entry, 'max_calls': budget,
            'bits': bits.tolist(), 'seed': cfg.seed, 'widths_um': (8, 16) if recovery else C.WIDTHS_UM,
            'source_manifest_sha256': digest(SOURCE/'evidence_sha256.json'),
            'clock_external': True, 'ctle_connected': False, **stamp()})
        started, calls = time.perf_counter(), 0
        def evaluate(width, corner, phase):
            nonlocal calls
            calls += 1
            if calls > budget:
                raise RuntimeError('registered call budget exhausted')
            folder = out / f'{phase}_w{width}_{corner}'
            try:
                cm, key, sha = source_common_mode(SOURCE, corner)
                rendered = C.deck(width, corner, cm, bits)
                P.invoke(rendered, folder)
                t, y = C.read_trace(folder/'trace.txt')
                r = C.analyze(t, y, bits, 1.8*corner.vdd_scale, cm)
                mos = C.mos_lines(width)
                nodes = V.read_nodes(folder/'terminals.txt', D.terminal_nodes(mos), t)
                r.update(voltage_audit=V.audit(mos, nodes), instrument_ok=True,
                         common_mode_v=cm, common_mode_source_key=key, common_mode_source_sha256=sha)
                shutil.copyfile(SOURCE/key, folder/'source_ctle_ac_noise.log')
            except Exception as exc:
                folder.mkdir(parents=True, exist_ok=True)
                r = {'block_pass': False, 'instrument_ok': False,
                     'fail_reason': f'{type(exc).__name__}: {exc}'}
            r.update(width_um=width, geometry=C.geometry(width),
                     hardware_dfe_complete=False, full_receiver_verified=False)
            P.write_json(folder/'result.json', r)
            print(f'{calls}/{budget} {phase} W={width} {corner}: accepted={accepted(r)}, '
                  f'bits={r.get("correct_bits")}/32 error={r.get("fail_reason")}', flush=True)
            return r
        result = (recovery_schedule if recovery else schedule)(evaluate)
        result.update(spice_calls=calls, wall_seconds=time.perf_counter()-started)
        P.write_json(out/'summary.json', result)
        P.write_json(out/'evidence_sha256.json', {
            p.relative_to(out).as_posix(): digest(p) for p in sorted(out.rglob('*')) if p.is_file()})
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--recovery', action='store_true', help='Entry 123 registered corner screen')
    args = parser.parse_args()
    raise SystemExit(0 if run(args.out, recovery=args.recovery)['standalone_pvt_pass'] else 1)
