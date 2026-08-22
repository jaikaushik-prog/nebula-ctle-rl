# SESSION_26_HANDOFF.md — Stage 0 of the SAC brief, mid-flight

**Written 2026-08-22, mid-session, for the next agent (fresh chat).**
Its only purpose is that long chats make an agent's reasoning drift and mistakes
creep in. This file is written *now*, while the state is exact, so a fresh agent
can verify every claim against the repo and continue **without re-deriving
anything and without guessing.**

> **Read this AFTER `nebula/CONTINUE_HERE.md` and `CLAUDE.md`, and BEFORE you
> touch any code.** It is the living state of one specific piece of work —
> **Stage 0 of `nebula/NEXT_AGENT_SAC.md`** — that is written but *not committed*.
> Everything in it is checkable; where I give a number, re-measure it if you
> doubt it. Do not trust this file over the repo.

---

## 0. The one-paragraph version

We are building **`nebula/experiments/exp_hybrid.py`** — the "propose first, fall
back to the search" wrapper that `NEXT_AGENT_SAC.md` §4 orders built **first,
before any SAC code**. It takes one request (a peaking-dB + peak-frequency
target), asks a *proposer* for a design `u`, scores that `u` on the 4-corner
screen (4 SPICE decks), and **if it passes, delivers it; if not, runs today's
CMA-ES search unchanged** (`exp_coverage.solve_request`). The proposer today is
the **library lookup** (0 simulations) — that is the *control* a future SAC
policy has to beat. The wrapper is **written and its 20 unit tests pass**, but it
is **not committed**, its **proposals-only scan mode is half-wired**, and **no
PREDICTIONS.md entry has been pre-registered** yet. The immediate job is: finish
the scan mode + its tests, run the full suite, pre-register entry 31, commit
Stage 0, then run the cheap 64-deck scan and report. **Nothing expensive should
run before entry 31 is committed.**

---

## 1. Which project, and the read-order

You are on **Nebula** (`nebula/`, contract `CLAUDEwa.md`), not the SerDes
framework. Target: 5 Gbps NRZ PCIe Gen2 CTLE on SKY130, RL-driven device sizing.
Deadline 15 Sept 2026; demo 25 Sept at BITS Goa.

Read, in this order, before doing anything:

| # | file | why |
|---|---|---|
| 1 | `nebula/CONTINUE_HERE.md` | the project entry point; its top blockquote is current as of the sweep |
| 2 | **this file** | the exact state of the uncommitted Stage 0 work |
| 3 | `nebula/NEXT_AGENT_SAC.md` | the brief being executed — §4 (stages), §5 (rules), §7 (what NOT to do), §8 (human-only decisions) |
| 4 | `nebula/PREDICTIONS.md` entry 30 OUTCOME (line ~5041) | the last measurement; how claims are made here (pre-register → commit → run) |
| 5 | `HANDOFF.md` §9 gotchas **G100–G121** | every one cost real debugging; **G107, G109, G111, G113, G120, G121** are load-bearing for this work |
| 6 | `CLAUDEwa.md` §§7, 8 | the contract and the standing rules |

---

## 2. What just happened, in sequence (so you know why we're here)

1. **Session 25** fixed the search-ranking bug: the CMA-ES search was steering on
   a score that *clips* (stops getting worse once a spec is missed), so it
   couldn't tell bad candidates apart. The fix (unclipped `search_score`) was
   committed as `e1c7c67` and **pre-registered as `PREDICTIONS.md` entry 30**.
2. The owner authorised the coverage sweep. **It ran.** Result committed as
   **`e1dc5fd`** (current HEAD).
3. **Entry 30 scored 2 of 5** (line ~5041 of `PREDICTIONS.md`):
   - **The mechanism worked (Q3, CONFIRMED):** all four runaway peaks came home
     from 8–12 GHz to ~2 GHz. `10.0 dB @ 2.253 GHz` went from an unrankable
     −2.0000 with 0 corners to `screen_reward +14.0472` at **43 of 45**.
   - **The headline was falsified (Q1, Q2, Q4):** mandated 45-corner coverage
     went **8/16 → 7/16**. But aggregate corner passes rose **459 → 585 of 720
     (+27 %)**, and the two regressions kept a *positive* `pvt45_worst` — the
     lost corners are **unmeasurable eyes, not spec violations**.
   - Per its own pre-committed branch, **nothing was tuned.** The named next
     lever is **reachability** (the tuning bank or the 200-eval budget), *not* a
     third scoring heuristic.
4. The owner then said, verbatim: *"i feel sac one fdrom next steps agent shoyld
   be executed now since this aint giving good relsults anyway"* — i.e. **stop
   the coverage/unclip line, start the SAC track in `NEXT_AGENT_SAC.md`.**
5. The brief orders **Stage 0 first** (*"Do this first, it needs no SAC"*). That
   is what this session has been building.

**Professor-ready framing of step 3:** the experiment did exactly what a good
experiment should — it *confirmed the physical mechanism we predicted* (the
search can now distinguish candidates) while *falsifying the headline number*
(coverage fell by one). We wrote the mechanism and the number down as separate
predictions *before* the run, so a correct mechanism does not get to launder a
wrong number into a "partial success". That discipline is the point.

---

## 3. Exact git state (verify with `git status --short` from repo root)

```
HEAD: e1dc5fd  "nebula: the sweep ran -- entry 30 scored 2 of 5, mandated coverage 8/16 -> 7/16"

Untracked (the only changes in the tree):
  ?? nebula/experiments/exp_hybrid.py          <- the Stage 0 deliverable (written)
  ?? nebula/tests/test_hybrid.py               <- 20 tests, all pass, no SPICE
  ?? nebula/experiments/hybrid_results.json    <- SMOKE JUNK, do NOT commit (see §6)
  ?? nebula/experiments/hybrid_run.jsonl        <- SMOKE JUNK, do NOT commit (see §6)
```

Working tree is otherwise clean. **Nothing about Stage 0 is committed.**

---

## 4. What `exp_hybrid.py` is, and the four design decisions inside it

The file is ~600 lines and heavily commented; read it in full. The four
decisions below are the ones that make its central claim *checkable* rather than
*hopeful*, and a fresh agent must not undo them by accident.

1. **Call, don't copy.** The fallback is a literal call to
   `exp_coverage.solve_request(...)` with `exp_coverage`'s **own seed formula**
   (`seed = C.BASE_SEED + i`). There is exactly one CMA-ES path in this project
   (`CLAUDEwa.md` §8 rule 9). A test bans `method_cmaes`, `CmaConfig`,
   `BudgetExhausted` from the source so nobody quietly reimplements the search.

2. **The safety property, stated precisely.** The brief calls it *"coverage
   cannot get worse"*. The *true* statement is: a fallback request is
   **bit-identical to `exp_coverage` given the same archive**. An *accepted*
   proposal changes what enters the archive (which `choose_start` re-probes as
   seeds), so the guarantee is **"no worse search", not "identical trajectory"**.
   That caveat is written into the module docstring — do not overclaim it.

3. **Score the proposal on the LIVE screen, not on `EDGE4_MANDATED`.** The
   brief's step 2 literally says `evaluate_at_points(u, EDGE4_MANDATED, ...)`. I
   deliberately used `screen.points` instead (which *starts* equal to
   `EDGE4_MANDATED` and only grows). Reason: the fallback search is graded on the
   live screen, so grading the proposal on a smaller set would give it an easier
   bar — two definitions of "passes the screen" (G32). This deviation is
   **intentional, documented in the docstring, and pinned by a test**
   (`test_the_proposal_is_scored_on_the_LIVE_screen`). Keep it.

4. **`n_sims` is the SUM of both paths, and verification is NOT in it.**
   `n_sims = proposal decks + search decks`. The 135-point verification is
   recorded separately as `n_verify_points` and **never added to `n_sims`**,
   matching `exp_coverage.verify_request` which doesn't charge it either. The
   whole deliverable is a *ratio of simulation counts*, so a wrapper that
   reported only the winning path would understate exactly the expensive
   requests. Three cost lines in the report, never one.

**The claim Stage 0 measures** is the **amortisation curve** — decks-per-request
falling as the proposer improves — *not* "RL beats CMA-ES". With the library
proposer it produces the **control**; a future SAC policy produces the treatment
against the same grid, screen, verifier and schema.

---

## 5. DONE vs NOT DONE (the checklist to work from)

### Done and verified
- [x] `exp_hybrid.py` written: `library_proposer`, `null_proposer` (the
      ablation), `propose_then_search`, `run`/`_run` (full sweep), `_report`.
- [x] `scan_proposals()` + `_report_scan()` added (the cheap proposals-only mode).
- [x] `test_hybrid.py`: **20 tests, all pass in ~0.13 s, no SPICE.** Both gate
      halves were deliberately sabotaged, watched go red, and restored (brief
      rule 4). Re-run: `python -m pytest nebula/tests/test_hybrid.py -q`.
- [x] A real-SPICE smoke run of ONE request confirmed the accounting
      (`64 decks = 4 proposal + 60 search`) and surfaced a real signal (§6).

### NOT done — this is your work, in order
- [ ] **Wire `scan_proposals` into the CLI.** `main()` has `--run --analyse
      --budget --proposer --no-verify` but **no `--proposals` flag** — the scan
      function is defined but unreachable from the command line. Add
      `--proposals`, route it to `scan_proposals(...)` + `_report_scan(...)`.
- [ ] **Write tests for the scan mode** (there are currently zero). At minimum:
      it writes `PROPOSAL_SCAN` not `RESULTS`; it runs no search
      (`solve_request` never called); it counts `n_accepted` / `n_infeasible` /
      `n_unscorable` as three separate buckets (the G107 distinction); it holds
      its own `hybrid_proposal_scan` run lock.
- [ ] **Delete the two smoke artifacts** before committing (§6).
- [ ] **Run the full suite** from repo root:
      `python -m pytest tests nebula/tests -q -m "not slow"`.
      Baseline to beat: **1806 passed, 11 deselected** (CLAUDE.md, measured
      2026-08-22). Report before/after counts. (Note: `NEXT_AGENT_SAC.md` rule 2
      says "1670 tests" — that is **stale** from session 23; trust CLAUDE.md's
      1806 and re-measure.)
- [ ] **Pre-register `PREDICTIONS.md` entry 31 BEFORE any measurement run**, with
      confidences, acceptance bands and falsifiers (brief rule 3). It should
      cover the proposals-only scan and — conditionally — the full hybrid sweep.
      **Never edit anything above an OUTCOME heading.**
- [ ] **Commit Stage 0** as one commit: `exp_hybrid.py`, `test_hybrid.py`, entry
      31, and same-commit updates to `HANDOFF.md` §12 (+ affected sections) and
      `nebula/PROGRESS.md` (repo rule 1 AND brief rule 1). Update
      `CONTINUE_HERE.md`'s top blockquote and `CLAUDE.md`'s Nebula note to point
      at Stage 0.
- [ ] **Only then** run the 64-deck proposals-only scan (~30 s), report it in
      plain language, and **ask the owner** whether the ~90-minute full hybrid
      sweep is warranted before spending it.

---

## 6. Traps specific to THIS work (the things a tired agent will get wrong)

1. **The two `hybrid_*.json`/`.jsonl` files in the tree are SMOKE JUNK.**
   `hybrid_results.json` has `budget_design_evals = 3` and `n_requests = 1` — it
   is a one-request smoke run, **not a measurement**. If it is committed it will
   read like a real coverage result to anyone who opens it (this is exactly
   G113's shape). **Delete both before the Stage 0 commit**, and let the real
   sweep regenerate them afterwards.

2. **The `−15.5` signal is real and important.** In the smoke run, the library's
   proposal for `6.0 dB @ 1.387 GHz` scored **−15.5** — that is the *unscorable*
   band (`invalid_reward(13) = −16`, plus `2/4` screen points measurable), with
   `worst_spec = None`. Meaning: **2 of the 4 screen corners could not be
   measured at all** because the stage was compressing (output swing 2179.8 mVpp
   vs the 520.5 mVpp linear limit), so the AC/pole-zero eye model doesn't apply.
   This is **"cannot be measured", not "fails"** (G107) — a different fact. It
   predicts a *low proposal-acceptance rate* for the library, which is *why* the
   cheap 64-deck scan is worth running before the 90-minute sweep, and it
   connects to the still-open `n_unscorable 74 → 133` question from entry 30.

3. **Two different "16 held-out requests" exist and are NOT the same set.** The
   `NEXT_AGENT_SAC.md` §1 table conflates them:
   - `exp_coverage` (and this hybrid) use a **4×4 grid** (`PEAKING_REQUESTS ×
     FREQ_REQUESTS`) verified at **45 corners**;
   - `exp_corner_rl` uses **16 random `spec_dist.interpolation_split` targets**
     scored on the **4-point screen only**.
   When you compare the hybrid's coverage to "7/16", make sure it's the
   `exp_coverage` grid. **This has not yet been reported to the owner or written
   into any doc except this one** — flag it when you next report.

4. **`n_scorable` vs `feasible` are different.** `scan_proposals` records both on
   purpose. A proposal with `ok=False` did **not** fail the specs — its eye
   couldn't be computed. Do not collapse the two into one "pass/fail" column;
   that is failure shape #4 from the brief (§6) and G107.

5. **The `_report` function was broken mid-edit and is now fixed.** Earlier this
   session I removed `n = d["n_requests"]` while adding the scan mode, which left
   three `NameError`s. It has been restored. If you see a `NameError` on `n` in
   `_report` or `_report_scan`, that binding got dropped again.

---

## 7. Standing rules still in force (from the owner and the repo)

The owner's verbatim working rules, still binding:
> *"surgical, no scope creep. Don't touch anything outside what's listed above.
> Explain each step in plain language — what you did, why, and what it means —
> because I have to present this to my professor. If you hit something
> ambiguous, ask me rather than picking."*

Hard constraints (each earned through a real failure):
- **`HANDOFF.md` + `PROGRESS.md` updated in the SAME commit** as any change
  (repo rule 1, brief rule 1).
- **Pre-register in `PREDICTIONS.md` before any run**, bands + falsifiers,
  committed (brief rule 3). **Nothing above an OUTCOME heading is ever edited.**
- **Run the suite before and after; never commit red.** Add tests for anything
  you build (brief rule 2). Use the **system** Python, not the conda `nebula`
  env (no torch there).
- **One experiment at a time** — `runlock` enforces it. A finished run silently
  overwrote a finished run on 2026-08-21 (G113); that is why the hybrid has its
  **own** artifacts and lock names (`hybrid`, `hybrid_proposal_scan`), separate
  from `coverage`.
- **Do NOT modify without a human decision:** `common/params.py`,
  `rl/contract.py`, `rl/env.py`, `rl/ppo.py`, `V1_SPECS`, the box, the
  tolerances, `reward_v1.py`, `baselines.py`. **Wrap, do not replace.**
- **Do NOT touch `SEARCH_TAIL_W` / `SEARCH_ROW_CAP`** — entry 30's pre-committed
  branch says the next lever is reachability, not scoring.
- **Do NOT tune tolerances to make coverage look better** (G111) — they are
  derived from measured PVT excursions.
- **Do NOT merge the 45-corner and 135-point results** into one coverage number
  (D8/G109): compliance = 45 corners, characterisation = 135 points, both shown,
  neither merged.
- **Do NOT report `search_score`'s scalar as a compliance result** — it's a rank
  signal for the search, not a spec verdict.
- ngspice exits 0 on failure — **parse output and assert, never trust the exit
  code**. Use `ngspice_con.exe`. Instance W/L are plain microns.
- Commit only as `Jai Kaushik <jaikaushik-prog@users.noreply.github.com>`
  (never the BITS email, G12). **Repo is PRIVATE and stays private** (G1).
- Windows console is cp1252 — **no non-ASCII glyphs in `print()`**. Run pytest
  from repo root.
- **Never commit `session25_desktop_transcript.jsonl`** (gitignored local backup).

---

## 8. The bigger picture — where Stage 0 sits, and what's blocked

`NEXT_AGENT_SAC.md` has four stages. **Do not skip ahead.**

- **Stage 0 (now):** the fallback wrapper. No SAC. Produces the amortisation
  curve with the library as proposer — the control. *This is what you're
  finishing.*
- **Stage 1:** `nebula/rl/sac.py` (new, alongside `ppo.py` — do NOT edit
  `ppo.py`). SAC is *off-policy*, so unlike PPO it can reuse the 74,526 already
  simulated designs (Trap 1). Pre-train on `analytic_env.py`, then fine-tune on
  SPICE **one change at a time** (G114: last time fine-tuning *erased* the
  policy because three things changed at once). Gate: the entropy coefficient
  must actually move.
- **Stage 2 — BLOCKED.** Feeding CMA-ES's evaluations into SAC's buffer. Two
  landmines: CMA-ES `sigma0=0.30` vs `contract.MAX_STEP=0.15`, so consecutive
  samples are ~2× further apart than one action can reach and are **not valid
  MDP transitions** (Trap 2 — filter, or behaviour-clone the winners instead).
  **`NEXT_AGENT_SAC.md` §8: do NOT start Stage 2 before the competition mentor
  answers whether the rubric requires RL to be the optimiser.** That answer had
  not arrived as of 2026-08-22.
- **Stage 3:** run 50–100 requests through `exp_hybrid` with the SAC proposer,
  plot decks-per-request vs index against the library control. That plot is the
  headline figure.

Trap 3 (a judge's framing critique — "is this an MDP or a contextual bandit?"):
the recommended answer is keep the horizon-8 refinement MDP and **write the
critique into the report yourself**. Not code; just don't forget it.

---

## 9. Canonical files (where the truth lives, not this doc)

- **The search being wrapped:** `nebula/experiments/exp_coverage.py` (815 lines,
  read in full). Constants the wrapper reuses: `PEAKING_REQUESTS`,
  `FREQ_REQUESTS`, `BUDGET_DESIGN_EVALS=200`, `ARCHIVE_MAX=6`, `BASE_SEED`.
  Signatures reused: `solve_request(...)`, `verify_request(res, best, screen)`,
  `library_candidates(...)`, `RequestResult`.
- **The screen + evaluator:** `nebula/experiments/adaptive_screen.py`.
  `EDGE4_MANDATED` = the 4 screen edges; `evaluate_at_points(...)` returns a
  `DesignEval` whose `n_sims` is SPICE **decks**, with `.ok` (all points
  scorable), `.feasible`, `.n_scorable`, `.n_points`, `.reward`.
- **The rank score:** `nebula/experiments/search_score.py`.
  `score_design_eval(ev, R.V6_SPECS)` is the single scalar both the search and
  the proposal rank on (a test pins that they use the *same* call).
- **The lock/provenance:** `nebula/experiments/runlock.py` — `hold(name, meta)`
  and `stamp()`.
- **The last measurement + how claims are made:** `PREDICTIONS.md` entry 30
  OUTCOME (~line 5041).
- **Gotchas:** `HANDOFF.md` §9. Load-bearing here: **G107** (unscorable ≠
  infeasible), **G109** (45 vs 135 never merged), **G111** (no tuning tolerances
  for coverage), **G113** (a run overwrote a run → separate artifacts + lock),
  **G120** (`pvt45_worst` silently excludes unmeasurable points), **G121** (the
  45/45 binary metric is a cliff — a correct mechanism must not launder a
  falsified number).

---

## 10. If you're unsure

Two things are genuinely open and are **the owner's call, not yours**:
1. Whether to spend ~90 minutes on the full hybrid sweep after the 64-deck scan
   comes back (decide *with* the owner, showing the scan first).
2. Whether to next chase the unmeasurable-eye corners (`n_unscorable 74 → 133`,
   `PROGRESS.md` §6 row 4d) or go straight at reachability (row 4c). **Row 4c
   must not be started without the owner's say-so.**

For anything else ambiguous: **ask, don't pick.** The owner is a beginner in this
domain and is presenting this to a professor — a wrong guess that looks confident
is worse than a question.
