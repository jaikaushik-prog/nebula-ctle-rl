"""Entry 125: external clock retiming and finite noiseless eye aperture.

The Entry 124 transistor renderer and analyzer remain byte-unchanged.
"""
import re

import numpy as np

from nebula.common.types import UI_SECONDS as UI
from nebula.device import dfe_connected as F, dfe_cml as C

PHASES_UI = (1., 1.25, 1.5, 1.75)


def deck(corner, cfg, bits, phase, code, sign):
    if phase not in PHASES_UI or code not in (0, 2) or sign not in (-1, 1):
        raise ValueError('unregistered timing member')
    text = F.deck(corner, cfg, bits, 1., code, sign)
    vdd = 1.8*corner.vdd_scale
    for name, lo, hi in [('clk',vdd/3,2*vdd/3),('clkb',2*vdd/3,vdd/3)]:
        line = (f'Vdf{name} df_{name} 0 PULSE({lo:.16g} {hi:.16g} '
                f'{F.edge_time(0,phase):.16g} {C.EDGE_S:.16g} {C.EDGE_S:.16g} '
                f'{UI/2-2*C.EDGE_S:.16g} {UI:.16g})')
        text, count = re.subn(rf'^Vdf{name}\s+.*$', lambda _: line, text, flags=re.M)
        if count != 1:
            raise ValueError('expected exactly one external clock source')
    return text.replace('set numdgt=15\n', 'set numdgt=15\nset wr_singlescale\n', 1)


def read_table(path, vector_count, *, expected_time=None):
    a = np.loadtxt(path)
    if (vector_count < 1 or a.ndim != 2 or len(a) < 2
            or a.shape[1] != vector_count+1 or not np.isfinite(a).all()
            or np.any(np.diff(a[:,0]) <= 0)):
        raise ValueError('malformed single-scale table')
    t, y = a[:,0], a[:,1:]
    if expected_time is not None and not np.array_equal(t, expected_time):
        raise ValueError('terminal time axis differs from main trace')
    return t,y


def aperture(t, differential, bits, phase):
    t,v,bits = np.asarray(t),np.asarray(differential),np.asarray(bits)
    if (t.ndim != 1 or len(t) < 100 or v.shape != t.shape
            or not np.isfinite(t).all() or not np.isfinite(v).all()
            or np.any(np.diff(t) <= 0) or np.max(np.diff(t)) > UI/100
            or bits.shape != (F.N_BITS,) or not np.isin(bits,(0,1)).all()
            or phase not in PHASES_UI):
        raise ValueError('invalid aperture data')
    offsets = np.arange(-100,101)*.005
    indices = np.arange(F.WARMUP,F.N_BITS)
    times = (indices[:,None]+2+phase+offsets[None,:])*UI
    if times.min() < t[0] or times.max() > t[-1]:
        raise ValueError('truncated aperture data')
    waves = np.interp(times,t,v)
    positive = bits[indices] == 1
    if not positive.any() or positive.all():
        raise ValueError('missing eye level')
    low = waves[positive].min(axis=0)
    high = waves[~positive].max(axis=0)
    height = low-high
    anchor = int(np.argmin(abs(offsets+.025)))
    def interval(threshold):
        ok = (low>0)&(high<0)&(height>threshold)
        if not ok[anchor]:
            return {'width_ui':0.,'left_ui':None,'right_ui':None,'scan_limited':False}
        left=right=anchor
        while left>0 and ok[left-1]: left-=1
        while right+1<len(ok) and ok[right+1]: right+=1
        return {'width_ui':float(offsets[right]-offsets[left]),
                'left_ui':float(offsets[left]),'right_ui':float(offsets[right]),
                'scan_limited':left==0 or right==len(ok)-1}
    opened, at100 = interval(0.),interval(.1)
    return {'eye_width_ui':opened['width_ui'],
            'eye_width_at_100mv_ui':at100['width_ui'],
            'positive_eye_interval':opened,'height_100mv_interval':at100,
            'passes_0p4ui':opened['width_ui']>.4,
            'grid_step_ui':.005,'sample_anchor_ui':-.025,
            'offsets_ui':offsets.tolist(),'positive_min_v':low.tolist(),
            'negative_max_v':high.tolist(),'ber_verified':False,
            'scope':'finite noiseless waveform aperture at one clock phase, not BER or phase-sweep proof'}
