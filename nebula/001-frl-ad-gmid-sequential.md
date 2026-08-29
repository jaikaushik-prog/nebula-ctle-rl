# Proposal 001 — fRL-AD: gm/ID parameterisation + sequential feasible-problem RL

**Source:** Hong et al., "Analog Circuit Design Automation via Sequential RL Agents and Gm/ID
Methodology", IEEE Access vol. 12, 2024, pp. 104473–104489. DOI 10.1109/ACCESS.2024.3435331.
Full PDF at `papers/frl-ad-2024.pdf` — read specific sections only if this brief is insufficient.

**Status:** UNEVALUATED. Do not implement. See `EVAL_PROTOCOL.md`.

---

## 1. Core claim

Sizing is treated as multi-objective combinatorial optimisation under uncertainty. Two moves are
claimed to make it tractable: (a) reparameterise so the DC operating point is held fixed and only
AC behaviour is searched, which removes the uncertainty term from the objective; (b) replace the
single hard optimisation with a chain of easier feasibility problems, each seeded by the solution
of the last.

## 2. Mechanism — four separable pieces

These are independent. Each can be adopted or rejected on its own.

**2.1 gm/ID reparameterisation.** The agent does not act on W/L. It acts on bias currents, with
transconductance efficiency gm/ID and the normalised parasitics Cdd/ID, Cgg/ID looked up from a
prior DC simulation sweep. Because gm/ID depends only on bias condition and not on W/L, the
lookup is reusable across geometries. Sizing is then recovered arithmetically at the end. The DC
operating point is fixed by construction, so no sampled point can be mis-biased.

**2.2 Sequential feasible-problem decomposition.** Define a spec target vector x*, and a feasible
region F = {q : wᵀd(q, x*) ≤ η}, where d is a per-spec distance and w a fixed preference vector.
Run the pre-trained policy for at most T steps. If it lands in F, tighten the target by a positive
step δ and repeat from the design just found. If it times out at T, loosen the target by δ instead.
Iterate up to I_max times. The last reached point is the answer. The step δ and the tolerance η are
hyperparameters chosen from domain knowledge, not learned.

**2.3 Adaptive action space.** Instead of a fixed ±1 quantisation step, the step magnitude scales
with how far the current measurement is from target: Δ_t = max(1, floor(α·r_t)), action space
{−Δ_t, 0, +Δ_t} per dimension. α trades convergence speed against variance. α → 0 recovers the
fixed-step case exactly, so this is a strict generalisation and an agent trained with fixed steps
can be *deployed* under adaptive steps with no retraining.

**2.4 Parasitics as unobserved environment variation.** Normalised parasitic capacitance is
injected into the simulator but withheld from the agent's observation. The agent is reported to
adapt by spending more current to drive the same load, without ever being told the parasitic value.

Algorithm details for 2.2 are on p. 104479 (Algorithm 1); reward shaping and the three constraint
types (upper-bound, lower-bound, error/centred) on p. 104480.

## 3. Preconditions the method assumes

Check every one of these against the current repo state.

- The circuit is adequately described by a **small-signal AC equivalent**. The authors state
  directly that this is what breaks: nonlinear and switched-capacitor circuits are outside the
  method's scope.
- The **objective set is scalarisable** by a fixed preference vector w. The authors list scalar
  reward as an acknowledged limitation and name vector-reward RL as future work.
- Every spec is expressible as a **graded distance** to a target — the reward is built from
  per-spec distance functions plus a constant terminal bonus.
- **Discretised parameter space.** Each of N parameters quantised to K levels; convergence bound
  is stated as O(K·N) per validation, O(I·K·N) overall.
- A **DC sweep exists to build the gm/ID lookup** for the target PDK.
- **One agent per topology.** Retraining is needed for a new topology; not for a new spec target
  within the trained range, and not for a new characteristic vector c.

## 4. Reported results and their setting

40 nm process, five topologies (1-stage diff amp, 2-stage diff amp, OTA, CTLE, CTLE with active
inductor), PPO, K = 200, load capacitances 1–2 pF. Headline numbers:

- Against AutoCkt (transistor-level RL, ref [17]) on 100 trials: the gm/ID agent shows tighter
  spread on gain / GBW / bias current. The claim is **variance reduction**, not a better mean.
- Adaptive action: reward crosses zero at ~70–80k steps with fixed action vs ~10k/~30k at α = 10/30
  on the differential amplifier. Larger α raises per-episode variance on the more complex
  topologies, so α is a tuning knob, not a free win.
- AC-equivalent results track post-layout simulation to roughly 0.2 dB gain / ~1 GHz GBW on the
  amplifiers.
- **The CTLE result is partially negative.** With DC gain pinned at 1, the agent hits zero
  frequency targets of 0.34 and 0.56 Grad/s but reports 0.78 Grad/s as unreachable for that
  topology. The bandwidth ceiling behaves as a structural limit, not a soft cost.

## 5. Costs and known failure modes

- The gm/ID table must be regenerated per process, per device flavour, per temperature if bias
  shifts materially with it.
- Terminal reward is a constant bonus; the method optimises *feasibility*, then walks the target.
  It does not directly maximise margin.
- δ and η are hand-set from expert judgement. Bad δ makes the chain either stall or overshoot.
- Larger α destabilises convergence on higher-dimensional topologies (their Fig. 14b/14c).
- No PVT corner treatment anywhere in the paper. Every result is a single operating condition
  plus injected parasitics.
- No noise, no PSRR, no distortion spec — named as future work.

## 6. Explicitly setup-specific — likely does not transfer

- Their CTLE state is 2-D (A_DC, ω_z) with a 3-D action; no eye metric, no DFE, no channel.
- The one-stage amplifier case is degenerate: parameter space and observation space coincide, so
  results there overstate how easy the mapping is.
- 1–2 pF loads. Load capacitance is fixed, never swept as a robustness axis.
