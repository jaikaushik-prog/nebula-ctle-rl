"""Entry 111 lower-load circuit boundaries and drawn-terminal voltage audit."""
import json
from pathlib import Path

import numpy as np
import pytest

from nebula.common.types import Corner
from nebula.device import dfe_hardware as D
from nebula.link.config import LinkConfig


@pytest.mark.parametrize('width',[2,1])
def test_only_sixteen_peripheral_widths_and_fingers_change(width):
    old=D.dut_lines(4,buffered=True)
    new=D.dut_lines(4,buffered=True,chain_width_um=width)
    assert old[:11]==new[:11] and len(new)==27
    for a,b in zip(old[11:],new[11:]):
        fields=a.split(); fields[6]=f'w={width}'; fields[8]='nf=1'
        assert fields==b.split()
    g=D.geometry(4,buffered=True,chain_width_um=width)
    assert g['gate_geometry_mm2']==pytest.approx((48+16*width)*.15/1e6)
    assert g['full_area_mm2'] is None and g['mos_count']==27


@pytest.mark.parametrize('width,buffered,chain,drive',[(8,True,2,None),(4,False,2,None),
    (4,True,3,None),(4,True,4,None),(4,True,2,(8,8))])
def test_unapproved_combination_refused(width,buffered,chain,drive):
    with pytest.raises(ValueError):
        D.dut_lines(width,buffered=buffered,chain_width_um=chain,buffer_drive_um=drive)


def test_stimulus_and_gate_unchanged_only_extra_voltage_trace():
    bits=D.pattern(LinkConfig(channel_loss_db_at_nyquist=7.5)); c=Corner('tt',1,27)
    old=D.deck(4,c,1.36,bits,buffered=True)
    new=D.deck(4,c,1.36,bits,buffered=True,chain_width_um=2)
    assert old.split('Xin1')[0].split('\n',1)[1]==new.split('Xin1')[0].split('\n',1)[1]
    new_control='\n'.join(l for l in new.split('.control')[1].split('\n') if not l.startswith('wrdata terminals.txt'))
    assert old.split('.control')[1]==new_control
    nodes=D.terminal_nodes(D.dut_lines(4,buffered=True,chain_width_um=2))
    assert 'q_series' in nodes and 'tail' in nodes and 'vdd' in nodes and '0' not in nodes


def test_voltage_audit_uses_source_and_polarity():
    from nebula.device.dfe_voltage_audit import audit
    lines=[f'Xn d g s 0 {D.NFET} w=2 l=.15 nf=1',
           f'Xp d g vdd vdd {D.PFET} w=2 l=.15 nf=1']
    nodes={'d':np.array([.2]),'g':np.array([1.]),'s':np.array([.1]),'vdd':np.array([1.8])}
    r=audit(lines,nodes)
    assert r['documented_ranges_ok']
    n,p=r['devices']
    assert n['vds']['min_v']==pytest.approx(.1)
    assert n['vgs']['max_v']==pytest.approx(.9)
    assert n['vbs']['min_v']==pytest.approx(-.1)
    assert p['vds']['min_v']==pytest.approx(-1.6)
    nodes['d']=np.array([-.214])
    r=audit(lines,nodes)
    assert not r['documented_ranges_ok']
    assert r['devices'][1]['vds']['below_samples']==1
    assert r['max_abs_vds_vgs_v']==pytest.approx(2.014)
    assert not r['reliability_verified']


@pytest.mark.parametrize('fault',['missing','nan','shape','unknown'])
def test_bad_audit_inputs_refused(fault):
    from nebula.device.dfe_voltage_audit import audit
    lines=[f'Xn d g 0 0 {D.NFET} w=2 l=.15 nf=1']
    nodes={'d':np.array([1.]),'g':np.array([1.])}
    if fault=='missing': del nodes['g']
    elif fault=='nan': nodes['g'][0]=np.nan
    elif fault=='shape': nodes['g']=np.array([1.,2.])
    else: lines=[lines[0].replace(D.NFET,'unknown_model')]
    with pytest.raises(ValueError): audit(lines,nodes)


@pytest.mark.parametrize('passing',[True,False])
def test_schedule_always_two_calls_no_selection_or_pvt(passing):
    from nebula.experiments.exp_dfe_low_load import schedule
    calls=[]
    def evaluate(width):
        calls.append(width); return {'block_pass':passing}
    r=schedule(evaluate)
    assert calls==[2,1] and len(r['screening'])==2
    assert not r['hardware_dfe_complete'] and not r['full_receiver_verified']
    assert r['pvt_calls']==0 and r['selected_width_um'] is None


def test_failure_is_retained_without_retry(tmp_path,monkeypatch):
    from nebula.experiments import exp_dfe_low_load as E
    calls=[]
    def fail(deck,folder):
        calls.append(folder); folder.mkdir()
        (folder/'design.cir').write_text(deck,encoding='ascii')
        (folder/'ngspice.log').write_text('injected unit-test failure')
        raise ValueError('unit-test simulator failure')
    monkeypatch.setattr(E.P,'invoke',fail)
    out=tmp_path/'test-only'; r=E.run(out)
    assert r['spice_calls']==len(calls)==2
    assert all(not s['result']['instrument_ok'] for s in r['screening'])
    for key,sha in json.loads((out/'evidence_sha256.json').read_text()).items():
        assert E.digest(out/key)==sha
    with pytest.raises(FileExistsError): E.run(out)


def test_terminal_reader_rejects_time_mismatch(tmp_path):
    from nebula.device.dfe_voltage_audit import read_nodes
    t=np.array([0.,1e-12,2e-12]); data=np.column_stack((t,t+1,t,t+2))
    path=tmp_path/'synthetic-only.txt'; np.savetxt(path,data)
    nodes=read_nodes(path,['a','b'],t)
    assert np.array_equal(nodes['a'],t+1)
    data[1,2]+=1e-13; np.savetxt(path,data)
    with pytest.raises(ValueError,match='time axis'): read_nodes(path,['a','b'],t)


def test_real_entry111_both_fail_transitions_and_model_domain():
    from nebula.device import dfe_voltage_audit as V
    from nebula.experiments.exp_dfe_slicer import digest
    root=Path(__file__).resolve().parents[1]/'product_audits/entry111_dfe_low_load_20260906'
    manifest=json.loads((root/'evidence_sha256.json').read_text())
    assert len(manifest)==35
    for key,sha in manifest.items(): assert digest(root/key)==sha
    cfg=json.loads((root/'config.json').read_text()); summary=json.loads((root/'summary.json').read_text())
    assert summary['spice_calls']==cfg['max_calls']==2 and summary['pvt_calls']==0
    assert summary['selected_width_um'] is None
    for width,delay,vmax in ((2,45.5,2.176607663767069),(1,40.5,2.227363484917005)):
        folder=root/f'screen_chain{width}_tt_1.00_27'
        saved=json.loads((folder/'result.json').read_text())
        t,y=D.read_trace(folder/'trace.txt'); z=D.read_buffer_trace(folder/'buffers.txt',t)
        result=D.analyze(t,y,cfg['bits'],1.8,saved['common_mode_v'])
        assert all(v==saved[k] for k,v in result.items())
        assert result['stimulus_valid'] and not result['block_pass'] and result['correct_bits']==14
        assert all(b['raw_min_logic_margin_v']>0 for b in result['bits'])
        assert max(b['raw_final_stable_delay_s'] for b in result['bits'])==pytest.approx(delay*1e-12,abs=1e-15)
        for b in result['bits']:
            i=b['bit_index']; assert b['pass']==(cfg['bits'][i]==cfg['bits'][i-1])
        devices=D.dut_lines(4,buffered=True,chain_width_um=width)
        nodes=V.read_nodes(folder/'terminals.txt',D.terminal_nodes(devices),t)
        for col,name in enumerate(('clk','inp','inn','x','y','q','qb')):
            assert np.array_equal(nodes[name],y[:,col])
        for col,name in enumerate(('bx1','bx','by1','by')):
            assert np.array_equal(nodes[name],z[:,col])
        va=V.audit(devices,nodes)
        assert va==saved['voltage_audit'] and not va['documented_ranges_ok']
        assert va['max_abs_vds_vgs_v']==pytest.approx(vmax)
        ps=(t-D.edge_time(6))*1e12
        good=np.flatnonzero((ps>=0)&(ps<=190)&(y[:,5]>.9)&(y[:,6]<.9))
        assert len(good) and ps[good[0]]>150  # Now switches, but too late for +110 hold.
        assert (folder/'design.cir').read_text()==D.deck(4,Corner('tt',1,27),saved['common_mode_v'],cfg['bits'],buffered=True,chain_width_um=width)
