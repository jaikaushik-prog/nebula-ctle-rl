# Full 7.3 dB attenuator x CTLE bank verification -- entry 86

**Measured 2026-09-03.** This is the outcome of the experiment preregistered
in `PREDICTIONS.md` entry 86. It tests the 7.3 dB maximum input-attenuator
candidate across the complete tunable CTLE bank and the mandated PVT grid.

## Scope

The experiment measured one fixed transistor design with 8 real-PMOS
attenuator codes, 64 drawn-passive CTLE codes and all 45 process/voltage/
temperature corners: **23,040 real SKY130/ngspice circuit evaluations**. Each
device result was evaluated on seven constructed channels from 3 to 12 dB.
This is one design load, not the separate 135-point load grid, and the channels
are constructed models rather than measured boards.

Only the opt-in attenuator maximum changed, from production D11's 1.98 ratio
to 2.3173946499684783 (7.3 dB). Production remains unchanged until the owner
explicitly adopts the verified range.

## Result

| Channel loss | Scorable setting/corner rows | Solvable corner/request pairs | Requests served at all 45 corners | Change from entry 81 |
|---:|---:|---:|---:|---:|
| 3.0 dB | 10,378 | 720 / 720 | **16 / 16** | +2,859 rows; +5 requests |
| 4.5 dB | 13,100 | 720 / 720 | **16 / 16** | +2,297 rows; +1 request |
| 6.0 dB | 15,955 | 720 / 720 | **16 / 16** | +1,525 rows |
| 7.5 dB | 18,566 | 720 / 720 | **16 / 16** | +885 rows |
| 9.0 dB | 20,209 | 720 / 720 | **16 / 16** | +515 rows |
| 10.5 dB | 21,101 | 720 / 720 | **16 / 16** | +346 rows |
| 12.0 dB | 21,650 | 720 / 720 | **16 / 16** | +223 rows |

Every PVT corner has at least 114 scorable settings at 3 dB, compared with 54
for entry 81. There were zero hard simulator/device failures. The 1,390
device-valid rows rejected at the longest channel all report expected output
swing compression and are classified as unscorable link points.

## Preregistered gates

| Gate | Outcome | Evidence |
|---|---|---|
| Q1 exact membership and device health | **PASS** | 23,040 expected unique rows; zero hard failures |
| Q2 entry-85 reproduction | **PASS** | The final-boundary row reproduces gain, noise and valid 3/12 dB links |
| Q3 short-channel closure | **PASS** | 16/16 all-corner requests at 3 dB; 720/720 pairs solvable |
| Q4 no longer-channel regression | **PASS** | 16/16 at every loss from 4.5 to 12 dB |
| Q5 short-channel density | **PASS** | 10,378 scorable rows versus 7,519; every corner is nonzero |
| Q6 measured cost | **PASS** | Complete uninterrupted run: 7,875.99 s = 131.27 min, below 180 min |
| Q7 reporting | **PASS** | All losses, per-code counts, deltas and adaptation fields are present |

The preregistered recommendation gate therefore **passes**. This supports
adopting the 7.3 dB range; it does not itself make that human-controlled
production decision.

## Post-result decision

On 2026-09-03 the owner approved that recommendation as decision **D16**.
The production `ATTEN_MAX_X` is now the exact verified value
2.3173946499684783. The historical D11 1.98x range remains available through
the explicit range argument; no measurement artifact was rewritten.

## Q1 audit

The first result artifact incorrectly counted all `ok=false` rows as hard
device failures and printed Q1 FAIL. Inspection showed all 1,390 were ordinary
output-compression rejections after successful device measurement. A red-first
test now separates that known link-rejection signature from genuine simulator
or parsing failures. Commit `5e04916` contains only this analysis correction.
The frozen journal was then re-scored with **zero additional SPICE calls** into
a distinct artifact; the original artifact remains unchanged.

## Implication for RL

No corner/request pair requires a different code merely to comply across the
seven channels: **0/720**. A conservative fixed code is therefore sufficient
for binary compliance, so that is not a useful RL task.

The code giving the largest eye does change with channel loss in **580/720
(80.56%)** cases. A new RL experiment can therefore target eye/margin
optimization under hidden channel/PVT conditions. It must be separately
preregistered and beat fixed-code, random, coordinate-hillclimb and lookup/
oracle controls on held-out conditions before it can be called useful.

## Evidence

- `experiments/joint_bank_73_results.json` is the preserved first analysis;
  SHA-256 `A6B5979C6401B8FAFA4DD011B37BB1531930396CA064B8E765A872E22540A9F9`.
- `experiments/joint_bank_73_results_q1_reanalysis.json` is the corrected
  zero-SPICE analysis; SHA-256
  `D86CCC9E939C213AB18CE91CE41627D6D7DF5A67892198EB92299325FA8F591C`.
- `experiments/joint_bank_73_run.jsonl.gz` is the complete 23,040-row journal,
  compressed from 25,279,548 to 4,324,645 bytes. Its decoded SHA-256 is
  `1B5F941DF4B34F3C90F6DD050F264D8A77C7BB2E5CE4D9EED8CC29EBD9F9843F`;
  compressed SHA-256 is
  `D1CE3759BD93854E8A051FC85696DA755E8737328BF132B479F411619F8CAE22`.
- The local uncompressed journal is retained for analysis and ignored by Git.
- The complete non-slow suite passed **2,606 tests** both before and after the
  zero-SPICE reanalysis/evidence package, with 13 deselected and 2 warnings;
  the final invocation took 343.54 s.
