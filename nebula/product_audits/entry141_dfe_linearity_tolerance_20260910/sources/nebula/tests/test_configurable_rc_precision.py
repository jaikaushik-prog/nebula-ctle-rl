"""Precision recovery must not alter physical circuits or soften evidence gates."""
import json
from pathlib import Path

import numpy as np
import pytest

from nebula.device import configurable_rc as R, configurable_rc_serial as S
from nebula.device import configurable_rc_precision as Q
from nebula.experiments import raw_manifest as M, evidence_archive as A
from nebula.experiments.exp_configurable_rc import baseline_reference
from nebula.experiments.exp_configurable_rc_serial import extract

ROOT=Path(__file__).resolve().parents[1]/'product_audits/entry129_configurable_rc_serial_20260910'


@pytest.mark.parametrize('g',R.GEOMETRIES)
def test_precision_changes_only_solver_options(g):
    original=S.deck(g); precise=Q.deck(g)
    assert precise.replace(Q.OPTIONS+'\n','')==original
    assert precise.count(Q.OPTIONS)==1
    assert Q.OPTIONS=='.options reltol=1e-9 vntol=1e-12 abstol=1e-15'
    assert precise.index(Q.OPTIONS)<precise.index('.control')
    assert precise.count('alter Vr0 ')==81 and precise.count('alter Vc0 ')==81


def test_unregistered_precision_geometry_rejected():
    with pytest.raises(ValueError): Q.deck((1,0.))


def test_original_serial_failure_is_preserved_and_rejected():
    assert A.digest(ROOT/'summary.json')=='3f4c1536754a27eadd661b3e2dc7536d6e53c9b2e217a5bf4bb027fe797bfdb8'
    assert M.verify(ROOT)=={'manifest_sha256':'ee32dd501afab1813e373aaba63574a46ba334bda8296f8bc392d30d3e1c15e0','file_count':198}
    saved=json.loads((ROOT/'summary.json').read_text())
    assert saved['spice_calls']==saved['attempted_cases']==1
    assert saved['validated_op_ac_pairs']==0 and not saved['characterization_complete']
    assert saved['pdk_unchanged'] and saved['sources_unchanged']
    f=ROOT/'candidate_n100_fixed0pf'; ref=baseline_reference()[0]
    assert (f/'design.cir').read_text()==S.deck(R.GEOMETRIES[0])
    assert (f/'ngspice.log').stat().st_size>0
    with pytest.raises(ValueError,match='fixed baseline DC changed'):
        extract(f,R.GEOMETRIES[0],ref)
    for i in range(81):
        h=R.parse_ac(np.loadtxt(f/f'ac_{i:03d}.txt'),2)
        assert R.baseline_matches(h[:,1],ref)


def test_precision_registration_has_portable_hash_bytes():
    root=Path(__file__).resolve().parents[2]
    name='nebula/CONFIGURABLE_RC_PRECISION_PLAN.md'
    assert name+' text eol=lf' in (root/'.gitattributes').read_text()
    assert b'\r\n' not in (root/name).read_bytes()


def test_precision_prerequisites_pin_all_previous_sources():
    from nebula.experiments.exp_configurable_rc_precision import prerequisites,SOURCES
    proofs,config=prerequisites()
    assert len(proofs)==3
    assert config['entry']==129
    assert set(config['source_sha256'])<=set(SOURCES)
