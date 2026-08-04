# G0 — toolchain gate results

**Date:** 2026-08-03 · **Verdict: PASS, with one substantive finding.**

Gate criterion (CLAUDEwa.md §7): *"ngspice + PDK runs DC sweep, AC sweep,
`.noise`, `.disto` on a diff pair."*

| Analysis | Status | Notes |
|---|---|---|
| `.op` | **works** | operating point, `@m1[gm]` etc. all readable |
| `.ac` | **works** | 251-point decade sweep, 1 MHz – 100 GHz |
| `.noise` | **works** | `inoise_total` / `onoise_total` over 10 MHz – 5 GHz |
| `.disto` | **runs, but returns exactly zero for BSIM4** | see below — this is the finding |

## Environment as installed

- **conda:** Miniforge3 26.3.2, user-scope, `C:\Users\DELL\miniforge3`
- **env:** `nebula` — python 3.11, **ngspice 41** (conda-forge), numpy, scipy,
  matplotlib, pandas, pytest
- **binary:** `C:\Users\DELL\miniforge3\envs\nebula\Library\bin\ngspice_con.exe`
  — note **`ngspice_con.exe`**, not `ngspice.exe`. The latter is the GUI build
  and produces no console output under `-b`, which looks exactly like a broken
  install. Use the `_con` binary for everything.
- **PySpice 1.5** is installed but **not usable**: its bundled ngspice DLL
  fails to load (`OSError 0x7e`) and the post-install downloader is dead. This
  is not worth fixing — batch-mode `ngspice_con -b netlist.cir` via
  `subprocess` is a better fit for the RL loop anyway (no FFI state to corrupt,
  trivially parallel across corners, and a crashed run is an exit code rather
  than a segfault inside the Python process).

Reproduce: `nebula/device/spice/g0_diffpair.cir`.

## The finding: `.disto` is unusable for HD3 with any real PDK

`.disto` runs to completion on a BSIM4 differential pair and reports
**exactly 0.0** for both the 2nd and 3rd harmonic. That is not a linear
circuit — it is a model that contributes no distortion terms at all.

Confirmed with a controlled A/B in one netlist
(`nebula/device/spice/g0_disto_control.cir`): the same topology built twice,
once with BSIM4 (`level=54`) and once with the Shichman-Hodges `level=1`
model, driven by the same source.

| Model | fundamental | 3rd harmonic | HD3 |
|---|---|---|---|
| BSIM4 `level=54` | 100.1 mV | **0.0** | — (no distortion terms) |
| MOS `level=1` | 95.3 mV | 103.2 µV | **−59.3 dBc** |

`level=1` produces a sensible answer, so `.disto` itself works — BSIM4 simply
does not implement the higher-order derivative routines the analysis needs.
**Every open PDK we might use (SKY130, IHP SG13G2) is BSIM4-based**, so this
is not something a different PDK fixes.

**Consequence: S4 (HD3 < −30 dBc) must be measured by transient + FFT.**

## The fallback works, and it is cheap

`nebula/device/spice/g0_hd3_tran_fft.cir` — 100 MHz differential tone, 5
cycles settling, 20 cycles captured at 10 ps, FFT in Python over an exact
integer number of cycles (no window, no leakage).

```
samples=20000  dt=10.0ps  span=200.0ns  binwidth=5.00MHz
  H1 @ 100.0 MHz : 1.9917e-02 V (    0.00 dBc)
  H2 @ 200.0 MHz : 9.2305e-12 V ( -186.68 dBc)
  H3 @ 300.0 MHz : 6.5330e-07 V (  -89.68 dBc)
  H5 @ 500.0 MHz : 4.0395e-10 V ( -153.86 dBc)

HD3 = -89.68 dBc     (S4 wants < -30 dBc)
```

Two sanity checks pass: HD2 is ~180 dB down (a balanced differential pair
cancels even harmonics, so this is the number it *should* be, and its absence
would have meant the netlist was unbalanced), and odd harmonics fall off
monotonically.

### Cost, for the fidelity-tier budget

| Path | wall clock, one corner |
|---|---|
| `.op` + `.ac` + `.noise` | **0.066 s** |
| transient + FFT (HD3 only) | **0.256 s** |

~4× for HD3, but both are sub-second, so the full 45-corner sweep is roughly
**3 s** for AC+noise and **12 s** with HD3 included. That is comfortable —
the earlier worry that a transient-based HD3 would blow up the per-evaluation
budget does not materialise at this circuit size.

### Scaled to a training run — this is the abstract's number

At 10⁵ PPO steps, measured rather than asserted:

| Tier | wall clock | vs cheapest |
|---|---|---|
| TT only, no HD3 | **1.8 hours** | 1× |
| TT only, with HD3 | **7.1 hours** | 3.9× |
| 45 corners, no HD3 | **3.4 days** | 45× |
| 45 corners, with HD3 | **13.3 days** | **175×** |

That **175× spread** is the quantitative justification for the three-tier
corner-aware fidelity hierarchy (CLAUDEwa.md §7, contribution 1). It is a
much stronger claim in the abstract than a hand-wave about simulation being
expensive, and every number in it comes from a run on the target machine.

**Recommendation:** do not run HD3 on every evaluation. §3 says linearity is
the comfortable spec, and the reference point above sits ~60 dB inside it.
Put HD3 in the promotion tier only (evaluate on candidates that already clear
the other specs), which keeps the inner loop at 0.066 s/corner and the
tier-3 sweep at 3.4 days rather than 13.3.

## Preview of G1 from the smoke-test netlist

Not a hand-design — generic BSIM4 cards, ideal tail current sources — but the
AC numbers are already informative:

| | value |
|---|---|
| gm (per device, 2.5 mA) | 10.97 mS |
| DC gain | −14.57 dB |
| gain at Nyquist (2.5 GHz) | −7.96 dB |
| peak gain | −6.28 dB **at 1.259 GHz** |
| **peaking** | **8.29 dB** |
| integrated input noise, 10 MHz–5 GHz | 0.27 mV_rms |
| power (1.2 V × 5 mA) | 6.0 mW |

Peaking of 8.3 dB sits inside S3's 3–12 dB, and 1.26 GHz sits just at the
bottom edge of S3's 1.25–2.5 GHz window. Note the DC gain is **−14.6 dB**:
the stage attenuates heavily at DC, which is exactly what
`nebula/device/mock.py` had to do to stay out of compression.

**Do not put any of these numbers in a deliverable.** Generic model cards, no
PDK, ideal current sources.

## What G0 has NOT done

1. ~~**No PDK installed.**~~ **RESOLVED 2026-08-04.** SKY130 is installed via
   `volare` (WSL2) and copied to `C:\Users\DELL\sky130A`; `.op`, `.ac` and
   `.noise` all run against `libs.tech/ngspice/sky130.lib.spice`, with all
   five S9 process corners (`tt|ss|ff|sf|fs`) available as `.lib` sections.
   Reference netlist `nebula/device/spice/g1_sky130_volare.cir`. See HANDOFF
   G33 for the install and G31 for the micron-units trap.

   Still open on top of the PDK: everything above still uses **generic BSIM4
   cards at 1.2 V**, and the SKY130 device is 1.8 V, so the G1 sizing and its
   parameter bounds do not transfer. The **MIM capacitor and poly resistor**
   models that Cs, Rs, RL and the S7 area estimate depend on are present in
   the install but not yet exercised.

## The PDK changes the cost model — the table above assumes generic BSIM4

**Measured 2026-08-04**, same netlist structure, same machine, only the model
library differing:

| | per ngspice invocation |
|---|---|
| generic BSIM4 cards (`g1_handdesign.cir`) | **0.02 s** |
| SKY130 lib (`g1_sky130_volare.cir`) | **16.5 s** |

That is a **~700× per-invocation penalty, and essentially all of it is library
parsing**, not analysis. It is paid once per *process*, so it collapses if
evaluations are batched:

| batching | total | marginal per point |
|---|---|---|
| 1 sizing point per process | 16.5 s | 16.5 s |
| 20 points in one process | 16.57 s | ~0.004 s |
| **200 points in one process** | **16.89 s** | **~0.002 s** |

**Consequence for the fidelity hierarchy — this is not an optimisation, it is
the difference between feasible and infeasible.** At 10⁵ PPO steps on SKY130:

- one ngspice process per evaluation → 10⁵ × 16.5 s ≈ **19 days** for TT
  alone, against the 1.8 hours the generic-BSIM4 table above records. A ~250×
  blowup that would otherwise have been discovered in September.
- a persistent process per corner, with `alter` between sizing points →
  16.5 s once plus ~0.002 s/point ≈ **minutes**.

### Resolved 2026-08-04: process reuse is the WRONG fix. Trim the library.

The 200-point probe above altered resistors only, so three things were
measured before designing the device layer around `alter`.

**Test 1 — hierarchical `alter` into the subckt: WORKS mechanically, but
takes plain (scale-unit) numbers.** `alter @m...[w] = 3.2u` applies
`scale=1e-6` a second time and gives 3.2e-12 m; `alter @m...[w] = 3.2` is
correct. The X-instance form `alter xm1 w=...` does not work at all.

**Test 2 — does it produce the RIGHT answer? NO, and not even within a bin.**
Compared against fresh-parse ground truth:

| W (µm) | bin vs baseline W=4 | gm fresh | gm altered | error |
|---|---|---|---|---|
| 4.5 | **same** bin [3,5] | 2.358e-3 | 2.272e-3 | **−3.6%** |
| 6.0 | crosses to [5,7] | 3.175e-3 | 2.407e-3 | **−24.2%** |
| 9.0 | crosses to [7,100] | 3.6e-3 | **NaN** | broken |

The same-bin failure is the informative one and it kills the approach
outright: the `sky130_fd_pr` subckt derives `ad/as/pd/ps/nrd/nrs` from W by
`.param` expression at **parse** time, so `alter` moves W and leaves every
geometry-derived parasitic stale. It can never be right for device geometry,
in any bin. Worse, ngspice printed `Error: no model available for w=...` and
`print @m1[gm]` still returned the **stale** value — the §8 rule 10 failure
mode again.

**Test 3 — trim the library. This is the fix.** The S2 CTLE instantiates one
device type; the full library parses 30 families per corner and throws the
rest away.

| | per invocation |
|---|---|
| full `sky130.lib.spice` | 16–35 s (variable, disk-cache dependent) |
| `sky130_nfet_only.lib.spice` | **0.42 s** (tight) |

**~40–80× faster, and bit-identical** — verified exactly equal (`rel=0,
abs=0`) on gm, gmbs, vth, id, g_dc, g_pk and inoise_total across all five
process corners × four (W, L) points straddling three W bins and two L bins
(`nebula/tests/test_trimmed_lib.py`). It also removes the *variability*,
which matters more than the mean for a fidelity schedule.

**Revised cost picture at 10⁵ PPO steps, TT only:**

| approach | wall clock |
|---|---|
| generic BSIM4 (no PDK) — the original table | 1.8 h |
| full SKY130 lib, one process per evaluation | **~19 days** |
| **trimmed SKY130 lib, one process per evaluation** | **~11.7 h** |

So a PDK-backed inner loop costs roughly **6.5× the no-PDK baseline**, not
250×, and needs no process-reuse machinery at all. `alter` remains usable for
the ideal R/C/I elements (rs, cs, rl, cl, i_bias) if that 6.5× ever needs
attacking, but the input pair's W/L/nf must go through a fresh parse.

**Consequence for the fidelity-hierarchy claim:** it survives, because the
tier *ratios* are set by corner count and HD3, which the trim does not change.
But **quote ratios, not absolute wall-clock**, until a tier has been timed
end-to-end on the trimmed PDK.
2. **No tail current source device.** Ideal `i1`/`i2` sinks were used to
   isolate the input pair. The tail transistor's headroom is one of the two
   constraints that make S6 bind.
3. **No corner model cards.** SS/FF/SF/FS need the PDK's corner files.

## Notes for whoever writes the ngspice wrapper

- Use `ngspice_con.exe`, not `ngspice.exe`.
- `.disto` with a trailing `f2overf1` argument silently switches to two-tone
  intermodulation mode and aborts with *"No source with f2 distortion input"*
  unless a `distof2` source exists. Single-tone harmonic mode is the form
  **without** that argument. (This cost 20 minutes and looked like a broken
  `.disto` when it was a broken invocation.)
- `meas ac ... vdb(a,b)` — the two-argument `vdb` form is **not** supported in
  `meas`. Build the differential vector explicitly first:
  `let vd = v(outp)-v(outn)` then `let vd_db = db(vd)`.
- `maxat` is not a `meas` function in ngspice 41. `MAX` reports the value and
  prints `at=<x>` alongside it; parse that, or use `WHEN`.
- `linearize` takes vector names, not a timestep.
- ngspice's own `fft` zero-pads to a power of two, which moves the bin
  indices away from the obvious `f/binwidth`. Dump with `wrdata` and FFT in
  numpy instead — the bin arithmetic is then exact and testable.
