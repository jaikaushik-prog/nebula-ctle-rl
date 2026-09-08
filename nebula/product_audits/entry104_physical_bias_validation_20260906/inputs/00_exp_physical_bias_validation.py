"""Entry 104: exact-deck distortion/swing + existing device-to-link model.

Reuses hash-verified Entry 103 AC/noise; never changes the production runner.
See BIAS_VALIDATION_PLAN.md. Electrical pass deliberately excludes full S7 area.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import time
from types import SimpleNamespace

import numpy as np

from nebula.common.types import all_corners
from nebula.device import sky130_runner as S
from nebula.device.crosscheck import assert_no_silent_failures, parse_meas
from nebula.experiments import exp_physical_bias as P, exp_product_readiness as A
from nebula.link.bridge import device_result_from_point, evaluate_link, swing_for_compression_check
from nebula.link.channel import DEFAULT_OSR
from nebula.link.config import LinkConfig
from nebula.link.cursors import pulse_response
from nebula.link import dfe_ablation as DFE
from nebula.report.product_scope import area_inventory, circuit_signature
from nebula.report.schematic import params_of
from nebula.rl import reward_v1 as R
from nebula.rl.contract import f_peak_octaves
from nebula.rl.evaluator import validate, Verdict, annotate_interpolated_peak, scored_meas

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'nebula/product_audits/entry103_physical_bias_20260906'
ELECTRICAL_SPECS = tuple(dict.fromkeys((*[s for s in R.V6_SPECS if s != 'S7_area'], 'S4_hd3')))


def load_source(folder):
    """Reuse measured values only after verifying raw identity and all 45 points."""
    folder = Path(folder)
    proof = json.loads((folder / 'reparse_provenance.json').read_text())
    for name, expected in proof['raw_sha256'].items():
        path = (folder / name).resolve()
        if not path.is_relative_to(folder.resolve()):
            raise ValueError('source provenance escapes evidence directory')
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f'changed source hash: {name}')
    rows = [json.loads(line) for line in (folder / 'corners_reparsed.jsonl').read_text().splitlines()]
    expected = {(c.process, c.vdd_scale, c.temp_c) for c in all_corners()}
    if len(rows) != 45 or {(r['process'], r['vdd_scale'], r['temp_c']) for r in rows} != expected:
        raise ValueError('source must contain exactly all 45 PVT points')
    signature = circuit_signature((folder / 'design.cir').read_text())
    for row in rows:
        key = f"{row['process']}_{row['vdd_scale']:.2f}_{row['temp_c']:g}"
        if row['key'] != key or not row['ok']:
            raise ValueError('source key/measurement invalid')
        deck = (folder / key / 'design.cir').read_text()
        if circuit_signature(deck) != signature or row['circuit_signature'] != signature:
            raise ValueError('source changed fixed circuit')
        if not math.isclose(params_of(deck)['VDD'], 1.8 * row['vdd_scale']):
            raise ValueError('source supply disagrees with corner')
        if not re.search(rf'^\.lib .* {row["process"]}$', deck, re.M):
            raise ValueError('source library disagrees with corner')
        actual_temp = float(re.search(r'^\.temp (\S+)', deck, re.M)[1])
        if actual_temp != row['temp_c']:
            raise ValueError('source temperature disagrees with corner')
        log = (folder / key / 'ngspice.log').read_text()
        assert_no_silent_failures(log)
        # Reproduce the archived arithmetic exactly (1.8*scale, not its
        # decimal netlist formatting); the checked hardware supply is unchanged.
        recomputed = P.extract(log, folder / key, 1.8 * row['vdd_scale'])
        if any(row[k] != value for k, value in recomputed.items()):
            raise ValueError('parsed source no longer reproduces raw measurements')
    return rows, signature


def measurement_deck(source, tone, amplitude, *, swing):
    """Keep every circuit line; use the canonical existing measurement blocks."""
    if not all(math.isfinite(x) and x > 0 for x in (tone, amplitude)):
        raise ValueError('tone and amplitude must be positive and finite')
    matches = re.findall(r'^Vid\s+vid\s+0\s+dc\s+0\s+ac\s+1\s*$', source, re.M)
    if len(matches) != 1 or '\nac dec ' not in source:
        raise ValueError('expected one unmodulated Vid and original AC control')
    deck = source.split('\nac dec ')[0]
    deck = re.sub(r'^(Vid\s+vid\s+0\s+dc\s+0\s+ac\s+1)[ \t]*$',
                  lambda m: m[1] + S._hd3_source(amplitude, tone), deck, flags=re.M)
    if swing:
        deck += S._SWING_BLOCK.format(device=P.NFET, vid_max=.8, vid_step=.004)
    deck += S._hd3_block(tone) + '\nquit\n.endc\n.end\n'
    if circuit_signature(deck) != circuit_signature(source):
        raise ValueError('measurement changed circuit geometry')
    return deck


def parse_swing(raw):
    raw = np.asarray(raw)
    if raw.ndim != 2 or raw.shape[1] != 16 or raw.shape[0] < 5 or not np.isfinite(raw).all():
        raise ValueError('invalid DC swing shape or values')
    if not np.all(np.diff(raw[:, 0]) > 0) or not np.allclose(raw[:, 0::2], raw[:, 0, None]):
        raise ValueError('DC sweep coordinates are not increasing/consistent')
    return dict(vid=raw[:, 0], vod=raw[:, 1] - raw[:, 3],
                sat_ok=(raw[:, 5] > raw[:, 7]) & (raw[:, 11] > raw[:, 13]),
                id_min=np.minimum(raw[:, 9], raw[:, 15]))


def parse_hd3(raw, tone, amplitude):
    raw = np.asarray(raw)
    if raw.ndim != 2 or raw.shape[1] != 2 or raw.shape[0] < 64 or not np.isfinite(raw).all():
        raise ValueError('invalid HD3 waveform shape or values')
    dt = np.diff(raw[:, 0])
    if not np.all(dt > 0) or not np.allclose(dt, dt.mean(), rtol=1e-5, atol=1e-18):
        raise ValueError('HD3 time samples must be uniform and increasing')
    value, detail = S.hd3_from_waveform(raw[:, 0], raw[:, 1], f_tone_hz=tone)
    if not math.isfinite(value):
        raise ValueError('nonfinite HD3')
    # The shared FFT helper defaults this label to 100 mV; use the actual deck drive.
    detail['vin_diff_pk_v'] = float(f'{amplitude:.6g}')
    return value, detail


def measured_point(source_deck, ac_log, fresh_log, ac_folder, swing_raw, hd3, detail):
    """Adapt explicit raw primitives; the first MOS in the log can be a PMOS."""
    p = params_of(source_deck)
    # Metadata only for the existing power and swing adapters, never a netlist
    # generator or a second definition of the physical reference geometry.
    meta = SimpleNamespace(vdd=p['VDD'], i_tail_per_side_a=p['IT'])
    pt = S.Sky130Point(ok=True, point=meta, netlist=source_deck)
    for attr, prop in [('gm', 'gm'), ('gmbs', 'gmbs'), ('gds', 'gds'), ('vth', 'vth'),
                       ('vds', 'vds'), ('vdsat', 'vdsat'), ('vgs', 'vgs'), ('id_a', 'id')]:
        setattr(pt, attr, P.scalar(fresh_log, f'@m.xm1.m{P.NFET}[{prop}]'))
    for attr, prop in [('i_tail_meas_a', 'id'), ('vds_tail', 'vds'), ('vdsat_tail', 'vdsat'),
                       ('vgs_tail', 'vgs'), ('vth_tail', 'vth'), ('gm_tail', 'gm')]:
        setattr(pt, attr, P.scalar(fresh_log, f'@m.xmt1.m{P.NFET}[{prop}]'))
    pt.i_supply_a = -P.scalar(fresh_log, 'i(vdd)')
    pt.i_ref_meas_a = P.scalar(fresh_log, f'@m.xmr.m{P.NFET}[id]')
    pt.v_bias_dc = P.scalar(fresh_log, 'v(nbias)')
    pt.v_out_dc, pt.v_src_dc = P.scalar(fresh_log, 'v(outp)'), P.scalar(fresh_log, 'v(s1)')
    # Fresh transient fixture's zero-input OP must reproduce the reused AC bias.
    for key in ('i(vdd)', 'v(nbias)', 'v(p_bias)', f'@m.xm1.m{P.NFET}[gm]'):
        if not math.isclose(P.scalar(ac_log, key), P.scalar(fresh_log, key), rel_tol=1e-6, abs_tol=1e-12):
            raise ValueError(f'fresh DC point differs from reused AC bias: {key}')
    checked = P.extract(ac_log, ac_folder, p['VDD'])
    for attr, name in [('g_dc_db', 'g_dc'), ('g_nyq_db', 'g_nyq'), ('g_pk_db', 'g_pk'), ('g_top_db', 'g_top')]:
        setattr(pt, attr, parse_meas(ac_log, name)[0])
    pt.f_pk_hz = parse_meas(ac_log, 'g_pk')[1]
    pt.vn_in_vrms = checked['noise_vrms']
    ac = np.loadtxt(ac_folder / 'ac.txt')
    pt.ac_freq_hz, pt.ac_mag_db = ac[:, 0], ac[:, 1]
    peak = S.interpolate_peak_log_f(pt.ac_freq_hz, pt.ac_mag_db)
    pt.f_pk_interp_hz, pt.g_pk_interp_db, pt.peak_interp = peak.f_hz, peak.g_db, peak.as_dict()
    for attr, value in parse_swing(swing_raw).items():
        setattr(pt, attr, value)
    pt.hd3_dbc, pt.hd3_detail = hd3, detail
    verdict, reason = validate(pt, meta)
    if verdict is not Verdict.VALID:
        raise ValueError(f'physical operating-point validity failed: {reason}')
    return pt


def links_for_point(pt, hd3_100, losses, request, area):
    dev = device_result_from_point(pt, area_mm2=area['geometry_subtotal_mm2'])
    if not dev.ok:
        raise ValueError(f'device-to-link fit/swing rejected: {dev.fail_reason}')
    meas = {'g_dc_db': dev.g_dc_db, 'peaking_db': dev.peaking_db,
            'f_peak_oct': f_peak_octaves(dev.f_peak_hz), 'nyq_boost_db': pt.nyquist_boost_db,
            'inoise_vrms': dev.vn_in_vrms, 'power_w': dev.power_w,
            'pair_margin_v': pt.vds-pt.vdsat, 'tail_margin_v': pt.tail_margin_v}
    annotate_interpolated_peak(meas, None, pt)
    meas = scored_meas(meas, True)
    rows = []
    for loss in losses:
        cfg, detail = LinkConfig(channel_loss_db_at_nyquist=loss), []
        link = evaluate_link(dev, cfg, detail=detail, swing_is_lower_bound=swing_for_compression_check(pt)[1])
        margins = R.margins(meas, request['f_peak_hz'], target_peaking_db=request['peaking_db'],
                            link=link if link.ok else None, area_mm2=None,
                            hd3_dbc=hd3_100, hd3_nyq_dbc=pt.hd3_dbc)
        missing = [s for s in ELECTRICAL_SPECS if s not in margins]
        failed = [s for s, value in R.shortfalls(margins, tuple(s for s in ELECTRICAL_SPECS if s in margins)).items() if value != 0]
        row = dict(loss_db=loss, ok=link.ok, reason=link.fail_reason, model_pass=not missing and not failed,
                   failed_specs=failed, unmeasured_specs=missing, policies={}, control_pass=False,
                   margins={s: margins[s] for s in ELECTRICAL_SPECS if s in margins}, area_status='NOT_VERIFIED')
        if link.ok and detail:
            pr = pulse_response(cfg.channel, cfg.tx, detail[0].ctle)
            eyes = DFE.all_policies(pr, DEFAULT_OSR, int(np.argmax(pr)))
            row.update(bridge_eye_h_v=link.eye_h_v, bridge_eye_w_ui=link.eye_w_ui,
                       policies={k: asdict(e) for k, e in eyes.items()},
                       control_pass=A.control_matches(eyes['ideal'], link.eye_h_v, link.eye_w_ui),
                       predicted_peak_excursion_pp_v=detail[0].peak_excursion_pp_v)
        rows.append(row)
    return dict(meas=meas, links=rows, fit_residual_db=dev.fit_residual_db,
                measured_swing_pp_v=dev.vout_swing_v,
                swing_is_lower_bound=swing_for_compression_check(pt)[1])


def summarise(rows, losses, representative):
    summary = A.summarise_fixed(rows, losses, representative)
    valid = [r for r in rows if r['ok']]
    summary.update(area_status='NOT_VERIFIED', full_product_compliance=False,
                   electrical_specs=list(ELECTRICAL_SPECS),
                   excluded_full_receiver_specs=['S7_area'],
                   note='Electrical model gate only: S7 excluded as unknown; behavioural DFE, typical passives, one load, constructed channels. NOT full hardware compliance.',
                   hd3_100mhz_worst_dbc=max((r['hd3_100mhz_dbc'] for r in rows if r.get('hd3_100mhz_dbc') is not None), default=None),
                   hd3_nyquist_worst_dbc=max((r['hd3_nyq_dbc'] for r in rows if r.get('hd3_nyq_dbc') is not None), default=None),
                   max_fit_residual_db=max((r['fit_residual_db'] for r in valid), default=None))
    return summary


def run(out, source=SOURCE):
    out, source = Path(out).resolve(), Path(source).resolve()
    if out.exists():
        raise FileExistsError(f'refusing to overwrite {out}')
    previous, signature = load_source(source)
    candidate_path = ROOT / 'nebula/product_audits/entry101_fixed490_20260906/candidate.json'
    candidate = json.loads(candidate_path.read_text())
    losses, request = candidate['channel_losses_db'], candidate['request']
    area = area_inventory((source / 'design.cir').read_text())
    out.mkdir(parents=True)
    from nebula.experiments.runlock import hold, stamp
    with hold('physical_bias_validation', here=out):
        started, calls, results = time.perf_counter(), 0, []
        snapshot = out / 'inputs'
        snapshot.mkdir()
        inputs = [Path(__file__), Path(P.__file__), Path(A.__file__), Path(S.__file__),
                  ROOT / 'nebula/link/bridge.py', ROOT / 'nebula/link/fit.py', ROOT / 'nebula/link/config.py',
                  ROOT / 'nebula/link/dfe_ablation.py', ROOT / 'nebula/rl/reward_v1.py',
                  ROOT / 'nebula/BIAS_VALIDATION_PLAN.md', candidate_path,
                  source / 'summary_reparsed.json', source / 'corners_reparsed.jsonl', source / 'reparse_provenance.json']
        hashes = {}
        for index, path in enumerate(inputs):
            dest = snapshot / f'{index:02d}_{path.name}'
            shutil.copyfile(path, dest)
            hashes[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
        P.write_json(out / 'provenance.json', {**stamp(), 'input_sha256': hashes,
                     'source_evidence': str(source), 'circuit_signature': signature, 'max_spice_calls': 90})
        P.write_json(out / 'area_inventory.json', area)
        shutil.copyfile(source / 'design.cir', out / 'design.cir')
        cfg = LinkConfig(channel_loss_db_at_nyquist=losses[0])
        with (out / 'fixed_pvt.jsonl').open('x', encoding='utf-8') as journal:
            for prev in previous:
                sub = source / prev['key']
                deck = (sub / 'design.cir').read_text()
                row = dict(corner=f"{prev['process']}/{prev['vdd_scale']:.2f}/{prev['temp_c']:g}C",
                           source_key=prev['key'], setting=candidate['search']['setting'],
                           circuit_signature=signature, ok=False, links=[], spice_calls=0)
                measured, errors = {}, []
                for name, tone, amplitude, swing in [('s4', S.HD3_TONE_HZ, S.HD3_VIN_DIFF_PK_V, False),
                                                    ('nyquist', cfg.nyquist_hz, .5*cfg.v_in_diff_pp_v, True)]:
                    folder = out / prev['key'] / name
                    try:
                        cir = measurement_deck(deck, tone, amplitude, swing=swing)
                        calls += 1
                        row['spice_calls'] += 1
                        log = P.invoke(cir, folder)
                        hd3, detail = parse_hd3(np.loadtxt(folder / 'hd3.txt'), tone, amplitude)
                        measured[name] = dict(log=log, hd3=hd3, detail=detail, folder=folder)
                    except (ValueError, RuntimeError, OSError) as exc:
                        errors.append(f'{name}: {exc}')
                row['hd3_100mhz_dbc'] = measured.get('s4', {}).get('hd3')
                row['hd3_nyq_dbc'] = measured.get('nyquist', {}).get('hd3')
                row['hd3_details'] = {k: value['detail'] for k, value in measured.items()}
                if not errors:
                    try:
                        nyq = measured['nyquist']
                        pt = measured_point(deck, (sub / 'ngspice.log').read_text(), nyq['log'], sub,
                                            np.loadtxt(nyq['folder'] / 'swing.txt'), nyq['hd3'], nyq['detail'])
                        row.update(links_for_point(pt, measured['s4']['hd3'], losses, request, area), ok=True)
                    except (ValueError, RuntimeError, OSError) as exc:
                        errors.append(str(exc))
                if errors:
                    row['reason'] = '; '.join(errors)
                results.append(row)
                journal.write(json.dumps(row, allow_nan=False) + '\n')
                journal.flush()
                print(f"{len(results)}/45 {row['corner']}: {sum(p['model_pass'] for p in row['links'])}/{len(losses)} electrical model passes" + (f"; {row['reason']}" if errors else ''), flush=True)
        fixed = summarise(results, losses, candidate['search']['representative_channel_loss_db'])
        summary = dict(fixed=fixed, spice_calls=calls, reused_ac_noise_points=len(previous),
                       wall_s=time.perf_counter()-started, adopted=False, full_product_compliance=False)
        P.write_json(out / 'summary.json', summary)
        raw = {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in out.rglob('*') if p.is_file() and 'runlock' not in p.name}
        P.write_json(out / 'evidence_sha256.json', raw)
        print(json.dumps(summary, indent=2), flush=True)
        return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    result = run(parser.parse_args().out)
    fixed = result['fixed']
    raise SystemExit(0 if fixed['n_model_pass'] == fixed['n_expected_conditions'] and fixed['dfe_control_all_pass'] else 1)
