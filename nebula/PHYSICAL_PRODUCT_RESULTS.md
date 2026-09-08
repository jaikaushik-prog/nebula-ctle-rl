# Physical-bias product integration - Entry 105

2026-09-06. The physical-reference experiment is now available as an **opt-in
product mode**, not just a standalone experiment. The old mode remains unchanged.

## What works now

Enter peaking and frequency, select **Physical bias - fixed circuit - fresh PVT**
in the dashboard, then Generate and verify. The background worker proposes one
design, builds the physical reference and bypass MIM, and freshly verifies that
same circuit across all 45 PVT corners. The result includes a schematic, exact
SPICE deck, fixed PVT explorer and downloadable raw evidence.

If the server was already running before this update, restart it from the repo
root with `py -3.13 -m nebula.web` and refresh the page. The historical Judge
button still loads the original legacy artifact; it does not relabel it physical.

Command-line equivalent (choose a **new** output folder for each run):

```powershell
py -3.13 -m nebula.design --method rl-physical --peaking 9 --f-peak 1.9 --out output/my_physical_design
```

The mode always performs fresh verification, even without `--verify`. Maximum
137 SPICE calls per accepted proposal; no retry that changes the bypass capacitor.
Run one simulator job at a time. A failed circuit stays failed; an empty legacy
fixed-setting intersection refuses this proposal procedure, not all possible
physical circuits.

## Measured product acceptance run

[Product files](product_demo/physical_bias_9db_1p9ghz_20260906/README.md)
and [raw summary](product_demo/physical_bias_9db_1p9ghz_20260906/physical_evidence/summary.json).

| Check | Result |
|---|---|
| Request | 9 dB at 1.9 GHz |
| Delivered TT response | 8.834174 dB at 1.768990 GHz |
| Request acceptance | Within existing 1.5 dB / 0.3-octave tolerances; not an exact match |
| Fixed setting | 490 (A7/B42), unchanged across PVT |
| Electrical model gate | 45/45 corners; 315/315 corner/channel cases |
| Fresh SPICE work | 137 calls, 107.908 s on this machine |
| Nominal CTLE + reference VDD power | 6.965787 mW |
| Nominal input-referred noise | 0.589729 mVrms |
| Worst HD3, 100 MHz / Nyquist | -81.490709 / -47.079003 dBc |
| Worst ideal-DFE model eye | 133.517 mV and 0.765625 UI |
| Worst no-DFE control eye | 131.943 mV and 0.656250 UI |
| Counted gate/body/plate subtotal | 0.007854511 mm2, including bypass MIM |
| Full receiver area/compliance | Unknown / not verified |

HD3 drive: 100 MHz at 0.1 V differential peak; 2.5 GHz at 0.267338 V
differential peak. Typical passive process, one assumed external load
(32.62806 fF each output), seven constructed channels. The DC compression
sweep uses the existing attenuation-adjusted range, not an arbitrary new limit.

## What RL did - and did not do

The frozen legacy RL-hybrid path proposed its nominal setting 425. A classical
intersection across the old bank found only setting 490 eligible as a fixed
candidate for this request. Fresh physical-bias measurements then decided the
new pass. The 161,280 pre-screen lookups and 2,406 policy trial lookups used
existing data; they are not additional SPICE simulations.

This integration does **not** demonstrate a new RL training improvement. The
policy was not retrained on the physical reference. Other requests are checked
afresh when used; this acceptance run is not evidence that every target works.

## Evidence and remaining limits

All 616 archived evidence file hashes matched. All 135 corner measurement decks
share one circuit signature. The top-level exported deck is byte-identical to
the measured nominal physical AC/noise deck. The raw-evidence ZIP was checked
to include nested logs and waveforms (about 7.4 MB before this reading guide).
The schematic shows all 27 physical instances, with ordered-pin validation.

After the run, the presentation gate was additionally hardened to reject a
missing, duplicated, failed or different-circuit condition. The original runner
snapshot and its hashes remain preserved; no raw results were overwritten or
simulations repeated for this reporting check.

Still incomplete: transistor-level DFE/slicer/clock, physical Rs/Cs selectors,
common-mode generation, independent passive variation, mismatch and layout.
The reference current varies with PVT; the weakest requested frequency margin
from the identical Entry 104b circuit is small (~0.3%). Do not infer immunity
to added switch or layout parasitics. S7 is explicitly excluded as unknown,
not marked passed using the small geometry subtotal. Power is the measured
CTLE/reference VDD branch, not the entire receiver.

The previous report, legacy demo, original bias audits and RL bank are unchanged.

## Software verification

Full test suite: **2,823 passed before / 2,837 after**, 13 deselected, two
unchanged warnings. All 14 new product tests pass; focused group 34/34.
JavaScript syntax and diff-whitespace checks pass. The actual exported
schematic was visually inspected. No simulator/test job remains running.
