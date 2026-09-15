"""Focused UI contracts: real attempt order, output truth, and circuit scope."""
import json
from pathlib import Path
import shutil
import subprocess
import pytest

STATIC = Path('nebula/web/static')

def trace(design):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required for the pure browser receipt presenter')
    program = "const api=require('./nebula/web/static/recovery_trace.js');process.stdout.write(JSON.stringify(api.steps(JSON.parse(process.argv[1]))));"
    run = subprocess.run([node, '-e', program, json.dumps(design)], capture_output=True, text=True, check=True)
    return json.loads(run.stdout)

def test_actual_saved_recovery_keeps_rejected_and_accepted_attempts():
    root = Path('nebula/product_demo/submission_runs_20260915_v2/94b55321c7f245df8093284b402c8a40')
    receipt = json.loads((root/'workflow_receipt.json').read_text())
    design = {'request':receipt['parsed_request'], 'recovery':receipt,
              'artifacts':['design.cir','design_schematic.png','explanation.txt']}
    rows = trace(design)
    assert [row['kind'] for row in rows] == ['request','rejected','accepted','outputs']
    assert '6 dB' in rows[0]['title'] and '2.1 GHz' in rows[0]['title']
    assert rows[1]['title'] == 'Setting 288' and '314/315' in rows[1]['detail']
    assert rows[2]['title'] == 'Setting 352' and '315/315' in rows[2]['detail']
    assert 'design.cir' in rows[3]['detail']

def test_trace_does_not_invent_success_outputs_or_condition_counts():
    rows = trace({'request':{},'recovery':{'attempts':[
        {'setting':0,'accepted':False}, {'setting':17}]}})
    assert rows[1]['kind']=='rejected' and rows[1]['title']=='Setting 0'
    assert rows[2]['kind']=='unknown'
    assert 'not recorded' in rows[1]['detail']
    assert rows[-1]['kind']=='missing_outputs'
    assert all('315/315' not in row['detail'] for row in rows)

def test_legacy_run_has_no_fabricated_attempt_trace():
    assert trace({'request':{'peaking_db':9,'f_peak_ghz':1.9},'artifacts':['design.cir']}) == []

def test_workflow_payload_and_arbitrary_attempt_order_are_supported():
    rows=trace({'request':{'peaking_db':3,'f_peak_hz':1.9e9},
        'recovery_workflow':{'attempts':[{'setting':400,'accepted':False,'n_pass':2,'n_points':5},
                                      {'setting':12,'accepted':True,'n_pass':5,'n_points':5}]},
        'artifacts':['design.json']})
    assert [x['title'] for x in rows[1:3]]==['Setting 400','Setting 12']
    assert '1.9 GHz' in rows[0]['title'] and rows[-1]['kind']=='outputs'

def test_selected_ctle_scope_and_modeled_dfe_are_explicit():
    html=(STATIC/'index.html').read_text(encoding='utf-8')
    js=(STATIC/'circuit_views.js').read_text(encoding='utf-8')
    app=(STATIC/'app.js').read_text(encoding='utf-8')
    assert 'id="selectedCircuitHeading">Selected CTLE' in html
    assert 'Independent transistor receiver evidence' in html
    assert 'Separate 9 dB / 1.9 GHz reference' in html
    assert 'physical CTLE, attenuation, bias and fixed Rs/Cs' in html
    assert 'behavioral DFE is outside this CTLE netlist' in html
    assert 'receiver/receiver.cir' in app
    assert 'Modeled 1-tap DFE' in js and 'Ideal behavioral' in js
    assert 'modeledDfeView' in js
    assert 'NebulaRecoveryTrace.render(design)' in app
    assert html.index('/recovery_trace.js') < html.index('/app.js')


def test_recorded_connected_receiver_appears_in_outputs():
    rows=trace({'request':{'peaking_db':6,'f_peak_ghz':2.1},
        'recovery':{'attempts':[{'setting':352,'accepted':True,'n_pass':315,'n_points':315}]},
        'artifacts':['design.cir','receiver/receiver.cir','receiver/metadata.json']})
    assert 'receiver/receiver.cir' in rows[-1]['detail']
    assert 'receiver/metadata.json' in rows[-1]['detail']
