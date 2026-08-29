# SCOPE_BOUNDARY.md — what this tool is claimed to cover, and what it is not

**Session 29, 2026-08-29.** Report-ready. No new measurement: every row below is
sourced from an artifact already in the repo, cited inline.

**Why this document exists.** Proposal 002 §1.2 (Vikas Vijay, a practising analog
designer) argues that a sizing tool must **state its own similarity boundary
explicitly**, because "similar circuit" is undefined and a tool that silently
generalises past its training is worse than one that refuses. We have always had
a boundary — one topology, one PDK, a stated box — and had never written it down.
An unstated boundary invites the same question as a narrow one, with no answer
ready.

**This is also the honest reading of the brief's "zero human intervention".** We
automate **sizing inside the box below**. We do not claim to choose the topology,
produce a layout, or sign off verification. Saying so precisely is what makes the
automation claim credible rather than overreaching.

---

## 1. The boundary, in one table

| Axis | What is covered | Source |
|---|---|---|
| **Topology** | Exactly one: 1-stage CTLE with source degeneration (variable `Rs`, `Cs`) plus a 1-tap DFE. No retraining claim across topologies. | S2, mandated; CLAUDEwa §8 rule 5 |
| **Signalling** | NRZ, PCIe Gen2, 5.0 Gbps, Nyquist 2.5 GHz | S1 |
| **PDK / device** | SKY130, `nfet_01v8`, VDD **1.8 V** nominal ±5 % | `G0_RESULTS.md`, G33, G36 |
| **Parameter box** | `w_in` 20–100 µm · `l_in` 0.15–1.0 µm · `i_bias` 0.5–8 mA · `rs` 50–1000 Ω · `cs` 100 fF–10 pF · `rl` 50–800 Ω · `vcm_in` 1.1–1.6 V | `rl/contract.py` |
| **Load** | 13.64–78.04 fF (**5.72x**, 2.52 octaves), per-edge provenance | `CL_RANGE.md` §5 |
| **Channel** | `IL_dB(f) = A√f + B·f`, 21-member family. **Loss at DC is exactly 0 by construction.** | `CHANNEL_MODEL.md` |
| **Corners** | 45 mandated = 5 process (TT/SS/FF/SF/FS) × 3 VDD (±5 %) × 3 temp (0/27/125 °C); × 3 loads = **135 points** | S9; `S9_YIELD.md` |
| **Spec target** | Peaking 3–12 dB, peak in 1.25–2.5 GHz — but see §3: the target axis is **effectively 1-D** | S3; `CONTINUE_HERE.md` §5 OPEN item 5 |
| **Layout** | **Not covered.** Schematic-level only; see §2 | — |

**Outside any of these, the tool makes no claim.** A different topology needs a
retrained policy and a re-derived box. A different PDK needs the gm/ID table and
the `cl` range re-measured. A load outside 13.64–78.04 fF is extrapolation.

## 2. The layout boundary — and the part of it we DID bound

This is the objection a designer raises first, and it is fair: **every yield
number in this repository is a schematic number.** There is no layout, no
parasitic extraction, no LVS anywhere in the project.

**What we can say precisely, rather than as a caveat.** The dominant
layout-dependent quantity on the bandwidth-critical node is its capacitance, and
`CL_RANGE.md` §4 bounds it from PDK data rather than assuming it:

* the routing allowance is derived from `sky130_fd_pr__cap_vpp_01p8x01p8_m1m2_noshield`,
  **parsed at run time** (`ctot_a = 7.833e-16 F`, `rat_m1 = 0.387`,
  `rat_m2 = 0.596`, 22 and 28 squares), and the function **raises** if the PDK
  file's structure changes rather than falling back on a remembered value;
* that gives **m1 = 0.0984 fF/µm** and **m2 = 0.1191 fF/µm**;
* applied to stated wire lengths (20 µm abutted, 120 µm displaced by a lane
  pitch): **1.97 fF and 14.29 fF**;
* which is **14 % of `cl_lo` and 18 % of `cl_hi`** — and the design is verified
  across the whole range, so the routing allowance is *inside* the compliance
  result, not a correction applied after it;
* **doubling the entire allowance moves `cl_hi` by 18 %** — a fifth of an octave
  against a range 2.52 octaves wide.

So the defensible sentence is:

> We do not run post-layout extraction. We bound the dominant layout parasitic on
> the output node from PDK capacitor data, carry it inside the load range the
> design is verified across, and measure that doubling it moves that range by a
> fifth of an octave. **The compliance result is not sensitive to the routing
> assumption.**

**Two declared weaknesses that must travel with that claim** — both stated in
`CL_RANGE.md` itself, and quoting them is what makes the rest credible:

1. **The metal width (0.14 µm) is declared, not measured.** This install carries
   `libs.tech/ngspice` and `libs.ref/sky130_fd_pr/spice` only — no tech LEF, no
   magic techfile. It is a divisor: if fingers are drawn wider than minimum, the
   real fF/µm is *lower* and both edges move down.
2. **Wire length is stated, not measured, because there is no layout.** The
   20 µm / 120 µm pair is argued from how a bandwidth-critical node is floorplanned,
   not from a drawn one.

There are two further reasons the figure is an **upper** bound on a routing wire,
which is why it is honest to use it for the upper edge: a finger capacitor has a
minimum-spaced neighbour on *both* sides, which routing normally does not; and
`ctot_a` includes the m1–m2 coupling that makes it a capacitor at all.

**What this does NOT answer.** STI stress, well proximity, and device mismatch —
three of the four effects proposal 002 §1.1 names. We bound none of them. The
GNN-based parasitic prediction that brief points toward, and the netlist-to-GDS
route through ALIGN (`003-bag-autockt-align-magical.eval.md` §2), are both named
future work, not results.

## 3. The boundary row that is uncomfortable, stated anyway

**The spec target axis is effectively one-dimensional.** `target_peaking_db` is
accepted by `reward_v1.margins` and **deliberately ignored**, so one design scores
identically against targets of 3, 5, 7.5, 10 and 12 dB
(`CONTINUE_HERE.md` §5 OPEN item 5).

This belongs in the boundary rather than being discovered by a reader, because it
is the honest explanation for a result we report elsewhere: a lookup over
already-simulated designs serves **32 of 32** held-out targets, and 50 random
designs serve 100 % of them. **On a 1-D manifold a lookup table *is* the optimal
policy** — that is a property of the problem as posed, not a failure of the
learner. It is also the gate on two independent external proposals
(`001-...eval.md` §2.2 and `004-...eval.md` §2.2), both of which need the target
to be live before they can be tried.

## 4. How to use this document

* **In the report:** as a boxed "Scope and limitations" section, early, before the
  results — not as an appendix. A boundary stated up front reads as engineering
  discipline; the same boundary extracted under questioning reads as a defect.
* **In the demo:** it is the answer to "what happens if I ask for something
  else?" — the tool's domain is §1's table, and outside it the answer is
  *"retrain / re-measure", not a number.*
* **Do not soften it.** The value of this document is entirely in its being
  believed.
