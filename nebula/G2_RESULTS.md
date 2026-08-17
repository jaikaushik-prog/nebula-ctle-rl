# G2_RESULTS.md — the loop is closed

**Session 21, 2026-08-17.** Gate **G2**, due 20 Aug:

> One full evaluation end-to-end: params → ngspice → fit → eye → scalar reward.
> No RL yet. **Wall-clock cost of each fidelity tier measured.**

**PASSED.** One parameter vector produces a drawn SKY130 schematic that meets
**every one of S3–S8 at TT**, with no mock anywhere in the path.

| | |
|---|---|
| The fit | `nebula/link/fit.py` (new) |
| The bridge | `nebula/link/bridge.py` (new) |
| The experiment | `nebula/experiments/exp_g2_closed_loop.py` (new) |
| Logged data | `g2_closed_loop_run.jsonl` (tracked, G49) |
| Tests | `test_link_fit.py` (30), `test_link_bridge.py`, `test_ac_sweep` additions in `test_sky130_runner.py` |
| One command | `python -m nebula.experiments.exp_g2_closed_loop --example` |

---

## 0. What a reader in a hurry needs

1. **The gate is passed on one design and the whole spec table clears.** Peaking
   **9.667 dB at 2.188 GHz** (S3), HD3 **−61.10 dBc** (S4), noise
   **0.290 mV_rms** (S5), power **5.289 mW** (S6), passive area
   **0.001092 mm²** (S7), eye **758.1 mV × 0.875 UI** (S8). §5 prints it end
   to end.

2. **"The link layer is a mock end to end" overstated the gap.** Most of the
   chain was built and tested. Two things were genuinely missing, and both were
   structural: **nothing in the repo had ever constructed a `DeviceResult`**
   (only `device/mock.py` did), and **the AC sweep was measured and thrown
   away** — only four `meas` scalars were kept, and a pole-zero fit cannot be
   made to four numbers.

3. **The first thing the closed loop revealed is that compression, not the eye,
   is binding.** Over 300 samples of the approved box: 92 % fit, **8.7 % meet
   S3**, and **61 % of fitted designs are rejected because the small-signal
   model no longer applies at the link's own drive level.** The median design
   overshoots its measured linear limit by **1.29×**.

4. **S8 is confirmed non-binding, now by measurement through real silicon.**
   Of the designs whose small-signal model holds, **76 % meet S8** (82 of 108).
   `CHANNEL_MODEL.md` §5 predicted this from a pulse response alone — *"S8
   vertical is not binding and never has been"* — and the end-to-end path now
   agrees by an independent route.

5. **A full-fidelity evaluation costs 0.279 s**, including the HD3 transient,
   and the link half adds **0.049 s with no simulator call at all**. Before
   session 19a's library trim, an AC-only evaluation cost 2.887 s.

6. **S8 is wired into the reward as `V2_SPECS`, and `V1_SPECS` is untouched** —
   so the +8.950669 ceiling and every published reward number still reproduce.

---

## 1. What was actually missing

The link layer was never fake in the sense G16 suggested. `link/channel.py`,
`link/tx.py`, `link/cursors.py` and `link/calibration.py` were all real,
tested, and had already produced published results. What did not exist:

| Gap | Fix |
|---|---|
| **No `DeviceResult` was ever built** from a real run. `sky130_runner` produced a `Sky130Point` and stopped; `device/mock.py` was the only constructor in the repo. So the real device layer and the real link layer had never been connected by anything. | `bridge.device_result_from_point()` |
| **The AC curve was discarded.** `.ac dec 50 1meg 100g` always ran, but only `g_dc`, `g_nyq`, `g_pk`/`f_pk` and `g_top` were parsed. | `run_point(ac_sweep=True)` dumps `vd_db`; 251 points |
| **No pole-zero fit existed.** `curve_fit` appeared nowhere in the repo outside a comment in the mock. | `link/fit.py` |
| **No eye WIDTH.** `CursorSet` gave height only. | `cursors.eye_opening_vs_phase()` |
| **S4 and S7 were unmeasured**, and the contract requires every numeric field on success (§8 rule 1). | `run_point(hd3=True)` transient+FFT; `PassiveGeometry.area_mm2` |

`ac_sweep` and `hd3` both default **OFF**, so the netlist stays byte-identical
to the one every published number came from.
`test_ac_sweep_capture_changes_no_measured_value` compares 17 parsed fields
across both settings at **rel = 0, abs = 0**.

---

## 2. The pole-zero fit (§5.3b)

`|H(f)| = g_dc·|1 + jf/f_z| / (|1 + jf/f_p1|·|1 + jf/f_p2|)`, fitted as
**decibels against log-frequency** because that is the unit the 0.5 dB
rejection gate is written in — fitting in linear magnitude would minimise a
different quantity from the one the gate reads. Parameters are carried as
`log10`, which removes the positivity constraint rather than penalising it.

**Exactness.** On noiseless synthetic responses the fit recovers the generating
parameters to **machine precision** (residual < 1e-9 dB), including a case
where the poles are supplied in the wrong order and one with a nearly
cancelling pole-zero pair.

**The gate discriminates, in both directions.** It must, or it is a deleted
gate (G73):

| response | residual | verdict |
|---|---|---|
| resonance, Q = 2 / 5 / 12 | 3.17 / 4.25 / 4.88 dB | **rejected** |
| third pole above the band | 0.224 dB | accepted |
| real SKY130, drawn passives | 0.008–0.227 dB | accepted |

**The basin is probed, not assumed.** A four-parameter fit that only ever
starts from one place cannot tell a unique minimum from a lucky one, so
`fit_ctle` exposes `p0` and starts spanning **±2 decades** all converge to the
same parameters to 1e-6.

**The §5.3b cross-check is independent.** The fit never reads the device
layer's own `meas ac g_dc`; on three real designs the two agree to
**0.001–0.027 dB**.

**A docstring claim of mine was wrong and is recorded as such.** The initial
guess's reasoning said *"the peak sits between `f_z` and `f_p1`"*. False
whenever `f_p2` pulls the maximum upward: at `(1.9, 0.6, 2.4, 9.0) GHz` the
true peak is at **4.52 GHz, above `f_p1`**, and the guess returns `f_z` =
2.56 GHz against a true 0.6 GHz — a factor of 4. The fit converges anyway,
which is what the basin probe is for.

---

## 3. The fidelity tiers — G2's other half

Cumulative, because that is how they are bought: one ngspice invocation runs
`.op`, `.ac` and `.noise` whatever else is asked for.

| tier | min s | median s | increment | separable |
|---|---|---|---|---|
| `.op` + `.ac` + `.noise` | 0.1768 | 0.2274 | — | — |
| + AC curve dump | 0.2047 | 0.2452 | +0.0279 | yes |
| + `.dc` swing sweep | 0.2257 | 0.2867 | +0.0210 | yes |
| + HD3 transient + FFT | **0.2787** | 0.3488 | +0.0530 | yes |
| pole-zero fit | 0.0114 | | | *no simulator* |
| link eval (pulse → cursors → eye) | 0.0372 | | | *no simulator* |

**Total added by the three extra tiers: +0.1018 s, 1.58×.**

**Two methodological notes, because the first version of this table was
wrong.**

*G71 fired on my own measurement.* Run tier-by-tier with a per-tier warm-up,
the table came out with `.op+.ac+.noise` at 0.3841 s and `+ac_curve` at
0.3138 s — **a negative increment for strictly more work**, because whichever
tier goes first pays the process-level cache warming. The fix is the full
protocol: **interleaved, order re-shuffled every repeat**, 21 repeats.

*The minimum is the estimator, and that is a choice with a reason.* Process
launch and OS scheduling noise is strictly **additive and one-sided** —
nothing makes an ngspice run faster than the work it does — so the minimum
over repeats estimates that work while the median carries whatever contention
the machine had. Medians are reported beside it and the two **agree on every
ordering**. Read against the median alone, none of the increments is separable
from the p10–p90 spread; read against the minimum's own noise floor
(0.0182 s), all three are.

**Against the earlier estimate:** `s9_yield.py` recorded HD3 as *"needs
transient+FFT, ~4× the cost of AC+noise"* and G0 measured a 175× spread across
analyses. Measured here the transient adds **+0.053 s to a 0.226 s base, i.e.
1.23×**. The earlier figures were taken when library *parsing* dominated every
invocation; session 19a's 13× trim made the analyses themselves visible, and
the transient turns out to be cheap.

---

## 4. The funnel — 300 samples of the approved box

Latin hypercube over `rl/contract.ACTION_SPACE`, TT/27 °C, `cl_mid` =
32.63 fF, drawn passives and a real current-mirror tail, channel at **12 dB**
(the top of the derived family, the hardest member). 161 s total.

CTLE input: **534.7 mVpp long-run**, 201.0 mVpp at Nyquist.

| stage | count | of 300 | lost |
|---|---|---|---|
| proposed | 300 | 100.00 % | |
| simulated | 300 | 100.00 % | 0 |
| pole-zero fit held | 276 | 92.00 % | −24 |
| **S3 met** | 26 | 8.67 % | −250 |
| small-signal model still valid | 10 | 3.33 % | −16 |
| eye open | 10 | 3.33 % | 0 |
| **S8 met** | **10** | **3.33 %** | 0 |

**S3 and compression are not nested**, so the funnel alone would hide the
picture. Independent tallies:

| | count |
|---|---|
| S3 met | 26 |
| link evaluated (small-signal valid) | 108 |
| **rejected as compressing** | **168** |
| S8 met | 82 |
| **S3 and S8 both met** | **10** |

### 4.1 Compression is the binding constraint the bridge revealed

**168 of 276 fitted designs — 61 % — cannot be evaluated at all**, because the
predicted peak output excursion exceeds the device's own measured linear limit.
The distribution of `peak excursion / swing limit`:

    median 1.291    p10 0.531    p90 3.015    max 7.769

So the *median* design in the approved box overshoots its linear range by 29 %.

**This is not a new physical claim — it confirms one already on record by a
different route.** `CHANNEL_MODEL.md` §6 measured *"compression binds at 5 of
7 loss points, and 3 dB is 1.51×"* using convention C on a pulse response, and
HANDOFF §8 records the actionable item as being **S3's floor**. The bridge
reaches the same place from transistor-level silicon.

**The convention matters and is stated.** The swing checked is the pulse
response's own peak excursion, `2·Σ|h_k|` — G61's **convention C**, which
`CHANNEL_MODEL.md` §6 selects after measuring that the three conventions in
this repo disagree by **1.8×**. It needs no decision about which input level
pairs with which gain. It is also a **worst-case bound**: real PCIe traffic is
8b/10b coded and run-length limited, so the true peak excursion is smaller.

### 4.2 S8 is not binding, measured end to end

**82 of the 108 designs whose small-signal model holds meet S8 — 76 %.** And
all 10 designs that meet S3 *and* are valid also meet S8: the `eye_open` and
`s8_met` rows lose nobody.

`CHANNEL_MODEL.md` §5 predicted exactly this from a pulse response with no
transistors in it: *"S8's 100 mV vertical is met with the CTLE **attenuating**
by 13–15 dB … S8 vertical is not binding and never has been."* Two
independent paths, same conclusion.

### 4.3 The fit gate is real but not the story

24 of 300 (8 %) rejected. The surviving residuals run median **0.0388 dB**, p90
0.268, **max 0.4969** — i.e. the worst accepted design sits at 99.4 % of the
gate. The gate is binding at the tail and idle in the middle, which is what a
gate should look like.

---

## 5. One worked evaluation, end to end

`python -m nebula.experiments.exp_g2_closed_loop --example`

The design is **row i=110 of the funnel** — the largest eye among the ten that
met both S3 and S8. **Found by the search, not hand-picked from outside the
box**, which is what makes it evidence that the approved box contains designs
that close the loop.

**1. Parameters** (the RL action space)

    w_in    38.873 um      rs      697.71 ohm
    l_in     0.18762 um    cs        1.0134 pF
    i_bias   3.0787 mA     rl      653.11 ohm
    vcm_in   1.18384 V     nf_in        4  (fixed, G38)
                           cl      32.628 fF (context)

**2. The schematic** — drawn SKY130 devices. *This is the deliverable.*

    input pair   W=38.873 um  L=0.187622 um  nf=4
    tail         W=171 um  L=0.5 um  nf=8, current mirror 1:8
    Rs           res_high_po   w=10  l=20.69    m=1   (R error -0.01 %)
    Cs           cap_mim_m3_1  w=22.345 l=22.345 m=1  (C error -0.02 %)
    RL           res_high_po   w=10  l=19.285   m=1   (R error +0.00 %)
    passive area 1091.9 um^2 = 0.001092 mm^2

**3. Measured specs** — one ngspice call: `.op .ac .noise .dc .tran`

| spec | measured | required | |
|---|---|---|---|
| S3 peaking | **9.667 dB @ 2.1878 GHz** | 3–12 dB in 1.25–2.5 GHz | **PASS** |
| S3 Nyquist boost | +9.640 dB | > 0 (reading (b)) | **PASS** |
| S4 HD3 | **−61.10 dBc** @ 100 MHz, 100 mV pk | < −30 dBc | **PASS** |
| S5 input noise | **0.2897 mV_rms** | < 1.5 mV_rms | **PASS** |
| S6 power | **5.289 mW** (measured supply) | < 15 mW | **PASS** |
| S7 passive area | **0.001092 mm²** | < 0.05 mm² | **PASS** (2.2 %) |

**4. The pole-zero fit**

    g_dc     1.44692 V/V = +3.209 dB
    f_zero   0.2689 GHz
    f_pole1  0.9489 GHz     (k = f_p1/f_z = 3.5281)
    f_pole2  5.6067 GHz
    residual 0.0222 dB      (gate: reject above 0.5 dB)

**5. The eye** — channel + TX de-emphasis + CTLE + ideal 1-tap DFE

| | measured | required | |
|---|---|---|---|
| S8 eye height | **758.11 mV** | > 100 mV | **PASS** |
| S8 eye width | **0.8750 UI** | > 0.4 UI | **PASS** |
| gain at Nyquist | +12.838 dB | | |
| DFE tap | −0.1895 | | |
| peak swing | 1577.2 mVpp against a 1961.9 mVpp limit | | 80 % |
| SNR at slicer | 298.5 = +49.5 dB | | **device noise only** |

**All of S3–S8 met at TT.** S9 (corners) is not claimed — see §7.

---

## 6. S8 in the reward

`reward_v1.V2_SPECS` = `V1_SPECS` **plus** `S8_eye_h` and `S8_eye_w`, with
tolerances of **50 mV** and **0.2 UI** — half of each S8 floor, by the same
rule the other tolerances use.

**`V1_SPECS` is untouched, and that is deliberate.** Adding two rows changes
`len(specs)`, which changes the feasibility bonus `B = N + 1`, which changes
**every reward number this project has published** — including the +8.950669
ceiling (G74), which is a property of the spec set. `BASELINES.md` §7f:
*"do not touch the evaluator, the reward tolerances, the box or the geometry
mapping. If any of those change, every baseline must be re-run."* So v2 is
opt-in until a human decides to re-run them. 88 reward tests pass unchanged.

`margins()` **omits** the S8 rows when no link result is given, rather than
defaulting them — so asking for `V2_SPECS` without an eye raises a `KeyError`
instead of scoring a missing eye as satisfied or as just-failed.

**S8 costs no extra simulation.** The eye is computed from the AC curve the
same invocation already produced: +0.037 s, no simulator.

---

## 7. What this does NOT license

* **S9 is not claimed.** Everything here is **TT/27 °C, nominal VDD, one
  load** (`cl_mid`). The corner axis is the next gate (G4), not this one.
* **The BER is a bound, not a link BER.** `Q((eye/2)/σ)` at the worst-case ISI
  pattern with **device noise only** — no reference-clock jitter, no crosstalk,
  no TX noise, and the residual ISI treated as a deterministic subtraction
  rather than a distribution. At the worked example's SNR of 298 it underflows
  double precision and reports 0.0, which means "below ~1e-308", **not**
  "verified error-free". Read the SNR.
* **The 1e-15 bathtub is not delivered.** `python_models/statistical_eye.py` is
  the engine for it and its NRZ path **deliberately raises
  `NotImplementedError`** rather than reporting a BER 0.75× the truth from
  four-level mathematics (`NRZ_RETARGET_AUDIT.md` groups A–E). Wiring it in is
  the next step and is scoped: ~6 items, all inside that one file, all with
  hand-computable NRZ values. Groups C and D are the time-domain CDR/FFE chain
  and S2 does not use them.
* **The eye width is a zero-height noiseless width** — the contiguous phase
  span over which an ideal 1-tap DFE leaves the eye open, quantised at
  **1/64 UI = 0.0156 UI**. A strict upper bound on the width at any finite BER.
* **S7 is a lower bound**: drawn passive device area only. No head enclosure,
  routing or guard ring (`PASSIVES.md` §4.5's 4h budget), and no MOSFET area.
* **The channel is a construction**, not a measurement, and contains no
  reflections — which push the 12 dB channel-only eye below S8's floor
  (`CHANNEL_MODEL.md` §8). Every ISI number is a lower bound.

---

## 8. Open, in the order a next session should take it

1. **The NRZ retarget of the BER path**, to replace the bound with a real
   bathtub. Scoped above; the fence is there precisely so this is done group by
   group with a hand-computed `BER = Q(1/σ)` test, never wholesale.
2. **The corner axis (G4).** The bridge takes a `DeviceResult` per corner
   already; nothing structural is missing. `run_point` costs 0.279 s at full
   fidelity, so 3 corners × 2 loads is 1.7 s per design.
3. **Compression is now the top open DESIGN question**, and it is a human's
   call, not an agent's. 61 % of the box is unevaluable at the PCIe input
   level. Three routes, all already on record: reach below S3's 3 dB floor;
   declare the low-loss end of the channel family out of scope; or accept that
   the CTLE must attenuate and re-derive the box's `rl` range downward.
   `CHANNEL_MODEL.md` §6 and HANDOFF §8 both already point here.
4. **Re-run the funnel with `V2_SPECS`** once a human accepts re-running the
   baselines, and report the reward distribution including S8.
