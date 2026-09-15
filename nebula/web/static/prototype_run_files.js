"use strict";
// Lazy, parent-bound saved evidence. No generation or acceptance changes.
const NebulaRunPrototype = (() => {
  let revision=0;
  const el=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
  function render(design) {
    const token=++revision,panel=document.querySelector('#programmableRunEvidence');
    panel.replaceChildren();panel.hidden=true;
    const accepted=(design.recovery?.attempts||[]).find(a=>a.accepted);
    if(design.method!=='rl-physical' || (accepted?.setting??design.nominal?.setting)!==352)return;
    const details=el('details');details.className='prototype-disclosure';
    const summary=el('summary'),copy=el('span');copy.className='evidence-summary-copy';
    copy.append(el('strong','Programmable receiver prototype'),el('span','Physical Rs/Cs controls with transistor DFE; separate nominal evidence'));
    summary.append(copy);details.append(summary);
    const content=el('div');content.className='receiver-evidence-content';details.append(content);panel.append(details);panel.hidden=false;
    let loaded=false,loading=false;
    async function load() {
      if(loading || token!==revision)return;loading=true;
      content.replaceChildren(el('p','Reading the saved prototype matched to this CTLE...'));
      try {
        const response=await fetch(`/api/submission/programmable/${encodeURIComponent(design.id)}`,{cache:'no-store'});
        if(!response.ok){const body=await response.json().catch(()=>({}));throw Object.assign(new Error(body.error||'Prototype endpoint unavailable'),{status:response.status});}
        const payload=await response.json();if(token!==revision)return;
        const d=payload.programmable;
        if(!d){content.replaceChildren(el('p','No matching saved programmable prototype exists for this circuit. The selected CTLE is unchanged.'));loaded=true;return;}
        if(!payload.read_only || !d.read_only || d.full_receiver_verified!==false || d.nominal_receiver_verified!==false)throw new Error('Unexpected prototype evidence scope');
        content.replaceChildren(el('p','This variant retains the setting-352 amplifier, attenuation, bias and transistor DFE, replacing fixed Rs/Cs with a controlled resistor branch and SKY130 varactors. It is a separate prototype; setting 352 remains the accepted fixed CTLE.'));
        const metrics=el('dl');metrics.className='receiver-measurements';
        for(const [name,value] of [['Decisions',`${d.correct_bits}/${d.scored_bits}`],['Sampled eye',`${d.eye_height_mv.toFixed(3)} mV`],['Width above 100 mV',`${d.aperture_above_100mv_ui.toFixed(3)} UI`],['VDD power',`${d.power_mw.toFixed(4)} mW`]]){const cell=el('div');cell.append(el('dt',name),el('dd',value));metrics.append(cell);}content.append(metrics);
        content.append(el('p',`Saved TT / 1.8 V / 27 C, constructed 7.5 dB channel, external clock and fixed tap. Rs control: ${d.control_voltage_v[0].toFixed(3)} V; Cs control: ${d.control_voltage_v[1].toFixed(3)} V. Positive aperture: ${d.positive_aperture_ui.toFixed(3)} UI (scan-limited). External source power is excluded.`));
        const r=d.response;
        content.append(el('p',`Both held-clock states give ${Math.min(...r.map(x=>x.boost_db)).toFixed(3)} to ${Math.max(...r.map(x=>x.boost_db)).toFixed(3)} dB peaking at ${(Math.min(...r.map(x=>x.peak_frequency_hz))/1e9).toFixed(3)} to ${(Math.max(...r.map(x=>x.peak_frequency_hz))/1e9).toFixed(3)} GHz. The 6 dB / 2.1 GHz request matches the existing internal 0.5 dB / 100 MHz tolerances.`));
        const scope=el('section');scope.className='receiver-verification-scope';
        scope.append(el('h3','Verification scope'),el('p',`Nominal simulation results only; full receiver verification remains future work. ${d.model_violations.length} devices have signed model-domain violations. Noise instrumentation was rejected; HD3 and PVT remain unverified. Controls were calibrated from measured results, not RL. No runtime retuning, BER or routed layout result is claimed.`));content.append(scope);
        content.append(el('h3','Prototype files'));
        const links=el('div');links.className='evidence-file-links';
        const names={deck:'Download prototype deck',drawing:'Open exact drawing','response-eye':'Open response and eye',review:'Review and retained failures','link-result':'Nominal results',config:'Control selection',waveform:'Waveform data',terminals:'Terminal voltages'};
        for(const a of d.artifact_links){const link=el('a',names[a.key]||a.key);link.href=a.url;link.target='_blank';link.rel='noopener';if(a.key==='deck')link.download='Nebula_programmable_receiver.cir';links.append(link);}content.append(links);
        for(const [key,title,alt] of [['drawing','Exact programmable receiver drawing','Exact saved programmable receiver device connections and sizes'],['response-eye','Measured response and eye','Saved loaded response at three capacitor controls and nominal transistor receiver eye']]){
          const visual=el('details');visual.className='prototype-visual';visual.append(el('summary',title));
          const img=el('img');img.alt=alt;img.loading='lazy';
          visual.addEventListener('toggle',()=>{if(visual.open&&!img.getAttribute('src'))img.src=d.artifact_links.find(a=>a.key===key).url;});
          img.addEventListener('error',()=>{img.hidden=true;visual.append(el('p','Preview unavailable. Use the named artifact link above to inspect the saved file.'));},{once:true});
          visual.append(img);content.append(visual);
        }
        content.append(el('p','These downloads contain saved prototype evidence. They do not replace the primary circuit or add the prototype to an older run archive. Matching future exports include it separately without fresh verification.'));
        loaded=true;
      } catch(error){if(token===revision)NebulaEvidenceLoading.failure(content,error,load);}
      finally{loading=false;}
    }
    details.addEventListener('toggle',()=>{if(details.open&&!loaded)load();});
  }
  return {render};
})();
