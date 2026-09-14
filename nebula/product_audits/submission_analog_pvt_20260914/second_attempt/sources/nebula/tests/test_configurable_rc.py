"""Entry 128 boundaries; synthetic responses are tests, never measured evidence."""
import numpy as np
import pytest

from nebula.device import configurable_rc as R


def test_registered_membership_and_one_geometry_per_bank():
    assert len(R.GEOMETRIES)==9 and len(R.biases())==81
    deck=R.screen_deck(R.GEOMETRIES[0])
    assert deck.count('.subckt rc_tuned ')==1
    assert deck.count('.subckt rc_fixed ')==1
    assert len([s for s in deck.splitlines() if s.startswith('Xcase')])==82
    assert deck.count('.lib ')==1 and '.model ' not in deck
    assert 'set wr_singlescale' in deck
    assert 'ac dec 50 1meg 100g' in deck


def test_actual_controlled_devices_and_metadata_not_fixed_rs_cs():
    body=R.circuit_body(R.GEOMETRIES[-1])
    assert 'Xrc_switch rc_mid rc_gate s2 0 sky130_fd_pr__nfet_01v8 W=80 L=0.15 nf=2' in body
    assert body.count('sky130_fd_pr__cap_var_lvt w=5 l=0.5 vm=1 m=500')==2
    assert ' RS=' not in body and ' CS=' not in body
    for token in ('Xrc_rmax','Xrc_branch','Xrc_rfeed','Xrc_cfeed','Xrc_rbypass','Xrc_cbypass','Xrc_fixedc'):
        assert token in body
    assert not any(s.split()[0].lower() in ('vdd','vcm','vid','einp','einn') for s in body.splitlines() if s.strip())
    assert R.geometry(R.GEOMETRIES[-1])['geometry_subtotal_mm2']<.05
    assert not R.geometry(R.GEOMETRIES[-1])['routed_layout']


@pytest.mark.parametrize('geom',[(0,0),(500,3e-12),(500.5,0),(250,-1e-12)])
def test_unregistered_geometry_rejected(geom):
    with pytest.raises(ValueError): R.circuit_body(geom)


def test_missing_baseline_parts_not_silently_accepted():
    with pytest.raises(ValueError): R.circuit_body(R.GEOMETRIES[0],source='* incomplete\n.end\n')


def synthetic_table():
    f=R.FREQUENCIES_HZ
    # A known stable lead/lag response with an interior peak.
    h=(1+1j*f/2e8)/((1+1j*f/1e9)*(1+1j*f/4e9))
    a=np.empty((len(f),7)); a[:,0]=f
    for j,y in enumerate((-.5*h,.5*h,np.ones(len(f)))):
        a[:,1+2*j]=np.real(y); a[:,2+2*j]=np.imag(y)
    return a,h


def test_parse_complex_response_and_wrong_axes_inputs_fail():
    a,h=synthetic_table()
    parsed=R.parse_ac(a,1)
    assert np.allclose(parsed[:,0],h)
    for kind in ('axis','input','nan','shape'):
        b=a.copy()
        if kind=='axis': b[10,0]*=1.01
        if kind=='input': b[:,5]=.5
        if kind=='nan': b[1,2]=np.nan
        if kind=='shape': b=b[:-1]
        with pytest.raises(ValueError): R.parse_ac(b,1)


def test_peak_is_measured_not_assumed_and_no_peak_is_retained():
    _,h=synthetic_table()
    r=R.response_metrics(h)
    assert r['interior_peak'] and r['boost_db']>0
    r=R.response_metrics(1/(1+1j*R.FREQUENCIES_HZ/1e9))
    assert not r['interior_peak'] and not r['ac_shape_pass']
    with pytest.raises(ValueError): R.response_metrics(np.zeros(251))


def test_baseline_comparison_can_reject_plausible_wrong_gain():
    _,h=synthetic_table(); reference=20*np.log10(np.abs(h))
    assert R.baseline_matches(h,reference)
    assert not R.baseline_matches(1.001*h,reference)


def test_dc_shape_and_negative_power_are_rejected():
    layout=R.op_layout(None,1)
    a=np.zeros((1,len(layout)+1)); a[0,1]=-.003
    # Missing data is a hard instrument error, not a partial result.
    with pytest.raises(ValueError): R.parse_op(a[:,:-1],None,1)
    a[0,1]=.003
    with pytest.raises(ValueError): R.parse_op(a,None,1)


def test_rc_nominal_sizing_uses_measured_switch_reference():
    d=R.resistor_targets()
    assert 0<d['branch_poly_ohm']<d['rmax_ohm']
    assert np.isclose(1/(1/d['rmax_ohm']+1/(d['branch_poly_ohm']+d['measured_ron_ohm'])),d['nominal_low_ohm'])


def test_geometry_counts_drawn_cells_once_and_both_control_filters():
    for g in R.GEOMETRIES:
        x=R.geometry(g)
        assert x['varactor_active_um2']==2*g[0]*5*.5
        rows={r['name']:r for r in x['added_components']}
        assert rows['Xrc_switch']['geometry_um2']==80*.15  # nf is NOT another multiplier
        assert rows['Xrc_cbypass']['geometry_um2']>4000
        assert rows['Xrc_rbypass']['geometry_um2']>400
        assert np.isclose(sum(r['geometry_um2'] for r in rows.values()),x['varactor_active_um2']+x['added_nonvaractor_um2'])


def test_schedule_stops_calibration_and_keeps_all_screen_failures():
    from nebula.experiments.exp_configurable_rc import schedule
    calls=[]
    def failure(geometry):
        calls.append(geometry)
        return {'instrument_ok':False,'baseline_matches':False}
    assert not schedule(failure)['characterization_complete']
    assert calls==[None]
    calls.clear()
    def mixed(geometry):
        calls.append(geometry)
        return {'instrument_ok':len(calls)!=4,'baseline_matches':True}
    assert not schedule(mixed)['characterization_complete']
    assert len(calls)==10
