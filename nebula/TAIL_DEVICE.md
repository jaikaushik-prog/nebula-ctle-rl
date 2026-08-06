# TAIL_DEVICE.md — the tail transistor, measured

**Session 13, 2026-08-06.** Closes HANDOFF §8's top open item, promoted on
2026-08-05 and open since the project began.

> Every simulation this project has ever run uses **two ideal current sinks**
> for the tail. An ideal sink delivers exactly `I_tail` at every corner: it does
> not lose current at SS/125 °C, does not gain it at FF/0 °C, and does not fall
> out of saturation when the rail drops 5 %. That single assumption is what
> makes the whole S9 result an **optimistic bound** (G47), and it also blocks
> three of the nine box dimensions.

**Read §0 before quoting anything from this file.**

Everything here is reproducible from `nebula/experiments/tail_device_data.csv`
(261 rows, tracked per G49) with **no simulator**:

```
python -m nebula.experiments.tail_device --report     # the sweep analysis
python -m nebula.experiments.tail_device --bounds     # §6, derived from the CSV
```

---

## 0. What is still assumed, stated first

1. **`I_ref` is an ideal current source.** Generating it is a bandgap or a
   constant-gm bias cell — a circuit S2 does not name. Modelling it badly would
   be worse than declaring it. **One justified ideal element is defensible;
   four are not.** Everything else in the tail is now a device.
2. **Matching is not modelled.** Longer `L` improves mirror matching as well as
   output resistance, and §6 only measures the second. A Monte-Carlo mismatch
   study is not open in this project; SKY130 ships mismatch corner files
   (`sky130_fd_pr__nfet_01v8__mismatch.corner.spice`, already included by the
   trimmed library) so it is available, not done.
3. **The sizing rule in §3 is a design DECISION, not a measurement.** It is
   stated, and it is the thing a reader is most likely to want to reject.
   `common/params.py` is untouched (CLAUDEwa §8 rule 6).
4. **A residual ~0.4 % of runs still return `-nan(ind)`** and are counted as
   hard failures rather than silently dropped. See G54 and §7.

---

## 1. The topology, and why a mirror rather than a fixed gate bias

An ideal reference current is forced into a diode-connected `nfet_01v8`, whose
gate drives **one tail device per side**:

```
        vdd                     vdd            vdd
         |                       |              |
       Iref (ideal)             RLp            RLn
         |                       |              |
      +--+--- nbias ---+      outp            outn
      |               |         |              |
   [XMR] gate=drain   |      [XM1]          [XM2]     input pair
      |               |         |              |
     gnd              |        s1 --Rs||Cs--- s2
                      |         |              |
                      +------[XMT1]         [XMT2]     tail, W_tail each
                                |              |
                               gnd            gnd
        Cbyp: nbias to gnd, 10 pF (G54, §4)
```

**Why a mirror and not a fixed gate voltage.** A fixed `Vgs` holds while `vth`
moves with process and temperature, so the delivered current would swing far
more than silicon does — it would **exaggerate** the corner spread and make the
tail look like a worse problem than it is. A mirror tracks, because the
reference device's `vth` moves the same way as the tail's and the gate voltage
follows it.

**Why TWO tail devices.** S2 degenerates the pair with `Rs`/`Cs` *between the
two sources*. A single shared tail would put a low impedance across that
network and short it out. This was already true of the ideal sinks; the mirror
keeps it. **It is not a bookkeeping detail — it is why the tail's noise is not
common-mode.** See §4.

**Why the reference is N matched unit fingers.** `nf_ref = nf_tail / N`, so the
reference and each tail finger have the *same width*. G38 measured a ±10 %
non-monotonic effect of finger width on `gm`; with mismatched fingers that
lands directly on the mirror ratio. Measured at `W_tail = 100 µm, L = 0.5 µm,
N = 8`:

| `nf_tail` | `nf_ref` | finger widths | realised ratio |
|---|---|---|---|
| 8 | 1 | 12.5 / 12.5 µm | **7.38** |
| 8 | 8 | 12.5 / 1.56 µm | 9.55 |

The matched case's error is *physics* (§2). The mismatched case lands nearer
8.0 by cancelling one error against another, which is not a design.

---

## 2. The three identities, and the one that is the point

`--identity`, at session 9c's corrected reference point (`W = 40, nf = 4,
I_tail = 1.5 mA/side, VCM = 1.25, VDD = 1.8`). Each check can **fail**, and
`nebula/tests/test_tail.py` breaks each one by hand and requires it to go red
(CLAUDEwa §8 rule 10).

| check | measured | verdict |
|---|---|---|
| `I_tail` delivered vs requested | 1.384 mA vs 1.500 mA | PASS (−7.72 %) |
| **`vds_tail == v(source)`** | 0.353821 vs 0.353821 V | PASS, **delta 0** |
| `v(source) == VCM − Vgs_in` | 0.353821 vs 0.353821 V | PASS, delta −5.6e-17 |

**The middle row is the whole reason this experiment exists.** The tail's drain
*is* the input pair's source node, and that node is `VCM − Vgs(I_tail, W_in,
L_in)`. So the tail's headroom requirement

```
        VCM  −  Vgs(I_tail, W_in, L_in)   >   vdsat_tail(I_tail, W_tail, L_tail)
```

**ties VCM, W_in, L_in, i_bias and the tail geometry into a single
inequality.** Nothing else in the spec table couples five box coordinates.
`s9_yield.py` now scores it as a spec row named `tail_saturation`.

### What fitting the tail changed at TT

| | ideal sinks | current mirror | |
|---|---|---|---|
| `I_tail` | 1.5000 mA | 1.3841 mA | **−7.72 %** |
| `v(s1)` | +0.3435 V | +0.3538 V | +10.4 mV (less current ⇒ less `Vgs`) |
| `gm` | 12.623 mS | 12.238 mS | −3.0 % |
| peaking | 4.500 dB | 4.183 dB | −0.32 dB |
| S5 noise | 0.2750 mV | 0.4425 mV | **×1.61** |
| power | 5.738 mW requested | **5.320 mW measured** | −7.3 % |

### The −7.7 % is physics, not a bug

The reference device sits at `vds = vgs ≈ 1.0 V` and the tail at
`v(source) ≈ 0.34 V`. Channel-length modulation gives the reference more current
per micron than the tail, so a geometric ratio of 8 delivers about 7.4. It
moves with corner, which is exactly the behaviour an ideal sink could not have:

| corner | median mirror error | over |
|---|---|---|
| `tt / 1.00 / 27 °C` | **−6.61 %** | 87 geometries |
| `ss / 0.95 / 125 °C` | **−8.09 %** | 87 |
| `ff / 1.05 / 0 °C` | **−5.41 %** | 86 |

**Consequence for S6:** power is now billed on the **measured** supply current
(`print i(vdd)`), which carries both the reference branch (+1/2N = +6.25 % of
the tail current) and the mirror's shortfall. With ideal sinks the measured and
requested numbers are identical by construction, so this change costs nothing
in the legacy path.

---

## 3. The sizing rule

`--sweep`: 261 runs, 38 s at 8 workers. Three currents × three lengths × nine
widths × three corners, plus an `nf` probe.

### Headroom against width, at `I_side` = 1.5 mA, `L` = 0.5 µm

`margin` is `vds_tail − vdsat_tail`; **negative means the tail is in triode.**

| `W_tail` µm | TT: vdsat / margin | SS/0.95/125 °C: vdsat / margin | FF/1.05/0 °C: vdsat / margin |
|---|---|---|---|
| 25.0 | 0.3544 / **+0.0064** | 0.4985 / **−0.1417** | 0.3064 / +0.0965 |
| 38.6 | 0.2905 / +0.0661 | 0.4042 / **−0.0580** | 0.2534 / +0.1476 |
| 59.5 | 0.2373 / +0.1180 | 0.3271 / +0.0129 | 0.2081 / +0.1926 |
| 91.7 | 0.1954 / +0.1586 | 0.2641 / +0.0718 | 0.1720 / +0.2280 |
| 141.4 | 0.1626 / +0.1906 | 0.2164 / +0.1171 | 0.1435 / +0.2560 |
| 218.1 | 0.1365 / +0.2160 | 0.1798 / +0.1521 | 0.1207 / +0.2783 |
| 336.4 | 0.1155 / +0.2364 | 0.1512 / +0.1794 | 0.1024 / +0.2961 |
| 518.7 | 0.0985 / +0.2529 | 0.1287 / +0.2011 | 0.0757* / +0.3221 |
| 800.0 | 0.0849 / +0.2662 | 0.1107 / +0.2183 | 0.0757 / +0.3221 |

\* one FF row lost to G54's NaN.

**The worst corner for the tail is `ss / 0.95 / 125 °C`, and it is not close.**
That is the *expected* direction here and worth contrasting with G46: tail
saturation is a **one-sided** constraint, so it does have a single worst corner,
unlike S3, whose two edges sit on opposite sides of the process axis.

### Width per amp for `vdsat_tail` = 0.20 V

The number in each cell is **thousands of microns of width per amp of side
current**. It is quoted this way round because what a caller does with it is
multiply by a current to get a width.

| L, corner | 0.75 mA | 1.50 mA | 3.00 mA | spread |
|---|---|---|---|---|
| 0.5 µm, FF/1.05/0 | 47.2k | 43.7k | 40.9k | 1.15× |
| **0.5 µm, TT** | 63.4k | 58.3k | 55.4k | 1.14× |
| **0.5 µm, SS/0.95/125** | 124.0k | **111.2k** | 105.4k | **1.18×** |
| 0.75 µm, SS/0.95/125 | 189.7k | 181.4k | 171.8k | 1.10× |
| 1.0 µm, SS/0.95/125 | 262.0k | 252.4k | 245.7k | 1.07× |

**It really is a current density.** The width per amp drifts by only 1.07–1.18×
across a **4× change in current**, so `w_tail` is derivable from `i_bias`
rather than needing to be searched independently. That is the finding that lets
the action space stay at nine dimensions.

**The corner spread is 2.5×** (43.7k at FF to 111.2k at SS at 1.5 mA), which is
much larger than the current-drift. So the corner, not the current, is what a
sizing rule has to be conservative about.

### The rule the S9 re-run uses

```
        w_tail  =  i_side  ×  111.2k µm/A          l_tail = 0.5 µm
        nf_tail =  smallest multiple of N=8 with w_tail/nf ≤ 100 µm   (G53)
```

**Sized at `ss/0.95/125 °C` deliberately** — the corner that needs the *most*
width — so the tail is saturated at every corner rather than only at nominal.
It is a stated decision, in `s9_yield.TAIL_UM_PER_AMP`, and a test pins it
against the CSV so the two cannot drift apart (rule 9).

---

## 4. Noise: the expectation was wrong, and the reason is instructive

The stated expectation before measuring was:

> *"My expectation is that it is largely common-mode and therefore rejected in a
> balanced pair, so S5 should barely move — check it rather than assuming, and
> say if I am wrong."*

**You are wrong, and the mechanism you named is real — it just applies to a
different device.**

`--noise`, per-instance attribution at TT, `W_tail` = 100 µm, `L` = 0.5 µm.
The parts reconstruct the total to **2.0e-9** relative, which is the gate on
believing any share below.

| contributor | ideal tail | | real tail | |
|---|---|---|---|---|
| | µV_rms | % power | µV_rms | % power |
| input pair, + | 109.8 | 15.95 % | 110.7 | 6.26 % |
| input pair, − | 109.8 | 15.95 % | 110.7 | 6.26 % |
| `Rs` degeneration | 153.2 | 31.04 % | 135.2 | 9.34 % |
| `RL`, + | 118.4 | 18.53 % | 108.6 | 6.02 % |
| `RL`, − | 118.4 | 18.53 % | 108.6 | 6.02 % |
| **tail, +** | — | — | **254.4** | **33.05 %** |
| **tail, −** | — | — | **254.4** | **33.05 %** |
| **mirror reference** | — | — | **1.8e-6** | **2e-21 %** |
| **TOTAL** | **275.0** | 100 % | **442.5** | 100 % |

**Three things to take from this table.**

1. **S5 moves ×1.61, and the two tail devices are 66.1 % of the noise power** —
   the single largest contributor, more than the input pair and both loads
   combined. It still **passes**: 0.442 mV against a 1.5 mV spec, so the
   headroom goes from 5.5× to 3.4×.
2. **The common-mode-rejection argument is visible in the same table and it
   works perfectly.** The mirror *reference* device's noise modulates `nbias`,
   which drives both tail gates equally, so it is exactly common-mode and is
   rejected to **2e-21 of the total** — ten orders of magnitude down.
3. **It does not apply to the tails because there are two of them.** S2 needs
   one sink per side or the degeneration is shorted (§1), and two separate
   devices have **independent** noise, so it appears differentially by
   construction. The textbook "tail noise is rejected" result assumes *one*
   tail whose noise current is shared by both sides.

### Units trap, recorded because this repo keeps hitting them

**The per-instance contributions are RMS volts and add in QUADRATURE.** They
sum *linearly* to 1082.5 µV against a true total of 442.5 µV — 2.4× — and in
quadrature to 442.465 µV, which equals `inoise_total` to every printed digit.
`Sky130Point.noise_share_power()` squares before normalising. Getting this
backwards is the same class of error as square-rooting `inoise_total`
(`tests/test_noise_units.py`) and it flatters whichever contributor is largest.

### Headroom is bought with noise

`gm_tail = 2·I/vdsat`, so a wider tail (lower `vdsat`, more headroom) has more
`gm` and injects more noise. That is the tail's design trade:

| `W_tail` µm | vdsat | margin | `gm_tail` mS | S5 | tail share of power |
|---|---|---|---|---|---|
| 50 | 0.2571 | +0.0985 | 6.95 | 0.384 mV | 54.9 % |
| 100 | 0.1882 | +0.1656 | 10.90 | 0.443 mV | 66.1 % |
| 200 | 0.1412 | +0.2114 | 16.19 | 0.498 mV | 74.3 % |
| 400 | 0.1083 | +0.2435 | 21.70 | 0.519 mV | 78.3 % |
| 800 | 0.0849 | +0.2662 | 26.38 | 0.489 mV | 78.6 % |

16× more width buys **+168 mV** of headroom and costs **1.27×** in S5. Noise is
therefore *not* what limits `w_tail` today — S3 is (§5).

### This is a SECOND coupling through the tail, and it is currently slack

`gm_tail = 2·I/vdsat_tail`, so **the tail's `vdsat` is a single knob with
opposite signs on two constraints**:

```
        small vdsat  ->  more v(source) margin   AND  more gm_tail  ->  MORE noise
        large vdsat  ->  less noise              AND  less margin   ->  tail_saturation
```

So the tail couples five box coordinates through *headroom* (§2) **and**
trades headroom against noise through `vdsat` on the same device. The second
coupling is slack right now — S5 sits 3.4× inside spec — which is exactly why
it is worth writing down before it stops being slack:

* **S5 headroom went 5.5× → 3.4×** when the tail became real. Still free; **no
  longer free by a margin anyone should ignore.**
* **It becomes live in the tunable experiment.** Raising `R_s` to get peaking
  adds `4kT·R_s` directly to the input-referred noise, on top of a budget that
  has just lost 1.61× to the two tails. `R_s` is already the largest passive
  contributor at the reference point (31 % of the noise power with an ideal
  tail; 9.3 % only because the tails swamped it).

**If S5 ever binds in this project, this is the mechanism it will bind
through**, and it will bind at the high-`R_s` end of the tuning range.

---

## 5. What the tail does to S3

`--rout`. Each tail device hangs from one source node to ground, so it adds
**both** a finite `r_o` (which shunts the `Rs`/`Cs` degeneration and takes
peaking *away*) **and** a parasitic capacitance (which degenerates less at high
frequency, exactly as `Cs` does, and *adds* peaking). The two pull in opposite
directions and both scale with tail size, so the net sign is a measurement.

Reference with an ideal tail: **4.500 dB at 4.365 GHz**.

### Axis 1 — width, at fixed `L` = 0.5 µm

| `W_tail` µm | vdsat | margin | `gm_in` mS | peaking | vs ideal |
|---|---|---|---|---|---|
| 25 | 0.3544 | +0.0064 | 11.955 | 2.736 dB | **−1.764** |
| 50 | 0.2571 | +0.0985 | 12.165 | 3.659 dB | −0.840 |
| 100 | 0.1882 | +0.1656 | 12.238 | 4.183 dB | −0.317 |
| 200 | 0.1412 | +0.2114 | 12.285 | 4.747 dB | +0.248 |
| 400 | 0.1083 | +0.2435 | 12.320 | 5.560 dB | +1.060 |
| 800 | 0.0849 | +0.2662 | 12.344 | 6.652 dB | **+2.152** |

### Axis 2 — length, at fixed `W` = 141.4 µm

| `L_tail` µm | vdsat | margin | `gm_in` mS | peaking | vs ideal |
|---|---|---|---|---|---|
| 0.15 | 0.0729 | +0.3085 | 11.012 | 3.052 dB | **−1.448** |
| 0.25 | 0.1083 | +0.2564 | 11.789 | 3.835 dB | −0.665 |
| 0.50 | 0.1626 | +0.1906 | 12.264 | 4.444 dB | −0.056 |
| 0.75 | 0.2037 | +0.1471 | 12.357 | 4.649 dB | +0.150 |
| 1.00 | 0.2380 | +0.1123 | 12.376 | 4.786 dB | +0.286 |
| 2.00 | 0.3415 | +0.0106 | 12.306 | 5.419 dB | +0.919 |

**Honest caveat: neither axis is a clean single-mechanism sweep**, because both
also move `vdsat`. What *is* clean is that `gm_in` barely moves across either
(11.0–12.4 mS), so this is the tail's **impedance** at the source node and not
a shift in the input pair's bias point.

**The two effects cancel near `W` = 200 µm at `L` = 0.5 µm**, where the real
tail reproduces the ideal one to +0.25 dB.

### The number that decides the recommendation

Session 11 measured that corner robustness needs **≥ 1.0 dB of peaking margin**
(that filter, with ≥ 0.133 octaves of `f_peak` margin, gives 92.1 % robustness
against a 60.8 % base rate).

* A tail **sized by rule** (`vdsat` within ±0.05 V of the 0.20 V target) shifts
  S3 peaking by only **−0.32 to +0.29 dB** — a small fraction of that budget.
* A tail left as a **free search dimension** can shift it by **2.15 dB** —
  **2.2× the entire budget**, on its own.

**That is the case for sizing the tail rather than searching it.**

### `nf_tail` is a near-dead dimension

`W` = 200 µm, `L` = 0.5 µm, `I_side` = 1.5 mA, TT:

| `nf_tail` | `nf_ref` | tail finger | ref finger | matched | `I_tail` mA | vdsat |
|---|---|---|---|---|---|---|
| 2 | 1 | 100.00 µm | 25.00 µm | no | 1.4779 | 0.1424 |
| 4 | 1 | 50.00 | 25.00 | no | 1.4524 | 0.1421 |
| **8** | 1 | 25.00 | 25.00 | **yes** | 1.3975 | 0.1412 |
| **16** | 2 | 12.50 | 12.50 | **yes** | 1.3966 | 0.1434 |
| **24** | 3 | 8.33 | 8.33 | **yes** | 1.3993 | 0.1453 |
| **32** | 4 | 6.25 | 6.25 | **yes** | 1.4053 | 0.1472 |

* **matched fingers only: 0.6 % spread** in delivered current
* **all `nf`, matched or not: 5.8 %**

So `nf_tail` carries essentially no design information, but choosing it *badly*
(breaking finger matching) costs ~6 % of mirror accuracy. It should be
**derived**, not searched — the same conclusion G38 reached for `nf_in` and G42
for `cl`.

---

## 6. The bounds — PROPOSAL ONLY

**`common/params.py` is untouched** (CLAUDEwa §8 rule 6: the box is a human
decision). Every edge below traces to a row of `tail_device_data.csv` and is
regenerated by `--bounds`.

### `w_tail`

| edge | value | provenance |
|---|---|---|
| **rule** | **105.4–124.0k µm/A** at `L` = 0.5 µm | `ss/0.95/125 °C` width for `vdsat_tail` = 0.20 V, measured at three currents spanning 0.75–3.00 mA/side; 1.18× spread is what makes it a density (§3) |
| **floor** | **82.9k µm/A** | below this the tail is in **triode** at `ss/0.95/125 °C`. Hard, not a target: a triode tail is not delivering its current, so every small-signal number above it describes a different circuit. **Interpolated onto `margin = 0`, not read off a ladder rung — see G52 note below** |
| **ceiling** | **~267k µm/A** (400 µm at 1.5 mA/side) | at this width the tail's own source-node capacitance moves S3 peaking by **+1.06 dB**, more than session 11's whole 1.0 dB margin requirement (§5). Noise agrees in direction but is not the binding limit |

### `l_tail`

| edge | value | provenance |
|---|---|---|
| **floor** | **0.5 µm** | at `L` = 0.15 µm the tail's output resistance shunts the degeneration and gives away **−1.45 dB** of peaking against an ideal tail — more than session 11's whole 1.0 dB margin. At 0.5 µm it is **−0.06 dB** (§5, axis 2) |
| **ceiling** | **1.0 µm** | the same headroom costs **2.27×** the width (111k → 252k µm/A at `ss/0.95/125 °C`), and width is what the S3 ceiling above is made of. Length past 1 µm buys output resistance the design does not need at a width cost it cannot afford |

### `nf_tail`

**Not a search dimension.** Derived as the smallest multiple of `N` = 8 that
keeps `W/nf ≤ 100 µm` (G53), which also keeps the reference a whole number of
matched fingers. Measured over the matched values `nf` ∈ {8, 16, 24, 32}: the
delivered current moves **0.6 %**. If it is searched anyway, the range is 2–32
and multiples of `N` are the only sane values.

### The recommendation

**None of the three should enter the action space.** `w_tail` follows from
`i_bias`, `nf_tail` follows from `w_tail`, and `l_tail` spans a single octave
with one genuine trade in it. That keeps the RL action space at **nine
dimensions rather than twelve** — and, given G42's finding that a badly chosen
dimension actively *lowers* the random-search yield, adding three near-dead
axes would make the G3 baseline harder to beat for no design benefit.

### A G52 catch, on this file's own numbers

The saturation floor was first computed as the smallest **passing ladder rung**
and came out at **112.1k µm/A** — *above* the vdsat-target rule's own 105.4k
lower edge. That is impossible: the saturation floor is by construction looser
than a `vdsat = 0.20 V` target when `v(source)` is ~0.33 V. It was a property of
the ladder, not of the device. Interpolated onto `margin = 0` instead:
**82.9k µm/A**. A test now asserts `floor < min(rule)` so the contradiction
cannot come back.

---

## 7. Two new gotchas

### G53 — the bin ceiling is on W per FINGER

Measured against the trimmed library at TT: `W=100 nf=1` builds, `W=101 nf=1`
aborts; `W=200 nf=2` and `W=400 nf=4` build, `W=210 nf=2` and `W=410 nf=4`
abort. The break is exactly `W/nf = 100 µm`, the `wmax = 1e-4` of the widest bin
in `sky130_fd_pr__nfet_01v8__tt.pm3.spice`.

`nf` still does not multiply width (G38 stands) but it **does** multiply the
ceiling. Without this, a tail needing 400 µm at `L` = 0.5 µm looks unbuildable
when it is routine.

**A knock-on for `PROPOSED_BOX`, reported and NOT folded in (rule 6):** `w_in`'s
provenance says *"the SKY130 nfet_01v8 W bin limit (wmax = 1.0e-4 m)"*, which is
the per-finger limit described as if it were a total. At `nf_in` = 8 the real
ceiling is 800 µm. Widening `w_in` is a human's call and would change the
sampled population.

### G54 — `.noise` can return `-nan(ind)` and exit 0

The mirror's reference device drives both tail gates equally, so its noise is
perfectly common-mode and is rejected to machine zero (§4). ngspice's
integrated-noise log-slope integration then evaluates `log(0)` and returns
`inoise_total = -nan(ind)` — **with exit code 0**. Only that one contributor is
ever NaN; every other stays finite, which is what identifies the mechanism.
Knife-edge in geometry (W = 141 µm fine, 200 µm NaN, 218 µm fine), so it is
numerics, not physics.

**It was caught only by accident.** `crosscheck.py`'s numeric regexes do not
match `"nan"`, so the value parsed as `None` and the run failed as "could not
parse". A laxer parser would have carried NaN into a spec check, where
`nan < tau` is False and reads as a genuine **failure** — biasing a yield
downward, silently. An explicit non-finite pattern is now in
`scan_for_silent_failures`, anchored to `= value` so `nfactor` and
`.param nano=1e-9` cannot trip it.

**The fix is a real circuit element, not a workaround:** a bias-node bypass
capacitor, which every current mirror has, to keep reference and supply noise
off the shared gate. `C_BYPASS_F = 10 pF`.

**The value provably does not change the answer** — which is how we know it is
not buying the result:

| point | 1 pF | 10 pF | 100 pF | 1 nF |
|---|---|---|---|---|
| ff/1.05/0 °C, W 519 µm | **NaN** | 0.505543 | 0.505543 | 0.505543 |
| ff/1.05/0 °C, W 336 µm | 0.509358 | 0.509358 | 0.509358 | 0.509358 |
| ss/0.95/125 °C, W 200 µm | 0.535162 | 0.535162 | 0.535162 | 0.535162 |
| tt/1.00/27 °C, W 100 µm | 0.442465 | 0.442465 | 0.442465 | 0.442465 |

(mV_rms; identical to every printed digit wherever they all compute.)

A residual **~0.4 %** of runs still NaN at extreme widths. Raising the bypass
clears individual cases, so it is a bounded numerical nuisance rather than a
physical limit; chasing it with capacitance is whack-a-mole and was stopped.

**Its area is not in any S7 estimate** — there is no S7 estimate, because no MIM
cap or poly resistor models have been pulled yet. Whoever builds one must
include a 10 pF capacitor.

---

## 8. The S9 re-run

`python -m nebula.experiments.s9_yield --n 2000`, **15 255 SPICE runs, 35.2
min at 8 workers.** Identical to session 12b except that the tail is a real
mirror. `PREDICTIONS.md` entry 2 was committed *before* it ran; the full
scorecard is there.

### The headline: nothing moved

```
                                12b (ideal tail)      13b (real tail)
        nominal PVT, both loads     15 / 1890            15 / 1890   0.79 %
        3 corners x 2 loads          1 / 1890             1 / 1890   0.05 %
        45 corners x 3 loads         1 / 1890             1 / 1890   0.05 %
```

**And it is the same design** — index 432, identical parameters. Health: 0
screen/promotion mismatches, 52 headroom rejections (exactly 12b's), 12 hard
failures in 15 255 runs (**0.08 %**, all G54 NaN).

### What DID move: the population underneath

```
                                12b        13b       delta
        robust at cl_lo alone    43         39         −4
        robust at cl_hi alone   118        108        −10
        robust at ANY load      160        146        −14   (−8.8 %)
        robust at EVERY load      1          1         ±0
```

and per screen column: `−7, −7, +5, +7, +0, −8`. So the tail is a **real but
second-order** tax — **8.8 %** of the corner-robust-at-some-load population,
against the load range's **99.4 %**.

### The mechanism, measured paired rather than inferred

600 designs at `cl_hi`, **the same design evaluated with an ideal tail and with
the mirror**, so the only difference is the tail:

| corner | pass with both | gained | lost | net |
|---|---|---|---|---|
| `ff / 1.05 / 0 °C` | 53 | 6 | 5 | **+1** |
| `ss / 0.95 / 125 °C` | 40 | 6 | **10** | **−4** |

* **The losses at slow-hot are the tail's own constraint:** 4 of the 10 are
  ranked `tail_saturation`, against 1 of the 5 at fast-cold.
* **The gains at both corners are mostly `S3_peaking`** — designs that had been
  outside the window, pulled back in by the mirror's ~2 % `gm` reduction and
  ~0.05 dB peaking reduction.

**The honest statement is "the tail costs designs at slow-hot and is roughly
neutral at fast-cold."** +1 on 600 paired designs is noise, and calling it a
gain would be over-reading.

### `tail_saturation`: how often it binds, and why the ranking hides it

| screen corner | **violated** | ranked worst |
|---|---|---|
| `ss / 0.95 / 125 °C` | **13.3 %** | 0.6-1.5 % |
| `ss / 0.95 / 0 °C` | 6.3 % | 0.4-0.8 % |
| `tt / 1.00 / 27 °C` | 5.2 % | 0.2-0.7 % |
| `ff / 1.05 / 0 °C` | 2.6 % | 0.1-0.2 % |

**The two columns differ by an order of magnitude, and that is the point.** The
first-failure ranking scores by normalised shortfall, so a constraint missing
by tens of millivolts always loses to an `S3_f_peak` missing by 17 GHz. Without
the violation table added this session, the tail's real footprint — a **13.3 %**
constraint at the worst corner — would have shown up as a 1 % footnote.

**The corner ordering is the sizing rule showing through.** The rule sizes at
`ss/0.95/125 °C`, so everywhere else the tail is deliberately oversized:
`vdsat_tail` is 0.201 V at SS/125 and 0.134 V at FF/0 for the surviving design.
Sizing at the worst corner costs width everywhere and buys a **5×** reduction in
tail-saturation failures at the best corner.

### The survivor, with a real tail under it

Design 432 gets **W 180.8 µm / L 0.5 µm / nf 8**, reference 22.6 µm / nf 1,
`I_ref` = 203 µA.

| corner @ load | `vds_tail` | `vdsat_tail` | margin | peaking | `f_peak` | mirror err |
|---|---|---|---|---|---|---|
| ss/0.95/125 @ lo | 0.4479 | 0.2006 | **+0.2473** | 6.058 dB | 1.995 GHz | −4.7 % |
| ss/0.95/125 @ hi | 0.4479 | 0.2006 | +0.2473 | 5.223 dB | **1.259 GHz** | −4.7 % |
| ff/1.05/0 @ lo | 0.4973 | 0.1342 | +0.3631 | 8.499 dB | **2.399 GHz** | −4.0 % |
| ff/1.05/0 @ hi | 0.4973 | 0.1342 | +0.3631 | 7.310 dB | 1.514 GHz | −4.0 % |
| ss/0.95/0 @ lo | 0.4358 | 0.1444 | +0.2914 | 7.659 dB | 2.188 GHz | −5.3 % |
| ss/0.95/0 @ hi | 0.4358 | 0.1444 | +0.2914 | 6.602 dB | 1.380 GHz | −5.3 % |

**Its tail has comfortable headroom (+0.25 to +0.36 V), so it did not survive by
luck on that axis.** What it spends is the *window*: `f_peak` ranges
1.259-2.399 GHz, **0.93 of the 1.00-octave S3 window**, confirming 12b's "less
than one ladder rung of margin" from an independent direction.

### What this settles

1. **The tail was not the missing coupled constraint — GIVEN THE CURRENT
   SCREEN.** HANDOFF §8 called it *"the one experiment that could still turn
   corner robustness into a real constraint rather than a tax"*. It did not.
   `tail_saturation` is a genuine coupled inequality — the only row in the
   table tying five box coordinates together — but it binds on 2.6-13.3 % of
   the box and costs 8.8 % of the corner-robust population, against the load's
   99.4 %.

   **MASKED, NOT UNIMPORTANT — and the distinction is the point.** The 8.8 % is
   measured on a population the LOAD screen had already reduced by 99.4 %, so it
   is a **conditional** number: "what the tail costs, given that the load range is
   already screened at its full 5.72x". `tail_saturation` binds on 2.6-13.3 % of
   the box and is the only constraint coupling five box coordinates; those two
   facts are unconditional. **The correct wording is "retired GIVEN THE CURRENT
   SCREEN", not retired absolutely.**
   
   **The re-check trigger, stated so it is not forgotten:** when the load screen
   narrows from the full derived range to a specification *tolerance band* — which
   is what `CL_RANGE.md` §7b and the tunable experiment are both heading towards —
   the surviving population grows, and `tail_saturation` should be re-read off the
   **violation** table to see whether it moves up. A constraint that binds on 13 %
   of the box cannot stay a footnote once the thing masking it is removed.
2. **G47's caveat is discharged.** Every S9 number in this project carried
   *"optimistic bound — the tail is ideal"*. It is now measured: the optimism
   was worth **8.8 %** of the corner-robust-at-some-load population and **zero**
   of the headline yield. G47's three-corner screen result survives; the screen
   was again exact (1 promoted, 1 robust, 0 false positives).
3. **The three-tier hierarchy still holds.** 0 screen/promotion mismatches
   across the repeated triples, and the 45-corner promotion again rejected
   nothing the 3-corner screen had passed.
4. **Session 11's margin thresholds were lower bounds, and they still are —
   but by less than feared.** They were derived with an ideal tail; the tail
   moves a rule-sized design's peaking by ~0.05 dB, well under the 0.0664-octave
   `f_peak` quantisation and the 1.0 dB peaking-margin threshold. Re-running
   `robust_geometry.py --collect` is now a low-value experiment, which is
   itself a useful thing to know before spending 23 minutes on it.
