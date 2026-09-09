# Entry 127: official SKY130 tunable-capacitor characterization

Measured 2026-09-10 from checkpoint fa5fbed. All 46 registered calls ran once:
one complete-cell multiplier calibration and 45 process/supply/temperature
probes. Every call has valid finite currents and DC biases; all 319 external
PDK dependency hashes remained unchanged. Trial wall time 1656.665651 s,
excluding preceding DFE archive verification. No CTLE/DFE insertion yet.

Native m=4 and m=500 match explicit parallel complete cells at both electrodes
and all four tested frequencies. The subcircuit's vm=4 does NOT reproduce
complete-cell substrate loading; it is not used in candidates.
The full library emits its multiplier-hierarchy warning; it is retained in
the raw logs, and the explicit two-electrode native/parallel comparison is
the measured check of the candidate multiplier rather than an assumption
that a successful exit code establishes correct scaling.

At TT/1.00/27, source common mode 0.5 V, 2.5 GHz, the same fixed pair of
500 unit cells per side gives:

| External control | Differential effective C | Parallel loss G | Q |
|---|---|---|---|
| 0 V | 4.680496 pF | 21.583813 mS | 3.4063 |
| 0.45 V | 1.326954 pF | 0.672394 mS | 30.9993 |
| 0.90 V | 1.067042 pF | 0.273943 mS | 61.1845 |
| 1.80 V | 1.064084 pF | 0.272366 mS | 61.3681 |

Across all 45 PVT cases and all declared source/control probes, the 2.5 GHz
capacitance range is 0.970218 to 5.946816 pF; parallel conductance is
0.207065 to 31.557674 mS; Q is 1.99936 to 73.61499. These global extrema
are NOT a guaranteed tuning range at one bias/corner. At each source bias,
capacitance decreases strictly with increasing control at all four test
frequencies in every one of the 45 PVT cases. The source biases
0.35/0.50/0.65 V bracket the earlier measured CTLE source-voltage envelope;
0.80/0.95 V are additional declared headroom probes.

The useful finding is real electrical capacitance tuning, with substantial
GHz loss at the high-C end. Therefore the next registered CTLE screen tests
smaller tunable arrays combined with a fixed MIM capacitor, carrying loss
into the actual amplifier instead of treating capacitance as ideal.
No old failed switch-bank gate is relabelled as passed.

One candidate pair occupies 2500 um2 active cell geometry, not routed area.
The control voltage is an external ideal AC ground in this isolated probe.
The installed varactor subcircuit does not establish substrate leakage or
breakdown. This characterization does not verify CTLE peaking, eye, HD3,
noise, runtime settling, a physical control generator or full receiver PVT.

Raw evidence: `product_audits/entry127_varactor_probe_20260909/` (291 original
manifest entries, including every raw deck/log/OP/complex-current table).
Summary SHA-256:
`9d687f8d1c836d8e5ff9cf915a853126bb303631ef0957dc0577a4cefdb16339`.
Manifest SHA-256:
`ffd538df78082790601e7831868152046b507e0c2d7c5598414c1ad0bc37b843`.
