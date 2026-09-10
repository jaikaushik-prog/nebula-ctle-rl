"""The known AC-grid workaround changes no hardware or runtime gate."""
from pathlib import Path

import numpy as np
import pytest

from nebula.device import configurable_rc_runtime as U
from nebula.device import configurable_rc_runtime_recovery as V


def test_only_the_static_ac_grid_changes():
    for i in range(3):
        old=U.deck('static',i);new=V.deck('static',i)
        assert new==old.replace('ac lin 2 100meg 1.9g','ac lin 3 100meg 1.9g')
        assert 'ac lin 2 ' not in new
    assert V.deck('runtime',0)==U.deck('runtime',0)


def test_validate_all_three_rows_then_select_actual_endpoints():
    raw=np.array([[f,0,0,h,0,1,0] for f,h in zip([1e8,1e9,1.9e9],[.2,.3,.4])])
    assert V.tone_reference(raw)==pytest.approx([.2,.4])
    for bad in (raw[:2],np.full_like(raw,np.nan)):
        with pytest.raises(ValueError): V.tone_reference(bad)
    bad=raw.copy();bad[1,0]+=1e7
    with pytest.raises(ValueError): V.tone_reference(bad)
    bad=raw.copy();bad[1,5]=0
    with pytest.raises(ValueError): V.tone_reference(bad)


def test_real_missing_endpoint_remains_rejected():
    root=Path(__file__).resolve().parents[1]/'product_audits/entry134_configurable_rc_runtime_20260910/static_0'
    with pytest.raises(ValueError): V.tone_reference(np.loadtxt(root/'tones.txt'))


def test_complete_failed_prerequisite_and_extractor_remain_strict():
    from nebula.experiments import exp_configurable_rc_runtime_recovery as E
    failed,original,config,prior=E.prerequisites()
    assert failed['verified_files']==80 and failed['verified_archives']==2
    assert original['file_count']==1812 and config['entry']==134
    with pytest.raises(ValueError,match='three-point'):
        E.extract(E.PRIOR/'static_0','static',0,prior,[None]*3)


def test_registration_and_frozen_source_closure():
    from nebula.experiments import exp_configurable_rc_runtime_recovery as E, exp_configurable_rc_runtime as U0
    root=Path(__file__).resolve().parents[2];name='nebula/CONFIGURABLE_RC_RUNTIME_RECOVERY_PLAN.md'
    assert name+' text eol=lf' in (root/'.gitattributes').read_text()
    assert b'\r\n' not in (root/name).read_bytes()
    assert set(U0.SOURCES)<=set(E.SOURCES)
