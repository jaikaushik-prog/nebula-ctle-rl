import subprocess
from pathlib import Path

import numpy as np
import pytest

from nebula.device import configurable_rc as R, configurable_rc_serial as S
from nebula.experiments import spice_capture as C


def test_scientific_registration_hashes_survive_windows_checkout():
    root=Path(__file__).resolve().parents[2]
    attrs=(root/'.gitattributes').read_text()
    for name in ('nebula/VARACTOR_PROBE_PLAN.md','nebula/CONFIGURABLE_RC_SCREEN_PLAN.md',
                 'nebula/CONFIGURABLE_RC_SERIAL_PLAN.md','nebula/device/spice/.spiceinit'):
        assert name+' text eol=lf' in attrs
        assert b'\r\n' not in (root/name).read_bytes()


def test_one_physical_geometry_and_only_external_sources_altered():
    d=S.deck(R.GEOMETRIES[0])
    assert len([s for s in d.splitlines() if s.startswith('Xcase')])==2
    assert 'Xcase0 ' in d and 'Xcase81 ' in d
    assert d.count('alter Vr0 ')==81 and d.count('alter Vc0 ')==81
    assert d.count('\nop\n')==81 and d.count('ac dec 50 1meg 100g')==81
    assert 'alterparam' not in d and d.count('.lib ')==1
    assert 'op_000.txt' in d and 'ac_080.txt' in d
    assert d.split('.subckt rc_tuned ')[1].split('.ends rc_tuned')[0] in R.screen_deck(R.GEOMETRIES[0])
    with pytest.raises(ValueError): S.deck(None)


def raw_ops(g):
    layout=S.layout(g)
    rows=[]
    for r,c in R.biases():
        values=[]
        for i,key,_ in layout:
            v=.5
            if key=='supply_current_a': v=-.003
            if key=='vdd': v=1.8
            if key=='rctrl': v=1.8*r if i==0 else 0
            if key=='cctrl': v=1.8*c if i==0 else 0
            values.append(v)
        rows.append(np.array([[0.,*values]]))
    return rows


def test_assembly_contains_each_real_step_without_imputation():
    g=R.GEOMETRIES[0]; raw=raw_ops(g)
    merged=S.assemble_op(raw,g)
    assert merged.shape==(1,1+len(R.op_layout(g)))
    dc=R.parse_op(merged,g)
    assert len(dc)==82
    for row,(r,c) in zip(dc,R.biases()):
        assert row['dc_nodes_v']['rctrl']==1.8*r
        assert row['dc_nodes_v']['cctrl']==1.8*c
    with pytest.raises(ValueError): S.assemble_op(raw[:-1],g)


@pytest.mark.parametrize('kind',['baseline','nan','shape','shifted_controls'])
def test_bad_step_is_not_valid_evidence(kind):
    g=R.GEOMETRIES[0]; raw=raw_ops(g); layout=S.layout(g)
    if kind=='baseline': raw[7][0,-1]+=.01
    if kind=='nan': raw[7][0,2]=np.nan
    if kind=='shape': raw[7]=raw[7][:,:-1]
    if kind=='shifted_controls':
        j=next(i for i,x in enumerate(layout) if x[0]==0 and x[1]=='rctrl')
        raw[7][0,j+1]+=.01
    with pytest.raises(ValueError): R.parse_op(S.assemble_op(raw,g),g)


def test_timeout_keeps_partial_log_even_if_exception_capture_types_differ(tmp_path,monkeypatch):
    def timeout(*args,**kw):
        assert kw['timeout']==180 and kw['stderr']==subprocess.STDOUT
        kw['stdout'].write(b'partial simulator diagnostic\n'); kw['stdout'].flush()
        raise subprocess.TimeoutExpired('ngspice',180,output='text output',stderr=b'bytes error')
    monkeypatch.setattr(C.subprocess,'run',timeout)
    with pytest.raises(ValueError,match='timed out'):
        C.invoke('* test only\n.end\n',tmp_path/'run',180)
    assert (tmp_path/'run/ngspice.log').read_bytes()==b'partial simulator diagnostic\n'


def test_zero_exit_with_silent_error_is_rejected(tmp_path,monkeypatch):
    def bad(*args,**kw):
        kw['stdout'].write(b'Error: missing vector\n')
        return subprocess.CompletedProcess(args[0],0)
    monkeypatch.setattr(C.subprocess,'run',bad)
    with pytest.raises(Exception): C.invoke('* test only\n.end\n',tmp_path/'run',180)
    assert 'Error:' in (tmp_path/'run/ngspice.log').read_text()


def test_frozen_old_timeout_handler_failure_is_reproduced_without_spice(tmp_path,monkeypatch):
    from nebula.experiments import exp_physical_bias as old
    def timeout(*args,**kw):
        raise subprocess.TimeoutExpired('ngspice',60,output='captured text',stderr=None)
    monkeypatch.setattr(old.subprocess,'run',timeout)
    with pytest.raises(TypeError,match='concat'):
        old.invoke('* test only\n.end\n',tmp_path/'old')
    assert not (tmp_path/'old/ngspice.log').exists()


def test_serial_schedule_stops_first_instrument_failure_and_counts_all_later_calls():
    from nebula.experiments.exp_configurable_rc_serial import schedule
    calls=[]
    def fail(g):
        calls.append(g); return {'instrument_ok':False,'baseline_matches':False}
    assert not schedule(fail)['characterization_complete'] and len(calls)==1
    calls.clear()
    def mixed(g):
        calls.append(g); return {'instrument_ok':len(calls)!=4,'baseline_matches':True}
    assert not schedule(mixed)['characterization_complete'] and len(calls)==9
