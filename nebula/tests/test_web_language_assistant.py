"""Offline and opt-in contracts for optional browser language assistance."""
import json
from pathlib import Path
import shutil
import subprocess
import pytest

def run_js(body):
    node=shutil.which('node')
    if not node: pytest.skip('Node is required for browser helper tests')
    pre="const helper=require('./nebula/web/static/language_assistant.js');"
    proc=subprocess.run([node,'-e',pre+body],check=True,capture_output=True,text=True,timeout=10)
    return json.loads(proc.stdout)

def test_language_request_requires_available_explicit_opt_in():
    assert run_js("process.stdout.write(JSON.stringify([helper.enabled(false,true),helper.enabled(true,false),helper.enabled(true,true),helper.enabled('yes',true)]));") == [False,False,True,False]

def test_parser_provenance_keeps_source_and_notes():
    text=run_js("process.stdout.write(JSON.stringify(helper.parseLabel({parsed_by:'regex',peaking_db:6,f_peak_ghz:2.1,notes:['Provider unavailable; deterministic parser used.']})));")
    assert 'regex' in text and 'Provider unavailable' in text and '6 dB' in text

def test_explanation_is_text_and_missing_scope_does_not_disappear():
    item=run_js("process.stdout.write(JSON.stringify(helper.explanationView({text:'<img onerror=alert(1)>',source:'template',label:'Deterministic fallback',verdict:'MODEL PASS'})));")
    assert item['text']=='<img onerror=alert(1)>'
    assert item['label']=='Deterministic fallback'
    assert item['verdict']=='MODEL PASS' and 'outside' in item['scope']

def test_ui_exposes_separate_opt_in_and_plain_text_output():
    static=Path('nebula/web/static')
    html=(static/'index.html').read_text(encoding='utf-8')
    js=(static/'language_assistant.js').read_text(encoding='utf-8')
    app=(static/'app.js').read_text(encoding='utf-8')
    assert 'id="use-llm" type="checkbox" disabled' in html
    assert 'id="explanationUseLlm" type="checkbox" disabled' in html
    assert 'use_llm: NebulaLanguageAssistant.optedIn()' in app
    assert '.textContent = view.text' in js and 'innerHTML' not in js
    assert '/api/llm/availability' in js and '/api/llm/explain' in js
