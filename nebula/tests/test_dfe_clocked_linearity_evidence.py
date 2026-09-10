"""Immutable failed-instrument evidence and four-way measured HD3 replay."""
import json
import numpy as np
import pytest
from nebula.experiments import evidence_archive as A
from nebula.experiments import exp_dfe_clocked_linearity as P, exp_dfe_linearity_gear as G, exp_dfe_linearity_tolerance as E
from nebula.device import configurable_rc as R, dfe_loaded_initialization as I, dfe_loaded_analog as L
ROOT=E.ROOT/'nebula/product_audits'

@pytest.mark.parametrize('entry,stem,count,manifest',[
 (139,'dfe_clocked_linearity',89,'34dff7d9f1d0d98b6b77c0fb51ff676ae33f12e5392792d730c978736e0a6229'),
 (140,'dfe_linearity_gear',92,'43b0e3b4ca32613cdbaf57af8e68e8abb91fb2a38fa47272c956c29b0c3f50ea')])
def test_aborted_pair_archive_and_exact_rejection(entry,stem,count,manifest):
    root=ROOT/f'entry{entry}_{stem}_20260910'
    assert A.verify(root)=={'verified_files':count,'verified_archives':4,'manifest_sha256':manifest}
    summary=json.loads((root/'summary.json').read_text())
    assert summary['spice_calls']==2 and not summary['clocked_ctle_hd3_model_pass']
    reference=json.loads((root/'reference_result.json').read_text())
    ac=R.parse_ac(np.loadtxt(root/'reference_ac.txt'),1)[:,0]
    for step in L.STEPS:
        folder=root/f'tone_step{step*1e12:g}ps'
        text=(folder/'design.cir').read_text()
        assert text==(I.deck('tone',0,step,-1,reference) if entry==139 else G.deck(step,reference))
        with pytest.raises(ValueError,match='aborted transient'):
            G.abort_audit((folder/'ngspice.log').read_text())
        if entry==139:
            with pytest.raises(ValueError,match='incomplete or malformed'):
                P.N.extract(folder,text,'tone',0,step,-1,reference,ac)
        else:
            with pytest.raises(ValueError,match='aborted transient'):
                G.extract(folder,text,step,reference,ac)

def test_complete_four_way_linearity_archive_and_schedule():
    root=ROOT/'entry141_dfe_linearity_tolerance_20260910'
    assert A.verify(root)=={'verified_files':107,'verified_archives':8,
        'manifest_sha256':'56071ef43b5e0084318ed1a35a1246d0567bde105bbb512eba8f96e5ed064eb7'}
    assert A.digest(root/'summary.json')=='dd25c77f80f18d90f8706da310a7d7e900ce6dd003f14a6f0500bbb86056b748'
    s=json.loads((root/'summary.json').read_text())
    assert s['spice_calls']==4 and s['clocked_ctle_hd3_model_pass'] and s['four_way_agreement']
    assert s['sources_unchanged'] and s['pdk_unchanged']
    replay=E.schedule(lambda tol,step:json.loads((root/f'tone_tol{tol:g}_step{step*1e12:g}ps/result.json').read_text()))
    assert all(s[k]==v for k,v in replay.items())
    assert not s['full_receiver_verified'] and not s['tuning_map_verified']

@pytest.mark.parametrize('tol,step',[(tol,step) for tol in E.TOLERANCES for step in L.STEPS])
def test_actual_complete_linearity_waveform_replay(tol,step):
    root=ROOT/'entry141_dfe_linearity_tolerance_20260910'
    folder=root/f'tone_tol{tol:g}_step{step*1e12:g}ps'
    reference=json.loads((root/'reference_result.json').read_text())
    ac=R.parse_ac(np.loadtxt(root/'reference_ac.txt'),1)[:,0]
    text=(folder/'design.cir').read_text()
    assert text==E.deck(tol,step,reference)
    actual=E.extract(folder,text,step,reference,ac)
    saved=json.loads((folder/'result.json').read_text())
    assert actual=={k:v for k,v in saved.items() if k not in ('relative_tolerance','max_step_s')}
    assert actual['instrument_ok'] and actual['hd3_model_pass'] and actual['initialization_valid']
    assert actual['ctle_hd3']['hd3_dbc'] < -55
    assert not actual['passive_nonlinearity_verified'] and not actual['full_receiver_verified']
