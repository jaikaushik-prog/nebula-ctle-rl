"use strict";
// Explain a failed read without substituting data from another server.
const NebulaEvidenceLoading = (() => {
  const el = (tag, text) => { const n=document.createElement(tag); n.textContent=text; return n; };
  function failure(panel, error, retry) {
    const legacy=error.status===404 && location.port==='8765' &&
      ['127.0.0.1','localhost','[::1]'].includes(location.hostname);
    panel.replaceChildren();
    if(legacy) {
      const message='This older server cannot load the submission evidence. Open the current Nebula app on port 8766. Saved circuits and measurements are unchanged.';
      const makeLink=()=>{const a=el('a','Open current Nebula');a.href='http://127.0.0.1:8766/#results';a.className='button button-secondary';return a;};
      panel.append(el('p',message),makeLink());
      let banner=document.querySelector('#evidenceServerNotice');
      if(!banner){banner=el('section','');banner.id='evidenceServerNotice';banner.className='evidence-server-notice';banner.setAttribute('role','alert');document.querySelector('#workspace').prepend(banner);}
      banner.replaceChildren(el('p',message),makeLink());
      return;
    }
    panel.append(el('p',`Saved evidence could not load${error.status ? ` (HTTP ${error.status})` : ''}: ${error.message}. No verification claim added.`));
    const button=el('button','Retry saved evidence');button.type='button';button.className='button button-secondary';
    button.addEventListener('click',()=>{button.disabled=true;retry();},{once:true});panel.append(button);
  }
  return {failure};
})();
