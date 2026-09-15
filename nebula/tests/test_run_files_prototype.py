from pathlib import Path
STATIC=Path('nebula/web/static')

def test_prototype_is_run_files_only_and_lazy():
    html=(STATIC/'index.html').read_text(encoding='utf-8')
    js=(STATIC/'prototype_run_files.js').read_text(encoding='utf-8')
    assert html.index('id="evidenceView"') < html.index('id="programmableRunEvidence"') < html.index('id="judgeEvidenceIndex"')
    assert "details.open&&!loaded" in js and "token!==revision" in js
    assert 'NebulaRunPrototype.render(design)' in (STATIC/'judge_evidence.js').read_text(encoding='utf-8')
    assert html.index('/prototype_run_files.js') < html.index('/judge_evidence.js')

def test_prototype_retains_scope_and_no_generation_control():
    js=(STATIC/'prototype_run_files.js').read_text(encoding='utf-8')
    for phrase in ('setting 352 remains the accepted fixed CTLE','full receiver verification remains future work',
        'signed model-domain violations','Noise instrumentation was rejected','not RL','No runtime retuning',
        'do not replace the primary circuit','d.full_receiver_verified!==false','NebulaEvidenceLoading.failure'):
        assert phrase in js
    assert '/api/design' not in js and 'type="range"' not in js

def test_prototype_missing_parent_does_not_inherit_results():
    js=(STATIC/'prototype_run_files.js').read_text(encoding='utf-8')
    assert "if(!d){content.replaceChildren" in js and 'No matching saved programmable prototype' in js
    assert 'panel.replaceChildren();panel.hidden=true' in js
