# SerDes DSP Framework — State Analysis & Roadmap
*Design review + next-step mapping, 2026-07-18*

---

## 1. What exists today

### 1.1 Reference library (mapped)

| File | Identity | Role in this project |
|---|---|---|
| `High-Speed_Wireline_LinksPart_I_Modeling.pdf` | Shakiba, Tonietto, Sheikholeslami, IEEE OJ-SSCS 2024 (invited) | **Core methodology** — reference TX/RX model, channel compliance, equalizer modeling |
| `High-Speed_Wireline_LinksPart_II_...pdf` | Same authors, Part II | **Core methodology** — FFE/CTLE/DFE tap optimization, BER assessment |
| `Modelling (1).pdf` | Davide Menin PhD thesis, Univ. Udine 2021, "Modelling and Design of High-Speed Wireline Transceivers with Fully-Adaptive Equalization" | Adaptation-loop realism: joint AGC/CTLE/FFE/DFE convergence, interaction, stability |
| `EECS-2019-143.pdf` | Jaeduk Han PhD dissertation, UC Berkeley (Alon/Stojanović), "Design and Automatic Generation of 60Gb/s Wireline Transceivers" | BAG-style analog generation, TX/RX circuit implementation reference |
| `PAM4.pdf` | Intel AN-835 "PAM4 Signaling Fundamentals" (2019) | PAM-4 basics, measurement definitions (levels, EH/EW, RLM) |
| `PAM4 (1).pdf` | Zhang et al., Xilinx, DesignCon 2016 "PAM4 Signaling for 56G Serial Link Applications — A Tutorial" | Practical 56G PAM-4 link tradeoffs |
| `Introduction.pdf` | CERN "Introduction to PAM4" slides | Introductory material |
| `A (1).docx` | Substack-style article: "A Comprehensive Overview of High-Speed Optical Communications" (IM-DD → CPO → coherent → SiPh) | Optical track background (VCSEL, MZM, TIA, link budgets) |
| `wireline-video-links.docx` | Sheikholeslami wireline lecture series (YouTube) + **Toronto StatOpt** statistical link-analysis tool pages | StatOpt = template for the statistical BER engine this repo is missing |

The reference set clearly points at one methodology: **statistical (semi-analytic) link modeling + joint equalizer optimization**, à la OJ-SSCS Part I/II and StatOpt. The current codebase is pure brute-force time-domain — that is the biggest architectural gap.

### 1.2 Codebase inventory (~6.8k lines)

- `python_models/` — behavioral chain: channel (loss-model/S-param/IM-DD), PAM-4 TX, FFE/DFE/MLSE, MM & BB CDR, TI-ADC, coherent/IM-DD optical DSP, viz, `link_sim.py` harness. Plus a 690-line PyTorch `ml_equalizer.py` (LSTM/GRU/CNN + INT8 quantized inference), **not integrated** into `link_sim.py`.
- `rtl/` — 32-parallel FFE + speculative DFE + SS-LMS (`ffe_dfe_lms.sv`), BB-CDR + PRBS-31 BER checker (`bb_cdr_ber.sv`). Written, **never simulated/synthesized** (no logs, no results).
- `verification/tb_dsp_uvm.sv` — UVM TB skeleton covering 6 scenarios. **Never run.**
- `veriloga_models/`, `ams/`, `scripts/cadence/` — TIA, CTLE/VGA/ADC/VCO/PD Verilog-A + Spectre TB + Ocean PVT/MC scripts. **Requires Cadence; unverified.**
- `matlab_models/dsp_verify.m` — algorithm cross-check suite.
- No `results/`, no git repo, no unit tests, no S-parameter channel files. Stray literal directories `{python_models,veriloga_models,...}` from a failed bash brace expansion on Windows — delete.

---

## 2. Design-review findings (bugs & modeling gaps)

### Confirmed bugs
1. **Monte Carlo is a no-op.** `run_link()` (link_sim.py:96) calls `np.random.seed(42)` unconditionally, overriding the per-run seed set in `monte_carlo()` (link_sim.py:273). All 50 "MC runs" are bit-identical; the reported mean/std/worst statistics are meaningless.
2. **CDR is not in the datapath.** `MuellerMullerCDR` is imported and given `cdr_kp/cdr_ki` config, but `run_link()` never instantiates it. The simulated chain samples at ideal baud instants — timing recovery, sampling-phase error, and jitter tolerance are unmodeled, yet the README describes the chain as CTLE+ADC+FFE+DFE+CDR.
3. **CTLE placed before noise injection** (link_sim.py:124-135). AWGN is added *after* the CTLE, so CTLE noise enhancement — the central CTLE design tradeoff — is invisible. Noise must be injected at the channel output, then shaped by the CTLE transfer function.
4. **BER estimator is fragile.** `final_ber = last nonzero entry of ber_trace` — a single-window sample, not an aggregate over post-training symbols with a confidence interval.

### Modeling-fidelity gaps
5. **Baud-rate-only signal path.** Channel applied via `pulse_response(osr=1)` + `np.convolve(mode='same')`. No oversampled waveform through the AFE → no eye at the slicer, no sampling-phase sensitivity, no fractionally-spaced EQ in the main loop, `mode='same'` hides causality/cursor alignment.
6. **CTLE as a 3-tap baud-rate FIR** — cannot represent a real pole/zero peaking characteristic. Apply the actual 1-zero/2-pole transfer function in the frequency domain on the oversampled waveform.
7. **No jitter decomposition.** No RJ/DJ/SJ/SSC injection at TX or sampling clock; ADC aperture jitter is the only jitter in the model.
8. **No statistical engine.** Time-domain at 50k symbols floors out near BER 1e-4; no StatEye/COM-style semi-analytic BER, no bathtub extrapolation to 1e-15 equivalent, no way to run the Part-II style tap optimization efficiently.
9. **Power numbers are hardcoded constants** (0.8 mW/tap etc.) presented next to simulated metrics. Keep, but label as placeholder budget, not estimate.

### Spec inconsistencies (README)
10. **KP4 pre-FEC target is wrong.** README states "Pre-FEC target 2×10⁻²". KP4 RS(544,514) corrects 15 symbols; the accepted pre-FEC random-error BER threshold for 1e-15 post-FEC is **≈2.4×10⁻⁴** (802.3bs/cd). 2×10⁻² is soft-decision coherent-FEC territory. For the 224G track (802.3dj), the concatenated inner-Hamming(128,120)+KP4 scheme moves the pre-FEC operating point to the ~1e-3–5e-3 region — different spec line, state both explicitly.
11. **DFE speculation claim needs proof.** "Tap-1 speculation within 570 ps" at 32-way parallelism implies a 32-symbol unrolled speculative structure whose critical path must actually be characterized in synthesis, not asserted.

---

## 3. Roadmap

### Phase 0 — Hygiene ✅ DONE 2026-07-18 (commit ce733a8)
- [x] `git init`, baseline commit, `.gitignore`; stray brace-expansion dirs deleted.
- [x] MC seeding: all randomness now flows from `LinkConfig.seed` via `np.random.Generator`.
- [x] BER estimator: post-training error count + Wilson 95 % upper bound (`ber_wilson_upper`).
- [x] README FEC row corrected (2.4e-4 KP4; 802.3dj concatenated note).
- [x] pytest suite (48 tests incl. Phase 1).
- Bugs found *by* Phase 0 beyond the audit list: scrambler was not self-synchronising
  (fed back input, not output); MLSE trellis had inconsistent state encoding (SER 0.7 → 5e-4);
  PAM-4 BER theory 2× high; TX returned pre-scrambler bits as reference.

### Phase 1 — Model fidelity ✅ DONE 2026-07-18
- [x] Oversampled (OSR 8) waveform TX → channel `apply()` → AFE; cursor alignment by
      calibration pulse + cross-correlation (`estimate_delay`, negative lags included).
- [x] Real CTLE (1 zero / 2 poles, numerically calibrated peaking); noise injected at
      channel output *before* CTLE — noise enhancement verified by unit test.
- [x] CDR loop closed: pattern-gated **Alexander BB PD** (T/2 interpolated mid-samples)
      + PI loop with gear-shifted acquisition and integrator clamp; ppm offset tracked.
      (Design note: sign-MM locks to the eye EDGE on low-ISI pulses — h(−1)=h(+1)
      equilibrium — verified in sim; MM belongs post-FFE with an h(+1) target → Phase 3.)
- [x] Jitter: TX RJ + SJ via phase-warped resampling; RX aperture RJ + TI timing/gain/offset
      mismatch at the sampling instant. JTOL sweep mode added (corner ~1–3 MHz, 0.1 UI floor).
- [x] MMSE warm start fixed: cursor placed at the FFE's n_pre (was centred → 7-symbol
      reference misalignment); Wiener gain preserved; full-cyclic peak search.
- [x] Bring-up sequencing: DSP adaptation held until after CDR acquisition (`adapt_start`).
- [ ] Deeper alignment with OJ-SSCS Part I reference model (carried into Phase 2 —
      natural to do together with the statistical engine calibration).
- Validation: SNR waterfall monotone, 0 errors at 28 dB (3 cm); loss sweep degrades
  monotonically, lock lost ≥30 dB with 6 dB CTLE (expected — needs AFE/EQ co-design);
  MC runs now statistically independent; SS-LMS + 6b ADC + TI mismatch + jitter form
  the measured implementation penalty vs no-ISI theory.

### Phase 2 — Statistical engine ✅ CORE DONE 2026-07-18 (`statistical_eye.py`)
- [x] Semi-analytic BER: exact ISI PMF (4-point shifts per tap, O(taps·grid)),
      correlated-noise sigma through CTLE+FFE (wᵀRw, not white), ideal-DFE
      post-cursor cancellation, per-boundary Gray BER, horizontal bathtub,
      Gaussian RJ folding, eye width @ 1e-6/1e-12. Reduces to (3/4)Q(1/σ) on a
      clean channel (unit-tested).
- [x] Cross-validation: engines agree within ~3× across BER 1e-1…1e-4 on the
      3 cm channel (fig5_crossval.png); statistical is mildly conservative
      (reference-receiver assumptions) — documented.
- [x] Part II-style optimization (`optimize_ctle`, CLI `--mode optimize`):
      CTLE peaking × (MMSE FFE + ideal DFE) against statistical BER, **subject
      to a CDR timing-feasibility constraint**.
      **Key finding:** the unconstrained slicer optimum on dispersive channels
      is 0 dB CTLE (long FFE equalizes with less noise boost than analog
      peaking) but that config is unlockable — the BB PD's zero crossings are
      pattern-smeared. New metric `crossing_jitter_ui()` (edge-ISI / edge-slope)
      calibrated against time-domain lock outcomes: healthy < 0.45 UI, lock
      boundary ≈ 0.6–0.75 UI. In this architecture the CTLE's primary job is
      timing health, not slicer margin.
- [ ] Full COM (IEEE 802.3 Annex 93A) as a compliance metric.
- [ ] Real `.s4p` channels (802.3ck/dj public packages) — needs scikit-rf
      installed + channel files; `Channel.from_sparam` is ready.
- [ ] OJ-SSCS Part I reference-model alignment (joint TX-FFE optimization,
      their Section IV/V structure).

### Phase 3 — Adaptation realism + bit-true model
- [x] **3a (2026-07-18): post-FFE MM phase detector** (`cdr_arch='mm_postffe'`,
      commit pending): MM PD behind a FROZEN MMSE timing-path FFE (production
      arrangement; freezing sidesteps the FFE↔CDR tap-rotation degeneracy for
      now). Sign lesson: E[MM product] ∝ h(+1)−h(−1) ⇒ raw sign locks 0.5 UI
      off-centre in this loop convention; negated and verified.
      Results: locks at 6 cm/0 dB CTLE (Alexander-infeasible) and 10 cm/6 dB
      (Alexander lock-lost); CDR jitter flat ~20 mUI across ALL CTLE settings
      vs 28–75 mUI for Alexander (fig8) — timing decoupled from AFE tuning.
- [x] **ADC clipping discovered as the real 0-dB limiter**: 17 % of samples
      clip at 6 cm/0 dB (peaks 7.65 vs ±4 full scale) → BER 2e-2 for BOTH
      architectures; explains the statistical(1.3e-5)-vs-time-domain(2.2e-2)
      gap at that point. `clip_probability()` added to the statistical engine,
      `adc_clip_frac` reported by run_link, clip constraint (<12 %, calibrated)
      added to `optimize_ctle`. **Refined conclusion: CTLE is needed for
      timing health (Alexander arch) AND ADC dynamic range (any arch).**
- [ ] Fold clipping distortion into the statistical BER itself (currently a
      constraint, not a penalty).
- [ ] TRUE joint adaptation per Menin thesis: LMS + CDR + AGC running
      simultaneously with bandwidth separation; demonstrate tap-walking and
      its mitigation (tap re-centring); dLev-based adaptive slicer.
- [ ] Bit-true fixed-point Python model matching the README fixed-point table
      exactly (Q2.8 coeffs, 16-bit LMS accumulator) — golden model for RTL.

### Phase 4 — RTL verification: run what's written (2–4 weeks)
- [ ] Get `ffe_dfe_lms.sv` + `bb_cdr_ber.sv` through an actual simulator (Verilator/Icarus for free, Xcelium if available); the UVM TB has never executed.
- [ ] Golden-model co-sim: vector files or cocotb from the Phase-3 bit-true model; FFE/DFE/LMS bit-exact equivalence.
- [ ] Synthesis trial at 1.75 GHz 28nm (or open PDK proxy) to substantiate the speculative-DFE timing claim.

### Phase 5 — Extensions (after the core is trustworthy)
- [ ] 224G config: 106.25 GBd PAM-4, stronger RX-FFE, MLSE/MLSD path (the `MLSE` class exists — benchmark vs DFE at 224G ISI), concatenated FEC operating point.
- [ ] Integrate `ml_equalizer.py` as a selectable receiver in `link_sim.py`; benchmark vs FFE/DFE and MLSE at equal complexity (MAC/symbol), not just equal BER.
- [ ] Optical IM-DD track: complete link budget with RIN/shot/thermal-TIA noise partition, tie `A (1).docx` + Verilog-A TIA into the Python chain; CPO short-reach config.

### Sequencing rationale
Phases 1–2 before any RTL work: the RTL and UVM code verify an architecture whose system-level parameters (tap counts, bit widths, CDR gains) currently rest on a simulation with the four bugs above. Fixing the model first prevents verifying the wrong spec.
