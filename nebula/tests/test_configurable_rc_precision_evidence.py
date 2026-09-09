"""Replay every retained Entry 130 operating point and AC spectrum."""
import json
from pathlib import Path

import pytest

from nebula.device import configurable_rc as R, configurable_rc_precision as Q
from nebula.experiments import evidence_archive as A, raw_manifest as M
from nebula.experiments.exp_configurable_rc import baseline_reference
from nebula.experiments.exp_configurable_rc_serial import extract

ROOT=Path(__file__).resolve().parents[1]/'product_audits/entry130_configurable_rc_precision_20260910'


def test_complete_precision_evidence_and_accounting():
    assert A.digest(ROOT/'summary.json')=='5285ad72e81dda0e5ff85acbcad7ed4d29f7f6ad09d72cc297a87ac51d96fbfa'
    assert M.verify(ROOT)=={'manifest_sha256':'407e9ffa00af20cb3f3275b372d4089655d1430bc26c0ddc637778fc7c5d5ee7','file_count':1530}
    result=json.loads((ROOT/'summary.json').read_text())
    assert result['characterization_complete'] and result['sources_unchanged'] and result['pdk_unchanged']
    assert not result['connected_dfe_verified']
    assert result['spice_calls']==result['attempted_cases']==9
    assert result['validated_op_ac_pairs']==729
    assert [x['result']['ac_spec_pass_count'] for x in result['candidates']]==[0,9,9,11,9,9,5,7,6]


@pytest.mark.parametrize('g',R.GEOMETRIES)
def test_every_precision_geometry_replays_from_raw_tables(g):
    f=ROOT/f'candidate_n{g[0]}_fixed{g[1]*1e12:g}pf'
    assert (f/'design.cir').read_text()==Q.deck(g)
    saved=json.loads((f/'result.json').read_text())
    measured=extract(f,g,baseline_reference()[0])
    assert measured=={k:v for k,v in saved.items() if k not in ('op_tables_retained','ac_tables_retained')}
    assert saved['op_tables_retained']==saved['ac_tables_retained']==81
    assert measured['instrument_ok'] and measured['baseline_matches']
