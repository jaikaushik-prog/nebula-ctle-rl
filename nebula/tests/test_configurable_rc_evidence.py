"""The measured calibration and instrument failures must remain reproducible."""
import json
from pathlib import Path

import numpy as np

from nebula.device import configurable_rc as R
from nebula.experiments import raw_manifest as M, evidence_archive as A
from nebula.experiments.exp_configurable_rc import baseline_reference

ROOT=Path(__file__).resolve().parents[1]/'product_audits/entry128_configurable_rc_20260910'


def test_original_complete_manifest_keeps_nine_instrument_failures():
    assert A.digest(ROOT/'summary.json')=='eb2a01bf10c47d9af5b372668d64c819b28c84461caec9e359d936fffb51a67b'
    assert M.verify(ROOT)=={'manifest_sha256':'4a2a4e3472a84145f7ff705fe3d42027f6bab4ad0ca05015f9f5b5e770bc65a3','file_count':60}
    r=json.loads((ROOT/'summary.json').read_text())
    assert r['spice_calls']==r['attempted_cases']==10 and len(r['candidates'])==9
    assert r['pdk_unchanged'] and r['sources_unchanged']
    assert not r['characterization_complete'] and not r['connected_dfe_verified']
    for saved,g in zip(r['candidates'],R.GEOMETRIES):
        assert tuple(saved['geometry'])==g
        assert not saved['result']['instrument_ok']
        assert saved['result']['fail_reason']=="TypeError: can't concat str to bytes"
        folder=ROOT/f'candidate_n{g[0]}_fixed{g[1]*1e12:g}pf'
        assert (folder/'design.cir').read_text()==R.screen_deck(g)
        assert all(not (folder/name).exists() for name in ('ac.txt','op.txt','ngspice.log'))


def test_fixed_calibration_raw_voltage_and_current_replay():
    folder=ROOT/'calibration'
    assert (folder/'design.cir').read_text()==R.screen_deck(None)
    h=R.parse_ac(np.loadtxt(folder/'ac.txt'),1)[:,0]
    assert R.baseline_matches(h,baseline_reference()[0])
    dc=R.parse_op(np.loadtxt(folder/'op.txt'),None)[0]
    saved=json.loads((folder/'result.json').read_text())
    assert dc==saved['baseline_dc']
    assert saved['baseline_matches'] and saved['instrument_ok']
