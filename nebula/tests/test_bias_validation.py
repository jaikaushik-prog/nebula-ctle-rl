"""Fail-capable boundaries for the exact-deck electrical validation."""
from pathlib import Path
import numpy as np
import pytest

from nebula.experiments import exp_physical_bias_validation as V
from nebula.report.product_scope import circuit_signature

SOURCE = Path(__file__).resolve().parents[1] / 'product_audits/entry103_physical_bias_20260906'


@pytest.mark.parametrize('tone,amplitude,swing', [(100e6, .1, False), (2.5e9, .267354, True)])
def test_transient_changes_stimulus_only_and_keeps_physical_bias(tone, amplitude, swing):
    original = (SOURCE / 'tt_1.00_27/design.cir').read_text()
    deck = V.measurement_deck(original, tone, amplitude, swing=swing, vid_max=.8 if swing else None)
    assert circuit_signature(deck) == circuit_signature(original)
    assert 'Xbpfeed nbias p_bias vdd vdd' in deck
    assert 'Xcbyp nbias 0' in deck
    assert '\nac dec' not in deck and '\nnoise ' not in deck
    assert ('dc vid -0.8 0.8 0.004' in deck) == swing
    assert 'wrdata hd3.txt vd_t' in deck


def test_missing_or_already_modulated_input_is_refused():
    original = (SOURCE / 'tt_1.00_27/design.cir').read_text()
    changed = original.replace('Vid   vid 0 dc 0 ac 1', 'Vid vid 0 sin(0 .1 1e8)')
    with pytest.raises(ValueError):
        V.measurement_deck(changed, 100e6, .1, swing=False)


def test_swing_parser_uses_differential_output_and_rejects_bad_grid():
    raw = np.zeros((5, 16))
    raw[:, 0::2] = np.arange(5)[:, None] - 2
    raw[:, 1], raw[:, 3] = 1.2, .8
    raw[:, 5], raw[:, 7], raw[:, 11], raw[:, 13] = .6, .2, .6, .2
    raw[:, 9], raw[:, 15] = .001, .002
    result = V.parse_swing(raw)
    assert np.allclose(result['vod'], .4)
    assert result['sat_ok'].all()
    assert np.allclose(result['id_min'], .001)
    for malformed in (raw[:, :3], raw[::-1], raw * float('nan')):
        with pytest.raises(ValueError):
            V.parse_swing(malformed)


def test_hd3_parser_records_actual_drive_and_rejects_irregular_time():
    tone, amplitude = 2.5e9, .267354
    t = np.linspace(5/tone, 25/tone, 2001)
    wave = .2*np.sin(2*np.pi*tone*t) + .0002*np.sin(6*np.pi*tone*t)
    value, detail = V.parse_hd3(np.column_stack((t, wave)), tone, amplitude)
    assert value == pytest.approx(-60, abs=1e-7)
    assert detail['vin_diff_pk_v'] == amplitude
    t[30] += 1e-12
    with pytest.raises(ValueError, match='uniform'):
        V.parse_hd3(np.column_stack((t, wave)), tone, amplitude)


def test_source_checks_hashes_and_complete_corner_membership():
    rows, signature = V.load_source(SOURCE)
    assert len(rows) == 45 and len({r['key'] for r in rows}) == 45
    assert signature == circuit_signature((SOURCE / 'design.cir').read_text())


def test_electrical_gate_never_certifies_unknown_area():
    assert 'S7_area' not in V.ELECTRICAL_SPECS
    assert 'S4_hd3' in V.ELECTRICAL_SPECS and 'S4_hd3_nyq' in V.ELECTRICAL_SPECS
    with pytest.raises(ValueError):
        V.summarise([], [7.5], 7.5)


def test_point_adapter_uses_explicit_input_mos_and_rejects_changed_bias():
    sub = SOURCE / 'tt_1.00_27'
    deck, log = (sub / 'design.cir').read_text(), (sub / 'ngspice.log').read_text()
    raw = np.zeros((401, 16))
    x = np.linspace(-.8, .8, 401)
    raw[:, 0::2] = x[:, None]
    raw[:, 1], raw[:, 3] = 1.2-.2*x, 1.2+.2*x
    raw[:, 5], raw[:, 7], raw[:, 11], raw[:, 13] = .6, .2, .6, .2
    raw[:, 9], raw[:, 15] = .001, .002
    pt = V.measured_point(deck, log, log, sub, raw, -50., {})
    assert pt.gm == pytest.approx(.01019719341323120)
    assert pt.id_a == pytest.approx(.001710406188841514)
    assert pt.power_measured_w == pytest.approx(.006965786645056476)
    changed = log.replace('i(vdd) = -3.86988146947582e-03', 'i(vdd) = -4e-03')
    with pytest.raises(ValueError, match='fresh DC point differs'):
        V.measured_point(deck, log, changed, sub, raw, -50., {})


def test_altered_source_hash_is_refused_before_any_simulation(tmp_path):
    import json
    (tmp_path / 'ngspice.log').write_text('tampered')
    (tmp_path / 'reparse_provenance.json').write_text(json.dumps({'raw_sha256': {'ngspice.log': '0'*64}}))
    with pytest.raises(ValueError, match='changed source hash'):
        V.load_source(tmp_path)


def test_all_electrical_passes_still_leave_full_receiver_unverified():
    rows = [{'corner': V.A._label(c), 'setting': 490, 'circuit_signature': 'same', 'ok': True,
             'hd3_100mhz_dbc': -50., 'hd3_nyq_dbc': -40., 'fit_residual_db': .1,
             'links': [{'loss_db': 7.5, 'model_pass': True, 'control_pass': True,
                        'failed_specs': [], 'unmeasured_specs': [],
                        'policies': {p: {'eye_h_v': .2, 'eye_w_ui': .7} for p in V.DFE.POLICIES}}]}
            for c in V.all_corners()]
    summary = V.summarise(rows, [7.5], 7.5)
    assert summary['n_model_pass'] == 45
    assert summary['full_product_compliance'] is False
    assert summary['area_status'] == 'NOT_VERIFIED'
    assert summary['excluded_full_receiver_specs'] == ['S7_area']


def test_swing_instrument_uses_existing_attenuation_adjustment():
    import json
    from nebula.experiments.exp_physical_bias_swing_fix import dc_deck, candidate_vid_max
    from nebula.experiments.adaptive_screen import _attenuation_run_args
    candidate = json.loads((SOURCE.parent / 'entry101_fixed490_20260906/candidate.json').read_text())
    search = candidate['search']
    expected = _attenuation_run_args(search['atten_code'], search['atten_max_x'])['vid_max']
    assert candidate_vid_max(candidate) == expected and expected > .8
    source = (SOURCE / 'tt_1.00_27/design.cir').read_text()
    deck = dc_deck(source, expected)
    assert f'dc vid -{expected} {expected} 0.004' in deck
    assert 'tran ' not in deck and '\nac dec' not in deck
    assert circuit_signature(deck) == circuit_signature(source)
    with pytest.raises(ValueError, match='explicit attenuation-adjusted'):
        V.measurement_deck(source, 2.5e9, .267354, swing=True)
