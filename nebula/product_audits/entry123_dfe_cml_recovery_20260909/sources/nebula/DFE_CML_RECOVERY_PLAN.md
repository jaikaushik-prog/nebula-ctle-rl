# Entry 123: fixed-width CML corner recovery

Registered 2026-09-09 before new measurements, under the owner's explicit
bounded hardware-development authorization. Entry 122 is closed and retained:
all three TT sizes pass, but selected W=4 um passes only 34/45 PVT points.
Every run stayed inside the signed terminal model domain. Hot/low-supply
failure has weak regenerative hold (wrong previous-bit and held signs), not
the old late CMOS-buffer rail transition. Wider TT devices showed stronger
held margins, with slower but still in-window clock-to-Q transitions.

Keep Entry 122 topology, resistor dimensions, tail/bias/clock devices,
pattern, input common-mode provenance, external clock, output scoring,
voltage checks and power/area accounting EXACTLY unchanged.

New finite membership: W=8 and 16 um input/regeneration pairs, each at
SS/0.95/125 C, FS/0.95/125 C, and FF/1.05/0 C (six calls). These include
the observed weak-hold cases and the fast/high-supply extreme. Select the
smaller width that passes all three, else stop this experiment. Then run
ONE selected fixed width at all 45 PVT points, including fresh TT control.
Maximum 51 calls, no retries, no per-corner resizing or membership expansion.
Original TT runs are context, not replacements for the new fixed-width PVT.

Run command after tests and freeze commit:

    py -3.13 -m nebula.experiments.exp_dfe_cml --recovery --out nebula/product_audits/entry123_dfe_cml_recovery_20260909

This still does not integrate the CTLE or a feedback DAC. Even a 45/45 pass
remains finite-pattern standalone decision/storage evidence, not complete DFE,
BER, metastability, hardware clock, mismatch or receiver signoff. Further
integration requires a separate preregistration. Frozen RL and reports stay
unchanged. Archive raw traces using byte-verified gzip siblings; keep local
uncompressed originals and the original immutable evidence manifest.
