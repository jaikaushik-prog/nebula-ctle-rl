# Eval — Proposal 001 (fRL-AD: gm/ID + sequential feasible problems)

**Evaluated 2026-08-29, session 29. 17 days to G5 (15 Sept).**

**Protocol deviation, declared up front.** `EVAL_PROTOCOL.md` Stage 1 requires a
sealed pass — the evaluator forms a view before seeing any note about how the idea
might fit our direction. That seal was not available: all four documents (001, 002,
003, the protocol itself) were supplied in one message, including 002 §3 and 003's
relevance ordering. This is therefore a **Stage 1+2 combined pass**, and the bias
control that was skipped is named here rather than pretended.

**Headline: the paper's flagship mechanism has already been evaluated in this repo,
on this PDK, and the result was negative.** `GMID_MAP.md` is a completed measurement
of §2.1. That fact decides most of this eval.

---

## 1. Precondition audit (brief §3)

| # | Precondition | Verdict | Decided by |
|---|---|---|---|
| 1 | Circuit adequately described by a **small-signal AC equivalent** | **VIOLATED — measured, and it is the project's binding constraint** | G103; `CONTINUE_HERE.md` §3.1; `PREDICTIONS.md` entry 32 |
| 2 | Objective **scalarisable by a fixed preference vector w** | **DIFFERENT** — we use maximin, not weighted sum | `rl/reward_v1.py`; G102 |
| 3 | Every spec expressible as a **graded distance to target** | **SATISFIED** | `reward_v1.margins` returns normalised `margin/tol` |
| 4 | **Discretised** parameter space, K levels | **VIOLATED as built** | `rl/contract.py`: 7-D continuous box, normalised [0,1]; SAC is continuous-action |
| 5 | A **DC sweep exists to build the gm/ID lookup** for the PDK | **SATISFIED — already built** | `device/gmid_lut.py` -> `data/gmid_lut_sky130_nfet01v8.npz`, 3 000 invocations / 510 s at 6 workers, 4 corners, gm/ID 0.56-35.87 1/V, 100.00 % monotone in V_gs |
| 6 | **One agent per topology** | **SATISFIED** | S2 is mandated; CLAUDEwa §8 rule 5 forbids changing it |

**Precondition 1 is the one that matters and it is not a close call.** The paper
states directly that nonlinear operation is outside the method's scope. Our binding
failure *is* nonlinear operation:

    linear input range at Nyquist    153 / 172 / 219 mVpp
    link drive at the CTLE input                535 mVpp
    OVERDRIVE                        2.44 / 3.11 / 3.49 x

and, independently, **115 of 116 unscorable candidates (99.1 %) in entry 32 fail on
output-swing compression** — the small-signal fit stops describing the stage. A
method whose premise is "hold the DC operating point fixed and search only AC
behaviour" is aimed at a regime we have measured ourselves to be outside of.

---

## 2. Mechanism-by-mechanism verdict

### 2.1 gm/ID reparameterisation — **SKIP.** Already done here; negative.

`GMID_MAP.md` (session 20) built the table, built the map (`common/design_space.py`),
ran the validation (`experiments/exp_gmid_validation.py`), and has 75 tests behind it.
Findings:

* **The stated mechanism is falsified.** The hypothesis was that making `f_z` a
  coordinate puts the G44 sweep-edge region out of reach by construction. Measured:
  **38.07 % in device coordinates vs 37.74 % in design coordinates.** Unchanged.
* **The real benefit is small and arrives by a different route:** 89.40 % of
  design-space proposals are rejected pre-simulation, but because they are not
  representable in the device box at all (878 of 1341 = "no width in 20-100 um
  carries this current at this inversion level"). Net: **1.90 -> 1.64 simulations
  per valid design, 1.16x.**
* **The analytic peak predictor cannot serve as a pre-simulation filter:** TN = 0,
  precision 61.78 %; with the 20 GHz ceiling defect fixed, TN = 8, precision 65.10 %.
* **A PDK finding that attacks the paper's premise directly:** on SKY130 at fixed
  `nf`, **I_D/W varies 1.56x across the `w_in` box** because `W/nf` sweeps the model
  bins. Scaling current linearly in `W` — which is what the textbook gm/ID method
  does — is a **56 % width error** on a device that simulates happily. The paper's
  40 nm result does not carry across this binning.

**Blast radius if adopted anyway:** `common/params.py`, `rl/contract.py`, `rl/env.py`.
`GMID_MAP.md` §0 states it plainly — adopting this **invalidates every existing
baseline comparison**. That fires `BASELINES.md` §7f, which re-runs every published
arm: the 25 500-simulation sweep (~42 min), the budget ladder, and every reward
number in the report. **With 17 days left this is disqualifying on schedule alone,
before the measured negative is even considered.**

**What to do with it instead — and it is already on the task list.**
`CONTINUE_HERE.md` §6.3 row 10: report gm/ID as a **measured negative**, with the
1.16x and the 56 % binning finding attached. This is worth real points. It converts
the most obvious question an analog-designer judge will ask ("why not gm/ID?") from
an opinion into a measurement, and the binning result is a genuine PDK contribution
that outlives the experiment.

### 2.2 Sequential feasible-problem decomposition — **SKIP for 15 Sept.** The usable residue is already row 8 and costs zero simulations.

There is a real insight here and it deserves naming. The method optimises
**feasibility, then walks the target** — which is a structural answer to G102. Our
maximin gives no credit for exceeding a met spec, so it goes *flat*: within 0.001 of
the best score the population spans **8.4x in tail current**, and the delivered
operating point was drawn from a plateau rather than chosen. The repo's own diagnosis
is "the lever is an added term". Target-walking is a **different lever for the same
defect**: tighten the target by δ until feasibility breaks, and the last feasible
point has margin by construction — no new reward term needed.

**But the precondition fails.** `CONTINUE_HERE.md` §5 OPEN item 5:
`target_peaking_db` is accepted by `reward_v1.margins` and **deliberately ignored**,
so one design scores identically against targets of 3, 5, 7.5, 10 and 12 dB. **The
spec manifold is effectively 1-D.** You cannot walk a target the objective cannot
see. Making it live is flagged in the same section as moving *every published reward
number* — a §7f re-run event — and is reserved to the owner under rule 6.

**Cheap substitute that captures the same idea, zero simulations:**
`CONTINUE_HERE.md` §6.2 item 8 — re-score the **74 526 designs already on disk**
through `spec_pool` with a lexicographic tiebreak (maximise `min(margin/tol)`, then
minimise tail current within ε). That is "feasibility first, then improve" harvested
from data we already own. Prefer it.

### 2.3 Adaptive action space — **SKIP.** The benefit is convergence speed; convergence speed is not our problem.

Cheapest piece in the paper (α -> 0 recovers fixed-step exactly, so a fixed-step
agent can be *deployed* adaptively with no retraining). Its claimed gain is reward
crossing zero at ~10k/30k steps instead of ~70-80k.

Our RL is **statistically indistinguishable from uniform random search at every
budget from 150 to 2 400 simulations**, while CMA-ES is separably better at every
one. **Reaching the same null faster is not a result.** Two further reasons:

* The paper reports larger α **destabilises** convergence on the more complex
  topologies (their Fig. 14b/14c). Ours is 7-D against their 3-D CTLE action.
* We partly have it already: SAC learns a per-dimension σ, measured moving
  `log_std` **-1.7788 -> -2.0902** (σ 0.169 -> 0.124) over the SPICE fine-tune.
  That is an adaptive step size arrived at by learning rather than by an α heuristic.

### 2.4 Parasitics as unobserved environment variation — **PROTOTYPE.** The only piece here aimed at a live, measured, open failure.

Mechanism: inject the varying quantity into the simulator, **withhold it from the
observation**, and the agent adapts without ever being told the value.

Why this one fits *this* repo specifically:

1. **`cl` is currently pinned.** `rl/contract.py` §2 lists `cl` as CONTEXT, "Fixed
   at `cl_mid` = 32.63 fF for this run."
2. **Compliance is reported over a 135-point grid = 45 mandated corners x 3 loads**,
   and the load range is **13.64 -> 78.04 fF, 5.72x, 2.52 octaves** with per-edge
   provenance (`CL_RANGE.md` §5).
3. **That axis is the project's named open failure: 135-point load grid 0 of 16**
   (entry 40), against mandated-corner coverage of 8 of 16. The policy has never been
   trained on the axis it is scored on.

**This is NOT what G42 killed, and the conflation is the trap.** G42 /
`CL_SENSITIVITY.md` measured that letting the search **choose** `cl` lowers the S3
yield — pinning at 150 fF took it from 8.73 % [7.54, 10.09] to 13.54 % [12.08, 15.16]
on disjoint intervals. An agent choosing its own load is reward hacking: `contract.py`
says it outright — "an agent that could choose its own load could buy S3 by declaring
a load nobody will build." **Domain randomisation is the opposite move.** `cl` is
drawn per episode from the measured `CL_RANGE` and never enters the observation, so
the policy *cannot* select for it and must pay for load sensitivity. G42 forecloses
the first; it says nothing about the second.

**Blast radius — the smallest of anything in these three briefs.** It changes the
**environment**, not the action space, not the observation dimension, not the reward.
`reward_v1.py` is untouched (G111 satisfied), `contract.py`'s ACTION_SPACE is
untouched, so **no published baseline is invalidated and §7f does not fire.** It does
need a new env or a flag on an existing one, and a training-config change is rule 6
territory: **the owner decides.**

**Cheapest falsifying experiment.** Reuse the entry 36/38 harness verbatim — 16
requests, k = 5, ~1 600 decks, ~18 min — with two arms: today's `cl`-pinned policy
and a `cl`-randomised one. Score on **135-point coverage**, where the current value
is **0 of 16**, and on accept rate against the library's **6 of 16**.
Pre-registration must state a falsifier; the obvious one is *135-point coverage
remains 0 of 16 and accept rate does not exceed 1 of 16*, i.e. it behaves like entries
36 and 38.

---

## 3. Transfer analysis (brief §4 setting vs ours)

| Axis | fRL-AD's CTLE | Ours | Effect on the claimed gain |
|---|---|---|---|
| State / action | 2-D state (A_DC, ω_z), 3-D action | 18-D obs, 7-D action | Their one-stage-amp case is degenerate (param space = obs space); complexity is not comparable |
| PVT | **none anywhere in the paper** | 45 mandated corners x 3 loads | Their entire result is one operating condition |
| Load | fixed 1-2 pF, never swept | 5.72x range, swept as a robustness axis | The axis we fail on does not exist in their setting |
| Specs | gain, GBW, bias current | + noise (S5), HD3 (S4), eye (S8), channel, DFE | Noise/distortion named as *future work* by the authors |
| Nonlinearity | assumed absent | **measured present, 2.44-3.49x overdrive** | Precondition 1 |
| Their own CTLE result | **partially negative** — 0.78 Grad/s reported unreachable, behaving as a structural ceiling | — | The one topology closest to ours is where their method reports a wall |

There is no axis on which their setting is harder than ours. The claimed gain is
**variance reduction, not a better mean** (brief §4), measured against AutoCkt — see
the 003 eval, where that comparison is the useful part.

---

## 4. Verdicts

| Piece | Verdict | One-line reason |
|---|---|---|
| 2.1 gm/ID reparameterisation | **SKIP** (report as measured negative) | Already measured here: mechanism falsified, 1.16x residual, 56 % width error from SKY130 binning; adopting invalidates every baseline |
| 2.2 Sequential feasible problems | **SKIP for 15 Sept** | Target is deliberately inert in the reward; spec manifold is 1-D; the usable residue is row 8, zero simulations |
| 2.3 Adaptive action space | **SKIP** | Speeds convergence to a measured null; α destabilises at higher d; SAC already learns σ |
| 2.4 Unobserved environment variation | **PROTOTYPE** — owner decision | Smallest blast radius of anything here; aimed at the 0-of-16 load grid; distinct from what G42 killed |

---

## 5. Strongest argument against each verdict

**Against SKIP on 2.1.** `GMID_MAP.md` tested the reparameterisation as a *search
coordinate system* and measured that it does not make the bad region unreachable.
That is not the same claim as fRL-AD's. fRL-AD's claim is that holding the **DC
operating point fixed by construction** removes the uncertainty term from the
objective — and our G44 measurement (38.07 vs 37.74 %) says nothing about DC bias
validity, because G44 is a *frequency-sweep-edge* artifact, not a bias artifact. A
reviewer wanting the opposite outcome would say we falsified a hypothesis of our own
construction and then attributed the falsification to the paper. The counter to the
counter is precondition 1 and the 56 % binning error, neither of which depends on
the G44 argument — but the objection is fair and the eval should not lean on G44.

**Against SKIP on 2.2.** The 1-D spec manifold is the very thing §5 OPEN item 5 says
we should consider fixing, and §5 also says making `target_peaking_db` live "would
make the problem genuinely 2-D". Sequential target-walking is arguably the *best
motivated* reason yet offered to make it live, because it turns the target from a
decoration into the search's control variable. Dismissing 2.2 on the grounds that
the target is inert is circular: the target is inert because we chose to ignore it.
The honest reason to skip is **17 days and a §7f re-run**, not the precondition.

**Against SKIP on 2.3.** "RL is a null so speed does not matter" assumes the null is
about the policy rather than the budget. If the crossover simply lies beyond 2 400
simulations — which `CONTINUE_HERE.md` §6.2 item 7 explicitly says we should state as
the honest framing — then a 3-7x reduction in steps-to-crossover is precisely the
thing that would move the crossover inside our budget. Someone wanting adaptive steps
would say we are refusing the one cheap change that could falsify our own null.

**Against PROTOTYPE on 2.4.** This is the strongest counterargument in the file, and
it is a pattern, not a guess. Entry 36: SAC as proposer, 1 of 16 against the library's
6. Entry 38: fix the blind spot the mechanism named (swing), and accept rate does not
move — the failures **migrate** to `S3_peaking_match` / `S3_f_peak_match`, because
buying headroom moves the poles. The lesson entry 38 registered is that **fixing one
missing quantity exposed the next constraint**. Load randomisation is a *third*
blind spot on the same policy, and the base rate for "this fix will be the one that
pays" is now 0 for 2. A reviewer would say: this is the third consecutive attempt to
rescue an RL arm that has been measured worse than a zero-simulation lookup twice,
and with 17 days left the expected value of the sixth item on the list is below that
of the five report items above it. **That objection is correct on expected value and
is why 2.4 is ranked below the writing work, not above it.**
