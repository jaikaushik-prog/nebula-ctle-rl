"use strict";
// Saved, parent-bound experimental option. Never changes selected-run acceptance.
const NebulaProgrammable = (() => {
  let revision=0;
  const el=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
  async function render(design) {
    const token=++revision,panel=document.querySelector('#programmableReceiverOption');
    panel.hidden=true;panel.replaceChildren();
    try {
      const response=await fetch(`/api/submission/programmable/${encodeURIComponent(design.id)}`,{cache:'no-store'});
      if(!response.ok){
        let detail='';try{const failure=await response.json();detail=String(failure.error||failure.message||'').slice(0,240);}catch(_){}
        throw new Error(`Saved programmable evidence could not be loaded (HTTP ${response.status}${detail?': '+detail:''})`);
      }
      const payload=await response.json();if(token!==revision)return;
      const d=payload.programmable;if(!d)return;
      if(!d.read_only || d.full_receiver_verified || d.nominal_receiver_verified)throw new Error('Unexpected experimental evidence scope');
      const details=el('details');details.className='details-card';
      details.append(el('summary','Programmable receiver option — experimental'));
      details.append(el('h3','Physical Rs/Cs controls in a receiver derived from setting 352'));
      details.append(el('p','This new circuit retains the selected amplifier, attenuator, bias and transistor DFE, and replaces fixed Rs/Cs with a controlled resistor branch and SKY130 varactors. The accepted fixed-CTLE result above is unchanged.'));
      const values=d.response;
      details.append(el('p',`Measured controls: Rs ${d.control_voltage_v[0].toFixed(3)} V and Cs ${d.control_voltage_v[1].toFixed(3)} V. Both held states give ${Math.min(...values.map(x=>x.boost_db)).toFixed(3)}–${Math.max(...values.map(x=>x.boost_db)).toFixed(3)} dB near ${(Math.min(...values.map(x=>x.peak_frequency_hz))/1e9).toFixed(3)}–${(Math.max(...values.map(x=>x.peak_frequency_hz))/1e9).toFixed(3)} GHz. This meets the 6 dB / 2.1 GHz request within the existing internal ±0.5 dB / ±100 MHz tolerance.`));
      details.append(el('p',`Nominal transistor link: ${d.correct_bits}/${d.scored_bits} decisions, ${d.eye_height_mv.toFixed(3)} mV sampled eye, ${d.positive_aperture_ui.toFixed(3)} UI positive aperture (scan-limited), ${d.aperture_above_100mv_ui.toFixed(3)} UI above 100 mV and ${d.power_mw.toFixed(4)} mW VDD draw.`));
      const limits=el('p',`${d.model_violations.length} devices violate signed model-domain limits. Noise instrumentation was rejected; HD3 and PVT are unverified. Controls were selected by measured calibration, not RL. No live tuning, BER or full receiver signoff is claimed.`);limits.className='programmable-limits';details.append(limits);
      const image=el('img');image.src='/api/submission/programmable-artifact/response-eye';image.alt='Measured loaded response at three physical Cs controls and the chosen programmable receiver transistor eye';image.loading='eager';details.append(image);
      const table=el('table'),head=el('thead'),tr=el('tr');
      for(const title of ['Recorded Cs control','Peaking across held states','Peak frequency across held states'])tr.append(el('th',title));head.append(tr);table.append(head);
      const body=el('tbody');for(const p of d.control_points){const row=el('tr');row.append(el('td',`${(1.8*p.c_fraction).toFixed(3)} V${p.c_fraction===d.c_fraction?' — chosen':''}`));row.append(el('td',p.states.map(s=>s.boost_db.toFixed(3)).join(' / ')+' dB'));row.append(el('td',p.states.map(s=>(s.peak_frequency_hz/1e9).toFixed(3)).join(' / ')+' GHz'));body.append(row);}table.append(body);details.append(table);
      details.append(el('p','Recorded measurements at fixed external controls, not a runtime retuning demonstration. TT / 1.8 V / 27°C; constructed 7.5 dB channel; external clock phase 1 UI and tap code 2.'));
      const links=el('div');links.className='evidence-links';
      const names={deck:'Download exact measured programmable deck',drawing:'Open exact device drawing','response-eye':'Open measured plots',review:'Review and retained failures','link-result':'Nominal transistor measurements',config:'Control selection record',waveform:'Recorded waveform',terminals:'Recorded terminal voltages'};
      for(const a of d.artifact_links){const link=el('a',names[a.key]||a.key);link.href=a.url;link.target='_blank';link.rel='noopener';if(a.key==='deck')link.download='Nebula_programmable_receiver.cir';links.append(link);}details.append(links);
      details.append(el('p',`Eight recorded simulator calls include the failed attempts. ${d.verified_archived_files} archived files were checked in the independent raw-data recomputation. Matching future 6 dB / 2.1 GHz exports include this saved measured option separately; they do not launch fresh verification of it.`));
      panel.append(details);panel.hidden=false;
    } catch(error) {if(token===revision){
      const message=el('p',`${error.message}. The selected CTLE is unchanged.`);
      const retry=el('button','Reload saved evidence');retry.type='button';retry.addEventListener('click',()=>render(design));
      const note=el('p','This reload reads saved files only and does not start a simulation. If it still fails, copy the HTTP error above and check that this page is using the current recovery server at port 8766.');
      panel.replaceChildren(message,retry,note);panel.hidden=false;
    }}
  }
  return {render};
})();
