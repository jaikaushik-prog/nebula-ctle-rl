"""Read-only audit of the final circuit's saved warnings and model provenance."""
from pathlib import Path
import argparse
import json
import re

from nebula.experiments.exp_post_review_attribution import ROOT, frozen_plan, sha

PHYSICAL = ROOT / 'nebula/product_demo/physical_bias_9db_1p9ghz_20260906/physical_evidence'
NONLINEAR = {'p2', 'q2', 'p3', 'q3'}


def ignored_parameters(log):
    return sorted(set(re.findall(r'unrecognized parameter\s*\(([^)]+)\)\s*-\s*ignored', log, re.I)))


def run(out):
    protocol = frozen_plan()
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((PHYSICAL / 'evidence_sha256.json').read_text())
    for name, expected in manifest.items():
        path = (PHYSICAL / name).resolve()
        if not path.is_relative_to(PHYSICAL.resolve()) or sha(path) != expected:
            raise ValueError('saved physical evidence integrity failure')
    records = []
    for path in sorted(PHYSICAL.rglob('ngspice.log')):
        ignored = ignored_parameters(path.read_text())
        records.append(dict(path=str(path.relative_to(ROOT)), sha256=sha(path),
                            ignored=ignored, omitted_nonlinear_terms=sorted(NONLINEAR.intersection(ignored))))
    if not records or not any(r['omitted_nonlinear_terms'] for r in records):
        raise ValueError('expected ignored-term finding did not reproduce; inspect before reporting')
    deck = (PHYSICAL / 'design.cir').read_text()
    resistors = [line for line in deck.splitlines() if line.lower().startswith('x') and 'res_high_po ' in line]
    from nebula.device.sky130_runner import lib_for_device
    lib = lib_for_device('sky130_fd_pr__nfet_01v8', real_passives=True, section='tt', include_pfet=True)
    includes = re.findall(r'^\.include\s+"([^"]+)"', lib.read_text(), re.M)
    models = []
    for name in includes:
        path = Path(name)
        if path.name in ('sky130_fd_pr__res_high_po.model.spice', 'sky130_fd_pr__res_high_po_0p69.model.spice'):
            text = path.read_text()
            models.append(dict(path=str(path), sha256=sha(path),
                               generic_coefficients=all(re.search(r'\b' + key + r'\s*=', text) for key in NONLINEAR),
                               voltage_expression='abs(v(r0,r1))' in text))
    if len(models) != 2:
        raise ValueError('expected two independently referenced resistor model families')
    result = dict(status='OMITTED_RESISTOR_NONLINEARITY_CONFIRMED', protocol_sha256=protocol,
                  simulations_run=0, saved_logs=len(records), log_records=records,
                  instantiated_generic_resistors=resistors, model_sources=models,
                  saved_evidence_files_verified=len(manifest), hd3_full_passive_linearity='NOT_VERIFIED',
                  circuit_changed=False,
                  conclusion='Saved HD3 extraction is valid for the simulated model. Generic resistor voltage coefficients are ignored. Fixed-width PDK resistors have supported voltage expressions but different resistance and parasitics; no drop-in equivalence or corrected-circuit compliance is established.')
    (out / 'summary.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    (out / 'sha256.json').write_text(json.dumps({'summary.json': sha(out / 'summary.json')}, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    run(parser.parse_args().out)
