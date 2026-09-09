"""Drawn-terminal model-domain diagnostics, NOT lifetime/reliability signoff.

Bounds: https://skywater-pdk.readthedocs.io/en/main/rules/device-details.html
Standard 1.8 V NMOS and PMOS model-validity sections, checked 2026-09-06.
Signed voltages use the exact netlisted D/G/S/B; no source/drain swapping.
"""
import numpy as np

from nebula.device import dfe_hardware as D

BOUNDS = {
    D.NFET: {'vds': (0, 1.95), 'vgs': (0, 1.95), 'vbs': (-1.95, .3)},
    D.PFET: {'vds': (-1.95, 0), 'vgs': (-1.95, 0), 'vbs': (-.1, 1.95)},
}


def read_nodes(path, names, expected_time):
    data = np.loadtxt(path)
    if (not names or len(set(names)) != len(names) or data.ndim != 2
            or data.shape[1] != 2*len(names) or not np.isfinite(data).all()):
        raise ValueError('malformed/nonfinite terminal voltage trace')
    if (not np.equal(data[:, 0::2], data[:, :1]).all()
            or not np.array_equal(data[:, 0], expected_time)):
        raise ValueError('terminal time axis differs from main trace')
    return dict(zip(names, data[:, 1::2].T))


def audit(lines, nodes):
    if not lines or not nodes:
        raise ValueError('missing devices or terminal voltages')
    nodes = {name: np.asarray(value) for name, value in nodes.items()}
    first = next(iter(nodes.values()))
    if (first.ndim != 1 or not len(first)
            or any(v.shape != first.shape or not np.isfinite(v).all() for v in nodes.values())):
        raise ValueError('nonfinite or inconsistent terminal voltage arrays')
    nodes = {**nodes, '0': np.zeros_like(first)}
    rows = []
    seen = set()
    for line in lines:
        fields = line.split()
        if len(fields) != 9 or not fields[0].startswith('X') or fields[0] in seen:
            raise ValueError('malformed or duplicate transistor')
        name, drain, gate, source, bulk, model = fields[:6]
        seen.add(name)
        if model not in BOUNDS or any(n not in nodes for n in (drain, gate, source, bulk)):
            raise ValueError('unknown model or missing terminal voltage')
        row = {'instance': name, 'model': model}
        for quantity, node in (('vds', drain), ('vgs', gate), ('vbs', bulk)):
            wave = nodes[node] - nodes[source]
            lo, hi = BOUNDS[model][quantity]
            row[quantity] = {'min_v': float(wave.min()), 'max_v': float(wave.max()),
                             'documented_min_v': lo, 'documented_max_v': hi,
                             'below_samples': int(np.sum(wave < lo)),
                             'above_samples': int(np.sum(wave > hi))}
        rows.append(row)
    excursions = sum(row[q]['below_samples'] + row[q]['above_samples']
                     for row in rows for q in ('vds', 'vgs', 'vbs'))
    magnitude = max(abs(row[q][bound]) for row in rows for q in ('vds', 'vgs')
                    for bound in ('min_v', 'max_v'))
    return {'documented_ranges_ok': excursions == 0,
            'out_of_range_device_quantity_samples': excursions,
            'max_abs_vds_vgs_v': magnitude, 'devices': rows,
            'reliability_verified': False,
            'scope': 'signed drawn-terminal model-domain check, not absolute-maximum or lifetime signoff'}
