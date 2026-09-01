# CLAUDE.md — instructions for AI agents working in this repository

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

0. `nebula/CONTINUE_HERE.md` — **the entry point (2026-08-19).** Where the
   project stands, what is decided, what is OPEN, what to do next.
   **As of 2026-08-22 (session 26c): stage 0 is MEASURED at two depths, and the
   depth is what mattered.** `nebula/experiments/exp_hybrid.py` — the
   "propose, else fall back to the search" wrapper — is committed, and its
   64-deck k=1 scan RAN: entry 31 scored 5 of 5, with only **1 of 16** free
   proposals accepted (1 infeasible, 14 unscorable, **all 14 on output-swing
   compression**). Entry 31's closing recommendation — re-rank the library on
   swing headroom, "the pool already carries it" — **was checked and is FALSE**:
   the pool has no swing field, and no nominal channel separates the 1 success
   from the 14 failures. What replaced it, `scan_topk`, scores the top **k=8**
   candidates per request instead of the top 1 — and it **RAN**: entry 32 scored
   **6 of 6**, `accepted_at_k = [1,4,5,5,6,6,6,6]`, so **A = 6 of 16** and the
   old 1-of-16 was measuring **depth**, not the library. **`k=5` is the optimum**
   (same A for 120 fewer decks): **35.6 % fewer simulations** than the
   13 718-deck search, against k=1's 5.8 %. `DEFAULT_TOPK` stays 8 — retuning it
   on the run that measured it would be tuning. **The bar for SAC is now 35.6 %,
   not zero.** But `A = 6` is **not** a compliance number: mandated-corner
   coverage is still **7/16**. The **~90-minute full sweep still needs the
   owner's say-so** — `A >= 5` makes it defensible, not authorised.
   Read `nebula/PROGRESS.md` §5h, then §5g, then entries 31-32, then G122-G125.
   The prior line stopped here: entry 30's sweep RAN, scored 2 of 5, and
   mandated coverage went 8/16 -> 7/16 (`PROGRESS.md` §5e;
   `nebula/SESSION_25_HANDOFF.md` has the reasoning behind that fix).
1. `HANDOFF.md` — state, session log, gotchas **G1–G125**
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
   `python -m pytest tests nebula/tests -q -m "not slow"` — **2242 passed,
   13 deselected, ~5.5 min** (329 s, measured 2026-09-01 on system Python
   3.13.14; it was 2213 before session 31 added 29 across
   `test_rl_refine.py`, `test_union.py` and `test_design_cli.py`).
   **This line was stale by 381 tests for ten days** — it read 1861/11 from
   2026-08-22 while the suite ran 2213/13. Re-measure it when you change the
   count; a reviewer who clones the tag and finds the stated figure wrong
   starts checking every other number.
   Report the count before and after. Never commit with failures. Add tests for
   anything you fix or build.
   - Use the **system** interpreter, not the conda env `nebula` — that env has
     no `torch`, and `ngspice_con.exe` is found by absolute path regardless
     (HANDOFF §9 G69), so activation buys nothing for the suite.
   - `-m "not slow"` deselects 13 tests, incl. ones that re-derive golden values
     from the full SKY130 library (~30 s each). Run them after a PDK update.
   - Either suite runs standalone; the two `conftest.py` files do not collide.
   - Do **not** run the suite alongside an experiment sweep (G70): one
     concurrent ngspice makes it ~4.8x slower and the timings become meaningless.
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
