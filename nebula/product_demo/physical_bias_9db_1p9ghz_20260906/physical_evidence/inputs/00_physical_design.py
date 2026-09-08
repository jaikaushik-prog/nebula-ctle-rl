"""Opt-in product path: legacy proposals, fresh fixed physical-bias evidence.

No training/reward change. See PHYSICAL_PRODUCT_PLAN.md (Entry 105).
Measurement definitions are reused from the bounded, tested bias instruments.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shutil
import time

import numpy as np

from nebula.common.types import all_corners
from nebula.device import sky130_runner as S
from nebula.device.bias_reference import calibration_deck, reference_geometry, physical_reference_deck
from nebula.experiments import exp_physical_bias as P
from nebula.experiments import exp_physical_bias_validation as V
from nebula.report.product_scope import area_inventory, circuit_signature, implementation_scope

ROOT = Path(__file__).resolve().parents[1]
MODE = 'fresh-fixed-physical-bias-v1'
MAX_CALLS = 137


def select_fixed_setting(table, request, nominal_setting, losses):
    """Classical proposal pre-screen ONLY; this is not new-hardware proof."""
    eligible = set(table.settings)
    checks = 0
    for loss in losses:
        for corner in table.corners:
            eligible.intersection_update(table.compliant_settings(corner, loss, *request))
            checks += len(table.settings)
    choices = sorted(eligible)
    if not choices:
        raise RuntimeError('no single fixed setting in the characterised legacy bank; '
                           'this is not proof that a physical solution is impossible')
    return (nominal_setting if nominal_setting in eligible else choices[0]), choices, checks


def propose(peaking_db, f_peak_hz, loss_db):
    from nebula.rl import hybrid_designer as H
    from nebula.experiments import exp_joint_bank as J, exp_joint_bank_73 as B
    old = H.solve(peaking_db, f_peak_hz, loss_db)
    table, _, _, _ = H._load_assets()
    setting, eligible, checks = select_fixed_setting(
        table, (peaking_db, f_peak_hz), old['setting'], old['channel_losses_db'])
    _, _, base_u, _ = B._load_sources()
    bank = J.bank(base_u, n_rs=J.N_RS, n_cs=J.N_CS, rs_span=J.RS_SPAN, cs_span=J.CS_SPAN)
    atten, code = J.split_setting(setting)
    search = {k: value for k, value in old.items() if not k.startswith('_')}
    search.update(u=list(bank[code].u), setting=int(setting), atten_code=int(atten),
                  bank_code=int(code), reward=None, design_id=None,
                  which_path='legacy-rl-proposal/classical-fixed-intersection/fresh-physical',
                  legacy_nominal_setting=old['setting'], fixed_eligible_settings=eligible,
                  fixed_prescreen_rows_checked=checks,
                  fixed_selection_reason='kept-nominal' if setting == old['setting'] else 'lowest-fixed-eligible',
                  selection_objective='legacy fixed intersection proposes one candidate; fresh physical electrical gate decides',
                  evidence_warning='Old-bank reward/verification are not physical-bias evidence.')
    return search, old


def capture_candidate(search, folder):
    """One canonical runner call, no geometry-changing NaN retry."""
    from nebula.experiments.cl_range import committed_cl_range
    from nebula.experiments.adaptive_screen import _attenuation_run_args
    from nebula.rl.contract import sizing_from_u
    from nebula.rl.evaluator import build_point
    sizing = sizing_from_u(search['u'], cl_f=committed_cl_range().cl_mid_f)
    point, _ = build_point(sizing, corner='tt', vdd_scale=1.)
    folder.mkdir()
    pt = S.run_point(point, corner='tt', temp_c=27., swing=False, ac_peak_interp=True,
                     keep_netlist=True, keep_text=True, nan_retry_bypass_f=None,
                     **_attenuation_run_args(search['atten_code'], search['atten_max_x']))
    if pt.netlist:
        (folder / 'design.cir').write_text(pt.netlist, encoding='ascii')
    (folder / 'ngspice.log').write_text(pt.raw_text or pt.fail_reason or '', encoding='utf-8')
    if pt.ac_freq_hz is not None:
        np.savetxt(folder / 'ac.txt', np.column_stack((pt.ac_freq_hz, pt.ac_mag_db)))
    if not pt.ok or not pt.netlist or not pt.raw_text or pt.nan_retry_used:
        raise RuntimeError(f'legacy candidate export failed without retry: {pt.fail_reason}')
    P.assert_no_silent_failures(pt.raw_text)
    return pt.netlist, dict(sizing.params)


def verification_records(rows, search):
    records = []
    for row in rows:
        by_loss = {p['loss_db']: p for p in row['links']}
        for loss in search['channel_losses_db']:
            link = by_loss.get(loss, {})
            compliant = bool(row['ok'] and link.get('model_pass') and link.get('control_pass'))
            records.append(dict(channel_loss_db=loss, corner=row['corner'], setting=search['setting'],
                                atten_code=search['atten_code'], bank_code=search['bank_code'],
                                source='fresh-ngspice-and-behavioural-link',
                                selection_reason='unchanged-physical-circuit', compliant=compliant,
                                eye_area=(link['bridge_eye_h_v'] * link['bridge_eye_w_ui'] if link.get('ok') else None),
                                eye_h_v=link.get('bridge_eye_h_v'), eye_w_ui=link.get('bridge_eye_w_ui'),
                                failed_specs=link.get('failed_specs', []),
                                unmeasured_specs=link.get('unmeasured_specs', list(V.ELECTRICAL_SPECS) if not row['ok'] else []),
                                reason=row.get('reason') or link.get('reason'),
                                meas=row.get('meas', {}), circuit_signature=row['circuit_signature']))
    n_pass = sum(r['compliant'] for r in records)
    mandated = sum(all(r['compliant'] for r in records if r['corner'] == row['corner']) for row in rows)
    return dict(mode=MODE, n_corners=len(rows), n_channel_losses=len(search['channel_losses_db']),
                n_points=len(records), n_pass=n_pass, n_failed=len(records)-n_pass,
                all_points_pass=bool(records) and n_pass == len(records),
                n_mandated_points=len(rows), n_mandated_pass=mandated,
                mandated_all_pass=mandated == len(rows),
                channel_losses_db=search['channel_losses_db'],
                representative_channel_loss_db=search['representative_channel_loss_db'],
                spec_set='fresh electrical model checks; S7 unknown/excluded; behavioural DFE',
                per_condition=records)


def is_verified(design):
    """Fail closed: merely relabelling an old bank result cannot pass."""
    v = design.get('verification') or {}
    evidence = design.get('physical_evidence') or {}
    fixed = (design.get('product_readiness_audit') or {}).get('fixed') or {}
    return bool(v.get('mode') == MODE and v.get('all_points_pass')
                and v.get('n_corners') == 45 and evidence.get('deck_sha256')
                and fixed.get('n_corners') == 45 and fixed.get('n_invalid_corners') == 0
                and fixed.get('n_model_pass') == 45 * v.get('n_channel_losses', 0)
                and fixed.get('dfe_control_all_pass'))


def output_deck(design):
    evidence = design['physical_evidence']
    path = Path(evidence['directory']) / 'design.cir'
    if hashlib.sha256(path.read_bytes()).hexdigest() != evidence['deck_sha256']:
        raise ValueError('physical output deck hash changed')
    return path.read_text(encoding='ascii')


def _snapshots(out):
    paths = [Path(__file__), Path(P.__file__), Path(V.__file__), Path(S.__file__),
             ROOT / 'nebula/device/bias_reference.py', ROOT / 'nebula/device/passives.py',
             ROOT / 'nebula/report/product_scope.py', ROOT / 'nebula/rl/hybrid_designer.py',
             ROOT / 'nebula/rl/reward_v1.py', ROOT / 'nebula/rl/evaluator.py',
             ROOT / 'nebula/link/bridge.py', ROOT / 'nebula/link/fit.py',
             ROOT / 'nebula/link/config.py', ROOT / 'nebula/link/dfe_ablation.py',
             ROOT / 'nebula/PHYSICAL_PRODUCT_PLAN.md', S.SPICE_DIR / '.spiceinit']
    folder = out / 'inputs'
    folder.mkdir()
    hashes = {}
    for i, path in enumerate(paths):
        shutil.copyfile(path, folder / f'{i:02d}_{path.name}')
        hashes[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    P.write_json(out / 'provenance.json', dict(input_sha256=hashes, max_spice_calls=MAX_CALLS,
                 ngspice=str(P.ngspice_path()), verification_mode=MODE,
                 note='Legacy bank is proposal-only. No physical-bias RL training or full receiver claim.'))


def run(peaking_db, f_peak_hz, *, evidence_dir, channel_loss_db=None, progress=None):
    if evidence_dir is None:
        raise ValueError('physical mode requires a new evidence directory')
    out = Path(evidence_dir).resolve()
    out.mkdir(parents=True, exist_ok=False)
    from nebula.experiments.runlock import hold
    from nebula.design import request_miss
    from nebula.link.config import LinkConfig
    request = dict(peaking_db=float(peaking_db), f_peak_hz=float(f_peak_hz), f_peak_ghz=float(f_peak_hz)/1e9)
    started, calls = time.perf_counter(), 0

    def update(message, percent):
        if progress:
            progress(message, percent)

    with hold('physical_product', here=out):
        try:
            _snapshots(out)
            update('RL proposal and fixed-setting pre-screen (legacy evidence only)', 10)
            search, old = propose(peaking_db, f_peak_hz, channel_loss_db)
            P.write_json(out / 'legacy_proposal_not_physical_evidence.json', old)
            P.write_json(out / 'candidate.json', dict(request=request, search=search))
            update('Building the physical reference and MIM bypass', 18)
            calls += 1
            source, params = capture_candidate(search, out / 'legacy_candidate')
            calls += 1
            cal = P.invoke(calibration_deck(source), out / 'calibration')
            geo = reference_geometry(source, P.scalar(cal, 'v(p_bias)'))
            P.write_json(out / 'geometry.json', asdict(geo))
            physical = physical_reference_deck(source, geo)
            signature = circuit_signature(physical)
            area = area_inventory(physical)
            P.write_json(out / 'area_inventory.json', area)
            losses = search['channel_losses_db']
            cfg = LinkConfig(channel_loss_db_at_nyquist=losses[0])
            rows = []
            with (out / 'fixed_pvt.jsonl').open('x', encoding='utf-8') as journal:
                for corner in all_corners():
                    key = f'{corner.process}_{corner.vdd_scale:.2f}_{corner.temp_c:g}'
                    deck = P.corner_deck(physical, corner.process, corner.vdd_scale, corner.temp_c)
                    row = dict(corner=V.A._label(corner), setting=search['setting'],
                               circuit_signature=signature, ok=False, links=[], spice_calls=0)
                    errors, measured = [], {}
                    try:
                        calls += 1
                        row['spice_calls'] += 1
                        ac_folder = out / key / 'ac_noise'
                        ac_log = P.invoke(deck, ac_folder)
                        P.extract(ac_log, ac_folder, 1.8 * corner.vdd_scale)
                        if row['corner'] == 'tt/1.00/27C':
                            # Captured verbatim from the invocation, not a new ideal export.
                            shutil.copyfile(ac_folder / 'design.cir', out / 'design.cir')
                    except (ValueError, RuntimeError, OSError) as exc:
                        errors.append(f'ac/noise: {exc}')
                    for name, tone, amplitude, swing in [
                        ('s4', S.HD3_TONE_HZ, S.HD3_VIN_DIFF_PK_V, False),
                        ('nyquist', cfg.nyquist_hz, .5 * cfg.v_in_diff_pp_v, True)]:
                        folder = out / key / name
                        try:
                            cir = V.measurement_deck(deck, tone, amplitude, swing=swing,
                                  vid_max=V.candidate_vid_max({'search': search}) if swing else None)
                            calls += 1
                            row['spice_calls'] += 1
                            log = P.invoke(cir, folder)
                            hd3, detail = V.parse_hd3(np.loadtxt(folder / 'hd3.txt'), tone, amplitude)
                            measured[name] = dict(log=log, hd3=hd3, detail=detail, folder=folder)
                        except (ValueError, RuntimeError, OSError) as exc:
                            errors.append(f'{name}: {exc}')
                    row.update(hd3_100mhz_dbc=measured.get('s4', {}).get('hd3'),
                               hd3_nyq_dbc=measured.get('nyquist', {}).get('hd3'),
                               hd3_details={k: v['detail'] for k, v in measured.items()})
                    if not errors:
                        try:
                            nyq = measured['nyquist']
                            pt = V.measured_point(deck, ac_log, nyq['log'], ac_folder,
                                  np.loadtxt(nyq['folder'] / 'swing.txt'), nyq['hd3'], nyq['detail'])
                            row.update(V.links_for_point(pt, measured['s4']['hd3'], losses, request, area), ok=True)
                        except (ValueError, RuntimeError, OSError) as exc:
                            errors.append(str(exc))
                    if errors:
                        row['reason'] = '; '.join(errors)
                    rows.append(row)
                    journal.write(json.dumps(row, allow_nan=False) + '\n')
                    journal.flush()
                    update(f'Fresh physical circuit: {len(rows)}/45 PVT corners checked', 20 + int(60 * len(rows)/45))
            fixed = V.summarise(rows, losses, search['representative_channel_loss_db'])
            verification = verification_records(rows, search)
            nominal_row = next(r for r in rows if r['corner'] == 'tt/1.00/27C')
            nominal = dict(ok=nominal_row['ok'], verdict='ok' if nominal_row['ok'] else 'invalid',
                           reason=nominal_row.get('reason'), params=params, reward=None,
                           design_id='physical-' + signature[:16], feasible=False, meas={})
            if nominal_row['ok']:
                m = dict(nominal_row['meas'])
                link = next(r for r in nominal_row['links'] if r['loss_db'] == search['representative_channel_loss_db'])
                m.update(_f_peak_ghz=2.5 * 2**m['f_peak_oct'], _noise_mv=m['inoise_vrms']*1e3,
                         _power_mw=m['power_w']*1e3, area_mm2=area['geometry_subtotal_mm2'],
                         eye_h_v=link.get('bridge_eye_h_v'), eye_w_ui=link.get('bridge_eye_w_ui'),
                         hd3_nyq_dbc=nominal_row['hd3_nyq_dbc'], hd3_100mhz_dbc=nominal_row['hd3_100mhz_dbc'])
                nominal.update(meas=m, feasible=bool(link['model_pass'] and link['control_pass']))
            search['design_id'] = nominal['design_id']
            path = out / 'design.cir'
            # Invalid TT still exports its exact attempted deck, labelled NEEDS WORK.
            if not path.exists():
                shutil.copyfile(out / 'tt_1.00_27/ac_noise/design.cir', path)
            result = dict(request=request, method='rl-physical', robust_search=True, search=search,
                          nominal=nominal, verification=verification, area_inventory=area_inventory(path.read_text()),
                          physical_evidence=dict(directory=str(out), deck_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                                 circuit_signature=signature, spice_calls=calls),
                          product_readiness_audit=dict(fixed=fixed),
                          simulations=dict(search=0, measure=2, verify=calls-2, total=calls),
                          wall_s=time.perf_counter()-started,
                          peaking_is_a_band_not_a_target='Both requested response tolerances are checked by the fresh electrical gate; unknown full S7 area is excluded.')
            result['request_match'] = request_miss(result)
            result['implementation_scope'] = implementation_scope(result)
            if calls > MAX_CALLS:
                raise RuntimeError('physical product exceeded its frozen call budget')
            P.write_json(out / 'summary.json', dict(fixed=fixed, spice_calls=calls,
                         electrical_model_pass=is_verified(result), full_product_compliance=False,
                         wall_s=result['wall_s']))
            P.write_json(out / 'result.json', result)
            return result
        except Exception as exc:
            P.write_json(out / 'failure.json', dict(error=f'{type(exc).__name__}: {exc}',
                         spice_calls=calls, electrical_model_pass=False, full_product_compliance=False))
            raise
        finally:
            hashes = {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in out.rglob('*') if p.is_file() and 'runlock' not in p.name
                      and p.name != 'evidence_sha256.json'}
            P.write_json(out / 'evidence_sha256.json', hashes)


def report(design):
    v, n = design['verification'], design['nominal']
    m = n.get('meas') or {}
    lines = ['NEBULA - fixed physical-bias circuit',
             'ELECTRICAL MODEL PASS' if is_verified(design) else 'NEEDS WORK - physical verification did not pass',
             f"One unchanged setting: {design['search']['setting']}; {v['n_pass']}/{v['n_points']} conditions pass.",
             f"Fresh SPICE calls: {design['simulations']['total']}."]
    if n.get('ok'):
        lines += [f"TT peaking: {m['peaking_db']:.4f} dB at {m['_f_peak_ghz']:.6f} GHz.",
                  f"TT CTLE + reference power: {m['_power_mw']:.4f} mW; noise: {m['_noise_mv']:.4f} mVrms."]
    lines += implementation_scope(design)['notes']
    return '\n'.join(lines)
