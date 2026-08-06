# PASSIVES.md — replacing the ideal R and C with real SKY130 devices

**Session 15, 2026-08-06/07.** Tests 698 -> 725 (+27), 9 deselected.

---

## 0. Status — what this document establishes, and what it does not

Task 4 has ten parts. This document covers **four of them completely** and one
structurally. The rest are set up but not run, and are listed as open rather
than sketched, because a half-run corner sweep is worse than none.

| Part | | Status |
|---|---|---|
| 4a | Enumerate the families, choose with reasoning | **DONE** — §1 |
| 4b | Measure passives properly, gate on nominal accuracy | **DONE** — §2 |
| 4c | Extend the trimmed library, re-verify bit-identical | **DONE** — §3 |
| 4i | Discretisation + `to_geometry()` | **DONE** — §4 |
| 4f | Do the passives change which corners are worst? | **STRUCTURE ESTABLISHED, SWEEP NOT RUN** — §5 |
| 4d | Regression gate: real passives at nominal | **NOT DONE** — §6 |
| 4e | f_z movement in octaves, pre-registered | **NOT DONE** — §6 |
| 4g | Parasitics into the `cl` budget | **PARTIAL** — the model is extracted (§4.4), not yet folded into `CL_RANGE.md` |
| 4h | S7 area from real geometry | **PARTIAL** — first numbers in §4.5, no ladder projection |
| 4j | Declare what is not being done | **DONE** — §7 |

**Nothing here changes any published number.** No experiment has been re-run
with real passives yet; `s9_yield.py` and `tunable.py` still instantiate ideal
`R` and `C`. What exists now is the device layer those experiments need.

---

## 1. (4a) What is actually installed

Enumerated from `C:\Users\DELL\sky130A`, not from memory. Every constant below
is re-read from the PDK by `test_passives.py` and the test fails on drift.

### 1.1 The question that had to be answered first

4a said to stop and report if the MIM family the design wants is not in this
metal stack. **It is.** `sky130_fd_pr__cap_mim_m3_1` (capm, between m3 and m4)
and `..._m3_2` (cap2m, m4/m5) are both installed and both simulate. So the task
proceeds as written.

### 1.2 Resistors

| Family | `w` | `l` | Multiplier | Sheet | Notes |
|---|---|---|---|---|---|
| `res_high_po` | **free** | free | `m=` only | 317.39 Ω/sq body | + a fixed head term |
| `res_xhigh_po` | **free** | free | `m=` only | 2000 Ω/sq | 6.3× the sheet |
| `res_high_po_{0p35,0p69,1p41,2p85,5p73}` | **FIXED, in the name** | free | `m=` only | width-specific | voltage coefficients implemented |
| `res_xhigh_po_{same five}` | **FIXED** | free | `m=` only | width-specific | |
| `res_generic_{nd,pd}` | free | free | — | 120 / 197 Ω/sq | diffusion; junction-isolated |
| `res_iso_pw` | free | free | — | 3816 Ω/sq | isolated p-well |

The fixed-width families exist at **exactly five widths: 0.35, 0.69, 1.41,
2.85, 5.73 µm.** This is what 4a warned about, and it is worse than "only a
fixed set is permitted" — see trap 2 below.

**The head resistance is the non-obvious part.** `res_high_po` is not
`rsheet · l / w`: it carries a fixed contact/head term that does not scale with
length. Measured floor at `l = 0.5 µm`:

```
w = 0.35 µm   ->  1444 Ω          the whole rs bound (50-1000 Ω) is
w = 1.00 µm   ->   537 Ω          UNREACHABLE at minimum width
w = 2.85 µm   ->   198 Ω
w = 10.0 µm   ->    58 Ω
```

This is why `to_geometry` widens rather than shortens, and why the low end of
`rs` and `rl` needs 8-10 µm devices.

### 1.3 Capacitors

| Family | Density | Terminals | Bias-dependent? |
|---|---|---|---|
| `cap_mim_m3_1` / `_m3_2` | **2.00 fF/µm²** areal + 0.19 fF/µm perimeter | **2 — no bulk node** | **No.** `tc1 = tc2 = 0`, no voltage argument anywhere |
| `cap_var_{lvt,hvt}` | higher | 3 | **Yes, strongly** — explicit `cmin`/`cmax` with `tanh`/`log-cosh` |
| `cap_vpp_*` (finger) | lower | 2-3 | No |

Both MIM flavours measure **1.8197 pF at w = l = 30 µm**, identical to every
printed digit. They differ only in series resistance (7.697 vs 7.696 Ω).

### 1.4 The choice, and the reasoning

**`cs` -> MIM (`cap_mim_m3_1`).** 4a asked for MOS caps to be evaluated against
MIM on density, with HD3 measured before ruling a MOS cap in or out. **That
measurement was not needed, because the decision falls out of the topology
before it gets to linearity:**

- `cs` sits **floating between the two source nodes** at ~+0.34 V, with the
  full differential swing across it. A MOS capacitor is a two-terminal device
  whose capacitance is a function of gate-to-channel voltage; a floating one
  with a differential signal across it sees its capacitance modulated by the
  signal it is supposed to be setting a pole with. The varactor models make
  this explicit — they take a bulk terminal and define `cmin`/`cmax` against
  `v(c0) - v(p2)`.
- The MIM has **no bulk terminal and no voltage argument at all**, so it is
  valid in exactly this floating configuration, which is what 4a asked to check
  rather than assume.
- Density: MIM is 2.00 fF/µm², so the largest `cs` in the box (10 pF) is a
  70.5 µm square — 4,970 µm², under **10 %** of the S7 budget. **Area is not
  scarce enough to buy nonlinearity with.** That is the argument that settles
  it, and it is a measurement, not a preference.

**`rs` and `rl` -> `res_high_po` (generic, 317 Ω/sq).** Chosen over
`res_xhigh_po` because at 2000 Ω/sq the whole `rs` bound sits below one square,
so value would be set entirely by the head term and the width, with length
doing nothing — a bad grid exactly where 4a asks for a fine one. Chosen over
the fixed-width families because those give up the width degree of freedom that
the head-resistance floor makes necessary, and over the diffusion families
because a junction-isolated resistor puts a voltage-dependent depletion
capacitance on the degeneration node.

**One caveat on that choice, and it is recorded rather than resolved:** ngspice
discards the generic family's non-linearity terms (trap 3), so `res_high_po`
simulates as perfectly linear while the fixed-width families do not. A
linearity (S4) claim must therefore **not** be quoted off the generic family.
If HD3 ever becomes binding, the fixed-width family is the honest device to
measure it on.

### 1.5 The three silent traps

Each was found by measurement, each exits 0, and each is now pinned by a test.

**Trap 1 — `mult` and `mf` do nothing.** They are the parameter names the
subckts declare, so they read like device multipliers. In every SKY130 R and
MIM model they appear **only inside mismatch terms**, all multiplied by
`MC_MM_SWITCH`, which the corner files set to 0. Measured on `res_high_po`
w=1 l=1.78 at 10 µA:

```
mult=1   942.90 Ω
mult=4   942.90 Ω     <- IDENTICAL. a silent 4x error
m=4      235.72 Ω     <- exactly /4, and equal to four explicit
                         parallel devices to every printed digit
```

Same on the MIM: `mf=4` gives 1.8197 pF, `m=4` gives 7.2789 pF.
**Use ngspice's native `m=`.**

**Trap 2 — `w` is inert on the fixed-width families.** `res_high_po_0p69` with
`w=0.69`, `w=2.85` and `w=99` all return **2893.64 Ω**, identical to every
digit, and `w=99` raises nothing. The width is encoded in the subckt name and
baked into that subckt's `rsheet`. The device that really is 2.85 µm wide
(`res_high_po_2p85`) reads 718.61 Ω — so asking the wrong subckt for a width
is a **4.03× error, silently**. `l` *is* honoured; only `w` is inert.

**Trap 3 — ngspice discards the generic families' non-linearity terms.**
Loading `res_high_po` prints `unrecognized parameter (p2) - ignored`, and the
same for `q2`, `p3`, `q3` — exactly the terms that make the resistance depend
on the voltage across it. ngspice's `.model r` has nowhere to put them. So the
two families **disagree about whether a poly resistor is linear**, and the
generic one is optimistic.

---

## 2. (4b) How the passives were measured

Not read off model cards. Measured the way the rest of the project measures.

**Resistance:** instantiate the subckt alone, force a known DC current
(10 µA — small enough that the fixed-width families' voltage coefficients
contribute below the printed precision), measure the node voltage, report V/I.

**Capacitance:** drive with a 1 µA AC current at **1 MHz** and extract
`C = -1 / (ω · Im{Z})`. 1 MHz is justified rather than assumed: the MIM's
series resistance is ~8 Ω against a reactance of ~87 kΩ there, so `Im{Z}` is
the capacitance to 1 part in 10⁸, and the nearest resonance is orders away. A
1 GΩ resistor gives the floating node a DC path; it is four orders above the
reactance and does not perturb it.

**The gate.** `passives.py` carries an analytic, invertible model of each
device, and `test_passives.py` holds it against simulation. An invertible model
that disagrees with the device is worse than none, because `to_geometry` would
emit geometries that look right and measure wrong.

| Quantity | Model vs simulation |
|---|---|
| `res_high_po`, 6 geometries incl. `m=4` and both width regimes | **0.000 %** |
| MIM, 4 plates incl. `m=4`, at 4 passive corners | **−0.0065 %**, uniform |

The MIM residual is uniform across corners and is the 1 GΩ DC path's loading —
a systematic, understood offset, not scatter.

**One real bug this caught.** The first model used a single plate-offset
constant. It is per corner, and *asymmetric* — see §5.2. The model was wrong by
up to 0.7 % between two corners that both nominally have `cap_high`, and only
measuring at four corners rather than one exposed it.

---

## 3. (4c) The extended trimmed library

`nebula/device/spice/sky130_ctle.lib.spice` — **25 sections**, nfet + both
generic poly families + all ten fixed-width variants + the `res_po` parasitic
+ MIM.

### 3.1 Equivalence, at rel=0 abs=0

G36's bit-identical verification covered **nfet cards only** and did not
survive adding these devices. Re-established in
`test_trimmed_lib_passives.py`: 8 resistor geometries straddling both width
regimes and the head-dominated floor, 4 MIM plates spanning the `cs` bound,
plus the nfet, across **6 (MOS × passive) sections including two mixed ones**.

**Result: bit-identical, rel=0 abs=0, on every value.** The criterion did not
have to be relaxed, so 4c's "if bit-identity cannot be achieved, propose a
tolerance" clause does not apply.

Comparison is on **raw printed text**, not parsed floats — parsing to float and
back would hide a difference below the printed precision, which is exactly the
kind of "equivalent" this test exists to refuse. The test also asserts a
minimum value count, because a diff of two empty sets passes vacuously; that
false pass happened once during development and is why the guard is there.

### 3.2 The cost, and it is not free

Five runs each, same trivial netlist, same machine:

| Library | Runs (ms) | Mean | vs nfet-only |
|---|---|---|---|
| nfet-only (G36) | 531 801 593 557 686 | **634 ms** | 1.0× |
| **extended** | 5044 4702 4421 4541 4565 | **4655 ms** | **7.3× slower** |
| full | 57972 61131 55131 29881 32691 | 47 s | 0.014× |

**The extended library costs 7.3× the nfet-only one.** That is a real hit on
the RL inner loop: G48 budgets ~100 ms per corner evaluation at 8 workers with
the nfet-only trim, and this would push it toward ~700 ms.

**Run-to-run variability has NOT come back** in the sense G36 cared about —
the extended library's spread is 1.14× (4421-5044 ms), *tighter* in relative
terms than nfet-only's 1.51× (531-801 ms). The full library remains wild at
2.05× (29.9-61.1 s). Variability matters more than the mean for a fidelity
schedule, and on that axis the extended trim is well behaved.

**The likely cause of the 7.3× is identified but not yet acted on:** the R/C
corner files include `parameters/typical.spice` (3,023 lines) and
`invariant.spice` (7,340 lines), neither of which a resistor or a MIM cap
needs. Trimming those is the obvious next optimisation and is listed in §6.

### 3.3 The units trap, checked

G31/G36: a trimmed library must declare `.option scale=1.0u` **itself**,
because the full library sets it in `all.spice`, which no trim includes. Omit
it and `W=5` means five metres. A test asserts all 25 sections carry it, plus
`mc_mm_switch=0`.

---

## 4. (4i) Discretisation, and `to_geometry()`

### 4.1 The achievable grid

| Parameter | Free | Grid |
|---|---|---|
| resistor `w` | yes, 0.35-10 µm (generic family) | 5 nm layout grid |
| resistor `l` | yes, 0.5-50 µm | 5 nm layout grid |
| resistor `m` | yes, integer | exact |
| MIM `w`, `l` | yes | 5 nm layout grid |
| MIM `m` | yes, integer | exact |

### 4.2 The result, and it is a negative one

4i asked whether quantisation alone consumes a significant share of the
**0.12 octaves** of centring slack session 12b measured. **It does not.**

Over 4,000 Latin samples of the full `(rs, cs, rl)` box:

```
samples realisable            4000 / 4000        (none rejected)
|f_z quantisation| median     1.5e-4 octaves
|f_z quantisation| p99        8.2e-4 octaves
|f_z quantisation| MAX        1.04e-3 octaves
worst component error         0.070 %

as a share of the 0.12-octave slack:  0.87 %
```

**Quantisation is not a first-order effect here**, and the reason is
structural: `l` is free on a 5 nm grid while `f_z` depends on it only through a
ratio, so the grid is ~3 orders finer than the thing it has to resolve. This
was worth measuring precisely because the opposite result would have been a
headline.

At design 432 — the only corner-and-load-robust survivor:

```
rs = 319 Ω    ->  w=8.00  l=14.785 m=2   ->  319.001 Ω   (+0.0003 %)
cs = 1.90 pF  ->  30.660 × 30.660 µm     ->  1.90017 pF  (+0.0087 %)
rl = 565 Ω    ->  w=10.00 l=16.505 m=1   ->  565.032 Ω   (+0.0056 %)
f_z  target 262.59 MHz  ->  realised 262.56 MHz  =  -0.00013 octaves
```

### 4.3 `to_geometry()`

`nebula/device/passives.py::to_geometry(rs, cs, rl)` maps a continuous triple
onto drawable devices. It is treated as a deliverable, not a helper — it is
what turns the framework's output into a schematic.

Search order, and the order is the whole content of the function:

1. **Narrowest width first** — area and bottom-plate parasitic both scale with
   width, and the parasitic lands on `cl` when the device is `RL` (§4.4).
2. **`m = 1` first** — a multiplier buys reach at the low end but costs a
   factor of `m` in both area and parasitic.
3. **Reject rather than clamp.** A target below the head-resistance floor at
   every legal width raises, with the floor quoted in the message. Clamping is
   how an undrawable geometry ends up in a netlist that simulates fine.

### 4.4 The `RL` bottom-plate parasitic — the 4g model

The PDK models it as `sky130_fd_pr__model__parasitic__res_po`, which puts
**half on each terminal**:

```
C_half = ((l + 4.16)·w·crpf_precision + 2·(l + 4.16 + w)·crpfsw_precision) / 2
```

So the amount landing on the output node is half the total.
`PolyResistorModel.parasitic_to_bulk_f()` implements it, per passive corner.

**This is extracted but NOT yet folded into `CL_RANGE.md`** — that requires the
`cl` budget to be re-derived and re-published, which is §6 work.

**The MIM has no bulk terminal at all**, so the model carries no bottom-plate
capacitance for `cs`. That is a modelling *absence*, not a physical one, and it
must be derived the G51 way rather than assumed to be zero. Not done.

### 4.5 First area numbers (4h, partial)

At design 432, drawn device area only:

```
cs   30.66 × 30.66            940 µm²    62 %
rs   8.00 × 14.785 × 2        236 µm²    16 %
rl   10.00 × 16.505 × 2       330 µm²    22 %   (two loads)
                            --------
                            1,506 µm²  = 0.0015 mm²
```

against the S7 budget of 0.05 mm² — **about 3 %**. So **`cs` does dominate the
passives (62 %), confirming 4h's expectation, but the passives do not stress
S7 at all** at this supply and these values. Even the largest `cs` in the box
(10 pF, a 70.5 µm square) is under 10 % of budget.

**Not included yet:** routing and spacing overhead, head enclosure, the
transistors, the tail devices, the G54 bypass capacitor, and the N-segment
ladder projection. So this is a lower bound and is *not* the S7 headline.

---

## 5. (4f) The corner question — structure established, sweep not run

### 5.1 The structural finding, and it is the important one

**SKY130 carries a passive corner axis that is completely independent of the
MOS one, and all five MOS corners hold the passives at typical.**

```
.lib tt / ss / ff / sf / fs   ->  all include res_typical__cap_typical
```

So **every corner number this project has ever published held `rs`, `cs` and
`rl` at their typical process values** — not because that was decided, but
because the MOS corner names do not touch the passives. This is asserted by a
test now rather than stated in prose.

The library provides the **full 5 × 5 cross product** as named sections:

```
tt ss ff sf fs        MOS corner, passives typical
ll hh hl lh           passives varied, MOS typical  (note: no `tt_` prefix)
ss_ll ... fs_lh       every remaining combination
```

**So S9's 45 corners become 225, not the 135 a three-passive-corner guess
would give.** `lib_section(mos, passive)` owns the naming, including the trap
that `tt` + a passive corner drops the `tt` prefix entirely.

### 5.2 How much the passives actually move

Measured, not read:

| | typical | ll | lh | hh | hl |
|---|---|---|---|---|---|
| `res_high_po` | — | **−12.5 %** | −12.5 % | **+12.5 %** | +12.5 % |
| MIM `cs` | — | −11.7 % | **+12.9 %** | +12.1 % | **−12.4 %** |

**The MIM capacitance depends on BOTH letters, and the second one is not the
capacitor.** `camimc` follows the capacitor letter as expected, but `tol_m3` —
the metal width tolerance, which sets the plate *size* — follows the
**resistor** letter, because it is the same metal layer the resistor's
interconnect is drawn in. And the magnitudes are not symmetric: mixed corners
carry ±0.065 µm against matched ones' ±0.0455 µm.

Consequence: `hh` and `lh` both have "cap_high" and differ by **0.7 %** in
capacitance. Treating the two letters as independent is wrong.

### 5.3 What this implies for f_z — arithmetic, not yet a measurement

With `Rs` at ±12.5 % and `Cs` at −11.7/+12.9 %, and `f_z = 1/(2π·Rs·Cs)`:

```
worst-case f_z spread   ~1.29x  =  ~0.37 octaves
```

against the **0.12 octaves** of centring slack. **That is ~3× the slack**,
which is the arithmetic 4e flagged, and it points the same way: the passives
alone could plausibly eliminate design 432.

**This is a prediction from component spreads, not a measured f_z movement.**
It is written here *before* the sweep as a pre-registration anchor, and it must
be confirmed or refuted by running §6's experiments. It would be wrong to
report it as a result.

### 5.4 Whether the 3-corner screen survives — NOT ANSWERED

G47's "3 corners are worth 98.7 % of 45" was measured on MOS-only evidence, and
the resistor's temperature coefficient is where the risk sits: **the poly body
TC is +514 ppm/°C and the head TC is −430 ppm/°C**, so they oppose, and *which
one dominates depends on the geometry `to_geometry` picks*. "The poly
resistor's tempco" is therefore not a single number. Whether that cancels
against `gm`'s drift in `k = 1 + (gm + gmbs)·Rs/2` — 4e's question — cannot be
answered from the model card and needs the sweep.

**The screen recommendation is deliberately not made here.** Making it without
the cross-product data is exactly what G46 and G47 warn against.

---

## 6. Open, in priority order

1. **4d — the regression gate.** Swap real passives in at nominal and confirm
   they reproduce the ideal-R/C results within the measured accuracy, on a
   handful of designs including 432. **Nothing downstream is trustworthy until
   this passes**, because without it a later change cannot be attributed to
   variation rather than to the swap.
2. **4e — f_z movement in octaves**, process and temperature decomposed, with
   the `k`-cancellation prediction pre-registered before the run.
3. **4f — the cross-product sweep** on a subset, then re-test G47's 98.7 %
   claim with passives varying, then recommend a screen set.
4. **4g — fold the `RL` parasitic into `CL_RANGE.md`** and say whether `cl_lo`
   must rise from 13.64 fF. Derive the MIM bottom plate the G51 way. Check
   `|Z(2.5 GHz)| / R_dc` for the chosen geometries.
5. **4h — the real S7 budget**, including routing overhead and the N-segment
   ladder projection.
6. **Trim `parameters/typical.spice` and `invariant.spice` out of the extended
   library** and re-verify — the likely 7.3× parse-cost fix (§3.2).

---

## 7. (4j) What is explicitly NOT being done

- **Mismatch.** `Rs` and `RL` mismatch between the two halves creates offset
  and common-mode-to-differential conversion. Every model in this document runs
  at `mc_mm_switch = 0`, i.e. **mismatch is switched off**, and every number
  here is a nominal one. The PDK provides the machinery (`res_match`,
  `body_pelgrom`, `rend_mm`, and the MIM's `AGAUSS` term), so enabling it is a
  switch, not new modelling — but Monte Carlo over 1,890 designs × 25 corners
  is a large run and it is out of scope for now. **Cost to add:** roughly the
  per-design SPICE budget multiplied by the MC sample count; at G48's ~100 ms
  and 100 samples that is ~5 hours for a single corner.
- **Layout parasitics beyond the device models.** No tech LEF or magic techfile
  is installed (G51), so routing capacitance is derived from the PDK's own vpp
  cap models rather than extracted.
- **The fixed-width resistor families as the primary choice.** They are
  enumerated and included in the trimmed library, but `to_geometry` uses the
  generic family. If S4 ever binds, the fixed-width family is the honest device
  to measure linearity on (trap 3).
- **`res_generic_nd/pd` and `res_iso_pw`.** Enumerated, not characterised.

---

## 8. New gotchas

**G56** — `mult` and `mf` are mismatch parameters, not device multipliers.
**G57** — `w` is inert on the fixed-width resistor families.
**G58** — the passive corner axis is orthogonal to the MOS one, and the MIM
capacitance depends on both letters of it.

Full text in `HANDOFF.md` §9.
