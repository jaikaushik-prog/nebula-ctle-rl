"""Entry 103 bounded physical-reference prototype (see BIAS_REFERENCE_PLAN.md).

No production integration, RL updates, retry/recalibration, or full-pass claim.
Run once into a new directory with `py -3.13 -m ... --out <new-directory>`.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import itertools
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import time

import numpy as np

from nebula.device.bias_reference import calibration_deck, reference_geometry, physical_reference_deck
from nebula.device.crosscheck import assert_no_silent_failures, parse_scalar, parse_meas
from nebula.device.ngspice_runner import ngspice_path
from nebula.device.sky130_runner import SPICE_DIR, lib_for_device, interpolate_peak_log_f
from nebula.report.product_scope import area_inventory, circuit_signature
from nebula.report.schematic import params_of

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'nebula/product_audits/entry101_fixed490_20260906/design.cir'
NFET = 'sky130_fd_pr__nfet_01v8'
PFET = 'sky130_fd_pr__pfet_01v8'


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def scalar(log, name):
    value = parse_scalar(log, name)
    if value is None or not math.isfinite(value):
        raise ValueError(f'missing/nonfinite scalar: {name}')
    return value


def invoke(deck, folder):
    """Exactly one fresh parse, raw evidence kept even on failure."""
    folder.mkdir(parents=True, exist_ok=False)
    (folder / 'design.cir').write_text(deck, encoding='ascii')
    shutil.copyfile(SPICE_DIR / '.spiceinit', folder / '.spiceinit')
    try:
        run = subprocess.run([str(ngspice_path()), '-b', 'design.cir'], cwd=folder,
                             capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired as exc:
        raw = (exc.stdout or b'') + (exc.stderr or b'')
        (folder / 'ngspice.log').write_text(raw.decode(errors='replace'), encoding='utf-8')
        raise ValueError('ngspice timed out, no retry') from exc
    log = run.stdout + '\n' + run.stderr
    (folder / 'ngspice.log').write_text(log, encoding='utf-8')
    if run.returncode:
        raise ValueError(f'ngspice exit {run.returncode}')
    assert_no_silent_failures(log)
    return log


def corner_deck(deck, process, scale, temp):
    lib = lib_for_device(NFET, real_passives=True, section=process, include_pfet=True)
    result = re.sub(r'^\.lib .*$', lambda _: f'.lib "{lib.as_posix()}" {process}', deck, flags=re.M)
    result = re.sub(r'^\.temp .*$', f'.temp {temp}', result, flags=re.M)
    result = re.sub(r'\bVDD=[-+0-9.eE]+', f'VDD={1.8 * scale:.16g}', result)
    result = result.replace('set noaskquit', 'set noaskquit\nset numdgt=15')
    result = result.replace('\nop\n', f'\nop\nprint v(p_bias)\nprint @m.xbpref.m{PFET}[id] @m.xbpfeed.m{PFET}[id]\n')
    if circuit_signature(result) != circuit_signature(deck):
        raise ValueError('PVT changed circuit geometry or settings')
    return result


def extract(log, folder, vdd):
    ac = np.loadtxt(folder / 'ac.txt')
    if ac.ndim != 2 or ac.shape[1] not in (2, 3) or not np.isfinite(ac).all():
        raise ValueError('missing/nonfinite/unexpected AC data')
    if ac.shape[1] == 3 and not np.all(ac[:, 2] == 0):
        raise ValueError('AC db vector unexpectedly has a nonzero imaginary column')
    peak = interpolate_peak_log_f(ac[:, 0], ac[:, 1])
    if not peak.ok:
        raise ValueError(f'no valid interior peak: {peak.reason}')
    grid_db, grid_hz = parse_meas(log, 'g_pk')
    if (grid_db is None or grid_hz is None or not math.isfinite(grid_hz) or grid_hz <= 0
            or abs(math.log2(grid_hz / peak.f_grid_hz)) > .5 * peak.step_octaves
            or not math.isclose(grid_db, peak.g_grid_db, abs_tol=1e-5)):
        raise ValueError('Python AC peak does not reproduce the SPICE MAX measurement')
    dc, _ = parse_meas(log, 'g_dc')
    nyq, _ = parse_meas(log, 'g_nyq')
    if dc is None or nyq is None or not all(map(math.isfinite, [dc, nyq])):
        raise ValueError('missing finite AC measures')
    result = {
        'reference_current_a': scalar(log, f'@m.xmr.m{NFET}[id]'),
        'tail_current_each_a': scalar(log, f'@m.xmt1.m{NFET}[id]'),
        'pmos_resistor_branch_a': abs(scalar(log, f'@m.xbpref.m{PFET}[id]')),
        'pmos_output_branch_a': abs(scalar(log, f'@m.xbpfeed.m{PFET}[id]')),
        'nbias_v': scalar(log, 'v(nbias)'), 'p_bias_v': scalar(log, 'v(p_bias)'),
        'power_ctle_and_bias_w': -scalar(log, 'i(vdd)') * vdd,
        'noise_vrms': scalar(log, 'inoise_total'),
        'peaking_db': peak.g_db - dc, 'f_peak_hz': peak.f_hz,
        'nyquist_boost_db': nyq - dc,
    }
    if any(result[k] <= 0 for k in ('reference_current_a', 'tail_current_each_a',
                                   'power_ctle_and_bias_w', 'noise_vrms')):
        raise ValueError('nonpositive current/power/noise')
    # Diagnostic statement limits only: no extra target tightness invented here.
    result['s3_s5_s6_only_pass'] = bool(
        3 <= result['peaking_db'] <= 12 and 1.25e9 <= result['f_peak_hz'] <= 2.5e9
        and result['nyquist_boost_db'] > 0 and result['noise_vrms'] < .0015
        and result['power_ctle_and_bias_w'] < .015)
    return result


def startup_deck(deck):
    p = params_of(deck)
    circuit = deck.split('.control')[0]
    circuit = re.sub(r'^Vdd\s+.*$', f"Vdd vdd 0 PWL(0 0 1n 0 21n {p['VDD']:.16g})", circuit, flags=re.M)
    circuit = re.sub(r'^Vcm\s+.*$', f"Vcm cm 0 PWL(0 0 1n 0 21n {p['VCM']:.16g})", circuit, flags=re.M)
    return circuit + '''* External common-mode stimulus ramps with supply; not a VCM generator.
.control
set noaskquit
set numdgt=15
tran 20p 200n
wrdata startup.txt v(nbias) v(p_bias) v(vdd)
meas tran final_nbias FIND v(nbias) AT=200n
quit
.endc
.end
'''


def run(out):
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    source = SOURCE.read_text(encoding='utf-8')
    shutil.copyfile(SOURCE, out / 'source.cir')
    files = [SOURCE, Path(__file__), ROOT / 'nebula/device/bias_reference.py',
             ROOT / 'nebula/device/passives.py', ROOT / 'nebula/BIAS_REFERENCE_PLAN.md',
             ROOT / 'nebula/report/product_scope.py', SPICE_DIR / '.spiceinit']
    write_json(out / 'provenance.json', {
        'inputs': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        'ngspice': str(ngspice_path()), 'max_invocations': 47,
        'scope': 'Physical-bias prototype only; typical passive process; NOT deployed.',
    })
    started, calls, rows = time.monotonic(), 0, []
    try:
        calls += 1
        cal = invoke(calibration_deck(source), out / 'calibration')
        geo = reference_geometry(source, scalar(cal, 'v(p_bias)'))
        write_json(out / 'geometry.json', asdict(geo))
        deck = physical_reference_deck(source, geo)
        (out / 'design.cir').write_text(deck, encoding='ascii')
        write_json(out / 'area_inventory.json', area_inventory(deck))
        for process, scale, temp in itertools.product(('tt', 'ss', 'ff', 'sf', 'fs'), (.95, 1., 1.05), (0, 27, 125)):
            key = f'{process}_{scale:.2f}_{temp}'
            row = dict(key=key, process=process, vdd_scale=scale, temp_c=temp, ok=False)
            try:
                cir = corner_deck(deck, process, scale, temp)
                row['circuit_signature'] = circuit_signature(cir)
                calls += 1
                log = invoke(cir, out / key)
                row.update(extract(log, out / key, 1.8 * scale), ok=True)
            except (ValueError, RuntimeError, OSError) as exc:
                row['error'] = str(exc)
            rows.append(row)
            with (out / 'corners.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(row, allow_nan=False) + '\n')
            print(f'{len(rows)}/45 {key}: ' + ('measured' if row['ok'] else row['error'][:120]), flush=True)
        startup = {'ok': False}
        try:
            calls += 1
            log = invoke(startup_deck(deck), out / 'startup')
            final, _ = parse_meas(log, 'final_nbias')
            nominal = next(r for r in rows if r['key'] == 'tt_1.00_27')
            if final is None or not math.isfinite(final) or not nominal['ok']:
                raise ValueError('startup final value or nominal comparison unavailable')
            startup.update(final_nbias_v=final, nominal_nbias_v=nominal['nbias_v'],
                           relative_settling_error=abs(final / nominal['nbias_v'] - 1), ok=True)
        except (ValueError, RuntimeError, OSError) as exc:
            startup['error'] = str(exc)
        valid = [r for r in rows if r['ok']]
        fields = ('reference_current_a', 'power_ctle_and_bias_w', 'noise_vrms', 'peaking_db', 'f_peak_hz')
        summary = dict(n_expected=45, n_measured=len(valid),
                       n_s3_s5_s6_only_pass=sum(r['s3_s5_s6_only_pass'] for r in valid),
                       ranges={k: [min(r[k] for r in valid), max(r[k] for r in valid)] for k in fields} if valid else {},
                       startup=startup, full_product_compliance=False, deployed=False,
                       not_verified=['HD3', 'eye', 'physical DFE', 'Rs/Cs selector', 'common-mode generator',
                                     'independent passive corners', 'mismatch', 'layout area/parasitics'])
    except (ValueError, RuntimeError, OSError) as exc:
        summary = {'error': str(exc), 'full_product_compliance': False, 'deployed': False}
    summary.update(invocations=calls, elapsed_s=time.monotonic() - started)
    write_json(out / 'summary.json', summary)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    result = run(parser.parse_args().out)
    raise SystemExit(0 if result.get('n_measured') == 45 and result.get('startup', {}).get('ok') else 1)
