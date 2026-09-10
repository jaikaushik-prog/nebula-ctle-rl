"use strict";

const state = {
  current: null,
  hardware: null,
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
  if (!["hardware", "results", "pvt", "compare", "channel", "evidence"].includes(name)) name = "hardware";
  $$(".tab").forEach((button) => button.classList.toggle("active", button.dataset.tab === name));
  $$(".view").forEach((view) => view.classList.toggle("active", view.dataset.view === name));
  document.body.dataset.view = name;
  $(".target-panel").hidden = name !== "results";
  if (name === "compare") renderCompare();
  if (name === "hardware" && state.hardware) renderHardwareSidebar();
  else if (state.current) {
    renderOutcome(state.current);
    renderRunTruth(state.current);
  }
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
    ? `Saved legacy explorer artifact / ${design.method === "rl-physical" ? "physical CTLE" : "RL adaptive bank"}`
    : `Generated legacy explorer artifact / ${design.method === "rl-physical" ? "physical CTLE" : "RL adaptive bank"}`;
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
  if ($('.tab[data-tab="hardware"]')?.classList.contains("active") && state.hardware) {
    renderHardwareSidebar();
  }
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
  $("#hardwareNote").textContent = state.hardware?.status === "pass"
    ? "Latest checkpoint: transistor DFE and configurable Rs/Cs pass 45/45 Link PVT points. The selected design's older boundary remains listed separately."
    : incomplete.length
      ? `${incomplete.length} implementation item${incomplete.length === 1 ? "" : "s"} remain. Open the hardware boundary below for details.`
      : "All recorded hardware items are implemented.";
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
  heading.append(title, stateMark);
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

function renderHardwareMetrics(checkpoint) {
  const nominal = checkpoint.nominal || {};
  const pvt = checkpoint.pvt || {};
  const rows = [
    ["Loaded response", `${number(nominal.boost_db?.min, 3)}-${number(nominal.boost_db?.max, 3)} dB at ${number((nominal.peak_frequency_hz?.min || 0) / 1e9, 4)}-${number((nominal.peak_frequency_hz?.max || 0) / 1e9, 4)} GHz`, "Nominal held-state AC"],
    ["Input noise", `${number((nominal.input_noise_vrms?.max || 0) * 1e3, 4)} mV rms`, "Nominal held-clock model, 10 MHz-5 GHz"],
    ["HD3", `${number(nominal.hd3_dbc?.min, 3)} to ${number(nominal.hd3_dbc?.max, 3)} dBc`, "Clocked, 100 MHz, 100 mV differential peak"],
    ["Fresh decode", `${number(nominal.correct_bits, 0)}/${number(nominal.scored_bits, 0)} bits`, `${number(nominal.sampled_eye_height_v * 1e3, 1)} mV sampled eye`],
    ["Link PVT", `${number(pvt.n_pass, 0)}/${number(pvt.n_points, 0)} pass`, `${number(pvt.minimum_eye_height_v * 1e3, 1)} mV minimum eye; ${number(pvt.minimum_width_above_100mv_ui, 3)} UI above 100 mV`],
    ["VDD power", `${number(pvt.maximum_vdd_power_w * 1e3, 3)} mW maximum`, "CTLE + transistor DFE across Link PVT"],
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

function renderHardwareCorner(row) {
  const target = $("#hardwareCornerDetail");
  target.replaceChildren();
  const heading = document.createElement("div");
  const title = document.createElement("h4");
  title.textContent = row.label;
  heading.append(title, statusNode(row.status === "pass", "Pass"));
  const values = [
    ["Decoded", `${number(row.correct_bits, 0)}/${number(row.scored_bits, 0)} bits`],
    ["Sampled eye", `${number(row.sampled_eye_height_v * 1e3, 3)} mV`],
    ["Positive aperture", `${number(row.positive_width_ui, 3)} UI`],
    ["Above 100 mV", `${number(row.width_above_100mv_ui, 3)} UI`],
    ["VDD power", `${number(row.vdd_power_w * 1e3, 3)} mW`],
    ["External clock", `${number(row.external_clock_positive_power_w * 1e3, 4)} mW`],
  ];
  const dl = document.createElement("dl");
  values.forEach(([name, value]) => {
    const wrap = document.createElement("div");
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = name;
    dd.textContent = value;
    wrap.append(dt, dd);
    dl.append(wrap);
  });
  const scope = document.createElement("p");
  scope.textContent = "Finite noiseless 7.5 dB constructed-channel result; not a BER measurement.";
  target.append(heading, dl, scope);
  $$(".hardware-cell", $("#hardwarePvtGrid")).forEach((cell) => {
    cell.classList.toggle("selected", cell.dataset.corner === row.corner);
  });
}

function drawHardwarePvt(checkpoint) {
  const pvt = checkpoint.pvt || {};
  const target = $("#hardwarePvtGrid");
  target.replaceChildren();
  const corners = pvt.corners || [];
  const processes = ["ss", "sf", "tt", "fs", "ff"];
  const supplies = [0.95, 1.00, 1.05];
  const temperatures = [0, 27, 125];
  const rows = new Map(corners.map((row) => [
    `${row.process}/${Number(row.vdd).toFixed(2)}/${row.temp_c}`,
    row,
  ]));
  const blank = document.createElement("div");
  blank.className = "hardware-pvt-head";
  blank.textContent = "PVT";
  target.append(blank);
  supplies.forEach((vdd) => temperatures.forEach((temp) => {
    const head = document.createElement("div");
    head.className = "hardware-pvt-head";
    const supply = document.createElement("strong");
    supply.textContent = `${(1.8 * vdd).toFixed(2)} V`;
    const temperature = document.createElement("span");
    temperature.textContent = `${temp} C`;
    head.append(supply, temperature);
    target.append(head);
  }));
  processes.forEach((process) => {
    const label = document.createElement("div");
    label.className = "hardware-pvt-row";
    label.textContent = process.toUpperCase();
    target.append(label);
    supplies.forEach((vdd) => temperatures.forEach((temp) => {
      const row = rows.get(`${process}/${vdd.toFixed(2)}/${temp}`);
      const button = document.createElement("button");
      button.type = "button";
      button.className = `hardware-cell ${row?.status || "missing"}`;
      if (!row) {
        button.disabled = true;
        button.textContent = "Missing";
      } else {
        button.dataset.corner = row.corner;
        button.setAttribute("aria-label", `${row.label}: pass, ${number(row.sampled_eye_height_v * 1e3, 1)} millivolt eye`);
        const result = document.createElement("strong");
        result.textContent = "PASS";
        const eye = document.createElement("span");
        eye.textContent = `${number(row.sampled_eye_height_v * 1e3, 0)} mV`;
        button.append(result, eye);
        button.addEventListener("click", () => renderHardwareCorner(row));
      }
      target.append(button);
    }));
  });
  $("#hardwarePvtCount").textContent = `${number(pvt.n_pass, 0)} / ${number(pvt.n_points, 0)} PASS`;
  if (corners.length) {
    const worst = corners.reduce((left, right) => left.sampled_eye_height_v <= right.sampled_eye_height_v ? left : right);
    renderHardwareCorner(worst);
  }
}

function renderHardwareEvidence(checkpoint) {
  const evidence = $("#hardwareEvidence");
  evidence.replaceChildren();
  (checkpoint.evidence || []).forEach((item) => {
    const link = document.createElement("a");
    link.href = item.url;
    link.target = "_blank";
    link.rel = "noopener";
    const label = document.createElement("strong");
    label.textContent = item.label;
    const detail = document.createElement("span");
    detail.textContent = item.key;
    link.append(label, detail);
    evidence.append(link);
  });

  const boundary = $("#hardwareBoundary");
  boundary.replaceChildren();
  (checkpoint.boundaries || []).forEach((item) => {
    const row = document.createElement("div");
    const label = document.createElement("strong");
    label.textContent = item.label;
    const detail = document.createElement("p");
    detail.textContent = item.detail;
    row.append(label, detail);
    boundary.append(row);
  });
}

function renderHardwareCheckpoint(checkpoint) {
  state.hardware = checkpoint;
  $("#hardwareLoadError").hidden = true;
  $("#hardwareContent").hidden = false;
  const badge = $("#hardwareStatusBadge");
  badge.textContent = checkpoint.status_label || "Verified checkpoint";
  badge.className = `source-badge ${checkpoint.status === "pass" ? "pass" : ""}`;
  $("#hardwareCalloutStatus").textContent = checkpoint.status === "pass"
    ? checkpoint.status_label
    : "Evidence unavailable";
  const controls = checkpoint.controls || {};
  $("#hardwareControlR").textContent = `${number(controls.r_fraction, 3)} VDD / ${number(controls.r_control_v_nominal, 3)} V nominal`;
  $("#hardwareControlC").textContent = `${number(controls.c_fraction, 3)} VDD / ${number(controls.c_control_v_nominal, 3)} V nominal`;
  $("#hardwareControlNote").textContent = controls.corner_retuning
    ? "Corner-specific controls were used."
    : "Calibrated settings (read-only). These are physical voltage controls, not fixed exported Rs/Cs. Editing them and running fresh verification is not available here; 45/45 Link PVT applies only to this saved setting.";
  renderHardwareTopology(checkpoint.topology);
  NebulaCircuitViews.mount(checkpoint);
  renderHardwareMetrics(checkpoint);
  drawHardwarePvt(checkpoint);
  renderHardwareEvidence(checkpoint);
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
  if ($('.tab[data-tab="hardware"]')?.classList.contains("active")) {
    renderHardwareSidebar();
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
  $("#hardwareCalloutStatus").textContent = "Evidence unavailable";
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
    ? "The live physical export is the legacy fixed Rs/Cs path. Open Receiver for the calibrated transistor DFE and configurable controls."
    : "Legacy adaptive bank: the frozen RL policy proposes settings and a deterministic shield checks each condition. DFE scoring is behavioral.";
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
    if (job.status === "complete") { renderDesign(job.result); selectTab("results"); showMessage("Circuit generated and evidence recorded.", "info"); return job.result; }
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
    if (!state.hardware) renderHardwareCheckpoint(await api("/api/hardware"));
    const design = await api("/api/demo");
    state.judgeMode = true; $("#judgeStrip").hidden = false; $("#judgeButton").textContent = "Judge mode active";
    renderDesign(design); selectTab("hardware");
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
  const targetPanel = $(".target-panel");
  const compactLayout = matchMedia("(max-width: 850px)");
  const positionControls = () => {
    if (compactLayout.matches) $(".explorer-scope").after(targetPanel);
    else $("#workspace").prepend(targetPanel);
  };
  compactLayout.addEventListener("change", positionControls);
  positionControls();
  const runDetails = document.createElement("details");
  runDetails.className = "details-card run-details";
  const runSummary = document.createElement("summary");
  runSummary.textContent = "Run verification and provenance";
  runDetails.append(runSummary, $(".verification-panel"));
  $("#resultsView").append(runDetails);
  selectTab(location.hash.slice(1) || "hardware", false);
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
    const requestedView = location.hash.slice(1);
    if (["results", "hardware", "pvt", "compare", "channel", "evidence"].includes(requestedView)) {
      selectTab(requestedView, false);
    }
  }
  catch (error) { showMessage(`The preverified design could not be loaded: ${error.message}`, "error"); }
}

document.addEventListener("DOMContentLoaded", init);
