"""The final report must be bound to physical evidence, not the older demo."""
import pytest

from nebula.report import competition_submission as R


def test_final_report_uses_verified_physical_export():
    e = R.load_evidence()
    assert e['product']['method'] == 'rl-physical'
    assert len(e['rows']) == 45
    assert e['conditions'] == 315
    assert e['manifest_count'] == 616
    assert e['area']['geometry_subtotal_mm2'] == pytest.approx(.0078545111070017)
    assert e['summary']['fixed']['full_product_compliance'] is False
    assert e['winning']['benchmark']['aggregate']['candidate_visit_reduction'] == pytest.approx(91.76574716034814)
    assert e['winning']['recovery']['n_targets_recovered'] == 2
    assert [x['first_passing_setting'] for x in e['winning']['recovery']['targets']] == [401, 474]


def test_final_report_rejects_identity_drift(monkeypatch):
    original = R.read_rows
    def changed(path):
        rows = original(path)
        rows[-1]['circuit_signature'] = 'wrong'
        return rows
    monkeypatch.setattr(R, 'read_rows', changed)
    with pytest.raises(ValueError, match='identity'):
        R.load_evidence()


def test_final_report_rejects_changed_raw_artifact(tmp_path):
    (tmp_path / 'wave.txt').write_text('changed')
    with pytest.raises(ValueError, match='hash'):
        R.verify_hashes(tmp_path, {'wave.txt': '0' * 64})


def test_final_report_rejects_manifest_path_escape(tmp_path):
    with pytest.raises(ValueError, match='path'):
        R.verify_hashes(tmp_path, {'../outside': '0' * 64})


def test_final_report_metrics_are_derived_not_old_candidate():
    e = R.load_evidence()
    m = R.metrics(e)
    assert m['nom_peak'] == pytest.approx(8.834174025328473)
    assert m['nom_freq'] == pytest.approx(1.768989568062205)
    assert m['min_eye_mv'] == pytest.approx(133.51734348134464)
    assert m['max_power_mw'] < 9.803
    assert m['min_frequency_margin_oct'] > 0


def test_final_report_schematic_checks_actual_connectivity():
    from nebula.report.physical_schematic import physical_components
    deck = (R.DEMO / 'design.cir').read_text()
    c = physical_components(deck)
    assert len([n for n in c if n.startswith('x')]) == 27
    assert c['xcbyp']['geometry_um2'] == pytest.approx(4976.597025)
    with pytest.raises(ValueError):
        physical_components(deck.replace('Xbpfeed nbias p_bias vdd vdd', 'Xbpfeed p_bias nbias vdd vdd'))
