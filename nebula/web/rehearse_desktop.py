"""Rehearse the saved desktop path in an already running local CDP browser.

Requires the app at port 8877 and a local browser debugging port 9223.
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
    tab=next(t for t in tabs if t["type"]=="page" and "127.0.0.1:8877" in t["url"])
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
    js("new Promise((resolve,reject)=>{let n=0;let t=setInterval(()=>{if(state.current && state.designs.size>1 && document.querySelector('#selectedEye svg')){clearInterval(t);resolve(true)}else if(++n>200){clearInterval(t);reject('initialization timeout')}},100)})")
    records=[]
    physical=js("[...state.designs.values()].find(d=>d.method==='rl-physical' && d.request.peaking_db===3).id")
    for width,height in ((1440,1000),(1280,900)):
        call("Emulation.setDeviceMetricsOverride",{"width":width,"height":height,"deviceScaleFactor":1,"mobile":False})
        js(f"renderDesign(state.designs.get('{physical}'));selectTab('hardware')")
        js("new Promise((r,j)=>{let n=0,t=setInterval(()=>{if(document.querySelector('#selectedEye svg')){clearInterval(t);r(true)}else if(++n>100){clearInterval(t);j('eye timeout')}},100)})")
        shot(f"{width}-receiver")
        assert js("document.documentElement.scrollWidth<=innerWidth")
        assert js("document.querySelector('#resultVerdict').getBoundingClientRect().bottom<innerHeight")
        assert js("document.querySelector('#resultCoverage').getBoundingClientRect().bottom<innerHeight")
        assert js("document.querySelector('[data-block=ctle]').open && !document.querySelector('#referenceCheckpoint').open")
        assert js("document.querySelector('[data-block=ctle] svg').getBoundingClientRect().bottom<innerHeight")
        for key in ("attenuator","reference","ctle"):
            js(f"document.querySelector('[data-block={key}] summary').click()")
            assert js("document.querySelectorAll('#designBlockGrid details[open]').length===1")
            assert js(f"document.querySelector('[data-block={key}] .design-block-canvas').scrollWidth<=document.querySelector('[data-block={key}] .design-block-canvas').clientWidth")
        js("document.querySelector('#selectedEye').scrollIntoView({block:'center',behavior:'instant'})")
        shot(f"{width}-selected-eye")
        # Replay the completion UI with a real saved result; no simulator call.
        js(f"(async()=>{{const original=api;try{{api=async(url,...args)=>url.startsWith('/api/jobs/')?({{status:'complete',result:state.designs.get('{physical}')}}):original(url,...args);await pollJob('rehearsal',()=>{{}})}}finally{{api=original}}}})()")
        assert js("scrollY===0 && document.body.dataset.view==='hardware' && document.activeElement.id==='resultOverview'")
        js("new Promise((r,j)=>{let n=0,t=setInterval(()=>{if(document.querySelector('#selectedEye svg')){clearInterval(t);r(true)}else if(++n>100){clearInterval(t);j('eye timeout')}},100)})")
        js("selectTab('results');document.querySelector('#peakingInput').value='8';document.querySelector('#peakingInput').dispatchEvent(new Event('input'));selectTab('hardware')")
        assert js("document.querySelector('#selectedEye svg')!==null && document.querySelector('#selectedRun').value===state.current.id")
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
        assert js("document.querySelector('#resultsView #designBlockGrid')===null")
        js("enterJudgeMode()")
        assert js("state.current.id==='judge-demo' && document.querySelector('#selectedEye svg')===null")
        js(f"document.querySelector('#selectedRun').value='{physical}';document.querySelector('#selectedRun').dispatchEvent(new Event('change'))")
        js("new Promise((r,j)=>{let n=0,t=setInterval(()=>{if(document.querySelector('#selectedEye svg')){clearInterval(t);r(true)}else if(++n>100){clearInterval(t);j('eye timeout')}},100)})")
        assert js("document.querySelector('#selectedEyeScope').textContent.includes('physical-7c2475d5c7e0b0c6')")
        js("exitJudgeMode()")
        records.append({"width":width,"height":height,"saved_3db_eye":"PASS","completion_landing":"PASS","ctle_fits_initial_view":"PASS","separate_reference":"PASS","no_duplicate_explorer_circuits":"PASS","pvt_cells":45})
    call("Emulation.setDeviceMetricsOverride",{"width":1440,"height":1000,"deviceScaleFactor":1,"mobile":False})
    js("selectTab('hardware');scrollTo(0,0)")
    cover=shot("report-receiver")
    asset=ROOT/"nebula/report/assets/submission_20260914/receiver_desktop.png"
    asset.write_bytes(cover.read_bytes())
    assert not exceptions,exceptions
    (out/"checks.json").write_text(json.dumps({"desktop_checks":records,"runtime_exceptions":exceptions,"new_jobs_submitted":0,"completion_test":"real saved result replayed through pollJob"},indent=2)+"\n")
    ws.close()
    print(json.dumps(records))


if __name__=="__main__":
    main()
