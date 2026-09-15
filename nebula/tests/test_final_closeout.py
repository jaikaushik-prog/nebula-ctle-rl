from pathlib import Path

def test_simple_nebula_brand():
    text=(Path(__file__).parents[1]/'web/static/index.html').read_text()
    assert '<title>Nebula</title>' in text
    assert '<span>Nebula</span>' in text
    assert 'aria-label="Nebula home"' in text

def test_comparison_run_identity():
    text=(Path(__file__).parents[1]/'web/static/app.js').read_text()
    assert 'Historical adaptive bank' in text
    assert 'design.id.slice(0, 8)' in text
    assert '${design.status === "pass" ? "Accepted" : "FAILED"}' in text
