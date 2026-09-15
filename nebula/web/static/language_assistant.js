/* Optional wording only; deterministic measurements remain authoritative. */
(function (root) {
  "use strict";
  let available = false, currentId = null, revision = 0, requestApi = null;
  const el = id => document.getElementById(id);
  const enabled = (isAvailable, checked) => isAvailable === true && checked === true;
  const optedIn = () => enabled(available, el("use-llm").checked);
  function parseLabel(parsed) {
    const notes = Array.isArray(parsed.notes) ? parsed.notes.join(" ") : "";
    return `Parser: ${parsed.parsed_by || "not recorded"}. Read as ${parsed.peaking_db ?? "unknown"} dB at ${parsed.f_peak_ghz ?? "unknown"} GHz. ${notes}`.trim();
  }
  function explanationView(data) {
    return {text:typeof data.text === "string" ? data.text : "No explanation returned.",
      label:data.label || (data.source === "llm" ? "LLM-grounded wording" : "Deterministic fallback"),
      verdict:data.verdict || "Verification verdict not provided.",
      scope:data.scope || "Generated physical CTLE only; ideal behavioral DFE is outside the exported netlist. Independent transistor receiver evidence has a separate scope."};
  }
  function select(design) {
    currentId = design.id; revision += 1;
    el("explanationResult").hidden = true;
    el("explainResultButton").disabled = false;
    el("selectedParserProvenance").textContent = design.natural_language
      ? parseLabel(design.natural_language) : "Parser provenance is not recorded for this saved run.";
  }
  async function explain() {
    if (!currentId || !requestApi) return;
    const selectedId = currentId, selectedRevision = revision;
    const button = el("explainResultButton"); button.disabled = true;
    try {
      const data = await requestApi("/api/llm/explain", {method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({run_id:selectedId, use_llm:optedIn()})});
      if (selectedId !== currentId || selectedRevision !== revision) return;
      const view = explanationView(data);
      el("explanationLabel").textContent = view.label;
      el("explanationText").textContent = view.text;
      el("explanationVerdict").textContent = view.verdict;
      el("explanationScope").textContent = view.scope;
      el("explanationResult").hidden = false;
    } catch (error) {
      if (selectedRevision !== revision) return;
      el("explanationLabel").textContent = "Explanation unavailable";
      el("explanationText").textContent = error.message;
      el("explanationVerdict").textContent = "Recorded circuit verification is unchanged.";
      el("explanationScope").textContent = explanationView({}).scope;
      el("explanationResult").hidden = false;
    } finally { if (selectedRevision === revision) button.disabled = false; }
  }
  async function init(api) {
    requestApi = api;
    const boxes = [el("use-llm"), el("explanationUseLlm")];
    for (const box of boxes) {
      box.checked = false; box.disabled = true;
      box.addEventListener("change", () => {for (const other of boxes) other.checked = enabled(available, box.checked);});
    }
    el("explainResultButton").addEventListener("click", explain);
    let label;
    try {
      const info = await api("/api/llm/availability");
      available = info.available === true;
      label = `${info.label || (available ? "Optional LLM available" : "Optional LLM unavailable")}. ${info.reason || ""}`.trim();
    } catch (_) { available = false; label = "Optional LLM unavailable. Deterministic parsing and explanations remain available."; }
    for (const box of boxes) {box.disabled = !available; box.checked = false;}
    el("llmAvailability").textContent = label;
    el("explanationAvailability").textContent = label;
  }
  const api = {enabled, optedIn, parseLabel, explanationView, select, init};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.NebulaLanguageAssistant = api;
})(typeof window === "undefined" ? globalThis : window);
