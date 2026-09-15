/* Recorded attempts only: this presenter never infers a physical pass. */
(function (root) {
  "use strict";
  const present = value => value !== null && value !== undefined && Number.isFinite(Number(value));
  const fmt = value => present(value) ? String(Number(Number(value).toPrecision(6))) : "not recorded";
  function steps(design) {
    const recovery = design.recovery || design.recovery_workflow || {};
    if (!Array.isArray(recovery.attempts) || !recovery.attempts.length) return [];
    const request = design.request || {};
    const ghz = present(request.f_peak_ghz) ? request.f_peak_ghz
      : present(request.f_peak_hz) ? Number(request.f_peak_hz) / 1e9 : null;
    const result = [{kind:"request", title:`${fmt(request.peaking_db)} dB at ${fmt(ghz)} GHz`, detail:"Requested target"}];
    for (const attempt of recovery.attempts) {
      const kind = attempt.accepted === true ? "accepted" : attempt.accepted === false ? "rejected" : "unknown";
      const count = present(attempt.n_pass) && present(attempt.n_points)
        ? `${fmt(attempt.n_pass)}/${fmt(attempt.n_points)} model conditions` : "Condition count not recorded";
      result.push({kind, title:`Setting ${fmt(attempt.setting)}`,
        detail:`${count} - ${kind === "unknown" ? "decision not recorded" : kind}`});
    }
    const outputs = (Array.isArray(design.artifacts) ? design.artifacts : [])
      .filter(name => ["design.cir", "design.json", "design_schematic.png", "explanation.txt", "receiver/receiver.cir", "receiver/metadata.json"].includes(name));
    result.push({kind:outputs.length ? "outputs" : "missing_outputs", title:"Outputs",
      detail:outputs.length ? outputs.join(", ") : "No output files recorded"});
    return result;
  }
  function render(design) {
    const panel = document.getElementById("recoveryTrace");
    const list = document.getElementById("recoverySteps");
    const rows = steps(design);
    list.replaceChildren();
    panel.hidden = !rows.length;
    for (const row of rows) {
      const item = document.createElement("li"); item.className = `recovery-step ${row.kind}`;
      const title = document.createElement("strong"); title.textContent = row.title;
      const detail = document.createElement("span"); detail.textContent = row.detail;
      item.append(title, detail); list.append(item);
    }
  }
  const api = {steps, render};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.NebulaRecoveryTrace = api;
})(typeof window === "undefined" ? globalThis : window);
