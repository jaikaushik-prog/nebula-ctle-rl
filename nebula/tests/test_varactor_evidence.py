"""Replay Entry 127 raw measured artifacts, with no simulator calls."""
import json
from pathlib import Path

import numpy as np
import pytest

from nebula.common.types import Corner
from nebula.device import varactor_probe as V
from nebula.experiments import evidence_archive as A
from nebula.experiments import raw_manifest

ROOT=Path(__file__).resolve().parents[1]/'product_audits/entry127_varactor_probe_20260909'


def test_complete_capacitor_manifest_and_frozen_schedule():
    assert A.digest(ROOT/'summary.json')=='9d687f8d1c836d8e5ff9cf915a853126bb303631ef0957dc0577a4cefdb16339'
    assert A.digest(ROOT/'evidence_sha256.json')=='ffd538df78082790601e7831868152046b507e0c2d7c5598414c1ad0bc37b843'
    assert raw_manifest.verify(ROOT)['file_count']==291
    r=json.loads((ROOT/'summary.json').read_text())
    assert r['characterization_complete'] and r['pdk_unchanged']
    assert r['spice_calls']==r['attempted_cases']==46 and len(r['pvt'])==45
    assert all(x['result']['instrument_ok'] for x in r['pvt'])
    assert r['calibration']['native_m_equivalent'] and not r['calibration']['vm4_equivalent']
    assert not r['configurable_ctle_verified']


@pytest.mark.parametrize('c',[Corner('tt',1,27),Corner('ss',.95,125),Corner('fs',1.05,125)])
def test_raw_corner_deck_currents_and_physical_capacitance_replay(c):
    folder=ROOT/f'probe_{c}'
    assert (folder/'design.cir').read_text()==V.probe_deck(c)
    V.check_op(np.loadtxt(folder/'op.txt'),V.probe_op_expected(c))
    measured=V.probe_metrics(V.parse_ac(np.loadtxt(folder/'admittance.txt'),410),c)
    saved=json.loads((folder/'result.json').read_text())
    assert all(measured[k]==saved[k] for k in measured)


def test_raw_both_electrode_multiplicity_calibration_replay():
    folder=ROOT/'calibration_tt_vdd1.00_t27'
    assert (folder/'design.cir').read_text()==V.calibration_deck()
    V.check_op(np.loadtxt(folder/'op.txt'),V.calibration_op_expected())
    measured=V.calibration_currents_metrics(V.parse_ac(np.loadtxt(folder/'admittance.txt'),72))
    saved=json.loads((folder/'result.json').read_text())
    assert all(measured[k]==saved[k] for k in measured)
