"""Physical bias is an opt-in prototype, never a relabelled ideal source."""
from pathlib import Path
import pytest

from nebula.device.bias_reference import reference_geometry, physical_reference_deck
from nebula.device.passives import capacitor_geometry
from nebula.report.product_scope import area_inventory, circuit_lines
from nebula.report.schematic import _check_topology

SOURCE = Path(__file__).resolve().parents[1] / 'product_audits/entry101_fixed490_20260906/design.cir'


def prototype():
    original = SOURCE.read_text()
    # Synthetic gate voltage for a unit test, not a measured calibration.
    geo = reference_geometry(original, 0.9)
    return original, geo, physical_reference_deck(original, geo)


def test_physical_reference_connectivity_and_no_ideal_bias():
    original, geo, deck = prototype()
    lines = circuit_lines(deck)
    assert not any(x.startswith(('iref ', 'cbyp ')) for x in lines)
    assert any(x.startswith('xbpref p_bias p_bias vdd vdd sky130_fd_pr__pfet_01v8') for x in lines)
    assert any(x.startswith('xbpfeed nbias p_bias vdd vdd sky130_fd_pr__pfet_01v8') for x in lines)
    assert any(x.startswith('xrbias p_bias 0 0 sky130_fd_pr__res_high_po') for x in lines)
    assert any(x.startswith('xcbyp nbias 0 sky130_fd_pr__cap_mim_m3_1') for x in lines)
    assert 'Iref  vdd nbias {IREF}' in original
    assert geo.resistor.r_target_ohm == pytest.approx(0.9 / 0.000226681162)


def test_area_counts_mim_resistor_and_both_reference_mos():
    original, geo, deck = prototype()
    old, new = area_inventory(original), area_inventory(deck)
    delta = geo.capacitor.area_um2 + geo.resistor.area_um2 + 2 * geo.w_um * geo.l_um
    assert new['geometry_subtotal_mm2'] - old['geometry_subtotal_mm2'] == pytest.approx(delta * 1e-6)
    assert new['full_area_mm2'] is None and new['s7_status'] == 'NOT_VERIFIED'
    assert not {'iref', 'cbyp'} & set(new['unresolved'])
    assert 'no physical implementation' not in new['note']
    assert 'common-mode generation' in new['not_in_netlist']
    assert geo.capacitor == capacitor_geometry(1e-11)


def test_physical_cap_native_multiplier_counts_all_plates():
    _, _, deck = prototype()
    # All mapper-generated instances carry an explicit native m parameter.
    line = next(x for x in deck.splitlines() if x.startswith('Xcbyp '))
    doubled = deck.replace(line, line.replace('m=1', 'm=2'))
    a, b = area_inventory(deck), area_inventory(doubled)
    plate = next(x['geometry_um2'] for x in a['components'] if x['name'] == 'xcbyp')
    assert b['geometry_subtotal_mm2'] - a['geometry_subtotal_mm2'] == pytest.approx(plate * 1e-6)


@pytest.mark.parametrize('voltage', [0, -1, 1.8, float('nan'), float('inf')])
def test_invalid_calibration_fails(voltage):
    with pytest.raises(ValueError):
        reference_geometry(SOURCE.read_text(), voltage)


def test_double_application_and_wrong_connectivity_refused():
    original, geo, deck = prototype()
    with pytest.raises(ValueError):
        physical_reference_deck(deck, geo)
    with pytest.raises(ValueError):
        physical_reference_deck(original.replace('Iref  vdd nbias', 'Iref  vdd outp'), geo)


def test_old_picture_cannot_misrepresent_new_physical_bias():
    original, _, deck = prototype()
    _check_topology(original)
    with pytest.raises(ValueError, match='topology'):
        _check_topology(deck)


def test_probe_scalar_is_fail_closed():
    from nebula.experiments.exp_physical_bias import scalar
    assert scalar('v(nbias) = 0.8', 'v(nbias)') == .8
    for log in ('', 'v(nbias) = nan', 'v(nbias) = 1e999'):
        with pytest.raises(ValueError):
            scalar(log, 'v(nbias)')


def test_probe_corner_changes_only_allowed_conditions():
    from nebula.experiments.exp_physical_bias import corner_deck
    from nebula.report.product_scope import circuit_signature
    _, _, deck = prototype()
    corner = corner_deck(deck, 'ss', .95, 125)
    assert circuit_signature(corner) == circuit_signature(deck)
    assert '.temp 125' in corner and 'VDD=1.71' in corner


def test_probe_refuses_complex_db_vector(tmp_path):
    import numpy as np
    from nebula.experiments.exp_physical_bias import extract
    np.savetxt(tmp_path / 'ac.txt', [[1e6, 2., .1], [2e6, 3., .2]])
    with pytest.raises(ValueError, match='imaginary'):
        extract('', tmp_path, 1.8)


def test_probe_reads_printed_supply_current_not_vector_alias(tmp_path):
    import numpy as np
    from nebula.experiments.exp_physical_bias import extract, NFET, PFET
    # Synthetic instrument output, not circuit evidence.
    np.savetxt(tmp_path / 'ac.txt', np.column_stack((np.logspace(8, 10, 5), [1, 3, 5, 3, 1])))
    log = 'g_dc = 0\ng_nyq = 3\ng_pk = 5 at= 1e9\ni(vdd) = -0.002\n'
    for instance, family, current in [('xmr', NFET, .0001), ('xmt1', NFET, .0008),
                                       ('xbpref', PFET, .0001), ('xbpfeed', PFET, .0001)]:
        log += f'@m.{instance}.m{family}[id] = {current}\n'
    log += 'v(nbias) = 0.8\nv(p_bias) = 0.5\ninoise_total = 0.0005\n'
    result = extract(log, tmp_path, 1.8)
    assert result['power_ctle_and_bias_w'] == pytest.approx(.0036)
    assert result['noise_vrms'] == .0005  # RMS volts, not sqrt(RMS volts).
