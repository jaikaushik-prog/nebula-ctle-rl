"use strict";

const state = {
  current: null,
  hardware: null,
  visuals: new Map(),
  compareRevision: 0,
  signalView: "dfe",
  designs: new Map(),
  selectedCondition: null,
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

function showMessage(text, kind = "info") {
  const box = $("#message");
  box.textContent = text;
  box.className = `message ${kind}`;
  box.hidden = false;
}

function clearMessage() {
  $("#message").hidden = true;
}

async function api(url, options = {}) {
  const response = await fetch(url, options);
  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) throw new Error(data.error || data || `Request failed (${response.status})`);
  return data;
}

function finite(value) {
  return value !== null && value !== undefined && value !== "" && typeof value !== "boolean" && Number.isFinite(Number(value));
}

function number(value, digits = 3) {
  if (!finite(value)) return "Not measured";
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: digits });
}

function engineering(value, key) {
  if (!finite(value)) return "Not measured";
  const v = Number(value);
  if (key === "w_in" || key === "l_in") return `${number(v * 1e6, 3)} um`;
  if (key === "i_bias") return `${number(v * 1e3, 3)} mA`;
  if (key === "cs" || key === "cl") return `${number(v * 1e12, 3)} pF`;
  if (key === "rs" || key === "rl") return `${number(v, 2)} ohm`;
  if (key === "vcm_in") return `${number(v, 3)} V`;
  if (key === "nf_in") return number(v, 0);
  return number(v, 4);
}

function measured(row) {
  if (!finite(row.measured)) return "Not measured";
  const digits = ["V", "UI", "mm2"].includes(row.unit) ? 4 : 3;
  return `${number(row.measured, digits)} ${row.unit}`;
}

function requirement(row) {
  if (!finite(row.target)) return "Not recorded";
  if (row.rule === "min") return `>= ${number(row.target, 3)} ${row.unit}`;
  if (row.rule === "max") return `<= ${number(row.target, 3)} ${row.unit}`;
  if (row.rule === "target") return `${number(row.target, 3)} ${row.unit} +/- 1.5 dB`;
  if (row.rule === "target_oct") return `${number(row.target, 3)} ${row.unit} +/- 0.3 octave`;
  return `${number(row.target, 3)} ${row.unit}`;
}

function statusNode(status, label = null) {
  const span = document.createElement("span");
  const name = status === true ? "pass" : status === false ? "fail" : "unknown";
  span.className = `status ${name}`;
  const dot = document.createElement("span");
  dot.className = "status-dot";
  const copy = document.createElement("span");
  copy.textContent = label || (status === true ? "Pass" : status === false ? "Fail" : "Not measured");
  span.append(dot, copy);
  return span;
}

function selectTab(name, updateHash = true) {
  const checkpoint = name === "checkpoint";
  if (name === "hardware" || checkpoint) name = "results";
  if (!["results", "pvt", "compare", "channel", "evidence"].includes(name)) name = "results";
  $$(".tab").forEach((button) => button.classList.toggle("active", button.dataset.tab === name));
  $$(".view").forEach((view) => view.classList.toggle("active", view.dataset.view === name));
  document.body.dataset.view = name;
  if (name === "compare") renderCompare();
  if (state.current) {
    renderOutcome(state.current);
    renderRunTruth(state.current);
  }
  $("#resultOverview").hidden = name !== "results";
  if (updateHash) { history.replaceState(null, "", `#${name}`); window.scrollTo({top: 0, behavior: "instant"}); }
  if (checkpoint) { $("#referenceCheckpoint").open = true; $("#referenceCheckpoint").scrollIntoView({block:"start",behavior:"instant"}); }
}

function artifactUrl(design, name) {
  return `/api/artifacts/${encodeURIComponent(design.id)}/${encodeURIComponent(name)}`;
}

function syncRequest(design) {
  const req = design.request || {};
  $("#peakingInput").value = finite(req.peaking_db) ? req.peaking_db : "";
  $("#frequencyInput").value = finite(req.f_peak_ghz) ? req.f_peak_ghz : "";
  if (finite(req.peaking_db) && finite(req.f_peak_ghz)) {
    $("#requestText").value = `I need ${req.peaking_db} dB of peaking with the peak near ${req.f_peak_ghz} GHz`;
  }
  if (state.hardware) renderHardwareTargetState(state.hardware);
}

function renderDesign(design) {
  state.current = design;
  state.designs.set(design.id, design);
  clearMessage();
  if (["rl-hybrid", "rl-physical"].includes(design.method)) {
    $("#designMode").value = design.method;
    updateModeSummary();
  }

  const req = design.request || {};
  syncRequest(design);
  $("#resultTitle").textContent = finite(req.peaking_db) && finite(req.f_peak_ghz)
    ? `${number(req.peaking_db, 2)} dB CTLE at ${number(req.f_peak_ghz, 3)} GHz`
    : "Generated CTLE design";
  $("#resultContext").textContent = design.cached
    ? `Saved design / ${design.method === "rl-physical" ? "physical CTLE" : "RL adaptive bank"}`
    : `Generated design / ${design.method === "rl-physical" ? "physical CTLE" : "RL adaptive bank"}`;
  const sourceBadge = $("#sourceBadge");
  sourceBadge.textContent = design.source === "saved-run" ? "Saved replay" : design.cached ? "Historical demo" : "New run this session";
  sourceBadge.classList.toggle("live", design.source === "live-run");

  renderSelectedOverview(design);
  NebulaJudgeEvidence.render(design);
  const connectedReceiver = (design.artifacts || []).includes("receiver/receiver.cir");
  $(".selected-circuit-scope").textContent = "design.cir contains the physical CTLE, attenuation, bias and fixed Rs/Cs. Its eye gate uses an ideal behavioral DFE outside the netlist. " + (connectedReceiver
    ? "receiver/receiver.cir is a separate structural transistor-DFE export; it does not establish nominal or full receiver verification."
    : "Matching nominal transistor-receiver evidence is grouped below by exact CTLE hash. The independent 9 dB reference owns its own measurements.");
  NebulaRecoveryTrace.render(design);
  NebulaLanguageAssistant.select(design);
  renderSelectedEye(design);
  NebulaCircuitViews.renderDesign(design);
  renderSchematic(design);
  renderSpecs(design.specs || []);
  renderSizing(design.nominal?.params || {}, design.method === "rl-physical");
  renderOutcome(design);
  renderRunTruth(design);
  renderPvt(design);
  renderEvidence(design);
  refreshComparePickers();
  $("#compareA").value = design.id;
  if ($("#compareB").value === design.id) $("#compareB").value = [...state.designs.keys()].find(id=>id!==design.id) || design.id;
  if ($('.tab[data-tab="hardware"]')?.classList.contains("active") && state.hardware) {
    renderOutcome(state.current);
    renderRunTruth(state.current);
  }
}

function renderSelectedOverview(design) {
  const picker = $("#selectedRun"); picker.replaceChildren();
  for (const item of state.designs.values()) {
    const option = document.createElement("option"); option.value = item.id;
    option.textContent = `${number(item.request?.peaking_db, 2)} dB / ${number(item.request?.f_peak_ghz, 3)} GHz - ${item.method === "rl-physical" ? "physical CTLE" : "adaptive bank"} (${item.id === "judge-demo" ? "historical, not final" : `${item.status === "pass" ? "accepted" : "FAILED"} ${item.id.slice(0, 8)}`})`;
    picker.append(option);
  }
  picker.value = design.id;
  const m = design.nominal?.meas || {}, v = design.verification || {};
  $("#resultHighlights").replaceChildren();
  for (const [label, value] of [["Measured peaking", `${number(m.peaking_db, 3)} dB`], ["Measured peak", `${number(m._f_peak_ghz, 3)} GHz`], ["Modeled eye height", `${number(finite(m.eye_h_v) ? m.eye_h_v * 1000 : null, 1)} mV`], ["Modeled eye width", `${number(m.eye_w_ui, 3)} UI`]]) {
    const box = document.createElement("div"), name = document.createElement("span"), strong = document.createElement("strong");
    name.textContent = label; strong.textContent = value; box.append(name, strong); $("#resultHighlights").append(box);
  }
  $("#resultCoverage").textContent = `${number(v.n_pass, 0)}/${number(v.n_points, 0)} conditions pass across ${number(v.n_corners, 0)} PVT corners and ${number(v.n_channel_losses, 0)} channel losses. ${design.method === "rl-physical" ? "One fixed exported CTLE." : "Adaptive settings by condition."}`;
}

function loadDesignVisual(design) {
  if (state.visuals.has(design.id)) return state.visuals.get(design.id);
  const promise = api(`/api/eye/${encodeURIComponent(design.id)}`).then(data => {
    if (data.run_id !== design.id) throw new Error("Visual evidence belongs to a different run.");
    return data;
  }).catch(error => {state.visuals.delete(design.id);throw error;});
  state.visuals.set(design.id,promise);
  return promise;
}

async function renderSelectedEye(design) {
  $("#designAcPlot").textContent = "Loading saved AC...";
  $("#designAcScope").textContent = "";
  try {
    const data = await loadDesignVisual(design);
    if (state.current?.id !== design.id) return;
    NebulaDesignPlots.ac($("#designAcPlot"),data.ac);
    $("#designAcScope").textContent = `Nominal ngspice AC / ${data.design_id}`;
  } catch (error) {
    if (state.current?.id !== design.id) return;
    $("#designAcPlot").textContent = "No raw AC retained for this artifact.";
    $("#designAcScope").textContent = "Recorded specifications remain available below.";
  }
}

async function renderCompareEyes(a,b) {
  const revision = ++state.compareRevision;
  const designs = [a,b];
  for (const [i,key] of ["A","B"].entries()) {
    const design=designs[i],m=design?.nominal?.meas || {};
    $(`#eye${key}Title`).textContent = design ? `${key} / ${number(design.request?.peaking_db,2)} dB at ${number(design.request?.f_peak_ghz,3)} GHz` : `Circuit ${key}`;
    $(`#eye${key}Metrics`).textContent = design ? `${number(finite(m.eye_h_v)?m.eye_h_v*1000:null,1)} mV / ${number(m.eye_w_ui,3)} UI recorded margin` : "";
    $(`#eye${key}Plot`).textContent = design ? "Loading waveform..." : "Select a circuit.";
    $(`#eye${key}Scope`).textContent = "";
  }
  const results = await Promise.allSettled(designs.map(design => design ? loadDesignVisual(design) : Promise.reject(new Error("Select a circuit."))));
  if (revision !== state.compareRevision) return;
  const data = results.filter(r=>r.status==="fulfilled").map(r=>r.value);
  const mode=state.signalView;
  const max = data.reduce((value,d)=>Math.max(value,...(mode==="envelope"?d.height_v.map(v=>Math.abs(v)/2):[...d.waveform.ctle_v.flat(),...d.waveform.ideal_dfe_v.flat()].map(Math.abs))),.01);
  const limit = Math.ceil(max*1.06*20)/20;
  results.forEach((result,i)=>{
    const key=i===0?"A":"B",target=$(`#eye${key}Plot`),scope=$(`#eye${key}Scope`);
    if (result.status !== "fulfilled") {target.textContent="Waveform unavailable";scope.textContent=designs[i]?"This saved artifact retains scalar margins, not raw AC for a waveform.":"Select another completed design.";return;}
    const d=result.value;
    if (mode==="envelope") NebulaDesignPlots.envelope(target,d,limit);
    else NebulaDesignPlots.eye(target,d.waveform,mode,limit);
    scope.textContent = `${d.channel_loss_db} dB channel / ${d.design_id}`;
  });
  $("#compareEyeMethod").textContent = mode === "envelope"
    ? "Worst-case ISI opening envelope with ideal first-post-cursor cancellation at each sampling phase. This is the source of the recorded margin dimensions; it is not a waveform or BER measurement."
    : "Noiseless modeled waveform from each circuit's saved transistor AC and constructed channel. Both eyes use identical voltage and time scales. Ideal feedback removes the sampled h1 contribution using the known previous bit; rectangular feedback updates between samples. No decision errors, jitter, noise or transistor clock circuitry are modeled. Recorded margins come from the separate worst-case cursor analysis, not from these finite overlays.";
}

function renderSchematic(design) {
  const frame = $("#schematicFrame");
  frame.replaceChildren();
  const hasImage = (design.artifacts || []).includes("design_schematic.png");
  const link = $("#openSchematic");
  $("#generatedSchematicTitle").textContent = design.method === "rl-physical"
    ? "Generated physical CTLE export" : "Generated adaptive-bank CTLE export";
  $("#generatedSchematicScope").textContent = design.method === "rl-physical"
    ? "Exact generated physical CTLE, attenuation, bias and fixed Rs/Cs. Ideal behavioral DFE scoring is outside this exported netlist."
    : "Parsed from the selected cached-bank CTLE deck; link scoring and transistor hardware evidence are shown separately.";
  if (!hasImage) {
    const p = document.createElement("p");
    p.className = "muted";
    p.textContent = "No schematic image was written for this result.";
    frame.append(p);
    link.hidden = true;
    return;
  }
  const src = artifactUrl(design, "design_schematic.png");
  const img = document.createElement("img");
  img.src = src;
  img.alt = "Generated CTLE schematic parsed from the exact SPICE deck";
  frame.append(img);
  link.href = src;
  link.hidden = false;
}

function renderSpecs(rows) {
  const body = $("#specTable");
  body.replaceChildren();
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    const name = document.createElement("td");
    name.textContent = row.label;
    const target = document.createElement("td");
    target.textContent = requirement(row);
    target.className = "numeric";
    const value = document.createElement("td");
    value.textContent = measured(row);
    value.className = "numeric";
    const result = document.createElement("td");
    result.append(statusNode(row.status, row.status_label));
    tr.append(name, target, value, result);
    body.append(tr);
  });
}

function renderSizing(params, physical = false) {
  const labels = {
    w_in: "Input pair width", l_in: "Input pair length", nf_in: "Input fingers",
    i_bias: "Bias current", rs: "Source resistance", cs: "Source capacitance",
    rl: "Load resistance", cl: "Output load", vcm_in: "Input common mode",
  };
  if (physical) labels.i_bias = "Tail current sizing target";
  const grid = $("#sizingGrid");
  grid.replaceChildren();
  Object.entries(labels).forEach(([key, label]) => {
    const item = document.createElement("div");
    const name = document.createElement("span");
    name.textContent = label;
    const value = document.createElement("strong");
    value.textContent = engineering(params[key], key);
    item.append(name, value);
    grid.append(item);
  });
}

function hardwareStage(block, extraClass = "") {
  const article = document.createElement("article");
  article.className = `hardware-stage ${extraClass}`.trim();
  const heading = document.createElement("div");
  heading.className = "hardware-stage-heading";
  const title = document.createElement("h4");
  title.textContent = block.label;
  const stateMark = document.createElement("span");
  stateMark.textContent = block.status === "implemented" ? "Implemented" : "Unverified";
  stateMark.className = block.status === "implemented" ? "implemented" : "unverified";
  heading.append(title);
  if (block.status !== "implemented") heading.append(stateMark);
  const detail = document.createElement("p");
  detail.textContent = block.detail;
  article.append(heading, detail);
  return article;
}

function hardwareLink() {
  const link = document.createElement("span");
  link.className = "hardware-chain-link";
  link.setAttribute("aria-hidden", "true");
  link.append(document.createElement("i"));
  return link;
}

function renderHardwareTopology(blocks) {
  const target = $("#hardwareTopology");
  target.replaceChildren();
  const byKey = new Map((blocks || []).map((block) => [block.key, block]));
  const required = ["attenuator", "ctle", "rs", "cs", "summer", "memory", "dac"];
  if (required.some((key) => !byKey.has(key))) {
    throw new Error("The verified topology record is incomplete.");
  }

  const chain = document.createElement("div");
  chain.className = "hardware-chain-main";
  const ctle = hardwareStage(byKey.get("ctle"), "ctle-stage");
  const controls = document.createElement("div");
  controls.className = "control-primitives";
  controls.append(hardwareStage(byKey.get("rs"), "primitive"));
  controls.append(hardwareStage(byKey.get("cs"), "primitive"));
  ctle.append(controls);
  chain.append(
    hardwareStage(byKey.get("attenuator")),
    hardwareLink(),
    ctle,
    hardwareLink(),
    hardwareStage(byKey.get("summer")),
    hardwareLink(),
    hardwareStage(byKey.get("memory")),
    hardwareLink(),
    hardwareStage(byKey.get("dac")),
  );

  const feedback = document.createElement("div");
  feedback.className = "hardware-feedback";
  const trace = document.createElement("span");
  trace.setAttribute("aria-hidden", "true");
  const label = document.createElement("strong");
  label.textContent = "Decided bit returns through the 1-tap current DAC to the CML summer";
  feedback.append(trace, label);
  target.append(chain, feedback);
}

function hardwareTargetMatches(checkpoint, requestedBoost, requestedFrequency) {
  if (!finite(checkpoint.nominal?.target_boost_db) || !finite(checkpoint.nominal?.target_peak_frequency_hz)) return false;
  const checkpointBoost = Number(checkpoint.nominal?.target_boost_db);
  const checkpointFrequency = Number(checkpoint.nominal?.target_peak_frequency_hz) / 1e9;
  return checkpointBoost > 0 && checkpointFrequency > 0
    && Number.isFinite(requestedBoost) && Number.isFinite(requestedFrequency)
    && Math.abs(requestedBoost - checkpointBoost) < 1e-9
    && Math.abs(requestedFrequency - checkpointFrequency) < 1e-9;
}

function renderHardwareTargetState(checkpoint) {
  const label = `${number(checkpoint.nominal?.target_boost_db, 2)} dB at ${number(checkpoint.nominal?.target_peak_frequency_hz / 1e9, 3)} GHz`;
  $("#hardwareRequestedTarget").textContent = label;
  $("#hardwareMatchedEvidence").hidden = false;
  $("#hardwareTargetMismatch").hidden = true;
  $("#hardwareTargetMatch").className = "checkpoint-match";
  $("#hardwareMatchMessage").textContent = "Saved transistor evidence for this independent calibration.";
  $("#hardwareTargetSummary").textContent = `${label} calibrated configurable CTLE + transistor DFE. Separate from the selected run.`;
}

function renderHardwareMetrics(checkpoint) {
  const nominal = checkpoint.nominal || {};
  const pvt = checkpoint.pvt || {};
  const scaled = (value, scale, digits) => number(finite(value) ? value * scale : null, digits);
  const rows = [
    ["Loaded response", `${number(nominal.boost_db?.min, 3)}-${number(nominal.boost_db?.max, 3)} dB at ${scaled(nominal.peak_frequency_hz?.min, 1e-9, 4)}-${scaled(nominal.peak_frequency_hz?.max, 1e-9, 4)} GHz`, "Nominal held-state AC"],
    ["Input noise", `${scaled(nominal.input_noise_vrms?.max, 1e3, 4)} mV rms`, "Nominal held-clock model, 10 MHz-5 GHz"],
    ["HD3", `${number(nominal.hd3_dbc?.min, 3)} to ${number(nominal.hd3_dbc?.max, 3)} dBc`, "Clocked, 100 MHz, 100 mV differential peak"],
    ["Fresh decode", `${number(nominal.correct_bits, 0)}/${number(nominal.scored_bits, 0)} bits`, `${scaled(nominal.sampled_eye_height_v, 1e3, 1)} mV sampled eye`],
    ["VDD power", `${scaled(pvt.maximum_vdd_power_w, 1e3, 3)} mW maximum`, "CTLE + transistor DFE across Link PVT"],
    ["Fixed-control Link PVT", `${number(pvt.n_pass, 0)}/${number(pvt.n_points, 0)} points pass`, `${scaled(pvt.minimum_eye_height_v, 1e3, 1)} mV minimum eye; ${number(pvt.minimum_width_above_100mv_ui, 3)} UI minimum above 100 mV`],
  ];
  const target = $("#hardwareMetrics");
  target.replaceChildren();
  rows.forEach(([label, value, scope]) => {
    const item = document.createElement("div");
    const name = document.createElement("span");
    name.textContent = label;
    const measured = document.createElement("strong");
    measured.textContent = value;
    const note = document.createElement("small");
    note.textContent = scope;
    item.append(name, measured, note);
    target.append(item);
  });
}

function renderHardwareCheckpoint(checkpoint) {
  state.hardware = checkpoint;
  $("#hardwareLoadError").hidden = true;
  $("#hardwareContent").hidden = false;
  const badge = $("#hardwareStatusBadge");
  badge.textContent = checkpoint.status === "pass" ? "Verified checkpoint" : "Unavailable";
  badge.className = `source-badge ${checkpoint.status === "pass" ? "pass" : ""}`;
  const controls = checkpoint.controls || {};
  $("#hardwareControlR").textContent = `${number(controls.r_fraction, 3)} VDD / ${number(controls.r_control_v_nominal, 3)} V nominal`;
  $("#hardwareControlC").textContent = `${number(controls.c_fraction, 3)} VDD / ${number(controls.c_control_v_nominal, 3)} V nominal`;
  $("#hardwareControlNote").textContent = controls.corner_retuning
    ? "Corner-specific controls were used."
    : "Calibrated settings (read-only). These are physical voltage controls, not fixed exported Rs/Cs. Editing them and running fresh verification is not available here; the saved Link PVT result applies only to this setting.";
  renderHardwareTopology(checkpoint.topology);
  NebulaCircuitViews.mount(checkpoint);
  renderHardwareMetrics(checkpoint);
  renderHardwareTargetState(checkpoint);
  if (state.current) NebulaCircuitViews.renderDesign(state.current);
  for (const [imageId, linkId, key] of [
    ["hardwareEye", "openHardwareEye", "nominal-eye"],
    ["hardwareSchematic", "openHardwareSchematic", "hardware-schematic"],
  ]) {
    const visual = checkpoint.evidence.find((item) => item.key === key);
    if (!visual) throw new Error("The hardware visual evidence is missing.");
    document.getElementById(imageId).src = visual.url;
    document.getElementById(linkId).href = visual.url;
  }
  $("#hardwareNote").textContent = "Latest checkpoint: transistor DFE and configurable Rs/Cs pass 45/45 Link PVT points. Open Hardware proof for the exact scope.";
  if (state.current) {
    renderOutcome(state.current);
    renderRunTruth(state.current);
  }
}

function renderHardwareFailure(message) {
  state.hardware = null;
  $("#hardwareContent").hidden = true;
  const error = $("#hardwareLoadError");
  error.textContent = `Hardware evidence could not be validated: ${message}`;
  error.hidden = false;
  $("#hardwareStatusBadge").textContent = "Unavailable";
  $("#hardwareStatusBadge").className = "source-badge";
  $("#hardwareNote").textContent = "The latest hardware evidence could not be validated.";
}

function renderHardwareSidebar() {
  const checkpoint = state.hardware;
  if (!checkpoint) return;
  const pvt = checkpoint.pvt || {};
  const card = $("#outcomeCard");
  card.className = `outcome-card ${checkpoint.status}`;
  $("#outcomeIcon").textContent = checkpoint.status === "pass" ? "OK" : "!";
  $("#outcomeText").textContent = checkpoint.status === "pass" ? "HARDWARE PASS" : "HARDWARE UNAVAILABLE";
  $("#outcomeDetail").textContent = `${number(pvt.n_pass, 0)} of ${number(pvt.n_points, 0)} fixed-control Link PVT points pass; analog PVT not verified`;
  $("#failureBox").hidden = true;
  $("#coverageBar").style.width = pvt.all_pass ? "100%" : "0%";
  $("#coverageText").textContent = `${number(pvt.n_pass, 0)}/${number(pvt.n_points, 0)} Link PVT points pass on one 7.5 dB constructed channel without corner retuning.`;
  const provenance = checkpoint.provenance || {};
  const controls = checkpoint.controls || {};
  const values = [
    ["Source", `Pinned Entries ${provenance.nominal_entry} + ${provenance.pvt_entry}`],
    ["Method", "Transistor CTLE + DFE"],
    ["PDK", provenance.pdk || "Not recorded"],
    ["Simulator", provenance.simulator || "Not recorded"],
    ["Controls", `${number(controls.r_fraction, 3)} / ${number(controls.c_fraction, 3)} VDD`],
    ["Channel", `${number(pvt.channel_loss_db, 1)} dB constructed`],
    ["Conditions", number(pvt.n_points, 0)],
  ];
  const dl = $("#runTruth");
  dl.replaceChildren();
  values.forEach(([term, value]) => {
    const row = document.createElement("div");
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = term;
    dd.textContent = String(value);
    row.append(dt, dd);
    dl.append(row);
  });
  $("#hardwareNote").textContent = "Physical Rs/Cs controls, CML summer, master/slave decision memory and 1-tap feedback DAC are present in the pinned SKY130 netlist.";
}

function renderOutcome(design) {
  const card = $("#outcomeCard");
  card.className = `outcome-card ${design.status}`;
  $("#outcomeIcon").textContent = design.status === "pass" ? "OK" : "!";
  $("#outcomeText").textContent = design.status_label || "MODEL STATUS UNKNOWN";
  const v = design.verification || {};
  $("#outcomeDetail").textContent = finite(v.n_points)
    ? `${number(v.n_pass, 0)} of ${number(v.n_points, 0)} model conditions pass; full receiver not verified`
    : "No complete verification record";
  const failure = $("#failureBox");
  if ((design.failure_reasons || []).length) {
    failure.replaceChildren();
    const strong = document.createElement("strong"); strong.textContent = "Why this was not delivered as a pass";
    const list = document.createElement("ul");
    design.failure_reasons.forEach((text) => { const li = document.createElement("li"); li.textContent = text; list.append(li); });
    failure.append(strong, list); failure.hidden = false;
  } else {
    failure.hidden = true;
  }

  const total = Number(v.n_points || 0);
  const passed = Number(v.n_pass || 0);
  const ratio = total ? 100 * passed / total : 0;
  $("#coverageBar").style.width = `${ratio}%`;
  $("#coverageText").textContent = total
    ? `${passed}/${total} recorded conditions pass across ${v.n_corners || "?"} PVT corners and ${v.n_channel_losses || "?"} channel-loss points.`
    : "No verification conditions were recorded.";
}

function renderRunTruth(design) {
  const v = design.verification || {};
  const values = [
    ["Source", design.source === "saved-run" ? "Saved replay; originally generated by live pipeline" : design.cached ? "Historical preverified adaptive-bank demo" : "New live pipeline run this session"],
    ["Method", design.method_label || "Not recorded"],
    ["PDK", "SKY130"],
    ["Simulator", "ngspice"],
    ["Design ID", design.nominal?.design_id || "Not recorded"],
    ["Policy seed", design.search?.policy_seed ?? "Not recorded"],
    ["Conditions", finite(v.n_points) ? number(v.n_points, 0) : "Not recorded"],
  ];
  const dl = $("#runTruth"); dl.replaceChildren();
  values.forEach(([term, value]) => {
    const row = document.createElement("div"); const dt = document.createElement("dt"); const dd = document.createElement("dd");
    dt.textContent = term; dd.textContent = String(value); row.append(dt, dd); dl.append(row);
  });
}

function parseCorner(text) {
  const parts = String(text || "").replace("C", "").split("/");
  return { process: parts[0] || "?", vdd: parts[1] || "?", temp: parts[2] || "?" };
}

function renderPvt(design) {
  $("#pvtSettingsLabel").textContent = design.method === "rl-physical" ? "fixed settings in slice" : "adaptive settings in slice";
  const v = design.verification || {};
  const select = $("#channelLossSelect");
  select.replaceChildren();
  const summaries = new Map((v.loss_summaries || []).map((item) => [Number(item.channel_loss_db), item]));
  (v.channel_losses_db || []).forEach((loss) => {
    const summary = summaries.get(Number(loss));
    const result = summary
      ? ` - ${summary.n_pass}/${summary.n_points}${summary.n_failed ? ` (${summary.n_failed} fail)` : ""}`
      : "";
    const option = document.createElement("option"); option.value = String(loss); option.textContent = `${number(loss, 1)} dB${result}`; select.append(option);
  });
  const preferredLoss = finite(v.first_failing_loss_db) ? Number(v.first_failing_loss_db)
    : (v.channel_losses_db || []).some((loss) => Number(loss) === 7.5) ? 7.5
      : Number(select.options[0]?.value);
  if (finite(preferredLoss)) select.value = String(preferredLoss);
  $("#pvtOverallCount").textContent = finite(v.n_pass) && finite(v.n_points)
    ? `${number(v.n_pass, 0)}/${number(v.n_points, 0)}` : "Not measured";
  select.onchange = () => drawPvtGrid(design, Number(select.value));
  if (select.options.length) drawPvtGrid(design, Number(select.value));
  else {
    $("#pvtGrid").innerHTML = "";
    $("#pvtPassCount").textContent = "Not measured";
    $("#pvtWorstEye").textContent = "Not measured";
    $("#pvtSettings").textContent = "Not measured";
    $("#pvtScopeNote").textContent = "No per-condition verification rows were recorded.";
  }
}

function drawPvtGrid(design, loss) {
  const all = design.verification?.conditions || [];
  const rows = all.filter((item) => Number(item.channel_loss_db) === Number(loss));
  const processes = ["ss", "sf", "tt", "fs", "ff"].filter((p) => rows.some((item) => parseCorner(item.corner).process === p));
  const columns = [...new Set(rows.map((item) => { const c = parseCorner(item.corner); return `${c.vdd}/${c.temp}`; }))]
    .sort((a, b) => { const [av, at] = a.split("/").map(Number); const [bv, bt] = b.split("/").map(Number); return av - bv || at - bt; });
  const byKey = new Map(rows.map((item) => { const c = parseCorner(item.corner); return [`${c.process}|${c.vdd}/${c.temp}`, item]; }));
  const grid = $("#pvtGrid"); grid.replaceChildren();
  const blank = document.createElement("div"); blank.className = "pvt-head"; blank.textContent = "PVT"; grid.append(blank);
  columns.forEach((column) => { const head = document.createElement("div"); head.className = "pvt-head"; const [vdd, temp] = column.split("/"); head.textContent = `${vdd}x / ${temp}C`; grid.append(head); });
  processes.forEach((process) => {
    const head = document.createElement("div"); head.className = "pvt-row-head"; head.textContent = process.toUpperCase(); grid.append(head);
    columns.forEach((column) => {
      const item = byKey.get(`${process}|${column}`);
      const status = item?.condition_status || (item?.compliant === true ? "pass" : item?.compliant === false ? "fail" : "missing");
      const button = document.createElement("button"); button.type = "button";
      button.className = `pvt-cell ${status}`;
      const verdict = document.createElement("strong"); verdict.textContent = item ? status.toUpperCase() : "--";
      const codes = document.createElement("span"); codes.textContent = item ? `${item.setting ?? "off-grid"}: A${item.atten_code ?? "?"} R${Number.isInteger(item.bank_code) ? Math.floor(item.bank_code / 8) : "?"} C${Number.isInteger(item.bank_code) ? item.bank_code % 8 : "?"}` : "Not measured";
      button.append(verdict, codes);
      button.title = item ? `${item.corner}: ${status}${item.reason ? ` - ${item.reason}` : ""}` : "Not measured";
      button.disabled = !item;
      if (item) button.onclick = () => showCondition(item, button);
      grid.append(button);
    });
  });
  const pass = rows.filter((row) => row.condition_status === "pass" || row.compliant === true).length;
  const failed = rows.filter((row) => row.condition_status === "fail" || row.compliant === false).length;
  const areas = rows.map((row) => row.eye_area).filter(finite).map(Number);
  const settings = new Set(rows.map((row) => row.setting).filter((v) => v !== null && v !== undefined));
  $("#pvtPassCount").textContent = `${pass}/${rows.length}`;
  $("#pvtWorstEye").textContent = areas.length ? `${number(Math.min(...areas), 4)} V*UI` : "Not measured";
  $("#pvtSettings").textContent = number(settings.size, 0);
  const scope = $("#pvtScopeNote");
  scope.className = `pvt-scope-note${failed ? " fail" : ""}`;
  if (design.verification?.condition_counts_match === false) {
    scope.textContent = "Saved totals and per-condition rows disagree. Inspect the evidence bundle before using this verdict.";
    scope.className = "pvt-scope-note fail";
  } else if (Number(design.verification?.n_failed) > 0) {
    scope.textContent = `Overall: ${number(design.verification.n_failed, 0)} of ${number(design.verification.n_points, 0)} conditions fail. Showing ${number(loss, 1)} dB: ${failed} failure${failed === 1 ? "" : "s"}.`;
  } else {
    scope.textContent = `Overall: all ${number(design.verification?.n_points, 0)} conditions pass. Showing the ${number(loss, 1)} dB channel-loss slice.`;
  }
  scope.textContent += " Scope: CTLE electrical model + ideal behavioral DFE. Full S7 area and transistor receiver PVT are unverified.";
  const detail = $("#conditionDetail"); detail.replaceChildren();
  const prompt = document.createElement("p"); prompt.textContent = "Select a cell to see its recorded values."; detail.append(prompt);
}

function showCondition(item, button) {
  $$(".pvt-cell.selected").forEach((cell) => cell.classList.remove("selected"));
  button.classList.add("selected");
  const detail = $("#conditionDetail"); detail.replaceChildren();
  const dl = document.createElement("dl");
  const items = [
    ["Corner", item.corner], ["Channel loss", `${number(item.channel_loss_db, 1)} dB`],
    ["Result", item.condition_status === "missing" ? "Not measured" : item.compliant ? "Pass" : "Fail"], ["Eye area", `${number(item.eye_area, 5)} V*UI`],
    ["Selected setting", `${item.setting ?? "Off-grid"} (A${item.atten_code ?? "?"}, R${Number.isInteger(item.bank_code) ? Math.floor(item.bank_code / 8) : "?"}, C${Number.isInteger(item.bank_code) ? item.bank_code % 8 : "?"})`],
    ["Decision source", item.source || "Not recorded"], ["RL measurements", item.rl_measurements ?? "Not recorded"],
    ["Shield table rows", item.bank_rows_checked ?? "Not recorded"],
  ];
  if (item.meas) {
    items.splice(6); // Physical conditions are fresh measurements, not bank decisions.
    items.push(["Peaking", `${number(item.meas.peaking_db, 4)} dB`],
      ["Peak frequency", `${number(2.5 * 2 ** item.meas.f_peak_oct, 6)} GHz`],
      ["CTLE + reference power", `${number(item.meas.power_w * 1e3, 4)} mW`],
      ["Input noise", `${number(item.meas.inoise_vrms * 1e3, 4)} mV rms`],
      ["Eye height / width", finite(item.eye_h_v) && finite(item.eye_w_ui)
        ? `${number(item.eye_h_v * 1e3, 2)} mV / ${number(item.eye_w_ui, 4)} UI` : "Not measured"]);
    if (item.reason) items.push(["Failure reason", item.reason]);
    if (item.failed_specs?.length) items.push(["Failed checks", item.failed_specs.join(", ")]);
    if (item.unmeasured_specs?.length) items.push(["Unmeasured checks", item.unmeasured_specs.join(", ")]);
  }
  items.forEach(([name, value]) => { const wrap = document.createElement("div"); const dt = document.createElement("dt"); const dd = document.createElement("dd"); dt.textContent = name; dd.textContent = String(value); wrap.append(dt, dd); dl.append(wrap); });
  detail.append(dl);
}

function renderEvidence(design) {
  const list = $("#artifactList"); list.replaceChildren();
  (design.artifacts || []).forEach((name) => {
    const row = document.createElement("div"); row.className = "artifact-row";
    const copy = document.createElement("div"); const strong = document.createElement("strong"); strong.textContent = name;
    const description = document.createElement("span"); description.textContent = artifactDescription(name); copy.append(strong, document.createElement("br"), description);
    const link = document.createElement("a"); link.className = "text-button"; link.textContent = "Open"; link.href = artifactUrl(design, name); link.target = "_blank"; link.rel = "noopener";
    row.append(copy, link); list.append(row);
  });
  if (!(design.artifacts || []).length) {
    const row = document.createElement("div"); row.className = "artifact-row"; row.textContent = "No artifacts were written."; list.append(row);
  }
  $("#downloadEvidence").href = `/api/evidence/${encodeURIComponent(design.id)}.zip`;
}

function artifactDescription(name) {
  const descriptions = {
    "design.json": "Complete machine-readable measurement and provenance record",
    "design.cir": "Exact selected physical CTLE deck; behavioral DFE is outside this netlist",
    "receiver/receiver.cir": "Connected transistor CTLE + DFE structural export; not nominally or fully verified",
    "receiver/metadata.json": "Connected receiver identity and structural-only verification scope",
    "design_schematic.png": "Schematic parsed from the delivered deck",
    "rl_dashboard.png": "Recorded policy and safety-shield decisions",
    "programmable_architecture.png": "Hardware boundary and code manifest",
    "explanation.txt": "Grounded plain-language explanation",
    "README.md": "Artifact reading guide",
  };
  return descriptions[name] || "Pipeline output";
}

function circuitName(design) {
  const req = design.request || {};
  const prefix = design.cached ? "Historical adaptive bank" : `${design.status === "pass" ? "Accepted" : "FAILED"} ${design.id.slice(0, 8)}`;
  return `${prefix}: ${number(req.peaking_db, 1)} dB at ${number(req.f_peak_ghz, 3)} GHz`;
}

function refreshComparePickers() {
  const selectors = [$("#compareA"), $("#compareB")];
  const previous = selectors.map((select) => select.value);
  selectors.forEach((select) => {
    select.replaceChildren();
    state.designs.forEach((design) => { const option = document.createElement("option"); option.value = design.id; option.textContent = circuitName(design); select.append(option); });
  });
  if (previous[0] && state.designs.has(previous[0])) selectors[0].value = previous[0];
  const ids = [...state.designs.keys()];
  if (previous[1] && state.designs.has(previous[1]) && previous[1] !== selectors[0].value) {
    selectors[1].value = previous[1];
  } else if (ids.length > 1) {
    selectors[1].value = ids.findLast((id) => id !== selectors[0].value) || ids[0];
  }
  selectors.forEach((select) => { select.onchange = renderCompare; });
  renderCompare();
}

function renderCompare() {
  const a = state.designs.get($("#compareA").value);
  const b = state.designs.get($("#compareB").value);
  if (document.body.dataset.view === "compare") renderCompareEyes(a,b);
  const canCompare = a && b && a.id !== b.id;
  $("#compareEmpty").hidden = Boolean(canCompare);
  $("#compareTableWrap").hidden = !canCompare;
  if (!canCompare) return;
  $("#compareAHead").textContent = circuitName(a);
  $("#compareBHead").textContent = circuitName(b);
  const rows = [
    ["Model result", a.status_label || "Unknown", b.status_label || "Unknown"],
    ["Design ID", a.nominal.design_id || "Not recorded", b.nominal.design_id || "Not recorded"],
    ["Requested peaking", `${number(a.request?.peaking_db, 3)} dB`, `${number(b.request?.peaking_db, 3)} dB`],
    ["Requested peak frequency", `${number(a.request?.f_peak_ghz, 4)} GHz`, `${number(b.request?.f_peak_ghz, 4)} GHz`],
    ["Measured peaking", measuredValue(a, "peaking_db", "dB"), measuredValue(b, "peaking_db", "dB")],
    ["Peak frequency", measuredValue(a, "_f_peak_ghz", "GHz"), measuredValue(b, "_f_peak_ghz", "GHz")],
    ["Eye height", measuredValue(a, "eye_h_v", "V"), measuredValue(b, "eye_h_v", "V")],
    ["Eye width", measuredValue(a, "eye_w_ui", "UI"), measuredValue(b, "eye_w_ui", "UI")],
    ["CTLE power", measuredValue(a, "_power_mw", "mW"), measuredValue(b, "_power_mw", "mW")],
    ["Partial passive area", measuredValue(a, "area_mm2", "mm2"), measuredValue(b, "area_mm2", "mm2")],
    ...Object.entries({ w_in: "Input pair width", l_in: "Input pair length", nf_in: "Input fingers", i_bias: "Bias current", rs: "Source resistance", cs: "Source capacitance", rl: "Load resistance", cl: "Output load", vcm_in: "Input common mode" })
      .map(([key, label]) => [label, engineering(a.nominal.params[key], key), engineering(b.nominal.params[key], key)]),
  ];
  const body = $("#compareTable"); body.replaceChildren();
  rows.forEach((values) => { const tr = document.createElement("tr"); values.forEach((value, index) => { const td = document.createElement("td"); td.textContent = String(value); if (index) td.className = "numeric"; tr.append(td); }); body.append(tr); });
}

function measuredValue(design, key, unit) {
  const value = design.nominal?.meas?.[key];
  return finite(value) ? `${number(value, 4)} ${unit}` : "Not measured";
}

async function parseNaturalRequest() {
  const note = $("#parseNote"); note.classList.remove("error");
  try {
    const parsed = await api("/api/parse", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ request: $("#requestText").value, use_llm: NebulaLanguageAssistant.optedIn() }) });
    $("#peakingInput").value = parsed.peaking_db;
    $("#frequencyInput").value = parsed.f_peak_ghz;
    if (state.hardware) renderHardwareTargetState(state.hardware);
    note.textContent = NebulaLanguageAssistant.parseLabel(parsed);
    return parsed;
  } catch (error) {
    note.textContent = error.message; note.classList.add("error"); throw error;
  }
}

async function generate() {
  clearMessage();
  const peaking = Number($("#peakingInput").value);
  const frequency = Number($("#frequencyInput").value);
  if (!finite($("#peakingInput").value) || !finite($("#frequencyInput").value)) { $("#dialogError").textContent="Enter both requested values."; $("#dialogError").hidden=false; return; }
  const request = `${peaking} dB of peaking with the peak near ${frequency} GHz`;
  $("#requestText").value = request;
  const button = $("#generateButton"); button.disabled = true;
  try {
    const job = await api("/api/design", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ request, method: $("#designMode").value, use_llm: NebulaLanguageAssistant.optedIn() }) });
    $("#targetDialog").close();
    showProgress(job);
    await pollJob(job.id, (update) => showProgress(update));
  } catch (error) {
    if ($("#targetDialog").open) {$("#dialogError").textContent=error.message;$("#dialogError").hidden=false;}
    else showMessage(error.message, "error");
  } finally {
    button.disabled = false;
  }
}

function updateModeSummary() {
  const physical = $("#designMode").value === "rl-physical";
  $("#modeSummary").textContent = physical
    ? "Fixed Rs/Cs and physical reference; fresh PVT verification."
    : "Frozen RL proposals with measured-bank safety checks.";
}

function showProgress(job) {
  const panel = $("#progressPanel"); panel.hidden = false;
  $("#progressStage").textContent = job.stage;
  $("#progressValue").textContent = `${job.progress}%`;
  $("#progressBar").style.width = `${job.progress}%`;
}

async function pollJob(id, onUpdate) {
  for (;;) {
    const job = await api(`/api/jobs/${encodeURIComponent(id)}`);
    onUpdate(job);
    if (job.status === "complete") {
      localStorage.setItem("nebula-selected-design", job.result.id);
      renderDesign(job.result); selectTab("results");
      $("#referenceCheckpoint").open = false;
      $("#progressPanel").hidden = true;
      $("#resultOverview").focus({preventScroll: true});
      return job.result;
    }
    if (job.status === "failed") throw new Error(job.error || "The pipeline stopped without a result.");
    await new Promise((resolve) => setTimeout(resolve, 700));
  }
}

function setChannelFile(file) {
  const input = $("#channelFile");
  if (file && file !== input.files?.[0]) {
    const transfer = new DataTransfer(); transfer.items.add(file); input.files = transfer.files;
  }
  $("#channelFilename").textContent = file ? file.name : "or drop it here";
}

async function profileChannel() {
  const file = $("#channelFile").files?.[0];
  if (!file) { showMessage("Choose a Touchstone channel file first.", "error"); return; }
  const button = $("#profileChannel"); button.disabled = true;
  try {
    const outPort = Number($("#outputPort").value); const inPort = Number($("#inputPort").value);
    const job = await api(`/api/channel?out=${encodeURIComponent(outPort)}&in=${encodeURIComponent(inPort)}`, {
      method: "POST", headers: { "Content-Type": "application/octet-stream", "X-Filename": file.name }, body: file,
    });
    showMessage("Channel profiling started. The design worker remains protected.", "info");
    const result = await pollChannelJob(job.id);
    renderChannel(result);
  } catch (error) { showMessage(error.message, "error"); }
  finally { button.disabled = false; }
}

async function pollChannelJob(id) {
  for (;;) {
    const job = await api(`/api/jobs/${encodeURIComponent(id)}`);
    showMessage(`${job.stage} (${job.progress}%)`, "info");
    if (job.status === "complete") return job.result;
    if (job.status === "failed") throw new Error(job.error || "Channel profiling stopped.");
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
}

function renderChannel(profile) {
  const target = $("#channelResult"); target.className = "channel-result warning"; target.hidden = false; target.replaceChildren();
  const title = document.createElement("h3"); title.textContent = profile.status;
  const limitation = document.createElement("p"); limitation.textContent = profile.limitation;
  const dl = document.createElement("dl");
  const values = [
    ["Source file", profile.source_file], ["SHA-256", profile.source_sha256],
    ["Nyquist loss", `${number(profile.measured_loss_at_nyquist_db, 3)} dB`],
    ["Fit RMS residual", `${number(profile.fit?.rms_residual_db, 4)} dB`],
    ["Nearest characterised loss", `${number(profile.nearest_characterised_loss_db, 1)} dB`],
    ["Points parsed", number(profile.n_points, 0)],
  ];
  values.forEach(([name, value]) => { const wrap = document.createElement("div"); const dt = document.createElement("dt"); const dd = document.createElement("dd"); dt.textContent = name; dd.textContent = value; wrap.append(dt, dd); dl.append(wrap); });
  target.append(title, limitation, dl);
  if ((profile.artifacts || []).includes("channel_profile.png")) { const img = document.createElement("img"); img.src = `/api/artifacts/${encodeURIComponent(profile.id)}/channel_profile.png`; img.alt = "Uploaded insertion-loss data and fitted channel model"; target.append(img); }
  clearMessage();
}

function bindEvents() {
  $$(".tab").forEach((button) => button.addEventListener("click", () => selectTab(button.dataset.tab)));
  $$('[data-open-tab]').forEach((button) => button.addEventListener("click", () => selectTab(button.dataset.openTab)));
  $$('[data-signal-view]').forEach(button => button.addEventListener("click", () => {
    state.signalView=button.dataset.signalView;
    $$('[data-signal-view]').forEach(item=>item.setAttribute("aria-pressed",String(item===button)));
    renderCompare();
  }));
  for (const button of $$("[data-inspector]")) button.addEventListener("click", () => {
    for (const item of $$("[data-inspector]")) item.setAttribute("aria-pressed",String(item === button));
    for (const panel of $$("[data-inspector-panel]")) panel.hidden = panel.dataset.inspectorPanel !== button.dataset.inspector;
  });
  $("#expandCircuit").addEventListener("click", () => {
    const expanded = $("#circuitWorkbench").classList.toggle("circuit-focus");
    $("#designInspector").hidden = expanded;
    $("#expandCircuit").setAttribute("aria-pressed",String(expanded));
    $("#expandCircuit").textContent = expanded ? "Show inspector" : "Expand circuit";
  });
  $("#setTargetButton").addEventListener("click", () => {$("#dialogError").hidden=true;$("#targetDialog").showModal();$("#peakingInput").focus();});
  $("#closeTargetDialog").addEventListener("click", () => $("#targetDialog").close());
  $("#selectedRun").addEventListener("change", event => {
    const design = state.designs.get(event.target.value);
    if (design) { localStorage.setItem("nebula-selected-design", design.id); renderDesign(design); selectTab("results"); }
  });
  $("#readRequest").addEventListener("click", () => parseNaturalRequest().catch(() => {}));
  $("#designMode").addEventListener("change", updateModeSummary);
  for (const input of [$("#peakingInput"), $("#frequencyInput")]) {
    input.addEventListener("input", () => {
      if (state.hardware) renderHardwareTargetState(state.hardware);
    });
  }
  $("#generateButton").addEventListener("click", generate);
  $("#swapCompare").addEventListener("click", () => { const a = $("#compareA"); const b = $("#compareB"); [a.value, b.value] = [b.value, a.value]; renderCompare(); });
  $("#channelFile").addEventListener("change", (event) => setChannelFile(event.target.files?.[0]));
  $("#profileChannel").addEventListener("click", profileChannel);
  const drop = $("#dropZone");
  ["dragenter", "dragover"].forEach((name) => drop.addEventListener(name, (event) => { event.preventDefault(); drop.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((name) => drop.addEventListener(name, (event) => { event.preventDefault(); drop.classList.remove("drag"); }));
  drop.addEventListener("drop", (event) => setChannelFile(event.dataTransfer.files?.[0]));
}

async function init() {
  bindEvents();
  NebulaLanguageAssistant.init(api);
  $("#resultVerdict").append($("#outcomeCard"), $("#failureBox"));
  $("#inspectorProvenance").append($(".verification-panel"));
  selectTab(location.hash.slice(1) || "results", false);
  updateModeSummary();
  const hardwareRequest = api("/api/hardware")
    .then(renderHardwareCheckpoint)
    .catch((error) => renderHardwareFailure(error.message));
  try {
    renderDesign(await api("/api/demo"));
    await hardwareRequest;
    const catalogue = await api("/api/designs");
    for (const item of catalogue.designs || []) {
      if (!state.designs.has(item.id)) {
        try {
          const design = await api(`/api/designs/${encodeURIComponent(item.id)}`);
          state.designs.set(design.id, design);
        } catch (_) {
          // A run can disappear only when its server process ends. Keep the
          // currently loaded evidence usable if that happens.
        }
      }
    }
    refreshComparePickers();
    const savedId = localStorage.getItem("nebula-selected-design");
    const saved = state.designs.get(savedId) || state.designs.get("4608cf1c525f4e59b2d5226059b0ce5d") || [...state.designs.values()].filter(d => d.id !== "judge-demo" && d.status === "pass").at(-1);
    if (saved) renderDesign(saved);
    else renderSelectedOverview(state.current);
    const requestedView = location.hash.slice(1);
    if (["results", "hardware", "pvt", "compare", "channel", "evidence"].includes(requestedView)) {
      selectTab(requestedView, false);
    }
  }
  catch (error) { showMessage(`The preverified design could not be loaded: ${error.message}`, "error"); }
}

document.addEventListener("DOMContentLoaded", init);
