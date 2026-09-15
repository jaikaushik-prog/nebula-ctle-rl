"""Recover Entry 103's printed-current label error WITHOUT further SPICE calls.

Original failed parser journal/summary are preserved. This writes separate
reparsed evidence, rescans raw logs, and verifies each fixed circuit signature.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

from nebula.experiments.exp_physical_bias import extract, write_json
from nebula.device.crosscheck import assert_no_silent_failures, parse_meas
from nebula.report.product_scope import circuit_signature


def reparse(folder):
    folder = Path(folder).resolve()
    paths = [folder / x for x in ('corners_reparsed.jsonl', 'summary_reparsed.json', 'reparse_provenance.json')]
    if any(p.exists() for p in paths):
        raise ValueError('refusing to overwrite reparsed evidence')
    old = json.loads((folder / 'summary.json').read_text())
    rows = [json.loads(s) for s in (folder / 'corners.jsonl').read_text().splitlines()]
    if old['invocations'] != 47 or len(rows) != 45 or len({r['key'] for r in rows}) != 45:
        raise ValueError('unexpected original experiment size')
    expected = circuit_signature((folder / 'design.cir').read_text())
    hashes = {}
    recovered = []
    for original in rows:
        row = {k: original[k] for k in ('key', 'process', 'vdd_scale', 'temp_c')}
        row['ok'] = False
        sub = folder / row['key']
        for name in ('design.cir', 'ngspice.log', 'ac.txt'):
            p = sub / name
            hashes[str(p.relative_to(folder))] = hashlib.sha256(p.read_bytes()).hexdigest()
        try:
            signature = circuit_signature((sub / 'design.cir').read_text())
            if signature != expected:
                raise ValueError('changed circuit geometry')
            log = (sub / 'ngspice.log').read_text()
            assert_no_silent_failures(log)
            row.update(extract(log, sub, 1.8 * row['vdd_scale']),
                       circuit_signature=signature, ok=True)
        except (ValueError, RuntimeError, OSError) as exc:
            row['error'] = str(exc)
        recovered.append(row)
    log = (folder / 'startup/ngspice.log').read_text()
    assert_no_silent_failures(log)
    final, _ = parse_meas(log, 'final_nbias')
    nominal = next(r for r in recovered if r['key'] == 'tt_1.00_27')
    startup = {'ok': False}
    if nominal['ok'] and final is not None and math.isfinite(final):
        startup.update(ok=True, final_nbias_v=final, nominal_nbias_v=nominal['nbias_v'],
                       relative_settling_error=abs(final / nominal['nbias_v'] - 1))
    valid = [r for r in recovered if r['ok']]
    keys = ('reference_current_a', 'power_ctle_and_bias_w', 'noise_vrms', 'peaking_db', 'f_peak_hz')
    summary = dict(old, n_measured=len(valid), startup=startup,
                   n_s3_s5_s6_only_pass=sum(r['s3_s5_s6_only_pass'] for r in valid),
                   nominal=nominal,
                   ranges={k: [min(r[k] for r in valid), max(r[k] for r in valid)] for k in keys} if valid else {},
                   reparse_note='i(vdd) is the print label; vdd#branch was the wrong parser key. No SPICE rerun.',
                   reparse_additional_spice_calls=0)
    for name in ('summary.json', 'corners.jsonl', 'startup/ngspice.log', 'startup/design.cir', 'startup/startup.txt'):
        p = folder / name
        hashes[name] = hashlib.sha256(p.read_bytes()).hexdigest()
    parser = Path(__file__).with_name('exp_physical_bias.py')
    write_json(paths[2], {'raw_sha256': hashes, 'parser_sha256': hashlib.sha256(parser.read_bytes()).hexdigest(),
                          'reparser_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    with paths[0].open('x', encoding='utf-8') as stream:
        for row in recovered:
            stream.write(json.dumps(row, allow_nan=False) + '\n')
    write_json(paths[1], summary)
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', type=Path)
    result = reparse(parser.parse_args().folder)
    raise SystemExit(0 if result['n_measured'] == 45 and result['startup']['ok'] else 1)
