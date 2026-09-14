"""Rehearse the saved desktop path in an already running local CDP browser.

Requires the app at port 8765 and a local browser debugging port 9223.
No design, simulator or training job is submitted. Outputs go to tmp, with
one report screenshot copied into the project-owned report assets directory.
"""
import base64
import json
from pathlib import Path
from urllib.request import urlopen

import websocket

ROOT=Path(__file__).resolve().parents[2]


def main():
    tabs=json.load(urlopen("http://127.0.0.1:9223/json"))
    tab=next(t for t in tabs if t["type"]=="page" and "127.0.0.1:8765" in t["url"])
    ws=websocket.create_connection(tab["webSocketDebuggerUrl"],timeout=30)
    serial=0; exceptions=[]
    def call(method,params=None):
        nonlocal serial
        serial+=1
        ws.send(json.dumps({"id":serial,"method":method,"params":params or {}}))
        while True:
            reply=json.loads(ws.recv())
            if reply.get("method")=="Runtime.exceptionThrown": exceptions.append(reply)
            if reply.get("id")==serial:
                if "error" in reply: raise RuntimeError(reply)
                return reply.get("result",{})
    def js(expression):
        reply=call("Runtime.evaluate",{"expression":expression,"returnByValue":True,"awaitPromise":True})
        if "exceptionDetails" in reply: raise RuntimeError(reply)
        return reply.get("result",{}).get("value")
    def settle():
        js("new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))")
    out=ROOT/"tmp/submission-desktop-review"; out.mkdir(parents=True,exist_ok=True)
    def shot(name):
        settle()
        data=call("Page.captureScreenshot",{"format":"png","captureBeyondViewport":False})
        path=out/f"{name}.png"; path.write_bytes(base64.b64decode(data["data"]))
        return path
    call("Runtime.enable")
    call("Emulation.setDeviceMetricsOverride",{"width":1440,"height":1000,"deviceScaleFactor":1,"mobile":False})
    call("Page.reload",{"ignoreCache":True})
    js("new Promise((resolve,reject)=>{let n=0;let t=setInterval(()=>{if(state.current && state.designs.size>1 && document.querySelector('#designAcPlot svg')){clearInterval(t);resolve(true)}else if(++n>200){clearInterval(t);reject('initialization timeout')}},100)})")
    records=[]
    physical=js("[...state.designs.values()].find(d=>d.method==='rl-physical' && d.request.peaking_db===3).id")
    for width,height in ((1440,1000),(1280,900)):
        call("Emulation.setDeviceMetricsOverride",{"width":width,"height":height,"deviceScaleFactor":1,"mobile":False})
        js(f"renderDesign(state.designs.get('{physical}'));selectTab('results')")
        js("new Promise((r,j)=>{let n=0,t=setInterval(()=>{if(document.querySelector('#designAcPlot svg')){clearInterval(t);r(true)}else if(++n>100){clearInterval(t);j('eye timeout')}},100)})")
        shot(f"{width}-explorer")
        assert js("document.documentElement.scrollWidth<=innerWidth")
        assert js("document.querySelector('#resultVerdict').getBoundingClientRect().bottom<innerHeight")
        assert js("document.querySelector('#resultCoverage').getBoundingClientRect().bottom<innerHeight")
        assert js("document.querySelector('[data-block=ctle]').open && !document.querySelector('#referenceCheckpoint').open")
        assert js("document.querySelector('[data-block=ctle] svg').getBoundingClientRect().bottom<innerHeight")
        for key in ("attenuator","reference","dfe","ctle"):
            js(f"document.querySelector('[data-design-block={key}]').click()")
            assert js("document.querySelectorAll('#designBlockGrid details[open]').length===1")
            assert js(f"document.querySelector('[data-block={key}] .design-block-canvas').scrollWidth<=document.querySelector('[data-block={key}] .design-block-canvas').clientWidth")
        js("(async()=>{selectTab('compare');await renderCompareEyes(state.designs.get(document.querySelector('#compareA').value),state.designs.get(document.querySelector('#compareB').value))})()")
        assert js("document.querySelector('#eyeAPlot svg')!==null && getComputedStyle(document.querySelector('#compareEmpty')).display==='none'")
        for mode in ("ctle","envelope","dfe"):
            js(f"document.querySelector('[data-signal-view={mode}]').click()")
            settle()
            assert js("document.querySelector('#eyeAPlot svg')!==null")
        shot(f"{width}-selected-eye")
        js("selectTab('results')")
        assert js("document.querySelector('#designInspector').getBoundingClientRect().left>document.querySelector('#designBlockGrid').getBoundingClientRect().left")
        for panel in ("specs","sizing","provenance","response"):
            js(f"document.querySelector('[data-inspector={panel}]').click()")
            assert js(f"!document.querySelector('[data-inspector-panel={panel}]').hidden")
            assert js("document.querySelectorAll('[data-inspector-panel]:not([hidden])').length===1")
            shot(f"{width}-inspector-{panel}")
        js("document.querySelector('#expandCircuit').click()")
        assert js("document.querySelector('#designInspector').hidden && document.querySelector('#circuitWorkbench').classList.contains('circuit-focus')")
        js("document.querySelector('#expandCircuit').click()")
        assert js("!document.querySelector('#designInspector').hidden")
        for selector in (".generated-drawing", "#referenceCheckpoint"):
            js(f"document.querySelector('{selector}').open=true;document.querySelector('{selector}').scrollIntoView({{block:'start',behavior:'instant'}})")
            assert js("document.documentElement.scrollWidth<=innerWidth")
            shot(f"{width}-evidence-{selector[1:]}")
            js(f"document.querySelector('{selector}').open=false")
        # Replay the completion UI with a real saved result; no simulator call.
        js(f"(async()=>{{const original=api;try{{api=async(url,...args)=>url.startsWith('/api/jobs/')?({{status:'complete',result:state.designs.get('{physical}')}}):original(url,...args);await pollJob('rehearsal',()=>{{}})}}finally{{api=original}}}})()")
        assert js("scrollY===0 && document.body.dataset.view==='results' && document.activeElement.id==='resultOverview'")
        js("new Promise((r,j)=>{let n=0,t=setInterval(()=>{if(document.querySelector('#designAcPlot svg')){clearInterval(t);r(true)}else if(++n>100){clearInterval(t);j('eye timeout')}},100)})")
        js("selectTab('results');document.querySelector('#peakingInput').value='8';document.querySelector('#peakingInput').dispatchEvent(new Event('input'));selectTab('results')")
        assert js("document.querySelector('#designAcPlot svg')!==null && document.querySelector('#selectedRun').value===state.current.id")
        assert js("document.querySelector('#resultHighlights').innerText.includes('341.8')")
        js("document.querySelector('#referenceCheckpoint').open=true")
        assert js("document.querySelector('#hardwareRequestedTarget').textContent==='9 dB at 1.9 GHz'")
        for key in ("ctle","attenuator","dfe","rc","reference"):
            js(f"document.querySelector('[data-circuit={key}]').click()")
            assert js("document.querySelector('#circuitViewCanvas').scrollWidth<=document.querySelector('#circuitViewCanvas').clientWidth")
        js("document.querySelector('#hardwareMatchedEvidence').scrollIntoView({block:'start',behavior:'instant'});document.querySelector('#hardwareEye').decode()")
        shot(f"{width}-reference-eye")
        js("document.querySelector('#referenceCheckpoint').open=false;selectTab('pvt')")
        assert js("scrollY===0 && document.querySelectorAll('.pvt-cell').length===45")
        assert js("document.querySelector('#pvtGrid').getBoundingClientRect().bottom<innerHeight")
        shot(f"{width}-pvt")
        js("selectTab('results')"); shot(f"{width}-explorer")
        assert js("document.querySelectorAll('#resultsView #designBlockGrid details').length===4 && document.querySelector('[data-tab=hardware]')===null")
        js("document.querySelector('#setTargetButton').click()")
        assert js("document.querySelector('#targetDialog').open && document.activeElement.id==='peakingInput'")
        shot(f"{width}-target-dialog")
        js("document.querySelector('#closeTargetDialog').click()")
        js("enterJudgeMode()")
        assert js("state.current.id==='judge-demo' && document.querySelector('#designAcPlot svg')===null")
        js(f"document.querySelector('#selectedRun').value='{physical}';document.querySelector('#selectedRun').dispatchEvent(new Event('change'))")
        js("new Promise((r,j)=>{let n=0,t=setInterval(()=>{if(document.querySelector('#designAcPlot svg')){clearInterval(t);r(true)}else if(++n>100){clearInterval(t);j('eye timeout')}},100)})")
        assert js("document.querySelector('#designAcScope').textContent.includes('physical-7c2475d5c7e0b0c6')")
        js("exitJudgeMode()")
        records.append({"width":width,"height":height,"saved_3db_eye":"PASS","completion_landing":"PASS","ctle_fits_initial_view":"PASS","separate_reference":"PASS","four_expandable_explorer_circuits":"PASS","compare_waveform_modes":"PASS","target_dialog":"PASS","adjacent_inspector":"PASS","four_inspector_modes":"PASS","expand_circuit":"PASS","evidence_panels":"PASS","pvt_cells":45})
    call("Emulation.setDeviceMetricsOverride",{"width":1440,"height":1000,"deviceScaleFactor":1,"mobile":False})
    js("selectTab('results');scrollTo(0,0)")
    cover=shot("report-explorer")
    asset=ROOT/"nebula/report/assets/submission_20260914/receiver_desktop.png"
    asset.write_bytes(cover.read_bytes())
    assert not exceptions,exceptions
    (out/"checks.json").write_text(json.dumps({"desktop_checks":records,"runtime_exceptions":exceptions,"new_jobs_submitted":0,"completion_test":"real saved result replayed through pollJob"},indent=2)+"\n")
    ws.close()
    print(json.dumps(records))


if __name__=="__main__":
    main()
