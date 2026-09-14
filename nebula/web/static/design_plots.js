"use strict";

const NebulaDesignPlots = (() => {
  const ns = "http://www.w3.org/2000/svg";
  const ink = "#173449", teal = "#007d99", amber = "#a65f18";
  function chart(target, title, xmin, xmax, ymin, ymax, xticks, yticks, xlabel, ylabel) {
    const svg = document.createElementNS(ns,"svg");
    svg.setAttribute("viewBox","0 0 720 380"); svg.setAttribute("role","img"); svg.setAttribute("aria-label",title);
    const add = (tag,attrs,text) => {const e=document.createElementNS(ns,tag);Object.entries(attrs).forEach(([k,v])=>e.setAttribute(k,String(v)));if(text!==undefined)e.textContent=text;svg.append(e);return e;};
    const x = v => 72+(v-xmin)/(xmax-xmin)*626, y = v => 311-(v-ymin)/(ymax-ymin)*275;
    add("rect",{x:72,y:36,width:626,height:275,fill:"#f5fafc"});
    xticks.forEach(([v,label])=>{add("line",{x1:x(v),x2:x(v),y1:36,y2:311,stroke:"#d8e6eb"});add("text",{x:x(v),y:338,"text-anchor":"middle",fill:ink},label);});
    yticks.forEach(([v,label])=>{add("line",{x1:72,x2:698,y1:y(v),y2:y(v),stroke:v===0?"#91acb8":"#d8e6eb"});add("text",{x:61,y:y(v)+6,"text-anchor":"end",fill:ink},label);});
    add("text",{x:385,y:371,"text-anchor":"middle",fill:ink},xlabel);
    add("text",{x:20,y:174,transform:"rotate(-90 20 174)","text-anchor":"middle",fill:ink},ylabel);
    target.replaceChildren(svg);
    const path = (xs,ys,attrs={}) => add("path",{d:xs.map((v,i)=>`${i?'L':'M'}${x(v).toFixed(2)},${y(ys[i]).toFixed(2)}`).join(" "),fill:"none",stroke:teal,"stroke-width":1.4,...attrs});
    return {svg,add,x,y,path};
  }
  const tick = v => Number(v.toFixed(3)).toString();
  function eye(target, data, mode, sharedLimit = null) {
    const traces = mode === "ctle" ? data.ctle_v : data.ideal_dfe_v;
    const scale = Math.max(...data.ctle_v.flat().map(Math.abs),...data.ideal_dfe_v.flat().map(Math.abs),.01)*1.06;
    const lim = sharedLimit || Math.ceil(scale*20)/20;
    const plot=chart(target,mode==="ctle"?"Modeled CTLE output eye":"Modeled ideal 1-tap feedback eye",-1,1,-lim,lim,[-1,-.5,0,.5,1].map(v=>[v,String(v)]),[-lim,-lim/2,0,lim/2,lim].map(v=>[v,tick(v)]),`Time relative to sampling cursor (UI; 1 UI = ${data.ui_ps} ps)`,"Differential voltage (V)");
    traces.forEach(trace=>plot.path(data.time_ui,trace,{"stroke-opacity":.12,"stroke-width":1.25}));
    plot.add("line",{x1:plot.x(0),x2:plot.x(0),y1:36,y2:311,stroke:amber,"stroke-dasharray":"5 5","stroke-width":1.3});
    plot.add("text",{x:90,y:23,fill:ink},`${data.segments} modeled NRZ traces`);
  }
  function envelope(target,data,sharedLimit=null) {
    const lim=sharedLimit || Math.ceil(Math.max(...data.height_v.map(Math.abs),.01)*.6*20)/20;
    const plot=chart(target,"Worst-case ISI opening envelope",-.5,.5,-lim,lim,[-.5,-.25,0,.25,.5].map(v=>[v,String(v)]),[-lim,-lim/2,0,lim/2,lim].map(v=>[v,tick(v)]),"Sampling phase (UI)","Opening boundary (V)");
    for(const sign of [-1,1])plot.path(data.phase_ui,data.height_v.map(v=>sign*v/2),{"stroke-width":3});
    plot.add("text",{x:90,y:23,fill:ink},"Worst-case ISI opening");
  }
  function ac(target,data) {
    const lo=Math.floor(Math.min(...data.gain_db)/5)*5,hi=Math.ceil(Math.max(...data.gain_db)/5)*5;
    const yt=[];for(let v=lo;v<=hi;v+=5)yt.push([v,String(v)]);
    const plot=chart(target,"Saved nominal CTLE AC response",-2,1,lo,hi===lo?hi+5:hi,[[.01,"0.01"],[.1,"0.1"],[1,"1"],[10,"10"]].map(([v,t])=>[Math.log10(v),t]),yt,"Frequency (GHz, logarithmic)","Differential gain (dB)");
    plot.path(data.frequency_ghz.map(Math.log10),data.gain_db,{"stroke-width":3});
    for(const [value,color,dash] of [[data.target_peak_ghz,amber,"5 5"],[data.measured_peak_ghz,teal,"2 3"]]){
      const x=plot.x(Math.log10(value));plot.add("line",{x1:x,x2:x,y1:36,y2:311,stroke:color,"stroke-dasharray":dash,"stroke-width":1.5});
    }
    plot.add("text",{x:90,y:23,fill:amber},`Target ${data.target_peak_ghz.toFixed(3)} GHz`);
    plot.add("text",{x:350,y:23,fill:teal},`Measured ${data.measured_peak_ghz.toFixed(3)} GHz`);
  }
  return {eye,envelope,ac};
})();
