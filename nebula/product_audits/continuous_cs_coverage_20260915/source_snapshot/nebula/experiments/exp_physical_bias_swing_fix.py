"""Entry 104b: bounded DC-only correction of Entry 104's missed G140 rule.

Original 90-call failure records are immutable. This uses the established
attenuation-adjusted sweep; no new circuit, repeat HD3, or tolerance change.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import time

import numpy as np

from nebula.experiments import exp_physical_bias_validation as V
from nebula.experiments.exp_physical_bias_validation import candidate_vid_max
from nebula.experiments import exp_physical_bias as P
from nebula.device.crosscheck import assert_no_silent_failures
from nebula.report.product_scope import area_inventory, circuit_signature

ORIGINAL = V.ROOT / 'nebula/product_audits/entry104_physical_bias_validation_20260906'


def dc_deck(source, vid_max):
    if not math.isfinite(vid_max) or vid_max <= 0 or '\nac dec ' not in source:
        raise ValueError('invalid DC range/source')
    deck = source.split('\nac dec ')[0]
    deck += V.S._SWING_BLOCK.format(device=P.NFET, vid_max=vid_max, vid_step=.004)
    deck += '\nquit\n.endc\n.end\n'
    if circuit_signature(deck) != circuit_signature(source):
        raise ValueError('DC instrument changed hardware')
    return deck


def run(out, original=ORIGINAL, source=V.SOURCE):
    out, original, source = Path(out).resolve(), Path(original).resolve(), Path(source).resolve()
    if out.exists():
        raise FileExistsError(f'refusing to overwrite {out}')
    source_rows, signature = V.load_source(source)
    proof = json.loads((original / 'evidence_sha256.json').read_text())
    for name, digest in proof.items():
        path = (original / name).resolve()
        if not path.is_relative_to(original):
            raise ValueError('original manifest escapes its evidence directory')
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f'original evidence changed: {name}')
    old_summary = json.loads((original / 'summary.json').read_text())
    old_rows = [json.loads(line) for line in (original / 'fixed_pvt.jsonl').read_text().splitlines()]
    if old_summary['spice_calls'] != 90 or len(old_rows) != 45 or {r['source_key'] for r in old_rows} != {r['key'] for r in source_rows}:
        raise ValueError('original grid/call count does not match the frozen correction')
    candidate_path = V.ROOT / 'nebula/product_audits/entry101_fixed490_20260906/candidate.json'
    candidate = json.loads(candidate_path.read_text())
    area = area_inventory((source / 'design.cir').read_text())
    vid_max = candidate_vid_max(candidate)
    out.mkdir(parents=True)
    from nebula.experiments.runlock import hold, stamp
    with hold('physical_bias_swing_fix', here=out):
        started, calls, rows = time.perf_counter(), 0, []
        inputs = out / 'inputs'
        inputs.mkdir()
        paths = [Path(__file__), Path(V.__file__), Path(P.__file__), Path(V.S.__file__),
                 V.ROOT / 'nebula/experiments/adaptive_screen.py',
                 V.ROOT / 'nebula/BIAS_SWING_CORRECTION_PLAN.md', candidate_path,
                 original / 'evidence_sha256.json', original / 'summary.json']
        hashes = {}
        for i, path in enumerate(paths):
            shutil.copyfile(path, inputs / f'{i:02d}_{path.name}')
            hashes[str(path.relative_to(V.ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
        P.write_json(out / 'provenance.json', {**stamp(), 'input_sha256': hashes,
                     'source': str(source), 'original': str(original), 'vid_max': vid_max,
                     'maximum_additional_calls': 45, 'circuit_signature': signature})
        P.write_json(out / 'area_inventory.json', area)
        shutil.copyfile(source / 'design.cir', out / 'design.cir')
        with (out / 'fixed_pvt.jsonl').open('x', encoding='utf-8') as journal:
            for old in old_rows:
                key = old['source_key']
                sub = source / key
                deck = (sub / 'design.cir').read_text()
                row = {k: old[k] for k in ('corner', 'source_key', 'setting', 'circuit_signature',
                                          'hd3_100mhz_dbc', 'hd3_nyq_dbc', 'hd3_details')}
                row.update(ok=False, links=[], spice_calls=0, reused_hd3_calls=2)
                try:
                    if row['circuit_signature'] != signature:
                        raise ValueError('original HD3 circuit identity differs')
                    cfg = V.LinkConfig(channel_loss_db_at_nyquist=candidate['channel_losses_db'][0])
                    for name, tone, amplitude in [('s4', V.S.HD3_TONE_HZ, V.S.HD3_VIN_DIFF_PK_V),
                                                  ('nyquist', cfg.nyquist_hz, .5*cfg.v_in_diff_pp_v)]:
                        folder = original / key / name
                        assert_no_silent_failures((folder / 'ngspice.log').read_text())
                        value, detail = V.parse_hd3(np.loadtxt(folder / 'hd3.txt'), tone, amplitude)
                        field = 'hd3_100mhz_dbc' if name == 's4' else 'hd3_nyq_dbc'
                        if value != old[field] or detail != old['hd3_details'][name]:
                            raise ValueError('original HD3 does not reproduce its raw waveform')
                    calls += 1
                    row['spice_calls'] = 1
                    fresh = P.invoke(dc_deck(deck, vid_max), out / key)
                    pt = V.measured_point(deck, (sub / 'ngspice.log').read_text(), fresh, sub,
                                          np.loadtxt(out / key / 'swing.txt'), old['hd3_nyq_dbc'], old['hd3_details']['nyquist'])
                    row.update(V.links_for_point(pt, old['hd3_100mhz_dbc'], candidate['channel_losses_db'],
                                                candidate['request'], area), ok=True,
                               swing_input_peak_v=vid_max)
                except (ValueError, RuntimeError, OSError) as exc:
                    row['reason'] = str(exc)
                rows.append(row)
                journal.write(json.dumps(row, allow_nan=False) + '\n')
                journal.flush()
                print(f"{len(rows)}/45 {row['corner']}: {sum(p['model_pass'] for p in row['links'])}/7 electrical model passes" + (f"; {row['reason']}" if not row['ok'] else ''), flush=True)
        fixed = V.summarise(rows, candidate['channel_losses_db'], candidate['search']['representative_channel_loss_db'])
        summary = dict(fixed=fixed, additional_dc_spice_calls=calls, original_spice_calls=90,
                       total_validation_spice_calls=90+calls, prior_reference_spice_calls=47,
                       reused_ac_noise_points=45, reused_hd3_waveforms=90,
                       wall_s=time.perf_counter()-started, adopted=False, full_product_compliance=False,
                       correction='Restore existing G140 attenuation-adjusted DC sweep. Original 168/315 result retained, not circuit failure evidence.')
        P.write_json(out / 'summary.json', summary)
        hashes = {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in out.rglob('*') if p.is_file() and 'runlock' not in p.name}
        P.write_json(out / 'evidence_sha256.json', hashes)
        print(json.dumps(summary, indent=2), flush=True)
        return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    result = run(parser.parse_args().out)
    fixed = result['fixed']
    raise SystemExit(0 if fixed['n_model_pass'] == fixed['n_expected_conditions'] and fixed['dfe_control_all_pass'] else 1)
