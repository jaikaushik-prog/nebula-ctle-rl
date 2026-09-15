"""Entry 130: tighter numerical convergence, unchanged serial physical circuit."""
from nebula.device import configurable_rc_serial as S

OPTIONS='.options reltol=1e-9 vntol=1e-12 abstol=1e-15'


def deck(geometry):
    original=S.deck(geometry)
    if '\n.options ' in original.lower():
        raise ValueError('unexpected pre-existing solver options')
    return original.replace('\n.control\n','\n'+OPTIONS+'\n.control\n',1)
