# Calibrated configurable CTLE + transistor DFE

The calibrated physical circuit meets the nominal 9 dB / 1.9 GHz target
tolerances and passes independently measured noise, distortion and decoding.
It contains the actual SKY130 CTLE, physical configurable Rs/Cs network and
transistor-level DFE summer, memory and feedback DAC.

The fixed external control fractions are R=.70 VDD and C=.185 VDD (1.26 V
and .333 V at nominal supply). They were selected by a bounded 65-point
loaded OP/AC calibration, not by changing circuit geometry or relabeling the
old 1.75 GHz response. The measured nominal boost is 8.744-8.747 dB and
peak is 1.903-1.906 GHz, within the unchanged internal .5 dB/100 MHz target
tolerances. Do not call the actual measured boost exactly 9 dB.

Independent nominal checks (Entry 143, TT / 1.8 V / 27 C):

- Input-referred noise: .65404-.65405 mVrms over 10 MHz-5 GHz, below 1.5 mVrms.
  These are two negative-branch held-clock small-signal measurements, not
  periodic receiver noise or verification of all held branches.
- Clocked CTLE-output HD3: -54.9137 to -54.9201 dBc at 100 MHz with 100 mV
  differential peak input, below -30 dBc. All four numerical settings and
  all harmonic windows pass; generic-poly voltage-dependent nonlinearity
  remains outside the model verification.
- Physical decoding: 64/64 scored bits correct on the constructed 7.5 dB
  channel. Sampled eye is 210.340 mV; positive opening .705 UI, with .655 UI
  above 100 mV. This is finite-pattern, noiseless waveform evidence, not BER.
- VDD power in the decoding run: 9.26348 mW. Clock/control/common-mode
  generators remain external; this is not full receiver power.
- Geometry subtotal is .014715766 mm2, not routed layout area.

Inspect the exact fresh physical decoding netlist:
product_audits/entry143_dfe_calibrated_verification_20260910/link_state0_tol1e-05_step5ps/design.cir.
Its main/terminal waveforms, log and result are retained alongside lossless
gzip copies. The analog and decoder runners read actual primitives and
reject incomplete traces, warnings, mismatched controls and failed gates.

Evidence sequence: Entry 142 measures 65 OP/AC pairs in one 33.4446967 s call.
Entry 143 independently runs seven checks in 331.0175002 s. Old-control
Entry 141 HD3 and Entry 133 link PVT are separate records and are not silently
transferred. Entries 139/140 numerical aborts remain preserved failures.
All source snapshots and external PDK hashes are retained and verified.

Entry 144 independently passes **45/45 sampled link PVT points** with the
same controls, code and phase at every point: five transistor corners,
three supplies and three temperatures, on the same 7.5 dB constructed
channel. All 64 scored bits are correct at every point.

- Minimum sampled eye: 113.244 mV at FS / .95 VDD / 125 C.
- Minimum positive opening: .635 UI; minimum width above 100 mV: .560 UI.
- Maximum CTLE + DFE VDD power: 12.5241 mW, below 15 mW.
- Strict new-DFE voltage, whole-circuit magnitude/body and varactor envelopes
  pass. The separately recorded signed bilateral Rs-switch Vds model-domain
  findings remain present at all 45 points; this is not reliability signoff.

The 45-call run takes 1921.9629508 s including 2.9553573 s preflight.
Its immutable evidence is in product_audits/entry144_dfe_calibrated_pvt_20260910/.
Manifest: 362 files, SHA-256
c5213fb228fc450b882b2ce7b4be7219adc6f352d63315b5195af32a4e63afe1.
Summary SHA-256:
21a6b7cb5d81bd0e23981d2cc3741a9a0147b6793f401d63c646c5e08f06e424.
All 45 exact decks and actual waveform measurements are regression-replayed.

This is sampled **link PVT**, with nominal noise/HD3 measured separately.
Analog PVT, a complete loaded target map, DFE-active runtime tuning,
mismatch/passive tolerances and layout remain unverified. The local product
frontend now opens this pinned checkpoint in its **Receiver** view, including
the transistor device schematic, saved summer eye and 45-corner link grid;
run `py -3.13 -m nebula.web`. Its secondary Design explorer live generator,
CLI/registry, reports and frozen RL experiment still represent their earlier
scoped paths and have not been relabeled as this prototype. The result
demonstrates working calibrated transistor hardware without claiming complete
receiver or full competition signoff.

Reproduction note: Entry 143 uses one common call-label format. Its saved
`relative_tolerance` / `max_step_s` dispatch labels are actual solver settings
only for the tone cases. Static decks retain reltol=1e-7, vntol=1e-10 and
abstol=1e-13; the link deck explicitly uses a 1 ps transient step and limit.
Read the frozen deck for non-tone solver settings, not those shared labels.
Exact-deck and raw-waveform replay tests preserve this distinction; no
measurement or frozen metadata has been rewritten.
