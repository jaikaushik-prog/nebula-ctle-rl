
Measured the model directly: 11,279 parameters, 44 KB. Here's both answers.

---
Part 1 — Compute: you don't need a GPU. At all.

Tell your ML person this up front, because it's counterintuitive and it changes what he plans.

The model is tiny. The policy network is an 18-input → 64 → 64 → 7-output MLP. 11,279 parameters. For scale, ResNet-50 is 25 million — this is ~2,000× smaller. It trains on a laptop CPU faster than it would take to copy the data to a GPU.

The bottleneck is the circuit simulator, not the learning. Measured in session 17 over a real 500-step run:

┌─────────────────────────┬──────────┬────────┐
│                         │   time   │ share  │
├─────────────────────────┼──────────┼────────┤
│ ngspice (the simulator) │ 1585.8 s │ 99.7 % │
├─────────────────────────┼──────────┼────────┤
│ PPO weight updates      │ 3.5 s    │ 0.2 %  │
├─────────────────────────┼──────────┼────────┤
│ logging                 │ 0.9 s    │ 0.1 %  │
└─────────────────────────┴──────────┴────────┘

So optimising the ML side is worth nothing. A GPU would speed up 0.2 % of the run.

What you actually need

┌──────────┬─────────┬────────────────────────────────────────────────────────────────┐
│ resource │ needed  │                              why                               │
├──────────┼─────────┼────────────────────────────────────────────────────────────────┤
│ GPU      │ none    │ 44 KB model. Would be slower than CPU due to transfer overhead │
├──────────┼─────────┼────────────────────────────────────────────────────────────────┤
│ CPU      │ 8 cores │ ngspice is single-threaded; you run many in parallel           │
├──────────┼─────────┼────────────────────────────────────────────────────────────────┤
│ RAM      │ 8–16 GB │ plenty; the biggest single file is a 27 MB lookup table        │
├──────────┼─────────┼────────────────────────────────────────────────────────────────┤
│ Disk     │ ~5 GB   │ SKY130 PDK + logs                                              │
└──────────┴─────────┴────────────────────────────────────────────────────────────────┘

More than 8 cores does not help — this is measured, not assumed. 11 workers came out slower than 8 (G48, G71). Parallel scaling is poor because each ngspice process competes for memory bandwidth: 8 workers buy about 1.8–2.6×, not 8×.

Your current machine has 12 cores. That is enough. Don't buy anything.

What runs cost today

After last week's 13× library speed-up, one full evaluation is 0.28 s:

┌──────────────────────────────────┬───────────────────────┐
│               job                │         time          │
├──────────────────────────────────┼───────────────────────┤
│ 500-step smoke run               │ ~4 min (was 26.5 min) │
├──────────────────────────────────┼───────────────────────┤
│ Baselines sweep (25,500 sims)    │ ~1–2 h                │
├──────────────────────────────────┼───────────────────────┤
│ Serious training run (50k steps) │ ~3–6 h                │
└──────────────────────────────────┴───────────────────────┘

The real lever is fewer or cheaper simulations, not more hardware. That's exactly what the reference paper's surrogate idea does — run real SPICE on 0.5–5 % of steps and a learned approximation on the rest. If your ML person wants a speed project, that's it. And even that trains on CPU, because the dataset is thousands of rows, not millions.

---
Part 2 — Work division

The project in one picture (say this first, to everyone)

▎ There's a circuit with 7 adjustable numbers (transistor width, resistor values, etc.). Some combinations meet all our targets; most don't. A simulator tells us how good any combination is, but each check costs about a third of a second and there are effectively infinite combinations.
▎
▎ Our entry is a program that finds good combinations automatically, using reinforcement learning, and outputs a real circuit diagram plus its measured performance.
▎
▎ As of today the whole pipeline works end to end and we have a circuit that meets every target. What's left is proving the AI finds them faster than dumb search, checking it survives manufacturing variation, and writing it up.

---
Lane A — the RL/ML person

Your one-line job: prove the AI beats random guessing and grid search. That's gate G3, due 3 Sept.

You don't need to understand the electronics. Treat it as a black-box optimisation problem: 7 knobs in, one score out, each evaluation costs 0.28 s.

Tasks in order:

1. Run the baselines sweep. One command, ~1–2 h unattended. It compares random search, Latin hypercube, grid search, CMA-ES, Bayesian optimisation and PPO on the same problem with the same budget. It has never been run and everything downstream needs it.
2. Write up the outcome honestly. There's a pre-registered prediction file with seven specific numerical predictions — go through each and mark hit or miss. A miss is a result.
3. Tune PPO and answer G3.

Three things you must know before you start:

- The score has a hard ceiling of +8.950669 that belongs to the simulator's frequency grid, not the circuit. So "best score" saturates and can't separate methods. Use "how many simulations to reach the ceiling" instead.
- Tuning counts as PPO's cost. If PPO needs 50,000 simulations of tuning to win a 150-simulation comparison, it hasn't won.
- About 60 % of proposals are now rejected as invalid (the circuit overloads). That's a big flat region in the reward exactly where an untrained policy starts. This project has been bitten by that shape before — check the policy is getting a usable gradient before touching hyperparameters. A flat learning curve caused by a flat objective is not a tuning problem.

If RL loses, that is a publishable finding, not a failure. The project contract says so explicitly.

Read first: nebula/BASELINES.md, nebula/RL_SMOKE.md.

---
Lane B — the analog electronics person

Your one-line job: be the person who says "that number is wrong" — and make the one design decision nobody else can.

You don't need to understand the RL. Your value is that you can look at a circuit and its numbers and know whether they're physically sensible. No test can do that. This project has already had several cases where the code was correct, the tests passed, and the number was wrong.

Task 1 — the decision, this week.

We found that 61 % of the parameter range is unusable: driven by a real PCIe transmitter, the amplifier overloads and stops behaving linearly, so the small-signal analysis stops describing it.

Our recommendation is to accept it and treat it as part of the problem — the framework's job is to find the 3 % that works, and a hard search problem makes the RL result more interesting. But before we commit, you should check the premise:

▎ We compare the worst-case output swing over any bit pattern against the 1 dB compression point. Is that the right validity test, or too strict?

That's an analog judgment call. The alternatives are on record: relax the peaking spec's lower limit, declare the easy channels out of scope, or shrink the load-resistor range so the stage attenuates instead of amplifying.

Task 2 — sanity-check the worked design. Open nebula/G2_RESULTS.md §5. It's a full circuit with all its measurements. Does a 38.9 µm × 0.188 µm input pair at 3.08 mA plausibly give 9.67 dB of peaking at 2.19 GHz? Is 0.29 mV of input noise sensible? Is 5.3 mW right? If anything looks off, say so — that's the single highest-value thing you can do.

Task 3 — gate G4, corner robustness (due 12 Sept): does the design still work across manufacturing variation and temperature? The infrastructure exists; you decide which corners and what margin is acceptable.

Read first: nebula/G2_RESULTS.md §5 and §7. §7 is what the result does not prove — read it before quoting any number.

---
Lane C — you

Your one-line job: own the deliverable and keep the two specialists unblocked.

1. The report and slides. Lead with the methodology — that's our strongest asset. Six pre-registered predictions with the misses recorded as misses; a central claim we retracted when our own measurement disproved it; a catalogue of 87 documented failure modes, most of which reported success and exited zero. Judges who are practising engineers recognise that immediately.
2. The LLM wrapper — the competition's stated bonus. Type a request in English, get a sized circuit and a written explanation. ~1 day. Two hard rules: the LLM must never invent a number, and it must never touch the sizing loop (that would undercut our "zero human intervention" claim).
3. The live demo for the final presentation.
4. Run the AI sessions to build what A and B specify.
5. Own the schedule. Three gates, 29 days.

---
The handoffs

- B decides compression → A can trust the box and run the sweep without risking a re-run.
- A's sweep result → C writes it up in the report.
- B's corner decision → C runs G4.
- Everyone → C keeps HANDOFF.md current. That documentation is part of what makes the entry credible, not overhead.

Rough weeks

┌──────┬─────────────────────────┬────────────────────────────────────┬──────────────────────────────┐
│ week │         A (RL)          │             B (analog)             │           C (you)            │
├──────┼─────────────────────────┼────────────────────────────────────┼──────────────────────────────┤
│ 1    │ run sweep, write up     │ compression decision, sanity-check │ LLM wrapper, report skeleton │
├──────┼─────────────────────────┼────────────────────────────────────┼──────────────────────────────┤
│ 2    │ tune PPO, G3            │ G4 corners                         │ demo, slides                 │
├──────┼─────────────────────────┼────────────────────────────────────┼──────────────────────────────┤
│ 3    │ spec-conditioned policy │ verify final design                │ write-up                     │
├──────┼─────────────────────────┼────────────────────────────────────┼──────────────────────────────┤
│ 4    │ buffer                  │ buffer                             │ submit (15 Sept)             │
└──────┴─────────────────────────┴────────────────────────────────────┴──────────────────────────────┘

One line to say out loud

The competition asks for zero human intervention in the design. Every decision we three make — compression, the parameter box, the tolerances — is about setting up the problem, not solving it. That distinction has been enforced in the code throughout (the AI has never been allowed to pick a parameter range or a spec tolerance). A judge will ask. It's worth a slide.
