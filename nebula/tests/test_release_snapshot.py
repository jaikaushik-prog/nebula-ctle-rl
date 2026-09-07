import hashlib,json,zipfile
import pytest
from nebula.release_snapshot import included,verify_archive

@pytest.mark.parametrize('name',[
    'nebula/resources/reference.pdf','nebula/phd_thesis_reviewed_Basso.pdf',
    'nebula/.claude/settings.json','nebula/.env','nebula/credentials.json',
    '../outside.py','output/pdf/archive_20260906/Nebula_Competition_Report.pdf'])
def test_release_excludes_references_credentials_and_paths(name):
    assert not included(name)

@pytest.mark.parametrize('name',[
    'nebula/physical_design.py','nebula/device/spice/.spiceinit',
    'nebula/product_audits/example/tt/ac_noise/ngspice.log',
    'nebula/product_audits/example/inputs/15_.spiceinit',
    'nebula/experiments/shielded_bc_2026090500.pth',
    'output/pdf/Nebula_Competition_Report.pdf'])
def test_release_includes_required_runtime_and_our_report(name):
    assert included(name)

def test_release_verifier_detects_changed_payload(tmp_path):
    p=tmp_path/'bundle.zip'
    with zipfile.ZipFile(p,'w') as z:
        z.writestr('nebula/test.py','changed')
        z.writestr('RELEASE_MANIFEST.json',json.dumps({'files':{'nebula/test.py':hashlib.sha256(b'original').hexdigest()}}))
    with pytest.raises(ValueError,match='hash'):
        verify_archive(p)
