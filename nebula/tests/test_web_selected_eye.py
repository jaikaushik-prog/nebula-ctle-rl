"""Regression coverage for a completed physical run in Receiver."""
import json
import shutil
from pathlib import Path

import pytest

from nebula.web.design_visuals import selected_eye
from nebula.web.server import NebulaWebApp

SOURCE = Path("nebula/product_audits/entry115_physical_recovery_20260908/p3_f1.9_s401")


@pytest.fixture
def physical_run(tmp_path):
    run = tmp_path / ("a" * 32)
    root = run / "physical_evidence"
    root.mkdir(parents=True)
    for name in ("design.cir", "evidence_sha256.json", "tt_1.00_27/ac_noise/ac.txt"):
        dst = root / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / name, dst)
    raw = json.loads((SOURCE / "result.json").read_text())
    (run / "design.json").write_text(json.dumps(raw))
    return run


def test_selected_eye_reproduces_real_three_db_record(physical_run):
    eye = selected_eye(physical_run)
    assert eye["eye_h_v"] == pytest.approx(.3417911991427772, abs=1e-10)
    assert eye["eye_w_ui"] == .859375
    assert len(eye["phase_ui"]) == len(eye["height_v"]) == 64
    assert eye["kind"] == "worst-case-isi-envelope"
    assert "not a transistor transient" in eye["scope"]


@pytest.mark.parametrize("name", ["design.cir", "tt_1.00_27/ac_noise/ac.txt"])
def test_selected_eye_rejects_changed_sources(physical_run, name):
    with (physical_run / "physical_evidence" / name).open("a") as stream:
        stream.write("tamper")
    with pytest.raises(ValueError, match="hash mismatch"):
        selected_eye(physical_run)


def test_selected_eye_rejects_a_different_recorded_eye(physical_run):
    path = physical_run / "design.json"
    raw = json.loads(path.read_text())
    raw["nominal"]["meas"]["eye_h_v"] += .05
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="disagrees"):
        selected_eye(physical_run)


def test_scalar_bank_record_does_not_invent_waveforms(tmp_path):
    (tmp_path / "design.json").write_text(json.dumps({"method": "rl-hybrid"}))
    with pytest.raises(ValueError, match="scalar values"):
        selected_eye(tmp_path)


def test_explicit_run_root_recovers_completed_design(physical_run):
    bad = physical_run.parent / ("b" * 32)
    bad.mkdir()
    (bad / "design.json").write_text("incomplete json")
    app = NebulaWebApp(run_root=physical_run.parent)
    try:
        result = app.get_design(physical_run.name)
        assert result["request"]["peaking_db"] == 3
        assert result["status"] == "pass"
        assert app.get_design(bad.name) is None
        assert app.artifact(physical_run.name, "design.json") == physical_run / "design.json"
    finally:
        app.close()


def test_completion_lands_on_result_and_stale_eye_is_discarded():
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("Node required for frontend behavior check")
    script = r"""
const fs=require('fs'), vm=require('vm'), assert=require('assert');
const elements=new Map();
function el(id){if(!elements.has(id)) elements.set(id,{textContent:'',hidden:false,children:[],classList:{contains(){return true;}},replaceChildren(...x){this.children=x;this.textContent='';},focus(){this.focused=true;}});return elements.get(id);}
const document={addEventListener(){},querySelector(s){return el(s.slice(1));},getElementById(id){return el(id);}};
const context=vm.createContext({document,console,localStorage:{setItem(){}},NebulaCircuitViews:{mount(){},renderDesign(){}},events:[],done:null});
vm.runInContext(fs.readFileSync('nebula/web/static/app.js','utf8')+`
done=(async()=>{
 renderHardwareTopology=()=>{};renderHardwareMetrics=()=>{};renderHardwareTargetState=()=>{};
 renderOutcome=()=>{throw Error('No selected design exists yet');};renderRunTruth=()=>{};
 renderHardwareCheckpoint({status:'pass',evidence:[{key:'nominal-eye',url:'/eye'},{key:'hardware-schematic',url:'/circuit'}]});
 const result={id:'physical3',status:'pass'};
 api=async()=>({status:'complete',result});
 renderDesign=d=>events.push(['render',d.id]);
 selectTab=name=>events.push(['tab',name]);
 await pollJob('job',()=>{});
 let release;
 api=()=>new Promise(resolve=>{release=resolve});
 state.current={id:'older'};
 const pending=renderSelectedEye(state.current);
 state.current={id:'newer'};
 document.querySelector('#designAcPlot').textContent='Newer result';
 release({run_id:'older',height_v:[.2],phase_ui:[0]});
 await pending;
})();`,context);
(async()=>{await context.done;
 assert.deepEqual(JSON.parse(JSON.stringify(context.events)),[['render','physical3'],['tab','results']]);
 assert.equal(el('progressPanel').hidden,true);
 assert.equal(el('referenceCheckpoint').open,false);
 assert.equal(el('resultOverview').focused,true);
 assert.equal(el('designAcPlot').textContent,'Newer result');
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    subprocess.run([node, "-e", script], check=True, capture_output=True, text=True)


def test_comparison_discards_stale_pair_and_uses_shared_axes():
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("Node required for frontend behavior check")
    script = r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const nodes=new Map();
const document={addEventListener(){},querySelector(s){if(!nodes.has(s))nodes.set(s,{id:s,textContent:''});return nodes.get(s);}};
const plotted=[];
const context=vm.createContext({document,console,plotted,NebulaDesignPlots:{eye(target,data,mode,limit){plotted.push([target.id,data.label,mode,limit]);},envelope(){throw Error('Unexpected mode');}},done:null});
vm.runInContext(fs.readFileSync('nebula/web/static/app.js','utf8')+`
done=(async()=>{
 const pending=new Map();loadDesignVisual=d=>new Promise(resolve=>pending.set(d.id,resolve));
 const design=id=>({id,request:{peaking_db:3,f_peak_ghz:1.9},nominal:{meas:{eye_h_v:.3,eye_w_ui:.8}}});
 state.signalView='dfe';
 const older=renderCompareEyes(design('oldA'),design('oldB'));
 const newer=renderCompareEyes(design('newA'),design('newB'));
 const data=(label,amplitude)=>({design_id:label,channel_loss_db:7.5,waveform:{label,ctle_v:[[amplitude]],ideal_dfe_v:[[-amplitude]]}});
 pending.get('newA')(data('newA',.2));pending.get('newB')(data('newB',.4));await newer;
 pending.get('oldA')(data('oldA',.9));pending.get('oldB')(data('oldB',.8));await older;
})();`,context);
(async()=>{await context.done;assert.equal(plotted.length,2);assert.equal(plotted[0][1],'newA');assert.equal(plotted[1][1],'newB');assert.equal(plotted[0][3],plotted[1][3]);assert(plotted[0][3]>.4);})().catch(e=>{console.error(e);process.exitCode=1});
"""
    subprocess.run([node,"-e",script],check=True,capture_output=True,text=True)
