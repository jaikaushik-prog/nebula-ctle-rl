"""Entry160 bounded integration; all calls charged, no historical overwrite."""
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil
import time
from nebula import programmable_receiver as P
from nebula.device import loaded_tuning_bound as B
from nebula.device.ngspice_runner import ngspice_path
from nebula.experiments import spice_capture as C
from nebula.experiments.exp_varactor_probe import pdk_hashes
from nebula.experiments.runlock import hold,stamp

ROOT=B.ROOT
RUN=ROOT/'nebula/product_demo/submission_runs_20260915_v2/4608cf1c525f4e59b2d5226059b0ce5d'
OUT=ROOT/'nebula/product_audits/entry160_programmable_receiver_20260915'
DEADLINE=datetime(2026,9,15,14,4,35,tzinfo=timezone.utc)
SOURCES=('nebula/PROGRAMMABLE_RECEIVER_INTEGRATION_PLAN_20260915.md','nebula/programmable_receiver.py',
 'nebula/generated_receiver.py','nebula/experiments/exp_programmable_receiver.py','nebula/tests/test_programmable_receiver.py',
 'nebula/device/loaded_tuning_bound.py')
def write(path,value):Path(path).write_text(json.dumps(value,indent=2,allow_nan=False),encoding='utf-8')
def remaining():return (DEADLINE-datetime.now(timezone.utc)).total_seconds()

def run():
    if OUT.exists():raise ValueError('output exists; no overwrite or automatic retry')
    if remaining()<240:raise ValueError('insufficient measurement time')
    if (Path(__file__).parent/'.dfe_slicer.runlock.json').exists():raise ValueError('existing simulator lock; not modified')
    with hold('dfe_slicer'):
        OUT.mkdir(parents=True,exist_ok=False);start=time.perf_counter();calls=[];states=[]
        summary=dict(entry=160,parent_setting=352,parent_unchanged=False,full_receiver_verified=False,nominal_receiver_verified=False,
                     status='EXPERIMENTAL_UNVERIFIED',states=states,calls=calls)
        sources={};models={}
        try:
            design=json.loads((RUN/'design.json').read_text());source=(RUN/'design.cir').read_bytes().decode('ascii')
            P.G._accepted(design);P.G._selected_deck(design,source)
            parent={p.name:B.sha(p) for p in RUN.iterdir() if p.is_file()}
            old=json.loads(B.original_file(B.LOADED,'config.json').read_text())
            for name,digest in old['source_sha256'].items():B.checked_file(ROOT,name,digest)
            models=pdk_hashes()
            if models!=old['external_pdk_include_closure_sha256']:raise ValueError('PDK closure changed')
            if B.sha(ngspice_path())!=old['ngspice_sha256']:raise ValueError('simulator changed')
            sources={name:B.sha(ROOT/name) for name in (*old['source_sha256'],*SOURCES)}
            for name in sources:
                dst=OUT/'sources'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dst)
            controls=[tuple(x) for x in B.proposals()['controls']]
            if (.73,.195) not in controls:controls.insert(-1,(.73,.195))
            # Previous calibrated .7/.185 endpoint is retained as a repeatability pair,
            # but is not asserted equivalent to the different selected receiver.
            config=dict(entry=160,measurement_deadline_utc=DEADLINE.isoformat(),timeout_s=180,controls=controls,
                        target=[6.,2.1e9],source_sha256=sources,parent_files_sha256=parent,
                        external_pdk_include_closure_sha256=models,ngspice_sha256=B.sha(ngspice_path()),**stamp())
            write(OUT/'config.json',config)
            def invoke(name,deck,extract):
                if remaining()<210:raise ValueError('measurement deadline reached; reserve closeout time')
                if any(B.sha(ROOT/n)!=h for n,h in sources.items()):raise ValueError('frozen source changed before call')
                folder=OUT/name;call=dict(index=len(calls)+1,case=name,started_utc=datetime.now(timezone.utc).isoformat(),instrument_ok=False)
                calls.append(call);write(OUT/'progress.json',calls);begin=time.perf_counter()
                print(f'Call {len(calls)}: {name}, timeout 180 s',flush=True)
                try:
                    C.invoke(deck,folder,timeout_s=180);row=extract(folder)
                    call['instrument_ok']=bool(row.get('instrument_ok'))
                except Exception as exc:
                    folder.mkdir(parents=True,exist_ok=True)
                    row=dict(instrument_ok=False,full_receiver_verified=False,fail_reason=f'{type(exc).__name__}: {exc}')
                call.update(wall_seconds=time.perf_counter()-begin,fail_reason=row.get('fail_reason'))
                write(folder/'result.json',row);write(OUT/'progress.json',calls)
                print(f'{name}: instrument_ok={row.get("instrument_ok")}; {row.get("fail_reason", "complete")}',flush=True)
                return row
            for state in (0,1):
                row=invoke(f'held_state{state}',P.static_batch(design,source,state,controls),lambda folder,s=state:P.extract_static(folder,s,controls))
                states.append(row)
                if not row.get('instrument_ok'):break
            choice=P.select_control(states,6.,2.1e9);summary['selected_control']=choice
            if choice['nominal_ac_match']:
                control=(choice['r_fraction'],choice['c_fraction'])
                summary['export']=P.export(design,source,OUT/'export',*control)
                summary['link']=invoke('nominal_link',P.build_deck(design,source,*control),lambda folder:P.extract_link(folder,control))
                link=summary['link']
                summary['nominal_receiver_verified']=bool(choice['signed_model_domain_pass'] and link.get('nominal_receiver_verified'))
                summary['status']='NOMINAL_VERIFIED_PVT_UNTESTED' if summary['nominal_receiver_verified'] else 'MEASURED_EXPERIMENTAL_NOT_SIGNED_OFF'
            else:
                summary['export']=P.export(design,source,OUT/'export',.73,.195)
                summary['status']='NO_MATCH_IN_BOUNDED_SAMPLE'
            summary.update(parent_unchanged=all(B.sha(RUN/n)==h for n,h in parent.items()),
                           sources_unchanged=all(B.sha(ROOT/n)==h for n,h in sources.items()),pdk_unchanged=pdk_hashes()==models,
                           simulator_unchanged=B.sha(ngspice_path())==old['ngspice_sha256'])
            if not all(summary[k] for k in ('parent_unchanged','sources_unchanged','pdk_unchanged','simulator_unchanged')):
                raise ValueError('final provenance check failed')
        except Exception as exc:
            summary.update(fail_reason=f'{type(exc).__name__}: {exc}',nominal_receiver_verified=False,status='INCOMPLETE_OR_INVALID')
        summary.update(charged_calls=len(calls),wall_seconds=time.perf_counter()-start,completed_utc=datetime.now(timezone.utc).isoformat())
        write(OUT/'summary.json',summary)
        write(OUT/'evidence_sha256.json',{p.relative_to(OUT).as_posix():B.sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='evidence_sha256.json'})
        print(json.dumps({k:v for k,v in summary.items() if k not in ('states','link','calls')},indent=2),flush=True)
        return summary

if __name__=='__main__':run()
