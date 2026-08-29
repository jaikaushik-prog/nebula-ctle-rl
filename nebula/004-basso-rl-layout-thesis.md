# Proposal 004 — RL floorplanning and routing (Basso thesis)

**Source:** Davide Basso, "Automating the Layout of Analog Circuits: A Machine Learning-Based
Approach", PhD thesis, Università degli Studi di Trieste, XXXVIII cycle, Applied Data Science &
AI, funded by Infineon Technologies. Supervisors Bortolussi, Videnovic-Misic, Habal. 137 pp,
compiled Dec 2025. Local copy at `papers/basso-thesis-2025.pdf`.

**Status:** UNEVALUATED. See `EVAL_PROTOCOL.md`.

**Scope warning — read before evaluating.** This thesis is about **layout**: floorplanning
(where devices go) and routing (how wires connect them). It is not about sizing. Nothing in it
proposes a spec-to-parameter map, and none of its metrics (area, half-perimeter wirelength,
routability, DRC compliance) are our metrics. Do NOT evaluate it as a sizing method — it will
score `skip` on every precondition and that will be a meaningless result.

Evaluate it on two narrower questions instead:
(a) which of its **RL formulation techniques** transfer to our environment, independent of the
    layout domain they were developed in;
(b) whether it changes the answer on layout scope (proposal 002 §1.1, proposal 003 §2).

---

## 1. What the thesis actually builds

Four successive floorplanning engines plus a routing flow, integrated into ANAGEN, Infineon's
internal procedural layout generation framework.

1. **RL-SA and Annealed-RL.** Two floorplanners — one where RL cooperates with simulated
   annealing, one where the RL agent's behaviour and state representation imitate the SA search
   instead. Supports device symmetry, alignment, target aspect ratio, and variable per-device
   shapes.
2. **R-GCN RL.** A relational graph convolutional network is first trained *supervised* to predict
   the reward of a circuit placement. The trained model is then frozen and reused as an **encoder**
   of circuit, device and geometric constraints feeding the RL agent's state. Devices are placed on
   a discretised 32×32 grid.
3. **BS-RL.** A beam search wrapped around the trained R-GCN RL policy at inference time.
4. **Routing-aware R-GCN RL.** Adds device pin information to the graph, a U-Net policy, dynamic
   routing resource estimation, and a revised reward, followed by an A* rip-up-and-reroute engine.

Global routing uses an obstacle-avoiding rectilinear Steiner minimal tree; detailed routing is A*
honouring parallel-run-length spacing, end-of-line spacing and via spacing.

## 2. The transferable techniques — these are the reason to read it

**2.1 Action masking (highest relevance).** The state carries positional masks over the grid
marking which cells are admissible for the next block given non-overlap and spatial constraints,
and *these same masks are used to mask the action space*. An action that would produce an invalid
placement is not merely penalised — it cannot be selected.

Why this matters here: our v1 measured 26.5% of evaluations invalid, 78% of those being a fake
peak that would have scored high, and G72 records the distinction we drew between a validity gate
and a reward. Masking is a third option we have not considered — prevent rather than gate or
penalise. Open question for the evaluator: how much of our invalid region is knowable *before*
simulating (e.g. bias conditions computable from a cheap .op, or geometric constraints on the box)
versus only after? Masking only pays where invalidity is predictable a priori.

**2.2 Beam search at inference, with objective weights set by the user.** BS-RL wraps the trained
policy without any finetuning, lets the user set trade-off weights between competing metrics at
inference time, and is reported to improve the baseline by 5–85% across metrics, comparable to a
finetuned approach and without needing a GPU.

Why this matters here: our abstract framing is automation and tunability. A trained policy that
can be re-weighted at inference — favour peaking here, favour power there — is a direct fit for
"one map, many operating points", and costs no retraining. The reported cost profile (no GPU)
suits our setting, where 99.7% of run time is the simulator, though a beam widens the number of
simulator calls per decision and that trade needs measuring, not assuming.

**2.3 Pretrain a reward predictor, reuse it as the state encoder.** Rather than learning
representations from RL signal alone, a network is trained supervised to predict placement reward,
then repurposed as an encoder. The stated rationale is that aligning the pretraining task with the
agent's objective makes the embeddings carry meaningful signal and improves generalisation.

Note this converges with the mentor-supplied ISCAS 2026 direction (ensemble surrogates + OOD
discriminator) from a completely independent domain. Two unrelated works pointing at the same
structure is worth a line in the deck.

**2.4 Dense partial reward plus terminal reward.** Per-step reward is the negative *increase* in
the proxy metrics caused by that action; the episode-end reward is a negative weighted sum of the
final objectives. Contrast this with our banded-verdict reward and consider whether an incremental
form is available for any of our specs.

## 3. Convergent limitation — worth noting across proposals

The thesis states as a limitation that it treats an inherently multi-objective problem as a
single-objective one via a weighted sum, and names multi-objective RL as future work. Proposal 001
§5 records the same admission from fRL-AD. Two independent groups naming scalarised reward as the
known weak point is a stronger signal than either alone, and it lands on a design decision we have
already made.

Its other stated limitations: dynamic routing resource allocation overestimates the space needed;
HPWL is only a proxy and richer signals from the router or from post-layout electrical simulation
would guide optimisation better; A* needs broader DRC coverage before producing sign-off-ready
output.

## 4. Reported results, and what they are results *about*

Over 20 industrial use cases: routability improved 73.4%, layout time reduced 67.3% versus manual,
mean area reduced 8.3% versus manual. RL approaches reported to beat metaheuristic baselines on
area, proxy wirelength, speed and cost.

Two honest observations. First, none of these metrics is one of ours — this is not evidence that
anything here helps a sizing agent. Second, the *shape* of the headline claim is worth copying:
time-to-produce versus a manual baseline, on a set of real cases. That is exactly the
cost-to-produce-N-designs comparison our abstract framing already promises, and this thesis is a
template for how to present it credibly.

## 5. Not transferable

Everything geometric and everything infrastructural: floorplanning representations, OARSMT global
routing, the A* detailed router, DRC rule handling, common-centroid and interdigitated placement
patterns, dummy devices for well-proximity effects, Pcells. ANAGEN is Infineon-internal and is not
available to us. The grid discretisation and graph encoding are built for circuits far larger than
a single CTLE stage plus a 1-tap DFE.

## 6. Scope reality

Final submission is 15 Sept. Nothing in §1 or §5 is buildable in that window. The items in §2 are
changes to an RL environment we already have, and are the only parts worth costing.
