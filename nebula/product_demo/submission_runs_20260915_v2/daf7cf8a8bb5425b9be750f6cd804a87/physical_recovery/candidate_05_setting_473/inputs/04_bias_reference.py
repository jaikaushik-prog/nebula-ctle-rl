"""Opt-in physical-bias prototype; frozen production/RL circuits are untouched.

The resistor-biased PMOS mirror is supply/process/temperature dependent. A
nominal calibration is NOT evidence of a precision current reference. Geometry
is frozen after that one calibration and must be measured in the loaded CTLE.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re

from nebula.device.passives import (
    CapacitorGeometry, ResistorGeometry, capacitor_geometry, resistor_geometry,
)
from nebula.report.product_scope import circuit_lines
from nebula.report.schematic import params_of


@dataclass(frozen=True)
class ReferenceGeometry:
    w_um: float
    l_um: float
    nf: int
    target_current_a: float
    calibration_gate_v: float
    resistor: ResistorGeometry
    capacitor: CapacitorGeometry


def reference_geometry(source: str, calibration_gate_v: float) -> ReferenceGeometry:
    """Map one TT diode-PMOS measurement to fixed, canonical PDK geometry."""
    p = params_of(source)
    v = float(calibration_gate_v)
    if not math.isfinite(v) or not 0 < v < p['VDD']:
        raise ValueError('calibration gate voltage must lie strictly between ground and VDD')
    for name in ('WREF', 'LT', 'NFREF', 'IREF', 'CBYP'):
        if not math.isfinite(p[name]) or p[name] <= 0:
            raise ValueError(f'invalid reference parameter {name}')
    if p['NFREF'] != int(p['NFREF']):
        raise ValueError('NFREF must be an integer')
    return ReferenceGeometry(
        p['WREF'], p['LT'], int(p['NFREF']), p['IREF'], v,
        resistor_geometry(v / p['IREF']), capacitor_geometry(p['CBYP']),
    )


def calibration_deck(source: str) -> str:
    """An isolated diode-PMOS measurement, not the deliverable bias circuit."""
    p = params_of(source)
    lib = next(x for x in source.splitlines() if x.lower().startswith('.lib '))
    return f'''* Entry 103 isolated TT calibration; Ical is measurement apparatus ONLY
{lib}
.temp 27
Vdd vdd 0 {p['VDD']:.16g}
Xbpref p_bias p_bias vdd vdd sky130_fd_pr__pfet_01v8 W={p['WREF']:.16g} L={p['LT']:.16g} nf={int(p['NFREF'])}
Ical p_bias 0 {p['IREF']:.16g}
.control
set noaskquit
set numdgt=15
op
print v(p_bias)
quit
.endc
.end
'''


def physical_reference_deck(source: str, geometry: ReferenceGeometry) -> str:
    """Replace exactly the old ideal reference/cap; refuse other topologies."""
    lines = circuit_lines(source)
    expected = {
        'iref': ['iref', 'vdd', 'nbias', '{iref}'],
        'cbyp': ['cbyp', 'nbias', '0', '{cbyp}'],
    }
    for name, words in expected.items():
        found = [line.split() for line in lines if line.split()[0] == name]
        if found != [words]:
            raise ValueError(f'expected exactly the original {name} topology')
    if any(line.split()[0] in ('xbpref', 'xbpfeed', 'xrbias', 'xcbyp') for line in lines):
        raise ValueError('physical bias component already present')
    # Refuse applying calibration geometry to another nominal reference.
    if reference_geometry(source, geometry.calibration_gate_v) != geometry:
        raise ValueError('reference geometry does not belong to this source')
    g, r, c = geometry, geometry.resistor, geometry.capacitor
    branch = f'''* Physical supply-dependent reference prototype, not a precision reference.
* IREF is the nominal sizing target below, not an ideal current source.
Xbpref p_bias p_bias vdd vdd sky130_fd_pr__pfet_01v8 W={g.w_um:.16g} L={g.l_um:.16g} nf={g.nf}
Xbpfeed nbias p_bias vdd vdd sky130_fd_pr__pfet_01v8 W={g.w_um:.16g} L={g.l_um:.16g} nf={g.nf}
Xrbias p_bias 0 0 {r.subckt} w={r.w_um:.16g} l={r.l_um:.16g} m={r.m}'''
    deck = re.sub(r'^Iref\s+.*$', lambda _: branch, source, flags=re.M | re.I)
    # Historical bypass comment claimed an ideal-cap comparison, not this model.
    deck = re.sub(r'^\* Bias-node bypass\.[\s\S]*?(?=^Cbyp\s)', '', deck, flags=re.M)
    cap = (f'* Physical MIM bypass; body/plate area is counted, layout remains unverified.\n'
           f'Xcbyp nbias 0 {c.subckt} w={c.w_um:.16g} l={c.l_um:.16g} m={c.m}')
    return re.sub(r'^Cbyp\s+.*$', lambda _: cap, deck, flags=re.M | re.I)
