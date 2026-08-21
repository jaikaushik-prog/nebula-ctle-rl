# SESSION_25_HANDOFF.md — the unclip fix, handed over mid-flight

**Written 2026-08-22.** This file exists because session 25 ran in the Claude
desktop app and the work is being continued in Claude Code. **The code is on
disk; the reasoning was not.** This file is the reasoning. Read it before you
touch `nebula/experiments/`.

It is a *session* handoff, not a replacement for anything. `CONTINUE_HERE.md`
is still the entry point and `HANDOFF.md` is still the source of truth. What
follows is one change, why it was made, what was proven about it, and the four
things that are **not done yet**.

---

## 0. The 30-second version

A search was ranking candidate circuits on a score that **stops getting worse
past a point**. So a CTLE peaking at 10 GHz and one peaking legally at 2.5 GHz
scored *the same number*, and the optimiser had no reason to prefer the legal
one. Four of the sixteen coverage requests failed this way.

The fix is a new module that gives the *search* an uncapped score to rank on,
while the *verdict* reported as a result stays exactly what `reward_v1` says.
It is written, tested, and **not yet committed, not yet run.**

---

## 1. What is on disk right now, uncommitted

Verify with `git status --short`. Three items belong to this change; everything
else in that output is pre-existing line-ending noise (see §7.1).

| Path | State | What it is |
|---|---|---|
| `nebula/experiments/search_score.py` | **new, untracked** | the whole fix, 257 lines, mostly docstring |
| `nebula/tests/test_search_score.py` | **new, untracked** | 34 tests |
| `nebula/experiments/exp_coverage.py` | **modified, 4 edits** | the seam that uses it |

`reward_v1.py` is **untouched**, deliberately. So are `V1_SPECS`, the
tolerances, `rl/contract.py`, `rl/env.py`, `rl/ppo.py`, `common/params.py`,
the box, the pre-screen, and `experiments/baselines.py`. That list is
`PROGRESS.md` §8 rule 7 plus the benchmark file, and none of it may move
without a human decision.

The four edits to `exp_coverage.py`, exhaustively:

1. `from nebula.experiments import search_score as SS`
2. `RequestResult` gains `screen_search_score: Optional[float] = None`
3. `_Objective.__init__` gains `rank_unclipped: bool = True` and
   `self.best_score: Optional[float] = None`
4. `_Objective.evaluate` computes `score = SS.score_design_eval(ev, R.V6_SPECS)`
   when `rank_unclipped`, keeps `self.best` by that score, logs
   `"search_score"` and `"rank_unclipped"`, and returns `SS.RankView(reward=score)`
   instead of `ev`. `solve_request` additionally sets
   `res.screen_search_score = obj.best_score`; `res.screen_reward = best.reward`
   is **unchanged**.

`rank_unclipped=False` reproduces the old behaviour exactly. That switch exists
so the two regimes are comparable by measurement rather than by argument, and
there is a test pinning it.

---

## 2. The defect, with the numbers

`reward_v1.reward` scores an infeasible design as

```python
spec_r = -sum(min(v, 1.0) for v in s.values())     # reward_v1.py line ~808
```

where `v` is a per-spec-row shortfall in units of that row's tolerance. **Once
a row misses by more than one tolerance its contribution is pinned at 1.0.**
Any search ranking on that number is optimising on a flat plateau.

Measured 2026-08-22, **zero SPICE**, against the live `reward_v1.shortfalls`
with the real `TOL["S3_f_peak_match"] = 0.30` octaves and a 1.387 GHz request:

| delivered peak | octaves off | shortfall | **clipped** |
|---|---|---|---|
| 1.378 GHz | 0.009 | 0.031 | 0.031 |
| 2.500 GHz | 0.850 | 2.833 | **1.000** |
| 10.303 GHz | 2.893 | 9.644 | **1.000** |
| 11.800 GHz | 3.087 | 10.291 | **1.000** |

The gradient pulling a runaway peak back into the legal window is exactly
**0.0**.

**This is corroborated by an artifact, not only by arithmetic.** In
`coverage_results_AFTER_seeding_fix.json`, all four out-of-window requests
recorded `screen_reward` of **exactly -2.0000** — an integer, because it is
simply *how many rows are fully saturated* (`S3_f_peak_band` and
`S3_f_peak_match`) and carries nothing about how far out. Delivered frequency
errors of 1.901, 2.386, 2.715 and 2.893 octaves all produced the same score.

**Re-verified from the artifact on 2026-08-22**, not quoted from memory: that
file holds 16 requests, `total_sims` = **13718**, nine `screen_reward` values in
the feasible band (~+14.06 to +14.44), and **exactly four** at `-2.0` to machine
precision, plus one at `-1.0` and two small negatives. The same four also appear
in `coverage_results.json`, which is byte-identical on these fields.
`coverage_results_BEFORE_seeding_fix.json` has **none** at `-2.0` — so the
plateau pile-up is specific to the post-seeding-fix run, which is the run the
next sweep must be compared against.

This answers a question `PREDICTIONS.md` entry 29 explicitly left open. Its
OUTCOME section says the runaway cause is *"stated as unexplained rather than
guessed at"* and proposes logging every candidate the seeder probed. That
diagnostic is no longer needed: the seeder was probing fine, the ranking could
not tell the candidates apart.

### 2.1 A second defect, found on the way

`adaptive_screen.evaluate_at_points` selects a design's worst PVT point with
`if worst is None or pr.reward < worst.reward` — the **clipped** number. With
two points both saturated, "worst" was whichever tied first, i.e. arbitrary.
`score_design_eval` re-derives the minimum over all scorable points using the
unclipped score, so that choice is now determined. This was not on anyone's
list; it fell out of reading the same plateau twice.

---

## 3. The transform, and why it is safe

Per row, given `v = shortfall = max(0, -margin/tol)`:

```
penalty(v) = min(v, 1.0) + W * log1p(max(0, v - 1.0))     capped at ROW_CAP
search_spec_reward = -sum(penalty_i) / ROW_CAP            in [-N, 0]
```

`W = 1.0`, `ROW_CAP = 4.0`, N = `len(V6_SPECS)` = 13.

Three properties, each a test:

1. **Bit-identical to the clip for `v <= 1`.** `log1p(0.0)` is `0.0`, so below
   one tolerance the sum *is* the clipped sum, and the `/ROW_CAP` division is
   one positive constant applied to every candidate — which cannot reorder
   anything. **Every one of the eight already-solved requests lives in this
   region, so the fix provably cannot disturb what already works.** This is the
   safety property and the reason the change is worth running.
2. **Strictly monotone past the clip.** 10.303 GHz now ranks strictly worse
   than 2.500 GHz. That is the recovered gradient; it is the entire point.
3. **Band-safe.** `reward_v1`'s bands are infeasible `[-13, 0)`, headroom top
   `-14`, invalid `-16`. An *uncapped, undivided* penalty sum would put a badly
   infeasible design near **-50** — below the invalid floor — so the search
   would start preferring **unbuildable** designs over measurable ones, which
   is G107 (*"cannot be scored" is not "fails"*) committed on purpose. The
   division keeps the infeasible band exactly where `reward_v1` put it.
   **`ROW_CAP` is a band-safety requirement, not a tuning knob.**

`ROW_CAP` saturates at `v = e^3 + 1 = 21.1` tolerances = a **6.33-octave** miss.
The widest miss ever observed in this project is 3.09 octaves, so the cap is
inert on real data and exists only to bound the arithmetic. Neither constant
was fitted to an outcome.

### 3.1 Why a wrapper and not a two-character edit

Changing `min(v, 1.0)` in `reward_v1.py` would be smaller and is **wrong**.
That file defines every published reward in `BASELINES.md`, the `+8.950669`
ceiling, and the whole arm ranking. Editing it silently re-bases the benchmark
and rule 7 forbids it without a human decision. It is also not even desirable:
the clip is *correct for scoring* — one catastrophic row must not drown out the
other twelve — and only wrong for *searching*. Both halves of that sentence
come from the same comment in `reward_v1`. So the verdict stays clipped and a
second, private scalar does the ranking.

`RankView` carries **one field**, `reward`, deliberately. `baselines.method_cmaes`
line ~940 reads exactly `-obj.evaluate(X[i]).reward` and uses it only as an
argsort key, so a one-field shim steers the search without touching the
benchmark file. A shim that also proxied `feasible` or `margins` would be a
second thing shaped like a `DesignEval` (`CLAUDEwa.md` §8 rule 9: model cards and
device parameters have exactly ONE definition, referenced, never redeclared) and
a caller reaching for `.feasible` would silently read the search's opinion
instead of the verdict. As written, that raises
`AttributeError` immediately. There is a test that greps `method_cmaes`'s own
source, so if someone makes it read `.feasible`, that test fails first and says
why.

---

## 4. What was verified, and what was not

Run in a Linux sandbox with **numpy only** — no pytest, no network, no SKY130
PDK. A throwaway pytest shim executed the *real* test file:

**31 passed, 3 deferred, 0 failed.**

The 3 deferred import `exp_coverage` / `baselines`, which pull `rl/contract.py`,
which reads `C:/Users/DELL/sky130A` at module load. **They have never run.**
They are the two `_Objective` seam tests and
`test_method_cmaes_reads_only_the_attribute_rankview_provides`. Running them is
the first item in §6.

`CONTINUE_HERE.md` §9 rule 4 (= `NEXT_AGENT_SAC.md` §7 rule 4: *every new gate
is deliberately broken, watched go red, and restored*) was satisfied with three
sabotage runs:

| sabotage | result |
|---|---|
| delete the `log1p` tail | 6 red |
| delete the `/ROW_CAP` division | 2 red |
| delete the `if not ev.ok` G107 guard | **green — the gate was not gating** |

The third one matters. `test_an_unscorable_design_passes_through_as_the_floor`
originally used an eval with empty `points`/`margins`, so `score_margins`
returned `None` and the function fell back to `ev.reward` **anyway** — it passed
for the wrong reason. It was rewritten to carry a complete margins dict plus one
scorable point, which is realistic because `evaluate_at_points`'s unscorable
branch sets `margins=(worst.margins if worst else {})`. Re-run then gave 1 red,
and restoring gave 31 green.

**Write that down as a gotcha (§7.2). A sabotage run that stays green is the
only reason we know one of these tests was decorative.**

---

## 5. The pre-agreed decision rule — recorded BEFORE the result

The owner chose both of these by explicit answer, before the run:

- **Order:** coverage sweep first, not a PPO re-run first.
- **Threshold:** keep PPO if the sweep shows it can learn, defined as
  **>= 5/16**. Below that, drop PPO and implement SAC per
  `nebula/NEXT_AGENT_SAC.md`.

Do not renegotiate this number after seeing the result. If it needs to change,
the change and its reason go in `PREDICTIONS.md` *above* an outcome heading, and
the owner decides.

### 5.1 A plan that was checked and rejected — do not redo it

An earlier agent proposed a *"Fixed PPO Re-run"* whose two fixes were **already
active** in the runs that produced 1/16 and then 0/16. Re-running it would
reproduce those numbers and cost hours. If a plan resembling that one reappears,
check whether its "fixes" are already in `HEAD` before spending a single sweep
on it.

---

## 6. What is NOT done — in order

1. **Run the 3 deferred tests on Windows**, plus the full suite.
2. **Pre-register `PREDICTIONS.md` entry 30 and commit it BEFORE the sweep**
   (`PROGRESS.md` §8 rule 3). The last entry is `## 29`; entry 29's own text says *"entry 30 will
   carry its final numbers"*. Entry 30 must contain: this diagnosis; the
   prediction that the 4 runaway requests recover; a coverage band on the
   **45-corner** grid (8/16 now, band 10–13/16 predicted); that the 8 solved
   requests do not regress; that simulation cost per request does not rise
   materially; a falsifier for each; and the §5 decision rule restated.
   **It must also disclose that the plateau was already confirmed by a
   zero-SPICE re-score before the pre-registration was written** — the
   precedent for disclosing a prior run is entry 19.
3. **Update `HANDOFF.md` §12 session log and §9 gotchas, and `PROGRESS.md`, in
   the SAME commit** (repo rule 1). Note the log's last entry is
   `2026-08-20 session 22u`: **sessions 23 and 24 are missing entirely** and
   should be reconstructed from `PREDICTIONS.md` 27–29 and the git log.
4. **Run the coverage sweep** with `rank_unclipped=True`. Compare against
   `coverage_results_AFTER_seeding_fix.json`: 9 screen / 8 pvt45 / 0 full135,
   13,718 sims, 95.6 min.
5. **Apply the §5 decision rule.**

Keep the compliance/characterisation split straight throughout (D8): the slide
mandates **45** PVT corners; the **135**-point grid adds this project's own load
axis. 45 is compliance, 135 is characterisation, and they are never merged into
one number.

---

## 7. Debt and traps

### 7.1 Line-ending debt — fix this BEFORE committing

The entire working tree is CRLF while `HEAD` is LF: **203 files, 338,478
insertions/deletions.** The proof that it is *only* line endings is that
`git diff --ignore-all-space --stat` returns just this session's four files:

```
 .gitignore                         |  3 ++
 CLAUDE.md                          |  2 ++
 nebula/CONTINUE_HERE.md            |  7 +++++
 nebula/experiments/exp_coverage.py | 56 ++++++++++++++++++++++++++++++++++----
```

plus the two untracked files in §1. **Use `--ignore-all-space` for every diff
until this is fixed.** If you commit as-is, this change is buried in a 338k-line
diff and is effectively unreviewable. Set `.gitattributes` / `core.autocrlf`, run
`git add --renormalize .`, commit that as its own hygiene commit, **then** commit
the fix.

Also confirmed clean by the same check: `reward_v1.py`, `baselines.py`,
`rl/contract.py`, `rl/env.py`, `rl/ppo.py` and `common/params.py` have **zero**
non-whitespace changes. That is the rule-7 guarantee, measured rather than
asserted.

### 7.2 Gotcha candidates earned this session

Add to `HANDOFF.md` §9 with real numbers:

- **A sabotage run that stays green means the test passed for the wrong
  reason.** The G107 guard test used an eval with empty margins and so never
  exercised the guard. Rule 4 is what caught it; without the sabotage step it
  would have shipped as a decorative test.
- **The clip is not only a scoring choice, it is a search-killer.** Any place
  that ranks on `reward_v1`'s infeasible number is on a plateau. `worst_point`
  selection in `adaptive_screen` had the same bug independently (§2.1). Grep for
  other consumers before assuming these were the only two.
- **`rl/contract.py` reads the PDK at module load**, so importing anything under
  `experiments/` requires the SKY130 install. That is why 3 tests cannot run
  anywhere but the owner's Windows box.

### 7.3 Standing traps that apply here

- **G70:** do not run the sweep alongside the test suite. One concurrent ngspice
  makes it ~4.8x slower and the timing numbers become meaningless.
- **G20:** `ngspice_con.exe`, never `ngspice.exe`. **G23:** PySpice is installed
  and broken.
- **G36:** use the trimmed library `sky130_nfet_only.lib.spice` (0.42 s vs
  16–35 s, verified bit-identical). **G29:** run netlists from
  `nebula/device/spice/` so `.spiceinit` is read at parse time.
- **The test count is disputed.** `CLAUDE.md` says 407, `PROGRESS.md` says 1667.
  **Measure and report the number you actually get; do not quote either.**

### 7.4 THREE rule lists exist and they are numbered differently

This tripped the writing of this very file, so it is worth a line. "Rule 4"
means three different things depending on the document:

| | `CLAUDEwa.md` §8 | `PROGRESS.md` §8 | `CONTINUE_HERE.md` §9 |
|---|---|---|---|
| rule 3 | the 48 existing tests stay green | pre-register in `PREDICTIONS.md` | — |
| rule 4 | tests before implementation | never fabricate a number | break every new gate, watch it go red |
| rule 7 | commit daily, tag every gate | **wrap, do not replace** | — |
| rule 9 | exactly ONE definition | don't run experiments with the suite | — |

**Always cite the document with the number.** This is the repo's own third named
failure mode (*two definitions of one thing*) applied to its own rules, and it is
a real trap for an agent that has read only one of the three files.

---

## 8. The commands

From the repo root, in conda env `nebula`, on Windows:

```
conda activate nebula
python -m pytest tests nebula/tests -q -m "not slow"
python -m pytest nebula/tests/test_search_score.py -q
```

Report the counts before and after the change. Then, and **only once the test
run has finished** (G70):

```
python -m nebula.experiments.exp_coverage
```

---

## 9. What not to do

- Do not edit `reward_v1.py`, the tolerances, or `baselines.py` to make a number
  move. Loosening a tolerance to buy coverage is the G111 defect committed on
  purpose; this module is the alternative to it.
- Do not merge the 45-corner and 135-point results into one coverage figure.
- Do not report `search_score`'s scalar as a compliance result anywhere. It is a
  private ranking key. The reportable number is `screen_reward`.
- Do not commit without updating `HANDOFF.md` in the same commit
  (`CLAUDE.md` rule 1 = `PROGRESS.md` §8 rule 1).
- Do not run the sweep before entry 30 is committed (`PROGRESS.md` §8 rule 3).

---

## 10. Note for whoever explains this to the professor

Plain-language framing that holds up: *the optimiser was being graded on a test
where every wrong answer scored the same, so it had no way to tell "nearly
right" from "absurd". The grading for the final verdict is unchanged — what
changed is the feedback the search gets while it looks.* The evidence that this
was real, not theoretical, is that four failing cases all recorded the identical
score of exactly -2.0000 despite being between 1.9 and 2.9 octaves off target.

---

## 11. The raw record

The full session-25 conversation is kept at repo root as
`session25_desktop_transcript.jsonl` (684 records, ~2.4 MB, **gitignored** —
local backup only, do not commit). This file supersedes it for every practical
purpose; the transcript is there only if you need to check *how* a conclusion in
§2 or §4 was reached. Grep it, do not read it.

