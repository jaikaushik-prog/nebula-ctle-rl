# AGENTS.md — instructions for AI agents working in this repository

**Before doing anything else: read `HANDOFF.md` in full.** It is the living
source of truth for this project — what it is, everything done so far and why,
current state, conventions, known footguns, and the prioritized next steps.

## There are TWO projects in this repository. Work out which one you are on.

| | **SerDes framework** (original) | **Nebula** (competition track) |
|---|---|---|
| Contract | this file + `HANDOFF.md` | **`CLAUDEwa.md`** + `HANDOFF.md` |
| Code | `python_models/` | `nebula/` |
| Target | 112G PAM-4 RX, 28 nm | 5 Gbps NRZ PCIe Gen2 CTLE, SKY130 |
| Goal | link-design methodology | RL-driven device sizing, zero human in the loop |
| Deadline | open-ended | **15 Sept 2026** (see CLAUDEwa.md §7 gates) |

They share `HANDOFF.md` and the test suite; they are otherwise independent by
design. **If you are touching `nebula/`, read `CLAUDEwa.md` in full first** —
it has its own spec table (S1–S9), its own gates (G0–G5), and its own standing
rules, several of which were written after a specific failure and are not
guessable. Start with these, in order:

1. `HANDOFF.md` — state, session log, gotchas **G1–G36**
2. `CLAUDEwa.md` — the Nebula contract
3. `nebula/G0_RESULTS.md` — toolchain findings + the cost model
4. `nebula/NRZ_RETARGET_AUDIT.md` — the 24 PAM-4 assumptions, 3 fixed

The gotchas are the highest-value-per-line thing in the repo. Every one cost
real debugging time; several describe failures that **report success and exit
zero**.

## Mandatory working rules

1. **Update `HANDOFF.md` in the same commit as any change you make.**
   Append a dated entry to its Session Log (§12) and update the affected
   sections (§2 repo map, §5 history, §6 current state, §7 limitations,
   §8 next steps, §9 gotchas). A change without a handoff update is
   incomplete.
2. **Run the test suite before and after changes** (from repo root):
   `python -m pytest tests nebula/tests -q -m "not slow"` — **407 tests,
   ~1.5 min** (`tests/` 92 + `nebula/tests/` 315). Report the count before and
   after. Never commit with failures. Add tests for anything you fix or build.
   - `-m "not slow"` deselects 2 tests that re-derive golden values from the
     full SKY130 library (~30 s each). Run them after a PDK update.
   - Either suite runs standalone; the two `conftest.py` files do not collide.
3. **Git identity:** commit with the global config
   (`Jai Kaushik <jaikaushik-prog@users.noreply.github.com>`). Never use the
   BITS Pilani email (wrong GitHub attribution — see HANDOFF §9 G12).
4. **This repo is PRIVATE and must stay private** — it contains copyrighted
   reference PDFs (HANDOFF §9 G1). Never make it public or copy the PDFs to
   any public location.
5. **The owner is a beginner in this domain.** Explain every change in plain
   language (what/why/implication) so they can present the work to their
   professor. Provide professor-ready takeaways for new findings.
6. Respect the codebase conventions in HANDOFF §4 (symbol units, seeds via
   `LinkConfig.seed` only, cursor alignment, line-bit references) and the
   gotchas in §9 — each one was earned through real debugging.
7. Windows environment: no non-ASCII glyphs in `print()` output (cp1252
   console); run pytest from repo root, link_sim from `python_models/`.

## Quick orientation

**SerDes framework**
- Core code: `python_models/` (link_sim.py is the harness; statistical_eye.py
  is the semi-analytic engine; rx_frontend.py has CTLE + closed-loop CDR;
  modulation.py carries the symbol alphabet, default PAM-4).
- Docs: `HANDOFF.md` (state), `docs/ROADMAP.md` (phased plan), `README.md`
  (user-facing).
- Figures: regenerate with `python_models/make_report_figures.py`.
- Untrusted/unaudited: `rtl/`, `verification/`, `veriloga_models/`,
  `matlab_models/`, `ml_equalizer.py`, `optical_dsp.py`, `Makefile`.

**Nebula** (contract: `CLAUDEwa.md`)
- `nebula/common/` types + params + design equations; `nebula/device/` ngspice;
  `nebula/link/` device→eye bridge; `nebula/rl/` reward. Mocks exist for all
  three layers and **produce fake numbers** (G16) — none may reach a
  deliverable.
- **Simulator:** ngspice 41 in conda env `nebula`. Use `ngspice_con.exe`, NOT
  `ngspice.exe` (G20). PySpice is installed and broken; don't (G23).
  `conda activate nebula`.
- **PDK:** SKY130 at `C:\Users\DELL\sky130A`, installed via volare (G33).
  Use the **trimmed** library `nebula/device/spice/sky130_nfet_only.lib.spice`
  — 0.42 s vs 16–35 s, verified bit-identical (G36). Run netlists **from
  `nebula/device/spice/`** so `.spiceinit` is read at parse time (G29).
  Instance W/L are **plain numbers in microns** (G31).
- **Hand-sizing sandbox:** `nebula/device/spice/ctle.cir`, driven
  interactively (`ngspice_con ctle.cir`). Not a deliverable.

## The three failure modes this repo keeps hitting

Stated here because each one produced a wrong number that looked right:

1. **Silent success.** ngspice reports many failures as warnings and exits 0
   (G26, G30, G35). Parse output and assert; never trust an exit code. See
   `nebula/device/crosscheck.py` and CLAUDEwa.md §8 rule 10.
2. **Units.** Microns vs metres (G31), scale applied twice (G35),
   `inoise_total` is RMS volts and must **not** be square-rooted
   (`nebula/tests/test_noise_units.py`). Each is a factor of 10³–10⁶ that
   still simulates happily.
3. **Two definitions of one thing.** A model card that differs between the
   netlist a human reads and the runner that produced the numbers (G32).
   CLAUDEwa.md §8 rule 9: exactly one definition, referenced, never redeclared.
