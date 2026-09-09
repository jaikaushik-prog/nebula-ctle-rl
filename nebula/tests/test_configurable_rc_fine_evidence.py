"""Measured nine-target single-circuit tuning must replay from raw evidence."""
import json
from pathlib import Path

import pytest

from nebula.device import configurable_rc_fine as F
from nebula.experiments import evidence_archive as A, raw_manifest as M
from nebula.experiments.exp_configurable_rc import baseline_reference
from nebula.experiments.exp_configurable_rc_fine import extract

ROOT=Path(__file__).resolve().parents[1]/'product_audits/entry131_configurable_rc_fine_20260910'


def test_complete_fine_evidence_and_single_geometry_selection():
    assert A.digest(ROOT/'summary.json')=='06f6344b3802bf863f3ceb80be847cd0ab6c95debe3c0c3760a8ce590ef87b12'
    assert M.verify(ROOT)=={'manifest_sha256':'03585ee1a882bb36523557bfa029b61cb9f29edcc21cd0eaf402d33372e3ab01','file_count':1812}
    r=json.loads((ROOT/'summary.json').read_text())
    assert r['characterization_complete'] and r['pdk_unchanged'] and r['sources_unchanged']
    assert r['spice_calls']==r['attempted_cases']==2 and r['validated_op_ac_pairs']==882
    assert r['selected_geometry']==[500,0.] and not r['connected_dfe_verified'] and not r['full_target_rectangle_verified']
    assert [x['target_count'] for x in r['candidates']]==[5,9]
    replay=F.schedule(lambda g:next(x['result'] for x in r['candidates'] if tuple(x['geometry'])==g))
    assert list(replay['selected_geometry'])==r['selected_geometry']
    assert [x['targets'] for x in replay['candidates']]==[x['targets'] for x in r['candidates']]


@pytest.mark.parametrize('g',F.GEOMETRIES)
def test_fine_geometry_replays_all_441_pairs(g):
    f=ROOT/f'candidate_n{g[0]}_fixed0pf'
    assert (f/'design.cir').read_text()==F.deck(g)
    saved=json.loads((f/'result.json').read_text())
    assert extract(f,g,baseline_reference()[0])=={k:v for k,v in saved.items() if k not in ('op_tables_retained','ac_tables_retained')}
    assert saved['op_tables_retained']==saved['ac_tables_retained']==441
