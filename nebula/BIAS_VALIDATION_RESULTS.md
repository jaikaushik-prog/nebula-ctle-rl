# Physical reference: distortion and eye validation

6 September 2026, Entries 104/104b. **The fixed physical-reference circuit
passes the tested electrical model gate: 315/315 cases. Not yet adopted by
the RL product, and not a full receiver hardware/area compliance claim.**

## What this establishes

The two added PMOS devices, bias resistor and physically sized MIM bypass from
Entry 103 do not prevent this fixed CTLE from meeting the tested distortion,
request-match, noise, measured VDD-power and model-eye limits across the chosen
45 PVT points and seven constructed channels. No component dimensions or
switch settings changed between cases. This is a validation of one 9 dB /
1.9 GHz request, not proof of coverage of the entire tunable specification.

| Check | Worst measured/model result | Requirement |
|---|---:|---:|
| HD3 at 100 MHz, 0.1 V differential peak input | -81.490709 dBc | < -30 dBc |
| HD3 at 2.5 GHz, 0.267338 V differential peak input | -47.079003 dBc | < -30 dBc, existing additional gate |
| Eye height, ideal behavioural 1-tap DFE | 133.517 mV | > 100 mV |
| Eye width, ideal behavioural 1-tap DFE | 0.765625 UI | > 0.4 UI |
| Eye height, DFE removed | 131.943 mV | > 100 mV |
| Eye width, DFE removed | 0.65625 UI | > 0.4 UI |
| Pole/zero model fit residual | 0.112242 dB | Existing fit-rejection rule unchanged |

Height/width minima can occur in different cases. All four existing DFE policies
(ideal, none, 20% misadapted and quantised) meet both eye requirements in all
315 cases. The ideal ablation reproduces the main bridge at every case. This
does not implement a DFE, justify omitting the required block, or measure its
power, timing, decision errors or area.

The 45 distinct transistor-level PVT points are five MOS process corners x
three supplies x 0/27/125 C, with typical passive process and one fixed load.
Each feeds seven constructed channels: 3, 4.5, 6, 7.5, 9, 10.5 and 12 dB loss
at 2.5 GHz. **315 cases are not 315 independent SPICE circuits or measured
physical channels.** Eyes come from the existing fitted AC/pulse-response model
with measured DC compression guards, not a transistor-level PRBS receiver.

The smallest existing request-match margins are only **0.118983 dB** for
peaking and **0.004412 octave** for peak frequency (about 0.3% in frequency).
These are small margins. Independent passive variation, mismatch and selector
parasitics can still matter; no robustness claim beyond the tested model follows.

## The instrument mistake, and why the correction is legitimate

The first 90-call run passed both HD3 tones but accepted only 168/315 link
cases. I had used a default +/-0.8 V DC input sweep, overlooking the existing
G140 attenuation adjustment. With this input attenuator, that sweep ended
before measuring compression. The bridge correctly refused output predictions
above that lower bound; the results did not demonstrate actual compression.

The correction restores the already established
`_attenuation_run_args(...)["vid_max"]`: **+/-1.85391572 V at the external test
source**, with the same 4 mV step. This is a characterization sweep, not the
operating NRZ amplitude or the voltage swing at the attenuated MOS inputs.
It was not found by searching for a range that produces a pass.

Exactly 45 additional DC-only calls were run under a separate frozen correction
plan. All old HD3 waveforms and AC/noise data were reused and checked against
their hashes. No hardware, fit rule, compression guard, request tolerance or
eye threshold changed. Old failed-gate artifacts remain in their own directory.

Nominal measured output swing is 1.103941 Vpp. Across PVT, accepted measured
limits/lower bounds span 0.768511-1.296853 Vpp; 3 of 45 still remain lower
bounds. All tested pulse excursions are inside the resulting conservative
guard. The new tests require an explicit adjusted sweep range, preventing the
same default-range mistake from recurring silently.

## Cost and evidence

- Entry 103: 47 prior calls (calibration, DC/AC/noise and startup).
- Entry 104: 90 HD3/swing calls, 53.447 s.
- Entry 104b: 45 DC-only correction calls, 35.802 s.
- **135 new calls in this validation turn; 182 including the prior prototype.**
  Count the instrument mistake, not just the successful correction.

Both HD3 tones use the existing 5-cycle settling, 20-cycle capture and
100-samples/cycle instrument. The recorded input amplitude is parsed/formatted
consistently with the source. The shared FFT detail's historical `v1_v`/`v3_v`
fields are unnormalised bin magnitudes, not terminal-voltage amplitudes; HD3
uses their ratio. No separate settling/grid-refinement study was run here.

Authoritative corrected evidence:
[Entry 104b summary](product_audits/entry104b_physical_bias_swing_20260906/summary.json),
[full journal](product_audits/entry104b_physical_bias_swing_20260906/fixed_pvt.jsonl).
Original measurement/setup issue:
[Entry 104 summary](product_audits/entry104_physical_bias_validation_20260906/summary.json).
Plans: [initial](BIAS_VALIDATION_PLAN.md), [correction](BIAS_SWING_CORRECTION_PLAN.md).

All corrected evidence hashes were independently checked: zero mismatches,
45 distinct corners and one unchanged circuit signature. Both instrument
versions have source snapshots. No failed run was erased or relabelled as
having used the corrected sweep.

## What remains before calling the product complete

The counted geometry remains 0.007854511 mm2, **not full S7 area**. This gate
explicitly excludes S7 and keeps `full_product_compliance=false`. VDD power
includes the CTLE and new reference, not an implemented full receiver.

Still missing: transistor-level DFE/slicer/clock, physical Rs/Cs selection and
control, common-mode generation, independent passive-corner/mismatch checks and
credible layout-area/parasitic verification. Existing generic-resistor and
two-terminal MIM model limitations remain. The reference still has substantial
PVT current drift; these results do not turn it into a precision reference.

Next is controlled integration of this measured physical-reference path, with
truthful circuit export and fresh verification. Do not attach the old ideal-
reference RL bank's results to the new hardware. The old demo, policy, bank and
competition PDF have not been changed in this validation step.

Software checks: **2,812 passing before; 2,823 passing after**, 13 deselected
and two unchanged warnings. Focused checks: 39/39. No simulation/test process
remains running; no commit or push was performed.
