"""Preserve Entry 134's failed instrument and its actual, incomplete data."""
import json
from pathlib import Path

import numpy as np
import pytest

from nebula.device import configurable_rc_runtime as U
from nebula.experiments import evidence_archive as A, exp_configurable_rc_runtime as E

ROOT=Path(__file__).resolve().parents[1]/'product_audits/entry134_configurable_rc_runtime_20260910'


def test_failed_runtime_instrument_manifest_and_stop():
    assert A.digest(ROOT/'summary.json')=='041f2f243634859dc4e8aa1884a2bd3b519d194de0ad65214a2d0d22c526309d'
    assert A.verify(ROOT)=={'verified_files':80,'verified_archives':2,'manifest_sha256':'9cb555a0264202056e2e63e904b77bea547d3fbb2c2fd649b07c5e0d767e7140'}
    s=json.loads((ROOT/'summary.json').read_text())
    assert s['spice_calls']==s['attempted_cases']==1 and s['runtime'] is None
    assert not s['runtime_demonstration_pass'] and s['pdk_unchanged'] and s['sources_unchanged']
    assert s['static'][0]['fail_reason']=='ValueError: malformed exact-frequency AC primitives'


def test_missing_endpoint_is_not_imputed_from_a_passing_full_sweep():
    folder=ROOT/'static_0'
    raw=np.atleast_2d(np.loadtxt(folder/'tones.txt'))
    assert raw.shape==(1,7) and raw[0,0]==1e8
    with pytest.raises(ValueError,match='exact-frequency'): U.tone_reference(raw)
    _,_,prior=E.prerequisites()
    cal=U.reference_match(np.loadtxt(folder/'op.txt'),np.loadtxt(folder/'ac.txt'),0,prior[0])
    assert cal['reference_matches'] and cal['reference_max_dc_drift_v']<1e-12
    with pytest.raises(ValueError,match='exact-frequency'):
        E.extract(folder,'static',0,prior,[None]*3)
