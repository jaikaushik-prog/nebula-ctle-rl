"""Entry 124 frozen raw evidence: retain successes AND electrical failures."""
import json
from pathlib import Path
import re

import pytest

from nebula.common.types import Corner
from nebula.device import dfe_connected as F, dfe_hardware as D, dfe_voltage_audit as V
from nebula.experiments import evidence_archive as A, exp_dfe_connected as E
from nebula.link.config import LinkConfig

ROOT=Path(__file__).resolve().parents[1]/'product_audits/entry124_dfe_connected_20260909'


def test_all_original_hashes_and_registered_selection_survive_archival():
    proof=A.verify(ROOT)
    assert proof['verified_files']==372 and proof['verified_archives']==116
    summary=json.loads((ROOT/'summary.json').read_text())
    assert summary['spice_calls']==58
    assert summary['selected']=={'phase_ui':1.,'code':2,'sign':1}
    assert len(summary['pvt'])==45
    assert sum(r['result']['logic_pass'] for r in summary['pvt'])==45
    assert sum(r['result']['signal_gate_pass'] for r in summary['pvt'])==44
    assert not summary['primary_channel_pvt_pass'] and not summary['full_receiver_verified']
    def replay(corner,loss,phase,code,sign,stage):
        folder=ROOT/f'{stage}_{corner}_loss{loss:g}_phase{phase:g}_code{code}_sign{sign}'
        return json.loads((folder/'result.json').read_text())
    reproduced=E.schedule(replay)
    assert all(v==summary[k] for k,v in reproduced.items())


@pytest.mark.parametrize('case,bits,passed',[
    ('phase_tt_vdd1.00_t27_loss7.5_phase0.5_code0_sign1',10,False),
    ('phase_tt_vdd1.00_t27_loss7.5_phase0.75_code0_sign1',36,False),
    ('tap_tt_vdd1.00_t27_loss7.5_phase1_code2_sign1',64,True),
    ('pvt_fs_vdd0.95_t125_loss7.5_phase1_code2_sign1',64,False),
    ('channel_tt_vdd1.00_t27_loss12_phase1_code2_sign1',15,False),
    ('tap_tt_vdd1.00_t27_loss7.5_phase1_code8_sign-1',61,False)])
def test_representative_raw_waveforms_reproduce_exact_metrics_and_audits(case,bits,passed):
    folder=ROOT/case
    saved=json.loads((folder/'result.json').read_text())
    pattern=json.loads((ROOT/'config.json').read_text())['bits']
    match=re.fullmatch(r'(tt|ss|ff|sf|fs)_vdd([0-9.]+)_t([0-9.]+)',saved['corner'])
    # The frozen scheduler constructs TT screens with integer 27, whereas
    # all_corners supplies float temperatures. Preserve exact deck spelling.
    temp=float(match[3]) if case.startswith('pvt_') else int(float(match[3]))
    corner=Corner(match[1],float(match[2]),temp)
    cfg=LinkConfig(channel_loss_db_at_nyquist=saved['loss_db'])
    t,y=F.read_trace(folder/'trace.txt.gz')
    actual=F.analyze(t,y,pattern,cfg,saved['phase_ui'],1.8*corner.vdd_scale,code=saved['code'])
    assert all(value==saved[k] for k,value in actual.items())
    assert actual['correct_bits']==bits and E.accepted(saved)==passed
    deck=(folder/'design.cir').read_text()
    mos=F.all_mos(deck)
    nodes=V.read_nodes(folder/'terminals.txt.gz',D.terminal_nodes(mos),t)
    assert V.audit(mos,nodes)==saved['whole_circuit_voltage_audit']
    assert V.audit(F.extra_mos(saved['sign']),nodes)==saved['new_dfe_voltage_audit']
    assert deck==F.deck(corner,cfg,pattern,saved['phase_ui'],saved['code'],saved['sign'])
