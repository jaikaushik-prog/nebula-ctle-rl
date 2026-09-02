# Next-session prompt: continue Nebula Entry 85

Continue the Nebula project in:

`C:\Users\DELL\Desktop\serdes-dsp-framework-main`

First read `HANDOFF.md` and `CLAUDEwa.md` completely, then follow
`AGENTS.md`. Do not restart the earlier experiments.

## Current Git state

Branch: `nebula/tuning-bank-rl`

Committed state:

- `570f646` recorded Entry 84's adjacent-C2 result.
- `4f125ce` preregistered Entry 85, the final 7.3 dB boundary probe.

## Entry 84 result

- Combined recovery improved from 13/16 to **15/16**.
- The final failing case is:
  - corner: `sf/0.95/125C`
  - request: 12
  - CTLE bank: 50 / R6C2
  - attenuator code: 7
- Its frequency and peaking are now correct.
- It fails only compression: 754.0 mVpp demand versus 731.5 mVpp limit.
- This corresponds to a 0.263140 dB input-reduction lower bound.
- Artifact: `nebula/experiments/atten_cs_probe_results.json`
- SHA-256:
  `BAECB4621818D80B71BFC9CF1977EF81E71A02BB3026CF67211123FCFFA204C5`
- Full suite after Entry 84: 2,589 passed, 13 deselected, 2 warnings.

The owner explicitly approved exactly one **7.3 dB nominal top-code
diagnostic** for that final R6C2 row. Entry 85 in `nebula/PREDICTIONS.md`
contains the fixed predictions and decision rules. Do not choose another
attenuation value, run extra points, adopt the production range, or launch the
full PVT table without further approval.

## Intentional uncommitted work

- Modified: `nebula/tests/test_atten_range_probe.py`
- New: `nebula/tests/test_atten_final_probe.py`
- Preserve both files.
- The focused tests were run and failed as intended because
  `nebula.experiments.exp_atten_final_probe` does not exist yet.
- `nebula/experiments/exp_atten_final_probe.py` has **not** been created.
- No Entry 85 SPICE simulation has run.

Unrelated pre-existing untracked files -- do not touch:

- `gmcmp.pkl`
- `nebula/.claude/`

## Resume steps

1. Inspect the two uncommitted test changes.
2. Implement the smallest Entry 85 driver:
   `nebula/experiments/exp_atten_final_probe.py`.
3. Modify `exp_atten_range_probe._measure()` to accept an optional
   `atten_max_x`, defaulting to the existing 7.0 dB value so all historical
   behavior remains unchanged.
4. The new driver must:
   - verify the Entry 84 source hash;
   - select exactly the one registered row;
   - use `PROBE_TOP_DB = 7.3`;
   - use `PROBE_MAX_X = 10**(7.3/20) = 2.31739464996848`;
   - run attenuator code 7 and bank code 50;
   - score request 12 at both 3 dB and 12 dB;
   - check noise and measured DC-gain reduction;
   - refuse to overwrite
     `nebula/experiments/atten_final_probe_results.json`;
   - use only ASCII in console `print()` strings.
5. Make the focused tests green.
6. Update `HANDOFF.md`, `PROGRESS.md`, and the Entry 85 implementation record.
7. Commit the implementation and tests **before** running SPICE.
8. Run exactly:
   `py -3.13 -m nebula.experiments.exp_atten_final_probe --run`
9. Record the result honestly against Q1-Q6. A failed gate remains a failed
   gate; do not increase attenuation again.
10. Run the complete non-slow suite:
    `py -3.13 -m pytest tests nebula/tests -q -m "not slow"`
11. Update `HANDOFF.md` in the same commit as the result artifact and report
    before/after test counts.
12. Commit using the configured global identity:
    `Jai Kaushik <jaikaushik-prog@users.noreply.github.com>`.

Explain progress and results in simple language. The key question is whether
this one 7.3 dB measurement closes the final case, giving focused 16/16
closure. Even if it passes, it only authorises proposing a separately
preregistered full 45-corner verification; it does not automatically adopt
7.3 dB or start that large run.
