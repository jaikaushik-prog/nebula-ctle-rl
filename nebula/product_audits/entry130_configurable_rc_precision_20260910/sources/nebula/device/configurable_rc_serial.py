"""Entry 129 serial DC controls on one unchanged Entry 128 physical circuit."""
import re

import numpy as np

from nebula.device import configurable_rc as R

FIXED_INDEX=len(R.biases())


def layout(geometry):
    return [x for x in R.op_layout(geometry) if x[0] in (0,FIXED_INDEX)]


def deck(geometry):
    if geometry not in R.GEOMETRIES: raise ValueError('unregistered serial geometry')
    prefix=R.screen_deck(geometry).split('.control')[0]
    lines=[]
    for line in prefix.splitlines():
        name=line.split()[0] if line.strip() else ''
        match=re.fullmatch(r'(?:Xcase|Vsupply|Vcm|Vid|Einp|Einn|Vr|Vc)(\d+)',name)
        if match and int(match[1]) not in (0,FIXED_INDEX): continue
        lines.append(line)
    lines+=['.control','set noaskquit','set numdgt=15','set wr_singlescale']
    op_vectors=' '.join(x[2] for x in layout(geometry))
    ac_vectors=' '.join(f'v({n}{i})' for i in (0,FIXED_INDEX) for n in ('outp','outn','vid'))
    for step,(r,c) in enumerate(R.biases()):
        lines += [f'alter Vr0 {1.8*r:.16g}',f'alter Vc0 {1.8*c:.16g}',
                  'op',f'wrdata op_{step:03d}.txt {op_vectors}',
                  'ac dec 50 1meg 100g',f'wrdata ac_{step:03d}.txt {ac_vectors}']
    lines+=['quit','.endc','.end']
    return '\n'.join(lines)+'\n'


def assemble_op(tables,geometry):
    labels=layout(geometry); n=sum(x[0]==0 for x in labels)
    if len(tables)!=len(R.biases()): raise ValueError('missing serial DC step')
    checked=[]
    for table in tables:
        a=np.atleast_2d(np.asarray(table,dtype=float))
        if a.shape!=(1,1+len(labels)) or not np.isfinite(a).all():
            raise ValueError('malformed/nonfinite serial DC step')
        checked.append(a[0])
    baseline=checked[0][1+n:]
    if not all(np.allclose(x[1+n:],baseline,rtol=0,atol=1e-9) for x in checked):
        raise ValueError('fixed baseline DC changed across serial controls')
    # Every candidate segment comes from its own saved, measured OP record.
    return np.concatenate(([checked[0][0]],*(x[1:1+n] for x in checked),baseline))[None,:]
