"""Entry 138: released measured-state initial guesses; unchanged transistor DUT."""
import numpy as np
from nebula.device import dfe_loaded_analog as L

SEED_NODES=('df_q','df_qb','df_mp','df_mn')


def seed_values(reference,sign):
    if sign not in (-1,1): raise ValueError('unregistered initial polarity')
    try: values={n:float(reference['dc_nodes_v'][n]) for n in SEED_NODES}
    except (KeyError,TypeError,ValueError) as exc: raise ValueError('missing measured seed primitives') from exc
    if (not all(np.isfinite(v) and 0<v<1.95 for v in values.values())
            or values['df_q']-values['df_qb']>=-.1):
        raise ValueError('expected resolved negative measured latch reference')
    if sign==1:
        for a,b in [('df_q','df_qb'),('df_mp','df_mn')]: values[a],values[b]=values[b],values[a]
    return values


def deck(kind,state,step,sign,reference):
    text=L.deck(L.PRIMARY,kind,state,step)
    values=seed_values(reference,sign)
    if '.nodeset ' in text.lower() or '.ic ' in text.lower():
        raise ValueError('unexpected existing initial condition')
    line='.nodeset '+' '.join(f'v({n})={values[n]:.16g}' for n in SEED_NODES)
    return text.replace('.control',line+'\n.control',1)


def calibration_matches(result,reference,h,reference_h):
    a,b=np.asarray(h),np.asarray(reference_h)
    if a.shape!=(251,) or b.shape!=(251,) or not np.isfinite(a).all() or not np.isfinite(b).all() or np.any(abs(b)<1e-9):
        return False
    old=reference['dc_nodes_v'];new=result['dc_nodes_v']
    return bool(set(old)==set(new) and all(np.isfinite(new[n]) and abs(new[n]-old[n])<=1e-6 for n in old)
        and np.max(abs(a/b-1))<=1e-4
        and abs(result['noise']['input_noise_vrms']/reference['noise']['input_noise_vrms']-1)<=.001
        and abs(result['vdd_power_w']-reference['vdd_power_w'])<=1e-7)


def valid(r): return bool(r.get('instrument_ok',False) and r.get('initialization_valid',False))


def schedule(evaluate):
    r={'entry':138,'static':[],'tones':[],'measurement_complete':False,'primary_analog_model_pass':False,
       'primary_target_match':False,'full_receiver_verified':False,'clocked_receiver_noise_verified':False,
       'nine_target_map_verified':False,'nodeset_is_released_initial_guess':True}
    def static(state,sign):
        row=evaluate('static',state,L.STEPS[0],sign)
        r['static'].append({'clock_state':state,'initial_polarity':sign,'result':row})
        return row
    first=static(1,-1)
    if not valid(first) or not first.get('calibration_matches',False): return r
    for state,sign in [(1,1),(0,-1),(0,1)]: static(state,sign)
    if not all(valid(x['result']) for x in r['static']): return r
    r['tones']=[evaluate('tone',0,step,-1) for step in L.STEPS]
    r['measurement_complete']=all(valid(x) for x in r['tones'])
    r['resolution_agreement']=L.resolution_matches(*r['tones'])
    r['primary_target_match']=all(x['result'].get('target_match',False) for x in r['static'])
    r['primary_analog_model_pass']=bool(r['measurement_complete'] and r['resolution_agreement']
        and all(x['result'].get('small_signal_specs_pass',False) for x in r['static'])
        and all(x.get('hd3_model_pass',False) for x in r['tones']))
    return r
