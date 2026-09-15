"""Entry 135: G164-compliant AC sampling, unchanged physical runtime DUT."""
import numpy as np

from nebula.device import configurable_rc_runtime as U


def deck(kind,index):
    text=U.deck(kind,index)
    if kind=='runtime': return text
    old='ac lin 2 100meg 1.9g'
    if text.count(old)!=1: raise ValueError('unexpected frozen AC command membership')
    return text.replace(old,'ac lin 3 100meg 1.9g',1)


def tone_reference(raw):
    a=np.asarray(raw)
    if (a.shape!=(3,7) or not np.isfinite(a).all()
            or not np.allclose(a[:,0],[1e8,1e9,1.9e9],rtol=1e-12,atol=1e-3)):
        raise ValueError('malformed three-point AC primitives')
    inp=a[:,5]+1j*a[:,6]
    if not np.allclose(inp,1.,rtol=0,atol=1e-12): raise ValueError('incorrect three-point AC input')
    return U.tone_reference(a[[0,2]])
