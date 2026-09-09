"""Replay Entry 126's unchanged hardware and externally retimed channels."""
import json
from pathlib import Path
import re

import pytest

from nebula.common.types import Corner
from nebula.device import dfe_connected as F, dfe_hardware as D
from nebula.device import dfe_tail_bleed as B, dfe_timing as T, dfe_voltage_audit as V
from nebula.experiments import evidence_archive as A, exp_dfe_tail_bleed as E
from nebula.experiments import exp_dfe_timing as R
from nebula.link.config import LinkConfig

ROOT=Path(__file__).resolve().parents[1]/'product_audits/entry126_dfe_timing_20260909'


def test_retiming_manifest_frozen_membership_and_honest_coverage():
    proof=A.verify(ROOT)
    manifest=json.loads((ROOT/'evidence_sha256.json').read_text())
    assert proof['verified_files']==len(manifest)==605
    assert proof['verified_archives']==190
    assert proof['manifest_sha256']=='e5a52225a37ba62f4b1347599fd2640b1102d707f64b75657f4e4f978d0eb302'
    summary=json.loads((ROOT/'summary.json').read_text())
    assert summary['spice_calls']==summary['attempted_cases']==95
    assert summary['selected_phase_ui']==1.5 and summary['selected_bleeder_length_um']==4
    assert len(summary['pvt'])==90
    assert summary['prior_7p5db_pvt_passes']==45 and summary['prior_spice_calls']==57
    assert summary['prior_counts_are_not_new_simulations']
    assert not summary['full_receiver_verified'] and not summary['code_zero_is_feedback_disabled']
    def replay(corner,loss,phase,code,sign,stage):
        folder=ROOT/f'{stage}_{corner}_loss{loss:g}_phase{phase:g}_code{code}_sign{sign}_bleedL4'
        return json.loads((folder/'result.json').read_text())
    reproduced=R.schedule(replay)
    assert all(value==summary[k] for k,value in reproduced.items())
    assert summary['new_channel_pvt_pass']
    assert all(E.accepted(row['result']) for row in summary['pvt'])
    # The earlier timing screen is a retained failure, not silently dropped.
    assert not summary['screens'][0]['result']['signal_gate_pass']
    assert summary['screens'][0]['result']['correct_bits']==64


@pytest.mark.parametrize('case',[
    'phase_tt_vdd1.00_t27_loss12_phase1.25_code2_sign1_bleedL4',
    'control_tt_vdd1.00_t27_loss12_phase1.5_code0_sign1_bleedL4',
    'pvt_fs_vdd0.95_t125_loss3_phase1_code2_sign1_bleedL4',
    'pvt_fs_vdd0.95_t125_loss12_phase1.5_code2_sign1_bleedL4'])
def test_exact_retimed_waveforms_voltage_audits_and_hardware(case):
    folder=ROOT/case
    saved=json.loads((folder/'result.json').read_text())
    bits=json.loads((ROOT/'config.json').read_text())['bits']
    match=re.fullmatch(r'(tt|ss|ff|sf|fs)_vdd([0-9.]+)_t([0-9.]+)',saved['corner'])
    temp=float(match[3]) if case.startswith('pvt_') else int(float(match[3]))
    corner=Corner(match[1],float(match[2]),temp)
    cfg=LinkConfig(channel_loss_db_at_nyquist=saved['loss_db'])
    t,y=T.read_table(folder/'trace.txt.gz',len(F.VECTORS))
    actual=F.analyze(t,y,bits,cfg,saved['phase_ui'],1.8*corner.vdd_scale,code=saved['code'])
    assert all(value==saved[k] for k,value in actual.items())
    assert T.aperture(t,y[:,3]-y[:,4],bits,saved['phase_ui'])==saved['aperture']
    deck=(folder/'design.cir').read_text()
    mos=F.all_mos(deck); names=D.terminal_nodes(mos)
    _,ny=T.read_table(folder/'terminals.txt.gz',len(names),expected_time=t)
    nodes=dict(zip(names,ny.T))
    assert V.audit(mos,nodes)==saved['whole_circuit_voltage_audit']
    assert V.audit(F.extra_mos(saved['sign'])+B.bleeders(4),nodes)==saved['new_dfe_voltage_audit']
    assert deck==B.deck(4,corner,cfg,bits,saved['phase_ui'],saved['code'],saved['sign'])
