# Entry 104b - restore the existing G140 swing instrument

Entry 104 completed its 90-call budget. All 45 corners pass both HD3 tones,
but only 168/315 link cases pass the compression-validity gate. Inspection
found an INSTRUMENT ERROR: Entry 104 used the generic +/-0.8 V sweep rather
than `_attenuation_run_args`' existing `0.8 / input_gain` sweep. All its sweep
limits are lower bounds, not observed compression points. This cannot establish
that the new physical reference broke the circuit's large-signal behaviour.

## Bounded correction, frozen before new measurements

- Restore `_attenuation_run_args(atten_code, atten_max_x)['vid_max']` from the
  same candidate metadata used by Entry 101. This is the existing G140 rule,
  not a newly chosen amplitude or a larger sweep chosen to force a pass.
- Maximum 45 additional DC-only SPICE invocations, one per existing PVT point.
  No repeated HD3, AC or noise, no circuit changes, no retries or calibration.
- Check exact circuit signatures and fresh OP identity again. Reuse Entry 104's
  captured HD3 and Entry 103's captured AC/noise. Preserve both old directories.
- Write a separate correction directory, journal, summary, source snapshots and
  hashes. Count all costs: 90 original calls + 45 correction calls maximum.
- Same fit/compression, target/electrical/eye limits; full S7 remains unknown.
  If the corrected instrument still rejects cases, report them and stop; do not
  extend the sweep again or select another circuit in this validation turn.
- Add a regression pinning the attenuation-adjusted sweep range. Do not quote
  Entry 104's rejected cases as measured compression or erase its original result.
