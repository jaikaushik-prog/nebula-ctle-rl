# Entry 136: extend observation, preserve the failed 500 ns criterion

Registered 2026-09-10 after Entry 135's valid transient shows 1.5--3.5 mV
control errors at the last windows and fails the 1 mV/500 ns settling gate.
The circuit does change response; the actual combined settling time is not
yet bounded by that run. Do not change the recorded gate or claim it passed.

One ngspice_con call maximum, 180 s, no retry. Keep the exact same physical
CTLE, all device values (including 10 kohm control feeds), TT supply/temp,
two-tone stimulus, solver precision and 5 ps maximum step. Reuse the three
accepted Entry 135 static references after verifying the complete raw/gzip
manifest, source hashes and external PDK closure. No static SPICE reruns.

Only observation timing changes: control ramp starts at 100/1100/2100 ns,
same 10 ns ramp and 9 -> 3 -> 6 -> 9 sequence, stop at 3100 ns. No reset,
no device or control-voltage change. Verify exact deck equality after only
the two PWL source lines and transient-stop line are removed from comparison.

Use the unchanged two-tone fitting, all 1 mV/2%/5%/15 mW window gates,
input/voltage checks and contiguous-tail definition. Evaluate 20 ns windows
every 10 ns, now 98 windows per transition. Report each observed windowed
settling bound, or None if it still does not settle before the next change.

Report TWO separate conclusions: whether all three transitions eventually
settle within the longer observation, and whether their measured bounds
meet the ORIGINAL 500 ns criterion. The latter must remain false if any
bound exceeds 500 ns, even if eventual settling is demonstrated. Missing
verification, invalid primitives or electrical envelopes fail both conclusions.
This is characterization, not a relaxed replacement pass for Entry 135.

Failure-first tests and focused/full regression precede local freeze and
one run into `product_audits/entry136_configurable_rc_settling_20260910/`.
Retain full raw traces, failures and lossless gzip copies. Record the prior
four calls separately. No DFE runtime/BER, runtime PVT, noise/HD3 or full
receiver claim follows. Original connected PVT, PDFs and RL remain unchanged.
