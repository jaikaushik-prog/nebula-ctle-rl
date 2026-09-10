"""Verify eventual settling while retaining the original failed latency gate."""
import json
from pathlib import Path

import pytest

from nebula.device import configurable_rc_settling as W
from nebula.experiments import evidence_archive as A, exp_configurable_rc_settling as E

ROOT=Path(__file__).resolve().parents[1]/'product_audits/entry136_configurable_rc_settling_20260910'


def test_complete_archive_preserves_separate_settling_conclusions():
    assert A.digest(ROOT/'summary.json')=='a816bab17c13a7700a83ef0dcd62c571a701df8be8b1f3265de026f95022d4e3'
    assert A.verify(ROOT)=={'verified_files':85,'verified_archives':2,'manifest_sha256':'d4177c1ce2b9458743f80466160558be5dbf5a4d931920f36e59f9eb45a70324'}
    s=json.loads((ROOT/'summary.json').read_text())
    assert s['spice_calls']==1 and s['instrument_ok'] and s['all_transitions_settled']
    assert s['pdk_unchanged'] and s['sources_unchanged']
    assert not s['passes_original_500ns_gate'] and not s['connected_dfe_runtime_verified']
    assert not s['full_receiver_verified']
    assert [r['settling_bound_s'] for r in s['transitions']]==pytest.approx([850e-9,690e-9,650e-9],abs=1e-15)
    assert [sum(w['pass'] for w in r['windows']) for r in s['transitions']]==[13,29,33]
    assert all(len(r['windows'])==98 and not r['passes_original_500ns_gate'] for r in s['transitions'])
    assert s['whole_magnitude_body_envelope_pass'] and s['varactor_envelope_pass']


def test_full_waveform_and_every_terminal_reproduce_recorded_result():
    refs=[json.loads((ROOT/f'static_reference_{i}.json').read_text()) for i in range(3)]
    folder=ROOT/'runtime_0';saved=json.loads((folder/'result.json').read_text())
    assert (folder/'design.cir').read_text()==W.deck()
    assert E.extract(folder,refs)==saved
