"""Entry 127 instrument contracts; synthetic arrays are tests, not evidence."""
import numpy as np
import pytest

from nebula.common.types import Corner
from nebula.device import varactor_probe as V
from nebula.experiments import exp_varactor_probe as E


def table(values):
    y=np.asarray(values,dtype=complex)
    if y.ndim==1: y=np.broadcast_to(y,(4,len(y)))
    result=np.empty((4,1+2*y.shape[1]))
    result[:,0]=V.FREQUENCIES_HZ
    result[:,1::2]=y.real
    result[:,2::2]=y.imag
    return result


def test_complex_current_parser_and_hand_computed_differential_admittance():
    y=.001+1j*2*np.pi*np.array(V.FREQUENCIES_HZ)*2e-12
    raw=table(np.column_stack((-y,y)))
    currents=V.parse_ac(raw,2)
    assert np.array_equal(currents[:,0],-y)
    m=V.metrics(-.5*(currents[:,0]-currents[:,1]))
    assert np.allclose(m['parallel_g_s'],.001,rtol=1e-14)
    assert np.allclose(m['capacitance_f'],2e-12,rtol=1e-14)
    assert np.allclose(m['quality_factor'],y.imag/.001,rtol=1e-14)
    assert np.allclose(m['series_resistance_ohm'],(1/y).real,rtol=1e-14)


@pytest.mark.parametrize('kind',['axis','missing','nan','shape','polarity'])
def test_malformed_or_reversed_ac_is_not_a_measurement(kind):
    raw=table([.001+.01j])
    if kind=='axis': raw[2,0]+=100
    if kind=='missing': raw=raw[:3]
    if kind=='nan': raw[1,1]=np.nan
    if kind=='shape': raw=np.c_[raw,np.ones(4)]
    if kind=='polarity': raw[:,1:]*=-1
    with pytest.raises(ValueError):
        V.metrics(V.parse_ac(raw,1)[:,0])


def test_op_exact_counts_bias_and_model_domain_fail_loudly():
    expected=[.5,.45,0.]
    V.check_op(np.array([[0.,*expected]]),expected)
    for raw in (np.array([[0.,.5,.44,0.]]),np.array([[0.,.5,.45]]),
                np.array([[0.,.5,np.nan,0.]])):
        with pytest.raises(ValueError): V.check_op(raw,expected)
    with pytest.raises(ValueError): V.validate_bias(.35,2.4)


def test_native_multiplier_gate_can_fail_and_vm_is_not_used_as_equivalence():
    unit=np.array([.001+.02j]*4)
    y=np.column_stack([unit,4*unit,4*unit,3.9*unit,500*unit,500*unit]*6)
    result=V.calibration_metrics(y)
    assert result['native_m_equivalent']
    assert not result['vm4_equivalent']
    y[:,4]*=1.01
    assert not V.calibration_metrics(y)['native_m_equivalent']


def test_decks_have_real_complete_cells_and_external_biases_only():
    c=Corner('tt',1,27)
    cal=V.calibration_deck()
    assert cal.count('sky130_fd_pr__cap_var_lvt w=5 l=0.5')==6*(1+1+4+1+1+500)
    assert 'vm=4' in cal and 'm=500' in cal
    main=V.probe_deck(c)
    assert main.count('sky130_fd_pr__cap_var_lvt w=5 l=0.5')==410
    assert main.count('vm=1 m=500')==410
    assert 'vm=500' not in main
    assert 'sky130.lib.spice' in main and 'pdk_trim' not in main
    assert '.model ' not in main and '.subckt ' not in main
    assert 'set wr_singlescale' in main
    assert 'ac lin 4 1250000000 5000000000' in main
    assert len(V.probe_members())==205
    assert V.candidate_geometry()['active_geometry_um2']==2500


@pytest.mark.parametrize('source,control',[(-.1,0),(.5,-.1),(.5,2.1),(float('nan'),0)])
def test_invalid_bias_arguments(source,control):
    with pytest.raises(ValueError): V.validate_bias(source,control)


def test_schedule_stops_on_calibration_failure_and_bills_every_later_failure():
    calls=[]
    def bad_cal(kind,corner):
        calls.append((kind,corner))
        return {'instrument_ok':True,'native_m_equivalent':False}
    assert not E.schedule(bad_cal)['characterization_complete']
    assert len(calls)==1
    calls.clear()
    def one_bad(kind,corner):
        calls.append((kind,corner))
        return {'instrument_ok':len(calls)!=7,'native_m_equivalent':True}
    result=E.schedule(one_bad)
    assert len(calls)==46 and len(result['pvt'])==45
    assert not result['characterization_complete']
    assert not result['configurable_ctle_verified']


def test_probe_projection_keeps_loss_and_rejects_side_imbalance():
    currents=np.empty((4,410),dtype=complex)
    for i,(_,fraction) in enumerate(V.probe_members()):
        y=.001+1j*2*np.pi*np.array(V.FREQUENCIES_HZ)*(2-fraction)*1e-12
        currents[:,2*i]=-y
        currents[:,2*i+1]=y
    result=V.probe_metrics(currents,Corner('tt',1,27))
    assert len(result['rows'])==205
    assert all(result['capacitance_strictly_decreases'].values())
    assert result['ranges_by_frequency']['parallel_g_s'][0]==[.001,.001]
    assert not result['configurable_ctle_verified']
    currents[2,42]*=1.01
    with pytest.raises(ValueError,match='sides disagree'):
        V.probe_metrics(currents,Corner('tt',1,27))


def test_grounded_terminal_transfer_current_must_scale_too():
    raw=np.empty((4,72),dtype=complex)
    scales=(1,4,4,3.9,500,500)
    for i,(_,drive,kind) in enumerate(V.calibration_layout()):
        y=(.001+.02j)*scales[V.CALIBRATION_KINDS.index(kind)]
        raw[:,2*i:2*i+2]=(-y,.9*y) if drive=='c0' else (.9*y,-y)
    assert V.calibration_currents_metrics(raw)['native_m_equivalent']
    raw[:,3]*=1.01
    assert not V.calibration_currents_metrics(raw)['native_m_equivalent']
