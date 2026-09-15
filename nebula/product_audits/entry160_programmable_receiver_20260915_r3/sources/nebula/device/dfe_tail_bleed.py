"""Entry 125: physical weak discharge paths on inactive DAC tail nodes."""
from nebula.device import dfe_connected as F, dfe_hardware as D, dfe_timing as T

LENGTHS_UM=(4.,2.)


def bleeders(length):
    if length not in LENGTHS_UM:
        raise ValueError('unregistered bleeder geometry')
    return [f'Xdfe_bleed{k} fd_tail{k} df_nbias 0 0 {D.NFET} w=0.42 l={length:g} nf=1'
            for k in range(4)]


def deck(length,corner,cfg,bits,phase,code,sign):
    added=bleeders(length)
    text=T.deck(corner,cfg,bits,phase,code,sign)
    if text.count('.control')!=1:
        raise ValueError('ambiguous connected control block')
    # No new electrical nodes: the existing full-terminal wrdata list suffices.
    return text.replace('.control', '* Entry 125 physical off-branch bleeders\n'
                        +'\n'.join(added)+'\n.control',1)


def geometry(length):
    bleeders(length)
    result=F.geometry()
    area=4*.42*length
    result.update(added_bleeder_gate_um2=area,added_bleeder_count=4,
        added_mos_count=result['added_mos_count']+4,
        added_mos_gate_um2=result['added_mos_gate_um2']+area,
        geometry_subtotal_mm2=result['geometry_subtotal_mm2']+area*1e-6,
        code_zero_is_feedback_disabled=False,
        code_zero_scope='minimum current code; weak bleeders create residual feedback')
    return result
