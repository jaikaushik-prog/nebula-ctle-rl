# Entry 137: loaded CTLE analog specification screen

Registered 2026-09-10 after the owner prioritizes actual competition
requirements over the internal 500 ns runtime target. No new circuit sizing,
frozen RL change, report promotion or product integration in this experiment.

Use the exact Entry 133 physical configurable CTLE plus transistor CML summer,
decision memory and feedback DAC: N500/no fixed MIM, bleeders L=4, normal code
2 and phase 1 UI. Every device, original output load, external common-mode
source and physical reference is preserved. Only external stimulus, held
clock states, registered control voltages and numerical analysis change.

Maximum 20 sequential ngspice_con calls, 180 s each, no retries:
1. Primary 9 dB / 1.9 GHz controls (.7/.165 VDD), TT/1.8 V/27 C, both held
   complementary clock states .6/1.2 V and 1.2/.6 V: OP, 251-point complex
   AC from 1 MHz to 100 GHz, differential CTLE-output noise over EXACTLY
   10 MHz to 5 GHz (500 linearly spaced points at 10 MHz increments).
   Run both; stop after two if either instrument is invalid.
2. Two clocked 100 MHz distortion runs, 100 mV DIFFERENTIAL PEAK input
   (200 mVpp), same primary controls, real original 5 GHz external clock.
   Stop 150 ns; maximum time steps 5 ps and 2.5 ps. Run both and retain both.
   Stop after four if either instrument is invalid.
3. All eight other previously selected Entry 131 tuning identities, each
   at both held clock states, with the same OP/AC/noise instrument. No
   selection or retuning based on these new results; retain all 16 cases
   even if a specification or later instrument fails.

All runs use reltol=1e-7, vntol=1e-10, abstol=1e-13. These explicit precision
settings do not change the circuit. No fabricated endpoint, noise, bit or
harmonic primitive may enter evidence. No .disto for BSIM4 (G21), and no
two-row AC shortcut (G164).

Strict extraction:
- Exact primitive dimensions, finite values, expected frequency membership,
  AC differential input unity, actual supply/control/clock/input values.
- Both signed new-DFE and whole-circuit magnitude/body envelopes, exact
  bilateral Rs-switch signed findings separately, varactor voltage envelope.
- Noise totals are already RMS V; spectra are V/sqrt(Hz), explicitly
  unset sqrnoise. Require positive totals/spectra and independently
  reintegrate squared spectra over the full band; disagreement >2% is an
  instrument failure, never a replacement noise value.
- AC broad S3: peaking 3-12 dB, interior peak 1.25-2.5 GHz. Track nine target
  identities separately using the unchanged Entry 131 internal tolerances
  .5 dB / .1 GHz. Those tolerances are not organiser-specified accuracy.
- S5 loaded-CTLE static-model noise <1.5 mVrms, measured VDD power <15 mW.
- Clocked HD3: extract physical CTLE output outn-outp, not the hard-decision
  output. Uniform interpolation to 2.5 ps, exact 10-cycle window 50-150 ns,
  with separate five-cycle halves. Use raw fundamental/third harmonic
  amplitudes; no zero floor that could disguise missing data. Record the
  5 GHz clock component and summer harmonics as separate diagnostics.
- All three CTLE windows must be below -30 dBc; the two halves must agree
  within .5 dB. Two time-step runs must agree within .5 dB HD3 and 1%
  fundamental amplitude. These are internal numerical-evidence checks,
  not new competition specifications. Preserve instability as failure.
- Report circuit VDD power separately from external positive clock and
  tuning-source power; external generators are not implemented here.
- Scan simulator logs and reject unregistered warnings. Retain the known
  generic-resistor ignored sw_et/isnoisy/p2/q2/p3/q3 qualifications. These
  models do not validate passive voltage-dependent nonlinearity.

Evidence boundaries:
This establishes only nominal loaded CTLE small-signal/noise snapshots and
a finite clocked transistor-loaded HD3 model measurement. Ordinary ngspice
noise linearizes around a DC operating point; two held clock states are NOT
periodic noise, a switching-noise bound, or full receiver input noise.
Even passing model HD3 does not close generic-poly nonlinearity signoff.
No new PVT analog/HD3 sweep, loaded NRZ eye map at other controls, complete
3-12 dB by 1.25-2.5 GHz target rectangle, BER, layout, passive tolerance,
mismatch, runtime DFE decoding or full receiver signoff is claimed.
The 45/45 Entry 133 bit/eye/power result remains a separate frozen result.

Source basis: ngspice operating-point/noise documentation and implementation:
https://ngspice.sourceforge.io/docs/ngspice-manual.pdf
https://raw.githubusercontent.com/ngspice/ngspice/master/src/spicelib/analysis/noisean.c
Existing measured RMS-unit test: nebula/tests/test_noise_units.py.
These references explain the method; the installed ngspice 41 binary hash
and actual raw primitives remain authoritative for this experiment.

Verify complete Entry 133 archived evidence and Entry 131 raw manifest;
check every prior scientific source hash and external PDK dependency.
Snapshot the complete source closure, simulator identity and git commit.
Failure-first focused checks and full regression must pass, then freeze
locally before a single run into:
product_audits/entry137_dfe_loaded_analog_20260910/
Retain all failures and archive trace/terminal files losslessly without
deleting originals. Do not promote incomplete measurements to the product.
Public upload remains paused until the contradictory privacy instruction
is explicitly resolved.
