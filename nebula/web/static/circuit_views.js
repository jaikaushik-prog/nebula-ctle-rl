/* Connectivity guides, not generated netlists or a new simulation.
 * Named instances refer to the SHA-pinned Entry 143 transistor deck.
 * Keep the exact device sheet as the terminal-level source of truth.
 */
"use strict";
const NebulaCircuitViews = (() => {
  const escapeText = (value) => value.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
  const text = (x, y, value, cls = "") =>
    `<text x="${x}" y="${y}" class="${cls}">${escapeText(value)}</text>`;
  const wire = (d, feedback = false) =>
    `<path d="${d}" class="circuit-wire${feedback ? " circuit-feedback" : ""}"/>`;
  const box = (x, y, w, h, title, detail = "") =>
    `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="5" class="circuit-box"/>` +
    text(x + 14, y + 28, title, "circuit-label") +
    (detail ? text(x + 14, y + 52, detail, "circuit-small") : "");
  const resistor = (x, y, label) => wire(`M${x} ${y}h15m50 0h15`) +
    `<rect x="${x + 15}" y="${y - 8}" width="50" height="16" class="circuit-component"/>` +
    text(x + 2, y - 18, label, "circuit-small");
  const mos = (x, y, label, gate, pmos = false) =>
    wire(`M${x + 45} ${y - 30}v15h-15v30h15v15M${x + 24} ${y - 15}v30M${x} ${y}h24`) +
    (pmos ? `<circle cx="${x + 18}" cy="${y}" r="4" class="circuit-component"/>` : "") +
    text(x + 56, y + 5, label, "circuit-small") +
    text(x - 8, y + 4, gate, "circuit-small circuit-gate");
  const capacitor = (x, y, label) => wire(`M${x} ${y}h25m10 0h25M${x + 25} ${y - 14}v28M${x + 35} ${y - 14}v28M${x + 16} ${y + 20}l30 -40`) +
    text(x - 10, y - 29, label, "circuit-small");
  const frame = (title, body) =>
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1040 340" role="img" aria-label="${title}"><title>${title}</title>${body}</svg>`;

  const views = {
    dfe: {
      label: "1-tap DFE",
      description: "The CTLE drives a real transistor summer. Two clocked CML latches hold the decision; df_q / df_qb steer the current DAC back into sum_p / sum_n. Tap code 2 is the calibrated setting. Clock and bias wiring are condensed here.",
      svg: frame("Transistor DFE: summer, master/slave memory and current feedback",
        text(25, 92, "CTLE output", "circuit-label") + text(25, 117, "outp / outn", "circuit-small") +
        wire("M25 145H185M375 145H450M640 145H715M905 145H1010") +
        box(185, 100, 190, 90, "CML summer", "Xdfe_sump / sumn") +
        box(450, 100, 190, 90, "Master latch", "Xdf_m* devices") +
        box(715, 100, 190, 90, "Slave latch", "Xdf_s* devices") +
        text(380, 82, "sum_p / sum_n", "circuit-small") +
        text(648, 82, "df_mp / df_mn", "circuit-small") +
        text(915, 127, "df_q / df_qb", "circuit-small") +
        wire("M545 45V100M810 45V100", true) +
        text(453, 33, "External complementary clock", "circuit-small") +
        box(450, 240, 350, 76, "Switched-current feedback DAC", "Xdfe_dacp / dacn + 4 weighted branches") +
        wire("M962 145V278H800M450 278H280V190", true) +
        text(310, 265, "Feedback current", "circuit-small") +
        text(818, 265, "Held decision", "circuit-small")),
    },
    attenuator: {
      label: "Attenuator",
      description: "One half of the differential attenuator is shown; the iny-to-inn half mirrors it. A series poly resistor feeds three resistor-plus-PMOS shunts to the input common-mode node. All three shunts are enabled in code A7; they are not the Rs/Cs controls.",
      svg: frame("PMOS input attenuator, positive half with three shunt branches",
        text(35, 37, "Positive input half", "circuit-label") +
        wire("M35 85H160M240 85H940M360 85V115M570 85V115M780 85V115") +
        text(35, 73, "inx", "circuit-small") + text(935, 73, "inp to CTLE", "circuit-small") +
        resistor(160, 85, "Xatt_sp") +
        [360, 570, 780].map((x, i) =>
          wire(`M${x} 115v15m0 38v17M${x} 245v45`) +
          `<rect x="${x-8}" y="130" width="16" height="38" class="circuit-component"/>` +
          text(x + 20, 151, `Xatt_rp${i}`, "circuit-small") +
          mos(x - 45, 215, `Xatt_swp${i}`, "gate = 0", true)).join("") +
        wire("M300 290H860") + text(875, 295, "cm", "circuit-label") +
        text(35, 325, "Mirrored negative half: iny -> Xatt_sn -> inn; Xatt_rn0..2 / Xatt_swn0..2", "circuit-small")),
    },
    ctle: {
      label: "CTLE core",
      description: "The SKY130 input pair converts inp / inn into differential output voltage through poly loads. Rs/Cs connect the source nodes s1 and s2. Tail devices use the physical bias reference; open Rs/Cs controls for the reconfigurable degeneration network.",
      svg: frame("CTLE differential pair and configurable source degeneration",
        text(30, 36, "Source-degenerated differential pair", "circuit-label") +
        wire("M350 55H735M395 55V80M695 55V80M395 116V140M695 116V140") +
        text(540, 42, "VDD", "circuit-small") +
        '<rect x="387" y="80" width="16" height="36" class="circuit-component"/><rect x="687" y="80" width="16" height="36" class="circuit-component"/>' +
        text(310, 102, "Xrlp", "circuit-small") + text(726, 102, "Xrln", "circuit-small") +
        wire("M395 130H215M695 130H900") + text(215, 120, "outp", "circuit-small") + text(853, 120, "outn", "circuit-small") +
        mos(350, 170, "XM1", "inp") + mos(650, 170, "XM2", "inn") +
        wire("M395 200V220H450M695 200V220H640M395 220V245M695 220V245") +
        box(450, 194, 190, 64, "Configurable Rs/Cs") +
        text(407, 210, "s1", "circuit-small") + text(659, 210, "s2", "circuit-small") +
        mos(350, 275, "XMT1", "nbias") + mos(650, 275, "XMT2", "nbias") +
        wire("M395 305V320H695V305") +
        text(505, 336, "Tail return to ground", "circuit-small")),
    },
    rc: {
      label: "Rs/Cs controls",
      description: "Rs changes through the NMOS gate voltage; Cs changes through the varactor bias voltage. These are external electrical controls on one circuit, not a menu of fixed passive netlists. This page inspects the saved calibration only; different voltages require fresh SPICE checks and do not inherit its 45/45 result.",
      svg: frame("Configurable Rs parallel branches and paired Cs varactors",
        text(25, 35, "Rs: fixed branch + voltage-controlled branch", "circuit-label") +
        text(570, 35, "Cs: two bias-controlled varactors", "circuit-label") +
        wire("M40 85H195M275 85H490M60 85V205H105M465 85V205H440") +
        text(30, 73, "s1", "circuit-small") + text(473, 73, "s2", "circuit-small") +
        resistor(195, 85, "Xrc_rmax") + resistor(105, 205, "Xrc_branch") +
        wire("M185 205H285M345 205H440M315 218V259", true) +
        '<path d="M285 193v24M345 193v24M285 205l60 -12M300 218h30" class="circuit-wire"/>' +
        text(259, 169, "Xrc_switch (NMOS)", "circuit-small") +
        text(234, 280, "rc_gate <- filtered rctrl", "circuit-small") +
        text(38, 322, "Gate feed: Xrc_rfeed + Xrc_rbypass", "circuit-small") +
        wire("M580 130H650M710 130H775M775 130H835M895 130H995M775 130V235") +
        capacitor(650, 130, "Xrc_var_s1") + capacitor(835, 130, "Xrc_var_s2") +
        text(580, 116, "s1", "circuit-small") + text(978, 116, "s2", "circuit-small") +
        text(783, 166, "rc_ct", "circuit-small") +
        box(630, 235, 305, 65, "Filtered cctrl + AC bypass") +
        text(570, 322, "Bias feed: Xrc_cfeed + Xrc_cbypass", "circuit-small")),
    },
  };

  function mount(checkpoint) {
    const buttons = document.getElementById("circuitViewButtons");
    buttons.replaceChildren();
    function select(key, scroll = false) {
      const view = views[key];
      document.getElementById("circuitViewCanvas").innerHTML = view.svg;
      let description = view.description;
      if (key === "rc") {
        const c = checkpoint.controls;
        description = `Saved calibration: Rs control ${c.r_control_v_nominal.toFixed(3)} V (${c.r_fraction} VDD); Cs control ${c.c_control_v_nominal.toFixed(3)} V (${c.c_fraction} VDD). ` + description;
      }
      document.getElementById("circuitViewDescription").textContent = description;
      for (const button of buttons.children) button.setAttribute("aria-pressed", String(button.dataset.circuit === key));
      if (scroll) {
        buttons.querySelector(`[data-circuit="${key}"]`).focus({preventScroll: true});
        document.querySelector(".circuit-inspector").scrollIntoView({behavior: "smooth", block: "start"});
      }
    }
    for (const [key, view] of Object.entries(views)) {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.circuit = key;
      button.textContent = view.label;
      button.addEventListener("click", () => select(key));
      buttons.append(button);
    }
    document.getElementById("inspectRcButton").onclick = () => select("rc", true);
    select("dfe");
  }
  return {mount};
})();
