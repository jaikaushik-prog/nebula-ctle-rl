"""Entry 126 channel retiming, conditional on verified Entry 125 recovery."""
import argparse
import json
from pathlib import Path

from nebula.common.types import Corner, all_corners
from nebula.experiments import exp_dfe_connected as E, exp_dfe_tail_bleed as B
from nebula.experiments.exp_dfe_slicer import ROOT
from nebula.experiments.runlock import hold

PRIOR=ROOT/'nebula/product_audits/entry125_dfe_tail_bleed_20260909'


def schedule(evaluate):
    tt=Corner('tt',1,27)
    screens=[{'phase_ui':phase,'result':evaluate(tt,12.,phase,2,1,'phase')}
             for phase in (1.25,1.5,1.75)]
    result={'entry':126,'screens':screens,'controls':[],'selected_phase_ui':None,
            'pvt':[],'new_channel_pvt_pass':False,'full_receiver_verified':False,
            'code_zero_is_feedback_disabled':False}
    good=[r for r in screens if B.accepted(r['result'])]
    if not good: return result
    best=max(good,key=lambda r:(r['result']['sampled_eye_height_v'],-r['phase_ui']))
    phase=best['phase_ui']
    controls=[{'code':code,'sign':sign,'result':evaluate(tt,12.,phase,code,sign,'control')}
              for code,sign in ((0,1),(2,-1))]
    result['controls']=controls
    eye=best['result']['sampled_eye_height_v']
    if not all(E.valid(r['result']) and eye-r['result']['sampled_eye_height_v']>1e-6 for r in controls):
        return result
    result['selected_phase_ui']=phase
    result['pvt']=[{'loss_db':loss,'corner':str(c),
        'result':evaluate(c,loss,1. if loss==3 else phase,2,1,'pvt')}
        for loss in (3.,12.) for c in all_corners()]
    result['new_channel_pvt_pass']=all(B.accepted(r['result']) for r in result['pvt'])
    return result


def run(out):
    old=json.loads((PRIOR/'summary.json').read_text())
    if (old['entry']!=125 or not old['primary_channel_pvt_pass'] or len(old['pvt'])!=45
            or old['selected_length_um'] not in (2.,4.)
            or not all(B.accepted(r['result']) for r in old['pvt'])):
        raise ValueError('Entry 125 fixed-geometry 45-PVT prerequisite has not passed')
    with hold('dfe_slicer'):
        trial=B.Trial(out,126,95,PRIOR)
        length=old['selected_length_um']
        result=schedule(lambda c,loss,phase,code,sign,stage:
                        trial.evaluate(length,c,loss,phase,code,sign,stage))
        result.update(selected_bleeder_length_um=length,
                      prior_7p5db_pvt_passes=45,prior_spice_calls=old['spice_calls'],
                      prior_counts_are_not_new_simulations=True)
        return trial.finish(result)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True,type=Path)
    raise SystemExit(0 if run(parser.parse_args().out)['new_channel_pvt_pass'] else 1)
