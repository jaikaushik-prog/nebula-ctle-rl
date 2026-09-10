"""Fine controls change only external voltages on previously measured geometry."""
from pathlib import Path
import json
import numpy as np
import pytest

from nebula.device import configurable_rc as R, configurable_rc_serial as S
from nebula.device import configurable_rc_precision as Q, configurable_rc_fine as F


def raw_step(g,r,c):
    values=[]
    for i,key,_ in S.layout(g):
        v=.5
        if key=='supply_current_a': v=-.003
        if key=='vdd': v=1.8
        if key=='rctrl': v=1.8*r if i==0 else 0.
        if key=='cctrl': v=1.8*c if i==0 else 0.
        values.append(v)
    return np.array([0.,*values])


@pytest.mark.parametrize('g',[(250,0.),(500,0.)])
def test_fine_grid_keeps_the_measured_physical_geometry(g):
    d=F.deck(g)
    assert d.split('.control')[0]==Q.deck(g).split('.control')[0]
    assert len(F.biases())==441
    assert d.count('alter Vr0 ')==441 and d.count('alter Vc0 ')==441
    assert d.count('\nop\n')==441 and d.count('ac dec 50 1meg 100g')==441
    assert 'op_440.txt' in d and 'ac_440.txt' in d
    assert F.R_FRACTIONS[0]==.65 and F.R_FRACTIONS[-1]==.85
    assert F.C_FRACTIONS[0]==0. and F.C_FRACTIONS[-1]==.3
    with pytest.raises(ValueError): F.deck((100,0.))


def test_actual_controls_and_dc_primitives_are_checked():
    g=(500,0.);r=.73;c=.165
    raw=raw_step(g,r,c); rows=F.parse_op(raw,g,r,c)
    assert len(rows)==2 and rows[0]['dc_nodes_v']['rctrl']==1.8*r
    assert rows[0]['vdd_power_w']==.0054
    with pytest.raises(ValueError): F.parse_op(raw,g,r+.01,c)
    for malformed in (raw[:-1],np.full_like(raw,np.nan),raw[:,None]):
        with pytest.raises(ValueError): F.parse_op(malformed,g,r,c)


def test_fixed_reference_drift_remains_a_failure():
    a={'s1':.5,'supply_current_a':-.003}
    F.check_fixed(a,dict(a))
    with pytest.raises(ValueError): F.check_fixed(a,{**a,'s1':.5+2e-9})
    with pytest.raises(ValueError): F.check_fixed(a,{'s1':.5})


def test_target_selection_requires_both_tolerances_and_physical_pass():
    row={'r_fraction':.7,'c_fraction':.15,'ac_spec_pass':True,'boost_db':9.,'peak_frequency_hz':1.9e9}
    assert F.select_target([row],9.,1.9e9)['found']
    for changed in ({'ac_spec_pass':False},{'boost_db':9.51},{'peak_frequency_hz':2.01e9}):
        assert not F.select_target([{**row,**changed}],9.,1.9e9)['found']
    assert not F.select_target([],9.,1.9e9)['found']


def test_fine_schedule_is_bounded_and_stops_first_instrument_failure():
    calls=[]
    def fail(g): calls.append(g);return {'instrument_ok':False,'baseline_matches':False}
    result=F.schedule(fail)
    assert len(calls)==1 and not result['characterization_complete']
    calls.clear()
    def valid(g): calls.append(g);return {'instrument_ok':True,'baseline_matches':True,'rows':[]}
    result=F.schedule(valid)
    assert len(calls)==2 and result['characterization_complete']
    assert result['selected_geometry'] is None


def test_fine_registration_is_checkout_stable():
    root=Path(__file__).resolve().parents[2];name='nebula/CONFIGURABLE_RC_FINE_PLAN.md'
    assert name+' text eol=lf' in (root/'.gitattributes').read_text()
    assert b'\r\n' not in (root/name).read_bytes()


def test_new_dc_parser_matches_old_parser_on_real_shared_control():
    root=Path(__file__).resolve().parents[1]/'product_audits/entry130_configurable_rc_precision_20260910/candidate_n500_fixed0pf'
    i=R.biases().index((.7,.15))
    measured=F.parse_op(np.loadtxt(root/f'op_{i:03d}.txt'),(500,0.),.7,.15)[0]
    saved=json.loads((root/'result.json').read_text())['rows'][i]
    assert measured=={k:saved[k] for k in measured}


def test_geometry_ranking_prefers_coverage_and_requires_primary_identity():
    rows=[{'r_fraction':.7,'c_fraction':.15,'ac_spec_pass':True,'boost_db':b,'peak_frequency_hz':f} for b,f in F.TARGETS]
    def evaluate(g): return {'instrument_ok':True,'baseline_matches':True,'rows':rows[:-1] if g[0]==250 else rows}
    result=F.schedule(evaluate)
    assert result['selected_geometry']==(500,0.)
    assert [x['target_count'] for x in result['candidates']]==[8,9]
    no_primary=[r for r in rows if (r['boost_db'],r['peak_frequency_hz'])!=(9.,1.9e9)]
    assert F.schedule(lambda g:{'instrument_ok':True,'baseline_matches':True,'rows':no_primary})['selected_geometry'] is None


def test_missing_fine_step_is_rejected(tmp_path):
    from nebula.experiments.exp_configurable_rc_fine import extract
    with pytest.raises(ValueError,match='file membership'):
        extract(tmp_path,(500,0.),np.zeros(251))
