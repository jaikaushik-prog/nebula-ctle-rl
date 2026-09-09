"""Replay frozen Entry 125 transistor evidence, including residual feedback."""
import json
from pathlib import Path
import re

import pytest

from nebula.common.types import Corner
from nebula.device import dfe_connected as F, dfe_hardware as D
from nebula.device import dfe_tail_bleed as B, dfe_timing as T, dfe_voltage_audit as V
from nebula.experiments import evidence_archive as A, exp_dfe_tail_bleed as E
from nebula.link.config import LinkConfig

ROOT=Path(__file__).resolve().parents[1]/'product_audits/entry125_dfe_tail_bleed_20260909'


def test_recovery_manifest_and_frozen_schedule():
    proof=A.verify(ROOT)
    assert proof['verified_files']==377 and proof['verified_archives']==114
    summary=json.loads((ROOT/'summary.json').read_text())
    assert summary['spice_calls']==summary['attempted_cases']==57
    assert summary['selected_length_um']==4 and len(summary['pvt'])==45
    assert summary['primary_channel_pvt_pass']
    assert all(E.accepted(row['result']) for row in summary['pvt'])
    assert not summary['code_zero_is_feedback_disabled']
    def replay(length,corner,loss,phase,code,sign,stage):
        folder=ROOT/f'{stage}_{corner}_loss{loss:g}_phase{phase:g}_code{code}_sign{sign}_bleedL{length:g}'
        return json.loads((folder/'result.json').read_text())
    reproduced=E.schedule(replay)
    assert all(value==summary[k] for k,value in reproduced.items())
    assert not summary['full_receiver_verified']


@pytest.mark.parametrize('case',[
    'screen_fs_vdd0.95_t125_loss7.5_phase1_code2_sign1_bleedL4',
    'control_tt_vdd1.00_t27_loss7.5_phase1_code0_sign1_bleedL4',
    'control_tt_vdd1.00_t27_loss7.5_phase1_code2_sign-1_bleedL4',
    'screen_tt_vdd1.00_t27_loss7.5_phase1_code2_sign1_bleedL2'])
def test_real_single_scale_waveforms_reproduce_metrics_and_every_voltage(case):
    folder=ROOT/case
    saved=json.loads((folder/'result.json').read_text())
    bits=json.loads((ROOT/'config.json').read_text())['bits']
    match=re.fullmatch(r'(tt|ss|ff|sf|fs)_vdd([0-9.]+)_t([0-9.]+)',saved['corner'])
    corner=Corner(match[1],float(match[2]),int(float(match[3])))
    cfg=LinkConfig(channel_loss_db_at_nyquist=saved['loss_db'])
    t,y=T.read_table(folder/'trace.txt.gz',len(F.VECTORS))
    actual=F.analyze(t,y,bits,cfg,saved['phase_ui'],1.8*corner.vdd_scale,code=saved['code'])
    assert all(value==saved[k] for k,value in actual.items())
    assert T.aperture(t,y[:,3]-y[:,4],bits,saved['phase_ui'])==saved['aperture']
    text=(folder/'design.cir').read_text()
    mos=F.all_mos(text)
    names=D.terminal_nodes(mos)
    _,ny=T.read_table(folder/'terminals.txt.gz',len(names),expected_time=t)
    nodes=dict(zip(names,ny.T))
    assert V.audit(mos,nodes)==saved['whole_circuit_voltage_audit']
    assert V.audit(F.extra_mos(saved['sign'])+B.bleeders(saved['length_um']),nodes)==saved['new_dfe_voltage_audit']
    assert saved['new_dfe_voltage_audit']['documented_ranges_ok']
    assert text==B.deck(saved['length_um'],corner,cfg,bits,saved['phase_ui'],saved['code'],saved['sign'])
