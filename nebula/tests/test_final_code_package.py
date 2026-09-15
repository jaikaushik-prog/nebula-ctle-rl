"""Packaging safety only; no simulations or archive builds."""
import pytest
from nebula.final_code_package import safe

@pytest.mark.parametrize('path',[
    '../outside.py','C:/outside.py','nebula/.env','nebula/credentials.json',
    'nebula/resources/reference.py','nebula/sky130A/sky130.lib.spice',
    'nebula/report.pdf','nebula/demo.docx','nebula/video.mp4','nebula/cache.runlock.json',
    'nebula/final_demo_script_v2.py','nebula/SUBMISSION_FINAL_DEMO_SCRIPT.md',
    'nebula/INDEPENDENT_JUDGE_AUDIT_20260915.md',
])
def test_private_reference_and_out_of_scope_files_excluded(path):
    assert not safe(path)

@pytest.mark.parametrize('path',[
    'nebula/web/recovery_server.py','nebula/web/static/index.html',
    'nebula/device/spice/sky130_ctle.lib.spice',
    'nebula/experiments/shielded_policy_2026090504.pth',
    'nebula/product_demo/submission_runs_20260915_v2/run/design.cir',
])
def test_project_code_policies_and_decks_allowed(path):
    assert safe(path)
