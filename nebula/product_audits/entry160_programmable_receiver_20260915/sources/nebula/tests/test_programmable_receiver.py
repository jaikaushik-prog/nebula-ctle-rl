import json
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]
RUN=ROOT/'nebula/product_demo/submission_runs_20260915_v2/4608cf1c525f4e59b2d5226059b0ce5d'
def inputs():
    return json.loads((RUN/'design.json').read_text()),(RUN/'design.cir').read_bytes().decode('ascii')

def test_selected_receiver_replaces_only_fixed_tuning_elements():
    from nebula import programmable_receiver as P
    design,source=inputs();deck=P.build_deck(design,source,.73,.195)
    assert '\nXrs ' not in deck and '\nXcs ' not in deck
    assert 'Xrc_switch ' in deck and 'Xrc_var_s1 ' in deck and 'Xrc_var_s2 ' in deck
    assert 'VrcR rctrl 0 1.314' in deck and 'VrcC cctrl 0 0.351' in deck
    assert 'Xdfe_sump' in deck and 'Xdf_mtrack' in deck
    for line in source.replace('\r\n','\n').split('.control')[0].splitlines():
        if line.startswith(('XM','Xatt','Xrl','Xbp','Xrbias','Xcbyp')):assert line in deck
    assert deck.count('.lib ')==deck.count('.control')==1

def test_invalid_controls_and_source_are_refused():
    from nebula import programmable_receiver as P
    design,source=inputs()
    for controls in [(float('nan'),.195),(.73,2),(.731,.195)]:
        with pytest.raises(ValueError):P.build_deck(design,source,*controls)
    with pytest.raises(ValueError,match='hash'):P.build_deck(design,source+'\n',.73,.195)

def test_export_does_not_inherit_any_verified_status(tmp_path):
    from nebula import programmable_receiver as P
    design,source=inputs();result=P.export(design,source,tmp_path/'variant',.73,.195)
    assert result['structurally_integrated']
    assert result['status']=='EXPERIMENTAL_UNVERIFIED'
    assert not result['nominal_receiver_verified'] and not result['full_receiver_verified']
    assert result['derived_from_setting']==352 and result['inherits_parent_verification'] is False
    assert (tmp_path/'variant/receiver.cir').exists()
    with pytest.raises(FileExistsError):P.export(design,source,tmp_path/'variant',.73,.195)

def test_static_batch_holds_clock_and_records_controls():
    from nebula import programmable_receiver as P
    design,source=inputs();deck=P.static_batch(design,source,0,[(.73,.195),(.73,.195)])
    assert 'Vdfclk df_clk 0 0.6' in deck
    assert '.nodeset ' in deck and '.ic ' not in deck
    assert 'Vid vid 0 DC 0 AC 1' in deck and 'PWL(' not in deck
    assert 'wrdata op_001.txt' in deck and 'alter VrcR 1.314' in deck

def test_selection_never_converts_signed_failure_to_signoff():
    from nebula import programmable_receiver as P
    row=dict(instrument_ok=True,r_fraction=.73,c_fraction=.195,boost_db=6.,peak_frequency_hz=2.1e9,ac_model_pass=True,signed_model_domain_pass=False)
    chosen=P.select_control([dict(clock_state=0,instrument_ok=True,rows=[row]),dict(clock_state=1,instrument_ok=True,rows=[row])],6.,2.1e9)
    assert chosen['nominal_ac_match'] and not chosen['signed_model_domain_pass']
    assert not chosen['nominal_receiver_verified'] and not chosen['full_receiver_verified']
    assert not P.select_control([],6.,2.1e9)['nominal_ac_match']

def test_selection_requires_both_states_and_matching_control_order():
    from nebula import programmable_receiver as P
    row=dict(instrument_ok=True,r_fraction=.73,c_fraction=.195,boost_db=6.,peak_frequency_hz=2.1e9,ac_model_pass=True,signed_model_domain_pass=True)
    bad={**row,'peak_frequency_hz':1.5e9}
    assert not P.select_control([dict(clock_state=0,instrument_ok=True,rows=[row]),dict(clock_state=1,instrument_ok=True,rows=[bad])],6.,2.1e9)['nominal_ac_match']
    with pytest.raises(ValueError):P.select_control([dict(clock_state=0,instrument_ok=True,rows=[row]),dict(clock_state=1,instrument_ok=True,rows=[{**row,'r_fraction':.74}])],6.,2.1e9)
