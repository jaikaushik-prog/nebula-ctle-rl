# Next-session prompt: continue Nebula Entry 86

Continue in `C:\Users\DELL\Desktop\serdes-dsp-framework-main`. Read
`HANDOFF.md`, `CLAUDEwa.md` and `AGENTS.md` first.

Entry 86 is historical and complete. Preregistration commit: `a9e3f44`;
implementation commit: `91398ea`; Q1 classification repair: `5e04916`.
Read `JOINT_BANK_73_RESULTS.md` for the result and artifact hashes. Do not
touch the unrelated `gmcmp.pkl` or `nebula/.claude/`.

**Current state: COMPLETE.** All 23,040 rows completed uninterrupted in 131.27
min. The tested G147 correction was committed before one zero-SPICE reanalysis.
Q1-Q7 and the adoption-recommendation gate pass: zero hard device failures,
16/16 all-corner coverage at every loss, and 10,378 scorable rows at 3 dB.
The original false-Q1 artifact remains preserved beside the corrected result.

Do not rerun SPICE. Do not silently adopt 7.3 dB: the evidence supports the
change, but the owner makes the production-range decision separately. No RL
was trained here. A future RL experiment should optimize eye/margin rather
than compliance and requires a new preregistration and owner authority.
