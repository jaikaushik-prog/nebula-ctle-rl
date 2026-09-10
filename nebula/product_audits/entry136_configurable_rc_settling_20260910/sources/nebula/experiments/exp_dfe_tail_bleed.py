"""Entry 125 bounded DAC discharge-path recovery; all failures are retained."""
import argparse
import json
from pathlib import Path
import shutil
import time

from nebula.common.types import Corner, all_corners
from nebula.device import dfe_connected as F, dfe_hardware as D
from nebula.device import dfe_tail_bleed as B, dfe_timing as T, dfe_voltage_audit as V
from nebula.experiments import exp_dfe_connected as E, evidence_archive as A
from nebula.experiments import exp_physical_bias as P
from nebula.experiments.exp_dfe_slicer import ROOT
from nebula.experiments.runlock import hold, stamp
from nebula.link.config import LinkConfig

PRIOR=ROOT/'nebula/product_audits/entry124_dfe_connected_20260909'
EXTRA_PATHS=('nebula/DFE_TAIL_BLEED_PLAN.md','nebula/DFE_TIMING_PLAN.md',
    'nebula/device/dfe_tail_bleed.py','nebula/device/dfe_timing.py',
    'nebula/experiments/exp_dfe_tail_bleed.py','nebula/experiments/exp_dfe_timing.py',
    'nebula/experiments/evidence_archive.py','nebula/experiments/archive_traces.py',
    'nebula/tests/test_dfe_tail_bleed.py','nebula/tests/test_dfe_timing.py',
    'nebula/tests/test_evidence_archive.py')


def accepted(r):
    return E.accepted(r) and r.get('aperture',{}).get('passes_0p4ui',False)


def schedule(evaluate):
    corners=(Corner('tt',1,27),Corner('fs',.95,125),Corner('ss',.95,125),Corner('ff',1.05,0))
    screens=[{'length_um':length,'corner':str(c),
        'result':evaluate(length,c,7.5,1.,2,1,'screen')}
        for length in B.LENGTHS_UM for c in corners]
    result={'entry':125,'screens':screens,'controls':[],'selected_length_um':None,
            'pvt':[],'primary_channel_pvt_pass':False,'full_receiver_verified':False,
            'code_zero_is_feedback_disabled':False}
    good=[]
    for length in B.LENGTHS_UM:
        rows=[r for r in screens if r['length_um']==length]
        if not all(accepted(r['result']) for r in rows): continue
        controls=[{'length_um':length,'code':code,'sign':sign,
            'result':evaluate(length,corners[0],7.5,1.,code,sign,'control')}
            for code,sign in ((0,1),(2,-1))]
        result['controls'].extend(controls)
        eye=rows[0]['result']['sampled_eye_height_v']
        if all(E.valid(c['result']) and eye-c['result']['sampled_eye_height_v']>1e-6 for c in controls):
            good.append(length)
    if not good: return result
    length=max(good)
    result['selected_length_um']=length
    result['pvt']=[{'corner':str(c),'result':evaluate(length,c,7.5,1.,2,1,'pvt')}
                   for c in all_corners()]
    result['primary_channel_pvt_pass']=all(accepted(r['result']) for r in result['pvt'])
    return result


class Trial:
    """Shared exact hardware/measurement runner for the two registered stages."""
    def __init__(self,out,entry,budget,prior):
        self.proof=A.verify(prior)
        self.prior_summary=json.loads((prior/'summary.json').read_text())
        # Scientific dependencies must still match the measured prerequisite.
        manifest=json.loads((prior/'evidence_sha256.json').read_text())
        for key,sha in manifest.items():
            if key.startswith('sources/'):
                rel=key[len('sources/'):]
                critical=rel.startswith(('nebula/device/','nebula/common/','nebula/link/'))
                critical |= rel in ('nebula/experiments/exp_physical_bias.py',
                                    'nebula/experiments/exp_dfe_slicer.py')
                if critical and A.digest(ROOT/rel)!=sha:
                    raise ValueError(f'prerequisite scientific source changed: {rel}')
        self.out=Path(out).resolve()
        self.out.mkdir(parents=True,exist_ok=False)
        for path in (prior/'sources').rglob('*'):
            if path.is_file():
                dest=self.out/'sources'/path.relative_to(prior/'sources')
                dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(path,dest)
        for rel in EXTRA_PATHS:
            dest=self.out/'sources'/rel
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/rel,dest)
        shutil.copyfile(prior/'source_ctle.cir',self.out/'source_ctle.cir')
        cfg=LinkConfig(channel_loss_db_at_nyquist=7.5)
        self.bits=F.pattern(cfg)
        self.budget=budget
        self.attempts=self.spice_calls=0
        self.started=time.perf_counter()
        P.write_json(self.out/'config.json',{'entry':entry,'max_calls':budget,
            'bits':self.bits.tolist(),'seed':cfg.seed,'prior':str(prior.relative_to(ROOT)),
            'prior_manifest_sha256':self.proof['manifest_sha256'],
            'prior_summary_sha256':A.digest(prior/'summary.json'),
            'geometry_candidates':{str(length):B.geometry(length) for length in B.LENGTHS_UM},
            'external_clock_control_common_mode':True,**stamp()})

    def evaluate(self,length,corner,loss,phase,code,sign,stage):
        self.attempts+=1
        if self.attempts>self.budget:
            raise RuntimeError('registered case budget exceeded')
        folder=self.out/f'{stage}_{corner}_loss{loss:g}_phase{phase:g}_code{code}_sign{sign}_bleedL{length:g}'
        try:
            cfg=LinkConfig(channel_loss_db_at_nyquist=loss)
            text=B.deck(length,corner,cfg,self.bits,phase,code,sign)
            self.spice_calls+=1
            P.invoke(text,folder)
            t,y=T.read_table(folder/'trace.txt',len(F.VECTORS))
            r=F.analyze(t,y,self.bits,cfg,phase,1.8*corner.vdd_scale,code=code)
            mos=F.all_mos(text)
            names=D.terminal_nodes(mos)
            _,ny=T.read_table(folder/'terminals.txt',len(names),expected_time=t)
            nodes=dict(zip(names,ny.T))
            whole=V.audit(mos,nodes)
            new=V.audit(F.extra_mos(sign)+B.bleeders(length),nodes)
            r.update(instrument_ok=True,new_dfe_voltage_audit=new,
                whole_circuit_voltage_audit=whole,whole_circuit_voltage_envelope_pass=E.envelope(whole),
                aperture=T.aperture(t,y[:,3]-y[:,4],self.bits,phase))
        except Exception as exc:
            folder.mkdir(parents=True,exist_ok=True)
            r={'instrument_ok':False,'logic_pass':False,'fail_reason':f'{type(exc).__name__}: {exc}',
               'full_receiver_verified':False}
        r.update(length_um=length,corner=str(corner),loss_db=loss,phase_ui=phase,code=code,sign=sign)
        r['signal_gate_pass']=accepted(r)
        P.write_json(folder/'result.json',r)
        print(f'{self.attempts}/{self.budget} {folder.name}: pass={accepted(r)} '
              f'bits={r.get("correct_bits")}/64 eye={r.get("sampled_eye_height_v")} '
              f'error={r.get("fail_reason")}',flush=True)
        return r

    def finish(self,result):
        result.update(spice_calls=self.spice_calls,attempted_cases=self.attempts,
            wall_seconds=time.perf_counter()-self.started,
            prior_manifest_sha256=self.proof['manifest_sha256'])
        P.write_json(self.out/'summary.json',result)
        P.write_json(self.out/'evidence_sha256.json',{
            p.relative_to(self.out).as_posix():A.digest(p)
            for p in sorted(self.out.rglob('*')) if p.is_file()})
        return result


def run(out):
    old=json.loads((PRIOR/'summary.json').read_text())
    if (old['entry']!=124 or old['selected']!={'phase_ui':1.,'code':2,'sign':1}
            or len(old['pvt'])!=45 or not all(r['result']['logic_pass'] for r in old['pvt'])):
        raise ValueError('connected recovery prerequisite differs')
    with hold('dfe_slicer'):
        trial=Trial(out,125,57,PRIOR)
        return trial.finish(schedule(trial.evaluate))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True,type=Path)
    raise SystemExit(0 if run(parser.parse_args().out)['primary_channel_pvt_pass'] else 1)
