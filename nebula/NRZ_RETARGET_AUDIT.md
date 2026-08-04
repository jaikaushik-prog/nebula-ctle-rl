# NRZ retarget audit — every 4-level assumption in `python_models/`

**Status:** audit complete. **3 of 24 items fixed (2026-08-04); 21 remain.**
This is the checklist for Workstream C (CLAUDEwa.md §4.3). Audit date:
2026-08-03.

## Progress

| Item | What | Status |
|---|---|---|
| E5 | `crossing_jitter_ui`'s `sqrt(5.0·Σg²)` | **DONE** — now `sqrt(mod.mean_square·Σg²)`. Was overestimating NRZ jitter by exactly √5 = 2.2361× and would have declared a lockable CDR infeasible. A wrong result, not a slow one, which is why it went first. |
| F2 | `CTLE.from_peaking`'s absolute 28/56 GHz pole defaults | **DONE** — `f_pole1`/`f_pole2` are now REQUIRED. There is no correct default because the right poles depend on fbaud, so there is no default. |
| E3 | `adc_vref = 4.0` | **MOOT, no change.** S2's topology is CTLE + slicer + 1-tap DFE — there is no ADC in it. `nebula/link/` imports neither `link_sim` nor `adc_model`. Pinned by tests in `tests/test_modulation.py::TestAdcVrefIsMootForS2` so the conclusion stays checkable. |

**Infrastructure landed with them:** `python_models/modulation.py` — the
`Modulation` object this document's "rule that governs the whole retarget"
calls for, with every alphabet-dependent constant DERIVED from `levels` rather
than chosen. `PAM4` is the default everywhere.

**The BER path is FENCED, not retargeted.** `StatisticalEye` accepts
`modulation="nrz"` but **raises `NotImplementedError`** from `ber_at_phase`,
`analyse` and `clip_probability`, because groups A–E below are still
four-level. Running anyway would report a BER 0.75× the truth — optimistic,
finite, plausible. Remove the fence group by group as the work below lands,
never wholesale.

**Next:** step 2 of the recommended order — groups A + B, with the
hand-computed `BER == Q(1/σ)` test.

---

The framework is a validated 112G **PAM-4** receiver model. Nebula needs
5 Gbps **NRZ**. CLAUDEwa.md §4.3 names five things to audit; this audit found
**24**. The five named ones are marked ★.

## The rule that governs the whole retarget

> **Keep the PAM-4 path working behind a flag. Do not fork the repo.**
> — CLAUDEwa.md §4.3
>
> **The 65 existing tests stay green.** — CLAUDEwa.md §8 rule 3

So the shape of the fix is: a `modulation: Literal["pam4","nrz"] = "pam4"`
field on `LinkConfig`, a small `Modulation` object carrying
`(levels, thresholds, rms, bits_per_symbol, max_level)`, and every constant
below read from it instead of from a module-level PAM-4 literal. Defaulting to
`"pam4"` is what keeps the existing tests green without touching them. (That baseline was 65 tests
when this audit was written; it is 92 in `tests/` as of 2026-08-04.)

## Risk key

- **SILENT** — wrong by a finite factor, no error, plausible-looking output.
  These are the dangerous ones; each needs a test with a hand-computed NRZ
  value, not just a code change.
- **LOUD** — crashes, asserts, or fails to converge. Annoying, not dangerous.
- **PERF** — correct but wasteful.

---

## A. Symbol alphabet

| # | Location | Assumption | NRZ needs | Risk |
|---|---|---|---|---|
| A1 | `statistical_eye.py:44-45` | `PAM4_LEVELS = [-3,-1,1,3]`, `PAM4_THRESH = [-2,0,2]` | `[-1,1]`, `[0]` | SILENT |
| A2 | `equalizers.py:26-27` | same two constants, **duplicated** | single source of truth | SILENT |
| A3 | `ml_equalizer.py:38` | torch copy of the levels | out of scope (unaudited module) | — |

A2 is worth fixing first: two copies of the alphabet is how a half-finished
retarget produces a slicer and a BER engine that disagree.

## B. BER mathematics — the highest-risk group

| # | Location | Assumption | NRZ needs | Risk |
|---|---|---|---|---|
| B1 ★ | `statistical_eye.py:240` | `ber = 0.5 * total / 4.0` | `ber = total / 2.0` | SILENT |
| B2 | `statistical_eye.py:232-239` | loops `PAM4_LEVELS` × `PAM4_THRESH` | 2 levels × 1 threshold | SILENT |
| B3 | `statistical_eye.py:236` | adjacency test `abs(a0 - thr) > 1.01` | works for NRZ **by luck** — level-to-threshold distance is 1.0 in both alphabets. Do not leave it as a bare literal. | SILENT |
| B4 | `statistical_eye.py:86` | `nxt += 0.25 * pmf` — the 1/M symbol probability in `isi_pmf` | `0.5` | SILENT |
| B5 | `statistical_eye.py:71` | `span = 3.0 * Σ|taps|` — 3.0 is max\|a\| for PAM-4 | `1.0`; leaving 3.0 is safe but triples the grid | PERF |
| B6 | `channel.py:291` | `ber_from_snr_pam4()` — Gray-coded PAM-4 AWGN theory | NRZ counterpart `Q(√(2·SNR))` | LOUD (wrong curve is visibly wrong) |

### B1 in detail — the ★ "0.75·Q" prefactor

The `0.5` is (1 bit error per crossing) ÷ (2 bits per symbol). The `/4.0` is
averaging over 4 equiprobable levels. For an ISI-free PAM-4 eye the sum runs
over 6 adjacent level/threshold pairs (2 outer × 1 + 2 inner × 2), giving the
documented closed form `0.75·Q(1/σ)`.

For NRZ: 2 levels, 1 threshold, 1 adjacent pair each, 1 bit per symbol. The
sum is `2·Q(1/σ)` and the correct prefactor is **`1.0`**, i.e. `BER = Q(1/σ)`.

Leaving the PAM-4 form in place reports BER **0.75× the truth** — optimistic,
finite, and completely plausible. This is the single most dangerous line in
the retarget.

## C. Slicers

| # | Location | Assumption | Risk |
|---|---|---|---|
| C1 ★ | `rx_frontend.py:126` | `_slice_pam4()` — 3-way threshold ladder | SILENT |
| C2 | `rx_frontend.py:259, 271` | call sites in `CDRSampler` | SILENT |
| C3 ★ | `equalizers.py:29` | `hard_slicer_pam4()` | SILENT |
| C4 | `equalizers.py:142, 211, 330, 407` | call sites in FFE/DFE LMS, MLSE | SILENT |
| C5 | `rx_frontend.py:272` | MM PD gates updates on `abs(d_pd) == 3.0` — outer-level transition pairs only | LOUD |

**C5 is a good failure.** NRZ symbols are ±1, so `abs(d) == 3.0` is never
true, the Mueller-Müller phase detector never updates, and the CDR simply
never locks. That is a visible failure rather than a silent bias — but it does
mean the `mm_postffe` architecture needs a new gating rule for NRZ (there is
no outer level to gate on; the natural NRZ analogue is to gate on a data
transition, `d_k != d_{k-1}`).

## D. Bit mapping and BER counting

| # | Location | Assumption | Risk |
|---|---|---|---|
| D1 ★ | `pam4_chain.py:107-126` | `gray_encode` / `gray_decode`, IEEE 802.3 2-bit dibit map | LOUD |
| D2 | `pam4_chain.py:119` | `assert len(bits) % 2 == 0` | LOUD |
| D3 | `link_sim.py:219` | `rx_bits = gray_decode(decisions[k0:])` | LOUD |
| D4 | link BER accounting | bits = 2 × symbols for PAM-4, 1 × symbols for NRZ | SILENT |

For NRZ, Gray coding is the identity map (1 bit per symbol), so the cleanest
retarget is a pass-through encoder rather than a special case at every call
site. D4 is the silent one: a BER denominator that still assumes 2 bits per
symbol reports **half** the true BER.

## E. Amplitude and scale constants

| # | Location | Assumption | NRZ needs | Risk |
|---|---|---|---|---|
| E1 ★ | `rx_frontend.py:97` | `PAM4_RMS = sqrt(5)` — rms of equiprobable {±1,±3} | `1.0` | SILENT |
| E2 | `rx_frontend.py:100-107` | `agc_scale()` normalises rms to `PAM4_RMS` | as E1 | SILENT |
| E3 | `link_sim.py:79` | `adc_vref = 4.0` "full scale in symbol units" — sized for ±3 | ~1.5-2.0 | SILENT |
| E4 | `statistical_eye.py:280` | `clip_probability(vref=4.0)` | as E3 | SILENT |
| E5 | `statistical_eye.py:276` | `sigma_e = sqrt(5.0 · Σ g²)` — the 5.0 is E[a²] for PAM-4 | `1.0` | SILENT |
| E6 | `statistical_eye.py:376` | `syms = rng.choice(PAM4_LEVELS, 4000)` in the noise calibration | NRZ alphabet | SILENT |

**E1/E2** is the one CLAUDEwa.md §4.3 names. Leaving `sqrt(5)` in the AGC
scales every downstream amplitude by 2.24×, which then propagates into eye
height, the ADC operating point, and the mV calibration.

**E3** is quieter but real: an ADC referenced to ±4 carrying an NRZ signal at
±1 wastes two bits of range, so quantisation noise comes out ~4× too high and
the design looks worse than it is.

**E5** overestimates crossing jitter by √5 = 2.24×, which would falsely report
the CDR as infeasible (`crossing_jitter_ui` > 0.45 UI) for perfectly good NRZ
configurations.

## F. Frequency defaults — CLAUDEwa.md §12's named trap

| # | Location | Assumption | NRZ/5 Gbps needs | Risk |
|---|---|---|---|---|
| F1 | `link_sim.py:55` | `fbaud = 56e9` | `5e9` | LOUD |
| F2 | `rx_frontend.py:50-51` | `CTLE.from_peaking(f_pole1=28e9, f_pole2=56e9)` — **absolute** 112G defaults | poles near 1-6 GHz | SILENT |
| F3 | `link_sim.py:74-75` | `ctle_fp1_rel=0.5`, `ctle_fp2_rel=1.0` — relative, so these track `fbaud` correctly | no change | — |
| F4 | `link_sim.py:96-98` | `ffe_pre=3, ffe_post=17, dfe_taps=5` | S2 fixes a **1-tap DFE** and no RX FFE | SILENT |
| F5 | `statistical_eye.py:133` | `StatisticalEye(n_dfe=5)` default | `n_dfe=1` | SILENT |
| F6 | `statistical_eye.py:134` | `snr_mmse_db = 26.0` | re-derive for the nebula link budget | SILENT |

**F2 is the trap in its purest form.** `from_peaking()` is callable without
pole arguments and silently places a 5 Gbps CTLE's poles at 28/56 GHz. The
nebula link layer must always construct `CTLE` from the fitted device poles,
never via `from_peaking` defaults — which is why `nebula/link/mock.py` builds
its response from `(g_dc, f_zero, f_pole1, f_pole2)` and nothing else.

**F4/F5 matter for honesty, not just correctness.** S2 fixes the topology at
one CTLE stage plus a 1-tap DFE. Reporting an eye that a 21-tap FFE and a
5-tap DFE opened would not be a result about the CTLE the RL loop sized.

## G. Secondary modules

| # | Location | Assumption | Risk |
|---|---|---|---|
| G1 | `equalizers.py:431-435` | `MLSE(n_levels=4)`; `linspace(-1,1,2)` = `[-1,1]` for `n_levels=2` — **already correct for NRZ** | — |
| G2 | `equalizers.py:511-530` | `AdaptiveThreshold` — 4 level estimates, 3 thresholds, hard-coded index arithmetic | LOUD |
| G3 | `cdr.py:270, 345-398` | standalone CDR study models, PAM-4 throughout. Not on the link path (HANDOFF §2) | out of scope |
| G4 | `ml_equalizer.py`, `optical_dsp.py` | PAM-4 throughout; both unaudited/unintegrated | out of scope |

---

## Recommended order of work

1. **`Modulation` object + `modulation` flag on `LinkConfig`,** defaulting to
   `"pam4"`. **DONE 2026-08-04** — `python_models/modulation.py`. Nothing else
   changed with it; the whole existing suite must still pass. This is
   the step that makes the rest non-forking.
2. **Group A + B** (alphabet + BER maths) with a new NRZ closed-form test
   asserting `BER == Q(1/σ)` against a hand-computed value — the direct
   analogue of the existing PAM-4 `0.75·Q` check in
   `test_statistical_eye.py`.
3. **Group E** (amplitude constants), with a test that AGC on an ideal NRZ
   waveform yields unity gain.
4. **Group C + D** (slicers, bit mapping), including a new MM PD gating rule
   for NRZ (C5).
5. **Group F** (frequency and DSP defaults) — mechanical once 1-4 are done.
6. **Group G2** if `AdaptiveThreshold` is needed; it is not on the S2 path.

## What this audit does not do

It does not tell you whether the retargeted engine is *right*. Every item
above is a place where the code is knowably PAM-4-specific. The cross-check
that the NRZ path actually works is the existing cross-validation test between
the statistical and waveform engines (`test_statistical_eye.py`), re-run in
NRZ mode — that test compares two independent implementations and is the only
thing in the repo that would catch a mistake this audit missed.
