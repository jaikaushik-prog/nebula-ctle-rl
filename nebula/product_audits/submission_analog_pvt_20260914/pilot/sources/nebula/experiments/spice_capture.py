"""Direct-to-disk diagnostic capture for bounded new SPICE experiments."""
from pathlib import Path
import shutil
import subprocess

from nebula.device.crosscheck import assert_no_silent_failures
from nebula.device.ngspice_runner import ngspice_path
from nebula.device.sky130_runner import SPICE_DIR

MAX_SECONDS=180


def invoke(deck,folder,timeout_s=MAX_SECONDS):
    if not 0<timeout_s<=MAX_SECONDS: raise ValueError('unregistered simulator timeout')
    folder=Path(folder); folder.mkdir(parents=True,exist_ok=False)
    (folder/'design.cir').write_text(deck,encoding='ascii')
    shutil.copyfile(SPICE_DIR/'.spiceinit',folder/'.spiceinit')
    with (folder/'ngspice.log').open('wb') as capture:
        try:
            run=subprocess.run([str(ngspice_path()),'-b','design.cir'],cwd=folder,
                               stdout=capture,stderr=subprocess.STDOUT,timeout=timeout_s)
        except subprocess.TimeoutExpired as exc:
            # The actual bytes are already on disk, regardless of the exception's
            # platform-dependent stdout/stderr capture types.
            raise ValueError(f'ngspice timed out after {timeout_s:g} s; partial log retained; no retry') from exc
    log=(folder/'ngspice.log').read_text(encoding='utf-8',errors='replace')
    if run.returncode: raise ValueError(f'ngspice exit {run.returncode}; log retained')
    assert_no_silent_failures(log)
    return log
