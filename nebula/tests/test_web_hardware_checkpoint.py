"""Frontend gates for the calibrated transistor CTLE + DFE checkpoint."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from nebula.web.hardware_checkpoint import (
    NOMINAL_SUMMARY,
    build_hardware_checkpoint,
)
from nebula.web.server import NebulaWebApp, make_server


def test_checkpoint_is_derived_from_frozen_nominal_and_pvt_evidence():
    shown = build_hardware_checkpoint()

    assert shown["id"] == "calibrated-transistor-dfe-entry144"
    assert shown["status"] == "pass"
    assert shown["controls"] == {
        "r_fraction": 0.7,
        "c_fraction": 0.185,
        "r_control_v_nominal": 1.26,
        "c_control_v_nominal": 0.333,
        "corner_retuning": False,
        "runtime_settling_verified": False,
    }
    assert [block["key"] for block in shown["topology"]] == [
        "attenuator", "ctle", "rs", "cs", "summer", "memory", "dac"]
    assert all(block["status"] == "implemented" for block in shown["topology"])

    nominal = shown["nominal"]
    assert nominal["boost_db"] == pytest.approx({
        "min": 8.743882759698478,
        "max": 8.746919126302751,
    })
    assert nominal["peak_frequency_hz"] == pytest.approx({
        "min": 1903117755.0807912,
        "max": 1906285212.4517019,
    })
    assert nominal["input_noise_vrms"]["max"] == pytest.approx(
        0.0006540509224963711)
    assert nominal["hd3_dbc"]["max"] == pytest.approx(-54.913713538981)
    assert nominal["correct_bits"] == nominal["scored_bits"] == 64
    assert nominal["sampled_eye_height_v"] == pytest.approx(
        0.21034034194371198)

    pvt = shown["pvt"]
    assert pvt["n_pass"] == pvt["n_points"] == 45
    assert pvt["all_pass"] is True
    assert len(pvt["corners"]) == 45
    assert all(row["status"] == "pass" for row in pvt["corners"])
    assert pvt["minimum_eye_height_v"] == pytest.approx(0.11324371549900603)
    assert pvt["minimum_positive_width_ui"] == pytest.approx(0.635)
    assert pvt["minimum_width_above_100mv_ui"] == pytest.approx(0.56)
    assert pvt["maximum_vdd_power_w"] == pytest.approx(0.0125240811345151)
    assert next(row for row in pvt["corners"] if row["corner"] == "tt_vdd1.00_t27")["label"] == "TT / 1.80 V / 27 C"


def test_checkpoint_fails_closed_if_the_pinned_summary_changes(tmp_path):
    changed = tmp_path / "summary.json"
    changed.write_bytes(NOMINAL_SUMMARY.read_bytes() + b"\n")

    with pytest.raises(ValueError, match="SHA-256"):
        build_hardware_checkpoint(nominal_summary=changed)


def test_checkpoint_exposes_only_named_review_artifacts(tmp_path):
    app = NebulaWebApp(run_root=tmp_path)
    try:
        shown = app.hardware_checkpoint()
        assert shown["provenance"]["nominal_entry"] == 143
        assert shown["provenance"]["pvt_entry"] == 144
        assert app.hardware_artifact("nominal-netlist").name == "design.cir"
        assert app.hardware_artifact("pvt-summary").name == "summary.json"
        assert app.hardware_artifact("../HANDOFF.md") is None
        assert app.hardware_artifact("missing") is None
    finally:
        app.close()


def test_hardware_api_and_allow_listed_artifact_are_served(tmp_path):
    app = NebulaWebApp(run_root=tmp_path)
    server = make_server(app, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(f"{base}/api/hardware") as response:
            shown = json.loads(response.read())
        assert shown["status_label"] == "45/45 LINK PVT"
        assert len(shown["pvt"]["corners"]) == 45

        with urlopen(
            f"{base}/api/hardware/artifacts/nominal-netlist"
        ) as response:
            deck = response.read().decode("utf-8")
        assert "Xrc_switch rc_mid rc_gate s2" in deck
        assert "Xdfe_dacp sum_p df_q fd_common" in deck
        for name in ("hardware-schematic", "nominal-eye"):
            with urlopen(f"{base}/api/hardware/artifacts/{name}") as response:
                assert response.headers["Content-Type"] == "image/png"
                assert response.read(8) == b"\x89PNG\r\n\x1a\n"

        with pytest.raises(HTTPError) as rejected:
            urlopen(f"{base}/api/hardware/artifacts/missing")
        assert rejected.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        app.close()
        thread.join(timeout=2)


def test_frontend_has_a_visible_transistor_hardware_view():
    static = Path("nebula/web/static")
    html = (static / "index.html").read_text(encoding="utf-8")
    js = (static / "app.js").read_text(encoding="utf-8")
    css = (static / "styles.css").read_text(encoding="utf-8")
    server = Path("nebula/web/server.py").read_text(encoding="utf-8")

    assert 'data-tab="hardware"' in html
    for identity in (
        "hardwareView", "hardwareTopology", "hardwareControlR",
        "hardwareControlC", "hardwarePvtGrid", "hardwareCornerDetail",
        "hardwareEvidence", "hardwareBoundary",
    ):
        assert f'id="{identity}"' in html
    assert "Transistor-level DFE" in html
    assert 'api("/api/hardware")' in js
    assert "renderHardwareCheckpoint" in js
    assert "drawHardwarePvt" in js
    assert ".hardware-signal-chain" in css
    assert 'path == "/api/hardware"' in server
    assert 'path.startswith("/api/hardware/artifacts/")' in server


def test_frontend_copy_keeps_the_new_checkpoint_scope_explicit():
    static = Path("nebula/web/static")
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (static / "index.html", static / "app.js")
    )

    assert "Link PVT" in text
    assert "Analog PVT is not verified" in text
    assert "finite noiseless" in text
    assert "legacy fixed Rs/Cs" in text


def test_eye_visual_uses_the_registered_waveform_and_aperture():
    from nebula.web.hardware_visuals import eye_data, devices
    offsets, waves, aperture = eye_data()
    assert waves.shape == (64, 401)
    assert offsets[0] == -1 and offsets[-1] == 1
    assert aperture["eye_width_at_100mv_ui"] == pytest.approx(.655)
    assert aperture["eye_width_ui"] == pytest.approx(.705)
    rows = devices()
    assert len(rows) == 73
    assert next(r for r in rows if r[0] == "Xdfe_dacp")[1] == ["sum_p", "df_q", "fd_common", "0"]


def test_visual_source_tamper_is_rejected(tmp_path):
    from nebula.web.hardware_visuals import pinned, TRACE_SHA
    changed = tmp_path / "trace.txt.gz"
    changed.write_bytes(b"incorrect waveform")
    with pytest.raises(ValueError, match="SHA-256"):
        pinned(changed, TRACE_SHA)


def test_block_view_connections_match_pinned_devices():
    from nebula.web.hardware_visuals import devices
    by_name = {r[0]: r[1] for r in devices()}
    expected = {
        "Xatt_sp": ["inx", "inp", "0"],
        "Xatt_swp0": ["att_p0", "0", "cm", "vdd"],
        "Xrc_rmax": ["s1", "s2", "0"],
        "Xrc_branch": ["s1", "rc_mid", "0"],
        "Xrc_switch": ["rc_mid", "rc_gate", "s2", "0"],
        "Xrc_var_s1": ["s1", "rc_ct", "0"],
        "Xrc_var_s2": ["s2", "rc_ct", "0"],
        "Xdfe_sump": ["sum_n", "outn", "sum_tail", "0"],
        "Xdfe_dacp": ["sum_p", "df_q", "fd_common", "0"],
        "XM1": ["outp", "inp", "s1", "0"],
    }
    for name, nets in expected.items():
        assert by_name[name] == nets


def test_circuit_selector_renders_all_views_and_rc_shortcut():
    import shutil
    import subprocess
    import xml.etree.ElementTree as ET
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for frontend interaction checks")
    script = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert');
class Element {
  constructor(){this.children=[];this.dataset={};this.attributes={};}
  replaceChildren(){this.children=[];}
  append(x){this.children.push(x);}
  addEventListener(name, fn){this[name]=fn;}
  setAttribute(k,v){this.attributes[k]=v;}
  querySelector(s){return this.children.find(x=>s.includes('"'+x.dataset.circuit+'"'));}
  focus(){this.focused=true;}
  scrollIntoView(){this.scrolled=true;}
}
const elements = new Map();
const document = {
  getElementById(id){if(!elements.has(id))elements.set(id,new Element());return elements.get(id);},
  createElement(){return new Element();},
  querySelector(){return document.getElementById('inspector');}
};
const context = vm.createContext({document});
vm.runInContext(fs.readFileSync('nebula/web/static/circuit_views.js','utf8')+
  '\nNebulaCircuitViews.mount({controls:{r_control_v_nominal:1.26,c_control_v_nominal:.333,r_fraction:.7,c_fraction:.185}});', context);
const buttons = document.getElementById('circuitViewButtons').children;
assert.equal(buttons.length,4);
assert.equal(buttons[0].attributes['aria-pressed'],'true');
const svgs = {};
for(const b of buttons){
  b.click();
  assert.equal(buttons.filter(x=>x.attributes['aria-pressed']==='true').length,1);
  svgs[b.dataset.circuit] = document.getElementById('circuitViewCanvas').innerHTML;
}
buttons[0].click();
document.getElementById('inspectRcButton').onclick();
assert.equal(buttons[3].attributes['aria-pressed'],'true');
assert(buttons[3].focused);
assert(document.getElementById('inspector').scrolled);
const desc=document.getElementById('circuitViewDescription').textContent;
assert(desc.includes('1.260 V') && desc.includes('0.333 V'));
assert(desc.includes('fresh SPICE') && desc.includes('saved calibration'));
process.stdout.write(JSON.stringify(svgs));
"""
    result = subprocess.run([node, "-e", script], check=True, capture_output=True, text=True)
    views = json.loads(result.stdout)
    assert set(views) == {"dfe", "attenuator", "ctle", "rc"}
    for svg in views.values():
        root = ET.fromstring(svg)
        assert root.attrib["role"] == "img"
        assert root.attrib["viewBox"] == "0 0 1040 340"
    assert "Feedback current" in views["dfe"]
    assert "Xatt_swp2" in views["attenuator"]
    assert "Xrc_var_s2" in views["rc"]
