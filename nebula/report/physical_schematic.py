"""Exact-deck physical-bias schematic; named nets join the three panels.

Unlike the historical renderer this checks ordered MOS pins and draws the
PMOS reference and physical bypass. All 27 physical instances are represented.
"""
from __future__ import annotations

import re
from pathlib import Path

from nebula.report.product_scope import area_inventory, circuit_lines, circuit_signature
from nebula.report.schematic import params_of, _wire, _node, _gnd, _res_v, _res_h, _cap_v, _cap_h

NFET = 'sky130_fd_pr__nfet_01v8'
PFET = 'sky130_fd_pr__pfet_01v8'
RES = 'sky130_fd_pr__res_high_po'
CAP = 'sky130_fd_pr__cap_mim_m3_1'


def physical_components(deck):
    """Refuse wrong models, swapped pins, duplicates or omitted components."""
    inventory = area_inventory(deck)
    components = {r['name']: r for r in inventory['components']}
    expected = {
        'xm1': (('outp', 'inp', 's1', '0'), NFET),
        'xm2': (('outn', 'inn', 's2', '0'), NFET),
        'xmt1': (('s1', 'nbias', '0', '0'), NFET),
        'xmt2': (('s2', 'nbias', '0', '0'), NFET),
        'xmr': (('nbias', 'nbias', '0', '0'), NFET),
        'xrlp': (('vdd', 'outp', '0'), RES), 'xrln': (('vdd', 'outn', '0'), RES),
        'xrs': (('s1', 's2', '0'), RES), 'xcs': (('s1', 's2'), CAP),
        'xbpref': (('p_bias', 'p_bias', 'vdd', 'vdd'), PFET),
        'xbpfeed': (('nbias', 'p_bias', 'vdd', 'vdd'), PFET),
        'xrbias': (('p_bias', '0', '0'), RES), 'xcbyp': (('nbias', '0'), CAP),
    }
    for side, external, internal in [('p', 'inx', 'inp'), ('n', 'iny', 'inn')]:
        expected[f'xatt_s{side}'] = ((external, internal, '0'), RES)
        for bit in range(3):
            expected[f'xatt_r{side}{bit}'] = ((internal, f'att_{side}{bit}', '0'), RES)
            name = f'xatt_sw{side}{bit}'
            row = components.get(name, {})
            tokens = row.get('netlist_line', '').split()
            gate = tokens[2] if len(tokens) >= 6 else None
            if gate not in ('0', 'vdd'):
                raise ValueError(f'{name}: unsupported switch control')
            expected[name] = ((f'att_{side}{bit}', gate, 'cm', 'vdd'), PFET)
    for name, (nodes, model) in expected.items():
        row = components.get(name)
        if row is None or row.get('model') != model:
            raise ValueError(f'{name}: absent or unexpected physical model')
        if tuple(row['netlist_line'].split()[1:1+len(nodes)]) != nodes:
            raise ValueError(f'{name}: ordered connectivity does not match drawing')
    physical = {name for name in components if name.startswith('x')}
    if physical != set(expected) or inventory['unresolved']:
        raise ValueError('unrepresented physical or ideal components in schematic')
    for name, nodes in [('clp', ('outp', '0')), ('cln', ('outn', '0'))]:
        if tuple(components.get(name, {}).get('netlist_line', '').split()[1:3]) != nodes:
            raise ValueError(f'{name}: wrong external load connection')
    return components


def draw_physical_schematic(netlist, out_path, *, title='CTLE with physical reference',
                            subtitle=None, extra=None, warning=None):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle

    c = physical_components(netlist)
    p = params_of(netlist)
    fig = plt.figure(figsize=(19, 12), facecolor='white')
    fig.suptitle(title + (' - NEEDS WORK' if warning else ''), x=.045, y=.975,
                 ha='left', fontsize=21, weight='bold', color='#16202b')
    fig.text(.045, .937, subtitle or 'Exact measured deck; equal node names connect between panels.', fontsize=10)

    def panel(rect, heading, ymax=10):
        ax = fig.add_axes(rect)
        ax.set(xlim=(0, 10), ylim=(-.4, ymax))
        ax.axis('off')
        ax.set_title(heading, loc='left', fontsize=13, weight='bold', pad=12)
        return ax

    def text(ax, x, y, label, **kwargs):
        ax.text(x, y, label, fontsize=8.6, color='#16202b', **kwargs)

    def size(name):
        r = c[name]
        return f"{r['w_um']:.4g} x {r['l_um']:.4g} um" + (f"; m={r['multiplier']:g}" if r['multiplier'] != 1 else '')

    def mos(ax, x, y, name, gate, *, pmos=False, label_side=1):
        # D at lower pin for PMOS, upper for NMOS; source is the opposite pin.
        _wire(ax, (x, y+.6), (x, y+.35), (x-.3, y+.35))
        _wire(ax, (x, y-.6), (x, y-.35), (x-.3, y-.35))
        _wire(ax, (x-.3, y-.42), (x-.3, y+.42))
        _wire(ax, (x-.46, y-.4), (x-.46, y+.4))
        _wire(ax, (x-.9, y), (x-.56 if pmos else x-.46, y))
        if pmos:
            ax.add_patch(Circle((x-.51, y), .05, ec='#16202b', fc='white', lw=1.3))
        text(ax, x-.95, y+.07, gate, ha='right')
        dx = .17 if label_side > 0 else -1.25
        text(ax, x+dx, y+.28, name.upper() + (' (P)' if pmos else ' (N)'))
        text(ax, x+dx, y-.02, size(name))
        text(ax, x+dx, y-.30, 'bulk=VDD' if pmos else 'bulk=0')

    core = panel([.045, .43, .47, .46], '01 / CTLE core - fixed drawn Rs and Cs')
    _wire(core, (1.8, 9.1), (7.6, 9.1))
    text(core, 4.7, 9.4, f"VDD = {p['VDD']:g} V", ha='center')
    for x, pair, tail, load, inp, out, src in [
        (2.3, 'xm1', 'xmt1', 'xrlp', 'inp', 'outp', 's1'),
        (7.1, 'xm2', 'xmt2', 'xrln', 'inn', 'outn', 's2')]:
        _wire(core, (x, 9.1), (x, 8.55))
        _res_v(core, x, 8.12)
        _wire(core, (x, 7.69), (x, 6.4))
        text(core, x+.3, 8.2, load.upper())
        text(core, x+.3, 7.9, size(load))
        _node(core, x, 7.1)
        text(core, x-.16, 7.2, out, ha='right')
        mos(core, x, 5.8, pair, inp)
        _wire(core, (x, 5.2), (x, 2.1))
        _node(core, x, 4.6)
        text(core, x+.17, 4.8, src)
        mos(core, x, 1.5, tail, 'nbias')
        _wire(core, (x, .9), (x, .35))
        _gnd(core, x, .35)
        # External load is a named-net branch, so it cannot touch an input gate.
        cx = x + 1.55
        _wire(core, (x, 7.1), (cx, 7.1), (cx, 6.88))
        _cap_v(core, cx, 6.8)
        _wire(core, (cx, 6.72), (cx, 6.6))
        _gnd(core, cx, 6.6)
    _wire(core, (2.3, 4.1), (4.27, 4.1))
    _res_h(core, 4.7, 4.1)
    _wire(core, (5.13, 4.1), (7.1, 4.1))
    text(core, 4.7, 4.4, 'XRS ' + size('xrs'), ha='center')
    _wire(core, (2.3, 3.0), (4.62, 3.0))
    _cap_h(core, 4.7, 3.0)
    _wire(core, (4.78, 3.0), (7.1, 3.0))
    text(core, 4.7, 3.4, 'XCS ' + size('xcs'), ha='center')
    text(core, 4.7, -.2, f"CLp / CLn: {p['CL']*1e15:.4g} fF each, assumed external", ha='center')

    bias = panel([.55, .43, .405, .46], '02 / Physical supply-dependent reference + bypass')
    _wire(bias, (1.8, 9.1), (7.0, 9.1))
    text(bias, 4.5, 9.4, 'VDD', ha='center')
    for x, name in [(2.2, 'xbpref'), (6.6, 'xbpfeed')]:
        _wire(bias, (x, 9.1), (x, 8.0))
        mos(bias, x, 7.4, name, 'p_bias', pmos=True)
        _wire(bias, (x, 6.8), (x, 5.6))
    # Gates are explicitly named above; diode tie is also wired here.
    _wire(bias, (2.2, 6.2), (.95, 6.2), (.95, 7.4), (1.3, 7.4))
    _node(bias, 2.2, 6.2)
    text(bias, 2.35, 6.25, 'p_bias')
    _wire(bias, (2.2, 5.6), (2.2, 4.83))
    _res_v(bias, 2.2, 4.4)
    _wire(bias, (2.2, 3.97), (2.2, 1.2))
    _gnd(bias, 2.2, 1.2)
    text(bias, 2.5, 4.6, 'XRBIAS')
    text(bias, 2.5, 4.25, size('xrbias'))
    _node(bias, 6.6, 5.6)
    text(bias, 6.75, 5.8, 'nbias -> both tail gates')
    _wire(bias, (6.6, 5.6), (6.6, 3.6))
    mos(bias, 6.6, 3., 'xmr', 'nbias')
    _wire(bias, (6.6, 4.5), (5.5, 4.5), (5.5, 3.), (5.7, 3.))
    _node(bias, 6.6, 4.5)
    _wire(bias, (6.6, 2.4), (6.6, 1.2))
    _gnd(bias, 6.6, 1.2)
    _wire(bias, (6.6, 5.6), (9.2, 5.6), (9.2, 4.88))
    _cap_v(bias, 9.2, 4.8)
    _wire(bias, (9.2, 4.72), (9.2, 4.4))
    _gnd(bias, 9.2, 4.4)
    text(bias, 9.2, 3.65, 'XCBYP', ha='center')
    text(bias, 9.2, 3.32, size('xcbyp'), ha='center')
    text(bias, .3, .3, 'IREF is a sizing target, not an ideal source. Current varies with PVT.')
    text(bias, .3, -.05, 'All dimensions parsed from design.cir. MIM plate area is included.')

    # Both halves are shown. Gate labels are actual 0/VDD values from the deck.
    for side, external, internal, rect in [
        ('p', 'inx', 'inp', [.045, .09, .29, .25]),
        ('n', 'iny', 'inn', [.355, .09, .29, .25])]:
        ax = panel(rect, f'03{side} / Physical input attenuator ({side} side)', ymax=7)
        _wire(ax, (.5, 6.2), (1.27, 6.2))
        _res_h(ax, 1.7, 6.2)
        _wire(ax, (2.13, 6.2), (9.2, 6.2))
        text(ax, .5, 6.6, external)
        text(ax, 9.2, 6.6, internal, ha='right')
        text(ax, .5, 5.5, f'XATT_S{side.upper()}\n' + size(f'xatt_s{side}'))
        for bit, x in enumerate((3.1, 5.95, 8.8)):
            r, sw = f'xatt_r{side}{bit}', f'xatt_sw{side}{bit}'
            _node(ax, x, 6.2)
            _wire(ax, (x, 6.2), (x, 4.53))
            _res_v(ax, x, 4.1)
            _wire(ax, (x, 3.67), (x, 2.8))
            text(ax, x, 4.85, r.upper(), ha='center')
            text(ax, x, 4.57, size(r), ha='center', rotation=0)
            # For these attenuator PMOS: drawn top is drain, lower terminal
            # is source cm. Symbol polarity alone does not swap netlisted pins.
            _wire(ax, (x, 2.8), (x, 2.35), (x-.3, 2.35))
            _wire(ax, (x, 1.15), (x, 1.65), (x-.3, 1.65))
            _wire(ax, (x-.3, 1.6), (x-.3, 2.4))
            _wire(ax, (x-.46, 1.6), (x-.46, 2.4))
            ax.add_patch(Circle((x-.53, 2.), .07, ec='#16202b', fc='white'))
            _wire(ax, (x-.60, 2.), (x-1.0, 2.))
            gate = c[sw]['netlist_line'].split()[2]
            text(ax, x-1., 2.22, gate.upper(), ha='right')
            text(ax, x+.14, 2.3, sw.upper().replace('XATT_', ''))
            text(ax, x+.14, 1.9, size(sw))
            text(ax, x, .8, 'S=cm; B=VDD', ha='center')
            text(ax, x, 3.1, f'att_{side}{bit}', ha='center')
        text(ax, .5, -.05, f'External cm = {p["VCM"]:.5g} V (ideal testbench supply).')

    notes = panel([.68, .08, .275, .26], 'Scope and evidence', ymax=10)
    import textwrap
    area = area_inventory(netlist)
    paragraphs = [
        f"Counted gate/body/plate subtotal: {area['geometry_subtotal_mm2']:.8f} mm2. Full S7 layout area remains UNKNOWN.",
        '1-tap DFE: behavioural link model only; no DFE, slicer or clock transistors in this deck.',
        'Rs/Cs selector hardware is not implemented. This is one fixed geometry, not a complete programmable IC.',
        'Equal node names connect across panels. Poly resistor substrates are tied to 0; MIM has two terminals.',
        'Circuit signature: ' + circuit_signature(netlist)[:20],
    ]
    if warning:
        paragraphs.insert(0, warning)
    notes.text(0, 9.5, '\n\n'.join(textwrap.fill(s, 57) for s in paragraphs), va='top', fontsize=9.4, linespacing=1.25)
    fig.text(.045, .025, 'SKY130 transistor/passive models | Geometry dimensions are W x L, not laid-out footprints | Exact deck and raw evidence accompany this drawing', fontsize=9, color='#5d6b7a')
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180, facecolor='white')
    plt.close(fig)
    return path
