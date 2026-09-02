# Next-session prompt: continue Nebula Entry 86

Continue in `C:\Users\DELL\Desktop\serdes-dsp-framework-main`. Read
`HANDOFF.md`, `CLAUDEwa.md` and `AGENTS.md` first.

Entry 85 passed 6/6 and focused closure is 16/16. The owner approved Entry
86's full 7.3 dB verification. Preregistration commit: `a9e3f44`.

The implementation is `nebula/experiments/exp_joint_bank_73.py`, with the
minimal optional-range seam in `exp_joint_bank.py`. The focused shared group is
25/25 green and the complete suite is 2,605/2,605. Before any SPICE row, commit the implementation and its HANDOFF,
PROGRESS and PREDICTIONS updates. Do not touch the unrelated `gmcmp.pkl` or
`nebula/.claude/`.

Fresh run, eight workers:

```text
py -3.13 -m nebula.experiments.exp_joint_bank_73 --run --workers 8
```

If and only if the process was interrupted after writing
`joint_bank_73_run.jsonl`, resume with:

```text
py -3.13 -m nebula.experiments.exp_joint_bank_73 --resume --workers 8
```

Never restart or delete a partial journal. Do not run pytest alongside the
experiment. When complete, score Entry 86 Q1-Q7 exactly as written, preserve
misses, run the complete non-slow suite, update `HANDOFF.md` in the result
commit, and compress the verified journal for Git without changing its decoded
SHA-256.

Even if Q1-Q5 pass, do not silently adopt 7.3 dB. The outcome only supports a
recommendation; the owner makes the production-range decision separately.
