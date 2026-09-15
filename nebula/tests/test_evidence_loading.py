"""Wrong-server navigation must not mix evidence between origins."""
from pathlib import Path

STATIC=Path('nebula/web/static')

def test_helper_loads_before_both_readers():
    html=(STATIC/'index.html').read_text(encoding='utf-8')
    assert html.index('/evidence_loading.js') < html.index('/judge_evidence.js')
    assert html.index('/evidence_loading.js') < html.index('/engineering_diagnostics.js')

def test_legacy_hint_is_narrow_and_does_not_fetch_another_origin():
    js=(STATIC/'evidence_loading.js').read_text(encoding='utf-8')
    assert "error.status===404" in js and "location.port==='8765'" in js
    assert "['127.0.0.1','localhost','[::1]']" in js
    assert "a.href='http://127.0.0.1:8766/#results'" in js
    assert 'fetch(' not in js and 'location.replace' not in js
    assert 'Retry saved evidence' in js and 'No verification claim added' in js

def test_both_readers_preserve_status_and_allow_retry():
    for name in ('judge_evidence.js','engineering_diagnostics.js'):
        js=(STATIC/name).read_text(encoding='utf-8')
        assert 'status:response.status' in js
        assert 'NebulaEvidenceLoading.failure' in js
        assert 'no-store' in js
