"""Entry 124 registered connected CTLE/DFE screen; not receiver signoff."""
import argparse
import json
from pathlib import Path
import shutil
import time

from nebula.common.types import Corner, all_corners
from nebula.device import dfe_connected as F, dfe_hardware as D, dfe_voltage_audit as V
from nebula.experiments import exp_physical_bias as P
from nebula.experiments.exp_dfe_slicer import ROOT, digest
from nebula.experiments.runlock import hold, stamp
from nebula.link.config import LinkConfig


def envelope(audit):
    return audit['max_abs_vds_vgs_v'] <= 1.95 and all(
        r['vbs']['below_samples'] == r['vbs']['above_samples'] == 0 for r in audit['devices'])


def valid(r):
    return (r.get('instrument_ok', False) and r.get('new_dfe_voltage_audit', {}).get('documented_ranges_ok', False)
            and r.get('whole_circuit_voltage_envelope_pass', False))


def accepted(r):
    return (valid(r) and r['logic_pass'] and r['sampled_eye_height_v'] > .1
            and r['minimum_sample_signed_v'] > 0 and 0 < r['ctle_plus_dfe_vdd_power_w'] < .015)


def verify_recovery():
    root = ROOT/'nebula/product_audits/entry123_dfe_cml_recovery_20260909'
    manifest = json.loads((root/'evidence_sha256.json').read_text())
    summary = json.loads((root/'summary.json').read_text())
    cml = 'sources/nebula/device/dfe_cml.py'
    if (digest(root/'summary.json') != manifest['summary.json']
            or digest(ROOT/'nebula/device/dfe_cml.py') != manifest[cml]
            or not summary['standalone_pvt_pass'] or summary['selected_width_um'] != 8
            or len(summary['pvt']) != 45
            or {r['corner'] for r in summary['pvt']} != {str(c) for c in all_corners()}
            or not all(r['result']['block_pass'] and r['result']['correct_bits'] == 32
                       and r['result']['voltage_audit']['documented_ranges_ok'] for r in summary['pvt'])):
        raise ValueError('verified fixed-width CML recovery prerequisite changed or missing')
    return digest(root/'summary.json')


def schedule(evaluate):
    tt = Corner('tt', 1, 27)
    baseline = [{'phase_ui': p, 'result': evaluate(tt, 7.5, p, 0, 1, 'phase')}
                for p in F.PHASES_UI]
    good = [r for r in baseline if valid(r['result'])]
    result = {'entry': 124, 'baselines': baseline, 'candidates': [], 'selected': None,
              'diagnostic_channels': [], 'pvt': [], 'primary_channel_pvt_pass': False,
              'full_receiver_verified': False}
    if not good:
        return result
    best = max(good, key=lambda r: (r['result']['sampled_eye_height_v'], -r['phase_ui']))
    phase = best['phase_ui']
    candidates = [{'code': code, 'sign': sign,
        'result': evaluate(tt, 7.5, phase, code, sign, 'tap')}
        for code in F.TAP_CODES for sign in (1, -1)]
    result['candidates'] = candidates
    winners = []
    for r in candidates:
        other = next(c for c in candidates if c['code'] == r['code'] and c['sign'] == -r['sign'])
        if accepted(r['result']) and valid(other['result']):
            eye = r['result']['sampled_eye_height_v']
            r['eye_improvement_over_disabled_v'] = eye-best['result']['sampled_eye_height_v']
            r['eye_improvement_over_reversed_v'] = eye-other['result']['sampled_eye_height_v']
            if min(r['eye_improvement_over_disabled_v'], r['eye_improvement_over_reversed_v']) > 1e-6:
                winners.append(r)
    if not winners:
        return result
    winner = max(winners, key=lambda r: (r['result']['sampled_eye_height_v'], -r['code'], r['sign']))
    code, sign = winner['code'], winner['sign']
    result['selected'] = {'phase_ui': phase, 'code': code, 'sign': sign}
    result['diagnostic_channels'] = [{'loss_db': loss,
        'result': evaluate(tt, loss, phase, code, sign, 'channel')} for loss in (3., 12.)]
    result['pvt'] = [{'corner': str(c), 'result': evaluate(c, 7.5, phase, code, sign, 'pvt')}
                     for c in all_corners()]
    result['primary_channel_pvt_pass'] = all(accepted(r['result']) for r in result['pvt'])
    return result


def run(out):
    recovery_sha = verify_recovery()
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    with hold('dfe_slicer'):
        paths = ('nebula/DFE_CONNECTED_PLAN.md', 'nebula/device/dfe_connected.py',
                 'nebula/experiments/exp_dfe_connected.py', 'nebula/tests/test_dfe_connected.py',
                 'nebula/device/dfe_cml.py', 'nebula/device/dfe_hardware.py',
                 'nebula/device/dfe_voltage_audit.py', 'nebula/device/passives.py',
                 'nebula/experiments/exp_physical_bias.py', 'nebula/experiments/exp_dfe_slicer.py',
                 'nebula/experiments/runlock.py', 'nebula/device/crosscheck.py',
                 'nebula/device/sky130_runner.py', 'nebula/device/ngspice_runner.py',
                 'nebula/common/types.py', 'nebula/link/config.py', 'nebula/link/channel.py',
                 'nebula/link/tx.py', 'nebula/device/spice/.spiceinit',
                 'nebula/report/product_scope.py', 'nebula/report/schematic.py')
        for rel in paths:
            target = out/'sources'/rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT/rel, target)
        shutil.copyfile(F.SOURCE/'design.cir', out/'source_ctle.cir')
        cfg = LinkConfig(channel_loss_db_at_nyquist=7.5)
        bits = F.pattern(cfg)
        P.write_json(out/'config.json', {'entry': 124, 'max_calls': 58, 'bits': bits.tolist(),
            'seed': cfg.seed, 'phases_ui': F.PHASES_UI, 'tap_codes': F.TAP_CODES,
            'source_ctle_sha256': digest(F.SOURCE/'design.cir'),
            'recovery_summary_sha256': recovery_sha, 'geometry': F.geometry(),
            'clock_and_control_external': True, 'ctle_connected': True, **stamp()})
        calls, started = 0, time.perf_counter()
        def evaluate(corner, loss, phase, code, sign, stage):
            nonlocal calls
            calls += 1
            if calls > 58:
                raise RuntimeError('registered 58-call budget exceeded')
            folder = out/f'{stage}_{corner}_loss{loss:g}_phase{phase:g}_code{code}_sign{sign}'
            try:
                cfg = LinkConfig(channel_loss_db_at_nyquist=loss)
                rendered = F.deck(corner, cfg, bits, phase, code, sign)
                P.invoke(rendered, folder)
                t, y = F.read_trace(folder/'trace.txt')
                r = F.analyze(t, y, bits, cfg, phase, 1.8*corner.vdd_scale, code=code)
                mos = F.all_mos(rendered)
                nodes = V.read_nodes(folder/'terminals.txt', D.terminal_nodes(mos), t)
                whole = V.audit(mos, nodes)
                new = V.audit(F.extra_mos(sign), nodes)
                r.update(instrument_ok=True, new_dfe_voltage_audit=new,
                    whole_circuit_voltage_audit=whole, whole_circuit_voltage_envelope_pass=envelope(whole))
            except Exception as exc:
                folder.mkdir(parents=True, exist_ok=True)
                r = {'instrument_ok': False, 'logic_pass': False,
                     'fail_reason': f'{type(exc).__name__}: {exc}', 'full_receiver_verified': False}
            r.update(code=code, sign=sign, phase_ui=phase, loss_db=loss, corner=str(corner))
            r['signal_gate_pass'] = accepted(r)
            P.write_json(folder/'result.json', r)
            print(f'{calls}/58 {folder.name}: signal={accepted(r)} bits={r.get("correct_bits")}/64 '
                  f'eye={r.get("sampled_eye_height_v")} error={r.get("fail_reason")}', flush=True)
            return r
        result = schedule(evaluate)
        result.update(spice_calls=calls, wall_seconds=time.perf_counter()-started)
        P.write_json(out/'summary.json', result)
        P.write_json(out/'evidence_sha256.json', {
            p.relative_to(out).as_posix(): digest(p) for p in sorted(out.rglob('*')) if p.is_file()})
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    raise SystemExit(0 if run(parser.parse_args().out)['primary_channel_pvt_pass'] else 1)
