"use strict";

const state = {
  current: null,
  designs: new Map(),
  selectedCondition: null,
  judgeMode: false,
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
  return value !== null && value !== undefined && Number.isFinite(Number(value));
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
  if (row.rule === "target") return `${number(row.target, 3)} ${row.unit} +/- tolerance`;
  if (row.rule === "target_oct") return `${number(row.target, 3)} ${row.unit} +/- tolerance`;
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
  $$(".tab").forEach((button) => button.classList.toggle("active", button.dataset.tab === name));
  $$(".view").forEach((view) => view.classList.toggle("active", view.dataset.view === name));
  if (name === "compare") renderCompare();
  if (updateHash) history.replaceState(null, "", `#${name}`);
}

function artifactUrl(design, name) {
  return `/api/artifacts/${encodeURIComponent(design.id)}/${encodeURIComponent(name)}`;
}

function renderDesign(design) {
  state.current = design;
  state.designs.set(design.id, design);
  clearMessage();

  const req = design.request || {};
  $("#resultTitle").textContent = finite(req.peaking_db) && finite(req.f_peak_ghz)
    ? `${number(req.peaking_db, 2)} dB CTLE at ${number(req.f_peak_ghz, 3)} GHz`
    : "Generated CTLE design";
  $("#resultContext").textContent = design.cached
    ? "Preverified judge artifact - loaded without rerunning SPICE"
    : "Live generated artifact";
  const sourceBadge = $("#sourceBadge");
  sourceBadge.textContent = design.cached ? "Preverified" : "Live run";
  sourceBadge.classList.toggle("live", !design.cached);

  const meas = design.nominal?.meas || {};
  $("#metricPeaking").textContent = finite(meas.peaking_db) ? `${number(meas.peaking_db, 3)} dB` : "--";
  $("#metricPeakingTarget").textContent = finite(req.peaking_db) ? `Requested ${number(req.peaking_db, 2)} dB` : "Not requested";
  $("#metricFrequency").textContent = finite(meas._f_peak_ghz) ? `${number(meas._f_peak_ghz, 4)} GHz` : "--";
  $("#metricFrequencyTarget").textContent = finite(req.f_peak_ghz) ? `Requested ${number(req.f_peak_ghz, 3)} GHz` : "Not requested";
  $("#metricEye").textContent = finite(meas.eye_h_v) && finite(meas.eye_w_ui)
    ? `${number(meas.eye_h_v * 1e3, 1)} mV / ${number(meas.eye_w_ui, 3)} UI` : "--";

  renderSchematic(design);
  renderSpecs(design.specs || []);
  renderSizing(design.nominal?.params || {}, design.method === "rl-physical");
  const scope = design.implementation_scope || {};
  const hardware = design.hardware || {};
  renderHardware({...hardware, note: [hardware.note, ...(scope.notes || [])].filter(Boolean).join(" ")});
  renderOutcome(design);
  renderRunTruth(design);
  renderPvt(design);
  renderEvidence(design);
  refreshComparePickers();
}

function renderSchematic(design) {
  const frame = $("#schematicFrame");
  frame.replaceChildren();
  const hasImage = (design.artifacts || []).includes("design_schematic.png");
  const link = $("#openSchematic");
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

function renderHardware(hardware) {
  const target = $("#hardwareTruth");
  target.replaceChildren();
  const note = document.createElement("p");
  note.textContent = hardware.note || "No hardware implementation record was stored.";
  target.append(note);
  const list = document.createElement("ul");
  list.className = "truth-list";
  Object.entries(hardware.items || {}).forEach(([name, value]) => {
    const li = document.createElement("li");
    const left = document.createElement("span"); left.textContent = name;
    const right = document.createElement("strong"); right.textContent = String(value);
    li.append(left, right); list.append(li);
  });
  target.append(list);
  const incomplete = hardware.incomplete_items || [];
  $("#hardwareNote").textContent = incomplete.length
    ? `${incomplete.length} implementation item${incomplete.length === 1 ? "" : "s"} remain. Open the hardware boundary below for details.`
    : "All recorded hardware items are implemented.";
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
    ["Source", design.cached ? "Preverified artifact" : "Live pipeline"],
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
      const codes = document.createElement("span"); codes.textContent = item ? `A${item.atten_code ?? "?"} B${item.bank_code ?? "?"}` : "Not measured";
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
  $("#pvtWorstEye").textContent = areas.length ? number(Math.min(...areas), 4) : "Not measured";
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
    ["Result", item.condition_status === "missing" ? "Not measured" : item.compliant ? "Pass" : "Fail"], ["Eye area", number(item.eye_area, 5)],
    ["Selected code", `A${item.atten_code ?? "?"} / B${item.bank_code ?? "?"}`],
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
    "design.cir": "Exact representative ngspice deck",
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
  const prefix = design.cached ? "Judge demo" : "Generated";
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
    const parsed = await api("/api/parse", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ request: $("#requestText").value }) });
    $("#peakingInput").value = parsed.peaking_db;
    $("#frequencyInput").value = parsed.f_peak_ghz;
    note.textContent = parsed.notes?.length ? parsed.notes.join(" ") : `Read as ${number(parsed.peaking_db, 2)} dB at ${number(parsed.f_peak_ghz, 3)} GHz.`;
    return parsed;
  } catch (error) {
    note.textContent = error.message; note.classList.add("error"); throw error;
  }
}

async function generate() {
  clearMessage();
  const peaking = Number($("#peakingInput").value);
  const frequency = Number($("#frequencyInput").value);
  if (!Number.isFinite(peaking) || !Number.isFinite(frequency)) { showMessage("Enter both requested values.", "error"); return; }
  const request = `${peaking} dB of peaking with the peak near ${frequency} GHz`;
  $("#requestText").value = request;
  const button = $("#generateButton"); button.disabled = true;
  try {
    const job = await api("/api/design", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ request, method: $("#designMode").value }) });
    showProgress(job);
    await pollJob(job.id, (update) => showProgress(update));
  } catch (error) {
    showMessage(error.message, "error");
  } finally {
    button.disabled = false;
  }
}

function updateModeSummary() {
  const physical = $("#designMode").value === "rl-physical";
  $("#modeSummary").textContent = physical
    ? "One fixed circuit is remeasured across 45 PVT points and seven channel losses."
    : "The frozen RL policy proposes adaptive settings; the simulator-backed shield checks every condition.";
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
    if (job.status === "complete") { renderDesign(job.result); showMessage("Circuit generated and evidence recorded.", "info"); return job.result; }
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

async function enterJudgeMode() {
  try {
    const design = await api("/api/demo");
    state.judgeMode = true; $("#judgeStrip").hidden = false; $("#judgeButton").textContent = "Judge mode active";
    renderDesign(design); selectTab("results");
  } catch (error) { showMessage(error.message, "error"); }
}

function exitJudgeMode() {
  state.judgeMode = false; $("#judgeStrip").hidden = true; $("#judgeButton").textContent = "Enter judge mode";
}

function bindEvents() {
  $$(".tab").forEach((button) => button.addEventListener("click", () => selectTab(button.dataset.tab)));
  $$('[data-open-tab]').forEach((button) => button.addEventListener("click", () => selectTab(button.dataset.openTab)));
  $("#readRequest").addEventListener("click", () => parseNaturalRequest().catch(() => {}));
  $("#designMode").addEventListener("change", updateModeSummary);
  $("#generateButton").addEventListener("click", generate);
  $("#judgeButton").addEventListener("click", enterJudgeMode);
  $("#exitJudge").addEventListener("click", exitJudgeMode);
  $$('[data-judge-target]').forEach((button) => button.addEventListener("click", () => selectTab(button.dataset.judgeTarget)));
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
  updateModeSummary();
  try {
    renderDesign(await api("/api/demo"));
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
    const requestedView = location.hash.slice(1);
    if (["results", "pvt", "compare", "channel", "evidence"].includes(requestedView)) {
      selectTab(requestedView, false);
    }
  }
  catch (error) { showMessage(`The preverified design could not be loaded: ${error.message}`, "error"); }
}

document.addEventListener("DOMContentLoaded", init);
