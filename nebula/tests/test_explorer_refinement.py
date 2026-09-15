"""Presentation contracts; measurements and scientific sources are unchanged."""
from pathlib import Path
STATIC=Path('nebula/web/static')

def test_programmable_panel_is_not_loaded_in_explorer():
    html=(STATIC/'index.html').read_text(encoding='utf-8')
    js=(STATIC/'judge_evidence.js').read_text(encoding='utf-8')
    assert 'programmableReceiverOption' not in html
    assert '/programmable_option.js' not in html and 'NebulaProgrammable.render' not in js
    assert Path('nebula/programmable_option.py').is_file()
    assert Path('nebula/product_audits/entry160_programmable_receiver_review_20260915/review.json').is_file()

def test_circuit_scope_and_receiver_are_structured_disclosures():
    html=(STATIC/'index.html').read_text(encoding='utf-8')
    assert '<details class="circuit-selection-scope">' in html
    assert '<details id="selectedReceiverEvidence"' in html
    assert html.index('Selection and verification scope')<html.index('id="candidateCatalogue"')<html.index('id="circuitWorkbench"')
    js=(STATIC/'judge_evidence.js').read_text(encoding='utf-8')
    assert "metrics=el('dl')" in js and "el('dt',label)" in js
    assert 'Verification scope' in js and 'Six attenuator PMOS devices' in js
    assert 'Terminal voltages' in js and 'Simulator log' in js

def test_white_full_width_evidence_and_keyboard_focus():
    html=(STATIC/'index.html').read_text(encoding='utf-8')
    css=(STATIC/'explorer_refinement.css').read_text(encoding='utf-8')
    assert 'href="/explorer_refinement.css?v=4"' in html
    assert '.evidence-shelf { grid-template-columns: minmax(0,1fr)' in css
    assert 'background: var(--paper)' in css
    assert ':focus-visible' in css and '@media (max-width: 700px)' in css
