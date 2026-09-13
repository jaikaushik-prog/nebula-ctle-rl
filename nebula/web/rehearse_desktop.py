"""Rehearse the saved desktop path in an already running local CDP browser.

Requires the app at port 8876 and a local browser debugging port 9223.
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
    tab=next(t for t in tabs if t["type"]=="page" and "127.0.0.1:8876" in t["url"])
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
    js("new Promise((resolve,reject)=>{let n=0;let t=setInterval(()=>{if(document.querySelectorAll('[data-circuit]').length===5 && document.querySelectorAll('#designBlockGrid details').length===4){clearInterval(t);resolve(true)}else if(++n>200){clearInterval(t);reject('initialization timeout')}},100)})")
    records=[]
    for width,height in ((1440,1000),(1280,900)):
        call("Emulation.setDeviceMetricsOverride",{"width":width,"height":height,"deviceScaleFactor":1,"mobile":False})
        js("selectTab('hardware');scrollTo(0,0)"); shot(f"{width}-receiver")
        assert js("document.documentElement.scrollWidth<=innerWidth")
        for key in ("dfe","attenuator","ctle","rc","reference"):
            js(f"document.querySelector('[data-circuit={key}]').click();document.querySelector('.circuit-inspector').scrollIntoView({{block:'start',behavior:'instant'}})")
            shot(f"{width}-{key}")
            assert js(f"document.querySelector('[data-circuit={key}]').getAttribute('aria-pressed')==='true'")
        js("document.querySelector('#hardwareMatchedEvidence').scrollIntoView({block:'start',behavior:'instant'})")
        js("document.querySelector('#hardwareEye').decode()")
        shot(f"{width}-measurements")
        js("selectTab('results');scrollTo(0,0)"); shot(f"{width}-explorer")
        for key in ("ctle","dfe","reference","attenuator"):
            js(f"document.querySelector('[data-block={key}] summary').click()")
            assert js("document.querySelectorAll('#designBlockGrid details[open]').length===1")
        js("document.querySelector('#peakingInput').value='8';document.querySelector('#peakingInput').dispatchEvent(new Event('input'));selectTab('hardware')")
        assert js("document.querySelector('#hardwareMatchedEvidence').hidden")
        shot(f"{width}-mismatch")
        js("enterJudgeMode()")
        assert js("document.querySelector('#peakingInput').value==='9' && !document.querySelector('#hardwareMatchedEvidence').hidden")
        js("selectTab('pvt');scrollTo(0,0)"); shot(f"{width}-design-pvt")
        assert js("document.querySelectorAll('.pvt-cell').length===45")
        js("selectTab('evidence');scrollTo(0,0)"); shot(f"{width}-files")
        records.append({"width":width,"height":height,"initialization":"PASS","circuits":5,
                        "accordion":"PASS","target_mismatch":"PASS","judge_target_reset":"PASS","pvt_cells":45})
        js("exitJudgeMode()")
    call("Emulation.setDeviceMetricsOverride",{"width":1440,"height":1000,"deviceScaleFactor":1,"mobile":False})
    js("selectTab('hardware');document.querySelector('[data-circuit=dfe]').click();scrollTo(0,0)")
    cover=shot("report-receiver")
    asset=ROOT/"nebula/report/assets/submission_20260914/receiver_desktop.png"
    asset.parent.mkdir(parents=True,exist_ok=True); asset.write_bytes(cover.read_bytes())
    assert not exceptions,exceptions
    (out/"checks.json").write_text(json.dumps({"desktop_checks":records,"runtime_exceptions":exceptions,"new_jobs_submitted":0},indent=2)+"\n")
    ws.close()
    print(json.dumps(records))


if __name__=="__main__":
    main()
