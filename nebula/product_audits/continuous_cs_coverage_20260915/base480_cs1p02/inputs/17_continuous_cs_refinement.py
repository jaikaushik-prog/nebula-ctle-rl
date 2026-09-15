"""Preregistered continuous-Cs candidates; canonical physical measurement gate."""
from __future__ import annotations
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shutil
import time
import numpy as np
from nebula import physical_design as D
from nebula.rl.contract import ACTION_NAMES, ACTION_SPACE, sizing_from_u

ROOT, P, V, S, MAX_CALLS = D.ROOT, D.P, D.V, D.S, D.MAX_CALLS
capture_candidate, verification_records, is_verified = D.capture_candidate, D.verification_records, D.is_verified
_record_call_progress = D._record_call_progress
reference_geometry, calibration_deck = D.reference_geometry, D.calibration_deck
physical_reference_deck = D.physical_reference_deck
circuit_signature, area_inventory = D.circuit_signature, D.area_inventory
implementation_scope, all_corners = D.implementation_scope, D.all_corners
FACTORS = (1.01, 1.02, 1.03)
PLAN = ROOT / 'nebula/TARGET_COVERAGE_CS_PLAN_20260915.md'
BASE = ROOT / 'nebula/product_audits/submission_recovery_20260915/coverage_005_6db_2p5ghz_rl_r0/output/physical_recovery/candidate_01_setting_480/result.json'
BASE_SHA256 = 'f23a102c6546fde1f70dacc1ba60b64847f8b0dadf8c849cdc27177d59165e54'

class BudgetExceeded(Exception):
    """Campaign stops before charging a call whose complete timeout cannot fit."""

def load_base():
    if hashlib.sha256(BASE.read_bytes()).hexdigest() != BASE_SHA256:
        raise ValueError('preregistered base evidence changed')
    return json.loads(BASE.read_text(encoding='utf-8'))

def candidate_id(factor):
    if factor not in FACTORS:
        raise ValueError('unregistered Cs factor')
    return 'base480_cs' + format(factor, '.2f').replace('.', 'p')

def make_candidate(factor):
    identity = candidate_id(factor)
    search = deepcopy(load_base()['search'])
    u = list(search['u'])
    index = ACTION_NAMES.index('cs')
    dim = ACTION_SPACE[index]
    cs = sizing_from_u(u).params['cs'] * factor
    if not dim.lo <= cs <= dim.hi:
        raise ValueError('Cs outside unchanged action domain')
    u[index] = float(dim.to_normalised(cs))
    retained = ('u', 'atten_code', 'atten_max_x', 'channel_loss_mode',
                'channel_losses_db', 'representative_channel_loss_db')
    search = {key: search[key] for key in retained}
    search.update(u=u, setting=identity, candidate_id=identity, bank_setting=None,
                  bank_code=None, base_setting=480, cs_factor=factor,
                  which_path='deterministic-continuous-cs-refinement',
                  eligibility_scope='Continuous candidate; no legacy-bank eligibility claim.')
    return search

def call_fits(now, deadline, stage):
    return now + (120. if stage == 'legacy_candidate' else 60.) <= deadline

def _snapshots(out):
    D._snapshots(out, (Path(__file__), PLAN))

def run_candidate(factor, evidence_dir, deadline):
    peaking_db, f_peak_hz, progress = 6., 2.5e9, None
    if evidence_dir is None:
        raise ValueError('physical mode requires a new evidence directory')
    out = Path(evidence_dir).resolve()
    out.mkdir(parents=True, exist_ok=False)
    from nebula.experiments.runlock import hold
    from nebula.design import request_miss
    from nebula.link.config import LinkConfig
    request = dict(peaking_db=float(peaking_db), f_peak_hz=float(f_peak_hz), f_peak_ghz=float(f_peak_hz)/1e9)
    started, calls = time.perf_counter(), 0

    def record_calls(stage, invocation_state):
        _record_call_progress(out, calls, stage, invocation_state, time.perf_counter()-started)

    def charge(stage):
        nonlocal calls
        if not call_fits(time.perf_counter(), deadline, stage):
            raise BudgetExceeded('insufficient wall budget for complete invocation timeout')
        calls += 1
        record_calls(stage, 'potentially_active')

    record_calls('created', 'none_charged')

    def update(message, percent):
        if progress:
            progress(message, percent)

    with hold('physical_product', here=out):
        try:
            _snapshots(out)
            search = make_candidate(factor)
            old = dict(base_result=str(BASE.relative_to(ROOT)), base_result_sha256=BASE_SHA256,
                       base_setting=480, bank_setting=None, candidate_id=search['candidate_id'],
                       scope='Provenance only; fresh physical measurements determine acceptance.')
            P.write_json(out / 'legacy_proposal_not_physical_evidence.json', old)
            P.write_json(out / 'candidate.json', dict(request=request, search=search))
            update('Building the physical reference and MIM bypass', 18)
            charge('legacy_candidate')
            source, params = capture_candidate(search, out / 'legacy_candidate')
            charge('calibration')
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
                        charge(f'{key}/ac_noise')
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
                            charge(f'{key}/{name}')
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
            record_calls('completed', 'verification_finished')
            P.write_json(out / 'summary.json', dict(fixed=fixed, spice_calls=calls,
                         electrical_model_pass=is_verified(result), full_product_compliance=False,
                         wall_s=result['wall_s']))
            P.write_json(out / 'result.json', result)
            return result
        except Exception as exc:
            record_calls('exception', 'exception')
            P.write_json(out / 'failure.json', dict(error=f'{type(exc).__name__}: {exc}',
                         spice_calls=calls, electrical_model_pass=False, full_product_compliance=False))
            raise
        finally:
            hashes = {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in out.rglob('*') if p.is_file() and 'runlock' not in p.name
                      and p.name != 'evidence_sha256.json'}
            P.write_json(out / 'evidence_sha256.json', hashes)
