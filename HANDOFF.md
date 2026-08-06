# HANDOFF.md — Living Project State & Continuation Guide

> **READ THIS FIRST.** This file is the single source of truth for project
> state. It exists so that ANY person or AI agent picking up this repository —
> at any point, with zero prior context — knows what this project is, what has
> been done, why every non-obvious decision was made, what the current state
> is, and what to do next.
>
> **THE RULE: if you change this repository, you update this file in the same
> commit.** Add a dated entry to the Session Log (bottom), update the Current
> State and Next Steps sections if they changed, and add any new gotcha you
> discovered to the Gotchas section. A change without a handoff update is an
> incomplete change.

Last updated: **2026-08-06** (session 12a: **`cl` has a physically derived
range, and every corner number this project has published was measured
1.92x above the top of it.** `cl` was pinned at 150 fF because that maximised
the S3 yield among five values tested — `CL_SENSITIVITY.md` §6 flagged that as
choosing the answer. Deriving it instead from what actually loads the CTLE
output (the 1-tap DFE summer input pair + the slicer input pair + routing)
gives **cl_lo 13.64 fF, cl_mid 32.63 fF, cl_hi 78.04 fF — a 5.72x range, 2.52
octaves**, entirely below the 150 fF pin. 180 SPICE runs, 16 s. Three results:
(1) **`@m[cgg]` is NOT the gate load — it understates it 1.9-2.7x** by
excluding the overlap capacitance and the Miller multiplication of C_gd, so
the load is measured as the AC current the driver must supply into the gate,
cross-checked against the primitives to 1.0% median (**G50**); (2) **the
sizing sketch moves the load 5.9x while the process corner moves it 1.16x**,
so the range is wide because the next stage is undesigned, not because silicon
varies — and **the corner that loads the node most (`fs`) is the one with the
LEAST gm**, the inverse of the device ordering; (3) a **half-rate front end
gives cl_hi = 141.8 fF**, i.e. the 150 fF pin was the right number for a
topology S2 does not describe. Full write-up `nebula/CL_RANGE.md`;
`params.py` untouched (rule 6) and §8 of that file is the proposal.
**528 -> 591 green** (+63: `test_cap_probe.py` 36, `test_cl_range.py` 27).
`nebula/PREDICTIONS.md` is new and carries the pre-registered prediction for
session 12b, committed before that experiment runs.
Earlier session 11 + 11b: **corner robustness is not a
property of where a design sits in the parameter BOX; it is a property of where
it sits in the SPEC WINDOW** — 7560 SPICE runs, 23 min, re-simulating 10d's
population from its seed and reproducing 10d's counts exactly. Splitting the
255 nominal winners into the 155 corner-robust and the 100 corner-fragile:
**every box coordinate is a null** (q > 0.16, and the two purpose-built
interiority statistics are the LEAST significant rows at q = 0.98), so the
"robust designs are interior in the box" hypothesis is **FALSIFIED**; but
**both S3 axes separate the groups once FOLDED onto distance-to-nearer-edge**,
and neither does before — f_peak margin **0.325 vs 0.126 octaves**
(p = 2.8e-12), peaking margin **2.70 vs 0.86 dB** (p = 3.2e-11), while the raw
medians are identical to four figures. The methodological lesson, which is the
transferable part: **a two-sided spec makes its own raw coordinate
uninformative**, because top-edge and bottom-edge failures sit on opposite
sides of any median and cancel. The usable output is a **joint filter — f_peak
margin >= 0.133 oct AND peaking margin >= 1.0 dB gives 92.1% [86.5, 95.6]
corner-robust against a 60.8% base rate**, keeping 140 of 255; either alone
reaches only ~75%, and both come free from an AC run the evaluator already
does. Proposal only, for the SEARCH — `params.py` untouched (rule 6), and
`ROBUST_GEOMETRY.md` §7 lists the three caveats a human must weigh (ideal tail,
in-sample thresholds, and that a 1 dB peaking margin bans the endpoints of
S3's own tunable range). Also: **f_peak is quantised at 0.0664 octaves** by
`meas ac MAX` on an `ac dec 50` grid, so the one-octave window holds exactly 15
distinct values and finer margins quote the sweep setup. Full write-up
`nebula/ROBUST_GEOMETRY.md`. **481 -> 528 green** (+47, all
`test_robust_geometry.py`; verified twice in 11b, 98 s and 95 s).
Session 11b landed it as `de874db`, which also carries the sessions **10c and
10d work that had never been committed** (the G44 peak-detector fix,
`s9_yield.py`, `S9_YIELD.md`), and restores §9's gotchas, which an earlier
commit had truncated from ~415 lines to 77. See G49.
Earlier session 10d: **the corner-robust yield is
measured — 20 205 SPICE runs, 47 min.** The same 1890 designs give **13.49% at
TT/27C, 8.20% [7.05, 9.52] across three corners, 8.10% [6.95, 9.41] across all
45**, and cross-tabulating design by design shows **100 of the 255 nominal
winners (39.2%) fail at a corner**, with 0 going the other way. Quote it as a
**tax on the baseline**, not as a coupled constraint — S9 was listed as the
cheapest route to replacing the argument G40 retired, and it did not deliver
one. What it did deliver is three reusable results: **three corners are worth
98.7% of forty-five** and the screen can only ever be wrong in one direction,
so budget the RL reward at 3-5 corners and put the full sweep in a verification
tier (G47); **the worst corner is FAST-hot, not slow-hot**, because S3 is a
two-sided spec and its two edges sit on opposite sides of the process axis
(G46); and **11 cores buy 3.2x, not 11x** — ~100 ms per corner evaluation, flat
past 8 workers (G48). Health: 0 hard failures, 0 retries, 0 screen/promotion
mismatches. **All of it is an OPTIMISTIC bound because the tail is still two
ideal current sinks**, which is why the tail transistor is now the top open
item in §8. Full write-up `nebula/S9_YIELD.md`; `params.py` untouched (rule 6).
444 (session 10b) -> **481 green**, of which
29 are `nebula/tests/test_s9_yield.py`. See G46, G47, G48.
Earlier session 10b: **`cl` is a BAD SEARCH DIMENSION —
removing it from the search RAISES the S3 yield.** Pinning `cl` at 150 fF and
holding every other bound takes the random-search yield from
**8.73% [7.54, 10.09] to 13.54% [12.08, 15.16]**, disjoint 95% intervals, on
2000 paired LHS samples. The optimum is bracketed (50/100/150/250/400 fF gives
8.73/11.27/13.54/12.06/9.52%), so 150 fF is a real interior maximum, though not
separable from 250 fF at this n. Mechanism: `cl` trades peak MAGNITUDE against
peak LOCATION and location wins up to ~150 fF, after which the load pole stops
relocating peaks and starts extinguishing them. **Second result, and it
sharpens G40:** the RAW coupling factor falls 1.05 -> 0.68 across the sweep
while the conditional-on-a-peak one stays flat at 0.97-1.06 with **every one of
the five 95% intervals covering 1.00** — so the raw statistic is unstable and
contaminated, and there is no measured coupling anywhere. **Third, and it must
not be buried: this makes G3 HARDER**, because the random-search baseline RL
has to beat rises from ~11 samples per hit to ~7.
Full write-up `nebula/CL_SENSITIVITY.md`; `params.py` untouched (rule 6).
430 -> **444 green**. See G42, G43.
**All coupling numbers above are POST-G44-FIX (session 10c) and supersede the
first pass**, which reported a 1.10x [1.02, 1.20] adverse effect at 100 fF —
an artifact of a peak detector that counted sweep-edge maxima as real and
inflated the has-peak population by up to 42%. The S3 yields themselves barely
moved. See G44 (fixed) and G45 (transient ngspice failures under load).
Earlier session 10a: **this checkout is a git repository
again, and for the first time its history is CLEAN of the copyrighted PDFs.**
Session 9d ended with a note that `git init` had never been run here, so the
"update HANDOFF in the same commit" rule could not be honoured mechanically.
It is now: `main`, one initial commit, 102 files, committed as
`Jai Kaushik <jaikaushik-prog@users.noreply.github.com>` (G12). The ten
reference PDFs/DOCXs are gitignored and were verified absent from the index
BEFORE committing, which means G1's "a public version must strip them from
HISTORY" no longer applies to this tree — there is nothing to strip. Tests
430 green before and after (nothing executable changed). See G41.
Earlier session 9d: the START HERE item is CLOSED. Bounds
re-derived on the corrected 1.8 V SKY130 bias and the S3 yield re-run —
**8.73%**, not 5.3%. But the headline is a **negative result: the "S3 is a
coupled constraint" argument is falsified.** Measured as a box-independent
statistic — P(A)·P(B) vs P(A and B) across three box widths — the **coupling
factor is 1.04x**, i.e. the two S3 conditions are INDEPENDENT. The low yield is
just one low marginal (f_peak lands in-window 16% of the time). That sentence
must not go in the abstract. Also: `2*I*RL` understated the available swing
~2x and the real limit is current steering, not headroom (measured 1.43 Vpp
linear / 2.28 Vpp ceiling); the compression verdict was partly a fixed-boost
artifact; a 3.3 V device is rejected on f_T; and `nf` does NOT multiply width
on SKY130. Full write-up: `nebula/BOUNDS_REDERIVATION.md`.
407 -> **430 green**. Earlier session 9: CLAUDEwa.md corrected in four places
(§6 body effect, §3 binding constraints, new §8 rule 9, bound provenance);
the §6 cross-check moved out of `.control` into Python where it can actually
fail, with captured-output fixtures and a falsifiability test; **SKY130
installed and simulating via volare — G29 cleared**, and it independently
re-confirms the body-effect finding with gmbs/gm = 0.40; NRZ retarget fixes
1-3 landed behind a `modulation` flag. Then 9b: `alter` proved silently wrong
for device geometry, and a **trimmed SKY130 library** cut an ngspice run from
16-35 s to 0.42 s, bit-identical. Then 9c (hand-sizing at the terminal): the
G1 bias point was found **badly mis-biased at gm/I_D = 1.7** with the sources
below ground; corrected to gm/I_D = 8.4, which moves DC gain from -6.4 dB to
+5.1 dB and makes **compression, not noise, the binding problem**.
315 nebula + 92 existing = **407 green** (+2 slow, deselected by default).
Earlier session 8: G1 hand-design audited against
ngspice — §6's gain equation found to fail its own gate without the body-effect
term; parameter bounds measured at 5.3% S3 yield and two bound errors fixed;
SKY130 blocker precisely diagnosed. 267 nebula + 65 existing = 332 green.
Earlier session 7 + addendum: Nebula G0 gate PASSED —
ngspice 41 in a conda env, all four analyses run; `.disto` found unusable for
BSIM4, HD3 must come from transient+FFT (175x cost spread across fidelity
tiers, measured). Link-layer compression bug and channel DC-loss
inconsistency both fixed; reference sizing verified against S8. 255 nebula
tests + 65 existing = 320 green.)

---

## 1. What this project is

A **simulation and design framework for a 112G PAM-4 SerDes receiver** —
the chip-to-chip link technology used in AI datacenters (56 Gbaud, 4-level
signaling, ADC-based DSP receiver, 28 nm CMOS reference parameters).

- **Owner:** Jai Kaushik, BITS Pilani EEE undergraduate
  (GitHub: `jaikaushik-prog`; commits use `jaikaushik-prog@users.noreply.github.com` — see Gotcha G12).
- **Supervisor:** research professor at BITS Pilani who provided the original
  materials (papers + starter code). The professor receives progress via
  figures + explanations; the owner is a **beginner in this domain** — when
  working with them, explain changes in plain language, one at a time.
- **Origin:** the owner received a folder of research papers, video links, and
  a starter codebase (~6.8k lines) built by previous students. The starter
  code looked complete but contained many correctness bugs (see §5).
- **Long-term goal (scope deliberately open):** a credible link-design
  methodology + verified RX DSP architecture; potential thesis/paper; possible
  scaled FPGA/shuttle demonstrator. NOT a competitive commercial PHY (that
  requires a large team and advanced nodes — documented expectation).
- **NEW DIRECTION (2026-07-23) — UCIe group project.** The professor pointed the
  owner at `hussin-mohamed/UCIE_GP` (a UCIe 3.0 *logical/digital* PHY: RTL +
  UVM — link-training FSM, sideband, TX path with byte-to-lane + LFSR scramble
  + serializer, RX path). That repo **explicitly excludes the analog front-end**
  (no channel/driver/CTLE/FFE/DFE — "signal integrity and channel modeling out
  of scope"). The group's task is to **build the analog electrical PHY around
  it**, split into 6 parts: (1) channel (2) serializer (3) driver (4) CTLE
  (5) DFE (6) FFE. **The owner has taken FFE.** Professor confirmed the target
  is the **high-data-rate DSP-equalization regime** (NOT light UCIe short-reach
  NRZ) — so this framework's 112G PAM-4 DSP-RX context IS the intended context,
  and `equalizers.py` (FFE/DFE joint LMS) + `pam4_chain.py` (TX-FFE) are the
  starting points. See §8 item 0 and Session 5.
- **GitHub:** https://github.com/jaikaushik-prog/serdes-dsp-framework —
  **PRIVATE, and must stay private** (contains copyrighted PDFs, see G1).

## 2. Repository map (what every file/folder is)

```
├── .gitignore              ← sectioned BY REASON (copyright / redistribution /
│                             regenerable), not by extension. Keeps the ten
│                             copyrighted reference PDFs out of history (G1,
│                             G41) and the SKY130 tree out of the repo. One
│                             explicit `!` un-ignore: our own trimmed library.
├── HANDOFF.md              ← this file. Update it every session.
├── CLAUDE.md               ← instructs AI agents to read + maintain HANDOFF.md
├── CLAUDEwa.md             ← NEW (2026-08-03). Contract for the **Nebula**
│                             competition track (Astera Labs x BITS Goa,
│                             RL-driven CTLE sizing, 5 Gbps PCIe Gen2).
│                             Separate project; own spec table, gates and
│                             rules. Read it in full before touching nebula/.
├── README.md               ← user-facing docs: structure, quickstart, params
├── docs/ROADMAP.md         ← full audit of the original code + phased plan
│                             with per-phase completion status. Keep in sync.
├── python_models/          ← THE CORE. All validated work lives here.
│   ├── pam4_chain.py       TX: PRBS (LFSR), self-sync scrambler (x^58+x^39+1),
│   │                       Gray mapping, TX-FFE, tx_waveform() = oversampled
│   │                       waveform w/ TX bandwidth pole + RJ/SJ jitter
│   ├── channel.py          PCB-trace loss model (skin+dielectric), S-param
│   │                       import hook (unused; needs scikit-rf), apply() =
│   │                       frequency-domain waveform filtering, PAM4 BER theory
│   ├── rx_frontend.py      CTLE (1z/2p, calibrated peaking), AGC, CDRSampler:
│   │                       closed timing loop, TWO architectures (see §6),
│   │                       TI-ADC mismatch + quantization at the sampling
│   │                       instant, estimate_delay() cross-correlator
│   ├── equalizers.py       FFE + DFE (joint single-pass LMS receiver), MMSE
│   │                       warm start (mmse_init_ffe), MLSE (Viterbi),
│   │                       fractional FFE, adaptive thresholds
│   ├── adc_model.py        Standalone ADC characterization (ENOB/SINAD, TI
│   │                       spurs). NOTE: the LINK uses the sampler's inline
│   │                       quantization, not this file's convert() chain.
│   ├── statistical_eye.py  Semi-analytic BER engine (StatEye-class): exact ISI
│   │                       PMF, correlated-noise w'Rw, bathtub, RJ folding,
│   │                       crossing_jitter_ui() CDR-feasibility metric,
│   │                       clip_probability(), optimize_ctle()
│   ├── link_sim.py         Top harness. LinkConfig dataclass = single source
│   │                       of config for BOTH engines. Modes: single,
│   │                       sweep_snr, sweep_loss, monte_carlo, jtol,
│   │                       statistical, optimize. CLI flags incl. --cdr_arch.
│   ├── make_report_figures.py  Generates figs 1-8 into results/ from sweep
│   │                       CSVs (caches some; delete CSV to force recompute)
│   ├── modulation.py      NEW (2026-08-04). The symbol alphabet as ONE object
│   │                       (PAM4 | NRZ). Every alphabet-dependent constant is
│   │                       DERIVED from `levels` — mean_square, max_level,
│   │                       symbol_probability, rms — so PAM-4's E[a^2] comes
│   │                       out at exactly the 5.0 that used to be hard-coded.
│   │                       Default is PAM4 everywhere; that is what keeps the
│   │                       existing suite green. NOTE only crossing_jitter_ui
│   │                       reads it so far — see NRZ_RETARGET_AUDIT.md.
│   ├── ml_equalizer.py     PyTorch LSTM/GRU/CNN equalizers. NOT INTEGRATED,
│   │                       NOT VALIDATED. Future work (needs equal-complexity
│   │                       benchmark vs FFE/DFE/MLSE).
│   ├── optical_dsp.py      IM-DD + coherent DSP models. NOT AUDITED YET.
│   ├── cdr.py              Standalone CDR study models (older). The LINK uses
│   │                       rx_frontend.CDRSampler, not these. Partially
│   │                       superseded; keep for reference.
│   ├── visualization.py    Older plotting helpers. Partially superseded by
│   │                       make_report_figures.py. NOT AUDITED.
│   └── results/            Generated CSVs + PNGs (gitignored). Regenerate:
│                           run sweeps then make_report_figures.py
├── nebula/                 NEW (2026-08-03). The Nebula competition track:
│   ├── BOUNDS_REDERIVATION.md  NEW (2026-08-04). Closes the START HERE item:
│   │                       the 1.8 V box with per-edge provenance, the 8.73%
│   │                       yield, the measured output swing, the fixed-vs-
│   │                       matched boost comparison, the 3.3 V rejection —
│   │                       and §4, which RETRACTS the coupled-constraint
│   │                       argument. Read §4 before writing any deliverable.
│   ├── CL_SENSITIVITY.md   NEW (2026-08-04). What `cl` does to the S3 yield,
│   │                       measured by pinning it. Removing cl from the search
│   │                       RAISES yield 8.73% -> 13.54%; the optimum is
│   │                       bracketed at ~150-250 fF. Also the cleanest
│   │                       demonstration that a RAW coupling factor tracks the
│   │                       no-peak fraction (G43). Read §5 before touching the
│   │                       action space and §7 before quoting any coupling
│   │                       number.
│   ├── CL_RANGE.md         NEW (2026-08-06, session 12a). Where `cl` comes
│   │                       from. Derives it from the gate load of the stages
│   │                       the CTLE drives instead of pinning it at the
│   │                       yield-maximising 150 fF: **13.64 / 32.63 /
│   │                       78.04 fF, a 5.72x range** whose TOP is 1.92x below
│   │                       the value every published corner number used.
│   │                       Read §2 before measuring any gate capacitance
│   │                       (`@m[cgg]` is not it, G50), §3 for what actually
│   │                       moves the load (the sketch, not the corners), and
│   │                       §9 before quoting a yield derived from it.
│   ├── PREDICTIONS.md      NEW (2026-08-06). Pre-registered predictions,
│   │                       committed BEFORE the experiment they are about,
│   │                       with the outcome written in afterwards whichever
│   │                       way it went. Entry 1 predicts a near-ZERO
│   │                       corner-and-load-robust yield, against the stated
│   │                       expectation of 8.73-13.54%. Precedent: G40 and
│   │                       10b's failed f_p2 prediction.
│   ├── S9_YIELD.md         NEW (2026-08-05). Corner-robust yield: 3-corner
│   │                       screen -> 45-corner promotion, with CIs, the
│   │                       measured parallel speedup, and — the actual
│   │                       headline — WHICH SPEC FAILS FIRST at each corner
│   │                       and by how much. 13.49% at TT -> 8.20% at 3
│   │                       corners -> 8.10% at 45, so **39% of nominal
│   │                       winners are corner-fragile** (§4), three corners
│   │                       are worth 98.7% of forty-five (§3, G47), and the
│   │                       worst corner is fast-hot not slow-hot (G46).
│   │                       Read its assumptions section first: the tail is
│   │                       still ideal, so every corner spread in it is an
│   │                       UNDERSTATEMENT.
│   ├── ROBUST_GEOMETRY.md  NEW (2026-08-05, session 11). WHERE the
│   │                       corner-robust designs live. Splits 10d's 255
│   │                       nominal winners into the 155 robust and 100
│   │                       fragile and asks what separates them. Answer:
│   │                       **not the parameter box (every coordinate is a
│   │                       null, q > 0.16, and the two interiority statistics
│   │                       are the LEAST significant rows at q = 0.98) but
│   │                       the SPEC WINDOW** — and only once both S3 axes are
│   │                       FOLDED onto distance-to-nearer-edge, because raw
│   │                       f_peak and raw peaking carry no information at all
│   │                       (identical medians). Joint filter f_peak margin
│   │                       >= 0.133 oct AND peaking margin >= 1.0 dB gives
│   │                       92.1% corner-robust vs a 60.8% base rate. Read §7
│   │                       before touching the reward shape, and §0 first:
│   │                       it is a RE-SIMULATION (G49), thresholds are
│   │                       IN-SAMPLE, and the tail is still ideal.
│   ├── experiments/robust_geometry.py  the session-11 experiment. Reproduces
│   │                       10d's population FROM THE SEED and asserts the
│   │                       published counts before analysing anything
│   │                       (`check_reproduction`; main() refuses to draw a
│   │                       figure on a mismatch). Owns the statistics —
│   │                       tie-corrected Mann-Whitney U, Benjamini-Hochberg,
│   │                       the octave margin, the normalised box position —
│   │                       all pure and all tested. `--collect` re-simulates
│   │                       (7560 runs, ~23 min); without it the analysis and
│   │                       figures run from the CSV with NO simulator.
│   ├── experiments/robust_geometry_data.csv  TRACKED ON PURPOSE (G49). The
│   │                       per-design table behind ROBUST_GEOMETRY.md: 1890
│   │                       rows, lossless `repr` floats, TT measurements plus
│   │                       the four corner verdicts. This is the file whose
│   │                       absence for S9 cost 23 minutes to rebuild.
│   ├── figures/            PNGs for the write-ups. robust_s3_plane.png is the
│   │                       one that carries session 11 on its own: all 255
│   │                       designs pass S3 at TT, and only the ones away from
│   │                       the window edges survive three corners.
│   ├── experiments/s9_yield.py  the corner sweep. Owns the three ASSUMPTIONS
│   │                       (cl pinned at 150 fF as a LOAD not a choice, VCM
│   │                       does not track VDD, ideal tail) and prints them in
│   │                       every run's header. VDD scaling lives in
│   │                       `point_at_corner` and nowhere else; temperature is
│   │                       a `.temp` card via `run_point(temp_c=)`. Retries
│   │                       once on failure (G45) and prints a `health:` line
│   │                       per stage so the denominator is never implicit.
│   │                       `screen_augmentation()` names which corner would
│   │                       have caught each of the screen's false positives,
│   │                       so the screen is re-cut from data, not intuition.
│   │                       Writes results NEXT TO THE SCRIPT, not the cwd.
│   ├── experiments/s3_yield.py  the random-search baseline, as a coupling
│   │                       factor rather than a bare percentage. Carries
│   │                       PROPOSED_BOX (not yet in params.py — rule 6).
│   │                       `--cl-fixed F` pins one axis by overwriting that
│   │                       coordinate of the SAME seeded LHS design, so runs
│   │                       are PAIRED. Every rate carries a two-sided Wilson
│   │                       95% interval; the coupling factor carries a
│   │                       percentile bootstrap (resolution ~+/-10% at n=2000).
│   ├── experiments/cl_range.py  session 12a. The `cl` derivation: the sizing
│   │                       SKETCH (4 loading stages, each with its reasoning
│   │                       and a MIN_STAGE_GAIN >= 1 gate that fired for
│   │                       real), the PDK-derived routing allowance (read out
│   │                       of SKY130's own vpp cap model, one declared design
│   │                       rule), and `derive_cl_range()` — pure, so the whole
│   │                       thing re-runs from the CSV with no simulator.
│   ├── experiments/cl_range_data.csv  TRACKED ON PURPOSE (G49). 180 rows:
│   │                       every (stage, corner, temp, output common mode)
│   │                       measurement behind CL_RANGE.md.
│   ├── device/cap_probe.py  session 12a. What a following stage presents to
│   │                       the CTLE output, measured as the AC current the
│   │                       driver must supply into one gate under
│   │                       DIFFERENTIAL drive — not `@m[cgg]`, which
│   │                       understates it 1.9-2.7x (G50). Cross-checked
│   │                       against parsed primitives + the model card's own
│   │                       overlap constants (`analytic_load_ff`), and
│   │                       `sanity_check_load` REJECTS a point that
│   │                       disagrees, is out of saturation, or is not
│   │                       capacitive. PDK constants are READ from the model
│   │                       file, never re-declared (rule 9), and the reader
│   │                       raises on a parameter the 180 bins disagree on.
│   ├── device/sky130_runner.py  one SKY130 point, four analyses (.op .ac
│   │                       .noise .dc), one call. Owns the two unit
│   │                       conversions (metres->microns, i_bias->per-side)
│   │                       and the MEASURED swing (G37).
│   │                       RL-driven CTLE sizing. Contract = CLAUDEwa.md.
│   │                       INTERFACES + MOCKS + G0 SPICE PROBES. No PDK, no
│   │                       RL yet. Independent of python_models/ by design.
│   ├── G0_RESULTS.md       G0 gate: PASSED. ngspice 41 env, all 4 analyses,
│   │                       and the .disto/BSIM4 finding (G21). Read before
│   │                       writing the ngspice wrapper.
│   ├── NRZ_RETARGET_AUDIT.md  All 24 four-level assumptions in python_models/,
│   │                       risk-marked, with a recommended order of work.
│   ├── device/spice/       netlists + the PDK plumbing:
│   │                       .spiceinit          ngbehavior=hsa (PARSE-TIME, G29)
│   │                       sky130_nfet_only.lib.spice  TRIMMED SKY130, all 5
│   │                                           corners. 0.42 s vs 16-35 s,
│   │                                           bit-identical (G36). USE THIS.
│   │                       ctle.cir            hand-sizing sandbox, interactive
│   │                       g1_handdesign.cir   generic BSIM4 1.2 V reference
│   │                       g1_sky130_volare.cir  SKY130 1.8 V, full lib
│   │                       g1_sky130.cir       SUPERSEDED (raw repo, G29)
│   │                       g0_diffpair.cir (4 analyses), g0_disto_control.cir
│   │                       (BSIM4 vs level=1 A/B), g0_hd3_tran_fft.cir
│   ├── common/types.py     Frozen §5.1 contracts: Corner, TargetSpec,
│   │                       DeviceResult, LinkResult + the §3 spec constants
│   │                       and the 45-corner S9 grid. ok=False is a VALUE;
│   │                       numeric fields are None on failure, never nan.
│   ├── common/params.py    Action-space NAMES (§5.2). BOUNDS deliberately
│   │                       EMPTY — param_space() raises until a human fills
│   │                       them from the G1 hand-design (§8 rule 6).
│   ├── common/design_equations.py  §6 pole/zero/gain equations (incl. the
│   │                       gmbs body-effect term) + cross_check_extraction().
│   ├── device/crosscheck.py  NEW (2026-08-04). The §6 gate, in PYTHON, where
│   │                       it raises. Parses ngspice stdout; refuses to run on
│   │                       output containing warning-shaped failures
│   │                       (scan_for_silent_failures). Replaces the .control
│   │                       block that exited 0 while computing nothing (G26,
│   │                       G30). derived_ac() separates peaking_db from
│   │                       nyquist_boost_db — they are not the same number.
│   ├── device/ngspice_runner.py  batch-mode driver: netlist template ->
│   │                       subprocess -> parsed SpicePoint.
│   ├── tests/fixtures/     REAL captured ngspice output (3 files): the G1
│   │                       BSIM4 point, the SKY130 point, and the historical
│   │                       BROKEN run that exited 0. Lets the parser and the
│   │                       gate be tested with no simulator, in 0.2 s. Plus
│   │                       sky130_full_lib_golden.json = 20 points from the
│   │                       FULL library, the reference the trimmed one is
│   │                       held to.
│   └── tests/              315 tests. Needing a simulator: test_trimmed_lib.py
│                           (equivalence of the trim) and test_noise_units.py
│                           (inoise_total is RMS VOLTS, verified against
│                           4kTR*BW; do NOT square-root it). Both skip cleanly
│                           if ngspice or the PDK is absent.
│   ├── device/interface.py evaluate() protocol, safe_evaluate (exception ->
│   │                       ok=False), reject_bad_fit (§5.3b, >0.5 dB).
│   ├── device/mock.py      SYNTHETIC square-law stand-in. NOT A PDK. Every
│   │                       number fake. Physically coherent trends only.
│   ├── link/calibration.py THE normalised->volts conversion (§5.3a). The
│   │                       single highest-risk silent bug in that project.
│   ├── link/config.py      LinkConfig for the nebula flow. v_in_diff_pp_v
│   │                       and channel_loss_db_at_nyquist have NO defaults.
│   ├── link/mock.py        SYNTHETIC device->link bridge.
│   ├── rl/reward.py        §9 shortfall reward, worst-corner aggregation.
│   └── tests/              228 tests, <1 s. Run: python -m pytest nebula/tests -q
├── tests/                  pytest suite — 92 tests, ~1.5 min. THE safety net.
│   │                       Run from REPO ROOT: python -m pytest tests -q
│   ├── conftest.py         puts python_models/ on sys.path
│   ├── test_pam4_chain.py  PRBS/Gray/scrambler/TX-coherence/Wilson bound
│   ├── test_channel_adc.py IL vs analytic, BER theory vs Monte Carlo, SQNR
│   ├── test_equalizers.py  MMSE init, FFE/DFE convergence, MLSE exactness
│   ├── test_rx_frontend.py CTLE peaking/noise-enhancement, CDR lock/track
│   ├── test_statistical_eye.py  PMF properties, closed-form check,
│   │                       CROSS-VALIDATION of the two engines, optimizer
│   └── test_link_e2e.py    full-link regressions incl. mm_postffe cases
├── rtl/                    SystemVerilog: 32-parallel FFE+DFE+SS-LMS
│                           (ffe_dfe_lms.sv), BB-CDR + PRBS BER checker
│                           (bb_cdr_ber.sv). WRITTEN, NEVER SIMULATED. Phase 4.
├── verification/           UVM testbench skeleton. NEVER RUN. Phase 4.
├── veriloga_models/        Verilog-A TIA/CTLE/VGA/ADC/PD for Cadence. UNRUN.
├── ams/, scripts/cadence/  Spectre TB + Ocean scripts. Require Cadence. UNRUN.
├── matlab_models/          dsp_verify.m algorithm cross-checks. NOT AUDITED.
├── ffe_learning/           NEW (2026-07-23). Owner's FFE teaching sandbox for
│   └── ffe_demo.py         the UCIe project (§8 item 0). Self-contained demo
│                           (numpy/scipy/matplotlib) that visualizes ISI ->
│                           eye closing -> zero-forcing FFE -> eye reopening +
│                           channel/FFE/combined freq response (ffe_demo.png).
│                           Does NOT touch validated python_models/. Not a test.
├── *.pdf, *.docx           Reference library (see §3). COPYRIGHTED — do not
│                           redistribute; keep repo private.
├── PCI.2/                  GITIGNORED (2026-08-05). Nebula competition material
│                           supplied by the organisers: two handouts plus
│                           `nebula_ctle_rl_1.zip`, a reference PPO+CTLE
│                           implementation (src/env.py, reward.py, train.py, a
│                           generic 130 nm lib, a trained agent, a PVT report).
│                           On disk, out of history — not ours to redistribute.
│                           Worth READING before the RL work starts; do NOT
│                           anchor on its numbers (same rule as ams_rl_ppo,
│                           CLAUDEwa §4.2).
└── Makefile                Build automation (predates audit; NOT AUDITED).
```

## 3. Reference library (what the PDFs/docs are)

| File | Identity | Role |
|---|---|---|
| High-Speed_Wireline_Links Part I / II | Shakiba, Tonietto, Sheikholeslami, IEEE OJ-SSCS 2024 (invited) | **The core methodology** — reference link modeling (I) and optimization/BER assessment (II). The statistical engine follows this school. |
| Modelling (1).pdf | Davide Menin PhD thesis, Univ. Udine 2021 | Fully-adaptive equalization; the guide for Phase 3 joint-adaptation work (tap walking, loop interaction) |
| EECS-2019-143.pdf | Jaeduk Han PhD dissertation, UC Berkeley (Alon/Stojanović) | Automated 60G transceiver generation (BAG); circuit-generation reference |
| PAM4.pdf | Intel AN-835 PAM4 fundamentals | PAM-4 measurement definitions (levels, EH/EW, RLM) |
| PAM4 (1).pdf | Zhang et al., Xilinx, DesignCon 2016 | Practical 56G PAM4 link tradeoffs |
| Introduction.pdf | CERN intro-to-PAM4 slides | Background |
| A (1).docx | Substack-style overview of optical interconnects (IM-DD→CPO→coherent) | Optical track background |
| wireline-video-links.docx | Sheikholeslami lecture series + **Toronto StatOpt** tool links | StatOpt = the template for statistical_eye.py |
| `hussin-mohamed/UCIE_GP` (external GitHub, public) | UCIe 3.0 **logical/digital** PHY, SystemVerilog + UVM, 14 nm, 16 lanes, up to 32 GT/s NRZ forwarded-clock, 500 MHz logical clock | Digital-half reference for the new UCIe group project (§1 New Direction). Contains the **serializer + LFSR scrambler** RTL; NO analog blocks. Also a **gold-standard UVM verification template** (found/fixed 55+ RTL bugs) — relevant to §8 #5. |
| `Part 11 FFE.pdf` (professor's handwritten note, 12 pp) | The professor's own FFE lecture, sent to the owner after they chose FFE | **The syllabus/scope for the owner's FFE block.** Covers: 2-tap FFE + freq response (DC=1+a, Nyquist=1-a, high-pass boost); FIR/z-transform (unconditionally stable); RC toy example; **zero-forcing** matrix method + 3-tap worked example + general (2M+1)-tap form + limits (only sampled points -> no jitter fix, neglects far ISI); full-rate vs half-rate circuits; combiner (IDAC taps, sign bit, inductive peaking); **max boost = 1/(1-2K)** (K=1/3 -> 9.54 dB, verified), fixed by K not N; practical limits; sim (channel+FFE+eyes). NOTE: the 3-tap worked answer [-0.25,1.05,0.28] does not match the matrix as read (solve gives [-0.275,1.169,-0.243], post-tap sign flips) — confirm exact pulse-sample layout w/ professor. |

## 4. The simulated system (architecture + conventions)

Signal chain (waveform engine, `link_sim.run_link`):

```
PRBS → scramble → Gray/PAM4 → TX-FFE → ZOH ×OSR(8) → TX pole (0.75·fbaud)
 → TX jitter (RJ/SJ, time-warp) → channel H(f) → +AWGN (AT CTLE INPUT!)
 → CTLE (1z/2p) → gain calibration → CDR-driven sampler (closed loop,
   ppm offset, aperture RJ, 16-way TI mismatch, 6-bit quantization ±vref)
 → joint FFE(3+1+17)+DFE(5) single-pass LMS (supervised→DD at training_len)
 → Gray decode → bit errors vs LINE bits → BER + Wilson 95% bound
```

**Conventions you MUST know before touching code** (each earned by a bug):

- **Symbol units:** post-calibration, the cursor sample = 1.0, so PAM-4 levels
  sit at ±1/±3, slicer thresholds at −2/0/+2, ADC full scale = ±4.0
  (`adc_vref`). All slicer-domain sigmas are in these units.
- **Gain calibration** is pulse-cursor-based (scale = 1/pr[cursor]), NOT
  RMS-AGC — CTLE edge overshoot inflates RMS and compresses levels (G5).
- **Noise definition:** `noise_db` = SNR at channel output measured in the
  SYMBOL Nyquist band [0, fbaud/2]. Simulated white noise on the OSR grid
  therefore has total power P_sig·osr/SNR (factor osr is intentional).
- **Alignment:** samples[k + delay] carries symbol k, delay found by
  `estimate_delay` (cross-correlation, scans negative lags — CDR can slip
  whole UIs during acquisition). Inside the equalizer, decisions[k] is the
  decision FOR symbol k (FFE pre-cursor delay handled internally).
- **Reference bits:** `PAM4Transmitter.generate` returns LINE bits
  (post-scrambler) — these are coherent with the transmitted symbols. Raw
  PRBS bits are `.raw_bits` (comparing against them is bug G2).
- **Seeds:** ALL randomness flows from `LinkConfig.seed` via a
  `np.random.Generator`. Never call `np.random.seed()` (G3).
- **Both engines share `LinkConfig`** and build from the same calibration
  path (`StatisticalEye.from_link_config`) — that's what makes cross-
  validation meaningful. If you change the chain in link_sim, mirror it there.

## 5. Complete history (what was done, in order, with the WHY)

### Phase 0 — audit + correctness (commit `ce733a8` equivalent; authors later rewritten, see G12)
Bugs found in the inherited code and fixed:
1. **MC seeding no-op:** `np.random.seed(42)` inside run_link made all Monte
   Carlo runs identical.
2. **Scrambler not self-synchronizing:** fed the INPUT bit back into the LFSR;
   multiplicative scramblers must feed back the OUTPUT bit. Roundtrip failed.
3. **MLSE trellis inconsistent:** state decode used newest-symbol=MSB, state
   update wrote newest=LSB → SER 0.72 (random). One convention → SER 5e-4.
4. **TX reference incoherent:** returned pre-scrambler bits as the BER/training
   reference while transmitting scrambled symbols.
5. **PAM4 BER theory 2× high:** used erfc where Q was meant. Correct:
   BER = (3/8)·erfc(√(SNR/10)).
6. **FFE/DFE two-pass processing** reset delay lines at the training→DD switch;
   replaced with single-pass joint receiver, delay-aware references.
7. **README FEC target wrong:** claimed pre-FEC 2e-2; KP4 RS(544,514) needs
   ~2.4e-4 (802.3bs); 802.3dj concatenated ≈ 1e-3 class.
Plus: git init, .gitignore, 28 tests, Wilson-bound BER reporting.

### Phase 1 — honest waveform engine (commit `8cbd26a` equivalent)
- Oversampled waveform chain (OSR 8) replacing baud-rate-only shortcuts.
- Real CTLE with noise injected BEFORE it (noise enhancement modeled, tested).
- Closed CDR loop: **Alexander BB PD** (T/2 interpolated mid-samples, gated on
  symmetric transitions) + PI filter. Lessons (all documented in code):
  - Sign-MM on raw waveforms locks at the eye EDGE (h(−1)=h(+1) equilibrium).
  - Pattern-gated BB loop: effective integral gain ×(update gap); keep
    4·ki/kp ≲ 2% or it limit-cycles.
  - Gear-shift (P-only acquisition, then enable integrator w/ clamp) or the
    integrator winds up during acquisition → cycle slips → runaway.
  - Lock metric must check phase slope is explained by the freq word.
- MMSE warm start fixed: cursor placed at FFE's n_pre (was centred at
  n_taps/2 → 7-symbol reference misalignment, ~4 dB penalty), Wiener gain
  preserved, full-cyclic peak search.
- `adapt_start`: LMS held until after CDR acquisition (silicon bring-up order).
- JTOL mode; validation: 0 errors @ 28 dB/3 cm; JTOL corner ~1–3 MHz, 0.1 UI
  floor; lock lost ≥30 dB loss with 6 dB CTLE (honest architecture limit).

### Phase 2 — statistical engine (commit `83ee4bf` equivalent)
- `statistical_eye.py`: exact ISI PMF (per-tap 4-point shifted adds), slicer
  noise via wᵀRw with CTLE-colored autocorrelation at baud spacing, ideal-DFE
  cancellation, per-boundary Gray BER, bathtub, Gaussian RJ fold, eye widths.
- Cross-validation: engines agree within ~3× over BER 1e-1…1e-4 (statistical
  mildly conservative — reference-receiver assumptions). fig5.
- `optimize_ctle`: Part II-style sweep. **Finding #1: unconstrained slicer
  optimum on dispersive channels is 0 dB CTLE** (long digital FFE equalizes
  with less noise boost than analog peaking) **but that config was unlockable**
  → derived `crossing_jitter_ui()` = pattern-dependent zero-crossing jitter at
  the eye edge (edge-ISI σ / edge slope), calibrated vs time-domain lock
  outcomes: healthy <0.45 UI, boundary ~0.6–0.75 UI. Constraint added.

### Phase 3a — post-FFE MM PD + clipping discovery (commit `6c84e89` → `3aa5b28` after author rewrite)
- `CDRSampler pd_mode='mm_postffe'`: MM PD behind a FROZEN MMSE timing-path
  FFE (production arrangement; freezing sidesteps the FFE↔CDR tap-rotation
  degeneracy — true co-adaptation is future work). `LinkConfig.cdr_arch`.
- **MM sign lesson:** E[y_k·d_{k−1} − y_{k−1}·d_k] ∝ h(+1)−h(−1) = positive
  when EARLY; with this loop's convention (phase↑ = sample earlier) the raw
  product locks 0.5 UI off-centre. Negated + verified.
- Results: locks at 6 cm/0 dB (Alexander-infeasible) and 10 cm/6 dB
  (Alexander lock-lost); CDR jitter flat ~20 mUI across ALL CTLE settings vs
  28–75 mUI Alexander (fig8) — timing decoupled from AFE tuning.
- **Finding #2: ADC clipping is the real 0-dB-CTLE limiter** — 17 % of samples
  beyond ±4 full scale (peaks 7.65) → BER 2e-2 for BOTH architectures;
  explains the 1000× stat-vs-TD gap at that point (stat engine assumes a
  linear unclipped ADC). Added `clip_probability()` (exact, from pre-FFE ISI
  PMF incl. cursor), `adc_clip_frac` in run_link results, calibrated clip
  constraint (<12 %; 10 % survivable / 16 % fatal measured) in optimize_ctle;
  timing constraint is now architecture-aware.
- **Refined design rule: the CTLE is needed for timing health (Alexander arch)
  AND ADC dynamic range (any arch). Only the first is engineerable away.**

### Repo/GitHub (2026-07-18, latest session)
- Pushed to private GitHub repo. Commit authors REWRITTEN via filter-branch to
  `Jai Kaushik <jaikaushik-prog@users.noreply.github.com>` (original author
  email attributed commits to a wrong GitHub account) — hashes changed;
  current HEAD `3aa5b28`. See G12.
- Report figures 1–8 generated (`make_report_figures.py`); figs explained to
  the owner in plain language for professor communication.

## 6. Key numbers & validated behavior (current state)

- Tests: **591 passing** —
  `python -m pytest tests nebula/tests -q -m "not slow"`.
  Split: `tests/` **92**, `nebula/tests/` **499**. (Was 65 + 267 = 332 at the
  start of session 9; 430 at the end of it; 444 after 10b; 528 after 11.) Two
  further tests are marked `slow` and deselected by default: they re-derive
  the SKY130 golden values from the FULL library (~30 s each). Run them after
  a PDK update. **Runtime is machine-load dependent** — the same suite has
  taken 1.5 min on a quiet machine and 34 min while an 11-worker ngspice pool
  was running. A slow suite is contention, not a hang.
- **Measured output swing at the corrected point (session 9d).** 1 dB gain
  compression at **1427 mVpp** differential; saturation limit 2161 mVpp;
  steering ceiling 2281 mVpp; `4*I*RL` textbook value 2400 mVpp. Session 9c
  used `2*I*RL` = 1200 mVpp, which is **a peak read as a peak-to-peak** — the
  ceiling is `4*I*RL`. And the binding mechanism is **current steering, not
  headroom**: at the 1 dB point the pair still has vds 1.29 V against vdsat
  0.079 V. `DeviceResult.vout_swing_v` should carry the 1 dB number.
- **The G1 reference point is superseded (session 9c).** The published
  numbers — peaking 8.29 dB @ 1.259 GHz, 0.275 mVrms, 6.0 mW — are correct for
  what they describe, but that operating point runs at **gm/I_D = 1.7 V^-1**
  with its sources 0.44 V BELOW ground, which no real tail transistor can
  provide. Corrected bias: **W=40 nf=4, I_tail=1.5 mA, VCM=1.25 V, VDD=1.8 V,
  SKY130 -> gm 12.62 mS, gm/I_D 8.42, v(s1) +0.343 V, noise 0.275 mV.**
  The parameter BOUNDS and the 5.3% S3 yield were both derived inside the old
  bias and are **provisional until re-run**.
- **The honest random-search baseline is 8.73%** (165 of 1890 simulated, from
  2000 Latin-hypercube samples of the re-derived 1.8 V box), **95% CI
  [7.54, 10.09]**. It is a baseline for G3 to beat, not evidence of a
  mechanism. **It rises to 13.54% [12.08, 15.16] if `cl` is pinned at 150 fF
  instead of searched** (session 10b, `nebula/CL_SENSITIVITY.md`) — so which
  number G3 must beat is a live decision, not a fact.
- **Corner-robust yield, the same 1890 designs at 45 corners** (session 10d,
  `nebula/S9_YIELD.md`, 20 205 SPICE runs). **13.49% at TT/27C ->
  8.20% [7.05, 9.52] across three corners -> 8.10% [6.95, 9.41] across all
  45.** Cross-tabulated design by design: **100 of the 255 nominal winners
  (39.2%) fail at a corner**, and 0 designs fail nominal yet pass the corners.
  The quotable sentence is **"an optimiser scored at nominal is wrong about two
  of every five designs it calls a success"** — a tax on the baseline, NOT a
  coupled constraint (do not let it drift back into one; see G40). Two further
  results: **three corners are worth 98.7% of forty-five** (G47) and **the
  worst corner is fast-hot, not slow-hot** (G46). Health: 0 hard simulator
  failures, 0 retries, 0 screen/promotion mismatches across 465 repeated
  (design, corner) pairs. **Optimistic bound** — the tail is still ideal
  current sinks, so all corner spreads here are understatements.
- **Geometry of corner-robust designs** (session 11,
  `nebula/ROBUST_GEOMETRY.md`, 7560 SPICE runs re-simulating 10d's population).
  **Corner robustness is not a property of where a design sits in the parameter
  BOX; it is a property of where it sits in the SPEC WINDOW.** Splitting 10d's
  255 nominal winners into the 155 corner-robust and 100 corner-fragile:
  - **Every box coordinate is a null.** rs, cs, rl, i_bias, w_in, l_in, vcm_in,
    nf_in all have q > 0.16, and the two purpose-built interiority statistics
    (distance to the nearest box face, min and mean over dimensions) are the
    LEAST significant rows in the table at q = 0.98. **The "robust designs are
    interior in the box" half of the hypothesis is FALSIFIED.**
  - **Both S3 axes separate the groups once FOLDED onto distance-to-nearer-
    edge**, and neither does before: raw f_peak medians are 1.738 GHz in BOTH
    groups (q = 0.81) and raw peaking differs by 0.05 dB (q = 0.81), while
    f_peak margin reads **0.325 vs 0.126 octaves (p = 2.8e-12)** and peaking
    margin **2.70 vs 0.86 dB (p = 3.2e-11)**. A two-sided spec makes the raw
    coordinate uninformative by construction — the two failure modes point in
    opposite directions and cancel in any median. Starkest single number:
    **0 of 155 robust designs sit within 0.5 dB of a peaking edge, against 37
    of 100 fragile.**
  - **The usable output is a JOINT filter:** f_peak margin >= 0.133 octaves AND
    peaking margin >= 1.0 dB gives **92.1% [86.5, 95.6] corner-robust against a
    60.8% base rate**, keeping 140 of 255. Either condition alone reaches only
    ~75%. Both are computed from an AC run the evaluator already does, so the
    filter is free. **Thresholds are IN-SAMPLE** — a fresh seed would cost
    23 min and has not been run.
  - **Resolution limit:** `meas ac MAX` returns a grid sample and the sweep is
    `ac dec 50`, so f_peak is quantised at **0.0664 octaves** and the 1-octave
    S3 window holds only **15 distinct f_peak values**. Margin thresholds finer
    than that quote the sweep setup, not the circuit.
  Proposal only — `params.py` untouched (rule 6). Still an optimistic bound:
  the tail is ideal, so the required margins are lower bounds.
- **`cl` has a derived range, and it is entirely below the value every corner
  number used** (session 12a, `nebula/CL_RANGE.md`, 180 SPICE runs / 16 s).
  Derived from what physically loads the CTLE output — the 1-tap DFE summer
  input pair, the slicer input pair, and the wire:

        cl_lo   13.64 fF   (11.67 device + 1.97 routing)
        cl_mid  32.63 fF   (geometric mean; a screen point, not a claim)
        cl_hi   78.04 fF   (63.74 device + 14.29 routing)
        ratio    5.72x  =  2.52 octaves   vs S3's 1.00-octave f_peak window

  **The 150 fF pin behind 13.49 / 8.20 / 8.10 % is 1.92x above `cl_hi`.**
  Four things worth carrying:
  - **`@m[cgg]` is not the gate load (G50).** It is the INTRINSIC capacitance
    and excludes the overlap (`cgso = cgdo = 2.449e-10 F/m`) and the Miller
    multiplication of C_gd by the loading stage's gain. Measured
    understatement **2.00x / 2.52x / 2.70x** on the 4 / 12 / 16 um stages —
    it grows with gain, which is the Miller signature. At the 16 um stage
    **52% of the load is C_gd,overlap x (1 + |A|)**.
  - **The sizing sketch moves the load 5.9x; the process corner moves it
    1.16x, temperature 1.08x, the CTLE output common mode 1.04x.** The range
    is wide because the following stage is undesigned, not because silicon
    varies. Designing the slicer would narrow `cl` far more than any corner
    analysis.
  - **The corner that loads the node most has the LEAST gm.** C_in orders
    `fs` > `ss` > `tt` > `ff` > `sf`, exactly inverse to gm. Do not screen the
    load and the device at "the" worst corner — same shape as G46. (Also: for
    the nfet, `sf` behaves fast and `fs` slow; the label order is not
    (nfet, pfet).)
  - **A half-rate front end gives `cl_hi` = 141.8 fF** — the 150 fF pin was
    the right number for a topology S2 does not describe. Reported, NOT folded
    into the bound (rule 5).
  Cross-check: the AC measurement is reconstructed from `.op` primitives plus
  the model card's overlap constants to **1.02% median / 2.20% worst** over
  180 runs, and `sanity_check_load` rejects a point that disagrees by >5%.
  0 of 180 rejected. Proposal only; `params.py` untouched.
- **`cl` sensitivity, 2000 paired LHS samples per point** (session 10b). Pin
  `cl`, hold every other bound:

        cl        50f     100f     150f     250f     400f    (sampled 10-500f)
        S3      8.73%   11.27%   13.54%   12.06%    9.52%          8.73%
        A       52.65   48.52    46.14    39.26    33.54           48.47
        B       16.61   21.90    24.02    22.80    19.21           16.03
        peaks    1673    1559     1469     1313     1168            1578

  Both marginals turn over; A falls monotonically (the load pole eats peaking)
  while B rises then falls (the load pole first relocates the peak into the S3
  window, then extinguishes it). 150 fF is a genuine interior maximum but is
  NOT separable from 250 fF at this n. S5, S6 and the saturated fraction do
  not move at all with `cl`, as expected.
- Reference operating point: 3 cm (9 dB) channel, SNR 26 dB, CTLE 6 dB,
  Alexander: BER ≈ 1e-4; SNR 28: 0 errors (bound ~1e-4→ 8.7e-5 at 30k syms).
- Loss sweep (SNR 28, CTLE 6 dB): clean ≤12 dB; ~1e-2 at 24 dB; lock lost
  ≥30 dB (Alexander) / locks but BER-fails (mm_postffe).
- JTOL (3 cm): 1.0 UI below ~1–3 MHz, 0.1 UI floor above (grid-limited res).
- Optimizer @ 6 cm: 1.5 dB peaking optimum (both archs, constraints active);
  time-domain confirms 3.4e-4 there.
- CDR: tracks 50–100 ppm; Alexander jitter 26–35 mUI typical; mm_postffe
  ~17–23 mUI, flat vs CTLE peaking.
- Two engines agree within ~3× where both operate (fig5).
- Figures: results/fig1_eyes … fig8_arch_compare (+ link_run.png dashboard).

## 7. Known model limitations (honest list — do not overclaim)

- Statistical engine: ideal DFE (no error propagation), MMSE-designed FFE
  (assumes white noise in design, correlated in evaluation), Gaussianized
  quantization, NO clipping distortion in the BER itself (only a constraint),
  fixed rj_cdr=0.015 UI approximation in from_link_config.
- Time-domain: no CDR loop latency modeled (RTL has ~32-symbol parallelism
  latency → lower usable kp); TI gain error applied post-AGC; single-pole TX
  model; loss-model channel only (no reflections/crosstalk until .s4p data).
- JTOL amplitude grid is coarse (0.05/0.1/0.2/0.4/0.7/1.0 UI).
- Power numbers are PLACEHOLDERS (literature-based), never simulated.
- rtl/, verification/, veriloga_models/, matlab_models/, optical_dsp.py,
  ml_equalizer.py, visualization.py, Makefile: NOT AUDITED/RUN — treat as
  untrusted until proven (the Phase-0 experience says assume bugs).

## 8. Next steps (prioritized backlog with context)

**-1. NEBULA competition track (ACTIVE, started 2026-08-03).** Separate
   project, own contract (`CLAUDEwa.md`), hard deadline 15 Sept 2026.
   DONE: layer interfaces + mocks + 251 tests; **G0 PASSED**
   (`nebula/G0_RESULTS.md`); NRZ retarget audit written
   (`nebula/NRZ_RETARGET_AUDIT.md`); bounds re-derived; robust geometry
   confirmed; corner-yield swept (13.49% -> 8.10%). Blocking next actions,
   in priority order:
   - **>>> THE TAIL TRANSISTOR IS NOW THE HIGHEST-VALUE OPEN ITEM. <<<**
     (Promoted 2026-08-05.) Every simulation this project has ever run uses
     **two ideal current sinks** for the tail. An ideal sink delivers exactly
     I_tail at every corner: it does not lose current at SS/125C, does not
     gain it at FF/0 C, and does not fall out of saturation when the rail
     drops 5%. That single assumption is what makes the whole S9 result an
     **optimistic bound** (G47), and it also blocks three of the nine box
     dimensions (`w_tail`, `l_tail`, `nf_tail` have no provenance). Everything
     needed to re-measure is already instrumented: add the device, then re-run
     `python -m nebula.experiments.s9_yield --n 2000` unchanged and diff
     against `nebula/S9_YIELD.md`. **This is the one experiment that could
     still turn corner robustness into a real constraint rather than a tax.**
     Session 11 adds a second reason to do it now: `ROBUST_GEOMETRY.md`
     measures how much S3 margin a design needs to survive the corners
     (0.133 octaves of f_peak margin plus 1.0 dB of peaking margin buys
     92.1% robustness against a 60.8% base rate), and **every one of those
     margins is a LOWER BOUND while the tail is ideal.** Re-running
     `robust_geometry.py --collect` afterwards is the cheapest way to see how
     far the requirement moves — 23 min, no new code.
   - **Session 11's two proposals, for a human** (`ROBUST_GEOMETRY.md` §7).
     Neither touches `params.py`; both are about the SEARCH, not the box.
     (a) **warm-start** the policy and the baselines from designs with
     f_peak margin >= 0.133 oct and peaking margin >= 1.0 dB — free, since
     both come out of an AC run the evaluator already does; (b) **shape the S3
     reward on the two FOLDED margins** rather than on peaking and f_peak
     directly, since §3 of that file shows the raw coordinates carry no
     information about corner robustness and the folded ones carry essentially
     all of it. Caveat the human must weigh: a 1.0 dB peaking margin bans the
     3 dB and 12 dB endpoints of S3's own tunable range, so the rule belongs
     on the search and not on the deliverable. Whether those endpoints are
     corner-robust AT ALL in this topology is unmeasured and worth asking.
   - **Approve or amend the proposed box**, then copy it into
     `common/params.py::BOUNDS`. The `cl` dimension is recommended to be
     **removed from the SEARCH and replaced by a screened CONTEXT RANGE**,
     `cl = 13.6-78.0 fF` (`nebula/CL_RANGE.md` §8, session 12a). This
     supersedes `CL_SENSITIVITY.md`'s "pin at 150-250 fF": that value was the
     S3-yield maximum of five tested, and the derived range's TOP is 1.92x
     below it. **One topology question rides on this and is a human's**: if
     the receiver is half-rate (two data + two edge slicers on the node), the
     range becomes 13.6-141.8 fF and the ratio 10.4x instead of 5.7x. S2 names
     no CDR, so the bound above assumes full rate.
   - **The CTLE output common mode may not be able to bias the stage it
     drives** (`CL_RANGE.md` §7a). `headroom_ok_1v8()` lets v_out fall to
     0.5 V; the loading pair needs roughly 1.15 V or its source node goes
     negative — session 9c's unbuildable-tail failure, one stage downstream.
     Either the box needs a tighter v_out floor or the RX needs AC coupling /
     a level shift. Nothing in the project currently notices this.
   - **G1 — was "hand-size a reference CTLE at TT".** Port to 1.8 V (the bounds
     are 1.2 V numbers and do NOT transfer — see the provenance audit), add
     a real tail transistor (above), and pull the **MIM cap and poly resistor**
     models the S7 area estimate needs.
   - **Compression: real, but much smaller than 9c reported.** The limit is
     **current steering, not headroom** — which is also why a 3.3 V device
     buys only +12% swing (G39).
   - **Abstract due Aug 6.** Write it around what G1 shows is achievable.
     **The "coupled constraint" argument is RETRACTED (G40).** State the
     ideal-tail assumption plainly; it is the live one.
   - **The NRZ retarget.** 21 of the 24 audit items remain; order of work at
     bottom of `nebula/NRZ_RETARGET_AUDIT.md`.

**0. UCIe group project — owner's FFE block (ACTIVE, started 2026-07-23).**
   STATUS: starting Part A step 2 (zero-forcing math).

**1-9.** (See existing backlog: .s4p, clipping disto, joint adaptation, etc.)

## 9. Gotchas & footguns (each one cost real debugging time)

- **G1 — Repo must stay PRIVATE.** The PDFs are copyrighted (IEEE, theses,
  Intel/Xilinx). A public/portfolio version must strip them from HISTORY
  (they're in the baseline commit), not just delete the files.
  **AMENDED 2026-08-04 (session 10a) — true of the GitHub repo, NOT of this
  checkout.** `github.com/jaikaushik-prog/serdes-dsp-framework` still carries
  them in its baseline commit and still needs a history rewrite before it could
  ever go public. This working tree was `git init`-ed fresh with the PDFs
  already in `.gitignore`, and the index was checked empty of them before the
  initial commit, so **its** history has never contained them. The two are now
  unrelated histories. Do not `git remote add origin` that URL and push — it
  would either be rejected as unrelated or, if forced, replace a repo whose
  history you have not audited. Decide deliberately (new remote vs. rewrite of
  the old one); see G41.
- **G41 — (repo) `git init` was run on 2026-08-04; the history starts clean,
  and there is NO remote.** One commit on `main`, 102 files. The check that
  makes the claim real is two commands, and they are the ones to re-run before
  any future `git add -A`:

        git diff --cached --name-only | grep -iE '\.(pdf|docx)$'   # must be empty
        git status --ignored --porcelain | grep '^!!'              # what was skipped

  `.gitignore` is now sectioned and commented by *reason* rather than by file
  type, because the reasons differ in kind: copyright (PDFs — never commit),
  redistribution (the PDK tree at `C:\Users\DELL\sky130A`, out of tree today
  but the patterns exist so an in-tree copy cannot slip in), and mere
  regenerability (results, `__pycache__`, ngspice scratch, the `ams_rl_ppo`
  checkpoints). **One deliberate non-ignore:**
  `nebula/device/spice/sky130_nfet_only.lib.spice` is OURS (G36) — 69 lines of
  `.include` pointers plus `.option scale=1.0u`, redistributing no model cards
  — and is excluded from the `sky130*` pattern by an explicit `!` rule. Losing
  it would cost the 40-80x inner-loop speedup.
- **G2 — Scrambler coherence:** always compare RX bits against LINE bits
  (post-scrambler) or descramble first. `generate()` returns line bits.
- **G3 — Never `np.random.seed()`.** Thread `LinkConfig.seed` →
  `np.random.default_rng`. The TIADC class in adc_model.py still has an
  internal seed=42 (standalone use only; the link path doesn't use it).
- **G4 — FFE cursor convention:** warm starts must place the cursor at
  `n_pre`, not the filter centre. `mmse_init_ffe(..., n_pre=)`.
- **G5 — Don't RMS-AGC a peaked waveform;** use pulse-cursor gain calibration.
- **G6 — BB-loop stability:** pattern-gated updates ⇒ effective ki multiplied
  by mean update gap (~4). Keep 4·ki/kp ≲ 2 %. Gear-shift + integrator clamp
  are load-bearing, not decoration.
- **G7 — MM PD sign:** raw MM product is positive-when-early; this loop needs
  positive-when-late (phase↑ = earlier). See rx_frontend comment.
- **G8 — Alexander PD needs a partially-open RAW eye** (crossing jitter
  <~0.6 UI); MM-postffe needs an FFE-openable eye. Neither is universal.
- **G9 — adapt_start:** never let sign-sign LMS adapt during CDR acquisition
  (|Δtap|=µ regardless of error size — it walks off the warm start).
- **G10 — Windows console is cp1252:** no →, ≤, µ, ≈, em-dash in print()
  strings (crashes under redirection). Files themselves are UTF-8, fine.
- **G11 — Working directory:** run pytest from repo ROOT; run link_sim from
  python_models/. PowerShell sessions persist cwd between tool calls.
- **G12 — Git identity:** commit as `Jai Kaushik
  <jaikaushik-prog@users.noreply.github.com>` (global config is set). Do NOT
  use the BITS email — it attributes commits to a wrong GitHub account
  (history was already rewritten once to fix this; hashes changed).
- **G13 — Figure caching:** make_report_figures reads cached CSVs
  (arch_compare_pk.csv etc.); delete the CSV to force recomputation.
- **G14 — `Channel.pulse_response` uses argmax cursor + trimming; the
  waveform path avoids `np.convolve(mode='same')` deliberately.** Keep
  explicit alignment; never reintroduce 'same'-mode shortcuts.
- **G15 — scikit-rf not installed** (S-param import raises); matplotlib may
  need `MPLBACKEND=Agg` for headless runs.
- **G16 — (nebula) `nebula/device/mock.py` and `nebula/link/mock.py` produce
  FAKE numbers.** They exist so three people can build three layers in
  parallel before ngspice exists. No value from either may reach the abstract,
  report, slides or results table (CLAUDEwa.md §8 rule 1). Their *trends* are
  physically coherent; their *magnitudes* are invented. The mock's noise floor
  in particular is optimistic — do not read S5 headroom off it.
- **G20 — (nebula) ngspice: use `ngspice_con.exe`, NOT `ngspice.exe`.** The
  latter is the GUI build and prints nothing under `-b`, which looks exactly
  like a broken install. Binary lives in
  `C:\Users\DELL\miniforge3\envs\nebula\Library\bin\`. Activate with
  `conda activate nebula`.
- **G21 — (nebula) `.disto` returns exactly 0.0 for BSIM4.** Not a linear
  circuit — BSIM4 does not implement the higher-order derivatives the analysis
  needs, so it silently contributes no distortion at all. Proven with an A/B
  against a `level=1` model in one netlist (see `nebula/G0_RESULTS.md`). Every
  open PDK is BSIM4-based, so no PDK fixes this. **HD3 (S4) must come from
  transient + FFT**, ~0.26 s/corner vs 0.066 s for AC+noise.
- **G22 — (nebula) `.disto` with a trailing `f2overf1` argument** switches to
  two-tone intermodulation mode and aborts with "No source with f2 distortion
  input". Single-tone harmonic mode is the form WITHOUT that argument. Also:
  `meas` does not accept the two-argument `vdb(a,b)`; `maxat` is not a `meas`
  function; `linearize` takes vector names, not a timestep; ngspice's own
  `fft` zero-pads to a power of two so bin indices are not `f/binwidth` —
  dump with `wrdata` and FFT in numpy.
- **G23 — (nebula) PySpice is installed but does not work** (bundled ngspice
  DLL fails to load, 0x7e; post-install downloader dead). Do not spend time on
  it: batch `ngspice_con -b` via `subprocess` is the better fit for the RL loop
  anyway — no FFI state, trivially parallel per corner, crashes are exit codes.
- **G24 — (nebula) compression is a validity condition, not a clamp.** The
  link layer used to compute `min(g_dc * v_in_pp, vout_swing_v)`. Both halves
  were wrong: (a) `g_dc` is the DC gain, but the eye is set by `|H(f_nyquist)|`
  which is 3-12 dB higher by construction (S3); (b) `min()` silently converted
  an invalid operating point into a plausible number, and an RL policy hunting
  eye height would have found that region and lived in it. Now:
  `output_swing_pp_v()` returns the unclamped linear prediction from the
  PEAKED gain, and `check_compression()` returns a reason string that the link
  layer turns into `ok=False`. See `nebula/link/calibration.py` conventions
  C3/C4.
- **G26 — (nebula) ngspice `let` failures are WARNINGS, and the run exits 0.**
  `@m1[gm]` and friends live in the `op1` plot; after an `.ac` the current
  plot is `ac1` and every `let` referencing them fails with
  "vector ... is not available or has zero length" while the script carries on
  and returns success. The G1 netlist's entire §6 cross-check block failed
  this way and was reported as passing. **Grep ngspice output for
  `not available|Error:` before believing any derived number**, or compute
  derived quantities in Python from parsed primitives (which is what
  `nebula/device/ngspice_runner.py` does).
- **G27 — (nebula) §6's gain equation is missing the body effect and fails
  its own 1 dB gate.** In a bulk process the bulk is grounded, the source
  moves, so `k = 1 + (gm + gmbs)*Rs/2`. Measured at the G1 point gmbs/gm was
  0.33 and §6-as-written was **2.33 dB** optimistic. `predict()` and
  `cross_check_extraction()` take `gmbs` (default 0.0 = §6 verbatim). Always
  pass the simulated gmbs when comparing to SPICE.
- **G28 — (nebula) `rl`'s ceiling is JOINT with `i_bias`, not independent.**
  Load drop is `0.5*i_bias*rl` and must fit under VDD=1.2 V. 12 mA x 500 ohm
  drops 3.0 V. Both values are individually inside their bounds. Use
  `params.headroom_ok()` to reject the pair before spending a SPICE call
  (measured: 9.5% of samples, and it cuts triode failures 9.3% -> 2.5%).
- **G30 — (nebula) `.param` names are NOT visible as `.control` vectors.**
  The second, independent reason the §6 cross-check block never ran (the first
  is G26's plot-context trap). `let k = 1 + gm * {RS_OHM} / 2` does not
  substitute — ngspice reports `vector rs_ohm is not available`, then
  `Error: RHS "1 + gm * rs_ohm / 2" invalid`, and **exits 0**. Same for
  `let power_mw = v(vdd) * {ITAIL} * 1000`. **Put no derived arithmetic in
  `.control` at all.** Print primitives; compute in Python
  (`nebula/device/crosscheck.py`). CLAUDEwa.md §8 rule 9.
- **G31 — (nebula) SKY130 instance W and L are PLAIN NUMBERS IN MICRONS.**
  `libs.tech/ngspice/sky130.lib.spice` sets `option scale=1e-6` and the
  `sky130_fd_pr` subckts default to `l=1 w=1` meaning one micron. So write
  `W=5 L=0.15`, not `W=5u L=0.15u` — the latter gives 5 pm, falls outside all
  180 model bins, and aborts with the *misleading* **"could not find a valid
  modelname"** (which reads like a missing library, not a units error). The
  generic-BSIM4 netlists in the same directory use SI metres. Never copy W/L
  between the two families without converting.
- **G32 — (nebula) two netlists described "the same" reference point with
  different model cards.** `g1_handdesign.cir` was missing `k2=0.05`, which
  `ngspice_runner.py::_NETLIST` had — and `k2` is BSIM4's body-effect
  coefficient, i.e. exactly the term G27 is about. Effect: gmbs/gm 0.250 vs
  0.327, A_dc −14.123 vs −14.569 dB, peaking 8.19 vs 8.29 dB. All published
  numbers came from the runner. Fixed by matching the cards. **If you clone a
  netlist, diff the `.model` line**; a one-parameter drift is invisible and
  moves the body-effect term by 30%.
- **G29 — (nebula) the raw `sky130_fd_pr` clone is NOT ngspice-ready.**
  **RESOLVED 2026-08-04 — see G33.** Kept for the diagnosis.
  `ngbehavior=hsa` must go in a **`.spiceinit`**, not `.control` (too late —
  `.include` runs at parse time); that clears the `sqrt()` problem. What it
  does not clear: the `.pm3.spice` `.subckt` declares its parameters via a
  `.param` line inside the body ("13 formal but 0 actual params"), and the
  `.corner.spice` files contain zero `.model` cards. **Install `open_pdks` or
  use `volare`** for the generated `libs.tech/ngspice/sky130.lib.spice`. Do
  not patch the raw repo.
- **G33 — (nebula) the WORKING SKY130 install.** `C:\Users\DELL\sky130A`
  (`libs.tech/ngspice` + `libs.ref/sky130_fd_pr/spice`, ~52 MB, 856 files),
  copied out of a `volare` install in WSL2 Ubuntu. Use
  `.lib "C:/Users/DELL/sky130A/libs.tech/ngspice/sky130.lib.spice" tt` — and
  `ss`/`ff`/`sf`/`fs` for the other four S9 process corners. Reference
  netlist: `nebula/device/spice/g1_sky130_volare.cir`; run it from
  `nebula/device/spice/` so the local `.spiceinit` (`ngbehavior=hsa`) is read
  at parse time. Reinstall recipe if the tree is lost:
  `pip3 install --user --break-system-packages volare` inside WSL
  (**not** a venv — `python3-venv` is absent and installing it needs sudo),
  then `~/.local/bin/volare enable --pdk sky130 c6d73a35f524070e85faff4a6a9eef49553ebc2b`.
  Superseded: `g1_sky130.cir` (raw-repo version). **See G34 for the cost.**
- **G34 — (nebula) the SKY130 library costs 16.5 s to PARSE, per ngspice
  process.** Measured: the same netlist takes **0.02 s** on generic BSIM4
  cards and **16.5 s** on the SKY130 lib — a ~700× penalty that is almost
  entirely parsing, not analysis. It amortises completely if the process is
  reused: 20 points in one process took 16.57 s, **200 points took 16.89 s**
  (~0.002 s marginal per point). Therefore **the device layer must hold
  ngspice processes open and `alter` between sizing points; one `subprocess`
  call per evaluation is not viable against a PDK** — at 1e5 PPO steps that is
  19 days for TT alone versus the 1.8 hours the generic-BSIM4 cost table
  records. This revises G23: batch mode is still right, but processes must be
  REUSED, not respawned. **SUPERSEDED 2026-08-04 by G35 and G36:** `alter`
  turned out to be unsafe for W/L, so process reuse is NOT the answer — the
  trimmed library is, and it makes the question moot.
- **G35 — (nebula) `alter` CANNOT move W/L of a subckt-wrapped PDK device.
  It fails SILENTLY, returning plausible wrong numbers.** Measured against
  fresh-parse ground truth:

        W (um)   bin vs baseline     gm fresh    gm altered   error
        4.5      SAME bin [3,5]      2.358e-3    2.272e-3     -3.6%
        6.0      crosses to [5,7]    3.175e-3    2.407e-3     -24.2%
        9.0      crosses to [7,100]  3.6e-3      NaN          broken

  **Even within one bin it is wrong**, which rules out "only alter inside a
  bin" as a workaround. Cause: the `sky130_fd_pr` subckt derives
  `ad/as/pd/ps/nrd/nrs` from W by `.param` expression at PARSE time. `alter`
  writes the `w` instance parameter and leaves every geometry-derived
  parasitic at its old value, so the device becomes internally inconsistent.
  Two further traps found on the way: `alter @m...[w] = 3.2u` applies
  `scale=1e-6` a SECOND time (giving 3.2e-12 m), so alter takes PLAIN numbers
  exactly as the netlist does; and `alter xm1 w=...` (the X-instance form)
  does not work at all — only the hierarchical
  `@m.xm1.msky130_fd_pr__nfet_01v8[w]` form reaches the device. In the failing
  cases ngspice printed `Error: no model available for w=...` and then
  **`print @m1[gm]` still returned the stale value** — exactly the §8 rule 10
  failure mode. **Do not use `alter` for device geometry.** It is fine for the
  ideal R/C/I elements (rs, cs, rl1/rl2, cl1/cl2, it1/it2), which are not
  subckts.
- **G36 — (nebula) TRIM THE PDK LIBRARY: 16-35 s -> 0.42 s, bit-identical.**
  `nebula/device/spice/sky130_nfet_only.lib.spice` includes only the
  `nfet_01v8` model files instead of the 30 device families the full
  `sky130.lib.spice` loads per corner (20 V devices, BJTs, ESD, RF, the whole
  pfet set — none of which the S2 CTLE instantiates). All five process corners
  provided. Verified **exactly equal** (`rel=0, abs=0`) to the full library on
  gm, gmbs, vth, id, g_dc, g_pk and inoise_total across 5 corners x 4 (W,L)
  points chosen to straddle three W bins and two L bins —
  `nebula/tests/test_trimmed_lib.py`, 22 tests, 7 s. Goldens captured from the
  full library live in `tests/fixtures/sky130_full_lib_golden.json`; a
  `slow`-marked test re-derives them after a PDK update.
  **Gotcha within the gotcha:** a trimmed library MUST declare
  `.option scale=1.0u` itself. The full library sets it in
  `libs.tech/ngspice/all.spice`, which the trim does not include; omit it and
  W=5 means five METRES, producing G31's misleading "could not find a valid
  modelname" from the opposite cause.
- **G37 — (nebula) `2*I_tail*RL` is a PEAK, not a peak-to-peak, and it is a
  steering ceiling, not the linear swing.** Three separate traps in one
  formula, and session 9c hit all three. Full steering puts `2*I*RL` across
  the load in EACH polarity, so the differential output spans `+/- 2*I*RL` and
  the peak-to-peak figure is **`4*I*RL`** — 9c compared required swings against
  `2*I*RL` read as peak-to-peak and so ran 2x pessimistic. Then even `4*I*RL`
  is the hard ceiling with the device slammed into triode; the number a
  compression check needs is the **1 dB gain-compression** point, measured off
  a `.dc` differential transfer curve. At the corrected reference: 1427 mVpp
  linear, 2161 mVpp saturation-limited, 2281 mVpp steering, 2400 mVpp
  textbook. And third: at this operating point the pair is still saturated far
  past the 1 dB point (vds 1.29 V vs vdsat 0.079 V), so the limit is
  **steering, not headroom** — which is why raising the supply barely helps
  (G39). Use `sky130_runner.swing_limits()`; it returns `None` rather than
  falling back to a computed ceiling when the sweep never reached compression.
- **G38 — (nebula) on SKY130 `nf` does NOT multiply device width.** `W` is the
  TOTAL width and `nf` only splits it into fingers. Measured at W=40,
  1.5 mA/side: gm = 14.22, 13.68, 12.62, 13.12, 12.29, 11.79 mS for
  nf = 1, 2, 4, 8, 16, 32 — a **+/-10% NON-MONOTONIC** parasitic effect. The
  generic-BSIM4 netlists in the same directory write `m={NF}`, where nf really
  is a multiplier, which is where `BOUNDS["nf_in"]`'s "1-32 multiplies
  effective W" came from. Consequence for the action space: `nf_in`/`nf_tail`
  are near-dead dimensions AND non-monotonic, which is worse than dead for a
  policy gradient. Extra width must come from W (bin-capped at 100 um) or a
  device multiplier.
- **G39 — (nebula) the SKY130 3.3/5 V devices cannot do S3 at 2.5 GHz.**
  `nfet_g5v0d10v5`'s model bins give it a **minimum L of 1.0 um** against
  0.15 um for `nfet_01v8`, and f_T falls ~1/L^2. Measured at VDD=3.3 V over
  six sizings: best peaking **2.66 dB**, below S3's 3 dB floor, at
  1.32-1.38 GHz; pushing RL to 1200 ohm for gain moves the peak to 0.398 GHz
  and drives the Nyquist boost to **-5.14 dB** (worse than a wire where the
  data is — the CLAUDEwa §3 reading-(a)/(b) counterexample, on a second device
  family). Swing improves only +12%, because the limit is steering not
  headroom (G37), and power rises 5.4 -> 9.9 mW. **Rejected on f_T, not on
  headroom.** Do not re-propose "use a higher-voltage device" without reading
  this.
- **G40 — (nebula) a bare yield percentage is not evidence of coupling, and
  ours was not.** "5.3% of random samples meet S3, therefore S3 is a coupled
  constraint" does not follow: a hit rate depends entirely on how wide the box
  was drawn. The box-independent test is to decompose the conjunction and
  compare the joint against the product of its marginals. Done for S3 across
  three box widths: the raw yield swings **5.5x** (17.25% -> 8.73% -> 3.13%)
  while the coupling factor stays at **1.00-1.06x**. The conditions are
  independent; there is no coupling. One trap inside the trap: designs with no
  peak at all fail both conditions together and make them look positively
  associated, so the statistic must also be computed **conditional on a peak
  existing** (that is the 1.04x figure). Costs the same simulations as the
  bare percentage — three counters instead of one. Generalise the habit: any
  "X% therefore hard" claim in this project needs the marginals next to it.
- **G42 — (nebula) a search DIMENSION can be worth less than a constant, and
  `cl` is.** Pinning `cl` at 150 fF and holding every other bound raises the S3
  random-search yield from **8.73% [7.54, 10.09] to 13.54% [12.08, 15.16]** —
  disjoint intervals, 2000 paired samples. The whole 10-500 fF bound is worse
  than a single well-chosen value inside it, so the axis is not carrying
  information, it is spending samples. That is now **two** of nine sampled
  parameters that measurement says should not be in the action space
  (`nf_in` is the other, G38). **The trap this sets: improving the box
  improves the RANDOM-SEARCH BASELINE, which is what CLAUDEwa §7 requires RL
  to beat at G3.** 8.73% -> 13.54% moves the bar from ~11 samples per hit to
  ~7. Take the better box anyway — a baseline that was weak only because of a
  badly chosen dimension is not one worth beating, and a judge will ask why
  `cl` was searched at all — but record it as a deliberate decision, not as a
  silent improvement that raises the bar three weeks before the gate. Full
  data: `nebula/CL_SENSITIVITY.md`.
- **G43 — (nebula) a RAW coupling factor tracks the no-peak fraction, not the
  coupling.** G40 already said the statistic must also be computed conditional
  on a peak existing. Session 10b shows *how badly* it matters, as a trend
  rather than a footnote. Sweeping `cl` over 50/100/150/250/400 fF:

        raw coupling          1.00  0.94  0.82  0.74  0.68   monotone
        conditional coupling  1.08  1.10  1.01  1.02  1.05   flat
        designs with a peak   1673  1559  1469  1313  1168   monotone

  The raw factor moves by 32% while the real one does not move at all, and it
  moves in lockstep with the number of designs that have no interior maximum.
  Those fail A and B together and make the two look positively associated for
  a reason that has nothing to do with S3. **Never quote a raw coupling factor
  without the conditional one beside it** — it is the no-peak fraction in
  disguise. (One honest wrinkle: at `cl` = 100 fF the conditional interval
  [1.02, 1.20] does exclude 1.0, so there is a real ~10% adverse effect there.
  Ten percent cannot explain a 8.73% yield; G40 stands.)
- **G44 — (nebula) `meas ac MAX ... TO=50g` reports the SWEEP EDGE as a peak.**
  The `has_peak` filter in `s3_yield.py` is
  `peaking_db > 0.25 and f_pk_hz > 50e6`, which catches a monotonically
  FALLING response (it reports `f_pk` at the 10 MHz start) but **not** a
  response still rising at the top of the sweep, which reports `f_pk` at
  ~47.9 GHz and sails through both tests. Observed on a real sample:
  rl=111, cl=50f -> `f_pk = 47.863 GHz`, i.e. no interior maximum at all.
  Those designs are counted in `n_has_peak` and should not be. It does not
  affect S3 itself (47.9 GHz fails the 1.25-2.5 GHz window anyway) but it
  inflates the has-peak denominator and therefore slightly biases the
  conditional coupling factor. Fix is a symmetric upper guard
  (`f_pk_hz < 0.9 * f_sweep_max`); not applied yet because it changes a
  published statistic and needs the re-run to go with it.
- **G25 — (nebula) the channel needs TWO loss numbers, not one.** A CTLE's
  peaking is RELATIVE (|H(f_nyq)|/|H(0)|), so what it equalises is the
  channel's **tilt**, not its absolute loss. Comparing peaking against
  absolute loss silently assumes a channel that is lossless at DC — which no
  real channel is. `LinkConfig` now carries `channel_loss_db_at_nyquist`
  (swept) and `channel_loss_db_at_dc` (placeholder, 1.0 dB, no measured
  provenance), with `channel_tilt_db` derived. Two amplitudes follow:
  `v_in_diff_pp_v` (long-run level, set by DC loss — this is what the
  compression check has to survive) and `v_in_nyquist_pp_v` (the content the
  eye is built from). Do not collapse them back into one.
- **G17 — (nebula) `nebula/common/params.py::BOUNDS` is empty ON PURPOSE.**
  `param_space()` raises until a human fills it from the G1 hand-design.
  CLAUDEwa.md §8 rule 6 forbids an agent choosing parameter ranges: too wide
  and ngspice will not converge over most of the box, too narrow and the
  optimum is outside it — and neither failure announces itself, they both
  just look like "RL didn't work". Same rule covers the reward tolerances in
  `RewardConfig` and the two link numbers in `LinkConfig`; all four are
  required arguments with no defaults for exactly this reason.
- **G18 — (nebula) the millivolt calibration is one function.**
  `nebula/link/calibration.py`. NRZ symbols are +/-1, so a fully open eye is
  2.0 normalised units and maps to the FULL differential peak-to-peak swing;
  one normalised unit is HALF the swing. `DeviceResult.vout_swing_v` is the
  compression limit (a device property), not the actual swing — the actual
  swing is `min(g_dc * v_in_pp, vout_swing_v)`. Nothing else in the codebase
  may multiply a normalised amplitude by a voltage. A factor-of-two error here
  crashes nothing and silently moves the S8 spec line by 2x.
- **G19 — (nebula) run its tests separately or together, both work:**
  `python -m pytest nebula/tests -q` (228 tests, <1 s) or
  `python -m pytest tests nebula/tests -q` (293 total, ~50 s). The two
  conftest.py files put different things on `sys.path` and do not collide.
- **G45 — (nebula) ngspice failures under machine LOAD are transient and do
  not reproduce.** A 2000-point run at 11 workers, sharing the box with a
  second pool and a pytest run, reported **20 failures**; the identical
  configuration and seed on a quiet machine reported **0/1890**. Cause is
  process-launch or temp-directory contention on Windows, not any property of
  the design. Harmless in `s3_yield.py`, where a failed run drops out of the
  denominator. **NOT harmless in a corner experiment**, where scoring a
  transient failure as "this design fails at SS/125C" biases the corner yield
  downward and does it silently, because a failed corner and a failed spec
  look identical once counted. `s9_yield.py::evaluate_at_corner` therefore
  **retries once** and reports retries separately from hard failures — a
  genuine non-convergence fails twice and is real; a transient one succeeds on
  the retry and is reported as noise. Every stage prints a `health:` line
  (simulated / headroom-rejected / hard failures / retried) so the denominator
  is never implicit.
- **G46 — (nebula) "slow-hot is the worst corner" is FALSE for a two-sided
  spec, and S3 is two-sided.** The S9 screen was built on the standard
  intuition — ss/0.95V/125C, ff/1.05V/0C, ss/0.95V/0C. Promoting its survivors
  to all 45 corners shows every remaining failure lands at **125 C on ff, sf or
  tt**, and **none on ss at any rail**. Mechanism: a FASTER device has higher
  gm, which pushes the peak UP in frequency and out through S3's 2.5 GHz top
  edge. A one-sided spec (max power, max noise) has a worst corner; a spec with
  a window has a worst corner per EDGE, and the two are on opposite sides of
  the process axis. **Choose corners per spec edge, not per folklore** — and if
  a corner set was chosen by intuition, promote a sample and check, because the
  screen will look perfectly healthy either way.
  **REFINED 2026-08-05 (session 11, `ROBUST_GEOMETRY.md` §5).** The mechanism
  is real but NOT symmetric, and the asymmetry matters. Among the 100
  corner-fragile designs: those sitting BELOW the window centre die at SS 4.5x
  more often than at FF (45 vs 10), as predicted — but those ABOVE the centre
  die about EQUALLY at both (29 vs 27), which the clean two-mechanism story
  does not predict. Cause: **SS has two ways to kill a design and FF has one.**
  Lower gm drops f_peak (killing the low side) AND drops peaking toward the
  3 dB floor (killing anything with little peaking margin, at any frequency).
  SS's 69 failures split 40/26 across those two routes; FF's split 19/19. Do
  not write "designs above the centre are predominantly killed by FF" — 29 vs
  27 on 56 events is a coin flip. Note also that "which corner kills the most
  designs" (`ss/0.95/125`, at the screen stage) and "which corner does the
  screen MISS" (fast-hot, at the promotion stage) are different questions with
  different answers; G46 as originally written is about the second.
- **G47 — (nebula) a corner SCREEN can only be wrong in one direction, and
  three corners are worth 98.7% of forty-five.** The screen corners are a
  SUBSET of the 45, so any design the screen rejects the full sweep would also
  have rejected: **no false negatives, by construction**, and the 3-corner
  yield is a hard upper bound on the 45-corner one. The only possible error is
  a false positive. Measured: 155 designs passed 3 corners, **153 passed all
  45** — the full sweep consumed **64% of the wall clock to reject two
  designs**. Budget the RL reward at 3-5 corners and put the 45-corner sweep in
  a final verification tier; that is a ~15x throughput factor over a training
  run. **The caveat that limits this:** the tail is still two ideal current
  sinks, which do not lose current at SS/125C or drop out of saturation at
  0.95 VDD, so every corner spread measured so far is an UNDERSTATEMENT and
  8.10% is an OPTIMISTIC bound. Re-run `s9_yield.py` unchanged once a tail
  transistor exists before relying on the 3-corner shortcut.
  Full data: `nebula/S9_YIELD.md`.
- **G48 — (nebula) 11 cores do NOT buy 11x; budget ~100 ms per corner
  evaluation, not 0.42 s and not 38 ms.** Measured on 220 identical tasks:
  1 worker 318 ms/task, 2 workers 179 (1.78x), 4 workers 150 (2.11x), 8
  workers 106 (3.00x), 11 workers 100 (3.18x). **Efficiency collapses after
  2 workers and the curve is flat past 8** — 8 to 11 buys 6%. Each run spawns
  a process, parses the trimmed library and writes `wrdata` files, so wall
  clock is dominated by process launch and disk I/O, and extra workers contend
  for the same disk. Two ways to get this wrong: dividing the 0.42 s single-run
  figure (G36) by the core count (predicts 38 ms, off by 2.6x), or quoting the
  serial number for a parallel run (predicts 318 ms, off by 3.2x). Both have
  appeared in cost estimates in this project.
- **G49 — (nebula) a 47-minute experiment's raw results were gitignored, and
  they are gone.** `s9_yield_results.json` is `.gitignore` line 67, filed under
  "RUN ARTIFACTS — regenerable. Nothing here is an input to anything." It was
  regenerable in principle — the Latin-hypercube sampling is seeded — but
  nobody had to regenerate it until session 11 wanted the per-design
  coordinates behind `S9_YIELD.md` §4's 155/100 split, at which point it cost
  **7560 fresh SPICE runs / 23 min** to get back. It would have cost the full
  47 min if the population had not been seeded, and it could not have been
  recovered at all if the box or the seed had moved in between.
  **The rule: an experiment's output is TRACKED if any deliverable quotes a
  number from it.** A results file that took longer to produce than it takes to
  review is an INPUT to the write-up, not a build artifact.
  Two further things the loss cost, both worth knowing before trusting the word
  "regenerable" again: the JSON stored only **counts and design indices**, so
  even surviving it would not have carried per-design `f_peak`/`peaking` and
  this analysis would have needed the re-simulation anyway; and regeneration
  reproduces bit-identically only on the same machine, PDK and trimmed library.
  `nebula/experiments/robust_geometry_data.csv` is tracked for exactly this
  reason (1890 rows, lossless `repr` floats), and it makes the whole session-11
  analysis re-runnable with **no simulator**. `check_reproduction()` asserts the
  regenerated population against 10d's published counts and refuses to draw a
  figure on a mismatch — without that gate a silently different population
  would have produced a plausible, wrong write-up.
  **Same class of loss, one level up:** the commit that added
  `ROBUST_GEOMETRY.md` also rewrote this section and collapsed G2–G28 into
  one-line stubs, dropping G29 and G31–G47 entirely. It was recovered by
  splicing §9 out of commit `4a286a8` (44 gotchas, 347 lines) and re-appending
  G45–G49. **Before rewriting HANDOFF wholesale, diff the gotcha count**:
  `grep -c '^- \*\*G' HANDOFF.md`.
- **G50 — (nebula) `@m[cgg]` is NOT the gate load a driver has to supply. It
  understates it by 1.9-2.7x, silently.** BSIM4's `cgg` instance parameter is
  the **intrinsic** gate charge derivative. Two real terms are missing:
  (a) the gate **overlap** capacitance — SKY130's `nfet_01v8` card carries
  `cgso = cgdo = 2.449e-10 F/m`, i.e. ~3.9 fF per side on a 16 um device;
  (b) **Miller multiplication of C_gd** by the following stage's own voltage
  gain. The trap is that the *intrinsic* C_gd of a saturated device really is
  ~0 (measured 1.8e-17 F), which makes "C_gd is negligible" feel safe — but
  the *overlap* C_gd is not, and it is multiplied by (1 + |A|). Measured on
  the loading stages of `CL_RANGE.md`:

        stage         W      |A|    @m[cgg]    real load    ratio
        summer_min    4 um   1.34    3.27 fF     6.56 fF     2.00x
        summer_max   12 um   3.00    9.68 fF    24.43 fF     2.52x
        slicer_max   16 um   3.52   12.71 fF    34.34 fF     2.70x

  The ratio grows with gain, which is the signature. **Measure it as the AC
  current the driver must supply** into the gate under the drive the real
  circuit applies (differential, here), through a zero-volt ammeter:
  `C = Im{i(Vgp)} / (omega * v_gate)` — `nebula/device/cap_probe.py`. And
  cross-check it against the primitives (`analytic_load_ff`), because an AC
  current is not self-evidently a capacitance; agreement is 1.0% median.
  Consequence if ignored: a `cl` that is 2x low moves f_p2 and hence f_peak by
  ~0.5 octaves, half of S3's entire window, and nothing errors.
- **G51 — (nebula) a routing/parasitic number cannot be measured from this
  PDK install, but it can be DERIVED from it.** `C:\\Users\\DELL\\sky130A` carries
  `libs.tech/ngspice` and `libs.ref/sky130_fd_pr/spice` only — no tech LEF, no
  magic techfile — so there is no interconnect model to query. The route that
  works: SKY130's own vpp finger capacitors state both their total capacitance
  and their metal run length in squares
  (`cap_vpp_01p8x01p8_m1m2_noshield`: `ctot_a = 7.833e-16`, `rat_m1 = 0.387`
  over `22*rm1` squares, `rat_m2 = 0.596` over `28*rm2`), so capacitance per
  micron = rat*ctot/(n_sq*width) = **0.0984 fF/um (m1), 0.1191 fF/um (m2)**.
  The only declared input is the metal width (0.14 um, a design rule), and it
  is a DIVISOR — assume it wrong high and the answer comes out low. The figure
  is an UPPER bound for routing: a finger cap has a minimum-spaced neighbour on
  both sides and its `ctot` includes the m1-m2 coupling that makes it a
  capacitor. Prefer this to any remembered fF/um: it is in the repo's own PDK
  and it is parsed, not recalled.

## 10. Environment

- Windows 11, PowerShell 5.1 (+ Git Bash available), Python 3.13.14,
  numpy 2.2.6, scipy 1.15.3, pytest 9.1.1, matplotlib, pandas. No scikit-rf,
  no torch verified in current env (ml_equalizer imports torch — untested).
- git 2.52 for Windows. **This checkout: `main`, initial commit 2026-08-04,
  NO remote configured** (session 10a / G41). The private GitHub repo
  https://github.com/jaikaushik-prog/serdes-dsp-framework.git still exists and
  still has the PDFs in its baseline commit; it is an **unrelated history** to
  this one and wiring them together is a decision, not a chore — see G1 as
  amended. Credentials for `jaikaushik-prog` are in Windows Credential Manager.
  Commit identity comes from the global config (G12); never pass `-c user.*`.
- Cadence/Xcelium NOT available on this machine (Phase 4 blocked on access
  or open-source simulators).

## 11. Communication guidance (for agents working with the owner)

- The owner is a beginner: explain every change in plain language — what,
  why, what it implies — so they can present the work to their professor as
  AI-assisted work they fully understand. Prepare "professor-ready"
  one-sentence takeaways for findings and figures.
- Findings are presented with figures: fig1 (eyes closing = the problem),
  fig2 (waterfall + implementation penalty), fig5 (engine cross-validation),
  fig7/fig8 (CTLE role findings). fig3 answers "when does each EQ stage stop
  sufficing" (professor's framing).
- Professor context so far: responded to fig1 with the classic escalation
  ladder (CTLE → FFE → "DSP technique"); the framework already implements the
  full DSP receiver — communication should clarify rungs and offer fig3.

---

## 12. SESSION LOG (append-only — newest at bottom; NEVER delete old entries)

### 2026-07-18 — Session 1 (audit) 
Mapped reference library; audited codebase; wrote docs/ROADMAP.md with
findings (4 confirmed bugs, modeling gaps, phased plan).

### 2026-07-18 — Session 2 (Phases 0–1)
git init + baseline; fixed 7 correctness bugs (scrambler, MLSE, seeds,
references, theory, two-pass EQ, README FEC); 28 tests. Built waveform
engine: Channel.apply, tx_waveform w/ jitter, CTLE class, Alexander-BB
CDRSampler (gearshift+clamp), MMSE cursor fix, adapt_start, JTOL mode.
48 tests. Commits: baseline, Phase 0, Phase 1.

### 2026-07-18 — Session 3 (figures + Phase 2)
make_report_figures.py (figs 1–4, palette-styled). statistical_eye.py:
ISI-PMF engine, wᵀRw noise, bathtub, RJ fold; cross-validation (~3×
agreement, fig5); optimize_ctle with crossing_jitter_ui() CDR-feasibility
constraint (Finding #1: CTLE's job = timing health). CLI modes statistical/
optimize; figs 5–7. 60 tests. Commits: figure generator, Phase 2.

### 2026-07-18 — Session 4 (Phase 3a + GitHub)
pd_mode='mm_postffe' (frozen timing-FFE + MM PD; sign convention fixed and
documented); locks where Alexander fails; jitter flat ~20 mUI (fig8).
Finding #2: ADC clipping limits 0-dB-CTLE BER (17 % clipped); added
clip_probability(), adc_clip_frac, calibrated clip constraint. 65 tests.
Pushed to private GitHub; commit authors rewritten to Jai Kaushik (G12);
HEAD 3aa5b28. Explained figs/circuits to owner for professor comms.
Created HANDOFF.md + CLAUDE.md (this change).

<!-- NEW SESSIONS: append below this line using the same format:
### YYYY-MM-DD — Session N (short title)
What changed, why, key results, new gotchas, commits/hashes, test count.
Then update §2/§5/§6/§7/§8/§9 above if they changed. -->

### 2026-07-23 — Session 5 (UCIe direction + owner takes FFE; no code change)
Docs-only session; no code touched, tests unchanged (still 65 passing).
- Professor pointed owner at external repo `hussin-mohamed/UCIE_GP`. Analyzed it:
  it is the UCIe 3.0 **logical/digital** PHY (SystemVerilog + UVM, 14 nm, 16
  lanes, up to 32 GT/s NRZ forwarded-clock, 500 MHz logical clock). Blocks:
  link-training FSM, sideband, TX path (byte-to-lane -> LFSR scramble ->
  serializer), RX path (detectors -> lane-assembly -> descramble). It
  **explicitly excludes the analog front-end / channel / SI modeling.**
- Relationship to this framework: two different halves of a link at two layers
  (this repo = analog/DSP electrical PHY; UCIE_GP = digital logical PHY). They
  meet only at the serializer-output -> analog-TX seam (where TX-FFE lives).
  UCIE_GP does NOT improve this framework's analog models, but offers (a) a
  proven UVM verification template for our un-simulated rtl/*.sv (§8 #5), and
  (b) a serializer/scrambler RTL reference.
- Group task = build the analog PHY around UCIE_GP, split 6 ways: channel,
  serializer, driver, CTLE, DFE, FFE. **Owner chose FFE** (most AI-tractable:
  pure DSP/math, no transistor-level ambiguity, existing code to build on).
- Professor answered scope Q1: aim for the **high-rate regime WITH DSP
  equalization** (not light UCIe NRZ). So this framework's context is on-target;
  FFE = a real multi-tap adaptive equalizer, not token de-emphasis.
- Recorded the FFE math+build plan as §8 item 0. Next: teach Part A step 1
  (ISI + why an FFE is needed) in beginner plain language.
- Added §3 reference row for UCIE_GP and §1 "New Direction" paragraph.
- Professor then sent his own 12-page handwritten FFE note (`Part 11 FFE.pdf`);
  analyzed it in depth (added §3 reference row). It is effectively the owner's
  FFE syllabus and maps onto the §8 item-0 plan. Verified his boosting formula
  (K=1/3 -> 9.54 dB). Flagged a mismatch in his 3-tap zero-forcing worked answer
  (see §3 note) as a question to bring back to him.
- Taught Part A step 1 (ISI/pulse response) in chat, then built `ffe_learning/
  ffe_demo.py` to VISUALIZE it (added to §2): channel low-pass -> ISI -> eye
  closes -> 7-tap zero-forcing FFE -> eye reopens, plus channel/FFE/combined
  freq response. Teaching point captured: zero-forcing over-boosts a lossy
  channel (taps exploded to ~5.8 / main tap 1.27 -> noise enhancement) which
  motivates MMSE (already in equalizers.py) as Step 3.
- NEXT: Part A step 2 = zero-forcing math by hand (using professor's 3-tap
  example, which also resolves the tap-sign question).

### 2026-08-03 — Session 6 (Nebula track: interface freeze + mocks + tests)

New parallel project, separate contract: **`CLAUDEwa.md`** — the Nebula
competition (Astera Labs x BITS Goa), RL-driven CTLE sizing for a 5 Gbps PCIe
Gen2 link, team of three, final deadline 15 Sept 2026. Added §2 repo-map
entries, §8 item -1, and gotchas G16-G19.

**What was built.** The thing CLAUDEwa.md §5.1 says must exist before any
implementation: `common/types.py` plus mocks and interface tests for all three
layers, so three people can build in parallel against a frozen interface.

- `nebula/common/types.py` — §5.1 contracts verbatim (Corner, TargetSpec,
  DeviceResult, LinkResult), the §3 spec constants with per-row provenance
  comments, and `all_corners()` = the 45-corner S9 grid with TT/1.00/27 first.
  One deliberate strengthening of §5.1: numeric fields are `Optional[float]`
  and `__post_init__` enforces `ok=True <=> every field finite` /
  `ok=False <=> fail_reason set and no numbers`. Failure carries `None`, not
  `nan`, because `None` explodes on first arithmetic whereas `nan` propagates
  silently into a reward and poisons a training run without an error message.
- `nebula/common/design_equations.py` — §6 equations, plus
  `cross_check_extraction()`: the §6 "if A_dc disagrees, stop" gate as code.
- `nebula/common/params.py` — action-space names from §5.2. **BOUNDS is empty
  and `param_space()` raises.** See G17.
- `nebula/device/` — `evaluate()` protocol, `safe_evaluate` (any exception ->
  `ok=False`), `reject_bad_fit` (§5.3b), and a synthetic square-law mock whose
  headroom checks make a large slab of the sizing space return `ok=False`,
  which is what the RL loop must learn to avoid.
- `nebula/link/` — `calibration.py` (the §5.3a conversion, see G18),
  `config.py` (two required numbers with no defaults), `interface.py`
  (`propagate_device_failure`, `safe_evaluate_link`), synthetic bridge mock.
- `nebula/rl/reward.py` — the §9 shortfall reward: non-positive, saturating at
  zero, per-spec normalised, eight terms (S3 x2, S4, S5, S6, S7, S8 x2),
  `worst_corner_reward` = min over corners, `total_reward` = + discriminator.
  Failure floor defaults to `-N_SPEC_TERMS`, which is the mathematical minimum
  of R_spec rather than a tuned penalty.

**Tests: 228 new, all passing, <1 s.** `python -m pytest nebula/tests -q`.
Existing suite re-run before and after: **65 passing, unchanged**. Together:
293 passing, ~50 s (G19). Highlights: `test_mv_calibration.py` is the
dedicated hand-computed test §5.3a demands (every expected value derived in a
comment, not by calling the code under test); `test_reward.py` pins "no bonus
for exceeding a spec" by showing a met spec cannot pay for an unmet one;
`test_design_equations.py` pins the factor of two in `1 + gm*Rs/2`.

**Known asymmetry recorded, not fixed:** the §9 normaliser `(|x| + |tau|)`
depends on `x`, so for the S3 "match" terms an undershoot is penalised
slightly harder than an equal overshoot. Inherent to the §9 form; pinned by a
test so it stays known.

**Four decisions deliberately left to a human** (CLAUDEwa.md §8 rule 6 — all
four are required arguments with no defaults, so nothing runs until they are
stated): the 12 parameter ranges (needs G1), the two link numbers
(`v_in_diff_pp_v`, `channel_loss_db_at_nyquist` — neither is in the §3 spec
table), and the two S3 reward tolerances (`peaking_tol_db`, `f_peak_tol_hz`).

**Not done / next:** G0 and G1 are both overdue and both gate everything else.
No ngspice, no PDK, no netlist, no RL, no NRZ retarget yet.

### 2026-08-03 — Session 7 (Nebula: G0 passed, compression bug fixed, NRZ audit)

Three workstreams, all in `nebula/` plus one toolchain install. Tests:
**251 nebula + 65 existing = 316 passing** (`python -m pytest tests nebula/tests -q`).

**1. G0 GATE PASSED — `nebula/G0_RESULTS.md`.**
Installed Miniforge3 (user scope) and a `nebula` conda env with **ngspice 41**
from conda-forge, then ran a source-degenerated diff pair through all four
analyses. `.op`, `.ac`, `.noise` all work.

**The finding: `.disto` returns exactly 0.0 for BSIM4.** Proven with a
controlled A/B in one netlist — same topology twice, BSIM4 (`level=54`) vs
Shichman-Hodges (`level=1`), same source. level=1 gives HD3 = −59.3 dBc;
BSIM4 gives 0.0 for both HD2 and HD3. `.disto` itself works; BSIM4 just does
not implement the derivatives. Every open PDK is BSIM4-based, so no PDK fixes
it. **S4 must be measured by transient + FFT.** That fallback is built and
verified: HD3 = −89.7 dBc on the reference point, with HD2 ~180 dB down
(correct for a balanced pair — its absence would have meant an unbalanced
netlist). Cost: **0.256 s/corner vs 0.066 s** for AC+noise, so ~12 s for a
full 45-corner sweep with HD3. Recommendation recorded: put HD3 in the
promotion tier only, keeping the inner loop at 0.066 s/corner.

New gotchas G20–G23 (use `ngspice_con.exe`; `.disto` two-tone trap; PySpice
broken and not worth fixing; several `meas`/`fft` syntax traps).

Still outstanding for G0: **no PDK installed** (generic BSIM4 cards were used
— CLAUDEwa.md's own documented fallback), no tail-transistor headroom, no
corner model cards. The PDK is specifically needed for MIM caps and poly
resistors, without which the S7 area estimate has nothing behind it.

**2. Link-layer compression bug fixed (gotcha G24).**
`min(g_dc * v_in_pp, vout_swing_v)` was wrong twice over — wrong gain (DC
instead of the peaked response the eye actually sees, understating the swing
by exactly the S3 peaking) and a silent clamp where the correct answer is
"the small-signal model does not apply here". Now split into
`output_swing_pp_v()` (unclamped, takes `|H(f_nyquist)|`) and
`check_compression()` (returns a reason the link layer turns into `ok=False`).
Calibration conventions rewritten as C1–C4.

This immediately found something real: the previous mock reference sizing
drove **994 mVpp into a 460 mVpp linear limit** under a PCIe Gen2 minimum TX
swing. The replacement reference point (found by grid search, valid at all 45
corners AND every point of the loss sweep) has **g_dc = 0.27 — it attenuates
at DC.** That is not a mock artifact; it is how a CTLE driven by a
PCIe-class swing has to be biased, and G0's independent ngspice run agrees
(DC gain −14.6 dB, peak −6.3 dB, i.e. 8.3 dB of peaking at 1.26 GHz).
**Expect G1 to hit the same wall.**

Also per human decision this session:
- **Channel loss is now a swept axis, not an assumption.** `LinkConfig`
  requires `channel_loss_db_at_nyquist`; `sweep_channel_loss()` and
  `DEFAULT_LOSS_SWEEP_DB` (3–12 dB, read off S3's tunable range) give the
  reporting axis. Pass rate vs channel loss is a curve, not a number to defend.
- **Input amplitude is derived, not configured**: `v_in_diff_pp_v` is now a
  property = TX swing × channel attenuation, anchored to
  `PCIE_GEN2_TX_DIFF_PP_MIN_V = 0.8 V`. **Provenance is a secondary source
  only** (Renesas Gen2 PCIe Hardware Design Guide); the PCI Express Base Spec
  is paywalled and not in `resources/`. A human must confirm it before it
  appears in any deliverable — until then the report must call it an
  assumption.
- **Reward tolerances set**: ±1 dB peaking, ±10% of target f_peak
  (`f_peak_tol_frac`, fractional so it scales across S3's 1.25–2.5 GHz).
  Deliberately loose so the policy can learn at G3; real CTLEs tune in
  discrete steps a dB or two apart, so ±1 dB is at production granularity and
  ±0.5 dB would be tighter than the hardware. `TOLERANCE_SWEEP` makes it a
  reported axis rather than a hidden constant.

**3. NRZ retarget audit — `nebula/NRZ_RETARGET_AUDIT.md`. No code changed.**
CLAUDEwa.md §4.3 names five four-level assumptions; the audit found **24**,
grouped A–G with a SILENT/LOUD/PERF risk marking on each and a recommended
order of work. The dangerous ones are the SILENT group: the `0.75·Q` BER
prefactor (must become `1.0·Q` — leaving it reports BER 0.75× the truth),
`PAM4_RMS = sqrt(5)` in the AGC (scales every downstream amplitude by 2.24×),
`adc_vref = 4.0` (wastes two ADC bits on a ±1 signal), `sqrt(5·Σg²)` in
`crossing_jitter_ui` (overestimates jitter by 2.24×, would falsely declare the
CDR infeasible), and `CTLE.from_peaking`'s **absolute** 28/56 GHz pole
defaults — CLAUDEwa.md §12's named trap, callable without arguments.

**Next:** G1 hand-design (human, blocks the parameter bounds and the abstract),
PDK install, abstract due Aug 6.

### 2026-08-03 — Session 7 addendum (channel model corrected; reference verified)

Review follow-up on session 7. **320 tests passing** (255 nebula + 65 existing).

**1. Channel model had a real inconsistency — fixed (new gotcha G25).**
`link/mock.py` compared the channel's **absolute** loss at Nyquist against the
CTLE's **boost**, which is a *relative* quantity (|H(f_nyq)|/|H(0)|). That is
only self-consistent for a channel with exactly 0 dB loss at DC, and no real
channel has that — conductor, dielectric and connector losses are broadband.

The channel is now two numbers, and the CTLE equalises the difference:

    tilt_dB = channel_loss_db_at_nyquist - channel_loss_db_at_dc
    v_in_diff_pp_v     = TX swing attenuated by the DC loss   (long-run level)
    v_in_nyquist_pp_v  = TX swing attenuated by the full loss (eye content)

`channel_loss_db_at_dc` defaults to **1.0 dB** and is a **placeholder with no
measured provenance** — a human must replace it, ideally with a real `.s4p`
(§8 item 1), which would retire this whole parameterisation. A high-pass
channel (Nyquist loss < DC loss) is now rejected outright.

Compression is now checked against `max(equalised Nyquist level, long-run
level)`: a run of identical bits sits at the DC level through `g_dc`, and that
excursion has to fit linearly too.

Effect on the reference point: eye at 3 dB total loss moved 172 -> 129 mV
(the tilt there is 2 dB, not 3, so the CTLE is more over-equalised than the
old model thought). Everything still passes.

**2. The reference sizing was verified, not assumed (the falsifiable test).**
Eye height at TT across the whole loss sweep: **129 / 171 / 189 / 193 / 143 mV**
at 3/5/7/9/12 dB. Worst case over all 45 corners x 5 loss points is
**111.6 mV** against S8's 100 mV. So the DC attenuation (g_dc = 0.27,
-11.4 dB) is an *expected property* of a degeneration CTLE at PCIe TX levels,
not a symptom of a bad search. G0's independent ngspice run agrees
(-14.6 dB DC, -6.3 dB peak, 8.3 dB peaking at 1.26 GHz).

**3. The squeeze is from both ends of the loss sweep.** Maximum permissible
peak gain set purely by compression: **+0.5 dB at 3 dB loss**, rising to
+9.5 dB at 12 dB loss. So compression binds hardest at LOW channel loss (big
input) while S8 binds hardest at HIGH loss (small input). A single design must
satisfy the tightest of each. Worth knowing before G1: it is the low-loss end
that forces the low gain.

**4. The reference search was checked for degeneracy and is not degenerate.**
Concern raised: a search whose only constraint is "does not compress" is
trivially won by minimising gain. It is not, because in this topology
`vout_swing_v` scales with RL alongside the gain, and lowering RL also raises
f_p2 and hence the peaking. Measured, sweeping RL with everything else fixed:

    rl= 40  g_dc=0.090  pk=14.94 dB  -> 81/225 link evaluations COMPRESS
    rl= 60  g_dc=0.134  pk=13.31 dB  -> 45/225 COMPRESS
    rl=120  g_dc=0.269  pk= 9.74 dB  -> all ok, worst eye 111.6 mV, S8 PASS
    rl=200  g_dc=0.448  pk= 6.56 dB  -> 103/225 COMPRESS

The chosen point is bracketed by failures on both sides. (Correction to the
session-7 summary: low-gain designs fail by *compressing*, not by failing S8 —
the ranking was already on worst-case eye height, but the earlier one-line
claim about why low gain loses was wrong.)

**5. Cost scaled to a training run — the abstract's number.** At 1e5 PPO steps:
TT no HD3 **1.8 h**; TT with HD3 **7.1 h**; 45 corners no HD3 **3.4 days**;
45 corners with HD3 **13.3 days**. A **175x spread**, measured on this
machine, which is the quantitative justification for the three-tier fidelity
hierarchy. Recorded in `nebula/G0_RESULTS.md`.

**Note for G1:** `vout_swing_v` (600 mVpp at the reference point) is itself a
design variable — headroom, VDD, device sizing — not a constant. If gain turns
out to be the binding problem, that is the lever.

### 2026-08-03 — Session 8 (G1 hand-design audited against ngspice)

Owner did the G1 hand-design and populated `nebula/common/params.py::BOUNDS`.
This session verified it **against the simulator**, not by inspection.
**332 tests passing** (267 nebula + 65 existing). New: G26–G29.

**What was right.** The netlist (`nebula/device/spice/g1_handdesign.cir`) is
sound and uses the correct `1 + gm*Rs/2` degeneration factor. The reference
point reproduces: peaking **8.29 dB @ 1.259 GHz**, noise **0.275 mVrms**,
power **6.0 mW** — S3/S5/S6 all met with margin at TT/27C. Starting from the
already-validated G0 point rather than a fresh guess was the right call.

**1. The §6 cross-check silently failed and was reported as passing (G26).**
Every `let` after the `.ac` in that netlist errored — `@m1[gm]` is not
available in the `ac1` plot, only in `op1`. So `k_degen`, `Adc_predicted`,
`gain_error_db` and even `peaking_db` were never computed. The 8.19 dB figure
was correct arithmetic done by hand; the automated gate CLAUDEwa §6 says must
not be passed simply did not run. ngspice reports these as warnings, not
errors, and exits 0.

**2. Run properly, §6 AS WRITTEN FAILS ITS OWN GATE (G27).** Measured at the
G1 point (gm = 10.973 mS, gmbs = 3.583 mS, Rs = 800, RL = 120):

    simulated A_dc            -14.57 dB
    §6 as written             -12.24 dB   -> off by 2.33 dB   GATE FAILS (tol 1 dB)
    §6 + gmbs                 -14.29 dB   -> off by 0.28 dB   passes

§6 assumes the bulk is tied to the source. In a bulk process every NMOS sits
in the grounded substrate, so the moving source drives the body too and
`k = 1 + (gm + gmbs)*Rs/2`. gmbs/gm was **0.33** here — not a small term the
1 dB tolerance can absorb. `design_equations.predict()` and
`cross_check_extraction()` now take `gmbs`, defaulting to 0.0 so §6 verbatim
is still reproducible. Five new tests pin this.

**3. The bounds were audited with 2000 ngspice runs.** Latin hypercube over
the 12-dim box, one `.op`+`.ac`+`.noise` per point:

    90.7% simulate (0% non-convergence; 9.3% land in triode)
    90.7% meet S5 — free in this box     90.7% meet S6 — free
     5.3% meet S3 (peaking 3-12 dB AND f_peak 1.25-2.5 GHz)

**S3 is the binding constraint, not S5/S6.** But the box is not wrong: passing
points span peaking **3.06-11.88 dB** and f_peak **1.26-2.40 GHz**, i.e. it
reaches every corner of S3. The 5.3% is because S3 couples (gm, Rs, Cs, RL, CL)
and no axis-aligned box can be efficient against it — which is exactly what
the surrogate and OOD discriminator are for. **5.3% is the honest random-search
baseline G3 must beat. Recorded, not engineered away.**

**4. Two concrete bound errors fixed (G28).**
- `rl`'s provenance justified its 500 ohm ceiling with *"barely fits in
  VDD=1.8V"* — but the BSIM4 hand-design runs at **VDD = 1.2 V**. The 1.8 V
  came from the separate SKY130 netlist. At 12 mA and 500 ohm the load drops
  **3.0 V into a 1.2 V supply**. The ceiling is kept (at 1 mA it drops only
  0.25 V and that corner is useful) but it is now documented as JOINT with
  i_bias, and `params.headroom_ok()` rejects the infeasible pairs analytically.
- `cl` trimmed **5 pF -> 3 pF**: measured, no sample above 2.92 pF ever met S3
  (f_p2 falls below the peak window). Cost nothing, removed dead space.
- `nf_in` provenance said "ref 1" while the synthetic mock uses nf_in=4. Noted
  in the provenance string — they are different devices, do not compare.

Combined effect, re-measured over 400 samples: **9.5% rejected for free**
(no SPICE call), triode failures 9.3% -> 2.5%, and yield **2.7% -> 4.7% per
SPICE call**.

**5. Noise number is structurally sound.** Checked whether the bare model card
omits flicker noise: it does not — BSIM4's default noia/noib/noic are non-zero
and 1/f is present. Integrating from 1 kHz instead of 10 MHz changes the total
by <1%, so the S5 band sits above the flicker corner and is thermal-dominated.
The *magnitude* is still uncalibrated generic-BSIM4, not a PDK.

**6. SKY130 is installed but does not parse — precise diagnosis (G29).**
The PDK IS at `C:\Users\DELL\sky130_fd_pr` with all five corner files. The
blocker is not `sqrt()`: setting `set ngbehavior=hsa` in a **`.spiceinit`**
(not in `.control`, which is too late — `.include` is processed at parse time)
clears that. The real blocker is that the raw `sky130_fd_pr` repo is the
Spectre/HSPICE-oriented source form: `...__tt.pm3.spice` holds a `.subckt`
whose parameters are declared by a `.param` line INSIDE the body, which
ngspice reads as "13 formal but 0 actual params", and the corner file contains
**zero `.model` cards** so `sky130_fd_pr__nfet_01v8__model` is never defined.
**Fix: install `open_pdks` (or use `volare`), which generates the
ngspice-ready `libs.tech/ngspice/sky130.lib.spice`.** Do not keep patching the
raw repo. Estimated 1-2 h; it does NOT block the abstract.

**Still outstanding.** S9 is unverified — every number above is TT/27C, and
corner cards need the PDK. The bounds may not survive SS/125C.

**New this session:** `nebula/device/ngspice_runner.py` — batch-mode driver
(netlist template -> subprocess -> parsed `SpicePoint`). Not the full device
layer (no `DeviceResult`, no corners) but it is what made this audit possible
and is the foundation the real wrapper builds on.

### 2026-08-04 — Session 9 (contract corrections, SS6 gate moved to Python, SKY130 installed, NRZ fixes 1-3)

**Tests: 332 before -> 383 after.** (`python -m pytest tests nebula/tests -q`,
~77 s.) Split: `tests/` 65 -> 92, `nebula/tests/` 267 -> 291.
Nothing was deleted or weakened; two existing tests gained explicit arguments
where a dangerous default was removed.

**P0 — four corrections to CLAUDEwa.md, all applied.**

1. **SS6 now carries the body-effect term.** `k = 1 + (gm + gmbs)*Rs/2`, with
   the measurement table and the reason (bulk process, grounded body, moving
   source). Also recorded the hand-sizing consequence: `Rs ~ 3/gm` oversizes
   by a third, use `Rs ~ 3/(gm+gmbs) ~ 2.25/gm`; deep n-well would remove the
   term at an area cost, considered and rejected.
2. **New standing rule SS8 #9 — "a check that reports failure as a warning and
   exits zero is not a gate."** ngspice's exit code is never a success signal.
3. **Provenance audit of all 12 bounds** (see below).
4. **SS3 reframed:** S5/S6 marked *measured free* (90.7% each), S3 marked
   **the** binding constraint at 5.3%. The old "noise vs power will be the
   real fight" note is gone — it would have aimed the next session at the
   wrong problem.

**The provenance audit found the confusion was real but contained.** Three
bounds are supply-dependent and are now labelled as such — `i_bias` (its
12 mA ceiling is S6 evaluated at 1.2 V: 14.4 mW; at 1.8 V the same current is
21.6 mW and fails S6 outright), `rl` (joint with `i_bias`, and its string used
to cite 1.8 V), and `vcm_in`. The other nine are supply-independent. The stray
1.8 V came from `spice/g1_sky130.cir`, which really is an 1.8 V device — so
the number was not invented, it was transplanted. One unrelated defect found
and recorded rather than papered over: `rs`'s measured evidence covers
100-2000 ohm but the bound is 50-2500, i.e. the ends are extrapolation.

**P1 — the SS6 cross-check now lives in Python and can fail.**
New `nebula/device/crosscheck.py` + `nebula/tests/test_crosscheck.py`
(24 tests). It parses `.op` primitives and `meas` results out of raw ngspice
stdout, does the arithmetic in Python, and **raises**. `scan_for_silent_
failures()` greps for the G26 warning shapes first, so a dirty run can never
be read as a clean result; a short, justified benign-list keeps SKY130's
per-device conductance-reset warnings from crying wolf.

Three fixtures of **real captured ngspice output** are checked in under
`nebula/tests/fixtures/`, so the suite needs no simulator and runs in 0.2 s.
One of them is the historical broken run itself — the exact text that exited 0
while computing nothing — so the scanner is tested against the real thing.

**Verified falsifiable, twice.** A parametrised test corrupts A_dc by ±3 and
+12 dB and requires `CrossCheckFailure`. Separately, `raise_if_failed` was
temporarily neutered and 4 tests went red, confirming they are not vacuous.

**Running the netlist properly turned up more than G26 recorded.** The
`.control` block failed for a *second* independent reason: `.param` names such
as `{RS_OHM}` are not visible as `.control` vectors at all, so even
`let power_mw = v(vdd) * {ITAIL} * 1000` had nothing to multiply. All derived
arithmetic has been removed from `g1_handdesign.cir`; it now prints primitives
only and the file carries a comment saying why. New gotcha **G30**.

**A real inconsistency surfaced while building the fixtures (G32).** The two
netlists that describe "the same" G1 reference point had **different model
cards**, differing by exactly one parameter — `k2`, BSIM4's body-effect
coefficient, i.e. precisely the term the SS6 correction turns on:

        parameter        g1_handdesign.cir      ngspice_runner.py
        k2               absent                 0.05
        gm               11.154 mS              10.973 mS
        gmbs              2.787 mS               3.583 mS
        gmbs/gm             0.250                  0.327
        A_dc            -14.123 dB             -14.569 dB
        peaking            8.19 dB                8.29 dB

Every measured number in HANDOFF came from the runner; the `.cir` a human
opens and edits gave different ones. `k2=0.05` added to the netlist, which now
reproduces HANDOFF SS2 exactly (gm 10.97342 mS, gmbs 3.582543 mS,
A_dc -14.56892 dB, peak -6.279118 dB at 1.258925 GHz -> peaking 8.2898 dB).
This also explains session 8's unexplained 8.19-vs-8.29 dB discrepancy.

**P2 — SKY130 INSTALLED AND SIMULATING. G29 is cleared.**
Inside timebox. `volare` 0.20.6 into WSL2 Ubuntu (`pip install --user
--break-system-packages`; `python3-venv` is absent and needs sudo, so the venv
route is a dead end). `volare enable --pdk sky130 c6d73a35...` pulled the
open_pdks-generated tree, which **does** contain
`libs.tech/ngspice/sky130.lib.spice` with real `.model` cards and working
`.lib tt|ss|ff|sf|fs` sections — all five S9 process corners. Copied to
`C:\Users\DELL\sky130A` (libs.tech/ngspice + libs.ref/sky130_fd_pr/spice,
~52 MB, 856 files) so the existing Windows conda ngspice drives it.

`nebula/device/spice/g1_sky130_volare.cir` runs `.op` + `.ac` + `.noise`
against it cleanly. **The raw-repo blockers are gone**: no "13 formal but 0
actual params", real `.model` cards. `g1_sky130.cir` (raw-repo version) is
superseded.

Two things cost time and are now gotchas. **G31: sky130 instance W/L are plain
numbers in MICRONS**, because the lib sets `option scale=1e-6` and the subckts
default to `l=1 w=1`. Writing `W=5u` gives 5 picometres, falls outside all 180
model bins, and aborts with the *misleading* "could not find a valid
modelname". The generic-BSIM4 netlists in the same directory use SI metres —
do not copy W/L between the two families.

**The SKY130 run independently re-confirms the SS6 finding on a completely
different device model**, which is the strongest form this result has taken:

                            generic BSIM4        real SKY130
        simulated A_dc        -14.57 dB           -13.54 dB
        SS6 verbatim          -12.24 dB           -11.80 dB
          error                 2.33 dB             1.74 dB   BOTH FAIL (tol 1 dB)
        SS6 + gmbs            -14.29 dB           -13.41 dB
          error                 0.28 dB             0.13 dB   both pass
        gmbs/gm                  0.327               0.396

**gmbs/gm is WORSE on the real PDK (0.40) than on the generic cards (0.33)**,
so the correction matters more with the PDK, not less. Both fixtures are
pinned by tests.

**Caveat, stated plainly: that netlist is a toolchain smoke test, not a design
point.** VDD is 1.8 V (nfet_01v8), ideal tail sinks pull the sources to
-0.68 V, and Vds = 1.98 V exceeds the rail. Its AC numbers (peaking 3.82 dB at
**724 MHz**, noise 0.60 mVrms) show a stage that peaks *below* S3's
1.25-2.5 GHz window and is **0.99 dB below its own DC gain at Nyquist**. Not a
result about a design; a result about the toolchain.

That last point is worth keeping: **peaking and in-band boost are different
numbers.** A stage can show 3.8 dB of peaking, inside S3's band, and still
deliver less than its DC gain where the data lives. `DerivedAc` exposes
`peaking_db` and `nyquist_boost_db` separately and a test pins the distinction.

**P3 — NRZ retarget, the three named fixes only.**
New `python_models/modulation.py`: a `Modulation` object carrying
`(levels, thresholds, bits_per_symbol)` with **every** other quantity derived
(`mean_square`, `symbol_probability`, `max_level`, `rms`, `level_spacing`,
`is_adjacent`). PAM-4's `mean_square` comes out at exactly the 5.0 that was
hard-coded, because it is E[a^2] over {+/-1,+/-3} — no chosen numbers, per
SS8 rule 6. `PAM4` is the default everywhere, which is what kept the existing
suite green without editing it.

1. **`crossing_jitter_ui`'s `sqrt(5.0 * ...)` is now `sqrt(mod.mean_square *
   ...)`.** Highest priority because it is a *wrong result*, not a slow one:
   the PAM-4 factor on an NRZ link overestimates jitter by exactly
   sqrt(5) = 2.2361x and would have declared a lockable CDR infeasible. Pinned
   by a test asserting the PAM-4/NRZ ratio is sqrt(5) to 1e-12, plus a
   regression test reproducing the old literal for the PAM-4 path.
2. **`CTLE.from_peaking`'s pole arguments are now REQUIRED.** They defaulted to
   28e9/56e9 — absolute 112G frequencies — so `from_peaking(6.0)` silently
   built a 5 Gbps equaliser with poles eleven times above the band. There is
   no correct default because the right poles depend on fbaud, so there is now
   no default. A test shows the trapped construction delivers <1 dB of in-band
   boost where correct poles give >3 dB. Two existing tests now pass poles
   explicitly; what they assert is unchanged.
3. **`adc_vref = 4.0`: established MOOT, and left alone.** S2's topology is
   CTLE + slicer + 1-tap DFE — **there is no ADC in it.** `nebula/link/`
   imports neither `link_sim` nor `adc_model`, and
   `LinkConfig.to_link_sim_config()` still raises. So `adc_vref` cannot reach
   a Nebula number. Three tests pin that conclusion so it stays checkable
   rather than being a claim in a document.

**The staging boundary is enforced, not just documented.** `StatisticalEye`
now takes `modulation="pam4"` and **refuses** to run `ber_at_phase`,
`analyse` or `clip_probability` in NRZ mode, because audit groups A-E are
still four-level. Running anyway would report a BER 0.75x the truth —
optimistic, finite and plausible. A loud `NotImplementedError` costs one
traceback; the silent factor costs a wrong number in a report.

**ONE MEASURED RESULT CONTRADICTS THE RECORDED COST TABLE, and it is the most
consequential finding of this session (G34).** The 175x fidelity-tier spread
was measured on **generic BSIM4 cards with no PDK library**. On SKY130 the
same netlist takes **16.5 s instead of 0.02 s** — a ~700x per-invocation
penalty that is almost entirely *library parsing*, not analysis. If the device
layer spawns one ngspice process per evaluation, 1e5 PPO steps at TT alone is
**~19 days**, against the 1.8 hours the table records.

It amortises completely when the process is reused: 20 points in one process
took 16.57 s, **200 points took 16.89 s** (~0.002 s marginal each). So
**holding ngspice processes open and using `alter` between sizing points is
not an optimisation — it is the difference between feasible and infeasible**,
and it revises G23 (batch mode still right; respawning per evaluation not).

Load-bearing caveat, unproven: the probe altered resistors only. The input
pair is a **subckt** instance, so changing its W/L/nf may need `altermod` or
re-instantiation — and if that forces a re-parse, the amortisation does not
cover the parameters the policy moves most. **Measure this before the device
layer is designed around it.**

**Nothing else in SS2 was contradicted.** Everything else measured this
session agreed with it or sharpened it. The two other numbers worth carrying
forward are gmbs/gm = **0.40 on the real PDK** (up from 0.33) and the `k2`
model-card drift (G32), which was a genuine internal inconsistency rather than
a wrong published figure.

**Not started, by instruction:** S-parameter channel, any RL training, corner
verification. G2 remains unmet.

### 2026-08-04 — Session 9b (the parse-cost question settled; it changes the device layer)

**Tests: 383 -> 405** (+22, `nebula/tests/test_trimmed_lib.py`; 2 more behind
`-m slow`). Follow-up to G34, which was the session's most consequential
finding and was left with an unproven caveat. The caveat turned out to be
worse than stated, and the fix turned out to be somewhere else entirely.

**`alter` is not the answer — it is silently WRONG (G35).** Fresh-parse ground
truth vs `alter`, on the input pair's W:

    W=4.5 um, SAME bin [3,5]      gm 2.358e-3 vs 2.272e-3    -3.6%
    W=6.0 um, crosses to [5,7]    gm 3.175e-3 vs 2.407e-3   -24.2%
    W=9.0 um, crosses to [7,100]  gm 3.6e-3   vs NaN        broken

The **same-bin** failure is what kills it: this is not a bin-resolution
problem that could be avoided by staying inside a bin. The `sky130_fd_pr`
subckt derives `ad/as/pd/ps/nrd/nrs` from W by `.param` expression at PARSE
time, so `alter` moves W and leaves every geometry-derived parasitic stale.
And it fails in the §8-rule-10 shape: ngspice printed
`Error: no model available for w=...` while `print @m1[gm]` kept returning the
**stale** value. An RL loop sweeping W would have read the same gm for every W
and never known. Two side-traps recorded: `alter` applies `scale` a second
time (so it takes plain numbers), and the `alter xm1 w=` form does not work —
only the hierarchical `@m.xm1.m<subckt>[w]`.

**Trimming the library is the answer, and it is a bigger win (G36).** The S2
CTLE instantiates ONE device type; the full library parses 30 families per
corner. `nebula/device/spice/sky130_nfet_only.lib.spice` (all five process
corners) takes an invocation from **16-35 s, variable, to 0.42 s, tight** —
~40-80x — and is **bit-identical**: verified `rel=0, abs=0` on gm, gmbs, vth,
id, g_dc, g_pk and inoise_total across 5 corners x 4 (W,L) points straddling
three W bins and two L bins. Removing the *variability* matters as much as the
mean, because a variable per-point cost makes a fidelity schedule
non-deterministic. One trap: a trimmed library must declare
`.option scale=1.0u` itself — the full one sets it in `all.spice`.

**Revised cost at 1e5 PPO steps, TT only:**

    generic BSIM4, no PDK (the original table)        1.8 h
    full SKY130 lib, one process per evaluation      ~19 days
    TRIMMED SKY130 lib, one process per evaluation   ~11.7 h

So a PDK-backed inner loop is **~6.5x the no-PDK baseline, not 250x**, and
needs no process-reuse machinery. `alter` stays available for the ideal R/C/I
elements (not subckts) if that 6.5x ever needs attacking.

**Two smaller items closed.**
- **New CLAUDEwa.md §8 rule 9 — model cards and device parameters have exactly
  ONE definition in the repo.** Netlists and runners reference it; neither
  redeclares it. A human reading any netlist must see the values that produced
  the published numbers. (The old rule 9 became rule 10.) This is the standing
  rule for the `k2` class of bug found in session 9a.
- **`rs` bound tightened 50-2500 -> 100-2000**, i.e. exactly the range that
  was deliberately swept. Given the choice between extending the evidence and
  tightening the bound, the bound moved.

### 2026-08-04 — Session 9c (hand-sizing at the terminal; the G1 bias was wrong)

**Tests: 405 -> 407** (+2, `nebula/tests/test_noise_units.py`). Human-led
hand-sizing session at the ngspice prompt; these numbers come from twenty-odd
AC runs done deliberately, not from a script.

**1. `inoise_total` is RMS VOLTS, not V^2 — verified, and now pinned.**
Settled against a closed-form case (one resistor, 4kTR*BW): ngspice returns
**4.069e-06** for 1 kohm over 1 Hz-1 MHz, and sqrt(4kTR*BW) = **4.071e-06 V**.
Match to 0.05%. So every noise figure in this project is already in volts and
must NOT be square-rooted. Had the squared reading been right, the G1 point's
0.275 mV would have been 16.6 mV and **S5 would have flipped from "free at
90.7%" to failing by ~11x**. `test_noise_units.py` pins it, including a test
that states what the wrong reading would look like.

**2. THE G1 BIAS POINT IS BADLY MIS-BIASED. gm/I_D = 1.7 V^-1.**
A well-biased MOSFET runs at 8-15. At W=5 nf=4 and 1.5 mA the device needs
vgs = 1.34 V, so with the gates at VCM = 0.9 V the sources sit at
**v(s1) = -0.44 V** — below ground. Ideal tail sinks permit that; a real tail
transistor cannot, so the operating point is physically unbuildable even
though it simulates cleanly. Measured sweep at IT = 1.5 mA, VCM = 0.9:

        W    nf   gm(mS)   gm/ID   v(s1)
        5     4    2.577    1.72   -0.439
        10    4    4.822    3.21   -0.184
        20    4    8.735    5.82   -0.042
        40    4   12.992    8.66   +0.050
        80    4   19.850   13.23   +0.089

Width alone does not fix v(s1); VCM must rise too (it is a placeholder, not a
constraint — a real RX AC-couples and biases the gates itself). **Corrected
reference: W=40 nf=4, IT=1.5 mA, VCM=1.25 V -> gm = 12.62 mS, gm/I_D = 8.42,
v(s1) = +0.343 V, vds-vdsat = 0.74 V, noise 0.275 mV.**

**3. Consequences, and they move the design point.**
- **DC gain went from -6.4 dB to +5.1 dB.** The stage no longer attenuates.
  Session 7's conclusion that "a CTLE at PCIe levels has to attenuate at DC"
  was drawn on a device with gm/I_D = 1.7 and does not survive the bias fix.
- **The asymptotic peaking formula is now badly optimistic.** At Rs=200,
  20*log10(k) = 7.66 dB but the REALISED peaking is **0.00 dB** — the entire
  boost is eaten by the load pole. Do not size Rs from `20*log10(k)`.
- **f_z must sit BELOW f_p2 or there is no peak at all.** Measured at Rs=200,
  Cs=400f: RL=400/CL=100f (f_p2 = 3.98 GHz) gives 1.06 dB at 2.96 GHz;
  CL=200f (f_p2 = 1.99 GHz) gives **no peak whatsoever**. Lowering f_p2 does
  not move the peak down, it EXTINGUISHES it. The ordering f_z < f_p2 is a
  hard structural constraint, not a tuning preference.
- **Rs sets how much, Cs sets where — cleanly separated.** Sweeping Cs at
  fixed Rs=200 left `gdc` at 5.05 dB for every value while the peak moved
  7.96 -> 0.50 GHz. That separation is the single most useful fact for the
  presentation.

**4. Twelve configurations now MEET S3** (3-12 dB peaking, f_pk in
1.25-2.5 GHz), spanning 4.63-10.01 dB at 1.32-2.30 GHz — e.g. Rs=200,
Cs=1.6p, RL=400, CL=100f -> 4.63 dB at 1.95 GHz.

**5. But compression is now the binding problem, exactly as predicted.**
Available differential swing is 2*IT*RL = 1.2 Vpp. At the LOW-loss end of the
channel sweep (3 dB) a 0.8 Vpp PCIe TX needs **1465-1944 mVpp** at the output
across all twelve S3-meeting points — every one compresses. At 9 dB loss they
are all fine (734-974 mV). This reproduces session 7's "compression binds
hardest at LOW channel loss" on a properly biased device, and it is now worse
because the gain is higher.

**The lever is NOT RL.** Compression ratio is
`TX_pp*|H_pk| / (2*IT*RL)`, and `|H_pk| ~ gm*RL/k`, so **RL very nearly
cancels** — measured, dropping RL 400->300 made it slightly *worse*
(ratio 1.44 -> 1.63). Raising Rs does not help either (1.44 -> 1.48 at
Rs=400), because lower DC gain buys back exactly the peaking it adds. What is
left is **I_tail up, or gm/I_D down**. So there is a real tension: high gm/I_D
is efficient for noise and power but *directly worsens compression headroom*
at PCIe input levels. That tension, not noise, is the actual design problem.

**Consequence to act on:** the parameter BOUNDS in `common/params.py` were
derived from the mis-biased 1.2 V generic-BSIM4 design and the 5.3% S3 yield
was measured inside them. Both need re-deriving once the bias is settled. Do
not quote 5.3% as a corner-robust figure without re-running it.

**S3's ambiguity is now stated in the contract, not resolved silently.**
"3-12 dB peaking, peak in 1.25-2.5 GHz" admits (a) peak-to-DC ratio anywhere
and (b) boost at Nyquist. Our SKY130 smoke test is the counterexample that
makes the difference concrete: **+3.82 dB peaking — a pass under (a) — with
the peak at 724 MHz and the response 0.99 dB BELOW its own DC gain at
2.5 GHz.** We require and report BOTH. If a judge reads S3 the other way, we
have shown we considered it rather than picking the convenient reading.

### 2026-08-04 — Session 9d (bounds re-derived; the central argument falsified)

**Tests: 407 -> 430** (+23, `nebula/tests/test_sky130_runner.py`; 3 need the
simulator and skip cleanly). Full write-up: `nebula/BOUNDS_REDERIVATION.md`.
This session closed the START HERE item and, in doing so, overturned four
prior conclusions. Ordered by how much they matter.

**1. THE COUPLED-CONSTRAINT ARGUMENT IS FALSIFIED (G40).** The project's
designated "strongest single sentence for the abstract" was: S3 couples gm,
Rs, Cs, RL and CL, no axis-aligned box can exploit a coupled constraint, hence
random search lands only 5.3% of the time. A bare percentage cannot support
that, because it depends entirely on the box width. The box-independent form
decomposes S3 into A (peaking 3-12 dB) and B (f_peak 1.25-2.5 GHz) and
compares the joint against the product of the marginals. 2000 Latin-hypercube
samples per box, three widths:

        width   P(A)     P(B)     P(A)P(B)   P(A and B)   coupling
        x0.6    69.40%   24.95%    17.32%      17.25%      1.00x
        x1.0    48.47%   16.03%     7.77%       8.73%      0.89x
        x1.5    35.04%    8.01%     2.81%       3.13%      0.90x

and, conditioned on a peak existing at all (the shared no-peak region
otherwise associates A and B for an unrelated reason), **1.00 / 1.04 / 1.06x**.
The raw yield swings 5.5x across box widths; the coupling factor does not
move. **The two conditions are independent.** S3's yield is low because one
marginal is low — f_peak lands in-window 16% of the time — not because
anything is coupled. Four candidate replacement arguments are listed in
BOUNDS_REDERIVATION §4; the recommendation is **tunability** (S3 wants any
point in 3-12 dB on demand, which random search cannot deliver at all) with
8.73% quoted purely as a baseline. **Human decision, and the abstract is due
6 Aug.**

**2. The available swing was understated ~2x, and by the wrong mechanism
(G37).** `2*I*RL` is a PEAK; the peak-to-peak ceiling is `4*I*RL`. Measured at
the corrected point by DC transfer curve: **1427 mVpp at 1 dB compression**,
2161 mVpp saturation-limited, 2281 mVpp steering, against the 1200 mVpp
session 9c compared everything to. And at the 1 dB point the pair is still
saturated with vds 1.29 V against vdsat 0.079 V — so the limit is **current
steering, not headroom**, which contradicts 9c's diagnosis and predicts (
correctly, see 4) that more supply voltage will not help.

**3. The compression verdict was partly a fixed-boost artifact.** S3's peaking
is tunable and S2's knobs are Rs/Cs, but 9c evaluated twelve FIXED designs
against all five loss points — nobody runs a tunable equaliser that way. With
the boost matched to each channel's tilt, compression goes from "11/11 at 3 dB
loss, up to 1.9x over" to **1.22x at 3 dB, 1.04x at 5 dB, clean at 7/9/12 dB**.
Real, but localised, and not the project-defining constraint. **Caveat that
dominates the whole question:** under `calibration.py` C3's long-run
convention the verdict flips to 11/11 compressing at EVERY loss point, because
`CHANNEL_DC_LOSS_DB` is a fixed 1.0 dB placeholder with no provenance. A
made-up constant currently decides this. Strongest case yet for a real .s4p.

**4. A 3.3 V device is rejected, on f_T not headroom (G39).**
`nfet_g5v0d10v5`'s minimum L is 1.0 um against 0.15 um. Best peaking achieved
**2.66 dB** — under S3's floor — and pushing RL for gain puts the peak at
0.398 GHz with the Nyquist boost at -5.14 dB. Swing improves only +12%,
exactly as 2's steering-limited finding predicts. Power 5.4 -> 9.9 mW.

**5. `nf` does not multiply width on SKY130 (G38).** W is the total; nf splits
it into fingers. gm moves +/-10%, non-monotonically, over nf = 1..32. Two
action-space dimensions are near-dead and non-monotonic, and `BOUNDS`'s
provenance string for `nf_in` is factually wrong for the PDK.

**6. The re-derived box and its yield.** Nine of the twelve §5.2 parameters,
each edge traced to a measurement, in
`nebula/experiments/s3_yield.py::PROPOSED_BOX`. `cl` is ~6x tighter than the
1.2 V box (400 fF already drives the Nyquist boost negative). Yield: 8.73% S3,
100% S5, 100% S6, 99.05% saturated, 0 non-convergences.
**`w_tail`/`l_tail`/`nf_tail` are deliberately absent** — the tail is still two
ideal current sinks, so no simulation in this project has ever contained a
tail transistor, and inventing ranges for it is what §8 rule 6 forbids.
**The box is NOT written into `params.py`** (rule 6); the old bounds now carry
a superseded banner naming their three known defects.

**Also checked and NOT a bug:** `.noise`'s input reference. Naming a
single-ended `vinp` (ac 0.5) versus a differential `Vid` (ac 1) looked like a
guaranteed 2x on every input-referred noise number; measured on the identical
circuit, both give inoise_total = 1.723594e-04. ngspice normalises by the
named source's AC magnitude. Recorded because "obviously a factor of two" is
how the last three units bugs here introduced themselves.

**Note for whoever commits this:** the working tree is NOT a git repository
(`git init` has not been run in this checkout), so the CLAUDE.md rule about
updating HANDOFF.md in the same commit could not be honoured mechanically.
HANDOFF.md is updated; the commit still needs making.
**RESOLVED in session 10a below** — this and every earlier session's work went
into the initial commit.

### 2026-08-04 — Session 10a (git init; the history starts clean of the PDFs)

**Tests: 430 before, 430 after** (`python -m pytest tests nebula/tests -q
-m "not slow"`, 73.9 s, 2 deselected). Nothing executable changed — this
session touched `.gitignore` and `HANDOFF.md` only.

Closes the note directly above, which had been open since session 9d: the rule
in CLAUDE.md that HANDOFF is updated *in the same commit* as any change had no
commit to be in.

**What was done.** `git init -b main`, a rewritten `.gitignore`, and one
initial commit of **102 files** under the global identity
`Jai Kaushik <jaikaushik-prog@users.noreply.github.com>` (G12 — the BITS
address attributes to the wrong GitHub account and has already forced one
history rewrite).

**The part that matters, and it is a one-time opportunity that was taken.**
G1 says the reference PDFs are copyrighted and that a public version of the
GitHub repo would have to strip them from **history**, because they are in that
repo's baseline commit — deleting the files later does not help. This checkout
had no history at all, so the PDFs could simply be excluded from commit #1.
They were, and it was **verified rather than assumed**:

        git diff --cached --name-only | grep -iE '\.(pdf|docx|doc|pptx)$'
        -> empty
        git status --ignored --porcelain | grep '^!!'
        -> all 10 reference documents listed as ignored

All ten (the two Shakiba wireline papers, Menin, Han/EECS-2019-143, both PAM4
notes, the CERN intro, the professor's `Part 11 FFE.pdf`, and the two `.docx`
files) are ignored. So **this tree's history is clean and needs no rewrite**;
the GitHub repo's is not and still does. They are now unrelated histories, and
G1 has been amended to say so, because "the repo has the PDFs in history" was
about to become half-true and half-false with no marker saying which half.

**`.gitignore` is organised by reason, not by extension**, because the reasons
are not interchangeable:

| section | why | if violated |
|---|---|---|
| reference library | copyright (G1) | cannot ever be made public |
| PDK | not ours to redistribute; 52 MB | licence + repo bloat |
| run artifacts | regenerable | noise in every diff |
| `__pycache__`, caches | regenerable | noise |

The PDK patterns (`sky130*/`, `libs.tech/`, `libs.ref/`, `*.pm3.spice`) match
**nothing today** — the install is out of tree at `C:\Users\DELL\sky130A`
(G33). They are there so that a copy dropped in-tree cannot be committed by
accident. That created the one trap in the file: `sky130*/` would also have
caught **our own** trimmed library, so
`!nebula/device/spice/sky130_nfet_only.lib.spice` is an explicit un-ignore. It
is 69 lines of `.include` pointers and `.option scale=1.0u`, redistributes no
model cards, and is what makes an ngspice invocation 0.42 s instead of 16-35 s
(G36) — losing it silently would have been expensive and would have looked
like a performance regression, not a missing file.

**Committed vs. not, for the `ams_rl_ppo` files sitting loose at repo root**
(CLAUDEwa §4.2's reference implementation, unpacked at top level rather than
into `resources/`): the **source** is tracked (`train.py`, `gym_env.py`,
`discriminator.py`, `circuits.py`, `evaluate.py`, `reward.py`,
`component_importance.py`, `reproduce_tables.py`, `llm_baseline.py`, the two
YAMLs) because §4.2 calls it plumbing to port; the **checkpoints and training
logs** (`*.pt`, `*.npz`, `policy*.zip`, `train_summary*.json` — 20-odd files,
several byte-identical duplicates with `(15)`-style suffixes) are ignored,
because they are the artifacts behind the degenerate results table §4.2 says
explicitly not to anchor on. Nothing was deleted; they are still on disk.

**New gotcha G41** (the two verification commands, the reason-based structure,
and the `!`-rule trap). **G1 amended.** **§10 corrected** — it claimed a remote
`origin` that this checkout does not have.

**Not done, deliberately:** no remote, no push. Pointing this history at the
existing GitHub repo is a real choice between a new remote and a rewrite of the
old one, and it is a human's (G1 as amended).

### 2026-08-04 — Session 10b (`cl` sensitivity: a search dimension worth less than a constant)

> **CORRECTION, added by session 10c — read before quoting anything below.**
> Every *coupling* number in this entry was measured with a peak detector that
> counted `meas ac MAX` sweep-edge maxima as genuine peaks (G44), inflating the
> has-peak population by up to 42%. Session 10c fixed it and re-ran all five
> points. **What changes:** the raw coupling reads 1.05 -> 0.68 (not
> 1.00 -> 0.68); the conditional reads 0.97-1.06 with all five intervals
> covering 1.00; the "real ~10% adverse effect at 100 fF" reported below is
> **RETRACTED** — 1.10x [1.02, 1.20] became 1.06x [0.99, 1.15]; and the
> "lockstep with the falling peak count" explanation is **wrong**, because the
> peak count is hump-shaped post-fix. **What does NOT change:** the S3 yields
> (166/213/256/226/180 vs 165/213/256/228/180) and therefore every conclusion
> in G42 about `cl` being a bad search dimension. Corrected numbers are in
> `nebula/CL_SENSITIVITY.md` sec 9 and in G43/G44 as amended.

**Tests: 430 -> 444** (+14, all in `nebula/tests/test_sky130_runner.py`;
105.9 s, 2 deselected). Full write-up: `nebula/CL_SENSITIVITY.md`.
**`common/params.py` is untouched** — this is a measurement and a proposal,
and rule 6 reserves the bound change for a human.

**What was added.** `--cl-fixed FARADS` in `experiments/s3_yield.py`, plus the
uncertainty machinery the conclusions need.

The pin **overwrites the `cl` coordinate of the same seeded LHS design** rather
than re-sampling in eight dimensions. That is the load-bearing design choice:
the other eight coordinates are identical sample-by-sample across all runs, so
a yield difference is attributable to `cl` and nothing else. A free consistency
check falls out — `headroom_ok_1v8()` never reads `cl`, so the free-rejection
count must be identical across runs, and it is (110 rejected / 1890 simulated,
every time).

**Result 1 — pinning `cl` BEATS searching it (G42).** 2000 samples per point:

        cl        50f     100f     150f     250f     400f    sampled 10-500f
        S3      8.73%   11.27%   13.54%   12.06%    9.52%          8.73%
                                  ^^^ max, and disjoint CIs vs both ends

8.73% [7.54, 10.09] -> 13.54% [12.08, 15.16]. The whole bound is worse than a
single value inside it. 150 fF is a real interior maximum, **but is not
separable from 250 fF** at this n — the supportable claim is "the optimum is in
150-250 fF", not "the optimum is 150 fF".

Mechanism, visible in the marginals: A (peaking 3-12 dB) falls monotonically
52.65 -> 33.54% as the load pole eats peaking, while B (f_peak in window) rises
16.61 -> 24.02% then falls back to 19.21%. Extra `cl` first *relocates* the
peak into the S3 window and then *extinguishes* it — session 9c's finding,
re-measured across 9450 designs instead of two. The count of designs with any
interior peak falls monotonically 1673 -> 1168.

**Result 2 — the raw coupling factor is the no-peak fraction in disguise
(G43).** Across the same sweep the raw factor moves 1.00 -> 0.68 (32%) while
the conditional-on-a-peak factor sits flat at 1.01-1.10, in lockstep with the
falling peak count. This is the strongest form G40 has taken: not an argument
that the conditional version is better, but a five-point trend showing the raw
one measuring something else entirely. Honest wrinkle recorded rather than
smoothed: at `cl` = 100 fF the conditional interval [1.02, 1.20] does exclude
1.0, so there is a real ~10% adverse effect there — an order of magnitude too
small to be the retracted sentence's mechanism, and G40 stands.

**Result 3, and it is the uncomfortable one — this makes G3 HARDER.** RL must
beat random search. A better box means a better baseline: ~11 samples per hit
becomes ~7. Recorded in G42 as a decision to take deliberately rather than a
free win.

**An analytic prediction was made in advance and FAILED, which is why it is
written down.** The obvious model — peak of a 1-zero/2-pole response sits near
f_p2 — predicts *zero* S3 yield at `cl` = 50 fF, because no `rl` in 50-800 ohm
puts f_p2 inside 1.25-2.5 GHz (it would need 1273-2547). Measured: 8.73%. One
probed sample has f_p2 = 55.3 GHz and peaks at 9.55 GHz. **f_peak is set by
the zero interacting with both poles, not by the load pole alone** — the first
evidence that the analytic pre-screen in the next work item will not be a
one-liner.

**A near-miss worth recording.** `cl` = 50 fF returned 165/1890, the same
integer as the baseline, which is exactly what a silently-ignored CLI flag
looks like. It was tested rather than explained away: A moved 916 -> 995 and
B moved 303 -> 314, and a direct probe showed `f_pk` moving 9.55 -> 6.61 ->
5.50 -> 3.16 GHz across cl = 50/100/150/500 fF on one sample. Genuine
coincidence. (The identical `n_simulated` is not a coincidence — see above.)

**New: uncertainty on every number.** `wilson_ci()` (two-sided Wilson score —
stays in [0,1] and gives a real upper bound at zero successes, which the
45-corner sweep will need) and `bootstrap_coupling_ci()` (percentile bootstrap
over whole rows, the only honest option for a ratio of three correlated
proportions; measured resolution ~+/-10% at n=2000). Wilson is deliberately
NOT imported from `python_models/pam4_chain.py` — nebula is independent by
design — and a test holds the two implementations to each other so they cannot
drift.

**New gotchas G42** (a dimension worth less than a constant; and the G3
tension), **G43** (raw coupling = no-peak fraction), **G44** (`meas ac MAX`
reports the 50 GHz sweep edge as a peak, so `has_peak` over-counts; found
while probing, not yet fixed because fixing it moves a published statistic).

### 2026-08-05 — Session 10d (the corner-robust yield: a tax, not a constraint)

**Tests: 444 -> 481** (+37; `nebula/tests/test_s9_yield.py` is 29 of them,
the rest landed in `test_sky130_runner.py` alongside the runner work).
`python -m pytest tests nebula/tests -q -m "not slow"`, split 92 + 389,
2 deselected. Full write-up: `nebula/S9_YIELD.md`. **`common/params.py` is
untouched** — rule 6 again; this is a measurement, not a bound change.

*(Session 10c has no entry of its own: its work was the G44 peak-detector fix,
recorded as the correction block at the head of the 10b entry and in G43/G44.)*

**What this closes.** HANDOFF §8's third follow-on and `BOUNDS_REDERIVATION.md`
§7 item 3: every yield this project had published was TT/27 C, while S9
requires every spec to hold at every corner. **20 205 SPICE runs, 47 min.**

**The number, three ways, on the SAME 1890 designs:**

        TT / 1.00 / 27 C          255/1890 = 13.49%
        all 3 screen corners      155/1890 =  8.20%  [7.05, 9.52]
        all 45 corners            153/1890 =  8.10%  [6.95, 9.41]

        cross-tab:  TT pass + corners pass   155
                    TT pass + corners FAIL   100   <- 39.2% of the winners
                    TT fail + corners pass     0

**39.2% of designs that meet every spec at nominal fail at a corner.** The
defensible sentence is *"an optimiser scored at nominal is wrong about two of
every five designs it calls a success"*. It is a **tax on the baseline**, not
a coupled constraint — S9 was listed in BOUNDS_REDERIVATION §4 as the cheapest
route to replacing the argument G40 retired, and **it did not deliver one**.
Recorded plainly because the temptation to dress 13.49 -> 8.10 up as coupling
is exactly the mistake G40 exists to prevent.

**The bottom-right zero is a real check, not a tautology.** tt/1.00/27 C is NOT
one of the three screen corners, so "no design fails nominal yet passes all
three extremes" had to be measured.

**Consistency with 10b.** CL_SENSITIVITY reports 13.54% (256/1890) at
cl = 150 fF counting S3 alone; this run additionally requires Nyquist boost,
S5, S6 and saturation, and gets 255. Four extra conditions remove exactly one
design — outside S3, nothing in this box binds at nominal.

**Three reusable results, which are worth more than the yield:**

1. **G47 — three corners are worth 98.7% of forty-five.** The screen corners
   are a SUBSET of the 45, so the screen has **no false negatives by
   construction** and its yield is a hard upper bound; the only error possible
   is a false positive, and it made two out of 155. Stage 2 spent **64% of the
   wall clock to reject two designs**. Budget the RL reward at 3-5 corners,
   full sweep in a verification tier.
2. **G46 — the worst corner is FAST-hot, not slow-hot.** Every promotion-stage
   failure lands at 125 C on ff/sf/tt and **none on ss at any rail**. A faster
   device has higher gm, which pushes the peak out through S3's 2.5 GHz top
   edge. S3 is a two-sided spec and its two edges sit on opposite sides of the
   process axis, so "the worst corner" is not a well-formed idea for it. The
   screen had been built on the slow-hot folklore.
3. **G48 — 11 cores buy 3.2x, not 11x.** 318 / 179 / 150 / 106 / 100 ms per
   task at 1 / 2 / 4 / 8 / 11 workers. Efficiency collapses after 2 and the
   curve is flat past 8. **~100 ms per (design, corner) is the number to
   budget** — dividing G36's 0.42 s by the core count is off by 2.6x, and
   quoting the serial figure is off by 3.2x. Both have appeared in estimates
   here.

**What binds, which is the headline the script was written to produce.** Of
1890 designs at each screen corner, first failure by normalised shortfall
(CLAUDEwa §9):

        S3_f_peak      800 / 799 / 786   (42%)   median -1.7 to -2.1 GHz
        S3_peaking     686 / 719 / 688   (37%)   median -3.000 dB
        S3_nyq_boost   162 / 126 / 144   ( 8%)   median about -1.0 dB
        headroom        13 /   - /  13
        saturation       5 /   1 /   3
        S6_power         - /   2 /   -

The median S3_peaking failure misses by **exactly -3.000 dB, i.e. its peaking
is 0.000 dB** — a flat stage, not a mis-tuned one. Same population 9d found
behind the low P(B) marginal, seen from the other side. **S5 never ranks as
the binding constraint anywhere**, and S6 does so twice in 5670 runs: what
binds in this box is bandwidth PLACEMENT, and it is not close.

**Health, and why it is printed.** 0 hard simulator failures, 0 retries, 26
(design, corner) headroom rejections (13 at each 0.95 V slow corner), and
**0 screen/promotion mismatches across 465 repeated (design, corner) pairs** —
the free determinism check that falls out of the screen corners being members
of the 45. A mismatch would have invalidated everything downstream (G45).

**THE CAVEAT THAT OUTRANKS ALL OF IT: the tail is still two ideal current
sinks.** An ideal sink does not lose current at SS/125 C, does not gain it at
FF/0 C, and does not fall out of saturation at 0.95 VDD. Every corner spread
above is therefore an **understatement** and 8.10% is an **optimistic bound** —
it is the corner spread attributable to the input pair alone. **This is why
§8 now lists the tail transistor as the top open item**, above everything else
in the Nebula backlog: it is the one experiment that could still turn corner
robustness into a real constraint, and re-running it costs nothing new
(`python -m nebula.experiments.s9_yield --n 2000`, unchanged).

**Added this session:** `nebula/experiments/s9_yield.py` (the two-stage sweep,
owning the three assumptions and printing them in every run header),
`nebula/tests/test_s9_yield.py` (29 tests, all simulator-free — the arithmetic
and the assumption-plumbing, which is where a wrong answer would be invisible),
and `screen_augmentation()`, which maps each corner to the false positives it
would have caught so the screen can be re-cut from data rather than intuition.
Its default `--out` now resolves next to the script, not to the cwd: a 28-min
run must not scatter its only record wherever it was launched from.

### 2026-08-05 — Session 11 (where the robust designs live: in the window, not in the box)

**Tests: 481 -> 528** (+47, all in `nebula/tests/test_robust_geometry.py`;
`python -m pytest tests nebula/tests -q -m "not slow"`, split 92 + 436,
2 deselected). Full write-up: `nebula/ROBUST_GEOMETRY.md`.
**`common/params.py` untouched** — rule 6; §7 of that file is a proposal about
the SEARCH, not a bound change.

**The task premise did not hold, and that is the first result.** This was
scoped as "no new SPICE — it uses data you already have". Session 10d's
20 205-run, 47-minute sweep wrote `s9_yield_results.json`, which is
`.gitignore` line 67 under "run artifacts - regenerable". It was never
committed and is not on disk. It would not have been enough anyway: it stored
counts and design indices, not the per-design f_peak/peaking values this
analysis plots. **New gotcha G49.** Recovery: the LHS is seeded, so the 1890
designs regenerate for free; re-simulating them at TT plus the 3 screen corners
cost **7560 runs / 23 min**. The per-design table is now **committed** as
`nebula/experiments/robust_geometry_data.csv`, so the whole analysis is
simulator-free from here.

**10d's counts reproduced EXACTLY**, and this is asserted rather than assumed
(`check_reproduction()`; `main()` refuses to draw a figure on a mismatch):
1890 designs, 255 TT winners, 155 corner-robust, 100 corner-fragile. That is a
stronger statement than it looks — box, seed, `cl` pin, headroom filter, corner
plumbing, spec checker and peak detector all still produce, design for design,
what they produced in 10d.

**The hypothesis was HALF right, and the wrong half is the more useful half.**
- **FALSIFIED: "robust designs are interior in the box".** All eight sampled
  dimensions are nulls after BH correction, and the two purpose-built
  interiority statistics are the least significant rows in the table
  (q = 0.98). Corners do not move a design's parameters, they move its
  RESPONSE — so a design is fragile when its response starts near a SPEC edge,
  and a response can be near a spec edge from anywhere in the box.
- **CONFIRMED, overwhelmingly: robustness needs f_peak centred in the WINDOW.**
  Median margin 0.325 vs 0.126 octaves, p = 2.8e-12.
- **NOT PREDICTED, and it is the session's own finding: the same holds on S3's
  OTHER axis.** Peaking margin 2.70 vs 0.86 dB, p = 3.2e-11.

**The methodological point worth carrying forward.** Raw `f_peak` and raw
`peaking` carry NO information about corner robustness (medians identical to
four figures; q = 0.81 both). Folded onto distance-to-nearer-edge, the same
numbers separate the groups at 12 sigma. **A two-sided spec makes its own raw
coordinate uninformative**: designs failing at the top edge and at the bottom
edge sit on opposite sides of any median and cancel. Same family as G40 and
G43 — ask the question in the coordinate the SPEC is written in, not the one
the simulator reports.

**The deliverable number: a joint filter, and it is free.** f_peak margin
>= 0.133 oct AND peaking margin >= 1.0 dB gives **92.1% [86.5, 95.6]
corner-robust against a 60.8% base rate**, keeping 140 of 255 designs. Either
condition alone reaches only ~75%, so they guard two independent failure
routes. Both come out of an AC run the evaluator already performs. Proposed as
a warm-start prior and as the S3 reward shape (fold both axes); §7 of the
write-up, for a human to accept or reject.

**G46 partly corrected.** Designs below the window centre die at SS 4.5x more
often than at FF (45 vs 10) — as predicted. Designs ABOVE the centre die about
EQUALLY at both (29 vs 27), which the clean two-mechanism story does not
predict and which an earlier draft of this entry mis-stated as "predominantly
FF". Mechanism: **SS has two ways to kill a design and FF has one** — lower gm
drops f_peak (killing the low side) AND drops peaking toward the 3 dB floor
(killing anything with little peaking margin, at any frequency). SS's 69
failures split 40/26 across those routes; FF's split 19/19. No contradiction
with G46, which was about the PROMOTION stage (the screen's blind spot is
fast-hot) rather than about which corner kills most (`ss/0.95/125`).

**Resolution limit found and pinned.** `meas ac MAX` returns a grid SAMPLE and
the netlist sweeps `ac dec 50`, so f_peak is quantised at log2(10)/50 =
**0.0664 octaves** and the one-octave S3 window holds exactly **15 distinct
f_peak values**. That is why the threshold table has duplicate rows and the
margin histogram has empty bins. Any margin quoted finer than ~0.07 octaves is
quoting the sweep setup.

**Added this session:** `nebula/experiments/robust_geometry.py` (population
reproduction + collection + statistics + four figures, with the reproduction
GATE), `nebula/tests/test_robust_geometry.py` (47 tests, all simulator-free —
the Mann-Whitney implementation is held to `scipy.stats.mannwhitneyu` over
tie-heavy cases rather than to hand-copied numbers), the committed CSV, and
`nebula/figures/`. One additive change to `s9_yield.py`: `CornerResult` gained
a `measured` dict populated from scalars the evaluator already had in hand, so
the pass/fail LABEL and the coordinates plotted against it come from the same
evaluation (rule 9) at zero extra SPICE cost.

**Still an optimistic bound.** The tail is two ideal current sinks, so the
margins above are the margins needed against the input pair's spread alone.
The thresholds are also IN-SAMPLE; a fresh seed costs 23 min and has not been
run.

### 2026-08-05 — Session 11b (verification + the commit)

Housekeeping session; **no analysis changed and no number moved.** Task 1 was
complete on disk but uncommitted and unverified, so this session verified it
and landed it.

**Verified before committing, all four green:**
- **Suite: 528 passed, 2 deselected, 98 s** (`python -m pytest tests
  nebula/tests -q -m "not slow"`, split 92 + 436) — the count §6 already
  claimed, now measured. Re-run after the commit: **528, 95 s.** Note the
  runtime against §6's warning — 98 s here versus the 21.5 min the same suite
  took in session 11 under an 11-worker ngspice pool. Contention, not a hang.
- **Gotcha count 49, no duplicates**, by the §9 splice check — i.e. the
  truncation `df2f7d4` caused is genuinely repaired, not just papered over.
- **`ROBUST_GEOMETRY.md` regenerates from the committed CSV**, with no
  simulator, including the reproduction gate (1890 / 255 / 155 / 100). Every
  number in the write-up was re-derived, including the ones the default report
  does not print: the t = 0.066 row (220 kept, 153 robust, 69.5%), 33-vs-2 and
  51-vs-12 within one and two grid steps of a window edge, 0-vs-37 within
  0.5 dB of a peaking edge, and the 60.9% / 60.7% symmetry about the centre.
- **G41's staging check clean** — no PDF or DOCX in the index.

**The commit (`de874db`) is wider than session 11.** Sessions **10c** (the G44
peak-detector fix in `sky130_runner.py` + `s3_yield.py`) and **10d**
(`s9_yield.py`, `S9_YIELD.md`, `test_s9_yield.py`, and `run_point(temp_c=)`)
were on disk but had never been committed — `4a286a8` was 10b. They are in it,
named in the message, and their absence from history was itself a small version
of G49.

**`PCI.2/` is now gitignored** (owner's call, asked before acting): competition
material from the organisers — two handouts and `nebula_ctle_rl_1.zip`, a
reference PPO+CTLE implementation with a trained agent and a PVT report. Not
ours to redistribute. It stays on disk and is worth reading before the RL work;
CLAUDEwa §4.2's "do not anchor on the reference implementation's numbers"
applies to it exactly as it does to `ams_rl_ppo`.

**Deleted `nebula/SESSION_11_HANDOFF.md`** — session-11 scaffolding that said
to delete itself once Task 1 was committed. Nothing else referenced it.

**Task 2 (`cl` as a robustness axis) has NOT been started**, by instruction: it
needs a pre-registered prediction committed to `nebula/PREDICTIONS.md` *before*
the experiment runs, and the owner reviews between tasks.

### 2026-08-06 — Session 12a (`cl` becomes a derived range, not a chosen constant)

**Tests: 528 -> 591** (+63: `nebula/tests/test_cap_probe.py` 36,
`nebula/tests/test_cl_range.py` 27). `python -m pytest tests nebula/tests -q
-m "not slow"`, split 92 + 499, 2 deselected, 150 s (baseline before the
session: 528, 130 s). Full write-up: `nebula/CL_RANGE.md`.
**`common/params.py` untouched** — rule 6; §8 of that file is the proposal.

**What this closes.** `CL_SENSITIVITY.md` §6's own caveat, open since session
10b: *"`cl` is the one parameter here that is not really free... pinning it at
whatever value maximises S3 yield, if that value is not physically
justifiable, is choosing the answer."* Every corner number this project has
published — 13.49 % / 8.20 % / 8.10 % — was measured with `cl` pinned at
**150 fF**, which was the best of five values tested for S3 yield.

**The decision this session implements** (human, taken for this task): `cl` is
**neither a design variable nor a constant**. Nobody chooses the following
stage's input capacitance, so it is not a knob (G42 already measured that
searching it LOWERS the yield); but it is not known to one value either. It is
a **context variable with a physically derived range**, to be screened like a
PVT corner.

**The range: `cl_lo` = 13.64 fF, `cl_mid` = 32.63 fF, `cl_hi` = 78.04 fF —
5.72x, 2.52 octaves.** 180 SPICE runs, 16 s. Built from what actually loads
the node under S2's topology: the 1-tap DFE summer input pair, the slicer
input pair, and the wire between them.

**`@m[cgg]` is NOT the gate load — new gotcha G50.** It is the obvious probe
and it understates the load by **1.9-2.7x**, silently, because it is the
INTRINSIC capacitance: no gate overlap (`cgso = cgdo = 2.449e-10 F/m`, ~3.9 fF
per side on a 16 um device) and no Miller multiplication of C_gd. The trap is
that the *intrinsic* C_gd of a saturated device really is ~0 (measured
1.8e-17 F), which makes "C_gd is negligible" feel safe while the *overlap*
C_gd gets multiplied by (1 + |A|). At the 16 um slicer, **52 % of the load is
that one term.** So the load is measured as the AC current the driver has to
supply into one gate under differential drive, through a zero-volt ammeter,
and cross-checked against the parsed primitives plus the model card's own
overlap constants: **1.02 % median disagreement, 2.20 % worst, over 180 runs.**
`sanity_check_load()` rejects any point that disagrees by >5 %, is out of
saturation, or is not capacitive; **0 of 180 rejected**, and a test corrupts
the AC number by 1.5x and requires the check to go red.

**The range is wide because of the SKETCH, not because of silicon.** Measured
per axis: the sizing decision moves the load **5.9x**, the process corner
1.16x, temperature 1.08x, the CTLE output common mode 1.04x. Stated plainly in
the write-up because it is the honest headline — designing the slicer would
narrow `cl` far more than any amount of corner analysis. Two smaller results
from the same runs: capacitance dispersion across S3's window is **0.17 %**
(so a lumped `cl` in the netlist is honest, previously assumed), and **the
corner that loads the node most is the one with the LEAST gm** (`fs` > `ss` >
`tt` > `ff` > `sf` for C_in, exactly inverse to gm) — the same shape of
mistake G46 had to correct once for S3.

**The minimum sizes were set by a gate that fired.** `MIN_STAGE_GAIN = 1.0`:
a summer or slicer front end that attenuates is worse than the wire it
replaced. The first sizing tried measured **|A| = 0.85 at TT**, the second
**0.95 at ss/125 C**; only 0.5 mA into 800 ohm clears unity everywhere. The
gate runs on every sweep and prints PASS/FAIL.

**The routing allowance is derived from PDK data, with one declared input —
new gotcha G51.** This install has no tech LEF and no magic techfile, so there
is no interconnect model to query. SKY130's own vpp finger capacitors state
both their total capacitance and their metal run length in squares, which
gives **0.0984 fF/um (m1) and 0.1191 fF/um (m2)**; the only declared number is
the 0.14 um metal width, and it is a divisor. Routing is 14-18 % of each edge,
so doubling the whole allowance moves `cl_hi` by a fifth of an octave against
a 2.52-octave range. **The routing assumption is not what makes the range
wide.**

**The comparison that matters, and the coincidence inside it.** The 150 fF pin
is **1.92x above `cl_hi`** — outside the derived range entirely. But a
**half-rate front end** (two data + two edge slicers on the node, which is
what a real 5 Gbps receiver with a CDR looks like) gives `cl_hi` = **141.8 fF**.
So the pinned value was not absurd; it was the right number **for a topology
S2 does not describe**. Reported and deliberately NOT folded into the bound
(rule 5) — that is a human's call and it changes the ratio from 5.7x to 10.4x.

**One finding outside `cl`, recorded because nothing else in the project
notices it:** `headroom_ok_1v8()` lets the CTLE output DC fall to 0.5 V, but
the stage it drives needs roughly **1.15 V** or its source node goes negative
— session 9c's unbuildable-tail failure, one stage downstream. Either the box
needs a tighter v_out floor or the RX needs AC coupling / a level shift.

**Added this session:** `nebula/device/cap_probe.py` (the measurement, with
the PDK constants READ from the model file and a reader that raises on a
parameter the 180 bins disagree on — `cgso` agrees, `u0` does not),
`nebula/experiments/cl_range.py` (the sketch, the routing model, and
`derive_cl_range()`, which is pure so the whole derivation re-runs from the
CSV with no simulator), the tracked 180-row `cl_range_data.csv` (G49), and
two ngspice fixtures so the parser is testable with no simulator.

**`nebula/PREDICTIONS.md` is new**, and it is committed in this same commit
**before** session 12b's experiment runs. Entry 1 predicts the
corner-and-load-robust yield at **essentially zero (0-10 of 1890)**, against
the stated expectation of 8.73-13.54 %, on the argument that S3's f_peak
window is 1.00 octave and the derived `cl` range moves f_peak by 1.26. Whether
that holds or not, the outcome goes in that file next to the prediction.

**Not started, by instruction:** the second half of task 2 (folding the range
into `s9_yield.py` and re-running). The owner reviews between tasks.
