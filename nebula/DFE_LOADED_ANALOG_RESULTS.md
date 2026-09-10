# Entry 137: one accepted loaded analog snapshot; initialization failure retained

The physical transistor DFE is attached to the configurable CTLE. One
held-clock operating point passes the nominal broad analog-model limits.
The experiment is incomplete: the other held-clock state emits convergence
warnings, so the registered rule stops before distortion or the other targets.

The accepted state-1 measurement, TT / 1.8 V / 27 C:

- Input-referred loaded-CTLE noise: **0.635864655 mVrms**, below 1.5 mVrms,
  over the complete 10 MHz to 5 GHz band. This is a DC-linearized held-clock
  snapshot, not periodic receiver noise.
- CTLE peaking: **8.836252475 dB** at **1.750132069 GHz**. This meets the
  broad 3-12 dB / 1.25-2.5 GHz limits. It does NOT meet the requested
  9 dB / 1.9 GHz identity under the existing internal .5 dB / .1 GHz
  tolerances. The old control map needs loaded-frequency recalibration.
- Circuit VDD power: **9.280663703 mW**. External clock/control generators
  remain testbench apparatus, not included hardware generators.
- Strict signed new-DFE, whole-circuit magnitude/body and varactor envelopes
  pass. The bilateral tuning-switch signed audit remains separately reported.
- Independent integration of the saved noise spectrum gives
  0.637966458 mVrms, 0.330543% from the simulator's RMS total. The total
  is used directly; it is not square-rooted again.

State 0 prints "Further gmin increment" and "Last gmin step failed".
Although it writes numerical OP/AC/noise files and exits normally, the
strict warning check rejects the result. None of its numerical metrics
is credited as verified. No warning was suppressed and no retry occurred.

Exactly two calls, 103.8435664 s including 39.2008146 s complete prior-evidence
verification. All scientific source and external PDK hashes are unchanged.
No clocked distortion run or remaining tuning-map case ran. The geometry
subtotal remains 0.014715765982 mm2, not routed layout. Earlier NRZ PVT,
standalone tuning, runtime results and frozen RL claims remain separate.

Evidence: product_audits/entry137_dfe_loaded_analog_20260910/
Run source freeze: 818806be95462519f36f4998021155515fc785a8.
Original manifest: 84 entries, SHA-256
1b422c6c56894809ce87adbd845ccb4b77fa0abaaaa399f2ddf05c6cab349119.
Summary SHA-256:
5a0ee9d638785de33e11c5c23e2b878c39601280354e74b04b8307987598f802.
Only small static files exist; no waveform compression or raw deletion is needed.

Takeaway: adding the DFE has a measurable loading effect, while nominal
loaded-CTLE noise remains comfortably below its limit in the accepted
snapshot. Entry 138 tests released initial guesses for the bistable latch
without changing the hardware or loosening any acceptance rule.
