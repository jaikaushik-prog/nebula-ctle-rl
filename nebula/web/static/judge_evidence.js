"use strict";
// Read-only evidence presentation, not a special UI mode or acceptance mechanism.
const NebulaJudgeEvidence = (() => {
  let revision = 0;
  const el = (tag, text) => { const n=document.createElement(tag); if(text!==undefined)n.textContent=text; return n; };
  async function render(design) {
    const token=++revision;
    NebulaRunPrototype.render(design);
    const catalogue=document.querySelector('#candidateCatalogue');
    const accepted=(design.recovery?.attempts || []).find(a=>a.accepted);
    const setting=accepted?.setting ?? design.nominal?.setting;
    const physical=design.method==='rl-physical';
    document.querySelector('#selectedCircuitIdentity').textContent=physical&&setting!==undefined?`Setting ${setting}`:physical?'Physical output':'Historical bank';
    document.querySelector('#selectedCircuitSummary').textContent=physical?'Physical CTLE with fixed Rs/Cs. Eye results use a behavioral DFE.':'Historical adaptive-bank result, not a single final physical circuit.';
    catalogue.textContent='512 candidate settings: 8 attenuation levels x 8 Rs values x 8 Cs values. This catalogue supports RL candidate search; it is not a second final circuit. The recorded eye gate uses an ideal behavioral DFE.';
    const card=document.querySelector('#selectedReceiverEvidence'), index=document.querySelector('#judgeEvidenceIndex');
    card.hidden=true; card.open=false; card.replaceChildren(); index.replaceChildren(el('p','Loading saved evidence index...'));
    try {
      const response=await fetch(`/api/submission/index/${encodeURIComponent(design.id)}`, {cache:"no-store"});
      if(!response.ok) { const body=await response.json().catch(()=>({})); throw Object.assign(new Error(body.error || 'Evidence index unavailable'), {status:response.status}); }
      const data=await response.json(); if(token!==revision)return;
      if(data.receiver) {
        const r=data.receiver;
        const summary=el('summary'),copy=el('span');copy.className='evidence-summary-copy';
        copy.append(el('strong','Selected CTLE + transistor DFE'),el('span','Separate nominal measurement matched to this CTLE'));summary.append(copy);card.append(summary);
        const content=el('div');content.className='receiver-evidence-content';
        const metrics=el('dl');metrics.className='receiver-measurements';
        for(const [label,value] of [['Decisions',`${r.correct_bits}/${r.scored_bits}`],['Sampled eye',`${r.eye_height_mv.toFixed(3)} mV`],['Width above 100 mV',`${r.aperture_above_100mv_ui.toFixed(3)} UI`],['VDD power',`${r.power_mw.toFixed(4)} mW`]]){const item=el('div');item.append(el('dt',label),el('dd',value));metrics.append(item);}
        content.append(metrics);
        const conditions=el('p',`TT / 1.8 V / 27 C, constructed 7.5 dB channel, external clock and fixed tap. Positive aperture: ${r.positive_aperture_ui.toFixed(3)} UI (scan-limited). The exact selected CTLE deck hash matches this measurement.`);conditions.className='receiver-conditions';content.append(conditions);
        const scope=el('section');scope.className='receiver-verification-scope';scope.append(el('h3','Verification scope'),el('p','Six attenuator PMOS devices violate signed model-domain limits. Full receiver verification remains false; no analog/link PVT, BER or routed layout claim. External source power is excluded.'));content.append(scope);
        content.append(el('h3','Measured circuit files'));
        const links=el('div');links.className='evidence-file-links';
        const names={'design.cir':'Transistor receiver deck','trace.txt':'Waveform data','result.json':'Nominal results','terminals.txt':'Terminal voltages','ngspice.log':'Simulator log'};
        for(const a of r.artifacts){const link=el('a',names[a.name]||a.name);link.href=a.url;link.target='_blank';link.rel='noopener';links.append(link);}
        content.append(links);card.append(content);card.hidden=false;
      }
      index.replaceChildren(el('h3','Evidence ownership and exact bytes'),el('p',data.note));
      const table=el('table'), head=el('thead'), hr=el('tr');
      for(const text of ['Circuit / artifact','Measurement scope','SHA-256']) hr.append(el('th',text));
      head.append(hr);table.append(head);const body=el('tbody');
      for(const row of data.rows) {
        const tr=el('tr'),name=el('td'),a=el('a',row.artifact);a.href=row.url;a.target='_blank';a.rel='noopener';
        name.append(el('strong',row.circuit),el('br'),a);tr.append(name,el('td',row.scope),el('td',row.sha256));body.append(tr);
      }
      table.append(body);index.append(table);
    } catch(error) { if(token===revision)NebulaEvidenceLoading.failure(index,error,()=>render(design)); }
  }
  document.addEventListener('DOMContentLoaded',()=>{
    const image=document.querySelector('#hardwareSchematic');
    image.addEventListener('load',()=>{image.hidden=false;});
    image.addEventListener('error',()=>{image.hidden=true; const p=el('p','The embedded drawing could not load. Use “Open schematic” to inspect the exact saved image.');image.parentElement.append(p);});
  });
  return {render};
})();
