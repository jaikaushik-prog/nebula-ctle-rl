"use strict";
// Separate diagnostic evidence: never changes a target, circuit or acceptance status.
async function loadEngineeringDiagnostics() {
  const panel=document.querySelector('#engineeringDiagnostics');
  const el=(tag,text)=>{const n=document.createElement(tag);n.textContent=text;return n;};
  try {
    const response=await fetch('/api/submission/diagnostics', {cache:'no-store'});
    if(!response.ok){const body=await response.json().catch(()=>({}));throw Object.assign(new Error(body.error || 'Diagnostic endpoint unavailable'),{status:response.status});}
    const data=await response.json();
    if(!data.read_only || data.simulations_launched!==0)throw new Error('Unexpected diagnostic scope');
    panel.replaceChildren();
    const details=el('details','');details.className='details-card';
    details.append(el('summary','Additional engineering diagnostics: tuning, RL cost and receiver limits'));
    details.append(el('h3','Programmable reference: nominal loaded tuning'));
    details.append(el('p','Independent programmable reference, not setting 352. Two recorded SPICE calls checked 31 OP/AC snapshots in each held-clock state. Five of twelve targets match in both states, using the existing 0.5 dB / 100 MHz request tolerances. No noise, HD3, eye, dynamic retuning or PVT pass is added. End-to-end coverage remains 4/12.'));
    const table=el('table',''),head=el('thead',''),hr=el('tr','');
    for(const title of ['Requested target','Nominal AC result','Control voltages / VDD'])hr.append(el('th',title));
    head.append(hr);table.append(head);const body=el('tbody','');
    for(const t of data.tuning.targets){
      const tr=el('tr','');tr.append(el('td',`${t.target_boost_db} dB / ${(t.target_frequency_hz/1e9).toFixed(2)} GHz`));
      tr.append(el('td',t.nominal_ac_match ? 'Both held states match; not receiver signoff' : 'No match in this bounded sample'));
      tr.append(el('td',t.nominal_ac_match ? `R: ${t.r_fraction.toFixed(3)}; C: ${t.c_fraction.toFixed(3)}` : 'Not selected'));body.append(tr);
    }
    table.append(body);details.append(table);
    const r=data.rl;
    details.append(el('h3','RL contribution: search visits are not design time'));
    details.append(el('p',`Recomputed from ${r.episodes.toLocaleString()} saved seed/identity rows: mean oracle regret ${r.mean_quality_regret.toFixed(4)}; ${(100*r.fraction_within_0p05).toFixed(2)}% within 0.05 of the bank oracle. The ${r.cached_visit_reduction_factor.toFixed(1)}x cached-visit reduction is not an RL SPICE speedup.`));
    details.append(el('p',`Complete workflow comparison: RL ${r.arms.rl.delivered}/12 delivered, ${r.arms.rl.charged_calls} charged calls, ${r.arms.rl.wall_seconds.toFixed(1)} s; classical ${r.arms.classical.delivered}/12, ${r.arms.classical.charged_calls} calls, ${r.arms.classical.wall_seconds.toFixed(1)} s. Eight both-success pairs have median classical/RL time ratio ${r.paired_classical_over_rl_median.toFixed(3)}. No speed or near-optimality advantage is established. One classical failure was infrastructure-related.`));
    details.append(el('h3','Selected receiver: exact remaining electrical gap'));
    details.append(el('p','Six attenuator PMOS devices have signed Vds violations; two also have +0.299 V off-state Vgs. All six measured Vds intervals cross zero, so relabeling source/drain would not close the gap. The nominal 64-bit result is retained; the other 44 selected-receiver link corners remain unverified. Independent-reference PVT is not transferable.'));
    const link=el('a','Download recomputed diagnostic evidence (JSON)');link.href='/api/submission/diagnostics';link.target='_blank';link.rel='noopener';details.append(link);
    panel.append(details);
  } catch(error) {NebulaEvidenceLoading.failure(panel,error,loadEngineeringDiagnostics);}
}
document.addEventListener('DOMContentLoaded',loadEngineeringDiagnostics);
