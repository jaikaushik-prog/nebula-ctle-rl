# Loaded CTLE distortion with clocked transistor DFE

Entry 141 passes all four preregistered numerical settings at TT / 1.8 V /
27 C. The same physical configurable CTLE and transistor DFE are used;
the test applies a 100 MHz sine at 100 mV differential peak.

- CTLE-output HD3: -55.4354 to -55.4369 dBc, below the -30 dBc requirement.
- Fundamental output: about 39.10 mV peak; third harmonic: about 66.12 uV peak.
- CTLE + DFE VDD power: 9.2579-9.2586 mW, below 15 mW.
- External clock positive power: .11708-.11716 mW, reported separately.
- Four-way maximum HD3 spread: .0015561 dB. Both half-windows also pass.
- Complete 150 ns waveforms, actual input/clock/initial-state primitives,
  strict new-DFE voltage and whole-circuit magnitude/body gates all pass.

The recovery changes numerical settings, not transistor sizes or controls.
Both default-method Entry 139 traces abort at 2.6/3.89 ns. Gear-only Entry
140 aborts at 13.49/18 ns. All failures are retained and remain rejected.
Entry 141 uses Gear-2, relative tolerances 2e-5/1e-5 crossed with 5/2.5 ps
steps, VNTOL 1e-7 V and ABSTOL 1e-12 A. All four cases must pass with every
pair agreeing within .5 dB HD3 and 1% fundamental; no best-case selection.
Tolerance meanings/defaults are documented in the
[official ngspice manual](https://ngspice.sourceforge.io/docs/ngspice-43-manual.pdf).

This is a nominal simulated-model result at the loaded CTLE output, not
distortion of the hard decision. Generic-poly voltage-dependent nonlinearity
remains unverified. Clock/common-mode/control generators remain external.
Periodic receiver noise, analog PVT, full receiver signoff and layout are
not established. The unchanged controls still peak near 1.75 GHz rather
than the requested 1.9 GHz; that separate calibration remains necessary.
The prior positive held-state convergence warning is not erased.

Evidence: product_audits/entry141_dfe_linearity_tolerance_20260910/.
Exactly four calls: 246.3457895 s including .4406218 s prior archive proof.
Prior two-call costs remain separately billed: Entry 139 60.9518274 s,
Entry 140 80.2683491 s. All scientific source and PDK hashes are unchanged.
The source snapshot is authoritative; Git ca8cfb9 is recorded honestly as
the dirty worktree's parent, not a commit containing the new runner.

Manifest: 107 entries, SHA-256
56071ef43b5e0084318ed1a35a1246d0567bde105bbb512eba8f96e5ed064eb7.
Summary SHA-256:
dd25c77f80f18d90f8706da310a7d7e900ce6dd003f14a6f0500bbb86056b748.
Original traces are retained alongside lossless gzip copies. Regression
tests verify complete archives, exact decks and all four raw-waveform replays.
